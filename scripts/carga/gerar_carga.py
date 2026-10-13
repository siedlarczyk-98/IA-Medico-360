"""
Gerador de carga do Médico 360 — imita médicos entrando pela Waid e perguntando.

Cada médico é uma corrotina com o PRÓPRIO cliente HTTP (conexões e cookies
próprios, como navegadores diferentes) e faz o que o front faz:

  1. `POST /auth/embed/token` com um token de identidade da Waid. No 429 espera
     2/5/10 s + sorteio de até 1 s e repete com o MESMO token — é o
     `comEsperaNoLimite` de `shared/embed/identidade.ts`.
  2. Onboarding, se a conta é nova (`GET /meta/especialidades` + `POST /auth/onboarding`).
  3. A tela inicial do chat: `/auth/me`, `/conversations`, `/folders`, `/users/usage`
     em paralelo.
  4. Perguntas em `POST /orquestrador/stream`, lendo o SSE até `done`/`error`.

O token de identidade só é aceito pelo servidor falso (`falso_externo.py`), que
faz o papel da Waid. Contra produção este script NÃO funciona como está — lá o
login precisa de outro caminho (etapa B do `LEIAME.md`).

Cenários:
  rajada    todos entram numa janela curta e não perguntam ("abram o app agora")
  onda      todos entram e cada um faz 1 pergunta (30% fazem uma segunda) numa
            janela — a demonstração ao vivo
  continuo  cada médico pergunta, "lê" 30-90 s e pergunta de novo, até a duração

Uso:
  python -m scripts.carga.gerar_carga --cenario onda --medicos 100
  python -m scripts.carga.gerar_carga --cenario rajada --medicos 300 --janela-login 60
"""

import argparse
import asyncio
import json
import random
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

import httpx

# Mistura de modos medida em produção (107 QUICK, 66 PHARMA, 35 CLINICAL, 8 EXAM).
MIX_MODOS = [("QUICK_SEARCH", 0.50), ("PHARMA_CHECK", 0.30), ("CLINICAL_REASONING", 0.16), ("EXAM_REVIEW", 0.04)]

PERGUNTAS = {
    "QUICK_SEARCH": [
        "Qual a dose de amoxicilina para otite média aguda em adulto?",
        "Critérios diagnósticos de sepse segundo Sepsis-3",
        "Meta de LDL em paciente de muito alto risco cardiovascular",
        "Tratamento de primeira linha para hipertensão estágio 1",
        "Quando indicar anticoagulação na fibrilação atrial?",
        "Esquema de insulina basal-bolus para diabetes tipo 2",
    ],
    "PHARMA_CHECK": [
        "Interação entre varfarina e amiodarona",
        "Bula da losartana",
        "Receita da dipirona",
        "Tem genérico do enalapril?",
        "Posso associar losartana com espironolactona?",
    ],
    "CLINICAL_REASONING": [
        "Homem de 58 anos, hipertenso e diabético, com dispneia progressiva há 3 semanas, "
        "edema de membros inferiores e ortopneia. Ecocardiograma com FE de 35%. Como conduzir?",
        "Mulher de 34 anos com febre há 5 dias, artralgia e rash maculopapular após viagem ao Nordeste. "
        "Plaquetas 95 mil. Diagnósticos diferenciais e conduta inicial?",
    ],
    "EXAM_REVIEW": [
        "Hemograma: Hb 9,2, VCM 72, RDW 17, ferritina 8. Como interpretar e tratar?",
    ],
}


@dataclass
class Registro:
    medico: int
    etapa: str
    inicio: float          # segundos desde o começo da rodada
    dur_ms: float
    status: int | None     # HTTP; None = exceção antes da resposta
    erro: str | None = None
    extra: dict = field(default_factory=dict)


class Rodada:
    def __init__(self, args):
        self.args = args
        self.t0 = time.monotonic()
        self.registros: list[Registro] = []
        self.streams_abertos = 0
        self.linha_do_tempo: list[tuple[float, int]] = []

    def agora(self) -> float:
        return time.monotonic() - self.t0

    def registra(self, r: Registro) -> None:
        self.registros.append(r)

    def stream_abriu(self) -> None:
        self.streams_abertos += 1
        self.linha_do_tempo.append((self.agora(), self.streams_abertos))

    def stream_fechou(self) -> None:
        self.streams_abertos -= 1
        self.linha_do_tempo.append((self.agora(), self.streams_abertos))


def _sorteia_modo() -> str:
    r = random.random()
    acumulado = 0.0
    for modo, peso in MIX_MODOS:
        acumulado += peso
        if r < acumulado:
            return modo
    return MIX_MODOS[0][0]


class Medico:
    def __init__(self, n: int, rodada: Rodada, ip: str):
        self.n = n
        self.rodada = rodada
        self.args = rodada.args
        self.token: str | None = None
        self.conversa: str | None = None
        cabecalhos = {"Origin": self.args.origem, "User-Agent": "m360-carga/1"}
        if ip:
            # Local, o uvicorn confia no X-Forwarded-For (`--forwarded-allow-ips *`):
            # é assim que se simula "todos no mesmo Wi-Fi" ou "cada um no seu 4G".
            cabecalhos["X-Forwarded-For"] = ip
        self.http = httpx.AsyncClient(
            base_url=self.args.base,
            headers=cabecalhos,
            timeout=httpx.Timeout(30.0, read=90.0),
        )

    def _auth(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    async def _chama(self, etapa: str, metodo: str, url: str, **kw) -> httpx.Response | None:
        inicio = self.rodada.agora()
        t = time.monotonic()
        try:
            resp = await self.http.request(metodo, url, **kw)
        except httpx.HTTPError as e:
            self.rodada.registra(Registro(self.n, etapa, inicio, (time.monotonic() - t) * 1000, None,
                                          f"{type(e).__name__}: {e}"[:200]))
            return None
        erro = None if resp.status_code < 400 else resp.text[:200]
        self.rodada.registra(Registro(self.n, etapa, inicio, (time.monotonic() - t) * 1000,
                                      resp.status_code, erro))
        return resp

    async def entrar(self) -> bool:
        token_waid = f"carga-{self.n}-{uuid.uuid4().hex}"
        inicio_login = self.rodada.agora()
        t = time.monotonic()
        tentativas = 0
        resp = None
        for espera in (None, 2.0, 5.0, 10.0):
            if espera is not None:
                await asyncio.sleep(espera + random.random())
            tentativas += 1
            resp = await self._chama("login:tentativa", "POST", "/api/v1/auth/embed/token",
                                     json={"token": token_waid})
            if resp is None or resp.status_code != 429:
                break
        ok = resp is not None and resp.status_code == 200
        # O que o médico sente: do clique até entrar (ou desistir), somando esperas.
        self.rodada.registra(Registro(
            self.n, "login:total", inicio_login, (time.monotonic() - t) * 1000,
            resp.status_code if resp is not None else None,
            None if ok else "não entrou",
            {"tentativas": tentativas},
        ))
        if not ok:
            return False
        dados = resp.json()
        self.token = dados["access_token"]

        if not dados.get("onboarding_complete"):
            await self._chama("onboarding:especialidades", "GET", "/api/v1/meta/especialidades")
            r = await self._chama("onboarding:enviar", "POST", "/api/v1/auth/onboarding",
                                  headers=self._auth(),
                                  json={"med_status": "especialista", "terms_accepted": True})
            if r is None or r.status_code != 200:
                return False
            self.token = r.json()["access_token"]

        await asyncio.gather(
            self._chama("inicio:me", "GET", "/api/v1/auth/me", headers=self._auth()),
            self._chama("inicio:conversas", "GET", "/api/v1/conversations?page=1&page_size=100",
                        headers=self._auth()),
            self._chama("inicio:pastas", "GET", "/api/v1/folders", headers=self._auth()),
            self._chama("inicio:uso", "GET", "/api/v1/users/usage", headers=self._auth()),
        )
        return True

    async def perguntar(self) -> None:
        modo = _sorteia_modo()
        pergunta = random.choice(PERGUNTAS[modo])
        if random.random() < 0.5:
            # Metade das perguntas é única, metade repete o texto de outro médico
            # (o Redis cacheia triagem, especialidade e medicamentos por texto).
            pergunta += f" (caso {self.n}-{random.randint(1, 10_000)})"
        corpo = {"prompt": pergunta, "mode": modo, "effort": "detalhado"}
        if self.conversa:
            corpo["conversation_id"] = self.conversa

        etapa = f"stream:{modo}"
        inicio = self.rodada.agora()
        t = time.monotonic()
        marcos: dict[str, float] = {}
        evento_final = None
        status = None
        erro = None
        tokens = 0
        self.rodada.stream_abriu()
        try:
            async with self.http.stream("POST", "/api/v1/orquestrador/stream", json=corpo,
                                        headers=self._auth(),
                                        timeout=httpx.Timeout(30.0, read=120.0)) as resp:
                status = resp.status_code
                marcos["cabecalho"] = (time.monotonic() - t) * 1000
                if status != 200:
                    erro = (await resp.aread()).decode(errors="replace")[:200]
                else:
                    evento = None
                    async for linha in resp.aiter_lines():
                        if linha.startswith("event: "):
                            evento = linha[7:].strip()
                            if evento == "token":
                                tokens += 1
                                marcos.setdefault("primeiro_token", (time.monotonic() - t) * 1000)
                            elif evento in ("text_done", "start", "cache_hit"):
                                marcos.setdefault(evento, (time.monotonic() - t) * 1000)
                            elif evento in ("done", "error", "clarification"):
                                evento_final = evento
                        elif linha.startswith("data: ") and evento in ("done", "error", "clarification", "cache_hit"):
                            try:
                                dados = json.loads(linha[6:])
                            except ValueError:
                                dados = {}
                            if evento == "error":
                                erro = str(dados.get("message") or dados.get("status"))[:200]
                            elif evento == "cache_hit":
                                evento_final = "cache_hit"
                            if dados.get("conversation_id"):
                                self.conversa = dados["conversation_id"]
                            if evento in ("done", "error", "clarification", "cache_hit"):
                                break
        except httpx.HTTPError as e:
            erro = f"{type(e).__name__}: {e}"[:200]
        finally:
            self.rodada.stream_fechou()
        if evento_final is None and erro is None:
            erro = "stream terminou sem done/error"
        self.rodada.registra(Registro(
            self.n, etapa, inicio, (time.monotonic() - t) * 1000, status, erro,
            {"final": evento_final, "tokens": tokens, **{k: round(v) for k, v in marcos.items()}},
        ))

    async def fechar(self) -> None:
        await self.http.aclose()


async def _um_medico(n: int, rodada: Rodada, ip: str) -> None:
    a = rodada.args
    await asyncio.sleep(random.uniform(0, a.janela_login))
    m = Medico(n, rodada, ip)
    try:
        if not await m.entrar():
            return
        if a.cenario == "rajada":
            return
        if a.cenario == "onda":
            # A pergunta cai dentro da janela, contada a partir do FIM do login.
            await asyncio.sleep(random.uniform(0, a.janela_perguntas))
            await m.perguntar()
            if random.random() < 0.30:
                await asyncio.sleep(random.uniform(20, 40))
                await m.perguntar()
            return
        # continuo
        fim = rodada.t0 + a.janela_login + a.duracao
        await asyncio.sleep(random.uniform(0, 30))
        while time.monotonic() < fim:
            await m.perguntar()
            await asyncio.sleep(random.uniform(30, 90))
    finally:
        await m.fechar()


def _pct(valores: list[float], p: float) -> float:
    if not valores:
        return float("nan")
    v = sorted(valores)
    k = min(len(v) - 1, max(0, round(p / 100 * (len(v) - 1))))
    return v[k]


def resumo(rodada: Rodada) -> dict:
    por_etapa: dict[str, list[Registro]] = {}
    for r in rodada.registros:
        por_etapa.setdefault(r.etapa, []).append(r)

    saida: dict = {"etapas": {}, "pico_streams_abertos": max((n for _, n in rodada.linha_do_tempo), default=0)}
    for etapa, regs in sorted(por_etapa.items()):
        durs = [r.dur_ms for r in regs]
        status: dict[str, int] = {}
        for r in regs:
            chave = str(r.status) if r.status is not None else "exceção"
            if etapa.startswith("stream:") and r.status == 200:
                chave = f"200/{r.extra.get('final') or 'sem_final'}"
            status[chave] = status.get(chave, 0) + 1
        info = {
            "n": len(regs),
            "status": status,
            "p50_ms": round(_pct(durs, 50)), "p95_ms": round(_pct(durs, 95)),
            "p99_ms": round(_pct(durs, 99)), "max_ms": round(max(durs)),
            "erros_exemplo": sorted({r.erro for r in regs if r.erro})[:5],
        }
        if etapa.startswith("stream:"):
            for marco in ("cabecalho", "start", "primeiro_token", "text_done"):
                vals = [r.extra[marco] for r in regs if marco in r.extra]
                if vals:
                    info[f"{marco}_p50_ms"] = round(_pct(vals, 50))
                    info[f"{marco}_p95_ms"] = round(_pct(vals, 95))
        if etapa == "login:total":
            tent = [r.extra.get("tentativas", 1) for r in regs]
            info["com_429"] = sum(1 for x in tent if x > 1)
            info["tentativas_max"] = max(tent)
        saida["etapas"][etapa] = info
    return saida


def imprime(res: dict) -> None:
    print(f"\npico de streams abertos: {res['pico_streams_abertos']}\n")
    print(f"{'etapa':32} {'n':>5} {'p50':>8} {'p95':>8} {'p99':>8} {'max':>8}  status")
    for etapa, i in res["etapas"].items():
        print(f"{etapa:32} {i['n']:>5} {i['p50_ms']:>8} {i['p95_ms']:>8} {i['p99_ms']:>8} {i['max_ms']:>8}  {i['status']}")
        extras = {k: v for k, v in i.items() if k.endswith("_ms") and k.split("_")[0] in
                  ("cabecalho", "start", "primeiro", "text")}
        if extras:
            print(f"{'':32} {extras}")
        if i.get("com_429"):
            print(f"{'':32} médicos que levaram 429: {i['com_429']} (máx. {i['tentativas_max']} tentativas)")
        for e in i["erros_exemplo"]:
            print(f"{'':32} ! {e}")


async def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--base", default="http://localhost:8010")
    p.add_argument("--origem", default="https://www.medico360.app")
    p.add_argument("--cenario", choices=["rajada", "onda", "continuo"], required=True)
    p.add_argument("--medicos", type=int, default=50)
    p.add_argument("--primeiro-id", type=int, default=1,
                   help="id do primeiro médico; repetir ids = contas que já existem")
    p.add_argument("--janela-login", type=float, default=60.0, help="segundos em que os logins se espalham")
    p.add_argument("--janela-perguntas", type=float, default=180.0)
    p.add_argument("--duracao", type=float, default=1800.0, help="cenário continuo, em segundos")
    p.add_argument("--ips", type=int, default=1, help="quantos IPs distintos (1 = todos no mesmo Wi-Fi)")
    p.add_argument("--saida", default="scripts/carga/resultados")
    a = p.parse_args()

    rodada = Rodada(a)
    ips = [f"10.77.{i // 250}.{i % 250 + 1}" for i in range(max(a.ips, 1))]
    print(f"[carga] {a.cenario}: {a.medicos} médicos a partir do id {a.primeiro_id}, "
          f"{len(ips)} IP(s), login em {a.janela_login:.0f}s -> {a.base}")

    async def progresso():
        while True:
            await asyncio.sleep(10)
            regs = rodada.registros
            falhas = sum(1 for r in regs if r.status is None or (r.status >= 400 and r.status != 429)
                         or (r.etapa.startswith("stream:") and r.erro))
            print(f"[carga] t={rodada.agora():5.0f}s  registros={len(regs):5}  "
                  f"streams abertos={rodada.streams_abertos:4}  falhas={falhas}")

    vigia = asyncio.create_task(progresso())
    await asyncio.gather(*(
        _um_medico(a.primeiro_id + i, rodada, ips[i % len(ips)]) for i in range(a.medicos)
    ))
    vigia.cancel()

    res = resumo(rodada)
    res["parametros"] = vars(a)
    res["duracao_s"] = round(rodada.agora())
    imprime(res)

    pasta = Path(a.saida)
    pasta.mkdir(parents=True, exist_ok=True)
    carimbo = datetime.now().strftime("%Y%m%d-%H%M%S")
    nome = f"{carimbo}-{a.cenario}-{a.medicos}"
    (pasta / f"{nome}-resumo.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    with (pasta / f"{nome}-registros.jsonl").open("w", encoding="utf-8") as f:
        for r in rodada.registros:
            f.write(json.dumps(asdict(r), ensure_ascii=False) + "\n")
    (pasta / f"{nome}-streams.json").write_text(json.dumps(rodada.linha_do_tempo), encoding="utf-8")
    print(f"\n[carga] resultados em {pasta / nome}-*")


if __name__ == "__main__":
    asyncio.run(main())
