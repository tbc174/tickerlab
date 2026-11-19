"""Dívida ativa estadual por CNPJ (linha 755 da fila; motor de risco cedente/sacado, linha 754).

Três tabelas de pessoa jurídica, a partir do que o arquivista guarda (`base/arquivo/lote_divida_estadual.py`):
`sefa_pr_divida_ativa` (os débitos inscritos em dívida ativa no Paraná, Sefa-PR, de ZIPs diários),
`sef_mg_divida_ativa` (as CDAs de Minas Gerais, SEF-MG) e `sef_mg_parcelamentos` (os parcelamentos de
débitos inscritos, também de MG), as duas últimas de planilhas `.xlsb` de endereço fixo.

- **Um retrato por arquivo, uma série por tabela:** o endereço do ZIP do Paraná muda todo dia, então todos
  os arquivos guardados formam uma série só; o de Minas tem endereço fixo, e cada versão nova do arquivo
  é um retrato (o motor de `base/retratos.py`). Débito novo, ou com valor ou situação diferente, vira
  linha nova desde o dia em que foi visto; débito que some do arquivo (pago, cancelado, prescrito) ganha
  `consta` falso nesse dia. Esse "sumiu" é o sinal de que o devedor quitou, mas a fonte não diz o motivo.
- **Só pessoa jurídica (ADR 0075 e 0088):** a coleta já tirou o CPF, o nome e a razão social; aqui o CNPJ
  se confere de novo. Empresário individual e MEI não se distinguem no arquivo (não há natureza
  jurídica), então ficam com `trata_como_pessoa` pela Receita guardada.
- **Sem olhar o futuro** (`disponivel_em`): o dia em que o TickerLab viu a linha. A data da inscrição
  (`inscrito_em`, às vezes de 1973) e a do parcelamento (`parcelado_em`) contam quando o fato nasceu,
  nunca quando a base soube.
- **Identidade:** PR: o número da dívida ativa, o CNPJ e o tipo do crédito juntos (o número sozinho se
  repete entre devedores e tipos). MG: o número da CDA (ou do parcelamento) e o CNPJ.

Limites conhecidos: a fonte não dá o nome do devedor, a natureza do débito além do tipo do crédito (PR) ou
da espécie (MG), nem o motivo de o débito sair; Minas não diz a data da última atualização do saldo; a
licença é "a confirmar" (ADR 0102, Emenda 2).
"""

from collections.abc import Callable, Collection, Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import sqlalchemy as sa

from base import cnpj as cnpjs
from base import retratos as motor
from base.arquivo import lote_divida_estadual as coleta
from base.parquet import LINHAGEM, gravar_se_mudou, origens_gravadas
from base.pgfn import pessoas_pela_receita
from src.versao_do_codigo import versao_do_codigo

SEPARADOR = ";"  # a coleta grava todo CSV com ";"
UTF8 = "utf-8"
FORMATO_DA_DATA_DO_PR = "%d/%m/%Y"  # a Sefa-PR escreve "18/06/1973"
FORMATO_DA_DATA_DE_MG = "%Y-%m-%d"  # a coleta de MG grava a data da planilha em ISO
SIM = "Sim"
JA_MONTADO = {"ja_montado": 1}  # no resumo: nenhum arquivo novo desde a última montagem

FONTE_DO_PR = "sefapr-divida-ativa"
TABELA_DO_PR = "sefa_pr_divida_ativa"
ARQUIVO_DO_PR = "divida_ativa"
FONTE_DE_MG = "sefmg-divida-ativa"
TABELA_DAS_CDAS_DE_MG = "sef_mg_divida_ativa"
TABELA_DOS_PARCELAMENTOS_DE_MG = "sef_mg_parcelamentos"
ORDEM = ["id_na_fonte", "visto_em"]

# do nome da coluna na fonte (`coleta.COLUNAS_GUARDADAS_NO_PR`) para o nosso
_PR = {
    "divida_ativa": "Dívida ativa",
    "inscrito_em": "Data da inscrição do débito",
    "atualizado_em": "Data da atualização",
    "valor_do_imposto": "Valor do imposto",
    "valor_da_multa": "Valor da multa",
    "valor_dos_juros": "Valor dos juros",
    "valor_total": "Valor total",
    "tipo_do_credito": "Tipo do crédito",
    "cnpj": "CNPJ",
    "suspensao": "Suspensão de exigibilidade",
    "garantia": "Indicativo de garantia",
    "parcelamento": "Indicativo de parcelamento ativo",
}
# o mesmo para as planilhas de Minas (`coleta.COLUNAS_DAS_CDAS_DE_MG` e `..._DOS_PARCELAMENTOS_DE_MG`)
_CDAS_DE_MG = {
    "cnpj": "CNPJ",
    "cda": "CDA",
    "inscrito_em": "Data da inscrição",
    "especie": "Espécie",
    "saldo_da_cda": "Saldo da CDA",
    "saldo_do_nucleo": "Saldo do núcleo",
}
_PARCELAMENTOS_DE_MG = {
    "cnpj": "CNPJ",
    "parcelamento": "Parcelamento",
    "especie": "Espécie",
    "parcelado_em": "Data do parcelamento",
    "parcelas": "Parcelas",
    "debito": "Débito",
}
VALORES_EM_REAIS = [
    "valor_do_imposto",
    "valor_da_multa",
    "valor_dos_juros",
    "valor_total",
]
DATAS = ["inscrito_em", "atualizado_em"]
SIM_OU_NAO = ["com_garantia", "com_parcelamento_ativo"]
CHAVE = ["divida_ativa", "cnpj", "tipo_do_credito"]
# o que, mudando, faz do débito uma linha nova (a data da atualização acompanha o valor)
VALORES = [
    *VALORES_EM_REAIS,
    "atualizado_em",
    "suspensao",
    *SIM_OU_NAO,
    "consta",
]
_CARIMBOS = ["consta", "trata_como_pessoa", "visto_em", "disponivel_em"]
_IDENTIDADE = ["id_na_fonte", "cnpj", "cnpj_basico"]
COLUNAS = [
    *_IDENTIDADE,
    "divida_ativa",
    "tipo_do_credito",
    "inscrito_em",
    "atualizado_em",
    *VALORES_EM_REAIS,
    "suspensao",
    *SIM_OU_NAO,
    *_CARIMBOS,
]
COLUNAS_DAS_CDAS_DE_MG = [
    *_IDENTIDADE,
    "cda",
    "inscrito_em",
    "especie",
    "saldo_da_cda",
    "saldo_do_nucleo",
    *_CARIMBOS,
]
COLUNAS_DOS_PARCELAMENTOS_DE_MG = [
    *_IDENTIDADE,
    "parcelamento",
    "parcelado_em",
    "especie",
    "parcelas",
    "debito",
    *_CARIMBOS,
]

Leitor = Callable[[Path], tuple[pd.DataFrame, dict[str, int]]]


def _abrir_csv(caminho: Path) -> pd.DataFrame:
    """O CSV guardado como texto aparado (o acervo guarda em `.gz` o que não veio comprimido)."""
    bruto = pd.read_csv(
        caminho,
        sep=SEPARADOR,
        encoding=UTF8,
        dtype=str,
        keep_default_na=False,
        compression="gzip" if caminho.name.endswith(".gz") else None,
    )
    return bruto.apply(lambda serie: serie.str.strip())


def _data(texto: pd.Series, formato: str) -> pd.Series:
    """ "18/06/1973" em data; vazio e data impossível ficam nulos."""
    return pd.to_datetime(texto, format=formato, errors="coerce")


def _numero(texto: pd.Series) -> pd.Series:
    """Número com ponto decimal ("1787.10"); vazio e texto ficam nulos."""
    return pd.to_numeric(texto, errors="coerce")


def _so_cnpj_inteiro(
    bruta: pd.DataFrame, mapa: dict[str, str], chave: list[str]
) -> tuple[pd.DataFrame, dict[str, int]]:
    """As linhas de CNPJ de dígito certo, com a chave do registro, sem repetida, e a contagem do resto."""
    nossas = pd.DataFrame(
        {c: bruta.get(f, pd.Series("", index=bruta.index)) for c, f in mapa.items()}
    )
    completo = nossas["cnpj"].map(cnpjs.completo)
    valido = completo.map(lambda c: isinstance(c, str) and cnpjs.dv_confere(c)).astype(
        bool
    )
    nossas = nossas[valido.to_numpy()].assign(cnpj=completo[valido])
    nossas["id_na_fonte"] = motor.chave(nossas, chave)
    repetido = nossas["id_na_fonte"].duplicated(keep="first")
    contagem = {
        "linhas": len(bruta),
        "cnpj_invalido": int((~valido).sum()),
        "id_repetido": int(repetido.sum()),
    }
    return nossas[~repetido], contagem


def _identidade(nossas: pd.DataFrame) -> dict[str, pd.Series]:
    return {
        "id_na_fonte": nossas["id_na_fonte"],
        "cnpj": nossas["cnpj"].map(cnpjs.formatar),
        "cnpj_basico": nossas["cnpj"].str[: cnpjs.TAMANHO_DA_RAIZ],
    }


def ler_pr(caminho: Path) -> tuple[pd.DataFrame, dict[str, int]]:
    """Os débitos de CNPJ inteiro de um retrato do Paraná e a contagem do que ficou de fora."""
    nossas, contagem = _so_cnpj_inteiro(_abrir_csv(caminho), _PR, CHAVE)
    pronta = pd.DataFrame(
        {
            **_identidade(nossas),
            "divida_ativa": motor.sem_vazio(nossas["divida_ativa"]),
            "tipo_do_credito": motor.sem_vazio(nossas["tipo_do_credito"]),
            **{c: _data(nossas[c], FORMATO_DA_DATA_DO_PR) for c in DATAS},
            **{c: _numero(nossas[c]) for c in VALORES_EM_REAIS},
            "suspensao": motor.sem_vazio(
                nossas["suspensao"].where(~nossas["suspensao"].str.fullmatch("N[ãa]o"))
            ),  # "Não" é a ausência de suspensão
            "com_garantia": nossas["garantia"].eq(SIM),
            "com_parcelamento_ativo": nossas["parcelamento"].eq(SIM),
        }
    ).reset_index(drop=True)
    return pronta, contagem


def ler_cdas_de_mg(caminho: Path) -> tuple[pd.DataFrame, dict[str, int]]:
    """As CDAs de CNPJ inteiro de um retrato de Minas e a contagem do que ficou de fora."""
    nossas, contagem = _so_cnpj_inteiro(
        _abrir_csv(caminho), _CDAS_DE_MG, ["cda", "cnpj"]
    )
    pronta = pd.DataFrame(
        {
            **_identidade(nossas),
            "cda": motor.sem_vazio(nossas["cda"]),
            "inscrito_em": _data(nossas["inscrito_em"], FORMATO_DA_DATA_DE_MG),
            "especie": motor.sem_vazio(nossas["especie"]),
            "saldo_da_cda": _numero(nossas["saldo_da_cda"]).round(2),
            "saldo_do_nucleo": _numero(nossas["saldo_do_nucleo"]).round(2),
        }
    ).reset_index(drop=True)
    return pronta, contagem


def ler_parcelamentos_de_mg(caminho: Path) -> tuple[pd.DataFrame, dict[str, int]]:
    """Os parcelamentos de CNPJ inteiro de um retrato de Minas e a contagem do que ficou de fora."""
    nossas, contagem = _so_cnpj_inteiro(
        _abrir_csv(caminho), _PARCELAMENTOS_DE_MG, ["parcelamento", "cnpj"]
    )
    pronta = pd.DataFrame(
        {
            **_identidade(nossas),
            "parcelamento": motor.sem_vazio(nossas["parcelamento"]),
            "parcelado_em": _data(nossas["parcelado_em"], FORMATO_DA_DATA_DE_MG),
            "especie": motor.sem_vazio(nossas["especie"]),
            "parcelas": _numero(nossas["parcelas"]).astype("Int64"),
            "debito": _numero(nossas["debito"]).round(2),
        }
    ).reset_index(drop=True)
    return pronta, contagem


@dataclass(frozen=True)
class Serie:
    """Uma tabela: de que fonte e arquivo vem, como se lê e o que, mudando, faz linha nova."""

    nome: str  # a chave no resumo da montagem
    fonte: str
    url_termina_em: str | None
    tabela: str
    arquivo: str
    ler: Leitor
    colunas: list[str]
    valores: list[str]
    datas: list[str]


SERIES = (
    Serie(
        ARQUIVO_DO_PR,
        FONTE_DO_PR,
        None,
        TABELA_DO_PR,
        ARQUIVO_DO_PR,
        ler_pr,
        COLUNAS,
        VALORES,
        DATAS,
    ),
    Serie(
        "mg_divida_ativa",
        FONTE_DE_MG,
        coleta.ARQUIVO_DAS_CDAS_DE_MG,
        TABELA_DAS_CDAS_DE_MG,
        "divida_ativa",
        ler_cdas_de_mg,
        COLUNAS_DAS_CDAS_DE_MG,
        ["saldo_da_cda", "saldo_do_nucleo", "especie", "consta"],
        ["inscrito_em"],
    ),
    Serie(
        "mg_parcelamentos",
        FONTE_DE_MG,
        coleta.ARQUIVO_DOS_PARCELAMENTOS_DE_MG,
        TABELA_DOS_PARCELAMENTOS_DE_MG,
        "parcelamentos",
        ler_parcelamentos_de_mg,
        COLUNAS_DOS_PARCELAMENTOS_DE_MG,
        ["debito", "parcelas", "especie", "consta"],
        ["parcelado_em"],
    ),
)


def _disponivel_no_primeiro(novos: pd.DataFrame, dia: pd.Timestamp) -> pd.Series:
    """O dia do arquivo: a fonte não diz quando publicou cada débito."""
    return pd.Series(dia, index=novos.index)


@dataclass(frozen=True)
class _Montagem:
    """A tabela de uma série de retratos a gravar."""

    serie: Serie
    destino: Path
    achados: list[motor.Retrato]


def _origens(achados: list[motor.Retrato]) -> list[dict[str, str]]:
    return [{"url": r.url, "sha256": r.sha256} for r in achados]


def _montagens(conexao: sa.Connection, pasta: Path) -> Iterator[_Montagem]:
    for serie in SERIES:
        achados = motor.retratos(conexao, serie.fonte, serie.url_termina_em)
        if achados:
            yield _Montagem(serie, pasta / serie.tabela / serie.arquivo, achados)


def _como_numeros(pessoas: Collection[str] | np.ndarray) -> np.ndarray:
    if isinstance(pessoas, np.ndarray):
        return pessoas
    return cnpjs.ordenados(cnpjs.raizes_em_numeros(pd.Series(list(pessoas), dtype=str)))


def _para_gravar(
    tabela: pd.DataFrame, pessoas: np.ndarray, agora: datetime, serie: Serie
) -> pd.DataFrame:
    basico = tabela["cnpj_basico"].astype(str)
    return (
        tabela.assign(
            trata_como_pessoa=cnpjs.contem(pessoas, cnpjs.raizes_em_numeros(basico))
            if len(tabela)
            else pd.Series(dtype=bool),
            **{
                c: pd.to_datetime(tabela[c]).dt.date
                for c in [*serie.datas, "visto_em", "disponivel_em"]
            },
            consta=tabela["consta"].astype(bool),
            montado_em=agora.isoformat(),
            versao_do_codigo=versao_do_codigo(),
        )[[*serie.colunas, *LINHAGEM]]
        .sort_values(ORDEM, kind="stable")
        .reset_index(drop=True)
    )


def _montar_uma(
    conexao: sa.Connection,
    montagem: _Montagem,
    agora: datetime,
    pessoas: Collection[str] | np.ndarray | None,
) -> dict[str, int]:
    serie = montagem.serie
    contagem: dict[str, int] = {}
    lidos = []
    for retrato in montagem.achados:
        tabela, contou = serie.ler(retrato.caminho)
        for chave, valor in contou.items():
            contagem[chave] = contagem.get(chave, 0) + valor
        lidos.append((retrato, tabela))
    tabela, pulados = motor.juntar(lidos, serie.valores, _disponivel_no_primeiro)
    if pessoas is None:
        raizes = cnpjs.ordenados(
            cnpjs.raizes_em_numeros(tabela["cnpj_basico"].drop_duplicates().astype(str))
        )
        de_pessoa = pessoas_pela_receita(conexao, raizes)
    else:
        de_pessoa = _como_numeros(pessoas)
    gravar_se_mudou(
        _para_gravar(tabela, de_pessoa, agora, serie),
        montagem.destino,
        _origens(montagem.achados),
        ORDEM,
        carimbos=LINHAGEM,
    )
    return {
        **contagem,
        "retratos": len(montagem.achados),
        "retratos_pulados": pulados,
        "na_tabela": len(tabela),
    }


def montar(
    conexao: sa.Connection,
    pasta: Path,
    agora: datetime,
    pessoas: Collection[str] | np.ndarray | None = None,
    refazer: bool = False,
) -> dict[str, dict[str, int]]:
    """As tabelas de `SERIES` em `<pasta>/<tabela>/<arquivo>.parquet`, com todos os retratos guardados.

    Sem arquivo novo desde a última montagem, a série é pulada (`refazer` relê mesmo assim, para
    código novo). `pessoas`: as raízes de pessoa já sabidas; sem elas, pergunta à Receita guardada.
    """
    resumo: dict[str, dict[str, int]] = {}
    for montagem in _montagens(conexao, pasta):
        nome = montagem.serie.nome
        if not refazer and origens_gravadas(montagem.destino) == _origens(
            montagem.achados
        ):
            resumo[nome] = JA_MONTADO
            continue
        resumo[nome] = _montar_uma(conexao, montagem, agora, pessoas)
    return resumo
