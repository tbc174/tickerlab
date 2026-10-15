"""Versões antigas do FCA no sistema de documentos da CVM (achado da série 4 da base de ML): a coleta
em gotas, que para no limite da CVM, e a carga do FCA que passa a usar as versões guardadas. Sem
internet: o FCA vem das amostras e os documentos das versões, de `tests/arquivos/cvm/fca/versoes/`."""

from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pytest
import sqlalchemy as sa

from base import fca
from scripts import carga_fca, coletar_fca_versoes
from src import acervo
from src import versao_do_codigo as vc
from src.banco.coletas import com_registro, registrar
from src.banco.conexao import criar_engine, migrar_para
from src.banco.modelo import coletas

PASTA = Path(__file__).parent / "arquivos" / "cvm" / "fca"
VERSAO = "9b1e0c4d2e1f0a9b8c7d6e5f4a3b2c1d0e9f8a7c"
VIA, ITAU = "33.041.260/0652-90", "60.872.504/0001-23"
PAGINA_DE_LIMITE = b"<html><body>Limite de acessos</body></html>"


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    """Banco, acervo e versão do código de mentira, com o FCA das amostras já carregado uma vez."""
    url = f"sqlite:///{(tmp_path / 'b.sqlite').as_posix()}"
    monkeypatch.setenv("TICKERLAB_DATABASE_URL", url)
    monkeypatch.setenv(acervo.VARIAVEL_DA_PASTA, str(tmp_path / "acervo"))
    monkeypatch.setenv(vc.VARIAVEL, VERSAO)
    monkeypatch.setattr(coletar_fca_versoes, "PAUSA_ENTRE_DOWNLOADS", 0)
    migrar_para("head", url=url)

    def fca_falso(endereco: str) -> bytes | None:
        arquivo = PASTA / endereco.rsplit("/", 1)[-1]
        return arquivo.read_bytes() if arquivo.exists() else None

    monkeypatch.setattr(carga_fca, "baixar", com_registro(carga_fca.FONTE, fca_falso))
    pasta = tmp_path / "base" / "fca"
    assert (
        carga_fca.main(["--pasta", str(pasta), "--desde", "2018", "--ate", "2026"]) == 0
    )
    return pasta


def _rad_falso(monkeypatch, respostas: dict[str, bytes | None]) -> list[str]:
    """O RAD de mentira: a resposta de cada documento pelo número; quem não está, página de limite."""
    pedidos: list[str] = []

    def baixar(endereco: str) -> bytes | None:
        pedidos.append(endereco)
        numero = endereco.split("numSequencia=")[1].split("&")[0]
        conteudo = respostas.get(numero, PAGINA_DE_LIMITE)
        return coletar_fca_versoes.conferir_documento(conteudo)

    monkeypatch.setattr(
        coletar_fca_versoes, "baixar", com_registro(fca.FONTE_DAS_VERSOES, baixar)
    )
    return pedidos


def _versao(id_documento: str) -> bytes:
    return (PASTA / "versoes" / f"fca_versao_{id_documento}.zip").read_bytes()


def test_coleta_em_ordem_e_para_no_limite_da_cvm(ambiente, monkeypatch):
    pedidos = _rad_falso(monkeypatch, {"104636": _versao("104636")})
    assert (
        coletar_fca_versoes.main(["--desde", "2021", "--ate", "2021", "--maximo", "10"])
        == 0
    )  # o limite não é erro
    assert [p.split("numSequencia=")[1].split("&")[0] for p in pedidos] == [
        "104636",
        "108298",
    ]
    with criar_engine().connect() as c:
        situacoes = dict(
            c.execute(
                sa.select(coletas.c.url, coletas.c.situacao).where(
                    coletas.c.fonte == fca.FONTE_DAS_VERSOES
                )
            ).all()
        )
    assert sorted(situacoes.values()) == ["falhou", "ok"]


def test_nao_baixa_de_novo_o_que_ja_tem_e_respeita_o_maximo(ambiente, monkeypatch):
    respostas = {
        "104636": _versao("104636"),
        "108298": None,
        "108846": _versao("108846"),
    }
    pedidos = _rad_falso(monkeypatch, respostas)
    coletar_fca_versoes.main(["--desde", "2021", "--ate", "2021", "--maximo", "2"])
    assert len(pedidos) == 2
    coletar_fca_versoes.main(["--desde", "2021", "--ate", "2021", "--maximo", "10"])
    # na 2ª rodada, só o que faltava: o que veio (ou que não existe na CVM) não é pedido de novo
    numeros = [p.split("numSequencia=")[1].split("&")[0] for p in pedidos]
    assert numeros.count("104636") == 1 and numeros.count("108298") == 1
    assert "108846" in numeros


def test_carga_usa_as_versoes_antigas_guardadas(ambiente, monkeypatch):
    """Com a versão 3 do FCA 2021 da Via guardada, o VIIA3 vale de 01/10/2021, não de 30/12/2021."""
    _rad_falso(
        monkeypatch,
        {"104636": _versao("104636"), "108298": None, "108846": _versao("108846")},
    )
    coletar_fca_versoes.main(["--desde", "2021", "--ate", "2021", "--maximo", "3"])
    assert (
        carga_fca.main(["--pasta", str(ambiente), "--desde", "2018", "--ate", "2026"])
        == 0
    )
    tickers = pd.read_parquet(ambiente / "tickers.parquet")
    assert fca.resolver_ticker(tickers, "VIIA3", date(2021, 10, 1)) == VIA
    assert fca.resolver_ticker(tickers, "VVAR3", date(2021, 10, 1)) is None
    valores = pd.read_parquet(ambiente / "valores_mobiliarios.parquet")
    do_rad = valores[valores["origem"] == fca.PELO_DOCUMENTO_DA_VERSAO]
    assert set(do_rad["id_documento"]) == {"104636", "108846"}


def test_carga_le_todas_as_baixadas_guardadas_do_ano(ambiente):
    """Uma baixada antiga do FCA de 2026 (com a versão 1 do Itaú, que a CVM depois trocou pela 2)
    continua valendo: a versão 1 entra na tabela com a data de entrega dela."""
    import io
    import zipfile

    url = carga_fca.URL_DO_FCA.format(ano=2026)
    atual = (PASTA / "fca_cia_aberta_2026.zip").read_bytes()
    with zipfile.ZipFile(io.BytesIO(atual)) as z:
        valores = z.read("fca_cia_aberta_valor_mobiliario_2026.csv").decode("latin-1")
        principal = z.read("fca_cia_aberta_2026.csv")
    antiga = valores.replace(
        f"{ITAU};2026-01-01;2;156921;", f"{ITAU};2026-01-01;1;156106;"
    )
    assert antiga != valores
    conteudo = io.BytesIO()
    with zipfile.ZipFile(conteudo, "w") as z:
        z.writestr("fca_cia_aberta_valor_mobiliario_2026.csv", antiga.encode("latin-1"))
        z.writestr("fca_cia_aberta_2026.csv", principal)
    quando = datetime(2026, 4, 20, tzinfo=UTC)
    caminho = acervo.guardar_original(carga_fca.FONTE, url, conteudo.getvalue(), quando)
    with criar_engine().begin() as c:
        registrar(c, carga_fca.FONTE, url, conteudo.getvalue(), "ok", agora=quando,
                  caminho_do_original=caminho)  # fmt: skip
    assert (
        carga_fca.main(["--pasta", str(ambiente), "--desde", "2026", "--ate", "2026"])
        == 0
    )
    tabela = pd.read_parquet(ambiente / "valores_mobiliarios.parquet")
    itau = tabela[tabela["cnpj"] == ITAU]
    assert set(itau["versao"]) == {1, 2}
    assert set(itau.loc[itau["versao"] == 1, "recebido_em"]) == {
        pd.Timestamp("2026-04-09")
    }


def test_conferir_documento_recusa_a_pagina_de_limite():
    with pytest.raises(coletar_fca_versoes.LimiteDaCVM):
        coletar_fca_versoes.conferir_documento(PAGINA_DE_LIMITE)
    assert coletar_fca_versoes.conferir_documento(None) is None
    assert coletar_fca_versoes.conferir_documento(_versao("104636")) == _versao(
        "104636"
    )
