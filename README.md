# Médico 360 — Backend API

Plataforma de apoio à decisão clínica para médicos com registro ativo no CRM.
Pipeline multi-agente com validação científica via PubMed e cache semântico.

---

## Sumário

- [Visão Geral](#visão-geral)
- [Stack Técnica](#stack-técnica)
- [Arquitetura](#arquitetura)
- [Módulos Principais](#módulos-principais)
  - [Orquestrador Multi-Agente](#orquestrador-multi-agente)
  - [Validação PubMed](#validação-pubmed)
  - [Cache Semântico](#cache-semântico)
  - [PharmaDB](#pharmadb)
  - [DLP e Auditoria](#dlp-e-auditoria)
- [Modelos de IA por Modo](#modelos-de-ia-por-modo)
- [Endpoints](#endpoints)
- [Variáveis de Ambiente](#variáveis-de-ambiente)
- [Banco de Dados](#banco-de-dados)
- [Como Rodar Localmente](#como-rodar-localmente)

---

## Visão Geral

O Médico 360 expõe um endpoint principal (`/api/v1/orquestrador/query`) que recebe perguntas de médicos e:

1. Faz triagem automática da pergunta (triage) para classificar o modo
2. Roteia para o agente especializado correto
3. Valida a resposta cientificamente via PubMed
4. Armazena/recupera respostas via cache semântico por vetores
5. Registra tudo em audit log e persiste métricas no banco

---

## Stack Técnica

| Camada | Tecnologia |
|--------|-----------|
| Framework | FastAPI + Uvicorn |
| Banco de dados | PostgreSQL + pgvector |
| ORM | SQLAlchemy (async) |
| Migrations | Alembic (async) |
| Cache semântico | pgvector (cosine similarity) |
| HTTP client | httpx (AsyncClient) |
| Auth | JWT (python-jose) |
| Python | 3.12+ |

---

## Arquitetura

```
POST /api/v1/orquestrador/query
          │
          ▼
    ┌─────────────┐
    │   DLP       │  sanitiza PII / dados sensíveis
    └──────┬──────┘
           │
    ┌──────▼──────┐
    │   Triage    │  classifica modo (GPT-4o-mini)
    └──────┬──────┘
           │
    ┌──────▼──────────────────────────────────┐
    │         Cache Semântico                  │
    │  normalize (GPT-4o-mini) → embed →       │
    │  pgvector cosine lookup (threshold 0.92) │
    └──────┬──────────────────┬───────────────┘
           │ HIT              │ MISS
           │                  ▼
           │         ┌────────────────────┐
           │         │  Agente Especializ.│
           │         │  QUICK_SEARCH      │ → Perplexity sonar-pro
           │         │  CLINICAL_REASON.  │ → Claude Sonnet 4
           │         │  PHARMA_CHECK      │ → PharmaDB local
           │         │  PRODUCTIVITY      │ → GPT nano
           │         └────────┬───────────┘
           │                  │
           │         ┌────────▼───────────┐
           │         │  Validação PubMed  │
           │         │  Trilha A: verifica│
           │         │  citações da resp. │
           │         │  Trilha B: busca   │
           │         │  guidelines novas  │
           │         └────────┬───────────┘
           │                  │
           │         ┌────────▼───────────┐
           │         │  Specialty/Topic   │
           │         │  Medications       │
           │         │  Audit Log         │
           │         │  store → cache     │
           │         └────────────────────┘
           │                  │
           └──────────────────▼
                    Response JSON
```

---

## Módulos Principais

### Orquestrador Multi-Agente

**Arquivo:** `app/services/orquestrador_service.py`

Pipeline principal. Orquestra todos os módulos em sequência:

| Passo | Ação |
|-------|------|
| 1 | DLP — sanitiza o prompt |
| 2 | Triage — classifica o modo com confiança |
| 3 | Cache semântico — lookup por similaridade |
| 4 | Conversation — cria ou recupera sessão |
| 5 | Interaction — persiste no banco |
| 6 | Agente — chama o modelo de IA |
| 7 | Custo — calcula com base em tokens |
| 8 | Specialty/Topic — detecta especialidade |
| 9 | Medicamentos — extrai da resposta |
| 10 | PubMed — valida citações |
| 11 | Audit Log — persiste metadados |
| 12 | Store cache — armazena se elegível |

**Modos disponíveis:**

| Modo | Trigger | Modelo | Temperature |
|------|---------|--------|-------------|
| `QUICK_SEARCH` | Dúvidas diretas, posologia, doses | sonar-pro (Perplexity) | 0.0 |
| `CLINICAL_REASONING` | Casos clínicos, raciocínio diagnóstico | claude-sonnet-4-20250514 | 0.0 |
| `PHARMA_CHECK` | Interações medicamentosas | PharmaDB (local) | — |
| `PRODUCTIVITY` | Laudos, emails, tarefas não clínicas | GPT nano | 0.7 |

Temperature 0.0 nos modos clínicos garante respostas determinísticas e reproduzíveis.

---

### Validação PubMed

**Arquivo:** `app/services/pubmed_service.py`

Executa duas trilhas paralelas após a resposta do agente:

#### Trilha A — Verificação de Citações
1. Extrai referências da resposta via GPT-4o-mini (guidelines + artigos seminais com autores)
2. Para cada citação, busca no PubMed:
   - Formato `Autor et al. Ano` → query `Autor[author] AND Ano[pdat]`
   - Outros formatos → `[tiab]` com fallback por palavras-chave + filtro guideline
3. Retorna `verified: true` + PMID se encontrado

#### Trilha B — Guidelines Recentes
1. Busca guidelines publicadas nos últimos 24 meses sobre o tópico detectado
2. Filtra as que já foram citadas (são novidades reais)
3. Sinaliza `outdated_alert: true` se houver diretrizes mais novas que o modelo não citou

#### Fórmula do Confidence Score

| Situação | Score |
|----------|-------|
| Sem citações na resposta | 0.10 |
| Citações presentes (base) | 0.60 |
| +0.10 por citação verificada | máx +0.30 |
| +0.10 se sem guidelines mais novas | bônus atualização |
| -0.15 por guideline mais nova encontrada | penalidade desatualização |

**Exemplos:**
- 2 verificadas + sem novidades → `0.60 + 0.20 + 0.10 = 0.90`
- 1 verificada + 1 nacional (não no PubMed) + sem novidades → `0.60 + 0.10 + 0.10 = 0.80`
- 0 verificadas + 1 guideline nova → `0.60 - 0.15 = 0.45`

Diretrizes nacionais (brasileiras, ministeriais) não estão no PubMed mas são válidas — o sistema não pune ausências, apenas recompensa verificações.

**Campos retornados:**

```json
{
  "confidence_score": 0.90,
  "low_evidence_alert": false,
  "outdated_alert": false,
  "cited_guidelines_verified": [
    { "title": "ESC 2021 Heart Failure Guidelines", "pmid": "34447992", "verified": true },
    { "title": "Diretriz Brasileira de IC 2018", "pmid": null, "verified": false }
  ],
  "newer_guidelines_found": []
}
```

**Timeout:** 15s com fallback automático (`confidence_score: 0.0, fallback: true`).

---

### Cache Semântico

**Arquivo:** `app/services/semantic_cache_service.py`
**Tabela:** `semantic_cache` (pgvector)

Evita chamadas repetidas aos modelos de IA para perguntas semanticamente equivalentes.

#### Pipeline por Query

```
Prompt
  │
  ▼
Guardrail + Normalização (GPT-4o-mini)
  ├── Decide se é cacheável (sem dados específicos de paciente)
  └── Expande siglas: FA→fibrilação atrial, ICFEr→insuficiência cardíaca com FE reduzida,
      PAC→pneumonia adquirida na comunidade, HAS→hipertensão arterial sistêmica, etc.
  │
  ▼ (se cacheável)
Embedding (text-embedding-3-small, 1536 dims)
  │
  ▼
pgvector cosine similarity lookup
  ├── sim ≥ 0.92 → HIT: retorna resposta cacheada
  └── sim < 0.92 → MISS: chama agente, armazena ao final
```

#### Regras de Elegibilidade

| Modo | Cacheável quando |
|------|-----------------|
| `QUICK_SEARCH` | Sempre que o guardrail aprovar |
| `CLINICAL_REASONING` | Apenas perguntas genéricas — qualquer dado de paciente (idade, sexo, valores laboratoriais, doses específicas, referências temporais) bloqueia o cache |
| `PHARMA_CHECK` | Nunca (sempre consulta PharmaDB em tempo real) |
| `PRODUCTIVITY` | Nunca |

#### Parâmetros

| Parâmetro | Valor |
|-----------|-------|
| Modelo de embedding | text-embedding-3-small |
| Dimensões | 1536 |
| Threshold similaridade | 0.92 |
| TTL | 30 dias |
| Índice pgvector | IVFFlat (cosine, lists=100) |

#### Estrutura da Tabela

```sql
CREATE TABLE semantic_cache (
    id           UUID PRIMARY KEY,
    mode         VARCHAR(50),
    normalized_prompt TEXT,
    prompt_embedding  vector(1536),
    response_json     JSONB,
    hit_count    INTEGER DEFAULT 0,
    created_at   TIMESTAMPTZ,
    expires_at   TIMESTAMPTZ
);
```

#### Indicadores no Response

```json
{
  "cache_hit": true,
  "interaction_id": "...",
  "response_text": "..."
}
```

---

### PharmaDB

**Arquivo:** `app/services/pharmadb_service.py`

Checagem local de interações medicamentosas. Ativado quando o triage classifica o modo como `PHARMA_CHECK`.

- Requer mínimo de 2 medicamentos no prompt
- Retorna semáforo de risco (vermelho/amarelo/verde) por par de princípios ativos
- Persiste alertas na tabela `pharma_alerts`
- Cache Redis interno por par de fármacos

---

### DLP e Auditoria

**Arquivo:** `app/middleware/dlp.py`

- Sanitiza CPF, CRM, nomes próprios e outros dados sensíveis antes de enviar ao modelo
- Flag `prompt_sanitized` indica se houve remoção

**Audit Log:** cada interação gera registro em `audit_logs` com metadados completos:
- Modo, modelo, custo, tempo de resposta
- Score PubMed, alertas de evidência
- Medicamentos extraídos, especialidade detectada

---

## Modelos de IA por Modo

| Modo | Modelo Principal | Fallbacks |
|------|-----------------|-----------|
| QUICK_SEARCH | sonar-pro (Perplexity) | gemini-2.5-flash |
| CLINICAL_REASONING | claude-sonnet-4-20250514 | gpt-4o → gemini-2.5-flash |
| PRODUCTIVITY | gpt-5.4-nano | gemini-2.5-flash |

Todos os modelos são configurados via tabela `model_pricing` no banco — sem hardcode de preços no código.

---

## Endpoints

### `POST /api/v1/orquestrador/query`

Endpoint principal. Requer JWT no header `Authorization: Bearer <token>`.

**Request:**
```json
{
  "prompt": "Quais betabloqueadores usar na ICFEr?",
  "conversation_id": null
}
```

**Response:**
```json
{
  "status": "ok",
  "cache_hit": false,
  "interaction_id": "uuid",
  "conversation_id": "uuid",
  "mode": "QUICK_SEARCH",
  "triage_confidence": 0.91,
  "model_used": "sonar-pro",
  "is_fallback": false,
  "response_text": "...",
  "tokens_in": 312,
  "tokens_out": 580,
  "cost_usd": 0.0021,
  "specialty_detected": "Cardiologia",
  "topic_detected": "betabloqueadores insuficiência cardíaca",
  "confidence_score": 0.90,
  "low_evidence_alert": false,
  "outdated_alert": false,
  "cited_guidelines_verified": [...],
  "newer_guidelines_found": [],
  "total_response_time_ms": 3241,
  "disclaimer": "⚕️ ..."
}
```

**Resposta com cache hit:**
```json
{
  "cache_hit": true,
  "response_text": "...",
  "total_response_time_ms": 847
}
```

### `POST /api/v1/agregador/query`

Assistente geral sem pipeline de validação. Responde qualquer pergunta do médico.

### `GET /api/v1/health`

Healthcheck da API.

---

## Variáveis de Ambiente

```env
# Banco
DATABASE_URL=postgresql+asyncpg://user:pass@host/db

# IA
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
GOOGLE_AI_API_KEY=...
PERPLEXITY_API_KEY=pplx-...

# PubMed (opcional — aumenta rate limit)
PUBMED_API_KEY=...

# Auth
SECRET_KEY=...
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60

# Redis (PharmaDB cache)
REDIS_URL=redis://localhost:6379
```

---

## Banco de Dados

### Tabelas principais

| Tabela | Descrição |
|--------|-----------|
| `users` | Médicos cadastrados |
| `companies` | Empresas/clínicas |
| `conversations` | Sessões de conversa |
| `interactions` | Cada query processada |
| `interaction_responses` | Resposta do modelo por interaction |
| `interaction_medications` | Medicamentos extraídos |
| `pubmed_validations` | Artigos verificados/encontrados no PubMed |
| `pharma_alerts` | Alertas de interação medicamentosa |
| `audit_logs` | Log completo de todas as ações |
| `model_pricing` | Modelos disponíveis e preços por token |
| `semantic_cache` | Cache semântico (pgvector) |
| `consent_logs` | Aceite de termos |

### Migrations

```bash
PYTHONPATH=. alembic upgrade head
```

---

## Como Rodar Localmente

```bash
# 1. Instalar dependências
pip install -r requirements.txt

# 2. Configurar variáveis de ambiente
cp .env.example .env

# 3. Rodar migrations
PYTHONPATH=. alembic upgrade head

# 4. Subir o servidor
uvicorn app.main:app --reload --port 8000
```

A documentação interativa da API estará disponível em `http://localhost:8000/docs`.
