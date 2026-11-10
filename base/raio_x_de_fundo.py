"""Raio-x de fundo por CNPJ (API A3b; linha 583 da fila): taxas, carteira e custo da taxa.

`raio_x_de_fundo(porta, cnpj, como_era_em)` junta, para um fundo:

- **Taxas** (`cadastro_de_fundos`, da CVM): administração e performance, a classe, a situação e o
  patrimônio líquido com a data dele. O cadastro é o retrato do dia da coleta, **sem data pública por
  linha**; por isso, com `como_era_em=D`, as taxas ficam fora e a lacuna diz isso (o futuro não muda o
  passado). O histórico por data (`cad_fi_hist`) e o gestor e o administrador "como eram em D" entram
  quando a porta servir esse histórico (linha 230).
- **Carteira** (`carteiras_dos_fundos`, o CDA): as posições em ações da competência mais nova que já
  era pública em D (`disponivel_em`, regra de `base/cda.py`).
- **Custo da taxa em 5 e 20 anos** (`src/ferramentas/custos.py`): uma conta de **exemplo**, com capital
  e retorno hipotéticos escritos na resposta; não é previsão nem recomendação.

Só tipos simples na saída (dicionários, listas, textos e números), para virar JSON na rota da API.
Gestor e administrador não saem daqui: a lista de palavras do portão (`src/portao_externo.py`) trata
"administrador" como nunca vendável, e o direito de cada campo é escrito na A5.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

import pandas as pd

from base import cnpj as cnpj_
from base.porta import Porta
from src.ferramentas.custos import custo_da_taxa

CADASTRO = "cadastro_de_fundos"
CARTEIRAS = "carteiras_dos_fundos"
PRAZOS_DO_CUSTO = (5, 20)
CAPITAL_DO_EXEMPLO = 10_000.0
RETORNO_DO_EXEMPLO = 0.10  # ao ano, antes da taxa: hipótese de conta, não previsão
CAMPOS_DO_CADASTRO = {
    "DENOM_SOCIAL": "nome",
    "CLASSE": "classe",
    "SIT": "situacao",
    "TAXA_ADM": "taxa_administracao_pct_ao_ano",
    "INF_TAXA_ADM": "texto_taxa_administracao",
    "TAXA_PERFM": "taxa_performance_pct",
    "INF_TAXA_PERFM": "texto_taxa_performance",
    "VL_PATRIM_LIQ": "patrimonio_liquido",
    "DT_PATRIM_LIQ": "data_do_patrimonio_liquido",
}
COLUNAS_DA_CARTEIRA = (
    "competencia", "codigo", "isin", "emissor", "tipo", "quantidade", "valor", "disponivel_em",
    "visto_em",
)  # fmt: skip


@dataclass(frozen=True)
class RaioX:
    cnpj: str
    como_era_em: str | None
    cadastro: dict | None
    competencia_da_carteira: str | None
    carteira: list[dict]
    hipotese_do_custo: dict
    custo_da_taxa: dict[int, dict]
    lacunas: list[str] = field(default_factory=list)


def _limpo(valor: object) -> object:
    """Tipo simples: vazio vira None (ausência nunca vira zero), data vira texto ISO."""
    if valor is None or (not isinstance(valor, str) and pd.isna(valor)):
        return None
    if isinstance(valor, pd.Timestamp):
        return valor.date().isoformat()
    if hasattr(valor, "item"):
        return valor.item()
    return valor


def _ler(
    porta: Porta,
    tabela: str,
    filtros: dict[str, object],
    colunas: Sequence[str],
    dia: object = None,
) -> pd.DataFrame | None:
    """A tabela filtrada só com as `colunas` que ela tem; None se a base não tem a tabela."""
    try:
        existentes = set(porta.colunas(tabela))
    except KeyError:
        return None
    usadas = [c for c in colunas if c in existentes]
    return porta.ler(tabela, como_era_em=dia, filtros=filtros, colunas=usadas)


def _cadastro_do_fundo(porta: Porta, cnpj: str) -> pd.Series | None:
    tabela = _ler(
        porta, CADASTRO, {"CNPJ_FUNDO": cnpj}, ["DT_REG", *CAMPOS_DO_CADASTRO]
    )
    if tabela is None or tabela.empty:
        return None
    return tabela.iloc[-1]


def _taxas(linha: pd.Series) -> dict:
    return {
        nome: _limpo(linha[coluna])
        for coluna, nome in CAMPOS_DO_CADASTRO.items()
        if coluna in linha.index
    }


def taxas_do_fundo(porta: Porta, cnpj_formatado: str) -> dict | None:
    """As taxas, a classe, a situação e o patrimônio do retrato do cadastro; None se o fundo não está nele.

    É o retrato mais novo, sem data por linha: quem usa decide a partir de que dia ele vale."""
    linha = _cadastro_do_fundo(porta, cnpj_formatado)
    return None if linha is None else _taxas(linha)


def _custo(cadastro: dict) -> tuple[dict[int, dict], list[str]]:
    taxa = cadastro.get("taxa_administracao_pct_ao_ano")
    if not isinstance(taxa, (int, float)) or math.isnan(taxa):
        return {}, ["taxa de administração: o cadastro da CVM não informa"]
    if taxa < 0 or taxa >= 100:
        return {}, [f"custo da taxa: taxa de administração fora do possível ({taxa})"]
    custos = {}
    for anos in PRAZOS_DO_CUSTO:
        conta = custo_da_taxa(CAPITAL_DO_EXEMPLO, RETORNO_DO_EXEMPLO, taxa / 100, anos)
        custos[anos] = {
            "sem_taxa": conta.sem_taxa,
            "com_taxa": conta.com_taxa,
            "ficou_com_a_taxa": conta.ficou_com_a_taxa,
            "fracao_do_resultado": conta.fracao_do_resultado,
        }
    return custos, []


def _carteira(porta: Porta, cnpj: str, dia: object) -> tuple[str | None, list[dict]]:
    tabela = _ler(porta, CARTEIRAS, {"cnpj_fundo": cnpj}, COLUNAS_DA_CARTEIRA, dia)
    if tabela is None or tabela.empty:
        return None, []
    ultima = tabela["competencia"].max()
    posicoes = tabela[tabela["competencia"] == ultima].sort_values(["codigo", "tipo"])
    linhas = [
        {coluna: _limpo(valor) for coluna, valor in linha.items()}
        for linha in posicoes.to_dict("records")
    ]
    return str(_limpo(ultima)), linhas


def _registro_depois_de(dt_reg: object, dia: pd.Timestamp) -> bool:
    """Se o registro é posterior a `dia`. Data ilegível (texto ruim) não prova nada: não corta o fundo."""
    if dt_reg is None:
        return False
    try:
        registro = pd.to_datetime(dt_reg, errors="coerce", dayfirst=True)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError):
        return False
    return bool(pd.notna(registro) and registro > dia)


def raio_x_de_fundo(porta: Porta, cnpj: str, como_era_em: object = None) -> RaioX:
    """O raio-x do fundo `cnpj`; com `como_era_em` (dia), só o que já era público nesse dia.

    Erro (`ValueError`) se `cnpj` não for um CNPJ."""
    normal = cnpj_.normalizar_cnpj(cnpj)
    if not normal:
        raise ValueError(f"CNPJ inválido: {cnpj!r}")
    formatado = cnpj_.formatar(normal)
    dia = None if como_era_em is None else pd.Timestamp(como_era_em)  # type: ignore[arg-type]
    linha = _cadastro_do_fundo(porta, formatado)
    lacunas: list[str] = []
    cadastro: dict | None = None
    custos: dict[int, dict] = {}
    if linha is None:
        lacunas.append("o fundo não está no cadastro da CVM desta base")
    elif dia is not None and _registro_depois_de(linha["DT_REG"], dia):
        lacunas.append(
            f"o fundo ainda não existia em {dia.date()} (registro posterior)"
        )
        return _resultado(formatado, dia, None, None, [], {}, lacunas)
    elif dia is not None:
        lacunas.append(
            f"taxa e patrimônio em {dia.date()}: o cadastro da CVM é um retrato sem data "
            "pública por linha; as taxas de uma data passada não são observáveis e ficam de fora"
        )
    else:
        cadastro = _taxas(linha)
        custos, avisos = _custo(cadastro)
        lacunas += avisos
    competencia, carteira = _carteira(porta, formatado, dia)
    if not carteira:
        lacunas.append("carteira: sem posição em ações pública nessa data")
    return _resultado(formatado, dia, cadastro, competencia, carteira, custos, lacunas)


def _resultado(
    cnpj: str,
    dia: pd.Timestamp | None,
    cadastro: dict | None,
    competencia: str | None,
    carteira: list[dict],
    custos: dict[int, dict],
    lacunas: list[str],
) -> RaioX:
    return RaioX(
        cnpj=cnpj,
        como_era_em=None if dia is None else dia.date().isoformat(),
        cadastro=cadastro,
        competencia_da_carteira=competencia,
        carteira=carteira,
        hipotese_do_custo={
            "capital": CAPITAL_DO_EXEMPLO,
            "retorno_ao_ano": RETORNO_DO_EXEMPLO,
            "aviso": "conta de exemplo com retorno hipotético; não é previsão nem recomendação",
        },
        custo_da_taxa=custos,
        lacunas=lacunas,
    )
