"""Capacidade de endividamento por regra declarada (protótipo B, DCM, do dossiê da plataforma; B-22).

Responde "quanto mais de dívida cabe" pelas regras que **quem usa declara** (`Regras`), nunca por um
limite que o TickerLab ache bom:

- **alavancagem:** dívida líquida ÷ EBITDA até L → cabem L × EBITDA − dívida líquida;
- **cobertura de juros:** (EBITDA ou EBIT) ÷ despesa financeira de pelo menos k, com a dívida nova
  custando a taxa declarada t → cabem (base ÷ k − despesa financeira) ÷ t;
- **caixa mínimo:** um ano de juros da dívida nova sai do caixa de hoje sem deixá-lo abaixo do
  mínimo M → cabem (caixa − M) ÷ t.

A capacidade é a menor entre as regras declaradas, e o resultado diz qual regra amarra. Regra que já
não é cumprida com os números de hoje não deixa caber nada (capacidade zero, `cumprida_hoje` falso).

Os insumos são os indicadores que a ficha já calcula (`src/fundamentos.py`: 12 meses, balanço mais
recente, dívida bruta, caixa, dívida líquida), sobre as demonstrações **como eram** no dia pedido (só
o que a CVM já tinha recebido). O que falta fica "não observado", com o motivo; nada é estimado, e
nada aqui é opinião de risco nem recomendação. Tipos simples, sem Streamlit (fáceis de virar JSON).
"""

from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field, replace
from datetime import date

import pandas as pd
import sqlalchemy as sa

from base import cnpj as cnpj_
from src import fundamentos as fu
from src.banco.demonstracoes import DadosDaEmpresa, dados_da_empresa
from src.rastro import DocumentoUsado, Rastro, datas_em_texto
from src.relatorio_empresa import FONTE_DA_CVM, documentos_usados

VERSAO_DO_CALCULO = "capacidade 1"  # sobe quando uma fórmula abaixo mudar
ALAVANCAGEM, COBERTURA, CAIXA_MINIMO = "alavancagem", "cobertura", "caixa_minimo"
BASES_DA_COBERTURA = ("ebitda", "ebit")
PONTOS_BASE = 10_000  # 1 ponto-base = 0,01% ao ano
CHOQUES_NO_EBITDA = (
    -0.30,
    -0.20,
    -0.10,
    0.0,
    0.10,
)  # fração do tamanho do EBITDA de hoje
CHOQUES_NA_TAXA_EM_PB = (-200, -100, 0, 100, 200)

FORMULA_DO_EBITDA = (
    "EBIT + depreciação e amortização (12 meses), como no EV/EBITDA da ficha"
)
FORMULA_DO_EBIT = "resultado antes do resultado financeiro e dos tributos (12 meses)"
FORMULA_DA_DESPESA = "despesas financeiras da DRE, em módulo (12 meses)"
FORMULAS = {
    ALAVANCAGEM: "max(0, L × EBITDA − dívida líquida); L = dívida líquida ÷ EBITDA máxima declarada",
    COBERTURA: (
        "max(0, (base ÷ k − despesa financeira) ÷ t); base = EBITDA ou EBIT (12 meses), "
        "k = cobertura mínima declarada, t = taxa declarada da dívida nova"
    ),
    CAIXA_MINIMO: (
        "max(0, (caixa − M) ÷ t); M = caixa mínimo declarado, t = taxa declarada da dívida nova "
        "(um ano de juros da dívida nova sai do caixa de hoje)"
    ),
}
FORMULA_DA_CAPACIDADE = "a menor capacidade entre as regras declaradas"
EBITDA_NAO_POSITIVO = (
    "EBITDA negativo ou zero: dívida líquida ÷ EBITDA não tem sentido, e nenhuma dívida nova "
    "cabe por esta regra."
)
REGRA_SEM_INSUMO = "A regra {regra} não pôde ser calculada: falta {insumo}."
TAXA_NAO_POSITIVA = "Taxa da dívida nova zero ou negativa depois do choque."
LIMITES = (
    (
        "As regras são as que você declarou, não um limite recomendado: o TickerLab não diz qual "
        "alavancagem ou cobertura é adequada. Nada aqui é recomendação."
    ),
    (
        "A dívida nova é tratada como gasta (não fica no caixa) e custa a taxa declarada; a despesa "
        "financeira de hoje fica como está (o choque na taxa vale só para a dívida nova)."
    ),
    (
        "A despesa financeira é a linha inteira da DRE (juros, variação cambial, outras), não só os "
        "juros da dívida."
    ),
    (
        "Números consolidados da última DFP e do último ITR que a CVM já tinha recebido no dia; "
        "dívida bruta, caixa e dívida líquida como na ficha (fórmula no rastro de cada um)."
    ),
)


@dataclass(frozen=True)
class Regras:
    """As regras declaradas por quem usa; None: a regra não entra."""

    alavancagem_maxima: float | None = None  # dívida líquida ÷ EBITDA, em vezes
    cobertura_minima: float | None = None  # base ÷ despesa financeira, em vezes
    base_da_cobertura: str = "ebitda"  # um de BASES_DA_COBERTURA
    caixa_minimo: float | None = None  # em reais
    taxa_da_divida_nova: float | None = None  # fração ao ano (0,14 = 14% a.a.)

    def __post_init__(self) -> None:
        if (self.alavancagem_maxima, self.cobertura_minima, self.caixa_minimo) == (
            None,
        ) * 3:
            raise ValueError("declare ao menos uma regra")
        if self.base_da_cobertura not in BASES_DA_COBERTURA:
            raise ValueError(f"base da cobertura {self.base_da_cobertura!r} não existe")
        for nome in ("alavancagem_maxima", "cobertura_minima"):
            valor = getattr(self, nome)
            if valor is not None and valor <= 0:
                raise ValueError(f"{nome} precisa ser positiva")
        if self.caixa_minimo is not None and self.caixa_minimo < 0:
            raise ValueError("caixa_minimo não pode ser negativo")
        pede_taxa = self.cobertura_minima is not None or self.caixa_minimo is not None
        if pede_taxa and (
            self.taxa_da_divida_nova is None or self.taxa_da_divida_nova <= 0
        ):
            raise ValueError(
                "cobertura e caixa mínimo pedem a taxa da dívida nova, positiva"
            )

    @classmethod
    def de_dict(cls, dados: dict) -> "Regras":
        """As regras a partir do JSON da API (campos que não existem levantam erro)."""
        return cls(**dados)

    def como_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Insumo:
    """Um número que entra nas regras, com o rastro; `valor` None: não observado (ver `motivo`)."""

    chave: str  # "ebitda", "ebit", "despesa_financeira", "divida_bruta", "caixa", "divida_liquida"
    nome: str
    valor: float | None  # em reais
    periodo: str  # "12 meses até 30/06/2026", "balanço de 30/06/2026"
    rastro: Rastro
    motivo: str = ""


@dataclass(frozen=True)
class Insumos:
    """Os insumos de um emissor como eram em `como_era_em`."""

    ebitda: Insumo
    ebit: Insumo
    despesa_financeira: Insumo
    divida_bruta: Insumo
    caixa: Insumo
    divida_liquida: Insumo

    def todos(self) -> tuple[Insumo, ...]:
        return (
            self.ebitda,
            self.ebit,
            self.despesa_financeira,
            self.divida_bruta,
            self.caixa,
            self.divida_liquida,
        )


@dataclass(frozen=True)
class FolgaDaRegra:
    """Quanto de dívida nova cabe por uma regra; `capacidade` None: não observado."""

    regra: str  # ALAVANCAGEM, COBERTURA ou CAIXA_MINIMO
    capacidade: float | None  # em reais, nunca negativa
    cumprida_hoje: bool | None  # a regra vale com os números de hoje, sem dívida nova
    rastro: Rastro
    motivo: str = ""


@dataclass(frozen=True)
class CapacidadeDeEndividamento:
    """O resultado: a folga de cada regra, a capacidade (a menor) e a regra que amarra."""

    emissor_cnpj: str | None
    como_era_em: date
    regras: Regras
    insumos: tuple[Insumo, ...]
    folgas: tuple[FolgaDaRegra, ...]
    capacidade: (
        float | None
    )  # em reais; None quando alguma regra declarada ficou sem número
    regra_que_amarra: str | None
    rastro: Rastro
    motivo: str = ""
    limites: tuple[str, ...] = LIMITES

    def como_dict(self) -> dict:
        """Para a API: datas em texto ISO."""
        return {k: datas_em_texto(v) for k, v in asdict(self).items()}


# --- as regras ------------------------------------------------------------------------------------
def _documentos_de(*insumos: Insumo) -> list[DocumentoUsado]:
    vistos: dict[str, DocumentoUsado] = {}
    for insumo in insumos:
        for documento in insumo.rastro.documentos:
            vistos.setdefault(documento.nome, documento)
    return list(vistos.values())


def _rastro(formula: str, *insumos: Insumo) -> Rastro:
    return Rastro.dos_documentos(
        formula, VERSAO_DO_CALCULO, FONTE_DA_CVM, _documentos_de(*insumos)
    )


def _sem_insumo(regra: str, *insumos: Insumo) -> FolgaDaRegra | None:
    faltando = next((i for i in insumos if i.valor is None), None)
    if faltando is None:
        return None
    motivo = REGRA_SEM_INSUMO.format(regra=regra, insumo=faltando.nome.lower())
    if faltando.motivo:
        motivo += f" {faltando.motivo}"
    return FolgaDaRegra(regra, None, None, _rastro(FORMULAS[regra], *insumos), motivo)


def _folga(regra: str, cabe: float, insumos: Sequence[Insumo]) -> FolgaDaRegra:
    return FolgaDaRegra(
        regra, max(0.0, cabe), cabe >= 0, _rastro(FORMULAS[regra], *insumos)
    )


def _alavancagem(insumos: Insumos, maxima: float) -> FolgaDaRegra:
    usados = (insumos.ebitda, insumos.divida_liquida)
    if (sem := _sem_insumo(ALAVANCAGEM, *usados)) is not None:
        return sem
    ebitda, liquida = insumos.ebitda.valor, insumos.divida_liquida.valor
    assert ebitda is not None and liquida is not None
    if ebitda <= 0:
        rastro = _rastro(FORMULAS[ALAVANCAGEM], *usados)
        return FolgaDaRegra(ALAVANCAGEM, 0.0, False, rastro, EBITDA_NAO_POSITIVO)
    return _folga(ALAVANCAGEM, maxima * ebitda - liquida, usados)


def _cobertura(insumos: Insumos, regras: Regras, taxa: float) -> FolgaDaRegra:
    base = insumos.ebitda if regras.base_da_cobertura == "ebitda" else insumos.ebit
    usados = (base, insumos.despesa_financeira)
    if (sem := _sem_insumo(COBERTURA, *usados)) is not None:
        return sem
    assert base.valor is not None and insumos.despesa_financeira.valor is not None
    assert regras.cobertura_minima is not None
    sobra = base.valor / regras.cobertura_minima - insumos.despesa_financeira.valor
    return _folga(COBERTURA, sobra / taxa, usados)


def _caixa_minimo(insumos: Insumos, minimo: float, taxa: float) -> FolgaDaRegra:
    if (sem := _sem_insumo(CAIXA_MINIMO, insumos.caixa)) is not None:
        return sem
    assert insumos.caixa.valor is not None
    return _folga(CAIXA_MINIMO, (insumos.caixa.valor - minimo) / taxa, (insumos.caixa,))


def folgas_das_regras(insumos: Insumos, regras: Regras) -> tuple[FolgaDaRegra, ...]:
    """A folga de cada regra declarada, na ordem alavancagem, cobertura, caixa mínimo."""
    folgas = []
    if regras.alavancagem_maxima is not None:
        folgas.append(_alavancagem(insumos, regras.alavancagem_maxima))
    taxa = regras.taxa_da_divida_nova
    if regras.cobertura_minima is not None and taxa is not None:
        folgas.append(_cobertura(insumos, regras, taxa))
    if regras.caixa_minimo is not None and taxa is not None:
        folgas.append(_caixa_minimo(insumos, regras.caixa_minimo, taxa))
    return tuple(folgas)


def _a_menor(folgas: Sequence[FolgaDaRegra]) -> tuple[float | None, str | None, str]:
    """(capacidade, regra que amarra, motivo): sem número em alguma regra, não há capacidade."""
    sem_numero = [f for f in folgas if f.capacidade is None]
    if sem_numero:
        return None, None, " ".join(f.motivo for f in sem_numero)
    amarra = min(folgas, key=lambda f: f.capacidade or 0.0)
    return amarra.capacidade, amarra.regra, ""


def calcular_capacidade(
    insumos: Insumos,
    regras: Regras,
    como_era_em: date,
    emissor_cnpj: str | None = None,
) -> CapacidadeDeEndividamento:
    """A capacidade pelas regras declaradas, sobre insumos já lidos como eram em `como_era_em`."""
    folgas = folgas_das_regras(insumos, regras)
    capacidade, amarra, motivo = _a_menor(folgas)
    return CapacidadeDeEndividamento(
        emissor_cnpj=emissor_cnpj,
        como_era_em=como_era_em,
        regras=regras,
        insumos=insumos.todos(),
        folgas=folgas,
        capacidade=capacidade,
        regra_que_amarra=amarra,
        rastro=_rastro(FORMULA_DA_CAPACIDADE, *insumos.todos()),
        motivo=motivo,
    )


# --- sensibilidade -------------------------------------------------------------------------------
@dataclass(frozen=True)
class CelulaDaSensibilidade:
    choque_no_ebitda: float  # fração do tamanho do EBITDA de hoje (−0,10 = 10% a menos)
    choque_na_taxa_em_pb: int  # pontos-base somados à taxa da dívida nova
    capacidade: float | None
    regra_que_amarra: str | None
    motivo: str = ""


@dataclass(frozen=True)
class TabelaDeSensibilidade:
    """A capacidade contra choques no EBITDA (linhas) e na taxa da dívida nova (colunas)."""

    choques_no_ebitda: tuple[float, ...]
    choques_na_taxa_em_pb: tuple[int, ...]
    celulas: tuple[
        tuple[CelulaDaSensibilidade, ...], ...
    ]  # [linha do EBITDA][coluna da taxa]
    rastro: Rastro
    hipotese: str = (
        "O choque no EBITDA soma ao EBITDA e ao EBIT o mesmo valor em reais (a depreciação não "
        "muda); o choque na taxa vale só para a dívida nova."
    )
    limites: tuple[str, ...] = field(default=LIMITES)

    def como_dict(self) -> dict:
        return {k: datas_em_texto(v) for k, v in asdict(self).items()}


def com_choque_no_ebitda(insumos: Insumos, choque: float) -> Insumos:
    """Os insumos com o EBITDA (e o EBIT, no mesmo valor) mudados em `choque` × |EBITDA|.

    Pelo tamanho, não pelo sinal: um choque negativo sempre diminui o resultado, também quando o
    EBITDA já é negativo."""
    ebitda = insumos.ebitda.valor
    if ebitda is None or choque == 0:
        return insumos
    delta = choque * abs(ebitda)

    def mudado(insumo: Insumo) -> Insumo:
        return (
            insumo
            if insumo.valor is None
            else replace(insumo, valor=insumo.valor + delta)
        )

    return replace(insumos, ebitda=mudado(insumos.ebitda), ebit=mudado(insumos.ebit))


def _celula(
    insumos: Insumos, regras: Regras, choque_no_ebitda: float, choque_em_pb: int
) -> CelulaDaSensibilidade:
    taxa = regras.taxa_da_divida_nova
    if taxa is not None:
        taxa += choque_em_pb / PONTOS_BASE
        if taxa <= 0:
            return CelulaDaSensibilidade(
                choque_no_ebitda, choque_em_pb, None, None, TAXA_NAO_POSITIVA
            )
        regras = replace(regras, taxa_da_divida_nova=taxa)
    folgas = folgas_das_regras(com_choque_no_ebitda(insumos, choque_no_ebitda), regras)
    capacidade, amarra, motivo = _a_menor(folgas)
    return CelulaDaSensibilidade(
        choque_no_ebitda, choque_em_pb, capacidade, amarra, motivo
    )


def tabela_de_sensibilidade(
    insumos: Insumos,
    regras: Regras,
    choques_no_ebitda: Iterable[float] = CHOQUES_NO_EBITDA,
    choques_na_taxa_em_pb: Iterable[int] = CHOQUES_NA_TAXA_EM_PB,
) -> TabelaDeSensibilidade:
    """A capacidade em cada par de choques (sem regra que use a taxa, as colunas se repetem)."""
    linhas, colunas = tuple(choques_no_ebitda), tuple(choques_na_taxa_em_pb)
    return TabelaDeSensibilidade(
        choques_no_ebitda=linhas,
        choques_na_taxa_em_pb=colunas,
        celulas=tuple(
            tuple(_celula(insumos, regras, choque, pb) for pb in colunas)
            for choque in linhas
        ),
        rastro=_rastro(
            f"{FORMULA_DA_CAPACIDADE}, com EBITDA + choque × |EBITDA| e taxa + choque ÷ 10.000",
            *insumos.todos(),
        ),
    )


# --- os insumos, das demonstrações como eram --------------------------------------------------------
@dataclass(frozen=True)
class DemonstracoesComoEram:
    dados: DadosDaEmpresa
    sem_a_versao_do_dia: tuple[
        str, ...
    ]  # documentos reapresentados depois do dia (ver abaixo)


def _dia(valor: object) -> date | None:
    return None if valor is None or pd.isna(valor) else pd.Timestamp(valor).date()  # type: ignore[arg-type]


def demonstracoes_como_eram(dados: DadosDaEmpresa, dia: date) -> DemonstracoesComoEram:
    """Só os documentos que a CVM já tinha recebido em `dia` (sem dia conhecido, fica de fora).

    O banco guarda só a versão mais nova de cada documento. Um documento de período já fechado em
    `dia` que foi reapresentado depois (versão > 1, recebida depois do dia) pode ter tido uma versão
    pública no dia que não está guardada: ele vai em `sem_a_versao_do_dia`, e os números ficam não
    observados (usar o documento anterior seria mostrar um passado que não existiu)."""
    documentos = dados.documentos
    if documentos.empty:
        return DemonstracoesComoEram(dados, ())
    recebidos = documentos["recebido_em"].map(_dia)
    publicos = recebidos.map(lambda d: d is not None and d <= dia)
    fora = documentos[~publicos]
    sem_a_versao = tuple(
        f"{linha.documento} de {_dia(linha.referencia):%d/%m/%Y}"
        for linha in fora.itertuples(index=False)
        if int(linha.versao) > 1 and (_dia(linha.referencia) or dia) < dia
    )
    ficam = documentos[publicos]
    chaves = set(
        zip(ficam["documento"], ficam["referencia"], ficam["versao"], strict=True)
    )
    contas = dados.contas
    if not contas.empty:
        contas = contas[
            [
                chave in chaves
                for chave in zip(
                    contas["documento"],
                    contas["referencia"],
                    contas["versao"],
                    strict=True,
                )
            ]
        ]
    return DemonstracoesComoEram(
        replace(dados, contas=contas, documentos=ficam), sem_a_versao
    )


def _documentos_dos(
    dados: DadosDaEmpresa, usados: Iterable[tuple[str, date]]
) -> list[DocumentoUsado]:
    usados_ = set(usados)
    documentos = dados.documentos
    if documentos.empty:
        return []
    escolhidos = documentos[
        [
            (d, r) in usados_
            for d, r in zip(
                documentos["documento"], documentos["referencia"], strict=True
            )
        ]
    ]
    return list(documentos_usados(escolhidos))


def _insumo(
    chave: str,
    nome: str,
    valor: float | None,
    periodo: str,
    formula: str,
    documentos: list[DocumentoUsado],
    motivo: str = "",
) -> Insumo:
    if valor is None and not motivo:
        motivo = "A conta não aparece nas demonstrações públicas no dia."
    rastro = Rastro.dos_documentos(
        formula, f"fundamentos {fu.VERSAO_DOS_FUNDAMENTOS}", FONTE_DA_CVM, documentos
    )
    return Insumo(chave, nome, None if motivo else valor, periodo, rastro, motivo)


def _da_ficha(
    indicador: fu.Indicador, documentos: list[DocumentoUsado], motivo: str
) -> Insumo:
    return _insumo(
        indicador.chave,
        indicador.nome,
        indicador.valor,
        indicador.base,
        fu.FORMULAS[indicador.chave],
        documentos,
        motivo or indicador.motivo,
    )


def insumos_das_demonstracoes(dados: DadosDaEmpresa, como_era_em: date) -> Insumos:
    """Os insumos das regras, pelas mesmas funções da ficha, sobre o que era público no dia."""
    cortadas = demonstracoes_como_eram(dados, como_era_em)
    dados = cortadas.dados
    motivo = (
        "Reapresentado depois do dia, sem a versão que era pública nele: "
        + ", ".join(cortadas.sem_a_versao_do_dia)
        + "."
        if cortadas.sem_a_versao_do_dia
        else ""
    )
    ficha = fu.calcular(dados, preco=None)
    if ficha.financeira:
        motivo = motivo or fu.NAO_SE_APLICA_A_FINANCEIRAS
    ttm, base_12m, usados_12m = fu.doze_meses(dados.contas)
    _, dia_do_balanco, documento_do_balanco = fu.balanco_mais_recente(dados.contas)
    do_12m = _documentos_dos(dados, usados_12m)
    do_balanco = _documentos_dos(
        dados, [(documento_do_balanco, dia_do_balanco)] if dia_do_balanco else []
    )
    ebit, depreciacao = ttm.get("ebit"), ttm.get("depreciacao")
    ebitda = None if ebit is None or depreciacao is None else ebit + depreciacao
    despesa = ttm.get("despesas_financeiras")
    return Insumos(
        ebitda=_insumo("ebitda", "EBITDA (12 meses)", ebitda, base_12m, FORMULA_DO_EBITDA, do_12m, motivo),
        ebit=_insumo("ebit", "EBIT (12 meses)", ebit, base_12m, FORMULA_DO_EBIT, do_12m, motivo),
        despesa_financeira=_insumo(
            "despesa_financeira", "Despesa financeira (12 meses)",
            None if despesa is None else abs(despesa), base_12m, FORMULA_DA_DESPESA, do_12m, motivo,
        ),
        divida_bruta=_da_ficha(ficha["divida_bruta"], do_balanco, motivo),
        caixa=_da_ficha(ficha["caixa"], do_balanco, motivo),
        divida_liquida=_da_ficha(ficha["divida_liquida"], do_balanco, motivo),
    )  # fmt: skip


def capacidade_do_emissor(
    conexao: sa.Connection, cnpj: str, regras: Regras, como_era_em: date
) -> CapacidadeDeEndividamento:
    """A capacidade de uma companhia aberta, como era em `como_era_em`."""
    cnpj_normal = cnpj_.normalizar_cnpj(cnpj)
    if cnpj_normal is None:
        raise ValueError(f"{cnpj!r} não é um CNPJ")
    dados = dados_da_empresa(conexao, cnpj_.formatar(cnpj_normal))
    insumos = insumos_das_demonstracoes(dados, como_era_em)
    return calcular_capacidade(insumos, regras, como_era_em, cnpj_normal)
