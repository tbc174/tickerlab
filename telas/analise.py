"""Analisar: visão geral (as seções), risco, retorno mensal, comparar e correlação.

Saiu do `app.py` sem mudar comportamento (Master v3, Fase E; PR E5a). Regra de `telas/`: nenhum estado
mutável no módulo (um módulo importado é do processo inteiro, isto é, de todos os usuários).
"""

import pandas as pd
import streamlit as st

from src import graficos, relatorios
from src import indicadores as ind
from src import presets as research_presets
from src.comparacao import (
    ATALHOS,
    ATALHOS_PADRAO,
    MAX_ATIVOS,
    NOMES_AMIGAVEIS,
    alinhar_fechamentos,
    escolher_ativos,
    montar_tabela_comparativa,
    rebasear_para_100,
)
from src.conteudo import descrever_pior_drawdown
from src.correlacao import (
    calcular_beta,
    calcular_beta_movel,
    calcular_correlacao_nas_quedas,
    calcular_retornos,
    resumir_betas,
)
from src.dados import DadosIndisponiveisError
from src.exportacao import converter_para_csv, montar_tabela_de_precos
from src.indicadores import NOMES_DOS_MESES
from telas.comum import (
    MIN_DIAS_PARA_ANALISE,
    ajuda_do,
    avisar_parametros,
    cabecalho_da_pagina,
    carregar_contexto,
    carregar_dados,
    formatar_metrica,
    formatar_pct,
    mostrar_grafico,
    parametros_em_vigor,
)
from telas.relatorios.estudio import atalho_para_o_relatorio
from telas.tutorial import mostrar_tutorial

JANELAS_VOLATILIDADE = [20, 60, 120]  # dias


JANELAS_MEDIAS = [20, 50, 200]  # dias


PERIODOS_DAS_VELAS = {"3 meses": 63, "6 meses": 126, "1 ano": 252, "Tudo": None}


def mostrar_metrica(coluna, rotulo, valor, termo_do_glossario):
    """Um número com o "?" que explica o termo, usando o texto do glossário."""
    coluna.metric(rotulo, valor, help=ajuda_do(termo_do_glossario))


def secao_painel_de_numeros(
    fechamento, retorno, taxa_livre_de_risco, confianca_do_var=95
):
    st.subheader("Painel de números")
    st.caption("Passe o mouse no ? de cada número para ver o que ele significa.")

    retorno_acumulado = ind.calcular_retorno_acumulado(retorno)
    drawdown = ind.calcular_drawdown(fechamento)
    data_melhor, melhor_dia = ind.encontrar_melhor_dia(retorno)
    data_pior, pior_dia = ind.encontrar_pior_dia(retorno)

    st.markdown("**Retorno e risco**")
    linha1 = st.columns([1.4, 1, 1, 1])
    with linha1[0]:  # o número principal da página, maior e mais claro
        mostrar_numero_principal(
            "Retorno total",
            formatar_pct(retorno_acumulado.iloc[-1], com_sinal=True),
            ajuda=ajuda_do("Retorno acumulado"),
        )
    mostrar_metrica(
        linha1[1],
        "Retorno anualizado",
        formatar_pct(ind.calcular_retorno_anualizado(retorno), com_sinal=True),
        "Retorno anualizado",
    )
    mostrar_metrica(
        linha1[2],
        "Volatilidade anual",
        formatar_pct(ind.calcular_volatilidade_anual(retorno)),
        "Volatilidade",
    )
    mostrar_metrica(
        linha1[3],
        "Maior queda (drawdown)",
        formatar_pct(drawdown.min()),
        "Drawdown",
    )

    st.markdown("**Consistência e dias extremos**")
    linha2 = st.columns(5)
    sharpe = ind.calcular_indice_sharpe(retorno, taxa_livre_de_risco)
    mostrar_metrica(
        linha2[0],
        "Índice de Sharpe",
        "—" if pd.isna(sharpe) else f"{sharpe:.2f}".replace(".", ","),
        "Índice de Sharpe",
    )
    mostrar_metrica(
        linha2[1],
        f"Melhor dia ({data_melhor:%d/%m/%Y})",
        formatar_pct(melhor_dia, com_sinal=True),
        "Melhor e pior dia",
    )
    mostrar_metrica(
        linha2[2],
        f"Pior dia ({data_pior:%d/%m/%Y})",
        formatar_pct(pior_dia, com_sinal=True),
        "Melhor e pior dia",
    )
    mostrar_metrica(
        linha2[3],
        "Dias de alta",
        formatar_pct(ind.calcular_percentual_dias_positivos(retorno)),
        "Dias de alta",
    )
    mostrar_metrica(
        linha2[4],
        f"Perda de um dia ruim (VaR {confianca_do_var}%)",
        formatar_pct(ind.calcular_var_historico(retorno, confianca_do_var / 100)),
        "Perda de um dia ruim (VaR)",
    )
    cvar = ind.calcular_cvar_historico(retorno, confianca_do_var / 100)
    st.caption(
        f"**Perda média nos piores dias (CVaR {confianca_do_var}%): {formatar_pct(cvar)}.** "
        "Quando o dia foi pior que o VaR, esta foi a perda média. Estimativa feita com o "
        "passado, não um limite de perda."
    )


def secao_tendencia_e_volume(dados, r):
    """ADX (força da tendência) e OBV com volume relativo, no diário ou no semanal."""
    st.subheader("Força da tendência e volume")
    semanal = r["tecnica.periodicidade"] == "semanal"
    barras = ind.para_semanal(dados) if semanal else dados
    periodo, nivel = int(r["tecnica.adx_periodo"]), int(r["tecnica.adx_tendencia"])
    janela = int(r["tecnica.volume_janela"])
    tem_ohlc = {"High", "Low"} <= set(barras.columns)
    tem_volume = "Volume" in barras.columns and (barras["Volume"].fillna(0) > 0).any()
    col_adx, col_volume = st.columns(2)
    with col_adx:
        if tem_ohlc and len(barras) > 2 * periodo:
            mostrar_grafico(
                graficos.criar_grafico_adx(ind.calcular_adx(barras, periodo), nivel)
            )
        else:
            st.info(
                "Sem máxima e mínima, ou com poucas barras, não dá para calcular o ADX."
            )
    with col_volume:
        if tem_volume:
            mostrar_grafico(
                graficos.criar_grafico_obv(
                    ind.calcular_obv(barras),
                    ind.calcular_volume_relativo(barras, janela),
                )
            )
        else:
            st.info("Este ativo não tem volume (índices e câmbio costumam não ter).")
    st.caption(
        f"Barras {'semanais' if semanal else 'diárias'} (mude em Parâmetros). ADX acima de "
        f"{nivel}: há tendência, de alta se o +DI está acima do -DI. OBV subindo: mais volume "
        f"nos dias de alta. Volume relativo: o volume do período contra a média dos {janela} "
        "anteriores. Nenhum deles é sinal de compra ou venda."
    )


def secao_preco(dados, medias_do_usuario=()):
    """`medias_do_usuario`: as janelas das médias que a pessoa escolheu em Parâmetros (já vêm
    marcadas; sem personalização, nenhuma média vem marcada, como antes)."""
    st.subheader("Preço")
    col_tipo, col_medias = st.columns([1, 2])
    tipo_do_grafico = col_tipo.radio(
        "Tipo de gráfico",
        ["Linha", "Velas"],
        horizontal=True,
        help=ajuda_do("Gráfico de velas (candlestick)"),
    )
    medias_escolhidas = col_medias.multiselect(
        "Médias móveis (dias)",
        sorted({*JANELAS_MEDIAS, *medias_do_usuario}),
        default=sorted(set(medias_do_usuario)),
        placeholder="Escolha uma ou mais médias",
        help=ajuda_do("Média móvel"),
    )
    dias_visiveis = None
    if tipo_do_grafico == "Velas":
        # com muitos dias as velas ficam finas demais; começa mostrando os últimos meses
        periodo_velas = st.radio(
            "Velas: período mostrado",
            list(PERIODOS_DAS_VELAS),
            index=1,
            horizontal=True,
            help="Cada vela é um dia. Com muitos dias elas ficam finas; use o zoom ou "
            "troque o período para ver os detalhes.",
        )
        dias_visiveis = PERIODOS_DAS_VELAS[periodo_velas]
    mostrar_grafico(
        graficos.criar_grafico_preco(
            dados,
            tipo_do_grafico.lower(),
            tuple(sorted(medias_escolhidas)),
            dias_visiveis,
        )
    )
    st.caption(
        "Dica: arraste sobre o gráfico para dar zoom numa área e clique duas vezes para "
        "voltar ao início. Os botões 1M a Tudo trocam o período e, ao passar o mouse, "
        "a barra de ferramentas tem zoom, mover e exportar como imagem."
    )


def secao_risco(fechamento, retorno, janela_do_usuario=None):
    st.subheader("Risco ao longo do tempo")
    janelas = sorted(
        {*JANELAS_VOLATILIDADE, *([janela_do_usuario] if janela_do_usuario else [])}
    )
    janela = st.radio(
        "Janela da volatilidade (dias)",
        janelas,
        index=janelas.index(janela_do_usuario) if janela_do_usuario else 0,
        horizontal=True,
        help=ajuda_do("Volatilidade móvel"),
    )
    drawdown = ind.calcular_drawdown(fechamento)
    pior_drawdown = ind.encontrar_pior_drawdown(fechamento)
    st.markdown(descrever_pior_drawdown(pior_drawdown))

    col_drawdown, col_volatilidade = st.columns(2)
    with col_drawdown:
        mostrar_grafico(graficos.criar_grafico_drawdown(drawdown, pior_drawdown))
    volatilidade_movel = ind.calcular_volatilidade_movel(retorno, janela)
    with col_volatilidade:
        if volatilidade_movel.dropna().empty:
            st.info(
                f"O período é curto demais para uma janela de {janela} dias. "
                "Escolha uma janela menor ou um período maior."
            )
        else:
            mostrar_grafico(
                graficos.criar_grafico_volatilidade(volatilidade_movel, janela)
            )


def secao_retorno_mensal(retorno):
    st.subheader("Retorno por mês e ano", help=ajuda_do("Sazonalidade"))
    retorno_mensal = ind.calcular_retorno_mensal(retorno)
    tabela_mensal = ind.montar_tabela_retornos(retorno_mensal)
    (mes_melhor, valor_melhor), (mes_pior, valor_pior) = (
        ind.encontrar_melhor_e_pior_mes(retorno_mensal)
    )

    colunas = st.columns(3)
    mostrar_metrica(
        colunas[0],
        f"Melhor mês ({NOMES_DOS_MESES[mes_melhor.month - 1]}/{mes_melhor.year})",
        formatar_pct(valor_melhor, com_sinal=True),
        "Retorno mensal",
    )
    mostrar_metrica(
        colunas[1],
        f"Pior mês ({NOMES_DOS_MESES[mes_pior.month - 1]}/{mes_pior.year})",
        formatar_pct(valor_pior, com_sinal=True),
        "Retorno mensal",
    )
    mostrar_metrica(
        colunas[2],
        "Meses de alta",
        formatar_pct(ind.calcular_percentual_dias_positivos(retorno_mensal)),
        "Retorno mensal",
    )
    st.write("")  # respiro entre os cartões e o mapa
    mostrar_grafico(graficos.criar_mapa_de_calor_mensal(tabela_mensal))
    st.caption(
        "O primeiro e o último mês do período podem estar incompletos. "
        "A última linha mostra a média de cada mês ao longo dos anos "
        "(com poucos anos de dados, isso pode ser só coincidência)."
    )


def formatar_tabela_comparativa(tabela):
    """Troca os números da tabela comparativa por textos no formato brasileiro."""
    exibicao = pd.DataFrame(index=[NOMES_AMIGAVEIS.get(t, t) for t in tabela.index])
    for coluna in ("Retorno total", "Retorno anualizado"):
        exibicao[coluna] = [formatar_pct(v, com_sinal=True) for v in tabela[coluna]]
    for coluna in ("Volatilidade anual", "Maior queda"):
        exibicao[coluna] = [formatar_pct(v) for v in tabela[coluna]]
    exibicao["Índice de Sharpe"] = [
        "—" if pd.isna(v) else f"{v:.2f}".replace(".", ",")
        for v in tabela["Índice de Sharpe"]
    ]
    return exibicao


def secao_comparar(principal, periodo, taxa_livre_de_risco):
    st.subheader("Comparar ativos", help=ajuda_do("Base 100"))
    st.caption(
        f"O ativo principal é {NOMES_AMIGAVEIS.get(principal, principal)} (troque lá em cima). "
        "Escolha com o que compará-lo ou digite outros tickers."
    )
    col_atalhos, col_extra = st.columns([3, 2])
    atalhos_escolhidos = col_atalhos.multiselect(
        "Comparar com",
        list(ATALHOS),
        default=ATALHOS_PADRAO,
        placeholder="Escolha índices ou ativos",
    )
    texto_extra = col_extra.text_input(
        "Outros tickers (separados por vírgula)", placeholder="Ex.: VALE3, AAPL"
    )

    tickers, ignorados = escolher_ativos(
        principal, [ATALHOS[nome] for nome in atalhos_escolhidos], texto_extra
    )
    if ignorados:
        st.warning(
            f"O limite é de {MAX_ATIVOS} ativos por comparação. "
            f"Ficaram de fora: {', '.join(ignorados)}."
        )
    if len(tickers) < 2:
        st.info("Escolha pelo menos um ativo para comparar.")
        return

    fechamentos, sem_dados = {}, []
    for ticker in tickers:
        try:
            fechamentos[ticker] = carregar_dados(ticker, periodo)["Close"]
        except DadosIndisponiveisError:
            sem_dados.append(ticker)
    if sem_dados:
        st.warning(
            f"Não encontrei dados para: {', '.join(sem_dados)}. "
            "Eles ficaram de fora da comparação."
        )
    if principal not in fechamentos or len(fechamentos) < 2:
        st.info("Não há ativos suficientes com dados para comparar.")
        return

    alinhado, descartados = alinhar_fechamentos(fechamentos)
    if len(alinhado) <= MIN_DIAS_PARA_ANALISE:
        st.warning(
            f"Só há {len(alinhado)} dias em comum entre esses ativos, e são necessários "
            f"mais de {MIN_DIAS_PARA_ANALISE}. Tente um período mais longo ou outros ativos."
        )
        return

    mostrar_grafico(
        graficos.criar_grafico_comparacao(
            rebasear_para_100(alinhado), principal, NOMES_AMIGAVEIS
        )
    )
    st.markdown("**Números no mesmo período**")
    st.dataframe(
        formatar_tabela_comparativa(
            montar_tabela_comparativa(alinhado, taxa_livre_de_risco)
        ),
        width="stretch",
    )
    st.caption(
        f"Comparação feita em {len(alinhado)} dias em comum. "
        f"{descartados} dias foram descartados porque algum ativo não tinha preço neles "
        "(feriados diferentes), sem preencher nem estimar nada. Por isso os números daqui podem "
        "diferir um pouco dos das outras abas, que usam todos os dias do ativo. "
        "As moedas diferentes "
        "(R\\$ e US\\$) não atrapalham, porque comparamos a variação percentual, não os "
        "preços. Para incluir o efeito do câmbio, marque a opção de converter ativos em "
        "dólar para reais, no topo."
    )


def secao_correlacao(
    principal, periodo, indice_do_usuario=None, janela_do_usuario=None
):
    st.subheader("Correlação e beta: como os ativos se mexem juntos")
    st.caption(
        "A correlação mostra se dois ativos andam juntos; o beta mostra quanto o ativo se "
        "mexe para cada 1% do índice. Tudo é calculado com os retornos diários dos dias em "
        "que todos têm preço."
    )
    c1, c2 = st.columns([1, 2])
    nomes_dos_indices = ["Ibovespa", "S&P 500"]
    preferido = next(
        (n for n in nomes_dos_indices if ATALHOS[n] == indice_do_usuario),
        nomes_dos_indices[0],
    )
    nome_do_indice = c1.selectbox(
        "Índice de referência",
        nomes_dos_indices,
        index=nomes_dos_indices.index(preferido),
        key="corr_indice",
    )
    texto = c2.text_input(
        "Outros ativos (separados por vírgula)",
        value="VALE3, ITUB4, AAPL",
        key="corr_ativos",
        help=f"O ativo principal ({principal}) entra sempre. No máximo {MAX_ATIVOS_CORRELACAO} ativos, fora o índice.",
    )
    indice = ATALHOS[nome_do_indice]
    tickers, ignorados = escolher_ativos(
        principal, [], texto, maximo=MAX_ATIVOS_CORRELACAO
    )
    tickers = [t for t in tickers if t != indice]
    if ignorados:
        st.warning(
            f"O limite é de {MAX_ATIVOS_CORRELACAO} ativos. Ficaram de fora: {', '.join(ignorados)}."
        )
    fechamentos, sem_dados = {}, []
    for ticker in [indice, *tickers]:
        try:
            fechamentos[ticker] = carregar_dados(ticker, periodo)["Close"]
        except DadosIndisponiveisError:
            sem_dados.append(ticker)
    if sem_dados:
        st.warning(
            f"Não encontrei dados para: {', '.join(sem_dados)}. Eles ficaram de fora."
        )
    if indice not in fechamentos or len(fechamentos) < 2:
        st.info("Não há ativos suficientes com dados.")
        return
    alinhado, descartados = alinhar_fechamentos(fechamentos)
    if len(alinhado) <= MIN_DIAS_PARA_ANALISE:
        st.warning(
            f"Só há {len(alinhado)} dias em comum e são necessários mais de "
            f"{MIN_DIAS_PARA_ANALISE}. Tente um período mais longo."
        )
        return
    retornos = calcular_retornos(alinhado)
    nome = lambda t: NOMES_AMIGAVEIS.get(t, t)

    st.markdown("**Correlação entre os ativos**")
    matriz = retornos.corr().rename(columns=nome, index=nome)
    mostrar_grafico(graficos.criar_mapa_de_calor_de_correlacao(matriz))
    st.caption(ajuda_do("Correlação"))

    st.markdown(f"**Beta contra o {nome_do_indice}**")
    try:
        betas = resumir_betas(retornos, indice)
    except ValueError as erro:
        st.info(str(erro))
        return
    exibicao = pd.DataFrame(index=betas.index)
    exibicao["Beta"] = [formatar_metrica("Sharpe", v) for v in betas["Beta"]]
    exibicao["Intervalo de 95%"] = [
        f"{formatar_metrica('Sharpe', lo)} a {formatar_metrica('Sharpe', hi)}"
        for lo, hi in zip(betas["Beta (mín. 95%)"], betas["Beta (máx. 95%)"])
    ]
    exibicao["Alfa anual"] = [
        formatar_pct(v, com_sinal=True) for v in betas["Alfa anual"]
    ]
    exibicao["Correlação"] = [
        formatar_metrica("Sharpe", v) for v in betas["Correlação"]
    ]
    exibicao["R²"] = [formatar_pct(v) for v in betas["R²"]]
    st.dataframe(exibicao, width="stretch")
    st.caption(
        f"{len(alinhado)} dias em comum ({descartados} descartados por feriados diferentes). "
        "Beta acima de 1 amplifica o índice; abaixo de 1 amortece. O alfa em poucos anos de "
        "dados é muito incerto: não o leia como habilidade."
    )

    st.markdown("**Um ativo de perto**")
    ativos = list(betas.index)
    escolhido = st.selectbox(
        "Ativo", ativos, index=0, key="corr_detalhe", format_func=nome
    )
    janela = st.slider(
        "Janela do beta móvel (dias)",
        60,
        252,
        min(max(int(janela_do_usuario or 126), 60), 252),
        6,
        key="corr_janela",
    )
    resultado = calcular_beta(retornos[escolhido], retornos[indice])
    erro_de_acompanhamento = ind.calcular_tracking_error(
        retornos[escolhido], retornos[indice]
    )
    razao_de_informacao = ind.calcular_information_ratio(
        retornos[escolhido], retornos[indice]
    )
    with st.container(horizontal=True):
        st.metric(
            f"Beta contra o {nome_do_indice}",
            formatar_metrica("Beta", resultado.beta),
            border=True,
        )
        st.metric(
            "Tracking error (ao ano)",
            formatar_pct(erro_de_acompanhamento),
            border=True,
            help="O quanto o ativo se descola do índice: o desvio padrão da diferença diária, "
            "anualizado. Zero: anda igual ao índice.",
        )
        st.metric(
            "Information Ratio",
            formatar_metrica("Sharpe", razao_de_informacao),
            border=True,
            help="Quanto o ativo rendeu acima do índice por unidade de tracking error. "
            "Positivo: o descolamento rendeu mais que o índice; negativo, menos.",
        )
    col_dispersao, col_movel = st.columns(2)
    with col_dispersao:
        mostrar_grafico(
            graficos.criar_grafico_dispersao_do_beta(
                retornos[escolhido],
                retornos[indice],
                resultado.beta,
                resultado.alfa_anual / ind.DIAS_POR_ANO,
            )
        )
    with col_movel:
        try:
            mostrar_grafico(
                graficos.criar_grafico_beta_movel(
                    calcular_beta_movel(retornos[escolhido], retornos[indice], janela),
                    janela,
                )
            )
        except ValueError as erro:
            st.info(str(erro))

    try:
        quedas = calcular_correlacao_nas_quedas(retornos, indice)
        linha = quedas.loc[escolhido]
        st.caption(
            f"Correlação de {nome(escolhido)} com o {nome_do_indice}: "
            f"{formatar_metrica('Sharpe', linha['Todos os dias'])} em todos os dias e "
            f"{formatar_metrica('Sharpe', linha['Piores dias do índice'])} nos 10% piores dias "
            "do índice. Cuidado ao comparar os dois números: olhar só os dias extremos do "
            "índice reduz a correlação por construção, então um valor menor aqui não prova "
            "que a diversificação funcionou nas quedas."
        )
    except ValueError as erro:
        st.caption(str(erro))


MAX_ATIVOS_CORRELACAO = 5


def mostrar_numero_principal(rotulo, valor, delta=None, ajuda=None):
    """O número mais importante da página, maior e numa superfície mais clara."""
    with st.container(key="tl-numero-principal"):
        st.metric(rotulo, valor, delta, help=ajuda)


def pagina_risco():
    cabecalho_da_pagina("risco")
    c = carregar_contexto()
    r = parametros_em_vigor(c.ticker)
    personalizou = r.origem("quant.janela_volatilidade") != research_presets.SISTEMA
    secao_risco(
        c.fechamento,
        c.retorno,
        int(r["quant.janela_volatilidade"]) if personalizou else None,
    )
    avisar_parametros(r, ("quant.janela_volatilidade",))


def pagina_retorno_mensal():
    cabecalho_da_pagina("retorno_mensal")
    c = carregar_contexto()
    secao_retorno_mensal(c.retorno)


def pagina_comparar():
    cabecalho_da_pagina("comparar")
    c = carregar_contexto()
    atalho_para_o_relatorio(relatorios.COMPARACAO)
    secao_comparar(c.ticker, c.periodo, c.taxa_livre_de_risco)


def pagina_correlacao():
    cabecalho_da_pagina("correlacao")
    c = carregar_contexto()
    r = parametros_em_vigor(c.ticker)
    secao_correlacao(
        c.ticker, c.periodo, r["quant.benchmark"], int(r["quant.janela_correlacao"])
    )
    avisar_parametros(r, ("quant.benchmark", "quant.janela_correlacao"))


def pagina_visao_geral():
    cabecalho_da_pagina("visao_geral")
    c = carregar_contexto()
    mostrar_tutorial("visao_geral", c)
    atalho_para_o_relatorio(relatorios.ATIVO)
    r = parametros_em_vigor(c.ticker)
    secao_painel_de_numeros(
        c.fechamento, c.retorno, c.taxa_livre_de_risco, int(r["quant.var_confianca"])
    )
    st.divider()
    medias = ("tecnica.media_rapida", "tecnica.media_lenta")
    personalizou_medias = any(r.origem(k) != research_presets.SISTEMA for k in medias)
    secao_preco(
        c.dados, tuple(int(r[k]) for k in medias) if personalizou_medias else ()
    )
    st.divider()
    secao_tendencia_e_volume(c.dados, r)
    avisar_parametros(
        r,
        (
            "quant.var_confianca",
            *medias,
            "tecnica.adx_periodo",
            "tecnica.adx_tendencia",
            "tecnica.volume_janela",
            "tecnica.periodicidade",
        ),
    )
    st.download_button(
        "Baixar os preços (CSV)",
        converter_para_csv(montar_tabela_de_precos(c.dados)),
        file_name=f"{c.ticker}_{c.periodo}.csv",
        mime="text/csv",
        help="Preços, volume e retorno diário, prontos para abrir no Excel (separador ponto e vírgula).",
    )
