"""Portão do nome por fonte (ADR 0106, item 4): o nome da pessoa só sai de casa com tudo isto junto.

1. a bandeira da fonte em `NOMES_LIBERADOS` (hoje todas `False`; abrir é um PR de uma linha, nível 1);
2. o arquivo `base/conferidas/portao_<fonte>.toml` com as quatro condições (`lia`, `ripd`, `privacidade`,
   `canal`), cada uma com `data` e `pode = true` (o "pode" do Tiago).

Tela, API, PDF e exportação passam o nome por `nome_para_saida`: fechado, devolve `None`.
"""

from pathlib import Path

import tomllib

NOMES_LIBERADOS: dict[str, bool] = {"rfb-cnpj": False}
CONDICOES = ("lia", "ripd", "privacidade", "canal")
PASTA_DAS_CONDICOES = Path(__file__).resolve().parent.parent / "conferidas"


def _arquivo(fonte: str, pasta: Path) -> Path:
    return pasta / f"portao_{fonte.replace('-', '_')}.toml"


def condicoes_cumpridas(fonte: str, pasta: Path = PASTA_DAS_CONDICOES) -> bool:
    """As quatro condições estão escritas, com data e o "pode"?"""
    arquivo = _arquivo(fonte, pasta)
    if not arquivo.is_file():
        return False
    escrito = tomllib.loads(arquivo.read_text(encoding="utf-8"))
    return all(
        isinstance(escrito.get(c), dict)
        and bool(escrito[c].get("data"))
        and escrito[c].get("pode") is True
        for c in CONDICOES
    )


def nomes_liberados(fonte: str, pasta: Path = PASTA_DAS_CONDICOES) -> bool:
    """Bandeira ligada **e** condições cumpridas; fonte desconhecida fica fechada."""
    return NOMES_LIBERADOS.get(fonte, False) and condicoes_cumpridas(fonte, pasta)


def nome_para_saida(
    fonte: str, nome: str | None, pasta: Path = PASTA_DAS_CONDICOES
) -> str | None:
    """O nome, se o portão da fonte está aberto; senão `None` (a tela mostra só a função e a data)."""
    return nome if nomes_liberados(fonte, pasta) else None
