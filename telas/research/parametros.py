"""Research: Parâmetros (etapa 1c): os parâmetros do usuário, o efeito nos números e o histórico.

Saiu do `app.py` sem mudar comportamento. Regra de `telas/`: nenhum estado mutável no módulo
(um módulo importado é do processo inteiro, isto é, de todos os usuários).
"""

import logging

import pandas as pd
import streamlit as st

from src import analise as research_analise
from src import parametros as research_parametros
from src import presets as research_presets
from src import relatorios
from src.banco.conexao import obter_engine
from src.banco.dados_do_usuario import historico_do_preset, salvar_preset
from src.cdi import CDIIndisponivelError, calcular_taxa_anual_do_cdi
from src.dados import DadosIndisponiveisError, normalizar_ticker
from src.planos import LimiteDoPlanoError, conferir_parametros_por_ativo
from telas.comum import (
    ROTULOS_DAS_OPCOES,
    _formatar_parametro,
    _presets_guardados,
    cabecalho_da_pagina,
    carregar_contexto,
    carregar_dados_de,
    formatar_pct,
    obter_cdi,
)
from telas.conta.guarda import conta_da_sessao_valendo

NOMES_DOS_ESCOPOS_NA_TELA = {
    research_presets.GLOBAL: "Seu padrão (todos os ativos)",
    research_presets.ATIVO: "Só para o ativo do topo",
}


DOMINIOS_QUE_JA_MUDAM_NUMEROS = ("quant", "tecnica")


def _chave_do_campo(escopo, alvo, versao, chave):
    return f"rp_{escopo}_{alvo or 'todos'}_{versao}_{chave}"


def _valor_do_campo(parametro, valor):
    """Converte o que o campo devolve para o tipo do catálogo (sem validar limites)."""
    if parametro.tipo == "temas":
        return tuple(t for t in parametro.opcoes if t in (valor or ()))
    if parametro.tipo == "inteiro" and isinstance(valor, float) and valor.is_integer():
        return int(valor)
    return valor


def _campo_do_parametro(parametro, chave_do_campo, inicial):
    """O campo certo para cada tipo: número, lista de opções ou seleção de temas."""
    if chave_do_campo not in st.session_state:
        st.session_state[chave_do_campo] = (
            list(inicial) if parametro.tipo == "temas" else inicial
        )
    rotulo = parametro.rotulo + (f" ({parametro.unidade})" if parametro.unidade else "")
    if parametro.tipo == "temas":
        st.multiselect(
            rotulo,
            list(parametro.opcoes),
            format_func=lambda o: ROTULOS_DAS_OPCOES.get(o, o),
            key=chave_do_campo,
            help=parametro.ajuda,
        )
    elif parametro.tipo == "escolha" or parametro.opcoes:
        st.selectbox(
            rotulo,
            list(parametro.opcoes),
            format_func=lambda o: ROTULOS_DAS_OPCOES.get(o, str(o)),
            key=chave_do_campo,
            help=parametro.ajuda,
        )
    elif parametro.tipo == "inteiro":
        st.number_input(
            rotulo,
            min_value=int(parametro.minimo),
            max_value=int(parametro.maximo),
            step=1,
            key=chave_do_campo,
            help=parametro.ajuda,
        )
    else:
        st.number_input(
            rotulo,
            min_value=float(parametro.minimo),
            max_value=float(parametro.maximo),
            step=0.1,
            format="%.2f",
            key=chave_do_campo,
            help=parametro.ajuda,
        )


def _restaurar_campo(chave_do_campo, valor):
    st.session_state[chave_do_campo] = (
        list(valor) if isinstance(valor, tuple) else valor
    )


def _aplicar_pronto(campos, herdado):
    """Põe nos campos os valores de um modo de leitura pronto (o resto volta ao herdado)."""
    pronto = research_presets.PRESETS_PRONTOS.get(st.session_state.get("rp_pronto"))
    if pronto is None:
        return
    for chave, chave_do_campo in campos.items():
        _restaurar_campo(chave_do_campo, pronto.parametros.get(chave, herdado[chave]))


def _descartar(campos):
    for chave_do_campo in campos.values():
        st.session_state.pop(chave_do_campo, None)


def _gravar(usuario, escopo, alvo, valores, motivo):
    """Grava uma versão nova (na conta, ou na sessão no modo local). Devolve o número ou None."""
    if usuario is None:
        atuais = list(st.session_state.get("presets_locais", []))
        anterior = next(
            (p for p in atuais if p.escopo == escopo and p.alvo == alvo), None
        )
        versao = (anterior.versao + 1) if anterior else 1
        novo = research_presets.Preset(
            escopo=escopo, alvo=alvo, versao=versao, parametros=valores
        )
        research_presets.conferir_ao_salvar(atuais, novo)
        st.session_state["presets_locais"] = research_presets.substituir(atuais, novo)
        return versao
    if not conta_da_sessao_valendo(usuario):
        return None
    with obter_engine().begin() as conexao:
        return salvar_preset(
            conexao,
            usuario.id,
            escopo,
            alvo,
            valores,
            plano=usuario.plano,
            motivo=motivo,
        )


def _formatar_metrica(metrica):
    if not metrica.disponivel:
        return "indisponível"
    valor = metrica.valor
    if metrica.unidade == "fração":
        return formatar_pct(valor)
    casas = 1 if metrica.unidade == "pontos" else 2
    return f"{valor:,.{casas}f}".replace(",", "#").replace(".", ",").replace("#", ".")


@st.cache_data(ttl=3600, show_spinner=False)
def _fechamento_do_indice(indice, periodo, exemplo, em_reais):
    """O fechamento do índice; `em_reais` entra na chave do cache (achado 5b do Codex, 17/10):
    sem isso, o índice ficava na moeda da 1ª chamada e o ativo na da opção marcada."""
    try:
        return carregar_dados_de(indice, periodo, em_reais)["Close"]
    except (DadosIndisponiveisError, ValueError):
        return None


def _taxa_do_cdi(c):
    try:
        return calcular_taxa_anual_do_cdi(
            c.cdi_diario
            if c.cdi_diario is not None
            else obter_cdi(c.dados.index[0], c.dados.index[-1]),
            c.dados.index,
        )
    except (
        CDIIndisponivelError,
        ValueError,
    ):  # sem CDI: Sharpe e Sortino ficam indisponíveis
        return None


def _analisar_com(c, resolucao):
    indice = resolucao["quant.benchmark"]
    benchmark = _fechamento_do_indice(
        indice,
        c.periodo,
        bool(st.session_state.get("usar_exemplo")),
        bool(st.session_state.get("em_reais")),
    )
    cdi = _taxa_do_cdi(c) if resolucao["quant.taxa_livre_de_risco"] == "cdi" else None
    return research_analise.analisar_ativo(c.ticker, c.dados, resolucao, cdi, benchmark)


def mostrar_efeito(c, salvo, rascunho):
    """A × B: o que muda nos parâmetros e nos números do ativo do topo, antes de salvar."""
    st.subheader(f"Efeito em {c.ticker}")
    diferencas = salvo.comparar(rascunho)
    if not diferencas:
        st.caption(
            "Nada mudou ainda. Mexa num parâmetro e a comparação aparece aqui, antes de salvar."
        )
    else:
        nomes = {p.chave: p.rotulo for p in research_parametros.PARAMETROS}
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Parâmetro": nomes[d.chave],
                        "Em vigor (A)": _formatar_parametro(d.chave, d.valor_a),
                        "Com as mudanças (B)": _formatar_parametro(d.chave, d.valor_b),
                    }
                    for d in diferencas
                ]
            ),
            hide_index=True,
            width="stretch",
        )
    a, b = _analisar_com(c, salvo), _analisar_com(c, rascunho)
    linhas = []
    for chave, metrica in a.metricas.items():
        nova = b[chave]
        linhas.append(
            {
                "Métrica": nova.nome,
                "Em vigor (A)": _formatar_metrica(metrica),
                "Com as mudanças (B)": _formatar_metrica(nova),
                "Mudou": "●"
                if (metrica.valor != nova.valor or metrica.nome != nova.nome)
                else "",
            }
        )
    st.dataframe(pd.DataFrame(linhas), hide_index=True, width="stretch")
    indisponiveis = [m for m in b.metricas.values() if not m.disponivel]
    for m in indisponiveis:
        st.caption(f"**{m.nome}** indisponível: {m.motivo}")
    p = b.proveniencia
    st.caption(
        f"Dados: {p.fonte}, de {p.inicio:%d/%m/%Y} a {p.fim:%d/%m/%Y} ({p.pregoes} pregões), "
        f"em {p.moeda}, {p.ajuste}. Execução {b.id_da_execucao} · parâmetros "
        f"{p.assinatura_dos_parametros}."
    )


def mostrar_historico(usuario, escopo, alvo):
    if usuario is None:
        return
    try:
        with obter_engine().connect() as conexao:
            versoes = historico_do_preset(conexao, usuario.id, escopo, alvo)
    except Exception:
        logging.getLogger(__name__).exception("Falha ao ler o histórico")
        return
    if not versoes:
        return
    nomes = {p.chave: p.rotulo for p in research_parametros.PARAMETROS}
    with st.expander(f"Histórico de versões ({len(versoes)})"):
        for i, v in enumerate(versoes):
            mudados = (
                ", ".join(
                    f"{nomes.get(k, k)} {_formatar_parametro(k, tuple(x) if isinstance(x, list) else x)}"
                    for k, x in v.parametros.items()
                )
                or "tudo no padrão"
            )
            col_texto, col_botao = st.columns([5, 1], vertical_alignment="center")
            col_texto.markdown(
                f"**v{v.versao}** · {v.criado_em.astimezone(relatorios.FUSO):%d/%m/%Y %H:%M}"
                f" · {mudados}" + (f" · _{v.motivo}_" if v.motivo else "")
            )
            if i > 0:
                col_botao.button(
                    "Voltar a esta",
                    key=f"rpb_voltar_{escopo}_{v.versao}",
                    on_click=_voltar_versao,
                    args=(usuario, escopo, alvo, v),
                )


def _voltar_versao(usuario, escopo, alvo, versao):
    try:
        nova = _gravar(
            usuario, escopo, alvo, versao.parametros, f"volta à versão {versao.versao}"
        )
    except (ValueError, LimiteDoPlanoError) as erro:
        st.session_state["rp_erro"] = str(erro)
        return
    if nova:
        st.toast(f"Versão {nova} criada com os valores da versão {versao.versao}.")


def _campos_por_dominio(campos, proprio, herdado):
    """Uma aba por domínio com os campos; devolve o que difere do herdado (o rascunho)."""
    rascunho_valores = {}
    abas = st.tabs(
        [research_parametros.DOMINIOS[d] for d in research_parametros.DOMINIOS]
    )
    for aba, dominio in zip(abas, research_parametros.DOMINIOS, strict=True):
        with aba:
            if dominio == "fundamentalista":
                st.caption(
                    "Usados na página Fundamentos (horizonte, ROIC mínimo e P/L máximo). A "
                    "janela dos proventos entra numa próxima etapa."
                )
            elif dominio not in DOMINIOS_QUE_JA_MUDAM_NUMEROS:
                st.caption(
                    "Estes parâmetros serão usados pelo Research (eventos e newsletter) nas "
                    "próximas etapas; por enquanto não mudam números."
                )
            for parametro in research_parametros.PARAMETROS:
                if parametro.dominio != dominio:
                    continue
                chave_do_campo = campos[parametro.chave]
                inicial = (proprio.parametros if proprio else {}).get(
                    parametro.chave, herdado[parametro.chave]
                )
                col_campo, col_origem = st.columns([3, 2], vertical_alignment="bottom")
                with col_campo:
                    _campo_do_parametro(parametro, chave_do_campo, inicial)
                valor = _valor_do_campo(parametro, st.session_state[chave_do_campo])
                if valor != herdado[parametro.chave]:
                    rascunho_valores[parametro.chave] = valor
                    col_origem.button(
                        "Restaurar",
                        key=f"rpb_restaurar_{chave_do_campo}",
                        icon=":material/undo:",
                        help=f"Voltar a {_formatar_parametro(parametro.chave, herdado[parametro.chave])} "
                        f"({herdado.efetivos[parametro.chave].nome_da_origem.lower()}).",
                        on_click=_restaurar_campo,
                        args=(chave_do_campo, herdado[parametro.chave]),
                    )
                else:
                    col_origem.caption(
                        f"Vem de: {herdado.efetivos[parametro.chave].nome_da_origem.lower()}"
                    )
    return rascunho_valores


def _validar_rascunho(guardados, escopo, alvo, versao, rascunho_valores, salvo, ticker):
    """(rascunho resolvido, problemas): confere o rascunho como se fosse salvo."""
    # valida o rascunho inteiro (tipo, limites e as regras entre parâmetros)
    problemas = []
    rascunho = salvo
    try:
        novo = research_presets.Preset(
            escopo=escopo, alvo=alvo, versao=versao + 1, parametros=rascunho_valores
        )
        research_presets.conferir_ao_salvar(guardados, novo)
        rascunho = research_presets.resolver(
            research_presets.substituir(guardados, novo), ticker=ticker
        )
    except research_presets.CombinacaoInvalidaError as erro:
        problemas = erro.problemas
    except ValueError as erro:
        problemas = [str(erro)]
    return rascunho, problemas


def pagina_parametros():
    cabecalho_da_pagina("parametros")
    c = carregar_contexto()
    usuario = st.session_state.get("usuario")
    plano = usuario.plano if usuario is not None else None
    if usuario is None:
        st.info(
            "Modo local: os parâmetros valem só nesta sessão. Entre com a sua conta para "
            "guardá-los e ter o histórico de versões.",
            icon=":material/info:",
        )
    escopo = st.segmented_control(
        "Onde estes parâmetros valem",
        list(NOMES_DOS_ESCOPOS_NA_TELA),
        format_func=lambda e: (
            f"Só para {c.ticker}"
            if e == research_presets.ATIVO
            else NOMES_DOS_ESCOPOS_NA_TELA[e]
        ),
        default=research_presets.GLOBAL,
        required=True,
        key="rp_escopo",
    )
    alvo = normalizar_ticker(c.ticker) if escopo == research_presets.ATIVO else None
    guardados = _presets_guardados(usuario)
    proprio = next(
        (p for p in guardados if p.escopo == escopo and p.alvo == alvo), None
    )
    versao = proprio.versao if proprio else 0
    # o que vale sem este escopo (é para onde "Restaurar" volta)
    sem_este = [p for p in guardados if p is not proprio]
    try:
        herdado = research_presets.resolver(sem_este, ticker=c.ticker)
        salvo = research_presets.resolver(guardados, ticker=c.ticker)
    except ValueError as erro:
        st.error(
            f"Os parâmetros guardados não combinam mais: {erro} Restaure algum deles."
        )
        herdado = salvo = research_presets.resolver([])
    pode_salvar, motivo_do_bloqueio = True, ""
    if escopo == research_presets.ATIVO and plano is not None:
        try:
            conferir_parametros_por_ativo(
                plano,
                len([p for p in guardados if p.escopo == research_presets.ATIVO]),
                ja_tem_este=proprio is not None,
            )
        except LimiteDoPlanoError as erro:
            pode_salvar, motivo_do_bloqueio = False, str(erro)
    if erro_anterior := st.session_state.pop("rp_erro", None):
        st.error(erro_anterior)

    campos = {
        p.chave: _chave_do_campo(escopo, alvo, versao, p.chave)
        for p in research_parametros.PARAMETROS
    }
    col_pronto, col_aplicar = st.columns([3, 1], vertical_alignment="bottom")
    col_pronto.selectbox(
        "Começar de um modo de leitura",
        list(research_presets.PRESETS_PRONTOS),
        format_func=lambda k: (
            f"{research_presets.PRESETS_PRONTOS[k].nome}: "
            f"{research_presets.PRESETS_PRONTOS[k].enfatiza}"
        ),
        index=None,
        placeholder="Visão equilibrada, Longo prazo, Renda e proventos…",
        key="rp_pronto",
        help="Modos de leitura, não perfis de risco nem recomendação. Tudo continua editável.",
    )
    col_aplicar.button(
        "Aplicar",
        key="rpb_aplicar",
        on_click=_aplicar_pronto,
        args=(campos, herdado),
        disabled=not st.session_state.get("rp_pronto"),
        width="stretch",
    )

    rascunho_valores = _campos_por_dominio(campos, proprio, herdado)

    rascunho, problemas = _validar_rascunho(
        guardados, escopo, alvo, versao, rascunho_valores, salvo, c.ticker
    )
    for problema in problemas:
        st.error(problema)
    mudou = rascunho_valores != (proprio.parametros if proprio else {})

    with st.container(key="tl-barra-parametros"):
        col_motivo, col_salvar, col_descartar = st.columns(
            [3, 1, 1], vertical_alignment="bottom"
        )
        motivo = col_motivo.text_input(
            "Motivo da mudança (opcional)",
            key=f"rp_motivo_{escopo}_{versao}",
            placeholder="Ex.: testar RSI mais lento",
            max_chars=200,
        )
        salvar = col_salvar.button(
            "Salvar",
            type="primary",
            icon=":material/save:",
            key="rpb_salvar",
            disabled=not mudou or bool(problemas) or not pode_salvar,
            width="stretch",
        )
        col_descartar.button(
            "Descartar",
            key="rpb_descartar",
            on_click=_descartar,
            args=(campos,),
            disabled=not mudou,
            width="stretch",
        )
    if motivo_do_bloqueio:
        st.info(motivo_do_bloqueio, icon=":material/workspace_premium:")
    if salvar:
        try:
            nova = _gravar(usuario, escopo, alvo, rascunho_valores, motivo)
        except (ValueError, LimiteDoPlanoError) as erro:
            st.error(f"Não salvei: {erro}")
        except Exception:
            logging.getLogger(__name__).exception("Falha ao salvar os parâmetros")
            st.error("Não consegui salvar agora. Tente de novo em instantes.")
        else:
            if nova:
                st.toast(f"Versão {nova} salva.", icon=":material/check_circle:")
            st.rerun()
    mostrar_efeito(c, salvo, rascunho)
    mostrar_historico(usuario, escopo, alvo)
