"""
Médico 360 — Serviço PharmaDB.
Integração com API PharmaDB para checagem farmacológica.
Cache via Redis para economizar requests.
"""

import json
import logging
from datetime import timedelta

import httpx
import redis.asyncio as redis

from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

# TTLs do cache
TTL_PA_LOOKUP = timedelta(days=90)
TTL_PRODUTO_LOOKUP = timedelta(days=90)
TTL_INTERACOES = timedelta(days=30)

# Semáforo de segurança
SEMAFORO = {
    "grave": {"level": 4, "color": "RED", "emoji": "🔴"},
    "moderada": {"level": 3, "color": "YELLOW", "emoji": "🟡"},
    "leve": {"level": 1, "color": "GREEN", "emoji": "🟢"},
}


class PharmaDBService:
    """Serviço de integração com PharmaDB + cache Redis."""

    def __init__(self):
        self.base_url = "https://api.pharmadb.com.br"
        self.api_key = settings.pharmadb_api_key
        self._jwt_token: str | None = None
        self._redis: redis.Redis | None = None
        logger.info(f"PharmaDB init — configured={bool(self.api_key)}")

    # ── Redis ────────────────────────────────────────────────

    async def _get_redis(self) -> redis.Redis:
        if self._redis is None:
            self._redis = redis.from_url(settings.redis_url, decode_responses=True)
        return self._redis

    async def _cache_get(self, key: str) -> dict | list | None:
        try:
            r = await self._get_redis()
            data = await r.get(key)
            if data:
                return json.loads(data)
        except Exception as e:
            logger.warning(f"Redis cache get error: {e}")
        return None

    async def _cache_set(self, key: str, value: dict | list, ttl: timedelta) -> None:
        try:
            r = await self._get_redis()
            await r.setex(key, int(ttl.total_seconds()), json.dumps(value, ensure_ascii=False))
        except Exception as e:
            logger.warning(f"Redis cache set error: {e}")

    # ── Autenticação PharmaDB ────────────────────────────────

    async def _get_token(self) -> str:
        if self._jwt_token:
            return self._jwt_token

        logger.info("PharmaDB auth POST — obtendo token")
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{self.base_url}/auth/token",
                headers={"x-api-key": self.api_key},
            )
            logger.info(f"PharmaDB auth status: {resp.status_code} — {resp.text[:200]}")
            resp.raise_for_status()
            data = resp.json()
            self._jwt_token = data["access_token"]
            logger.info(f"PharmaDB token obtido: {self._jwt_token[:20]}...")
            return self._jwt_token

    async def _api_get(self, path: str, params: dict | None = None) -> dict:
        token = await self._get_token()
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{self.base_url}{path}",
                headers={"Authorization": f"Bearer {token}"},
                params=params,
            )
            if resp.status_code == 401:
                self._jwt_token = None
                token = await self._get_token()
                resp = await client.get(
                    f"{self.base_url}{path}",
                    headers={"Authorization": f"Bearer {token}"},
                    params=params,
                )
            resp.raise_for_status()
            return resp.json()

    async def _api_post(self, path: str, body: dict) -> dict:
        token = await self._get_token()
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{self.base_url}{path}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            if resp.status_code == 401:
                self._jwt_token = None
                token = await self._get_token()
                resp = await client.post(
                    f"{self.base_url}{path}",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
            resp.raise_for_status()
            return resp.json()

    # ── Busca de Princípios Ativos ───────────────────────────

    async def buscar_principio_ativo(self, nome: str) -> dict | None:
        cache_key = f"pharmadb:pa:nome:{nome.lower().strip()}"

        cached = await self._cache_get(cache_key)
        if cached:
            return cached

        try:
            data = await self._api_get("/v1/principios-ativos/busca", {"q": nome})
            logger.info(f"PharmaDB PA busca '{nome}': {data}")
            items = data.get("items", [])
            if not items:
                return None

            pa = items[0]
            result = {
                "pa_id": pa["id"],
                "nome_dcb": pa["nome_dcb"],
            }

            try:
                detalhes = await self._api_get(f"/v1/principios-ativos/{pa['id']}")
                result["codigo_atc"] = detalhes.get("codigo_atc")
                result["descricao"] = detalhes.get("descricao")
            except Exception:
                pass

            await self._cache_set(cache_key, result, TTL_PA_LOOKUP)
            return result

        except Exception as e:
            logger.error(f"Erro ao buscar PA '{nome}': {e}")
            return None

    # ── Busca de Produtos (nome comercial) ───────────────────

    async def buscar_produto(self, nome: str) -> dict | None:
        cache_key = f"pharmadb:produto:nome:{nome.lower().strip()}"

        cached = await self._cache_get(cache_key)
        if cached:
            return cached

        try:
            data = await self._api_get("/v1/produtos/busca", {"q": nome})
            items = data.get("items", [])
            if not items:
                return None

            prod = items[0]
            result = {
                "produto_id": prod["id"],
                "nome": prod["nome"],
                "principios_ativos": prod.get("principios_ativos", []),
                "laboratorio": prod.get("laboratorio"),
                "tarja": prod.get("tarja"),
            }

            await self._cache_set(cache_key, result, TTL_PRODUTO_LOOKUP)
            return result

        except Exception as e:
            logger.error(f"Erro ao buscar produto '{nome}': {e}")
            return None

    # ── Resolver medicamento (genérico ou comercial) ─────────

    async def resolver_medicamento(self, nome: str) -> dict | None:
        pa = await self.buscar_principio_ativo(nome)
        if pa:
            return {"tipo": "pa", "id": pa["pa_id"], "nome": pa["nome_dcb"], **pa}

        produto = await self.buscar_produto(nome)
        if produto:
            return {"tipo": "produto", "id": produto["produto_id"], "nome": produto["nome"], **produto}

        return None

    # ── Interações de um PA ──────────────────────────────────

    async def get_interacoes_pa(self, pa_id: int, gravidade: str | None = None) -> list[dict]:
        cache_key = f"pharmadb:interacoes:pa:{pa_id}"
        if gravidade:
            cache_key += f":{gravidade}"

        cached = await self._cache_get(cache_key)
        if cached:
            return cached

        try:
            params = {"page": 1, "per_page": 200}
            if gravidade:
                params["gravidade"] = gravidade

            data = await self._api_get(f"/v1/interacoes/pa/{pa_id}", params)
            interacoes = data.get("interacoes", [])

            await self._cache_set(cache_key, interacoes, TTL_INTERACOES)
            return interacoes

        except Exception as e:
            logger.error(f"Erro ao buscar interações do PA {pa_id}: {e}")
            return []

    # ── Interações cruzadas entre 2 produtos ─────────────────

    async def _get_interacoes_cruzadas(self, produto_a: int, produto_b: int) -> list[dict]:
        sorted_ids = tuple(sorted([produto_a, produto_b]))
        cache_key = f"pharmadb:interacoes:cruzadas:{sorted_ids[0]}-{sorted_ids[1]}"

        cached = await self._cache_get(cache_key)
        if cached:
            return cached

        try:
            data = await self._api_get(
                "/v1/interacoes/cruzadas",
                {"produto_a": produto_a, "produto_b": produto_b}
            )
            interacoes = data.get("interacoes", [])
            await self._cache_set(cache_key, interacoes, TTL_INTERACOES)
            return interacoes

        except Exception as e:
            logger.error(f"Erro nas interações cruzadas {produto_a} x {produto_b}: {e}")
            return []

    # ── PAs de um produto ────────────────────────────────────

    async def _get_pas_do_produto(self, produto_id: int) -> list[int]:
        cache_key = f"pharmadb:produto:pas:{produto_id}"

        cached = await self._cache_get(cache_key)
        if cached:
            return cached

        try:
            data = await self._api_get(f"/v1/produtos/{produto_id}")
            composicao = data.get("composicao", [])
            pa_ids = [c["pa_id"] for c in composicao if "pa_id" in c]
            await self._cache_set(cache_key, pa_ids, TTL_PRODUTO_LOOKUP)
            return pa_ids

        except Exception as e:
            logger.error(f"Erro ao buscar PAs do produto {produto_id}: {e}")
            return []

    # ── Interações batch (3+ produtos) ───────────────────────

    async def get_interacoes_batch(self, produto_ids: list[int]) -> dict:
        sorted_ids = sorted(produto_ids)
        cache_key = f"pharmadb:interacoes:batch:{'-'.join(map(str, sorted_ids))}"

        cached = await self._cache_get(cache_key)
        if cached:
            return cached

        try:
            data = await self._api_post("/v1/interacoes/batch", {"produto_ids": produto_ids})
            await self._cache_set(cache_key, data, TTL_INTERACOES)
            return data

        except Exception as e:
            logger.error(f"Erro no batch de interações: {e}")
            return {"interacoes": [], "total_interacoes": 0}

    # ── Checagem completa (fluxo principal do PHARMA_CHECK) ──

    async def checar_interacoes(self, medicamentos: list[str]) -> dict:
        if len(medicamentos) < 2:
            return {
                "status": "sem_interacao",
                "message": "É necessário informar pelo menos 2 medicamentos para checar interações.",
                "medicamentos_encontrados": [],
                "interacoes": [],
            }

        # 1. Resolver todos os medicamentos
        resolvidos = []
        nao_encontrados = []

        for med in medicamentos:
            resultado = await self.resolver_medicamento(med)
            if resultado:
                resolvidos.append(resultado)
            else:
                nao_encontrados.append(med)

        if len(resolvidos) < 2:
            return {
                "status": "insuficiente",
                "message": f"Encontrei apenas {len(resolvidos)} medicamento(s) na base. Preciso de pelo menos 2.",
                "medicamentos_encontrados": [r["nome"] for r in resolvidos],
                "nao_encontrados": nao_encontrados,
                "interacoes": [],
            }

        # 2. Buscar interações cruzadas
        interacoes_encontradas = []

        produtos = [r for r in resolvidos if r["tipo"] == "produto"]
        pas = [r for r in resolvidos if r["tipo"] == "pa"]

        # Se temos 2+ produtos, usar cruzadas ou batch
        if len(produtos) >= 2:
            produto_ids = [p["id"] for p in produtos]

            if len(produto_ids) == 2:
                interacoes_encontradas = await self._get_interacoes_cruzadas(
                    produto_ids[0], produto_ids[1]
                )
            else:
                batch_result = await self.get_interacoes_batch(produto_ids)
                interacoes_encontradas = batch_result.get("interacoes", [])

        # Se temos mix de produtos e PAs, ou só PAs, ou produtos não deu resultado
        if not interacoes_encontradas:
            todos_pa_ids = []

            for r in resolvidos:
                if r["tipo"] == "pa":
                    todos_pa_ids.append(r["id"])
                elif r["tipo"] == "produto":
                    produto_pas = await self._get_pas_do_produto(r["id"])
                    todos_pa_ids.extend(produto_pas)

            for i, pa_a in enumerate(todos_pa_ids):
                interacoes_a = await self.get_interacoes_pa(pa_a)

                for interacao in interacoes_a:
                    pa_b_id = interacao.get("pa_b", {}).get("id")
                    if pa_b_id in todos_pa_ids and pa_b_id != pa_a:
                        par = tuple(sorted([pa_a, pa_b_id]))
                        ja_existe = any(
                            tuple(sorted([
                                ie.get("pa_a", {}).get("id"),
                                ie.get("pa_b", {}).get("id")
                            ])) == par
                            for ie in interacoes_encontradas
                        )
                        if not ja_existe:
                            interacoes_encontradas.append(interacao)

        # 3. Montar semáforo
        alertas = []
        for interacao in interacoes_encontradas:
            gravidade = interacao.get("gravidade", "leve")
            semaforo = SEMAFORO.get(gravidade, SEMAFORO["leve"])

            alertas.append({
                "pa_a": interacao.get("pa_a", {}).get("nome_dcb", ""),
                "pa_b": interacao.get("pa_b", {}).get("nome_dcb", ""),
                "gravidade": gravidade,
                "semaforo_level": semaforo["level"],
                "semaforo_color": semaforo["color"],
                "semaforo_emoji": semaforo["emoji"],
                "efeito_clinico": interacao.get("efeito_clinico", ""),
                "mecanismo": interacao.get("mecanismo", ""),
                "manejo_clinico": interacao.get("manejo_clinico", ""),
                "referencias": interacao.get("referencias", []),
            })

        alertas.sort(key=lambda x: x["semaforo_level"], reverse=True)

        if not alertas:
            return {
                "status": "sem_interacao",
                "message": "Nenhuma interação conhecida encontrada entre os medicamentos informados.",
                "medicamentos_encontrados": [r["nome"] for r in resolvidos],
                "nao_encontrados": nao_encontrados,
                "interacoes": [],
            }

        return {
            "status": "interacoes_encontradas",
            "total_interacoes": len(alertas),
            "medicamentos_encontrados": [r["nome"] for r in resolvidos],
            "nao_encontrados": nao_encontrados,
            "interacoes": alertas,
        }

    # ── Formatar resposta como texto ─────────────────────────

    def formatar_resposta_texto(self, resultado: dict) -> str:
        if resultado["status"] == "sem_interacao":
            return f"🟢 {resultado['message']}"

        if resultado["status"] == "insuficiente":
            msg = resultado["message"]
            if resultado.get("nao_encontrados"):
                msg += f"\n\nMedicamentos não encontrados na base: {', '.join(resultado['nao_encontrados'])}"
            return f"⚠️ {msg}"

        linhas = ["## Checagem Farmacológica\n"]

        meds = ", ".join(resultado["medicamentos_encontrados"])
        linhas.append(f"**Medicamentos analisados:** {meds}\n")

        if resultado.get("nao_encontrados"):
            linhas.append(f"⚠️ Não encontrados na base: {', '.join(resultado['nao_encontrados'])}\n")

        linhas.append(f"**Total de interações:** {resultado['total_interacoes']}\n")
        linhas.append("---\n")

        for alerta in resultado["interacoes"]:
            emoji = alerta["semaforo_emoji"]
            grav = alerta["gravidade"].upper()
            linhas.append(f"### {emoji} {alerta['pa_a']} ↔ {alerta['pa_b']} — **{grav}**\n")

            if alerta["efeito_clinico"]:
                linhas.append(f"**Efeito clínico:** {alerta['efeito_clinico']}\n")
            if alerta["mecanismo"]:
                linhas.append(f"**Mecanismo:** {alerta['mecanismo']}\n")
            if alerta["manejo_clinico"]:
                linhas.append(f"**Manejo clínico:** {alerta['manejo_clinico']}\n")

            refs = alerta.get("referencias", [])
            if refs:
                linhas.append("**Referências:**")
                for ref in refs:
                    linhas.append(f"- [{ref.get('text', 'Link')}]({ref.get('url', '')})")

            linhas.append("")

        return "\n".join(linhas)


# ── Instância singleton ──────────────────────────────────────

_pharmadb = PharmaDBService()


def get_pharmadb_service() -> PharmaDBService:
    return _pharmadb