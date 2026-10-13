#!/usr/bin/env bash
# Roda uma rodada de carga DE DENTRO da rede do Docker, com observação do servidor.
#
# Por que num container: no Windows, o encaminhamento de porta do Docker Desktop
# é o gargalo — 300 conexões simultâneas em localhost:8010 levam 31 s de mediana,
# contra 1,8 s dentro da rede (medido em 2026-09-28). Rodando do host, o teste
# mediria o Docker Desktop, não o backend.
#
# Uso: bash scripts/carga/rodar.sh <segundos de observação> <argumentos do gerar_carga.py>
#   bash scripts/carga/rodar.sh 400 --cenario onda --medicos 100 --primeiro-id 5001
set -euo pipefail
cd "$(dirname "$0")/../.."

OBS=$1; shift
mkdir -p scripts/carga/resultados
NOME="obs-$(date +%Y%m%d-%H%M%S)-$(echo "$*" | tr -c 'a-z0-9' '-' | cut -c1-60)"
bash scripts/carga/observar.sh "$OBS" "scripts/carga/resultados/$NOME.tsv" &
OBSERVADOR=$!

MSYS_NO_PATHCONV=1 docker run --rm --network m360-carga \
  -v "$(cygpath -w "$PWD/scripts/carga" 2>/dev/null || echo "$PWD/scripts/carga"):/carga" \
  m360-carga-api python /carga/gerar_carga.py --base http://m360-carga-api:8000 \
  --saida /carga/resultados "$@"

wait $OBSERVADOR 2>/dev/null || true
echo "[carga] observação do servidor em scripts/carga/resultados/$NOME.tsv"
