"""O PDF do relatório completo de empresa (série 2 da base de ML, PR 7; ADR 0032).

Lê o mesmo `Relatorio` da página (`src/relatorio_empresa.py`): as mesmas seções, na mesma ordem,
com os mesmos números já escritos. A cascata do lucro e a ponte da dívida viram gráficos; a seção
"Limites e perguntas em aberto" vem do relatório (obrigatória). No papel, a explicação que a
tela recolhe sai por inteiro.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from fpdf.enums import XPos, YPos

from src import dossie
from src import o_que_os_dados_mostram as leitura_da_ficha
from src.analise_escrita.modelo_da_tela import AnaliseDaTela
from src.estilos_pdf import PADRAO, Estilo
from src.graficos_pdf import grafico_de_cascata
from src.rastro import DOCUMENTO as DOCUMENTO_DO_RASTRO
from src.rastro import FONTE, FORMULA, PUBLICADO_EM, VERSAO, como_foi_calculado
from src.relatorio_empresa import (
    Item,
    Relatorio,
    Secao,
    escrever_celula,
    nome_da_tabela,
    rotulo_da_coluna,
)
from src.relatorio_pdf import AVISO, RelatorioPDF

FUSO = ZoneInfo("America/Sao_Paulo")
ESPACO_MINIMO_DA_TABELA = 50  # mm: o título não fica sozinho no pé da página
MAX_COLUNAS = 7  # mais que isso não cabe na largura de uma página A4
GRAFICOS = {"cascata": True, "ponte": False}  # tabela que vira gráfico → subir é bom?
LISTA = "lista"  # tabela de itens (título, texto, nota, link): os destaques da amostra
TITULO_DO_ANEXO = "Como cada número foi calculado"
COLUNAS_DO_ANEXO = tuple(r.capitalize() for r in (FORMULA, VERSAO, FONTE, PUBLICADO_EM))
DOCUMENTO = DOCUMENTO_DO_RASTRO.capitalize()


def _comparacao(item: Item) -> str:
    if item.comparacao is None:
        return item.sem_comparacao
    return f"{item.comparacao.contra}: {item.comparacao.texto}"


def _itens(pdf: RelatorioPDF, itens: list[Item]) -> None:
    """Os números numa tabela (indicador, valor, comparação, nota); embaixo, as bases e as fontes
    sem repetir, os motivos dos que não saíram e o texto de cada nota."""
    linhas = [[i.nome, i.texto, _comparacao(i), i.nota or ""] for i in itens]
    pdf.tabela_de_texto(["Indicador", "Valor", "Comparado com", "Nota"], linhas)
    bases = list(dict.fromkeys(i.base for i in itens if i.base))
    if bases:
        pdf.paragrafo("Base: " + "; ".join(bases) + ".", apagado=True)
    fontes = list(dict.fromkeys(i.fonte for i in itens if i.fonte))
    if fontes:
        pdf.paragrafo("Fonte: " + "; ".join(fontes) + ".", apagado=True)
    for frase in dict.fromkeys(
        [f"{i.nome}: {i.motivo}" for i in itens if i.motivo]
        + [i.nota_texto for i in itens if i.nota_texto]
    ):
        pdf.paragrafo(frase, apagado=True)


def _cabecalho_e_linhas(linhas: list[dict]) -> tuple[list[str], list[list[str]]]:
    """A tabela em texto; larga demais, ela vira de lado (contas nas linhas, anos nas colunas)
    e fica com as colunas mais recentes."""
    colunas = list(linhas[0])
    if len(colunas) > MAX_COLUNAS and len(linhas) < len(colunas):
        chave = colunas[0]
        cabecalho = [rotulo_da_coluna(chave)] + [str(linha[chave]) for linha in linhas]
        corpo = [
            [rotulo_da_coluna(c)] + [escrever_celula(linha.get(c)) for linha in linhas]
            for c in colunas[1:]
        ]
    else:
        cabecalho = [rotulo_da_coluna(c) for c in colunas]
        corpo = [[escrever_celula(linha.get(c)) for c in colunas] for linha in linhas]
    if len(cabecalho) > MAX_COLUNAS:
        cabecalho = [cabecalho[0], *cabecalho[-(MAX_COLUNAS - 1) :]]
        corpo = [[linha[0], *linha[-(MAX_COLUNAS - 1) :]] for linha in corpo]
    return cabecalho, corpo


def _titulo_da_tabela(pdf: RelatorioPDF, titulo: str) -> None:
    if pdf.get_y() > pdf.h - ESPACO_MINIMO_DA_TABELA:
        pdf.add_page()
    pdf.set_font("Manrope", "B", 10)
    pdf.cell(0, 6, titulo, new_x=XPos.LMARGIN, new_y=YPos.NEXT)


def escrever_secao(pdf: RelatorioPDF, secao: Secao, estilo: Estilo) -> None:
    pdf.secao(secao.titulo, reservar=40, numerada=True)
    if secao.itens:
        _itens(pdf, secao.itens)
    for titulo, pontos in leitura_da_ficha.por_lado(secao.pontos):
        _titulo_da_tabela(pdf, titulo)
        pdf.lista([leitura_da_ficha.frase(p) for p in pontos])
    for paragrafo in secao.paragrafos:
        pdf.paragrafo(paragrafo)
    for chave, linhas in secao.tabelas.items():
        if not linhas:
            continue
        if chave == LISTA:
            for linha in linhas:
                pdf.item(
                    linha["titulo"],
                    linha["texto"],
                    linha.get("link", ""),
                    nota=linha["nota"],
                )
            continue
        if chave in dossie.TITULOS_DAS_TABELAS:
            _titulo_da_tabela(pdf, dossie.titulo_da_tabela(chave))
            pdf.tabela_de_texto(
                list(linhas[0]), [list(linha.values()) for linha in linhas]
            )
            continue
        if chave in GRAFICOS:
            passos = [(linha["passo"], float(linha["valor"])) for linha in linhas]
            grafico = grafico_de_cascata(
                passos, nome_da_tabela(chave), estilo, GRAFICOS[chave]
            )
            pdf.imagem(grafico)
            continue
        _titulo_da_tabela(pdf, nome_da_tabela(chave))
        pdf.tabela(*_cabecalho_e_linhas(linhas))


def _sem_marcas_de_markdown(texto: str) -> str:
    return texto.replace("*", "")


def _analise(pdf: RelatorioPDF, analise: AnaliseDaTela) -> None:
    """A análise escrita antes da ficha: cada parte com o texto e, embaixo, as notas dela."""
    pdf.secao("A análise", reservar=40, numerada=True)
    pdf.aviso_destacado(analise.aviso)
    if analise.motivo:
        pdf.aviso_destacado(f"Texto de reserva por regras: {analise.motivo}.")
    for parte in analise.partes:
        _titulo_da_tabela(pdf, parte.titulo)
        for paragrafo in parte.paragrafos:
            frases = " ".join(f.com_marcas() for f in paragrafo.frases)
            rotulo = f"{paragrafo.rotulo}: " if paragrafo.rotulo else ""
            pdf.paragrafo(_sem_marcas_de_markdown(rotulo + frases))
        for nota in analise.notas_da_parte(parte):
            pdf.paragrafo(f"[{nota.numero}] {nota.legenda()}", apagado=True)


def _como_foi_calculado(pdf: RelatorioPDF, relatorio: Relatorio) -> None:
    """O anexo com o rastro de cada número (item 7 do lançamento): a fórmula, a versão do
    cálculo, a fonte e a publicação numa tabela; embaixo, cada documento usado, com o link."""
    rastros = [
        (i.nome, i.rastro) for s in relatorio.secoes for i in s.itens if i.rastro
    ]
    if not rastros:
        return
    linhas, documentos = [], {}
    for nome, rastro in rastros:
        partes = como_foi_calculado(rastro)
        textos = {p.rotulo: p.texto for p in partes}
        linhas.append([nome, *(textos[c] for c in COLUNAS_DO_ANEXO)])
        documentos |= {(p.texto, p.url): None for p in partes if p.rotulo == DOCUMENTO}
    pdf.secao(TITULO_DO_ANEXO, reservar=40)
    pdf.tabela_de_texto(["Indicador", *COLUNAS_DO_ANEXO], linhas)
    if documentos:
        _titulo_da_tabela(pdf, "Documentos usados")
        for texto, url in documentos:
            pdf.item(texto, "", url)


def relatorio_da_empresa(
    relatorio: Relatorio,
    gerado_em: datetime | None = None,
    estilo: Estilo = PADRAO,
    aviso: str = AVISO,
    com_rastro: bool = True,
) -> bytes:
    """Os bytes do PDF do relatório (`aviso`: o rodapé, que diz de onde vêm os dados). Com
    `com_rastro`, o anexo "como cada número foi calculado" fecha o relatório."""
    gerado_em = gerado_em or datetime.now(FUSO)
    pdf = RelatorioPDF(
        f"Relatório da empresa: {relatorio.empresa}",
        f"{relatorio.ticker.removesuffix('.SA')} · {relatorio.setor or 'setor não informado'}",
        gerado_em,
        estilo,
        aviso,
    )
    pdf.capa(
        [
            ("Empresa", relatorio.empresa),
            ("CNPJ", relatorio.cnpj),
            ("Grupo de setores", relatorio.grupo),
            ("Gerado em", f"{gerado_em:%d/%m/%Y às %H:%M}"),
            ("Fontes", "; ".join(relatorio.fontes)),
        ],
        [
            *(["A análise"] if relatorio.analise else []),
            *(s.titulo for s in relatorio.secoes),
        ],
    )
    pdf.add_page()
    if relatorio.em_conferencia:
        pdf.aviso_destacado(
            "Há números desta empresa em conferência pelas regras de qualidade: veja a seção "
            "Qualidade dos dados."
        )
    pdf.aviso_destacado(relatorio.aviso_das_notas)
    if relatorio.analise:
        _analise(pdf, relatorio.analise)
    for secao in relatorio.secoes:
        escrever_secao(pdf, secao, estilo)
    if com_rastro:
        _como_foi_calculado(pdf, relatorio)
    return pdf.para_bytes()
