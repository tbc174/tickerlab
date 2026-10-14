"""Registro de coletas (Radar, PR 1): cada arquivo baixado deixa uma linha, e o registro nunca
derruba a coleta."""

import hashlib
import logging
from datetime import UTC, datetime, timedelta

import pytest

from src.banco import coletas
from src.banco.coletas import com_registro, licenca_da_fonte, registrar, ultimas

URL = "https://dados.cvm.gov.br/arquivo.zip"


def _todas(banco):
    with banco.connect() as conexao:
        return ultimas(conexao)


def test_arquivo_baixado_fica_registrado_com_tamanho_e_sha256(banco):
    baixar = com_registro("cvm-eventos", lambda url: b"conteudo")
    assert baixar(URL) == b"conteudo"
    [linha] = _todas(banco)
    assert linha.fonte == "cvm-eventos"
    assert linha.url == URL
    assert linha.situacao == "ok"
    assert linha.bytes == len(b"conteudo")
    assert linha.sha256 == hashlib.sha256(b"conteudo").hexdigest()
    assert linha.licenca.startswith("ODbL")


def test_404_fica_registrado_como_nao_encontrado(banco):
    assert com_registro("sec-13f", lambda url: None)(URL) is None
    [linha] = _todas(banco)
    assert (linha.situacao, linha.bytes, linha.sha256) == ("nao_encontrado", None, None)


def test_erro_fica_registrado_e_segue_para_a_coleta(banco):
    def baixar(url):
        raise TimeoutError("demorou")

    with pytest.raises(TimeoutError):
        com_registro("cvm-cda", baixar)(URL)
    [linha] = _todas(banco)
    assert (linha.situacao, linha.detalhe) == ("falhou", "TimeoutError")


def test_os_outros_argumentos_chegam_a_funcao_de_baixar(banco):
    recebidos = []

    def baixar(url, cabecalhos=None):
        recebidos.append((url, cabecalhos))
        return b"x"

    com_registro("sec-eventos", baixar)(URL, cabecalhos={"User-Agent": "teste"})
    assert recebidos == [(URL, {"User-Agent": "teste"})]


def test_banco_fora_do_ar_nao_derruba_a_coleta(monkeypatch, caplog):
    monkeypatch.setattr(
        coletas, "obter_engine", lambda: (_ for _ in ()).throw(OSError("sem banco"))
    )
    with caplog.at_level(logging.ERROR, logger=coletas.__name__):
        assert com_registro("cvm-vlmo", lambda url: b"x")(URL) == b"x"
    assert "Falha ao registrar a coleta de cvm-vlmo" in caplog.text


@pytest.mark.parametrize(
    ("fonte", "comeco"),
    [
        ("cvm-documentos", "ODbL"),
        ("bcb-sgs", "ODbL"),
        ("yahoo-precos", "Uso pessoal: só interno"),
        ("iex", "Termos do IEX"),
        ("cftc-tff", "Obra do governo dos EUA"),
        ("rfb-cripto", "Dados abertos da Receita"),
        ("wiki-acessos", "CC0"),
        ("gdelt-cripto", "GDELT"),
        ("btc-no", "Blockchain pública"),
        ("kraken-ohlc", "Sem termo de dados de mercado"),
        ("mb-candles", "Sem termo de dados de mercado"),
        ("desconhecida", "Desconhecida"),
    ],
)
def test_licenca_vem_da_familia_da_fonte(fonte, comeco):
    assert licenca_da_fonte(fonte).startswith(comeco)


def test_ultimas_vem_da_mais_nova_e_filtram_pela_fonte(banco):
    agora = datetime(2026, 10, 12, 3, tzinfo=UTC)
    with banco.begin() as conexao:
        for horas, fonte in [(2, "cvm-eventos"), (0, "cvm-eventos"), (1, "sec-13f")]:
            registrar(
                conexao, fonte, URL, b"x", "ok", agora=agora - timedelta(hours=horas)
            )
    with banco.connect() as conexao:
        assert [r.fonte for r in ultimas(conexao)] == [
            "cvm-eventos",
            "sec-13f",
            "cvm-eventos",
        ]
        so_cvm = ultimas(conexao, fonte="cvm-eventos", quantas=1)
    assert [r.baixado_em.replace(tzinfo=UTC) for r in so_cvm] == [agora]


def test_url_e_detalhe_longos_sao_cortados(banco):
    with banco.begin() as conexao:
        registrar(conexao, "cvm-eventos", "h" * 2000, None, "falhou", "d" * 500)
    [linha] = _todas(banco)
    assert len(linha.url) == coletas.LIMITE_DA_URL
    assert len(linha.detalhe) == coletas.LIMITE_DO_DETALHE


def test_familias_do_arquivo_tem_licenca_e_as_com_dado_pessoal_sao_so_internas():
    assert "CGU" in licenca_da_fonte("cgu-ceis")
    assert "CNPJ" in licenca_da_fonte("rfb-cnpj")
    assert (
        licenca_da_fonte("rfb-cripto") == coletas.LICENCAS["rfb"]
    )  # a planilha de cripto não muda
    assert licenca_da_fonte("gleif-br").startswith("CC0")
    for fonte in (
        "cgu-ceis",
        "pgfn-divida",
        "ibama-autos",
        "mte-lista-suja",
        "rfb-cnpj",
    ):
        assert coletas.revenda_da_fonte(fonte) == coletas.SO_USO_INTERNO, fonte
    assert coletas.revenda_da_fonte("gleif-br") == coletas.VENDAVEL_COM_ATRIBUICAO
    assert coletas.revenda_da_fonte("termos-b3") == coletas.SO_USO_INTERNO


def test_registrar_arquivo_grande_usa_o_sha256_e_o_tamanho_ja_calculados(banco):
    agora = datetime(2026, 10, 14, 2, tzinfo=UTC)
    with banco.begin() as conexao:
        coletas.registrar_arquivo(
            conexao,
            "rfb-cnpj",
            URL,
            "a" * 64,
            6_000_000_000,
            "ok",
            "lm=x",
            agora,
            "bruto/x.zip",
        )
        coletas.registrar_arquivo(
            conexao, "rfb-cnpj", URL, None, None, "falhou", "Timeout", agora
        )
    with banco.connect() as conexao:
        ultima = coletas.ultima_coleta_ok(conexao, URL)
        assert coletas.ultima_coleta_ok(conexao, "https://outra") is None
    assert ultima is not None
    assert (ultima.sha256, ultima.bytes, ultima.detalhe) == (
        "a" * 64,
        6_000_000_000,
        "lm=x",
    )
