"""Extração de M&A por modelo de linguagem (série 1, PR 2): o modelo copia, o código confere."""

from datetime import date

import pandas as pd
import pytest

from base import ma_extracao as mx

TEXTO = (
    'FATO RELEVANTE. A Alfa Energia S.A. ("Companhia") comunica que, em 10 de março de 2024, '
    "celebrou contrato de compra e venda de ações para adquirir 100% do capital social da Beta "
    "Geração Ltda., detida pela Gama Participações S.A., pelo valor de R$ 1,25 bilhão, a ser pago "
    "em dinheiro. A Companhia passará a deter 100% das ações da Beta. O fechamento ocorreu em 2 de "
    "abril de 2024. O preço por ação é de US$ 3,10."
)
PUBLICO_EM = date(2024, 4, 5)


def _leitura(**campos) -> mx.LeituraDaOperacao:
    base = {
        "tipo": "AQ_CONTROLE",
        "etapa": "ASSINATURA",
        "trecho_do_tipo": "adquirir 100% do capital social da Beta",
        "partes": [
            {"nome": "Alfa Energia S.A.", "papel": "comprador", "participacao_depois": None,
             "trecho": "A Alfa Energia S.A. (\"Companhia\") comunica"},
            {"nome": "Beta Geração Ltda.", "papel": "alvo", "participacao_depois": 100,
             "trecho": "adquirir 100% do capital social da Beta Geração Ltda."},
            {"nome": "Gama Participações S.A.", "papel": "vendedor", "participacao_depois": None,
             "trecho": "detida pela Gama Participações S.A."},
        ],
        "valores": [
            {"campo": "valor_participacao", "valor": 1.25, "unidade": "bilhoes", "moeda": "BRL",
             "trecho": "pelo valor de R$ 1,25 bilhão"},
        ],
        "datas": [
            {"etapa": "ASSINATURA", "data": "2024-03-10", "trecho": "em 10 de março de 2024, celebrou"},
        ],
        "forma_pagamento": "dinheiro",
    }  # fmt: skip
    return mx.LeituraDaOperacao.model_validate(base | campos)


def _conferir(leitura: mx.LeituraDaOperacao) -> mx.LeituraConferida:
    return mx.conferir(leitura, TEXTO, PUBLICO_EM)


# --- o que o código prova no texto -------------------------------------------------------------


def test_leitura_certa_passa_inteira_sem_descarte_nem_problema():
    conferida = _conferir(_leitura())
    assert conferida.descartes == []
    assert conferida.problemas == []
    assert len(conferida.leitura.partes) == 3
    assert conferida.leitura.valores[0].valor == 1.25
    assert not conferida.precisa_de_revisao


def test_numero_sem_o_trecho_de_origem_e_descartado():
    inventado = {"campo": "valor_empresa", "valor": 2.0, "unidade": "bilhoes", "moeda": "BRL",
                 "trecho": "valor da empresa de R$ 2 bilhões"}  # fmt: skip
    errado = {"campo": "valor_participacao", "valor": 1.3, "unidade": "bilhoes", "moeda": "BRL",
              "trecho": "pelo valor de R$ 1,25 bilhão"}  # fmt: skip
    conferida = _conferir(_leitura(valores=[inventado, errado]))
    assert conferida.leitura.valores == []
    assert [d.motivo for d in conferida.descartes] == [
        mx.TRECHO_AUSENTE,
        mx.NUMERO_FORA_DO_TRECHO,
    ]


def test_moeda_diferente_do_simbolo_do_trecho_e_descartada():
    dolar = {"campo": "preco_por_acao", "valor": 3.10, "unidade": "unidade", "moeda": "BRL",
             "trecho": "O preço por ação é de US$ 3,10"}  # fmt: skip
    conferida = _conferir(_leitura(valores=[dolar]))
    assert conferida.leitura.valores == []
    assert conferida.descartes[0].motivo == mx.MOEDA_FORA_DO_TRECHO


def test_parte_cujo_nome_nao_esta_no_trecho_e_descartada():
    partes = [{"nome": "Delta S.A.", "papel": "comprador", "participacao_depois": None,
               "trecho": "A Alfa Energia S.A. (\"Companhia\") comunica"}]  # fmt: skip
    conferida = _conferir(_leitura(partes=partes))
    assert conferida.leitura.partes == []
    assert conferida.descartes[0].motivo == mx.NOME_FORA_DO_TRECHO


def test_participacao_sem_o_numero_no_trecho_perde_so_o_numero():
    partes = [{"nome": "Beta Geração Ltda.", "papel": "alvo", "participacao_depois": 60,
               "trecho": "capital social da Beta Geração Ltda."}]  # fmt: skip
    conferida = _conferir(_leitura(partes=partes))
    assert conferida.leitura.partes[0].nome == "Beta Geração Ltda."
    assert conferida.leitura.partes[0].participacao_depois is None
    assert conferida.descartes[0].motivo == mx.NUMERO_FORA_DO_TRECHO


def test_data_que_nao_esta_no_trecho_e_descartada():
    datas = [{"etapa": "ASSINATURA", "data": "2024-03-11", "trecho": "em 10 de março de 2024, celebrou"},
             {"etapa": "FECHAMENTO", "data": "2024-13-02", "trecho": "ocorreu em 2 de abril de 2024"}]  # fmt: skip
    conferida = _conferir(_leitura(datas=datas))
    assert conferida.leitura.datas == []
    assert [d.motivo for d in conferida.descartes] == [
        mx.DATA_FORA_DO_TRECHO,
        mx.DATA_INVALIDA,
    ]


@pytest.mark.parametrize(
    ("data", "trecho"),
    [
        ("2024-04-02", "O fechamento ocorreu em 2 de abril de 2024"),
        ("2024-04-02", "fechamento em 02/04/2024"),
        ("2024-04-02", "fechamento em 02.04.2024"),
    ],
)
def test_data_escrita_por_extenso_ou_com_barras_confere(data, trecho):
    texto = TEXTO + " " + trecho
    datas = [{"etapa": "FECHAMENTO", "data": data, "trecho": trecho}]
    conferida = mx.conferir(_leitura(datas=datas), texto, PUBLICO_EM)
    assert [d.data for d in conferida.leitura.datas] == [data]


# --- regras de coerência: não descartam, mandam para revisão humana -------------------------------


def test_participacoes_que_somam_mais_de_100_vao_para_revisao():
    texto = TEXTO + " A Alfa terá 70% e a Gama terá 40% da Beta."
    partes = [
        {"nome": "Alfa", "papel": "comprador", "participacao_depois": 70, "trecho": "A Alfa terá 70%"},
        {"nome": "Gama", "papel": "vendedor", "participacao_depois": 40, "trecho": "a Gama terá 40%"},
        {"nome": "Beta Geração Ltda.", "papel": "alvo", "participacao_depois": None,
         "trecho": "capital social da Beta Geração Ltda."},
    ]  # fmt: skip
    conferida = mx.conferir(_leitura(partes=partes), texto, PUBLICO_EM)
    assert mx.PARTICIPACOES_ACIMA_DE_100 in conferida.problemas
    assert conferida.precisa_de_revisao


def test_fechamento_antes_da_assinatura_vai_para_revisao():
    texto = TEXTO + " Assinado em 20 de abril de 2024."
    datas = [
        {
            "etapa": "ASSINATURA",
            "data": "2024-04-20",
            "trecho": "Assinado em 20 de abril de 2024",
        },
        {
            "etapa": "FECHAMENTO",
            "data": "2024-04-02",
            "trecho": "ocorreu em 2 de abril de 2024",
        },
    ]
    conferida = mx.conferir(_leitura(datas=datas), texto, PUBLICO_EM)
    assert mx.DATAS_FORA_DE_ORDEM in conferida.problemas


def test_assinatura_depois_da_publicacao_vai_para_revisao():
    conferida = mx.conferir(_leitura(), TEXTO, date(2024, 3, 1))
    assert mx.ASSINATURA_DEPOIS_DA_PUBLICACAO in conferida.problemas


def test_operacao_sem_alvo_vai_para_revisao():
    conferida = _conferir(_leitura(partes=[]))
    assert mx.SEM_ALVO in conferida.problemas


def test_nao_e_operacao_nao_exige_alvo():
    leitura = _leitura(tipo="NAO_E_OPERACAO", etapa=None, partes=[], valores=[], datas=[],
                       forma_pagamento="nao_informado")  # fmt: skip
    assert _conferir(leitura).problemas == []


def test_tipo_sem_trecho_vai_para_revisao():
    conferida = _conferir(_leitura(trecho_do_tipo="compra de 30% da Beta"))
    assert mx.TIPO_SEM_TRECHO in conferida.problemas


# --- duas leituras independentes --------------------------------------------------------------------


def test_duas_leituras_iguais_nao_divergem():
    a = _conferir(_leitura()).leitura
    b = _conferir(_leitura()).leitura
    assert mx.divergencias(a, b) == []


def test_duas_leituras_divergem_no_tipo_nas_partes_e_no_valor():
    a = _conferir(_leitura()).leitura
    b = _leitura(
        tipo="AQ_MINORITARIA",
        partes=[{"nome": "Gama Participações S.A.", "papel": "comprador",
                 "participacao_depois": None, "trecho": "Gama Participações"}],
        valores=[{"campo": "valor_participacao", "valor": 1250, "unidade": "milhoes",
                  "moeda": "BRL", "trecho": "x"},
                 {"campo": "valor_empresa", "valor": 9, "unidade": "bilhoes",
                  "moeda": "BRL", "trecho": "y"}],
    )  # fmt: skip
    assert mx.divergencias(a, b) == ["tipo", "alvo", "comprador", "vendedor"]


def test_nomes_batem_pela_palavra_que_distingue():
    assert mx.nomes_batem("Beta Geração Ltda.", "BETA GERACAO S.A.")
    assert mx.nomes_batem(
        "ALL – América Latina Logística S.A.", "América Latina Logística"
    )
    assert not mx.nomes_batem("Energisa S.A.", "Equatorial Energia S.A.")
    assert not mx.nomes_batem(
        "Brasil Participações S.A.", "Grupo Participações Brasil Ltda."
    )


# --- medir contra a amostra de ouro -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("R$ 2,121 bilhões (R$ 1,327 bilhão pelas ações)", {2.121e9, 1.327e9}),
        ("EV de US$ 202,2 milhões", {202.2e6}),
        ("R$ 57,2 mil", {57.2e3}),
        ("R$ 8,42 por ação", {8.42}),
        ("R$ 1.150 milhões", {1.15e9}),
        ("", set()),
    ],
)
def test_valores_do_ouro_viram_numeros(texto, esperado):
    assert mx.valores_do_ouro(texto) == pytest.approx(sorted(esperado))


def test_medir_conta_acertos_por_campo_chave():
    ouro = pd.DataFrame(
        {
            "Protocolo_Entrega": ["p1", "p2", "p3"],
            "confere_tiago": ["ok", "tipo: X", "nao"],
            "tipo_conferido": ["AQ_CONTROLE", "INC_EMPRESA", None],
            "alvo": ["Beta Geração", "Zeta S.A.", None],
            "comprador": ["Alfa Energia", None, None],
            "vendedor": ["Gama Participações", None, None],
            "valor": ["R$ 1,25 bilhão", None, None],
        }
    )
    certa = _conferir(_leitura()).leitura
    errada = _leitura(tipo="FUSAO", partes=[], valores=[], datas=[])
    nada = _leitura(tipo="NAO_E_OPERACAO", etapa=None, partes=[], valores=[], datas=[])
    placar = mx.medir({"p1": certa, "p2": errada, "p3": nada}, ouro).set_index("campo")
    assert placar.loc["tipo", ["casos", "acertos"]].tolist() == [3, 2]
    assert placar.loc["alvo", ["casos", "acertos"]].tolist() == [2, 1]
    assert placar.loc["comprador", ["casos", "acertos"]].tolist() == [1, 1]
    assert placar.loc["valor", ["casos", "acertos"]].tolist() == [1, 1]
    assert placar.loc["campos_chave", ["casos", "acertos"]].tolist() == [8, 6]


def test_medir_conta_leitura_que_faltou_como_erro():
    ouro = pd.DataFrame(
        {"Protocolo_Entrega": ["p1"], "confere_tiago": ["ok"], "tipo_conferido": ["CISAO"],
         "alvo": ["Beta"], "comprador": [None], "vendedor": [None], "valor": [None]}
    )  # fmt: skip
    placar = mx.medir({}, ouro).set_index("campo")
    assert placar.loc["tipo", ["casos", "acertos"]].tolist() == [1, 0]


def test_medir_deixa_de_fora_a_linha_em_duvida():
    ouro = pd.DataFrame(
        {"Protocolo_Entrega": ["p1"], "confere_tiago": ["duvida"], "tipo_conferido": [None],
         "alvo": [None], "comprador": [None], "vendedor": [None], "valor": [None]}
    )  # fmt: skip
    assert mx.medir({}, ouro).set_index("campo").loc["tipo", "casos"] == 0


# --- pedido e custo -----------------------------------------------------------------------------


def test_pedido_tem_guia_em_cache_esquema_e_texto_cortado():
    pedido = mx.pedido("x" * 50_000, mx.MODELO)
    assert pedido["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "AQ_CONTROLE" in pedido["system"][0]["text"]
    assert pedido["output_config"]["format"]["schema"] == mx.ESQUEMA_DA_RESPOSTA
    assert len(pedido["messages"][0]["content"]) <= mx.MAX_CARACTERES_DO_TEXTO


def test_esquema_lista_os_codigos_do_dicionario():
    tipos = mx.ESQUEMA_DA_RESPOSTA["properties"]["tipo"]["enum"]
    assert {"AQ_CONTROLE", "OPA_CANCEL", "UPI", "NAO_E_OPERACAO"} <= set(tipos)


def test_custo_pelo_lote_e_a_metade_e_modelo_sem_preco_e_erro():
    assert mx.custo_em_dolares(
        1_000_000, 0, lote=False, modelo=mx.MODELO
    ) == pytest.approx(0.10)
    assert mx.custo_em_dolares(
        1_000_000, 1_000_000, modelo=mx.CONFERENTE
    ) == pytest.approx(6.0)
    with pytest.raises(ValueError):
        mx.custo_em_dolares(1, 1, modelo="claude-qualquer")


def test_estimativa_sem_api_cresce_com_o_texto():
    curto = mx.estimar_custo(["a" * 1_000], mx.MODELO)
    longo = mx.estimar_custo(["a" * 10_000], mx.MODELO)
    assert 0 < curto < longo
