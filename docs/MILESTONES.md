# Milestones

## M0 — Reconciliação documental
Critérios de aceite:
  - [ ] 8 documentos existem no commit
  - [ ] Nenhuma perda material vs M0 v1.6 aprovado
  - [ ] Inspeção de integridade PASS
  - [ ] Commit raiz com mensagem "chore: establish CaixaClaro M0..."

## M1 — Backend base + auth + perfil
Critérios:
  - [ ] docker compose up sobe backend + postgres
  - [ ] Migration 001 executa sem erro
  - [ ] POST /auth/register → 201 com JWT
  - [ ] POST /auth/login → 200 com JWT
  - [ ] POST /auth/logout → 200; JWT revogado é rejeitado
  - [ ] GET /perfil, PATCH /perfil funcionam
  - [ ] JWT.exp == sessions.expira_em (verificado)
  - [ ] telegram_chat_id fora do PATCH /perfil
  - [ ] Testes de aceite de cada endpoint PASS

## M2 — Segurança
Critérios:
  - [ ] CPF armazenado como HMAC + AES-GCM; nunca claro
  - [ ] JWT tem expiração; sessão revogada rejeitada
  - [ ] Cadastro duplicado retorna 409
  - [ ] Rate limit de login comprovado
  - [ ] Auditoria de tentativa falha

## M3 — Ingestão
Critérios:
  - [ ] POST /transacoes/extrato/colar retorna classificação
  - [ ] Parsers CSV/OFX convergem para o mesmo formato
  - [ ] POST /contas/conectar retorna connect token Pluggy
  - [ ] Webhook item/created fecha ciclo (consent + accounts + transactions)
  - [ ] Bateria C (H2 clientUserId) executada
  - [ ] sync_requests segue claim persistente

## M4 — Inteligência fiscal
Critérios:
  - [ ] Classificação roda no servidor
  - [ ] Guardrails bloqueiam casos NUNCA
  - [ ] Parecer de 7 estágios gerado no servidor
  - [ ] fiscal_state atualizado no mesmo passo da ingestão
  - [ ] Golden dataset em tests/golden/
  - [ ] Eval contra golden dataset: zero violações NUNCA
  - [ ] Sync não sobrescreve confirmação do usuário

## M5 — Billing
Critérios:
  - [ ] Checkout com Idempotency-Key
  - [ ] GET antes de POST obrigatório (property testável)
  - [ ] Claim persistente = exclusão mútua
  - [ ] Webhook com duplo lookup (asaas_payment_id + externalReference)
  - [ ] user_id do payment local (não do evento)
  - [ ] PAYMENT_CONFIRMED × 5 estados de payment (matriz completa)
  - [ ] Política B (confirmação tardia) auditada
  - [ ] 4 testes de aceite de B11/B12
  - [ ] corrida entre workers e crash após POST sem persistência de ID provados

## M6 — Workers
Critérios:
  - [ ] Bateria B de concorrência: exatamente 1 worker processa cada evento
  - [ ] Renewal implementado
  - [ ] 6 comportamentos de renewal provados
  - [ ] Pausa bloqueia cobrança
  - [ ] Falha de rede → 'pendente_reconciliacao', nunca 'falhou' silencioso

## M7 — Telegram
Critérios:
  - [ ] Bot real responde /start
  - [ ] Token único ativo por usuário (coluna ativo)
  - [ ] Chat_id vinculado ao usuário correto
  - [ ] Alerta de DAS enviado

## M8 — Frontend conectado
Critérios:
  - [ ] Componentes consomem API
  - [ ] Motor fiscal não existe no bundle
  - [ ] Maria Silva apenas em modo demonstração
  - [ ] services/api.ts injeta JWT

## M9 — Eval em CI
Critérios:
  - [ ] Golden dataset versionado em tests/golden/
  - [ ] CI roda eval a cada push
  - [ ] Resultado publicado em /api/v1/eval/ultima-execucao
  - [ ] Bateria A–H executada

## M10 — Produção
Critérios:
  - [ ] Deploy em ambiente real
  - [ ] Backup e observabilidade ativos
  - [ ] Rollback ensaiado
  - [ ] Primeiro usuário real end-to-end
