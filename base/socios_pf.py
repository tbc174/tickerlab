"""Contagem sem identificação dos movimentos mensais de sócios PF (linha 1104).

O QSA já pseudonimizado é lido em memória. Desfazendo as diferenças mensais,
recuperamos a quantidade de linhas por chave em cada retrato; só a presença da
chave conta como pessoa. Assim uma duplicata ou troca de qualificação não vira
entrada nem saída. Nenhum identificador individual faz parte da saída.
"""

from collections import Counter
from collections.abc import Collection, Sequence

import pandas as pd

from base.receita_diff import ENTROU, MES, SAIU, disponivel_em

TABELA = "movimento_de_socios_pf"
EMPRESA = "cnpj_basico"
RETRATO = "mes_do_retrato"
TIPO_PESSOA_FISICA = "2"
CHAVE = [EMPRESA, "id_pessoa"]
CONTAGENS = ["socios_pf_entraram", "socios_pf_sairam", "socios_pf_no_fim"]
COLUNAS = [
    EMPRESA,
    RETRATO,
    *CONTAGENS,
    "tem_retrato_anterior",
    "fonte",
    "disponivel_em",
]
FONTE = "Receita Federal, dados abertos do CNPJ"


def conferir_meses(meses: Sequence[str]) -> None:
    """Recusa série vazia, fora de ordem ou com lacunas que impedem a comparação mensal."""
    if not meses or any(not MES.fullmatch(m) for m in meses):
        raise ValueError("meses inválidos no manifesto")
    esperados = pd.period_range(meses[0], meses[-1], freq="M").astype(str).tolist()
    if list(meses) != esperados:
        raise ValueError("os retratos devem ser meses consecutivos e ordenados")


def _filtrar(tabela: pd.DataFrame, raizes: Collection[str]) -> pd.DataFrame:
    fisicas = tabela.loc[
        tabela[EMPRESA].isin(raizes) & tabela["tipo_socio"].eq(TIPO_PESSOA_FISICA)
    ]
    return fisicas.assign(id_pessoa=fisicas["id_pessoa"].fillna("").str.strip())


def _chaves(tabela: pd.DataFrame) -> Counter:
    return Counter(tabela[CHAVE].itertuples(index=False, name=None))


def _anterior(estado: Counter, mudancas: pd.DataFrame) -> Counter:
    anterior = estado.copy()
    anterior.subtract(_chaves(mudancas[mudancas.tipo == ENTROU]))
    anterior.update(_chaves(mudancas[mudancas.tipo == SAIU]))
    if any(n < 0 for n in anterior.values()):
        raise ValueError("QSA e mudanças inconsistentes; contagem interrompida")
    return +anterior


def _contar(antes: set, depois: set, mes: str, comparavel: bool) -> list[dict]:
    # Uma chave apagada ou ausente não identifica uma pessoa. Omitir a comparação
    # inteira da raiz evita publicar zero ou uma contagem parcial como se fosse exata.
    incompletas = {raiz for raiz, pessoa in antes | depois if not pessoa}
    entradas = Counter(raiz for raiz, _ in depois - antes) if comparavel else Counter()
    saidas = Counter(raiz for raiz, _ in antes - depois) if comparavel else Counter()
    saldo = Counter(raiz for raiz, _ in depois)
    return [
        {
            EMPRESA: raiz,
            RETRATO: mes,
            CONTAGENS[0]: entradas[raiz],
            CONTAGENS[1]: saidas[raiz],
            CONTAGENS[2]: saldo[raiz],
            "tem_retrato_anterior": comparavel,
            "fonte": FONTE,
            "disponivel_em": pd.Timestamp(disponivel_em(mes)),
        }
        for raiz in sorted({r for r, _ in antes | depois} - incompletas)
    ]


def contar_movimentos(
    vigente: pd.DataFrame,
    mudancas: pd.DataFrame,
    meses: Sequence[str],
    pessoas_juridicas: Collection[str],
) -> pd.DataFrame:
    """Conta PF distintas por raiz e mês, só nas empresas da lista sem pessoa.

    O primeiro mês tem saldo, movimentos zero e `tem_retrato_anterior=False`:
    não sabemos quando entraram. Linha existe se havia PF em algum dos dois
    retratos, com todas as chaves preenchidas. Uma chave vazia omite a comparação
    inteira da empresa naquele mês. Mudanças só de atributos não contam;
    tipo 3 (estrangeiro) fica fora.
    A lista de empresas é a vigente, como no molde PJ: privacidade antes do PIT.
    """
    conferir_meses(meses)
    estado = _chaves(_filtrar(vigente, pessoas_juridicas))
    mudancas = _filtrar(mudancas, pessoas_juridicas)
    if not mudancas["mes"].isin(meses[1:]).all():
        raise ValueError("mudanças fora dos meses comparáveis do manifesto")
    if not mudancas["tipo"].isin([ENTROU, SAIU, "mudou"]).all():
        raise ValueError("tipo de mudança desconhecido")
    linhas = []
    for mes in reversed(meses):
        comparavel = mes != meses[0]
        anterior = (
            _anterior(estado, mudancas[mudancas.mes == mes]) if comparavel else estado
        )
        linhas.extend(_contar(set(anterior), set(estado), mes, comparavel))
        estado = anterior
    tabela = pd.DataFrame(linhas, columns=COLUNAS)
    tabela = tabela.astype(
        {**dict.fromkeys(CONTAGENS, "int64"), "tem_retrato_anterior": "bool"}
    )
    tabela["disponivel_em"] = pd.to_datetime(tabela["disponivel_em"])
    return tabela.sort_values([EMPRESA, RETRATO]).reset_index(drop=True)
