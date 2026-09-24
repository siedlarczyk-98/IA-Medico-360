# Pendências do plano — o que falta e de quem é

Atualizado em 2026-09-21. Plano completo em `docs/pitacos-do-fable.md`; resultado da
conferência de produção em `docs/fase-0-conferencia-producao.md`.

O plano foi percorrido até a fase 7. Fases 0 a 4 e a 6 estão feitas; a 5 e a 7, em parte
(o que ficou de fora está na seção 5). **Tudo em código, SEM COMMIT: são 168 arquivos.** O que está abaixo é o que
ainda precisa de alguém — na maior parte, do Ruben, porque depende do painel do
Railway, de produção ou de decisão de produto.

> **Para subir tudo isto para produção, siga `docs/subir-para-producao.md`** — tem a
> ordem obrigatória (backup → migrations → código), a verificação pós-deploy e o plano
> de reversão. Este arquivo é o inventário; aquele é o roteiro.

## 1. Painel e máquina local (sem código)

- [ ] **Mover e criptografar os cinco dumps de `backups/`** (58 MB, banco real, sem
      criptografia, na área de trabalho). Apagar os dois `pre-*`. Item 7 do ranking.
- [ ] **Trocar `NOTICIAS_URL`** no Railway para `https://news-m360.up.railway.app`.
      **Confirmado em 2026-09-22 que ainda não foi feito**: o digest chega com
      `localhost:5176` em todos os links. Sem esta env, o padrão do `config.py`
      é o localhost — vale para produção também, não só para disparo local.
- [ ] **Conferir `FRONTEND_URL`** no Railway (`https://www.medico360.app`). É a
      env do link do CONVITE, diferente da de cima. No `.env` local ela aponta
      para a porta 5174, que é a das calculadoras, não a do chat.
      Hoje aponta para a API, e todo link do digest diário por e-mail dá 404.
- [ ] **Rotacionar a `PHOENIX_API_KEY`** no Arize (foi colada em texto puro numa conversa).
- [ ] **Exportar os preços dos modelos de produção** para `scripts/dados/model_pricing.json`.
      O arquivo está VAZIO: nenhum preço existe no repositório, a verdade mora só no
      banco. O `SELECT json_agg(...)` pronto está no docstring de `scripts/seed_models.py`
      — rodar, colar o resultado no arquivo, e tirar os modelos da lista
      `PRECO_PENDENTE_DE_EXPORTACAO` em `tests/test_seed_models.py`.
- [ ] Definir **`RAILWAY_DEPLOYMENT_DRAINING_SECONDS=90`** no serviço do backend. Sem isso
      o `--timeout-graceful-shutdown` novo não adianta: o Railway mata o processo antes
      e todo deploy continua cortando as respostas em andamento.
- [ ] Rodar `SHOW max_connections;` e `SELECT count(*) FROM pg_stat_activity;` no banco
      de produção. Alimenta a fase 4.
- [ ] **Confirmar que existe Redis em produção** (`REDIS_URL` no painel). O rate limit
      passou a contar no Redis; sem ele cai para memória e o limite volta a valer por
      processo — o que impede subir workers na fase 4.
- [ ] Depois que o código da fase 2 subir, `dea-m360` e `news-m360` podem **sair** de
      `EMBED_ALLOWED_ORIGINS`, se estiverem lá só para contornar o 403.

## 2. Para subir o que já está pronto

- [ ] **Revisar e commitar — é o item mais urgente desta lista.** Fases 1 a 7 estão na
      árvore de trabalho: 168 arquivos. Sugestão: um commit por fase, na ordem, para a
      revisão caber na cabeça e um eventual `revert` ser cirúrgico. O resumo de cada fase
      está na memória do projeto (`medico360-fase-N-andamento`).
- [ ] `git rm --cached .claude/settings.local.json` (já está no `.gitignore`).
- [ ] **Aplicar as migrations `013_consent_anonimizavel`, `014_token_version` e
      `015_otp_code_hmac`** JUNTO com o deploy. Sem a 015 **ninguém entra por código de
      e-mail**: o HMAC de 64 caracteres não cabe na coluna antiga de 6. Ela também
      invalida os códigos pendentes (quem estava no meio do login pede outro). Sem a 013 a exclusão de conta continua falhando (grava `NULL` em coluna
      ainda `NOT NULL`). Sem a 014 **ninguém entra**: todo login lê `users.token_version`.
- [ ] Conferir o primeiro run do CI: o job novo `landing-pages` e o portão de cobertura
      em 75 nunca rodaram no GitHub.

## 3. Homologação na tela (não tem teste que substitua)

- [ ] **Embed**: abrir chat, calculadoras, notícias e uma página de captação DENTRO da
      área de membros. O cabeçalho `frame-ancestors` é novo; origem errada = app em
      branco. O console mostra `Refused to frame` com a origem que faltou.
- [ ] **Deploy com aba aberta**: os Dockerfiles perderam o `-s` do `serve`. Conferir que
      rota profunda (ex.: `/conversa/123`) ainda abre ao recarregar.
- [ ] **DEA**: cadastrar um aparelho pelo navegador (era 403); ver o rótulo "remoção
      relatada"; abrir em ambiente interno e ver o aviso de localização.
- [ ] **Chat**: (a) mandar a próxima pergunta enquanto "verificando referências" e ver
      que a anterior fica; (b) apertar Enter com anexo processando; (c) a mensagem de
      limite semanal com um usuário beta estourado.
- [ ] **Exclusão de conta** com uma conta de teste real em produção: esperar 204.
- [ ] **Sair**: clicar em Sair e, na mesma aba, abrir `/api/v1/auth/me` — tem de dar 401.
      Conferir que as outras abas e o celular do mesmo médico também caem (é o esperado).
- [ ] **Sessão de 24h**: quem entra por código de e-mail vai digitar código uma vez por
      dia. Se incomodar, é a variável `SESSION_MAX_AGE_HOURS`, sem deploy de código.
- [ ] **Perfil**: o e-mail aparece como somente leitura.
- [ ] **Farmácia pelo stream**: perguntar uma bula, um receituário e uma interação no chat.
      A resposta chega de uma vez (é um evento só), com o chip do modo certo.
- [ ] **Resposta longa em rede de hospital**: o stream agora manda `: ping` a cada 15 s;
      conferir que respostas de raciocínio clínico não são mais cortadas no meio.
- [ ] **Pergunta abortada**: mandar outra pergunta no meio de uma resposta e reabrir a
      conversa. A pergunta interrompida agora APARECE, sem resposta (antes sumia).

### Fase 5 — quase tudo aqui só se confirma na tela

Nada da fase 5 foi visto num navegador; os testes rodam em jsdom.

- [ ] **Chat, durante a resposta**: o campo aceita digitação; o botão é "Parar"; Parar
      mantém na tela o texto parcial; o texto não engasga no fim de resposta longa.
- [ ] **Rolagem**: ao enviar, a pergunta sobe para o topo e a resposta preenche a tela
      sem rolar à mão. Ao trocar de conversa, abre no fim. Conferir que NÃO sobra um vão
      em branco no fim da conversa.
- [ ] **Trocar de conversa rápido**: clicar em duas em sequência mostra a do último clique.
- [ ] **Mais de 50 conversas**: as antigas aparecem na lista e dentro das pastas.
- [ ] **Celular (iPhone de verdade)**: o campo não fica sob a barra do navegador; focar o
      campo não dá zoom; o menu "⋮" da conversa aparece e move para pasta.
- [ ] **Metrônomo**: ligar o metrônomo, receber ou fazer uma ligação → aparece "O som foi
      interrompido" com "Retomar som". Pulso visual junto do clique. Trocar de aba por
      10 s e voltar: sem rajada de cliques.
- [ ] **Notícias no app da Waid**: abrir duas vezes seguidas NÃO pede código de novo
      (mudança SEM teste automatizado — o app não tem suíte).
- [ ] **Página de contabilidade**: a imagem de topo (agora 72 KB) está com boa aparência.

### Fase 7

- [ ] **Acompanhar o log `orquestrador_query_obsoleto`** por uma ou duas semanas. Sem
      ocorrência, a rota `/orquestrador/query` pode sair (com o `OrquestradorService.query`,
      o ramo `unsupported_mode` do chat e os testes de paridade). Com ocorrência, o log
      diz quem chama: `user_id`, `origem`, `user_agent`.

### Fase 6

- [ ] **Notícias**: abrir alguns artigos e conferir que o corpo continua bem formatado
      (negrito, listas). O HTML agora passa por uma lista de permissão no servidor e no
      navegador; link dentro do corpo do artigo deixa de existir, por desenho.
- [ ] **DEA e páginas de captação**: continuam funcionando normalmente. Deixaram de
      receber credenciais de CORS; como nunca mandaram cookie, nada deve mudar.
- [ ] **Login por código**: pedir e digitar um código em produção depois do deploy.

## 4. Decisões de produto em aberto

- [ ] **Formulários das páginas de captação na exclusão de conta**: nome, e-mail,
      telefone e faturamento hoje SOBREVIVEM à exclusão, só sem o vínculo. Decidir se o
      pedido de eliminação alcança o lead já entregue ao parceiro.
- [ ] Rota `/orquestrador/query`: aposentar ou manter como coletor (fase 7; falta saber
      se há chamador além do frontend).
- [ ] Agregador: as duas rotas sem chamador saem?
- [ ] Telas para os direitos do titular (exportação, consentimentos, revogação existem
      só na API).
- [ ] Ensaio de carga antes de qualquer campanha de crescimento. A fase 4 removeu os
      tetos conhecidos, mas NADA foi medido sob carga — nem o teto novo.
- [x] **Subir workers — FEITO em 2026-09-21.** `--workers ${WEB_CONCURRENCY:-2}` no
      Dockerfile; os agendadores passaram a subir só no processo líder
      (`app/core/lider.py`). Sobe para 2 workers no próximo deploy, sem env nova.
      **Corrigido em 2026-09-24 (item 59):** a eleição decidia só no boot e todo
      deploy deixava o backend sem agendadores. Agora é disputada a cada 60 s.
      Até este código subir, Restart (não Redeploy) do backend depois de cada deploy.
- [ ] **Homologar o item 60 no celular** (passo 3 do roteiro em `docs/pitacos-do-fable-2.md`):
      Sair no computador ou nas calculadoras, abrir o chat no celular em menos de 60 min e
      mandar uma pergunta. Esperado: tela de espera por um instante, o chat volta na mesma
      conversa e a pergunta volta para o campo, sem código por e-mail. Corrigido em
      2026-09-24: todo 401 do chat leva a `sessaoExpirou` (`frontend-app/src/lib/auth.ts`).
- [ ] **Homologar o item 59 em produção:** dois deploys seguidos SEM Restart, e nos
      dois o log mostra "Agendador 'agendadores': este processo é o líder" em até
      ~2 min depois que o container antigo sai.
- [ ] **Depois de um dia com 2 workers**, decidir se vai para 4: rodar
      `python -m scripts.medir_conexoes_presas --minutos 30` num horário de movimento e
      conferir `pg_stat_activity`. Com 4 são ~164 conexões de um teto de 500.
- [ ] **Cadência do PubMed é POR PROCESSO** (8/s com chave): com N workers o total vira
      N×8/s contra a NCBI, que aceita 10/s por IP. Com 2 workers já passa do teto se os
      dois coletarem ao mesmo tempo. Dividir `_Cadencia` por `WEB_CONCURRENCY`, ou mover
      a cadência para o Redis.
- [ ] Perguntar à Waid: outro iframe no mesmo LMS consegue pedir um token e reusá-lo?

## 5. Dívidas técnicas registradas, não resolvidas

- **Refactors grandes da fase 7, adiados de propósito** para depois do commit: dividir
  `ai_providers.py` (1200 linhas; os testes patcham o módulo pelo caminho, então dividir
  exige reescrever esses patches), app único para as três páginas de captação, código
  compartilhado entre apps, juntar auxiliares de teste repetidos no `conftest.py`.
- **`/agregador/stream` segura a conexão de banco o stream inteiro** — o mesmo defeito
  que a fase 4 corrigiu no orquestrador. O agregador está oculto na interface; corrigir
  antes de reexibir.
- Na máquina do Ruben: um dos dois ambientes virtuais (~430 MB cada) e a pasta
  `medico-360/` (28 MB de protótipo) podem sair da pasta do projeto.

- **`alembic check` fora do CI.** Hoje ele acusa 54 KB de falsos positivos: o
  `alembic/env.py` não passa `include_schemas`, então toda tabela de `news`,
  `landing_pages`, `calculators` e `dea` aparece como "tabela nova". Arrumar o `env.py`
  primeiro; só então dá para ver se existe deriva real entre modelos e migrations.
- **Leads sem e-mail fora do iframe (item 15).** Os formulários das três páginas não
  têm campo de e-mail: sem a identidade da Waid o lead chega sem contato. É mudança de
  tela em três arquivos idênticos sem teste.
- **Origem do LMS parceiro continua com credenciais de CORS.** Falta confirmar com a
  Curseduca se a página deles chama a nossa API diretamente; se não chama, sai da lista.
- `GET /landing-pages/{slug}/check` ainda revela se um e-mail já se cadastrou (baixa
  sensibilidade, com rate limit). Remover exige mexer nos três formulários.
- Aviso de privacidade e link da política ao lado dos formulários de captação: falta o
  texto jurídico.
- Item 17 (`/orquestrador/query` descarta citações) não foi feito: a rota sai na fase 7.

- **Formulário das páginas de captação some por até 30 s** quando a Waid não responde
  (`TIMEOUT_MS` de `shared/embed/identidade.ts`). Correção sugerida: em `lead.ts`, um
  `setTimeout` de ~4 s que libera o formulário pedindo o e-mail, e pré-preenche se a
  identidade chegar depois. Não apliquei: três arquivos idênticos, sem teste.
- **DEA offline (PWA)** não foi feito: um service worker não dá para testar aqui, e um
  com defeito fica preso no aparelho de quem instalou.
- Cache de conversa ao alternar (item 36), painel lateral que recolhe (44), divisão do
  pacote do chat e fontes (45) e acessibilidade (46) não foram feitos.
- O noticias-app e o calculadoras-app não têm testes unitários; o noticias-app nem tem
  vitest instalado (lockfile precisa nascer em Linux).

- Não pus `--limit-concurrency` no uvicorn: sem medição, um valor errado vira 503 para
  usuário legítimo. Decidir depois do ensaio de carga.
- O `/orquestrador/query` (sem streaming) ainda espera o modelo DENTRO da transação. É o
  motivo de o `idle_in_transaction_session_timeout` ser folgado (3 min). Some com o
  `/query` na fase 7.
- O ramo `unsupported_mode` do frontend ficou, inerte. Sai na fase 7.
- Não fiz o seed único de calculadoras (o CI roda 2 dos 6 seeds).

- Identidade divergente no embed agora dá 403. O caso LEGÍTIMO (o LMS re-provisionou o
  aluno com uuid novo) trava o médico até o suporte corrigir `users.waid_uuid` por SQL;
  o alarme `embed_identidade_divergente` avisa quando acontecer.
- O logout derruba TODAS as sessões do médico, não só a do navegador: o JWT não tem
  identificador por sessão.

- A régua do "não encontrado" do DEA é um contador (`verificacoes_negativas >= 2`), não
  origens distintas: duas contestações da mesma máquina contam.
- O `ip_hash` do DEA rotaciona a cada 24h por desenho; a mesma pessoa em dois dias conta
  como duas origens na remoção.
- O dea-app não tem teste de renderização (só lógica pura). Instalar jsdom exige gerar o
  lockfile em Linux.
- Redução de imagem no cliente (~2000 px) antes do upload não foi feita.
- O `serve` aplica o cache `immutable` também ao 404 de `/assets`; um 404 durante a
  troca de deploy pode ficar em cache no navegador.
- As três páginas de captação têm supressões de lint justificadas e nenhum teste.

## Fases restantes

| Fase | Tema | Estado |
| --- | --- | --- |
| 3 | Conta e sessão (itens 4, 6, 21, 50) | feita em código |
| 4 | Capacidade e continuidade | feita em código |
| 5 | Experiência percebida | feita em parte (ver dívidas) |
| 6 | Endurecimento e invariantes | feita (ver dívidas) |
| 7 | Limpeza estrutural | feita em parte (ganhos rápidos, agregador, docs) |

## Rodada de UX para o lançamento (2026-09-21)

Seis itens levantados pelo Ruben olhando a plataforma antes do lançamento.

| # | Item | Estado |
| --- | --- | --- |
| 1 | Template do e-mail de OTP | feito |
| 2 | E-mail de notícias | feito |
| 3 | Periodicidade do digest (diário, semanal, horário) | feito |
| 4 | Header das calculadoras: tirar "Sair" no embed | feito |
| 5 | Termos de uso desatualizados | link e versão corrigidos; o texto depende de jurídico |
| 6 | Menu do usuário duplicado ao editar perfil | feito |

Os e-mails passaram a sair em HTML com a identidade da marca (`app/services/
email_templates.py`); antes os três eram texto puro. O `send_invite` entrou junto,
embora não estivesse na lista — era o mesmo texto puro dos outros dois.

### Periodicidade do digest (item 3)

O médico escolhe na tela de temas: **frequência** (todo dia / uma vez por
semana), **dia** (só no semanal) e **horário** (manhã 7h, tarde 13h, noite 19h).

Decisões que estão travadas em código e comentário:

- **Faixa, e não hora exata.** Hora exata obriga a responder "sete da manhã de
  ONDE", e o sistema não guarda fuso de usuário nenhum — nem no banco nem vindo
  do navegador. A faixa resolve em hora fixa de Brasília. Se um dia houver
  médico fora do Brasil em número que importe, guardar o fuso junto da
  preferência e converter em `news_digest_agenda.esta_na_hora` é o único ponto
  que muda.
- **O filtro de hora saiu do agendador e virou por usuário.** `news_agendado`
  chama `enviar_digests` TODA HORA; quem decide se é a hora de cada médico é a
  agenda dele. Por isso `NEWS_DIGEST_HOUR` e `NEWS_DIGEST_JANELA_DIAS` foram
  REMOVIDAS do `config.py`: um ajuste global ali não faria mais nada e ficaria
  parecendo que faz. (Se as envs continuarem definidas no Railway não há
  problema — o pydantic ignora env desconhecida; verificado.)
- **A janela acompanha a frequência**: 2 dias no diário, 7 no semanal. Sem isso
  quem escolhesse semanal receberia só os últimos dois dias.
- **Campo ausente = não mexa**: um PUT só com `email` (o botão de desligar)
  NÃO apaga a agenda. Senão quem religasse depois passaria a receber noutro
  horário sem ter pedido. Travado por teste.
- Preferência sem agenda = diário de manhã, que é o comportamento de antes.
  Ninguém muda de horário por efeito colateral de deploy.
- `resumo["fora_de_hora"]` entrou no heartbeat: numa rodada qualquer esse é o
  número grande, e é o que distingue "não era a hora de ninguém" de "a tarefa
  morreu".

Testes: `tests/test_news_digest_agenda.py` (26, a agenda pura — percorre a
semana hora a hora) e `tests/test_news_digest_periodicidade.py` (11, com banco e
HTTP). Os de digest foram rodados com o relógio deslocado em +100, +365 e -200
dias para provar que não dependem da data em que rodam.

### Dívidas que esta rodada deixou

- **A marca pede Just Sans e a plataforma não carrega nenhuma.** Três tipografias
  diferentes rodando: `frontend-app`/`calculadoras-app`/`dea-app` usam Plus Jakarta
  Sans; `noticias-app` pede `'Just Sans'` que NUNCA é carregada (cai no system-ui,
  muda de máquina para máquina); `lp-contabilidade`/`lp-financas` usam Hanken
  Grotesk. Não há arquivo de fonte no repositório. Unificar exige licenciar e
  hospedar a Just Sans e apontar os seis apps. Nos e-mails o ponto é irrelevante
  (cliente de e-mail ignora webfont), mas no produto é a marca não batendo consigo.
- **O logo dos e-mails é só texto, de propósito.** O "M" foi redesenhado em SVG a
  partir do PDF do manual, virou data URI, e Gmail/Outlook bloquearam: chegava um
  quadradinho vazio. Se aparecer o SVG/AI original da marca, dá para hospedar e usar
  nos apps — no e-mail, imagem continua não valendo a pena.
- Nenhum e-mail foi conferido no Outlook desktop (o motor do Word é o mais restrito);
  só Gmail. O HTML segue as regras que o Outlook exige (tabelas, estilo inline).

### O NER do DLP falha ABERTO — vale uma decisão

Descoberto em 2026-09-21 ao investigar 13 testes de DLP vermelhos na máquina
local. Não era regressão: faltava o modelo `pt_core_news_sm` (confirmado contra
o HEAD numa worktree limpa — as mesmas 13 falhavam sem alteração nenhuma).
Resolvido com `python -m spacy download pt_core_news_sm`; os 60 passam. O
`Dockerfile` e o CI instalam o modelo, então nem produção nem CI eram afetados.

O que a investigação deixou à mostra, e que vale uma decisão:

- **O NER falha ABERTO, de propósito.** `app/middleware/ner.py::_load` registra
  `logger.error` e devolve `None`; o DLP segue com as palavras-gatilho e o
  `main.py` loga um warning no startup. Ou seja: se o modelo sumir de produção
  (mudança no Dockerfile, imagem base, falha de download no build), **nomes sem
  palavra-gatilho passam para os modelos** e a única evidência é uma linha de
  log que ninguém lê.
- O `/health/ready` NÃO verifica o NER. Um readiness que olhasse
  `ner.warmup()` transformaria essa falha silenciosa em deploy que não sobe —
  mas também impediria a aplicação de subir num ambiente sem o modelo, o que
  é uma decisão de produto (fail-closed x disponibilidade), não minha.
- A suíte passa com 13 vermelhos em qualquer máquina sem o modelo. Isso treina
  a equipe a ignorar vermelho, que é o começo de não perceber o vermelho de
  verdade. Um `skipif` quando o modelo não está presente resolveria — mas aí a
  cobertura do DLP some sem avisar, o que é pior. A saída boa é o CI garantir o
  modelo (ver `medico360-ci`) e o teste falhar mesmo.

## Termos de uso: o item 5 era três problemas (2026-09-22)

O pedido era "ver onde estão os termos de uso desatualizados". Eles não estão
desatualizados — **são de outro produto**, e o aceite não levava a lugar nenhum.

### 1. O link do aceite não abria nada — CORRIGIDO

O checkbox "Li e aceito" apontava para `/termos` e `/privacidade`, caminhos que
**não existem em nenhum dos três apps**. Cada roteador termina em
`<Route path="*" element={<Navigate to="/" replace />} />`, então clicar não dava
nem 404: jogava o médico de volta na home. Ele aceitava sem ter como ler.

Havia um `frontend-app/src/lib/documentos.ts` com as URLs corretas e um commit
chamado "liga os documentos legais reais ao aceite do onboarding" — mas **o
arquivo nunca foi importado por ninguém**. Nada acusou, porque link quebrado não
quebra build nem type-check.

Corrigido: o arquivo foi para `shared/onboarding/documentos.ts` (é lá que o
`OnboardingGate` compartilhado vive) e o checkbox agora usa as URLs reais.
Travado por `frontend-app/src/components/OnboardingGate.documentos.test.tsx` —
6 testes, verificados contra o defeito original.

### 2. A versão do consentimento mentia sobre a política de cookies — CORRIGIDO

`VERSAO_DOCUMENTOS` era uma constante única, `2024-08-05`. Mas a **Política de
Cookies é de 2024-07-26** (conferido no documento publicado). Quem aceitava
ficava registrado como tendo aceitado uma versão de cookies que nunca existiu.

Agora a data é declarada **por documento** nos dois lados, e a versão do
conjunto é a mais recente entre as três (avança quando qualquer uma é revisada).
`tests/test_consentimento.py` compara documento a documento — a comparação só da
versão do conjunto era justamente o que deixava a de cookies passar.

### 3. Os documentos são do PACIENTE 360 — DEPENDE DE JURÍDICO

Este é o grande, e não se resolve em código.

Os três documentos que o médico aceita falam de **Paciente 360®**. A expressão
"Médico 360" não aparece em nenhum dos três.

Pior, a Política de Privacidade afirma:

> "A Active **não compartilha com terceiros** os Dados Pessoais fornecidos pelo
> Usuário através do acesso à Plataforma"

e lista **um** operador (AWS Brasil). Enquanto isso a plataforma envia texto
clínico para **cinco provedores de LLM** (Anthropic, OpenAI, Google, Perplexity,
Maritaca), além de Sentry, Intercom, Arize Phoenix, SendGrid e Railway. Sobre
IA, os documentos não dizem uma palavra.

É dado de saúde (LGPD art. 11, sensível) indo para subprocessadores que a
política afirma não existirem. O DLP mascara PII antes de enviar — mitigação
real — mas mitigação não substitui declaração.

**Decisão do Ruben (2026-09-22):** rascunhar os três documentos para revisão
jurídica, e **não travar o lançamento** por isso. Feito:

- `docs/inventario-tratamento-de-dados.md` — o que o sistema faz, com
  `arquivo:linha` em cada afirmação;
- `docs/juridico/RASCUNHO-politica-de-privacidade.md`
- `docs/juridico/RASCUNHO-termos-de-uso.md`
- `docs/juridico/RASCUNHO-politica-de-cookies.md`

Os rascunhos marcam com **[DECISÃO]** tudo que é escolha de negócio ou de
direito, e trazem um checklist no fim. **Nenhum deles está pronto para
publicar** — são insumo para quem for redigir.

Enquanto o texto certo não existe, os links do P360 foram colocados em TODOS os
lugares que coletam dado e não tinham nada (decisão do Ruben: "independente de
estar certo"), para que o titular ao menos tenha o que ler:

| Onde | Antes | Agora |
| --- | --- | --- |
| Onboarding (4 apps) | link para rota inexistente | URL real |
| Cadastro (`RegisterPage`) | nada | termos + privacidade |
| LP contabilidade | nada | privacidade |
| LP finanças | nada | privacidade |
| LP parceiros | nada | privacidade |
| Rodapé dos 3 e-mails | nada | termos + privacidade |

As URLs nos e-mails são uma segunda cópia (Python não importa TypeScript);
`tests/test_email_templates.py` compara as duas e quebra se divergirem.

Datas conferidas nos documentos publicados em 2026-09-22:
| Documento | Revisão publicada |
| --- | --- |
| Política de Privacidade | 2024-08-05 |
| Termos de Uso | 2024-08-05 |
| Política de Cookies | 2024-07-26 |


## Links dos e-mails (2026-09-22)

O digest chegava com `localhost` em todos os links. **Duas causas**, e só uma
era ambiente:

1. **`NOTICIAS_URL` não definida** no Railway — cai no default `localhost:5176`
   do `config.py`. É pendência do Ruben, acima. Cada e-mail usa uma env
   diferente: convite → `FRONTEND_URL`; digest → `NOTICIAS_URL`; OTP → nenhuma
   (não tem link).

2. **As rotas do digest não existiam.** O `noticias-app` navegava só por estado
   interno (`fase: 'feed' | 'temas'`), sem roteador nenhum — então
   `/artigo/153` e `/preferencias` carregavam o feed genérico. O médico clicava
   num destaque e tinha de procurar de novo o que acabara de escolher ler; e
   `/preferencias` é o link de **descadastro**, que é o que mais custa caro se
   não funcionar.

   Corrigido com `react-router-dom` (mesma versão do `frontend-app` e do
   `calculadoras-app`, para não haver uma terceira forma de navegar no
   monorepo). O `serve.json` já reescrevia qualquer caminho fora de `/assets`
   para o index, então o servidor não precisou mudar.

**Desenho das rotas:** a autenticação e o onboarding ficam FORA e ANTES do
roteador. A URL escolhe entre feed, artigo e temas — não dá acesso. Se
`/artigo/:id` fosse alcançável por qualquer um, o link do e-mail entraria no
conteúdo sem passar pela sessão.

`/artigo/:id` abre o feed com o modal daquele destaque; qual modal está aberto é
**derivado da URL no render**, não copiado para o estado — duas fontes para a
mesma verdade divergem, e o oxlint reclama de `setState` em efeito com razão.

Travado por `tests/test_links_dos_emails.py` (7 testes), que varre os links
REAIS gerados pelo template e confere cada caminho contra as rotas lidas do
`App.tsx`. Um link novo no e-mail entra na verificação sozinho. Verificado
contra os três defeitos: sem `/artigo/:id`, sem `/preferencias`, e com base
fixa em localhost.

**Por que o teste é no backend:** o `noticias-app` não tem harness de teste, e
instalar jsdom aqui exige gerar o lockfile em Linux (mesma restrição do
dea-app). Testar pelo lado que GERA o link é melhor de qualquer forma — é onde
o `localhost` nasceu.

### O link abre FORA do iframe — e era isso que faltava

Levantado pelo Ruben: o app é embedado, mas o clique num link de e-mail abre o
navegador **sem iframe**. Sem `window.parent` o handshake com a Waid é
impossível (`sem_iframe`), e o médico passa pelo login por código.

Com o roteador sozinho, o destino ainda se perdia: depois do código, o app
chamava `carregarConteudo()`, que decidia entre feed e temas **ignorando a
URL**. O `/artigo/153` sobrevivia na barra de endereços e não servia para nada.

Corrigido com `temEntradaDireta()` em `noticias-app/src/App.tsx`, consultada nos
DOIS caminhos de entrada: o login por código e o reaproveitamento de sessão.
Quem veio por link de destaque vai para o destaque, mesmo sendo a primeira
visita — a escolha de temas continua acessível pelo feed e volta a aparecer
sozinha na próxima visita sem link.

Ela lê `window.location` em vez do roteador de propósito: roda no fluxo de
autenticação, que vive FORA das rotas. Usar `useLocation` exigiria mover o
handshake para dentro do roteador, e aí `/artigo/:id` viraria rota alcançável
sem sessão.

**Bug achado de passagem:** `noticias-app/src/lib/auth.ts::logout` mandava para
`/login`, rota que não existe neste app (a tela de código é uma FASE, não uma
rota). Caía no catch-all e trazia o médico de volta ao feed, deslogado. Agora
vai para a raiz.

### Caminho pela Waid: descartado por ora

Considerado fazer o link apontar para o LMS, que embedaria o app já no artigo —
o médico não digitaria código nenhum. **Descartado**, e vale registrar o porquê:

1. depende de a Waid aceitar repassar um parâmetro de destino ao iframe —
   conversa com outro time, prazo fora do nosso controle;
2. **não resolveria o pior caso.** Nos aplicativos da Waid a seção abre em
   webview direto, sem iframe (já documentado em `ARQUITETURA_TECNICA.md`), e
   ali o handshake é impossível de qualquer jeito. Quem clica num digest pelo
   celular está, provavelmente, no app;
3. a URL da seção de notícias no LMS não está registrada em lugar nenhum.

Se um dia for retomado, o caminho é uma env nova (`NOTICIAS_EMBED_URL`) com o
link direto como padrão.

## Ordem do feed de notícias (2026-09-22)

Feedback do chefe da empresa, olhando a tela: *"vamos deixar essas notícias em
ordem cronológica"*. A lista saía assim: **18 SET · 03 SET · 01 SET · 01 SET ·
08 SET · 06 SET**.

**Causa:** o feed ordenava por SCORE (relevância do tema), com a data só como
desempate — `order_by(max(score).desc(), visible_at.desc())`. Funcionava como
curadoria, mas cada linha da tela mostra o dia e o mês: ela promete cronologia
na forma e entregava relevância no conteúdo. Lista datada fora de ordem parece
defeito, mesmo quando a ordem tem lógica.

**Decisão do Ruben:** cronológica na lista, **capa por relevância**. Mantém a
queixa resolvida sem jogar fora o que diferencia o módulo de um leitor de RSS.

### O risco escondido, que era o trabalho de verdade

A capa (`heroItem`) era escolhida como `candidatos[0]` — o primeiro da lista.
Isso só significava "o mais relevante" PORQUE o backend ordenava por score. Com
a ordem cronológica, `[0]` viraria **"o mais recente" em silêncio**, e a
curadoria sumiria da tela sem ninguém notar.

Por isso a mudança tem duas partes:
- `_em_ordem_cronologica` ordena a lista final (não dá para ordenar no SQL: o
  feed é montado de três blocos concatenados — temas, palavras-chave,
  preenchimento — e ordenar cada consulta ordenaria os blocos, que era
  exatamente o defeito);
- o **`score` passou a sair no schema** e a capa escolhe pelo maior,
  explicitamente. A preferência pelo journal do dia continua vindo antes (é a
  lógica editorial da revista) e o score desempata entre os do dia.

`score` é opcional no tipo do frontend por causa da janela de deploy: backend
antigo não manda o campo, todos ficam em 0 e a capa cai no primeiro item — o
mais recente. Degradação aceitável e temporária; melhor que ficar sem capa.

Travado por `tests/test_news_feed_ordem.py` (7 testes), verificados contra os
dois defeitos: ordem antiga de volta, e `score` fora da resposta.

**Um teste meu estava afirmando o que o SQL já impedia:** escrevi um caso de
`visible_at` nulo passando pelo feed, mas a consulta filtra `visible_at >=
desde` e o nulo nunca chega lá. Reescrito para testar a função diretamente — a
defesa contra nulo continua valendo, porque a função é genérica.
