"""`Porta.ler` pela faixa (linha 1015, item e, PR 5): a lista de valores vai em parâmetros soltos (o DuckDB pula os
grupos de linhas pelo rodapé do Parquet) e, na lista de empresas da Receita (gravada em arquivos por faixa de
`cnpj_basico`), só os arquivos cuja faixa cobre as raízes pedidas são lidos. Sempre o mesmo resultado da visão.
Base de mentira, sem nome de pessoa."""

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from base import porta as porta_
from base.porta import METADADOS, Porta, _igualdades

TABELA = "cnpj_empresas_pj"
# raízes de mentira em quatro arquivos, como a lista da Receita: um arquivo por faixa, em ordem de `cnpj_basico`
FAIXAS = {
    "00": ["00000001", "00000002", "00500000"],
    "11": ["11000000", "11000001", "11999999"],
    "22": ["22000000", "22222222"],
    "33": ["33000000", "33000001", "33000002", "33999999"],
}
TODAS = [raiz for raizes in FAIXAS.values() for raiz in raizes]
FORA = ["00000000", "05000000", "11500000", "44000000", "99999999"]


def _empresas(raizes: list[str], *, com_capital: bool = True) -> pd.DataFrame:
    tabela = pd.DataFrame(
        {
            "cnpj_basico": raizes,
            "razao_social": [f"EMPRESA DE MENTIRA {r[-3:]} LTDA" for r in raizes],
            "natureza_juridica": "2062",
            "mes_do_retrato": "2026-10",
            "disponivel_em": "2026-10-15",
        }
    )
    if com_capital:
        tabela["capital_social"] = 1000.0
    return tabela


def _gravar(pasta, nome: str, tabela: pd.DataFrame, **opcoes) -> None:
    arquivo = pasta / TABELA / f"{nome}.parquet"
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(
        pa.Table.from_pandas(tabela, preserve_index=False), arquivo, **opcoes
    )


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    pasta = tmp_path_factory.mktemp("base")
    for nome, raizes in FAIXAS.items():
        _gravar(pasta, nome, _empresas(raizes))
    return pasta


class _Anotadora:
    """A conexão de verdade, anotando o texto de cada consulta."""

    def __init__(self, con) -> None:
        self._con, self.consultas = con, []

    def execute(self, sql, *argumentos):
        self.consultas.append(sql)
        return self._con.execute(sql, *argumentos)

    def __getattr__(self, nome):
        return getattr(self._con, nome)


def _pela_visao(monkeypatch, porta: Porta, **pedido) -> pd.DataFrame:
    with monkeypatch.context() as m:
        m.setattr(porta_, "POR_FAIXA_DE_ARQUIVO", {})
        m.setattr(porta_, "LISTA_SOLTA", 0)
        return porta.ler(TABELA, **pedido)


def _ordenada(tabela: pd.DataFrame) -> pd.DataFrame:
    return tabela.sort_values("cnpj_basico").reset_index(drop=True)


# ---------------------------------------------------------------- lista em parâmetros soltos


def test_lista_curta_vai_em_parametros_soltos():
    condicoes, parametros = _igualdades({"cnpj_basico": ["a", "b"], "mes": "x"}, "f")
    assert condicoes == ['"cnpj_basico" IN ($f0_0, $f0_1)', '"mes" = $f1']
    assert parametros == {"f0_0": "a", "f0_1": "b", "f1": "x"}


def test_lista_vazia_nao_deixa_linha_nenhuma(base):
    assert _igualdades({"cnpj_basico": []}, "f") == (["false"], {})
    with Porta(base) as porta:
        assert porta.ler(TABELA, filtros={"cnpj_basico": []}).empty


def test_lista_longa_segue_pelo_unnest(monkeypatch):
    monkeypatch.setattr(porta_, "LISTA_SOLTA", 2)
    condicoes, parametros = _igualdades({"cnpj_basico": ["a", "b", "c"]}, "f")
    assert condicoes == ['"cnpj_basico" IN (SELECT unnest($f0))']
    assert parametros == {"f0": ["a", "b", "c"]}


# ---------------------------------------------------------------- só os arquivos da faixa


def test_le_so_os_arquivos_da_faixa_pedida(base):
    with Porta(base) as porta:
        porta.con = _Anotadora(porta.con)
        lidas = porta.ler(TABELA, filtros={"cnpj_basico": ["11000001", "33000002"]})
        consulta = porta.con.consultas[-1]
    assert sorted(lidas["cnpj_basico"]) == ["11000001", "33000002"]
    assert "11.parquet" in consulta and "33.parquet" in consulta
    assert "00.parquet" not in consulta and "22.parquet" not in consulta


@settings(
    max_examples=150,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    pedidas=st.lists(st.sampled_from(TODAS + FORA), max_size=12),
    uma_so=st.booleans(),
    com_dia=st.booleans(),
    com_colunas=st.booleans(),
)
def test_pela_faixa_da_o_mesmo_que_a_visao(
    monkeypatch, base, pedidas, uma_so, com_dia, com_colunas
):
    pedido = {
        "filtros": {
            "cnpj_basico": (pedidas[0] if pedidas else "00000001")
            if uma_so
            else pedidas,
            "mes_do_retrato": "2026-10",
        },
        "como_era_em": "2026-11-19" if com_dia else None,
        "colunas": ["cnpj_basico", "razao_social", "publico_em"]
        if com_colunas
        else None,
    }
    with Porta(base) as porta:
        pela_faixa = porta.ler(TABELA, **pedido)
        pela_visao = _pela_visao(monkeypatch, porta, **pedido)
    pd.testing.assert_frame_equal(_ordenada(pela_faixa), _ordenada(pela_visao))


def test_nada_publico_no_dia_continua_fora(base):
    with Porta(base) as porta:
        antes = porta.ler(
            TABELA, como_era_em="2026-09-30", filtros={"cnpj_basico": ["11000001"]}
        )
    assert antes.empty


def test_arquivo_sem_faixa_no_rodape_e_sempre_lido(tmp_path):
    for nome, raizes in FAIXAS.items():
        _gravar(tmp_path, nome, _empresas(raizes), write_statistics=nome != "22")
    with Porta(tmp_path) as porta:
        porta.con = _Anotadora(porta.con)
        lidas = porta.ler(TABELA, filtros={"cnpj_basico": ["22222222", "33000000"]})
        consulta = porta.con.consultas[-1]
    assert sorted(lidas["cnpj_basico"]) == ["22222222", "33000000"]
    assert "22.parquet" in consulta and "00.parquet" not in consulta


def test_arquivos_de_colunas_diferentes_voltam_para_a_visao(monkeypatch, tmp_path):
    """Um arquivo sem uma coluna: a leitura pela faixa daria outras colunas; lê pela visão (a coluna vem vazia)."""
    for nome, raizes in FAIXAS.items():
        _gravar(tmp_path, nome, _empresas(raizes, com_capital=nome != "11"))
    pedido = {"filtros": {"cnpj_basico": ["11000000"]}}  # só o arquivo sem a coluna
    with Porta(tmp_path) as porta:
        porta.con = _Anotadora(porta.con)
        pela_faixa = porta.ler(TABELA, **pedido)
        consulta = porta.con.consultas[-1]
        pela_visao = _pela_visao(monkeypatch, porta, **pedido)
    pd.testing.assert_frame_equal(_ordenada(pela_faixa), _ordenada(pela_visao))
    assert "read_parquet" not in consulta
    assert pela_faixa["capital_social"].isna().all()
    # com outro arquivo que tem a coluna, as colunas são as da view, e a faixa vale
    with Porta(tmp_path) as porta:
        porta.con = _Anotadora(porta.con)
        pela_faixa = porta.ler(
            TABELA, filtros={"cnpj_basico": ["11000000", "22000000"]}
        )
        assert "read_parquet" in porta.con.consultas[-1]
        pela_visao = _pela_visao(
            monkeypatch, porta, filtros={"cnpj_basico": ["11000000", "22000000"]}
        )
    pd.testing.assert_frame_equal(_ordenada(pela_faixa), _ordenada(pela_visao))


def test_as_faixas_ficam_na_memoria_da_base(base):
    with Porta(base) as porta:
        porta.memoria_da_base = {}
        porta.ler(TABELA, filtros={"cnpj_basico": ["11000001"]})
        porta.memoria_da_base.pop("outra coisa", None)
        porta.con = _Anotadora(porta.con)
        porta.ler(TABELA, filtros={"cnpj_basico": ["22000000"]})
        assert not any("parquet_metadata" in c for c in porta.con.consultas)
        assert any(
            isinstance(chave, tuple) and chave[0] == "faixas"
            for chave in porta.memoria_da_base[METADADOS]
        )


def test_so_tabela_que_nao_e_da_rede_le_pela_faixa():
    """A rede (`entidades`, `identificadores`, `ligacoes`) tem a vista sem pessoa montada sobre outra tabela: a
    leitura pela faixa nunca vale para ela."""
    assert not set(porta_.POR_FAIXA_DE_ARQUIVO) & {
        "entidades",
        "identificadores",
        "ligacoes",
    }
    for tabela, coluna in porta_.POR_FAIXA_DE_ARQUIVO.items():
        assert coluna in porta_.TABELAS[tabela].chaves


@pytest.mark.parametrize(
    "pedidas",
    [["11000000", None], ["11000000", 11000000], [None], ["22000000", "22000000"]],
)
def test_lista_com_vazio_tipos_misturados_ou_repetidos_da_o_mesmo_que_a_visao(
    monkeypatch, base, pedidas
):
    """Achado da revisão cruzada: a lista com vazio quebrava ao ordenar. Vazio e tipos misturados leem pela view e
    seguem pelo unnest, como antes."""
    with Porta(base) as porta:
        porta.con = _Anotadora(porta.con)
        pela_faixa = porta.ler(TABELA, filtros={"cnpj_basico": pedidas})
        consulta = porta.con.consultas[-1]
        pela_visao = _pela_visao(monkeypatch, porta, filtros={"cnpj_basico": pedidas})
    pd.testing.assert_frame_equal(_ordenada(pela_faixa), _ordenada(pela_visao))
    if len({type(v) for v in pedidas}) > 1:
        assert "unnest" in consulta and "read_parquet" not in consulta


def test_lista_de_um_tipo_so_vai_solta_e_misturada_segue_pelo_unnest():
    assert _igualdades({"c": [1, 2]}, "f")[0] == ['"c" IN ($f0_0, $f0_1)']
    assert _igualdades({"c": ["a", None]}, "f")[0] == ['"c" IN (SELECT unnest($f0))']
    assert _igualdades({"c": ["a", 1]}, "f")[0] == ['"c" IN (SELECT unnest($f0))']


def test_tipo_diferente_entre_arquivos_volta_para_a_visao(monkeypatch, tmp_path):
    """O union_by_name de só um pedaço dos arquivos daria outro tipo à coluna: lê pela view."""
    for nome, raizes in FAIXAS.items():
        tabela = _empresas(raizes)
        if nome == "11":
            tabela["capital_social"] = tabela["capital_social"].astype("int64")
        _gravar(tmp_path, nome, tabela)
    pedido = {"filtros": {"cnpj_basico": ["11000000"]}}
    with Porta(tmp_path) as porta:
        porta.con = _Anotadora(porta.con)
        pela_faixa = porta.ler(TABELA, **pedido)
        assert "read_parquet" not in porta.con.consultas[-1]
        pela_visao = _pela_visao(monkeypatch, porta, **pedido)
    pd.testing.assert_frame_equal(pela_faixa, pela_visao)


def test_coluna_com_outra_caixa_no_arquivo_continua_lida(monkeypatch, tmp_path):
    """O DuckDB junta `CNPJ_BASICO` e `cnpj_basico` pelo nome sem caixa: a faixa do rodapé também."""
    for nome, raizes in FAIXAS.items():
        tabela = _empresas(raizes)
        if nome == "22":
            tabela = tabela.rename(columns={"cnpj_basico": "CNPJ_BASICO"})
        _gravar(tmp_path, nome, tabela)
    pedido = {"filtros": {"cnpj_basico": ["22222222", "33000000"]}}
    with Porta(tmp_path) as porta:
        pela_faixa = porta.ler(TABELA, **pedido)
        pela_visao = _pela_visao(monkeypatch, porta, **pedido)
    pd.testing.assert_frame_equal(_ordenada(pela_faixa), _ordenada(pela_visao))
    assert sorted(pela_faixa["cnpj_basico"]) == ["22222222", "33000000"]
