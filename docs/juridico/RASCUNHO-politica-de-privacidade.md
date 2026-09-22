# RASCUNHO — Política de Privacidade do Médico 360

> **ESTE DOCUMENTO NÃO ESTÁ PRONTO PARA PUBLICAR.**
>
> Foi escrito por quem conhece o código, não por quem conhece a lei. Serve para
> que a revisão jurídica comece de um texto que descreve **o que o sistema
> realmente faz**, em vez de começar do zero ou de um documento de outro
> produto.
>
> Os fatos técnicos estão em `docs/inventario-tratamento-de-dados.md`, com
> `arquivo:linha` para cada afirmação. Se alguma frase daqui divergir de lá,
> **o inventário é que vale** — ele foi conferido no código.
>
> As passagens marcadas **[DECISÃO]** não são redação: são escolhas de negócio
> ou de direito que alguém precisa tomar antes de publicar.

---

## Por que não dá para continuar com os documentos do Paciente 360

Os três documentos publicados hoje (Termos, Privacidade e Cookies) tratam do
**Paciente 360®**. A expressão "Médico 360" não aparece em nenhum deles.

Além do nome, há uma divergência de fato. A Política de Privacidade vigente diz:

> "A Active não compartilha com terceiros os Dados Pessoais fornecidos pelo
> Usuário através do acesso à Plataforma, exceto se: (...)"

e cita **um** operador (AWS Brasil). O Médico 360 envia conteúdo clínico a
**cinco provedores de modelos de linguagem**, além de outros cinco serviços.
Nenhum documento menciona inteligência artificial.

---

## 1. Quem trata os dados

Active Metodologias Ativas de Ensino, CNPJ 23.903.127/0001-16, Rua Borges Lagoa
1083, conj. 44, Vila Clementino, São Paulo/SP, CEP 04038-032.

**[DECISÃO]** Confirmar se a controladora do Médico 360 é a mesma pessoa
jurídica do Paciente 360. O código não responde isso, e os e-mails saem de
`noreply@medico360.com.br` enquanto a documentação está em
`docs.paciente360.com.br`.

**[DECISÃO]** Indicar o encarregado (DPO) e um canal de contato — LGPD art. 41.
Não há nada disso no produto hoje.

## 2. Quem é o titular, e o que é dado de terceiro

O usuário do Médico 360 é **médico**. Boa parte do que ele digita descreve
**pacientes dele**, que não são usuários da plataforma e nunca a acessaram.

Isso precisa estar dito com todas as letras, porque muda o enquadramento:
- em relação ao médico, a Active trata dados como **controladora**;
- em relação ao paciente descrito, o médico é quem tem a relação clínica.
  **[DECISÃO]** definir juridicamente o papel da Active aqui (operadora do
  médico? controladora conjunta?). É a decisão mais importante do documento e a
  que mais muda as obrigações.

Dados de saúde são **sensíveis** (LGPD art. 11), o que restringe as bases legais
disponíveis.

## 3. Que dados são tratados

**Do médico:** e-mail, nome, telefone, CRM e UF, especialidade, estágio de
carreira, profissão, identificador no ambiente de ensino, data de matrícula.

**Conteúdo produzido pelo médico:**
- as perguntas clínicas que ele escreve;
- as respostas geradas;
- a evolução clínica que ele registra nas pastas de paciente;
- os valores que digita nas calculadoras;
- os arquivos que anexa (PDF, DOCX, XLSX) e **as imagens** (JPEG, PNG, WEBP),
  como fotos de exames e receitas.

**Registros técnicos:** endereço IP e user-agent, guardados nos registros de
auditoria e de consentimento.

**Preferências:** temas e palavras-chave do módulo de notícias, modelos
preferidos, ajustes de interface.

## 4. Para que são usados

- responder às perguntas clínicas (é a finalidade central do produto);
- manter o histórico de conversas e o contexto das pastas;
- selecionar e enviar o resumo de notícias, quando o médico pede;
- autenticar e manter a sessão;
- segurança, auditoria e investigação de incidentes;
- suporte ao usuário.

**O que NÃO é feito hoje:** os dados **não** são usados para publicidade, não
são vendidos, e não há analytics de comportamento (nenhum Google Analytics,
Hotjar, Meta Pixel ou equivalente está instalado — verificado nos seis
frontends).

**[DECISÃO]** Existe uma intenção registrada de monetizar insights anonimizados
(RN-DATA-001). O código já separa esse consentimento, mas **ele não é coletado**.
Decidir se o documento deve mencionar isso desde já ou só quando existir.

## 5. Com quem os dados são compartilhados

Esta é a seção que falta por inteiro nos documentos atuais.

### 5.1 Provedores de modelos de linguagem

Para gerar a resposta clínica, o conteúdo da pergunta é enviado a um destes
provedores, conforme o modo escolhido:

| Provedor | País |
| --- | --- |
| Anthropic | EUA |
| OpenAI | EUA |
| Google | EUA |
| Perplexity | EUA |
| Maritaca AI | Brasil |

Isso caracteriza **transferência internacional** (LGPD art. 33) para os quatro
primeiros. **[DECISÃO]** Indicar a base da transferência — cláusulas-padrão,
garantias contratuais, ou o que a assessoria entender aplicável. Não há nada
contratado refletido no código.

**[DECISÃO]** Verificar e declarar a política de **treinamento** de cada
provedor. Não há configuração de opt-out no código hoje. Contratos de API
costumam não usar o conteúdo para treino, mas isso precisa ser confirmado e
dito.

### 5.2 Outros operadores

| Serviço | Finalidade | O que vê |
| --- | --- | --- |
| Railway | hospedagem e banco | tudo que está armazenado |
| Arize Phoenix | observabilidade de IA | trechos de pergunta e resposta (até 2.000 caracteres cada) |
| Sentry | monitoramento de erros | identificador do usuário, rota, rastro de erro |
| SendGrid | envio de e-mail | e-mail e nome do destinatário |
| Intercom | suporte por chat | identificador, e-mail e nome |
| Curseduca/Waid | login pelo ambiente de ensino | e-mail |
| PharmaDB | checagem de interações | nomes de medicamentos |
| PubMed/NCBI | referências científicas | termos de busca |

**[DECISÃO]** Confirmar a **região de hospedagem** do Railway e do banco. A
política atual afirma AWS Brasil; o código não diz onde roda. Se não for Brasil,
é mais uma transferência internacional a declarar.

## 6. Proteção aplicada antes do envio a terceiros

Antes de sair da plataforma, o texto passa por um filtro automático que
substitui por marcadores genéricos: CPF, RG, cartão SUS, e-mail, telefone, CEP,
endereço, e nomes de pessoas (tanto os precedidos de "paciente"/"Dr." quanto os
detectados por reconhecimento de entidades).

**É preciso ser honesto sobre os limites, e há três:**

1. **Imagens não são filtradas.** O filtro trabalha só sobre texto. Uma foto de
   receita ou de exame com o nome do paciente é enviada **como está** ao
   provedor de IA.
   **[DECISÃO]** corrigir antes de publicar, ou declarar a limitação. Declarar
   uma limitação que se pode corrigir é uma escolha ruim.
2. **Data de nascimento e idade não são filtradas.**
3. O filtro é automático e, como todo filtro, pode falhar. A orientação ao
   médico de não digitar dados identificáveis continua valendo — e
   **[DECISÃO]** talvez deva estar nos Termos como obrigação do usuário.

## 7. Por quanto tempo

| Dado | Prazo |
| --- | --- |
| Imagens anexadas | 30 dias |
| Texto extraído de arquivos | 180 dias |
| Conversas, perguntas e respostas | enquanto a conta existir |
| Pastas e evolução clínica | enquanto a conta existir |
| Registros de auditoria e consentimento | mantidos após a exclusão, anonimizados |

**[DECISÃO]** Definir prazo para o conteúdo clínico. Hoje ele é mantido
indefinidamente, o que é difícil de justificar diante do princípio da
necessidade (art. 6º, III).

## 8. Direitos do titular

O médico pode, pela própria plataforma:
- **acessar e exportar** tudo que é dele, em JSON (`/auth/me/export`);
- **excluir a conta**, com confirmação.

Na exclusão, o conteúdo clínico, as conversas, os arquivos e as preferências são
apagados. Os registros de consentimento e auditoria **permanecem, anonimizados**
— sem identificador, sem IP e sem user-agent —, porque é o que comprova que
houve consentimento válido enquanto os dados foram tratados.

**[DECISÃO]** Os formulários das páginas de captação (nome, e-mail, telefone,
faturamento) **sobrevivem à exclusão da conta**, perdendo só o vínculo. O
próprio código marca isso como pendente de decisão.

## 9. Consentimento

O aceite é registrado com data, IP, user-agent e a versão do documento vigente,
e o histórico nunca é sobrescrito.

**[DECISÃO]** O consentimento é hoje **um só**, cobrindo os quatro aplicativos
(chat, calculadoras, notícias, DEA). Quem entra pelo módulo de notícias aceita o
mesmo documento de quem usa o chat clínico, ainda que nunca o abra. Decidir se
isso é adequado ou se os usos devem ser separados.

**[DECISÃO]** Revisar se **consentimento** é a base legal correta para o
tratamento do conteúdo clínico, ou se cabe outra hipótese do art. 11.

## 10. Menores

Não há verificação de idade nem tratamento diferenciado no produto. O público é
médico — logo, maior de idade —, **[DECISÃO]** mas isso deve estar declarado
como restrição de uso nos Termos.

---

## Checklist para a revisão jurídica

- [ ] Controladora: mesma PJ do Paciente 360?
- [ ] Encarregado (DPO) e canal de contato
- [ ] Papel da Active quanto ao dado do paciente descrito pelo médico
- [ ] Base legal para dado sensível (art. 11)
- [ ] Base para transferência internacional (art. 33) — 4 provedores nos EUA
- [ ] Política de treinamento de cada provedor de IA
- [ ] Região de hospedagem (Railway/Postgres)
- [ ] Prazo de retenção do conteúdo clínico
- [ ] Imagem sem filtro: corrigir ou declarar
- [ ] Formulários de captação que sobrevivem à exclusão
- [ ] Aceite único para os quatro apps
- [ ] Restrição de uso a maiores / profissionais de saúde
- [ ] Obrigação do médico de não inserir dado identificável
