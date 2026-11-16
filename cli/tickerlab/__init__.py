"""CLI do TickerLab (linha 772; ADR 0127): um cliente fino da API externa do TickerLab Data.

A CLI não tem regra própria: só chama a API (`cliente.py`), formata (`formato.py`) e cita a fonte e a data
de cada número. Conta, consulta, portão e texto ficam no servidor; se faltar um dado, a correção é na API.
"""

__version__ = "0.1.0"
