# Arquitetura Técnica — Médico 360

> Levantamento estático do código em **2026-09-02** (commit `14496b0`). Referências `arquivo:linha` apontam para a raiz do repositório.
> Substitui a versão de 2026-08-28 — o que mudou desde então está no §1.

## 0. Como ler este documento

Se você tem uma tarde para entender o sistema, leia nesta ordem:

1. **§2 — topologia.** Quantos serviços existem de verdade e quem fala com quem.
2. **§5 — pipeline do Orquestrador.** É o produto. Todo o resto do backend orbita este fluxo.
3. **§3.4 — identidade profissional.** Como o médico é reconhecido e de onde vem a especialidade dele. É o trabalho mais recente e o que mais toca os três frontends.
4. **§6 — contexto e memória.** Histórico, orçamento de tokens e pastas-como-projeto. É fácil de quebrar sem perceber.
5. **§11 — banco.** O ER completo e as constraints que a aplicação assume.
6. **§17 — pontos de atenção.** Onde estão as armadilhas conhecidas, e o mapa de dívidas com tamanho e risco.

O resto é referência: tabelas de rotas, variáveis de ambiente, CI, scripts.

Documentos irmãos, que este aqui não duplica:

| Arquivo | O que traz |
|---|---|
| `docs/regras-de-negocio-v2.2.md` | Regras de negócio numeradas (RN-*) |
| `docs/Calculadoras_Cientificas_Regras_de_Arquitetura_v1.0.md` | Contrato de arquitetura do módulo de calculadoras |
| `docs/debitos.md` | 14 débitos técnicos, com status e justificativa de cada um |
| `docs/runbook.md` | Operação: incidentes, rotação de segredos, backup/restore (com números medidos), retenção |
| `docs/teste-e2e.md` | Como rodar o E2E das calculadoras |
| `README.md` | Setup local |

---

## 1. O que mudou desde o levantamento anterior (28 de agosto → 2 de setembro)

Duas frentes: o módulo de notícias e a identidade profissional do médico.

**Notícias (`noticias-app` + schema `news`)** — feed clínico por tema, alimentado por um pipeline PubMed → tagger → redator. O médico escolhe temas e palavras-chave; o feed casa artigos contra as duas coisas. Ver §7-A.

**Identidade profissional** — reescrita de como o sistema sabe quem é o médico:

- **A especialidade passou a ter dono e proveniência.** `users.specialty` era texto livre sem validação; agora existe um vocabulário canônico (`app/medicina/especialidades.py`, 55 especialidades do CFM) e uma regra de precedência entre as quatro fontes que podem escrevê-la (`app/medicina/identidade.py`).
- **Ela chega sozinha, dos grupos de acesso da Curseduca.** A página de cadastro (outro sistema, outro time) consulta o CFM e cria um grupo `[CFM] <especialidade>`. O payload do membro já era baixado a cada login de embed e descartado; agora dele saem o nome e a especialidade.
- **O onboarding virou uma tela só, compartilhada pelos três apps** (`shared/onboarding/`). O servidor calcula o que falta (`onboarding_pendencias`); os apps só renderizam. Antes existia em um app só, e os outros dois nem checavam.
- **O CRM deixou de ser exigido.** A prova de registro vem do grupo `[CFM]`; um CRM digitado à mão não acrescentava prova. A coluna continua, e continua sendo gravada de fonte confiável.
- **Os frontends passaram a buildar por Dockerfile**, com contexto na raiz do monorepo — o `shared/` fica fora da pasta de cada app e o Nixpacks não o enxergava. Ver §13.2.
- **`services/` ganhou um subpacote `integracoes/`** com os seis clientes de sistemas externos, que estavam soltos entre os demais.
- **Roteamento do Orquestrador unificado.** O bloco que decide qual agente atende era escrito duas vezes e já tinha divergido: na mesma situação de confiança baixa, `/query` e `/stream` diziam textos diferentes ao médico. Agora é `orquestrador_shared.decidir_rota`.
- **A cascata de exclusão de conta saiu do endpoint** para `auth_repository`, e ganhou os primeiros testes — eram 25 linhas de SQL cru sem cobertura nenhuma, onde a ORDEM das exclusões é o que impede erro de chave estrangeira.

---

## 2. Topologia real

Não existem "3 instâncias" no sentido de serviços de backend independentes. A arquitetura é:

- **1 backend único** (`app/`) — FastAPI monolítico que serve todos os domínios (Orquestrador/Agregador, Calculadoras, Notícias, Landing Pages) no mesmo processo, mesmo banco, mesmo router raiz.
- **6 frontends React**, cada um com deploy próprio no Railway:

| App | Papel | Porta dev | Rotas de backend que consome |
|---|---|---|---|
| `frontend-app/` | Chat do Orquestrador, histórico, pastas, anexos | 5173 | `/auth`, `/orquestrador`, `/agregador`, `/conversations`, `/folders`, `/uploads`, `/users/usage` |
| `calculadoras-app/` | Calculadoras clínicas | 5174 | `/auth`, `/calculators`, `/prevent`, `/landing-pages/calculators` |
| `noticias-app/` | Feed clínico por tema | 5176 | `/auth`, `/news`, `/meta` |
| `lp-financas/` | LP de captação — finanças | 5175 | `/landing-pages/finance` |
| `lp-contabilidade/` | LP de captação — contabilidade | 5178 | `/landing-pages/accounting` |
| `lp-parceiros/` | LP de captação — parceiros | 5177 | `/landing-pages/partners` |

Fora das pastas de app existe **`shared/`**, na raiz do monorepo: código que os três apps autenticados importam via alias `@shared`. Hoje contém só o onboarding (§3.4). Não é workspace npm — é alias de Vite + `paths` de TypeScript, e é o motivo de os três buildarem por Dockerfile com contexto na raiz (§13.2).

Os frontends não conversam entre si, e **os três autenticados são embedados separadamente** como iframes no LMS (Curseduca) — cada um com seu próprio `EmbedAuthPage`. Compartilham sessão via cookie SSO (`medico360_session`, domínio comum em `COOKIE_DOMAIN`) mais o fluxo dedicado `/auth/embed/token`. O que eles de fato compartilham é o **banco**: uma linha em `users` serve aos três, e é por isso que o onboarding preenchido em qualquer um vale para todos.

As LPs são públicas — não autenticam, exceto `/landing-pages/calculators/submit`, que é chamada de dentro do módulo logado.

> **Atenção ao ler código antigo:** o `noticias-app` foi um repositório separado (`medico360-news`) antes de migrar para cá. O schema `news` no Postgres tem migrations próprias na cadeia principal desde a `004`.

```mermaid
flowchart LR
    subgraph Apps["Apps autenticados (Railway / Nixpacks / serve dist)"]
        FA["frontend-app<br/>React 19 + Vite<br/>Orquestrador"]
        CA["calculadoras-app<br/>React 19 + Vite<br/>Calculadoras"]
    end

    subgraph LPs["Landing pages publicas"]
        LF["lp-financas"]
        LC["lp-contabilidade"]
        LPP["lp-parceiros"]
    end

    subgraph Backend["Backend unico (Docker / uvicorn)"]
        API["FastAPI app.main:app<br/>/api/v1/*"]
    end

    subgraph Dados["Dados"]
        PG[("PostgreSQL + pgvector<br/>schemas: public, calculators, landing_pages")]
        RD[("Redis<br/>cache exato / rate limit / throttle por e-mail")]
    end

    subgraph Externos["Servicos externos"]
        LLM["Anthropic - OpenAI - Google - Perplexity"]
        PHARMA["PharmaDB"]
        PUBMED["PubMed"]
        CURSE["Curseduca (SSO / membros)"]
        SG["SendGrid (e-mail / OTP)"]
        OBS["Sentry - Arize Phoenix"]
    end

    FA -- "cookie medico360_session ou Bearer JWT" --> API
    CA -- "cookie medico360_session ou Bearer JWT" --> API
    LF -- "POST /landing-pages/finance/submit (sem auth)" --> API
    LC -- "POST /landing-pages/accounting/submit (sem auth)" --> API
    LPP -- "POST /landing-pages/partners/submit (sem auth)" --> API
    API --> PG
    API --> RD
    API --> LLM
    API --> PHARMA
    API --> PUBMED
    API --> CURSE
    API --> SG
    API --> OBS
```

Pontos-chave:

- Nunca há chamada HTTP entre serviços internos — é sempre frontend → backend único.
- Banco físico único. Os schemas `calculators` e `landing_pages` são separação **lógica**, com FKs cruzando para o schema público (`users`, `company`, `interactions`).
- O CORS é montado no boot a partir de `frontend_url + calculadoras_url + embed_allowed_origins + landing_pages_origins` (`app/main.py:87-94`); fora de produção, cada origem também entra na variante `localhost`/`127.0.0.1`, que o browser trata como distintas.

---

## 3. Backend — stack e estrutura

### 3.1 Stack

- Python 3.12, FastAPI 0.141, SQLAlchemy 2.0 async (`asyncpg`), Alembic 1.14.
- `slowapi` (rate limiting sobre Redis), `httpx` (cliente compartilhado com pool), `sse-starlette`, `spaCy` `pt_core_news_sm` (NER do DLP), `pgvector`, `sendgrid`.
- Parsers de upload: `pdfplumber`, `python-docx`, `openpyxl`.
- Observabilidade: Sentry (`app/core/error_tracking.py`, com scrubbing de PII obrigatório) e OpenTelemetry/Arize Phoenix (`app/core/telemetry.py`).
- Imagem Docker única na raiz, servida por `uvicorn`.

### 3.2 Estrutura de pastas

```
app/
├── main.py            bootstrap FastAPI: logging → Sentry → Phoenix → http_client →
│                       warmup do NER → registry de fórmulas → tarefa de expurgo;
│                       CORS, GZip, RequestId, handler global de exceção
├── api/
│   ├── deps.py         get_current_user (Bearer JWT ou cookie de sessão)
│   └── v1/
│       ├── router.py    agrega todos os sub-routers sob /api/v1
│       └── endpoints/   auth, conversations, folders, agregador, orquestrador,
│                        uploads, usage, health, landing_pages, news, meta
├── calculators/         módulo self-contained das calculadoras
│   ├── engine/           motor de execução (coerção de campos, validação)
│   ├── formulas/         fórmulas por especialidade, auto-carregadas no boot
│   ├── registry/         mapa formula_key → função pura (@register_formula)
│   ├── repositories/     acesso ao schema `calculators`
│   ├── routers/          calculators_router.py, prevent_router.py
│   ├── schemas/          Pydantic de entrada/saída
│   ├── services/         execução + extração de campos via LLM
│   └── cache.py          cache in-process do catálogo (TTL 300s)
├── core/                config (Settings), database, limiter, circuit_breaker,
│                        http_client, logging_config, error_tracking, telemetry,
│                        prompts, alarme (evento operacional no Sentry)
├── medicina/            DOMINIO PURO — nao importa banco, HTTP nem config
│   ├── especialidades.py  vocabulario canonico do CFM (55), normalizacao,
│   │                      leitura dos grupos `[CFM]` da Curseduca
│   └── identidade.py      precedencia de escrita da especialidade e calculo
│                          das pendencias de perfil
├── news/                DOMINIO PURO — taxonomia de temas e lista de periodicos
├── middleware/          dlp.py (mascaramento de PII antes do LLM), ner.py (spaCy pt)
├── models/              models.py (public), calculators.py, landing_pages.py, news.py
├── repositories/        auth_repository.py
├── schemas/             agregador, auth, conversations, usage, landing_pages, news
└── services/
    ├── integracoes/     clientes de sistemas externos (ver 3.3)
    └── ...              servicos de dominio
```

**O padrão que emergiu, e que vale seguir em coisa nova:** `calculators/`, `news/` e
`medicina/` são fatias verticais — trazem o próprio domínio e não dependem de
infraestrutura. `app/services/` (32 arquivos, ~9.600 linhas) é o núcleo antigo,
organizado horizontalmente. Não há projeto para reorganizá-lo; a orientação é
**construir o novo como fatia e deixar o antigo encolher por atrito**.

### 3.3 Serviços — o que cada um faz

| Módulo | Responsabilidade |
|---|---|
| `orquestrador_service.py` | Pipeline não-streaming de `/orquestrador/query` |
| `orquestrador_stream_service.py` | Mesmo pipeline via SSE; abre sessão de banco própria |
| `orquestrador_shared.py` | Peças comuns aos dois: título, posse da conversa, clarificação, montagem de contexto, vínculo de anexos |
| `orquestrador_modes.py` | **Definição única** dos modos: enum, mapa modo→modelo, temperatura, cadeia de fallback, modos que exigem visão, teto de tokens por esforço |
| `triage_service.py` | Classificação da pergunta em um modo; atalho local para saudações |
| `agregador_service.py` | Consulta paralela a N modelos (produto legado, fora da UI) |
| `conversation_history.py` | Histórico lido do banco (nunca do cliente) |
| `context_budget.py` | Corte do histórico por orçamento de tokens estimado |
| `folder_context_service.py` | Contexto entre conversas da mesma pasta, por similaridade |
| `semantic_cache_service.py` | Cache semântico pgvector + fast-path exato no Redis |
| `cache_service.py` | Wrapper de Redis (get/set/throttle) |
| `file_extractor_service.py` | Validação, extração de texto e resolução de anexos |
| `medication_extractor.py` | Extrai fármacos mencionados na interação |
| `orquestrador_shared.py` (cont.) | `decidir_rota` — **as regras de roteamento vivem aqui**, não nos dois serviços |
| `response_metadata.py` | Serializa fontes/PubMed em `InteractionResponse.extra_metadata` |
| `specialty_detector.py` | Detecta especialidade/tópico da interação |
| `usage_service.py` | Limite semanal de custo por usuário |
| `pricing.py` | Preços por modelo, cache TTL 1h |
| `auth_service.py` | Login OTP/convite/embed + `reconciliar_especialidade_do_embed` (§3.4) |
| `news_feed_service.py` | Monta o feed por temas + palavras-chave; piso de especialidade |
| `news_tagger_service.py` / `news_writer_service.py` / `news_collector_service.py` | Pipeline PubMed → tema → texto em português |
| `news_digest_service.py` / `news_keyword_service.py` | Digest diário e palavras-chave do médico |
| `consent_service.py` / `data_subject_service.py` | Consentimento LGPD e exportação do titular |
| `expurgo_agendado.py` | Expurgo de retenção rodando dentro do processo |
| `vigilancia_service.py` | Mede cache, custo e última rodada de expurgo; `avaliar` decide o que vira alarme |
| `vigilancia_agendada.py` | Laço de 6h que roda as medições e alarma no Sentry |
| `email_service.py` | SendGrid |

**`services/integracoes/` — quem fala com o mundo de fora.** Separado porque todos
compartilham a mesma forma: timeout explícito, disjuntor (`app/core/circuit_breaker.py`)
e uma **decisão deliberada sobre o que fazer quando o outro lado não responde** — que
é diferente em cada um.

| Módulo | Sistema externo | Política de falha |
|---|---|---|
| `ai_providers.py` | Anthropic / OpenAI / Gemini / Perplexity + `DlpEnforcingProvider` | cadeia de fallback entre modelos |
| `curseduca_service.py` | API da Curseduca (validação de matrícula) | **fail-closed** — a dúvida é sobre direito de acesso |
| `pharmadb_service.py` | PharmaDB (bula, interação, receita, genérico) | degrada com aviso |
| `pubmed_service.py` / `pubmed_eutils.py` | PubMed (validação de citação, diretrizes) | degrada com aviso |
| `news_pubmed.py` | PubMed (coleta do feed) | pula a rodada |

### 3.4 Autenticação e identidade profissional

**Sessão.** `get_current_user` (`app/api/deps.py`) aceita `Authorization: Bearer <jwt>`
**ou** o cookie `medico360_session`; decodifica com `jwt_secret_key`, valida `sub` como
UUID e busca o `User` com `status=true`. O cookie é setado em `_set_session_cookie`
(`auth.py`) com `httponly`, `secure=is_production`, `samesite=lax`, `domain=COOKIE_DOMAIN`.
Todas as rotas exigem autenticação, exceto as marcadas "não" nas tabelas do §4.

**Como o médico entra.** Quatro caminhos: OTP por e-mail, convite, auto-cadastro
(desligado por padrão) e — o que importa na prática — **embed do LMS**
(`POST /auth/embed/token`). O LMS monta a URL do iframe com `?email=`; trocamos por um
JWT. O `?email=` não é identidade: a prova vem da validação server-to-server na API da
Curseduca, obrigatória em produção (o startup cai sem ela).

#### De onde vem a especialidade

A página de cadastro — **outro sistema, outro time** — coleta CRM e consulta o CFM, e
cria na Curseduca um grupo de acesso chamado `[CFM] <especialidade>` (ou
`[CFM] GENERALISTA`, quando o Conselho não devolve especialidade). O payload do membro
que já era baixado para validar a matrícula traz `name` e `groups`; **os dois eram
descartados**. Hoje `auth_service.reconciliar_especialidade_do_embed` os lê a cada login
de embed.

Quatro fontes podem escrever a especialidade, com precedência estrita
(`app/medicina/identidade.py`):

```
admin  >  cadastro  >  cfm  >  waid_grupo  >  declarado
```

`declarado` — o que o médico digita — fica no **fundo**, e isso é deliberado:
`users.specialty` não é preferência de leitura, é identidade profissional, e a intenção
é que passe a definir acesso a conteúdo pago. Se fosse editável pelo app, trocar de
especialidade alcançaria produto não contratado. O que o médico ajusta livremente é o que
ele **lê** (`news.user_topics`), não quem ele é. Correção só por suporte
(`PATCH /auth/admin/users/{id}/especialidade`, com `AuditLog`) — é o que sustenta a trava
perante o direito de correção da LGPD (art. 18, III).

Invariantes que o código protege, e que têm teste:

- **`[CFM] GENERALISTA` não vira "Clínica Médica".** Clínica Médica é especialidade real,
  com RQE; afirmá-la para quem o Conselho diz não ter nenhuma seria gravar registro falso.
  O generalista fica com `specialty` NULL — e o conteúdo dele é resolvido noutra camada,
  pelo `ESPECIALIDADE_PISO` do feed.
- **Duas residências são guardadas** (`users.specialties`, JSONB). Clínica Médica é
  pré-requisito de quase toda residência clínica; guardar só uma revogaria o acesso à
  outra. `specialty_slug` é só a principal, para exibição e prompt.
- **A reconciliação nunca derruba o login.** Enriquecer perfil é acessório; autenticar não.
- **Ela só roda em `/auth/embed/token`.** Quem reaproveita sessão não é enriquecido até o
  token expirar ou abrir outro app. É a explicação para "funcionou no segundo app e não no
  primeiro".

#### O onboarding

Uma tela só, em **`shared/onboarding/`**, importada pelos três apps. O servidor calcula
`onboarding_pendencias` (`identidade.pendencias`) e os apps **apenas renderizam** — nenhum
deles decide o que falta. É o que permite acrescentar uma exigência no backend e os três
herdarem; se cada um decidisse, uma regra nova viraria três divergências. Foi exatamente
assim que o repo acabou com três listas de especialidade incompatíveis.

Sobrou pouco a perguntar, porque quase tudo chega sozinho:

| Pendência | Por que ainda é perguntada |
|---|---|
| `med_status` | Nenhuma fonte distingue residente de especialista — o R1 aparece no CFM sem RQE, igual ao generalista |
| `aceite_termos` | Ninguém consente pelo titular. Fica aqui, e não na página de cadastro, porque a versão dos documentos (`consent_service.VERSAO_DOCUMENTOS`) é nossa |
| `nome`, `especialidade` | Só quando não chegaram do LMS |

**CRM não é pendência**, decisão de 2026-09-02: a prova de registro é o grupo `[CFM]`;
um número digitado à mão não acrescenta prova. A coluna existe e continua sendo gravada
de fonte confiável.

Comportamento por app: `frontend-app` e `noticias-app` **bloqueiam** (no segundo, o perfil
define o que ele vai ler); `calculadoras-app` só **avisa**, e só sobre o aceite — não
filtra nada por especialidade, então cobrar o perfil ali prometendo "conteúdo da sua
especialidade" seria prometer o que aquele app não entrega.

---

## 4. Rotas

### 4.1 `/auth` (`app/api/v1/endpoints/auth.py`)

| Método | Path | Auth | Rate limit | Descrição |
|---|---|---|---|---|
| POST | /api/v1/auth/register | não | 5/min | Cadastro público (se `allow_public_registration`); envia convite por e-mail |
| POST | /api/v1/auth/invite/generate | sim (admin) | 30/min | Gera token de convite; grava `AuditLog action=invite.generate` |
| POST | /api/v1/auth/invite/accept | não | 10/min | Aceita convite por token+e-mail; seta cookie SSO |
| POST | /api/v1/auth/embed/token | não | 5/min | SSO para embeds; valida `Origin` e o membro via Curseduca; cria usuário se necessário; **reconcilia nome e especialidade** (§3.4) |
| POST | /api/v1/auth/otp/request | não | 3/15min (+3/900s por e-mail) | Solicita OTP por e-mail |
| POST | /api/v1/auth/otp/verify | não | 5/min (+10/900s por e-mail) | Verifica OTP; seta cookie SSO |
| POST | /api/v1/auth/onboarding | sim | 30/min | Aplica o que veio e o SERVIDOR decide se acabou; consentimento na mesma transação |
| GET | /api/v1/auth/me | sim | — | Usuário logado + `onboarding_pendencias`, `med_status_opcoes`, `specialty_editavel` |
| PATCH | /api/v1/auth/me | sim | 30/min | Nome, e-mail, CRM+UF e especialidade — esta última só se `specialty_editavel` (senão 409) |
| PATCH | /api/v1/auth/admin/users/{id}/especialidade | sim (admin) | 30/min | Correção pelo suporte, com `AuditLog`. É o que sustenta a trava do §3.4 perante a LGPD |
| GET | /api/v1/auth/me/consentimentos | sim | — | Situação dos consentimentos LGPD + versão vigente |
| POST | /api/v1/auth/me/consentimentos/{tipo}/revogar | sim | 10/h | Revoga consentimento (exceto `termos_e_privacidade`) |
| GET | /api/v1/auth/me/export | sim | 5/h | Portabilidade LGPD art. 18, V |
| DELETE | /api/v1/auth/me | sim | 10/min | Exclusão de conta em cascata (a cascata vive em `auth_repository`) |

> Os números de linha saíram desta tabela de propósito: envelheciam a cada edição do
> arquivo e já apontavam para o lugar errado. O nome da função é âncora melhor.

### 4.1-A `/meta` (`app/api/v1/endpoints/meta.py`)

| Método | Path | Auth | Descrição |
|---|---|---|---|
| GET | /api/v1/meta/especialidades | **não** | As 55 especialidades canônicas (`{slug, nome}`), `Cache-Control: 1h` |

Público porque a tela de cadastro precisa da lista **antes** de existir sessão. Exigir
token aqui devolveria a lista para dentro do TSX, que é o que este trabalho desfez.

### 4.2 `/orquestrador` (`app/api/v1/endpoints/orquestrador.py`)

| Método | Path | Linha | Rate limit | Descrição |
|---|---|---|---|---|
| POST | /api/v1/orquestrador/query | 74 | 30/min | Triagem + roteamento, resposta completa |
| POST | /api/v1/orquestrador/stream | 118 | 30/min | Mesmo pipeline via SSE. Não atende `PHARMA_CHECK` — use `/query` |

Body `OrquestradorRequest` (`orquestrador.py:21-72`):

| Campo | Tipo | Nota |
|---|---|---|
| `prompt` | str (1–4000) | obrigatório |
| `conversation_id` | UUID? | ausente = cria conversa nova |
| `force` | bool | pula a etapa de clarificação |
| `clarification_answers` | str? | respostas às perguntas de clarificação |
| `effort` | `rápido` \| `detalhado` | teto de tokens de saída (700 / 4096) |
| `mode` | str? | modo explícito; pula a triagem automática |
| `folder_id` | UUID? | pasta da nova conversa |
| `file_id` | UUID? | **deprecado** — tratado como lista de um |
| `file_ids` | UUID[] | até 5 anexos por mensagem |

O campo `history` **não existe mais**: o servidor lê o histórico do banco.

Eventos SSE de `/stream`: `start` · `cache_hit` · `clarification` · `token` · `text_done` · `done` · `error`. `text_done` existe para o cliente liberar a digitação sem esperar o pós-processamento (PubMed, custo, specialty), que sai no `done`.

### 4.3 `/agregador` (produto legado, fora da UI)

| Método | Path | Linha | Rate limit | Descrição |
|---|---|---|---|---|
| GET | /api/v1/agregador/models | 45 | — | Modelos ativos, com disponibilidade derivada da chave configurada e `cost_tier` |
| POST | /api/v1/agregador/query | 93 | 30/min | Consulta a N modelos em paralelo (`MAX_MODELS_PER_QUERY`) |
| POST | /api/v1/agregador/stream | 123 | 30/min | SSE multi-modelo; eventos `delta`/`complete`/`error`/`pubmed`/`disclaimer`/`done` |
| GET | /api/v1/agregador/history | 292 | — | Histórico pesquisável por query/modelo/data |

### 4.4 `/conversations` e `/folders`

| Método | Path | Arquivo:linha | Rate limit | Descrição |
|---|---|---|---|---|
| GET | /api/v1/conversations | conversations.py:23 | 60/min | Conversas ativas do usuário, paginadas, `updated_at desc` |
| GET | /api/v1/conversations/{id} | conversations.py:42 | 60/min | Detalhe + mensagens; devolve anexos, citações e validação PubMed por mensagem |
| GET | /api/v1/folders | folders.py:34 | 60/min | Lista pastas |
| POST | /api/v1/folders | folders.py:49 | 30/min | Cria |
| PUT | /api/v1/folders/{id} | folders.py:65 | 30/min | Renomeia |
| DELETE | /api/v1/folders/{id} | folders.py:86 | 30/min | Apaga (conversas ficam sem pasta, `SET NULL`) |
| PATCH | /api/v1/folders/conversations/{id}/folder | folders.py:104 | 60/min | Move 1 conversa |
| PATCH | /api/v1/folders/conversations/bulk | folders.py:134 | 30/min | Move até 100 conversas |

`ConversationDetail` (`app/schemas/conversations.py:69`) carrega `messages[]` com `role`, `content`, `attachments[]`, `mode`, `citations[]` e `pubmed_validation` — é o que permite a conversa reabrir com as fontes intactas.

### 4.5 `/uploads`

| Método | Path | Linha | Rate limit | Descrição |
|---|---|---|---|---|
| POST | /api/v1/uploads/extract | 45 | 20/min | Valida content-type **e** magic bytes; extrai texto em thread; imagem vira descrição via Claude Haiku (custo cobrado); trunca em `MAX_EXTRACTED_CHARS`; grava `FileExtraction`; devolve `file_id` e um `warning` opcional |

Limites (`app/services/file_extractor_service.py:36-46`): 10 MB por arquivo (5 MB para imagem, limite do base64 da Anthropic), 50 000 caracteres extraídos, 100 páginas de PDF, 20 000 parágrafos/linhas de tabela DOCX, 50 000 linhas XLSX, 200 MB descompactados (proteção contra zip-bomb), 5 anexos por mensagem.

O `warning` é deliberado: um PDF digitalizado sem OCR não faz o upload falhar — o médico pode ter motivo para anexar assim — mas ele precisa saber que o conteúdo não chegou ao modelo (`docs/debitos.md`, item 2).

### 4.6 `/calculators` e `/prevent`

| Método | Path | Arquivo:linha | Rate limit | Descrição |
|---|---|---|---|---|
| GET | /api/v1/calculators | calculators_router.py:23 | 60/min | Lista, filtro opcional por especialidade |
| GET | /api/v1/calculators/{slug} | calculators_router.py:34 | 60/min | Detalhe (campos, versão ativa) |
| POST | /api/v1/calculators/{slug}/execute | calculators_router.py:45 | 60/min | Executa (`inputs`, `dry_run` opcional) |
| POST | /api/v1/calculators/{slug}/extract | calculators_router.py:64 | 30/min | Extrai campos de texto livre via LLM |
| PUT / DELETE | /api/v1/calculators/{slug}/favorite | calculators_router.py:88 / :99 | 60/min | (Des)favorita |
| GET | /api/v1/calculators/{slug}/history | calculators_router.py:110 | 60/min | Histórico de execuções do usuário |
| POST | /api/v1/prevent/calculate | prevent_router.py:12 | 60/min | Escore PREVENT (AHA, Khan et al. 2024), seis desfechos. **Sem estado**: não grava execução nem audit log |

O PREVENT é um caso à parte de propósito: campos fora da faixa de validade voltam `None` desfecho a desfecho, seguindo `AHAprevent::pred_risk_base` — a AHA invalida por desfecho, não em bloco. Onde a AHA diverge do MDCalc, o projeto segue a AHA; as faixas vivem em `_REGRAS` dentro de `app/calculators/formulas/cardiologia/prevent.py`.

### 4.7 `/landing-pages`

| Método | Path | Linha | Auth | Rate limit | Descrição |
|---|---|---|---|---|---|
| GET | /api/v1/landing-pages/{slug}/check | 62 | não | 60/min | `already_submitted` por e-mail; `slug` validado contra a lista fixa `ALLOWED_SLUGS` |
| POST | /api/v1/landing-pages/finance/submit | 75 | não | 20/min | 409 se já houver submissão com o mesmo e-mail |
| POST | /api/v1/landing-pages/accounting/submit | 108 | não | 20/min | Idem + seleções de dor (1:N) |
| POST | /api/v1/landing-pages/partners/submit | 148 | não | 20/min | Idem + categorias (1:N) |
| POST | /api/v1/landing-pages/calculators/submit | 185 | **sim** | 20/min | Pedido de calculadora nova, feito de dentro do módulo logado — identidade vem da conta, não do body; 409 por `user_id` |

O bloqueio por e-mail só se aplica quando o e-mail veio na URL (embed do fornecedor): sem e-mail não há como identificar reenvio, e a submissão segue permitida.

### 4.8 `/news`

Ver §7-A.4 — a tabela completa está lá, junto do contexto do módulo.

### 4.9 `/users/usage` e `/health`

| Método | Path | Arquivo:linha | Auth | Descrição |
|---|---|---|---|---|
| GET | /api/v1/users/usage | usage.py:12 | sim | Uso/limite semanal |
| GET | /api/v1/health | health.py:33 | não | Liveness pura — não toca dependência nenhuma |
| GET | /api/v1/health/ready | health.py:63 | não | Readiness: Postgres (`SELECT 1`) e Redis (`ping`) em paralelo, timeout 3s cada; 503 se algo falhar |

---

## 5. Pipeline do Orquestrador

É o coração do produto. `/query` e `/stream` seguem o mesmo caminho; o que é comum vive em `orquestrador_shared.py` (os dois serviços nasceram como cópias e já tinham divergido — um chegou a importar função privada do outro).

```mermaid
flowchart TD
    A["prompt + anexos"] --> B["resolve_files_context<br/>ate 5 anexos: texto + imagens"]
    B --> C{"clarification_answers?"}
    C -- sim --> D["resolve_clarification_prompt<br/>recompoe prompt original + respostas"]
    C -- nao --> E
    D --> E["DLP: sanitize_prompt_async<br/>nomes, CPF/RG/SUS, contato, endereco"]
    E --> F{"saudacao sem<br/>conteudo clinico?"}
    F -- sim --> G["OFF_TOPIC: resposta local<br/>zero chamada de modelo"]
    F -- nao --> H["Contexto: historico do banco<br/>+ trechos da pasta, dentro do orcamento"]
    H --> I{"mode explicito?"}
    I -- nao --> J["triage()"]
    I -- sim --> K
    J --> K["modo resolvido<br/>anexo promove CLINICAL_REASONING para EXAM_REVIEW"]
    K --> L{"CLINICAL_REASONING,<br/>sem force?"}
    L -- sim --> M["check_clarification<br/>evento clarification, encerra"]
    L -- nao --> N["Cache semantico<br/>Redis exato, depois pgvector"]
    N -- HIT --> O["cache_hit: resposta pronta"]
    N -- MISS --> P{"modo"}
    P -- "PHARMA_*" --> Q["PharmaDB"]
    P -- "outros" --> R["Provider do modo<br/>+ cadeia de fallback"]
    R --> S["tokens, depois text_done"]
    S --> T["pos-processamento em background:<br/>PubMed, specialty, medicacoes, custo, audit"]
    T --> U["done"]
```

### 5.1 Roteamento por modo (`app/services/orquestrador_modes.py`)

| Modo | Modelo primário | Fallback | Temp. |
|---|---|---|---|
| `QUICK_SEARCH` | `sonar-pro` (Perplexity) | `gemini-2.5-flash` | 0.0 |
| `CLINICAL_REASONING` | `claude-sonnet-4-6` | `gpt-4o` → `gemini-2.5-flash` | 0.0 |
| `EXAM_REVIEW` | `claude-sonnet-4-6` | `gpt-4o` → `gemini-2.5-flash` (todos com visão) | 0.0 |
| `PRODUCTIVITY` | `gpt-5.4-nano` | `gemini-2.5-flash` | 0.7 |
| `PHARMA_CHECK` / `PHARMA_BULA` / `PHARMA_RECEITA` / `PHARMA_GENERICO` | PharmaDB (sem LLM) | — | — |
| `OFF_TOPIC` | atalho local | — | — |

Detalhes que não são óbvios:

- **`EXAM_REVIEW` só pode cair em modelo com visão** (`MODES_REQUIRING_VISION`). Rotear para Perplexity entregaria ao médico uma leitura de exame feita sem o exame — baseada só na descrição textual gerada por outro modelo, sem ele saber.
- **A promoção `CLINICAL_REASONING → EXAM_REVIEW` acontece por anexo, não por triagem** (`upgrade_mode_for_attachments`). A triagem só vê o texto; "o que você acha disso?" com uma tomografia junto e a mesma frase sem anexo pedem modos diferentes. Um modo escolhido explicitamente na interface **nunca** é promovido. Anexar um documento e pedir "resuma isto" continua sendo `PRODUCTIVITY`.
- **`PHARMA_CHECK` exige confiança ≥ 0.90** (`PHARMA_CHECK_MIN_CONFIDENCE`). Um modo explícito ainda passa pela triagem, para resolver o sub-modo (bula / receita / genérico / interação), mas ignora o gate de confiança.
- **`ModeEnum` em `app/models/models.py` NÃO é a fonte dos modos** — é resíduo do ERD original (BIZU, SHERLOCK, FARMACIA…), com valores que nunca corresponderam aos modos reais e que nenhum código do orquestrador lê. Mexer nele é mudança de schema, não de serviço.
- O toggle Rápido/Detalhado só limita o tamanho da resposta (`EFFORT_MAX_TOKENS`: 700 / 4096) — o que reduz tempo de geração e custo de saída.

### 5.2 DLP

`app/middleware/dlp.py` + `ner.py` (RN-SEC-001). Mascara antes de qualquer envio externo: nomes com palavra-gatilho → `[PACIENTE]`/`[MÉDICO]` (regex), nomes sem gatilho → `[NOME]` (NER spaCy), CPF/RG/Cartão SUS → `[DOCUMENTO]`, telefone/e-mail → `[CONTATO]`, endereço → `[ENDEREÇO]`.

Não há re-identificação: o placeholder vai ao modelo e volta no texto. Um falso positivo apaga o termo em definitivo — por isso o passo de NER é conservador, e os filtros anti-epônimo em `ner._is_person` existem por medição real. **Não simplifique sem ler a justificativa.** `DlpEnforcingProvider` (`ai_providers.py:721`) é a rede de segurança: envolve o provider e recusa o envio se o texto não passou pela sanitização.

O modelo de NER é carregado no boot (`ner.warmup()`), fora do caminho da primeira requisição — custava ~1s ao primeiro usuário.

---

## 6. Contexto e memória

### 6.1 Histórico vem do banco, não do cliente

`app/services/conversation_history.py`. Antes o histórico chegava no corpo da requisição. Duas consequências: o servidor mandava ao modelo — e cobrava do usuário — um texto que nunca verificou (um cliente podia afirmar qualquer coisa como "dito anteriormente pelo assistente"); e o que o médico via na tela podia divergir do que o modelo recebia. Lê no máximo `MAX_INTERACTIONS_LIDAS = 40` interações.

Os turnos viram papéis de verdade (`user`/`assistant`), não um bloco de texto achatado com rótulos dentro — o modelo distinguia quem falou o quê por um rótulo textual, que ele podia ignorar ou confundir com conteúdo.

### 6.2 Orçamento por tokens

`app/services/context_budget.py`. `DEFAULT_HISTORY_TOKEN_BUDGET = 6000`, `CHARS_PER_TOKEN = 3.2` (medido contra dados reais em 2026-08-27), `TOKEN_OVERHEAD_POR_MENSAGEM = 4`.

A contagem é estimativa de propósito: `tiktoken` só vale para OpenAI e o projeto fala com quatro provedores. **Errar para menos é inofensivo aqui** — o orçamento está muito abaixo da janela de qualquer modelo em uso (200k no Sonnet); ele é controle de custo e de ruído, não proteção contra limite técnico. Isso inverte a intuição comum sobre contagem de tokens, e é por isso que a razão é calibrada pela mediana e não por um percentil pessimista.

### 6.3 Pastas como projetos

`app/services/folder_context_service.py` + tabela `message_embeddings`. Uma conversa dentro de uma pasta pode usar as **outras** conversas daquela pasta como contexto, recuperadas sob demanda por similaridade (`text-embedding-3-small`, 1536 dims, `SIMILARITY_FLOOR = 0.25`, até 4 trechos de 2000 caracteres).

Por que não injetar a pasta inteira: uma pasta de acompanhamento acumula dezenas de conversas — estouraria a janela, subiria o custo sem teto e afogaria o caso atual em ruído de casos parecidos.

**A garantia que mais importa é o isolamento.** A busca cruza conversas — exatamente o tipo de recurso que vaza dado de um paciente para a discussão de outro se o filtro estiver frouxo. Todo caminho de leitura filtra por `user_id` **e** `folder_id`; `user_id` é denormalizado em `message_embeddings` para que o filtro não dependa de um JOIN que alguém possa esquecer de escrever. Teste dedicado: `tests/test_folder_context.py`.

O bloco da pasta entra **antes** do histórico próprio, como turno de usuário: é pano de fundo, não a última coisa dita. E disputa o mesmo orçamento — se a conversa própria for longa, ela ganha o espaço, que é o comportamento certo (o caso atual vale mais que casos vizinhos).

A indexação é agendada fora do caminho da resposta (`agendar_indexacao`), até `MAX_INDEXAR_POR_VEZ = 60` trechos por vez.

### 6.4 Cache semântico

`app/services/semantic_cache_service.py`. Pipeline: guardrail + normalização por LLM (expande siglas: PAC → pneumonia adquirida na comunidade) → embedding → fast-path exato no Redis (TTL 30 dias) → busca cosine no pgvector (`SIMILARITY_THRESHOLD = 0.88`, TTL 30 dias).

`QUICK_SEARCH` é sempre cacheável se o guardrail passar; `CLINICAL_REASONING` só sem dados de paciente específico.

A chave de cache usa o **prompt atual sem histórico** — separação deliberada, senão cada conversa teria chave própria e o cache nunca acertaria.

**Histórico de defeito, vale conhecer:** o cache ficou desligado em silêncio desde sempre. `_normalize_prompt` mandava `max_tokens`, que a família gpt-5 recusa com HTTP 400, e toda escrita era pulada sem erro visível. Corrigido em `f31dd2c`. Com a tabela ainda vazia, a migration `003` aproveitou para trocar o índice ivfflat por HNSW: ivfflat calcula os centroides no momento da criação, e o índice do baseline nasceu sobre uma tabela vazia — recall degradado até alguém lembrar de reindexar, e `lists = 100` dimensionado para ~10 000 linhas que a tabela nunca teve. HNSW constrói o grafo incrementalmente e some com a classe inteira de bug. Há um script de medição: `scripts/medir_cache_semantico.py`.

---

## 7. Calculadoras

Módulo self-contained (`app/calculators/`), com contrato próprio em `docs/Calculadoras_Cientificas_Regras_de_Arquitetura_v1.0.md`.

- **Definição em dados, execução em código.** `calculator_definitions` / `calculator_fields` / `calculator_versions` vivem no banco (populados por seeds); a `formula_key` da versão ativa aponta para uma função pura registrada via `@register_formula` no `registry`.
- **Fail-fast no boot**: `load_all_formulas()` roda no lifespan e importa todos os módulos de fórmula. Uma `formula_key` órfã derruba o startup, não a primeira execução clínica em produção.
- **Uma versão ativa por calculadora**, garantido por índice único parcial no banco (§11.3).
- Fórmulas em Python hoje: CHA₂DS₂-VASc + HAS-BLED, Cockcroft-Gault, CURB-65, PREVENT.
- O **Risco CV SBC 2025** é um caso especial: a fórmula em Python foi removida e o wizard passou a viver no frontend (`calculadoras-app/src/calculators/riscoCv/`), consumindo `/prevent/calculate` para a parte quantitativa. A definição continua no banco (seed `seed_risco_cv_sbc2025`) e o E2E cobre o fluxo.

---

## 7-A. Notícias

Feed clínico por tema. Migrou de um repositório separado (`medico360-news`); o schema
`news` entra na cadeia de migrations desde a `004`.

### 7-A.1 O pipeline

```
PubMed  →  collector  →  tagger  →  writer  →  published
           (coleta)      (temas)   (reescreve em pt)
```

`app/services/news_collector_service.py` busca por ISSN dos periódicos listados em
`app/news/journals.py`; `news_tagger_service.py` classifica cada artigo contra o
**vocabulário fechado** de `app/news/taxonomia.py` (51 temas) — slug fora da lista é
descartado com WARNING; `news_writer_service.py` reescreve em português.

### 7-A.2 Dois eixos de personalização, de propósito

| Eixo | Casa contra | Por quê |
|---|---|---|
| **Temas** (`news.user_topics`) | o que o tagger atribuiu | vocabulário controlado, curado |
| **Palavras-chave** (`news.user_keywords`) | o TEXTO do artigo (`busca_tsv`) | o médico digita o que quiser |

Palavra-chave **não podia ser "mais um tema"**: o tagger escolhe de uma lista fechada, e
um tema criado pelo usuário nunca estaria nela — ele veria o tema marcado na tela e
receberia zero destaques para sempre, sem erro e sem log. Os pesos do `tsvector` (`A` no
título, `B` no corpo) são o que separa "artigo SOBRE amiloidose" de "artigo que menciona
amiloidose uma vez".

### 7-A.3 O papel da especialidade

`news.topic_specialties` liga tema ↔ especialidade com peso (`core` / `relevante`) e casa
**por rótulo**, não por FK — daí a regra 8 do §17. A especialidade do médico:

- **pré-marca** os temas na primeira visita (`temas_sugeridos_para`), usando **todas** as
  especialidades dele (`users.specialties`);
- **preenche** o feed quando ele tem poucos itens, com temas da área que ele não marcou
  (`preenchimento=True` — e esses **nunca** disparam o digest por e-mail: completar a tela
  é cortesia de navegação, não motivo para interromper alguém);
- **não decide nada depois disso.** O que ele escolheu manda.

`ESPECIALIDADE_PISO = "Clínica Médica"` atende quem não tem especialidade — o embed cria
usuário só com e-mail. O piso **não filtra por peso**, porque nenhum tema é `core` de
Clínica Médica; exigir `core` ali devolveria lista vazia. Toda vez que ele é acionado sai
`news.piso_especialidade` no log: **essa contagem é a métrica de sucesso do trabalho de
identidade do §3.4.**

### 7-A.4 Rotas (`/api/v1/news`, todas autenticadas)

| Rota | O que faz |
|---|---|
| `GET /news/highlights` | O feed montado (temas + palavras-chave + preenchimento) |
| `GET /news/articles/{id}` | Um destaque |
| `GET` / `PUT /news/me/topics` | Temas escolhidos; o GET traz os sugeridos e a especialidade |
| `GET` / `POST` / `DELETE /news/me/keywords` | Palavras-chave |
| `GET /news/keywords/preview` | Quantos destaques um termo traria **antes** de salvar |
| `GET` / `POST /news/favorites` | Favoritos |
| `POST /news/feedback/nao-interessa` | Registra desinteresse, com a especialidade do momento |
| `GET` / `PUT /news/me/preferences` | E-mail do digest |
| `POST /news/admin/pipeline` | Dispara o pipeline (admin) |

---

## 8. Landing pages

Schema `landing_pages` no mesmo banco. Modelagem: catálogo (`landing_pages`) → submissão comum (`submissions`) → resposta tipada por LP (`finance_answers`, `accounting_answers`, `partner_answers`) ou seleção 1:N (`benefit_selections`, `calculator_selections`, `accounting_pain_selections`, `partner_category_selections`).

`submissions.user_id` → `public.users` (`SET NULL`) liga a submissão ao usuário logado quando ela vem de dentro do produto. `email_missing` marca explicitamente a submissão sem e-mail vindo da URL — distinguir "não informou" de "não veio no embed" importa para a análise. `notify_on_availability` guarda o "quero ser avisado quando disponível".

Os três apps de LP são React 19 + Vite + Tailwind 4 + shadcn/ui, cada um com `railway.json` e `nixpacks.toml` próprios, servidos por `npx serve dist`.

---

## 9. LGPD, segurança e vigilância

| Mecanismo | Onde | Nota |
|---|---|---|
| DLP antes do LLM | `app/middleware/dlp.py`, `ner.py`, `DlpEnforcingProvider` | RN-SEC-001; sem re-identificação |
| Consentimento | `consent_service.py`, tabela `consent_logs` | Registrado com IP e user-agent; `termos_e_privacidade` não é revogável |
| Portabilidade (art. 18, V) | `data_subject_service.py`, `GET /auth/me/export` | 5/h |
| Exclusão de conta | `DELETE /auth/me` | Cascata sobre conversas, interações, alertas, preferências |
| Expurgo de retenção (art. 16) | `expurgo_agendado.py` | Roda **dentro do backend**, a cada 24h, 90s após o boot; grava `audit_logs.action='expurgo.rodada'` |
| Vigilância de garantias | `vigilancia_agendada.py` | Laço de 6h: alarma se o cache parou de gravar, se o custo triplicou ou se o expurgo não roda |
| Scrubbing de PII no Sentry | `app/core/error_tracking.py` | Obrigatório e testado — sem ele o prompt clínico bruto sai em cada evento, inclusive nos frames do stack trace |
| Fail-closed em produção | `config._validate_production_secrets` | Ver §12 |
| Rate limiting | `slowapi` + throttle por e-mail no Redis | OTP tem os dois |
| Autorização / IDOR | `tests/test_authorization.py`, `test_idor.py`, `test_calculadoras_isolamento.py` | A política das rotas está declarada em teste |

Sobre o expurgo estar no processo em vez de num cron: o agendamento vivia no painel do Railway — fora do repositório, invisível a testes, CI e code review. Parou de rodar e ninguém soube por 39 dias; o código continuava correto e a suíte verde, só o dado vencido acumulava. Trocar um cron por outro resolveria a instância, não a classe. Como código, ele aparece no diff, tem teste, e não some sem o backend cair junto. Com várias réplicas todas rodam o expurgo, o que é inofensivo (operação idempotente e barata); há alarme no Sentry quando o expurgo atrasa mais de `ATRASO_TOLERADO_DIAS = 2`.

### 9.1 Observabilidade

Três camadas, com papéis distintos:

| Camada | Ferramenta | Responde a |
|---|---|---|
| Erro | Sentry (`core/error_tracking.py`) | "o que estourou, e em qual requisição?" |
| Trace de LLM | Arize Phoenix (`core/telemetry.py`) | "o que foi mandado ao modelo, com quantos tokens?" |
| Log | JSON estruturado (`core/logging_config.py`) | "o que aconteceu antes disso?" |

O que costura as três é o **`request_id`**: aceito do proxy se vier, gerado se não, propagado por `ContextVar` para qualquer `logger` da pilha, carimbado como tag no Sentry e devolvido no header `X-Request-ID`. Dado um erro, dá para reconstruir a requisição inteira atravessando as camadas.

Os spans do Phoenix são escritos **à mão**, seguindo o schema OpenInference: o projeto chama os providers via `httpx` direto, sem SDK oficial, então os auto-instrumentors não enxergam nada.

O log nunca carrega conteúdo de prompt, texto extraído de arquivo ou e-mail. Correlação se faz por id, não por dado de paciente.

### 9.2 Vigilância — por que instrumentar não bastou

As três camadas acima observam **requisições**. Nenhuma delas observa **garantias que param de valer sem ninguém errar**.

Foi assim que o cache semântico ficou meses sem gravar uma linha. O detalhe que dói: `interactions.cache_hit` é gravado em toda interação desde sempre, e um `SELECT avg(cache_hit::int)` teria devolvido zero a qualquer momento. Não faltou instrumentação — faltou alguém perguntando.

`vigilancia_agendada.py` é a pergunta, feita a cada 6h pelo próprio backend:

| Alarme | Dispara quando | Por que o limiar é esse |
|---|---|---|
| `cache_semantico_sem_escrita` | ≥50 interações elegíveis em 7d **e** zero entradas vigentes | Abaixo de 50, "tabela vazia" não se distingue de "ninguém perguntou nada cacheável" |
| `custo_escalando` | Custo de 7d ≥3x o dos 7d anteriores, base ≥US$ 5 | 3x é grosseiro de propósito: pega laço de retry e abuso, não crescimento de produto |
| `expurgo_parado` / `expurgo_sem_rastro` | Sem rodada registrada em `audit_logs` há >2 dias, ou nunca | Complementa o alarme de dentro do expurgo: aquele dispara quando a rodada acontece e acha atraso; estes, quando ela não acontece |

Três decisões de desenho que valem conhecer antes de mexer:

- **Medir e decidir são coisas separadas.** `medir_*` só lê o banco; `avaliar` é função pura que recebe números e devolve alarmes. Isso permite testar todo limiar sem banco, e permite que `scripts/verificar_vigilancia.py` mostre as mesmas medições sem disparar nada — mesmo motivo pelo qual `verificar_expurgo.py` reusa `medir_passivo`.
- **Um alarme por tag por dia** (`SILENCIO_POR_TAG_HORAS`). Uma condição que persiste renderia quatro eventos diários e ensinaria o time a arquivar sem ler — o mecanismo exato pelo qual um alarme deixa de proteger qualquer coisa. O registro é em memória e some no deploy, de propósito: depois de um deploy você quer saber de novo.
- **Ordem de boot é uma dependência real.** `vigilancia_agendada.ATRASO_INICIAL_SEGUNDOS` (900s) precisa ser maior que o do expurgo (90s), senão todo boot de banco novo alarma `expurgo_sem_rastro`. Só um teste protege isso (`test_vigilancia_roda_depois_do_expurgo_no_boot`).

**O limite honesto:** este laço não vigia a si mesmo. Se a tarefa morrer, nada avisa. É um degrau a menos de silêncio, não zero — e o degrau restante é o processo, que já é observado de fora por `/health/ready`, de um jeito que um cron externo nunca foi.

---

## 10. Frontends

### 10.1 `frontend-app/` — Orquestrador

React 19 + Vite 8 + React Router 7 + TanStack Query + `react-markdown`/`remark-gfm`/`rehype-sanitize`. Testes com Vitest + Testing Library + jsdom.

```
src/
├── App.tsx, main.tsx     rotas: /cadastro /login /invite /onboarding /embed-auth /
├── api/                  agregador, auth, conversations, folders, orquestrador, uploads, usage
├── components/           ChatView, InputBar, ModelSelector, Sidebar, Topbar,
│                         ClarificationPrompt, ModeChip/ModeIntro, ProfileModal, EmptyState
│   └── sidebar/           ConvItem, DropZoneNoPasta, FolderRow, groupByDate
├── hooks/                 useIsMobile
├── lib/                   auth, useCurrentUser, useUserUsage, appModes, documentos,
│                          enterParaEnviar, intercom/IntercomIdentity, modelDescriptions, styles
├── pages/                 EmbedAuth, Invite, Login, Onboarding, Register
└── test/                  setup, utils, harness.test.tsx
```

Testes: `App.streaming`, `App.pasta`, `App.agregador-oculto`, `InputBar` (+ anexos, aviso), `Sidebar`, `harness`.

Comportamentos de UI com razão de ser documentada: Enter envia / Shift+Enter quebra linha (`lib/enterParaEnviar.ts`); a sidebar abre colapsada, expande no hover e fixa no clique; o Agregador foi retirado de `APP_MODES` mas o tipo `AppMode` mantém `'agregador'` porque conversas gravadas ainda carregam `feature: 'AGREGADOR'` e precisam ser reconhecidas para serem filtradas.

### 10.2 `calculadoras-app/`

React 19 + Vite, mesmo padrão de deploy. E2E com Playwright.

```
src/
├── App.tsx               rotas: /login /embed-auth / /calculadoras/risco-cv-sbc2025 /calculadoras/:slug
├── api/                   auth, calculators, prevent
├── calculators/           formSpecs registrados por side-effect import (index.ts):
│                          cockcroftGault, cha2ds2vaschHasbled, curb65
│   └── riscoCv/            wizard dedicado do risco CV: RiskCalculator, StepIndicator,
│       └── steps/          RiscoCvResultDashboard, visibility.ts, riskGoals.ts,
│                           steps: Triagem, Diabetes, Agravantes, AltoRisco, Prevent
├── components/            AiPrefillBox/Section, CalculatorCard, CalculatorTopbar,
│                          DynamicCalculatorForm, FieldWidget, GenericResultPanel,
│                          ResultPanel, WizardStepper, RequestCalculatorModal
├── hooks/                 useCalculatorDetail, useCalculators, useExecuteCalculator,
│                          useExtractFields, useFavorites, usePreventCalculator
├── lib/                   auth, specialtyStyles, useCurrentUser
└── pages/                 CalculatorsList, EmbedAuth, GenericCalculator, Login, RiscoCvSbc2025
e2e/                       risco-cv-sbc2025.spec.ts + helpers (auth, wizard)
```

Duas formas de calculadora: **genérica**, um `formSpec` declarativo renderizado por `DynamicCalculatorForm`; e **com wizard próprio**, uma página dedicada. `RequestCalculatorModal` é a ponte para `/landing-pages/calculators/submit`.

### 10.3 `noticias-app/`

React 19 + Vite, **sem React Router e sem design tokens** — é o mais enxuto dos três.
Duas telas: `TemasPage` (escolha de temas, com amostra real de conteúdo em cada um) e
`HighlightsMagazine` (o feed). O estado é uma máquina de quatro fases
(`carregando | erro | temas | feed`) no próprio `App.tsx`.

É o único que guarda o **dono do token** (`medico360_noticias_email` + `tokenPertenceA`):
em navegador compartilhado — estação de clínica, plantão — o `?email=` do LMS muda mas o
token antigo continua no `localStorage`, e o segundo médico herdaria a sessão do primeiro.
`frontend-app` e `calculadoras-app` **não têm essa proteção**.

### 10.4 `shared/` — código comum aos três apps autenticados

Na raiz do monorepo, fora das pastas de app. Hoje só o onboarding
(`shared/onboarding/`), importado via alias `@shared`.

Não é workspace npm — introduzir workspaces arrastaria build, CI e Dockerfile dos três de
uma vez. É alias de Vite + `paths` no tsconfig. Duas consequências que travaram o deploy e
estão resolvidas, mas convém conhecer antes de mexer:

- **TypeScript não acha o React a partir de `shared/`** (ele fica fora do `node_modules`
  de cada app): daí o `paths` para `@types/react` no `tsconfig.app.json` dos três.
- **Vite também não**, em runtime: daí `resolve.dedupe: ['react','react-dom']` no
  `vite.config.ts` dos três — que de quebra garante uma cópia só do React, já que duas
  quebrariam os hooks.

O componente é **autossuficiente por necessidade**: traz a própria paleta (cópia do
`:root` do `frontend-app`) e a própria fonte, porque o `noticias-app` não define variável
de CSS nenhuma. Se o `:root` daquele app mudar, `shared/onboarding/estilos.ts` **não
acompanha sozinho** — é o custo de não ter tokens compartilhados, e está anotado no topo
do arquivo.

### 10.5 LPs

`lp-financas`, `lp-contabilidade`, `lp-parceiros`: React 19 + Vite + Tailwind 4 + shadcn/ui, cada uma com um formulário (`LeadForm` / `InterestForm` / `PartnerForm`), schema de perguntas em `src/lib/*-interest-schema.ts` e `src/lib/api.ts` apontando para o backend via `VITE_API_URL`.

---

## 11. Banco de dados

PostgreSQL com extensão `vector` (pgvector), três schemas no **mesmo** banco físico: `public`, `calculators`, `landing_pages`.

### 11.1 Cadeia de migrations

```
000_baseline → 000a_lp_schema → 000b_lp_tables → 000c → 000d → 000e → 000f → 000g
             → 000h_lp_partners → 001_file_interaction → 002_msg_embeddings
             → 003_cache_hnsw → 004_news_monorepo → 005_news_taxonomia
             → 006_news_keywords → 007_identidade_profissional   (head)
```

| Revisão | O que faz |
|---|---|
| `000_baseline` | Schema completo (`down_revision=None`). Cria a extensão `vector` e o schema `calculators` |
| `000a`–`000h` | Schema `landing_pages`: criação, tabelas, índice em `submissions.email`, flag `email_missing`, rework de `accounting_answers`, vínculo com `users`, flag `notify_on_availability`, tabelas de parceiros |
| `001_file_interaction` | `file_extractions.interaction_id` (nullable, `SET NULL`) — liga o anexo à mensagem em que foi enviado |
| `002_msg_embeddings` | Tabela `message_embeddings` para o contexto de pasta |
| `003_cache_hnsw` | Troca o índice de `semantic_cache` de ivfflat para HNSW, com `CONCURRENTLY` |
| `004_news_monorepo` | Schema `news` inteiro (artigos, temas, escolhas do usuário), vindo do repositório separado |
| `005_news_taxonomia` | Seed idempotente da taxonomia de temas (`ON CONFLICT DO NOTHING`) |
| `006_news_keywords` | `news.user_keywords` + coluna gerada `articles.busca_tsv` (tsvector, peso A/B) |
| `007_identidade_profissional` | 10 colunas em `users` para a identidade profissional (§3.4). Todas nullable, **sem backfill** — preencher é trabalho revisável de `scripts/normalizar_especialidades.py`, não efeito colateral de um `alembic upgrade` |

`alembic/versions_legacy/` é histórico arquivado, **fora da cadeia ativa** — não deve ser alterado nem referenciado por migrations novas.

Decisões registradas nas próprias migrations, que vale ler antes de mexer:

- `message_embeddings` é tabela nova, e não coluna vetorial em `interactions`: uma interação vira **dois** trechos indexáveis (pergunta e resposta), e uma coluna só não comportaria os dois. `content` é duplicado ali de propósito — ir buscar o texto na origem exigiria uma segunda consulta no caminho quente, por linha recuperada.
- `message_embeddings` **não tem índice ivfflat**, ao contrário de `semantic_cache`: a busca é sempre dentro de uma pasta de um usuário, o conjunto filtrado é pequeno, e a varredura exata é mais correta e rápida o bastante (débito 11).
- `file_extractions.interaction_id` é `SET NULL` e não CASCADE: apagar uma conversa não deve apagar o arquivo, que pode estar referenciado em outra mensagem.

Não há `CREATE TYPE` (enums nativos) nem triggers: campos categóricos (`role`, `status`, `feature`, `engine_type`…) são `VARCHAR` validados na camada de aplicação (Pydantic), não por CHECK constraint.

### 11.2 Diagrama ER

```mermaid
erDiagram
    COMPANY ||--o{ USERS : "company_id"
    USERS ||--o{ CONSENT_LOGS : "user_id"
    USERS ||--o{ FILE_EXTRACTIONS : "user_id (CASCADE)"
    USERS ||--o{ FOLDERS : "user_id"
    USERS ||--o| USER_PREFERENCES : "user_id (UNIQUE)"
    USERS ||--o| USER_WEEKLY_USAGE : "user_id (UNIQUE, CASCADE)"
    USERS ||--o{ CONVERSATIONS : "user_id"
    USERS ||--o{ INVITE_TOKENS : "created_by"
    FOLDERS ||--o{ CONVERSATIONS : "folder_id (SET NULL)"
    CONVERSATIONS ||--o{ INTERACTIONS : "conversation_id"
    USERS ||--o{ INTERACTIONS : "user_id"
    COMPANY ||--o{ INTERACTIONS : "company_id"
    INTERACTIONS ||--o{ AUDIT_LOGS : "interaction_id"
    USERS ||--o{ AUDIT_LOGS : "user_id"
    INTERACTIONS ||--o{ INTERACTION_MEDICATIONS : "interaction_id"
    INTERACTIONS ||--o{ INTERACTION_RESPONSES : "interaction_id"
    INTERACTIONS ||--o{ PHARMA_ALERTS : "interaction_id"
    INTERACTIONS ||--o{ PUBMED_VALIDATIONS : "interaction_id"

    SPECIALTIES ||--o{ CALCULATOR_DEFINITIONS : "specialty_id"
    CALCULATOR_DEFINITIONS ||--o{ CALCULATOR_FIELDS : "calculator_id (CASCADE)"
    CALCULATOR_DEFINITIONS ||--o{ CALCULATOR_VERSIONS : "calculator_id (CASCADE)"
    CALCULATOR_DEFINITIONS ||--o{ CALCULATOR_FAVORITES : "calculator_id (CASCADE)"
    USERS ||--o{ CALCULATOR_FAVORITES : "user_id (CASCADE)"
    CALCULATOR_DEFINITIONS ||--o{ CALCULATOR_EXECUTIONS : "calculator_id"
    CALCULATOR_VERSIONS ||--o{ CALCULATOR_EXECUTIONS : "version_id"
    USERS ||--o{ CALCULATOR_EXECUTIONS : "user_id"
    COMPANY ||--o{ CALCULATOR_EXECUTIONS : "company_id"
    INTERACTIONS ||--o{ CALCULATOR_EXECUTIONS : "interaction_id"

    COMPANY {
        uuid id PK
        varchar name
        varchar slug UK
        jsonb settings
        boolean company_status
        varchar legacy_company_id
        timestamptz created_at
        timestamptz updated_at
    }
    USERS {
        uuid id PK
        varchar phone_number
        uuid company_id FK
        varchar email UK
        varchar name
        varchar crm
        varchar crm_state
        varchar role
        varchar med_status
        varchar specialty
        date enrollment_date
        boolean onboarding_complete
        boolean status
        varchar legacy_user_id
        timestamptz created_at
        timestamptz updated_at
    }
    CONSENT_LOGS {
        uuid id PK
        uuid user_id FK
        varchar consent_type
        boolean accepted
        inet ip_address
        text user_agent
        timestamptz accepted_at
        timestamptz revoked_at
        timestamptz created_at
    }
    FILE_EXTRACTIONS {
        uuid id PK
        uuid user_id FK "ON DELETE CASCADE"
        varchar file_name
        varchar file_type
        uuid interaction_id FK "ON DELETE SET NULL"
        text extracted_text
        text image_base64
        varchar image_media_type
        timestamptz created_at
    }
    FOLDERS {
        uuid id PK
        uuid user_id FK
        varchar name
        timestamptz created_at
        timestamptz updated_at
    }
    INVITE_TOKENS {
        uuid id PK
        uuid token UK
        varchar email
        uuid created_by FK
        timestamptz created_at
        timestamptz expires_at
        boolean used
    }
    USER_PREFERENCES {
        uuid id PK
        uuid user_id FK,UK
        jsonb selected_models
        jsonb ui_settings
        jsonb notification_prefs
        timestamptz updated_at
    }
    USER_WEEKLY_USAGE {
        uuid id PK
        uuid user_id FK,UK "ON DELETE CASCADE"
        timestamptz week_start
        numeric total_cost_usd
        timestamptz created_at
        timestamptz updated_at
    }
    CONVERSATIONS {
        uuid id PK
        uuid user_id FK
        uuid folder_id FK "ON DELETE SET NULL"
        varchar title
        varchar feature
        boolean status
        timestamptz created_at
        timestamptz updated_at
    }
    INTERACTIONS {
        uuid id PK
        uuid conversation_id FK
        uuid user_id FK
        uuid company_id FK
        varchar feature
        varchar mode
        varchar input_type
        text prompt_text
        boolean prompt_sanitized
        float triage_confidence
        varchar triage_category
        integer response_time_ms
        boolean cache_hit
        numeric token_cost_usd
        float confidence_score
        varchar specialty_detected
        varchar topic_detected
        varchar status
        jsonb clarification_questions
        timestamptz started_at
        timestamptz completed_at
        timestamptz created_at
    }
    AUDIT_LOGS {
        uuid id PK
        uuid user_id FK
        uuid interaction_id FK
        varchar action
        varchar entity_type
        uuid entity_id
        jsonb metadata
        inet ip_address
        text user_agent
        timestamptz created_at
    }
    INTERACTION_MEDICATIONS {
        uuid id PK
        uuid interaction_id FK
        varchar medication_raw
        varchar medication_normalized
        varchar atc_code
        varchar source
        timestamptz created_at
    }
    INTERACTION_RESPONSES {
        uuid id PK
        uuid interaction_id FK
        varchar model_used
        text response_text
        integer response_time_ms
        integer tokens_in
        integer tokens_out
        numeric cost_usd
        boolean is_fallback
        text error_message
        jsonb extra_metadata
        timestamptz created_at
    }
    PHARMA_ALERTS {
        uuid id PK
        uuid interaction_id FK
        integer alert_level
        varchar alert_color
        text description
        varchar source_api
        text doctor_justification
        timestamptz acknowledged_at
        timestamptz created_at
    }
    PUBMED_VALIDATIONS {
        uuid id PK
        uuid interaction_id FK
        varchar pmid
        text article_title
        text abstract_snippet
        float relevance_score
        timestamptz created_at
    }
    MODEL_PRICING {
        uuid id PK
        varchar model_id UK
        varchar provider
        varchar provider_type
        varchar display_name
        numeric input_per_million
        numeric output_per_million
        boolean status
        timestamptz updated_at
        timestamptz created_at
    }
    OTP_CODES {
        uuid id PK
        varchar email "idx"
        varchar code
        boolean used
        integer failed_attempts
        timestamptz created_at
        timestamptz expires_at
    }
    SEMANTIC_CACHE {
        uuid id PK
        varchar mode
        text normalized_prompt
        vector prompt_embedding "vector(1536), ivfflat idx"
        jsonb response_json
        integer hit_count
        timestamptz created_at
        timestamptz expires_at "idx"
    }
    SPECIALTIES {
        uuid id PK
        varchar name
        varchar slug UK
        timestamptz created_at
        timestamptz updated_at
    }
    CALCULATOR_DEFINITIONS {
        uuid id PK
        uuid specialty_id FK
        varchar slug UK
        varchar name
        text description
        varchar engine_type
        varchar status
        timestamptz created_at
        timestamptz updated_at
    }
    CALCULATOR_FIELDS {
        uuid id PK
        uuid calculator_id FK "ON DELETE CASCADE"
        varchar key
        varchar label
        varchar field_type
        varchar unit
        boolean required
        float min_value
        float max_value
        integer max_length
        jsonb options
        integer display_order
        timestamptz created_at
        timestamptz updated_at
    }
    CALCULATOR_VERSIONS {
        uuid id PK
        uuid calculator_id FK "ON DELETE CASCADE"
        integer version_number
        varchar formula_key
        jsonb interpretation_rules
        text clinical_reference
        boolean is_active "unique parcial: 1 ativa por calculadora"
        timestamptz created_at
    }
    CALCULATOR_FAVORITES {
        uuid id PK
        uuid user_id FK "ON DELETE CASCADE"
        uuid calculator_id FK "ON DELETE CASCADE"
        timestamptz created_at
    }
    CALCULATOR_EXECUTIONS {
        uuid id PK
        uuid calculator_id FK
        uuid version_id FK
        uuid user_id FK
        uuid company_id FK
        uuid interaction_id FK
        jsonb inputs
        jsonb result
        text interpretation
        timestamptz created_at
    }
    MESSAGE_EMBEDDINGS {
        uuid id PK
        uuid interaction_id FK "ON DELETE CASCADE"
        uuid conversation_id FK "ON DELETE CASCADE"
        uuid user_id FK "ON DELETE CASCADE, denormalizado"
        varchar role "user ou assistant"
        text content "duplicado de proposito"
        vector embedding "vector(1536), sem indice ivfflat"
        timestamptz created_at
    }
    LP_LANDING_PAGES {
        uuid id PK
        varchar slug UK
        varchar name
        timestamptz created_at
    }
    LP_SUBMISSIONS {
        uuid id PK
        uuid landing_page_id FK "ON DELETE RESTRICT"
        uuid user_id FK "public.users, ON DELETE SET NULL"
        varchar name
        varchar email "idx"
        boolean email_missing
        varchar phone
        timestamptz lgpd_consent_at
        boolean notify_on_availability
        timestamptz created_at
    }
    LP_FINANCE_ANSWERS {
        uuid id PK
        uuid submission_id FK,UK "ON DELETE CASCADE"
        varchar career_stage
        varchar main_pain_point
        timestamptz created_at
    }
    LP_ACCOUNTING_ANSWERS {
        uuid id PK
        uuid submission_id FK,UK "ON DELETE CASCADE"
        varchar career_stage
        varchar income_method
        varchar accountant_status
        varchar revenue_range
        varchar willingness_to_pay
        timestamptz created_at
    }
    LP_PARTNER_ANSWERS {
        uuid id PK
        uuid submission_id FK,UK "ON DELETE CASCADE"
        varchar career_stage
        varchar desired_brands
        timestamptz created_at
    }
    LP_SELECTIONS {
        uuid id PK
        uuid submission_id FK "ON DELETE CASCADE"
        varchar option
        timestamptz created_at
    }

    INTERACTIONS ||--o{ MESSAGE_EMBEDDINGS : "interaction_id (CASCADE)"
    CONVERSATIONS ||--o{ MESSAGE_EMBEDDINGS : "conversation_id (CASCADE)"
    USERS ||--o{ MESSAGE_EMBEDDINGS : "user_id (CASCADE)"
    INTERACTIONS ||--o{ FILE_EXTRACTIONS : "interaction_id (SET NULL)"

    LP_LANDING_PAGES ||--o{ LP_SUBMISSIONS : "landing_page_id (RESTRICT)"
    USERS ||--o{ LP_SUBMISSIONS : "user_id (SET NULL)"
    LP_SUBMISSIONS ||--o| LP_FINANCE_ANSWERS : "submission_id (CASCADE)"
    LP_SUBMISSIONS ||--o| LP_ACCOUNTING_ANSWERS : "submission_id (CASCADE)"
    LP_SUBMISSIONS ||--o| LP_PARTNER_ANSWERS : "submission_id (CASCADE)"
    LP_SUBMISSIONS ||--o{ LP_SELECTIONS : "accounting_pain / benefit / calculator / partner_category"
```

> No diagrama, `LP_*` são as tabelas do schema `landing_pages`; `LP_SELECTIONS` representa as quatro tabelas de seleção 1:N, que têm a mesma forma (`accounting_pain_selections`, `benefit_selections`, `calculator_selections`, `partner_category_selections`). Um `FileExtraction` agora aponta para a `Interaction` em que foi enviado (nullable: extrações anteriores à migration `001`, e o intervalo entre o upload e o envio da mensagem).

### 11.3 Constraints e regras notáveis

- **`semantic_cache.prompt_embedding`**: `VECTOR(1536)`; índice **`semantic_cache_embedding_hnsw_idx`** — `USING hnsw (prompt_embedding vector_cosine_ops)` desde a migration `003` (era ivfflat `lists = 100`, criado sobre tabela vazia). Índice composto `semantic_cache_mode_expires_idx (mode, expires_at)` para varredura de expiração por modo.
- **`message_embeddings`**: dois índices B-tree — `ix_message_embeddings_user_conversation (user_id, conversation_id)`, que é a garantia de isolamento e não uma otimização, e `ix_message_embeddings_interaction (interaction_id, role)`, usado para saber o que falta indexar. **Sem índice vetorial**, de propósito.
- **`calculators.calculator_versions`**: índice único parcial `uq_calculator_versions_one_active` — `CREATE UNIQUE INDEX ... ON calculator_versions (calculator_id) WHERE is_active` — no máximo **uma** versão ativa por calculadora, sem impedir múltiplas versões históricas.
- **`calculators.calculator_favorites`**: `UNIQUE(user_id, calculator_id)`.
- **`calculators.calculator_fields`**: `UNIQUE(calculator_id, key)`.
- **`calculators.calculator_versions`**: `UNIQUE(calculator_id, version_number)`.
- **`landing_pages.landing_pages.slug`**: `UNIQUE`; `submissions.landing_page_id` é `ON DELETE RESTRICT` (o catálogo não some por baixo de submissões existentes); cada tabela `*_answers` tem `UNIQUE(submission_id)` — uma resposta tipada por submissão.
- **`users.email`**, **`company.slug`**, **`model_pricing.model_id`**, **`invite_tokens.token`**, **`specialties.slug`**, **`calculator_definitions.slug`**: todos `UNIQUE`.
- **`user_preferences.user_id`** e **`user_weekly_usage.user_id`**: `UNIQUE` (1:1 com `users`).
- **Cascades explícitos**: `file_extractions.user_id`, `user_weekly_usage.user_id`, `calculator_favorites.user_id/calculator_id`, `calculator_fields.calculator_id`, `calculator_versions.calculator_id`, `message_embeddings.*`, `landing_pages.*_answers.submission_id` → `ON DELETE CASCADE`. `conversations.folder_id`, `file_extractions.interaction_id`, `landing_pages.submissions.user_id` → `ON DELETE SET NULL`.
- **Sem enums nativos e sem triggers** — validação de valores categóricos e regras de workflow vivem na camada de aplicação.
- **Isolamento lógico, não físico**: os três schemas no mesmo database; FKs cruzam livremente (`calculator_favorites.user_id → public.users`, `calculator_executions.interaction_id → public.interactions`, `landing_pages.submissions.user_id → public.users`).

---

## 12. Variáveis de ambiente

### 12.1 Backend (`app/core/config.py`)

| Variável | Default | Obrigatória em produção |
|---|---|---|
| APP_ENV | **sem default, de propósito** | sim |
| APP_DEBUG | False | não |
| LOG_LEVEL | INFO | não |
| DATABASE_URL | — | sim |
| JWT_SECRET_KEY | — | sim |
| JWT_ALGORITHM | HS256 | não |
| JWT_ACCESS_TOKEN_EXPIRE_MINUTES | 60 | não |
| ANTHROPIC_API_KEY / OPENAI_API_KEY / GOOGLE_AI_API_KEY / PERPLEXITY_API_KEY | "" | não |
| PHARMADB_API_KEY / PUBMED_API_KEY | "" | não |
| SENDGRID_API_KEY | "" | sim |
| SENDGRID_FROM_EMAIL | noreply@medico360.com.br | não |
| FRONTEND_URL | http://localhost:5173 | não |
| CALCULADORAS_URL | http://localhost:5174 | não |
| INVITE_TOKEN_EXPIRE_HOURS | 72 | não |
| OTP_EXPIRE_MINUTES | 10 | não |
| ALLOW_PUBLIC_REGISTRATION | False | não |
| COOKIE_DOMAIN | None | não |
| EMBED_ALLOWED_ORIGINS | `["https://adminportalmedico360.curseduca.pro"]` | não |
| **LANDING_PAGES_ORIGINS** | `["http://localhost:5175"]` | não (mas necessária para as LPs em produção) |
| CURSEDUCA_VALIDATION_ENABLED | False | sim (deve ser `true`) |
| CURSEDUCA_API_BASE | https://prof.curseduca.pro | sim, se validação habilitada |
| CURSEDUCA_API_KEY | "" | sim, se validação habilitada |
| CURSEDUCA_ACCESS_TOKEN | "" | exigida na prática pelo endpoint `members/by` |
| INTERCOM_IDENTITY_SECRET | "" | não |
| REDIS_URL | redis://localhost:6379/0 | não |
| SENTRY_DSN / SENTRY_RELEASE | "" | não (vazio desliga o Sentry) |
| PHOENIX_API_KEY / PHOENIX_PROJECT_NAME / PHOENIX_ENDPOINT | "" / medico-360 / app.phoenix.arize.com/s/ruben-nogueira | não |
| MAX_MODELS_PER_QUERY | 4 | não |
| MAX_PROMPT_CHARS | 4000 | não |
| DEFAULT_TIMEOUT_SECONDS | 30 | não |
| CALCULATOR_TEXT_FIELD_MAX_CHARS | 2000 | não |
| CALCULATOR_CATALOG_CACHE_TTL_SECONDS | 300 | não |
| CALCULATOR_EXTRACTION_MAX_CONCURRENCY | 8 | não |
| CALCULATOR_EXTRACTION_TIMEOUT_SECONDS | 15 | não |

Duas sutilezas que já causaram incidente:

- **`APP_ENV` não tem default.** Todo o endurecimento de produção está atrás de `is_production` — docs fechada, cookie `Secure`, validação fail-closed do embed. Com um default, esquecer a variável fazia a aplicação rodar em modo de desenvolvimento em produção, em silêncio. Aconteceu. Hoje a falta de `APP_ENV` derruba o startup com mensagem clara.
- **`LANDING_PAGES_ORIGINS` usa `NoDecode`.** O auto-parse JSON do pydantic-settings roda *antes* de qualquer `field_validator` e derrubava o processo no import se a env não viesse com colchetes e aspas exatos — foi o que aconteceu em produção. O validator próprio aceita JSON array, CSV (`a,b`) ou uma URL única.

**Validação fail-closed em produção** (`_validate_production_secrets`): o startup levanta `ValueError` se `jwt_secret_key`, `database_url` ou `sendgrid_api_key` estiverem vazios; se `curseduca_validation_enabled` for `false`; ou se estiver `true` e faltar `curseduca_api_base`/`curseduca_api_key`. O motivo do segundo: sem validação server-to-server, `/auth/embed/token` confia apenas no header `Origin` (forjável) e emite JWT para qualquer e-mail.

Use `python -m scripts.verificar_prontidao_producao` para saber, sem mudar nada, se a aplicação subiria com `APP_ENV=production`.

### 12.2 Frontends (build-time, Vite)

| Variável | Usada em | Comportamento |
|---|---|---|
| VITE_API_URL | `frontend-app/src/api/*.ts` | fallback `http://localhost:8000` |
| VITE_API_URL | `calculadoras-app/src/api/*.ts` | em dev, ausência = caminho relativo (o proxy do Vite cuida do CORS); em prod aponta para o domínio do backend |
| VITE_API_URL | `lp-*/src/lib/api.ts` | idem |
| VITE_INTERCOM_APP_ID | `frontend-app/src/main.tsx` | só no frontend-app; ativa o widget do Intercom |

---

## 13. Infraestrutura e deploy

### 13.1 Backend — Dockerfile único (raiz)

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN python -m spacy download pt_core_news_sm
COPY . .
RUN useradd --create-home --uid 1000 appuser && chown -R appuser:appuser /app
USER appuser
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
```

Não há `docker-compose.yml` nem `Procfile` — apenas este Dockerfile serve o backend.

### 13.2 Frontends — Dockerfile por app, contexto na raiz

Os três apps autenticados importam `shared/onboarding/`, que fica **fora da pasta de cada
um**. Com o Nixpacks e Root Directory apontando para a pasta do app, `../shared` não
existia no contexto do build e o `tsc -b` falhava. Cada um tem agora seu Dockerfile
multi-stage, com o contexto na raiz do monorepo.

No painel do Railway, por serviço:

| Campo | Valor |
|---|---|
| Root Directory | `/` |
| Builder | Dockerfile |
| `RAILWAY_DOCKERFILE_PATH` (variável) | `<app>/Dockerfile` |
| Config file path | vazio |

**As duas armadilhas, ambas silenciosas:**

1. **Sem `RAILWAY_DOCKERFILE_PATH`**, o Railway acha o `Dockerfile` da raiz — que é o do
   backend — e o serviço de frontend sobe `uvicorn`, quebrando por falta de `DATABASE_URL`.
   No log de um frontend deve aparecer `npm ci` e `vite build`, nunca `pip install`.
2. **`VITE_API_URL` é resolvida em tempo de BUILD.** Se faltar, o build passa e o bundle
   aponta para `localhost:8000` em produção. Só aparece quando alguém abre o app.

O `.dockerignore` da raiz é obrigatório: sem ele cada build enviaria `venv/`,
`node_modules/` e os **dumps de banco em `backups/`**.

> Config as Code (`railway.json` / `railway.toml`) está **depreciado** e para de ser lido
> em **2026-12-01**. Os arquivos dos três apps autenticados foram removidos porque
> sobrescreviam o painel; as quatro LPs ainda têm os seus. A substituição é
> Infrastructure as Code (`.railway/railway.ts`), que descreve o projeto inteiro num
> arquivo — migração pendente, e ela toca todos os serviços de uma vez.

### 13.3 Backup

**O Railway não faz backup gerenciado.** A estratégia real é dump manual verificado + armazenamento externo:

- `python -m scripts.backup_producao --dsn ... --saida backups/` — gera o dump com carimbo de data e **prova que ele é legível** antes de declarar sucesso.
- `python -m scripts.verificar_restore` — ensaio de restore: só faz `SELECT` (contagens, `max(created_at)`, `alembic_version`) nos dois bancos, e pode apontar para produção como origem sem risco.
- RPO/RTO medidos no ensaio de 2026-08-19 estão em `docs/runbook.md`, junto com os três achados daquele ensaio.

---

## 14. Testes e CI

### 14.1 Suíte

- **Backend** — `tests/`, 46 arquivos, **811 testes**. Cobertura mínima de 50% cobrada no CI como catraca contra regressão (o número é o medido, arredondado para baixo — não é um atestado de qualidade).
  - Segurança/LGPD: `test_authorization`, `test_idor`, `test_lgpd`, `test_consentimento`, `test_dlp`, `test_dlp_enforcement`, `test_expurgo_agendado`, `test_calculadoras_isolamento`, `test_contexto_seguranca`
  - Orquestrador: `test_orquestrador_paridade` (garante que `/query` e `/stream` não divirjam — **leia este primeiro**, o docstring conta os dois incidentes que o motivaram), `test_orquestrador_stream`, `test_contexto`, `test_contexto_cache`, `test_folder_context`, `test_exames`, `test_conversas_referencias`, `test_response_metadata`
  - Identidade: `test_especialidades` (vocabulário, precedência, leitura dos grupos `[CFM]`), `test_reconciliacao_embed`, `test_onboarding_pendencias`, `test_prompts_contexto`, `test_normalizar_especialidades`, `test_exclusao_de_conta`
  - Notícias: `test_news_taxonomia` (coerência da taxonomia, sem banco), `test_news_feed`, `test_news_feed_multiespecialidade`, `test_news_pipeline`, `test_news_keywords`
  - Cache: `test_cache_semantico_contrato`, `test_cache_hit_historico`
  - Resiliência/infra: `test_circuit_breaker`, `test_agregador_resiliencia`, `test_health`, `test_logging`, `test_error_tracking`, `test_usage_limits`, `test_harness`
  - Calculadoras: `tests/calculators/` (fórmulas + validação)
- **frontend-app** — Vitest + Testing Library, roda no CI **antes** do build (falha de teste deve aparecer como falha de teste, não como build verde de código quebrado).
- **calculadoras-app** — Playwright, contra backend e frontend reais (não mockados), por cima de seeds determinísticos.

**Harness de teste** (`tests/conftest.py`): trava de banco explícita — o nome do banco precisa conter `test`, senão o pytest se recusa a rodar. O `.env` do projeto aponta para o banco hospedado; sem a trava, um `pytest` distraído roda migrations e apaga tabelas em produção. Rodar localmente exige o container pgvector:

```bash
docker run -d --name m360-test-db -p 55433:5432 \
    -e POSTGRES_USER=test -e POSTGRES_PASSWORD=test \
    -e POSTGRES_DB=medico360_test pgvector/pgvector:pg16
pytest
```

A imagem precisa ser `pgvector` (índices vetoriais). SQLite não serve — os modelos usam JSONB e UUID do dialeto PostgreSQL.

### 14.2 CI — `.github/workflows/ci.yml` (4 jobs, todos bloqueantes)

1. **backend**: serviço `pgvector/pgvector:pg16` na porta `55433` → `ruff check .` (escopo total; exceções declaradas em `ruff.toml`) → `pytest --cov=app --cov-fail-under=50` → **`alembic upgrade head` num banco vazio** → `pip-audit -r requirements.txt --strict`.
2. **frontend-app**: node 20 → `npm ci` → `npm run lint` → `tsc -b --noEmit` → `npm test` → `npm run build`.
3. **calculadoras-app**: igual, sem o passo de teste unitário.
4. **e2e-calculadoras**: sobe Postgres pgvector, `alembic upgrade head` + seeds (`seed_calculators`, `seed_risco_cv_sbc2025`, `seed_usuario_e2e`), sobe backend e o dev server na 5174 em background, **espera as duas portas responderem** e roda o Playwright.

Detalhes do CI que valem saber antes de mexer:

- O passo de migrations existe porque a cadeia ficou **quebrada por muito tempo** — o schema nasceu de um `create_all` fora do Alembic. O harness monta o schema pelos models, então sem este passo uma migration quebrada passaria despercebida.
- Os seeds rodam como `python -m scripts.x`, nunca `python scripts/x.py`: a forma com caminho coloca `scripts/` no `sys.path` em vez da raiz, e os seeds importam `app.*`. Mesma causa do `prepend_sys_path` que o Alembic precisou.
- As senhas dos serviços são derivadas do `github.run_id`, e os segredos JWT gerados com `openssl rand`: literal com cara de credencial dispara scanner, e scanner que dá alarme falso é scanner ignorado.
- A espera pelos servidores foi o que eliminou a intermitência do E2E. O alvo é `/api/v1/health` (o router tem prefixo) e é liveness puro, não consulta banco.

---

## 15. Scripts operacionais (`scripts/`)

| Script | Para quê |
|---|---|
| `backup_producao.py` | Dump com carimbo de data que **prova** ser legível antes de reportar sucesso |
| `verificar_restore.py` | Ensaio de restore; só faz `SELECT`, seguro contra produção |
| `verificar_prontidao_producao.py` | "A aplicação subiria com `APP_ENV=production`?" — lista o que falta, não muda nada |
| `expurgar_dados_vencidos.py` | Expurgo LGPD manual (o automático roda no backend) |
| `verificar_expurgo.py` | Conta o que já passou do prazo e continua no banco; não apaga |
| `verificar_vigilancia.py` | Mostra cache, custo e último expurgo agora; só `SELECT`, sai 1 se algo estiver em alarme |
| `verificar_sentry.py` | Envia um evento de teste e confirma que o scrubbing funciona no ambiente real |
| `simular_erro_de_usuario.py` | Exercita o contexto de **requisição** no Sentry (corpo, headers, cookie, query) |
| `medir_cache_semantico.py` | Mede o cache antes de mexer no índice vetorial |
| `seed_calculators.py` + `seed_*` | Catálogo e calculadoras (Cockcroft-Gault, CURB-65, CHA₂DS₂-VASc/HAS-BLED, Risco CV SBC 2025) |
| `seed_usuario_e2e.py` | Usuário fixo de UUID conhecido que o Playwright usa para assinar token |
| `add_gemini_2_5_flash.py`, `deactivate_gemini_3_flash.py`, `update_claude_sonnet_model_id.py` | Manutenção de `model_pricing` — a disponibilidade de modelo é controlada pelo backend, nunca por exclusão hardcoded no frontend |
| `generate_dev_token.py` | JWT de desenvolvimento (não versionado no git) |

---

## 16. Convenções do repositório

- **Commits direto na `main`**, sem branch. Mensagens em português, no formato `tipo(escopo): o que mudou` — descrevem o efeito observável, não o mecanismo.
- **Comentários no código carregam o porquê, não o quê.** Boa parte do raciocínio de arquitetura deste sistema está em docstrings de módulo e em cabeçalhos de migration; várias seções acima são resumo delas. Ao mexer numa dessas áreas, leia o cabeçalho antes.
- `ruff` em escopo total, exceções declaradas em `ruff.toml` via `per-file-ignores`.
- Diretórios não versionados: `.venv/`, `venv/`, `medico-360/` (rascunho antigo), `backups/` (o dump ali é local).

---

## 17. Pontos de atenção para quem for mexer

Armadilhas conhecidas, em ordem de quanto custam se ignoradas:

1. **Nunca rode `pytest` sem a trava de banco.** O `.env` aponta para o banco hospedado. A trava exige `test` no nome do banco — não a contorne.
2. **Migrations partem de `000_baseline`.** `alembic/versions_legacy/` é arquivo morto; não altere nem referencie.
3. **Os filtros de DLP têm exceções calibradas por medição real** (epônimos médicos — "manobra de Valsalva" não é um paciente). Simplificar `ner._is_person` sem ler a justificativa reintroduz falsos positivos que apagam termos clínicos em definitivo.
4. **O isolamento da busca em pasta é filtro por `user_id` + `folder_id` em todo caminho de leitura.** É o ponto do sistema onde um filtro frouxo vaza dado de um paciente para a discussão de outro.
5. **`/query` e `/stream` precisam continuar equivalentes.** Há teste de paridade (`tests/test_orquestrador_paridade.py`) porque os dois já divergiram por cópia — duas vezes: o atalho de saudação (que virava erro interno no `/query`) e o texto do pedido de reformulação. Mudança em um dos dois provavelmente pertence a `orquestrador_shared.py`.
6. **Modos se definem em `orquestrador_modes.py` e em nenhum outro lugar.** O mapa modo→prompt em `core/prompts.py` ainda é um segundo lugar — é o débito 6, conhecido e aberto.
7. **Especialidade se escreve por `identidade.aplicar_especialidade`, e por mais nenhum caminho.** Um `user.specialty = ...` solto em qualquer lugar mata a precedência do §3.4 e o arquivo vira decoração.
8. **Renomear um rótulo de especialidade é MIGRAÇÃO DE DADOS.** `users.specialty` e `news.topic_specialties.specialty` casam por string. Há teste travando os 55 rótulos que estão em produção; se ele falhar, a pergunta não é "como conserto o teste".
9. **Não há backup automático do Railway.** Antes de qualquer operação destrutiva no banco, rode `scripts/backup_producao.py`.
10. **Alarme novo exige medição nova.** Toda garantia que o sistema passar a oferecer em silêncio (uma tarefa agendada, um cache, um limite) deve virar uma medição em `vigilancia_service.py`. As falhas silenciosas de agosto não foram falta de código correto — foram falta de alguém perguntando.
11. **`docs/debitos.md` tem o raciocínio de cada débito** — incluindo os já resolvidos e um marcado como "não é dívida". Vale ler antes de propor melhorias: várias já foram consideradas e recusadas por motivo registrado.

### 17.1 Mapa de dívidas — tamanho e risco

Para quem for avaliar por onde começar. A coluna que importa é a última: o que dói hoje.

| Dívida | Tamanho | Risco de mexer | O que dói hoje |
|---|---|---|---|
| `orquestrador_service` + `_stream` — 1.100 linhas em dois métodos gigantes, com a persistência da interação ainda duplicada | semanas | **alto** — é o caminho principal do produto | Bug corrigido num não chega no outro. Já aconteceu duas vezes |
| SQL direto em 21 services e 6 endpoints | grande, contínuo | baixo **se de carona** | Nada agudo. Vira campanha cara se tratado como projeto |
| `services/` com 32 arquivos soltos (~9.600 linhas) | médio | baixo — é mover arquivo | Achar coisa depende de grep |
| Taxonomia de temas de notícias sem revisão médica | não é código | — | Nasceu de rascunho de engenharia; erro ali é silencioso (o tema não é sugerido a ninguém) |
| Backup manual, sem agendamento | pequeno | — | RPO = idade do último dump |
| Webhook de cadastro não construído | médio | baixo | O CRM não chega ao Médico 360; hoje isso é aceito de propósito (§3.4) |
| Migração para Railway IaC | médio | médio — toca todos os serviços | Prazo real: 2026-12-01 |

**O que NÃO é dívida, e já foi decidido:**

- Perseguir clean architecture no `services/` legado. O benefício real — domínio testável sem banco — já existe em `medicina/`, `news/` e `calculators/formulas/`. A orientação é construir o novo como fatia vertical e deixar o antigo encolher por atrito.
- `ESPECIALIDADE_PISO` no feed de notícias. Parece gambiarra e não é: o embed cria usuário só com e-mail, e sem o piso ele encara 51 caixas em branco. A contagem de quantas vezes ele é acionado (`news.piso_especialidade` no log) é a métrica de sucesso do trabalho de identidade.
- Índice vetorial em `message_embeddings`. A busca é sempre dentro de uma pasta de um usuário; varredura exata é mais correta e rápida o bastante (débito 11).

### 17.2 Onde as decisões estão escritas

Este repositório documenta **por que**, não **o quê** — os comentários de código são a
fonte primária e costumam trazer o incidente que motivou a regra. Vale ler antes de
"simplificar":

| Arquivo | Decisão que ele guarda |
|---|---|
| `app/medicina/identidade.py` | Precedência da especialidade, por que `declarado` fica no fundo, por que o CRM saiu das pendências |
| `app/medicina/especialidades.py` | Por que os 55 rótulos do TSX foram eleitos canônicos; por que GENERALISTA não vira Clínica Médica |
| `app/news/taxonomia.py` | Que o arquivo é PRODUTO e ainda não passou por revisão médica |
| `app/services/integracoes/curseduca_service.py` | O molde de cliente externo: disjuntor, timeout, fail-closed |
| `app/services/news_feed_service.py` | O piso de especialidade e por que ele não filtra por peso |
| `alembic/versions/*.py` | Cada migration explica a decisão de modelagem no topo |
| `docs/debitos.md` | Débitos com status e justificativa |
| `docs/runbook.md` | Operação: incidentes, rotação de segredos, backup/restore com números medidos |
