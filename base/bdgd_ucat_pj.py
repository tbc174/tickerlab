"""BDGD da ANEEL, `UCAT_PJ`, agregado por município e CNAE (linha 640 da fila; ADR 0121, item 4).

O `UCAT_PJ` é o cadastro das unidades consumidoras de pessoa jurídica em alta tensão (CSV com `;`, 101
colunas, 1,42 MB, guardado pela fonte `aneel-bdgd-ucat-pj`). O identificador da unidade vem cifrado, mas a
linha ainda traz endereço, CEP e coordenada. Por isso **nada daqui sai por unidade**: só a agregação.

- **Licença:** ODbL, que pede a mesma licença na base derivada. A tabela sai em ODbL, com `ATRIBUICAO`
  (ANEEL) em todo uso.
- **Sem linha individual:** lê só as colunas que entram na conta (`COLUNAS_LIDAS`); identificador, endereço,
  bairro, CEP, coordenada e descrição nunca são carregados. Município e CNAE com menos de
  `MINIMO_DE_UNIDADES` unidades ficam de fora: uma célula de uma unidade seria a unidade, só com outro nome.
  O resumo diz quantas unidades e células foram retidas, para ninguém ler a tabela como o total do país.
- **Energia em kWh por ano:** soma dos 12 meses de ponta (`ENE_P_*`) e fora de ponta (`ENE_F_*`) da
  fotografia da base. Mês em branco conta zero; unidade sem nenhum mês informado não soma energia.
- **CNAE de 7 dígitos**, sem pontuação (`0151201`), para casar com `cnae_principal` da Receita.

**Sem olhar o futuro:** a base não traz a data em que a ANEEL a publicou. `disponivel_em` é a data da coleta.

Sem Streamlit; pandas só.
"""

from datetime import date
from pathlib import Path

import pandas as pd

FONTE = "aneel-bdgd-ucat-pj"
ATRIBUICAO = (
    "Fonte: ANEEL, Base de Dados Geográfica da Distribuidora (BDGD), unidades consumidoras de pessoa "
    "jurídica em alta tensão (UCAT_PJ), dados abertos sob ODbL, https://dadosabertos.aneel.gov.br"
)
LICENCA = "ODbL"
MINIMO_DE_UNIDADES = 3

MESES = [f"{mes:02d}" for mes in range(1, 13)]
COLUNAS_DE_ENERGIA = [f"ENE_{faixa}_{mes}" for faixa in "PF" for mes in MESES]
COLUNAS_LIDAS = ["MUN", "CNAE", "CAR_INST", "DEM_CONT", *COLUNAS_DE_ENERGIA]
COLUNAS = (
    "codigo_ibge_municipio", "cnae", "unidades", "carga_instalada_kw", "demanda_contratada_kw",
    "energia_ponta_kwh_ano", "energia_fora_ponta_kwh_ano", "disponivel_em",
)  # fmt: skip
CHAVE = ["codigo_ibge_municipio", "cnae"]


def ler(caminho: Path) -> pd.DataFrame:
    """Só as colunas de `COLUNAS_LIDAS` do CSV, tudo em texto (código com zero à esquerda não se perde).

    Tenta UTF-8 e cai para Latin-1 (o portal já publicou nas duas). Coluna que falta é ValueError: o
    layout mudou e ninguém deve agregar em cima de um palpite.
    """
    for codificacao in ("utf-8", "latin-1"):
        try:
            bruto = pd.read_csv(
                caminho,
                sep=";",
                dtype=str,
                usecols=lambda coluna: coluna in COLUNAS_LIDAS,
                encoding=codificacao,
            )
        except UnicodeDecodeError:
            continue
        return _conferir_colunas(bruto)
    raise ValueError(f"UCAT_PJ: {caminho} não abriu nem em UTF-8 nem em Latin-1")


def _conferir_colunas(bruto: pd.DataFrame) -> pd.DataFrame:
    if faltam := [c for c in COLUNAS_LIDAS if c not in bruto.columns]:
        raise ValueError(f"UCAT_PJ: faltam as colunas {', '.join(faltam)}")
    return bruto


def _numeros(coluna: pd.Series) -> pd.Series:
    return pd.to_numeric(coluna.str.replace(",", ".", regex=False), errors="coerce")


def _codigo_de_7_digitos(codigo: pd.Series) -> pd.Series:
    """`0151-2/01` vira `0151201`; o que não tem 7 dígitos fica vazio."""
    digitos = codigo.fillna("").str.replace(r"\D", "", regex=True)
    return digitos.where(digitos.str.len() == 7, "")


def _soma_da_faixa(bruto: pd.DataFrame, faixa: str) -> pd.Series:
    meses = pd.DataFrame({mes: _numeros(bruto[f"ENE_{faixa}_{mes}"]) for mes in MESES})
    return meses.sum(axis=1, min_count=1)


def agregar(
    bruto: pd.DataFrame, coletado_em: date
) -> tuple[pd.DataFrame, dict[str, int]]:
    """`(tabela, resumo)`: uma linha por município e CNAE com ao menos `MINIMO_DE_UNIDADES` unidades.

    Unidade sem município ou sem CNAE válido não entra em nenhuma célula (`unidades_sem_chave` no resumo).
    """
    _conferir_colunas(bruto)
    unidades = pd.DataFrame(
        {
            "codigo_ibge_municipio": _codigo_de_7_digitos(bruto["MUN"]),
            "cnae": _codigo_de_7_digitos(bruto["CNAE"]),
            "carga_instalada_kw": _numeros(bruto["CAR_INST"]),
            "demanda_contratada_kw": _numeros(bruto["DEM_CONT"]),
            "energia_ponta_kwh_ano": _soma_da_faixa(bruto, "P"),
            "energia_fora_ponta_kwh_ano": _soma_da_faixa(bruto, "F"),
        }
    )
    com_chave = unidades[
        (unidades["codigo_ibge_municipio"] != "") & (unidades["cnae"] != "")
    ]
    grupos = com_chave.groupby(CHAVE)
    tabela = (
        grupos.sum(min_count=1).join(grupos.size().rename("unidades")).reset_index()
    )
    suficientes = tabela[tabela["unidades"] >= MINIMO_DE_UNIDADES].copy()
    suficientes["disponivel_em"] = pd.Timestamp(coletado_em)
    suficientes = suficientes[list(COLUNAS)].sort_values(CHAVE).reset_index(drop=True)
    resumo = {
        "unidades_lidas": len(unidades),
        "unidades_sem_chave": len(unidades) - len(com_chave),
        "unidades_retidas": int(
            tabela["unidades"].sum() - suficientes["unidades"].sum()
        ),
        "celulas_retidas": len(tabela) - len(suficientes),
        "celulas": len(suficientes),
    }
    return suficientes, resumo


def agregar_arquivo(
    caminho: Path, coletado_em: date
) -> tuple[pd.DataFrame, dict[str, int]]:
    """O CSV da fonte até a tabela agregada."""
    return agregar(ler(caminho), coletado_em)
