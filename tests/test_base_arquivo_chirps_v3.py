"""CHIRPS v3 `rnl` pela cópia Zarr (base/arquivo/chirps_v3.py). Nada vai à internet: um Zarr pequeno
é montado em memória e servido por um dublê do cliente."""

import json
from datetime import UTC, date, datetime

import numpy as np
import pytest
import requests
import zstandard

from base.arquivo import chirps_v3 as v3
from base.arquivo import fontes
from base.arquivo.coleta import Resposta, SemArquivo
from base.arquivo.destinos import DESTINOS
from base.arquivo.registro import TERMOS_LIDOS_EM
from base.commodities import clima_regiao
from src.banco.coletas import Marca, licenca_da_fonte, marca_da_fonte

ORIGEM = date(1980, 1, 1)
PRIMEIRO_DIA = date(2026, 1, 1)
DIAS = 70  # até 11/03/2026: janeiro e fevereiro inteiros, março pela metade
FORMA = (DIAS, 12, 16)
PEDACO = (
    32,
    8,
    8,
)  # fevereiro cruza dois pedaços de tempo; a janela cruza dois de lat e de lon
JANELA = v3.Janela(lat_norte=-7.0, lat_sul=-7.6, lon_oeste=-40.0, lon_leste=-39.2)
LAT = -7.0 - 0.05 * (np.arange(FORMA[1]) + 0.5)  # 12 centros: -7.025 a -7.575
LON = -40.0 + 0.05 * (np.arange(FORMA[2]) + 0.5)  # 16 centros: -39.975 a -39.225


def _zarr_json(forma, pedaco, tipo, atributos, nomes, preenchimento=0, codecs=None):
    return json.dumps(
        {
            "shape": list(forma),
            "data_type": tipo,
            "chunk_grid": {
                "name": "regular",
                "configuration": {"chunk_shape": list(pedaco)},
            },
            "fill_value": preenchimento,
            "codecs": codecs
            or [
                {"name": "bytes", "configuration": {"endian": "little"}},
                {"name": "zstd"},
            ],
            "attributes": atributos,
            "dimension_names": nomes,
            "node_type": "array",
        }
    ).encode()


def _comprimir(matriz: np.ndarray, dtype: str) -> bytes:
    return zstandard.ZstdCompressor().compress(matriz.astype(dtype).tobytes())


def _chuva() -> np.ndarray:
    """Todo dia, em cada pixel, `1 + linha` décimos de mm: a soma do mês é fácil de conferir."""
    dia = np.ones(FORMA, dtype=np.int16)
    return dia * (1 + np.arange(FORMA[1], dtype=np.int16))[None, :, None]


def _preencher(matriz: np.ndarray) -> np.ndarray:
    """Completa a matriz até múltiplos do pedaço (o Zarr guarda os pedaços da borda inteiros)."""
    sobra = [(0, -tam % ped) for tam, ped in zip(matriz.shape, PEDACO, strict=True)]
    return np.pad(matriz, sobra, constant_values=v3.SEM_DADO)


def _loja(chuva: np.ndarray | None = None, **mudancas) -> dict[str, bytes]:
    raiz = v3.RAIZ_DO_ZARR
    chuva = _chuva() if chuva is None else chuva
    tempo = np.arange(DIAS) + (PRIMEIRO_DIA - ORIGEM).days
    atributos = {"scale_factor": 0.1, "add_offset": 0.0} | mudancas.pop("atributos", {})
    precip = _zarr_json(FORMA, PEDACO, mudancas.pop("tipo", "int16"), atributos,
                        ["time", "lat", "lon"], v3.SEM_DADO)  # fmt: skip
    loja = {
        f"{raiz}/precip/zarr.json": precip,
        f"{raiz}/time/zarr.json": _zarr_json(
            [DIAS], [DIAS], "int32", {"units": "days since 1980-01-01"}, ["time"]
        ),
        f"{raiz}/time/c/0": _comprimir(tempo, "<i4"),
        f"{raiz}/lat/zarr.json": _zarr_json(
            [FORMA[1]], [FORMA[1]], "float64", {}, ["lat"]
        ),
        f"{raiz}/lat/c/0": _comprimir(LAT, "<f8"),
        f"{raiz}/lon/zarr.json": _zarr_json(
            [FORMA[2]], [FORMA[2]], "float64", {}, ["lon"]
        ),
        f"{raiz}/lon/c/0": _comprimir(LON, "<f8"),
    }
    cheio = _preencher(chuva)
    for t in range(cheio.shape[0] // PEDACO[0]):
        for lin in range(cheio.shape[1] // PEDACO[1]):
            for col in range(cheio.shape[2] // PEDACO[2]):
                bloco = cheio[
                    t * PEDACO[0] : (t + 1) * PEDACO[0],
                    lin * PEDACO[1] : (lin + 1) * PEDACO[1],
                    col * PEDACO[2] : (col + 1) * PEDACO[2],
                ]
                loja[f"{raiz}/precip/c/{t}/{lin}/{col}"] = _comprimir(bloco, "<i2")
    return loja


class Cliente:
    def __init__(self, loja: dict[str, bytes]):
        self.loja = loja
        self.pedidos: list[str] = []

    def ler(self, url, *, metodo="GET", cabecalhos=None, corpo=None):
        self.pedidos.append(url)
        if url not in self.loja:
            resposta = requests.Response()
            resposta.status_code = 404
            raise requests.HTTPError("404", response=resposta)
        return Resposta(url, self.loja[url], {})


def _mes(cliente, ano, mes) -> v3.MesDoCHIRPS:
    return v3.ler_arquivo(v3.montar_arquivo(cliente, ano, mes, JANELA))


def test_soma_do_mes_e_a_janela_certa():
    mes = _mes(Cliente(_loja()), 2026, 1)
    # a janela pega as linhas com centro entre -7,0 e -7,6: todas as 12; as colunas -40,0 a -39,2: 16
    assert mes.chuva_mm.shape == (12, 16)
    assert mes.grade.passo == 0.05
    assert (mes.grade.lat_norte, mes.grade.lon_oeste) == (-7.0, -40.0)
    # 31 dias de (1 + linha) décimos de mm → mm
    esperado = 31 * (1 + np.arange(12)) / 10
    assert np.allclose(mes.chuva_mm[:, 0], esperado, atol=1e-4)
    assert (mes.ano, mes.mes) == (2026, 1)


def test_mes_que_cruza_dois_pedacos_de_tempo():
    mes = _mes(Cliente(_loja()), 2026, 2)  # dias 31 a 58; os pedaços são 0–31, 32–63
    assert np.allclose(mes.chuva_mm[:, 3], 28 * (1 + np.arange(12)) / 10, atol=1e-4)


def test_janela_menor_pega_so_os_pixels_dentro():
    janela = v3.Janela(lat_norte=-7.1, lat_sul=-7.3, lon_oeste=-39.9, lon_leste=-39.7)
    mes = v3.ler_arquivo(v3.montar_arquivo(Cliente(_loja()), 2026, 1, janela))
    assert mes.chuva_mm.shape == (4, 4)  # centros -7,125 a -7,275 e -39,875 a -39,725
    assert (mes.grade.lat_norte, mes.grade.lon_oeste) == (-7.1, -39.9)
    assert np.allclose(mes.chuva_mm[0], 31 * 3 / 10, atol=1e-4)  # a 3ª linha da grade


def test_dia_sem_dado_deixa_o_pixel_vazio_nunca_zero():
    chuva = _chuva()
    chuva[10, 2, 5] = v3.SEM_DADO  # 11/01 naquele pixel
    mes = _mes(Cliente(_loja(chuva)), 2026, 1)
    assert np.isnan(mes.chuva_mm[2, 5])
    assert np.isfinite(mes.chuva_mm[2, 4]) and np.isfinite(mes.chuva_mm[3, 5])


def test_pedaco_ausente_e_tudo_sem_dado_e_nao_erro():
    loja = _loja()
    del loja[f"{v3.RAIZ_DO_ZARR}/precip/c/0/0/0"]
    mes = _mes(Cliente(loja), 2026, 1)
    assert np.isnan(mes.chuva_mm[:8, :8]).all()
    assert np.isfinite(mes.chuva_mm[8:, :]).all()


def test_mes_que_a_copia_ainda_nao_cobre_inteiro_e_sem_arquivo():
    cliente = Cliente(_loja())
    with pytest.raises(SemArquivo):
        v3.montar_arquivo(cliente, 2026, 3, JANELA)  # só até 11/03
    with pytest.raises(SemArquivo):
        v3.montar_arquivo(cliente, 2026, 4, JANELA)
    with pytest.raises(SemArquivo):
        v3.montar_arquivo(
            cliente, 2025, 12, JANELA
        )  # antes do começo da cópia de teste


@pytest.mark.parametrize(
    "mudanca",
    [
        {"tipo": "float32"},
        {"atributos": {"scale_factor": 0.01}},
        {"atributos": {"add_offset": 5.0}},
    ],
)
def test_zarr_que_mudou_de_formato_e_erro_e_nao_chuva_errada(mudanca):
    with pytest.raises(ValueError, match="mudou de formato"):
        v3.montar_arquivo(Cliente(_loja(**mudanca)), 2026, 1, JANELA)


def test_o_mesmo_dado_gera_os_mesmos_bytes():
    a = v3.montar_arquivo(Cliente(_loja()), 2026, 1, JANELA)
    b = v3.montar_arquivo(Cliente(_loja()), 2026, 1, JANELA)
    assert a == b


def test_arquivo_que_nao_e_do_chirps_v3_e_recusado():
    with pytest.raises(ValueError, match="não é um arquivo mensal"):
        v3.ler_arquivo(b"II*\x00GeoTIFF")


def test_meses_vizinhos_dividem_os_pedacos_baixados():
    cliente = Cliente(_loja())
    pedacos = v3._Pedacos()
    v3.montar_arquivo(cliente, 2026, 1, JANELA, pedacos)
    v3.montar_arquivo(cliente, 2026, 2, JANELA, pedacos)
    baixados = [u for u in cliente.pedidos if "/precip/c/" in u]
    assert len(baixados) == len(set(baixados))  # nenhum pedaço pedido duas vezes


# --- da máscara do município à região --------------------------------------------------------------
def test_chuva_do_municipio_e_a_media_dos_pixels_da_mascara():
    mes = _mes(Cliente(_loja()), 2026, 1)
    grade = clima_regiao.Grade(**mes.grade._asdict())
    quadrado = {
        "type": "Polygon",
        "coordinates": [
            [
                [-39.95, -7.04],
                [-39.85, -7.04],
                [-39.85, -7.16],
                [-39.95, -7.16],
                [-39.95, -7.04],
            ]
        ],
    }
    mascara = clima_regiao.mascara_do_municipio(quadrado, grade)
    por_municipio = clima_regiao.ler_chirps_v3(
        v3.montar_arquivo(Cliente(_loja()), 2026, 1, JANELA), {"3100001": mascara}
    )
    linhas = np.unique(mascara.linhas)
    esperado = 31 * (1 + linhas).mean() / 10
    assert por_municipio["codigo"].tolist() == ["3100001"]
    assert por_municipio["chuva_mm"].iloc[0] == pytest.approx(esperado, abs=1e-3)


def test_regiao_do_v3_traz_a_fonte_propria_e_a_normal_nao_mistura_com_a_v2():
    por_municipio = clima_regiao.pd.DataFrame(
        {"codigo": ["3106200"], "chuva_mm": [120.0]}
    )
    v2 = clima_regiao.chirps_por_regiao(por_municipio, date(2026, 1, 1))
    v3_rnl = clima_regiao.chirps_por_regiao(por_municipio, date(2026, 1, 1), fonte=v3.FONTE_CHIRPS_V3_RNL)  # fmt: skip
    assert set(v2["fonte"]) == {clima_regiao.FONTE_CHIRPS}
    assert set(v3_rnl["fonte"]) == {"chirps-v3-rnl"}
    assert v3.FONTE_CHIRPS_V3_RNL != clima_regiao.FONTE_CHIRPS


# --- a coleta ---------------------------------------------------------------------------------------
AGORA = datetime(2026, 10, 28, 12, tzinfo=UTC)


def test_recentes_sao_os_tres_ultimos_meses_do_mais_antigo_ao_mais_novo():
    urls = [a.url for a in v3._recentes(Cliente({}), AGORA)]
    assert [u.rsplit("=", 1)[1] for u in urls] == ["2026-07", "2026-08", "2026-09"]


def test_historico_vai_de_1991_ao_mes_anterior_aos_recentes_sem_repetir():
    recentes = {a.url for a in v3._recentes(Cliente({}), AGORA)}
    historico = [a.url for a in v3._historico(Cliente({}), AGORA)]
    assert historico[0].endswith("mes=1991-01") and historico[-1].endswith(
        "mes=2026-06"
    )
    assert len(historico) == len(set(historico)) == (2026 - 1991) * 12 + 6
    assert not recentes & set(historico)


def test_alvo_tem_obter_proprio_e_endereco_que_nao_e_o_do_chc():
    alvo = v3._recentes(Cliente({}), AGORA)[0]
    assert alvo.obter is not None
    assert "huggingface.co" in alvo.url and "chc.ucsb.edu" not in alvo.url


def test_fontes_registradas_com_licenca_marca_data_e_destino():
    ids = {f.id for f in fontes.FONTES}
    for id_ in ("chirps3-rnl-mensal", "chirps3-rnl-historico"):
        assert id_ in ids
        assert "CC BY 4.0" in licenca_da_fonte(id_)
        assert marca_da_fonte(id_) is Marca.VENDAVEL
        assert TERMOS_LIDOS_EM["chirps3"].year == 2026
        assert DESTINOS[id_] == DESTINOS["chirps-mensal"]
