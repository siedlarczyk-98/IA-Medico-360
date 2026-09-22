# RASCUNHO — Termos de Uso do Médico 360

> **NÃO ESTÁ PRONTO PARA PUBLICAR.** Escrito por quem conhece o código, para a
> revisão jurídica partir do que o sistema faz. **[DECISÃO]** marca escolha de
> negócio ou de direito, não redação.
>
> Fatos técnicos: `docs/inventario-tratamento-de-dados.md`.
> Privacidade é documento separado: `RASCUNHO-politica-de-privacidade.md`.

---

## O ponto que os termos atuais não cobrem

Os Termos vigentes são do **Paciente 360®** e tratam de uma plataforma de
conteúdo. O Médico 360 é outra coisa: uma ferramenta que **gera texto clínico
por inteligência artificial**, para um profissional que vai decidir conduta a
partir dele.

A cláusula central que falta é a de **responsabilidade clínica**. Sem ela, os
termos não protegem ninguém — nem a Active, nem o médico, nem o paciente.

## 1. O que é o Médico 360

Ferramenta de apoio à decisão clínica para profissionais de medicina, composta
de: assistente de perguntas clínicas com IA, calculadoras médicas, resumo de
publicações científicas, e localizador de desfibriladores.

**[DECISÃO]** Nomear os módulos formalmente e dizer se os termos cobrem os
quatro (hoje o aceite é um só para todos).

## 2. Quem pode usar

**[DECISÃO]** Definir e declarar. A proposta é: profissionais de medicina com
registro ativo, e estudantes de medicina, maiores de 18 anos.

Hoje o sistema **não verifica idade** e a verificação de registro vem do
ambiente de ensino (grupos `[CFM]`), não de consulta direta ao Conselho a cada
acesso.

**[DECISÃO]** Se estudantes podem usar, os termos precisam dizer o que muda para
eles — não podem prescrever.

## 3. Natureza do serviço — a cláusula que falta

Este é o núcleo do documento. A redação abaixo é a intenção; a forma é com o
jurídico.

**3.1** O Médico 360 é ferramenta de **apoio**. Não exerce medicina, não
diagnostica, não prescreve e não substitui o julgamento clínico.

**3.2** As respostas são geradas por **modelos de linguagem**, que produzem
texto plausível e **podem conter erro**, inclusive erro que aparenta correção:
dose incorreta, referência inexistente, contraindicação omitida.

**3.3** A decisão clínica é **exclusivamente do profissional**, que responde por
ela perante o paciente e o Conselho. Cabe a ele conferir toda informação antes
de usar.

**3.4** As referências científicas apresentadas devem ser verificadas na fonte.
*(Nota técnica: há verificação automática de citações contra o PubMed, mas ela
não cobre tudo e não substitui a conferência.)*

**3.5** A checagem de interações medicamentosas depende de base de terceiro e
pode estar indisponível ou incompleta. **Ausência de alerta não significa
ausência de interação.**

**[DECISÃO]** Verificar se há exigência do CFM sobre uso de IA em apoio à
decisão que precise ser referida aqui (Resolução CFM 2.314/2022 trata de
telemedicina; avaliar o que se aplica).

## 4. Obrigações do usuário

**4.1** Usar dentro da sua competência profissional e da regulamentação do CFM.

**4.2** **Não inserir dados que identifiquem pacientes** — nome, CPF, documento,
contato, endereço. A plataforma filtra automaticamente o que consegue, mas o
filtro é imperfeito e **não cobre imagens**.

**[DECISÃO]** Esta é obrigação do usuário, mas a plataforma **aceita anexo de
imagem** (foto de exame, de receita) e a envia sem filtro ao provedor de IA.
Pedir que ele não faça o que a ferramenta oferece é frágil. Resolver o problema
técnico é o caminho melhor.

**4.3** Não compartilhar credenciais. A conta é pessoal e intransferível.

**4.4** Não usar para fins ilícitos, nem tentar contornar limites técnicos.

## 5. Conteúdo do usuário

**[DECISÃO]** Definir a titularidade do que o médico escreve e do que é gerado.
Proposta: o conteúdo é do médico; a Active tem licença limitada para operar o
serviço (armazenar, processar, enviar aos provedores necessários).

## 6. Disponibilidade

Serviço prestado "como está", sem garantia de disponibilidade ininterrupta.
Depende de terceiros (provedores de IA, bases de dados) que podem falhar.

**[DECISÃO]** Definir se há SLA. Hoje não há.

## 7. Limitação de responsabilidade

**[DECISÃO]** Toda esta seção é jurídica. O que o redator precisa saber:

- o produto influencia **decisão clínica**, com risco a terceiros (pacientes)
  que não são parte do contrato;
- limitação de responsabilidade tem eficácia reduzida quando há dano a terceiro;
- o CDC pode incidir se houver contratação individual por profissional.

## 8. Preço e contratação

**[DECISÃO]** Não determinado pelo código. Hoje o acesso vem por convite e pelo
ambiente de ensino. Definir: é gratuito? incluído em outro produto? assinatura
avulsa? Há direito de arrependimento (art. 49 do CDC) se houver contratação
direta.

## 9. Encerramento

O usuário pode excluir a conta a qualquer momento pela própria plataforma, o que
apaga seu conteúdo (ver Política de Privacidade).

**[DECISÃO]** Definir as hipóteses de encerramento pela Active e o aviso prévio.

## 10. Alterações

**[DECISÃO]** Definir como comunicar revisão dos documentos.

*Nota técnica:* a plataforma **já registra** a versão aceita por cada usuário e
sabe dizer quem aceitou versão antiga. Hoje, por decisão explícita de código,
uma revisão **não** força novo aceite — a base inteira continuaria válida. Se o
jurídico entender que revisão material exige novo aceite, é uma linha de código:
`aceitou_termos` em `app/services/consent_service.py`.

## 11. Foro e lei aplicável

Lei brasileira. **[DECISÃO]** Foro.

---

## Checklist para a revisão jurídica

- [ ] Quem pode usar (registro ativo? estudantes? idade mínima)
- [ ] Redação final da responsabilidade clínica (seção 3)
- [ ] Exigências do CFM aplicáveis a apoio por IA
- [ ] Titularidade do conteúdo e licença de uso
- [ ] Limitação de responsabilidade com risco a terceiro
- [ ] Modelo comercial e direito de arrependimento
- [ ] Hipóteses de encerramento pela Active
- [ ] Revisão dos documentos exige novo aceite?
- [ ] Foro
- [ ] **Anexo de imagem sem filtro** — obrigação do usuário ou correção técnica?
