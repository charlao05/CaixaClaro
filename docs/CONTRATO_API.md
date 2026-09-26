# Contrato da API v1

Base: /api/v1.

## Auth
POST /auth/register → 201 e Location /api/v1/perfil.
POST /auth/login → {token, expires_at, user}.
POST /auth/logout → revoga a sessão.
JWT HS256: sub=user_id, sid=session_id, iat, exp. Segredo mínimo de 32 bytes. Validação exige assinatura, expiração, sessão existente e não revogada.

## Perfil
GET /perfil
PATCH /perfil
PATCH não aceita telegram_chat_id.

## Transações
POST /transacoes/extrato/colar
POST /transacoes/importar
GET /transacoes
GET /transacoes/fila
POST /transacoes/{id}/confirmar

Identidades: Pluggy usa (user_id, pluggy_tx_id); paste usa (user_id, paste_id, line_index); CSV/OFX usa (user_id, import_id, line_index). paste_id = sha256(texto_normalizado)[:16].

Confirmar exige versao. Divergência → 409 CONFLITO_VERSAO. Mesma decisão já aplicada é no-op. salvar_regra=true cria regra pessoal.

## Contas e sync
POST /contas/conectar
GET /contas
POST /contas/{id}/sync → 202 {sync_id,status}
POST /contas/{id}/revogar
GET /sync/{sync_id} → pendente|processando|completed|failed.

## Fiscal
GET /fiscal/resumo
GET /fiscal/obrigacoes
GET /regras-pessoais

## Billing
POST /billing/checkout
POST /billing/pausar
GET /billing/status
GET /payments
Planos pro_mensal e pro_anual. PIX avulso Asaas.

## Alertas
GET /alertas
POST /alertas/{id}/lido

## Eval
GET /eval/ultima-execucao

## Telegram
POST /telegram/token-vinculacao. Token válido por 10 minutos; somente um ativo por usuário. O webhook grava telegram_chat_id.

## Webhooks
POST /webhooks/pluggy
POST /webhooks/asaas
POST /webhooks/telegram

Eventos externos são idempotentes.

### Webhook Asaas
event.id é identidade do evento e é único em webhook_events.

Caminho 1:
SELECT * FROM payments WHERE asaas_payment_id = $asaas_id;

Se vazio, caminho 2:
SELECT * FROM payments WHERE id = $external_reference;

O user_id vem de payments.user_id; não é extraído do evento externo.

Se externalReference não estiver no evento, o caminho de recuperação pode fazer GET /payments/{asaas_payment_id}. Se ambos os caminhos falharem: audit_log payment_orfao, alerta operacional alto e HTTP 200.

Ao localizar por externalReference, validar que a referência corresponde a payments.id antes de associar asaas_payment_id.

PAYMENT_CONFIRMED libera o período contratado conforme Política B. PAYMENT_RECEIVED significa saldo disponível e não é confundido com CONFIRMED.

## Paginação
Transações: data DESC,id DESC. Fila/alertas/contas/payments: criado_em DESC,id DESC. Cursor opaco. Máximo 500.

## Idempotency-Key
Unicidade por (user_id, rota, chave). Mesmo payload concluído retorna resposta persistida. Payload diferente → 409 IDEMPOTENCY_KEY_REUSED. Processando → 409 IDEMPOTENCY_EM_ANDAMENTO + Retry-After 1. Falha permite reprocessamento.

## Erros
Códigos de domínio são estáveis e ownership é verificado no backend.
