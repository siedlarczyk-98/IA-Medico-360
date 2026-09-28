-- Cards do dashboard gerencial (Metabase). Cada bloco e uma pergunta SQL nativa.
-- Validados em producao em 2026-09-28 com o role gerencial_leitura.
-- Graficos semanais excluem a semana corrente (incompleta). Ver docs/dashboard-gerencial.md.

-- KPIs de 7 dias: uma linha por janela (inicio_periodo = primeiro dia da janela), para o
-- card "smartscalar" do Metabase mostrar o valor atual e a variacao sobre os 7 dias anteriores.

-- name: kpi_ativos_7d
WITH a AS (
    SELECT usuario_ref, dia FROM gerencial.perguntas
    UNION ALL SELECT usuario_ref, dia FROM gerencial.calculadoras
    UNION ALL SELECT usuario_ref, dia FROM gerencial.acessos
)
SELECT CASE WHEN dia > current_date - 7 THEN current_date - 6 ELSE current_date - 13 END AS inicio_periodo,
       count(DISTINCT usuario_ref) AS usuarios_ativos
FROM a WHERE dia > current_date - 14
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

-- name: semanal_ativos
WITH a AS (
    SELECT usuario_ref, dia FROM gerencial.perguntas
    UNION ALL SELECT usuario_ref, dia FROM gerencial.calculadoras
    UNION ALL SELECT usuario_ref, dia FROM gerencial.acessos
)
        SELECT date_trunc('week', dia)::date AS semana, count(DISTINCT usuario_ref) AS usuarios_ativos
        FROM a WHERE dia < date_trunc('week', current_date) GROUP BY 1 ORDER BY 1;

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
    UNION ALL SELECT usuario_ref, dia FROM gerencial.acessos
) x GROUP BY 1)
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

-- name: base_por_especialidade
SELECT COALESCE(especialidade, 'não informada') AS especialidade, count(*) AS usuarios
FROM gerencial.usuarios GROUP BY 1 ORDER BY 2 DESC;

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
