# Teste de carga

Feito para o lançamento de 08/10/2026. A pergunta: **o que quebra quando a sala
inteira abre o Médico 360 ao mesmo tempo?**

São duas etapas:

- **A — local (esta pasta).** Serve para achar o teto do NOSSO lado sem pagar LLM
  e sem depender da Waid: pools de conexão, workers, Redis, DLP, rate limit.
- **B — produção.** Serve para confirmar com os provedores de verdade. Ainda não
  foi feita. Ver "O que a etapa A não mede", no fim deste arquivo.

## O que é real e o que é falso

| Real (igual a produção) | Falso |
|---|---|
| Imagem do `Dockerfile`, `APP_ENV=production`, 2 workers | Anthropic, OpenAI, Perplexity, Gemini, Maritaca |
| Postgres 16 + pgvector, `max_connections=500` | Waid/Curseduca (validação do token, `members/by`) |
| Redis (rate limit e caches) | PharmaDB, PubMed, SendGrid |
| Pools do httpx (100 curtas / 300 streams), DLP com NER | |

A troca é feita no **transporte** do httpx ([interceptador/sitecustomize.py](interceptador/sitecustomize.py)),
e não nos provedores. Isso preserva os limites dos pools. O servidor falso
([falso_externo.py](falso_externo.py)) responde no formato de cada serviço, com
a latência medida em produção (CLINICAL p50 33 s / p95 57 s, QUICK p50 13 s / p95 28 s).
O interceptador **se recusa a subir** se o `DATABASE_URL` não for local.

## Como rodar (Git Bash, da raiz do repo)

```bash
bash scripts/carga/subir_ambiente.sh                 # constrói a imagem e sobe tudo (~1 min)

# uma rodada, com observação do servidor (CPU, conexões do banco) a cada 2 s
bash scripts/carga/rodar.sh 240 --cenario onda --medicos 300 \
     --janela-login 60 --janela-perguntas 60 --ips 300 --primeiro-id 6001

# degradar os serviços externos sem reconstruir nada
FALSO_ESCALA_WAID=8 bash scripts/carga/subir_ambiente.sh --so-falso   # Waid 8x mais lenta
FALSO_ERRO_PCT=30   bash scripts/carga/subir_ambiente.sh --so-falso   # 30% de 429 nos modelos
bash scripts/carga/subir_ambiente.sh --so-falso                       # volta ao normal

bash scripts/carga/subir_ambiente.sh --derrubar
```

**Cenários** (`gerar_carga.py`):

- `rajada` — só login e tela inicial.
- `onda` — login + 1 pergunta cada (30% fazem uma segunda) dentro de `--janela-perguntas`.
- `continuo` — pergunta, lê 30 a 90 s, pergunta de novo, por `--duracao`.

**Opções:**

- `--ips 1` põe todos no mesmo IP (o Wi-Fi do evento); `--ips N` espalha.
- `--primeiro-id` novo cria contas novas (com onboarding); repetir ids reusa contas.

Os resultados ficam em `scripts/carga/resultados/` (fora do git).

**Rode o gerador pelo `rodar.sh`, nunca direto do Windows.** O encaminhamento de
porta do Docker Desktop é o gargalo: 300 conexões simultâneas em `localhost:8010`
levam 31 s de mediana, contra 1,8 s de dentro da rede do Docker.

## Resultados de 2026-09-28 (etapa A)

Máquina: Docker Desktop com 4 CPUs para tudo (backend, banco, servidor falso e
gerador). O backend rodou com 2 workers, igual a produção.

**Capacidade (Waid e modelos normais, cada médico com o próprio IP):**

| Médicos | Perguntas | Pico de streams | Erros | 1º token QUICK p95 | CPU máx. do backend |
|---|---|---|---|---|---|
| 100 em 3 min | 136 | 16 | 0 | 3,9 s | — |
| 300 em 1 min | 405 | 81 | 0 | 4,4 s | 38% |
| 600 em 1 min | 764 | 154 | 0 | 4,6 s | 46% |
| 1200 em 1 min | 1559 | 301 | 0 | 4,9 s | 137% (teto: 200%) |

O nosso lado quase não acrescenta latência à do modelo, e o banco fica em 61
conexões sem nenhuma presa esperando o modelo. **Mesmo com 1200 médicos em um
minuto nada quebrou.** Ali começou o joelho da curva: a tela inicial foi de 31 ms
para 250 ms no p95, e a CPU chegou perto do teto dos 2 workers.

**Login com todos no mesmo IP** (limite de 120/min por IP em `/auth/embed/token`):

| Médicos | Janela | Levaram 429 | Não entraram | Espera máx. |
|---|---|---|---|---|
| 200 | 60 s | 182 respostas | **6 (3%)** | 20 s |
| 200 | 180 s | 1 | 0 | 3,6 s |

A espera do front no 429 (2 + 5 + 10 s) termina antes de a janela de 1 minuto do
limite virar.

**Waid lenta** (300 médicos em 1 min):

| Waid | Login p50 / p95 | Não entraram (503) |
|---|---|---|
| normal | 0,8 s / 1,8 s | 0 |
| 8x mais lenta | 6,0 s / 11,1 s | **10 (3%)** |
| 15x mais lenta | 8,7 s / 13,8 s | **83 (28%)** |

O 503 acontece quando a validação passa do timeout de 8 s. O front mostra "A
verificação de identidade está indisponível" e **não tenta de novo** (só tenta
no 401). O login segura uma conexão do banco em transação enquanto espera o
`members/by` da Waid. Com a Waid 8x mais lenta, isso chegou a 19 das 60
conexões, sem esgotar o pool.

**Provedor falhando** (30% de 429 nos modelos, 300 médicos):

- As 410 perguntas terminaram em `done`, e 19% foram respondidas pelo modelo
  reserva.
- O reserva não faz streaming. O 1º token vai para 11 s (QUICK) e 21 s (CLINICAL)
  no p95, e o texto chega de uma vez.
- 3 médicos (0,7%) receberam "Desculpe, não foi possível processar": o Gemini
  reserva estourou o próprio timeout de 15 s.

**Uso contínuo** (200 médicos, 20 min):

- 3319 perguntas, zero erros, tempos iguais aos da onda curta.
- Nenhuma interação ficou `em_andamento` no fim: as 6983 do banco estão `completed`.
- As conexões do banco ficaram estáveis em 62.
- A memória do backend foi de 584 para 634 MiB e **não voltou** depois da carga,
  crescendo em degraus. São ~15 KB por pergunta. Isso não pesa para um dia de
  evento, mas vale acompanhar no Railway numa rodada mais longa.

### Observação que não é carga

Há sempre **1 conexão `idle in transaction`**: é a do líder (`app/core/lider.py`),
que deixa a transação aberta de propósito para segurar o advisory lock. O `xmin`
dela avança a cada `SELECT 1` (60 s), então ela não segura o vacuum. Quem ler o
`medir_conexoes_presas.py` deve descontar essa conexão.

## O que a etapa A não mede

- **O limite dos provedores de LLM** (RPM/TPM do plano). É o teto mais provável
  no evento, e só a etapa B ou o painel de cada provedor respondem.
- **A capacidade da Waid:** quantas validações de token por minuto ela aguenta,
  e se limita por IP de origem (todo o nosso tráfego sai do mesmo IP).
- **A borda do Railway, TLS, Phoenix e Sentry**, que estão desligados aqui.
- **Os fronts estáticos** (chat, calculadoras, notícias), que são servidos fora
  do backend.
- **A CPU de produção:** o Railway tem 8 vCPU. Aqui, 4 CPUs eram divididas
  com o gerador.
