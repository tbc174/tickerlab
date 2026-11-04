"""Carga do ESTBAN (scripts/carga_estban.py). Nada vai à internet: o ZIP vem de um dublê de `baixar`."""

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from base import estban
from base.licenca import FAMILIA_DO_ENDERECO
from base.parquet import GRAVADO, IGUAL, ler_tabela
from scripts import carga_estban
from src import rede
from src.banco import coletas
from tests.test_base_estban import LINHAS, _zip

HOJE = date(2026, 11, 4)
MODIFICADO = date(2026, 10, 13)


def _baixada(**opcoes: object) -> carga_estban.Baixada:
    return carga_estban.Baixada(_zip(**opcoes), MODIFICADO)


def test_competencias_vao_do_mes_anterior_ate_a_primeira_da_mais_nova_para_a_mais_antiga():
    competencias = carga_estban.competencias_ate(HOJE, primeira=202509)
    assert competencias == [202610, 202609, 202608, 202607, 202606, 202605, 202604,
                            202603, 202602, 202601, 202512, 202511, 202510, 202509]  # fmt: skip
    assert carga_estban.competencias_ate(date(2026, 1, 10), primeira=202511) == [
        202512,
        202511,
    ]


@pytest.mark.parametrize(
    ("cabecalho", "esperado"),
    [
        ("Tue, 13 Oct 2026 14:30:00 GMT", date(2026, 10, 13)),
        (None, HOJE),
        ("não é data", HOJE),
    ],
)
def test_data_de_modificacao_usa_o_servidor_e_na_duvida_o_dia_da_coleta(
    cabecalho, esperado
):
    assert carga_estban.data_de_modificacao(cabecalho, HOJE) == esperado


def test_carregar_grava_a_competencia_com_disponivel_em_do_servidor(tmp_path: Path):
    assert carga_estban.carregar(202512, _baixada(), tmp_path) == GRAVADO
    tabela = ler_tabela(tmp_path / "estban_agencias" / "202512.parquet")
    assert len(tabela) == len(LINHAS)
    assert set(tabela["disponivel_em"]) == {pd.Timestamp(MODIFICADO)}
    assert set(tabela["gerado_em"]) == {pd.Timestamp("2026-08-03")}


def test_baixar_de_novo_com_os_mesmos_numeros_nao_empurra_a_data_para_frente(
    tmp_path: Path,
):
    carga_estban.carregar(202512, _baixada(), tmp_path)
    depois = carga_estban.Baixada(_zip(geracao="2026-11-01"), date(2026, 11, 2))
    assert carga_estban.carregar(202512, depois, tmp_path) == IGUAL
    tabela = ler_tabela(tmp_path / "estban_agencias" / "202512.parquet")
    assert set(tabela["disponivel_em"]) == {pd.Timestamp(MODIFICADO)}


def test_numero_revisado_vira_versao_nova_com_a_data_nova(tmp_path: Path):
    carga_estban.carregar(202512, _baixada(), tmp_path)
    revisadas = [LINHAS[0].replace(";1000;", ";1500;"), *LINHAS[1:]]
    depois = carga_estban.Baixada(
        _zip(revisadas, geracao="2026-11-01"), date(2026, 11, 2)
    )
    assert carga_estban.carregar(202512, depois, tmp_path) == GRAVADO
    tabela = ler_tabela(tmp_path / "estban_agencias" / "202512.parquet")
    assert set(tabela["disponivel_em"]) == {pd.Timestamp("2026-11-02")}
    assert 1500 in set(tabela["verbete_160"])
    assert list((tmp_path / "estban_agencias").glob("202512.v*.parquet"))


def _servidor(publicadas: set[int], pedidos: list[int]):
    def baixar(url: str, hoje: date) -> carga_estban.Baixada | None:
        competencia = int(url.rsplit("/", 1)[1][:6])
        pedidos.append(competencia)
        if competencia not in publicadas:
            return None
        return carga_estban.Baixada(
            _zip(competencia=str(competencia), linhas=[
                linha.replace("202512", str(competencia)) for linha in LINHAS
            ]),
            MODIFICADO,
        )  # fmt: skip

    return baixar


def test_rodada_baixa_o_que_falta_e_so_as_6_mais_novas_publicadas_de_novo(
    tmp_path: Path,
):
    publicadas = {202512, 202511, 202510, 202509, 202508, 202507, 202506, 202505}
    pedidos: list[int] = []
    primeira = carga_estban.rodar(
        None, tmp_path, date(2027, 1, 20), _servidor(publicadas, pedidos), pausa=0
    )
    assert primeira[202512] == GRAVADO
    assert primeira[202601] == carga_estban.NAO_PUBLICADA
    assert primeira[202301] == carga_estban.NAO_PUBLICADA  # nunca publicada
    pedidos.clear()
    segunda = carga_estban.rodar(
        None, tmp_path, date(2027, 1, 20), _servidor(publicadas, pedidos), pausa=0
    )
    assert [segunda[c] for c in (202512, 202511, 202510, 202509, 202508, 202507)] == [
        IGUAL
    ] * 6
    assert segunda[202506] == segunda[202505] == carga_estban.PULADA
    assert 202506 not in pedidos


def test_competencia_que_falha_nao_derruba_as_outras(tmp_path: Path):
    def baixar(url: str, hoje: date) -> carga_estban.Baixada | None:
        if "202511" in url:
            raise OSError("rede caiu")
        return _baixada()

    resultado = carga_estban.rodar([202511, 202512], tmp_path, HOJE, baixar, pausa=0)
    assert resultado == {202511: carga_estban.FALHOU, 202512: GRAVADO}


def test_baixar_le_o_last_modified_e_trata_404_como_nao_publicada(monkeypatch):
    class Resposta:
        def __init__(self, status: int, cabecalhos: dict[str, str]):
            self.status_code = status
            self.headers = cabecalhos
            self.content = b"zip"

        def raise_for_status(self) -> None:
            assert self.status_code < 400

    registros: list[tuple[str | None, str]] = []
    monkeypatch.setattr(
        carga_estban,
        "_registrar",
        lambda url, conteudo, situacao, detalhe, agora: registros.append(
            (situacao, detalhe)
        ),
    )
    respostas = iter(
        [
            Resposta(200, {"Last-Modified": "Tue, 13 Oct 2026 14:30:00 GMT"}),
            Resposta(404, {}),
        ]
    )
    monkeypatch.setattr(rede, "get_com_agente", lambda url, **kw: next(respostas))
    baixada = carga_estban.baixar("https://x/202602_ESTBAN_AG.csv.zip", HOJE)
    assert baixada == carga_estban.Baixada(b"zip", date(2026, 10, 13))
    assert carga_estban.baixar("https://x/202607_ESTBAN_AG.csv.zip", HOJE) is None
    assert registros == [
        ("ok", "modificado no servidor em 2026-10-13"),
        ("nao_encontrado", "HTTP 404"),
    ]


def test_fonte_do_estban_tem_licenca_propria_e_so_uso_interno():
    endereco = estban.endereco_da_competencia(202602).split("://", 1)[1]
    casam = [p for p in FAMILIA_DO_ENDERECO if endereco.startswith(p)]
    assert FAMILIA_DO_ENDERECO[max(casam, key=len)] == "estban"
    assert estban.FONTE.startswith("estban")
    assert "ODbL" not in coletas.licenca_da_fonte(estban.FONTE)
    assert "a confirmar" in coletas.licenca_da_fonte(estban.FONTE)
    assert coletas.revenda_da_fonte(estban.FONTE) == coletas.A_CONFIRMAR
    assert "estban" in coletas.COLETA_E_GUARDA
