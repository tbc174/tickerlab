"""Reparte os arquivos de teste entre as máquinas do CI, para a suíte rodar em paralelo.

No CI a suíte roda em várias máquinas ao mesmo tempo, cada uma com uma parte
(`python -m pytest --parte=2/3`, ou `--parte=trader-1/2`; com o "=": separado, o pytest confunde
o `trader` com a pasta `trader/`). O `tests/conftest.py` chama este módulo para saber quais
arquivos ficam em cada parte:

- `trader-K/N` (ou `trader`, todos juntos): os testes da pesquisa de trading (`test_trader_*`,
  `test_c1_*`), os únicos que precisam do `requirements-trader.txt` (torch, Qt, LightGBM...).
- `K/N`: o resto, o do app, que instala só o `requirements.txt` (mais rápido e igual ao que o app
  usa em produção).

Cada grupo é repartido em N partes de tempo parecido pelos tempos guardados em
`tests/duracoes.json`. Arquivo inteiro numa parte só, para a preparação de cada módulo não se
repetir em várias máquinas. Arquivo novo, ainda sem tempo guardado, conta como a mediana.

Os tempos se refazem com `python -m pytest -n 4 --dist loadgroup --gravar-duracoes` (só precisa
quando as partes ficarem muito desiguais: um tempo velho não quebra nada, só equilibra pior).
"""

import json
import statistics
from collections.abc import Iterable, Mapping
from fnmatch import fnmatch
from pathlib import Path, PurePosixPath

RAIZ = Path(__file__).resolve().parent.parent
ARQUIVO_DE_DURACOES = RAIZ / "tests" / "duracoes.json"
PARTE_DO_TRADER = "trader"
PREFIXO_DO_TRADER = "trader-"
PADROES_DO_TRADER = ("test_trader_*.py", "test_c1_*.py")
# tempo de um arquivo sem medida quando ainda não há medida nenhuma
SEGUNDOS_SEM_MEDIDA = 1.0


def e_do_trader(arquivo: str) -> bool:
    """Diz se o arquivo de teste (caminho como `tests/test_x.py`) é da pesquisa de trading."""
    nome = PurePosixPath(arquivo).name
    return any(fnmatch(nome, padrao) for padrao in PADROES_DO_TRADER)


def ler_parte(texto: str) -> tuple[int, int]:
    """Lê `K/N` (parte K de N, começando em 1) e recusa o que não faz sentido."""
    try:
        numero, total = (int(pedaco) for pedaco in texto.split("/"))
    except ValueError:
        raise ValueError(
            f"parte inválida: {texto!r} (use 'K/N', 'trader-K/N' ou 'trader', como '2/3')"
        ) from None
    if not 1 <= numero <= total:
        raise ValueError(f"parte inválida: {texto!r} (K vai de 1 a N)")
    return numero, total


def repartir(
    arquivos: Iterable[str], duracoes: Mapping[str, float], partes: int
) -> list[list[str]]:
    """Divide os arquivos em `partes` grupos com tempo total parecido.

    O maior arquivo vai para o grupo mais leve, depois o seguinte, e assim por diante (o método
    guloso do "maior primeiro"). A ordem é sempre a mesma para a mesma entrada: cada processo do
    pytest calcula a repartição sozinho e todos precisam chegar ao mesmo resultado.
    """
    conhecidos = [duracoes[arquivo] for arquivo in arquivos if arquivo in duracoes]
    padrao = statistics.median(conhecidos) if conhecidos else SEGUNDOS_SEM_MEDIDA
    tempo = {arquivo: duracoes.get(arquivo, padrao) for arquivo in arquivos}
    grupos: list[list[str]] = [[] for _ in range(partes)]
    totais = [0.0] * partes
    for arquivo in sorted(tempo, key=lambda nome: (-tempo[nome], nome)):
        mais_leve = totais.index(min(totais))
        grupos[mais_leve].append(arquivo)
        totais[mais_leve] += tempo[arquivo]
    return grupos


def arquivos_da_parte(
    parte: str, arquivos: Iterable[str], duracoes: Mapping[str, float]
) -> set[str]:
    """Devolve os arquivos que a parte pedida (`K/N`, `trader-K/N` ou `trader`) roda."""
    arquivos = sorted(set(arquivos))
    do_trader = [arquivo for arquivo in arquivos if e_do_trader(arquivo)]
    if parte == PARTE_DO_TRADER:
        return set(do_trader)
    if parte.startswith(PREFIXO_DO_TRADER):
        grupo = do_trader
        parte = parte.removeprefix(PREFIXO_DO_TRADER)
    else:
        grupo = [arquivo for arquivo in arquivos if not e_do_trader(arquivo)]
    numero, total = ler_parte(parte)
    return set(repartir(grupo, duracoes, total)[numero - 1])


def ler_duracoes(caminho: Path = ARQUIVO_DE_DURACOES) -> dict[str, float]:
    """Lê os tempos guardados (segundos por arquivo); sem o arquivo, nenhum tempo."""
    if not caminho.exists():
        return {}
    return json.loads(caminho.read_text(encoding="utf-8"))


def juntar_duracoes(
    antigas: Mapping[str, float],
    medidas: Mapping[str, float],
    existentes: Iterable[str],
) -> dict[str, float]:
    """Atualiza os tempos com os medidos agora e esquece os arquivos que não existem mais."""
    existentes = set(existentes)
    juntas = {**antigas, **medidas}
    return {
        arquivo: round(juntas[arquivo], 1)
        for arquivo in sorted(juntas)
        if arquivo in existentes
    }


def gravar_duracoes(
    duracoes: Mapping[str, float], caminho: Path = ARQUIVO_DE_DURACOES
) -> None:
    """Grava os tempos em JSON (um arquivo por linha, em ordem, para o diff ficar legível)."""
    caminho.write_text(
        json.dumps(duracoes, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
