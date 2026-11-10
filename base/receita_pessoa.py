"""Sócio pessoa física do cadastro da Receita, para a tela da equipe (ADR 0128, Emenda 1; linha 808).

Leitor **separado** do retrato da base (`base/receita_retrato.py`, que nunca devolve pessoa à base aberta): a
saída daqui só vai para a pasta `acervo_pessoa/`, fora da base e do recorte da API por chave, lida só pela
tela com login de organização com a permissão `pessoa_na_tela`.

**O que sai:** raiz da empresa, nome do sócio, qualificação e data de entrada. Nada mais.

**O que nunca sai** (a coluna é lida só para decidir o descarte, e não é guardada):
- CPF: o documento do sócio nem é lido; um CPF escrito no nome sai (`base.pessoas.sem_cpf`);
- **menor de idade**, pela leitura mais estreita: fora as faixas etárias 0 a 12 e 13 a 20 (a Receita junta
  13 a 20 numa faixa só), a faixa ausente ou desconhecida, todo sócio com representante legal e toda
  qualificação de menor ou incapaz;
- o representante legal (nome, CPF e qualificação) e a faixa etária de quem fica;
- sócio pessoa jurídica (já está na base) e sócio estrangeiro (tipo 3: pode ser pessoa ou empresa, e não dá
  para conferir a idade).

Layout do `Socios*.zip` conferido em 15 e 17/10/2026: 11 campos, sem cabeçalho, `;`, aspas, latin-1.
"""

from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import IO, NamedTuple

import pandas as pd

from base.pessoas.sem_cpf import tirar_cpf_da_coluna
from base.receita_retrato import CAMPOS_DO_SOCIO, CPF_MASCARADO, _datas, _partes

# posição de cada campo no arquivo; o documento do sócio (3) e o país (6) nem são lidos
SOCIO = {
    0: "cnpj_basico", 1: "tipo_socio", 2: "nome_socio", 4: "qualificacao", 5: "data_entrada",
    7: "cpf_do_representante", 8: "nome_do_representante", 9: "qualificacao_do_representante",
    10: "faixa_etaria",
}  # fmt: skip
COLUNAS = ("cnpj_basico", "nome_socio", "qualificacao", "data_entrada")
TIPO_PESSOA_FISICA = "2"
FAIXAS_DE_MENOR = {"1", "2"}  # 0 a 12 anos; 13 a 20 anos
FAIXAS_DE_ADULTO = {"3", "4", "5", "6", "7", "8", "9"}  # 21 a 30 ... mais de 80
# 29 e 58: sócio incapaz; 30: sócio menor; 67 e 68: titular incapaz e titular menor
QUALIFICACOES_DE_MENOR_OU_INCAPAZ = {"29", "30", "58", "67", "68"}
# 09: curador; 14: mãe; 15: pai; 35: tutor. Quem aparece assim está no quadro por um menor ou incapaz:
# mostrar o nome com esse rótulo diria que há um menor ali, e de que família.
QUALIFICACOES_DE_QUEM_REPRESENTA = {"09", "14", "15", "35"}
SEM_REPRESENTANTE = {"", "0", "00", "***000000**", "00000000000"}

NAO_E_PESSOA_FISICA = "nao_e_pessoa_fisica"
MENOR_PELA_FAIXA = "menor_pela_faixa"
FAIXA_DESCONHECIDA = "faixa_desconhecida"
COM_REPRESENTANTE = "com_representante_legal"
QUALIFICACAO_DE_MENOR = "qualificacao_de_menor_ou_incapaz"
QUALIFICACAO_DE_REPRESENTANTE = "qualificacao_de_quem_representa"
SEM_NOME = "sem_nome"
MOTIVOS = (
    NAO_E_PESSOA_FISICA, MENOR_PELA_FAIXA, FAIXA_DESCONHECIDA, COM_REPRESENTANTE,
    QUALIFICACAO_DE_MENOR, QUALIFICACAO_DE_REPRESENTANTE, SEM_NOME,
)  # fmt: skip


class ParteDosSocios(NamedTuple):
    """Um pedaço do `Socios*.zip`: quem fica e quantas linhas saíram por motivo (só números)."""

    socios: pd.DataFrame
    descartes: Counter[str]


def _motivo_do_descarte(parte: pd.DataFrame) -> pd.Series:
    """O primeiro motivo que tira a linha, na ordem de `MOTIVOS`; vazio para quem fica."""
    faixa = parte["faixa_etaria"].str.strip()
    com_representante = (
        ~parte["cpf_do_representante"].str.strip().isin(SEM_REPRESENTANTE)
        | (parte["nome_do_representante"].str.strip() != "")
        | ~parte["qualificacao_do_representante"].str.strip().isin(SEM_REPRESENTANTE)
    )
    qualificacao = parte["qualificacao"].str.strip().str.zfill(2)
    condicoes = {
        NAO_E_PESSOA_FISICA: parte["tipo_socio"].str.strip() != TIPO_PESSOA_FISICA,
        MENOR_PELA_FAIXA: faixa.isin(FAIXAS_DE_MENOR),
        FAIXA_DESCONHECIDA: ~faixa.isin(FAIXAS_DE_ADULTO),
        COM_REPRESENTANTE: com_representante,
        QUALIFICACAO_DE_MENOR: qualificacao.isin(QUALIFICACOES_DE_MENOR_OU_INCAPAZ),
        QUALIFICACAO_DE_REPRESENTANTE: qualificacao.isin(
            QUALIFICACOES_DE_QUEM_REPRESENTA
        ),
        SEM_NOME: parte["nome_socio"].str.strip() == "",
    }
    motivo = pd.Series("", index=parte.index)
    for nome in reversed(MOTIVOS):  # o primeiro da ordem vence
        motivo = motivo.mask(condicoes[nome], nome)
    return motivo


def _sem_documento(nomes: pd.Series) -> pd.Series:
    """O nome sem CPF: inteiro ou pontuado (`sem_cpf`) e na máscara do arquivo de sócios (`***123456**`)."""
    limpos = tirar_cpf_da_coluna(nomes.str.strip())
    return (
        limpos.str.replace(CPF_MASCARADO, " ", regex=True)
        .str.replace(r"\s{2,}", " ", regex=True)
        .str.strip()
    )


def _socios_pf(parte: pd.DataFrame) -> ParteDosSocios:
    parte = parte.rename(columns=SOCIO)
    motivo = _motivo_do_descarte(parte)
    fica = parte.loc[motivo == "", list(COLUNAS)].copy()
    fica["cnpj_basico"] = fica["cnpj_basico"].str.strip().str.upper()
    fica["nome_socio"] = _sem_documento(fica["nome_socio"])
    fica["qualificacao"] = fica["qualificacao"].str.strip().str.zfill(2)
    fica["data_entrada"] = _datas(fica["data_entrada"])
    descartes = Counter(motivo[motivo != ""].value_counts().to_dict())
    return ParteDosSocios(fica.reset_index(drop=True), descartes)


def ler_socios_pf(arquivo_zip: Path | IO[bytes]) -> Iterator[ParteDosSocios]:
    """Os sócios pessoa física adultos de um `Socios*.zip`, em partes, com a contagem dos descartes.

    `socios`: `cnpj_basico`, `nome_socio`, `qualificacao` (código de 2 dígitos) e `data_entrada`. Sem
    documento, sem faixa etária e sem representante. `descartes` conta as linhas tiradas por motivo.
    """
    for parte in _partes(arquivo_zip, CAMPOS_DO_SOCIO, SOCIO):
        yield _socios_pf(parte)
