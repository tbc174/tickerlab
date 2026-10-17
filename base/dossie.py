"""O dossiê da empresa: o que a base de ML diz de cada companhia, para o app (plano de 17/10/2026).

O "Relatório da empresa" do app (ADR 0032) ganha seções que vêm da base. Elas são calculadas toda noite
no servidor de casa (`scripts/montar_dossies.py`), uma ficha JSON por CNPJ, e só o assinante Pro as vê.
É o primeiro uso da base como produto (ADR 0076: o TickerLab é o primeiro cliente).

**Só entra o que pode ser mostrado a quem paga** (`pode_mostrar`):

- a tabela está no dicionário da base e **não guarda pessoa** (ADR 0075: nomes esperam a LGPD);
- a fonte é **vendável** (Emenda 1 da ADR 0008). "Só uso interno" pode entrar num modelo, mas mostrar o
  dado a quem assina é revendê-lo; "a confirmar" e "não comercial", nunca;
- não é uma tabela de crise ou de risco com o nome da empresa (insolvência, atraso, situação especial,
  dívida com a União: esperam o parecer, P-44), nem das assessorias de M&A (licença a confirmar).

Uma fonte que passar a ser vendável entra sozinha: basta a tabela estar numa seção. Para pôr uma série
nova de agência (as das séries 5 e 6 da base, quando chegarem), é uma linha em `SERIES_DAS_AGENCIAS`.

Por último, `conferir_sem_pessoas` passa pela ficha inteira: nenhum CPF, nenhum nome de entidade tratada
como pessoa e nenhuma coluna de pessoa. Os textos livres (o assunto de um fato relevante) só são
conferidos contra os nomes que a rede conhece: é um limite, escrito na seção.

Funções puras: as tabelas chegam já só com a empresa da ficha; ler e gravar fica no script.
"""

import json
import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

import pandas as pd

from base.dicionario import TABELAS
from src.banco.coletas import (
    VENDAVEL_COM_ATRIBUICAO,
    VENDAVEL_ODBL,
    licenca_da_fonte,
    revenda_da_fonte,
)

VERSAO_DO_ESQUEMA = 1  # muda quando o app precisa ler a ficha de outro jeito
REVENDAS_QUE_PODEM_SER_MOSTRADAS = frozenset({VENDAVEL_ODBL, VENDAVEL_COM_ATRIBUICAO})
# vendáveis pela licença, mas fora do app até o parecer (crise com o nome da empresa, P-44)
TABELAS_PROIBIDAS = frozenset(
    {"insolvencia", "rotulos_atraso", "cnpj_situacao_especial", "pgfn_divida"}
)
LINHAS_NAS_LISTAS = (
    20  # últimas ofertas, últimos negócios: o resto fica na contagem por ano
)
MESES_DOS_FUNDOS = 24
ANOS_NAS_SERIES = 10
AUDITOR_PESSOA = "Auditor pessoa física (nome não mostrado)"
DIGITOS_DO_CNPJ = 14
SOMA_DO_ANO, ULTIMO_MES = "soma do ano", "último mês do ano"
CPF = re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b")
COLUNAS_DE_PESSOA = frozenset(
    {"cpf", "administrador", "conselheiro", "diretor", "nome_pessoa", "socio"}
)
# palavras do assunto que indicam compra, venda, fusão ou reorganização (escolha editorial, sem acento)
PALAVRAS_DE_NEGOCIO = re.compile(
    r"aquisi|incorpora|fusao|cisao|aliena|desinvestimento|combinacao de negocio"
    r"|venda de (?:participa|ativo|controle|acoes)|compra de (?:participa|ativo|controle|acoes)"
    r"|oferta publica de aquisi|\bopa\b|reorganizacao societaria|joint venture"
    r"|transferencia de controle|memorando de entendimento"
)
ROTULOS_DE_NEGOCIO = ("Fato relevante", "Comunicado ao mercado")


class TabelaProibidaError(ValueError):
    """Uma seção do dossiê usaria uma tabela que não pode ser mostrada a quem assina."""


class PessoaNaFichaError(ValueError):
    """A ficha montada tem CPF, nome de pessoa ou coluna de pessoa: não sai do servidor de casa."""


# --- a regra de mostrar --------------------------------------------------------------------------


def pode_mostrar(nome_da_tabela: str) -> bool:
    """A tabela pode aparecer no app para quem assina? (vendável, sem pessoa e fora da lista proibida)"""
    tabela = TABELAS.get(nome_da_tabela)
    if tabela is None or tabela.pessoa or nome_da_tabela in TABELAS_PROIBIDAS:
        return False
    return revenda_da_fonte(tabela.familia_da_fonte) in REVENDAS_QUE_PODEM_SER_MOSTRADAS


def exigir_que_pode_mostrar(tabelas: Iterable[str]) -> None:
    """Levanta `TabelaProibidaError` com as tabelas que não podem ser mostradas."""
    proibidas = [nome for nome in tabelas if not pode_mostrar(nome)]
    if proibidas:
        raise TabelaProibidaError(f"não podem ser mostradas: {', '.join(proibidas)}")


def fontes_das_tabelas(tabelas: Iterable[str]) -> list[str]:
    """As licenças das fontes das tabelas, sem repetir: vão na seção (a atribuição que a licença pede)."""
    return sorted(
        {licenca_da_fonte(TABELAS[nome].familia_da_fonte) for nome in tabelas}
    )


@dataclass(frozen=True)
class SerieDaAgencia:
    """Uma medida de agência por entidade e mês, ligada à companhia pela tabela empresa ↔ série (B13)."""

    nome: str  # chave da série na ficha
    fonte_b13: str  # a `fonte` em `empresa_serie`
    tabela: str  # no dicionário da base
    pasta: str  # dentro da base
    chave: str  # a coluna que a B13 usa como `chave`
    valor: str
    modo: str  # SOMA_DO_ANO ou ULTIMO_MES
    medida: str  # o que o número é, escrito para a tela
    unidade: str
    filtros: tuple[tuple[str, str], ...] = ()
    pular_arquivos: str = (
        ""  # parte do nome dos Parquet que repetem o dado em outro recorte
    )
    chave_em_digitos: bool = False  # CNPJ: casa formatado ou não


SERIES_DAS_AGENCIAS = (
    SerieDaAgencia(
        "aneel_consumidores",
        "aneel-samp",
        "aneel_samp",
        "setoriais/aneel",
        "cnpj",
        "valor",
        ULTIMO_MES,
        "Consumidores atendidos pelas distribuidoras (ANEEL)",
        "consumidores",
        (
            ("detalhe_do_mercado", "Número de consumidores"),
            ("tipo_de_mercado", "Regular"),
        ),
        chave_em_digitos=True,
    ),
    *(
        SerieDaAgencia(
            f"anatel_{servico}",
            "anatel-acessos",
            "anatel_acessos",
            "setoriais/anatel",
            "cnpj",
            "acessos",
            ULTIMO_MES,
            f"Acessos em serviço, {texto} (Anatel)",
            "acessos",
            (("servico", servico),),
            pular_arquivos="Tecnologia",
            chave_em_digitos=True,
        )
        for servico, texto in (
            ("telefonia_movel", "telefonia móvel"),
            ("banda_larga_fixa", "banda larga fixa"),
            ("tv_por_assinatura", "TV por assinatura"),
        )
    ),
    SerieDaAgencia(
        "ans_beneficiarios",
        "ans-beneficiarios",
        "ans_beneficiarios",
        "setoriais/ans",
        "cd_operadora",
        "beneficiarios",
        ULTIMO_MES,
        "Beneficiários de planos de saúde (ANS)",
        "beneficiários",
    ),
    SerieDaAgencia(
        "anac_passageiros",
        "anac-estatistico",
        "anac_estatistico",
        "setoriais/anac",
        "empresa_sigla",
        "passageiros_pagos",
        SOMA_DO_ANO,
        "Passageiros pagos transportados (ANAC)",
        "passageiros",
    ),
    SerieDaAgencia(
        "susep_premio_ganho",
        "susep-ses",
        "susep_seguros",
        "setoriais/susep",
        "coenti",
        "premio_ganho",
        SOMA_DO_ANO,
        "Prêmio ganho das seguradoras (SUSEP)",
        "R$",
    ),
    SerieDaAgencia(
        "anp_vendas",
        "anp-vendas-distribuidora",
        "anp_vendas",
        "setoriais/anp",
        "agente",
        "quantidade",
        SOMA_DO_ANO,
        "Vendas das distribuidoras de combustíveis líquidos (ANP)",
        "mil m³",
        (("unidade", "mil m³"),),
    ),
)


@dataclass(frozen=True)
class SecaoDaBase:
    chave: str
    titulo: str
    tabelas: tuple[str, ...]


SECOES = (
    SecaoDaBase(
        "auditor_e_controladas",
        "Auditor e controladas",
        (
            "auditores",
            "trocas_de_auditor",
            "controladas",
            "ligacoes",
            "entidades",
            "identificadores",
        ),
    ),
    SecaoDaBase(
        "ofertas_e_fundos",
        "Ofertas e fundos",
        ("ofertas_resolucao_160", "ofertas_antigas", "painel_dos_fundos"),
    ),
    SecaoDaBase(
        "setor_regulado",
        "Setor regulado",
        ("empresa_serie", *dict.fromkeys(s.tabela for s in SERIES_DAS_AGENCIAS)),
    ),
    SecaoDaBase("negocios", "Negócios (M&A pela CVM)", ("eventos",)),
)
_SECAO_POR_CHAVE = {secao.chave: secao for secao in SECOES}

LIMITES = {
    "auditor_e_controladas": (
        "Controladas e coligadas vêm do Formulário de Referência (FRE) mais recente entregue à CVM; "
        "a controladora aparece só quando ela também entrega o FRE. Auditor pessoa física não tem o "
        "nome mostrado."
    ),
    "ofertas_e_fundos": (
        "Ofertas registradas na CVM (Resolução 160 e as anteriores), pelo valor registrado, não o "
        "colocado. Fundos: a posição comprada somada das carteiras entregues à CVM (CDA), que saem "
        "com até 90 dias de atraso."
    ),
    "setor_regulado": (
        "Soma das entidades ligadas à companhia pela tabela empresa ↔ série da base (própria ou "
        "controlada, pelo FRE). A participação é sobre o total da agência no ano."
    ),
    "negocios": (
        "Fatos relevantes e comunicados cujo assunto fala de compra, venda, fusão, incorporação ou "
        "reorganização. A escolha é pelas palavras do assunto: pode deixar escapar ou incluir algum. "
        "O assunto é escrito pela empresa."
    ),
}


# --- peças comuns ---------------------------------------------------------------------------------


def normalizar_nome(texto: str) -> str:
    """Sem acento, em minúsculas e com um espaço só: para comparar nomes."""
    sem_acento = unicodedata.normalize("NFD", str(texto))
    sem_acento = "".join(c for c in sem_acento if unicodedata.category(c) != "Mn")
    return " ".join(sem_acento.casefold().split())


def digitos(valores: pd.Series) -> pd.Series:
    """Só os dígitos de cada valor (CNPJ formatado ou não)."""
    return valores.astype(str).str.replace(r"\D", "", regex=True)


def _data(valor: object) -> str | None:
    return None if pd.isna(valor) else pd.Timestamp(valor).strftime("%Y-%m-%d")


def _registros(tabela: pd.DataFrame) -> list[dict[str, Any]]:
    """As linhas em tipos simples (datas ISO, faltando → None), como vão no JSON."""
    copia = tabela.copy()
    for coluna in copia.columns:
        if pd.api.types.is_datetime64_any_dtype(copia[coluna]):
            copia[coluna] = copia[coluna].dt.strftime("%Y-%m-%d")
    return json.loads(copia.to_json(orient="records", force_ascii=False))


def _item(
    chave: str, nome: str, valor: str | float | None, unidade: str, base: str | None
) -> dict[str, Any]:
    return {
        "chave": chave,
        "nome": nome,
        "valor": valor,
        "unidade": unidade,
        "base": base,
    }


def _secao(
    chave: str,
    itens: list[dict[str, Any]],
    tabelas: Mapping[str, pd.DataFrame],
    paragrafos: list[str] | None = None,
) -> dict[str, Any]:
    registro = _SECAO_POR_CHAVE[chave]
    return {
        "chave": chave,
        "titulo": registro.titulo,
        "itens": itens,
        "tabelas": {nome: _registros(t) for nome, t in tabelas.items() if not t.empty},
        "paragrafos": [*(paragrafos or []), LIMITES[chave]],
        "fontes": fontes_das_tabelas(registro.tabelas),
    }


def _mais_recente(tabela: pd.DataFrame) -> pd.DataFrame:
    """As linhas do documento mais recente (maior referência e, nela, a maior versão)."""
    if tabela.empty:
        return tabela
    ultima = tabela["referencia"].max()
    do_ultimo = tabela[tabela["referencia"] == ultima]
    return do_ultimo[do_ultimo["versao"] == do_ultimo["versao"].max()]


# --- auditor e controladas -----------------------------------------------------------------------


def _e_pessoa(nome: object, pessoas: set[str]) -> bool:
    return normalizar_nome(nome) in pessoas


def _nome_do_auditor(linha: pd.Series, pessoas: set[str]) -> str:
    """O nome da firma; o de um auditor pessoa física não aparece (sem CNPJ de firma ou nome de pessoa)."""
    cnpj = re.sub(r"\D", "", str(linha.get("auditor_cnpj") or ""))
    firma = len(cnpj) == DIGITOS_DO_CNPJ or str(linha.get("auditor_id", "")).startswith(
        "rede:"
    )
    if not firma or _e_pessoa(linha["auditor"], pessoas):
        return AUDITOR_PESSOA
    return str(linha["auditor"])


def _itens_do_auditor(
    auditores: pd.DataFrame, pessoas: set[str]
) -> list[dict[str, Any]]:
    if auditores.empty:
        return []
    em_curso = _mais_recente(auditores)
    em_curso = em_curso[em_curso["fim"].isna()].sort_values("inicio")
    if em_curso.empty:
        return []
    atual = em_curso.iloc[-1]
    base = _data(atual["referencia"])
    return [
        _item(
            "auditor_atual",
            "Auditor atual",
            _nome_do_auditor(atual, pessoas),
            "texto",
            base,
        ),
        _item("auditor_desde", "Auditor desde", _data(atual["inicio"]), "data", base),
    ]


def _trocas_sem_pessoas(trocas: pd.DataFrame, pessoas: set[str]) -> pd.DataFrame:
    if trocas.empty:
        return trocas
    tabela = trocas[["efetiva_em", "anterior", "novo", "anos_com_o_anterior"]].copy()
    for coluna in ("anterior", "novo"):
        tabela[coluna] = tabela[coluna].map(
            lambda nome: AUDITOR_PESSOA if _e_pessoa(nome, pessoas) else nome
        )
    return tabela.sort_values("efetiva_em", ascending=False)


def _controladas_do_ultimo_fre(
    controladas: pd.DataFrame,
) -> tuple[pd.DataFrame, str | None]:
    ultimas = _mais_recente(controladas)
    if ultimas.empty:
        return ultimas, None
    tabela = ultimas[["razao_social", "tipo", "participacao"]].sort_values(
        "participacao", ascending=False
    )
    return tabela, _data(ultimas["referencia"].iloc[0])


def secao_auditor_e_controladas(
    auditores: pd.DataFrame,
    trocas: pd.DataFrame,
    controladas: pd.DataFrame,
    controladoras_da_empresa: pd.DataFrame,
    pessoas: set[str],
) -> dict[str, Any] | None:
    """Quem audita, as trocas de auditor, as controladas e coligadas e quem controla (None: nada)."""
    itens = _itens_do_auditor(auditores, pessoas)
    tabela_de_controladas, base = _controladas_do_ultimo_fre(controladas)
    if not tabela_de_controladas.empty:
        tipos = tabela_de_controladas["tipo"].value_counts()
        itens += [
            _item(
                "controladas",
                "Controladas",
                int(tipos.get("controlada", 0)),
                "empresas",
                base,
            ),
            _item(
                "coligadas",
                "Coligadas",
                int(tipos.get("coligada", 0)),
                "empresas",
                base,
            ),
        ]
    tabelas = {
        "trocas_de_auditor": _trocas_sem_pessoas(trocas, pessoas),
        "controladas": tabela_de_controladas,
        "controladoras": controladoras_da_empresa.drop(columns="cnpj", errors="ignore"),
    }
    if not itens and all(t.empty for t in tabelas.values()):
        return None
    return _secao("auditor_e_controladas", itens, tabelas)


def controladoras(
    ligacoes: pd.DataFrame, entidades: pd.DataFrame, identificadores: pd.DataFrame
) -> pd.DataFrame:
    """Quem controla cada companhia hoje pela rede (FRE da controladora): cnpj, controladora, participação.

    Só ligações vigentes; nenhuma entidade tratada como pessoa. Sem datas de fim: o `ate` da rede ainda
    pode olhar o futuro (achado na Ultrapar), e aqui só importa a situação de hoje.
    """
    cnpjs = identificadores[
        (identificadores["sistema"] == "cnpj") & identificadores["ate"].isna()
    ][["id_entidade", "valor"]].rename(columns={"id_entidade": "de", "valor": "cnpj"})
    vigentes = ligacoes[
        (ligacoes["tipo"] == "controlada_de")
        & (ligacoes["situacao"] == "vigente")
        & (ligacoes["fonte"] == "cvm-fre")
    ]
    nomes = entidades[~entidades["trata_como_pessoa"].fillna(True).astype(bool)][
        ["id_entidade", "nome"]
    ].rename(columns={"id_entidade": "para", "nome": "controladora"})
    tabela = vigentes.merge(cnpjs, on="de").merge(nomes, on="para")
    return tabela[["cnpj", "controladora", "participacao"]].reset_index(drop=True)


# --- ofertas e fundos ----------------------------------------------------------------------------


def _numero(valores: pd.Series) -> pd.Series:
    return pd.to_numeric(valores, errors="coerce")


def _ofertas(ofertas_160: pd.DataFrame, ofertas_antigas: pd.DataFrame) -> pd.DataFrame:
    """As ofertas das duas tabelas da CVM numa só, da mais nova para a mais velha."""
    partes = []
    if not ofertas_160.empty:
        partes.append(
            pd.DataFrame(
                {
                    "data": ofertas_160["data_registro"].fillna(
                        ofertas_160["data_requerimento"]
                    ),
                    "regime": "Res. 160",
                    "valor_mobiliario": ofertas_160["valor_mobiliario"],
                    "tipo_oferta": ofertas_160["tipo_oferta"],
                    "valor_total": _numero(ofertas_160["valor_total_registrado"]),
                    "situacao": ofertas_160["status_requerimento"],
                }
            )
        )
    if not ofertas_antigas.empty:
        partes.append(
            pd.DataFrame(
                {
                    "data": ofertas_antigas["data_registro_oferta"].fillna(
                        ofertas_antigas["data_protocolo"]
                    ),
                    "regime": "anterior à Res. 160",
                    "valor_mobiliario": ofertas_antigas["tipo_ativo"],
                    "tipo_oferta": ofertas_antigas["tipo_oferta"],
                    "valor_total": _numero(ofertas_antigas["valor_total"]),
                    "situacao": None,
                }
            )
        )
    if not partes:
        return pd.DataFrame()
    juntas = pd.concat(partes, ignore_index=True)
    juntas["data"] = pd.to_datetime(juntas["data"])
    return juntas.sort_values("data", ascending=False, ignore_index=True)


def _ofertas_por_ano(ofertas: pd.DataFrame) -> pd.DataFrame:
    if ofertas.empty:
        return ofertas
    por_ano = ofertas.groupby(ofertas["data"].dt.year.rename("ano")).agg(
        ofertas=("regime", "size"), valor_total=("valor_total", "sum")
    )
    return (
        por_ano.reset_index().sort_values("ano", ascending=False).head(ANOS_NAS_SERIES)
    )


def _fundos(painel: pd.DataFrame) -> tuple[list[dict[str, Any]], pd.DataFrame]:
    """Quantos fundos têm a ação e quanto, no último mês, e a série dos últimos meses."""
    if painel.empty:
        return [], painel
    comprado = painel[painel["tipo"] == "comprado"].sort_values("competencia")
    if comprado.empty:
        return [], comprado
    ultimo = comprado.iloc[-1]
    base = _data(ultimo["competencia"])
    itens = [
        _item(
            "fundos_com_a_acao",
            "Fundos com a empresa na carteira",
            int(ultimo["fundos"]),
            "fundos",
            base,
        ),
        _item(
            "valor_nos_fundos",
            "Valor nas carteiras dos fundos",
            float(ultimo["valor"]),
            "R$",
            base,
        ),
    ]
    serie = comprado[["competencia", "fundos", "valor"]].tail(MESES_DOS_FUNDOS)
    return itens, serie


def secao_ofertas_e_fundos(
    ofertas_160: pd.DataFrame, ofertas_antigas: pd.DataFrame, painel: pd.DataFrame
) -> dict[str, Any] | None:
    """As ofertas registradas na CVM e os fundos que têm a empresa na carteira (None: nada)."""
    ofertas = _ofertas(ofertas_160, ofertas_antigas)
    itens, fundos_por_mes = _fundos(painel)
    if ofertas.empty and not itens:
        return None
    if not ofertas.empty:
        itens.insert(
            0,
            _item(
                "ofertas",
                "Ofertas registradas na CVM",
                len(ofertas),
                "ofertas",
                _data(ofertas["data"].max()),
            ),
        )
    tabelas = {
        "ofertas": ofertas.head(LINHAS_NAS_LISTAS),
        "ofertas_por_ano": _ofertas_por_ano(ofertas),
        "fundos_por_mes": fundos_por_mes,
    }
    return _secao("ofertas_e_fundos", itens, tabelas)


# --- setor regulado ------------------------------------------------------------------------------


def serie_anual(tabela: pd.DataFrame, modo: str) -> pd.DataFrame:
    """De (competencia, chave, valor) por mês para (ano, chave, valor) por ano.

    `SOMA_DO_ANO` soma os meses (passageiros, prêmios); `ULTIMO_MES` fica com o último mês que a fonte
    tem em cada ano (consumidores, acessos: um estoque, que não se soma).
    """
    ano = tabela["competencia"].dt.year
    if modo == ULTIMO_MES:
        ultimo = tabela.groupby(ano)["competencia"].transform("max")
        tabela, ano = (
            tabela[tabela["competencia"] == ultimo],
            ano[tabela["competencia"] == ultimo],
        )
    somada = tabela.groupby([ano.rename("ano"), "chave"])["valor"].sum()
    return somada.reset_index()


def _chaves(ligacoes: pd.DataFrame, serie: SerieDaAgencia) -> set[str]:
    principais = ligacoes[
        (ligacoes["fonte"] == serie.fonte_b13) & ligacoes["principal"]
    ]
    valores = principais["chave"].astype(str).str.strip()
    return set(digitos(valores) if serie.chave_em_digitos else valores)


def _participacao_por_ano(dados: pd.DataFrame, chaves: set[str]) -> pd.DataFrame:
    dados = dados.assign(chave=dados["chave"].astype(str).str.strip())
    total = dados.groupby("ano")["valor"].sum()
    da_empresa = dados[dados["chave"].isin(chaves)].groupby("ano")["valor"].sum()
    tabela = pd.DataFrame({"valor": da_empresa, "participacao": da_empresa / total})
    return (
        tabela.reset_index().sort_values("ano", ascending=False).head(ANOS_NAS_SERIES)
    )


def _entidades_ligadas(ligacoes: pd.DataFrame) -> pd.DataFrame:
    principais = ligacoes[ligacoes["principal"]]
    return principais[["fonte", "nome", "via", "desde"]].sort_values(["fonte", "nome"])


def secao_setor_regulado(
    ligacoes_b13: pd.DataFrame, series: Mapping[str, pd.DataFrame]
) -> dict[str, Any] | None:
    """Os números da agência que regula a empresa, somadas as entidades dela (None: sem agência).

    `ligacoes_b13` são as linhas de `empresa_serie` da companhia; `series`, por `SerieDaAgencia.nome`,
    (ano, chave, valor) de todo o mercado, para a participação.
    """
    if ligacoes_b13.empty:
        return None
    itens, tabelas = [], {}
    for serie in SERIES_DAS_AGENCIAS:
        chaves = _chaves(ligacoes_b13, serie)
        dados = series.get(serie.nome)
        if not chaves or dados is None or dados.empty:
            continue
        tabela = _participacao_por_ano(dados, chaves)
        if tabela.empty:
            continue
        tabelas[serie.nome] = tabela
        ultimo = tabela.iloc[0]
        base = str(int(ultimo["ano"]))
        itens.append(
            _item(serie.nome, serie.medida, float(ultimo["valor"]), serie.unidade, base)
        )
    if not tabelas:
        return None
    tabelas["entidades_ligadas"] = _entidades_ligadas(ligacoes_b13)
    return _secao("setor_regulado", itens, tabelas)


# --- negócios ------------------------------------------------------------------------------------


def secao_negocios(eventos: pd.DataFrame) -> dict[str, Any] | None:
    """Fatos relevantes e comunicados de compra, venda, fusão ou reorganização (None: nenhum)."""
    if eventos.empty:
        return None
    assunto = eventos["assunto"].fillna("").map(normalizar_nome)
    negocios = eventos[
        eventos["rotulo"].isin(ROTULOS_DE_NEGOCIO)
        & assunto.str.contains(PALAVRAS_DE_NEGOCIO)
    ].sort_values("publicado_em", ascending=False)
    if negocios.empty:
        return None
    por_ano = (
        negocios.groupby(negocios["publicado_em"].dt.year.rename("ano"))
        .size()
        .rename("documentos")
        .reset_index()
        .sort_values("ano", ascending=False)
        .head(ANOS_NAS_SERIES)
    )
    base = _data(negocios["publicado_em"].iloc[0])
    itens = [
        _item(
            "negocios",
            "Documentos de negócios na CVM",
            len(negocios),
            "documentos",
            base,
        )
    ]
    tabelas = {
        "negocios": negocios[["publicado_em", "rotulo", "assunto", "link"]].head(
            LINHAS_NAS_LISTAS
        ),
        "negocios_por_ano": por_ano,
    }
    return _secao("negocios", itens, tabelas)


# --- a ficha e o filtro de pessoas ---------------------------------------------------------------


def montar_ficha(
    cnpj: str, empresa: str, secoes: Iterable[dict[str, Any] | None], gerado_em: str
) -> dict[str, Any]:
    """A ficha de uma companhia: o esquema, quem é e as seções que existem, na ordem de `SECOES`."""
    return {
        "versao_do_esquema": VERSAO_DO_ESQUEMA,
        "cnpj": cnpj,
        "empresa": empresa,
        "gerado_em": gerado_em,
        "secoes": [secao for secao in secoes if secao is not None],
    }


def _textos_e_chaves(valor: object) -> Iterable[tuple[str, str]]:
    """Cada texto da ficha, com o tipo ("texto" ou "coluna"), percorrendo listas e dicionários."""
    if isinstance(valor, dict):
        for chave, dentro in valor.items():
            yield "coluna", str(chave)
            yield from _textos_e_chaves(dentro)
    elif isinstance(valor, list):
        for dentro in valor:
            yield from _textos_e_chaves(dentro)
    elif isinstance(valor, str):
        yield "texto", valor


def conferir_sem_pessoas(ficha: Mapping[str, Any], pessoas: set[str]) -> None:
    """Levanta `PessoaNaFichaError` se a ficha tem CPF, nome de pessoa (já normalizado) ou coluna de pessoa."""
    for tipo, texto in _textos_e_chaves(ficha):
        if tipo == "coluna":
            if texto in COLUNAS_DE_PESSOA:
                raise PessoaNaFichaError(f"coluna de pessoa na ficha: {texto}")
        elif CPF.search(texto):
            raise PessoaNaFichaError("CPF na ficha")
        elif normalizar_nome(texto) in pessoas:
            raise PessoaNaFichaError("nome de pessoa na ficha")
