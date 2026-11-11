"""Entradas e saídas de sócio pessoa jurídica no quadro da Receita (linha 810, PR 2).

É o material da lista de compradores por setor: quem **entrou como sócio** de uma empresa, e quando. Não diz
que houve compra (holding de família, reorganização e aumento de capital também entram): isso só uma fonte
de aquisição diz (fato relevante, formulário de referência, CADE).

Lê o retrato vigente do QSA e as mudanças de cada mês (ADR 0106) e devolve uma linha por movimento:
- `entrou`: uma linha por entrada (empresa, sócio, `data_entrada`), no primeiro mês em que a base a viu (o
  primeiro mês da base para quem já estava lá);
- `saiu`: uma linha por saída, no mês em que ela apareceu.

Três regras:
- **sem pessoa:** só sócio do tipo 1 e só raízes da lista sem pessoa do CNPJ (`cnpj_estabelecimentos_pj`:
  fora MEI, empresário individual e grupo 4, mesmo com CNPJ), dos dois lados; na dúvida, fora;
- **sem olhar o futuro:** cada linha depende só dos meses até o dela, então montar até M é o mesmo que
  montar tudo e cortar em M;
- **sem movimento fantasma:** sair e entrar com os mesmos dados no mesmo mês não é movimento (a troca de
  layout de 2024-09 fez isso com mais de 100 mil sócios PJ).
"""

from collections.abc import Collection

import pandas as pd

from base.receita_diff import ENTROU, MUDOU, SAIU, TIPO_PESSOA_JURIDICA, disponivel_em

TABELA = "entradas_de_socio_pj"
EMPRESA, SOCIO, ENTRADA = "cnpj_basico", "raiz_socio_pj", "data_entrada"
IDENTIDADE = [
    EMPRESA,
    SOCIO,
    ENTRADA,
]  # uma entrada: quem, onde e a data que a Receita dá
MES, QUALIFICACAO = "mes_do_retrato", "qualificacao"
COLUNAS = ["movimento", *IDENTIDADE, QUALIFICACAO, MES, "disponivel_em"]
# no mesmo mês, a prova de que já estava (saiu ou mudou) vem antes da entrada
_JA_ESTAVA, _ENTRADA = 0, 1
_DEPOIS_DE_TODO_MES = (
    "9999-12"  # o vigente sem mudança só vale quando não há notícia mais antiga
)


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
            ENTRADA: escolhidas[f"{ENTRADA}_{lado}"],
            QUALIFICACAO: escolhidas[f"{QUALIFICACAO}_{lado}"],
        }
    )


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


def _primeira_aparicao(
    vigente: pd.DataFrame,
    entradas: pd.DataFrame,
    provas: pd.DataFrame,
    primeiro_mes: str,
) -> pd.DataFrame:
    """Uma linha por entrada, com o mês em que a base a viu: o da mudança `entrou`, ou o primeiro mês da
    base quando a primeira notícia dela é que já estava lá (saiu, mudou ou está no vigente sem mudança)."""
    vistas = pd.concat(
        [
            entradas.assign(_prioridade=_ENTRADA),
            provas.assign(_prioridade=_JA_ESTAVA),
            vigente.assign(**{MES: _DEPOIS_DE_TODO_MES, "_prioridade": _JA_ESTAVA}),
        ],
        ignore_index=True,
    )
    vistas = vistas.sort_values(
        [MES, "_prioridade", QUALIFICACAO], kind="stable", na_position="last"
    )
    primeiras = vistas.drop_duplicates(IDENTIDADE, keep="first").copy()
    primeiras.loc[primeiras["_prioridade"] == _JA_ESTAVA, MES] = primeiro_mes
    return primeiras.assign(movimento=ENTROU)


def entradas_e_saidas(
    vigente: pd.DataFrame,
    mudancas: pd.DataFrame,
    primeiro_mes: str,
    pessoas_juridicas: Collection[str],
) -> pd.DataFrame:
    """As entradas e saídas de sócio PJ entre raízes de `pessoas_juridicas` (as colunas de `COLUNAS`).

    `vigente` é o QSA do último mês de `mudancas`; `primeiro_mes` (AAAA-MM) é o do retrato inicial da base.
    """
    atual = _so_pessoa_juridica(vigente)[[*IDENTIDADE, QUALIFICACAO]]
    pj = _so_pessoa_juridica(mudancas)
    entradas, saidas = _sem_fantasmas(
        _lado(pj, [ENTROU], "depois"), _lado(pj, [SAIU], "antes")
    )
    provas = pd.concat([saidas, _lado(pj, [MUDOU], "antes")], ignore_index=True)
    # a data de entrada corrigida (mudou) só existe dali em diante: conta como vista naquele mês
    corrigidas = _lado(pj, [MUDOU], "depois")
    aparicoes = _primeira_aparicao(
        atual,
        pd.concat([entradas, corrigidas], ignore_index=True),
        provas,
        primeiro_mes,
    )
    saidas = saidas.assign(movimento=SAIU).drop_duplicates([MES, *IDENTIDADE])
    tabela = pd.concat([aparicoes, saidas], ignore_index=True)
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
