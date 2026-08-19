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

> ### Limitação importante, leia antes
>
> **O banco não pode ser reconstruído do zero pelas migrations.** A migration `001`
> é a raiz e só cria `semantic_cache`; nenhuma migration cria `users`,
> `conversations` ou `interactions` — essas tabelas nasceram de um `create_all`
> fora do Alembic, e as demais migrations são `ALTER`s em cima.
>
> Consequência prática: **a recuperação depende do backup do Railway**, não de
> replay de migrations. `alembic upgrade head` num banco vazio falha.
>
> Enquanto não houver uma migration de baseline, este é o único caminho.

1. Railway → Postgres → aba de backups → escolher o ponto de restauração.
2. Restaurar para um banco **novo**, nunca por cima do atual.
3. Validar: contagem de `users`, `conversations` e `interactions` compatível com o
   esperado.
4. Só então apontar `DATABASE_URL` para o banco restaurado e reiniciar.

**Pendente:** ninguém executou um restore de verdade ainda. Até que isso aconteça e
o tempo seja cronometrado, não há RPO nem RTO conhecidos — só prometidos.

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

**Antes de confiar:** provoque um erro de propósito num ambiente de teste e
confira no painel que o evento chegou **sem** o texto do prompt em nenhum campo.
O scrubbing tem 17 testes (`tests/test_error_tracking.py`), incluindo um ponta a
ponta, mas a verificação no painel real custa dois minutos e fecha a dúvida.

Nunca ligar `send_default_pii=True` nem remover o `before_send`: é o que separa
"alerta útil" de "prontuário saindo do país num evento de erro".

---

## Retenção de dados

O expurgo roda por cron: `python -m scripts.expurgar_dados_vencidos`.

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
