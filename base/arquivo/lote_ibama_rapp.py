"""Relatórios do RAPP do IBAMA no arquivista (meta das 300 tabelas pelo CNPJ, linha 1074, PR 1).

O que o arquivista passa a guardar, sempre como veio (a razão social e o texto livre ficam no acervo; a tabela de
`base/ibama_rapp.py` não os leva): emissões de poluentes atmosféricos, efluentes líquidos, fontes de energia e a
cadeia dos resíduos sólidos (destinador, transportador e armazenador). Família `ibama` (domínio público no portal;
no código, "integridade sob contrato", ADR 0122 Emenda 1).

Escolhas (testes em `tests/test_base_arquivo_lote_ibama_rapp.py`):
- **endereço fixo, sem descoberta pelo CKAN:** cada relatório é sempre `dados/RAPP/<pasta>/relatorio.csv` no
  próprio portal do IBAMA (conferido em 25/11/2026). O endereço sai do código, nunca do dado do portal, e o pacote
  também publica o mesmo dado em HTML, XML e JSON, que não interessam;
- **mensal:** o IBAMA regrava o arquivo inteiro de vez em quando (a última, em 04/05/2026); o arquivista olha uma
  vez por mês e guarda só quando o conteúdo muda;
- **pesada:** o de efluentes tem 188 MB e o de energia 213 MB.
"""

from base.arquivo.coleta import Alvo, Descobrir, Fonte
from base.ibama_rapp import RELATORIOS

MENSAL = "mensal"
PESADAS = frozenset({"ibama-rapp-efluentes-liquidos", "ibama-rapp-fontes-energeticas"})


def _fixo(url: str) -> Descobrir:
    return lambda _cliente, _agora: [Alvo(url)]


def fontes() -> list[Fonte]:
    """As fontes do lote, para a lista `FONTES` (os ids seguem a família: `ibama-rapp-...`)."""
    return [
        Fonte(r.fonte, MENSAL, _fixo(r.url), pesada=r.fonte in PESADAS)
        for r in RELATORIOS
    ]
