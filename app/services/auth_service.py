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


def create_access_token(user: "User") -> str:
    settings = get_settings()
    expire = _utcnow() + timedelta(minutes=settings.jwt_access_token_expire_minutes)
    payload = {
        "sub": str(user.id),
        "role": user.role,
        "exp": expire,
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

    user = await repo.get_user_by_email(db, email, active_only=True)
    if user:
        return user, False
    try:
        user = User(email=email, role="beta_user", status=True, onboarding_complete=False)
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user, True
    except IntegrityError:
        await db.rollback()
        user = await repo.get_user_by_email(db, email, active_only=True)
        assert user is not None, "IntegrityError implica que o usuário já existe"
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
        return user, False

    user = await repo.get_user_by_email(db, identidade.email, active_only=True)
    if user is not None:
        user.waid_uuid = identidade.uuid
        await db.commit()
        logger.info("waid_uuid preenchido para user=%s no primeiro login por token", user.id)
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
        code=code,
        expires_at=_utcnow() + timedelta(minutes=settings.otp_expire_minutes),
    )
    db.add(otp)
    await db.commit()

    await email_service.send_otp(email, code)


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

    if otp.code != code:
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
