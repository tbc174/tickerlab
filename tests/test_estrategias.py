"""Testes de src/estrategias.py, incluindo a prova de que NENHUMA estratégia olha o futuro."""

import numpy as np
import pandas as pd
import pytest

from src.estrategias import (
    ESTRATEGIAS,
    gerar_posicao,
    posicao_canal_de_keltner,
    posicao_comprar_e_segurar,
    posicao_cruzamento_de_medias,
    posicao_filtro_de_tendencia,
    posicao_filtro_mensal,
    posicao_macd,
    posicao_momentum,
    posicao_rompimento_de_canal,
)


def _dados(fechamentos):
    return pd.DataFrame(
        {"Close": np.array(fechamentos, dtype=float)},
        index=pd.date_range("2026-01-05", periods=len(fechamentos), freq="B"),
    )


def _dados_sinteticos(dias=400, semente=7):
    rng = np.random.default_rng(semente)
    fechamento = 20 * np.cumprod(1 + rng.normal(0.0004, 0.015, dias))
    return pd.DataFrame(
        {
            "Open": fechamento * 0.999,
            "High": fechamento * 1.01,
            "Low": fechamento * 0.99,
            "Close": fechamento,
            "Volume": rng.integers(1_000, 5_000, dias),
        },
        index=pd.date_range("2024-01-01", periods=dias, freq="B"),
    )


# --- cada função de posição -----------------------------------------------------------


def test_comprar_e_segurar_fica_sempre_comprado():
    assert list(posicao_comprar_e_segurar(_dados([1, 2, 3]))) == [1, 1, 1]


def test_cruzamento_de_medias_compra_quando_a_curta_passa_da_longa():
    # sobe até 5 e desce: a média curta fica acima da longa do 3º ao 6º dia
    dados = _dados([1, 2, 3, 4, 5, 4, 3, 2, 1])
    posicao = posicao_cruzamento_de_medias(dados, curta=2, longa=3)
    assert list(posicao) == [0, 0, 1, 1, 1, 1, 0, 0, 0]


def test_cruzamento_exige_curta_menor_que_longa():
    with pytest.raises(ValueError, match="curta"):
        posicao_cruzamento_de_medias(_dados([1, 2, 3, 4]), curta=5, longa=5)


def test_filtro_de_tendencia_compra_acima_da_media():
    posicao = posicao_filtro_de_tendencia(_dados([1, 2, 3, 2, 1]), janela=3)
    assert list(posicao) == [0, 0, 1, 0, 0]


def test_sem_historico_suficiente_fica_em_caixa():
    posicao = posicao_filtro_de_tendencia(_dados([1, 2, 3]), janela=200)
    assert list(posicao) == [0, 0, 0]


# --- registro e validação de parâmetros -----------------------------------------------------


def test_o_registro_tem_a_referencia_e_estrategias_de_tendencia():
    assert "Comprar e segurar" in ESTRATEGIAS
    assert ESTRATEGIAS["Comprar e segurar"].grupo == "Referência"
    assert ESTRATEGIAS["Cruzamento de médias"].grupo == "Tendência"


def test_o_nome_no_registro_e_o_nome_da_estrategia():
    assert all(chave == e.nome for chave, e in ESTRATEGIAS.items())


def test_gerar_posicao_usa_os_parametros_padrao():
    dados = _dados_sinteticos()
    padrao = gerar_posicao("Cruzamento de médias", dados)
    explicito = gerar_posicao("Cruzamento de médias", dados, curta=20, longa=50)
    assert padrao.equals(explicito)


def test_estrategia_desconhecida():
    with pytest.raises(ValueError, match="desconhecida"):
        gerar_posicao("Bola de cristal", _dados_sinteticos())


def test_parametro_desconhecido():
    with pytest.raises(ValueError, match="desconhecidos"):
        gerar_posicao("Cruzamento de médias", _dados_sinteticos(), banana=3)


@pytest.mark.parametrize("curta", [1, 0, 500])
def test_parametro_fora_dos_limites(curta):
    with pytest.raises(ValueError, match="deve ficar entre"):
        gerar_posicao("Cruzamento de médias", _dados_sinteticos(), curta=curta)


# --- propriedades que TODA estratégia do registro precisa cumprir --------------------------


@pytest.mark.parametrize("nome", list(ESTRATEGIAS))
def test_posicao_valida(nome):
    dados = _dados_sinteticos()
    posicao = gerar_posicao(nome, dados)
    assert posicao.index.equals(dados.index)
    assert not posicao.isna().any()
    assert posicao.between(0, 1).all()


@pytest.mark.parametrize("nome", list(ESTRATEGIAS))
def test_estrategia_nao_olha_o_futuro(nome):
    # Se a posição dos primeiros 300 dias muda quando se apagam os dias seguintes, a estratégia
    # usou informação do futuro. Esse teste vale para qualquer estratégia nova do registro.
    dados = _dados_sinteticos(400)
    completa = gerar_posicao(nome, dados)
    cortada = gerar_posicao(nome, dados.iloc[:300])
    assert completa.iloc[:300].equals(cortada)


# --- Estratégias de tendência: casos conferíveis de cabeça --------------------------------


def _dados_ohlc(fechamentos, folga=0.0):
    f = np.array(fechamentos, dtype=float)
    return pd.DataFrame(
        {"Open": f, "High": f + folga, "Low": f - folga, "Close": f, "Volume": 1_000},
        index=pd.date_range("2026-01-05", periods=len(f), freq="B"),
    )


def test_cruzamento_com_media_exponencial_reage_diferente_da_simples():
    dados = _dados_sinteticos(300)
    simples = posicao_cruzamento_de_medias(dados, 10, 40, "Simples")
    exponencial = posicao_cruzamento_de_medias(dados, 10, 40, "Exponencial")
    assert not simples.equals(exponencial)
    assert exponencial.between(0, 1).all()


def test_tipo_de_media_invalido_e_barrado_pelo_registro():
    with pytest.raises(ValueError, match="opções"):
        gerar_posicao("Cruzamento de médias", _dados_sinteticos(), tipo="Triangular")


def test_filtro_mensal_so_usa_a_decisao_do_mes_anterior():
    # cada mês tem um preço único: jan 10, fev 11, mar 12, abr 13, mai 12, jun 9, jul 8.
    # Com média de 3 meses o sinal do fim de cada mês é: mar sim (12 > 11), abr sim (13 > 12),
    # mai não (12 < 12,33), jun não, jul não. Cada sinal só vale a partir do mês seguinte.
    datas = pd.bdate_range("2026-01-01", "2026-07-15")
    precos_do_mes = [10, 11, 12, 13, 12, 9, 8]
    fechamento = pd.Series(
        [precos_do_mes[d.month - 1] for d in datas], index=datas, dtype=float
    )
    dados = pd.DataFrame({"Close": fechamento})
    posicao = posicao_filtro_mensal(dados, meses=3)
    assert (
        posicao[posicao.index.month == 3] == 0
    ).all()  # o sinal de março ainda não vale
    assert (posicao[posicao.index.month == 4] == 1).all()  # vale em abril
    assert (
        posicao[posicao.index.month == 5] == 1
    ).all()  # o sinal de abril vale em maio
    assert (posicao[posicao.index.month == 6] == 0).all()  # o sinal de maio era "não"
    assert (posicao[posicao.index.month <= 2] == 0).all()  # sem histórico de 3 meses


def test_donchian_entra_no_rompimento_e_sai_na_perda_do_canal():
    dados = _dados_ohlc([10, 10, 10, 10, 12, 13, 13, 9, 9, 9])
    posicao = posicao_rompimento_de_canal(dados, entrada=3, saida=2)
    assert list(posicao) == [0, 0, 0, 0, 1, 1, 1, 0, 0, 0]


def test_donchian_exige_saida_menor_que_entrada():
    with pytest.raises(ValueError, match="saída"):
        posicao_rompimento_de_canal(_dados_ohlc([1, 2, 3, 4]), entrada=5, saida=5)


def test_macd_compra_na_alta_e_sai_na_queda():
    subindo = _dados_ohlc(np.linspace(10, 30, 120))
    caindo = _dados_ohlc(np.linspace(30, 10, 120))
    assert posicao_macd(subindo).iloc[-1] == 1
    assert posicao_macd(caindo).iloc[-1] == 0


def test_macd_exige_rapida_menor_que_lenta():
    with pytest.raises(ValueError, match="rápida"):
        posicao_macd(_dados_ohlc(np.linspace(10, 20, 60)), rapida=30, lenta=26)


def test_momentum_olha_o_retorno_passado_pulando_os_dias_recentes():
    dados = _dados_ohlc([10, 11, 12, 13, 12, 11, 10])
    posicao = posicao_momentum(dados, janela=3, pulo=1)
    assert list(posicao) == [0, 0, 0, 0, 1, 1, 0]


def test_momentum_sem_historico_fica_em_caixa():
    assert (posicao_momentum(_dados_ohlc(np.linspace(10, 20, 100))) == 0).all()


def test_keltner_compra_no_rompimento_de_forca_e_sai_abaixo_da_media():
    precos = [10.0] * 30 + [15.0] * 10 + [8.0] * 10
    dados = _dados_ohlc(precos, folga=0.1)
    posicao = posicao_canal_de_keltner(
        dados, janela_media=5, janela_atr=5, multiplicador=1.0
    )
    assert posicao.iloc[29] == 0  # preço parado: nada a fazer
    assert posicao.iloc[30] == 1  # salto para 15: rompeu a faixa superior
    assert posicao.iloc[39] == 1  # segue comprado enquanto está acima da média
    assert posicao.iloc[40] == 0  # caiu para 8, abaixo da média: sai
    assert posicao.iloc[49] == 0


def test_parametro_decimal_do_registro():
    dados = _dados_sinteticos()
    posicao = gerar_posicao("Canal de Keltner", dados, multiplicador=1.5)
    assert posicao.between(0, 1).all()
    with pytest.raises(ValueError, match="deve ficar entre"):
        gerar_posicao("Canal de Keltner", dados, multiplicador=9.0)
