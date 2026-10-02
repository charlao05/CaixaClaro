-- E1 - Gate de autorizacao de uso.
--
-- Adiciona a marcacao de isencao de trial em users.
--
-- Contexto:
--   - users.criado_em ja e TIMESTAMPTZ NOT NULL DEFAULT now() (001_initial.sql),
--     portanto o fim do trial e derivado (criado_em + TRIAL_DIAS), sem coluna
--     de expiracao propria.
--   - trial_exempt e a unica excecao explicita ao calculo do trial.
--     Um usuario marcado como TRUE tem acesso independente do tempo.
--
-- Nenhuma outra alteracao de schema e feita nesta migration.

ALTER TABLE users
  ADD COLUMN trial_exempt BOOLEAN NOT NULL DEFAULT FALSE;