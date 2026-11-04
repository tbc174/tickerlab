"""Congelamento dos arquivos de entrada (`dados_congelados`) numa árvore temporária.

Confere o que entra no manifesto (só o desenvolvimento: nada de 2024 em diante nem do papel), que a
cópia é idempotente e não se sobrescreve, que uma mudança no meio da rodada é pega e que a marca
entra na especificação da C-1 só quando é dada.
"""

from datetime import date
from pathlib import Path

import pytest

from trader.estrategias import dados_congelados as dc
from trader.estrategias import rodar_c1


def _escrever(caminho: Path, conteudo: bytes = b"x") -> Path:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_bytes(conteudo)
    return caminho


@pytest.fixture
def arvore(tmp_path: Path) -> dict[str, Path]:
    pesquisa, mt5, acervo = tmp_path / "pq", tmp_path / "mt5", tmp_path / "base"
    _escrever(pesquisa / "f_b3" / "COTAHIST_A2015.ZIP")
    _escrever(pesquisa / "f_b3" / "cvm" / "dfp_cia_aberta_2015.zip")
    _escrever(pesquisa / "binance_brl" / "BTCBRL.parquet")
    _escrever(pesquisa / "cdi_20090102_20230908.parquet")
    _escrever(pesquisa / "cdi_20261010_20261103.parquet")  # do papel: fora
    _escrever(pesquisa / "registro.db")  # fora
    _escrever(mt5 / "BOVA11.SA_D1.parquet")
    _escrever(acervo / "curva_juros" / "2026.parquet")  # a curva é lida inteira
    _escrever(acervo / "demonstracoes" / "2023.parquet")
    _escrever(acervo / "demonstracoes" / "2024.parquet")  # fora
    _escrever(acervo / "insolvencia" / "2015.v1.parquet")  # versão anterior: fora
    _escrever(acervo / "eventos" / "2015.json")  # fora
    _escrever(acervo / "fca" / "emissores.parquet")
    _escrever(acervo / "fca" / "tickers.parquet")
    return {"pesquisa": pesquisa, "mt5": mt5, "acervo": acervo}


def test_o_manifesto_so_tem_o_desenvolvimento(arvore):
    nomes = set(dc.arquivos_lidos(**arvore))
    assert nomes == {
        "pesquisa/f_b3/COTAHIST_A2015.ZIP",
        "pesquisa/f_b3/cvm/dfp_cia_aberta_2015.zip",
        "pesquisa/binance_brl/BTCBRL.parquet",
        "pesquisa/cdi_20090102_20230908.parquet",
        "mt5/BOVA11.SA_D1.parquet",
        "acervo/curva_juros/2026.parquet",
        "acervo/demonstracoes/2023.parquet",
        "acervo/fca/emissores.parquet",
        "acervo/fca/tickers.parquet",
    }


def test_congelar_copia_e_e_idempotente(arvore, tmp_path):
    arquivos = dc.arquivos_lidos(**arvore)
    destino = tmp_path / "congelados" / "2026-11-04"
    marca = dc.congelar(destino, arquivos)
    assert (destino / "mt5" / "BOVA11.SA_D1.parquet").read_bytes() == b"x"
    assert (destino / dc.NOME_DO_MANIFESTO).exists()
    assert dc.congelar(destino, arquivos) == marca
    assert marca == dc.marca(dc.manifesto(arquivos))


def test_congelamento_nao_se_sobrescreve(arvore, tmp_path):
    destino = tmp_path / "congelados" / "2026-11-04"
    dc.congelar(destino, dc.arquivos_lidos(**arvore))
    _escrever(arvore["mt5"] / "BOVA11.SA_D1.parquet", b"regravado")
    with pytest.raises(RuntimeError, match="outros arquivos"):
        dc.congelar(destino, dc.arquivos_lidos(**arvore))


def test_mudanca_durante_a_rodada_e_pega(arvore):
    marca = dc.marca(dc.manifesto(dc.arquivos_lidos(**arvore)))
    dc.exigir_a_mesma_marca(marca, dc.arquivos_lidos(**arvore))
    _escrever(arvore["acervo"] / "demonstracoes" / "2023.parquet", b"novo")
    with pytest.raises(RuntimeError, match="mudaram durante a rodada"):
        dc.exigir_a_mesma_marca(marca, dc.arquivos_lidos(**arvore))


def test_arquivo_novo_de_2024_nao_muda_a_marca(arvore):
    marca = dc.marca(dc.manifesto(dc.arquivos_lidos(**arvore)))
    _escrever(arvore["acervo"] / "eventos" / "2024.parquet")
    dc.exigir_a_mesma_marca(marca, dc.arquivos_lidos(**arvore))


def test_a_marca_entra_na_especificacao_da_c1_so_quando_dada():
    fim = date(2023, 9, 8)
    sem = rodar_c1.especificacao(rodar_c1.CANDIDATA, fim)
    com = rodar_c1.especificacao(rodar_c1.CANDIDATA, fim, "abc")
    assert "dados" not in sem
    assert com == {**sem, "dados": "abc"}
