-- 002_alerts_dedup.sql — M4b §10 (unicidade do alerta)
--
-- O §10 do M4_CONTRATO exige:
--   UNIQUE (user_id, tipo, banda_ou_slug, prazo)
-- para impedir que a mesma faixa gere dois alertas no mesmo prazo.
--
-- A tabela alerts do 001_initial.sql nao tinha banda_ou_slug nem prazo.
-- Esta migracao adiciona as duas colunas e o indice unico.
--
-- NULLs nao conflitam entre si (SQL standard), entao alertas legados
-- (banda_ou_slug NULL) permanecem intactos.

ALTER TABLE alerts
  ADD COLUMN IF NOT EXISTS banda_ou_slug TEXT,
  ADD COLUMN IF NOT EXISTS prazo DATE;

CREATE UNIQUE INDEX IF NOT EXISTS alerts_dedup_uq
  ON alerts (user_id, tipo, banda_ou_slug, prazo);
