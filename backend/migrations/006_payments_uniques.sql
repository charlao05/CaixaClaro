-- M5: unicidade de payments.
-- Duplo lookup (webhook) depende de external_reference e asaas_payment_id
-- unicos por linha. Sem isso, corrida entre workers pode duplicar.
CREATE UNIQUE INDEX payments_external_reference_uq
  ON payments (external_reference)
  WHERE external_reference IS NOT NULL;

CREATE UNIQUE INDEX payments_asaas_id_uq
  ON payments (asaas_payment_id)
  WHERE asaas_payment_id IS NOT NULL;
