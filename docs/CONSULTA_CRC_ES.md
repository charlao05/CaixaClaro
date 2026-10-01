# Consulta ao CRC-ES — Enquadramento funcional do CaixaClaro

**Data:** 2026-10-01
**Solicitante:** Charles Rodrigues da Silva
**Assunto:** Consulta institucional sobre enquadramento de funcionalidades
de software de organização financeira e gerencial frente à Resolução
CFC nº 1.640/2021 e ao Decreto-Lei nº 9.295/1946.

## 1. Contexto

O CaixaClaro é uma aplicação web em desenvolvimento, destinada a pessoas
físicas que exercem atividade econômica — autônomos, profissionais liberais,
microempreendedores individuais (MEI) e pequenas empresas.

O produto tem dois módulos previstos:

- **Módulo fiscal (já implementado):** classifica transações bancárias,
  gera parecer informativo sobre possível tratamento tributário e organiza
  informações para o usuário levar ao seu contador.
- **Módulo "Meu Negócio" (em fase de modelagem):** permite que o próprio
  usuário organize informações sobre o seu negócio e visualize cálculos
  derivados dessas informações.

É sobre o **segundo módulo** que esta consulta se dirige.

## 2. Princípio declarado do produto

O CaixaClaro adota internamente uma regra — a **Regra do Orientador** —
que estabelece:

> O CaixaClaro pode apresentar dados, cálculos, cenários, comparações
> e limitações derivados das informações disponíveis; não deve apresentar
> como fato, recomendação profissional ou conclusão aquilo que depende
> de julgamento especializado ou de dados que não possui.

Operacionalmente:

- O sistema **não recomenda** preço, regime tributário, canal de venda
  ou investimento.
- O sistema **não conclui** que o negócio "dá lucro" ou "está saudável".
- O sistema **não atesta** custo, margem, ponto de equilíbrio ou
  conformidade fiscal.
- O sistema **não emite** DRE, demonstração, laudo ou parecer com
  aparência de peça contábil formal.
- O sistema **não assina**, certifica ou valida decisões do usuário.
- Todo cálculo é apresentado com as premissas informadas pelo usuário,
  a fórmula aplicada e as limitações correspondentes.
- O sistema **pode recusar-se a calcular** quando faltam dados, em vez
  de preencher lacunas com valores default.

As premissas utilizadas nos cálculos são informadas ou confirmadas pelo
usuário; dados externos, quando utilizados, são tratados como dados de
origem identificável e não como premissas inferidas pelo sistema.

## 3. Categorias funcionais previstas

Submetemos à apreciação do CRC-ES três categorias de funcionalidades.

### Categoria I — Cálculo puro sobre dado informado

O usuário informa preço atual, custo variável unitário estimado, volume
estimado e custos fixos mensais. O sistema calcula:

- Diferença entre preço e custo informado
- Margem de contribuição por unidade
- Ponto de equilíbrio em unidades e em receita
- Comparação entre dois cenários hipotéticos, lado a lado, sem
  indicar preferência

Características: todos os dados vêm do usuário; nenhuma classificação
automática de custo; nenhum rateio de custo indireto; a fórmula é
exibida com os valores substituídos; o resultado é rotulado como
CÁLCULO, não como conclusão.

### Categoria II — Consolidação de transações já classificadas

O usuário já classificou suas transações bancárias. O sistema apenas:

- Soma valores por categoria e por período
- Apresenta totais consolidados
- Mostra a origem de cada item

Características: não há nova classificação ou interpretação; o sistema
apenas agrega matematicamente transações cuja classificação já foi
realizada e confirmada pelo usuário.

### Categoria III — Indicadores dependentes de variáveis externas

Caso implementados no futuro:

- **Payback:** tempo de retorno de investimento informado, a partir de
  receita incremental e custos relacionados declarados pelo usuário
- **EVA:** valor econômico adicionado, dependente de capital investido,
  resultado operacional e custo de capital estimado

Características: dependem de premissas adicionais, que podem não estar
disponíveis ou suficientemente determinadas para o cálculo. O sistema
já prevê responder "não há dados suficientes" quando faltarem.
## 4. Perguntas objetivas

### Pergunta 1 — Enquadramento

Como o CRC-ES enquadra, à luz da legislação aplicável, essas
funcionalidades quando disponibilizadas por uma aplicação de
autosserviço? Em quais circunstâncias, se houver, esse tipo de
funcionalidade poderia caracterizar atividade privativa de profissional
da contabilidade?

### Pergunta 2 — Diferenciação entre categorias

Há diferença de enquadramento entre Categoria I, Categoria II e
Categoria III? Se sim, qual delas, isoladamente, poderia caracterizar
serviço privativo?

### Pergunta 3 — Forma de apresentação

A forma de apresentação do resultado altera o enquadramento?
Especificamente: se o resultado é rotulado como CÁLCULO com premissas
e limitações explícitas; se o sistema pode recusar-se a calcular; e
se não recomenda decisão — isso altera a natureza da atividade, ou o
enquadramento depende apenas do conteúdo funcional?

### Pergunta 4 — Orientação sobre limites

Caso alguma dessas funcionalidades esteja na fronteira, existe
orientação institucional do CFC/CRC-ES sobre como aplicações de
autosserviço podem disponibilizar cálculos gerenciais ao usuário sem
caracterizar prestação de serviço privativo?

### Pergunta 5 — Encaminhamento

Se a consulta extrapolar a esfera deste Conselho Regional, solicitamos
indicação do encaminhamento adequado (CFC, comissão específica, ou
orientação para consulta jurídica paralela).

## 5. O que esta consulta NÃO pergunta

Para evitar ambiguidade:

- Não solicitamos autorização para exercer atividade contábil.
- Não pedimos aval para o produto em si.
- Não pedimos posição sobre funcionalidades que emitem peças formais
  ou substituem profissional habilitado — isso está fora do escopo do
  produto por decisão interna.

## 6. Forma de resposta desejada

Solicitamos posicionamento por escrito, que possa ser anexado à
documentação técnica do produto como referência de diligência.

Caso o CRC-ES prefira responder parcialmente ou indicar necessidade
de complementação, qualquer retorno já será útil para orientar a
arquitetura.

## 7. Anexo

A Regra do Orientador, citada no item 2, está documentada em
docs/REGRA_ORIENTADOR.md no repositório do projeto. Cópia integral
pode ser encaminhada em anexo, se útil.