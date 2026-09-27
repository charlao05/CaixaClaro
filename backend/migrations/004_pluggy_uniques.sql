-- M3b: unicidade de entidades Pluggy.
-- Impede duplicacao de consent e account quando o webhook reexecuta
-- ou chega evento distinto para o mesmo item.
CREATE UNIQUE INDEX consents_pluggy_uq
  ON consents (provider, provider_user_id)
  WHERE provider = 'pluggy';

CREATE UNIQUE INDEX accounts_pluggy_uq
  ON accounts (provider, provider_account_id)
  WHERE provider = 'pluggy';
