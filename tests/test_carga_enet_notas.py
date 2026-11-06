"""Carga do texto das notas da DFP (linha 135): todas as versões da DFP, uma por vez, só até o fim da
janela, e a montagem de `notas_dfp` a partir do acervo. Sem internet."""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from base import enet_notas
from scripts import carga_enet, carga_enet_notas
from src import acervo
from src.banco.coletas import registrar
from src.banco.conexao import criar_engine, migrar_para
from tests.ajudantes_da_sala import pdf
from tests.test_carga_enet import _zip_do_ano

FUSO = ZoneInfo("America/Sao_Paulo")


@pytest.fixture
def url(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'c.sqlite').as_posix()}"
    monkeypatch.setenv("TICKERLAB_DATABASE_URL", url)
    monkeypatch.setenv(acervo.VARIAVEL_DA_PASTA, str(tmp_path / "acervo"))
    migrar_para("head", url=url)
    return url


class _Mundo:
    def __init__(self, monkeypatch, comeco: datetime):
        self.agora, self.pacotes = comeco, []
        monkeypatch.setattr(
            carga_enet,
            "baixar",
            lambda endereco: _zip_do_ano("DFP", 2024) if "2024" in endereco else None,
        )
        monkeypatch.setattr(carga_enet_notas, "Baixador", lambda: self)
        monkeypatch.setattr(carga_enet_notas, "agora", lambda: self.agora)

    def baixar(self, link: str) -> bytes:
        self.pacotes.append(link)
        self.agora += timedelta(minutes=10)
        return _pacote_com_pdf(pdf(f"Nota 12 versao {link[-1]}"))


def _pacote_com_pdf(conteudo: bytes) -> bytes:
    from tests.test_base_enet_notas import _pacote as pacote_de_teste

    return pacote_de_teste(conteudo)


def test_baixa_todas_as_versoes_da_dfp_e_pula_o_que_ja_esta_guardado(url, monkeypatch):
    mundo = _Mundo(monkeypatch, datetime(2026, 10, 25, 0, 30, tzinfo=FUSO))
    assert carga_enet_notas.main(["--desde", "2024", "--ate", "2024"]) == 0
    assert mundo.pacotes == [f"http://enet/DFP/2024/{v}" for v in (1, 2, 3)]
    mundo.pacotes = []
    assert carga_enet_notas.main(["--desde", "2024", "--ate", "2024"]) == 0
    assert mundo.pacotes == []


def test_para_no_fim_da_janela(url, monkeypatch):
    mundo = _Mundo(monkeypatch, datetime(2026, 10, 25, 5, 45, tzinfo=FUSO))
    assert carga_enet_notas.main(["--desde", "2024", "--ate", "2024"]) == 0
    assert len(mundo.pacotes) == 2  # 5h45 e 5h55; às 6h05 não começa o terceiro


def test_nada_veio_e_algo_falhou_devolve_1(url, monkeypatch):
    mundo = _Mundo(monkeypatch, datetime(2026, 10, 25, 0, 30, tzinfo=FUSO))
    monkeypatch.setattr(mundo.__class__, "baixar", lambda self, link: b"isto nao e zip")
    assert carga_enet_notas.main(["--desde", "2024", "--ate", "2024"]) == 1


# --- montagem ------------------------------------------------------------------------------------
def test_monta_o_parquet_do_ano_da_referencia_com_a_origem_de_cada_linha(
    url, monkeypatch, tmp_path
):
    motor = criar_engine(url)
    agora = datetime(2026, 10, 25, 3, tzinfo=UTC)
    try:
        with motor.begin() as c:
            zip_do_indice = _zip_do_ano("DFP", 2024)
            registrar(
                c, "cvm-hist-dfp", "https://dados.cvm.gov.br/dfp_cia_aberta_2024.zip",
                zip_do_indice, "ok", agora=agora,
                caminho_do_original=acervo.guardar_original(
                    "cvm-hist-dfp", "https://dados.cvm.gov.br/dfp_cia_aberta_2024.zip",
                    zip_do_indice, agora,
                ),
            )  # fmt: skip
            enet_notas.guardar_notas(
                c,
                "http://enet/DFP/2024/1",
                _pacote_com_pdf(pdf("Nota 12 Emprestimos")),
                agora,
            )
        cadastro = pd.DataFrame(
            {
                "cnpj": ["00.000.208/0001-00"],
                "registro": pd.to_datetime(["1990-01-01"]),
                "cancelamento": pd.to_datetime([None]),
            }
        )
        monkeypatch.setattr(
            enet_notas,
            "cadastro_do_acervo",
            lambda conexao: (cadastro, {"url": "cad", "sha256": "x"}),
        )
        monkeypatch.setattr(enet_notas, "versao_do_codigo", lambda: "abc1234")
        with motor.connect() as c:
            por_ano = enet_notas.montar(c, tmp_path / "base", agora)
    finally:
        motor.dispose()
    assert por_ano == {2024: 1}
    tabela = pd.read_parquet(tmp_path / "base" / "notas_dfp" / "2024.parquet")
    linha = tabela.iloc[0]
    assert "Emprestimos" in linha["texto"] and linha["pagina"] == 1
    assert linha["disponivel_em"] == date(2025, 1, 10)
    assert linha["versao_do_codigo"] == "abc1234" and len(linha["origem_sha256"]) == 64


def test_sem_cadastro_a_montagem_para_em_vez_de_chutar_a_data(
    url, monkeypatch, tmp_path
):
    monkeypatch.setattr(enet_notas, "cadastro_do_acervo", lambda conexao: None)
    motor = criar_engine(url)
    try:
        with motor.connect() as c, pytest.raises(enet_notas.SemOIndice):
            enet_notas.montar(c, tmp_path, datetime.now(UTC))
    finally:
        motor.dispose()
