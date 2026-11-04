"""Informe mensal dos Fiagro da CVM (linha 227 da fila; fonte `cvm-fiagro`): um ZIP por mês
(`inf_mensal_fiagro_AAAAMM.zip`) com o informe da classe e o das subclasses.

- **Formato** (conferido em 04/11/2026 nos ZIPs guardados, de 2025-10 a 2026-09): `;`, Latin-1, 133
  colunas no informe da classe. Aqui entram a identificação, o número de cotistas, o balanço resumido, a
  rentabilidade, as taxas e a carteira por tipo de ativo. Contato (e-mail, telefone, site) e o nome do
  administrador e do gestor ficam de fora; administrador e gestor entram só pelo CNPJ.
- **Uma linha por classe e mês**; reenvio traz `Versao` maior e vale o de maior versão.
- **Só classe com CNPJ de DV certo** (ADR 0075); o que não fecha é contado.
- **Sem olhar o futuro**: `disponivel_em` é a `Data_Entrega` do informe (o dia em que ele chegou à CVM),
  nunca a `Data_Referencia` (o mês a que ele se refere).

Sem Streamlit; pandas só.
"""

import io
import zipfile

import pandas as pd

from base import cnpj as cnpjs

FONTE = "cvm-fiagro"
SEPARADOR = ";"
CODIFICACAO = "latin-1"
PREFIXO_DA_CLASSE = (
    "inf_mensal_fiagro_2"  # `inf_mensal_fiagro_subclasse_*` não casa (sem o "2" do ano)
)
TEXTOS = {
    "Nome_Classe": "nome_da_classe",
    "Publico_Alvo": "publico_alvo",
    "Codigo_ISIN": "codigo_isin",
    "Mercado_Negociacao": "mercado_de_negociacao",
}
CNPJS = {
    "CNPJ_Classe": "cnpj",
    "CNPJ_Administrador": "cnpj_administrador",
    "CNPJ_Gestor": "cnpj_gestor",
}
NUMEROS = {
    "Numero_Cotistas": "cotistas",
    "Valor_Ativo": "valor_do_ativo",
    "Patrimonio_Liquido": "patrimonio_liquido",
    "Cotas_Emitidas": "cotas_emitidas",
    "Valor_Patrimonial_Cotas": "valor_patrimonial_da_cota",
    "Percentual_Despesas_Taxa_Administracao": "taxa_de_administracao_pct",
    "Percentual_Despesas_Taxa_Gestao": "taxa_de_gestao_pct",
    "Rentabilidade_Efetiva_Mes": "rentabilidade_efetiva_no_mes",
    "Rentabilidade_Patrimonial_Mes": "rentabilidade_patrimonial_no_mes",
    "Dividend_Yield_Mes": "dividend_yield_no_mes",
    "Total_Investido": "total_investido",
    "Imoveis_Rurais": "imoveis_rurais",
    "CRA": "cra",
    "CRI": "cri",
    "LCA": "lca",
    "LCI": "lci",
    "Total_Passivo": "total_do_passivo",
}
DATAS = {"Data_Referencia": "referencia", "Data_Entrega": "disponivel_em"}
COLUNAS = [
    "cnpj", "cnpj_basico", "referencia", "versao", *TEXTOS.values(), "cnpj_administrador",
    "cnpj_gestor", *NUMEROS.values(), "disponivel_em",
]  # fmt: skip


def _arquivo_da_classe(zip_: zipfile.ZipFile) -> str | None:
    return next((n for n in zip_.namelist() if n.startswith(PREFIXO_DA_CLASSE)), None)


def _cnpj_ou_vazio(serie: pd.Series) -> pd.Series:
    completos = serie.map(cnpjs.completo)
    certos = completos.map(lambda c: isinstance(c, str) and cnpjs.dv_confere(c))
    return completos.where(certos.astype(bool), None)


def _formatado(serie: pd.Series) -> pd.Series:
    return _cnpj_ou_vazio(serie).map(
        lambda c: cnpjs.formatar(c) if isinstance(c, str) else None
    )


def ler_mes(conteudo: bytes) -> tuple[pd.DataFrame, dict[str, int]]:
    """O informe da classe de um ZIP mensal e a contagem do que ficou de fora."""
    with zipfile.ZipFile(io.BytesIO(conteudo)) as zip_:
        nome = _arquivo_da_classe(zip_)
        if nome is None:
            return pd.DataFrame(columns=COLUNAS), {
                "linhas": 0,
                "cnpj_invalido": 0,
                "versao_antiga": 0,
            }
        bruta = pd.read_csv(
            io.BytesIO(zip_.read(nome)),
            sep=SEPARADOR,
            encoding=CODIFICACAO,
            dtype=str,
            keep_default_na=False,
        )
    for coluna in [*TEXTOS, *CNPJS, *NUMEROS, *DATAS, "Versao"]:
        if coluna not in bruta:
            bruta[coluna] = ""  # coluna que a CVM não mandou naquele mês
    bruta = bruta.apply(lambda serie: serie.str.strip())
    cnpj = _cnpj_ou_vazio(bruta["CNPJ_Classe"])
    valido = cnpj.notna()
    tabela = bruta[valido].assign(CNPJ_Classe=cnpj[valido])
    tabela = tabela.assign(
        _versao=pd.to_numeric(tabela["Versao"], errors="coerce").fillna(0)
    )
    tabela = tabela.sort_values("_versao").drop_duplicates(
        ["CNPJ_Classe", "Data_Referencia"], keep="last"
    )
    antiga = int(valido.sum()) - len(tabela)
    pronta = pd.DataFrame(
        {
            "cnpj": tabela["CNPJ_Classe"].map(cnpjs.formatar),
            "cnpj_basico": tabela["CNPJ_Classe"].str[: cnpjs.TAMANHO_DA_RAIZ],
            "versao": tabela["_versao"].astype("Int64"),
            **{nova: tabela[velha].replace("", None) for velha, nova in TEXTOS.items()},
            "cnpj_administrador": _formatado(tabela["CNPJ_Administrador"]),
            "cnpj_gestor": _formatado(tabela["CNPJ_Gestor"]),
            **{
                nova: pd.to_numeric(tabela[velha], errors="coerce")
                for velha, nova in NUMEROS.items()
            },
            **{
                nova: pd.to_datetime(tabela[velha], format="%Y-%m-%d", errors="coerce")
                for velha, nova in DATAS.items()
            },
        }
    )[COLUNAS].reset_index(drop=True)
    contagem = {
        "linhas": len(bruta),
        "cnpj_invalido": int((~valido).sum()),
        "versao_antiga": antiga,
    }
    return pronta, contagem
