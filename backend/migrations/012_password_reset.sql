-- M12 (migration 012): recuperacao de senha por codigo de 6 digitos.
--
-- Canal inicial: Telegram (users.telegram_chat_id). E-mail entra em
-- incremento posterior — a tabela nao muda quando isso acontecer.
--
-- Contexto:
--   - O codigo em claro NUNCA e' armazenado. So o hash SHA-256.
--   - Uso unico garantido por UPDATE ... WHERE usado_em IS NULL.
--   - Expiracao de 15 minutos, definida no service.
--   - Uma solicitacao ativa por usuario: criar nova invalida a anterior.

CREATE TABLE password_reset_tokens (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  codigo_hash TEXT NOT NULL,
  expira_em TIMESTAMPTZ NOT NULL,
  usado_em TIMESTAMPTZ,
  criado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_password_reset_user ON password_reset_tokens(user_id);