# noticias-app

Feed personalizado de destaques dos journals médicos. Roda dentro de um
`<iframe>` no LMS (Curseduca) e consome a API em `/api/v1/news/*`.

```bash
npm install
npm run dev      # http://localhost:5176
```

Variáveis (`.env.local`):

```
VITE_API_URL=http://localhost:8000
```

## Como a identidade funciona aqui

O LMS monta a URL do iframe com `?email=...`. Esse e-mail **não é a identidade** —
é a semente de uma troca: o app chama `/api/v1/auth/embed/token`, recebe um JWT
e passa a usá-lo em toda chamada.

A distinção importa. A versão anterior deste app mandava o e-mail cru como
identificador em cada requisição, o que era tolerável quando ele só listava posts
públicos do WordPress. Com feed personalizado, aceitar um e-mail informado pelo
navegador permitiria a qualquer um ler e alterar os temas de outra pessoa.

## As duas telas

**Escolha de temas** (`src/pages/TemasPage.tsx`) — aparece só na primeira visita.
Os temas vêm pré-marcados a partir da especialidade que o usuário já informou no
onboarding do app principal: ele nunca encara 50 caixas em branco. É também onde
liga o e-mail diário.

**Feed** (`src/components/HighlightsMagazine.tsx`) — hero do destaque do dia,
lista, busca, filtro por journal e favoritos.

## Três regras da interface que não são cosméticas

**A tela nunca fica vazia, e nunca mente.** Se nada casou com os temas do
usuário, o backend completa a lista com temas adjacentes à especialidade, e esses
itens vêm com `preenchimento: true`. Eles são exibidos com a etiqueta *"fora dos
seus temas"* — e o hero nunca é um deles, porque dar destaque de capa a um item
de preenchimento seria vendê-lo como relevante quando não é.

Essa flag também é lida pelo backend: item de preenchimento **nunca** dispara
e-mail. Navegar é barato, interromper é caro.

**Vazio tem dois motivos, e eles são ditos de forma diferente.** `sem_conteudo`
("não publicaram nada") e `sem_match` ("seus temas estão estreitos") produzem a
mesma tela vazia se ninguém os distinguir — e o usuário conclui que o produto
morreu.

**"Ver tudo" existe para o filtro não virar caixa-preta.** Sem essa válvula, a
primeira reclamação é "sumiu conteúdo" e não há como o usuário verificar. Pelo
mesmo motivo, cada card mostra quais temas casaram: é a resposta a "por que estou
vendo isto?".

O botão **✕** ("não é do meu interesse") grava artigo + tema + especialidade no
servidor. É a única fonte de dado real para corrigir a taxonomia depois — sem
ele, ajustar o mapeamento tema↔especialidade seria palpite.
