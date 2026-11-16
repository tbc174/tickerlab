"""Confere que o código morto não cresceu: o vulture em modo "não piorar" (fila 701, 05/11/2026).

O vulture (https://github.com/jendrikseipp/vulture) aponta funções, classes, variáveis e atributos
que ninguém usa. Ele erra bastante (campo de modelo lido só pelo JSON, método chamado pelo framework,
atributo de biblioteca), então não dá para exigir saída vazia. O combinado é "não piorar": o que ele
aponta hoje fica em `tests/arquivos/vulture_esperado.txt` e cada rodada compara com essa lista:

- item novo → falha: apague o código morto ou, se for falso positivo, grave-o na lista com `--gravar`
  e diga no PR por quê;
- item que sumiu → falha também, para a lista ficar honesta e encolher junto com o código (`--gravar`).

A comparação ignora o número da linha (o código em volta muda sem que o item mude), usa barras
normais no caminho (o PC é Windows; o CI é Linux) e conta duplicatas (multiconjunto). O vulture não
está no `requirements.txt`: é ferramenta de desenvolvimento, instalada só no passo do CI
(`vulture==2.16`); no PC, instale-o fora do venv e aponte o `PYTHONPATH` para essa pasta.

Roda: CI (trabalho trader-2, passo do vulture) e manual: python -m scripts.conferir_codigo_morto [--gravar]
"""

import argparse
import os
import re
import subprocess
import sys
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ESPERADO = Path("tests/arquivos/vulture_esperado.txt")

# Os mesmos alvos e a mesma confiança do relatório de 05/11/2026 (pasta privada). `tests` entra para
# que o que só os testes usam não conte como morto (isso é outro relatório, mensal e não bloqueante).
ALVOS = (
    "src",
    "telas",
    "base",
    "scripts",
    "trader",
    "tests",
    "app.py",
    "cli",
    "conector_remoto",
)
CONFIANCA_MINIMA = 60
# Decoradores que registram a função em outro lugar (rotas do FastAPI, fixtures do pytest,
# validadores do Pydantic, caches e fragmentos do Streamlit, eventos do SQLAlchemy, comandos do click da
# CLI `tickerlab`): quem os leva
# não é código morto. Padrão com ponto casa com qualquer objeto na frente (`@app.get`, `@rotas.get`).
DECORADORES_IGNORADOS = (
    "@*.route",
    "@*.get",
    "@*.post",
    "@*.put",
    "@*.delete",
    "@*.patch",
    "@*.api_route",
    "@*.fixture",
    "@*.validator",
    "@*.field_validator",
    "@*.model_validator",
    "@field_validator",
    "@model_validator",
    "@*.cache_data",
    "@*.cache_resource",
    "@*.fragment",
    "@*.dialog",
    "@*.listens_for",
    "@*.command",
    "@*.group",
    # ferramentas e rotas do servidor MCP do conector remoto (linha 570)
    "@*.tool",
    "@*.custom_route",
)

# Saídas do vulture 2.16: 0 sem achado e 3 com achado são normais; 1 (arquivo ilegível) e 2
# (argumento inválido) são erro da ferramenta, e aí a lista não vale.
SAIDAS_NORMAIS_DO_VULTURE = (0, 3)
SAIDA_LISTA_DIFERENTE = 1
SAIDA_FERRAMENTA_FALHOU = 2

# `caminho:linha: mensagem (NN% confidence)`; no Windows o caminho vem com `\`.
LINHA_DO_VULTURE = re.compile(r"^(?P<caminho>.+?):(?P<linha>\d+): (?P<mensagem>.+)$")

O_QUE_FAZER_COM_O_NOVO = (
    "Item novo: apague o código morto ou, se é falso positivo (campo lido só pelo JSON, método "
    "chamado pelo framework, atributo de biblioteca), acrescente-o à lista com "
    "`python -m scripts.conferir_codigo_morto --gravar` e diga no PR por quê."
)


class VultureFalhou(Exception):
    """O vulture não rodou até o fim (não está instalado, arquivo ilegível, argumento inválido)."""


@dataclass(frozen=True)
class Diferenca:
    """O que mudou em relação à lista esperada (itens já normalizados, em ordem)."""

    novos: list[str]
    sumidos: list[str]

    @property
    def vazia(self) -> bool:
        """Diz se a rodada bateu com a lista esperada."""
        return not self.novos and not self.sumidos


def comando_do_vulture() -> list[str]:
    """Monta a linha de comando do vulture, no mesmo Python deste script (pelo `-m`)."""
    return [
        sys.executable,
        "-m",
        "vulture",
        *ALVOS,
        "--min-confidence",
        str(CONFIANCA_MINIMA),
        "--ignore-decorators",
        ",".join(DECORADORES_IGNORADOS),
    ]


def rodar_vulture(raiz: Path) -> str:
    """Roda o vulture na raiz do repositório e devolve a saída crua (uma linha por item)."""
    processo = subprocess.run(
        comando_do_vulture(),
        cwd=raiz,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,  # o código de saída é lido logo abaixo (3 é "achou código morto", não erro)
        # a saída do filho em UTF-8 também no Windows (o padrão lá é cp1252)
        env={**os.environ, "PYTHONUTF8": "1"},
    )
    erro = processo.stderr.strip()
    if erro or processo.returncode not in SAIDAS_NORMAIS_DO_VULTURE:
        raise VultureFalhou(erro or f"saiu com o código {processo.returncode}")
    return processo.stdout


def normalizar_linha(linha: str) -> str:
    """Tira o número da linha e põe barras normais: `base/x.py: unused variable 'Y' (60% confidence)`."""
    casou = LINHA_DO_VULTURE.match(linha.strip())
    if casou is None:
        raise ValueError(f"linha do vulture fora do formato esperado: {linha!r}")
    caminho = casou["caminho"].replace("\\", "/")
    return f"{caminho}: {casou['mensagem']}"


def normalizar(saida: str) -> list[str]:
    """Transforma a saída do vulture nos itens comparáveis, em ordem (duplicatas ficam)."""
    return sorted(
        normalizar_linha(linha) for linha in saida.splitlines() if linha.strip()
    )


def comparar(encontrados: list[str], esperados: list[str]) -> Diferenca:
    """Compara como multiconjuntos: o mesmo item duas vezes só bate com duas linhas na lista."""
    contagem_encontrada = Counter(encontrados)
    contagem_esperada = Counter(esperados)
    return Diferenca(
        novos=sorted((contagem_encontrada - contagem_esperada).elements()),
        sumidos=sorted((contagem_esperada - contagem_encontrada).elements()),
    )


def ler_esperado(caminho: Path) -> list[str]:
    """Lê a lista esperada: uma linha por item; linhas vazias não contam."""
    linhas = caminho.read_text(encoding="utf-8").splitlines()
    return [linha.strip() for linha in linhas if linha.strip()]


def gravar_esperado(caminho: Path, itens: list[str]) -> None:
    """Reescreve a lista esperada, uma linha por item, em ordem e com fim de linha LF (como no CI)."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8", newline="\n") as arquivo:
        arquivo.writelines(f"{item}\n" for item in itens)


def relatar(diferenca: Diferenca) -> None:
    """Imprime cada item novo (com o que fazer) e cada item que sumiu da lista."""
    for item in diferenca.novos:
        print(f"novo: {item}")
    if diferenca.novos:
        print(O_QUE_FAZER_COM_O_NOVO)
    for item in diferenca.sumidos:
        print(f"saiu da lista: {item} (rode --gravar)")


def _ler_opcoes(argumentos: list[str]) -> argparse.Namespace:
    leitor = argparse.ArgumentParser(
        description="Confere que o código morto apontado pelo vulture não cresceu."
    )
    leitor.add_argument(
        "--gravar",
        action="store_true",
        help=f"reescreve {ESPERADO.as_posix()} com o que o vulture aponta hoje",
    )
    return leitor.parse_args(argumentos)


def main(
    argumentos: list[str],
    raiz: Path = RAIZ,
    rodar: Callable[[Path], str] = rodar_vulture,
) -> int:
    """Confere (ou grava, com --gravar) a lista do código morto e devolve o código de saída."""
    opcoes = _ler_opcoes(argumentos)
    esperado = raiz / ESPERADO
    try:
        encontrados = normalizar(rodar(raiz))
    except (VultureFalhou, ValueError) as erro:
        print(f"O vulture não rodou direito: {erro}")
        return SAIDA_FERRAMENTA_FALHOU
    if opcoes.gravar:
        gravar_esperado(esperado, encontrados)
        print(f"Gravados {len(encontrados)} itens em {ESPERADO.as_posix()}.")
        return 0
    if not esperado.exists():
        print(
            f"Falta a lista esperada {ESPERADO.as_posix()}: rode --gravar para criá-la."
        )
        return SAIDA_LISTA_DIFERENTE
    diferenca = comparar(encontrados, ler_esperado(esperado))
    relatar(diferenca)
    if not diferenca.vazia:
        return SAIDA_LISTA_DIFERENTE
    print(
        f"Código morto: {len(encontrados)} itens, os mesmos de {ESPERADO.as_posix()} "
        "(nada piorou)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
