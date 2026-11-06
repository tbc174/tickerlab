"""A lista de onde o app lê o preço do Yahoo fica completa (ADR 0008, Emenda 3, item 4; linha 413,
Y2, "pode" do Tiago em 25/10/2026): todo módulo que chega ao Yahoo está em `CAMINHOS_DO_YAHOO`,
com o substituto, e a lista não guarda módulo que não chega mais. Sem internet: só lê o código."""

import ast
from pathlib import Path

from src.banco import coletas

RAIZ = Path(__file__).resolve().parent.parent
# o `trader/` roda só no PC, fora do app e da imagem Docker (regras em trader/AGENTS.md)
PASTAS = ("src", "telas", "scripts", "base")
# as portas do preço: quem importa uma destas funções lê a série do Yahoo
PORTAS: dict[str, set[str]] = {
    "src.dados": {"baixar_dados", "baixar_historico_completo"},
    "telas.comum": {
        "carregar_contexto",
        "carregar_dados",
        "carregar_dados_de",
        "carregar_dados_na_moeda",
    },
    "src.api_v1.contexto": {"carregar_dados"},
}
# módulos importados inteiros que são portas (`from src import dados`)
PORTAS_INTEIRAS = {("src", "dados"), ("src.api_v1", "contexto")}


def _chega_ao_yahoo(arvore: ast.AST) -> bool:
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            if any(a.name.split(".")[0] == "yfinance" for a in no.names):
                return True
        elif isinstance(no, ast.ImportFrom) and no.module:
            if no.module.split(".")[0] == "yfinance":
                return True
            if {a.name for a in no.names} & PORTAS.get(no.module, set()):
                return True
            if any((no.module, a.name) in PORTAS_INTEIRAS for a in no.names):
                return True
    return False


def _modulos_que_chegam_ao_yahoo() -> set[str]:
    arquivos = [RAIZ / "app.py", *(p for d in PASTAS for p in (RAIZ / d).rglob("*.py"))]
    return {
        arquivo.relative_to(RAIZ).as_posix()
        for arquivo in arquivos
        if _chega_ao_yahoo(ast.parse(arquivo.read_text(encoding="utf-8")))
    }


def _registrados() -> list[str]:
    return [m for caminho in coletas.CAMINHOS_DO_YAHOO for m in caminho.modulos]


def test_todo_modulo_que_le_o_yahoo_esta_na_lista():
    faltam = _modulos_que_chegam_ao_yahoo() - set(_registrados())
    assert not faltam, f"registre em coletas.CAMINHOS_DO_YAHOO: {sorted(faltam)}"


def test_a_lista_nao_guarda_modulo_que_nao_le_mais_o_yahoo():
    sobram = set(_registrados()) - _modulos_que_chegam_ao_yahoo()
    assert not sobram, f"tire de coletas.CAMINHOS_DO_YAHOO: {sorted(sobram)}"


def test_cada_caminho_diz_onde_e_o_substituto_sem_repetir_modulo():
    registrados = _registrados()
    assert len(registrados) == len(set(registrados))
    for caminho in coletas.CAMINHOS_DO_YAHOO:
        assert caminho.modulos and caminho.onde and caminho.substituto, caminho


def test_o_uso_do_yahoo_na_emenda_3_aponta_para_a_lista():
    uso = coletas.uso_sem_cobranca("yahoo")
    assert uso is not None and "CAMINHOS_DO_YAHOO" in uso.onde
