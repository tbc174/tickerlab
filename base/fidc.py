"""FIDC desde 2013 e cadastro de fundos, sem dado pessoal (série 3 da base de ML, PR 6; camada 1 da
base do TickerLab Capital, decisão C-07).

- **Informe mensal de FIDC** (`inf_mensal_fidc_*.zip`): uma tabela por quadro do informe (`tab_I` a
  `tab_X_7`), no formato da fonte. O inventário de 14/10/2026 achou 15 tabelas em 2013, 17 em 2019 e 18
  em 2026, com colunas renomeadas; a harmonização entre anos fica para quando um modelo pedir. Cada
  tabela ganha `competencia` e `cnpj_fundo` (o nome da coluna muda com a CVM 175).
- **Cedentes:** a tabela I traz até 9 `CPF_CNPJ_CEDENTE`. Só fica o que é **CNPJ válido** (pelos dígitos
  verificadores, completando os zeros que a CVM tira); CPF, ou valor que não fecha, vira vazio.
- **Cadastro:** o diretor responsável (nome de pessoa) fica fora, inclusive o histórico dele; o gestor
  pessoa física fica só com a marca "PF", sem CPF e sem nome. Fundos cancelados continuam.
- **"Como era na data":** o informe é entregue em até 15 dias; a base usa competência + 45 dias
  (conservador). Cada regravação da CVM vira versão (`base/parquet.py::gravar_com_versoes`).
"""

import io
import re
import zipfile

import pandas as pd

from base import cnpj

CODIFICACAO_DA_CVM = "latin-1"
DIAS_ATE_FICAR_PUBLICO = 45
COLUNAS_DO_FUNDO = (
    "CNPJ_FUNDO_CLASSE",
    "CNPJ_FUNDO",
    "CNPJ_CLASSE",
)  # a 1ª não vazia de cada linha
NOME_DA_TABELA = re.compile(r"inf_mensal_fidc_(tab_[IVX]+(?:_\d+)*)_\d{6}\.csv$")
DIGITOS_DO_CNPJ, DIGITOS_DO_CPF = 14, 11
PESSOA_FISICA = "PF"
# cadastro: colunas com nome de pessoa (saem) e as do gestor (vazias quando é pessoa física)
COLUNAS_DE_PESSOA = ("DIRETOR", "Diretor")
GESTOR = (
    ("PF_PJ_GESTOR", "CPF_CNPJ_GESTOR", "GESTOR"),
    ("Tipo_Pessoa_Gestor", "CPF_CNPJ_Gestor", "Gestor"),
)
HISTORICO_DE_PESSOA = ("diretor_resp",)


def _digito(numeros: str, pesos: range | list[int]) -> int:
    resto = sum(int(n) * p for n, p in zip(numeros, pesos, strict=True)) % 11
    return 0 if resto < 2 else 11 - resto


def _cpf_valido(digitos: str) -> bool:
    if len(digitos) != DIGITOS_DO_CPF or digitos == digitos[0] * DIGITOS_DO_CPF:
        return False
    primeiro = _digito(digitos[:9], range(10, 1, -1))
    segundo = _digito(digitos[:10], range(11, 1, -1))
    return digitos[9:] == f"{primeiro}{segundo}"


def documento_de_empresa(valor: object) -> str | None:
    """O CNPJ formatado, se o valor for um CNPJ válido e não puder ser um CPF; senão, None."""
    if not isinstance(valor, str):
        return None
    com_letras = cnpj.completo(valor)
    if com_letras and cnpj.tem_letra(com_letras):  # com letra é CNPJ, nunca CPF
        return cnpj.formatar(com_letras) if cnpj.dv_confere(com_letras) else None
    digitos = re.sub(r"\D", "", valor)
    if not digitos or len(digitos) > DIGITOS_DO_CNPJ:
        return None
    if len(digitos) <= DIGITOS_DO_CPF and _cpf_valido(digitos.zfill(DIGITOS_DO_CPF)):
        return None  # na dúvida entre CPF e CNPJ, é dado pessoal
    numerico = digitos.zfill(DIGITOS_DO_CNPJ)
    return cnpj.formatar(numerico) if cnpj.dv_confere(numerico) else None


def _ler_csv(
    arquivo: zipfile.ZipFile | None, nome: str, conteudo: bytes | None = None
) -> pd.DataFrame:
    fonte = io.BytesIO(conteudo) if conteudo is not None else arquivo.open(nome)  # type: ignore[union-attr]
    return pd.read_csv(
        fonte, sep=";", encoding=CODIFICACAO_DA_CVM, encoding_errors="replace", dtype=str,
        keep_default_na=False,
    ).replace("", None)  # fmt: skip


def _sem_cpf(tabela: pd.DataFrame) -> pd.DataFrame:
    for coluna in [c for c in tabela.columns if "CPF" in c.upper()]:
        tabela[coluna] = tabela[coluna].map(documento_de_empresa)
    return tabela


def _normalizar_informe(tabela: pd.DataFrame) -> pd.DataFrame:
    colunas_do_fundo = [c for c in COLUNAS_DO_FUNDO if c in tabela.columns]
    tabela = _sem_cpf(tabela)
    tabela.insert(
        0, "competencia", pd.to_datetime(tabela["DT_COMPTC"], errors="coerce")
    )
    # meses de cabeçalhos diferentes, juntados num só quadro, deixam as duas colunas:
    # vale a primeira não vazia de cada linha
    cnpj_fundo = tabela[colunas_do_fundo].bfill(axis=1).iloc[:, 0]
    tabela = tabela.drop(columns=colunas_do_fundo)
    tabela.insert(1, "cnpj_fundo", cnpj_fundo.str.strip())
    return tabela


def quadros_do_arquivo(conteudo_do_zip: bytes) -> set[str]:
    """Os quadros (`tab_I`...) que um arquivo do informe traz, sem ler os dados."""
    with zipfile.ZipFile(io.BytesIO(conteudo_do_zip)) as arquivo:
        return {
            a.group(1) for n in arquivo.namelist() if (a := NOME_DA_TABELA.search(n))
        }


def ler_informe(conteudo_do_zip: bytes) -> dict[str, pd.DataFrame]:
    """Uma tabela por quadro do informe (`tab_I`...), juntando os meses do arquivo, sem CPF."""
    partes: dict[str, list[pd.DataFrame]] = {}
    with zipfile.ZipFile(io.BytesIO(conteudo_do_zip)) as arquivo:
        for nome in sorted(arquivo.namelist()):
            achado = NOME_DA_TABELA.search(nome)
            if achado:
                partes.setdefault(achado.group(1), []).append(_ler_csv(arquivo, nome))
    return {
        chave: _normalizar_informe(pd.concat(lista, ignore_index=True))
        for chave, lista in partes.items()
    }


def disponivel_em(tabela: pd.DataFrame) -> pd.Series:
    """Desde quando o informe era público: competência + 45 dias (o prazo de entrega é 15)."""
    return tabela["competencia"] + pd.Timedelta(days=DIAS_ATE_FICAR_PUBLICO)


def _sem_pessoas(tabela: pd.DataFrame) -> pd.DataFrame:
    tabela = tabela.drop(columns=[c for c in COLUNAS_DE_PESSOA if c in tabela.columns])
    for tipo, documento, nome in GESTOR:
        if tipo in tabela.columns:
            pessoa = tabela[tipo].eq(PESSOA_FISICA)
            for coluna in (documento, nome):
                if coluna in tabela.columns:
                    tabela[coluna] = tabela[coluna].where(~pessoa, None)
    return tabela


def ler_cadastro_de_fundos(conteudo_csv: bytes) -> pd.DataFrame:
    """O cadastro de fundos da CVM (`cad_fi.csv`), sem diretor e sem gestor pessoa física."""
    return _sem_pessoas(_ler_csv(None, "", conteudo_csv))


def ler_historico_do_cadastro(conteudo_do_zip: bytes) -> dict[str, pd.DataFrame]:
    """As tabelas de `cad_fi_hist.zip` (admin, auditor, classe...), menos a do diretor responsável."""
    tabelas = {}
    with zipfile.ZipFile(io.BytesIO(conteudo_do_zip)) as arquivo:
        for nome in arquivo.namelist():
            chave = nome.removeprefix("cad_fi_hist_").removesuffix(".csv")
            if chave not in HISTORICO_DE_PESSOA:
                tabelas[chave] = _sem_pessoas(_ler_csv(arquivo, nome))
    return tabelas


def ler_registro_de_fundos(conteudo_do_zip: bytes) -> dict[str, pd.DataFrame]:
    """`registro_fundo_classe.zip` (CVM 175): fundo, classe e subclasse, sem diretor nem gestor PF."""
    with zipfile.ZipFile(io.BytesIO(conteudo_do_zip)) as arquivo:
        return {
            nome.removesuffix(".csv"): _sem_pessoas(_ler_csv(arquivo, nome))
            for nome in arquivo.namelist()
        }
