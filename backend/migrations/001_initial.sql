CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;

CREATE TABLE users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email CITEXT NOT NULL UNIQUE,
  senha_hash TEXT NOT NULL,
  nome TEXT,
  cpf_hash TEXT NOT NULL UNIQUE,
  cpf_cifrado BYTEA NOT NULL,
  regime TEXT NOT NULL CHECK (regime IN ('MEI','SIMPLES','PF')),
  mes_abertura_mei INTEGER CHECK (mes_abertura_mei BETWEEN 1 AND 12),
  ano_abertura_mei INTEGER CHECK (ano_abertura_mei BETWEEN 2000 AND 2100),
  telegram_chat_id BIGINT UNIQUE,
  criado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
  atualizado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE sessions (
  id UUID PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  expira_em TIMESTAMPTZ NOT NULL,
  revogada_em TIMESTAMPTZ,
  criado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX sessions_user_active_idx ON sessions(user_id) WHERE revogada_em IS NULL;

CREATE TABLE audit_log (
  id BIGSERIAL PRIMARY KEY,
  user_id UUID REFERENCES users(id) ON DELETE SET NULL,
  ator TEXT NOT NULL,
  acao TEXT NOT NULL,
  alvo TEXT,
  meta JSONB NOT NULL DEFAULT '{}'::jsonb,
  criado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE consents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  provider TEXT NOT NULL,
  provider_user_id TEXT,
  concedido_em TIMESTAMPTZ NOT NULL DEFAULT now(),
  revogado_em TIMESTAMPTZ
);

CREATE TABLE accounts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  provider TEXT NOT NULL,
  provider_account_id TEXT,
  nome TEXT,
  criado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
  atualizado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE transactions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  account_id UUID REFERENCES accounts(id) ON DELETE SET NULL,
  origem TEXT NOT NULL CHECK (origem IN ('pluggy','paste','csv','ofx','manual')),
  pluggy_tx_id TEXT,
  paste_id TEXT,
  import_id TEXT,
  line_index INTEGER,
  data DATE NOT NULL,
  descricao_bruta TEXT NOT NULL,
  valor NUMERIC(18,2) NOT NULL,
  contraparte_cpf_hash TEXT,
  contraparte_cnpj TEXT,
  categoria TEXT,
  proposito TEXT,
  patrimonio TEXT,
  tratamento_tributario TEXT,
  confianca NUMERIC(6,5),
  needs_review BOOLEAN,
  via TEXT,
  motivo TEXT,
  confirmado_por UUID REFERENCES users(id),
  confirmado_em TIMESTAMPTZ,
  versao INTEGER NOT NULL DEFAULT 1,
  criado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
  atualizado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX transactions_pluggy_uq ON transactions(user_id,pluggy_tx_id) WHERE pluggy_tx_id IS NOT NULL;
CREATE UNIQUE INDEX transactions_paste_uq ON transactions(user_id,paste_id,line_index) WHERE paste_id IS NOT NULL;
CREATE UNIQUE INDEX transactions_import_uq ON transactions(user_id,import_id,line_index) WHERE import_id IS NOT NULL;

CREATE TABLE fiscal_state (
  user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  atualizado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
  estado JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE alerts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  tipo TEXT NOT NULL,
  severidade TEXT,
  mensagem TEXT NOT NULL,
  lido_em TIMESTAMPTZ,
  criado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE subscriptions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  plano TEXT NOT NULL,
  status TEXT NOT NULL,
  periodo_inicio TIMESTAMPTZ,
  periodo_fim TIMESTAMPTZ,
  pausada_ate DATE,
  criado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
  atualizado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE payments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  subscription_id UUID REFERENCES subscriptions(id) ON DELETE SET NULL,
  plano TEXT NOT NULL,
  valor NUMERIC(18,2) NOT NULL,
  periodo_dias INTEGER NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('pendente','pendente_reconciliacao','confirmado','falhou','expirado')),
  asaas_payment_id TEXT,
  external_reference TEXT,
  pix_qr_code TEXT,
  pix_copy_paste TEXT,
  idempotency_key TEXT,
  claimed_at TIMESTAMPTZ,
  claimed_by TEXT,
  tentativa_em TIMESTAMPTZ,
  expira_em TIMESTAMPTZ NOT NULL DEFAULT (now() + interval '24 hours'),
  criado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
  atualizado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE webhook_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  origem TEXT NOT NULL,
  event_id TEXT NOT NULL,
  payload JSONB NOT NULL,
  criado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(origem,event_id)
);

CREATE TABLE idempotency_keys (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  rota TEXT NOT NULL,
  chave TEXT NOT NULL,
  payload_hash TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('processando','concluido','falhou')),
  response JSONB,
  status_http INTEGER,
  expira_em TIMESTAMPTZ NOT NULL DEFAULT (now() + interval '24 hours'),
  criado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
  atualizado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(user_id,rota,chave)
);

CREATE TABLE telegram_link_tokens (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token TEXT NOT NULL,
  ativo BOOLEAN NOT NULL DEFAULT TRUE,
  expira_em TIMESTAMPTZ NOT NULL,
  criado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX telegram_link_tokens_active_uq ON telegram_link_tokens(user_id) WHERE ativo = TRUE;
CREATE UNIQUE INDEX telegram_link_tokens_token_uq ON telegram_link_tokens(token);

CREATE TABLE sync_requests (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'pendente',
  claimed_at TIMESTAMPTZ,
  claimed_by TEXT,
  tentativa_em TIMESTAMPTZ,
  erro TEXT,
  criado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
  atualizado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE personal_rules (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  regra JSONB NOT NULL,
  criado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);
