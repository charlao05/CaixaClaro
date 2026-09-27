-- M5: vinculo local do usuario ao Customer do Asaas.
ALTER TABLE users ADD COLUMN asaas_customer_id TEXT;

CREATE UNIQUE INDEX users_asaas_customer_uq
  ON users (asaas_customer_id)
  WHERE asaas_customer_id IS NOT NULL;
