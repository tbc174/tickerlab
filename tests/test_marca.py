"""A identidade visual do TickerLab não se desfaz sem ninguém perceber (aprovada em 11/10/2026)."""

from pathlib import Path

import tomllib
from streamlit.testing.v1 import AppTest

from src import estilo, graficos, marca, trade
from tests.ajudantes_da_conta import ir_para

RAIZ = Path(__file__).resolve().parent.parent
TEMA = tomllib.loads((RAIZ / ".streamlit" / "config.toml").read_text(encoding="utf-8"))


def test_o_tema_do_streamlit_usa_as_cores_da_marca():
    tema = TEMA["theme"]
    assert tema["base"] == "dark"
    assert tema["primaryColor"] == marca.AZUL
    assert tema["backgroundColor"] == marca.FUNDO
    assert tema["secondaryBackgroundColor"] == marca.DESTAQUE
    assert tema["textColor"] == marca.TEXTO
    assert tema["linkColor"] == marca.AZUL_TEXTO
    assert tema["greenColor"] == marca.ALTA and tema["redColor"] == marca.QUEDA
    assert tuple(tema["chartCategoricalColors"]) == marca.SERIES


def test_as_fontes_vem_do_proprio_site_e_nao_do_google():
    """Carregar fonte do Google mandaria o IP de quem visita a terceiros (LGPD)."""
    assert "googleapis" not in estilo.CSS_DO_APP
    assert "googleapis" not in (RAIZ / ".streamlit" / "config.toml").read_text(
        encoding="utf-8"
    )
    assert TEMA["server"]["enableStaticServing"] is True
    for face in TEMA["theme"]["fontFaces"]:
        arquivo = RAIZ / face["url"].removeprefix("app/")
        assert arquivo.exists(), arquivo
    for licenca in ("OFL-Manrope.txt", "OFL-JetBrainsMono.txt"):
        assert (marca.PASTA_ESTATICA / "fontes" / licenca).exists()


def test_os_arquivos_do_simbolo_existem_e_batem_com_o_desenho():
    assert (
        marca.ARQUIVO_DO_SIMBOLO.read_text(encoding="utf-8").strip()
        == marca.simbolo_svg()
    )
    assert marca.ARQUIVO_DO_ICONE.exists() and marca.ARQUIVO_DA_ASSINATURA.exists()


def test_a_imagem_docker_leva_a_pasta_static():
    assert "COPY static ./static" in (RAIZ / "Dockerfile").read_text(encoding="utf-8")


def test_os_graficos_usam_o_tema_da_marca():
    figura = graficos.go.Figure()
    graficos._estilo_base(figura, None, 300)
    assert figura.layout.template.layout.colorway == marca.SERIES
    assert marca.FONTE in figura.layout.template.layout.font.family


def test_seta_acompanha_alta_e_queda():
    assert (marca.seta(0.01), marca.seta(-0.01), marca.seta(0)) == ("▲", "▼", "■")


def test_tickerlab_trade_mostra_a_fase_os_downloads_e_o_aviso():
    app = AppTest.from_file("../app.py", default_timeout=120)
    app.session_state["usar_exemplo"] = True
    app.run()
    ir_para(app, "trade")
    assert not app.exception
    texto = " ".join(m.value for m in app.markdown)
    assert f"fase {trade.fase_atual().codigo}" in texto
    for f in trade.FASES:
        assert f.nome in texto
    botoes = [b for b in app.button if b.key and b.key.startswith("download_")]
    assert len(botoes) == len(trade.DOWNLOADS)
    assert all(b.disabled for b in botoes)  # nada para baixar antes do fim do projeto
    assert (
        "não é recomendação" in app.warning[0].value
        or "Nada aqui" in app.warning[0].value
    )


def test_so_uma_fase_esta_em_andamento():
    assert sum(f.estado == trade.AGORA for f in trade.FASES) == 1


def test_o_periodo_nunca_fica_sem_escolha():
    app = AppTest.from_file("../app.py", default_timeout=120)
    app.session_state["usar_exemplo"] = True
    app.run()
    ir_para(app, "visao_geral")
    periodo = app.button_group(key="periodo")  # o segmented_control
    assert periodo.value == "2y"
