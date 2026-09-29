# Milestones

## M0 — Reconciliação documental
Critérios de aceite:
  - [ ] 8 documentos existem no commit
  - [ ] Nenhuma perda material vs M0 v1.6 aprovado
  - [ ] Inspeção de integridade PASS
  - [ ] Commit raiz com mensagem "chore: establish CaixaClaro M0..."

## M1 — Backend base + auth + perfil
**Estado reconciliado em 27/09/2026 contra ea86998: implementado e testado.**

Critérios:
  - [x] docker compose up sobe backend + postgres
  - [x] Migration 001 executa sem erro
  - [x] POST /auth/register → 201 com JWT
  - [x] POST /auth/login → 200 com JWT
  - [x] POST /auth/logout → 200; JWT revogado é rejeitado
  - [x] GET /perfil, PATCH /perfil funcionam
  - [x] JWT.exp == sessions.expira_em (verificado)
  - [x] telegram_chat_id fora do PATCH /perfil
  - [x] Testes de aceite de cada endpoint PASS

## M2 — Segurança
**Estado reconciliado em 27/09/2026 contra ea86998: implementado e testado no desenho atual.**

Critérios:
  - [x] CPF armazenado como HMAC + AES-GCM; nunca claro
  - [x] JWT tem expiração; sessão revogada rejeitada
  - [x] Cadastro duplicado retorna 409
  - [x] Rate limit de login comprovado
  - [x] Auditoria de tentativa falha

> Observação: rate limiting continua por processo; isso não é tratado como
> bloqueio enquanto o alvo M10a permanece uma VPS única.

## M3a — Ingestão

Origem: M3 original foi repartido em M3a e M3b. O critério original
"POST /transacoes/extrato/colar retorna classificação" era erro do plano:
misturava ingestão com classificação.

**Estado reconciliado em 27/09/2026 contra ea86998: implementação presente
e bateria executada, com uma divergência arquitetural em relação ao
contrato histórico de "ingestão pura".**

Critérios:
  - [x] POST /transacoes/extrato/colar parseia e persiste
  - [x] POST /transacoes/importar aceita CSV e OFX, convergindo para o mesmo formato
  - [x] GET /transacoes com paginação por cursor (data DESC, id DESC)
  - [x] Idempotency-Key obrigatório em ambos os POSTs
  - [x] valor é string decimal na API; JSON number retorna 422
  - [x] line_index 0-based pós-parser
  - [~] needs_review = NULL em toda transação de M3a — contrato histórico
        não corresponde mais ao fluxo atual: M4 classifica/triage no mesmo
        passo transacional da ingestão
  - [x] Isolamento por usuário garantido
  - [x] Bateria de M3a passando, com dívidas de evidência D1–D5 registradas

> **Reconciliação M3a × M4:** o estado atual não deve ser "corrigido" para
> voltar a needs_review = NULL. A implementação posterior de M4 incorporou
> classificação e triagem no mesmo passo transacional da ingestão. O
> contrato/documentação histórica é que precisa ser atualizado em revisão
> específica, se desejado.

## M3b — Pluggy

Depende de credencial externa (trial Pluggy).

Critérios:
  - [x] POST /contas/conectar retorna connect token
  - [x] Webhook item/created fecha ciclo (consent + accounts + sync_requests)
  - [x] Bateria C (H2 clientUserId) executada
## M4 — Inteligência fiscal
**Estado reconciliado em 27/09/2026 contra ea86998: implementado; eval atual PASS.**

Critérios:
  - [x] Classificação roda no servidor
  - [x] Guardrails bloqueiam casos NUNCA
  - [x] Parecer de 7 estágios gerado no servidor
  - [x] fiscal_state atualizado no mesmo passo da ingestão
  - [x] Golden dataset em tests/golden/
  - [x] Eval contra golden dataset: zero violações NUNCA
  - [x] Sync não sobrescreve confirmação do usuário

> O PASS do golden/eval é evidência sobre o dataset versionado atual; não
> é uma garantia de comportamento universal fora dessa cobertura.

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
        DECIDIDO: VPS container-first. Ver docs/M10_DECISAO_2026-08.md.
  - [ ] Backup e observabilidade ativos
  - [x] Rollback ensaiado
        ENSAIO MECÂNICO LOCAL: retag da imagem anterior + recreate de api/worker.
  - [ ] Primeiro usuário real end-to-end
        ABERTO: via API ou via UI? Depende de M8.
