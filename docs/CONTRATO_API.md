# Contrato da API v1

Base: /api/v1.

## Auth

### POST /auth/register
Retorna 201 e Location /api/v1/perfil.

### POST /auth/login
Retorna {token, expires_at, user}. Cada login cria uma nova sessão revogável.

JWT:
{sub:user_id, sid:session_id, iat, exp}

Assinatura HS256. JWT_SECRET >= 32 bytes.

Validação protegida:
1. assinatura;
2. exp > now();
3. sessão sid existe;
4. sessions.revogada_em IS NULL;
5. sessions.expira_em > now();
6. sessions.user_id == sub;
7. JWT.exp == sessions.expira_em.

Falha → 401. JWT expirado pode ser rejeitado sem consultar sessions.

### POST /auth/logout
Revoga a sessão. O mesmo JWT, mesmo ainda dentro de exp, retorna 401.

## Perfil

GET /perfil
PATCH /perfil

telegram_chat_id não pertence ao PATCH; somente webhook Telegram pode gravá-lo.

## Transações

POST /transacoes/extrato/colar
POST /transacoes/importar
GET /transacoes
GET /transacoes/fila
POST /transacoes/{id}/confirmar

Identidade:
- Pluggy: UNIQUE (user_id, pluggy_tx_id)
- paste: UNIQUE (user_id, paste_id, line_index)
- CSV/OFX: UNIQUE (user_id, import_id, line_index)
- paste_id = sha256(texto_normalizado)[:16]
- manual: identidade própria, sem deduplicação por conteúdo.

Hash de data/descricao/valor não é identidade.

Confirmar exige versao. Divergência → 409 CONFLITO_VERSAO. Mesma decisão já aplicada é no-op, sem updated_at novo. Decisão diferente é nova transição. salvar_regra=true cria regra pessoal; false não remove regra existente. Auditoria registra payload completo.

## Contas e sync

POST /contas/conectar
GET /contas
POST /contas/{id}/sync → 202 {sync_id,status}
POST /contas/{id}/revogar
GET /sync/{sync_id} → pendente|processando|completed|failed

sync é assíncrono; sync_request é persistido e processado por worker.

## Fiscal

GET /fiscal/resumo
GET /fiscal/obrigacoes
GET /regras-pessoais

Obrigações carregam nome, URL, verificada_em e fonte_pendente_verificacao quando aplicável.

## Billing

POST /billing/checkout
POST /billing/pausar
GET /billing/status
GET /payments

Planos: pro_mensal = 30 dias; pro_anual = 365 dias.

Asaas: PIX avulso controlado pelo CaixaClaro.

Payment carrega plano, valor e periodo_dias; subscription não decide período.

Estados locais: pendente, pendente_reconciliacao, confirmado, falhou, expirado.

payments.id é enviado como externalReference somente para reconciliação; não é garantia de idempotência externa.

### Checkout / GET antes de POST

Regra: nenhum POST de criação no Asaas sem GET prévio por externalReference={payments.id} que tenha retornado vazio.

Fluxo:
1. transação local cria/reutiliza payment e idempotency record;
2. claim persistente;
3. se asaas_payment_id existe, não criar;
4. GET externalReference;
5. encontrado → adotar;
6. vazio → POST;
7. persistir resultado;
8. auditar;
9. liberar claim.

Timeout/resultado desconhecido → pendente_reconciliacao. Nunca POST cego depois de timeout.

### Reconciliação

Worker consulta por externalReference. Encontrou → adota. Vazio → nova criação só se ainda autorizada pela política e sempre precedida pelo GET vazio. Timeout → mantém pendente_reconciliacao.

## Alertas

GET /alertas
POST /alertas/{id}/lido

Segundo mark-read do mesmo alerta é no-op e não altera lido_em. Ownership é obrigatório.

## Eval

GET /eval/ultima-execucao

Golden/eval é executado fora do cliente.

## Telegram

POST /telegram/token-vinculacao: token válido por 10 minutos; somente um ativo por usuário.

POST /webhooks/telegram: somente este fluxo grava telegram_chat_id.

Índice de token ativo usa ativo=true; não usar now() em índice parcial.

## Webhooks

POST /webhooks/pluggy
POST /webhooks/asaas
POST /webhooks/telegram

Entrega externa é at-least-once; não exactly-once.

### Webhook Pluggy

event_id é identidade por origem. webhook_events possui UNIQUE (origem,event_id). Handler é idempotente e pode ser reexecutado por worker.

### Webhook Asaas — duplo lookup

Caminho 1:
SELECT * FROM payments WHERE asaas_payment_id = $asaas_id;

Se vazio:
SELECT * FROM payments WHERE id = $external_reference;

user_id vem de payments.user_id, nunca de um user_id externo.

Se externalReference não estiver no evento, recuperação pode fazer GET /payments/{asaas_payment_id} para obtê-lo.

Se ambos falharem:
- audit_log: payment_orfao;
- alerta operacional alto;
- HTTP 200.

Ao localizar por externalReference, validar que corresponde a payments.id antes de associar asaas_payment_id.

### PAYMENT_CONFIRMED — Política B

| Estado local | Ação |
|---|---|
| confirmado | no-op; não concede novamente |
| pendente | confirma e aplica periodo_dias |
| pendente_reconciliacao | associa/atualiza asaas_payment_id, confirma e aplica período |
| expirado | confirma, aplica período, audit payment_confirmado_tardio + dias_apos_expiracao |
| falhou | confirma, aplica período, audit payment_confirmado_apos_falha, severidade alta |

Aplicação:
- periodo_fim NULL ou < now() → now() + payment.periodo_dias;
- caso contrário → periodo_fim + payment.periodo_dias.

PAYMENT_CONFIRMED é suficiente para conceder o período segundo Política B. PAYMENT_RECEIVED representa saldo disponível e é semanticamente distinto.

### Alerta operacional

Job diário conta payment_confirmado_tardio e payment_confirmado_apos_falha. Mais de 5 em 7 dias gera alerta operacional.

## Paginação

| Endpoint | Ordenação |
|---|---|
| GET /transacoes | data DESC, id DESC |
| GET /transacoes/fila | criado_em DESC, id DESC |
| GET /alertas | criado_em DESC, id DESC |
| GET /contas | criado_em DESC, id DESC |
| GET /payments | criado_em DESC, id DESC |

Cursor opaco = valor da ordenação + id codificados. Máximo 500.

## Idempotency-Key

UNIQUE (user_id, rota, chave).

Estados: processando | concluido | falhou.

Máquina:
1. ausente → INSERT com payload_hash/status=processando; processa; só depois persiste response/status_http e status=concluido;
2. concluido + mesmo hash → devolve resposta persistida, sem nova cobrança;
3. concluido + hash diferente → 409 IDEMPOTENCY_KEY_REUSED;
4. processando → 409 IDEMPOTENCY_EM_ANDAMENTO + Retry-After: 1;
5. falhou → permite reprocessamento;
6. expira_em < now() → trata como nova; cleanup periódico.

Resposta parcial nunca é persistida.

Aceite:
A → QR + 201;
B mesma chave/payload → mesmo response, sem nova cobrança;
C payload diferente → 409;
D durante processamento → 409 + Retry-After 1;
E após falha → reprocessa.

## Erros

ErroAPI:
{erro, mensagem, detalhes?}

Códigos mínimos:
UNAUTHORIZED, FORBIDDEN, NOT_FOUND, CONFLICT, RATE_LIMIT,
VALIDATION_ERROR, UPSTREAM_INDISPONIVEL, IDEMPOTENCY_KEY_REUSED,
IDEMPOTENCY_EM_ANDAMENTO, CONFLITO_VERSAO.

Ownership é sempre verificado no backend.
