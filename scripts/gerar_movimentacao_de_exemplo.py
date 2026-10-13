"""Gera conteudo/movimentacao_de_exemplo.xlsx: uma movimentação da B3 FICTÍCIA.

Mesmo formato da planilha real da Área do Investidor (colunas, tipos, data em texto, "-" no lugar
de número, do mais novo ao mais velho) e os mesmos ativos da carteira de exemplo
(`conteudo/carteira_de_exemplo.xlsx`), com as quantidades finais batendo com ela:

- PETR4: duas compras e uma venda (o médio não muda com a venda), dividendos e JCP.
- VALE3: uma compra e proventos.
- ITUB4: compra, bonificação e outra compra.
- WEGE3: a movimentação começa depois da primeira compra (custo médio incompleto).
- HGLG11: fundo imobiliário comprado e vendido inteiro, com rendimentos e um reembolso.
- E linhas que ficam fora das contas: transferência entre corretoras, aluguel e Tesouro.

Uso: .venv\\Scripts\\python -m scripts.gerar_movimentacao_de_exemplo
"""

from pathlib import Path

import pandas as pd

DESTINO = Path(__file__).parents[1] / "conteudo" / "movimentacao_de_exemplo.xlsx"
CORRETORA = "CORRETORA DE EXEMPLO S/A"
PETR = "PETR4 - PETROLEO BRASILEIRO S/A PETROBRAS"
VALE = "VALE3 - VALE S.A."
ITUB = "ITUB4 - ITAU UNIBANCO HOLDING S.A."
WEGE = "WEGE3 - WEG S.A."
HGLG = "HGLG11 - CGHG LOGISTICA FDO INV IMOB - FII"
TESOURO = "Tesouro Selic 2029"
LIQUIDACAO = "Transferência - Liquidação"
JCP = "Juros Sobre Capital Próprio"

# (entrada, data, movimentação, produto, quantidade, preço unitário, valor da operação)
LINHAS = [
    ("Credito", "01/02/2024", LIQUIDACAO, HGLG, 10, 160.0, 1600.0),
    ("Credito", "05/03/2024", LIQUIDACAO, PETR, 100, 30.0, 3000.0),
    ("Credito", "15/03/2024", "Rendimento", HGLG, 10, 1.1, 11.0),
    ("Credito", "02/04/2024", LIQUIDACAO, VALE, 80, 62.0, 4960.0),
    ("Credito", "15/04/2024", "Reembolso", HGLG, 10, "-", 11.0),
    ("Credito", "06/05/2024", LIQUIDACAO, ITUB, 100, 28.0, 2800.0),
    ("Credito", "14/06/2024", "Rendimento", HGLG, 10, 1.1, 11.0),
    ("Credito", "20/06/2024", "Dividendo", PETR, 100, 0.9, 90.0),
    ("Debito", "15/07/2024", LIQUIDACAO, WEGE, 10, 40.0, 400.0),
    ("Credito", "10/09/2024", LIQUIDACAO, PETR, 100, 36.0, 3600.0),
    ("Credito", "13/09/2024", "Rendimento", HGLG, 10, 1.1, 11.0),
    ("Debito", "20/10/2024", LIQUIDACAO, HGLG, 10, 165.0, 1650.0),
    ("Debito", "05/11/2024", "Transferência", PETR, 50, "-", "-"),
    ("Credito", "05/11/2024", "Transferência", PETR, 50, "-", "-"),
    ("Credito", "18/12/2024", JCP, PETR, 200, 0.5, 85.0),  # líquido: 15% de IR retido
    ("Credito", "08/01/2025", LIQUIDACAO, WEGE, 10, 45.0, 450.0),
    ("Credito", "20/01/2025", "Empréstimo", PETR, 50, "-", 3.5),
    ("Debito", "12/02/2025", LIQUIDACAO, PETR, 50, 40.0, 2000.0),
    ("Credito", "14/03/2025", "Dividendo", VALE, 80, 2.1, 168.0),
    ("Credito", "20/03/2025", "Bonificação em Ativos", ITUB, 10, "-", "-"),
    ("Debito", "02/04/2025", "COMPRA / VENDA", TESOURO, 1, 15000.0, 15000.0),
    ("Credito", "03/06/2025", LIQUIDACAO, ITUB, 10, 35.0, 350.0),
    ("Credito", "01/07/2025", JCP, ITUB, 110, 0.2, 18.7),
    ("Credito", "21/08/2025", "Dividendo", PETR, 150, 1.2, 180.0),
    ("Credito", "10/09/2025", JCP, VALE, 80, 1.0, 68.0),
    ("Credito", "28/11/2025", JCP, WEGE, 40, 0.3, 10.2),
    ("Credito", "27/02/2026", "Dividendo", ITUB, 120, 1.5, 180.0),
    ("Credito", "13/03/2026", "Dividendo", VALE, 80, 1.8, 144.0),
    ("Credito", "20/05/2026", "Dividendo", PETR, 150, 1.0, 150.0),
]
COLUNAS = [
    "Entrada/Saída",
    "Data",
    "Movimentação",
    "Produto",
    "Instituição",
    "Quantidade",
    "Preço unitário",
    "Valor da Operação",
]


def tabela() -> pd.DataFrame:
    linhas = [(e, d, m, p, CORRETORA, q, pr, v) for e, d, m, p, q, pr, v in LINHAS]
    return pd.DataFrame(reversed(linhas), columns=COLUNAS)  # a B3 manda do mais novo


def main() -> None:
    tabela().to_excel(DESTINO, sheet_name="Movimentação", index=False)
    print(f"Gerado: {DESTINO}")


if __name__ == "__main__":
    main()
