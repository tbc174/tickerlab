"""Entradas e saídas de sócio pessoa jurídica no quadro da Receita (linha 810, PR 2).

É o material da lista de compradores por setor: quem **entrou como sócio** de uma empresa, e quando. Não diz
que houve compra (holding de família, reorganização e aumento de capital também entram): isso só uma fonte
de aquisição diz (fato relevante, formulário de referência, CADE).

Lê o retrato vigente do QSA e as mudanças de cada mês (ADR 0106) e devolve uma linha por movimento:
- `entrou`: uma linha por entrada (empresa, sócio, `data_entrada`) no mês em que a base a viu, inclusive a volta
  de quem tinha saído; para quem já estava lá antes de a base começar, o primeiro mês da base;
- `saiu`: uma linha por saída, no mês em que ela apareceu;
- `data_corrigida`: a Receita trocou a data de entrada de um sócio que continuou (não é entrada nova).

Três regras:
- **sem pessoa:** só sócio do tipo 1 e só raízes da lista sem pessoa do CNPJ (`cnpj_estabelecimentos_pj`:
  fora MEI, empresário individual e grupo 4, mesmo com CNPJ), dos dois lados; na dúvida, fora;
- **sem olhar o futuro:** com a mesma lista sem pessoa, cada linha depende só dos meses até o dela, então
  montar até M é o mesmo que montar tudo e cortar em M. A lista é a do mês mais recente (só ela existe): uma
  raiz que deixou de ser só empresa some da história inteira, porque a privacidade vem antes do ponto no
  tempo;
- **sem movimento fantasma:** sair e entrar com os mesmos dados no mesmo mês não é movimento; e as mudanças de
  um retrato com defeito conhecido (`RETRATOS_COM_DEFEITO`) passam para o mês seguinte, como se a base
  comparasse o seguinte direto com o anterior.

O ponto no tempo vale para todo mês que não é retrato com defeito: montar com o vigente do próprio retrato com
defeito não é um ponto válido (é o arquivo errado).
"""

from collections.abc import Collection, Mapping

import pandas as pd

from base.receita_diff import ENTROU, MUDOU, SAIU, TIPO_PESSOA_JURIDICA, disponivel_em

DATA_CORRIGIDA = "data_corrigida"

TABELA = "entradas_de_socio_pj"
EMPRESA, SOCIO, ENTRADA = "cnpj_basico", "raiz_socio_pj", "data_entrada"
IDENTIDADE = [
    EMPRESA,
    SOCIO,
    ENTRADA,
]  # uma entrada: quem, onde e a data que a Receita dá
MES, QUALIFICACAO = "mes_do_retrato", "qualificacao"
COLUNAS = ["movimento", *IDENTIDADE, QUALIFICACAO, MES, "disponivel_em"]
# no mesmo mês, a prova de que já estava (saiu ou mudou) vem antes da notícia nova (entrou ou data corrigida)
_JA_ESTAVA, _NOVA = 0, 1
_DEPOIS_DE_TODO_MES = (
    "9999-12"  # o vigente sem mudança só vale quando não há notícia mais antiga
)
# Retrato da Receita com defeito conhecido → o mês em que as mudanças dele passam a contar. O de 2024-09 tirou
# uns 115 mil sócios PJ que voltaram em 2024-10 com a mesma data de entrada e pôs uns 113 mil que só existem
# nele (116.055 das 116.116 voltas com a mesma data da base inteira; ensaio de 11/11/2026). Comparar 2024-10
# direto com 2024-08 desfaz os dois; o que mudou de verdade aparece em 2024-10, com o piso de publicação dele.
# Só entra mês aqui com contagem assim: nenhuma regra geral sem evidência.
RETRATOS_COM_DEFEITO: Mapping[str, str] = {"2024-09": "2024-10"}


def _so_pessoa_juridica(socios: pd.DataFrame) -> pd.DataFrame:
    raiz = socios[SOCIO].fillna("")
    return socios[(socios["tipo_socio"] == TIPO_PESSOA_JURIDICA) & (raiz != "")]


def _lado(mudancas: pd.DataFrame, tipos: Collection[str], lado: str) -> pd.DataFrame:
    """As mudanças dos `tipos` com os valores de um `lado` (`antes` ou `depois`) nas colunas de sempre."""
    escolhidas = mudancas[mudancas["tipo"].isin(tipos)]
    return pd.DataFrame(
        {
            "tipo": escolhidas["tipo"],
            MES: escolhidas["mes"],
            EMPRESA: escolhidas[EMPRESA],
            SOCIO: escolhidas[SOCIO],
            # data sempre como data: um lado vazio lido como texto quebraria a junção dos fantasmas
            ENTRADA: pd.to_datetime(escolhidas[f"{ENTRADA}_{lado}"]),
            QUALIFICACAO: escolhidas[f"{QUALIFICACAO}_{lado}"],
        }
    )


def _sem_retratos_com_defeito(
    mudancas: pd.DataFrame, retratos_com_defeito: Mapping[str, str]
) -> pd.DataFrame:
    """As mudanças de um retrato com defeito passam para o mês seguinte: lá, quem saiu e voltou (ou entrou e
    saiu) com os mesmos dados vira par fantasma do mesmo mês e some; o resto conta naquele mês."""
    return mudancas.assign(mes=mudancas["mes"].replace(dict(retratos_com_defeito)))


def _sem_fantasmas(
    entradas: pd.DataFrame, saidas: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Tira a saída e a entrada da mesma identidade no mesmo mês: o sócio não se mexeu."""
    ligacao = [MES, *IDENTIDADE]
    pares = entradas[ligacao].merge(saidas[ligacao]).drop_duplicates()

    def sem_os_pares(tabela: pd.DataFrame) -> pd.DataFrame:
        marcada = tabela.merge(pares, on=ligacao, how="left", indicator=True)
        return marcada[marcada["_merge"] == "left_only"].drop(columns="_merge")

    return sem_os_pares(entradas), sem_os_pares(saidas)


def _ja_estavam(
    vigente: pd.DataFrame,
    novas: pd.DataFrame,
    provas: pd.DataFrame,
    primeiro_mes: str,
) -> pd.DataFrame:
    """As entradas cuja primeira notícia é que já estavam lá (saíram, mudaram ou estão no vigente sem mudança
    nenhuma): `entrou` no primeiro mês da base. As que a base viu chegar (`novas`) não entram aqui."""
    vistas = pd.concat(
        [
            novas.assign(_prioridade=_NOVA),
            provas.assign(_prioridade=_JA_ESTAVA),
            vigente.assign(**{MES: _DEPOIS_DE_TODO_MES, "_prioridade": _JA_ESTAVA}),
        ],
        ignore_index=True,
    )
    vistas = vistas.sort_values(
        [MES, "_prioridade", QUALIFICACAO], kind="stable", na_position="last"
    )
    primeiras = vistas.drop_duplicates(IDENTIDADE, keep="first")
    ja_estavam = primeiras[primeiras["_prioridade"] == _JA_ESTAVA]
    return ja_estavam.assign(**{MES: primeiro_mes, "movimento": ENTROU})


def _so_as_datas_trocadas(antes: pd.DataFrame, depois: pd.DataFrame) -> pd.DataFrame:
    """O lado de depois das mudanças que trocaram a data de entrada (as outras só mudaram a qualificação)."""
    trocou = antes[ENTRADA].ne(depois[ENTRADA]) & ~(
        antes[ENTRADA].isna() & depois[ENTRADA].isna()
    )
    return depois[trocou]


def entradas_e_saidas(
    vigente: pd.DataFrame,
    mudancas: pd.DataFrame,
    primeiro_mes: str,
    pessoas_juridicas: Collection[str],
    retratos_com_defeito: Mapping[str, str] = RETRATOS_COM_DEFEITO,
) -> pd.DataFrame:
    """As entradas e saídas de sócio PJ entre raízes de `pessoas_juridicas` (as colunas de `COLUNAS`).

    `vigente` é o QSA do último mês de `mudancas`; `primeiro_mes` (AAAA-MM) é o do retrato inicial da base.
    """
    atual = _so_pessoa_juridica(vigente)[[*IDENTIDADE, QUALIFICACAO]]
    pj = _sem_retratos_com_defeito(_so_pessoa_juridica(mudancas), retratos_com_defeito)
    entradas, saidas = _sem_fantasmas(
        _lado(pj, [ENTROU], "depois"), _lado(pj, [SAIU], "antes")
    )
    mudaram = _lado(pj, [MUDOU], "antes")
    corrigidas = _so_as_datas_trocadas(mudaram, _lado(pj, [MUDOU], "depois"))
    # a data corrigida só existe dali em diante: é notícia nova naquele mês, não prova de que já estava
    ja_estavam = _ja_estavam(
        atual,
        pd.concat([entradas, corrigidas], ignore_index=True),
        pd.concat([saidas, mudaram], ignore_index=True),
        primeiro_mes,
    )
    tabela = pd.concat(
        [
            ja_estavam,
            entradas.assign(movimento=ENTROU),
            corrigidas.assign(movimento=DATA_CORRIGIDA),
            saidas.assign(movimento=SAIU),
        ],
        ignore_index=True,
    ).drop_duplicates(["movimento", MES, *IDENTIDADE])
    lista = set(pessoas_juridicas)
    tabela = tabela[tabela[EMPRESA].isin(lista) & tabela[SOCIO].isin(lista)]
    tabela = tabela.assign(
        disponivel_em=tabela[MES].map(lambda mes: pd.Timestamp(disponivel_em(mes)))
    )
    return (
        tabela[COLUNAS]
        .sort_values([EMPRESA, SOCIO, MES, "movimento"], kind="stable")
        .reset_index(drop=True)
    )
