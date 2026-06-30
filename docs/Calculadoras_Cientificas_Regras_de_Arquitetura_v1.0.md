# Calculadoras Científicas — Regras de Arquitetura v1.0

**Status:** Rascunho para discussão
**Escopo:** Novo módulo, schema isolado, mesmo banco do Médico 360
**Relacionado a:** Regras de Negócio Médico 360 v2.2

---

## 1. Visão Geral

O módulo de Calculadoras Científicas adiciona ao Médico 360 um conjunto extensível de calculadoras clínicas organizadas por especialidade (cardiologia, nefrologia, infectologia etc.). Na primeira fase, todas as calculadoras são **determinísticas** (fórmulas fixas, sem chamada a modelos de IA). A arquitetura deve, no entanto, deixar um gancho explícito para que calculadoras futuras possam ser executadas via Orquestrador (IA), sem exigir refatoração estrutural.

### 1.1 Premissas

- O módulo convive no **mesmo banco de dados** do Médico 360, em **schema isolado** (`calculators`), não em `public`.
- Reaproveita entidades já existentes em `public` (`users`, `company`, `audit_logs`) via foreign keys cross-schema — não duplica usuário, empresa ou auditoria.
- "Multi-tenant" aqui não se refere a isolamento por organização (`company_id` já cobre isso) — refere-se a suportar **múltiplas calculadoras, agrupadas por especialidade**, de forma escalável.
- A maioria das calculadoras é modelada como **dados configuráveis**, não como código/tabela dedicada por calculadora.

---

## 2. Regras de Modelagem de Dados (Schema)

### RN-CALC-SCHEMA-001: Isolamento de Schema

- Todas as tabelas do módulo residem no schema `calculators`, nunca em `public`.
- Referências a `users`, `company` e `audit_logs` são feitas via FK cross-schema (`public.users.id`, `public.company.id`).
- Migrations do módulo são versionadas separadamente das migrations de `public`.

### RN-CALC-SCHEMA-002: Modelagem Orientada a Dados

- Calculadoras NÃO geram uma tabela física nova por calculadora (ex.: proibido criar `child_pugh`, `cha2ds2vasc` como tabelas).
- Toda calculadora é uma linha em `calculator_definitions`; seus campos de entrada são linhas em `calculator_fields`.
- Justificativa: adicionar uma calculadora deve ser uma operação de **dados** (insert/seed), não de **schema** (migration), sempre que a fórmula for puramente determinística.

### RN-CALC-SCHEMA-003: Entidades Principais

| Tabela | Propósito |
|---|---|
| `calculators.specialties` | Agrupamento de calculadoras por especialidade médica |
| `calculators.calculator_definitions` | Metadados de cada calculadora (nome, slug, especialidade, status, `engine_type`) |
| `calculators.calculator_fields` | Inputs de cada calculadora (tipo, unidade, obrigatoriedade, faixa válida) |
| `calculators.calculator_versions` | Versionamento de fórmula/critério clínico ao longo do tempo |
| `calculators.calculator_executions` | Registro de cada execução (inputs, resultado, interpretação, auditoria) |

### RN-CALC-SCHEMA-004: Campo `engine_type`

- `calculator_definitions.engine_type` aceita os valores `formula` (padrão, determinístico) e `orchestrator` (futuro, via IA).
- Esse campo é o único ponto de decisão sobre como uma calculadora é executada — não deve haver lógica de tipo de calculadora espalhada em outras tabelas.

### RN-CALC-SCHEMA-005: Versionamento de Fórmula

- Mudança em critério clínico (ex.: atualização de guideline) DEVE gerar uma nova linha em `calculator_versions`, nunca sobrescrever a versão anterior.
- `calculator_executions` DEVE referenciar a `version_id` usada no momento do cálculo, garantindo rastreabilidade/auditoria clínica retroativa.

### RN-CALC-SCHEMA-006: Gancho para Orquestrador (Futuro)

- `calculator_executions` possui campo nullable `interaction_id` (FK para `public.interactions`).
- Esse campo é preenchido **somente** quando a execução específica envolveu uma chamada ao Orquestrador.
- Calculadoras `formula` nunca preenchem esse campo.
- Nenhuma tabela ou lógica de IA (triagem, cache semântico, validação PubMed) é replicada dentro do schema `calculators` — se uma calculadora futura precisar disso, ela reutiliza o pipeline já existente em `public`/Orquestrador via esse gancho.

### RN-CALC-SCHEMA-007: Auditoria

- Toda execução de calculadora DEVE gerar registro em `public.audit_logs`, seguindo o mesmo padrão já estabelecido no Médico 360 (Seção 6 das Regras de Negócio v2.2), e não um log de auditoria paralelo dentro do schema `calculators`.

---

## 3. Regras de Arquitetura de Backend

### RN-CALC-BACK-001: Motor Genérico (Engine + Registry)

- Não é permitido criar um service/router dedicado por calculadora.
- Toda calculadora `formula` é executada por um **engine genérico** (`calculator_engine.py`) que:
  1. Recebe `slug` da calculadora + inputs do usuário.
  2. Busca a definição ativa (`calculator_definitions` + `calculator_fields` + `calculator_versions` vigente).
  3. Valida os inputs contra os campos definidos (tipo, obrigatoriedade, faixa).
  4. Executa a função de fórmula correspondente, buscada em um **registry**.
  5. Persiste a execução em `calculator_executions`.
  6. Retorna resultado + interpretação ao cliente.

### RN-CALC-BACK-002: Organização por Especialidade na Camada de Fórmulas

- A organização por especialidade (cardiologia, nefrologia etc.) ocorre **apenas na camada de fórmulas**, não na camada de rotas/controllers.
- Stack: **Python / FastAPI**, consistente com o backend já existente do Médico 360 (Agregador de IA).
- Estrutura de pastas sugerida:

```
/calculators
  /engine
    calculator_engine.py     # orquestra validação + execução + persistência
    validation.py            # validação de inputs contra calculator_fields
  /registry
    __init__.py              # mapeia slug -> função de fórmula
  /formulas
    /cardiologia
      cha2ds2vasc.py
      has_bled.py
    /nefrologia
      cockcroft_gault.py
      ckd_epi.py
    /infectologia
      ...
  /schemas
    calculator_schemas.py    # modelos Pydantic (request/response)
  /routers
    calculators_router.py    # APIRouter com os endpoints do módulo
  /services
    calculators_service.py   # regras de negócio, chama engine + persistência
  /repositories
    calculators_repository.py # acesso a dados (schema `calculators`)
```

- Cada função de fórmula é **pura** (sem side effects, sem acesso a banco/sessão), recebendo inputs já validados (via Pydantic) e retornando resultado + interpretação. Isso garante testabilidade isolada por especialidade, com testes unitários simples por função.
- Validação de input usa modelos Pydantic dinâmicos ou validação programática a partir de `calculator_fields` — não há um `schema.py` por calculadora; o mesmo modelo genérico de request é reaproveitado, validado contra a definição vinda do banco.

### RN-CALC-BACK-003: Rotas Genéricas (Router Único)

- As rotas do módulo NÃO crescem por calculadora. O conjunto fixo de endpoints, expostos via um único `APIRouter` (`calculators_router.py`), é:
  - `GET /calculators?specialty=` — lista calculadoras (com filtro opcional por especialidade)
  - `GET /calculators/{slug}` — retorna definição e campos de input
  - `POST /calculators/{slug}/execute` — executa o cálculo e retorna resultado
  - `GET /calculators/{slug}/history` — histórico de execuções do usuário (futuro, alinhado ao padrão de histórico já existente no Médico 360)
- Adicionar uma nova calculadora determinística NÃO deve exigir criação de rota nova.

### RN-CALC-BACK-004: Gancho de Execução via Orquestrador (Futuro)

- Quando `engine_type = orchestrator`, o `calculator_engine.py` delega a execução ao pipeline do Orquestrador já existente (Seção 3 das Regras de Negócio v2.2), em vez de buscar uma fórmula no registry.
- Essa ramificação deve ser isolada em uma única camada de decisão dentro do engine (ex.: `if engine_type == "orchestrator": delegate_to_orchestrator(...)`), evitando espalhar condicionais de tipo de engine pelo restante do código.
- Esta capacidade não será implementada na primeira fase, mas a interface do engine deve prevê-la desde o início.

### RN-CALC-BACK-005: Multi-tenant (Empresa)

- Toda execução é vinculada a `user_id` e `company_id`, seguindo o mesmo modelo de isolamento por organização já usado em `public.interactions`.
- O módulo não introduz um novo conceito de tenant — reutiliza `company_id` existente.

---

## 4. Fora de Escopo (Fase 1)

Para deixar explícito o que NÃO está sendo construído agora:

- Execução de calculadoras via IA/Orquestrador (apenas o gancho de dados/arquitetura é preparado).
- Cache semântico para resultados de calculadoras.
- Exportação de histórico de execuções (PDF/CSV).
- Versionamento automático de guideline (a criação de nova `calculator_version` é manual/curada).

---

## 5. Controle de Versão

| Versão | Data | Alterações |
|---|---|---|
| 1.0 | 30/06/2026 | Criação inicial — schema isolado, engine genérico, gancho para Orquestrador |
| 1.1 | 30/06/2026 | Estrutura de backend corrigida de Node/TS para Python/FastAPI, alinhada ao stack real do Médico 360 |
