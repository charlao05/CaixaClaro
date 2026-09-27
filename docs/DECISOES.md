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

## 2026-09-26 — Idempotency-Key com máquina de estados
Decisão: idempotency_keys tem estados processando / concluido / falhou. Retry durante processando retorna 409 com Retry-After: 1.

Motivo: v1.3 gravava response antes do Asaas responder; retry recebia resposta sem QR code.

Consequência: resposta só é persistida após operação concluir; retry durante processamento não devolve resposta parcial.

## 2026-09-26 — subscription.status='ativa' = habilitada para renovação
Decisão: ativa NÃO implica periodo_fim no futuro. Worker de renovação processa subscriptions com status=ativa e periodo_fim vencido.

Motivo: sem essa semântica explícita, M1/M6 poderia tratar ativa como período vigente e nunca renovar as vencidas.

## 2026-09-26 — Fonte fiscal
Fonte não verificada é exibida como pendente e não sustenta garantia ou penalidade.

## 2026-09-26 — Critério de parada
Milestone só reabre por (a) contradição, (b) impossibilidade técnica, (c) afirmação externa não verificada ou (d) risco de perda de dado/dinheiro.

## 2026-09-26 — M3 repartido em M3a (ingestão) e M3b (Pluggy)

**Decisão:** M3a entrega ingestão pura (colar, CSV, OFX, persistência,
Decimal, paginação) sem classificação. M3b entrega Pluggy (connect token,
webhook item/created, sync_requests).

**Motivo:** o critério original "POST /transacoes/extrato/colar retorna
classificação" misturava M3 e M4. Além disso, M3b depende de credencial
externa (trial Pluggy) e não pode ser fechado por bateria local.

**Consequência:** `MILESTONES.md` deixa de ter M3 como bloco único.
Classificação fica inteiramente em M4.

## 2026-09-26 — line_index 0-based pós-parser

**Decisão:** `line_index` é a posição do registro após o parsing, começando em 0.

**Motivo:** precisa ser determinístico sobre a mesma entrada. "Linha física"
acopla a identidade ao formato (cabeçalho, linhas em branco, quebras CRLF/LF).

**Consequência:** CSV e OFX convergem para a mesma numeração quando os
dados são os mesmos.

## 2026-09-26 — import_id é UUID novo por upload

**Decisão:** cada requisição a `POST /transacoes/importar` gera um novo
`import_id` (UUID v4).

**Motivo:** previsível. Reenvio explícito do mesmo arquivo pelo usuário é
decisão dele; retry acidental de HTTP é responsabilidade do Idempotency-Key.

**Consequência:** combinar com Idempotency-Key obrigatório; sem ele, retry
duplicaria tudo.

## 2026-09-26 — needs_review com três estados

**Decisão:** `needs_review` é BOOLEAN nullable.
  NULL  → ainda não classificada (M3a)
  false → classificada, sem revisão pendente (M4)
  true  → classificada, com revisão pendente (M4)

**Motivo:** separa ingestão (M3a) de inteligência fiscal (M4) sem
forçar um valor falso durante a ingestão.

**Consequência:** M3a nunca escreve true nem false.

## 2026-09-26 — Idempotency-Key obrigatório em ingestão

**Decisão:** `POST /transacoes/extrato/colar` e `POST /transacoes/importar`
exigem header Idempotency-Key (UUID v4).

**Motivo:** com import_id novo por upload, retry de HTTP duplicaria.
Idempotency-Key protege o HTTP; UNIQUE da transação protege o negócio.
São proteções distintas e complementares.

**Consequência:** payload_hash é calculado sobre o **corpo efetivo da
requisição**, antes de qualquer UUID gerado pelo servidor.

## 2026-09-26 — valor é string decimal na API

**Decisão:** `valor` entra e sai da API como string decimal ("1234.56").
JSON number e notação científica são rejeitados com 422.

**Motivo:** JSON number não preserva semântica decimal.

**Consequência:** o parser interno pode aceitar formatos bancários, mas a
fronteira HTTP é estrita.

## 2026-09-26 — Normalização de identidade mora em CONTRATOS_INTERNOS §16

**Decisão:** o algoritmo de normalização usado para `paste_id` é §16 de
CONTRATOS_INTERNOS. `specs/textnorm.md` nunca existiu em commit e não será
criado.

**Motivo:** é contrato interno curto; não justifica pasta `specs/`.

**Consequência:** `ESTRUTURA.md` deixa de listar `specs/textnorm.md`.

## 2026-09-27 — connect_token sem expira_em

Pluggy nao retorna `expiresAt` em /connect_token; nosso response
devolve expira_em: null. TTL real e 30 min (doc Pluggy). Corrigir
quando alguem precisar do campo — nao bloqueia M3b.

## 2026-09-27 — M6 fechado por testes; prova operacional Asaas pendente

Renewal e sync worker implementados e cobertos por 19 testes
(13 sync + 6 renewal). Prova operacional ponta-a-ponta do renewal
contra Asaas sandbox nao executada por ausencia de ASAAS_API_KEY
no .env. Worker persistente foi observado rodando e a guard clause
de configuracao funciona (uma linha, sem retry).

Reabrir M6 apenas se: (a) credencial Asaas sandbox for obtida e o
renewal real falhar; (b) algum dos 6 comportamentos do §12 divergir
em uso real.

## 2026-09-27 — M7 fechado parcialmente; bot real pendente

Vinculacao Telegram por token implementada e coberta por 8 testes
(token unico ativo, /start <token> grava chat_id, token expirado,
token invalido, update_id duplicado, payload invalido, /start sem
token, auth obrigatoria).

Pendentes por ausencia de credencial Telegram (bot token):
  - bot real respondendo /start
  - envio de alerta de DAS

Reabrir M7 apenas se: (a) credencial Telegram obtida e algum
comportamento divergir; (b) algum dos 2 criterios pendentes exigir
mudanca de contrato.

## 2026-09-27 — Telegram: credencial real validada via getMe

`GET https://api.telegram.org/bot<TOKEN>/getMe` retornou
{"status": 200, "ok": true, "username": "CaixaClaroBot"}.
Confirma que TELEGRAM_BOT_TOKEN está correta e que o backend
consegue autenticar na Bot API. Nao prova ainda o ciclo
/start -> vinculacao -> resposta (isso exige entrega real,
registrado em §M7 da DECISOES).
