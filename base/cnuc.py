"""CNUC do MMA (B5 da rodada de fontes de 03/11/2026): Cadastro Nacional de Unidades de Conservação.

O CSV do dados.mma.gov.br (CC Atribuição, CP1252, separador `;`, 41 colunas, um por mês) traz uma linha por
unidade de conservação (UC): categoria, esfera, grupo, ano e ato de criação, órgão gestor, área e o código
WDPA. **Não tem geometria, proprietário nem CNPJ** (nem as RPPN). Os municípios vêm como texto
("A (GO), B (GO)"), então `municipios_abrangidos` os separa em linhas de nome e UF.

**A ligação com empresas é só territorial:** uma empresa num município que a UC abrange não está dentro da
UC, e estar dentro dela não prova infração. O texto que mostra o dado leva `AVISO_TERRITORIAL`.

**Sem olhar o futuro:** a fonte não dá a data de divulgação por linha; `disponivel_em` é a data da coleta.
Sem Streamlit; pandas só.
"""

import io
import re
from datetime import date

import pandas as pd

FONTE = "mma-cnuc"
ATRIBUICAO = (
    "Fonte: Ministério do Meio Ambiente e Mudança do Clima (MMA), Cadastro Nacional de Unidades de "
    "Conservação (CNUC), CC BY, https://dados.mma.gov.br/dataset/unidadesdeconservacao"
)
AVISO_TERRITORIAL = (
    "A ligação com empresas é apenas territorial: o cadastro não traz proprietário nem CNPJ, e uma empresa "
    "no município de uma unidade de conservação não prova que esteja dentro dela, nem que haja infração."
)
COLUNAS_DA_FONTE = {
    "Código UC": "codigo_uc",
    "Nome da UC": "nome",
    "Esfera Administrativa": "esfera",
    "Categoria de Manejo": "categoria_manejo",
    "Categoria IUCN": "categoria_iucn",
    "UF": "uf",
    "Ano de Criação": "ano_criacao",
    "Ato Legal de Criação": "ato_legal",
    "Municípios Abrangidos": "municipios",
    "Órgão Gestor": "orgao_gestor",
    "Área soma biomas": "area_ha",
    "Bioma declarado": "bioma",
    "Grupo": "grupo",
    "Código WDPA": "codigo_wdpa",
}
MUNICIPIO_E_UF = re.compile(r"([^,;()]+?)\s*\(([A-Z]{2})\)")


def _hectares(valor: str) -> float:
    """ "65.038,5" → 65038.5 (ponto de milhar, vírgula decimal); vazio vira nulo."""
    texto = valor.strip().replace(".", "").replace(",", ".")
    return float(texto) if texto else float("nan")


def ler(conteudo: bytes, coletado_em: date) -> pd.DataFrame:
    """Uma linha por unidade de conservação, com o código da UC como chave."""
    try:
        texto = conteudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = conteudo.decode("cp1252")
    bruta = pd.read_csv(io.StringIO(texto), sep=";", dtype=str, keep_default_na=False)
    bruta.columns = [c.strip() for c in bruta.columns]
    faltam = set(COLUNAS_DA_FONTE) - set(bruta.columns)
    if faltam:
        raise ValueError(f"CNUC: faltam colunas {sorted(faltam)}")
    tabela = bruta[list(COLUNAS_DA_FONTE)].rename(columns=COLUNAS_DA_FONTE).copy()
    for coluna in tabela.columns:
        tabela[coluna] = tabela[coluna].str.strip()
    tabela["area_ha"] = tabela["area_ha"].map(_hectares)
    tabela["ano_criacao"] = pd.to_numeric(
        tabela["ano_criacao"], errors="coerce"
    ).astype("Int64")
    tabela["codigo_wdpa"] = pd.to_numeric(
        tabela["codigo_wdpa"], errors="coerce"
    ).astype("Int64")
    tabela["disponivel_em"] = pd.Timestamp(coletado_em)
    return tabela.drop_duplicates("codigo_uc").reset_index(drop=True)


def municipios_abrangidos(unidades: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por UC e município abrangido: `codigo_uc`, `municipio` (como veio) e `uf`."""
    linhas = [
        (codigo, nome.strip(), uf)
        for codigo, texto in zip(
            unidades["codigo_uc"], unidades["municipios"], strict=True
        )
        for nome, uf in MUNICIPIO_E_UF.findall(texto)
    ]
    return pd.DataFrame(linhas, columns=["codigo_uc", "municipio", "uf"])
