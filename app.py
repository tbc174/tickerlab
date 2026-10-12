"""TickerLab: interface do app. Só mostra; os cálculos ficam em src/."""

import logging

import numpy as np
import pandas as pd
import streamlit as st

from src import (
    aprendizado,
    catalogo,
    graficos,
    marca,
    relatorios,
    trade,
    tutorial,
)
from src import indicadores as ind
from src import presets as research_presets
from src.acaso import (
    calcular_comprimento_minimo,
    calcular_pbo,
    calcular_sharpe_deflacionado,
    simular_monte_carlo,
    testar_contra_o_acaso,
)
from src.backtest import CUSTO_PADRAO_POR_OPERACAO, executar_backtest
from src.banco.conexao import obter_engine
from src.banco.dados_do_usuario import (
    DadosInvalidosError,
    apagar_simulacao,
    carregar_preferencias,
    listar_favoritos,
    listar_simulacoes,
    salvar_preferencias,
    salvar_simulacao,
)
from src.carteiras import (
    ESTRATEGIAS_DE_CARTEIRA,
    MAX_ATIVOS_NA_CARTEIRA,
    MIN_ATIVOS_NA_CARTEIRA,
    simular_carteira,
)
from src.cdi import (
    CDIIndisponivelError,
    curva_do_cdi,
)
from src.comparacao import (
    NOMES_AMIGAVEIS,
    alinhar_fechamentos,
    interpretar_tickers,
)
from src.conteudo import (
    carregar_estrategias,
    carregar_sobre,
    proteger_cifrao,
)
from src.dados import DadosIndisponiveisError, normalizar_ticker
from src.estilo import CSS_DO_APP
from src.estrategias import ESTRATEGIAS, gerar_posicao
from src.experimentos import (
    REGRAS_DE_REBALANCEAMENTO,
    calcular_retorno_da_noite_com_custo,
    comparar_dentro_e_fora,
    comparar_janelas,
    resumir_janelas,
    resumir_noite_e_dia,
    separar_noite_e_dia,
    simular_aporte_unico_e_dca,
    simular_rebalanceamento,
    simular_virada_do_mes,
)
from src.exportacao import (
    converter_para_csv,
    montar_tabela_de_curvas,
    montar_tabela_de_operacoes,
    montar_tabela_de_precos,
)
from src.imposto import aplicar_imposto
from src.link import ler_parametros
from src.logs import configurar_logs
from src.metricas import (
    calcular_intervalo_do_sharpe,
    calcular_kelly,
    calcular_omega,
    resumir_desempenho,
)
from src.momentum import montar_tabela_de_momentum
from src.paginas import (
    GRUPOS,
    PAGINA_INICIAL,
    pagina,
    paginas_do_grupo,
)
from src.pares import MAX_ATIVOS_PARA_PARES, procurar_pares, simular_par
from src.planos import (
    APRENDIZADO_DE_MAQUINA,
    PARES,
    LimiteDoPlanoError,
    descrever_limite,
    limites_do,
    pode_usar,
)
from src.protecoes import Protecoes, aplicar_protecoes
from src.ranking import montar_ranking
from src.regimes import (
    REGIMES_DE_TENDENCIA,
    REGIMES_DE_VOLATILIDADE,
    aplicar_disjuntor_de_drawdown,
    classificar_regimes_de_tendencia,
    classificar_regimes_de_volatilidade,
    filtrar_por_regime,
    gerir_pela_variancia,
    resumir_por_regime,
    varrer_disjuntor,
)
from src.simulacoes import NOMES_DOS_TIPOS, capturar_estado, restaurar_estado
from src.validacao import (
    avaliar_treino_e_teste,
    calcular_retornos_dos_candidatos,
    data_de_corte,
    executar_walk_forward,
    montar_candidatos,
    montar_mapa_de_sharpe,
    parametros_numericos,
)
from telas.analise import (
    pagina_comparar,
    pagina_correlacao,
    pagina_retorno_mensal,
    pagina_risco,
    secao_painel_de_numeros,
    secao_preco,
    secao_tendencia_e_volume,
)
from telas.comum import (
    PAGINAS_DO_MENU,
    PERIODOS_DO_TOPO,
    _alternar_favorito_atual,
    ajuda_do,
    avisar_parametros,
    cabecalho_da_pagina,
    carregar_contexto,
    carregar_dados,
    formatar_metrica,
    formatar_pct,
    marcar_feito,
    mostrar_grafico,
    obter_cdi,
    obter_glossario,
    parametros_em_vigor,
    plano_atual,
)
from telas.conta.admin import pagina_admin
from telas.conta.assinatura import (
    exigir_recurso,
    mostrar_conta,
    mostrar_planos,
    mostrar_retorno_do_pagamento,
    pagina_planos,
)
from telas.conta.entrada import obter_usuario_logado
from telas.conta.meus_dados import pagina_meus_dados
from telas.conta.textos_legais import pagina_privacidade, pagina_termos
from telas.relatorios.biblioteca import mostrar_biblioteca
from telas.relatorios.estudio import (
    _aplicar_secoes,
    atalho_para_o_relatorio,
    mostrar_estudio,
)
from telas.research.acontecimentos import pagina_research
from telas.research.alertas import pagina_alertas
from telas.research.donos import pagina_donos
from telas.research.fundamentos import pagina_fundamentos
from telas.research.minha_carteira import pagina_carteira_research
from telas.research.newsletter import pagina_newsletter
from telas.research.parametros import pagina_parametros
from telas.research.por_dentro import pagina_por_dentro

# o mesmo logger do telas/comum.py (o nome fixo faz o Python devolver o mesmo objeto)
log_da_conta = logging.getLogger("tickerlab.conta")
ESPERAS_DEPOIS_DO_STOP = {
    "Só com um sinal novo da estratégia": None,
    "Esperar 5 dias úteis": 5,
    "Esperar 20 dias úteis": 20,
    "Esperar 60 dias úteis": 60,
}
ESTRATEGIA_DE_REFERENCIA = "Comprar e segurar"

configurar_logs()
st.set_page_config(
    page_title="TickerLab", page_icon=str(marca.ARQUIVO_DO_ICONE), layout="wide"
)
st.markdown(f"<style>{CSS_DO_APP}</style>", unsafe_allow_html=True)
# símbolo + "TickerLab" no canto do menu (clicar volta ao Início); só o símbolo se faltar espaço
st.logo(str(marca.ARQUIVO_DA_ASSINATURA), size="large")


# --- Ajudantes --------------------------------------------------------------


@st.cache_data
def obter_estrategias():
    """Lê as explicações das estratégias uma vez só."""
    return carregar_estrategias()


# --- Dados da conta: favoritos, preferências e simulações salvas ------------------------


def carregar_da_conta(usuario):
    """Uma vez por sessão: favoritos e preferências da conta viram o ponto de partida.

    Vem antes de `ler_entradas`, então um link compartilhado (que é lido depois) ainda manda.
    """
    if usuario is None or st.session_state.get("conta_carregada"):
        return
    st.session_state["conta_carregada"] = True
    try:
        with obter_engine().connect() as conexao:
            favoritos = listar_favoritos(conexao, usuario.id)
            preferencias = carregar_preferencias(conexao, usuario.id)
    except Exception:
        log_da_conta.exception("Falha ao carregar os dados da conta")
        st.warning("Não consegui carregar os favoritos e as preferências da sua conta.")
        return
    lidos = ler_parametros(
        {
            "ticker": str(preferencias.get("ticker", "")),
            "periodo": str(preferencias.get("periodo", "")),
            "taxa": str(preferencias.get("taxa", "")),
            "reais": "1" if preferencias.get("em_reais") is True else "",
            "fav": ",".join(favoritos),
        }
    )
    for chave in ("ticker", "periodo", "taxa", "em_reais", "favoritos"):
        if chave in lidos:
            st.session_state[chave] = lidos[chave]
    if isinstance(preferencias.get("relatorio"), dict):
        st.session_state["config_salva_do_relatorio"] = preferencias["relatorio"]
    if preferencias.get("tutorial_visto") is True:
        st.session_state["tutorial_visto"] = True


def _campo_ainda_vale(chave, valor):
    """A tela de hoje ainda aceita este valor guardado? (evita quebrar um campo ao reabrir)"""
    if chave == "backtest_estrategia":
        return valor in ESTRATEGIAS
    if chave == "carteira_estrategia":
        return valor in ESTRATEGIAS_DE_CARTEIRA
    if chave == "espera_depois_do_stop":
        return valor in ESPERAS_DEPOIS_DO_STOP
    if chave == "backtest_modo_custos":
        return valor in ("Um número só", "Detalhados")
    registros = (
        ("parametro_", ESTRATEGIAS),
        ("carteira_", ESTRATEGIAS_DE_CARTEIRA),
    )
    for prefixo, registro in registros:
        for nome, estrategia in registro.items():
            for p in estrategia.parametros:
                if chave == f"{prefixo}{nome}_{p.nome}":
                    if getattr(p, "opcoes", None):
                        return valor in p.opcoes
                    return (
                        isinstance(valor, int | float)
                        and not isinstance(valor, bool)
                        and p.minimo <= valor <= p.maximo
                    )
    return not chave.startswith("parametro_")  # parâmetro desconhecido: não volta


def _salvar_simulacao(usuario, tipo, nome_sugerido, resumo):
    nome = st.session_state.get(f"salvar_nome_{tipo}", "").strip() or nome_sugerido
    try:
        with obter_engine().begin() as conexao:
            salvar_simulacao(
                conexao,
                usuario.id,
                tipo,
                nome,
                capturar_estado(st.session_state, tipo),
                resumo,
                plano=usuario.plano,
            )
    except (DadosInvalidosError, LimiteDoPlanoError) as erro:
        st.toast(str(erro))
        return
    except Exception:
        log_da_conta.exception("Falha ao salvar a simulação")
        st.toast("Não consegui salvar a simulação agora. Tente de novo em instantes.")
        return
    st.session_state[f"salvar_nome_{tipo}"] = ""
    st.toast(f"Simulação salva: {nome}. Veja em Minhas simulações.")


def oferecer_salvar_simulacao(tipo, nome_sugerido, numeros, dados_ate):
    """Caixa para guardar a simulação da tela na conta do usuário."""
    usuario = st.session_state.get("usuario")
    nome_sugerido = nome_sugerido[:120]
    resumo = {
        "numeros": {str(k): str(v) for k, v in numeros.items()},
        "dados_ate": dados_ate,
    }
    with st.expander("Salvar esta simulação na minha conta"):
        if usuario is None:
            st.caption("Entre com a sua conta do Google para guardar simulações.")
            return
        st.text_input(
            "Nome",
            key=f"salvar_nome_{tipo}",
            placeholder=nome_sugerido,
            max_chars=120,
            help="Se ficar em branco, uso o nome sugerido.",
        )
        st.button(
            "Salvar",
            key=f"salvar_{tipo}",
            on_click=_salvar_simulacao,
            args=(usuario, tipo, nome_sugerido, resumo),
        )
        st.caption(
            "Guardo as escolhas desta aba e um resumo dos números. Ao reabrir, "
            "tudo é recalculado com os dados de hoje."
        )


def _reabrir_simulacao(simulacao):
    campos = restaurar_estado(
        simulacao.parametros, simulacao.tipo, campo_ainda_vale=_campo_ainda_vale
    )
    for chave, valor in campos.items():
        st.session_state[chave] = valor
    st.toast(
        f'Reabri "{simulacao.nome}". Abra a aba {NOMES_DOS_TIPOS[simulacao.tipo]} '
        "para ver."
    )


def _apagar_simulacao(usuario, simulacao):
    try:
        with obter_engine().begin() as conexao:
            apagar_simulacao(conexao, usuario.id, simulacao.id)
    except Exception:
        log_da_conta.exception("Falha ao apagar a simulação")
        st.toast("Não consegui apagar agora. Tente de novo em instantes.")
        return
    st.toast(f"Simulação apagada: {simulacao.nome}.")


def secao_minhas_simulacoes():
    usuario = st.session_state.get("usuario")
    if usuario is None:
        st.info(
            "Entre com a sua conta do Google para guardar e reabrir simulações. "
            "Depois de rodar um Backtest, uma Carteira ou um Par, use "
            '"Salvar esta simulação na minha conta".'
        )
        return
    try:
        with obter_engine().connect() as conexao:
            simulacoes = listar_simulacoes(conexao, usuario.id)
    except Exception:
        log_da_conta.exception("Falha ao listar as simulações")
        st.warning("Não consegui carregar as suas simulações agora.")
        return
    if not simulacoes:
        st.caption(
            f"Plano {limites_do(usuario.plano).nome}: "
            f"{descrever_limite(limites_do(usuario.plano).simulacoes).lower()} simulações."
        )
        st.info(
            "Você ainda não salvou nenhuma simulação. Rode um Backtest, uma Carteira ou "
            'um Par e use "Salvar esta simulação na minha conta".'
        )
        return
    limite = limites_do(usuario.plano).simulacoes
    st.caption(
        f"{len(simulacoes)} de {descrever_limite(limite).lower()} simulações no plano "
        f"{limites_do(usuario.plano).nome}, da mais nova para a mais antiga."
    )
    with st.expander("Ver os planos"):
        mostrar_planos()
    for simulacao in simulacoes:
        titulo = (
            f"{simulacao.nome} · {NOMES_DOS_TIPOS[simulacao.tipo]} · "
            f"{simulacao.criada_em:%d/%m/%Y %H:%M}"
        )
        with st.expander(titulo):
            numeros = simulacao.resultado.get("numeros", {})
            if numeros:
                st.dataframe(pd.DataFrame({"Resultado": numeros}), width="stretch")
            if simulacao.resultado.get("dados_ate"):
                st.caption(
                    f"Números calculados com dados até {simulacao.resultado['dados_ate']}."
                )
            col_reabrir, col_apagar, _ = st.columns([1, 1, 4])
            col_reabrir.button(
                "Reabrir",
                key=f"reabrir_{simulacao.id}",
                on_click=_reabrir_simulacao,
                args=(simulacao,),
            )
            with col_apagar.popover("Apagar"):
                st.write("Apagar esta simulação para sempre?")
                st.button(
                    "Sim, apagar",
                    key=f"apagar_{simulacao.id}",
                    on_click=_apagar_simulacao,
                    args=(usuario, simulacao),
                )


# --- Cabeçalho e entradas -----------------------------------------------------


def preparar_estado_inicial():
    """Valores iniciais dos campos do topo; na primeira visita, lê os da URL (link compartilhado)."""
    padroes = {"ticker": "PETR4.SA", "periodo": "2y", "taxa": "Zero", "favoritos": []}
    for chave, valor in padroes.items():
        st.session_state.setdefault(chave, valor)
    if not st.session_state.get("url_lida"):
        st.session_state["url_lida"] = True
        lidos = ler_parametros(dict(st.query_params))
        for chave in (
            "ticker",
            "periodo",
            "taxa",
            "em_reais",
            "usar_exemplo",
            "favoritos",
        ):
            if chave in lidos:
                st.session_state[chave] = lidos[chave]


def acoes_feitas():
    feitos = set(st.session_state.get("tutorial_feitos", set()))
    if st.session_state.get("favoritos"):
        feitos.add("salvou_favorito")
    return feitos


# --- Seções -----------------------------------------------------------------


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


def _curva_a_partir_de(retorno):
    return (1 + retorno).cumprod()


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
):
    """Treino/teste, walk-forward e mapa de parâmetros: o resultado se sustenta fora do passado?"""
    st.divider()
    st.subheader("Isto se sustenta? Validação fora da amostra")
    st.caption(
        "Um backtest sempre parece bom quando os parâmetros foram escolhidos olhando os "
        "mesmos dados. Aqui a escolha é feita num pedaço do histórico e conferida em outro."
    )
    numericos = parametros_numericos(nome)
    if not numericos:
        st.info(
            "Esta estratégia não tem números para ajustar, então não há o que validar."
        )
        return
    rotulos = {p.nome: p.rotulo for p in numericos}
    livres = st.multiselect(
        "Parâmetros que podem variar na validação (até 2)",
        [p.nome for p in numericos],
        default=[p.nome for p in numericos][:2],
        format_func=lambda n: rotulos[n],
        max_selections=2,
        key=f"validacao_livres_{nome}",
        help="O app testa vários valores destes parâmetros. Os outros ficam como você "
        "configurou acima.",
    )
    if not livres:
        st.info("Escolha pelo menos um parâmetro para variar.")
        return
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
                "Melhor do treino": _curva_a_partir_de(tt.retorno_no_teste),
                "Sua configuração": _curva_a_partir_de(teste),
                "Comprar e segurar": _curva_a_partir_de(referencia),
            }
            mostrar_grafico(
                graficos.criar_grafico_curvas_de_capital(
                    curvas, capital_inicial, destaque="Melhor do treino"
                )
            )

    with aba_wf:
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
                        "Walk-forward (só dias de teste)": _curva_a_partir_de(fora),
                        "Comprar e segurar": _curva_a_partir_de(referencia),
                    },
                    capital_inicial,
                    destaque="Walk-forward (só dias de teste)",
                )
            )
            janelas = wf.janelas.copy()
            for coluna in ("Começo do treino", "Começo do teste", "Fim do teste"):
                janelas[coluna] = janelas[coluna].dt.strftime("%d/%m/%Y")
            janelas["Parâmetros escolhidos"] = [
                _texto_dos_parametros(p, rotulos)
                for p in janelas["Parâmetros escolhidos"]
            ]
            for coluna in ("Sharpe no treino", "Sharpe no teste"):
                janelas[coluna] = [
                    formatar_metrica("Sharpe", v) for v in janelas[coluna]
                ]
            with st.expander(f"Ver as {len(janelas)} janelas"):
                st.dataframe(janelas, width="stretch", hide_index=True)

    with aba_mapa:
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
        valores = pd.Series(mapa.to_numpy(dtype=float).ravel()).dropna()
        if not valores.empty:
            st.caption(
                f"Mediana do Sharpe na grade: {formatar_metrica('Sharpe', valores.median())}; "
                f"melhor: {formatar_metrica('Sharpe', valores.max())}. "
                f"{formatar_pct((valores > 0).mean())} das combinações têm Sharpe positivo. "
                "O quadrado azul marca a sua configuração atual (se ela estiver na grade)."
            )

    with aba_acaso:
        st.markdown("**Monte Carlo: e se as operações tivessem vindo em outra ordem?**")
        st.caption(ajuda_do("Monte Carlo (das operações)"))
        if len(operacoes) < 5:
            st.info(
                "Com menos de 5 operações, o Monte Carlo não diz nada. Tente um período maior ou outros parâmetros."
            )
        else:
            mc = simular_monte_carlo(operacoes["retorno"])
            c1, c2, c3, c4 = st.columns(4)
            c1.metric(
                "Retorno típico (mediana)",
                formatar_pct(
                    float(pd.Series(mc.retornos_finais).median()), com_sinal=True
                ),
            )
            c2.metric(
                "Faixa de 90% dos casos",
                f"{formatar_pct(float(pd.Series(mc.retornos_finais).quantile(0.05)), com_sinal=True)} a "
                f"{formatar_pct(float(pd.Series(mc.retornos_finais).quantile(0.95)), com_sinal=True)}",
            )
            c3.metric("Chance de prejuízo", formatar_pct(mc.probabilidade_de_prejuizo))
            c4.metric(
                "Queda máxima no pior caso comum",
                formatar_pct(float(pd.Series(mc.quedas_maximas).quantile(0.05))),
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
            c1.metric(
                "Sharpe da estratégia", formatar_metrica("Sharpe", teste.sharpe_real)
            )
            c2.metric(
                "Sharpe mediano ao acaso",
                formatar_metrica(
                    "Sharpe", float(pd.Series(teste.sharpes_ao_acaso).median())
                ),
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

    with aba_sorte:
        st.markdown(
            "**Sharpe deflacionado: o melhor de muitas tentativas vale quanto?**"
        )
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
        melhor_coluna = retornos.apply(
            lambda r: ind.calcular_indice_sharpe(r, taxa_livre_de_risco)
        ).idxmax()
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


def _experimento_aporte(dados):
    st.markdown("**Aporte único ou parcelado?**")
    st.caption(
        "Investir tudo de uma vez ou dividir em parcelas mensais no mesmo ativo? "
        "O dinheiro que espera para ser investido fica parado, sem render."
    )
    fechamento = dados["Close"]
    c1, c2, c3 = st.columns(3)
    total = c1.number_input(
        "Valor total (R\\$)",
        min_value=100.0,
        value=12_000.0,
        step=1_000.0,
        key="exp_total",
    )
    parcelas = c2.slider("Parcelas mensais", 2, 24, 12, key="exp_parcelas")
    horizonte = c3.slider(
        "Horizonte das janelas (dias úteis)", 63, 504, 252, 21, key="exp_horizonte"
    )
    try:
        caminho = simular_aporte_unico_e_dca(fechamento, total, parcelas)
        janelas = comparar_janelas(fechamento, parcelas, horizonte)
    except ValueError as erro:
        st.info(
            f"{erro} Tente menos parcelas, um horizonte maior ou um período mais longo."
        )
        return
    resumo = resumir_janelas(janelas)
    k1, k2, k3, k4 = st.columns(4)
    k1.metric(
        "Aporte único vence em",
        formatar_pct(resumo["Aporte único vence"]),
        help="Fatia das datas de início em que investir tudo de uma vez terminou na frente.",
    )
    k2.metric(
        "Mediana: aporte único",
        formatar_pct(resumo["Mediana do aporte único"], com_sinal=True),
    )
    k3.metric(
        "Mediana: parcelado",
        formatar_pct(resumo["Mediana do parcelado"], com_sinal=True),
    )
    k4.metric(
        "Pior caso (único | parcelado)",
        f"{formatar_pct(resumo['Pior caso do aporte único'])} | "
        f"{formatar_pct(resumo['Pior caso do parcelado'])}",
    )
    st.caption(
        f"{int(resumo['Janelas'])} datas de início, cada uma acompanhada por {horizonte} dias úteis. "
        "As janelas se sobrepõem, então não são testes independentes: com poucos anos de dados, "
        "pense nelas como uma ilustração. "
        + (ajuda_do("DCA (aportes parcelados)") or "")
    )
    mostrar_grafico(
        graficos.criar_grafico_curvas_de_capital(
            {n: caminho[n] / total for n in caminho.columns},
            total,
            destaque="Aporte único",
        )
    )
    mostrar_grafico(graficos.criar_grafico_diferenca_das_janelas(janelas["Diferença"]))


def _experimento_rebalanceamento(dados, periodo, taxa_livre_de_risco):
    st.markdown("**Rebalanceamento: vale a pena voltar aos pesos?**")
    st.caption(ajuda_do("Rebalanceamento"))
    c1, c2, c3, c4 = st.columns(4)
    segundo = c1.text_input("Segundo ativo", value="^GSPC", key="exp_segundo")
    peso = c2.slider("Peso do ativo principal (%)", 10, 90, 50, 5, key="exp_peso")
    faixa = c3.slider("Faixa (pontos percentuais)", 1, 20, 5, key="exp_faixa")
    custo_percentual = c4.number_input(
        "Custo por operação (%)",
        0.0,
        2.0,
        CUSTO_PADRAO_POR_OPERACAO * 100,
        0.01,
        format="%.2f",
        key="exp_custo_rebalancear",
    )
    ticker_segundo = normalizar_ticker(segundo)
    if not ticker_segundo:
        st.info("Digite o segundo ativo.")
        return
    try:
        outro = carregar_dados(ticker_segundo, periodo)["Close"]
    except DadosIndisponiveisError as erro:
        st.warning(str(erro))
        return
    principal_nome = "Principal"
    alinhado, _ = alinhar_fechamentos(
        {principal_nome: dados["Close"], ticker_segundo: outro}
    )
    if len(alinhado) < 60 or list(alinhado.columns) != [principal_nome, ticker_segundo]:
        st.warning("Não há dias suficientes em comum entre os dois ativos.")
        return
    resultados = {}
    for regra in REGRAS_DE_REBALANCEAMENTO:
        resultados[regra if regra != "Por faixa" else f"Por faixa ({faixa} pontos)"] = (
            simular_rebalanceamento(
                alinhado, peso / 100, regra, faixa / 100, custo_percentual / 100
            )
        )
    linhas = {}
    for rotulo, r in resultados.items():
        numeros = resumir_desempenho(r.retorno, None, None, taxa_livre_de_risco)
        linhas[rotulo] = {
            "Retorno total": formatar_metrica(
                "Retorno total", numeros["Retorno total"]
            ),
            "Índice de Sharpe": formatar_metrica("Sharpe", numeros["Índice de Sharpe"]),
            "Maior queda": formatar_metrica("Maior queda", numeros["Maior queda"]),
            "Rebalanceamentos": str(r.rebalanceamentos),
            "Giro (x o capital)": f"{r.giro:.1f}".replace(".", ","),
        }
    mostrar_grafico(
        graficos.criar_grafico_curvas_de_capital(
            {n: r.curva_de_capital for n, r in resultados.items()},
            10_000.0,
            destaque=next(iter(resultados)),
        )
    )
    st.dataframe(pd.DataFrame(linhas).T, width="stretch")
    st.caption(
        f"Carteira com {peso}% no ativo principal e {100 - peso}% em {ticker_segundo}. "
        "Sem rebalancear, quem sobe vai ficando com mais peso. Rebalancear costuma reduzir "
        "o risco, mas cada ajuste custa; o efeito no retorno depende de os ativos "
        "se alternarem na liderança."
    )


def _experimento_noite_e_dia(dados, taxa_livre_de_risco):
    st.markdown("**Noite × dia: de onde vem o retorno?**")
    st.caption(ajuda_do("Retorno da noite e do dia"))
    try:
        partes = separar_noite_e_dia(dados)
    except ValueError as erro:
        st.info(str(erro))
        return
    custo_percentual = st.number_input(
        "Custo por operação (%) para quem só fica comprado à noite",
        0.0,
        2.0,
        CUSTO_PADRAO_POR_OPERACAO * 100,
        0.01,
        format="%.2f",
        key="exp_custo_noite",
    )
    resumo = resumir_noite_e_dia(partes, taxa_livre_de_risco)
    tabela = pd.DataFrame(
        {
            rotulo: {
                "Retorno total": formatar_metrica(
                    "Retorno total", linha["Retorno total"]
                ),
                "Média por dia": formatar_pct(linha["Média por dia"], com_sinal=True),
                "Índice de Sharpe": formatar_metrica(
                    "Sharpe", linha["Índice de Sharpe"]
                ),
                "Dias de alta": formatar_pct(linha["Dias de alta"]),
            }
            for rotulo, linha in resumo.iterrows()
        }
    )
    st.dataframe(tabela, width="stretch")
    liquido = calcular_retorno_da_noite_com_custo(partes, custo_percentual / 100)
    curvas = {
        "Total (comprar e segurar)": (
            1 + (1 + partes["Noite"]) * (1 + partes["Dia"]) - 1
        ).cumprod(),
        "Só a noite": (1 + partes["Noite"]).cumprod(),
        "Só o dia": (1 + partes["Dia"]).cumprod(),
        "Só a noite, com custos": (1 + liquido).cumprod(),
    }
    mostrar_grafico(
        graficos.criar_grafico_curvas_de_capital(
            curvas, 10_000.0, destaque="Total (comprar e segurar)"
        )
    )
    st.caption(
        "Os dados vêm do ativo e do período escolhidos lá em cima. "
        "A curva com custos mostra o que sobra de quem compra no fechamento e vende na abertura "
        "todo dia: são duas operações por dia."
    )


def _experimento_virada_do_mes(dados, taxa_livre_de_risco):
    st.markdown("**Virada do mês: comprado só em torno da troca de mês**")
    st.caption(ajuda_do("Virada do mês"))
    c1, c2, c3 = st.columns(3)
    antes = c1.slider("Últimos dias do mês", 0, 5, 1, key="exp_antes")
    depois = c2.slider("Primeiros dias do mês seguinte", 0, 5, 3, key="exp_depois")
    custo_percentual = c3.number_input(
        "Custo por operação (%)",
        0.0,
        2.0,
        CUSTO_PADRAO_POR_OPERACAO * 100,
        0.01,
        format="%.2f",
        key="exp_custo_virada",
    )
    fechamento = dados["Close"]
    try:
        resultado, marcados = simular_virada_do_mes(
            fechamento, antes, depois, custo_percentual / 100
        )
        dentro_e_fora = comparar_dentro_e_fora(
            ind.calcular_retorno_diario(fechamento).fillna(0.0), marcados
        )
    except ValueError as erro:
        st.info(str(erro))
        return
    referencia = executar_backtest(
        fechamento, pd.Series(1.0, index=fechamento.index), custo_percentual / 100
    )
    numeros = resumir_desempenho(
        resultado.retorno, resultado.posicao, resultado.operacoes, taxa_livre_de_risco
    )
    numeros_referencia = resumir_desempenho(
        referencia.retorno,
        referencia.posicao,
        referencia.operacoes,
        taxa_livre_de_risco,
    )
    cartoes = st.columns(4)
    for coluna, metrica in zip(
        cartoes, ["Retorno total", "Índice de Sharpe", "Maior queda", "Exposição média"]
    ):
        coluna.metric(
            metrica,
            formatar_metrica(metrica, numeros[metrica]),
            delta=f"{formatar_metrica(metrica, numeros_referencia[metrica])} em comprar e segurar",
            delta_color="off",
            delta_arrow="off",
        )
    desejada = marcados.shift(-1, fill_value=False).astype(float)
    try:
        acaso = testar_contra_o_acaso(
            fechamento, desejada, custo_percentual / 100, taxa_livre_de_risco
        )
        st.caption(
            f"Teste contra o acaso: p-valor de {formatar_metrica('Sharpe', acaso.p_valor)}. "
            "Abaixo de 0,05, poucas posições sem relação com o preço fariam igual."
        )
    except ValueError as erro:
        st.caption(str(erro))
    st.caption(
        f"Média por dia dentro da virada: {formatar_pct(dentro_e_fora['Média por dia (dentro)'], com_sinal=True)}; "
        f"fora: {formatar_pct(dentro_e_fora['Média por dia (fora)'], com_sinal=True)}. "
        f"({int(dentro_e_fora['Dias dentro'])} dias dentro e {int(dentro_e_fora['Dias fora'])} fora.)"
    )
    mostrar_grafico(
        graficos.criar_grafico_curvas_de_capital(
            {
                "Só na virada do mês": resultado.curva_de_capital,
                "Comprar e segurar": referencia.curva_de_capital,
            },
            10_000.0,
            destaque="Só na virada do mês",
        )
    )


def secao_experimentos(dados, periodo, taxa_livre_de_risco):
    st.subheader("Experimentos: perguntas clássicas com os seus dados")
    st.caption(
        "Cada experimento responde com o ativo e o período escolhidos lá em cima. "
        "O resultado vale para eles, não para o mercado em geral."
    )
    aba_aporte, aba_rebalancear, aba_noite, aba_virada = st.tabs(
        ["Aporte único × parcelado", "Rebalanceamento", "Noite × dia", "Virada do mês"]
    )
    with aba_aporte:
        _experimento_aporte(dados)
    with aba_rebalancear:
        _experimento_rebalanceamento(dados, periodo, taxa_livre_de_risco)
    with aba_noite:
        _experimento_noite_e_dia(dados, taxa_livre_de_risco)
    with aba_virada:
        _experimento_virada_do_mes(dados, taxa_livre_de_risco)


def secao_sobre():
    st.subheader("Sobre o TickerLab")
    aba_metodo, aba_glossario, aba_estrategias = st.tabs(
        ["Metodologia e limites", "Glossário", "Estratégias"]
    )
    with aba_metodo:
        for titulo, texto in carregar_sobre().items():
            st.markdown(f"#### {titulo}")
            st.markdown(proteger_cifrao(texto))
    with aba_glossario:
        _lista_de_verbetes(
            obter_glossario(), "Buscar no glossário", "sobre_busca_glossario"
        )
    with aba_estrategias:
        _lista_de_verbetes(
            obter_estrategias(), "Buscar nas estratégias", "sobre_busca_estrategias"
        )


def _lista_de_verbetes(verbetes, rotulo_da_busca, chave):
    busca = st.text_input(rotulo_da_busca, key=chave).strip().lower()
    achados = {
        termo: texto
        for termo, texto in verbetes.items()
        if busca in termo.lower() or busca in texto.lower()
    }
    st.caption(f"{len(achados)} de {len(verbetes)} verbetes.")
    for termo, texto in achados.items():
        with st.expander(termo):
            st.markdown(proteger_cifrao(texto))


def secao_momentum(principal, periodo):
    st.subheader("Favoritos e momentum")
    st.caption(
        "Compara o momentum (a tendência recente) do ativo principal e dos seus favoritos. "
        "Marque favoritos com o botão do topo da página."
    )
    favoritos = st.session_state.get("favoritos", [])
    tickers = [principal, *[normalizar_ticker(f) for f in favoritos]]
    tickers = list(dict.fromkeys(tickers))
    if len(tickers) < 2:
        st.info(
            "Favorite alguns ativos para compará-los aqui. Por enquanto só há o principal."
        )
    mostrar_reversao = st.checkbox(
        "Mostrar também a reversão à média (z-score de 20 dias)",
        key="momentum_reversao",
        help=ajuda_do("Reversão à média"),
    )
    fechamentos, sem_dados = {}, []
    for ticker in tickers:
        try:
            fechamentos[ticker] = carregar_dados(ticker, periodo)["Close"]
        except DadosIndisponiveisError:
            sem_dados.append(ticker)
    if sem_dados:
        st.warning(f"Não encontrei dados para: {', '.join(sem_dados)}.")
    try:
        tabela, sem_historico = montar_tabela_de_momentum(fechamentos)
    except ValueError as erro:
        st.info(f"{erro} Escolha o período de 2 ou 5 anos.")
        return
    if sem_historico:
        st.caption(
            f"Sem histórico suficiente (menos de 1 ano): {', '.join(sem_historico)}."
        )
    exibicao = pd.DataFrame(index=tabela.index)
    exibicao["Posição"] = tabela["Posição"].astype(int)
    for coluna in ("1 mês", "3 meses", "6 meses", "12-1 meses"):
        exibicao[coluna] = [formatar_pct(v, com_sinal=True) for v in tabela[coluna]]
    exibicao["Momentum"] = [
        "positivo" if v > 0 else "negativo" for v in tabela["12-1 meses"]
    ]
    if mostrar_reversao:
        exibicao["Z-score (20 dias)"] = [
            formatar_metrica("Sharpe", v) for v in tabela["Z-score (20 dias)"]
        ]
        exibicao["Leitura da reversão"] = [
            "esticado para cima"
            if v > 2
            else "esticado para baixo"
            if v < -2
            else "perto da média"
            for v in tabela["Z-score (20 dias)"]
        ]
    st.dataframe(exibicao, width="stretch")
    mostrar_grafico(graficos.criar_grafico_momentum(tabela["12-1 meses"]))
    st.caption(
        "A posição segue o momentum 12-1 (retorno de 12 meses sem contar o último mês). "
        "Momentum positivo não é recomendação de compra: é um fato do passado. Com "
        "poucos ativos e poucos anos, a ordem muda muito de um período para outro. "
        + (
            "Um z-score acima de +2 ou abaixo de −2 indica um preço bem afastado da média "
            "de 20 dias; a reversão à média aposta que ele volta, o momentum aposta que continua."
            if mostrar_reversao
            else ""
        )
    )


CORES_DOS_REGIMES = {
    "Calmo": graficos.COR_ALTA,
    "Agitado": graficos.COR_QUEDA,
    "Alta": graficos.COR_ALTA,
    "Baixa": graficos.COR_QUEDA,
}


def _escolher_regimes(chave, fechamento):
    """Controles do tipo de regime; devolve (regimes, nomes possíveis, descrição)."""
    criterio = st.radio(
        "Como separar os regimes",
        ["Volatilidade (calmo × agitado)", "Tendência (alta × baixa)"],
        horizontal=True,
        key=f"{chave}_criterio",
        help=ajuda_do("Regime de mercado"),
    )
    if criterio.startswith("Volatilidade"):
        c1, c2 = st.columns(2)
        janela = c1.slider(
            "Janela da volatilidade (dias)", 5, 60, 20, 1, key=f"{chave}_jan_vol"
        )
        percentil = c2.slider(
            "Agitado acima do percentil",
            0.3,
            0.9,
            0.5,
            0.05,
            key=f"{chave}_percentil",
            help="0,5 = a mediana: metade dos dias, em média, é chamada de agitada.",
        )
        regimes = classificar_regimes_de_volatilidade(fechamento, janela, percentil)
        return regimes, REGIMES_DE_VOLATILIDADE, f"volatilidade de {janela} dias"
    janela = st.slider("Média móvel (dias)", 20, 300, 200, 10, key=f"{chave}_jan_tend")
    regimes = classificar_regimes_de_tendencia(fechamento, janela)
    return regimes, REGIMES_DE_TENDENCIA, f"preço contra a média de {janela} dias"


def _tabela_de_regimes(resumo):
    exibicao = pd.DataFrame(index=resumo.index)
    exibicao["Dias"] = resumo["Dias"].astype(int)
    exibicao["% do tempo"] = [formatar_pct(v) for v in resumo["% do tempo"]]
    exibicao["Retorno médio por dia"] = [
        formatar_pct(v, com_sinal=True) for v in resumo["Retorno médio por dia"]
    ]
    exibicao["Retorno anualizado"] = [
        formatar_pct(v, com_sinal=True) for v in resumo["Retorno anualizado"]
    ]
    exibicao["Volatilidade anual"] = [
        formatar_pct(v) for v in resumo["Volatilidade anual"]
    ]
    exibicao["Índice de Sharpe"] = [
        formatar_metrica("Sharpe", v) for v in resumo["Índice de Sharpe"]
    ]
    exibicao["Pior dia"] = [formatar_pct(v) for v in resumo["Pior dia"]]
    return exibicao


def _regimes_do_ativo(dados, taxa_livre_de_risco):
    st.markdown("**Como o ativo se comporta em cada regime**")
    fechamento = dados["Close"]
    regimes, nomes, descricao = _escolher_regimes("reg_ativo", fechamento)
    try:
        resumo = resumir_por_regime(
            ind.calcular_retorno_diario(fechamento).fillna(0.0),
            regimes,
            taxa_livre_de_risco,
        )
    except ValueError as erro:
        st.info(str(erro))
        return
    mostrar_grafico(
        graficos.criar_grafico_regimes(
            fechamento, regimes, {n: CORES_DOS_REGIMES[n] for n in nomes}
        )
    )
    st.dataframe(_tabela_de_regimes(resumo), width="stretch")
    st.caption(
        f"Regime pelo critério: {descricao}. Cada dia é contado no regime da véspera, "
        "que é o que dava para saber antes do pregão. Se a volatilidade for bem maior no "
        "regime agitado e o retorno não compensar, fugir dele pode valer a pena; a próxima "
        "aba testa isso com uma estratégia."
    )


def _escolher_estrategia_simples(chave):
    return st.selectbox(
        "Estratégia (com os parâmetros padrão)",
        list(ESTRATEGIAS),
        index=list(ESTRATEGIAS).index(ESTRATEGIA_DE_REFERENCIA),
        format_func=lambda n: f"{ESTRATEGIAS[n].grupo} · {n}",
        key=f"{chave}_estrategia",
    )


def _custo_do_experimento(chave):
    return (
        st.number_input(
            "Custo por operação (%)",
            0.0,
            2.0,
            CUSTO_PADRAO_POR_OPERACAO * 100,
            0.01,
            format="%.2f",
            key=f"{chave}_custo",
        )
        / 100
    )


def _tabela_de_resultados(resultados, taxa_livre_de_risco, extras=None):
    linhas = {}
    for rotulo, r in resultados.items():
        numeros = resumir_desempenho(
            r.retorno, r.posicao, r.operacoes, taxa_livre_de_risco
        )
        linha = {
            "Retorno total": formatar_metrica(
                "Retorno total", numeros["Retorno total"]
            ),
            "Índice de Sharpe": formatar_metrica("Sharpe", numeros["Índice de Sharpe"]),
            "Maior queda": formatar_metrica("Maior queda", numeros["Maior queda"]),
            "Exposição média": formatar_pct(numeros["Exposição média"]),
        }
        if extras and rotulo in extras:
            linha.update(extras[rotulo])
        linhas[rotulo] = linha
    return pd.DataFrame(linhas).T


def _filtro_por_regime(dados, taxa_livre_de_risco):
    st.markdown("**Operar só em certos regimes**")
    fechamento = dados["Close"]
    nome = _escolher_estrategia_simples("reg_filtro")
    custo = _custo_do_experimento("reg_filtro")
    regimes, nomes, descricao = _escolher_regimes("reg_filtro", fechamento)
    ficar_em = st.multiselect(
        "Ficar comprado nos regimes",
        list(nomes),
        default=[nomes[0]],
        key=f"reg_filtro_ficar_em_{nomes[0]}",
    )
    usar_variancia = st.checkbox(
        "Comparar também a variância gerida (posição menor quando a variância sobe)",
        key="reg_filtro_variancia",
        help=ajuda_do("Variância gerida"),
    )
    try:
        posicao = gerar_posicao(nome, dados)
        filtrada = filtrar_por_regime(posicao, regimes, tuple(ficar_em))
        rotulo_filtrado = f"{nome} só em {' e '.join(ficar_em).lower()}"
        resultados = {
            nome: executar_backtest(fechamento, posicao, custo),
            rotulo_filtrado: executar_backtest(fechamento, filtrada, custo),
        }
        if usar_variancia:
            resultados[f"{nome} com variância gerida"] = executar_backtest(
                fechamento, gerir_pela_variancia(fechamento, posicao), custo
            )
        if nome != ESTRATEGIA_DE_REFERENCIA:
            resultados[ESTRATEGIA_DE_REFERENCIA] = executar_backtest(
                fechamento, pd.Series(1.0, index=fechamento.index), custo
            )
    except ValueError as erro:
        st.info(str(erro))
        return
    mostrar_grafico(
        graficos.criar_grafico_curvas_de_capital(
            {n: r.curva_de_capital for n, r in resultados.items()},
            10_000.0,
            destaque=rotulo_filtrado,
        )
    )
    st.dataframe(
        _tabela_de_resultados(resultados, taxa_livre_de_risco), width="stretch"
    )
    st.caption(
        f"Regimes pelo critério: {descricao}. A decisão do fim do dia vale a partir do dia "
        "seguinte e os limites dos regimes usam só o passado. Filtrar costuma reduzir o risco "
        "e a exposição; se o Sharpe também melhora ou se só se perdeu retorno depende do "
        "ativo e do período, e uma única janela de dados não prova nada."
    )


def _disjuntor(dados, taxa_livre_de_risco):
    st.markdown("**Disjuntor de drawdown: se a estratégia cair demais, para**")
    st.caption(ajuda_do("Disjuntor de drawdown"))
    fechamento = dados["Close"]
    nome = _escolher_estrategia_simples("reg_disj")
    c1, c2, c3 = st.columns(3)
    limite = c1.slider("Dispara com queda de (%)", 3, 40, 15, 1, key="reg_disj_limite")
    pausa = c2.slider("Pausa (dias)", 1, 126, 21, 1, key="reg_disj_pausa")
    with c3:
        custo = _custo_do_experimento("reg_disj")
    try:
        posicao = gerar_posicao(nome, dados)
        disjuntor = aplicar_disjuntor_de_drawdown(
            fechamento, posicao, limite / 100, pausa, custo
        )
        com = executar_backtest(fechamento, disjuntor.posicao, custo)
        sem = executar_backtest(fechamento, posicao, custo)
        varredura = varrer_disjuntor(
            fechamento,
            posicao,
            [0.05, 0.10, 0.20, 0.30],
            [10, 21, 63],
            custo,
            taxa_livre_de_risco,
        )
    except ValueError as erro:
        st.info(str(erro))
        return
    rotulo_com = f"{nome} com disjuntor"
    resultados = {rotulo_com: com, f"{nome} sem disjuntor": sem}
    extras = {
        rotulo_com: {"Disparos": str(len(disjuntor.acionamentos))},
        f"{nome} sem disjuntor": {"Disparos": "0"},
    }
    mostrar_grafico(
        graficos.criar_grafico_disjuntor(
            {n: r.curva_de_capital for n, r in resultados.items()},
            10_000.0,
            rotulo_com,
            disjuntor.acionamentos,
        )
    )
    st.dataframe(
        _tabela_de_resultados(resultados, taxa_livre_de_risco, extras),
        width="stretch",
    )
    st.caption(
        f"O disjuntor ficou {disjuntor.dias_parado} dias travado em caixa. Depois da pausa "
        "o topo é refeito, senão ele dispararia de novo pela mesma queda."
    )
    with st.expander(
        "E se o limite e a pausa fossem outros? (cuidado: é pescar resultado)"
    ):
        exibicao = pd.DataFrame(index=varredura.index)
        exibicao["Retorno total"] = [
            formatar_pct(v, com_sinal=True) for v in varredura["Retorno total"]
        ]
        exibicao["Índice de Sharpe"] = [
            formatar_metrica("Sharpe", v) for v in varredura["Índice de Sharpe"]
        ]
        exibicao["Maior queda"] = [formatar_pct(v) for v in varredura["Maior queda"]]
        exibicao["Disparos"] = varredura["Acionamentos"].astype(int)
        st.dataframe(exibicao, width="stretch")
        st.caption(
            "São 13 linhas testadas no mesmo passado: escolher a melhor é o data snooping "
            "de que falamos na aba Backtest. Olhe o padrão (quanto a queda máxima diminui "
            "e quanto o retorno perde), não o campeão."
        )


def secao_regimes(dados, taxa_livre_de_risco):
    st.subheader("Regimes e disjuntor: o mercado muda de humor")
    st.caption(
        "O mesmo ativo tem fases calmas e fases agitadas. Aqui você vê como ele se "
        "comporta em cada uma, testa uma estratégia que só opera em certas fases e um "
        "disjuntor que a desliga depois de uma queda grande."
    )
    aba_ativo, aba_filtro, aba_disjuntor = st.tabs(
        ["Regimes do ativo", "Estratégia por regime", "Disjuntor de drawdown"]
    )
    with aba_ativo:
        _regimes_do_ativo(dados, taxa_livre_de_risco)
    with aba_filtro:
        _filtro_por_regime(dados, taxa_livre_de_risco)
    with aba_disjuntor:
        _disjuntor(dados, taxa_livre_de_risco)


@st.cache_data(show_spinner="Treinando o modelo (só com o passado de cada data)...")
def calcular_previsoes_do_sinal(dados, tipo, alvo, stop, prazo, mascara_bytes=None):
    """Treino com janela que expande; guardado em cache porque leva alguns segundos."""
    if tipo == "dia":
        conjunto = aprendizado.rotular_proximo_dia(dados)
    else:
        conjunto = aprendizado.rotular_barreira_tripla(dados, alvo, stop, prazo)
    mascara = None
    if mascara_bytes is not None:
        sinal = np.frombuffer(mascara_bytes, dtype=bool)
        mascara = sinal[conjunto.posicao]
    return conjunto, aprendizado.prever_fora_da_amostra(conjunto, mascara=mascara)


def _tabela_de_avaliacao(r):
    return pd.DataFrame(
        {
            "Modelo": [
                formatar_pct(r["Acurácia do modelo"]),
                formatar_metrica("Sharpe", r["AUC"]),
                formatar_metrica("Sharpe", r["Brier do modelo"]),
            ],
            "Previsão ingênua": [
                formatar_pct(r["Acurácia ingênua"]),
                "0,50",
                formatar_metrica("Sharpe", r["Brier ingênuo"]),
            ],
        },
        index=[
            "Acurácia (acertos)",
            "AUC (0,5 = acaso)",
            "Erro de Brier (menor é melhor)",
        ],
    )


def _veredito(r):
    z = r["Diferença em erros-padrão"]
    if z >= 2:
        return (
            f"O modelo acertou {formatar_pct(r['Acurácia do modelo'] - r['Acurácia ingênua'], com_sinal=True)} "
            f"a mais que a previsão ingênua, a {formatar_metrica('Sharpe', z)} erros-padrão. "
            "Isso é raro: desconfie antes de comemorar e confira em outro período e outro ativo."
        )
    return (
        f"A diferença para a previsão ingênua foi de {formatar_metrica('Sharpe', z)} "
        "erros-padrão: dentro do que o acaso produz. O modelo não mostrou saber algo "
        "que o preço passado não esconda."
    )


def _ml_sinal_do_dia(dados, taxa_livre_de_risco):
    st.markdown("**Um modelo consegue prever se amanhã sobe?**")
    st.caption(
        "Regressão logística com 8 variáveis simples (retornos, volatilidade, amplitude, "
        "volume, distância da média). Treina só com o passado de cada data, numa janela que "
        "cresce, e é comparada com a previsão ingênua: sempre apostar no lado mais comum."
    )
    c1, c2 = st.columns(2)
    limiar = c1.slider(
        "Compra se a probabilidade passar de", 0.45, 0.65, 0.5, 0.01, key="ml_limiar"
    )
    with c2:
        custo = _custo_do_experimento("ml_dia")
    try:
        conjunto, previsoes = calcular_previsoes_do_sinal(dados, "dia", 0, 0, 0)
        r = aprendizado.avaliar_previsoes(conjunto.y, previsoes, limiar)
    except ValueError as erro:
        st.info(str(erro))
        return
    st.dataframe(_tabela_de_avaliacao(r), width="stretch")
    st.caption(f"{int(r['Previsões'])} previsões fora da amostra. " + _veredito(r))

    fechamento = dados["Close"]
    posicao = aprendizado.posicao_a_partir_das_probabilidades(
        previsoes["p"], fechamento.index, limiar
    )
    inicio = previsoes["p"].first_valid_index()
    teste = fechamento.loc[inicio:]
    resultados = {
        "Modelo (sinal do dia)": executar_backtest(teste, posicao.loc[inicio:], custo),
        ESTRATEGIA_DE_REFERENCIA: executar_backtest(
            teste, pd.Series(1.0, index=teste.index), custo
        ),
    }
    mostrar_grafico(
        graficos.criar_grafico_curvas_de_capital(
            {n: x.curva_de_capital for n, x in resultados.items()},
            10_000.0,
            destaque="Modelo (sinal do dia)",
        )
    )
    st.dataframe(
        _tabela_de_resultados(resultados, taxa_livre_de_risco), width="stretch"
    )
    try:
        acaso = testar_contra_o_acaso(
            teste, posicao.loc[inicio:], custo, taxa_livre_de_risco
        )
        st.caption(
            f"Teste contra o acaso: p-valor de {formatar_metrica('Sharpe', acaso.p_valor)}. "
            "Abaixo de 0,05, poucas posições sem relação com o preço fariam igual."
        )
    except ValueError as erro:
        st.caption(str(erro))
    st.caption(
        "Só vale o período de teste (depois do primeiro treino). Comprar e segurar é medido "
        "no mesmo período, para a comparação ser justa."
    )


def _ml_barreira_e_meta(dados, taxa_livre_de_risco):
    st.markdown("**Barreira tripla, validação com expurgo e meta-rotulagem**")
    st.caption(ajuda_do("Barreira tripla"))
    c1, c2, c3 = st.columns(3)
    alvo = c1.slider("Alvo (%)", 1, 10, 3, 1, key="ml_alvo")
    stop = c2.slider("Stop (%)", 1, 10, 3, 1, key="ml_stop")
    prazo = c3.slider("Prazo (dias)", 3, 40, 10, 1, key="ml_prazo")
    try:
        conjunto, previsoes = calcular_previsoes_do_sinal(
            dados, "barreira", alvo / 100, stop / 100, prazo
        )
        com = aprendizado.validar_com_expurgo(conjunto, 5, prazo, expurgar=True)
        sem = aprendizado.validar_com_expurgo(conjunto, 5, prazo, expurgar=False)
        r = aprendizado.avaliar_previsoes(conjunto.y, previsoes)
    except ValueError as erro:
        st.info(str(erro))
        return
    st.markdown(
        "*Quanto o modelo acerta se bate o alvo antes do stop (treino que expande)*"
    )
    st.dataframe(_tabela_de_avaliacao(r), width="stretch")
    st.caption(
        f"Em {formatar_pct(r['Fração de 1'])} dos dias o alvo veio antes do stop. "
        + _veredito(r)
    )
    st.markdown("*Validação cruzada em 5 blocos, com e sem expurgo*")
    st.dataframe(
        pd.DataFrame(
            {
                "k-fold comum": [
                    formatar_pct(sem["Acurácia do modelo"]),
                    formatar_metrica("Sharpe", sem["AUC"]),
                ],
                "Com expurgo e embargo": [
                    formatar_pct(com["Acurácia do modelo"]),
                    formatar_metrica("Sharpe", com["AUC"]),
                ],
            },
            index=["Acurácia", "AUC"],
        ),
        width="stretch",
    )
    st.caption(
        "Como cada rótulo olha os próximos dias, exemplos vizinhos do treino e do teste "
        "compartilham o mesmo futuro. O expurgo tira do treino o que encosta no teste e o "
        "embargo deixa uma folga depois dele. Uma diferença grande entre as colunas indica vazamento."
    )

    st.markdown("*Meta-rotulagem: o modelo filtra os sinais de uma regra simples*")
    nome = _escolher_estrategia_simples("ml_meta")
    limiar = st.slider(
        "Age se a probabilidade de sucesso passar de",
        0.4,
        0.7,
        0.5,
        0.01,
        key="ml_meta_limiar",
    )
    custo = _custo_do_experimento("ml_meta")
    fechamento = dados["Close"]
    try:
        base = gerar_posicao(nome, dados)
        sinal = (base > 0).to_numpy()
        conjunto_meta, previsoes_meta = calcular_previsoes_do_sinal(
            dados, "barreira", alvo / 100, stop / 100, prazo, sinal.tobytes()
        )
    except ValueError as erro:
        st.info(str(erro))
        return
    aceitos = previsoes_meta["p"] > limiar
    avaliados = previsoes_meta["p"].notna()
    if avaliados.sum() < 30:
        st.info(
            "Há poucos sinais da regra para treinar o modelo. Use outra regra ou um período maior."
        )
        return
    taxa_geral = conjunto_meta.y[avaliados].mean()
    taxa_aceitos = conjunto_meta.y[aceitos].mean() if aceitos.any() else float("nan")
    meta = base.where(base.index.isin(aceitos[aceitos].index), 0.0)
    inicio = previsoes_meta["p"].first_valid_index()
    teste = fechamento.loc[inicio:]
    resultados = {
        f"{nome} + meta-modelo": executar_backtest(teste, meta.loc[inicio:], custo),
        nome: executar_backtest(teste, base.loc[inicio:], custo),
    }
    if nome != ESTRATEGIA_DE_REFERENCIA:
        resultados[ESTRATEGIA_DE_REFERENCIA] = executar_backtest(
            teste, pd.Series(1.0, index=teste.index), custo
        )
    st.caption(
        f"Dos {int(avaliados.sum())} sinais avaliados, o alvo veio primeiro em "
        f"{formatar_pct(taxa_geral)}; nos {int(aceitos.sum())} que o modelo aceitou, em "
        f"{formatar_pct(taxa_aceitos)}."
    )
    mostrar_grafico(
        graficos.criar_grafico_curvas_de_capital(
            {n: x.curva_de_capital for n, x in resultados.items()},
            10_000.0,
            destaque=f"{nome} + meta-modelo",
        )
    )
    st.dataframe(
        _tabela_de_resultados(resultados, taxa_livre_de_risco), width="stretch"
    )


def _ml_volatilidade(dados, taxa_livre_de_risco):
    st.markdown("**Prever a volatilidade (mais fácil que prever o preço)**")
    st.caption(
        "Regressão linear do log da volatilidade futura nas volatilidades de 5, 20 e 60 dias "
        "(estilo HAR), treinada só com o passado. A base de comparação é dizer que os próximos "
        "dias serão iguais aos últimos 20."
    )
    c1, c2, c3 = st.columns(3)
    horizonte = c1.slider("Prever os próximos (dias)", 5, 42, 21, 1, key="ml_horizonte")
    alvo = c2.slider("Alvo de volatilidade (% ao ano)", 5, 40, 15, 1, key="ml_alvo_vol")
    with c3:
        custo = _custo_do_experimento("ml_vol")
    try:
        r = aprendizado.prever_volatilidade(dados, horizonte)
    except ValueError as erro:
        st.info(str(erro))
        return
    m = r.metricas
    cartoes = st.columns(3)
    cartoes[0].metric(
        "Erro do modelo (log)",
        formatar_metrica("Sharpe", m["Erro do modelo (log)"]),
        delta=f"{formatar_metrica('Sharpe', m['Erro ingênuo (log)'])} na previsão ingênua",
        delta_color="off",
        delta_arrow="off",
    )
    cartoes[1].metric(
        "Melhora sobre a ingênua",
        formatar_pct(m["Melhora sobre o ingênuo"], com_sinal=True),
    )
    cartoes[2].metric(
        "Correlação com o que veio",
        formatar_metrica("Sharpe", m["Correlação do modelo"]),
        delta=f"{formatar_metrica('Sharpe', m['Correlação ingênua'])} na ingênua",
        delta_color="off",
        delta_arrow="off",
    )
    mostrar_grafico(
        graficos.criar_grafico_volatilidade_prevista(r.prevista, r.ingenua, r.realizada)
    )
    fechamento = dados["Close"]
    inicio = r.prevista.index[0]
    teste = fechamento.loc[inicio:]
    posicoes = {
        "Alvo com a volatilidade prevista": aprendizado.posicao_pelo_alvo_de_volatilidade(
            r.prevista, fechamento.index, alvo / 100
        ),
        "Alvo com a volatilidade dos últimos 20 dias": aprendizado.posicao_pelo_alvo_de_volatilidade(
            r.ingenua, fechamento.index, alvo / 100
        ),
    }
    resultados = {
        n: executar_backtest(teste, p.loc[inicio:], custo) for n, p in posicoes.items()
    }
    resultados[ESTRATEGIA_DE_REFERENCIA] = executar_backtest(
        teste, pd.Series(1.0, index=teste.index), custo
    )
    mostrar_grafico(
        graficos.criar_grafico_curvas_de_capital(
            {n: x.curva_de_capital for n, x in resultados.items()},
            10_000.0,
            destaque="Alvo com a volatilidade prevista",
        )
    )
    st.dataframe(
        _tabela_de_resultados(resultados, taxa_livre_de_risco), width="stretch"
    )
    st.caption(
        "A volatilidade é persistente (dias agitados vêm em sequência), por isso é bem mais "
        "previsível que o sinal do preço. O erro do modelo costuma cair em relação aos "
        "últimos 20 dias porque ele corrige o nível (a volatilidade tende a voltar à média), "
        "mas a correlação com o que veio quase não melhora. Sem alavancagem (no máximo 100%)."
    )


def secao_aprendizado(dados, taxa_livre_de_risco):
    st.subheader("Aprendizado de máquina honesto")
    st.warning(
        "Aprendizado de máquina aumenta muito o risco de overfitting. Aqui o modelo sempre "
        "treina só com o passado e é medido contra uma previsão ingênua. É normal ele não vencer."
    )
    aba_dia, aba_barreira, aba_vol = st.tabs(
        ["Sinal do dia", "Barreira tripla e meta-rotulagem", "Volatilidade"]
    )
    with aba_dia:
        _ml_sinal_do_dia(dados, taxa_livre_de_risco)
    with aba_barreira:
        _ml_barreira_e_meta(dados, taxa_livre_de_risco)
    with aba_vol:
        _ml_volatilidade(dados, taxa_livre_de_risco)


PARES_PADRAO = "ITUB4, BBDC4, BBAS3, PETR4, PETR3"


def _tabela_de_pares(tabela):
    exibicao = pd.DataFrame(index=tabela.index)
    exibicao["Correlação"] = [
        formatar_metrica("Sharpe", v) for v in tabela["Correlação"]
    ]
    exibicao["Beta"] = [formatar_metrica("Sharpe", v) for v in tabela["Beta"]]
    exibicao["ADF no treino"] = [
        formatar_metrica("Sharpe", v) for v in tabela["ADF no treino"]
    ]
    exibicao["Meia-vida (dias)"] = [
        "—" if not np.isfinite(v) else f"{v:.0f}" for v in tabela["Meia-vida (dias)"]
    ]
    exibicao["Ligado no treino?"] = [
        "Sim" if v else "Não" for v in tabela["Cointegrado no treino"]
    ]
    exibicao["ADF no teste"] = [
        formatar_metrica("Sharpe", v) for v in tabela["ADF no teste"]
    ]
    exibicao["Continuou no teste?"] = [
        "Sim" if v else "Não" for v in tabela["Continuou no teste"]
    ]
    return exibicao


def secao_pares(periodo, taxa_livre_de_risco):
    st.subheader("Pairs trading: apostar que dois ativos voltam a andar juntos")
    st.caption(ajuda_do("Pairs trading"))
    st.warning(
        "Este é um desafio educativo. A perna vendida exige aluguel de ações, que tem custo e "
        "nem sempre está disponível; esse custo não entra na simulação. Resultado do passado "
        "não garante nada."
    )
    with st.container(border=True):
        texto = st.text_input(
            f"Ativos (2 a {MAX_ATIVOS_PARA_PARES}, separados por vírgula)",
            value=PARES_PADRAO,
            key="pares_ativos",
            help="O app testa todos os pares possíveis da lista.",
        )
        c1, c2 = st.columns(2)
        fracao = c1.slider(
            "Parte do período usada para estimar (treino)",
            0.3,
            0.8,
            0.5,
            0.05,
            key="pares_treino",
            help="A relação entre os ativos é estimada só nesta parte; a negociação acontece no resto.",
        )
        custo = (
            c2.number_input(
                "Custo por operação (%)",
                0.0,
                2.0,
                CUSTO_PADRAO_POR_OPERACAO * 100,
                0.01,
                format="%.2f",
                key="pares_custo",
            )
            / 100
        )
    tickers = interpretar_tickers(texto)
    if not 2 <= len(tickers) <= MAX_ATIVOS_PARA_PARES:
        st.info(
            f"Escolha de 2 a {MAX_ATIVOS_PARA_PARES} ativos (agora são {len(tickers)})."
        )
        return
    fechamentos, sem_dados = {}, []
    for ticker in tickers:
        try:
            fechamentos[ticker] = carregar_dados(ticker, periodo)["Close"]
        except DadosIndisponiveisError:
            sem_dados.append(ticker)
    if sem_dados:
        st.warning(
            f"Não encontrei dados para: {', '.join(sem_dados)}. Eles ficaram de fora."
        )
    if len(fechamentos) < 2:
        st.info("Não há ativos suficientes com dados.")
        return
    alinhado, _ = alinhar_fechamentos(fechamentos)
    try:
        tabela = procurar_pares(alinhado, fracao)
    except ValueError as erro:
        st.info(str(erro))
        return
    st.markdown("**Todos os pares da lista**")
    st.dataframe(_tabela_de_pares(tabela), width="stretch")
    sobreviventes = int(tabela["Cointegrado no treino"].sum())
    continuaram = int(
        (tabela["Cointegrado no treino"] & tabela["Continuou no teste"]).sum()
    )
    st.caption(
        f"{len(tabela)} pares testados; {sobreviventes} pareceram ligados no treino e "
        f"{continuaram} continuaram ligados no teste. ADF abaixo de −3,34 indica relação "
        "(valor aproximado de Engle-Granger a 5%). Ao testar muitos pares, uns 5% parecem "
        "ligados só por sorte: por isso a conferência no teste."
    )

    par = st.selectbox("Par para simular", list(tabela.index), key="pares_escolhido")
    a, b = par.split(" × ")
    c1, c2, c3, c4 = st.columns(4)
    entrada = c1.slider(
        "Entra com |z| acima de", 1.0, 3.0, 2.0, 0.1, key="pares_entrada"
    )
    saida = c2.slider("Sai com |z| abaixo de", 0.0, 1.0, 0.5, 0.1, key="pares_saida")
    stop = c3.slider("Stop com |z| acima de", 3.0, 6.0, 4.0, 0.5, key="pares_stop")
    janela = c4.slider("Janela do z-score (dias)", 20, 120, 60, 5, key="pares_janela")
    try:
        r = simular_par(
            alinhado[a], alinhado[b], fracao, entrada, saida, stop, janela, custo
        )
    except ValueError as erro:
        st.info(str(erro))
        return
    bt = r.backtest
    numeros = resumir_desempenho(
        bt.retorno, bt.posicao, bt.operacoes, taxa_livre_de_risco
    )
    cartoes = st.columns(4)
    for coluna, metrica in zip(
        cartoes, ["Retorno total", "Índice de Sharpe", "Maior queda", "Operações"]
    ):
        coluna.metric(metrica, formatar_metrica(metrica, numeros[metrica]))
    oferecer_salvar_simulacao(
        "pares",
        f"Par {a} × {b} · {periodo}",
        {m: formatar_metrica(m, v) for m, v in numeros.items()},
        f"{alinhado.index[-1]:%d/%m/%Y}",
    )
    meia = r.treino.meia_vida
    st.caption(
        f"Relação estimada no treino: log {a} = {formatar_metrica('Sharpe', r.treino.beta)} × log {b} + constante. "
        f"Meia-vida do spread no treino: {'sem volta' if not np.isfinite(meia) else f'{meia:.0f} dias'}. "
        f"ADF: {formatar_metrica('Sharpe', r.treino.adf)} no treino e "
        f"{formatar_metrica('Sharpe', r.teste.adf)} no teste "
        f"({'a relação continuou' if r.teste.cointegrado else 'a relação NÃO se confirmou no teste'})."
    )
    mostrar_grafico(
        graficos.criar_grafico_z_do_par(r.z, r.lado, entrada, stop, r.inicio_do_teste)
    )
    teste_a = alinhado[a].loc[r.inicio_do_teste :]
    teste_b = alinhado[b].loc[r.inicio_do_teste :]
    mostrar_grafico(
        graficos.criar_grafico_curvas_de_capital(
            {
                f"Par {a} × {b}": bt.curva_de_capital,
                f"Comprar e segurar {a}": teste_a / teste_a.iloc[0],
                f"Comprar e segurar {b}": teste_b / teste_b.iloc[0],
            },
            10_000.0,
            destaque=f"Par {a} × {b}",
        )
    )
    st.caption(
        "O par é neutro ao mercado: não depende de os preços subirem. Compare o retorno e a "
        "queda com os dois ativos sozinhos, no mesmo período de teste. Se o ADF do teste não "
        "confirma a relação, o lucro (se houve) provavelmente foi sorte."
    )


ATIVOS_PADRAO_DA_CARTEIRA = "PETR4, VALE3, ITUB4, WEGE3, ABEV3"


def _ativos_padrao_da_carteira():
    """A lista de exemplo, cortada para caber no limite de ativos do plano."""
    ativos = ATIVOS_PADRAO_DA_CARTEIRA.split(", ")
    return ", ".join(ativos[: limites_do(plano_atual()).ativos_na_carteira])


def _controles_da_estrategia(estrategia, chave):
    """Sliders dos parâmetros de uma estratégia de carteira."""
    valores = {}
    if estrategia.parametros:
        colunas = st.columns(min(len(estrategia.parametros), 3))
        for posicao, p in enumerate(estrategia.parametros):
            valores[p.nome] = colunas[posicao % len(colunas)].slider(
                p.rotulo,
                p.minimo,
                p.maximo,
                p.padrao,
                p.passo,
                key=f"{chave}_{p.nome}",
                help=p.ajuda or None,
            )
    return valores


def secao_carteira(periodo, taxa_livre_de_risco, cdi_diario):
    st.subheader("Carteira: várias ações ao mesmo tempo")
    st.caption(
        "Cada estratégia decide no último pregão do mês quanto colocar em cada ativo; o que "
        "não está nos ativos fica em caixa. Entre uma decisão e outra, os pesos variam com os "
        "preços, como numa carteira de verdade."
    )
    with st.container(border=True):
        texto = st.text_input(
            f"Ativos ({MIN_ATIVOS_NA_CARTEIRA} a {MAX_ATIVOS_NA_CARTEIRA}, separados por vírgula)",
            value=_ativos_padrao_da_carteira(),
            key="carteira_ativos",
            help="O primeiro ativo da lista é o canário da estratégia de mesmo nome.",
        )
        nome = st.selectbox(
            "Estratégia", list(ESTRATEGIAS_DE_CARTEIRA), key="carteira_estrategia"
        )
        parametros = _controles_da_estrategia(
            ESTRATEGIAS_DE_CARTEIRA[nome], f"carteira_{nome}"
        )
        col_custo, col_caixa = st.columns(2)
        custo_percentual = col_custo.number_input(
            "Custo por operação (%)",
            min_value=0.0,
            max_value=2.0,
            value=CUSTO_PADRAO_POR_OPERACAO * 100,
            step=0.01,
            format="%.2f",
            key="carteira_custo",
            help=ajuda_do("Custo de operação"),
        )
        caixa_rende_cdi = col_caixa.checkbox(
            "O dinheiro parado rende o CDI",
            key="carteira_caixa_cdi",
            help=ajuda_do("CDI"),
        )

    tickers = interpretar_tickers(texto)
    if not MIN_ATIVOS_NA_CARTEIRA <= len(tickers) <= MAX_ATIVOS_NA_CARTEIRA:
        st.info(
            f"Escolha de {MIN_ATIVOS_NA_CARTEIRA} a {MAX_ATIVOS_NA_CARTEIRA} ativos "
            f"(agora são {len(tickers)})."
        )
        return
    limite_de_ativos = limites_do(plano_atual()).ativos_na_carteira
    if len(tickers) > limite_de_ativos:
        st.info(
            f"O plano {limites_do(plano_atual()).nome} aceita até {limite_de_ativos} ativos "
            f"na carteira (agora são {len(tickers)}). O plano Pro aceita "
            f"{limites_do('pro').ativos_na_carteira}."
        )
        return
    fechamentos, sem_dados = {}, []
    for ticker in tickers:
        try:
            fechamentos[ticker] = carregar_dados(ticker, periodo)["Close"]
        except DadosIndisponiveisError:
            sem_dados.append(ticker)
    if sem_dados:
        st.warning(
            f"Não encontrei dados para: {', '.join(sem_dados)}. Eles ficaram de fora."
        )
    if len(fechamentos) < MIN_ATIVOS_NA_CARTEIRA:
        st.info("Não há ativos suficientes com dados.")
        return
    alinhado, descartados = alinhar_fechamentos(fechamentos)
    if len(alinhado) < 60:
        st.warning(
            f"Só há {len(alinhado)} dias em comum entre os ativos. Tente um período mais longo."
        )
        return

    retorno_do_caixa = None
    if caixa_rende_cdi:
        try:
            cdi = cdi_diario
            if cdi is None:
                cdi = obter_cdi(alinhado.index[0], alinhado.index[-1])
            retorno_do_caixa = (
                curva_do_cdi(cdi, alinhado.index).pct_change().fillna(0.0)
            )
        except CDIIndisponivelError as erro:
            st.warning(f"{erro} O dinheiro parado ficou sem render.")

    custo = custo_percentual / 100
    try:
        principal = simular_carteira(
            nome, alinhado, custo, retorno_do_caixa, **parametros
        )
        referencia = simular_carteira(
            "Pesos iguais (referência)", alinhado, custo, retorno_do_caixa
        )
    except ValueError as erro:
        st.error(str(erro))
        return

    explicacao = obter_estrategias().get(nome)
    if explicacao:
        with st.expander("Como funciona esta estratégia", expanded=True):
            st.markdown(proteger_cifrao(explicacao))

    carteiras = {nome: principal}
    if nome != "Pesos iguais (referência)":
        carteiras["Pesos iguais (referência)"] = referencia
    numeros = {
        rotulo: resumir_desempenho(r.retorno, r.exposicao, None, taxa_livre_de_risco)
        for rotulo, r in carteiras.items()
    }
    sem_estrategia = pd.Series(1.0, index=alinhado.index)
    for ativo in alinhado.columns:
        retorno_do_ativo = ind.calcular_retorno_diario(alinhado[ativo])
        numeros[f"{NOMES_AMIGAVEIS.get(ativo, ativo)} (comprar e segurar)"] = (
            resumir_desempenho(
                retorno_do_ativo, sem_estrategia, None, taxa_livre_de_risco
            )
        )

    cartoes = st.columns(4)
    for coluna, metrica in zip(
        cartoes, ["Retorno total", "Índice de Sharpe", "Maior queda", "Exposição média"]
    ):
        coluna.metric(
            metrica,
            formatar_metrica(metrica, numeros[nome][metrica]),
            delta=(
                f"{formatar_metrica(metrica, numeros['Pesos iguais (referência)'][metrica])} "
                "em pesos iguais"
                if nome != "Pesos iguais (referência)"
                else None
            ),
            delta_color="off",
            delta_arrow="off",
        )
    anos = len(alinhado) / ind.DIAS_POR_ANO
    st.caption(
        f"Giro de {formatar_pct(principal.giro / anos)} do capital por ano "
        "(tudo o que foi comprado e vendido, dividido pelos anos do período)."
    )
    oferecer_salvar_simulacao(
        "carteira",
        f"{nome} · {', '.join(alinhado.columns)} · {periodo}",
        {m: formatar_metrica(m, v) for m, v in numeros[nome].items()},
        f"{alinhado.index[-1]:%d/%m/%Y}",
    )

    curvas = {rotulo: r.curva_de_capital for rotulo, r in carteiras.items()}
    escolhidos = st.multiselect(
        "Mostrar também (comprar e segurar)",
        list(alinhado.columns),
        key="carteira_ativos_no_grafico",
    )
    for ativo in escolhidos:
        curvas[f"{NOMES_AMIGAVEIS.get(ativo, ativo)} (comprar e segurar)"] = (
            alinhado[ativo] / alinhado[ativo].iloc[0]
        )
    mostrar_grafico(
        graficos.criar_grafico_curvas_de_capital(curvas, 10_000.0, destaque=nome)
    )
    mostrar_grafico(graficos.criar_grafico_pesos(principal.pesos))

    st.markdown("**Números lado a lado**")
    st.dataframe(
        pd.DataFrame(
            {
                rotulo: {m: formatar_metrica(m, v) for m, v in valores.items()}
                for rotulo, valores in numeros.items()
            }
        ),
        width="stretch",
    )
    st.caption(
        f"Feito em {len(alinhado)} dias em comum ({descartados} descartados por feriados "
        "diferentes). Cuidado: a lista de ativos foi escolhida hoje, entre empresas que "
        "sobreviveram (*viés de sobrevivência*), e com poucos ativos o resultado depende "
        "muito de quais você escolheu."
    )


@st.cache_data(show_spinner="Rodando todas as estratégias...")
def calcular_ranking(dados, custo, taxa, extras):
    return montar_ranking(dados, custo, taxa, extras)


def secao_ranking(dados, taxa_livre_de_risco):
    st.subheader("Ranking: todas as estratégias no mesmo ativo")
    st.caption(
        "Cada estratégia roda com os valores padrão, sem proteções, e é ordenada pelo Sharpe. "
        "Olhar só o topo da lista é o jeito mais fácil de se enganar: leia as duas colunas "
        "que descontam a sorte."
    )
    col_custo, col_extras = st.columns(2)
    custo_percentual = col_custo.number_input(
        "Custo por operação (%)",
        min_value=0.0,
        max_value=2.0,
        value=CUSTO_PADRAO_POR_OPERACAO * 100,
        step=0.01,
        format="%.2f",
        key="ranking_custo",
    )
    extras = col_extras.number_input(
        "Outras ideias que você já testou (opcional)",
        min_value=0,
        max_value=10_000,
        value=0,
        step=10,
        key="ranking_extras",
        help=ajuda_do("Data snooping (ir pescando resultados)"),
    )
    tabela, resultados = calcular_ranking(
        dados, custo_percentual / 100, taxa_livre_de_risco, int(extras)
    )
    st.caption(f"{len(tabela) + int(extras)} tentativas contadas.")

    exibicao = tabela.copy()
    for coluna in exibicao.columns:
        if coluna != "Grupo":
            exibicao[coluna] = [formatar_metrica(coluna, v) for v in exibicao[coluna]]
    st.dataframe(exibicao, width="stretch")
    st.caption(
        "**Chance de não ser sorte:** Sharpe deflacionado (acima de 95% é convincente). "
        "**p-valor (acaso):** fatia de posições sem relação com o preço que fez igual ou "
        "melhor (abaixo de 5% é convincente)."
    )

    mostrar_grafico(
        graficos.criar_grafico_risco_retorno(tabela, destaque=ESTRATEGIA_DE_REFERENCIA)
    )
    padrao = [ESTRATEGIA_DE_REFERENCIA] + [
        n for n in tabela.index if n != ESTRATEGIA_DE_REFERENCIA
    ][:2]
    escolhidas = st.multiselect(
        "Curvas de capital",
        list(tabela.index),
        default=padrao,
        key="ranking_curvas",
    )
    if escolhidas:
        mostrar_grafico(
            graficos.criar_grafico_curvas_de_capital(
                {n: resultados[n].curva_de_capital for n in escolhidas},
                10_000.0,
                destaque=escolhidas[0],
            )
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


def secao_backtest(dados, taxa_livre_de_risco, cdi_diario=None):
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
        cartoes, ["Retorno total", "Índice de Sharpe", "Maior queda", "Operações"]
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
    )
    st.download_button(
        "Baixar as curvas de capital (CSV)",
        converter_para_csv(montar_tabela_de_curvas(curvas, capital_inicial)),
        file_name="curvas_de_capital.csv",
        mime="text/csv",
        key="baixar_curvas_backtest",
    )

    with st.expander("Mais números: Ômega, Kelly e quanto histórico seria preciso"):
        retorno_principal = resultado.retorno
        omega = calcular_omega(retorno_principal)
        kelly = calcular_kelly(retorno_principal)
        dias_minimos = calcular_comprimento_minimo(
            retorno_principal, 0.95, 0.0, taxa_livre_de_risco
        )
        c1, c2, c3 = st.columns(3)
        c1.metric(
            "Ômega",
            "—" if pd.isna(omega) else formatar_metrica("Sharpe", omega),
            help=ajuda_do("Ômega"),
        )
        c2.metric(
            "Meio Kelly (fração do capital)",
            "—" if pd.isna(kelly) else formatar_pct(kelly / 2),
            help=ajuda_do("Critério de Kelly"),
        )
        if pd.isna(dias_minimos):
            texto_dias = "—"
        elif dias_minimos == float("inf"):
            texto_dias = "nunca (Sharpe não passa de zero)"
        else:
            texto_dias = f"{dias_minimos / ind.DIAS_POR_ANO:.1f} anos".replace(".", ",")
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

    if descontar_imposto:
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

    if not resultado.operacoes.empty:
        with st.expander(f"Ver as {len(resultado.operacoes)} operações"):
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
    )

    st.warning(
        "Cuidado: o passado não garante o futuro. Uma regra que funcionou aqui pode ter sido "
        "ajustada ao acaso (*overfitting*); o app usa só ativos que existem hoje (*viés de "
        "sobrevivência*); e os custos reais podem ser maiores que os simulados."
    )


# --- Páginas ----------------------------------------------------------------
PAGINAS_DO_MENU.recomecar()  # o menu desta sessão, refeito a cada execução (telas/comum.py)
PREFIXOS_QUE_SOBREVIVEM_A_TROCA_DE_PAGINA = (
    "backtest_",
    "parametro_",
    "custo_",
    "liga_",
    "valor_",
    "espera_depois_do_stop",
    "carteira_",
    "pares_",
    "validacao_",
    "exp_",
    "corr_",
    "momentum_",
    "reg_",
    "ml_",
    "ranking_",
    "relatorio_",  # Report Studio (os botões usam "estudio_", que não pode ser reatribuído)
)
CAMPOS_DO_TOPO_QUE_SOBREVIVEM = (
    "ticker",
    "periodo",
    "taxa",
    "em_reais",
    "usar_exemplo",
)


def manter_estado():
    """Evita que o Streamlit esqueça os campos ao trocar de página.

    Ele apaga o valor de todo campo que não aparece na página atual. Reatribuir o valor a cada
    execução o mantém (só vale para campos com `key`).
    """
    for chave in list(st.session_state.keys()):
        if chave in CAMPOS_DO_TOPO_QUE_SOBREVIVEM or chave.startswith(
            PREFIXOS_QUE_SOBREVIVEM_A_TROCA_DE_PAGINA
        ):
            st.session_state[chave] = st.session_state[chave]


def mostrar_topo(usuario):
    """A conta (ou o aviso de modo local) à direita; a marca fica no canto do menu."""
    _, col_conta = st.columns([5, 2], vertical_alignment="center")
    with col_conta:
        if usuario is not None:
            mostrar_conta(usuario)
        else:
            st.markdown(":gray-badge[Modo local · sem login]")


def _analisar_o_ativo_do_inicio():
    simbolo = catalogo.resolver(st.session_state.get("ativo_do_inicio"))
    if simbolo:
        st.session_state["ticker"] = simbolo
        st.session_state["ir_para_visao_geral"] = True
        marcar_feito("escolheu_ativo")


def _analisar_o_atalho(chave):
    simbolo = st.session_state.get(chave)
    if simbolo:
        st.session_state["ticker"] = simbolo
        st.session_state["ir_para_visao_geral"] = True
        marcar_feito("escolheu_ativo")


# --- Tutorial por objetivo (blueprint, seção 4) ---------------------------------------------
def _guardar_na_conta(chave, valor):
    """Grava uma preferência na conta, sem apagar as outras (sem conta, fica só na sessão)."""
    usuario = st.session_state.get("usuario")
    if usuario is None:
        return
    try:
        with obter_engine().begin() as conexao:
            atuais = carregar_preferencias(conexao, usuario.id)
            salvar_preferencias(conexao, usuario.id, {**atuais, chave: valor})
    except Exception:
        logging.getLogger(__name__).exception("Falha ao salvar a preferência %s", chave)


def _preparar_o_estudio(tipo, modelo=relatorios.EXECUTIVO):
    st.session_state["tipo_de_relatorio"] = tipo
    st.session_state["relatorio_modelo"] = modelo
    _aplicar_secoes(tipo, relatorios.secoes_do_modelo(tipo, modelo))
    st.session_state.pop("relatorio_gerado", None)


def _comecar_tutorial(objetivo):
    st.session_state["tutorial"] = {"objetivo": objetivo, "passo": 0}
    if objetivo == tutorial.CARTEIRA:
        _preparar_o_estudio(relatorios.MINHA_CARTEIRA, relatorios.COMPLETO)
        st.session_state["tutorial_ir_para"] = "relatorio"
    elif objetivo == tutorial.RELATORIO:
        _preparar_o_estudio(relatorios.ATIVO)
        st.session_state["tutorial_ir_para"] = "relatorio"


def _encerrar_tutorial(concluiu):
    st.session_state.pop("tutorial", None)
    st.session_state["tutorial_visto"] = True
    _guardar_na_conta("tutorial_visto", True)
    if concluiu:
        st.toast(
            "Tutorial concluído. Dá para reabrir na página inicial.",
            icon=":material/school:",
        )


def _reabrir_tutorial():
    st.session_state["tutorial_visto"] = False
    st.session_state.pop("tutorial", None)
    st.session_state.pop("checklist_escondido", None)


def _andar_no_tutorial(passo):
    estado = st.session_state["tutorial"]
    total = len(tutorial.passos(estado["objetivo"]))
    novo = estado["passo"] + passo
    if novo >= total:
        _encerrar_tutorial(concluiu=True)
        return
    estado["passo"] = max(0, novo)
    atual = tutorial.passo_atual(estado["objetivo"], estado["passo"])
    if (
        atual.chave == "gere"
    ):  # o passo do relatório já abre o estúdio no modelo Executivo
        _preparar_o_estudio(relatorios.ATIVO)
        st.session_state["tutorial_ir_para"] = "relatorio"


def _ir_pelo_tutorial(chave_da_pagina):
    if (
        chave_da_pagina == "relatorio"
        and st.session_state.get("tutorial", {}).get("objetivo") == tutorial.ANALISAR
    ):
        _preparar_o_estudio(relatorios.ATIVO)
    st.session_state["tutorial_ir_para"] = chave_da_pagina


def _explicar_dois_numeros(c):
    """A mini-lição do passo "Leia dois números", com os números do ativo aberto."""
    total = float(ind.calcular_retorno_acumulado(c.retorno).iloc[-1])
    queda = float(ind.calcular_drawdown(c.fechamento).min())
    rotulo = PERIODOS_DO_TOPO.get(c.periodo, c.periodo)
    st.markdown(
        f"- **Retorno total ({formatar_pct(total, com_sinal=True)}):** quem comprou {c.ticker} no "
        f"primeiro dia dos últimos {rotulo} e vendeu no último teria essa variação, antes de "
        "impostos e custos.\n"
        f"- **Maior queda ({formatar_pct(queda)}):** em algum momento, quem tinha "
        "comprado no topo chegou a ver esse prejuízo no papel. É uma medida do susto, não "
        "do resultado final.\n\n"
        "Os dois descrevem o **passado**: não dizem o que vai acontecer."
    )


def mostrar_tutorial(pagina_atual, c=None):
    """A faixa do tutorial: passo atual, progresso, o que falta e os botões (sem bloquear a
    tela: a pessoa continua usando tudo normalmente)."""
    destino = st.session_state.pop("tutorial_ir_para", None)
    if destino and destino != pagina_atual:
        st.switch_page(PAGINAS_DO_MENU[destino])
    estado = st.session_state.get("tutorial")
    if not estado:
        return
    objetivo = tutorial.OBJETIVOS[estado["objetivo"]]
    roteiro = tutorial.passos(objetivo.chave)
    passo = tutorial.passo_atual(objetivo.chave, estado["passo"])
    feitos = acoes_feitas()
    cumprido = tutorial.pode_continuar(passo, feitos)
    with st.container(border=True, key="tl-tutorial"):
        st.caption(
            f"Tutorial · {objetivo.nome_do_roteiro} · passo {estado['passo'] + 1} de "
            f"{len(roteiro)}"
        )
        st.progress((estado["passo"] + 1) / len(roteiro))
        st.markdown(f"**{passo.titulo}**")
        st.markdown(passo.texto)
        if passo.chave == "explore" and c is not None and pagina_atual == "visao_geral":
            if st.button(
                "Mostrar como ler", icon=":material/lightbulb:", key="tut_ler"
            ):
                marcar_feito("leu_os_numeros")
                cumprido = True
            if "leu_os_numeros" in acoes_feitas():
                _explicar_dois_numeros(c)
        if passo.chave == "pronto" and objetivo.chave == tutorial.ANALISAR:
            col_fav, col_outro = st.columns(2)
            ticker = normalizar_ticker(st.session_state.get("ticker", ""))
            if ticker not in st.session_state.get("favoritos", []):
                col_fav.button(
                    f"Adicionar {ticker} aos favoritos",
                    icon=":material/star:",
                    key="tut_favoritar",
                    on_click=_alternar_favorito_atual,
                )
            col_outro.button(
                "Analisar outro ativo",
                icon=":material/search:",
                key="tut_outro",
                on_click=_ir_pelo_tutorial,
                args=("inicio",),
            )
        if not cumprido:
            st.caption(f"Falta: {passo.pendente}")
            if passo.pagina != pagina_atual:
                st.button(
                    f"Ir para {pagina(passo.pagina).titulo}",
                    icon=":material/arrow_forward:",
                    key="tut_ir",
                    on_click=_ir_pelo_tutorial,
                    args=(passo.pagina,),
                )
        col_voltar, col_seguir, col_pular = st.columns([1, 1, 1])
        col_voltar.button(
            "Voltar",
            icon=":material/arrow_back:",
            key="tut_voltar",
            disabled=estado["passo"] == 0,
            on_click=_andar_no_tutorial,
            args=(-1,),
            width="stretch",
        )
        ultimo = estado["passo"] == len(roteiro) - 1
        col_seguir.button(
            "Concluir" if ultimo else "Continuar",
            type="primary",
            icon=":material/check:" if ultimo else ":material/arrow_forward:",
            key="tut_seguir",
            disabled=not cumprido,
            on_click=_andar_no_tutorial,
            args=(1,),
            width="stretch",
        )
        col_pular.button(
            "Pular tutorial",
            key="tut_pular",
            on_click=_encerrar_tutorial,
            args=(False,),
            width="stretch",
        )
    destino = st.session_state.pop("tutorial_ir_para", None)
    if destino and destino != pagina_atual:
        st.switch_page(PAGINAS_DO_MENU[destino])


def mostrar_portas_de_entrada():
    """'O que você quer fazer hoje?': três objetivos, não três níveis técnicos."""
    st.subheader("O que você quer fazer hoje?")
    for i, (coluna, objetivo) in enumerate(
        zip(st.columns(3), tutorial.OBJETIVOS.values(), strict=True)
    ):
        with coluna, st.container(border=True, height=176, key=f"tl-cartao-porta-{i}"):
            st.markdown(f"#### {objetivo.icone} {objetivo.titulo}")
            st.caption(objetivo.descricao)
            st.button(
                "Começar",
                key=f"tut_porta_{objetivo.chave}",
                icon=":material/play_arrow:",
                on_click=_comecar_tutorial,
                args=(objetivo.chave,),
            )
    st.button(
        "Pular: já sei usar",
        key="tut_pular_portas",
        on_click=_encerrar_tutorial,
        args=(False,),
        type="tertiary",
    )


def mostrar_lista_de_tarefas():
    """Três primeiras ações, discretas; some quando tudo foi feito ou quando a pessoa esconde."""
    if st.session_state.get("checklist_escondido"):
        return
    feitos = acoes_feitas()
    if not tutorial.tarefas_pendentes(feitos):
        return
    with st.container(border=True, key="tl-primeiros-passos"):
        col_titulo, col_esconder = st.columns([4, 1], vertical_alignment="center")
        col_titulo.markdown(
            f"**Primeiros passos** · {len(tutorial.TAREFAS) - len(tutorial.tarefas_pendentes(feitos))} "
            f"de {len(tutorial.TAREFAS)}"
        )
        if col_esconder.button("Esconder", key="tut_esconder", type="tertiary"):
            st.session_state["checklist_escondido"] = True
            st.rerun()
        for tarefa in tutorial.TAREFAS:
            if tarefa.chave in feitos:
                st.markdown(f":material/check_circle: ~~{tarefa.rotulo}~~")
            else:
                st.page_link(
                    PAGINAS_DO_MENU[tarefa.pagina],
                    label=tarefa.rotulo,
                    icon=":material/radio_button_unchecked:",
                )


def pagina_inicio():
    if st.session_state.pop("ir_para_visao_geral", False):
        st.switch_page(PAGINAS_DO_MENU["visao_geral"])
    mostrar_tutorial("inicio")
    st.markdown(
        '<div class="tl-olho">Ações da B3 e dos EUA</div>', unsafe_allow_html=True
    )
    st.markdown(
        '<div class="tl-hero">Entenda uma ação antes de investir.</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        "Retorno, risco e testes de estratégia **no passado**, com custos e cada número "
        "explicado em português: passe o mouse no **?**."
    )
    col_ativo, col_analisar, col_guia = st.columns(
        [3, 1, 1], vertical_alignment="bottom"
    )
    col_ativo.selectbox(
        "Busque código ou empresa",
        catalogo.simbolos(),
        index=None,
        format_func=catalogo.rotulo,
        key="ativo_do_inicio",
        placeholder="PETR4, Petrobras, AAPL, Ibovespa…",
        accept_new_options=True,
        on_change=_analisar_o_ativo_do_inicio,
        help="Escolha na lista para abrir a análise. Não precisa saber o sufixo .SA.",
    )
    col_analisar.button(
        "Analisar ativo",
        type="primary",
        key="comecar",
        width="stretch",
        on_click=_analisar_o_ativo_do_inicio,
    )
    recentes = st.session_state.get("recentes", [])
    st.pills(
        "Recentes" if recentes else "Experimente",
        recentes or list(catalogo.EXEMPLOS),
        format_func=lambda s: catalogo.rotulo(s).split(" · ")[0],
        key="atalho_do_inicio",
        on_change=_analisar_o_atalho,
        args=("atalho_do_inicio",),
    )
    col_guia.page_link(
        PAGINAS_DO_MENU["guia"], label="Ver o guia", icon=":material/menu_book:"
    )

    if not st.session_state.get("tutorial") and not st.session_state.get(
        "tutorial_visto"
    ):
        mostrar_portas_de_entrada()
    mostrar_lista_de_tarefas()

    st.subheader("O que dá para fazer")
    cartoes = [
        (
            ":material/dashboard:",
            "Analisar ativo",
            "Retorno, risco e comportamento de uma ação, índice ou cripto.",
            "visao_geral",
            None,
        ),
        (
            ":material/history:",
            "Testar estratégia",
            "Repita uma regra de compra e venda no passado, com custos.",
            "backtest",
            None,
        ),
        (
            ":material/picture_as_pdf:",
            "Gerar relatório",
            "Um PDF com os números, os gráficos e cada termo explicado.",
            "relatorio",
            None,
        ),
        (
            ":material/account_balance_wallet:",
            "Minha carteira (B3)",
            "Envie a planilha da Área do Investidor e veja concentração e risco.",
            "relatorio",
            relatorios.MINHA_CARTEIRA,
        ),
    ]
    for i, (coluna, (icone, titulo, texto, destino, tipo)) in enumerate(
        zip(st.columns(4), cartoes, strict=True)
    ):
        with coluna, st.container(border=True, height=196, key=f"tl-cartao-{i}"):
            st.markdown(f"#### {icone} {titulo}")
            st.caption(texto)
            if tipo is None:
                st.page_link(
                    PAGINAS_DO_MENU[destino],
                    label="Abrir",
                    icon=":material/arrow_forward:",
                )
            else:
                atalho_para_o_relatorio(tipo, rotulo="Abrir", chave=f"inicio_{tipo}")

    st.subheader("Como o TickerLab trabalha")
    principios = [
        ("Sem olhar o futuro", "A decisão de um dia só vale no dia seguinte."),
        ("Com custos", "Corretagem, impostos e o CDI entram em todo teste."),
        ("Honesto", "O app mostra quando uma estratégia não funciona."),
        ("Explicado", "Cada termo técnico vem com uma explicação em português."),
    ]
    for coluna, (titulo, texto) in zip(st.columns(4), principios, strict=True):
        coluna.markdown(
            f'<div class="tl-principio"><b>{titulo}</b>{texto}</div>',
            unsafe_allow_html=True,
        )

    if st.session_state.get("usuario") is not None:
        limites = limites_do(plano_atual())
        st.divider()
        st.info(
            f"Você está no plano **{limites.nome}**. "
            "Veja o que cada plano inclui em **Planos e assinatura**."
        )
        st.page_link(
            PAGINAS_DO_MENU["planos"],
            label="Planos e assinatura",
            icon=":material/workspace_premium:",
        )
    if st.session_state.get("tutorial_visto") and not st.session_state.get("tutorial"):
        st.button(
            "Reabrir o tutorial",
            icon=":material/school:",
            key="tut_reabrir",
            type="tertiary",
            on_click=_reabrir_tutorial,
        )


# --- Funções das páginas (as que ainda não saíram para telas/) -----------------------------


def pagina_relatorio():
    cabecalho_da_pagina("relatorio")
    c = carregar_contexto()
    # o lugar da faixa fica no topo, mas ela é desenhada no fim: assim já enxerga o que o
    # estúdio acabou de fazer (prévia pronta, carteira carregada) e libera o "Continuar"
    lugar_do_tutorial = st.container()
    usuario = st.session_state.get("usuario")
    limites = limites_do(plano_atual())
    aba_estudio, aba_biblioteca = st.tabs(
        [":material/edit_document: Estúdio", ":material/folder_open: Meus relatórios"]
    )
    with aba_estudio:
        mostrar_estudio(usuario, limites, c)
    with aba_biblioteca:
        mostrar_biblioteca(usuario)
    with lugar_do_tutorial:
        mostrar_tutorial("relatorio", c)


def pagina_trade():
    fase = trade.fase_atual()
    st.markdown(
        f'<span class="tl-estado">Em pesquisa · fase {fase.codigo}</span>',
        unsafe_allow_html=True,
    )
    cabecalho_da_pagina("trade")
    st.markdown(
        "Uma pesquisa de **trading quantitativo**: modelos de aprendizado de máquina testados "
        "em mais de 80 ativos (ações, índices, moedas, juros, commodities e cripto), com regras "
        "de aprovação **escritas antes de olhar os resultados**. Só se um modelo passar, ele "
        "vira um robô numa **conta de demonstração** do MetaTrader 5, sem dinheiro de verdade. "
        "Resultado negativo também é publicado."
    )
    fases = "".join(
        f'<div class="tl-fase {f.estado}"><b>{f.codigo}'
        f"{' ✓' if f.estado == trade.FEITA else ' ●' if f.estado == trade.AGORA else ''}"
        f"</b>{f.nome}</div>"
        for f in trade.FASES
    )
    st.markdown(f'<div class="tl-fases">{fases}</div>', unsafe_allow_html=True)
    st.caption(f"Agora: {fase.nome}. {fase.explicacao}")

    st.subheader("Downloads")
    for coluna, item in zip(
        st.columns(len(trade.DOWNLOADS)), trade.DOWNLOADS, strict=True
    ):
        with coluna, st.container(border=True):
            st.markdown(f"**{item.titulo}**")
            st.caption(item.descricao)
            st.button(
                "Disponível no fim do projeto",
                key=f"download_{item.titulo}",
                disabled=not item.disponivel,
                width="stretch",
            )
    st.warning(
        "É uma pesquisa educacional. Nada aqui é recomendação de investimento, e nenhum teste "
        "garante rentabilidade.",
        icon=":material/info:",
    )


def pagina_guia():
    cabecalho_da_pagina("guia")
    secao_sobre()


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


def pagina_backtest():
    cabecalho_da_pagina("backtest")
    c = carregar_contexto()
    atalho_para_o_relatorio(relatorios.BACKTEST)
    secao_backtest(c.dados, c.taxa_livre_de_risco, c.cdi_diario)


def pagina_ranking():
    cabecalho_da_pagina("ranking")
    c = carregar_contexto()
    secao_ranking(c.dados, c.taxa_livre_de_risco)


def pagina_carteira():
    cabecalho_da_pagina("carteira")
    c = carregar_contexto()
    atalho_para_o_relatorio(relatorios.CARTEIRA)
    secao_carteira(c.periodo, c.taxa_livre_de_risco, c.cdi_diario)


def pagina_experimentos():
    cabecalho_da_pagina("experimentos")
    c = carregar_contexto()
    secao_experimentos(c.dados, c.periodo, c.taxa_livre_de_risco)


def pagina_regimes():
    cabecalho_da_pagina("regimes")
    c = carregar_contexto()
    secao_regimes(c.dados, c.taxa_livre_de_risco)


def pagina_aprendizado():
    cabecalho_da_pagina("aprendizado")
    if not exigir_recurso(APRENDIZADO_DE_MAQUINA):
        return
    c = carregar_contexto()
    secao_aprendizado(c.dados, c.taxa_livre_de_risco)


def pagina_pares():
    cabecalho_da_pagina("pares")
    if not exigir_recurso(PARES):
        return
    c = carregar_contexto()
    secao_pares(c.periodo, c.taxa_livre_de_risco)


def pagina_momentum():
    cabecalho_da_pagina("momentum")
    c = carregar_contexto()
    secao_momentum(c.ticker, c.periodo)


def pagina_simulacoes():
    cabecalho_da_pagina("simulacoes")
    secao_minhas_simulacoes()


# --- Menu: a função de cada página ----------------------------------------------------------
FUNCOES_DAS_PAGINAS = {
    "inicio": pagina_inicio,
    "relatorio": pagina_relatorio,
    "parametros": pagina_parametros,
    "research": pagina_research,
    "fundamentos": pagina_fundamentos,
    "por_dentro": pagina_por_dentro,
    "donos": pagina_donos,
    "newsletter": pagina_newsletter,
    "alertas": pagina_alertas,
    "carteira_research": pagina_carteira_research,
    "trade": pagina_trade,
    "guia": pagina_guia,
    "termos": pagina_termos,
    "privacidade": pagina_privacidade,
    "visao_geral": pagina_visao_geral,
    "risco": pagina_risco,
    "retorno_mensal": pagina_retorno_mensal,
    "comparar": pagina_comparar,
    "correlacao": pagina_correlacao,
    "backtest": pagina_backtest,
    "ranking": pagina_ranking,
    "carteira": pagina_carteira,
    "experimentos": pagina_experimentos,
    "regimes": pagina_regimes,
    "aprendizado": pagina_aprendizado,
    "pares": pagina_pares,
    "simulacoes": pagina_simulacoes,
    "meus_dados": pagina_meus_dados,
    "admin": pagina_admin,
    "momentum": pagina_momentum,
    "planos": pagina_planos,
}


def montar_navegacao(e_admin=False):
    """O menu do topo: um grupo por seção; páginas do Pro ganham cadeado no plano Gratuito."""
    plano = plano_atual()
    estrutura = {}
    for grupo in GRUPOS:
        itens = []
        for p in paginas_do_grupo(grupo):
            if p.somente_admin and not e_admin:
                continue
            bloqueada = p.recurso is not None and not pode_usar(plano, p.recurso)
            e_a_inicial = p.chave == PAGINA_INICIAL
            pagina_do_menu = st.Page(
                FUNCOES_DAS_PAGINAS[p.chave],
                title=p.titulo,
                icon=":material/lock:" if bloqueada else p.icone,
                url_path="" if e_a_inicial else p.url,
                default=e_a_inicial,
                visibility="visible" if p.no_menu else "hidden",
            )
            PAGINAS_DO_MENU[p.chave] = pagina_do_menu
            itens.append(pagina_do_menu)
        if itens:
            estrutura[grupo] = itens
    return estrutura


# --- Programa principal --------------------------------------------------------
usuario_logado = obter_usuario_logado()
carregar_da_conta(usuario_logado)
preparar_estado_inicial()
manter_estado()
pagina_atual = st.navigation(
    montar_navegacao(e_admin=bool(usuario_logado and usuario_logado.e_admin)),
    position="top",
)
mostrar_topo(usuario_logado)
if usuario_logado is not None:
    if st.session_state.pop("primeira_vez", False):
        st.toast(
            f"Bem-vindo ao TickerLab, {usuario_logado.nome or usuario_logado.email}!"
        )
    mostrar_retorno_do_pagamento()
pagina_atual.run()

st.divider()
col_aviso, col_guia, col_termos, col_privacidade = st.columns(
    [5, 1, 1.2, 1.2], vertical_alignment="center"
)
col_aviso.markdown(
    '<div class="tl-rodape"><b>Ticker<span>Lab</span></b> · projeto educacional, não é '
    "recomendação de investimento. Dados do Yahoo Finance, que podem ter atraso ou erros. "
    "Rentabilidade passada não garante resultado futuro.</div>",
    unsafe_allow_html=True,
)
col_guia.page_link(PAGINAS_DO_MENU["guia"], label="Guia")
col_termos.page_link(PAGINAS_DO_MENU["termos"], label="Termos de uso")
col_privacidade.page_link(PAGINAS_DO_MENU["privacidade"], label="Privacidade")
