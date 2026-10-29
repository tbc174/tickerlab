"""Incentivos por CNPJ (linha 525 da fila; Ficha Clara, etapa 4b): as três coletas da etapa 4a
(`base/arquivo/fontes.py`) em três tabelas.

- `mme_reidi`: projetos de energia enquadrados no REIDI (MME), com a portaria, as datas e os valores.
  Um retrato do cadastro a cada vez (o motor de `base/retratos.py`), como as licenças.
- `aneel_cde`: os descontos tarifários pagos pela CDE (ANEEL), **somados** por CNPJ, mês, distribuidora,
  classe, grupo tarifário e tipo de subsídio (a fonte traz uma linha por unidade consumidora; `linhas`
  diz quantas foram somadas). Cada arquivo (um ZIP por mês; um CSV por ano da rede básica) é um retrato
  só dele: a ANEEL pode republicar o mês corrigido, e a correção vira linha nova.
- `bcb_rde_ied`: os registros de investimento estrangeiro direto (BC, RDE-IED) pelo CNPJ básico da
  empresa que recebeu (a fonte só dá a raiz, 8 caracteres), de nov/2011 a dez/2022.

Lê os arquivos que o arquivista já guardou (não baixa nada).

- **Só pessoa jurídica:** a coleta já tirou o CPF (a CDE mensal tem baixa renda e rural) e o nome do
  cliente, do agente, do investidor e da empresa; aqui a conferência do CNPJ se repete. Empresário
  individual e MEI ficam com `trata_como_pessoa` (ADR 0075).
- **Sem olhar o futuro** (`disponivel_em`): o dia do arquivo em que a linha foi vista, também no
  primeiro. Nenhuma das três diz quando publicou cada linha: a portaria do REIDI e o mês da CDE ou do
  RDE ficam nas colunas deles, para ler, nunca como `disponivel_em`.

Limites conhecidos: o arquivista começou a guardar as três em 29/10/2026, então nada aqui vale antes
disso; a CDE guardada começa nos 13 meses mais novos (o histórico desde 2018 está na fila); o RDE-IED
publica a moeda e o valor sempre vazios, e ficam de fora; o código da classe, do grupo e do tipo de
desconto da rede básica vem como a ANEEL escreve (o sentido está no dicionário em PDF da fonte).
"""

import gzip
import io
import json
import re
from collections.abc import Callable, Collection, Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import IO

import numpy as np
import pandas as pd
import sqlalchemy as sa

from base import cnpj as cnpjs
from base import retratos as motor
from base.parquet import LINHAGEM, gravar_se_mudou, origens_gravadas
from base.pgfn import pessoas_pela_receita
from src.versao_do_codigo import versao_do_codigo

SEPARADOR = ";"  # a coleta grava todo CSV com ";"
LATIN1 = "latin-1"
UTF8 = "utf-8"
LINHAS_POR_PEDACO = (
    500_000  # o CSV mensal da CDE, só com as linhas de CNPJ, tem centenas de MB
)
JA_MONTADO = {"ja_montado": 1}  # no resumo: nenhum arquivo novo desde a última montagem
RAIZ = r"[0-9A-Z]{8}"  # o CNPJ básico, com letras ou não (julho de 2026)
FORA_DO_NOME_DO_ARQUIVO = re.compile(r"[^a-z0-9-]+")
MESES = (
    "janeiro", "fevereiro", "marco", "abril", "maio", "junho", "julho", "agosto", "setembro",
    "outubro", "novembro", "dezembro",
)  # fmt: skip

FONTE_DO_REIDI = "mme-reidi"
FONTE_DA_CDE = "aneel-cde"
FONTE_DO_RDE = "bcb-rde-ied"
TABELA_DO_REIDI = "mme_reidi"
TABELA_DA_CDE = "aneel_cde"
TABELA_DO_RDE = "bcb_rde_ied"
TABELAS = (TABELA_DO_REIDI, TABELA_DA_CDE, TABELA_DO_RDE)

_CARIMBOS = ["consta", "trata_como_pessoa", "visto_em", "disponivel_em"]
TEXTOS_DO_REIDI = [
    "processo",
    "projeto",
    "nome_do_projeto",
    "portaria",
    "uf",
    "municipio",
]
DATAS_DO_REIDI = ["portaria_em", "execucao_desde", "execucao_ate"]
VALORES_DO_REIDI = [
    "valor_com_incidencia",
    "valor_sem_incidencia",
    "valor_do_beneficio",
]
COLUNAS_DO_REIDI = [
    "id_na_fonte", "cnpj", "cnpj_basico", *TEXTOS_DO_REIDI, *DATAS_DO_REIDI, *VALORES_DO_REIDI,
    *_CARIMBOS,
]  # fmt: skip
CHAVE_DA_CDE = [
    "cnpj", "mes", "distribuidora", "cnpj_da_distribuidora", "classe", "grupo_tarifario",
    "tipo_de_desconto",
]  # fmt: skip
SOMAS_DA_CDE = ["valor_do_desconto", "valor_cobrado", "linhas"]
COLUNAS_DA_CDE = [
    "arquivo", "id_na_fonte", "cnpj_basico", *CHAVE_DA_CDE, *SOMAS_DA_CDE, "gerado_em",
    *_CARIMBOS,
]  # fmt: skip
TEXTOS_DO_RDE = ["codigo_rde", "uf", "pais", "ocorrencia"]
COLUNAS_DO_RDE = ["id_na_fonte", "cnpj_basico", *TEXTOS_DO_RDE, "mes", *_CARIMBOS]
ORDEM = ["id_na_fonte", "visto_em"]

_REIDI = {
    "processo": "Processo",
    "projeto": "idt_projeto",
    "nome_do_projeto": "Nome_do_Projeto",
    "portaria": "Portaria",
    "uf": "UF",
    "municipio": "Municipio",
    "portaria_em": "Data_inicio_portaria",
    "execucao_desde": "dat_Execucao_Inicio",
    "execucao_ate": "dat_Execucao_Termino",
    "valor_com_incidencia": "vlr_Total_Com_Incidencia_PISPASEP_COFINS",
    "valor_sem_incidencia": "vlr_Total_Sem_Incidencia_PISPASEP_COFINS",
    "valor_do_beneficio": "vlr_Beneficio_Fiscal",
}
# o arquivo mensal: uma linha por unidade consumidora e tipo de subsídio
_CDE_MENSAL = {
    "cnpj": "NumCPFCNPJCliente",
    "mes": "AnmReferencia",  # "05/2026"
    "distribuidora": "SigAgente",
    "cnpj_da_distribuidora": "NumCNPJDistribuidora",
    "classe": "IdcClasseConsumidor",
    "grupo_tarifario": "IdcSubgrupoTarifario",
    "tipo_de_desconto": "DscTipoSubsidio",
    "valor_do_desconto": "VlrSubsidio",
    "gerado_em": "DatGeracaoConjuntoDados",  # "10/07/2026"
}
# a rede básica: uma linha por agente (usina, consumidor livre) e mês
_CDE_REDE_BASICA = {
    "cnpj": "NumCNPJ",
    "ano": "NumAno",
    "nome_do_mes": "NomMes",  # "Janeiro"
    "classe": "IdcClasseConsumidor",
    "grupo_tarifario": "DscGrupoTarifario",
    "tipo_de_desconto": "IdcTipo",
    "valor_do_desconto": "VlrDesconto",
    "valor_cobrado": "VlrCobranca",
    "gerado_em": "DatGeracaoConjuntoDados",  # "23/07/2026 09:24:34"
}
_RDE = {
    "codigo_rde": "CodigoRDE",
    "cnpj_basico": "CnpjBaseReceptora",
    "uf": "UfPessoaNacional",
    "pais": "PaisPessoaEstrangeira",
    "ocorrencia": "Ocorrencia",
}
CHAVE_DO_RDE = ["codigo_rde", "ocorrencia", "mes", "pais"]


def _reais(texto: pd.Series) -> pd.Series:
    """ "17.959.886,51" em número; o que não for número fica nulo."""
    limpo = texto.fillna("").str.replace(".", "", regex=False).str.replace(",", ".")
    return pd.to_numeric(limpo, errors="coerce")


def _cnpjs_validos(documento: pd.Series) -> tuple[pd.Series, pd.Series]:
    """O CNPJ completo e se ele é de pessoa jurídica com o dígito certo (com letras ou não)."""
    cnpj = documento.map(cnpjs.completo)
    valido = cnpj.map(lambda c: isinstance(c, str) and cnpjs.dv_confere(c)).astype(bool)
    return cnpj, valido


def _abrir(caminho: Path) -> IO[bytes]:
    """O arquivo guardado sem carregar tudo na memória (o acervo guarda em `.gz` o que não veio
    comprimido)."""
    return gzip.open(caminho) if caminho.name.endswith(".gz") else caminho.open("rb")


def _csv(
    caminho: Path, codificacao: str, colunas: Collection[str]
) -> Iterator[pd.DataFrame]:
    """O CSV guardado em pedaços, só com as `colunas` que vierem, como texto aparado."""
    with _abrir(caminho) as entrada:
        pedacos = pd.read_csv(
            entrada,
            sep=SEPARADOR,
            encoding=codificacao,
            dtype=str,
            keep_default_na=False,
            usecols=lambda coluna: coluna in colunas,
            chunksize=LINHAS_POR_PEDACO,
        )  # type: ignore[call-overload]
        for pedaco in pedacos:
            yield pedaco.apply(lambda serie: serie.str.strip())


# REIDI


def ler_reidi(caminho: Path) -> tuple[pd.DataFrame, dict[str, int]]:
    """Os projetos de CNPJ inteiro de um retrato do REIDI e a contagem do que ficou de fora."""
    bruta = pd.concat(
        list(_csv(caminho, UTF8, {*_REIDI.values(), "CNPJ"})), ignore_index=True
    )
    cnpj, valido = _cnpjs_validos(bruta["CNPJ"])
    nossas = pd.DataFrame(
        {c: bruta.get(f, pd.Series("", index=bruta.index)) for c, f in _REIDI.items()}
    )[valido.to_numpy()].assign(cnpj=cnpj[valido])
    nossas["id_na_fonte"] = motor.chave(nossas, ["processo", "projeto"])
    repetido = nossas["id_na_fonte"].duplicated(keep="first")
    nossas = nossas[~repetido]
    pronta = pd.DataFrame(
        {
            "id_na_fonte": nossas["id_na_fonte"],
            "cnpj": nossas["cnpj"].map(cnpjs.formatar),
            "cnpj_basico": nossas["cnpj"].str[: cnpjs.TAMANHO_DA_RAIZ],
            **{c: motor.sem_vazio(nossas[c]) for c in TEXTOS_DO_REIDI},
            **{
                c: pd.to_datetime(nossas[c], format="%Y-%m-%d", errors="coerce")
                for c in DATAS_DO_REIDI
            },
            **{c: _reais(nossas[c]) for c in VALORES_DO_REIDI},
        }
    ).reset_index(drop=True)
    contagem = {
        "linhas": len(bruta),
        "cnpj_invalido": int((~valido).sum()),
        "id_repetido": int(repetido.sum()),
    }
    return pronta, contagem


# CDE


def _mes_da_rede_basica(ano: pd.Series, nome_do_mes: pd.Series) -> pd.Series:
    numero = (
        nome_do_mes.map(motor.nome_da_coluna)
        .str.lower()
        .map({m: i + 1 for i, m in enumerate(MESES)})
    )
    return pd.to_datetime(
        pd.DataFrame(
            {"year": pd.to_numeric(ano, errors="coerce"), "month": numero, "day": 1}
        ),
        errors="coerce",
    )


def _cde_do_pedaco(pedaco: pd.DataFrame, mensal: bool) -> tuple[pd.DataFrame, int]:
    """As linhas de CNPJ inteiro de um pedaço, nas nossas colunas, e quantas ficaram de fora."""
    mapa = _CDE_MENSAL if mensal else _CDE_REDE_BASICA
    nossas = pd.DataFrame(
        {c: pedaco.get(f, pd.Series("", index=pedaco.index)) for c, f in mapa.items()}
    )
    cnpj, valido = _cnpjs_validos(nossas["cnpj"])
    nossas = nossas[valido.to_numpy()].assign(cnpj=cnpj[valido].map(cnpjs.formatar))
    if mensal:
        mes = pd.to_datetime(nossas["mes"], format="%m/%Y", errors="coerce")
        nossas = nossas.assign(mes=mes, valor_cobrado="")
    else:
        mes = _mes_da_rede_basica(nossas["ano"], nossas["nome_do_mes"])
        nossas = nossas.drop(columns=["ano", "nome_do_mes"]).assign(
            mes=mes, distribuidora="", cnpj_da_distribuidora=""
        )
    nossas = nossas.assign(
        valor_do_desconto=_reais(nossas["valor_do_desconto"]),
        valor_cobrado=_reais(nossas["valor_cobrado"]),
        gerado_em=pd.to_datetime(
            nossas["gerado_em"].str[:10], format="%d/%m/%Y", errors="coerce"
        ),
        linhas=1,
    )
    return nossas, int((~valido).sum())


def _somar(tabela: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por chave, com os valores e as linhas da fonte somados (o nulo não vira zero)."""
    return (
        tabela.groupby(CHAVE_DA_CDE, dropna=False, sort=False)
        .agg(
            valor_do_desconto=("valor_do_desconto", lambda s: s.sum(min_count=1)),
            valor_cobrado=("valor_cobrado", lambda s: s.sum(min_count=1)),
            linhas=("linhas", "sum"),
            gerado_em=("gerado_em", "max"),
        )
        .reset_index()
    )


def ler_cde(caminho: Path, mensal: bool) -> tuple[pd.DataFrame, dict[str, int]]:
    """Os descontos de CNPJ inteiro de um arquivo da CDE, somados, e a contagem do que ficou de fora."""
    mapa = _CDE_MENSAL if mensal else _CDE_REDE_BASICA
    codificacao = LATIN1 if mensal else UTF8
    somados: list[pd.DataFrame] = []
    linhas = invalidos = 0
    for pedaco in _csv(caminho, codificacao, set(mapa.values())):
        nossas, fora = _cde_do_pedaco(pedaco, mensal)
        linhas += len(pedaco)
        invalidos += fora
        somados.append(_somar(nossas))
    if somados:
        tabela = _somar(pd.concat(somados, ignore_index=True))
    else:
        tabela = pd.DataFrame(columns=[*CHAVE_DA_CDE, *SOMAS_DA_CDE, "gerado_em"])
    texto_da_chave = tabela[CHAVE_DA_CDE].astype(str).replace({"NaT": "", "nan": ""})
    tabela["id_na_fonte"] = motor.chave(texto_da_chave, CHAVE_DA_CDE)
    tabela["cnpj_basico"] = (
        tabela["cnpj"].map(cnpjs.completo).str[: cnpjs.TAMANHO_DA_RAIZ]
    )
    for coluna in (
        "distribuidora",
        "cnpj_da_distribuidora",
        "classe",
        "grupo_tarifario",
        "tipo_de_desconto",
    ):
        tabela[coluna] = motor.sem_vazio(tabela[coluna].fillna(""))
    return tabela, {"linhas": linhas, "cnpj_invalido": invalidos}


def _e_mensal(url: str) -> bool:
    return url.lower().endswith(".zip")


def nome_do_arquivo(url: str) -> str:
    """O nome do Parquet de um arquivo da CDE: o fim do endereço, sem extensão."""
    final = url.rstrip("/").rsplit("/", 1)[-1].lower()
    return FORA_DO_NOME_DO_ARQUIVO.sub("-", final.rsplit(".", 1)[0]).strip("-")


# RDE-IED


def ler_rde(caminho: Path) -> tuple[pd.DataFrame, dict[str, int]]:
    """Os registros com CNPJ básico bem formado e a contagem do que ficou de fora."""
    with _abrir(caminho) as entrada:
        itens = json.load(io.TextIOWrapper(entrada, encoding=UTF8))["value"]
    bruta = pd.DataFrame(itens)
    nossas = pd.DataFrame(
        {
            c: (bruta[f] if f in bruta else pd.Series("", index=bruta.index))
            .fillna("")
            .astype(str)
            .str.strip()
            for c, f in _RDE.items()
        }
    )
    nossas["mes"] = pd.to_datetime(
        pd.DataFrame(
            {
                "year": pd.to_numeric(bruta.get("Ano"), errors="coerce"),
                "month": pd.to_numeric(bruta.get("Mes"), errors="coerce"),
                "day": 1,
            }
        ),
        errors="coerce",
    )
    valido = nossas["cnpj_basico"].str.upper().str.fullmatch(RAIZ).astype(bool)
    nossas = nossas[valido].assign(cnpj_basico=nossas["cnpj_basico"].str.upper())
    texto_da_chave = nossas[CHAVE_DO_RDE].astype(str).replace({"NaT": ""})
    nossas["id_na_fonte"] = motor.chave(texto_da_chave, CHAVE_DO_RDE)
    repetido = nossas["id_na_fonte"].duplicated(keep="first")
    nossas = nossas[~repetido]
    pronta = nossas.assign(
        **{c: motor.sem_vazio(nossas[c]) for c in TEXTOS_DO_RDE}
    ).reset_index(drop=True)
    contagem = {
        "linhas": len(bruta),
        "cnpj_invalido": int((~valido).sum()),
        "id_repetido": int(repetido.sum()),
    }
    return pronta[["id_na_fonte", "cnpj_basico", *TEXTOS_DO_RDE, "mes"]], contagem


# montagem


def _disponivel_no_primeiro(novos: pd.DataFrame, dia: pd.Timestamp) -> pd.Series:
    """O dia do arquivo: nenhuma das três fontes diz quando publicou cada linha."""
    return pd.Series(dia, index=novos.index)


@dataclass(frozen=True)
class _Montagem:
    """Uma tabela de um arquivo (ou de uma série de retratos do mesmo endereço) a gravar."""

    destino: Path
    achados: list[motor.Retrato]
    ler: Callable[[Path], tuple[pd.DataFrame, dict[str, int]]]
    valores: list[str]
    colunas: list[str]
    datas: list[str]
    extra: dict[str, str]


def _como_numeros(pessoas: Collection[str] | np.ndarray) -> np.ndarray:
    if isinstance(pessoas, np.ndarray):
        return pessoas
    return cnpjs.ordenados(cnpjs.raizes_em_numeros(pd.Series(list(pessoas), dtype=str)))


def _origens(achados: list[motor.Retrato]) -> list[dict[str, str]]:
    return [{"url": r.url, "sha256": r.sha256} for r in achados]


def _montagens(conexao: sa.Connection, pasta: Path) -> Iterator[tuple[str, _Montagem]]:
    reidi = motor.retratos(conexao, FONTE_DO_REIDI)
    if reidi:
        yield "reidi", _Montagem(
            pasta / TABELA_DO_REIDI / "reidi", reidi, ler_reidi,
            ["cnpj", *TEXTOS_DO_REIDI, *DATAS_DO_REIDI, *VALORES_DO_REIDI, "consta"],
            COLUNAS_DO_REIDI, DATAS_DO_REIDI, {},
        )  # fmt: skip
    por_endereco: dict[str, list[motor.Retrato]] = {}
    for retrato in motor.retratos(conexao, FONTE_DA_CDE):
        por_endereco.setdefault(retrato.url, []).append(retrato)
    for url, achados in por_endereco.items():
        mensal = _e_mensal(url)
        nome = nome_do_arquivo(url)
        yield nome, _Montagem(
            pasta / TABELA_DA_CDE / nome, achados,
            lambda caminho, mensal=mensal: ler_cde(caminho, mensal),
            [*SOMAS_DA_CDE, "gerado_em", "consta"],
            COLUNAS_DA_CDE, ["mes", "gerado_em"],
            {"arquivo": "mensal" if mensal else "rede_basica"},
        )  # fmt: skip
    rde = motor.retratos(conexao, FONTE_DO_RDE)
    if rde:
        yield "rde_ied", _Montagem(
            pasta / TABELA_DO_RDE / "rde_ied", rde, ler_rde,
            [*TEXTOS_DO_RDE, "cnpj_basico", "consta"],
            COLUNAS_DO_RDE, ["mes"], {},
        )  # fmt: skip


def _para_gravar(
    tabela: pd.DataFrame, montagem: _Montagem, pessoas: np.ndarray, agora: datetime
) -> pd.DataFrame:
    basico = tabela["cnpj_basico"].astype(str)
    return (
        tabela.assign(
            **montagem.extra,
            trata_como_pessoa=cnpjs.contem(pessoas, cnpjs.raizes_em_numeros(basico))
            if len(tabela)
            else pd.Series(dtype=bool),
            **{
                c: pd.to_datetime(tabela[c]).dt.date
                for c in [*montagem.datas, "visto_em", "disponivel_em"]
            },
            consta=tabela["consta"].astype(bool),
            montado_em=agora.isoformat(),
            versao_do_codigo=versao_do_codigo(),
        )[[*montagem.colunas, *LINHAGEM]]
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
    """`<pasta>/<tabela>/<arquivo>.parquet` para cada arquivo guardado das três fontes.

    O REIDI e o RDE são um Parquet cada; a CDE, um por arquivo da ANEEL (o mês ou o ano da rede
    básica). Sem arquivo novo desde a última montagem, é pulado (`refazer` relê mesmo assim, para
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
        tabela, pulados = motor.juntar(lidos, montagem.valores, _disponivel_no_primeiro)
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
            _para_gravar(tabela, montagem, de_pessoa, agora),
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
