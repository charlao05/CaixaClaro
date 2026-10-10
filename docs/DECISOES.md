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

## 2026-09-27 — Telegram: ciclo /start provado E2E

Script de prova (descartado apos execucao):
  - obteve chat_id real via getUpdates
  - registrou usuario, gerou link_token
  - POST /webhooks/telegram com payload /start <token>
  - webhook retornou 200 vinculado=true
  - sendMessage entregou no Telegram (sem erro no handler)

Prova real dos 4 estagios do ciclo Telegram:
credencial valida -> token -> vinculacao -> resposta.
Arquivo temporario removido; codigo de producao intacto.

## 2026-09-27 — M7 fechado: alerta fiscal entregue ao Telegram

O criterio original "Alerta de DAS enviado" foi reinterpretado apos
leitura do codigo: faturamento.py so produz alertas do tipo
faturamento_faixa (cruzamento 60/80/90/95/100/120% do teto MEI).
Nao existe lembrete de DAS como feature — era escopo disfarcado.

Escopo efetivamente implementado:
  - FaturamentoResultado ganhou alertas_criados (RETURNING id no
    INSERT; ON CONFLICT DO NOTHING suprime duplicata sem eco)
  - services/notificacoes.enviar_alertas_telegram: best-effort,
    fora da transacao, chama telegram_bot.enviar_mensagem por alerta
  - /colar, /confirmar e worker chamam apos commit, com chat_id real
  - 4 testes cobrem envio, ausencia de chat_id, replay idempotente
    e ausencia de faixa cruzada

M7 fecha com todos os 4 criterios provados.


## 2026-10-03 — M11: Meu Negócio implementado (Fase 1+2)

Incremento do projeto com módulo "Meu Negócio": cadastro de produtos/serviços,
precificação (Categoria I da consulta ao CRC-ES) e movimentação manual de
estoque (Categoria II — consolidação de evento informado).

Escopo desta sessão, executado em etapas com evidência real a cada passo:
  - Migration 011_negocio.sql (products, stock_movements, pricing_scenarios)
  - domain/negocio/: taxonomia_movimento, estoque, precificacao (puros)
  - services/: produtos, estoque, precificacao
  - api/: produtos, estoque, precificacao
  - main.py: jsonable_encoder no handler de validação + 3 include_router
  - 51 testes novos distribuídos em 5 arquivos

Decisões de escopo tomadas durante a implementação:
  - Precificação limitada aos 4 itens já descritos em CONSULTA_CRC_ES.md
    (Categoria I). volume_hipotese é aceito e persistido, mas não deriva
    receita/lucro projetado — isso ficaria fora do que já foi submetido ao
    conselho, e REGRA_ORIENTADOR.md §7 pede revisão antes de ativar
    funcionalidade na fronteira.
  - Estoque tratado como Categoria II (consolidação de evento informado).
    Baixa automática a partir de transação confirmada NÃO foi implementada
    de propósito: o vínculo (referencia_transacao_id) existe no schema para
    o futuro, mas criar o movimento continua sempre ato explícito do
    usuário — o contrário violaria a regra de não transformar hipótese em
    fato sem confirmação.
  - Migration numerada 011 (não 010): colisão com
    010_payments_metodo_cancelado.sql, que já existia no repositório por
    trabalho concorrente (linha B, cartão avulso).

Bugs pré-existentes expostos e corrigidos (não eram do código novo isolado —
ver M11 em MILESTONES.md para detalhe técnico completo):
  - security/idempotency.py e security/audit.py recebendo UUID nativo do
    asyncpg sem str() nos novos pontos de chamada — corrigido nos call
    sites, replicando o padrão já usado em services/contas.py. Módulos de
    segurança compartilhados não foram alterados.
  - main.py:handler_validacao não serializava Decimal em erro de validação
    (500 em vez de 422) — primeira rota do projeto com campo Decimal
    validável a expor isso. Corrigido com jsonable_encoder.

Verificação final desta sessão: suíte completa do projeto, 521 passed,
0 failed, rodada contra PostgreSQL 16 real com as 11 migrations aplicadas
em sequência a partir de banco vazio.

Pendente, declarado e não escondido: nada deste milestone foi testado em
ambiente de produção real (depende de M10.C). Nenhuma das Fases 3–6 do
plano original (planilha, foto/OCR, API de ERP/CRM, alerta de estoque) foi
iniciada.

## 2026-10-07 — M12: recuperação de senha por Telegram

Canal inicial de recuperação de senha é Telegram. O endpoint de solicitação
responde 202 mesmo quando a conta não existe ou não possui Telegram, para
não revelar existência da conta.

O código tem 6 dígitos, é armazenado somente como SHA-256, expira em 15
minutos e é consumido uma única vez. Criar nova solicitação invalida a
anterior. Após reset bem-sucedido, todas as sessões ativas são revogadas.

O front orienta a vinculação prévia do Telegram. E-mail permanece fora do
M12 v1.


## 2026-10-07 — Operação: Cloudflare Tunnel com uma única réplica

Produção passa a operar com uma única réplica ativa do Cloudflare Tunnel.
A réplica concorrente que existia no Windows foi retirada do caminho de
produção após causar distribuição de requisições entre ambientes com bases
distintas.

Enquanto o Tunnel estiver em uso, HTTPS/TLS pertence à borda da Cloudflare;
o Caddy local atende o tráfego HTTP interno do compose.

## 2026-10-09 — Jornada do público-alvo (M13)

Auditoria da experiência real de MEI, autônomo no CPF, assalariado com renda
extra e pequeno negócio, registrada em docs/AUDITORIA_JORNADA_2026-10-09.md.
Oito decisões (D1–D8) foram tomadas na implementação e estão descritas lá,
com o motivo e o ponto do código onde reverter. As que mudam contrato:

- CONTRATOS_INTERNOS §6: `fato_confirmado` passa a significar "confirmado
  pelo usuário". Classificação automática, por mais confiante, é no máximo
  `leitura_provavel` (M4_CONTRATO §16; REGRA_ORIENTADOR §1).
- CONTRATOS_INTERNOS §6: cada opção de esclarecimento ganha `categoria`.
- GET /transacoes/fiscal/resumo: `teto_anual` e `percentual_consumido`
  podem ser `null` (quem não é MEI); campos novos de contagem e do mês.
- PATCH /transacoes/{id}/confirmar aceita `proposito` e `lembrar`.
- Rotas novas: PATCH /transacoes/{id}/corrigir, POST /transacoes/manual,
  GET /transacoes/opcoes-resposta.
- POST /auth/register aceita `regime`; omitido continua "MEI" (D7).
- Código de erro novo: PROPOSITO_INVALIDO.

Sem migration. Taxonomia v1 inalterada: "gasto pessoal", doação, rendimento
e dinheiro de terceiros entram como propósitos (padrão de M8-D3).

Pendente de decisão do responsável pelo produto: preço; taxonomia v2
(`receita_cpf`); default de regime da API; calendário de obrigações.

## 2026-10-09 — Revisão do M13 e correções pré-lançamento (M14)

Revisão independente do M13 e correção dos defeitos encontrados no `main`,
registradas em docs/AUDITORIA_JORNADA_2026-10-09.md, seção 8 (achados R1–R13,
decisões DR1–DR11, um commit por correção). Mudanças de contrato:

- ContextoClassificacao: `regras_pessoais` (regra com direção
  entrada/saída) substitui o `personal_propositos` introduzido pelo M13.
  `personal_rules` (M4_CONTRATO §5) não muda.
- fiscal_state / GET /transacoes/fiscal/resumo: `faturamento_acumulado` é
  a soma dos lançamentos gravados do ano (M4_CONTRATO §9), não mais um
  contador por deltas. `ano_referencia` passa a ser o ano mais recente com
  lançamento, sem passar do ano corrente. Os campos não mudam.
- Alerta de faixa (M4_CONTRATO §10): avaliado pelo faturamento atual do ano
  de cada lançamento escrito; inserido se ainda não existir para o prazo.
- Migration 013: índice transactions(user_id, data) e backfill das
  confirmações gravadas antes do M13.
- POST /transacoes/extrato/colar e /importar: campo `possiveis_repetidos`.
- Rotas novas: DELETE /transacoes/{id}, DELETE /transacoes/lotes/{lote_id},
  DELETE /transacoes/lotes/{lote_id}/repetidos. Lançamento de origem
  `pluggy` não é apagado (409 ORIGEM_BANCARIA). Lote inexistente: 404
  LOTE_NAO_ENCONTRADO. Sem Idempotency-Key (DELETE é idempotente).
- GET /transacoes/{id}/opiniao: campo `origem`.
- GET /billing/status: campo `acesso` (liberado, situacao, teste_ate);
  `ultimo_payment` ganha `plano` e `metodo`. GET /payments: `metodo`.
- POST /billing/checkout: pendente do mesmo plano fora do prazo local vira
  `expirado` antes de criar a cobrança nova (auditoria
  PAGAMENTO_PENDENTE_EXPIRADO).
- IP do cliente para limite de tentativas e auditoria: o Caddy envia
  `X-CaixaClaro-Conexao`; `CF-Connecting-IP` só vale quando essa conexão é
  interna (security/ip_cliente.py).
- Log: `httpx`/`httpcore` em WARNING; toda linha passa por máscara de token
  de bot e CPF.
- backup-vps.sh: código de saída 2 quando a cópia no R2 falha ou não está
  configurada.

Pendente de decisão do responsável pelo produto: preço; cadência da
renovação (hoje uma cobrança nova por dia enquanto a assinatura `ativa` não
é paga); notificações do Asaas; demais itens da seção 8.3 da auditoria.

## 2026-10-10 — Saúde responde a HEAD; Caddyfile sob teste

Preparação do monitor externo de `/readyz` (último critério aberto de
M10.C). Evidência e ensaios em docs/OPERACAO_PRODUCAO_2026-10-07.md,
atualização de 2026-10-10.

- `/healthz` e `/readyz` passam a responder a HEAD, com o mesmo código do
  GET e sem corpo. Motivo: o FastAPI devolve 405 a HEAD numa rota que só
  declara GET, e monitores de uptime (e o `curl -I`) sondam com HEAD — o
  monitor acusaria queda com o site no ar. O HEAD não entra no esquema
  público da API. `/health` (legado) não muda.
- O `Caddyfile` passa a ter testes (backend/tests/test_caddyfile.py):
  leitura do arquivo, sempre; Caddy de verdade, quando há um binário. O
  workflow de testes do backend baixa o Caddy 2.11.7 com checksum fixo e
  passa a rodar também quando só o `Caddyfile` muda. Motivo: a correção do
  IP do cliente (DR7) e o monitor de `/readyz` dependem do Caddyfile, e
  nada o verificava.
- `{remote_host}` e `{http.request.remote.host}` são a mesma configuração:
  o adaptador do Caddyfile troca a primeira pela segunda. O repositório
  mantém a grafia curta; não há correção a versionar.

Observação: a imagem de produção usa a tag flutuante `caddy:2-alpine`
(frontend/Dockerfile). A versão do Caddy que roda no VPS é a que foi
baixada na última construção da imagem `web`. O CI fixa uma versão para o
teste; não fixa a de produção.
