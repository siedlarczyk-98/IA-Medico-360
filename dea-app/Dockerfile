# App de DEA: metrônomo de RCP + mapa colaborativo de desfibriladores.
#
# Diferente dos outros apps do monorepo, este NÃO é embed: não abre em iframe do
# LMS, não tem identidade nem login. É público, e o público-alvo inicial são os
# participantes dos cursos de ACLS.
#
# O CONTEXTO DESTE BUILD É A RAIZ DO MONOREPO, não esta pasta — o `vite.config.ts`
# tem o alias `@shared` apontando para `../shared`. Hoje nada de `shared/` é
# importado, mas o contexto na raiz mantém o build idêntico ao dos outros apps e
# evita uma migração no dia em que passar a importar.
#
# No Railway (Settings do serviço, NÃO em railway.json):
#   Root Directory  = /
#   Builder         = Dockerfile
#   Dockerfile Path = dea-app/Dockerfile

FROM node:22-alpine AS build
WORKDIR /repo

COPY dea-app/package.json dea-app/package-lock.json dea-app/
RUN cd dea-app && npm ci

COPY shared/ shared/
COPY dea-app/ dea-app/

# Resolvida em tempo de build pelo Vite; sem ela o bundle aponta para localhost.
ARG VITE_API_URL
ENV VITE_API_URL=$VITE_API_URL

# TODA variável `VITE_` nova precisa de UMA LINHA `ARG` AQUI, além de existir no
# painel do Railway. Sem o ARG, o Docker não recebe o valor e o Vite assa o
# default do código no bundle — build verde, comportamento errado, e nenhum
# redeploy conserta.
#
# Não é hipotético: no primeiro deploy deste app (2026-09-09) o `ARG` faltava, o
# serviço subiu verde e o mapa chamava `localhost:8000` do navegador de quem
# abrisse a página.

RUN cd dea-app && npm run build

FROM node:22-alpine
WORKDIR /app
RUN npm install -g serve@14
COPY --from=build /repo/dea-app/dist ./dist

CMD ["sh", "-c", "serve dist -s -l tcp://0.0.0.0:${PORT:-3000}"]
