"""Tarefa diária das regras de qualidade (série 1 da base de ML, PR 3): lê os arquivos do acervo
(sem baixar de novo), grava os achados e rodar de novo não duplica. Sem internet."""

import io
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest
import sqlalchemy as sa

from scripts import atualizar_qualidade
from src import acervo
from src import demonstracoes as dm
from src.banco.coletas import registrar
from src.banco.conexao import criar_engine, migrar_para
from src.banco.modelo import achados_de_qualidade

PASTA = Path(__file__).parent / "arquivos" / "cvm" / "fundamentos"
COLETADO_EM = datetime(2026, 10, 12, 7, tzinfo=UTC)
NO_ACERVO = {2024: "dfp_cia_aberta_2024.zip", 2025: "dfp_cia_aberta_2025.zip"}
BANCO_DO_BRASIL = "00.000.000/0001-91"
PETROBRAS = "33.000.167/0001-01"
ATIVO_DO_BB_EM_2025 = "2455143253.0000000000"


def _com_defeitos(conteudo: bytes) -> bytes:
    """O DFP 2025 de teste com dois defeitos conhecidos: o ativo total do Banco do Brasil negativo
    (R4 e R1) e a Petrobras fora do índice, como se não tivesse entregado (R8)."""
    saida = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(conteudo)) as original,
        zipfile.ZipFile(saida, "w") as novo,
    ):
        for nome in original.namelist():
            texto = original.read(nome).decode("latin-1")
            if nome == "dfp_cia_aberta_BPA_con_2025.csv":
                texto = texto.replace(
                    f";{ATIVO_DO_BB_EM_2025};", f";-{ATIVO_DO_BB_EM_2025};"
                )
            if nome == "dfp_cia_aberta_2025.csv":
                linhas = texto.splitlines()
                texto = "\n".join(l for l in linhas if not l.startswith(PETROBRAS))
            novo.writestr(nome, texto.encode("latin-1"))
    return saida.getvalue()


@pytest.fixture
def url(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'q.sqlite').as_posix()}"
    monkeypatch.setenv("TICKERLAB_DATABASE_URL", url)
    monkeypatch.setenv(acervo.VARIAVEL_DA_PASTA, str(tmp_path / "acervo"))
    migrar_para("head", url=url)
    motor = criar_engine(url)
    with motor.begin() as c:
        for ano, nome in NO_ACERVO.items():
            conteudo = (PASTA / nome).read_bytes()
            if ano == 2025:
                conteudo = _com_defeitos(conteudo)
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
def pedidos(monkeypatch):
    """O que a tarefa precisou baixar: o cadastro e o ITR de 2026 existem; o resto é 404."""
    feitos: list[str] = []

    def baixar_falso(endereco: str) -> bytes | None:
        feitos.append(endereco)
        nome = endereco.rsplit("/", 1)[-1]
        return (PASTA / nome).read_bytes() if (PASTA / nome).exists() else None

    monkeypatch.setattr(atualizar_qualidade, "baixar", baixar_falso)
    return feitos


def _abertos(url: str) -> list[sa.Row]:
    motor = criar_engine(url)
    try:
        with motor.connect() as c:
            consulta = sa.select(achados_de_qualidade).where(
                achados_de_qualidade.c.fechado_em.is_(None)
            )
            return list(c.execute(consulta))
    finally:
        motor.dispose()


def test_atualizar_qualidade_usa_o_acervo_e_grava(url, pedidos):
    assert atualizar_qualidade.main(["--ano", "2026"]) == 0
    assert not [
        p for p in pedidos if "dfp_cia_aberta_2024" in p or "dfp_cia_aberta_2025" in p
    ]
    assert dm.URL_DO_CADASTRO in pedidos
    assert dm.URL_DO_ITR.format(ano=2026) in pedidos
    achados = {(a.regra, a.cnpj, a.documento, str(a.referencia)) for a in _abertos(url)}
    assert ("R4", BANCO_DO_BRASIL, "DFP", "2025-12-31") in achados
    assert ("R1", BANCO_DO_BRASIL, "DFP", "2025-12-31") in achados
    assert ("R8", PETROBRAS, "DFP", "2025-12-31") in achados


def test_rodar_de_novo_nao_duplica(url, pedidos):
    assert atualizar_qualidade.main(["--ano", "2026"]) == 0
    primeira = sorted(
        (a.regra, a.cnpj, a.documento, a.referencia, a.conta) for a in _abertos(url)
    )
    assert atualizar_qualidade.main(["--ano", "2026"]) == 0
    segunda = sorted(
        (a.regra, a.cnpj, a.documento, a.referencia, a.conta) for a in _abertos(url)
    )
    assert primeira == segunda


def test_arquivo_que_falha_ao_baixar_nao_para_os_outros(url, monkeypatch):
    def baixar_quebrado(endereco: str) -> bytes | None:
        raise OSError("sem rede")

    monkeypatch.setattr(atualizar_qualidade, "baixar", baixar_quebrado)
    assert atualizar_qualidade.main(["--ano", "2026"]) == 1  # avisa o Kuma
    regras = {a.regra for a in _abertos(url)}
    assert {"R1", "R4"} <= regras  # os DFPs do acervo rodaram
    assert "R8" not in regras  # sem o cadastro, a R8 não roda
