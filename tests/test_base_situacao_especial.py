"""B2, parte 2: "situação especial" do CNPJ (falência, recuperação judicial, liquidação) por empresa."""

import io
import zipfile
from datetime import UTC, datetime

import pandas as pd

from base import historico, rotulos
from base.ancoragem import parquets_sem_manifesto
from src import acervo
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


def _montar_visto_em(banco, tmp_path, *baixadas: datetime) -> pd.DataFrame:
    """O retrato de 2026-10 baixado nas datas dadas (o mesmo conteúdo), montado."""
    conteudo = _zip(
        _estabelecimento("11111111", "0001", "11", "1", "FALIDO", "20210311")
    )
    with banco.begin() as conexao:
        for quando in baixadas:
            coletas.registrar(
                conexao,
                "rfb-cnpj",
                URL,
                conteudo,
                "ok",
                agora=quando,
                caminho_do_original=acervo.guardar_original(
                    "rfb-cnpj", URL, conteudo, quando
                ),
            )
    with banco.connect() as conexao:
        rotulos.montar_situacao_especial(conexao, tmp_path / "base", AGORA)
    return pd.read_parquet(
        tmp_path / "base" / "cnpj_situacao_especial" / "2026-10.parquet"
    )


def test_retrato_visto_dentro_do_mes_vale_do_fim_do_mes(banco, tmp_path):
    """Achado 3a do Codex (17/10/2026): o mês do arquivo não é a data em que ele ficou público."""
    tabela = _montar_visto_em(banco, tmp_path, datetime(2026, 10, 13, 23, tzinfo=UTC))
    assert str(tabela["disponivel_em"].iloc[0]) == "2026-10-31"


def test_retrato_visto_depois_do_mes_vale_do_dia_em_que_foi_visto(banco, tmp_path):
    """Publicado (ou só baixado) em 10/11: antes disso ninguém sabia; ficar com 31/10 olharia o
    futuro. Baixar de novo o mesmo conteúdo depois não atrasa a data."""
    tabela = _montar_visto_em(
        banco,
        tmp_path,
        datetime(2026, 11, 10, 12, tzinfo=UTC),
        datetime(2026, 11, 20, 12, tzinfo=UTC),
    )
    assert str(tabela["disponivel_em"].iloc[0]) == "2026-11-10"


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


def _receita_zip(*linhas: list[str]) -> bytes:
    """Um `Empresas*.zip` ou `Simples.zip` de mentira (campos entre aspas, separados por `;`)."""
    texto = "\n".join(";".join(f'"{c}"' for c in linha) for linha in linhas) + "\n"
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as z:
        z.writestr("K3241.K03200Y0.D61010.CSV", texto.encode("latin-1"))
    return saida.getvalue()


def test_montagem_marca_o_empresario_individual_e_o_mei_como_pessoa(banco, tmp_path):
    """Linha 787: a falência do MEI e do empresário individual é dado de pessoa (ADR 0075). A linha sai
    com `trata_como_pessoa` pela natureza e pelo MEI da Receita guardada (a Porta não a serve); a raiz
    que a Receita não conhece também (na dúvida, é pessoa). Tudo fictício."""
    estabelecimentos = _zip(
        _estabelecimento("11111111", "0001", "11", "1", "FALIDO", "20210311"),
        _estabelecimento("22222222", "0001", "22", "1", "FALIDO", "20210311"),
        _estabelecimento("33333333", "0001", "33", "1", "FALIDO", "20210311"),
        _estabelecimento("44444444", "0001", "44", "1", "FALIDO", "20210311"),
        _estabelecimento("55555555", "0001", "55", "1", "FALIDO", "20210311"),
    )
    # básico; razão social; natureza; qualificação; capital; porte; ente
    empresas = _receita_zip(
        ["11111111", "EMPRESA FICTICIA LTDA", "2062", "49", "10,00", "03", ""],
        ["22222222", "", "2135", "50", "0,00", "01", ""],  # empresário individual
        ["33333333", "", "2062", "49", "0,00", "01", ""],  # MEI pelo Simples
        ["44444444", "", "4120", "50", "0,00", "01", ""],  # grupo 4: pessoa física
    )
    simples = _receita_zip(["33333333", "S", "20200101", "", "S", "20200101", ""])
    com_registro("rfb-cnpj", lambda _url: estabelecimentos)(URL)
    com_registro("rfb-cnpj", lambda _url: empresas)(
        URL.replace("Estabelecimentos0", "Empresas0")
    )
    com_registro("rfb-cnpj", lambda _url: simples)(
        URL.replace("Estabelecimentos0", "Simples")
    )
    with banco.connect() as conexao:
        rotulos.montar_situacao_especial(conexao, tmp_path / "base", AGORA)
    tabela = pd.read_parquet(
        tmp_path / "base" / "cnpj_situacao_especial" / "2026-10.parquet"
    )
    assert dict(
        zip(tabela["cnpj_basico"], tabela["trata_como_pessoa"], strict=True)
    ) == {
        "11111111": False,
        "22222222": True,
        "33333333": True,
        "44444444": True,
        "55555555": True,  # fora da Receita guardada
    }


def test_sem_a_receita_guardada_toda_linha_e_pessoa(banco, tmp_path):
    """Sem `Empresas*.zip` nem `Simples.zip` não dá para separar: na dúvida, tudo é pessoa."""
    tabela = _montar_visto_em(banco, tmp_path, datetime(2026, 10, 13, 23, tzinfo=UTC))
    assert list(tabela["trata_como_pessoa"]) == [True]
