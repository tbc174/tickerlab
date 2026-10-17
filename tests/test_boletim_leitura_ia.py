"""Parágrafo de leitura do boletim pela API (`base/boletim/leitura_ia.py`). O cliente da API é um
dublê: o teste não usa a internet."""

from types import SimpleNamespace

import anthropic
import httpx2

from base.boletim import leitura_ia as li

FATOS = "Linhas na base: 296,8 mi (+1,2 mi desde 16/10). Fatos relevantes em 30 dias: 174, contra 239 em 2025."


class Cliente:
    def __init__(self, texto="", parar="end_turn", erro=None):
        self.pedidos = []
        self._texto, self._parar, self._erro = texto, parar, erro
        self.messages = self

    def create(self, **pedido):
        self.pedidos.append(pedido)
        if self._erro:
            raise self._erro
        return SimpleNamespace(
            stop_reason=self._parar,
            content=[SimpleNamespace(type="text", text=self._texto)],
            usage=SimpleNamespace(input_tokens=900, output_tokens=120),
        )


def test_paragrafo_que_passa_nas_travas():
    cliente = Cliente(
        "A base chegou a 296,8 mi linhas. Os fatos relevantes caíram de 239 para 174."
    )
    leitura = li.escrever_leitura(FATOS, cliente)
    assert leitura.texto.startswith("A base chegou")
    assert leitura.motivo == ""
    pedido = cliente.pedidos[0]
    assert pedido["model"] == li.MODELO
    assert pedido["max_tokens"] <= 400
    assert FATOS in pedido["messages"][0]["content"]


def test_palavra_proibida_tira_o_paragrafo():
    for texto in (
        "Há sinais de crise no setor.",
        "Isso parece fraude.",
        "Recomendamos olhar as debêntures.",
        "Bom momento para comprar.",
    ):
        leitura = li.escrever_leitura(FATOS, Cliente(texto))
        assert leitura.texto is None
        assert "palavra" in leitura.motivo


def test_numero_que_nao_esta_no_boletim_tira_o_paragrafo():
    leitura = li.escrever_leitura(
        FATOS, Cliente("Os fatos relevantes caíram 27,2% no ano.")
    )
    assert leitura.texto is None
    assert "27,2" in leitura.motivo


def test_sem_chave_ou_com_erro_sai_sem_paragrafo(monkeypatch):
    monkeypatch.delenv(li.VARIAVEL_DA_CHAVE, raising=False)
    assert li.escrever_leitura(FATOS).motivo == "sem a chave da API"
    erro = anthropic.APIConnectionError(
        request=httpx2.Request("POST", "https://api.anthropic.com")
    )
    leitura = li.escrever_leitura(FATOS, Cliente(erro=erro))
    assert leitura.texto is None and "API" in leitura.motivo


def test_resposta_cortada_ou_recusada_sai_sem_paragrafo():
    leitura = li.escrever_leitura(FATOS, Cliente("A base", parar="max_tokens"))
    assert leitura.texto is None and "max_tokens" in leitura.motivo
