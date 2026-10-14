"""Gera conteudo/proventos_a_receber_de_exemplo.xlsx: proventos a receber da B3 FICTÍCIOS.

Mesmo formato da planilha real da Área do Investidor (colunas, tipos de evento em maiúsculas,
data em texto ou "-", quantidade em texto, linha "Total líquido" no fim) e os mesmos ativos da
carteira de exemplo (`conteudo/carteira_de_exemplo.xlsx`):

- PETR4: dividendo com data e JCP ainda sem data.
- VALE3: JCP com data.
- ITUB4: reembolso de JCP (ação emprestada).
- WEGE3: dividendo e leilão de frações.

Uso: .venv\\Scripts\\python -m scripts.gerar_proventos_a_receber_de_exemplo
"""

from pathlib import Path

import pandas as pd

DESTINO = Path(__file__).parents[1] / "conteudo" / "proventos_a_receber_de_exemplo.xlsx"
CORRETORA = "CORRETORA DE EXEMPLO S/A"
CONTA = 1000001
PETR = "PETR4 - PETROLEO BRASILEIRO S.A. PETROBRAS"
VALE = "VALE3 - VALE S.A."
ITUB = "ITUB4 - ITAU UNIBANCO HOLDING S.A."
WEGE = "WEGE3 - WEG S.A."
JCP = "JUROS SOBRE CAPITAL PRÓPRIO"

# (produto, tipo, tipo de evento, previsão de pagamento, quantidade, preço unitário, valor líquido)
LINHAS = [
    (PETR, "PN", "DIVIDENDO", "20/11/2026", "150", 1.1, 165.0),
    (PETR, "PN", JCP, "-", "150", 0.4, 51.0),
    (VALE, "ON", JCP, "05/12/2026", "80", 1.2, 81.6),
    (ITUB, "PN", f"Reembolso - {JCP}", "01/12/2026", "20", 0.2, 3.4),
    (WEGE, "ON", "DIVIDENDO", "15/12/2026", "40", 0.3, 12.0),
    (WEGE, "ON", "LEILÃO DE FRAÇÕES", "10/11/2026", "-", 18.5, 18.5),
]
COLUNAS = [
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


def tabela() -> pd.DataFrame:
    linhas: list[tuple[object, ...]] = [
        (p, t, e, d, CORRETORA, CONTA, q, pr, v) for p, t, e, d, q, pr, v in LINHAS
    ]
    total = round(sum(linha[-1] for linha in LINHAS), 2)
    linhas.append((None,) * 7 + ("Total líquido", total))
    return pd.DataFrame(linhas, columns=COLUNAS)


def main() -> None:
    tabela().to_excel(DESTINO, sheet_name="Proventos a Receber", index=False)
    print(f"Gerado: {DESTINO}")


if __name__ == "__main__":
    main()
