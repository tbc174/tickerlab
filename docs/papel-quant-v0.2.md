# Papel da v0.2: como o gravador funciona

O papel está na seção 5 do [pré-registro v0.2](pre-registro-quant-p0-v0.2.md). Lá estão a regra, a lista das séries
e os critérios P1 a P3. Este texto explica como o código em `trader/papel/` cumpre essa regra.

Séries gravadas hoje (`trader/papel/series.py`):

- P0-3 (registro 5);
- P0-1 (registro 11);
- DI1 (registro 12);
- P0-1b (registro 18; reprovada na 1ª tentativa, mas a seção 5 grava a série mesmo assim).

A C-1, candidata e comparação, entra quando a 1ª tentativa dela estiver na `main`.

Nada vai para corretora e nada aqui é recomendação de investimento.

## O que cada linha grava

Cada série tem um arquivo próprio, `papel/<serie>.jsonl`. As linhas só são acrescentadas, e cada uma guarda o hash
da anterior, como no registro dos agentes (`trader/agentes/registro.py`). Mudar uma linha antiga quebra a cadeia.
`verificar` acusa a quebra, e o julgamento recusa uma série com a cadeia quebrada.

| Campo | O que é |
|---|---|
| `dia` | o dia em que o sinal vale: o pregão da B3, ou o dia corrido na cripto |
| `fechamento` | o último fechamento usado; é a véspera do `dia` (pregão anterior, ou dia corrido anterior na cripto) |
| `prazo` | até quando a linha pode ser gravada: 09h45 de Brasília do `dia` na B3 (antes do leilão de abertura), 0h do `dia` na cripto |
| `registrado_em` | a hora da gravação, com fuso; tem de vir antes do `prazo` |
| `sinal`, `carteira` | o alvo de cada ativo e a carteira simulada (patrimônio e exposição) depois do fechamento |
| `cdi_do_dia` | o CDI do pregão do fechamento, para o excesso |
| `dados` | o hash das tabelas usadas, a data em que começam e os insumos `estimados` (abaixo) |
| `tipo` | `gravacao` ou `falta` |

- **Gravar duas vezes o mesmo dia falha.** Gravar depois do prazo também falha, e gravar antes do fechamento da
  véspera é cedo demais.
- **Dia pulado vira falta** e nunca é preenchido depois. O gravador registra a falta na primeira rodada depois do
  prazo.
- **O início é fixado uma vez.** É o primeiro pregão depois do merge (`--iniciar`), e fica em `papel/inicio.json` com
  o commit. Todas as séries começam nesse dia.

## Leitura dos dados

O gravador usa só as fontes que as séries já usam:

- P0-3: Yahoo (BOVA11, ouro, S&P 500 e o dólar), curva do Tesouro do acervo, CDI e IPCA do Banco Central.
- P0-1: arquivos diários e mensais da Binance e PTAX do Banco Central.
- DI1: curva do Tesouro e CDI.
- P0-1b: arquivos diários e mensais da Binance para BTCBRL e ETHBRL (em reais, sem PTAX) e CDI.

Os dados baixados ficam em `papel/dados/`, fora do Git e separados das pastas da pesquisa.

- **Preço do fechamento nunca é estimado.** Se a fonte ainda não publicou o fechamento da véspera, o gravador espera a
  próxima rodada. Se não sai até o prazo, o dia vira falta.
- **Insumo que só sai depois repete o último valor publicado,** e o nome dele vai em `dados.estimados`:
  - o CDI do dia;
  - a curva do Tesouro, que chega no acervo no dia seguinte;
  - o IPCA do mês, que só sai no mês seguinte. A NTN-B espalha esse IPCA pelos pregões do mês inteiro e não o
    antecipa.

  A linha gravada não muda quando o valor de verdade chega. Isso é a regra "corrige-se dali para a frente".
- **Aquecimento.** Os indicadores pedem histórico: 252 pregões na P0-3, 365 dias na P0-1 e 360 pregões no DI1. Por
  isso o gravador lê os preços desde 730 dias antes do primeiro fechamento. Até o primeiro fechamento, a carteira
  simulada fica 100% em caixa (`_sem_posicao_ate`). Nenhum retorno daquele período entra no papel nem no julgamento:
  o histórico serve só para o primeiro sinal existir. Esse trecho cai dentro do período do holdout (10/10/2023 a
  09/10/2026), mas o gravador não calcula ali nenhum resultado das estratégias.
- **Cortar o futuro não muda o passado.** Há um teste por série: a foto de um dia é a mesma com ou sem os dados dos
  dias seguintes.

## O julgamento (P1 a P3)

O julgamento sai só das linhas gravadas (`trader/papel/julgamento.py`). Vale 12 meses corridos depois do início.
Antes disso, `--julgar` mostra o resultado até hoje com `completo: false`.

| # | Conta no código | Passa quando |
|---|---|---|
| P1 | Sharpe anualizado do excesso sobre o CDI, só com os retornos de um dia gravado para o dia gravado seguinte | > 0 e ≥ 50% do de referência |
| P2 | queda máxima da curva dos patrimônios gravados, incluindo a queda que atravessa uma falta | ≥ 1,5 × a do desenvolvimento (as duas são negativas) |
| P3 | cada gravação antes do prazo, cadeia íntegra e faltas ≤ 5 | as três coisas juntas |

- O P1 usa o mesmo Sharpe da ficha de cada série (252 pregões na B3, 365 dias na cripto).
- O retorno que atravessa uma falta fica fora do Sharpe, porque junta mais de um dia.
- Para o P3, o dia esperado que nem virou falta (o gravador parou de rodar) conta como falta.

As renovações (mais 12 meses para quem passa, no máximo duas) ainda não estão no código. Elas entram antes do primeiro
julgamento, em novembro de 2027.

## Como roda

```powershell
.venv\Scripts\python -m trader.papel.gravar --iniciar 2026-11-05 --commit <sha>   # uma vez, depois do merge
.venv\Scripts\python -m trader.papel.gravar                                       # a rodada agendada
.venv\Scripts\python -m trader.papel.gravar --verificar                           # confere as cadeias
.venv\Scripts\python -m trader.papel.gravar --julgar                              # P1 a P3 até hoje
```

Cada rodada confere o pré-registro (`criterio_quant.conferir`) antes de gravar. Rodar de novo é seguro: o que já
foi gravado não se grava de novo. Duas rodadas ao mesmo tempo não escrevem juntas, por causa da trava `.gravando`.
Uma trava com mais de uma hora é de uma rodada que morreu, e a rodada nova a ignora.

A rodada é agendada no Agendador de Tarefas do PC:

- B3: às 19h30, às 7h e às 9h;
- cripto: a cada 15 minutos, das 22h30 às 23h55.

## Riscos conhecidos

- **O PC desligado vira falta.** O limite é 5 faltas em 12 meses. Rodar no servidor de casa daria mais folga, mas
  isso depende de uma decisão do Tiago.
- **A janela da cripto é curta.** A Binance publica o arquivo diário entre ~22h30 e ~23h45 de Brasília, e o prazo é
  0h.
- **Barras do Yahoo.** A barra do dia aparece antes do fechamento. Por isso o dia da B3 só abre às 18h. O dólar
  (`BRL=X`) é negociado o dia inteiro, então a barra lida às 19h30 ainda pode mudar um pouco depois.
- **Revisão de dado.** Quando o IPCA ou a curva de verdade chegam, a carteira dá um salto pequeno no dia seguinte.
  Isso é esperado e não reescreve nada.
