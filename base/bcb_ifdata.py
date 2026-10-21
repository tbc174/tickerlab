"""IF.data do Banco Central: balanço, resultado, capital e carteira de crédito de cada instituição e
conglomerado, por trimestre (série 3 da base de ML, PR 7).

- **API Olinda** (`IfDataValores` e `IfDataCadastro`), licença ODbL. Saldos em reais, no formato longo
  da fonte: uma linha por instituição, relatório, conta e coluna. O inventário de 14/10/2026 achou:
  - tipo 1 (conglomerado prudencial) desde mar/2014; tipos 2 (conglomerado financeiro) e 3
    (instituição individual) desde mar/2000; o tipo 4 (câmbio) e o relatório 15 (câmbio) ficam fora;
  - só o prudencial tem as carteiras de crédito (relatórios 5 a 16); o financeiro e o individual têm
    os relatórios 1 a 4 (o 5 até 2005) e respondem vazio aos outros. Medido em 14/10/2026: ~193 MB de
    JSON por trimestre no prudencial e ~58 MB nos outros dois; ~50× menor em gzip no acervo;
  - em 2000, 34 linhas de total sem código de instituição (somas da fonte): ficam fora;
  - o nome da coluna vem com a letra da nota numa linha nova ("Disponibilidades \\n(a)"): vira um
    espaço só.
- **"Como era na data":** jun/2026 já estava publicado em 14/10 (106 dias) e set/2026 não; a base usa
  data-base + 120 dias. O BC revisa datas-base já publicadas: cada baixada do arquivista é uma coleta
  e a tabela guarda uma linha por **valor diferente** de cada chave (`base/setoriais/revisoes.py`). O
  primeiro valor vale desde o prazo; a revisão vale só desde o dia em que foi vista (`visto_em`), nunca
  antes (ADR 0027, exigência 3). Limite: o que o BC revisou antes da 1ª coleta guardada não aparece, e
  a linha da primeira coleta sem dia (acervo desligado) fica com `visto_em` vazio. A versão anterior da
  tabela continua guardada como `<AAAAMM>.v<N>` e o SHA-256 de cada resposta fica no manifesto.
- **Ligação com a bolsa:** o cadastro de cada data dá a raiz do CNPJ do líder do conglomerado (ou o
  próprio código, para a instituição individual); a raiz liga ao CNPJ da empresa do FCA e aos tickers
  que valiam no ano (`base/fca.py`). Antes de 2010, sem FCA, a ligação chega ao CNPJ mas não à ação.
"""

import json
import re
from collections.abc import Sequence

import pandas as pd

from base.cnpj import raiz as raiz_do_cnpj
from base.fca import vale_na_data
from base.setoriais import revisoes

API = "https://olinda.bcb.gov.br/olinda/servico/IFDATA/versao/v1/odata/"
PRIMEIRO_ANO = 2000
PRIMEIRA_DATA_PRUDENCIAL = 201403
PRUDENCIAL, FINANCEIRO, INDIVIDUAL = 1, 2, 3
RELATORIOS = (
    1,
    2,
    3,
    4,
    5,
    6,
    7,
    8,
    9,
    10,
    11,
    12,
    13,
    14,
    16,
)  # 15 (câmbio) fica fora
MESES_DA_DATA_BASE = (3, 6, 9, 12)
DIAS_ATE_FICAR_PUBLICO = 120
# por onde a instituição chegou à empresa da bolsa (série 3, PR 8)
PELO_PROPRIO_CNPJ, PELO_LIDER = "próprio CNPJ", "líder do conglomerado"
CHAVE_DOS_VALORES = (
    "data_base",
    "tipo_instituicao",
    "cod_inst",
    "relatorio",
    "grupo",
    "conta",
    "coluna",
)
COLUNAS_DOS_VALORES = {
    "TipoInstituicao": "tipo_instituicao",
    "CodInst": "cod_inst",
    "NumeroRelatorio": "relatorio",
    "NomeRelatorio": "nome_relatorio",
    "Grupo": "grupo",
    "Conta": "conta",
    "NomeColuna": "coluna",
    "DescricaoColuna": "descricao",
    "Saldo": "saldo",
}
COLUNAS_DO_CADASTRO = {
    "CodInst": "cod_inst",
    "NomeInstituicao": "instituicao",
    "Tc": "tipo_controle",
    "Tcb": "tipo_consolidado",
    "Td": "tipo_documento",
    "Sr": "segmento_prudencial",
    "SegmentoTb": "segmento",
    "Atividade": "atividade",
    "Uf": "uf",
    "Municipio": "municipio",
    "CodConglomeradoFinanceiro": "conglomerado_financeiro",
    "CodConglomeradoPrudencial": "conglomerado_prudencial",
    "CnpjInstituicaoLider": "cnpj_lider",
    "DataInicioAtividade": "inicio_atividade",
    "Situacao": "situacao",
}


def datas_base(desde: int, ate: int) -> list[int]:
    """As datas-base trimestrais (`AAAAMM`) de `desde` a `ate`, inclusive."""
    return [
        ano * 100 + mes for ano in range(desde, ate + 1) for mes in MESES_DA_DATA_BASE
    ]


def tipos_da_data(data_base: int) -> tuple[int, ...]:
    """Os tipos de instituição que a data-base tem (o prudencial só desde mar/2014)."""
    if data_base >= PRIMEIRA_DATA_PRUDENCIAL:
        return (PRUDENCIAL, FINANCEIRO, INDIVIDUAL)
    return (FINANCEIRO, INDIVIDUAL)


def endereco_dos_valores(data_base: int, tipo: int, relatorio: int) -> str:
    return (
        f"{API}IfDataValores(AnoMes=@AnoMes,TipoInstituicao=@TipoInstituicao,Relatorio=@Relatorio)"
        f"?@AnoMes={data_base}&@TipoInstituicao={tipo}&@Relatorio='{relatorio}'&$format=json"
    )


def endereco_do_cadastro(data_base: int) -> str:
    return f"{API}IfDataCadastro(AnoMes=@AnoMes)?@AnoMes={data_base}&$format=json"


def _linhas(conteudo_json: bytes) -> pd.DataFrame:
    return pd.DataFrame(json.loads(conteudo_json)["value"])


def _data_da_base(anomes: pd.Series) -> pd.Series:
    return pd.to_datetime(anomes.astype(str), format="%Y%m") + pd.offsets.MonthEnd(0)


def _texto_limpo(serie: pd.Series) -> pd.Series:
    return serie.map(
        lambda v: re.sub(r"\s+", " ", v).strip() if isinstance(v, str) else v
    )


def ler_valores(conteudo_json: bytes) -> pd.DataFrame:
    """Uma resposta de `IfDataValores`, sem as linhas de total da fonte (sem código de instituição)."""
    bruto = _linhas(conteudo_json)
    if bruto.empty:
        return pd.DataFrame(columns=["data_base", *COLUNAS_DOS_VALORES.values()])
    bruto = bruto[bruto["CodInst"].notna()]
    valores = bruto.rename(columns=COLUNAS_DOS_VALORES)[
        list(COLUNAS_DOS_VALORES.values())
    ]
    valores.insert(0, "data_base", _data_da_base(bruto["AnoMes"]))
    for coluna in ("coluna", "descricao", "nome_relatorio"):
        valores[coluna] = _texto_limpo(valores[coluna])
    valores["relatorio"] = valores["relatorio"].astype(int)
    valores["saldo"] = valores["saldo"].astype(float)
    return valores.reset_index(drop=True)


def ler_cadastro(conteudo_json: bytes) -> pd.DataFrame:
    """Uma resposta de `IfDataCadastro`, com a raiz do CNPJ de cada instituição ou conglomerado."""
    bruto = _linhas(conteudo_json)
    cadastro = bruto.rename(columns=COLUNAS_DO_CADASTRO)[
        list(COLUNAS_DO_CADASTRO.values())
    ]
    cadastro.insert(0, "data_base", _data_da_base(bruto["Data"]))
    proprio = cadastro["cod_inst"].where(cadastro["cod_inst"].str.fullmatch(r"\d{8}"))
    cadastro["cnpj_raiz"] = cadastro["cnpj_lider"].where(
        cadastro["cnpj_lider"].notna(), proprio
    )
    return cadastro


def disponivel_em(tabela: pd.DataFrame) -> pd.Series:
    """Desde quando o número era público: data-base + 120 dias (jun/2026 saiu em até 106)."""
    return tabela["data_base"] + pd.Timedelta(days=DIAS_ATE_FICAR_PUBLICO)


def valores_com_revisoes(
    coletas: Sequence[tuple[pd.Timestamp, pd.DataFrame]],
) -> pd.DataFrame:
    """As coletas de um relatório (dia da baixada, `ler_valores`) numa tabela com as revisões do BC.

    Sem o dia (acervo desligado) a coleta entra com `visto_em` vazio: o valor vale desde o prazo."""
    com_prazo = [
        (dia, tabela.assign(disponivel_em=disponivel_em(tabela)))
        for dia, tabela in coletas
    ]
    return revisoes.juntar_coletas(com_prazo, list(CHAVE_DOS_VALORES))


def _raiz(cnpj: pd.Series) -> pd.Series:
    return cnpj.map(raiz_do_cnpj)


def ligacao_dos_bancos(
    cadastro: pd.DataFrame, emissores: pd.DataFrame, tickers: pd.DataFrame
) -> pd.DataFrame:
    """Instituição do IF.data → CNPJ da empresa da bolsa → tickers que valiam na data-base.

    `emissores` e `tickers` são as tabelas da `scripts/carga_fca.py`. A instituição individual cujo
    código é o próprio CNPJ de uma empresa da bolsa liga por ele (o Banco PAN, do conglomerado do
    BTG, tem a BPAN4); as outras, pela raiz do CNPJ do líder do conglomerado. Uma raiz com mais de um
    CNPJ no FCA (não acontece com os bancos de hoje) fica sem ligação, como os conflitos do FCA. O
    ticker vale na data-base só se o FCA que o trouxe já tinha sido entregue (`fca.vale_na_data`).
    """
    empresas = (
        emissores.loc[~emissores["conflito"], ["cnpj"]]
        .drop_duplicates()
        .assign(cnpj_raiz=lambda t: _raiz(t["cnpj"]))
    )
    unicas = empresas[~empresas["cnpj_raiz"].duplicated(keep=False)]
    cnpj_da_raiz = unicas.set_index("cnpj_raiz")["cnpj"]
    ligacao = cadastro[["data_base", "cod_inst", "instituicao", "cnpj_raiz"]].copy()
    proprio = ligacao["cod_inst"].where(ligacao["cod_inst"].str.fullmatch(r"\d{8}"))
    pelo_proprio = proprio.map(cnpj_da_raiz)
    pelo_lider = ligacao["cnpj_raiz"].map(cnpj_da_raiz)
    ligacao["cnpj"] = pelo_proprio.fillna(pelo_lider)
    ligacao["ligado_por"] = (
        pd.Series(PELO_LIDER, index=ligacao.index)
        .where(pelo_lider.notna())
        .mask(pelo_proprio.notna(), PELO_PROPRIO_CNPJ)
    )
    pares = (
        ligacao[["cnpj", "data_base"]]
        .drop_duplicates()
        .merge(tickers[["codigo", "cnpj", "primeiro_visto", "valido_ate"]], on="cnpj")
    )
    vigentes = pares[vale_na_data(pares, pares["data_base"])]
    codigos = (
        vigentes.groupby(["cnpj", "data_base"])["codigo"]
        .agg(lambda c: ",".join(sorted(set(c))))
        .rename("tickers")
        .reset_index()
    )
    return ligacao.merge(codigos, on=["cnpj", "data_base"], how="left")
