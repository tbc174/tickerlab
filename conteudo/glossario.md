# Glossário do TickerLab

Textos da aba **Glossário**, escritos para quem está começando na bolsa.
Cada verbete tem: o que é, um exemplo e um cuidado. Formato pensado para virar
dados no app (um `##` por termo).

> **Aviso:** o TickerLab é um projeto educacional. Nada aqui é recomendação de
> compra ou venda. Rentabilidade passada não garante resultado futuro.

---

## Ticker
**O que é:** o código que identifica um ativo na bolsa. Funciona como um apelido.

**Exemplo:** `PETR4.SA` é a Petrobras na bolsa brasileira (B3); `AAPL` é a Apple na bolsa americana.

**Cuidado:** no Yahoo Finance, ações da B3 levam `.SA` no final. Sem ele, o app pode não achar a ação.

## Preço de fechamento
**O que é:** o último preço negociado no dia. É o valor usado nos cálculos do app.

**Exemplo:** se a ação fechou a R$ 38,50 hoje, esse é o valor do dia.

**Cuidado:** o app usa preços *ajustados* por dividendos e desdobramentos, para que o histórico seja comparável ao longo do tempo.

## Retorno
**O que é:** quanto o preço variou em relação ao dia anterior (ou ao início do período), em porcentagem.

**Exemplo:** de R$ 10 para R$ 11, o retorno é de +10%.

**Cuidado:** perder 50% e depois ganhar 50% **não** zera. De 100 vai a 50, e depois a 75.

## Retorno acumulado
**O que é:** quanto o investimento rendeu do início ao fim do período escolhido.

**Exemplo:** R$ 1.000 que viraram R$ 1.300 deram retorno acumulado de +30%.

**Cuidado:** compare sempre períodos iguais. +30% em 5 anos é bem diferente de +30% em 1 ano.

## Volatilidade
**O que é:** o quanto o preço oscila. Quanto maior, mais "montanha-russa". Aqui é calculada como o desvio padrão dos retornos diários, anualizado.

**Exemplo:** uma ação com volatilidade de 40% ao ano sobe e desce muito mais que uma de 15%.

**Cuidado:** volatilidade não é perda. Ela mede a incerteza, para os dois lados.

## Drawdown
**O que é:** a queda desde o ponto mais alto já atingido até o ponto mais baixo seguinte. O *drawdown máximo* é a pior queda do período.

**Exemplo:** se a ação chegou a R$ 50 e caiu para R$ 30, o drawdown foi de -40%.

**Cuidado:** mostra o pior susto que quem comprou no topo teria passado. É útil para saber se você aguentaria segurar a ação.

## Volatilidade móvel
**O que é:** a volatilidade calculada só com os últimos N dias (a "janela"), recalculada a cada dia. Mostra como o nível de oscilação muda ao longo do tempo.

**Exemplo:** uma linha que sobe de 20% para 50% em março de 2020 mostra que o mercado ficou muito mais agitado naquele mês.

**Cuidado:** janelas curtas (20 dias) reagem rápido, mas são "nervosas"; janelas longas (120 dias) são suaves, mas demoram a perceber mudanças.

## Recuperação de um drawdown
**O que é:** o dia em que o preço volta ao nível do topo anterior, encerrando a queda. Entre o topo e a recuperação, quem comprou no topo estava no prejuízo.

**Exemplo:** topo em janeiro, fundo em abril e recuperação em setembro: foram quase 8 meses até empatar.

**Cuidado:** algumas quedas nunca são recuperadas dentro do período analisado. O app avisa quando isso acontece.

## Melhor e pior dia
**O que é:** o maior ganho e a maior perda em um único dia no período.

**Exemplo:** "pior dia: -12% em 16/03/2020".

**Cuidado:** um ou dois dias extremos podem pesar muito no resultado total.

## Índice de Sharpe
**O que é:** mede quanto de retorno você recebeu para cada unidade de risco (volatilidade). Quanto maior, melhor a relação retorno/risco.

**Exemplo:** duas ações rendem 20% ao ano, mas a de menor volatilidade tem Sharpe maior.

**Cuidado:** depende do período e de uma taxa livre de risco; valores muito altos em períodos curtos costumam ser sorte.

## Retorno anualizado
**O que é:** o retorno do período convertido para a escala de um ano, como se o ritmo se mantivesse. Permite comparar períodos de tamanhos diferentes, como 6 meses e 5 anos.

**Exemplo:** +10% em 6 meses equivale a cerca de +21% ao ano (os ganhos se acumulam, o que se chama juros compostos).

**Cuidado:** é uma projeção matemática, não uma previsão. Em períodos curtos, o número fica exagerado.

## Dias de alta
**O que é:** a porcentagem dos dias em que o preço fechou acima do dia anterior.

**Exemplo:** 55% de dias de alta quer dizer que, em cada 100 dias, 55 fecharam em alta e 45 em queda ou parados.

**Cuidado:** acertar muitos dias não basta. Uma ação pode subir na maioria dos dias e ainda assim perder dinheiro se as quedas forem grandes.

## Perda de um dia ruim (VaR)
**O que é:** uma medida de risco que responde: "em um dia ruim, qual perda eu devo esperar?". Aqui, olhamos o pior dia em cada 20 (nível de 95%) na história do período.

**Exemplo:** VaR de -2,6% quer dizer que, em 95% dos dias, a perda não passou de 2,6%. Nos outros 5%, passou.

**Cuidado:** é calculado com o passado e não diz o tamanho da perda nos dias realmente extremos.

## Gráfico de velas (candlestick)
**O que é:** um jeito de mostrar o preço de cada dia com quatro informações de uma vez: abertura, fechamento, máxima e mínima. O "corpo" da vela vai da abertura ao fechamento; os "pavios" mostram a máxima e a mínima do dia. Verde indica que o preço fechou acima da abertura; vermelho, abaixo.

**Exemplo:** uma vela verde com pavio longo para cima mostra que o preço subiu bastante durante o dia, mas recuou antes do fechamento.

**Cuidado:** a linha mostra só o fechamento e é mais limpa para ver a tendência; as velas mostram mais detalhe e ajudam a ver a oscilação dentro de cada dia.

## Retorno mensal
**O que é:** quanto o preço subiu ou caiu em cada mês do calendário, juntando os retornos de todos os dias do mês. O app mostra uma grade com um ano por linha e um mês por coluna: verde é alta e vermelho é queda.

**Exemplo:** +10% em janeiro e -1% em fevereiro dão +8,9% no acumulado dos dois meses, porque os ganhos se acumulam (juros compostos) em vez de simplesmente se somarem.

**Cuidado:** o primeiro e o último mês do período podem estar incompletos, então não são comparáveis com os meses inteiros.

## Sazonalidade
**O que é:** a ideia de que certos meses costumam ser melhores ou piores que outros, ano após ano. A última linha da grade mostra a média de cada mês ao longo dos anos.

**Exemplo:** se janeiro teve média de +4% nos últimos cinco anos, dizemos que janeiro foi historicamente bom para aquela ação.

**Cuidado:** com poucos anos de dados, a média é só coincidência. Um padrão do passado não garante que se repita.

## Base 100
**O que é:** um jeito de comparar ativos de preços e moedas diferentes. Todos começam valendo 100 no primeiro dia em comum, e a linha mostra quanto aquele "100" virou depois.

**Exemplo:** se a linha da Petrobras termina em 150 e a do Ibovespa em 120, quem comprou a Petrobras no começo ganhou +50% e quem comprou o índice ganhou +20%.

**Cuidado:** só entram os dias em que todos os ativos negociaram. Feriados diferentes (B3 e bolsas dos EUA) fazem alguns dias serem descartados, e o app avisa quantos. Os preços não são preenchidos nem estimados.

## Stop-loss
**O que é:** uma ordem de segurança que tira você da posição se o preço cair uma certa porcentagem abaixo do preço de compra. Limita a perda de cada operação.

**Exemplo:** compra a R$ 100 com stop-loss de 8%: se o preço fechar em R$ 92 ou menos, a posição é encerrada.

**Cuidado:** um stop curto demais é acionado por oscilações normais e você sai no "susto", antes de o preço se recuperar. Aqui o stop é conferido no fechamento do dia.

## Take-profit
**O que é:** o contrário do stop-loss: encerra a posição quando o ganho chega a uma porcentagem definida, para "garantir o lucro".

**Exemplo:** compra a R$ 100 com take-profit de 15%: ao fechar em R$ 115 ou mais, vende.

**Cuidado:** limita os ganhos. Nas grandes altas, quem usa take-profit sai cedo e perde o resto do movimento.

## Stop móvel
**O que é:** um stop que **sobe junto com o preço**. Em vez de olhar o preço de compra, olha o maior preço atingido depois da compra.

**Exemplo:** stop móvel de 10%: se o preço sobe de R$ 100 para R$ 120, o limite vira R$ 108. Se cair até lá, a posição é encerrada, com o lucro parcialmente protegido.

**Cuidado:** em mercados que sobem e descem muito, ele sai cedo e nunca deixa o ganho "respirar".

## Stop por ATR
**O que é:** um stop cuja distância depende da **volatilidade** do ativo. O ATR (*Average True Range*) é o tamanho médio do movimento diário. Em ativos agitados o stop fica mais longe; em ativos calmos, mais perto.

**Exemplo:** com ATR de R$ 1,00 e multiplicador 2, o stop fica R$ 2,00 abaixo do preço de compra. É a regra usada pelas "Tartarugas", um grupo famoso de operadores.

**Cuidado:** o ATR usado é o do dia da compra e não muda depois.

## Risco por operação
**O que é:** em vez de comprar sempre com todo o capital, o tamanho da posição é calculado para que, se o stop for atingido, você perca só uma pequena fração do capital (como 1%). Funciona junto com o stop por ATR.

**Exemplo:** capital de R$ 10.000, risco de 1% (R$ 100) e stop 4% abaixo do preço: a posição é de R$ 2.500 (25% do capital), pois uma queda de 4% sobre R$ 2.500 custa R$ 100.

**Cuidado:** ativos muito voláteis geram posições pequenas, e o restante do capital fica parado em caixa, sem render.

## Alvo de volatilidade
**O que é:** ajusta o tamanho da posição para que a volatilidade da carteira fique perto de um valor escolhido. Quando o mercado fica agitado, a posição diminui; quando fica calmo, volta ao máximo.

**Exemplo:** alvo de 15% ao ano. Se a volatilidade recente do ativo é de 30%, o app fica com metade da posição (e metade em caixa).

**Cuidado:** o app nunca usa dinheiro emprestado (a posição máxima é 100%). A volatilidade é medida no passado e pode mudar de repente.

## Média móvel
**O que é:** a média dos últimos N preços, recalculada a cada dia. Suaviza o gráfico e mostra a tendência.

**Exemplo:** a média móvel de 20 dias é a média dos últimos 20 fechamentos.

**Cuidado:** ela sempre "chega atrasada": só confirma a tendência depois que ela já começou.

## Cruzamento de médias
**O que é:** estratégia que compra quando uma média curta (ex.: 20 dias) cruza para cima de uma longa (ex.: 50 dias), e vende quando cruza para baixo.

**Exemplo:** média de 20 dias passa acima da de 50: sinal de compra.

**Cuidado:** em mercado lateral gera muitos sinais falsos, e cada operação tem custo.

## Backtest
**O que é:** simular uma estratégia com dados do passado para ver como ela teria se saído.

**Exemplo:** "e se eu tivesse comprado sempre que as médias cruzassem, nos últimos 5 anos?"

**Cuidado:** um bom resultado no passado não garante nada no futuro. Veja os dois verbetes seguintes.

## Comprar e segurar (buy and hold)
**O que é:** comprar o ativo no início e manter até o fim, sem fazer nada. É a referência: uma estratégia só vale a pena se superar isso.

**Exemplo:** comprar PETR4 em jan/2022 e só olhar em dez/2025.

**Cuidado:** simples não significa sem risco; o drawdown continua existindo.

## Look-ahead bias
**O que é:** erro de backtest em que a simulação "usa o futuro" sem querer, por exemplo decidir com o preço de fechamento de hoje e comprar a esse mesmo preço.

**Exemplo:** o sinal só pode valer a partir do dia seguinte (por isso se usa `shift(1)` no código).

**Cuidado:** esse erro faz qualquer estratégia parecer genial. Se o resultado parece bom demais, desconfie.

## Overfitting (sobreajuste)
**O que é:** ajustar tanto a estratégia ao passado que ela só funciona nele. Ela "decorou" os dados em vez de aprender algo útil.

**Exemplo:** testar 500 combinações de médias e ficar com a que deu mais lucro.

**Cuidado:** teste em um período diferente do usado para escolher os parâmetros.

## Treino e teste
**O que é:** dividir o histórico em duas partes. No **treino** você escolhe os parâmetros da estratégia; no **teste**, um período que ela nunca viu, você confere se a escolha se sustenta. Resultado "fora da amostra" é o do teste.

**Exemplo:** escolher a melhor média móvel nos primeiros 3,5 anos de 5 e medir só nos 1,5 ano seguintes. Se o Sharpe cai muito, o ajuste foi sorte.

**Cuidado:** o teste só vale uma vez. Se você olhar o teste, mudar a estratégia e olhar de novo, o teste virou treino.

## Walk-forward
**O que é:** um treino/teste repetido ao longo do tempo. Escolhe os parâmetros numa janela, opera a janela seguinte, anda para frente e repete. Só os resultados dos períodos de teste são emendados.

**Exemplo:** treinar em 2 anos, operar 6 meses, avançar 6 meses e repetir. É o mais próximo de como a estratégia seria usada de verdade.

**Cuidado:** a **eficiência** (Sharpe de fora dividido pelo Sharpe de treino) perto de 1 é bom sinal; perto de 0 ou negativa, o ajuste não se sustentou. Com poucos anos de dados há poucas janelas.

## Mapa de parâmetros
**O que é:** uma grade colorida com o Sharpe de cada combinação de valores de uma estratégia. Mostra se o bom resultado vem de uma região larga e suave (robusto) ou de um ponto isolado (provavelmente sorte).

**Exemplo:** se a média de 50 dias vai bem mas 45 e 55 vão mal, o 50 foi coincidência.

**Cuidado:** escolher o ponto mais verde do mapa é o *overfitting* de novo. Use o mapa para ver a **vizinhança**, não para caçar o recorde.

## Monte Carlo (das operações)
**O que é:** sorteia, milhares de vezes, as operações da estratégia (com reposição) e refaz a curva de capital. Mostra o intervalo de resultados que teriam sido possíveis se os ganhos e as perdas tivessem vindo em outra ordem.

**Exemplo:** com 30 operações, o app mostra que em 90% das simulações o retorno ficou entre -5% e +60%. O resultado real é só um desses caminhos.

**Cuidado:** só reordena o que já aconteceu. Não cria cenários novos, e pouquíssimas operações dão um cone sem sentido (o app pede pelo menos 5).

## Teste contra o acaso
**O que é:** compara a estratégia com versões que têm a mesma exposição e o mesmo número de operações, mas com a posição deslocada no tempo, sem relação com o preço do dia. O *p-valor* é a fatia das versões ao acaso que fez igual ou melhor.

**Exemplo:** p-valor de 0,02 quer dizer que só 2% das versões ao acaso bateram a estratégia. Já 0,40 quer dizer que 40% fizeram igual: o resultado pode ser só sorte.

**Cuidado:** num ativo que sobe o tempo todo, qualquer posição comprada ganha, e o teste mostra isso: a estratégia não se destaca do acaso. E um p-valor baixo não prova que o resultado vai se repetir.

## Sharpe deflacionado
**O que é:** o Sharpe do melhor candidato, descontado pelo número de combinações testadas. Quanto mais combinações você experimenta, maior é o Sharpe do vencedor só por sorte. O resultado é uma probabilidade: acima de 95%, é difícil explicar o Sharpe apenas pela sorte.

**Exemplo:** o melhor de 49 combinações tem Sharpe 1,1, mas a sorte sozinha já explicaria cerca de 0,9. A probabilidade fica baixa, e o 1,1 não convence.

**Cuidado:** o app só conhece as combinações da grade. Se você testou outras antes (em outros ativos, em outras estratégias), some-as em "outras tentativas".

## PBO (probabilidade de overfitting)
**O que é:** o histórico é cortado em blocos e o app testa muitas divisões treino/teste. Em cada uma, pega a melhor combinação do treino e vê onde ela cai no teste. PBO é a fatia das vezes em que ela caiu abaixo da mediana.

**Exemplo:** PBO de 10% é bom sinal: a melhor do treino quase sempre continua boa. Perto de 50%, escolher a melhor do treino equivale a tirar no sorteio.

**Cuidado:** combinações de uma mesma estratégia são parecidas entre si, então o PBO costuma ficar baixo mesmo quando a estratégia toda não vale nada. Ele mede a escolha entre variações, não a estratégia.

## Data snooping (ir pescando resultados)
**O que é:** testar muitas estratégias, ativos ou parâmetros e destacar só a que foi melhor. Quanto mais se testa, mais certo é que alguma pareça boa só por sorte.

**Exemplo:** com 12 estratégias no mesmo ativo, a melhor do ranking quase sempre tem um Sharpe bom, mesmo que nenhuma tenha valor. Por isso o app mostra também a "chance de não ser sorte", que desconta o número de estratégias testadas.

**Cuidado:** a conta vale para tudo o que você testou, inclusive fora do app. Se já testou outras ideias, some-as nas "tentativas extras".

## CDI
**O que é:** a taxa dos empréstimos entre bancos, que acompanha de perto a Selic. É a "régua" do investimento sem risco no Brasil: a renda fixa e a poupança dos fundos são comparadas a ela. O app busca o CDI de cada dia no Banco Central.

**Exemplo:** se a estratégia rendeu 12% no ano e o CDI rendeu 14%, ela não valeu o risco: era melhor ter deixado o dinheiro parado no CDI.

**Cuidado:** o CDI é em reais. Para ações de fora (como a AAPL), a comparação mistura moedas. O Sharpe usa o CDI do período como taxa livre de risco.

## Imposto de renda (simplificado)
**O que é:** uma estimativa do imposto sobre as operações do backtest, com as regras de ações na B3 em operações normais (*swing trade*): 15% sobre o lucro do mês, isento se o total vendido no mês é de até R$ 20 mil, e o prejuízo de um mês abate o lucro dos seguintes.

**Exemplo:** comprar e segurar só paga imposto quando vende, então o dinheiro continua rendendo sem o desconto. Estratégias que compram e vendem muito pagam a cada ciclo.

**Cuidado:** é uma simplificação para estudo. Não considera *day trade*, retenção na fonte, dividendos nem ativos de fora, e **não é orientação tributária**. Confira as regras atuais na Receita Federal e na B3.

## Rebalanceamento
**O que é:** voltar a carteira aos pesos desejados. Entre um rebalanceamento e outro, quem sobe passa a pesar mais (a *deriva* dos pesos). Rebalancear é vender um pouco do que subiu e comprar um pouco do que ficou para trás.

**Exemplo:** carteira 50% A e 50% B. Se A dobra e B fica parado, A passa a pesar 67%. No rebalanceamento, vende-se parte de A e compra-se B para voltar a 50% e 50%.

**Cuidado:** cada rebalanceamento tem custo. Rebalancear com muita frequência pode comer o ganho que ele busca.

## Custo de operação
**O que é:** taxas e impostos pagos a cada compra ou venda. Reduzem o resultado real.

**Exemplo:** um custo de 0,1% por troca parece pouco, mas estratégias que operam muito perdem bastante.

**Cuidado:** backtests sem custo são otimistas demais.

## Correlação
**O que é:** mede se dois ativos andam juntos. Vai de -1 (opostos) a +1 (sempre juntos); perto de 0, não há relação.

**Exemplo:** duas petroleiras costumam ter correlação alta; ouro e bolsa, mais baixa.

**Cuidado:** correlação não é causa, e muda ao longo do tempo (em crises, quase tudo cai junto).

## Diversificação
**O que é:** dividir o dinheiro entre ativos que não andam juntos, para que a queda de um seja amortecida por outro.

**Exemplo:** carteira com ações brasileiras, americanas e Bitcoin.

**Cuidado:** ativos muito correlacionados não diversificam de verdade.

## Ibovespa (`^BVSP`)
**O que é:** principal índice da bolsa brasileira, uma "média" das ações mais negociadas. Serve de termômetro do mercado.

**Cuidado:** se uma ação rendeu 15% e o Ibovespa 25%, ela ficou **abaixo** do mercado.

## S&P 500 (`^GSPC`)
**O que é:** índice das 500 maiores empresas dos EUA. Referência do mercado americano.

**Cuidado:** está em dólares; compare com ativos brasileiros considerando a moeda.

## Câmbio e moeda
**O que é:** ações da B3 são em reais (R$); as americanas e o Bitcoin (`BTC-USD`), em dólares (US$).

**Cuidado:** comparar o *retorno percentual* é mais justo que comparar preços. Mesmo assim, a variação do dólar afeta quem investe de fora do país.

## Feriados e dias sem negociação
**O que é:** a B3 e as bolsas dos EUA fecham em dias diferentes. O Bitcoin negocia todos os dias.

**Cuidado:** ao comparar ativos, o app só usa os dias em que ambos têm preço.
