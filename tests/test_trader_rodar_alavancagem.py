"""Alavancagem do núcleo: a rodada completa com dados sintéticos e um registro temporário."""

import numpy as np
import pandas as pd
import pytest

from trader import criterio_quant
from trader.estrategias import dados_alavancagem
from trader.estrategias import rodar_alavancagem as rodar
from trader.estrategias.carteira_rp import ATIVOS_DE_RISCO

# A rodada do fixture de módulo demora; num processo só ela roda uma vez (CI com --dist loadgroup).
pytestmark = pytest.mark.xdist_group("alavancagem")
DATAS = pd.bdate_range("2014-01-02", "2020-12-30")
CDI = pd.Series(0.0003, index=DATAS)
VOLUMES = pd.Series(5e7, index=list(ATIVOS_DE_RISCO))


def _precos(semente=5):
    """Volatilidade que troca de ativo todo mês, com tendência (como no teste da P0-3): olhar o
    mês seguinte infla o Sharpe, e o item V tem o que conferir."""
    gerador = np.random.default_rng(semente)
    mes_par = pd.Series(DATAS.month).shift(1).bfill().to_numpy() % 2 == 0
    vol_a = np.where(mes_par, 0.03, 0.004)
    vol_b = np.where(mes_par, 0.004, 0.03)
    vols = np.column_stack(
        [vol_a, vol_b, np.full(len(DATAS), 0.01), np.full(len(DATAS), 0.01)]
    )
    retornos = gerador.normal(0.0006, vols)
    return pd.DataFrame(
        100 * np.cumprod(1 + retornos, axis=0),
        index=DATAS,
        columns=list(ATIVOS_DE_RISCO),
    )


def _curva(semente=8):
    gerador = np.random.default_rng(semente)
    taxa = 0.10 + np.cumsum(gerador.normal(0, 0.0005, len(DATAS)))
    return pd.DataFrame(
        {"data_base": list(DATAS), "curva": "nominal", "prazo_anos": 2.0, "taxa": taxa}
    )


def _excessos(precos):
    return {
        "WIN": dados_alavancagem.excesso_do_win(precos["BOVA11"], CDI),
        "DI1": dados_alavancagem.excesso_do_di1(_curva(), CDI, DATAS),
    }


@pytest.fixture(scope="module")
def rodada(tmp_path_factory):
    registro = rodar.abrir_registro(tmp_path_factory.mktemp("alav") / "registro.db")
    precos = _precos()
    saida = rodar.executar(precos, CDI, VOLUMES, _excessos(precos), registro)
    return precos, registro, saida


def test_registra_a_base_e_uma_tentativa_por_instrumento(rodada):
    _, registro, saida = rodada
    assert list(saida["ids"]) == ["1,0x", "1,3x WIN", "1,3x DI1"]
    assert registro.contar() == 3
    base = registro.obter(saida["ids"]["1,0x"])
    assert base["nome"] == "p0_3_risk_parity" and "alavancagem" not in base["spec"]
    win = registro.obter(saida["ids"]["1,3x WIN"])
    assert win["familia"] == "P0-3"
    assert win["spec"]["alavancagem"] == 1.3 and win["spec"]["instrumento"] == "WIN"
    assert win["spec"]["pre_registro"] == criterio_quant.HASH_DO_CRITERIO
    assert win["resultado"]["veredito"]["itens"]
    assert win["resultado"]["resumo"]["rolagens"] > 0


def test_rodar_de_novo_nao_conta_configuracao_nova(rodada):
    precos, registro, _ = rodada
    rodar.executar(precos, CDI, VOLUMES, _excessos(precos), registro)
    assert registro.contar() == 3
    assert registro.execucoes() == 6  # mas toda execução conta no DSR


def test_cada_versao_tem_o_veredito_completo(rodada):
    vereditos = rodada[2]["vereditos"]
    for veredito in vereditos.values():
        itens = {i.codigo: i for i in veredito.itens}
        assert list(itens) == [
            "A1",
            "A2",
            "A3",
            "A4",
            "A5",
            "A6",
            "A7",
            "A8",
            "F1",
            "V",
        ]
        # Só 1,0x e 1,3x, pré-registradas: não há alternativas a escolher, o PBO não se aplica.
        assert itens["A2"].valor is None and itens["A2"].passou
        assert itens["V"].passou


def test_resumos_mostram_o_que_a_secao_7_pede(rodada):
    resumos = rodada[2]["resumos"]
    for r in resumos.values():
        assert {
            "maior_queda",
            "queda_com_freio",
            "sharpe",
            "custo_de_rolagem_por_ano",
            "dias_com_margem_acima",
            "exposicao_media",
        } <= set(r)
    assert resumos["1,0x"]["exposicao_media"] == 1.0
    assert resumos["1,0x"]["custo_de_rolagem_por_ano"] == 0.0
    assert resumos["1,3x WIN"]["exposicao_media"] == pytest.approx(1.3, abs=0.05)
    assert resumos["1,3x DI1"]["custo_de_rolagem_por_ano"] > 0
    assert (
        resumos["1,3x WIN"]["volatilidade_anual"]
        > resumos["1,0x"]["volatilidade_anual"]
    )


def test_versao_que_entra_segue_os_vereditos(rodada):
    saida = rodada[2]
    aprovadas = saida["aprovadas_1_3"]
    if aprovadas:
        assert saida["versao_que_entra"] == 1.3
    elif saida["vereditos"]["1,0x"].aprovado:
        assert saida["versao_que_entra"] == 1.0
    else:
        assert saida["versao_que_entra"] is None


def test_relatorio_tem_as_tabelas_e_os_limites(rodada, tmp_path):
    texto = rodar.escrever_relatorio(rodada[2], tmp_path).read_text(encoding="utf-8")
    assert "Versão que entra" in texto
    assert "### 1,3x WIN" in texto and "### 1,3x DI1" in texto
    assert "Custo de rolagem/ano" in texto and "Dias com margem > 30%" in texto
    assert "## Freio por camada (40%)" in texto
    assert "## Limites e cuidados" in texto
    assert "recomendação de investimento" in texto


def test_pre_registro_alterado_nao_roda_nem_registra(tmp_path, monkeypatch):
    def recusar(*_, **__):
        raise criterio_quant.PreRegistroAlteradoError("mudou")

    monkeypatch.setattr(rodar.criterio_quant, "conferir", recusar)
    registro = rodar.abrir_registro(tmp_path / "registro.db")
    precos = _precos()
    with pytest.raises(criterio_quant.PreRegistroAlteradoError):
        rodar.executar(precos, CDI, VOLUMES, _excessos(precos), registro)
    assert registro.contar() == 0


def test_versoes_pre_registradas_sao_so_tres():
    versoes = rodar.versoes_pre_registradas()
    assert list(versoes) == ["1,0x", "1,3x WIN", "1,3x DI1"]
    assert {p.fator for p in versoes.values()} == {1.0, 1.3}


def test_carregar_curva_junta_os_parquets(tmp_path):
    _curva().iloc[:10].to_parquet(tmp_path / "2014.parquet")
    _curva().iloc[10:20].to_parquet(tmp_path / "2015.parquet")
    assert len(rodar.carregar_curva(tmp_path)) == 20
    with pytest.raises(FileNotFoundError):
        rodar.carregar_curva(tmp_path / "vazia")
