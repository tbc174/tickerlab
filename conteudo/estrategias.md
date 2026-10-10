# Estratégias do TickerLab

Textos da aba **Backtest**, escritos para quem está começando. Cada estratégia tem: **A ideia**,
**A regra**, **Quando costuma funcionar**, **Quando costuma falhar** e **O que olhar nos resultados**.

> **Aviso:** o TickerLab é um projeto educacional. Um backtest mostra o que teria acontecido no
> passado; não prevê o futuro e não é recomendação de compra ou venda.

---

## Comprar e segurar
**A ideia:** comprar no começo e não fazer mais nada. É a "régua": toda estratégia só vale a pena se vencer isso, depois dos custos.

**A regra:** fica 100% comprado o tempo todo. Há uma única compra.

**Quando costuma funcionar:** em ativos que sobem no longo prazo, para quem aguenta as quedas sem vender.

**Quando costuma falhar:** quando o ativo cai muito e demora a se recuperar. A pessoa que vende no pior momento transforma a queda em prejuízo de verdade.

**O que olhar nos resultados:** a **maior queda** e o tempo "debaixo d'água". É o susto que quem comprou e segurou teve de aguentar.

## Cruzamento de médias
**A ideia:** a média móvel curta reage rápido aos preços; a longa reage devagar. Quando a curta passa por cima da longa, o preço está ganhando força, e a estratégia compra.

**A regra:** fica comprado enquanto a média curta está acima da média longa. Quando a curta cai abaixo da longa, vai para o caixa (dinheiro parado). A decisão é tomada no fim do dia e vale a partir do dia seguinte. A média pode ser **simples** (todos os dias pesam igual) ou **exponencial** (os dias recentes pesam mais, então ela reage mais rápido, com mais falsos sinais).

**Quando costuma funcionar:** em tendências longas e firmes, de alta ou de queda, em que ela evita parte da queda.

**Quando costuma falhar:** quando o preço anda de lado. As médias se cruzam várias vezes, a estratégia compra e vende sem ganhar nada e ainda paga os custos em cada operação. Ela também chega **atrasada**: só percebe a mudança depois que ela já aconteceu.

**O que olhar nos resultados:** o **número de operações** (cada uma custa), a **exposição** (quanto tempo ficou no mercado) e se o resultado supera comprar e segurar **depois dos custos**. Teste vários pares de médias: se só um par específico funciona, é sinal de *overfitting* (ajuste ao passado).

## Filtro de tendência
**A ideia:** só ficar comprado quando o mercado está em tendência de alta. A régua de "tendência de alta" é o preço estar acima da sua própria média móvel longa (a de 200 dias é a mais usada).

**A regra:** fica comprado enquanto o preço de fechamento está acima da média móvel de N dias; caso contrário, fica em caixa.

**Quando costuma funcionar:** em quedas longas e profundas, em que a estratégia sai cedo e evita boa parte do tombo.

**Quando costuma falhar:** em quedas rápidas seguidas de recuperação rápida (a estratégia sai tarde e volta tarde) e em mercados de lado, com muitos falsos sinais.

**O que olhar nos resultados:** compare a **maior queda** e a **volatilidade** com as de comprar e segurar: o objetivo dessa estratégia costuma ser **reduzir o susto**, mais do que aumentar o ganho.

## Filtro mensal de 10 meses
**A ideia:** olhar o mercado só uma vez por mês, e não todo dia. Quem decide menos vezes erra menos por "ruído" e paga menos custos. A versão clássica (de Meb Faber) compara o preço com a média dos últimos 10 meses.

**A regra:** no fim de cada mês, compara o fechamento do mês com a média simples dos fechamentos dos últimos N meses (padrão: 10). Se está acima, fica comprado durante o mês seguinte; se está abaixo, fica em caixa. A decisão de um mês só vale a partir do mês seguinte.

**Quando costuma funcionar:** em quedas longas, em que ela sai antes do fundo, e em mercados com tendências de vários meses.

**Quando costuma falhar:** em viradas rápidas, porque só olha uma vez por mês: pode sair tarde de uma queda curta e voltar tarde de uma recuperação.

**O que olhar nos resultados:** o **número de operações** (deve ser bem menor que o das outras estratégias) e a **maior queda** comparada com a de comprar e segurar.

## Rompimento de canal (Donchian)
**A ideia:** é a estratégia dos "Tartarugas", um grupo de operadores treinado nos anos 1980. Se o preço supera o maior valor dos últimos dias, uma nova tendência de alta pode estar começando.

**A regra:** compra quando o fechamento supera a **máxima** dos últimos N dias (padrão: 20). Vende quando o fechamento perde a **mínima** dos últimos M dias (padrão: 10, sempre menor que N). Entre um sinal e outro, mantém a posição.

**Quando costuma funcionar:** em tendências fortes e longas, que "vazam" para fora do canal e continuam.

**Quando costuma falhar:** em mercado lateral, em que o preço sai do canal, volta e gera vários falsos rompimentos. Cada falso rompimento custa dinheiro.

**O que olhar nos resultados:** a **taxa de acerto costuma ser baixa** (muitas pequenas perdas), e o ganho vem de poucas operações grandes. Veja o **payoff médio** (ganho médio dividido pela perda média): ele precisa ser alto para compensar.

## MACD
**A ideia:** mede a diferença entre uma média exponencial rápida e uma lenta. Quando a diferença aumenta, o preço está acelerando para cima; quando diminui, está perdendo força.

**A regra:** MACD = média exponencial de 12 dias menos a de 26. A linha de sinal é a média exponencial de 9 dias do próprio MACD. Fica comprado enquanto o MACD está acima da linha de sinal; senão, em caixa.

**Quando costuma funcionar:** em tendências suaves, em que o MACD cruza o sinal e acompanha o movimento por semanas.

**Quando costuma falhar:** em mercado de lado, com cruzamentos o tempo todo (muitas operações). Como toda média, chega atrasado.

**O que olhar nos resultados:** o **número de operações** e a **exposição**. O MACD costuma operar bastante, então os custos pesam.

## Momentum 12-1
**A ideia:** ativos que subiram nos últimos meses tendem a continuar subindo por um tempo. É um dos efeitos mais estudados em finanças.

**A regra:** calcula o retorno de cerca de 12 meses (252 dias), **pulando o último mês** (21 dias). Se o retorno é positivo, fica comprado; senão, em caixa. O mês pulado evita a "reversão de curtíssimo prazo", em que o que subiu muito na última semana costuma devolver parte.

**Quando costuma funcionar:** em mercados com tendência de meses, em que ela evita a maior parte das quedas longas.

**Quando costuma falhar:** em viradas bruscas de mercado (os chamados *crashes de momentum*) e em períodos agitados e sem direção.

**O que olhar nos resultados:** ela precisa de pelo menos 1 ano e meio de dados para começar; com períodos curtos, o app avisa que não houve operações. Compare a **maior queda** com a de comprar e segurar.

## Canal de Keltner
**A ideia:** uma faixa em volta da média exponencial, com largura dada pelo **ATR** (o tamanho médio dos movimentos diários). Um fechamento acima da faixa superior mostra força fora do normal.

**A regra:** compra quando o preço fecha acima da média exponencial somada a N vezes o ATR (padrão: média de 20 dias, ATR de 10 dias, N = 2). Vende quando o preço fecha de volta abaixo da média. Entre um sinal e outro, mantém a posição.

**Quando costuma funcionar:** em arrancadas de preço, em que o rompimento da faixa marca o começo de um movimento forte.

**Quando costuma falhar:** quando o rompimento é "falso" e o preço volta logo para dentro da faixa. Também fica muito tempo em caixa em mercados calmos.

**O que olhar nos resultados:** a **exposição** (costuma ser baixa, porque a regra é seletiva) e se o retorno por tempo investido compensa ficar tanto tempo parado. Teste outros valores do multiplicador: se só um funciona, é sinal de ajuste ao passado.

## RSI clássico
**A ideia:** o RSI (Índice de Força Relativa) mede, de 0 a 100, o quanto o preço subiu ou caiu nos últimos dias. Valor muito baixo significa "caiu demais, rápido demais" (sobrevendido); valor muito alto, o contrário. A aposta é que o exagero se corrige.

**A regra:** compra quando o RSI de 14 dias cai abaixo de 30 e vende quando sobe acima de 70. Entre um sinal e outro, mantém a posição.

**Quando costuma funcionar:** em mercados que oscilam dentro de uma faixa, em que as quedas fortes voltam a subir.

**Quando costuma falhar:** em tendências fortes. Numa queda longa o RSI fica baixo por muito tempo, a estratégia compra "a faca caindo" e a perda cresce. Em alta forte, vende cedo demais.

**O que olhar nos resultados:** a **maior queda** (compras em queda livre aparecem aí), a **taxa de acerto** (costuma ser alta, com ganhos pequenos) e o **payoff médio**: muitos acertos pequenos e poucas perdas grandes são a "assinatura" das estratégias de reversão.

## RSI curto com filtro de tendência
**A ideia:** variação do RSI com um período bem curto (2 dias), que reage a quedas rápidas, combinada com um filtro: só comprar a queda se o preço está **acima da média de 200 dias**. É "comprar o recuo dentro de uma tendência de alta".

**A regra:** compra quando o RSI de 2 dias cai abaixo de 10 **e** o preço está acima da média de 200 dias. Vende quando o RSI de 2 dias sobe acima de 70.

**Quando costuma funcionar:** em ativos em tendência de alta, em que recuos curtos são seguidos de retomada. O filtro evita comprar quedas em mercado de baixa.

**Quando costuma falhar:** quando a tendência de alta termina e o recuo vira queda longa. Como compra cedo e sai rápido, as operações têm ganhos pequenos e ela fica pouco tempo no mercado.

**O que olhar nos resultados:** a **exposição** (costuma ser baixa), a **taxa de acerto** e se o resultado compensa ficar tanto tempo em caixa. Precisa de pelo menos 200 dias de histórico para começar.

## Bandas de Bollinger
**A ideia:** uma faixa em volta da média móvel, com largura dada pela oscilação recente (desvio-padrão). Preço fora da faixa é um evento "raro", e a pergunta é: ele volta ou continua?

**A regra:** a média é de 20 dias e as bandas ficam 2 desvios-padrão acima e abaixo. No **modo reversão**, compra quando o preço fecha abaixo da banda inferior e vende quando volta à média. No **modo rompimento**, compra quando fecha acima da banda superior e vende quando perde a média.

**Quando costuma funcionar:** a reversão, em mercado lateral; o rompimento, em arrancadas de preço.

**Quando costuma falhar:** a reversão, em quedas que continuam; o rompimento, em falsos rompimentos. Atenção: os preços saem das bandas mais vezes do que a teoria prevê, porque os retornos têm "caudas pesadas" (movimentos extremos mais comuns do que numa curva normal).

**O que olhar nos resultados:** compare os dois modos: eles apostam em direções opostas. Veja o **número de operações** e a **exposição**. Curiosidade: o modo reversão com 2 desvios dá o mesmo resultado que a estratégia do **z-score** com os valores padrão (são a mesma regra escrita de duas formas).

## Z-score do preço
**A ideia:** o z-score diz a que distância, em desvios-padrão, o preço está da sua média recente. Zero é "na média"; -2 é "bem abaixo do normal".

**A regra:** compra quando o z-score cai abaixo de -2 e vende quando volta acima de 0 (padrões ajustáveis). A média e o desvio vêm dos últimos 20 dias.

**Quando costuma funcionar:** em ativos que oscilam em torno de um nível, como uma faixa de preço bem definida.

**Quando costuma falhar:** quando o preço muda de nível e não volta (uma notícia relevante, por exemplo): a "média" passa a ser outra e a estratégia segue comprando uma queda que não se reverte.

**O que olhar nos resultados:** com os valores padrão, o z-score é **exatamente a mesma estratégia** das Bandas de Bollinger no modo reversão (comprar abaixo da média menos 2 desvios é comprar com z-score abaixo de -2; vender acima da média é vender com z-score acima de 0), só escrita de outro jeito. Teste os dois e confira que os resultados coincidem. Mude os limites do z-score para ver o que a faixa fixa das bandas não deixa fazer. Veja se os ganhos vêm de muitas operações pequenas e quantas perdas grandes aparecem.

## Pesos iguais (referência)
**A ideia:** dividir o dinheiro em partes iguais entre todos os ativos e, todo mês, voltar às partes iguais. É a "régua" das carteiras: dá o trabalho mínimo e costuma ser difícil de bater.

**A regra:** cada ativo recebe 1/N do capital. Entre um mês e outro, quem sobe fica com mais peso; no fim do mês, vende-se um pouco de quem subiu e compra-se um pouco de quem ficou para trás.

**Quando costuma funcionar:** quando os ativos variam de forma diferente entre si e o rebalanceamento "compra na baixa e vende na alta" quase sem pensar.

**Quando costuma falhar:** quando todos caem juntos (a diversificação some em crises) ou quando um só ativo domina o período inteiro.

**O que olhar nos resultados:** compare qualquer outra estratégia de carteira com esta. Se não vence os pesos iguais depois dos custos, a complexidade não se pagou.

## Rotação por momentum
**A ideia:** os ativos que mais subiram nos últimos meses tendem a continuar na frente por um tempo. A carteira fica só com os melhores.

**A regra:** no fim de cada mês, calcula o retorno de cerca de 12 meses de cada ativo, pulando o último mês, e fica com os N melhores em partes iguais (padrão: 2).

**Quando costuma funcionar:** em mercados com líderes claros e tendências de vários meses.

**Quando costuma falhar:** nas viradas bruscas, em que os líderes de ontem viram os piores de hoje, e com poucos ativos, em que um ou dois dominam o resultado.

**O que olhar nos resultados:** a concentração (quantos ativos de fato aparecem no gráfico de composição), o giro e se ela supera os pesos iguais. Com poucos ativos e poucos anos, o resultado depende muito de quais ativos você escolheu.

## Momentum dual
**A ideia:** combina duas perguntas. A relativa: quem está melhor que os outros? A absoluta: está subindo de verdade, ou só caiu menos? Só entra quem passa nas duas.

**A regra:** igual à rotação por momentum, mas só ficam os ativos com retorno positivo. Se nenhum passa, a carteira inteira vai para o caixa.

**Quando costuma funcionar:** em quedas longas de mercado, porque a regra absoluta tira a carteira de tudo e ela espera no caixa (ou no CDI).

**Quando costuma falhar:** em mercados de lado, com entradas e saídas sem ganho, e depois de quedas rápidas seguidas de recuperação rápida.

**O que olhar nos resultados:** a **exposição média** (quanto tempo ficou em caixa) e a **maior queda**, comparadas com a rotação simples. O objetivo costuma ser reduzir o susto.

## Pesos pelo inverso da volatilidade
**A ideia:** em vez de dar o mesmo dinheiro a cada ativo, dar o mesmo "risco". Quem oscila mais recebe menos dinheiro; quem oscila menos recebe mais.

**A regra:** o peso de cada ativo é proporcional a 1 dividido pela sua volatilidade dos últimos 60 dias (padrão), e os pesos somam 100%. Rebalanceia no fim do mês.

**Quando costuma funcionar:** quando a volatilidade passada ajuda a prever a futura (o que costuma valer), reduzindo a influência dos ativos mais agitados.

**Quando costuma falhar:** quando um ativo calmo de repente fica agitado, e nos mercados em que os ativos mais arriscados foram os que mais renderam.

**O que olhar nos resultados:** a **volatilidade anual** e a **maior queda** em comparação com os pesos iguais. O ganho esperado é em risco, não necessariamente em retorno.

## Baixa volatilidade
**A ideia:** ações mais calmas tendem a render, ajustadas ao risco, tanto quanto ou mais que as agitadas. A carteira fica só com as mais calmas.

**A regra:** no fim do mês, fica com os N ativos de menor volatilidade dos últimos 60 dias (padrão: 2), em partes iguais.

**Quando costuma funcionar:** em quedas de mercado e em períodos agitados, em que os ativos calmos caem menos.

**Quando costuma falhar:** em altas fortes e rápidas, lideradas pelos ativos mais arriscados.

**O que olhar nos resultados:** a **maior queda** e o **Sharpe** em comparação com os pesos iguais. Com poucos ativos, o resultado depende muito de quais são os "calmos" da sua lista.

## Ativo-canário
**A ideia:** um ativo funciona como termômetro do mercado, como o canário na mina. Se ele fica fraco, o perigo está no ar e a carteira inteira vai para o caixa.

**A regra:** o primeiro ativo da lista é o canário. No fim do mês, se o retorno dele nos últimos 12 meses (pulando o último) é positivo, a carteira fica em partes iguais em todos os ativos; senão, fica toda em caixa.

**Quando costuma funcionar:** quando o canário antecipa as quedas dos outros ativos, em geral porque representa o mercado inteiro (como um índice).

**Quando costuma falhar:** quando o canário e os outros ativos andam em direções diferentes, e nas viradas rápidas.

**O que olhar nos resultados:** a **exposição média**, a **maior queda** e se o canário que você escolheu realmente "avisa" dos outros: teste com um índice e com uma ação.

## Paridade hierárquica de risco (HRP)
**A ideia:** dividir o risco de forma esperta entre os ativos, sem exigir previsões de retorno. Ativos que andam juntos formam um grupo e dividem uma mesma fatia; ativos diferentes recebem fatias separadas. Foi proposta por Marcos López de Prado como alternativa mais estável à otimização clássica de Markowitz.

**A regra:** no fim do mês, olha como os ativos se moveram nos últimos 252 dias (padrão), agrupa os mais parecidos numa árvore e divide a carteira de cima para baixo: em cada ramificação, o ramo menos arriscado recebe mais. Dentro de cada ramo, o peso é inversamente proporcional à variância. Nenhum peso fica negativo e os pesos somam 100%.

**Quando costuma funcionar:** quando há grupos claros de ativos parecidos (por exemplo, três bancos e uma mineradora): a HRP evita que o setor repetido domine a carteira, o que os pesos iguais não fazem.

**Quando costuma falhar:** com poucos ativos ou ativos muito diferentes, ela se parece com o inverso da volatilidade; e como qualquer regra baseada no passado, depende de as relações entre os ativos se manterem.

**O que olhar nos resultados:** a **maior queda** e o **Sharpe** contra os pesos iguais e o inverso da volatilidade, e o gráfico de pesos: a HRP deve dar fatias menores aos ativos que se repetem.
