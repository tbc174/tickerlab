"""A receita anual das empresas compradas, tirada da nota de combinação de negócios (CPC 15) das DFPs da
compradora (`notas_dfp`; linha 1129). É a fonte `cpc15-compradora` da régua do middle market
(`base/ma_regua.py`, ADR 0082, item 2) e a única receita de empresa fechada vendida que a base tem.

**A nota vem em três formas** (testes em `tests/test_base_ma_receitas_cpc15.py`), sempre no parágrafo "se
a aquisição tivesse ocorrido em 1º de janeiro":
- só a da adquirida: o ano cheio é o próprio número;
- quanto o consolidado seria aumentado: o ano cheio é o número mais a receita que a nota diz ter entrado
  desde a compra;
- o consolidado inteiro: o ano cheio é o número menos a receita consolidada da DRE da mesma DFP, mais a
  receita desde a compra.

**Sem prova, vazio.** Cada valor passa por duas leituras que não dividem regra (por modelo de frase e por
conceito mais próximo do número); se discordam, se a unidade não está escrita, se a frase fala de mais de
uma empresa ou se o nome não leva a um CNPJ só, não há linha. Nunca se estima.

**Sem olhar o futuro:** cada linha sai de uma versão de DFP e vale a partir da entrega dela
(`disponivel_em`); a DRE usada na conta é a da mesma versão.

**Pessoa:** a linha só leva a razão social da empresa comprada, como a compradora a escreveu, e as frases
da receita (frase com tratamento de pessoa ou CPF é recusada). CNPJ de pessoa (MEI, empresário
individual) nunca é a ligação.
"""

import re
import unicodedata
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from base import ma_regua
from base.amostra.demonstracoes import UM_ANO, fatos
from base.ma_ligacao import normalizar

# formas da nota
SO_DA_ADQUIRIDA, AUMENTO, CONSOLIDADO = (
    "so_da_adquirida",
    "aumento_do_consolidado",
    "consolidado_inteiro",
)
# como o nome virou CNPJ
PELAS_CONTROLADAS, PELA_RECEITA = "controladas", "razao_social_da_receita"
# por que uma frase não virou valor
VARIAS_ALVOS, SEM_ALVO, SEM_VALOR = "varias_alvos", "sem_alvo", "sem_receita_liquida"
LEITURAS_DIVERGEM, SEM_UNIDADE, OUTRO_ANO = (
    "leituras_divergem",
    "sem_unidade",
    "outro_ano",
)
SEM_O_DESDE_A_COMPRA, SEM_DRE = "sem_receita_desde_a_compra", "sem_dre_consolidada"
INCONSISTENTE, COM_PESSOA, SEM_CNPJ = "inconsistente", "com_pessoa", "alvo_sem_cnpj"

COLUNAS = (
    "cnpj_raiz",
    "empresa",
    "cnpj_compradora",
    "compradora",
    "referencia",
    "versao",
    "exercicio_fim",
    "receita",
    "receita_desde_a_compra",
    "forma",
    "pagina",
    "pagina_impressa",
    "pagina_da_secao",
    "trecho",
    "ligacao_por",
    "resumo",
    "disponivel_em",
    "link",
    "origem_sha256",
    "origem_coletada_em",
)
ORDEM = ["cnpj_raiz", "exercicio_fim", "cnpj_compradora", "referencia", "versao"]
COLUNAS_DA_DRE = ["cnpj", "referencia", "versao", "exercicio_fim", "receita"]

FOLGA_DE_ARREDONDAMENTO = 1.005
ALCANCE_DA_SECAO = 15_000  # caracteres entre o nome da alvo e a frase da receita
PAGINAS_PARA_SER_CABECALHO = 3
FRACAO_PARA_SER_CABECALHO = 0.3
MIL, MILHAO, BILHAO = 1_000.0, 1_000_000.0, 1_000_000_000.0


@dataclass(frozen=True)
class Leitura:
    """O que a nota diz de uma alvo num exercício, em reais."""

    nome: str
    exercicio_fim: date
    forma: str
    valor_pro_forma: float
    valor_desde_a_compra: float | None
    pagina: int
    pagina_impressa: int | None
    pagina_da_secao: int
    trecho: str


def receita_do_ano(
    leitura: Leitura, dre_consolidada: float | None = None
) -> float | None:
    """A receita da alvo no ano cheio; None quando a conta não tem as parcelas."""
    if leitura.forma == SO_DA_ADQUIRIDA:
        return leitura.valor_pro_forma
    if leitura.valor_desde_a_compra is None:
        return None
    if leitura.forma == AUMENTO:
        return leitura.valor_desde_a_compra + leitura.valor_pro_forma
    if dre_consolidada is None or leitura.valor_pro_forma < dre_consolidada:
        return None
    return leitura.valor_pro_forma - dre_consolidada + leitura.valor_desde_a_compra


# --- o texto -----------------------------------------------------------------------------------------
def _letra(c: str) -> str:
    base = unicodedata.normalize("NFKD", c)[0]
    return (base if base.isascii() else c).lower()[:1]


def _dobrar(texto: str) -> str:
    """Sem acento e em minúsculas, **com o mesmo tamanho** (as posições continuam valendo)."""
    return "".join(map(_letra, texto))


PAGINA_IMPRESSA = re.compile(r"P[ÁA]GINA:\s*(\d+)\s+de\s+\d+", re.IGNORECASE)
RODAPE = re.compile(r"^(notas explicativas|pagina: \d+ de \d+|dfp - demonstracoes.*)$")
# só no começo da linha: a frase da nota também diz "no exercício findo em" no meio de uma linha
CABECALHO = re.compile(
    r"^(em (milhares|milhoes) de reais|exercicios (sociais )?findos em \d|notas explicativas|"
    r"demonstracoes financeiras (individuais|padronizadas))"
)
CABECALHO_MAIS_LONGO = 130
UNIDADE_MIL = re.compile(
    r"\b(em|expressos em|apresentados em) milhares de reais\b|\((em )?(reais|r\$) ?mil\)"
)
UNIDADE_MILHAO = re.compile(
    r"\b(em|expressos em|apresentados em) milhoes de reais\b|\((em )?r\$ ?milhoes\)"
)


def _unidade_da_pagina(texto: str) -> float | None:
    dobrado = " ".join(_dobrar(texto).split())
    achadas = {
        fator
        for padrao, fator in ((UNIDADE_MIL, MIL), (UNIDADE_MILHAO, MILHAO))
        if padrao.search(dobrado)
    }
    return achadas.pop() if len(achadas) == 1 else None


def _linhas_repetidas(paginas: Sequence[tuple[int, str]]) -> set[str]:
    """Cabeçalhos e rodapés: a mesma linha (sem os números) em muitas páginas."""
    contagem: Counter[str] = Counter()
    for _, texto in paginas:
        contagem.update(
            {re.sub(r"\d+", "", _dobrar(l).strip()) for l in texto.splitlines()}
        )
    minimo = max(PAGINAS_PARA_SER_CABECALHO, FRACAO_PARA_SER_CABECALHO * len(paginas))
    return {l for l, n in contagem.items() if l and n >= minimo}


def _e_cabecalho(linha: str, repetidas: set[str]) -> bool:
    dobrada = _dobrar(linha).strip()
    if RODAPE.match(dobrada) or "r$" in dobrada:
        return "r$" not in dobrada
    curta = len(dobrada) <= CABECALHO_MAIS_LONGO
    return curta and (
        bool(CABECALHO.search(dobrada)) or re.sub(r"\d+", "", dobrada) in repetidas
    )


@dataclass(frozen=True)
class _Documento:
    """O texto corrido das páginas, sem cabeçalho e rodapé, sabendo de que página veio cada trecho."""

    texto: str
    dobrado: str
    inicios: list[tuple[int, int]]  # (posição no texto, página)
    unidades: dict[int, float | None]
    impressas: dict[int, int | None]

    def pagina(self, posicao: int) -> int:
        return next(p for inicio, p in reversed(self.inicios) if inicio <= posicao)

    def unidade(self, posicao: int) -> float | None:
        """A do cabeçalho da página; sem ela, a única do documento."""
        propria = self.unidades[self.pagina(posicao)]
        if propria is not None:
            return propria
        todas = {u for u in self.unidades.values() if u is not None}
        return todas.pop() if len(todas) == 1 else None


def _documento(paginas: Sequence[tuple[int, str]]) -> _Documento:
    repetidas = _linhas_repetidas(paginas)
    pedacos, inicios, posicao = [], [], 0
    unidades, impressas = {}, {}
    for numero, bruto in paginas:
        unidades[numero] = _unidade_da_pagina(bruto)
        impressa = PAGINA_IMPRESSA.search(bruto)
        impressas[numero] = int(impressa.group(1)) if impressa else None
        corpo = " ".join(
            " ".join(
                l for l in bruto.splitlines() if not _e_cabecalho(l, repetidas)
            ).split()
        )
        inicios.append((posicao, numero))
        pedacos.append(corpo)
        posicao += len(corpo) + 1
    texto = " ".join(pedacos)
    return _Documento(texto, _dobrar(texto), inicios, unidades, impressas)


FIM_DE_FRASE = re.compile(r"(?<=[.;!?])\s+(?=[A-ZÀ-Ú(“\"])")
ABREVIATURA = re.compile(r"\b(s\.a|ltda|sr|sra|srta|dr|dra|n|art|cia|inc|co)\.$")


def _frases(documento: _Documento) -> list[tuple[int, int]]:
    """(início, fim) de cada frase; "S.A." e "Ltda." não terminam frase."""
    frases, inicio = [], 0
    for corte in FIM_DE_FRASE.finditer(documento.texto):
        if ABREVIATURA.search(
            documento.dobrado[max(0, corte.start() - 6) : corte.start()]
        ):
            continue
        frases.append((inicio, corte.start()))
        inicio = corte.end()
    return [*frases, (inicio, len(documento.texto))]


# --- o nome da alvo ----------------------------------------------------------------------------------
_PALAVRA = r"[A-ZÀ-Ú0-9][\wÀ-ÿ&.\-'’/]*"
_LIGACAO = r"(?:de|da|do|das|dos|e|em|&|-)"
_FORMA = r"(?:Ltda|LTDA|S\.A|S/A|SA|Limitada|LIMITADA|Eireli|EIRELI)(?![\wÀ-ÿ])\.?"
_NOME = rf"{_PALAVRA}(?:,?\s+(?:{_LIGACAO}|{_PALAVRA}))*?,?\s+{_FORMA}"
_APELIDO = r"(?:\s*\(\s*[“\"'‘]\s*(?P<apelido>[^”\"'’()]{2,60}?)\s*[”\"'’]\s*\))?"
_GATILHO = (
    r"(?:(?i:aquisi[çc][ãa]o)(?:\s+de\s+(?:controle|participa[çc][ãa]o(?:\s+societ[áa]ria)?))?"
    r"(?:\s+(?:da|de|do|na))?(?:\s+(?i:empresa|sociedade|companhia))?\s+"
    r"|(?i:adquiri)\w+[^.]{0,200}?\b(?:da|na)\s+(?i:empresa|sociedade|companhia)\s+)"
)
ANCORA = re.compile(rf"{_GATILHO}(?P<nome>{_NOME}){_APELIDO}")


@dataclass(frozen=True)
class _Alvo:
    posicao: int
    nome: str
    apelido: str | None

    def chaves(self) -> set[str]:
        """Como a nota chama a alvo, para reconhecer a menção a outra."""
        return {c for c in (normalizar(self.nome), normalizar(self.apelido)) if c}


def _alvos(documento: _Documento) -> list[_Alvo]:
    return [
        _Alvo(m.start("nome"), m.group("nome"), m.group("apelido"))
        for m in ANCORA.finditer(documento.texto)
    ]


def _alvo_da_frase(
    alvos: list[_Alvo], inicio: int, fim: int, dobrada: str
) -> _Alvo | None:
    """O último nome apresentado antes da frase; None se ela cita outra empresa já apresentada."""
    antes = [
        a for a in alvos if a.posicao < fim and inicio - a.posicao <= ALCANCE_DA_SECAO
    ]
    if not antes:
        return None
    alvo = antes[-1]
    limpa = f" {normalizar(dobrada) or ''} "
    outras = {c for a in alvos for c in a.chaves()} - alvo.chaves()
    cita_outra = any(f" {c} " in limpa for c in outras)
    cita_a_propria = any(f" {c} " in limpa for c in alvo.chaves())
    return None if cita_outra and not cita_a_propria else alvo


# --- as duas leituras --------------------------------------------------------------------------------
DINHEIRO = re.compile(
    r"r\$\s*(?P<menos>\()?\s*(?P<numero>\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?)\s*\)?"
    r"(?:\s*(?P<unidade>mil\b|milhao|milhoes|mi\b|bilhao|bilhoes|bi\b))?"
)
FATOR = {
    "mil": MIL, "milhao": MILHAO, "milhoes": MILHAO, "mi": MILHAO,
    "bilhao": BILHAO, "bilhoes": BILHAO, "bi": BILHAO,
}  # fmt: skip
_RECEITA = r"receitas?(?:\s+operaciona(?:l|is))?"


def _numero(achado: re.Match[str]) -> float:
    return float(achado["numero"].replace(".", "").replace(",", "."))


def _positivos(frase: str) -> list[re.Match[str]]:
    return [m for m in DINHEIRO.finditer(frase) if not m["menos"]]


def _por_modelo(frase: str) -> set[int]:
    """1ª leitura: o número logo antes de "de receita líquida"; sem ele, o primeiro depois de "receita"."""
    valores = _positivos(frase)
    antes = {
        m.start()
        for m in valores
        if re.match(rf"\s*de\s+{_RECEITA}\s+liquidas?", frase[m.end() :])
    }
    if antes:
        return antes
    depois = set()
    for palavra in re.finditer(rf"{_RECEITA}(?!\s+brutas?)", frase):
        seguinte = DINHEIRO.search(frase, palavra.end())
        entre = frase[palavra.end() : seguinte.start()] if seguinte else ""
        if seguinte and not seguinte["menos"] and "brut" not in entre:
            depois.add(seguinte.start())
    return depois


CONCEITO = re.compile(
    rf"(?P<liquida>{_RECEITA}\s+liquidas?)|(?P<bruta>{_RECEITA}\s+brutas?)|(?P<receita>{_RECEITA})"
    r"|(?P<outro>lucros?|prejuizos?|resultados?|ebitda|custos?|despesas?|preco|caixa)"
)


def _conceito_de_cada_numero(frase: str) -> list[tuple[re.Match[str], str]]:
    """2ª leitura: a que conceito cada número pertence, pela posição das palavras."""
    valores = list(DINHEIRO.finditer(frase))
    conceitos = [(m.start(), str(m.lastgroup)) for m in CONCEITO.finditer(frase)]
    if "respectivamente" in frase and valores:
        em_ordem = [c for p, c in conceitos if p < valores[0].start()]
        return list(zip(valores, em_ordem[-len(valores) :], strict=False))
    atribuidos = []
    for valor in valores:
        grudado = re.match(r"\s*de\s+", frase[valor.end() :])
        seguinte = (
            CONCEITO.match(frase, valor.end() + grudado.end()) if grudado else None
        )
        anteriores = [c for p, c in conceitos if p < valor.start()]
        conceito = (
            str(seguinte.lastgroup)
            if seguinte
            else (anteriores[-1] if anteriores else "")
        )
        atribuidos.append((valor, conceito))
    return atribuidos


def _por_conceito(frase: str) -> set[int]:
    atribuidos = [(m, c) for m, c in _conceito_de_cada_numero(frase) if not m["menos"]]
    for preferido in ("liquida", "receita"):
        achados = {m.start() for m, c in atribuidos if c == preferido}
        if achados:
            return achados
    return set()


def _valor(
    documento: _Documento, inicio: int, fim: int
) -> tuple[float | None, int, str]:
    """(valor em reais, posição, motivo): o número em que as duas leituras concordam."""
    frase = documento.dobrado[inicio:fim]
    primeira, segunda = _por_modelo(frase), _por_conceito(frase)
    if not primeira and not segunda:
        return None, inicio, SEM_VALOR
    if primeira != segunda or len(primeira) != 1:
        return None, inicio, LEITURAS_DIVERGEM
    achado = DINHEIRO.match(frase, primeira.pop())
    assert achado is not None
    posicao = inicio + achado.start()
    if achado["unidade"]:
        fator = FATOR[achado["unidade"]]
    elif re.search(r",\d{2}$", achado["numero"]) and _numero(achado) >= MILHAO:
        fator = 1.0  # com centavos, o número está em reais
    else:
        fator = documento.unidade(posicao)
    if fator is None:
        return None, posicao, SEM_UNIDADE
    return round(_numero(achado) * fator, 2), posicao, ""


# --- as frases da nota -------------------------------------------------------------------------------
CONDICAO = re.compile(r"\b(se|caso)\b.*\b(tivess|houvess|ocorress|fosse)")
JANEIRO = re.compile(r"\b(?:0?1[o°]?|primeiro)\s+de\s+janeiro\s+de\s+(\d{4})")
NEGOCIO = re.compile(r"aquisic|combinac|transac|operac|controle|incorporac|adquirid")
VARIAS = re.compile(
    r"\baquisicoes\b|\bcombinacoes\b|\b(das|dos) (duas|dois|tres|quatro|cinco|seis|\d+) "
    r"(empresas|sociedades|companhias|aquisicoes|negocios)|\bempresas adquiridas\b|\badquiridas\b"
)
PESSOA = re.compile(r"\b(sr|sra|srta|senhor|senhora|cpf)\b|\d{3}\.\d{3}\.\d{3}-\d{2}")


def _e_pro_forma(frase: str) -> bool:
    return bool(
        CONDICAO.search(frase) and JANEIRO.search(frase) and NEGOCIO.search(frase)
    )


def _forma_por_modelo(frase: str) -> str | None:
    if re.search(r"aumentad|aumentaria|acrescid|acrescimo|incremento", frase):
        return AUMENTO
    if re.search(
        r"\bcontribui|\brepresentaria\b|\bda adquirida\b|\bteria (apresentado|gerado|auferido)",
        frase,
    ):
        return SO_DA_ADQUIRIDA
    return CONSOLIDADO if "consolidad" in frase else None


def _forma_por_palavra(frase: str) -> str:
    if re.search(r"\b(aument|acresc|increment)", frase):
        return AUMENTO
    consolidado = "consolidad" in frase and not re.search(
        r"contribu|representar", frase
    )
    return CONSOLIDADO if consolidado else SO_DA_ADQUIRIDA


def _desde_a_compra(
    documento: _Documento,
    frases: list[tuple[int, int]],
    alvos: list[_Alvo],
    alvo: _Alvo,
    ano: int,
) -> tuple[float | None, tuple[int, int] | None]:
    """A receita que a nota diz ter entrado no consolidado desde a compra, na seção da mesma alvo."""
    achadas: dict[float, tuple[int, int]] = {}
    for inicio, fim in frases:
        frase = documento.dobrado[inicio:fim]
        if "contribu" not in frase or "receita" not in frase or _e_pro_forma(frase):
            continue
        anos = {int(a) for a in re.findall(r"de dezembro de (\d{4})", frase)}
        if (anos and ano not in anos) or _alvo_da_frase(
            alvos, inicio, fim, frase
        ) != alvo:
            continue
        valor, _, _ = _valor(documento, inicio, fim)
        if valor is not None:
            achadas[valor] = (inicio, fim)
    if len(achadas) != 1:
        return None, None
    ((valor, posicao),) = achadas.items()
    return valor, posicao


def _ler_frase(
    documento: _Documento,
    frases: list[tuple[int, int]],
    alvos: list[_Alvo],
    inicio: int,
    fim: int,
    referencia: date,
) -> Leitura | str:
    """A leitura de uma frase "se a aquisição tivesse ocorrido", ou o motivo de não haver."""
    frase = documento.dobrado[inicio:fim]
    if VARIAS.search(frase):
        return VARIAS_ALVOS
    casado = JANEIRO.search(frase)
    assert casado is not None
    ano = int(casado.group(1))
    if referencia.month != 12 or ano not in (referencia.year, referencia.year - 1):
        return OUTRO_ANO
    alvo = _alvo_da_frase(alvos, inicio, fim, frase)
    if alvo is None:
        return SEM_ALVO
    valor, posicao, motivo = _valor(documento, inicio, fim)
    if valor is None:
        return motivo
    forma = _forma_por_modelo(frase)
    if forma != _forma_por_palavra(frase):
        return LEITURAS_DIVERGEM
    desde, onde = _desde_a_compra(documento, frases, alvos, alvo, ano)
    if desde is None and forma != SO_DA_ADQUIRIDA:
        return SEM_O_DESDE_A_COMPRA
    if (
        desde is not None
        and forma == SO_DA_ADQUIRIDA
        and desde > valor * FOLGA_DE_ARREDONDAMENTO
    ):
        return INCONSISTENTE
    provas = sorted(p for p in (onde, (inicio, fim)) if p)
    if any(PESSOA.search(documento.dobrado[a:b]) for a, b in provas):
        return COM_PESSOA
    pagina = documento.pagina(posicao)
    return Leitura(
        nome=alvo.nome,
        exercicio_fim=date(ano, 12, 31),
        forma=forma,
        valor_pro_forma=valor,
        valor_desde_a_compra=desde,
        pagina=pagina,
        pagina_impressa=documento.impressas[pagina],
        pagina_da_secao=documento.pagina(alvo.posicao),
        trecho=" ".join(documento.texto[a:b] for a, b in provas),
    )


def _sem_contradicao(lidas: list[Leitura], recusadas: Counter[str]) -> list[Leitura]:
    """Uma leitura por alvo e exercício; se o documento dá dois números, nenhum entra."""
    grupos: dict[tuple[str | None, date], list[Leitura]] = {}
    for lida in lidas:
        grupos.setdefault((normalizar(lida.nome), lida.exercicio_fim), []).append(lida)
    saida = []
    for grupo in grupos.values():
        numeros = {(l.forma, l.valor_pro_forma, l.valor_desde_a_compra) for l in grupo}
        if len(numeros) == 1:
            saida.append(grupo[0])
        else:
            recusadas[LEITURAS_DIVERGEM] += 1
    return saida


def ler_notas(
    paginas: Sequence[tuple[int, str]], referencia: date
) -> tuple[list[Leitura], Counter[str]]:
    """As receitas de alvos de um documento (`paginas`: número e texto) e os motivos das recusadas."""
    documento = _documento(paginas)
    frases = _frases(documento)
    alvos = _alvos(documento)
    lidas, recusadas = [], Counter()
    for inicio, fim in frases:
        if not _e_pro_forma(documento.dobrado[inicio:fim]):
            continue
        lida = _ler_frase(documento, frases, alvos, inicio, fim, referencia)
        if isinstance(lida, Leitura):
            lidas.append(lida)
        else:
            recusadas[lida] += 1
    return _sem_contradicao(lidas, recusadas), recusadas


# --- o nome até o CNPJ -------------------------------------------------------------------------------
def _das_controladas(controladas: pd.DataFrame) -> dict[str, set[str]]:
    """nome normalizado → raízes, pelas controladas que as companhias informam no FRE."""
    razao = (
        controladas["razao_social"]
        .fillna("")
        .str.replace(r"\([^)]*\)", " ", regex=True)
    )
    digitos = (
        controladas["cnpj"].fillna("").astype(str).str.replace(r"\D", "", regex=True)
    )
    saida: dict[str, set[str]] = {}
    for nome, cnpj in zip(razao, digitos, strict=True):
        chave = normalizar(nome)
        if chave and len(cnpj) == 14 and cnpj.strip("0"):
            saida.setdefault(chave, set()).add(cnpj[:8])
    return saida


def _unica_da_receita(
    chave: str, homonimas: pd.DataFrame, publico_em: date
) -> str | None:
    """A raiz da razão social única na Receita; None para homônimo, pessoa ou outra empresa provável."""
    if homonimas["raiz"].nunique() != 1:
        return None
    linha = homonimas.iloc[0]
    aberta_depois = pd.notna(linha["abertura"]) and linha["abertura"] > pd.Timestamp(
        publico_em
    )
    nome_curto_de_pequena = " " not in chave and bool(linha["pequena"])
    if bool(linha["pessoa"]) or aberta_depois or nome_curto_de_pequena:
        return None
    return str(linha["raiz"])


def ligar_nomes(
    nomes: Iterable[str],
    controladas: pd.DataFrame,
    receita: pd.DataFrame,
    publico_em: date,
) -> dict[str, tuple[str, str]]:
    """nome da nota → (raiz, por onde ligou). Só liga com um candidato; na dúvida, não liga.

    `receita`: o que `base.ma_ligacao.ler_receita` devolve para os nomes normalizados.
    """
    pelas_controladas = _das_controladas(controladas)
    pela_razao = receita[receita["por"] == "razao_social"]
    saida = {}
    for nome in nomes:
        chave = normalizar(nome)
        if not chave:
            continue
        das_controladas = pelas_controladas.get(chave, set())
        homonimas = pela_razao[pela_razao["nome_normalizado"] == chave]
        if len(das_controladas) == 1:
            (raiz,) = das_controladas
            contradiz = (
                homonimas["raiz"].nunique() == 1 and raiz != homonimas["raiz"].iloc[0]
            )
            if not contradiz:
                saida[nome] = (raiz, PELAS_CONTROLADAS)
        elif not das_controladas:
            raiz = _unica_da_receita(chave, homonimas, publico_em)
            if raiz:
                saida[nome] = (raiz, PELA_RECEITA)
    return saida


# --- a tabela ----------------------------------------------------------------------------------------
DOCUMENTO = ["cnpj", "referencia", "versao"]
CHEIRA_A_PRO_FORMA = re.compile(
    r"(?is)\b(se|caso)\b.{0,300}?(tivess|houvess|ocorress|fosse)"
)


def extrair(notas: pd.DataFrame) -> tuple[list[tuple[dict, Leitura]], Counter[str]]:
    """(documento, leitura) de cada alvo achada nas páginas de `notas_dfp`."""
    achadas: list[tuple[dict, Leitura]] = []
    recusadas: Counter[str] = Counter()
    for _, paginas in notas.groupby(DOCUMENTO, sort=True):
        paginas = paginas.sort_values("pagina")
        textos = paginas["texto"].fillna("")
        if not textos.str.contains("janeiro", case=False, regex=False).any():
            continue
        if not CHEIRA_A_PRO_FORMA.search(" ".join(textos)):
            continue
        documento = paginas.iloc[0].drop(["pagina", "texto"]).to_dict()
        lidas, nao = ler_notas(
            list(zip(paginas["pagina"].astype(int), textos, strict=True)),
            pd.Timestamp(documento["referencia"]).date(),
        )
        recusadas.update(nao)
        achadas.extend((documento, lida) for lida in lidas)
    return achadas, recusadas


def dre_consolidada(demonstracoes: pd.DataFrame) -> pd.DataFrame:
    """A receita anual consolidada de cada versão de DFP (`demonstracoes_como_era`, DRE, conta 3.01)."""
    todos = fatos(demonstracoes)
    anuais = todos[
        (todos["indicador"] == "receita")
        & (todos["documento"] == "DFP")
        & (todos["grupo"] == "con")
        & ((todos["fim"] - todos["inicio"]) >= UM_ANO)
    ]
    return pd.DataFrame(
        {
            "cnpj": anuais["cnpj"],
            "referencia": pd.to_datetime(anuais["referencia"]).dt.date,
            "versao": anuais["versao"].astype(int),
            "exercicio_fim": anuais["fim"].dt.date,
            "receita": anuais["valor"].astype(float),
        },
        columns=COLUNAS_DA_DRE,
    ).drop_duplicates(COLUNAS_DA_DRE[:-1])


def _da_dre(dre: pd.DataFrame, documento: dict, exercicio_fim: date) -> float | None:
    linha = dre[
        (dre["cnpj"] == documento["cnpj"])
        & (dre["referencia"] == pd.Timestamp(documento["referencia"]).date())
        & (dre["versao"] == int(documento["versao"]))
        & (dre["exercicio_fim"] == exercicio_fim)
    ]
    return None if linha.empty else float(linha["receita"].iloc[0])


def _em_milhoes(valor: float) -> str:
    return f"{valor / MILHAO:,.1f}".translate(str.maketrans(",.", ".,"))


def _linha(
    documento: dict, lida: Leitura, receita: float, raiz: str, como: str
) -> dict:
    resumo = (
        f"R$ {_em_milhoes(receita)} mi em {lida.exercicio_fim.year}, nota CPC 15 da DFP de "
        f"{documento['empresa']}, página {lida.pagina}"
    )
    return {
        "cnpj_raiz": raiz,
        "empresa": lida.nome,
        "cnpj_compradora": documento["cnpj"],
        "compradora": documento["empresa"],
        "referencia": pd.Timestamp(documento["referencia"]).date(),
        "versao": int(documento["versao"]),
        "exercicio_fim": lida.exercicio_fim,
        "receita": receita,
        "receita_desde_a_compra": lida.valor_desde_a_compra,
        "forma": lida.forma,
        "pagina": lida.pagina,
        "pagina_impressa": lida.pagina_impressa,
        "pagina_da_secao": lida.pagina_da_secao,
        "trecho": lida.trecho,
        "ligacao_por": como,
        "resumo": resumo,
        "disponivel_em": pd.Timestamp(documento["disponivel_em"]).date(),
        "link": documento["link"],
        "origem_sha256": documento.get("origem_sha256"),
        "origem_coletada_em": documento.get("origem_coletada_em"),
    }


def tabela_das_leituras(
    achadas: list[tuple[dict, Leitura]],
    controladas: pd.DataFrame,
    receita: pd.DataFrame,
    dre: pd.DataFrame,
    recusadas: Counter[str],
) -> pd.DataFrame:
    """Uma linha por alvo, exercício e versão de DFP, só com CNPJ e conta completos."""
    linhas = []
    for documento, lida in achadas:
        publico_em = pd.Timestamp(documento["disponivel_em"]).date()
        ligada = ligar_nomes([lida.nome], controladas, receita, publico_em).get(
            lida.nome
        )
        if ligada is None or ligada[0] == re.sub(r"\D", "", documento["cnpj"])[:8]:
            recusadas[SEM_CNPJ] += 1
            continue
        do_ano = receita_do_ano(lida, _da_dre(dre, documento, lida.exercicio_fim))
        if do_ano is None:
            recusadas[SEM_DRE] += 1
            continue
        linhas.append(_linha(documento, lida, do_ano, *ligada))
    tabela = pd.DataFrame(linhas, columns=list(COLUNAS)).astype(
        {c: object for c in COLUNAS}
    )
    return (
        tabela.astype(
            {
                "versao": "int64",
                "receita": float,
                "receita_desde_a_compra": float,
                "pagina": "int64",
                "pagina_impressa": "Int64",
                "pagina_da_secao": "int64",
            }
        )
        .drop_duplicates(ORDEM)
        .sort_values(ORDEM, ignore_index=True)
    )


COLUNAS_DAS_NOTAS = [
    "cnpj", "empresa", "referencia", "versao", "pagina", "texto", "disponivel_em", "link",
    "origem_sha256", "origem_coletada_em",
]  # fmt: skip


def montar_dos_arquivos(
    anos_das_notas: Sequence[Path],
    controladas: pd.DataFrame,
    ler_receita: Callable[[set[str]], pd.DataFrame],
    ler_demonstracoes: Callable[[set[str]], pd.DataFrame],
    ler_empresas: Callable[[set[str]], set[str]],
) -> tuple[pd.DataFrame, Counter[str]]:
    """A tabela a partir de `notas_dfp`, um ano por vez (o texto de um ano é grande).

    `ler_receita(nomes normalizados)`: `base.ma_ligacao.ler_receita`; `ler_demonstracoes(cnpjs)`: as
    linhas da DRE (conta 3.01) das compradoras que escreveram o consolidado inteiro;
    `ler_empresas(raízes)`: `base.ma_ligacao.raizes_de_empresa`. A tabela não tem pessoa: sai a
    raiz que não for de empresa, mesmo a que veio das controladas.
    """
    achadas: list[tuple[dict, Leitura]] = []
    recusadas: Counter[str] = Counter()
    for arquivo in anos_das_notas:
        do_ano, nao = extrair(pd.read_parquet(arquivo, columns=COLUNAS_DAS_NOTAS))
        achadas.extend(do_ano)
        recusadas.update(nao)
    nomes = {chave for _, lida in achadas if (chave := normalizar(lida.nome))}
    do_consolidado = {d["cnpj"] for d, lida in achadas if lida.forma == CONSOLIDADO}
    demonstracoes = (
        ler_demonstracoes(do_consolidado) if do_consolidado else pd.DataFrame()
    )
    dre = pd.DataFrame(columns=COLUNAS_DA_DRE)
    if not demonstracoes.empty:
        dre = dre_consolidada(demonstracoes)
    tabela = tabela_das_leituras(
        achadas, controladas, ler_receita(nomes), dre, recusadas
    )
    de_empresa = tabela["cnpj_raiz"].isin(ler_empresas(set(tabela["cnpj_raiz"])))
    if not de_empresa.all():
        recusadas[SEM_CNPJ] += int((~de_empresa).sum())
        tabela = tabela[de_empresa].reset_index(drop=True)
    return tabela, recusadas


def resumo(tabela: pd.DataFrame, recusadas: Counter[str]) -> str:
    """Os números da conferência: linhas, alvos, compradoras, as formas e o que ficou vazio."""
    contagem = tabela["forma"].value_counts()
    formas = ", ".join(f"{f} {n}" for f, n in contagem.items()) or "nenhuma"
    vazios = ", ".join(f"{m} {n}" for m, n in sorted(recusadas.items())) or "nenhum"
    return (
        f"{len(tabela)} linhas, {tabela['cnpj_raiz'].nunique()} alvos, "
        f"{tabela['cnpj_compradora'].nunique()} compradoras; formas: {formas}; sem valor: {vazios}"
    )


def montar_tabela(
    notas: pd.DataFrame,
    controladas: pd.DataFrame,
    receita: pd.DataFrame,
    dre: pd.DataFrame,
) -> tuple[pd.DataFrame, Counter[str]]:
    achadas, recusadas = extrair(notas)
    return tabela_das_leituras(achadas, controladas, receita, dre, recusadas), recusadas


def receitas_para_a_regua(tabela: pd.DataFrame) -> pd.DataFrame:
    """As linhas como a régua do middle market as lê (`base.ma_regua.COLUNAS_DAS_RECEITAS`)."""
    return pd.DataFrame(
        {
            "cnpj_raiz": tabela["cnpj_raiz"],
            "exercicio_fim": tabela["exercicio_fim"],
            "receita": tabela["receita"].astype(float),
            "fonte": ma_regua.CPC15,
            "documento": [
                f"DFP {l['cnpj_compradora']} {l['referencia']} v{l['versao']}, página {l['pagina']}"
                for l in tabela.to_dict("records")
            ],
            "documento_sha256": tabela["origem_sha256"],
            "publico_em": tabela["disponivel_em"],
        },
        columns=list(ma_regua.COLUNAS_DAS_RECEITAS),
    ).reset_index(drop=True)
