# Landing page de captação.
#
# O CONTEXTO DESTE BUILD É A RAIZ DO MONOREPO, não esta pasta — a LP importa
# `shared/embed`, que fica fora daqui. É o mesmo motivo dos três apps
# autenticados: com Root Directory apontando para a pasta da LP, `../shared`
# não existe no contexto e o `tsc -b` falha.
#
# No Railway (Settings do serviço):
#   Root Directory  = /
#   Builder         = Dockerfile
#   Dockerfile Path = lp-contabilidade/Dockerfile   (via RAILWAY_DOCKERFILE_PATH)
#
# O `railway.json` desta pasta foi REMOVIDO: Config as Code está depreciado
# (para de ser lido em 2026-12-01) e sobrescreveria o painel enquanto existisse.

FROM node:22-alpine AS build
WORKDIR /repo

COPY lp-contabilidade/package.json lp-contabilidade/package-lock.json lp-contabilidade/
RUN cd lp-contabilidade && npm ci

COPY shared/ shared/
COPY lp-contabilidade/ lp-contabilidade/

# O Vite RESOLVE `import.meta.env` em tempo de BUILD. TODA variável `VITE_`
# nova precisa de UMA LINHA `ARG` aqui, além de existir no painel do Railway —
# sem o ARG o valor não chega, o default do código é assado no bundle, e nenhum
# redeploy conserta.
ARG VITE_API_URL
ARG VITE_WAID_ORIGIN
ENV VITE_API_URL=$VITE_API_URL
ENV VITE_WAID_ORIGIN=$VITE_WAID_ORIGIN

RUN cd lp-contabilidade && npm run build

FROM node:22-alpine
WORKDIR /app
RUN npm install -g serve@14
COPY --from=build /repo/lp-contabilidade/dist ./dist

CMD ["sh", "-c", "serve dist -s -l tcp://0.0.0.0:${PORT:-3000}"]
