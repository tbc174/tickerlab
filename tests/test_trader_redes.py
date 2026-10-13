"""H4: redes pequenas (MLP, LSTM, TCN) no PyTorch, só CPU, determinísticas e sem olhar o futuro."""

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from trader import pipeline, redes

RAPIDO = {"epocas_max": 3, "paciencia": 2}


def _dados(n=6000, seed=0):
    rng = np.random.default_rng(seed)
    x = rng.normal(size=(n, 4))
    y = (x[:, 0] + 0.8 * rng.normal(size=n) > 0).astype(float)
    dias = np.arange(n) // 2  # dois "ativos" por dia
    return x, y, {"dias": dias}


def test_janela_so_olha_o_passado_do_mesmo_ativo():
    linhas = [np.array([0, 2, 4, 6]), np.array([1, 3, 5])]
    j = redes.janelas_por_linha(linhas, 7, janela=3)
    assert j[6].tolist() == [2, 4, 6]  # termina na própria linha
    assert j[2].tolist() == [-1, 0, 2]  # antes do começo: -1 (vira zeros)
    assert j[5].tolist() == [1, 3, 5]  # nunca mistura ativos


def test_convolucao_da_tcn_e_causal():
    torch.manual_seed(0)
    bloco = redes._BlocoCausal(2, 4, kernel=3, dilatacao=2, dropout=0.0).eval()
    x = torch.randn(1, 2, 20)
    mexido = x.clone()
    mexido[:, :, 15:] = 99.0  # mudar o "futuro" da sequência
    a, b = bloco(x), bloco(mexido)
    assert torch.allclose(a[:, :, :15], b[:, :, :15])


@pytest.mark.parametrize("tipo", ["mlp", "lstm", "tcn"])
def test_rede_aprende_um_sinal_simples(tipo):
    x, y, ctx = _dados()
    if tipo in redes.SEQUENCIAIS:
        linhas = [np.arange(0, len(x), 2), np.arange(1, len(x), 2)]
        ctx["janelas"] = redes.janelas_por_linha(linhas, len(x), janela=10)
    treino, teste = np.arange(4800), np.arange(4800, 6000)
    rede = redes.Rede(tipo, RAPIDO, 0).ajustar(x, y[treino], treino, ctx)
    p = rede.prever(x, teste, ctx)
    # teto ~78% (correlação 0,78 entre atributo e rótulo); com 3 épocas a LSTM fica perto de 65%.
    # Em 1200 dias, 60% já é muito mais que o acaso (erro-padrão ~1,4%)
    assert ((p > 0.5) == (y[teste] == 1)).mean() > 0.6
    assert rede.epocas_usadas >= 1


def test_treinar_duas_vezes_da_exatamente_o_mesmo():
    x, y, ctx = _dados(3000, 1)
    treino, teste = np.arange(2400), np.arange(2400, 3000)
    a = (
        redes.Rede("mlp", RAPIDO, 3)
        .ajustar(x, y[treino], treino, ctx)
        .prever(x, teste, ctx)
    )
    b = (
        redes.Rede("mlp", RAPIDO, 3)
        .ajustar(x, y[treino], treino, ctx)
        .prever(x, teste, ctx)
    )
    assert np.array_equal(a, b)


def test_validacao_tem_expurgo_antes_dela(monkeypatch):
    x, y, ctx = _dados(4000, 2)
    treino = np.arange(4000)
    vistos = {}
    original = redes.Rede._lote

    def espiar(self, z, linhas, contexto):
        vistos.setdefault("dias", set()).update(contexto["dias"][linhas].tolist())
        return original(self, z, linhas, contexto)

    monkeypatch.setattr(redes.Rede, "_lote", espiar)
    redes.Rede("mlp", {"epocas_max": 1}, 0).ajustar(x, y, treino, ctx)
    dias = np.array(sorted(vistos["dias"]))
    corte = np.unique(ctx["dias"])[int(2000 * 0.8)]
    buraco = set(range(corte - 21, corte))
    assert not buraco & set(
        dias.tolist()
    )  # os 21 dias antes da validação ficam de fora


def test_redes_sao_familia_h4_com_parametros_fixos():
    for tipo in redes.TIPOS:
        c = pipeline.Configuracao("r", tipo)
        assert c.familia == "H4"
        assert c.especificacao()["parametros"]["epocas_max"] == 30
    assert (
        pipeline.Configuracao("t", "tcn").especificacao()["parametros"]["kernel"] == 3
    )


@pytest.mark.parametrize("tipo", ["mlp", "lstm"])
def test_pipeline_com_rede_roda(tipo):
    from tests import test_trader_pipeline as tp

    series, painel = tp.mundo.__wrapped__()
    res = pipeline.rodar(
        pipeline.Configuracao("r", tipo, ajustes=RAPIDO),
        painel,
        series,
        None,
        cpcv=tp.CPCV_PEQUENO,
        trabalhadores=1,
    )
    assert len(res.caminhos) == 3 and all(c.notna().all() for c in res.caminhos)
