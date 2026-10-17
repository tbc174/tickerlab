"""Cadastro de cada companhia **como era na data**, pelo FCA da CVM (critério de pronto do modelo 8, nota i).

O `cad_cia_aberta.csv` (`base/cadastro.py`) é o retrato de hoje: o setor e a categoria que ele traz
são os de agora, e usá-los para prever o passado é olhar o futuro. O FCA (formulário cadastral) de
cada ano traz, na tabela `fca_cia_aberta_geral`, a categoria do registro (A ou B), o setor de
atividade, a espécie do controle acionário e o mês de fim do exercício **como a companhia informou
naquele formulário**, e o arquivo principal dá o dia em que a CVM recebeu o documento (`DT_RECEB`,
ligado pelo `ID_DOC`): é o `conhecido_em`.

Como em `base/auditores.py`, o arquivo anual só traz a **última versão** de cada formulário: a data
que vale é a dessa versão, que pode ser mais tarde que a primeira notícia, nunca mais cedo. O FCA
mandado durante o pedido de registro só fica público no registro (`historico`, `data_publica`).
"""

import io
import zipfile

import pandas as pd

CODIFICACAO_DA_CVM = "latin-1"
COLUNAS = (
    "cnpj", "empresa", "referencia", "versao", "id_documento", "conhecido_em", "categoria",
    "setor", "controle_acionario", "mes_fim_do_exercicio",
)  # fmt: skip
# "Categoria A" → "A"; o resto (vazio, texto novo) fica como veio
CATEGORIA = {"Categoria A": "A", "Categoria B": "B"}


def _ler(arquivo: zipfile.ZipFile, trecho: str) -> pd.DataFrame:
    nome = next(n for n in arquivo.namelist() if trecho in n)
    return pd.read_csv(
        arquivo.open(nome), sep=";", encoding=CODIFICACAO_DA_CVM, dtype=str,
        keep_default_na=False,
    )  # fmt: skip


def _texto(serie: pd.Series) -> pd.Series:
    return serie.str.strip().replace("", None)


def ler_geral_do_fca(conteudo_do_zip: bytes) -> pd.DataFrame:
    """Os dados gerais de um arquivo anual do FCA, um por formulário, com a data de entrega."""
    with zipfile.ZipFile(io.BytesIO(conteudo_do_zip)) as arquivo:
        bruto = _ler(arquivo, "_geral_")
        principal = _ler(arquivo, "fca_cia_aberta_2")
    recebido = dict(
        zip(principal["ID_DOC"].str.strip(), principal["DT_RECEB"], strict=True)
    )
    id_documento = bruto["ID_Documento"].str.strip()
    categoria = _texto(bruto["Categoria_Registro_CVM"])
    tabela = pd.DataFrame(
        {
            "cnpj": bruto["CNPJ_Companhia"].str.strip(),
            "empresa": _texto(bruto["Nome_Empresarial"]),
            "referencia": pd.to_datetime(
                bruto["Data_Referencia"], errors="coerce"
            ).dt.date,
            "versao": pd.to_numeric(bruto["Versao"], errors="coerce"),
            "id_documento": id_documento,
            "conhecido_em": pd.to_datetime(
                id_documento.map(recebido), errors="coerce"
            ).dt.date,
            "categoria": categoria.map(lambda c: CATEGORIA.get(c, c)),
            "setor": _texto(bruto["Setor_Atividade"]),
            "controle_acionario": _texto(bruto["Especie_Controle_Acionario"]),
            "mes_fim_do_exercicio": pd.to_numeric(
                bruto["Mes_Encerramento_Exercicio_Social"], errors="coerce"
            ).astype("Int64"),
        }
    )
    tabela = tabela.dropna(subset=["conhecido_em", "referencia"])
    # a mesma versão entregue duas vezes (como no FCA de 2021 dos auditores): vale a primeira entrega
    tabela = tabela.sort_values(["conhecido_em", "id_documento"], kind="stable")
    tabela = tabela.drop_duplicates(["cnpj", "referencia", "versao"])
    return tabela[list(COLUNAS)].reset_index(drop=True)
