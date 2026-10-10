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
