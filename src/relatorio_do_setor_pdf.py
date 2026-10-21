"""O PDF do relatório do setor (molde D, PR 5 do plano de 19/10/2026).

Lê o mesmo `RelatorioDoSetor` que a rota `GET /v1/relatorio-setor` devolve e escreve as seções com o
mesmo corpo do relatório da empresa (`src/relatorio_empresa_pdf.py`). As tabelas do setor já vêm
escritas (rótulos e células), então entram como estão, com os títulos da tela. Para o plano sem o
dossiê da base, as seções com números saem trancadas, igual na tela. "Limites e cuidados" sai sempre.
"""

from datetime import datetime

from src.estilos_pdf import PADRAO, Estilo
from src.relatorio_empresa_pdf import FUSO, _titulo_da_tabela, escrever_secao
from src.relatorio_pdf import RelatorioPDF
from src.relatorio_setor import RelatorioDoSetor, titulo_da_tabela

MAX_COLUNAS = 6  # mais que isso o cabeçalho não cabe na largura de uma página A4
COLUNAS_POR_BLOCO = 4
TITULO_DOS_LIMITES = "Limites e cuidados"
AVISO_DO_RODAPE = (
    "Nada aqui é recomendação de investimento. Dados públicos de companhias abertas, cada um com a "
    "fonte e a data da base."
)


def _blocos_de_tabela(
    colunas: list[str], linhas: list[list[str]]
) -> list[tuple[list[str], list[list[str]]]]:
    """Tabela larga demais para a página vira de lado (os indicadores nas linhas e, nas colunas, a
    primeira coluna de cada linha), em blocos de poucas colunas: o cabeçalho do PDF não quebra linha."""
    if len(colunas) <= MAX_COLUNAS:
        return [(colunas, linhas)]
    rotulos = [[c, *(linha[i] for linha in linhas)] for i, c in enumerate(colunas)]
    cabecalho, *corpo = rotulos
    blocos = []
    for inicio in range(1, len(cabecalho), COLUNAS_POR_BLOCO):
        fim = inicio + COLUNAS_POR_BLOCO
        blocos.append(
            (
                [cabecalho[0], *cabecalho[inicio:fim]],
                [[linha[0], *linha[inicio:fim]] for linha in corpo],
            )
        )
    return blocos


def _tabela_ja_escrita(pdf: RelatorioPDF, chave: str, linhas: list[dict]) -> None:
    _titulo_da_tabela(pdf, titulo_da_tabela(chave))
    colunas = list(linhas[0])
    texto = [[str(linha.get(c, "—")) for c in colunas] for linha in linhas]
    for cabecalho, corpo in _blocos_de_tabela(colunas, texto):
        pdf.tabela_de_texto(cabecalho, corpo)


def _capa(relatorio: RelatorioDoSetor, gerado_em: datetime) -> list[tuple[str, str]]:
    linhas = [("Setor", relatorio.nome)]
    if relatorio.como_era_em:
        linhas.append(("Ficha da noite de", f"{relatorio.como_era_em:%d/%m/%Y}"))
    linhas.append(("Gerado em", f"{gerado_em:%d/%m/%Y às %H:%M}"))
    return linhas


def relatorio_do_setor(
    relatorio: RelatorioDoSetor,
    gerado_em: datetime | None = None,
    estilo: Estilo = PADRAO,
) -> bytes:
    """Os bytes do PDF: avisos, as seções na ordem da tela, fontes e "Limites e cuidados"."""
    gerado_em = gerado_em or datetime.now(FUSO)
    pdf = RelatorioPDF(
        f"Relatório do setor: {relatorio.nome}",
        relatorio.nome,
        gerado_em,
        estilo,
        AVISO_DO_RODAPE,
    )
    pdf.capa(
        _capa(relatorio, gerado_em),
        [*(s.titulo for s in relatorio.secoes), TITULO_DOS_LIMITES],
    )
    pdf.add_page()
    for aviso in relatorio.avisos:
        pdf.aviso_destacado(aviso)
    for secao in relatorio.secoes:
        escrever_secao(pdf, secao, estilo, _tabela_ja_escrita)
    if relatorio.fontes:
        pdf.paragrafo("Fontes: " + "; ".join(relatorio.fontes) + ".", apagado=True)
    pdf.secao(TITULO_DOS_LIMITES, reservar=40, numerada=True)
    pdf.lista(relatorio.limites)
    return pdf.para_bytes()
