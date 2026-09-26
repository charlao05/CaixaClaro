# Estrutura do repositório

M0:
README.md
docs/PRINCIPIOS.md
docs/RECONCILIACAO.md
docs/CONTRATO_API.md
docs/CONTRATOS_INTERNOS.md
docs/DECISOES.md
docs/ESTRUTURA.md
docs/MILESTONES.md

Estrutura-alvo:
/
├── README.md
├── docs/
├── backend/
├── frontend/
├── tests/
└── .github/workflows/

M0 cria somente documentação.

Backend: Python/FastAPI, com API, domínio, persistência, integrações e workers separáveis.
Frontend: React, consumidor da API.
Tests: unitários, integração, contratos, segurança, billing e eval.
CI: PostgreSQL 16 e Python 3.12 como referência inicial.
Segredos somente por mecanismo seguro de CI.
