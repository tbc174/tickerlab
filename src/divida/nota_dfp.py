"""O cronograma de vencimentos da nota de endividamento da DFP, lido por regra (B-21, PR 2).

A nota de empréstimos, financiamentos e debêntures das demonstrações financeiras traz uma tabela do
que vence em cada ano. Aqui o texto da nota (a camada de texto do PDF, `src.leitura.texto_do_pdf`, ou
o OCR quando a tabela é imagem, `src.leitura.texto_por_ocr`) vira essa tabela **só por regra**, sem
modelo. Os dois desenhos que as DFPs de 2025 usam (conferidos em 21/10/2026 com CPFL, Localiza,
Petrobras, Sabesp e Vale):

- **anos nas linhas** (CPFL, Localiza, Vale): cada linha começa por um período ("2027", "2032 a
  2036", "Entre 2030 e 2032", "2033 em diante") e depois só tem números, um por coluna; a tabela fecha
  na linha "Total" ou "Subtotal";
- **anos nas colunas** (Petrobras, Sabesp): um cabeçalho com os períodos ("2026 2027 ... 2031 em
  diante Total"), que pode quebrar em várias linhas, e uma linha por instrumento, com o total logo
  depois do último período.

A tabela só entra com pelo menos dois períodos em ordem crescente (a tabela que compara exercícios,
"2025 2024", fica de fora) e com o total escrito pela própria nota. Cada série (uma coluna, ou uma
linha) só vale quando a soma dos períodos bate com esse total, com folga de arredondamento; a que não
bate fica **não observada** (None), nunca completada. A escala é a da frase mais próxima antes da
tabela ("Em milhares de reais", "Em milhões de reais"); sem ela, o valor em reais fica não observado.
Os números são copiados como escritos ("1.234.567"; "(1.234)" é negativo; "-" é zero).

A nota é do grupo inteiro (bancos, BNDES, exterior, controladas), diferente das ofertas da CVM
(`src/divida/instrumentos.py`), que só têm o que o próprio CNPJ ofertou no Brasil.
"""

import re
from dataclasses import asdict, dataclass
from itertools import pairwise

from base.debentures import simples
from src.rastro import DocumentoUsado, Rastro, datas_em_texto

FONTE_DA_NOTA = "cvm-enet"  # a DFP entregue no ENET da CVM (o PDF, com as notas)
VERSAO_DA_LEITURA = "nota da divida 1"
FORMULA_DA_NOTA = (
    "copiado da tabela de vencimentos da nota de endividamento, sem conta; a série só vale se a "
    "soma dos períodos bate com o total escrito na nota"
)
ANOS_NAS_LINHAS, ANOS_NAS_COLUNAS = "anos_nas_linhas", "anos_nas_colunas"
TOLERANCIA_POR_PERIODO = (
    1.0  # cada valor pode ter sido arredondado em até uma unidade da escala
)
MIN_PERIODOS = 2
MIN_ANOS_NO_CABECALHO = (
    3  # uma linha com menos anos que isso não abre tabela de anos nas colunas
)
MAX_LINHAS_DO_CABECALHO = 3  # o cabeçalho de anos nas colunas quebra em até três linhas
MAX_LINHAS_SEM_DADO = (
    3  # dentro da tabela de anos nas colunas (subtítulos, "Taxa média")
)
MAX_LINHAS_DE_CONTEXTO = 6  # as linhas antes da tabela guardadas para quem confere

ESCALAS: tuple[tuple[float, re.Pattern[str]], ...] = (
    (1_000.0, re.compile(r"em milhares de reais|\br\$ ?mil\b|valores em milhares")),
    (
        1_000_000.0,
        re.compile(r"em milhoes de reais|\br\$ ?milhoes\b|valores em milhoes"),
    ),
)
ANO = re.compile(r"^(?:19|20)\d{2}$")
INTERVALO_NUM_TOKEN = re.compile(r"^(20\d{2})-(20\d{2})$")  # "2028-2032"
NUMERO = re.compile(r"^\(?-?\d{1,3}(?:\.\d{3})*(?:,\d+)?\)?$|^\(?-?\d+(?:,\d+)?\)?$")
NOTA_DE_RODAPE = re.compile(
    r"^\((?:\d{1,2}|[ivx]{1,4}|\*{1,3})\)$"
)  # "(1)", "(ii)", "(*)"
TRACO = "-"  # na tabela, "-" é zero
TRACOS_LONGOS = str.maketrans({"–": "-", "—": "-", "‒": "-", "−": "-"})
# as palavras que ligam dois anos ("2032 a 2036") e as que abrem o fim ("2033 em diante")
ATE = {"a", "ate", "to", "-", "/", "e"}
EM_DIANTE = {("em", "diante"), ("em", "frente"), ("e", "seguintes"), ("e", "apos")}
DEPOIS_DE = {
    "apos": 1,
    "acima": 2,
    "depois": 2,
    "posterior": 2,
}  # palavra → onde está o ano
TOTAIS = ("total", "subtotal")


@dataclass(frozen=True)
class Periodo:
    """Um período de vencimento, como a nota escreve ("2032 a 2036"); `ano_final` None: em diante."""

    rotulo: str
    ano_inicial: int
    ano_final: int | None


@dataclass(frozen=True)
class SerieDoCronograma:
    """Os valores de uma coluna (anos nas linhas) ou de uma linha (anos nas colunas)."""

    rotulo: str  # o da linha ("Total Geral"); nas colunas, "coluna 1", "coluna 2"...
    valores: tuple[float, ...]  # um por período, na escala da nota
    total: float | None  # o que a nota escreve como total da série
    confere: bool  # a soma dos períodos bate com o total


@dataclass(frozen=True)
class CronogramaDaNota:
    """Uma tabela de vencimentos achada na nota (tipos simples, para JSON)."""

    orientacao: str  # ANOS_NAS_LINHAS ou ANOS_NAS_COLUNAS
    contexto: tuple[
        str, ...
    ]  # as linhas antes dos números (título, colunas, datas), como estão
    periodos: tuple[Periodo, ...]
    series: tuple[SerieDoCronograma, ...]
    escala: float | None  # 1.000 (milhares) ou 1.000.000; None: não observada
    rastro: Rastro

    def como_dict(self) -> dict:
        """Para a API: datas em texto ISO."""
        return {k: datas_em_texto(v) for k, v in asdict(self).items()}


@dataclass(frozen=True)
class FaixaDaNota:
    """O que vence num período, numa série; None: a série não conferiu com o total."""

    ano_inicial: int
    ano_final: int | None
    valor_na_nota: float | None  # na escala da nota
    valor_em_reais: float | None  # None também quando a escala não é observada
    rastro: Rastro


@dataclass(frozen=True)
class _Linha:
    original: tuple[str, ...]  # as palavras como estão
    simples: tuple[str, ...]  # sem acento e em minúsculas, para as regras


# o que cada leitor de tabela devolve: as séries, os períodos e a linha seguinte à tabela
_Achado = tuple[list[SerieDoCronograma], list[Periodo], int]


def _numero(token: str) -> float | None:
    """O número como a tabela escreve ("1.234,5", "(1.234)" negativo, "-" zero), ou None."""
    if token == TRACO:
        return 0.0
    if not NUMERO.match(token):
        return None
    negativo = token.startswith(("(", "-"))
    valor = float(token.strip("()-").replace(".", "").replace(",", "."))
    return -valor if negativo else valor


def _numeros(tokens: tuple[str, ...]) -> tuple[float, ...] | None:
    """Os valores dos tokens; None se algum não for número."""
    valores = [_numero(t) for t in tokens if t != "r$"]
    if not valores or any(v is None for v in valores):
        return None
    return tuple(v for v in valores if v is not None)


def _ano(token: str) -> int | None:
    return int(token) if ANO.match(token) else None


def _periodo_em(s: tuple[str, ...], i: int) -> tuple[int, int | None, int] | None:
    """O período que começa no token `i`: (ano inicial, ano final, o token seguinte), ou None."""

    def em(j: int) -> str:
        return s[j] if j < len(s) else ""

    if em(i) in DEPOIS_DE and (ano := _ano(em(i + DEPOIS_DE[em(i)]))):
        return ano + 1, None, i + DEPOIS_DE[em(i)] + 1
    if (em(i), em(i + 1), em(i + 2)) == ("a", "partir", "de") and (
        ano := _ano(em(i + 3))
    ):
        return ano, None, i + 4
    entre = em(i) == "entre" and em(i + 2) in ATE
    if entre and (ano := _ano(em(i + 1))) and (fim := _ano(em(i + 3))):
        return ano, fim, i + 4
    if achado := INTERVALO_NUM_TOKEN.match(em(i)):
        return int(achado.group(1)), int(achado.group(2)), i + 1
    ano = _ano(em(i))
    if ano is None:
        return None
    if (em(i + 1), em(i + 2)) in EM_DIANTE:
        return ano, None, i + 3
    if em(i + 1) == "adiante":
        return ano, None, i + 2
    if em(i + 1) in ATE and (fim := _ano(em(i + 2))) and fim > ano:
        return ano, fim, i + 3
    return ano, ano, i + 1


def _sem_rodape(tokens: tuple[str, ...], inicio: int) -> int:
    """Pula as notas de rodapé logo depois do rótulo ("Total (1) 19.890" → o 19.890)."""
    while inicio < len(tokens) and NOTA_DE_RODAPE.match(tokens[inicio]):
        inicio += 1
    return inicio


def _rotulo_e_numeros(linha: _Linha) -> tuple[str, tuple[float, ...]] | None:
    """Uma linha "rótulo e números" ("Debêntures 2.764.582 1.190.600 ..."), ou None.

    Os números são os do fim da linha; o ano de uma data no rótulo ("Total em 31 de dezembro de
    2025 12.026 ...") e a nota de rodapé logo depois dele ("Indexados (2) 6.409") ficam no rótulo."""
    s = linha.simples
    primeiro = len(s)
    while primeiro > 0 and _numero(s[primeiro - 1]) is not None:
        primeiro -= 1
    if primeiro == 0 or primeiro == len(s):  # sem rótulo, ou sem número
        return None
    if ANO.match(s[primeiro]) and s[primeiro - 1] == "de":
        primeiro += 1
    primeiro = _sem_rodape(s, primeiro)
    valores = _numeros(s[primeiro:])
    if valores is None:
        return None
    return " ".join(linha.original[:primeiro]).strip(" :"), valores


def _linha_de_ano(linha: _Linha) -> tuple[Periodo, tuple[float, ...]] | None:
    """Uma linha "período e números" ("2032 a 2036 318.854"), ou None."""
    achado = _periodo_em(linha.simples, 0)
    if achado is None:
        return None
    ano_inicial, ano_final, fim = achado
    resto = linha.simples[_sem_rodape(linha.simples, fim) :]
    if all(ANO.match(t) for t in resto):
        return None  # "2024 2023": o cabeçalho das colunas, não uma linha da tabela
    valores = _numeros(resto)
    if valores is None:
        return None
    rotulo = " ".join(linha.original[:fim])
    return Periodo(rotulo, ano_inicial, ano_final), valores


def _periodos_do_cabecalho(linha: _Linha) -> list[Periodo]:
    """Os períodos de um cabeçalho de anos nas colunas, da esquerda para a direita, até o "Total"."""
    s, periodos, i = linha.simples, [], 0
    while i < len(s) and _periodo_em(s, i) is None:
        i += 1  # "Vencimento em", "Cronograma de liquidação"
    while i < len(s) and s[i] not in TOTAIS:
        achado = _periodo_em(s, i)
        if achado is None:
            break
        ano_inicial, ano_final, fim = achado
        periodos.append(
            Periodo(" ".join(linha.original[i:fim]), ano_inicial, ano_final)
        )
        i = _sem_rodape(s, fim)
    return periodos


def _dado(token: str) -> bool:
    """Um valor da tabela (não um ano nem uma nota de rodapé do cabeçalho)."""
    return (
        _numero(token) is not None
        and not ANO.match(token)
        and not NOTA_DE_RODAPE.match(token)
    )


def _crescentes(periodos: list[Periodo]) -> bool:
    anos = [p.ano_inicial for p in periodos]
    return len(anos) >= MIN_PERIODOS and all(a < b for a, b in pairwise(anos))


def _confere(valores: tuple[float, ...], total: float | None) -> bool:
    folga = TOLERANCIA_POR_PERIODO * len(valores)
    return total is not None and abs(sum(valores) - total) <= folga


def _linhas(texto: str) -> list[_Linha]:
    linhas = []
    for bruta in texto.translate(TRACOS_LONGOS).splitlines():
        palavras = tuple(bruta.split())
        if not palavras:
            continue  # o PDF põe linhas vazias no meio das tabelas
        linhas.append(_Linha(palavras, tuple(simples(p) for p in palavras)))
    return linhas


def _escala_da_linha(linha: _Linha) -> float | None:
    texto = " ".join(linha.simples)
    achadas = {escala for escala, regra in ESCALAS if regra.search(texto)}
    return achadas.pop() if len(achadas) == 1 else None


def _contexto(linhas: list[_Linha], inicio: int) -> tuple[str, ...]:
    antes = [" ".join(lin.original) for lin in linhas[:inicio] if lin.original]
    return tuple(antes[-MAX_LINHAS_DE_CONTEXTO:])


def _anos_nas_linhas(linhas: list[_Linha], inicio: int) -> _Achado | None:
    """A tabela de anos nas linhas que começa em `inicio`: (períodos, séries, fim), ou None."""
    periodos: list[Periodo] = []
    colunas: list[tuple[float, ...]] = []
    i = inicio
    while i < len(linhas):
        linha = linhas[i]
        i += 1
        de_ano = _linha_de_ano(linha)
        if de_ano is not None:
            periodos.append(de_ano[0])
            colunas.append(de_ano[1])
            continue
        if linha.simples[0] in TOTAIS and (total := _rotulo_e_numeros(linha)):
            return _series_das_colunas(periodos, colunas, total[1]), periodos, i
        return None  # a tabela acabou sem total: não dá para conferir
    return None


def _series_das_colunas(
    periodos: list[Periodo], linhas: list[tuple[float, ...]], total: tuple[float, ...]
) -> list[SerieDoCronograma]:
    if not _crescentes(periodos):
        return []
    mesmo_tamanho = all(len(valores) == len(total) for valores in linhas)
    series = []
    for j, total_da_coluna in enumerate(total):
        valores = tuple(v[j] if j < len(v) else 0.0 for v in linhas)
        series.append(
            SerieDoCronograma(
                f"coluna {j + 1}",
                valores,
                total_da_coluna,
                mesmo_tamanho and _confere(valores, total_da_coluna),
            )
        )
    return series


def _cabecalho_de_anos(
    linhas: list[_Linha], inicio: int
) -> tuple[list[Periodo], int] | None:
    """O cabeçalho de anos nas colunas em `inicio` (com as linhas em que ele quebra), ou None."""
    if sum(1 for t in linhas[inicio].simples if ANO.match(t)) < MIN_ANOS_NO_CABECALHO:
        return None
    juntas = _Linha(linhas[inicio].original, linhas[inicio].simples)
    fim = inicio + 1
    while fim < len(linhas) and fim - inicio < MAX_LINHAS_DO_CABECALHO + 1:
        seguinte = linhas[fim]
        if any(_dado(t) for t in seguinte.simples):
            break  # já é linha de dados
        juntas = _Linha(
            juntas.original + seguinte.original, juntas.simples + seguinte.simples
        )
        fim += 1
    periodos = _periodos_do_cabecalho(juntas)
    return (periodos, fim) if _crescentes(periodos) else None


def _anos_nas_colunas(linhas: list[_Linha], inicio: int) -> _Achado | None:
    """A tabela de anos nas colunas que começa em `inicio`: (períodos, séries, fim), ou None."""
    cabecalho = _cabecalho_de_anos(linhas, inicio)
    if cabecalho is None:
        return None
    periodos, i = cabecalho
    series: list[SerieDoCronograma] = []
    sem_dado = 0
    while i < len(linhas) and sem_dado < MAX_LINHAS_SEM_DADO:
        if _cabecalho_de_anos(linhas, i) is not None:
            break  # outra tabela
        linha = _rotulo_e_numeros(linhas[i])
        i += 1
        if linha is None or len(linha[1]) < len(periodos):
            sem_dado += 1
            continue
        sem_dado = 0
        rotulo, numeros = linha
        valores = numeros[: len(periodos)]
        total = numeros[len(periodos)] if len(numeros) > len(periodos) else None
        series.append(
            SerieDoCronograma(rotulo, valores, total, _confere(valores, total))
        )
    if not series:
        return None
    return series, periodos, i


def ler_cronogramas(
    texto: str, documento: DocumentoUsado, escala: float | None = None
) -> tuple[CronogramaDaNota, ...]:
    """As tabelas de vencimentos do texto da nota, na ordem em que aparecem.

    `escala`: a do documento, para a tabela sem frase de escala antes dela no texto."""
    rastro = Rastro.dos_documentos(
        FORMULA_DA_NOTA, VERSAO_DA_LEITURA, FONTE_DA_NOTA, [documento]
    )
    linhas = _linhas(texto)
    cronogramas: list[CronogramaDaNota] = []
    escala_corrente: float | None = None
    i = 0
    while i < len(linhas):
        escala_corrente = _escala_da_linha(linhas[i]) or escala_corrente
        for orientacao, leitor in (
            (ANOS_NAS_COLUNAS, _anos_nas_colunas),
            (ANOS_NAS_LINHAS, _anos_nas_linhas),
        ):
            achado = leitor(linhas, i)
            if achado and any(serie.confere for serie in achado[0]):
                series, periodos, fim = achado
                cronogramas.append(
                    CronogramaDaNota(
                        orientacao=orientacao,
                        contexto=_contexto(linhas, i),
                        periodos=tuple(periodos),
                        series=tuple(series),
                        escala=escala_corrente or escala,
                        rastro=rastro,
                    )
                )
                i = fim - 1
                break
        i += 1
    return tuple(cronogramas)


def serie_do_total(cronograma: CronogramaDaNota) -> int | None:
    """Anos nas colunas: a última linha "Total..." que confere (o total geral); senão None.

    Nos anos nas linhas, cada coluna é uma data ou um recorte (controladora, consolidado), e quem
    escolhe é quem lê o `contexto`."""
    if cronograma.orientacao != ANOS_NAS_COLUNAS:
        return None
    totais = [
        j
        for j, serie in enumerate(cronograma.series)
        if simples(serie.rotulo).startswith(TOTAIS) and serie.confere
    ]
    return totais[-1] if totais else None


def faixas_da_serie(
    cronograma: CronogramaDaNota, serie: int
) -> tuple[FaixaDaNota, ...]:
    """O que vence em cada período, numa série; tudo None se a série não conferiu com o total."""
    escolhida = cronograma.series[serie]
    faixas = []
    for periodo, valor in zip(cronograma.periodos, escolhida.valores, strict=True):
        na_nota = valor if escolhida.confere else None
        em_reais = (
            None
            if na_nota is None or cronograma.escala is None
            else na_nota * cronograma.escala
        )
        faixas.append(
            FaixaDaNota(
                periodo.ano_inicial,
                periodo.ano_final,
                na_nota,
                em_reais,
                cronograma.rastro,
            )
        )
    return tuple(faixas)
