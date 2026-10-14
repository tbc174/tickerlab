"""Arquivista (base/arquivo): guarda o retrato de cada fonte como veio, com registro e manifesto."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from base.arquivo import coleta
from base.arquivo.coleta import Alvo, Fonte, Resposta
from src import acervo
from src.banco import coletas

AGORA = datetime(2026, 10, 14, 5, tzinfo=UTC)  # 2h em Brasília
ZIP = b"PK\x03\x04" + b"dados" * 100
URL = "https://exemplo.gov.br/arquivo.zip"


class ClienteFalso:
    """Um "servidor" em memória: url -> (conteúdo, cabeçalhos). Conta os downloads."""

    def __init__(self, arquivos: dict[str, tuple[bytes, dict[str, str]]]):
        self.arquivos = arquivos
        self.baixados: list[str] = []

    def ler(self, url, *, metodo="GET", cabecalhos=None):
        conteudo, cab = self.arquivos[url]
        return Resposta(url, conteudo, cab)

    def cabecalhos(self, url):
        return self.arquivos[url][1]

    def baixar(self, url, destino: Path):
        self.baixados.append(url)
        conteudo, cab = self.arquivos[url]
        destino.write_bytes(conteudo)
        return cab


def _fonte(
    urls=(URL,), *, tipo="arquivo", pesada=False, vigia=False, ident="teste-fonte"
):
    return Fonte(
        ident,
        "diaria",
        lambda cliente, agora: [Alvo(u) for u in urls],
        tipo,
        pesada,
        vigia,
    )


def _rodar(fonte, cliente, banco, tmp_path, **extra):
    return coleta.arquivar(
        fonte, cliente, AGORA, tmp_path / "temporario", pausa=0, **extra
    )


def _linhas(banco):
    with banco.connect() as conexao:
        return coletas.ultimas(conexao)


def test_baixa_guarda_no_acervo_e_registra(banco, tmp_path):
    cliente = ClienteFalso(
        {URL: (ZIP, {"Last-Modified": "Mon, 13 Oct 2026 21:15:06 GMT"})}
    )
    resultado = _rodar(_fonte(), cliente, banco, tmp_path)
    assert (resultado.novos, resultado.iguais, resultado.falhas) == (1, 0, [])
    [linha] = _linhas(banco)
    assert linha.situacao == "ok"
    assert linha.sha256 == hashlib.sha256(ZIP).hexdigest()
    assert acervo.ler_original(linha.caminho_do_original) == ZIP


def test_registro_guarda_a_data_que_a_fonte_declara(banco, tmp_path):
    cliente = ClienteFalso(
        {
            URL: (
                ZIP,
                {"Last-Modified": "Mon, 13 Oct 2026 21:15:06 GMT", "ETag": '"abc"'},
            )
        }
    )
    _rodar(_fonte(), cliente, banco, tmp_path)
    [linha] = _linhas(banco)
    assert "Mon, 13 Oct 2026 21:15:06 GMT" in linha.detalhe
    assert '"abc"' in linha.detalhe


def test_segunda_rodada_com_o_mesmo_arquivo_nao_duplica_no_acervo(banco, tmp_path):
    cliente = ClienteFalso({URL: (ZIP, {})})
    _rodar(_fonte(), cliente, banco, tmp_path)
    resultado = _rodar(_fonte(), cliente, banco, tmp_path)
    assert (resultado.novos, resultado.iguais) == (0, 1)
    linhas = _linhas(banco)
    assert len(linhas) == 2
    assert sum("igual à coleta anterior" in linha.detalhe for linha in linhas) == 1
    assert len(list((tmp_path / "acervo").rglob("*.zip"))) == 1


def test_fonte_leve_baixa_de_novo_mesmo_com_os_mesmos_cabecalhos(banco, tmp_path):
    # a CVM sobrescreve arquivos sem mudar sempre os cabeçalhos: nas leves, vale o SHA-256
    cab = {"Last-Modified": "x", "Content-Length": "10"}
    cliente = ClienteFalso({URL: (ZIP, cab)})
    _rodar(_fonte(), cliente, banco, tmp_path)
    cliente.arquivos[URL] = (ZIP + b"novo", cab)
    resultado = _rodar(_fonte(), cliente, banco, tmp_path)
    assert resultado.novos == 1
    assert len(cliente.baixados) == 2


def test_pesada_com_os_mesmos_cabecalhos_nao_baixa_de_novo(banco, tmp_path):
    cab = {
        "Last-Modified": "Mon, 06 Oct 2026 10:00:00 GMT",
        "ETag": '"e1"',
        "Content-Length": "500",
    }
    cliente = ClienteFalso({URL: (ZIP, cab)})
    _rodar(
        _fonte(pesada=True),
        cliente,
        banco,
        tmp_path,
        espaco=lambda pasta: (900 * 1024**3, 800 * 1024**3),
    )
    resultado = _rodar(
        _fonte(pesada=True),
        cliente,
        banco,
        tmp_path,
        espaco=lambda pasta: (900 * 1024**3, 800 * 1024**3),
    )
    assert resultado.pulados == 1
    assert cliente.baixados == [URL]


def test_freio_de_disco_para_as_pesadas(banco, tmp_path):
    cliente = ClienteFalso({URL: (ZIP, {})})
    gb = 1024**3
    with pytest.raises(coleta.FreioDeDisco):
        _rodar(
            _fonte(pesada=True),
            cliente,
            banco,
            tmp_path,
            espaco=lambda pasta: (900 * gb, 40 * gb),
        )
    with pytest.raises(coleta.FreioDeDisco):  # mais de 70% do disco usado
        _rodar(
            _fonte(pesada=True),
            cliente,
            banco,
            tmp_path,
            espaco=lambda pasta: (1000 * gb, 200 * gb),
        )
    assert cliente.baixados == []
    # as leves não têm freio (são pequenas)
    assert (
        _rodar(
            _fonte(), cliente, banco, tmp_path, espaco=lambda pasta: (100 * gb, 1)
        ).novos
        == 1
    )


def test_descoberta_vazia_e_falha(banco, tmp_path):
    with pytest.raises(coleta.ErroDeDescoberta):
        _rodar(_fonte(urls=()), ClienteFalso({}), banco, tmp_path)


def test_html_no_lugar_do_zip_e_falha_e_nao_vai_para_o_acervo(banco, tmp_path):
    cliente = ClienteFalso({URL: (b"<!DOCTYPE html><html>erro</html>", {})})
    resultado = _rodar(_fonte(), cliente, banco, tmp_path)
    assert resultado.novos == 0
    assert len(resultado.falhas) == 1
    [linha] = _linhas(banco)
    assert (linha.situacao, linha.caminho_do_original) == ("falhou", None)
    assert "HTML" in linha.detalhe


def test_pdf_esperado_confere_a_assinatura(banco, tmp_path):
    cliente = ClienteFalso({URL: (b"PK\x03\x04", {})})
    resultado = _rodar(_fonte(tipo="pdf"), cliente, banco, tmp_path)
    assert len(resultado.falhas) == 1


def test_termo_mudou_avisa_mas_mudanca_so_de_script_nao(banco, tmp_path):
    url = "https://exemplo.org/termos"
    pagina = b"<html><script>var t=1;</script><p>Uso pessoal apenas.</p></html>"
    cliente = ClienteFalso({url: (pagina, {})})
    fonte = _fonte(urls=(url,), tipo="html", vigia=True, ident="termos-teste")
    assert (
        _rodar(fonte, cliente, banco, tmp_path).mudaram == []
    )  # primeira vez: nada a comparar
    cliente.arquivos[url] = (pagina.replace(b"t=1", b"t=2"), {})
    assert _rodar(fonte, cliente, banco, tmp_path).mudaram == []  # só o script mudou
    cliente.arquivos[url] = (pagina.replace(b"pessoal", b"comercial"), {})
    assert _rodar(fonte, cliente, banco, tmp_path).mudaram == [url]


def test_manifesto_do_dia_tem_uma_linha_por_arquivo(banco, tmp_path):
    cliente = ClienteFalso({URL: (ZIP, {"ETag": '"e"'})})
    _rodar(_fonte(), cliente, banco, tmp_path)
    manifesto = tmp_path / "acervo" / "manifesto" / "2026-10-14.jsonl"
    [linha] = [
        json.loads(x) for x in manifesto.read_text(encoding="utf-8").splitlines()
    ]
    assert linha["sha256"] == hashlib.sha256(ZIP).hexdigest()
    assert linha["url"] == URL
    assert linha["cabecalhos"]["ETag"] == '"e"'
    assert linha["fonte"] == "teste-fonte"


def test_falha_num_arquivo_nao_impede_os_outros(banco, tmp_path):
    outro = "https://exemplo.gov.br/outro.zip"

    class Quebra(ClienteFalso):
        def baixar(self, url, destino):
            if url == URL:
                raise TimeoutError("lento")
            return super().baixar(url, destino)

    resultado = _rodar(
        _fonte(urls=(URL, outro)), Quebra({outro: (ZIP, {})}), banco, tmp_path
    )
    assert resultado.novos == 1
    assert resultado.falhas == [URL]
