# Auditoria da jornada do público-alvo — 2026-10-09

Base auditada: `main` @ `2215b7e`. Ambiente: PostgreSQL 16, Python 3.12,
Node 22. Linha de base antes de qualquer mudança: **550 testes verdes**,
eval do golden dataset PASS.

Este documento registra (1) para quem o repositório diz que o CaixaClaro é,
(2) o que uma pessoa desse público encontrava ao usar o produto, com
evidência executada, (3) o que o patch que acompanha este arquivo muda,
(4) as decisões tomadas nele — para aprovar ou reverter — e (5) o que
continua fora, declarado.

## 1. Para quem é o CaixaClaro, segundo o próprio repositório

- `README.md`: "aplicação financeira/fiscal para MEI, autônomos e pequenos
  negócios".
- Landing (`frontend/src/landing`): "Seu extrato fala. O CaixaClaro explica."
  "Parece uma conversa, não uma planilha." "Você não precisa entender de
  contabilidade para começar." FAQ: foco em quem trabalha por conta própria,
  autônomos, profissionais liberais e MEIs; pequenas empresas também.
- `docs/M8_DECISAO.md` (D5): o protótipo original tinha cinco perfis —
  `pf_geral`, `pf_autonomo`, `profissional_liberal`, `mei`, `pj_pequena` — e
  o mapeamento para `users.regime` ficou como "decisão de produto separada".
- `docs/REGRA_ORIENTADOR.md`: nada de default silencioso; hipótese não vira
  fato sem confirmação; limitação aparece na tela; e a regra vale também
  para o texto que o usuário lê.

Leitura: o produto é um **intérprete em linguagem simples para quem está
começando** — MEI, autônomo no CPF, assalariado com renda extra, pequeno
negócio. A implementação, porém, só atendia de fato o MEI, e mesmo para ele
o ciclo central falhava no caso mais comum (Pix de pessoa física).

## 2. O que acontecia (evidência executada na API real)

Extratos usados são **sintéticos**, escritos para esta auditoria.

| # | O que a pessoa encontrava | Evidência | Onde |
|---|---|---|---|
| A1 | Confirmar uma entrada como "pagamento por trabalho" não mudava o faturamento. 14 entradas confirmadas (R$ 5.405,00) → painel em R$ 0,00. Contraria M4_CONTRATO §9 ("outra categoria -> receita PJ: ADICIONA o valor"). O teste `test_confirmar_promove_para_receita_incrementa_faturamento` não verificava o incremento e seu comentário admitia delta 0. | `delta_faturamento: "0"` nas 14 respostas | `services/fila.py` (patrimônio ficava preso ao palpite original) |
| A2 | Parecer de lançamento já confirmado dizia "Guardrail §6 aplicado (None): categoria original era outros" e exibia o selo "Requer confirmação". | resposta de `GET /{id}/opiniao` | `api/transacoes.py`, `services/tax_opinion.py` |
| A3 | A direção do dinheiro era ignorada. Pix **enviado** com a palavra "salário" virava "Entrada … referente a salário … Declarar como rendimento tributável", selo "Fato confirmado". Pix **recebido** de alguém de sobrenome "Claro" virava despesa dedutível. Despesa com a palavra "consultoria" **reduzia** o faturamento (1.000 − 400 = 600). | três reproduções | `domain/fiscal/classificacao.py` (`valor` não era usado) |
| A4 | Todo cadastro nascia "MEI". Quem mudava para pessoa física continuava vendo "R$ X de R$ 81.000". O mês/ano de abertura existiam no perfil (sem campo na tela) e não entravam em cálculo nenhum, embora o limite do primeiro ano seja proporcional. | `teto_anual: "81000.00"` para regime PF | `api/auth.py`, `services/fiscal_resumo.py`, `services/faturamento.py` |
| A5 | Alerta (e mensagem do Telegram): "Faturamento MEI cruzou 60% do teto anual (R$ 81000.00)". Linha colada sem ano em outubro ("28/12 …") era gravada como 28/12 do ano corrente (futuro). Erros de arquivo devolviam lista Python ("Linha 0 incompleta: ['Extrato Conta Corrente']"). | respostas da API | `services/faturamento.py`, `domain/ingest/*` |
| A6 | O sistema não aprendia. A tabela `personal_rules` existe desde a migration 001, mas o código sempre montava o contexto com `personal_rules={}` e nada gravava regra. O mesmo pagador voltava à fila toda vez. | `grep personal_rules src/` | `api/transacoes.py`, `services/workers.py` |
| A7 | Palpite errado não tinha conserto: `/confirmar` devolve 409 para lançamento fora da fila ou já confirmado, e não havia outra rota. | 409 `NAO_EM_REVISAO` / `JA_CONFIRMADA` | `services/fila.py` |
| A8 | Não dava para começar sem extrato. `origem='manual'` está no schema e em CONTRATOS_INTERNOS §3, sem rota. O botão "Adicionar lançamento" abria colar/importar. | lista de rotas | `api/transacoes.py` |
| A9 | A revisão só oferecia respostas de **entrada** (trabalho, venda, transferência, empréstimo), inclusive para saídas, e não havia como dizer "gasto pessoal". Não havia "pular": travar no primeiro item travava a fila. | `Revisao.tsx`, `_opcoes_para` | frontend + `tax_opinion.py` |
| A10 | A tela de Perfil prometia "alertas … do boleto mensal do MEI (DAS) no Telegram". Esse aviso não existe (DECISOES 2026-09-27: "Nao existe lembrete de DAS como feature"). | `Perfil.tsx` × `services/alertas.py` | frontend |
| A11 | Identificadores internos na interface: `receita_servico`, `outros -> receita_servico`, `pro_mensal`, `ativa`, `critico`. Títulos do parecer em jargão ("Relação PF / PJ", "Possível tratamento tributário"). | telas | frontend |
| A12 | Colagem com data/descrição/valor em linhas separadas, valor com ponto decimal, CSV com linhas de título ou data ISO: todos recusados. | 400 nas quatro tentativas | `domain/ingest/*` |

Também observado, **não tratado neste patch** (seção 5): único tipo de
alerta é o de faixa do limite do MEI; recuperação de senha só por Telegram;
Privacidade/Termos/Contato "em breve"; sem exportar/excluir conta; sem
medição de uso; sem histórico de navegação (o voltar do Android sai do app);
preço divergente (R$ 29,90 no código, "em definição" na landing).

## 3. O que este patch muda

Backend
- **Confirmar conta** (A1): a decisão do usuário passa a levar junto
  propósito, patrimônio e tratamento; `via='usuario'`. Saída nunca conta
  como faturamento.
- **Direção** (A3): valor negativo ou marca textual de envio contradizendo
  uma categoria de entrada (e marca de recebimento contradizendo "gasto")
  manda o lançamento para a revisão, com o motivo em português.
- **Parecer** (A2, A11): reescrito em linguagem simples, por perfil (MEI /
  Simples / pessoa física) e por direção; sem imperativos fiscais; selo
  `fato_confirmado` só com confirmação do usuário.
- **Perfil** (A4): cadastro aceita `regime`; resumo e alertas respeitam o
  perfil; limite proporcional no ano de abertura; `teto_anual` é `null`
  para quem não é MEI. O resumo traz também contagens e a soma de entradas
  e saídas do mês mais recente.
- **Aprender** (A6): `lembrar: true` na confirmação grava regra pessoal e
  aplica a mesma resposta aos pendentes com descrição e direção iguais; as
  regras são carregadas na colagem, na importação e no sync do Open Finance.
- **Corrigir** (A7): `PATCH /transacoes/{id}/corrigir`.
- **Começar sem extrato** (A8): `POST /transacoes/manual`.
- **Vocabulário único** (A9, A11): `services/rotulos.py` — rótulos, opções
  de resposta por direção (incluindo "gasto pessoal ou da casa") e moeda;
  `GET /transacoes/opcoes-resposta`; a fila já entrega as opções de cada item.
- **Leitura tolerante** (A5, A12): colagem em colunas, ponto decimal, data
  sem ano nunca no futuro, CSV com preâmbulo e data ISO, erros em português.

Frontend
- Cadastro pergunta "Como você trabalha hoje?" (cinco respostas, incluindo
  "Estou começando e ainda não sei") e explica o uso do CPF.
- Painel por perfil, com contagens e a soma do mês; sem teto de MEI para
  quem não é MEI.
- Revisão em tom de conversa, respostas coerentes com entrada/saída,
  "Não sei agora — pular", "lembrar desta resposta", retorno em português.
- Tela do lançamento com títulos simples e botão "Não foi isso? Corrigir".
- Formulário "Anotar um recebimento ou gasto".
- Rótulos em português em lançamentos, avisos e assinatura; Perfil com
  mês/ano de abertura do MEI e sem a promessa do aviso de DAS.

## 4. Decisões tomadas neste patch (aprovar ou reverter)

| # | Decisão | Por quê | Como reverter |
|---|---|---|---|
| D1 | Confirmação do usuário atualiza propósito/patrimônio/tratamento. | M4_CONTRATO §9 e CONTRATOS_INTERNOS §15 já pediam; era defeito. | Não recomendado. |
| D2 | `fato_confirmado` só com confirmação; palpite de alta confiança vira `leitura_provavel`. | M4 §16 ("classificação automática ≠ confirmação") e REGRA_ORIENTADOR §1. Muda o significado de um valor de CONTRATOS_INTERNOS §6. | `_grau` em `tax_opinion.py`. |
| D3 | Conflito de direção manda para a revisão. Só valor negativo e marcas textuais contam como evidência, porque o golden dataset v1 usa valores sem sinal. | Fato do extrato vence palpite. | `_conflito_de_direcao` em `classificacao.py`. |
| D4 | Quem não é MEI não vê limite nem recebe alerta de faixa; a soma do que foi confirmado como trabalho/venda continua sendo mantida e é exibida com outro nome. | REGRA_ORIENTADOR §2.4. `receita_cpf` segue fora (taxonomia v2). | `teto_do_ano` em `faturamento.py`. |
| D5 | Limite proporcional: R$ 6.750 × meses de atividade no ano de abertura. | LC 123/2006, art. 18-A, §2º. | idem. |
| D6 | "Gasto pessoal" é propósito (`gasto_pessoal`) sobre a categoria `pessoal_prolabore`; doação, rendimento e dinheiro de terceiros são propósitos sobre `outros`. | Mesmo padrão de M8-D3: não infla a taxonomia v1. | `OPCOES_*` em `rotulos.py`. |
| D7 | A API continua assumindo "MEI" quando `regime` não é enviado no cadastro; a tela sempre envia. | Não quebrar o contrato histórico sem decisão explícita. | `api/auth.py`. |
| D8 | Regra pessoal = descrição inteira normalizada (mínimo 8 caracteres), nunca para `outros`; o guardrail de tributo continua prevalecendo. | Evitar regra que case com quase tudo. | `lembrar_regra` em `fila.py`. |

Textos do parecer: cada frase foi escrita para descrever, condicionar ou
declarar limitação — nenhuma recomenda. Ainda assim é **conteúdo fiscal
voltado ao usuário** e deve ser lido por um contador antes de ser tratado
como revisado. Está tudo em `services/tax_opinion.py`.

## 5. O que NÃO foi feito (declarado, não escondido)

- Calendário de obrigações (DAS, DASN-SIMEI, IRPF). M4 mandou para o M7; o
  M7 fechou sem ele. A promessa na tela foi removida; o recurso não existe.
- Recuperação de senha por e-mail; páginas de Privacidade, Termos e Contato;
  exportar e excluir conta; medição de uso; navegação com histórico
  (botão voltar); canal de aviso além do Telegram; decisão de preço.
- Taxonomia v2 (`receita_cpf`, `gasto_pessoal` como categorias) e o
  mapeamento formal dos cinco perfis para `users.regime`.
- Uso de dados ricos do Open Finance (documento da contraparte). O
  guardrail de CPF próprio continua sem dado para disparar em produção.
- Categoria II da consulta ao CRC-ES (somas por categoria) — a soma do mês
  no painel é só entradas × saídas, sem classificação.
- M11 fases 3–6.

## 6. Verificação

- Backend: **575 passed** (550 anteriores + 24 jornadas em
  `tests/test_jornada_publico_alvo.py` + 1 teste novo do parecer). Nove
  testes existentes que fixavam os textos antigos foram atualizados; o teste
  de confirmação que não verificava o faturamento passou a verificar.
- Eval do golden dataset: PASS, métricas idênticas às de antes
  (A = 0, B = 1,000, C = 0,235, D = 0).
- Frontend: `npm run build` (tsc + vite) sem erro; `npm run lint` com
  0 erros e os mesmos 2 avisos que já existiam.
- Jornadas por perfil (J18): manicure MEI, vendedora de marketplace MEI,
  pedreiro autônomo no CPF, assalariado com bico, prestadora no Simples.
  Em todas: tudo o que depende da pessoa cai na fila, as respostas que a
  própria API oferece resolvem a fila, e a soma final bate com o esperado.

## 7. Limites desta evidência

- Extratos sintéticos. Não substituem extratos reais de bancos reais.
- As telas **não foram vistas num navegador**: compilam e passam no lint,
  mas layout e leitura no celular não foram verificados.
- Nada foi executado contra Pluggy, Asaas ou Telegram reais, nem em produção.
- Sem migration nova; `personal_rules` já existia.
