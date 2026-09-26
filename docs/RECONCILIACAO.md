# Reconciliação arquitetural (M0)

## 1. Estado real do repositório

| Item | Valor |
|---|---|
| Repositório | charlao05/CaixaClaro |
| Branch padrão | main |
| Commit anterior | 7dc3d4b (M0 consolidado, reprovado por perda material) |
| Estado deste documento | restauração integral dos contratos M0 v1.6 |

## 2. Arquitetura definitiva

React frontend → HTTPS + JWT → FastAPI /api/v1.

FastAPI concentra autenticação/autorização, domínio financeiro/fiscal, ingestão, classificação, guardrails, TaxOpinion, billing, reconciliação e auditoria.

FastAPI usa PostgreSQL como fonte de verdade e workers persistentes para webhook events, sync requests e renewal. Integrações externas: Pluggy, Asaas e Telegram.

Eval/golden dataset permanece no backend/CI, fora do bundle do cliente.

## 3. Decisões fechadas

| Área | Decisão |
|---|---|
| Auth | Email/senha + bcrypt + JWT HS256 + sessão revogável |
| JWT | sub, sid, iat, exp; JWT.exp == sessions.expira_em |
| Persistência | PostgreSQL |
| Frontend | React consumidor da API |
| CPF | HMAC para igualdade + AES-GCM para recuperação autorizada |
| CNPJ | Texto claro em contraparte, com retenção ligada à transação |
| Monetário | Decimal no domínio / NUMERIC no PostgreSQL |
| Trial | 7 dias sem cartão |
| Billing | Asaas PIX one-off controlado pelo CaixaClaro |
| externalReference | payments.id para reconciliação; não é garantia de idempotência do POST |
| Billing concorrente | claim persistente como exclusão mútua |
| Criação Asaas | GET por externalReference obrigatório antes de POST |
| Webhook Asaas | lookup por asaas_payment_id e fallback por payments.id |
| user_id webhook | sempre derivado do payment local |
| PAYMENT_CONFIRMED | Política B, aplicada nos cinco estados |
| Sync | assíncrono, com proteção da confirmação humana |
| Telegram | token temporário; somente webhook grava telegram_chat_id |
| Firebase | fora da arquitetura final |
| Fiscal | proveniência explícita; fonte não verificada não sustenta garantia/penalidade |
| Golden/eval | fora do frontend, versionado em tests/golden e executado em CI |
| Evidência | IMPLEMENTADO / VERIFICADO / PASS / PRODUÇÃO |
| Critério de parada | somente (a)-(d) definidos em PRINCIPIOS.md |

## 4. Inventário AI Studio × Python × destino

| Arquivo AI Studio | Ação | Destino |
|---|---|---|
| App.tsx | Reescrever | Consumidor da API |
| firebase/config.ts | Deletar | Substituído por services/api.ts |
| firebase/service.ts | Deletar | Substituído por services/api.ts |
| engine/classifiers.ts | Deletar | spec/classificacao.md |
| engine/guardrails.ts | Deletar | spec/guardrails.md |
| engine/taxOpinions.ts | Deletar | spec/tax_opinions.md |
| engine/taxonomy.ts | Deletar | spec/taxonomia.md |
| engine/parsers.ts | Deletar | domain/ingest/*.py |
| engine/textnorm.ts | Deletar | domain/ingest/normalizacao.py |
| engine/goldenDataset.ts | Deletar | tests/golden/ |
| engine/evalHarness.ts | Deletar | CI |
| engine/shadowTraffic.ts | Deletar | jobs/shadow_traffic.py |
| components/DashboardOverview.tsx | Reescrever | Consome API |
| components/IngestionCenter.tsx | Reescrever | Consome API |
| components/ReviewQueueStories.tsx | Ajustar | Consome API |
| components/GuardianAuditor.tsx | Renomear | RegrasLab.tsx |
| components/AlertsAndViral.tsx | Ajustar | Remove "100%", "garantia" |
| components/UnitEconomics.tsx | Reescrever | Trial sem cartão |
| components/TaxOpinionCard.tsx | Manter | Exibe o que o backend retorna |
| components/TopBar.tsx | Manter | Navegação |
| components/AccountSettingsModal.tsx | Ajustar | Sem Pluggy fake |
| components/ProfileSelectorModal.tsx | Manter | PATCH /perfil |
| data/mockInitialData.ts | Mover | data/demo.ts |

## 5. Matriz IMPLEMENTADO / VERIFICADO / PASS / PRODUÇÃO

| Área | IMPLEMENTADO | VERIFICADO | PASS | PRODUÇÃO |
|---|---|---|---|---|
| Documentação M0 | SIM | SIM, por inspeção | Pendente desta restauração | NÃO |
| Backend/API | NÃO | NÃO | NÃO | NÃO |
| Segurança | NÃO | NÃO | NÃO | NÃO |
| Ingestão | NÃO | NÃO | NÃO | NÃO |
| Inteligência fiscal | NÃO | NÃO | NÃO | NÃO |
| Billing | NÃO | NÃO | NÃO | NÃO |
| Workers | NÃO | NÃO | NÃO | NÃO |
| Telegram | NÃO | NÃO | NÃO | NÃO |
| Frontend | Protótipo fora do repo | NÃO | NÃO | NÃO |
| Eval | NÃO | NÃO | NÃO | NÃO |
| Produção | NÃO | NÃO | NÃO | NÃO |

A matriz não transforma inspeção documental em PASS. PASS só existe quando a evidência correspondente foi executada.

## 6. Regra de reconciliação

A arquitetura do protótipo AI Studio não é a arquitetura de produção. O destino autoritativo é o backend/CI/PostgreSQL descrito nos contratos M0. Nenhuma funcionalidade client-side é considerada implementada no backend apenas por existir no protótipo.
