# App de notícias (feed por tema), embedado como iframe no LMS.
#
# O CONTEXTO DESTE BUILD É A RAIZ DO MONOREPO, não esta pasta — ver o comentário
# em `frontend-app/Dockerfile`. Resumo: este app importa `shared/onboarding`.
#
# No Railway (Settings do serviço, NÃO em railway.json):
#   Root Directory  = /
#   Builder         = Dockerfile
#   Dockerfile Path = noticias-app/Dockerfile
#
# Config as Code (railway.json) está depreciado e sobrescreveria o painel,
# então os arquivos legados foram removidos. A substituição da Railway é
# Infrastructure as Code (.railway/railway.ts), que descreve o projeto
# INTEIRO num arquivo só — migração à parte, não é pré-requisito daqui.

FROM node:22-alpine AS build
WORKDIR /repo

COPY noticias-app/package.json noticias-app/package-lock.json noticias-app/
RUN cd noticias-app && npm ci

COPY shared/ shared/
COPY noticias-app/ noticias-app/

# Resolvida em tempo de build pelo Vite; sem ela o bundle aponta para localhost.
ARG VITE_API_URL
ARG VITE_WAID_ORIGIN
ENV VITE_API_URL=$VITE_API_URL
ENV VITE_WAID_ORIGIN=$VITE_WAID_ORIGIN

# TODA variável `VITE_` nova precisa de UMA LINHA `ARG` AQUI, além de existir no
# painel do Railway. Sem o ARG, o Docker não recebe o valor e o Vite assa o
# default do código no bundle — build verde, comportamento errado, e nenhum
# redeploy conserta.

RUN cd noticias-app && npm run build

FROM node:22-alpine
WORKDIR /app
RUN npm install -g serve@14
COPY --from=build /repo/noticias-app/dist ./dist

CMD ["sh", "-c", "serve dist -s -l tcp://0.0.0.0:${PORT:-3000}"]
