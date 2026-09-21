# Plano de correções — análise externa de 2026-09-11

> Origem: revisão externa de 12 itens, verificada linha a linha contra o código em
> 2026-09-15. Este documento é o plano de execução, não a análise original.
>
> **Status:** EM PARTE IMPLEMENTADO — este cabeçalho dizia "nada implementado ainda" enquanto `debitos.md` já registrava itens daqui como feitos. O estado de cada item está no próprio item e em `debitos.md`; o que ainda depende de alguém está em `docs/pendencias.md`. Não arquivar: dois testes leem este arquivo pelo caminho.

## Como ler este documento

Cada tarefa traz: o que está errado, o que fazer, **como verificar**, e o que
NÃO fazer. As armadilhas registradas aqui foram encontradas na verificação e
não estão na análise original — várias delas transformariam a correção em
regressão.

A ordem das fases importa. Dentro de uma fase, as tarefas são independentes.

---

## Resumo da triagem

Dos 12 itens da análise, todos procedem em substância. Quatro tiveram a
justificativa corrigida na verificação:

| Item | Veredito | Correção da justificativa |
|---|---|---|
| 1 Sentry | procede | A premissa está invertida: `include_local_variables=False` **não** está no código hoje, e a blocklist por nome foi decisão deliberada e documentada. O furo real é outro (ver T1). |
| 4 `waid_uuid` | procede | O precedente citado (`is_(None)` em `auth_service.py:99-103` / `:218-225`) **não existe** — zero ocorrências no arquivo. |
| 6 re-sanitização | **retirado** | Os "~11ms por mensagem" são o custo do NER isolado num comentário (`dlp.py:70`), não medição do laço. E a otimização abriria um vazamento (ver "Item retirado"). |
| 7 CSRF | procede | São **6** rotas sem body param, não 2. A análise não varreu `app/dea` nem `app/calculators`. |

Três defeitos da mesma classe foram encontrados na verificação e **não estão na
análise**:

- `news_writer_service.py` roda `claude-sonnet-5` sem pricing cadastrado e sem
  `record_cost` — mesma classe do item 3, rota diferente, impacto maior.
- O cache semântico grava a resposta **crua** num payload global por modo,
  servido a outros médicos (`orquestrador_stream_service.py:504`).
- O ID do Haiku está duplicado em dois arquivos; divergir um deles faz
  `calculate_cost` devolver `Decimal("0")` em silêncio (`pricing.py:55-56`).

---

## Fase 1 — vazamento e contabilidade

Nada aqui depende de nada. Todas as tarefas são localizadas e verificáveis.

### T1 — Fechar o vazamento de dado clínico para o Sentry

**Itens:** 1
**Arquivos:** `app/core/error_tracking.py`, `app/middleware/dlp.py`,
`tests/test_error_tracking.py`, `scripts/verificar_sentry.py`

**O problema.** O Sentry captura as variáveis locais de cada frame do stack
trace. O filtro do projeto (`scrub_event`) mascara por nome de campo, e a lista
está correta — `"text"` e `"response_text"` já estão lá, e a comparação é por
substring. O furo é que `_limpa` (`error_tracking.py:65-78`) só recursa em
`dict` e `list|tuple`: ao encontrar qualquer outro objeto, devolve-o **intacto**
na linha 78. Um `SanitizationResult` — dataclass cujo primeiro campo é o texto
clínico **bruto, pré-DLP** — cai exatamente aí. Basta uma exceção depois do DLP
(queda no `db.flush()`, erro de provider) para o evento sair com o prompt
identificado.

Fechado hoje só porque `SENTRY_DSN` está vazio (`config.py:157`).

**Decisão tomada:** manter `include_local_variables` ligado. Desligá-lo fecharia
a classe inteira, mas cegaria o Sentry justamente no que o torna útil — e a
blocklist por nome foi escolha deliberada, documentada em
`error_tracking.py:4-12`. A correção ataca a causa, não o sintoma.

**Fazer:**

1. **Apagar o campo `original_text`** de `SanitizationResult`
   (`dlp.py:28`, escrito em `:105`). Verificado exaustivamente: escrito uma vez,
   **lido zero vezes** em todo o repositório. É lixo esquecido que carrega
   prontuário. Apagar remove a causa; o resto é rede de segurança.
2. **Ensinar `_limpa` a abrir objetos** — dataclass, `BaseModel`, instância
   comum — percorrendo `__dict__` / `dataclasses.fields`, aplicando a mesma
   regra de nome já existente. Respeitar `_MAX_PROFUNDIDADE`. Não é preciso
   acrescentar nome nenhum a `CAMPOS_BLOQUEADOS`.

**Como verificar.** O teste `test_excecao_real_nao_leva_o_prompt`
(`test_error_tracking.py:235`) já faz a coisa certa — liga
`include_local_variables=True` de propósito e assere que o alerta **continua
útil** (`"provider timeout"` e o nome da função sobrevivem). Falta só o caso que
expõe o furo:

- Acrescentar um caso que ponha um **`SanitizationResult` de verdade** no frame,
  não `str` e `list[dict]`. Esse é o ponto cego: os testes atuais só usam tipos
  que `_limpa` já sabe percorrer.
- Mesma correção em `scripts/verificar_sentry.py:56` — a lista `NAO_PODE_VAZAR`
  (`:34`) já tem os fragmentos certos.
- Rodar `python -m scripts.verificar_sentry` continua sendo o procedimento
  manual; ele passa a cobrir o caso real.

**Não fazer.** Não desligar `include_local_variables`. Não remover
`before_send_transaction` — ele passa pelo mesmo filtro e é o que permite
separar o 401 normal do embed do 401 de rota quebrada
(`error_tracking.py:160-168`).

---

### T2 — Sanitizar texto clínico na escrita, onde é coerente

**Itens:** 2, e a parte segura do que a verificação encontrou
**Arquivos:** `app/api/v1/endpoints/uploads.py`,
`app/services/orquestrador_service.py`, `app/services/agregador_service.py`,
`app/services/orquestrador_stream_service.py` (só o `done_payload`)

**O problema.** Três coisas distintas, mesma raiz:

1. **Anexos.** `uploads.py:147-157` grava `extracted_text` e `file_name` crus,
   direto do parser. Um laudo traz nome, CPF e data de nascimento no cabeçalho,
   e o nome do arquivo costuma trazer o nome do paciente. Fica 180 dias
   (`data_subject_service.py:37`). É a única porta por onde dado de paciente
   entra sem DLP. `docs/runbook.md:375` afirma o contrário — a doc está errada.
2. **Cache semântico com resposta crua.** `orquestrador_stream_service.py:504`
   grava `full_text` **cru** no `done_payload`. Esse payload é **global por modo**
   e servido a **outros médicos**. É vazamento entre titulares, e é o achado mais
   grave que a análise não viu.
3. **Resposta do modelo no `/query` e no agregador.** Gravada crua.

**Armadilha — leia antes de mexer.** O texto devolvido ao usuário e o texto
gravado saem de **duas leituras separadas** da mesma origem:

- `/query`: `orquestrador_service.py:265` (grava) e `:351` (retorna), ambas
  `agent_response.get("text", "")`.
- agregador: `agregador_service.py:126` (grava) e `:141` (retorna), ambas
  `result.text`.

Sanitizar só no ponto de gravação faz o médico ver um texto e o banco guardar
outro — e ao reabrir a conversa (`conversations.py:135`) **o texto muda diante
dele**. Sanitizar **na origem, uma vez**, antes do primeiro uso, mantém os dois
coerentes.

**Fazer:**

1. `extracted_text` e `file_name` por `sanitize_prompt_async` antes do `db.add`
   (`uploads.py:155`).
2. `agent_response["text"]` sanitizado **antes da linha 262** do
   `orquestrador_service.py` — um ponto só, os dois usos leem o valor limpo.
3. `result.text` sanitizado **antes da linha 123** do `agregador_service.py`.
4. `full_text` sanitizado **antes de montar o `done_payload`**
   (`orquestrador_stream_service.py:504`).
5. `full_text` sanitizado antes da gravação do `InteractionResponse`
   (`orquestrador_stream_service.py:388`). **Decisão de D1:** o médico vê o texto
   original token a token por SSE e encontra a versão mascarada ao reabrir. Isso
   é aceito — o requisito é que o registro seja consistente, não idêntico ao que
   passou na tela. Não sanitizar por token: a PII atravessa a fronteira entre dois
   deltas e o custo cairia dentro do laço.

**Usar `use_ner=False` em toda sanitização de resposta do modelo.** Decisão de
D1. Três razões:

1. `extract_from_interaction` extrai nomes de fármacos da resposta; nome
   comercial de medicamento é nome próprio e o NER o mascararia como `[NOME]`,
   degradando a extração sem ganho de privacidade. O mesmo vale para
   `extra_metadata`, que carrega títulos e abstracts do PubMed (nomes de autores).
2. **Retomada clínica.** O histórico mascarado realimenta o modelo nos turnos
   seguintes (`conversation_history.py:85`). Um NER agressivo comendo nome de
   fármaco, de escore ou epônimo de patologia quebra a continuidade da conversa —
   é a mesma razão pela qual os filtros anti-epônimo existem no DLP, por medição.
3. O ganho do NER na saída do modelo é baixo: a PII só chega ali se o modelo
   inventar ou se vier de fonte externa (busca, PubMed, bula). O regex — CPF,
   telefone, e-mail, data — cobre o caso real e é seguro.

**Como verificar.**

- Teste novo: PDF com nome, CPF e data de nascimento no cabeçalho → o
  `FileExtraction` gravado não contém nenhum dos três.
- Teste novo: resposta de modelo com PII → o `InteractionResponse` gravado e o
  payload retornado ao cliente contêm **o mesmo texto**, mascarado. Hoje não
  existe nenhum teste que cubra a direção saída-do-modelo → banco.
- Teste novo: `done_payload` do cache não contém PII.
- **Teste de retomada clínica** (critério de aceitação de D1): conversa de N
  turnos em que um turno tardio depende de dado clínico do turno 1 — idade,
  medicação, valor de exame. O dado tem de sobreviver ao mascaramento. É o teste
  que pega um NER agressivo comendo nome de fármaco ou epônimo.
- Corrigir `docs/runbook.md:375`, que hoje afirma que o texto extraído já é
  sanitizado.

**Não fazer.** Não sanitizar `extra_metadata` com NER (ver acima). Não mexer em
`error_message` trocando `None` por string — ele é usado como flag de controle
em cinco lugares (`conversation_history.py:83` entre outros), e um valor onde
havia `None` transformaria resposta boa em registro de falha, sumindo-a do
histórico.

**Fora de escopo — ver T11 (decisão pendente):** o `/stream` e os embeddings.

---

### T3 — Limite e contabilidade em toda chamada LLM fora do `ai_providers`

**Itens:** 3, ampliado pela verificação
**Arquivos:** `app/calculators/routers/calculators_router.py`,
`app/services/news_writer_service.py`, `app/services/integracoes/pharmadb_service.py`

**O problema.** Três caminhos chamam a API de LLM por httpx direto, fora do
`ai_providers`, e escapam do medidor:

1. `POST /calculators/{slug}/extract` — chama `gpt-5.4-mini`
   (`extraction_service.py:123`) **sem `check_limit` e sem `record_cost`**. Um
   `beta_user` que estourou o teto de US$ 5 semanais continua gastando aqui. O
   DLP, esse, está correto (`extraction_service.py:111`).
2. `news_writer_service.py:137` — roda **`claude-sonnet-5`, que não tem linha em
   `model_pricing`**, sem `calculate_cost` nem `record_cost`. Pior que o item 1
   da análise: modelo sem preço cadastrado e custo invisível.
3. `pharmadb_service.py:62` — mesmo padrão, conferir.

Nenhum dos três cria `Interaction`, então o gasto é invisível também para
`vigilancia_service.medir_custo` (`vigilancia_service.py:149-177`), que soma
`Interaction.token_cost_usd`. O alarme de custo tem ponto cego.

**Por que o teste-guarda atual não pega.** `test_todo_produtor_de_custo_registra`
(`test_orquestrador_paridade.py:377`) é grep por `"await calculate_cost("` sem
`record_cost`. Um arquivo que nunca chama `calculate_cost` — exatamente o
`news_writer_service.py` — passa sem ser notado. Ver T5.

**Fazer:** `check_limit` antes e `record_cost` depois nos três caminhos, no
padrão de `uploads.py:67` e `:116-119`. Cadastrar a linha de
`claude-sonnet-5` em `model_pricing` (é tabela de banco, sem seed versionado —
segue o padrão dos scripts `scripts/add_*.py`).

**Como verificar.** Teste por rota, não por grep — ver T5, que fecha a classe.

---

### T4 — Guarda `IS NULL` no backfill de `waid_uuid`

**Itens:** 4
**Arquivo:** `app/services/auth_service.py:179-184`

**O problema.** O docstring (`:166-167`), o log (`:183`) e a migration
`008_waid_uuid` afirmam que o vínculo é preenchido no **primeiro login**. Não há
guarda: toda vez que a busca por uuid falha e a por e-mail acerta, a vinculação
é **sobrescrita em silêncio** enquanto o log afirma ser o primeiro login. Se o
LMS re-provisiona a conta com uuid novo para o mesmo e-mail, o vínculo alterna a
cada login.

O mesmo arquivo tem a guarda análoga para o caso espelhado em
`sincronizar_email_da_waid` (`:218-225`), o que confirma a assimetria.

**Fazer:** condicionar a atribuição a `user.waid_uuid is None`.

> Nota: a análise afirma que o arquivo "já usa a primitiva `is_(None)` em
> `:99-103` e `:218-225`". Isso **não procede** — zero ocorrências de `is_(None)`
> no arquivo. Aqueles trechos usam comparação Python (`if user is not None`),
> que é o que esta correção também precisa. O achado procede; o precedente
> citado, não.

**Como verificar.** Teste novo: conta que **já possui** `waid_uuid` divergente
não é sobrescrita. O teste atual (`test_waid_identity.py:158-168`) assere
`waid_uuid is None` **antes** de chamar — só cobre o caso feliz, onde a guarda
ausente não faz diferença.

---

### T5 — Atualizar IDs de modelo e versão do web search

**Itens:** 12
**Arquivos:** `app/services/file_extractor_service.py:323`,
`app/api/v1/endpoints/uploads.py:117`, `app/services/integracoes/ai_providers.py:104`

**Fazer:**

1. `claude-haiku-4-5-20251001` → `claude-haiku-4-5`. **O ID está duplicado em
   dois arquivos** (`file_extractor_service.py:323` e `uploads.py:117`, que o
   repete em `calculate_cost`). Mudar um sem o outro faz `calculate_cost`
   devolver `Decimal("0")` **em silêncio** (`pricing.py:55-56`). Mudar os dois na
   mesma edição, e considerar extrair para constante única. Confirmar a linha
   correspondente em `model_pricing`.
2. `web_search_20250305` → `web_search_20260209` (`ai_providers.py:104`).
   Suportado pelo Sonnet 4.6, traz filtragem dinâmica. Revisar também o header
   `anthropic-beta: web-search-2025-03-05` (`:139`, `:192`).

**Armadilha.** A filtragem dinâmica do `web_search_20260209` roda code execution
por baixo. **Não** declarar `code_execution` separadamente em `tools` — dois
ambientes de execução confundem o modelo. Conferir que nada mais foi adicionado
a `_web_search_tool()`.

**Como verificar.** `tests/test_data_ocean.py` já cobre contagem de
`web_search_calls`. Confirmar que o parsing de `web_search_result`
(`ai_providers.py:158`, `:221`) segue válido na versão nova, e que erro de web
search continua tratado — erro volta **200 com bloco de erro**, não exceção, e
em sucesso `content` é lista, em erro é objeto.

---

## Fase 2 — travar as classes por teste — **FEITA em 2026-09-15**

Depende da Fase 1 estar em pé (para os testes nascerem verdes).

> **Estado:** T6 e T7 implementados. `exigir_origem_confiavel` é dependency do
> `api_v1_router` inteiro e filtra por método; os dois testes declarativos vivem
> em `tests/test_politica_de_custo_llm.py` (64 rotas) e
> `tests/test_politica_de_dlp_na_escrita.py` (36 campos). Suíte em 1145 testes.
>
> Correções de rumo durante a execução, registradas porque contrariam o que este
> plano dizia antes:
> - O teste de custo precisa inspecionar o par **endpoint + service**:
>   `check_limit` vive no endpoint (é gate de entrada) e `record_cost` no service
>   (é consequência). Olhar só o service acusa falsamente as quatro rotas do
>   orquestrador e do agregador.
> - A política de DLP é declarada por **campo**, não por site de `db.add`: os
>   mesmos modelos são instanciados em ~26 lugares e mover um `db.add` é
>   refatoração rotineira, mas o campo permanece.
> - A detecção usa **AST, não grep**. Um grep textual conta comentário como
>   chamada — inclusive os comentários escritos na Fase 1 explicando por que
>   `record_cost` NÃO existe ali.

### T6 — Origem confiável em todos os métodos não-idempotentes

**Itens:** 7
**Arquivos:** `app/api/deps.py`, routers, `tests/test_csrf_upload.py`

**O problema.** O cookie `medico360_session` é `SameSite=None; Secure` em
produção (`auth.py:43-65`, por causa do iframe da Waid). A premissa anti-CSRF
documentada em `deps.py:92-95` — "toda rota exige `application/json`, logo há
preflight" — **falha para handler sem parâmetro de corpo**: sem body param o
FastAPI não impõe content-type, e um `<form>` cross-site chega sem preflight com
o cookie anexado.

**São 6 rotas sem body param, não 2** (a análise não varreu `app/dea` nem
`app/calculators`):

| Método | Rota | Emissível por `<form>`? |
|---|---|---|
| POST | `auth.py:564` `revogar_consentimento` | **sim — risco real** |
| POST | `news.py:419` `rodar_pipeline` | **sim** (mas exige `role == admin`) |
| DELETE | `folders.py:158` `delete_folder` | não |
| DELETE | `news.py:401` `remover_palavra` | não |
| PUT | `calculators_router.py:88` `favorite_calculator` | não |
| DELETE | `calculators_router.py:99` `unfavorite_calculator` | não |

`<form>` HTML só emite GET e POST, então DELETE e PUT só são alcançáveis por
`fetch`/XHR, que dispara preflight. O risco real são os **dois POST** — e o da
revogação de consentimento grava manifestação de vontade negativa, permanente e
falsamente atribuída, no registro que o próprio docstring chama de prova
(LGPD Art. 8º §5º).

**Fazer:** aplicar `exigir_origem_confiavel` (já existe, `deps.py:83`, hoje usado
em **uma** rota só — `uploads.py:45-53`) como dependency **de router** para todos
os métodos não-idempotentes. Corrigir por classe, não por rota: um handler futuro
sem corpo reabriria isso em silêncio.

**Fazer também:** corrigir a premissa hoje falsa em `deps.py:92-95` e em
`tests/test_csrf_upload.py:9-13`, que afirmam que o content-type protege todo o
resto.

**Como verificar.** Teste de regressão cobrindo **as 6 rotas**: POST/PUT/DELETE
sem corpo com `Origin: https://evil.com` devolve 403. Atenção ao fail-open
deliberado de `exigir_origem_confiavel` (`deps.py:119-126`): ausência de `Origin`
é permitida — `test_requisicao_sem_origin_e_permitida` (`test_csrf_upload.py:69`)
trava isso e deve continuar verde.

---

### T7 — Testes de política para custo de LLM e DLP na escrita

**Itens:** 11
**Arquivo:** novo, no padrão de `tests/test_authorization.py`

**Por que.** Metade da lista tem a mesma origem: uma invariante respeitada no
caminho principal que um módulo mais novo não herdou. O projeto já tem o
mecanismo certo — `test_authorization.py` enumera rotas via `app.openapi()`,
declara a política de cada uma num dict, e tem **duas travas bidirecionais**:
rota sem política falha, e política apontando para rota inexistente também falha
(`:180-197`).

**Ancorar por rota, não por registry nem por grep.** Os dois análogos que
existem hoje não alcançam os casos reais:

- `test_dlp_enforcement.py:45-54` varre o **registry de providers**. As três
  chamadas httpx diretas (`news_writer`, `file_extractor`, `pharmadb`) escapam
  por construção.
- `test_orquestrador_paridade.py:377` é **grep de fonte** por `calculate_cost`.
  Um arquivo que nunca chama `calculate_cost` passa — que é exatamente o
  `news_writer_service.py`.

**Fazer:** dois testes declarativos ancorados na enumeração de rotas:

1. "toda rota que gasta LLM chama `check_limit` e `record_cost`" — **7 rotas**
   hoje: `/orquestrador/query`, `/orquestrador/stream`, `/agregador/query`,
   `/agregador/stream`, `/uploads/extract`, `/calculators/{slug}/extract`,
   `/news/admin/pipeline`.
2. "todo texto clínico passa por DLP antes do `db.add`" — **~18 sites** em 7
   arquivos.

Rodar **depois** de T2 e T3, para nascerem verdes.

**Nota de escopo.** Estes dois testes fecham T2 e T3, mas **não** T4 — a guarda
do `waid_uuid` é invariante de identidade, não de custo nem de DLP. A existência
do T7 não protege o T4 contra regressão; ele precisa do próprio teste.

---

## Fase 3 — latência e cache — **FEITA em 2026-09-15**

> **Estado:** T8 e T9 implementados.
>
> Correções de rumo durante a execução, registradas porque contrariam o que este
> plano dizia antes:
>
> - **T8 mexe no contrato da API, não só na latência.** O `return_dict` do
>   `/query` devolve sete campos apurados pelo pós-processamento
>   (`specialty_detected`, `topic_detected`, `confidence_score`,
>   `low_evidence_alert`, `outdated_alert`, `cited_guidelines_verified`,
>   `newer_guidelines_found`). Eles passam a sair vazios. Mantidos no contrato
>   de propósito: o front (`queryOrquestrador`) lê apenas `response_text`,
>   `mode` e `conversation_id`, e removê-los seria quebra explícita.
> - **A gravação no cache foi junto para o background.** O mesmo `return_dict`
>   alimenta `store_response`; cachear antes do pós-processamento serviria a
>   outro médico uma resposta sem validação PubMed — e é do cache que o
>   `cache_hit` do front tira o bloco de referências.
> - **Foi preciso um commit explícito antes de agendar a tarefa.** O commit do
>   `/query` só acontecia em `get_db`, depois do handler retornar; como
>   `create_task` agenda para o próximo ciclo do loop, a tarefa podia procurar
>   por id, em sessão própria, registros de uma transação não confirmada — não
>   encontraria nada e sairia em silêncio. O `/stream` já tinha esse commit,
>   pelo mesmo motivo.
> - **Testar background exige aguardar a tarefa.** Os testes que só conferem o
>   retorno da rota passam mesmo que a tarefa nunca rode. Ver
>   `tests/test_pos_processamento_background.py`, que aguarda `_pos_em_voo` e
>   monta a session factory sobre a conexão do teste — padrão que
>   `test_folder_context` e `test_orquestrador_stream` já usavam.

### T8 — Pós-processamento do `/query` em background

**Itens:** 5
**Arquivo:** `app/services/orquestrador_service.py:298-302`

**O problema.** `pos_processar_interacao` é aguardado antes do return: validação
PubMed, detecção de especialidade e extração de medicamentos entram no tempo que
o médico vê. O `/stream` emite `text_done` antes disso
(`orquestrador_stream_service.py:434-452`) e não paga esse preço. Como o `/query`
é o caminho de **todos os modos PharmaDB** (`orquestrador_stream_service.py:198-203`
recusa streaming para eles), é a divergência `/query`↔`/stream` de novo.

**Dimensão real do ganho.** As três chamadas **já são paralelas** dentro de um
`gather` (`orquestrador_shared.py:505-509`). O custo é o **máximo** das três, não
a soma; o PubMed tem timeout de 15s. O ganho é real, mas menor do que a análise
sugere.

**Fazer:** `create_task` com sessão de banco própria, no padrão de
`agendar_indexacao` (`folder_context_service.py:298-330`) — que é molde completo:
dict de referência forte contra coleta prematura, `async_session_factory()`
própria, e `done_callback` que drena a exceção para não virar "Task exception was
never retrieved".

**Como verificar.** Nada do que é gravado muda — validar por diff dos registros
antes/depois. `test_os_dois_caminhos_usam_o_pos_processamento_compartilhado`
(`test_orquestrador_paridade.py:404`) deve continuar verde.

---

### T9 — Gate do cache semântico por allowlist

**Itens:** 8
**Arquivos:** `app/services/orquestrador_shared.py:200`, `docs/debitos.md` §16,
`tests/test_cache_paridade.py:129`

**O problema.** `contexto_tem_dado_de_paciente` decide cacheabilidade testando se
alguma mensagem começa com `[` (`orquestrador_shared.py:200-203`). Isso detecta
os dois blocos sintéticos (evolução da pasta, similaridade entre conversas) e
**não detecta os turnos comuns do histórico**, que são texto sem prefixo e
rotineiramente carregam o quadro do paciente. Como a chave é `(modo, embedding do
prompt normalizado)` — **sem usuário, sem conversa** (`semantic_cache_service.py`,
`_lookup`) — um follow-up curto ("e qual a dose?") respondido a partir do caso do
Dr. A pode ser servido ao Dr. B.

**Dormente hoje:** `semantic_cache_enabled = False` (`config.py:86`), e a flag
**não aparece em `.env.example`, no Dockerfile nem no CI** — não há como religá-la
por ambiente sem editar código. Mas `docs/debitos.md` §16 instrui o próximo
engenheiro a religar sem mexer no gate ("Religar é mudar a flag — não mexer nas
outras duas"). **Fazer antes de religar.**

**Fazer:**

1. Em `pode_usar_cache`, cacheável apenas quando **não há contexto nenhum**
   montado (`not mensagens`).
2. Reescrever o parágrafo "Cuidado ao religar" de `docs/debitos.md` §16
   (linhas 375-377), que hoje atesta o gate como completo.
3. Corrigir `test_conversa_comum_continua_cacheavel`
   (`test_cache_paridade.py:129`), que trava o comportamento errado.

**Relação com T2.** T2 sanitiza o `done_payload` do cache, fechando o vazamento
pelo conteúdo. T9 fecha pelo gate. São complementares: T2 limita o dano, T9
impede a entrada.

---

## Fase 4 — medição (só com decisão explícita)

Esta fase custa mais que as três anteriores somadas e é a única com incerteza
real. Não começar sem decidir que vale.

### T10 — Construir o conjunto de avaliação clínica

**Pré-requisito de T11 e T12. Não existe hoje.**

Não há golden set, eval ou dataset de casos clínicos no repositório. Os "Golden
values" de `tests/calculators/` são fórmulas determinísticas conferidas contra
o paper — sem LLM. `test_e2e_pergunta_real.py` valida contabilização, não
qualidade.

Sem isso, T11 é troca no escuro. **Esta é a maior tarefa da lista**, e é de
produto tanto quanto de engenharia: exige médico definindo o que é resposta boa.

---

### T11 — Medir e avaliar migração para `claude-sonnet-5`

**Itens:** 10 · **Depende de:** T10

`claude-sonnet-4-6` custa 3,00/15,00 por MTok; `claude-sonnet-5` custa
2,00/10,00 — **um terço a menos nas duas pontas** (confirmado contra a tabela
oficial). Motivo extra: a troca de `claude-sonnet-4` para `4-6` **aumentou a
latência em 56%** (21s → 33s no p50, `ARQUITETURA_TECNICA.md:563`, n=35) e isso
nunca foi recuperado. É a única mudança da lista que pode melhorar custo e
latência ao mesmo tempo.

**Armadilha, maior do que a análise diz.** `MODE_TEMPERATURE_MAP` envia
`temperature: 0.0` nos modos clínicos (`orquestrador_modes.py:104-113`), e o
provider Anthropic manda `temperature` **incondicionalmente**
(`ai_providers.py:127`, `:180`) — diferente do provider OpenAI, que já é
condicional (`ai_providers.py:306`, helper em `:255`). No Sonnet 5 **`temperature`,
`top_p` e `top_k` foram removidos e retornam 400** (a análise menciona só
`temperature`). A troca não é só o `model_id`.

**Fazer:** tornar o envio de `temperature` condicional no provider Anthropic, no
padrão que o provider OpenAI já usa; cadastrar `claude-sonnet-5` em
`model_pricing`; medir latência p50 pós-troca; avaliar consistência das respostas
por outro caminho, já que `temperature: 0.0` deixa de existir.

---

### T12 — Prompt caching — **FEITO em 2026-09-15 (sem a reordenação)**

> **Decisão:** a reordenação do bloco da pasta **não** foi feita. O caching foi
> aplicado só onde não contraria decisão de qualidade já tomada.
>
> O plano previa mover o bloco da pasta para depois do histórico, porque ele é
> recuperado por similaridade contra a pergunta atual — muda a cada turno e, no
> começo do prefixo, invalida tudo depois dele. Mas o comentário em
> `orquestrador_shared.load_context_messages` registra a posição atual como
> escolha deliberada de qualidade ("é pano de fundo, não a última coisa dita"),
> e medir o efeito da troca exigiria o eval clínico do T10, que foi descartado.
>
> Trocar uma decisão de qualidade clínica por ganho de custo, sem conseguir
> medir o que se perde, não se justifica. O que foi feito:
>
> - Breakpoint explícito no **fim do histórico** (`AnthropicProvider.
>   _com_breakpoint_de_cache`), nos dois caminhos (`complete` e `stream`).
> - Fora de pasta: cache funciona pleno, e o prefixo cresce a cada turno.
> - Dentro de pasta: não cacheia, por construção. Ganho abre mão, qualidade
>   preservada.
>
> **Por que no fim do histórico, e não no system:** o system clínico tem ~460
> tokens e o mínimo cacheável no Sonnet é 1024. Breakpoint ali nunca criaria
> entrada — a API devolve `cache_creation_input_tokens: 0` sem erro.
>
> **Por que explícito, e não automático:** o automático se coloca no último
> bloco cacheável, que é a pergunta atual — pagaria prêmio de escrita em bytes
> que ninguém relê.
>
> **Escopo do cache:** o system carrega especialidade e status do médico
> (`_user_context_suffix`), então o prefixo é por-usuário. Serve o mesmo médico
> entre turnos, nunca entre médicos.
>
> **Falta medir:** `usage.cache_read_input_tokens` em produção. Zero em
> requisições consecutivas do mesmo médico na mesma conversa significa
> invalidador no prefixo. Travado por `tests/test_prompt_caching.py`.

### T12 (original) — Reordenar montagem de contexto e ativar prompt caching

**Itens:** 9 · **Fazer depois de T11**

Caches são **model-scoped**: medir o caching antes de decidir o modelo significa
medir duas vezes. Esta ordem não está na análise.

**Não existe `cache_control` em lugar nenhum do projeto** (verificado: zero
ocorrências). Mas acrescentar o marcador não é o primeiro passo. Caching é
prefix match, e a ordem atual é `[evolução] → [bloco da pasta] → [histórico] →
[pergunta atual]` (`orquestrador_shared.py:117-148`). O bloco da pasta é
recuperado **por similaridade contra a pergunta atual**
(`folder_context_service.py:536`) — muda a cada turno e está no começo do
prefixo. Em conversa dentro de pasta, o cache erraria em 100% das requisições.

**Dois números confirmados contra a documentação oficial:**

- **O system prompt sozinho não cacheia.** O mínimo cacheável é **1024 tokens**
  no Sonnet 4.6 **e no Sonnet 5** (mesmo valor — a conclusão sobrevive à
  migração). `SYSTEM_PROMPT_CLINICAL_REASONING` tem ~421 tokens (~460 com o
  sufixo do médico). O que cacheia é system + histórico.
- **TTL de 1 hora, não 5 minutos.** A janela conta do **início** de uma
  requisição à seguinte, e o tempo de geração conta contra ela. Com 33s de p50 e
  o médico lendo ~1350 tokens antes de responder, o intervalo passa dos 5
  minutos com frequência — a faixa (5-60 min) em que o write dobrado do TTL de 1h
  se paga. Write: 1,25× (5 min) vs 2× (1h); read ~0,1×.

**Fazer:** mover o bloco da pasta para depois do histórico; breakpoint
**explícito** no fim da porção estável — nunca o automático, porque o prompt
termina em conteúdo único por requisição e o automático pagaria prêmio de escrita
em bytes que ninguém relê; medir `usage.cache_read_input_tokens` (zero em
requisições consecutivas significa que ainda há invalidador no prefixo).

**Conflito a resolver.** O comentário do código justifica a posição atual do
bloco da pasta por **qualidade da resposta** ("é pano de fundo, não a última
coisa dita"). A razão é boa e a mudança a contraria. Decidir com T10 na mão —
é medível.

---

## Item retirado

### Item 6 — pular re-sanitização do histórico: **não fazer**

A proposta parte de que o histórico vem de `Interaction.prompt_text`, já
sanitizado na escrita. **Meia verdade.** `conversation_history.py:74-86` monta o
histórico com os dois papéis:

- turnos `user` ← `prompt_text` → **sanitizado na escrita** ✅
- turnos `assistant` ← `response_text` → **nunca passou por DLP** ❌

Para os turnos do assistente, a re-sanitização que a análise quer remover é hoje
a **única** passagem de DLP que esse texto recebe antes de voltar ao provider.
Aplicar como escrito abre um vazamento onde não existe.

Além disso, os "~11ms por mensagem" não são medição do laço: é o custo do passo
de NER isolado, num comentário em `dlp.py:70`. Não há benchmark. E o limite de
40 são **interações** (`conversation_history.py:30`), até ~80 turnos, cortados
depois por orçamento de tokens — o número que chega ao `_sanitize_history` é o
pós-orçamento.

**Reconsiderar apenas depois de T2**, que sanitiza parte das respostas na origem.
Mesmo então, o ganho é desconhecido e o risco é conhecido.

---

## Decisões

### D1 — O `/stream` entra no DLP de escrita? **SIM — decidido em 2026-09-15**

**Regra:** o histórico é registro e tem de ser gravado. Ao reabrir a conversa o
médico encontra a versão **mascarada, consistente** — não é exigido que seja
idêntica ao que passou na tela durante o streaming.

Consequências, já refletidas em T2:

- `/stream` entra (item 5 de T2). O médico lê o original token a token por SSE e
  encontra o mascarado ao reabrir. Aceito.
- `/query` e agregador entram, sanitizados **na origem**, de modo que resposta
  devolvida e resposta gravada sejam o mesmo valor.
- **`use_ner=False` em toda resposta de modelo**, para não quebrar a retomada
  clínica nem a extração de medicamentos. Travado pelo teste de retomada.
- **Embeddings continuam fora.** `MessageEmbedding.content`
  (`folder_context_service.py:252`) é gerado do mesmo texto que grava; sanitizar
  criaria **espaço vetorial misto** — registros antigos (cru) convivendo com
  novos (mascarado), degradando a similaridade até rotacionarem. Entra só com
  backfill, que é tarefa própria e não está neste plano.

### D2 — A imagem crua do exame

Fora de escopo na análise original, e concordo. `ai_providers.py:1028` repassa
`image_content` intacto por design — mascarar pixel exige OCR. No modo
`EXAM_REVIEW`, a foto com o nome impresso vai para fora do país. É decisão de
base legal, não de engenharia.

---

## Ordem de execução

```
Fase 1  T1  Sentry                          ── independentes entre si
        T2  DLP na escrita (onde é coerente)
        T3  check_limit/record_cost (3 caminhos)
        T4  waid_uuid IS NULL
        T5  IDs de modelo + web search

Fase 2  T6  CSRF por classe (6 rotas)       ── depende da Fase 1
        T7  Testes de política (nascem verdes depois de T2 e T3)

Fase 3  T8  /query em background            ── independentes
        T9  Gate do cache por allowlist

Fase 4  T10 Eval clínico                    ── pré-requisito
        T11 Sonnet 5        (depois de T10)
        T12 Prompt caching  (depois de T11 — cache é model-scoped)
```

**Parar e revisar ao fim de cada fase.** As Fases 1 e 2 mexem em DLP e auth —
diff grande é exatamente onde revisão desatenta dói.
