"""Todo pin dos `requirements*.txt` tem quem o use (casa em ordem, fila 701).

Um pacote fixado num `requirements*.txt` precisa de um dos três: ser importado pelo código do
repositório (uma raiz); estar em `EXCECOES`, com o motivo (comando, plugin ou motor carregado pelo
nome); ou ser puxado, pelos metadados `Requires-Dist` dos pacotes instalados, por um pin que já é
usado. Pin sem uso é peso na instalação e na imagem Docker, e engana quem lê o arquivo.

Como o teste confere:

- Raízes: os módulos de primeiro nível importados (por AST) em todos os `.py` do repositório, fora
  de `.venv`, `node_modules`, `site`, `novo`, `web`, `.git`, `__pycache__`, das pastas ocultas e de
  `estudos/` (os cadernos usam o `requirements-estudos.txt`). Para o `requirements-prod.txt` só
  conta o código que a imagem leva: `app.py`, `src/`, `base/`, `telas/` e `migracoes/` (ver o
  `Dockerfile` e o `.dockerignore`).
- Módulo → distribuição pelos metadados instalados (`top_level.txt` ou `RECORD`), como faz o
  `importlib.metadata.packages_distributions()`, que aqui levaria uns 6 s por conferir arquivo por
  arquivo no disco.
- Arestas: `Requires-Dist`, ignorando os marcadores de ambiente (`sys_platform`, `python_version`:
  o pin vale no Windows do PC e no Linux do CI) e seguindo um extra só quando alguém o pediu
  (`coverage[toml]`). Contando todo extra, nada ficaria sem uso: o altair, o pytest e outros listam
  o Jupyter inteiro nos extras de desenvolvimento.
- Pin não instalado é pulado: no CI, as partes do app instalam só o `requirements.txt`, as do
  trader o `-trader`, e ninguém instala o `-estudos`.
- Também reprova: pin repetido no mesmo arquivo; pacote do `requirements-estudos.txt` que também
  está em outro arquivo; e, com o Jupyter instalado, pin do `-estudos` que o resto do código já
  puxa (ele pertence ao `requirements.txt`).
"""

import ast
import inspect
import os
import re
import sys
from collections import deque
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from functools import cache
from importlib import metadata
from pathlib import Path

import pytest

# na suíte em paralelo, tudo num processo só: o AST dos 1.600 arquivos fica em cache no módulo
pytestmark = pytest.mark.xdist_group("requirements")

RAIZ = Path(__file__).resolve().parent.parent
ARQUIVO_PRINCIPAL = "requirements.txt"
ARQUIVO_DA_IMAGEM = "requirements-prod.txt"
ARQUIVO_DO_TRADER = "requirements-trader.txt"
ARQUIVO_DOS_ESTUDOS = "requirements-estudos.txt"
ARQUIVOS_COM_CODIGO = (ARQUIVO_PRINCIPAL, ARQUIVO_DA_IMAGEM, ARQUIVO_DO_TRADER)
TODOS_OS_ARQUIVOS = (*ARQUIVOS_COM_CODIGO, ARQUIVO_DOS_ESTUDOS)
# sem código do repositório (ambiente, pastas geradas, JavaScript) ou com requirements próprio
PASTAS_PULADAS = frozenset(
    {".venv", "node_modules", "site", "novo", "web", ".git", "__pycache__", "estudos"}
)
# o que o Dockerfile copia e tem Python (tests/, trader/ e scripts/ ficam fora da imagem)
CODIGO_DA_IMAGEM = ("app.py", "src", "base", "telas", "migracoes", "conector_remoto")

# Pins usados sem `import`: nome como o pip o vê → motivo conferido no código, no CI ou nos
# metadados. Exceção nova só com o motivo real; exceção sem pin em nenhum arquivo falha o teste.
EXCECOES: dict[str, str] = {
    "ruff": "linter e formatador: `python -m ruff` no CI e nos comandos do AGENTS.md",
    "pyright": "checagem de tipos: `python -m pyright` no CI (pyrightconfig.json)",
    "pytest-cov": "plugin do pytest: `--cov` no CI (configuração no .coveragerc)",
    "pytest-xdist": "plugin do pytest: `-n 4 --dist loadgroup` na suíte e no CI",
    "pytest-qt": (
        "plugin do pytest: a fixture `qtbot` dos testes do painel do trader "
        "(tests/test_trader_interface.py)"
    ),
    "uvicorn": (
        "servidor da API: `uvicorn src.api:app` no compose.yaml (hoje o Streamlit também o puxa)"
    ),
    "authlib": (
        "o `st.login` do Streamlit (telas/conta/entrada.py) carrega a Authlib por dentro; o "
        "Streamlit só a declara no extra `auth`"
    ),
    "psycopg": (
        "driver do PostgreSQL que o SQLAlchemy carrega pela URL `postgresql+psycopg://` "
        "(src/configuracao.py)"
    ),
    "psycopg-binary": (
        "a implementação em C do psycopg, que ele usa quando está instalada (é o extra "
        "`psycopg[binary]`)"
    ),
    "xlrd": (
        'motor do `pd.read_excel(engine="xlrd")` para o .xls antigo (base/cripto/receita.py, '
        "trader/p2/dividendos.py)"
    ),
    "kaleido": (
        "exporta as figuras do Plotly (`figura.write_image`) em scripts/gerar_imagens_do_readme.py"
    ),
    "onnxruntime": (
        "motor de inferência do rapidocr (src/leitura.py), que o carrega pelo nome e não o "
        "declara nos metadados"
    ),
}

# nome, extras e, logo depois, o fim, a versão (`==`, `>=`, `(>=` nos metadados antigos), `@ url`
# ou `;` do marcador: uma URL ou um caminho solto não casa
_REQUISITO = re.compile(
    r"^([A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)\s*(?:\[([^\]]*)\])?\s*(?=$|[=<>!~@;(])"
)
_MARCADOR_DE_EXTRA = re.compile(r"""extra\s*==\s*["']([^"']+)["']""")
_COMENTARIO = re.compile(r"(?:^|\s+)#.*$")
_OPCOES_DE_INCLUSAO = ("-r", "--requirement")
# onde um comando pode estar aninhado (função, classe, if, for, try, with, match)
_BLOCOS = ("body", "orelse", "finalbody", "handlers", "cases")


@dataclass(frozen=True)
class Pin:
    """Uma linha `pacote[extras]==versão` de um requirements, com o nome como o pip o vê."""

    nome: str
    extras: frozenset[str]
    linha: int


@dataclass(frozen=True)
class Requisito:
    """Uma aresta `Requires-Dist`: o pacote exigido, os extras pedidos e o extra que a condiciona."""

    nome: str
    extras: frozenset[str]
    so_com_o_extra: str | None


@dataclass(frozen=True)
class Instalados:
    """O que os metadados do ambiente dizem: módulo → distribuições e distribuição → requisitos."""

    distribuicoes_do_modulo: Mapping[str, frozenset[str]]
    requisitos: Mapping[str, tuple[Requisito, ...]]

    def tem(self, nome: str) -> bool:
        """A distribuição está instalada?"""
        return nome in self.requisitos


def normalizar(nome: str) -> str:
    """O nome como o pip compara (PEP 503): minúsculas, e `-`, `_` e `.` seguidos viram um `-`."""
    return re.sub(r"[-_.]+", "-", nome).lower()


def _ler_requisito(texto: str) -> tuple[str, frozenset[str]]:
    """Nome normalizado e extras de um requisito (`pkg[a,b]>=1; marcador`); erro se não parece um."""
    sem_marcador = texto.split(";", 1)[0]
    casado = _REQUISITO.match(sem_marcador)
    if casado is None:
        raise ValueError(f"requisito que o teste não entende: {texto!r}")
    extras = (casado.group(2) or "").split(",")
    return normalizar(casado.group(1)), frozenset(
        normalizar(extra.strip()) for extra in extras if extra.strip()
    )


def _linhas_uteis(caminho: Path) -> Iterator[tuple[int, str]]:
    """As linhas de um requirements sem comentário nem vazio, com o número da linha."""
    for numero, linha in enumerate(
        caminho.read_text(encoding="utf-8").splitlines(), start=1
    ):
        util = _COMENTARIO.sub("", linha).strip()
        if util:
            yield numero, util


def ler_pins(caminho: Path) -> list[Pin]:
    """Os pins do arquivo (sem os que ele inclui por `-r`), na ordem em que estão."""
    pins = []
    for numero, linha in _linhas_uteis(caminho):
        if linha.startswith("-"):
            continue  # `-r outro.txt` e opções do pip: ver `arquivos_incluidos`
        nome, extras = _ler_requisito(linha)
        pins.append(Pin(nome, extras, numero))
    return pins


def arquivos_incluidos(caminho: Path) -> list[Path]:
    """Os arquivos que o `-r` puxa, inclusive em cadeia (caminho relativo ao arquivo que inclui)."""
    incluidos: list[Path] = []
    for _, linha in _linhas_uteis(caminho):
        opcao, _, resto = linha.partition(" ")
        if opcao in _OPCOES_DE_INCLUSAO:
            outro = caminho.parent / resto.strip()
            incluidos.extend([outro, *arquivos_incluidos(outro)])
    return incluidos


def pins_disponiveis(caminho: Path) -> list[Pin]:
    """Os pins do arquivo e dos que ele inclui por `-r`: todos ficam instalados juntos."""
    return [
        pin
        for arquivo in (caminho, *arquivos_incluidos(caminho))
        for pin in ler_pins(arquivo)
    ]


def _modulos_da_distribuicao(dist: metadata.Distribution) -> set[str]:
    """Os módulos de primeiro nível que a distribuição instala: `top_level.txt` ou, senão, `RECORD`.

    É o que o `importlib.metadata.packages_distributions()` faz, sem conferir se cada arquivo
    existe no disco (43 mil `stat`, uns 6 s neste venv).
    """
    declarados = dist.read_text("top_level.txt")
    if declarados:
        return set(declarados.split())
    modulos: set[str] = set()
    for linha in (dist.read_text("RECORD") or "").splitlines():
        caminho = linha.split(",", 1)[0]
        primeiro, barra, _ = caminho.partition("/")
        if not barra:
            # arquivo solto: `six.py`, `_cffi_backend.cp312-win_amd64.pyd`
            modulo = inspect.getmodulename(primeiro)
            if modulo:
                modulos.add(modulo)
        elif "." not in primeiro and primeiro != "__pycache__":
            # pacote; fica de fora `x.dist-info`, `x.libs` e `../../Scripts`
            modulos.add(primeiro)
    return modulos


def _requisitos_da_distribuicao(dist: metadata.Distribution) -> tuple[Requisito, ...]:
    """As arestas `Requires-Dist` da distribuição, com o extra que condiciona cada uma."""
    requisitos = []
    for texto in dist.requires or []:
        nome, extras = _ler_requisito(texto)
        condicao = _MARCADOR_DE_EXTRA.search(texto.partition(";")[2])
        so_com_o_extra = normalizar(condicao.group(1)) if condicao else None
        requisitos.append(Requisito(nome, extras, so_com_o_extra))
    return tuple(requisitos)


@cache
def instalados() -> Instalados:
    """Lê os metadados do ambiente uma vez só (uns 0,2 s)."""
    modulos: dict[str, set[str]] = {}
    requisitos: dict[str, tuple[Requisito, ...]] = {}
    for dist in metadata.distributions():
        nome_bruto = dist.metadata["Name"]
        if not nome_bruto:
            continue
        nome = normalizar(nome_bruto)
        if nome in requisitos:
            continue  # a mesma distribuição vista por dois caminhos do sys.path
        requisitos[nome] = _requisitos_da_distribuicao(dist)
        for modulo in _modulos_da_distribuicao(dist):
            modulos.setdefault(modulo, set()).add(nome)
    return Instalados(
        {modulo: frozenset(nomes) for modulo, nomes in modulos.items()}, requisitos
    )


def _arquivos_python(*entradas: Path) -> Iterator[Path]:
    """Os `.py` dentro das entradas (arquivo ou pasta), pulando as pastas da lista e as ocultas."""
    for entrada in entradas:
        if entrada.is_file():
            yield entrada
            continue
        for pasta, subpastas, arquivos in os.walk(entrada):
            subpastas[:] = sorted(
                s
                for s in subpastas
                if s not in PASTAS_PULADAS and not s.startswith(".")
            )
            yield from (Path(pasta) / a for a in sorted(arquivos) if a.endswith(".py"))


def _modulos_importados(arvore: ast.Module) -> Iterator[str]:
    """Os módulos de primeiro nível dos `import` do arquivo, em qualquer bloco.

    Desce só pelos comandos (não pelas expressões): dá o mesmo resultado que o `ast.walk` em um
    terço do tempo, e são 1.600 arquivos.
    """
    pendentes: list[ast.AST] = list(arvore.body)
    while pendentes:
        no = pendentes.pop()
        if isinstance(no, ast.Import):
            yield from (apelido.name.partition(".")[0] for apelido in no.names)
        elif isinstance(no, ast.ImportFrom) and no.level == 0 and no.module:
            yield no.module.partition(".")[0]
        for bloco in _BLOCOS:
            filhos = getattr(no, bloco, None)
            if isinstance(filhos, list):
                pendentes.extend(filhos)


@cache
def _pacotes_do_repositorio() -> frozenset[str]:
    """Os nomes de primeiro nível do próprio repositório (`src`, `telas`, `app`...), que não vêm do pip."""
    nomes = set()
    for caminho in RAIZ.iterdir():
        if caminho.is_dir():
            nomes.add(caminho.name)
        elif caminho.suffix == ".py":
            nomes.add(caminho.stem)
    return frozenset(nomes)


@cache
def _modulos_do_arquivo(arquivo: Path) -> frozenset[str]:
    """Os módulos de primeiro nível que o arquivo importa; cada arquivo é lido uma vez só.

    O `ast.parse` dos 1.600 arquivos é o que custa no teste (uns 4 s); o código da imagem é
    conferido duas vezes (no requirements.txt e no -prod) e não pode ser lido duas vezes.
    """
    arvore = ast.parse(arquivo.read_bytes(), filename=str(arquivo))
    return frozenset(_modulos_importados(arvore))


def raizes(arquivos: Iterable[Path]) -> frozenset[str]:
    """As distribuições cujos módulos o código importa (fora a biblioteca padrão e o repositório)."""
    modulos: set[str] = set()
    for arquivo in arquivos:
        modulos |= _modulos_do_arquivo(arquivo)
    modulos -= sys.stdlib_module_names | _pacotes_do_repositorio()
    distribuicoes: set[str] = set()
    for modulo in modulos:
        distribuicoes |= instalados().distribuicoes_do_modulo.get(modulo, frozenset())
    return frozenset(distribuicoes)


@cache
def raizes_do_repositorio() -> frozenset[str]:
    """O que todo o código do repositório importa (menos as pastas puladas)."""
    return raizes(_arquivos_python(RAIZ))


@cache
def raizes_da_imagem() -> frozenset[str]:
    """O que o código que vai na imagem Docker importa."""
    return raizes(_arquivos_python(*(RAIZ / caminho for caminho in CODIGO_DA_IMAGEM)))


def puxados(
    sementes: Iterable[tuple[str, frozenset[str]]], ambiente: Instalados | None = None
) -> dict[str, str | None]:
    """Tudo o que as sementes puxam pelos `Requires-Dist` instalados: nome → quem o puxou (None na semente).

    Cada semente é (nome, extras pedidos). Os marcadores de ambiente são ignorados; um extra só é
    seguido quando foi pedido (`pkg[extra]`), e o pedido se propaga pela cadeia.
    """
    ambiente = ambiente or instalados()
    quem_puxou: dict[str, str | None] = {}
    visitados: set[tuple[str, frozenset[str]]] = set()
    fila: deque[tuple[str, frozenset[str], str | None]] = deque(
        (nome, extras, None) for nome, extras in sementes
    )
    while fila:
        nome, extras, origem = fila.popleft()
        quem_puxou.setdefault(nome, origem)
        if (nome, extras) in visitados:
            continue
        visitados.add((nome, extras))
        for requisito in ambiente.requisitos.get(nome, ()):
            if requisito.so_com_o_extra is None or requisito.so_com_o_extra in extras:
                fila.append((requisito.nome, requisito.extras, nome))
    return quem_puxou


def _sementes(
    caminho: Path, raizes_do_codigo: frozenset[str]
) -> list[tuple[str, frozenset[str]]]:
    """De onde a busca parte: as raízes do código e os pins do arquivo que são raiz ou exceção.

    Raiz não pinada também entra: o que ela exige está no arquivo por causa dela.
    """
    sementes = [(raiz, frozenset[str]()) for raiz in raizes_do_codigo]
    sementes += [
        (pin.nome, pin.extras)
        for pin in pins_disponiveis(caminho)
        if pin.nome in raizes_do_codigo or pin.nome in EXCECOES
    ]
    return sementes


def sem_uso(caminho: Path, raizes_do_codigo: frozenset[str]) -> list[Pin]:
    """Os pins instalados do arquivo que nem o código, nem as exceções, nem outro pin usado puxam."""
    usados = puxados(_sementes(caminho, raizes_do_codigo))
    return [
        pin
        for pin in ler_pins(caminho)
        if instalados().tem(pin.nome) and pin.nome not in usados
    ]


def _como_resolver(arquivo: str, sobrando: list[Pin]) -> str:
    """A mensagem da falha: cada pin sem uso, a linha e o que fazer com ele."""
    do_jupyter = puxados(
        (pin.nome, pin.extras) for pin in ler_pins(RAIZ / ARQUIVO_DOS_ESTUDOS)
    )
    linhas = [
        f"{arquivo}: pins sem uso (sem import no código, sem exceção e sem pin usado que os puxe):"
    ]
    for pin in sobrando:
        destino = (
            f"; só o Jupyter o puxa: leve-o para o {ARQUIVO_DOS_ESTUDOS}"
            if pin.nome in do_jupyter
            else ""
        )
        linhas.append(f"  - {pin.nome} (linha {pin.linha}){destino}")
    linhas.append(
        "Tire o pin ou, se ele é usado sem import (comando, plugin, motor carregado pelo nome), "
        "escreva o motivo em EXCECOES de tests/test_requirements.py."
    )
    return "\n".join(linhas)


@pytest.mark.parametrize("arquivo", ARQUIVOS_COM_CODIGO)
def test_todo_pin_tem_quem_o_use(arquivo):
    raizes_do_codigo = (
        raizes_da_imagem() if arquivo == ARQUIVO_DA_IMAGEM else raizes_do_repositorio()
    )
    sobrando = sem_uso(RAIZ / arquivo, raizes_do_codigo)
    assert not sobrando, _como_resolver(arquivo, sobrando)


@pytest.mark.parametrize("arquivo", TODOS_OS_ARQUIVOS)
def test_nenhum_pin_se_repete_no_mesmo_arquivo(arquivo):
    linhas_por_nome: dict[str, list[int]] = {}
    for pin in ler_pins(RAIZ / arquivo):
        linhas_por_nome.setdefault(pin.nome, []).append(pin.linha)
    repetidos = {
        nome: linhas for nome, linhas in linhas_por_nome.items() if len(linhas) > 1
    }
    assert not repetidos, (
        f"{arquivo}: pin repetido (nome: linhas) {repetidos}; deixe uma linha só"
    )


def test_os_estudos_nao_repetem_os_outros_arquivos():
    dos_estudos = {pin.nome for pin in ler_pins(RAIZ / ARQUIVO_DOS_ESTUDOS)}
    for arquivo in ARQUIVOS_COM_CODIGO:
        repetidos = sorted(dos_estudos & {pin.nome for pin in ler_pins(RAIZ / arquivo)})
        assert not repetidos, (
            f"{repetidos}: no {ARQUIVO_DOS_ESTUDOS} e no {arquivo}; um pacote fica num arquivo só"
        )


def test_os_estudos_so_tem_o_que_o_resto_do_codigo_nao_puxa():
    """Com o Jupyter instalado: pin do -estudos que o requirements.txt já puxa pertence a ele."""
    dos_estudos = [
        pin
        for pin in ler_pins(RAIZ / ARQUIVO_DOS_ESTUDOS)
        if instalados().tem(pin.nome)
    ]
    if not dos_estudos:
        pytest.skip(
            f"nada do {ARQUIVO_DOS_ESTUDOS} está instalado (só no PC, para os cadernos)"
        )
    usados = puxados(_sementes(RAIZ / ARQUIVO_PRINCIPAL, raizes_do_repositorio()))
    indevidos = [
        f"{pin.nome} (linha {pin.linha}; puxado por {usados[pin.nome] or 'um import do código'})"
        for pin in dos_estudos
        if pin.nome in usados
    ]
    assert not indevidos, (
        f"o resto do código já puxa {indevidos}: leve de volta ao {ARQUIVO_PRINCIPAL}"
    )


def test_toda_excecao_e_um_pin_escrito_como_o_pip():
    pinados = {
        pin.nome for arquivo in TODOS_OS_ARQUIVOS for pin in ler_pins(RAIZ / arquivo)
    }
    for nome, motivo in EXCECOES.items():
        assert nome == normalizar(nome), (
            f"{nome}: escreva como o pip (minúsculas e hífens)"
        )
        assert nome in pinados, (
            f"{nome}: exceção sem pin em nenhum requirements; apague-a"
        )
        assert motivo.strip(), f"{nome}: exceção sem motivo"


def test_leitura_entende_comentario_extra_marcador_e_inclusao(tmp_path):
    (tmp_path / "base.txt").write_text("A_b.C==1  # comentário\n", encoding="utf-8")
    (tmp_path / "topo.txt").write_text(
        "# só comentário\n\n-r base.txt\nPsycopg[Binary]==3; sys_platform == 'win32'\n",
        encoding="utf-8",
    )
    assert ler_pins(tmp_path / "topo.txt") == [Pin("psycopg", frozenset({"binary"}), 4)]
    assert arquivos_incluidos(tmp_path / "topo.txt") == [tmp_path / "base.txt"]
    assert ler_pins(tmp_path / "base.txt") == [Pin("a-b-c", frozenset(), 1)]
    assert [pin.nome for pin in pins_disponiveis(tmp_path / "topo.txt")] == [
        "psycopg",
        "a-b-c",
    ]


@pytest.mark.parametrize(
    "linha", ["https://exemplo/pacote.whl", "./pacote.whl", "==1.0"]
)
def test_linha_que_nao_e_requisito_e_erro(linha):
    with pytest.raises(ValueError, match="não entende"):
        _ler_requisito(linha)


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("pandas>=2", ("pandas", frozenset())),
        ("coverage[toml]>=7 ; extra == 'cov'", ("coverage", frozenset({"toml"}))),
        ("mako (>=1.0)", ("mako", frozenset())),
        ("pkg @ https://exemplo/pkg.whl", ("pkg", frozenset())),
        ("Zope.Interface_x", ("zope-interface-x", frozenset())),
    ],
)
def test_leitura_de_requisito_como_nos_metadados(texto, esperado):
    assert _ler_requisito(texto) == esperado


def test_extra_so_e_seguido_quando_pedido():
    nada = frozenset[str]()
    ambiente = Instalados(
        {},
        {
            "a": (Requisito("b", nada, None), Requisito("c", nada, "dev")),
            "b": (Requisito("d", frozenset({"x"}), None),),
            "d": (Requisito("e", nada, "x"), Requisito("f", nada, "y")),
        },
    )
    assert set(puxados([("a", nada)], ambiente)) == {"a", "b", "d", "e"}
    assert set(puxados([("a", frozenset({"dev"}))], ambiente)) == {
        "a",
        "b",
        "c",
        "d",
        "e",
    }
    assert puxados([("a", nada)], ambiente)["e"] == "d"


def test_imports_dentro_de_funcao_try_e_if_contam_e_os_relativos_nao():
    codigo = (
        "import a.b as ab\n"
        "def f():\n"
        "    try:\n"
        "        from c.d import e\n"
        "    except ImportError:\n"
        "        import g\n"
        "if True:\n"
        "    from . import h\n"
        "else:\n"
        "    import i\n"
    )
    assert set(_modulos_importados(ast.parse(codigo))) == {"a", "c", "g", "i"}
