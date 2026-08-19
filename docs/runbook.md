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

> ### Sobre reconstruir o schema
>
> Isto já foi uma limitação: o schema nascia de um `create_all` fora do Alembic e
> `alembic upgrade head` num banco vazio falhava. Hoje existe a migration de
> baseline (`000_baseline`), e o CI prova a cada push que a cadeia aplica do zero
> (job `backend`, step "migrations aplicam do zero").
>
> Isso reconstrói o **schema**, não os **dados**. Para recuperar dados, o caminho
> continua sendo o backup do Railway, abaixo.

1. Railway → Postgres → aba de backups → escolher o ponto de restauração.
   **Anote a hora do snapshot** — sem ela o RPO não é calculável depois.
2. Restaurar para um banco **novo**, nunca por cima do atual. **Marque início e
   fim**: esse intervalo é o RTO real.
3. Validar com o script, da sua máquina (não é preciso terminal no Railway — as
   duas URLs saem de Railway → Postgres → *Connect*):

   ```
   python -m scripts.verificar_restore --origem "postgresql://..." --restaurado "postgresql://..."
   ```

   Ele só lê (pode apontar para produção como origem), compara **todas** as
   tabelas — não só três —, confere a revisão do Alembic e sai com código 1 em
   qualquer divergência. Conferir 3 tabelas escolhidas a olho deixaria passar
   perda em `consent_logs` ou `audit_logs`, que existem por obrigação regulatória.
4. Subir um ambiente de **teste** contra o restaurado e confirmar
   `/api/v1/health/ready` (esse endpoint consulta o Postgres de verdade;
   `/api/v1/health` não). **Nunca aponte produção para o banco restaurado** —
   é assim que um ensaio vira incidente.
5. Registrar aqui o RPO (distância entre o dado mais recente que o script mostra
   e a hora do snapshot) e o RTO (o tempo do passo 2).

**Pendente — lacuna conhecida, não fechada:** ninguém executou um restore de
verdade ainda. Os números de RPO e RTO seguem **prometidos, não medidos**, e só
deixam de ser quando alguém com acesso ao painel do Railway fizer o ensaio:
restaurar um ponto recente para um banco novo cronometrando início e fim, conferir
as contagens de `users`, `conversations` e `interactions` contra o original, subir
um ambiente de teste (nunca produção) contra o banco restaurado e registrar aqui os
tempos reais. Enquanto isso não acontecer, trate o plano de recuperação como não
testado.

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
