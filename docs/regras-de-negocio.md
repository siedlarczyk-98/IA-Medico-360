# MÉDICO 360 — Regras de Negócio v2.3
**CONFIDENCIAL**

Plataforma de Assistência Clínica com Inteligência Artificial

---

**DOCUMENTAÇÃO DE REGRAS DE NEGÓCIO**

Orquestrador Multi-Agente + Calculadoras + Notícias + Localizador de DEA

**Versão 2.3 — 10 de setembro de 2026**

**Status: Em produção**

> Documento **interno**. Descreve as regras como estão implementadas, com o arquivo e a
> constante de cada número. Onde o código e a intenção de produto divergem, o texto diz qual
> é qual — não inventa consenso.

---

## Sumário

1. Visão Geral do Produto
2. Agregador de IA — histórico, fora da interface
3. Orquestrador Multi-Agente Clínico
4. Validação Científica via PubMed
5. Cache Semântico — implementado, desligado
6. Auditoria, Logs e Data Monetization
7. Segurança, Privacidade e LGPD
8. Disponibilidade e Resiliência
9. Interface e UX — Mobile First
10. Status de Implementação
11. Calculadoras Científicas
12. Notícias
13. Localizador de DEA
14. Identidade profissional
15. Pastas com evolução clínica
16. Glossário
17. Controle de Versão

---

## 1. Visão Geral do Produto

### 1.1 Descrição

O Médico 360 é uma plataforma SaaS de assistência clínica baseada em Inteligência Artificial,
para médicos e profissionais de saúde. O produto é o **Orquestrador Multi-Agente**: o médico
faz uma pergunta, uma triagem classifica a intenção e roteia para o agente especializado.

Em torno dele existem quatro módulos com regras próprias: **Calculadoras Científicas**,
**Notícias**, **Localizador de DEA** e as **Landing Pages** de captação.

> **O Agregador de IA saiu da interface.** Backend, rotas `/agregador/*` e testes continuam
> intactos, mas o usuário não o vê mais — a §2 descreve uma feature que hoje é histórica.

### 1.2 Estratégia de Lançamento

**Fase atual (beta):** acesso gratuito a todas as funcionalidades, sem diferenciação de
planos por perfil clínico.

**Existe um teto de custo por usuário**, e ele não é cosmético — ver RN-CUSTO-001 (§1.5).

**Monetização futura:** planos pagos, limites por perfil e B2B serão definidos com base nos
dados coletados.

### 1.3 Posicionamento Jurídico

**Classificação:** Non-SaMD (Software as a Medical Device). Ferramenta de apoio à decisão
clínica, NÃO instrumento de diagnóstico.

Todo output DEVE conter disclaimer explícito:

> *"⚕️ Esta resposta é de suporte à decisão clínica. A conduta adotada é de responsabilidade
> exclusiva do médico assistente. As informações apresentadas não substituem avaliação
> clínica individualizada."*

### 1.4 Autenticação e Acesso

- O sistema valida o `role` do usuário, vindo do banco ou do JWT.
- **O default é `beta_user`** (`app/models/models.py:94`), não `free_user`. É esse valor que
  o controle de custo consulta.
- A estrutura de roles suporta expansão (`basic`, `pro`, `b2b_partner`) sem refatoração.
- **Login por embed:** o médico entra pelo LMS (Curseduca/Waid) com token verificável
  server-to-server. O caminho legado que aceitava `{email}` está desligado — ele não provava
  identidade, e quem soubesse o e-mail de um colega recebia a sessão dele. Ver §14.

### 1.5 Limite de custo por usuário

**RN-CUSTO-001 — Teto semanal de US$ 5,00 por usuário.**
`app/services/usage_service.py:33`. Ao ultrapassar, a API responde **429** nos dois endpoints
do orquestrador (`/query` e `/stream`).

O teto era US$ 1,00 e subiu para US$ 5,00 porque **uma** consulta no modo Data Ocean custou
US$ 0,647945: o médico batia o limite na segunda pergunta e perdia acesso a *todos* os modos,
inclusive os baratos.

**RN-CUSTO-002 — A janela é de 7 dias corridos**, contada por usuário, não por mês
calendário.

---

## 2. Agregador de IA — histórico, fora da interface

> ⚠️ **Esta seção descreve uma feature que o usuário não vê mais.** O Agregador foi
> removido da interface (`frontend-app/src/App.agregador-oculto.test.tsx`); o produto
> passou a ser o Orquestrador. Backend, rotas `/agregador/*` e testes continuam intactos
> e funcionando — a remoção é de superfície.
>
> Mantida como referência de contrato de API. **Não priorizar trabalho a partir daqui**
> (as RN-AGR-003 sobre layout lado a lado descrevem uma tela que não existe).

### 2.1 Definição

Interface unificada para consultar múltiplos modelos de IA simultaneamente ou de forma
seletiva, com as respostas num painel comparativo. Teto de **4 modelos por consulta**
(`max_models_per_query`, `app/core/config.py:190`).

### 2.2 Modelos de IA Disponíveis

| Modelo | Provider | Caso de Uso | Custo Relativo |
|--------|----------|-------------|----------------|
| Claude Sonnet 4.6 | Anthropic | Raciocínio clínico avançado | Médio |
| GPT-4o | OpenAI | Consultas gerais | Médio |
| Gemini 2.5 Flash | Google | Respostas rápidas | Baixo |
| Perplexity Sonar Pro | Perplexity | Busca online com fontes | Médio |

*A lista de modelos é gerenciada via tabela `model_pricing` no banco de dados — configurável pelo administrador sem alteração de código.*

### 2.3 Regras de Negócio do Agregador

#### RN-AGR-001: Seleção de Modelos ✅ Implementado

- O médico DEVE selecionar ao menos 1 modelo antes de enviar uma consulta.
- O médico PODE selecionar múltiplos modelos para comparação simultânea.
- Caso um modelo esteja indisponível (timeout/erro), a plataforma DEVE exibir mensagem de indisponibilidade específica sem impactar os demais.

#### RN-AGR-002: Envio de Consulta ⚠️ Parcial

- A entrada DEVE aceitar texto livre (limite: 4.000 caracteres). ✅
- A entrada PODE aceitar áudio via API Whisper (transcrição automática para texto). ❌ Pendente
- O prompt DEVE ser precedido de system prompt médico padrão definido pela plataforma. ✅

#### RN-AGR-003: Exibição de Respostas ✅ Backend pronto / Frontend pendente

- Respostas DEVEM ser exibidas em Markdown, com tabelas para posologias e negrito para red flags.
- Múltiplos modelos: exibição lado a lado (desktop) ou em abas (mobile).
- Cada resposta DEVE identificar o modelo e o tempo de resposta.

#### RN-AGR-004: Registro e Histórico ⚠️ Parcial

- TODA interação DEVE ser registrada conforme padrão de auditoria (Seção 6). ✅
- O histórico DEVE ser pesquisável pelo médico por data, modelo e palavras-chave. ❌ Endpoint pendente
- Retenção mínima: 12 meses. ✅ (dados persistidos em PostgreSQL)
- O médico PODE exportar histórico em PDF ou CSV. ❌ Pendente

---

## 3. Feature 2: Orquestrador Multi-Agente Clínico

### 3.1 Definição

O Orquestrador (codinome: **The Gatekeeper**) é uma arquitetura multi-agente que recebe a pergunta do médico, classifica a complexidade via triagem inteligente, e roteia automaticamente para o agente especializado mais adequado. O objetivo é entregar respostas com validação científica, segurança farmacológica e blindagem jurídica.

### 3.2 Pipeline do Orquestrador

```
Entrada do Médico
      │
      ▼
[1] DLP — sanitiza PII antes de qualquer envio externo
      │
      ▼
[2] Triagem Inteligente (gpt-5.4-nano) — classifica modo + confiança
      │ confiança < 0.7 → solicita refinamento
      │ confiança ≥ 0.7 → prossegue
      ▼
[3] Cache Semântico — normalize → embed → pgvector lookup
      │ HIT → retorna resposta cacheada (cache_hit: true)
      │ MISS → prossegue para agente
      ▼
[4] Agente Especializado (por modo)
      │
      ▼
[5] Validação Científica PubMed (trilhas paralelas A+B)
      │
      ▼
[6] Detecção de Especialidade + Extração de Medicamentos
      │
      ▼
[7] Audit Log + Store no Cache Semântico
      │
      ▼
Resposta Final
```

### 3.3 Classificação por Modo

#### RN-ORC-001: Modos do Orquestrador ✅ Implementado

São **dez** modos. Fonte: `app/services/orquestrador_modes.py`.

| Modo (Produto) | Código Interno | Critério | Modelo | Temp. |
|---|---|---|---|---|
| **Bizu** | `QUICK_SEARCH` | Dúvida direta: posologia, CID, conduta rápida | `sonar-pro` (Perplexity) | 0.0 |
| **Sherlock** | `CLINICAL_REASONING` | Caso clínico, diagnóstico diferencial | `claude-sonnet-4-6` | 0.0 |
| **Exame** | `EXAM_REVIEW` | Leitura de exame anexado | `claude-sonnet-4-6` (visão) | 0.0 |
| **Farmácia — interação** | `PHARMA_CHECK` | Interação entre **2+** fármacos | PharmaDB local | — |
| **Farmácia — bula** | `PHARMA_BULA` | Bula de **um** medicamento | PharmaDB local | — |
| **Farmácia — receita** | `PHARMA_RECEITA` | Receituário, Portaria 344 | PharmaDB local | — |
| **Farmácia — genérico** | `PHARMA_GENERICO` | Genéricos e intercambiáveis | PharmaDB local | — |
| **Data Ocean** | `DATA_OCEAN` | Dados públicos brasileiros | `sabia-4-thinking` (Maritaca) | 0.0 |
| **Produtividade** | `PRODUCTIVITY` | Laudo, e-mail, resumo — não-clínico | `gpt-5.4-nano` | 0.7 |
| **Saudação** | `OFF_TOPIC` | "oi", "bom dia" | — (resposta local) | — |

> Temperature 0.0 nos modos clínicos é critério de segurança: respostas determinísticas e
> reproduzíveis. Só Produtividade usa 0.7, e ali o texto não é clínico.

#### RN-ORC-002: Regras da Triagem ✅ Implementado

- Modelo da triagem: **`gpt-5.4-nano`** (`app/services/triage_service.py`), timeout de **10 s**.
- A triagem retorna um índice de confiança (0–1). **Abaixo de 0.7**, o sistema pede ao médico
  que refine a pergunta (`CONFIANCA_MINIMA_TRIAGEM`).
- **Fallback:** modelo de triagem indisponível → classifica como `QUICK_SEARCH`.
- O resultado da triagem é registrado no log de auditoria.

#### RN-ORC-003: Modos que a triagem NUNCA escolhe ✅ Implementado

`DATA_OCEAN` só entra por **seleção explícita do médico** (`MODOS_NAO_TRIADOS`). Motivo: é
lento e cobrado por uso de ferramenta — uma consulta medida custou US$ 0,647945, contra
~US$ 0,03 de uma pergunta clínica comum. Entrar nele por acidente de classificação queimaria
o teto semanal do médico numa pergunta.

#### RN-ORC-004: Promoção automática por anexo ✅ Implementado

**Anexo + modo sem visão → `EXAM_REVIEW`.** `upgrade_mode_for_attachments()`.

É regra de segurança clínica, não conveniência. A triagem lê **apenas o texto**: para "e esse
aqui?" com um exame anexado, ela devolvia `QUICK_SEARCH`, que roteia para `sonar-pro` — um
modelo **sem visão**. O resultado era uma resposta confiante sobre um exame que o médico via
na tela e o modelo não. `MODES_REQUIRING_VISION` impede o roteamento cego.

#### RN-ORC-005: Saudação não gasta API ✅ Implementado

Mensagens de até 40 caracteres reconhecidas como saudação recebem resposta local constante,
sem chamada a modelo nenhum (`is_off_topic_greeting()`).

#### RN-ORC-006: Toggle Rápido/Detalhado ✅ Implementado

Campo `effort` na requisição: **rápido = 700 tokens**, **detalhado = 4096**
(`EFFORT_MAX_TOKENS`). Afeta latência e custo de saída.

#### RN-ORC-007: Limite de entrada ✅ Implementado

**4.000 caracteres** por prompt (`max_prompt_chars`), e no máximo **5 anexos** por mensagem.

### 3.4 Agentes Especializados

#### 3.4.1 Modo Bizu (Ação Rápida) ✅ Implementado

**Modelo:** Perplexity Sonar Pro

**Propósito:** Respostas rápidas com busca online (posologias, protocolos, condutas diretas).

**RN-BIZU-001:**
- Resposta em Markdown estruturado: medicação, dose, via, frequência, observações.
- Timeout: 10 segundos. Fallback: Gemini 2.5 Flash.
- Validação PubMed ativa neste modo.
- Cache semântico ativo com TTL 30 dias.

#### 3.4.2 Modo Sherlock (Raciocínio Clínico) ✅ Implementado

**Modelo:** `claude-sonnet-4-6` (Anthropic)

**Propósito:** Discussão de casos clínicos, diagnósticos diferenciais, análise de quadros complexos.

**RN-SHERLOCK-001:**
- Resposta DEVE seguir estrutura obrigatória de 5 seções:
  1. **Hipóteses diagnósticas** — ranqueadas por probabilidade, SEM percentagens numéricas
  2. **Exames complementares** — divididos em "Urgentes" e "Complementares"
  3. **Conduta sugerida** — imediata e seguimento
  4. **Red Flags** — em negrito, sinais de alarme
  5. **Referências** — apenas diretrizes e artigos reais; NUNCA inventar PMIDs
- O modelo DEVE respeitar TODAS as características do paciente informadas (sexo, idade, comorbidades).
- NUNCA sugerir condições exclusivas de um sexo para o sexo oposto.
- Timeout: 30 segundos. Fallback: GPT-4o → Gemini 2.5 Flash.
- Cache semântico ativo **apenas para perguntas genéricas** (sem dados de paciente específico).

#### 3.4.3 Modo Farmácia (Segurança Farmacológica) ✅ Implementado

**Fonte:** PharmaDB (base local)

**Propósito:** Checagem de interações medicamentosas com semáforo de segurança.

**RN-FARM-001: Semáforo de Segurança**

| Nível | Cor | Significado | Ação do Sistema |
|-------|-----|-------------|-----------------|
| 1 | 🟢 Verde | Sem interação conhecida | Prosseguir |
| 2 | 🟡 Amarelo | Interação leve/moderada | Alerta informativo |
| 3 | 🟠 Laranja | Interação significativa | Alerta + recomendação de ajuste |
| 4 | 🔴 Vermelho | Contraindicação grave | Bloqueio + justificativa obrigatória |

**RN-FARM-002:**
- **Só `PHARMA_CHECK` exige 2+ medicamentos** — é o modo de *interação*. Os outros três
  (`PHARMA_BULA`, `PHARMA_RECEITA`, `PHARMA_GENERICO`) operam sobre **um** medicamento
  nomeado, e a triagem os classifica assim de propósito.
- Confiança mínima da triagem para rotear a `PHARMA_CHECK`: **0.90**
  (`PHARMA_CHECK_MIN_CONFIDENCE`), acima do 0.7 geral — errar o roteamento aqui devolve
  um semáforo de risco sobre a pergunta errada.
- Histórico de alertas é armazenado em `pharma_alerts` para auditoria.
- Cache semântico DESABILITADO nos quatro modos — segurança farmacológica exige consulta real.
- Validação PubMed não se aplica.

---

## 4. Validação Científica via PubMed ✅ Implementado

### 4.1 Definição

Camada de fact-checking automático executada após a resposta de cada agente clínico (Bizu e Sherlock). Objetivo: detectar alucinações, verificar citações e alertar quando o modelo está desatualizado.

### 4.2 Arquitetura de Duas Trilhas Paralelas

#### Trilha A — Verificação de Citações

1. `gpt-5.4-nano` extrai todas as referências mencionadas na resposta (guidelines + artigos seminais com autores)
2. Para cada citação, busca no PubMed:
   - Formato `Autor et al. Ano` → query `Autor[author] AND Ano[pdat]`
   - Outros formatos → busca por `[tiab]` com fallback por palavras-chave + filtro de guideline
3. Retorna `verified: true` + PMID real se encontrado no PubMed

#### Trilha B — Detecção de Diretrizes Mais Recentes

1. Busca guidelines publicadas nos **últimos 24 meses** sobre o tópico detectado
2. Filtra as que já foram citadas na resposta (são novidades reais que o modelo não conhecia)
3. Sinaliza `outdated_alert: true` se houver diretrizes pós-cutoff do modelo

### 4.3 Fórmula do Confidence Score

#### RN-ORC-003: Score de Confiança Científica

| Situação | Score |
|----------|-------|
| Sem citações na resposta | 0.10 |
| Citações presentes (base) | 0.60 |
| +0.10 por citação verificada no PubMed | máx +0.30 |
| +0.10 se sem guidelines mais novas | bônus de atualização |
| −0.15 por guideline mais nova encontrada | penalidade de desatualização |

**Exemplos práticos:**
- 2 citações verificadas + sem novidades → `0.60 + 0.20 + 0.10 = **0.90**`
- 1 verificada + 1 nacional (não indexada no PubMed) + sem novidades → `0.60 + 0.10 + 0.10 = **0.80**`
- 0 verificadas + 1 guideline nova encontrada → `0.60 − 0.15 = **0.45**`

> **Nota:** Diretrizes nacionais (brasileiras, ministeriais) são clinicamente válidas mas não estão no PubMed. O sistema **recompensa verificações** sem punir ausências — score 0.80 para respostas com diretrizes nacionais é esperado e correto.

### 4.4 Campos Retornados na Resposta

```json
{
  "confidence_score": 0.90,
  "low_evidence_alert": false,
  "outdated_alert": false,
  "cited_guidelines_verified": [
    {
      "title": "2020 ESC Guidelines for Atrial Fibrillation",
      "pmid": "32860505",
      "verified": true
    },
    {
      "title": "Diretriz Brasileira de FA - ABC 2016",
      "pmid": null,
      "verified": false
    }
  ],
  "newer_guidelines_found": []
}
```

**RN-ORC-003 adicional:**
- Score < 0.5 → `low_evidence_alert: true` — exibir alerta ao médico
- `outdated_alert: true` → exibir lista de diretrizes mais recentes disponíveis
- Timeout: 15 segundos com fallback automático (`confidence_score: 0.0, fallback: true`)

---

## 5. Cache Semântico ⚠️ Implementado, mas DESLIGADO

> **`SEMANTIC_CACHE_ENABLED = False`** (`app/core/config.py:86`). O código existe inteiro e
> funciona; o que não existe é o cache rodando em produção.
>
> **Não é bug — é decisão medida.** Em 90 dias e 240 interações houve **zero acertos**, e a
> tentativa de servir o cache custava 500–1150 ms *antes do primeiro token*. Ou seja: só
> atrasava. A causa provável é a natureza da pergunta clínica, que raramente se repete entre
> médicos diferentes com similaridade ≥ 0.88.
>
> **Consequência prática:** ao dimensionar custo de API, **não conte com economia de cache**.
> Toda pergunta hoje vai para o modelo.
>
> Religar exige re-medir. O caminho vetorial é o que foi medido como inútil; o fast-path
> exato no Redis (abaixo) é mais barato e não foi avaliado separadamente.

### 5.1 Definição

Camada que intercepta consultas antes de enviá-las aos modelos. Se uma pergunta
semanticamente equivalente já foi respondida recentemente, retorna a resposta cacheada sem
consumir novos tokens.

Há **dois caminhos**, e o documento originalmente só descrevia o segundo:

1. **Fast-path exato (Redis)** — hash do prompt normalizado, TTL de 30 dias. Evita as duas
   chamadas à OpenAI (normalização + embedding).
2. **Caminho vetorial (pgvector)** — normaliza, gera embedding e busca por similaridade.

### 5.2 Arquitetura Técnica

**Storage:** PostgreSQL + extensão pgvector (não Redis — decisão de arquitetura para manter consistência transacional e evitar dependência de serviço adicional).

**Pipeline por query:**

```
Prompt recebido
      │
      ▼
Guardrail + Normalização (gpt-5.4-nano)
  ├── Verifica se é cacheável (sem dados de paciente específico)
  └── Expande siglas médicas:
      FA → fibrilação atrial
      ICFEr → insuficiência cardíaca com fração de ejeção reduzida
      PAC → pneumonia adquirida na comunidade
      HAS → hipertensão arterial sistêmica
      DM → diabetes mellitus
      IAM → infarto agudo do miocárdio
      AVC → acidente vascular cerebral
      (e demais siglas clínicas comuns)
      │
      ▼ (se cacheável)
Embedding (text-embedding-3-small, 1536 dimensões)
      │
      ▼
pgvector cosine similarity lookup
  ├── sim ≥ 0.88 → HIT: retorna resposta cacheada (cache_hit: true)
  └── sim < 0.88 → MISS: chama agente, armazena ao final
```

### 5.3 Regras de Negócio do Cache

#### RN-CACHE-001: Elegibilidade por Modo

| Modo | Cache | Critério |
|------|-------|----------|
| Bizu (`QUICK_SEARCH`) | ✅ Ativo | Sempre que o guardrail aprovar |
| Sherlock (`CLINICAL_REASONING`) | ✅ Ativo com restrição | Apenas perguntas genéricas — qualquer dado de paciente bloqueia |
| Farmácia (`PHARMA_CHECK`) | ❌ Desabilitado | Segurança exige consulta real sempre |
| Produtividade (`PRODUCTIVITY`) | ❌ Desabilitado | Tarefas individuais, sem benefício de cache |

**Indicadores de não-cacheável (Sherlock):** idade, sexo, valores laboratoriais, doses específicas, referências temporais ("há 3 dias"), "meu paciente", dados de exame com valores numéricos.

#### RN-CACHE-002: Parâmetros Técnicos

| Parâmetro | Valor | Justificativa |
|-----------|-------|---------------|
| Modelo de embedding | text-embedding-3-small | Custo baixo, 1536 dims, alta qualidade semântica |
| Dimensões | 1.536 | Padrão OpenAI para esse modelo |
| Threshold de similaridade | **0.88** | `SIMILARITY_THRESHOLD`. Era 0.92; foi baixado sem que o valor produzisse acertos (ver §5) |
| TTL | 30 dias | Diretrizes mudam com baixa frequência |
| Índice pgvector | IVFFlat (cosine, lists=100) | Performance em escala |

#### RN-CACHE-003: Registro ✅ Implementado

- Toda resposta cacheada DEVE ser marcada como `cache_hit: true` na resposta e no audit log.
- O custo registrado em cache hits é o custo da resposta original (já pago anteriormente).
- Métrica de cache hit rate: ❌ Endpoint de métricas pendente.

### 5.4 Estrutura da Tabela

```sql
CREATE TABLE semantic_cache (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    mode              VARCHAR(50) NOT NULL,
    normalized_prompt TEXT NOT NULL,           -- prompt após expansão de siglas
    prompt_embedding  vector(1536) NOT NULL,   -- pgvector
    response_json     JSONB NOT NULL,          -- resposta completa serializada
    hit_count         INTEGER DEFAULT 0,       -- quantas vezes foi reutilizado
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    expires_at        TIMESTAMPTZ NOT NULL     -- created_at + 30 dias
);
```

---

## 6. Auditoria, Logs e Data Monetization

### 6.1 Registro Obrigatório de Interações ✅ Implementado

TODA interação DEVE gerar um registro completo. Esses registros servem para auditoria interna e monetização futura via insights anonimizados.

#### RN-AUD-001: Campos Obrigatórios no Log

| Campo | Tipo | Status |
|-------|------|--------|
| `interaction_id` | UUID v4 | ✅ |
| `timestamp` (início e fim) | ISO 8601 UTC | ✅ |
| `user_id` | String | ✅ |
| `organization_id` | String / null | ✅ |
| `feature` | Enum: AGREGADOR / ORQUESTRADOR | ✅ |
| `mode` | Enum: QUICK_SEARCH / CLINICAL_REASONING / PHARMA_CHECK / PRODUCTIVITY | ✅ |
| `prompt_text` | Text anonimizado (sem PII) | ✅ |
| `model_used` | String | ✅ |
| `response_time_ms` | Integer | ✅ |
| `cache_hit` | Boolean | ✅ |
| `token_cost_usd` | Decimal | ✅ |
| `confidence_score` | Float 0–1 | ✅ |
| `specialty_detected` | String | ✅ |
| `medication_mentioned` | String[] | ✅ |
| `pharma_alerts` | JSON[] | ✅ |
| `pubmed_cited_verified` | Integer | ✅ |
| `pubmed_newer_found` | Integer | ✅ |
| `pubmed_outdated_alert` | Boolean | ✅ |

### 6.2 Data Monetization

#### RN-DATA-001: Regras de Monetização de Dados

- Os dados vendidos DEVEM ser 100% anonimizados — sem possibilidade de identificação de médico ou paciente.
- Os campos `specialty_detected` e `medication_mentioned` são os ativos primários para venda de insights.
- Insights DEVEM ser agregados em nível estatístico (ex: "42% das consultas de cardiologia envolvem enalapril"), nunca em nível individual.
- A plataforma DEVE manter `consent_log` explícito do usuário autorizando uso anonimizado (LGPD, Art. 7 e 11). ✅ Tabela criada / ✅ Infraestrutura de registro pronta / ❌ Consentimento específico de monetização não coletado

> **BLOQUEIO REGULATÓRIO — leia antes de ativar esta regra.**
> RN-DATA-001 **não pode ser ativada** enquanto o consentimento
> `uso_dados_anonimizados` não estiver sendo coletado. O aceite de termos que o
> onboarding registra hoje (`termos_e_privacidade`) **não cobre** este uso:
> monetização é finalidade secundária sobre dado sensível de saúde e, pelo
> Art. 11, exige consentimento **específico e destacado** — checkbox próprio,
> desmarcado por padrão, separado do aceite obrigatório. Amarrar os dois
> invalida ambos.
>
> A infraestrutura já existe (`app/services/consent_service.py`, constante
> `USO_DADOS_ANONIMIZADOS`, rota de revogação). Falta a tela e a decisão de
> produto — não falta código de base.
- Dados de interações medicamentosas são especialmente valiosos para farmacovigilância.

---

## 7. Segurança, Privacidade e LGPD

### 7.1 Anonimização Obrigatória (Middleware DLP) ✅ Implementado

Nenhuma informação PII pode sair do backend. O Middleware DLP intercepta toda mensagem antes do envio para APIs externas.

#### RN-SEC-001: Regras de Substituição

| Dado Detectado | Substituição | Exemplo |
|----------------|-------------|---------|
| Nomes próprios | `[PACIENTE]` ou `[MÉDICO]` | "João Silva" → `[PACIENTE]` |
| CPF / RG / Cartão SUS | `[DOCUMENTO]` | "123.456.789-00" → `[DOCUMENTO]` |
| Telefones / E-mails | `[CONTATO]` | "(11) 99999-0000" → `[CONTATO]` |
| Endereços | `[ENDEREÇO]` | "Rua das Flores, 123" → `[ENDEREÇO]` |

#### RN-SEC-002: Proteção de Dados

- Toda comunicação com APIs externas DEVE usar HTTPS/TLS.
- Logs de auditoria DEVEM ser imutáveis e com acesso restrito.
- A plataforma NÃO DEVE armazenar dados PII de pacientes após sanitização.

---

## 8. Disponibilidade e Resiliência

### 8.1 Política de Fallback ✅ Implementado

| Serviço Primário | Fallback | Timeout | Ação Adicional |
|-----------------|----------|---------|----------------|
| `gpt-5.4-nano` (Triagem) | Classificar como QUICK_SEARCH | 10s | Log de erro |
| Perplexity Sonar Pro (Bizu) | Gemini 2.5 Flash | 10s | Log de erro |
| `claude-sonnet-4-6` (Sherlock) | GPT-4o → Gemini 2.5 Flash | 30s | Log de erro |
| PharmaDB (Farmácia) | Mensagem de indisponibilidade | 10s | Flag na resposta |
| PubMed (Validação) | `fallback: true`, sem validação | 15s | Alerta ao médico |
| Cache Semântico | Bypass silencioso, chama agente | — | Log warning |

---

## 9. Interface e UX — Mobile First

*(Responsabilidade do time de Frontend — backend preparado para suportar todos os requisitos abaixo)*

### 9.1 Diretriz Geral

A plataforma DEVE ser projetada com abordagem **Mobile First** (viewport base: 375px). A migração futura para app nativo (iOS/Android) deve ser viável sem redesign estrutural.

### 9.2 Regras de Layout e Componentes

#### RN-UX-001: Elementos Proibidos

- NÃO utilizar hover states como única forma de interação.
- NÃO utilizar layouts side-by-side fixos que não colapsem em coluna única.
- NÃO utilizar tabelas horizontais com mais de 3 colunas sem scroll horizontal.
- NÃO utilizar fontes abaixo de 14px para corpo de texto.
- NÃO utilizar áreas de toque menores que 44×44px.

#### RN-UX-002: Padrões Obrigatórios

- Todo componente DEVE ser funcional em viewport de 375px sem scroll horizontal.
- Navegação principal: bottom navigation bar (não sidebar).
- Campo de input fixo na parte inferior da tela (padrão chat).
- Respostas em Markdown com line-height ≥ 1.5.
- Comparação multi-modelo (Agregador): abas/swipe no mobile.

#### RN-UX-003: Performance Mobile

- First Contentful Paint < 1.5s em conexão 4G.
- Bundle JS inicial < 200KB (gzipped).
- **Respostas de IA via streaming (token a token).** ⚠️ Backend: providers implementados, endpoint SSE pendente.
- Lazy loading em imagens e assets.

#### RN-UX-004: Preparação para App Nativo

- Lógica de negócio separada da camada de apresentação.
- Comunicação 100% via API REST.
- Sistema de notificações preparado para push (FCM/APNs).
- Áudio via `MediaRecorder` API nativa do navegador.

#### RN-UX-005: Formatação de Respostas Médicas

| Elemento | Regra |
|----------|-------|
| Posologias | SEMPRE em tabela vertical no mobile |
| Red Flags | Negrito + fundo vermelho sutil, visíveis sem scroll |
| Referências (PMIDs) | Colapsável por padrão, expandir com tap |
| Semáforo Farmácia | Badge colorido ≥ 44px com label textual |
| Disclaimer | Rodapé fixo discreto |

---

## 10. Status de Implementação

### Orquestrador

| Módulo | Status | Observações |
|--------|--------|-------------|
| Pipeline completo | ✅ Produção | 12 etapas |
| Triagem inteligente | ✅ Produção | `gpt-5.4-nano`, confiança, fallback |
| Bizu (QUICK_SEARCH) | ✅ Produção | `sonar-pro` + fallback Gemini |
| Sherlock (CLINICAL_REASONING) | ✅ Produção | `claude-sonnet-4-6`, temperature=0 |
| Exame (EXAM_REVIEW) | ✅ Produção | Visão; promoção automática por anexo (RN-ORC-004) |
| Farmácia — 4 modos | ✅ Produção | PharmaDB local com semáforo |
| Data Ocean (DATA_OCEAN) | ✅ Produção | Maritaca; só por seleção explícita (RN-ORC-003) |
| Produtividade | ✅ Produção | `gpt-5.4-nano`, temperature=0.7 |
| Saudação (OFF_TOPIC) | ✅ Produção | Resposta local, sem custo de API |
| **Streaming SSE** | ✅ **Produção** | `POST /orquestrador/stream`, 6 eventos. Não suporta PHARMA_CHECK |
| Toggle Rápido/Detalhado | ✅ Produção | 700 / 4096 tokens de saída |
| Validação PubMed (duas trilhas) | ✅ Produção | Trilha A + B paralelas |
| Confidence score PubMed | ✅ Produção | Fórmula baseada em verificações |
| **Cache semântico** | ⚠️ **Desligado** | Código pronto; `SEMANTIC_CACHE_ENABLED=False`. Ver §5 |
| DLP Middleware | ✅ Produção | Sanitização PII + NER |
| Audit Log completo | ✅ Produção | Todos os campos RN-AUD-001 |
| Extração de medicamentos | ✅ Produção | `gpt-5.4-mini` |
| Detecção de especialidade | ✅ Produção | `gpt-5.4-nano` |
| Cálculo de custo por tokens | ✅ Produção | Via tabela `model_pricing` |
| Teto semanal de custo | ✅ Produção | US$ 5,00/usuário, 429 ao estourar |
| Circuit breaker | ✅ Produção | PharmaDB, Curseduca, OpenAI auxiliares |
| **Métricas de cache hit rate** | ✅ **Produção** | `vigilancia_service`, roda a cada 6h com alarme |
| Anexos (PDF, DOCX, XLSX, imagens) | ✅ Produção | Máx. 5 por mensagem, 100 páginas de PDF |
| Áudio / Whisper | ⏳ Backlog | — |
| Busca por palavra-chave no histórico | ⏳ Backlog | Listagem e detalhe existem; falta a busca textual |
| Exportação PDF/CSV do histórico | ⏳ Backlog | A exportação LGPD (JSON) existe — ver §7 |

### Outros módulos

| Módulo | Status | Onde |
|--------|--------|------|
| Calculadoras Científicas | ✅ Produção | §11 e `docs/Calculadoras_Cientificas_Regras_de_Arquitetura_v1.0.md` |
| Notícias | ✅ Produção | §12 |
| Localizador de DEA | ✅ Produção | §13 |
| Identidade profissional / onboarding | ✅ Produção | §14 |
| Landing pages | ✅ Produção | 3 LPs + backend |
| Pastas com evolução clínica | ✅ Produção | §15 |
| Agregador de IA | ⚠️ Fora da interface | Backend intacto — ver §2 |

### Frontend

| App | Status |
|-----|--------|
| `frontend-app` (chat do Orquestrador) | ✅ Produção |
| `calculadoras-app` | ✅ Produção |
| `noticias-app` | ✅ Produção |
| `dea-app` (metrônomo + mapa) | ✅ Produção |
| 3 landing pages | ✅ Produção |
| App mobile nativo | ⏳ Fase futura |

### Conformidade e documentos

| Item | Status | Observações |
|------|--------|-------------|
| Aceite de termos registrado (LGPD art. 8) | ✅ Produção | `consent_logs` com IP, user-agent e versão |
| Portabilidade (art. 18, V) | ✅ Produção | `GET /auth/me/export`, rate limit 5/hora |
| Exclusão de conta | ✅ Produção | Apaga a cascata e anonimiza o audit log |
| Expurgo por prazo | ✅ Produção | Roda no backend a cada 24h, com alarme de atraso |
| Scrubbing no Sentry | ✅ Produção | Fail-closed: erro no scrubbing descarta o evento |
| Termos de Uso próprios do Médico 360 | ❌ Ausente | O documento linkado é o do **Paciente 360**, produto diferente |
| Política de Privacidade cobrindo dado de saúde | ⚠️ Lacuna | Texto vigente (05/08/2024) não trata dado de saúde como sensível |
| Consent de monetização (art. 11) | 🚫 Bloqueia RN-DATA-001 | Infra pronta; falta tela e decisão de produto |
| Exclusão de conversa pelo médico | ❌ Ausente | `Conversation.status` é lido como filtro e nunca definido como `False` |

---

## 11. Calculadoras Científicas

Módulo de calculadoras clínicas baseadas em diretrizes, com frontend próprio
(`calculadoras-app`) e extração de valores por IA a partir de texto de exame.

> **As regras deste módulo vivem em `docs/Calculadoras_Cientificas_Regras_de_Arquitetura_v1.0.md`**,
> com as `RN-CALC-*` que o código referencia diretamente. Não duplicamos aqui — manter a
> mesma regra em dois documentos é como eles divergem.

O que vale registrar neste documento, por ser decisão de produto:

- **Uma versão ativa por calculadora**, garantida por índice único parcial no banco. Versões
  históricas continuam existindo para auditar execuções antigas.
- **Toda execução deixa rastro.** Não há modo "dry run": cálculo clínico sem registro não é
  aceitável (RN-CALC-SCHEMA-005).
- **Extração por IA é assistiva, nunca automática.** O médico confere os valores extraídos do
  exame antes de calcular. Modelo: `gpt-5.4-mini`, timeout de 15 s, no máximo 8 extrações
  simultâneas por processo.
- Campo de texto para extração: **2.000 caracteres**.
- Calculadoras em produção: CHA₂DS₂-VASc, HAS-BLED, PREVENT (cardiologia), CURB-65
  (infectologia), Cockcroft-Gault (nefrologia).

---

## 12. Notícias

Feed clínico por tema, com curadoria automatizada a partir do PubMed e digest por e-mail.

### RN-NEWS-001: Dois limiares distintos, de propósito ✅ Implementado

| Limiar | Valor | Por quê |
|---|---|---|
| `news_feed_score_minimo` | **0.3** | Navegar é barato: item fraco no feed custa um scroll |
| `news_digest_score_minimo` | **0.6** | **Interromper é caro**: e-mail exige mais |

Um único limiar forçaria escolher entre um feed vazio e um e-mail irrelevante.

### RN-NEWS-002: Personalização em dois eixos ✅ Implementado

- **Temas** escolhidos pelo médico (taxonomia curada).
- **Palavras-chave** livres: máximo **10**, mínimo de **4 caracteres** cada — "IC" e "PA"
  trariam lixo por ambiguidade.

Quando o feed tem poucos itens, ele é **preenchido** com temas da especialidade que o médico
não marcou. Esses itens de preenchimento **nunca disparam o digest**: completar a tela é
cortesia de navegação, não motivo para interromper alguém.

### RN-NEWS-003: Sugestão social exige amostra ✅ Implementado

Abaixo de **20 usuários** da especialidade, a tela diz "Selecionamos para quem é de X". Acima,
mostra o que os colegas mais acompanham, com percentuais reais. Sem esse piso, a frase social
seria estatística inventada.

### RN-NEWS-004: Modelo do redator é configurável ✅ Implementado

`news_writer_model` (hoje `claude-sonnet-5`) vive em configuração, **não em constante**. Ao
migrar do repositório antigo o valor virou constante uma vez, e teria rebaixado o redator em
produção sem ninguém perceber.

**Agenda:** coleta às 11h UTC, digest às 12h UTC.

> ⚠️ **A taxonomia de temas ainda não passou por revisão médica.** É ela que decide se o feed
> acerta o interesse do médico.

---

## 13. Localizador de DEA

Mapa colaborativo de desfibriladores externos automáticos, mais um metrônomo de RCP.
**É o único módulo público do produto**: sem login, sem embed, sem identidade.

Público-alvo inicial: participantes dos cursos de ACLS ministrados pela empresa — o médico
instala pelo metrônomo, que é útil sozinho, e descobre o mapa.

### RN-DEA-001: Sem autenticação, por decisão clínica ✅ Implementado

Numa parada cardiorrespiratória não há tempo para autenticar, e quem socorre raramente é quem
tem a conta. Exigir login para cadastrar mataria a base antes de ela existir.

### RN-DEA-002: A confiança envelhece ✅ Implementado

O app **nunca afirma que há um DEA num lugar**. Diz o que se sabe e há quanto tempo:
"confirmado por 3 pessoas · há 12 dias", ou "ainda não confirmado por ninguém".

| Nível | Quando |
|---|---|
| `alta` | 2+ confirmações e verificação ≤ 90 dias |
| `media` | ao menos 1 confirmação, ou `alta` que envelheceu |
| `baixa` | nunca confirmado, ou passou de 365 dias |
| `contestado` | negativas ≥ positivas — **domina qualquer histórico positivo** |

Correr 300 m até um DEA que não existe mais é tempo fora da janela de sobrevida. Por isso a
confiança decai sozinha, e uma contestação recente pesa mais que confirmações antigas.

**A API não devolve score numérico** — só o rótulo e os fatos crus. Um número viraria
porcentagem em alguma tela, e porcentagem parece medida.

### RN-DEA-003: Registro novo nasce "não confirmado" ✅ Implementado

Aparece no mapa **imediatamente**, marcado. Segurar o pin até alguém validar mataria a
contribuição exatamente onde ela é mais valiosa: um bairro onde ainda não há usuários para
validar coisa alguma.

Promove a "ativo" quando alguém **de outra origem** confirma.

### RN-DEA-004: Antivandalismo sem login ✅ Implementado

| Limite | Valor |
|---|---|
| Cadastros por origem | 5/hora |
| Verificações por origem | 20/hora |
| Locais novos numa mesma região (~1 km) | 5/hora |

**Verificações não contam para o limite de densidade** — trinta alunos confirmando o mesmo
DEA durante um curso de ACLS é o caso de uso, não um ataque.

### RN-DEA-005: Nada é deletado ✅ Implementado

"Duas pessoas procuraram e não acharam" é informação útil para a terceira. Registros
contestados continuam no mapa, marcados; só `removido` e `spam` saem da listagem, e as linhas
permanecem no banco.

### RN-DEA-006: Contribuidor anônimo, sem rastro persistente ✅ Implementado

Identificado por `sha256(sal ‖ ip ‖ dia)`. O componente de data faz o identificador rotacionar
a cada 24 h: dá para impedir que alguém confirme o próprio cadastro e aplicar limite por hora,
mas não para seguir uma pessoa ao longo de meses. O sal é obrigatório em produção.

---

## 14. Identidade profissional

### RN-IDENT-001: Precedência de fontes ✅ Implementado

A especialidade do médico pode vir de cinco fontes, nesta ordem:

```
admin > cadastro > cfm > waid_grupo > declarado
```

### RN-IDENT-002: O médico não reescreve a própria especialidade ✅ Implementado

`users.specialty` **define acesso a conteúdo pago**. Deixar o campo livre seria deixar o
usuário escolher o que pode ver.

A correção prevista na LGPD (art. 18, III) é atendida **pelo suporte**, que edita com a fonte
`admin` — o bloqueio é de tela, não de banco.

### RN-IDENT-003: CRM não é exigido no cadastro ✅ Implementado

Exigir CRM antes de deixar entrar barrava estudantes e residentes, que são parte do público.

---

## 15. Pastas com evolução clínica

### RN-PASTA-001: Dois tipos de pasta ✅ Implementado

`clinical` (paciente) e `general` (estudo/tema). O tipo decide **como o contexto é marcado no
prompt** enviado ao modelo — não é só rótulo de interface.

### RN-PASTA-002: A evolução é contexto declarado, não inferido ✅ Implementado

Texto que o **médico escreve** sobre o paciente, com no máximo **8.000 caracteres** (~2.500
tokens). É custo recorrente: entra em toda mensagem daquela pasta.

### RN-PASTA-003: DLP na escrita, não na leitura ✅ Implementado

Este campo era o único texto clínico que entrava no banco sem passar pelo DLP. Sanitizar na
leitura deixaria o dado sensível gravado.

### RN-PASTA-004: Campo ausente significa "não mexa" ✅ Implementado

No `PUT`, `clinical_context: null` = preserve; string vazia = apague. Antes dessa distinção,
**renomear uma pasta apagava a evolução do paciente sem aviso**.

---

## 16. Glossário

| Termo | Definição |
|-------|-----------|
| Agregador | Interface unificada para consulta simultânea a múltiplos modelos de IA |
| Orquestrador | Pipeline inteligente (The Gatekeeper) que classifica e roteia para agentes especializados |
| Cache Semântico | Camada pgvector que retornaria respostas cacheadas para similaridade cosine ≥ 0.88 — **desligada em produção**, ver §5 |
| Modo Bizu | Agente de ação rápida para consultas simples (doses, bulas, protocolos) |
| Modo Sherlock | Agente de raciocínio clínico para diagnósticos diferenciais e casos complexos |
| Modo Farmácia | Agente de segurança farmacológica com semáforo de risco |
| DLP Middleware | Camada de Data Loss Prevention que sanitiza PII antes do envio para APIs externas |
| Non-SaMD | Classificação regulatória: software NÃO é dispositivo médico |
| PMID | PubMed Identifier — código único de artigos na base PubMed/MEDLINE |
| Confidence Score | Score 0–1 baseado em verificações reais de citações no PubMed |
| Outdated Alert | Alerta quando há diretrizes publicadas após o cutoff do modelo que não foram citadas |
| PharmaDB | Base local de interações medicamentosas com semáforo de segurança |
| pgvector | Extensão PostgreSQL para busca por similaridade de vetores de embedding |
| Temperature | Parâmetro de aleatoriedade dos modelos de IA (0.0 = determinístico) |
| Data Monetization | Venda de insights anonimizados e agregados para a indústria de saúde |
| SSE | Server-Sent Events — protocolo para streaming de respostas token a token |

---

## 17. Controle de Versão

| Versão | Data | Alterações |
|--------|------|-----------|
| 1.0 | 04/05/2026 | Criação inicial |
| 2.0 | 04/05/2026 | + Cache Semântico, Data Monetization, DLP Middleware, modo Produtividade |
| 2.1 | 04/05/2026 | + Seção 8: UX Mobile First |
| 2.2 | 19/05/2026 | Atualização completa para refletir estado de produção. Implementação de validação PubMed de duas trilhas (Trilha A: verificação de citações + Trilha B: detecção de diretrizes recentes). Confidence score reformulado (recompensa verificações, não penaliza ausências). Cache semântico implementado em pgvector com normalização de siglas antes do embedding, guardrail para CLINICAL_REASONING e threshold 0.92. Temperature=0 definido como padrão para modos clínicos. System prompts de Sherlock atualizados com regras invioláveis (sem percentagens, respeito ao sexo do paciente). Status de implementação adicionado por módulo. |
| 2.3 | 10/09/2026 | **Alinhamento ao código após 4 meses de defasagem.** Corrigidos 7 nomes de modelo de IA — nenhum existia no código (a triagem é `gpt-5.4-nano`, não GPT-4o-mini; Sherlock é `claude-sonnet-4-6`); threshold do cache 0.92 → **0.88**; `role` default `free_user` → **`beta_user`**. Registrado que o **cache semântico está DESLIGADO** por decisão medida (zero acertos em 240 interações), apesar de o documento anterior marcá-lo como em produção. Registrado o **teto de US$ 5,00/semana** por usuário, que contradizia o "acesso irrestrito" da §1.2. A §3 passou de 4 para os **10 modos** reais, com RN-ORC-003 a 007 novas. RN-FARM-002 corrigida: exigir 2 medicamentos vale só para `PHARMA_CHECK`, não para os outros 3 modos de farmácia — implementar pela regra antiga quebraria três modos. §2 (Agregador) marcada como histórica: saiu da interface. Status de implementação refeito — SSE e métricas de cache estavam como backlog e estão em produção; "interface web não iniciada" com 7 frontends no ar. Acrescentadas §11 a §15 (calculadoras, notícias, DEA, identidade profissional, pastas com evolução clínica), módulos que não existiam no documento. |
