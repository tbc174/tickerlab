"""Paridade entre a CLI `tickerlab` e o conector remoto (linha 570; Tiago, 11/11/2026: "integrar nossa CLI
na IA deles ou na minha pra fazer pesquisas específicas e mais complexas com a nossa base").

Todo comando de leitura da CLI tem uma ferramenta no conector, e a ferramenta faz à API externa os mesmos
pedidos que o comando faz: mesma rota e mesmos parâmetros, portanto a mesma regra. Comando novo na CLI
sem ferramenta faz este teste falhar, a menos que entre em `SEM_FERRAMENTA` com o motivo escrito; ferramenta
sem comando, só em `SO_NO_CONECTOR`, também com o motivo.
"""

import httpx
import pytest
from click.testing import CliRunner
from tickerlab import comandos, configuracao

from conector_remoto import ferramentas
from tests import ajudantes_do_conector as aj

# comando da CLI -> as ferramentas do conector que o cobrem
FERRAMENTAS_DO_COMANDO: dict[str, tuple[str, ...]] = {
    "prospectar": ("buscar_empresas",),
    "empresa": ("ficha_da_empresa",),
    "comparaveis": ("comparaveis",),
    "demonstracoes": ("demonstracoes",),
    "eventos": ("eventos",),
    "vinculos": ("vinculos",),
    "compradores": ("compradores_do_setor",),
    "fundo": ("fundo",),
    "novidades": ("novidades",),
    "setor": ("setores", "setor"),  # sem chave, a lista; com chave, o setor
    "catalogo": ("o_que_posso_ver",),
    "consumo": ("o_que_posso_ver",),
}
# comando sem ferramenta, com o motivo: nenhum lê a base
SEM_FERRAMENTA: dict[str, str] = {
    "login": "guarda a chave no PC; no conector a chave entra pela página /autorizar do OAuth",
    "logout": "apaga a chave guardada no PC; no conector, quem corta o acesso é revogar a chave",
    "instrucoes": "ensina a IA do PC a chamar a CLI; no conector, a descrição de cada ferramenta faz isso",
}

# ferramenta sem comando na CLI, com o motivo: quando o comando entrar, vira caso de paridade
SO_NO_CONECTOR: dict[str, str] = {}

ENDERECO = "https://api.exemplo.test"
CNPJ = "11111111000191"  # de mentira, com os dígitos verificadores certos
UM_DIA = "2026-03-31"

# (argumentos da CLI, ferramenta, argumentos da ferramenta): o mesmo pedido pelos dois lados
CASOS = [
    pytest.param(
        ["prospectar", "--uf", "SC", "--cnae", "2222600", "--aberta-antes", "2010-01-01",
         "--so-matriz", "--por-pagina", "20"],
        "buscar_empresas",
        {"uf": ["SC"], "cnae": ["2222600"], "aberta_antes_de": "2010-01-01", "so_matriz": True,
         "limite": 20},
        id="prospectar",
    ),
    pytest.param(
        ["empresa", CNPJ, "--como-era", UM_DIA],
        "ficha_da_empresa",
        {"cnpj": CNPJ, "como_era_em": UM_DIA},
        id="empresa",
    ),
    pytest.param(
        ["comparaveis", CNPJ, "--como-era", UM_DIA],
        "comparaveis",
        {"cnpj": CNPJ, "como_era_em": UM_DIA},
        id="comparaveis",
    ),
    pytest.param(
        ["demonstracoes", CNPJ, "--como-era", UM_DIA, "--periodo", "2025-12-31"],
        "demonstracoes",
        {"cnpj": CNPJ, "como_era_em": UM_DIA, "fim_do_periodo": "2025-12-31"},
        id="demonstracoes",
    ),
    pytest.param(
        ["eventos", CNPJ, "--como-era", UM_DIA, "--tipo", "auditor"],
        "eventos",
        {"cnpj": CNPJ, "como_era_em": UM_DIA, "tipos": ["auditor"]},
        id="eventos",
    ),
    pytest.param(
        ["vinculos", CNPJ, "--como-era", UM_DIA, "--profundidade", "2", "--tipo", "coligada"],
        "vinculos",
        {"cnpj": CNPJ, "como_era_em": UM_DIA, "profundidade": 2, "tipos": ["coligada"]},
        id="vinculos",
    ),
    pytest.param(
        ["compradores", "--cnae", "35115", "--uf", "SP", "--anos", "5", "--limite", "10", "--como-era", UM_DIA],
        "compradores_do_setor",
        {"cnae": "35115", "uf": "SP", "anos": 5, "limite": 10, "como_era_em": UM_DIA},
        id="compradores",
    ),
    pytest.param(
        ["fundo", CNPJ, "--como-era", UM_DIA, "--retorno-suposto", "0.1"],
        "fundo",
        {"cnpj": CNPJ, "como_era_em": UM_DIA, "retorno_suposto": 0.1},
        id="fundo",
    ),
    pytest.param(["novidades", "--dias", "14"], "novidades", {"dias": 14}, id="novidades"),
    pytest.param(["setor"], "setores", {}, id="setores"),
    pytest.param(
        ["setor", "combustiveis", "--como-era", UM_DIA],
        "setor",
        {"chave": "combustiveis", "como_era_em": UM_DIA},
        id="setor",
    ),
    pytest.param(["catalogo"], "o_que_posso_ver", {}, id="catalogo"),
    pytest.param(["consumo"], "o_que_posso_ver", {}, id="consumo"),
]  # fmt: skip


def _gravador(pedidos: list[httpx.Request]) -> httpx.MockTransport:
    return aj.api_de_mentira({}, pedidos=pedidos)


def _como_pedido(pedido: httpx.Request) -> tuple[str, tuple[tuple[str, str], ...]]:
    return pedido.url.path, tuple(sorted(pedido.url.params.multi_items()))


def _pedidos_da_cli(argumentos: list[str], tmp_path) -> set:
    pedidos: list[httpx.Request] = []

    def abrir(_endereco: str) -> httpx.Client:
        return httpx.Client(base_url=ENDERECO, transport=_gravador(pedidos))

    CliRunner().invoke(
        comandos.principal,
        [*argumentos, "--json"],
        obj=abrir,
        env={
            configuracao.VARIAVEL_DA_PASTA: str(tmp_path / "config"),
            configuracao.VARIAVEL_DA_CHAVE: aj.CHAVE_DE_MENTIRA,
            configuracao.VARIAVEL_DO_ENDERECO: ENDERECO,
        },
    )
    return {_como_pedido(p) for p in pedidos}


def _pedidos_da_ferramenta(ferramenta: str, argumentos: dict) -> set:
    pedidos: list[httpx.Request] = []
    with aj.conector(_gravador(pedidos)) as cliente:
        aj.chamar(cliente, aj.CHAVE_DE_MENTIRA, ferramenta, **argumentos)
    return {_como_pedido(p) for p in pedidos}


def test_todo_comando_da_cli_tem_ferramenta_ou_motivo_escrito():
    da_cli = set(comandos.principal.commands)
    sem_par = da_cli - set(FERRAMENTAS_DO_COMANDO) - set(SEM_FERRAMENTA)
    assert not sem_par, (
        f"comando novo na CLI sem ferramenta no conector: {sorted(sem_par)}. Crie a ferramenta "
        "(conector_remoto/ferramentas.py) ou ponha o comando em SEM_FERRAMENTA com o motivo."
    )
    assert set(FERRAMENTAS_DO_COMANDO) | set(SEM_FERRAMENTA) == da_cli  # nada sobrando
    assert all(motivo.strip() for motivo in SEM_FERRAMENTA.values())


def test_toda_ferramenta_do_conector_corresponde_a_um_comando():
    cobertas = {f for lista in FERRAMENTAS_DO_COMANDO.values() for f in lista}
    assert cobertas | set(SO_NO_CONECTOR) == set(ferramentas.CONJUNTOS_DA_FERRAMENTA)
    assert not cobertas & set(SO_NO_CONECTOR)  # ou tem comando, ou está na lista
    assert all(motivo.strip() for motivo in SO_NO_CONECTOR.values())


def test_os_casos_cobrem_todo_comando_de_leitura():
    comandos_dos_casos = {caso.values[0][0] for caso in CASOS}
    assert comandos_dos_casos == set(FERRAMENTAS_DO_COMANDO)


@pytest.mark.parametrize(("argumentos_da_cli", "ferramenta", "argumentos"), CASOS)
def test_ferramenta_faz_os_mesmos_pedidos_que_o_comando(
    argumentos_da_cli, ferramenta, argumentos, tmp_path
):
    """A ferramenta pode pedir a mais (o catálogo da chave, para filtrar a lista), nunca outra coisa."""
    assert ferramenta in FERRAMENTAS_DO_COMANDO[argumentos_da_cli[0]]
    da_cli = _pedidos_da_cli(argumentos_da_cli, tmp_path)
    assert da_cli, "a CLI não fez pedido nenhum (argumentos errados?)"
    assert da_cli <= _pedidos_da_ferramenta(ferramenta, argumentos)
