"""A ficha do dossiê no app do VPS (plano do dossiê da empresa no app, 17/10/2026, PR 3, tarefa 11).

O servidor de casa manda as fichas para `dados_locais/dossies/<dia>/` e troca o link `atual`; o app lê
`atual/<cnpj>.json`. Uma ficha que não deve ser mostrada some (`None`) ou perde a parte que não pode.
"""

import json
import logging
from datetime import date
from pathlib import Path

import pytest

from src import dossie

EXEMPLO = dossie.FICHA_DE_EXEMPLO
CPFL = "02429144000193"


def _bruta() -> dict:
    return json.loads(EXEMPLO.read_text(encoding="utf-8"))


def _pasta(tmp_path: Path, bruta: dict | str | None = None, nome: str = CPFL) -> Path:
    atual = tmp_path / "atual"
    atual.mkdir(exist_ok=True)
    conteudo = _bruta() if bruta is None else bruta
    (atual / f"{nome}.json").write_text(
        conteudo if isinstance(conteudo, str) else json.dumps(conteudo),
        encoding="utf-8",
    )
    return tmp_path


def test_le_a_ficha_do_cnpj_na_pasta_atual(tmp_path: Path) -> None:
    ficha = dossie.ficha_do(CPFL, _pasta(tmp_path))
    assert ficha is not None
    assert ficha.empresa == "CPFL ENERGIA S.A."


def test_cnpj_formatado_tambem_acha_a_ficha(tmp_path: Path) -> None:
    assert dossie.ficha_do("02.429.144/0001-93", _pasta(tmp_path)) is not None


def test_ficha_ja_vem_cortada(tmp_path: Path) -> None:
    ficha = dossie.ficha_do(CPFL, _pasta(tmp_path))
    setor = next(s for s in ficha.secoes if s.chave == "setor_regulado")
    assert "anatel_banda_larga_fixa" not in setor.tabelas  # o ruído de 113 acessos


def test_ficha_ausente_e_none(tmp_path: Path) -> None:
    assert dossie.ficha_do(CPFL, tmp_path) is None


@pytest.mark.parametrize("cnpj", ["../../etc/passwd", "0242914400019", "", "abc"])
def test_cnpj_estranho_nao_le_nada(tmp_path: Path, cnpj: str) -> None:
    assert dossie.ficha_do(cnpj, _pasta(tmp_path)) is None


def test_versao_desconhecida_e_none_com_log(tmp_path: Path, caplog) -> None:
    pasta = _pasta(tmp_path, _bruta() | {"versao_do_esquema": 99})
    with caplog.at_level(logging.WARNING):
        assert dossie.ficha_do(CPFL, pasta) is None
    assert "versão desconhecida" in caplog.text


@pytest.mark.parametrize("conteudo", ["{nao é json", {"versao_do_esquema": 1}])
def test_json_fora_do_esquema_e_none(tmp_path: Path, conteudo) -> None:
    assert dossie.ficha_do(CPFL, _pasta(tmp_path, conteudo)) is None


def test_ficha_de_outro_cnpj_no_nome_do_arquivo_e_none(tmp_path: Path) -> None:
    outro = "33000167000101"
    assert dossie.ficha_do(outro, _pasta(tmp_path, nome=outro)) is None


def test_arquivo_grande_demais_nem_e_lido(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(dossie, "TAMANHO_MAXIMO", 100)
    assert dossie.ficha_do(CPFL, _pasta(tmp_path)) is None


def test_secao_fora_do_registro_sai_e_o_resto_fica(tmp_path: Path) -> None:
    bruta = _bruta()
    bruta["secoes"].append(
        {"chave": "pgfn", "titulo": "Dívida com a União", "itens": [], "fontes": []}
    )
    ficha = dossie.ficha_do(CPFL, _pasta(tmp_path, bruta))
    assert ficha is not None
    assert "pgfn" not in [s.chave for s in ficha.secoes]
    assert "negocios" in [s.chave for s in ficha.secoes]


def test_tabela_sem_colunas_declaradas_sai(tmp_path: Path) -> None:
    bruta = _bruta()
    bruta["secoes"][0]["tabelas"]["insolvencia"] = [{"cnpj": CPFL, "rj": True}]
    ficha = dossie.ficha_do(CPFL, _pasta(tmp_path, bruta))
    assert "insolvencia" not in ficha.secoes[0].tabelas
    assert "trocas_de_auditor" in ficha.secoes[0].tabelas


def test_cpf_na_ficha_barra_a_ficha_inteira(tmp_path: Path) -> None:
    bruta = _bruta()
    bruta["secoes"][0]["paragrafos"].append("Responsável: 123.456.789-09")
    assert dossie.ficha_do(CPFL, _pasta(tmp_path, bruta)) is None


def test_coluna_de_pessoa_barra_a_ficha_inteira(tmp_path: Path) -> None:
    bruta = _bruta()
    bruta["secoes"][0]["tabelas"]["controladas"][0]["administrador"] = "Fulano"
    assert dossie.ficha_do(CPFL, _pasta(tmp_path, bruta)) is None


def test_variavel_de_ambiente_escolhe_a_pasta(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TICKERLAB_DOSSIES", str(_pasta(tmp_path)))
    assert dossie.ficha_do(CPFL) is not None


# --- a ficha vira o dossiê do relatório -------------------------------------------------------------


def _ficha():
    return dossie.cortar(dossie.ler_ficha(EXEMPLO))  # gerada em 17/10/2026


def test_dossie_tem_as_secoes_as_fontes_e_os_limites() -> None:
    feito = dossie.dossie_da_ficha(_ficha(), date(2026, 10, 18))
    assert [s.chave for s in feito.secoes] == [
        "auditor_e_controladas",
        "ofertas_e_fundos",
        "setor_regulado",
        "negocios",
    ]
    assert "ODbL (dados abertos da CVM; citar a fonte)" in feito.fontes
    assert feito.dia == date(2026, 10, 17)
    assert not feito.velha
    assert any("17/10/2026" in limite for limite in feito.limites)
    assert any("pessoas" in limite for limite in feito.limites)


@pytest.mark.parametrize(
    ("hoje", "velha"),
    [(date(2026, 10, 20), False), (date(2026, 10, 21), True)],
)
def test_mais_de_3_dias_e_ficha_velha(hoje: date, velha: bool) -> None:
    assert dossie.dossie_da_ficha(_ficha(), hoje).velha is velha
