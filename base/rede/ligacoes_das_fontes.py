"""As ligações que a base já tem viram linhas de `ligacoes` (ADR 0077; plano, tarefa 3.2).

Cada fonte vira um tipo, com as duas pontas como `id_entidade` (pelos `identificadores` do PR 2):

| Tipo | De → para | Fonte |
|---|---|---|
| `controlada_de`, `coligada_de`, `participada_de` | sociedade → companhia | FRE (`controladas`) |
| `opera_para` | entidade do regulador → companhia (`papel` = via e "principal") | `empresa_serie` (B13) |
| `do_conglomerado_de` | instituição → líder do conglomerado prudencial | cadastro do IF.data |
| `audita` | firma (código da CVM) → companhia | FCA (`auditores`) |
| `emite` | empresa (pelo emissor do ISIN) → valor mobiliário | carteiras dos fundos (CDA) |
| `detem` | fundo → valor mobiliário (`papel` = comprado, emprestado ou vendido) | carteiras (CDA) |

Ponta que não é entidade da rede (controlada estrangeira, fundo fora do cadastro) fica de fora e é
contada no log. Quando a fonte repete a relação em cada entrega (o FRE de cada ano, a carteira de cada
mês, o cadastro de cada trimestre), as entregas seguidas viram **um período** (`comprimir_periodos`):
`aconteceu_em` é a primeira, `ate` é a primeira entrega que já não a mostra (encerrada pela fonte) e
`ate_publico_em` é quando essa entrega ficou pública (o FRE entregue, a carteira 90 dias depois do mês,
o IF.data 120 dias depois da data-base). O mandato de auditor sem fim que some do FCA seguinte acaba
quando entra o mandato novo (ou na entrega desse FCA, se nenhum entra), público com esse FCA.

O FRE mais novo deixa o tipo em branco em muitas linhas: vale o último tipo informado antes (nunca um
de depois); sem nenhum, `participada_de`. Firma de auditoria com o código da CVM de outra firma (~1,3%
das linhas das redes) é conflito e não liga; auditor pessoa física (sem CNPJ) nunca entra.
"""

import logging
import re
from collections.abc import Sequence

import pandas as pd

from base.bcb_ifdata import disponivel_em
from base.cda import DIAS_ATE_FICAR_PUBLICA
from base.cnpj import normalizar_cnpj
from base.rede.ligacoes import comprimir_periodos

log = logging.getLogger(__name__)

CONTROLADA_DE, COLIGADA_DE, PARTICIPADA_DE = (
    "controlada_de",
    "coligada_de",
    "participada_de",
)
OPERA_PARA, DO_CONGLOMERADO_DE = "opera_para", "do_conglomerado_de"
AUDITA, EMITE, DETEM = "audita", "emite", "detem"
TIPO_DO_FRE = {"controlada": CONTROLADA_DE, "coligada": COLIGADA_DE}
PRODUTO_DO_COMEX = "produto"
PELA_REGRA, PELA_TABELA = "regra", "tabela"
LIDER = "lider"
INSTITUICAO_INDIVIDUAL = r"\d{8}"
ISIN = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")
MESES_POR_ANO = 12
_VAZIA = pd.DataFrame()


class Resolvedor:
    """Identificador → `id_entidade`, só quando ele aponta para uma entidade só (sem período)."""

    def __init__(self, identificadores: pd.DataFrame) -> None:
        self._mapas: dict[str, pd.Series] = {}
        for sistema, grupo in identificadores.groupby("sistema"):
            unicos = grupo.drop_duplicates(["valor", "id_entidade"])
            unicos = unicos[~unicos["valor"].duplicated(keep=False)]
            self._mapas[str(sistema)] = unicos.set_index("valor")["id_entidade"]

    def sistema(self, sistema: str, valores: pd.Series) -> pd.Series:
        mapa = self._mapas.get(sistema, pd.Series(dtype=object))
        return valores.map(mapa)

    def cnpj(self, cnpjs: pd.Series) -> pd.Series:
        """Empresa ou fundo pelo CNPJ de 14; a filial, pela raiz."""
        cnpj = cnpjs.map(normalizar_cnpj)
        return self.sistema("cnpj", cnpj).fillna(
            self.sistema("cnpj_raiz", cnpj.str[:8])
        )

    def raiz(self, raizes: pd.Series) -> pd.Series:
        return self.sistema("cnpj_raiz", raizes)


def _dia(serie: pd.Series) -> pd.Series:
    datas = pd.to_datetime(serie, errors="coerce", utc=True)
    return datas.dt.tz_localize(None).dt.normalize()


def _com_as_duas_pontas(tabela: pd.DataFrame, tipo: str) -> pd.DataFrame:
    """Só as linhas com as duas pontas na rede e pontas diferentes (a empresa não liga a ela mesma)."""
    tem = (
        tabela["de"].notna() & tabela["para"].notna() & (tabela["de"] != tabela["para"])
    )
    if (~tem).any():
        log.info(
            "%s: %d linhas sem as duas pontas na rede ficaram de fora",
            tipo,
            (~tem).sum(),
        )
    return tabela[tem]


def _fim_pela_fonte(fim: pd.Series, entregas: Sequence) -> pd.Series:
    """O valor da entrega seguinte ao período (`fim` + 1) na lista `entregas`; vazio se não há."""
    proxima = (fim + 1).astype(int)
    datas = list(entregas)
    return pd.Series(
        [datas[p] if p < len(datas) else pd.NaT for p in proxima], index=fim.index
    )


# --- controladas e coligadas (FRE) -------------------------------------------------------------
def _tipo_do_fre(controladas: pd.DataFrame) -> pd.Series:
    """O tipo informado; em branco, o último informado antes para o mesmo par (nunca um de depois)."""
    tipo = controladas["tipo"].map(
        lambda t: TIPO_DO_FRE.get(t) if isinstance(t, str) else None
    )
    par = [controladas["cnpj_companhia"], controladas["cnpj"]]
    return tipo.groupby(par).ffill().fillna(PARTICIPADA_DE)


def das_controladas(controladas: pd.DataFrame, r: Resolvedor) -> pd.DataFrame:
    """Cada sociedade → companhia, um período por FREs seguidos que a mostram (com a mesma %)."""
    if controladas.empty:
        return _VAZIA
    tabela = controladas[controladas["cnpj"].notna()].copy()
    tabela["referencia"] = _dia(tabela["referencia"])
    tabela = tabela.sort_values(["cnpj_companhia", "cnpj", "referencia"], kind="stable")
    tabela["tipo"] = _tipo_do_fre(tabela)
    tabela["de"], tabela["para"] = (
        r.cnpj(tabela["cnpj"]),
        r.cnpj(tabela["cnpj_companhia"]),
    )
    tabela = _com_as_duas_pontas(tabela, "controladas")
    # o passo é a posição do FRE na lista de FREs da companhia: o que não aparece num FRE saiu
    # cada FRE da companhia (a referência) e quando ficou público (a primeira entrega dele)
    publico_do_fre = (
        controladas.assign(
            referencia=_dia(controladas["referencia"]),
            conhecido_em=_dia(controladas["conhecido_em"]),
        )
        .groupby(["cnpj_companhia", "referencia"])["conhecido_em"]
        .min()
    )
    entregas = {
        c: list(g.index.get_level_values("referencia"))
        for c, g in publico_do_fre.groupby(level="cnpj_companhia")
    }
    publicos = {c: list(g) for c, g in publico_do_fre.groupby(level="cnpj_companhia")}
    tabela["inicio"] = [
        entregas[c].index(ref)
        for c, ref in zip(tabela["cnpj_companhia"], tabela["referencia"], strict=True)
    ]
    tabela["fim"] = tabela["inicio"]
    # duas filiais da mesma sociedade no mesmo FRE: fica a maior participação
    tabela = tabela.sort_values(
        ["participacao"], ascending=False, kind="stable"
    ).drop_duplicates(["de", "para", "inicio"])
    periodos = comprimir_periodos(
        tabela[["de", "para", "tipo", "participacao", "cnpj_companhia", "inicio", "fim",
                "referencia", "conhecido_em", "origem_sha256"]],
        ["de", "para", "tipo", "participacao"],
    )  # fmt: skip

    def pela_fonte(lista: dict[str, list]) -> pd.Series:
        if periodos.empty:
            return pd.Series(dtype="datetime64[ns]")
        return pd.concat(
            [
                _fim_pela_fonte(g["fim"], lista[c])
                for c, g in periodos.groupby("cnpj_companhia", sort=False)
            ]
        ).reindex(periodos.index)

    return periodos.assign(
        aconteceu_em=periodos["referencia"],
        publico_em=periodos["conhecido_em"],
        ate=pela_fonte(entregas),
        ate_publico_em=pela_fonte(publicos),
        fonte="cvm-fre",
        conferido_por=PELA_REGRA,
    )


# --- entidade do regulador → companhia (empresa ↔ série, B13) ---------------------------------
def opera_para(empresa_serie: pd.DataFrame, r: Resolvedor) -> pd.DataFrame:
    """A entidade que o regulador enxerga → a companhia listada. Produto do Comex é exposição, não
    ligação; a própria companhia não liga a ela mesma. A fonte de governo é conhecida desde guardada."""
    if empresa_serie.empty:
        return _VAZIA
    tabela = empresa_serie[
        empresa_serie["raiz"].notna()
        & empresa_serie["cnpj_companhia"].notna()
        & (empresa_serie["via"] != PRODUTO_DO_COMEX)
    ].copy()
    tabela["de"], tabela["para"] = (
        r.raiz(tabela["raiz"]),
        r.cnpj(tabela["cnpj_companhia"]),
    )
    tabela = _com_as_duas_pontas(tabela, "opera_para")
    tabela["desde"] = _dia(tabela["desde"])
    tabela["publico_em"] = pd.concat(
        [tabela["desde"], _dia(tabela["montado_em"])], axis=1
    ).max(axis=1)
    tabela["pela_regra"] = tabela["por"] != PELA_TABELA
    juntas = (
        tabela.sort_values(["origem_sha256"], kind="stable")
        .groupby(["de", "para", "via", "desde"], dropna=False, sort=True)
        .agg(
            principal=("principal", "any"),
            participacao=("participacao", "max"),
            publico_em=("publico_em", "min"),
            pela_regra=("pela_regra", "any"),
            origem_sha256=("origem_sha256", "first"),
        )
        .reset_index()
    )
    return juntas.assign(
        tipo=OPERA_PARA,
        papel=juntas["via"] + juntas["principal"].map({True: ";principal", False: ""}),
        aconteceu_em=juntas["desde"],
        fonte="empresa_serie",
        conferido_por=juntas["pela_regra"].map({True: PELA_REGRA, False: PELA_TABELA}),
    )


# --- instituição → líder do conglomerado (IF.data) ---------------------------------------------
def do_conglomerado(cadastro: pd.DataFrame, r: Resolvedor) -> pd.DataFrame:
    """A instituição individual → a líder do conglomerado prudencial, um período por trimestres
    seguidos; público 120 dias depois da data-base."""
    if cadastro.empty or "cnpj_lider" not in cadastro:
        return _VAZIA
    data_base = _dia(cadastro["data_base"])
    datas = sorted(data_base.dropna().unique())
    tabela = cadastro.assign(data_base=data_base)
    individual = tabela["cod_inst"].astype(str).str.fullmatch(INSTITUICAO_INDIVIDUAL)
    lider = tabela["cnpj_lider"].astype(str).str[:8]
    tabela = tabela[
        individual & tabela["cnpj_lider"].notna() & (lider != tabela["cod_inst"])
    ]
    tabela = tabela.assign(
        de=r.raiz(tabela["cod_inst"]), para=r.raiz(tabela["cnpj_lider"].str[:8])
    )
    tabela = _com_as_duas_pontas(tabela, "do_conglomerado_de")
    tabela = tabela.sort_values("data_base", kind="stable").assign(
        inicio=tabela["data_base"].map(datas.index),
        publico_em=disponivel_em(tabela),
    )
    tabela["fim"] = tabela["inicio"]
    periodos = comprimir_periodos(
        tabela[
            ["de", "para", "inicio", "fim", "data_base", "publico_em", "origem_sha256"]
        ],
        ["de", "para"],
    )
    ate = _fim_pela_fonte(periodos["fim"], datas)
    return periodos.assign(
        tipo=DO_CONGLOMERADO_DE,
        papel=LIDER,
        aconteceu_em=periodos["data_base"],
        ate=ate,
        ate_publico_em=disponivel_em(pd.DataFrame({"data_base": ate})),
        fonte="bcb-ifdata",
        conferido_por=PELA_REGRA,
    )


# --- auditores (FCA) ----------------------------------------------------------------------------
def auditores_sem_conflito(auditores: pd.DataFrame) -> pd.DataFrame:
    """Os mandatos de firma (com CNPJ) com o código da CVM que é dela: cada código fica com a firma
    que mais o usa (`auditor_id`); a linha com o código de outra firma é conflito e sai."""
    if auditores.empty:
        return auditores
    firmas = auditores[
        auditores["auditor_cnpj"].notna() & auditores["codigo_cvm_auditor"].notna()
    ]
    dona = firmas.groupby("codigo_cvm_auditor")["auditor_id"].agg(
        lambda ids: ids.value_counts().sort_index().idxmax()
    )
    return firmas[firmas["auditor_id"] == firmas["codigo_cvm_auditor"].map(dona)]


def _fca_seguinte(
    mandatos: pd.DataFrame, auditores: pd.DataFrame, tabela: pd.DataFrame
) -> pd.DataFrame:
    """Para cada mandato, o FCA da companhia logo depois do último que o lista (`proxima`, o dia em que
    ficou público em `proxima_em`) e o início mais cedo de um mandato que começa depois dele nesse FCA
    (`entrou_em`). Sem FCA depois, tudo vazio."""
    entregas = (
        auditores.assign(
            referencia=_dia(auditores["referencia"]),
            conhecido_em=_dia(auditores["conhecido_em"]),
        )
        .groupby(["cnpj", "referencia"], as_index=False)["conhecido_em"]
        .min()
        .rename(columns={"referencia": "proxima", "conhecido_em": "proxima_em"})
    )
    depois = mandatos.merge(entregas, on="cnpj")
    depois = depois[depois["proxima"] > depois["ultima"]]
    proxima = depois.sort_values("proxima", kind="stable").drop_duplicates("_mandato")
    novos = proxima.merge(
        tabela[["cnpj", "referencia", "inicio"]].rename(
            columns={"referencia": "proxima", "inicio": "inicio_novo"}
        ),
        on=["cnpj", "proxima"],
    )
    entrou = (
        novos[novos["inicio_novo"] > novos["inicio"]]
        .groupby("_mandato")["inicio_novo"]
        .min()
        .rename("entrou_em")
    )
    return (
        proxima.set_index("_mandato")[["proxima", "proxima_em"]]
        .join(entrou)
        .reindex(mandatos["_mandato"])
    )


def audita(auditores: pd.DataFrame, r: Resolvedor) -> pd.DataFrame:
    """A firma → a companhia, um mandato por início; público do primeiro FCA que o mostrou, fim do
    FCA mais novo, público no primeiro FCA que o trouxe. O mandato sem fim que o FCA seguinte da
    companhia já não lista acabou (a KPMG de 2006 não fica "vigente" em 2020): no início do mandato
    que entrou nesse FCA ou, sem nenhum, na entrega dele; o fim é público com esse FCA."""
    tabela = auditores_sem_conflito(auditores)
    if tabela.empty:
        return _VAZIA
    tabela = tabela.assign(
        de=r.sistema("codigo_cvm_auditor", tabela["codigo_cvm_auditor"]),
        para=r.cnpj(tabela["cnpj"]),
        inicio=_dia(tabela["inicio"]),
        fim=_dia(tabela["fim"]),
        conhecido_em=_dia(tabela["conhecido_em"]),
        referencia=_dia(tabela["referencia"]),
    )
    tabela = _com_as_duas_pontas(tabela, "audita")
    mandato = ["de", "para", "inicio"]
    ordem = tabela.sort_values(
        [*mandato, "conhecido_em", "origem_sha256"], kind="stable"
    )
    por_mandato = ordem.groupby(mandato, dropna=False)
    primeiro = por_mandato.first().reset_index()
    resumo = por_mandato.agg(
        fim=("fim", "last"), ultima=("referencia", "max")
    ).reset_index()
    # o primeiro FCA que trouxe o fim (o fim só é público desde ele)
    com_fim = ordem[ordem["fim"].notna()]
    fim_em = (
        com_fim.groupby(mandato, dropna=False)["conhecido_em"]
        .min()
        .rename("fim_em")
        .reset_index()
    )
    juntas = (
        primeiro.drop(columns=["fim", "referencia"])
        .merge(resumo, on=mandato, how="left")
        .merge(fim_em, on=mandato, how="left")
    )
    juntas["_mandato"] = range(len(juntas))
    seguinte = _fca_seguinte(juntas, auditores, tabela)
    sumiu = juntas["fim"].isna() & seguinte["proxima"].notna().to_numpy()
    fim_que_sumiu = (
        pd.concat([seguinte["entrou_em"], seguinte["proxima_em"]], axis=1)
        .min(axis=1)
        .to_numpy()
    )
    ate = juntas["fim"].mask(sumiu, fim_que_sumiu)
    ate_publico_em = juntas["fim_em"].mask(sumiu, seguinte["proxima_em"].to_numpy())
    return juntas.drop(columns=["_mandato", "ultima", "fim_em"]).assign(
        tipo=AUDITA,
        aconteceu_em=juntas["inicio"],
        publico_em=juntas["conhecido_em"],
        ate=ate,
        ate_publico_em=ate_publico_em,
        fonte="cvm-fca",
        conferido_por=PELA_REGRA,
    )


# --- carteiras dos fundos (CDA): valores mobiliários, emite e detem -----------------------------
def mes(datas: pd.Series) -> pd.Series:
    return datas.dt.year * MESES_POR_ANO + datas.dt.month - 1


def _fim_do_mes(meses: pd.Series) -> pd.Series:
    inicio = pd.to_datetime(
        {"year": meses // MESES_POR_ANO, "month": meses % MESES_POR_ANO + 1, "day": 1}
    )
    return inicio + pd.offsets.MonthEnd(0)


def _posicoes_validas(posicoes: pd.DataFrame) -> pd.DataFrame:
    tabela = posicoes[posicoes["isin"].astype(str).str.fullmatch(ISIN.pattern)]
    return tabela.assign(
        competencia=_dia(tabela["competencia"]),
        disponivel_em=_dia(tabela["disponivel_em"]),
    )


def isins_das_posicoes(posicoes: pd.DataFrame) -> pd.DataFrame:
    """Cada ISIN com o emissor, o primeiro e o último mês visto e quando ficou público."""
    tabela = _posicoes_validas(posicoes).sort_values(
        ["isin", "competencia", "disponivel_em"], kind="stable"
    )
    if tabela.empty:
        return pd.DataFrame(
            columns=[
                "isin",
                "emissor",
                "primeiro",
                "ultimo",
                "publico_em",
                "origem_sha256",
            ]
        )
    por_isin = tabela.groupby("isin", sort=True)
    return pd.DataFrame(
        {
            "emissor": por_isin["emissor"].first(),
            "primeiro": por_isin["competencia"].min(),
            "ultimo": por_isin["competencia"].max(),
            "publico_em": por_isin["disponivel_em"].min(),
            "origem_sha256": por_isin["origem_sha256"].first(),
        }
    ).reset_index()


def fundos_das_posicoes(posicoes: pd.DataFrame) -> pd.DataFrame:
    """Cada fundo (ou classe) das carteiras, com o tipo e o nome da carteira mais recente e quando
    ficou público pela primeira vez: metade das linhas do CDA é de fundo fora do cadastro."""
    tabela = posicoes.assign(
        cnpj_fundo=posicoes["cnpj_fundo"].map(normalizar_cnpj),
        competencia=_dia(posicoes["competencia"]),
        disponivel_em=_dia(posicoes["disponivel_em"]),
    ).dropna(subset=["cnpj_fundo"])
    tabela = tabela.sort_values(["cnpj_fundo", "competencia"], kind="stable")
    por_fundo = tabela.groupby("cnpj_fundo", sort=True)
    return pd.DataFrame(
        {
            "fundo": por_fundo["fundo"].last(),
            "tipo_do_fundo": por_fundo["tipo_do_fundo"].last(),
            "ultimo": por_fundo["competencia"].max(),
            "publico_em": por_fundo["disponivel_em"].min(),
        }
    ).reset_index()


def juntar_fundos(partes: list[pd.DataFrame]) -> pd.DataFrame:
    """Os fundos de cada ano somados: o nome e o tipo do ano mais recente, o primeiro dia público."""
    partes = [p for p in partes if not p.empty]
    if not partes:
        return pd.DataFrame(
            columns=["cnpj_fundo", "fundo", "tipo_do_fundo", "ultimo", "publico_em"]
        )
    tabela = pd.concat(partes, ignore_index=True).sort_values(
        ["cnpj_fundo", "ultimo"], kind="stable"
    )
    por_fundo = tabela.groupby("cnpj_fundo", sort=True)
    return pd.DataFrame(
        {
            "fundo": por_fundo["fundo"].last(),
            "tipo_do_fundo": por_fundo["tipo_do_fundo"].last(),
            "ultimo": por_fundo["ultimo"].max(),
            "publico_em": por_fundo["publico_em"].min(),
        }
    ).reset_index()


def juntar_isins(partes: list[pd.DataFrame]) -> pd.DataFrame:
    """Os ISINs de cada ano somados (o primeiro mês de todos, o último de todos)."""
    tabela = pd.concat([p for p in partes if not p.empty], ignore_index=True) if any(
        not p.empty for p in partes
    ) else isins_das_posicoes(pd.DataFrame(columns=["isin", "competencia", "disponivel_em"]))  # fmt: skip
    if tabela.empty:
        return tabela
    tabela = tabela.sort_values(["isin", "primeiro"], kind="stable")
    por_isin = tabela.groupby("isin", sort=True)
    return pd.DataFrame(
        {
            "emissor": por_isin["emissor"].first(),
            "primeiro": por_isin["primeiro"].min(),
            "ultimo": por_isin["ultimo"].max(),
            "publico_em": por_isin["publico_em"].min(),
            "origem_sha256": por_isin["origem_sha256"].first(),
        }
    ).reset_index()


def periodos_das_posicoes(posicoes: pd.DataFrame) -> pd.DataFrame:
    """Meses seguidos do mesmo fundo, ISIN e tipo de posição viram um período (`inicio`..`fim` em
    meses). Rode por ano e junte com `comprimir_periodos` de novo: o ano inteiro não precisa caber."""
    tabela = _posicoes_validas(posicoes)
    tabela = tabela.assign(
        cnpj_fundo=tabela["cnpj_fundo"].map(normalizar_cnpj),
        inicio=mes(tabela["competencia"]),
        publico_em=tabela["disponivel_em"],
    ).sort_values(["disponivel_em"], kind="stable")
    tabela["fim"] = tabela["inicio"]
    return comprimir_periodos(
        tabela[
            [
                "cnpj_fundo",
                "isin",
                "tipo",
                "inicio",
                "fim",
                "publico_em",
                "origem_sha256",
            ]
        ],
        ["cnpj_fundo", "isin", "tipo"],
    )


def detem(periodos: pd.DataFrame, r: Resolvedor, ultimo_mes: int) -> pd.DataFrame:
    """O fundo → o valor mobiliário, um período por meses seguidos. O período que chega ao último mês
    da base continua; os outros acabam no mês seguinte (a carteira já não tinha a posição)."""
    if periodos.empty:
        return _VAZIA
    tabela = periodos.assign(
        de=r.sistema("cnpj", periodos["cnpj_fundo"]),
        para=r.sistema("isin", periodos["isin"]),
    )
    tabela = _com_as_duas_pontas(tabela, "detem")
    continua = tabela["fim"] >= ultimo_mes
    ate = _fim_do_mes(tabela["fim"] + 1).mask(continua)
    return tabela.assign(
        tipo=DETEM,
        papel=tabela["tipo"],
        aconteceu_em=_fim_do_mes(tabela["inicio"]),
        ate=ate,
        # a carteira que já não tinha a posição só ficou pública 90 dias depois do mês
        ate_publico_em=ate + pd.Timedelta(days=DIAS_ATE_FICAR_PUBLICA),
        fonte="cvm-cda",
        conferido_por=PELA_REGRA,
    )


def emite(isins: pd.DataFrame, identificadores: pd.DataFrame) -> pd.DataFrame:
    """A empresa dona do emissor do ISIN → o valor mobiliário. O emissor tem de apontar para uma
    empresa só em algum momento da vida do ISIN; duas empresas no período é conflito e não liga."""
    if isins.empty:
        return _VAZIA
    r = Resolvedor(identificadores)
    emissores = identificadores[identificadores["sistema"] == "emissor"]
    pares = isins.merge(
        emissores[["valor", "id_entidade", "desde", "ate", "publico_em", "conferido_por"]],
        left_on="emissor", right_on="valor", suffixes=("", "_emissor"),
    )  # fmt: skip
    cruza = (pares["desde"].isna() | (pares["desde"] <= pares["ultimo"])) & (
        pares["ate"].isna() | (pares["ate"] > pares["primeiro"])
    )
    pares = pares[cruza]
    uma_so = pares.groupby("isin")["id_entidade"].transform("nunique") == 1
    if (~uma_so).any():
        log.info(
            "emite: %d ISINs com emissor de mais de uma empresa (conflito)",
            pares.loc[~uma_so, "isin"].nunique(),
        )
    pares = pares[uma_so].sort_values(["isin", "publico_em_emissor"], kind="stable")
    pares = pares.drop_duplicates("isin")
    tabela = pares.assign(
        de=pares["id_entidade"], para=r.sistema("isin", pares["isin"])
    )
    tabela = _com_as_duas_pontas(tabela, "emite")
    return tabela.assign(
        tipo=EMITE,
        aconteceu_em=tabela["primeiro"],
        publico_em=tabela[["publico_em", "publico_em_emissor"]].max(axis=1),
        fonte="cvm-cda",
    )
