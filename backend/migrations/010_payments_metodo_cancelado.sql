-- B: cartao de credito como instrumento de cobranca avulsa.
--
-- Contexto:
--   - payments passa a distinguir instrumento (pix vs cartao).
--   - Trocas de instrumento substituem a cobranca pendente anterior.
--     O estado 'cancelado' representa essa substituicao sem confundir
--     com 'falhou' (erro de cobranca) nem 'expirado' (decurso de prazo).
--
-- Escopo desta migration:
--   - coluna metodo com CHECK restrito a pix/cartao
--   - valor 'cancelado' adicionado ao CHECK de status
--   - sem novas colunas, sem novos indices, sem backfill

ALTER TABLE payments
  ADD COLUMN metodo TEXT NOT NULL DEFAULT 'pix';

ALTER TABLE payments
  ADD CONSTRAINT payments_metodo_check
  CHECK (metodo IN ('pix', 'cartao'));

ALTER TABLE payments
  DROP CONSTRAINT payments_status_check;

ALTER TABLE payments
  ADD CONSTRAINT payments_status_check
  CHECK (status IN (
    'pendente',
    'pendente_reconciliacao',
    'confirmado',
    'falhou',
    'expirado',
    'cancelado'
  ));