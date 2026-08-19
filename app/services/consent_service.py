"""
Registro de consentimento (LGPD).

O ônus da prova é do controlador (LGPD art. 8, §2º): não basta o usuário marcar a
caixa, é preciso conseguir DEMONSTRAR depois que ele marcou — quando, de onde, e
sob qual versão do documento. Antes disso existir, o onboarding já mostrava o
checkbox de "Li e aceito", mas o valor só habilitava o botão e não era gravado
em lugar nenhum.

Tipos de consentimento são deliberadamente separados. Aceitar os termos para usar
o produto NÃO autoriza uso secundário dos dados: monetização de insights
anonimizados (RN-DATA-001) envolve dado sensível de saúde e, pelo art. 11, exige
consentimento específico e destacado. Amarrar os dois num checkbox só invalidaria
os dois.
"""

import logging

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import ConsentLog, User, utcnow

logger = logging.getLogger(__name__)

# Obrigatório para usar o produto.
TERMOS_E_PRIVACIDADE = "termos_e_privacidade"

# Opcional, ainda NÃO implementado. Só passa a ser coletado quando a
# monetização (RN-DATA-001) existir, em checkbox próprio e desmarcado por padrão.
USO_DADOS_ANONIMIZADOS = "uso_dados_anonimizados"

# Consentir com um documento que muda depois não prova nada: o registro guarda a
# versão vigente no momento do aceite. Ao publicar uma revisão dos documentos,
# suba esta constante — quem aceitou a anterior aparece como desatualizado, em
# vez de parecer que consentiu com um texto que nunca viu.
VERSAO_DOCUMENTOS = "2026-08"


def _origem(request: Request | None) -> tuple[str | None, str | None]:
    if request is None:
        return None, None
    ip = request.client.host if request.client else None
    return ip, request.headers.get("user-agent")


async def registrar(
    db: AsyncSession,
    user: User,
    tipo: str,
    aceito: bool,
    request: Request | None = None,
) -> ConsentLog:
    """
    Grava uma manifestação de vontade. Nunca sobrescreve a anterior: o histórico
    inteiro importa (aceite, revogação, novo aceite), e é ele que responde
    "sob qual versão o usuário estava quando aceitou?".

    Não faz commit — quem chama decide o limite da transação.
    """
    registro = ConsentLog(
        user_id=user.id,
        consent_type=f"{tipo}@{VERSAO_DOCUMENTOS}",
        accepted=aceito,
        accepted_at=utcnow() if aceito else None,
        revoked_at=None if aceito else utcnow(),
    )
    registro.ip_address, registro.user_agent = _origem(request)
    db.add(registro)
    logger.info("consentimento registrado: user=%s tipo=%s aceito=%s", user.id, tipo, aceito)
    return registro


async def historico(db: AsyncSession, user_id) -> list[ConsentLog]:
    resultado = await db.execute(
        select(ConsentLog).where(ConsentLog.user_id == user_id).order_by(ConsentLog.created_at.desc())
    )
    return list(resultado.scalars().all())


async def situacao_atual(db: AsyncSession, user_id) -> dict[str, dict]:
    """
    Estado vigente por tipo: o registro mais recente de cada um vence.

    A chave ignora a versão para agrupar o histórico do mesmo consentimento, mas
    a versão aceita continua no retorno — é ela que diz se o aceite ainda vale
    para os documentos publicados hoje.
    """
    atual: dict[str, dict] = {}
    for registro in await historico(db, user_id):
        tipo, _, versao = registro.consent_type.partition("@")
        if tipo in atual:
            continue  # já vimos o mais recente deste tipo
        atual[tipo] = {
            "aceito": registro.accepted,
            "versao": versao or None,
            "versao_atual": versao == VERSAO_DOCUMENTOS,
            "em": (registro.accepted_at or registro.revoked_at or registro.created_at),
        }
    return atual
