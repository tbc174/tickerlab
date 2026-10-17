"""E-mail do boletim diário da base (`base/boletim/email.py`): destinatário único, as duas partes,
o aviso, e o envio pelo Resend (dublê, sem internet)."""

from datetime import date
from types import SimpleNamespace

import pytest

from base.boletim import analises as an
from base.boletim import email as em
from base.boletim import fotografia as fo
from base.boletim import tarefas as ta
from base.boletim.leitura_ia import Leitura

FOTO_ANTES = {
    "formato": fo.FORMATO,
    "tabelas": {
        "cda/2026": {"linhas": 100, "sha256": "a", "bytes": 1000, "versoes_guardadas": 0, "licenca": None, "contrato": None, "problemas_do_contrato": 0},
        "rede/ligacoes": {"linhas": 50, "sha256": "b", "bytes": 500, "versoes_guardadas": 1, "licenca": None, "contrato": None, "problemas_do_contrato": 0},
    },
}  # fmt: skip
FOTO_AGORA = {
    "formato": fo.FORMATO,
    "tabelas": {
        "cda/2026": {"linhas": 130, "sha256": "c", "bytes": 1300, "versoes_guardadas": 0, "licenca": "vendavel", "contrato": "com_problemas", "problemas_do_contrato": 4},
        "rede/ligacoes": {"linhas": 50, "sha256": "b", "bytes": 500, "versoes_guardadas": 1, "licenca": None, "contrato": None, "problemas_do_contrato": 0},
        "ratings/ratings": {"linhas": 42, "sha256": "d", "bytes": 90, "versoes_guardadas": 0, "licenca": "vendavel", "contrato": "aprovada", "problemas_do_contrato": 0},
    },
}  # fmt: skip
SECAO = an.Secao(
    nome="ratings",
    titulo="Ratings publicados na CVM",
    pergunta="Como se distribuem as notas?",
    kpis=[("ratings lidos", "42")],
    cabecalho=["Agência", "Total"],
    linhas=[["Fitch", "15"]],
    achado="35 de 42 notas estão no grau de investimento.",
    limites="Só o que o extrator leu.",
    fonte="CVM",
)
TAREFAS = ta.EstadoDasTarefas(
    disponivel=True,
    total=30,
    em_dia=18,
    falhas=[
        ta.EstadoDaTarefa(
            "rede", "falha", "2026-10-17T06:10:00-03:00", "rede: sem memória"
        )
    ],
    atrasadas=[ta.EstadoDaTarefa("ratings-tabela", "atrasada", horas=30)],
)


LEITURA = Leitura("A base cresceu 72 linhas.")


def _conteudo(leitura=LEITURA, antes=FOTO_ANTES):
    return em.Conteudo(
        dia=date(2026, 10, 17),
        dia_anterior=date(2026, 10, 16) if antes else None,
        foto=FOTO_AGORA,
        foto_anterior=antes,
        tarefas=TAREFAS,
        secao=SECAO,
        leitura=leitura,
        proxima="Dívida ativa da União (empresas)",
    )


def test_destinatario_unico(monkeypatch):
    monkeypatch.setenv(em.VARIAVEL_DO_DESTINATARIO, "autor@exemplo.com.br")
    assert em.destinatario() == "autor@exemplo.com.br"
    for ruim in (
        "",
        "a@b.com, c@d.com",
        "a@b.com;c@d.com",
        "sem-arroba",
        "a@b.com c@d.com",
    ):
        monkeypatch.setenv(em.VARIAVEL_DO_DESTINATARIO, ruim)
        with pytest.raises(em.DestinatarioInvalidoError):
            em.destinatario()
    monkeypatch.delenv(em.VARIAVEL_DO_DESTINATARIO)
    with pytest.raises(em.DestinatarioInvalidoError):
        em.destinatario()


def test_email_tem_a_evolucao_a_analise_e_o_aviso():
    e = em.montar(_conteudo())
    for parte in (
        "Ratings publicados na CVM",  # análise do dia
        "35 de 42 notas",  # achado
        "ratings/ratings",  # tabela nova
        "cda/2026",  # mudou
        "rede: sem memória",  # falha
        "ratings-tabela",  # atrasada
        "16/10/2026",  # desde quando
        "A base cresceu 72 linhas.",  # parágrafo da IA
        "Dívida ativa da União",  # amanhã
        "Não é recomendação de investimento",
    ):
        assert parte in e.html, parte
        assert parte in e.texto, parte
    assert e.assunto.startswith("TickerLab · Boletim da base · 17/10")
    assert "1 falha" in e.assunto


def test_sem_paragrafo_diz_por_que():
    e = em.montar(_conteudo(leitura=Leitura(None, 'palavra proibida ("crise")')))
    assert "palavra proibida (&quot;crise&quot;)" in e.html
    assert "sem o parágrafo" in e.texto


def test_primeiro_dia_e_so_o_retrato():
    e = em.montar(_conteudo(antes=None))
    assert "Primeiro retrato" in e.html
    assert "222" in e.texto  # linhas de agora


def test_fatos_para_a_ia_usam_os_numeros_do_email():
    fatos = em.fatos(_conteudo())
    assert "+30" in fatos  # linhas a mais (130 + 42 − 100 = +72 no total; +30 na cda)
    assert "+72" in fatos
    assert "35 de 42 notas" in fatos
    assert "rede" in fatos  # a falha


def test_envio_recusado_sai_com_erro():
    def transporte(*_, **__):
        return SimpleNamespace(ok=False, status_code=403, json=dict)

    with pytest.raises(em.EnvioFalhouError):
        em.enviar(
            em.montar(_conteudo()),
            "autor@exemplo.com.br",
            date(2026, 10, 17),
            "re_x",
            transporte,
        )


def test_envio_sem_cabecalho_de_saida_e_com_idempotencia_do_dia():
    pedidos = []

    def transporte(url, **pedido):
        pedidos.append(pedido)
        return SimpleNamespace(ok=True, status_code=200, json=lambda: {"id": "msg_1"})

    assert em.enviar(em.montar(_conteudo()), "autor@exemplo.com.br", date(2026, 10, 17), "re_x", transporte) == "msg_1"  # fmt: skip
    corpo = pedidos[0]["json"]
    assert corpo["to"] == ["autor@exemplo.com.br"]
    assert "headers" not in corpo
    assert corpo["from"] == em.REMETENTE_PADRAO
    assert pedidos[0]["headers"]["Idempotency-Key"] == "boletim-da-base-2026-10-17"


def test_tabela_de_conjuntos_mostra_os_que_mudaram_e_corta_o_resto(monkeypatch):
    monkeypatch.setattr(em, "MAXIMO_DE_CONJUNTOS", 1)
    e = em.montar(_conteudo())
    assert "cda" in e.texto  # mudou: entra sempre
    assert "e mais 1 conjunto menor, sem mudança" in e.texto
