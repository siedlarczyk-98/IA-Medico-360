# MÉDICO 360 — Regras de Negócio v2.2
**CONFIDENCIAL**

Plataforma de Assistência Clínica com Inteligência Artificial

---

**DOCUMENTAÇÃO DE REGRAS DE NEGÓCIO**

Agregador de IA + Orquestrador Multi-Agente

Cache Semântico + Validação Científica PubMed + Data Monetization

**Versão 2.2 — Maio 2026**

**Status: Em Produção (Sprint 2)**

---

## Sumário

1. Visão Geral do Produto
2. Feature 1: Agregador de IA
3. Feature 2: Orquestrador Multi-Agente Clínico
4. Validação Científica via PubMed
5. Cache Semântico
6. Auditoria, Logs e Data Monetization
7. Segurança, Privacidade e LGPD
8. Disponibilidade e Resiliência
9. Interface e UX — Mobile First
10. Status de Implementação
11. Glossário
12. Controle de Versão

---

## 1. Visão Geral do Produto

### 1.1 Descrição

O Médico 360 é uma plataforma SaaS de assistência clínica baseada em Inteligência Artificial, projetada para médicos e profissionais de saúde. A plataforma oferece duas features principais — **Agregador de IA** e **Orquestrador Multi-Agente** — que permitem ao profissional consultar múltiplos modelos de IA para apoio em tomadas de decisão clínica, pesquisa farmacológica e raciocínio diagnóstico.

### 1.2 Estratégia de Lançamento

**Fase atual:** Acesso 100% gratuito. Todos os usuários têm acesso irrestrito a todas as funcionalidades (Agregador + Orquestrador completo). Não há diferenciação de planos ou restrições por perfil clínico nesta fase.

**Objetivo:** Validação de produto, aquisição de base de usuários e coleta de dados para monetização futura via insights anonimizados.

**Monetização futura:** Modelos de planos pagos, limites por perfil e B2B serão definidos em fase posterior com base nos dados coletados.

### 1.3 Posicionamento Jurídico

**Classificação:** Non-SaMD (Software as a Medical Device). A plataforma é uma ferramenta de apoio à decisão clínica, NÃO um instrumento de diagnóstico.

Todo output gerado pela plataforma DEVE conter disclaimer explícito:

> *"⚕️ Esta resposta é de suporte à decisão clínica. A conduta adotada é de responsabilidade exclusiva do médico assistente. As informações apresentadas não substituem avaliação clínica individualizada."*

### 1.4 Autenticação e Acesso

- O sistema DEVE validar o `user_role` proveniente do banco de dados ou token JWT.
- Nesta fase, todos os usuários autenticados recebem acesso completo (`role = "free_user"`).
- A estrutura de roles DEVE ser projetada para suportar expansão futura (`basic`, `pro`, `b2b_partner`) sem refatoração.

---

## 2. Feature 1: Agregador de IA

### 2.1 Definição

O Agregador de IA é uma interface unificada que permite ao médico realizar consultas a múltiplos modelos de IA simultaneamente ou de forma seletiva. O profissional escolhe quais modelos deseja consultar e recebe as respostas em um único painel comparativo.

### 2.2 Modelos de IA Disponíveis

| Modelo | Provider | Caso de Uso | Custo Relativo |
|--------|----------|-------------|----------------|
| Claude Sonnet 4 | Anthropic | Raciocínio clínico avançado | Médio |
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
[2] Triagem Inteligente (GPT-4o-mini) — classifica modo + confiança
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

| Modo (Produto) | Código Interno | Critério | Modelo | Temperature |
|----------------|---------------|----------|--------|-------------|
| **Bizu** | `QUICK_SEARCH` | Dúvida direta: posologia, CID, conduta rápida, doses | Perplexity Sonar Pro | 0.0 |
| **Sherlock** | `CLINICAL_REASONING` | Caso clínico, diagnóstico diferencial, quadro complexo | Claude Sonnet 4 | 0.0 |
| **Farmácia** | `PHARMA_CHECK` | Interações medicamentosas, checagem de risco | PharmaDB | — |
| **Produtividade** | `PRODUCTIVITY` | Tarefas não-clínicas: laudo, email, resumo | GPT nano | 0.7 |

> **Nota:** Temperature 0.0 nos modos clínicos (Bizu e Sherlock) garante respostas determinísticas e reproduzíveis — critério de segurança clínica.

#### RN-ORC-002: Regras da Triagem ✅ Implementado

- A triagem DEVE retornar a classificação em menos de 2 segundos.
- A triagem DEVE retornar um índice de confiança (0–1). Se < 0.7, solicitar ao médico que refine a pergunta.
- Fallback: se o modelo de triagem estiver indisponível, classificar como BIZU.
- O resultado da triagem DEVE ser registrado no log de auditoria.

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

**Modelo:** Claude Sonnet 4 (Anthropic)

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
- Requer mínimo de 2 medicamentos identificados no prompt.
- Histórico de alertas DEVE ser armazenado em `pharma_alerts` para auditoria.
- Cache semântico DESABILITADO — segurança farmacológica exige consulta real sempre.
- Validação PubMed não aplicável neste modo.

---

## 4. Validação Científica via PubMed ✅ Implementado

### 4.1 Definição

Camada de fact-checking automático executada após a resposta de cada agente clínico (Bizu e Sherlock). Objetivo: detectar alucinações, verificar citações e alertar quando o modelo está desatualizado.

### 4.2 Arquitetura de Duas Trilhas Paralelas

#### Trilha A — Verificação de Citações

1. GPT-4o-mini extrai todas as referências mencionadas na resposta (guidelines + artigos seminais com autores)
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

## 5. Cache Semântico ✅ Implementado

### 5.1 Definição

Camada de otimização que intercepta consultas antes de enviá-las aos modelos de IA. Se uma pergunta semanticamente equivalente já foi respondida recentemente, o sistema retorna a resposta cacheada sem consumir novos tokens.

### 5.2 Arquitetura Técnica

**Storage:** PostgreSQL + extensão pgvector (não Redis — decisão de arquitetura para manter consistência transacional e evitar dependência de serviço adicional).

**Pipeline por query:**

```
Prompt recebido
      │
      ▼
Guardrail + Normalização (GPT-4o-mini)
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
  ├── sim ≥ 0.92 → HIT: retorna resposta cacheada (cache_hit: true)
  └── sim < 0.92 → MISS: chama agente, armazena ao final
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
| Threshold de similaridade | 0.92 | Calibrado empiricamente — abaixo disso há divergência clínica |
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
| GPT-4o-mini (Triagem) | Classificar como QUICK_SEARCH | 3s | Log de erro |
| Perplexity Sonar Pro (Bizu) | Gemini 2.5 Flash | 10s | Log de erro |
| Claude Sonnet 4 (Sherlock) | GPT-4o → Gemini 2.5 Flash | 30s | Log de erro |
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

### Backend

| Módulo | Status | Observações |
|--------|--------|-------------|
| Orquestrador pipeline completo | ✅ Produção | 12 etapas implementadas |
| Triagem inteligente | ✅ Produção | GPT-4o-mini, confiança, fallback |
| Modo Bizu (QUICK_SEARCH) | ✅ Produção | Perplexity + fallback Gemini |
| Modo Sherlock (CLINICAL_REASONING) | ✅ Produção | Claude Sonnet 4, temperature=0 |
| Modo Farmácia (PHARMA_CHECK) | ✅ Produção | PharmaDB local com semáforo |
| Modo Produtividade | ✅ Produção | GPT nano |
| Validação PubMed (duas trilhas) | ✅ Produção | Trilha A + B paralelas |
| Confidence score PubMed | ✅ Produção | Fórmula baseada em verificações |
| Cache semântico (pgvector) | ✅ Produção | Normalização + embedding + lookup |
| DLP Middleware | ✅ Produção | Sanitização PII |
| Audit Log completo | ✅ Produção | Todos os campos RN-AUD-001 |
| Extração de medicamentos | ✅ Produção | GPT-4o-mini |
| Detecção de especialidade | ✅ Produção | GPT-4o-mini |
| Cálculo de custo por tokens | ✅ Produção | Via tabela model_pricing |
| Agregador multi-modelo | ✅ Produção | Chamadas paralelas, comparação |
| Streaming (SSE) no orquestrador | ⏳ Próximo sprint | Providers implementados |
| Histórico pesquisável pelo médico | ⏳ Backlog | Dados persistidos, endpoint pendente |
| Exportação PDF/CSV | ⏳ Backlog | — |
| Áudio / Whisper | ⏳ Backlog | — |
| Métricas de cache hit rate | ⏳ Backlog | — |
| Aceite de termos registrado (LGPD art. 8) | ✅ Implementado | `consent_logs` com IP, user-agent e versão do documento |
| Consent específico de monetização (art. 11) | 🚫 Bloqueia RN-DATA-001 | Infra pronta; falta tela e decisão de produto |

### Frontend

| Módulo | Status |
|--------|--------|
| Interface web | ⏳ Não iniciado |
| App mobile nativo | ⏳ Fase futura |

---

## 11. Glossário

| Termo | Definição |
|-------|-----------|
| Agregador | Interface unificada para consulta simultânea a múltiplos modelos de IA |
| Orquestrador | Pipeline inteligente (The Gatekeeper) que classifica e roteia para agentes especializados |
| Cache Semântico | Camada pgvector que retorna respostas cacheadas para perguntas com similaridade cosine ≥ 0.92 |
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

## 12. Controle de Versão

| Versão | Data | Alterações |
|--------|------|-----------|
| 1.0 | 04/05/2026 | Criação inicial |
| 2.0 | 04/05/2026 | + Cache Semântico, Data Monetization, DLP Middleware, modo Produtividade |
| 2.1 | 04/05/2026 | + Seção 8: UX Mobile First |
| 2.2 | 19/05/2026 | Atualização completa para refletir estado de produção. Implementação de validação PubMed de duas trilhas (Trilha A: verificação de citações + Trilha B: detecção de diretrizes recentes). Confidence score reformulado (recompensa verificações, não penaliza ausências). Cache semântico implementado em pgvector com normalização de siglas antes do embedding, guardrail para CLINICAL_REASONING e threshold 0.92. Temperature=0 definido como padrão para modos clínicos. System prompts de Sherlock atualizados com regras invioláveis (sem percentagens, respeito ao sexo do paciente). Status de implementação adicionado por módulo. |
