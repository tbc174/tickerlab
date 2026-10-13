"""A página Pulse dentro do app: login simulado, banco de teste e a amostra da CVM."""

import io
import zipfile
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from streamlit.testing.v1 import AppTest

from src import eventos as ev
from src import pulse
from src.banco import dados_do_usuario as repo
from src.banco import eventos as repo_eventos
from src.banco import pulse as repo_pulse
from src.banco.modelo import eventos
from tests.ajudantes_da_conta import abrir_app, entrar_como, id_do_usuario, ir_para

PASTA = Path(__file__).parent / "arquivos" / "cvm"
# os preços de exemplo vão até 09/10/2026: o "agora" do teste fica fixo logo depois
AGORA = datetime(2026, 10, 9, 23, 0, tzinfo=UTC)
VISITA = datetime(2026, 10, 5, 22, 0, tzinfo=UTC)  # 19h em São Paulo
COLETA = datetime(2026, 10, 8, 10, 0, tzinfo=UTC)  # entre a visita e agora


def _zip(nome, arquivo):
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as z:
        z.writestr(nome, (PASTA / arquivo).read_bytes())
    return saida.getvalue()


def _coletar(banco, coletado_em=COLETA):
    tabela = ev.ler_ipe(_zip("ipe_cia_aberta_2026.csv", "ipe_amostra.csv"))
    tabela["publicado_em"] = date(2026, 10, 7)
    tickers = ev.ler_tickers_do_fca(
        [_zip("fca_cia_aberta_valor_mobiliario_2026.csv", "fca_vm_2026.csv")]
    )
    with banco.begin() as c:
        repo_eventos.gravar_tickers(c, tickers)
        repo_eventos.gravar_eventos(c, tabela)
        c.execute(sa.update(eventos).values(ingerido_em=coletado_em))


@pytest.fixture
def ana(banco, monkeypatch):
    """A Ana logada, com o relógio do Pulse parado em AGORA."""
    monkeypatch.setattr(pulse, "agora", lambda: AGORA)
    entrar_como(monkeypatch, "g-ana", "ana@exemplo.com")
    app = abrir_app()
    return app, id_do_usuario(banco, "g-ana")


def _visita(banco, usuario_id):
    with banco.connect() as c:
        return repo_pulse.ultima_visita(c, usuario_id)


def _textos(app):
    return " ".join(
        e.value for e in [*app.caption, *app.info, *app.markdown, *app.warning]
    )


def test_sem_login_pede_para_entrar(banco):
    app = AppTest.from_file("../app.py", default_timeout=120)
    app.run()
    ir_para(app, "pulse")
    assert not app.exception
    assert "Entre com a sua conta" in " ".join(i.value for i in app.info)


def test_sem_ativos_guardados_explica_e_marca_a_visita(banco, ana):
    app, ana_id = ana
    ir_para(app, "pulse")
    assert not app.exception and not app.error
    assert "Primeira visita" in _textos(app)
    assert "nenhum ativo guardado" in _textos(app)
    assert _visita(banco, ana_id) == AGORA


def test_mostra_acontecimentos_e_variacao_desde_a_visita(banco, ana):
    app, ana_id = ana
    with banco.begin() as c:
        repo.salvar_favoritos(c, ana_id, ["PETR4.SA"])
        repo_pulse.marcar_visita(c, ana_id, VISITA)
    _coletar(banco)
    ir_para(app, "pulse")
    assert not app.exception and not app.error
    textos = _textos(app)
    assert "Desde a sua última visita, em 05/10/2026 às 19h00." in textos
    assert "Você acompanha PETR4 em: favoritos." in textos
    variacoes = app.dataframe[0].value
    assert list(variacoes["Ativo"]) == ["PETR4"]
    assert list(variacoes["De"]) == ["05/10/2026"]
    assert _visita(banco, ana_id) == AGORA


def test_evento_coletado_antes_da_visita_nao_volta(banco, ana):
    app, ana_id = ana
    with banco.begin() as c:
        repo.salvar_favoritos(c, ana_id, ["PETR4.SA"])
        repo_pulse.marcar_visita(c, ana_id, VISITA)
    _coletar(banco, coletado_em=datetime(2026, 10, 5, 12, 0, tzinfo=UTC))
    ir_para(app, "pulse")
    assert not app.exception and not app.error
    assert "Você acompanha PETR4" not in _textos(app)
    assert "Nenhum acontecimento novo" in _textos(app)


def test_rerun_nao_zera_a_janela(banco, ana):
    app, ana_id = ana
    with banco.begin() as c:
        repo.salvar_favoritos(c, ana_id, ["PETR4.SA"])
        repo_pulse.marcar_visita(c, ana_id, VISITA)
    _coletar(banco)
    ir_para(app, "pulse")
    app.run()  # um clique qualquer na página roda o script de novo
    assert "Desde a sua última visita, em 05/10/2026 às 19h00." in _textos(app)
    assert "Você acompanha PETR4 em: favoritos." in _textos(app)


def test_erro_ao_ler_os_acontecimentos_nao_marca_a_visita(banco, ana, monkeypatch):
    app, ana_id = ana
    with banco.begin() as c:
        repo.salvar_favoritos(c, ana_id, ["PETR4.SA"])
        repo_pulse.marcar_visita(c, ana_id, VISITA)

    def falhar(*_args, **_kwargs):
        raise RuntimeError("banco fora do ar")

    monkeypatch.setattr("telas.research.pulse.eventos_dos_tickers", falhar)
    ir_para(app, "pulse")
    assert not app.exception
    assert app.warning
    assert _visita(banco, ana_id) == VISITA
