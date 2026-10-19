"""Painel do café: o lado do mercado financeiro do café numa tela só (plano do café, PR 11).

Junta, para arábica ou conilon e "como estava em D", o preço de referência mensal e o spread, o câmbio,
a posição dos fundos na bolsa de Nova York, as exportações, o balanço mundial do USDA, a safra da CONAB
(com o termômetro do 1º levantamento e a bienalidade), o clima da região, o calendário e as fichas das
contrapartes. Cada bloco diz o que é, de onde vem e de quando é o número mais novo; bloco sem dado diz
por quê, nunca mostra zero.

**Sem olhar o futuro:** os preços e o câmbio vêm do acervo de séries "como estavam em D"; cada tabela
da base é cortada pelo `como_estava_em` do próprio módulo (CONAB e USDA pelo `divulgado_em`, a CFTC pelo
`disponivel_em`). As tabelas são lidas inteiras pela porta da base (`base.porta`) e cortadas aqui.

**Sem previsão nem recomendação:** os blocos descrevem o que foi publicado. O termômetro mostra o erro
histórico do 1º levantamento com números, sem aplicá-lo à safra em curso. A ficha das contrapartes não
tem nota, selo nem semáforo (ADR da confiança da contraparte: PR 13, Diretoria).

Fica sem Streamlit e sem React: entradas e saídas em tipos simples (dataclass que vira JSON).
"""

import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

import pandas as pd
import sqlalchemy as sa

from base.commodities import cftc_cot, clima_regiao, comex_cafe, conab_cafe, usda_psd
from base.contrapartes import cafe as contrapartes_cafe
from src.banco import series as acervo
from src.commodities import painel_de_precos as precos
from src.commodities.cafe import (
    balanco,
    bienalidade,
    calendario,
    pacote_do_painel,
    termometro,
)
from src.commodities.cafe import indices_de_clima as clima
from src.commodities.cafe import spread as spread_do_cafe
from src.commodities.cafe.pontos import PontoDaSafra
from src.commodities.cafe.regioes import ARABICA, CONILON, POR_ID, REGIOES, Regiao

TIPOS = (ARABICA, CONILON)
NOME_DO_TIPO = {ARABICA: "Arábica", CONILON: "Conilon (robusta)"}
CHAVE_DO_PRECO = {ARABICA: precos.ARABICA, CONILON: precos.ROBUSTA}
PTAX = "bcb-ptax-venda"
CONTRATO_DO_ARABICA = "cafe-arabica"  # Coffee C, ICE Futures U.S. (código CFTC 083731)
SACAS_POR_LOTE = (
    37_500 * 0.45359237 / 60
)  # o lote do Coffee C: 37.500 libras-peso ≈ 283,5 sacas
MESES_DO_HISTORICO = 60
SEMANAS_DOS_FUNDOS = 5 * 52
MESES_DAS_EXPORTACOES = 12
DESTINOS_NA_TABELA = 10
SAFRAS_DO_BALANCO = 15
MESES_DA_CHUVA = 3
BRASIL = "BRASIL"  # a linha do país inteiro na tabela da CONAB

AVISO_DIARIO = precos.AVISO_DIARIO
FONTE_DO_CAMBIO = "Banco Central do Brasil, PTAX (venda)."
FONTE_DOS_FUNDOS = (
    "CFTC, Commitments of Traders (disaggregated), Coffee C na ICE Futures U.S."
)
FONTE_DAS_EXPORTACOES = (
    "Comex Stat (MDIC/Secex), NCMs 0901.11.10, 0901.11.90, 0901.21.00 e 2101.11.10."
)
FONTE_DO_BALANCO = "USDA, PSD Online (Production, Supply and Distribution)."
FONTE_DA_CONAB = "CONAB, Acompanhamento da safra brasileira de café."
FONTE_DO_CLIMA = {
    clima_regiao.FONTE_INMET: "INMET, estações automáticas; normal de 1991 a 2020.",
    clima_regiao.FONTE_CHIRPS: "CHIRPS (UCSB), chuva por satélite; normal de 1991 a 2020.",
}
FONTE_DO_CALENDARIO = "Camargo & Camargo (2001, Bragantia), CONAB e Embrapa Café."
FONTE_DAS_CONTRAPARTES = "Notícias e documentos públicos lidos à mão, ditos com as nossas palavras, com o link de cada fato."

LEGENDA_DOS_FUNDOS = (
    "Fundos (managed money) costumam ampliar movimentos de preço que já começaram; não os criam "
    "sozinhos. Quanto o câmbio do real pesa no preço do café não é consenso: a CEPAL (2021) e a "
    "Organização Internacional do Café (2025) chegam a conclusões diferentes."
)
NOTA_DAS_EXPORTACOES = (
    "A NCM não separa arábica de conilon e soma o café torrado e o solúvel em peso do produto. A fatia "
    "do Espírito Santo (quase só conilon) é uma pista do conilon, não a conta dele."
)
NOTA_DO_TERMOMETRO = (
    "Erro positivo: o 1º levantamento da CONAB veio acima do número final (o 4º). É o histórico das "
    "safras já fechadas; a safra em curso não tem erro conhecido."
)
SEM_FUNDOS_NO_CONILON = (
    "O robusta é negociado em Londres (ICE Futures Europe), e esse relatório não está na base; a CFTC "
    "cobre só as bolsas dos Estados Unidos."
)
SEM_BIENALIDADE_NO_CONILON = "O conilon não tem o ciclo de safra cheia e vazia do arábica; por isso não há marcação."

O_QUE_E = {
    "preco_de_referencia": "O preço de referência mensal do café verde no mercado internacional, em dólar por quilo, "
    "e o spread: quanto o arábica custa a mais que o robusta.",
    "cambio": "Quantos reais compram um dólar (PTAX de venda). O café é cotado em dólar: o câmbio muda o "
    "preço em reais para quem produz e para quem compra.",
    "fundos": "A posição dos fundos (managed money) no contrato futuro de arábica de Nova York: compras "
    "menos vendas, em lotes, em sacas e em fração de todos os contratos em aberto.",
    "exportacoes": "Quanto café o Brasil exportou nos últimos 12 meses publicados e para quais países.",
    "balanco": "O balanço mundial do USDA: estoque final dividido pelo consumo de cada safra. Quanto menor, "
    "menos café sobra no fim da safra para cada saca consumida.",
    "safra": "A estimativa oficial da safra brasileira em curso, por estado, no levantamento mais novo "
    "da CONAB (são quatro por safra).",
    "termometro": "Quanto o 1º levantamento da CONAB errou em relação ao número final, safra a safra, "
    "em porcentagem.",
    "bienalidade": "O arábica alterna safras cheias e vazias: a planta que produz muito num ano se poupa "
    "no seguinte. Cada safra marcada como cheia ou vazia pela produção final da CONAB.",
    "clima": "A chuva dos últimos três meses e a temperatura mínima do último mês na região, contra a "
    "normal de 1991 a 2020.",
    "calendario": "Em que fase o café está neste mês na região e o que o mercado costuma acompanhar "
    "nessa época. É contexto, não previsão.",
    "contrapartes": "Fatos públicos e datados sobre empresas do café (cooperativas, exportadoras, "
    "torrefadoras) e o que ainda não sabemos de cada uma. Sem nota e sem selo.",
}
TITULO = {
    "preco_de_referencia": "Preço de referência e spread",
    "cambio": "Câmbio",
    "fundos": "Posição dos fundos",
    "exportacoes": "Exportações",
    "balanco": "Balanço mundial",
    "safra": "Safra em curso (CONAB)",
    "termometro": "Termômetro da CONAB",
    "bienalidade": "Bienalidade",
    "clima": "Clima da região",
    "calendario": "Calendário",
    "contrapartes": "Contrapartes",
}
SEM_A_BASE = (
    "A base do café (CFTC, Comex, USDA, CONAB e clima) ainda não chega a este servidor."
)
TABELAS_DA_BASE = {
    "cftc": "cftc_cot_agro",
    "comex": "comex_cafe",
    "usda": "usda_psd_cafe",
    "conab": "conab_cafe",
    "clima": "clima_regiao_cafe",
}
FILTROS_DA_BASE = {
    "cftc": {"contrato": CONTRATO_DO_ARABICA}
}  # a tabela da CFTC tem todo o agro


def motivo_sem_tabela(tabela: str) -> str:
    return f"A tabela `{tabela}` ainda não chega à base deste servidor."


# --- os blocos -----------------------------------------------------------------------------------
@dataclass(frozen=True)
class Bloco[T]:
    """Uma caixa do painel: o que é, a fonte, a data do número mais novo e o conteúdo (ou o motivo de
    não haver conteúdo)."""

    chave: str
    titulo: str
    o_que_e: str
    fonte: str
    data: date | None
    conteudo: T | None
    motivo_sem_dado: str | None = None


@dataclass(frozen=True)
class PrecoDoCafe:
    item: precos.PrecoDeReferencia
    spread: tuple[spread_do_cafe.PontoDoSpread, ...]  # centavos de dólar por libra-peso
    marcos: tuple[spread_do_cafe.Marco, ...]  # acontecimentos que mexeram no spread


@dataclass(frozen=True)
class PontoDoMes:
    mes: date  # dia 1 do mês
    valor: float


@dataclass(frozen=True)
class Cambio:
    ultimo_dia: date
    ultimo_valor: float  # R$ por US$
    variacao_12_meses: float | None  # em %, contra o dia mais próximo de um ano antes
    historico: tuple[PontoDoMes, ...]  # média do mês


@dataclass(frozen=True)
class PontoDosFundos:
    relatorio: date
    liquido_lotes: float
    fracao_do_interesse_aberto: float


@dataclass(frozen=True)
class Fundos:
    relatorio: date  # a terça-feira da posição (o relatório sai na sexta)
    comprados_lotes: float
    vendidos_lotes: float
    liquido_lotes: float  # comprados menos vendidos
    liquido_sacas: float
    interesse_aberto_lotes: float
    fracao_do_interesse_aberto: float  # 0,10 = 10%
    historico: tuple[PontoDosFundos, ...]
    legenda: str = LEGENDA_DOS_FUNDOS


@dataclass(frozen=True)
class Destino:
    pais: str
    sacas: float
    fob_usd: float
    fracao: float  # das sacas do período


@dataclass(frozen=True)
class Exportacoes:
    primeiro_mes: date
    ultimo_mes: date
    sacas: float
    fob_usd: float
    destinos: tuple[Destino, ...]
    fracao_do_espirito_santo: float | None
    nota: str = NOTA_DAS_EXPORTACOES


@dataclass(frozen=True)
class Balanco:
    ultima_safra: int
    estoque_consumo_mundo: tuple[balanco.PontoAnual, ...]
    estoque_consumo_brasil: tuple[balanco.PontoAnual, ...]
    participacao_do_brasil: tuple[balanco.PontoAnual, ...]  # do tipo escolhido
    paises: tuple[balanco.BalancoDoPais, ...]  # os grandes do robusta (só no conilon)


@dataclass(frozen=True)
class LinhaDaSafra:
    uf: str
    area_producao_ha: float | None
    produtividade_sc_ha: float | None
    producao_mil_sacas: float | None


@dataclass(frozen=True)
class Safra:
    safra: int
    levantamento: int
    divulgado_em: date
    linhas: tuple[LinhaDaSafra, ...]  # o Brasil primeiro, depois os estados


@dataclass(frozen=True)
class ErroDaSafra:
    safra: int
    erro_pct: float
    erro_mil_sacas: float


@dataclass(frozen=True)
class Termometro:
    erros: tuple[ErroDaSafra, ...]
    vies_medio_pct: float | None  # média das últimas 10 safras (None com menos de 3)
    menor_erro_pct: float
    maior_erro_pct: float
    nota: str = NOTA_DO_TERMOMETRO


@dataclass(frozen=True)
class Bienalidade:
    marcas: tuple[PontoDaSafra, ...]  # rótulo "cheio" ou "vazio", produção em mil sacas


@dataclass(frozen=True)
class TemperaturaDoMes:
    competencia: date
    tmin_media_c: float | None
    tmin_normal_c: float | None
    tmin_anomalia_c: float | None
    dias_tmin_abaixo_de_2c: float | None


@dataclass(frozen=True)
class ClimaDaRegiao:
    regiao: str
    nome_da_regiao: str
    fonte_dos_dados: str  # "inmet" ou "chirps"
    chuva: dict[str, object]  # `indices_de_clima.em_dicionario`
    temperatura: TemperaturaDoMes


@dataclass(frozen=True)
class Contrapartes:
    fichas: tuple[contrapartes_cafe.FichaDaContraparte, ...]


@dataclass(frozen=True)
class OpcaoDeRegiao:
    id: str
    nome: str
    tipo_predominante: str


@dataclass(frozen=True)
class PainelDoCafe:
    dia: date
    tipo: str
    nome_do_tipo: str
    regiao: str
    regioes: tuple[OpcaoDeRegiao, ...]
    aviso_diario: str
    preco_de_referencia: Bloco[PrecoDoCafe]
    cambio: Bloco[Cambio]
    fundos: Bloco[Fundos]
    exportacoes: Bloco[Exportacoes]
    balanco: Bloco[Balanco]
    safra: Bloco[Safra]
    termometro: Bloco[Termometro]
    bienalidade: Bloco[Bienalidade]
    clima: Bloco[ClimaDaRegiao]
    calendario: Bloco[calendario.OQueOMercadoOlha]
    contrapartes: Bloco[Contrapartes]

    @property
    def blocos(self) -> tuple[Bloco, ...]:
        return (
            self.preco_de_referencia, self.cambio, self.fundos, self.exportacoes, self.balanco, self.safra,
            self.termometro, self.bienalidade, self.clima, self.calendario, self.contrapartes,
        )  # fmt: skip


def _bloco[T](
    chave: str,
    fonte: str,
    data: date | None,
    conteudo: T | None,
    motivo: str | None = None,
) -> Bloco[T]:
    if conteudo is None and motivo is None:
        raise ValueError(f"bloco {chave} sem conteúdo e sem motivo")
    return Bloco(chave, TITULO[chave], O_QUE_E[chave], fonte, data, conteudo, motivo)


def _sem_dado(chave: str, fonte: str, motivo: str) -> Bloco[Any]:
    """A caixa vazia (serve a qualquer tipo de conteúdo): o motivo no lugar do número."""
    return _bloco(chave, fonte, None, None, motivo)


# --- as tabelas da base ---------------------------------------------------------------------------
@dataclass(frozen=True)
class TabelasDoCafe:
    """As tabelas da base que o painel usa (inteiras: o corte "como estava em D" é feito aqui) e, para
    cada uma que faltou, o motivo."""

    tabelas: Mapping[str, pd.DataFrame] = field(default_factory=dict)
    motivos: Mapping[str, str] = field(default_factory=dict)
    contrapartes: pd.DataFrame | None = None  # None: a tabela conferida do repositório

    def tabela(self, nome: str) -> pd.DataFrame | None:
        return self.tabelas.get(nome)

    def motivo(self, nome: str) -> str:
        return self.motivos.get(nome) or motivo_sem_tabela(TABELAS_DA_BASE[nome])


def tabelas_do_pacote() -> TabelasDoCafe:
    """As tabelas do pacote montado no servidor de casa (`pacote_do_painel`); sem pacote, o motivo."""
    pacote = pacote_do_painel.ler_pacote()
    if pacote is None:
        return TabelasDoCafe(motivos=dict.fromkeys(TABELAS_DA_BASE, SEM_A_BASE))
    return TabelasDoCafe(pacote.tabelas, pacote.motivos)


def tabelas_pela_porta() -> TabelasDoCafe:
    """Lê as tabelas do café pela porta da base; a que não está neste servidor vira motivo. Onde a
    base não está (o servidor do app), lê o pacote que o servidor de casa monta."""
    tabelas: dict[str, pd.DataFrame] = {}
    motivos: dict[str, str] = {}
    try:
        # o DuckDB só está instalado onde a base está (o servidor de casa), não no servidor do app
        import duckdb

        from base import porta

        aberta = porta.abrir()
    except (ImportError, ValueError, OSError):
        return tabelas_do_pacote()
    with aberta as p:
        for nome, tabela in TABELAS_DA_BASE.items():
            try:
                tabelas[nome] = p.ler(tabela, filtros=FILTROS_DA_BASE.get(nome))
            except (KeyError, ValueError, OSError, duckdb.Error):
                motivos[nome] = motivo_sem_tabela(tabela)
    return TabelasDoCafe(tabelas, motivos)


# --- cada bloco -----------------------------------------------------------------------------------
def _preco(conexao: sa.Connection, tipo: str, dia: date) -> Bloco[PrecoDoCafe]:
    chave = CHAVE_DO_PRECO[tipo]
    painel = precos.montar_painel(conexao, dia)
    item = next((i for i in painel.itens if i.chave == chave), None)
    if item is None:
        motivo = "O preço de referência do Banco Mundial ainda não foi coletado neste servidor."
        return _sem_dado("preco_de_referencia", precos.ATRIBUICAO, motivo)
    pontos = spread_do_cafe.spread_como_estava_em(conexao, dia)[-MESES_DO_HISTORICO:]
    marcos = tuple(spread_do_cafe.marcos_ate(dia))
    conteudo = PrecoDoCafe(item, tuple(pontos), marcos)
    return _bloco("preco_de_referencia", precos.ATRIBUICAO, item.ultimo_mes, conteudo)


def _cambio(conexao: sa.Connection, dia: date) -> Bloco[Cambio]:
    serie = acervo.como_estava_em(conexao, PTAX, dia).dropna()
    if serie.empty:
        motivo = "A PTAX do Banco Central ainda não foi coletada neste servidor."
        return _sem_dado("cambio", FONTE_DO_CAMBIO, motivo)
    ultimo = serie.index[-1]
    um_ano_antes = serie[: ultimo - pd.DateOffset(years=1)]
    variacao = (
        float((serie.iloc[-1] / um_ano_antes.iloc[-1] - 1) * 100)
        if not um_ano_antes.empty
        else None
    )
    por_mes = (
        serie.groupby(serie.index.to_period("M")).mean().iloc[-MESES_DO_HISTORICO:]
    )
    historico = tuple(
        PontoDoMes(periodo.to_timestamp().date(), float(valor))
        for periodo, valor in por_mes.items()
    )
    conteudo = Cambio(ultimo.date(), float(serie.iloc[-1]), variacao, historico)
    return _bloco("cambio", FONTE_DO_CAMBIO, ultimo.date(), conteudo)


def _fundos(tabelas: TabelasDoCafe, tipo: str, dia: date) -> Bloco[Fundos]:
    if tipo == CONILON:
        return _sem_dado("fundos", FONTE_DOS_FUNDOS, SEM_FUNDOS_NO_CONILON)
    tabela = tabelas.tabela("cftc")
    if tabela is None:
        return _sem_dado("fundos", FONTE_DOS_FUNDOS, tabelas.motivo("cftc"))
    linhas = cftc_cot.como_estava_em(tabela, dia)
    linhas = linhas[linhas["contrato"] == CONTRATO_DO_ARABICA].sort_values("relatorio")
    linhas = linhas[linhas["open_interest"] > 0]
    if linhas.empty:
        motivo = f"Nenhum relatório da CFTC do Coffee C era público em {dia:%d/%m/%Y}."
        return _sem_dado("fundos", FONTE_DOS_FUNDOS, motivo)
    liquido = linhas["managed_money_long"] - linhas["managed_money_short"]
    fracao = liquido / linhas["open_interest"]
    historico = tuple(
        PontoDosFundos(pd.Timestamp(r).date(), float(lq), float(fr))
        for r, lq, fr in zip(
            linhas["relatorio"].iloc[-SEMANAS_DOS_FUNDOS:],
            liquido.iloc[-SEMANAS_DOS_FUNDOS:],
            fracao.iloc[-SEMANAS_DOS_FUNDOS:],
            strict=True,
        )
    )
    ultima = linhas.iloc[-1]
    relatorio = pd.Timestamp(ultima["relatorio"]).date()
    conteudo = Fundos(
        relatorio=relatorio,
        comprados_lotes=float(ultima["managed_money_long"]),
        vendidos_lotes=float(ultima["managed_money_short"]),
        liquido_lotes=float(liquido.iloc[-1]),
        liquido_sacas=float(liquido.iloc[-1] * SACAS_POR_LOTE),
        interesse_aberto_lotes=float(ultima["open_interest"]),
        fracao_do_interesse_aberto=float(fracao.iloc[-1]),
        historico=historico,
    )
    return _bloco("fundos", FONTE_DOS_FUNDOS, relatorio, conteudo)


def _exportacoes(tabelas: TabelasDoCafe, dia: date) -> Bloco[Exportacoes]:
    tabela = tabelas.tabela("comex")
    if tabela is None:
        return _sem_dado("exportacoes", FONTE_DAS_EXPORTACOES, tabelas.motivo("comex"))
    linhas = comex_cafe.como_estava_em(tabela, dia)
    if linhas.empty:
        motivo = f"Nenhuma exportação de café estava guardada em {dia:%d/%m/%Y}."
        return _sem_dado("exportacoes", FONTE_DAS_EXPORTACOES, motivo)
    competencias = pd.to_datetime(linhas["competencia"])
    meses = sorted(competencias.unique())[-MESES_DAS_EXPORTACOES:]
    periodo = linhas[competencias.isin(meses)]
    sacas = float(periodo["sacas"].sum())
    por_pais = (
        periodo.groupby("pais_destino")[["sacas", "vl_fob_usd"]]
        .sum()
        .sort_values("sacas", ascending=False)
        .head(DESTINOS_NA_TABELA)
    )
    destinos = tuple(
        Destino(str(pais), float(linha["sacas"]), float(linha["vl_fob_usd"]),
                float(linha["sacas"] / sacas) if sacas else 0.0)
        for pais, linha in por_pais.iterrows()
    )  # fmt: skip
    do_es = float(periodo.loc[periodo["proxy_conilon"].astype(bool), "sacas"].sum())
    ultimo_mes = pd.Timestamp(meses[-1]).date()
    conteudo = Exportacoes(
        primeiro_mes=pd.Timestamp(meses[0]).date().replace(day=1),
        ultimo_mes=ultimo_mes,
        sacas=sacas,
        fob_usd=float(periodo["vl_fob_usd"].sum()),
        destinos=destinos,
        fracao_do_espirito_santo=do_es / sacas if sacas else None,
    )
    return _bloco("exportacoes", FONTE_DAS_EXPORTACOES, ultimo_mes, conteudo)


def _balanco(tabelas: TabelasDoCafe, tipo: str, dia: date) -> Bloco[Balanco]:
    tabela = tabelas.tabela("usda")
    if tabela is None:
        return _sem_dado("balanco", FONTE_DO_BALANCO, tabelas.motivo("usda"))
    visivel = usda_psd.como_estava_em(tabela, dia)
    mundo = balanco.relacao_estoque_consumo(visivel)
    if not mundo:
        motivo = (
            f"O USDA ainda não tinha publicado o balanço do café em {dia:%d/%m/%Y}."
        )
        return _sem_dado("balanco", FONTE_DO_BALANCO, motivo)
    ultima = mundo[-1].ano_safra
    paises = (
        tuple(p for p in balanco.balanco_por_pais(visivel) if p.ano_safra == ultima)
        if tipo == CONILON
        else ()
    )
    conteudo = Balanco(
        ultima_safra=ultima,
        estoque_consumo_mundo=tuple(mundo[-SAFRAS_DO_BALANCO:]),
        estoque_consumo_brasil=tuple(
            balanco.relacao_estoque_consumo(visivel, balanco.BRASIL)[
                -SAFRAS_DO_BALANCO:
            ]
        ),
        participacao_do_brasil=tuple(
            balanco.participacao_do_brasil(visivel, tipo)[-SAFRAS_DO_BALANCO:]
        ),
        paises=paises,
    )
    divulgado = pd.Timestamp(visivel["divulgado_em"].max()).date()
    return _bloco("balanco", FONTE_DO_BALANCO, divulgado, conteudo)


def _numero(valor: object) -> float | None:
    return None if valor is None or pd.isna(valor) else float(valor)  # type: ignore[arg-type]


def _safra(tabelas: TabelasDoCafe, tipo: str, dia: date) -> Bloco[Safra]:
    tabela = tabelas.tabela("conab")
    if tabela is None:
        return _sem_dado("safra", FONTE_DA_CONAB, tabelas.motivo("conab"))
    visivel = conab_cafe.como_estava_em(tabela, dia)
    visivel = visivel[visivel["tipo"] == tipo]
    if visivel.empty:
        motivo = f"A CONAB ainda não tinha levantamento de {NOME_DO_TIPO[tipo].lower()} em {dia:%d/%m/%Y}."
        return _sem_dado("safra", FONTE_DA_CONAB, motivo)
    safra = int(visivel["safra"].max())
    da_safra = visivel[visivel["safra"] == safra]
    da_safra = pd.concat(
        [
            da_safra[da_safra["uf"] == BRASIL],
            da_safra[da_safra["uf"] != BRASIL].sort_values("uf"),
        ]
    )
    referencia = (
        da_safra[da_safra["uf"] == BRASIL].iloc[0]
        if (da_safra["uf"] == BRASIL).any()
        else da_safra.sort_values("divulgado_em").iloc[-1]
    )
    divulgado = pd.Timestamp(referencia["divulgado_em"]).date()
    conteudo = Safra(
        safra=safra,
        levantamento=int(referencia["levantamento"]),
        divulgado_em=divulgado,
        linhas=tuple(
            LinhaDaSafra(
                str(linha["uf"]),
                _numero(linha["area_producao_ha"]),
                _numero(linha["produtividade_sc_ha"]),
                _numero(linha["producao_mil_sacas"]),
            )
            for _, linha in da_safra.iterrows()
        ),
    )
    return _bloco("safra", FONTE_DA_CONAB, divulgado, conteudo)


def _ultima_divulgacao(tabela: pd.DataFrame, tipo: str, dia: date) -> date | None:
    linhas = tabela[
        (tabela["tipo"] == tipo) & (tabela["divulgado_em"] <= pd.Timestamp(dia))
    ]
    return None if linhas.empty else pd.Timestamp(linhas["divulgado_em"].max()).date()


def _termometro(tabelas: TabelasDoCafe, tipo: str, dia: date) -> Bloco[Termometro]:
    tabela = tabelas.tabela("conab")
    if tabela is None:
        return _sem_dado("termometro", FONTE_DA_CONAB, tabelas.motivo("conab"))
    pontos = termometro.erro_do_primeiro_levantamento(tabela, tipo, BRASIL, ate=dia)
    em_pct = {p.safra: p.valor for p in pontos if p.serie == "erro_1o_levantamento_pct"}
    em_sacas = {
        p.safra: p.valor for p in pontos if p.serie == "erro_1o_levantamento_mil_sacas"
    }
    if not em_pct:
        motivo = "Nenhuma safra com o 1º e o 4º levantamento da CONAB estava fechada nessa data."
        return _sem_dado("termometro", FONTE_DA_CONAB, motivo)
    erros = tuple(ErroDaSafra(s, em_pct[s], em_sacas[s]) for s in sorted(em_pct))
    vies = termometro.vies_medio(tabela, tipo, BRASIL, ate=dia)
    conteudo = Termometro(
        erros=erros,
        vies_medio_pct=vies[0].valor if vies else None,
        menor_erro_pct=min(em_pct.values()),
        maior_erro_pct=max(em_pct.values()),
    )
    return _bloco(
        "termometro", FONTE_DA_CONAB, _ultima_divulgacao(tabela, tipo, dia), conteudo
    )


def _bienalidade(tabelas: TabelasDoCafe, tipo: str, dia: date) -> Bloco[Bienalidade]:
    if tipo == CONILON:
        return _sem_dado("bienalidade", FONTE_DA_CONAB, SEM_BIENALIDADE_NO_CONILON)
    tabela = tabelas.tabela("conab")
    if tabela is None:
        return _sem_dado("bienalidade", FONTE_DA_CONAB, tabelas.motivo("conab"))
    marcas = bienalidade.marcar(tabela, tipo, BRASIL, ate=dia)
    if not marcas:
        motivo = "São precisas duas safras fechadas da CONAB para marcar a primeira."
        return _sem_dado("bienalidade", FONTE_DA_CONAB, motivo)
    data = _ultima_divulgacao(tabela, tipo, dia)
    return _bloco("bienalidade", FONTE_DA_CONAB, data, Bienalidade(tuple(marcas)))


def regiao_padrao(tipo: str) -> Regiao:
    """A região de maior área do tipo: o ponto de partida do clima e do calendário."""
    return max(
        (r for r in REGIOES if r.tipo_predominante == tipo), key=lambda r: r.area_ha
    )


def _clima(tabelas: TabelasDoCafe, regiao: Regiao, dia: date) -> Bloco[ClimaDaRegiao]:
    fonte_padrao = FONTE_DO_CLIMA[clima_regiao.FONTE_INMET]
    tabela = tabelas.tabela("clima")
    if tabela is None:
        return _sem_dado("clima", fonte_padrao, tabelas.motivo("clima"))
    visivel = tabela[
        (tabela["regiao"] == regiao.id) & (tabela["disponivel_em"] <= pd.Timestamp(dia))
    ]
    for fonte in (clima_regiao.FONTE_INMET, clima_regiao.FONTE_CHIRPS):
        da_fonte = visivel[visivel["fonte"] == fonte].dropna(subset=["chuva_mm"])
        if not da_fonte.empty:
            break
    else:
        motivo = (
            f"Nenhum mês de clima de {regiao.nome} estava publicado em {dia:%d/%m/%Y}."
        )
        return _sem_dado("clima", fonte_padrao, motivo)
    ultima = da_fonte.sort_values("competencia").iloc[-1]
    competencia = pd.Timestamp(ultima["competencia"])
    meses = [
        (competencia - pd.DateOffset(months=k)).month
        for k in reversed(range(MESES_DA_CHUVA))
    ]
    chuva = clima.chuva_acumulada(visivel, regiao.id, competencia.year, meses, fonte)
    temperatura = TemperaturaDoMes(
        competencia=competencia.date(),
        tmin_media_c=_numero(ultima["tmin_media_c"]),
        tmin_normal_c=_numero(ultima["tmin_normal_c"]),
        tmin_anomalia_c=_numero(ultima["tmin_anomalia_c"]),
        dias_tmin_abaixo_de_2c=_numero(ultima["dias_tmin_abaixo_de_2c"]),
    )
    conteudo = ClimaDaRegiao(
        regiao.id, regiao.nome, fonte, clima.em_dicionario(chuva), temperatura
    )
    return _bloco("clima", FONTE_DO_CLIMA[fonte], competencia.date(), conteudo)


def _calendario(regiao: Regiao, dia: date) -> Bloco[calendario.OQueOMercadoOlha]:
    conteudo = calendario.o_que_o_mercado_olha(dia.month, regiao)
    return _bloco("calendario", FONTE_DO_CALENDARIO, dia, conteudo)


def _contrapartes(tabelas: TabelasDoCafe, dia: date) -> Bloco[Contrapartes]:
    fatos = (
        tabelas.contrapartes
        if tabelas.contrapartes is not None
        else contrapartes_cafe.ler()
    )
    fichas = tuple(contrapartes_cafe.fichas(fatos, em=dia))
    datas = [f.divulgado_em for ficha in fichas for f in ficha.fatos]
    if not datas:
        motivo = (
            f"Nenhum fato sobre as contrapartes do café era público em {dia:%d/%m/%Y}."
        )
        return _sem_dado("contrapartes", FONTE_DAS_CONTRAPARTES, motivo)
    return _bloco(
        "contrapartes", FONTE_DAS_CONTRAPARTES, max(datas), Contrapartes(fichas)
    )


# --- o painel -------------------------------------------------------------------------------------
def montar_painel(
    conexao: sa.Connection,
    tipo: str,
    dia: date,
    regiao: str | None = None,
    tabelas: TabelasDoCafe | None = None,
) -> PainelDoCafe:
    """O painel do café de `tipo` (arábica ou conilon) como estava em `dia`.

    `regiao` é o id de uma região do café (`regioes.POR_ID`); vazio, a de maior área do tipo.
    `tabelas` vem pronto nos testes; vazio, as tabelas são lidas pela porta da base.
    """
    if tipo not in TIPOS:
        raise ValueError(f"tipo de café inválido: {tipo!r} (use {' ou '.join(TIPOS)})")
    if regiao is not None and regiao not in POR_ID:
        raise ValueError(f"região de café desconhecida: {regiao!r}")
    escolhida = POR_ID[regiao] if regiao is not None else regiao_padrao(tipo)
    tabelas = tabelas if tabelas is not None else tabelas_pela_porta()
    return PainelDoCafe(
        dia=dia,
        tipo=tipo,
        nome_do_tipo=NOME_DO_TIPO[tipo],
        regiao=escolhida.id,
        regioes=tuple(
            OpcaoDeRegiao(r.id, r.nome, r.tipo_predominante) for r in REGIOES
        ),
        aviso_diario=AVISO_DIARIO,
        preco_de_referencia=_preco(conexao, tipo, dia),
        cambio=_cambio(conexao, dia),
        fundos=_fundos(tabelas, tipo, dia),
        exportacoes=_exportacoes(tabelas, dia),
        balanco=_balanco(tabelas, tipo, dia),
        safra=_safra(tabelas, tipo, dia),
        termometro=_termometro(tabelas, tipo, dia),
        bienalidade=_bienalidade(tabelas, tipo, dia),
        clima=_clima(tabelas, escolhida, dia),
        calendario=_calendario(escolhida, dia),
        contrapartes=_contrapartes(tabelas, dia),
    )


def _simples(valor: object) -> object:
    """Datas em ISO, NaN e infinito em None; o resto como está (dicionários e listas por dentro)."""
    if isinstance(valor, dict):
        return {chave: _simples(v) for chave, v in valor.items()}
    if isinstance(valor, list | tuple):
        return [_simples(v) for v in valor]
    if isinstance(valor, date):
        return valor.isoformat()
    if isinstance(valor, float) and not math.isfinite(valor):
        return None
    return valor


def em_dicionario(painel: PainelDoCafe) -> dict[str, object]:
    """O painel em tipos simples (datas em ISO, vazio em None), pronto para a API."""
    dado = _simples(asdict(painel))
    assert isinstance(dado, dict)
    return dado
