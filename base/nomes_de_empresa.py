"""Os nomes pelos quais se acha uma empresa (linha 1033): razão social, nome fantasia e razão social antiga.

A busca pela razão social de hoje não acha a empresa que o mercado chama pela marca, nem a que mudou de nome
depois de comprada. Esta tabela (`cnpj_nomes_pj`, uma linha por raiz e nome) junta os três.

**Só empresa (LGPD, ADR 0106).** Entra só a raiz da vista sem pessoa dos estabelecimentos
(`cnpj_estabelecimentos_pj`: fora o empresário individual, o grupo 4 e o MEI, cujo nome fantasia e razão social
costumam ser o nome da pessoa). Em todo nome, o CPF escrito no texto sai, e nome com e-mail ou endereço de site
não entra. Telefone, endereço e o resto do arquivo de estabelecimentos nem são lidos.

**Como o nome é procurado** (`normalizar`): sem acento, em maiúsculas, só letras e números, com as letras soltas
juntas ("D P B" vira "DPB", "S/A" vira "SA"). O pedido passa pela mesma função.
"""

import re
import unicodedata
from collections.abc import Iterator
from pathlib import Path
from typing import IO

import pandas as pd

from base.pessoas.sem_cpf import tirar_cpf_da_coluna
from base.receita_empresas import sem_numero_de_pessoa
from base.receita_retrato import CAMPOS_DO_ESTABELECIMENTO, _partes
from base.rede.entidades import natureza_de_pessoa

RAZAO_SOCIAL, NOME_FANTASIA = "razao_social", "nome_fantasia"
RAZAO_SOCIAL_ANTERIOR = "razao_social_anterior"
# quando o mesmo nome vem por mais de um caminho, fica o primeiro desta ordem
TIPOS_DE_NOME = (RAZAO_SOCIAL, NOME_FANTASIA, RAZAO_SOCIAL_ANTERIOR)
COLUNAS = (
    "cnpj_basico", "tipo_de_nome", "nome_de_empresa", "nome_para_busca", "trocado_em_mes",
)  # fmt: skip
# raiz e nome fantasia nos `Estabelecimentos*.zip`; nenhuma outra coluna é lida
CAMPOS_DA_FANTASIA = {0: "cnpj_basico", 4: "nome_fantasia"}
CONTATO_NO_NOME = r"@|\bWWW\.|HTTP"
# só no nome fantasia (texto livre): telefone (8 a 10 dígitos, ou 0800), CEP e logradouro seguido
# de número. Na dúvida o nome sai: a empresa continua achada pela razão social
CONTATO_NA_FANTASIA = (
    r"(?<!\d)(?:9[\s.-]?)?\d{4}[\s.-]?\d{4}(?!\d)|(?<!\d)\d{10}(?!\d)|\b0800[\s.-]?\d|(?<!\d)\d{5}-\d{3}(?!\d)"
    r"|\b(?:RUA|R\.|AVENIDA|AV|ALAMEDA|TRAVESSA|PRACA|PRAÇA|ESTRADA|RODOVIA)(?=[\s.,]).*\d"
)
FORMA_JURIDICA_NO_FIM = r"(?: (?:LTDA|LIMITADA|SA|EIRELI|ME|EPP))+$"
LETRA_SOLTA_ANTES_DE_OUTRA = r"\b([A-Z0-9]) (?=[A-Z0-9]\b)"
# a mesma junção no banco, cujo motor de expressão não olha à frente: marca com "~" cada palavra de uma letra
# (duas passadas, porque o espaço entre vizinhas é um só) e junta as marcadas vizinhas, dobrando a cada passada
PASSADAS_PARA_MARCAR, PASSADAS_PARA_JUNTAR = 2, 5  # 5 juntam até 32 letras soltas


def normalizar(nome: str) -> str:
    """O nome como é procurado: sem acento, maiúsculo, só letras e números e com as letras soltas juntas."""
    decomposto = unicodedata.normalize("NFKD", nome.upper())
    sem_acento = "".join(c for c in decomposto if not unicodedata.combining(c))
    palavras = re.sub(r"[^A-Z0-9]+", " ", sem_acento).strip()
    return re.sub(LETRA_SOLTA_ANTES_DE_OUTRA, r"\1", palavras)


def normalizar_em_sql(coluna: str) -> str:
    """A expressão do DuckDB que dá o mesmo que `normalizar`, para o nome que ainda não está na tabela de nomes.

    `coluna` é um nome de coluna ou parâmetro escrito no código, nunca um texto de quem pede.
    """
    base = (
        f"trim(regexp_replace(strip_accents(upper({coluna})), '[^A-Z0-9]+', ' ', 'g'))"
    )
    junto = f"(' ' || {base} || ' ')"
    for _ in range(PASSADAS_PARA_MARCAR):
        junto = rf"regexp_replace({junto}, ' ([A-Z0-9]) ', ' \1~ ', 'g')"
    for _ in range(PASSADAS_PARA_JUNTAR):
        junto = rf"regexp_replace({junto}, '~ ([A-Z0-9]+)~', '\1~', 'g')"
    return (
        f"CASE WHEN regexp_matches({base}, '(^| )[A-Z0-9] [A-Z0-9]( |$)') "
        f"THEN trim(replace({junto}, '~', '')) ELSE {base} END"
    )


def sem_forma_juridica(normalizado: str) -> str:
    """O nome normalizado sem "LTDA", "SA" e afins no fim; se sobrar nada, o próprio nome."""
    return re.sub(FORMA_JURIDICA_NO_FIM, "", normalizado) or normalizado


def ler_nomes_fantasia(arquivo_zip: Path | IO[bytes]) -> Iterator[pd.DataFrame]:
    """(raiz, nome fantasia) das linhas que têm nome fantasia, de um `Estabelecimentos*.zip`, em partes."""
    for parte in _partes(arquivo_zip, CAMPOS_DO_ESTABELECIMENTO, CAMPOS_DA_FANTASIA):
        parte = parte.rename(columns=CAMPOS_DA_FANTASIA)
        parte["nome_fantasia"] = parte["nome_fantasia"].str.strip()
        yield parte[parte["nome_fantasia"] != ""].reset_index(drop=True)


def _nomes(
    raizes: pd.Series, nomes: pd.Series, tipo: str, trocado_em: pd.Series | str = ""
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "cnpj_basico": raizes.to_numpy(),
            "tipo_de_nome": tipo,
            "nome_de_empresa": nomes.to_numpy(),
            "trocado_em_mes": trocado_em if isinstance(trocado_em, str) else trocado_em.to_numpy(),
        }
    )  # fmt: skip


def _antigos(historico: pd.DataFrame) -> pd.DataFrame:
    """Cada razão social de uma versão do histórico, com o mês da versão seguinte (quando ela mudou).

    A versão que ainda vale também sai daqui, sem mês: `tabela_de_nomes` a descarta por ser igual à de hoje.
    A versão do tempo em que a raiz era empresário individual ou grupo 4 nunca entra (a razão social era o
    nome da pessoa); o leitor do histórico já a grava vazia, e aqui se confere de novo.
    """
    versoes = historico.sort_values(["cnpj_basico", "mes_do_retrato"], kind="stable")
    seguinte = versoes.groupby("cnpj_basico")["mes_do_retrato"].shift(-1)
    versoes = versoes.assign(trocado=seguinte.fillna(""))
    valendo = versoes["consta"].astype(bool) & versoes["razao_social"].fillna("").ne("")
    if "natureza_juridica" in versoes.columns:
        naturezas = versoes["natureza_juridica"].fillna("").astype(str)
        valendo &= ~naturezas.map(natureza_de_pessoa).astype(bool)
    versoes = versoes[valendo]
    return _nomes(
        versoes["cnpj_basico"],
        versoes["razao_social"],
        RAZAO_SOCIAL_ANTERIOR,
        versoes["trocado"],
    )


def _limpar(nomes: pd.DataFrame) -> pd.DataFrame:
    """Sem CPF nem contato no nome, com a forma de procurar; sai o nome que ficou vazio. O nome fantasia
    com telefone ou endereço escrito dentro sai inteiro."""
    texto = sem_numero_de_pessoa(
        tirar_cpf_da_coluna(nomes["nome_de_empresa"].astype(str).str.strip())
    )
    limpos = nomes.assign(nome_de_empresa=texto, nome_para_busca=texto.map(normalizar))
    maiusculo = texto.str.upper()
    com_contato = maiusculo.str.contains(CONTATO_NO_NOME, regex=True) | (
        nomes["tipo_de_nome"].eq(NOME_FANTASIA)
        & maiusculo.str.contains(CONTATO_NA_FANTASIA, regex=True)
    )
    return limpos[~com_contato & limpos["nome_para_busca"].ne("")]


def tabela_de_nomes(
    empresas: pd.DataFrame, fantasias: pd.DataFrame, historico: pd.DataFrame | None
) -> pd.DataFrame:
    """As linhas de `cnpj_nomes_pj` das raízes de `empresas` (a lista sem pessoa: `cnpj_basico`, `razao_social`).

    `fantasias`: `cnpj_basico` e `nome_fantasia` (`ler_nomes_fantasia`). `historico`: as versões de
    `cnpj_empresas_historico`; sem ele, a tabela sai sem razão social antiga. Nome que, sem a forma jurídica,
    repete outro da mesma raiz fica uma vez só, na ordem de `TIPOS_DE_NOME`.
    """
    partes = [_nomes(empresas["cnpj_basico"], empresas["razao_social"], RAZAO_SOCIAL)]
    partes.append(
        _nomes(fantasias["cnpj_basico"], fantasias["nome_fantasia"], NOME_FANTASIA)
    )
    if historico is not None and len(historico):
        partes.append(_antigos(historico))
    juntas = pd.concat([p for p in partes if len(p)] or partes[:1], ignore_index=True)
    juntas = _limpar(juntas[juntas["cnpj_basico"].isin(set(empresas["cnpj_basico"]))])
    sem_forma = juntas["nome_para_busca"].map(sem_forma_juridica)
    ordem = juntas["tipo_de_nome"].map(TIPOS_DE_NOME.index)
    juntas = juntas.assign(chave=sem_forma, ordem=ordem).sort_values(
        ["cnpj_basico", "ordem", "nome_de_empresa", "trocado_em_mes"],
        ascending=[True, True, True, False],
        kind="stable",
    )
    juntas = juntas.drop_duplicates(["cnpj_basico", "chave"], keep="first")
    return juntas[list(COLUNAS)].reset_index(drop=True)
