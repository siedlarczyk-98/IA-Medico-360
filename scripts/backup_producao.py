"""
Backup logico do Postgres: gera um dump com carimbo de data e PROVA que ele e
legivel antes de dizer que deu certo.

    python -m scripts.backup_producao --dsn "postgresql://..." --saida backups/

A URL sai de Railway > Postgres > Connect. So faz leitura no banco de origem.

Por que existe: ate 2026-08-19 o projeto nao tinha backup NENHUM (o Railway so
oferece backup/PITR no plano Pro, e o servico nao esta nele). O runbook afirmava
que a recuperacao dependia do backup do Railway - afirmacao falsa, no documento
que alguem abre durante um incidente.

Usa `pg_dump` dentro do Docker, com a MESMA versao maior do servidor: pg_dump
mais antigo que o servidor se recusa a rodar, e nao ha pg_dump instalado no
Windows por padrao. Formato custom (-Fc), que permite restauracao seletiva e ja
vem comprimido.

O que este script NAO faz, e voce precisa fazer: levar o arquivo para fora desta
maquina (Drive, S3). Dump que so existe no mesmo disco nao sobrevive ao incidente
que mais assusta.
"""

import argparse
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

# Precisa conter o pg_dump; a tag muda conforme a versao do servidor.
IMAGEM = "pgvector/pgvector:pg{maior}"


def _normaliza(dsn: str) -> str:
    for prefixo, troca in (("postgresql+asyncpg://", "postgresql://"), ("postgres://", "postgresql://")):
        if dsn.startswith(prefixo):
            return troca + dsn[len(prefixo):]
    return dsn


def _para_container(dsn: str) -> str:
    """
    `localhost` dentro do container e o proprio container, nao esta maquina. Nao
    afeta o uso real (URL do Railway), mas deixa o script utilizavel tambem
    contra um banco local - inclusive para testar o proprio script.
    """
    return re.sub(r"@(localhost|127\.0\.0\.1)(?=[:/])", "@host.docker.internal", dsn)


def _oculta(texto: str, dsn: str) -> str:
    """Nunca imprimir a senha - a saida daqui costuma ser colada em chat/ticket."""
    senha = re.search(r"://[^:]+:([^@]+)@", dsn)
    return texto.replace(senha.group(1), "***") if senha else texto


def _versao_maior(dsn: str) -> int | None:
    """
    Descobre a versao do servidor para escolher a imagem certa. asyncpg ja e
    dependencia do projeto, entao nao adiciona nada novo.
    """
    import asyncio

    import asyncpg

    async def consulta():
        con = await asyncpg.connect(dsn)
        try:
            return await con.fetchval("SHOW server_version")
        finally:
            await con.close()

    try:
        bruta = asyncio.run(consulta())
    except Exception as erro:
        print(f"ERRO ao conectar no banco: {_oculta(str(erro), dsn)}")
        return None
    print(f"Servidor: PostgreSQL {bruta}")
    return int(str(bruta).split(".")[0].split(" ")[0])


def main() -> int:
    parser = argparse.ArgumentParser(description="Dump do Postgres, com verificacao de integridade.")
    parser.add_argument("--dsn", default=os.environ.get("BACKUP_DSN"), help="URL do banco (ou BACKUP_DSN)")
    parser.add_argument("--saida", default="backups", help="Diretorio de destino (padrao: backups/)")
    args = parser.parse_args()

    if not args.dsn:
        print("ERRO: informe --dsn ou a variavel BACKUP_DSN.")
        return 2

    dsn = _normaliza(args.dsn)

    if subprocess.run(["docker", "version"], capture_output=True).returncode != 0:
        print("ERRO: Docker nao esta disponivel. Abra o Docker Desktop e tente de novo.")
        return 2

    maior = _versao_maior(dsn)
    if maior is None:
        return 1
    imagem = IMAGEM.format(maior=maior)

    destino = Path(args.saida)
    destino.mkdir(parents=True, exist_ok=True)
    # UTC no nome: fuso local em nome de arquivo de backup e fonte classica de
    # confusao na hora de ordenar qual e o mais recente.
    momento = datetime.now(UTC)
    arquivo = destino / f"medico360-{momento.strftime('%Y%m%dT%H%M%SZ')}.dump"

    print(f"Imagem: {imagem}")
    print(f"Destino: {arquivo}")
    print("Rodando pg_dump (so leitura na origem)...")
    inicio = datetime.now(UTC)

    with arquivo.open("wb") as saida:
        resultado = subprocess.run(
            [
                "docker", "run", "--rm", "-i",
                "--add-host=host.docker.internal:host-gateway",
                imagem,
                "pg_dump", "--format=custom", "--no-owner", "--no-privileges",
                _para_container(dsn),
            ],
            stdout=saida,
            stderr=subprocess.PIPE,
            text=False,
        )

    duracao = datetime.now(UTC) - inicio
    if resultado.returncode != 0:
        erro = resultado.stderr.decode("utf-8", "replace").strip()
        print(f"FALHOU: {_oculta(erro, dsn)}")
        arquivo.unlink(missing_ok=True)  # nao deixar dump parcial parecendo backup valido
        return 1

    tamanho = arquivo.stat().st_size
    print(f"Dump escrito em {duracao} ({tamanho / 1_048_576:.1f} MiB)")

    # Arquivo existir e ter tamanho nao prova nada: dump truncado tambem tem.
    # `pg_restore -l` le o indice interno - se ele lista as tabelas, o arquivo
    # esta integro o suficiente para ser restaurado.
    print("Verificando se o arquivo e legivel (pg_restore -l)...")
    with arquivo.open("rb") as entrada:
        listagem = subprocess.run(
            ["docker", "run", "--rm", "-i", imagem, "pg_restore", "-l"],
            stdin=entrada,
            capture_output=True,
            text=True,
        )
    if listagem.returncode != 0:
        print(f"FALHOU a verificacao: {listagem.stderr.strip()}")
        print("O arquivo NAO e um backup confiavel. Nao o envie como se fosse.")
        return 1

    tabelas = sum(1 for linha in listagem.stdout.splitlines() if " TABLE DATA " in linha)
    print(f"OK: arquivo integro, {tabelas} tabelas com dados.")
    if tabelas == 0:
        print("ATENCAO: nenhuma tabela com dados. Confira se a URL aponta para o banco certo.")
        return 1

    print()
    print("FALTA O PASSO QUE VOCE PRECISA FAZER:")
    print(f"  1. Suba {arquivo.name} para o Drive (ou outro destino FORA desta maquina).")
    print("     Backup no mesmo disco nao sobrevive ao incidente que mais assusta.")
    print("  2. Anote a data deste dump: seu RPO e a distancia entre ele e agora.")
    print("  3. Para provar que ele restaura de verdade, ver docs/runbook.md > Ensaio de restore.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
