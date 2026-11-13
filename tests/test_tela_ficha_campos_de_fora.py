"""O mapa da tela da ficha confere com a API: todo campo do cadastro que a lista de não consultados pode
trazer tem par e rótulo na tela (linha 899, P2 da revisão cruzada do #1118).

A tela (`web/src/app/telas/FichaDaEmpresa.tsx`) recebe `campos_do_cadastro_nao_disponiveis` com o nome de
fora da API e o leva, por `CHAVE_DO_CAMPO_DE_FORA`, ao rótulo de `NOMES_DOS_CAMPOS`. Campo novo na API sem
par ou sem rótulo apareceria na tela com o nome cru: este teste quebra antes.
"""

import re
from pathlib import Path

from src.api_externa.conjuntos import empresas
from src.api_externa.nomes import NOMES_DE_FORA

TELA = (
    Path(__file__).resolve().parents[1]
    / "web"
    / "src"
    / "app"
    / "telas"
    / "FichaDaEmpresa.tsx"
)
VALORES = TELA.with_name(
    "valoresDaFicha.ts"
)  # onde moram os rótulos (a tela os importa)
PAR = re.compile(r'^\s*(\w+):\s*"([^"]*)",', re.MULTILINE)


def _objeto(nome: str, arquivo: Path = TELA) -> dict[str, str]:
    """Os pares `chave: "valor"` do objeto `const NOME: Record<string, string> = {...}` da tela."""
    texto = arquivo.read_text(encoding="utf-8")
    achado = re.search(
        rf"const {nome}: Record<string, string> = \{{(.*?)\n\}};", texto, re.DOTALL
    )
    assert achado, f"{nome} não achado em {arquivo.name}"
    return dict(PAR.findall(achado.group(1)))


def test_o_mapa_da_tela_tem_todo_campo_que_a_lista_pode_trazer():
    esperado = {
        NOMES_DE_FORA[nome]: nome for nome in empresas.TABELA_DO_CAMPO_DO_CADASTRO
    }
    assert _objeto("CHAVE_DO_CAMPO_DE_FORA") == esperado


def test_todo_campo_do_mapa_tem_rotulo_na_tela():
    rotulos = _objeto("NOMES_DOS_CAMPOS", VALORES)
    sem_rotulo = [
        chave
        for chave in _objeto("CHAVE_DO_CAMPO_DE_FORA").values()
        if not rotulos.get(chave)
    ]
    assert sem_rotulo == []


def test_o_mes_do_retrato_do_cadastro_tem_o_rotulo_aprovado():
    assert (
        _objeto("NOMES_DOS_CAMPOS", VALORES)["mes_do_retrato_do_cadastro"]
        == "Mês do retrato do cadastro"
    )
