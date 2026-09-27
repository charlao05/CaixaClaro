# M4 — Contrato: Inteligência Fiscal (v1)

Status: PROPOSTO. Aguardando segunda auditoria pós-patch.
Referência: docs/CONTRATOS_INTERNOS.md §4 (e §4.1 novo), §5, §6, §15.
Milestone anterior: M3a PASS.

---

## 1. Escopo

M4 entrega classificação fiscal determinística, guardrail de titularidade,
triagem em três destinos, estado fiscal e alertas de faixa de faturamento.
Tudo dentro da mesma unidade transacional da ingestão (Arquitetura A, §15).

Entra em M4:
- taxonomia v1 (promovida a CONTRATOS_INTERNOS §4.1)
- classificador determinístico (regras, sem LLM, sem rede)
- guardrail de CPF (5 regras, alinhado a CONTRATOS_INTERNOS §5)
- triagem (silencioso / confirmação / fila de revisão)
- `needs_review` preenchido (false ou true)
- `fiscal_state.faturamento_acumulado` atualizado no mesmo passo
- alertas de faixa de faturamento (60/80/90/95/100/120%)
- golden dataset v1 + harness de eval
- métricas A–D e severidade

Não entra em M4:
- LLM (reabre Arquitetura A — §15)
- Pluggy / sync (M3b)
- Billing (M5)
- Workers assíncronos (M6)
- Frontend (M8)
- Telegram (M7)
- Alertas de obrigação fiscal (DAS / DASN-SIMEI / IRPF) — pertencem a M7,
  que é onde o calendário fiscal vira superfície própria
- TaxOpinion (§6 do CONTRATOS_INTERNOS) — fora de M4 v1
- Comparação de CNPJ do titular (D-M4-1 = B; ver §6.3)

---

## 2. Taxonomia v1

Taxonomia oficial promovida a CONTRATOS_INTERNOS §4.1 (D-M4-4).
Este documento a reproduz para referência operacional.

Onze categorias. Cada uma com id estável, rótulo de exibição,
classificação econômica.

| id                      | rótulo                              | receita | despesa | neutra |
|-------------------------|-------------------------------------|---------|---------|--------|
| receita_servico         | Trabalho / Prestação de Serviço     | sim     | não     | não    |
| receita_venda           | Vendas de Produtos / Comércio       | sim     | não     | não    |
| salario                 | Salário Formal / Aposentadoria      | sim     | não     | não    |
| imposto_das             | Impostos e Tributos (DAS/IRPF/DARF) | não     | sim     | não    |
| taxas_tarifas           | Taxas Bancárias & Maquininha        | não     | sim     | não    |
| custo_operacional       | Gastos da Atividade / Trabalho      | não     | sim     | não    |
| transferencia_propria   | Transferência Entre Contas Próprias | não     | não     | sim    |
| pessoal_prolabore       | Retirada da Empresa / Pró-Labore    | não     | não     | sim    |
| reembolso               | Devolução / Reembolso               | não     | não     | sim    |
| emprestimo              | Empréstimo (peguei ou emprestei)    | não     | não     | sim    |
| outros                  | Aguardando Confirmação              | não     | não     | sim    |

---

## 3. Identificadores estáveis

`categoria` é dado persistido em `transactions.categoria`. Uma vez gravado,
o identificador é imutável.

- Renomear `receita_servico` para `receita_de_servico` NÃO é ajuste
  cosmético. É migração.
- Adicionar nova categoria é extensão. Vai para v2 da taxonomia.
- Remover categoria exige plano de migração dos dados existentes.

Identificadores em §2 são congelados até decisão explícita de v2.

---

## 4. TAXONOMIA_VERSION

Constante exportada em domain/fiscal/taxonomia.py:

    TAXONOMIA_VERSION = "v1"

O golden dataset declara contra qual versão foi avaliado.
O runner de eval compara `dataset.taxonomia_version` contra
`taxonomia.TAXONOMIA_VERSION` e recusa executar se houver divergência.

Não é coluna de banco. Não é dado de usuário. É metadado de código.

---

## 5. Classificação

Contrato completo definido em CONTRATOS_INTERNOS §4. M4 implementa
integralmente.

### Assinatura

    classificar_v2(
        descricao: str,
        valor: Decimal,
        contexto: ContextoClassificacao,
    ) -> ClassificacaoResultado

### ContextoClassificacao (entrada)

    {
      "personal_rules": dict[str, str],       # pode ser vazio
      "cpf_titular_hash": str | null,
      "cpf_contraparte_hash": str | null,
      "tipo_conta": "corrente" | "poupanca" | null,
      "regime": "MEI" | "SIMPLES" | "PF"
    }

### ClassificacaoResultado (saída)

Nove campos, conforme CONTRATOS_INTERNOS §4:

    categoria: str                    # id de §2
    proposito: str                    # id de DimensionPurpose
    origem_sugerida: str              # id de DimensionOrigin
    patrimonio: str                   # pessoa_fisica | atividade_negocio |
                                      #   ponte_pf_pj | transito_terceiro
    tratamento_tributario: str        # tributavel_irpf | isento_nao_tributavel |
                                      #   carne_leao_potencial | faturamento_pj |
                                      #   retencao_fonte | indeterminado_pendente
    confianca: float                  # 0.0 <= confianca <= 1.0
    needs_review: bool
    via: str                          # regra_personalizada | heuristica |
                                      #   guardrail | usuario
    motivo: str | null

### Precedência interna

    1. personal_rules  (via = "regra_personalizada")
    2. heurística determinística  (via = "heuristica")
    3. fallback: categoria="outros", needs_review=true  (via = "heuristica")

O resultado de (1), (2) ou (3) passa então pelo guardrail (§6).
O guardrail SEMPRE prevalece. Se ele reescreve a categoria, o
campo `via` do resultado efetivo passa a ser "guardrail".

### Regra absoluta

Entrada sem evidência NUNCA vira `receita_servico` por padrão. Cai
em `outros` com `needs_review=true`.

### Ordem de avaliação das heurísticas

    2.1 tributos (das, darf, carne leao, gps inss)
    2.2 salário e benefícios (salario, folha pagto, inss benef)
    2.3 empréstimos (emprestimo, financiamento, credito pessoal)
    2.4 devolução (estorno, devolucao, reembolso)
    2.5 transferência própria textual (minha poupanca, mesma titularidade)
    2.6 retirada de empresa (pro labore, retirada titular, distribuicao lucros)
    2.7 tarifas bancárias (tarifa, iof, mdr)
    2.8 custos operacionais (posto, combustivel, internet, etc.)
    2.9 venda (venda balcao, shopee)
    2.10 serviço por PJ (agencia ... ltda, servico prestado)

---

## 6. Guardrail CPF

Aplicado DEPOIS da classificação. Nunca antes.

### GuardrailResultado (saída)

Conforme CONTRATOS_INTERNOS §5:

    aplicado: bool
    categoria_original: str
    categoria_corrigida: str
    motivo: str
    regra_acionada: str | null
        # "cpf_proprio" | "emprestimo" | "estorno" |
        # "ponte_pf_pj" | "tributo" | null

`regra_acionada=null` significa "nenhum guardrail aplicado". Não é erro.

O guardrail NÃO define `needs_review`. Essa decisão é da triagem (§7).

### Dados de entrada

    cpf_titular_hash        → users.cpf_hash (via transactions.user_id)
    cpf_contraparte_hash    → transactions.contraparte_cpf_hash
    cnpj_contraparte        → transactions.contraparte_cnpj

Comparação é hash-a-hash (HMAC-SHA256 com CPF_HMAC_KEY, conforme
CONTRATOS_INTERNOS §2). NUNCA CPF em claro.

`users` NÃO tem coluna de CNPJ. Regra §6.3 usa apenas padrão textual
(D-M4-1 = B). Comparação por CNPJ do titular fica para v2.

### Cinco regras

#### 6.1 — Empréstimo nunca vira receita
    regra_acionada = "emprestimo"
    Se texto indica empréstimo/financiamento e categoria ∈ {receita_servico,
    receita_venda}, reescreve para "emprestimo".

#### 6.2 — Estorno nunca vira receita
    regra_acionada = "estorno"
    Se texto indica estorno/devolução/reembolso e categoria ∈ {receita_servico,
    receita_venda}, reescreve para "reembolso".

#### 6.3 — Ponte PF ↔ PJ (titular/sócio)
    regra_acionada = "ponte_pf_pj"
    Se padrão textual ("retirada titular", "distribuicao lucros", e categoria ∈ {"transferencia_propria",
      "pessoal_prolabore"}: reclassifica (1º caso)
      ou confirma (2º caso). Em ambos regra_acionada =
      "ponte_pf_pj" e a triagem §7.2 exige confirmação.
    para "pessoal_prolabore".

#### 6.4 — CPF próprio => transferência própria
    regra_acionada = "cpf_proprio"
    Se cpf_contraparte_hash == cpf_titular_hash e categoria ∈ {receita_servico,
    receita_venda}, reescreve para "transferencia_propria".

#### 6.5 — Tributo nunca vira gasto comum
    regra_acionada = "tributo"
    Se texto indica tributo ("das", "darf", "carne leao", "gps inss") e
    categoria ≠ "imposto_das", reescreve para "imposto_das".

Propósito: tributo textual (DARF, DAS, GPS INSS, CARNE LEAO) é sinal
factual inequívoco. §6.5 existe para impedir que `personal_rules`
sobreponha esse sinal. Sem essa defesa, uma personal_rule mal
configurada poderia classificar DARF como custo operacional.

### Registro

Os nomes usados aqui são os do contrato canônico (GuardrailResultado):
`aplicado`, `motivo`, `regra_acionada`. Não há `guardrail_applied`
nem `guardrail_motivo` — são equivalentes antigos que NÃO existem no
contrato atual.

Quando aplicado:
  aplicado = true
  motivo = <motivo da regra acionada>
  regra_acionada ∈ {cpf_proprio, emprestimo, estorno, ponte_pf_pj, tributo}
  audit_log: ação = "guardrail_cpf_bloqueio"

Quando não aplicado:
  aplicado = false
  regra_acionada = null
  motivo não é consultado
  audit_log não registra (não houve evento de guardrail)

---

## 7. Triagem

Três destinos, decididos em runtime por (categoria, `guardrail.aplicado`,
`guardrail.regra_acionada`, `via`).

Importante: a triagem NÃO usa `severidade`. Severidade é conceito de
eval (§14). Runtime não conhece `categoria_esperada`.

### 7.1 — silencioso
    Disposição: silencioso, needs_review=false.
    Critério:
      - via ∈ {regra_personalizada, heuristica}
      - guardrail.aplicado == false
      - categoria ≠ "outros"
    Ação: persistir, sem intervenção humana.

### 7.2 — confirmacao
    Disposição: confirmacao, needs_review=true.
    Critério:
      - guardrail.aplicado == true
        E guardrail.regra_acionada ∈ {"ponte_pf_pj", "tributo",
                                       "cpf_proprio", "emprestimo",
                                       "estorno"}
      OU
      - via == "heuristica"
        E 0.7 <= confianca < 0.9
        E categoria ≠ "outros"
    Ação: persistir, sinalizar para correção em um toque.

### 7.3 — fila_revisao
    Disposição: fila_revisao, needs_review=true.
    Critério:
      - categoria == "outros"
      OU
      - via == "heuristica" E confianca < 0.7
    Ação: persistir, rotear para fila.

### 7.4 — Exclusividade mútua das três disposições

As três disposições são mutuamente exclusivas. Ordem de avaliação:

    1. §7.3 fila_revisao  (categoria == "outros" OU confianca < 0.7)
    2. §7.2 confirmacao   (guardrail crítico OU 0.7 <= confianca < 0.9)
    3. §7.1 silencioso    (todo o resto)

A primeira que casar vence. Um lançamento nunca é classificado em
duas disposições simultaneamente.

---

## 8. needs_review — semântica final

    NULL   — ainda não classificado (M3a)
    false  — classificado, sem revisão pendente
    true   — classificado, revisão pendente

Em M4, todo lançamento classificado sai com `false` ou `true`.
O estado NULL permanece válido para transações históricas de M3a.

---

## 9. fiscal_state

### Regra de faturamento

`faturamento_acumulado` representa EXCLUSIVAMENTE faturamento
empresarial do MEI. Não mistura renda pessoal.

Incrementa `faturamento_acumulado`:

    patrimonio == "atividade_negocio"
    AND categoria IN ("receita_servico", "receita_venda")

Não incrementa:

    categoria == "salario"                    (patrimonio=pessoa_fisica)
    categoria == "transferencia_propria"      (patrimonio=pessoa_fisica)
    categoria == "emprestimo"                 (patrimonio=pessoa_fisica)
    categoria == "reembolso"                  (patrimonio=pessoa_fisica)
    categoria == "pessoal_prolabore"          (patrimonio=ponte_pf_pj)
    categoria == "imposto_das"                (despesa)
    categoria == "taxas_tarifas"              (despesa)
    categoria == "custo_operacional"          (despesa)
    categoria == "outros"                     (indeterminado)

A regra usa `patrimonio` + `categoria`, não apenas categoria. Motivo:
`patrimonio` é a dimensão contratada em §4 que separa PF de PJ.

### Outros campos

`ultima_avaliacao_em = now()`
`banda_atual = faixa_teto_mei(faturamento_acumulado)`

### Escopo

`receita_cpf` (categoria futura) é explicitamente fora de M4 v1. Não
existe no dataset, não entra no cálculo. Sua eventual inclusão exige
v2 da taxonomia e revisão desta seção.

---

## 10. Alertas

M4 gera APENAS alertas de faixa de faturamento. Alertas de obrigação
fiscal (DAS, DASN-SIMEI, IRPF) saem do escopo — pertencem a M7.

### Faixas

    60%   informativo
    80%   atenção
    90%   atenção
    95%   crítico
    100%  crítico (dentro da tolerância)
    120%  crítico (acima da tolerância)

Faixas são normativamente definidas aqui. M4 é a autoridade fiscal
dos alertas de faturamento. Não delega para M3a.

### Identidade do alerta

    id estável por faixa: "enq_MEI_60" ... "enq_MEI_120"
    uma faixa = no máximo um alerta por usuário

### Deduplicação

`UNIQUE (user_id, tipo, banda_ou_slug, prazo)` na tabela `alerts`.
Garante que a mesma faixa não gera dois alertas no mesmo prazo.

### Geração

Dentro da mesma transação que atualiza `fiscal_state`, antes do
COMMIT, o serviço avalia qual faixa corresponde ao faturamento
atual e insere o alerta se ainda não existir para aquele prazo.

Atomicidade (ver §16): alerta, transações e `fiscal_state` pertencem
à MESMA transação de banco. Falha em qualquer um deles produz
rollback integral.

`prazo` para alertas de enquadramento: **último dia do ano-calendário**
(ex.: 2026-12-31). Um alerta por faixa por ano-calendário. Re-dispara
no ano seguinte. Isso evita a colisão com UNIQUE da tabela `alerts` e
torna a deduplicação determinística.

Nenhum canal externo é chamado em M4 (Telegram é M7). O alerta é
persistido em `alerts` e fica disponível para leitura via API.

---

## 11. Golden dataset — schema do caso

Cada caso é um objeto JSON com os campos:

    id                     string      — identificador único
    descricao              string      — texto da transação
    valor                  string      — decimal como string ("650.00")
    data                   string      — "YYYY-MM-DD"
    contexto               object      — opcional (ex.: cpf_contraparte_hash)
    categoria_esperada     string      — id de §2
    proposito_esperado     string      — id de DimensionPurpose
    guardrail_esperado     object      — { regra_acionada: str | null }
    needs_review_esperado  boolean
    difficulty             enum        — easy | medium | hard | adversarial
    note                   string      — raciocínio humano

Obrigatórios: todos, exceto `contexto`.

### Contrato do caso para guardrail `cpf_proprio`

Quando o caso testa `guardrail.regra_acionada == "cpf_proprio"`,
o `contexto` DEVE incluir `cpf_titular_hash` e `cpf_contraparte_hash`
com o MESMO valor. Assim o guardrail de §6.4 é exercitado de forma
determinística sem depender de tabela `users`.

Exemplo:

    "contexto": {
      "cpf_titular_hash": "aaaaaaaaaaaaaaaa",
      "cpf_contraparte_hash": "aaaaaaaaaaaaaaaa"
    }

Nos demais casos, esses campos são opcionais ou ausentes. Não se
polui o golden dataset com contexto que não participa da regra.

### Papel do campo `note`

`note` é METADADO HUMANO.
- NÃO é entrada do classificador.
- NÃO é usado pelo eval.
- NÃO pode ser passado no `contexto` de runtime.

Qualquer uso de `note` além de documentação é violação do contrato.

### O que o eval mede em v1

O gate estatístico (§13) mede APENAS 4 campos:

    categoria
    proposito
    guardrail.regra_acionada
    needs_review

`guardrail.regra_acionada` admite `null`. Um caso sem guardrail não
é "erro" por ter `null` — é "sem guardrail aplicado".

Os outros 5 campos do ClassificacaoResultado (`origem_sugerida`,
`patrimonio`, `tratamento_tributario`, `confianca`, `via`) SÃO
obrigatórios no resultado e são verificados em testes de contrato
runtime (§19), mas NÃO entram no gate estatístico v1.

Motivo: medir 9 dimensões simultaneamente reduz a taxa de sucesso
aparente sem aumentar segurança real. Medição das 5 restantes entra
em v2.

---

## 12. Schema JSON

    tests/golden/schema.json       — tipos, enums, obrigatoriedade
    tests/golden/dataset_v1.json   — casos

Objeto raiz:

    {
      "taxonomia_version": "v1",
      "criado_em": "YYYY-MM-DD",
      "casos": [ ... ]
    }

Runner de eval valida `dataset_v1.json` contra `schema.json` e
compara `taxonomia_version` contra `TAXONOMIA_VERSION`. Recusa
executar em divergência.

---

## 13. Métricas A–D

Não compensatórias. Todas precisam passar.

### Métrica A — Violações NUNCA
    violacoes_nunca = |{c ∈ C : regra_nunca_violada(c)}|
Gate: == 0.

Conjunto C = todos os casos.
Independente de abstenção. Nenhuma acurácia compensa.

### Métrica B — Acurácia no conjunto avaliável
    A = {c ∈ C : needs_review_predito == false}
    acuracia_avaliavel = |{c ∈ A : categoria_predita == categoria_esperada}| / |A|

Gate: acuracia_avaliavel >= 0.85.

Proteção contra dataset pequeno:
- se |A| == 0: runner recusa avaliação (erro de configuração)
- se |A| < 15: runner recusa avaliação (dataset insuficiente)

Caso abstido não conta em B (nem acerto, nem erro). Sua qualidade é
avaliada em C.

O threshold 0.85 é meta de produto, não derivada matemática.

### Métrica C — Abstenção
    taxa_abstencao = |C \ A| / |C|
Gate: 0.10 <= taxa <= 0.25.

Adicional:
- nenhum caso com difficulty=easy pode estar em C \ A
- nenhum caso com difficulty=medium pode estar em C \ A
- casos hard/adversarial PODEM estar em C \ A

Abstenção em easy/medium é falha de cobertura.

### Métrica D — Erros críticos entre classificados
    erro_critico = |{c ∈ A : (esperado, predito) ∈ CONJUNTO_CRITICO}|
Gate: == 0.

C \ A (abstidos) não entra em D. Caso crítico permitido pode ser
abstido sem virar erro crítico — desde que a difficulty permita.

Regras NUNCA continuam absolutas. A é a regra; D é a
operacionalização quando o modelo não abstém.

---

## 14. Severidade e pesos

Severidade (binária, sem número):

    CRITICO    — reprova eval. Deve ser 0.
    GRAVE      — alerta se > 2 no dataset
    RELEVANTE  — alerta se > 5
    COMUM      — baseline

Mapa:

    transferencia_propria -> receita_servico      CRITICO
    transferencia_propria -> receita_venda        CRITICO
    emprestimo            -> receita_servico      CRITICO
    emprestimo            -> receita_venda        CRITICO
    imposto_das           -> pessoal_prolabore    CRITICO
    imposto_das           -> outros               CRITICO
    reembolso             -> receita_servico      GRAVE
    reembolso             -> receita_venda        GRAVE
    receita_servico       -> reembolso            RELEVANTE
    (restante)                                    COMUM

Pesos (observabilidade apenas, NÃO decide PASS):

    CRITICO = 5.0
    GRAVE = 4.5
    RELEVANTE = 2.5
    COMUM = 1.0

    indice_erro_ponderado = soma dos pesos dos erros

Exibido no relatório. Não é gate.

Alerta ≠ reprovação. GRAVE > 2 e RELEVANTE > 5 geram alerta no
relatório, mas não falham o build.

---

## 15. Arquitetura A

Classificação dentro da mesma transação da ingestão.

    POST /api/v1/transacoes/extrato/colar
       |
       BEGIN
         parse
         classificar (personal_rules → heurísticas → fallback)
         guardrail_cpf
         triagem
         INSERT transactions (com categoria, proposito, needs_review)
         UPDATE fiscal_state
         INSERT alerts (se faixa cruzada)
       COMMIT

### Propriedade arquitetural: nenhum I/O externo

O classificador de M4 v1 é CPU/memória local apenas.

    - Nenhuma chamada HTTP.
    - Nenhum LLM.
    - Nenhum worker.
    - Nenhum serviço externo.
    - PostgreSQL acessado SOMENTE dentro da unidade transacional.

Esta é a propriedade que sustenta Arquitetura A. Se qualquer um dos
itens acima deixar de ser verdade, a decisão de arquitetura reabre.

### Preparação do contexto antes do pipeline

Dentro da transação de negócio, imediatamente antes do parse:

    SELECT cpf_hash FROM users WHERE id = $user_id
    → populado em contexto.cpf_titular_hash

Executado UMA vez por requisição/lote, reutilizado para todas as
transações do lote. Não é consulta por linha do extrato.

`cpf_titular_hash` é dado do usuário. Não é recalculado nem inferido
a partir da transação.

### Mudança comportamental em relação a M3a

Endpoints deixam de persistir com `categoria=NULL` e passam a
persistir com categoria preenchida. M3a permanece historicamente
correto em 1c8760a; M4 introduz nova versão do comportamento.

### Ressalva

Introdução de LLM, rede ou processamento assíncrono reabre
formalmente esta decisão. Arquitetura A vale para classificação
determinística.

---

## 16. Atomicidade

`Idempotency-Key` protege a operação inteira: parse + classificação +
guardrail + triagem + persistência + fiscal_state + alerts.

Retry com mesma chave + mesmo payload devolve resposta persistida.
Se a chave estiver presa, janela de 300s permite reprocessamento
(ver security/idempotency.py e M3a_CONTRATO §13).

M4 não preenche `confirmado_por` nem `confirmado_em`. Esses campos
são exclusivos da confirmação do usuário (§15 do CONTRATOS_INTERNOS).
Classificação automática ≠ confirmação.

---

## 17. Comportamento em falhas

### Erros de negócio conhecidos (4xx)

    EXTRATO_ILEGIVEL        400  (herdado de M3a)
    ARQUIVO_ILEGIVEL        400  (herdado de M3a)
    VALIDATION_ERROR        422  (herdado)
    IDEMPOTENCY_*           409  (herdado)

M4 não introduz novos códigos de erro de negócio. `outros + needs_review=true`
é comportamento normal, não erro HTTP.

### Erro interno inesperado (500)

Resposta 500 + rollback total. Chave de idempotência vai para
`falhou`. `audit_log` registra. Retry com mesma chave + mesmo
payload é permitido (estado `falhou` aceita retry).

### Falha em etapa crítica pós-persistência

Se `fiscal_state` ou `alerts` falharem, ROLLBACK TOTAL. Não existe
transação persistida com categoria preenchida mas sem fiscal_state
atualizado. Ou tudo, ou nada.

---

## 18. Critérios de aceite

1. Taxonomia v1 promovida a CONTRATOS_INTERNOS §4.1 com
   `TAXONOMIA_VERSION = "v1"` em domain/fiscal/taxonomia.py.

2. `classificar_v2` produz os 9 campos de §4 (verificado por teste
   de contrato runtime).

3. Precedência: personal_rules > heurísticas > fallback. Guardrail
   sempre prevalece sobre o resultado.

4. Entrada genérica (ex.: "PIX RECEBIDO JOAO") cai em `outros` com
   needs_review=true.

5. Guardrail reescreve pelo menos os 5 casos de §6.

6. Triagem classifica cada transação em silencioso / confirmacao /
   fila_revisao com critérios de §7.

7. `fiscal_state.faturamento_acumulado` atualizado no mesmo passo,
   pela regra `patrimonio + categoria`. `salario` NÃO incrementa.

8. Alerta de faixa é gerado quando o faturamento cruza 60/80/90/95/100/120%.
   UNIQUE impede duplicação.

9. Idempotency-Key cobre operação inteira. Retry com mesma chave e
   mesmo payload devolve resposta persistida sem re-classificar.

10. Golden dataset v1 em tests/golden/dataset_v1.json com pelo menos
    25 casos cobrindo easy/medium/hard/adversarial, incluindo ao
    menos um caso de cada regra NUNCA.

11. Runner de eval:
    - valida dataset contra schema.json
    - verifica taxonomia_version
    - produz relatório com Métricas A, B, C, D + breakdown por difficulty
    - reprova se qualquer gate falhar
    - recusa execução se |A| < 15

12. Métrica A: zero violações NUNCA.

13. Métrica B: acuracia_avaliavel >= 0.85.

14. Métrica C: 0.10 <= taxa_abstencao <= 0.25, sem abstenção em
    easy/medium.

15. Métrica D: zero erros críticos entre classificados.

---

## 19. Bateria mínima de testes

- test_taxonomia: 11 categorias existem, TAXONOMIA_VERSION == "v1".
- test_classificacao: 10 casos cobrindo cada regra de §5.2.
- test_classificacao_contrato: para cada chamada, verifica que
  TODOS os 9 campos de §4 existem com tipos corretos e bounds
  (`0.0 <= confianca <= 1.0`).
- test_precedencia: personal_rule vence heurística; guardrail vence
  personal_rule.
- test_guardrail_cpf: 5 casos, um por regra, verificando
  GuardrailResultado completo (aplicado, categoria_original,
  categoria_corrigida, motivo, regra_acionada).
- test_guardrail_null: caso sem guardrail tem `regra_acionada=null` e
  `aplicado=false`.
- test_triagem: 3 casos, um por destino.
- test_fiscal_state_pj: soma de `patrimonio=atividade_negocio` +
  categoria receita.
- test_fiscal_state_ignora_salario: `salario` NÃO incrementa
  faturamento_acumulado.
- test_alerta_faixa: faturamento cruzando 80% gera alerta com id
  estável; segunda chamada não duplica.
- test_idempotencia_em_ingestao: retry da mesma chave + mesmo payload
  não re-classifica.
- test_servico_ingestao_end_to_end: parse → classificar → guardrail →
  triagem → persistência + fiscal_state + alerts em uma chamada.
- test_atomicidade_m4: verifica que persistência de transactions,
  atualização de fiscal_state e inserção de alerts pertencem à mesma
  transação de banco; falha em qualquer uma dessas etapas produz
  rollback integral.
- test_sem_io_externo_no_classificador: verifica que `classificar_v2`
  não executa HTTP, LLM, worker, nem acesso ao PostgreSQL. Inspeção
  via monkeypatch de `conexao()` e verificação de ausência de
  `httpx`, `requests` ou client LLM no caminho de execução.
- test_eval_runner: executa contra dataset_v1.json; verifica as
  quatro métricas; recusa execução com |A| < 15.

---

## 20. O que NÃO é PASS

- Acurácia alta compensando violação NUNCA. Nunca.
- Acurácia alta compensando erro crítico classificado. Nunca.
- Abstenção em easy ou medium. Nunca.
- Categoria preenchida sem fiscal_state atualizado. Nunca.
- `salario` incrementando `faturamento_acumulado`. Nunca.
- Alerta duplicado pela mesma faixa. Nunca.
- Dataset com `taxonomia_version` divergente do código. O runner recusa.
- `classificar_v2` fazendo I/O externo. Arquitetura A reabre.
- `personal_rule` violando regra NUNCA. Guardrail prevalece.
- `note` do golden dataset aparecendo no contexto de runtime. Nunca.
- Classificação com LLM antes da decisão de reabrir Arquitetura A.
- Teste que passa só porque o valor foi hardcoded para bater.
- M4 preenchendo `confirmado_por` ou `confirmado_em`. Exclusivo do usuário.

---

## 21. Dívidas e decisões adiadas

### N1 — Janela de abstenção

A janela 10%–25% da Métrica C (v1) pode ser infactível se o
classificador abstiver corretamente em poucos casos hard/adversarial.
Com dataset mínimo de 25 casos e proibição de abstenção em easy/medium,
a janela exige entre 3 e 6 casos abstidos. Se o classificador acertar
todos os hard/adversarial, C falha por sub-abstenção.

**Decisão adiada:** revisar a janela quando o dataset v1 existir, com
dados concretos. Nenhuma alteração do classificador é autorizada para
"satisfazer" a janela — o eval não pode ser desenhado para fabricar PASS.

### N2 — `personal_rules` fora do golden dataset v1

O golden dataset v1 NÃO inclui casos com `personal_rules`.

Motivo: personal_rules é configuração operacional do usuário,
não comportamento fiscal padrão. Misturar as duas coisas no dataset
de referência criaria dependência entre eval e configuração de usuário.

O teste de precedência (`test_precedencia`, §19) constrói o contexto
`personal_rules` diretamente em código de teste. Golden dataset mede
comportamento padrão.

---

Fim do contrato M4 v1. Aguardando segunda auditoria.
