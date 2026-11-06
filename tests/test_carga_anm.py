"""Carga da ANM (scripts/carga_anm.py). Nada vai à internet: o download é um dublê que devolve os arquivos de
`dados_de_exemplo/anm`, e o `rede.get_com_agente` é trocado onde o agente é testado."""

from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from base import anm
from base.parquet import GRAVADO, IGUAL, ler_tabela
from scripts import carga_anm
from src import rede
from src.banco import coletas

PASTA = Path(__file__).parent.parent / "dados_de_exemplo" / "anm"
PRIMEIRA = date(2026, 11, 4)
DEPOIS = date(2026, 12, 5)
ARQUIVOS = {
    "cfem": (PASTA / "cfem_arrecadacao.csv").read_bytes(),
    "sigbm": (PASTA / "sigbm_barragens.csv").read_bytes(),
    "bruta": (PASTA / "amb_producao_bruta.csv").read_bytes(),
    "beneficiada": (PASTA / "amb_producao_beneficiada.csv").read_bytes(),
    "agua": (PASTA / "amb_agua_mineral.csv").read_bytes(),
}


def _download(arquivos: dict[str, bytes]):
    def baixar(url: str) -> bytes:
        for sufixo, conteudo in (
            ("CFEM_Arrecadacao_2022_2026.csv", arquivos["cfem"]),
            ("Barragens.csv", arquivos["sigbm"]),
            ("Producao_Bruta.csv", arquivos["bruta"]),
            ("Producao_Beneficiada.csv", arquivos["beneficiada"]),
            ("Agua_Mineral_Producao.csv", arquivos["agua"]),
        ):
            if url.endswith(sufixo):
                return conteudo
        raise AssertionError(f"endereço inesperado: {url}")

    return baixar


def _carregar(
    grupo: str, saida: Path, quando: date, arquivos: dict[str, bytes] | None = None
):
    baixar = _download(arquivos or ARQUIVOS)
    resultados = {}
    for tabela in carga_anm.tabelas_pedidas(["2022_2026"], [grupo], quando):
        if tabela.grupo == "cfem" and not tabela.url.endswith("2022_2026.csv"):
            continue
        resultados[tabela.nome] = carga_anm.carregar(tabela, saida, quando, baixar)
    return resultados


def test_cfem_grava_so_pessoa_juridica_e_a_data_da_linha(tmp_path: Path):
    resultado = _carregar("cfem", tmp_path, PRIMEIRA)
    assert resultado == {"anm_cfem_arrecadacao/2022_2026": GRAVADO}
    tabela = ler_tabela(tmp_path / "anm_cfem_arrecadacao" / "2022_2026.parquet")
    assert list(tabela.columns) == list(anm.COLUNAS_CFEM)
    assert (tabela["cnpj"].str.len() == 14).all()
    com_data = tabela["criado_em"].notna()
    assert (
        tabela.loc[com_data, "disponivel_em"] == tabela.loc[com_data, "criado_em"]
    ).all()
    # sem data na linha, vale a coleta
    assert (tabela.loc[~com_data, "disponivel_em"] == pd.Timestamp(PRIMEIRA)).all()


def test_sigbm_grava_as_barragens_com_o_cnpj_do_empreendedor(tmp_path: Path):
    _carregar("sigbm", tmp_path, PRIMEIRA)
    tabela = ler_tabela(tmp_path / "anm_sigbm_barragens" / "barragens.parquet")
    assert list(tabela.columns) == list(anm.COLUNAS_SIGBM)
    assert (tabela["disponivel_em"] == pd.Timestamp(PRIMEIRA)).all()


def test_amb_grava_as_tres_series_sem_cnpj(tmp_path: Path):
    resultado = _carregar("amb", tmp_path, PRIMEIRA)
    assert set(resultado.values()) == {GRAVADO} and len(resultado) == 3
    for pasta in ("producao_bruta", "producao_beneficiada", "agua_mineral"):
        tabela = ler_tabela(tmp_path / f"anm_amb_{pasta}" / "atual.parquet")
        assert not tabela.empty and "cnpj" not in tabela.columns


def test_olhar_de_novo_o_mesmo_arquivo_nao_regrava_nem_empurra_a_data(tmp_path: Path):
    _carregar("sigbm", tmp_path, PRIMEIRA)
    resultado = _carregar("sigbm", tmp_path, DEPOIS)
    assert set(resultado.values()) == {IGUAL}
    tabela = ler_tabela(tmp_path / "anm_sigbm_barragens" / "barragens.parquet")
    assert (tabela["disponivel_em"] == pd.Timestamp(PRIMEIRA)).all()


def test_barragem_nova_vale_a_coleta_nova_e_as_antigas_mantem_a_data(tmp_path: Path):
    _carregar("sigbm", tmp_path, PRIMEIRA)
    cabecalho, *linhas = ARQUIVOS["sigbm"].decode("cp1252").splitlines()
    mudada = linhas[0].replace("Fictícia 1", "Fictícia 1 (renomeada)")
    novo = "\r\n".join([cabecalho, mudada, *linhas[1:]]) + "\r\n"
    arquivos = {**ARQUIVOS, "sigbm": novo.encode("cp1252")}
    assert set(_carregar("sigbm", tmp_path, DEPOIS, arquivos).values()) == {GRAVADO}
    tabela = ler_tabela(tmp_path / "anm_sigbm_barragens" / "barragens.parquet")
    datas = list(tabela["disponivel_em"])
    assert datas[0] == pd.Timestamp(DEPOIS)  # a linha que mudou
    assert all(d == pd.Timestamp(PRIMEIRA) for d in datas[1:])  # as que ficaram iguais


def test_faixa_do_cfem_contem_o_ano_e_as_recentes_sao_a_do_ano_e_a_anterior():
    assert carga_anm.faixa_do_ano(2026) == "2022_2026"
    assert carga_anm.faixa_do_ano(2002) == "2002_2006"
    assert carga_anm.faixa_do_ano(2011) == "2007_2011"
    assert carga_anm.faixas_recentes(date(2026, 11, 4)) == ["2017_2021", "2022_2026"]
    assert carga_anm.faixas_recentes(date(2027, 1, 5), 1) == ["2027_2031"]


def test_a_rodada_padrao_pede_duas_faixas_do_cfem_e_as_demais_tabelas():
    nomes = [t.nome for t in carga_anm.tabelas_pedidas([], None, PRIMEIRA)]
    assert nomes[:2] == [
        "anm_cfem_arrecadacao/2017_2021",
        "anm_cfem_arrecadacao/2022_2026",
    ]
    assert len(nomes) == 6
    so_sigbm = [t.nome for t in carga_anm.tabelas_pedidas([], ["sigbm"], PRIMEIRA)]
    assert so_sigbm == ["anm_sigbm_barragens/barragens"]


def test_o_download_e_pedido_pelo_agente_do_tickerlab(monkeypatch: pytest.MonkeyPatch):
    pedidos: list[tuple[str, dict[str, Any]]] = []

    class Resposta:
        content = b"abc"

        def raise_for_status(self) -> None:
            return None

    def falso(url: str, *_args: object, **kwargs: Any) -> Resposta:
        pedidos.append((url, kwargs))
        return Resposta()

    monkeypatch.setattr(rede, "get_com_agente", falso)
    assert carga_anm.baixar(carga_anm.URL_SIGBM) == b"abc"
    assert pedidos[0][0] == "https://dadosabertos.anm.gov.br/SIGBM/Barragens.csv"
    assert pedidos[0][1]["timeout"] == carga_anm.TEMPO_LIMITE


@pytest.mark.parametrize(
    "fonte",
    [
        anm.FONTE_CFEM,
        anm.FONTE_SIGBM,
        anm.FONTE_AMB_BRUTA,
        anm.FONTE_AMB_BENEFICIADA,
        anm.FONTE_AMB_AGUA,
    ],
)
def test_as_fontes_da_anm_sao_vendaveis_por_risco_assumido(fonte: str):
    assert "risco assumido (ADR 0122)" in coletas.licenca_da_fonte(fonte)
    assert coletas.revenda_da_fonte(fonte) == coletas.VENDAVEL_RISCO_ASSUMIDO


def test_o_cadastro_mineiro_continua_com_a_licenca_propria():
    assert "CC BY" in coletas.licenca_da_fonte("anm-cadastro-mineiro")
    assert (
        coletas.revenda_da_fonte("anm-cadastro-mineiro")
        == coletas.VENDAVEL_COM_ATRIBUICAO
    )
