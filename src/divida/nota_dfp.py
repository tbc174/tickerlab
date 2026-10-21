"""O cronograma de vencimentos da nota de endividamento da DFP, lido por regra (B-21, PR 2).

A nota de empréstimos, financiamentos e debêntures das demonstrações financeiras costuma trazer a
tabela das parcelas do passivo não circulante por ano de vencimento ("2027 ... 2030 em diante",
"Total"). Aqui o texto da nota, já tirado do PDF (`src.leitura.texto_do_pdf`), vira essa tabela
**só por regra**, sem modelo:

- a tabela começa depois de uma linha que fala de vencimento, cronograma, amortização ou parcelas;
  cada linha começa por um ano ("2027", "2030 em diante", "Após 2030", "2028 a 2032") e depois só
  tem números, como escritos ("1.234.567", "(1.234)", "-" é zero);
- termina na linha "Total". Uma coluna só vale quando a soma das linhas bate com o total (com folga
  de arredondamento); sem total, com linhas de tamanhos diferentes ou com a soma errada, a coluna
  fica **não observada** (None), nunca completada;
- a escala vem da frase da nota ou do documento ("em milhares de reais", "R$ mil", "em milhões");
  sem ela, ou com as duas, o valor em reais fica não observado (o da nota continua lá).

A nota é do grupo inteiro (controladora e consolidado, bancos, BNDES, exterior), diferente das
ofertas da CVM (`src/divida/instrumentos.py`), que só têm o que o próprio CNPJ ofertou no Brasil.
"""

import re
from dataclasses import asdict, dataclass

from base.debentures import simples
from src.rastro import DocumentoUsado, Rastro, datas_em_texto

FONTE_DA_NOTA = "cvm-enet"  # a DFP entregue no ENET da CVM (o PDF, com as notas)
VERSAO_DA_LEITURA = "nota da divida 1"
FORMULA_DA_NOTA = (
    "copiado da tabela de vencimentos da nota de endividamento, sem conta; a coluna só vale se "
    "a soma das linhas bate com a linha Total"
)
TOLERANCIA_POR_LINHA = (
    1.0  # cada linha pode ter sido arredondada em até uma unidade da escala
)
MAX_LINHAS_DE_CABECALHO = 8  # entre o título da tabela e a 1ª linha de ano

TITULO = re.compile(r"vencimento|cronograma|amortizac|parcelas")
ESCALAS: tuple[tuple[float, re.Pattern[str]], ...] = (
    (1_000.0, re.compile(r"em milhares de reais|\br\$ ?mil\b|valores em milhares")),
    (
        1_000_000.0,
        re.compile(r"em milhoes de reais|\br\$ ?milhoes\b|valores em milhoes"),
    ),
)
# o rótulo do ano, no texto simplificado (sem acento, minúsculas, traços longos viram "-")
ANO = r"(20\d{2})"
ROTULOS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(rf"^(?:apos|acima de|depois de|posterior a)\s+{ANO}\b"), "depois"),
    (re.compile(rf"^a partir de\s+{ANO}\b"), "em_diante"),
    (
        re.compile(rf"^{ANO}\s+(?:em diante|e seguintes|e apos|adiante|em frente)\b"),
        "em_diante",
    ),
    (re.compile(rf"^{ANO}\s*(?:a|ate|-|/)\s*{ANO}\b"), "intervalo"),
    (re.compile(rf"^{ANO}\b"), "ano"),
)
NUMERO = re.compile(r"^\(?-?\d{1,3}(?:\.\d{3})*(?:,\d+)?\)?$|^\(?-?\d+(?:,\d+)?\)?$")
SO_ANO = re.compile(r"^(?:19|20)\d{2}$")
TRACO = "-"  # na tabela, "-" é zero
TRACOS_LONGOS = str.maketrans({"–": "-", "—": "-", "‒": "-"})


@dataclass(frozen=True)
class LinhaDoCronograma:
    """Uma linha da tabela: o período de vencimento e um valor por coluna, na escala da nota."""

    rotulo: str  # como está na nota
    ano_inicial: int
    ano_final: int | None  # None: "em diante"
    valores: tuple[float, ...]


@dataclass(frozen=True)
class CronogramaDaNota:
    """Uma tabela de vencimentos achada na nota (tipos simples, para JSON)."""

    titulo: str  # a linha que abre a tabela
    cabecalho: tuple[
        str, ...
    ]  # as linhas entre o título e a 1ª linha de ano (colunas, datas)
    linhas: tuple[LinhaDoCronograma, ...]
    total: tuple[float, ...]  # vazio: a nota não tem a linha Total
    confere: tuple[bool, ...]  # por coluna: a soma das linhas bate com o total
    escala: float | None  # 1.000 (milhares) ou 1.000.000; None: não observada
    rastro: Rastro

    def como_dict(self) -> dict:
        """Para a API: datas em texto ISO."""
        return {k: datas_em_texto(v) for k, v in asdict(self).items()}


@dataclass(frozen=True)
class FaixaDaNota:
    """O que vence num período, numa coluna da tabela; None: a coluna não conferiu."""

    ano_inicial: int
    ano_final: int | None
    valor_na_nota: float | None  # na escala da nota
    valor_em_reais: float | None  # None também quando a escala não é observada
    rastro: Rastro


def _numero(token: str) -> float | None:
    """O número como a tabela escreve ("1.234,5", "(1.234)" negativo, "-" zero), ou None."""
    if token == TRACO:
        return 0.0
    if not NUMERO.match(token):
        return None
    negativo = token.startswith(("(", "-"))
    valor = float(token.strip("()-").replace(".", "").replace(",", "."))
    return -valor if negativo else valor


def _numeros(tokens: list[str]) -> tuple[float, ...] | None:
    """Os valores do resto da linha; None se algum não for número (a linha não é da tabela)."""
    valores = [_numero(t) for t in tokens if t != "r$"]
    if not valores or any(v is None for v in valores):
        return None
    return tuple(v for v in valores if v is not None)


def _periodo(linha: str) -> tuple[int, int | None, str] | None:
    """O período do rótulo da linha e o resto do texto, ou None se a linha não começa por um ano."""
    for regra, tipo in ROTULOS:
        achado = regra.match(linha)
        if not achado:
            continue
        ano = int(achado.group(1))
        resto = linha[achado.end() :]
        if tipo == "depois":
            return ano + 1, None, resto
        if tipo == "em_diante":
            return ano, None, resto
        if tipo == "intervalo":
            return ano, int(achado.group(2)), resto
        return ano, ano, resto
    return None


def _linha_de_ano(original: str, simples_: str) -> LinhaDoCronograma | None:
    periodo = _periodo(simples_)
    if periodo is None:
        return None
    ano_inicial, ano_final, resto = periodo
    tokens = resto.split()
    if all(SO_ANO.match(t) for t in tokens):
        return None  # "2024 2023": o cabeçalho das colunas, não uma linha da tabela
    valores = _numeros(tokens)
    if valores is None:
        return None
    rotulo = original.strip()[: len(original.strip()) - len(resto.strip())].strip()
    return LinhaDoCronograma(rotulo, ano_inicial, ano_final, valores)


def _linha_de_total(simples_: str) -> tuple[float, ...] | None:
    if not simples_.startswith("total"):
        return None
    tokens = simples_.split()
    primeiro_numero = next(
        (i for i, t in enumerate(tokens) if _numero(t) is not None), None
    )
    return None if primeiro_numero is None else _numeros(tokens[primeiro_numero:])


def _confere(
    linhas: list[LinhaDoCronograma], total: tuple[float, ...]
) -> tuple[bool, ...]:
    """Por coluna: a soma das linhas bate com o total (todas as linhas com o mesmo tamanho)."""
    colunas = len(total)
    if not total or any(len(linha.valores) != colunas for linha in linhas):
        return tuple(False for _ in range(colunas))
    folga = TOLERANCIA_POR_LINHA * len(linhas)
    return tuple(
        abs(sum(linha.valores[j] for linha in linhas) - total[j]) <= folga
        for j in range(colunas)
    )


def escala_do_texto(texto: str) -> float | None:
    """1.000 ou 1.000.000 pela frase da escala; None sem a frase ou com as duas."""
    texto_ = simples(texto)
    achadas = {escala for escala, regra in ESCALAS if regra.search(texto_)}
    return achadas.pop() if len(achadas) == 1 else None


def ler_cronogramas(
    texto: str, documento: DocumentoUsado, escala: float | None = None
) -> tuple[CronogramaDaNota, ...]:
    """As tabelas de vencimentos do texto da nota, na ordem em que aparecem.

    `escala`: a do documento, quando a nota não diz (a capa da DFP costuma dizer); sem ela, vale a
    frase do próprio texto."""
    escala_ = escala_do_texto(texto) or escala
    rastro = Rastro.dos_documentos(
        FORMULA_DA_NOTA, VERSAO_DA_LEITURA, FONTE_DA_NOTA, [documento]
    )
    linhas = [linha.translate(TRACOS_LONGOS) for linha in texto.splitlines()]
    cronogramas: list[CronogramaDaNota] = []
    i = 0
    while i < len(linhas):
        achado = (
            _tabela(linhas, i, escala_, rastro)
            if TITULO.search(simples(linhas[i]))
            else None
        )
        if achado is None:
            i += 1
            continue
        cronograma, i = achado
        cronogramas.append(cronograma)
    return tuple(cronogramas)


def _tabela(
    linhas: list[str], inicio: int, escala: float | None, rastro: Rastro
) -> tuple[CronogramaDaNota, int] | None:
    """A tabela que o título da linha `inicio` abre e a linha seguinte a ela, ou None."""
    cabecalho: list[str] = []
    anos: list[LinhaDoCronograma] = []
    total: tuple[float, ...] = ()
    i = inicio + 1
    while i < len(linhas):
        original, simples_ = linhas[i], simples(linhas[i])
        i += 1
        if not simples_:
            continue
        linha = _linha_de_ano(original, simples_)
        if linha is not None:
            anos.append(linha)
            continue
        if anos:
            total = _linha_de_total(simples_) or ()
            if not total:
                i -= 1  # a linha que fechou a tabela pode abrir a próxima
            break
        if len(cabecalho) == MAX_LINHAS_DE_CABECALHO:
            return None  # o título não abriu tabela
        cabecalho.append(original.strip())
    if not anos:
        return None
    cronograma = CronogramaDaNota(
        titulo=linhas[inicio].strip(),
        cabecalho=tuple(cabecalho),
        linhas=tuple(anos),
        total=total,
        confere=_confere(anos, total),
        escala=escala,
        rastro=rastro,
    )
    return cronograma, i


def faixas_da_coluna(
    cronograma: CronogramaDaNota, coluna: int
) -> tuple[FaixaDaNota, ...]:
    """O que vence em cada período, numa coluna; tudo None se a coluna não conferiu com o total."""
    vale = coluna < len(cronograma.confere) and cronograma.confere[coluna]
    faixas = []
    for linha in cronograma.linhas:
        valor = linha.valores[coluna] if vale else None
        em_reais = (
            None
            if valor is None or cronograma.escala is None
            else valor * cronograma.escala
        )
        faixas.append(
            FaixaDaNota(
                linha.ano_inicial, linha.ano_final, valor, em_reais, cronograma.rastro
            )
        )
    return tuple(faixas)
