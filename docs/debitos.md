# Débitos técnicos conhecidos

Registro do que sabemos estar pendente, com o motivo de ter sido deixado assim.
Escrito em 2026-08-27, ao fim da Fase 5 do trabalho de reposicionamento do
Orquestrador.

Um débito listado aqui é uma decisão consciente, não um esquecimento. O que
falta em cada um é o critério para resolvê-lo — quase sempre uma decisão de
produto, não de código.

---

## 1. Retenção de dados de saúde em `file_extractions` — LGPD

**O que é.** A tabela guarda o texto extraído de todo arquivo enviado e, no caso
de imagens, o **base64 da imagem inteira**. Não há expiração, não há rotina de
limpeza, e nada apaga esses registros exceto a remoção do usuário (`ondelete
CASCADE` em `user_id`).

**Por que importa mais agora.** A Fase 5 vinculou anexos a mensagens
(`interaction_id`) e passou a aceitar até cinco arquivos por mensagem. O
problema já existia — a Fase 5 não o criou —, mas o volume cresce e os arquivos
passam a ser permanentemente referenciados pelo histórico, o que torna apagá-los
uma decisão com efeito visível ao médico.

**O que falta decidir (não é decisão técnica):**
- Prazo de retenção de exame anexado. É prontuário? Segue os 20 anos do CFM ou
  é material transitório de apoio?
- O que acontece com o anexo quando o médico apaga a conversa. Hoje a conversa
  tem *soft delete* (`status`) e o arquivo fica.
- Se o base64 da imagem precisa ficar no Postgres depois de a descrição ter sido
  extraída. É o item mais pesado da tabela.

**Onde mexer:** `app/models/models.py` (`FileExtraction`),
`app/services/file_extractor_service.py`, e uma rotina de expurgo que não existe.

---

## 2. PDF escaneado sem OCR

**O que é.** `extract_pdf` usa `pdfplumber`, que só lê texto embutido. Um laudo
escaneado — imagem dentro de um PDF — devolve
`"(PDF sem texto extraível — pode ser escaneado sem OCR)"`.

**Por que não foi resolvido.** OCR de qualidade clínica é um projeto próprio, com
custo e dependência nova (Tesseract ou API paga). E há uma saída melhor no curto
prazo: laudo antigo escaneado costuma ser mais bem atendido pelo caminho de
**imagem**, que já passa por visão.

**Mitigação atual:** nenhuma na interface. O médico anexa o PDF, recebe uma
resposta pobre e não entende por quê.

**Próximo passo barato:** detectar o retorno vazio e avisar na tela —
"este PDF parece ser digitalizado; envie como imagem para melhor leitura".

**Onde mexer:** `app/services/file_extractor_service.py:extract_pdf`.

---

## 3. Contagem de tokens é estimativa, não medição

**O que é.** `app/services/context_budget.py` estima tokens por uma razão fixa de
3,5 caracteres por token. Não há tokenizador.

**Por que assim.** `tiktoken` só vale para OpenAI e o projeto fala com quatro
provedores; um tokenizador por provedor seria dependência pesada para uma
decisão que só precisa ser conservadora. A razão é deliberadamente baixa: errar
para menos manda menos contexto (seguro), errar para mais estoura a janela.

**Sintoma se estiver errada:** o médico recebe menos contexto do que caberia. Não
quebra, só empobrece — e por isso é invisível.

**O que falta:** medir o erro real da estimativa contra o `tokens_in` que os
providers já devolvem em `ProviderResponse`. O dado para calibrar já está sendo
gravado em `interaction_responses.tokens_in`, sem ninguém olhar.

---

## 4. Orçamento de contexto de 6000 tokens não foi calibrado

**O que é.** `DEFAULT_HISTORY_TOKEN_BUDGET = 6000` é um número escolhido, não
medido. É quanto do prompt aceitamos gastar relembrando a conversa.

**O que falta:** verificar em conversas reais se 6000 corta cedo demais (o médico
percebe que "ele esqueceu o que eu disse") ou tarde demais (custo por mensagem
subindo sem ganho). Depende de dados de uso que ainda não existem.

---

## 5. O campo `history` da API é inerte, mas o frontend ainda o envia

**O que é.** Desde a Fase 4, `/orquestrador/query` e `/stream` leem o histórico
do banco e **ignoram** o campo `history` do corpo da requisição. O frontend
continua enviando.

**Por que ficou.** Remover um campo de contrato é mudança que merece ser
deliberada. Há teste (`tests/test_contexto_seguranca.py`) garantindo que a
requisição com `history` continua sendo aceita, justamente para que a remoção
seja consciente e não uma quebra silenciosa.

**Custo de deixar:** payload maior à toa em toda mensagem, e um campo que induz
quem lê o código a achar que o cliente controla o contexto — que era exatamente
o problema corrigido.

**Onde mexer:** `frontend-app/src/api/orquestrador.ts` (parar de enviar),
depois `app/api/v1/endpoints/orquestrador.py` (remover do schema).

---

## 6. Mapa de prompts e mapa de modos vivem em arquivos diferentes

**O que é.** `MODE_SYSTEM_PROMPTS` está em `app/core/prompts.py` e
`MODE_MODEL_MAP` em `app/services/orquestrador_modes.py`. Adicionar um modo
exige tocar os dois.

**Por que não foi unificado.** Juntar exigiria `orquestrador_modes` importar
`core/prompts`, invertendo a direção da dependência entre camada de serviço e
camada de configuração.

**Mitigação:** existe teste (`test_todo_modo_com_llm_tem_prompt_de_sistema`) que
falha se divergirem. O risco de um modo responder com prompt vazio está coberto.

---

## 7. Teste intermitente: `test_revogacao_preserva_o_aceite_anterior`

**O que é.** Falha em ~1 de cada 3 execuções da suíte completa, e passa isolado.

**Causa.** `consent_service.historico()` ordena só por `created_at DESC`, sem
critério de desempate. No harness, as duas escritas caem na mesma transação e
recebem o mesmo timestamp de `now()`, então a ordem entre elas é indefinida.

**Por que não foi corrigido.** É código de consentimento/LGPD, e mudar a
ordenação de um histórico com valor probatório é decisão de quem responde pela
conformidade, não de quem passava por perto.

**Correção provável:** desempate por `id` ou por uma coluna de sequência.

**Onde mexer:** `app/services/consent_service.py:80`.

---

## 8. Anexos sem backfill no histórico

**O que é.** Mensagens anteriores à migration `001_file_interaction` não têm
vínculo com seus anexos e sempre voltam com `attachments: []`.

**Por que não há backfill.** Não existe informação para inferir qual arquivo
pertencia a qual mensagem: o texto era injetado no prompt e o vínculo nunca foi
gravado. Qualquer heurística (por usuário e proximidade de horário) erraria em
silêncio, e errar aqui significa mostrar ao médico um exame que não era daquela
conversa.

---

## 9. Vulnerabilidades pré-existentes no `npm audit` do frontend

**O que é.** Seis vulnerabilidades altas em `react-router`, `postcss`, `nanoid`,
`brace-expansion`, `fast-uri` e `serve` — todas transitivas e anteriores ao
trabalho atual.

**Por que não foram corrigidas junto.** `npm audit fix` arrasta bump de
`react-router`, que é dependência de roteamento de todo o app. Merece PR próprio
com regressão visual, não carona numa mudança de contexto de IA.

---

## 10. Sem cobertura end-to-end do fluxo de exames

**O que é.** Os testes de exame cobrem as peças (resolução de anexos, posse,
vínculo, roteamento de modo) mas nenhum exercita o caminho completo com o app
rodando: subir imagem real → visão → resposta → recarregar → anexo ainda lá.

**Por que.** O e2e existente (`calculadoras-app`, Playwright) cobre outro app, e
o fluxo de exames depende de chamada real a provedor de visão — o que o guard de
rede dos testes bloqueia por bom motivo.

**Mitigação atual:** validação manual. Está no roteiro de teste do dia seguinte.
