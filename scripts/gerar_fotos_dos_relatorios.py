"""Grava a "foto" dos relatórios em PDF: `tests/arquivos/fotos_dos_relatorios.json`.

    python -m scripts.gerar_fotos_dos_relatorios

Para cada relatório de exemplo (dados de exemplo do projeto, data de geração fixa), guarda as
seções na ordem e os números de cada seção, como aparecem no PDF ("+545,8%", "1,45"). O layout, as
cores e os gráficos ficam de fora, para a foto não quebrar a cada ajuste visual. O teste
`tests/test_fotos_dos_relatorios.py` gera de novo e compara: se um número ou uma seção mudar sem
querer, ele falha e mostra a seção e o número que mudaram. Rodar este script **só** depois de mudar
um relatório de propósito, e explicar a mudança no PR (o diff do JSON mostra o que mudou).
"""

import json
import re
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

import pandas as pd
from pypdf import PdfReader

from src import relatorios
from src.carteira_b3 import ler_carteira
from src.comparacao import alinhar_fechamentos
from src.exemplos import carregar_exemplo

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "tests" / "arquivos" / "fotos_dos_relatorios.json"
CARTEIRA_DA_B3 = RAIZ / "conteudo" / "carteira_de_exemplo.xlsx"
GERADO_EM = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)  # fixa: a data aparece no PDF
PERIODO = "5y"
# o glossário é texto do site (tem teste próprio): fora da foto, para ela mudar só com os números
SECOES_FORA_DA_FOTO = ("Glossário",)
# um número solto (o 4 de "PETR4" não conta) com sinal, milhar, decimais e %/× do PDF
NUMERO = re.compile(r"(?<![A-Za-zÀ-ÿ\d])[+−-]?\d+(?:[.,]\d+)*[%×]?")
# o rodapé "Página 2 de 4" muda com qualquer ajuste de layout: fora da foto
RODAPE = re.compile(r"Página \d+ de \d+")


def _texto(pdf: bytes) -> str:
    texto = " ".join(p.extract_text() for p in PdfReader(BytesIO(pdf)).pages)
    return " ".join(RODAPE.sub(" ", texto).split())


def _titulos(pdf: bytes) -> list[str]:
    """Os títulos das seções, na ordem, pelos marcadores do PDF ("1. Resumo executivo")."""
    return [item.title for item in PdfReader(BytesIO(pdf)).outline]


def extrair(pdf: bytes) -> dict[str, list[str]]:
    """{título da seção: números da seção, na ordem}. A capa (antes da 1ª seção) entra como "Capa".

    Cada seção começa na última vez que o título aparece (a primeira é o sumário da capa).
    """
    texto = _texto(pdf)
    titulos = _titulos(pdf)
    inicios = [texto.rfind(f"{titulo} ") for titulo in titulos]
    cortes = [*inicios, len(texto)]
    foto = {"Capa": NUMERO.findall(texto[: inicios[0]])}
    for titulo, inicio, fim in zip(titulos, cortes, cortes[1:], strict=False):
        nome = titulo.split(". ", 1)[1]
        if nome in SECOES_FORA_DA_FOTO:
            foto[titulo] = []
            continue
        corpo = texto[inicio + len(titulo) : fim]
        foto[titulo] = NUMERO.findall(corpo)
    return foto


def _fechamento(ticker: str) -> pd.Series:
    dados = carregar_exemplo(ticker, PERIODO)
    assert dados is not None, ticker
    return dados["Close"]


def _relatorios() -> dict[str, bytes]:
    petr4 = carregar_exemplo("PETR4.SA", PERIODO)
    assert petr4 is not None
    comparacao, _ = alinhar_fechamentos(
        {t: _fechamento(t) for t in ("PETR4.SA", "VALE3.SA", "AAPL", "^BVSP")}
    )
    carteira = pd.DataFrame(
        {t: _fechamento(t) for t in ("PETR4.SA", "VALE3.SA", "ITUB4.SA", "WEGE3.SA")}
    ).dropna()
    da_b3 = ler_carteira(CARTEIRA_DA_B3.read_bytes(), CARTEIRA_DA_B3.name)
    fechamentos_da_b3 = pd.DataFrame(
        {t: _fechamento(t) for t in da_b3.posicoes["ticker"]}
    )
    comum = {"gerado_em": GERADO_EM, "exemplo": True, "periodo": "5 anos"}
    return {
        "ativo PETR4.SA": relatorios.relatorio_do_ativo("PETR4.SA", petr4, **comum),
        "comparacao": relatorios.relatorio_de_comparacao(comparacao, **comum),
        "backtest PETR4.SA": relatorios.relatorio_de_backtest(
            "PETR4.SA", petr4, "Cruzamento de médias", **comum
        ),
        "carteira": relatorios.relatorio_de_carteira(
            carteira, "Rotação por momentum", **comum
        ),
        "minha carteira": relatorios.relatorio_da_minha_carteira(
            da_b3, fechamentos_da_b3, _fechamento("^BVSP"), demonstracao=True, **comum
        ),
    }


def calcular() -> dict[str, dict[str, list[str]]]:
    return {nome: extrair(pdf) for nome, pdf in _relatorios().items()}


def main() -> None:
    DESTINO.write_text(
        json.dumps(calcular(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"fotos gravadas em {DESTINO}")


if __name__ == "__main__":
    main()
