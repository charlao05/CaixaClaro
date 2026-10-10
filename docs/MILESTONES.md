# Milestones

## M0 — Reconciliação documental
Critérios de aceite:
  - [x] 8 documentos existem no commit raiz 7dc3d4b
  - [~] Nenhuma perda material vs M0 v1.6 aprovado - nao verificavel:
        M0 v1.6 nao existe no repositorio. c3ec0fc registra restauracao
        integral, mas sem o original a completude e inaferivel.
  - [~] Inspecao de integridade PASS - artefato da inspecao original
        nao recuperavel. Auditoria de 30/09/2026 confirma o estado
        atual: git diff --check PASS, 8 arquivos presentes no HEAD
        e git fsck sem indicacao de corrupcao.
  - [x] Commit raiz 7dc3d4b com mensagem "chore: establish CaixaClaro M0..."

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
  - [x] B11/B12 nominal nao recuperavel; criterios do bloco M5 cobertos
        por testes nomeados em test_billing.py e test_webhook_asaas.py.
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
  - [x] Componentes consomem API
        Evidência: 11 arquivos em frontend/src/screens/ importam de
        frontend/src/services/ e chamam os serviços efetivamente
        (Dashboard.tsx:4-6 → getResumo/listarAlertas/listarFila em :47-49;
        Login.tsx:2 → login em :22; Ingestao.tsx:11 → colar em :87,
        importar em :110; Contas.tsx:10-15 → listarContas em :76,
        conectarBanco em :176, revogarConta em :209, iniciarSync em :223;
        Assinatura.tsx:4-6 → getStatus/listarPayments/checkout/pausar;
        Revisao.tsx:4 → listarFila em :87, confirmar em :113;
        Alertas.tsx:4 → listarAlertas em :47, marcarAlertaLido em :74;
        ListaTransacoes.tsx:7 → listarTransacoes em :54,:77;
        Opiniao.tsx:8 → getOpiniao em :54; Perfil.tsx:9-13 → getPerfil
        em :79, atualizarPerfil em :120, gerarTokenVinculacao em :139;
        Register.tsx:2 → register em :45).
        Cobertura CI: typecheck + lint via .github/workflows/frontend.yml.
        Sem teste E2E das telas contra API real.
  - [x] Motor fiscal não existe no bundle
        Evidência: git grep -n "domain/fiscal" -- frontend/ → vazio;
        git grep -n "from caixaclaro" -- frontend/ → vazio; strings
        exclusivas do motor fiscal ('heuristica', 'regra_personalizada')
        ausentes do artefato dist/assets/index-*.js gerado por
        npm run build.
        Ressalva técnica: frontend/src/screens/Revisao.tsx:21,:41 hardcoda
        IDs de categoria ('receita_servico'). É vocabulário de UI, não o
        motor. Candidato a follow-up (centralizar taxonomia via endpoint);
        não bloqueia o critério.
  - [x] Maria Silva não ocorre em código de produção
        Critério original: "Maria Silva apenas em modo demonstração".
        Reescrito porque não existe mecanismo de modo demonstração no
        repositório: git grep -i "modo.demo|modo_demo|demo_mode" e
        git grep -i "seed|dados.demo|dados_demo" em backend/src e frontend/src
        retornam vazio. O critério original era inavaliável literalmente.
        Evidência do critério operacional: git grep -n --untracked
        "Maria Silva" retorna 4 ocorrências, todas em backend/tests/
        (test_asaas.py:105,:113; test_perfil.py:12,:13). Zero em
        backend/src/, zero em frontend/src/, zero no bundle.
  - [x] services/api.ts injeta JWT
        Evidência: frontend/src/services/api.ts:92-93 injeta
        Authorization: Bearer ${token} quando token é passado.
        Todos os serviços autenticados passam token (alertas.ts, billing.ts,
        contas.ts, fila.ts, fiscal.ts, perfil.ts, sync.ts, tax_opinion.ts,
        telegram.ts, transacoes.ts). auth.ts:26-34 (register) e :40-46
        (login) são públicos por design; :50-54 (logout) é autenticado.
        Ressalva técnica: RequestOptions não obriga token no tipo
        TypeScript; a garantia é por uso correto, não por constraint. Não
        bloqueia o critério; registrado como nota de robustez.

M8 fechado documentalmente em 2026-09-30. Nenhuma alteração de código
ou infraestrutura foi feita neste ciclo.

## M9 — Eval em CI
Critérios:
  - [x] Golden dataset versionado em tests/golden/
  - [x] CI roda eval a cada push
  - [x] Resultado publicado em /api/v1/eval/ultima-execucao
  - [x] M9.4 fechado conforme contrato operacional em docs/M9.4_CONTRATO.md
        A–H histórica não recuperável; critérios operacionais atuais,
        gates 0–8, publicação e consumo do snapshot foram verificados.

## M10 — Produção

Este milestone foi reestruturado para separar três naturezas que estavam
misturadas: artefato versionado, ensaio mecânico executado e operação em
ambiente real. Cada bloco abaixo declara sua natureza e o tipo de evidência
que o fecha.

> Nota de nomenclatura: a divisão M10a/M10b usada em
> docs/M10_DECISAO_2026-08.md é histórica e pertence à decisão
> arquitetural. Não corresponde diretamente à divisão atual M10.A/B/C,
> que é a estrutura de aceite/evidência adotada aqui.

### M10.A — Artefatos versionados no repositório (natureza A)

Critérios verificáveis por `arquivo:linha` no repositório.

- [x] Compose de produção define db, migrator, api, worker, web
      evidência: docker-compose.prod.yml
- [x] Migrations rodam como serviço one-shot do compose, não no entrypoint da API
      evidência: docker-compose.prod.yml (serviço migrator) +
      backend/src/caixaclaro/migration_runner.py
- [x] Caddyfile roteia /api/*, /healthz, /readyz
      evidência: Caddyfile + backend/tests/test_caddyfile.py (leitura do
      arquivo e Caddy de verdade; adicionado em 2026-10-10)
- [x] GET /healthz (liveness) existe
      evidência: backend/src/caixaclaro/main.py; desde 2026-10-10 responde
      também a HEAD (backend/tests/test_health.py)
- [x] GET /readyz (readiness) verifica pool PostgreSQL
      evidência: backend/src/caixaclaro/main.py; desde 2026-10-10 responde
      também a HEAD, e o 503 com o banco fora está sob teste
      (backend/tests/test_health.py)
- [x] Logging JSON estruturado existe e é testado
      evidência: backend/src/caixaclaro/logging_config.py +
      backend/tests/test_logging_config.py
- [x] Webhooks Pluggy/Asaas/Telegram verificam tokens nos headers
      evidência: backend/src/caixaclaro/api/webhooks.py
- [x] Scripts de backup e restore existem, com Dockerfile dedicado
      evidência: backup/backup.sh, backup/backup-vps.sh, backup/backup.ps1,
      backup/restore.ps1, backup/restore-funcional.ps1, backup/Dockerfile

### M10.B — Ensaios mecânicos executados (natureza B)

Fecham quando houver registro rastreável no repositório: data, comando e
saída, em docs/ ou backup/.

- [x] Rollback ensaiado (retag da imagem anterior + recreate de api/worker)
      ENSAIO EXECUTADO em 2026-09-30 21:51 (local).
      Imagens: caixaclaro-api:latest = 13c323d5ccf1 (mais nova) e
      caixaclaro-api:preserved-ff4f1bf2d499 = ff4f1bf2d499 (anterior).
      Direção 1 (preserved → latest):
        docker tag caixaclaro-api:latest caixaclaro-api:prod
        docker compose -f docker-compose.prod.yml up -d --no-deps --force-recreate api worker
        Evidência: docker inspect → sha256:13c323d5ccf1; /healthz=200;
        worker log: worker_started worker-fddf95fe.
      Direção 2 (latest → preserved, rollback efetivo):
        docker tag caixaclaro-api:preserved-ff4f1bf2d499 caixaclaro-api:prod
        docker compose -f docker-compose.prod.yml up -d --no-deps --force-recreate api worker
        Evidência: docker inspect → sha256:ff4f1bf2d499; /healthz=200;
        worker sem erro no startup.
      Ressalva: /healthz não exercita o pool do PostgreSQL; prova que os
      processos sobem e respondem, não que a versão anterior é compatível
      com o schema atual. /readyz teria fechado essa lacuna.
      Histórico: [x] original rebaixado a [~] por falta de registro
      rastreável; revertido a [x] com base na evidência acima.
- [x] Restore funcional ensaiado a partir de um backup real
      ENSAIO EXECUTADO em 2026-09-30 21:40.
      Pacote: caixaclaro-20261001T004021Z.tar.gpg.
      Script: backup/restore-funcional.ps1.
      Resultado: RESTORE FUNCIONAL CONCLUIDO.
      Evidências: extração PASS; .env restaurado com JWT_SECRET,
      CPF_HMAC_KEY e CPF_AES_KEY; Postgres pronto; pg_restore PASS;
      /healthz=200; register=201 + token; login=200 + token;
      cpf_cifrado decifrado com len=11; worker iniciado sem erro.
      Cadeia de backups registrada em C:\backups\caixaclaro\backup.log.

### M10.C — Operação em ambiente real (natureza C)

Critérios que exigem evidência do ambiente real. O repositório pode
registrar essa evidência, mas não substitui a execução.

- [x] Deploy em VPS/host real
      Evidência operacional registrada em
      docs/OPERACAO_PRODUCAO_2026-10-07.md: VPS Hetzner, domínio
      meucaixaclaro.com.br, HTTPS via Cloudflare Tunnel e uma única réplica
      ativa após eliminação da réplica concorrente do Windows.
- [x] Backup agendado em produção e restauração comprovada
      Evidência operacional de 2026-10-09: timer diário às 03:00 UTC;
      objeto diário em R2 (`caixaclaro-20261008T030009Z.tar.gpg`) e seu
      `.sha256` baixados do bucket `caixaclaro-backup`; `sha256sum -c`
      retornou OK; arquivo GPG decifrado; `pg_restore` executado em banco
      separado `restore_test`; 20 tabelas restauradas/listadas. Contagens
      verificadas de `users`, `accounts`, `transactions`, `products`,
      `subscriptions` e `sessions` bateram com o snapshot comparável.
      `audit_log` tinha 49 registros no snapshot e 52 no banco de produção
      no momento da comparação, diferença temporal de 3 eventos após o dump.
      Diretório temporário e extração contendo `.env` foram removidos, e a
      verificação final não encontrou resíduo em `/tmp`. Ver
      docs/OPERACAO_PRODUCAO_2026-10-07.md.
- [ ] Observabilidade ativa em produção
      /readyz existe e é verificável localmente, mas ainda não há monitor
      externo com alerta funcional comprovado.
      Preparação de 2026-10-10 (não fecha o critério): o que um monitor
      enxerga em cada situação foi ensaiado fora do servidor e está em
      docs/OPERACAO_PRODUCAO_2026-10-07.md, atualização de 2026-10-10.
      Fecha quando estiverem registrados: o monitor configurado (serviço,
      tipo, endereço, intervalo, canal do alerta), uma queda provocada, o
      alerta recebido e o aviso de retorno, com os horários.
- [x] Primeiro uso real end-to-end
      Evidência: vinculação do Telegram e recuperação de senha executadas
      ponta a ponta em produção. O fluxo de reset entregou o código,
      aceitou-o dentro da validade, redefiniu a senha, permitiu login com
      a nova senha e rejeitou a senha anterior. Isso fecha o critério de
      primeiro uso real E2E; não significa certificação exaustiva de todas
      as telas, integrações ou combinações possíveis. O smoke test ampliado
      após deploy permanece como hardening operacional, não como substituto
      do monitor externo que falta para M10.C.

### Notas

- Naturezas A e B podem ser comprovadas por evidência versionada no
  repositório. Natureza C exige evidência do ambiente real; o repositório
  pode registrar essa evidência, mas não substitui a execução real.
- O critério "Backup e observabilidade ativos" foi quebrado em três
  critérios por natureza: artefatos existem (M10.A), ensaios executados
  (M10.B), operação real (M10.C).
- O [x] original de "Rollback ensaiado" foi rebaixado a [~] pela mesma
  disciplina probatória aplicada ao M0 e ao M8.
- Deploy automatizado permanece fora de escopo por decisão consciente
  (docs/M10_DECISAO_2026-08.md, seção "Fora de escopo").

Ver docs/M10_DECISAO_2026-08.md para topologia e decisões de arquitetura.


## M11 — Meu Negócio: cadastro, precificação e estoque

Escopo desta entrega: Fase 1 (cadastro de produto/serviço + precificação) e
Fase 2 (movimentação de estoque manual + consulta de saldo) do plano de 6
fases discutido para o incremento. Fases 3–6 (ingestão por planilha, alertas
de estoque via Telegram, contrato de API para ERP/CRM, ingestão por foto/OCR)
não foram iniciadas — ver "Fora de escopo" abaixo.

A precificação segue Categoria I da consulta institucional ao CRC-ES
(docs/CONSULTA_CRC_ES.md) e o contrato de comportamento em
docs/REGRA_ORIENTADOR.md: cálculo puro sobre dado informado, toda saída
rotulada por estado (calculo/limitacao), recusa explícita quando faltam
dados. A consulta ao CRC-ES segue PENDENTE de resposta — nenhum cálculo
além dos quatro itens já descritos nela foi implementado (decisão registrada
em backend/src/caixaclaro/domain/negocio/precificacao.py, docstring).
A movimentação de estoque é tratada como Categoria II (consolidação de
eventos informados pelo usuário — sem inferência a partir de transação
bancária).

Critérios:
  - [x] Cadastro de produto/serviço (CRUD) com isolamento por usuário
        evidência: backend/src/caixaclaro/api/produtos.py +
        backend/src/caixaclaro/services/produtos.py +
        backend/migrations/011_negocio.sql (tabela products) +
        backend/tests/test_produtos.py (8 testes, EXECUTADO: 8 passed)
  - [x] Precificação Categoria I: diferença preço-custo, margem de
        contribuição (R$ e %), ponto de equilíbrio (unidades e receita),
        comparação de até 2 cenários sem indicar preferência
        evidência: backend/src/caixaclaro/domain/negocio/precificacao.py +
        backend/src/caixaclaro/services/precificacao.py +
        backend/src/caixaclaro/api/precificacao.py +
        backend/tests/test_precificacao_domain.py (12 testes) +
        backend/tests/test_precificacao.py (8 testes)
        EXECUTADO: 20 passed. Inclui teste de conformidade explícito com
        REGRA_ORIENTADOR.md (toda saída rotulada por estado; limitação
        sempre presente; nenhuma palavra de recomendação na resposta).
  - [x] Sistema se recusa a calcular quando faltam dados (DadosInsuficientes)
        em vez de assumir default silencioso
        evidência: backend/tests/test_precificacao_domain.py::
        test_recusa_calcular_sem_preco,
        test_item3_sem_custos_fixos_vira_limitacao_nao_erro
  - [x] Movimentação de estoque (entrada/saída) com saldo derivado por soma
        do histórico, nunca armazenado de forma redundante
        evidência: backend/src/caixaclaro/services/estoque.py
        (saldo_atual: SUM sobre stock_movements)
  - [x] Guardrail NUNCA estoque negativo, inclusive em movimento de ajuste
        evidência: backend/src/caixaclaro/domain/negocio/estoque.py
        (EstoqueNegativoRecusado) + backend/tests/test_estoque_domain.py
        (15 execuções: 7 funções + 4 + 4 parametrizadas) +
        backend/tests/test_estoque.py::
        test_estoque_negativo_recusado_409 (HTTP 409 real, EXECUTADO)
  - [x] Idempotência real em POST de movimento (reusa
        security/idempotency.py já existente, mesmo padrão de /transacoes)
        evidência: backend/tests/test_estoque.py::
        test_idempotencia_mesma_chave_nao_duplica_movimento (EXECUTADO)
  - [x] Trilha de auditoria em audit_log para criação/atualização de
        produto e registro de movimento
        evidência: chamadas a registrar_auditoria em
        backend/src/caixaclaro/services/produtos.py e
        backend/src/caixaclaro/services/estoque.py
  - [x] Suíte completa do projeto permanece verde após o incremento
        EXECUTADO: 521 passed (470 pré-existentes + 51 novos deste
        milestone), 0 failed. Migration 011 aplicada sobre banco real.

Bugs reais encontrados e corrigidos durante esta entrega (não eram do meu
código novo isoladamente — ficaram latentes porque nenhum endpoint anterior
tinha as mesmas condições):
  - security/audit.py:registrar_auditoria e security/idempotency.py:
    executar_com_idempotencia esperam user_id como str; o valor retornado
    por usuario_ativo (api/deps.py) é um asyncpg.pgproto.UUID nativo.
    A convenção já usada em services/contas.py (_uuid.UUID(str(x))) foi
    replicada nos pontos de chamada novos — módulos de segurança
    compartilhados não foram alterados.
  - main.py:handler_validacao serializava exc.errors() com JSONResponse
    puro; quando um campo Decimal falha validação (ex.: quantidade=0 com
    Field(gt=0)), o erro de validação do Pydantic ecoa o valor bruto
    rejeitado (Decimal), que json.dumps não serializa — 500 em vez de 422.
    Esta era a primeira rota do projeto com campo Decimal validável, por
    isso o bug nunca havia aparecido. Corrigido com jsonable_encoder
    (mesmo utilitário que o handler padrão do FastAPI usa).
    evidência: backend/src/caixaclaro/main.py +
    backend/tests/test_estoque.py::test_quantidade_zero_rejeitada
    (passava a reproduzir o bug antes da correção; passa limpo depois)
  - Colisão de numeração de migration: 010 já estava ocupado por
    010_payments_metodo_cancelado.sql (linha B, cartão avulso). Migration
    deste milestone renumerada para 011_negocio.sql antes de aplicar.

Fora de escopo nesta entrega (declarado, não escondido):
  - Baixa automática de estoque a partir de uma transação bancária
    confirmada. Decisão deliberada: inferir produto/quantidade a partir de
    uma transação sem confirmação explícita do usuário violaria
    REGRA_ORIENTADOR.md (hipótese virando fato sem confirmação). O vínculo
    existe no schema (stock_movements.referencia_transacao_id) mas a
    criação do movimento continua sempre um ato explícito do usuário.
  - Ingestão de movimentos por planilha, foto/OCR ou API de ERP/CRM
    (Fases 3–6 do plano original).
  - Alertas de estoque mínimo/validade via Telegram (depende de Fase 3/4;
    o canal já existe — services/telegram.py — mas não foi acionado por
    este módulo).
  - Endpoint de leitura de pricing_scenarios salvos (a gravação existe e é
    testada; não há endpoint GET para consultá-los nesta versão).
  - "receita projetada"/"lucro projetado" a partir de volume_hipotese —
    deliberadamente fora dos quatro itens já descritos na consulta ao
    CRC-ES; ver docstring de domain/negocio/precificacao.py.
  - Estado de deploy no momento da implementação (2026-10-03): ainda não
    aplicado em produção. Atualização posterior: M11 foi implantado no
    ambiente real em 06–07/10/2026; ver docs/OPERACAO_PRODUCAO_2026-10-07.md.
    Atualização de 2026-10-09: backup diário remoto no R2 e restauração
    comprovada; o critério M10.C que segue aberto é observabilidade externa
    com alerta funcional de /readyz. Pendências de reboot/firewall e retirada
    do serviço redundante no Windows permanecem no hardening operacional.

## M12 — Recuperação de senha por Telegram

Escopo: recuperação de acesso por código temporário enviado pelo Telegram,
com resposta indistinguível na solicitação, uso único do código, expiração,
revogação de sessões e interface web para redefinição.

Critérios:
  - [x] Migration 012 cria `password_reset_tokens` sem armazenar o código
        em claro.
  - [x] Código de recuperação possui 6 dígitos e validade de 15 minutos.
  - [x] Nova solicitação invalida a solicitação ativa anterior.
  - [x] Consumo do código é atômico e de uso único.
  - [x] Solicitação responde 202 de forma indistinguível para e-mail
        inexistente e conta sem Telegram.
  - [x] Reset bem-sucedido troca a senha e revoga sessões ativas.
  - [x] Frontend possui fluxo "Esqueci minha senha" e "Redefinir senha".
  - [x] Suíte M12: 547 testes verdes registrados no commit 8f57db0.
  - [x] E2E real em produção: código entregue no Telegram, senha redefinida,
        novo login aceito e senha anterior rejeitada.

Limitação conhecida:
  - O canal inicial é Telegram. Conta sem `telegram_chat_id` não recebe o
    código. E-mail é um incremento posterior de produto, não parte do M12 v1.

## M13 — Jornada do público-alvo

Escopo: fazer o ciclo central funcionar para quem o produto diz atender —
MEI, autônomo no CPF, assalariado com renda extra, pequeno negócio e quem
está começando — e fazer a interface falar a língua dessa pessoa.
Contexto, achados e decisões: docs/AUDITORIA_JORNADA_2026-10-09.md.

Critérios:

- [x] Entrada confirmada como trabalho ou venda entra na soma (M4 §9)
      evidência: tests/test_jornada_publico_alvo.py::test_j1…;
      tests/test_confirmacao.py::test_confirmar_promove_para_receita_incrementa_faturamento
      (agora verifica o delta e o acumulado)
- [x] O que o usuário lê não vaza vocabulário interno nem se contradiz
      evidência: test_j2, test_j3, test_j18 (varre os sete textos de todos
      os lançamentos de cinco perfis)
- [x] Palpite não se apresenta como fato; direção do dinheiro é respeitada
      evidência: test_j4 a test_j7
- [x] Quem não é MEI não recebe teto nem alerta de MEI; limite proporcional
      no ano de abertura
      evidência: test_j8, test_j9, test_j17
- [x] Mensagens em moeda brasileira; data sem ano nunca no futuro; erro de
      arquivo sem estrutura interna
      evidência: test_j10 a test_j12
- [x] Ensinar uma vez vale para os iguais e para os próximos
      evidência: test_j13
- [x] Todo palpite tem conserto
      evidência: test_j14, test_j15
- [x] Dá para começar sem extrato
      evidência: test_j16
- [x] Jornada completa por perfil (5 perfis)
      evidência: test_j18[…]
- [x] Colagem em colunas, ponto decimal e CSV com data ISO são aceitos
      evidência: test_j19
- [x] Vocabulário de respostas vem do backend e respeita a taxonomia v1
      evidência: test_j20
- [x] Suíte completa verde e eval inalterado
      EXECUTADO em 2026-10-09: 575 passed; eval PASS
      (A=0, B=1.000, C=0.235, D=0). Frontend: build e lint sem erro.

Ressalvas (natureza da evidência):

- Extratos sintéticos; nenhum extrato real de banco foi usado.
- Telas compilam e passam no lint, mas não foram vistas em navegador.
- Nada foi exercitado em produção nem contra Pluggy/Asaas/Telegram reais.
- Os textos do parecer são conteúdo fiscal voltado ao usuário e aguardam
  leitura de um contador.

Fora de escopo, declarado: ver seção 5 da auditoria (calendário de
obrigações, recuperação por e-mail, páginas legais, exportar/excluir conta,
medição de uso, navegação com histórico, preço, taxonomia v2).

## M14 — Correções pré-lançamento (revisão de 2026-10-09)

Escopo: corrigir o que a revisão independente do M13 e a auditoria do
`main` encontraram antes de receber usuários reais. Achados, decisões e o
que ficou aberto: docs/AUDITORIA_JORNADA_2026-10-09.md, seção 8.

Critérios:

- [x] Resposta lembrada respeita a direção do dinheiro e só promete o que
      cumpre (R1)
      evidência: tests/test_regras_pessoais.py; test_jornada_publico_alvo.py
      ::test_j21, test_j22, test_j26 (falham no M13 original)
- [x] Texto ao usuário só promete o que existe (R2, R4, card da landing)
      evidência: test_telegram.py::test_telegram_start_envia_confirmacao;
      test_tax_opinion.py::test_venda_de_pessoa_fisica_declara_o_que_o_produto_nao_sabe
- [x] Rotas novas do M13 isoladas por conta (R3)
      evidência: test_jornada_publico_alvo.py::test_j23 a test_j25
- [x] Faturamento do ano = soma dos lançamentos do ano; outro ano não
      corrompe o painel; confirmações antigas entram na soma (R5, R6)
      evidência: tests/test_faturamento_por_ano.py; tests/test_migracao_013.py;
      test_sync.py::test_worker_sync_que_atravessa_a_virada_soma_cada_ano
- [x] Voltar no dia seguinte para pagar funciona; quem já assinou renova
      pela tela (R7, R8)
      evidência: test_billing.py (4 testes de R7, situação do acesso);
      test_autorizacao.py; navegador 28/28
- [x] Token do bot e CPF fora do log (R9)
      evidência: test_logging_config.py (funções reais com transporte simulado)
- [x] Limite de tentativas por cliente atrás do Caddy e do Tunnel (R10)
      evidência: tests/test_ip_cliente.py; Caddy 2.10.2 real com o Caddyfile;
      desde 2026-10-10, tests/test_caddyfile.py (cabeçalho forjado chega
      substituído; passa em 22 versões do Caddy, da 2.7.0 à 2.11.7)
- [x] Sessão encerrada volta ao login (R11)
      evidência: navegador 6/6
- [x] Extratos sobrepostos: aviso de repetidos, apagar e desfazer (R12)
      evidência: tests/test_lotes.py; navegador 10/10
- [x] Backup sinaliza falha da cópia no R2 (R13)
      evidência: script real com stubs (código 2)
- [x] Suíte completa verde e eval inalterado
      EXECUTADO em 2026-10-10: 653 passed; eval PASS
      (A=0, B=1.000, C=0.235, D=0). Frontend: typecheck, build e lint sem
      erro (2 avisos que já existiam). Jornada completa em navegador
      (18 telas, 390 px) sem rolagem horizontal e sem erro de API. Cada
      commit da série também rodado sozinho (suíte, typecheck, lint e eval).
- [ ] Implantado em produção, com as portas 80 e 443 do VPS sem resposta
      de fora (IPv4 e IPv6) e a consulta B1 mostrando IPs variados
- [ ] Token do bot do Telegram trocado e logs antigos tratados

Ressalvas (natureza da evidência):

- Extratos sintéticos; Asaas exercitado por um substituto local; nenhum
  aparelho real; nada executado em produção.
- Cadência da renovação e notificações do Asaas ficaram para decisão
  (seção 8.3 da auditoria).
