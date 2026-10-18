"""Arquivos diários da B3 no arquivista: posições em aberto (aluguel e derivativos) e empréstimos.

A B3 só deixa os últimos ~21 pregões no ar (BDI, `arquivos.b3.com.br/bdi`): quem não baixa todo dia
perde o histórico. Só arquivo (cópia bruta datada, só pesquisa); o CSV abaixo é inventado.
"""

import dataclasses
import gzip
import json
from datetime import UTC, date, datetime, timedelta

import pytest
import requests

from base.arquivo import coleta, destinos, fontes
from base.arquivo.coleta import Resposta
from src.banco import coletas

AGORA = datetime(2026, 10, 14, 5, tzinfo=UTC)  # 2h em Brasília
DIA = date(2026, 10, 13)
IDS = ("b3-emprestimo-posicoes", "b3-derivativos-posicoes", "b3-emprestimo-resumo")
TABELA_DE = {
    "b3-emprestimo-posicoes": "BTBLendingOpenPosition",
    "b3-derivativos-posicoes": "OpenPositionsEquities",
    "b3-emprestimo-resumo": "BTBLoanBalance",
}
CABECALHO = "Ticker symbol;Segment;Open interest\n"
CSV_DO_DIA = CABECALHO + "ICFZ26;AGRIBUSINESS;2944\nBGIV26;AGRIBUSINESS;22259\n"


def _alvo(id_: str, dia: date = DIA) -> coleta.Alvo:
    [alvo] = [a for a in fontes.POR_ID[id_].descobrir(None, AGORA) if str(dia) in a.url]
    return alvo


class B3Falsa:
    """O BDI em memória: (tabela, dia) -> CSV (`None` = 404). Guarda cada pedido recebido."""

    def __init__(self, csvs: dict[tuple[str, str], str | None]):
        self.csvs = csvs
        self.pedidos: list[dict] = []

    def ler(self, url, *, metodo="GET", cabecalhos=None, corpo=None):
        pedido = json.loads(corpo)
        self.pedidos.append(
            {"url": url, "metodo": metodo, "corpo": pedido, "cabecalhos": cabecalhos}
        )
        texto = self.csvs.get((pedido["Name"], pedido["Date"]), CABECALHO)
        if texto is None:
            resposta = requests.Response()
            resposta.status_code = 404
            raise requests.HTTPError("404", response=resposta)
        return Resposta(url, texto.encode("utf-8-sig"), {})


def _fonte_de_um_dia(id_: str, dia: date = DIA) -> coleta.Fonte:
    alvo = _alvo(id_, dia)
    return dataclasses.replace(
        fontes.POR_ID[id_], descobrir=lambda cliente, agora: [alvo]
    )


def _rodar(cliente, tmp_path, id_, rodada=0, dia: date = DIA):
    return coleta.arquivar(
        _fonte_de_um_dia(id_, dia),
        cliente,
        AGORA + timedelta(hours=rodada),
        tmp_path / "temporario",
        pausa=0,
        espaco=lambda pasta: (900 * 1024**3, 800 * 1024**3),
    )


def _linhas(banco):
    with banco.connect() as conexao:
        return coletas.ultimas(conexao)


@pytest.mark.parametrize("id_", IDS)
def test_fonte_diaria_so_de_arquivo_e_com_pausa(id_):
    fonte = fontes.POR_ID[id_]
    assert (fonte.grupo, fonte.pesada, fonte.vigia) == ("diaria", False, False)
    assert fonte.pausa_minima > 0  # um pedido por vez, sem sobrecarregar a B3


@pytest.mark.parametrize("id_", IDS)
def test_alvos_cobrem_os_dias_uteis_da_janela(id_):
    alvos = fontes.POR_ID[id_].descobrir(None, AGORA)
    dias = [a.url.rsplit("data=", 1)[-1] for a in alvos]
    assert dias[0] == "2026-09-15"  # 21 pregões atrás, como o BDI (D-21)
    assert dias[-1] == "2026-10-14"
    assert (
        len(dias) == len(set(dias)) == 22
    )  # feriado e hoje entram: respondem sem dados
    assert not any(date.fromisoformat(d).weekday() >= 5 for d in dias)
    assert all(f"tabela={TABELA_DE[id_]}" in a.url for a in alvos)
    assert {a.extensao for a in alvos} == {".csv"}


def test_cada_fonte_tem_endereco_proprio_por_dia():
    todos = [a.url for i in IDS for a in fontes.POR_ID[i].descobrir(None, AGORA)]
    assert len(todos) == len(set(todos)) == 3 * 22


def test_pedido_ao_bdi_e_um_post_honesto_com_a_tabela_e_o_dia(banco, tmp_path):
    cliente = B3Falsa({("OpenPositionsEquities", "2026-10-13"): CSV_DO_DIA})
    _rodar(cliente, tmp_path, "b3-derivativos-posicoes")
    [pedido] = cliente.pedidos
    assert pedido["metodo"] == "POST"
    assert pedido["url"].startswith("https://arquivos.b3.com.br/bdi/table/export/csv")
    assert pedido["corpo"] == {
        "Name": "OpenPositionsEquities",
        "Date": "2026-10-13",
        "FinalDate": "2026-10-13",
    }
    # nada de se passar por navegador: o `User-Agent` é o do cliente do arquivista
    assert "User-Agent" not in (pedido["cabecalhos"] or {})


def test_csv_do_dia_e_guardado_e_registrado(banco, tmp_path):
    cliente = B3Falsa({("OpenPositionsEquities", "2026-10-13"): CSV_DO_DIA})
    resultado = _rodar(cliente, tmp_path, "b3-derivativos-posicoes")
    assert (resultado.novos, resultado.falhas, resultado.sem_arquivo) == (1, [], 0)
    [linha] = _linhas(banco)
    assert (linha.situacao, linha.fonte) == ("ok", "b3-derivativos-posicoes")
    assert ".csv" in linha.caminho_do_original  # o acervo comprime (.csv.gz)
    guardado = next((tmp_path / "acervo").rglob("*.csv.gz"))
    assert b"ICFZ26;AGRIBUSINESS;2944" in gzip.decompress(guardado.read_bytes())


@pytest.mark.parametrize("resposta", [CABECALHO, "", None])
def test_dia_sem_dados_nao_derruba_a_rodada(banco, tmp_path, resposta):
    # feriado ou dia que ainda não saiu: só o cabeçalho, corpo vazio ou 404
    cliente = B3Falsa({("BTBLoanBalance", "2026-10-13"): resposta})
    resultado = _rodar(cliente, tmp_path, "b3-emprestimo-resumo")
    assert (resultado.novos, resultado.falhas, resultado.sem_arquivo) == (0, [], 1)
    [linha] = _linhas(banco)
    assert linha.situacao == "nao_encontrado"
    assert linha.caminho_do_original is None
    assert not list((tmp_path / "acervo").rglob("*.csv*"))


def test_erro_do_servidor_e_falha_e_nao_sem_arquivo(banco, tmp_path):
    class Fora(B3Falsa):
        def ler(self, url, **argumentos):
            resposta = requests.Response()
            resposta.status_code = 503
            raise requests.HTTPError("503", response=resposta)

    resultado = _rodar(Fora({}), tmp_path, "b3-emprestimo-posicoes")
    assert len(resultado.falhas) == 1
    assert resultado.sem_arquivo == 0


def test_html_no_lugar_do_csv_e_falha(banco, tmp_path):
    cliente = B3Falsa(
        {("BTBLendingOpenPosition", "2026-10-13"): "<html>manutencao</html>"}
    )
    resultado = _rodar(cliente, tmp_path, "b3-emprestimo-posicoes")
    assert len(resultado.falhas) == 1


def test_dia_guardado_depois_do_pregao_nao_e_baixado_de_novo(banco, tmp_path):
    cliente = B3Falsa({("OpenPositionsEquities", "2026-10-13"): CSV_DO_DIA})
    _rodar(cliente, tmp_path, "b3-derivativos-posicoes")
    resultado = _rodar(cliente, tmp_path, "b3-derivativos-posicoes", rodada=24)
    assert resultado.pulados == 1
    assert len(cliente.pedidos) == 1


def test_dia_baixado_no_proprio_pregao_e_baixado_de_novo(banco, tmp_path):
    # 14/10 às 2h já tinha um pedido do dia 14 (parcial): a rodada das 22h pega a versão final
    dia = date(2026, 10, 14)
    cliente = B3Falsa({("OpenPositionsEquities", "2026-10-14"): CSV_DO_DIA})
    _rodar(cliente, tmp_path, "b3-derivativos-posicoes", dia=dia)
    _rodar(cliente, tmp_path, "b3-derivativos-posicoes", rodada=2, dia=dia)
    assert len(cliente.pedidos) == 2


def test_destino_so_pesquisa_e_cita_a_proibicao_de_coleta():
    for id_ in IDS:
        destino = destinos.DESTINOS[id_]
        assert destino.tipo == destinos.SO_PESQUISA
        assert "coleta automatizada" in destino.porque
        assert "18/10/2026" in destino.porque


def test_termos_da_b3_com_a_proibicao_entram_na_lista_de_vigias():
    assert "termos-b3-coleta-automatizada" in fontes.TERMOS
    assert destinos.DESTINOS["termos-b3-coleta-automatizada"].tipo == destinos.VIGIA


def test_licenca_da_fonte_nova_e_a_da_b3_so_pesquisa():
    for id_ in IDS:
        assert coletas.licenca_da_fonte(id_) == coletas.LICENCAS["b3"]
        assert coletas.revenda_da_fonte(id_) == coletas.REVENDA["b3"]


def test_cliente_http_aceita_corpo_no_post(monkeypatch):
    from base.arquivo.cliente_http import ClienteHttp

    visto = {}

    class Sessao:
        def request(self, metodo, url, headers, timeout, data=None):
            visto.update(metodo=metodo, data=data, headers=headers)
            resposta = requests.Response()
            resposta.status_code = 200
            resposta._content = b"ok"
            resposta.url = url
            return resposta

    cliente = ClienteHttp()
    cliente.sessao = Sessao()
    cliente.ler("https://exemplo/x", metodo="POST", corpo=b'{"a": 1}')
    assert visto["data"] == b'{"a": 1}'
    assert visto["metodo"] == "POST"
