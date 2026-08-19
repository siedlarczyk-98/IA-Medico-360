"""
Ensaio de restore: o banco restaurado bate com o de origem?

NAO ESCREVE NADA. So faz SELECT (contagem, max(created_at), alembic_version) nos
dois bancos. Pode ser apontado para producao como ORIGEM sem risco de alteracao.

Roda na SUA MAQUINA, nao dentro do Railway - as duas URLs saem de
Railway > Postgres > Connect (ou da aba Variables, DATABASE_PUBLIC_URL):

    python -m scripts.verificar_restore --origem "postgresql://..." --restaurado "postgresql://..."

Ou, para nao deixar credencial no historico do shell:

    $env:RESTORE_ORIGEM = "postgresql://..."
    $env:RESTORE_DESTINO = "postgresql://..."
    python -m scripts.verificar_restore

Por que existe: o runbook mandava conferir `users`, `conversations` e
`interactions` - 3 de 25 tabelas. Um restore pode trazer essas tres intactas e
ter perdido `consent_logs` ou `audit_logs`, que existem por obrigacao
regulatoria. Aqui a comparacao e de TODAS as tabelas, e quem decide a lista e o
proprio banco de origem, nao uma lista escrita a mao que envelhece.

Sai com codigo 1 se houver qualquer divergencia, para poder rodar sem leitura
humana (num agendamento trimestral, por exemplo).
"""

import argparse
import asyncio
import os
import sys
from datetime import UTC, datetime

try:
    import asyncpg
except ModuleNotFoundError:  # pragma: no cover - depende do ambiente, nao da logica
    print("ERRO: asyncpg nao instalado. Rode: pip install -r requirements.txt")
    sys.exit(2)


def _normaliza(dsn: str) -> str:
    """
    asyncpg nao entende o prefixo do SQLAlchemy nem o `postgres://` legado que
    alguns paineis do Railway ainda entregam.
    """
    for prefixo, troca in (
        ("postgresql+asyncpg://", "postgresql://"),
        ("postgres://", "postgresql://"),
    ):
        if dsn.startswith(prefixo):
            return troca + dsn[len(prefixo):]
    return dsn


async def _tabelas(con) -> list[tuple[str, str]]:
    """
    A lista sai do banco de origem: nenhuma tabela nova escapa da conferencia.

    TODOS os schemas de aplicacao, nao so `public` - as calculadoras vivem em
    `calculators`, e restringir a `public` deixaria 6 tabelas fora da conferencia
    (era o bug que este script existe para nao cometer).
    """
    linhas = await con.fetch(
        """
        SELECT schemaname, tablename FROM pg_tables
        WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
          AND tablename <> 'alembic_version'
        ORDER BY schemaname, tablename
        """
    )
    return [(linha["schemaname"], linha["tablename"]) for linha in linhas]


async def _tem_created_at(con, schema: str, tabela: str) -> bool:
    return bool(
        await con.fetchval(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = $1 AND table_name = $2 AND column_name = 'created_at'
            """,
            schema,
            tabela,
        )
    )


async def _fotografa(con, tabelas: list[tuple[str, str]]) -> dict[tuple[str, str], tuple[int, datetime | None]]:
    """Contagem e dado mais recente de cada tabela. Aspas duplas: o nome vem do banco."""
    foto: dict[tuple[str, str], tuple[int, datetime | None]] = {}
    for schema, tabela in tabelas:
        alvo = f'"{schema}"."{tabela}"'
        total = await con.fetchval(f"SELECT count(*) FROM {alvo}")
        recente = None
        if await _tem_created_at(con, schema, tabela):
            recente = await con.fetchval(f"SELECT max(created_at) FROM {alvo}")
        foto[(schema, tabela)] = (total, recente)
    return foto


async def _revisao(con) -> str | None:
    """Contagem igual com revisao de schema diferente nao prova restore integro."""
    try:
        return await con.fetchval("SELECT version_num FROM alembic_version")
    except asyncpg.PostgresError:
        return None


async def executar(dsn_origem: str, dsn_destino: str) -> int:
    origem = await asyncpg.connect(_normaliza(dsn_origem))
    try:
        destino = await asyncpg.connect(_normaliza(dsn_destino))
    except Exception:
        await origem.close()
        raise

    try:
        rev_origem, rev_destino = await _revisao(origem), await _revisao(destino)
        tabelas_origem = await _tabelas(origem)
        tabelas_destino = set(await _tabelas(destino))

        foto_origem = await _fotografa(origem, tabelas_origem)
        presentes = [t for t in tabelas_origem if t in tabelas_destino]
        foto_destino = await _fotografa(destino, presentes)
    finally:
        await origem.close()
        await destino.close()

    problemas: list[str] = []

    print(f"revisao alembic  origem:     {rev_origem or '(sem tabela alembic_version)'}")
    print(f"revisao alembic  restaurado: {rev_destino or '(sem tabela alembic_version)'}")
    if rev_origem != rev_destino:
        problemas.append("revisao do Alembic diferente entre os dois bancos")
    print()

    ausentes = [t for t in tabelas_origem if t not in tabelas_destino]
    if ausentes:
        nomes = ", ".join(f"{s}.{t}" for s, t in ausentes)
        problemas.append(f"{len(ausentes)} tabela(s) nao existem no restaurado: {nomes}")

    print(f"{'tabela':<40} {'origem':>10} {'restaurado':>12}   dado mais recente (origem)")
    print("-" * 100)
    for chave in tabelas_origem:
        nome = f"{chave[0]}.{chave[1]}"
        total_origem, recente = foto_origem[chave]
        if chave in ausentes:
            print(f"{nome:<40} {total_origem:>10} {'AUSENTE':>12}")
            continue
        total_destino, _ = foto_destino[chave]
        if total_origem != total_destino:
            problemas.append(f"{nome}: {total_origem} na origem, {total_destino} no restaurado")
        marca = "" if total_origem == total_destino else "   <-- DIVERGE"
        carimbo = recente.isoformat(sep=" ", timespec="seconds") if recente else "-"
        print(f"{nome:<40} {total_origem:>10} {total_destino:>12}   {carimbo}{marca}")

    # O RPO real e a distancia entre este carimbo e a hora do snapshot. Sem este
    # numero, RPO segue sendo promessa - que e o que o runbook admitia.
    recentes = [r for _, r in foto_origem.values() if r is not None]
    print()
    if recentes:
        ultimo = max(recentes)
        print(f"Dado mais recente em qualquer tabela (origem): {ultimo.isoformat(sep=' ', timespec='seconds')}")
        if ultimo.tzinfo is not None:
            agora = datetime.now(UTC)
            print(f"  ...ou seja, {agora - ultimo} atras (agora: {agora.isoformat(sep=' ', timespec='seconds')})")
        print("  RPO real = intervalo entre esse carimbo e a hora do snapshot do backup.")

    print()
    if problemas:
        print(f"DIVERGENCIAS ({len(problemas)}):")
        for problema in problemas:
            print(f"  - {problema}")
        print()
        print("Restore NAO confere. Nao registre RPO/RTO com base neste ensaio.")
        return 1

    print(f"OK: {len(tabelas_origem)} tabelas conferem em contagem, e a revisao do Alembic bate.")
    print("Falta so o passo manual: subir um ambiente de TESTE contra o restaurado e")
    print("confirmar /api/v1/health/ready. Nunca aponte producao para ele.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Compara banco de origem e banco restaurado. Somente leitura.")
    parser.add_argument("--origem", default=os.environ.get("RESTORE_ORIGEM"))
    parser.add_argument("--restaurado", default=os.environ.get("RESTORE_DESTINO"))
    args = parser.parse_args()

    if not args.origem or not args.restaurado:
        print("ERRO: faltou informar os dois bancos (--origem/--restaurado ou as")
        print("      variaveis RESTORE_ORIGEM/RESTORE_DESTINO). Ver o topo do arquivo.")
        return 2

    # Salvaguarda barata contra o erro que transforma ensaio em incidente.
    if _normaliza(args.origem) == _normaliza(args.restaurado):
        print("ERRO: as duas URLs sao o mesmo banco - o ensaio compararia producao com ela mesma.")
        return 2

    return asyncio.run(executar(args.origem, args.restaurado))


if __name__ == "__main__":
    sys.exit(main())
