"""A planilha de um levantamento da CONAB em miniatura (2 UFs), no desenho de `site_previsao-de-safra-cafe-*.xls`.

A CONAB publica .xls; o leitor aceita também .xlsx (o pandas escolhe o motor), e é .xlsx que o `openpyxl`
sabe escrever. Os números são inventados; a estrutura (3 linhas de cabeçalho, regiões e sub-regiões
no meio das UFs, rodapé) foi lida da planilha de setembro/2026.
"""

import io

from openpyxl import Workbook

ABAS_DE_PRODUCAO = {
    "1 Café Total": "total",
    "2 Café Arábica": "arabica",
    "3 Café Conilon": "conilon",
}
ABAS_DE_AREA = {
    "4 Café Total - Área": "total",
    "5 Café Arábica - Área": "arabica",
    "6 Café Conilon - Área": "conilon",
}


def _cabecalho(safra: int, blocos: tuple[str, ...]) -> list[list]:
    titulos = ["REGIÃO/UF"]
    anos = [""]
    letras = [""]
    for bloco in blocos:
        titulos += [bloco, "", ""]
        anos += [f"Safra {safra - 1}", f"Safra {safra}", "VAR. % "]
        letras += [" (a)", "(b)", "(b/a)"]
    return [[""] * len(titulos)] * 3 + [titulos, anos, letras]


def _linha(rotulo: str, valores: list) -> list:
    return [rotulo, *[x for v in valores for x in (v * 0.9, v, 11.1)]]


def _aba_de_producao(safra: int, tipo: str, fator: float) -> list[list]:
    linhas = _cabecalho(
        safra,
        (
            "ÁREA EM PRODUÇÃO (ha)",
            "PRODUTIVIDADE (sc/ha)",
            "PRODUÇÃO (mil sacas beneficiadas)",
        ),
    )
    mg, es = 100000 * fator, 20000 * fator
    linhas += [
        _linha("SUDESTE", [mg + es, 30.0, 4000.0 * fator]),
        _linha("MG", [mg, 30.0, 3000.0 * fator]),
        _linha("     Sul e Centro-Oeste", [mg / 2, 28.0, 1500.0 * fator]),
        _linha("ES", [es, 25.0, 500.0 * fator]),
        _linha("OUTROS (*)", [1000.0, 10.0, 10.0]),
        _linha("BRASIL", [mg + es + 1000, 29.0, 3510.0 * fator]),
        ["Fonte: Conab."] + [""] * 9,
    ]
    return linhas


def _aba_de_area(safra: int, tipo: str, fator: float) -> list[list]:
    linhas = _cabecalho(
        safra, ("ÁREA EM FORMAÇÃO (ha)", "ÁREA EM PRODUÇÃO (ha)", "ÁREA TOTAL (ha)")
    )
    linhas += [
        _linha("MG", [8000.0 * fator, 100000.0 * fator, 108000.0 * fator]),
        _linha("ES", [1500.0 * fator, 20000.0 * fator, 21500.0 * fator]),
        _linha("BRASIL", [9600.0 * fator, 121000.0 * fator, 130600.0 * fator]),
    ]
    return linhas


def planilha(safra: int = 2026, fator_do_arabica: float = 1.0) -> bytes:
    """Um levantamento com as safras `safra - 1` (coluna a) e `safra` (coluna b)."""
    livro = Workbook()
    livro.remove(livro.active)
    for nome, tipo in ABAS_DE_PRODUCAO.items():
        fator = (
            fator_do_arabica if tipo == "arabica" else 0.3 if tipo == "conilon" else 1.3
        )
        aba = livro.create_sheet(nome)
        for linha in _aba_de_producao(safra, tipo, fator):
            aba.append(linha)
    for nome, tipo in ABAS_DE_AREA.items():
        fator = (
            fator_do_arabica if tipo == "arabica" else 0.3 if tipo == "conilon" else 1.3
        )
        aba = livro.create_sheet(nome)
        for linha in _aba_de_area(safra, tipo, fator):
            aba.append(linha)
    livro.create_sheet("10 % Colheita").append(["não é para ler"])
    saida = io.BytesIO()
    livro.save(saida)
    return saida.getvalue()
