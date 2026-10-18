"""Configuração comum dos testes."""

from collections import Counter

import pytest

from scripts import repartir_testes
from src.acervo import VARIAVEL_DA_PASTA
from src.armazenamento import VARIAVEL_DO_CAMINHO
from src.banco.conexao import criar_engine, migrar_para


def pytest_addoption(parser):
    parser.addoption(
        "--parte",
        help="roda só uma parte da suíte, como no CI: --parte=K/N ou --parte=trader-K/N (scripts/repartir_testes.py)",
    )
    parser.addoption(
        "--gravar-duracoes",
        action="store_true",
        help="mede o tempo de cada arquivo e grava em tests/duracoes.json (rode a suíte inteira)",
    )


_ARQUIVOS_DA_PARTE = pytest.StashKey[set[str]]()


def _arquivos_de_teste(config) -> list[str]:
    pasta = config.rootpath / "tests"
    return [
        arquivo.relative_to(config.rootpath).as_posix()
        for arquivo in pasta.glob("test_*.py")
    ]


def pytest_ignore_collect(collection_path, config):
    # a parte é escolhida antes de abrir os arquivos: as partes do app nem importam os testes do
    # trader, que precisam de pacotes que elas não instalam
    escolhidos = config.stash.get(_ARQUIVOS_DA_PARTE, None)
    e_arquivo_de_teste = (
        collection_path.parent == config.rootpath / "tests"
        and collection_path.name.startswith("test_")
        and collection_path.suffix == ".py"
    )
    if escolhidos is None or not e_arquivo_de_teste:
        return None
    if f"tests/{collection_path.name}" not in escolhidos:
        return True
    return None


class _MedidorDeDuracoes:
    """Soma o tempo de cada arquivo de teste e grava em tests/duracoes.json no fim (--gravar-duracoes)."""

    def __init__(self, config):
        self.config = config
        self.medidas = Counter()

    def pytest_runtest_logreport(self, report):
        # com o xdist, o processo principal recebe aqui os relatórios de todos os processos
        self.medidas[report.nodeid.split("::")[0]] += report.duration

    def pytest_sessionfinish(self):
        existentes = _arquivos_de_teste(self.config)
        antigas = repartir_testes.ler_duracoes()
        repartir_testes.gravar_duracoes(
            repartir_testes.juntar_duracoes(antigas, self.medidas, existentes)
        )


def pytest_configure(config):
    parte = config.getoption("--parte")
    if parte:
        duracoes = repartir_testes.ler_duracoes()
        try:
            escolhidos = repartir_testes.arquivos_da_parte(
                parte, _arquivos_de_teste(config), duracoes
            )
        except ValueError as erro:
            raise pytest.UsageError(str(erro)) from None
        config.stash[_ARQUIVOS_DA_PARTE] = escolhidos
    eh_processo_do_xdist = hasattr(config, "workerinput")
    if config.getoption("--gravar-duracoes") and not eh_processo_do_xdist:
        config.pluginmanager.register(_MedidorDeDuracoes(config), "medidor_de_duracoes")


@pytest.fixture(scope="session", autouse=True)
def limites_de_depois_do_lancamento():
    """Os testes conferem os limites de cada plano; o pré-lançamento (tudo liberado) tem os seus.

    Vale para a sessão inteira: fixtures de módulo (ex.: `no_gratuito`) são montadas antes das
    de função e já precisam ver a trava desligada.
    """
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("src.planos.TUDO_LIBERADO_NO_PRE_LANCAMENTO", False)
        yield


@pytest.fixture(autouse=True)
def banco_de_precos_isolado(tmp_path, monkeypatch):
    """Cada teste usa um banco SQLite novo: nenhum teste lê ou escreve o banco de verdade."""
    monkeypatch.setenv(VARIAVEL_DO_CAMINHO, str(tmp_path / "precos_de_teste.sqlite"))
    # o acervo do arquivo original (src/acervo.py) também fica na pasta do teste
    monkeypatch.setenv(VARIAVEL_DA_PASTA, str(tmp_path / "acervo"))
    # e a memória do Pulse dos ativos sem preço começa vazia (um teste não herda a do outro)
    monkeypatch.setattr("src.api_v1.rotas._sem_preco", {})


@pytest.fixture
def banco(tmp_path, monkeypatch):
    """Um banco SQLite com as migrações aplicadas, usado pelo app como `TICKERLAB_DATABASE_URL`."""
    url = f"sqlite:///{(tmp_path / 'conta.sqlite').as_posix()}"
    monkeypatch.setenv("TICKERLAB_DATABASE_URL", url)
    migrar_para("head", url=url)
    motor = criar_engine(url)
    yield motor
    motor.dispose()
