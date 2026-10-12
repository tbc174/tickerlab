"""Grava os valores "golden" da fachada de análise: `tests/arquivos/golden_analise.json`.

    python -m scripts.gerar_golden_analise

São os números de hoje, calculados com os dados de exemplo do projeto. O teste
`tests/test_analise.py` recalcula e compara: se um número mudar sem a versão da fórmula
(`src.analise.VERSOES_DAS_FORMULAS`) mudar junto, o teste falha. Rodar este script **só** depois de
mudar uma fórmula de propósito e subir a versão dela.
"""

import json
from pathlib import Path

import pandas as pd

from src import analise
from src.presets import Preset, resolver

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "tests" / "arquivos" / "golden_analise.json"
PERSONALIZADO = {
    "tecnica.rsi_periodo": 21,
    "tecnica.tipo_de_media": "exponencial",
    "tecnica.media_rapida": 20,
    "tecnica.media_lenta": 50,
    "tecnica.bollinger_periodo": 30,
    "tecnica.bollinger_desvios": 2.5,
    "tecnica.atr_periodo": 21,
    "quant.janela_volatilidade": 63,
    "quant.janela_correlacao": 60,
    "quant.var_confianca": 99,
    "quant.taxa_livre_de_risco": "cdi",
}
CDI_DO_CENARIO = 0.1


def dados(ticker: str) -> pd.DataFrame:
    tabela = pd.read_csv(
        RAIZ / "dados_de_exemplo" / f"{ticker.replace('^', '_')}.csv",
        index_col=0,
        parse_dates=True,
    )
    tabela.attrs["origem"] = "exemplo"
    return tabela


def cenarios() -> dict[str, analise.Analise]:
    personalizado = resolver([Preset(escopo="global", parametros=PERSONALIZADO)])
    return {
        "PETR4_padrao": analise.analisar_ativo(
            "PETR4.SA", dados("PETR4.SA"), benchmark=dados("^BVSP")["Close"]
        ),
        "PETR4_personalizado": analise.analisar_ativo(
            "PETR4.SA",
            dados("PETR4.SA"),
            personalizado,
            taxa_cdi_anual=CDI_DO_CENARIO,
            benchmark=dados("^BVSP")["Close"],
        ),
        "AAPL_contra_SP500": analise.analisar_ativo(
            "AAPL", dados("AAPL"), benchmark=dados("^GSPC")["Close"]
        ),
    }


def main() -> None:
    conteudo = {
        "versoes": analise.VERSOES_DAS_FORMULAS,
        "cenarios": {
            nome: {k: m.valor for k, m in a.metricas.items()}
            for nome, a in cenarios().items()
        },
    }
    DESTINO.write_text(
        json.dumps(conteudo, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"golden gravado em {DESTINO}")


if __name__ == "__main__":
    main()
