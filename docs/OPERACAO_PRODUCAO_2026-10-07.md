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

## Pendências operacionais ainda abertas

- monitor externo de `https://meucaixaclaro.com.br/readyz` com alerta real
  comprovado — último critério aberto de M10.C;
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
