"""Logs estruturados: JSON válido, sem perder a exceção, e configuráveis por variável."""

import io
import json
import logging

import pytest

from src import logs


@pytest.fixture(autouse=True)
def restaurar_logging():
    raiz = logging.getLogger()
    antes = (list(raiz.handlers), raiz.level)
    yield
    raiz.handlers[:] = antes[0]
    raiz.setLevel(antes[1])
    for nome in logs.LOGGERS_DO_UVICORN:
        logging.getLogger(nome).handlers = []
        logging.getLogger(nome).propagate = True


def _registro(mensagem="olá", nivel=logging.INFO, exc_info=None):
    return logging.LogRecord(
        "tickerlab.teste", nivel, __file__, 1, mensagem, None, exc_info
    )


def test_json_tem_hora_nivel_origem_e_mensagem():
    linha = json.loads(logs.FormatadorJson().format(_registro("tudo certo")))
    assert linha["mensagem"] == "tudo certo" and linha["nivel"] == "INFO"
    assert linha["origem"] == "tickerlab.teste"
    assert linha["hora"].endswith("+00:00")


def test_json_guarda_acentos_sem_escapar():
    texto = logs.FormatadorJson().format(_registro("ação concluída"))
    assert "ação concluída" in texto


def test_json_e_uma_linha_so_mesmo_com_quebras_na_mensagem():
    texto = logs.FormatadorJson().format(_registro("linha 1\nlinha 2"))
    assert "\n" not in texto
    assert json.loads(texto)["mensagem"] == "linha 1\nlinha 2"


def test_json_inclui_a_excecao_com_tamanho_limitado():
    try:
        raise ValueError("x" * 10_000)
    except ValueError:
        import sys

        registro = _registro("falhou", logging.ERROR, sys.exc_info())
    linha = json.loads(logs.FormatadorJson().format(registro))
    assert "ValueError" in linha["erro"]
    assert len(linha["erro"]) <= logs.TAMANHO_MAXIMO_DO_ERRO


def test_configurar_em_json_escreve_json(monkeypatch):
    destino = io.StringIO()
    handler = logs.configurar_logs({"TICKERLAB_LOG_FORMATO": "json"})
    handler.setStream(destino)
    logging.getLogger("tickerlab.x").info("pronto")
    assert (
        json.loads(destino.getvalue().strip().splitlines()[-1])["mensagem"] == "pronto"
    )


def test_configurar_em_texto_por_padrao():
    handler = logs.configurar_logs({})
    assert not isinstance(handler.formatter, logs.FormatadorJson)


def test_nivel_vem_da_variavel_e_valor_ruim_vira_info():
    logs.configurar_logs({"TICKERLAB_LOG_NIVEL": "warning"})
    assert logging.getLogger().level == logging.WARNING
    logs.configurar_logs({"TICKERLAB_LOG_NIVEL": "banana"})
    assert logging.getLogger().level == logging.INFO


def test_chamar_de_novo_nao_duplica_os_registros():
    for _ in range(3):
        logs.configurar_logs({})
    nossos = [
        h for h in logging.getLogger().handlers if getattr(h, "_do_tickerlab", False)
    ]
    assert len(nossos) == 1


def test_json_leva_os_logs_do_uvicorn_pelo_mesmo_caminho():
    handler = logs.configurar_logs({"TICKERLAB_LOG_FORMATO": "json"})
    for nome in logs.LOGGERS_DO_UVICORN:
        assert logging.getLogger(nome).handlers == [handler]
        assert logging.getLogger(nome).propagate is False
