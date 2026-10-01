# Regra do Orientador

> **O CaixaClaro pode apresentar dados, cálculos, cenários, comparações
> e limitações derivados das informações disponíveis; não deve apresentar
> como fato, recomendação profissional ou conclusão aquilo que depende
> de julgamento especializado ou de dados que não possui.**

Esta regra se aplica a **toda** funcionalidade do CaixaClaro, não
apenas ao módulo fiscal ou a áreas futuras. Ela é critério de aceite:
uma tela que a viole não entra em produção.

## 1. Os quatro estados de informação

Toda saída visível ao usuário pertence a um destes estados. O estado
precisa ser **explícito na interface**, não apenas no código.

| Estado | Definição | Exemplo |
|---|---|---|
| **FATO** | Dado efetivamente identificado e cuja origem é conhecida, proveniente de fonte externa verificável ou confirmado pelo usuário como ocorrência realizada. | "Saldo em 01/10: R$ 1.234,56" |
| **HIPÓTESE** | Dado fornecido pelo usuário como expectativa, estimativa ou premissa. | "Volume esperado: 100 unidades/mês" |
| **CÁLCULO** | Resultado matemático derivado dos dados disponíveis, com fórmula e variáveis rastreáveis. | "Ponto de equilíbrio = R$ 2.000 / 0,40 = R$ 5.000" |
| **LIMITAÇÃO** | O que não pode ser determinado porque faltam dados, porque a fórmula tem restrição, ou porque o resultado depende de julgamento externo. | "Não foram considerados custos indiretos" |

## 2. As cinco perguntas de aceite

Antes de implementar qualquer tela, endpoint ou mensagem, responder:

1. O sistema está aplicando **fórmula** sobre dado que o usuário
   **informou, confirmou ou que veio de fonte externa** — ou está
   inferindo sozinho?
2. A saída está rotulada **conforme seu estado** — FATO, HIPÓTESE,
   CÁLCULO ou LIMITAÇÃO — e não se apresenta como conclusão aquilo
   que os dados não permitem concluir?
3. A **LIMITAÇÃO** correspondente está visível **na própria tela**,
   não apenas em rodapé ou texto auxiliar?
4. O sistema **pode se recusar a calcular** e dizer "faltam dados"
   como resposta válida — ou tenta preencher com default silencioso?
5. A **origem** de cada dado de entrada é rastreável ao FATO ou
   à HIPÓTESE que o gerou?

Se qualquer resposta for "não", a tela não passa.

## 3. O que o CaixaClaro pode fazer

- Somar, subtrair, multiplicar, dividir, calcular percentuais,
  proporções, médias, medianas — sobre dados fornecidos.
- Comparar cenários hipotéticos lado a lado, sem indicar preferência.
- Consolidar transações já classificadas e confirmadas.
- Exibir a fórmula aplicada, as variáveis substituídas e o resultado.
- Apontar quais dados estão faltando para que um cálculo seja possível.
- Recusar-se a calcular e explicar o motivo.
- Registrar hipóteses do usuário e compará-las, no futuro, com o
  resultado observado — sem julgamento sobre o acerto.

## 4. O que o CaixaClaro não pode fazer

- **Recomendar** preço, mix, canal, investimento ou regime tributário.
- **Concluir** que "o negócio dá lucro" ou "está saudável" com base
  em cálculo parcial.
- **Atestar** custo, estoque, margem, ponto de equilíbrio,
  conformidade fiscal ou qualquer matéria contábil.
- **Emitir** DRE, demonstração, balanço, laudo ou parecer **como
  demonstração contábil formal**.
- **Assinar**, certificar ou validar decisões do usuário.
- **Substituir** contador, advogado, ou qualquer profissional
  habilitado em matéria reservada.
- **Transformar hipótese em fato** sem confirmação explícita do
  usuário.
- **Ocultar limitação** para tornar o resultado mais "amigável".
- **Prometer resultado**: lucro, economia, redução de inadimplência,
  aceitação de preço pelo mercado.

## 5. Relação com o código existente

Esta regra **não é nova**. Ela formaliza o que o CaixaClaro já pratica
em partes do sistema:

- O motor de classificação fiscal trabalha com `needs_review=True`
  quando a confiança é insuficiente — HIPÓTESE aguardando
  confirmação para virar FATO.
- O parecer fiscal já separa fato observado, interpretação,
  relação PF/PJ e pendências — estrutura análoga a
  FATO / CÁLCULO / LIMITAÇÃO.
- O `triagem.py` recusa classificar quando não há base suficiente.

A regra torna esse padrão **universal** e **verificável**, em vez de
ser um comportamento emergente de módulos específicos.

## 6. Consequências

- **Falha na regra é bug**, não decisão de produto. Corrige-se como
  qualquer outro defeito: teste que reproduz, correção, teste que
  confirma.
- **Documentação voltada ao usuário** (marketing, ajuda, onboarding)
  segue a mesma regra. Alegações que a violem são removidas.
- **Prompts para LLM** (quando existirem) herdam a regra. Saídas
  que a violem são filtradas antes de chegar ao usuário.
- **Pareceres externos** (CRC, advogado) podem fundamentar a revisão
  desta regra e das funcionalidades afetadas. Havendo orientação
  relevante, a documentação e o produto são revisados antes da
  ativação de novas funcionalidades.

## 7. Versão

- v1 — 2026-10-01 — primeira formalização.
- A ser revista após resposta do CRC-ES sobre a fronteira entre
  cálculo gerencial e atividade privativa.