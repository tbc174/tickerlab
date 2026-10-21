"""A montagem do memorando por regra: cada seção escrita a partir do que o protótipo A já calcula.

Cada frase nasce junto com as evidências que cita (`_Bloco`); a frase cuja evidência ficou pública
depois do dia do memorando sai inteira (sem olhar o futuro), e a seção sem nenhuma frase diz o que
falta com uma lacuna em vez de calar. O texto só repete números já escritos nas evidências, e nunca
diz quanto a empresa vale: o DCF entra ao contrário (o crescimento que o preço do dia supõe), os comps
como a régua do que foi pago e o LBO com as premissas declaradas.

As entradas são tipos simples já calculados como eram no dia (`RelatorioDoCnpj`, `CompsPorTransacao`,
`ResultadoDoLbo`, a ficha do dossiê para os cruzamentos e os três tipos abaixo para pares, DCF reverso
e múltiplos). O memorando sai de `montar_memorando` já conferido (`conferencia.para_mostrar`).
"""

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import date

from src import cruzamentos
from src.analise_escrita.saida import Frase
from src.busca_por_cnpj import SECOES_DO_GRUPO_E_DA_REDE, RelatorioDoCnpj
from src.comps_por_transacao import CompsPorTransacao, ResumoDoMultiplo
from src.dossie import Ficha
from src.lbo import FONTE_DAS_PREMISSAS, ResultadoDoLbo
from src.memorando_ma import evidencia as ev
from src.memorando_ma.conferencia import para_mostrar
from src.memorando_ma.evidencia import Evidencia
from src.memorando_ma.formato import SECOES, Memorando, SecaoDoMemorando
from src.negociacoes import formatar_valor
from src.rastro import Rastro
from src.relatorio_empresa import Secao
from src.valuation import (
    CRESCIMENTO_MAXIMO,
    CRESCIMENTO_MINIMO,
    crescimento_implicito,
)

VERSAO_DO_CALCULO = (
    "memorando de M&A 1"  # sobe quando uma regra de escrita abaixo mudar
)
VEZES, FRACAO, REAIS = "vezes", "fração", "reais"
SECOES_DO_PERFIL = ("cadastro", *SECOES_DO_GRUPO_E_DA_REDE)
SECAO_DE_CREDITO = "credito"
# a lacuna que o memorando repete da busca por CNPJ: as tabelas proibidas no app (base/dossie.py)
PALAVRA_DO_DESLIGADO = "insolvência"
FORMULA_DO_CRESCIMENTO = (
    "o crescimento anual do caixa livre que faz o DCF (`src/valuation.py`) dar o preço do dia, com "
    "o desconto, a perpetuidade e os anos declarados"
)
FORMULA_DAS_PREMISSAS = "premissas declaradas pelo usuário"
LIMITES = (
    (
        "O memorando junta números já calculados, cada um com a sua fonte; não diz quanto a empresa "
        "vale nem se a compra é boa. Nada aqui é recomendação de investimento."
    ),
    (
        "O DCF entra ao contrário: o crescimento que o preço do dia supõe, com o desconto e a "
        "perpetuidade declarados, e nunca um valor por ação."
    ),
)


@dataclass(frozen=True)
class IndicadorContraOsPares:
    """Um indicador da empresa e a mediana do grupo de setor, no mesmo dia."""

    chave: str
    nome: str  # "Margem EBITDA"
    unidade: str  # VEZES, FRACAO ou REAIS
    valor: float
    mediana_dos_pares: float
    empresas: int  # quantas empresas do grupo entram na mediana
    nome_do_grupo: str
    rastro: Rastro  # o do valor da empresa
    rastro_da_mediana: Rastro


@dataclass(frozen=True)
class MultiploContraOHistorico:
    """O múltiplo do dia e a mediana do próprio histórico (`valuation.percentis_do_historico`)."""

    chave: str
    nome: str  # "P/L"
    atual: float
    mediana_do_historico: float
    anos: int
    rastro: Rastro
    rastro_do_historico: Rastro


@dataclass(frozen=True)
class PremissasDoDcfReverso:
    """O preço, o caixa livre e as ações do dia, mais as premissas declaradas (taxas em fração)."""

    preco: float
    caixa_livre: float
    acoes: float
    divida_liquida: float
    anos: int
    desconto: float
    perpetuidade: float
    rastro_do_mercado: Rastro  # o do preço, das ações e da dívida líquida
    rastro_do_caixa_livre: Rastro


@dataclass(frozen=True)
class EntradaDoMemorando:
    relatorio: RelatorioDoCnpj
    ficha: Ficha | None = None  # para os cruzamentos (cortados no dia)
    pares: tuple[IndicadorContraOsPares, ...] = ()
    dcf_reverso: PremissasDoDcfReverso | None = None
    multiplos: tuple[MultiploContraOHistorico, ...] = ()
    comps: CompsPorTransacao | None = None
    lbo: ResultadoDoLbo | None = None


@dataclass(frozen=True)
class _Bloco:
    texto: str
    evidencias: tuple[Evidencia, ...]

    def frase(self) -> Frase:
        return Frase(self.texto, tuple(e.id for e in self.evidencias))


# --- números escritos -----------------------------------------------------------------------------
def _decimal(valor: float, casas: int) -> str:
    return f"{valor:.{casas}f}".replace(".", ",")


def escrito(valor: float, unidade: str) -> str:
    """O número como o memorando escreve ("8,10 vezes", "23,1%", "R$ 495,2 mi")."""
    if unidade == VEZES:
        return f"{_decimal(valor, 2)} vezes"
    if unidade == FRACAO:
        return f"{_decimal(valor * 100, 1)}%"
    if unidade == REAIS:
        return formatar_valor(valor, "BRL")
    return _decimal(valor, 2)


def _anos(anos: int) -> str:
    return "1 ano" if anos == 1 else f"{anos} anos"


def _comparado(valor: float, referencia: float) -> str:
    if valor > referencia:
        return "acima da"
    return "abaixo da" if valor < referencia else "igual à"


def _premissa(id: str, afirmacao: str, valor: float, dia: date) -> Evidencia:
    rastro = Rastro(FORMULA_DAS_PREMISSAS, VERSAO_DO_CALCULO, FONTE_DAS_PREMISSAS, dia)
    return ev.do_rastro(id, afirmacao, valor, rastro)


def _lacuna_da_secao(chave: str, dia: date) -> _Bloco:
    afirmacao = f"{SECOES[chave]}: sem dado público até {dia:%d/%m/%Y}."
    return _Bloco(afirmacao, (ev.lacuna(f"{chave}.sem_dado", afirmacao),))


# --- perfil ---------------------------------------------------------------------------------------
def _itens_como_frases(
    secoes: Iterable[Secao], dia_da_ficha: date | None
) -> Iterator[_Bloco]:
    for secao in secoes:
        if secao.trancada:
            continue
        for item in secao.itens:
            evidencia = ev.do_item(secao.chave, item, dia_da_ficha)
            if evidencia is not None:
                yield _Bloco(f"{evidencia.afirmacao.rstrip('.')}.", (evidencia,))


def perfil(relatorio: RelatorioDoCnpj) -> list[_Bloco]:
    """O cadastro, o auditor, as controladas e a rede, item a item (o que está na ficha)."""
    secoes = [s for s in relatorio.secoes if s.chave in SECOES_DO_PERFIL]
    return list(_itens_como_frases(secoes, relatorio.como_era_em))


# --- pares, DCF reverso e múltiplos ---------------------------------------------------------------
def pares(indicadores: Iterable[IndicadorContraOsPares]) -> list[_Bloco]:
    blocos = []
    for i in indicadores:
        valor, mediana = (
            escrito(i.valor, i.unidade),
            escrito(i.mediana_dos_pares, i.unidade),
        )
        da_empresa = ev.do_rastro(
            f"pares.{i.chave}", f"{i.nome}: {valor}", i.valor, i.rastro
        )
        do_grupo = ev.do_rastro(
            f"pares.{i.chave}.mediana",
            f"Mediana de {i.nome} das {i.empresas} empresas do grupo {i.nome_do_grupo}: {mediana}",
            i.mediana_dos_pares,
            i.rastro_da_mediana,
        )
        texto = (
            f"{i.nome} de {valor}, {_comparado(i.valor, i.mediana_dos_pares)} mediana de "
            f"{mediana} das {i.empresas} empresas do grupo {i.nome_do_grupo}."
        )
        blocos.append(_Bloco(texto, (da_empresa, do_grupo)))
    return blocos


def _dcf_reverso(premissas: PremissasDoDcfReverso, dia: date) -> _Bloco:
    p = premissas
    declaradas = (
        f"desconto de {escrito(p.desconto, FRACAO)} ao ano, perpetuidade de "
        f"{escrito(p.perpetuidade, FRACAO)} ao ano e {_anos(p.anos)} de fluxo explícito"
    )
    da_premissa = _premissa(
        "dcf.premissas",
        f"Premissas declaradas do DCF reverso: {declaradas}",
        p.desconto,
        dia,
    )
    crescimento = crescimento_implicito(
        p.preco,
        p.caixa_livre,
        p.anos,
        p.desconto,
        p.perpetuidade,
        p.acoes,
        p.divida_liquida,
    )
    if crescimento is None:
        faixa = f"{escrito(CRESCIMENTO_MINIMO, FRACAO)} e {escrito(CRESCIMENTO_MAXIMO, FRACAO)}"
        afirmacao = f"Nenhum crescimento entre {faixa} ao ano faz o DCF dar o preço do dia com {declaradas}."
        return _Bloco(
            afirmacao, (ev.lacuna("dcf.crescimento_implicito", afirmacao), da_premissa)
        )
    dias = [
        d
        for d in (
            p.rastro_do_mercado.publicado_em,
            p.rastro_do_caixa_livre.publicado_em,
        )
        if d is not None
    ]
    rastro = Rastro(
        FORMULA_DO_CRESCIMENTO,
        VERSAO_DO_CALCULO,
        p.rastro_do_mercado.fonte_id,
        max(dias) if dias else None,  # sem dia público, a conferência reprova o número
        (*p.rastro_do_mercado.documentos, *p.rastro_do_caixa_livre.documentos),
        (p.rastro_do_caixa_livre.fonte_id, FONTE_DAS_PREMISSAS),
    )
    implicito = escrito(crescimento, FRACAO)
    do_preco = ev.do_rastro(
        "dcf.crescimento_implicito",
        f"Crescimento implícito no preço do dia: {implicito} ao ano",
        crescimento,
        rastro,
    )
    texto = (
        f"Com {declaradas} (premissas declaradas), o preço do dia supõe um crescimento de "
        f"{implicito} ao ano no caixa livre."
    )
    return _Bloco(texto, (do_preco, da_premissa))


def _multiplo(m: MultiploContraOHistorico) -> _Bloco:
    atual, mediana = escrito(m.atual, VEZES), escrito(m.mediana_do_historico, VEZES)
    do_dia = ev.do_rastro(
        f"multiplos.{m.chave}", f"{m.nome} do dia: {atual}", m.atual, m.rastro
    )
    do_historico = ev.do_rastro(
        f"multiplos.{m.chave}.historico",
        f"Mediana do {m.nome} nos {m.anos} anos do próprio histórico: {mediana}",
        m.mediana_do_historico,
        m.rastro_do_historico,
    )
    texto = (
        f"O {m.nome} do dia é de {atual}, {_comparado(m.atual, m.mediana_do_historico)} mediana "
        f"de {mediana} dos {m.anos} anos do próprio histórico."
    )
    return _Bloco(texto, (do_dia, do_historico))


def dcf_e_multiplos(
    premissas: PremissasDoDcfReverso | None,
    multiplos: Iterable[MultiploContraOHistorico],
    dia: date,
) -> list[_Bloco]:
    blocos = [_dcf_reverso(premissas, dia)] if premissas is not None else []
    return blocos + [_multiplo(m) for m in multiplos]


# --- comps por transação --------------------------------------------------------------------------
def _resumo(resumo: ResumoDoMultiplo, nome_do_grupo: str) -> _Bloco:
    chave = f"comps.{resumo.chave}"
    if (
        resumo.mediana is None
        or resumo.primeiro_quartil is None
        or resumo.terceiro_quartil is None
    ):
        afirmacao = f"{resumo.nome} pago no grupo {nome_do_grupo}: {resumo.motivo}."
        return _Bloco(afirmacao, (ev.lacuna(chave, afirmacao),))
    mediana = escrito(resumo.mediana, VEZES)
    q1, q3 = (
        escrito(resumo.primeiro_quartil, VEZES),
        escrito(resumo.terceiro_quartil, VEZES),
    )
    n = len(resumo.precedentes)
    afirmacao = (
        f"{resumo.nome} pago em {n} precedentes do grupo {nome_do_grupo} até a data: mediana de "
        f"{mediana}, primeiro quartil de {q1} e terceiro de {q3}"
    )
    evidencia = ev.do_rastro(chave, afirmacao, resumo.mediana, resumo.rastro)
    texto = (
        f"A mediana do {resumo.nome} pago em {n} precedentes do grupo {nome_do_grupo} foi de "
        f"{mediana}, com o primeiro quartil em {q1} e o terceiro em {q3}."
    )
    return _Bloco(texto, (evidencia,))


def comps_por_transacao(comps: CompsPorTransacao) -> list[_Bloco]:
    if comps.motivo:
        afirmacao = f"Comps por transação: {comps.motivo}."
        return [_Bloco(afirmacao, (ev.lacuna("comps.sem_setor", afirmacao),))]
    return [_resumo(r, comps.nome_do_grupo) for r in comps.multiplos]


# --- LBO ------------------------------------------------------------------------------------------
def lbo(resultado: ResultadoDoLbo) -> list[_Bloco]:
    """As premissas, o capital do acionista e a TIR e o MOIC (nunca o valor da empresa)."""
    p, dia = resultado.premissas, resultado.como_era_em
    entrada, saida = (
        escrito(p.multiplo_de_entrada, VEZES),
        escrito(p.multiplo_de_saida, VEZES),
    )
    declaradas = (
        f"compra a {entrada} o EBITDA de entrada, venda a {saida} o EBITDA do último ano e "
        f"{_anos(p.anos)} até a saída"
    )
    premissas = _premissa(
        "lbo.premissas",
        f"Premissas declaradas do LBO: {declaradas}",
        p.multiplo_de_entrada,
        dia,
    )
    capital = resultado.fontes_e_usos.capital_do_acionista
    do_capital = ev.do_rastro(
        "lbo.capital_do_acionista",
        f"Capital do acionista na compra: {escrito(capital, REAIS)}",
        capital,
        resultado.rastros["capital_do_acionista"],
    )
    blocos = [
        _Bloco(f"As premissas declaradas do LBO são {declaradas}.", (premissas,)),
        _Bloco(
            f"Com elas, o acionista põe {escrito(capital, REAIS)} na compra.",
            (premissas, do_capital),
        ),
    ]
    if resultado.tir is None or resultado.moic is None:
        afirmacao = f"TIR e MOIC do acionista: vazios porque {resultado.motivo}."
        return [*blocos, _Bloco(afirmacao, (ev.lacuna("lbo.tir", afirmacao),))]
    tir, moic = escrito(resultado.tir, FRACAO), escrito(resultado.moic, VEZES)
    da_tir = ev.do_rastro(
        "lbo.tir",
        f"TIR do acionista: {tir} ao ano",
        resultado.tir,
        resultado.rastros["tir"],
    )
    do_moic = ev.do_rastro(
        "lbo.moic",
        f"MOIC do acionista: {moic}",
        resultado.moic,
        resultado.rastros["moic"],
    )
    texto = f"A TIR do acionista é de {tir} ao ano e o MOIC, de {moic}."
    return [*blocos, _Bloco(texto, (da_tir, do_moic))]


# --- red flags ------------------------------------------------------------------------------------
def _cruzamento(c: cruzamentos.Cruzamento) -> _Bloco:
    """O achado (ou o "sem achado") com a fonte; sem data nem fonte, o que faltou vira lacuna."""
    afirmacao = f"{c.titulo}. {c.frase}"
    id = f"red_flags.{c.chave}"
    if c.medido_em and c.fontes:
        evidencia = ev.Evidencia(
            id,
            ev.TRECHO,
            afirmacao,
            date.fromisoformat(c.medido_em[:10]),
            documento="; ".join(c.fontes),
        )
    else:
        evidencia = ev.lacuna(id, afirmacao)
    return _Bloco(afirmacao, (evidencia,))


def _desligado(relatorio: RelatorioDoCnpj) -> list[_Bloco]:
    blocos = []
    for posicao, texto in enumerate(relatorio.desligado):
        if PALAVRA_DO_DESLIGADO in texto:
            blocos.append(
                _Bloco(texto, (ev.lacuna(f"red_flags.desligado.{posicao}", texto),))
            )
    return blocos


def red_flags(
    relatorio: RelatorioDoCnpj, ficha: Ficha | None, dia: date
) -> list[_Bloco]:
    """Os quatro cruzamentos da ficha, os ratings da seção de crédito e o que espera o parecer."""
    blocos = (
        [_cruzamento(c) for c in cruzamentos.cruzamentos_da_ficha(ficha, dia)]
        if ficha
        else []
    )
    credito = [s for s in relatorio.secoes if s.chave == SECAO_DE_CREDITO]
    blocos += _itens_como_frases(credito, relatorio.como_era_em)
    return blocos + _desligado(relatorio)


# --- o memorando ----------------------------------------------------------------------------------
def _publico_ate(bloco: _Bloco, dia: date) -> bool:
    return all(
        e.publicado_em is None or e.publicado_em <= dia for e in bloco.evidencias
    )


def _blocos_por_secao(
    entrada: EntradaDoMemorando, dia: date
) -> dict[str, list[_Bloco]]:
    lbo_do_dia = entrada.lbo if entrada.lbo and entrada.lbo.como_era_em <= dia else None
    comps_do_dia = (
        entrada.comps if entrada.comps and entrada.comps.como_era_em <= dia else None
    )
    return {
        "perfil": perfil(entrada.relatorio),
        "pares": pares(entrada.pares),
        "dcf_e_multiplos": dcf_e_multiplos(entrada.dcf_reverso, entrada.multiplos, dia),
        "comps_por_transacao": comps_por_transacao(comps_do_dia)
        if comps_do_dia
        else [],
        "lbo": lbo(lbo_do_dia) if lbo_do_dia else [],
        "red_flags": red_flags(entrada.relatorio, entrada.ficha, dia),
    }


def montar_memorando(entrada: EntradaDoMemorando, dia: date) -> Memorando:
    """O memorando como era em `dia`, já conferido (`MemorandoReprovadoError` se algo reprovar)."""
    secoes: list[SecaoDoMemorando] = []
    evidencias: dict[str, Evidencia] = {}
    limites: list[str] = []
    for chave, blocos in _blocos_por_secao(entrada, dia).items():
        publicos = [b for b in blocos if _publico_ate(b, dia)] or [
            _lacuna_da_secao(chave, dia)
        ]
        for bloco in publicos:
            evidencias.update((e.id, e) for e in bloco.evidencias)
        secoes.append(SecaoDoMemorando(chave, tuple(b.frase() for b in publicos)))
    if entrada.comps is not None and entrada.comps.como_era_em <= dia:
        limites += entrada.comps.limites
    if entrada.lbo is not None and entrada.lbo.como_era_em <= dia:
        limites += entrada.lbo.limites
    memorando = Memorando(
        entrada.relatorio.cnpj,
        entrada.relatorio.empresa,
        dia,
        tuple(secoes),
        tuple(evidencias.values()),
        (*limites, *LIMITES),
    )
    return para_mostrar(memorando)
