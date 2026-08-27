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

## 5. ~~O campo `history` da API é inerte~~ — RESOLVIDO em 2026-08-27

O frontend parou de enviar e o campo saiu do schema do orquestrador, junto com
o parâmetro `history` dos dois serviços e a `messagesRef` que existia só para
alimentá-lo.

Clientes antigos que ainda mandem `history` continuam funcionando — o FastAPI
descarta campo desconhecido —, e há teste travando essa compatibilidade em
`tests/test_contexto_seguranca.py`.

**O agregador não foi tocado:** ele ainda lê `history` do corpo, e o frontend
segue enviando por lá. Se o agregador voltar à interface um dia, essa dívida
existe lá também.

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

## 10. Calibração da busca em pasta — parcialmente medida

**Estado.** O limiar original (0.72) estava errado e foi corrigido na
homologação de 2026-08-27. Hoje é um **piso contra lixo** de 0.25, não um
critério de relevância: quem filtra relevância é a PASTA, e a similaridade só
ranqueia o que cabe no orçamento.

**O erro que motivou a correção, registrado para não se repetir.** O 0.72 foi
ancorado no 0.88 do cache semântico, com o raciocínio "mais frouxo, então
serve". Os dois números medem regimes incomparáveis: o cache compara dois
prompts CURTOS quase idênticos; a busca em pasta compara uma pergunta curta com
um documento clínico longo. Medição real: a pergunta *"existe alguma
contraindicação para o paciente Jorge?"* pontuou **0.516** contra a evolução que
diz *"Jorge, 58 anos, HAS em acompanhamento"* — o documento mais pertinente
possível. Com limiar 0.72, a busca voltava vazia para toda pergunta, sempre.
Cosseno absoluto não é comparável entre usos diferentes.

**O que ainda não foi medido:** `MAX_TRECHOS = 4` e o valor do piso em pastas
grandes e heterogêneas. Com piso baixo, uma pasta com assuntos misturados pode
injetar trecho pouco pertinente — o teto de 4 e o rótulo de "material de apoio"
limitam o estrago, mas o ajuste fino depende de uso real.

**Observabilidade:** `recuperar_trechos` agora loga as similaridades de cada
busca. Sem isso, "não veio contexto" e "veio contexto ruim" eram
indistinguíveis de fora — foi essa cegueira que deixou o limiar errado passar
por 20 testes verdes.

---

## 11. Sem índice ivfflat em `message_embeddings`

**O que é.** `semantic_cache` tem índice ivfflat; `message_embeddings` não.

**Por quê.** ivfflat é aproximado e precisa de volume para ser treinado bem.
Aqui a busca é sempre dentro de UMA pasta de UM usuário — o conjunto filtrado é
pequeno e a varredura exata é mais correta.

**Quando revisitar.** Se aparecer pasta com centenas de conversas e a latência
da primeira resposta subir de forma perceptível.

---

## 12. Indexação preguiçosa cobra a conta na primeira pergunta

**O que é.** `indexar_pasta` roda no caminho quente: a primeira pergunta feita
numa pasta que já tinha conversas paga a indexação de até 60 trechos (uma
chamada de embedding em lote) antes de a resposta começar.

**Por que assim.** Indexar na escrita de cada mensagem cobraria embedding de
toda conversa, inclusive as que nunca entram em pasta. E não resolveria conversa
MOVIDA para dentro de uma pasta depois de pronta, que nunca teria sido indexada.

**Alternativa se incomodar:** disparar a indexação em background ao mover
conversa para pasta, mantendo a preguiçosa como rede.

---

## 13. Embeddings não são reindexados quando a mensagem muda

**O que é.** `message_embeddings.content` é uma cópia do texto no momento da
indexação. Não há caminho que edite mensagem hoje, então não há divergência —
mas se um dia houver, o índice ficará apontando para texto antigo.

**Mitigação atual:** nenhuma necessária. Registrado para que quem for
implementar edição de mensagem saiba que precisa invalidar o índice.

---

## 14. Sem cobertura end-to-end do fluxo de exames

**O que é.** Os testes de exame cobrem as peças (resolução de anexos, posse,
vínculo, roteamento de modo) mas nenhum exercita o caminho completo com o app
rodando: subir imagem real → visão → resposta → recarregar → anexo ainda lá.

**Por que.** O e2e existente (`calculadoras-app`, Playwright) cobre outro app, e
o fluxo de exames depende de chamada real a provedor de visão — o que o guard de
rede dos testes bloqueia por bom motivo.

**Mitigação atual:** validação manual. Está no roteiro de teste do dia seguinte.
