# Migrations históricas (pré-baseline)

Estas 21 migrations foram aplicadas na produção entre o início do projeto e
2026-08-19. Estão aqui como **registro histórico**, fora do caminho lido pelo
Alembic (`script_location` aponta só para `alembic/versions/`).

## Por que saíram de circulação

A cadeia nunca aplicou num banco vazio. A `001` era a raiz e criava apenas
`semantic_cache`; nenhuma migration criava `users`, `conversations` ou
`interactions` — o schema original nasceu de um `Base.metadata.create_all()`
fora do Alembic, e estas 21 eram `ALTER`s em cima de tabelas que não existiam
do ponto de vista do Alembic.

Consequência prática: era impossível reconstruir o banco do zero, criar um
ambiente de staging ou dar a um desenvolvedor novo um banco local sem copiar
dump de produção.

`000_baseline` substitui todas elas, capturando o schema completo no estado em
que estava. Bancos que já existiam foram marcados com `alembic stamp
000_baseline`, sem re-executar nada.

## Não use estes arquivos

Não devolva nenhum deles para `alembic/versions/`. A baseline já contém o
resultado final de todos. Eles servem só para consultar como uma coluna ou
índice específico surgiu.
