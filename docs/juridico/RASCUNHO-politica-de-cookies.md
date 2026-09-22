# RASCUNHO — Política de Cookies do Médico 360

> **NÃO ESTÁ PRONTO PARA PUBLICAR.** Insumo para revisão jurídica.
> Fatos em `docs/inventario-tratamento-de-dados.md`.

---

## O caso mais simples dos três

A política de cookies vigente (do Paciente 360, revisada em 26/07/2024) fala em
**"cookies de publicidade e de terceiros"** para "fornecer conteúdo relevante".

No Médico 360 **isso não existe**. Varredura nos seis frontends por Google
Analytics, Google Tag Manager, Hotjar, PostHog, Mixpanel, Meta Pixel, Microsoft
Clarity, AdSense e DoubleClick: **nenhuma ocorrência**.

Ou seja: o documento atual descreve um rastreamento mais invasivo do que o que
o produto faz. Corrigir aqui é deixar o texto **menos** assustador, não mais.

## 1. O que o Médico 360 usa de fato

### 1.1 Cookie de sessão (estritamente necessário)

Um único cookie, `medico360_session`, com o token de autenticação. É `httponly`
(o JavaScript da página não o lê), `secure` em produção, e expira com a sessão.

Sem ele não há como manter o médico logado. **Cookie estritamente necessário
dispensa consentimento prévio** — o que elimina a necessidade de banner.

**[DECISÃO]** Confirmar esse entendimento com a assessoria.

### 1.2 Armazenamento local (`localStorage`)

Os aplicativos também guardam o token no `localStorage` do navegador — o backend
aceita as duas formas (o cookie ou o cabeçalho `Authorization`), porque dentro
do iframe do ambiente de ensino nem sempre o cookie viaja.

Além do token, ficam ali preferências de interface (tema, barra lateral
recolhida, filtros).

Tecnicamente não é cookie, mas a política deve mencionar: o titular não
distingue, e a finalidade é a mesma. Nada disso sai do navegador.

### 1.3 Terceiro: Intercom (suporte)

O widget de chat de suporte é carregado de `widget.intercom.io` e define
cookies próprios. É o **único** terceiro que roda no navegador.

**[DECISÃO]** O Intercom é funcional (suporte) ou deve ser tratado como
opcional, com consentimento? Depende de ele fazer ou não perfilamento — o que
é configuração da conta Intercom, não do nosso código.

## 2. O que NÃO é usado

Dizer isto explicitamente vale mais que a lista do que é usado:

- não há cookies de **publicidade**;
- não há cookies de **rastreamento entre sites**;
- não há ferramenta de **analytics de comportamento**;
- os dados **não** são vendidos nem compartilhados para marketing.

## 3. Como o usuário controla

Bloquear o cookie de sessão impede o login — não há como usar a plataforma sem
ele. As instruções por navegador podem ser mantidas como estão no documento
atual.

---

## Checklist para a revisão jurídica

- [ ] Cookie estritamente necessário dispensa banner? (entendimento atual: sim)
- [ ] Intercom: funcional ou sujeito a consentimento?
- [ ] Mencionar `localStorage` junto dos cookies?
- [ ] Remover toda a menção a publicidade (não se aplica)
