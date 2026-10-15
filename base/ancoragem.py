"""Âncora de uma versão da base: a raiz de Merkle dos manifestos (ADR 0078; ADR 0055,
exigências 9 e 13).

Cada tabela da base já tem um manifesto (`base/parquet.py`) com o SHA-256 do conteúdo e as origens.
Aqui os manifestos atuais de uma pasta viram **folhas** (uma por tabela inteira, nunca por linha) e as
folhas viram uma **raiz de Merkle**: um único hash de 32 bytes que muda se qualquer tabela mudar. A
âncora (`texto_da_ancora`) leva só nomes de tabela e hashes; é ela que `scripts/ancorar_base.py`
carimba no Bitcoin pelo OpenTimestamps. A **prova de inclusão** de uma tabela deixa um cliente
conferir que o manifesto dela está na raiz sem ver as outras tabelas.

A árvore segue a RFC 6962 (Certificate Transparency): prefixo 0x00 na folha e 0x01 no nó, e a divisão
pela maior potência de 2, sem duplicar a última folha (o defeito do Bitcoin, CVE-2012-2459).

**LGPD (ADR 0075 e 0077):** só entra manifesto de tabela inteira; tabela de pessoas com menos de
`LINHAS_MINIMAS_PESSOAS` linhas não entra (seria quase o hash de um registro individual).
"""

import hashlib
import json
import re
from pathlib import Path
from typing import Any

FORMATO = "tickerlab-ancora-v1"
ALGORITMO = "sha256, árvore da RFC 6962"
LINHAS_MINIMAS_PESSOAS = 50
VERSAO_ANTIGA = re.compile(
    r"\.v\d+$"
)  # `emissores.v1.json`: versão guardada por `base/parquet.py`


def hash_folha(dados: bytes) -> bytes:
    return hashlib.sha256(b"\x00" + dados).digest()


def hash_no(esquerda: bytes, direita: bytes) -> bytes:
    return hashlib.sha256(b"\x01" + esquerda + direita).digest()


def _divisao(total: int) -> int:
    """A maior potência de 2 menor que `total` (RFC 6962, seção 2.1)."""
    k = 1
    while k * 2 < total:
        k *= 2
    return k


def raiz_de_merkle(folhas: list[bytes]) -> bytes:
    """Raiz da árvore com as folhas (já passadas por `hash_folha`) nesta ordem."""
    if not folhas:
        raise ValueError("uma âncora precisa de pelo menos uma folha")
    if len(folhas) == 1:
        return folhas[0]
    k = _divisao(len(folhas))
    return hash_no(raiz_de_merkle(folhas[:k]), raiz_de_merkle(folhas[k:]))


def prova_de_inclusao(folhas: list[bytes], indice: int) -> list[dict[str, str]]:
    """Os irmãos da folha `indice` até a raiz, de baixo para cima, com o lado de cada um."""
    if len(folhas) == 1:
        return []
    k = _divisao(len(folhas))
    if indice < k:
        irmao = {"lado": "direita", "hash": raiz_de_merkle(folhas[k:]).hex()}
        return [*prova_de_inclusao(folhas[:k], indice), irmao]
    irmao = {"lado": "esquerda", "hash": raiz_de_merkle(folhas[:k]).hex()}
    return [*prova_de_inclusao(folhas[k:], indice - k), irmao]


def conferir_prova(folha: bytes, caminho: list[dict[str, str]], raiz: bytes) -> bool:
    atual = folha
    for passo in caminho:
        irmao = bytes.fromhex(passo["hash"])
        atual = (
            hash_no(irmao, atual)
            if passo["lado"] == "esquerda"
            else hash_no(atual, irmao)
        )
    return atual == raiz


def _canonico(objeto: object) -> bytes:
    """O mesmo objeto vira sempre os mesmos bytes, qualquer que seja a ordem das chaves."""
    return json.dumps(
        objeto, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")


def _e_de_pessoas(nome: str) -> bool:
    return "pessoas" in nome.split("/")


def folha_do_manifesto(nome: str, manifesto: dict[str, Any]) -> bytes:
    """Bytes da folha de uma tabela: o nome e o manifesto inteiro, em JSON canônico."""
    if "sha256_da_tabela" not in manifesto or "linhas" not in manifesto:
        raise ValueError(
            f"{nome}: só entra manifesto de tabela inteira (base/parquet.py)"
        )
    if _e_de_pessoas(nome) and manifesto["linhas"] < LINHAS_MINIMAS_PESSOAS:
        raise ValueError(
            f"{nome}: tabela de pessoas com menos de {LINHAS_MINIMAS_PESSOAS} linhas não é ancorada"
        )
    return _canonico({"tabela": nome, "manifesto": manifesto})


def folha_de_arquivo(nome: str, conteudo: bytes) -> bytes:
    """Bytes da folha de um arquivo (pré-registro, lote de rótulos): o nome e o SHA-256 dele."""
    return _canonico({"arquivo": nome, "sha256": hashlib.sha256(conteudo).hexdigest()})


def manifestos_atuais(pasta: Path) -> dict[str, dict[str, Any]]:
    """Manifestos da versão atual de cada tabela, por nome (`fca/emissores`), em ordem."""
    achados = {}
    for arquivo in pasta.rglob("*.json"):
        if (
            VERSAO_ANTIGA.search(arquivo.stem)
            or not arquivo.with_suffix(".parquet").exists()
        ):
            continue
        nome = arquivo.relative_to(pasta).with_suffix("").as_posix()
        achados[nome] = json.loads(arquivo.read_text(encoding="utf-8"))
    return dict(sorted(achados.items()))


def folhas_da_base(pasta: Path) -> dict[str, bytes]:
    return {
        nome: hash_folha(folha_do_manifesto(nome, manifesto))
        for nome, manifesto in manifestos_atuais(pasta).items()
    }


def montar_ancora(folhas: dict[str, bytes], rotulo: str) -> dict[str, Any]:
    nomes = sorted(folhas)
    return {
        "formato": FORMATO,
        "rotulo": rotulo,
        "algoritmo": ALGORITMO,
        "folhas": [{"nome": nome, "hash": folhas[nome].hex()} for nome in nomes],
        "raiz": raiz_de_merkle([folhas[nome] for nome in nomes]).hex(),
    }


def texto_da_ancora(ancora: dict[str, Any]) -> bytes:
    """Os bytes que são carimbados: JSON com chaves em ordem, para dar sempre o mesmo hash."""
    texto = json.dumps(ancora, sort_keys=True, ensure_ascii=False, indent=1) + "\n"
    return texto.encode("utf-8")


def diferencas(ancora: dict[str, Any], folhas: dict[str, bytes]) -> list[str]:
    """O que mudou entre a âncora e as folhas de hoje (lista vazia: é a mesma versão)."""
    anotadas = {f["nome"]: f["hash"] for f in ancora["folhas"]}
    achados = []
    for nome in sorted(anotadas.keys() | folhas.keys()):
        if nome not in folhas:
            achados.append(f"{nome}: sumiu")
        elif nome not in anotadas:
            achados.append(f"{nome}: não estava na âncora")
        elif anotadas[nome] != folhas[nome].hex():
            achados.append(f"{nome}: mudou")
    folhas_anotadas = [bytes.fromhex(f["hash"]) for f in ancora["folhas"]]
    if not achados and raiz_de_merkle(folhas_anotadas).hex() != ancora["raiz"]:
        achados.append("raiz: não bate com as folhas anotadas")
    return achados


def prova_da_tabela(ancora: dict[str, Any], nome: str) -> dict[str, Any]:
    """O que se entrega ao cliente de uma tabela: o caminho até a raiz, sem as outras folhas."""
    if _e_de_pessoas(nome):
        raise ValueError(f"{nome}: tabela de pessoas não tem prova de inclusão (LGPD)")
    nomes = [f["nome"] for f in ancora["folhas"]]
    folhas = [bytes.fromhex(f["hash"]) for f in ancora["folhas"]]
    return {
        "formato": FORMATO,
        "rotulo": ancora["rotulo"],
        "nome": nome,
        "caminho": prova_de_inclusao(folhas, nomes.index(nome)),
        "raiz": ancora["raiz"],
    }


def conferir_prova_da_tabela(prova: dict[str, Any], manifesto: dict[str, Any]) -> bool:
    try:
        folha = hash_folha(folha_do_manifesto(prova["nome"], manifesto))
    except ValueError:
        return False
    return conferir_prova(folha, prova["caminho"], bytes.fromhex(prova["raiz"]))
