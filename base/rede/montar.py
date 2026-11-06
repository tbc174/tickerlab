"""Montagem das tabelas `entidades` e `identificadores` da rede (ADR 0077; plano, tarefa 2.6).

Só com o que a base já tem (nenhuma coleta nova): o cadastro de companhias da CVM, os tickers e os
emissores do FCA, os emissores antigos conferidos, as controladas do FRE, a empresa ↔ série, o cadastro
de fundos (com administrador, gestor PJ, auditor, custodiante e controlador), o cadastro do IF.data e a
ponte LEI ↔ CNPJ do GLEIF. Cada fonte vira **observações** (`base/rede/resolucao.py`); a natureza
jurídica e o MEI vêm de duas colunas da Receita (`base/receita_natureza.py`).

Desde o PR 3 entram também o **valor mobiliário** (pelo ISIN das carteiras dos fundos) e a **firma de
auditoria** (pelo código da CVM, só a que informa CNPJ: auditor pessoa física nunca entra; a natureza
vem da Receita pela raiz do CNPJ mais frequente do código), e
`montar_ligacoes` monta a tabela `ligacoes` (`base/rede/ligacoes_das_fontes.py`).

Fica de fora, de propósito: entidade só com nome (série de governo, regra 6), conglomerado do IF.data
(é um grupo, não uma entidade: a ligação de cada instituição com a líder vai para `ligacoes`), produto
do Comex (é exposição, não entidade) e gestor pessoa física.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field

import pandas as pd

from base.bcb_ifdata import cadastro_mais_novo, disponivel_em
from base.cnpj import completo, dv_confere, normalizar_cnpj
from base.pessoas.sem_cpf import tirar_cpf_da_coluna
from base.rede import ids, ligacoes_das_fontes
from base.rede.entidades import COMPANHIA_ABERTA, FUNDO_DE_INVESTIMENTO, com_natureza
from base.rede.ligacoes import normalizar
from base.rede.resolucao import (
    COLUNAS_DAS_OBSERVACOES,
    PELA_REGRA,
    PELA_TABELA,
    resolver,
)

EMPRESA, FUNDO = "empresa", "fundo"
VALOR_MOBILIARIO, AUDITOR = "valor_mobiliario", "auditor"
TEM_RAIZ = (EMPRESA, FUNDO)  # só estes se procuram na Receita (natureza jurídica e MEI)
CATEGORIA_FUNDO_DO_GLEIF = "FUND"
CONFERIDOS_NO_FCA = "códigos conferidos"  # `base/fca.py::PELOS_CODIGOS_CONFERIDOS`
CONFERIDA_NA_EMPRESA_SERIE = "tabela"  # `base/empresa_serie.py::PELA_TABELA`
PRODUTO_DO_COMEX = "produto"
PESSOA_JURIDICA = "PJ"
INSTITUICAO_INDIVIDUAL = (
    r"\d{8}"  # no IF.data, o código da instituição individual é a raiz
)
# quem dá o nome da entidade, da mais confiável para a menos (o regulador que registra vem antes)
PRIORIDADE_DO_NOME = {
    "cvm-cadastro": 0,
    "cvm-fundos": 1,
    "bcb-ifdata": 2,
    "gleif": 3,
    "cvm-fre": 4,
    "cvm-fundos-participantes": 5,
    "conferida-emissores": 6,
    "empresa_serie": 7,
    "cvm-fca": 8,
    "cvm-fca-auditores": 9,
    "cvm-cda": 10,
}
PARTICIPANTES_DOS_FUNDOS = (
    ("CNPJ_ADMIN", "ADMIN"),
    ("CNPJ_AUDITOR", "AUDITOR"),
    ("CNPJ_CUSTODIANTE", "CUSTODIANTE"),
    ("CNPJ_CONTROLADOR", "CONTROLADOR"),
)
COLUNAS_DAS_ENTIDADES = (
    "id_entidade",
    "tipo",
    "nome",
    "natureza_juridica",
    "natureza_fonte",
    "mei",
    "trata_como_pessoa",
    "fontes",
    "publico_em",
)


def _vazia() -> pd.DataFrame:
    return pd.DataFrame()


@dataclass(frozen=True)
class Entradas:
    """As tabelas de entrada (cada uma pode faltar: vira vazia)."""

    cadastro: pd.DataFrame = field(default_factory=_vazia)
    tickers: pd.DataFrame = field(default_factory=_vazia)
    emissores: pd.DataFrame = field(default_factory=_vazia)
    emissores_antigos: pd.DataFrame = field(default_factory=_vazia)
    controladas: pd.DataFrame = field(default_factory=_vazia)
    empresa_serie: pd.DataFrame = field(default_factory=_vazia)
    fundos: pd.DataFrame = field(default_factory=_vazia)
    ifdata: pd.DataFrame = field(default_factory=_vazia)
    gleif: pd.DataFrame = field(default_factory=_vazia)
    auditores: pd.DataFrame = field(default_factory=_vazia)
    isins: pd.DataFrame = field(
        default_factory=_vazia
    )  # `ligacoes_das_fontes.juntar_isins`
    fundos_das_carteiras: pd.DataFrame = field(
        default_factory=_vazia
    )  # `ligacoes_das_fontes.juntar_fundos`


def _dia(valores: Iterable) -> pd.Series:
    """Datas sem hora nem fuso (a data pública é um dia)."""
    datas = pd.to_datetime(
        pd.Series(list(valores), dtype=object), errors="coerce", utc=True
    )
    return datas.dt.tz_localize(None).dt.normalize()


def _observacoes(
    fonte: str, tipo: str, ancora: Iterable, **colunas: object
) -> pd.DataFrame:
    """Uma observação por âncora; cada coluna é um valor só (vale para todas) ou um por âncora."""
    tabela = pd.DataFrame({"ancora": list(ancora)})
    for nome, valor in colunas.items():
        tabela[nome] = (
            valor if valor is None or isinstance(valor, str | int) else list(valor)
        )  # type: ignore[arg-type]
    tabela["fonte"], tabela["tipo"] = fonte, tipo
    tabela["prioridade_do_nome"] = PRIORIDADE_DO_NOME[fonte]
    return tabela.reindex(columns=list(COLUNAS_DAS_OBSERVACOES)).dropna(
        subset=["ancora", "valor"]
    )


def _ancoras(
    fonte: str,
    cnpjs: Iterable,
    nomes: Iterable,
    publico_em: Iterable,
    natureza: str | None = None,
    tipo: str = EMPRESA,
) -> pd.DataFrame:
    """CNPJ (regra 1) e, na empresa, a raiz (regra 2) de cada âncora, com o nome da fonte."""
    cnpj = pd.Series([normalizar_cnpj(c) for c in cnpjs], dtype=object)
    ancora = cnpj.str[:8] if tipo == EMPRESA else cnpj
    comum = {
        "nome": list(nomes),
        "publico_em": _dia(publico_em),
        "natureza_da_fonte": natureza,
        "conferido_por": PELA_REGRA,
        "cnpj_da_fonte": cnpj,
    }
    partes = [
        _observacoes(fonte, tipo, ancora, sistema="cnpj", valor=cnpj, regra=1, **comum)
    ]
    if tipo == EMPRESA:
        partes.append(
            _observacoes(
                fonte, tipo, ancora, sistema="cnpj_raiz", valor=ancora, regra=2, **comum
            )
        )
    return pd.concat(partes, ignore_index=True)


def _do_cadastro(cadastro: pd.DataFrame) -> list[pd.DataFrame]:
    if cadastro.empty:
        return []
    return [
        _ancoras(
            "cvm-cadastro",
            cadastro["cnpj"],
            cadastro["empresa"],
            cadastro["registro"],
            COMPANHIA_ABERTA,
        )
    ]


def _regra_da_origem(origem: pd.Series, conferida: str) -> tuple[list[int], list[str]]:
    pela_tabela = (origem == conferida).tolist()
    return (
        [7 if t else 4 for t in pela_tabela],
        [PELA_TABELA if t else PELA_REGRA for t in pela_tabela],
    )


def _dos_tickers(tickers: pd.DataFrame) -> list[pd.DataFrame]:
    """Ticker: vale e é público da entrega do FCA que o trouxe (`primeiro_visto`), não do início da
    negociação que a empresa informa; até a entrega do FCA que veio sem ele (`valido_ate`)."""
    if tickers.empty:
        return []
    regra, por = _regra_da_origem(tickers["origem"], CONFERIDOS_NO_FCA)
    visto = _dia(tickers["primeiro_visto"])
    return [
        _observacoes(
            "cvm-fca",
            EMPRESA,
            tickers["cnpj"].map(normalizar_cnpj).str[:8],
            sistema="ticker",
            valor=tickers["codigo"],
            desde=visto,
            ate=_dia(tickers["valido_ate"]),
            publico_em=visto,
            regra=regra,
            conferido_por=por,
        )
    ]


def _dos_emissores(emissores: pd.DataFrame) -> list[pd.DataFrame]:
    """Emissor com mais de um CNPJ no FCA é conflito lá mesmo: não entra."""
    if emissores.empty:
        return []
    validos = emissores[~emissores["conflito"].astype(bool)]
    regra, por = _regra_da_origem(validos["origem"], CONFERIDOS_NO_FCA)
    desde = _dia(validos["primeiro_recebido_em"])
    return [
        _observacoes(
            "cvm-fca",
            EMPRESA,
            validos["cnpj"].map(normalizar_cnpj).str[:8],
            sistema="emissor",
            valor=validos["emissor"],
            desde=desde,
            publico_em=desde,
            regra=regra,
            conferido_por=por,
        )
    ]


def _dos_emissores_antigos(antigos: pd.DataFrame) -> list[pd.DataFrame]:
    """Emissores de antes do FCA, ligados à mão (`base/conferidas/emissores_antigos.csv`)."""
    if antigos.empty:
        return []
    registro = _dia(antigos["registro"])
    return [
        _ancoras(
            "conferida-emissores",
            antigos["cnpj"],
            antigos["empresa_no_cadastro"],
            registro,
        ),
        _observacoes(
            "conferida-emissores",
            EMPRESA,
            antigos["cnpj"].map(normalizar_cnpj).str[:8],
            sistema="emissor",
            valor=antigos["emissor"],
            desde=registro,
            ate=_dia(antigos["cancelamento"]),
            publico_em=registro,
            regra=7,
            conferido_por=PELA_TABELA,
        ),
    ]


def _das_controladas(controladas: pd.DataFrame) -> list[pd.DataFrame]:
    if controladas.empty:
        return []
    return [
        _ancoras(
            "cvm-fre",
            controladas["cnpj"],
            tirar_cpf_da_coluna(controladas["razao_social"]),
            controladas["conhecido_em"],
        ),
        _ancoras(
            "cvm-fre",
            controladas["cnpj_companhia"],
            controladas["companhia"],
            controladas["conhecido_em"],
        ),
    ]


def _da_empresa_serie(ligadas: pd.DataFrame) -> list[pd.DataFrame]:
    """O código de cada regulador (regra 5; regra 7 quando a raiz veio da tabela conferida). Sem raiz
    (ligada só pelo nome) fica para a série de governo; produto do Comex não é entidade."""
    if ligadas.empty:
        return []
    entidades = ligadas[
        ligadas["raiz"].notna() & (ligadas["via"] != PRODUTO_DO_COMEX)
    ].drop_duplicates(subset=["fonte", "chave", "raiz"])
    pela_tabela = (entidades["por"] == CONFERIDA_NA_EMPRESA_SERIE).tolist()
    montado = _dia(
        entidades["montado_em"]
    )  # fonte de governo: conhecida desde que guardada
    comum = {"nome": entidades["nome"], "publico_em": montado}
    return [
        _observacoes(
            "empresa_serie",
            EMPRESA,
            entidades["raiz"],
            sistema="cnpj_raiz",
            valor=entidades["raiz"],
            regra=2,
            conferido_por=PELA_REGRA,
            **comum,
        ),
        _observacoes(
            "empresa_serie",
            EMPRESA,
            entidades["raiz"],
            sistema="codigo_" + entidades["fonte"],
            valor=entidades["chave"].astype(str),
            regra=[7 if t else 5 for t in pela_tabela],
            conferido_por=[PELA_TABELA if t else PELA_REGRA for t in pela_tabela],
            **comum,
        ),
    ]


def _cnpj_de_empresa(valor: object) -> str | None:
    """Só CNPJ de 14 com o DV conferido (participante do fundo pode vir com CPF ou vazio)."""
    if not isinstance(valor, str):
        return None
    cnpj = completo(valor)
    return cnpj if cnpj and dv_confere(cnpj) else None


def _dos_fundos(fundos: pd.DataFrame) -> list[pd.DataFrame]:
    """O fundo (âncora = CNPJ de 14, código da CVM pela regra 5) e as empresas que o servem."""
    if fundos.empty:
        return []
    registro = _dia(fundos["DT_REG"])
    cnpj = fundos["CNPJ_FUNDO"].map(normalizar_cnpj)
    # a CVM reaproveita o código em tipos diferentes de fundo (FI 19 e FIF 19 são fundos diferentes)
    tipo_do_fundo = (
        fundos["TP_FUNDO"].fillna(FUNDO)
        if "TP_FUNDO" in fundos
        else pd.Series(FUNDO, fundos.index)
    )
    partes = [
        _ancoras(
            "cvm-fundos",
            fundos["CNPJ_FUNDO"],
            fundos["DENOM_SOCIAL"],
            registro,
            FUNDO_DE_INVESTIMENTO,
            tipo=FUNDO,
        ),
        _observacoes(
            "cvm-fundos",
            FUNDO,
            cnpj,
            sistema="codigo_cvm_" + tipo_do_fundo,
            valor=fundos["CD_CVM"],
            publico_em=registro,
            regra=5,
            conferido_por=PELA_REGRA,
        ),
    ]
    colunas = list(PARTICIPANTES_DOS_FUNDOS)
    if "PF_PJ_GESTOR" in fundos:
        gestor_pj = fundos["PF_PJ_GESTOR"] == PESSOA_JURIDICA
        fundos = fundos.assign(
            _GESTOR_PJ=fundos["CPF_CNPJ_GESTOR"].where(gestor_pj, None)
        )
        colunas.append(("_GESTOR_PJ", "GESTOR"))
    for coluna_do_cnpj, coluna_do_nome in colunas:
        if coluna_do_cnpj not in fundos:
            continue
        participante = fundos[coluna_do_cnpj].map(_cnpj_de_empresa)
        com_cnpj = participante.notna().to_numpy()
        partes.append(
            _ancoras(
                "cvm-fundos-participantes",
                participante[com_cnpj],
                fundos[coluna_do_nome][com_cnpj],
                registro[com_cnpj],
            )
        )
    return partes


def _do_ifdata(cadastro: pd.DataFrame) -> list[pd.DataFrame]:
    """Só a instituição individual (código = raiz); público 120 dias depois da data-base."""
    if cadastro.empty:
        return []
    cadastro = cadastro_mais_novo(cadastro)  # a revisão do BC não repete a instituição
    individuais = cadastro[
        cadastro["cod_inst"].astype(str).str.fullmatch(INSTITUICAO_INDIVIDUAL)
    ]
    publico = _dia(disponivel_em(individuais))
    comum = {
        "nome": individuais["instituicao"],
        "publico_em": publico,
        "conferido_por": PELA_REGRA,
    }
    raiz = individuais["cod_inst"]
    return [
        _observacoes(
            "bcb-ifdata",
            EMPRESA,
            raiz,
            sistema="cnpj_raiz",
            valor=raiz,
            regra=2,
            **comum,
        ),
        _observacoes(
            "bcb-ifdata",
            EMPRESA,
            raiz,
            sistema="codigo_bcb_ifdata",
            valor=raiz,
            regra=5,
            **comum,
        ),
    ]


def _do_gleif(ponte: pd.DataFrame) -> list[pd.DataFrame]:
    """LEI (regra 3) da ponte sem conflito; o fundo do GLEIF fica na âncora do CNPJ de 14."""
    if ponte.empty:
        return []
    partes = []
    validos = ponte[~ponte["conflito"].astype(bool)]
    for tipo, linhas in (
        (FUNDO, validos[validos["categoria"] == CATEGORIA_FUNDO_DO_GLEIF]),
        (EMPRESA, validos[validos["categoria"] != CATEGORIA_FUNDO_DO_GLEIF]),
    ):
        if linhas.empty:
            continue
        ancora = linhas["cnpj"] if tipo == FUNDO else linhas["cnpj"].str[:8]
        partes += [
            _ancoras(
                "gleif", linhas["cnpj"], linhas["nome"], linhas["publico_em"], tipo=tipo
            ),
            _observacoes(
                "gleif",
                tipo,
                ancora,
                sistema="lei",
                valor=linhas["lei"],
                publico_em=_dia(linhas["publico_em"]),
                regra=3,
                conferido_por=PELA_REGRA,
                cnpj_da_fonte=linhas["cnpj"],
            ),
        ]
    return partes


def _dos_auditores(auditores: pd.DataFrame) -> list[pd.DataFrame]:
    """A firma de auditoria pelo código da CVM (regra 5), com o nome e o CNPJ que ela informa."""
    firmas = ligacoes_das_fontes.auditores_sem_conflito(auditores)
    if firmas.empty:
        return []
    codigo = firmas["codigo_cvm_auditor"]
    return [
        _observacoes(
            "cvm-fca-auditores",
            AUDITOR,
            codigo,
            sistema="codigo_cvm_auditor",
            valor=codigo,
            nome=firmas["auditor"],
            publico_em=_dia(firmas["conhecido_em"]),
            regra=5,
            conferido_por=PELA_REGRA,
            cnpj_da_fonte=firmas["auditor_cnpj"],
        )
    ]


def _dos_isins(isins: pd.DataFrame) -> list[pd.DataFrame]:
    """O valor mobiliário pelo ISIN (regra 4), público desde a primeira carteira que o mostrou."""
    if isins.empty:
        return []
    return [
        _observacoes(
            "cvm-cda",
            VALOR_MOBILIARIO,
            isins["isin"],
            sistema="isin",
            valor=isins["isin"],
            publico_em=_dia(isins["publico_em"]),
            regra=4,
            conferido_por=PELA_REGRA,
        )
    ]


def _dos_fundos_das_carteiras(fundos: pd.DataFrame) -> list[pd.DataFrame]:
    """O fundo (ou classe da CVM 175) que aparece nas carteiras, com ou sem cadastro (regra 1): o nome
    do cadastro, quando há, ganha pela prioridade."""
    if fundos.empty:
        return []
    return [
        _ancoras(
            "cvm-cda",
            fundos["cnpj_fundo"],
            fundos["fundo"],
            fundos["publico_em"],
            FUNDO_DE_INVESTIMENTO,
            tipo=FUNDO,
        )
    ]


def _cnpjs_de_fundo(entradas: Entradas) -> set[str]:
    """Os CNPJs que são fundo: os do cadastro e os das carteiras."""
    cnpjs = set()
    if not entradas.fundos.empty:
        cnpjs |= set(entradas.fundos["CNPJ_FUNDO"].map(normalizar_cnpj).dropna())
    if not entradas.fundos_das_carteiras.empty:
        cnpjs |= set(entradas.fundos_das_carteiras["cnpj_fundo"].dropna())
    return cnpjs


def _fundo_e_sempre_o_fundo(
    tabela: pd.DataFrame, cnpjs_de_fundo: set[str]
) -> pd.DataFrame:
    """CNPJ de fundo (do cadastro ou das carteiras) é o fundo, venha de onde vier (o FRE lista FIPs
    como controladas; o GLEIF registra fundos como GENERAL): a observação vai para a âncora do fundo."""
    if not cnpjs_de_fundo:
        return tabela
    e_fundo = (tabela["tipo"] == EMPRESA) & tabela["cnpj_da_fonte"].isin(cnpjs_de_fundo)
    tabela = tabela.assign(
        tipo=tabela["tipo"].mask(e_fundo, FUNDO),
        ancora=tabela["ancora"].mask(e_fundo, tabela["cnpj_da_fonte"]),
    )
    return tabela[~(e_fundo & (tabela["sistema"] == "cnpj_raiz"))]  # fundo não tem raiz


def observacoes(entradas: Entradas) -> pd.DataFrame:
    """As observações de todas as fontes, numa ordem que não depende da ordem das linhas."""
    partes = [
        *_do_cadastro(entradas.cadastro),
        *_dos_tickers(entradas.tickers),
        *_dos_emissores(entradas.emissores),
        *_dos_emissores_antigos(entradas.emissores_antigos),
        *_das_controladas(entradas.controladas),
        *_da_empresa_serie(entradas.empresa_serie),
        *_dos_fundos(entradas.fundos),
        *_do_ifdata(entradas.ifdata),
        *_do_gleif(entradas.gleif),
        *_dos_auditores(entradas.auditores),
        *_dos_isins(entradas.isins),
        *_dos_fundos_das_carteiras(entradas.fundos_das_carteiras),
    ]
    partes = [p for p in partes if not p.empty]
    if not partes:
        return pd.DataFrame(columns=list(COLUNAS_DAS_OBSERVACOES))
    tabela = _fundo_e_sempre_o_fundo(
        pd.concat(partes, ignore_index=True), _cnpjs_de_fundo(entradas)
    )
    for coluna in ("desde", "ate", "publico_em"):
        tabela[coluna] = pd.to_datetime(tabela[coluna])
    tabela["regra"] = tabela["regra"].astype(int)
    return tabela


def raiz_dos_auditores(observacoes: pd.DataFrame) -> pd.Series:
    """A raiz do CNPJ de cada firma de auditoria (índice: o código da CVM), para a Receita dizer a
    natureza: a da maioria das linhas do código, porque parte do FCA traz o CNPJ errado (no empate,
    a menor, para sair sempre a mesma)."""
    firmas = observacoes[observacoes["tipo"] == AUDITOR]
    linhas = (
        firmas.assign(raiz=firmas["cnpj_da_fonte"].str[:8])
        .dropna(subset=["raiz"])
        .groupby(["ancora", "raiz"])
        .size()
        .rename("linhas")
        .reset_index()
        .sort_values(["ancora", "linhas", "raiz"], ascending=[True, False, True])
    )
    return linhas.drop_duplicates("ancora").set_index("ancora")["raiz"]


def raizes(observacoes: pd.DataFrame) -> set[str]:
    """As raízes de CNPJ da rede: o que se procura na Receita (natureza e MEI)."""
    com_raiz = observacoes[observacoes["tipo"].isin(TEM_RAIZ)]
    return set(com_raiz["ancora"].dropna().str[:8]) | set(
        raiz_dos_auditores(observacoes)
    )


def montar_rede(
    observacoes: pd.DataFrame,
    naturezas: pd.DataFrame,
    meis: pd.DataFrame,
    fixados: dict[ids.Chave, str],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """(entidades, identificadores, conflitos), ordenados pelo id (o mesmo resultado sempre)."""
    entidades, identificadores, conflitos = resolver(observacoes, fixados)
    raiz = (
        entidades["ancora"]
        .str[:8]
        .where(entidades["tipo"].isin(TEM_RAIZ))
        .fillna(entidades["ancora"].map(raiz_dos_auditores(observacoes)))
        .where(entidades["tipo"].isin((*TEM_RAIZ, AUDITOR)))
    )
    entidades = com_natureza(entidades.assign(raiz=raiz), naturezas, meis)
    entidades = entidades[list(COLUNAS_DAS_ENTIDADES)]
    return (
        entidades.sort_values("id_entidade").reset_index(drop=True),
        identificadores.sort_values(
            ["id_entidade", "sistema", "valor", "desde"]
        ).reset_index(drop=True),
        conflitos,
    )


def montar_ligacoes(
    entradas: Entradas,
    identificadores: pd.DataFrame,
    periodos: pd.DataFrame,
    ultimo_mes: int,
) -> pd.DataFrame:
    """A tabela `ligacoes` de todas as fontes. `periodos` são os da `detem`, já comprimidos
    (`ligacoes_das_fontes.periodos_das_posicoes`); `ultimo_mes`, o último mês das carteiras."""
    r = ligacoes_das_fontes.Resolvedor(identificadores)
    partes = [
        ligacoes_das_fontes.das_controladas(entradas.controladas, r),
        ligacoes_das_fontes.opera_para(entradas.empresa_serie, r),
        ligacoes_das_fontes.do_conglomerado(entradas.ifdata, r),
        ligacoes_das_fontes.audita(entradas.auditores, r),
        ligacoes_das_fontes.emite(entradas.isins, identificadores),
        ligacoes_das_fontes.detem(periodos, r, ultimo_mes),
    ]
    partes = [p for p in partes if not p.empty]
    return normalizar(
        pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()
    )
