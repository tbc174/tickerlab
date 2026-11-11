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
portão some da resposta, sem `null`; sem o setor, nada sai.
"""

import math
import statistics
import unicodedata
from dataclasses import dataclass, field, replace
from datetime import date

import pandas as pd

from base import cnpj as cnpj_
from base import indicadores_de_caixa as caixa
from base.porta import Porta
from base.porta.rede import views
from base.regras import LINHA_DO_LUCRO
from src import setores
from src.api_externa.conjuntos import Permitido
from src.api_externa.conjuntos.empresas import e_empresa, e_empresas
from src.api_externa.envelope import campo

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
# contas nossas sobre as linhas da CVM (somas e divisões), não o dado como a fonte publicou
DERIVADOS = frozenset({"grupo_de_setores", "ebitda", "divida_liquida", *RAZOES})
# de que colunas da tabela sai cada campo que não é coluna dela (o teste de linhagem confere que existem)
_LINHAS_DO_DFP = ("demonstracao", "conta", "descricao", "valor")
ORIGEM_DAS_CONTAS: dict[str, tuple[str, ...]] = {
    "grupo_de_setores": ("setor",),
    "exercicio": ("fim",),
    **{nome: _LINHAS_DO_DFP for nome in (*NUMEROS, *RAZOES)},
}

LIMITES = (
    "Cada campo traz a fonte e o dia em que ficou público: nada publicado depois de known_at entra.",
    (
        "Os pares são as companhias abertas do mesmo grupo de setores, pelo setor informado à CVM no FCA; "
        "só entra quem tinha DFP de um exercício recente no dia. Não cobre empresa fechada."
    ),
    (
        "Os números são do DFP (consolidado; sem ele, o individual), em reais, como a companhia publicou; "
        "EBITDA, dívida líquida e as razões são contas do TickerLab sobre essas linhas. Bancos e seguradoras "
        "têm outro plano de contas: as razões deles não se comparam às das outras empresas."
    ),
    (
        "A mediana de cada razão só sai com pelo menos 8 pares que a têm. Comparação não é opinião sobre a "
        "empresa, e nada aqui é recomendação de investimento."
    ),
    "Pessoa natural (MEI, empresário individual) não é servida.",
)


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
    numeros: dict[str, float] = field(default_factory=dict)
    numeros_publicos_em: date | None = None


def _simples(texto: object) -> str:
    sem = unicodedata.normalize("NFD", str(texto))
    return "".join(c for c in sem if unicodedata.category(c) != "Mn").lower().strip()


def _profundidade(conta: str) -> int:
    return conta.count(".")


def _um(linhas: pd.DataFrame) -> float | None:
    """O valor da primeira linha achada; a linha com o valor vazio (NaN na base) conta como conta que falta."""
    valores = linhas["valor"].dropna()
    return None if valores.empty else float(valores.iloc[0])


def _soma(*valores: float | None) -> float | None:
    presentes = [v for v in valores if v is not None]
    return sum(presentes) if presentes else None


def _do_balanco(
    linhas: pd.DataFrame, demonstracao: str, conta: str, comeco: str
) -> float | None:
    """A conta do balanço pelo código e pelo começo da descrição (as regras de `src.demonstracoes`)."""
    achadas = linhas[
        (linhas["demonstracao"] == demonstracao)
        & (linhas["conta"] == conta)
        & linhas["s"].str.startswith(comeco)
    ]  # fmt: skip
    return _um(achadas)


def _patrimonio(linhas: pd.DataFrame) -> float | None:
    bpp = linhas[linhas["demonstracao"] == "BPP"]
    return _um(
        bpp[
            (bpp["conta"].map(_profundidade) == 1)
            & bpp["s"].str.startswith("patrimonio liquido")
        ]
    )


def _lucro(linhas: pd.DataFrame) -> float | None:
    dre = linhas[
        (linhas["demonstracao"] == "DRE") & (linhas["conta"].map(_profundidade) == 1)
    ]
    return _um(
        dre[dre["descricao"].map(lambda d: bool(LINHA_DO_LUCRO.match(str(d).strip())))]
    )


def _ebitdas(exercicios: list[pd.DataFrame]) -> dict[tuple[str, pd.Timestamp], float]:
    """O EBITDA de cada (cnpj, fim) pela mesma conta da ficha de caixa (`base.indicadores_de_caixa`: EBIT +
    D&A), numa conta só para todas as companhias (o período lá já separa por cnpj e grupo)."""
    if not exercicios:
        return {}
    tabela = caixa.indicadores_de_caixa(pd.concat(exercicios, ignore_index=True))
    tabela = tabela[tabela["ebitda"].notna()]
    return {
        (str(linha.cnpj), pd.Timestamp(linha.fim)): float(linha.ebitda)
        for linha in tabela.itertuples(index=False)
    }


def _divida_liquida(linhas: pd.DataFrame) -> float | None:
    """Empréstimos e financiamentos (curto e longo prazo) menos caixa e aplicações; sem a dívida ou sem o
    caixa, não há conta (a falta não vira zero)."""
    divida = _soma(
        _do_balanco(linhas, "BPP", "2.01.04", "emprestimos e financiamentos"),
        _do_balanco(linhas, "BPP", "2.02.01", "emprestimos e financiamentos"),
    )
    caixa_ = _do_balanco(linhas, "BPA", "1.01.01", "caixa")
    if divida is None or caixa_ is None:
        return None
    return (
        divida - caixa_ - (_do_balanco(linhas, "BPA", "1.01.02", "aplicacoes") or 0.0)
    )


def _dividir(numerador: float | None, denominador: float | None) -> float | None:
    """A razão só com o denominador positivo: sobre receita, patrimônio ou EBITDA negativos ela engana."""
    if numerador is None or denominador is None or denominador <= 0:
        return None
    return numerador / denominador


def numeros_do_exercicio(
    linhas: pd.DataFrame, ebitda: float | None
) -> dict[str, float]:
    """Os números e as razões de um exercício, a partir das linhas do DFP de um grupo (con ou ind) e do
    EBITDA já calculado (`_ebitdas`)."""
    linhas = linhas.assign(s=linhas["descricao"].map(_simples))
    dre = linhas[linhas["demonstracao"] == "DRE"]
    receita = _um(dre[dre["conta"] == "3.01"])
    lucro = _lucro(linhas)
    patrimonio = _patrimonio(linhas)
    divida = _divida_liquida(linhas)
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
    # só número finito sai: o JSON da API não leva NaN nem infinito
    return {
        nome: valor
        for nome, valor in valores.items()
        if valor is not None and math.isfinite(valor)
    }


def _do_exercicio(linhas: pd.DataFrame) -> pd.DataFrame:
    """As linhas do grupo consolidado (sem ele, do individual), uma por conta: a da entrega mais nova."""
    grupo = CONSOLIDADO if (linhas["grupo"] == CONSOLIDADO).any() else INDIVIDUAL
    linhas = linhas[linhas["grupo"] == grupo]
    chave = ["demonstracao", "conta", "inicio"]
    return linhas.sort_values(["divulgado_em", "versao"]).drop_duplicates(
        chave, keep="last"
    )


def _exercicios_recentes(
    dfps: pd.DataFrame, mais_velho: pd.Timestamp
) -> dict[str, tuple[pd.Timestamp, pd.DataFrame]]:
    """O último exercício de cada companhia (cnpj formatado), se não for mais velho que `mais_velho`: o fim e
    as linhas dele (`_do_exercicio`)."""
    exercicios = {}
    for formatado, linhas in (
        {} if dfps.empty else dict(tuple(dfps.groupby("cnpj")))
    ).items():
        fim = pd.Timestamp(linhas["fim"].max())
        if fim >= mais_velho:
            exercicios[str(formatado)] = (
                fim,
                _do_exercicio(linhas[linhas["fim"] == fim]),
            )
    return exercicios


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
        )

    def _companhias(
        self, cadastros: pd.DataFrame, como_era_em: date
    ) -> dict[str, _Companhia]:
        """Cada companhia dos cadastros com os números do último DFP recente (sem ele, só o cadastro)."""
        dfps = self._dfps(list(cadastros["cnpj"]), como_era_em)
        exercicios = _exercicios_recentes(
            dfps, pd.Timestamp(como_era_em) - IDADE_MAXIMA_DO_EXERCICIO
        )
        ebitdas = _ebitdas([linhas for _fim, linhas in exercicios.values()])
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
                fim, do_exercicio = exercicios[formatado]
                companhia = replace(
                    companhia,
                    exercicio=fim.date(),
                    numeros=numeros_do_exercicio(
                        do_exercicio, ebitdas.get((formatado, fim))
                    ),
                    numeros_publicos_em=pd.Timestamp(
                        do_exercicio["divulgado_em"].max()
                    ).date(),
                )
            companhias[companhia.cnpj] = companhia
        return companhias

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
                valores[nome],
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
                mediana, fonte=FONTE_DOS_NUMEROS, publico_em=publico_em, visto_em=None
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
        cadastros = self._cadastros(como_era_em)
        dela = cadastros[cadastros["cnpj"] == normal]
        if dela.empty or dela["grupo"].iloc[0] == setores.SEM_GRUPO:
            return None
        grupo = str(dela["grupo"].iloc[0])
        candidatas = cadastros[(cadastros["grupo"] == grupo)]
        # a trava de pessoa em lote: uma pergunta à rede pelo grupo inteiro, não uma por candidata
        e_empresa_cada_uma = e_empresas(self.porta, candidatas["cnpj"])
        candidatas = candidatas[
            (candidatas["cnpj"] == normal) | candidatas["cnpj"].map(e_empresa_cada_uma)
        ]
        companhias = self._companhias(candidatas, como_era_em)
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
        corpo["limites"] = list(LIMITES)
        return ComparaveisServidos(corpo, fontes, 1 + len(servidos))
