"""
Cópia diária dos membros da Waid que contam como usuários do Médico 360 (`membros_waid`).

POR QUE EXISTE
`users` só ganha linha quando a pessoa abre o app de IA. Quem entrou pela Waid
e nunca abriu — o comprador de curso presencial que só fez o pré-curso, por
exemplo — tem acesso ao Médico 360 e não existia em número nenhum do painel.

QUEM CONTA (regras do Ruben, 2026-10-13; a leitura está em app/medicina/canal.py)
Só quem está num grupo `[Cursos Active]`, `[CFM]` ou `[ONBOARDING]`. Quem não está
em nenhum deles não conta nunca — nem se abrir a IA. O canal:
  - `[Cursos Active]`                                   -> Cursos Active
  - `[CFM]`/`[ONBOARDING]` sem andar de farmacêutica      -> LP do Médico 360
  - `[CFM]`/`[ONBOARDING]` com andar de farmacêutica      -> Usuário Immerso

COMO
1. `GET /reports/groups` traz todos os grupos, com os andares (`tenants`) que
   cada um libera e quantos membros tem. Grupo vazio é pulado.
2. `GET /groups/{id}/members` dos grupos que contam: quem são.
3. Dos grupos que liberam andar de farmacêutica, só se guarda QUEM está neles
   (o uuid), para marcar o "Usuário Immerso". Nada dessas pessoas é gravado.
4. Uma linha por pessoa em `membros_waid`; quem sumiu vira `tem_acesso = false`.
5. O canal é copiado para `users.canal_entrada` de quem tem conta, para ficar
   visível no banco também.

Rodada que falha não grava nada: com uma lista parcial, quem estava no grupo
que falhou seria marcado como "perdeu o acesso". O laço tenta de novo em 1 hora.

QUEM RODA
O processo líder (`app/core/lider.py`). Idempotente.
"""

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import func, or_, update
from sqlalchemy.dialects.postgresql import insert

from app.core.alarme import alarmar
from app.core.database import async_session_factory
from app.medicina import canal
from app.models.models import AuditLog, MembroWaid, User
from app.services.integracoes import curseduca_service

logger = logging.getLogger(__name__)

ACAO_SINCRONIZACAO = "membros_waid.sincronizacao"

INTERVALO_HORAS = 24
INTERVALO_APOS_FALHA_HORAS = 1
ATRASO_INICIAL_SEGUNDOS = 180


class NenhumGrupoEncontrado(Exception):
    """O relatório não trouxe grupo que conta: algo mudou na Waid, não "todos saíram"."""


def _data(valor) -> datetime | None:
    if not isinstance(valor, str) or not valor:
        return None
    try:
        data = datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except ValueError:
        return None
    return data if data.tzinfo else data.replace(tzinfo=UTC)


def _vazio(grupo: dict) -> bool:
    """Só pula quando a Waid DIZ que está vazio; contagem ausente não é zero."""
    return grupo.get("membersCount") == 0


def _libera_andar_de_farmaceutica(grupo: dict) -> bool:
    andares = grupo.get("tenants")
    return isinstance(andares, list) and any(canal.e_andar_de_farmaceutica(a) for a in andares)


async def coletar() -> dict[str, dict]:
    """Baixa quem conta como usuário. Uma entrada por `waid_uuid`."""
    relatorio = await curseduca_service.listar_relatorio_de_grupos()
    que_contam = {
        g["id"]: g["name"] for g in relatorio
        if g.get("id") is not None and canal.e_grupo_que_conta(g.get("name"))
    }
    if not que_contam:
        raise NenhumGrupoEncontrado("Nenhum grupo [Cursos Active], [CFM] ou [ONBOARDING] na Waid")
    de_farmaceutica = [
        g["id"] for g in relatorio
        if g.get("id") is not None and _libera_andar_de_farmaceutica(g) and not _vazio(g)
    ]
    vazios = {g["id"] for g in relatorio if _vazio(g)}

    membros: dict[str, dict] = {}
    for grupo_id, nome_grupo in que_contam.items():
        if grupo_id in vazios:
            continue
        for m in await curseduca_service.listar_membros_do_grupo(grupo_id):
            uuid = m.get("uuid")
            # `hasAccess` falso = vínculo vencido: está no grupo, mas sem acesso.
            if not uuid or m.get("hasAccess") is False:
                continue
            reg = membros.setdefault(str(uuid), {
                "waid_id": m.get("id"),
                "email": m.get("email"),
                "nome": m.get("name"),
                "grupos": set(),
                "entrou_em": None,
            })
            reg["grupos"].add(nome_grupo)
            entrada = _data(m.get("enteredAt"))
            if entrada and (reg["entrou_em"] is None or entrada < reg["entrou_em"]):
                reg["entrou_em"] = entrada

    em_farmaceutica: set[str] = set()
    for grupo_id in de_farmaceutica:
        for m in await curseduca_service.listar_membros_do_grupo(grupo_id):
            if m.get("uuid") and m.get("hasAccess") is not False:
                em_farmaceutica.add(str(m["uuid"]))

    for uuid, reg in membros.items():
        reg["em_andar_de_farmaceutica"] = uuid in em_farmaceutica
    return membros


async def sincronizar(db, membros: dict[str, dict]) -> dict:
    """Grava a rodada. Separado de `coletar` para o teste não depender de rede."""
    agora = datetime.now(UTC)
    for waid_uuid, reg in membros.items():
        grupos = sorted(reg["grupos"])
        valores = {
            "waid_id": reg["waid_id"] if isinstance(reg["waid_id"], int) else None,
            "email": reg["email"],
            "nome": reg["nome"],
            "grupos": grupos,
            "canal_entrada": canal.canal_de_entrada(
                grupos, em_andar_de_farmaceutica=reg.get("em_andar_de_farmaceutica", False)
            ),
            "profissao": canal.profissao(grupos),
            "entrou_em": reg["entrou_em"],
            "tem_acesso": True,
            "sincronizado_em": agora,
        }
        await db.execute(
            insert(MembroWaid)
            .values(waid_uuid=waid_uuid, **valores)
            .on_conflict_do_update(index_elements=[MembroWaid.waid_uuid], set_=valores)
        )

    saiu = await db.execute(
        update(MembroWaid)
        .where(MembroWaid.tem_acesso.is_(True), MembroWaid.sincronizado_em < agora)
        .values(tem_acesso=False)
    )

    # O canal fica visível também na conta do app. Liga pelo id da Waid ou, para
    # a conta criada por login direto (sem id da Waid), pelo e-mail.
    contas = await db.execute(
        update(User)
        .where(
            MembroWaid.tem_acesso.is_(True),
            or_(
                User.waid_uuid == MembroWaid.waid_uuid,
                (User.waid_uuid.is_(None)) & (func.lower(User.email) == func.lower(MembroWaid.email)),
            ),
            User.canal_entrada.is_distinct_from(MembroWaid.canal_entrada),
        )
        .values(canal_entrada=MembroWaid.canal_entrada)
        .execution_options(synchronize_session=False)
    )

    resultado = {
        "com_acesso": len(membros),
        "perderam_acesso": saiu.rowcount or 0,
        "contas_com_canal_atualizado": contas.rowcount or 0,
    }
    db.add(AuditLog(action=ACAO_SINCRONIZACAO, entity_type="membros_waid", metadata_=resultado))
    await db.commit()
    return resultado


async def _uma_rodada() -> None:
    membros = await coletar()
    async with async_session_factory() as db:
        resultado = await sincronizar(db, membros)
    logger.info("Membros da Waid sincronizados", extra=resultado)


async def _laco() -> None:
    await asyncio.sleep(ATRASO_INICIAL_SEGUNDOS)
    while True:
        espera_horas = INTERVALO_HORAS
        try:
            await _uma_rodada()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            # Falhar aqui só deixa o painel com a cópia anterior. Não pode matar
            # o laço, senão o painel congela em silêncio — e vai ao Sentry, porque
            # credencial sem permissão (403) não se resolve sozinha.
            logger.exception("Sincronização de membros da Waid falhou; tenta de novo em 1h: %s", exc)
            alarmar(
                tag="membros_waid",
                mensagem=f"Sincronização de membros da Waid falhou: {exc!r}"[:300],
            )
            espera_horas = INTERVALO_APOS_FALHA_HORAS
        await asyncio.sleep(espera_horas * 3600)


def iniciar() -> asyncio.Task:
    """Dispara o laço em background. Chamado no lifespan, só no processo líder."""
    logger.info(
        "Sincronização de membros da Waid ativa (a cada %dh, primeira em %ds)",
        INTERVALO_HORAS, ATRASO_INICIAL_SEGUNDOS,
    )
    return asyncio.create_task(_laco(), name="membros-waid")


async def parar(tarefa: asyncio.Task | None) -> None:
    if tarefa is None or tarefa.done():
        return
    tarefa.cancel()
    try:
        await tarefa
    except asyncio.CancelledError:
        pass

