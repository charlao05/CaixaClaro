# M8 — Decisão: integração do frontend protótipo

## Contexto

M8 (frontend conectado) estava marcado como PULADO em MILESTONES.md, com
nota "nenhum artefato frontend no repositorio atual". A auditoria de
docs/RECONCILIACAO.md §5 registrava "Frontend | Protótipo fora do repo".

Investigação posterior localizou materialmente o protótipo no Google AI
Studio (Applet 0833d2aa-3e71-4a93-8e95-c7acaa6fd35b, projeto GCP
gen-lang-client-0687034954). O protótipo tem 24 arquivos-fonte em
/app/applet/src/, preservados, compilando, nunca exportados para este
repositório. Não há repositório git no AI Studio.

A auditoria subsequente comparou os contratos fiscais do protótipo
(engine/*.ts) com o backend (domain/fiscal/*.py, services/tax_opinion.py,
eval/runner.py) e identificou alinhamento estrutural amplo, mas cinco
divergências normativas. Este documento registra o que foi encontrado,
as divergências, as decisões e o contrato de integração.

M8a cobre a decisão documental. M8b (implementação) entra em commits
posteriores, sem começar antes de cada decisão estar registrada aqui.

## Inventário do protótipo

Categorização derivada de docs/RECONCILIACAO.md §4, confirmada pela
leitura dos arquivos recuperados:

- UI pura, sem acoplamento fiscal: TaxOpinionCard, TopBar,
  ProfileSelectorModal, AlertsAndViral
- UI com dados locais, adaptável: ReviewQueueStories,
  AccountSettingsModal, UnitEconomics
- Depende de lógica fiscal (a ser substituída por API): DashboardOverview,
  IngestionCenter, GuardianAuditor
- Orquestrador: App.tsx
- Domínio fiscal duplicado no cliente (a descartar): engine/classifiers,
  engine/guardrails, engine/taxOpinions, engine/taxonomy,
  engine/parsers, engine/textnorm, engine/goldenDataset,
  engine/evalHarness, engine/shadowTraffic
- Persistência Firebase (a descartar): firebase/config, firebase/service
- Dados sintéticos: data/mockInitialData

## Alinhamento confirmado com o backend

Quatro dimensões do contrato fiscal do protótipo e do backend têm
vocabulários idênticos, valor a valor:

- CategoriaId: 11 categorias, mesmos IDs, mesma ordem
- OrigemSugeridaId: 7 valores (`empresa_contratante`, `cliente_pf`,
  `conta_propria`, `amigo_familiar`, `banco_financeira`, `governo_orgao`,
  `desconhecido`)
- PatrimonioId: 4 valores (`pessoa_fisica`, `atividade_negocio`,
  `ponte_pf_pj`, `transito_terceiro`)
- TratamentoTributarioId: 6 valores (`tributavel_irpf`,
  `isento_nao_tributavel`, `carne_leao_potencial`, `faturamento_pj`,
  `retencao_fonte`, `indeterminado_pendente`)

Consequência prática: transações persistidas pelo backend são
renderizáveis no protótipo sem tabela de tradução para essas dimensões.

## Divergências e decisões

### D1 — `reembolso -> receita_*`

Protótipo: NUNCA via `violatesNuncaRule`, peso 4.5 (grave).
Backend: `PALAVRAS_NUNCA_RECEITA` registra violação, mas o par não está
em `CONJUNTO_CRITICO`. Não incrementa `erros_criticos`.

DECISÃO: par passa a ser erro crítico quando não há revisão humana.
Alinha a severidade do evaluator com a intenção já expressa no protótipo.

### D2a — `imposto_das -> pessoal_prolabore`

Protótipo: NUNCA, peso 5.0.
Backend: em `CONJUNTO_CRITICO`.

DECISÃO: alinhado. Sem ação.

### D2b — `imposto_das -> outros`

Protótipo: NUNCA, peso 4.0 (grave).
Backend: em `CONJUNTO_CRITICO`.

DECISÃO: manter crítico no backend. DAS caindo em `outros` significa
que o guardrail de tributo falhou — é o cenário mais perigoso e não
deve ser rebaixado para alinhar mecanicamente com o protótipo.

### D2c — `imposto_das -> reembolso`

Protótipo: NUNCA.
Backend: não coberto. Nem em `CONJUNTO_CRITICO`, nem em
`PALAVRAS_NUNCA_RECEITA` (que só dispara se a final for receita).

DECISÃO: adicionar ao `CONJUNTO_CRITICO`. Lacuna real; o protótipo
protege, o backend não.

### D3 — vocabulário de PropositoId

Backend tem 11 valores. Protótipo tem 15. Os quatro ausentes:

- aporte_capital — PF colocando dinheiro na empresa
- dinheiro_terceiros — entrada para repassar
- rendimento_aplicacao — juros, dividendos, aluguel
- doacao_heranca — transmissão patrimonial sem trabalho

O backend já permite `_montar(proposito=...)` explícito, diferente do
default da categoria. Isso permite incorporar os quatro como
**propósitos**, sem inflar a taxonomia de categorias (que é declarada
imutável em TAXONOMIA_VERSION = v1).

DECISÃO: avaliar os quatro como extensões de `PropositoId`, não como
categorias. `aporte_capital` e `dinheiro_terceiros` têm prioridade porque
o protótipo tem casos dedicados no switch de `taxOpinions.ts`.
`rendimento_aplicacao` e `doacao_heranca` permanecem em avaliação; no
curto prazo caem em `outros_indeterminado`.

### D4 — via="fallback"

Vocabulário declarado: `regra_personalizada`, `heuristica`, `guardrail`,
`usuario`. Único produtor real: `api/transacoes.py`, com fallback
`row["via"] or "heuristica"`. `via == "fallback"` existe em
`tax_opinion.py:33` mas nenhum ponto do código o produz.

DECISÃO: código legado inativo. Sem ação. Não vira decisão de produto.

### D5 — geração do parecer

Protótipo: `generateTaxOpinion` é chaveado por `purpose` e consulta
`userProfileType` + `accountPurpose`, produzindo textos diferentes para
autônomo vs MEI sobre o mesmo tipo de movimentação.

Backend: `generate_tax_opinion` é chaveado por `categoria` (após
guardrail) e usa tabelas estáticas (`_FATO`, `_INTERP`, `_PF_PJ`,
`_TRATAMENTO`, `_CONDICAO`). Não recebe perfil. Um MEI e um autônomo
recebem o mesmo texto.

O backend já tem os campos no contrato interno:

    ContextoClassificacao
        regime: str = "MEI"
        tipo_conta: str | None = None

Mas `api/transacoes.py` constrói o contexto com
`ContextoClassificacao(personal_rules={})`, caindo em `regime="MEI"`
independente do usuário real. E `services/fiscal.py` propaga esse
contexto para `classificar_v2`, mas não para `generate_tax_opinion`.

DECISÃO: o contexto fiscal do usuário deve participar do pipeline quando
alterar materialmente a interpretação. A integração M8 deve:

1. Conectar `users.regime` (MEI/SIMPLES/PF) ao `ContextoClassificacao`.
2. Decidir, por ponto de uso, se `tipo_conta` e `regime` influenciam a
   classificação, o parecer, ou ambos.
3. Determinar o mapeamento entre `users.regime` (3 valores) e os perfis
   do protótipo (`pf_geral`, `pf_autonomo`, `profissional_liberal`,
   `mei`, `pj_pequena`) — decisão de produto separada, não inferida
   automaticamente.

## Contrato de integração

Regra central:

> O frontend NÃO recriará `engine/classifiers.ts`, `engine/guardrails.ts`
> ou `engine/taxOpinions.ts`. O backend permanece autoridade sobre
> classificação, guardrail, triagem e parecer. O protótipo fornece
> comportamento de produto e apresentação; suas regras somente entram no
> backend após decisão explícita registrada neste documento.

Fluxo alvo:

    descrição + valor + contexto do usuário
        ↓
    backend: classificar_v2 → aplicar_guardrail → triar
        ↓
    backend: generate_tax_opinion(classif, guard, tri, contexto)
        ↓
    API: resposta com ClassificacaoResultado + TaxOpinion
        ↓
    React: TaxOpinionCard renderiza

Não há duas inteligências fiscais concorrentes.

## Estratégia de portabilidade dos componentes

Bloco 1 — portar direto (UI pura, sem acoplamento fiscal):
    TaxOpinionCard, TopBar, ProfileSelectorModal, AlertsAndViral

Bloco 2 — portar trocando a fonte de dados (Firebase → HTTP):
    ReviewQueueStories, AccountSettingsModal, UnitEconomics

Bloco 3 — portar após fechamento do contrato fiscal:
    DashboardOverview, IngestionCenter, GuardianAuditor

O Bloco 3 depende de D1, D2b, D2c, D3 e D5 implementados. Não começa antes.

## O que NÃO será portado

- firebase/config.ts, firebase/service.ts (substituídos por services/api.ts)
- engine/classifiers.ts, engine/guardrails.ts, engine/taxOpinions.ts,
  engine/taxonomy.ts, engine/parsers.ts, engine/textnorm.ts,
  engine/goldenDataset.ts, engine/evalHarness.ts, engine/shadowTraffic.ts
- data/mockInitialData.ts como fonte de verdade; sobrevive apenas como
  data/demo.ts para modo demonstração

## Fora de escopo

- Definir o mapeamento users.regime → perfis do protótipo (decisão de
  produto separada)
- Definir se `rendimento_aplicacao` e `doacao_heranca` entram no
  vocabulário de PropositoId
- Migração de dados históricos do Firebase
- Reimplementação de shadowTraffic no backend
- Deploy do frontend

## Referências

- docs/M9.3_DECISAO.md — padrão deste documento
- docs/M10_DECISAO_2026-08.md — padrão deste documento
- docs/RECONCILIACAO.md §4 §5 — inventário do protótipo
- backend/src/caixaclaro/domain/fiscal/taxonomia.py
- backend/src/caixaclaro/domain/fiscal/classificacao.py
- backend/src/caixaclaro/services/tax_opinion.py
- backend/src/caixaclaro/eval/runner.py
- backend/src/caixaclaro/api/transacoes.py
- backend/src/caixaclaro/api/perfil.py
- backend/migrations/001_initial.sql
