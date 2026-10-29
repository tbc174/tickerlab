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
    volume_financeiro: float = 18_120.0,
) -> str:
    """Uma linha de 245 posições do COTAHIST (preços e volume financeiro em centavos)."""
    abertura, maxima, minima, fechamento = (f"{round(p * 100):013d}" for p in precos)
    linha = ("01" + "20261013" + "02" + simbolo.ljust(12) + tipo_de_mercado).ljust(56)
    linha += abertura + maxima + minima + "0" * 13 + fechamento
    linha = linha.ljust(147) + f"{negocios:05d}" + f"{volume:018d}"
    linha += f"{round(volume_financeiro * 100):018d}"
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


def test_cotahist_traz_o_volume_em_reais_alem_da_quantidade(tmp_path):
    """Regressão (pregão do dia, 28/10/2026): `volume` é a quantidade de papéis (QUATOT, como o
    FinInstrmQty do PR); o valor negociado em reais (VOLTOT) vem à parte. VALE3 em 27/10/2026:
    43.938.600 ações e R$ 2.772.825.021,00."""
    caminho = zip_do_cotahist(
        tmp_path,
        [
            registro_do_cotahist(
                "VALE3", "010", volume=43_938_600, volume_financeiro=2_772_825_021.0
            ),
            registro_do_cotahist("BBAS3T", "030", volume_financeiro=1_000.5),
            registro_do_cotahist("BBAS3T", "030", volume_financeiro=2_000.25),
        ],
    )
    cotahist = b3.ler_cotahist(caminho)
    assert cotahist.loc["VALE3", "volume"] == 43_938_600
    assert cotahist.loc["VALE3", "volume_financeiro"] == 2_772_825_021.0
    assert (
        cotahist.loc["BBAS3T", "volume_financeiro"] == 3_000.75
    )  # somado, como o volume


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


# --- negócios inseridos depois (identificador fora da dezena) -----------------------------------


def test_correcao_fica_no_lugar_do_negocio_corrigido(tmp_path):
    """PETR4 em 25/09/2026: às 17h06 a B3 cancelou o 346910 (2.700.000 ações, das 16h08) e lançou o
    346911 (270.000) com a hora da correção. O substituto vale no minuto das 16h08, e o fechamento
    continua sendo o do leilão (47,99), não o da correção."""
    linhas = [
        linha("PETR4", "48,06", 2_700_000, "160844573", 346910),
        linha("PETR4", "47,99", 900, "170540272", 397450),
        linha("PETR4", "48,06", 2_700_000, "170634974", 346910, acao=2),
        linha("PETR4", "48,06", 270_000, "170634974", 346911),
    ]
    barras = b3.barras_do_pregao(DIA, [zip_de_negocios(tmp_path, linhas)])
    assert barras["minuto"].dt.strftime("%H:%M").tolist() == ["16:08", "17:05"]
    assert barras["volume"].tolist() == [270_000, 900]
    assert b3.totais_do_dia(barras).loc["PETR4", "fechamento"] == 47.99


def test_registro_tardio_vai_para_o_minuto_do_leilao(tmp_path):
    """PETR4 em 18/09/2026: o 312415 foi registrado às 19h04, entre dois negócios do leilão das
    17h10 (312410 e 312420)."""
    linhas = [
        linha("PETR4", "48,50", 1000, "171031645", 312410),
        linha("PETR4", "48,50", 24100, "171031645", 312420),
        linha("PETR4", "48,50", 12000, "190400722", 312415),
    ]
    barras = b3.barras_do_pregao(DIA, [zip_de_negocios(tmp_path, linhas)])
    assert barras["minuto"].dt.strftime("%H:%M").tolist() == ["17:10"]
    assert barras["negocios"].tolist() == [3]


def test_insercao_sem_o_negocio_de_referencia_fica_com_a_propria_hora(tmp_path):
    linhas = [linha("PETR4", "48,50", 100, "120000000", 5)]
    barras = b3.barras_do_pregao(DIA, [zip_de_negocios(tmp_path, linhas)])
    assert barras["minuto"].dt.strftime("%H:%M").tolist() == ["12:00"]


def test_insercao_em_pedacos_diferentes_do_arquivo(tmp_path):
    linhas = [
        linha("PETR4", "48,06", 2_700_000, "160844573", 346910),
        linha("PETR4", "47,99", 900, "170540272", 397450),
        linha("PETR4", "48,06", 2_700_000, "170634974", 346910, acao=2),
        linha("PETR4", "48,06", 270_000, "170634974", 346911),
    ]
    caminho = zip_de_negocios(tmp_path, linhas)
    pd.testing.assert_frame_equal(
        b3.barras_do_pregao(DIA, [caminho], linhas_por_pedaco=1),
        b3.barras_do_pregao(DIA, [caminho]),
    )


# --- PR 3: houve pregão? e o alarme da janela de 20 pregões ------------------------------------


def dias_uteis(inicio: date, fim: date) -> list[date]:
    dias = pd.bdate_range(inicio, fim).date
    return [d for d in dias if d != date(2026, 10, 12)]  # 12/10: sem COTAHIST (feriado)


PREGOES = dias_uteis(date(2026, 9, 15), date(2026, 10, 13))  # os 20 no ar em 14/10


def test_janela_de_14_10_tem_os_20_pregoes():
    assert len(PREGOES) == 20


def test_pregao_mais_antigo_sem_arquivo_esta_em_risco():
    salvos = set(PREGOES) - {date(2026, 9, 15)}
    assert b3.dias_em_risco(PREGOES, salvos) == [(date(2026, 9, 15), 1)]


def test_risco_so_nos_cinco_pregoes_mais_antigos():
    faltando = {date(2026, 9, 21), date(2026, 9, 22), date(2026, 10, 13)}
    salvos = set(PREGOES) - faltando
    # 21/09 é o 5º mais antigo (some em 5 pregões); 22/09 é o 6º; 13/10 acabou de sair
    assert b3.dias_em_risco(PREGOES, salvos) == [(date(2026, 9, 21), 5)]


def test_feriado_sem_cotahist_nao_e_falha():
    """12/10/2026 (Nossa Senhora Aparecida): sem COTAHIST, não houve pregão; nada a salvar."""
    assert date(2026, 10, 12) not in PREGOES
    assert b3.dias_em_risco(PREGOES, set(PREGOES)) == []


def test_pregao_que_ja_saiu_da_janela_nao_entra_no_alarme():
    pregoes = dias_uteis(date(2026, 9, 1), date(2026, 10, 13))
    salvos = set(PREGOES)  # tudo antes de 15/09 já saiu da janela e não foi salvo
    assert b3.dias_em_risco(pregoes, salvos) == []


@pytest.mark.parametrize(
    ("ultimo", "hoje", "atrasado"),
    [
        (date(2026, 10, 13), date(2026, 10, 15), False),
        (date(2026, 10, 9), date(2026, 10, 14), False),  # sexta, feriado na segunda
        (date(2026, 10, 9), date(2026, 10, 16), True),
    ],
)
def test_cotahist_atrasado(ultimo, hoje, atrasado):
    assert b3.cotahist_atrasado([date(2026, 10, 1), ultimo], hoje) is atrasado


def test_sem_nenhum_cotahist_e_atrasado():
    assert b3.cotahist_atrasado([], date(2026, 10, 14)) is True


def test_lista_curta_de_pregoes_nao_tem_risco():
    """Com poucos pregões conhecidos (acervo começando), todos são recentes."""
    assert b3.dias_em_risco([date(2026, 10, 9), date(2026, 10, 13)], set()) == []


def test_contratos_do_pr_trazem_o_ajuste_do_di_em_taxa_e_o_do_dolar_em_preco(tmp_path):
    """DI1: a taxa de ajuste (% ao ano), não o preço unitário; DOL: o preço de ajuste (R$ por US$ 1.000).
    Contrato sem negócio no dia também tem ajuste; ação e contrato de outro prefixo ficam de fora."""
    caminho = zip_do_boletim(
        tmp_path,
        {
            "BVBG.086.01_A.xml": (
                datetime(2026, 10, 27, 21, 0, tzinfo=UTC),
                xml_do_boletim(
                    [
                        relatorio(
                            "DI1F29",
                            TradQty="139933",
                            AdjstdQt="74289.66",
                            AdjstdQtTax="14.76",
                            PrvsAdjstdQt="73646.86",
                            PrvsAdjstdQtTax="15.223",
                        ),
                        relatorio("DI1F35", AdjstdQtTax="14.1", PrvsAdjstdQtTax="14.2"),
                        relatorio(
                            "DOLX26",
                            TradQty="41018",
                            AdjstdQt="5350.365",
                            PrvsAdjstdQt="5422.909",
                        ),
                        PETR4_NO_BOLETIM,
                        relatorio(
                            "WINZ26",
                            TradQty="9",
                            AdjstdQt="176000",
                            PrvsAdjstdQt="177000",
                        ),
                    ]
                ),
            )
        },
    )
    contratos = b3.ler_contratos_do_pr(caminho)
    assert sorted(contratos.index) == ["DI1F29", "DI1F35", "DOLX26"]
    assert tuple(contratos.loc["DI1F29"]) == (14.76, 15.223)
    assert tuple(contratos.loc["DI1F35"]) == (14.1, 14.2)
    assert tuple(contratos.loc["DOLX26"]) == (5350.365, 5422.909)


def test_contrato_sem_ajuste_fica_de_fora(tmp_path):
    caminho = zip_do_boletim(
        tmp_path,
        {
            "BVBG.086.01_A.xml": (
                datetime(2026, 10, 27, 21, 0, tzinfo=UTC),
                xml_do_boletim([relatorio("DOLF27", PrvsAdjstdQt="5400")]),
            )
        },
    )
    assert b3.ler_contratos_do_pr(caminho).empty
