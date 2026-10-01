-- Histórico do processo antes de uma publicação (uma linha por caso). SÓ LEITURA.
-- Parâmetros (psycopg): %(processo_id)s bigint, %(data_evento)s timestamptz,
--                       %(dias_hist)s int (janela para trás das tarefas), %(tarefas_max)s int, %(pubs_max)s int
-- Foi o que mais ajudou o classificador (65 % -> 77 % de acurácia): dados cadastrais da pasta, tarefas já
-- cadastradas antes desta publicação e as publicações anteriores do mesmo processo.
SELECT
  (SELECT pp.equipe          FROM monitoramento.processo_planilha pp WHERE pp.legalone_id = %(processo_id)s) AS pp_equipe,
  (SELECT pp.posicao_cliente FROM monitoramento.processo_planilha pp WHERE pp.legalone_id = %(processo_id)s) AS pp_posicao_cliente,
  ve.natureza      AS ve_natureza,
  ve.fase          AS ve_fase,
  ve.acao          AS ve_acao,
  ve.tipo_processo AS ve_tipo_processo,
  ve.status        AS ve_status,
  (SELECT json_agg(y) FROM (
     SELECT a.descricao AS titulo, a.tipo, a.subtipo, a.status, a.data_inicio, a.data_fim
     FROM monitoramento.agenda a
     WHERE a.processo_id = %(processo_id)s
       AND a.data_cadastro >= %(data_evento)s::timestamptz - make_interval(days => %(dias_hist)s)
       AND a.data_cadastro <= %(data_evento)s::timestamptz - interval '1 day'
     ORDER BY a.data_cadastro DESC
     LIMIT %(tarefas_max)s
   ) y) AS tarefas_historico,
  (SELECT json_agg(z) FROM (
     SELECT left(an.descricao, 200) AS trecho, an.data_evento,
            (SELECT pt.subtipo FROM monitoramento.publicacao_triagem pt
             WHERE pt.andamento_id = an.legalone_id LIMIT 1) AS subtipo_triagem
     FROM monitoramento.andamento an
     WHERE an.processo_id = %(processo_id)s
       AND an.data_evento < %(data_evento)s::timestamptz
     ORDER BY an.data_evento DESC
     LIMIT %(pubs_max)s
   ) z) AS publicacoes_anteriores
FROM (SELECT 1) AS um
LEFT JOIN monitoramento.vw_processo_enriquecido ve ON ve.legalone_id = %(processo_id)s;
