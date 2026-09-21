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
- [ ] Subir workers (a máquina tem 8 vCPU e a API usa uma). Pré-requisitos: Redis em
      produção confirmado (rate limit), cadência do PubMed dividida pelo número de
      workers, e o digest de notícias com transação por usuário (fase 6).
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
