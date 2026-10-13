"""O catálogo de módulos (src/modulos.py): só diz "disponível" o que existe no app."""

from src import modulos
from src.paginas import PAGINAS


def test_toda_funcionalidade_disponivel_aponta_para_uma_pagina_do_app():
    urls = {p.url for p in PAGINAS}
    for modulo in modulos.MODULOS:
        for f in modulo.funcionalidades:
            if f.disponivel:
                assert f.pagina_do_app in urls, (modulo.nome, f.nome)


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
    """Ferramentas (as calculadoras) ainda é ideia futura; do Mercado, as Cotações também."""
    assert modulos.POR_CHAVE["ferramentas"].disponiveis == 0
    disponiveis = [
        f.nome for f in modulos.POR_CHAVE["mercado"].funcionalidades if f.disponivel
    ]
    assert disponiveis == ["Juros e inflação", "Qualidade dos dados"]
    assert not _funcionalidade("carteira", "Dividendos e custo médio").disponivel


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
