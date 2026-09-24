# Pitacos do Fable 2 — Segunda varredura e plano até o evento

Data: 2026-09-24. Cópia em Markdown do documento
https://claude.ai/code/artifact/8dc958fd-32cc-411a-80de-39b592a66805
Complementa `docs/pitacos-do-fable.md` (18/09); não o substitui. **Nada foi alterado no código.**

Dos 58 itens de 18/09, 29 estão fechados com teste e só 8 seguem abertos. O código novo trouxe um incidente ativo em produção hoje e um beco sem saída de sessão no chat que derruba o uso no celular, o cenário do evento. A suíte passou de 1263 para 1614 testes e a cobertura real subiu para 83%.

## Incidente ativo: agendadores desligados em produção

Desde o deploy de hoje às 14:56, nenhum processo do backend roda o expurgo LGPD, a vigilância nem o pipeline de notícias. O log do Railway mostra os dois workers escrevendo "Agendador 'agendadores': outro processo já é o líder; não vou rodar", e nenhuma linha "este processo é o líder" depois.

**Causa.** A eleição de líder em `app/core/lider.py` tenta o lock uma única vez, no boot. No deploy, o container novo sobe enquanto o antigo ainda segura o lock, os dois workers novos desistem, e quando o antigo morre ninguém assume. É determinístico: acontece em todo deploy a partir do segundo com esse código. A vigilância, que deveria alarmar a parada do expurgo, mora no mesmo líder ausente. É o incidente dos 39 dias sem expurgo reintroduzido pela correção que deveria evitá-lo.

**Hoje, sem código.** Quando o deploy em andamento terminar, usar Restart no serviço do backend, não Redeploy. O Restart mata o processo antes de subir o novo, o lock fica livre e o worker novo vira líder. Conferir a linha "este processo é o líder" no log. Repetir depois de cada deploy até a correção entrar.

**Correção.** Uma tarefa em segundo plano que tenta o lock a cada 60 s e sobe os agendadores ao conseguir, e que os derruba se a conexão dedicada cair. Esforço M. Teste: dois processos, o primeiro solta o lock, o segundo precisa assumir em menos de dois minutos.

**Efeito acumulado.** O expurgo é idempotente e recupera o atraso na primeira rodada. A coleta de notícias e os resumos das faixas perdidas não são recuperados.

## Placar dos 58 itens de 18/09

Cada item foi reconferido no código atual, e cada nota de fase foi tratada como alegação a verificar. Nenhum item regrediu.

| Status | Quantidade | Itens |
| --- | --- | --- |
| Fechado com teste | 29 | 1, 4, 5, 6, 8, 9, 10, 11, 12, 13, 14, 16, 19, 20, 21, 22, 23, 25, 28, 29, 30, 31, 32, 33, 35, 39, 41, 49, 51 |
| Fechado sem teste | 3 | 37 cache estático, 38 celular, 42 notícias sem código repetido |
| Parcial | 15 | 3, 18, 24, 26, 27, 34, 36, 40, 43, 48, 52, 53, 55, 57, 58 |
| Desvio deliberado que fecha o risco | 3 | 2 remoção de DEA, 47 CORS, 50 token no embed |
| Aberto | 8 | 7, 15, 17, 44, 45, 46, 54, 56 |

**O que resta nos parciais que importa**

- **3, GPS.** O aviso e o botão existem, mas quando a localização falha a busca ainda roda em torno de São Paulo e a lista aparece sob o aviso. Só a lógica pura tem teste.
- **18, conexões.** O orquestrador está resolvido e testado com pool real. Continuam presas a conexão do stream do agregador, oculto na interface, e a do upload durante a extração.
- **24, seed de modelos.** O script existe, mas o JSON está vazio e o teste isenta justamente os seis modelos em uso. A invariante passa sem provar nada.
- **26, memória.** Upload em blocos resolvido. Imagens em base64 seguem inteiras na memória durante o stream.
- **27, servidor.** Timeouts e heartbeat feitos. A variável de drenagem do Railway depende do painel.
- **34, campo durante a resposta.** Editar e Parar feitos. Devolver o foco ao terminar não foi feito.
- **36, troca de conversa.** Corrida fechada. Cache não feito.
- **53, duas implementações.** A rota antiga está marcada obsoleta e medida. Os 14 blocos duplicados só saem com ela.
- **58, higiene.** O `settings.local.json` continua versionado apesar do `.gitignore`. Os dois ambientes virtuais e o protótipo de 28 MB continuam na pasta.

**Abertos que pesam.** O item 7 piorou: são seis dumps agora, 69 MB, com um novo do dia 21, nenhum movido nem criptografado. O item 15, leads sem contato fora do iframe, segue como estava.

**Três desvios que valem registro.** A remoção de DEA exige duas origens distintas em vez de índice único, porque uma turma de ACLS no mesmo wi-fi confirma o mesmo aparelho de propósito. O CORS com credenciais continua para a origem do LMS parceiro, porque não se sabe se a página deles chama a API. O embed não limpa o token na entrada porque os apps nativos da Waid abrem sem iframe e dependem do login por código.

## Achados novos, ranqueados pelo impacto no evento

São 31 achados no código escrito entre 18 e 24 de setembro. A numeração começa em 59 para não colidir com o relatório anterior. Gravidade e status seguem a mesma escala de lá. "Executado" aqui significa reproduzido na suíte ou lido no log de produção.

### Faixa 1. Incidente ativo ou bloqueio do uso no celular

| # | Achado | Eixo | Gravidade | Impacto | Esforço | Status |
| --- | --- | --- | --- | --- | --- | --- |
| 59 | Eleição de líder decide uma vez no boot; todo deploy deixa o backend sem agendadores | Backend | Crítica | Expurgo LGPD, vigilância e notícias parados desde hoje. Sem alarme, porque o alarme mora no mesmo líder | M | Executado, log de produção |
| 60 | No chat, um 401 é beco sem saída: sem reentrada, sem botão, e a renovação ignora o 401 de propósito | Frontend | Crítica | "Sair" em qualquer aparelho revoga todos. O médico no celular vê "sessão expirada" por até uma hora sem como entrar. Falha de renovação em wi-fi ruim dá no mesmo | P a M | Confirmado |
| 61 | Casca mobile nasce desligada sem `VITE_SHELL_MOVEL=on` no Railway | Frontend | Alta | Sem a variável, o evento roda na casca desktop espremida | P | Confirmado, depende do painel |
| 62 | Agendador de hora em hora deriva e pula horas | Backend | Alta | Cada rodada dorme 3600 s depois de terminar. A hora pulada perde a coleta do dia ou o resumo de uma faixa inteira | P | Confirmado |
| 63 | Calculadoras: 401 no meio do formulário redireciona e perde os campos | Frontend | Alta | Assistente de risco com 15 campos preenchidos volta vazio depois da reentrada | M | Confirmado |
| 64 | Android: teclado nunca é detectado na casca mobile | Frontend | Alta | Saudação não some e a barra de abas fica sobre o teclado, comendo 60 px do campo | P | Inferido, precisa de aparelho |

### Faixa 2. Dados, privacidade e robustez

| # | Achado | Eixo | Gravidade | Impacto | Esforço | Status |
| --- | --- | --- | --- | --- | --- | --- |
| 65 | Conta inativa com o mesmo e-mail derruba o embed com 500; conta inativa por identificador recebe token | Backend | Média | Médico desativado não recebe recusa clara, e a entrada por identificador ignora o status | P | Confirmado |
| 66 | Interações em andamento ficam órfãs para sempre e aparecem como pergunta sem resposta | Backend | Média | Parar, falha ou queda depois do commit deixa a linha. Tokens já cobrados do modelo primário não são registrados | M | Confirmado |
| 67 | Notícias antigas seguem com HTML sem sanitização no servidor | Segurança | Média | A lista de permissão vale só na escrita. Tudo publicado antes do deploy mantém o que o modelo emitiu | P | Confirmado |
| 68 | Notícias: todo 401 recarrega a página, e a trava de 60 s deixa o app sem tela de login | Frontend | Média | Edição de temas perdida; depois da trava, nada responde por um minuto | P | Confirmado |
| 69 | Reentrada remonta o app e deixa a pilha de camadas suja | Frontend | Média | Depois da reentrada, gaveta que não fecha ou botão voltar que sai da seção | P | Inferido |
| 70 | Handshake de 30 s roda mesmo com token válido | Frontend | Média | Ponte presente e muda deixa o médico 30 s no spinner | P | Precisa de aparelho |
| 71 | `sessionStorage` sem proteção no consentimento de imagem | Frontend | Média | Em webview com armazenamento bloqueado, nenhuma imagem sobe | P | Inferido |
| 72 | "Sair" aparece na casca desktop dentro do iframe e some na mobile | Frontend | Média | Inconsistente, e o Sair do desktop revoga o celular | P | Confirmado |
| 73 | Stream do agregador e upload prendem a conexão de banco | Capacidade | Média | Mesma classe do item 18. O agregador está oculto; o upload prende por segundos em PDF grande | P | Confirmado |
| 74 | Data Ocean usa o pool HTTP curto, e é a chamada mais longa | Capacidade | Média | Cada consulta ocupa uma das 100 conexões da triagem e do login por dezenas de segundos | P | Confirmado |
| 75 | Cadência do PubMed é por processo, e agora são dois workers | Capacidade | Média | 16 por segundo contra um teto de 10. Bloqueio da NCBI derruba a validação para todos | P | Confirmado |
| 76 | Seed de modelos com verde falso | Operação | Média | Já no placar como item 24. Um banco restaurado do schema não responde em nenhum modo | P | Confirmado |
| 77 | Corpo em chunks contorna o limite de tamanho nas rotas JSON | Segurança | Baixa | Só fora do navegador. Um cliente pode empurrar gigabytes para a memória de um worker | P | Confirmado |

### Faixa 3. Subida e operação

| # | Achado | Eixo | Gravidade | Impacto | Esforço | Status |
| --- | --- | --- | --- | --- | --- | --- |
| 78 | Roteiro de subida diz "executado" e mantém caixas desmarcadas; a premissa do estado de produção não está registrada | Operação | Alta | Quem lê não sabe o que falta nem qual commit está no ar | P | Confirmado |
| 79 | Deploy dos frontends antes do backend quebra a página de temas das notícias | Operação | Média | Campo `agenda` ausente vira tela branca durante o descompasso | P | Confirmado |
| 80 | `CMD` em forma de shell pode engolir o SIGTERM | Operação | Média | Se o shell não repassar o sinal, os 90 s de drenagem não valem nada | P | Não verificado |
| 81 | Readiness acoplada ao Redis, e `REDIS_URL` nunca foi confirmada no painel | Operação | Média | Sem Redis, ou o deploy nunca fica saudável, ou os limites viram por worker em silêncio | P | Depende do painel |
| 82 | `NOTICIAS_URL` errada desde a fase 0, e nada no código pega isso | Operação | Média | Links do resumo por e-mail quebrados na semana do evento. O valor errado também entra na lista de origens confiáveis | P | Confirmado |
| 83 | Restore nunca ensaiado de novo; o dump de 21/09 é 27% menor que o de 09/09 | Operação | Média | O único caminho de recuperação é um arquivo que ninguém provou restaurar | P | Confirmado |
| 84 | Script de prontidão não lê as configurações reais | Operação | Baixa | Diz "tudo pronto" e o container morre no boot por falta de `DEA_IP_HASH_SALT` | P | Confirmado |

### Faixa 4. Baixa gravidade

| # | Achado | Esforço |
| --- | --- | --- |
| 85 | `como_lider` faz `yield` duas vezes se o corpo do lifespan levantar, mascarando o erro original | P |
| 86 | O heartbeat do stream não fecha o gerador embrulhado; sessão e transação só fecham no coletor de lixo | P |
| 87 | Dois cliques em "enviar código" criam dois códigos ativos e a verificação dá 500 | P |
| 88 | Falha do SendGrid depois do 204 só loga, sem alarme | P |
| 89 | Nome só com espaços quebra o resumo por e-mail daquele usuário | P |
| 90 | Metrônomo sem link de telefone para o 192; "próxima troca" atrasa pelo tempo da interrupção | P |
| 91 | Erros 500 saem sem cabeçalhos de CORS e de segurança; o navegador não lê o corpo | P |
| 92 | Ramo `unsupported_mode` morto no chat; docstrings dos agendadores contradizem a eleição de líder; comentário errado sobre ordem dos middlewares | P |
| 93 | Três cópias idênticas do logout entre apps, com três semânticas diferentes de "sessão expirou" | M |

## Detalhe dos críticos e altos

### 59. Eleição de líder sem nova tentativa

Detalhado na primeira seção. Dois pontos a mais: se o Postgres estiver fora do ar por um segundo no boot, o resultado é o mesmo, e a conexão dedicada de cada worker que perdeu a eleição fica aberta e ociosa pela vida do processo. O teste `tests/test_lider.py` cobre exclusividade e falha do banco, não reaquisição.

### 60. No chat, um 401 é beco sem saída

- **Onde:** `frontend-app/src/api/erros.ts` linha 48 transforma o 401 em mensagem; `frontend-app/src/chat/useChatController.ts` linhas 255 a 263 a exibem como balão sem ação. `shared/embed/sessao.ts` linhas 130 a 133 ignoram o 401 da renovação de propósito, esperando que "a próxima chamada leve à reentrada pelo caminho normal". No chat esse caminho não existe: nenhum arquivo em `frontend-app/src` chama a reserva de reentrada.
- **Gatilho 1, confirmado no backend:** `POST /auth/logout` incrementa a versão do token e derruba todos os aparelhos. O médico toca "Sair" nas calculadoras dentro do app da Waid, ou no computador de manhã, e o chat do celular fica com um token que ainda tem 40 minutos de validade mas é recusado em toda chamada. A tela mostra "Sua sessão expirou. Entre novamente" e não há botão nem redirecionamento. Dentro do iframe o Sair está escondido, e no app nativo o Sair leva ao login por código, não ao handshake.
- **Gatilho 2, inferido:** aba em primeiro plano, duas renovações falham no wi-fi do evento, o token expira aos 60 minutos, mesmo beco. Em webview Android antigo, `AbortSignal.timeout` não existe e a renovação nunca funciona.
- **Também engolido:** 401 ao abrir uma conversa vira "Nova consulta" vazia em silêncio; 401 na lista vira "Erro ao carregar histórico"; 401 no upload mostra o texto cru do servidor.
- **Correção:** um `sessaoExpirou()` no chat igual ao das calculadoras, chamado no 401 do controller, da lista, da conversa e do upload, mais um botão "Entrar novamente" no balão. A renovação deve tratar 401 como expiração na próxima volta.
- **Teste:** stream que devolve 401 exige navegação para a rota de entrada e reserva de reentrada marcada.

### 61. Casca mobile desligada por padrão

`frontend-app/src/shell/layout.ts` linhas 74 a 76 tratam qualquer valor diferente de `on` ou `qa` como `off`. O Dockerfile declara o ARG sem valor. Sem a variável no painel, o celular recebe a casca desktop e o pacote da casca mobile nem é baixado. O override `?layout=` fica na `sessionStorage` pela vida do webview, então um link de QA compartilhado prende o médico na casca errada até `?layout=auto`. Conferir em `/diagnostico-embed` o campo "Flag da build".

### 62. Agendador que pula horas

`app/services/news_agendado.py` linhas 85 a 97: a rodada roda, depois dorme 3600 s. Cada rodada avança o relógio pela duração do pipeline. Uma rodada às 10:59:30 que leva 90 s acorda às 12:01 e a hora 11 nunca é vista. A coleta é gatilhada por `hour == news_run_hour`, e cada faixa do resumo por `hour == hora_da_faixa`. A hora pulada perde o dia, e a idempotência por data não recupera. Correção: dormir até a próxima virada de hora, ou guardar a última hora processada e recuperar as perdidas.

### 63. Calculadoras perdem o formulário no 401

`calculadoras-app/src/lib/auth.ts` linha 118 faz `location.replace` para a reentrada. O destino é guardado, o estado do formulário não. Correção: guardar o estado em `sessionStorage` por slug antes de sair e reidratar, ou tentar a chamada de novo uma vez depois de uma reentrada silenciosa.

### 64. Teclado invisível no Android

`frontend-app/src/shell/mobile/useTeclado.ts` linha 40 compara `innerHeight` com a altura do `visualViewport`. Com `interactive-widget=resizes-content`, que a casca define, o Chrome encolhe os dois juntos e a diferença fica em zero. Dentro do iframe do portal a meta é ignorada e a detecção funciona. Correção: comparar com a altura medida na montagem.

### 65. Conta inativa no embed

`app/services/auth_service.py` linha 214 busca por e-mail só entre ativos; se a conta existe inativa, a linha 248 tenta criar outra com o mesmo e-mail e a unicidade estoura em 500. A busca por identificador na linha 210 não filtra status, então uma conta desativada recebe token e depois leva 401 em tudo. Correção: tratar `IntegrityError`, rebuscar sem o filtro e recusar inativo com 403; filtrar status na busca por identificador.

### 66. Interações órfãs

A interação nasce `em_andamento` e é comitada antes do modelo, o que foi a correção certa para o pool. Mas só a gravação da resposta a marca como concluída. Parar, falha da cadeia de contingência ou queda deixam a linha para sempre, e a listagem da conversa a mostra como pergunta sem resposta. Nenhum expurgo toca nela. Correção: no `except` externo e no cancelamento, abrir sessão curta e marcar como interrompida, com varredura periódica das linhas com mais de dez minutos.

## Subida e operação

**O estado de produção precisa ser registrado.** O roteiro diz "executado em 21/09" com o commit `6fd05ab`, e os 14 commits já estão em `origin/main`. O log de hoje confirma que o deploy automático está ligado e que o código com eleição de líder está no ar. Nenhum documento do repositório registra isso. Antes de qualquer passo, anotar no roteiro o hash ativo no Railway e o resultado de `SELECT version_num FROM alembic_version`, que deve ser `015_otp_code_hmac`.

**Migrations.** As três são reversíveis por código e não reescrevem tabela. A tabela de sintomas do roteiro está errada em dois pontos: sem a 014, toda rota autenticada devolve 500, não só o login; sem a 015, o pedido de código por e-mail devolve 500 e o médico nunca recebe o código. Não há deriva real entre modelos e migrations além das três. Os falsos positivos do `alembic check` vêm de `alembic/env.py` sem `include_schemas`, e isso continua sem correção.

**Descompasso entre serviços.** O backend baixa o spaCy no build, então os frontends quase sempre entram no ar antes. Nesse intervalo, a página de temas do app de notícias quebra, porque lê o campo `agenda` que o backend antigo não devolve. Tudo o mais tolera o descompasso nos dois sentidos: logout e renovação falham em silêncio contra backend antigo, e o backend novo mantém a rota antiga do orquestrador.

**Variáveis.** Nenhuma nova obrigatória. Três dependem de confirmação no painel: `REDIS_URL`, que sem valor cai em `localhost` e leva a readiness a 503 ou os limites a por worker; `NOTICIAS_URL`, errada desde a fase 0 e agora também na lista de origens confiáveis; `RAILWAY_DEPLOYMENT_DRAINING_SECONDS=90`, sem a qual a drenagem não existe. O caminho do health check do Railway não está registrado em lugar nenhum. `PHOENIX_API_KEY` não aparece em arquivo versionado, e a rotação segue pendente.

**Janela de deploy.** Entre 08:00 e 10:00 de Brasília o container antigo e o novo podem rodar a coleta e o resumo em dobro. Fora dessa janela, o overlap é inofensivo.

**Backup.** O ensaio de restore aconteceu uma vez, em 19/08, e nunca mais. O roteiro manda subir o dump para o Drive, mas não manda restaurar em um banco descartável e rodar `verificar_restore` antes de migrar. O dump de 21/09 tem 8,5 MB contra 11,7 MB do de 09/09; a diferença é plausível pelo expurgo de imagens, mas ninguém conferiu.

**CI.** Os sete lockfiles têm as variantes Linux e musl, então o `npm ci` no Ubuntu passa. Mas o CI não é portão: o push na `main` faz deploy independentemente do resultado, salvo se "wait for CI" estiver ligado no Railway, o que não foi possível verificar. O `pip-audit` estrito pode ficar vermelho por CVE sem relação com a mudança.

**Correções no roteiro `docs/subir-para-producao.md`**

1. Trocar o banner "executado" pelo hash ativo e pela revisão do Alembic, e marcar as caixas já feitas.
2. Registrar o caminho do health check e a decisão sobre `REDIS_URL`.
3. Antes de migrar, restaurar o dump em banco descartável e rodar `verificar_restore`.
4. Corrigir a tabela de sintomas das migrations 014 e 015.
5. Backend primeiro vira passo obrigatório, esperando `/health/ready` antes dos frontends.
6. Depois de cada deploy, Restart do backend e conferência da linha "este processo é o líder", até o item 59 ser corrigido.
7. Mover `REDIS_URL` e a variável de drenagem da seção "não bloqueia" para os pré-requisitos.
8. `sh -c "exec uvicorn ..."` no Dockerfile, para garantir que o SIGTERM chegue ao processo.

## Testes

A suíte hoje valida o que descreve. Os cinco ajustes do harness foram feitos e confirmados por sonda, não só por leitura.

| Medida | 18/09 | 24/09 |
| --- | --- | --- |
| Backend | 1263 passam | 1614 passam, 6 pulados, 0 falhas, 0 intermitentes em duas rodadas |
| Cobertura combinada | 75% mal medida | 83%, linhas 85,8%, ramos 70,7% |
| Portão do CI | 50% | 75%, com folga de 8 pontos |
| Testes que vazam para a rede | 23 | 0 |
| Chat principal | 175 testes | 318 testes, 77% de instruções |
| DEA | 18 | 43 |
| Tempo do backend | 60 s | 76 a 112 s |

**Harness, confirmado por sondas escritas fora do repositório.** Uma chamada HTTP real reprova o teste mesmo engolida por `except Exception` ou por `gather` com exceções empacotadas. Um `rollback()` do app dentro do teste preserva o cenário, inclusive no ramo real de erro do stream. Disjuntor aberto e rate limit estourado não vazam para o teste seguinte. A fixture de conexões reais trunca antes e depois. Resta: o esquema ainda vem de `create_all`, e nada confere paridade com as migrations; o CI faz o ciclo de downgrade e upgrade, mas uma coluna nova sem migration passa.

**Qualidade dos 30 arquivos novos.** A maioria exercita o caminho real por HTTP ou por transporte falso. Destaques positivos: o teste de destino dos dados percorre as chaves estrangeiras de forma transitiva e falha em tabela nova; o de origens enumera as rotas de escrita do OpenAPI; o do PharmaDB dirige o serviço real; o de concorrência usa pool real de 2 com provedor em barreira. Ressalvas: o de seed de modelos isenta os seis modelos em uso; o contrato SSE do frontend lê o código-fonte do controller como texto, mas falha em voz alta em vez de passar vazio; três asserções de relógio podem oscilar em runner carregado, em `test_otp.py`, `test_infra_de_capacidade.py` e `test_sse_heartbeat.py`.

**O que segue descoberto e importa**

- Acerto do cache semântico pelo stream, com a troca de identificadores entre usuários: 0%. É o caminho cuja docstring descreve o vazamento de privacidade.
- Gravação no cache semântico pelo stream, com a trava que mantém resposta condicionada por pasta fora do cache global: 0%.
- Esclarecimento pelo stream: 0%.
- Conversão de saída do modelo em entradas de calculadora: 0 de 28 ramos. É clínico.
- Verificação e pontuação do PubMed, os sinais de confiança mostrados ao médico: cerca de 0%.
- Handler global de 500: nunca executado, então nada prova que a pilha não chega ao cliente.
- Mascaramento na saída dos modos de farmácia: o código roda, mas nenhum teste alimenta texto com dado de paciente e confere o que foi gravado.
- Perda do lock de líder: não há caminho no código para testar.
- No chat: eventos de esclarecimento, acerto de cache e erro do servidor no controller; fluxos de mover e excluir pasta na casca mobile; detecção de teclado em 27%.

**Testes propostos, por risco sobre esforço**

1. Acerto de cache pelo stream com identificadores de outro usuário, exigindo linhas do usuário atual e custo zero. Pequeno.
2. Bula com CPF no texto, exigindo resposta gravada sem o CPF. Pequeno.
3. Conversão de entradas de calculadora com vírgula decimal, unidade no texto e chave desconhecida. Médio.
4. Rota que levanta exceção, exigindo 500 genérico sem pilha e com cabeçalhos. Muito pequeno.
5. Reaquisição do lock de líder, depois da correção do item 59. Médio.
6. Verificação do PubMed por transporte falso, com citação válida, inválida e timeout. Médio.
7. Reentrada no 401 do chat, item 60. Pequeno.
8. Eventos de esclarecimento, cache e erro no controller. Pequeno.

## Plano até o evento

Três semanas. A regra é a mesma da primeira rodada: primeiro o que está quebrado ou vai quebrar no evento, depois o que dá confiança, e só então o resto. Nada da fase 7 antiga entra antes do evento.

| Semana | Objetivo | Itens | Esforço |
| --- | --- | --- | --- |
| Hoje | Religar os agendadores e registrar o estado de produção | 59 paliativo, 78, 81, 82 | meio dia, sem código |
| 1 | Corrigir o que derruba o celular e a operação | 59, 60, 61, 62, 63, 65, 68, 72, 76, 79, 80 | 5 a 7 dias |
| 2 | Homologar no aparelho e fechar o que a homologação achar | roteiro da próxima seção, 64, 69, 70, 71 | 4 a 6 dias |
| 3 | Congelar, ensaiar a subida, medir | 83, 66, 73, 74, 75, testes 1 a 4 | 3 a 4 dias |

### Hoje

- [ ] Restart do backend depois do deploy em andamento; conferir "este processo é o líder" no log.
- [ ] Anotar no roteiro o hash ativo no Railway e a revisão do Alembic.
- [ ] Conferir `REDIS_URL`, `NOTICIAS_URL`, `RAILWAY_DEPLOYMENT_DRAINING_SECONDS` e o caminho do health check no painel.
- [ ] Definir `VITE_SHELL_MOVEL=on` no serviço do chat, se a casca mobile for para o evento.
- [ ] Mover e criptografar os seis dumps. É o terceiro relatório que pede isso.

### Semana 1. Correções

1. **59.** Eleição com nova tentativa periódica e teste de reaquisição. Primeiro de tudo, porque cada deploy da semana repete o incidente.
2. **60.** Reentrada no 401 do chat, botão "Entrar novamente", renovação tratando 401 como expiração. Junto, **72**: Sair escondido no iframe também na casca desktop.
3. **62.** Agendador dormindo até a virada da hora.
4. **63.** Formulário das calculadoras preservado na reentrada.
5. **65.** Conta inativa no embed com 403 claro.
6. **68.** Notícias: trava de reentrada leva à tela de login, não ao vazio.
7. **76.** Exportar os preços de produção para o JSON e esvaziar a lista de isenção do teste.
8. **79 e 80.** Campo `agenda` opcional no cliente de notícias; `exec` no `CMD` do Dockerfile.
9. **61.** Se a casca mobile for para o evento, decidir agora e travar a flag.

**Aceite:** dois deploys seguidos sem Restart e o log mostra líder nos dois. Sair no computador e o celular reentra sozinho na próxima chamada. Teste de reaquisição e de reentrada no repositório.

### Semana 2. Homologação no aparelho

Rodar o roteiro da próxima seção em Android e iPhone reais, dentro do app da Waid e no portal. Corrigir o que aparecer, com prioridade para **64** teclado, **69** pilha de camadas, **70** handshake com token válido e **71** armazenamento bloqueado. Esses quatro só se confirmam no aparelho, por isso ficam depois da primeira rodada de homologação e não antes.

**Aceite:** os 16 passos do roteiro com resultado anotado. Nenhum passo com "não consegui entrar".

### Semana 3. Congelar

1. **83.** Restaurar o dump mais recente em banco descartável e rodar `verificar_restore`. Anotar o resultado.
2. **66.** Interações interrompidas marcadas e varridas.
3. **73, 74, 75.** Commit no agregador antes do stream, Data Ocean no pool longo, cadência do PubMed dividida pelos workers.
4. Testes propostos 1 a 4.
5. Congelamento de código três dias antes do evento. Deploy fora da janela de 08:00 a 10:00. Restart e conferência do líder depois.

**Aceite:** um ensaio de subida completo seguindo o roteiro corrigido, com o hash final registrado.

**Fica para depois do evento:** itens 67, 77, 84 a 93, os oito abertos do primeiro relatório e a limpeza estrutural da fase 7 antiga.

## Roteiro de homologação no celular

Nada abaixo se prova em jsdom. Cada passo precisa de aparelho real, e a maioria precisa do app da Waid. Anotar o resultado de cada um.

1. **App da Waid, Android e iPhone, chat.** Deixar o app em segundo plano por mais de 65 minutos e voltar. Esperado: spinner compartilhado e a mesma tela, sem código por e-mail. Anotar se a conversa aberta continua na tela e se a gaveta e o botão voltar funcionam depois.
2. **Mesmo cenário com a gaveta aberta ao minimizar.** Ao voltar: abrir a gaveta, tocar uma conversa, voltar pelo hardware. A gaveta fecha? A seção sai?
3. **Revogação.** Sair nas calculadoras dentro do app, ou no computador, e abrir o chat no celular em menos de 60 minutos. Hoje deve reproduzir o beco do item 60. Depois da correção, reentrada silenciosa.
4. **Ponte de identidade.** Abrir `/diagnostico-embed` dentro do app. "Ponte de identidade: SIM" e "Hospedeiro: hospedado" na primeira pintura. Se aparecer "avulso", a barra de abas, o logo e o Sair vão aparecer dentro do app.
5. **Latência do handshake.** Tempo da abertura até o chat, esperado abaixo de 3 s. Se a ponte não responder, confirmar os 30 s e o "Entrar por e-mail".
6. **Botão voltar do Android** com gaveta, com folha e sem nada aberto. A Waid repassa ao webview ou fecha a seção?
7. **Teclado.** Android Chrome, webview e iOS: campo visível com teclado aberto, saudação e barra de abas escondidas, sem zoom ao focar, folha alcançável com teclado aberto.
8. **Iframe do portal no iPhone Safari.** Teclado aberto cobre o campo? O iOS não redimensiona iframes.
9. **Iframe do portal, computador e celular.** Enviar uma pergunta: a página do LMS rola sozinha? Voltar do navegador com a gaveta aberta fecha a gaveta ou sai da página?
10. **Rotação** com resposta em andamento, no celular e no iPad. O texto continua no mesmo balão, rascunho preservado, rolagem mantida.
11. **`/diagnostico-embed` no app:** `localStorage: OK`, flag da build `on`, suporte a `100dvh`, margens de área segura em zero, casca automática `mobile`.
12. **Webview com armazenamento bloqueado**, iOS com "bloquear todos os cookies" ou aba privada: consentimento de imagem e upload funcionam; trava de reentrada cai para o login.
13. **Servidor estático em produção:** `curl -I` em um arquivo com hash mostra `immutable`; rota profunda devolve `index.html` com `no-cache`; asset inexistente devolve 404 e não HTML; `frame-ancestors` presente e o iframe abre no portal real.
14. **DEA no iOS**, Safari e dentro do webview: wake lock, áudio do metrônomo depois de bloquear a tela e depois de uma ligação, "Retomar som" pede um toque. Android: áudio continua com a tela apagada, `tel:192` abre o discador.
15. **Webview Android antigo**, abaixo da versão 103: a renovação funciona? Se não, esperar o beco aos 60 minutos.
16. **Notícias dentro do app:** editar temas por mais de um minuto depois de um Sair em outro lugar. Observar o recarregamento e a perda das seleções, item 68.

Além desses, os itens de homologação das fases 2, 5 e 6 do inventário `docs/pendencias.md` continuam válidos e ainda não têm resultado anotado.

## Maturidade revista e limites desta varredura

**Nota geral: 7,5 de 10.** Subiu meio ponto em seis dias, e não mais, por dois motivos. O primeiro é que o incidente ativo é da classe mais grave para um produto de saúde: uma garantia silenciosa que parou sem avisar, e parou justamente pelo código que veio para protegê-la. O segundo é que o código mobile ainda não foi visto em aparelho nenhum.

| Área | 18/09 | 24/09 | Motivo |
| --- | --- | --- | --- |
| Segurança de aplicação | 8 | 8,5 | Sessão, logout, OTP com HMAC e cabeçalhos fechados. Fica a conta inativa e o HTML antigo |
| Arquitetura e disciplina | 8 | 8 | Mantém os hábitos. Sete fases em três dias deixaram docstrings contraditórias e um roteiro que diz "executado" com caixas abertas |
| Testes | 6 | 8 | Harness confiável, 1614 testes, 83% real. Faltam cache semântico, PubMed e calculadoras por IA |
| Prontidão para escala | 4 | 6,5 | Teto de conexões removido e provado. Dois workers. Ainda sem ensaio de carga, e o PubMed dobra com os workers |
| LGPD na prática | 5 | 7,5 | Exclusão e export completos com invariante estrutural. Desconta o expurgo parado hoje |
| Frontend | 7 | 6,5 | Caiu. A casca mobile é boa em código, mas o beco do 401 e o teclado no Android são do tipo que impede o uso no evento, e nada foi homologado em aparelho |
| Operação | 6 | 5,5 | Caiu. Eleição de líder quebrada em produção, roteiro desatualizado, restore não ensaiado, dumps ainda no notebook |

**O padrão que se repete.** Na primeira varredura, o teste confirmava o fluxo imaginado e não o real. Desta vez o harness resolveu isso, e o padrão mudou de lugar: agora é o deploy. A eleição de líder passa em todo teste e falha em todo deploy, porque nenhum teste tem dois containers com overlap. O beco do 401 passa em jsdom e falha no celular, porque nenhum teste tem dois aparelhos. O próximo degrau de maturidade não é mais teste; é homologação em ambiente real antes de cada subida.

**Não verificado**

- Qual commit o Railway está rodando e se "wait for CI" está ligado. O log de hoje prova que o deploy automático existe.
- Os valores de `REDIS_URL`, `NOTICIAS_URL`, `FRONTEND_URL`, `SENTRY_DSN` e da drenagem no painel.
- Se o shell do container repassa o SIGTERM.
- Tudo o que está no roteiro de homologação: nenhum aparelho real, nenhum app da Waid.
- Deriva entre modelos e migrations contra o banco real; só por leitura.
- Os itens marcados "Inferido" e "Relatado" nas tabelas não tiveram segunda conferência.
- Nenhum número de capacidade foi medido sob carga.

---

Documento online, com comentários e edição: https://claude.ai/code/artifact/8dc958fd-32cc-411a-80de-39b592a66805
