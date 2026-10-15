"""O catálogo de módulos (src/modulos.py): só diz "disponível" o que existe no app ou no site."""

from pathlib import Path

import pytest

from src import modulos
from src.paginas import PAGINAS

SITE = Path(__file__).resolve().parents[1] / "site"


def test_toda_funcionalidade_disponivel_aponta_para_uma_pagina_que_existe():
    urls = {p.url for p in PAGINAS}
    for modulo in modulos.MODULOS:
        for f in modulo.funcionalidades:
            if f.pagina_do_site is not None:
                assert (SITE / f.pagina_do_site).is_file(), (modulo.nome, f.nome)
                assert f.pagina_do_app is None, (modulo.nome, f.nome)  # um lugar só
            elif f.disponivel:
                assert f.pagina_do_app in urls, (modulo.nome, f.nome)


@pytest.mark.parametrize(
    ("nome", "pagina"),
    [
        ("Juros simples e compostos", "calculadora-de-juros-compostos.html"),
        ("Aportes e metas", "calculadora-de-aportes-e-metas.html"),
        ("Custo das taxas e da queda", "custo-das-taxas-e-da-queda.html"),
        ("Viver de renda", "calculadora-viver-de-renda.html"),
        ("Sorte em série", "sorte-em-serie.html"),
        ("Imposto sobre ações (DARF)", "calculadora-de-darf.html"),
        ("Conversor de moedas", "conversor-de-moedas.html"),
        ("Renda fixa com IR", "calculadora-de-renda-fixa.html"),
        ("Juro real e taxas", "calculadora-de-juro-real.html"),
        ("Correção pela inflação", "calculadora-de-correcao-pela-inflacao.html"),
        ("Preço médio", "calculadora-de-preco-medio.html"),
        ("Fundo ou CDB", "fundo-ou-cdb.html"),
        ("Financiamento SAC ou Price", "simulador-de-financiamento.html"),
        ("Quanto daria? Foi sorte?", "quanto-daria.html"),
    ],
)
def test_calculadoras_levam_as_paginas_do_site(nome, pagina):
    f = _funcionalidade("ferramentas", nome)
    assert f.disponivel
    assert f.pagina_do_site == pagina


def test_as_contagens_batem_com_as_funcionalidades():
    for modulo in modulos.MODULOS:
        assert modulo.disponiveis + modulo.em_breve == len(modulo.funcionalidades)
        assert modulo.funcionalidades, modulo.nome


def _funcionalidade(chave_do_modulo, nome):
    (f,) = [
        f for f in modulos.POR_CHAVE[chave_do_modulo].funcionalidades if f.nome == nome
    ]
    return f


def test_o_que_ainda_nao_existe_nao_diz_que_existe():
    """Do Mercado, as Cotações ainda são ideia futura; do Research, o Calendário."""
    disponiveis = [
        f.nome for f in modulos.POR_CHAVE["mercado"].funcionalidades if f.disponivel
    ]
    assert disponiveis == ["Juros e inflação", "Qualidade dos dados"]
    research = [
        f.nome for f in modulos.POR_CHAVE["research"].funcionalidades if not f.disponivel
    ]
    assert research == ["Calendário"]


def test_juros_e_inflacao_e_linha_do_tempo_levam_as_paginas_da_onda_2():
    assert (
        _funcionalidade("mercado", "Juros e inflação").pagina_do_app
        == "juros-e-inflacao"
    )
    linha = _funcionalidade("research", "Linha do tempo")
    assert linha.pagina_do_app == "linha-do-tempo"
    assert linha.ticker == modulos.EXEMPLO  # a página precisa de um ativo no topo


def test_cuidar_da_carteira_leva_a_carteira_da_b3_e_nao_a_de_estrategias():
    """A página "carteira" é a Carteira de Estratégias (backtest); a da planilha é "carteira-b3"."""
    da_planilha = (
        "Importar a planilha da B3",
        "Concentração e número efetivo",
        "A carteira no passado",
        "Raio-X",
        "Rebalanceamento",
        "Dividendos e custo médio",
    )
    for nome in da_planilha:
        assert _funcionalidade("carteira", nome).pagina_do_app == "carteira-b3", nome
    for modulo in modulos.MODULOS:
        for f in modulo.funcionalidades:
            assert f.pagina_do_app != "carteira", (modulo.nome, f.nome)


def test_comparacoes_em_pdf_levam_ao_report_studio():
    """O Report Studio já gera o relatório de comparação (até 5 ativos)."""
    assert (
        _funcionalidade("relatorios", "Comparações em PDF").pagina_do_app == "relatorio"
    )


def test_qualidade_dos_dados_leva_a_uma_acao_da_b3_nos_fundamentos():
    """O selo "em conferência" aparece na tela Fundamentos, e só para documentos da CVM."""
    f = _funcionalidade("mercado", "Qualidade dos dados")
    assert f.pagina_do_app == "fundamentos"
    assert f.ticker is not None and f.ticker.endswith(".SA")


def test_chaves_unicas_para_as_ancoras_da_pagina_produto():
    chaves = [m.chave for m in modulos.MODULOS]
    assert len(chaves) == len(set(chaves))


def test_compartilhamento_seguro_disponivel_na_biblioteca():
    """Onda 4: o link da ficha (backtest) e do PDF (biblioteca do Report Studio)."""
    f = _funcionalidade("relatorios", "Compartilhamento seguro")
    assert f.disponivel and f.pagina_do_app == "relatorio"
