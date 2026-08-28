# Runbook operacional — Médico 360

O que fazer quando algo quebra em produção. Escrito para quem **não** escreveu o
código conseguir agir sozinho.

Ambiente: Railway (backend + Postgres + Redis). Observabilidade: Sentry (erros de
aplicação) e Arize Phoenix (traces de LLM).

---

## Primeiro passo, sempre

```bash
curl -s https://<host>/api/v1/health/ready | jq
```

- **200 `ready`** — a aplicação está sadia; o problema é outro (provedor externo,
  front-end, rede do usuário).
- **503 `degraded`** — o campo `dependencies` diz qual componente caiu.
- **Sem resposta** — o processo está fora. Verifique `/api/v1/health` (liveness):
  se ele também não responde, é caso de reinício do serviço no Railway.

A distinção importa: **liveness falhando = reinicie**; **readiness falhando = pare
de mandar tráfego, mas reiniciar não resolve.**

Todo erro no Sentry carrega a tag `request_id`. O mesmo id sai no header
`X-Request-ID` da resposta e em cada linha de log — é por ele que se reconstrói
uma requisição inteira.

---

## Postgres fora do ar

**Sintoma:** `/health/ready` retorna 503 com `postgres.ok = false`. Todas as rotas
autenticadas falham (a validação de token consulta o banco).

1. Painel do Railway → serviço Postgres → verificar status e métrica de conexões.
2. Se for esgotamento de pool: o backend abre `pool_size=30 + max_overflow=10` por
   processo. Com múltiplos workers isso multiplica. Confira o limite do plano.
3. Reinício do backend libera conexões presas, mas trata sintoma, não causa.

**Não** rode migrations para "consertar" — veja a seção de limitação abaixo.

---

## Redis fora do ar

**Sintoma:** `/health/ready` retorna 503 com `redis.ok = false`.

O sistema **continua funcionando**, degradado: cache semântico e cache de triagem
passam a errar sempre, o que aumenta latência e custo de LLM. O throttle de OTP
por e-mail falha aberto (o limite por IP continua valendo).

Prioridade média: não derruba o produto, mas cada minuto custa dinheiro em chamada
de modelo que seria evitada por cache.

---

## Provedor de LLM fora do ar ou com cota estourada

**Sintoma:** usuários relatam "não foi possível processar sua consulta"; Sentry
mostra erro do provedor.

O orquestrador já tem fallback automático: se o modelo primário do modo falha, ele
tenta a lista alternativa (`_fallback_complete`). A mensagem acima só aparece
quando **todos** falham.

1. Confira no Sentry qual provedor está falhando e o código de erro.
2. 401/403 → chave expirada ou revogada. Rotacione (ver abaixo).
3. 429 → cota. Verifique o painel do provedor.
4. Mitigação imediata: desative o modelo problemático marcando
   `model_pricing.status = false` no banco. O agregador passa a ignorá-lo e o
   orquestrador cai no fallback. Não exige deploy.

O Agregador é resiliente por regra (RN-AGR-001): a falha de um modelo não derruba
os demais, aparece como erro só naquele card.

---

## PharmaDB ou PubMed fora do ar

**Sintoma:** respostas clínicas saem sem checagem de interação ou sem validação de
citação.

Ambos são enriquecimento *best-effort*: a falha é capturada e a resposta segue com
um aviso ao usuário ("a checagem automática de interações está temporariamente
indisponível"). **Não é incidente de indisponibilidade** — é degradação anunciada.

Ação: abrir chamado com o fornecedor. Nada a fazer do nosso lado.

---

## Rotação de segredos

Todas as variáveis vivem no painel do Railway. Após alterar, o serviço reinicia.

| Segredo | Efeito da rotação |
|---|---|
| `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_AI_API_KEY`, `PERPLEXITY_API_KEY` | Sem impacto para o usuário |
| `PHARMADB_API_KEY` | Sem impacto; o token JWT interno é renovado sozinho |
| `SENDGRID_API_KEY` | Sem impacto; afeta só envio de OTP e convite |
| `JWT_SECRET_KEY` | **Desloga todos os usuários imediatamente.** Todo token emitido vira inválido. Faça em janela de baixo uso e avise. |
| `CURSEDUCA_API_KEY` | O embed para de funcionar até a nova chave valer (fail-closed, por projeto) |

**Atenção:** `CURSEDUCA_VALIDATION_ENABLED` não pode ser `false` em produção — o
startup falha de propósito. Sem essa validação, `/auth/embed/token` emite token
para qualquer e-mail informado.

---

## Restaurar o banco

> ### LEIA PRIMEIRO: o Railway NÃO faz backup deste banco
>
> Verificado em 2026-08-19 no painel: a aba *Backups* diz
> *"This service's volume does not have any backups"* — backup e PITR são
> exclusivos do plano **Pro**, e este serviço não está nele.
>
> Ou seja: **não existe ponto de restauração para clicar.** Se o volume do
> Postgres se perder, a única recuperação possível é a partir de um dump feito
> manualmente (abaixo). Versões anteriores deste runbook mandavam "escolher o
> ponto de restauração no Railway" — instrução que não funcionava e custaria os
> primeiros minutos de um incidente.

### Fazer um backup (o que protege você hoje)

```
python -m scripts.backup_producao --dsn "postgresql://..."
```

A URL sai de Railway → Postgres → *Connect*. Só faz leitura na origem. O script
escolhe a imagem do `pg_dump` conforme a versão do servidor, grava
`backups/medico360-<data>Z.dump` e **verifica com `pg_restore -l` que o arquivo é
legível** — arquivo com tamanho não prova nada, dump truncado também tem tamanho.

Depois, o passo que o script não faz por você: **subir o arquivo para o Drive.**
Dump que só existe no mesmo disco não sobrevive ao incidente que mais assusta.

> **Seu RPO é a idade do último dump.** Um dump semanal significa aceitar perder
> até uma semana. Se isso não é aceitável, ou o backup vira rotina agendada, ou
> o serviço sobe para um plano com PITR — e aí o ensaio abaixo continua valendo,
> porque PITR contratado e nunca testado é promessa, não garantia.

### Restaurar

```
docker run --rm -i pgvector/pgvector:pg16   pg_restore -d "postgresql://URL_DO_BANCO_NOVO" --no-owner --no-privileges < backups/ARQUIVO.dump
```

Sempre para um banco **novo**, nunca por cima do atual. Marque início e fim: esse
intervalo é o RTO real.

### Conferir que o restore veio íntegro

```
python -m scripts.verificar_restore --origem "postgresql://..." --restaurado "postgresql://..."
```

Só lê (pode apontar para produção como origem). Compara **todas** as tabelas de
todos os schemas — `public` e `calculators` —, confere a revisão do Alembic e sai
com código 1 em qualquer divergência. Conferir três tabelas a olho deixaria passar
perda em `consent_logs` ou `audit_logs`, que existem por obrigação regulatória.

Por fim, suba um ambiente de **teste** contra o banco restaurado e confirme
`/api/v1/health/ready` (esse consulta o Postgres de verdade; `/api/v1/health` não).
**Nunca aponte produção para o banco restaurado** — é assim que um ensaio vira
incidente.

> ### Sobre reconstruir o schema
>
> Isto já foi uma limitação: o schema nascia de um `create_all` fora do Alembic e
> `alembic upgrade head` num banco vazio falhava. Hoje existe a migration de
> baseline (`000_baseline`), e o CI prova a cada push que a cadeia aplica do zero
> (job `backend`, step "migrations aplicam do zero"). Isso reconstrói o **schema**,
> não os **dados** — para dados, o caminho é o dump acima.

### Ensaio de 2026-08-19 — números medidos

Primeiro ensaio real, ponta a ponta, contra o banco de produção. Não são
estimativas:

| Medida | Valor |
|---|---|
| Dump de produção | **27s**, 13,8 MiB, 30 tabelas com dados |
| Restore num Postgres 18 vazio | **2s**, `pg_restore` sem erro |
| Aplicação contra o banco restaurado | `/api/v1/health/ready` → **200**, `postgres.ok = true` |
| **RTO mecânico** | **~30s** + o tempo humano de provisionar um banco novo |
| **RPO** | **= idade do último dump** (hoje manual, sem agendamento) |

Dados conferidos no restaurado: 42 `users`, 429 `conversations`, 521
`interactions`, 395 `audit_logs`.

**O RPO é o número frágil aqui.** Os 30 segundos de RTO são ótimos, mas de nada
adiantam se o dump mais recente for de duas semanas atrás. Enquanto o backup for
manual, o RPO é literalmente "quando alguém lembrou". Agendar o dump é o que
transforma esse número em garantia.

### Três achados do ensaio

1. **O banco é compartilhado.** Além de `public` (21 tabelas) e `calculators`
   (6), existe o schema `news` (3 tabelas) — é o `medico360-news`, com cadeia de
   migrations própria (`news.alembic_version`). O dump acima cobre os três; um
   restore recupera os dois serviços juntos.
2. **Duas tabelas fora do versionamento:** `public.legacy_user_mapping` e
   `public.company_legacy_mapping` existem em produção e **nenhuma migration as
   cria**. Reconstruir o schema pelo Alembic não as recriaria. Ambas estão
   **vazias** hoje, então o risco é baixo — mas é dívida registrada, não
   invisível.
3. **Nada do baseline falta em produção** — as migrations são um subconjunto do
   que está lá, nunca o contrário. A cadeia não está atrasada.

---

## Integração lenta (disjuntor aberto)

**Sintoma:** no log, `Circuito 'X' ABERTO após N falha(s)`.

O disjuntor (`app/core/circuit_breaker.py`) corta chamadas para uma integração
que está falhando em sequência, para não gastar o timeout inteiro a cada
requisição. Ele religa sozinho: passado o descanso, deixa uma requisição testar
o terreno e fecha se der certo.

| Integração | Falhas para abrir | Descanso | Efeito enquanto aberto |
|---|---|---|---|
| PharmaDB | 5 | 30s | Resposta sai sem checagem de interação |
| PubMed | 5 | 30s | Resposta sai sem validação de citação |
| Curseduca | 10 | 15s | **Embed para de autenticar** (fail-closed) |

Ação: nenhuma do nosso lado — o circuito se recupera sozinho. Se ficar reabrindo,
o problema é do fornecedor. Só a Curseduca é urgente, porque bloqueia login.

---

## Ativar o rastreamento de erro

O Sentry está implementado mas **desligado**: sem `SENTRY_DSN` o código é no-op.

Para ligar:

1. Criar projeto em `sentry.io` (plano gratuito cobre volume baixo) ou subir uma
   instância de GlitchTip, que é compatível e roda na sua infraestrutura.
2. Definir `SENTRY_DSN` no Railway. Opcionalmente `SENTRY_RELEASE` com o hash do
   commit, para o erro apontar a versão.
3. Configurar alerta por taxa de 5xx e por erro novo, com destino definido —
   sem isso o painel existe mas ninguém é avisado.

**Antes de confiar**, rode a verificação no ambiente real:

```bash
python -m scripts.verificar_sentry
```

Ela envia UM evento de teste com um prompt clínico sintético vivo no escopo e
imprime a lista do que não pode aparecer no painel. Não escreve no banco nem
chama provedor de IA. O evento vai com a tag `verificacao=manual` e título
"VERIFICACAO DE SCRUBBING", para ser fácil de achar e resolver depois.

O scrubbing tem 17 testes automatizados (`tests/test_error_tracking.py`),
incluindo um ponta a ponta que inspeciona o envelope que sairia pela rede. Mas
conferir no painel real custa dois minutos e fecha a dúvida.

Nunca ligar `send_default_pii=True` nem remover o `before_send`: é o que separa
"alerta útil" de "prontuário saindo do país num evento de erro".

---

## Alarmes de vigilância

**O backend se pergunta a cada 6 horas se as garantias silenciosas continuam
valendo** — ver `app/services/vigilancia_agendada.py`. Quando alguma não vale,
abre um `warning` no Sentry com a tag `alarme=<nome>`, no máximo **um por tag
por dia** (alarme repetido é alarme ignorado).

Para ver o estado agora, sem esperar o ciclo e **sem escrever nada**:

```bash
python -m scripts.verificar_vigilancia   # sai 1 se algo estiver em nível de alarme
```

### `alarme=cache_semantico_sem_escrita`

**Significa:** houve tráfego elegível (≥50 interações em `QUICK_SEARCH` ou
`CLINICAL_REASONING` em 7 dias) e a tabela `semantic_cache` não tem **nenhuma**
entrada vigente. A escrita está falhando em silêncio.

1. Procure no log por `[Cache]` — o lookup registra o corpo da resposta quando a
   API recusa (`API recusou o lookup (HTTP ...)`).
2. Causa mais provável: contrato com a API da OpenAI. Foi exatamente assim que o
   cache passou meses desligado — `max_tokens` em vez de `max_completion_tokens`,
   HTTP 400 engolido por um `except`.
3. Confirme a chave: `OPENAI_API_KEY` alimenta a normalização **e** o embedding.
   Sem ela, o cache degrada para sempre-miss sem erro visível.

**Urgência:** média. Nada quebra para o médico — só se paga modelo por toda
pergunta repetida.

### `alarme=custo_escalando`

**Significa:** o gasto com modelo nos últimos 7 dias é ≥3x o dos 7 anteriores,
partindo de uma base ≥US$ 5. Não é crescimento de produto: 3x em uma semana é
laço de retry, abuso, ou um fallback que virou o caminho principal.

1. `SELECT mode, count(*), sum(token_cost_usd) FROM interactions
   WHERE created_at > now() - interval '7 days' GROUP BY 1 ORDER BY 3 DESC;`
2. Compare com a janela anterior. Um modo que explodiu sozinho aponta para
   roteamento; crescimento parelho aponta para volume real de uso.
3. Verifique `is_fallback` em `interaction_responses`: se o provider primário
   está caindo, todo tráfego vai para o fallback, que pode custar mais.

**Urgência:** alta — é dinheiro saindo a cada hora que passa.

### `alarme=expurgo_parado` / `alarme=expurgo_sem_rastro`

**Significa:** não há rodada de expurgo registrada em `audit_logs` há mais de 2
dias (`parado`), ou nunca houve nenhuma (`sem_rastro`). Complementa o
`alarme=expurgo_lgpd`, que dispara quando a rodada **acontece** e acha atraso —
estes dois disparam quando ela **não acontece**, que foi o modo de falha original.

1. `python -m scripts.verificar_expurgo` para ver o passivo.
2. Procure no log por `Rodada de expurgo falhou`.
3. `sem_rastro` logo após um deploy de banco novo é esperado até a primeira
   rodada (90s após o boot). Se persiste, a tarefa não está subindo.

**Urgência:** alta — é obrigação legal (LGPD art. 16), não preferência.

> **Por que isto existe.** O cache semântico ficou meses sem gravar uma linha e
> ninguém soube. O dado para descobrir sempre esteve lá: `interactions.cache_hit`
> é gravado em toda interação, e um `SELECT avg(cache_hit::int)` teria mostrado
> zero a qualquer momento. Não faltou instrumentação — faltou alguém perguntando.
> Estes alarmes são a pergunta, feita pelo próprio backend.

---

## Retenção de dados

**O expurgo roda sozinho, dentro do backend.** Uma tarefa em background dispara
90 segundos após o boot e depois a cada 24 horas — ver
`app/services/expurgo_agendado.py`. **Não há cron a configurar em painel nenhum.**

Cada rodada bem-sucedida grava uma linha em `audit_logs` com
`action='expurgo.rodada'` — é o rastro que responde "quando rodou pela última
vez?" sem depender da memória de quem estava por perto.

Se ele encontrar mais de 2 dias de atraso ao rodar, abre um evento `warning` no
Sentry com a tag `alarme=expurgo_lgpd` — o que significa que o backend ficou
fora do ar por dias ou que a tarefa vinha falhando.

Para conferir à mão, sem apagar nada:

```
python -m scripts.verificar_expurgo      # responde "está em dia?", sai 1 se não
python -m scripts.expurgar_dados_vencidos # limpa agora
```

> **Por que não é cron.** Até 2026-08-27 o expurgo era agendado no painel do
> Railway. O agendamento parou e ninguém soube por **39 dias**: havia 14 imagens
> além do prazo e 8 já expurgadas — a assinatura de um job que rodou uma vez e
> nunca mais. O código estava correto, os testes verdes, e nada avisava.
>
> A causa provável: o Railway executa o start command do serviço e **pula** a
> execução seguinte se a anterior ainda estiver rodando. Com o *Cron Schedule*
> no serviço do backend, o que roda é o `uvicorn`, que nunca encerra — então
> tudo depois da primeira execução foi pulado, em silêncio.
>
> Trocar por outro cron consertaria a instância, não o problema: agendamento em
> painel é invisível a testes, ao CI e a code review. Dentro do processo, ele
> aparece no diff, tem teste, e só some se o backend sumir junto.
>
> **Se ainda houver um Cron Schedule configurado em algum serviço do Railway
> apontando para o expurgo, ele pode ser removido.**

| Dado | Prazo | Por quê |
|---|---|---|
| Imagem crua de arquivo (`image_base64`) | 30 dias | Mais sensível da base: foto de exame ou receita, fora do alcance do DLP |
| Extração de arquivo | 180 dias | Texto extraído, já sanitizado |
| Cache semântico | 30 dias | Guarda prompt e não tem dono |

Se o cron falhar por dias, nada quebra — o expurgo é idempotente e recupera o
atraso na execução seguinte. Confira a contagem no log para comprovar que a
política está sendo cumprida.

**Portabilidade:** o titular exporta os próprios dados em `GET /api/v1/auth/me/export`.

---

## Verificar antes de considerar resolvido

- [ ] `/api/v1/health/ready` retorna 200
- [ ] Uma consulta real no orquestrador responde ponta a ponta
- [ ] Sem erros novos no Sentry nos últimos 15 minutos
- [ ] Se houve rotação de `JWT_SECRET_KEY`: login novo funciona
