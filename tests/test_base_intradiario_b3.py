"""Negócios do pregão da B3 em barras de 1 minuto e o selo por ativo (plano dos intradiários, PR 2).

Arquivos montados aqui, pequenos, com o formato medido em 14/10/2026: `;`, vírgula decimal,
HoraFechamento HHMMSSmmm, AcaoAtualizacao 0 (novo) ou 2 (cancela o negócio de mesmo identificador),
TipoSessaoPregao 1 (regular) ou 6 (after-market) e DataNegocio, que pode ser o pregão seguinte
(futuros negociados à noite).
"""

import io
import zipfile
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pytest

from base import intradiario_b3 as b3

CABECALHO = (
    "DataReferencia;CodigoInstrumento;AcaoAtualizacao;PrecoNegocio;QuantidadeNegociada;"
    "HoraFechamento;CodigoIdentificadorNegocio;TipoSessaoPregao;DataNegocio;"
    "CodigoParticipanteComprador;CodigoParticipanteVendedor"
)
DIA = date(2026, 10, 13)


def linha(
    simbolo: str,
    preco: str,
    quantidade: int,
    hora: str,
    identificador: int,
    *,
    acao: int = 0,
    sessao: int = 1,
    referencia: str = "2026-10-13",
    data_do_negocio: str | None = None,
) -> str:
    return (
        f"{referencia};{simbolo};{acao};{preco};{quantidade};{hora};{identificador};"
        f"{sessao};{data_do_negocio or referencia};;"
    )


def zip_de_negocios(pasta: Path, linhas: list[str], nome: str = "dia.zip") -> Path:
    caminho = pasta / nome
    with zipfile.ZipFile(caminho, "w", zipfile.ZIP_DEFLATED) as arquivo:
        arquivo.writestr(
            "13-10-2026_NEGOCIOSAVISTA.txt", "\n".join([CABECALHO, *linhas]) + "\n"
        )
    return caminho


SEIS_LINHAS = [
    linha("PETR4", "30,10", 100, "100000047", 10),
    linha("PETR4", "30,30", 200, "100030500", 20),
    linha("PETR4", "29,90", 5000, "104300000", 30),
    linha("PETR4", "29,90", 5000, "165600000", 30, acao=2),
    linha("PETR4", "30,50", 300, "182500100", 40, sessao=6),
    linha("WINZ26", "187905,000", 1, "090000394", 230),
]


def test_ler_negocios_da_as_colunas_com_o_instante_em_sao_paulo(tmp_path):
    pedacos = list(b3.ler_negocios(zip_de_negocios(tmp_path, SEIS_LINHAS)))
    negocios = pd.concat(pedacos, ignore_index=True)
    assert list(negocios.columns) == [
        "instante",
        "pregao",
        "simbolo",
        "preco",
        "quantidade",
        "sessao",
        "cancelado",
        "identificador",
    ]
    primeiro = negocios.iloc[0]
    assert primeiro["instante"] == pd.Timestamp(
        "2026-10-13 10:00:00.047", tz="America/Sao_Paulo"
    )
    assert primeiro["pregao"] == pd.Timestamp(DIA)
    assert (primeiro["simbolo"], primeiro["preco"], primeiro["quantidade"]) == (
        "PETR4",
        30.10,
        100,
    )
    assert negocios["cancelado"].tolist() == [False] * 3 + [True] + [False] * 2
    assert negocios["sessao"].tolist() == [1, 1, 1, 1, 6, 1]
    # 09h00: a hora com um algarismo a menos no começo continua certa
    assert negocios.iloc[5]["instante"].hour == 9


def test_ler_negocios_vem_em_pedacos(tmp_path):
    pedacos = list(
        b3.ler_negocios(zip_de_negocios(tmp_path, SEIS_LINHAS), linhas_por_pedaco=4)
    )
    assert [len(p) for p in pedacos] == [4, 2]


def test_zip_sem_o_arquivo_de_negocios_falha(tmp_path):
    caminho = tmp_path / "vazio.zip"
    with zipfile.ZipFile(caminho, "w") as arquivo:
        arquivo.writestr("outro.csv", "x")
    with pytest.raises(ValueError, match="NEGOCIOSAVISTA"):
        list(b3.ler_negocios(caminho))


def test_barras_do_pregao_tiram_o_cancelado_e_o_original(tmp_path):
    barras = b3.barras_do_pregao(DIA, [zip_de_negocios(tmp_path, SEIS_LINHAS)])
    petr = barras[barras["simbolo"] == "PETR4"]
    assert 5000 not in petr["volume"].tolist()  # o negócio das 10h43 foi cancelado
    assert petr["negocios"].sum() == 2


def test_barras_do_pregao_iguais_lendo_em_pedacos(tmp_path):
    caminho = zip_de_negocios(tmp_path, SEIS_LINHAS)
    inteiro = b3.barras_do_pregao(DIA, [caminho])
    em_pedacos = b3.barras_do_pregao(DIA, [caminho], linhas_por_pedaco=2)
    pd.testing.assert_frame_equal(inteiro, em_pedacos)


def test_negocio_da_noite_vai_para_o_pregao_seguinte(tmp_path):
    """Futuro negociado às 17h05 de sexta: vem no arquivo de sexta, com DataNegocio de segunda, e o
    boletim conta no pregão de segunda (medido em 18/09 e 21/09/2026)."""
    sexta = zip_de_negocios(
        tmp_path,
        [
            linha("CCMX26", "76,32", 2, "160000000", 5, referencia="2026-09-18"),
            linha(
                "CCMX26",
                "76,32",
                2,
                "170500197",
                10,
                referencia="2026-09-18",
                data_do_negocio="2026-09-21",
            ),
        ],
        "sexta.zip",
    )
    segunda = zip_de_negocios(
        tmp_path,
        [linha("CCMX26", "76,78", 1, "090033463", 270, referencia="2026-09-21")],
        "segunda.zip",
    )
    barras = b3.barras_do_pregao(date(2026, 9, 21), [sexta, segunda])
    assert barras["negocios"].sum() == 2
    assert barras["minuto"].min() == pd.Timestamp("2026-09-18 17:05")
    assert b3.barras_do_pregao(date(2026, 9, 18), [sexta])["negocios"].sum() == 1


# --- boletim PR (BVBG.086) ----------------------------------------------------------------------

NS = "urn:bvmf.217.01.xsd"


def relatorio(simbolo: str, **campos: str) -> str:
    negocios = campos.pop("TradQty", None)
    detalhes = (
        f"<TradDtls><TradQty>{negocios}</TradQty></TradDtls>"
        if negocios
        else "<TradDtls />"
    )
    atributos = "".join(
        f'<{k} Ccy="BRL">{v}</{k}>' if "Pric" in k else f"<{k}>{v}</{k}>"
        for k, v in campos.items()
    )
    return (
        f'<BizGrp><Document xmlns="{NS}"><PricRpt><TradDt><Dt>2026-10-13</Dt></TradDt>'
        f"<SctyId><TckrSymb>{simbolo}</TckrSymb></SctyId>{detalhes}"
        f"<FinInstrmAttrbts>{atributos}</FinInstrmAttrbts></PricRpt></Document></BizGrp>"
    )


def xml_do_boletim(relatorios: list[str]) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?><Document xmlns="urn:bvmf.052.01.xsd">'
        f"<BizFileHdr><Xchg>{''.join(relatorios)}</Xchg></BizFileHdr></Document>"
    )


def zip_do_boletim(pasta: Path, versoes: dict[str, tuple[datetime, str]]) -> Path:
    """O PR vem num zip dentro de outro zip, com uma versão por hora da noite."""
    interno = io.BytesIO()
    with zipfile.ZipFile(interno, "w") as arquivo:
        for nome, (quando, xml) in versoes.items():
            arquivo.writestr(zipfile.ZipInfo(nome, quando.timetuple()[:6]), xml)
    caminho = pasta / "PR261013.zip"
    with zipfile.ZipFile(caminho, "w") as externo:
        externo.writestr("PR261013.zip", interno.getvalue())
    return caminho


PETR4_NO_BOLETIM = relatorio(
    "PETR4",
    TradQty="3",
    FinInstrmQty="600",
    FrstPric="30.1",
    MinPric="30.1",
    MaxPric="30.3",
    LastPric="30.3",
)


def test_boletim_usa_a_ultima_versao(tmp_path):
    antiga = xml_do_boletim([relatorio("PETR4", TradQty="1", FinInstrmQty="1")])
    caminho = zip_do_boletim(
        tmp_path,
        {
            "BVBG.086.01_B.xml": (
                datetime(2026, 10, 13, 21, 0, tzinfo=UTC),
                xml_do_boletim([PETR4_NO_BOLETIM]),
            ),
            "BVBG.086.01_A.xml": (datetime(2026, 10, 13, 18, 39, tzinfo=UTC), antiga),
        },
    )
    boletim = b3.ler_boletim_pr(caminho)
    assert boletim.loc["PETR4", "negocios"] == 3
    assert boletim.loc["PETR4", "volume"] == 600
    assert boletim.loc["PETR4", "abertura"] == pytest.approx(30.1)


def test_boletim_so_com_instrumentos_negociados_e_varias_linhas_somadas(tmp_path):
    """Termo (BBAS3T) vem numa linha por vencimento: soma negócios e volume; abertura e
    fechamento de várias linhas não dá para saber."""
    caminho = zip_do_boletim(
        tmp_path,
        {
            "BVBG.086.01_A.xml": (
                datetime(2026, 10, 13, 21, 0, tzinfo=UTC),
                xml_do_boletim(
                    [
                        relatorio("DLTR34"),  # sem negócio no dia: fica de fora
                        relatorio(
                            "BBAS3T",
                            TradQty="2",
                            FinInstrmQty="100",
                            FrstPric="27.5",
                            MinPric="27.5",
                            MaxPric="27.6",
                            LastPric="27.6",
                        ),
                        relatorio(
                            "BBAS3T",
                            TradQty="4",
                            FinInstrmQty="900",
                            FrstPric="24.5",
                            MinPric="24.4",
                            MaxPric="24.6",
                            LastPric="24.5",
                        ),
                    ]
                ),
            )
        },
    )
    boletim = b3.ler_boletim_pr(caminho)
    assert list(boletim.index) == ["BBAS3T"]
    termo = boletim.loc["BBAS3T"]
    assert (termo["negocios"], termo["volume"]) == (6, 1000)
    assert (termo["maxima"], termo["minima"]) == (27.6, 24.4)
    assert pd.isna(termo["abertura"]) and pd.isna(termo["fechamento"])


# --- conferência por ativo ----------------------------------------------------------------------


def barras_de(linhas: list[str], pasta: Path) -> pd.DataFrame:
    return b3.barras_do_pregao(DIA, [zip_de_negocios(pasta, linhas)])


NEGOCIOS_DO_PETR4 = [
    linha("PETR4", "30,10", 100, "100000047", 10),
    linha("PETR4", "30,30", 200, "120000000", 20),
    linha("PETR4", "30,50", 300, "182500100", 30, sessao=6),
]


def boletim_de(**por_simbolo: dict[str, float | None]) -> pd.DataFrame:
    return pd.DataFrame.from_dict(por_simbolo, orient="index")


def test_ativo_que_bate_em_tudo_e_completo(tmp_path):
    # preços só da sessão 1 (o after de 30,50 não muda a máxima); volume e negócios com o after
    boletim = boletim_de(
        PETR4={
            "abertura": 30.1,
            "maxima": 30.3,
            "minima": 30.1,
            "fechamento": 30.3,
            "volume": 600,
            "negocios": 3,
        }
    )
    conferencia = b3.conferir_dia(barras_de(NEGOCIOS_DO_PETR4, tmp_path), boletim)
    petr = conferencia.set_index("simbolo").loc["PETR4"]
    assert petr["selo"] == "completo"
    assert petr["campos_diferentes"] == ""


def test_volume_menor_e_incompleto_com_a_diferenca(tmp_path):
    boletim = boletim_de(
        PETR4={
            "abertura": 30.1,
            "maxima": 30.3,
            "minima": 30.1,
            "fechamento": 30.3,
            "volume": 700,
            "negocios": 4,
        }
    )
    petr = (
        b3.conferir_dia(barras_de(NEGOCIOS_DO_PETR4, tmp_path), boletim)
        .set_index("simbolo")
        .loc["PETR4"]
    )
    assert petr["selo"] == "incompleto"
    assert petr["campos_diferentes"] == "volume,negocios"
    assert (petr["volume_no_arquivo"], petr["volume_no_boletim"]) == (600, 700)


def test_ativo_do_boletim_que_falta_no_arquivo_e_ausente(tmp_path):
    boletim = boletim_de(
        PETR4={
            "abertura": 30.1,
            "maxima": 30.3,
            "minima": 30.1,
            "fechamento": 30.3,
            "volume": 600,
            "negocios": 3,
        },
        VALE3={
            "abertura": 70.0,
            "maxima": 71.0,
            "minima": 69.0,
            "fechamento": 70.5,
            "volume": 100,
            "negocios": 1,
        },
    )
    conferencia = b3.conferir_dia(
        barras_de(NEGOCIOS_DO_PETR4, tmp_path), boletim
    ).set_index("simbolo")
    assert conferencia.loc["VALE3", "selo"] == "ausente"


def test_ativo_fora_do_boletim_e_sem_boletim(tmp_path):
    boletim = boletim_de(
        VALE3={
            "abertura": 70.0,
            "maxima": 71.0,
            "minima": 69.0,
            "fechamento": 70.5,
            "volume": 100,
            "negocios": 1,
        }
    )
    conferencia = b3.conferir_dia(
        barras_de(NEGOCIOS_DO_PETR4, tmp_path), boletim
    ).set_index("simbolo")
    assert conferencia.loc["PETR4", "selo"] == "sem_boletim"


def test_dia_sem_boletim_tudo_sem_boletim(tmp_path):
    conferencia = b3.conferir_dia(barras_de(NEGOCIOS_DO_PETR4, tmp_path), None)
    assert conferencia["selo"].tolist() == ["sem_boletim"]


def test_campo_que_o_boletim_nao_tem_nao_e_conferido(tmp_path):
    """Termo com várias linhas: o boletim não diz a abertura nem o fechamento."""
    boletim = boletim_de(
        PETR4={
            "abertura": None,
            "maxima": 30.3,
            "minima": 30.1,
            "fechamento": None,
            "volume": 600,
            "negocios": 3,
        }
    )
    petr = (
        b3.conferir_dia(barras_de(NEGOCIOS_DO_PETR4, tmp_path), boletim)
        .set_index("simbolo")
        .loc["PETR4"]
    )
    assert petr["selo"] == "completo"


# --- selo do dia --------------------------------------------------------------------------------


def conferencia_de(selos: dict[str, str]) -> pd.DataFrame:
    return pd.DataFrame({"simbolo": list(selos), "selo": list(selos.values())})


def test_dia_completo_quando_todo_o_a_vista_e_completo():
    conferencia = conferencia_de(
        {"PETR4": "completo", "VALE3": "completo", "DI1F27": "incompleto"}
    )
    assert b3.selo_do_dia(conferencia, a_vista={"PETR4", "VALE3"}) == "completo"


@pytest.mark.parametrize("selo", ["incompleto", "ausente"])
def test_dia_incompleto_quando_um_ativo_a_vista_nao_bate(selo):
    conferencia = conferencia_de({"PETR4": "completo", "VALE3": selo})
    assert b3.selo_do_dia(conferencia, a_vista={"PETR4", "VALE3"}) == "incompleto"


def test_dia_sem_boletim():
    conferencia = conferencia_de({"PETR4": "sem_boletim"})
    assert b3.selo_do_dia(conferencia, a_vista=set()) == "sem_boletim"


def test_dia_sem_cotahist_fica_sem_boletim():
    """Sem o COTAHIST não se sabe quais são do à vista (nem se houve pregão): espera por ele."""
    conferencia = conferencia_de({"PETR4": "completo"})
    assert b3.selo_do_dia(conferencia, a_vista=set()) == "sem_boletim"


# --- COTAHIST do dia e datas dos endereços ------------------------------------------------------


def registro_do_cotahist(
    simbolo: str,
    tipo_de_mercado: str,
    precos: tuple[float, float, float, float] = (30.1, 30.3, 30.1, 30.3),
    negocios: int = 3,
    volume: int = 600,
) -> str:
    """Uma linha de 245 posições do COTAHIST (preços em centavos, 13 algarismos)."""
    abertura, maxima, minima, fechamento = (f"{round(p * 100):013d}" for p in precos)
    linha = ("01" + "20261013" + "02" + simbolo.ljust(12) + tipo_de_mercado).ljust(56)
    linha += abertura + maxima + minima + "0" * 13 + fechamento
    linha = linha.ljust(147) + f"{negocios:05d}" + f"{volume:018d}"
    return linha.ljust(245, "0")


FIM_DE_LINHA = chr(13) + chr(10)


def zip_do_cotahist(pasta: Path, registros: list[str]) -> Path:
    caminho = pasta / "COTAHIST_D13102026.ZIP"
    linhas = [
        "00COTAHIST.2026BOVESPA 20261013".ljust(245),
        *registros,
        "99COTAHIST.2026BOVESPA 20261013".ljust(245),
    ]
    with zipfile.ZipFile(caminho, "w") as arquivo:
        arquivo.writestr(
            "COTAHIST_D13102026.TXT", FIM_DE_LINHA.join(linhas).encode("latin-1")
        )
    return caminho


def test_cotahist_com_os_campos_e_o_mercado(tmp_path):
    caminho = zip_do_cotahist(
        tmp_path,
        [
            registro_do_cotahist("PETR4", "010"),
            registro_do_cotahist("PETR4F", "020"),
            registro_do_cotahist("PETRK331", "070"),
            registro_do_cotahist("BBAS3T", "030", negocios=2, volume=100),
            registro_do_cotahist("BBAS3T", "030", negocios=4, volume=900),
        ],
    )
    cotahist = b3.ler_cotahist(caminho)
    assert b3.a_vista(cotahist) == {"PETR4", "PETR4F"}
    petr = cotahist.loc["PETR4"]
    assert (petr["abertura"], petr["maxima"], petr["negocios"], petr["volume"]) == (
        30.1,
        30.3,
        3,
        600,
    )
    termo = cotahist.loc["BBAS3T"]  # uma linha por vencimento, somadas como no PR
    assert (termo["negocios"], termo["volume"]) == (6, 1000)
    assert pd.isna(termo["abertura"])


def test_boletim_do_dia_e_o_pr_completado_pelo_cotahist(tmp_path):
    """KNUQ12 (direito de subscrição) em 17/09/2026: no COTAHIST e no arquivo, fora do PR."""
    pr = boletim_de(PETR4={"negocios": 3, "volume": 600})
    cotahist = b3.ler_cotahist(
        zip_do_cotahist(
            tmp_path,
            [
                registro_do_cotahist("PETR4", "010", negocios=99),
                registro_do_cotahist("KNUQ12", "010", negocios=534, volume=44279),
            ],
        )
    )
    boletim = b3.boletim_do_dia(pr, cotahist)
    assert boletim.loc["PETR4", "negocios"] == 3  # o PR vale mais
    assert boletim.loc["KNUQ12", "negocios"] == 534
    assert "mercado" not in boletim.columns


def test_boletim_do_dia_sem_pr_nem_cotahist_e_none():
    assert b3.boletim_do_dia(None, None) is None


@pytest.mark.parametrize(
    ("endereco", "dia"),
    [
        (
            "https://arquivos.b3.com.br/rapinegocios/tickercsv/2026-10-13",
            date(2026, 10, 13),
        ),
        (
            "https://www.b3.com.br/pesquisapregao/download?filelist=PR261013.zip",
            date(2026, 10, 13),
        ),
        (
            "https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_D13102026.ZIP",
            date(2026, 10, 13),
        ),
    ],
)
def test_pregao_do_endereco(endereco, dia):
    assert b3.pregao_do_endereco(endereco) == dia
