"""Carga do CNES por competência (scripts/carga_cnes.py). Nada vai à internet: a API é um dublê que pagina
por `offset` em itens, e o `rede.get_com_agente` é trocado."""

from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from base import cnes
from base.licenca import FAMILIA_DO_ENDERECO
from base.parquet import GRAVADO, IGUAL, ler_tabela
from scripts import carga_cnes
from src import rede
from src.banco import coletas

PRIMEIRA = date(2026, 11, 4)
DEPOIS = date(2026, 12, 5)


def _item(codigo: str, **campos: object) -> dict[str, object]:
    item: dict[str, object] = {
        "nu_comp": 202607,
        "co_cnes": codigo,
        "co_ibge": 330330,
        "no_empresarial": f"EMPRESA {codigo}",
        "no_fantasia": f"FANTASIA {codigo}",
        "nu_cnpj": "11222333000181",
        "nu_cnpj_mantenedora": None,
        "no_logradouro": "RUA DO SIGILO",
        "nu_telefone": "2100000000",
        "ds_email": "contato@exemplo.invalid",
    }
    item.update(campos)
    return item


def _api(itens_por_competencia: dict[int, list[dict[str, object]]]) -> cnes.Buscador:
    def buscar(competencia: int, offset: int, limit: int) -> dict[str, Any]:
        itens = itens_por_competencia.get(competencia, [])
        return {cnes.CHAVE_DA_LISTA: itens[offset : offset + limit]}

    return buscar


def test_grava_estabelecimentos_e_situacao_da_competencia(tmp_path: Path):
    api = _api({202607: [_item("1"), _item("2", nu_cnpj_mantenedora="00394460000141")]})
    resultado = carga_cnes.carregar_competencia(202607, tmp_path, PRIMEIRA, api)
    assert resultado == (GRAVADO, GRAVADO)
    tabela = ler_tabela(tmp_path / "cnes_estabelecimentos" / "202607.parquet")
    assert list(tabela["codigo_cnes"]) == ["1", "2"]
    assert tabela.loc[1, "cnpj_mantenedora"] == "00394460000141"
    situacao = ler_tabela(tmp_path / "cnes_competencias" / "202607.parquet")
    assert situacao.loc[0, "situacao"] == cnes.COMPETENCIA_COM_DADOS
    assert situacao.loc[0, "linhas"] == 2


def test_competencia_vazia_vira_registro_vazia_e_nao_grava_estabelecimentos(
    tmp_path: Path,
):
    carga_cnes.carregar_competencia(202608, tmp_path, PRIMEIRA, _api({}))
    situacao = ler_tabela(tmp_path / "cnes_competencias" / "202608.parquet")
    assert situacao.loc[0, "situacao"] == cnes.COMPETENCIA_VAZIA
    assert situacao.loc[0, "linhas"] == 0
    estabelecimentos = ler_tabela(tmp_path / "cnes_estabelecimentos" / "202608.parquet")
    assert estabelecimentos.empty
    assert list(estabelecimentos.columns) == list(cnes.COLUNAS)


def test_endereco_telefone_e_email_nunca_entram(tmp_path: Path):
    carga_cnes.carregar_competencia(
        202607, tmp_path, PRIMEIRA, _api({202607: [_item("1")]})
    )
    colunas = ler_tabela(tmp_path / "cnes_estabelecimentos" / "202607.parquet").columns
    assert not {"no_logradouro", "nu_telefone", "ds_email"} & set(colunas)


def test_pessoa_fisica_sem_cnpj_fica_sem_nome(tmp_path: Path):
    pessoa = _item("9", nu_cnpj=None, nu_cnpj_mantenedora=None)
    carga_cnes.carregar_competencia(
        202607, tmp_path, PRIMEIRA, _api({202607: [pessoa]})
    )
    linha = ler_tabela(tmp_path / "cnes_estabelecimentos" / "202607.parquet").iloc[0]
    assert linha["razao_social"] == "" and linha["nome_fantasia"] == ""


def test_olhar_de_novo_sem_dado_novo_nao_empurra_a_data_para_frente(tmp_path: Path):
    api = _api({202607: [_item("1")]})
    carga_cnes.carregar_competencia(202607, tmp_path, PRIMEIRA, api)
    resultado = carga_cnes.carregar_competencia(202607, tmp_path, DEPOIS, api)
    assert resultado == (IGUAL, IGUAL)
    tabela = ler_tabela(tmp_path / "cnes_estabelecimentos" / "202607.parquet")
    assert tabela.loc[0, "disponivel_em"] == pd.Timestamp(PRIMEIRA)


def test_competencia_que_estava_vazia_e_agora_tem_dados_vale_a_coleta_nova(
    tmp_path: Path,
):
    carga_cnes.carregar_competencia(202608, tmp_path, PRIMEIRA, _api({}))
    api = _api({202608: [_item("1", nu_comp=202608)]})
    resultado = carga_cnes.carregar_competencia(202608, tmp_path, DEPOIS, api)
    assert resultado == (GRAVADO, GRAVADO)
    situacao = ler_tabela(tmp_path / "cnes_competencias" / "202608.parquet")
    assert situacao.loc[0, "situacao"] == cnes.COMPETENCIA_COM_DADOS
    assert situacao.loc[0, "coletado_em"] == pd.Timestamp(DEPOIS)


def test_dado_que_mudou_guarda_a_versao_anterior(tmp_path: Path):
    carga_cnes.carregar_competencia(
        202607, tmp_path, PRIMEIRA, _api({202607: [_item("1")]})
    )
    novo = _api({202607: [_item("1", no_empresarial="OUTRO NOME")]})
    assert carga_cnes.carregar_competencia(202607, tmp_path, DEPOIS, novo)[0] == GRAVADO
    tabela = ler_tabela(tmp_path / "cnes_estabelecimentos" / "202607.parquet")
    assert tabela.loc[0, "razao_social"] == "OUTRO NOME"


def test_competencias_recentes_viram_o_ano_e_voltam_meses():
    assert carga_cnes.competencias_recentes(date(2026, 11, 4)) == [
        202609,
        202610,
        202611,
    ]
    assert carga_cnes.competencias_recentes(date(2026, 2, 1), 3) == [
        202512,
        202601,
        202602,
    ]


def test_a_api_e_pedida_pelo_agente_do_tickerlab(monkeypatch: pytest.MonkeyPatch):
    pedidos: list[tuple[str, dict[str, Any]]] = []

    class Resposta:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {cnes.CHAVE_DA_LISTA: []}

    def falso(url: str, *args: object, **kwargs: Any) -> Resposta:
        pedidos.append((url, kwargs))
        return Resposta()

    monkeypatch.setattr(rede, "get_com_agente", falso)
    assert carga_cnes.buscar_na_api(202607, 2000, 1000) == {cnes.CHAVE_DA_LISTA: []}
    url, kwargs = pedidos[0]
    assert url == cnes.URL_DA_API
    assert kwargs["params"] == {"nu_comp": 202607, "offset": 2000, "limit": 1000}
    assert kwargs["timeout"] == carga_cnes.TEMPO_LIMITE


def test_fonte_do_cnes_e_a_confirmar_e_so_uso_interno():
    endereco = cnes.URL_DA_API.removeprefix("https://")
    familia = next(f for p, f in FAMILIA_DO_ENDERECO.items() if endereco.startswith(p))
    assert familia == "ms"
    assert cnes.FONTE.startswith(familia)
    assert "a confirmar" in coletas.licenca_da_fonte(cnes.FONTE)
    assert coletas.revenda_da_fonte(cnes.FONTE) == coletas.A_CONFIRMAR


def test_carga_pelo_ftp_grava_com_origem_do_ftp(tmp_path: Path):
    from tests.test_base_dbc import CAMPOS, HOSPITAL, _registro, montar_dbc

    def baixar(uf: str, competencia: int) -> bytes:
        return montar_dbc(
            CAMPOS, [_registro(f"{cnes.UFS.index(uf) + 1:07d}", HOSPITAL)]
        )

    resultado = carga_cnes.carregar_competencia(
        202608, tmp_path, PRIMEIRA, fonte=carga_cnes.FONTE_FTP, baixar=baixar
    )
    assert resultado == (GRAVADO, GRAVADO)
    tabela = ler_tabela(tmp_path / "cnes_estabelecimentos" / "202608.parquet")
    assert len(tabela) == len(cnes.UFS)
    assert carga_cnes._origem(202608, carga_cnes.FONTE_FTP)["url"].startswith("ftp://")


def test_carga_pelo_ftp_de_competencia_nao_publicada_registra_vazia(tmp_path: Path):
    def baixar(uf: str, competencia: int) -> bytes:
        raise FileNotFoundError(uf)

    carga_cnes.carregar_competencia(
        202609, tmp_path, PRIMEIRA, fonte=carga_cnes.FONTE_FTP, baixar=baixar
    )
    situacao = ler_tabela(tmp_path / "cnes_competencias" / "202609.parquet")
    assert situacao.loc[0, "situacao"] == cnes.COMPETENCIA_VAZIA
