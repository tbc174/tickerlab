"""Testes de src/compartilhamentos.py: o código do link, o prazo e a ficha congelada (onda 4)."""

import hashlib
from datetime import UTC, date, datetime, timedelta

import pandas as pd
import pytest

from src import compartilhamentos as comp
from src import ficha
from src.ficha import Checagem, Ficha, PedidoDaFicha, Resultado, Situacao
from src.protecoes import Protecoes

AGORA = datetime(2026, 10, 13, 23, 30, tzinfo=UTC)


# --- código e prazo ------------------------------------------------------------------------


def test_codigo_tem_256_bits_e_so_o_hash_vai_ao_banco():
    codigo = comp.novo_codigo()
    assert len(codigo) == 43  # 32 bytes em base64 sem o "=" do fim
    assert comp.codigo_valido(codigo)
    assert comp.novo_codigo() != codigo
    guardado = comp.hash_do_codigo(codigo)
    assert guardado == hashlib.sha256(codigo.encode()).hexdigest()
    assert len(guardado) == 64 and codigo not in guardado


@pytest.mark.parametrize(
    "texto",
    ["", "a" * 42, "a" * 44, "a" * 42 + "/", "a" * 42 + " ", "a" * 42 + "=", None, 123],
)
def test_formato_do_codigo_recusa_o_resto(texto):
    assert not comp.codigo_valido(texto)


def test_formato_do_codigo_aceita_base64_de_url():
    assert comp.codigo_valido("Ab0_-" + "x" * 38)


def test_prazos():
    assert comp.PRAZOS_EM_DIAS == (7, 30, 90)
    assert comp.PRAZO_PADRAO == 30
    assert comp.expira_em(AGORA, 30) == AGORA + timedelta(days=30)
    for dias in (0, 1, 31, 365, -7):
        with pytest.raises(ValueError):
            comp.expira_em(AGORA, dias)


# --- a ficha congelada ---------------------------------------------------------------------

CHECAGENS = (
    Checagem(ficha.PERGUNTA_FORA_DO_PERIODO, Situacao.PASSOU, "Rendeu 8,0% fora."),
    Checagem(ficha.PERGUNTA_VIZINHOS, Situacao.NAO_SE_APLICA, "Nada foi ajustado."),
    Checagem(ficha.PERGUNTA_CUSTOS, Situacao.NAO_PASSOU, "Perdeu para o CDI."),
    Checagem(ficha.PERGUNTA_QUEDAS, Situacao.SEM_MEDIDA, "Poucas operações."),
    Checagem(ficha.PERGUNTA_ACASO, Situacao.PASSOU, "p = 0,01."),
)


def _pedido(**mudar) -> PedidoDaFicha:
    dias = pd.date_range("2024-01-02", "2025-12-30", freq="B")
    dados = pd.DataFrame({"Close": range(len(dias))}, index=dias)
    base = {
        "dados": dados,
        "estrategia": "Cruzamento de médias",
        "parametros": {"curta": 20, "longa": 50, "tipo": "Simples"},
        "custo_por_operacao": 0.001,
        "capital_inicial": 250_000.0,
        "protecoes": Protecoes(stop_loss=0.1),
    }
    return PedidoDaFicha(**{**base, **mudar})


def _congelada(**mudar) -> dict:
    argumentos = {
        "resultado": Ficha(CHECAGENS, tentativas=37),
        "pedido": _pedido(),
        "ticker": "PETR4.SA",
        "texto_das_tentativas": "Você testou 3 configurações em PETR4.",
        "fonte": "Yahoo Finance",
        "agora": AGORA,
    }
    return comp.congelar_ficha(**{**argumentos, **mudar})


def test_congelar_e_ler_a_ficha_devolve_o_mesmo():
    lida = comp.ler_ficha_congelada(_congelada())
    assert lida.ticker == "PETR4.SA"
    assert lida.estrategia == "Cruzamento de médias"
    assert lida.parametros == {"curta": 20, "longa": 50, "tipo": "Simples"}
    assert lida.protecoes == {"stop_loss": 0.1}  # só o que difere do padrão
    assert lida.custo_por_operacao == 0.001
    assert (lida.inicio, lida.fim) == (date(2024, 1, 2), date(2025, 12, 30))
    assert lida.checagens == CHECAGENS
    assert lida.tentativas == 37
    esperado = Ficha(CHECAGENS, tentativas=37).veredito
    assert lida.veredito == esperado
    assert lida.texto_das_tentativas == "Você testou 3 configurações em PETR4."
    assert lida.fonte == "Yahoo Finance"
    assert lida.calculada_em == AGORA


def test_ficha_compartilhada_traz_data_e_aviso():
    lida = comp.ler_ficha_congelada(_congelada())
    assert lida.veredito.texto.endswith(ficha.AVISO)
    assert lida.calculada_em.tzinfo is not None


def test_ficha_usa_o_custo_que_a_checagem_usou():
    """A ficha nunca usa custo abaixo do padrão: o congelado mostra o custo de verdade."""
    congelada = _congelada(pedido=_pedido(custo_por_operacao=0.0))
    assert comp.ler_ficha_congelada(congelada).custo_por_operacao == (
        ficha.custo_da_checagem(0.0)
    )


def test_ficha_congelada_nao_leva_o_capital_nem_os_precos():
    congelada = _congelada()
    assert "capital_inicial" not in congelada
    assert "250000" not in repr(congelada)
    assert "dados" not in congelada


def test_ficha_congelada_e_json_puro():
    import json

    assert json.loads(json.dumps(_congelada())) == _congelada()


def test_titulo_da_ficha():
    assert comp.titulo_da_ficha("PETR4.SA", "Cruzamento de médias") == (
        "Foi sorte? Cruzamento de médias em PETR4"
    )
    assert comp.titulo_da_ficha("AAPL", "Comprar e segurar") == (
        "Foi sorte? Comprar e segurar em AAPL"
    )
    # índice com o código da tela, sem o ^ do Yahoo (ADR 0065)
    assert comp.titulo_da_ficha("^BVSP", "Comprar e segurar") == (
        "Foi sorte? Comprar e segurar em IBOV"
    )


def _estragar(chave: str, valor: object) -> dict:
    congelada = _congelada()
    congelada[chave] = valor
    return congelada


@pytest.mark.parametrize(
    "estragada",
    [
        None,
        [],
        "texto",
        _estragar("versao", 2),
        _estragar("ticker", "<script>"),
        _estragar("estrategia", ""),
        _estragar("estrategia", "x" * 81),
        _estragar("parametros", {"a" * 41: 1}),
        _estragar("parametros", {f"p{i}": i for i in range(31)}),
        _estragar("parametros", {"curta": float("nan")}),
        _estragar("parametros", {"curta": [1, 2]}),
        _estragar("custo_por_operacao", 0.5),
        _estragar("custo_por_operacao", "0.001"),
        _estragar("inicio", "ontem"),
        _estragar("fim", "2023-01-01"),  # antes do início
        _estragar("checagens", []),
        _estragar(
            "checagens", [{"pergunta": "p", "situacao": "talvez", "explicacao": "e"}]
        ),
        _estragar("checagens", [{"pergunta": "p", "situacao": "passou"}] * 1),
        _estragar(
            "checagens",
            [{"pergunta": "p", "situacao": "passou", "explicacao": "e"}] * 11,
        ),
        _estragar(
            "checagens",
            [{"pergunta": "p", "situacao": "passou", "explicacao": "x" * 2001}],
        ),
        _estragar("tentativas", -1),
        _estragar("tentativas", True),
        _estragar("resultado", "ótimo"),
        _estragar("titulo", ""),
        _estragar("texto", "x" * 2001),
        _estragar("calculada_em", "2026-10-13T23:30:00"),  # sem fuso
        _estragar("fonte", "x" * 201),
    ],
)
def test_ler_ficha_recusa_lixo(estragada):
    with pytest.raises(ValueError):
        comp.ler_ficha_congelada(estragada)


def test_ler_ficha_recusa_veredito_que_as_checagens_nao_dao():
    """Um "passou" com uma checagem que não passou seria uma ficha adulterada."""
    with pytest.raises(ValueError):
        comp.ler_ficha_congelada(_estragar("resultado", Resultado.PASSOU.value))


# --- o que a tela usa (onda 4, PR 4) -------------------------------------------------------


def test_endereco_do_link_leva_o_codigo_depois_do_jogo_da_velha():
    codigo = comp.novo_codigo()
    assert comp.endereco_do_link(codigo) == (
        f"https://app.tickerlab.com.br/novo/c#{codigo}"
    )


def test_fonte_dos_precos_pela_origem_dos_dados():
    assert comp.fonte_dos_precos(None) == "Yahoo Finance"
    assert comp.fonte_dos_precos("exemplo") == "dados de exemplo guardados no projeto"
    assert "Yahoo não respondeu" in comp.fonte_dos_precos("cache_antigo")


def test_textos_da_tela():
    assert comp.rotulo_do_prazo(30) == "30 dias"
    assert "não aparece de novo" in comp.AVISO_DO_LINK_CRIADO
    for texto in (comp.O_QUE_FICA_VISIVEL["ficha"], comp.O_QUE_FICA_VISIVEL["pdf"]):
        assert "nome" in texto and "e-mail" in texto
    assert set(comp.NOMES_DOS_TIPOS) == set(comp.TIPOS)


def test_impressao_da_ficha_ignora_a_hora_e_pega_o_ativo():
    """A tela usa a impressão para não mostrar o link de outra ficha (achado 2a do Codex)."""
    base = comp.impressao_da_ficha(_congelada())
    assert comp.impressao_da_ficha(_congelada(agora=AGORA + timedelta(hours=1))) == base
    assert comp.impressao_da_ficha(_congelada(ticker="VALE3.SA")) != base
