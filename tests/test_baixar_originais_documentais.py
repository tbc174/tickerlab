"""Download dos originais documentais conferido contra o manifesto (plano de 05/11/2026, ADR 0124).

"HTTP 200 não basta": o que veio só vale com assinatura de PDF, os bytes e o SHA-256 do manifesto. Coleta
vazia nunca é sucesso, e a divergência vira pendência com as duas evidências (a esperada e a que veio).
"""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from scripts import baixar_originais_documentais as baixar

AGORA = datetime(2026, 11, 5, 23, 0, tzinfo=UTC)
PDF = b"%PDF-1.7\n1 0 obj << >> endobj\n%%EOF\n"
URL = "https://exemplo.gov.br/arquivo.pdf"


class _Cliente:
    """Dublê que grava `conteudo` no destino, ou levanta `erro`."""

    def __init__(self, conteudo: bytes = PDF, erro: Exception | None = None) -> None:
        self.conteudo, self.erro, self.pedidos = conteudo, erro, []

    def baixar(self, url: str, destino: Path) -> dict[str, str]:
        self.pedidos.append(url)
        if self.erro:
            raise self.erro
        destino.write_bytes(self.conteudo)
        return {"Content-Type": "application/pdf"}


def _original(conteudo: bytes = PDF, **outros: object) -> dict:
    return {
        "fonte": "divida-documental",
        "url": URL,
        "sha256": hashlib.sha256(conteudo).hexdigest(),
        "bytes": len(conteudo),
        **outros,
    }


def _rodar(tmp_path: Path, cliente: _Cliente, original: dict):
    pendencias = tmp_path / "pendencias.jsonl"
    conferencias = baixar.baixar(
        cliente, tmp_path / "pasta", AGORA, originais=[original], pendencias=pendencias
    )
    linhas = (
        [json.loads(x) for x in pendencias.read_text(encoding="utf-8").splitlines()]
        if pendencias.exists()
        else []
    )
    return conferencias, linhas


def test_original_conferido_fica_guardado_pelo_sha(tmp_path):
    (conferencia,), linhas = _rodar(tmp_path, _Cliente(), _original())
    assert conferencia.situacao == baixar.CONFERIDO
    guardado = tmp_path / "pasta" / "originais" / f"{_original()['sha256']}.pdf"
    assert guardado.read_bytes() == PDF
    assert conferencia.caminho == str(guardado)
    assert linhas == []


def test_recusa_sem_assinatura_bytes_e_sha(tmp_path):
    html = b"<!DOCTYPE html><html><body>Acesso negado</body></html>"
    # mesmo com o SHA e os bytes "certos" no manifesto, HTML no lugar do PDF é recusado
    (conferencia,), linhas = _rodar(tmp_path, _Cliente(html), _original(html))
    assert conferencia.situacao == baixar.RECUSADO
    assert "HTML" in conferencia.motivo
    assert not (tmp_path / "pasta" / "originais").exists()
    assert linhas[0]["situacao"] == baixar.RECUSADO

    # assinatura certa, mas o tamanho não bate com o manifesto: pendência, nunca "conferido"
    outro = _original(bytes=len(PDF) + 1)
    (conferencia,), _ = _rodar(tmp_path / "b", _Cliente(), outro)
    assert conferencia.situacao == baixar.PENDENCIA
    assert "bytes" in conferencia.motivo


def test_coleta_vazia_nao_e_sucesso(tmp_path):
    (conferencia,), linhas = _rodar(tmp_path, _Cliente(b""), _original())
    assert conferencia.situacao == baixar.VAZIO
    assert conferencia.situacao != baixar.CONFERIDO
    assert linhas[0]["situacao"] == baixar.VAZIO
    assert not (tmp_path / "pasta" / "originais").exists()


def test_divergencia_de_sha_vira_pendencia(tmp_path):
    novo = PDF.replace(b"1.7", b"1.6")  # mesmo tamanho, outro conteúdo
    esperado = _original()
    (conferencia,), linhas = _rodar(tmp_path, _Cliente(novo), esperado)
    assert conferencia.situacao == baixar.PENDENCIA
    observado = hashlib.sha256(novo).hexdigest()
    # as duas evidências: o que o manifesto esperava e o que veio, guardado à parte
    assert linhas[0]["sha256_esperado"] == esperado["sha256"]
    assert linhas[0]["sha256_observado"] == observado
    divergente = tmp_path / "pasta" / "divergentes" / f"{observado}.pdf"
    assert divergente.read_bytes() == novo
    assert linhas[0]["caminho"] == str(divergente)
    assert not (tmp_path / "pasta" / "originais").exists()


def test_falha_de_rede_vira_pendencia_sem_arquivo(tmp_path):
    cliente = _Cliente(erro=ConnectionError("caiu"))
    (conferencia,), linhas = _rodar(tmp_path, cliente, _original())
    assert conferencia.situacao == baixar.FALHOU
    assert linhas[0]["situacao"] == baixar.FALHOU
    assert "caiu" in linhas[0]["motivo"]
    assert not list((tmp_path / "pasta").rglob("*.pdf"))


def test_pendencia_registra_fonte_url_e_hora(tmp_path):
    _, linhas = _rodar(tmp_path, _Cliente(b""), _original())
    assert linhas[0]["fonte"] == "divida-documental"
    assert linhas[0]["url"] == URL
    assert linhas[0]["registrado_em"] == AGORA.isoformat()


def test_pasta_precisa_ser_nova_e_vazia(tmp_path):
    (tmp_path / "pasta").mkdir()
    (tmp_path / "pasta" / "sobra.txt").write_text("x")
    with pytest.raises(ValueError, match="vazia"):
        baixar.baixar(_Cliente(), tmp_path / "pasta", AGORA, originais=[_original()])


def test_lido_do_manifesto_conferido_por_padrao():
    originais = baixar.originais_do_manifesto()
    assert len(originais) == 10
    assert {o["fonte"] for o in originais} == {
        "divida-documental",
        "sudeco-fdco",
        "sudam-fda",
    }
    assert all(len(o["sha256"]) == 64 and o["bytes"] > 0 for o in originais)


def test_pendencias_vao_para_o_acervo_por_padrao(tmp_path, monkeypatch):
    monkeypatch.setenv("TICKERLAB_ACERVO", str(tmp_path / "acervo"))
    assert baixar.caminho_das_pendencias() == (
        tmp_path / "acervo" / "pendencias" / "fatos_documentais.jsonl"
    )
