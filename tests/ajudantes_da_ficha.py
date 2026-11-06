"""A ficha da CPFL congelada em 17/10/2026, a base dos testes que dependem dos números dela.

`dados_de_exemplo/dossie/` é a ficha do site e muda a cada troca (ADR do relatório de exemplo); o gabarito
da análise e os testes de relatório foram escritos em cima desta, que não muda.
"""

from pathlib import Path

FICHA_DE_17_10 = (
    Path(__file__).parent / "arquivos" / "analise" / "cpfl" / "ficha-17-10.json"
)
