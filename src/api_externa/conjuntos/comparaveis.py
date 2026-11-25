"""Os comparáveis de uma companhia aberta na API externa (linha 736, PR 3): `/data/v1/companies/{cnpj}/comparables`.

`LeitorDeComparaveis(porta, permitido, linhas_maximas).comparaveis(cnpj, como_era_em)` junta, em tipos simples
e com as chaves em português (a rota traduz na saída), o que a base sabia no dia:

- `grupo_de_setores`: o grupo da empresa (`src.setores`, o mesmo do app), pelo setor do último FCA já
  entregue à CVM (`fca_geral`, como era: o setor de hoje não vale para o passado);
- `empresa_pedida` e `pares`: as companhias do mesmo grupo, cada uma com o cadastro do FCA e os números do
  último DFP já entregue (`demonstracoes_como_era`): receita, EBITDA, lucro, patrimônio, dívida líquida e as
  razões entre eles. Par é quem tem DFP de um exercício recente (`IDADE_MAXIMA_DO_EXERCICIO`); os pares vêm
  da maior receita para a menor (sem direito à receita, pela ordem do CNPJ), cortados no limite de linhas do
  plano;
- `medianas_dos_pares`: a mediana de cada razão entre os pares (sem a empresa pedida), só com pelo menos
  `setores.MINIMO_DE_EMPRESAS` pares que a têm (abaixo disso é ruído, como no app).

Cada campo sai no envelope, com a fonte e o dia em que ficou público: o cadastro pelo dia da entrega do FCA,
os números pelo dia da entrega do DFP. Número que a base não tem some, nunca vira zero. Pessoa não sai
(ADR 0108 D2.2): a empresa pedida e cada par passam por `empresas.e_empresa`. Bloco ou campo negado pelo
portão some da resposta, sem `null`; sem o setor, nada sai. O número ou a razão que o portão não libera não
some em silêncio (linha 881, `src/api_externa/nao_disponivel.py`): ele vai em `numeros_nao_disponiveis` (com o
nome de fora) e os limites avisam que os pares e as medianas não dizem nada sobre ele, para a mediana que falta
não ler como "menos de 8 pares".

**A memória por (grupo, dia)** (linha 1015, item c, PR 3): pelo log de produção de 25/11 o bloco atrasou em 6 de
6 pedidos da análise completa, porque cada pedido relia os FCA do dia e os DFP do grupo inteiro e refazia as
contas. Na porta do pedido da API (`porta_compartilhada`), os cadastros do dia e as companhias do grupo no dia
(com os números) ficam guardados na porta dona, que morre quando a base é trocada. O dia entra na chave. O que
fica guardado só depende da base e do dia: a trava de pessoa em lote (`e_empresas`) e o portão (`permitido`)
rodam a cada pedido, depois da memória, e nada do que é de quem pede entra nela. Há um teto de entradas
(`ENTRADAS_GUARDADAS`), e a mais velha sai primeiro.
"""

import functools
import math
import statistics
import threading
import unicodedata
from collections import OrderedDict
from collections.abc import Callable, Hashable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date
from types import MappingProxyType

import pandas as pd

from base import cnpj as cnpj_
from base import indicadores_de_caixa as caixa
from base.porta import Porta
from base.porta.rede import views
from base.regras import LINHA_DO_LUCRO
from src import setores
from src.api_externa import nao_disponivel
from src.api_externa.conjuntos import Permitido
from src.api_externa.conjuntos.empresas import e_empresa, e_empresas
from src.api_externa.envelope import campo
from src.api_externa.nomes import NOMES_DE_FORA

CONJUNTO = "comparables"
TABELA_DO_CADASTRO = "fca_geral"
TABELA_DAS_DEMONSTRACOES = "demonstracoes_como_era"
FONTE_DO_CADASTRO = "cvm-hist-fca"
FONTE_DOS_NUMEROS = "cvm-hist-dfp"
CONSOLIDADO, INDIVIDUAL = "con", "ind"
# um DFP mais velho que isso já não descreve a empresa: 12 meses do exercício e mais os 3 do prazo da CVM,
# com folga para a entrega atrasada (a companhia que deixou de entregar não serve de par)
IDADE_MAXIMA_DO_EXERCICIO = pd.DateOffset(months=18)

# o grupo de setores em código de fora (D7), um para cada grupo de `src.setores.GRUPOS`
GRUPOS_DE_FORA = {
    "energia": "electric_power",
    "saneamento": "water_sanitation_gas",
    "transporte": "transportation",
    "construcao": "construction",
    "comercio": "trade",
    "bens_de_capital": "capital_goods",
    "materiais_basicos": "basic_materials",
    "petroleo": "oil_and_gas",
    "consumo_nao_ciclico": "consumer_staples",
    "consumo_ciclico": "consumer_discretionary",
    "saude": "healthcare",
    "telecom_ti": "telecom_and_technology",
    "educacao": "education",
    "financeiro": "financials",
    "holdings": "holdings",
}

CAMPOS_DO_CADASTRO = ("cnpj", "empresa", "setor")
NUMEROS = ("receita", "ebitda", "lucro_liquido", "patrimonio_liquido", "divida_liquida")
RAZOES = ("margem_ebitda", "margem_liquida", "roe", "divida_liquida_sobre_ebitda")
CAMPOS_DOS_NUMEROS = ("exercicio", *NUMEROS, *RAZOES)
# as razões saem com 4 casas (0,1234 = 12,34%): a divisão inteira dava 16 casas que não dizem nada a mais
# (ensaio de 19/11/2026); a conta e as medianas usam a razão inteira, e só a saída é arredondada
CASAS_DAS_RAZOES = 4
# contas nossas sobre as linhas da CVM (somas e divisões), não o dado como a fonte publicou
DERIVADOS = frozenset({"grupo_de_setores", "ebitda", "divida_liquida", *RAZOES})
# de que colunas da tabela sai cada campo que não é coluna dela (o teste de linhagem confere que existem)
_LINHAS_DO_DFP = ("demonstracao", "conta", "descricao", "valor")
ORIGEM_DAS_CONTAS: dict[str, tuple[str, ...]] = {
    "grupo_de_setores": ("setor",),
    "exercicio": ("fim",),
    **{nome: _LINHAS_DO_DFP for nome in (*NUMEROS, *RAZOES)},
}

# os limites que valem para toda resposta; os dos números só entram quando algum número foi consultado
LIMITES_GERAIS = (
    "Cada campo traz a fonte e o dia em que ficou público: nada publicado depois de known_at entra.",
    (
        "Os pares são as companhias abertas do mesmo grupo de setores, pelo setor informado à CVM no FCA; "
        "só entra quem tinha DFP de um exercício recente no dia. Não cobre empresa fechada."
    ),
    # o ensaio de 16/11 (linha 955): em Saúde, hospital e cosmético saíram como pares; o grupo é a nossa
    # junção de setores do FCA (`src.setores.GRUPOS`), e a classificação mais fina é a da própria companhia
    (
        "Um grupo junta setores diferentes do FCA (em Saúde, por exemplo, serviços médicos e farmacêutico): "
        "o setor que cada companhia informou à CVM vem em `sector`, e as medianas são do grupo inteiro. "
        "Confira o setor de cada par antes de usá-lo como comparação."
    ),
    (
        "Comparação não é opinião sobre a empresa, e nada aqui é recomendação de investimento. Pessoa natural "
        "(MEI, empresário individual) não é servida."
    ),
)
_FRASE_DOS_NUMEROS = (
    "Os números são do DFP (consolidado; sem ele, o individual), em reais, como a companhia publicou; "
    "EBITDA, dívida líquida e as razões são contas do TickerLab sobre essas linhas. Bancos e seguradoras "
    "têm outro plano de contas: as razões deles não se comparam às das outras empresas."
)
_FRASE_DAS_MEDIANAS = "A mediana de cada razão só sai com pelo menos 8 pares que a têm."
LIMITES_DO_NUMERO: dict[str, str | tuple[str, ...]] = {
    **{nome: _FRASE_DOS_NUMEROS for nome in NUMEROS},
    **{nome: (_FRASE_DOS_NUMEROS, _FRASE_DAS_MEDIANAS) for nome in RAZOES},
}
# o nome de dentro da lista dos números e razões que o portão não libera: o par sem o número e a mediana que
# falta não querem dizer que a base não tem o número nem que faltaram pares (linha 881)
NAO_DISPONIVEIS = "numeros_nao_disponiveis"
LIMITE_DO_NUMERO_NAO_DISPONIVEL = nao_disponivel.aviso(
    NAO_DISPONIVEIS, "números", "os pares e as medianas"
)
GERAIS_ANTES_DOS_NUMEROS = (
    3  # o do known_at, o de quem são os pares e o da mistura do grupo
)


def limites(
    numeros_servidos: Iterable[str], nao_disponiveis: Sequence[str] = ()
) -> list[str]:
    """Os limites de uma resposta: os gerais, as frases dos números e das medianas quando foram consultados
    e, quando algum número ficou de fora, o aviso de que os pares e as medianas não dizem nada sobre ele."""
    return nao_disponivel.limites(
        LIMITES_GERAIS,
        LIMITES_DO_NUMERO,
        numeros_servidos,
        nao_disponiveis,
        LIMITE_DO_NUMERO_NAO_DISPONIVEL,
        antes=GERAIS_ANTES_DOS_NUMEROS,
    )


# os limites com todos os números consultados
LIMITES = tuple(limites((*NUMEROS, *RAZOES)))


# entradas guardadas por porta dona: os cadastros de um dia e as companhias de um grupo num dia (cada uma com os
# números de algumas centenas de companhias, no máximo); o dia da pergunta (`known_at`) varia de pedido para pedido.
# Cada dia ocupa duas (os cadastros e o grupo): 32 entradas são ~16 dias. A memória da porta dona também esvazia
# inteira quando enche (`porta_compartilhada.lembrar`), e aí estas entradas são calculadas de novo.
ENTRADAS_GUARDADAS = 32
_NA_MEMORIA_DA_PORTA = ("comparaveis", "por_grupo_e_dia")


class _Guardados:
    """As entradas dos comparáveis de uma porta dona, com teto: a mais velha (a menos usada) sai primeiro.

    Dividida entre os pedidos e as linhas dos blocos: a trava protege só a lista; o cálculo roda fora dela (dois
    pedidos podem calcular a mesma entrada ao mesmo tempo, com o mesmo resultado)."""

    def __init__(self) -> None:
        self._entradas: OrderedDict[Hashable, object] = OrderedDict()
        self._trava = threading.Lock()

    def __len__(self) -> int:
        with self._trava:
            return len(self._entradas)

    def chaves(self) -> list[Hashable]:
        with self._trava:
            return list(self._entradas)

    def valor(self, chave: Hashable) -> object:
        with self._trava:
            return self._entradas[chave]

    def lembrar[T](self, chave: Hashable, calcular: Callable[[], T]) -> T:
        with self._trava:
            if chave in self._entradas:
                self._entradas.move_to_end(chave)
                return self._entradas[chave]  # type: ignore[return-value]
        valor = calcular()
        with self._trava:
            self._entradas[chave] = valor
            self._entradas.move_to_end(chave)
            while len(self._entradas) > ENTRADAS_GUARDADAS:
                self._entradas.popitem(last=False)
        return valor


def _guardados(porta: Porta) -> _Guardados | None:
    """As entradas dos comparáveis na memória da porta dona; None na porta que não é de pedido (calcula sempre)."""
    memoria = getattr(porta, "memoria_da_base", None)
    if memoria is None:
        return None
    return memoria.setdefault(_NA_MEMORIA_DA_PORTA, _Guardados())


@dataclass(frozen=True)
class ComparaveisServidos:
    """O que sai de um pedido de comparáveis: o corpo, as fontes usadas e as linhas servidas."""

    corpo: dict
    fontes: set[str] = field(default_factory=set)
    linhas: int = 0


@dataclass(frozen=True)
class _Companhia:
    """Uma companhia como a base a conhecia no dia: o cadastro do FCA e os números do último DFP."""

    cnpj: str
    empresa: str
    setor: str
    cadastro_publico_em: date
    exercicio: date | None = None
    # só leitura: a companhia fica guardada e é dividida entre os pedidos (a memória por grupo e dia)
    numeros: Mapping[str, float] = field(default_factory=dict)
    numeros_publicos_em: date | None = None


def _simples(texto: object) -> str:
    sem = unicodedata.normalize("NFD", str(texto))
    return "".join(c for c in sem if unicodedata.category(c) != "Mn").lower().strip()


def _profundidade(conta: str) -> int:
    return conta.count(".")


def _soma(*valores: float | None) -> float | None:
    presentes = [v for v in valores if v is not None]
    return sum(presentes) if presentes else None


def _dividir(numerador: float | None, denominador: float | None) -> float | None:
    """A razão só com o denominador positivo: sobre receita, patrimônio ou EBITDA negativos ela engana."""
    if numerador is None or denominador is None or denominador <= 0:
        return None
    return numerador / denominador


@functools.lru_cache(maxsize=65536)
def _simples_de(texto: str) -> str:
    return _simples(texto)


@functools.lru_cache(maxsize=65536)
def _e_o_lucro(texto: str) -> bool:
    return bool(LINHA_DO_LUCRO.match(texto.strip()))


def _numeros(
    receita: float | None,
    ebitda: float | None,
    lucro: float | None,
    patrimonio: float | None,
    divida: float | None,
) -> dict[str, float]:
    """Os números e as razões de um exercício; só número finito sai (o JSON da API não leva NaN nem infinito)."""
    valores = {
        "receita": receita,
        "ebitda": ebitda,
        "lucro_liquido": lucro,
        "patrimonio_liquido": patrimonio,
        "divida_liquida": divida,
        "margem_ebitda": _dividir(ebitda, receita),
        "margem_liquida": _dividir(lucro, receita),
        "roe": _dividir(lucro, patrimonio),
        "divida_liquida_sobre_ebitda": _dividir(divida, ebitda),
    }
    return {
        nome: valor
        for nome, valor in valores.items()
        if valor is not None and math.isfinite(valor)
    }


@dataclass(frozen=True)
class Exercicio:
    """O último exercício recente de uma companhia: o fim, os números e as razões (só de leitura: ficam guardados
    na memória por grupo e dia) e o dia mais novo em que as linhas usadas ficaram públicas."""

    fim: pd.Timestamp
    numeros: Mapping[str, float]
    publicos_em: pd.Timestamp


def _do_ultimo_exercicio(dfps: pd.DataFrame, mais_velho: pd.Timestamp) -> pd.DataFrame:
    """De cada companhia, as linhas do último exercício, se ele não é mais velho que `mais_velho`. Sai só o grupo
    consolidado (sem ele, o individual) e uma linha por conta, a da entrega mais nova.

    As linhas saem agrupadas por cnpj, cada companhia na ordem da entrega. É a mesma ordem em que a conta
    companhia a companhia as via, e "a primeira linha achada" de cada conta continua a mesma."""
    fim = dfps.groupby("cnpj")["fim"].transform("max")
    linhas = dfps[(dfps["fim"] == fim) & (fim >= mais_velho)]
    tem_consolidado = (
        (linhas["grupo"] == CONSOLIDADO).groupby(linhas["cnpj"]).transform("any")
    )
    linhas = linhas[
        linhas["grupo"] == tem_consolidado.map({True: CONSOLIDADO, False: INDIVIDUAL})
    ]
    # ordenação estável: dentro de cada companhia a ordem é a de antes; entre elas, a do cnpj
    linhas = linhas.sort_values(["divulgado_em", "versao"], kind="stable")
    linhas = linhas.drop_duplicates(
        ["cnpj", "demonstracao", "conta", "inicio"], keep="last"
    )
    return linhas.sort_values("cnpj", kind="stable").reset_index(drop=True)


def _primeiro(linhas: pd.DataFrame, achadas: pd.Series) -> dict[str, float]:
    """Por cnpj, o valor da primeira linha achada; a linha com o valor vazio conta como conta que falta."""
    com_valor = linhas[achadas & linhas["valor"].notna()]
    return {
        str(cnpj): float(valor)
        for cnpj, valor in com_valor.groupby("cnpj", sort=False)["valor"]
        .first()
        .items()
    }


def numeros_do_grupo(
    dfps: pd.DataFrame, mais_velho: pd.Timestamp
) -> dict[str, Exercicio]:
    """O último exercício recente de cada companhia das linhas do DFP (`_dfps`), por cnpj formatado, com as contas
    das regras de `src.demonstracoes`, feitas uma vez para o grupo inteiro (linha 1015, item d):
    - receita: a conta 3.01 da DRE;
    - lucro: a linha de profundidade 1 da DRE que é o lucro ou prejuízo do período;
    - patrimônio: a linha de profundidade 1 do BPP que começa por "patrimônio líquido";
    - dívida líquida: empréstimos e financiamentos de curto e de longo prazo, menos caixa e aplicações. Sem a
      dívida ou sem o caixa não há conta, e a falta nunca vira zero;
    - EBITDA: a mesma conta da ficha de caixa (`base.indicadores_de_caixa`: EBIT + D&A).
    """
    if dfps.empty:
        return {}
    linhas = _do_ultimo_exercicio(dfps, mais_velho)
    if linhas.empty:
        return {}
    simples = linhas["descricao"].map(lambda d: _simples_de(str(d)))
    profundidade = linhas["conta"].map(_profundidade)
    demonstracao, conta = linhas["demonstracao"], linhas["conta"]
    dre, bpa, bpp = demonstracao == "DRE", demonstracao == "BPA", demonstracao == "BPP"

    def do_balanco(da: pd.Series, codigo: str, comeco: str) -> dict[str, float]:
        return _primeiro(
            linhas, da & (conta == codigo) & simples.str.startswith(comeco)
        )

    receitas = _primeiro(linhas, dre & (conta == "3.01"))
    lucros = _primeiro(
        linhas,
        dre
        & (profundidade == 1)
        & linhas["descricao"].map(lambda d: _e_o_lucro(str(d))),
    )
    patrimonios = _primeiro(
        linhas, bpp & (profundidade == 1) & simples.str.startswith("patrimonio liquido")
    )
    dividas_cp = do_balanco(bpp, "2.01.04", "emprestimos e financiamentos")
    dividas_lp = do_balanco(bpp, "2.02.01", "emprestimos e financiamentos")
    caixas = do_balanco(bpa, "1.01.01", "caixa")
    aplicacoes = do_balanco(bpa, "1.01.02", "aplicacoes")
    tabela = caixa.indicadores_de_caixa(linhas)
    tabela = tabela[tabela["ebitda"].notna()]
    ebitdas = {
        (str(linha.cnpj), pd.Timestamp(linha.fim)): float(linha.ebitda)
        for linha in tabela.itertuples(index=False)
    }
    publicos = linhas.groupby("cnpj", sort=False)["divulgado_em"].max()
    fins = linhas.groupby("cnpj", sort=False)["fim"].first()
    exercicios = {}
    for cnpj, fim in fins.items():
        formatado, fim = str(cnpj), pd.Timestamp(fim)
        divida = _soma(dividas_cp.get(formatado), dividas_lp.get(formatado))
        caixa_ = caixas.get(formatado)
        liquida = (
            None
            if divida is None or caixa_ is None
            else divida - caixa_ - (aplicacoes.get(formatado) or 0.0)
        )
        numeros = _numeros(
            receitas.get(formatado),
            ebitdas.get((formatado, fim)),
            lucros.get(formatado),
            patrimonios.get(formatado),
            liquida,
        )
        exercicios[formatado] = Exercicio(
            fim, MappingProxyType(numeros), pd.Timestamp(publicos[cnpj])
        )
    return exercicios


def _na_saida(nome: str, valor: float | str) -> float | str:
    """O valor como sai na resposta: a razão com `CASAS_DAS_RAZOES` casas, o resto como está."""
    if nome in RAZOES and isinstance(valor, float):
        return round(valor, CASAS_DAS_RAZOES)
    return valor


def _corte(como_era_em: date) -> pd.Timestamp:
    """O fim de exercício mais velho que ainda serve de par no dia."""
    return pd.Timestamp(como_era_em) - IDADE_MAXIMA_DO_EXERCICIO


class LeitorDeComparaveis:
    """Lê os comparáveis de uma companhia aberta de uma porta para um pedido."""

    def __init__(self, porta: Porta, permitido: Permitido, linhas_maximas: int) -> None:
        self.porta = porta
        self.permitido = permitido
        self.linhas_maximas = linhas_maximas

    # ------------------------------------------------------------ leitura

    def _cadastros(self, como_era_em: date) -> pd.DataFrame:
        """O último FCA já entregue de cada companhia, com o grupo de setores (cnpj só com dígitos)."""
        if TABELA_DO_CADASTRO not in views(self.porta.con):
            return pd.DataFrame(
                columns=["cnpj", "empresa", "setor", "conhecido_em", "grupo"]
            )
        fca = self.porta.ler(
            TABELA_DO_CADASTRO,
            como_era_em=como_era_em,
            colunas=["cnpj", "empresa", "setor", "referencia", "conhecido_em"],
        )
        fca = fca.sort_values(["referencia", "conhecido_em"]).drop_duplicates(
            "cnpj", keep="last"
        )
        fca["cnpj"] = fca["cnpj"].map(cnpj_.normalizar_cnpj)
        fca["grupo"] = fca["setor"].map(
            lambda s: (
                setores.grupo_do_setor(str(s)) if pd.notna(s) else setores.SEM_GRUPO
            )
        )
        return fca[fca["cnpj"].astype(bool)].reset_index(drop=True)

    def _dfps(self, cnpjs: list[str], como_era_em: date) -> pd.DataFrame:
        """As linhas do DFP das companhias, só dos exercícios que terminam depois do corte de
        `IDADE_MAXIMA_DO_EXERCICIO` (linha 1015, item d). O exercício mais novo de cada companhia, quando
        passa do corte, está inteiro depois dele; quando não passa, a companhia já fica sem números. Ler o
        histórico inteiro dava o mesmo resultado (há teste), com 980 mil linhas num grupo da base do ensaio."""
        if TABELA_DAS_DEMONSTRACOES not in views(self.porta.con):
            return pd.DataFrame()
        colunas = [
            "cnpj", "grupo", "demonstracao", "conta", "descricao", "inicio", "fim", "valor", "versao",
            "divulgado_em",
        ]  # fmt: skip
        return self.porta.ler(
            TABELA_DAS_DEMONSTRACOES,
            como_era_em=como_era_em,
            filtros={"cnpj": [cnpj_.formatar(c) for c in cnpjs], "documento": "DFP"},
            colunas=colunas,
            a_partir_de={"fim": _corte(como_era_em).date()},
        )

    def _companhias(
        self, cadastros: pd.DataFrame, como_era_em: date
    ) -> dict[str, _Companhia]:
        """Cada companhia dos cadastros com os números do último DFP recente (sem ele, só o cadastro)."""
        dfps = self._dfps(list(cadastros["cnpj"]), como_era_em)
        exercicios = numeros_do_grupo(dfps, _corte(como_era_em))
        companhias = {}
        for linha in cadastros.itertuples(index=False):
            companhia = _Companhia(
                cnpj=str(linha.cnpj),
                empresa=str(linha.empresa),
                setor=str(linha.setor),
                cadastro_publico_em=pd.Timestamp(linha.conhecido_em).date(),
            )
            formatado = cnpj_.formatar(companhia.cnpj)
            if formatado in exercicios:
                do_exercicio = exercicios[formatado]
                companhia = replace(
                    companhia,
                    exercicio=do_exercicio.fim.date(),
                    numeros=do_exercicio.numeros,
                    numeros_publicos_em=do_exercicio.publicos_em.date(),
                )
            companhias[companhia.cnpj] = companhia
        return companhias

    def _lembrado[T](self, chave: Hashable, calcular: Callable[[], T]) -> T:
        guardados = _guardados(self.porta)
        return calcular() if guardados is None else guardados.lembrar(chave, calcular)

    def _cadastros_do_dia(self, dia: date) -> pd.DataFrame:
        """Os cadastros do dia (`_cadastros`), lembrados por dia; sai uma cópia, que quem pede pode mexer."""
        return self._lembrado(("cadastros", dia), lambda: self._cadastros(dia)).copy()

    def _companhias_do_grupo(
        self, cadastros: pd.DataFrame, grupo: str, dia: date
    ) -> dict[str, _Companhia]:
        """Todas as companhias do grupo no dia, com os números (`_companhias`), lembradas por (grupo, dia): ainda
        sem a trava de pessoa e sem o portão, que são de cada pedido."""
        do_grupo = cadastros[cadastros["grupo"] == grupo]
        return dict(
            self._lembrado(
                ("companhias", grupo, dia), lambda: self._companhias(do_grupo, dia)
            )
        )

    # ------------------------------------------------------------ saída

    def _servida(self, companhia: _Companhia) -> tuple[dict, set[str]]:
        """A linha de uma companhia, com os campos que o portão libera, cada um no envelope."""
        cadastro = {
            "cnpj": companhia.cnpj,
            "empresa": companhia.empresa,
            "setor": companhia.setor,
        }
        linha = {
            nome: campo(
                cadastro[nome],
                fonte=FONTE_DO_CADASTRO,
                publico_em=companhia.cadastro_publico_em,
                visto_em=None,
            )
            for nome in CAMPOS_DO_CADASTRO
            if self.permitido(FONTE_DO_CADASTRO, nome, nome in DERIVADOS)
        }
        fontes = {FONTE_DO_CADASTRO}
        if companhia.exercicio is None or companhia.numeros_publicos_em is None:
            return linha, fontes
        valores = {"exercicio": companhia.exercicio.isoformat(), **companhia.numeros}
        numeros = {
            nome: campo(
                _na_saida(nome, valores[nome]),
                fonte=FONTE_DOS_NUMEROS,
                publico_em=companhia.numeros_publicos_em,
                visto_em=None,
            )
            for nome in CAMPOS_DOS_NUMEROS
            if nome in valores
            and self.permitido(FONTE_DOS_NUMEROS, nome, nome in DERIVADOS)
        }
        if set(numeros) - {"exercicio"}:
            linha |= numeros
            fontes.add(FONTE_DOS_NUMEROS)
        return linha, fontes

    def _medianas(self, pares: list[_Companhia]) -> dict:
        """A mediana de cada razão entre os pares, só com pelo menos `MINIMO_DE_EMPRESAS` que a têm."""
        medianas = {}
        for nome in RAZOES:
            if not self.permitido(FONTE_DOS_NUMEROS, nome, True):
                continue
            com = [
                p
                for p in pares
                if nome in p.numeros and p.numeros_publicos_em is not None
            ]
            if len(com) < setores.MINIMO_DE_EMPRESAS:
                continue
            publico_em = max(
                p.numeros_publicos_em for p in com if p.numeros_publicos_em is not None
            )
            mediana = statistics.median(p.numeros[nome] for p in com)
            medianas[nome] = campo(
                _na_saida(nome, mediana),
                fonte=FONTE_DOS_NUMEROS,
                publico_em=publico_em,
                visto_em=None,
            )
        return medianas

    def comparaveis(self, cnpj: str, como_era_em: date) -> ComparaveisServidos | None:
        """Os comparáveis do CNPJ como eram em `como_era_em`, só com o que o portão libera; None se o CNPJ
        não é de empresa, se não tinha FCA no dia, se o setor não cai em grupo ou se o portão nega o setor."""
        normal = cnpj_.normalizar_cnpj(cnpj)
        if not normal:
            raise ValueError(f"CNPJ inválido: {cnpj!r}")
        if not all(
            self.permitido(FONTE_DO_CADASTRO, nome, False) for nome in ("cnpj", "setor")
        ):
            return None
        if not e_empresa(self.porta, normal):
            return None
        cadastros = self._cadastros_do_dia(como_era_em)
        dela = cadastros[cadastros["cnpj"] == normal]
        if dela.empty or dela["grupo"].iloc[0] == setores.SEM_GRUPO:
            return None
        grupo = str(dela["grupo"].iloc[0])
        do_grupo = self._companhias_do_grupo(cadastros, grupo, como_era_em)
        # a trava de pessoa em lote, a cada pedido e depois da memória: uma pergunta à rede pelo grupo inteiro
        e_empresa_cada_uma = e_empresas(self.porta, list(do_grupo))
        companhias = {
            cnpj: companhia
            for cnpj, companhia in do_grupo.items()
            if cnpj == normal or e_empresa_cada_uma.get(cnpj, False)
        }
        pedida = companhias[normal]
        # sem direito à receita, a ordem não pode entregá-la: os pares vão pela ordem do CNPJ
        pela_receita = self.permitido(FONTE_DOS_NUMEROS, "receita", False)
        pares = sorted(
            (
                c
                for c in companhias.values()
                if c.cnpj != normal and c.exercicio is not None
            ),
            key=lambda c: (
                -c.numeros.get("receita", float("-inf")) if pela_receita else 0.0,
                c.cnpj,
            ),
        )
        return self._resposta(normal, como_era_em, grupo, pedida, pares)

    def _resposta(
        self,
        normal: str,
        como_era_em: date,
        grupo: str,
        pedida: _Companhia,
        pares: list[_Companhia],
    ) -> ComparaveisServidos:
        linha_da_pedida, fontes = self._servida(pedida)
        corpo: dict[str, object] = {
            "cnpj": normal,
            "como_era_em": como_era_em.isoformat(),
        }
        if self.permitido(FONTE_DO_CADASTRO, "grupo_de_setores", True):
            corpo["grupo_de_setores"] = campo(
                GRUPOS_DE_FORA[grupo],
                fonte=FONTE_DO_CADASTRO,
                publico_em=pedida.cadastro_publico_em,
                visto_em=None,
            )
        cabem = max(self.linhas_maximas - 1, 0)
        servidos = []
        for par in pares[:cabem]:
            linha, fontes_do_par = self._servida(par)
            servidos.append(linha)
            fontes |= fontes_do_par
        corpo |= {
            "empresa_pedida": linha_da_pedida,
            "pares": servidos,
            "cortada": len(pares) > cabem,
        }
        medianas = self._medianas(pares)
        if medianas:
            corpo["medianas_dos_pares"] = medianas
            fontes.add(FONTE_DOS_NUMEROS)
        numeros = {
            nome: (nome,)
            if self.permitido(FONTE_DOS_NUMEROS, nome, nome in DERIVADOS)
            else ()
            for nome in (*NUMEROS, *RAZOES)
        }
        nao_disponiveis = nao_disponivel.nao_disponiveis(numeros)
        corpo[NAO_DISPONIVEIS] = [NOMES_DE_FORA[nome] for nome in nao_disponiveis]
        corpo["limites"] = limites(
            [nome for nome, campos in numeros.items() if campos], nao_disponiveis
        )
        return ComparaveisServidos(corpo, fontes, 1 + len(servidos))
