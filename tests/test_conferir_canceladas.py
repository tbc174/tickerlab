"""Conferência medida das canceladas no acervo e na base (ADR 0027, exigência 4; critério de pronto
do modelo 8). Sem internet: os originais da CVM e as tabelas da base são montados à mão."""

import io
import zipfile

import pandas as pd

from base.dicionario import TABELAS
from scripts import conferir_canceladas
from src.banco.coletas import com_registro

ATIVA = "11.111.111/0001-11"
SAIU = "22.222.222/0001-22"
PERDIDA = "33.333.333/0001-33"
DADOS = "https://dados.cvm.gov.br/dados/CIA_ABERTA/"


def _zip(nome: str, cabecalho: str, cnpjs: list[str]) -> bytes:
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as arquivo:
        linhas = [cabecalho, *(f"{cnpj};x" for cnpj in cnpjs)]
        arquivo.writestr(nome, "\n".join(linhas).encode("latin-1"))
    return saida.getvalue()


def _guardar(fonte: str, url: str, conteudo: bytes) -> None:
    com_registro(fonte, lambda _url: conteudo)(url)


def _acervo() -> None:
    cadastro = (
        "CNPJ_CIA;DENOM_SOCIAL;DT_REG;DT_CANCEL;MOTIVO_CANCEL;SIT;SETOR_ATIV;UF\n"
        f"{ATIVA};ATIVA;2001-01-01;;;ATIVO;Energia;SP\n"
        f"{SAIU};SAIU;2001-01-01;2015-06-30;Cancelamento voluntário;CANCELADA;Têxtil;SP\n"
        f"{PERDIDA};PERDIDA;2001-01-01;2016-06-30;Cancelamento voluntário;CANCELADA;Bancos;RJ\n"
    ).encode("latin-1")
    _guardar("cvm-cadastros", DADOS + "CAD/DADOS/cad_cia_aberta.csv", cadastro)
    _guardar(
        "cvm-hist-dfp",
        DADOS + "DOC/DFP/DADOS/dfp_cia_aberta_2014.zip",
        _zip("dfp_cia_aberta_2014.csv", "CNPJ_CIA;X", [ATIVA, SAIU, PERDIDA]),
    )
    _guardar(
        "cvm-hist-fca",
        DADOS + "DOC/FCA/DADOS/fca_cia_aberta_2014.zip",
        _zip("fca_cia_aberta_auditor_2014.csv", "CNPJ_Companhia;X", [ATIVA, SAIU]),
    )
    _guardar(
        "cvm-hist-ipe",
        DADOS + "DOC/IPE/DADOS/ipe_cia_aberta_2014.zip",
        _zip("ipe_cia_aberta_2014.csv", "CNPJ_Companhia;X", [SAIU]),
    )


def _tabela(pasta, nome: str, cnpjs: list[str]) -> None:
    """A tabela com todas as colunas do dicionário (a porta monta as views com elas), vazias."""
    tabela = "demonstracoes_como_era" if nome == "demonstracoes" else nome
    colunas = {coluna: [None] * len(cnpjs) for coluna in TABELAS[tabela].colunas}
    (pasta / nome).mkdir(parents=True, exist_ok=True)
    pd.DataFrame({**colunas, "cnpj": cnpjs}).astype("string").to_parquet(
        pasta / nome / "2014.parquet"
    )


def test_cancelada_que_a_fonte_tem_e_a_base_nao_faz_a_conferencia_falhar(
    banco, tmp_path
):
    _acervo()
    base = tmp_path / "base"
    _tabela(base, "demonstracoes", [ATIVA, SAIU])  # a PERDIDA está no índice da CVM
    _tabela(base, "auditores", [ATIVA, SAIU])
    _tabela(base, "eventos", [SAIU])

    assert conferir_canceladas.main(["--pasta", str(base)]) == 1

    conferencia = pd.read_csv(
        base / "conferencias" / "canceladas.csv", sep=";", dtype=str
    )
    situacao = conferencia.set_index(["tabela", "cnpj"])["situacao"].to_dict()
    assert situacao == {
        ("demonstracoes_como_era", SAIU): "na_tabela",
        ("demonstracoes_como_era", PERDIDA): "perdida_na_montagem",
        ("auditores", SAIU): "na_tabela",
        ("auditores", PERDIDA): "sem_documento_na_fonte",
        ("eventos", SAIU): "na_tabela",
        ("eventos", PERDIDA): "sem_documento_na_fonte",
    }

    _tabela(base, "demonstracoes", [ATIVA, SAIU, PERDIDA])
    assert conferir_canceladas.main(["--pasta", str(base)]) == 0


def test_sem_cadastro_no_acervo_a_conferencia_falha(banco, tmp_path):
    assert conferir_canceladas.main(["--pasta", str(tmp_path)]) == 1


def test_cada_falta_explicada_a_mao_tem_motivo_e_data():
    explicadas = pd.read_csv(conferir_canceladas.EXPLICADAS, sep=";", dtype=str)
    assert set(explicadas["tabela"]) <= set(conferir_canceladas.FONTES)
    assert explicadas[["cnpj", "explicacao", "conferido_em"]].notna().all(axis=None)
    assert not explicadas.duplicated(["tabela", "cnpj"]).any()
