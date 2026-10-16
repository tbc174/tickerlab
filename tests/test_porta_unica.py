"""Código novo lê a base só pela porta (ADR 0077, item 9; plano da rede, PR 4, tarefa 4.3).

Ler Parquet direto (`read_parquet`, `ler_tabela`, `read_table`) ou abrir outro DuckDB fora de
`base/porta/` quebra este teste, salvo nos montadores (`scripts/carga_*`, `montar_*` e `coletar_*`
gravam a base e releem o que gravaram) e nas exceções herdadas abaixo, cada uma com o motivo. A
lista só diminui: um arquivo novo nela muda também o teto, e isso aparece na revisão do PR.
"""

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PASTAS = ("base", "src", "scripts", "telas")
A_PORTA = "base/porta/"
LE_A_BASE = re.compile(r"read_parquet|ler_tabela|read_table\(|duckdb\.connect")
MONTADORES = ("scripts/carga_*.py", "scripts/montar_*.py", "scripts/coletar_*.py")

_ORIGINAL_EM_PARQUET = (
    "lê o original que a fonte entrega em Parquet (bytes do acervo), não a base"
)
_CRIPTO = "base de cripto (ADR 0041): pasta própria, montada e lida pelo próprio módulo"
EXCECOES_HERDADAS: dict[str, str] = {
    "base/parquet.py": "é quem grava e confere as tabelas (hash, versões, lápide)",
    "base/ponto_no_tempo.py": "grava e confere a base dos balanços por ano (série 1)",
    "base/auditores.py": "montador das trocas de auditor: relê todos os anos de `auditores`",
    "base/empresa_serie.py": "montador da `empresa_serie`: relê `controladas` e lê o original da ANEEL",
    "base/arquivo/obter.py": _ORIGINAL_EM_PARQUET,
    "base/setoriais/aneel.py": _ORIGINAL_EM_PARQUET,
    "base/setoriais/ons.py": _ORIGINAL_EM_PARQUET,
    "base/cripto/arquivos.py": _CRIPTO,
    "base/cripto/coleta.py": _CRIPTO,
    "base/cripto/leitura.py": _CRIPTO,
    "base/cripto/reprodutivel.py": _CRIPTO,
}
TETO_DE_EXCECOES = (
    11  # só desce: arquivo que passou para a porta sai da lista e o teto cai
)


def _arquivos() -> list[str]:
    return sorted(
        a.relative_to(RAIZ).as_posix()
        for pasta in PASTAS
        for a in (RAIZ / pasta).rglob("*.py")
    ) + ["app.py"]


def _montador(arquivo: str) -> bool:
    return any(Path(arquivo).match(padrao) for padrao in MONTADORES)


def _le_a_base(arquivo: str) -> bool:
    return bool(LE_A_BASE.search((RAIZ / arquivo).read_text(encoding="utf-8")))


def test_codigo_novo_so_le_a_base_pela_porta():
    fora = [
        a
        for a in _arquivos()
        if not a.startswith(A_PORTA)
        and not _montador(a)
        and a not in EXCECOES_HERDADAS
        and _le_a_base(a)
    ]
    assert not fora, (
        f"lendo a base sem passar pela porta: {fora}; use `base.porta` "
        "(ler, rede, carteira) ou, se for um montador, o nome scripts/carga_*, montar_* ou coletar_*"
    )


def test_excecoes_so_diminuem():
    """Cada exceção ainda lê a base (senão sai da lista) e o número delas não sobe."""
    assert len(EXCECOES_HERDADAS) <= TETO_DE_EXCECOES
    sobrando = [
        a for a in EXCECOES_HERDADAS if not (RAIZ / a).is_file() or not _le_a_base(a)
    ]
    assert not sobrando, (
        f"já não leem a base direto: tire da lista e baixe o teto: {sobrando}"
    )
    assert all(motivo.strip() for motivo in EXCECOES_HERDADAS.values())


def test_o_padrao_pega_as_formas_de_ler():
    for linha in (
        "pd.read_parquet(arquivo)",
        "ler_tabela(rede / 'x.parquet')",
        "pq.read_table(caminho)",
        "duckdb.connect()",
    ):
        assert LE_A_BASE.search(linha), linha
    assert _montador("scripts/montar_rede.py")
    assert not _montador("scripts/medir_rede.py")
