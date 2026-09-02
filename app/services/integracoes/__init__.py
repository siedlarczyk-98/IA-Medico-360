"""
Clientes de sistemas externos.

O que mora aqui é código cujo trabalho é FALAR COM ALGUÉM DE FORA — a API da
Curseduca, o PubMed, o PharmaDB, os provedores de IA. Não regra de negócio.

Estavam soltos entre os 38 arquivos de `app/services/`, misturados com serviços
de domínio, e por isso o padrão que eles compartilham ficava invisível: todos
precisam de timeout, disjuntor (`app.core.circuit_breaker`), e uma decisão
explícita sobre o que fazer quando o outro lado não responde. Essa decisão é
diferente em cada um e sempre deliberada — a Curseduca é fail-closed porque a
dúvida ali é sobre direito de acesso; o CFM será fail-open porque a dúvida é
sobre um atributo de perfil.

Ao acrescentar um cliente aqui, copie a forma do `curseduca_service`: função de
fetch isolada, disjuntor nomeado, timeout explícito, e o docstring dizendo o que
acontece quando a integração cai.
"""
