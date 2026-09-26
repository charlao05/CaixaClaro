# Milestones

## M0 — Arquitetura e contratos
Fecha reconciliação, contrato API, contratos internos, decisões, estrutura e sequência de implementação.

M0 PASS exige oito documentos versionados, inspeção do commit e ausência de contradições conhecidas.

## M1 — Backend/API
Implementar endpoints e domínio faltantes contra contrato congelado. Mudanças de contrato exigem decisão registrada.

## M2 — Segurança
Hardening de auth, autorização, sessões, segredos, rate limiting e validação.

## M3 — Ingestão
Pluggy, CSV/OFX, paste, normalização, idempotência e sync. Verificar comportamentos externos em sandbox.

## M4 — Inteligência
Classificação, regras pessoais, guardrails, opinião fiscal, proveniência e autoridade backend.

## M5 — Billing
Checkout, idempotency keys, payments, Asaas PIX, webhooks, reconciliação, Política B, claims e testes de corrida/crash.

Propriedade: nenhum POST Asaas de criação sem GET prévio por externalReference retornando vazio.

## M6 — Workers
Webhook, sync e renewal com claims, stale recovery, tentativas, observabilidade e idempotência.

## M7 — Telegram
Webhook, token de vinculação e associação segura.

## M8 — Frontend
React como consumidor da API; remover Firebase e autoridade client-side.

## M9 — Eval CI
Golden dataset e baterias A–H no backend/CI, reproduzíveis e versionados.

## M10 — Produção
Deploy, observabilidade, backups, restauração testada, métricas e alertas.

### Regra de transição
Nenhum milestone é PASS por intenção. PASS exige execução, output e critério satisfeito.
