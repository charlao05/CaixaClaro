# Contratos internos

## 1. JWT e sessão
JWT contém session id. Login cria sessão revogável. Logout revoga. Validação exige assinatura, expiração, sessão válida e correspondência sub/sessão.

## 2. CPF
CPF normalizado; HMAC para busca; AES-GCM para armazenamento reversível. Claro somente na fronteira autorizada de perfil e billing.

## 3. Transações
Campos: origem, paste_id, import_id, line_index. Unicidades por origem. Confirmar usa transactions.versao e auditoria do payload.

## 4. Telegram
telegram_link_tokens possui ativo BOOLEAN. Índice parcial único: UNIQUE(user_id) WHERE ativo=true. Não usar now() em índice parcial. Token dura 10 minutos; uso invalida.

## 5. Webhooks
webhook_events possui identidade do evento e processamento idempotente.

## 6. Billing
payments: id, subscription_id, user_id, asaas_payment_id UNIQUE, plano, valor NUMERIC(14,2), periodo_dias, status, pix_qrcode, pix_copia_cola, idempotency_key, criado_em, confirmado_em, expira_em, erro, reconciliado_em, claimed_at, claimed_by, tentativa_em.

Estados: pendente, pendente_reconciliacao, confirmado, falhou, expirado.

payments.id é externalReference e serve para reconciliação; não é garantia de idempotência externa.

### Idempotency keys
idempotency_keys usa (user_id, rota, chave) UNIQUE e estados processando|concluido|falhou. Resposta só é persistida após operação completa.

### Claim
Antes de qualquer tentativa externa, obter claim persistente:
UPDATE payments SET claimed_at=now(), claimed_by=$worker_id, tentativa_em=now()
WHERE id=$payment_id AND status IN ('pendente','pendente_reconciliacao')
AND (claimed_at IS NULL OR claimed_at < now()-interval '5 minutes')
RETURNING id;

Claim é exclusão mútua, não autorização cega.

### GET antes de POST
Nenhum POST /payments ocorre sem GET por externalReference={payments.id} que tenha retornado vazio.

Checkout/renovação:
1. claim;
2. se asaas_payment_id existe, não criar;
3. GET externalReference;
4. se encontrou, adotar e não POST;
5. se vazio, POST;
6. persistir resultado;
7. auditar;
8. liberar claim.

Timeout/resultado desconhecido → pendente_reconciliacao; nunca POST cego depois de timeout.

Reconciliação: claim + GET. Encontrou → adota. Vazio → pode marcar falha segundo política. Timeout → mantém pendente_reconciliacao.

Crash após POST e antes de persistir ID: próximo executor faz GET e adota a cobrança existente.

### Política B
confirmed → no-op; pending → confirma; expired → confirma e audita payment_confirmado_tardio; failed → confirma e audita payment_confirmado_apos_falha; pending_reconciliation → associa, confirma e aplica período.

### Renovação
Worker a cada 6h. Pausa vigente não cobra; período nulo ignora; período além de 3 dias ignora. Payments pendente e pendente_reconciliacao recuperável bloqueiam duplicação.

## 7. Contas
accounts.consent_id deve ser preenchido. Regime fiscal vem de users; não hardcode MEI.

## 8. Sync
Async; não sobrescreve decisão do usuário. Claims persistentes seguem padrão de stale recovery.

## 9. Auditoria
Ações relevantes guardam ator, ação, recurso e contexto.

## 10. Fiscal
Fonte, URL e verificada_em acompanham obrigação; fonte pendente não sustenta garantia.

## 11. Trial
Sete dias sem cartão.

## 12. Concorrência
Sync pode incrementar transactions.versao. Confirmação obsoleta retorna 409.

## 13. Asaas
externalReference não é idempotência garantida. Webhooks são at-least-once e podem chegar fora de ordem.

Fonte externa verificada em 26/09/2026: documentação oficial do Asaas.
