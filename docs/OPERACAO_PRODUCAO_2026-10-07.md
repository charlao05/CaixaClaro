# CaixaClaro — Evidência de operação em produção — 2026-10-07

## Natureza da evidência

Este documento registra evidências operacionais informadas e validadas
durante a sessão de 06–07/10/2026. Ele não substitui os comandos/telemetria
do ambiente; serve para tornar rastreável no repositório o que foi observado
em produção.

## Ambiente

- VPS: Hetzner.
- Entrada pública: domínio `meucaixaclaro.com.br`.
- TLS/HTTPS: Cloudflare Tunnel.
- Topologia do Tunnel: uma réplica ativa após remoção da réplica concorrente
  que existia no Windows.
- Backend/migrations: cadeia de migrations 001–012 aplicada em produção.

## Evidências funcionais em produção

### Vinculação do Telegram

Em 06–07/10/2026, a vinculação automática do Telegram foi executada em
produção e o usuário recebeu a confirmação de vínculo. Não houve atualização
manual do `telegram_chat_id`.

### Recuperação de senha

O fluxo de recuperação de senha por Telegram foi executado de ponta a ponta
em produção:

1. solicitação de recuperação;
2. código de 6 dígitos entregue no Telegram;
3. código aceito dentro da janela de validade;
4. senha redefinida;
5. login com a nova senha;
6. senha anterior rejeitada.

## Causa-raiz eliminada

Foi identificado que existiam duas réplicas do mesmo Cloudflare Tunnel:
uma no VPS e outra no Windows. As requisições eram distribuídas entre
ambientes diferentes, com bases de dados distintas, produzindo comportamento
aparentemente aleatório. A réplica do Windows foi desativada/removida do
caminho de produção.

## Atualização operacional — backup remoto e restauração — 2026-10-09

### Evidência observada

- O timer de backup foi informado como ativo diariamente às 03:00 UTC.
- Artefato recuperado do R2: `caixaclaro-20261008T030009Z.tar.gpg`, junto
  de seu arquivo `.sha256`, no caminho `caixaclaro-backup/daily/`.
- A verificação `sha256sum -c` retornou `OK`.
- O arquivo foi decifrado localmente com a passphrase mantida no host; nenhum
  valor de credencial/passphrase foi incluído neste documento.
- O arquivo extraído continha `MANIFEST.json`, `db.dump` e configuração
  de ambiente dentro do pacote criptografado.
- `pg_restore` concluiu sem erro no banco separado `restore_test`; as 20
  tabelas foram listadas no banco restaurado.
- As contagens de `users`, `accounts`, `transactions`, `products`,
  `subscriptions` e `sessions` coincidiram com a referência comparável.
  O `audit_log` tinha 49 registros no snapshot restaurado e 52 no banco de
  produção no momento da comparação. A diferença de três eventos é
  compatível com eventos criados após o horário do dump; não se espera que
  uma restauração point-in-time acompanhe alterações posteriores.
- O banco descartável `restore_test` foi removido. O diretório de extração
  em `/tmp` foi apagado e a verificação subsequente não encontrou resíduo
  da pasta temporária nem da árvore `caixaclaro/env`.

### Limites da evidência

Este ensaio comprova checksum, decifragem e restauração lógica do dump em
um banco separado no PostgreSQL do VPS. Não substitui um exercício completo
de disaster recovery em um host isolado, nem comprova sozinho a política de
retenção dos objetos no R2. Para futuras decifragens, preferir
`gpg --passphrase-file /opt/caixaclaro/.backup-passphrase` em vez de expandir
a passphrase como argumento de linha de comando.

## Atualização — preparação do monitor externo e Caddyfile — 2026-10-10

### Natureza da evidência

Tudo nesta seção foi executado **fora do servidor**: ensaios locais (Caddy
2.11.7 com o `Caddyfile` do repositório sem alteração, a API real servida
pelo uvicorn, PostgreSQL 16) e uma leitura do endereço público feita de
fora. Nada aqui foi executado no VPS, e esta seção não registra o estado
da implantação do M13/M14 em produção.

### Leitura externa

Em 2026-10-10, por volta de 11h40 UTC, `GET
https://meucaixaclaro.com.br/readyz` devolveu `{"ok":true}`. É uma leitura
única feita de fora; não é monitor e não diz qual versão está no ar.

### O que um monitor enxerga em cada situação (ensaio local)

Cadeia do ensaio: cliente → Caddy → API → PostgreSQL. Sem a Cloudflare na
frente.

| Situação | GET /readyz | HEAD /readyz | GET /healthz |
|---|---|---|---|
| Tudo no ar, `main` @ `0d905cf` | 200 `{"ok":true}` | **405** | 200 |
| Tudo no ar, com `/readyz` respondendo a HEAD | 200 `{"ok":true}` | 200, sem corpo | 200 |
| PostgreSQL parado | 503 `{"ok":false}` | 503 | 200 |
| PostgreSQL de volta, API não reiniciada | 200 já na primeira leitura | 200 | 200 |
| API parada, Caddy no ar | 502 | 502 | 502 |

O Caddy só encaminha à API o endereço exato. `GET /readyz/` (com barra no
fim) e `GET /ready` recebem **200 com o HTML do front**, com a API no ar ou
fora.

Consequências para a configuração do monitor:

- o monitor deve conferir o corpo (`"ok":true`), não só o código 200. Um
  endereço digitado com uma barra a mais responderia 200 para sempre;
- um monitor que sonda com HEAD recebia 405 com tudo no ar. Em produção,
  isso vale enquanto a versão implantada for anterior à mudança de
  2026-10-10 (docs/DECISOES.md);
- depois de uma queda do banco a API volta sozinha: o aviso de retorno do
  monitor não depende de reiniciar nada.

Não verificado: se a borda da Cloudflare repassa o HEAD como HEAD para
`/readyz` (confere-se com `curl -sI https://meucaixaclaro.com.br/readyz`).

### Grafia do endereço no `Caddyfile`

Foi informado que, durante a implantação de 2026-10-10, o `Caddyfile` do
VPS foi editado à mão, sem commit: `{remote_host}` virou
`{http.request.remote.host}`, na crença de que só a segunda grafia fazia o
IP do cliente chegar à API.

As duas grafias são a mesma configuração. `caddy adapt` devolve
configuração idêntica para os dois arquivos em 22 versões do Caddy (2.7.0
a 2.11.7): o adaptador troca a grafia curta pela longa. Com qualquer uma
das duas, um `X-CaixaClaro-Conexao` forjado pelo cliente chega à API
substituído pelo endereço de quem abriu a conexão
(backend/tests/test_caddyfile.py).

Portanto:

- a edição não mudou o comportamento do Caddy. O que fez o IP do cliente
  passar a ser gravado em produção **não foi determinado**; a troca de
  grafia não pode ter sido;
- não há correção a versionar. A edição local deve ser descartada no VPS
  (`git checkout -- Caddyfile`), para a pasta voltar a ser igual ao
  repositório;
- enquanto a edição existir, o git não a sobrescreve: um `git pull` que
  não traga mudança no `Caddyfile` passa e a mantém; um que traga é
  recusado ("Your local changes to the following files would be
  overwritten by merge"). Simulado num clone descartável.

## Pendências operacionais ainda abertas

- monitor externo de `https://meucaixaclaro.com.br/readyz` com alerta real
  comprovado — último critério aberto de M10.C. O monitor deve conferir o
  corpo da resposta (ver a atualização de 2026-10-10);
- descartar no VPS a edição local do `Caddyfile` (atualização de
  2026-10-10);
- desinstalar o `cloudflared` redundante do Windows (a réplica concorrente
  já foi desativada/retirada do caminho de produção, mas a desinstalação
  preventiva ainda está pendente);
- confirmar, em janela controlada e com acesso alternativo disponível, que
  as regras `iptables DOCKER-USER` persistem após reboot. `iptables-persistent`
  foi informado como instalado/configurado, mas o reboot de validação aguarda
  janela operacional;
- executar/registrar o smoke test ampliado pós-deploy, incluindo o retorno
  real do cartão avulso Asaas depois da correção de `FRONTEND_URL`;
- consolidar a rotação de credenciais identificadas como potencialmente
  expostas em tracebacks, pendência de segurança deliberadamente separada.

A configuração efetiva de `FRONTEND_URL` no VPS foi informada como corrigida
para o domínio de produção. Esse fato não substitui a validação E2E do retorno
do checkout de cartão.

## Regra probatória

Evidência de produção deve ser classificada como:
IMPLEMENTADO ≠ VERIFICADO ≠ PASS ≠ PRODUÇÃO.

Para M10.C, cada critério operacional só deve ser marcado como concluído
quando houver registro objetivo da execução e do resultado.
