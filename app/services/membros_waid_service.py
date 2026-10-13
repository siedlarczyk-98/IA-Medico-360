"""
Cópia diária dos membros da Waid com acesso ao Médico 360 (`membros_waid`).

POR QUE EXISTE
`users` só ganha linha quando a pessoa abre o app de IA. Quem entrou pela Waid
e nunca abriu — o comprador de curso presencial que só fez o pré-curso, por
exemplo — tem acesso ao Médico 360 e não existia em número nenhum do painel.
A diretoria conta essas pessoas como "com acesso" (Ruben, 2026-10-13).

QUEM ENTRA
Só membros dos grupos `[CFM]` e `[Cursos Active]` (app/medicina/canal.py).
Força de vendas e áreas de laboratório, que dividem a mesma Waid, ficam fora —
e, por minimização, nem são baixadas.

COMO
`GET /groups?search=` acha os grupos que contam; `GET /groups/{id}/members`
traz quem está em cada um hoje. Uma linha por pessoa (`waid_uuid`), com todos
os grupos dela. Quem estava na tabela e não apareceu nesta rodada perdeu o
acesso: `tem_acesso = false`, e a linha fica.

QUEM RODA
O processo líder (`app/core/lider.py`), uma vez por dia, como o expurgo.
Idempotente: rodar duas vezes seguidas dá o mesmo resultado.
"""

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert

from app.core.alarme import alarmar
from app.core.database import async_session_factory
from app.medicina import canal
from app.models.models import AuditLog, MembroWaid
from app.services.integracoes import curseduca_service

logger = logging.getLogger(__name__)

ACAO_SINCRONIZACAO = "membros_waid.sincronizacao"

INTERVALO_HORAS = 24
ATRASO_INICIAL_SEGUNDOS = 180

# O que se pede à busca por nome da Waid; o filtro de verdade é o prefixo, em
# `canal`, porque a busca pode casar "CFM" no meio de outro nome.
_BUSCAS = ("CFM", "Cursos Active")


class NenhumGrupoEncontrado(Exception):
    """A busca não achou grupo nenhum: algo mudou na Waid, não "todos saíram"."""


def _data(valor) -> datetime | None:
    if not isinstance(valor, str) or not valor:
        return None
    try:
        data = datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except ValueError:
        return None
    return data if data.tzinfo else data.replace(tzinfo=UTC)


async def coletar() -> dict[str, dict]:
    """Baixa os membros dos grupos que contam. Uma entrada por `waid_uuid`."""
    grupos: dict = {}
    for busca in _BUSCAS:
        for g in await curseduca_service.listar_grupos(busca):
            nome = g.get("name")
            if g.get("id") is not None and (canal.e_grupo_cfm(nome) or canal.e_grupo_cursos_active(nome)):
                grupos[g["id"]] = nome
    if not grupos:
        raise NenhumGrupoEncontrado("Nenhum grupo [CFM] ou [Cursos Active] na Waid")

    membros: dict[str, dict] = {}
    for grupo_id, nome_grupo in grupos.items():
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
            "canal_entrada": canal.canal_de_entrada(grupos),
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
    resultado = {"com_acesso": len(membros), "perderam_acesso": saiu.rowcount or 0}
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
        try:
            await _uma_rodada()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            # Falhar aqui só deixa o painel com a cópia de ontem. Não pode matar
            # o laço, senão o painel congela em silêncio — e vai ao Sentry, porque
            # a causa mais provável (credencial sem permissão para listar grupos,
            # 403) não se resolve sozinha.
            logger.exception("Sincronização de membros da Waid falhou; tenta no próximo ciclo: %s", exc)
            alarmar(
                tag="membros_waid",
                mensagem=f"Sincronização de membros da Waid falhou: {exc}"[:300],
            )
        await asyncio.sleep(INTERVALO_HORAS * 3600)


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
