# Golden dataset v1

Dataset anotado para eval do classificador fiscal (M4_CONTRATO 14).

Formato: id, descricao, valor, categoria_esperada, nota (opcional).

Regras:
- id estavel, nunca reaproveitar
- valor em string com 2 casas decimais
- categoria_esperada = o que o usuario esperaria, nao o que o
  classificador atual devolve
- se o classificador errar, ajustar o classificador, nao a anotacao

Metricas alvo: A=0, B>=0.85, C em 0.10..0.25, D=0.
