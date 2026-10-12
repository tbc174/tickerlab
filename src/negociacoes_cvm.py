"""Negociações de pessoas de dentro na B3, pelo formulário VLMO da CVM (Research R2).

O arquivo anual (`vlmo_cia_aberta_AAAA.zip`) traz dois CSV:
- o **índice** (`vlmo_cia_aberta_AAAA.csv`): um documento por empresa e mês, com versão, data de
  entrega e link do original;
- a **posição consolidada** (`vlmo_cia_aberta_con_AAAA.csv`): saldos e movimentações do mês,
  somados por cargo (controlador, conselho, diretoria...), sem o nome de ninguém.

Daqui só saem as **compras e vendas** (à vista, a termo ou sem especificar) de **ações e units da
própria empresa**. Exercício de opção, plano de remuneração, empréstimo, posse e saída de cargo
não são decisões de compra ou venda e ficam de fora. Preço e volume zerados (comuns no arquivo)
viram "não informado", nunca zero. Fica só a versão mais nova de cada documento.
"""

import io
import zipfile

import pandas as pd

from src.negociacoes import COLUNAS, COMPRA, FONTE_VLMO, VENDA, tabela_vazia

URL_DO_VLMO = (
    "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/VLMO/DADOS/vlmo_cia_aberta_{ano}.zip"
)
CODIFICACAO_DA_CVM = "cp1252"
OPERACOES = {
    "Compra à vista": COMPRA,
    "Compra à termo": COMPRA,
    "Compra": COMPRA,
    "Venda à vista": VENDA,
    "Venda à termo": VENDA,
    "Venda": VENDA,
}
CARGOS_DA_CVM = {
    "Controlador ou Vinculado": "controlador",
    "Diretor ou Vinculado": "diretoria",
    "Conselho de Administração ou Vinculado": "conselho",
    "Conselho Fiscal ou Vinculado": "conselho_fiscal",
    "Órgão Estatutário ou Vinculado": "outros_orgaos",
    "": "companhia",  # a própria empresa (ações em tesouraria)
}
ATIVOS = ("Ações", "Units")
DA_PROPRIA_EMPRESA = "Companhia"  # e não a controladora ou uma controlada


def _ler(arquivo: zipfile.ZipFile, contem: str) -> pd.DataFrame:
    nomes = [n for n in arquivo.namelist() if contem in n]
    if not nomes:
        return pd.DataFrame()
    return pd.read_csv(
        arquivo.open(nomes[0]),
        sep=";",
        encoding=CODIFICACAO_DA_CVM,
        encoding_errors="replace",
        dtype=str,
        keep_default_na=False,
    )


def _positivo(serie: pd.Series) -> pd.Series:
    """Número da CVM; zero vira "não informado" (NaN)."""
    numeros = pd.to_numeric(serie, errors="coerce")
    return numeros.where(numeros > 0)


def _so_a_versao_mais_nova(movimentos: pd.DataFrame) -> pd.DataFrame:
    chave = ["CNPJ_Companhia", "Data_Referencia"]
    versao = pd.to_numeric(movimentos["Versao"], errors="coerce").fillna(1).astype(int)
    mais_nova = versao.groupby([movimentos[c] for c in chave]).transform("max")
    return movimentos[versao == mais_nova].assign(versao=versao)


def ler_vlmo(conteudo_do_zip: bytes) -> pd.DataFrame:
    """As compras e vendas de pessoas de dentro de um arquivo anual do VLMO, no formato comum."""
    with zipfile.ZipFile(io.BytesIO(conteudo_do_zip)) as arquivo:
        indice = _ler(arquivo, "vlmo_cia_aberta_20")
        movimentos = _ler(arquivo, "vlmo_cia_aberta_con_")
    if indice.empty or movimentos.empty:
        return tabela_vazia()
    movimentos = _so_a_versao_mais_nova(movimentos)
    movimentos = movimentos[
        (movimentos["Tipo_Empresa"] == DA_PROPRIA_EMPRESA)
        & movimentos["Tipo_Ativo"].isin(ATIVOS)
        & movimentos["Tipo_Movimentacao"].isin(OPERACOES)
        & movimentos["Tipo_Cargo"].isin(CARGOS_DA_CVM)
    ]
    if movimentos.empty:
        return tabela_vazia()
    documentos = indice.assign(
        versao=pd.to_numeric(indice["Versao"], errors="coerce").fillna(1).astype(int)
    )[["CNPJ_Companhia", "Data_Referencia", "versao", "Data_Entrega", "Link_Download"]]
    juntos = movimentos.merge(
        documentos, on=["CNPJ_Companhia", "Data_Referencia", "versao"], how="inner"
    )
    referencia = pd.to_datetime(juntos["Data_Referencia"], errors="coerce")
    quantidade = pd.to_numeric(juntos["Quantidade"], errors="coerce")
    preco = _positivo(juntos["Preco_Unitario"])
    valor = _positivo(juntos["Volume"]).fillna(quantidade * preco)
    tabela = pd.DataFrame(
        {
            "fonte": FONTE_VLMO,
            "documento": juntos["CNPJ_Companhia"].str.strip()
            + "|"
            + referencia.dt.strftime("%Y-%m"),
            "versao": juntos["versao"],
            "cnpj": juntos["CNPJ_Companhia"].str.strip(),
            "empresa": juntos["Nome_Companhia"].str.strip(),
            "cargo": juntos["Tipo_Cargo"].map(CARGOS_DA_CVM),
            "cargo_descricao": "",
            "operacao": juntos["Tipo_Movimentacao"].map(OPERACOES),
            "ativo": (
                juntos["Tipo_Ativo"] + " " + juntos["Caracteristica_Valor_Mobiliario"]
            )
            .str.strip()
            .str[:80],
            "data": pd.to_datetime(
                juntos["Data_Movimentacao"], errors="coerce"
            ).dt.date,
            "referencia": referencia.dt.date,
            "entregue_em": pd.to_datetime(
                juntos["Data_Entrega"], errors="coerce"
            ).dt.date,
            "quantidade": quantidade,
            "preco": preco,
            "valor": valor,
            "moeda": "BRL",
            "plano_10b5_1": None,
            "link": juntos["Link_Download"]
            .str.strip()
            .str.replace("http://", "https://", n=1),
        }
    )
    tabela = tabela.dropna(subset=["referencia", "entregue_em", "quantidade"])
    tabela = tabela[tabela["quantidade"] > 0]
    return tabela[COLUNAS].reset_index(drop=True)
