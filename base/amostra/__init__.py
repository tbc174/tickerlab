"""Amostra integrada (ADR 0058; plano `projeto-acoes/planos/2026-10-16-amostra-integrada-v1.md`): o painel
companhia × fim de mês em que cada linha tem só o que se sabia da companhia naquele dia, de todas as
fontes da base.

- `como_era.py`: a grade de meses, o "valor mais novo já público" (as-of) e o corte da base numa data,
  que os testes usam para provar que nenhum bloco olha o futuro;
- `universo.py`: quem está no painel em cada mês (registrada na CVM, já com uma DFP ou ITR entregue) e
  os tickers válidos na data. As canceladas ficam nos meses em que existiam.

Os outros blocos (demonstrações, eventos, governança, fundos, setor, macro) entram um por PR.
"""
