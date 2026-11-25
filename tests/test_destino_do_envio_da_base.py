"""O destino do envio do recorte vem de uma variável de ambiente, nunca do código (linha 988, 25/11/2026).

O repositório é público: endereço, usuário e detalhe de servidor não podem estar escritos nele (AGENTS.md,
"O que é"). Quem manda o recorte à mão por `--enviar` entrega o destino em `TICKERLAB_DESTINO_DO_ENVIO_DA_BASE`.
O envio diário de casa não passa por aqui: o roteiro dele faz o ssh por conta própria.
"""

import re
from pathlib import Path

import pytest

from scripts import montar_recorte_da_api as recorte

VARIAVEL = "TICKERLAB_DESTINO_DO_ENVIO_DA_BASE"
DESTINO_DE_TESTE = "usuario@servidor.exemplo"


def test_o_destino_vem_da_variavel_de_ambiente(monkeypatch):
    monkeypatch.setenv(VARIAVEL, DESTINO_DE_TESTE)

    comando = recorte.comando_ssh_padrao()

    assert comando[-2:] == [DESTINO_DE_TESTE, "receber-base-api"]
    assert comando[0] == "ssh"


@pytest.mark.parametrize("valor", [None, "", "   "])
def test_sem_destino_para_com_uma_frase_clara_e_sem_padrao(monkeypatch, valor):
    if valor is None:
        monkeypatch.delenv(VARIAVEL, raising=False)
    else:
        monkeypatch.setenv(VARIAVEL, valor)

    with pytest.raises(SystemExit) as parada:
        recorte.comando_ssh_padrao()

    frase = str(parada.value)
    assert VARIAVEL in frase
    assert "destino" in frase.lower()


def test_o_destino_com_espacos_nas_pontas_e_aparado(monkeypatch):
    monkeypatch.setenv(VARIAVEL, f"  {DESTINO_DE_TESTE}  ")

    assert recorte.comando_ssh_padrao()[-2] == DESTINO_DE_TESTE


@pytest.mark.parametrize(
    "valor", ["-oProxyCommand=comando", "-p 22 usuario@servidor.exemplo"]
)
def test_destino_que_parece_opcao_do_ssh_ou_traz_espaco_e_recusado(monkeypatch, valor):
    monkeypatch.setenv(VARIAVEL, valor)

    with pytest.raises(SystemExit) as parada:
        recorte.comando_ssh_padrao()

    assert VARIAVEL in str(parada.value)


def test_o_codigo_nao_traz_usuario_e_endereco_escritos():
    texto = Path(recorte.__file__).read_text(encoding="utf-8")

    # `usuario@endereco` escrito entre aspas: o formato de um destino de ssh
    assert not re.search(r"[\"'][A-Za-z0-9_.-]+@[A-Za-z0-9_.-]+[\"']", texto)
