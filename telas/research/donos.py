"""Research: Donos e fundos (R3): fundos da CVM (CDA) e gestores dos EUA (13F).

Saiu do `app.py` sem mudar comportamento. Regra de `telas/`: nenhum estado mutável no módulo
(um módulo importado é do processo inteiro, isto é, de todos os usuários).
"""

import logging

import pandas as pd
import streamlit as st
from sqlalchemy import exc as sa_exc

from src import detentores, fundos_cvm, graficos
from src.banco import detentores as repo_detentores
from src.banco.conexao import obter_engine, tabela_inexistente
from src.dados import normalizar_ticker
from src.edicao import FONTES_DOS_DETENTORES
from src.moedas import moeda_do_ticker
from telas.comum import (
    cabecalho_da_pagina,
    carregar_contexto,
    formatar_pct,
    mostrar_grafico,
)
from telas.research.comum import _ainda_nao_coletado, _dinheiro, _numero_br

TAMANHO_DA_LISTA_DO_MERCADO = 10


def _ler_detentores(fonte, codigo):
    """(histórico com a fatia, maiores, cobertura) ou None quando a leitura falhou.

    O histórico só tem as competências utilizáveis (sem o mês mais novo ainda incompleto) e a
    coluna `fatia`: detentores ÷ fundos que informaram na competência.
    """
    try:
        with obter_engine().connect() as conexao:
            cobertura = repo_detentores.cobertura(conexao, fonte)
            datas = detentores.competencias_utilizaveis(cobertura)
            if not datas:
                return pd.DataFrame(), pd.DataFrame(), {}
            historico = repo_detentores.historico_do_ativo(conexao, fonte, codigo)
            maiores = repo_detentores.maiores_do_ativo(conexao, fonte, codigo, datas[0])
    except Exception as erro:
        if tabela_inexistente(erro):  # modo local sem migrar: o mesmo que não coletado
            return pd.DataFrame(), pd.DataFrame(), {}
        logging.getLogger(__name__).exception("Falha ao ler os detentores")
        return None
    historico = historico[historico["competencia"].isin(datas)].copy()
    informantes = historico["competencia"].map(cobertura)
    historico["fatia"] = historico["detentores"] / informantes
    historico["fatia_vendidos"] = historico["vendidos"] / informantes
    return historico, maiores, cobertura


def _tabela_de_detentores(maiores, tipo, simbolo):
    linhas = maiores[maiores["tipo"] == tipo]
    return pd.DataFrame(
        {
            "#": linhas["posicao"].astype(int),
            "Nome": linhas["nome"],
            "Valor": [_dinheiro(v, simbolo) for v in linhas["valor"]],
            "Ações": [_numero_br(q, 0) for q in linhas["quantidade"]],
        }
    )


def _variacao_comparavel(historico, cobertura):
    """Variação de detentores desde a competência anterior, se as duas forem comparáveis."""
    par = detentores.par_comparavel(cobertura)
    if par is None or historico.empty or historico["competencia"].iloc[-1] != par[0]:
        return None
    anterior = historico[historico["competencia"] == par[1]]
    if anterior.empty:
        return None
    return int(historico["detentores"].iloc[-1] - anterior["detentores"].iloc[0])


def _metricas_dos_detentores(atual, variacao, quem, periodo, simbolo, da_cvm):
    with st.container(horizontal=True):
        st.metric(
            f"{quem.capitalize()} com a ação",
            int(atual["detentores"]),
            variacao,
            border=True,
            help=f"Variação desde o {periodo} anterior, quando os dois têm cobertura parecida.",
        )
        st.metric(
            f"Fatia dos {quem} que informaram",
            formatar_pct(atual["fatia"]),
            border=True,
            help="Detentores ÷ todos que informaram posições: não muda só porque a cobertura mudou.",
        )
        st.metric("Valor que eles têm", _dinheiro(atual["valor"], simbolo), border=True)
        if da_cvm:
            st.metric(
                "Fundos vendidos (aposta na queda)",
                int(atual["vendidos"]),
                border=True,
                help="Fundos que tomaram a ação emprestada e venderam.",
            )
            st.metric(
                "Valor vendido", _dinheiro(atual["valor_vendido"], simbolo), border=True
            )


def _detentores_do_ativo(ticker):
    escolha = FONTES_DOS_DETENTORES.get(moeda_do_ticker(ticker))
    if escolha is None:
        st.info(
            f"{ticker} não é ação da B3 nem dos EUA: não há carteira de fundos para mostrar.",
            icon=":material/info:",
        )
        return
    fonte, quem, periodo, simbolo = escolha
    codigo = ticker.removesuffix(".SA")
    lido = _ler_detentores(fonte, codigo)
    if lido is None:
        st.error("Não consegui ler os dados agora. Tente de novo em instantes.")
        return
    historico, maiores, cobertura = lido
    if not cobertura:
        st.info(
            _ainda_nao_coletado(
                "Os dados ainda não foram coletados neste servidor.",
                [
                    "python -m scripts.atualizar_fundos_cvm",
                    "python -m scripts.atualizar_fundos_sec",
                ],
            ),
            icon=":material/schedule:",
        )
        return
    ultima = detentores.competencias_utilizaveis(cobertura)[0]
    mais_nova = max(cobertura)
    if mais_nova != ultima:
        st.caption(
            f"{mais_nova:%m/%Y} ainda está chegando ({cobertura[mais_nova]} {quem} informaram, "
            f"contra {cobertura[ultima]} em {ultima:%m/%Y}): fica de fora até completar."
        )
    if historico.empty or historico["competencia"].iloc[-1] != ultima:
        st.info(
            f"Nenhum dos {quem} informou posição em {codigo} em {ultima:%m/%Y}.",
            icon=":material/info:",
        )
        return
    st.markdown(f"**{codigo}** · posição de {ultima:%d/%m/%Y}")
    aviso = detentores.aviso_de_cobertura(cobertura, ultima, quem)
    if aviso:
        st.caption(aviso)
    _metricas_dos_detentores(
        historico.iloc[-1],
        _variacao_comparavel(historico, cobertura),
        quem,
        periodo,
        simbolo,
        fonte == fundos_cvm.FONTE_CDA,
    )
    if len(historico) > 1:
        mostrar_grafico(graficos.criar_grafico_detentores(historico, quem))
    st.markdown(f"##### Os maiores {quem} (comprados)")
    st.dataframe(
        _tabela_de_detentores(maiores, detentores.COMPRADO, simbolo),
        hide_index=True,
        width="stretch",
    )
    if fonte == fundos_cvm.FONTE_CDA and (maiores["tipo"] == detentores.VENDIDO).any():
        st.markdown("##### Os maiores fundos vendidos")
        st.dataframe(
            _tabela_de_detentores(maiores, detentores.VENDIDO, simbolo),
            hide_index=True,
            width="stretch",
        )
        st.caption(
            "Um fundo pode estar comprado e vendido na mesma ação ao mesmo tempo (estratégias "
            "long-short e de arbitragem): a posição vendida nem sempre é uma aposta isolada na "
            "queda."
        )


def _lista_do_mercado(tabela, crescente):
    escolhidas = tabela.dropna(subset=["variacao"]).sort_values(
        "variacao", ascending=crescente
    )
    escolhidas = escolhidas.head(TAMANHO_DA_LISTA_DO_MERCADO)
    return pd.DataFrame(
        {
            "Ativo": escolhidas["codigo"],
            "Agora": escolhidas["detentores"].astype(int),
            "Antes": escolhidas["detentores_antes"].astype("Int64"),
            "Variação": [f"{v:+.0f}" for v in escolhidas["variacao"]],
            "Ações em carteira": [
                formatar_pct(v) for v in escolhidas["variacao_quantidade"]
            ],
        }
    )


def _detentores_no_mercado():
    bolsa = st.segmented_control(
        "Bolsa",
        ["BRL", "USD"],
        format_func={"BRL": "B3 (fundos, CVM)", "USD": "EUA (gestores, 13F)"}.get,
        default="BRL",
        required=True,
        key="donos_bolsa",
    )
    fonte, quem, periodo, _ = FONTES_DOS_DETENTORES[bolsa]
    try:
        with obter_engine().connect() as conexao:
            cobertura = repo_detentores.cobertura(conexao, fonte)
            par = detentores.par_comparavel(cobertura)
            resumo = (
                repo_detentores.resumo_do_mercado(conexao, fonte, par) if par else None
            )
    except (sa_exc.OperationalError, sa_exc.ProgrammingError):
        par = None
    if par is None:
        st.info(
            f"Para comparar é preciso ter dois {periodo}s seguidos com cobertura parecida.",
            icon=":material/schedule:",
        )
        return
    atual, anterior = par
    tabela = detentores.comparar(resumo, atual, anterior)
    st.caption(
        f"{anterior:%m/%Y} ({cobertura[anterior]} {quem} informaram) → {atual:%m/%Y} "
        f'({cobertura[atual]}). "Ações em carteira" é a variação da quantidade de ações que '
        "eles têm, sem o efeito do preço."
    )
    st.markdown(f"##### Mais {quem} entraram")
    st.dataframe(_lista_do_mercado(tabela, False), hide_index=True, width="stretch")
    st.markdown(f"##### Mais {quem} saíram")
    st.dataframe(_lista_do_mercado(tabela, True), hide_index=True, width="stretch")
    if fonte == fundos_cvm.FONTE_CDA:
        st.markdown("##### Mais vendidas pelos fundos (vendido ÷ comprado)")
        apostas = tabela[tabela["valor"] > 0].sort_values(
            "fatia_vendida", ascending=False
        )
        apostas = apostas.head(TAMANHO_DA_LISTA_DO_MERCADO)
        st.dataframe(
            pd.DataFrame(
                {
                    "Ativo": apostas["codigo"],
                    "Fundos vendidos": apostas["vendidos"].astype(int),
                    "Vendido ÷ comprado": [
                        formatar_pct(v) for v in apostas["fatia_vendida"]
                    ],
                }
            ),
            hide_index=True,
            width="stretch",
        )
    st.caption("Uma lista de fatos, não de recomendações.")


def pagina_donos():
    cabecalho_da_pagina("donos")
    c = carregar_contexto()
    aba_ativo, aba_mercado = st.tabs(["Do ativo do topo", "No mercado"])
    with aba_ativo:
        _detentores_do_ativo(normalizar_ticker(c.ticker))
    with aba_mercado:
        _detentores_no_mercado()
    with st.expander("Como ler estes dados"):
        st.markdown(
            "- **B3 (fundos):** todo fundo registrado na CVM informa, por mês, o que tem na "
            "carteira. O arquivo sai cerca de **40 dias** depois do mês e vai sendo completado "
            "depois; um fundo pode manter uma posição em **sigilo por até 90 dias**.\n"
            "- **Cobertura:** por causa do sigilo, o número de fundos que aparecem muda muito de um "
            "mês para o outro sem que ninguém compre ou venda. Por isso mostramos a **fatia** dos "
            "fundos que informaram e só comparamos meses com cobertura parecida.\n"
            "- **Vendido:** o fundo tomou a ação emprestada e vendeu, apostando na queda (ou se "
            "protegendo de outra posição). Ações emprestadas por um fundo continuam dele.\n"
            "- **EUA (13F):** gestores com mais de US$ 100 milhões informam as posições do fim de "
            "cada **trimestre**, até 45 dias depois. Só posições compradas; opções ficam de fora.\n"
            "- **O que a variação diz:** quantos fundos ou gestores entraram ou saíram. É um "
            "retrato do passado, com atraso, e não mostra a intenção de ninguém.\n\n"
            "Fontes: CVM (composição e diversificação das aplicações dos fundos, CDA) e SEC "
            "(Form 13F). Nada aqui é recomendação de investimento."
        )
