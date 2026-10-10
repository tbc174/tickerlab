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
