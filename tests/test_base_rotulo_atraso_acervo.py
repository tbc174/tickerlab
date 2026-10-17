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


def _guardar_originais() -> set[str]:
    """Duas DFPs (a de 2024 da empresa B atrasou; a A não entregou a sua) e o cadastro."""
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
    return {
        _guardar("cvm-hist-dfp", PASTA_DFP + "dfp_cia_aberta_2023.zip", dfp_2023),
        _guardar("cvm-hist-dfp", PASTA_DFP + "dfp_cia_aberta_2024.zip", dfp_2024),
        _guardar("cvm-cadastros", URL_DO_CADASTRO, cadastro),
    }


def test_monta_o_rotulo_dos_originais_com_manifesto(banco, tmp_path, monkeypatch):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    shas = _guardar_originais()
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
    assert set(manifesto["fora_dos_exemplos"]) == set(rotulo.MOTIVOS_FORA)
    assert all(
        contagem == {"exemplos": 0, "atrasou": 0}
        for contagem in manifesto["fora_dos_exemplos"].values()
    )
    assert conferir_tabela(arquivo)


def test_sem_originais_nada_e_gravado(banco, tmp_path):
    with banco.connect() as conexao:
        assert rotulo.montar(conexao, tmp_path / "base", AGORA) == 0
    assert not (tmp_path / "base" / "rotulos_atraso").exists()


def test_mesmos_originais_e_mesmo_dia_dao_o_mesmo_hash(banco, tmp_path, monkeypatch):
    """ADR 0027, exigência 9: o rótulo é função dos originais e do dia, não da hora da montagem."""
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    _guardar_originais()
    manha = datetime(2026, 10, 15, 9, tzinfo=UTC)  # 6h em Brasília
    noite = datetime(2026, 10, 16, 2, tzinfo=UTC)  # 23h do mesmo dia em Brasília
    with banco.connect() as conexao:
        rotulo.montar(conexao, tmp_path / "manha", manha)
        rotulo.montar(conexao, tmp_path / "noite", noite)
        rotulo.montar(
            conexao, tmp_path / "outro_dia", datetime(2026, 10, 17, 12, tzinfo=UTC)
        )

    def _hash(pasta: str) -> str:
        arquivo = tmp_path / pasta / "rotulos_atraso" / "rotulos_atraso.json"
        return json.loads(arquivo.read_text(encoding="utf-8"))["sha256_da_tabela"]

    assert _hash("manha") == _hash("noite")
    assert _hash("manha") != _hash(
        "outro_dia"
    )  # outro dia, outra montagem (`montado_em`)


def test_rotular_com_fonte_nao_comercial_da_erro(banco, tmp_path, monkeypatch):
    """A trava das licenças (ADR 0008, Emenda 1): se a CVM deixasse de permitir uso comercial, o
    rótulo não seria montado (erro, não aviso)."""
    import pytest

    from src.banco import coletas

    _guardar_originais()
    monkeypatch.setitem(coletas.REVENDA, "cvm", coletas.NAO_COMERCIAL)
    with banco.connect() as conexao, pytest.raises(coletas.LicencaNaoPermiteError):
        rotulo.montar(conexao, tmp_path / "base", AGORA)
    assert not (tmp_path / "base").exists()
