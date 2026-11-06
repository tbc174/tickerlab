"""O lote do histórico (leitor v2, ADR 0069): só os "Outros" pelo título, `--simular` sem gastar, teto,
lacre e a ordem do "pode". Cliente de mentira, sem rede."""

import json
from datetime import date
from types import SimpleNamespace

import pytest

from scripts import classificar_topicos_historico as lote
from src import topicos, topicos_modelo
from src.banco import leituras as repo
from src.eventos import FONTE_IPE
from tests.test_leituras import _fato


def _banco_com_fatos(banco):
    with banco.begin() as c:
        _fato(c, "claro", date(2025, 5, 1), assunto="Aquisição de empresa")
        _fato(c, "vago1", date(2025, 6, 1), assunto="Comunicado sobre a Sompo")
        _fato(c, "vago2", date(2025, 7, 1), assunto="Informação ao mercado")
        _fato(c, "depois", date(2026, 5, 1), assunto="Informação ao mercado")
        _fato(
            c,
            "outra",
            date(2025, 6, 2),
            categoria="Comunicado ao Mercado",
            assunto="Nada",
        )


def _selecionar(banco, **opcoes):
    with banco.connect() as c:
        return lote.selecionar(c, **opcoes)


def test_so_os_outros_pelo_titulo_ate_o_lacre(banco):
    _banco_com_fatos(banco)
    achados = {p[0] for p in _selecionar(banco)}
    assert achados == {
        "vago1",
        "vago2",
    }  # nem o claro, nem outra categoria, nem o pós-lacre


def test_teto_corta_os_mais_novos_primeiro(banco):
    _banco_com_fatos(banco)
    assert [p[0] for p in _selecionar(banco, teto=1)] == ["vago2"]


def test_quem_o_modelo_ja_leu_nao_volta(banco):
    _banco_com_fatos(banco)
    with banco.begin() as c:
        repo.gravar_leitura(
            c,
            FONTE_IPE,
            "vago2",
            repo.TOPICO_MODELO,
            "x",
            None,
            {},
            versao=topicos.VERSAO,
        )
    assert [p[0] for p in _selecionar(banco)] == ["vago1"]


class ClienteDoLote:
    """Imita count_tokens e a Batches API; `messages.create` não pode ser chamada."""

    def __init__(self, respostas=None):
        self.contagens, self.lotes = [], []
        self._respostas = respostas or {}
        self.messages = SimpleNamespace(
            count_tokens=self._contar,
            create=lambda **_: pytest.fail("o lote não chama messages.create"),
            batches=SimpleNamespace(
                create=self._criar, retrieve=self._ver, results=self._resultados
            ),
        )

    def _contar(self, **pedido):
        self.contagens.append(pedido)
        return SimpleNamespace(input_tokens=1_000)

    def _criar(self, requests):
        self.lotes.append(requests)
        return SimpleNamespace(id="lote1")

    def _ver(self, _id):
        return SimpleNamespace(processing_status="ended")

    def _resultados(self, _id):
        for pedido in self.lotes[-1]:
            conteudo = pedido["params"]["messages"][0]["content"]
            titulo = conteudo.split("\n")[0].removeprefix("Título: ")
            resposta = self._respostas.get(titulo)
            if resposta is None:
                yield SimpleNamespace(
                    custom_id=pedido["custom_id"],
                    result=SimpleNamespace(type="errored"),
                )
                continue
            mensagem = SimpleNamespace(
                stop_reason="end_turn",
                content=[SimpleNamespace(type="text", text=json.dumps(resposta))],
            )
            yield SimpleNamespace(
                custom_id=pedido["custom_id"],
                result=SimpleNamespace(type="succeeded", message=mensagem),
            )


def _lista():
    return [
        ("p1", "c", date(2025, 6, 1), "Comunicado sobre a Sompo"),
        ("p2", "c", date(2025, 7, 1), "Informação ao mercado"),
    ]


def test_simular_conta_e_nao_cria_lote():
    cliente = ClienteDoLote()
    estimativa = lote.simular(cliente, _lista())
    assert cliente.lotes == []
    assert estimativa.documentos == 2 and estimativa.tokens_de_entrada == 2_000
    # 2.000 tokens de entrada a US$ 0,10/M e 2 × 80 de saída a US$ 0,50/M, pela metade (lote)
    assert estimativa.custo_usd == pytest.approx(
        (2_000 * 0.10 + 160 * 0.50) / 1e6 * 0.5
    )


def test_simular_de_amostra_extrapola():
    cliente = ClienteDoLote()
    estimativa = lote.simular(cliente, _lista() * 10, amostra=3)
    assert len(cliente.contagens) == 3
    assert estimativa.tokens_de_entrada == 20_000  # 1.000 por documento × 20


def test_executar_grava_so_a_resposta_que_vale(banco):
    _banco_com_fatos(banco)
    resposta = {
        "principal": "JV",
        "secundarios": [],
        "trecho": "Comunicado sobre a Sompo",
    }
    cliente = ClienteDoLote({"Comunicado sobre a Sompo": resposta})
    with banco.begin() as c:
        gravados = lote.executar(cliente, c, _selecionar(banco), espera=0)
    assert gravados == 1  # o outro deu erro: fica a regra
    assert cliente.lotes[0][0]["params"]["model"] == topicos_modelo.MODELO
    with banco.connect() as c:
        lidos = repo._topicos_lidos(
            c, FONTE_IPE, repo.TOPICO_MODELO, ["vago1", "vago2"]
        )
    assert list(lidos) == ["vago1"] and lidos["vago1"].principal == "JV"


def test_sem_valor_autorizado_ou_abaixo_da_estimativa_nao_roda():
    estimativa = lote.simular(ClienteDoLote(), _lista())
    with pytest.raises(lote.SemAutorizacao):
        lote.conferir_autorizacao(estimativa, None)
    with pytest.raises(lote.SemAutorizacao):
        lote.conferir_autorizacao(estimativa, estimativa.custo_usd / 2)
    lote.conferir_autorizacao(estimativa, estimativa.custo_usd * 1.2)
