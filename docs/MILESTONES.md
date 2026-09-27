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

## M3a — Ingestão pura

Origem: M3 original foi repartido em M3a e M3b. O critério original
"POST /transacoes/extrato/colar retorna classificação" era erro do plano:
misturava ingestão com classificação. Classificação é M4.

Critérios:
  - [ ] POST /transacoes/extrato/colar parseia e persiste (sem classificar)
  - [ ] POST /transacoes/importar aceita CSV e OFX, convergindo para o mesmo formato
  - [ ] GET /transacoes com paginação por cursor (data DESC, id DESC)
  - [ ] Idempotency-Key obrigatório em ambos os POSTs
  - [ ] valor é string decimal na API; JSON number retorna 422
  - [ ] line_index 0-based pós-parser
  - [ ] needs_review = NULL em toda transação de M3a
  - [ ] Isolamento por usuário garantido
  - [ ] Bateria de M3a passando (12 critérios de docs/M3a_CONTRATO.md §7)

## M3b — Pluggy

Depende de credencial externa (trial Pluggy).

Critérios:
  - [x] POST /contas/conectar retorna connect token
  - [x] Webhook item/created fecha ciclo (consent + accounts + sync_requests)
  - [x] Bateria C (H2 clientUserId) executada
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
  - [x] Checkout com Idempotency-Key
  - [x] GET antes de POST obrigatório (property testável)
  - [x] Claim persistente = exclusão mútua
  - [x] Webhook com duplo lookup (asaas_payment_id + externalReference)
  - [x] user_id do payment local (não do evento)
  - [x] PAYMENT_CONFIRMED × 5 estados de payment (matriz completa)
  - [x] Política B (confirmação tardia) auditada
  - [~] 4 testes de aceite de B11/B12 — PENDENTE: definicao perdida em compactacao (c3ec0fc)
  - [x] corrida entre workers e crash após POST sem persistência de ID provados

## M6 — Workers
Critérios:
  - [x] Bateria B de concorrência: exatamente 1 worker processa cada evento
  - [x] Renewal implementado
  - [x] 6 comportamentos de renewal provados
  - [x] Pausa bloqueia cobrança
  - [x] Falha de rede → 'pendente_reconciliacao', nunca 'falhou' silencioso

## M7 — Telegram
Critérios:
  - [x] Bot real responde /start
  - [x] Token único ativo por usuário (coluna ativo)
  - [x] Chat_id vinculado ao usuário correto
  - [x] Alerta fiscal existente entregue ao Telegram (faturamento_faixa)

## M8 — Frontend conectado
Critérios:
  - [ ] Componentes consomem API
  - [ ] Motor fiscal não existe no bundle
  - [ ] Maria Silva apenas em modo demonstração
  - [ ] services/api.ts injeta JWT
        PULADO: nenhum artefato frontend no repositorio atual.

## M9 — Eval em CI
Critérios:
  - [x] Golden dataset versionado em tests/golden/
  - [x] CI roda eval a cada push
  - [x] Resultado publicado em /api/v1/eval/ultima-execucao
  - [ ] Bateria A–H executada
        BLOQUEADO: definição operacional não recuperável.
        Ver docs/M9.3_DECISAO.md §Fora de escopo.

## M10 — Produção
Critérios:
  - [ ] Deploy em ambiente real
        DECIDIDO: VPS container-first. Ver docs/M10_DECISAO.md.
  - [ ] Backup e observabilidade ativos
  - [ ] Rollback ensaiado
  - [ ] Primeiro usuário real end-to-end
        ABERTO: via API ou via UI? Depende de M8.
