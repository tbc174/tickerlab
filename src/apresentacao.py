"""O conteúdo do deck (apresentação em slides) da ficha e do relatório do setor (item 6 do lançamento).

Aqui só se decide **o que vai em cada slide**, lendo as mesmas seções da tela e do PDF
(`Secao`, `Item`): nenhum número é recalculado ou reescrito, só quebrado em slides que cabem
numa tela 16:9. O desenho fica à parte, em `src/apresentacao_pdf.py` e `src/apresentacao_pptx.py`,
que leem a mesma `Apresentacao` e por isso saem com os mesmos slides e os mesmos números.

Tipos simples (texto e tuplas), para virar JSON se a interface um dia consumir a API.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from src import dossie
from src import o_que_os_dados_mostram as leitura_da_ficha
from src.analise_escrita.modelo_da_tela import AnaliseDaTela
from src.relatorio_empresa import (
    ANEXO_DE_ANOS,
    Item,
    Relatorio,
    Secao,
    escrever_celula,
    nome_da_tabela,
    rotulo_da_coluna,
)
from src.relatorio_setor import RelatorioDoSetor, titulo_da_tabela

CAPA = "capa"
NUMEROS = "numeros"
TEXTO = "texto"
TABELA = "tabela"
FONTES = "fontes"
LIMITES = "limites"

LINHAS_POR_SLIDE = 6  # números e tabelas: mais que isso não se lê projetado
COLUNAS_NA_TABELA = 6  # a primeira coluna e as mais recentes
CARACTERES_POR_SLIDE = 700  # texto corrido: acima disso o slide vira outro
TITULO_DOS_LIMITES = "Limites e cuidados"
TITULO_DAS_FONTES = "Fontes"
AVISO_DO_DECK = "Nada aqui é recomendação de investimento. Dados públicos, cada número com a sua fonte."
NOTA_DAS_TABELAS_LONGAS = (
    "Tabelas longas (como o anexo de anos) ficam só no PDF do relatório."
)
TABELAS_FORA_DO_DECK = frozenset({ANEXO_DE_ANOS})
LISTA = "lista"  # tabela de itens (título, texto, nota, link) dos destaques

Linha = tuple[str, ...]


@dataclass(frozen=True)
class Slide:
    tipo: str
    titulo: str
    subtitulo: str = ""
    cabecalho: Linha = ()
    linhas: tuple[Linha, ...] = ()
    topicos: Linha = ()  # texto em tópicos (frases, parágrafos, limites)
    notas: Linha = ()  # letra miúda: fonte, base, motivos


@dataclass(frozen=True)
class Apresentacao:
    titulo: str
    subtitulo: str
    aviso: str  # o rodapé de todo slide
    slides: tuple[Slide, ...]

    def textos(self) -> list[str]:
        """Todo texto do deck, na ordem dos slides (para conferir os números nos testes)."""
        saida: list[str] = [self.aviso]
        for s in self.slides:
            saida += [s.titulo, s.subtitulo, *s.cabecalho, *s.topicos, *s.notas]
            saida += [c for linha in s.linhas for c in linha]
        return [t for t in saida if t]


def _em_blocos(itens: list, tamanho: int) -> list[list]:
    return [itens[i : i + tamanho] for i in range(0, len(itens), tamanho)] or [[]]


def _topicos_em_slides(topicos: list[str]) -> list[Linha]:
    """Os tópicos juntos até o limite de caracteres; um tópico maior que o limite fica sozinho."""
    slides: list[list[str]] = []
    gasto = 0
    for topico in topicos:
        if not slides or (gasto + len(topico) > CARACTERES_POR_SLIDE and slides[-1]):
            slides.append([])
            gasto = 0
        slides[-1].append(topico)
        gasto += len(topico)
    return [tuple(s) for s in slides]


def _slides_de_texto(titulo: str, topicos: list[str], tipo: str = TEXTO) -> list[Slide]:
    partes = _topicos_em_slides(topicos)
    return [
        Slide(tipo, _titulo_da_parte(titulo, i, len(partes)), topicos=parte)
        for i, parte in enumerate(partes)
    ]


def _titulo_da_parte(titulo: str, indice: int, total: int) -> str:
    return titulo if total == 1 else f"{titulo} ({indice + 1}/{total})"


# --- números -------------------------------------------------------------------------------------


def _comparacao(item: Item) -> str:
    if item.comparacao is None:
        return item.sem_comparacao or "—"
    return f"{item.comparacao.contra}: {item.comparacao.texto}"


def _slides_de_numeros(titulo: str, itens: list[Item]) -> list[Slide]:
    """Os números numa tabela (indicador, valor, comparação, fonte); embaixo, a base e o motivo
    dos que não saíram."""
    blocos = _em_blocos(itens, LINHAS_POR_SLIDE)
    slides = []
    for i, bloco in enumerate(blocos):
        linhas = tuple(
            (item.nome, item.texto, _comparacao(item), item.fonte or "—")
            for item in bloco
        )
        notas = list(
            dict.fromkeys(f"Base: {item.base}." for item in bloco if item.base)
        )
        notas += dict.fromkeys(
            f"{item.nome}: {item.motivo}" for item in bloco if item.motivo
        )
        slides.append(
            Slide(
                NUMEROS,
                _titulo_da_parte(titulo, i, len(blocos)),
                cabecalho=("Indicador", "Valor", "Comparado com", "Fonte"),
                linhas=linhas,
                notas=tuple(notas),
            )
        )
    return slides


# --- tabelas -------------------------------------------------------------------------------------


def _tabela_de_texto(
    linhas: list[dict], escrever: Callable[[object], str], rotulo: Callable[[str], str]
) -> tuple[Linha, list[Linha]]:
    """Cabeçalho e linhas em texto; larga demais, fica a primeira coluna e as mais recentes."""
    colunas = list(linhas[0])
    if len(colunas) > COLUNAS_NA_TABELA:
        colunas = [colunas[0], *colunas[-(COLUNAS_NA_TABELA - 1) :]]
    cabecalho = tuple(rotulo(c) for c in colunas)
    corpo = [tuple(escrever(linha.get(c)) for c in colunas) for linha in linhas]
    return cabecalho, corpo


def _slides_de_tabela(
    titulo: str,
    linhas: list[dict],
    escrever: Callable[[object], str],
    rotulo: Callable[[str], str],
) -> list[Slide]:
    cabecalho, corpo = _tabela_de_texto(linhas, escrever, rotulo)
    blocos = _em_blocos(corpo, LINHAS_POR_SLIDE + 2)
    return [
        Slide(
            TABELA,
            _titulo_da_parte(titulo, i, len(blocos)),
            cabecalho=cabecalho,
            linhas=tuple(bloco),
        )
        for i, bloco in enumerate(blocos)
    ]


def _como_texto(valor: object) -> str:
    return "—" if valor is None else str(valor)


# --- seções --------------------------------------------------------------------------------------


def _slides_da_secao(
    secao: Secao,
    titulo_da_tabela_: Callable[[str], str],
    escrever: Callable[[object], str],
    rotulo: Callable[[str], str],
) -> list[Slide]:
    slides: list[Slide] = []
    if secao.itens:
        slides += _slides_de_numeros(secao.titulo, secao.itens)
    for lado, pontos in leitura_da_ficha.por_lado(secao.pontos):
        titulo = f"{secao.titulo}: {lado}"
        slides += _slides_de_texto(titulo, [leitura_da_ficha.frase(p) for p in pontos])
    if secao.paragrafos:
        slides += _slides_de_texto(secao.titulo, list(secao.paragrafos))
    for chave, linhas in secao.tabelas_a_mostrar().items():
        if not linhas or chave in TABELAS_FORA_DO_DECK:
            continue
        titulo = f"{secao.titulo}: {titulo_da_tabela_(chave)}"
        if chave == LISTA:
            topicos = [
                f"{linha['titulo']}: {linha['texto']}"
                + (f" ({linha['nota']})" if linha.get("nota") else "")
                for linha in linhas
            ]
            slides += _slides_de_texto(titulo, topicos)
            continue
        slides += _slides_de_tabela(titulo, linhas, escrever, rotulo)
    if (
        not slides
    ):  # seção trancada pelo plano ou sem conteúdo: o título e o que a tela diz
        slides.append(Slide(TEXTO, secao.titulo, topicos=("Sem dados nesta seção.",)))
    return slides


def _titulo_da_tabela_da_ficha(chave: str) -> str:
    if chave in dossie.TITULOS_DAS_TABELAS:
        return dossie.titulo_da_tabela(chave)
    return nome_da_tabela(chave)


def _slides_da_analise(analise: AnaliseDaTela) -> list[Slide]:
    """A análise escrita: cada parte com o texto e, embaixo, as notas dela."""
    slides: list[Slide] = []
    for parte in analise.partes:
        topicos = []
        for paragrafo in parte.paragrafos:
            frases = " ".join(f.com_marcas() for f in paragrafo.frases)
            rotulo = f"{paragrafo.rotulo}: " if paragrafo.rotulo else ""
            topicos.append((rotulo + frases).replace("*", ""))
        notas = tuple(
            f"[{n.numero}] {n.legenda()}" for n in analise.notas_da_parte(parte)
        )
        slides += [
            Slide(slide.tipo, slide.titulo, topicos=slide.topicos, notas=notas)
            for slide in _slides_de_texto(f"A análise: {parte.titulo}", topicos)
        ]
    return slides


def _fechamento(fontes: list[str], limites: list[str]) -> list[Slide]:
    return [
        Slide(
            FONTES,
            TITULO_DAS_FONTES,
            topicos=tuple(fontes),
            notas=(NOTA_DAS_TABELAS_LONGAS,),
        ),
        *_slides_de_texto(TITULO_DOS_LIMITES, limites, LIMITES),
    ]


# --- os dois decks -------------------------------------------------------------------------------


def da_ficha(relatorio: Relatorio, gerado_em: datetime) -> Apresentacao:
    """O deck da ficha da empresa: as seções do relatório, as fontes e os limites."""
    sigla = relatorio.ticker.removesuffix(".SA")
    capa = Slide(
        CAPA,
        relatorio.empresa,
        subtitulo=f"{sigla} · {relatorio.setor or 'setor não informado'}",
        notas=(
            f"CNPJ {relatorio.cnpj}",
            f"Gerado em {gerado_em:%d/%m/%Y às %H:%M}",
        ),
    )
    avisos = [relatorio.aviso_das_notas]
    if relatorio.em_conferencia:
        avisos.insert(
            0,
            "Há números desta empresa em conferência pelas regras de qualidade: veja a "
            "seção Qualidade do lucro.",
        )
    slides = [capa, *_slides_de_texto("Antes de ler", avisos)]
    if relatorio.analise:
        slides += _slides_da_analise(relatorio.analise)
    limites: list[str] = []
    for secao in relatorio.secoes:
        if secao.chave == "limites":
            limites = list(secao.paragrafos)
            continue
        slides += _slides_da_secao(
            secao, _titulo_da_tabela_da_ficha, escrever_celula, rotulo_da_coluna
        )
    slides += _fechamento(list(relatorio.fontes), limites or [AVISO_DO_DECK])
    return Apresentacao(
        f"Ficha da empresa: {relatorio.empresa}", sigla, AVISO_DO_DECK, tuple(slides)
    )


def do_setor(relatorio: RelatorioDoSetor, gerado_em: datetime) -> Apresentacao:
    """O deck do relatório do setor: avisos, as seções na ordem da tela, fontes e limites."""
    notas = [f"Gerado em {gerado_em:%d/%m/%Y às %H:%M}"]
    if relatorio.como_era_em:
        notas.insert(0, f"Ficha da noite de {relatorio.como_era_em:%d/%m/%Y}")
    slides = [
        Slide(CAPA, relatorio.nome, subtitulo="Relatório do setor", notas=tuple(notas))
    ]
    if relatorio.avisos:
        slides += _slides_de_texto("Antes de ler", list(relatorio.avisos))
    for secao in relatorio.secoes:
        slides += _slides_da_secao(secao, titulo_da_tabela, _como_texto, str)
    slides += _fechamento(list(relatorio.fontes), list(relatorio.limites))
    return Apresentacao(
        f"Relatório do setor: {relatorio.nome}",
        relatorio.nome,
        AVISO_DO_DECK,
        tuple(slides),
    )
