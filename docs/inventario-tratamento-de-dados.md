# Inventário de tratamento de dados pessoais

Levantado em 2026-09-22 direto do código, para embasar a revisão dos documentos
legais (ver `docs/pendencias.md`, "Termos de uso"). **Não é a política de
privacidade** — é o insumo factual para quem for redigi-la.

Cada afirmação aqui tem `arquivo:linha` como prova. Onde o código não responde,
está escrito "não determinado" em vez de um palpite.

## Resumo para quem vai redigir

O que a política publicada hoje afirma e o código contradiz:

| A política diz | O código faz |
| --- | --- |
| "não compartilha com terceiros" | envia texto clínico a 5 provedores de LLM |
| lista 1 operador (AWS Brasil) | há ~10 terceiros com acesso a algum dado |
| nada sobre IA | o produto **é** uma aplicação de IA |
| nada sobre retenção | há expurgo de 30/180 dias para parte dos dados |

## 1. Dados coletados e armazenados

**Do médico (titular):** e-mail, nome, telefone, CRM+UF, especialidade(s),
estágio de carreira, profissão, `waid_uuid` (id no LMS), data de matrícula.
`app/models/models.py:70-118`

**Conteúdo clínico produzido pelo médico** — é o volume principal:
- `interactions.prompt_text` — a pergunta clínica. `app/models/models.py:242`
- `interaction_responses.response_text` — a resposta. `app/models/models.py:274`
- `folders.clinical_context` — a evolução do paciente, texto livre. É o campo
  mais sensível da base. `app/models/models.py:186`
- `message_embeddings.content` — trechos de pergunta e resposta, vetorizados.
  `app/models/models.py:463`
- `calculator_executions.inputs` — entrada clínica das calculadoras.
  `app/models/calculators.py:171`
- `file_extractions` — anexos: texto extraído E **a imagem crua em base64**.
  `app/models/models.py:483-487`

**Metadados de auditoria:** `audit_logs` e `consent_logs` guardam `ip_address`
(INET) e `user_agent`. `app/models/models.py:360-361,375-382`

**Onde ficam os anexos:** no próprio Postgres, não em S3 — não há boto3 nem
bucket no backend.

## 2. Terceiros que recebem dados (subprocessadores)

| Terceiro | O que recebe | Mascarado antes de sair? |
| --- | --- | --- |
| Anthropic | prompt, histórico, **imagem crua** | texto sim, **imagem não** |
| OpenAI | prompt, histórico, embeddings, triagem, 3000 chars da resposta | texto sim |
| Google (Gemini) | prompt, histórico, imagem | texto sim, imagem não |
| Perplexity | prompt, histórico | sim |
| Maritaca (Sabiá/Data Ocean) | prompt, histórico | sim |
| Arize Phoenix | **prompt e resposta, 2000 chars cada** | só o que o DLP já tirou |
| Sentry | id do usuário, rota, stack | sim, scrubbing agressivo |
| SendGrid | e-mail e nome do destinatário | não (é o canal) |
| Intercom | id, e-mail e nome — enviados pelo **browser** | não |
| Curseduca/Waid | e-mail (é a chave da consulta) | não |
| PharmaDB | só nomes de fármacos | não se aplica |
| PubMed/NCBI | termos de busca + e-mail do operador | não se aplica |
| Redis | cache de triagem (prompt) e de membro (e-mail) | prompt sim, e-mail não |
| Railway/Postgres | tudo que está no banco | — |

Nenhum analytics ou pixel: varredura por gtag/GA/Hotjar/PostHog/Mixpanel/
Meta/Clarity nos seis frontends não achou nada. O único terceiro no browser é
o Intercom.

## 3. O que o DLP mascara antes de sair

Regex: CPF, RG, cartão SUS, e-mail, telefone, CEP, logradouro, e nome com
palavra-gatilho ("paciente X", "Dr. Y"). `app/middleware/dlp.py:126-231`
NER (spaCy): nome de pessoa sem gatilho. `app/middleware/ner.py:138-154`

**NÃO mascara:** data de nascimento, idade, CRM, CNPJ, número de prontuário,
número de convênio — e **imagens**.

Roda na escrita (com NER), nas respostas do modelo (só regex, para não comer
nome de fármaco e epônimo) e de novo na saída para o provedor, como rede de
segurança. Não há re-identificação: o placeholder é definitivo.

## 4. Retenção e exclusão

Expurgo automático, diário (`app/services/data_subject_service.py:41-44`):
- imagem crua: **30 dias** (a linha fica, o base64 vira NULL)
- texto extraído de arquivo: **180 dias**
- cache semântico: **30 dias**

**Sem prazo nenhum** (ficam enquanto a conta existir): conversas, perguntas,
respostas, embeddings, contexto clínico das pastas, execuções de calculadora,
logs de auditoria e de consentimento.

O titular consegue **exportar** (`GET /auth/me/export`) e **excluir**
(`DELETE /auth/me`, com confirmação por digitação do nome). Na exclusão,
`audit_logs` e `consent_logs` são **anonimizados** (perdem user_id, IP e
user-agent) em vez de apagados — o registro de consentimento precisa sobreviver
para provar que houve consentimento enquanto os dados foram tratados.

## 5. Consentimento

Um tipo obrigatório (`termos_e_privacidade`), gravado com IP, user-agent e a
versão do documento vigente. Histórico nunca é sobrescrito. Revogar os termos é
recusado — o caminho é excluir a conta.
`app/services/consent_service.py`

Um segundo tipo (`uso_dados_anonimizados`) está declarado mas **não é coletado**:
só passa a existir quando a monetização existir, em checkbox próprio.

## 6. Lacunas que a redação precisa saber

1. **Imagem de exame/receita sai sem mascaramento nenhum** para Anthropic e
   Google. O `DlpEnforcingProvider` sanitiza `prompt` e `history` e repassa
   `image_content` intacto. `app/services/integracoes/ai_providers.py:1172,1198`
   No upload, a imagem vai à Anthropic para descrição **antes** de qualquer DLP.
   `app/services/file_extractor_service.py:328-339`
2. **Data de nascimento não é mascarada**, embora o docstring do
   `sanitize_prompt_async` prometa "data". Não há padrão de data nos filtros.
   `app/middleware/dlp.py:126-231,247`
3. **Formulários de landing page sobrevivem à exclusão da conta** com nome,
   e-mail, telefone e respostas — só perdem o vínculo. Marcado como "PENDENTE DE
   DECISÃO" no próprio código. `app/services/data_subject_service.py:95-105`
4. **Nada sobre menores**: não há verificação de idade nem tratamento
   diferenciado. O público é médico, mas isso não está declarado em lugar nenhum.
5. **Não há opt-out de treinamento** configurado em nenhum provedor de LLM. As
   políticas de retenção dos provedores não estão refletidas no código.
6. **Região de hospedagem não determinada** pelo código. A política atual afirma
   AWS Brasil; o deploy é Railway. Confirmar onde o Postgres roda de fato —
   importa para transferência internacional (LGPD art. 33).
