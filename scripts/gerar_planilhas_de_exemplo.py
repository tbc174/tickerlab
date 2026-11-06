"""Gera as três planilhas da B3 FICTÍCIAS de `conteudo/` que o app mostra como exemplo.

Mesmo formato das planilhas reais da Área do Investidor (colunas, tipos, data em texto, "-" no lugar
de número, do mais novo ao mais velho) e os mesmos ativos da carteira de exemplo
(`conteudo/carteira_de_exemplo.xlsx`), com as quantidades finais batendo com ela.

Movimentação (`movimentacao_de_exemplo.xlsx`):

- PETR4: duas compras e uma venda (o médio não muda com a venda), dividendos e JCP.
- VALE3: uma compra e proventos.
- ITUB4: compra, bonificação e outra compra.
- WEGE3: a movimentação começa depois da primeira compra (custo médio incompleto).
- HGLG11: fundo imobiliário comprado e vendido inteiro, com rendimentos e um reembolso.
- E linhas que ficam fora das contas: transferência entre corretoras, aluguel e Tesouro.

Negociação (`negociacao_de_exemplo.xlsx`; nomes dos mercados, "-" no vencimento do à vista,
fracionário com F, Valor dos futuros já multiplicado):

- PETR4: compra (com uma parte no fracionário) e venda com lucro, em meses diferentes.
- VALE3: day trade (compra 200 e vende 100 no mesmo dia) e venda do resto com prejuízo.
- HGLG11: fundo imobiliário comprado e vendido (o nome vem da movimentação de exemplo).
- WINM26: minicontrato de índice comprado e vendido no mesmo dia.
- WEGE3: venda de ações compradas antes do período (fica sem resultado).
- BOVAC130: opção de compra (fica de fora, com aviso).

Proventos a receber (`proventos_a_receber_de_exemplo.xlsx`; tipos de evento em maiúsculas, data em
texto ou "-", quantidade em texto, linha "Total líquido" no fim):

- PETR4: dividendo com data e JCP ainda sem data.
- VALE3: JCP com data.
- ITUB4: reembolso de JCP (ação emprestada).
- WEGE3: dividendo e leilão de frações.

Até 05/11/2026 eram três scripts (gerar_movimentacao_de_exemplo, gerar_negociacao_de_exemplo e
gerar_proventos_a_receber_de_exemplo); viraram um só na casa em ordem (fila 701). As planilhas
geradas ficam no Git: `tests/test_gerar_planilhas_de_exemplo.py` confere que são as deste gerador.

Uso: .venv\\Scripts\\python -m scripts.gerar_planilhas_de_exemplo [movimentacao|negociacao|proventos]

Roda: manual (python -m scripts.gerar_planilhas_de_exemplo), quando a carteira de exemplo muda; o app
(telas/carteira_b3.py) e os testes leem as planilhas prontas de conteudo/.
"""

import sys
from collections.abc import Callable
from pathlib import Path

import pandas as pd

CONTEUDO = Path(__file__).parents[1] / "conteudo"
CORRETORA = "CORRETORA DE EXEMPLO S/A"
VALE = "VALE3 - VALE S.A."
ITUB = "ITUB4 - ITAU UNIBANCO HOLDING S.A."
WEGE = "WEGE3 - WEG S.A."

# --- movimentação (extrato da Área do Investidor) ---------------------------------------------------
PETR_NA_MOVIMENTACAO = "PETR4 - PETROLEO BRASILEIRO S/A PETROBRAS"
HGLG = "HGLG11 - CGHG LOGISTICA FDO INV IMOB - FII"
TESOURO = "Tesouro Selic 2029"
LIQUIDACAO = "Transferência - Liquidação"
JCP = "Juros Sobre Capital Próprio"

# (entrada, data, movimentação, produto, quantidade, preço unitário, valor da operação)
LINHAS_DA_MOVIMENTACAO = [
    ("Credito", "01/02/2024", LIQUIDACAO, HGLG, 10, 160.0, 1600.0),
    ("Credito", "05/03/2024", LIQUIDACAO, PETR_NA_MOVIMENTACAO, 100, 30.0, 3000.0),
    ("Credito", "15/03/2024", "Rendimento", HGLG, 10, 1.1, 11.0),
    ("Credito", "02/04/2024", LIQUIDACAO, VALE, 80, 62.0, 4960.0),
    ("Credito", "15/04/2024", "Reembolso", HGLG, 10, "-", 11.0),
    ("Credito", "06/05/2024", LIQUIDACAO, ITUB, 100, 28.0, 2800.0),
    ("Credito", "14/06/2024", "Rendimento", HGLG, 10, 1.1, 11.0),
    ("Credito", "20/06/2024", "Dividendo", PETR_NA_MOVIMENTACAO, 100, 0.9, 90.0),
    ("Debito", "15/07/2024", LIQUIDACAO, WEGE, 10, 40.0, 400.0),
    ("Credito", "10/09/2024", LIQUIDACAO, PETR_NA_MOVIMENTACAO, 100, 36.0, 3600.0),
    ("Credito", "13/09/2024", "Rendimento", HGLG, 10, 1.1, 11.0),
    ("Debito", "20/10/2024", LIQUIDACAO, HGLG, 10, 165.0, 1650.0),
    ("Debito", "05/11/2024", "Transferência", PETR_NA_MOVIMENTACAO, 50, "-", "-"),
    ("Credito", "05/11/2024", "Transferência", PETR_NA_MOVIMENTACAO, 50, "-", "-"),
    (
        "Credito",
        "18/12/2024",
        JCP,
        PETR_NA_MOVIMENTACAO,
        200,
        0.5,
        85.0,
    ),  # líquido: 15% de IR retido
    ("Credito", "08/01/2025", LIQUIDACAO, WEGE, 10, 45.0, 450.0),
    ("Credito", "20/01/2025", "Empréstimo", PETR_NA_MOVIMENTACAO, 50, "-", 3.5),
    ("Debito", "12/02/2025", LIQUIDACAO, PETR_NA_MOVIMENTACAO, 50, 40.0, 2000.0),
    ("Credito", "14/03/2025", "Dividendo", VALE, 80, 2.1, 168.0),
    ("Credito", "20/03/2025", "Bonificação em Ativos", ITUB, 10, "-", "-"),
    ("Debito", "02/04/2025", "COMPRA / VENDA", TESOURO, 1, 15000.0, 15000.0),
    ("Credito", "03/06/2025", LIQUIDACAO, ITUB, 10, 35.0, 350.0),
    ("Credito", "01/07/2025", JCP, ITUB, 110, 0.2, 18.7),
    ("Credito", "21/08/2025", "Dividendo", PETR_NA_MOVIMENTACAO, 150, 1.2, 180.0),
    ("Credito", "10/09/2025", JCP, VALE, 80, 1.0, 68.0),
    ("Credito", "28/11/2025", JCP, WEGE, 40, 0.3, 10.2),
    ("Credito", "27/02/2026", "Dividendo", ITUB, 120, 1.5, 180.0),
    ("Credito", "13/03/2026", "Dividendo", VALE, 80, 1.8, 144.0),
    ("Credito", "20/05/2026", "Dividendo", PETR_NA_MOVIMENTACAO, 150, 1.0, 150.0),
]
COLUNAS_DA_MOVIMENTACAO = [
    "Entrada/Saída",
    "Data",
    "Movimentação",
    "Produto",
    "Instituição",
    "Quantidade",
    "Preço unitário",
    "Valor da Operação",
]

# --- negociação (negócios da Área do Investidor) ----------------------------------------------------
A_VISTA = "Mercado à Vista"
FRACIONARIO = "Mercado Fracionário"
OPCAO = "Opção de Compra sobre Ações"

# (data, compra/venda, mercado, prazo, código, quantidade, preço, valor)
LINHAS_DA_NEGOCIACAO = [
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
COLUNAS_DA_NEGOCIACAO = [
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

# --- proventos a receber (eventos provisionados da Área do Investidor) --------------------------------
CONTA = 1000001
PETR_NOS_PROVENTOS = "PETR4 - PETROLEO BRASILEIRO S.A. PETROBRAS"
JCP_EM_MAIUSCULAS = "JUROS SOBRE CAPITAL PRÓPRIO"

# (produto, tipo, tipo de evento, previsão de pagamento, quantidade, preço unitário, valor líquido)
LINHAS_DOS_PROVENTOS = [
    (PETR_NOS_PROVENTOS, "PN", "DIVIDENDO", "20/11/2026", "150", 1.1, 165.0),
    (PETR_NOS_PROVENTOS, "PN", JCP_EM_MAIUSCULAS, "-", "150", 0.4, 51.0),
    (VALE, "ON", JCP_EM_MAIUSCULAS, "05/12/2026", "80", 1.2, 81.6),
    (ITUB, "PN", f"Reembolso - {JCP_EM_MAIUSCULAS}", "01/12/2026", "20", 0.2, 3.4),
    (WEGE, "ON", "DIVIDENDO", "15/12/2026", "40", 0.3, 12.0),
    (WEGE, "ON", "LEILÃO DE FRAÇÕES", "10/11/2026", "-", 18.5, 18.5),
]
COLUNAS_DOS_PROVENTOS = [
    "Produto",
    "Tipo",
    "Tipo de Evento",
    "Previsão de pagamento",
    "Instituição",
    "Conta",
    "Quantidade",
    "Preço unitário",
    "Valor líquido",
]


def movimentacao() -> pd.DataFrame:
    """Movimentação fictícia, do mais novo ao mais velho (como a B3 manda)."""
    linhas = [
        (e, d, m, p, CORRETORA, q, pr, v)
        for e, d, m, p, q, pr, v in LINHAS_DA_MOVIMENTACAO
    ]
    return pd.DataFrame(reversed(linhas), columns=COLUNAS_DA_MOVIMENTACAO)


def negociacao() -> pd.DataFrame:
    """Negociação fictícia, do mais novo ao mais velho (como a B3 manda)."""
    linhas = [
        (d, t, m, p, CORRETORA, c, q, pr, v)
        for d, t, m, p, c, q, pr, v in LINHAS_DA_NEGOCIACAO
    ]
    return pd.DataFrame(reversed(linhas), columns=COLUNAS_DA_NEGOCIACAO)


def proventos_a_receber() -> pd.DataFrame:
    """Proventos a receber fictícios, com a linha "Total líquido" no fim (como a B3 manda)."""
    linhas: list[tuple[object, ...]] = [
        (p, t, e, d, CORRETORA, CONTA, q, pr, v)
        for p, t, e, d, q, pr, v in LINHAS_DOS_PROVENTOS
    ]
    total = round(sum(linha[-1] for linha in LINHAS_DOS_PROVENTOS), 2)
    linhas.append((None,) * 7 + ("Total líquido", total))
    return pd.DataFrame(linhas, columns=COLUNAS_DOS_PROVENTOS)


# nome na linha de comando -> (tabela, arquivo em conteudo/, nome da aba)
PLANILHAS: dict[str, tuple[Callable[[], pd.DataFrame], str, str]] = {
    "movimentacao": (movimentacao, "movimentacao_de_exemplo.xlsx", "Movimentação"),
    "negociacao": (negociacao, "negociacao_de_exemplo.xlsx", "Negociação"),
    "proventos": (
        proventos_a_receber,
        "proventos_a_receber_de_exemplo.xlsx",
        "Proventos a Receber",
    ),
}


def gerar(nome: str, pasta: Path | None = None) -> Path:
    """Grava a planilha `nome` (chave de `PLANILHAS`) em `pasta` (padrão: `conteudo/`) e devolve o caminho."""
    tabela, arquivo, aba = PLANILHAS[nome]
    destino = (CONTEUDO if pasta is None else pasta) / arquivo
    tabela().to_excel(destino, sheet_name=aba, index=False)
    return destino


def main(argumentos: list[str] | None = None) -> None:
    """Gera as planilhas pedidas na linha de comando (todas, sem argumento)."""
    pedidas = argumentos or list(PLANILHAS)
    desconhecidas = [nome for nome in pedidas if nome not in PLANILHAS]
    if desconhecidas:
        raise SystemExit(
            f"Planilha desconhecida: {', '.join(desconhecidas)}. Opções: {', '.join(PLANILHAS)}."
        )
    for nome in pedidas:
        print(f"Gerado: {gerar(nome)}")


if __name__ == "__main__":
    main(sys.argv[1:])
