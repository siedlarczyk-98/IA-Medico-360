import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import COOKIE_NAME, get_current_user
from app.core.config import get_settings
from app.core.database import get_db
from app.core.limiter import limiter
from app.medicina import especialidades, identidade
from app.models.models import AuditLog, User
from app.repositories import auth_repository
from app.schemas.auth import (
    DeleteAccountRequest,
    InviteAcceptRequest,
    InviteGenerateRequest,
    InviteGenerateResponse,
    OnboardingRequest,
    OTPRequest,
    OTPVerify,
    RegisterRequest,
    TokenResponse,
    UpdateProfileRequest,
    UserResponse,
)
from app.services import (
    auth_service,
    cache_service,
    consent_service,
    data_subject_service,
)
from app.services.integracoes import curseduca_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_session_cookie(response: Response, token: str) -> None:
    """Seta o cookie SSO compartilhado entre apps do mesmo domínio raiz, além do token no body.

    `SameSite` não é preferência: os apps rodam dentro do iframe da Waid, então
    toda chamada à API é cross-site e `lax` faz o navegador ENGOLIR o cookie —
    ele é aceito na resposta e nunca mais enviado. Daí os 401 em `/auth/me` que
    só somem quando o `Authorization` header entra em cena, mascarando o SSO
    quebrado entre os apps.

    `None` exige `Secure`, e `Secure` exige HTTPS. Em desenvolvimento (HTTP) o
    par `None`+inseguro é rejeitado pelo navegador, o que quebraria o local —
    por isso ali continua `lax`, onde mesmo-site já basta.
    """
    settings = get_settings()
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.is_production,
        samesite="none" if settings.is_production else "lax",
        domain=settings.cookie_domain or None,
        max_age=settings.jwt_access_token_expire_minutes * 60,
    )


@router.post("/register", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("5/minute")
async def register(request: Request, body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Cadastro público: cria usuário e envia link de acesso por email."""
    settings = get_settings()
    if not settings.allow_public_registration:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cadastro por convite apenas")
    await auth_service.register_and_send_invite(db, body.email)


@router.post("/invite/generate", response_model=InviteGenerateResponse)
@limiter.limit("30/minute")
async def generate_invite(
    request: Request,
    body: InviteGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Apenas admins podem gerar convites")
    invite = await auth_service.generate_invite_token(
        db, current_user.id, body.email, body.expires_hours
    )
    db.add(
        AuditLog(
            user_id=current_user.id,
            action="invite.generate",
            entity_type="invite",
            entity_id=invite.id,
            metadata_={"invited_email": body.email},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    )
    settings = get_settings()
    url = f"{settings.frontend_url}/invite?token={invite.token}"
    return InviteGenerateResponse(
        invite_url=url,
        token=str(invite.token),
        expires_at=invite.expires_at,
    )


@router.post("/invite/accept", response_model=TokenResponse)
@limiter.limit("10/minute")
async def accept_invite(request: Request, response: Response, body: InviteAcceptRequest, db: AsyncSession = Depends(get_db)):
    user, token = await auth_service.accept_invite(db, body.token, body.email)
    _set_session_cookie(response, token)
    return TokenResponse(access_token=token, onboarding_complete=user.onboarding_complete)


class EmbedTokenRequest(BaseModel):
    """Um dos dois: `token` (Waid, verificável) ou `email` (legado, em migração).

    O `email` não prova identidade — quem souber o e-mail de um colega recebe a
    sessão dele. Ele só continua aceito enquanto os apps migram, e apenas com
    `embed_email_fallback_enabled`.
    """

    token: str | None = None
    email: str | None = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip().lower()
        if "@" not in v or len(v) < 3:
            raise ValueError("Email inválido")
        return v

    @model_validator(mode="after")
    def exigir_um_dos_dois(self) -> "EmbedTokenRequest":
        if bool(self.token) == bool(self.email):
            raise ValueError("Envie `token` (recomendado) ou `email`, não os dois")
        return self


async def _auditar_embed(
    db: AsyncSession, request: Request, user: User, via: str
) -> None:
    """Registra quem entrou por embed, e por qual caminho.

    Existe porque não existia: até aqui, uma sessão emitida por embed não deixava
    rastro nenhum. Sem isso, um acesso indevido pelo caminho por e-mail seria
    indetectável mesmo depois de descoberto o método.
    """
    db.add(
        AuditLog(
            user_id=user.id,
            action="auth.embed",
            entity_type="user",
            entity_id=user.id,
            metadata_={"via": via, "origin": request.headers.get("origin", "")},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    )
    await db.commit()


@router.post("/embed/token", response_model=TokenResponse)
@limiter.limit("10/minute")
async def embed_token(
    request: Request,
    response: Response,
    body: EmbedTokenRequest,
    db: AsyncSession = Depends(get_db),
):
    """Autenticação para o embed no LMS. Dois caminhos, com garantias diferentes.

    **Por token (Waid)** — verificável. A página pede identidade por `postMessage`,
    a Waid devolve um token opaco de uso único (5 min), e nós o trocamos pela
    identidade numa chamada server-to-server. O e-mail é RESULTADO da verificação,
    não entrada. Quem não está dentro do iframe, logado na Waid, não tem token.

    **Por e-mail (legado)** — NÃO verificável, e é o motivo desta migração
    existir: o header `Origin` é forjável server-side, e a validação de matrícula
    prova que o e-mail é de um membro, não que o chamador é ele. Um `curl` com o
    `Origin` certo e o e-mail de um colega devolve a sessão dele.

    O caminho por e-mail só responde com `embed_email_fallback_enabled` e some na
    Fase 4 do plano de migração. Cada uso sai em WARNING — é esse log que diz
    quando é seguro cortar.
    """
    origin = request.headers.get("origin", "")
    settings = get_settings()
    allowed_origins = set(settings.embed_allowed_origins) | {settings.calculadoras_url}
    if origin not in allowed_origins:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Origem não autorizada para embed")

    if body.token:
        user, via = await _entrar_por_token_waid(db, body.token), "token"
    else:
        if not settings.embed_email_fallback_enabled:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Este app precisa ser atualizado: a identificação por e-mail foi descontinuada.",
            )
        user, via = await _entrar_por_email(db, body.email), "email"

    await _auditar_embed(db, request, user, via)
    token = auth_service.create_access_token(user)
    _set_session_cookie(response, token)
    return TokenResponse(access_token=token, onboarding_complete=user.onboarding_complete)


class IdentidadeEmbedResponse(BaseModel):
    nome: str | None
    email: str


@router.post("/embed/identidade", response_model=IdentidadeEmbedResponse)
@limiter.limit("10/minute")
async def identidade_embed(request: Request, body: EmbedTokenRequest):
    """Quem é o aluno, sem criar sessão nem usuário.

    Existe para as landing pages, que são PÚBLICAS: elas só querem
    pré-preencher o formulário com o nome e o e-mail de quem está do outro lado,
    e não têm login. Antes isso vinha do `?email=` na URL, que a Waid posiciona
    como legado.

    **Não cria conta, de propósito.** Quem abre uma LP pode não ser usuário do
    produto, e criar cadastro a partir de um formulário de captação seria
    inventar consentimento que ninguém deu.

    Público sem token nosso, e isso é seguro: o token da Waid é de uso único,
    vale 5 minutos e só chega a quem está dentro do iframe, logado. É a mesma
    prova que sustenta `/embed/token`; o que muda é só o que devolvemos.
    """
    if not body.token:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Informe o token de identidade da plataforma."
        )
    try:
        identidade = await curseduca_service.trocar_token_de_identidade(body.token)
    except curseduca_service.TokenDeIdentidadeInvalido as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            {"codigo": exc.codigo, "mensagem": "Token de identidade inválido ou expirado."},
        ) from exc
    except curseduca_service.CurseducaNotConfigured as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Não foi possível confirmar sua identidade no momento.",
        ) from exc

    return IdentidadeEmbedResponse(nome=identidade.nome, email=identidade.email)


async def _entrar_por_token_waid(db: AsyncSession, token_waid: str) -> User:
    """Caminho verificável: troca o token pela identidade e resolve o usuário."""
    try:
        identidade = await curseduca_service.trocar_token_de_identidade(token_waid)
    except curseduca_service.TokenDeIdentidadeInvalido as exc:
        # 401 com código, e não 403: o cliente CONSEGUE se recuperar sozinho
        # pedindo outro token pelo mesmo evento. Tratar como falha definitiva
        # deixaria o médico numa tela de erro que um retry resolveria.
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            {"codigo": exc.codigo, "mensagem": "Token de identidade inválido ou expirado."},
        ) from exc
    except curseduca_service.CurseducaNotConfigured as exc:
        # Credencial nossa, permissão ausente para o endpoint, ou a Waid fora do
        # ar. Pedir outro token não resolve — insistir viraria laço.
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Não foi possível confirmar sua identidade no momento.",
        ) from exc

    await _throttle_by_email("embed_token", identidade.uuid, limit=20, window_seconds=900)

    user, _ = await auth_service.get_or_create_por_identidade_waid(db, identidade)

    anterior = await auth_service.sincronizar_email_da_waid(db, user, identidade)
    if anterior:
        db.add(
            AuditLog(
                user_id=user.id,
                action="auth.email_alterado_pela_waid",
                entity_type="user",
                entity_id=user.id,
                metadata_={"de": anterior, "para": user.email},
            )
        )
        await db.commit()

    # Enriquecimento, não portão: o `validate` não devolve `groups`, então os
    # grupos `[CFM]` ainda vêm da API de membros — agora fail-open e cacheada.
    membro = await curseduca_service.buscar_membro_para_enriquecer(user.email)
    await auth_service.reconciliar_especialidade_do_embed(db, user, membro)
    return user


async def _entrar_por_email(db: AsyncSession, email: str) -> User:
    """Caminho legado. Fail-closed na matrícula, mas NÃO prova identidade."""
    logger.warning(
        "Embed autenticado por e-mail (caminho legado, não verificável): %s", email
    )
    membro = await curseduca_service.verify_active_member(email)
    user, _ = await auth_service.get_or_create_embed_user(email, db)
    await auth_service.reconciliar_especialidade_do_embed(db, user, membro)
    return user


async def _throttle_by_email(scope: str, email: str, limit: int, window_seconds: int) -> None:
    """Rate limit por e-mail, complementar ao limite por IP do slowapi.

    O e-mail só existe no corpo do request, fora do alcance do `key_func` do slowapi;
    sem isso, quem rotaciona IP (ou forja X-Forwarded-For) escapa do throttle de OTP.
    """
    key = cache_service.make_key(f"ratelimit:{scope}", email.strip().lower())
    if await cache_service.rate_limit_exceeded(key, limit, window_seconds):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Muitas tentativas para este e-mail. Tente novamente mais tarde.",
        )


@router.post("/otp/request", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("3/15minutes")
async def request_otp(request: Request, body: OTPRequest, db: AsyncSession = Depends(get_db)):
    await _throttle_by_email("otp_request", body.email, limit=3, window_seconds=900)
    await auth_service.request_otp(db, body.email)


@router.post("/otp/verify", response_model=TokenResponse)
@limiter.limit("5/minute")
async def verify_otp(request: Request, response: Response, body: OTPVerify, db: AsyncSession = Depends(get_db)):
    await _throttle_by_email("otp_verify", body.email, limit=10, window_seconds=900)
    user, token = await auth_service.verify_otp(db, body.email, body.code)
    _set_session_cookie(response, token)
    return TokenResponse(access_token=token, onboarding_complete=user.onboarding_complete)


@router.post("/onboarding", response_model=TokenResponse)
@limiter.limit("30/minute")
async def complete_onboarding(
    request: Request,
    body: OnboardingRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Aplica o que o médico informou e deixa o SERVIDOR decidir se acabou.

    Não exige um conjunto fixo de campos: nome e especialidade costumam chegar
    sozinhos (webhook do cadastro, grupos `[CFM]` da Curseduca), e pedir de novo
    o que já se sabe é o que tornava este formulário pesado. O cliente manda o
    que a tela coletou; quem diz se o perfil está completo é
    `identidade.pendencias()`, com o estado real do usuário na mão.
    """
    from datetime import date as date_type

    if body.name is not None:
        current_user.name = body.name
    if body.phone_number is not None:
        current_user.phone_number = f"+55{body.phone_number}"
    current_user.med_status = body.med_status
    if body.crm is not None and body.crm_state is not None:
        current_user.crm = body.crm
        current_user.crm_state = body.crm_state
    if body.specialty and identidade.usuario_pode_editar(current_user):
        # Só entra como fallback: se o cadastro ou o grupo já preencheram, o que
        # o médico digitou é ignorado — o campo é identidade profissional, e a
        # precedência em `identidade.py` é quem decide.
        identidade.aplicar_especialidade(
            current_user, slug=body.specialty, fonte=identidade.FONTE_DECLARADO
        )
    if body.enrollment_year:
        current_user.enrollment_date = date_type(body.enrollment_year, 1, 1)

    # Mesma transacao do onboarding, de proposito: se o consentimento nao for
    # gravado, o cadastro tambem nao se completa. Usuario ativo sem prova de
    # aceite e justamente o estado que isto veio corrigir.
    await consent_service.registrar(
        db,
        current_user,
        consent_service.TERMOS_E_PRIVACIDADE,
        aceito=body.terms_accepted,
        request=request,
    )

    pendencias = identidade.pendencias(current_user, aceite_vigente=body.terms_accepted)
    current_user.onboarding_complete = not pendencias

    await db.commit()
    await db.refresh(current_user)
    from app.services.auth_service import create_access_token
    token = create_access_token(current_user)
    return TokenResponse(
        access_token=token,
        onboarding_complete=current_user.onboarding_complete,
        onboarding_pendencias=pendencias,
    )


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    resp = UserResponse.model_validate(current_user)
    resp.intercom_user_hash = auth_service.intercom_user_hash(current_user)
    resp.onboarding_pendencias = identidade.pendencias(
        current_user,
        aceite_vigente=await consent_service.aceitou_termos(db, current_user.id),
    )
    resp.specialty_editavel = identidade.usuario_pode_editar(current_user)
    resp.med_status_opcoes = identidade.med_status_possiveis(current_user)
    return resp


@router.patch("/me", response_model=TokenResponse)
@limiter.limit("30/minute")
async def update_me(
    request: Request,
    body: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.email and body.email != current_user.email:
        result = await db.execute(select(User).where(User.email == body.email))
        if result.scalar_one_or_none():
            raise HTTPException(status.HTTP_409_CONFLICT, "Email já está em uso")
        current_user.email = body.email
    if body.name is not None:
        current_user.name = body.name

    # Trocar de registro invalida a verificação anterior: o CRM novo não foi
    # conferido em lugar nenhum ainda.
    if body.crm is not None and body.crm_state is not None:
        if (body.crm, body.crm_state) != (current_user.crm, current_user.crm_state):
            current_user.crm = body.crm
            current_user.crm_state = body.crm_state
            current_user.crm_status = None
            current_user.crm_verified_at = None

    if body.specialty_slug is not None:
        # A especialidade tranca assim que uma fonte automática a preenche: ela
        # é identidade profissional e vai definir acesso a conteúdo pago, não
        # preferência de leitura. Quem quer ajustar o que LÊ mexe nos temas
        # (`news.user_topics`), que continuam livres.
        if not identidade.usuario_pode_editar(current_user):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Sua especialidade veio do seu cadastro e não pode ser alterada por aqui. "
                "Fale com o suporte se estiver incorreta.",
            )
        identidade.aplicar_especialidade(
            current_user, slug=body.specialty_slug, fonte=identidade.FONTE_DECLARADO
        )

    await db.commit()
    await db.refresh(current_user)
    from app.services.auth_service import create_access_token
    token = create_access_token(current_user)
    return TokenResponse(access_token=token, onboarding_complete=current_user.onboarding_complete)


class CorrigirEspecialidadeRequest(BaseModel):
    specialty_slug: str

    @field_validator("specialty_slug")
    @classmethod
    def validar(cls, v: str) -> str:
        slug = especialidades.normalizar(v)
        if slug is None:
            raise ValueError(f"Especialidade desconhecida: {v}")
        return slug


@router.patch("/admin/users/{user_id}/especialidade", response_model=UserResponse)
@limiter.limit("30/minute")
async def corrigir_especialidade(
    request: Request,
    user_id: uuid.UUID,
    body: CorrigirEspecialidadeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Correção da especialidade pelo suporte.

    É a válvula que torna a trava do campo defensável: o médico não edita a
    própria especialidade (ela reflete o que foi contratado e vai definir
    acesso), mas a LGPD art. 18, III garante ao titular o direito de corrigir
    dado desatualizado. Sem este endpoint, o conserto seria UPDATE manual em
    produção — sem trilha, sem revisão, sem limite.

    Grava com fonte `admin`, o posto mais alto: uma correção de suporte não pode
    ser desfeita pela reconciliação do próximo login.
    """
    if current_user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Apenas admins podem corrigir especialidade")

    alvo = await db.get(User, user_id)
    if alvo is None or not alvo.status:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuário não encontrado")

    anterior = {"slug": alvo.specialty_slug, "fonte": alvo.specialty_source}
    identidade.aplicar_especialidade(
        alvo, slug=body.specialty_slug, fonte=identidade.FONTE_ADMIN
    )
    # O campo passa a valer acesso: quem mudou, quando e a partir de quê tem
    # que ficar registrado.
    db.add(
        AuditLog(
            user_id=current_user.id,
            action="user.especialidade.corrigir",
            entity_type="user",
            entity_id=alvo.id,
            metadata_={"de": anterior, "para": alvo.specialty_slug},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    )
    await db.commit()
    await db.refresh(alvo)

    resp = UserResponse.model_validate(alvo)
    resp.onboarding_pendencias = identidade.pendencias(
        alvo, aceite_vigente=await consent_service.aceitou_termos(db, alvo.id)
    )
    resp.specialty_editavel = identidade.usuario_pode_editar(alvo)
    resp.med_status_opcoes = identidade.med_status_possiveis(alvo)
    return resp


@router.get("/me/consentimentos")
async def listar_consentimentos(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    O que o titular consentiu, e sob qual versao dos documentos.

    `versao_atual: false` significa que os documentos foram revisados depois do
    aceite - o consentimento e valido para o texto antigo, nao para o vigente.
    """
    return {
        "versao_vigente": consent_service.VERSAO_DOCUMENTOS,
        "consentimentos": await consent_service.situacao_atual(db, current_user.id),
    }


@router.post("/me/consentimentos/{tipo}/revogar", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("10/hour")
async def revogar_consentimento(
    request: Request,
    tipo: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Revoga um consentimento (LGPD art. 8, §5º: revogacao a qualquer momento, por
    procedimento gratuito e facilitado).

    Nao apaga o aceite anterior - grava uma NOVA manifestacao negativa. O
    historico e a prova; sobrescrever destruiria a evidencia de que houve aceite
    valido no periodo em que os dados foram tratados.

    `termos_e_privacidade` nao e revogavel por aqui: sem ele nao ha como prestar
    o servico, e o caminho correto e a exclusao da conta (DELETE /auth/me), que
    de fato apaga os dados.
    """
    if tipo == consent_service.TERMOS_E_PRIVACIDADE:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Para deixar de aceitar os termos, exclua a conta em DELETE /auth/me - "
            "assim os dados sao efetivamente removidos, nao apenas marcados.",
        )
    if tipo not in {consent_service.USO_DADOS_ANONIMIZADOS}:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Consentimento desconhecido: {tipo}")

    await consent_service.registrar(db, current_user, tipo, aceito=False, request=request)
    await db.commit()


@router.get("/me/export")
@limiter.limit("5/hour")
async def export_me(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Portabilidade (LGPD art. 18, V): devolve todos os dados do titular em JSON.

    Limite baixo de propósito — a consulta varre todo o histórico do usuário e
    não há razão legítima para pedir isso com frequência.
    """
    return await data_subject_service.exportar_dados(db, current_user)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("10/minute")
async def delete_me(
    request: Request,
    body: DeleteAccountRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not current_user.name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Complete o onboarding antes de excluir a conta")
    if not body.confirm_name or body.confirm_name != current_user.name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nome de confirmação não confere")

    # A cascata em si vive no repositório: a ORDEM das exclusões é conhecimento
    # sobre o schema, não sobre HTTP. Aqui fica só o que é do endpoint —
    # validar a confirmação e fechar a transação.
    await auth_repository.apagar_dados_do_usuario(db, current_user.id)
    await db.commit()
