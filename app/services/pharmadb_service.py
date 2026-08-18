"""
Médico 360 — Serviço PharmaDB.
Integração com API PharmaDB para checagem farmacológica, bulas, receitas e genéricos.
Cache via Redis. Token JWT com renovação automática antes de 60min.
"""

import asyncio
import json
import logging
import time
from datetime import timedelta

import redis.asyncio as redis

from app.core.config import get_settings
from app.core.http_client import get_client

settings = get_settings()
logger = logging.getLogger(__name__)

BASE_URL = "https://api.pharmadb.com.br"

TTL_PA = timedelta(days=90)
TTL_PRODUTO = timedelta(days=90)
TTL_INTERACOES = timedelta(days=30)
TTL_BULA = timedelta(days=30)
TTL_RECEITA = timedelta(days=30)
TTL_GENERICOS = timedelta(days=7)

TOKEN_LIFETIME_S = 3300  # renova 5min antes de expirar (60min = 3600s)

SEMAFORO = {
    "grave":    {"level": 4, "color": "RED",    "emoji": "🔴"},
    "moderada": {"level": 3, "color": "YELLOW", "emoji": "🟡"},
    "leve":     {"level": 1, "color": "GREEN",  "emoji": "🟢"},
}


_BULA_CLEANUP_PROMPT = """Você recebe seções brutas de uma bula de medicamento extraídas de PDF.
Reformate cada seção em markdown limpo para leitura médica:
- Remova numeração de seções (ex: "1.", "2.", "8.")
- Remova textos legais, dados de fabricante, CNPJ, CRF, endereços, páginas
- Remova referências a "vide embalagem", "ligue para 0800", histórico de alterações
- Preserve apenas o conteúdo clínico relevante
- Use bullet points onde fizer sentido
- Seja conciso mas completo

Produto: {nome}

Seções:
{secoes}

Retorne APENAS o markdown formatado, sem comentários."""


async def _limpar_secoes_bula(nome: str, secoes: dict[str, str]) -> str:
    secoes_texto = "\n\n".join(f"### {titulo}\n{texto}" for titulo, texto in secoes.items())
    try:
        client = get_client()
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": settings.anthropic_api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 1500,
                "messages": [{
                    "role": "user",
                    "content": _BULA_CLEANUP_PROMPT.format(nome=nome, secoes=secoes_texto),
                }],
            },
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json()["content"][0]["text"].strip()
    except Exception as e:
        logger.warning(f"Falha ao limpar bula via LLM: {e}")
        # fallback: retorna texto bruto concatenado
        return secoes_texto


class PharmaDBService:

    def __init__(self):
        self.api_key = settings.pharmadb_api_key
        self._jwt_token: str | None = None
        self._token_obtained_at: float = 0.0
        self._redis: redis.Redis | None = None
        logger.info(f"PharmaDB init — configured={bool(self.api_key)}")

    # ── Redis ────────────────────────────────────────────────────────────────

    async def _get_redis(self) -> redis.Redis:
        if self._redis is None:
            self._redis = redis.from_url(
                settings.redis_url, decode_responses=True, max_connections=20
            )
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

    # ── Autenticação ─────────────────────────────────────────────────────────

    def _token_valid(self) -> bool:
        return bool(self._jwt_token) and (time.monotonic() - self._token_obtained_at) < TOKEN_LIFETIME_S

    async def _get_token(self) -> str:
        if self._token_valid():
            return self._jwt_token

        logger.info("PharmaDB auth — obtendo novo token")
        client = get_client()
        resp = await client.post(
            f"{BASE_URL}/auth/token",
            headers={"x-api-key": self.api_key},
            timeout=10,
        )
        logger.info(f"PharmaDB auth status: {resp.status_code}")
        resp.raise_for_status()
        self._jwt_token = resp.json()["access_token"]
        self._token_obtained_at = time.monotonic()
        return self._jwt_token

    # ── HTTP helpers ─────────────────────────────────────────────────────────

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        """
        Executa uma requisição autenticada. Renova o token automaticamente
        e refaz a chamada uma vez em caso de 401 (token expirado server-side).
        """
        client = get_client()
        url = f"{BASE_URL}{path}"
        extra_headers = kwargs.pop("headers", {})

        async def _call() -> "httpx.Response":
            token = await self._get_token()
            headers = {"Authorization": f"Bearer {token}", **extra_headers}
            return await client.request(method, url, headers=headers, timeout=15, **kwargs)

        resp = await _call()
        if resp.status_code == 401:
            self._jwt_token = None
            resp = await _call()
        resp.raise_for_status()
        return resp.json()

    async def _get(self, path: str, params: dict | None = None) -> dict:
        return await self._request("GET", path, params=params)

    async def _post(self, path: str, body: dict) -> dict:
        return await self._request(
            "POST", path,
            headers={"Content-Type": "application/json"},
            json=body,
        )

    # ── Princípios Ativos ─────────────────────────────────────────────────────

    async def buscar_pa(self, nome: str) -> dict | None:
        """Busca PA por nome genérico/DCB. Retorna {pa_id, nome_dcb, codigo_atc, total_interacoes}."""
        cache_key = f"pharmadb:pa:nome:{nome.lower().strip()}"
        cached = await self._cache_get(cache_key)
        if cached:
            return cached

        try:
            data = await self._get("/v1/principios-ativos/busca", {"q": nome, "per_page": 5})
            items = data.get("items", [])
            if not items:
                return None

            pa = items[0]
            try:
                detalhe = await self._get(f"/v1/principios-ativos/{pa['id']}")
                result = {
                    "pa_id": detalhe["id"],
                    "nome_dcb": detalhe["nome_dcb"],
                    "codigo_atc": detalhe.get("codigo_atc"),
                    "total_interacoes": detalhe.get("total_interacoes", 0),
                }
            except Exception:
                result = {"pa_id": pa["id"], "nome_dcb": pa["nome_dcb"], "codigo_atc": None, "total_interacoes": 0}

            await self._cache_set(cache_key, result, TTL_PA)
            return result
        except Exception as e:
            logger.error(f"Erro ao buscar PA '{nome}': {e}")
            return None

    # ── Produtos ──────────────────────────────────────────────────────────────

    async def buscar_produto(self, nome: str) -> dict | None:
        """Busca produto por nome (comercial ou genérico). Retorna dados completos."""
        cache_key = f"pharmadb:produto:busca:{nome.lower().strip()}"
        cached = await self._cache_get(cache_key)
        if cached:
            return cached

        try:
            data = await self._get("/v1/produtos/busca", {"q": nome, "per_page": 5})
            items = data.get("items", [])
            if not items:
                return None

            prod = items[0]
            result = {
                "produto_id": prod["id"],
                "nome": prod["nome"],
                "laboratorio": prod.get("laboratorio"),
                "tarja": prod.get("tarja"),
                "categoria_regulatoria": prod.get("categoria_regulatoria"),
                "principios_ativos": prod.get("principios_ativos", []),
            }
            await self._cache_set(cache_key, result, TTL_PRODUTO)
            return result
        except Exception as e:
            logger.error(f"Erro ao buscar produto '{nome}': {e}")
            return None

    # ── Interações ────────────────────────────────────────────────────────────

    async def _interacoes_do_pa(self, pa_id) -> list:
        """Interações de um princípio ativo, com cache. Levanta em erro (o caller loga)."""
        cache_key = f"pharmadb:interacoes:pa:{pa_id}"
        interacoes_pa = await self._cache_get(cache_key)
        if interacoes_pa is None:
            data = await self._get(f"/v1/interacoes/pa/{pa_id}", {"per_page": 200})
            interacoes_pa = data.get("interacoes", [])
            await self._cache_set(cache_key, interacoes_pa, TTL_INTERACOES)
        return interacoes_pa

    async def checar_interacoes(self, nomes_genericos: list[str]) -> dict:
        """
        Recebe nomes genéricos (já normalizados pelo extrator).
        Fluxo: nome → pa_id → /interacoes/pa/{id} filtrando pelos outros pa_ids.
        """
        if len(nomes_genericos) < 2:
            return {
                "status": "sem_interacao",
                "message": "É necessário informar pelo menos 2 medicamentos para checar interações.",
                "medicamentos_encontrados": [],
                "interacoes": [],
            }

        # 1. Resolver pa_ids (em paralelo: uma requisição por medicamento)
        pas = []
        nao_encontrados = []
        pa_results = await asyncio.gather(
            *(self.buscar_pa(nome) for nome in nomes_genericos),
            return_exceptions=True,
        )
        for nome, pa in zip(nomes_genericos, pa_results):
            if isinstance(pa, BaseException):
                logger.error(f"Erro ao resolver PA de '{nome}': {pa}")
                nao_encontrados.append(nome)
            elif pa:
                pas.append(pa)
            else:
                nao_encontrados.append(nome)

        if len(pas) < 2:
            return {
                "status": "insuficiente",
                "message": f"Encontrei apenas {len(pas)} fármaco(s) na base. Preciso de pelo menos 2.",
                "medicamentos_encontrados": [p["nome_dcb"] for p in pas],
                "nao_encontrados": nao_encontrados,
                "interacoes": [],
            }

        pa_ids = {p["pa_id"] for p in pas}

        # 2. Para cada PA, buscar interações e filtrar onde pa_b está no nosso conjunto
        interacoes_encontradas = []
        pares_vistos: set[tuple] = set()

        # Busca em paralelo; a deduplicação abaixo continua sequencial na ordem de `pas`
        # para manter o resultado determinístico.
        interacoes_por_pa = await asyncio.gather(
            *(self._interacoes_do_pa(pa["pa_id"]) for pa in pas),
            return_exceptions=True,
        )

        for pa, interacoes_pa in zip(pas, interacoes_por_pa):
            if isinstance(interacoes_pa, BaseException):
                logger.error(f"Erro ao buscar interações do PA {pa['pa_id']}: {interacoes_pa}")
                continue
            for interacao in interacoes_pa:
                pa_b_id = interacao.get("pa_b", {}).get("id")
                if pa_b_id not in pa_ids or pa_b_id == pa["pa_id"]:
                    continue
                par = tuple(sorted([pa["pa_id"], pa_b_id]))
                if par in pares_vistos:
                    continue
                pares_vistos.add(par)
                interacoes_encontradas.append(interacao)

        # 3. Montar alertas com semáforo
        alertas = []
        for interacao in interacoes_encontradas:
            gravidade = interacao.get("gravidade", "leve")
            semaforo = SEMAFORO.get(gravidade, SEMAFORO["leve"])
            refs = interacao.get("referencias", [])
            alertas.append({
                "pa_a": interacao.get("pa_a", {}).get("nome_dcb", ""),
                "pa_b": interacao.get("pa_b", {}).get("nome_dcb", ""),
                "gravidade": gravidade,
                "semaforo_level": semaforo["level"],
                "semaforo_color": semaforo["color"],
                "semaforo_emoji": semaforo["emoji"],
                "tipo_interacao": interacao.get("tipo_interacao", ""),
                "efeito_clinico": interacao.get("efeito_clinico", ""),
                "mecanismo": interacao.get("mecanismo", ""),
                "manejo_clinico": interacao.get("manejo_clinico", ""),
                "descricao_estendida": interacao.get("descricao_estendida_pt", ""),
                "referencias": refs,
            })

        alertas.sort(key=lambda x: x["semaforo_level"], reverse=True)

        if not alertas:
            return {
                "status": "sem_interacao",
                "message": "Nenhuma interação conhecida encontrada entre os fármacos informados.",
                "medicamentos_encontrados": [p["nome_dcb"] for p in pas],
                "nao_encontrados": nao_encontrados,
                "interacoes": [],
            }

        return {
            "status": "interacoes_encontradas",
            "total_interacoes": len(alertas),
            "medicamentos_encontrados": [p["nome_dcb"] for p in pas],
            "nao_encontrados": nao_encontrados,
            "interacoes": alertas,
        }

    # ── Bulas ─────────────────────────────────────────────────────────────────

    async def buscar_bula(self, nome: str) -> dict | None:
        """
        Busca bula de um produto por nome (comercial ou genérico).
        Sempre prioriza bula de profissional. Se não existir, retorna None
        (não usa bula de paciente — app médico).
        """
        cache_key = f"pharmadb:bula:nome:{nome.lower().strip()}"
        cached = await self._cache_get(cache_key)
        if cached:
            return cached

        try:
            data = await self._get("/v1/bulas/busca", {"q": nome, "per_page": 100})
            items = data.get("items", [])
            if not items:
                return None

            bula_profissional = next((i for i in items if i.get("tipo") == "profissional"), None)
            bula_item = bula_profissional or items[0]
            apenas_paciente = bula_profissional is None
            if apenas_paciente:
                logger.info(f"Bula profissional não disponível para '{nome}' — usando bula de paciente")

            bula = await self._get(f"/v1/bulas/{bula_item['id']}")

            result = {
                "bula_id": bula["id"],
                "tipo": bula["tipo"],
                "apenas_paciente": apenas_paciente,
                "produto_nome": bula.get("produto", {}).get("nome", nome),
                "laboratorio": bula.get("produto", {}).get("laboratorio"),
                "principios_ativos": bula.get("produto", {}).get("principios_ativos", []),
                "indicacoes": bula.get("texto_indicacoes"),
                "contraindicacoes": bula.get("texto_contraindicacoes"),
                "posologia": bula.get("texto_posologia"),
                "reacoes_adversas": bula.get("texto_reacoes_adversas"),
                "interacoes_texto": bula.get("texto_interacoes"),
            }

            await self._cache_set(cache_key, result, TTL_BULA)
            return result
        except Exception as e:
            logger.error(f"Erro ao buscar bula '{nome}': {e}")
            return None

    # ── Receita / Dispensação ─────────────────────────────────────────────────

    async def buscar_receita(self, nome: str) -> dict | None:
        """
        Retorna regime de dispensação conforme Portaria 344/98.
        Busca produto pelo nome e chama /produtos/{id}/receita.
        """
        cache_key = f"pharmadb:receita:nome:{nome.lower().strip()}"
        cached = await self._cache_get(cache_key)
        if cached:
            return cached

        try:
            produto = await self.buscar_produto(nome)
            if not produto:
                return None

            receita = await self._get(f"/v1/produtos/{produto['produto_id']}/receita")
            result = {
                "produto_nome": receita.get("produto_nome", produto["nome"]),
                "tarja": receita.get("tarja"),
                "tipo": receita.get("tipo"),
                "cor_receita": receita.get("cor_receita"),
                "requer_receita": receita.get("requer_receita"),
                "retencao": receita.get("retencao"),
                "vias": receita.get("vias"),
                "validade_dias": receita.get("validade_dias"),
                "lista_controle": receita.get("lista_controle"),
                "base_legal": receita.get("base_legal"),
                "observacao": receita.get("observacao"),
            }
            await self._cache_set(cache_key, result, TTL_RECEITA)
            return result
        except Exception as e:
            logger.error(f"Erro ao buscar receita '{nome}': {e}")
            return None

    # ── Genéricos / Intercambiáveis ───────────────────────────────────────────

    async def buscar_genericos(self, nome: str) -> dict | None:
        """
        Lista genéricos e similares intercambiáveis com preço e % de economia.
        """
        cache_key = f"pharmadb:genericos:nome:{nome.lower().strip()}"
        cached = await self._cache_get(cache_key)
        if cached:
            return cached

        try:
            produto = await self.buscar_produto(nome)
            if not produto:
                return None

            data = await self._get(f"/v1/produtos/{produto['produto_id']}/genericos")
            result = {
                "produto_nome": data.get("produto_nome", produto["nome"]),
                "categoria_regulatoria": data.get("categoria_regulatoria"),
                "composicao_resumo": data.get("composicao_resumo", []),
                "pmc_referencia_centavos": data.get("pmc_referencia_centavos"),
                "total_genericos": data.get("total_genericos", 0),
                "total_similares": data.get("total_similares", 0),
                "genericos": data.get("genericos", []),
                "similares_intercambiaveis": data.get("similares_intercambiaveis", []),
            }
            await self._cache_set(cache_key, result, TTL_GENERICOS)
            return result
        except Exception as e:
            logger.error(f"Erro ao buscar genéricos de '{nome}': {e}")
            return None

    # ── Histórico de Comercialização ──────────────────────────────────────────

    async def get_historico_comercializacao(self, produto_id: int) -> dict | None:
        cache_key = f"pharmadb:historico:{produto_id}"
        cached = await self._cache_get(cache_key)
        if cached:
            return cached

        try:
            data = await self._get(f"/v1/produtos/{produto_id}/historico-comercializacao")
            await self._cache_set(cache_key, data, TTL_PRODUTO)
            return data
        except Exception as e:
            logger.error(f"Erro ao buscar histórico do produto {produto_id}: {e}")
            return None

    async def mensagem_nao_encontrado(self, nome: str, contexto: str) -> str:
        """
        Tenta enriquecer a mensagem de "não encontrado" verificando se o produto
        existe na base mas foi descontinuado.
        contexto: 'bula' | 'receita' | 'generico'
        """
        produto = await self.buscar_produto(nome)
        if not produto:
            return f"⚠️ **{nome}** não encontrado na base PharmaDB. Verifique o nome do medicamento."

        historico = await self.get_historico_comercializacao(produto["produto_id"])
        if not historico:
            return f"⚠️ {contexto.capitalize()} de **{produto['nome']}** não disponível na base PharmaDB."

        if not historico.get("atualmente_comercializado", True):
            primeira = historico.get("primeira_deteccao_em", "")
            ultima = historico.get("ultima_deteccao_em", "")
            msg = f"⚠️ **{produto['nome']}** foi descontinuado e não está sendo comercializado."
            if ultima:
                msg += f" Última detecção na base: {ultima}."
            if primeira:
                msg += f" Registrado desde: {primeira}."
            return msg

        return f"⚠️ {contexto.capitalize()} de **{produto['nome']}** não disponível na base PharmaDB."

    # ── Formatadores ──────────────────────────────────────────────────────────

    def formatar_interacoes(self, resultado: dict) -> str:
        if resultado["status"] == "sem_interacao":
            meds = ", ".join(resultado.get("medicamentos_encontrados", []))
            return f"🟢 Nenhuma interação conhecida encontrada entre os fármacos informados ({meds})."

        if resultado["status"] == "insuficiente":
            msg = resultado["message"]
            if resultado.get("nao_encontrados"):
                msg += f"\n\nNão encontrados na base: {', '.join(resultado['nao_encontrados'])}"
            return f"⚠️ {msg}"

        linhas = ["## Checagem Farmacológica\n"]
        meds = ", ".join(resultado["medicamentos_encontrados"])
        linhas.append(f"**Fármacos analisados:** {meds}\n")

        if resultado.get("nao_encontrados"):
            linhas.append(f"⚠️ Não encontrados na base: {', '.join(resultado['nao_encontrados'])}\n")

        linhas.append(f"**Total de interações:** {resultado['total_interacoes']}\n")
        linhas.append("---\n")

        for alerta in resultado["interacoes"]:
            emoji = alerta["semaforo_emoji"]
            grav = alerta["gravidade"].upper()
            linhas.append(f"### {emoji} {alerta['pa_a']} ↔ {alerta['pa_b']} — **{grav}**\n")

            if alerta.get("tipo_interacao"):
                linhas.append(f"**Tipo:** {alerta['tipo_interacao']}\n")
            if alerta.get("efeito_clinico"):
                linhas.append(f"**Efeito clínico:** {alerta['efeito_clinico']}\n")
            if alerta.get("mecanismo"):
                linhas.append(f"**Mecanismo:** {alerta['mecanismo']}\n")
            if alerta.get("manejo_clinico"):
                linhas.append(f"**Manejo clínico:** {alerta['manejo_clinico']}\n")
            if alerta.get("descricao_estendida"):
                linhas.append(f"**Detalhes:** {alerta['descricao_estendida']}\n")

            refs = alerta.get("referencias", [])
            if refs:
                linhas.append("**Referências:**")
                for ref in refs:
                    linhas.append(f"- [{ref.get('text', 'Link')}]({ref.get('url', '')})")

            linhas.append("")

        return "\n".join(linhas)

    async def formatar_bula(self, bula: dict) -> str:
        nome = bula["produto_nome"]
        lab = bula.get("laboratorio", "")
        pas = ", ".join(bula.get("principios_ativos", []))

        secoes_raw = {}
        for campo, titulo in [
            ("indicacoes", "Indicações"),
            ("contraindicacoes", "Contraindicações"),
            ("posologia", "Posologia"),
            ("reacoes_adversas", "Reações Adversas"),
            ("interacoes_texto", "Interações Medicamentosas"),
        ]:
            texto = bula.get(campo)
            if texto and texto.strip():
                secoes_raw[titulo] = texto.strip()

        if not secoes_raw:
            return f"## {nome}\n\n⚠️ Conteúdo da bula não disponível."

        # Limpar via LLM
        secoes_formatadas = await _limpar_secoes_bula(nome, secoes_raw)

        linhas = [f"## {nome}"]
        if lab:
            linhas.append(f"**Laboratório:** {lab}")
        if pas:
            linhas.append(f"**Princípios ativos:** {pas}")
        if bula.get("apenas_paciente"):
            linhas.append("> ⚠️ Bula de profissional não disponível na base — exibindo bula de paciente.")
        linhas.append("---")
        linhas.append(secoes_formatadas)

        return "\n\n".join(linhas)

    def formatar_receita(self, receita: dict) -> str:
        nome = receita.get("produto_nome", "Produto")
        linhas = [f"## Receituário — {nome}\n"]

        if not receita.get("requer_receita"):
            linhas.append("🟢 **Não requer receita médica** (venda livre).\n")
        else:
            cor = receita.get("cor_receita", "").capitalize()
            tipo = receita.get("tipo", "")
            linhas.append(f"📋 **Tipo de receita:** {tipo} ({cor})\n")

            if receita.get("retencao"):
                linhas.append("🔒 **Retenção de receita:** Sim\n")

            if receita.get("vias"):
                linhas.append(f"**Vias:** {receita['vias']}\n")

            if receita.get("validade_dias"):
                linhas.append(f"**Validade:** {receita['validade_dias']} dias\n")

            if receita.get("lista_controle"):
                linhas.append(f"**Lista de controle:** {receita['lista_controle']}\n")

        if receita.get("base_legal"):
            linhas.append(f"**Base legal:** {receita['base_legal']}\n")

        if receita.get("observacao"):
            linhas.append(f"\n> {receita['observacao']}\n")

        return "\n".join(linhas)

    def formatar_genericos(self, data: dict) -> str:
        nome = data.get("produto_nome", "Produto")
        linhas = [f"## Genéricos e Similares — {nome}\n"]

        pmc = data.get("pmc_referencia_centavos")
        if pmc:
            linhas.append(f"**Preço de referência (PMC):** R$ {pmc / 100:.2f}\n")

        composicao = data.get("composicao_resumo", [])
        if composicao:
            linhas.append(f"**Composição:** {', '.join(composicao)}\n")

        genericos = data.get("genericos", [])
        similares = data.get("similares_intercambiaveis", [])

        if not genericos and not similares:
            linhas.append("\n⚠️ Nenhum genérico ou similar intercambiável encontrado na base.\n")
            return "\n".join(linhas)

        if genericos:
            linhas.append(f"\n### Genéricos ({len(genericos)})\n")
            for g in genericos[:10]:
                preco = f"R$ {g['pmc_centavos'] / 100:.2f}" if g.get("pmc_centavos") else "—"
                economia = f" *(economia de {g['economia_pct']:.0f}%)*" if g.get("economia_pct") else ""
                linhas.append(f"- **{g['nome']}** ({g.get('laboratorio', '—')}) — {preco}{economia}")

        if similares:
            linhas.append(f"\n### Similares intercambiáveis ({len(similares)})\n")
            for s in similares[:10]:
                preco = f"R$ {s['pmc_centavos'] / 100:.2f}" if s.get("pmc_centavos") else "—"
                economia = f" *(economia de {s['economia_pct']:.0f}%)*" if s.get("economia_pct") else ""
                linhas.append(f"- **{s['nome']}** ({s.get('laboratorio', '—')}) — {preco}{economia}")

        return "\n".join(linhas)


# ── Singleton ────────────────────────────────────────────────────────────────

_pharmadb = PharmaDBService()


def get_pharmadb_service() -> PharmaDBService:
    return _pharmadb
