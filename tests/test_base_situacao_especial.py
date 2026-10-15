"""B2, parte 2: "situação especial" do CNPJ (falência, recuperação judicial, liquidação) por empresa."""

import io
import zipfile
from datetime import UTC, datetime

import pandas as pd

from base import historico, rotulos
from base.ancoragem import parquets_sem_manifesto
from src.banco import coletas
from src.banco.coletas import com_registro

AGORA = datetime(2026, 10, 14, 7, tzinfo=UTC)
URL = (
    "https://arquivos.receitafederal.gov.br/public.php/dav/files/TOKEN/Dados/Cadastros/CNPJ/"
    "2026-10/Estabelecimentos0.zip"
)


def _estabelecimento(basico, ordem, dv, matriz, situacao, data):
    campos = [basico, ordem, dv, matriz] + ["X"] * 24 + [situacao, data]
    campos[27] = "email.pessoal@exemplo.com"  # dado pessoal: nunca pode sair
    return ";".join(f'"{c}"' for c in campos)


def _zip(*linhas: str) -> bytes:
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as z:
        z.writestr(
            "K3241.K03200Y7.D61010.ESTABELE", "\n".join(linhas).encode("latin-1")
        )
    return saida.getvalue()


def test_so_estabelecimentos_com_situacao_especial_e_sem_dado_pessoal():
    tabela = rotulos.ler_situacao_especial_do_cnpj(
        _zip(
            _estabelecimento("33000167", "0001", "01", "1", "", ""),
            _estabelecimento(
                "11111111", "0001", "11", "1", "RECUPERACAO JUDICIAL", "20230119"
            ),
            _estabelecimento("22222222", "0002", "22", "2", "FALIDO", "20210311"),
            _estabelecimento(
                "44444444", "0001", "44", "1", "ESPOLIO EV 407", "20200101"
            ),
            _estabelecimento(
                "55555555", "0001", "55", "1", "EM LIQUID.EXTRA-JUDICIAL", "20190101"
            ),
        )
    )
    assert list(tabela["cnpj"]) == [
        "11.111.111/0001-11",
        "22.222.222/0002-22",
        "44.444.444/0001-44",
        "55.555.555/0001-55",
    ]
    assert list(tabela["rotulo"]) == [
        "recuperacao_judicial",
        "falencia",
        None,
        "liquidacao_extrajudicial",
    ]
    assert list(tabela["matriz"]) == [True, False, True, True]
    assert str(tabela["data_situacao_especial"].iloc[0]) == "2023-01-19"
    assert "email.pessoal@exemplo.com" not in tabela.to_csv()


def test_retrato_do_mes_vira_parquet_com_a_origem(banco, tmp_path, monkeypatch):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    conteudo = _zip(
        _estabelecimento(
            "11111111", "0001", "11", "1", "RECUPERACAO JUDICIAL", "20230119"
        )
    )
    com_registro("rfb-cnpj", lambda _url: conteudo)(URL)
    with banco.connect() as conexao:
        linhas = rotulos.montar_situacao_especial(conexao, tmp_path / "base", AGORA)
    assert linhas == {"2026-10": 1}
    tabela = pd.read_parquet(
        tmp_path / "base" / "cnpj_situacao_especial" / "2026-10.parquet"
    )
    assert tabela["mes_do_retrato"].iloc[0] == "2026-10"
    assert len(tabela["origem_sha256"].iloc[0]) == 64
    assert tabela["versao_do_codigo"].iloc[0] == "0123abc"
    assert parquets_sem_manifesto(tmp_path / "base") == []


def test_arquivos_que_nao_sao_de_estabelecimentos_ficam_de_fora(banco, tmp_path):
    com_registro("rfb-cnpj", lambda _url: b"PK")(
        URL.replace("Estabelecimentos0", "Socios0")
    )
    with banco.connect() as conexao:
        assert rotulos.montar_situacao_especial(conexao, tmp_path / "base", AGORA) == {}


def test_historico_usa_a_mesma_busca_de_originais():
    assert historico.originais_mais_recentes is coletas.originais_mais_recentes


def test_comando_monta_o_retrato_do_cnpj(banco, tmp_path, monkeypatch):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    from scripts import montar_base_historica

    conteudo = _zip(
        _estabelecimento("11111111", "0001", "11", "1", "FALIDO", "20210311")
    )
    com_registro("rfb-cnpj", lambda _url: conteudo)(URL)
    assert (
        montar_base_historica.main(
            ["cnpj_situacao_especial", "--pasta", str(tmp_path / "b")]
        )
        == 0
    )
    assert (tmp_path / "b" / "cnpj_situacao_especial" / "2026-10.parquet").exists()
