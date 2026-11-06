"""DataJud por número de processo, só para uso interno (plano dos processos de 03/11/2026, PR 3).

Sem internet: o cliente é um dublê. A chave vem do ambiente e nunca aparece no log nem no arquivo.
"""

import json
import logging
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from base.arquivo import datajud
from base.arquivo.cliente_http import ClienteHttp
from base.arquivo.coleta import ErroDeDescoberta, Resposta
from base.arquivo.ritmo import Ritmo
from base.numero_cnj import digito_esperado
from src import acervo

CHAVE = "chave-de-teste-que-nunca-aparece"
AGORA = datetime(2026, 11, 8, 14, 0, tzinfo=UTC)


def _numero(segmento: str, tribunal: str, sequencial: str = "0001234") -> str:
    ano, origem = "2024", "0100"
    digito = digito_esperado(sequencial, ano, segmento, tribunal, origem)
    return f"{sequencial}{digito}{ano}{segmento}{tribunal}{origem}"


@pytest.fixture(autouse=True)
def _chave(monkeypatch):
    monkeypatch.setenv(datajud.VARIAVEL_DA_CHAVE, CHAVE)


# --- o tribunal sai do número, nunca do dado ---------------------------------------------------


@pytest.mark.parametrize(
    ("segmento", "tribunal", "apelido"),
    [
        ("8", "26", "tjsp"),
        ("8", "07", "tjdft"),
        ("8", "13", "tjmg"),
        ("4", "03", "trf3"),
        ("4", "06", "trf6"),
        ("6", "26", "tre-sp"),
        ("6", "00", "tse"),
        ("3", "00", "stj"),
        ("7", "00", "stm"),
        ("9", "13", "tjmmg"),
    ],
)
def test_o_apelido_do_tribunal_vem_do_numero(segmento, tribunal, apelido):
    endereco = datajud.endereco_do_tribunal(_numero(segmento, tribunal))
    assert (
        endereco
        == f"https://api-publica.datajud.cnj.jus.br/api_publica_{apelido}/_search"
    )


@pytest.mark.parametrize(
    "numero",
    [
        _numero(
            "5", "02"
        ),  # Justiça do Trabalho: fica de fora (Resolução CNJ 121/2010)
        _numero("1", "00"),  # STF: não está no DataJud
        _numero("8", "99"),  # tribunal que não existe
        _numero("9", "01"),  # o Acre não tem tribunal militar
        "00012340020248260100",  # dígito verificador errado
        "../../outro-host",
    ],
)
def test_numero_sem_tribunal_no_datajud_nao_vira_endereco(numero):
    assert datajud.endereco_do_tribunal(numero) is None


def test_todo_endereco_fica_no_host_do_datajud():
    for apelido in datajud.APELIDOS_VALIDOS:
        partes = urlsplit(datajud._endereco(apelido))
        assert (partes.scheme, partes.hostname) == (
            "https",
            "api-publica.datajud.cnj.jus.br",
        )


# --- a consulta ------------------------------------------------------------------------------


class _Cliente:
    def __init__(self, corpo: dict):
        self.corpo = corpo
        self.pedidos: list[dict] = []

    def ler(self, url, *, metodo="GET", cabecalhos=None, corpo=None):
        self.pedidos.append(
            {
                "url": url,
                "metodo": metodo,
                "cabecalhos": dict(cabecalhos or {}),
                "corpo": corpo,
            }
        )
        return Resposta(
            url, json.dumps(self.corpo).encode(), {"content-type": "application/json"}
        )


RESPOSTA = {
    "hits": {
        "total": {"value": 1},
        "hits": [
            {
                "_source": {
                    "numeroProcesso": "x",
                    "classe": {"codigo": 7, "nome": "Procedimento Comum Cível"},
                    "movimentos": [{"codigo": 26, "dataHora": "2024-05-01T10:00:00Z"}],
                }
            }
        ],
    }
}


def test_obter_faz_post_com_a_chave_e_grava_sem_ela(tmp_path: Path):
    numero = _numero("8", "26")
    alvo = datajud.alvo(numero, date(2026, 10, 30))
    assert (
        "#" in alvo.url
    )  # o fragmento separa os alvos do mesmo tribunal; não vai no pedido
    cliente = _Cliente(RESPOSTA)
    assert alvo.obter is not None
    alvo.obter(cliente, tmp_path / "r.json")

    (pedido,) = cliente.pedidos
    assert pedido["metodo"] == "POST"
    assert (
        pedido["url"]
        == "https://api-publica.datajud.cnj.jus.br/api_publica_tjsp/_search"
    )
    assert pedido["cabecalhos"]["Authorization"] == f"APIKey {CHAVE}"
    assert json.loads(pedido["corpo"]) == {
        "query": {"match": {"numeroProcesso": numero}}
    }

    gravado = (tmp_path / "r.json").read_text(encoding="utf-8")
    assert CHAVE not in gravado
    conteudo = json.loads(gravado)
    assert conteudo["consulta"] == {"numero": numero, "tribunal": "tjsp"}
    assert conteudo["total_na_fonte"] == 1
    assert conteudo["processos"][0]["classe"]["codigo"] == 7


def test_resposta_sem_hits_e_erro(tmp_path: Path):
    alvo = datajud.alvo(_numero("8", "26"), date(2026, 10, 30))
    assert alvo.obter is not None
    with pytest.raises(ValueError, match="DataJud"):
        alvo.obter(_Cliente({"error": "algo"}), tmp_path / "r.json")


def test_sem_a_chave_a_descoberta_falha_dizendo_o_nome_da_variavel(monkeypatch):
    monkeypatch.delenv(datajud.VARIAVEL_DA_CHAVE)
    descobrir = datajud.descobrir(
        lambda: {_numero("8", "26"): date(2026, 10, 1)}, frozenset
    )
    with pytest.raises(ErroDeDescoberta, match=datajud.VARIAVEL_DA_CHAVE):
        descobrir(None, AGORA)  # type: ignore[arg-type]


def test_a_chave_nunca_vai_para_o_log(tmp_path: Path, caplog):
    caplog.set_level(logging.DEBUG)

    class _Falha(_Cliente):
        def ler(self, url, **kwargs):
            super().ler(url, **kwargs)
            raise RuntimeError("HTTP 500")

    alvo = datajud.alvo(_numero("8", "26"), date(2026, 10, 30))
    assert alvo.obter is not None
    with pytest.raises(RuntimeError) as erro:
        alvo.obter(_Falha({}), tmp_path / "r.json")
    assert CHAVE not in caplog.text and CHAVE not in str(erro.value)
    assert CHAVE not in repr(alvo)


# --- quais processos -------------------------------------------------------------------------


def test_descobrir_consulta_cada_processo_da_base_e_pula_o_trabalho():
    tjsp, trf3, trabalho = _numero("8", "26"), _numero("4", "03"), _numero("5", "02")
    processos = {
        tjsp: date(2026, 10, 1),
        trf3: date(2026, 9, 1),
        trabalho: date(2026, 10, 2),
    }
    alvos = datajud.descobrir(lambda: processos, frozenset)(None, AGORA)  # type: ignore[arg-type]
    assert [datajud.da_chave(a.url) for a in alvos] == [
        (tjsp, date(2026, 10, 1)),
        (trf3, date(2026, 9, 1)),
    ]


def test_processo_ja_consultado_so_volta_se_o_djen_mostrar_comunicacao_nova():
    parado, andou = _numero("8", "26", "0000001"), _numero("8", "26", "0000002")
    guardadas = frozenset(
        {
            datajud.alvo(parado, date(2026, 9, 1)).url,
            datajud.alvo(andou, date(2026, 9, 1)).url,
        }
    )
    processos = {parado: date(2026, 9, 1), andou: date(2026, 10, 15)}
    alvos = datajud.descobrir(lambda: processos, lambda: guardadas)(None, AGORA)  # type: ignore[arg-type]
    assert [datajud.da_chave(a.url) for a in alvos] == [(andou, date(2026, 10, 15))]


def test_descobrir_respeita_o_maximo_por_rodada(monkeypatch):
    monkeypatch.setattr(datajud, "MAXIMO_DE_PROCESSOS_POR_RODADA", 2)
    processos = {_numero("8", "26", f"{i:07d}"): date(2026, 10, i) for i in range(1, 6)}
    alvos = datajud.descobrir(lambda: processos, frozenset)(None, AGORA)  # type: ignore[arg-type]
    assert [datajud.da_chave(a.url)[1] for a in alvos] == [
        date(2026, 10, 5),
        date(2026, 10, 4),
    ]


def test_sem_a_tabela_do_djen_a_descoberta_falha():
    with pytest.raises(ErroDeDescoberta, match="processos_comunicacoes"):
        datajud.descobrir(lambda: None, frozenset)(None, AGORA)  # type: ignore[arg-type]


def test_tudo_ja_consultado_repete_uma_guardada_sem_pedir():
    numero = _numero("8", "26")
    guardada = datajud.alvo(numero, date(2026, 9, 1)).url
    descobrir = datajud.descobrir(
        lambda: {numero: date(2026, 9, 1)}, lambda: frozenset({guardada})
    )
    (alvo,) = descobrir(None, AGORA)  # type: ignore[arg-type]
    assert alvo.url == guardada


def test_a_fonte_e_semanal_com_pausa_e_o_bruto_fica_no_restrito():
    fonte = datajud.fonte(dict, frozenset)
    assert (fonte.id, fonte.grupo, fonte.tipo) == (
        "datajud-processos",
        "semanal",
        "json",
    )
    assert fonte.pausa_minima >= 1
    relativo = acervo.caminho_relativo(
        fonte.id, "https://api-publica.datajud.cnj.jus.br/x", b"{}", AGORA, ".json"
    )
    assert relativo.startswith("restrito/datajud-processos/")


# --- 429: espera e repete --------------------------------------------------------------------


class _Resposta429:
    def __init__(self, status: int, corpo: bytes = b"{}"):
        self.status_code = status
        self.headers = {"Retry-After": "7"} if status == 429 else {}
        self.content = corpo
        self.url = "https://api-publica.datajud.cnj.jus.br/api_publica_tjsp/_search"

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def close(self):
        pass


def test_429_espera_o_retry_after_e_repete_o_post(tmp_path: Path):
    esperas: list[float] = []
    cliente = ClienteHttp(
        Ritmo(lambda url: None, relogio=lambda: 0.0, esperar=esperas.append)
    )
    respostas = [_Resposta429(429), _Resposta429(200, json.dumps(RESPOSTA).encode())]
    pedidos: list[tuple[str, dict]] = []

    def request(metodo, url, **kwargs):
        pedidos.append((metodo, kwargs))
        return respostas.pop(0)

    cliente.sessao.request = request  # type: ignore[method-assign]
    alvo = datajud.alvo(_numero("8", "26"), date(2026, 10, 30))
    assert alvo.obter is not None
    destino = tmp_path / "r.json"
    alvo.obter(cliente, destino)

    assert [m for m, _ in pedidos] == ["POST", "POST"]
    assert all(k["data"] == pedidos[0][1]["data"] for _, k in pedidos)
    assert 7 in esperas
    assert json.loads(destino.read_text(encoding="utf-8"))["total_na_fonte"] == 1
