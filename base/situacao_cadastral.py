"""B-30c: situação cadastral do CNPJ (ativa, baixada, inapta, suspensa, nula), só de pessoa jurídica, com histórico.

A Receita só publica o retrato do mês. A base do CNPJ (`scripts/carga_receita_mes.py`) guarda o retrato vigente
e as mudanças de cada mês desde 2023-05; daqui sai uma linha por versão de cada estabelecimento (linha 841),
como o histórico do Simples (`base/cnpj_historico.py`):

- `mes_do_retrato`: o mês da Receita em que a versão apareceu; `disponivel_em`: desde quando era pública;
- `consta`: falso quando o estabelecimento saiu do arquivo naquele mês (os campos vêm vazios);
- a situação, a data e o motivo, como a Receita os publicou.

A versão que vale em D é a última com `disponivel_em <= D` (nunca o mês do arquivo, que olharia o futuro). Uma
versão só nasce quando um destes campos muda (mudança de telefone ou endereço não conta): guardar o retrato
inteiro de cada mês daria quase um bilhão de linhas.

**Sem pessoa:** só entram os estabelecimentos das raízes da lista sem pessoa do CNPJ (`cnpj_estabelecimentos_pj`,
de `scripts/montar_empresas_pj.py`: fora MEI, empresário individual e grupo 4), a do mês do retrato vigente.
Como nas entradas de sócio PJ, quem hoje não é só empresa some da história inteira. Nome fantasia, razão social,
endereço e contatos nem são lidos (ADR 0106).
"""

from collections.abc import Collection, Mapping

import pandas as pd

from base import cnpj_historico as historico

TABELA = "cnpj_situacao_cadastral"
# a lista sem pessoa de `scripts/montar_empresas_pj.py` (o mesmo nome lá; há teste que confere)
LISTA_SEM_PESSOA = "cnpj_estabelecimentos_pj"
CHAVE = ("cnpj",)
CAMPOS = (
    "cnpj_basico", "matriz", "situacao_cadastral", "data_situacao_cadastral", "motivo_situacao",
)  # fmt: skip
CODIGOS = ("situacao_cadastral", "motivo_situacao")
# as colunas que se leem das mudanças de estabelecimentos (o resto do arquivo nunca vira coluna)
COLUNAS_DAS_MUDANCAS = (
    "mes", "tipo", "cnpj", "ordem",
    *(f"{campo}{lado}" for campo in CAMPOS for lado in (historico.ANTES, historico.DEPOIS)),
)  # fmt: skip
COLUNAS = (
    "cnpj", *CAMPOS, historico.MES, historico.DISPONIVEL_EM, historico.CONSTA,
)  # fmt: skip
TAMANHO_DA_RAIZ = 8
TAMANHO_DO_CODIGO = 2  # a base guarda sem o zero à esquerda em alguns meses
# Retrato da Receita com defeito conhecido → o mês em que as mudanças dele passam a contar. O de estabelecimentos
# de 2024-10 trouxe 4.634.796 CNPJs em dobro (a cópia com `ordem` 1) e deixou 3.054.993 de fora; em 2024-11 as
# mesmas 4.634.796 cópias saíram e os mesmos 3.054.993 voltaram (diagnóstico de 11/11/2026, todos os meses de
# estabelecimentos, Simples e QSA varridos: fora este, só o QSA de 2024-09, em `base/socios_pj.py`). Os SHA-256
# dos 10 zips do mês são distintos. Sem isto, a cópia que sai em 2024-11 parece o CNPJ saindo e o histórico não
# confere com o vigente. Os arquivos de mudanças ficam como a Receita publicou; só a leitura junta os dois meses.
# Só entra mês aqui com contagem assim: nenhuma regra geral sem evidência.
RETRATOS_COM_DEFEITO: Mapping[str, str] = {"2024-10": "2024-11"}


def da_raiz(cnpj: pd.Series) -> pd.Series:
    """A raiz (8 primeiros caracteres) de cada CNPJ de 14 caracteres."""
    return cnpj.astype(str).str[:TAMANHO_DA_RAIZ]


def so_das_raizes(tabela: pd.DataFrame, raizes: Collection[str]) -> pd.DataFrame:
    """As linhas cujo CNPJ é de uma das `raizes` (a lista sem pessoa)."""
    return tabela[da_raiz(tabela["cnpj"]).isin(set(raizes))].reset_index(drop=True)


def _codigo(serie: pd.Series) -> pd.Series:
    """O código de dois dígitos; vazio fica vazio."""
    texto = serie.astype("string").str.strip()
    return texto.where(texto.isna() | (texto == ""), texto.str.zfill(TAMANHO_DO_CODIGO))


def _formatado(cnpj: pd.Series) -> pd.Series:
    """`12.345.678/0001-90`, como as outras tabelas do CNPJ servidas pela porta."""
    texto = cnpj.astype(str)
    return (
        texto.str[:2] + "." + texto.str[2:5] + "." + texto.str[5:8] + "/"
        + texto.str[8:12] + "-" + texto.str[12:]
    )  # fmt: skip


def versoes(
    vigente: pd.DataFrame,
    mudancas: pd.DataFrame,
    primeiro_mes: str,
    raizes_pj: Collection[str],
    retratos_com_defeito: Mapping[str, str] = RETRATOS_COM_DEFEITO,
) -> pd.DataFrame:
    """As versões dos estabelecimentos das `raizes_pj`, do retrato vigente e das mudanças de todos os meses.

    As mudanças de um retrato com defeito (`RETRATOS_COM_DEFEITO`) contam no mês seguinte, juntas com as dele.
    A última versão de cada estabelecimento que consta tem de ser o vigente (`HistoricoNaoConfere` se não é).
    O ponto no tempo vale para todo mês que não é retrato com defeito: montar com o vigente do próprio retrato
    com defeito não é um ponto válido (é o arquivo errado).
    """
    vigente = so_das_raizes(vigente, raizes_pj)[[*CHAVE, *CAMPOS]]
    if not mudancas.empty:
        mudancas = historico.juntar_retratos_com_defeito(
            so_das_raizes(mudancas, raizes_pj), CHAVE, CAMPOS, retratos_com_defeito
        )
    feitas = historico.versoes_das_mudancas(
        vigente, mudancas, CHAVE, CAMPOS, primeiro_mes
    )
    historico.conferir_com_o_vigente(feitas, vigente, CHAVE, CAMPOS)
    return _sem_repeticao(_para_servir(feitas))


def _sem_repeticao(feitas: pd.DataFrame) -> pd.DataFrame:
    """Tira a versão igual à anterior do mesmo estabelecimento.

    A mudança de outro campo (telefone, endereço), ou o mesmo código escrito sem o zero à esquerda, não é
    versão nova da situação: vem depois de `_para_servir`, com os códigos e as datas já iguais. A
    versão que fica é a mais antiga, a desde quando aquele valor valia. As versões vêm ordenadas por CNPJ e mês.
    """
    valores = feitas[[*CAMPOS, historico.CONSTA]].astype("string").fillna("")
    mesmo_cnpj = feitas["cnpj"].eq(feitas["cnpj"].shift())
    igual = valores.eq(valores.shift()).all(axis=1)
    return feitas[~(mesmo_cnpj & igual)].reset_index(drop=True)


def _para_servir(feitas: pd.DataFrame) -> pd.DataFrame:
    """Raiz preenchida também na versão de quem saiu, códigos com dois dígitos, data sem hora e CNPJ formatado."""
    feitas = feitas.copy()
    feitas["cnpj_basico"] = da_raiz(feitas["cnpj"])
    for coluna in CODIGOS:
        feitas[coluna] = _codigo(feitas[coluna])
    feitas["data_situacao_cadastral"] = pd.to_datetime(
        feitas["data_situacao_cadastral"]
    ).dt.date
    feitas["matriz"] = feitas["matriz"].astype("boolean")
    feitas["cnpj"] = _formatado(feitas["cnpj"])
    return feitas[list(COLUNAS)]
