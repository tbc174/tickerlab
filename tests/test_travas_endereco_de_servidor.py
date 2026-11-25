"""Trava da regra "nada de IP ou detalhe de servidor no repositório" (AGENTS.md, o repositório é público).

Pega o que identifica uma máquina nossa: nome na rede privada (`maquina.<rede>.ts.net`) e número na faixa que essa
rede usa (a faixa CGNAT, o /10 que começa em 100.64). Deixa passar o que não identifica nada: a faixa interna do Docker e os números
inventados dos testes (10.x, 172.16-31.x, 192.168.x), e os exemplos com `<tailnet>` ou `exemplo`. A mensagem de
erro diz o arquivo e a linha, nunca o endereço.
"""

from __future__ import annotations

import ipaddress
import re
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]

# Nome de máquina na rede privada (Tailscale). Os exemplos do repositório usam `<tailnet>` ou `exemplo`.
_NOME_NA_REDE_PRIVADA = re.compile(
    r"\b([a-z0-9-]+)\.([a-z0-9-]+)\.ts\.net\b", re.IGNORECASE
)
PALAVRAS_DE_EXEMPLO = frozenset(
    {"exemplo", "example", "tailnet", "sua-rede", "minha-rede"}
)

# A rede privada dá a cada máquina um número desta faixa; a faixa só aparece no código quando alguém cola um.
# Montada por número (0x64400000 = começo da faixa CGNAT), para este arquivo não cair na própria varredura.
FAIXA_DA_REDE_PRIVADA = ipaddress.IPv4Network((0x64400000, 10))
_NUMERO_DE_QUATRO_PARTES = re.compile(r"(?<![\d.])(\d{1,3}(?:\.\d{1,3}){3})(?![\d.])")


def _nomes_reais(texto: str) -> list[str]:
    return [
        achado.group(0)
        for achado in _NOME_NA_REDE_PRIVADA.finditer(texto)
        if not (
            {achado.group(1).lower(), achado.group(2).lower()} & PALAVRAS_DE_EXEMPLO
        )
    ]


def _numeros_da_rede_privada(texto: str) -> list[str]:
    achados = []
    for numero in _NUMERO_DE_QUATRO_PARTES.findall(texto):
        try:
            endereco = ipaddress.ip_address(numero)
        except ValueError:
            continue  # 999.1.2.3, versão de programa etc.
        if endereco in FAIXA_DA_REDE_PRIVADA:
            achados.append(numero)
    return achados


def _linhas_do_git(padrao: str) -> list[str]:
    try:
        resultado = subprocess.run(
            ["git", "-C", str(RAIZ), "grep", "-I", "-n", "-i", "-E", padrao],
            capture_output=True,
            check=False,
            text=True,
            encoding="utf-8",
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as erro:
        pytest.skip(f"sem git: {erro}")
    if resultado.returncode not in (0, 1):  # 1 = nada achado
        pytest.skip(f"git grep falhou: {resultado.stderr.strip()}")
    return resultado.stdout.splitlines()


def _lugares(linhas: list[str], achar) -> list[str]:
    lugares = []
    for linha in linhas:
        arquivo, numero, texto = linha.split(":", 2)
        if achar(texto):
            lugares.append(f"{arquivo}:{numero}")
    return lugares


def test_a_varredura_de_nome_separa_o_exemplo_do_real() -> None:
    assert _nomes_reais("https://servidor.<tailnet>.ts.net:8443") == []
    assert _nomes_reais("https://servidor.exemplo.ts.net:8443") == []
    rede = "rede123"  # montado na hora, como abaixo
    assert len(_nomes_reais(f"ssh usuario@maquina.{rede}.ts.net")) == 1


def test_a_varredura_de_numero_separa_a_rede_privada_do_resto() -> None:
    # montados na hora, para este arquivo não cair na própria varredura
    primeiro = "100"
    da_rede = f"{primeiro}.101.7.9"
    assert _numeros_da_rede_privada(f"ssh {da_rede}") == [da_rede]
    assert (
        _numeros_da_rede_privada(
            "rede do docker 172.18.0.1 e teste 10.0.0.5 e 192.168.0.10"
        )
        == []
    )
    assert (
        _numeros_da_rede_privada(
            "versão 1.2.3.4, 100.63.255.255 e 100.128.0.1 ficam fora"
        )
        == []
    )
    assert _numeros_da_rede_privada("CNPJ 10.608.405/0001-60 e 999.100.64.1") == []


def test_nenhum_nome_de_maquina_da_rede_privada_versionado() -> None:
    achados = _lugares(_linhas_do_git(r"\.ts\.net"), _nomes_reais)
    assert not achados, (
        f"nome de máquina da rede privada versionado em {achados}. Leia de uma variável de ambiente "
        "e deixe `<tailnet>` nos exemplos."
    )


def test_nenhum_numero_da_rede_privada_versionado() -> None:
    linhas = _linhas_do_git(
        r"(^|[^0-9.])100\.(6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7])\.[0-9]"
    )
    achados = _lugares(linhas, _numeros_da_rede_privada)
    assert not achados, (
        f"número da rede privada versionado em {achados}. Leia de uma variável de ambiente; "
        "em teste, use a faixa do Docker (172.16.0.0/12) ou 10.0.0.0/8."
    )
