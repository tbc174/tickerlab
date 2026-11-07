"""Os sinais da ficha de crédito por CNPJ (linha 754), pela porta, como eram num dia.

A ficha serve a quem tokeniza duplicatas, para o cedente e para o sacado: dívida ativa da União por
situação (PGFN), situação cadastral (Receita), sanções (CGU), lista suja (MTE), embargos (IBAMA),
dívida ativa do Paraná e de Minas, o Estado de Pernambuco e o do Espírito Santo como pagadores, os
FIDCs em que a empresa cede, o rating mais novo, a insolvência em 24 meses e a entrega à CVM. Cada
sinal sai com a fórmula do dicionário (`DA_FICHA`), a fonte e o dia em que ficou público.

As mesmas regras de `features_da_base`: só pela porta, com `como_era_em`; tabela que não está na base,
lista que a base ainda não olhava e companhia sem documento na CVM ficam não observadas (nunca "não
consta"); empresário individual ou MEI não tem sinal nenhum (ADR 0075). Nas listas que gravam o que
mudou, vale a versão mais nova de cada registro vista até o dia, e o registro de pessoa natural (ou
na dúvida) não entra. Nada aqui é nota, score nem opinião de crédito (ADR 0103).
"""

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd

from base import cnpj as cnpj_
from base.dicionario import TABELAS
from base.porta import Porta
from base.porta.duckdb import condicao_como_era, nome_da_view
from base.receita_codigos import situacao_cadastral
from src.credito import features_da_base as fb
from src.credito.dicionario import DA_FICHA
from src.credito.features import Feature, nova_feature
from src.dossie import agencia_de_rating
from src.rastro import DocumentoUsado

SEM_O_CNPJ = "O CNPJ não aparece em nenhum retrato da {fonte} público no dia."
SEM_LISTA = "Nenhuma linha de `{tabela}` era pública no dia: a base ainda não olhava esta fonte."
SEM_PAGAMENTO = (
    "Nenhum pagamento do Estado ao CNPJ nos 12 meses: não há dias para medir."
)
SEM_FUNDO = (
    "O CNPJ não aparece entre os maiores cedentes de nenhum FIDC nos informes dos 12 meses "
    "públicos no dia."
)
SEM_CARTEIRA = "Nenhum dos fundos informou carteira positiva na competência."
SEM_RATING = (
    "Nenhum documento da CVM com rating legível da companhia era público no dia."
)
SEM_ENTREGA = "Nenhuma DFP ou ITR da companhia tinha sido entregue à CVM até o dia."
NAO_INFORMADA = "não informada"
DIAS_DO_ANO = 365
DIAS_DA_INSOLVENCIA = 730
ENTREGAS_OLHADAS = 8
POR_CENTO = 100
RATING_EXTRAIDO = "extraido"
_CEDENTE = re.compile(r"^TAB_I2[A-Z]\d*_CPF_CNPJ_CEDENTE_\d+$")
_CARTEIRA, _INADIMPLENTE = "TAB_I2_VL_CARTEIRA", "TAB_I2A3_VL_CRED_INAD"
_PERSPECTIVAS = {
    "estavel": "estável",
    "em_observacao_negativa": "em observação negativa",
    "em_observacao_positiva": "em observação positiva",
}

# a situação da PGFN de cada sinal (o texto da coluna `tipo_situacao`)
DA_PGFN_POR_SITUACAO = {
    "divida_ativa_em_cobranca": "Em cobrança",
    "divida_ativa_com_beneficio_fiscal": "Benefício Fiscal",
    "divida_ativa_em_garantia": "Garantia",
    "divida_ativa_suspensa_pela_justica": "Suspenso por decisão judicial",
    "divida_ativa_em_negociacao": "Em negociação",
}
DO_FIDC = (
    "fundos_em_que_cede",
    "maior_participacao_como_cedente",
    "carteira_dos_fundos_em_que_cede",
    "maior_inadimplencia_dos_fundos_em_que_cede",
)
DO_RATING = ("rating_mais_recente", "perspectiva_do_rating", "dias_desde_o_rating")
DA_INSOLVENCIA = ("insolvencia_24_meses", "ultima_insolvencia_24_meses")


def _medida_do_estado(uf: str) -> tuple[str, str, str]:
    return (
        f"pagamentos_recebidos_de_{uf}_12_meses",
        f"valor_recebido_de_{uf}_12_meses",
        f"mediana_de_dias_ate_receber_de_{uf}",
    )


DO_ESTADO = {
    "sefaz_pe_ordem_cronologica": _medida_do_estado("pe"),
    "es_ordem_cronologica": _medida_do_estado("es"),
}

# a tabela de onde sai cada sinal (dá a fonte do rastro)
TABELA_DO_SINAL = {
    **dict.fromkeys(DA_PGFN_POR_SITUACAO, "pgfn_divida"),
    "situacao_cadastral_na_receita": "cnpj_situacao_cadastral",
    "sancoes_vigentes_na_cgu": "sancoes_cgu",
    "registros_na_lista_suja": "mte_lista_suja",
    "embargos_vigentes_no_ibama": "ibama_embargos",
    "divida_ativa_no_parana": "sefa_pr_divida_ativa",
    "divida_ativa_no_parana_sem_parcelamento_nem_suspensao": "sefa_pr_divida_ativa",
    "divida_ativa_em_minas_gerais": "sef_mg_divida_ativa",
    "parcelamentos_em_minas_gerais": "sef_mg_parcelamentos",
    **{chave: tabela for tabela, chaves in DO_ESTADO.items() for chave in chaves},
    **dict.fromkeys(DO_FIDC, "fidc_informe"),
    **dict.fromkeys(DO_RATING, "ratings"),
    **dict.fromkeys(DA_INSOLVENCIA, "insolvencia"),
    "atrasos_de_entrega_na_cvm": "rotulos_atraso",
}


def _fonte(chave: str) -> str:
    return TABELAS[TABELA_DO_SINAL[chave]].familia_da_fonte


def _sinal(
    chave: str,
    valor: float | str | None,
    periodo: str,
    documentos: Sequence[DocumentoUsado],
    motivo: str = "",
) -> Feature:
    return nova_feature(chave, valor, periodo, documentos, motivo, _fonte(chave))


def _nao_observados(chaves: Sequence[str], motivo: str) -> list[Feature]:
    return [_sinal(chave, None, "", [], motivo) for chave in chaves]


def _sem_a_tabela(chaves: Sequence[str]) -> list[Feature]:
    return _nao_observados(
        chaves, fb.SEM_A_TABELA.format(tabela=TABELA_DO_SINAL[chaves[0]])
    )


def _numeros(serie: pd.Series) -> pd.Series:
    """A CVM e os Estados guardam alguns números em texto ("71493220.86")."""
    return pd.to_numeric(serie, errors="coerce")


def _e(serie: pd.Series, alvo: bool) -> pd.Series:
    """Só o verdadeiro (ou o falso) de fato: vazio não é nem um nem outro."""
    return serie.map(
        lambda valor: isinstance(valor, bool | np.bool_) and bool(valor) is alvo
    ).astype(bool)


def _sim(serie: pd.Series) -> pd.Series:
    return _e(serie, True)


def _entre(serie: pd.Series, inicio: date, fim: date) -> pd.Series:
    """Datas em (inicio, fim]; vazio fica de fora."""
    quando = pd.to_datetime(serie, errors="coerce")
    return ((quando > pd.Timestamp(inicio)) & (quando <= pd.Timestamp(fim))).astype(
        bool
    )


# --- PGFN por situação ----------------------------------------------------------------------------
def _pgfn_por_situacao(porta: Porta, raiz: str, dia: date) -> list[Feature]:
    chaves = list(DA_PGFN_POR_SITUACAO)
    linhas = fb._ler(porta, "pgfn_divida", dia, {"cnpj_basico": raiz})
    if linhas is None:
        return _sem_a_tabela(chaves)
    ultimo = fb._retrato_mais_novo(
        porta, "pgfn_divida", "data_do_retrato", "inscricoes", dia
    )
    if ultimo is None:
        return _nao_observados(chaves, fb.SEM_RETRATO.format(fonte="PGFN"))
    retrato, publico = fb._dia(ultimo[0]), ultimo[1]
    periodo = f"retrato de {retrato:%d/%m/%Y}"
    documentos = [DocumentoUsado(f"PGFN: dívida ativa da União, {periodo}", publico)]
    do_retrato = linhas.loc[
        pd.to_datetime(linhas["data_do_retrato"]) == pd.Timestamp(retrato)
    ]
    principal = do_retrato[do_retrato["tipo_devedor"] == fb.DEVEDOR_PRINCIPAL]
    return [
        _sinal(chave, float(principal.loc[principal["tipo_situacao"] == situacao,
                                          "valor_consolidado"].sum()), periodo, documentos)
        for chave, situacao in DA_PGFN_POR_SITUACAO.items()
    ]  # fmt: skip


# --- Receita: situação cadastral ------------------------------------------------------------------
def _situacao_cadastral(porta: Porta, raiz: str, dia: date) -> Feature:
    chave = "situacao_cadastral_na_receita"
    linhas = fb._ler(porta, "cnpj_situacao_cadastral", dia, {"cnpj_basico": raiz})
    if linhas is None:
        return _sem_a_tabela([chave])[0]
    if linhas.empty:
        return _sinal(chave, None, "", [], SEM_O_CNPJ.format(fonte="Receita"))
    meses = linhas["mes_do_retrato"].astype(str)
    mes = max(meses)
    do_mes = linhas[meses == mes]
    linha = do_mes.sort_values("matriz", ascending=False).iloc[0]  # a matriz primeiro
    codigo = str(linha["situacao_cadastral"]).strip().zfill(2)
    periodo = f"retrato de {mes}"
    publico = fb._dia(do_mes["publico_em"].max())
    documentos = [
        DocumentoUsado(f"Receita: situação cadastral do CNPJ, {periodo}", publico)
    ]
    return _sinal(chave, situacao_cadastral(codigo) or codigo, periodo, documentos)


# --- listas que gravam o que mudou ----------------------------------------------------------------
@dataclass(frozen=True)
class _Lista:
    """As linhas do CNPJ que valiam no dia e o documento que prova que a base olhava a fonte."""

    linhas: pd.DataFrame
    documento: DocumentoUsado


def _versao_mais_nova(porta: Porta, tabela: str, dia: date) -> date | None:
    """O dia da versão mais nova da tabela inteira que já era pública no dia (None: nenhuma)."""
    condicao = condicao_como_era(porta.colunas(tabela), tabela)
    consulta = f'SELECT max(publico_em) FROM "{nome_da_view(tabela)}" WHERE {condicao}'
    (mais_nova,) = porta.con.execute(consulta, {"dia": dia.isoformat()}).fetchone() or (
        None,
    )
    return None if pd.isna(mais_nova) else fb._dia(mais_nova)


def _lista(porta: Porta, tabela: str, raiz: str, dia: date) -> _Lista | str:
    """As linhas vigentes do CNPJ, ou o motivo de não dar para saber."""
    linhas = fb._ler(porta, tabela, dia, {"cnpj_basico": raiz})
    if linhas is None:
        return fb.SEM_A_TABELA.format(tabela=tabela)
    versao = _versao_mais_nova(porta, tabela, dia)
    if versao is None:
        return SEM_LISTA.format(tabela=tabela)
    vigentes = linhas.loc[
        _sim(linhas["consta"]) & _e(linhas["trata_como_pessoa"], False)
    ]
    nome = f"`{tabela}`: a fonte como a base a via em {versao:%d/%m/%Y}"
    return _Lista(vigentes, DocumentoUsado(nome, versao))


def _medir(
    chave: str, lista: _Lista | str, medida: Callable[[pd.DataFrame], float]
) -> Feature:
    if isinstance(lista, str):
        return _sinal(chave, None, "", [], lista)
    periodo = f"até {lista.documento.publicado_em:%d/%m/%Y}"
    return _sinal(chave, medida(lista.linhas), periodo, [lista.documento])


def _quantos(linhas: pd.DataFrame) -> float:
    return len(linhas)


def _soma(coluna: str) -> Callable[[pd.DataFrame], float]:
    return lambda linhas: float(_numeros(linhas[coluna]).sum())


def _sem_desembargo(linhas: pd.DataFrame) -> float:
    return len(linhas.loc[~_sim(linhas["cancelado"]) & ~_sim(linhas["desembargado"])])


def _parana_em_aberto(linhas: pd.DataFrame) -> float:
    suspensao = linhas["suspensao"].fillna("").astype(str).str.strip()
    em_aberto = (
        (suspensao == "")
        & ~_sim(linhas["com_garantia"])
        & ~_sim(linhas["com_parcelamento_ativo"])
    )
    return float(_numeros(linhas.loc[em_aberto, "valor_total"]).sum())


# (sinal, tabela, como medir)
DAS_LISTAS: tuple[tuple[str, str, Callable[[pd.DataFrame], float]], ...] = (
    ("sancoes_vigentes_na_cgu", "sancoes_cgu", _quantos),
    ("registros_na_lista_suja", "mte_lista_suja", _quantos),
    ("embargos_vigentes_no_ibama", "ibama_embargos", _sem_desembargo),
    ("divida_ativa_no_parana", "sefa_pr_divida_ativa", _soma("valor_total")),
    (
        "divida_ativa_no_parana_sem_parcelamento_nem_suspensao",
        "sefa_pr_divida_ativa",
        _parana_em_aberto,
    ),
    ("divida_ativa_em_minas_gerais", "sef_mg_divida_ativa", _soma("saldo_da_cda")),
    ("parcelamentos_em_minas_gerais", "sef_mg_parcelamentos", _soma("debito")),
)


def _das_listas(porta: Porta, raiz: str, dia: date) -> list[Feature]:
    listas = {tabela: _lista(porta, tabela, raiz, dia) for _, tabela, _ in DAS_LISTAS}
    return [
        _medir(chave, listas[tabela], medida) for chave, tabela, medida in DAS_LISTAS
    ]


# --- o Estado como pagador ------------------------------------------------------------------------
def _do_estado(porta: Porta, tabela: str, raiz: str, dia: date) -> list[Feature]:
    chaves = DO_ESTADO[tabela]
    lista = _lista(porta, tabela, raiz, dia)
    if isinstance(lista, str):
        return _nao_observados(chaves, lista)
    inicio = dia - timedelta(days=DIAS_DO_ANO)
    pagos = lista.linhas.loc[_entre(lista.linhas["pago_em"], inicio, dia)]
    periodo = f"12 meses até {dia:%d/%m/%Y}"
    documentos = [lista.documento]
    dias = _numeros(pagos["dias_ate_pagar"]).dropna()
    return [
        _sinal(chaves[0], len(pagos), periodo, documentos),
        _sinal(chaves[1], float(_numeros(pagos["valor_pago"]).sum()), periodo, documentos),
        _sinal(chaves[2], float(dias.median()) if len(dias) else None, periodo, documentos,
               "" if len(dias) else SEM_PAGAMENTO),
    ]  # fmt: skip


# --- FIDC como cedente ----------------------------------------------------------------------------
def _informes_em_que_cede(
    porta: Porta, cnpj_formatado: str, dia: date
) -> tuple[pd.DataFrame, list[str]]:
    """Os informes dos 12 meses até o dia que listam o CNPJ entre os maiores cedentes, e as colunas
    de CNPJ do cedente (o quadro I tem um bloco por classe de cota)."""
    colunas = porta.colunas("fidc_informe")
    cedentes = [coluna for coluna in colunas if _CEDENTE.match(coluna)]
    if not cedentes:
        return pd.DataFrame(), []
    aparece = " OR ".join(f'CAST("{coluna}" AS VARCHAR) = $cnpj' for coluna in cedentes)
    consulta = (
        f'SELECT * FROM "{nome_da_view("fidc_informe")}" WHERE '
        f"{condicao_como_era(colunas, 'fidc_informe')} AND competencia > CAST($inicio AS DATE) "
        f"AND ({aparece})"
    )
    parametros = {
        "dia": dia.isoformat(),
        "inicio": (dia - timedelta(days=DIAS_DO_ANO)).isoformat(),
        "cnpj": cnpj_formatado,
    }
    return porta.con.execute(consulta, parametros).df(), cedentes


def _participacao(linha: pd.Series, cedentes: list[str], cnpj_formatado: str) -> float:
    """O maior percentual que o informe dá ao CNPJ (o mesmo cedente pode estar em mais de um bloco)."""
    percentuais = [
        pd.to_numeric(linha.get(coluna.replace("_CPF_CNPJ_", "_PR_")), errors="coerce")
        for coluna in cedentes
        if str(linha[coluna]) == cnpj_formatado
    ]
    validos = [p for p in percentuais if not pd.isna(p)]
    return max(validos) / POR_CENTO if validos else float("nan")


def _inadimplencia(fundos: pd.DataFrame) -> float | None:
    carteira = _numeros(fundos[_CARTEIRA])
    com_carteira = carteira > 0
    if not com_carteira.any():
        return None
    return float(
        (_numeros(fundos[_INADIMPLENTE]).fillna(0) / carteira)[com_carteira].max()
    )


def _fidc(porta: Porta, cnpj_formatado: str, dia: date) -> list[Feature]:
    try:
        informes, cedentes = _informes_em_que_cede(porta, cnpj_formatado, dia)
    except KeyError:
        return _sem_a_tabela(DO_FIDC)
    if informes.empty:
        versao = _versao_mais_nova(porta, "fidc_informe", dia)
        if versao is None:
            return _nao_observados(DO_FIDC, SEM_LISTA.format(tabela="fidc_informe"))
        documentos = [
            DocumentoUsado(
                f"CVM: informes de FIDC públicos até {versao:%d/%m/%Y}", versao
            )
        ]
        periodo = f"12 meses até {dia:%d/%m/%Y}"
        return [
            _sinal(DO_FIDC[0], 0, periodo, documentos),
            _sinal(DO_FIDC[1], None, periodo, documentos, SEM_FUNDO),
            _sinal(DO_FIDC[2], 0.0, periodo, documentos),
            _sinal(DO_FIDC[3], None, periodo, documentos, SEM_FUNDO),
        ]
    competencia = informes["competencia"].max()
    fundos = (
        informes[informes["competencia"] == competencia]
        .sort_values(["cnpj_fundo", "publico_em"])
        .drop_duplicates("cnpj_fundo", keep="last")
    )
    periodo = f"competência {fb._dia(competencia):%m/%Y}"
    documentos = [
        DocumentoUsado(
            f"CVM: informe mensal do FIDC {fundo}, {periodo}", fb._dia(publico)
        )
        for fundo, publico in zip(
            fundos["cnpj_fundo"], fundos["publico_em"], strict=True
        )
    ]
    participacao = fundos.apply(
        _participacao, axis=1, args=(cedentes, cnpj_formatado)
    ).max()
    inadimplencia = _inadimplencia(fundos)
    return [
        _sinal(DO_FIDC[0], len(fundos), periodo, documentos),
        _sinal(DO_FIDC[1], None if pd.isna(participacao) else float(participacao), periodo,
               documentos),
        _sinal(DO_FIDC[2], float(_numeros(fundos[_CARTEIRA]).sum()), periodo, documentos),
        _sinal(DO_FIDC[3], inadimplencia, periodo, documentos,
               "" if inadimplencia is not None else SEM_CARTEIRA),
    ]  # fmt: skip


# --- rating ---------------------------------------------------------------------------------------
def _perspectiva(valor: object) -> str:
    if valor is None or pd.isna(valor) or not str(valor).strip():  # type: ignore[arg-type]
        return NAO_INFORMADA
    return _PERSPECTIVAS.get(str(valor), str(valor).replace("_", " "))


def _rating(porta: Porta, cnpj_formatado: str, dia: date) -> list[Feature]:
    linhas = fb._ler(porta, "ratings", dia, {"cnpj": cnpj_formatado})
    if linhas is None:
        return _sem_a_tabela(DO_RATING)
    legiveis = linhas[
        (linhas["situacao_extracao"] == RATING_EXTRAIDO) & linhas["nota"].notna()
    ]
    if legiveis.empty:
        return _nao_observados(DO_RATING, SEM_RATING)
    linha = legiveis.sort_values(["publico_em", "protocolo", "versao"]).iloc[-1]
    publico = fb._dia(linha["publico_em"])
    periodo = f"documento de {publico:%d/%m/%Y}"
    nome = (
        f"CVM: rating no IPE, protocolo {linha['protocolo']}, versão {linha['versao']}"
    )
    documentos = [DocumentoUsado(nome, publico, str(linha["link"] or ""))]
    escala = f", escala {linha['escala']}" if linha["escala"] else ""
    texto = f"{linha['nota']} ({agencia_de_rating(linha['agencia'])}{escala})"
    return [
        _sinal(DO_RATING[0], texto, periodo, documentos),
        _sinal(DO_RATING[1], _perspectiva(linha["perspectiva"]), periodo, documentos),
        _sinal(DO_RATING[2], (dia - publico).days, periodo, documentos),
    ]


# --- insolvência em 24 meses ----------------------------------------------------------------------
def _insolvencia(porta: Porta, cnpj_formatado: str, dia: date) -> list[Feature]:
    filtros = {"cnpj": cnpj_formatado}
    insolvencia = fb._ler(porta, "insolvencia", dia, filtros)
    if insolvencia is None:
        return _sem_a_tabela(DA_INSOLVENCIA)
    ultimo = fb._ultimo_documento(insolvencia, fb._ler(porta, "eventos", dia, filtros))
    if ultimo is None:
        return _nao_observados(DA_INSOLVENCIA, fb.SEM_IPE)
    inicio = dia - timedelta(days=DIAS_DA_INSOLVENCIA)
    proprias = insolvencia[
        _entre(insolvencia["publico_em"], inicio, dia)
        & (insolvencia["rotulo"] != fb.EXPOSICAO_A_TERCEIRO)
    ].sort_values(["publico_em", "protocolo", "versao"])
    mais_nova = proprias.tail(1)
    ultima = (
        f"{mais_nova['rotulo'].iloc[0]} em {fb._dia(mais_nova['publico_em'].iloc[0]):%d/%m/%Y}"
        if not mais_nova.empty
        else fb.NENHUM
    )
    periodo = f"24 meses até {dia:%d/%m/%Y}"
    return [
        _sinal(DA_INSOLVENCIA[0], int(proprias["protocolo"].nunique()), periodo,
               fb._documentos(proprias, ultimo)),
        _sinal(DA_INSOLVENCIA[1], ultima, periodo, fb._documentos(mais_nova, ultimo)),
    ]  # fmt: skip


# --- entrega à CVM --------------------------------------------------------------------------------
def _atrasos(porta: Porta, cnpj_formatado: str, dia: date) -> Feature:
    chave = "atrasos_de_entrega_na_cvm"
    linhas = fb._ler(porta, "rotulos_atraso", dia, {"cnpj": cnpj_formatado})
    if linhas is None:
        return _sem_a_tabela([chave])[0]
    if linhas.empty:
        return _sinal(chave, None, "", [], SEM_ENTREGA)
    ultimas = linhas.sort_values(["referencia", "documento"]).tail(ENTREGAS_OLHADAS)
    documentos = [
        DocumentoUsado(
            f"CVM: {linha['documento']} de {fb._dia(linha['referencia']):%d/%m/%Y}",
            fb._dia(linha["publico_em"]),
        )
        for _, linha in ultimas.iterrows()
    ]
    periodo = f"últimas {len(ultimas)} entregues até {dia:%d/%m/%Y}"
    return _sinal(chave, int(_sim(ultimas["atrasou"]).sum()), periodo, documentos)


# --- juntando -------------------------------------------------------------------------------------
def sinais_da_ficha(porta: Porta, cnpj: str, dia: date) -> tuple[Feature, ...]:
    """Os sinais da ficha de um CNPJ (ordem do dicionário, `DA_FICHA`), com o que era público no dia.

    Empresário individual ou MEI (pelas `entidades` da rede): todos não observados (ADR 0075)."""
    normal = fb._cnpj(cnpj)
    raiz, formatado = normal[: cnpj_.TAMANHO_DA_RAIZ], cnpj_.formatar(normal)
    if fb._pessoa_natural(porta, raiz, dia):
        return tuple(_nao_observados(DA_FICHA, fb.COMO_PESSOA))
    sinais = [
        *_pgfn_por_situacao(porta, raiz, dia),
        _situacao_cadastral(porta, raiz, dia),
        *_das_listas(porta, raiz, dia),
        *(
            sinal
            for tabela in DO_ESTADO
            for sinal in _do_estado(porta, tabela, raiz, dia)
        ),
        *_fidc(porta, formatado, dia),
        *_rating(porta, formatado, dia),
        *_insolvencia(porta, formatado, dia),
        _atrasos(porta, formatado, dia),
    ]
    por_chave = {sinal.chave: sinal for sinal in sinais}
    return tuple(por_chave[chave] for chave in DA_FICHA)
