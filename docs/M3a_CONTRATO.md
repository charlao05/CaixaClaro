# M3a — Ingestão pura

## 1. Escopo

M3a ingere, normaliza e persiste transações. Não classifica.

    transação recebida
       | parse
       v normalização (só para identidade)
       | persistência
    categoria = NULL
    needs_review = NULL

Classificação, guardrail de CPF e parecer tributário são M4.

## 2. Endpoints

### POST /api/v1/transacoes/extrato/colar

Autenticação:  requerida (Bearer JWT)
Headers:       Idempotency-Key obrigatório (UUID v4)
Request:       { "texto": string }
Response 201:  { "paste_id": string, "importados": number, "itens": [TransacaoResumo] }
Erros:         400 EXTRATO_ILEGIVEL
               401 UNAUTHORIZED
               409 IDEMPOTENCY_KEY_REUSED
               409 IDEMPOTENCY_EM_ANDAMENTO
               422 VALIDATION_ERROR
Efeitos:       INSERT em transactions (origem='paste', paste_id, line_index)
               INSERT em audit_log
               INSERT em idempotency_keys
Idempotência:  HTTP  → Idempotency-Key
               Negócio → UNIQUE (user_id, paste_id, line_index)
Origem:        PostgreSQL
Aceite:        §7

### POST /api/v1/transacoes/importar

Autenticação:  requerida
Headers:       Idempotency-Key obrigatório
Request:       { "formato": "csv"|"ofx", "conteudo_base64": string }
Response 201:  { "import_id": string, "importados": number, "itens": [TransacaoResumo] }
Erros:         400 ARQUIVO_ILEGIVEL
               400 FORMATO_NAO_SUPORTADO
               401 UNAUTHORIZED
               409 IDEMPOTENCY_KEY_REUSED
               409 IDEMPOTENCY_EM_ANDAMENTO
               422 VALIDATION_ERROR
Efeitos:       INSERT em transactions (origem='csv'|'ofx', import_id, line_index)
               INSERT em audit_log
               INSERT em idempotency_keys
Idempotência:  HTTP  → Idempotency-Key
               Negócio → UNIQUE (user_id, import_id, line_index)
Origem:        PostgreSQL
Aceite:        §7

### GET /api/v1/transacoes

Autenticação:  requerida
Query:         desde? (YYYY-MM-DD), ate? (YYYY-MM-DD),
               limite? (1-500, default 100), cursor? (opaco)
Ordenação:     data DESC, id DESC
Response 200:  { "itens": [Transacao], "next_cursor": string|null, "has_more": boolean }
Erros:         401 UNAUTHORIZED
Origem:        PostgreSQL
Aceite:        §7

## 3. Semântica

### paste_id
sha256(texto_normalizado)[:16 caracteres hexadecimais]
texto_normalizado definido em CONTRATOS_INTERNOS §16.

### Duplicata de paste
Mesmo usuário, mesmo texto, Idempotency-Key nova:

- o índice UNIQUE (user_id, paste_id, line_index) impede INSERT novo
- todas as linhas já existentes são devolvidas em "itens"
- resposta: 201, importados=0
- audit_log registra a operação, mas o efeito é no-op econômico

### import_id
UUID v4 gerado pelo servidor. Um import_id por requisição de upload.

### line_index
0-based.
Posição do registro após parsing, não número de linha física.
Não inclui cabeçalho, linhas vazias nem registros descartados pelo parser.
CSV e OFX convergem para a mesma numeração quando os dados são os mesmos.

### needs_review
Em M3a: sempre NULL.
Estados:
  NULL  -> ainda não classificada
  false -> classificada, sem revisão pendente (M4)
  true  -> classificada, com revisão pendente (M4)

### valor
Na API, é sempre string decimal.
  Válidos:   "1234.56", "-50.00", "0.01"
  Inválidos: 1234.56 (JSON number), "R$ 1.234,56", "1,234.56", "1e3"
O parser de extrato/CSV/OFX pode aceitar formatos bancários variados
internamente e convertê-los para Decimal antes de persistir. A restrição
acima é do modelo HTTP da API, não do conteúdo bruto recebido.
JSON number -> 422 VALIDATION_ERROR.

### categoria
Em M3a: sempre NULL.

### Colunas preenchidas em M3a
id, user_id, origem, data, descricao_bruta, valor,
paste_id/import_id, line_index, criado_em, atualizado_em, versao=1.

### Colunas NÃO preenchidas em M3a
account_id, pluggy_tx_id, contraparte_cpf_hash, contraparte_cnpj,
categoria, proposito, patrimonio, tratamento_tributario,
confianca, needs_review, via, motivo, confirmado_por, confirmado_em.

### TransacaoResumo (resposta de colar/importar)
{ "id", "data", "descricao_bruta", "valor", "origem", "line_index" }

### Transacao (resposta de GET /transacoes)
Todos os campos acima, mais:
  "categoria": null | string
  "needs_review": null | boolean
  "criado_em": string
  "atualizado_em": string
  "versao": number

## 4. Normalização

Definida em CONTRATOS_INTERNOS §16.
Usada apenas para calcular paste_id.
Não gera coluna descricao_norm.

## 5. Erros

Formato: { "erro": string, "mensagem": string, "detalhes"?: object }
Códigos em M3a: UNAUTHORIZED, VALIDATION_ERROR,
IDEMPOTENCY_KEY_REUSED, IDEMPOTENCY_EM_ANDAMENTO,
EXTRATO_ILEGIVEL, ARQUIVO_ILEGIVEL, FORMATO_NAO_SUPORTADO.

## 6. Fora de escopo

- classificação (M4)
- guardrail de CPF (M4)
- parecer tributário (M4)
- Pluggy (M3b)
- sync_requests (M3b)
- frontend (M8)

## 7. Critérios de aceite

1. Colar 5 linhas -> 5 transações, categoria=NULL, needs_review=NULL.

2. Colar o MESMO texto 2x com Idempotency-Key DISTINTAS:
   - paste_id idêntico
   - nenhum INSERT novo (UNIQUE por (user_id, paste_id, line_index))
   - quantidade persistida permanece 5
   - line_index permanece 0..4
   - resposta: 201, importados=0, itens=[5 transações já existentes]

3. Colar o mesmo texto com a MESMA Idempotency-Key:
   - mesma resposta da primeira chamada, byte a byte
   - nenhum INSERT novo
   - audit_log NÃO registra nova operação

4. Mesma Idempotency-Key + payload DIFERENTE:
   -> 409 IDEMPOTENCY_KEY_REUSED

5. Upload CSV de 10 linhas -> 10 transações, origem='csv'.

6. Upload OFX de 10 linhas -> 10 transações, origem='ofx',
   mesmo formato interno que o CSV.

7. "R$ 1.234,56" dentro do texto colado -> persistido como Decimal("1234.56")
   (parser interno converte; a fronteira HTTP só vê string).

8. (removido — não se aplica a M3a; ver §3 valor)

9. Texto ilegível -> 400 EXTRATO_ILEGIVEL.

10. GET /transacoes de A não vê transações de B.

11. GET /transacoes ordena por data DESC, id DESC.

12. Cursor opaco devolve página seguinte sem repetir nem pular.
## 8. Fora do escopo atual (pendências e rejeições)

### G5 — Detecção de delimitador CSV
Status: PENDENTE DE ESPECIFICAÇÃO.

Heurística de contagem (;, vs ,) não é robusta: vírgulas dentro de
descrições em CSV delimitado por ; quebram a decisão. Fica pendente
de spec baseada em parser CSV real e casos de teste.

### G2 — Formato da Idempotency-Key
Status: REJEITADO.

DECISOES.md já fixou UUID v4. Relaxar para string arbitrária seria
reabrir decisão fechada sem motivo. Idempotency-Key continua UUID v4.

### §7.8 original — valor como JSON number
Status: REMOVIDO.

Nenhum endpoint de M3a recebe "valor" diretamente. A regra de
valor-como-string-decimal continua válida como princípio, mas será
testada quando houver endpoint que receba "valor" (M4).
