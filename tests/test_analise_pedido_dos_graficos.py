"""O pedido que escolhe os gráficos e a porta 2 que os julga, sem rede.

O cardápio do guia sai de `CARDAPIO` (uma lista só); a porta 2 nunca aprova por falta.
"""

import json

import pytest

from src.analise_escrita import graficos as gr
from src.analise_escrita import pedido as pe
from src.analise_escrita import pedido_dos_graficos as pg
from src.analise_escrita import porta1_dos_graficos as p1g
from src.analise_escrita import porta2_dos_graficos as p2g
from src.analise_escrita import saida, series
from tests.ajudantes_da_analise import PAR_DA_CPFL
from tests.ajudantes_da_analise_do_setor import PAR_DO_SETOR

ENTRADA = json.loads((PAR_DA_CPFL / "entrada.json").read_text(encoding="utf-8"))
ANALISE = saida.ler_analise(
    json.loads((PAR_DA_CPFL / "gabarito.json").read_text(encoding="utf-8"))["analise"]
)
FUNDOS = gr.Grafico(
    tipo="linha_no_tempo",
    tabela="ofertas_e_fundos.fundos_por_mes",
    eixo="Mês",
    colunas=("Fundos",),
    titulo="Fundos com a ação, mês a mês",
    parte="quem_manda",
    paragrafo=0,
    por_que=saida.Frase(
        "A linha mostra os fundos.", ("ofertas_e_fundos.fundos_por_mes.0",)
    ),
)
DESTAQUE = gr.Destaque(
    "resultado",
    "o_que_os_numeros_mostram",
    saida.Frase("A cascata mostra os passos.", ("resultado.cascata.0",)),
)
ESCOLHA = gr.Escolha((FUNDOS,), (DESTAQUE,))


def test_guia_traz_todo_o_cardapio_e_nenhuma_marca_sobrando():
    for tipo in gr.CARDAPIO:
        assert f"`{tipo}`" in pg.GUIA
    assert "{{" not in pg.GUIA


def test_guia_apresenta_as_series_e_as_secoes_sem_destaque_da_porta1():
    """O modelo lê as mesmas listas que a porta 1 confere: a seção das séries e as que não viram
    destaque."""
    assert f"`{series.SECAO}`" in pg.GUIA
    for secao in p1g.SECOES_SEM_DESTAQUE:
        assert f"`{secao}`" in pg.GUIA


def test_pedido_leva_a_ficha_as_tabelas_e_os_paragrafos_com_rotulo():
    params = pg.pedido(ENTRADA, ANALISE, pe.SONNET)
    conteudo = params["messages"][0]["content"]
    assert "<ficha>" in conteudo
    assert (
        "ofertas_e_fundos.fundos_por_mes (24 linhas): Mês [número em 0, data em 24]"
        in conteudo
    )
    assert "[quem_manda.0] (fato)" in conteudo
    assert params["system"][0]["cache_control"] == {"type": "ephemeral"}
    partes = params["output_config"]["format"]["schema"]["properties"]["graficos"][
        "items"
    ]
    assert partes["properties"]["parte"]["enum"] == list(saida.PARTES)


def test_pedido_do_setor_usa_as_partes_do_setor():
    entrada = json.loads((PAR_DO_SETOR / "entrada.json").read_text(encoding="utf-8"))
    analise = saida.ler_analise(
        json.loads((PAR_DO_SETOR / "gabarito.json").read_text(encoding="utf-8"))[
            "analise"
        ],
        saida.PARTES_DO_SETOR,
    )
    esquema = pg.pedido(entrada, analise, pe.SONNET)["output_config"]["format"][
        "schema"
    ]
    destaque = esquema["properties"]["destaques"]["items"]["properties"]["parte"]
    assert destaque["enum"] == list(saida.PARTES_DO_SETOR)


def test_modelo_sem_preco_e_recusado():
    with pytest.raises(ValueError, match="sem preço"):
        pg.pedido(ENTRADA, ANALISE, "claude-de-mentira")


def test_resposta_cortada_e_invalida():
    with pytest.raises(saida.RespostaInvalidaError):
        pg.ler_resposta("max_tokens", json.dumps(ESCOLHA.como_dict()))
    assert pg.ler_resposta("end_turn", json.dumps(ESCOLHA.como_dict())) == ESCOLHA


def test_porta2_mostra_os_pontos_e_o_paragrafo_sem_dizer_quem_escolheu():
    params = p2g.pedido(ESCOLHA, ENTRADA, ANALISE, pe.OPUS)
    conteudo = params["messages"][0]["content"]
    assert "[grafico.0] linha_no_tempo" in conteudo
    assert "abr/2024: Fundos 436" in conteudo
    assert "[destaque.0] a seção resultado" in conteudo
    assert "sonnet" not in conteudo.lower() and "<ficha>" not in conteudo


def _veredito(itens: list[dict], stop="end_turn") -> p2g.Veredito:
    return p2g.ler_veredito(stop, json.dumps({"itens": itens}), ESCOLHA)


def test_porta2_aprova_so_o_que_mostra():
    veredito = _veredito(
        [{"item": "grafico.0", "veredito": p2g.MOSTRA, "motivo": ""},
         {"item": "destaque.0", "veredito": p2g.ENGANA, "motivo": "não soma"}]
    )  # fmt: skip
    assert veredito.reprovados == frozenset({"destaque.0"})


def test_porta2_item_sem_veredito_reprova():
    veredito = _veredito([{"item": "grafico.0", "veredito": p2g.MOSTRA, "motivo": ""}])
    assert veredito.reprovados == frozenset({"destaque.0"})


@pytest.mark.parametrize(
    ("stop", "texto"), [("max_tokens", "{}"), ("end_turn", "não é json")]
)
def test_porta2_fora_do_formato_reprova_tudo(stop, texto):
    veredito = p2g.ler_veredito(stop, texto, ESCOLHA)
    assert veredito.reprovados == frozenset({"grafico.0", "destaque.0"})
    assert veredito.motivo
