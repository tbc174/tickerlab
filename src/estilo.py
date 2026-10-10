"""Estilo visual do app (CSS). Segue a direção aprovada: preto, minimalista, azul vivo."""

COR_AZUL = "#2962ff"
COR_AZUL_CLARO = "#7aa2ff"
COR_LINHA_FINA = "rgba(255, 255, 255, 0.12)"

CSS_DO_APP = f"""
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&display=swap');

html, body, [class*="st-"], .stMarkdown, button, input, textarea, select {{
    font-family: 'Manrope', system-ui, -apple-system, 'Segoe UI', sans-serif;
}}

/* Largura e respiro da página */
.block-container, [data-testid="stMainBlockContainer"] {{
    max-width: 1280px;
    padding-top: 2.5rem;
    padding-bottom: 4rem;
}}

/* Título */
h1 {{
    font-weight: 800;
    letter-spacing: -0.02em;
    padding-bottom: 0.25rem;
}}

/* Subtítulos de seção: mais espaço em cima, menos embaixo */
h2, h3 {{
    font-weight: 700;
    letter-spacing: -0.01em;
    margin-top: 1.75rem;
    margin-bottom: 0.25rem;
}}

/* Linhas divisórias mais discretas, com espaço dos dois lados */
hr {{
    margin: 2.25rem 0 1.5rem 0;
    border-color: {COR_LINHA_FINA};
}}

/* Cartões das métricas: sem preenchimento, só uma linha fina */
[data-testid="stMetric"] {{
    background: transparent;
    border: 1px solid {COR_LINHA_FINA};
    border-radius: 14px;
    padding: 0.9rem 1.1rem;
    min-height: 6.4rem;
}}
[data-testid="stMetricValue"] {{
    font-weight: 700;
    font-size: 1.75rem;
}}
[data-testid="stMetricLabel"] {{
    opacity: 0.75;
}}
/* rótulos longos quebram a linha em vez de virar "Maior queda (drawdo..." */
[data-testid="stMetricLabel"] *, [data-testid="stMetricLabel"] p {{
    white-space: normal !important;
    overflow: visible !important;
    text-overflow: clip !important;
    line-height: 1.25;
}}

/* Espaço entre as colunas e as linhas de cartões */
[data-testid="stHorizontalBlock"] {{
    gap: 1rem;
}}

/* Abas: sem fundo, a ativa em azul */
.stTabs [data-baseweb="tab-list"] {{
    gap: 0.5rem;
    border-bottom: 1px solid {COR_LINHA_FINA};
}}
.stTabs [data-baseweb="tab"] {{
    height: 3rem;
    padding: 0 1.1rem;
    font-weight: 600;
}}
.stTabs [aria-selected="true"] {{
    color: {COR_AZUL_CLARO};
}}
.stTabs [data-baseweb="tab-highlight"] {{
    background-color: {COR_AZUL};
    height: 3px;
}}
.stTabs [data-baseweb="tab-panel"] {{
    padding-top: 1.5rem;
}}

/* Caixa de controles: cantos arredondados e linha fina */
[data-testid="stVerticalBlockBorderWrapper"] {{
    border-radius: 16px;
    border-color: {COR_LINHA_FINA};
}}

/* Legendas um pouco mais claras e com folga */
[data-testid="stCaptionContainer"] {{
    opacity: 0.7;
    margin-top: 0.25rem;
}}

/* Botões e campos em formato de pílula */
.stTextInput input, .stNumberInput input, .stSelectbox [data-baseweb="select"] > div {{
    border-radius: 999px;
}}
"""
