"""A ficha do dossiê no app do VPS (plano do dossiê da empresa no app, 17/10/2026, PR 3, tarefa 11).

O servidor de casa manda as fichas para `dados_locais/dossies/<dia>/` e troca o link `atual`; o app lê
`atual/<cnpj>.json`. Uma ficha que não deve ser mostrada some (`None`) ou perde a parte que não pode.
"""

import json
import logging
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from base import dossie as dossie_da_base
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


SECAO_DA_REDE = {
    "chave": "rede",
    "titulo": "Ligações na rede",
    "itens": [
        {
            "chave": "ligacoes",
            "nome": "Ligações na rede",
            "valor": 1,
            "unidade": "empresas",
        }
    ],
    "tabelas": {
        "ligacoes_da_rede": [
            {
                "relacao": "Controlada",
                "entidade": "CPFL Paulista",
                "cnpj": "33.050.196/0001-88",
                "participacao": 100.0,
                "desde": "2015-01-01",
                "documento": "Formulário de Referência (CVM)",
            }
        ],
        "identificadores_da_empresa": [
            {"identificador": "Ticker", "valor": "CPFE3", "desde": "2010-01-01"}
        ],
    },
    "paragrafos": [],
    "fontes": ["ODbL (dados abertos da CVM; citar a fonte)"],
}


def _com_a_rede(tmp_path: Path) -> Path:
    bruta = _bruta()
    bruta["secoes"].append(SECAO_DA_REDE)
    return _pasta(tmp_path, bruta)


def test_secao_da_rede_chega_ao_app_com_as_tabelas(tmp_path: Path) -> None:
    ficha = dossie.ficha_do(CPFL, _com_a_rede(tmp_path))
    assert ficha is not None
    rede = next(s for s in ficha.secoes if s.chave == "rede")
    assert set(rede.tabelas) == {"ligacoes_da_rede", "identificadores_da_empresa"}
    escrita = next(s for s in dossie.secoes_da_ficha(ficha) if s.chave == "rede")
    assert escrita.tabelas["ligacoes_da_rede"][0]["Participação"] == "100%"


def test_relatorio_da_empresa_ignora_as_secoes_do_molde_b(tmp_path: Path) -> None:
    """O molde A fica igual (a análise escrita confere o hash dele): a seção da rede é do molde B."""
    sem_a_rede = dossie.ficha_do(CPFL, _pasta(tmp_path))
    outra = tmp_path / "outra"
    outra.mkdir()
    com_a_rede = dossie.ficha_do(CPFL, _com_a_rede(outra))
    assert sem_a_rede is not None and com_a_rede is not None
    assert dossie.ficha_do_molde_a(com_a_rede) == dossie.ficha_do_molde_a(sem_a_rede)


def test_ficha_so_com_o_molde_b_nao_da_dossie_ao_molde_a(tmp_path: Path) -> None:
    bruta = _bruta() | {"secoes": [SECAO_DA_REDE]}
    ficha = dossie.ficha_do(CPFL, _pasta(tmp_path, bruta))
    assert ficha is not None
    assert dossie.ficha_do_molde_a(ficha) is None
    assert dossie.ficha_do_molde_a(None) is None


def _secao_do_setor() -> dict:
    """A seção `setor` como a noite a grava (molde D, plano de 19/10/2026, PR 1)."""
    setor = next(
        s for s in dossie_da_base.SETORES_DO_LANCAMENTO if s.chave == "eletricas"
    )
    ligacoes = pd.DataFrame(
        {
            "fonte": ["aneel-samp"],
            "chave": ["33050196000188"],
            "nome": ["CPFL Paulista"],
            "cnpj_companhia": [CPFL],
            "via": ["controlada"],
            "principal": [True],
            "desde": [pd.Timestamp("2010-05-01")],
        }
    )
    consumidores = pd.DataFrame(
        {
            "ano": [2025, 2025],
            "chave": ["33050196000188", "99999999000199"],
            "valor": [110.0, 890.0],
            "meses": [12, 12],
            "ultimo_mes": [pd.Timestamp("2025-12-31")] * 2,
        }
    )
    membros = dossie_da_base.membros_do_setor(
        setor,
        pd.DataFrame({"cnpj": [CPFL], "empresa": ["CPFL ENERGIA S.A."]}),
        ligacoes,
    )
    secao = dossie_da_base.secao_setor(
        setor, membros, {"aneel_consumidores": consumidores}, ligacoes, {}
    )
    assert secao is not None
    return json.loads(json.dumps(secao, allow_nan=False))


def test_relatorio_da_empresa_ignora_a_secao_do_setor(tmp_path: Path) -> None:
    """A ficha que leva o setor abre no app, e o molde A dela fica como era (o setor é do molde D)."""
    sem_o_setor = dossie.ficha_do(CPFL, _pasta(tmp_path))
    outra = tmp_path / "outra"
    outra.mkdir()
    bruta = _bruta()
    bruta["secoes"].append(_secao_do_setor())
    com_o_setor = dossie.ficha_do(CPFL, _pasta(outra, bruta))
    assert sem_o_setor is not None and com_o_setor is not None
    assert dossie.ficha_do_molde_a(com_o_setor) == dossie.ficha_do_molde_a(sem_o_setor)
