"""Financiamentos por CNPJ (linha 469 da fila; TickerLab Crédito e Ficha Clara): o histórico de
contratações reembolsáveis do BNDES (operações não automáticas) e da Finep (crédito direto e
descentralizado), numa tabela só, `financiamentos`, com um Parquet por banco.

É **histórico de contratações**, nunca saldo nem dívida atual: o que a fonte divulga é o valor contratado
e o desembolsado (o "Valor Pago" da Finep é desembolso, não quitação). Nada se soma (o mesmo contrato do
BNDES tem vários subcréditos, e duas fontes nunca se somam); o vazio fica nulo, nunca zero; e cada linha
diz quem emprestou e com que papel (`financiador`, `agente_papel`).

- **Situação como a fonte escreve** (`situacao`) e uma classe para separar (`situacao_classe`): o
  ENCERRADO da Finep é o fechamento técnico do projeto (`encerrado_tecnico`), não quitação; RESCINDIDO
  não é cancelado; o que a tabela não conhece fica `nao_classificado`, nunca no chute.
- **Identidade estável** (`id_na_fonte`, nunca o número da linha): no BNDES, o contrato, um resumo dos
  campos descritivos (os que não mudam com o tempo) e a ordem dentro do grupo pelo valor contratado; na
  Finep direta, o contrato; na descentralizada, o convênio do agente, o CNPJ e a data. Limite: dois
  subcréditos iguais em tudo trocam de ordem sem que se perceba (são iguais), e um subcrédito novo de
  valor menor no mesmo grupo empurra a ordem dos outros.
- **Só pessoa jurídica:** CNPJ inteiro de dígito certo; nome do cliente, descrição, título e resumo
  nunca entram (a coleta da Finep nem os guarda). Empresário individual e MEI ficam com
  `trata_como_pessoa` (ADR 0075).
- **Sem olhar o futuro** (`disponivel_em`): o dia do arquivo em que a linha foi vista, também no
  primeiro (nenhuma das duas fontes diz quando publicou cada linha).

Lê os arquivos que o arquivista já guardou (não baixa nada): o CSV das operações não automáticas da
fonte `bndes-operacoes` (#622) e o CSV que a coleta `finep-contratacao` grava da planilha
(`base/arquivo/finep.py`). Fora por enquanto: as indiretas automáticas e a exportação do BNDES, a aba de
condições da Finep e todo apoio não reembolsável.
"""

import gzip
import hashlib
from collections.abc import Callable, Collection, Iterable, Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import IO

import numpy as np
import pandas as pd
import pyarrow as pa
import sqlalchemy as sa

from base import cnpj as cnpjs
from base import retratos as motor
from base.parquet import LINHAGEM, gravar_se_mudou, origens_gravadas
from base.pgfn import pessoas_pela_receita
from src.versao_do_codigo import versao_do_codigo

TABELA = "financiamentos"
FONTE_DO_BNDES = "bndes-operacoes"
FONTE_DA_FINEP = "finep-contratacao"
ARQUIVO_DO_BNDES = "operacoes-financiamento-operacoes-nao-automaticas.csv"
JA_MONTADO = {"ja_montado": 1}  # no resumo: nenhum arquivo novo desde a última montagem
SEPARADOR = ";"  # a coleta grava todo CSV com ";"
CNPJ_DO_BNDES = "33657248000189"
CNPJ_DA_FINEP = "33749086000109"
CENTAVOS = Decimal("0.01")
CASAS_DOS_JUROS = Decimal("0.0001")
TAMANHO_DO_RESUMO = (
    10  # caracteres do hash dos campos descritivos no `id_na_fonte` do BNDES
)
TIPO_DO_DINHEIRO = pa.decimal128(18, 2)
TIPO_DOS_JUROS = pa.decimal128(9, 4)

_CARIMBOS = ["consta", "trata_como_pessoa", "visto_em", "disponivel_em"]
DINHEIRO = [
    "valor_contratado",
    "valor_desembolsado",
    "contrapartida",
    "outros_recursos",
]
PRAZOS = ["carencia_meses", "amortizacao_meses"]
COLUNAS = [
    "id_na_fonte", "fonte", "modalidade", "cnpj", "cnpj_basico", "uf", "contrato",
    "convenio_do_agente", "contratado_em", *DINHEIRO, "financiador", "agente_papel",
    "cnpj_do_financiador", "forma_de_apoio", "cnpj_do_executor", "uf_do_projeto", "produto",
    "instrumento", "fonte_de_recurso", "custo_financeiro", "juros", *PRAZOS, "inovacao", "porte",
    "natureza", "subsetor_cnae", "tipo_de_garantia", "situacao", "situacao_classe", *_CARIMBOS,
]  # fmt: skip
_LIDAS = [c for c in COLUNAS if c not in _CARIMBOS]
# as que contam para saber se o registro mudou de um retrato para o outro
VALORES = [c for c in _LIDAS if c != "id_na_fonte"] + ["consta"]
ORDEM = ["id_na_fonte", "visto_em"]

# BNDES: o nosso nome → a coluna do CSV (operações não automáticas, conferido em 04/11/2026)
_BNDES = {
    "cnpj": "cnpj",
    "uf": "uf",
    "contrato": "numero_do_contrato",
    "contratado_em": "data_da_contratacao",
    "valor_contratado": "valor_contratado_reais",
    "valor_desembolsado": "valor_desembolsado_reais",
    "fonte_de_recurso": "fonte_de_recurso_desembolsos",
    "custo_financeiro": "custo_financeiro",
    "juros": "juros",
    "carencia_meses": "prazo_carencia_meses",
    "amortizacao_meses": "prazo_amortizacao_meses",
    "modalidade_de_apoio": "modalidade_de_apoio",
    "forma_de_apoio": "forma_de_apoio",
    "produto": "produto",
    "instrumento": "instrumento_financeiro",
    "inovacao": "inovacao",
    "subsetor_cnae": "subsetor_cnae_codigo",
    "porte": "porte_do_cliente",
    "natureza": "natureza_do_cliente",
    "credenciada": "instituicao_financeira_credenciada",
    "cnpj_da_credenciada": "cnpj_da_instituicao_financeira_credenciada",
    "tipo_de_garantia": "tipo_de_garantia",
    "situacao": "situacao_do_contrato",
}
# os campos que descrevem o subcrédito e não mudam com o tempo (o desembolso e a situação mudam)
_DESCRITIVOS_DO_BNDES = [
    "cnpj", "contratado_em", "produto", "instrumento", "fonte_de_recurso", "custo_financeiro",
    "juros", "carencia_meses", "amortizacao_meses", "subsetor_cnae", "forma_de_apoio",
    "cnpj_da_credenciada",
]  # fmt: skip
_TEXTOS_DO_BNDES = [
    "uf", "forma_de_apoio", "produto", "instrumento", "fonte_de_recurso", "custo_financeiro",
    "inovacao", "porte", "natureza", "subsetor_cnae", "tipo_de_garantia",
]  # fmt: skip
REEMBOLSAVEL = (
    "REEMBOLSAVEL"  # sem acento nem espaço, como `motor.nome_da_coluna` deixa
)
DIRETA = "DIRETA"
SITUACOES_DO_BNDES = {"LIQUIDADO": "liquidado", "ATIVO": "ativo"}

# Finep: as colunas do CSV da coleta (`base/arquivo/finep.py`), por aba
_DIRETO = {
    "contrato": "Contrato",
    "contratado_em": "Data Assinatura",
    "cnpj": "CNPJ Proponente",
    "uf": "UF Proponente",
    "cnpj_do_executor": "CNPJ Executor",
    "uf_do_projeto": "UF Projeto",
    "valor_contratado": "Valor Finep",
    "contrapartida": "Contrapartida Financeira",
    "valor_desembolsado": "Valor Pago",
    "situacao": "Status",
}
_DESCENTRALIZADO = {
    "contratado_em": "Data Assinatura",
    "convenio_do_agente": "Contrato Finep Agente",
    "cnpj": "CNPJ Beneficiário",
    "uf": "UF Beneficiário",
    "valor_contratado": "Valor Financiado",
    "valor_desembolsado": "Valor Liberado",
    "contrapartida": "Contrapartida",
    "outros_recursos": "Outros Recursos",
    "financiador": "Agente",
}
COLUNAS_LIDAS_DA_FINEP = (
    "aba",
    *dict.fromkeys([*_DIRETO.values(), *_DESCENTRALIZADO.values()]),
)
ABA_DIRETA = "credito_direto"
ABA_DESCENTRALIZADA = "credito_descentralizado"
# o Status da Finep sem acento nem espaço (`motor.nome_da_coluna`) → a classe
SITUACOES_DA_FINEP = {
    "ENCERRADO": "encerrado_tecnico",  # fechamento técnico do projeto, não quitação
    "RESCINDIDO": "rescindido",
    "CANCELADO": "cancelado",
    "AGUARDANDOREGISTRO": "pendente",
    "EMEXECUCAO": "ativo",
    "EMPRESTACAODECONTAS": "ativo",
    "AGUARDANDOQUITACAODOFINANCIAMENTO": "ativo",
    "AGUARDANDOQUITACAODEFINANCIAMENTO": "ativo",
}
NAO_INFORMADO = "nao_informado"
NAO_CLASSIFICADO = "nao_classificado"


# ajudantes


def _abrir(caminho: Path) -> IO[bytes]:
    """O arquivo guardado (o acervo guarda em `.gz` o que não veio comprimido)."""
    return gzip.open(caminho) if caminho.name.endswith(".gz") else caminho.open("rb")


def _csv(caminho: Path, codificacao: str, colunas: Collection[str]) -> pd.DataFrame:
    """O CSV guardado só com as `colunas` que vierem, como texto aparado (os maiores têm dezenas de
    milhares de linhas: cabem na memória)."""
    with _abrir(caminho) as entrada:
        bruta = pd.read_csv(
            entrada,
            sep=SEPARADOR,
            encoding=codificacao,
            dtype=str,
            keep_default_na=False,
            usecols=lambda coluna: coluna in colunas,
        )
    return bruta.apply(lambda serie: serie.str.strip())


def _texto(serie: pd.Series) -> pd.Series:
    """O texto da fonte, com o vazio e o só-traços ("-", "----------") como nulo."""
    vazio = serie.fillna("").astype(str).str.strip("- ").eq("")
    # `object`: no texto do pandas 3 o nulo seria NaN, e a ficha confere `is None`
    return serie.astype(object).where(~vazio, None)


def _decimal(serie: pd.Series, coluna: str, casas: Decimal) -> pd.Series:
    """ "9090000,0" ou "4000000.04" em `Decimal` com as `casas`; vazio fica nulo, nunca zero. Número que
    não se lê para a leitura (o layout mudou), em vez de virar nulo calado."""

    def converter(texto: str | None) -> Decimal | None:
        if texto is None:
            return None
        limpo = texto.replace(".", "").replace(",", ".") if "," in texto else texto
        try:
            return Decimal(limpo).quantize(casas, rounding=ROUND_HALF_UP)
        except InvalidOperation:
            raise ValueError(f"{coluna}: número que não se lê") from None

    return _objetos((converter(t) for t in _texto(serie)), serie.index)


def _inteiro(serie: pd.Series) -> pd.Series:
    return pd.to_numeric(_texto(serie), errors="coerce").astype("Int64")


def _data(serie: pd.Series) -> pd.Series:
    return pd.to_datetime(_texto(serie), format="%Y-%m-%d", errors="coerce")


def _objetos(valores: Iterable[object], indice: pd.Index) -> pd.Series:
    """Uma coluna `object` em que o nulo é `None` (o `map` do pandas 3 deduz texto e o troca por NaN)."""
    return pd.Series(list(valores), index=indice, dtype=object)


def _cnpj_valido(documento: pd.Series) -> pd.Series:
    """Os 14 caracteres do CNPJ de dígito certo, ou nulo (CPF, mascarado, dígito errado, vazio)."""
    completos = (cnpjs.completo(d) for d in documento)
    return _objetos(
        (c if c is not None and cnpjs.dv_confere(c) else None for c in completos),
        documento.index,
    )


def _formatado(cnpj: pd.Series) -> pd.Series:
    return _objetos(
        (cnpjs.formatar(c) if isinstance(c, str) else None for c in cnpj), cnpj.index
    )


def _com_ordem(grupo: pd.Series, valor: pd.Series) -> pd.Series:
    """`<grupo>|<n>`: a ordem dentro do grupo pelo valor e, no empate, pela posição no arquivo."""
    numero = pd.Series(
        [float(v) if v is not None else np.nan for v in valor], index=valor.index
    )
    ordenada = pd.DataFrame({"grupo": grupo, "valor": numero}).sort_values(
        ["grupo", "valor"], kind="stable", na_position="last"
    )
    ordem = ordenada.groupby("grupo", sort=False).cumcount().add(1)
    return grupo + motor.SEPARADOR_DA_CHAVE + ordem.reindex(grupo.index).astype(str)


def _resumo(tabela: pd.DataFrame, colunas: list[str]) -> pd.Series:
    """Um hash curto das `colunas` como a fonte escreve (o texto, para não depender da conversão)."""
    juntas = tabela[colunas].fillna("").agg(motor.SEPARADOR_DA_CHAVE.join, axis=1)
    return juntas.map(
        lambda t: hashlib.sha256(t.encode()).hexdigest()[:TAMANHO_DO_RESUMO]
    )


def _classe(situacao: pd.Series, classes: Mapping[str, str]) -> pd.Series:
    return _objetos(
        (
            NAO_INFORMADO
            if s is None
            else classes.get(motor.nome_da_coluna(s), NAO_CLASSIFICADO)
            for s in situacao
        ),
        situacao.index,
    )


def _completa(partes: Mapping[str, object], indice: pd.Index) -> pd.DataFrame:
    """As colunas da tabela na ordem certa; a que a fonte não tem fica nula (do tipo dela)."""
    vazias: dict[str, object] = {
        **{c: pd.Series(pd.NA, index=indice, dtype="Int64") for c in PRAZOS},
        "contratado_em": pd.Series(pd.NaT, index=indice, dtype="datetime64[ns]"),
    }
    return pd.DataFrame(
        {
            c: partes.get(c, vazias.get(c, _objetos([None] * len(indice), indice)))
            for c in _LIDAS
        },
        index=indice,
    )


# BNDES


def ler_bndes(caminho: Path) -> tuple[pd.DataFrame, dict[str, int]]:
    """As operações reembolsáveis de CNPJ inteiro de um retrato do BNDES e a contagem do que saiu."""
    bruta = _csv(caminho, "latin-1", set(_BNDES.values()))
    nossas = pd.DataFrame(
        {c: bruta.get(f, pd.Series("", index=bruta.index)) for c, f in _BNDES.items()}
    )
    reembolsavel = (
        nossas["modalidade_de_apoio"].map(motor.nome_da_coluna).eq(REEMBOLSAVEL)
    )
    cnpj = _cnpj_valido(nossas["cnpj"])
    fica = reembolsavel & cnpj.notna()
    contagem = {
        "linhas": len(bruta),
        "nao_reembolsavel": int((~reembolsavel).sum()),
        "cnpj_invalido": int((reembolsavel & cnpj.isna()).sum()),
    }
    nossas = nossas[fica].assign(cnpj=cnpj[fica])
    return _bndes_nas_nossas_colunas(nossas).reset_index(drop=True), contagem


def _bndes_nas_nossas_colunas(nossas: pd.DataFrame) -> pd.DataFrame:
    """DIRETA: o próprio BNDES empresta, sem repassador (é normal); INDIRETA: a credenciada repassa."""
    direta = nossas["forma_de_apoio"].map(motor.nome_da_coluna).eq(DIRETA)
    credenciada = _cnpj_valido(nossas["cnpj_da_credenciada"])
    valor = _decimal(nossas["valor_contratado"], "valor_contratado", CENTAVOS)
    contrato = _texto(nossas["contrato"])
    grupo = (
        "bndes"
        + motor.SEPARADOR_DA_CHAVE
        + contrato.fillna("")
        + motor.SEPARADOR_DA_CHAVE
        + _resumo(nossas, _DESCRITIVOS_DO_BNDES)
    )
    situacao = _texto(nossas["situacao"])
    partes = {
        "id_na_fonte": _com_ordem(grupo, valor),
        "fonte": "bndes",
        "modalidade": "bndes_nao_automatica",
        "cnpj": _formatado(nossas["cnpj"]),
        "cnpj_basico": nossas["cnpj"].str[: cnpjs.TAMANHO_DA_RAIZ],
        "contrato": contrato,
        "contratado_em": _data(nossas["contratado_em"]),
        "valor_contratado": valor,
        "valor_desembolsado": _decimal(
            nossas["valor_desembolsado"], "valor_desembolsado", CENTAVOS
        ),
        "financiador": _texto(nossas["credenciada"]).where(~direta, "BNDES"),
        "agente_papel": direta.map(
            {True: "financiador_direto", False: "instituicao_credenciada"}
        ),
        "cnpj_do_financiador": _formatado(credenciada.where(~direta, CNPJ_DO_BNDES)),
        "juros": _decimal(nossas["juros"], "juros", CASAS_DOS_JUROS),
        **{c: _inteiro(nossas[c]) for c in PRAZOS},
        **{c: _texto(nossas[c]) for c in _TEXTOS_DO_BNDES},
        "situacao": situacao,
        "situacao_classe": _classe(situacao, SITUACOES_DO_BNDES),
    }
    return _completa(partes, nossas.index)


# Finep


def _finep_direta(linhas: pd.DataFrame) -> dict[str, object]:
    nossas = pd.DataFrame({c: linhas[f] for c, f in _DIRETO.items()})
    contrato = _texto(nossas["contrato"])
    valor = _decimal(nossas["valor_contratado"], "Valor Finep", CENTAVOS)
    situacao = _texto(nossas["situacao"])
    grupo = "finep|direto|" + contrato.fillna("")
    return {
        "id_na_fonte": _com_ordem(grupo, valor),
        "modalidade": "finep_credito_direto",
        "contrato": contrato,
        "uf": _texto(nossas["uf"]),
        "uf_do_projeto": _texto(nossas["uf_do_projeto"]),
        "cnpj_do_executor": _formatado(_cnpj_valido(nossas["cnpj_do_executor"])),
        "valor_contratado": valor,
        "valor_desembolsado": _decimal(
            nossas["valor_desembolsado"], "Valor Pago", CENTAVOS
        ),
        "contrapartida": _decimal(
            nossas["contrapartida"], "Contrapartida Financeira", CENTAVOS
        ),
        "financiador": "FINEP",
        "agente_papel": "financiador_direto",
        "cnpj_do_financiador": cnpjs.formatar(CNPJ_DA_FINEP),
        "situacao": situacao,
        "situacao_classe": _classe(situacao, SITUACOES_DA_FINEP),
    }


def _finep_descentralizada(linhas: pd.DataFrame) -> dict[str, object]:
    """O "Contrato Finep Agente" é o convênio entre a Finep e o agente, não o empréstimo: muitas
    empresas cabem no mesmo convênio. A aba não tem situação."""
    nossas = pd.DataFrame({c: linhas[f] for c, f in _DESCENTRALIZADO.items()})
    convenio = _texto(nossas["convenio_do_agente"])
    valor = _decimal(nossas["valor_contratado"], "Valor Financiado", CENTAVOS)
    grupo = (
        "finep|descentralizado|"
        + convenio.fillna("")
        + motor.SEPARADOR_DA_CHAVE
        + linhas["cnpj_valido"]
        + motor.SEPARADOR_DA_CHAVE
        + nossas["contratado_em"]
    )
    return {
        "id_na_fonte": _com_ordem(grupo, valor),
        "modalidade": "finep_credito_descentralizado",
        "convenio_do_agente": convenio,
        "uf": _texto(nossas["uf"]),
        "valor_contratado": valor,
        "valor_desembolsado": _decimal(
            nossas["valor_desembolsado"], "Valor Liberado", CENTAVOS
        ),
        "contrapartida": _decimal(nossas["contrapartida"], "Contrapartida", CENTAVOS),
        "outros_recursos": _decimal(
            nossas["outros_recursos"], "Outros Recursos", CENTAVOS
        ),
        "financiador": _texto(nossas["financiador"]),
        "agente_papel": "agente_descentralizado",
        "situacao_classe": NAO_INFORMADO,
    }


_ABAS_DA_FINEP: dict[str, tuple[str, Callable[[pd.DataFrame], dict[str, object]]]] = {
    ABA_DIRETA: ("CNPJ Proponente", _finep_direta),
    ABA_DESCENTRALIZADA: ("CNPJ Beneficiário", _finep_descentralizada),
}


def ler_finep(caminho: Path) -> tuple[pd.DataFrame, dict[str, int]]:
    """As operações de crédito de CNPJ inteiro de um retrato da Finep e a contagem do que saiu."""
    bruta = _csv(caminho, "utf-8", set(COLUNAS_LIDAS_DA_FINEP))
    if faltam := [c for c in COLUNAS_LIDAS_DA_FINEP if c not in bruta.columns]:
        raise ValueError(
            f"Finep: faltam as colunas {', '.join(faltam)} no CSV da coleta"
        )
    partes: list[pd.DataFrame] = []
    invalidos = 0
    for aba, (documento, ler) in _ABAS_DA_FINEP.items():
        linhas = bruta[bruta["aba"].eq(aba)]
        cnpj = _cnpj_valido(linhas[documento])
        invalidos += int(cnpj.isna().sum())
        linhas = linhas[cnpj.notna()].assign(cnpj_valido=cnpj[cnpj.notna()])
        if linhas.empty:
            continue
        comuns = {
            "fonte": "finep",
            "cnpj": _formatado(linhas["cnpj_valido"]),
            "cnpj_basico": linhas["cnpj_valido"].str[: cnpjs.TAMANHO_DA_RAIZ],
            "contratado_em": _data(linhas["Data Assinatura"]),
        }
        partes.append(_completa({**comuns, **ler(linhas)}, linhas.index))
    tabela = (
        pd.concat(partes, ignore_index=True)
        if partes
        else _completa({}, pd.RangeIndex(0))
    )
    return tabela, {"linhas": len(bruta), "cnpj_invalido": invalidos}


# montagem


def _disponivel_no_primeiro(novos: pd.DataFrame, dia: pd.Timestamp) -> pd.Series:
    """O dia do arquivo: nenhuma das duas fontes diz quando publicou cada linha."""
    return pd.Series(dia, index=novos.index)


@dataclass(frozen=True)
class _Montagem:
    """Os retratos de um banco a juntar num Parquet."""

    destino: Path
    achados: list[motor.Retrato]
    ler: Callable[[Path], tuple[pd.DataFrame, dict[str, int]]]


def _montagens(conexao: sa.Connection, pasta: Path) -> Iterator[tuple[str, _Montagem]]:
    bndes = motor.retratos(conexao, FONTE_DO_BNDES, url_termina_em=ARQUIVO_DO_BNDES)
    if bndes:
        yield "bndes", _Montagem(pasta / TABELA / "bndes", bndes, ler_bndes)
    finep = motor.retratos(conexao, FONTE_DA_FINEP)
    if finep:
        yield "finep", _Montagem(pasta / TABELA / "finep", finep, ler_finep)


def _como_numeros(pessoas: Collection[str] | np.ndarray) -> np.ndarray:
    if isinstance(pessoas, np.ndarray):
        return pessoas
    return cnpjs.ordenados(cnpjs.raizes_em_numeros(pd.Series(list(pessoas), dtype=str)))


def _origens(achados: list[motor.Retrato]) -> list[dict[str, str]]:
    return [{"url": r.url, "sha256": r.sha256} for r in achados]


def _para_gravar(
    tabela: pd.DataFrame, pessoas: np.ndarray, agora: datetime
) -> pd.DataFrame:
    """Com os tipos do disco fixos: o mesmo decimal nos dois Parquets, para a porta ler os dois juntos."""
    basico = tabela["cnpj_basico"].astype(str)
    return (
        tabela.assign(
            trata_como_pessoa=cnpjs.contem(pessoas, cnpjs.raizes_em_numeros(basico))
            if len(tabela)
            else pd.Series(dtype=bool),
            **{
                c: pd.to_datetime(tabela[c]).dt.date
                for c in ["contratado_em", "visto_em", "disponivel_em"]
            },
            **{c: tabela[c].astype(pd.ArrowDtype(TIPO_DO_DINHEIRO)) for c in DINHEIRO},
            juros=tabela["juros"].astype(pd.ArrowDtype(TIPO_DOS_JUROS)),
            consta=tabela["consta"].astype(bool),
            montado_em=agora.isoformat(),
            versao_do_codigo=versao_do_codigo(),
        )[[*COLUNAS, *LINHAGEM]]
        .sort_values(ORDEM, kind="stable")
        .reset_index(drop=True)
    )


def montar(
    conexao: sa.Connection,
    pasta: Path,
    agora: datetime,
    pessoas: Collection[str] | np.ndarray | None = None,
    refazer: bool = False,
) -> dict[str, dict[str, int]]:
    """`<pasta>/financiamentos/bndes.parquet` e `finep.parquet` com os retratos guardados.

    Sem arquivo novo desde a última montagem, o banco é pulado (`refazer` relê mesmo assim, para
    código novo). `pessoas`: as raízes de pessoa já sabidas; sem elas, pergunta à Receita guardada.
    """
    resumo: dict[str, dict[str, int]] = {}
    for nome, montagem in _montagens(conexao, pasta):
        if not refazer and origens_gravadas(montagem.destino) == _origens(
            montagem.achados
        ):
            resumo[nome] = JA_MONTADO
            continue
        contagem: dict[str, int] = {}
        lidos = []
        for retrato in montagem.achados:
            tabela, contou = montagem.ler(retrato.caminho)
            for chave, valor in contou.items():
                contagem[chave] = contagem.get(chave, 0) + valor
            lidos.append((retrato, tabela))
        tabela, pulados = motor.juntar(lidos, VALORES, _disponivel_no_primeiro)
        if pessoas is None:
            raizes = cnpjs.ordenados(
                cnpjs.raizes_em_numeros(
                    tabela["cnpj_basico"].drop_duplicates().astype(str)
                )
            )
            de_pessoa = pessoas_pela_receita(conexao, raizes)
        else:
            de_pessoa = _como_numeros(pessoas)
        gravar_se_mudou(
            _para_gravar(tabela, de_pessoa, agora),
            montagem.destino,
            _origens(montagem.achados),
            ORDEM,
            carimbos=LINHAGEM,
        )
        resumo[nome] = {
            **contagem,
            "retratos": len(montagem.achados),
            "retratos_pulados": pulados,
            "na_tabela": len(tabela),
        }
    return resumo
