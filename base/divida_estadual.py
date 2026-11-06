"""Dívida ativa estadual por CNPJ (linha 755 da fila; motor de risco cedente/sacado, linha 754).

A tabela `sefa_pr_divida_ativa`: os débitos inscritos em dívida ativa no Paraná (Sefa-PR), de
pessoa jurídica, a partir dos ZIPs diários que o arquivista guarda (`base/arquivo/lote_divida_estadual.py`).
Minas Gerais entra em PR seguinte, na mesma família de módulo.

- **Um retrato por dia, uma série só:** o endereço do ZIP muda todo dia, então todos os arquivos
  guardados formam uma série só (o motor de `base/retratos.py`). Débito novo, ou com valor ou situação
  diferente, vira linha nova desde o dia em que foi visto; débito que some do arquivo (pago, cancelado,
  prescrito) ganha `consta` falso nesse dia. Esse "sumiu" é o sinal de que o devedor quitou, mas a
  fonte não diz o motivo.
- **Só pessoa jurídica (ADR 0075 e 0088):** a coleta já tirou o CPF, o nome e a razão social; aqui o CNPJ
  se confere de novo. Empresário individual e MEI não se distinguem no arquivo (não há natureza
  jurídica), então ficam com `trata_como_pessoa` pela Receita guardada.
- **Sem olhar o futuro** (`disponivel_em`): o dia em que o TickerLab viu a linha. A data da inscrição
  (`inscrito_em`, às vezes de 1973) conta quando o débito nasceu, nunca quando a base soube.
- **Identidade do débito:** o número da dívida ativa, o CNPJ e o tipo do crédito juntos (o número
  sozinho se repete entre devedores e tipos).

Limites conhecidos: a fonte não dá o nome do devedor, a natureza do débito além do tipo do crédito,
nem o motivo de o débito sair; a licença é "a confirmar" (ADR 0102, Emenda 2).
"""

from collections.abc import Collection, Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import sqlalchemy as sa

from base import cnpj as cnpjs
from base import retratos as motor
from base.parquet import LINHAGEM, gravar_se_mudou, origens_gravadas
from base.pgfn import pessoas_pela_receita
from src.versao_do_codigo import versao_do_codigo

SEPARADOR = ";"  # a coleta grava todo CSV com ";"
UTF8 = "utf-8"
FORMATO_DA_DATA = "%d/%m/%Y"  # a fonte escreve "18/06/1973"
SIM = "Sim"
JA_MONTADO = {"ja_montado": 1}  # no resumo: nenhum arquivo novo desde a última montagem

FONTE_DO_PR = "sefapr-divida-ativa"
TABELA_DO_PR = "sefa_pr_divida_ativa"
ARQUIVO_DO_PR = "divida_ativa"
ORDEM = ["id_na_fonte", "visto_em"]

# do nome da coluna na fonte (`lote_divida_estadual.COLUNAS_GUARDADAS_NO_PR`) para o nosso
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
COLUNAS = [
    "id_na_fonte",
    "cnpj",
    "cnpj_basico",
    "divida_ativa",
    "tipo_do_credito",
    "inscrito_em",
    "atualizado_em",
    *VALORES_EM_REAIS,
    "suspensao",
    *SIM_OU_NAO,
    *_CARIMBOS,
]


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


def _data(texto: pd.Series) -> pd.Series:
    """ "18/06/1973" em data; vazio e data impossível ficam nulos."""
    return pd.to_datetime(texto, format=FORMATO_DA_DATA, errors="coerce")


def ler_pr(caminho: Path) -> tuple[pd.DataFrame, dict[str, int]]:
    """Os débitos de CNPJ inteiro de um retrato do Paraná e a contagem do que ficou de fora."""
    bruta = _abrir_csv(caminho)
    nossas = pd.DataFrame(
        {c: bruta.get(f, pd.Series("", index=bruta.index)) for c, f in _PR.items()}
    )
    completo = nossas["cnpj"].map(cnpjs.completo)
    valido = completo.map(lambda c: isinstance(c, str) and cnpjs.dv_confere(c)).astype(
        bool
    )
    nossas = nossas[valido.to_numpy()].assign(cnpj=completo[valido])
    nossas["id_na_fonte"] = motor.chave(nossas, CHAVE)
    repetido = nossas["id_na_fonte"].duplicated(keep="first")
    nossas = nossas[~repetido]
    pronta = pd.DataFrame(
        {
            "id_na_fonte": nossas["id_na_fonte"],
            "cnpj": nossas["cnpj"].map(cnpjs.formatar),
            "cnpj_basico": nossas["cnpj"].str[: cnpjs.TAMANHO_DA_RAIZ],
            "divida_ativa": motor.sem_vazio(nossas["divida_ativa"]),
            "tipo_do_credito": motor.sem_vazio(nossas["tipo_do_credito"]),
            **{c: _data(nossas[c]) for c in DATAS},
            **{
                c: pd.to_numeric(nossas[c], errors="coerce")  # ponto decimal, "1787.10"
                for c in VALORES_EM_REAIS
            },
            "suspensao": motor.sem_vazio(
                nossas["suspensao"].where(~nossas["suspensao"].str.fullmatch("N[ãa]o"))
            ),  # "Não" é a ausência de suspensão
            "com_garantia": nossas["garantia"].eq(SIM),
            "com_parcelamento_ativo": nossas["parcelamento"].eq(SIM),
        }
    ).reset_index(drop=True)
    contagem = {
        "linhas": len(bruta),
        "cnpj_invalido": int((~valido).sum()),
        "id_repetido": int(repetido.sum()),
    }
    return pronta, contagem


def _disponivel_no_primeiro(novos: pd.DataFrame, dia: pd.Timestamp) -> pd.Series:
    """O dia do arquivo: a fonte não diz quando publicou cada débito."""
    return pd.Series(dia, index=novos.index)


@dataclass(frozen=True)
class _Montagem:
    """A tabela de uma série de retratos a gravar."""

    destino: Path
    achados: list[motor.Retrato]


def _origens(achados: list[motor.Retrato]) -> list[dict[str, str]]:
    return [{"url": r.url, "sha256": r.sha256} for r in achados]


def _montagens(conexao: sa.Connection, pasta: Path) -> Iterator[tuple[str, _Montagem]]:
    achados = motor.retratos(conexao, FONTE_DO_PR)
    if achados:
        yield ARQUIVO_DO_PR, _Montagem(pasta / TABELA_DO_PR / ARQUIVO_DO_PR, achados)


def _como_numeros(pessoas: Collection[str] | np.ndarray) -> np.ndarray:
    if isinstance(pessoas, np.ndarray):
        return pessoas
    return cnpjs.ordenados(cnpjs.raizes_em_numeros(pd.Series(list(pessoas), dtype=str)))


def _para_gravar(
    tabela: pd.DataFrame, pessoas: np.ndarray, agora: datetime
) -> pd.DataFrame:
    basico = tabela["cnpj_basico"].astype(str)
    return (
        tabela.assign(
            trata_como_pessoa=cnpjs.contem(pessoas, cnpjs.raizes_em_numeros(basico))
            if len(tabela)
            else pd.Series(dtype=bool),
            **{
                c: pd.to_datetime(tabela[c]).dt.date
                for c in [*DATAS, "visto_em", "disponivel_em"]
            },
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
    """`<pasta>/sefa_pr_divida_ativa/divida_ativa.parquet` com todos os retratos guardados.

    Sem arquivo novo desde a última montagem, é pulado (`refazer` relê mesmo assim, para código
    novo). `pessoas`: as raízes de pessoa já sabidas; sem elas, pergunta à Receita guardada.
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
            tabela, contou = ler_pr(retrato.caminho)
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
