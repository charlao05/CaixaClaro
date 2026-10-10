-- 013_faturamento_por_ano.sql — revisao de 2026-10-09
--
-- Contexto: a soma do faturamento do ano passou a ser lida direto de
-- transactions (M4_CONTRATO §9: "soma atual das transacoes do usuario"),
-- em vez de um contador ajustado por deltas em fiscal_state.
--
-- 1. Indice para a leitura por usuario e data (soma do ano e listagem).
--
-- 2. Backfill das confirmacoes antigas. Ate o M13, quando o usuario trocava
--    a categoria ao confirmar, a linha ficava com proposito, patrimonio e
--    tratamento do palpite original. Por isso uma entrada confirmada como
--    trabalho nao contava no faturamento. O M13 corrigiu a gravacao dali em
--    diante, e este backfill alinha o que ja estava gravado, com a mesma
--    regra que o codigo aplica (dimensoes padrao da categoria escolhida).
--    Alcanca apenas linhas confirmadas pelo usuario, com categoria diferente
--    da original e ainda nao marcadas com via = 'usuario'.
--
-- Retrocompativel com a versao anterior da aplicacao (M10_DECISAO, item 6):
-- nenhuma coluna nova, nenhum valor novo de dominio.

CREATE INDEX IF NOT EXISTS transactions_user_data_idx
    ON transactions (user_id, data);

UPDATE transactions AS t
   SET proposito = d.proposito,
       patrimonio = d.patrimonio,
       tratamento_tributario = d.tratamento,
       via = 'usuario',
       atualizado_em = now()
  FROM (VALUES
    ('receita_servico',       'trabalho_servico',      'atividade_negocio', 'tributavel_irpf'),
    ('receita_venda',         'venda_produto',         'atividade_negocio', 'faturamento_pj'),
    ('salario',               'salario_aposentadoria', 'pessoa_fisica',     'retencao_fonte'),
    ('imposto_das',           'imposto_taxa',          'atividade_negocio', 'isento_nao_tributavel'),
    ('taxas_tarifas',         'imposto_taxa',          'atividade_negocio', 'isento_nao_tributavel'),
    ('custo_operacional',     'gasto_negocio',         'atividade_negocio', 'indeterminado_pendente'),
    ('transferencia_propria', 'transferencia_propria', 'pessoa_fisica',     'isento_nao_tributavel'),
    ('pessoal_prolabore',     'retirada_proprietario', 'ponte_pf_pj',       'indeterminado_pendente'),
    ('reembolso',             'devolucao_reembolso',   'pessoa_fisica',     'isento_nao_tributavel'),
    ('emprestimo',            'emprestimo',            'pessoa_fisica',     'isento_nao_tributavel'),
    ('outros',                'outros_indeterminado',  'pessoa_fisica',     'indeterminado_pendente')
  ) AS d(categoria, proposito, patrimonio, tratamento)
 WHERE t.categoria = d.categoria
   AND t.confirmado_por IS NOT NULL
   AND t.via IS DISTINCT FROM 'usuario'
   AND t.categoria_original IS NOT NULL
   AND t.categoria IS DISTINCT FROM t.categoria_original;
