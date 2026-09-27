-- M3b: vinculo conta -> Item Pluggy.
-- Necessario para POST /contas/{id}/revogar: precisamos saber qual Item
-- deletar na Pluggy a partir de uma conta local.
-- Nao e FK para consents porque consents e a entidade de consentimento
-- (revogavel), enquanto item_id aqui e so referencia operacional.
ALTER TABLE accounts ADD COLUMN item_id TEXT;

CREATE INDEX accounts_pluggy_item_idx
  ON accounts (provider, item_id)
  WHERE item_id IS NOT NULL;
