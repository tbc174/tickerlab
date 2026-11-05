"""O papel da v0.2 (seção 5 do `docs/pre-registro-quant-p0-v0.2.md`): gravar, todo dia, o sinal e a
carteira simulada de cada série da lista, com o hash e a data, antes do pregão em que valeriam.

- `registro`: a cadeia de hashes de cada série (um dia por linha, sem regravar, falta registrada);
- `series`: a lista fixa das séries e a conta de cada uma, feita pelo próprio simulador registrado;
- `dados`: a leitura dos dados do dia no disco, das mesmas fontes que as séries já usam;
- `julgamento`: a conta de P1 a P3, 12 meses depois do início;
- `gravar`: a linha de comando que grava o que está pendente (`python -m trader.papel.gravar`).

Nada vai para corretora e nada aqui é recomendação de investimento: o papel só grava o que a regra
registrada manda, e uma série que passa continua sem dinheiro (seção 5).
"""
