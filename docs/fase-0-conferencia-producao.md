# Fase 0 — Conferência de produção

Checklist para preencher no painel do Railway e no navegador. Data: 2026-09-21.

Cada item tem **onde olhar**, **o que anotar** e **como ler o resultado**. Escreva a
resposta na linha "Resposta:" — é o aceite da fase 0 no plano
(`docs/pitacos-do-fable.md`, itens 7, 9, 10, 20, 21).

Tempo estimado: 30 a 40 minutos. Nada aqui altera produção, exceto o item 6, que é
mover arquivo no seu notebook.

---

## 1. Origens confiáveis — decide se os itens 9 e 10 estão ativos

**Onde:** Railway → serviço do backend → aba *Variables*.

**Anotar o valor literal destas duas:**

- `EMBED_ALLOWED_ORIGINS` → **Resposta (2026-09-21):**
  `["http://localhost:5173","https://adminportalmedico360.curseduca.pro","https://frontend-medico-360-production.up.railway.app","https://news-m360.up.railway.app"]`
- `LANDING_PAGES_ORIGINS` → **Resposta (2026-09-21):**
  `https://lp-investimentos-m360.up.railway.app,https://lp-contabilidade-m360.up.railway.app,https://lp-parceiros-m360.up.railway.app`

**Como ler.** A lista de origens confiáveis é montada em `origens_confiaveis()`
(`app/core/config.py:340`) e é só isto:

```
frontend_url + calculadoras_url + EMBED_ALLOWED_ORIGINS + LANDING_PAGES_ORIGINS
```

`dea_url` está fora **de propósito** (tem docstring explicando), e `noticias_url`
nunca foi incluída. Então:

| Situação | Significado |
| --- | --- |
| A URL do dea-app **não** aparece em nenhuma das duas | **Item 9 ativo.** Cadastro de DEA pelo navegador dá 403 |
| A URL do noticias-app **não** aparece em nenhuma das duas | **Item 10 ativo.** Salvar tema de notícia dá 403 |
| Aparecem | Defeito mascarado pela env. Corrigir mesmo assim, mas sem pressa |

**Anotar também**, na mesma aba, para saber quais URLs procurar acima:

- `FRONTEND_URL` → **Resposta:** `https://frontend-medico-360-production.up.railway.app`
- `CALCULADORAS_URL` → **Resposta:** `https://calculadoras-medico-360.up.railway.app`
- `DEA_URL` → **Resposta:** `https://dea-m360.up.railway.app`
- `NOTICIAS_URL` → **Resposta:** `https://medico360-ia.up.railway.app` ← **errado, ver abaixo**

### Leitura do item 1

**Item 9 (DEA): ATIVO.** `https://dea-m360.up.railway.app` não está em nenhuma das
duas listas. Confirmado pelo 403 do item 2.

**Item 10 (notícias): MASCARADO, por acidente.** `https://news-m360.up.railway.app`
está em `EMBED_ALLOWED_ORIGINS`, então a guarda deixa passar — foi o 201 do item 3.
O defeito de código continua lá (`noticias_url` nunca entra em
`origens_confiaveis()`), mas ninguém sente hoje. Corrigir sem pressa.

**Achado novo, fora do relatório: `NOTICIAS_URL` aponta para a API.**
O valor é `https://medico360-ia.up.railway.app`, que é o backend. O app de notícias é
`https://news-m360.up.railway.app`. Essa variável **não** participa da guarda de
origem — ela é usada só para montar os links do digest por e-mail
(`app/services/email_service.py:73`). Consequência: **todo link do e-mail diário de
notícias está quebrado**, porque `{base}/artigo/{id}`, `{base}/preferencias` e o "Ver
tudo" apontam para a API e devolvem 404.

Gravidade alta em experiência (o e-mail é o canal do módulo de notícias), esforço
mínimo: trocar a variável no painel para `https://news-m360.up.railway.app`. Não
precisa de deploy nem de código. **Vale conferir antes se algum médico já recebeu o
digest com link quebrado** — se sim, o próximo e-mail já sai correto.

---

## 2. Cadastrar um DEA pelo navegador — a prova do item 9

**Onde:** abrir a URL do dea-app (o valor de `DEA_URL` anotado acima) no navegador,
com o console aberto (F12 → aba *Console*, e aba *Network*).

**Fazer:** tentar cadastrar um aparelho qualquer. Pode ser um endereço de teste; se
cadastrar, apague depois ou me avise para incluir a limpeza na fase 2.

**Anotar:**

- Status da requisição `POST /api/v1/dea/locais` na aba Network → **Resposta (2026-09-21): 403.**
- Se deu erro, o corpo da resposta → Resposta: (não anotado; o 403 já basta)

**ITEM 9 CONFIRMADO ATIVO EM PRODUÇÃO.** O app público de DEA não consegue receber
cadastro de ninguém pelo navegador. Entra na fase 2 como previsto.

**Como ler.** `403` com `{"detail":"Origem não autorizada."}` confirma o item 9 em
produção. `200`/`201` significa que a env do item 1 já mascara o defeito.

---

## 3. Salvar um tema de notícia — a prova do item 10

**Onde:** URL do noticias-app, logado, console aberto.

**Fazer:** marcar ou desmarcar um tema / palavra-chave e salvar.

**Anotar:**

- Status de `POST /api/v1/news/me/keywords` → **Resposta (2026-09-21): 201 Created**, testado pelo app embedado.

**Como ler.** Mesma leitura do item 2.

**ITEM 10 MASCARADO.** Passou porque `news-m360.up.railway.app` está em
`EMBED_ALLOWED_ORIGINS` — não porque o código esteja certo. Ver a leitura do item 1.

**Ressalva:** o teste foi feito com o app embedado. Vale repetir abrindo
`https://news-m360.up.railway.app` direto no navegador, fora do iframe, porque é daí
que sai o `Origin` que a guarda examina. O resultado deve ser o mesmo (a origem está
na lista), mas é a prova limpa.

---

## 4. Phoenix — decide se o item 20 está ativo

**Onde:** Railway → *Variables*.

- `PHOENIX_API_KEY` está definida e não-vazia? → **Resposta (2026-09-21): sim**, JWT válido.

> **A chave foi colada em texto puro na conversa de 2026-09-21.** Rotacionar no
> Arize quando der. Não é emergência — dá acesso à telemetria, não ao banco nem aos
> dados clínicos — mas é credencial de produção exposta em histórico. Para este
> checklist bastava "sim, está definida".

**ITEM 20 CONFIRMADO ATIVO.** Com a chave presente, `setup_phoenix` registra o
tracer e cada resposta exporta 2 spans de forma síncrona no event loop. Toda
resposta congela as demais por um round trip até o Phoenix. A correção (`batch=True`
em `app/core/telemetry.py:43`) é de uma linha e é o item de melhor retorno da fase 1.

**Como ler.** `setup_phoenix` (`app/core/telemetry.py:27`) retorna cedo quando a
chave é vazia — sem chave, **não há telemetria e o item 20 não existe hoje**. Com
chave, cada resposta exporta 2 spans de forma síncrona no event loop, e o item 20
está ativo. A correção (`batch=True`) é de uma linha e entra na fase 1 de qualquer
jeito, mas isto define a prioridade.

---

## 5. IP falsificável — decide a correção do item 21

**Onde:** PowerShell.

**A rota precisa ter rate limit.** `/health` **não tem** — o limiter é aplicado por
rota, com decorador, e `/health` ficou de fora. Usar
`GET /api/v1/landing-pages/finance/check`: 60/minuto, pública, `GET` (não passa pela
guarda de origem) e só faz um SELECT.

Primeiro bloco — 70 chamadas com o primeiro IP, até estourar o limite de 60:

```powershell
1..70 | ForEach-Object {
    try {
        $r = Invoke-WebRequest -UseBasicParsing `
             -Uri "https://medico360-ia.up.railway.app/api/v1/landing-pages/finance/check?email=teste-fase0@example.com" `
             -Headers @{ "X-Forwarded-For" = "1.2.3.4" }
        "$_`: $($r.StatusCode)"
    } catch {
        "$_`: $($_.Exception.Response.StatusCode.value__)"
    }
}
```

Assim que aparecer `429`, rodar o segundo bloco **na mesma janela de 1 minuto**,
trocando só o IP:

```powershell
1..5 | ForEach-Object {
    try {
        $r = Invoke-WebRequest -UseBasicParsing `
             -Uri "https://medico360-ia.up.railway.app/api/v1/landing-pages/finance/check?email=teste-fase0@example.com" `
             -Headers @{ "X-Forwarded-For" = "5.6.7.8" }
        "$_`: $($r.StatusCode)"
    } catch {
        "$_`: $($_.Exception.Response.StatusCode.value__)"
    }
}
```

O `try/catch` é necessário: o `Invoke-WebRequest` trata 4xx como erro terminante e
o loop morreria no primeiro 429 — que é justamente o que se quer observar.

**Anotar:**

- Em que número apareceu o primeiro `429` no bloco 1? → **Resposta (2026-09-21):** estourou dentro das 70, como esperado. O limiter está ativo em produção e conta certo.
- O bloco 2, com IP diferente, voltou a dar `200`? → **Resposta (2026-09-21):** não. `429` nas cinco, com `X-Forwarded-For: 5.6.7.8`. **Trocar o header não zera a cota.**
- Se houver acesso aos logs do Railway: qual IP aparece registrado? → **Resposta (2026-09-21):**

```
179.228.59.104:0 - "GET /api/v1/landing-pages/finance/check?..." 429
ratelimit 60 per 1 minute (179.228.59.104) exceeded at endpoint: /api/v1/landing-pages/finance/check
```

**ITEM 21: A PARTE GRAVE CAI. Prova fechada pelos logs.** As requisições saíram com
`X-Forwarded-For: 5.6.7.8`, e o limiter contabilizou `179.228.59.104` — o IP real.
A borda do Railway sobrescreve o header antes do uvicorn, então o
`--forwarded-allow-ips "*"` do `Dockerfile:22` não é explorável. **O cenário do
relatório — "um atacante zera todos os limites, inclusive o de código por e-mail" —
não acontece hoje.**

Os logs tornaram desnecessária a rodada de confirmação que faltava: eles mostram
diretamente qual chave o limiter usou, sem depender de janela de tempo.

**O que continua valendo do item 21:**

- O limite é **por IP**, então um hospital inteiro atrás de NAT divide a mesma cota
  de 30 perguntas por minuto. É a queixa real de usuário.
- O limite é **em memória**, então ele se multiplica pelo número de processos ou
  réplicas — e a fase 4 quer justamente subir réplicas.
- A dependência é frágil: se a borda mudar de comportamento, ou se um dia a API
  ficar atrás de outro proxy, o vetor volta. O `--forwarded-allow-ips "*"` é
  permissivo demais para o que o sistema precisa.

**Escopo novo:** chave por usuário nas rotas autenticadas com IP como reserva,
armazenamento no Redis. Restringir os IPs confiáveis vira endurecimento, não
correção urgente. O item sai de "Alta" para "Média" e continua na fase 3.

**Achado lateral.** O corpo do 429 é `{"error":"Rate limit exceeded: 60 per 1
minute"}` — mensagem padrão do slowapi, em inglês. Mesma classe do item 13 (limite
semanal aparece como "Erro ao conectar com o servidor"): o usuário recebe texto que
não explica o que aconteceu. Vale tratar os dois juntos.

**Como ler.** Se o bloco 2 volta a `200`, **o header manda na cota e o item 21 está
confirmado**: qualquer um zera o próprio limite trocando uma string, inclusive no
limite de código por e-mail (`5/minute` em `auth.py:69`). Se o bloco 2 continuar em
`429`, a borda do Railway sobrescreve o `X-Forwarded-For` e o risco é bem menor.

**Como ler.** O `Dockerfile:22` roda com `--forwarded-allow-ips "*"`, então o uvicorn
confia no `X-Forwarded-For` de **qualquer** remetente, e o limiter
(`app/core/limiter.py`) usa `get_remote_address`. Se trocar o header troca a cota,
um atacante zera qualquer limite — inclusive o de código por e-mail. Se a borda do
Railway sobrescrever o header, o risco cai bastante e a correção fica mais simples.

---

## 6. Dumps de produção (item 7) — **ABERTO**

- `backups/` ainda tem arquivo? → **Resposta (2026-09-21): sim, os cinco, intactos.**

```
medico360-20260819T195428Z.dump   14,4 MB
medico360-20260831T182702Z.dump   11,4 MB
medico360-20260909T212317Z.dump   11,7 MB
pre-007-20260901-164930.dump      11,4 MB
pre-008-20260902-113054.dump      11,5 MB
```

Total 58 MB, datas originais preservadas — nada foi movido nem criptografado. O item
7 do ranking **continua ativo**: cinco cópias do banco real, sem criptografia, na
área de trabalho.

**O que fazer:** mover para fora da árvore do projeto, criptografar, e apagar os dois
`pre-*` (dumps de segurança pré-migration que já cumpriram a função). É o item de
maior retorno por minuto de trabalho em todo o plano.

---

## 7. Limites de infraestrutura — alimenta a fase 4

**Onde:** Railway → serviço do Postgres → *Variables* / *Metrics*; e serviço do
backend → *Metrics*.

- `max_connections` do Postgres → **Resposta: não encontrado no painel.** Continua em aberto.
- Limite de memória do container do backend → **Resposta: 8 vCPU / 8 GB.**
- Tempo de inatividade (idle timeout) do proxy → **Resposta: não exposto no painel.**

### Leitura do item 7

**A memória folgada muda a prioridade do item 26.** Com 8 GB, o cenário "dez revisões
de exame simultâneas custam perto de 1 GB" deixa de derrubar o container. O item
continua valendo como higiene (ler o corpo em blocos antes de checar o tamanho), mas
sai da lista de tetos próximos.

**O `max_connections` continua sendo a peça que falta**, e é a que mais importa para
a fase 4. O pool é `pool_size=30, max_overflow=10` (`app/core/database.py:19`), e
cada stream segura 2 conexões — daí o teto de ~20 streams. Se o Postgres do Railway
tiver `max_connections` **menor que 40**, o teto real é mais baixo ainda, e o erro
muda de "espera 30 s" para `FATAL: too many connections`.

**Como obter, já que o painel não mostra:** rodar contra o banco de produção, em
qualquer cliente SQL:

```sql
SHOW max_connections;
SELECT count(*) FROM pg_stat_activity;
```

A segunda linha também diz quantas conexões estão em uso agora — número útil para a
fase 4. São consultas de leitura, não alteram nada.

**As 8 vCPU são uma oportunidade que o relatório não considerou.** O backend roda em
um processo só (`Dockerfile:21`), então 7 dos 8 núcleos estão ociosos. Subir para
múltiplos workers é o ganho de capacidade mais barato disponível — mas **não pode ser
feito antes** do rate limit ir para o Redis (senão o limite se multiplica por worker)
e do envio do digest ganhar transação por usuário (senão duplica e-mail). As duas
travas já estão escritas na fase 4; a novidade é que o hardware já está pago e parado.

**Como ler.** O relatório calcula o teto de ~20 streams simultâneos assumindo pool de
30+10. Com o `max_connections` real, o número deixa de ser derivado de configuração e
passa a ser aritmética verificada.

---

## 8. Uso da rota `/orquestrador/query` — decide o item 4 das pendências

**Onde:** Railway → backend → *Logs*, ou o Sentry (há amostragem de transações a 5%).

**Anotar:**

- Chega chamada a `/orquestrador/query` de algo que não seja o frontend? → **Resposta: não foi possível ver nos logs.** Continua em aberto.

**Não bloqueia nada agora** — a decisão sobre `/query` é da fase 7. Quando chegar a
hora, o caminho mais simples é olhar no Sentry a taxa de transações por rota (a
amostragem de 5% já basta para dizer se existe chamador além do frontend), ou
instrumentar a rota com um log de `User-Agent` por uma semana.

**Como ler.** Se só o frontend chama, a rota pode ser aposentada na fase 7. Se houver
outro chamador, ela vira coletor.

---

## Aceite da fase 0 — fechada em 2026-09-21

Seis dos oito itens respondidos. Os dois em aberto (`max_connections` e o uso de
`/query`) não bloqueiam a fase 1.

### Veredito dos itens que dependiam de produção

| Item | Antes | Depois da conferência |
| --- | --- | --- |
| 9 — 403 no cadastro de DEA | Depende de produção | **ATIVO.** `dea_url` fora das duas listas, 403 confirmado no navegador |
| 10 — 403 ao salvar tema de notícia | Depende de produção | **MASCARADO.** `news-m360` está em `EMBED_ALLOWED_ORIGINS`; 201 no teste. Defeito de código continua |
| 20 — Phoenix síncrono | Depende de produção | **ATIVO.** Chave presente, 2 spans síncronos por resposta |
| 21 — IP falsificável | Alta | **REBAIXADO para Média.** Logs provam que a borda sobrescreve o `X-Forwarded-For`. Sobra o limite por IP em memória |
| 7 — Dumps de produção | Relatado | **ATIVO, não resolvido.** Os cinco arquivos continuam em `backups/`, 58 MB |

### Achados novos, fora do relatório de 2026-09-18

1. **`NOTICIAS_URL` aponta para a API**, não para o app de notícias. Todo link do
   digest diário por e-mail está quebrado (`/artigo/{id}`, `/preferencias`, "Ver
   tudo" → 404). Correção: trocar a variável no painel. Sem deploy, sem código.
2. **`PHOENIX_API_KEY` exposta** em texto puro na conversa de 2026-09-21. Rotacionar
   no Arize.
3. **O corpo do 429 é a mensagem padrão do slowapi, em inglês**
   (`{"error":"Rate limit exceeded: 60 per 1 minute"}`). Mesma classe do item 13:
   o usuário recebe texto que não explica o que houve. Tratar junto.
4. **7 das 8 vCPU ociosas** — um processo só. Oportunidade de capacidade que o
   relatório não considerou, destravada pelas correções já previstas na fase 4.

### Próximos passos imediatos

- [ ] Mover e criptografar os cinco dumps de `backups/` (item 7) — cinco minutos
- [ ] Trocar `NOTICIAS_URL` para `https://news-m360.up.railway.app` no painel
- [ ] Rotacionar a `PHOENIX_API_KEY` no Arize
- [ ] Rodar `SHOW max_connections;` no banco de produção
- [ ] Começar a fase 1 (harness), que não depende de mais nada daqui
