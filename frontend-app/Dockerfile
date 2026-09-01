# App principal (chat/orquestrador).
#
# O CONTEXTO DESTE BUILD É A RAIZ DO MONOREPO, não esta pasta.
# Motivo: o app importa `shared/onboarding`, que vive fora daqui — é a tela de
# onboarding escrita uma vez e usada pelos três frontends. Com o Nixpacks e
# Root Directory apontando para `frontend-app/`, `../shared` simplesmente não
# existia no contexto e o build quebrava em `tsc -b`.
#
# No Railway (Settings do serviço, NÃO em railway.json):
#   Root Directory  = /
#   Builder         = Dockerfile
#   Dockerfile Path = frontend-app/Dockerfile
#
# Config as Code (railway.json) está depreciado e sobrescreveria o painel,
# então os arquivos legados foram removidos. A substituição da Railway é
# Infrastructure as Code (.railway/railway.ts), que descreve o projeto
# INTEIRO num arquivo só — migração à parte, não é pré-requisito daqui.

FROM node:22-alpine AS build
WORKDIR /repo

# Dependências primeiro, para a camada de `npm ci` reaproveitar cache enquanto
# só o código muda.
COPY frontend-app/package.json frontend-app/package-lock.json frontend-app/
RUN cd frontend-app && npm ci

COPY shared/ shared/
COPY frontend-app/ frontend-app/

# O Vite RESOLVE `import.meta.env` em tempo de build — variável que não chegar
# aqui vira o default do código (`http://localhost:8000`) dentro do bundle. Por
# isso vêm como ARG: no Railway, as variáveis do serviço são passadas como build
# args para builds com Dockerfile.
ARG VITE_API_URL
ARG VITE_INTERCOM_APP_ID
ENV VITE_API_URL=$VITE_API_URL
ENV VITE_INTERCOM_APP_ID=$VITE_INTERCOM_APP_ID

RUN cd frontend-app && npm run build

FROM node:22-alpine
WORKDIR /app
RUN npm install -g serve@14
COPY --from=build /repo/frontend-app/dist ./dist

# `-s` (single page application): qualquer rota cai no index.html, senão um F5
# em /onboarding devolve 404.
CMD ["sh", "-c", "serve dist -s -l tcp://0.0.0.0:${PORT:-3000}"]
