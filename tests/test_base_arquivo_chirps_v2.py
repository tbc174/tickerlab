"""CHIRPS v2 mensal: o servidor trocou `products/CHIRPS-2.0/` por `products/CHIRPS/v2.0/` (o caminho
antigo dá 404). Como 404 é "mês ainda não publicado", o erro ficava silencioso: a coleta precisa
avisar quando TODOS os meses pedidos derem 404."""

import dataclasses
import logging
from datetime import UTC, datetime
from pathlib import Path

import requests

from base.arquivo import coleta, fontes

AGORA = datetime(2026, 10, 18, 12, tzinfo=UTC)
PREFIXO_NOVO = "https://data.chc.ucsb.edu/products/CHIRPS/v2.0/global_monthly/tifs/"


class ServidorSoComOCaminhoNovo:
    """Responde 404 para tudo que não está no caminho novo, como o servidor do CHC."""

    def baixar(self, url: str, destino: Path):
        if not url.startswith(PREFIXO_NOVO):
            resposta = requests.Response()
            resposta.status_code = 404
            raise requests.HTTPError("404 Client Error", response=resposta)
        destino.write_bytes(b"tif")
        return {"Content-Type": "application/gzip"}


def test_os_enderecos_do_chirps_usam_o_caminho_novo_do_servidor():
    recentes = fontes.POR_ID["chirps-mensal"].descobrir(None, AGORA)  # type: ignore[arg-type]
    historico = fontes.POR_ID["chirps-historico"].descobrir(None, AGORA)  # type: ignore[arg-type]
    assert recentes and historico
    assert all(a.url.startswith(PREFIXO_NOVO) for a in recentes + historico)
    assert recentes[0].url.endswith("chirps-v2.0.2026.07.tif.gz")


def test_todos_os_meses_em_404_deixam_um_aviso_claro(banco, tmp_path, caplog):
    fonte = fontes.POR_ID["chirps-mensal"]
    antigos = [
        coleta.Alvo(url, ".tif.gz", fontes.arquivo_que_pode_faltar(url))
        for url in (
            a.url.replace("CHIRPS/v2.0", "CHIRPS-2.0")
            for a in fonte.descobrir(None, AGORA)  # type: ignore[arg-type]
        )
    ]
    fonte_antiga = dataclasses.replace(fonte, descobrir=lambda c, ag: antigos)
    with caplog.at_level(logging.WARNING):
        resultado = coleta.arquivar(
            fonte_antiga,
            ServidorSoComOCaminhoNovo(),  # type: ignore[arg-type]
            AGORA,
            tmp_path / "temporario",
            pausa=0,
            espaco=lambda pasta: (900 * 1024**3, 800 * 1024**3),
        )
    assert resultado.sem_arquivo == len(antigos) and not resultado.falhas
    avisos = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("todos os arquivos deram 404" in aviso for aviso in avisos)
