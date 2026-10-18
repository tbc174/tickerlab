"""Múltiplos implícitos das operações de M&A: o preço lido dividido pelos números da alvo entregues à
CVM **antes** do anúncio (o teste de "sem olhar o futuro" do plano), com as contas no formato de
`src.demonstracoes.ler_demonstracoes`."""

from datetime import date

import pandas as pd
import pytest

from base import ma_extracao as mx
from base import ma_multiplos as mm
from base import ma_operacoes as mo
from src.demonstracoes import ACUMULADO, ACUMULADO_ANTERIOR, EXERCICIO, POSICAO

CNPJ = "11.111.111/0001-11"
ALVO = "Gama Logística S.A."
ANUNCIO = date(2025, 5, 10)
DFP_2024 = (date(2024, 12, 31), date(2025, 3, 1))  # (referência, recebido em)

BALANCO = {"patrimonio_liquido": 100.0, "divida_cp": 30.0, "divida_lp": 20.0, "caixa": 10.0,
           "acoes_total": 11.0, "acoes_tesouraria": 1.0}  # fmt: skip
ANO = {"receita": 480.0, "ebit": 60.0, "lucro_liquido": 50.0, "lucro_controladores": 50.0,
       "lpa_basico": 5.0}  # fmt: skip


def _documento(documento: str, referencia: date, recebido: date, contas: dict) -> tuple:
    linhas = [
        {"cnpj": CNPJ, "documento": documento, "referencia": referencia, "versao": 1,
         "periodo": periodo, "inicio": None, "fim": referencia, "conta": conta, "valor": valor}
        for periodo, valores in contas.items() for conta, valor in valores.items()
    ]  # fmt: skip
    indice = {"cnpj": CNPJ, "empresa": ALVO.upper(), "documento": documento,
              "referencia": referencia, "versao": 1, "recebido_em": recebido, "link": ""}  # fmt: skip
    return linhas, indice


def _cvm(*documentos: tuple) -> tuple[pd.DataFrame, pd.DataFrame]:
    contas = [linha for linhas, _ in documentos for linha in linhas]
    return pd.DataFrame(contas), pd.DataFrame([indice for _, indice in documentos])


def _dfp(
    referencia: date, recebido: date, ano: dict = ANO, balanco: dict = BALANCO
) -> tuple:
    return _documento("DFP", referencia, recebido, {EXERCICIO: ano, POSICAO: balanco})


def _leitura(
    protocolo: str, dia: date, valores: list[dict], alvo: str = ALVO
) -> mo.DocumentoLido:
    leitura = mx.LeituraDaOperacao.model_validate(
        {
            "tipo": "AQ_CONTROLE",
            "partes": [{"nome": alvo, "papel": "alvo", "trecho": alvo}],
            "valores": [
                {"trecho": "trecho", "unidade": "unidade", "moeda": "BRL"} | v
                for v in valores
            ],
        }
    )
    return mo.DocumentoLido(protocolo, dia, leitura)


PRECO = {"campo": mm.PRECO_POR_ACAO, "valor": 20.0}
EMISSORAS = {"fato": mm.Emissora(CNPJ, "GAMA LOGISTICA SA")}


def _linha(documentos: list[mo.DocumentoLido], *cvm: tuple) -> dict:
    tabela = mm.multiplos(documentos, EMISSORAS, *_cvm(*cvm))
    assert len(tabela) == 1
    return tabela.iloc[0].to_dict()


def test_preco_por_acao_vira_os_quatro_multiplos():
    linha = _linha([_leitura("fato", ANUNCIO, [PRECO])], _dfp(*DFP_2024))
    # 10 ações em circulação (11 − 1 em tesouraria) × R$ 20; dívida líquida 30 + 20 − 10 = 40
    assert linha["valor_do_patrimonio"] == 200.0
    assert linha["valor_da_empresa"] == 240.0
    assert (linha["p_l"], linha["p_vp"]) == (4.0, 2.0)
    assert (linha["ev_receita"], linha["ev_ebit"]) == (0.5, 4.0)
    assert linha["alvo_cnpj"] == CNPJ
    assert linha["motivo"] == ""


def test_valor_da_empresa_lido_tira_a_divida_para_o_patrimonio():
    ev = {"campo": mm.VALOR_DA_EMPRESA, "valor": 0.3, "unidade": "mil"}
    linha = _linha([_leitura("fato", ANUNCIO, [PRECO, ev])], _dfp(*DFP_2024))
    assert linha["valor_campo"] == mm.VALOR_DA_EMPRESA  # o EV vence o preço por ação
    assert (linha["valor_da_empresa"], linha["valor_do_patrimonio"]) == (300.0, 260.0)


def test_sem_olhar_o_futuro():
    # o DFP de 2024 foi reentregue no dia do anúncio com outro lucro, e o ITR saiu depois: nenhum
    # dos dois vale; fica o DFP de 2023, entregue antes
    dfp_2023 = _dfp(
        date(2023, 12, 31),
        date(2024, 3, 1),
        ANO | {"lucro_controladores": 25.0, "lpa_basico": 2.5},
    )
    reentregue = _dfp(DFP_2024[0], ANUNCIO, ANO | {"lucro_controladores": 100.0})
    itr = _documento("ITR", date(2025, 3, 31), date(2025, 5, 12),
                     {ACUMULADO: ANO, ACUMULADO_ANTERIOR: ANO, POSICAO: BALANCO})  # fmt: skip
    linha = _linha([_leitura("fato", ANUNCIO, [PRECO])], dfp_2023, reentregue, itr)
    assert linha["entregue_ate"] < ANUNCIO
    assert linha["base_12m"] == "exercício encerrado em 31/12/2023"
    assert linha["p_l"] == 8.0  # 200 ÷ 25, não 200 ÷ 100


def test_nada_entregue_antes_do_anuncio_fica_sem_multiplo():
    linha = _linha([_leitura("fato", ANUNCIO, [PRECO])], _dfp(DFP_2024[0], ANUNCIO))
    assert linha["motivo"] == mm.SEM_DOCUMENTO
    assert pd.isna(linha["p_l"])


def test_prejuizo_e_patrimonio_negativo_nao_viram_multiplo():
    ano = ANO | {"lucro_controladores": -5.0, "lucro_liquido": -5.0, "lpa_basico": -0.5}
    linha = _linha(
        [_leitura("fato", ANUNCIO, [PRECO])],
        _dfp(*DFP_2024, ano, BALANCO | {"patrimonio_liquido": -1.0}),
    )
    assert pd.isna(linha["p_l"]) and pd.isna(linha["p_vp"])
    assert linha["ev_receita"] == 0.5


@pytest.mark.parametrize(
    ("valores", "alvo", "motivo"),
    [
        ([PRECO], "Delta Transportes Ltda.", mm.ALVO_FECHADA),
        ([], ALVO, mm.SEM_VALOR),
        ([{"campo": "valor_participacao", "valor": 10.0}], ALVO, mm.SO_PARTICIPACAO),
        ([PRECO | {"moeda": "USD"}], ALVO, mm.OUTRA_MOEDA),
    ],
)
def test_motivo_de_ficar_sem_multiplo(valores: list[dict], alvo: str, motivo: str):
    linha = _linha([_leitura("fato", ANUNCIO, valores, alvo)], _dfp(*DFP_2024))
    assert linha["motivo"] == motivo


def test_a_alvo_e_a_emissora_de_algum_documento_da_operacao():
    # a compradora publicou primeiro; a alvo, no mesmo dia: o CNPJ é o da alvo, não o da compradora
    emissoras = EMISSORAS | {
        "compradora": mm.Emissora("22.222.222/0001-22", "OUTRA SA")
    }
    membros = [_leitura("compradora", ANUNCIO, [PRECO]), _leitura("fato", ANUNCIO, [])]
    assert mm.alvo_aberta(membros, emissoras) == (CNPJ, "")
    assert mm.alvo_aberta(membros[:1], emissoras) == (None, mm.ALVO_FECHADA)


def test_controlada_com_o_nome_da_emissora_nao_e_a_emissora():
    # amostra de ouro: a ENERGISA S.A. publicou a venda da Energisa Bioeletricidade
    assert not mx.nome_cobre("Energisa Bioeletricidade S/A", "ENERGISA SA")
    assert not mx.nome_cobre("ITAUTEC S.A. – GRUPO ITAUTEC", "ITAUSA S.A.")
    assert not mx.nome_cobre(
        "Gol", "GOLDMAN SACHS DO BRASIL"
    )  # palavra curta não vale colada
    abreviados = [
        ("Ingá Agroflorestal S.A.", "INGA AGRO FLORESTAL SA"),
        ("Usinas Siderúrgicas de Minas Gerais S.A. – USIMINAS", "USINAS SID DE MINAS GERAIS S.A.-USIMINAS"),
        ("Eucatex S.A. – Indústria e Comércio", "EUCATEX SA IND COM"),
        ("Pan", "BANCO PAN SA"),
    ]  # fmt: skip
    for nome, abreviado in abreviados:
        assert mx.nome_cobre(nome, abreviado), nome
