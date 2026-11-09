"""Onde a CLI acha a chave e o endereço da API.

A chave vem de `TICKERLAB_API_KEY` ou do arquivo que `tickerlab login` grava, nesta ordem. Nunca de um
argumento da linha de comando: ele fica no histórico do terminal e aparece na lista de processos. O arquivo
fica na pasta de configuração do usuário, com permissão só do dono (0600 no Linux e no macOS; no Windows,
a pasta `%APPDATA%` já é só da conta).

O endereço vem de `TICKERLAB_API_URL` (padrão: o de produção). A chave só segue por HTTPS; HTTP só para a
própria máquina (`localhost`), onde a API roda nos testes e no desenvolvimento.
"""

import json
import os
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlsplit

VARIAVEL_DA_CHAVE = "TICKERLAB_API_KEY"
VARIAVEL_DO_ENDERECO = "TICKERLAB_API_URL"
VARIAVEL_DA_PASTA = "TICKERLAB_CONFIG_DIR"
ENDERECO_PADRAO = "https://api.tickerlab.com.br"
NOME_DA_PASTA = "tickerlab"
NOME_DO_ARQUIVO = "credenciais.json"
CAMPO_DA_CHAVE = "api_key"
SO_O_DONO_LE = 0o600
SO_O_DONO_ENTRA = 0o700
MAQUINAS_LOCAIS = frozenset({"localhost", "127.0.0.1", "::1"})


class ConfiguracaoInvalidaError(ValueError):
    """Endereço ou chave que a CLI não usa (a mensagem diz por quê, sem repetir a chave)."""


def pasta_da_configuracao(ambiente: Mapping[str, str]) -> Path:
    """A pasta da configuração: `TICKERLAB_CONFIG_DIR`, ou a do usuário no sistema."""
    if ambiente.get(VARIAVEL_DA_PASTA):
        return Path(ambiente[VARIAVEL_DA_PASTA])
    if os.name == "nt" and ambiente.get("APPDATA"):
        return Path(ambiente["APPDATA"]) / NOME_DA_PASTA
    base = ambiente.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / NOME_DA_PASTA


def arquivo_da_chave(ambiente: Mapping[str, str]) -> Path:
    """O arquivo em que `tickerlab login` grava a chave."""
    return pasta_da_configuracao(ambiente) / NOME_DO_ARQUIVO


def conferir_chave(chave: str) -> str:
    """A chave sem espaços nas pontas; recusa a vazia ou com espaço no meio (colada pela metade)."""
    limpa = chave.strip()
    if not limpa or any(letra.isspace() for letra in limpa):
        raise ConfiguracaoInvalidaError(
            "A chave está vazia ou tem espaço no meio: cole a chave inteira, de uma vez."
        )
    return limpa


def chave_do_arquivo(ambiente: Mapping[str, str]) -> str | None:
    """A chave gravada pelo `tickerlab login`, ou None se não há arquivo."""
    arquivo = arquivo_da_chave(ambiente)
    if not arquivo.is_file():
        return None
    try:
        conteudo = json.loads(arquivo.read_text(encoding="utf-8"))
    except (OSError, ValueError) as erro:
        raise ConfiguracaoInvalidaError(
            f"Não consegui ler {arquivo}: rode `tickerlab login` de novo."
        ) from erro
    chave = conteudo.get(CAMPO_DA_CHAVE) if isinstance(conteudo, dict) else None
    return chave if isinstance(chave, str) and chave.strip() else None


def chave_da_api(ambiente: Mapping[str, str]) -> str | None:
    """A chave a usar: a da variável de ambiente vale mais que a do arquivo."""
    da_variavel = ambiente.get(VARIAVEL_DA_CHAVE, "")
    if da_variavel.strip():
        return conferir_chave(da_variavel)
    return chave_do_arquivo(ambiente)


def gravar_chave(chave: str, ambiente: Mapping[str, str]) -> Path:
    """Grava a chave no arquivo do usuário, só com leitura do dono, e devolve o caminho.

    Escreve num arquivo novo já com a permissão certa e troca de uma vez (`os.replace`): a chave nunca
    fica num arquivo que outra conta da máquina possa ler, nem pela metade.
    """
    arquivo = arquivo_da_chave(ambiente)
    arquivo.parent.mkdir(parents=True, exist_ok=True, mode=SO_O_DONO_ENTRA)
    provisorio = arquivo.with_suffix(".tmp")
    provisorio.unlink(missing_ok=True)
    descritor = os.open(provisorio, os.O_WRONLY | os.O_CREAT | os.O_EXCL, SO_O_DONO_LE)
    with os.fdopen(descritor, "w", encoding="utf-8") as saida:
        json.dump({CAMPO_DA_CHAVE: conferir_chave(chave)}, saida)
    os.replace(provisorio, arquivo)
    os.chmod(arquivo, SO_O_DONO_LE)
    return arquivo


def apagar_chave(ambiente: Mapping[str, str]) -> bool:
    """Apaga o arquivo da chave; diz se havia um."""
    arquivo = arquivo_da_chave(ambiente)
    existia = arquivo.is_file()
    arquivo.unlink(missing_ok=True)
    return existia


def endereco_da_api(ambiente: Mapping[str, str]) -> str:
    """O endereço da API, sem a barra do fim; recusa HTTP fora da própria máquina (a chave iria aberta)."""
    endereco = (ambiente.get(VARIAVEL_DO_ENDERECO) or ENDERECO_PADRAO).strip()
    partes = urlsplit(endereco)
    local = partes.hostname in MAQUINAS_LOCAIS or (partes.hostname or "").endswith(
        ".localhost"
    )
    if partes.scheme == "https" or (partes.scheme == "http" and local):
        return endereco.rstrip("/")
    raise ConfiguracaoInvalidaError(
        f"{VARIAVEL_DO_ENDERECO} precisa começar com https:// (http:// só para localhost): "
        "a chave não pode viajar aberta."
    )
