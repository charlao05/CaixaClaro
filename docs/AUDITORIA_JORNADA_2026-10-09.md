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
  mas layout e leitura no celular não foram verificados. *(Atualizado na
  revisão da seção 8: vistas num navegador automatizado em 390 px; não em
  aparelho real.)*
- Nada foi executado contra Pluggy, Asaas ou Telegram reais, nem em produção.
- Sem migration nova; `personal_rules` já existia.

## 8. Revisão independente e correções pré-lançamento (2026-10-09)

Revisão feita sobre `main` @ `2215b7e` com este patch aplicado. Ambiente:
PostgreSQL 16, Python 3.12, Node 22. Executado: suíte completa do backend,
eval do golden dataset, typecheck, lint e build do frontend, e as telas num
Chromium automatizado em 390 px de largura contra a API local. A cobrança
foi exercitada contra um **servidor local que imita o Asaas** — não é o
Asaas. Nada foi executado em produção.

Os commits desta série vêm depois do commit do M13, um por correção, para
que cada um possa ser aprovado ou revertido sozinho. Os identificadores R1
a R13 abaixo aparecem nas mensagens de commit e nos testes.

### 8.1 Achados e correções

| # | O que acontecia | Evidência antes da correção | O que mudou |
|---|---|---|---|
| R1 | Resposta lembrada ignorava a direção do dinheiro: ensinar que a **saída** "PIX TRANSF JOAO" era gasto do trabalho fazia uma **entrada** com a mesma descrição virar gasto, em silêncio, fora da soma. Além disso, "lembrar" uma retirada do negócio prometia "o CaixaClaro já usa esta resposta" e perguntava de novo (regra de proteção). | J21, J22 e J26 falham no M13 original. | Regra por (padrão, direção); só é guardada se dispensar a pergunta; motivo sem identificador interno. |
| R2 | A boas-vindas do Telegram prometia "alertas de faturamento e DAS". | Texto fixo em `api/webhooks.py`. | Só promete o que existe: aviso de limite do MEI e código de senha. |
| R3 | Rotas novas sem teste de isolamento entre contas (o comportamento estava certo). | Ausência de teste. | J23 a J25. |
| R4 | Pessoa física + "venda de produto" recebia "É renda do seu trabalho por conta própria". O produto não sabe se é atividade ou venda de um bem da pessoa; o `main` declarava essa limitação. | Texto em `tax_opinion.py`. | Limitação restaurada em linguagem simples. Continua à espera do contador. |
| R5 | Lançamento de outro ano corrompia o número do painel: colar 2025 depois de 2026 trocava o painel para 2025 e zerava o acumulado; colagem que atravessa a virada ia toda para o ano novo; no M13, confirmar um Pix do ano anterior fazia o mesmo. | Reproduzido no `main` e no M13: R$ 50.000 viravam R$ 100. | Soma do ano lida de `transactions` (M4 §9: "soma atual das transações"). |
| R6 | Confirmações gravadas antes do M13 ficavam fora da soma (propósito e patrimônio presos ao palpite). | Leitura do código; nenhuma migration no M13. | Migration 013 alinha essas linhas com a regra do código. |
| R7 | Voltar no dia seguinte para pagar dava erro 500 (pendente fora do prazo local barrava a cobrança nova no índice único). | `UniqueViolationError payments_pendente_uq`. | Pendente vencido vira `expirado` antes de criar o novo, como o worker já faz. |
| R8 | Quem já assinou não conseguia renovar pela tela: "Situação: Ativa", só "Pausar assinatura", cobrança da renovação sem QR. | Navegador, assinatura vencida. | Tela por data, "Renovar", "Você tem um pagamento esperando"; `acesso` no status. |
| R9 | Token do bot do Telegram e CPF iam para o log (linha INFO da biblioteca HTTP). | Funções reais com transporte simulado: token e CPF no log. | `httpx`/`httpcore` em WARNING e máscara em toda linha de log. |
| R10 | O limite de tentativas tratava todos como um só (a API só enxerga o Caddy). | Local: dois `X-Forwarded-For` diferentes gravados como o mesmo IP; o 6º cadastro da mesma origem recebe 429. Em produção é inferência pelo código e pela topologia documentada; a consulta B1 do relatório de estado é como confirmar (não executada). | IP do cliente pelo cabeçalho do Caddy e pelo `CF-Connecting-IP`, este só quando a conexão vem do conector do Tunnel. |
| R11 | Sessão encerrada: toda tela mostrava "UNAUTHORIZED". | Navegador, sessão revogada. | Volta ao login com uma frase em português. |
| R12 | Extratos sobrepostos duplicavam lançamentos, e não havia como apagar. | Semana + mês: 5 lançamentos, soma errada. | Aviso de prováveis repetidos; apagar os repetidos, desfazer a importação, apagar um lançamento. |
| R13 | Backup terminava com sucesso mesmo com a cópia no R2 falhando. | Script real com stubs: código 0 nos três casos. | Código 2 quando a cópia no R2 falha ou não está configurada. |

Menores, no mesmo espírito: `scripts/bateria_c.py` gerava só CPF inválido;
estoque devolvia 500 para entrada malformada; o card "Alertas" da landing
prometia avisos que não existem para quem não é MEI; nenhum cabeçalho de
segurança na resposta.

### 8.2 Decisões tomadas na revisão (aprovar ou reverter)

Cada uma está num commit próprio. Testado sobre a ponta da série: os
commits a partir de "Faturamento: a soma do ano…" saem com `git revert` sem
conflito. Exceção de dependência: "Extratos sobrepostos…" usa funções
criadas em "Faturamento: a soma do ano…"; reverter este exige reverter
aquele junto. Os dois commits do M13 são a base de todos os outros.

| # | Decisão | Por quê |
|---|---|---|
| DR1 | Resposta lembrada vale só no sentido (entrada/saída) em que foi dada; uma regra por (padrão, direção); `ContextoClassificacao.regras_pessoais` substitui o `personal_propositos` do M13; `personal_rules` (contrato M4 §5) fica igual. | Há bancos cuja descrição é idêntica nos dois sentidos. |
| DR2 | A regra só é guardada quando vai dispensar a pergunta. | Não prometer o que a regra de proteção desfaz. |
| DR3 | O faturamento do ano é a soma dos lançamentos gravados daquele ano. `ano_referencia` passa a ser o ano mais recente com lançamento, sem passar do ano corrente (antes: o ano da última escrita). O aviso de faixa é avaliado pelo estado atual do ano e inserido se ainda não existir (M4 §10, ao pé da letra). | O contador por deltas se perdia. |
| DR4 | Migration 013: índice (user_id, data) e backfill das confirmações antigas. | Sem ela, quem confirmou antes do M13 continuaria fora da soma. |
| DR5 | Checkout marca o pendente vencido no prazo local como `expirado` antes de criar outro. A cobrança antiga não é cancelada no Asaas; se for paga, o webhook confirma. | Mesma regra do worker (CONTRATOS_INTERNOS §12, item 3). |
| DR6 | `GET /billing/status` informa `acesso` com a mesma função que libera as rotas; a tela decide pela data, não pelo rótulo `ativa`. | `ativa` quer dizer "habilitada para renovação" (DECISOES 2026-09-26). |
| DR7 | IP do cliente: o Caddy escreve `X-CaixaClaro-Conexao`; a API usa `CF-Connecting-IP` só quando essa conexão é interna (conector do Tunnel) e só quando a própria conexão da API é interna. | Corrige o limite global. Quem acessa o servidor direto por endereço público não consegue forjar o IP; a ressalva de implantação está em 8.4. |
| DR8 | 401 em requisição autenticada leva ao login. | Fim do "UNAUTHORIZED". |
| DR9 | Repetidos: a API conta e avisa; a pessoa apaga. Nada vira identidade por conteúdo. | CONTRATOS_INTERNOS §3 proíbe (data, descrição, valor) como identidade. |
| DR10 | Backup: código 2 quando a cópia no R2 falha ou não está configurada. | O agendador precisa ver a falha. |
| DR11 | Cabeçalhos `X-Content-Type-Options`, `X-Frame-Options` e `Referrer-Policy` no Caddy; HSTS e CSP ficam de fora. | Não mudam o funcionamento; HSTS é da borda da Cloudflare, CSP precisa de teste com a Pluggy. |

### 8.3 O que continua aberto (decisão do responsável; a revisão não mexeu)

- **Preço**: o código cobra R$ 29,90 e R$ 299,00 marcados como provisórios.
- **Cadência da renovação**: com o código real do worker e o substituto do
  Asaas, uma assinatura `ativa` que não é paga recebe **uma cobrança nova
  por dia, sem fim** (10 em 10 dias simulados, no `main` e nesta série).
  As anteriores viram `expirado` só no banco do CaixaClaro; no Asaas, cada
  uma foi criada com vencimento em 7 dias. Como o Asaas real trata essas
  cobranças antigas não foi verificado. É o algoritmo de
  CONTRATOS_INTERNOS §12 (cobra de novo sempre que não há cobrança
  pendente dentro do prazo local; comportamento 3: "nova cobrança
  permitida"), combinado com `expira_em` de 24 h e vencimento de 7 dias.
  Decidir a cadência e quando parar.
- **Notificações do Asaas**: o cliente é criado sem desligar as
  notificações. Não é possível determinar daqui se a conta do Asaas manda
  e-mail a cada cobrança — conferir no painel antes de cobrar gente real,
  por causa do item anterior.
- Trocar o token do bot do Telegram e tratar os logs antigos do VPS (R9
  impede novos vazamentos, não apaga os antigos).
- Monitor externo; páginas de Privacidade, Termos e Contato; exportar e
  excluir conta.
- Sessão de 60 minutos sem renovação (`JWT_EXPIRA_MINUTOS`).
- Retomar assinatura pausada sem pagar (não há rota).
- O cadastro revela se o e-mail ou o CPF já têm conta.
- OFX: usar o `FITID` como identidade deduplicaria o mesmo arquivo sozinho,
  mas muda CONTRATOS_INTERNOS §3.
- HSTS (na Cloudflare) e CSP.
- Webhook do Telegram responde 400 para token inválido.
- MEI que informa o ano de abertura e traz lançamentos de anos anteriores:
  o limite cheio é aplicado a esses anos.
- Para pessoa física, a soma "do que você recebeu por trabalho" inclui o
  que foi respondido como venda.

### 8.4 Implantação

- Reconstruir as imagens `api` (código e migration 013) e `web` (Caddyfile
  e frontend). Só a `api` nova, sem o Caddy novo, mantém o limite por IP
  como antes (sem regressão).
- O `migrator` aplica a 013 antes da API subir. A consulta B2 do relatório
  de estado, rodada antes, mostra quantas confirmações antigas estão fora
  da soma; rodada depois, o que sobrar não se encaixa no critério do
  backfill e precisa ser visto caso a caso.
- Depois de implantar: a consulta B1 do relatório de estado deve mostrar IPs
  variados; a resposta deve trazer `X-Content-Type-Options`; o
  `systemctl status` do backup passa a mostrar falha quando a cópia no R2
  falhar. A unidade do agendador do backup não deve usar
  `Restart=on-failure`.
- A correção do IP (DR7) confia no `CF-Connecting-IP` quando a conexão com
  o Caddy vem de endereço interno. Antes de implantar, conferir que as
  portas 80 e 443 do VPS não respondem de fora, em IPv4 e IPv6: um caminho
  externo que chegue ao contêiner com endereço interno (por exemplo, IPv6
  repassado pelo docker-proxy a um contêiner sem IPv6 — inferência sobre o
  Docker, não verificada no VPS) deixaria quem entra por ali escolher o IP
  que o limite enxerga. Se responderem, fechar (firewall, ou publicar a
  porta só em 127.0.0.1 se o cloudflared usa localhost). E se o cloudflared
  alcançar o Caddy pelo IP público do VPS, o limite continua global, como
  hoje; a B1 mostra.

### 8.5 Verificação

- Backend: 653 passed (575 do M13 + 78 novos). Eval do golden dataset: PASS,
  métricas idênticas (A = 0, B = 1,000, C = 0,235, D = 0).
- Cada commit da série rodado sozinho: suíte do backend (575, 596, 615,
  624, 629, 640, 640, 650, 650, 651, 653, 653, 653 e 653 passed, do
  primeiro ao último), typecheck e eval verdes em todos; lint com os mesmos
  2 avisos de antes em todos; build do frontend no último.
- Cada correção traz testes. Rodados também contra o código anterior, onde
  falham: R1 (J21, J22, J26 no M13 original), R7 (4 testes de cobrança) e
  o gerador do `bateria_c`. R5 e R9 foram reproduzidos antes e depois por
  roteiro executado com as funções reais. Os demais defeitos foram
  reproduzidos na auditoria do relatório de estado, antes da correção.
- Frontend: typecheck e build sem erro; lint com os mesmos 2 avisos de antes.
- Navegador (Chromium, 390 px): jornada completa de 18 telas sem rolagem
  horizontal e sem resposta de erro da API; Assinatura 28/28 verificações;
  sessão encerrada 6/6; extratos sobrepostos 10/10.
- Caddy 2.10.2 real com o Caddyfile da série: configuração válida;
  cabeçalho de conexão forjado chega substituído; cabeçalhos de segurança
  presentes na página e na API.
- Limites: extratos sintéticos; Asaas substituto; nenhum aparelho real;
  nada em produção.
