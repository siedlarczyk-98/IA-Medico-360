"""
Integração com a Curseduca/Waid: identidade do aluno e dados de matrícula.

Duas funções, com papéis muito diferentes:

`trocar_token_de_identidade` — O PORTÃO.
    A Waid entrega à página, por `postMessage`, um token opaco de uso único
    (5 min). Trocamos esse token por `{uuid, name, email}`. O token não carrega
    informação: a verdade está na resposta. É isso que torna a identidade
    VERIFICÁVEL, e não apenas informada — quem não está dentro do iframe, logado
    na Waid, não tem token nenhum para apresentar.

    Contrato (doc "Identidade do aluno em seção incorporada", v1.2):
      POST {api_base}/api/v1/embed-identity-tokens/validate  {"token": "..."}
      200 -> {uuid, name, email}
      400 -> token inválido ou JÁ USADO   (o cliente deve pedir outro)
      410 -> token expirado               (o cliente deve pedir outro)
      401 -> api_key ausente/inválida     (configuração NOSSA)
      403 -> sem permissão para o endpoint(configuração NOSSA — precisa de
             liberação específica para a credencial, no painel da Waid)

`verify_active_member` / `_fetch_member` — o caminho ANTIGO e o enriquecimento.
    Nasceu para reduzir a superfície do embed por `?email=`, que não prova
    identidade nenhuma (o header Origin é forjável server-side). Continua
    fail-closed enquanto aquele caminho existir.

    Mas o payload dele também é a ÚNICA fonte dos grupos `[CFM] <especialidade>`
    — o `validate` acima devolve identidade, não matrícula. Por isso, no caminho
    por token ele é usado só para ENRIQUECER: ali pode falhar sem barrar
    ninguém, porque o portão já foi a troca do token.
"""

import logging
from dataclasses import dataclass

import httpx
from fastapi import HTTPException, status

from app.core import circuit_breaker
from app.core.config import get_settings
from app.core.http_client import get_client

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 8.0

# Grupo de acesso muda em escala de dias; a autenticação passou a acontecer a
# cada carregamento de página. Sem cache, seria uma chamada externa por load.
TTL_MEMBRO_SEGUNDOS = 600


class CurseducaNotConfigured(Exception):
    """Validação habilitada mas a integração respondeu erro de configuração/indisponibilidade."""


class TokenDeIdentidadeInvalido(Exception):
    """Token recusado pela Waid — inválido, já usado ou expirado.

    Separada de `CurseducaNotConfigured` de propósito: aqui o conserto é PEDIR
    OUTRO TOKEN, e o cliente consegue fazer isso sozinho. Tratar os dois como o
    mesmo erro deixaria o médico numa tela de falha que um retry resolveria.
    """

    def __init__(self, codigo: str):
        self.codigo = codigo  # token_invalido | token_expirado
        super().__init__(codigo)


@dataclass(frozen=True)
class IdentidadeWaid:
    """Quem a Waid diz que é a pessoa do outro lado do iframe.

    `uuid` é a chave: a doc é explícita que ele é estável e o e-mail não. Um
    médico que troque de e-mail na Waid continua sendo a mesma pessoa aqui.
    """

    uuid: str
    nome: str | None
    email: str


def _credenciais() -> tuple[str, str, str]:
    """Base e credenciais da API, ou 503 se a integração não está configurada."""
    settings = get_settings()
    if not settings.curseduca_api_base or not settings.curseduca_api_key:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Integração com a plataforma não está configurada.",
        )
    return (
        settings.curseduca_api_base.rstrip("/"),
        settings.curseduca_api_key,
        settings.curseduca_access_token,
    )


async def trocar_token_de_identidade(token: str) -> IdentidadeWaid:
    """Troca o token de uso único da Waid pela identidade do aluno. FAIL-CLOSED.

    Este é o portão de acesso: em qualquer dúvida, ninguém entra. Mas separa dois
    tipos de falha, porque a ação certa é diferente em cada uma:

      `TokenDeIdentidadeInvalido` — o token não serve mais (inválido, já usado,
          expirado). Acontece no uso normal: o médico recarregou a página, ou a
          troca demorou mais que os 5 minutos. O cliente pede outro pelo mesmo
          evento e segue. NÃO é erro para mostrar na tela.

      `CurseducaNotConfigured` — credencial nossa errada, sem permissão para o
          endpoint, ou a Waid fora do ar. Pedir outro token não resolve; insistir
          vira laço infinito.
    """
    api_base, api_key, access_token = _credenciais()
    url = f"{api_base}/api/v1/embed-identity-tokens/validate"
    headers = {"api_key": api_key, "accept": "application/json"}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"

    async def _consulta():
        return await get_client().post(
            url, json={"token": token}, headers=headers, timeout=_TIMEOUT_SECONDS
        )

    try:
        resp = await circuit_breaker.curseduca.chama(_consulta)
    except circuit_breaker.CircuitoAberto as exc:
        raise CurseducaNotConfigured(str(exc)) from exc
    except httpx.HTTPError as exc:
        raise CurseducaNotConfigured(f"Falha ao contatar a Waid: {exc}") from exc

    if resp.status_code == 200:
        dados = resp.json()
        uuid = (dados or {}).get("uuid")
        email = (dados or {}).get("email")
        if not isinstance(dados, dict) or not uuid or not email:
            # Formato inesperado é problema NOSSO de contrato, não do token —
            # mandar o cliente pedir outro entraria em laço.
            raise CurseducaNotConfigured(
                f"Resposta do validate sem uuid/email: {resp.text[:200]}"
            )
        nome = dados.get("name")
        return IdentidadeWaid(
            uuid=str(uuid),
            nome=nome.strip() if isinstance(nome, str) and nome.strip() else None,
            email=str(email).strip().lower(),
        )

    if resp.status_code == 400:
        raise TokenDeIdentidadeInvalido("token_invalido")
    if resp.status_code == 410:
        raise TokenDeIdentidadeInvalido("token_expirado")

    # 401 (api_key), 403 (sem permissão para o endpoint — a doc avisa que ela é
    # liberada à parte pelo responsável da conta Waid), 5xx.
    raise CurseducaNotConfigured(
        f"Waid respondeu {resp.status_code} ao validar o token: {resp.text[:200]}"
    )


async def _fetch_member(email: str, api_base: str, api_key: str, access_token: str) -> dict | None:
    """Consulta a API e devolve o membro, ou `None` se não existir. Fail-closed em erro.

    Devolve o objeto INTEIRO, não um booleano: o payload já traz `groups`, e é
    de lá que sai a especialidade do médico (grupos `[CFM] <especialidade>`,
    criados automaticamente pela página de cadastro). Antes esta função baixava
    tudo isso e descartava — a reconciliação de especialidade sai de graça, sem
    uma requisição a mais.
    """
    url = f"{api_base.rstrip('/')}/api/v1/members/by"
    headers = {"api_key": api_key, "accept": "application/json"}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"

    async def _consulta():
        return await get_client().get(
            url, params={"email": email}, headers=headers, timeout=_TIMEOUT_SECONDS
        )

    try:
        # Disjuntor mais tolerante que os demais: abrir aqui bloqueia LOGIN, não
        # só enriquecimento. Ainda assim protege contra a API pendurada segurando
        # conexões enquanto vários alunos tentam entrar.
        resp = await circuit_breaker.curseduca.chama(_consulta)
    except circuit_breaker.CircuitoAberto as exc:
        raise CurseducaNotConfigured(str(exc)) from exc
    except httpx.HTTPError as exc:
        raise CurseducaNotConfigured(f"Falha ao contatar a API da Curseduca: {exc}") from exc

    if resp.status_code == 200:
        data = resp.json()
        # Membro encontrado quando a resposta traz o e-mail do próprio membro.
        return data if isinstance(data, dict) and data.get("email") else None
    if resp.status_code == 404:
        return None  # e-mail não corresponde a nenhum membro
    # 400 (query), 401 (api_key), 403 (token), 5xx -> não dá para confirmar => fail-closed.
    raise CurseducaNotConfigured(
        f"Curseduca respondeu {resp.status_code} ao validar membro: {resp.text[:200]}"
    )


async def verify_active_member(email: str) -> dict | None:
    """Levanta 403 se o e-mail não for membro; no-op quando a validação está desligada.

    Fail-closed: se a validação está ligada mas a integração não está pronta/configurada
    ou a API não respondeu OK, levanta 503 em vez de deixar passar.

    Devolve o payload do membro (para a reconciliação de especialidade) ou `None`
    quando a validação está desligada — nesse caso não houve consulta e não há o
    que reconciliar. Em produção isso não acontece: `_validate_production_secrets`
    derruba o startup se a validação estiver desligada.
    """
    settings = get_settings()
    if not settings.curseduca_validation_enabled:
        return None

    if not settings.curseduca_api_base or not settings.curseduca_api_key:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Validação de membro Curseduca habilitada mas não configurada.",
        )

    try:
        membro = await _fetch_member(
            email,
            settings.curseduca_api_base,
            settings.curseduca_api_key,
            settings.curseduca_access_token,
        )
    except CurseducaNotConfigured as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Não foi possível validar o membro na Curseduca no momento.",
        ) from exc

    if membro is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "E-mail não corresponde a um membro ativo.")
    return membro


async def buscar_membro_para_enriquecer(email: str) -> dict | None:
    """O payload do membro, para ler os grupos `[CFM]`. FAIL-OPEN e cacheado.

    Só existe porque o `validate` devolve identidade (`uuid`, `name`, `email`) e
    NÃO devolve `groups` — que é de onde sai a especialidade do médico.

    A diferença de política em relação a `verify_active_member` é o ponto todo:
    ali a consulta é o PORTÃO (dúvida = ninguém entra); aqui ela é
    ENRIQUECIMENTO, porque o portão já foi a troca do token. Uma instabilidade
    na API de membros deixava todo mundo de fora; agora custa no máximo uma
    especialidade não preenchida, que a próxima entrada resolve.

    Cacheado por 10 minutos: grupo de acesso muda em escala de dias, e sem cache
    isto seria uma chamada externa em todo carregamento de página — já que a
    autenticação passou a acontecer a cada load.
    """
    from app.services import cache_service

    chave = cache_service.make_key("waid_membro", email)
    try:
        em_cache = await cache_service.get_json(chave)
        if em_cache is not None:
            return em_cache
    except Exception:
        logger.debug("Cache indisponível ao buscar membro; seguindo direto para a API")

    try:
        api_base, api_key, access_token = _credenciais()
        membro = await _fetch_member(email, api_base, api_key, access_token)
    except (CurseducaNotConfigured, HTTPException) as exc:
        logger.warning("Enriquecimento de perfil indisponível para %s: %s", email, exc)
        return None

    if membro is not None:
        try:
            await cache_service.set_json(chave, membro, TTL_MEMBRO_SEGUNDOS)
        except Exception:
            logger.debug("Não foi possível cachear o membro; segue sem cache")
    return membro


def nomes_de_grupos(membro: dict | None) -> list[str]:
    """Extrai os nomes dos grupos do payload, tolerando formato inesperado.

    Defensivo de propósito: é payload de terceiro num caminho de LOGIN. Um
    `groups` ausente, nulo ou com formato diferente não pode derrubar a
    autenticação de ninguém — no pior caso o médico entra sem especialidade,
    que é exatamente o estado em que ele já estava.
    """
    if not isinstance(membro, dict):
        return []
    grupos = membro.get("groups")
    if not isinstance(grupos, list):
        return []
    return [g["name"] for g in grupos if isinstance(g, dict) and isinstance(g.get("name"), str)]
