"""Gráficos escolhidos pelo modelo (plano de 23/10/2026): o formato da escolha e o cardápio.

O modelo escolhe a forma (um tipo do cardápio), a tabela da ficha e as colunas; nunca manda número.
"""

import pytest

from src.analise_escrita import graficos as gr
from src.analise_escrita import saida

ENTRADA = {
    "empresa": "CPFL ENERGIA S.A.",
    "corte": "2026-10-17",
    "linhas": [
        {"id": "historico.contas.0", "tipo": "linha", "tabela": "Contas ano a ano",
         "celulas": {"ano": 2023, "receita": 4.1e10, "lucro_liquido": 5.1e9, "nome": "x"}},
        {"id": "historico.contas.1", "tipo": "linha", "tabela": "Contas ano a ano",
         "celulas": {"ano": 2024, "receita": 4.4e10, "lucro_liquido": 5.4e9, "nome": "y"}},
        {"id": "historico.contas.2", "tipo": "linha", "tabela": "Contas ano a ano",
         "celulas": {"ano": 2025, "receita": 4.5e10, "lucro_liquido": None, "nome": "z"}},
        {"id": "ofertas_e_fundos.fundos_por_mes.0", "tipo": "linha", "tabela": "Fundos",
         "celulas": {"Mês": "abr/2024", "Fundos": "436", "Valor nas carteiras": "R$ 655,8 mi"}},
        {"id": "ofertas_e_fundos.fundos_por_mes.1", "tipo": "linha", "tabela": "Fundos",
         "celulas": {"Mês": "mai/2024", "Fundos": "440", "Valor nas carteiras": "R$ 700,1 mi"}},
        {"id": "resultado.receita", "tipo": "numero", "texto": "R$ 44,4 bi", "valor": 4.44e10},
    ],
}  # fmt: skip

RESPOSTA = {
    "graficos": [
        {
            "tipo": "linha_no_tempo",
            "tabela": "historico.contas",
            "eixo": "ano",
            "colunas": ["receita"],
            "titulo": "Receita ano a ano",
            "parte": "o_que_os_numeros_mostram",
            "paragrafo": 0,
            "por_que": {
                "texto": "A receita subiu nos três anos da base.",
                "notas": ["historico.contas.0", "historico.contas.2"],
                "contas": [],
            },
        }
    ],
    "destaques": [
        {
            "secao": "ofertas_e_fundos",
            "parte": "quem_manda",
            "por_que": {"texto": "Os fundos entram e saem.", "notas": [], "contas": []},
        }
    ],
}


def test_resposta_valida_vira_escolha():
    escolha = gr.ler_escolha(RESPOSTA)
    grafico = escolha.graficos[0]
    assert grafico.tipo == "linha_no_tempo"
    assert grafico.tabela == "historico.contas"
    assert grafico.colunas == ("receita",)
    assert grafico.por_que.notas == ("historico.contas.0", "historico.contas.2")
    assert grafico.origem == saida.ORIGEM_MODELO
    assert escolha.destaques[0].secao == "ofertas_e_fundos"


def test_escolha_volta_ao_mesmo_dict():
    escolha = gr.ler_escolha(RESPOSTA)
    assert gr.ler_escolha(escolha.como_dict()) == escolha


@pytest.mark.parametrize(
    "estrago",
    [
        {"tipo": "pizza_3d"},
        {"colunas": []},
        {"titulo": "  "},
        {"paragrafo": -1},
        {"por_que": {"texto": "", "notas": [], "contas": []}},
    ],
)
def test_grafico_fora_do_formato_e_invalido(estrago):
    resposta = {**RESPOSTA, "graficos": [{**RESPOSTA["graficos"][0], **estrago}]}
    with pytest.raises(saida.RespostaInvalidaError):
        gr.ler_escolha(resposta)


def test_resposta_sem_lista_de_graficos_e_invalida():
    with pytest.raises(saida.RespostaInvalidaError):
        gr.ler_escolha({"destaques": []})


def test_o_esquema_so_aceita_os_tipos_do_cardapio():
    tipos = gr.ESQUEMA["properties"]["graficos"]["items"]["properties"]["tipo"]["enum"]
    assert set(tipos) == set(gr.CARDAPIO)


def test_tabelas_da_entrada_juntam_as_linhas_pela_tabela():
    tabelas = gr.tabelas_da_entrada(ENTRADA)
    assert set(tabelas) == {"historico.contas", "ofertas_e_fundos.fundos_por_mes"}
    assert [li.id for li in tabelas["historico.contas"]] == [
        "historico.contas.0",
        "historico.contas.1",
        "historico.contas.2",
    ]


@pytest.mark.parametrize(
    ("celula", "valor"),
    [
        (4.1e10, 4.1e10),
        (12, 12.0),
        ("436", 436.0),
        ("R$ 655,8 mi", 655.8e6),
        ("11,1%", 0.111),
        ("9.743.641", 9743641.0),
        (None, None),
        (True, None),  # "cumpriu" não é número
        ("sim", None),
        ("de 2 a 3", None),  # dois números: não dá para escolher um
    ],
)
def test_valor_da_celula(celula, valor):
    lido = gr.valor_da_celula(celula)
    assert lido == pytest.approx(valor) if valor is not None else lido is None


@pytest.mark.parametrize(
    ("celula", "ano", "mes"),
    [(2024, 2024, None), ("2025", 2025, None), ("abr/2024", 2024, 4),
     ("31/12/2023", 2023, 12), ("texto", None, None), (1.5, None, None)],
)  # fmt: skip
def test_momento_da_celula(celula, ano, mes):
    momento = gr.momento_da_celula(celula)
    if ano is None:
        assert momento is None
    else:
        assert (momento.ano, momento.mes) == (ano, mes)
