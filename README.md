# CaixaClaro

## Produto

CaixaClaro é uma aplicação financeira/fiscal para MEI, autônomos e pequenos negócios.

### Fonte de verdade
- Backend Python/FastAPI: autoridade de domínio.
- PostgreSQL: fonte de verdade persistente.
- React: cliente da API.
- Pluggy: integração bancária.
- Asaas: cobrança controlada pelo CaixaClaro; PIX e cartão avulso via Invoice conforme configuração.
- Telegram: vinculação, notificações e canal inicial de recuperação de senha.
- Eval/golden dataset: fora do cliente, no backend/CI.

### Evidência

Código existe ≠ funciona ≠ testes passam ≠ produção.

Estados usados no projeto: IMPLEMENTADO, VERIFICADO, PASS, PRODUÇÃO.

### Milestones

- **M0–M9:** arquitetura, backend, segurança, ingestão, integração bancária, inteligência fiscal, billing, workers, Telegram, frontend e eval em CI — PASS documental/testado conforme `docs/MILESTONES.md`.
- **M10:** produção — implantado em VPS com domínio e Cloudflare Tunnel; segue parcial até backup agendado e monitor externo de `/readyz`.
- **M11:** Meu Negócio — cadastro, edição e remoção de produto/serviço e precificação na interface; o backend também dispõe de movimentação manual de estoque. Fases 3–6 não iniciadas.
- **M12:** recuperação de senha por Telegram — E2E real registrado em produção. Contas sem Telegram vinculado ainda não têm canal alternativo; e-mail é incremento futuro.

### Documentação operacional

- `docs/MILESTONES.md`: critérios e evidências por milestone.
- `docs/OPERACAO_PRODUCAO_2026-10-07.md`: evidências e pendências da operação real.
- `docs/M10_DECISAO_2026-08.md`: decisão arquitetural histórica, complementada pela atualização operacional de outubro.

M1 não começa antes de M0 PASS.
