"""Falhas reais e simuladas do vigia, com HTTP substituído e sem internet."""

import json
from datetime import UTC, datetime, timedelta
from http.client import HTTPSConnection

import pytest

from scripts import vigiar_saude_publica as vigia

AGORA = datetime(2026, 11, 27, 12, tzinfo=UTC)
ALVOS = [
    ("app.tickerlab.com.br", "/classico/_stcore/health"),
    ("api.tickerlab.com.br", "/saude"),
    ("mcp.tickerlab.com.br", "/saude"),
    ("api.tickerlab.com.br", "/saude/frescor"),
]


@pytest.fixture
def rede(monkeypatch):
    respostas = {alvo: (200, b"ok") for alvo in ALVOS}
    respostas[ALVOS[-1]] = (
        200,
        json.dumps(
            {
                "base_atualizada_em": (AGORA - timedelta(hours=1)).isoformat(),
                "fonte": "mtime_parquet",
            }
        ).encode(),
    )
    pedidos = []

    def responder(conexao, metodo, caminho, body=None, headers=None, **kwargs):
        assert metodo == "GET" and body is None
        assert not headers or set(headers) <= {"Cache-Control"}
        assert 0 < conexao.timeout <= 30
        alvo = (conexao.host, caminho)
        assert alvo in ALVOS, "pedido fora das quatro rotas públicas"
        pedidos.append(alvo)
        conexao.alvo_do_teste = alvo

    class Resposta:
        def __init__(self, codigo, corpo):
            self.status = codigo
            self.corpo = corpo

        def read(self, limite):
            assert 0 < limite <= 8193
            return self.corpo[:limite]

    def receber(conexao):
        valor = respostas[conexao.alvo_do_teste]
        if isinstance(valor, Exception):
            raise valor
        return Resposta(*valor)

    class Relogio(datetime):
        @classmethod
        def now(cls, tz=None):
            return AGORA

    monkeypatch.setattr(HTTPSConnection, "request", responder)
    monkeypatch.setattr(HTTPSConnection, "getresponse", receber)
    monkeypatch.setattr(vigia, "datetime", Relogio, raising=False)
    monkeypatch.delenv("FORCAR_FALHA", raising=False)
    monkeypatch.delenv("FRESCOR_MAX_HORAS", raising=False)
    return respostas, pedidos


def test_vigia_saudavel_so_chama_as_quatro_rotas(rede):
    assert vigia.main() == 0
    assert rede[1] == ALVOS


@pytest.mark.parametrize("alvo", ALVOS)
@pytest.mark.parametrize("codigo", [204, 302, 401, 404, 503])
def test_qualquer_http_diferente_de_200_falha_sem_seguir_redirecionamento(
    rede, alvo, codigo
):
    rede[0][alvo] = (codigo, b"corpo privado que nao deve aparecer")
    assert vigia.main() == 1
    assert rede[1] == ALVOS


@pytest.mark.parametrize(
    "erro", [TimeoutError("detalhe privado"), OSError("detalhe privado")]
)
def test_falha_de_rede_nao_mascara_as_outras_checagens(rede, erro, capsys):
    rede[0][ALVOS[0]] = erro
    assert vigia.main() == 1
    assert rede[1] == ALVOS
    assert "detalhe privado" not in capsys.readouterr().out


@pytest.mark.parametrize("horas,esperado", [(71, 0), (72, 0), (72.001, 1), (-1, 1)])
def test_limite_de_frescor_e_data_futura(rede, horas, esperado):
    rede[0][ALVOS[-1]] = (
        200,
        json.dumps(
            {
                "base_atualizada_em": (AGORA - timedelta(hours=horas)).isoformat(),
                "fonte": "mtime_parquet",
            }
        ).encode(),
    )
    assert vigia.main() == esperado


@pytest.mark.parametrize(
    "corpo",
    [
        b"nao e json",
        b"{}",
        b"[]",
        b"null",
        b"x" * 8193,
        b'{"base_atualizada_em": null}',
        b'{"base_atualizada_em": "2026-11-27"}',
        b'{"base_atualizada_em": "invalida"}',
    ],
)
def test_frescor_invalido_falha_sem_publicar_corpo(rede, corpo, capsys):
    rede[0][ALVOS[-1]] = (200, corpo)
    assert vigia.main() == 1
    assert "base_atualizada_em" not in capsys.readouterr().out


def test_limite_de_frescor_pode_ser_reduzido_pelo_ambiente(rede, monkeypatch):
    monkeypatch.setenv("FRESCOR_MAX_HORAS", "0.5")
    assert vigia.main() == 1


@pytest.mark.parametrize("limite", ["0", "-1", "nan", "inf", "abc"])
def test_limite_invalido_falha(rede, monkeypatch, limite):
    monkeypatch.setenv("FRESCOR_MAX_HORAS", limite)
    assert vigia.main() == 1


def test_falha_forcada_fica_vermelha_mesmo_com_tudo_saudavel(rede, monkeypatch, capsys):
    monkeypatch.setenv("FORCAR_FALHA", "true")
    assert vigia.main() == 1
    assert "Falha forçada" in capsys.readouterr().out
