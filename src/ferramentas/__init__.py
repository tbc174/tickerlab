"""Ferramentas grátis do site público: as contas de referência (plano de 14/10/2026, ADR 0046).

Cada conta daqui tem uma cópia em TypeScript em `web/src/ferramentas/contas/`, que roda no
navegador; `web/testes/golden_ferramentas.json` (gerado por `scripts/gerar_golden_ferramentas.py`)
guarda casos com o resultado do Python, e o vitest confere que o TypeScript dá o mesmo número.
Mudou uma conta aqui? Mude a cópia em TS e rode o gerador.

Só contas, em tipos simples (sem pandas): o site, o app e a API podem usar as mesmas.
"""
