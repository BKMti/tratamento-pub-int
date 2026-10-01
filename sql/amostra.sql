-- Amostra rotulada para o experimento. SÓ LEITURA.
-- Parâmetros (psycopg): %(controllers)s text[]   nomes em monitoramento.usuario.nome
--                       %(dias)s        int      janela para trás a partir de agora
--                       %(limite)s      int      casos por grupo
--                       %(excluir)s     bigint[] andamentos já usados em amostras anteriores
-- Antes desta consulta a aplicação roda SELECT setseed(%(seed)s) na mesma sessão.
--
-- Gabarito:
--   tratado      = publicação marcada "Tratado" E com tarefa rotulada pelo POP ([FATAL/[PROTOCOLO/[COMPROMISSO/
--                  [INTERNO/[DILIG) cadastrada por um dos controllers no mesmo processo em até 7 dias.
--   nada_a_fazer = publicação marcada "Nada a fazer", com motivo nas observações e SEM tarefa rotulada em 7 dias.
WITH controllers AS (
  SELECT legalone_id FROM monitoramento.usuario
  WHERE nome = ANY(%(controllers)s::text[])
),
tratado_sample AS (
  SELECT pt.andamento_id, pt.processo_id, pt.data_evento, pt.tipo, pt.natureza, pt.equipe,
         left(an.descricao, 3500) AS descricao
  FROM monitoramento.publicacao_triagem pt
  JOIN monitoramento.andamento an ON an.legalone_id = pt.andamento_id
  WHERE pt.data_evento >= now() - make_interval(days => %(dias)s)
    AND pt.origem = 'OfficialJournalsCrawler'
    AND pt.tipo IN ('Publicação', 'Intimação Eletrônica')
    AND pt.subtipo = 'Tratado'
    AND NOT (pt.andamento_id = ANY(%(excluir)s::bigint[]))
    AND EXISTS (
      SELECT 1 FROM monitoramento.agenda a
      JOIN controllers c ON c.legalone_id = a.usuario_cadastro_id
      WHERE a.processo_id = pt.processo_id
        AND a.data_cadastro BETWEEN pt.data_evento AND pt.data_evento + interval '7 days'
        AND (a.descricao LIKE '[FATAL%%' OR a.descricao LIKE '[PROTOCOLO%%' OR a.descricao LIKE '[COMPROMISSO%%'
             OR a.descricao LIKE '[INTERNO%%' OR a.descricao LIKE '[DILIG%%')
    )
  ORDER BY random()
  LIMIT %(limite)s
),
nada_sample AS (
  SELECT pt.andamento_id, pt.processo_id, pt.data_evento, pt.tipo, pt.natureza, pt.equipe,
         left(an.descricao, 3500) AS descricao, an.observacoes AS motivo
  FROM monitoramento.publicacao_triagem pt
  JOIN monitoramento.andamento an ON an.legalone_id = pt.andamento_id
  WHERE pt.data_evento >= now() - make_interval(days => %(dias)s)
    AND pt.origem = 'OfficialJournalsCrawler'
    AND pt.tipo IN ('Publicação', 'Intimação Eletrônica')
    AND pt.subtipo = 'Nada a fazer'
    AND an.observacoes IS NOT NULL AND btrim(an.observacoes) <> ''
    AND NOT (pt.andamento_id = ANY(%(excluir)s::bigint[]))
    AND NOT EXISTS (
      SELECT 1 FROM monitoramento.agenda a
      WHERE a.processo_id = pt.processo_id
        AND a.data_cadastro BETWEEN pt.data_evento AND pt.data_evento + interval '7 days'
        AND (a.descricao LIKE '[FATAL%%' OR a.descricao LIKE '[PROTOCOLO%%' OR a.descricao LIKE '[COMPROMISSO%%'
             OR a.descricao LIKE '[INTERNO%%' OR a.descricao LIKE '[DILIG%%')
    )
  ORDER BY random()
  LIMIT %(limite)s
),
todos AS (
  SELECT 'tratado' AS grupo, andamento_id, processo_id, data_evento, tipo, natureza, equipe, descricao,
         NULL::text AS motivo
  FROM tratado_sample
  UNION ALL
  SELECT 'nada_a_fazer', andamento_id, processo_id, data_evento, tipo, natureza, equipe, descricao, motivo
  FROM nada_sample
)
SELECT t.grupo, t.andamento_id, t.processo_id, t.data_evento, t.tipo, t.natureza, t.equipe, t.descricao, t.motivo,
       (SELECT json_agg(json_build_object('titulo', a.descricao, 'tipo', a.tipo, 'subtipo', a.subtipo,
                                          'prazo_dias', a.prazo_dias))
        FROM monitoramento.agenda a
        WHERE a.processo_id = t.processo_id
          AND a.data_cadastro BETWEEN t.data_evento AND t.data_evento + interval '7 days'
          AND (a.descricao LIKE '[FATAL%%' OR a.descricao LIKE '[PROTOCOLO%%' OR a.descricao LIKE '[COMPROMISSO%%'
               OR a.descricao LIKE '[INTERNO%%' OR a.descricao LIKE '[DILIG%%')
       ) AS tarefas
FROM todos t;
