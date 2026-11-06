"""Comps por transação (B-25): os múltiplos pagos no setor até a data, com mediana, quartis e rastro, e
o princípio "sem olhar o futuro" (cortar o futuro não muda o passado), também com o Hypothesis."""

import json
from datetime import date, timedelta

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from base import ma_extracao as mx
from base import ma_multiplos as mm
from base import ma_operacoes as mo
from src import comps_por_transacao as ct
from src.demonstracoes import EXERCICIO, POSICAO
from src.setores import SEM_GRUPO

EMPRESA = "00.000.000/0001-00"
ENERGIA, VAREJO = "Energia Elétrica", "Comércio (Atacado e Varejo)"
DIA = date(2025, 6, 30)


def _linha(n: int, ev_ebitda: float | None, anuncio: date, **outros) -> dict:
    return {
        "operacao": f"op{n}",
        "alvo": f"Alvo {n} S.A.",
        "alvo_cnpj": f"{n:02d}.111.111/0001-11",
        "anuncio": anuncio,
        "valor_protocolo": f"protocolo-{n}",
        "valor_publico_em": anuncio,
        "base_12m": "exercício encerrado em 31/12/2024",
        "entregue_ate": anuncio - timedelta(days=30),
        "ev_ebitda": ev_ebitda,
        "ev_receita": None,
        "ev_ebit": None,
    } | outros


def _setores(tabela: pd.DataFrame, setor: str = ENERGIA) -> dict[str, str]:
    return {cnpj: setor for cnpj in tabela["alvo_cnpj"]} | {EMPRESA: ENERGIA}


def _gabarito() -> pd.DataFrame:
    linhas = [
        _linha(1, 4.0, date(2021, 3, 1)),
        _linha(2, 6.0, date(2022, 3, 1)),
        _linha(3, 8.0, date(2023, 3, 1)),
        _linha(4, 10.0, date(2024, 3, 1)),
        _linha(5, 30.0, date(2024, 4, 1)),  # outro setor (abaixo)
        _linha(6, 50.0, date(2025, 7, 1)),  # anunciada depois da data
        _linha(
            7, 60.0, date(2025, 1, 1), valor_publico_em=date(2025, 8, 1)
        ),  # valor depois
        _linha(8, None, date(2024, 5, 1)),  # sem múltiplo
    ]
    return pd.DataFrame(linhas)


def _comps(tabela: pd.DataFrame, dia: date = DIA) -> ct.CompsPorTransacao:
    setores = _setores(tabela) | {"05.111.111/0001-11": VAREJO}
    return ct.comps_por_transacao(tabela, setores, EMPRESA, dia)


def test_gabarito_da_mediana_e_dos_quartis():
    # 4, 6, 8 e 10 (quartis inclusivos, à mão): Q1 = 4 + 0,75 × (6 − 4) = 5,5; mediana 7;
    # Q3 = 8 + 0,25 × (10 − 8) = 8,5
    resumo = _comps(_gabarito()).do_multiplo("ev_ebitda")
    assert [p.multiplo for p in resumo.precedentes] == [4.0, 6.0, 8.0, 10.0]
    assert (resumo.primeiro_quartil, resumo.mediana, resumo.terceiro_quartil) == (
        5.5,
        7.0,
        8.5,
    )
    assert resumo.motivo == ""


def test_o_valor_publicado_depois_do_anuncio_conta_do_dia_do_valor():
    tabela = _gabarito()
    antes = _comps(tabela, date(2025, 7, 31)).do_multiplo("ev_ebitda")
    depois = _comps(tabela, date(2025, 8, 1)).do_multiplo("ev_ebitda")
    assert "op7" not in [p.operacao for p in antes.precedentes]
    op7 = next(p for p in depois.precedentes if p.operacao == "op7")
    assert (op7.anuncio, op7.disponivel_em) == (date(2025, 1, 1), date(2025, 8, 1))


def test_poucos_precedentes_ficam_sem_mediana_com_o_motivo():
    resumo = _comps(_gabarito(), date(2022, 12, 31)).do_multiplo("ev_ebitda")
    assert resumo.quantos == 2
    assert resumo.mediana is None and resumo.primeiro_quartil is None
    assert "menos de 3" in resumo.motivo
    assert _comps(_gabarito()).do_multiplo("ev_receita").motivo


def test_empresa_sem_setor_fica_sem_comps():
    tabela = _gabarito()
    comps = ct.comps_por_transacao(tabela, _setores(tabela), "99.999.999/0001-99", DIA)
    assert (comps.grupo, comps.multiplos, comps.motivo) == (SEM_GRUPO, (), ct.SEM_SETOR)


def test_cada_numero_tem_rastro_completo():
    resumo = _comps(_gabarito()).do_multiplo("ev_ebitda")
    assert resumo.rastro.o_que_falta() == []
    assert resumo.rastro.publicado_em == date(2024, 3, 1)  # o precedente mais novo
    for precedente in resumo.precedentes:
        assert precedente.rastro.o_que_falta() == []
        assert precedente.rastro.fonte_id == ct.FONTE_DO_VALOR
        assert precedente.rastro.outras_fontes == (ct.FONTE_DOS_NUMEROS,)
        assert precedente.rastro.publicado_em == precedente.disponivel_em
        assert "protocolo" in precedente.rastro.documentos[0].nome


def test_como_dict_vira_json():
    texto = json.dumps(_comps(_gabarito()).como_dict())
    assert '"como_era_em": "2025-06-30"' in texto


def test_nada_aqui_e_preco_alvo_nem_recomendacao():
    textos = " ".join(ct.LIMITES).lower()
    assert "não um preço nem uma recomendação" in textos
    for proibido in ("preço-alvo", "vale r$", "recomendamos", "comprar", "vender"):
        assert proibido not in textos and proibido not in (ct.__doc__ or "").lower()


DIAS = st.dates(min_value=date(2015, 1, 1), max_value=date(2026, 12, 31))


@st.composite
def _tabelas(desenho: st.DrawFn) -> pd.DataFrame:
    quantas = desenho(st.integers(min_value=0, max_value=12))
    linhas = []
    for n in range(quantas):
        anuncio = desenho(DIAS)
        atraso = desenho(st.integers(min_value=0, max_value=400))
        multiplo = desenho(
            st.one_of(
                st.none(), st.floats(min_value=0.1, max_value=40, allow_nan=False)
            )
        )
        linhas.append(
            _linha(
                n, multiplo, anuncio, valor_publico_em=anuncio + timedelta(days=atraso)
            )
        )
    return pd.DataFrame(linhas, columns=list(_linha(0, None, DIA)))


@settings(max_examples=150, deadline=None)
@given(tabela=_tabelas(), corte=DIAS)
def test_cortar_o_futuro_nao_muda_o_passado(tabela: pd.DataFrame, corte: date):
    """Os comps de `corte` são os mesmos com ou sem as operações que só ficaram públicas depois."""
    setores = _setores(tabela)
    completo = ct.comps_por_transacao(tabela, setores, EMPRESA, corte)
    publicas = [ct.disponivel_em(linha) <= corte for linha in tabela.to_dict("records")]
    cortada = tabela[pd.Series(publicas, index=tabela.index, dtype=bool)]
    assert ct.comps_por_transacao(cortada, setores, EMPRESA, corte) == completo
    for resumo in completo.multiplos:
        assert all(p.disponivel_em <= corte for p in resumo.precedentes)


# do documento do IPE à tabela: um documento publicado depois do dia não muda o precedente do dia

CNPJ_DA_ALVO = "11.111.111/0001-11"
ALVO = "Gama Energia S.A."
ANUNCIO = date(2025, 5, 10)
EMISSORAS = {
    "fato": mm.Emissora(CNPJ_DA_ALVO, "GAMA ENERGIA SA"),
    "comunicado": mm.Emissora(CNPJ_DA_ALVO, "GAMA ENERGIA SA"),
}


def _leitura(protocolo: str, dia: date, valores: list[dict]) -> mo.DocumentoLido:
    leitura = mx.LeituraDaOperacao.model_validate(
        {
            "tipo": "AQ_CONTROLE",
            "partes": [{"nome": ALVO, "papel": "alvo", "trecho": ALVO}],
            "valores": [
                {"trecho": "trecho", "unidade": "unidade", "moeda": "BRL"} | v
                for v in valores
            ],
        }
    )
    return mo.DocumentoLido(protocolo, dia, leitura)


def _cvm() -> tuple[pd.DataFrame, pd.DataFrame]:
    referencia, recebido = date(2024, 12, 31), date(2025, 3, 1)
    contas = {
        EXERCICIO: {"receita": 480.0, "ebit": 60.0, "depreciacao": 20.0,
                    "lucro_controladores": 50.0, "lpa_basico": 5.0},
        POSICAO: {"patrimonio_liquido": 100.0, "divida_cp": 30.0, "divida_lp": 20.0,
                  "caixa": 10.0, "acoes_total": 11.0, "acoes_tesouraria": 1.0},
    }  # fmt: skip
    linhas = [
        {"cnpj": CNPJ_DA_ALVO, "documento": "DFP", "referencia": referencia, "versao": 1,
         "periodo": periodo, "inicio": None, "fim": referencia, "conta": conta, "valor": valor}
        for periodo, valores in contas.items() for conta, valor in valores.items()
    ]  # fmt: skip
    indice = {"cnpj": CNPJ_DA_ALVO, "empresa": "GAMA ENERGIA SA", "documento": "DFP",
              "referencia": referencia, "versao": 1, "recebido_em": recebido, "link": ""}  # fmt: skip
    return pd.DataFrame(linhas), pd.DataFrame([indice])


@pytest.mark.parametrize(
    ("dia", "multiplo"),
    [
        (
            date(2025, 5, 31),
            3.0,
        ),  # preço R$ 20 × 10 ações + dívida líquida 40 = 240; ÷ 80
        (
            date(2025, 6, 30),
            3.75,
        ),  # o EV de 300 do comunicado (o EV vence o preço) ÷ 80
    ],
)
def test_documento_publicado_depois_nao_muda_o_precedente_do_dia(
    dia: date, multiplo: float
):
    documentos = [
        _leitura("fato", ANUNCIO, [{"campo": mm.PRECO_POR_ACAO, "valor": 20.0}]),
        _leitura(
            "comunicado",
            date(2025, 6, 15),
            [{"campo": mm.VALOR_DA_EMPRESA, "valor": 0.3, "unidade": "mil"}],
        ),
    ]
    tabela = ct.precedentes_como_eram_em(documentos, EMISSORAS, *_cvm(), dia)
    setores = {CNPJ_DA_ALVO: ENERGIA, EMPRESA: ENERGIA}
    resumo = ct.comps_por_transacao(tabela, setores, EMPRESA, dia).do_multiplo(
        "ev_ebitda"
    )
    assert [p.multiplo for p in resumo.precedentes] == [multiplo]
