# Contratos internos — CaixaClaro M0

Cada contrato abaixo é pré-requisito de implementação. Um contrato é aprovado quando: (1) está escrito aqui, (2) tem teste de aceite associado, (3) o teste passa.

---

## 1. JWT / session lifecycle

Payload:
  { "sub": user_id, "sid": session_id, "iat": unix, "exp": unix }

Assinatura: HS256 com JWT_SECRET (>= 32 bytes).

Invariante: JWT.exp == sessions.expira_em (mesmo instante, unidades diferentes).

Dependência de auth em toda rota protegida:
  1. Lê Authorization: Bearer <token>
  2. Verifica assinatura
  3. Verifica exp > now()
  4. SELECT * FROM sessions WHERE id = sid
     AND revogada_em IS NULL AND expira_em > now()
  5. Verifica sessions.user_id == sub
  6. Falha em qualquer passo → 401

Aceite:
  - login → JWT válido
  - logout → sessions.revogada_em preenchido
  - JWT ainda dentro do exp após logout → 401
  - JWT expirado → 401 (sem consultar sessions)

---

## 2. CPF — contrato criptográfico

Entrada: CPF string; normalizado via \D → 11 dígitos.

Derivação:
  cpf_hmac = HMAC-SHA256(CPF_HMAC_KEY, cpf_digitos)
  → users.cpf_hash (UNIQUE) — busca por igualdade

Cifragem:
  nonce = os.urandom(12)
  payload = nonce || AES-GCM(CPF_AES_KEY, nonce, cpf_digitos)
  → users.cpf_cifrado (BYTEA) — exibição ao titular

Regras absolutas:
  - CPF claro nunca persistido
  - CPF claro nunca em audit_log
  - CPF claro nunca em log de aplicação
  - CPF claro em resposta de API apenas em GET /perfil do próprio titular
  - CPF claro enviado a terceiros apenas para Asaas (criação de customer)

---

## 3. Identidade de transação / idempotência

Cada origem tem sua chave:

| Origem | Chave UNIQUE |
|---|---|
| pluggy | (user_id, pluggy_tx_id) WHERE pluggy_tx_id NOT NULL |
| paste | (user_id, paste_id, line_index) |
| csv/ofx | (user_id, import_id, line_index) |
| manual | (user_id, id) — sem deduplicação por conteúdo |

Proibido: hash de (data, descricao, valor) como chave — colide em transações economicamente distintas.

Colunas em transactions:
  origem TEXT NOT NULL
  paste_id TEXT
  import_id TEXT
  line_index INTEGER

---

## 4. Schema do resultado de classificação

ClassificacaoResultado:
  categoria: string
  proposito: string
  origem_sugerida: string
  patrimonio: pessoa_fisica | atividade_negocio | ponte_pf_pj | transito_terceiro
  tratamento_tributario: tributavel_irpf | isento_nao_tributavel | carne_leao_potencial | faturamento_pj | retencao_fonte | indeterminado_pendente
  confianca: number
  needs_review: boolean
  via: regra_personalizada | heuristica | guardrail | usuario
  motivo: string | null

---

## 5. Schema do resultado de guardrail

GuardrailResultado:
  aplicado: boolean
  categoria_original: string
  categoria_corrigida: string
  motivo: string
  regra_acionada: cpf_proprio | emprestimo | estorno | ponte_pf_pj | tributo | null

---

## 6. Schema de TaxOpinion

TaxOpinion:
  fato: string
  interpretacao: string
  relacao_pf_pj: string
  possivel_tratamento_tributario: string
  condicoes_necessarias: string
  pendencias: string
  proximo_passo: string
  grau_certeza_leitura: fato_confirmado | leitura_provavel | duvida_declarada
  opcoes_esclarecimento?: Array<{ label: string; proposito: string; descricao: string }>

Contrato: generate_tax_opinion(tx, classif, context) não pode afirmar certeza maior do que a confiança que a classificação sustenta.

---

## 7. Semântica de período de billing

O payment carrega a intenção original:
  - payments.plano
  - payments.valor
  - payments.periodo_dias

subscription NUNCA decide período. Sempre lê do payment.

Regra do webhook PAYMENT_CONFIRMED:
  1. Localiza payment via asaas_payment_id, ou externalReference em recuperação.
  2. status='confirmado' → no-op.
  3. status em ('pendente', 'pendente_reconciliacao') → confirma, aplica período.
  4. status='expirado' → Política B: confirma, aplica período, audit reforçado.
  5. status='falhou' → confirma, aplica período, audit severidade alta.
  6. Se periodo_fim IS NULL ou periodo_fim < now():
       periodo_fim = now() + payment.periodo_dias
     Senão:
       periodo_fim = periodo_fim + payment.periodo_dias

Aceite:
  - cobrança mensal antiga confirmada depois de upgrade anual → concede 30 dias, não 365.

---

## 8. Semântica de entrega de webhook

Provedores entregam at-least-once, não exactly-once.

Garantias do sistema:
  - UNIQUE (origem, event_id) em webhook_events → linha única.
  - Handler precisa ser idempotente.
  - Worker pode reexecutar em recuperação de crash.

Garantia NÃO oferecida:
  - Execução única do handler.

Aceite:
  - mesmo event_id × 10 requisições → 1 linha, efeito econômico único.

---

## 9. Schema de evento de audit

AuditEvent:
  ator: sistema | usuario | webhook_pluggy | webhook_asaas | webhook_telegram | worker
  acao: string
  alvo: string | null
  meta: Record<string, unknown>
  criado_em: string

Regras absolutas:
  - CPF, senha, tokens, segredos NUNCA em meta.
  - IP e user_agent em meta apenas em ações de auth.

---

## 10. Schema de erro

ErroAPI:
  erro: string
  mensagem: string
  detalhes?: Record<string, unknown>

Códigos: UNAUTHORIZED, FORBIDDEN, NOT_FOUND, CONFLICT, RATE_LIMIT,
VALIDATION_ERROR, UPSTREAM_INDISPONIVEL, IDEMPOTENCY_KEY_REUSED,
IDEMPOTENCY_EM_ANDAMENTO, CONFLITO_VERSAO, CURSOR_INVALIDO.

---

## 11. Paginação

Todos os endpoints paginados usam cursor opaco e ordenação determinística:

| Endpoint | Ordenação |
|---|---|
| GET /transacoes | data DESC, id DESC |
| GET /transacoes/fila | criado_em DESC, id DESC |
| GET /alertas | criado_em DESC, id DESC |
| GET /contas | criado_em DESC, id DESC |
| GET /payments | criado_em DESC, id DESC |

Cursor = base64("<valor_ordenacao>|<id>").

---

## 12. Renewal lifecycle (M6)

Worker renovar_assinaturas.py roda a cada 6h.

Para cada subscription com status='ativa':
  se pausada_ate IS NOT NULL AND pausada_ate >= today:
    → não cobra; continue
  se periodo_fim IS NULL:
    → continue
  se periodo_fim > today + 3 dias:
    → continue
  se existe payment pendente com expira_em > now():
    → continue   # NÃO usar criado_em > now()-6h
  senão:
    → obter claim persistente
    → GET /payments?externalReference={novo_payment.id}
    → se retorna vazio: POST /payments
    → liberar claim

Seis comportamentos que precisam ser provados (bateria M6):
  1. Vencida → exatamente 1 cobrança
  2. Rodar 2x no mesmo dia → ainda 1 cobrança
  3. Payment pendente com expira_em no passado → nova cobrança permitida
  4. Pausa vigente → não cobra
  5. Pausa expirada → cobra
  6. Falha de rede → payment em 'pendente_reconciliacao', nunca 'falhou' silenciosamente

---

## 13. Idempotency-Key por (user_id, rota, chave)

UNIQUE (user_id, rota, chave).

Estados: 'processando' | 'concluido' | 'falhou'

Comportamento ao receber POST com Idempotency-Key=K na rota R:
  1. Chave não existe:
       INSERT (user_id, rota, chave, payload_hash, status='processando')
       Processa. Ao final: response + status_http + status='concluido'
  2. Chave existe, status='concluido', payload_hash IGUAL:
       Retorna response persistida com status_http persistido
  3. Chave existe, status='concluido', payload_hash DIFERENTE:
       409 IDEMPOTENCY_KEY_REUSED
  4. Chave existe, status='processando':
       409 IDEMPOTENCY_EM_ANDAMENTO
       Header Retry-After: 1
  5. Chave existe, status='falhou':
       Reprocessa
  6. Chave existe, expira_em < now():
       Trata como nova; cleanup remove periodicamente

Aceite:
  1. Chamada A → response com QR + 201
  2. Chamada B mesma chave, mesmo payload → mesmo response, sem nova cobrança
  3. Chamada C mesma chave, payload diferente → 409 KEY_REUSED
  4. Chamada D durante processamento → 409 EM_ANDAMENTO
  5. Chamada E após falhou → reprocessa

---

## 14. Tratamento de CNPJ

CPF: criptografado (HMAC + AES-GCM).

CNPJ: armazenado em texto claro em transactions.contraparte_cnpj.

Motivo:
  - CNPJ é público.
  - Não identifica PF diretamente.
  - MEI tem CNPJ divulgado em nota fiscal.
  - Criptografia dificultaria conciliação sem ganho real.

Exceção: se CNPJ for de MEI cujo titular não consentiu, exposição pode virar dado pessoal indireto.

Política de retenção:
  - CNPJ mantido enquanto a transação existir.
  - Removido com a transação.

---

## 15. Sync × confirmação do usuário

Campos originados do provedor que o worker PODE atualizar:
  - descricao_bruta, data, valor
  - contraparte_cpf_hash, contraparte_cnpj
  - pluggy_tx_id, conta_id

Campos decididos pelo usuário que o worker NUNCA sobrescreve:
  - categoria, proposito
  - confirmado_por, confirmado_em

UPDATE pelo worker:
  UPDATE transactions
     SET <campos do provedor>,
         versao = versao + 1,
         atualizado_em = now()
   WHERE id = $1 AND user_id = $2

Se confirmado_por IS NOT NULL:
  - atualiza SOMENTE campos do provedor;
  - NÃO toca em categoria, proposito, confirmado_por, confirmado_em;
  - incrementa versao mesmo assim.

Aceite:
  - Usuário confirma categoria=X → confirmado_por preenchido.
  - Sync roda → categoria permanece X.
  - Sync nunca apaga decisão do usuário.

---

## Nota A — Semântica de subscription.status='ativa'

subscription.status='ativa' significa: "assinatura está habilitada para renovação". NÃO significa que periodo_fim está no futuro.

Estados possíveis:
  - status='ativa', periodo_fim=ontem → renovação pendente.
  - status='ativa', periodo_fim=daqui a N dias → situação normal.
  - status='pausada', pausada_ate=futuro → renovação suspensa.

Não introduzimos status 'expirada' agora. Se a frequência de assinaturas com periodo_fim muito no passado virar grande, reavalia-se.

---

## Nota B — Alerta operacional de confirmação tardia

Job diário conta no audit_log:
  - payment_confirmado_tardio
  - payment_confirmado_apos_falha

Se > 5 em 7 dias: alerta operacional.
Motivo: jobs de expiração/reconciliação desalinhados com o Asaas real.

---

## 16. Normalização para identidade do paste

Aplica-se somente ao cálculo de `paste_id`. Não gera coluna adicional.
Não define normalização de `descricao_bruta`.

Algoritmo determinístico:

    1.  Entrada é string Unicode.
    2.  Normalizar Unicode com NFKD.
    3.  Remover marcas combinantes (acentos).
    4.  Converter para lowercase.
    5.  Normalizar quebras de linha: CRLF e CR -> LF.
    6.  Colapsar qualquer sequência de whitespace em um único espaço.
    7.  Strip nas extremidades.
    8.  Codificar o resultado em UTF-8.
    9.  SHA-256 do resultado.
    10. Usar os primeiros 16 caracteres hexadecimais do digest como paste_id.

Notas:

- O passo 5 é logicamente absorvido pelo passo 6 (todas as quebras de
  linha são whitespace). Mantido por clareza de intenção.
- Não removemos pontuação, símbolos ou caracteres não alfanuméricos.
  Se um dia isso for necessário, é decisão explícita — não está
  autorizado por este contrato.
- Exemplo: "  PIX  João\r\n" e "PIX JOÃO" produzem ambos "pix joao" e,
  portanto, o mesmo paste_id.
