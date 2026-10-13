-- Cards do dashboard gerencial (Metabase). Cada bloco e uma pergunta SQL nativa.
-- Validados em producao em 2026-09-28 com o role gerencial_leitura.
-- Graficos semanais excluem a semana corrente (incompleta). Ver docs/dashboard-gerencial.md.

-- ACESSO x USO (pedido do Ruben em 2026-10-13): "com acesso" = tem conta, abriu o produto
-- pelo menos uma vez. "Usou" = pergunta ao assistente, calculadora ou noticia favoritada.
-- So entrar pela Waid e acesso, NAO uso: os cards de "ativos" deixaram de contar `acessos`.
-- Os nomes de coluna antigos (usuarios_ativos, custo_por_ativo_usd) ficaram para nao
-- quebrar a formatacao salva dos graficos.

-- KPIs de 7 dias: uma linha por janela (inicio_periodo = primeiro dia da janela), para o
-- card "smartscalar" do Metabase mostrar o valor atual e a variacao sobre os 7 dias anteriores.

-- name: kpi_ativos_7d
WITH a AS (
    SELECT usuario_ref, dia FROM gerencial.perguntas
    UNION ALL SELECT usuario_ref, dia FROM gerencial.calculadoras
    UNION ALL SELECT usuario_ref, dia FROM gerencial.noticias_favoritos
)
SELECT CASE WHEN dia > current_date - 7 THEN current_date - 6 ELSE current_date - 13 END AS inicio_periodo,
       count(DISTINCT usuario_ref) AS usuarios_ativos
FROM a WHERE dia > current_date - 14
  AND usuario_ref IN (SELECT usuario_ref FROM gerencial.usuarios)  -- so quem conta (019)
GROUP BY 1 ORDER BY 1;

-- name: kpi_perguntas_7d
SELECT CASE WHEN dia > current_date - 7 THEN current_date - 6 ELSE current_date - 13 END AS inicio_periodo,
       count(*) AS perguntas
FROM gerencial.perguntas WHERE dia > current_date - 14
GROUP BY 1 ORDER BY 1;

-- name: kpi_custo_7d
SELECT CASE WHEN dia > current_date - 7 THEN current_date - 6 ELSE current_date - 13 END AS inicio_periodo,
       round(sum(custo_usd), 2) AS custo_usd
FROM gerencial.perguntas WHERE dia > current_date - 14
GROUP BY 1 ORDER BY 1;

-- name: kpi_contas
SELECT count(*) AS total,
       count(*) FILTER (WHERE dia_cadastro > current_date - 7) AS novas_7d,
       count(*) FILTER (WHERE onboarding_completo) AS onboarding_completo
FROM gerencial.usuarios;

-- Tres niveis (migration 018): com acesso > abriu a IA > usou a IA. `gerencial.acesso`
-- tem uma linha por pessoa com acesso: membro de grupo [CFM] ou [Cursos Active] na Waid
-- (copia diaria em `membros_waid`) OU dono de conta no app.

-- name: com_acesso
-- Big number no topo (pergunta 14257). Antes da 018 contava so `usuarios` (quem abriu).
SELECT count(*) AS com_acesso FROM gerencial.acesso;

-- name: abriram_a_ia
-- Big number (pergunta 14291).
SELECT count(*) FILTER (WHERE abriu_ia) AS abriram_a_ia FROM gerencial.acesso;

-- name: usaram
-- Big number (pergunta 14258).
SELECT count(*) FILTER (WHERE usou_ia) AS usaram FROM gerencial.acesso;

-- name: funil_acesso_uso
-- Grafico de funil (pergunta 14290, display "funnel").
SELECT etapa, pessoas FROM (
    SELECT 1 AS ordem, 'Com acesso' AS etapa, count(*) AS pessoas FROM gerencial.acesso
    UNION ALL SELECT 2, 'Abriu a IA', count(*) FILTER (WHERE abriu_ia) FROM gerencial.acesso
    UNION ALL SELECT 3, 'Usou a IA', count(*) FILTER (WHERE usou_ia) FROM gerencial.acesso
) e ORDER BY ordem;

-- name: funil_por_canal
-- Pergunta 14293.
SELECT canal_entrada, count(*) AS com_acesso,
       count(*) FILTER (WHERE abriu_ia) AS abriram_a_ia,
       count(*) FILTER (WHERE usou_ia) AS usaram_a_ia
FROM gerencial.acesso GROUP BY 1 ORDER BY 2 DESC;

-- name: semanal_ativos
WITH a AS (
    SELECT usuario_ref, dia FROM gerencial.perguntas
    UNION ALL SELECT usuario_ref, dia FROM gerencial.calculadoras
    UNION ALL SELECT usuario_ref, dia FROM gerencial.noticias_favoritos
)
        SELECT date_trunc('week', dia)::date AS semana, count(DISTINCT usuario_ref) AS usuarios_ativos
        FROM a WHERE dia < date_trunc('week', current_date)
          AND usuario_ref IN (SELECT usuario_ref FROM gerencial.usuarios)  -- so quem conta (019)
        GROUP BY 1 ORDER BY 1;

-- name: semanal_contas_novas
SELECT date_trunc('week', dia_cadastro)::date AS semana, count(*) AS contas_novas
FROM gerencial.usuarios WHERE dia_cadastro < date_trunc('week', current_date) GROUP BY 1 ORDER BY 1;

-- name: semanal_perguntas_por_modo
-- Nomes de modo para a diretoria (pedido do Ruben em 2026-09-28): PHARMA_* vira "Bulario",
-- OFF_TOPIC fica fora. modo NULL nao e um periodo anterior a classificacao: convive com modos
-- classificados de maio a agosto e some depois de 20/08.
SELECT date_trunc('week', dia)::date AS semana,
       CASE
         WHEN modo = 'CLINICAL_REASONING' THEN 'Raciocínio Clínico'
         WHEN modo = 'QUICK_SEARCH'       THEN 'Busca Rápida'
         WHEN modo = 'PRODUCTIVITY'       THEN 'Produtividade'
         WHEN modo LIKE 'PHARMA%'         THEN 'Bulário'
         WHEN modo = 'EXAM_REVIEW'        THEN 'Modo de exames'
         WHEN modo = 'DATA_OCEAN'         THEN 'Dados do Brasil'
         WHEN modo IS NULL                THEN 'Modo não registrado'
         ELSE 'Outros'
       END AS modo,
       count(*) AS perguntas
FROM gerencial.perguntas
WHERE dia < date_trunc('week', current_date)
  AND modo IS DISTINCT FROM 'OFF_TOPIC'
GROUP BY 1, 2 ORDER BY 1, 2;

-- name: semanal_custo
WITH c AS (
          SELECT date_trunc('week', dia)::date AS semana, sum(custo_usd) AS custo
          FROM gerencial.perguntas WHERE dia < date_trunc('week', current_date) GROUP BY 1),
        a AS (
          SELECT date_trunc('week', dia)::date AS semana, count(DISTINCT usuario_ref) AS ativos
          FROM (
    SELECT usuario_ref, dia FROM gerencial.perguntas
    UNION ALL SELECT usuario_ref, dia FROM gerencial.calculadoras
    UNION ALL SELECT usuario_ref, dia FROM gerencial.noticias_favoritos
) x WHERE usuario_ref IN (SELECT usuario_ref FROM gerencial.usuarios)  -- so quem conta (019)
        GROUP BY 1)
        SELECT c.semana, round(c.custo, 2) AS custo_usd,
               round(c.custo / NULLIF(a.ativos, 0), 3) AS custo_por_ativo_usd
        FROM c LEFT JOIN a USING (semana) ORDER BY 1;

-- name: semanal_tempo_resposta
SELECT date_trunc('week', dia)::date AS semana,
       round((percentile_cont(0.5) WITHIN GROUP (ORDER BY tempo_resposta_ms) / 1000)::numeric, 1) AS p50_s,
       round((percentile_cont(0.9) WITHIN GROUP (ORDER BY tempo_resposta_ms) / 1000)::numeric, 1) AS p90_s
FROM gerencial.perguntas
WHERE status IN ('completed', 'resolved') AND tempo_resposta_ms IS NOT NULL AND dia < date_trunc('week', current_date)
GROUP BY 1 ORDER BY 1;

-- name: semanal_nao_concluidas
SELECT date_trunc('week', dia)::date AS semana, count(*) AS perguntas,
       count(*) FILTER (WHERE status = 'em_andamento' AND criado_em < now() - interval '10 minutes') AS nao_concluidas,
       round(100.0 * count(*) FILTER (WHERE status = 'em_andamento' AND criado_em < now() - interval '10 minutes')
             / count(*), 1) AS pct_nao_concluidas
FROM gerencial.perguntas WHERE dia < date_trunc('week', current_date) GROUP BY 1 ORDER BY 1;

-- name: custo_por_modelo_30d
SELECT COALESCE(modelo_nome, modelo) AS modelo, COALESCE(provedor, '?') AS provedor,
       count(*) AS chamadas, round(sum(custo_usd), 2) AS custo_usd,
       round(100.0 * avg(CASE WHEN com_erro THEN 1 ELSE 0 END), 1) AS pct_erro,
       round(100.0 * avg(CASE WHEN fallback THEN 1 ELSE 0 END), 1) AS pct_fallback
FROM gerencial.respostas_modelo WHERE dia > current_date - 30
GROUP BY 1, 2 ORDER BY custo_usd DESC NULLS LAST;

-- name: base_por_perfil
-- Pergunta 14292, barras horizontais empilhadas por uso (2026-10-13): todo mundo com
-- acesso num grafico so. Regra do perfil em `_perfil` de
-- alembic/versions/018_canal_e_acesso.py.
WITH b AS (
    SELECT perfil,
           CASE WHEN usou_ia THEN 'Usou a IA' ELSE 'Ainda não usou' END AS uso,
           count(*) AS pessoas
    FROM gerencial.acesso
    GROUP BY 1, 2
)
SELECT perfil, uso, pessoas FROM b
ORDER BY array_position(ARRAY['Especialista','Residente','Generalista','Médico, estágio não informado',
                              'Estudante','Enfermagem','Outro profissional de saúde','Não informado'], perfil),
         uso DESC;

-- name: base_por_especialidade
-- Pergunta 13867, grafico de barras horizontais empilhado por perfil (2026-10-13).
-- So especialistas e residentes: antes o "nao informada" juntava estudantes e
-- generalistas, que nao tem especialidade, e parecia que 77% da base nao respondeu.
WITH b AS (
    SELECT COALESCE(especialidade, 'Não informou a especialidade') AS especialidade,
           perfil, count(*) AS pessoas
    FROM gerencial.usuarios
    WHERE perfil IN ('Especialista', 'Residente')
    GROUP BY 1, 2
)
SELECT especialidade, perfil, pessoas FROM b
ORDER BY (especialidade = 'Não informou a especialidade'),
         sum(pessoas) OVER (PARTITION BY especialidade) DESC, especialidade, perfil;

-- name: top_calculadoras
SELECT calculadora, especialidade_calculadora, count(*) AS execucoes,
       count(DISTINCT usuario_ref) AS usuarios
FROM gerencial.calculadoras
GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 15;

-- name: noticias_publicadas_semana
SELECT date_trunc('week', dia_publicacao)::date AS semana, count(*) AS artigos_publicados
FROM gerencial.noticias_artigos WHERE dia_publicacao IS NOT NULL AND dia_publicacao < date_trunc('week', current_date) GROUP BY 1 ORDER BY 1;

-- name: captacao_por_landing
SELECT landing_page, count(*) AS leads,
       count(*) FILTER (WHERE virou_usuario) AS viraram_usuario,
       round(100.0 * count(*) FILTER (WHERE virou_usuario) / count(*), 1) AS pct_conversao
FROM gerencial.captacao GROUP BY 1 ORDER BY 2 DESC;

-- name: lista_usuarios
-- Pergunta 14294, aba "Usuarios" (2026-10-13). Unica pergunta nominal do painel: ver migration 018.
-- Inclui quem so tem acesso e nunca abriu a IA (situacao = 'Só tem acesso').
SELECT nome, email, situacao, canal_entrada, perfil,
       COALESCE(especialidade, 'não informada') AS especialidade, uf,
       dia_entrada, abriu_ia_em, ultimo_uso_em,
       perguntas, calculadoras, noticias_favoritadas, grupos_waid
FROM gerencial.usuarios_lista
ORDER BY usou_ia DESC, abriu_ia DESC, ultimo_uso_em DESC NULLS LAST, entrou_em DESC;
