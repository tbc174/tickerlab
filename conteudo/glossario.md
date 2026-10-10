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

## DCA (aportes parcelados)
**O que é:** em inglês, *dollar-cost averaging*: em vez de investir tudo de uma vez, dividir o valor em parcelas e comprar aos poucos (por exemplo, uma por mês).

**Exemplo:** R$ 12.000 viram 12 compras de R$ 1.000. Se o preço cai no meio do caminho, as últimas parcelas compram mais barato; se só sobe, o dinheiro que esperou perdeu a alta.

**Cuidado:** em mercados que sobem na maior parte do tempo, o aporte único costuma vencer, porque fica mais tempo investido. O DCA vence mais em quedas e traz menos arrependimento, mas isso é conforto, não lucro garantido. O experimento mostra o resultado do ativo escolhido, não uma regra geral.

## Retorno da noite e do dia
**O que é:** o retorno de um dia se divide em duas partes: a **noite** (do fechamento de ontem até a abertura de hoje) e o **dia** (da abertura até o fechamento). Em alguns mercados, boa parte do ganho de longo prazo vem de uma só das partes.

**Exemplo:** se uma ação fecha a R$ 10 e abre a R$ 10,20, a noite rendeu +2%. Se depois fecha a R$ 10,10, o dia rendeu -1%.

**Cuidado:** estudos americanos não valem automaticamente para o Brasil. E comprar no fechamento e vender na abertura todo dia custa duas operações por dia, o que costuma consumir o ganho.

## Virada do mês
**O que é:** um efeito de calendário: em alguns mercados, os retornos costumam ser melhores nos últimos dias de um mês e nos primeiros do seguinte (quando entram salários, aportes e fluxos de fundos).

**Exemplo:** ficar comprado só do último pregão do mês até o 3º pregão do mês seguinte, cerca de 20% do tempo.

**Cuidado:** efeitos de calendário somem quando muita gente passa a explorá-los e podem ser coincidência. O app compara com posições sem relação com o preço (teste contra o acaso) para ajudar a separar um efeito real da sorte.

## Regime de mercado
**O que é:** um "clima" em que o mercado se encontra: calmo ou agitado (pela volatilidade recente) e de alta ou de baixa (pelo preço acima ou abaixo de uma média longa). Cada regime costuma ter retorno e risco bem diferentes.

**Exemplo:** o app chama de "agitado" o dia em que a volatilidade dos últimos 20 dias passa da mediana de tudo o que já aconteceu até ali.

**Cuidado:** o regime só é conhecido depois que acontece, e costuma mudar tarde: quando o app avisa que está agitado, parte do susto já passou. Por isso a tabela compara cada dia com o regime da véspera, que é o que dava para saber antes.

## Variância gerida
**O que é:** reduzir a posição quando a variância dos últimos dias está alta e deixá-la cheia quando está baixa. Vem de um estudo de Moreira e Muir (2017) que mostrou ganho de Sharpe em vários fatores.

**Exemplo:** se a variância de hoje é o dobro da típica, a posição cai para a metade.

**Cuidado:** o app nunca usa alavancagem (no máximo 100% do capital) e a variância "típica" é a mediana só do passado. O resultado depende do ativo e do período, e cada ajuste custa.

## Disjuntor de drawdown
**O que é:** uma regra que desliga a estratégia quando ela cai mais de X% desde o seu último topo e a deixa em caixa por N dias.

**Exemplo:** queda de 15% e pausa de 21 dias: ao cair 15% desde o topo, a estratégia fica parada por cerca de um mês.

**Cuidado:** proteger tem preço. O disjuntor evita parte de uma queda longa, mas também faz perder a recuperação que vem depois (o dia em que o mercado vira costuma ser o de maior alta). Por isso o app mostra o resultado com e sem disjuntor lado a lado.

## Barreira tripla
**O que é:** uma forma de dar a "resposta certa" a um modelo de aprendizado de máquina. A partir de um dia, acompanha-se o preço até ele tocar o **alvo** (ganho), o **stop** (perda) ou acabar o **prazo**; o que vier primeiro decide o rótulo (1 = bateu o alvo, 0 = não).

**Exemplo:** alvo de 3%, stop de 3% e prazo de 10 dias: se o preço sobe 3% no 4º dia sem antes cair 3%, o dia de partida recebe o rótulo 1.

**Cuidado:** o rótulo só fica conhecido depois de vários dias. Por isso o treino não pode usar exemplos cujo rótulo ainda não estava resolvido na data da previsão (veja *Expurgo e embargo*).

## Expurgo e embargo
**O que é:** cuidados para a validação cruzada não "vazar" o futuro. Em séries de preços, o rótulo de um dia depende dos dias seguintes, então um exemplo do treino pode compartilhar o mesmo futuro com um exemplo do teste. O **expurgo** tira do treino o que se sobrepõe ao teste; o **embargo** deixa uma folga de alguns dias logo depois do teste.

**Exemplo:** teste de 1º a 31 de março, rótulos de 10 dias: saem do treino os exemplos de meados de fevereiro (cujo rótulo olha março) e os primeiros dias de abril.

**Cuidado:** sem isso o modelo parece melhor do que é, e a diferença entre a validação com e sem expurgo mede o tamanho do vazamento.

## Meta-rotulagem
**O que é:** usar duas camadas. Uma regra simples (por exemplo, um cruzamento de médias) decide a **direção**; um modelo decide **se vale a pena agir** naquele sinal, a partir da chance de sucesso.

**Exemplo:** a regra manda comprar 100 vezes; o modelo aceita 40 em que acha o sucesso mais provável. Se a taxa de sucesso dessas 40 não for maior que a das 100, o modelo não ajudou.

**Cuidado:** o modelo precisa de muitos sinais para aprender; com poucos, qualquer diferença é ruído. Passe o resultado pelo teste contra o acaso.

## Pairs trading
**O que é:** uma estratégia com dois ativos parecidos (por exemplo, dois bancos). Quando a diferença entre eles foge do normal, compra-se o que ficou barato e vende-se o que ficou caro, apostando que a relação volta. O resultado não depende de o mercado subir ou cair.

**Exemplo:** se o Banco A costuma valer 0,8 vezes o Banco B e hoje vale 0,7, compra-se A e vende-se B até a proporção voltar.

**Cuidado:** a relação pode se desfazer para sempre (uma das empresas muda). A perna vendida exige aluguel de ações, com custo e disponibilidade limitada. E, ao testar muitos pares, alguns parecem ligados só por sorte: confirme a relação em um período que não foi usado para escolhê-la.

## Cointegração
**O que é:** dois preços são cointegrados quando, mesmo vagando cada um para um lado, uma combinação deles (o spread) volta sempre para a média. É a base estatística do pairs trading. O app usa o teste de Dickey-Fuller aumentado (ADF) no spread: quanto mais negativo, mais evidência de que ele volta.

**Exemplo:** ADF abaixo de −3,34 indica relação com cerca de 95% de confiança (valor aproximado de Engle-Granger para dois ativos).

**Cuidado:** correlação alta não é cointegração: dois ativos podem subir juntos e se afastar para sempre. A **meia-vida** diz em quantos dias o spread volta metade do caminho; muito longa, a estratégia fica lenta e cara.

## Paridade hierárquica de risco (HRP)
**O que é:** um jeito de dividir o dinheiro entre ativos pelo risco, sem prever retornos. Agrupa os ativos que andam juntos numa árvore e divide a carteira de cima para baixo, dando fatias menores aos grupos mais arriscados. Foi proposta por Marcos López de Prado como alternativa mais estável à otimização de Markowitz.

**Exemplo:** com três bancos e uma mineradora, os três bancos dividem uma fatia, em vez de ficarem com três quartos da carteira.

**Cuidado:** depende de como os ativos se moveram no passado, e essas relações mudam, em especial nas crises, quando tudo cai junto.

## Ômega
**O que é:** a soma de todos os ganhos diários dividida pela soma de todas as perdas diárias. Acima de 1, os ganhos pesam mais que as perdas.

**Exemplo:** ômega de 1,2 significa R$ 1,20 de ganho para cada R$ 1,00 de perda.

**Cuidado:** usa todos os dias, não só a média e o desvio como o Sharpe, então é menos enganado por quedas raras e grandes. Mas ainda é uma medida do passado.

## Critério de Kelly
**O que é:** a fração do capital que, em teoria, maximizaria o crescimento a longo prazo, dada a média e a variância dos retornos. O app mostra **meio Kelly**, que é o que se costuma discutir na prática.

**Exemplo:** meio Kelly de 40% sugere ter 40% do capital na estratégia e o resto em caixa.

**Cuidado:** é extremamente sensível ao erro de estimar a média: um erro pequeno muda muito o resultado. Acima de 100% pediria alavancagem. Use como curiosidade, nunca como instrução.

## Comprimento mínimo do histórico
**O que é:** quantos anos de dados seriam necessários para ter 95% de confiança de que o Sharpe verdadeiro é positivo, dado o Sharpe medido e o formato dos retornos (assimetria e curtose). Vem da mesma conta do Sharpe probabilístico (Bailey e López de Prado).

**Exemplo:** se a tela mostra 8 anos e você só tem 5 anos de dados, o resultado ainda não é confiável.

**Cuidado:** quanto mais combinações você testou antes de escolher a estratégia, mais anos são necessários; esta conta não desconta isso (veja o Sharpe deflacionado).

## Custo de operação
**O que é:** taxas e impostos pagos a cada compra ou venda. Reduzem o resultado real.

**Exemplo:** um custo de 0,1% por troca parece pouco, mas estratégias que operam muito perdem bastante.

**Cuidado:** backtests sem custo são otimistas demais.

## Correlação
**O que é:** mede se dois ativos andam juntos. Vai de -1 (opostos) a +1 (sempre juntos); perto de 0, não há relação.

**Exemplo:** duas petroleiras costumam ter correlação alta; ouro e bolsa, mais baixa.

**Cuidado:** correlação não é causa, e muda ao longo do tempo (em crises, quase tudo cai junto).

## Beta
**O que é:** quanto um ativo costuma se mexer para cada 1% que o índice se mexe. É a inclinação da reta que liga os retornos diários do ativo aos do índice.

**Exemplo:** beta de 1,5 significa que, em média, quando o Ibovespa sobe 1% o ativo sobe 1,5%, e quando cai 1% o ativo cai 1,5%. Beta abaixo de 1 amortece o índice; beta negativo anda ao contrário.

**Cuidado:** o beta muda com o tempo e com o período, e tem uma margem de erro (o app mostra o intervalo de 95%). Beta mede só a parte do risco que vem do índice, não o risco total do ativo.

## Alfa
**O que é:** o retorno anual que sobra depois de descontar o que o índice explica (o beta). Seria a parte do resultado que não veio de acompanhar o mercado.

**Exemplo:** alfa de +4% ao ano: o ativo rendeu 4% a mais do que o beta dele justificaria.

**Cuidado:** em poucos anos de dados, o alfa é muito incerto e pode ser só sorte. Não é prova de habilidade.

## R² (poder de explicação do índice)
**O que é:** a parte da variação diária do ativo que o índice explica, de 0% a 100%.

**Exemplo:** R² de 40% quer dizer que 40% das oscilações do ativo vieram do movimento do índice; o resto é próprio do ativo.

**Cuidado:** R² baixo torna o beta pouco útil para prever o ativo, mesmo que o número do beta pareça claro.

## Momentum
**O que é:** a tendência recente do preço. Quem subiu mais nos últimos meses tende, em média, a continuar à frente por um tempo. O app usa o **12-1**: o retorno de 12 meses sem contar o último mês, que costuma ter o efeito contrário.

**Exemplo:** se a ação subiu 30% de 12 meses atrás até 1 mês atrás, o momentum 12-1 é +30%.

**Cuidado:** é uma regularidade de médias, não uma garantia. Muda de um período para o outro e quase some em amostras curtas. Os momentos de virada são justamente os mais caros.

## Reversão à média
**O que é:** a ideia contrária ao momentum: o que se afastou muito da própria média recente tende a voltar a ela. O app mede o afastamento com o **z-score de 20 dias**, o número de desvios-padrão entre o preço e a média dos últimos 20 dias.

**Exemplo:** z-score de +2,5 significa que o preço está 2,5 desvios acima da média de 20 dias; z-score de −2,5, abaixo.

**Cuidado:** um preço esticado pode continuar esticando (é o que o momentum aposta). A reversão tende a valer em prazos curtos e o momentum em prazos longos, mas nenhuma das duas funciona sempre.

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
