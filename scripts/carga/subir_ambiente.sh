#!/usr/bin/env bash
# Sobe o ambiente LOCAL do teste de carga: Postgres (pgvector, max_connections=500
# como produção), Redis, o servidor falso dos serviços externos e o backend na
# MESMA imagem do Dockerfile de produção.
#
# Uso (da raiz do repo, no Git Bash):
#   bash scripts/carga/subir_ambiente.sh              # 2 workers, como produção
#   WEB_CONCURRENCY=4 bash scripts/carga/subir_ambiente.sh
#   FALSO_ESCALA=0.5 bash scripts/carga/subir_ambiente.sh   # modelos 2x mais rápidos
#   FALSO_ESCALA_WAID=8 bash scripts/carga/subir_ambiente.sh --so-falso   # só a Waid lenta
#   bash scripts/carga/subir_ambiente.sh --derrubar
#
# Portas no host: backend 8010, falso 9000, Postgres 55434, Redis 56379.
# Não toca no m360-test-db (55433), que é do harness de testes.
set -euo pipefail

REDE=m360-carga
IMAGEM=m360-carga-api
CONTAINERS="m360-carga-api m360-carga-falso m360-carga-redis m360-carga-db"

if [[ "${1:-}" == "--derrubar" ]]; then
  docker rm -f $CONTAINERS >/dev/null 2>&1 || true
  docker network rm $REDE >/dev/null 2>&1 || true
  echo "[carga] ambiente derrubado"
  exit 0
fi

cd "$(dirname "$0")/../.."

# O servidor falso monta a pasta em vez de usar a cópia da imagem: dá para mudar
# latência ou código dele sem reconstruir nada (`--so-falso`).
subir_falso() {
  docker rm -f m360-carga-falso >/dev/null 2>&1 || true
  echo "[carga] servidor falso (escala ${FALSO_ESCALA:-1.0}, Waid x${FALSO_ESCALA_WAID:-1.0}, erro ${FALSO_ERRO_PCT:-0}%)"
  MSYS_NO_PATHCONV=1 docker run -d --name m360-carga-falso --network $REDE -p 9000:9000 \
    -v "$(cygpath -w "$PWD/scripts/carga" 2>/dev/null || echo "$PWD/scripts/carga"):/carga" \
    -e FALSO_ESCALA="${FALSO_ESCALA:-1.0}" -e FALSO_ESCALA_WAID="${FALSO_ESCALA_WAID:-1.0}" \
    -e FALSO_ERRO_PCT="${FALSO_ERRO_PCT:-0}" \
    $IMAGEM python -m uvicorn falso_externo:app --app-dir /carga \
    --host 0.0.0.0 --port 9000 --log-level warning --timeout-keep-alive 75 >/dev/null
}

if [[ "${1:-}" == "--so-falso" ]]; then
  subir_falso
  exit 0
fi

echo "[carga] construindo a imagem do backend"
docker build -q -t $IMAGEM . >/dev/null

docker rm -f $CONTAINERS >/dev/null 2>&1 || true
docker network create $REDE >/dev/null 2>&1 || true

echo "[carga] Postgres e Redis"
docker run -d --name m360-carga-db --network $REDE \
  -e POSTGRES_PASSWORD=carga -e POSTGRES_DB=m360 -p 55434:5432 \
  pgvector/pgvector:pg16 -c max_connections=500 >/dev/null
docker run -d --name m360-carga-redis --network $REDE -p 56379:6379 redis:7-alpine >/dev/null

for _ in $(seq 1 30); do
  docker exec m360-carga-db pg_isready -U postgres -d m360 >/dev/null 2>&1 && break
  sleep 1
done

echo "[carga] servidor falso (escala ${FALSO_ESCALA:-1.0}, erro ${FALSO_ERRO_PCT:-0}%)"
docker run -d --name m360-carga-falso --network $REDE -p 9000:9000 \
  -e FALSO_ESCALA="${FALSO_ESCALA:-1.0}" -e FALSO_ERRO_PCT="${FALSO_ERRO_PCT:-0}" \
  $IMAGEM python -m uvicorn scripts.carga.falso_externo:app \
  --host 0.0.0.0 --port 9000 --log-level warning --timeout-keep-alive 75 >/dev/null

echo "[carga] migrations e modelos"
docker run --rm --network $REDE --env-file scripts/carga/ambiente.env $IMAGEM \
  sh -c "alembic upgrade head >/dev/null && python scripts/seed_models.py >/dev/null"

echo "[carga] backend com ${WEB_CONCURRENCY:-2} worker(s)"
docker run -d --name m360-carga-api --network $REDE -p 8010:8000 \
  --env-file scripts/carga/ambiente.env -e WEB_CONCURRENCY="${WEB_CONCURRENCY:-2}" \
  -e CARGA_TROCA_MODELOS="${CARGA_TROCA_MODELOS:-}" -e CARGA_FALSO_HOSTS="${CARGA_FALSO_HOSTS:-}" \
  $IMAGEM >/dev/null

for _ in $(seq 1 60); do
  if curl -fs http://localhost:8010/api/v1/health >/dev/null 2>&1 \
     || curl -fs http://localhost:8010/health >/dev/null 2>&1; then
    echo "[carga] pronto: http://localhost:8010"
    exit 0
  fi
  sleep 2
done
echo "[carga] o backend não respondeu; últimas linhas do log:"
docker logs --tail 40 m360-carga-api
exit 1
