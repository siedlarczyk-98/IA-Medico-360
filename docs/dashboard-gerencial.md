# Dashboard gerencial — Metabase

Preparado em 2026-09-28. Público do dashboard: diretoria e líderes de área. Público
deste documento: quem vai ligar o Metabase ao banco e montar os painéis.

**A regra:** o Metabase lê o schema `gerencial` e nada mais. O banco guarda texto
clínico (pergunta, resposta, anexo extraído, embeddings) e dados pessoais (e-mail,
telefone, CRM, IP). Com o MCP do Metabase, o resultado de toda consulta passa por
um LLM. Então o que sai do banco já sai agregável e sem conteúdo.

Criado pela migration `016_schema_gerencial`. As garantias estão travadas em
`tests/test_gerencial_views.py`: uma marca escrita em todo campo livre e pessoal
não pode aparecer em view nenhuma, e o role não pode ler as tabelas do app.

---

## Subir

A ordem é a mesma de `docs/subir-para-producao.md`: **backup → migration → resto**.
A 016 só cria coisas novas e não altera tabela, então o código em produção não
depende dela.

1. **Backup** (dump manual, igual às outras subidas).
2. **Migration:** `alembic upgrade head` com `DATABASE_URL` apontando para produção.
   Ela cria o schema, as 10 views e o role `gerencial_leitura` (sem login).
3. **Login do Metabase**, à mão, fora do repositório:

   ```sql
   CREATE ROLE metabase LOGIN PASSWORD '<gerar, guardar no cofre>' IN ROLE gerencial_leitura;
   ```

   Conferir que ele não enxerga as tabelas do app. As duas linhas abaixo têm que
   dar `permission denied`:

   ```sql
   SET ROLE metabase;
   SELECT 1 FROM public.users LIMIT 1;
   SELECT 1 FROM public.interactions LIMIT 1;
   RESET ROLE;
   ```

4. **Conexão no Metabase** (Admin → Databases → Add):
   - usuário `metabase`, SSL ligado;
   - em *Schemas*, escolher **Only these…** → `gerencial`;
   - host: se o Metabase roda no mesmo projeto Railway, usar o endereço da rede
     privada (`*.railway.internal`). Se roda fora, é preciso o proxy TCP público do
     Postgres. Nesse caso a senha forte e o role restrito são a única barreira.
5. **MCP:** a chave de API do Metabase usada pelo MCP deve pertencer a um grupo que
   só tem acesso a essa conexão.

**Reverter:** `DROP SCHEMA gerencial CASCADE` resolve, ou basta revogar o login
(`DROP ROLE metabase`). Não é preciso `alembic downgrade`.

---

## As views

Nenhuma view expõe texto livre, e-mail, nome, telefone, CRM, IP ou user-agent.
`usuario_ref` é um pseudônimo estável: o mesmo médico tem o mesmo valor em todas
as views, o que permite contar usuários distintos e montar coortes.

`dia` é a data em horário de Brasília. `criado_em` fica em UTC.

| View | Uma linha por | Serve para |
|---|---|---|
| `usuarios` | conta | base cadastrada, especialidade, origem (Waid ou direto), onboarding |
| `perguntas` | pergunta ao assistente | volume, modo, status, tempo de resposta, custo, anexo, alerta de fármaco |
| `respostas_modelo` | chamada de modelo | custo e erro por modelo/provedor, fallback |
| `acessos` | entrada pela Waid | quem abriu o produto (inclui quem não perguntou nada) |
| `calculadoras` | execução | calculadoras mais usadas, por especialidade |
| `noticias_artigos` | artigo | fila do redator: coletado → publicado, tentativas |
| `noticias_digest` | e-mail de digest | envios e artigos por envio |
| `noticias_favoritos` | favorito | engajamento com o feed |
| `dea_dispositivos` | DEA cadastrado | cobertura por cidade/UF, status, verificações |
| `captacao` | envio de landing page | leads por página, conversão em usuário |

## Painéis sugeridos para a diretoria

1. **Adoção**
   - Usuários ativos por semana: `usuario_ref` distintos em `perguntas`,
     `calculadoras` ou `acessos`.
   - Contas novas por semana (`usuarios.dia_cadastro`).
   - Base por especialidade.
2. **Uso**
   - Perguntas por dia, empilhadas por `modo`.
   - Perguntas por usuário ativo.
   - Percentual de perguntas feitas dentro de pasta ou com anexo.
3. **Custo**
   - Custo semanal em USD (`perguntas.custo_usd`).
   - Custo por usuário ativo.
   - Custo por provedor (`respostas_modelo`).
4. **Qualidade**
   - Tempo de resposta p50/p90.
   - Respostas que não terminaram (`status = 'em_andamento'` com mais de 10 minutos).
   - Taxa de erro e de fallback por modelo.
5. **Módulos**
   - Top calculadoras.
   - Artigos publicados por semana.
   - DEAs ativos por UF.
   - Leads por landing page.

## Ressalvas que mudam o número

- **Contas `admin` estão fora** de todas as views. Contas de teste com perfil
  `beta_user` continuam contando.
- **`perguntas.custo_usd` já é o total da pergunta.** `respostas_modelo.custo_usd`
  serve para quebrar esse total por modelo. Não somar as duas.
- **A PREVENT não aparece em `calculadoras`**: ela calcula sem gravar execução.
- **`acessos` mede só a entrada pela Waid.** O login por código de e-mail não grava
  auditoria.
- **`cache_hit` é sempre falso** enquanto o cache semântico estiver desligado.
- **Não há histórico de `user_weekly_usage`**: a tabela guarda só a semana corrente
  de cada usuário. O custo ao longo do tempo vem de `perguntas`.
- **O pseudônimo não torna o uso anônimo.** Com poucos médicos por especialidade e
  UF, `usuario_ref` + especialidade identifica a pessoa. O que as views protegem é
  o conteúdo clínico e os dados de contato, não o fato de alguém ter usado o
  produto. Não publicar painel com recorte por usuário fora da diretoria.

## Adicionar uma view

Criar numa migration nova (`CREATE VIEW gerencial.<nome> AS …`). O
`ALTER DEFAULT PRIVILEGES` da 016 já dá leitura ao role. Incluir a view nos dados do
teste e confirmar que a marca `SEGREDO` não aparece nela.

## SQL dos cards

Os 15 cards (KPIs de 7 dias, tendências semanais, custo por modelo, qualidade e módulos)
estão em `docs/dashboard-gerencial.sql`, um bloco `-- name:` por pergunta. Todos foram
validados em produção com o role `gerencial_leitura` em 2026-09-28.

## Onde está o painel

- Instância: `metabase-pro.paciente360.com.br`, banco "Médico 360 - Railway" (id 331),
  conectado com o login `metabase`.
- Coleção "Médico 360 — Gerencial" (id 1783), perguntas 13861 a 13875.
- Dashboard "Médico 360 — Painel Gerencial":
  <https://metabase-pro.paciente360.com.br/dashboard/1651>.

Ao mudar um card no Metabase, atualizar o bloco correspondente no `.sql`: o arquivo é a
fonte para recriar o painel.
