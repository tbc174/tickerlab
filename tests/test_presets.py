"""Catálogo de parâmetros e resolvedor de presets do Research (PRD v2, seção 9)."""

import math
import random

import pydantic
import pytest

from src import parametros as pm
from src import presets as ps

PALAVRAS_PROIBIDAS = (
    "seguro",
    "garantid",
    "ideal para você",
    "recomend",
    "compre",
    "venda já",
)


# --- catálogo ---------------------------------------------------------------------------------
def test_padroes_do_sistema_passam_em_todas_as_regras():
    pm.conferir_padroes()
    assert ps.resolver([]).personalizados() == {}


def test_todo_parametro_tem_dominio_conhecido_ajuda_e_padrao_valido():
    for p in pm.PARAMETROS:
        assert p.dominio in pm.DOMINIOS, p.chave
        assert p.rotulo and len(p.ajuda) > 15, p.chave
        assert p.validar(p.padrao) == p.padrao, p.chave
        if p.tipo in ("inteiro", "decimal") and not p.opcoes:
            assert p.minimo is not None and p.maximo is not None, p.chave


@pytest.mark.parametrize(
    ("chave", "valor"),
    [
        ("tecnica.rsi_periodo", 1),  # abaixo do mínimo
        ("tecnica.rsi_periodo", 101),  # acima do máximo
        ("tecnica.rsi_periodo", 14.5),  # inteiro com fração
        ("tecnica.rsi_periodo", "14"),  # texto no lugar de número
        ("tecnica.rsi_periodo", True),  # verdadeiro/falso não é número
        ("tecnica.bollinger_desvios", math.nan),
        ("tecnica.bollinger_desvios", math.inf),
        ("quant.var_confianca", 90),  # fora das opções
        ("quant.benchmark", "PETR4.SA"),  # não é um índice do catálogo
        ("newsletter.temas", ("resultados", "fofoca")),
        ("newsletter.temas", ()),
        ("newsletter.temas", "risco"),  # texto solto não é lista
        ("relevancia.recencia", -5),  # percentual negativo
    ],
)
def test_valores_invalidos_sao_recusados_com_explicacao(chave, valor):
    with pytest.raises(pm.ParametroInvalidoError) as erro:
        pm.validar_valores({chave: valor})
    assert pm.CATALOGO[chave].rotulo in str(erro.value)


def test_chave_desconhecida_e_recusada():
    with pytest.raises(pm.ParametroInvalidoError, match="desconhecidos"):
        pm.validar_valores({"tecnica.rsi_magico": 3})


def test_valores_sao_normalizados():
    valores = pm.validar_valores(
        {
            "tecnica.rsi_periodo": 21.0,
            "tecnica.bollinger_desvios": 2,
            "newsletter.temas": ["risco", "resultados", "risco"],
        }
    )
    assert valores["tecnica.rsi_periodo"] == 21 and isinstance(
        valores["tecnica.rsi_periodo"], int
    )
    assert isinstance(valores["tecnica.bollinger_desvios"], float)
    assert valores["newsletter.temas"] == (
        "resultados",
        "risco",
    )  # sem repetir, na ordem do catálogo


# --- regras entre parâmetros ------------------------------------------------------------------
@pytest.mark.parametrize(
    ("mudancas", "trecho"),
    [
        ({"tecnica.media_rapida": 200, "tecnica.media_lenta": 50}, "média rápida"),
        ({"tecnica.macd_rapida": 30, "tecnica.macd_lenta": 26}, "MACD"),
        ({"tecnica.rsi_inferior": 70, "tecnica.rsi_superior": 30}, "RSI"),
        ({"relevancia.exposicao": 50}, "somar 100%"),
        ({"editorial.tecnica": 0}, "somar 100%"),
    ],
)
def test_combinacao_invalida_e_recusada_no_conjunto_final(mudancas, trecho):
    with pytest.raises(ps.CombinacaoInvalidaError, match=trecho):
        ps.resolver([], simulacao=mudancas)


def test_valor_valido_sozinho_pode_quebrar_ao_combinar_escopos():
    """Global com lenta 60 e ativo com rápida 100: cada um é válido, juntos não."""
    presets = [
        ps.Preset(escopo=ps.GLOBAL, parametros={"tecnica.media_lenta": 60}),
        ps.Preset(
            escopo=ps.ATIVO, alvo="PETR4.SA", parametros={"tecnica.media_rapida": 100}
        ),
    ]
    assert ps.resolver(presets)["tecnica.media_lenta"] == 60  # sem o ativo, tudo bem
    with pytest.raises(ps.CombinacaoInvalidaError):
        ps.resolver(presets, ticker="PETR4.SA")


# --- precedência e origem (US-02, US-05) ------------------------------------------------------
def _presets():
    return [
        ps.Preset(
            escopo=ps.GLOBAL,
            parametros={"tecnica.rsi_periodo": 21, "quant.benchmark": "^GSPC"},
        ),
        ps.Preset(
            escopo=ps.WATCHLIST,
            alvo="EUA",
            parametros={"quant.janela_volatilidade": 126},
        ),
        ps.Preset(
            escopo=ps.WATCHLIST, alvo="B3", parametros={"quant.benchmark": "^BVSP"}
        ),
        ps.Preset(escopo=ps.ATIVO, alvo="PETR4", parametros={"tecnica.rsi_periodo": 9}),
    ]


def test_precedencia_sistema_global_watchlist_ativo_simulacao():
    r = ps.resolver(
        _presets(),
        watchlist="B3",
        ticker="PETR4.SA",
        simulacao={"tecnica.atr_periodo": 20},
    )
    assert (r["tecnica.macd_sinal"], r.origem("tecnica.macd_sinal")) == (9, ps.SISTEMA)
    assert (r["quant.benchmark"], r.origem("quant.benchmark")) == (
        "^BVSP",
        ps.WATCHLIST,
    )
    assert (r["tecnica.rsi_periodo"], r.origem("tecnica.rsi_periodo")) == (9, ps.ATIVO)
    assert (r["tecnica.atr_periodo"], r.origem("tecnica.atr_periodo")) == (
        20,
        ps.SIMULACAO,
    )
    assert r.efetivos["tecnica.rsi_periodo"].nome_da_origem == "Do ativo"


def test_uma_watchlist_nao_vaza_para_outra():
    eua = ps.resolver(_presets(), watchlist="EUA")
    b3 = ps.resolver(_presets(), watchlist="B3")
    assert eua["quant.janela_volatilidade"] == 126 and eua["quant.benchmark"] == "^GSPC"
    assert b3["quant.janela_volatilidade"] == 252 and b3["quant.benchmark"] == "^BVSP"
    assert ps.resolver(_presets(), ticker="VALE3.SA")["tecnica.rsi_periodo"] == 21


def test_dois_presets_no_mesmo_escopo_e_alvo_sao_recusados():
    duplicados = [ps.Preset(escopo=ps.GLOBAL), ps.Preset(escopo=ps.GLOBAL)]
    with pytest.raises(pm.ParametroInvalidoError, match="só um pode valer"):
        ps.resolver(duplicados)


def test_alvo_obrigatorio_onde_faz_sentido_e_ticker_normalizado():
    with pytest.raises(pydantic.ValidationError):
        ps.Preset(escopo=ps.ATIVO)
    with pytest.raises(pydantic.ValidationError):
        ps.Preset(escopo=ps.GLOBAL, alvo="PETR4.SA")
    assert ps.Preset(escopo=ps.ATIVO, alvo=" petr4 ").alvo == "PETR4.SA"


def test_preset_recusa_parametro_invalido_e_campo_extra():
    with pytest.raises(pydantic.ValidationError, match="Período do RSI"):
        ps.Preset(escopo=ps.GLOBAL, parametros={"tecnica.rsi_periodo": 500})
    with pytest.raises(pydantic.ValidationError):
        ps.Preset(escopo=ps.GLOBAL, dono="outra pessoa")  # extra="forbid"


# --- versões, restaurar e comparar (US-03, US-08) ---------------------------------------------
def test_mudar_cria_versao_nova_sem_alterar_a_antiga():
    v1 = ps.Preset(
        escopo=ps.ATIVO, alvo="PETR4.SA", parametros={"tecnica.rsi_periodo": 14}
    )
    v2 = v1.com_valores({"tecnica.rsi_periodo": 21})
    assert (v1.versao, v1.parametros["tecnica.rsi_periodo"]) == (1, 14)
    assert (v2.versao, v2.parametros["tecnica.rsi_periodo"]) == (2, 21)
    assert v1.assinatura != v2.assinatura
    with pytest.raises(pydantic.ValidationError):
        v1.versao = 9  # congelado


def test_restaurar_padrao_volta_ao_escopo_mais_geral():
    global_ = ps.Preset(escopo=ps.GLOBAL, parametros={"tecnica.rsi_periodo": 21})
    ativo = ps.Preset(
        escopo=ps.ATIVO, alvo="PETR4.SA", parametros={"tecnica.rsi_periodo": 9}
    )
    restaurado = ativo.sem("tecnica.rsi_periodo")
    r = ps.resolver([global_, restaurado], ticker="PETR4.SA")
    assert (r["tecnica.rsi_periodo"], r.origem("tecnica.rsi_periodo")) == (
        21,
        ps.GLOBAL,
    )
    assert restaurado.versao == 2


def test_comparar_a_e_b_mostra_so_o_que_mudou_e_de_onde_veio():
    a = ps.resolver([])
    b = ps.resolver(
        [], simulacao={"tecnica.rsi_periodo": 21, "tecnica.media_rapida": 20}
    )
    diferencas = {d.chave: d for d in a.comparar(b)}
    assert set(diferencas) == {"tecnica.rsi_periodo", "tecnica.media_rapida"}
    d = diferencas["tecnica.rsi_periodo"]
    assert (d.valor_a, d.valor_b, d.origem_a, d.origem_b) == (
        14,
        21,
        ps.SISTEMA,
        ps.SIMULACAO,
    )


def test_assinatura_e_estavel_e_muda_com_qualquer_valor():
    assert ps.resolver([]).assinatura == ps.resolver([]).assinatura
    assert (
        ps.resolver([], simulacao={"tecnica.rsi_periodo": 15}).assinatura
        != ps.resolver([]).assinatura
    )


def test_propriedade_combinacoes_sorteadas_ou_passam_ou_explicam():
    """Valores sorteados dentro dos limites: o resolvedor ou aceita (e as regras valem) ou
    recusa com a lista de regras quebradas. Nunca devolve um conjunto inconsistente."""
    sorteio = random.Random(42)
    numericos = [p for p in pm.PARAMETROS if p.tipo == "inteiro" and not p.opcoes]
    for _ in range(300):
        escolhidos = sorteio.sample(numericos, 4)
        valores = {
            p.chave: sorteio.randint(int(p.minimo), int(p.maximo)) for p in escolhidos
        }
        try:
            r = ps.resolver([], simulacao=valores)
        except ps.CombinacaoInvalidaError as erro:
            assert erro.problemas
        else:
            assert pm.problemas_de_combinacao(r.valores()) == []
            assert sum(r.valores("relevancia").values()) == 100
            assert r["tecnica.media_rapida"] < r["tecnica.media_lenta"]


# --- presets prontos ---------------------------------------------------------------------------
def test_presets_prontos_sao_validos_e_nao_prometem_nada():
    assert set(ps.PRESETS_PRONTOS) == {
        "visao_equilibrada",
        "longo_prazo",
        "trader_quantitativo",
        "renda_e_proventos",
        "monitoramento_de_risco",
    }
    for pronto in ps.PRESETS_PRONTOS.values():
        r = ps.resolver([pronto.como_preset()])  # passa pelas regras (pesos = 100%)
        assert r.personalizados()
        texto = f"{pronto.nome} {pronto.enfatiza}".lower()
        assert not any(p in texto for p in PALAVRAS_PROIBIDAS), pronto.chave


def test_textos_do_catalogo_nao_prometem_nada():
    for p in pm.PARAMETROS:
        texto = f"{p.rotulo} {p.ajuda}".lower()
        assert not any(
            palavra in texto for palavra in ("garantid", "seguro", "ideal para você")
        )
