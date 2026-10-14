"""A identidade visual do TickerLab não se desfaz sem ninguém perceber (manual de identidade v1,
13/10/2026)."""

import itertools
import math
from pathlib import Path

import pytest
import tomllib
from streamlit.testing.v1 import AppTest

from src import estilo, graficos, marca, trade
from tests.ajudantes_da_conta import ir_para

RAIZ = Path(__file__).resolve().parent.parent
TEMA = tomllib.loads((RAIZ / ".streamlit" / "config.toml").read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("secao", "paleta"),
    [("light", marca.PALETA_CLARA), ("dark", marca.PALETA_ESCURA)],
)
def test_o_tema_do_streamlit_usa_as_cores_da_marca(secao, paleta):
    """Os dois temas do app: o Streamlit só deixa trocar se os dois estiverem definidos."""
    assert "base" not in TEMA["theme"]  # sem base fixa: claro e escuro valem
    tema = TEMA["theme"][secao]
    assert tema["primaryColor"] == marca.AZUL
    assert tema["backgroundColor"] == paleta.fundo
    assert tema["secondaryBackgroundColor"] == paleta.destaque
    assert tema["textColor"] == paleta.texto
    assert tema["linkColor"] == paleta.azul_texto
    assert tema["greenColor"] == paleta.alta and tema["redColor"] == paleta.queda
    assert tuple(tema["chartCategoricalColors"]) == paleta.series


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


def test_as_cores_institucionais_sao_as_do_manual():
    assert (marca.MARINHO, marca.AZUL, marca.CLARO, marca.AZUL_CLARO) == (
        "#0a1f44",
        "#2962ff",
        "#f6f8fb",
        "#e8f0ff",
    )


def test_o_simbolo_preserva_os_dois_tracos_do_manual():
    """Os dois traçados do SVG original, sem redesenhar (manual, seção 2)."""
    svg = marca.simbolo_svg()
    assert 'd="M9 14 H69 V25 C69 32 64 35 57 35 H9 Z"' in svg
    assert 'd="M32 35 L51 26 V59 C51 64 48 67 43 70 L32 74 Z"' in svg
    assert 'viewBox="9 14 60 60"' in svg  # só a área visível, quadrada


def test_em_fundo_escuro_so_o_topo_muda_de_cor():
    claro = marca.simbolo_svg()
    escuro = marca.simbolo_svg(topo=marca.CLARO)
    assert f'fill="{marca.MARINHO}"' in claro and f'fill="{marca.CLARO}"' in escuro
    assert (
        claro.count(f'fill="{marca.AZUL}"') == escuro.count(f'fill="{marca.AZUL}"') == 1
    )


def test_a_tela_de_entrada_usa_o_simbolo_do_tema():
    from telas.conta.entrada import marca_html

    assert f'fill="{marca.CLARO}"' in marca_html(
        marca.PALETA_ESCURA
    )  # topo claro no escuro
    assert f'fill="{marca.MARINHO}"' in marca_html(
        marca.PALETA_CLARA
    )  # topo marinho no claro
    assert marca_html() == marca_html(
        marca.PALETA_ESCURA
    )  # sem informação: o de sempre


def test_a_assinatura_do_topo_existe_nos_dois_temas():
    escura = marca.arquivo_da_assinatura(marca.PALETA_ESCURA)
    clara = marca.arquivo_da_assinatura(marca.PALETA_CLARA)
    assert escura == marca.ARQUIVO_DA_ASSINATURA and clara != escura
    assert clara.exists() and escura.exists()


def test_o_icone_da_aba_se_adapta_ao_tema_do_navegador():
    svg = marca.icone_svg()
    assert "prefers-color-scheme: dark" in svg
    assert marca.MARINHO in svg and marca.CLARO in svg


def test_os_arquivos_do_simbolo_existem_e_batem_com_o_desenho():
    assert (
        marca.ARQUIVO_DO_SIMBOLO.read_text(encoding="utf-8").strip()
        == marca.icone_svg()
    )
    assert marca.ARQUIVO_DO_ICONE.exists() and marca.ARQUIVO_DA_ASSINATURA.exists()
    assert marca.ARQUIVO_DE_COMPARTILHAMENTO.exists()


def test_icones_do_app_para_instalar_no_celular():
    """PWA (ADR 0066): 192 e 512 com cantos arredondados, e a versão "maskable" (o celular recorta
    em círculo ou gota) com o símbolo dentro da zona segura, o círculo de 80% do meio."""
    from PIL import Image

    for arquivo, lado in marca.ICONES_DO_APP.items():
        imagem = Image.open(arquivo)
        assert imagem.size == (lado, lado), arquivo.name
    mascaravel = Image.open(marca.ARQUIVO_DO_ICONE_MASCARAVEL).convert("RGBA")
    lado = mascaravel.width
    # fundo marinho até a borda: nada transparente para o celular recortar
    assert all(mascaravel.getpixel((x, y))[3] == 255 for x in (0, lado - 1) for y in (0, lado - 1))
    marinho = tuple(int(marca.MARINHO[i : i + 2], 16) for i in (1, 3, 5))
    raio_seguro = 0.4 * lado
    for x in range(0, lado, 4):
        for y in range(0, lado, 4):
            if math.dist((x, y), (lado / 2, lado / 2)) > raio_seguro:
                assert mascaravel.getpixel((x, y))[:3] == marinho, (x, y)


def test_a_imagem_docker_leva_a_pasta_static():
    assert "COPY static ./static" in (RAIZ / "Dockerfile").read_text(encoding="utf-8")


def test_a_imagem_docker_troca_o_icone_padrao_do_streamlit_pelo_nosso():
    """O Streamlit manda o HTML com o ícone dele (um barco que parece uma coroa) e só troca pelo
    page_icon depois que o script roda: a cada recarga a aba mostrava a coroa."""
    dockerfile = (RAIZ / "Dockerfile").read_text(encoding="utf-8")
    troca = dockerfile.index("static/favicon.png")
    passo = dockerfile[dockerfile.rindex("RUN", 0, troca) : troca]
    assert "static/marca/icone.png" in passo
    # a pasta do Streamlit só aceita escrita do root
    assert troca < dockerfile.index("USER app")


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


def _contraste(cor: str, fundo: str) -> float:
    def luminancia(hexa: str) -> float:
        canais = [int(hexa.lstrip("#")[i : i + 2], 16) / 255 for i in (0, 2, 4)]
        lineares = [
            c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in canais
        ]
        return 0.2126 * lineares[0] + 0.7152 * lineares[1] + 0.0722 * lineares[2]

    claro, escuro = sorted((luminancia(cor), luminancia(fundo)), reverse=True)
    return (claro + 0.05) / (escuro + 0.05)


@pytest.mark.parametrize("paleta", [marca.PALETA_CLARA, marca.PALETA_ESCURA])
def test_texto_e_cores_de_significado_passam_no_contraste_aa(paleta):
    """WCAG AA (4,5:1) para texto sobre as três superfícies, nos dois temas do app."""
    for fundo in (paleta.fundo, paleta.superficie, paleta.destaque):
        for nome in (
            "texto",
            "apagado",
            "sutil",
            "azul_texto",
            "alta",
            "queda",
            "atencao",
        ):
            cor = getattr(paleta, nome)
            assert _contraste(cor, fundo) >= 4.5, (paleta.tipo, nome, cor, fundo)


def test_a_paleta_escura_e_a_do_app_de_antes():
    p = marca.PALETA_ESCURA
    assert (p.fundo, p.superficie, p.texto, p.series) == (
        marca.FUNDO,
        marca.SUPERFICIE,
        marca.TEXTO,
        marca.SERIES,
    )
    assert marca.paleta_do_tema("light") is marca.PALETA_CLARA
    assert marca.paleta_do_tema("dark") is marca.PALETA_ESCURA
    assert (
        marca.paleta_do_tema(None) is marca.PALETA_ESCURA
    )  # sem informação: o de sempre


# --- a paleta das séries dos gráficos (conferida com o validador de cores, 13/10/2026) ---


def _oklab(cor):
    """#rrggbb → (L, a, b) do OKLab (a mesma conta do validador)."""

    def linear(c):
        c /= 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (linear(int(cor[i : i + 2], 16)) for i in (1, 3, 5))
    l_ = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m_ = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s_ = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    return (
        0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
        1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
        0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_,
    )


def _distancia(cor1, cor2):
    return (
        math.dist(_oklab(cor1), _oklab(cor2)) * 100
    )  # ΔE em OKLab ×100, como o validador


@pytest.mark.parametrize(
    ("series", "faixa", "alta", "queda"),
    [
        (marca.PAPEL_SERIES, (0.43, 0.77), marca.PAPEL_ALTA, marca.PAPEL_QUEDA),
        (marca.SERIES, (0.48, 0.67), marca.ALTA, marca.QUEDA),
    ],
)
def test_series_na_faixa_do_tema_e_longe_de_alta_e_queda(series, faixa, alta, queda):
    """Luminosidade na faixa do tema (no escuro, nada claro demais) e nenhuma série parecida com o
    verde de alta ou o vermelho de queda, que têm significado (ΔE >= 12)."""
    for cor in series:
        assert faixa[0] <= _oklab(cor)[0] <= faixa[1], cor
        assert _distancia(cor, alta) >= 12, (cor, "alta")
        assert _distancia(cor, queda) >= 12, (cor, "queda")


def test_series_vizinhas_bem_diferentes():
    """Vizinhas na ordem (a ordem das linhas num gráfico) bem diferentes à vista (ΔE >= 15)."""
    for series in (marca.PAPEL_SERIES, marca.SERIES):
        for cor, vizinha in itertools.pairwise(series):
            assert _distancia(cor, vizinha) >= 15, (cor, vizinha)
