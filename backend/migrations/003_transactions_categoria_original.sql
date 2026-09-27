-- 003_transactions_categoria_original.sql — M5A (auditoria decisão B)
--
-- Preserva a classificacao da maquina mesmo apos confirmacao do usuario.
-- No INSERT, categoria_original = categoria. Ao confirmar, categoria muda
-- mas categoria_original fica congelada.
--
-- Vazio nao e permitido: o backfill cobre o historico.

ALTER TABLE transactions
  ADD COLUMN IF NOT EXISTS categoria_original TEXT;

UPDATE transactions
   SET categoria_original = categoria
 WHERE categoria_original IS NULL
   AND categoria IS NOT NULL;
