"""A tela do simulador de trava do café (linha 340): pela função e pelo menu do app."""

from datetime import date

import pandas as pd
import sqlalchemy as sa
from streamlit.testing.v1 import AppTest

from src import precos_de_referencia as precos
from src.banco import series as acervo
from src.commodities.cafe import textos_da_trava as textos
from src.commodities.cafe import trava
from tests.ajudantes_da_conta import ir_para
from tests.test_commodities_cafe_trava import CONSELHO, NEGACAO, PTAX_NO_ACERVO

MESES = pd.date_range("2018-01-01", "2026-09-01", freq="MS")


def _semear(banco) -> None:
    preco = pd.Series([3.0 + (i % 7) * 0.4 for i in range(len(MESES))], index=MESES)
    ptax = pd.Series([4.0 + (i % 5) * 0.2 for i in range(len(MESES))], index=MESES)
    with banco.begin() as conexao:
        for codigo in trava.SERIE_DO_TIPO.values():
            acervo.garantir_serie(conexao, precos.serie_do_acervo(codigo))
            acervo.gravar(conexao, codigo, preco, date(2026, 10, 5))
        acervo.garantir_serie(conexao, PTAX_NO_ACERVO)
        acervo.gravar(conexao, trava.PTAX, ptax, date(2026, 10, 1))


def _tela() -> None:
    from telas.research.simulador_de_trava import pagina_simulador_de_trava

    pagina_simulador_de_trava()


def _abrir() -> AppTest:
    return AppTest.from_function(_tela, default_timeout=60).run()


def _textos(app: AppTest) -> str:
    return " ".join(
        [m.value for m in app.markdown]
        + [c.value for c in app.caption]
        + [w.value for w in app.warning]
        + [i.value for i in app.info]
    )


def _linhas_por_tabela(banco) -> dict[str, int]:
    with banco.connect() as conexao:
        nomes = sa.inspect(conexao).get_table_names()
        return {
            n: conexao.execute(sa.text(f'SELECT COUNT(*) FROM "{n}"')).scalar_one()
            for n in nomes
        }


def test_com_precos_mostra_avisos_tabelas_e_riscos(banco):
    _semear(banco)
    app = _abrir()
    assert not app.exception
    avisos = [w.value for w in app.warning]
    assert textos.AVISO_SEM_RECOMENDACAO in avisos
    assert textos.AVISO_DIARIO in avisos
    assert len(app.dataframe) == 2
    assert [e.label for e in app.expander] == [i.nome for i in textos.INSTRUMENTOS]
    assert textos.ATRIBUICAO in _textos(app)
    assert textos.AVISO_SO_NA_MEMORIA in _textos(app)


def test_o_resumo_segue_a_ordem_fixa_dos_instrumentos(banco):
    _semear(banco)
    resumo = _abrir().dataframe[0].value
    assert list(resumo[textos.COLUNA_INSTRUMENTO]) == [
        textos.NOMES_DOS_INSTRUMENTOS[c] for c in trava.ORDEM_DOS_INSTRUMENTOS
    ]


def test_nenhum_texto_da_tela_diz_o_que_fazer(banco):
    _semear(banco)
    tela = _textos(_abrir()).replace(NEGACAO, "")
    assert CONSELHO.findall(tela) == []


def test_mudar_a_producao_nao_grava_nada_no_banco(banco):
    _semear(banco)
    antes = _linhas_por_tabela(banco)
    app = _abrir()
    app.number_input(key="trava_sacas").set_value(4_321).run()
    app.number_input(key="trava_custo").set_value(1_234.0).run()
    assert not app.exception
    assert _linhas_por_tabela(banco) == antes


def test_sem_precos_coletados_explica_e_mostra_os_riscos(banco):
    app = _abrir()
    assert not app.exception
    assert textos.SEM_PRECOS in [i.value for i in app.info]
    assert len(app.expander) == len(textos.INSTRUMENTOS)


def test_abre_pelo_menu_do_research(banco):
    _semear(banco)
    app = AppTest.from_file("../app.py", default_timeout=120)
    app.session_state["usar_exemplo"] = True
    app.run()
    app = ir_para(app, "simulador_de_trava")
    assert not app.exception
    assert textos.AVISO_SEM_RECOMENDACAO in [w.value for w in app.warning]
    assert len(app.dataframe) == 2
