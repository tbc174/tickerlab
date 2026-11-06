"""Biblioteca ("Meus relatórios"): reabrir, versões, PDF original e exclusão.

Saiu do `app.py` sem mudar comportamento. Regra de `telas/`: nenhum estado mutável no módulo
(um módulo importado é do processo inteiro, isto é, de todos os usuários).
"""

import functools
import logging

import streamlit as st

from src import estilos_pdf, relatorios
from src.banco.conexao import obter_engine
from src.banco.dados_do_usuario import biblioteca_de_relatorios, excluir_relatorio
from src.banco.pdfs_originais import (
    DIAS_GUARDADO,
    baixar_pdf_original,
    pdfs_guardados,
    pode_guardar,
)
from src.banco.usuarios import esta_valendo
from src.planos import limites_do
from telas.compartilhar import compartilhar_pdf
from telas.comum import PAGINAS_DO_MENU, PERIODOS_DO_TOPO
from telas.conta.guarda import so_com_a_conta_valendo
from telas.relatorios.estudio import NOMES_DOS_MODELOS, _aplicar_secoes

ABRIR_O_RELATORIO_DA_EMPRESA = "biblioteca_abrir_relatorio_empresa"
CAMPOS_PARA_REABRIR = {
    "comparar_com": "relatorio_comparar_com",
    "estrategia": "relatorio_estrategia",
    "custo": "relatorio_custo",
    "ativos": "relatorio_carteira_ativos",
    "estrategia_carteira": "relatorio_carteira",
    "carteira_de_exemplo": "relatorio_carteira_exemplo",
    "lista": "relatorio_newsletter_lista",
    "janela": "relatorio_newsletter_janela",
}


def _reabrir(relatorio):
    """Põe o tipo, os dados e a configuração do relatório de volta no estúdio (o da empresa
    volta para a página dele, com o mesmo ticker)."""
    p = relatorio.parametros
    tipo = relatorio.tipo
    if tipo == relatorios.EMPRESA:
        st.session_state["ticker"] = p.get("ticker", st.session_state.get("ticker"))
        st.session_state[ABRIR_O_RELATORIO_DA_EMPRESA] = True
        return
    st.session_state["tipo_de_relatorio"] = tipo
    if p.get("ticker"):
        st.session_state["ticker"] = p["ticker"]
    if p.get("periodo") in PERIODOS_DO_TOPO:
        st.session_state["periodo"] = p["periodo"]
    for chave, campo in CAMPOS_PARA_REABRIR.items():
        if chave in p:
            st.session_state[campo] = p[chave]
    modelo = p.get("modelo")
    st.session_state["relatorio_modelo"] = (
        modelo if modelo in NOMES_DOS_MODELOS else relatorios.COMPLETO
    )
    st.session_state["relatorio_estilo"] = estilos_pdf.estilo(p.get("estilo")).chave
    _aplicar_secoes(tipo, p.get("secoes") or None)
    st.session_state.pop("relatorio_gerado", None)
    aviso = (
        " Envie de novo a planilha da B3: ela não fica guardada."
        if tipo == relatorios.MINHA_CARTEIRA and not p.get("carteira_de_exemplo")
        else ""
    )
    st.toast(
        f"Configuração de “{relatorio.titulo}” carregada na aba Estúdio.{aviso}",
        icon=":material/restore:",
    )


@so_com_a_conta_valendo
def _excluir(usuario, relatorio_id):
    try:
        with obter_engine().begin() as conexao:
            excluiu = excluir_relatorio(conexao, usuario.id, relatorio_id)
    except Exception:
        logging.getLogger(__name__).exception("Falha ao excluir o relatório")
        st.toast("Não consegui excluir agora.", icon=":material/error:")
        return
    if excluiu:
        st.toast("Relatório excluído da biblioteca.", icon=":material/delete:")


def _versoes(itens):
    """O número da versão de cada relatório: 1 para o primeiro com aquele título, e assim por
    diante (do mais antigo para o mais novo)."""
    contagem, versoes = {}, {}
    for item in sorted(itens, key=lambda r: r.criado_em):
        contagem[item.titulo] = contagem.get(item.titulo, 0) + 1
        versoes[item.id] = contagem[item.titulo]
    return versoes


def _pdf_original(usuario_id, relatorio_id):
    """Lê o PDF guardado só na hora do clique (a lista não carrega os arquivos)."""
    with obter_engine().connect() as conexao:
        if not esta_valendo(conexao, usuario_id):  # conta bloqueada ou apagada
            raise PermissionError("Conta bloqueada ou apagada: o download não sai.")
        pdf = baixar_pdf_original(conexao, usuario_id, relatorio_id)
    if pdf is None:  # venceu entre a tela e o clique, ou o hash não conferiu
        logging.getLogger(__name__).error("PDF original indisponível no download")
        return b""
    return pdf


def _botao_do_original(coluna, usuario, relatorio, guardado):
    if guardado is None:
        motivo = (
            "O relatório “Minha carteira” não é guardado."
            if not pode_guardar(relatorio.tipo)
            else f"Sem original: gerado antes do arquivo, há mais de {DIAS_GUARDADO} dias "
            "ou fora da cota do plano."
        )
        coluna.button(
            "Original",
            icon=":material/download:",
            key=f"estudio_original_{relatorio.id}",
            disabled=True,
            help=motivo,
            width="stretch",
        )
        return
    quando = guardado.gerado_em.astimezone(relatorios.FUSO)
    coluna.download_button(
        "Original",
        data=functools.partial(_pdf_original, usuario.id, relatorio.id),
        file_name=f"tickerlab-{relatorio.tipo}-{quando:%Y-%m-%d-%H%M}.pdf",
        mime="application/pdf",
        icon=":material/download:",
        key=f"estudio_original_{relatorio.id}",
        help=f"O PDF como foi entregue em {quando:%d/%m/%Y às %H:%M} "
        f"(SHA-256 {guardado.sha256[:12]}…).",
        on_click="ignore",
        width="stretch",
    )


def mostrar_biblioteca(usuario):
    if st.session_state.pop(ABRIR_O_RELATORIO_DA_EMPRESA, False):
        st.switch_page(PAGINAS_DO_MENU["relatorio_empresa"])
    if usuario is None:
        st.info(
            "A biblioteca guarda os relatórios de quem entra com a conta. No modo local, "
            "sem login, nada é guardado."
        )
        return
    try:
        with obter_engine().connect() as conexao:
            itens = biblioteca_de_relatorios(conexao, usuario.id)
            guardados = pdfs_guardados(conexao, usuario.id)
    except Exception:
        logging.getLogger(__name__).exception("Falha ao ler a biblioteca")
        st.error(
            "Não consegui abrir a sua biblioteca agora. Tente de novo em instantes."
        )
        return
    if not itens:
        st.info(
            "Você ainda não gerou relatórios. Eles aparecem aqui com o tipo, o período e o "
            "estilo, para gerar de novo com os mesmos parâmetros."
        )
        return
    st.caption(
        "“Original” baixa o PDF como foi entregue (guardado por 1 ano; o seu plano guarda "
        f"até {limites_do(usuario.plano).pdfs_guardados}, e os mais antigos saem). “Reabrir” "
        "traz os mesmos parâmetros para o estúdio, para gerar com os dados de hoje (o relatório "
        "da empresa volta para a página dele). O "
        "relatório “Minha carteira” não é guardado. Excluir apaga o original e não devolve o "
        "relatório ao limite."
    )
    col_busca, col_tipos = st.columns([1, 2])
    busca = col_busca.text_input(
        "Buscar", placeholder="Título ou ativo…", key="relatorio_busca"
    )
    tipos = col_tipos.pills(
        "Tipo",
        list(relatorios.NOMES_DOS_RELATORIOS),
        format_func=relatorios.NOMES_DOS_RELATORIOS.get,
        selection_mode="multi",
        key="relatorio_filtro_tipos",
    )
    versoes = _versoes(itens)
    visiveis = [
        r
        for r in itens
        if (not tipos or r.tipo in tipos)
        and (not busca or busca.strip().lower() in r.titulo.lower())
    ]
    if not visiveis:
        st.caption("Nenhum relatório com esse filtro.")
    for r in visiveis:
        p = r.parametros
        with st.container(border=True):
            col_texto, col_original, col_compartilhar, col_reabrir, col_excluir = (
                st.columns([6, 1.4, 1.6, 1.4, 1.2], vertical_alignment="center")
            )
            _botao_do_original(col_original, usuario, r, guardados.get(r.id))
            if r.id in guardados:  # só o PDF guardado tem o que compartilhar
                compartilhar_pdf(usuario, r.id, col_compartilhar, col_texto)
            col_texto.markdown(
                f"**{r.titulo or relatorios.NOMES_DOS_RELATORIOS[r.tipo]}**"
            )
            detalhes = [
                relatorios.NOMES_DOS_RELATORIOS.get(r.tipo, r.tipo),
                PERIODOS_DO_TOPO.get(p.get("periodo"), p.get("periodo") or "—"),
                NOMES_DOS_MODELOS.get(p.get("modelo"), "Pesquisa completa"),
                estilos_pdf.estilo(p.get("estilo")).nome,
                f"versão {versoes[r.id]}",
                f"{r.criado_em.astimezone(relatorios.FUSO):%d/%m/%Y %H:%M}",
            ]
            col_texto.caption(" · ".join(str(d) for d in detalhes))
            col_reabrir.button(
                "Reabrir",
                icon=":material/restore:",
                key=f"estudio_reabrir_{r.id}",
                on_click=_reabrir,
                args=(r,),
                width="stretch",
            )
            with col_excluir.popover("Excluir", icon=":material/delete:"):
                st.caption("Excluir da biblioteca? Os parâmetros são apagados.")
                st.button(
                    "Excluir de vez",
                    type="primary",
                    key=f"estudio_excluir_{r.id}",
                    on_click=_excluir,
                    args=(usuario, r.id),
                )
