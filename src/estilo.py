"""CSS do TickerLab: só o que o tema oficial do Streamlit (`.streamlit/config.toml`) não cobre.

As cores vêm de `src/marca.py` (identidade aprovada em 11/10/2026). A fonte é carregada pelo tema,
do nosso próprio servidor: aqui não há `@import` do Google Fonts (mandaria o IP de quem visita).
"""

from src import marca

CSS_DO_APP = f"""
/* Largura e respiro da página */
.block-container, [data-testid="stMainBlockContainer"] {{
    max-width: 1240px;
    padding-top: 5rem;  /* o menu do topo é fixo: com menos, o conteúdo fica embaixo dele */
    padding-bottom: 3rem;
}}

/* Números alinhados (algarismos de largura fixa) em métricas e tabelas */
[data-testid="stMetricValue"], [data-testid="stMetricDelta"], [data-testid="stDataFrame"],
[data-testid="stTable"], .tl-num {{
    font-variant-numeric: tabular-nums;
}}

/* Títulos: mais justos, com quebra equilibrada */
h1, h2, h3 {{
    letter-spacing: -0.02em;
    text-wrap: balance;
}}
h2, h3 {{
    margin-top: 1.5rem;
}}

/* Linhas divisórias discretas */
hr {{
    margin: 2rem 0 1.25rem 0;
    border-color: {marca.LINHA};
}}

/* Métricas como cartões na superfície intermediária */
[data-testid="stMetric"] {{
    background: {marca.SUPERFICIE};
    border: 1px solid {marca.LINHA};
    border-radius: 12px;
    padding: 0.85rem 1rem;
    min-height: 6.2rem;
}}
[data-testid="stMetricValue"] {{
    font-size: 1.6rem;
    letter-spacing: -0.02em;
}}
[data-testid="stMetricLabel"] {{
    color: {marca.TEXTO_APAGADO};
}}
/* rótulos longos quebram a linha em vez de virar "Maior queda (drawdo..." */
[data-testid="stMetricLabel"] *, [data-testid="stMetricLabel"] p {{
    white-space: normal !important;
    overflow: visible !important;
    text-overflow: clip !important;
    line-height: 1.25;
}}
/* o número principal da página (o primeiro cartão de .tl-heroi) fica maior e mais claro */
.st-key-tl-numero-principal [data-testid="stMetric"] {{
    background: {marca.DESTAQUE};
    border-color: {marca.LINHA_FORTE};
}}
.st-key-tl-numero-principal [data-testid="stMetricValue"] {{
    font-size: 2.2rem;
}}

/* Espaço entre colunas e linhas de cartões */
[data-testid="stHorizontalBlock"] {{
    gap: 0.75rem;
}}

/* Abas: a ativa em azul */
.stTabs [data-baseweb="tab-list"] {{
    gap: 0.25rem;
    border-bottom: 1px solid {marca.LINHA};
}}
.stTabs [data-baseweb="tab"] {{
    height: 2.75rem;
    padding: 0 1rem;
    font-weight: 600;
}}
.stTabs [aria-selected="true"] {{
    color: {marca.AZUL_TEXTO};
}}
.stTabs [data-baseweb="tab-highlight"] {{
    background-color: {marca.AZUL};
    height: 2px;
}}
.stTabs [data-baseweb="tab-panel"] {{
    padding-top: 1.25rem;
}}

/* Caixas com borda (controles, cartões): superfície intermediária */
[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]) {{
    background: {marca.SUPERFICIE};
}}

/* Legendas mais claras */
[data-testid="stCaptionContainer"] {{
    color: {marca.TEXTO_APAGADO};
}}

/* --- peças da marca ------------------------------------------------------------------- */

/* Nome no topo: "Ticker" + "Lab" em azul, com o símbolo */
.tl-marca {{
    display: flex;
    align-items: center;
    gap: 0.6rem;
    font-size: 1.35rem;
    font-weight: 800;
    letter-spacing: -0.03em;
    line-height: 1;
}}
.tl-marca svg {{
    width: 28px;
    height: 28px;
}}
.tl-marca span {{
    color: {marca.AZUL_TEXTO};
}}

/* "Olho": o grupo da página, acima do título */
.tl-olho {{
    margin: 0.5rem 0 -0.4rem 0;
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: {marca.AZUL_TEXTO};
}}

/* Código de ativo em fonte monoespaçada, como numa tela de cotações */
.tl-ticker {{
    font-family: '{marca.FONTE_MONO}', monospace;
    font-weight: 600;
    letter-spacing: 0.02em;
}}
.tl-alta {{ color: {marca.ALTA}; }}
.tl-queda {{ color: {marca.QUEDA}; }}
.tl-apagado {{ color: {marca.TEXTO_APAGADO}; }}

/* Frase de abertura da página inicial e da tela de entrada */
.tl-hero {{
    margin: 0.5rem 0 0.75rem 0;
    font-size: clamp(2rem, 4.2vw, 3rem);
    font-weight: 800;
    letter-spacing: -0.035em;
    line-height: 1.05;
    text-wrap: balance;
}}

/* Princípios da página inicial: um traço azul à esquerda */
.tl-principio {{
    border-left: 2px solid {marca.AZUL};
    padding: 0.1rem 0 0.1rem 0.8rem;
    color: {marca.TEXTO_APAGADO};
    font-size: 0.92rem;
}}
.tl-principio b {{
    display: block;
    color: {marca.TEXTO};
}}

/* TickerLab Trade: o estado da pesquisa e as fases */
.tl-estado {{
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.82rem;
    font-weight: 700;
    color: {marca.ATENCAO};
}}
.tl-estado::before {{
    content: "";
    width: 0.5rem;
    height: 0.5rem;
    border-radius: 50%;
    background: {marca.ATENCAO};
}}
.tl-fases {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 0.5rem;
    margin: 0.5rem 0 1rem 0;
}}
.tl-fase {{
    background: {marca.SUPERFICIE};
    border: 1px solid {marca.LINHA};
    border-radius: 12px;
    padding: 0.6rem 0.8rem;
    font-size: 0.88rem;
}}
.tl-fase b {{
    display: block;
    font-family: '{marca.FONTE_MONO}', monospace;
    font-size: 0.8rem;
    color: {marca.TEXTO_APAGADO};
}}
.tl-fase.feita b {{ color: {marca.ALTA}; }}
.tl-fase.agora {{ border-color: {marca.ATENCAO}; }}
.tl-fase.agora b {{ color: {marca.ATENCAO}; }}

/* Rodapé */
.tl-rodape {{
    color: {marca.TEXTO_APAGADO};
    font-size: 0.82rem;
}}
.tl-rodape b {{
    color: {marca.TEXTO};
    font-weight: 800;
}}
.tl-rodape b span {{
    color: {marca.AZUL_TEXTO};
}}

/* Links de página nos cartões */
[data-testid="stPageLink"] a {{
    font-weight: 700;
}}

/* --- microanimações (blueprint, seção 09): curtas, com função, nunca contínuas -------- */

/* a página aparece uma vez, sem pular */
[data-testid="stMainBlockContainer"] {{
    animation: tl-entrar 260ms ease-out both;
}}
@keyframes tl-entrar {{
    from {{ opacity: 0; transform: translateY(8px); }}
    to {{ opacity: 1; transform: none; }}
}}

/* cartões clicáveis: borda azul e sobem 2 px */
.tl-cartao [data-testid="stVerticalBlockBorderWrapper"],
[class*="st-key-tl-cartao"] {{
    transition: border-color 180ms ease, transform 180ms ease, background 180ms ease;
}}
[class*="st-key-tl-cartao"]:hover {{
    border-color: {marca.AZUL} !important;
    transform: translateY(-2px);
    background: {marca.DESTAQUE};
}}

/* botões: afundam um pouco ao clicar */
button {{
    transition: transform 120ms ease, background 150ms ease, border-color 150ms ease;
}}
button:active:not(:disabled) {{
    transform: scale(0.98);
}}

/* foco visível para quem usa teclado (WCAG) */
button:focus-visible, a:focus-visible, input:focus-visible, textarea:focus-visible,
[role="tab"]:focus-visible, [role="option"]:focus-visible {{
    outline: 2px solid {marca.AZUL_TEXTO} !important;
    outline-offset: 2px;
}}

/* metadados curtos */
.tl-sutil {{ color: {marca.TEXTO_SUTIL}; font-size: 0.82rem; }}

/* Report Studio: as páginas da prévia parecem folhas (sombra e cantos leves) */
.st-key-tl-previa img {{
    border-radius: 6px;
    border: 1px solid {marca.LINHA_FORTE};
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
    animation: tl-entrar 220ms ease-out both;
}}
/* barra de ações presa ao pé da tela enquanto a pessoa configura (Salvar · Gerar) */
.st-key-tl-barra-relatorio {{
    position: sticky;
    bottom: 0;
    z-index: 5;
    padding: 0.6rem 0.25rem;
    background: {marca.FUNDO};
    border-top: 1px solid {marca.LINHA};
}}

@media (prefers-reduced-motion: reduce) {{
    * {{ transition: none !important; animation: none !important; }}
}}
"""
