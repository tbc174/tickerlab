"""Entrega das análises aprovadas (linha 376), sem rede nem dependências externas.

Casa: empacotar --origem analises/v1/analises --entradas analises/entradas > pacote.tar
VPS: receber --dados dados_locais < pacote.tar (sob flock, pela chave de envio restrita).
Os originais e as fotografias anteriores são preservados. A troca do link é atômica.
"""

import argparse
import hashlib
import io
import json
import os
import re
import sys
import tarfile
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

MAXIMO_PACOTE = 100 * 1024 * 1024
MAXIMO_ARQUIVO = 5_000_000  # o mesmo teto do leitor do app
MAXIMO_ARQUIVOS = 2000
NOME = re.compile(r"[0-9]{14}\.json")


def _json(valor: object) -> bytes:
    return json.dumps(
        valor, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode()


def _hash(conteudo: bytes) -> str:
    return hashlib.sha256(conteudo).hexdigest()


def _ler(caminho: Path) -> dict[str, Any]:
    if caminho.is_symlink() or caminho.stat().st_size > MAXIMO_ARQUIVO:
        raise ValueError("arquivo de origem inválido")
    valor = json.loads(caminho.read_bytes())
    if not isinstance(valor, dict):
        raise ValueError("JSON deve ser objeto")  # noqa: TRY004 — conteúdo externo inválido
    return valor


def _validar(nome: str, valor: dict[str, Any]) -> None:
    if not isinstance(valor, dict) or valor.get("publicavel") is not True:
        raise ValueError("análise sem aprovação")
    porta3 = valor.get("linhagem", {}).get("porta3")
    if not isinstance(porta3, dict) or porta3.get("veredito") != "aprovado":
        raise ValueError("análise sem aprovação humana")
    if re.sub(r"\D", "", valor.get("cnpj", "")) != nome.removesuffix(".json"):
        raise ValueError("CNPJ diferente do arquivo")
    if not re.fullmatch(r"[0-9a-f]{64}", valor.get("hash_da_entrada_atual", "")):
        raise ValueError("hash da entrada inválido")
    date.fromisoformat(valor.get("corte", ""))
    if not isinstance(valor.get("analise", {}).get("partes"), list):
        raise ValueError("texto fora do formato")  # noqa: TRY004 — conteúdo externo inválido


def _com_corte(valor: dict[str, Any], nome: str, entradas: Path) -> dict[str, Any]:
    if "corte" in valor:
        return valor
    # Lote anterior ao PR B: recuperar o metadado só da entrada exata, sem remontar texto.
    for caminho in sorted(entradas.rglob(nome)):
        entrada = _ler(caminho)
        if _hash(_json(entrada)) == valor.get("hash_da_entrada_atual"):
            return {**valor, "corte": entrada["corte"]}
    raise ValueError(f"sem entrada original compatível: {nome}")


def empacotar(origem: Path, entradas: Path) -> bytes:
    """Tar determinístico com apenas textos aprovados; uma revogação sai da fotografia."""
    caminhos = sorted(c for c in origem.glob("*.json") if NOME.fullmatch(c.name))
    if not origem.is_dir() or not caminhos:
        raise ValueError("origem ausente ou vazia; não publicar")
    conteudos = {}
    for caminho in caminhos:
        if not NOME.fullmatch(caminho.name):
            continue
        valor = _ler(caminho)
        if valor.get("publicavel") is not True:
            continue
        valor = _com_corte(valor, caminho.name, entradas)
        _validar(caminho.name, valor)
        conteudos[caminho.name] = _json(valor)
    manifesto = {"versao": 1, "arquivos": {n: _hash(c) for n, c in conteudos.items()}}
    conteudos["manifesto.json"] = _json(manifesto)
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        for nome, conteudo in conteudos.items():
            info = tarfile.TarInfo(nome)
            info.size, info.mode = len(conteudo), 0o644
            tar.addfile(info, io.BytesIO(conteudo))
    pacote = buffer.getvalue()
    _conferir_pacote(pacote)
    return pacote


def _conteudos(pacote: bytes) -> dict[str, bytes]:
    if len(pacote) > MAXIMO_PACOTE:
        raise ValueError("pacote grande demais")
    conteudos, total = {}, 0
    try:
        with tarfile.open(fileobj=io.BytesIO(pacote), mode="r:") as tar:
            for membro in tar:
                nome = membro.name
                if not membro.isfile() or membro.issparse():
                    raise ValueError("só arquivos comuns")
                if nome != "manifesto.json" and not NOME.fullmatch(nome):
                    raise ValueError("nome de arquivo inválido")
                if nome in conteudos or len(conteudos) >= MAXIMO_ARQUIVOS:
                    raise ValueError("arquivo repetido ou arquivos demais")
                total += membro.size
                if not 0 <= membro.size <= MAXIMO_ARQUIVO or total > MAXIMO_PACOTE:
                    raise ValueError("conteúdo grande demais")
                arquivo = tar.extractfile(membro)
                if arquivo is None:
                    raise ValueError("arquivo sem conteúdo")
                conteudos[nome] = arquivo.read()
    except tarfile.TarError as erro:
        raise ValueError("tar inválido") from erro
    return conteudos


def _conferir_pacote(pacote: bytes) -> dict[str, bytes]:
    conteudos = _conteudos(pacote)
    try:
        manifesto = json.loads(conteudos["manifesto.json"])
        esperados = manifesto["arquivos"]
        if manifesto["versao"] != 1 or set(esperados) != set(conteudos) - {
            "manifesto.json"
        }:
            raise ValueError("manifesto não corresponde ao pacote")
        for nome, esperado in esperados.items():
            if _hash(conteudos[nome]) != esperado:
                raise ValueError("hash do arquivo não confere")
            _validar(nome, json.loads(conteudos[nome]))
    except (KeyError, TypeError, AttributeError) as erro:
        raise ValueError("pacote fora do formato") from erro
    return conteudos


def instalar(pacote: bytes, dados: Path) -> int:
    """Valida tudo antes de gravar; publica por link relativo, visível nos dois contêineres."""
    conteudos = _conferir_pacote(pacote)
    atual = dados / "analises"
    if atual.exists() and not atual.is_symlink():
        raise ValueError("destino existente não é link; preservar e migrar manualmente")
    manifesto = conteudos["manifesto.json"]
    if (atual / "manifesto.json").is_file() and (
        atual / "manifesto.json"
    ).read_bytes() == manifesto:
        return len(conteudos) - 1
    fotografias = dados / ".analises-publicadas"
    fotografias.mkdir(parents=True, exist_ok=True)
    pasta = Path(tempfile.mkdtemp(prefix="lote-", dir=fotografias))
    pasta.chmod(0o755)
    for nome, conteudo in conteudos.items():
        (pasta / nome).write_bytes(conteudo)
        (pasta / nome).chmod(0o644)
    link = dados / f".analises-{pasta.name}"
    link.symlink_to(pasta.relative_to(dados), target_is_directory=True)
    os.replace(link, atual)
    return len(conteudos) - 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="passo", required=True)
    enviar = sub.add_parser("empacotar")
    enviar.add_argument("--origem", type=Path, required=True)
    enviar.add_argument("--entradas", type=Path, required=True)
    receber = sub.add_parser("receber")
    receber.add_argument("--dados", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.passo == "empacotar":
            sys.stdout.buffer.write(empacotar(args.origem, args.entradas))
        else:
            quantidade = instalar(sys.stdin.buffer.read(MAXIMO_PACOTE + 1), args.dados)
            print(f"recebido: {quantidade} análises aprovadas")
    except (ValueError, OSError) as erro:
        print(f"FALHAS: análises: {erro}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
