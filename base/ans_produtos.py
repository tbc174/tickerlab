"""Planos de saúde da ANS (linha 770, item 1; fonte `ans-cobertura-e-produtos`): as características de cada plano
registrado (segmentação, cobertura, abrangência, contratação, situação), um retrato inteiro a cada baixada
(`base/retratos.py` junta os retratos numa tabela que só cresce), ligadas ao CNPJ da operadora.

- **Formato** (conferido em 25/11/2026 nos três retratos que o arquivista guardou, 25/10, 01/11 e 15/11, ~166 mil
  planos cada): `;`, UTF-8, texto entre aspas, data em `AAAA-MM-DD`, um plano por `ID_PLANO` (único no arquivo).
- **O CNPJ vem da ponte, nunca do nome:** o arquivo só traz o `REGISTRO_OPERADORA`; o CNPJ é o da operadora com o
  mesmo registro em `ans_operadoras` (`base/cnpj_pela_ponte.py`), na linha que já era pública no dia em que o plano
  ficou público. Registro sem linha na ponte, operadora que é pessoa (MEI, empresário individual) ou que saiu do
  cadastro deixam o CNPJ vazio. Nos três retratos conferidos, os 2.952 registros existem no cadastro da ANS.
- **Fica de fora:** a razão social da operadora (o nome está em `ans_operadoras`) e `DT_ATUALIZACAO`, que é a data
  do arquivo, igual em todas as linhas, e faria todo plano parecer mudado a cada retrato.
- **Sem olhar o futuro** (`disponivel_no_primeiro`): o plano vale desde o dia do retrato que o trouxe, mesmo com
  `DT_REGISTRO_PLANO` mais antigo: a ANS não diz quando passou a publicar cada plano. O que muda num retrato
  seguinte (a situação, por exemplo) vale desde o dia dele; o plano que some do arquivo ganha uma linha
  `consta=False`.
- **Ficam para depois:** o arquivo com os municípios de cada cobertura geográfica (`ID_GEO_COBERTURA` aponta para
  ele) e os produtos e prestadores hospitalares, que a mesma pasta da ANS também guarda.

Sem Streamlit; pandas só.
"""

import io
from collections.abc import Callable, Collection
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import sqlalchemy as sa

from base import cadastros_em_retrato, cnpj_pela_ponte
from base import retratos as motor
from base.ans_operadoras import TABELA as TABELA_DA_PONTE

FONTE = "ans-cobertura-e-produtos"
TABELA = "ans_produtos"
CADASTRO = "planos"
ARQUIVO = "pda-008-caracteristicas_produtos_saude_suplementar.csv"
SEPARADOR = ";"
CODIFICACAO = "utf-8-sig"
FORMATO_DA_DATA = "%Y-%m-%d"
COLUNAS_DA_FONTE = {
    "ID_PLANO": "id_na_fonte",
    "CD_PLANO": "codigo_do_plano",
    "NM_PLANO": "nome_do_plano",
    "REGISTRO_OPERADORA": "registro_da_operadora",
    "GR_MODALIDADE": "modalidade_da_operadora",
    "PORTE_OPERADORA": "porte_da_operadora",
    "VIGENCIA_PLANO": "vigencia_do_plano",
    "CONTRATACAO": "contratacao",
    "GR_CONTRATACAO": "grupo_de_contratacao",
    "SGMT_ASSISTENCIAL": "segmentacao_assistencial",
    "GR_SGMT_ASSISTENCIAL": "grupo_de_segmentacao",
    "LG_ODONTOLOGICO": "odontologico",
    "OBSTETRICIA": "obstetricia",
    "COBERTURA": "cobertura",
    "TIPO_FINANCIAMENTO": "tipo_de_financiamento",
    "ABRANGENCIA_COBERTURA": "abrangencia",
    "ID_GEO_COBERTURA": "id_da_cobertura_geografica",
    "FATOR_MODERADOR": "fator_moderador",
    "ACOMODACAO_HOSPITALAR": "acomodacao_hospitalar",
    "LIVRE_ESCOLHA": "livre_escolha",
    "SITUACAO_PLANO": "situacao_do_plano",
    "DT_SITUACAO": "situacao_desde",
    "DT_REGISTRO_PLANO": "registrado_em",
}
TEXTOS = [
    "codigo_do_plano",
    "nome_do_plano",
    "registro_da_operadora",
    "modalidade_da_operadora",
    "porte_da_operadora",
    "vigencia_do_plano",
    "contratacao",
    "grupo_de_contratacao",
    "segmentacao_assistencial",
    "grupo_de_segmentacao",
    "obstetricia",
    "cobertura",
    "tipo_de_financiamento",
    "abrangencia",
    "id_da_cobertura_geografica",
    "fator_moderador",
    "acomodacao_hospitalar",
    "livre_escolha",
    "situacao_do_plano",
]
DATAS = ["situacao_desde", "registrado_em"]
VALORES = [*TEXTOS, "odontologico", *DATAS, "consta"]
# da fonte, na ordem do arquivo; `cnpj` e `cnpj_basico` entram depois, pela ponte
COLUNAS = [
    "id_na_fonte",
    "codigo_do_plano",
    "nome_do_plano",
    "registro_da_operadora",
    "cnpj",
    "cnpj_basico",
    *TEXTOS[3:],
    "odontologico",
    *DATAS,
]
SO_DO_ARQUIVO = [c for c in COLUNAS if c not in ("cnpj", "cnpj_basico")]


def ler_retrato(conteudo: bytes) -> tuple[pd.DataFrame, dict[str, int]]:
    """Os planos de um arquivo e a contagem do que ficou de fora (sem `ID_PLANO`, ou repetido)."""
    bruta = pd.read_csv(
        io.BytesIO(conteudo),
        sep=SEPARADOR,
        encoding=CODIFICACAO,
        dtype=str,
        keep_default_na=False,
        usecols=lambda coluna: coluna.strip() in COLUNAS_DA_FONTE,
    )
    bruta = bruta.rename(columns=lambda c: COLUNAS_DA_FONTE[c.strip()])
    bruta = bruta.apply(lambda serie: serie.str.strip())
    com_id = bruta["id_na_fonte"].ne("")
    repetido = bruta["id_na_fonte"].duplicated(keep="first") & com_id
    tabela = bruta[com_id & ~repetido]
    pronta = pd.DataFrame(
        {
            "id_na_fonte": tabela["id_na_fonte"],
            **{c: motor.sem_vazio(tabela[c]) for c in TEXTOS},
            "odontologico": tabela["odontologico"]
            .map({"1": True, "0": False})
            .astype("boolean"),
            **{
                c: pd.to_datetime(tabela[c], format=FORMATO_DA_DATA, errors="coerce")
                for c in DATAS
            },
        }
    )[SO_DO_ARQUIVO].reset_index(drop=True)
    contagem = {
        "linhas": len(bruta),
        "sem_id": int((~com_id).sum()),
        "id_repetido": int(repetido.sum()),
    }
    return pronta, contagem


def disponivel_no_primeiro(novos: pd.DataFrame, dia: pd.Timestamp) -> pd.Series:
    """O dia do retrato para todos: a ANS não diz desde quando publica cada plano."""
    return pd.Series(dia, index=novos.index)


def juntar_retratos(
    lidos: list[tuple[motor.Retrato, pd.DataFrame]],
) -> tuple[pd.DataFrame, int]:
    """Os retratos lidos (do mais antigo ao mais novo) numa tabela de valores, e quantos foram pulados."""
    return motor.juntar(lidos, VALORES, disponivel_no_primeiro)


def com_cnpj_da_operadora(
    planos: pd.DataFrame, ponte: pd.DataFrame | None
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Os planos com `cnpj` e `cnpj_basico` da operadora de mesmo registro na ponte (`ans_operadoras`), e a
    contagem do que ligou. Nada é casado por nome."""
    return cnpj_pela_ponte.com_cnpj_da_ponte(
        planos, "registro_da_operadora", ponte, cnpj_pela_ponte.CNPJ_E_RAIZ
    )


CADASTROS = (
    cadastros_em_retrato.Cadastro(
        tabela=TABELA,
        nome=CADASTRO,
        fonte=FONTE,
        ler=lambda retrato: ler_retrato(motor.original(retrato.caminho)),
        juntar=juntar_retratos,
        colunas=tuple(COLUNAS),
        datas=tuple(DATAS),
        url_termina_em="/" + ARQUIVO,
        ponte=TABELA_DA_PONTE,
        ligar=com_cnpj_da_operadora,
    ),
)


def montar(
    conexao: sa.Connection,
    pasta: Path,
    agora: datetime,
    pessoas: Collection[str] | np.ndarray | None = None,
    refazer: bool = False,
    leitor: Callable[[Path], pd.DataFrame] | None = None,
) -> dict[str, dict[str, int]]:
    """`<pasta>/ans_produtos/planos.parquet` (um retrato por baixada, só CNPJ). Monte `ans_operadoras` antes: sem
    ela o CNPJ sai vazio, e a tabela se refaz sozinha quando a ponte muda. `leitor` (quem monta passa a função de
    reler Parquet de `base.parquet`) relê a ponte gravada; sem ele o CNPJ sai vazio."""
    return cadastros_em_retrato.montar(
        CADASTROS, conexao, pasta, agora, pessoas, refazer, leitor
    )
