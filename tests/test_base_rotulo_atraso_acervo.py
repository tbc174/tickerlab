"""O rótulo de atraso montado dos originais do acervo (plano do modelo 8, Tarefa 2.2)."""

import hashlib
import io
import json
import zipfile
from datetime import UTC, datetime

import pandas as pd

from base.modelos.atraso import rotulo
from base.parquet import conferir_tabela
from src.banco.coletas import com_registro

AGORA = datetime(2026, 10, 15, 6, tzinfo=UTC)
PASTA_DFP = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/DADOS/"
URL_DO_CADASTRO = (
    "https://dados.cvm.gov.br/dados/CIA_ABERTA/CAD/DADOS/cad_cia_aberta.csv"
)
CABECALHO = (
    "CNPJ_CIA;DT_REFER;VERSAO;DENOM_CIA;CD_CVM;CATEG_DOC;ID_DOC;DT_RECEB;LINK_DOC\n"
)


def _zip_da_dfp(ano: int, *linhas: str) -> bytes:
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as z:
        z.writestr(
            f"dfp_cia_aberta_{ano}.csv", (CABECALHO + "".join(linhas)).encode("latin-1")
        )
    return saida.getvalue()


def _guardar(fonte: str, url: str, conteudo: bytes) -> str:
    com_registro(fonte, lambda _url: conteudo)(url)
    return hashlib.sha256(conteudo).hexdigest()


def test_monta_o_rotulo_dos_originais_com_manifesto(banco, tmp_path, monkeypatch):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    dfp_2023 = _zip_da_dfp(
        2023,
        "11.111.111/0001-11;2023-12-31;1;EMPRESA A;1;DFP;1;2024-03-25;http://x?d=1\n",
    )
    dfp_2024 = _zip_da_dfp(
        2024,
        "22.222.222/0001-22;2024-12-31;1;EMPRESA B;2;DFP;2;2025-04-10;http://x?d=2\n",
    )
    cadastro = (
        "CNPJ_CIA;DENOM_SOCIAL;DT_REG;DT_CANCEL;MOTIVO_CANCEL;SIT;SETOR_ATIV;UF\n"
        "11.111.111/0001-11;EMPRESA A;2001-01-01;;;ATIVO;Energia;SP\n"
        "22.222.222/0001-22;EMPRESA B;2001-01-01;;;ATIVO;Bancos;RJ\n"
    ).encode("latin-1")
    shas = {
        _guardar("cvm-hist-dfp", PASTA_DFP + "dfp_cia_aberta_2023.zip", dfp_2023),
        _guardar("cvm-hist-dfp", PASTA_DFP + "dfp_cia_aberta_2024.zip", dfp_2024),
        _guardar("cvm-cadastros", URL_DO_CADASTRO, cadastro),
    }
    with banco.connect() as conexao:
        linhas = rotulo.montar(conexao, tmp_path / "base", AGORA)

    arquivo = tmp_path / "base" / "rotulos_atraso" / "rotulos_atraso.parquet"
    tabela = pd.read_parquet(arquivo)
    assert (
        linhas == len(tabela) == 3
    )  # A 2023, B 2024 (atrasou) e A 2024 (não entregou)
    assert tabela["atrasou"].tolist() == [False, True, True]
    assert {"montado_em", "versao_do_codigo"} <= set(tabela.columns)
    assert set(tabela["versao_do_codigo"]) == {"0123abc"}
    manifesto = json.loads(arquivo.with_suffix(".json").read_text(encoding="utf-8"))
    assert {o["sha256"] for o in manifesto["origens"]} == shas
    assert manifesto["fora_dos_exemplos"] == {
        "prazo_antes_do_primeiro_registro": {"exemplos": 0, "atrasou": 0}
    }
    assert conferir_tabela(arquivo)


def test_sem_originais_nada_e_gravado(banco, tmp_path):
    with banco.connect() as conexao:
        assert rotulo.montar(conexao, tmp_path / "base", AGORA) == 0
    assert not (tmp_path / "base" / "rotulos_atraso").exists()
