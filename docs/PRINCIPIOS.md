# Princípios

## 1. Backend como autoridade
Classificação, regras de negócio, guardrails, opinião fiscal, billing, autenticação e autorização são decididos no backend. React apenas apresenta estado e envia comandos.

## 2. PostgreSQL como fonte de verdade
Dados financeiros, identidade, sessões, decisões, cobranças, eventos e auditoria persistem no PostgreSQL.

## 3. Evidência antes de status
Código existente não é prova de funcionamento. PASS exige execução e critério satisfeito.

## 4. Dinheiro usa Decimal
Valores monetários usam Decimal/Numeric. Float não é permitido para cálculo monetário.

## 5. Idempotência explícita
Integrações externas e comandos repetíveis possuem identidade, estado e comportamento idempotente.

## 6. Cliente não é fonte de verdade
Nenhum campo autoritativo depende do React sem validação e decisão do backend.

## 7. Segurança por fronteira
JWT possui sessão revogável. CPF usa HMAC para busca e AES-GCM para armazenamento reversível. Segredos não pertencem ao frontend.

## 8. Integrações externas são não confiáveis
Timeout, duplicidade, entrega fora de ordem e falhas parciais são estados normais.

## 9. Auditoria
Mudanças relevantes deixam trilha auditável com ator, ação e contexto.

## 10. Todo erro vira caso de teste
Todo bug encontrado — em qualquer camada — vira caso no golden dataset ou teste unitário. O mesmo erro nunca precisa acontecer duas vezes para ser conhecido.

## 11. Contrato congelado
Após M0 PASS, mudanças de contrato exigem registro em DECISOES.md com data e motivo.

## 12. Critério de parada
Milestone só reabre por (a) contradição interna, (b) impossibilidade técnica, (c) afirmação externa não verificada ou (d) risco de perda de dado/dinheiro.
