"""Preços ajustados pelos eventos de capital (trader/estrategias/ajuste_b3.py), com preços sintéticos."""

import numpy as np
import pandas as pd
import pytest

from trader.estrategias import ajuste_b3

DATAS = pd.bdate_range("2015-01-02", periods=200)


def _precos(salto_em: int | None = None, razao: float = 1.0) -> pd.Series:
    """Preço com passos pequenos e, se pedido, um salto de `razao` no pregão `salto_em`."""
    rng = np.random.default_rng(7)
    passos = np.exp(rng.normal(0, 0.005, len(DATAS)))
    if salto_em is not None:
        passos[salto_em] = razao
    return pd.Series(20.0 * np.cumprod(passos), index=DATAS)


def _evento(cnpj: str, data: str, fator: float, tipo: str = "desdobramento") -> dict:
    return {"cnpj": cnpj, "tipo": tipo, "data": pd.Timestamp(data), "fator": fator}


def test_eventos_repetidos_contam_uma_vez_e_os_do_mesmo_dia_se_multiplicam():
    eventos = pd.DataFrame(
        [
            _evento("A", "2015-03-02", 2.0),
            _evento("A", "2015-03-02", 2.00001),  # outra versão do formulário
            _evento("B", "2015-04-01", 0.01, "grupamento"),
            _evento(
                "B", "2015-04-01", 100.0
            ),  # grupamento e desdobramento no mesmo dia
            _evento("C", "2015-05-04", 1.1, "bonificação"),
            _evento("C", "2015-06-01", 1.5, "aumento"),  # subscrição não ajusta
            _evento("D", "2015-06-01", 1.001, "bonificação"),  # pequeno demais
        ]
    )
    tabela = ajuste_b3.eventos_que_ajustam(eventos)
    assert list(tabela["cnpj"]) == ["A", "C"]
    assert tabela["fator"].tolist() == pytest.approx([2.0, 1.1])


def test_desdobramento_acha_a_data_ex_depois_da_deliberacao_e_ajusta_para_tras():
    precos = _precos(salto_em=50, razao=0.5)
    deliberacao = DATAS[40]  # a data ex vem 10 pregões depois
    ajustado, achados = ajuste_b3.ajustar_um(
        precos, pd.DataFrame([_evento("A", deliberacao, 2.0)])
    )
    assert achados == [(deliberacao, DATAS[50], 2.0)]
    assert ajustado.iloc[50:].equals(
        precos.iloc[50:]
    )  # depois da data ex, o preço do arquivo
    assert ajustado.iloc[:50].to_numpy() == pytest.approx(
        precos.iloc[:50].to_numpy() / 2
    )
    assert abs(np.log(ajustado.iloc[50] / ajustado.iloc[49])) < 0.05


def test_grupamento_e_bonificacao_pequena():
    precos = _precos(salto_em=30, razao=10.0)
    ajustado, _ = ajuste_b3.ajustar_um(
        precos, pd.DataFrame([_evento("A", DATAS[28], 0.1, "grupamento")])
    )
    assert ajustado.iloc[:30].to_numpy() == pytest.approx(
        precos.iloc[:30].to_numpy() * 10
    )
    precos = _precos(salto_em=30, razao=1 / 1.1)
    ajustado, achados = ajuste_b3.ajustar_um(
        precos, pd.DataFrame([_evento("A", DATAS[29], 1.1, "bonificação")])
    )
    assert achados[0][1] == DATAS[30]
    assert ajustado.iloc[:30].to_numpy() == pytest.approx(
        precos.iloc[:30].to_numpy() / 1.1
    )


def test_evento_sem_salto_no_preco_nao_ajusta():
    precos = _precos()
    ajustado, achados = ajuste_b3.ajustar_um(
        precos, pd.DataFrame([_evento("A", DATAS[40], 2.0)])
    )
    assert achados == [(DATAS[40], None, 2.0)]
    assert ajustado.equals(precos)


def test_salto_fora_da_janela_do_evento_nao_conta():
    precos = _precos(
        salto_em=150, razao=0.5
    )  # ~ 200 dias corridos depois da deliberação
    _, achados = ajuste_b3.ajustar_um(
        precos, pd.DataFrame([_evento("A", DATAS[5], 2.0)])
    )
    assert achados[0][1] is None


def test_eventos_posteriores_nao_mudam_os_retornos_do_passado():
    """Sem olhar o futuro: um evento depois de t só multiplica o passado por uma constante."""
    precos = _precos(salto_em=150, razao=0.5)
    evento = pd.DataFrame([_evento("A", DATAS[148], 2.0)])
    ajustado, _ = ajuste_b3.ajustar_um(precos, evento)
    antes = precos.iloc[:140].pct_change().dropna()
    assert ajustado.iloc[:140].pct_change().dropna().to_numpy() == pytest.approx(
        antes.to_numpy()
    )


def test_ajustar_a_tabela_por_cnpj_e_conta_saltos_sem_evento():
    fechamento = pd.DataFrame(
        {
            "AAA3": _precos(salto_em=50, razao=0.5),
            "AAA4": _precos(salto_em=51, razao=0.5),  # outra classe, mesma empresa
            "BBB3": _precos(salto_em=80, razao=0.3),  # queda sem evento
            "CCC3": _precos(),
        }
    )
    fechamento.loc[DATAS[:20], "CCC3"] = np.nan  # começou a negociar depois
    cnpj = pd.Series({"AAA3": "A", "AAA4": "A", "BBB3": "B", "CCC3": None})
    eventos = pd.DataFrame(
        [_evento("A", DATAS[45], 2.0), _evento("B", "2010-01-04", 2.0)]
    )
    ajuste = ajuste_b3.ajustar(fechamento, cnpj, eventos)
    assert list(ajuste.aplicados["ticker"]) == ["AAA3", "AAA4"]
    assert list(ajuste.aplicados["data_ex"]) == [DATAS[50], DATAS[51]]
    assert ajuste.sem_data_ex.empty  # o evento de B é de antes dos preços
    assert list(ajuste.saltos["ticker"]) == ["BBB3"]
    assert ajuste.ajustado["CCC3"].equals(fechamento["CCC3"])
    resumo = ajuste_b3.conferencia(ajuste, fechamento)
    assert resumo["eventos_aplicados"] == 2
    assert resumo["saltos_sem_evento"] == 1


def test_main_sem_os_cotahist_diz_o_que_falta(tmp_path, capsys):
    assert ajuste_b3.main(tmp_path, tmp_path) == 2
    assert "COTAHIST_A2009.ZIP" in capsys.readouterr().out


def _so_no_dia(dia: int) -> pd.Series:
    """Troca do número de distribuição só no pregão `dia` (o dia ex de um evento na B3)."""
    return pd.Series(DATAS.isin([DATAS[dia]]), index=DATAS)


@pytest.mark.parametrize(("razao", "fator"), [(0.25, 4.0), (10.0, 0.1), (1 / 3.1, 3.0)])
def test_desdobramento_sem_formulario_ajusta_pelo_preco_no_dia_da_troca(razao, fator):
    precos = _precos(salto_em=60, razao=razao)
    fechamento = pd.DataFrame({"AAA3": precos})
    ajuste = ajuste_b3.ajustar(
        fechamento,
        pd.Series({"AAA3": None}),
        pd.DataFrame(columns=["cnpj", "tipo", "data", "fator"]),
        trocas=pd.DataFrame({"AAA3": _so_no_dia(60)}),
    )
    assert list(ajuste.pelo_preco["data"]) == [DATAS[60]]
    assert ajuste.pelo_preco["fator"].tolist() == pytest.approx([fator])
    assert ajuste.ajustado["AAA3"].iloc[:60].to_numpy() == pytest.approx(
        precos.iloc[:60].to_numpy() / fator
    )
    assert ajuste.ajustado["AAA3"].iloc[60:].equals(precos.iloc[60:])
    assert ajuste.saltos.empty


def test_queda_sem_troca_de_distribuicao_fica_como_salto():
    """Uma quebra (como a da Americanas em 2023) não muda a distribuição e não é desdobramento."""
    precos = _precos(salto_em=60, razao=0.25)
    ajuste = ajuste_b3.ajustar(
        pd.DataFrame({"AAA3": precos}),
        pd.Series({"AAA3": None}),
        pd.DataFrame(columns=["cnpj", "tipo", "data", "fator"]),
        trocas=pd.DataFrame({"AAA3": _so_no_dia(61)}),
    )
    assert ajuste.pelo_preco.empty
    assert ajuste.ajustado["AAA3"].equals(precos)
    assert list(ajuste.saltos["data"]) == [DATAS[60]]


def test_salto_longe_de_um_fator_usual_nao_ajusta_pelo_preco():
    """Dividendo grande ou cisão no dia ex: razão de 2,41 não está a 5% de 2 nem de 3."""
    precos = _precos(salto_em=60, razao=1 / 2.41)
    ajuste = ajuste_b3.ajustar(
        pd.DataFrame({"AAA3": precos}),
        pd.Series({"AAA3": None}),
        pd.DataFrame(columns=["cnpj", "tipo", "data", "fator"]),
        trocas=pd.DataFrame({"AAA3": _so_no_dia(60)}),
    )
    assert ajuste.pelo_preco.empty
    assert len(ajuste.saltos) == 1


def test_evento_do_formulario_vem_antes_e_o_preco_nao_ajusta_de_novo():
    precos = _precos(salto_em=50, razao=0.5)
    ajuste = ajuste_b3.ajustar(
        pd.DataFrame({"AAA3": precos}),
        pd.Series({"AAA3": "A"}),
        pd.DataFrame([_evento("A", DATAS[45], 2.0)]),
        trocas=pd.DataFrame({"AAA3": _so_no_dia(50)}),
    )
    assert len(ajuste.aplicados) == 1
    assert ajuste.pelo_preco.empty
    assert ajuste.ajustado["AAA3"].iloc[:50].to_numpy() == pytest.approx(
        precos.iloc[:50].to_numpy() / 2
    )


def test_fator_usual():
    assert ajuste_b3.fator_usual(4.1) == 4
    assert ajuste_b3.fator_usual(0.0103) == pytest.approx(0.01)
    assert ajuste_b3.fator_usual(2.41) is None
    assert ajuste_b3.fator_usual(float("inf")) is None
    assert ajuste_b3.fator_usual(0.0) is None
