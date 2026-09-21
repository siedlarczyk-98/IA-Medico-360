# Subir para produção — roteiro das fases 1 a 7

Preparado em 2026-09-21. Cobre tudo o que está na árvore de trabalho: 168 arquivos,
três migrations, mudança no `CMD` dos oito Dockerfiles e um cabeçalho novo em todos
os frontends.

**A regra que organiza este roteiro:** as três migrations são compatíveis com o código
ANTIGO, e o código novo NÃO funciona sem elas. Então a ordem é sempre
**backup → migrations → código**. Invertido, ninguém faz login.

Tempo estimado: 2 a 3 horas, sem contar a revisão do diff. Faça fora do horário de
pico dos médicos; são 18 usuários, mas o deploy reinicia a API.

---

## Etapa 1 — Antes de tocar em produção

### 1.1 Revisar e commitar, num BRANCH

- [ ] Criar um branch (`git switch -c hardening-fases-1-7`) e commitar lá. **Não direto
      na `main`**: o push na `main` dispara o deploy de todos os serviços no Railway, e
      o CI novo nunca rodou no GitHub.
- [ ] Um commit por fase, na ordem. O resumo de cada uma está na memória do projeto
      (`medico360-fase-N-andamento`) e em `docs/pendencias.md`.
- [ ] `git rm --cached .claude/settings.local.json` (já está no `.gitignore`).
- [ ] Conferir que `backups/` continua fora do git (`git status` não deve listá-la).

### 1.2 Abrir um PR e esperar o CI ficar verde

O CI roda em `pull_request` — dá para validar tudo sem deployar nada. Três coisas
**nunca rodaram no GitHub** e são as que podem falhar:

- [ ] Job novo **`landing-pages`** (matriz das três páginas). Se o `npm ci` recusar o
      lockfile como incompleto, é a armadilha conhecida do lock gerado no Windows:
      regenerar o `package-lock.json` da página num Linux (ou no próprio Actions).
- [ ] **Portão de cobertura em 75%** (estava em 50). Medido localmente: 82%.
- [ ] Passo de migrations com **`alembic downgrade -1` + `upgrade head`**.

Localmente já está verde: backend 1524 testes, chat 222, dea-app 43; lint e build de
todos os apps tocados.

### 1.3 Variáveis no painel do Railway (pode fazer antes, não afeta o código atual)

Serviço do **backend**:

| Variável | Valor | Por quê |
| --- | --- | --- |
| `NOTICIAS_URL` | `https://news-m360.up.railway.app` | Hoje aponta para a API: todo link do e-mail diário de notícias dá 404. **Defeito ativo, independe deste deploy.** |
| `RAILWAY_DEPLOYMENT_DRAINING_SECONDS` | `90` | Sem ela o Railway mata o processo no deploy e corta as respostas em andamento; o `--timeout-graceful-shutdown` novo não adianta sozinho. |
| `REDIS_URL` | conferir que existe e aponta para um Redis de verdade | O rate limit passa a contar no Redis. Sem Redis ele cai para a memória (testado: nada quebra), mas o limite volta a valer por processo. |
| `PHOENIX_API_KEY` | rotacionar no Arize e colar a nova | A atual foi colada em texto puro numa conversa. |
| `SESSION_MAX_AGE_HOURS` | opcional; padrão `24` | Só se quiser outra duração de sessão. |

**Não precisa** criar nenhuma variável nova para o código subir. As quatro que saíram
do código (`APP_NAME`, `MAX_MODELS_PER_QUERY`, `MAX_PROMPT_CHARS`,
`DEFAULT_TIMEOUT_SECONDS`), se existirem no painel, são ignoradas — pode apagar depois.

Serviços dos **frontends**: nenhuma variável nova. Conferir só que `VITE_WAID_ORIGIN`
é `https://www.medico360.app` onde estiver definida (o `frame-ancestors` novo usa esse
valor, fixo nos `serve.json`).

---

## Etapa 2 — Backup (obrigatório, imediatamente antes das migrations)

O Railway não faz backup; o RPO é a idade do último dump.

```bash
python -m scripts.backup_producao --dsn "postgresql://..."   # URL em Railway → Postgres → Connect
```

- [ ] O script termina dizendo que o `pg_restore -l` leu o arquivo.
- [ ] **Subir o dump para o Drive.** Dump que só existe no notebook não sobrevive ao
      incidente que mais assusta.
- [ ] Aproveitar e resolver a pendência antiga: os cinco dumps velhos em `backups/`
      saem da pasta do projeto, criptografados (os dois `pre-*` podem ser apagados).

---

## Etapa 3 — Migrations (antes do código)

São três, e as três funcionam com o código que está no ar hoje:

| Migration | O que faz | Com o código ANTIGO rodando |
| --- | --- | --- |
| `013_consent_anonimizavel` | `consent_logs.user_id` aceita nulo | Nada muda |
| `014_token_version` | coluna `users.token_version`, padrão 0 | O banco preenche sozinho; nada muda |
| `015_otp_code_hmac` | `otp_codes.code` de 6 para 64 caracteres; **invalida os códigos pendentes** | Quem estava no meio de um login pede outro código |

Da sua máquina, contra produção (é o procedimento do `docs/runbook.md`):

```bash
DSN=$(grep "^DATABASE_URL=" .env | sed 's/^DATABASE_URL=//')
# CONFIRA o que vai ser tocado antes de rodar:
DATABASE_URL="$DSN" APP_ENV=development JWT_SECRET_KEY="<32+ bytes quaisquer>" \
  python -c "from app.core.config import get_settings; print(get_settings().database_url.split('@')[-1])"
DATABASE_URL="$DSN" APP_ENV=development JWT_SECRET_KEY="<32+ bytes quaisquer>" python -m alembic current
DATABASE_URL="$DSN" APP_ENV=development JWT_SECRET_KEY="<32+ bytes quaisquer>" python -m alembic upgrade head
```

- [ ] `alembic current` ANTES mostra `012_dea`. Se mostrar outra coisa, **pare**: a
      cadeia de produção não está onde se supõe.
- [ ] `alembic current` DEPOIS mostra `015_otp_code_hmac`.
- [ ] Abrir o chat em produção e conferir que o login continua funcionando com o
      código antigo no ar. É a prova de que as migrations são compatíveis.

Testado aqui: a cadeia inteira aplica num banco vazio, e cada uma das três fez ida e
volta (`downgrade -1` / `upgrade head`) num banco descartável.

---

## Etapa 4 — Código

- [ ] Merge do PR na `main`. O Railway reconstrói os serviços.
- [ ] **Backend primeiro, se der para escolher.** Os dois sentidos do descompasso foram
      pensados e nenhum quebra:
      - backend novo + frontend antigo: o perfil ainda manda o e-mail (aceito, se for o
        mesmo); a farmácia sai pelo stream e o chat antigo trata normalmente.
      - frontend novo + backend antigo: o "Sair" chama uma rota que ainda não existe (o
        erro é engolido de propósito); a farmácia cai no ramo `unsupported_mode`, que
        foi mantido para isso.
- [ ] Todos os **oito Dockerfiles mudaram**: o backend (keep-alive e encerramento
      gracioso) e os sete frontends (`serve` sem `-s`, fallback de SPA no `serve.json`).
      Conferir no painel que os oito serviços fizeram build.

---

## Etapa 5 — Verificar, na ordem do que mais dói se estiver quebrado

### 5.1 Em 5 minutos (bloqueante — se falhar, reverter)

- [ ] `GET https://medico360-ia.up.railway.app/api/v1/health/ready` → 200, postgres e
      redis `ok`.
- [ ] **Login por código de e-mail** em produção: pedir, receber, digitar. (Migration 015
      + HMAC + envio em segundo plano.)
- [ ] **Abrir o chat DENTRO da área de membros** (`www.medico360.app`). Se abrir em
      branco, é o `frame-ancestors`: o console mostra `Refused to frame` com a origem que
      faltou. Repetir para calculadoras, notícias e uma página de captação.
- [ ] **Recarregar uma rota profunda** do chat (F5 numa conversa aberta). É o `serve` sem
      `-s`: tem de abrir, não dar 404.
- [ ] Fazer **uma pergunta** no chat e ver a resposta chegar inteira, com as referências.
- [ ] Fazer **uma pergunta de farmácia** ("bula do Rivotril"): agora sai pelo stream.

### 5.2 Na primeira hora

- [ ] **Sair** e, na mesma aba, abrir `/api/v1/auth/me` → 401.
- [ ] Perfil: o e-mail aparece somente leitura.
- [ ] **Cadastrar um DEA pelo navegador** em `dea-m360.up.railway.app` — era 403.
- [ ] Depois disso, `dea-m360` e `news-m360` podem **sair** de `EMBED_ALLOWED_ORIGINS`, se
      estavam lá só para contornar o 403.
- [ ] Logs do backend, procurar por:
      - `orquestrador_query_obsoleto` — alguém ainda usa a rota antiga (esperado: nada);
      - `embed_identidade_divergente` — um médico legítimo foi barrado no embed; o
        conserto é corrigir `users.waid_uuid` por SQL;
      - `QueuePool limit` ou `TimeoutError` de pool — não deveria mais aparecer.
- [ ] Sentry: nenhum pico novo.

### 5.3 Na primeira semana

O roteiro completo de homologação na tela, por fase, está em `docs/pendencias.md`
(seção 3). Os que dependem de aparelho de verdade: iPhone (altura e zoom do campo),
metrônomo com uma ligação no meio, app da Waid abrindo notícias duas vezes seguidas.

---

## Se der errado — reverter

**Reverter é só código. NÃO faça `alembic downgrade`.**

- [ ] `git revert` do merge e push na `main` (ou redeploy do build anterior no painel).
- As três migrations ficam: o código antigo funciona com elas (é a premissa da etapa 3).
  O `downgrade` da 015 **apaga todos os códigos de login** e o da 013 apaga os
  consentimentos já anonimizados — não há motivo para rodar nenhum dos dois.
- Sessões emitidas pelo código novo continuam válidas no antigo (ele ignora as marcas
  `auth_time` e `tv`). Códigos de login emitidos pelo novo param de valer; o médico pede
  outro.

Sintoma → causa provável:

| Sintoma | Causa provável |
| --- | --- |
| Ninguém faz login, erro 500 | O código subiu ANTES da migration 014 (`users.token_version` não existe). Aplicar as migrations. |
| Login por código sempre "inválido" | Migration 015 não aplicada: o HMAC de 64 caracteres não coube na coluna de 6. |
| App em branco dentro da área de membros | Origem faltando no `frame-ancestors` dos `public/serve.json`. |
| 404 ao recarregar uma página do app | `public/serve.json` não chegou ao `dist` daquele app (conferir o build). |
| Exclusão de conta ainda dá 500 | Migration 013 não aplicada. |
| Deploy continua cortando respostas | Faltou `RAILWAY_DEPLOYMENT_DRAINING_SECONDS=90`. |

---

## O que NÃO bloqueia a subida, mas está aberto

- **Preços dos modelos**: `scripts/dados/model_pricing.json` está vazio; a verdade mora só
  no banco de produção. O `SELECT` de exportação está no cabeçalho de
  `scripts/seed_models.py`. Não afeta produção (o banco de lá tem os preços); afeta a
  capacidade de reconstruir um ambiente do zero.
- **`SHOW max_connections;`** no Postgres de produção — alimenta a decisão de subir
  workers.
- **Decisões de produto**: formulários de captação na exclusão de conta; origem do LMS
  parceiro com credenciais de CORS; aviso de privacidade nas páginas de captação.
- Tudo isso, mais as dívidas técnicas registradas, está em `docs/pendencias.md`.
