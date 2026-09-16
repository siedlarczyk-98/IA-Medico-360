# Plano de cobertura de testes

Medido em **2026-09-16**, com `pytest --cov=app` e `vitest --coverage`, sobre
1184 testes de backend e 134 de front passando.

| | Cobertura | Observação |
|---|---|---|
| Backend (`app/`) | **73%** → **77%** | 7759 linhas; 53 arquivos em 100%. Itens 1, 2 e 3 feitos em 2026-09-16 |
| Frontend (`src/`) | **53%** → **57%** statements | 1107 statements. Item 4 feito em 2026-09-16 |

O número não é o problema — 73% está acima da média para um projeto deste
porte, e a qualidade dos testes é melhor do que a porcentagem sugere: boa parte
foi escrita depois de um incidente real (`test_conversas_referencias.py` existe
porque as fontes sumiam ao reabrir; `test_renomear_sem_mandar_evolucao_nao_a_apaga`
porque um rename apagaria a evolução do paciente). O que este plano ataca é
**onde** falta, não quanto.

---

## O princípio que ordena as prioridades

Não perseguir porcentagem. Cada item abaixo entra pelo **custo de estar errado**,
não pelo número de linhas que colore de verde. Um `ProfileModal.tsx` a 3% é
irrelevante; 374 linhas sem teste decidindo interação medicamentosa não é.

Três perguntas, nesta ordem:

1. Se isto quebrar, o médico percebe? (Se não → prioridade alta.)
2. Se isto quebrar, alguém se machuca? (Consequência clínica.)
3. Isto já quebrou antes? (Padrão que se repete.)

---

## Prioridade 1 — PharmaDB (`pharmadb_service.py`, 374 linhas, **0%**)

O maior buraco do repositório, e o de maior consequência: bula, interação
medicamentosa, receita e genéricos, sem uma linha de teste.

**Reavaliação importante:** à primeira vista parece intestável por ser
integração externa. Não é. Quase metade do arquivo é **lógica pura**, e é ali
que está o risco clínico:

| O que testar | Por quê | Rede? |
|---|---|---|
| Deduplicação de pares em `checar_interacoes` | `pares_vistos` com `tuple(sorted(...))`: se falhar, a mesma interação aparece duas vezes — ou, pior, some | não |
| Filtro `pa_b_id not in pa_ids` | é o que impede alertar sobre um fármaco que o médico não perguntou | não |
| `len(pas) < 2` → `insuficiente` | distingue "nenhuma interação" de "não consegui checar". Confundir os dois é dizer "pode prescrever" quando a resposta é "não sei" | não |
| `SEMAFORO` grave/moderada/leve → nível e emoji | a cor é o que o médico lê primeiro | não |
| Os 4 formatadores (`formatar_interacoes`, `_bula`, `_receita`, `_genericos`) | entrada/saída pura, alto retorno por linha de teste | não |
| `mensagem_nao_encontrado` | o texto que aparece quando a base não tem o fármaco | não |
| `_token_valid` / renovação aos 3300s | token expirado derruba tudo em silêncio | não |
| `_cache_get` / `_cache_set` com Redis fora | fail-open ou fail-closed? precisa ser decisão testada | mock |

**A invariante que mais vale travar:** `status="sem_interacao"` só pode sair
quando a base foi consultada e não achou nada. Se um erro de rede puder produzir
o mesmo status, o app diz "nenhuma interação conhecida" quando deveria dizer
"não consegui verificar" — e o médico prescreve com base num silêncio que não é
resposta.

**Esforço:** ~1 dia. **Ganho:** 0% → ~55%, na área de maior risco clínico.

> **FEITO em 2026-09-16 — 0% → 52%**, em `tests/test_pharmadb_interacoes.py` (14)
> e `tests/test_pharmadb_bula_receita.py` (15).
>
> **ACHADO ABERTO, aguardando decisão de produto:** falha na consulta de
> interações (PharmaDB fora, disjuntor aberto, timeout) produz
> `status="sem_interacao"`, que o formatador renderiza como o VERDE "Nenhuma
> interação conhecida". A base cai e o médico lê uma luz verde. Documentado por
> `xfail` em `test_erro_ao_buscar_interacoes_nao_pode_virar_verde` — a correção
> exige um status novo ("não foi possível verificar") e muda o contrato de
> `checar_interacoes` e do formatador. Quando decidir, o teste já está escrito.
>
> Achado menor, também travado: em `formatar_receita`, `requer_receita` ausente
> vira "🟢 Não requer receita médica" — um controlado apareceria como venda
> livre.

---

## Prioridade 2 — O padrão "chama a OpenAI dentro de um `try/except` amplo"

Quatro módulos compartilham a mesma forma, e é **exatamente a forma do bug
corrigido em 2026-09-16** (`max_tokens` numa família gpt-5 → HTTP 400 → `except`
→ silêncio):

| Módulo | Cobertura | Testa o payload enviado? |
|---|---|---|
| `pubmed_service.py` | 41% | agora sim (`test_pubmed_payload.py`) |
| `medication_extractor.py` | 34% | **não** |
| `triage_service.py` | 50% | **não** |
| `specialty_detector.py` | 97% | **não** (cobertura é do vocabulário) |

O que os três primeiros têm em comum: o trecho descoberto é sempre o bloco
`client.post(...)` — ninguém olha a requisição, só o que se faz com a resposta.
É a lacuna que deixou o bug do PubMed viver por toda a vida do arquivo.

**Auditoria já feita (2026-09-16):** varri todos os callers de
`chat/completions`. Hoje o par modelo↔parâmetro está correto em todos —
`file_extractor_service.py:331` e `news_writer_service.py:131` usam `max_tokens`,
mas com modelos **Anthropic**, onde esse é o nome certo. Não há outro bug latente
do mesmo tipo. O que falta é o teste que impeça o próximo.

**O teste que resolve os três de uma vez:** um `MockTransport` do httpx que
captura o corpo da requisição e afirma o par modelo↔parâmetro — o molde já está
escrito em `tests/test_pubmed_payload.py`.

**Esforço:** ~meio dia para os três. **Ganho:** menor em porcentagem, alto em
prevenção: fecha uma classe inteira de falha silenciosa que já mordeu duas vezes
(cache semântico e PubMed).

> **FEITO em 2026-09-16**, em `tests/test_openai_payloads.py` (14). O ganho foi
> maior que o previsto: `triage_service` 50% → **98%**, `medication_extractor`
> 34% → **89%**, `specialty_detector` 97% (agora com o payload coberto).
>
> Além do par modelo↔parâmetro, os testes travam `temperature=0` nos quatro
> serviços — sem determinismo, o cache serviria classificações contraditórias
> para a mesma pergunta.
>
> **Achado menor:** `EXAM_REVIEW` não aparece no prompt de triagem e também
> **não** está em `MODOS_NAO_TRIADOS`. Na prática a triagem nunca o escolhe (o
> modo é alcançado por anexo), mas nada no código declara isso — quem ler a lista
> de não-triados conclui o contrário. Inconsistência de registro, não bug de
> runtime; travada por `test_o_prompt_de_triagem_nao_oferece_modo_nao_triavel`.

---

## Prioridade 3 — `ai_providers.py` (483 linhas, **59%**)

O grosso do descoberto são os caminhos de **streaming de cada provider**
(linhas 332-369, 504-619, 702-765). Os testes existentes cobrem o Perplexity;
Anthropic, OpenAI e Google streaming estão quase todos descobertos.

Foi mexido em 8 pontos de extração na mudança de citações de 2026-09-16 — e se
o streaming da Anthropic tivesse quebrado, provavelmente nenhum teste falharia.

**O que testar:** para cada provider, um stream fake emitindo a forma real dos
eventos, afirmando que texto, tokens e citações (com título) saem corretos. O
molde existe em `tests/test_perplexity_streaming.py`.

**Esforço:** ~1 dia. **Ganho:** 59% → ~75% num arquivo que toda resposta atravessa.

> **FEITO em 2026-09-16 — 59% → 80%**, em `tests/test_providers_streaming.py` (19).
>
> Um arquivo por provedor porque as formas de evento não se parecem: Anthropic
> fecha em `message_delta`, OpenAI em `response.completed`, Google em
> `finishReason` dentro do candidato. O que quebra é o detalhe de cada uma.
>
> Além do texto/tokens/fontes, ficou travado que a **Responses API usa
> `max_output_tokens`** — nem `max_tokens` nem `max_completion_tokens`. Três
> nomes para a mesma ideia em três APIs da mesma empresa é exatamente onde
> nascem os 400 silenciosos do item 2.

---

## Prioridade 4 — Frontend: a mecânica de pastas

| Arquivo | Cobertura | O que mora ali |
|---|---|---|
| `FolderRow.tsx` | **27%** | drag-and-drop, menu, renomear, entrar na pasta |
| `ConvItem.tsx` | 40% | seleção múltipla, arrastar conversa |
| `DropZoneNoPasta.tsx` | **0%** | tirar conversa da pasta |

Pasta aqui não é organização visual: ela injeta a **evolução do paciente na
íntegra em toda mensagem**. Um bug que mova a conversa para a pasta errada
muda a resposta clínica, e muda **em silêncio** — nada na tela denuncia.

**O que NÃO priorizar:** `src/api` (8,8%) é camada de `fetch`, onde teste
unitário rende pouco; `ProfileModal.tsx` (3%) é formulário de perfil sem
consequência clínica. Deixar baixo é decisão, não descuido.

**Esforço:** ~meio dia. **Ganho:** 27% → ~65% em `FolderRow`.

> **FEITO em 2026-09-16 — `FolderRow` 27% → 91%, `DropZoneNoPasta` 0% → 100%**,
> em `FolderRow.test.tsx` (15) e `DropZoneNoPasta.test.tsx` (4).
>
> A fronteira que os testes protegem é `dragOver` vs `drop`: passar por cima a
> caminho de outro lugar não pode mover nem remover conversa de pasta.
>
> **Melhoria de acessibilidade que saiu junto:** os botões de abrir a pasta e de
> abrir o menu não tinham nome acessível — um leitor de tela anunciava só
> "botão", e são três botões visualmente idênticos na mesma linha. Ganharam
> `aria-label`, `aria-expanded` e `aria-haspopup`. Foi o teste que expôs isso:
> não havia como selecioná-los a não ser por posição.
>
> `ConvItem.tsx` segue em 40% — é o próximo candidato natural desta área.

---

## Prioridade 5 — `agregador_service.py` (53%) e `dea_router.py` (62%)

Os dois têm teste (`test_agregador_resiliencia.py`, 4 arquivos de DEA), e o
descoberto é majoritariamente caminho de erro e o fluxo de streaming paralelo.
Risco menor: o Agregador está sendo descontinuado da interface (as conversas já
são ocultadas), e o DEA é app público sem dado clínico de paciente.

**Recomendação:** só depois dos quatro acima. Para o Agregador, vale confirmar
antes se ele continua no produto — cobrir o que vai sair é desperdício.

---

## Ordem sugerida

1. ~~**PharmaDB**~~ — **feito** (0% → 52%), com um achado clínico aberto
2. ~~**Payload dos callers da OpenAI**~~ — **feito** (triagem 98%, extrator 89%)
3. ~~**Streaming dos providers**~~ — **feito** (59% → 80%)
4. ~~**Pastas no front**~~ — **feito** (`FolderRow` 91%, `DropZone` 100%)
5. *(reavaliar)* Agregador e DEA — **próximo**, depois de confirmar o destino do
   Agregador

### Resultado de 2026-09-16

Backend **73% → 78%**, frontend **53% → 60%**, de 1184 para **1257 testes** de
backend e de 134 para **175** de front. Os quatro itens do plano foram
executados na mesma sessão, mais dois alvos escolhidos depois:

| Alvo | Antes | Depois |
|---|---|---|
| `pharmadb_service.py` | 0% | 52% |
| `triage_service.py` | 50% | 98% |
| `medication_extractor.py` | 34% | 89% |
| `ai_providers.py` | 59% | 80% |
| `orquestrador_service.py` | 61% | **85%** |
| `FolderRow.tsx` | 27% | 91% |
| `ConvItem.tsx` | 40% | 96% |
| `ChatView.tsx` | 56% | 66% |
| `DropZoneNoPasta.tsx` | 0% | 100% |

**`orquestrador_service.py`** (`tests/test_orquestrador_rotas_pharma.py`, 12):
o roteamento PharmaDB e sua degradação. O que ficou travado é uma **assimetria
deliberada** — interação medicamentosa cai para `CLINICAL_REASONING` (a pergunta
é sobre risco, o modelo tem o que dizer); bula/receita/genérico caem para
`QUICK_SEARCH` (a pergunta é factual, raciocinar seria inventar). Nos dois casos
com aviso no início do texto e `is_fallback=True`. Um teste específico
(`test_os_dois_fallbacks_usam_modos_diferentes`) existe para que ninguém
"uniformize" isso sem ler o porquê.

**O que vale mais que os números:** dois achados de comportamento que nenhum
teste anterior pegava — o falso verde do PharmaDB (aberto, aguardando decisão) e
a validação do PubMed que nunca funcionou (corrigida).

Os itens 1 e 2 somados são ~1,5 dia e cobrem o que, se quebrar, o médico não
percebe. Se houver tempo para só uma coisa, é o item 1.

## O que não fazer

- **Não perseguir um número.** Subir `src/api` de 8,8% para 80% mexeria bastante
  no total e não preveniria nenhum bug real.
- **Não cobrir o que vai sair.** Confirmar o destino do Agregador antes.
- **Não escrever teste que repete a implementação.** Os bons testes deste repo
  afirmam *invariantes* ("renomear não apaga a evolução"), não chamadas.
