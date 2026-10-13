"""
Lê o limite de taxa do NOSSO plano em cada provedor, modelo por modelo.

POR QUE EXISTE
O limite de taxa é por modelo: 100 médicos passando bem no Haiku não dizem nada
sobre o `claude-sonnet-5`. Mas a Anthropic e a OpenAI devolvem o limite do plano
nos cabeçalhos de TODA resposta, então uma requisição mínima por modelo responde
a pergunta sem carga nenhuma. Custa frações de centavo.

Usa as chaves do `.env` da raiz. Não imprime chave nenhuma.

Uso: python -m scripts.carga.limites_provedores
"""

import asyncio

import httpx
from dotenv import dotenv_values

CHAVES = dotenv_values(".env")

ALVOS = [
    # (provedor, modelo, url, cabeçalhos, corpo)
    *(("anthropic", m, "https://api.anthropic.com/v1/messages",
       {"x-api-key": CHAVES.get("ANTHROPIC_API_KEY", ""), "anthropic-version": "2023-06-01"},
       {"model": m, "max_tokens": 1, "messages": [{"role": "user", "content": "oi"}]})
      for m in ("claude-sonnet-5", "claude-haiku-4-5")),
    *(("openai", m, "https://api.openai.com/v1/chat/completions",
       {"Authorization": f"Bearer {CHAVES.get('OPENAI_API_KEY', '')}"},
       {"model": m, "max_completion_tokens": 16, "messages": [{"role": "user", "content": "oi"}]})
      for m in ("gpt-5.4-nano", "gpt-5.4-mini", "gpt-4o")),
    *(("perplexity", m, "https://api.perplexity.ai/chat/completions",
       {"Authorization": f"Bearer {CHAVES.get('PERPLEXITY_API_KEY', '')}"},
       {"model": m, "max_tokens": 16, "messages": [{"role": "user", "content": "oi"}]})
      for m in ("sonar-pro", "sonar")),
]


async def consulta(cliente, provedor, modelo, url, cabecalhos, corpo):
    try:
        r = await cliente.post(url, headers=cabecalhos, json=corpo)
    except httpx.HTTPError as e:
        return f"{provedor:10} {modelo:18} falhou: {type(e).__name__}"
    limites = {k: v for k, v in r.headers.items() if "ratelimit" in k.lower() or "rate-limit" in k.lower()}
    linhas = [f"{provedor:10} {modelo:18} HTTP {r.status_code}"]
    if r.status_code >= 400:
        linhas.append(f"{'':30}{r.text[:160]}")
    if not limites:
        linhas.append(f"{'':30}(nenhum cabeçalho de limite — conferir no painel)")
    for k, v in sorted(limites.items()):
        if "reset" in k:
            continue
        linhas.append(f"{'':30}{k}: {v}")
    return "\n".join(linhas)


async def main():
    async with httpx.AsyncClient(timeout=30) as cliente:
        for resultado in await asyncio.gather(*(consulta(cliente, *a) for a in ALVOS)):
            print(resultado)


if __name__ == "__main__":
    asyncio.run(main())
