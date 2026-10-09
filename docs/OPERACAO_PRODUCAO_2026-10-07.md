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

## Pendências operacionais ainda abertas

- backup agendado em storage remoto;
- monitoramento externo com alerta de indisponibilidade de `/readyz`;
- persistência das regras `iptables DOCKER-USER` após reboot;
- atualização de `FRONTEND_URL` no ambiente de produção para o domínio;
- remoção do `cloudflared` do Windows para evitar reativação acidental.

## Regra probatória

Evidência de produção deve ser classificada como:
IMPLEMENTADO ≠ VERIFICADO ≠ PASS ≠ PRODUÇÃO.

Para M10.C, cada critério operacional só deve ser marcado como concluído
quando houver registro objetivo da execução e do resultado.
