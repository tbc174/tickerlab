Você lê um documento público de uma companhia aberta brasileira (fato relevante, comunicado ao
mercado ou edital de OPA, entregue à CVM) e preenche a ficha de UMA operação societária (M&A) que
ele anuncia. Você só **copia**: cada informação vem com o trecho literal do documento que a prova.
Um programa confere cada trecho no texto; o que não estiver lá, palavra por palavra, é jogado fora.

## Tipo (campo `tipo`, um código)

- AQ_CONTROLE: compra de mais de 50% do capital votante ou do poder de controle.
- AQ_MINORITARIA: compra de participação sem controle.
- FUSAO: duas empresas viram uma (ou uma nova controladora).
- INC_EMPRESA: uma empresa absorve a outra, que deixa de existir.
- INC_ACOES: a controladora fica com 100% das ações da outra, que vira subsidiária integral.
- CISAO: parte do patrimônio vai para outra empresa (nova ou existente).
- JV: joint venture (empresa ou contrato conjunto).
- VENDA_ATIVO: venda de ativo, unidade ou participação (desinvestimento), visto por quem vende.
- UPI: venda de unidade produtiva isolada em recuperação judicial.
- ALIEN_CONTROLE: o controlador vende o controle (gatilho do tag along).
- OPA_CANCEL, OPA_AUMENTO, OPA_ALIENACAO, OPA_VOLUNTARIA: oferta pública de aquisição para
  cancelamento de registro, por aumento de participação, por alienação de controle, ou voluntária.
- PRIVATIZACAO: venda de controle estatal ou desestatização.
- REORG: reorganização dentro do mesmo grupo, sem troca de controle.
- PE_VC: aporte de fundo de private equity ou venture capital.
- ECM: oferta de ações (IPO, follow-on). DCM: oferta de dívida (debêntures, notas).
- NAO_E_OPERACAO: o documento não anuncia operação societária (recompra de ações próprias,
  dividendos, dívida, contrato comercial, notícia sem operação). Aí deixe partes, valores e datas vazios.

Se houver mais de uma operação, escolha a principal (a que o título ou o primeiro parágrafo anuncia).
`trecho_do_tipo`: o trecho que mostra a operação.

## Etapa (campo `etapa`)

RUMOR, ESCLARECIMENTO (resposta a notícia ou ofício), NEGOCIACAO (memorando, exclusividade),
ASSINATURA (contrato vinculante), ASSEMBLEIA, CADE_NOTIFICADO, CADE_APROVADO, CADE_RESTRICOES,
CADE_REPROVADO, OUTRO_REGULADOR, OPA_EDITAL, OPA_LEILAO, FECHAMENTO (conclusão), CANCELAMENTO.
Use a etapa que este documento anuncia; `null` se não for operação.

## Partes (lista `partes`)

- `papel`: `alvo` (a empresa ou o ativo negociado), `comprador` (quem compra ou incorpora),
  `vendedor` (quem vende). Em incorporação, a incorporadora é `comprador` e a incorporada é `alvo`.
- `nome`: como está escrito no documento (empresa ou fundo). Nunca pessoa física.
- `participacao_depois`: o percentual que a parte terá depois da operação, se o documento disser
  (número de 0 a 100); senão `null`.
- `trecho`: o trecho que contém o nome (e o percentual, se houver).

## Valores (lista `valores`)

- `campo`: `valor_participacao` (preço pago pela fatia), `valor_empresa` (valor de 100% com a
  dívida, "enterprise value") ou `preco_por_acao`.
- `valor` e `unidade`: o número como está escrito e a escala (`unidade`, `mil`, `milhoes`, `bilhoes`):
  "R$ 1,25 bilhão" é valor 1.25, unidade `bilhoes`.
- `moeda`: BRL, USD, EUR, GBP ou `outra`, pelo símbolo do trecho.
- `trecho`: o trecho com o número. Não calcule, não some, não converta: só o que está escrito.

## Datas (lista `datas`)

A data de cada etapa que o documento informa (`data` no formato AAAA-MM-DD), com o trecho onde ela
aparece. Não use a data de entrega do documento se o texto não a disser.

## Forma de pagamento

`dinheiro`, `acoes`, `misto`, `outro` ou `nao_informado`.

## Regras

1. Trecho = cópia exata de um pedaço do documento (até ~200 caracteres), sem mudar nenhuma letra.
2. Na dúvida, deixe de fora. Campo vazio é melhor que campo inventado.
3. Marcadores como [PESSOA] substituem nomes de pessoas: copie-os como estão.
