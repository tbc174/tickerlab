"""O quadro de sócios virado (linha 1032): de quais empresas uma PJ é sócia, e desde quando. Monta junto com as
entradas de sócio PJ (`scripts/montar_entradas_de_socio_pj.py`), só sócia pessoa jurídica. Dados de mentira."""

from datetime import date
from pathlib import Path

import pandas as pd

from base import dossie, socios_pj
from base.porta import Porta, vista_do_cnpj
from base.porta.duckdb import arquivos_da_tabela, dia_de, nome_da_view
from scripts import montar_entradas_de_socio_pj as script
from tests.test_montar_entradas_de_socio_pj import (
    EMPRESA,
    FUNDO,
    HOLDING,
    _acervo,
    _linha,
    _mes_seguinte,
    _rodar,
)

COLUNAS = [
    "raiz_socio_pj",
    "cnpj_basico",
    "data_entrada",
    "qualificacao",
    "mes_do_retrato",
    "disponivel_em",
]


def _quadro(destino: Path) -> pd.DataFrame:
    arquivos = arquivos_da_tabela(destino / socios_pj.QUADRO_INVERTIDO, "*.parquet")
    return pd.concat([pd.read_parquet(a) for a in arquivos], ignore_index=True)


def test_so_socia_pessoa_juridica_da_lista_e_nunca_de_si_mesma():
    fora, mei = "55555555", "66666666"
    vigente = pd.DataFrame(
        [
            _linha(EMPRESA, "1", HOLDING, "", "2015-03-02"),
            _linha(EMPRESA, "2", "", "pseudonimo-1", "2010-01-01"),  # pessoa física
            _linha(EMPRESA, "3", "", "", "2010-01-01"),  # sócio no exterior, sem CNPJ
            _linha(EMPRESA, "1", EMPRESA, "", "2012-01-01"),  # sócia de si mesma
            _linha(EMPRESA, "1", fora, "", "2011-01-01"),  # sócia fora da lista
            _linha(mei, "1", HOLDING, "", "2011-01-01"),  # empresa fora da lista
        ]
    )
    tabela = socios_pj.quadro_invertido(vigente, "2023-06", {EMPRESA, HOLDING})
    assert list(tabela.columns) == COLUNAS
    assert tabela.to_dict("records") == [
        {
            "raiz_socio_pj": HOLDING,
            "cnpj_basico": EMPRESA,
            "data_entrada": pd.Timestamp("2015-03-02"),
            "qualificacao": "22",
            "mes_do_retrato": "2023-06",
            "disponivel_em": pd.Timestamp("2023-06-21"),
        }
    ]


def test_socia_repetida_fica_uma_vez_com_a_entrada_mais_antiga():
    vigente = pd.DataFrame(
        [
            _linha(EMPRESA, "1", HOLDING, "", "2020-05-05"),
            _linha(EMPRESA, "1", HOLDING, "", "2015-03-02"),
        ]
    )
    tabela = socios_pj.quadro_invertido(vigente, "2023-06", {EMPRESA, HOLDING})
    assert list(tabela["data_entrada"]) == [pd.Timestamp("2015-03-02")]


def test_grava_o_quadro_repartido_pela_raiz_da_socia_sem_pessoa(tmp_path):
    cnpj, destino = _acervo(tmp_path)
    assert _rodar(cnpj, destino) == 0
    pasta = destino / socios_pj.QUADRO_INVERTIDO
    assert sorted(a.name for a in pasta.glob("*.parquet")) == [
        "11.parquet",
        "33.parquet",
    ]
    tabela = _quadro(destino)
    assert sorted(zip(tabela["raiz_socio_pj"], tabela["cnpj_basico"], strict=True)) == [
        (HOLDING, EMPRESA),
        (FUNDO, EMPRESA),
    ]
    assert "id_pessoa" not in tabela.columns
    assert not tabela.astype(str).isin(["pseudonimo-1"]).any().any()


def test_quem_saiu_nao_fica_no_quadro_nem_no_arquivo_da_socia(tmp_path):
    cnpj, destino = _acervo(tmp_path)
    assert _rodar(cnpj, destino) == 0
    vigente = cnpj / "vigente" / "qsa" / "11.parquet"
    atual = pd.read_parquet(vigente)
    atual[atual["raiz_socio_pj"] != FUNDO].to_parquet(vigente, index=False)
    assert _rodar(cnpj, destino) == 0
    assert set(_quadro(destino)["raiz_socio_pj"]) == {HOLDING}
    # o prefixo que ficou sem sócia vira arquivo vazio (a versão anterior fica guardada, ADR 0078)
    assert pd.read_parquet(destino / socios_pj.QUADRO_INVERTIDO / "33.parquet").empty


def test_deixa_na_base_do_cnpj_o_qsa_virado_que_a_ficha_le(tmp_path):
    cnpj, destino = _acervo(tmp_path)
    assert _rodar(cnpj, destino) == 0
    achadas = vista_do_cnpj.participacoes_da_raiz(cnpj, HOLDING)
    assert list(achadas.columns) == list(vista_do_cnpj.COLUNAS_DAS_PARTICIPACOES)
    assert list(achadas["cnpj_basico"]) == [EMPRESA]


def test_ensaio_nao_grava_o_quadro_nem_o_qsa_virado(tmp_path):
    cnpj, destino = _acervo(tmp_path)
    assert _rodar(cnpj, destino, "--ensaio") == 0
    assert not (destino / socios_pj.QUADRO_INVERTIDO).exists()
    assert not (cnpj / "vigente" / vista_do_cnpj.PARTICIPACOES).exists()


def test_mes_novo_com_defeito_deixa_o_quadro_como_estava(tmp_path, monkeypatch):
    cnpj, destino = _acervo(tmp_path)
    assert _rodar(cnpj, destino) == 0
    antes = _quadro(destino)
    _mes_seguinte(cnpj, destino)
    monkeypatch.setitem(script.MAXIMO_POR_MES, "entrou", 0)
    assert _rodar(cnpj, destino) == 1
    pd.testing.assert_frame_equal(_quadro(destino), antes)


def test_mes_novo_leva_o_quadro_e_o_qsa_virado(tmp_path):
    cnpj, destino = _acervo(tmp_path)
    assert _rodar(cnpj, destino) == 0
    _mes_seguinte(cnpj, destino)
    assert _rodar(cnpj, destino, "--se-houver-mes-novo") == 0
    assert set(_quadro(destino)["mes_do_retrato"]) == {"2023-07"}
    assert "44444444" in set(_quadro(destino)["raiz_socio_pj"])
    assert not vista_do_cnpj.participacoes_da_raiz(cnpj, "44444444").empty
    # a porta lê só o quadro vigente, sem as versões guardadas do mês anterior
    view = '"' + nome_da_view(socios_pj.QUADRO_INVERTIDO) + '"'
    linhas = Porta(destino).con.execute(f"SELECT count(*) FROM {view}").fetchone()
    assert linhas == (3,)


def test_o_cron_monta_o_que_falta_mesmo_sem_mes_novo(tmp_path, capsys):
    """As entradas já têm o mês, mas o quadro ainda não existe (primeira vez) ou a carga trocou o vigente do
    CNPJ e levou o QSA virado: o cron diário remonta."""
    cnpj, destino = _acervo(tmp_path)
    assert _rodar(cnpj, destino) == 0
    for pasta in (
        destino / socios_pj.QUADRO_INVERTIDO,
        cnpj / "vigente" / vista_do_cnpj.PARTICIPACOES,
    ):
        for arquivo in pasta.iterdir():
            arquivo.unlink()
        pasta.rmdir()
        assert _rodar(cnpj, destino, "--se-houver-mes-novo") == 0
        assert "nada a fazer" not in capsys.readouterr().out
        assert pasta.is_dir()
    assert _rodar(cnpj, destino, "--se-houver-mes-novo") == 0
    assert "nada a fazer" in capsys.readouterr().out


def test_a_porta_nao_mostra_o_quadro_antes_de_ele_ser_publico(tmp_path):
    """Sem olhar o futuro: o quadro é o do retrato de 2023-06; num dia anterior ele não existe."""
    cnpj, destino = _acervo(tmp_path)
    assert _rodar(cnpj, destino) == 0
    porta = Porta(destino)

    def empresas(dia: date) -> list[str]:
        view = '"' + nome_da_view(socios_pj.QUADRO_INVERTIDO) + '"'
        achadas = porta.con.execute(
            f"SELECT cnpj_basico FROM {view} WHERE raiz_socio_pj = $raiz "
            "AND publico_em <= CAST($dia AS DATE)",
            {"raiz": HOLDING, "dia": dia_de(dia)},
        ).df()
        return list(achadas["cnpj_basico"])

    assert empresas(date(2023, 6, 20)) == []
    assert empresas(date(2023, 6, 30)) == [EMPRESA]


def test_o_quadro_nao_sai_na_consulta_aberta():
    """Linha 1032: tabela nova com CNPJ fica fora da API aberta e da página Dados."""
    assert dossie.e_do_cnpj(socios_pj.QUADRO_INVERTIDO)
    assert not dossie.pode_consultar(socios_pj.QUADRO_INVERTIDO)
