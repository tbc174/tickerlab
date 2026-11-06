"""Ficha P0-6: leitores (Binance e B3, sem rede), o monitor do funding e o registro antes dos números."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import numpy as np
import pandas as pd
import pytest

from trader import criterio_quant
from trader.custos_br import CustosBR
from trader.estrategias import dados_funding as df
from trader.estrategias import monitor_funding as mf
from trader.estrategias import rodar_funding as rf

# --- dublês dos arquivos ---------------------------------------------------------------------------


def _zip(nome: str, conteudo: bytes) -> bytes:
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as z:
        z.writestr(nome, conteudo)
    return saida.getvalue()


def _linha_da_b3(data: str, curva: str, dias: int, taxa: float) -> str:
    sinal = "-" if taxa < 0 else "+"
    digitos = f"{round(abs(taxa) * df.DIVISOR_DA_TAXA):014d}"
    return f"00643000101{data}T1{curva:<5}{'descricao':<15}{dias:05d}{dias:05d}{sinal}{digitos}F{dias:05d}"


def arquivo_da_b3(data: str, pontos: dict[int, float], curva: str = "DOC") -> bytes:
    """Como a B3 entrega: zip → `.ex_` (um zip depois de um cabeçalho MZ) → TaxaSwap.txt."""
    linhas = [_linha_da_b3(data, "PRE", 30, 0.11)]
    linhas += [_linha_da_b3(data, curva, dias, taxa) for dias, taxa in pontos.items()]
    texto = "\r\n".join(linhas).encode("latin-1")
    autoextraivel = b"MZ" + b"\0" * 64 + _zip("TaxaSwap.txt", texto)
    return _zip(f"TS{data[2:]}.ex_", autoextraivel)


def funding_do_mes(mes: str, taxa: float = 0.0001) -> bytes:
    horas = pd.date_range(f"{mes}-01", pd.Period(mes).end_time.floor("h"), freq="8h")
    linhas = ["calc_time,funding_interval_hours,last_funding_rate"]
    linhas += [f"{int(h.value // 1_000_000)},8,{taxa}" for h in horas]
    return _zip(f"X-fundingRate-{mes}.csv", "\n".join(linhas).encode())


class Rede:
    """Dublê da rede: responde por um pedaço da URL e anota o que foi pedido."""

    def __init__(self, respostas: dict[str, bytes | None]) -> None:
        self.respostas = respostas
        self.pedidos: list[str] = []

    def __call__(self, url: str) -> bytes | None:
        self.pedidos.append(url)
        for pedaco, resposta in self.respostas.items():
            if pedaco in url:
                return resposta
        return None


# --- B3 ------------------------------------------------------------------------------------------


def test_le_a_curva_do_cupom_sem_executar_o_autoextraivel():
    curva = df.ler_taxas_da_b3(
        arquivo_da_b3("20201030", {21: -0.023, 31: 0.0029, 360: 0.0107})
    )
    assert curva.data == pd.Timestamp("2020-10-30")
    assert curva.taxas.to_dict() == pytest.approx({21: -0.023, 31: 0.0029, 360: 0.0107})
    esperado = -0.023 + (0.0029 + 0.023) * 9 / 10
    assert curva.a_prazo(30) == pytest.approx(esperado)


def test_arquivo_sem_a_curva_ou_que_nao_e_zip_conta_como_sem_pregao(tmp_path: Path):
    rede = Rede(
        {
            "TS201031": b"<html>sem pregao</html>",
            "TS201030": arquivo_da_b3("20201030", {30: 0.01}),
        }
    )
    arquivos = df.Arquivos(tmp_path, rede)
    assert df.curva_do_dia(pd.Timestamp("2020-10-31"), arquivos) is None
    curva = df.ultima_curva_ate(pd.Timestamp("2020-11-01"), arquivos)
    assert curva.data == pd.Timestamp("2020-10-30")
    assert sorted(arquivos.hashes()) == [
        "TS201030.zip"
    ]  # o que não era arquivo da B3 não foi gravado


def test_cupom_recente_comeca_depois_do_holdout(tmp_path: Path):
    rede = Rede({"TS2610": arquivo_da_b3("20261013", {30: 0.05})})
    cupom = df.cupom_recente(df.Arquivos(tmp_path, rede), pd.Timestamp("2026-10-15"))
    assert all("TS2610" in url and int(url[-7:-4]) >= 10 for url in rede.pedidos)
    assert "TS261009" not in "".join(rede.pedidos)
    assert cupom.iloc[0] == pytest.approx(0.05)


# --- Binance --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("inicio", "fim"),
    [
        ("2023-10-10", "2023-10-10"),
        ("2023-09-01", "2023-10-31"),
        ("2026-10-09", "2026-11-01"),
    ],
)
def test_nenhum_pedido_toca_o_holdout(inicio: str, fim: str):
    with pytest.raises(df.DadoNoHoldoutError):
        df.conferir_fora_do_holdout(pd.Timestamp(inicio), pd.Timestamp(fim))


def test_desenvolvimento_termina_em_setembro_de_2023_e_o_recente_em_10_10_2026():
    assert df.meses_do_desenvolvimento()[-1] == pd.Period("2023-09", "M")
    df.conferir_fora_do_holdout(pd.Timestamp("2023-09-01"), pd.Timestamp("2023-09-30"))
    assert pd.Timestamp("2026-10-10") == df.INICIO_DO_TRECHO_RECENTE


def test_historico_pula_os_meses_antes_do_primeiro_e_guarda_o_hash(tmp_path: Path):
    rede = Rede(
        {
            "2019-09": None,
            "2019-10": funding_do_mes("2019-10"),
            "2019-11": funding_do_mes("2019-11"),
        }
    )
    arquivos = df.Arquivos(tmp_path, rede)
    meses = pd.period_range("2019-09", "2019-11", freq="M")
    serie = df.historico_mensal("BTCUSDT", df.FUNDING, arquivos, meses)
    assert serie.index.min() == pd.Timestamp("2019-10-01")
    assert sorted(arquivos.hashes()) == [
        "BTCUSDT-fundingRate-2019-10.zip",
        "BTCUSDT-fundingRate-2019-11.zip",
    ]
    pedidos = len(rede.pedidos)
    df.historico_mensal("BTCUSDT", df.FUNDING, arquivos, meses)
    assert len(rede.pedidos) == pedidos + 1  # só o mês que não existe é pedido de novo


def test_buraco_no_meio_do_historico_e_erro(tmp_path: Path):
    rede = Rede(
        {"2019-10": funding_do_mes("2019-10"), "2019-12": funding_do_mes("2019-12")}
    )
    meses = pd.period_range("2019-10", "2019-12", freq="M")
    with pytest.raises(FileNotFoundError, match="2019-11"):
        df.historico_mensal("BTCUSDT", df.FUNDING, df.Arquivos(tmp_path, rede), meses)


def test_historico_corta_no_fim_do_desenvolvimento_em_brasilia(tmp_path: Path):
    rede = Rede({"2023-09": funding_do_mes("2023-09")})
    serie = df.historico_mensal(
        "BTCUSDT", df.FUNDING, df.Arquivos(tmp_path, rede), [pd.Period("2023-09", "M")]
    )
    # 09/09 00h UTC ainda é 08/09 em Brasília; 09/09 08h UTC já não é desenvolvimento.
    assert serie.index.max() == pd.Timestamp("2023-09-09 00:00")


def test_api_pede_da_meia_noite_de_brasilia_de_10_10_2026(tmp_path: Path):
    resposta = json.dumps(
        [
            {
                "fundingTime": 1_760_083_200_000,
                "fundingRate": "0.0001",
                "symbol": "BTCUSDT",
            }
        ]
    ).encode()
    rede = Rede({"fundingRate": resposta})
    serie = df.recente_da_api(
        "BTCUSDT", df.FUNDING, df.Arquivos(tmp_path, rede), pd.Timestamp("2026-10-20")
    )
    pedido = parse_qs(urlparse(rede.pedidos[0]).query)
    assert int(pedido["startTime"][0]) == int(
        pd.Timestamp("2026-10-10 03:00").value // 1_000_000
    )
    assert (
        int(pedido["endTime"][0])
        == int(pd.Timestamp("2026-10-20 03:00").value // 1_000_000) - 1
    )
    assert serie.iloc[0] == pytest.approx(0.0001)


def test_api_recusa_fim_no_holdout(tmp_path: Path):
    with pytest.raises(df.DadoNoHoldoutError):
        df.recente_da_api(
            "BTCUSDT",
            df.FUNDING,
            df.Arquivos(tmp_path, Rede({})),
            pd.Timestamp("2026-10-01"),
        )


# --- o monitor ------------------------------------------------------------------------------------


def _pagamentos(inicio: str, dias: int, taxa: float = 0.0001) -> pd.Series:
    horas = pd.date_range(inicio, periods=dias * 3, freq="8h")
    return pd.Series(taxa, index=horas)


def test_funding_do_dia_e_por_brasilia_e_descarta_a_ponta_incompleta():
    diario = mf.funding_por_dia(_pagamentos("2020-01-01 00:00", 10))
    # 01/01 00h UTC é 31/12 21h em Brasília: esse dia tem 1 pagamento e sai.
    assert diario.index[0] == pd.Timestamp("2020-01-01")
    assert diario.iloc[0] == pytest.approx(0.0003)
    assert diario.index[-1] == pd.Timestamp("2020-01-09")


def test_funding_liquido_desconta_o_custo_e_o_ir():
    custos = CustosBR()
    custo = mf.custo_anualizado(custos)
    assert custo == pytest.approx(4 * 0.001 * 365 / 30)
    bruto = pd.Series([0.30, 0.01])
    liquido = mf.funding_liquido(bruto, custos)
    assert liquido.iloc[0] == pytest.approx((0.30 - custo) * (1 - custos.ir_cripto))
    assert liquido.iloc[1] == pytest.approx(0.01 - custo)  # negativo não tem IR


def test_anualizado_so_com_sete_dias_completos():
    diario = pd.Series(0.001, index=pd.date_range("2020-01-01", periods=10, freq="D"))
    diario = diario.drop(pd.Timestamp("2020-01-05"))
    assert (
        mf.funding_anualizado(diario).isna().all()
    )  # o buraco de 05/01 fica em todas as janelas
    diario2 = pd.Series(0.001, index=pd.date_range("2020-01-01", periods=7, freq="D"))
    assert mf.funding_anualizado(diario2).iloc[-1] == pytest.approx(0.365)


def test_taxa_do_dia_e_sempre_a_publicada_antes():
    serie = pd.Series(
        [0.01, 0.02], index=pd.DatetimeIndex(["2020-01-02", "2020-01-05"])
    )
    dias = pd.date_range("2020-01-02", "2020-01-06", freq="D")
    conhecida = mf.taxa_conhecida_antes(serie, dias)
    assert np.isnan(conhecida.iloc[0])
    assert conhecida.loc["2020-01-05"] == pytest.approx(0.01)
    assert conhecida.loc["2020-01-06"] == pytest.approx(0.02)


def test_alertas_seguem_a_ficha():
    dias = 20
    pagamentos = _pagamentos(
        "2020-01-01 03:00", dias, taxa=0.0005
    )  # 0,15% ao dia: ~55% a.a.
    cdi = pd.Series(0.0004, index=pd.date_range("2019-12-20", "2020-01-25", freq="B"))
    cupom = pd.Series(
        [0.02, 0.60], index=pd.DatetimeIndex(["2019-12-31", "2020-01-14"])
    )
    premio = pd.Series(
        0.0002, index=pd.date_range("2020-01-01", periods=dias, freq="D")
    )
    tabela = mf.monitorar(pagamentos, premio, cupom, cdi)
    assert tabela["alerta_funding"].all()
    assert (
        (tabela["carry_em_reais"] - tabela["cdi"])
        .round(12)
        .equals((tabela["funding_liquido"] - tabela["cupom"]).round(12))
    )
    assert tabela.loc[
        :"2020-01-14", "alerta_carry"
    ].all()  # cupom de 2% até a curva nova
    assert not tabela.loc[
        "2020-01-15":, "alerta_carry"
    ].any()  # cupom de 60% a partir do dia seguinte
    resumo = mf.resumir(tabela)
    assert resumo["alerta_funding"] == 1.0
    assert resumo["maior_sequencia_funding"] == len(tabela)


def test_maior_sequencia():
    assert (
        mf.maior_sequencia(pd.Series([True, True, False, True, True, True, False])) == 3
    )
    assert mf.maior_sequencia(pd.Series([False, False])) == 0


# --- a rodada -------------------------------------------------------------------------------------


def _dados() -> rf.Dados:
    dados = rf.Dados(fim=pd.Timestamp("2026-10-30"), hash_dos_arquivos="abc")
    for par in df.PARES:
        dados.pagamentos["desenvolvimento", par] = _pagamentos("2023-08-01 03:00", 30)
        dados.premio["desenvolvimento", par] = pd.Series(
            0.0001, index=pd.date_range("2023-08-01", periods=30)
        )
        dados.pagamentos["recente", par] = _pagamentos("2026-10-10 03:00", 19)
        dados.premio["recente", par] = pd.Series(
            0.0001, index=pd.date_range("2026-10-10", periods=19)
        )
    dados.cupom = {
        "desenvolvimento": pd.Series([0.05], index=pd.DatetimeIndex(["2023-07-31"])),
        "recente": pd.Series([0.05], index=pd.DatetimeIndex(["2026-10-13"])),
    }
    dados.cdi = {
        "desenvolvimento": pd.Series(
            0.0005, index=pd.date_range("2023-07-20", "2023-09-08", freq="B")
        ),
        "recente": pd.Series(
            0.0005, index=pd.date_range("2026-10-10", "2026-10-29", freq="B")
        ),
    }
    return dados


def test_rodada_registra_antes_dos_numeros_e_guarda_o_resultado(tmp_path: Path):
    registro = criterio_quant.abrir_registro(tmp_path / "registro.db")
    saida = rf.executar(_dados(), registro)
    linhas = registro.listar()
    assert [(t["familia"], t["nome"]) for t in linhas] == [("P0-6", "monitor_funding")]
    assert saida["hoje"]["BTCUSDT"]["dia"] == "2026-10-28"
    relatorio = rf.escrever_relatorio(saida, tmp_path / "relatorios").read_text("utf-8")
    assert "## Limites e cuidados" in relatorio
    assert "Nada aqui é recomendação de investimento" in relatorio


def test_rodada_que_quebra_no_calculo_ainda_conta_como_tentativa(
    tmp_path: Path, monkeypatch
):
    registro = criterio_quant.abrir_registro(tmp_path / "registro.db")

    def quebrar(*_: object) -> None:
        raise RuntimeError("quebrou")

    monkeypatch.setattr(rf, "montar", quebrar)
    with pytest.raises(RuntimeError):
        rf.executar(_dados(), registro)
    assert len(registro.listar()) == 1


def test_p0_6_tem_duas_tentativas_e_nao_passa_pelo_criterio():
    assert criterio_quant.ORCAMENTO_POR_FICHA["P0-6"] == 2
    assert "P0-6" in criterio_quant.FICHAS_SEM_CRITERIO
