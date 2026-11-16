"""O custo por pergunta, o teto do mês e o pedido ao SDK do modelo (linha 903), sem rede.

Riscos: (1) a conta do custo errar para menos (o teto deixaria passar); (2) o teto não ser o de R$ 300
convertido; (3) o pedido ao modelo levar ferramenta de servidor (busca, código) ou perder o pensamento, o
esforço e o cache; (4) o chat ligar com qualquer valor da variável; (5) uma volta com JSON ilegível
derrubar a pergunta antes das tentativas.
"""

import asyncio
from types import SimpleNamespace

import anthropic
import pytest

from src import chat
from src.chat import custo
from src.chat import modelo_anthropic as ma
from src.chat.conversa import FimDoTurno, PedidoAoModelo, Recomeco, TextoParcial
from src.planos import LIMITES_DO_CHAT

# ---------------------------------------------------------------- as variáveis


@pytest.mark.parametrize(
    ("valor", "ligado"),
    [("1", True), (" 1 ", True), ("0", False), ("true", False), ("", False)],
)
def test_chat_so_liga_com_1(valor, ligado):
    assert chat.chat_ligado({chat.VARIAVEL_DE_LIGAR: valor}) is ligado
    assert chat.chat_ligado({}) is False


def test_modelo_padrao_e_o_da_variavel():
    assert chat.modelo_do_chat({}) == chat.MODELO_PADRAO == "claude-opus-5-5"
    assert (
        chat.modelo_do_chat({chat.VARIAVEL_DO_MODELO: "claude-sonnet-5-5"})
        == "claude-sonnet-5-5"
    )


def test_chave_do_modelo_so_confere_presenca():
    assert chat.tem_chave_do_modelo({chat.VARIAVEL_DA_CHAVE_DO_MODELO: "x"})
    assert not chat.tem_chave_do_modelo({chat.VARIAVEL_DA_CHAVE_DO_MODELO: " "})
    assert not chat.tem_chave_do_modelo({})


# chaves inventadas: nenhuma de verdade em teste
CHAVE_GERAL = "chave-geral-inventada"
CHAVE_DO_CHAT = "chave-do-chat-inventada"


def test_a_chave_do_chat_e_propria_e_nao_cai_na_geral():
    assert chat.VARIAVEL_DA_CHAVE_DO_MODELO == "ANTHROPIC_API_KEY_CHAT"
    so_a_geral = {"ANTHROPIC_API_KEY": CHAVE_GERAL}
    assert not chat.tem_chave_do_modelo(so_a_geral)
    assert chat.chave_do_modelo(so_a_geral) is None
    so_a_do_chat = {"ANTHROPIC_API_KEY_CHAT": f" {CHAVE_DO_CHAT} "}
    assert chat.tem_chave_do_modelo(so_a_do_chat)
    assert chat.chave_do_modelo(so_a_do_chat) == CHAVE_DO_CHAT


def test_so_a_chave_do_chat_nao_liga_os_outros_usos_pagos(monkeypatch):
    from base.boletim import leitura_ia
    from src import topicos_modelo

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY_CHAT", CHAVE_DO_CHAT)
    assert chat.tem_chave_do_modelo()
    assert topicos_modelo.cliente_da_chave() is None
    assert leitura_ia.cliente_da_chave() is None


class _SdkQueGuarda:
    """Troca o `AsyncAnthropic`: guarda com que chave o cliente seria criado, sem rede."""

    def __init__(self):
        self.chaves: list[object] = []

    def __call__(self, **argumentos):
        self.chaves.append(
            argumentos.get("api_key", "sem api_key: o SDK leria o ambiente")
        )
        return SimpleNamespace(messages=None)


def test_o_cliente_do_sdk_recebe_a_chave_do_chat(monkeypatch):
    sdk = _SdkQueGuarda()
    monkeypatch.setattr(ma.anthropic, "AsyncAnthropic", sdk)
    monkeypatch.setenv("ANTHROPIC_API_KEY", CHAVE_GERAL)
    monkeypatch.setenv("ANTHROPIC_API_KEY_CHAT", CHAVE_DO_CHAT)
    ma.ModeloDaAnthropic("claude-opus-5-5")._cliente_do_sdk()
    assert sdk.chaves == [CHAVE_DO_CHAT]


def test_so_com_a_geral_o_cliente_do_sdk_nao_e_criado(monkeypatch):
    sdk = _SdkQueGuarda()
    monkeypatch.setattr(ma.anthropic, "AsyncAnthropic", sdk)
    monkeypatch.setenv("ANTHROPIC_API_KEY", CHAVE_GERAL)
    monkeypatch.delenv("ANTHROPIC_API_KEY_CHAT", raising=False)
    with pytest.raises(ma.SemChaveDoChat) as erro:
        ma.ModeloDaAnthropic("claude-opus-5-5")._cliente_do_sdk()
    assert sdk.chaves == []
    assert CHAVE_GERAL not in str(erro.value)


# ---------------------------------------------------------------- o custo


def test_custo_pela_tabela_oficial():
    # Opus 5.5: US$ 4 / 20 / 0,20 / 5 por milhão (entrada, saída, cache lido, cache gravado)
    uso = custo.UsoDoModelo(
        entrada=1_000_000,
        saida=1_000_000,
        cache_lido=1_000_000,
        cache_gravado=1_000_000,
    )
    assert custo.custo_em_microdolares("claude-opus-5-5", uso) == 29_200_000
    assert custo.custo_em_microdolares("claude-sonnet-5-5", uso) == 14_600_000


def test_custo_arredonda_para_cima():
    uso = custo.UsoDoModelo(entrada=1)
    # 1 token de entrada do Opus = 4 microdólares exatos; 1 de cache lido = 0,2: vira 1
    assert custo.custo_em_microdolares("claude-opus-5-5", uso) == 4
    assert (
        custo.custo_em_microdolares("claude-opus-5-5", custo.UsoDoModelo(cache_lido=1))
        == 1
    )


def test_pergunta_tipica_fica_abaixo_da_reserva():
    # 6 voltas com 20 mil de entrada (metade do cache) e 2 mil de saída cada
    volta = custo.UsoDoModelo(entrada=10_000, cache_lido=10_000, saida=2_000)
    total = custo.UsoDoModelo()
    for _ in range(LIMITES_DO_CHAT.voltas_de_ferramenta):
        total = total + volta
    gasto = custo.custo_em_microdolares("claude-opus-5-5", total)
    assert gasto < LIMITES_DO_CHAT.reserva_por_pergunta_em_microdolares


# cautela na conversão de caracteres em tokens (JSON e português dão de 3 a 4 por token)
CARACTERES_POR_TOKEN = 3


def _pior_caso(modelo: str) -> int:
    """O custo máximo de uma pergunta pelos limites, sem acerto de cache (tudo gravado a preço de escrita).

    Voltas: as de ferramenta, a que recebe o aviso do limite e a última (`test_limite_de_voltas`). Cada
    uma pode levar as instruções, as ferramentas, o histórico inteiro, a pergunta, todos os dados da
    pergunta e a saída das voltas anteriores, e devolver `tokens_por_volta`. Fora da conta: os recomeços
    (até `RECOMECOS_MAXIMOS` por volta, raros: só com JSON ilegível no meio do streaming).
    """
    import json

    from src.chat.instrucoes import instrucoes_do_chat
    from tests.ajudantes_do_chat import caixa_de_mentira

    limites = LIMITES_DO_CHAT
    ferramentas = json.dumps(
        [d.para_o_modelo() for d in caixa_de_mentira().definicoes], ensure_ascii=False
    )
    historico = limites.perguntas_no_historico * (
        limites.caracteres_da_pergunta + limites.caracteres_do_historico
    )
    fixos = (
        len(instrucoes_do_chat())
        + len(ferramentas)
        + historico
        + limites.caracteres_da_pergunta
        + limites.caracteres_de_dados_por_pergunta
    ) // CARACTERES_POR_TOKEN
    chamadas = limites.voltas_de_ferramenta + 2
    entrada = sum(fixos + k * limites.tokens_por_volta for k in range(chamadas))
    uso = custo.UsoDoModelo(
        cache_gravado=entrada, saida=chamadas * limites.tokens_por_volta
    )
    return custo.custo_em_microdolares(modelo, uso)


@pytest.mark.parametrize("modelo", sorted(custo.PRECOS))
def test_reserva_cobre_o_pior_caso_de_cada_modelo(modelo):
    """A pergunta em curso segura do teto o pior caso: senão, as que estão no meio furam o teto."""
    assert _pior_caso(modelo) <= LIMITES_DO_CHAT.reserva_por_pergunta_em_microdolares


def test_modelo_sem_preco_nao_tem_custo():
    assert not custo.tem_preco("claude-modelo-inventado")
    with pytest.raises(KeyError):
        custo.custo_em_microdolares("claude-modelo-inventado", custo.UsoDoModelo())


def test_teto_do_mes_e_r_300_em_microdolares():
    # R$ 300 a R$ 6,00 por dólar = US$ 50
    assert custo.teto_em_microdolares(LIMITES_DO_CHAT) == 50_000_000


# ---------------------------------------------------------------- o pedido ao SDK

PEDIDO = PedidoAoModelo(
    sistema="sistema",
    ferramentas=[{"name": "setores", "input_schema": {"type": "object"}}],
    mensagens=[{"role": "user", "content": "oi"}],
    max_tokens=8_000,
)


def test_parametros_so_com_as_ferramentas_do_pedido():
    parametros = ma.parametros_do_pedido("claude-opus-5-5", PEDIDO)
    assert parametros == {
        "model": "claude-opus-5-5",
        "max_tokens": 8_000,
        "system": "sistema",
        "tools": PEDIDO.ferramentas,
        "messages": PEDIDO.mensagens,
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": "medium"},
        "cache_control": {"type": "ephemeral"},
    }


def test_instrucoes_levam_o_dia_de_brasilia():
    from datetime import UTC, datetime

    texto = ma.instrucoes_com_a_data("x", datetime(2026, 11, 14, 2, tzinfo=UTC))
    assert texto.endswith("Hoje é 13/11/2026 (horário de Brasília).")


def test_uso_da_resposta_aceita_cache_vazio():
    uso = SimpleNamespace(
        input_tokens=10,
        output_tokens=5,
        cache_read_input_tokens=None,
        cache_creation_input_tokens=3,
    )
    assert ma.uso_da_resposta(uso) == custo.UsoDoModelo(10, 5, 0, 3)


class _Fluxo:
    def __init__(self, eventos, final, erro=None):
        self._eventos, self._final, self._erro = eventos, final, erro

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    def __aiter__(self):
        return self._gerar()

    async def _gerar(self):
        for evento in self._eventos:
            yield evento
        if self._erro:
            raise self._erro

    async def get_final_message(self):
        return self._final


class _ClienteDeMentira:
    """Só o pedaço do `AsyncAnthropic` que o modelo usa; guarda os parâmetros."""

    def __init__(self, *fluxos):
        self._fluxos = list(fluxos)
        self.parametros: list[dict] = []
        self.messages = self

    def stream(self, **parametros):
        self.parametros.append(parametros)
        return self._fluxos.pop(0)


def _final():
    bloco = anthropic.types.ToolUseBlock(
        id="toolu_1", name="setores", input={}, type="tool_use"
    )
    return SimpleNamespace(
        content=[bloco],
        stop_reason="tool_use",
        usage=SimpleNamespace(input_tokens=7, output_tokens=2),
    )


def _partes(modelo):
    async def juntar():
        return [p async for p in modelo.turno(PEDIDO)]

    return asyncio.run(juntar())


def test_turno_entrega_o_texto_e_o_fim():
    texto = SimpleNamespace(type="text", text="olá")
    cliente = _ClienteDeMentira(_Fluxo([texto], _final()))
    modelo = ma.ModeloDaAnthropic("claude-opus-5-5", cliente)  # type: ignore[arg-type]
    partes = _partes(modelo)
    assert partes[0] == TextoParcial("olá")
    fim = partes[-1]
    assert isinstance(fim, FimDoTurno)
    assert fim.parada == "tool_use" and fim.chamadas[0].nome == "setores"
    assert fim.uso == custo.UsoDoModelo(7, 2, 0, 0)
    (parametros,) = cliente.parametros
    assert parametros["tools"] == PEDIDO.ferramentas


def test_json_ilegivel_recomeca_a_volta_e_desiste_depois_do_limite():
    ruim = ValueError("JSON ilegível")
    bons = _Fluxo([], _final())
    cliente = _ClienteDeMentira(_Fluxo([], None, ruim), bons)
    partes = _partes(ma.ModeloDaAnthropic("claude-opus-5-5", cliente))  # type: ignore[arg-type]
    assert isinstance(partes[0], Recomeco) and isinstance(partes[-1], FimDoTurno)
    sempre_ruim = [_Fluxo([], None, ruim) for _ in range(ma.RECOMECOS_MAXIMOS + 1)]
    cliente = _ClienteDeMentira(*sempre_ruim)
    with pytest.raises(ValueError):
        _partes(ma.ModeloDaAnthropic("claude-opus-5-5", cliente))  # type: ignore[arg-type]
