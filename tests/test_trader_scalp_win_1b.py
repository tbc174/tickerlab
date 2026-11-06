"""Fase 1b do scalp no mini índice (docs/pre-registro-scalp-win-fase1b.md), com negócios inventados."""

import zipfile

import numpy as np
import pandas as pd
import pytest

from trader import scalp_win as sw
from trader import scalp_win_1b as sb

PREGAO = pd.Timestamp("2026-10-05")
FUSO = "America/Sao_Paulo"
MINUTOS_NA_JANELA = 8 * 60 + 30


def _instante(hora: str) -> pd.Timestamp:
    return pd.Timestamp(f"2026-10-05 {hora}").tz_localize(FUSO)


def _negocios(linhas: list[tuple]) -> pd.DataFrame:
    """Linhas (hora, preço, quantidade, comprador, vendedor)."""
    registros = []
    for numero, (hora, preco, quantidade, comprador, vendedor) in enumerate(
        linhas, start=1
    ):
        registros.append(
            {
                "instante": _instante(hora),
                "pregao": PREGAO,
                "simbolo": "WINV26",
                "preco": float(preco),
                "quantidade": quantidade,
                "sessao": 1,
                "cancelado": False,
                "identificador": numero * 10,
                "comprador": comprador,
                "vendedor": vendedor,
            }
        )
    return pd.DataFrame(registros)


# --- leitura do arquivo com as corretoras ---
CABECALHO = (
    "DataReferencia;CodigoInstrumento;AcaoAtualizacao;PrecoNegocio;QuantidadeNegociada;"
    "HoraFechamento;CodigoIdentificadorNegocio;TipoSessaoPregao;DataNegocio;"
    "CodigoParticipanteComprador;CodigoParticipanteVendedor"
)


def test_le_o_arquivo_da_b3_com_as_corretoras(tmp_path):
    linhas = [
        CABECALHO,
        "2026-10-05;WINV26;0;210000,0;2;100000123;10;1;2026-10-05;3;308",
        "2026-10-05;WINV26;0;210005,0;1;91500000;20;1;2026-10-05;85;3",
    ]
    texto = "\n".join(linhas)
    caminho = tmp_path / "x.zip"
    with zipfile.ZipFile(caminho, "w") as arquivo:
        arquivo.writestr("05-10-2026_NEGOCIOSAVISTA.txt", texto)
    negocios = pd.concat(list(sb.ler_negocios_com_corretoras(caminho)))
    assert negocios["comprador"].tolist() == ["3", "85"]
    assert negocios["vendedor"].tolist() == ["308", "3"]
    assert negocios["preco"].tolist() == [210000.0, 210005.0]
    assert negocios["instante"].iloc[0] == _instante("10:00:00.123")
    assert negocios["instante"].iloc[1] == _instante("09:15:00")


# --- regra do tick ---
def test_regra_do_tick_herda_o_sinal_quando_o_preco_nao_muda():
    precos = np.array([100, 105, 105, 100, 100, 110], dtype=float)
    assert sb.sinais_do_tick(precos).tolist() == [0, 1, 1, -1, -1, 1]


def test_regra_do_tick_sem_negocio():
    assert sb.sinais_do_tick(np.array([], dtype=float)).tolist() == []


# --- fluxo por minuto ---
def test_fluxo_por_minuto_do_agressor_e_das_corretoras():
    negocios = _negocios(
        [
            (
                "09:14:00",
                100,
                9,
                "A",
                "B",
            ),  # antes da janela: só serve de referência do tick
            ("09:15:10", 105, 2, "A", "B"),  # sobe: compra agrediu, +2
            ("09:15:20", 105, 3, "B", "C"),  # igual: herda +, +3
            ("09:16:00", 100, 4, "C", "A"),  # cai: −4
            ("17:45:00", 120, 7, "A", "C"),  # fora da janela
        ]
    )
    fluxo = sb.fluxo_por_minuto(negocios, PREGAO)
    assert len(fluxo.agressor) == MINUTOS_NA_JANELA
    assert fluxo.agressor[:3].tolist() == [5.0, -4.0, 0.0]
    liquido = fluxo.corretoras
    assert (
        liquido.loc[0, "A"] == 2
        and liquido.loc[0, "B"] == 1
        and liquido.loc[0, "C"] == -3
    )
    assert liquido.loc[1, "A"] == -4 and liquido.loc[1, "C"] == 4
    assert fluxo.lotes.set_index("corretora").loc["A", "volume"] == 6
    assert fluxo.lotes.set_index("corretora").loc["A", "lados"] == 2


def test_fluxo_do_grupo_soma_e_anula_negocio_dentro_do_grupo():
    negocios = _negocios(
        [
            ("09:14:00", 100, 1, "A", "B"),
            ("09:15:10", 105, 2, "A", "B"),
            ("09:15:20", 100, 3, "C", "A"),
        ]
    )
    fluxo = sb.fluxo_por_minuto(negocios, PREGAO)
    assert sb.fluxo_do_grupo(fluxo, {"A", "B"})[0] == pytest.approx(-3.0)
    assert sb.fluxo_do_grupo(fluxo, {"Z"})[0] == 0.0


# --- grupo de lote pequeno ---
def test_grupo_de_lote_pequeno_usa_corte_de_1_por_cento_e_a_mediana():
    lotes = pd.DataFrame(
        {
            "corretora": ["A", "B", "C", "E"],
            "volume": [400.0, 300.0, 200.0, 1.0],  # E tem 0,1% do volume: fica de fora
            "lados": [
                400,
                100,
                20,
                1,
            ],  # lote médio: 1, 3, 10 e 1; mediana das que entram: 3
        }
    )
    assert sb.grupo_de_lote_pequeno([lotes]) == {"A", "B"}


def test_grupo_soma_os_dias_do_desenvolvimento():
    dia1 = pd.DataFrame(
        {"corretora": ["A", "B"], "volume": [10.0, 10.0], "lados": [10, 1]}
    )
    dia2 = pd.DataFrame(
        {"corretora": ["A", "B"], "volume": [10.0, 90.0], "lados": [10, 90]}
    )
    # somando: A tem lote 1 e B tem lote 100/91, ainda perto de 1, mas acima da mediana
    assert sb.grupo_de_lote_pequeno([dia1, dia2]) == {"A"}


# --- janela e regra ---
def test_soma_da_janela_usa_so_os_minutos_de_antes_da_decisao():
    por_minuto = np.array([1.0, 2.0, 3.0, 4.0])
    janela = sb.soma_da_janela(por_minuto, h=2)
    assert np.isnan(janela[0]) and np.isnan(janela[1])
    assert janela[2:].tolist() == [3.0, 5.0, 7.0]


def _grade(precos: list[float]) -> pd.Series:
    indice = pd.date_range(_instante("09:15:00"), periods=len(precos), freq="min")
    return pd.Series(precos, index=indice, dtype=float)


def test_ganhos_do_sinal_segue_ou_vai_contra_o_fluxo():
    grade = _grade([100, 100, 110, 105, 105, 120])
    sinal = np.array([np.nan, 5.0, -2.0, 0.0, 3.0, 1.0])
    assert sb.ganhos_do_sinal(grade, sinal, h=1, direcao="momento").tolist() == [
        10.0,
        5.0,
        15.0,
    ]
    assert sb.ganhos_do_sinal(grade, sinal, h=1, direcao="reversao").tolist() == [
        -10.0,
        -5.0,
        -15.0,
    ]


def test_cortar_o_futuro_nao_muda_o_sinal_do_passado():
    gerador = np.random.default_rng(3)
    segundos = np.sort(gerador.integers(9 * 3600 + 900, 17 * 3600 + 2700, size=2000))
    horas = [f"{s // 3600:02d}:{s // 60 % 60:02d}:{s % 60:02d}" for s in segundos]
    precos = 100_000 + 5 * np.cumsum(gerador.choice([-1, 0, 1], size=len(horas)))
    corretoras = gerador.choice(list("ABCD"), size=(len(horas), 2))
    linhas = [
        (h, p, 1, c, v) for h, p, (c, v) in zip(horas, precos, corretoras, strict=True)
    ]
    negocios = _negocios(linhas)
    inteiro = sb.fluxo_por_minuto(negocios, PREGAO)
    corte = _instante("13:00:00")
    cortado = sb.fluxo_por_minuto(negocios[negocios["instante"] < corte], PREGAO)
    minutos_antes = (13 * 60) - (9 * 60 + 15)
    janela_inteira = sb.soma_da_janela(inteiro.agressor, h=5)[: minutos_antes + 1]
    janela_cortada = sb.soma_da_janela(cortado.agressor, h=5)[: minutos_antes + 1]
    np.testing.assert_array_equal(janela_inteira, janela_cortada)


def test_ha_exatamente_dezesseis_variantes_na_ordem_pre_registrada():
    nomes = [variante.nome for variante in sb.VARIANTES]
    assert len(nomes) == 16
    assert nomes[0] == "F_momento_1min" and nomes[1] == "F_reversao_1min"
    assert nomes[8] == "C_momento_1min" and nomes[-1] == "C_reversao_10min"


def test_veredito_da_1b_usa_as_16_e_o_empate_de_10():
    ganhos = {}
    for variante in sb.VARIANTES:
        media = 6.0 if variante.nome == "C_reversao_5min" else 0.0
        ganhos[variante.nome] = {
            "desenvolvimento": [np.full(3, media) for _ in range(11)],
            "validacao": [np.full(3, 11.0) for _ in range(12)],
        }
    veredito = sw.veredito(
        ganhos, sb.EMPATE_EM_PONTOS, ordem=[v.nome for v in sb.VARIANTES]
    )
    assert veredito["escolhida"] == "C_reversao_5min"
    assert veredito["decisao"] == "APROVA"
    assert sb.EMPATE_EM_PONTOS == 10.0


def test_o_pre_registro_da_1b_nao_mudou_desde_a_medida():
    caminho = sw.RAIZ / "docs" / "pre-registro-scalp-win-fase1b.md"
    assert sw.sha256_do_pre_registro(caminho) == sb.SHA256_DO_PRE_REGISTRO
