"""O PDF da Newsletter do Research: a mesma edição da página (`src.newsletter`), no Report Studio.

Usa o molde dos outros relatórios (`src.relatorios`): capa com o sumário, seções escolhidas pela
pessoa (ou pelo modelo Executivo/Completo), estilo de cores e a seção de limites obrigatória.
"""

from collections.abc import Callable

from src import relatorios as rel
from src.estilos_pdf import estilo as estilo_pela_chave
from src.newsletter import TITULO_DOS_TRECHOS, Edicao, Item, Secao
from src.relatorio_pdf import RelatorioPDF

MAX_ATIVOS_NA_CAPA = 6
SECOES_DE_CONTEUDO = ("destaques", "alertas", "por_dentro", "resultados", "donos")


def _ativos_na_capa(edicao: Edicao) -> str:
    codigos = [t.removesuffix(".SA") for t in edicao.tickers]
    resto = len(codigos) - MAX_ATIVOS_NA_CAPA
    return ", ".join(codigos[:MAX_ATIVOS_NA_CAPA]) + (
        f" (+{resto})" if resto > 0 else ""
    )


def _nota(item: Item) -> str:
    """Os trechos do documento (R5) e o "por que aparece", em linhas apagadas."""
    linhas = []
    if item.trechos:
        linhas.append(
            f"{TITULO_DOS_TRECHOS}: " + " ".join(f"“{t}”" for t in item.trechos)
        )
    if item.razoes:
        linhas.append("Por que aparece: " + " · ".join(item.razoes))
    return "\n".join(linhas)


def _secao_de_conteudo(
    pdf: RelatorioPDF, cabecalho: Callable[..., None], secao: Secao
) -> None:
    cabecalho(secao.chave, reservar=40)
    if not secao.itens:
        pdf.paragrafo(secao.vazio, apagado=True)
        return
    for item in secao.itens:
        rotulo = (
            f"Abrir o documento original na {item.sigla_da_fonte}"
            if item.sigla_da_fonte
            else ""
        )
        pdf.item(item.titulo, item.texto, item.link, rotulo, _nota(item))


def relatorio_da_newsletter(
    edicao: Edicao,
    config: rel.Configuracao | None = None,
    ao_avancar: rel.AoAvancar = None,
) -> bytes:
    """Os bytes do PDF da edição."""
    config = config or rel.Configuracao()
    pdf = RelatorioPDF(
        f"Newsletter: {edicao.lista}",
        f"O que as empresas da lista publicaram de {edicao.inicio:%d/%m/%Y} a {edicao.fim:%d/%m/%Y}",
        edicao.gerada_em,
        estilo_pela_chave(config.estilo),
    )
    cabecalho = rel._cabecalho(pdf, rel.NEWSLETTER)  # o molde comum dos relatórios

    def parametros() -> None:
        cabecalho(
            "parametros", "Como esta edição foi montada, para poder ser refeita igual."
        )
        pdf.lista(list(edicao.parametros))
        if edicao.fontes:
            pdf.pares(list(edicao.fontes))

    def limites() -> None:
        cabecalho("limites", "O que esta edição não diz.", reservar=50)
        pdf.lista(list(edicao.limites))

    partes = {
        chave: (
            lambda chave=chave: _secao_de_conteudo(pdf, cabecalho, edicao.secao(chave))
        )
        for chave in SECOES_DE_CONTEUDO
    }
    partes |= {"parametros": parametros, "limites": limites}
    capa = [
        ("Lista", edicao.lista),
        ("Ativos", _ativos_na_capa(edicao)),
        ("Período", f"{edicao.inicio:%d/%m/%Y} a {edicao.fim:%d/%m/%Y}"),
        ("Gerada em", f"{edicao.gerada_em:%d/%m/%Y às %H:%M}"),
        ("Fontes", "CVM e SEC (documentos oficiais)"),
    ]
    return rel._montar(pdf, rel.NEWSLETTER, config, capa, partes, ao_avancar)
