"""Porta de entrada da coleta de cripto (`scripts/coletar_cripto.py`), sem rede."""

import pytest
import requests

from base.cripto.arquivos import ler_tabela
from scripts import coletar_cripto
from tests.test_base_cripto_precos import KRAKEN_REST


@pytest.fixture
def acervo(tmp_path, monkeypatch):
    monkeypatch.setenv("TICKERLAB_ACERVO", str(tmp_path))
    # o registro de coletas é testado em test_coletas.py; aqui só a coleta
    monkeypatch.setattr(coletar_cripto, "com_registro", lambda _nome, baixar: baixar)
    return tmp_path


def test_base_fica_dentro_do_acervo(acervo):
    assert coletar_cripto.pasta_da_base() == acervo / "base" / "cripto"


def test_coleta_da_kraken_grava_e_devolve_zero(acervo, monkeypatch):
    monkeypatch.setattr(coletar_cripto, "_baixar_da_fonte", lambda _url: KRAKEN_REST)

    assert coletar_cripto.main(["kraken"]) == 0
    assert not ler_tabela(acervo / "base" / "cripto" / "precos" / "kraken", "dia").empty


def test_falha_da_fonte_devolve_um_e_nao_grava(acervo, monkeypatch):
    def cai(_url):
        raise requests.ConnectionError("sem rede")

    monkeypatch.setattr(coletar_cripto, "_baixar_da_fonte", cai)

    assert coletar_cripto.main(["kraken"]) == 1
    assert not (acervo / "base" / "cripto" / "precos").exists()


def test_resposta_que_nao_e_json_conta_como_falha(acervo, monkeypatch):
    # o GDELT responde texto quando passamos do limite: falha, nunca "dia sem notícia"
    monkeypatch.setattr(
        coletar_cripto, "_baixar_da_fonte", lambda _url: b"Please limit requests"
    )

    assert coletar_cripto.main(["kraken"]) == 1


def test_cada_fonte_registra_numa_familia_com_licenca():
    from src.banco.coletas import SEM_LICENCA_CONHECIDA, licenca_da_fonte

    for nome_no_registro, _ in coletar_cripto.COLETAS.values():
        assert licenca_da_fonte(nome_no_registro) != SEM_LICENCA_CONHECIDA


def test_fonte_desconhecida_e_recusada():
    with pytest.raises(SystemExit):
        coletar_cripto.main(["binance"])


def test_carga_do_arquivo_historico_da_kraken(acervo, tmp_path):
    csv = tmp_path / "XBTUSD_1440.csv"
    linhas = [
        b"1381017600,122.0,122.0,122.0,122.0,0.1,1",
        b"1381104000,123.6,123.6,122.0,123.0,2.5,7",
    ]
    csv.write_bytes(b"\n".join(linhas) + b"\n")

    assert coletar_cripto.main(["kraken-arquivo", str(csv)]) == 0
    precos = ler_tabela(acervo / "base" / "cripto" / "precos" / "kraken", "dia")
    assert len(precos) == 2


def test_carga_do_arquivo_sem_caminho_e_recusada(acervo):
    assert coletar_cripto.main(["kraken-arquivo"]) == 1


def test_rodada_de_qualidade_grava_os_achados(acervo, monkeypatch):
    from datetime import date

    import pandas as pd

    from base.cripto import arquivos

    base = acervo / "base" / "cripto"
    precos = pd.DataFrame(
        {
            "dia": [date(2024, 1, 1), date(2024, 1, 3)],  # falta o dia 2: achado C1
            "abertura": [1.0, 1.0],
            "maxima": [1.0, 1.0],
            "minima": [1.0, 1.0],
            "fechamento": [1.0, 1.0],
            "volume": [1.0, 1.0],
        }
    )
    arquivos.gravar_parquet(base / "precos" / "kraken" / "2024.parquet", precos)
    monkeypatch.setattr(coletar_cripto, "_ptax", lambda: None)

    assert coletar_cripto.main(["qualidade"]) == 0
    achados = ler_tabela(base / "qualidade", "regra")
    assert achados["regra"].tolist() == ["C1"]
    assert achados["chave"].tolist() == ["2024-01-02"]
