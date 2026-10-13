"""A página Linha do tempo dentro do app (modo local, banco de teste com a amostra da CVM)."""

import io
import zipfile
from datetime import date, timedelta
from pathlib import Path

from streamlit.testing.v1 import AppTest

from src import eventos as ev
from src import linha_do_tempo as ldt
from src.banco import eventos as repo_eventos
from tests.ajudantes_da_conta import ir_para

PASTA = Path(__file__).parent / "arquivos" / "cvm"


def _zip(nome, arquivo):
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as z:
        z.writestr(nome, (PASTA / arquivo).read_bytes())
    return saida.getvalue()


def _coletar(banco):
    """A amostra real da CVM em datas fixas dentro dos preços de exemplo (que vão até 09/10/2026):
    com datas relativas a hoje, o teste quebraria sozinho com o passar dos dias."""
    tabela = ev.ler_ipe(_zip("ipe_cia_aberta_2026.csv", "ipe_amostra.csv")).reset_index(
        drop=True
    )
    tabela["publicado_em"] = [
        date(2026, 9, 1) - timedelta(days=3 * i) for i in range(len(tabela))
    ]
    tickers = ev.ler_tickers_do_fca(
        [_zip("fca_cia_aberta_valor_mobiliario_2026.csv", "fca_vm_2026.csv")]
    )
    with banco.begin() as c:
        repo_eventos.gravar_tickers(c, tickers)
        repo_eventos.gravar_eventos(c, tabela)


def _abrir_local() -> AppTest:
    app = AppTest.from_file("../app.py", default_timeout=120)
    app.session_state["usar_exemplo"] = True
    app.run()
    return ir_para(app, "linha_do_tempo")


def test_linha_do_tempo_mostra_os_fatos_com_link(banco):
    _coletar(banco)
    app = _abrir_local()
    assert not app.exception and not app.error
    assert any(ldt.AVISO_DA_LINHA in c.value for c in app.caption)
    tabela = app.dataframe[0].value
    assert len(tabela) >= 1
    assert all(
        link.startswith("https://") for link in tabela["Documento original"] if link
    )
    assert app.get("plotly_chart")  # o gráfico com o preço e os marcos


def test_ativo_sem_acontecimentos_mostra_so_o_preco(banco):
    app = _abrir_local()
    assert not app.exception and not app.error
    assert "Nenhum acontecimento" in " ".join(i.value for i in app.info)
    assert app.get("plotly_chart")
