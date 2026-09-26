# Decisões arquiteturais

## 2026-09-26 — M0
M0 congela arquitetura, contratos e fronteiras antes do primeiro código.

## 2026-09-26 — Firebase fora
Firebase Auth e Firestore não fazem parte da arquitetura final. Autenticação e persistência pertencem ao backend/PostgreSQL.

## 2026-09-26 — Trial sem cartão
Trial de 7 dias não exige cartão.

## 2026-09-26 — Asaas PIX one-off
Cobranças PIX são avulsas e controladas pelo CaixaClaro; não há assinatura recorrente do Asaas como fonte econômica.

## 2026-09-26 — externalReference
payments.id é enviado como externalReference para reconciliação. Não se presume idempotência garantida pelo Asaas.

## 2026-09-26 — Política B
PAYMENT_CONFIRMED libera o período contratado. PAYMENT_RECEIVED representa disponibilidade do saldo e tem semântica distinta.

## 2026-09-26 — Claim em payments é exclusão mútua
Checkout, renovação e reconciliação obtêm claim persistente. Depois do claim, sempre consultam Asaas por externalReference antes de decidir entre adoção e POST. Nenhum POST sem GET prévio vazio.

Motivo: evitar duplicação quando POST externo ocorreu e o processo morreu antes de persistir asaas_payment_id.

## 2026-09-26 — user_id no webhook
Payload Asaas não fornece user_id do CaixaClaro. Lookup por externalReference usa payments.id; user_id é lido de payments.user_id.

## 2026-09-26 — CPF
HMAC para busca e AES-GCM para armazenamento reversível.

## 2026-09-26 — CNPJ
Pode ser armazenado em claro; assimetria com CPF é intencional e documentada.

## 2026-09-26 — Decimal
Monetário usa Decimal/Numeric.

## 2026-09-26 — Sessão revogável
JWT contém session id e login cria sessão revogável.

## 2026-09-26 — Sync assíncrono
Sincronização bancária retorna 202 e é processada por worker.

## 2026-09-26 — Fonte fiscal
Fonte não verificada é exibida como pendente e não sustenta garantia ou penalidade.

## 2026-09-26 — Critério de parada
Milestone só reabre por (a) contradição, (b) impossibilidade técnica, (c) afirmação externa não verificada ou (d) risco de perda de dado/dinheiro.
