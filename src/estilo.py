"""CSS do TickerLab: só o que o tema oficial do Streamlit (`.streamlit/config.toml`) não cobre.

As cores vêm de `src/marca.py` (manual de identidade v1, 13/10/2026), nos dois temas do app (claro e
escuro). A fonte é carregada pelo tema,
do nosso próprio servidor: aqui não há `@import` do Google Fonts (mandaria o IP de quem visita).
"""

from src import marca

# a lupa do Material ("search"), como máscara: a cor vem do CSS (cinza; azul ao passar o mouse)
LUPA = (
    (
        "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'>"
        "<path d='M15.5 14h-.79l-.28-.27A6.47 6.47 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 "
        "3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 "
        "5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z'/></svg>"
    )
    .replace("<", "%3C")
    .replace(">", "%3E")
)  # sem < e > crus dentro do <style>


class _CorDosDoisTemas:
    """`COR.texto` vira `light-dark(<claro>, <escuro>)`: o .stApp declara `color-scheme` pelo tema
    ativo do Streamlit, e o navegador escolhe a cor sozinho, sem depender do Python saber o tema
    (o `st.context.theme` pode vir errado na primeira execução da sessão)."""

    def __getattr__(self, papel: str) -> str:
        clara = getattr(marca.PALETA_CLARA, papel)
        escura = getattr(marca.PALETA_ESCURA, papel)
        return f"light-dark({clara}, {escura})"


COR = _CorDosDoisTemas()

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
    border-color: {COR.linha};
}}

/* Métricas como cartões na superfície intermediária */
[data-testid="stMetric"] {{
    background: {COR.superficie};
    border: 1px solid {COR.linha};
    border-radius: 12px;
    padding: 0.85rem 1rem;
    min-height: 6.2rem;
}}
[data-testid="stMetricValue"] {{
    font-size: 1.6rem;
    letter-spacing: -0.02em;
}}
[data-testid="stMetricLabel"] {{
    color: {COR.apagado};
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
    background: {COR.destaque};
    border-color: {COR.linha_forte};
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
    border-bottom: 1px solid {COR.linha};
}}
.stTabs [data-baseweb="tab"] {{
    height: 2.75rem;
    padding: 0 1rem;
    font-weight: 600;
}}
.stTabs [aria-selected="true"] {{
    color: {COR.azul_texto};
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
    background: {COR.superficie};
}}

/* Legendas mais claras */
[data-testid="stCaptionContainer"] {{
    color: {COR.apagado};
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
    color: {COR.azul_texto};
}}

/* "Olho": o grupo da página, acima do título */
.tl-olho {{
    margin: 0.5rem 0 -0.4rem 0;
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: {COR.azul_texto};
}}

/* Código de ativo em fonte monoespaçada, como numa tela de cotações */
.tl-ticker {{
    font-family: '{marca.FONTE_MONO}', monospace;
    font-weight: 600;
    letter-spacing: 0.02em;
}}
.tl-alta {{ color: {COR.alta}; }}
.tl-queda {{ color: {COR.queda}; }}
.tl-apagado {{ color: {COR.apagado}; }}

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
    color: {COR.apagado};
    font-size: 0.92rem;
}}
.tl-principio b {{
    display: block;
    color: {COR.texto};
}}

/* TickerLab Trade: o estado da pesquisa e as fases */
.tl-estado {{
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.82rem;
    font-weight: 700;
    color: {COR.atencao};
}}
.tl-estado::before {{
    content: "";
    width: 0.5rem;
    height: 0.5rem;
    border-radius: 50%;
    background: {COR.atencao};
}}
.tl-fases {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 0.5rem;
    margin: 0.5rem 0 1rem 0;
}}
.tl-fase {{
    background: {COR.superficie};
    border: 1px solid {COR.linha};
    border-radius: 12px;
    padding: 0.6rem 0.8rem;
    font-size: 0.88rem;
}}
.tl-fase b {{
    display: block;
    font-family: '{marca.FONTE_MONO}', monospace;
    font-size: 0.8rem;
    color: {COR.apagado};
}}
.tl-fase.feita b {{ color: {COR.alta}; }}
.tl-fase.agora {{ border-color: {COR.atencao}; }}
.tl-fase.agora b {{ color: {COR.atencao}; }}

/* Rodapé */
.tl-rodape {{
    color: {COR.apagado};
    font-size: 0.82rem;
}}
.tl-rodape b {{
    color: {COR.texto};
    font-weight: 800;
}}
.tl-rodape b span {{
    color: {COR.azul_texto};
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
    background: {COR.destaque};
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
    outline: 2px solid {COR.azul_texto} !important;
    outline-offset: 2px;
}}

/* metadados curtos */
.tl-sutil {{ color: {COR.sutil}; font-size: 0.82rem; }}

/* busca de ativos: lupa no lugar da seta (é um campo de busca, não uma lista para abrir) */
.st-key-ticker [aria-label="Open"] svg,
.st-key-ativo_do_inicio [aria-label="Open"] svg {{
    display: none;
}}
.st-key-ticker [aria-label="Open"]::before,
.st-key-ativo_do_inicio [aria-label="Open"]::before {{
    content: "";
    display: block;
    width: 1.15rem;
    height: 1.15rem;
    background-color: {COR.apagado};
    -webkit-mask: url("{LUPA}") center / contain no-repeat;
    mask: url("{LUPA}") center / contain no-repeat;
}}
.st-key-ticker [aria-label="Open"]:hover::before,
.st-key-ativo_do_inicio [aria-label="Open"]:hover::before {{
    background-color: {COR.azul_texto};
}}

/* Report Studio: as páginas da prévia parecem folhas (sombra e cantos leves) */
.st-key-tl-previa img {{
    border-radius: 6px;
    border: 1px solid {COR.linha_forte};
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
    animation: tl-entrar 220ms ease-out both;
}}
/* barra de ações presa ao pé da tela enquanto a pessoa configura (Salvar · Gerar) */
.st-key-tl-barra-relatorio {{
    position: sticky;
    bottom: 0;
    z-index: 5;
    padding: 0.6rem 0.25rem;
    background: {COR.fundo};
    border-top: 1px solid {COR.linha};
}}

/* menus do topo e listas de escolha surgem do gatilho (blueprint 04). Anima o conteúdo, não a
   caixa: a caixa se posiciona com transform, e animá-la tiraria o menu do lugar. (Os expansores,
   como "Opções avançadas", o próprio Streamlit já anima.) */
[data-testid="stTopNavPopoverBody"] > *, [data-baseweb="popover"] > div {{
    transform-origin: top center;
    animation: tl-surgir 180ms ease-out both;
}}
@keyframes tl-surgir {{
    from {{ opacity: 0; transform: scale(0.98) translateY(-4px); }}
    to {{ opacity: 1; transform: none; }}
}}

/* abas: o traço azul desliza até a aba nova e o conteúdo entra suave (blueprint 05) */
.stTabs [data-baseweb="tab-highlight"] {{
    transition: transform 220ms ease, width 220ms ease;
}}
.stTabs [data-baseweb="tab-panel"] {{
    animation: tl-entrar 200ms ease-out both;
}}

/* campos: a borda e o brilho do foco chegam suaves (blueprint 07) */
[data-baseweb="input"], [data-baseweb="select"] > div, [data-baseweb="textarea"] {{
    transition: border-color 160ms ease, box-shadow 160ms ease;
}}

@media (prefers-reduced-motion: reduce) {{
    *, *::before, *::after {{
        transition: none !important;
        animation: none !important;
    }}
}}
"""
