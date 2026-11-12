"""Contato do estabelecimento no cadastro da Receita, para a tela da equipe (ADR 0128, Emenda 1; linha 808).

Leitor **separado** do retrato da base (`base/receita_retrato.py`, que nunca guarda telefone nem e-mail e
corta o endereço do MEI e do empresário individual): a saída daqui só vai para a pasta `acervo_pessoa/`,
fora da base e do recorte da API por chave, lida só pela tela com login de organização com a permissão
`pessoa_na_tela`. No MEI e no empresário individual o endereço e o telefone do estabelecimento costumam ser
os da pessoa: por isso este conjunto é tratado, inteiro, como dado de pessoa.

**O que sai**, só dos estabelecimentos **ativos** (situação cadastral 02): o CNPJ, se é a matriz, o endereço
(logradouro, número, complemento, bairro, CEP, município e UF), até dois telefones e o e-mail.

**O que nunca sai:** nome fantasia (o do MEI costuma ser o nome da pessoa), fax, estabelecimento que não está
ativo (o contato de uma empresa fechada não serve à prospecção e é só dado de pessoa parado) e qualquer coisa
com cara de CPF: CPF escrito no endereço é tirado (`base.pessoas.sem_cpf`), telefone fora do formato (DDD de
2 dígitos e número de 8 ou 9) fica vazio, e e-mail com onze dígitos seguidos no nome fica vazio.

Layout do `Estabelecimentos*.zip` conferido em 15 e 17/10/2026: 30 campos, sem cabeçalho, `;`, aspas, latin-1.
"""

from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import IO, NamedTuple

import pandas as pd

from base.pessoas.sem_cpf import tirar_cpf_da_coluna
from base.receita_retrato import CAMPOS_DO_ESTABELECIMENTO, MATRIZ, _partes

# posição de cada campo no arquivo; nome fantasia (4) e fax (25 e 26) nem são lidos
ESTABELECIMENTO = {
    0: "cnpj_basico", 1: "ordem", 2: "dv", 3: "matriz", 5: "situacao_cadastral",
    13: "tipo_logradouro", 14: "logradouro", 15: "numero", 16: "complemento", 17: "bairro",
    18: "cep", 19: "uf", 20: "municipio", 21: "ddd_1", 22: "telefone_1", 23: "ddd_2",
    24: "telefone_2", 27: "email",
}  # fmt: skip
ENDERECO = ("tipo_logradouro", "logradouro", "numero", "complemento", "bairro")
COLUNAS = (
    "cnpj_basico", "cnpj", "matriz", *ENDERECO, "cep", "municipio", "uf",
    "telefone_1", "telefone_2", "email",
)  # fmt: skip
ATIVA = "02"
DDD = r"[1-9]\d"
NUMERO_DO_TELEFONE = (
    r"\d{8,9}"  # mais que isso não é telefone (um CPF digitado ali tem 11)
)
CEP = r"\d{8}"
EMAIL = r"[^@\s]+@[^@\s]+\.[^@\s]+"
TAMANHO_MAXIMO_DO_EMAIL = 115  # o do campo no layout da Receita
# onze dígitos com qualquer separador entre eles (espaço, ponto, traço, barra, vírgula...), sem dígito colado
ONZE_DIGITOS_SEPARADOS = r"(?<!\d)\d(?:[^\w]|_)*(?:\d(?:[^\w]|_)*){9}\d(?!\d)"

NAO_ATIVO = "estabelecimento_nao_ativo"
TELEFONE_FORA_DO_FORMATO = "telefone_fora_do_formato"
EMAIL_FORA_DO_FORMATO = "email_fora_do_formato"
EMAIL_COM_CARA_DE_CPF = "email_com_cara_de_cpf"
DE_OPOSTO = "contato_de_titular_que_se_opos"  # linha 829
ENDERECO_CORTADO = "endereco_de_individual_cortado"  # linha 859
MOTIVOS = (
    NAO_ATIVO, TELEFONE_FORA_DO_FORMATO, EMAIL_FORA_DO_FORMATO, EMAIL_COM_CARA_DE_CPF,
    DE_OPOSTO, ENDERECO_CORTADO,
)  # fmt: skip


class ParteDoContato(NamedTuple):
    """Um pedaço do `Estabelecimentos*.zip`: quem fica e quantas linhas ou campos saíram por motivo."""

    estabelecimentos: pd.DataFrame
    descartes: Counter[str]


def _so_digitos(coluna: pd.Series) -> pd.Series:
    return coluna.str.replace(r"\D", "", regex=True)


def _telefone(ddd: pd.Series, numero: pd.Series, descartes: Counter[str]) -> pd.Series:
    """DDD e número juntos, só dígitos; fora do formato fica vazio (um CPF digitado ali não passa)."""
    numero = _so_digitos(numero)
    ddd = _so_digitos(ddd).str.lstrip("0")
    vale = ddd.str.fullmatch(DDD) & numero.str.fullmatch(NUMERO_DO_TELEFONE)
    descartes[TELEFONE_FORA_DO_FORMATO] += int(((numero != "") & ~vale).sum())
    return (ddd + numero).where(vale)


def _email(coluna: pd.Series, descartes: Counter[str]) -> pd.Series:
    """O e-mail em minúsculas; fora do formato, ou com onze dígitos seguidos no nome, fica vazio."""
    email = coluna.str.strip().str.lower()
    informado = email != ""
    forma = email.str.fullmatch(EMAIL) & (email.str.len() <= TAMANHO_MAXIMO_DO_EMAIL)
    cara_de_cpf = email.str.contains(ONZE_DIGITOS_SEPARADOS, regex=True)
    descartes[EMAIL_FORA_DO_FORMATO] += int((informado & ~forma).sum())
    descartes[EMAIL_COM_CARA_DE_CPF] += int((forma & cara_de_cpf).sum())
    return email.where(forma & ~cara_de_cpf)


def _texto(coluna: pd.Series) -> pd.Series:
    """O texto do endereço sem CPF e sem espaço sobrando; vazio vira ausente."""
    limpo = tirar_cpf_da_coluna(coluna.str.strip())
    limpo = limpo.str.replace(ONZE_DIGITOS_SEPARADOS, " ", regex=True)
    limpo = limpo.str.replace(r"\s{2,}", " ", regex=True).str.strip()
    return limpo.mask(limpo == "")


def _contato(parte: pd.DataFrame) -> ParteDoContato:
    parte = parte.rename(columns=ESTABELECIMENTO)
    ativo = parte["situacao_cadastral"].str.strip() == ATIVA
    descartes: Counter[str] = Counter({NAO_ATIVO: int((~ativo).sum())})
    fica = parte.loc[ativo].copy()
    fica["cnpj_basico"] = fica["cnpj_basico"].str.strip().str.upper()
    fica["cnpj"] = (fica["cnpj_basico"] + fica["ordem"] + fica["dv"]).str.upper()
    fica["matriz"] = fica["matriz"] == MATRIZ
    for coluna in ENDERECO:
        fica[coluna] = _texto(fica[coluna])
    cep = _so_digitos(fica["cep"])
    fica["cep"] = cep.where(cep.str.fullmatch(CEP))
    for coluna in ("municipio", "uf"):
        texto = fica[coluna].str.strip().str.upper()
        fica[coluna] = texto.mask(texto == "")
    for n in ("1", "2"):
        fica[f"telefone_{n}"] = _telefone(
            fica[f"ddd_{n}"], fica[f"telefone_{n}"], descartes
        )
    fica["email"] = _email(fica["email"], descartes)
    return ParteDoContato(fica[list(COLUNAS)].reset_index(drop=True), +descartes)


def _so_municipio(contato: ParteDoContato, raizes: set[str]) -> ParteDoContato:
    """Empresário individual e MEI: o endereço é o da pessoa, então só o município e a UF ficam (linha 859;
    política de privacidade, versão 16). Telefone e e-mail seguem, como a política diz."""
    cortar = contato.estabelecimentos["cnpj_basico"].isin(raizes)
    if not cortar.any():
        return contato
    estabelecimentos = contato.estabelecimentos.copy()
    for coluna in (*ENDERECO, "cep"):
        estabelecimentos.loc[cortar, coluna] = None
    contato.descartes[ENDERECO_CORTADO] += int(cortar.sum())
    return ParteDoContato(estabelecimentos, contato.descartes)


def ler_contato(
    arquivo_zip: Path | IO[bytes],
    tiradas: set[str],
    individuais: set[str] | None = None,
) -> Iterator[ParteDoContato]:
    """O contato dos estabelecimentos ativos de um `Estabelecimentos*.zip`, em partes, com os descartes.

    `estabelecimentos` tem as colunas de `COLUNAS`; o que não foi informado, ou não passou no formato, vem
    ausente. `descartes` conta os estabelecimentos que não estão ativos e os campos esvaziados, por motivo.
    As raízes em `tiradas` (empresário individual ou MEI que pediu a oposição, linha 829) ficam de fora; as
    em `individuais` (todo empresário individual e MEI) saem só com município, UF, telefones e e-mail.
    """
    for parte in _partes(arquivo_zip, CAMPOS_DO_ESTABELECIMENTO, ESTABELECIMENTO):
        contato = _so_municipio(_contato(parte), individuais or set())
        oposto = contato.estabelecimentos["cnpj_basico"].isin(tiradas)
        if oposto.any():
            contato.descartes[DE_OPOSTO] += int(oposto.sum())
            contato = ParteDoContato(
                contato.estabelecimentos.loc[~oposto].reset_index(drop=True),
                contato.descartes,
            )
        yield contato
