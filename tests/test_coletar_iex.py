"""Coletor diário do IEX HIST (F3), sem internet: uma IEX falsa devolve a lista e o arquivo do dia."""

import gzip
import io
import json
import struct
from datetime import date

import pandas as pd
import pytest
import urllib3

from scripts import coletar_iex_do_dia as coletor
from tests.test_iex_tops import mensagem_de_negocio, pacote, pcapng

SEXTA = date(2026, 10, 9)
LINK = "https://iex.exemplo/tops-20261009.pcap.gz"


class _Resposta:
    def __init__(self, json_=None, conteudo=b""):
        self._json = json_
        self.raw = io.BytesIO(conteudo)

    def raise_for_status(self):
        return None

    def json(self):
        return self._json

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def _iex_falsa(arquivo_do_dia: bytes | None, pedidos: list | None = None):
    def buscar(url, stream=False, timeout=None):
        if pedidos is not None:
            pedidos.append(url)
        if "hist?date=" in url:
            lista = [] if arquivo_do_dia is None else [{"feed": "TOPS", "link": LINK}]
            return _Resposta(json_=lista)
        return _Resposta(conteudo=gzip.compress(arquivo_do_dia))

    return buscar


def _dia_com_dois_negocios() -> bytes:
    return pcapng(
        [
            pacote([mensagem_de_negocio("AAPL", 227.5, 30, id_do_negocio=1)]),
            pacote([mensagem_de_negocio("AAPL", 228.0, 10, id_do_negocio=2)]),
        ]
    )


def test_coleta_um_dia_grava_as_barras_e_o_resumo(tmp_path):
    resumo = coletor.coletar_dia(
        SEXTA, {"AAPL"}, tmp_path, _iex_falsa(_dia_com_dois_negocios())
    )
    barras = pd.read_parquet(tmp_path / "2026-10-09.parquet")
    assert list(barras["simbolo"]) == ["AAPL"]
    assert barras["volume"].tolist() == [40]
    guardado = json.loads((tmp_path / "2026-10-09.json").read_text("utf-8"))
    assert guardado == resumo
    assert guardado["negocios_guardados"] == 2
    assert guardado["atribuicao"].startswith("Data provided for free by IEX.")
    assert len(guardado["sha256_do_parquet"]) == 64
    assert not list(tmp_path.glob("*.parcial"))  # gravação atômica: nada pela metade


def test_dia_sem_arquivo_na_iex_nao_grava_nada(tmp_path):
    assert (
        coletor.coletar_dia(SEXTA, {"AAPL"}, tmp_path, _iex_falsa(None))
        == coletor.SEM_ARQUIVO
    )
    assert not list(tmp_path.iterdir())


def test_arquivo_malformado_nao_grava_nada_e_a_tarefa_falha(tmp_path, monkeypatch):
    monkeypatch.setattr(coletor, "simbolos_do_sp500", lambda: {"AAPL"})
    quebrado = struct.pack("<II", 6, 0)  # bloco de tamanho 0 (A-03)
    codigo = coletor.main(
        ["--data", "2026-10-09", "--pasta", str(tmp_path)], _iex_falsa(quebrado)
    )
    assert codigo == 1
    assert not list(tmp_path.glob("*.parquet")) and not list(tmp_path.glob("*.parcial"))


def test_dias_uteis_recentes_pulam_o_fim_de_semana():
    segunda = date(2026, 10, 12)
    assert coletor.dias_uteis_recentes(segunda, 3) == [
        date(2026, 10, 7),
        date(2026, 10, 8),
        date(2026, 10, 9),
    ]


def test_dia_ja_guardado_nao_e_baixado_de_novo(tmp_path):
    for d in coletor.dias_uteis_recentes(date(2026, 10, 12)):
        coletor.arquivo_do_dia(d, tmp_path).write_bytes(b"x")
    assert coletor.dias_que_faltam(date(2026, 10, 12), tmp_path) == []


def test_sem_nada_a_coletar_termina_bem_sem_pedir_nada(tmp_path, monkeypatch):
    for d in coletor.dias_uteis_recentes(coletor.datetime.now(coletor.FUSO_NY).date()):
        coletor.arquivo_do_dia(d, tmp_path).write_bytes(b"x")
    pedidos: list = []
    assert coletor.main(["--pasta", str(tmp_path)], _iex_falsa(None, pedidos)) == 0
    assert pedidos == []


# --- carga dos 12 meses (13/10/2026) ---------------------------------------------------------------
def test_dias_uteis_desde_uma_data_do_mais_novo_para_o_mais_antigo():
    assert coletor.dias_uteis_desde(date(2026, 10, 7), date(2026, 10, 12)) == [
        date(2026, 10, 9),
        date(2026, 10, 8),
        date(2026, 10, 7),
    ]


def test_carga_respeita_o_maximo_e_pula_os_dias_ja_guardados(tmp_path, monkeypatch):
    monkeypatch.setattr(coletor, "simbolos_do_sp500", lambda: {"AAPL"})
    hoje = coletor.datetime.now(coletor.FUSO_NY).date()
    ontem_util = coletor.dias_uteis_desde(hoje - coletor.timedelta(days=10), hoje)[0]
    coletor.arquivo_do_dia(ontem_util, tmp_path).write_bytes(b"x")  # já guardado
    pedidos: list = []
    desde = (hoje - coletor.timedelta(days=30)).isoformat()
    codigo = coletor.main(
        ["--desde", desde, "--maximo", "3", "--pasta", str(tmp_path)],
        _iex_falsa(_dia_com_dois_negocios(), pedidos),
    )
    assert codigo == 0
    novos = sorted(p.stem for p in tmp_path.glob("*.parquet") if p.stat().st_size > 1)
    assert len(novos) == 3
    assert ontem_util.isoformat() not in novos  # não baixou de novo
    assert max(novos) < ontem_util.isoformat()  # do mais novo para trás


def test_feriado_nao_conta_no_maximo(tmp_path, monkeypatch):
    monkeypatch.setattr(coletor, "simbolos_do_sp500", lambda: {"AAPL"})
    pedidos: list = []
    codigo = coletor.main(
        ["--desde", "2026-09-01", "--maximo", "2", "--pasta", str(tmp_path)],
        _iex_falsa(None, pedidos),  # a IEX não tem arquivo de nenhum dia
    )
    assert codigo == 0
    assert not list(tmp_path.glob("*.parquet"))
    assert len(pedidos) > 2  # olhou todos os dias, sem parar no máximo


def test_carga_para_quando_acaba_o_tempo(tmp_path, monkeypatch):
    monkeypatch.setattr(coletor, "simbolos_do_sp500", lambda: {"AAPL"})
    relogio = iter([0.0, 0.0, 61.0, 200.0, 400.0])
    monkeypatch.setattr(coletor.time, "monotonic", lambda: next(relogio))
    codigo = coletor.main(
        [
            "--desde",
            "2026-09-01",
            "--maximo",
            "20",
            "--minutos",
            "1",
            "--pasta",
            str(tmp_path),
        ],
        _iex_falsa(_dia_com_dois_negocios()),
    )
    assert codigo == 0
    assert len(list(tmp_path.glob("*.parquet"))) == 1  # o 2º dia já não começa


# --- feriados dos EUA (14/10/2026: a carga travou no 404 do Labor Day, 07/09) ----------------------
class _Resposta404(_Resposta):
    def raise_for_status(self):
        raise coletor.requests.HTTPError("404 Client Error: Not Found")


def test_dias_uteis_desde_pulam_os_feriados_da_nyse():
    assert coletor.dias_uteis_desde(date(2026, 9, 4), date(2026, 9, 10)) == [
        date(2026, 9, 9),
        date(2026, 9, 8),
        date(2026, 9, 4),  # 07/09 (Labor Day) fora
    ]


def test_dias_uteis_recentes_pulam_os_feriados_da_nyse():
    assert coletor.dias_uteis_recentes(date(2026, 9, 9), 3) == [
        date(2026, 9, 3),
        date(2026, 9, 4),
        date(2026, 9, 8),
    ]


def test_carga_nao_pede_o_dia_de_feriado_que_a_iex_responde_com_404(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(coletor, "simbolos_do_sp500", lambda: {"AAPL"})
    pedidos: list = []

    def buscar(url, stream=False, timeout=None):
        pedidos.append(url)
        if url.endswith("date=20260907"):
            return _Resposta404()
        return _Resposta(json_=[])  # nenhum outro dia tem arquivo (não baixa nada)

    codigo = coletor.main(["--desde", "2026-09-01", "--pasta", str(tmp_path)], buscar)
    assert codigo == 0
    assert not any(url.endswith("date=20260907") for url in pedidos)
    assert any(url.endswith("date=20260908") for url in pedidos)


def test_404_num_dia_de_pregao_continua_sendo_falha(tmp_path, monkeypatch):
    # Um fechamento extra que o calendário não conhece aparece no alarme, em vez de sumir calado.
    monkeypatch.setattr(coletor, "simbolos_do_sp500", lambda: {"AAPL"})
    codigo = coletor.main(
        ["--data", "2026-09-08", "--pasta", str(tmp_path)],
        lambda url, stream=False, timeout=None: _Resposta404(),
    )
    assert codigo == 1


# --- conexão que cai no meio do arquivo (16/10/2026: a carga parou num ProtocolError da urllib3) ---
class _FluxoQueCai(io.RawIOBase):
    """O arquivo do dia que a IEX começa a mandar e corta no meio, como na carga de 16/10."""

    def readable(self):
        return True

    def readinto(self, _buffer):
        raise urllib3.exceptions.ProtocolError(
            "Connection broken: IncompleteRead(8791124987 bytes read, 8722677294 more expected)"
        )


def _iex_que_cai(vezes: int, pedidos: list, dia_que_cai: str = "20260909"):
    """Corta o arquivo de `dia_que_cai` nas primeiras `vezes` tentativas; o resto vai inteiro."""
    inteira = _iex_falsa(_dia_com_dois_negocios())
    cortes = {"faltam": vezes}

    def buscar(url, stream=False, timeout=None):
        pedidos.append(url)
        if url.endswith("hist?date=" + dia_que_cai):
            return _Resposta(json_=[{"feed": "TOPS", "link": LINK + dia_que_cai}])
        if url.endswith(LINK + dia_que_cai) and cortes["faltam"] > 0:
            cortes["faltam"] -= 1
            resposta = _Resposta()
            resposta.raw = _FluxoQueCai()
            return resposta
        return inteira(url, stream, timeout)

    return buscar


def test_conexao_que_cai_uma_vez_e_tentada_de_novo(tmp_path, monkeypatch):
    monkeypatch.setattr(coletor, "simbolos_do_sp500", lambda: {"AAPL"})
    pedidos: list = []
    codigo = coletor.main(
        ["--data", "2026-09-09", "--pasta", str(tmp_path)], _iex_que_cai(1, pedidos)
    )
    assert codigo == 0
    assert (tmp_path / "2026-09-09.parquet").exists()
    assert pedidos.count(LINK + "20260909") == 2


def test_conexao_que_cai_de_novo_falha_o_dia_sem_parar_a_rodada(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(coletor, "simbolos_do_sp500", lambda: {"AAPL"})
    pedidos: list = []
    codigo = coletor.main(
        ["--desde", "2026-09-08", "--maximo", "99", "--pasta", str(tmp_path)],
        _iex_que_cai(99, pedidos),
    )
    assert codigo == 1  # o alarme avisa
    assert not (tmp_path / "2026-09-09.parquet").exists()
    assert not list(tmp_path.glob("*.parcial"))
    # o dia seguinte da fila foi coletado
    assert (tmp_path / "2026-09-08.parquet").exists()
    assert "2026-09-09: FALHOU, nada gravado (ProtocolError" in capsys.readouterr().out


# --- selo por ativo (plano dos intradiários grátis, PR 5) --------------------------------------


@pytest.fixture(autouse=True)
def _sem_yahoo(monkeypatch):
    """Nenhum teste deste arquivo vai à internet: o fechamento oficial vem vazio, salvo pedido."""
    monkeypatch.setattr(
        coletor, "fechamentos_oficiais", lambda dia, simbolos: pd.Series(dtype=float)
    )


def _oficiais(precos: dict[str, float], pedidos: list | None = None):
    def buscar(dia, simbolos):
        if pedidos is not None:
            pedidos.append(dia)
        return pd.Series(precos, dtype=float)

    return buscar


def test_dia_coletado_ganha_o_selo(tmp_path, monkeypatch):
    monkeypatch.setattr(coletor, "simbolos_do_sp500", lambda: {"AAPL"})
    codigo = coletor.main(
        ["--data", SEXTA.isoformat(), "--pasta", str(tmp_path)],
        _iex_falsa(_dia_com_dois_negocios()),
        _oficiais({"AAPL": 228.10}),
    )
    assert codigo == 0
    selo = pd.read_parquet(tmp_path / "selo" / "2026-10-09.parquet")
    assert selo.set_index("simbolo").loc["AAPL", "selo"] == "confere"
    resumo = json.loads((tmp_path / "2026-10-09.json").read_text("utf-8"))
    assert resumo["selo"] == {"confere": 1}
    assert resumo["pior_diferenca"] == pytest.approx(abs(228.0 / 228.10 - 1), abs=1e-6)


def test_sem_resposta_do_oficial_nao_grava_selo_e_tenta_de_novo(tmp_path, monkeypatch):
    monkeypatch.setattr(coletor, "simbolos_do_sp500", lambda: {"AAPL"})
    coletor.coletar_dia(SEXTA, {"AAPL"}, tmp_path, _iex_falsa(_dia_com_dois_negocios()))
    assert coletor.selar_os_que_faltam(tmp_path, _oficiais({})) == []
    assert not (tmp_path / "selo").exists()
    pedidos: list = []
    [linha] = coletor.selar_os_que_faltam(tmp_path, _oficiais({"AAPL": 228.0}, pedidos))
    assert pedidos == [SEXTA]
    assert linha.startswith("2026-10-09: selo")


def test_dia_ja_selado_nao_pede_o_oficial_de_novo(tmp_path):
    coletor.coletar_dia(SEXTA, {"AAPL"}, tmp_path, _iex_falsa(_dia_com_dois_negocios()))
    coletor.selar_os_que_faltam(tmp_path, _oficiais({"AAPL": 228.0}))
    pedidos: list = []
    assert (
        coletor.selar_os_que_faltam(tmp_path, _oficiais({"AAPL": 228.0}, pedidos)) == []
    )
    assert pedidos == []


def test_fechamento_longe_aparece_na_saida_mas_nao_e_falha(
    tmp_path, monkeypatch, capsys
):
    """Na carga antiga, um desdobramento depois do dia muda o preço do Yahoo: fica registrado."""
    for d in coletor.dias_uteis_recentes(coletor.datetime.now(coletor.FUSO_NY).date()):
        coletor.arquivo_do_dia(d, tmp_path).write_bytes(b"x")
    coletor.coletar_dia(SEXTA, {"AAPL"}, tmp_path, _iex_falsa(_dia_com_dois_negocios()))
    codigo = coletor.main(
        ["--pasta", str(tmp_path)], _iex_falsa(None), _oficiais({"AAPL": 456.0})
    )
    assert codigo == 0
    assert "1 nao_confere" in capsys.readouterr().out


# --- selo dentro do orçamento (18/10/2026: o selo da carga segurou a trava das tarefas por horas) ---
def _relogio_que_avanca(passo_s: float):
    """Relógio de mentira: cada leitura anda `passo_s` segundos."""
    leituras = iter(range(10_000))
    return lambda: next(leituras) * passo_s


def _tres_dias_coletados(pasta):
    dias = [date(2026, 10, 7), date(2026, 10, 8), SEXTA]
    for dia in dias:
        coletor.coletar_dia(dia, {"AAPL"}, pasta, _iex_falsa(_dia_com_dois_negocios()))
    return dias


def test_selo_para_no_prazo_e_a_rodada_seguinte_retoma(tmp_path, monkeypatch, capsys):
    dias = _tres_dias_coletados(tmp_path)
    monkeypatch.setattr(coletor.time, "monotonic", _relogio_que_avanca(60.0))
    pedidos: list = []
    prazo = 90.0  # 1ª leitura 0 s (sela), 2ª 60 s (sela), 3ª 120 s (passou: para)
    linhas = coletor.selar_os_que_faltam(
        tmp_path, _oficiais({"AAPL": 228.0}, pedidos), prazo=prazo
    )
    assert pedidos == [SEXTA, date(2026, 10, 8)]  # do mais novo para o mais antigo
    assert len(linhas) == 2
    assert "1 dias ficam sem selo" in capsys.readouterr().out
    assert coletor.dias_sem_selo(tmp_path) == [dias[0]]

    pedidos.clear()
    [linha] = coletor.selar_os_que_faltam(tmp_path, _oficiais({"AAPL": 228.0}, pedidos))
    assert pedidos == [dias[0]]  # a rodada seguinte retoma de onde parou
    assert linha.startswith("2026-10-07: selo")
    assert coletor.dias_sem_selo(tmp_path) == []


def test_selo_no_prazo_grava_o_mesmo_que_sem_prazo(tmp_path):
    for subpasta, prazo in (("sem_prazo", None), ("com_prazo", float("inf"))):
        pasta = tmp_path / subpasta
        _tres_dias_coletados(pasta)
        coletor.selar_os_que_faltam(pasta, _oficiais({"AAPL": 228.1}), prazo=prazo)
    for dia in ("2026-10-07", "2026-10-08", "2026-10-09"):
        pd.testing.assert_frame_equal(
            pd.read_parquet(tmp_path / "sem_prazo" / "selo" / f"{dia}.parquet"),
            pd.read_parquet(tmp_path / "com_prazo" / "selo" / f"{dia}.parquet"),
        )


def test_carga_com_minutos_nao_sela_depois_do_prazo(tmp_path, monkeypatch, capsys):
    """O orçamento `--minutos` vale para a rodada inteira: coleta e selo."""
    _tres_dias_coletados(tmp_path)
    monkeypatch.setattr(coletor, "simbolos_do_sp500", lambda: {"AAPL"})
    monkeypatch.setattr(coletor.time, "monotonic", _relogio_que_avanca(61.0))
    pedidos: list = []
    codigo = coletor.main(
        ["--data", "2026-10-06", "--minutos", "2", "--pasta", str(tmp_path)],
        _iex_falsa(None),
        _oficiais({"AAPL": 228.0}, pedidos),
    )
    assert codigo == 0
    # leituras: prazo em 0 s (+120 s), coleta em 61 s, selos em 122 s em diante: já passou
    assert pedidos == []
    assert "3 dias ficam sem selo" in capsys.readouterr().out
