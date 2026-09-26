# Reconciliação da arquitetura

## Responsabilidades
React é consumidor da API. Backend concentra autenticação, domínio financeiro, ingestão, classificação, fiscal, billing, webhooks e auditoria. PostgreSQL é a fonte de verdade.

## Integrações
Pluggy fornece conexão bancária e sincronização. Asaas fornece cobrança PIX avulsa controlada pelo CaixaClaro. Telegram usa webhook e token temporário.

## Asaas
Cada cobrança local possui payments.id, enviado como externalReference. externalReference é identidade de reconciliação, não garantia de idempotência do POST do Asaas.

## Trial
Trial de 7 dias sem cartão.

## Fiscal
Fontes fiscais possuem proveniência. Fonte não verificada pode ser apresentada como pendente, mas não sustenta garantia ou penalidade.

## Firebase
Firebase Auth/Firestore ficam fora da arquitetura final. O protótipo Google AI Studio não é fonte de verdade.

## Sync
POST /contas/{id}/sync é assíncrono e retorna 202 com sync_id. O worker não sobrescreve decisões de confirmação do usuário.

## Workers
Claims persistentes sobrevivem à transação, permitem recuperação de stale e impedem processamento concorrente do mesmo trabalho.
