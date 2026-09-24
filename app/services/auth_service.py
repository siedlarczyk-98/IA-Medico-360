import asyncio
import hashlib
import hmac
import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt as pyjwt
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.medicina import especialidades, identidade
from app.models.models import InviteToken, OtpCode, User
from app.repositories import auth_repository as repo
from app.services import email_service
from app.services.integracoes import curseduca_service

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def intercom_user_hash(user: "User") -> str | None:
    """
    Gera o user_hash (HMAC-SHA256 do user.id) exigido pelo Messenger Security
    do Intercom. Retorna None se o secret não estiver configurado.
    O identificador usado (user.id) deve ser o mesmo enviado como user_id no boot.
    """
    settings = get_settings()
    secret = settings.intercom_identity_secret
    if not secret:
        return None
    return hmac.new(
        secret.encode("utf-8"),
        str(user.id).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


class IdentidadeDivergente(Exception):
    """O e-mail da identidade pertence a uma conta vinculada a OUTRO `waid_uuid`.

    Não há resposta segura além de recusar: entregar a conta existente dá a um
    desconhecido o histórico clínico de outra pessoa, e criar uma conta nova
    esbarra no e-mail único. Quem trata é o endpoint do embed — 403, auditoria e
    alarme, porque o caso legítimo (o LMS re-provisionou o aluno com uuid novo)
    só se resolve com o suporte corrigindo o vínculo.
    """

    def __init__(self, *, user_id, email: str):
        super().__init__(f"identidade divergente para {email}")
        self.user_id = user_id
        self.email = email


class ContaInativa(Exception):
    """A identidade é de uma conta desativada (`users.status = false`).

    Nada no código desativa conta — a exclusão pela LGPD apaga a linha. Então isto
    é decisão de alguém, à mão, e a resposta é recusar com clareza: 403, com uma
    frase que diz o que fazer.

    Antes, os dois caminhos do embed erravam em sentidos opostos. Por
    `waid_uuid`, a conta desativada RECEBIA token — e depois levava 401 em toda
    chamada, o que desde a reentrada automática do chat vira um ciclo de telas de
    espera. Por e-mail, a busca só enxergava contas ativas, tentava criar outra
    com o mesmo e-mail, e a unicidade estourava em 500.
    """

    def __init__(self, *, user_id):
        super().__init__(f"conta inativa {user_id}")
        self.user_id = user_id


def create_access_token(user: "User", *, auth_time: int | None = None) -> str:
    """Emite o JWT de sessão.

    `auth_time` é o instante (epoch) em que o usuário PROVOU quem é. Login de
    verdade não passa nada e o relógio começa agora. Quem está só RENOVANDO um
    token — perfil, onboarding — tem de repassar o `auth_time` do token em uso
    (`deps.auth_time_da_sessao`): é isso que impede a renovação de esticar a
    sessão além de `session_max_age_hours`.

    `tv` é a versão do token no momento da emissão; o logout a incrementa no
    usuário e todos os tokens anteriores morrem.
    """
    settings = get_settings()
    agora = _utcnow()
    inicio = int(agora.timestamp()) if auth_time is None else auth_time
    fim_da_sessao = datetime.fromtimestamp(inicio, tz=agora.tzinfo) + timedelta(
        hours=settings.session_max_age_hours
    )
    expire = min(agora + timedelta(minutes=settings.jwt_access_token_expire_minutes), fim_da_sessao)
    payload = {
        "sub": str(user.id),
        "role": user.role,
        "exp": expire,
        "auth_time": inicio,
        "tv": user.token_version or 0,
    }
    return pyjwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


async def generate_invite_token(
    db: AsyncSession,
    created_by: uuid.UUID,
    email: str | None = None,
    expires_hours: int | None = None,
) -> InviteToken:
    settings = get_settings()
    hours = expires_hours if expires_hours is not None else settings.invite_token_expire_hours
    invite = InviteToken(
        token=uuid.uuid4(),
        email=email,
        created_by=created_by,
        expires_at=_utcnow() + timedelta(hours=hours),
    )
    db.add(invite)
    await db.commit()
    await db.refresh(invite)
    return invite


async def _get_valid_invite(db: AsyncSession, token_str: str) -> InviteToken:
    try:
        token_uuid = uuid.UUID(token_str)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Token de convite inválido")

    invite = await repo.get_invite_by_token(db, token_uuid)
    if not invite or invite.used or invite.expires_at < _utcnow():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Link de convite inválido ou expirado")
    return invite


async def accept_invite(
    db: AsyncSession, token_str: str, email: str | None = None
) -> tuple[User, str]:
    invite = await _get_valid_invite(db, token_str)

    resolved_email = invite.email or email
    if not resolved_email:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Email é obrigatório")

    user = await repo.get_user_by_email(db, resolved_email)

    # Open invites (no pre-bound email) must never grant access to existing accounts —
    # that would allow any token holder to take over arbitrary accounts by supplying their email.
    if user is not None and invite.email is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Email já cadastrado. Faça login pelo código OTP.",
        )

    if not user:
        user = User(email=resolved_email, role="beta_user", status=True, onboarding_complete=False)
        db.add(user)

    invite.used = True
    await db.commit()
    await db.refresh(user)

    token = create_access_token(user)
    return user, token


async def register_and_send_invite(db: AsyncSession, email: str) -> None:
    """Auto-cadastro: cria usuário (se não existir) e envia link de convite por email."""
    settings = get_settings()
    user = await repo.get_user_by_email(db, email)
    if not user:
        user = User(email=email, role="beta_user", status=True, onboarding_complete=False)
        db.add(user)
        await db.commit()
        await db.refresh(user)

    invite = InviteToken(
        token=uuid.uuid4(),
        email=email,
        expires_at=_utcnow() + timedelta(hours=settings.invite_token_expire_hours),
    )
    db.add(invite)
    await db.commit()

    invite_url = f"{settings.frontend_url}/invite?token={invite.token}"
    await email_service.send_invite(email, invite_url)


async def get_or_create_embed_user(email: str, db: AsyncSession) -> tuple["User", bool]:
    """Retorna (user, created). created=True se o usuário foi criado agora."""
    from sqlalchemy.exc import IntegrityError

    # Sem `active_only`: filtrar aqui escondia a conta desativada, e o INSERT
    # abaixo estourava na unicidade do e-mail. Ver `ContaInativa`.
    user = await repo.get_user_by_email(db, email)
    if user:
        if not user.status:
            raise ContaInativa(user_id=user.id)
        return user, False
    try:
        user = User(email=email, role="beta_user", status=True, onboarding_complete=False)
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user, True
    except IntegrityError:
        await db.rollback()
        user = await repo.get_user_by_email(db, email)
        assert user is not None, "IntegrityError implica que o usuário já existe"
        if not user.status:
            raise ContaInativa(user_id=user.id)
        return user, False


async def get_or_create_por_identidade_waid(
    db: AsyncSession, identidade: curseduca_service.IdentidadeWaid
) -> tuple["User", bool]:
    """Encontra (ou cria) o usuário a partir da identidade verificada pela Waid.

    A ordem é o ponto: **uuid primeiro, e-mail depois**. A doc da Waid diz que o
    uuid é estável e o e-mail não, e a busca por e-mail existe aqui só como
    ponte — ela é o BACKFILL. Quem já tinha conta ganha o `waid_uuid` no primeiro
    login pelo caminho novo, um por vez, sem script.

    Depois do backfill, trocar de e-mail na Waid deixa de duplicar a conta.

    Retorna `(user, criado)`.
    """
    from sqlalchemy import select

    user = await db.scalar(select(User).where(User.waid_uuid == identidade.uuid))
    if user is not None:
        if not user.status:
            raise ContaInativa(user_id=user.id)
        return user, False

    # Sem `active_only`, pelo mesmo motivo do caminho legado: a conta desativada
    # com este e-mail tem que ser ACHADA para ser recusada, e não recriada.
    user = await repo.get_user_by_email(db, identidade.email)
    if user is not None:
        if not user.status:
            raise ContaInativa(user_id=user.id)
        # A guarda é o que faz este backfill ser ÚNICO, como o docstring acima, o
        # log abaixo e a migration 008 já afirmavam. Sem ela a vinculação era
        # sobrescrita toda vez que a busca por uuid falhava e a por e-mail
        # acertava — e o log seguia dizendo "primeiro login".
        #
        # O caminho não precisa de atacante: basta o LMS re-provisionar a conta
        # com uuid novo para o mesmo e-mail, e o vínculo passa a alternar a cada
        # login. A premissa de estabilidade do uuid é do provedor de identidade;
        # aqui ela é reforçada.
        #
        # Assimetria que confirmava o furo: `sincronizar_email_da_waid` (abaixo)
        # já recusa o caso espelhado, quando o e-mail novo pertence a outra conta.
        if user.waid_uuid is None:
            user.waid_uuid = identidade.uuid
            await db.commit()
            logger.info("waid_uuid preenchido para user=%s no primeiro login por token", user.id)
        elif user.waid_uuid != identidade.uuid:
            # RECUSADA DE VERDADE (2026-09-21). O log já dizia "identidade nova
            # recusada" — e a linha seguinte devolvia a conta assim mesmo: quem
            # chegava com uuid B e o e-mail de uma conta do uuid A ENTRAVA na
            # conta de A. Combinado com a troca de e-mail sem verificação (que
            # também saiu), um médico plantava a própria conta para um colega, e
            # as conversas clínicas do colega se acumulavam onde ele as lia.
            logger.warning(
                "Conta de e-mail %s já vinculada a outro waid_uuid; identidade nova "
                "RECUSADA, nenhuma sessão emitida (user=%s). Ver migration 008_waid_uuid.",
                identidade.email,
                user.id,
            )
            raise IdentidadeDivergente(user_id=user.id, email=identidade.email)
        return user, False

    user = User(
        email=identidade.email,
        waid_uuid=identidade.uuid,
        name=identidade.nome,
        role="beta_user",
        status=True,
        onboarding_complete=False,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user, True


async def sincronizar_email_da_waid(
    db: AsyncSession, user: "User", identidade: curseduca_service.IdentidadeWaid
) -> str | None:
    """Atualiza `users.email` quando ele mudou na Waid. Devolve o e-mail antigo, se mudou.

    A Waid é a fonte desse campo para quem entra por lá. Mas o e-mail também é
    chave de login pelo OTP: mudá-lo altera COMO a pessoa entra pelo outro
    caminho, então quem chama deve registrar em `AuditLog` — é por isso que esta
    função devolve o valor antigo em vez de trocar em silêncio.

    Nunca levanta: um conflito de unicidade aqui (o e-mail novo já pertence a
    outra conta) é situação real, e barrar o login não a resolve.
    """
    if not identidade.email or identidade.email == user.email:
        return None

    from sqlalchemy import select

    ocupado = await db.scalar(select(User.id).where(User.email == identidade.email))
    if ocupado is not None:
        logger.warning(
            "E-mail da Waid (%s) já pertence a outra conta; user=%s segue com o antigo",
            identidade.email,
            user.id,
        )
        return None

    anterior = user.email
    user.email = identidade.email
    await db.commit()
    return anterior


def _nome_do_membro(membro: dict | None) -> str | None:
    """O `name` do payload da Curseduca, se houver algo utilizável."""
    if not isinstance(membro, dict):
        return None
    nome = membro.get("name")
    return nome.strip() if isinstance(nome, str) and nome.strip() else None


async def reconciliar_especialidade_do_embed(
    db: AsyncSession, user: "User", membro: dict | None
) -> bool:
    """Preenche nome e especialidade a partir do payload da Curseduca.

    Roda a CADA login de embed, não só na criação do usuário. É de propósito:
    quem entrou antes de existir cadastro novo já está na base sem
    especialidade, e só volta a passar por aqui logando. Como
    `aplicar_especialidade` é idempotente e respeita precedência, repetir é
    inofensivo — e é o que faz a base antiga se preencher sozinha.

    Fonte `waid_grupo`, o posto mais baixo entre as automáticas: o nome do grupo
    é artefato de controle de acesso e pode ser renomeado no painel. Ele nunca
    desfaz o que veio do cadastro, do CFM ou do suporte.

    Nunca levanta exceção: isto acontece dentro do LOGIN. Falhar aqui deixaria o
    médico de fora por causa de um enriquecimento de perfil.
    """
    try:
        mudou = False

        # O nome vem no MESMO payload e era descartado junto com os grupos:
        # `get_or_create_embed_user` cria o usuário só com e-mail, então todo
        # mundo que entra pelo LMS começava anônimo e tinha que digitar o
        # próprio nome numa tela — sendo que a Curseduca já o conhece.
        #
        # Só preenche quando está vazio. Nome que o médico ajustou é dele: a
        # Curseduca guarda o nome da matrícula, que pode estar abreviado ou com
        # o nome de outra pessoa que pagou o curso.
        nome_curseduca = _nome_do_membro(membro)
        if nome_curseduca and not (user.name or "").strip():
            user.name = nome_curseduca
            mudou = True

        nomes = curseduca_service.nomes_de_grupos(membro)
        if not nomes:
            if mudou:
                await db.commit()
            return mudou

        resultado = especialidades.interpretar_grupos(nomes)

        # Existir QUALQUER grupo `[CFM]` — inclusive o GENERALISTA — prova que a
        # página de cadastro consultou o Conselho a partir de um CRM. É o que
        # permite parar de oferecer "aluno de graduação" a quem tem registro.
        # Só marca uma vez: reconciliação não é nova verificação.
        if (resultado.slugs or resultado.generalista) and not user.crm_verified_at:
            user.crm_verified_at = _utcnow()
            mudou = True

        if not resultado.slugs and not resultado.generalista and not user.specialty_slug:
            # Nenhum grupo `[CFM]`, nem sequer o `[CFM] GENERALISTA` — ou seja,
            # não dá para dizer nem que o CFM foi consultado. Registrar os nomes
            # revela a convenção real do cadastro sem precisar adivinhá-la.
            #
            # A condição se auto-limita: some conforme a base for sendo
            # preenchida, em vez de virar ruído permanente no log.
            logger.info(
                "Sem especialidade após reconciliar user=%s. Grupos vistos: %s",
                user.id,
                ", ".join(nomes) or "(nenhum)",
            )

        if resultado.desconhecidos:
            # O modo de falha que este trabalho veio eliminar: grupo criado
            # automaticamente com nome fora das 55 (tipicamente uma ÁREA DE
            # ATUAÇÃO do CFM, como Hepatologia). Sem este log, o médico ficaria
            # sem especialidade e ninguém saberia. O rótulo vai no log porque é
            # o insumo para virar alias em `app/medicina/especialidades.py`.
            logger.warning(
                "Grupo [CFM] não reconhecido para user=%s: %s. "
                "Provável área de atuação — avaliar alias em app/medicina/especialidades.py",
                user.id,
                ", ".join(resultado.desconhecidos),
            )

        if resultado.slugs:
            mudou = identidade.aplicar_especialidade(
                user, slugs=list(resultado.slugs), fonte=identidade.FONTE_WAID_GRUPO
            ) or mudou

        if mudou:
            await db.commit()
        return mudou
    except Exception:
        logger.exception("Falha ao reconciliar especialidade do embed para user=%s", user.id)
        await db.rollback()
        return False


async def request_otp(db: AsyncSession, email: str) -> None:
    user = await repo.get_user_by_email(db, email, active_only=True)
    if not user:
        return  # silencioso — não revelar se email existe

    await repo.invalidate_unused_otps(db, email)

    settings = get_settings()
    code = str(secrets.randbelow(900000) + 100000)
    otp = OtpCode(
        email=email,
        code=_resumo_do_codigo(email, code),
        expires_at=_utcnow() + timedelta(minutes=settings.otp_expire_minutes),
    )
    db.add(otp)
    await db.commit()

    # EM SEGUNDO PLANO, e não é por velocidade. O envio leva de centenas de
    # milissegundos a segundos; e-mail sem conta voltava na hora (o `return` lá em
    # cima). Bastava medir o tempo da resposta para saber quem tem conta — a
    # enumeração que o "silencioso" pretendia impedir. Agora os dois caminhos
    # respondem no mesmo tempo.
    _enviar_em_segundo_plano(email, code)


# Referência forte: sem ela o coletor de lixo pode recolher a tarefa no meio.
_envios_em_voo: set[asyncio.Task] = set()


def _enviar_em_segundo_plano(email: str, code: str) -> None:
    async def _enviar() -> None:
        try:
            await email_service.send_otp(email, code)
        except Exception:
            # A resposta já foi dada; o que resta é deixar rastro. Sem isto o
            # médico esperaria um código que nunca saiu, e o log não diria nada.
            logger.exception("Falha ao enviar o código de acesso")

    tarefa = asyncio.create_task(_enviar(), name="enviar-otp")
    _envios_em_voo.add(tarefa)
    tarefa.add_done_callback(_envios_em_voo.discard)


def _resumo_do_codigo(email: str, code: str) -> str:
    """HMAC-SHA256 do código, com o segredo do servidor como chave.

    O código ficava em texto puro: quem lesse a tabela (dump, réplica, log de
    consulta) entrava na conta de qualquer médico com código pendente. Um hash
    simples não resolveria — são só um milhão de códigos possíveis, e a tabela
    inteira se quebra em milissegundos. Com HMAC, sem o segredo do servidor o valor
    gravado não serve para nada. O e-mail entra na mensagem para o mesmo código de
    duas contas não produzir o mesmo resumo.
    """
    chave = get_settings().jwt_secret_key.encode()
    mensagem = f"{email.strip().lower()}:{code}".encode()
    return hmac.new(chave, mensagem, hashlib.sha256).hexdigest()


_OTP_MAX_ATTEMPTS = 5


async def verify_otp(db: AsyncSession, email: str, code: str) -> tuple[User, str]:
    now = _utcnow()
    otp = await repo.get_active_otp(db, email, now=now)
    if not otp:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Código inválido ou expirado")

    if otp.failed_attempts >= _OTP_MAX_ATTEMPTS:
        otp.used = True
        await db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Código inválido ou expirado")

    # `compare_digest`: comparação em tempo constante.
    if not hmac.compare_digest(otp.code, _resumo_do_codigo(email, code)):
        otp.failed_attempts += 1
        if otp.failed_attempts >= _OTP_MAX_ATTEMPTS:
            otp.used = True
        await db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Código inválido ou expirado")

    otp.used = True

    user = await repo.get_user_by_email(db, email, active_only=True)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuário não encontrado")

    await db.commit()

    token = create_access_token(user)
    return user, token
