"""Colunas do modelo de atraso **como eram na data da previsão** (modelo 8; critério de pronto, PR 3).

Cada exemplo do rótulo (`rotulo.py`: empresa, documento, data-base) ganha as colunas que um analista
teria na mão no dia da previsão. **Regra de ouro (com teste de propriedade):** toda coluna usa só fatos
públicos **antes** de `data_da_previsao`. A CVM só informa o dia da entrega, não a hora: o que chegou
no próprio dia fica de fora (vale a véspera, como em `base/ponto_no_tempo.py`).

Um bloco por grupo do plano (`planos/2026-10-14-modelo-8-atraso-na-entrega.md`):
- **Histórico de entregas** (os próprios exemplos e o índice da DFP/ITR): um documento anterior só
  conta se já se sabia o resultado dele na véspera (entregue antes, ou prazo vencido sem entrega); o
  atraso é o que se via naquele dia, nunca o de hoje. O próprio documento nunca entra.
- **Auditor** (`base/auditores.py`): o auditor do FCA vigente (o de referência e versão mais novas
  entre os entregues), se é uma das quatro grandes, anos com ele e troca anunciada nos últimos 12 meses.
- **Dificuldade** (`base/rotulos.py`, decisão do Tiago de 17/10/2026): só a **recuperação judicial da
  própria companhia**, pela raiz do CNPJ (filiais juntas); sem a extrajudicial e sem eventos de outras
  empresas do grupo. Vazio quando a empresa não tem nenhum documento no IPE antes da data (não dá para
  dizer "nunca").
- **Cadastro** (nota i do critério de pronto): setor, categoria, controle e mês do exercício vêm do
  **FCA vigente na data** (`base/fca_geral.py`), nunca do `cad_cia_aberta.csv` de hoje; dele só sai a
  data de registro (anos de registro). Ação na bolsa e segmento, dos valores mobiliários desse FCA.
- **Balanço** (`base/ponto_no_tempo.py`): o último balanço público na véspera (consolidado quando há);
  uma reapresentação publicada depois não aparece. Prejuízo é o do último exercício (12 meses) público,
  não a soma dos 4 trimestres (o acumulado anual já é a conta da CVM; desvio do plano anotado no PR).
- **Calendário**: trimestre da data-base e prazo a até 7 dias depois de um feriado nacional.

Fora (decisões escritas): o selo de qualidade (nota q do critério: fora da v1), fatos relevantes
(decisão de 17/10), o ano, o nome e o CNPJ (o modelo decoraria épocas e empresas). O rótulo também não
está aqui: a tabela tem só as colunas, e junta-se ao rótulo pela chave na hora de treinar.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from base.cnpj import SEPARADORES
from base.dias_uteis import dias_uteis, feriados_nacionais
from base.modelos.atraso import rotulo
from base.ponto_no_tempo import como_era_em
from base.rotulos import JUDICIAL

TABELA = "colunas_atraso"
CHAVE = ["cnpj", "documento", "referencia"]
HISTORICO = (
    "documentos_anteriores", "atrasou_o_anterior", "atrasos_nos_ultimos_4",
    "atrasos_nos_ultimos_8", "media_dias_de_atraso_ultimos_4", "folga_media_ultimos_4",
    "entregou_o_anterior_no_ultimo_dia", "reapresentacoes_12_meses",
)  # fmt: skip
AUDITOR = ("auditor_rede_grande", "trocou_de_auditor_12_meses", "anos_com_o_auditor")
DIFICULDADE = ("ja_entrou_em_recuperacao_judicial",)
CADASTRO = (
    "setor", "categoria", "controle_acionario", "exercicio_fora_de_dezembro",
    "anos_de_registro", "tem_acao_na_bolsa", "segmento_de_listagem",
)  # fmt: skip
BALANCO = (
    "ativo_total", "patrimonio_liquido_negativo", "prejuizo_no_ultimo_exercicio",
    "divida_curto_prazo_sobre_caixa",
)  # fmt: skip
CALENDARIO = ("trimestre", "prazo_perto_de_feriado")
COLUNAS_PARA_PREVER = (
    *HISTORICO, *AUDITOR, *DIFICULDADE, *CADASTRO, *BALANCO, *CALENDARIO,
)  # fmt: skip
COLUNAS = (*CHAVE, "data_da_previsao", *COLUNAS_PARA_PREVER)
# o tipo de cada coluna (vazio = não se sabia): o mesmo com ou sem linhas, para o Parquet e o modelo
INTEIRAS = (
    "documentos_anteriores", "atrasos_nos_ultimos_4", "atrasos_nos_ultimos_8",
    "reapresentacoes_12_meses", "trimestre",
)  # fmt: skip
TEXTOS = ("setor", "categoria", "controle_acionario", "segmento_de_listagem")
SIM_OU_NAO = (
    "atrasou_o_anterior", "entregou_o_anterior_no_ultimo_dia", "auditor_rede_grande",
    "trocou_de_auditor_12_meses", "ja_entrou_em_recuperacao_judicial",
    "exercicio_fora_de_dezembro", "tem_acao_na_bolsa", "patrimonio_liquido_negativo",
    "prejuizo_no_ultimo_exercicio", "prazo_perto_de_feriado",
)  # fmt: skip
TIPOS = {
    **dict.fromkeys(COLUNAS_PARA_PREVER, "float64"),
    **dict.fromkeys(INTEIRAS, "Int64"),
    **dict.fromkeys(TEXTOS, "string"),
    **dict.fromkeys(SIM_OU_NAO, "boolean"),
}

GRANDES = frozenset({"rede:ey", "rede:pwc", "rede:kpmg", "rede:deloitte"})
ACOES = frozenset({"Ações Ordinárias", "Ações Preferenciais", "Units"})
NA_BOLSA = "Bolsa"
DOZE_MESES = pd.Timedelta(days=365)
UM_EXERCICIO = pd.Timedelta(
    days=360
)  # DRE de 12 meses (inícios e fins de mês variam um pouco)
PERTO_DO_FERIADO = pd.Timedelta(days=7)
DIAS_POR_ANO = 365.25
VESPERA = pd.Timedelta(days=1)
# as contas do balanço: (demonstração, conta) exata, ou o 1º nível com a descrição (ver o dicionário)
ATIVO, CAIXA, DIVIDA, PL, LUCRO = "ativo", "caixa", "divida", "pl", "lucro"
CONTAS_EXATAS = {
    ("BPA", "1"): ATIVO,
    ("BPA", "1.01.01"): CAIXA,
    ("BPP", "2.01.04"): DIVIDA,
}
PRIMEIRO_NIVEL = r"^\d\.\d\d$"


@dataclass(frozen=True)
class Fontes:
    """O que as colunas leem, cada tabela com a data em que o fato ficou público.

    - `entregas`: os exemplos do rótulo (`cnpj`, `documento`, `referencia`, `prazo`, `primeira_entrega`);
    - `indice`: todas as versões da DFP/ITR (`cnpj`, `versao`, `publico_em`);
    - `cadastro`: `base/cadastro.ler_cadastro` (`cnpj`, `registro`, `cancelamento`);
    - `fca_geral`: `base/fca_geral.py` (`conhecido_em` já com a regra do pedido de registro);
    - `valores`: valores mobiliários do FCA (`cnpj`, `referencia`, `versao`, `publico_em`, ...);
    - `auditores` e `trocas`: `base/auditores.py`;
    - `insolvencia` (`cnpj`, `rotulo`, `conhecido_em`) e `eventos` (`cnpj`, `publicado_em`): o IPE;
    - `demonstracoes`: `base/ponto_no_tempo.py` (com `divulgado_em` e `ate`).
    """

    entregas: pd.DataFrame
    indice: pd.DataFrame
    cadastro: pd.DataFrame
    fca_geral: pd.DataFrame
    valores: pd.DataFrame
    auditores: pd.DataFrame
    trocas: pd.DataFrame
    insolvencia: pd.DataFrame
    eventos: pd.DataFrame
    demonstracoes: pd.DataFrame


def _raiz(cnpj: pd.Series) -> pd.Series:
    return cnpj.str.replace(SEPARADORES, "", regex=True).str[:8]


def _por_linha(
    base: pd.DataFrame, valores: pd.Series, padrao: object = np.nan
) -> pd.Series:
    """`valores` (índice = linha do exemplo) para todas as linhas, com `padrao` nas que faltam."""
    return valores.reindex(base.index).where(base.index.isin(valores.index), padrao)


def _com(
    base: pd.DataFrame, tabela: pd.DataFrame, data: str, por: str = "cnpj"
) -> pd.DataFrame:
    """Cada exemplo com as linhas de `tabela` da mesma empresa públicas antes da previsão."""
    pares = (
        base[[por, "data_da_previsao"]]
        .reset_index(names="linha")
        .merge(tabela, on=por, suffixes=("", "_da_fonte"))
    )
    return pares[pares[data] < pares["data_da_previsao"]]


def _booleano(serie: pd.Series) -> pd.Series:
    return serie.astype("boolean")


def _historico(base: pd.DataFrame, fontes: Fontes) -> pd.DataFrame:
    entregas = fontes.entregas[["cnpj", "referencia", "prazo", "primeira_entrega"]]
    pares = (
        base[["cnpj", "referencia", "data_da_previsao"]]
        .reset_index(names="linha")
        .merge(entregas, on="cnpj", suffixes=("", "_anterior"))
    )
    dia = pares["data_da_previsao"]
    entregue = pares["primeira_entrega"] < dia
    conhecido = entregue | (pares["prazo"] < dia)
    pares = pares[(pares["referencia_anterior"] < pares["referencia"]) & conhecido]
    entregue = pares["primeira_entrega"] < pares["data_da_previsao"]
    # o que se via na véspera: sem entrega até ali, o atraso vai até a previsão
    fim = pares["primeira_entrega"].where(entregue, pares["data_da_previsao"])
    dias = np.maximum(dias_uteis(pares["prazo"], fim), 0)
    pares = pares.assign(
        atrasou=~entregue | (pares["primeira_entrega"] > pares["prazo"]),
        dias=dias,
        folga=np.where(entregue, dias_uteis(fim, pares["prazo"]), -dias),
        ultimo_dia=entregue & (pares["primeira_entrega"] == pares["prazo"]),
    ).sort_values(["linha", "referencia_anterior"], ascending=[True, False])
    pares["ordem"] = pares.groupby("linha").cumcount()
    anterior = pares[pares["ordem"] == 0].set_index("linha")
    ultimos_4 = pares[pares["ordem"] < 4].groupby("linha")
    ultimos_8 = pares[pares["ordem"] < 8].groupby("linha")
    reapresentacoes = _com(
        base, fontes.indice[fontes.indice["versao"] > 1], "publico_em"
    )
    recentes = reapresentacoes[
        reapresentacoes["publico_em"]
        >= reapresentacoes["data_da_previsao"] - DOZE_MESES
    ]
    return pd.DataFrame(
        {
            "documentos_anteriores": _por_linha(base, pares.groupby("linha").size(), 0),
            "atrasou_o_anterior": _booleano(
                _por_linha(base, anterior["atrasou"], None)
            ),
            "atrasos_nos_ultimos_4": _por_linha(base, ultimos_4["atrasou"].sum()),
            "atrasos_nos_ultimos_8": _por_linha(base, ultimos_8["atrasou"].sum()),
            "media_dias_de_atraso_ultimos_4": _por_linha(
                base, ultimos_4["dias"].mean()
            ),
            "folga_media_ultimos_4": _por_linha(base, ultimos_4["folga"].mean()),
            "entregou_o_anterior_no_ultimo_dia": _booleano(
                _por_linha(base, anterior["ultimo_dia"], None)
            ),
            "reapresentacoes_12_meses": _por_linha(
                base, recentes.groupby("linha").size(), 0
            ),
        },
        index=base.index,
    )


def _vigente(base: pd.DataFrame, tabela: pd.DataFrame, data: str) -> pd.DataFrame:
    """Por exemplo, o formulário vigente na véspera: o de (referência, versão) mais novas entre os já
    públicos (uma reentrega de ano antigo não volta no tempo). Devolve as linhas desse formulário já
    públicas na véspera, a primeira entrega antes: a mesma versão entregue de novo depois da
    previsão não entra."""
    pares = _com(base, tabela, data).sort_values(
        ["linha", "referencia", "versao", data], kind="stable"
    )
    ultimo = pares.drop_duplicates("linha", keep="last").set_index("linha")
    mesmo = (
        pares["referencia"].to_numpy()
        == ultimo["referencia"].reindex(pares["linha"]).to_numpy()
    ) & (
        pares["versao"].to_numpy()
        == ultimo["versao"].reindex(pares["linha"]).to_numpy()
    )
    return pares[mesmo]


def _auditor(base: pd.DataFrame, fontes: Fontes) -> pd.DataFrame:
    vigente = _vigente(base, fontes.auditores, "conhecido_em")
    mandatos = vigente[
        vigente["inicio"].isna() | (vigente["inicio"] < vigente["data_da_previsao"])
    ].sort_values(["linha", "inicio"], na_position="first")
    atual = mandatos.drop_duplicates("linha", keep="last").set_index("linha")
    mesma_firma = mandatos[
        mandatos["auditor_id"].to_numpy()
        == atual["auditor_id"].reindex(mandatos["linha"]).to_numpy()
    ]
    desde = mesma_firma.groupby("linha")["inicio"].min()
    anos = (base["data_da_previsao"] - desde.reindex(base.index)).dt.days / DIAS_POR_ANO
    trocas = _com(base, fontes.trocas, "conhecido_em")
    trocas = trocas[trocas["conhecido_em"] >= trocas["data_da_previsao"] - DOZE_MESES]
    com_fca = base.index.isin(vigente["linha"])
    trocou = pd.Series(base.index.isin(trocas["linha"]), index=base.index)
    return pd.DataFrame(
        {
            "auditor_rede_grande": _booleano(
                _por_linha(base, atual["auditor_id"].isin(GRANDES), None)
            ),
            "trocou_de_auditor_12_meses": _booleano(trocou.where(com_fca, None)),
            "anos_com_o_auditor": anos,
        },
        index=base.index,
    )


def _dificuldade(base: pd.DataFrame, fontes: Fontes) -> pd.DataFrame:
    com_raiz = base.assign(raiz=_raiz(base["cnpj"]))
    judicial = fontes.insolvencia[fontes.insolvencia["rotulo"] == JUDICIAL]
    judicial = _com(
        com_raiz, judicial.assign(raiz=_raiz(judicial["cnpj"])), "conhecido_em", "raiz"
    )
    eventos = fontes.eventos.assign(raiz=_raiz(fontes.eventos["cnpj"]))
    primeiro = eventos.groupby("raiz", as_index=False)["publicado_em"].min()
    conhecida = base.index.isin(
        _com(com_raiz, primeiro, "publicado_em", "raiz")["linha"]
    )
    entrou = pd.Series(base.index.isin(judicial["linha"]), index=base.index)
    return pd.DataFrame(
        {"ja_entrou_em_recuperacao_judicial": _booleano(entrou.where(conhecida, None))},
        index=base.index,
    )


def _cadastro(base: pd.DataFrame, fontes: Fontes) -> pd.DataFrame:
    vigente = _vigente(base, fontes.fca_geral, "conhecido_em").drop_duplicates("linha")
    geral = vigente.set_index("linha")
    mes = _por_linha(base, geral["mes_fim_do_exercicio"])
    registros = _com(base, fontes.cadastro.dropna(subset=["registro"]), "registro")
    registro = registros.groupby("linha")["registro"].max().reindex(base.index)
    # ações do mesmo FCA (a mesma data de referência), na versão mais nova já pública
    valores = (
        vigente[["linha", "cnpj", "referencia"]]
        .merge(fontes.valores, on=["cnpj", "referencia"], suffixes=("", "_dos_valores"))
        .merge(base[["data_da_previsao"]], left_on="linha", right_index=True)
    )
    valores = valores[valores["publico_em"] < valores["data_da_previsao"]]
    valores = valores[
        valores["versao"] == valores.groupby("linha")["versao"].transform("max")
    ]
    acoes = valores[
        valores["valor_mobiliario"].isin(ACOES)
        & (valores["mercado"] == NA_BOLSA)
        & ~(valores["fim_negociacao"] < valores["data_da_previsao"])
    ]
    com_fca = base.index.isin(vigente["linha"])
    tem_acao = pd.Series(base.index.isin(acoes["linha"]), index=base.index)
    segmento = (
        acoes.dropna(subset=["segmento"])
        .groupby("linha")["segmento"]
        .agg(lambda s: s.mode().iloc[0])
    )
    return pd.DataFrame(
        {
            "setor": _por_linha(base, geral["setor"], None),
            "categoria": _por_linha(base, geral["categoria"], None),
            "controle_acionario": _por_linha(base, geral["controle_acionario"], None),
            "exercicio_fora_de_dezembro": _booleano(
                (mes != 12).where(mes.notna(), None)
            ),
            "anos_de_registro": (base["data_da_previsao"] - registro).dt.days
            / DIAS_POR_ANO,
            "tem_acao_na_bolsa": _booleano(tem_acao.where(com_fca, None)),
            "segmento_de_listagem": _por_linha(base, segmento, None),
        },
        index=base.index,
    )


def contas_do_balanco(demonstracoes: pd.DataFrame) -> pd.DataFrame:
    """Só as contas que o bloco do balanço usa, com o item (`ativo`, `caixa`, `divida`, `pl`, `lucro`).

    PL: a conta de 1º nível do passivo cuja descrição começa por "Patrimônio Líquido" (é a 2.03 nas
    empresas e a 2.05 a 2.08 nos bancos). Lucro: a de 1º nível da DRE com "Lucro" e "Período" que não
    é "antes" de algo (a última, quando há duas: o consolidado com os minoritários).
    """
    descricao = demonstracoes["descricao"].fillna("").str.lower()
    item = pd.Series(
        [
            CONTAS_EXATAS.get((d, c))
            for d, c in zip(
                demonstracoes["demonstracao"], demonstracoes["conta"], strict=True
            )
        ],
        index=demonstracoes.index,
        dtype=object,
    )
    primeiro_nivel = demonstracoes["conta"].str.match(PRIMEIRO_NIVEL)
    item[
        (demonstracoes["demonstracao"] == "BPP")
        & primeiro_nivel
        & descricao.str.startswith("patrimônio líquido")
    ] = PL
    item[
        (demonstracoes["demonstracao"] == "DRE")
        & primeiro_nivel
        & descricao.str.contains("lucro")
        & descricao.str.contains("período")
        & ~descricao.str.contains("antes")
    ] = LUCRO
    return demonstracoes.assign(item=item).dropna(subset=["item"])


def _balanco_em(era: pd.DataFrame) -> pd.DataFrame:
    """Por empresa, os itens do último balanço e o lucro do último exercício em `era`."""
    tem_con = era.groupby("cnpj")["grupo"].transform(lambda g: (g == "con").any())
    era = era[(era["grupo"] == "con") | ~tem_con]
    balanco = era[era["item"] != LUCRO]
    balanco = balanco[balanco["fim"] == balanco.groupby("cnpj")["fim"].transform("max")]
    itens = (
        balanco.sort_values("conta")
        .drop_duplicates(["cnpj", "item"])
        .pivot(index="cnpj", columns="item", values="valor")
    )
    lucro = era[(era["item"] == LUCRO) & (era["fim"] - era["inicio"] >= UM_EXERCICIO)]
    lucro = (
        lucro.sort_values(["fim", "conta"])
        .drop_duplicates("cnpj", keep="last")
        .set_index("cnpj")["valor"]
    )
    return itens.reindex(columns=[ATIVO, CAIXA, DIVIDA, PL]).join(
        lucro.rename(LUCRO), how="outer"
    )


def _balanco(base: pd.DataFrame, fontes: Fontes) -> pd.DataFrame:
    contas = fontes.demonstracoes
    partes = []
    for dia, deste in base.groupby("data_da_previsao"):
        era = como_era_em(
            contas[contas["cnpj"].isin(set(deste["cnpj"]))], dia - VESPERA
        )
        itens = _balanco_em(era)
        partes.append(deste[["cnpj"]].join(itens, on="cnpj").drop(columns="cnpj"))
    itens = (
        pd.concat(partes).reindex(base.index)
        if partes
        else pd.DataFrame(index=base.index)
    ).reindex(columns=[ATIVO, CAIXA, DIVIDA, PL, LUCRO])
    caixa = itens[CAIXA].where(itens[CAIXA] > 0)
    return pd.DataFrame(
        {
            "ativo_total": itens[ATIVO].astype(float),
            "patrimonio_liquido_negativo": _booleano(
                (itens[PL] < 0).where(itens[PL].notna(), None)
            ),
            "prejuizo_no_ultimo_exercicio": _booleano(
                (itens[LUCRO] < 0).where(itens[LUCRO].notna(), None)
            ),
            "divida_curto_prazo_sobre_caixa": (itens[DIVIDA] / caixa).astype(float),
        },
        index=base.index,
    )


def _calendario(base: pd.DataFrame) -> pd.DataFrame:
    prazos = base["prazo"]
    anos = (
        range(int(prazos.dt.year.min()) - 1, int(prazos.dt.year.max()) + 1)
        if len(base)
        else []
    )
    feriados = np.array(
        sorted(pd.Timestamp(f) for ano in anos for f in feriados_nacionais(ano)),
        dtype="datetime64[ns]",
    )
    # o primeiro feriado em [prazo - 7 dias, prazo]
    posicao = np.searchsorted(feriados, (prazos - PERTO_DO_FERIADO).to_numpy())
    achado = feriados[np.minimum(posicao, len(feriados) - 1)] if len(feriados) else None
    perto = (
        (posicao < len(feriados)) & (achado <= prazos.to_numpy())
        if achado is not None
        else np.zeros(len(base), dtype=bool)
    )
    return pd.DataFrame(
        {"trimestre": base["referencia"].dt.quarter, "prazo_perto_de_feriado": perto},
        index=base.index,
    )


def colunas_como_era_na_data(exemplos: pd.DataFrame, fontes: Fontes) -> pd.DataFrame:
    """As colunas de cada exemplo (`cnpj`, `documento`, `referencia`, `data_da_previsao`, `prazo`),
    com fatos públicos antes de `data_da_previsao`. Devolve `COLUNAS`, uma linha por exemplo."""
    base = exemplos[[*CHAVE, "data_da_previsao", "prazo"]].reset_index(drop=True)
    blocos = [
        _historico(base, fontes),
        _auditor(base, fontes),
        _dificuldade(base, fontes),
        _cadastro(base, fontes),
        _balanco(base, fontes),
        _calendario(base),
    ]
    return pd.concat([base, *blocos], axis=1)[list(COLUNAS)].astype(TIPOS)


# as fontes das colunas (todas da CVM): para treinar, cada uma precisa da licença (ADR 0008)
FONTES_DAS_COLUNAS = (
    *rotulo.FONTES_DO_INDICE.values(), "cvm-cadastros", "cvm-hist-fca", "cvm-hist-ipe",
)  # fmt: skip
