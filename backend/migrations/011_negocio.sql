-- M11 (migration 011): módulo "Meu Negócio" — cadastro de produtos/serviços,
-- precificação (Categoria I da consulta docs/CONSULTA_CRC_ES.md) e
-- movimentação de estoque (Categoria II — consolidação de eventos
-- informados pelo usuário, sem inferência).
-- Ver docs/REGRA_ORIENTADOR.md para o contrato de comportamento.

CREATE TABLE products (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  tipo TEXT NOT NULL CHECK (tipo IN ('produto','servico')),
  nome TEXT NOT NULL,
  unidade_medida TEXT NOT NULL DEFAULT 'un',
  custo_atual NUMERIC(18,2),
  preco_atual NUMERIC(18,2),
  controla_estoque BOOLEAN NOT NULL DEFAULT true,
  ativo BOOLEAN NOT NULL DEFAULT true,
  criado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
  atualizado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_products_user ON products(user_id);

CREATE TABLE stock_movements (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  tipo_movimento TEXT NOT NULL,
  quantidade NUMERIC(18,3) NOT NULL CHECK (quantidade > 0),
  origem TEXT NOT NULL DEFAULT 'manual' CHECK (origem IN ('manual','importado')),
  referencia_transacao_id UUID REFERENCES transactions(id) ON DELETE SET NULL,
  nota TEXT,
  criado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_stock_movements_product ON stock_movements(product_id, criado_em DESC);
CREATE INDEX idx_stock_movements_user ON stock_movements(user_id);

CREATE TABLE pricing_scenarios (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  product_id UUID REFERENCES products(id) ON DELETE SET NULL,
  nome TEXT NOT NULL,
  preco NUMERIC(18,2) NOT NULL,
  custo_variavel_unitario NUMERIC(18,2) NOT NULL,
  custos_fixos_periodo NUMERIC(18,2),
  volume_hipotese NUMERIC(18,3),
  criado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_pricing_scenarios_user ON pricing_scenarios(user_id, criado_em DESC);