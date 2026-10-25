"""Features de crédito da base, pela porta, como eram num dia (B-30; protótipo C, parte 2).

Dívida ativa da União (PGFN), situação especial no CNPJ (Receita), insolvência da própria companhia
e eventos do IPE (CVM) e a inadimplência do setor da empresa no SCR (Banco Central, B-30b), lidos só pela porta (`base/porta`) com `como_era_em`: entra o que já era
público no dia. A PGFN e a Receita valem pelo último dia do mês em que o retrato foi visto (a porta
já lê assim); o IPE, pelo dia da entrega à CVM.

Não observado (nunca estimado): tabela que não está na base, retrato que ainda não existia,
empresário individual ou MEI na PGFN (ADR 0075: nada negativo sobre pessoa sai da base) e companhia
sem nenhum documento do IPE até o dia. A empresa fora de um retrato público tem zero (ou "nenhuma"):
o retrato inteiro é a observação. Um documento do IPE reapresentado depois do dia some do dia (a base
guarda só a versão mais nova nos `eventos`): a contagem pode ficar menor, nunca olha o futuro.

`pgfn_divida`, `cnpj_situacao_especial` e `insolvencia` não podem aparecer no app até o parecer
(`base/dossie.py`, `TABELAS_PROIBIDAS`): estas features são da pesquisa, sem tela. Nada aqui é nota,
score nem opinião de crédito (B-31).
"""

from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import date, timedelta

import pandas as pd

from base import cnpj as cnpj_
from base.porta import Porta
from src.banco.demonstracoes import DadosDaEmpresa
from src.credito.features import (
    Feature,
    FeaturesDeCredito,
    features_das_demonstracoes,
    nova_feature,
)
from src.rastro import DocumentoUsado
from src.relatorio_empresa import FONTE_DA_CVM

FONTE_DA_PGFN, FONTE_DA_RECEITA = "pgfn", "rfb-cnpj"
DEVEDOR_PRINCIPAL = "principal"
EXPOSICAO_A_TERCEIRO = "exposicao_a_terceiro"
FATO_RELEVANTE = "Fato relevante"  # o rótulo de `src/eventos.py`
TEMA_DO_RATING = "risco"
DIAS_DA_JANELA = 365
NENHUMA, NENHUM = "nenhuma", "nenhum"
SEM_A_TABELA = "A tabela `{tabela}` não está nesta base."
SEM_RETRATO = "Nenhum retrato da {fonte} era público no dia."
COMO_PESSOA = (
    "Empresário individual ou MEI: nada negativo sobre pessoa sai da base (ADR 0075)."
)
SEM_A_SECAO = (
    "A seção do CNAE da companhia como era no dia não foi informada: o CNAE por CNPJ com data ainda "
    "não está na porta (carga do CNPJ, fila 120)."
)
SEM_MES_DO_SCR = "Nenhuma data-base do SCR com carteira nesta seção era pública no dia."
CARTEIRA_NAO_POSITIVA = "Carteira ativa zerada na seção: a razão não tem sentido."
FONTE_DO_SCR = "bcb"
SEM_IPE = (
    "Nenhum documento do IPE da companhia era público no dia: ela não entregava à CVM."
)
DA_PGFN = (
    "divida_ativa_da_uniao",
    "divida_ativa_ajuizada",
    "inscricoes_em_divida_ativa",
)
DO_SCR = ("inadimplencia_do_setor_no_scr", "carteira_do_setor_no_scr")
DO_IPE = (
    "eventos_de_insolvencia",
    "ultimo_evento_de_insolvencia",
    "fatos_relevantes_12_meses",
    "ratings_12_meses",
)


def _dia(valor: object) -> date:
    return pd.Timestamp(valor).date()  # type: ignore[arg-type]


def _ler(porta: Porta, tabela: str, dia: date, filtros: dict) -> pd.DataFrame | None:
    """As linhas públicas no dia (None: a tabela não está nesta base)."""
    try:
        return porta.ler(tabela, como_era_em=dia, filtros=filtros)
    except KeyError:
        return None


def _retrato_mais_novo(
    porta: Porta, tabela: str, coluna: str, valor: str, dia: date
) -> tuple[object, date] | None:
    """(retrato, dia em que ficou público) do retrato mais novo público no dia, somado no DuckDB
    (a tabela inteira não vem para o Python); None se nenhum era."""
    por_retrato = porta.somar(tabela, [coluna, "publico_em"], valor, como_era_em=dia)
    if por_retrato.empty:
        return None
    retrato = max(por_retrato[coluna])
    publico = max(por_retrato.loc[por_retrato[coluna] == retrato, "publico_em"])
    return retrato, _dia(publico)


def _nao_observadas(
    chaves: Sequence[str],
    motivo: str,
    fonte: str,
    periodo: str = "",
    documentos: Sequence[DocumentoUsado] = (),
) -> list[Feature]:
    return [nova_feature(c, None, periodo, documentos, motivo, fonte) for c in chaves]


# --- PGFN -----------------------------------------------------------------------------------------
def _pgfn(porta: Porta, raiz: str, dia: date) -> list[Feature]:
    linhas = _ler(porta, "pgfn_divida", dia, {"cnpj_basico": raiz})
    if linhas is None:
        return _nao_observadas(
            DA_PGFN, SEM_A_TABELA.format(tabela="pgfn_divida"), FONTE_DA_PGFN
        )
    ultimo = _retrato_mais_novo(
        porta, "pgfn_divida", "data_do_retrato", "inscricoes", dia
    )
    if ultimo is None:
        return _nao_observadas(DA_PGFN, SEM_RETRATO.format(fonte="PGFN"), FONTE_DA_PGFN)
    retrato, publico = _dia(ultimo[0]), ultimo[1]
    periodo = f"retrato de {retrato:%d/%m/%Y}"
    documentos = [DocumentoUsado(f"PGFN: dívida ativa da União, {periodo}", publico)]
    if linhas["trata_como_pessoa"].fillna(False).astype(bool).any():
        return _nao_observadas(DA_PGFN, COMO_PESSOA, FONTE_DA_PGFN, periodo, documentos)
    do_retrato = linhas[linhas["data_do_retrato"].map(_dia) == retrato]
    principal = do_retrato[do_retrato["tipo_devedor"] == DEVEDOR_PRINCIPAL]
    ajuizado = principal["ajuizado"].fillna(False).astype(bool)
    valores = (
        float(principal["valor_consolidado"].sum()),
        float(principal.loc[ajuizado, "valor_consolidado"].sum()),
        int(principal["inscricoes"].sum()),
    )
    return [
        nova_feature(chave, valor, periodo, documentos, fonte=FONTE_DA_PGFN)
        for chave, valor in zip(DA_PGFN, valores, strict=True)
    ]


# --- Receita: situação especial -------------------------------------------------------------------
def _situacao_especial(porta: Porta, raiz: str, dia: date) -> Feature:
    chave = "situacao_especial_na_receita"
    linhas = _ler(porta, "cnpj_situacao_especial", dia, {"cnpj_basico": raiz})
    if linhas is None:
        motivo = SEM_A_TABELA.format(tabela="cnpj_situacao_especial")
        return nova_feature(chave, None, "", [], motivo, FONTE_DA_RECEITA)
    ultimo = _retrato_mais_novo(
        porta, "cnpj_situacao_especial", "mes_do_retrato", "matriz", dia
    )
    if ultimo is None:
        motivo = SEM_RETRATO.format(fonte="Receita")
        return nova_feature(chave, None, "", [], motivo, FONTE_DA_RECEITA)
    mes, publico = str(ultimo[0]), ultimo[1]
    periodo = f"retrato de {mes}"
    documentos = [
        DocumentoUsado(f"Receita: CNPJ com situação especial, {periodo}", publico)
    ]
    do_retrato = linhas[linhas["mes_do_retrato"].astype(str) == mes]
    if do_retrato.empty:
        return nova_feature(chave, NENHUMA, periodo, documentos, fonte=FONTE_DA_RECEITA)
    # a matriz primeiro; o rótulo vazio (espólio, por exemplo) fica com o texto da Receita
    linha = do_retrato.sort_values("matriz", ascending=False).iloc[0]
    valor = linha["rotulo"] or linha["situacao_especial"]
    return nova_feature(chave, str(valor), periodo, documentos, fonte=FONTE_DA_RECEITA)


# --- IPE: insolvência e eventos -------------------------------------------------------------------
def _documento(linha: pd.Series) -> DocumentoUsado:
    nome = f"IPE: {linha['rotulo']}, protocolo {linha['protocolo']}, versão {linha['versao']}"
    return DocumentoUsado(nome, _dia(linha["publico_em"]), str(linha["link"] or ""))


def _documentos(linhas: pd.DataFrame, ou: DocumentoUsado) -> list[DocumentoUsado]:
    """Os documentos usados; sem nenhum (zero), o último do IPE da companhia, que prova que ela
    entregava e dá o dia desde quando o zero vale."""
    return [_documento(linha) for _, linha in linhas.iterrows()] or [ou]


def _ultimo_documento(*tabelas: pd.DataFrame | None) -> DocumentoUsado | None:
    linhas = [t for t in tabelas if t is not None and not t.empty]
    if not linhas:
        return None
    todas = pd.concat(
        [t[["rotulo", "protocolo", "versao", "link", "publico_em"]] for t in linhas]
    )
    return _documento(todas.sort_values(["publico_em", "protocolo", "versao"]).iloc[-1])


def _insolvencia(
    linhas: pd.DataFrame, ultimo: DocumentoUsado, ate: str
) -> list[Feature]:
    proprias = linhas[linhas["rotulo"] != EXPOSICAO_A_TERCEIRO].sort_values(
        ["publico_em", "protocolo", "versao"]
    )
    mais_nova = proprias.tail(1)
    return [
        nova_feature(
            "eventos_de_insolvencia", int(proprias["protocolo"].nunique()), ate,
            _documentos(proprias, ultimo), fonte=FONTE_DA_CVM,
        ),
        nova_feature(
            "ultimo_evento_de_insolvencia",
            str(mais_nova["rotulo"].iloc[0]) if not mais_nova.empty else NENHUM, ate,
            _documentos(mais_nova, ultimo), fonte=FONTE_DA_CVM,
        ),
    ]  # fmt: skip


def _nos_12_meses(
    linhas: pd.DataFrame, dia: date, ultimo: DocumentoUsado
) -> list[Feature]:
    inicio = dia - timedelta(days=DIAS_DA_JANELA)
    janela = linhas[linhas["publico_em"].map(_dia) > inicio]
    periodo = f"12 meses até {dia:%d/%m/%Y}"
    filtros: dict[str, Callable[[pd.DataFrame], pd.Series]] = {
        "fatos_relevantes_12_meses": lambda t: t["rotulo"] == FATO_RELEVANTE,
        "ratings_12_meses": lambda t: t["tema"] == TEMA_DO_RATING,
    }
    features = []
    for chave, filtro in filtros.items():
        contados = janela[filtro(janela)]
        features.append(nova_feature(
            chave, len(contados), periodo, _documentos(contados, ultimo), fonte=FONTE_DA_CVM
        ))  # fmt: skip
    return features


def _ipe(porta: Porta, cnpj_formatado: str, dia: date) -> list[Feature]:
    filtros = {"cnpj": cnpj_formatado}
    insolvencia = _ler(porta, "insolvencia", dia, filtros)
    eventos = _ler(porta, "eventos", dia, filtros)
    ultimo = _ultimo_documento(insolvencia, eventos)
    if ultimo is None:
        faltam = [
            t
            for t, v in (("insolvencia", insolvencia), ("eventos", eventos))
            if v is None
        ]
        motivo = SEM_A_TABELA.format(tabela=faltam[0]) if len(faltam) == 2 else SEM_IPE
        return _nao_observadas(DO_IPE, motivo, FONTE_DA_CVM)
    ate = f"até {dia:%d/%m/%Y}"
    return [
        *(
            _insolvencia(insolvencia, ultimo, ate)
            if insolvencia is not None
            else _nao_observadas(
                DO_IPE[:2], SEM_A_TABELA.format(tabela="insolvencia"), FONTE_DA_CVM
            )
        ),
        *(
            _nos_12_meses(eventos, dia, ultimo)
            if eventos is not None
            else _nao_observadas(
                DO_IPE[2:], SEM_A_TABELA.format(tabela="eventos"), FONTE_DA_CVM
            )
        ),
    ]


# --- SCR: o setor da empresa -----------------------------------------------------------------------
def _somas_do_scr(
    porta: Porta, secao: str, dia: date, coluna: str
) -> dict[date, tuple[float, date]]:
    """data-base → (soma, dia em que ficou pública) das pessoas jurídicas da seção, só as públicas."""
    por_mes = porta.somar(
        "scr_credito",
        ["data_base", "publico_em"],
        coluna,
        filtros={"cliente": "PJ", "cnae_ocupacao": secao},
        como_era_em=dia,
    )
    return {
        _dia(linha["data_base"]): (float(linha[coluna]), _dia(linha["publico_em"]))
        for _, linha in por_mes.iterrows()
    }


def _scr(porta: Porta, secao: str | None, dia: date) -> list[Feature]:
    if secao is None:
        return _nao_observadas(DO_SCR, SEM_A_SECAO, FONTE_DO_SCR)
    try:
        ativas = _somas_do_scr(porta, secao, dia, "carteira_ativa")
    except KeyError:
        motivo = SEM_A_TABELA.format(tabela="scr_credito")
        return _nao_observadas(DO_SCR, motivo, FONTE_DO_SCR)
    if not ativas:
        return _nao_observadas(DO_SCR, SEM_MES_DO_SCR, FONTE_DO_SCR)
    data_base = max(ativas)
    ativa, publico = ativas[data_base]
    inadimplente = _somas_do_scr(porta, secao, dia, "carteira_inadimplencia")[
        data_base
    ][0]
    periodo = f"data-base de {data_base:%d/%m/%Y}"
    nome = f"Banco Central: SCR.data, pessoas jurídicas em «{secao}», {periodo}"
    documentos = [DocumentoUsado(nome, publico)]
    motivo = CARTEIRA_NAO_POSITIVA if ativa <= 0 else ""
    return [
        nova_feature(
            DO_SCR[0], None if motivo else inadimplente / ativa, periodo, documentos,
            motivo, FONTE_DO_SCR,
        ),
        nova_feature(DO_SCR[1], ativa, periodo, documentos, fonte=FONTE_DO_SCR),
    ]  # fmt: skip


# --- juntando -------------------------------------------------------------------------------------
def _cnpj(cnpj: str) -> str:
    normal = cnpj_.normalizar_cnpj(cnpj)
    if normal is None:
        raise ValueError(f"{cnpj!r} não é um CNPJ")
    return normal


def features_da_base(
    porta: Porta,
    cnpj: str,
    data_da_analise: date,
    secao_do_cnae: str | None = None,
) -> tuple[Feature, ...]:
    """As features da base de um CNPJ (ordem do dicionário), com o que era público no dia.

    `secao_do_cnae` é a seção do CNAE da companhia **como era no dia**, no nome do SCR
    (`base.cnae.secao_do_cnae`); sem ela, as features do SCR ficam não observadas: o CNAE por CNPJ
    com data ainda não está na porta."""
    normal = _cnpj(cnpj)
    raiz = normal[: cnpj_.TAMANHO_DA_RAIZ]
    return (
        *_pgfn(porta, raiz, data_da_analise),
        _situacao_especial(porta, raiz, data_da_analise),
        *_ipe(porta, cnpj_.formatar(normal), data_da_analise),
        *_scr(porta, secao_do_cnae, data_da_analise),
    )


def features_de_credito(
    dados: DadosDaEmpresa,
    porta: Porta,
    cnpj: str,
    data_da_analise: date,
    secao_do_cnae: str | None = None,
) -> FeaturesDeCredito:
    """Todas as features de uma companhia aberta: as das demonstrações e as da base."""
    normal = _cnpj(cnpj)
    das_demonstracoes = features_das_demonstracoes(dados, data_da_analise, normal)
    return replace(
        das_demonstracoes,
        features=das_demonstracoes.features
        + features_da_base(porta, normal, data_da_analise, secao_do_cnae),
    )
