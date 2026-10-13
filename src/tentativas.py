"""A impressão de uma configuração do backtest, para contar as tentativas (ADR 0037, D2).

Duas rodadas com a mesma estratégia, os mesmos parâmetros, proteções, custo e período no mesmo
ativo são a mesma tentativa; mudar qualquer um deles é uma variação nova. O capital, o imposto e
o CDI não entram: são conferências, e a ficha "Foi sorte?" sempre aplica as duas.

Só a impressão (SHA-256) vai para o banco: dá para contar sem guardar a configuração.
"""

import hashlib
import json
from dataclasses import asdict

from src.protecoes import Protecoes

# a partir daqui a contagem para de crescer (e o app mostra "10.000+"): segura o tamanho da tabela
TETO_POR_PESSOA = 10_000


def impressao(
    ticker: str,
    estrategia: str,
    parametros: dict,
    protecoes: Protecoes | None,
    custo_por_operacao: float,
    periodo: str,
) -> str:
    """O SHA-256 (64 caracteres) da configuração; a ordem dos parâmetros não importa."""
    ligadas = protecoes if protecoes is not None and protecoes.alguma_ligada() else None
    configuracao = {
        "ticker": ticker.upper(),
        "estrategia": estrategia,
        "parametros": parametros,
        "protecoes": None if ligadas is None else asdict(ligadas),
        "custo": round(custo_por_operacao, 8),
        "periodo": periodo,
    }
    texto = json.dumps(configuracao, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()
