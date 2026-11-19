"""Histórico datado do CNPJ (linha 686 da fila): cada versão de um cadastro, com desde quando era pública.

O CNPJ da base (`scripts/carga_receita_mes.py`) guarda o retrato vigente e as mudanças de cada mês. Para
servir um campo "como era em D" sem mostrar o futuro, cada valor precisa da data em que ficou público. Aqui
cada chave (a raiz do CNPJ) ganha uma linha por versão:

- `mes_do_retrato`: o mês da Receita em que a versão apareceu (`AAAA-MM`);
- `disponivel_em`: desde quando aquele retrato era público (`receita_diff.disponivel_em`, o piso combinado);
- `consta`: falso quando a chave saiu do arquivo naquele mês (os campos vêm vazios);
- os campos da tabela, como a Receita os publicou naquele mês.

Uma versão só nasce quando algum campo muda: a versão que vale em D é a última com `disponivel_em <= D`.
Um mês novo só acrescenta linhas; as versões antigas nunca mudam (cortar o futuro não muda o passado).

Duas tabelas saem daqui:
- `cnpj_simples_historico`: opção pelo Simples e pelo MEI, montada do vigente e das mudanças que a base já
  tem (`versoes_das_mudancas`);
- `cnpj_empresas_historico`: natureza jurídica e razão social, montada mês a mês dos `Empresas*.zip`
  (`acrescentar_retrato`). **A razão social de pessoa nunca entra:** a do empresário individual e a do MEI
  (natureza 213-5) e a do grupo 4 (pessoas físicas) trazem o nome e o CPF da pessoa (ADR 0106); nas outras,
  o CPF que aparecer no texto sai (`base.pessoas.sem_cpf`). Capital, porte, qualificação do responsável e
  ente federativo não são lidos.
"""

import zipfile
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import IO

import numpy as np
import pandas as pd

from base.pessoas.sem_cpf import tirar_cpf_da_coluna
from base.receita_diff import ENTROU, MUDOU, ORDEM, SAIU, disponivel_em
from base.receita_retrato import CODIFICACAO, TAMANHO_DA_PARTE, _conferir_campos
from base.rede.entidades import natureza_de_pessoa

MES = "mes_do_retrato"
DISPONIVEL_EM = "disponivel_em"
CONSTA = "consta"
CHAVE = ("cnpj_basico",)
CAMPOS_DO_SIMPLES = (
    "optante_simples", "data_opcao_simples", "data_exclusao_simples",
    "optante_mei", "data_opcao_mei", "data_exclusao_mei",
)  # fmt: skip
CAMPOS_DA_EMPRESA = ("natureza_juridica", "razao_social")
CAMPOS_NO_ARQUIVO_DE_EMPRESAS = (
    7  # básico; razão social; natureza; qualificação; capital; porte; ente
)
EMPRESA = {0: "cnpj_basico", 1: "razao_social", 2: "natureza_juridica"}
ANTES, DEPOIS = "_antes", "_depois"


class HistoricoNaoConfere(ValueError):
    """A última versão de cada chave não é o retrato vigente: falta mês ou sobra mudança."""


def _versoes(
    chaves: pd.DataFrame, campos: pd.DataFrame, meses: pd.Series, consta: pd.Series
) -> pd.DataFrame:
    tabela = pd.concat(
        [chaves.reset_index(drop=True), campos.reset_index(drop=True)], axis=1
    )
    tabela.insert(len(chaves.columns), MES, meses.to_numpy())
    tabela.insert(len(chaves.columns) + 1, CONSTA, consta.to_numpy())
    return tabela


def _no_mes(mes: str, linhas: int) -> pd.Series:
    return pd.Series([mes] * linhas, dtype=object)


def _todas(linhas: int) -> pd.Series:
    return pd.Series([True] * linhas, dtype=bool)


def _com_disponivel_em(versoes: pd.DataFrame) -> pd.DataFrame:
    datas = {mes: disponivel_em(mes) for mes in versoes[MES].unique()}
    versoes.insert(
        versoes.columns.get_loc(MES) + 1,  # type: ignore[operator]
        DISPONIVEL_EM,
        versoes[MES].map(datas),
    )
    return versoes


def _ordenar(versoes: pd.DataFrame, chave: Sequence[str]) -> pd.DataFrame:
    return versoes.sort_values([*chave, MES], kind="stable").reset_index(drop=True)


def _de(mudancas: pd.DataFrame, campos: Sequence[str], sufixo: str) -> pd.DataFrame:
    return mudancas[[f"{c}{sufixo}" for c in campos]].set_axis(list(campos), axis=1)


def versoes_das_mudancas(
    vigente: pd.DataFrame,
    mudancas: pd.DataFrame,
    chave: Sequence[str],
    campos: Sequence[str],
    primeiro_mes: str,
) -> pd.DataFrame:
    """As versões de cada chave, do retrato vigente e das mudanças de todos os meses (`receita_diff`).

    A chave que já existia no primeiro mês ganha a versão daquele mês: o `_antes` da primeira mudança, ou o
    próprio vigente se nunca mudou. Cada mudança é uma versão do mês dela (o `_depois`; na saída, `consta`
    falso). Duas mudanças da mesma chave num mês (`ordem`) valem pela última.
    """
    chave = list(chave)
    if mudancas.empty:
        mudancas = pd.DataFrame(
            columns=["mes", "tipo", *chave, "ordem"]
            + [f"{c}{s}" for c in campos for s in (ANTES, DEPOIS)]
        )
    ordenadas = mudancas.sort_values([*chave, "mes", "ordem"], kind="stable")
    ordenadas = ordenadas.drop_duplicates([*chave, "mes"], keep="last")
    primeiras = ordenadas.drop_duplicates(chave, keep="first")
    ja_existiam = primeiras[primeiras["tipo"].ne(ENTROU)]
    sem_mudanca = vigente.merge(primeiras[chave], on=chave, how="left", indicator=True)
    sem_mudanca = sem_mudanca[sem_mudanca["_merge"].eq("left_only")]
    if len(ordenadas) and ordenadas["mes"].min() <= primeiro_mes:
        raise ValueError(f"mudança no mês do retrato inicial ({primeiro_mes}) ou antes")
    partes = [
        _versoes(
            sem_mudanca[chave],
            sem_mudanca[list(campos)],
            _no_mes(primeiro_mes, len(sem_mudanca)),
            _todas(len(sem_mudanca)),
        ),
        _versoes(
            ja_existiam[chave],
            _de(ja_existiam, campos, ANTES),
            _no_mes(primeiro_mes, len(ja_existiam)),
            _todas(len(ja_existiam)),
        ),
        _versoes(
            ordenadas[chave],
            _de(ordenadas, campos, DEPOIS),
            ordenadas["mes"].astype(object),
            ordenadas["tipo"].ne(SAIU),
        ),
    ]
    versoes = pd.concat([p for p in partes if len(p)] or partes[:1], ignore_index=True)
    return _com_disponivel_em(_ordenar(versoes, chave))


def juntar_retratos_com_defeito(
    mudancas: pd.DataFrame,
    chave: Sequence[str],
    campos: Sequence[str],
    retratos_com_defeito: Mapping[str, str],
) -> pd.DataFrame:
    """As mudanças de um retrato com defeito conhecido e as do mês seguinte viram uma só por linha do arquivo.

    Cada `retratos_com_defeito[defeito] = seguinte`: a linha (a `chave` com a `ordem` de `receita_diff`) fica com
    o lado de antes da primeira mudança e o de depois da última, no mês `seguinte`. É comparar o seguinte direto
    com o anterior ao defeito: a cópia em dobro que entrou e saiu some, a que faltou e voltou igual não se mexeu,
    a que voltou diferente mudou, e nada vale antes do piso de publicação do seguinte.
    """
    if mudancas.empty or not retratos_com_defeito:
        return mudancas
    seguinte = mudancas["mes"].replace(dict(retratos_com_defeito))
    no_seguinte = seguinte.isin(set(retratos_com_defeito.values()))
    if not no_seguinte.any():
        return mudancas
    linha = ["mes", *chave, ORDEM]
    juntas = (
        mudancas[no_seguinte]
        .assign(_original=mudancas["mes"], mes=seguinte)
        .sort_values([*linha, "_original"], kind="stable")
    )
    primeira = juntas.drop_duplicates(linha, keep="first").set_index(linha)
    ultima = juntas.drop_duplicates(linha, keep="last").set_index(linha)
    tinha, tem = primeira["tipo"].ne(ENTROU), ultima["tipo"].ne(SAIU)
    composta = pd.DataFrame(index=primeira.index)
    igual = pd.Series(True, index=composta.index)
    for campo in campos:
        antes = primeira[f"{campo}{ANTES}"].where(tinha)
        depois = ultima[f"{campo}{DEPOIS}"].where(tem)
        composta[f"{campo}{ANTES}"], composta[f"{campo}{DEPOIS}"] = antes, depois
        igual &= antes.eq(depois) | (antes.isna() & depois.isna())
    composta["tipo"] = SAIU
    composta.loc[tem, "tipo"] = ENTROU
    composta.loc[tinha & tem, "tipo"] = MUDOU
    composta = composta[(tinha | tem) & ~(tinha & tem & igual)]
    return pd.concat(
        [mudancas[~no_seguinte], composta.reset_index()], ignore_index=True
    )


def ultimas_versoes(versoes: pd.DataFrame, chave: Sequence[str]) -> pd.DataFrame:
    """A versão mais recente de cada chave (a que vale hoje)."""
    return _ordenar(versoes, chave).drop_duplicates(list(chave), keep="last")


def como_era_em(
    versoes: pd.DataFrame, chave: Sequence[str], data: object
) -> pd.DataFrame:
    """A versão de cada chave que valia em `data` (só as que constavam), sem nada publicado depois."""
    publicadas = versoes[pd.to_datetime(versoes[DISPONIVEL_EM]) <= pd.Timestamp(data)]  # type: ignore[arg-type]
    valendo = ultimas_versoes(publicadas, chave)
    return valendo[valendo[CONSTA].astype(bool)].reset_index(drop=True)


def _em_texto(tabela: pd.DataFrame) -> np.ndarray:
    return tabela.map(lambda x: None if pd.isna(x) else str(x)).to_numpy(dtype=object)


def _iguais(a: pd.DataFrame, b: pd.DataFrame) -> bool:
    """Mesmo conteúdo, com vazio igual a vazio, sem olhar o tipo exato de cada coluna.

    O vazio se confere à parte: no pandas 3 o `map` de `_em_texto` devolve coluna de texto, e o `None`
    volta como `nan`, que não é igual a si mesmo (uma data vazia no vigente não conferia consigo).
    """
    if a.shape != b.shape:
        return False
    x, y = _em_texto(a), _em_texto(b)
    vazio_x, vazio_y = pd.isna(x), pd.isna(y)
    return bool(((x == y) | (vazio_x & vazio_y)).all() and (vazio_x == vazio_y).all())


def conferir_com_o_vigente(
    versoes: pd.DataFrame,
    vigente: pd.DataFrame,
    chave: Sequence[str],
    campos: Sequence[str],
) -> None:
    """A última versão das chaves que constam é o vigente, linha por linha; senão `HistoricoNaoConfere`."""
    chave, colunas = list(chave), [*chave, *campos]
    ultimas = ultimas_versoes(versoes, chave)
    ultimas = ultimas[ultimas[CONSTA].astype(bool)][colunas]
    esperado = vigente[colunas].sort_values(chave).reset_index(drop=True)
    if not _iguais(ultimas.reset_index(drop=True), esperado):
        raise HistoricoNaoConfere(
            f"{len(ultimas)} chaves constam no histórico, {len(esperado)} no vigente, "
            "ou algum campo da última versão difere do vigente"
        )


def acrescentar_retrato(
    versoes: pd.DataFrame | None,
    retrato: pd.DataFrame,
    chave: Sequence[str],
    campos: Sequence[str],
    mes: str,
) -> pd.DataFrame:
    """As versões novas que o retrato do mês `mes` traz (só as linhas a acrescentar).

    Entra uma versão para a chave nova, para a que mudou algum campo e para a que saiu do arquivo
    (`consta` falso). Repetir um mês já acrescentado não traz nada; um mês anterior ao último é erro.
    """
    chave, campos = list(chave), list(campos)
    retrato = retrato[[*chave, *campos]].drop_duplicates(chave, keep="last")
    if versoes is None or versoes.empty:
        novas = _versoes(
            retrato[chave],
            retrato[campos],
            _no_mes(mes, len(retrato)),
            _todas(len(retrato)),
        )
        return _com_disponivel_em(_ordenar(novas, chave))
    if versoes[MES].max() > mes:
        raise ValueError(f"o histórico já vai até {versoes[MES].max()}; pedido {mes}")
    ultimas = ultimas_versoes(versoes, chave)
    juntas = ultimas[[*chave, CONSTA, *campos]].merge(
        retrato, on=chave, how="outer", suffixes=(ANTES, DEPOIS), indicator=True
    )
    antes, depois = _de(juntas, campos, ANTES), _de(juntas, campos, DEPOIS)
    mudou = ~(antes.eq(depois) | (antes.isna() & depois.isna())).all(axis=1)
    no_retrato = juntas["_merge"].ne("left_only")
    constava = juntas[CONSTA].eq(True)
    entrou_ou_mudou = no_retrato & (~constava | mudou)
    saiu = ~no_retrato & constava
    escolhidas = juntas[entrou_ou_mudou | saiu]
    campos_novos = _de(escolhidas, campos, DEPOIS)
    novas = _versoes(
        escolhidas[chave],
        campos_novos,
        _no_mes(mes, len(escolhidas)),
        escolhidas["_merge"].ne("left_only"),
    )
    return _com_disponivel_em(_ordenar(novas, chave))


def _empresas(parte: pd.DataFrame) -> pd.DataFrame:
    natureza = parte["natureza_juridica"].str.strip()
    pessoa = natureza.map(natureza_de_pessoa).astype(bool)
    razao = parte["razao_social"].str.strip().mask(pessoa)
    return pd.DataFrame(
        {
            "cnpj_basico": parte["cnpj_basico"].str.strip(),
            "natureza_juridica": natureza,
            "razao_social": tirar_cpf_da_coluna(razao),
        }
    )


def ler_empresas(arquivo_zip: Path | IO[bytes]) -> Iterator[pd.DataFrame]:
    """(cnpj_basico, natureza_juridica, razao_social) de um `Empresas*.zip`, por partes.

    A razão social da pessoa (213-5 e grupo 4) sai vazia antes de qualquer coisa ser guardada; nas outras,
    o CPF que estiver no texto sai. As outras quatro colunas do arquivo nem são lidas.
    """
    with zipfile.ZipFile(arquivo_zip) as zipado:
        (membro,) = zipado.namelist()  # cada ZIP da Receita tem um arquivo só
        _conferir_campos(zipado, membro, CAMPOS_NO_ARQUIVO_DE_EMPRESAS)
        with zipado.open(membro) as texto:
            leitor = pd.read_csv(
                texto, sep=";", header=None, dtype=str, encoding=CODIFICACAO,
                keep_default_na=False, na_values=[], chunksize=TAMANHO_DA_PARTE,
                usecols=sorted(EMPRESA),
            )  # fmt: skip
            for parte in leitor:
                yield _empresas(parte.rename(columns=EMPRESA))
