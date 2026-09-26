# CaixaClaro

## M0 — arquitetura e contratos

CaixaClaro é uma aplicação financeira/fiscal para MEI, autônomos e pequenos negócios.

M0 contém somente arquitetura, contratos e decisões. Não contém código de produção.

### Fonte de verdade

- Backend Python/FastAPI: autoridade de domínio.
- PostgreSQL: fonte de verdade persistente.
- React: cliente da API.
- Pluggy: integração bancária.
- Asaas: cobrança PIX avulsa controlada pelo CaixaClaro.
- Telegram: canal por webhook.
- Eval/golden dataset: fora do cliente, no backend/CI.

### Evidência

código existe ≠ funciona ≠ testes passam ≠ produção.

Estados: IMPLEMENTADO, VERIFICADO, PASS, PRODUÇÃO.

### Milestones

M0 contratos/arquitetura; M1 backend/API; M2 segurança; M3 ingestão; M4 inteligência; M5 billing; M6 workers; M7 Telegram; M8 frontend; M9 eval CI; M10 produção.

M1 não começa antes de M0 PASS.

M0 PASS somente após os documentos estarem versionados e o commit ser inspecionado.
