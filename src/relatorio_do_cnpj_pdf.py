"""O PDF do relatório do CNPJ (molde B, PR 4 do plano de 19/10/2026).

Lê o mesmo `RelatorioDoCnpj` que a rota `POST /v1/busca-por-cnpj` devolve e escreve as seções com as
mesmas funções do relatório da empresa (`src/relatorio_empresa_pdf.py`): cada linha com a base (a data em
que ficou pública) e a fonte. "Limites e cuidados" e "O que ainda não aparece" saem sempre; o CNPJ de
empresa fechada e o que a base não conhece recebem o mesmo arquivo (só muda o número impresso).
"""

from datetime import datetime

from src.busca_por_cnpj import FORA, RelatorioDoCnpj
from src.estilos_pdf import PADRAO, Estilo
from src.relatorio_empresa_pdf import FUSO, escrever_secao
from src.relatorio_pdf import RelatorioPDF

TITULO_DOS_LIMITES = "Limites e cuidados"
TITULO_DO_DESLIGADO = "O que ainda não aparece"
AVISO_DO_RODAPE = (
    "Nada aqui é recomendação de investimento. Fatos públicos de companhias abertas, cada um com a "
    "fonte e a data em que ficou público."
)


def _capa(relatorio: RelatorioDoCnpj, gerado_em: datetime) -> list[tuple[str, str]]:
    linhas = [("CNPJ", relatorio.cnpj)]
    if relatorio.situacao != FORA:
        linhas.insert(0, ("Empresa", relatorio.empresa))
        if relatorio.como_era_em:
            linhas.append(("Ficha da noite de", f"{relatorio.como_era_em:%d/%m/%Y}"))
    linhas.append(("Gerado em", f"{gerado_em:%d/%m/%Y às %H:%M}"))
    if relatorio.fontes:
        linhas.append(("Fontes", "; ".join(relatorio.fontes)))
    return linhas


def relatorio_do_cnpj(
    relatorio: RelatorioDoCnpj,
    gerado_em: datetime | None = None,
    estilo: Estilo = PADRAO,
) -> bytes:
    """Os bytes do PDF: avisos, seções (cadastro, grupo, rede, fatos), fontes, limites e o que falta."""
    gerado_em = gerado_em or datetime.now(FUSO)
    encontrada = relatorio.situacao != FORA
    pdf = RelatorioPDF(
        f"Relatório do CNPJ: {relatorio.empresa}" if encontrada else "Busca por CNPJ",
        ", ".join(relatorio.tickers) if relatorio.tickers else relatorio.cnpj,
        gerado_em,
        estilo,
        AVISO_DO_RODAPE,
    )
    pdf.capa(
        _capa(relatorio, gerado_em),
        [
            *(s.titulo for s in relatorio.secoes),
            TITULO_DOS_LIMITES,
            TITULO_DO_DESLIGADO,
        ],
    )
    pdf.add_page()
    for aviso in relatorio.avisos:
        pdf.aviso_destacado(aviso)
    for secao in relatorio.secoes:
        escrever_secao(pdf, secao, estilo)
    if relatorio.fontes:
        pdf.paragrafo("Fontes: " + "; ".join(relatorio.fontes) + ".", apagado=True)
    pdf.secao(TITULO_DOS_LIMITES, reservar=40, numerada=True)
    pdf.lista(relatorio.limites)
    pdf.secao(TITULO_DO_DESLIGADO, reservar=40, numerada=True)
    pdf.lista(relatorio.desligado)
    return pdf.para_bytes()
