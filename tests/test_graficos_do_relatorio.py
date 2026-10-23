"""Os desenhos dos gráficos que o modelo escolhe: pontos só da ficha, sem olhar o futuro, barras do zero.

Cada tipo do cardápio entra em `CASOS` com a ficha pequena abaixo; os três testes do plano rodam
para todos os tipos que o desenho já cobre.
"""

import copy
from datetime import date

import pytest

from src import graficos_do_relatorio as gdr
from src.analise_escrita import graficos as gr
from src.analise_escrita import saida

PNG = b"\x89PNG"


def _linhas(tabela: str, celulas: list[dict]) -> list[dict]:
    return [
        {"id": f"{tabela}.{i}", "tipo": "linha", "tabela": tabela, "celulas": dict(c)}
        for i, c in enumerate(celulas)
    ]


PASSOS = [
    {"passo": "Receita", "valor": 44.4e9},
    {"passo": "Custos", "valor": -30.0e9},
    {"passo": "Impostos", "valor": -4.4e9},
    {"passo": "Lucro", "valor": 10.0e9},
]
EMPRESAS = [
    {"empresa": "CPFL", "receita": "R$ 45,6 bi", "lucro": "R$ 5,1 bi"},
    {"empresa": "Equatorial", "receita": "R$ 29,0 bi", "lucro": "R$ 2,2 bi"},
    {"empresa": "Eletrobras", "receita": "R$ 37,3 bi", "lucro": None},
]
INDICADORES = [
    {"indicador": "Receita", "antes": "R$ 45,1 bi", "agora": "R$ 45,6 bi"},
    {"indicador": "Lucro", "antes": "R$ 5,4 bi", "agora": "R$ 5,1 bi"},
]


def _ficha() -> dict:
    anos = [
        {"ano": 2020, "receita": "R$ 41,0 bi", "lucro": "R$ 5,1 bi"},
        {"ano": 2021, "receita": "R$ 43,5 bi", "lucro": "R$ 5,4 bi"},
        {"ano": 2022, "receita": "R$ 40,2 bi", "lucro": "R$ 3,9 bi"},
        {"ano": 2023, "receita": "R$ 44,0 bi", "lucro": "R$ 6,0 bi"},
        {"ano": 2024, "receita": "R$ 45,6 bi", "lucro": None},
    ]
    return {
        "empresa": "CPFL ENERGIA S.A.",
        "corte": "2024-12-31",
        "secoes": {"historico": "Histórico"},
        "linhas": [
            *_linhas("historico.contas", anos),
            *_linhas("setor.empresas", EMPRESAS),
            *_linhas("o_que_mudou.indicadores", INDICADORES),
            *_linhas("resultado.cascata", PASSOS),
        ],
    }


def _grafico(tipo: str, tabela: str, eixo: str, *colunas: str) -> gr.Grafico:
    return gr.Grafico(
        tipo=tipo, tabela=tabela, eixo=eixo, colunas=colunas, titulo="Título",
        parte="o_que_os_numeros_mostram", paragrafo=0,
        por_que=saida.Frase("O gráfico mostra a série.", ("historico.contas.0",)),
    )  # fmt: skip


# tipo → (gráfico, valores esperados por coluna lidos à mão da ficha acima, em unidades da ficha)
CASOS = {
    "linha_no_tempo": (
        _grafico("linha_no_tempo", "historico.contas", "ano", "receita", "lucro"),
        (
            (41e9, 43.5e9, 40.2e9, 44e9, 45.6e9),
            (5.1e9, 5.4e9, 3.9e9, 6e9, None),
        ),
    ),
    "barras_no_tempo": (
        _grafico("barras_no_tempo", "historico.contas", "ano", "receita"),
        ((41e9, 43.5e9, 40.2e9, 44e9, 45.6e9),),
    ),
    "barras_por_categoria": (
        _grafico("barras_por_categoria", "setor.empresas", "empresa", "receita"),
        ((45.6e9, 29e9, 37.3e9),),
    ),
    "antes_e_agora": (
        _grafico(
            "antes_e_agora", "o_que_mudou.indicadores", "indicador", "antes", "agora"
        ),
        ((45.1e9, 5.4e9), (45.6e9, 5.1e9)),
    ),
    "dispersao": (
        _grafico("dispersao", "setor.empresas", "empresa", "receita", "lucro"),
        ((45.6e9, 29e9), (5.1e9, 2.2e9)),  # a Eletrobras sem lucro não vira ponto
    ),
    "cascata": (
        _grafico("cascata", "resultado.cascata", "passo", "valor"),
        ((44.4e9, -30e9, -4.4e9, 10e9),),
    ),
}
COM_TEMPO = [t for t in CASOS if gr.CARDAPIO[t].eixo == gr.TEMPO]
DE_BARRAS = [t for t in CASOS if t in ("barras_no_tempo", "barras_por_categoria", "antes_e_agora", "cascata")]  # fmt: skip


@pytest.mark.parametrize("tipo", CASOS)
def test_pontos_saem_so_da_ficha(tipo):
    grafico, esperado = CASOS[tipo]
    ficha = _ficha()

    pontos = gdr.pontos_do_grafico(grafico, ficha)

    assert pontos.valores == esperado
    assert pontos.ids[0] == f"{grafico.tabela}.0"
    # trocar um número na ficha muda o ponto: o desenho não tem outra fonte de número
    outra = copy.deepcopy(ficha)
    primeira = next(li for li in outra["linhas"] if li["id"] == f"{grafico.tabela}.0")
    primeira["celulas"][grafico.colunas[0]] = "R$ 99,0 bi"
    assert gdr.pontos_do_grafico(grafico, outra).valores[0][0] == 99e9


@pytest.mark.parametrize("tipo", [t for t in CASOS if t not in COM_TEMPO])
def test_grafico_sem_datas_nao_perde_linha_no_corte(tipo):
    grafico, _ = CASOS[tipo]

    antigo = gdr.pontos_do_grafico(grafico, _ficha(), corte=date(2000, 1, 1))

    assert antigo == gdr.pontos_do_grafico(grafico, _ficha())  # não há data para cortar


@pytest.mark.parametrize("tipo", COM_TEMPO)
def test_grafico_respeita_o_corte(tipo):
    grafico, _ = CASOS[tipo]
    ficha = _ficha()

    inteiro = gdr.pontos_do_grafico(grafico, ficha)
    cortado = gdr.pontos_do_grafico(grafico, ficha, corte=date(2022, 12, 31))

    assert cortado.rotulos == ("2020", "2021", "2022")
    assert "2023" in inteiro.rotulos
    # cortar o futuro não muda o passado
    n = len(cortado.rotulos)
    assert cortado.rotulos == inteiro.rotulos[:n]
    assert cortado.valores == tuple(coluna[:n] for coluna in inteiro.valores)


@pytest.mark.parametrize("tipo", CASOS)
def test_figuras_saem_nas_duas_saidas(tipo):
    grafico, _ = CASOS[tipo]
    pontos = gdr.pontos_do_grafico(grafico, _ficha())

    plotly = gdr.figura(pontos)
    imagem = gdr.png(pontos)

    assert len(plotly.data[0].y) == len(pontos.rotulos)
    assert imagem.startswith(PNG)


def test_linha_vai_para_a_escala_do_dinheiro_e_deixa_vao_onde_falta_numero():
    grafico, _ = CASOS["linha_no_tempo"]
    plotly = gdr.figura(gdr.pontos_do_grafico(grafico, _ficha()))

    assert plotly.data[0].y[0] == pytest.approx(41.0)  # R$ bilhões
    assert plotly.data[1].y[-1] is None  # 2024 sem lucro: vão, não zero
    assert "R$ bilhões" in plotly.layout.title.text


@pytest.mark.parametrize("tipo", DE_BARRAS)
def test_barras_comecam_do_zero(tipo):
    grafico, _ = CASOS[tipo]
    ficha = _ficha()
    # números todos altos e parecidos: sem o zero, a diferença parece enorme
    for i, linha in enumerate(
        li for li in ficha["linhas"] if li["id"].startswith(grafico.tabela + ".")
    ):
        for coluna in grafico.colunas:
            linha["celulas"][coluna] = f"R$ {90 + i},0 bi"
    pontos = gdr.pontos_do_grafico(grafico, ficha)

    plotly = gdr.figura(pontos)
    eixo_pdf = gdr.figura_do_pdf(pontos).axes[0]

    assert plotly.layout.yaxis.rangemode == "tozero"
    assert eixo_pdf.get_ylim()[0] <= 0


def test_cascata_na_escala_do_dinheiro_e_dispersao_com_um_indicador_em_cada_eixo():
    cascata = gdr.pontos_do_grafico(CASOS["cascata"][0], _ficha())
    dispersao = gdr.pontos_do_grafico(CASOS["dispersao"][0], _ficha())

    passos = gdr.figura(cascata).data[0]
    pontos = gdr.figura(dispersao).data[0]

    assert list(passos.y) == pytest.approx([44.4, -30.0, -4.4, 10.0])
    assert "R$ bilhões" in gdr.figura(cascata).layout.title.text
    assert list(pontos.x) == pytest.approx([45.6, 29.0])
    assert list(pontos.y) == pytest.approx([5.1, 2.2])
    assert list(pontos.text) == ["CPFL", "Equatorial"]
