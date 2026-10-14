"""Gera conteudo/negociacao_de_exemplo.xlsx: uma negociação da B3 FICTÍCIA.

Mesmo formato da planilha real da Área do Investidor (colunas, nomes dos mercados, data em texto,
"-" no vencimento do à vista, fracionário com F, Valor dos futuros já multiplicado, do mais novo
ao mais velho) e ativos da carteira de exemplo:

- PETR4: compra (com uma parte no fracionário) e venda com lucro, em meses diferentes.
- VALE3: day trade (compra 200 e vende 100 no mesmo dia) e venda do resto com prejuízo.
- HGLG11: fundo imobiliário comprado e vendido (o nome vem da movimentação de exemplo).
- WINM26: minicontrato de índice comprado e vendido no mesmo dia.
- WEGE3: venda de ações compradas antes do período (fica sem resultado).
- BOVAC130: opção de compra (fica de fora, com aviso).

Uso: .venv\\Scripts\\python -m scripts.gerar_negociacao_de_exemplo
"""

from pathlib import Path

import pandas as pd

DESTINO = Path(__file__).parents[1] / "conteudo" / "negociacao_de_exemplo.xlsx"
CORRETORA = "CORRETORA DE EXEMPLO S/A"
A_VISTA = "Mercado à Vista"
FRACIONARIO = "Mercado Fracionário"
OPCAO = "Opção de Compra sobre Ações"

# (data, compra/venda, mercado, prazo, código, quantidade, preço, valor)
LINHAS = [
    ("05/01/2026", "Compra", A_VISTA, "-", "PETR4", 100, 30.0, 3000.0),
    ("05/01/2026", "Compra", FRACIONARIO, "-", "PETR4F", 5, 30.0, 150.0),
    ("12/01/2026", "Compra", A_VISTA, "-", "HGLG11", 10, 160.0, 1600.0),
    ("10/02/2026", "Venda", A_VISTA, "-", "WEGE3", 10, 45.0, 450.0),
    ("20/02/2026", "Venda", A_VISTA, "-", "PETR4", 50, 34.0, 1700.0),
    ("05/03/2026", "Compra", OPCAO, "20/03/2026", "BOVAC130", 100, 1.2, 120.0),
    ("10/03/2026", "Compra", A_VISTA, "-", "VALE3", 200, 60.0, 12000.0),
    ("10/03/2026", "Venda", A_VISTA, "-", "VALE3", 100, 61.5, 6150.0),
    ("18/03/2026", "Venda", A_VISTA, "-", "HGLG11", 10, 166.0, 1660.0),
    ("15/04/2026", "Venda", A_VISTA, "-", "VALE3", 100, 58.0, 5800.0),
    ("22/04/2026", "Compra", "Futuro", "17/06/2026", "WINM26", 2, 128000, 51200.0),
    ("22/04/2026", "Venda", "Futuro", "17/06/2026", "WINM26", 2, 128400, 51360.0),
]
COLUNAS = [
    "Data do Negócio",
    "Tipo de Movimentação",
    "Mercado",
    "Prazo/Vencimento",
    "Instituição",
    "Código de Negociação",
    "Quantidade",
    "Preço",
    "Valor",
]


def tabela() -> pd.DataFrame:
    linhas = [
        (d, t, m, p, CORRETORA, c, q, pr, v) for d, t, m, p, c, q, pr, v in LINHAS
    ]
    return pd.DataFrame(reversed(linhas), columns=COLUNAS)  # a B3 manda do mais novo


def main() -> None:
    tabela().to_excel(DESTINO, sheet_name="Negociação", index=False)
    print(f"Gerado: {DESTINO}")


if __name__ == "__main__":
    main()
