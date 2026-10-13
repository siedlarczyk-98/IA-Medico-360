#!/usr/bin/env bash
# Amostra o lado do SERVIDOR durante uma rodada de carga, a cada 2 s:
# CPU/memória dos containers, conexões do Postgres por estado e streams abertos
# no servidor falso. Roda em paralelo com `gerar_carga.py` e para sozinho.
#
# Uso: bash scripts/carga/observar.sh <segundos> <arquivo de saída>
set -uo pipefail

DURACAO=${1:-300}
SAIDA=${2:-scripts/carga/resultados/observacao.tsv}
mkdir -p "$(dirname "$SAIDA")"

SQL="select count(*),
  count(*) filter (where state='active'),
  count(*) filter (where state='idle'),
  count(*) filter (where state like 'idle in transaction%'),
  coalesce(round(max(extract(epoch from now()-state_change)) filter (where state like 'idle in transaction%')),0),
  count(*) filter (where wait_event_type='Lock')
from pg_stat_activity where datname='m360' and pid<>pg_backend_pid()"

printf "t\tapi_cpu\tapi_mem\tdb_cpu\tredis_cpu\tfalso_cpu\tpg_total\tpg_ativas\tpg_ociosas\tpg_presas\tpresa_max_s\tpg_lock\tstreams_falso\n" > "$SAIDA"
INICIO=$(date +%s)
while (( $(date +%s) - INICIO < DURACAO )); do
  T=$(( $(date +%s) - INICIO ))
  STATS=$(docker stats --no-stream --format "{{.Name}} {{.CPUPerc}} {{.MemUsage}}" \
          m360-carga-api m360-carga-db m360-carga-redis m360-carga-falso 2>/dev/null)
  api_cpu=$(awk '$1=="m360-carga-api"{print $2}' <<<"$STATS")
  api_mem=$(awk '$1=="m360-carga-api"{print $3}' <<<"$STATS")
  db_cpu=$(awk '$1=="m360-carga-db"{print $2}' <<<"$STATS")
  redis_cpu=$(awk '$1=="m360-carga-redis"{print $2}' <<<"$STATS")
  falso_cpu=$(awk '$1=="m360-carga-falso"{print $2}' <<<"$STATS")
  PG=$(docker exec m360-carga-db psql -U postgres -d m360 -tA -F $'\t' -c "$SQL" 2>/dev/null)
  STREAMS=$(curl -s localhost:9000/_estatisticas | python -c "import sys,json;print(json.load(sys.stdin)['streams'])" 2>/dev/null)
  printf "%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n" "$T" "$api_cpu" "$api_mem" "$db_cpu" "$redis_cpu" "$falso_cpu" "$PG" "$STREAMS" >> "$SAIDA"
  sleep 2
done
