"""Montagem da base "como era na data" (série 1 da base de ML, PR 6): junta os dados abertos de dois
anos e as versões antigas do ENET que estiverem no acervo, e grava um Parquet por ano. Sem internet."""

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from base.enet_coleta import guardar
from base.ponto_no_tempo import como_era_em, ler_parquet
from scripts import montar_base_como_era as montar
from src import acervo
from src import demonstracoes as dm
from src import versao_do_codigo as vc
from src.banco.coletas import registrar
from src.banco.conexao import criar_engine, migrar_para
from tests.test_base_enet import _dfp
from tests.test_base_enet_coleta import _pacote

PASTA = Path(__file__).parent / "arquivos" / "cvm" / "fundamentos"
COLETADO_EM = datetime(2026, 10, 12, 7, tzinfo=UTC)


VERSAO = "7ddaf09c1e6b0b5a9c1d2e3f4a5b6c7d8e9f0a1b"


@pytest.fixture
def url(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'b.sqlite').as_posix()}"
    monkeypatch.setenv("TICKERLAB_DATABASE_URL", url)
    monkeypatch.setenv(vc.VARIAVEL, VERSAO)  # a carga da base exige a versão do código
    monkeypatch.setenv(acervo.VARIAVEL_DA_PASTA, str(tmp_path / "acervo"))
    migrar_para("head", url=url)
    motor = criar_engine(url)
    with motor.begin() as c:
        for ano in (2024, 2025):
            conteudo = (PASTA / f"dfp_cia_aberta_{ano}.zip").read_bytes()
            endereco = dm.URL_DO_DFP.format(ano=ano)
            caminho = acervo.guardar_original(
                "cvm-dfp-itr", endereco, conteudo, COLETADO_EM
            )
            registrar(
                c, "cvm-dfp-itr", endereco, conteudo, "ok", caminho_do_original=caminho
            )
    motor.dispose()
    return url


@pytest.fixture
def sem_internet(monkeypatch):
    """Só existem os arquivos de teste; o resto é 404. Guarda o que a montagem pediu."""
    pedidos: list[str] = []

    def baixar_falso(endereco: str) -> bytes | None:
        pedidos.append(endereco)
        nome = endereco.rsplit("/", 1)[-1]
        return (PASTA / nome).read_bytes() if (PASTA / nome).exists() else None

    monkeypatch.setattr(montar, "baixar", baixar_falso)
    return pedidos


def test_monta_o_ano_com_os_dois_arquivos_e_grava_o_parquet(
    url, sem_internet, tmp_path
):
    saida = tmp_path / "base"
    assert montar.main(["--anos", "2024", "--pasta", str(saida)]) == 0
    assert (saida / "2024.parquet").exists()
    base = ler_parquet(saida)
    assert set(base["fim"].dt.year) == {2024}
    # os fatos de 2024 também saem no DFP de 2025, na coluna do ano anterior
    assert {"ultimo", "penultimo"} <= set(base["ordem"])
    assert set(base["referencia"].dt.year) >= {2024, 2025}
    no_acervo = {dm.URL_DO_DFP.format(ano=a) for a in (2024, 2025)}
    assert not no_acervo & set(sem_internet)  # vieram do acervo, sem baixar de novo
    foto = como_era_em(base, "2025-06-30")
    assert not foto.empty and (foto["divulgado_em"] <= pd.Timestamp("2025-06-30")).all()


def test_versao_antiga_que_esta_no_acervo_entra_e_a_que_falta_e_contada(url):
    motor = criar_engine(url)
    indice = pd.DataFrame(
        {
            "cnpj": ["00.000.208/0001-00"] * 3,
            "referencia": [pd.Timestamp("2022-12-31")] * 3,
            "versao": pd.array([1, 2, 3], dtype="Int64"),  # a 3 vem dos dados abertos
            "recebido_em": pd.to_datetime(["2023-03-10", "2023-04-20", "2023-06-01"]),
            "link": ["http://enet/1", "http://enet/2", "http://enet/3"],
        }
    )
    with motor.begin() as c:
        guardar(c, "http://enet/1", _pacote(_dfp(versao=1)), COLETADO_EM)
    with motor.connect() as c:
        documentos, faltando, origens = montar.documentos_do_enet(c, indice)
    motor.dispose()
    assert [d.versao for d in documentos] == [1]
    assert faltando == ["http://enet/2"]
    assert [o["url"] for o in origens] == ["http://enet/1"] and len(
        origens[0]["sha256"]
    ) == 64


def test_montar_de_novo_da_o_mesmo_hash_e_conferir_confirma(
    url, sem_internet, tmp_path, capsys
):
    import json

    saida = tmp_path / "base"
    assert montar.main(["--anos", "2024", "--pasta", str(saida)]) == 0
    primeiro = json.loads((saida / "2024.json").read_text(encoding="utf-8"))
    assert montar.main(["--anos", "2024", "--pasta", str(saida)]) == 0
    segundo = json.loads((saida / "2024.json").read_text(encoding="utf-8"))
    assert primeiro["sha256_da_base"] == segundo["sha256_da_base"]
    urls = {o["url"] for o in primeiro["origens"]}
    assert {dm.URL_DO_DFP.format(ano=2024), dm.URL_DO_DFP.format(ano=2025)} <= urls
    assert montar.main(["--conferir", "--pasta", str(saida)]) == 0
    assert "2024: ok" in capsys.readouterr().out


def test_sem_a_versao_do_codigo_a_base_nao_e_gravada(
    url, sem_internet, tmp_path, monkeypatch
):
    """Exigência 13 da ADR 0055: número sem a versão do código que o fez não entra na base."""
    monkeypatch.delenv(vc.VARIAVEL)
    monkeypatch.setattr(vc, "_perguntar_ao_git", lambda: None)
    with pytest.raises(vc.VersaoDesconhecidaError, match=vc.VARIAVEL):  # desconhecida
        montar.main(["--anos", "2024", "--pasta", str(tmp_path / "base")])
    assert not (tmp_path / "base").exists()


def test_manifesto_leva_a_versao_do_codigo(url, sem_internet, tmp_path):
    import json

    saida = tmp_path / "base"
    assert montar.main(["--anos", "2024", "--pasta", str(saida)]) == 0
    manifesto = json.loads((saida / "2024.json").read_text(encoding="utf-8"))
    assert manifesto["versao_do_codigo"] == VERSAO
