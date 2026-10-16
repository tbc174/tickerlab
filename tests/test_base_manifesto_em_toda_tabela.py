"""Toda tabela gravada em `<acervo>/base/` tem manifesto ao lado (ADR 0078): sem o `.json`, a tabela
fica fora da raiz de Merkle carimbada no Bitcoin, sem aviso. Em 15/10/2026, 429 dos 1.138 Parquets
estavam assim (série B, curva, cripto...). Este teste pega o gravador novo que esquecer o manifesto:
quem grava Parquet usa `base/parquet.py` (`gravar_tabela`, `gravar_se_mudou`, `gravar_com_versoes`),
e as exceções abaixo dizem por que não precisam.
"""

from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PASTAS = ("base", "scripts", "src")

PODEM_GRAVAR_PARQUET = {
    "base/parquet.py": "é o gravador com manifesto",
    "base/ponto_no_tempo.py": "base 'como era na data': manifesto próprio, com `sha256_da_tabela`",
    "base/arquivo/obter.py": "original baixado pelo arquivista, guardado em `bruto/`, fora de `base/`",
    "base/cripto/reprodutivel.py": "Parquet só na memória, para calcular o hash",
    "scripts/barras_b3_do_dia.py": "intradiário em `<acervo>/intradiario/`, fora de `base/` (ADR 0019)",
    "scripts/coletar_iex_do_dia.py": "intradiário em `dados_locais/intradiario/`, fora de `base/`",
    "scripts/medir_iex_um_dia.py": "medição de um dia, fora de `base/`",
    "src/exportacao_do_acervo.py": "exportação para os admins, fora de `base/`",
}


def _quem_grava_parquet() -> set[str]:
    return {
        arquivo.relative_to(RAIZ).as_posix()
        for pasta in PASTAS
        for arquivo in (RAIZ / pasta).rglob("*.py")
        if ".to_parquet(" in arquivo.read_text(encoding="utf-8")
    }


def test_so_o_gravador_com_manifesto_e_as_excecoes_gravam_parquet():
    sem_manifesto = _quem_grava_parquet() - set(PODEM_GRAVAR_PARQUET)
    assert not sem_manifesto, (
        f"{sorted(sem_manifesto)} grava(m) Parquet sem manifesto: use "
        "`base/parquet.py::gravar_se_mudou` (ou ponha aqui o porquê, se não fica em `base/`)"
    )


def test_a_lista_de_excecoes_nao_tem_sobra():
    assert set(PODEM_GRAVAR_PARQUET) <= _quem_grava_parquet()
