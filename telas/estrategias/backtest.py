"""Estratégias: teste no passado (backtest), proteções, custos e a validação.

Saiu do `app.py` sem mudar comportamento (Master v3, Fase E). Regra de `telas/`: nenhum estado
mutável no módulo (um módulo importado é do processo inteiro, isto é, de todos os usuários).
"""

import pandas as pd
import streamlit as st

from src import graficos, relatorios
from src import indicadores as ind
from src.acaso import (
    calcular_pbo,
    calcular_sharpe_deflacionado,
    resumir_monte_carlo,
    simular_monte_carlo,
    testar_contra_o_acaso,
)
from src.backtest import CUSTO_PADRAO_POR_OPERACAO, executar_backtest
from src.cdi import CDIIndisponivelError, curva_do_cdi
from src.conteudo import proteger_cifrao
from src.dados import normalizar_ticker
from src.estrategias import ESTRATEGIAS, gerar_posicao
from src.exportacao import (
    converter_para_csv,
    montar_tabela_de_curvas,
    montar_tabela_de_operacoes,
)
from src.ficha import PedidoDaFicha, texto_das_tentativas
from src.imposto import aplicar_imposto
from src.metricas import (
    calcular_intervalo_do_sharpe,
    mais_numeros,
    resumir_desempenho,
)
from src.protecoes import Protecoes, aplicar_protecoes
from src.tentativas import TETO_POR_PESSOA
from src.validacao import (
    avaliar_treino_e_teste,
    calcular_retornos_dos_candidatos,
    data_de_corte,
    executar_walk_forward,
    melhor_candidato,
    montar_candidatos,
    montar_mapa_de_sharpe,
    parametros_numericos,
    resumir_grade,
)
from telas.comum import (
    ajuda_do,
    cabecalho_da_pagina,
    carregar_contexto,
    formatar_metrica,
    formatar_pct,
    mostrar_grafico,
    obter_cdi,
)
from telas.dados_da_conta import ESPERAS_DEPOIS_DO_STOP, oferecer_salvar_simulacao
from telas.estrategias.comum import ESTRATEGIA_DE_REFERENCIA, obter_estrategias
from telas.estrategias.ficha import (
    CHAVE_DA_FICHA_PARA_SALVAR,
    calcular_ficha,
    contar_esta_tentativa,
    escolher_tolerancia,
    esquecer_a_ficha_para_salvar,
    lembrar_para_salvar,
    mostrar_ficha,
)
from telas.relatorios.estudio import atalho_para_o_relatorio


def escolher_estrategia():
    """Menu da estratégia e controles dos parâmetros, gerados a partir do registro."""
    nome = st.selectbox(
        "Estratégia",
        list(ESTRATEGIAS),
        format_func=lambda n: f"{ESTRATEGIAS[n].grupo} · {n}",
        key="backtest_estrategia",
    )
    parametros = {}
    if ESTRATEGIAS[nome].parametros:
        colunas = st.columns(min(len(ESTRATEGIAS[nome].parametros), 3))
        for posicao, p in enumerate(ESTRATEGIAS[nome].parametros):
            coluna = colunas[posicao % len(colunas)]
            chave = f"parametro_{nome}_{p.nome}"
            if p.opcoes:
                parametros[p.nome] = coluna.selectbox(
                    p.rotulo,
                    p.opcoes,
                    index=p.opcoes.index(p.padrao),
                    key=chave,
                    help=p.ajuda or None,
                )
            else:
                parametros[p.nome] = coluna.slider(
                    p.rotulo,
                    p.minimo,
                    p.maximo,
                    p.padrao,
                    p.passo,
                    key=chave,
                    help=p.ajuda or None,
                )
    return nome, parametros


def _opcao_com_valor(
    coluna, chave, rotulo, rotulo_do_valor, padrao, minimo, maximo, termo
):
    """Uma caixa para ligar a proteção e, se ligada, o campo do valor. Devolve o valor ou None."""
    if not coluna.checkbox(rotulo, key=f"liga_{chave}", help=ajuda_do(termo)):
        return None
    return coluna.number_input(
        rotulo_do_valor,
        min_value=minimo,
        max_value=maximo,
        value=padrao,
        step=0.5,
        key=f"valor_{chave}",
    )


def escolher_protecoes():
    """Controles das proteções de risco (todas desligadas por padrão)."""
    with st.expander("Proteções de risco (opcional)"):
        st.caption(
            "Uma camada extra por cima da estratégia. Depois de um stop, a estratégia só volta "
            "a comprar quando mandar sair e depois entrar de novo (um sinal novo)."
        )
        col1, col2, col3 = st.columns(3)
        stop_loss = _opcao_com_valor(
            col1,
            "stop_loss",
            "Stop-loss",
            "Sair se cair (%)",
            8.0,
            1.0,
            50.0,
            "Stop-loss",
        )
        take_profit = _opcao_com_valor(
            col2,
            "take_profit",
            "Take-profit",
            "Sair se subir (%)",
            15.0,
            1.0,
            200.0,
            "Take-profit",
        )
        stop_movel = _opcao_com_valor(
            col3,
            "stop_movel",
            "Stop móvel",
            "Sair se cair da máxima (%)",
            10.0,
            1.0,
            50.0,
            "Stop móvel",
        )
        col4, col5, col6 = st.columns(3)
        stop_atr = _opcao_com_valor(
            col4,
            "stop_atr",
            "Stop por ATR",
            "Distância (x ATR)",
            2.0,
            0.5,
            6.0,
            "Stop por ATR",
        )
        risco = None
        if stop_atr is not None:
            risco = _opcao_com_valor(
                col5,
                "risco",
                "Risco por operação",
                "Capital arriscado (%)",
                1.0,
                0.5,
                10.0,
                "Risco por operação",
            )
        alvo = _opcao_com_valor(
            col6,
            "alvo_vol",
            "Alvo de volatilidade",
            "Volatilidade anual (%)",
            15.0,
            5.0,
            50.0,
            "Alvo de volatilidade",
        )
        espera = st.selectbox(
            "Depois de um stop, voltar a comprar...",
            list(ESPERAS_DEPOIS_DO_STOP),
            key="espera_depois_do_stop",
            help="Estratégias que nunca mandam sair (como comprar e segurar) só voltam se "
            "houver uma espera.",
        )
    return Protecoes(
        stop_loss=None if stop_loss is None else stop_loss / 100,
        take_profit=None if take_profit is None else take_profit / 100,
        stop_movel=None if stop_movel is None else stop_movel / 100,
        stop_atr=stop_atr,
        risco_por_operacao=None if risco is None else risco / 100,
        alvo_de_volatilidade=None if alvo is None else alvo / 100,
        dias_de_espera=ESPERAS_DEPOIS_DO_STOP[espera],
    )


@st.cache_data(show_spinner="Testando as combinações de parâmetros...")
def calcular_candidatos(dados, nome, candidatos, custo, protecoes):
    return calcular_retornos_dos_candidatos(dados, nome, candidatos, custo, protecoes)


def _texto_dos_parametros(parametros, rotulos):
    if not parametros:
        return "nenhum (ficou em caixa)"
    return ", ".join(f"{rotulos.get(k, k)} = {v}" for k, v in parametros.items())


def _aba_treino_e_teste(
    nome,
    retorno_do_usuario,
    capital_inicial,
    retorno_de_referencia,
    taxa_livre_de_risco,
    rotulos,
    retornos,
    validos,
    sharpe,
):
    """Treino e teste: escolhe no começo do histórico e confere no fim, que a escolha não viu."""
    fracao = st.slider(
        "Parte do histórico usada para escolher (treino)",
        50,
        90,
        70,
        5,
        format="%d%%",
        key=f"validacao_fracao_{nome}",
        help=ajuda_do("Treino e teste"),
    )
    try:
        corte = data_de_corte(retornos.index, fracao / 100)
        tt = avaliar_treino_e_teste(retornos, validos, corte, taxa_livre_de_risco)
    except ValueError as erro:
        st.info(str(erro))
    else:
        teste = retorno_do_usuario.loc[retorno_do_usuario.index >= corte]
        referencia = retorno_de_referencia.loc[retorno_de_referencia.index >= corte]
        st.markdown(
            f"Treino até **{(corte - pd.Timedelta(days=1)):%d/%m/%Y}**; teste a partir de "
            f"**{corte:%d/%m/%Y}**. Melhor combinação no treino: "
            f"**{_texto_dos_parametros(tt.melhor_do_treino, rotulos)}**."
        )
        c1, c2, c3, c4 = st.columns(4)
        c1.metric(
            "Sharpe da melhor, no treino",
            formatar_metrica("Sharpe", tt.sharpe_no_treino),
            help="O número bonito: foi escolhido justamente por ser o maior.",
        )
        c2.metric(
            "Esta mesma, no teste",
            formatar_metrica("Sharpe", tt.sharpe_no_teste),
            help="O número de verdade: período que a escolha nunca viu.",
        )
        c3.metric(
            "Sua configuração, no teste",
            formatar_metrica("Sharpe", sharpe(teste)),
        )
        c4.metric(
            "Comprar e segurar, no teste",
            formatar_metrica("Sharpe", sharpe(referencia)),
        )
        if tt.sharpe_no_teste < tt.sharpe_no_treino:
            st.caption(
                "O Sharpe caiu do treino para o teste. Uma queda é normal: parte do "
                "resultado do treino foi sorte. Quanto maior a queda, mais a escolha "
                "estava ajustada ao passado."
            )
        else:
            st.caption(
                "O Sharpe subiu do treino para o teste. Isso quase sempre quer dizer que "
                "o período de teste foi mais favorável (por exemplo, uma tendência de "
                "alta), e não que a estratégia ficou melhor. Compare com comprar e segurar."
            )
        curvas = {
            "Melhor do treino": ind.curva_de_capital(tt.retorno_no_teste),
            "Sua configuração": ind.curva_de_capital(teste),
            "Comprar e segurar": ind.curva_de_capital(referencia),
        }
        mostrar_grafico(
            graficos.criar_grafico_curvas_de_capital(
                curvas, capital_inicial, destaque="Melhor do treino"
            )
        )


def _aba_walk_forward(
    nome,
    capital_inicial,
    retorno_de_referencia,
    taxa_livre_de_risco,
    rotulos,
    retornos,
    validos,
    sharpe,
):
    """Walk-forward: escolhe e confere em janelas que andam pelo histórico."""
    col_a, col_b = st.columns(2)
    dias_treino = col_a.slider(
        "Janela de treino (dias úteis)",
        126,
        1008,
        504,
        21,
        key=f"validacao_treino_{nome}",
        help=ajuda_do("Walk-forward"),
    )
    dias_teste = col_b.slider(
        "Janela de teste (dias úteis)",
        21,
        252,
        126,
        21,
        key=f"validacao_teste_{nome}",
    )
    try:
        wf = executar_walk_forward(
            retornos, validos, dias_treino, dias_teste, taxa_livre_de_risco
        )
    except ValueError as erro:
        st.info(str(erro))
    else:
        fora = wf.retorno_fora_da_amostra
        referencia = retorno_de_referencia.loc[fora.index]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric(
            "Sharpe fora da amostra",
            formatar_metrica("Sharpe", wf.sharpe_fora_da_amostra),
        )
        c2.metric(
            "Sharpe médio no treino",
            formatar_metrica("Sharpe", wf.sharpe_medio_no_treino),
        )
        c3.metric(
            "Eficiência",
            formatar_metrica("Sharpe", wf.eficiencia),
            help="Sharpe de fora dividido pelo Sharpe médio de treino. Perto de 1: o "
            "ajuste se sustentou. Perto de 0 ou negativo: era sorte.",
        )
        c4.metric(
            "Comprar e segurar, no mesmo período",
            formatar_metrica("Sharpe", sharpe(referencia)),
        )
        mostrar_grafico(
            graficos.criar_grafico_curvas_de_capital(
                {
                    "Walk-forward (só dias de teste)": ind.curva_de_capital(fora),
                    "Comprar e segurar": ind.curva_de_capital(referencia),
                },
                capital_inicial,
                destaque="Walk-forward (só dias de teste)",
            )
        )
        janelas = wf.janelas.copy()
        for coluna in ("Começo do treino", "Começo do teste", "Fim do teste"):
            janelas[coluna] = janelas[coluna].dt.strftime("%d/%m/%Y")
        janelas["Parâmetros escolhidos"] = [
            _texto_dos_parametros(p, rotulos) for p in janelas["Parâmetros escolhidos"]
        ]
        for coluna in ("Sharpe no treino", "Sharpe no teste"):
            janelas[coluna] = [formatar_metrica("Sharpe", v) for v in janelas[coluna]]
        with st.expander(f"Ver as {len(janelas)} janelas"):
            st.dataframe(janelas, width="stretch", hide_index=True)


def _aba_mapa_de_parametros(
    parametros, taxa_livre_de_risco, rotulos, livres, retornos, validos
):
    """Mapa de parâmetros: o Sharpe de cada combinação no período inteiro."""
    st.caption(
        "Sharpe de cada combinação no período inteiro. Procure uma região grande e "
        "verde, não um quadradinho isolado."
    )
    segundo = livres[1] if len(livres) > 1 else None
    mapa = montar_mapa_de_sharpe(
        retornos, validos, livres[0], segundo, taxa_livre_de_risco
    )
    mostrar_grafico(
        graficos.criar_mapa_de_calor_de_parametros(
            mapa,
            rotulos[livres[0]],
            rotulos[segundo] if segundo else None,
            escolhido=(
                parametros[livres[0]],
                parametros[segundo] if segundo else "",
            ),
        )
    )
    resumo = resumir_grade(mapa)
    if resumo is not None:
        st.caption(
            f"Mediana do Sharpe na grade: {formatar_metrica('Sharpe', resumo.mediana)}; "
            f"melhor: {formatar_metrica('Sharpe', resumo.melhor)}. "
            f"{formatar_pct(resumo.fracao_positiva)} das combinações têm Sharpe positivo. "
            "O quadrado azul marca a sua configuração atual (se ela estiver na grade)."
        )


def _aba_monte_carlo_e_acaso(
    dados, operacoes, taxa_livre_de_risco, custo, posicao_desejada
):
    """Monte Carlo das operações e o teste contra posições ao acaso."""
    st.markdown("**Monte Carlo: e se as operações tivessem vindo em outra ordem?**")
    st.caption(ajuda_do("Monte Carlo (das operações)"))
    if len(operacoes) < 5:
        st.info(
            "Com menos de 5 operações, o Monte Carlo não diz nada. Tente um período maior ou outros parâmetros."
        )
    else:
        mc = simular_monte_carlo(operacoes["retorno"])
        resumo = resumir_monte_carlo(mc)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric(
            "Retorno típico (mediana)",
            formatar_pct(resumo.retorno_mediano, com_sinal=True),
        )
        c2.metric(
            "Faixa de 90% dos casos",
            f"{formatar_pct(resumo.retorno_p5, com_sinal=True)} a "
            f"{formatar_pct(resumo.retorno_p95, com_sinal=True)}",
        )
        c3.metric("Chance de prejuízo", formatar_pct(resumo.chance_de_prejuizo))
        c4.metric(
            "Queda máxima no pior caso comum",
            formatar_pct(resumo.queda_p5),
            help="Em 95% das simulações a maior queda foi menor que esta.",
        )
        mostrar_grafico(
            graficos.criar_grafico_cone_monte_carlo(
                mc.percentis_da_curva, mc.curva_observada
            )
        )
    st.divider()
    st.markdown(
        "**Teste contra o acaso: a regra bate posições sem relação com o preço?**"
    )
    st.caption(ajuda_do("Teste contra o acaso"))
    try:
        teste = testar_contra_o_acaso(
            dados["Close"], posicao_desejada, custo, taxa_livre_de_risco
        )
    except ValueError as erro:
        st.info(str(erro))
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric("Sharpe da estratégia", formatar_metrica("Sharpe", teste.sharpe_real))
        c2.metric(
            "Sharpe mediano ao acaso",
            formatar_metrica("Sharpe", teste.sharpe_mediano_ao_acaso),
        )
        c3.metric(
            "p-valor",
            formatar_metrica("Sharpe", teste.p_valor),
            help="Fatia das versões ao acaso que fez igual ou melhor. Abaixo de 0,05 "
            "é difícil atribuir o resultado só ao acaso.",
        )
        mostrar_grafico(
            graficos.criar_histograma_do_acaso(
                teste.sharpes_ao_acaso, teste.sharpe_real
            )
        )
        if teste.p_valor >= 0.05:
            st.caption(
                "Muitas versões ao acaso fizeram igual ou melhor. Em ativos que subiram "
                "bastante, quase qualquer posição comprada ganha, e a regra não se destaca."
            )


def _aba_sorte_na_escolha(nome, taxa_livre_de_risco, rotulos, retornos, validos):
    """Sharpe deflacionado e PBO: quanto do melhor resultado pode ser sorte de escolha."""
    st.markdown("**Sharpe deflacionado: o melhor de muitas tentativas vale quanto?**")
    st.caption(ajuda_do("Sharpe deflacionado"))
    extras = st.number_input(
        "Outras combinações que você já testou antes (opcional)",
        min_value=0,
        max_value=10_000,
        value=0,
        step=10,
        key=f"validacao_extras_{nome}",
        help="Cada combinação testada em outras estratégias ou ativos também conta como "
        "uma tentativa. Quanto mais tentativas, maior o Sharpe que só a sorte já daria.",
    )
    melhor_coluna = melhor_candidato(retornos, taxa_livre_de_risco)
    try:
        dsr = calcular_sharpe_deflacionado(
            retornos[melhor_coluna], retornos, int(extras), taxa_livre_de_risco
        )
    except ValueError as erro:
        st.info(str(erro))
    else:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Tentativas contadas", f"{dsr.tentativas}")
        c2.metric(
            "Sharpe do melhor candidato",
            formatar_metrica("Sharpe", dsr.sharpe_anual),
        )
        c3.metric(
            "Sharpe que a sorte já daria",
            formatar_metrica("Sharpe", dsr.sharpe_anual_por_sorte),
        )
        c4.metric(
            "Chance de não ser sorte",
            formatar_pct(dsr.probabilidade),
            help="Probabilidade do Sharpe deflacionado. Acima de 95%: convincente.",
        )
        st.caption(
            f"Melhor candidato: {_texto_dos_parametros(validos[int(melhor_coluna)], rotulos)}. "
            "Este Sharpe usa a média dos retornos diários, por isso pode diferir um pouco "
            "do Sharpe mostrado nas outras telas."
        )
    st.divider()
    st.markdown("**PBO: escolher a melhor do treino costuma funcionar?**")
    st.caption(ajuda_do("PBO (probabilidade de overfitting)"))
    try:
        pbo = calcular_pbo(retornos)
    except ValueError as erro:
        st.info(str(erro))
    else:
        c1, c2 = st.columns(2)
        c1.metric("PBO", formatar_pct(pbo.probabilidade))
        c2.metric("Divisões treino/teste testadas", f"{pbo.combinacoes}")
        st.caption(
            "Abaixo de 50%, a melhor do treino tende a continuar acima da mediana "
            "fora dele. Perto ou acima de 50%, a escolha vira sorte. Combinações da "
            "mesma estratégia são parecidas, então o PBO costuma ser baixo: ele mede a "
            "escolha entre variações, não se a estratégia vale a pena."
        )


def _escolher_livres(nome, numericos):
    """Os parâmetros que variam na ficha e na validação (até 2); vazio se a regra não tem números."""
    if not numericos:
        return []
    rotulos = {p.nome: p.rotulo for p in numericos}
    return st.multiselect(
        "Parâmetros que podem variar na validação (até 2)",
        [p.nome for p in numericos],
        default=[p.nome for p in numericos][:2],
        format_func=lambda n: rotulos[n],
        max_selections=2,
        key=f"validacao_livres_{nome}",
        help="O app testa vários valores destes parâmetros. Os outros ficam como você "
        "configurou acima.",
    )


def _detalhe_tecnico(
    dados,
    nome,
    parametros,
    custo,
    protecoes,
    taxa_livre_de_risco,
    retorno_do_usuario,
    retorno_de_referencia,
    capital_inicial,
    operacoes,
    posicao_desejada,
    livres,
):
    """Treino/teste, walk-forward, mapa de parâmetros, acaso e sorte na escolha, em abas."""
    numericos = parametros_numericos(nome)
    if not numericos:
        st.info(
            "Esta estratégia não tem números para ajustar, então não há o que validar."
        )
        return
    if not livres:
        st.info("Escolha pelo menos um parâmetro para variar.")
        return
    rotulos = {p.nome: p.rotulo for p in numericos}
    candidatos = montar_candidatos(nome, parametros, livres)
    try:
        retornos, validos = calcular_candidatos(
            dados, nome, candidatos, custo, protecoes
        )
    except ValueError as erro:
        st.error(str(erro))
        return
    st.caption(f"{len(validos)} combinações testadas.")

    def sharpe(r):
        return ind.calcular_indice_sharpe(r, taxa_livre_de_risco)

    aba_tt, aba_wf, aba_mapa, aba_acaso, aba_sorte = st.tabs(
        [
            "Treino e teste",
            "Walk-forward",
            "Mapa de parâmetros",
            "Monte Carlo e acaso",
            "Sorte na escolha",
        ]
    )

    with aba_tt:
        _aba_treino_e_teste(
            nome,
            retorno_do_usuario,
            capital_inicial,
            retorno_de_referencia,
            taxa_livre_de_risco,
            rotulos,
            retornos,
            validos,
            sharpe,
        )

    with aba_wf:
        _aba_walk_forward(
            nome,
            capital_inicial,
            retorno_de_referencia,
            taxa_livre_de_risco,
            rotulos,
            retornos,
            validos,
            sharpe,
        )

    with aba_mapa:
        _aba_mapa_de_parametros(
            parametros, taxa_livre_de_risco, rotulos, livres, retornos, validos
        )

    with aba_acaso:
        _aba_monte_carlo_e_acaso(
            dados, operacoes, taxa_livre_de_risco, custo, posicao_desejada
        )

    with aba_sorte:
        _aba_sorte_na_escolha(nome, taxa_livre_de_risco, rotulos, retornos, validos)


def secao_validacao(
    dados,
    nome,
    parametros,
    custo,
    protecoes,
    taxa_livre_de_risco,
    retorno_do_usuario,
    retorno_de_referencia,
    capital_inicial,
    operacoes,
    posicao_desejada,
    cdi_diario=None,
):
    """A ficha "Foi sorte?" em destaque e, um clique abaixo, a validação técnica completa."""
    st.divider()
    st.subheader("Foi sorte?", help=ajuda_do("Foi sorte?"))
    st.caption(
        "Um backtest sempre parece bom quando os parâmetros foram escolhidos olhando os "
        "mesmos dados. A ficha confere, em cinco perguntas, se o resultado se sustenta."
    )
    col_livres, col_tolerancia = st.columns([2, 1])
    with col_livres:
        livres = _escolher_livres(nome, parametros_numericos(nome))
    with col_tolerancia:
        tolerancia = escolher_tolerancia()
    ticker, tentativas_da_pessoa = contar_esta_tentativa(
        nome, parametros, protecoes, custo
    )
    pedido = PedidoDaFicha(
        dados=dados,
        estrategia=nome,
        parametros=dict(parametros),
        custo_por_operacao=custo,
        capital_inicial=capital_inicial,
        protecoes=protecoes,
        livres=tuple(livres),
        taxa_livre_de_risco=taxa_livre_de_risco,
        cdi_diario=cdi_diario,
        tolerancia_de_queda=tolerancia,
        tentativas_da_pessoa=tentativas_da_pessoa,
    )
    try:
        resultado_da_ficha = calcular_ficha(pedido)
        lembrar_para_salvar(pedido, resultado_da_ficha)
        mostrar_ficha(
            resultado_da_ficha,
            texto_das_tentativas(tentativas_da_pessoa, ticker, TETO_POR_PESSOA),
        )
    except ValueError as erro:
        st.info(str(erro))
    with st.expander("Ver o detalhe técnico"):
        _detalhe_tecnico(
            dados,
            nome,
            parametros,
            custo,
            protecoes,
            taxa_livre_de_risco,
            retorno_do_usuario,
            retorno_de_referencia,
            capital_inicial,
            operacoes,
            posicao_desejada,
            livres,
        )


def escolher_custos():
    """Custo por operação em %: um número só ou separado em corretagem, taxas e slippage."""
    modo = st.radio(
        "Custos",
        ["Um número só", "Detalhados"],
        horizontal=True,
        key="backtest_modo_custos",
        help=ajuda_do("Custo de operação"),
    )
    if modo == "Um número só":
        return st.number_input(
            "Custo por operação (%)",
            min_value=0.0,
            max_value=2.0,
            value=CUSTO_PADRAO_POR_OPERACAO * 100,
            step=0.01,
            format="%.2f",
            key="backtest_custo",
            help="Corretagem, taxas e a diferença entre o preço pedido e o executado, "
            "cobrados em cada compra e em cada venda.",
        )
    c1, c2, c3 = st.columns(3)
    corretagem = c1.number_input(
        "Corretagem (%)", 0.0, 1.0, 0.0, 0.01, format="%.2f", key="custo_corretagem"
    )
    taxas = c2.number_input(
        "Taxas e emolumentos (%)",
        0.0,
        1.0,
        0.03,
        0.01,
        format="%.2f",
        key="custo_taxas",
        help="Taxas da bolsa e da liquidação. Os valores variam: confira na sua corretora.",
    )
    slippage = c3.number_input(
        "Slippage (%)",
        0.0,
        1.0,
        0.02,
        0.01,
        format="%.2f",
        key="custo_slippage",
        help="Diferença entre o preço que você via e o preço em que a ordem foi executada.",
    )
    total = corretagem + taxas + slippage
    st.caption(
        f"Custo total: {f'{total:.2f}'.replace('.', ',')}% em cada compra e em cada venda."
    )
    return total


def _comparar_com_o_cdi(cdi_diario, fechamento, resultado, curvas, mostrar_cdi):
    """Põe o CDI nas curvas (se houver) e diz se a estratégia rendeu mais ou menos que ele."""
    if mostrar_cdi:
        try:
            cdi_diario = obter_cdi(fechamento.index[0], fechamento.index[-1])
        except CDIIndisponivelError as erro:
            st.warning(str(erro))
    if cdi_diario is not None:
        curva_cdi = curva_do_cdi(cdi_diario, fechamento.index)
        curvas["CDI"] = curva_cdi
        rendimento = float(resultado.curva_de_capital.iloc[-1] - 1)
        st.caption(
            f"O CDI rendeu {formatar_pct(curva_cdi.iloc[-1] - 1, com_sinal=True)} no período; "
            f"a estratégia, {formatar_pct(rendimento, com_sinal=True)}. "
            + (
                "Ela ficou acima do CDI."
                if rendimento > curva_cdi.iloc[-1] - 1
                else "Ela não bateu o CDI."
            )
        )


def _mais_numeros(taxa_livre_de_risco, resultado):
    """Ômega, meio Kelly e quanto histórico seria preciso para confiar no Sharpe."""
    retorno_principal = resultado.retorno
    numeros = mais_numeros(retorno_principal, taxa_livre_de_risco)
    c1, c2, c3 = st.columns(3)
    c1.metric(
        "Ômega",
        "—" if pd.isna(numeros.omega) else formatar_metrica("Sharpe", numeros.omega),
        help=ajuda_do("Ômega"),
    )
    c2.metric(
        "Meio Kelly (fração do capital)",
        "—" if pd.isna(numeros.meio_kelly) else formatar_pct(numeros.meio_kelly),
        help=ajuda_do("Critério de Kelly"),
    )
    if pd.isna(numeros.anos_minimos):
        texto_dias = "—"
    elif numeros.anos_minimos == float("inf"):
        texto_dias = "nunca (Sharpe não passa de zero)"
    else:
        texto_dias = f"{numeros.anos_minimos:.1f} anos".replace(".", ",")
    c3.metric(
        "Histórico para 95% de confiança",
        texto_dias,
        help=ajuda_do("Comprimento mínimo do histórico"),
    )
    anos = f"{len(retorno_principal) / ind.DIAS_POR_ANO:.1f}".replace(".", ",")
    st.caption(
        f"Os dados disponíveis têm {anos} anos. O Kelly é muito sensível ao erro de "
        "estimativa e acima de 100% pediria alavancagem: trate-o como curiosidade, "
        "não como recomendação."
    )


def _mostrar_imposto(nome_principal, impostos):
    """O imposto pago pela estratégia principal, com o detalhe mês a mês."""
    pago = impostos[nome_principal]
    valor = f"{pago.imposto_total:,.2f}".replace(",", "X").replace(".", ",")
    valor = valor.replace("X", ".")
    st.caption(
        f"Imposto pago por {nome_principal}: R\\$ {valor}. "
        "Regras simplificadas da B3 (15% sobre o lucro do mês, isento até R\\$ 20 mil "
        "vendidos no mês); não é orientação tributária. Comprar e segurar só paga "
        "imposto quando vende."
    )
    if not pago.meses.empty:
        with st.expander("Ver o imposto mês a mês"):
            mensal = pago.meses.copy()
            for coluna in mensal.columns[1:]:
                mensal[coluna] = [f"{v:,.2f}" for v in mensal[coluna]]
            st.dataframe(mensal, width="stretch", hide_index=True)


def _tabela_de_operacoes(resultado):
    """As operações da estratégia principal, em tabela e em CSV."""
    operacoes = resultado.operacoes.copy()
    operacoes["entrada"] = operacoes["entrada"].dt.strftime("%d/%m/%Y")
    operacoes["saida"] = operacoes["saida"].dt.strftime("%d/%m/%Y")
    operacoes["retorno"] = [
        formatar_pct(v, com_sinal=True) for v in operacoes["retorno"]
    ]
    operacoes["aberta"] = operacoes["aberta"].map({True: "sim", False: "não"})
    operacoes.columns = [
        "Primeiro dia",
        "Último dia",
        "Dias",
        "Retorno",
        "Em aberto",
    ]
    st.dataframe(operacoes, width="stretch", hide_index=True)
    st.download_button(
        "Baixar as operações (CSV)",
        converter_para_csv(montar_tabela_de_operacoes(resultado.operacoes)),
        file_name="operacoes.csv",
        mime="text/csv",
        key="baixar_operacoes_backtest",
    )


def _avisar_entrada_tardia(fechamento, nome, resultado):
    """Avisa quando a estratégia demorou a entrar no mercado (a comparação fica desigual)."""
    if nome != ESTRATEGIA_DE_REFERENCIA and not resultado.operacoes.empty:
        primeira_entrada = resultado.operacoes.iloc[0]["entrada"]
        dias_parada = (primeira_entrada - fechamento.index[0]).days
        dias_totais = (fechamento.index[-1] - fechamento.index[0]).days
        if dias_parada > 0.15 * dias_totais:
            st.caption(
                f"Atenção: a estratégia só entrou no mercado em {primeira_entrada:%d/%m/%Y}. "
                "Antes disso ficou em caixa (falta de histórico ou de sinal), então ela e "
                "comprar e segurar não ficaram expostas pelo mesmo tempo."
            )


def secao_backtest(dados, taxa_livre_de_risco, cdi_diario=None):
    esquecer_a_ficha_para_salvar()
    st.subheader("Backtest: e se eu tivesse seguido esta regra?")
    st.caption(
        "Simulação com dados do passado. A decisão tomada no fim de cada dia só vale a partir "
        "do dia seguinte, para a simulação não usar o futuro."
    )
    with st.container(border=True):
        nome, parametros = escolher_estrategia()
        custo_percentual = escolher_custos()
        capital_inicial = st.number_input(
            "Capital inicial (R\\$)",
            min_value=100.0,
            value=10_000.0,
            step=1_000.0,
            key="backtest_capital",
        )
        protecoes = escolher_protecoes()
        col_imposto, col_cdi = st.columns(2)
        descontar_imposto = col_imposto.checkbox(
            "Descontar imposto de renda (simplificado)",
            key="backtest_imposto",
            help=ajuda_do("Imposto de renda (simplificado)"),
        )
        mostrar_cdi = False
        if cdi_diario is None:
            mostrar_cdi = col_cdi.checkbox(
                "Mostrar o CDI como referência",
                key="backtest_mostrar_cdi",
                help=ajuda_do("CDI"),
            )

    fechamento = dados["Close"]
    try:
        posicao = gerar_posicao(nome, dados, **parametros)
        posicao_protegida = aplicar_protecoes(dados, posicao, protecoes)
    except ValueError as erro:
        st.error(str(erro))
        return
    tem_stop = any(
        v is not None
        for v in (
            protecoes.stop_loss,
            protecoes.take_profit,
            protecoes.stop_movel,
            protecoes.stop_atr,
        )
    )
    if (
        nome == ESTRATEGIA_DE_REFERENCIA
        and tem_stop
        and protecoes.dias_de_espera is None
    ):
        st.info(
            "Comprar e segurar nunca manda sair, então depois de um stop ela não teria um "
            "sinal novo para voltar e ficaria fora do mercado até o fim. Para ver o efeito "
            'do stop com reentrada, escolha uma espera em "Depois de um stop".'
        )
    custo = custo_percentual / 100
    com_protecao = protecoes.alguma_ligada()
    nome_principal = f"{nome} + proteções" if com_protecao else nome

    # todas as simulações, na ordem em que aparecem nos gráficos e na tabela
    resultados = {
        nome_principal: executar_backtest(fechamento, posicao_protegida, custo)
    }
    if com_protecao:
        resultados[f"{nome} (sem proteções)"] = executar_backtest(
            fechamento, posicao, custo
        )
    if nome != ESTRATEGIA_DE_REFERENCIA:
        resultados[ESTRATEGIA_DE_REFERENCIA] = executar_backtest(
            fechamento, gerar_posicao(ESTRATEGIA_DE_REFERENCIA, dados), custo
        )
    resultados_brutos = resultados
    impostos = {}
    if descontar_imposto:
        resultados = {}
        for rotulo, r in resultados_brutos.items():
            impostos[rotulo] = aplicar_imposto(r, capital_inicial)
            resultados[rotulo] = impostos[rotulo].resultado
    resultado = resultados[nome_principal]

    explicacao = obter_estrategias().get(nome)
    if explicacao:
        with st.expander("Como funciona esta estratégia", expanded=True):
            st.markdown(proteger_cifrao(explicacao))

    if resultado.operacoes.empty:
        st.info(
            "A estratégia não fez nenhuma operação neste período. Algumas regras precisam de "
            "mais histórico (por exemplo, uma média de 200 dias): tente um período maior."
        )

    _avisar_entrada_tardia(fechamento, nome, resultado)

    numeros = {
        rotulo: resumir_desempenho(
            r.retorno, r.posicao, r.operacoes, taxa_livre_de_risco
        )
        for rotulo, r in resultados.items()
    }
    numeros_principal = numeros[nome_principal]
    numeros_referencia = numeros.get(ESTRATEGIA_DE_REFERENCIA, numeros_principal)

    cartoes = st.columns(4)
    for coluna, metrica in zip(
        cartoes,
        ["Retorno total", "Índice de Sharpe", "Maior queda", "Operações"],
        strict=True,
    ):
        comparacao = (
            f"{formatar_metrica(metrica, numeros_referencia[metrica])} em {ESTRATEGIA_DE_REFERENCIA.lower()}"
            if nome != ESTRATEGIA_DE_REFERENCIA
            else None
        )
        coluna.metric(
            metrica,
            formatar_metrica(metrica, numeros_principal[metrica]),
            delta=comparacao,
            delta_color="off",
            delta_arrow="off",
            help=ajuda_do(
                {"Retorno total": "Retorno acumulado", "Maior queda": "Drawdown"}.get(
                    metrica, metrica
                )
            ),
        )

    sharpe, minimo, maximo = calcular_intervalo_do_sharpe(
        resultado.retorno, taxa_livre_de_risco
    )
    if not pd.isna(sharpe):
        medido, baixo, alto = (
            formatar_metrica("Sharpe", v) for v in (sharpe, minimo, maximo)
        )
        st.caption(
            f"O Sharpe medido é {medido}, mas com estes dados ele pode estar entre "
            f"{baixo} e {alto} (intervalo de ~95%). Com poucos anos de dados, "
            "o Sharpe é muito incerto: não compare estratégias por diferenças pequenas."
        )

    curvas = {rotulo: r.curva_de_capital for rotulo, r in resultados.items()}
    _comparar_com_o_cdi(cdi_diario, fechamento, resultado, curvas, mostrar_cdi)
    mostrar_grafico(
        graficos.criar_grafico_curvas_de_capital(
            curvas, capital_inicial, destaque=nome_principal
        )
    )

    col_quedas, col_preco = st.columns(2)
    with col_quedas:
        mostrar_grafico(
            graficos.criar_grafico_quedas_comparadas(curvas, destaque=nome_principal)
        )
    with col_preco:
        mostrar_grafico(
            graficos.criar_grafico_operacoes_no_preco(fechamento, resultado.operacoes)
        )

    st.markdown("**Números lado a lado**")
    tabela = pd.DataFrame(
        {
            rotulo: {m: formatar_metrica(m, v) for m, v in valores.items()}
            for rotulo, valores in numeros.items()
        }
    )
    st.dataframe(tabela, width="stretch")
    oferecer_salvar_simulacao(
        "backtest",
        f"{nome_principal} · {normalizar_ticker(st.session_state['ticker'])} · "
        f"{st.session_state['periodo']}",
        tabela[nome_principal].to_dict(),
        f"{fechamento.index[-1]:%d/%m/%Y}",
        chave_da_ficha=CHAVE_DA_FICHA_PARA_SALVAR,
    )
    st.download_button(
        "Baixar as curvas de capital (CSV)",
        converter_para_csv(montar_tabela_de_curvas(curvas, capital_inicial)),
        file_name="curvas_de_capital.csv",
        mime="text/csv",
        key="baixar_curvas_backtest",
    )

    with st.expander("Mais números: Ômega, Kelly e quanto histórico seria preciso"):
        _mais_numeros(taxa_livre_de_risco, resultado)

    if descontar_imposto:
        _mostrar_imposto(nome_principal, impostos)

    if not resultado.operacoes.empty:
        with st.expander(f"Ver as {len(resultado.operacoes)} operações"):
            _tabela_de_operacoes(resultado)

    secao_validacao(
        dados,
        nome,
        parametros,
        custo,
        protecoes,
        taxa_livre_de_risco,
        resultados_brutos[nome_principal].retorno,
        resultados_brutos[ESTRATEGIA_DE_REFERENCIA].retorno,
        capital_inicial,
        resultado.operacoes,
        posicao_protegida,
        cdi_diario,
    )

    st.warning(
        "Cuidado: o passado não garante o futuro. Uma regra que funcionou aqui pode ter sido "
        "ajustada ao acaso (*overfitting*); o app usa só ativos que existem hoje (*viés de "
        "sobrevivência*); e os custos reais podem ser maiores que os simulados."
    )


def pagina_backtest():
    cabecalho_da_pagina("backtest")
    c = carregar_contexto()
    atalho_para_o_relatorio(relatorios.BACKTEST)
    secao_backtest(c.dados, c.taxa_livre_de_risco, c.cdi_diario)
