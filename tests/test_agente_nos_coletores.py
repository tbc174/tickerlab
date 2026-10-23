"""Todo coletor que fala com site de fora se identifica com o `User-Agent` do TickerLab (ADR 0102).

Sem internet: o dublê só confere o cabeçalho que chegaria à fonte.
"""

import ast
from pathlib import Path

import pytest
import requests

from base.arquivo.agente import AGENTE
from src import rede

RAIZ = Path(__file__).resolve().parent.parent
PASTAS = ("base", "src", "scripts")
# chamadas que baixam de um site: quem precisa delas passa por `src.rede` (que põe o agente)
CHAMADAS_DE_REDE = {
    ("requests", "get"),
    ("requests", "head"),
    ("requests", "request"),
    ("requests", "Session"),
    ("httpx", "get"),
    ("urllib", "urlopen"),
    ("request", "urlopen"),
}
# arquivos que usam a rede por conta própria, e por quê
PERMITIDOS = {
    "src/rede.py": "é onde o agente é posto",
    "base/arquivo/cliente_http.py": "a sessão já leva o AGENTE no cabeçalho",
    "base/enet_coleta.py": "a sessão do Enet leva o AGENTE em cada pedido",
    "scripts/carga_leve.py": "teste de carga no site do próprio TickerLab",
    "src/api_v1/acesso.py": "chaves públicas do Google para validar o login, não é coleta",
}


class _Resposta:
    def raise_for_status(self) -> None:
        return None


def _chamadas_de_rede(arquivo: Path) -> list[str]:
    nome = arquivo.relative_to(RAIZ).as_posix()
    arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
    return [
        f"{nome}:{no.lineno} {no.value.id}.{no.attr}"
        for no in ast.walk(arvore)
        if isinstance(no, ast.Attribute)
        and isinstance(no.value, ast.Name)
        and (no.value.id, no.attr) in CHAMADAS_DE_REDE
    ]


def _chamadas_sem_agente() -> list[str]:
    achadas: list[str] = []
    for pasta in PASTAS:
        for arquivo in sorted((RAIZ / pasta).rglob("*.py")):
            if arquivo.relative_to(RAIZ).as_posix() not in PERMITIDOS:
                achadas += _chamadas_de_rede(arquivo)
    return achadas


def test_nenhum_coletor_chama_a_rede_sem_o_agente():
    assert _chamadas_sem_agente() == [], (
        "use `rede.obter` ou `rede.get_com_agente` (src/rede.py), que põem o User-Agent"
    )


def test_obter_manda_o_agente(monkeypatch: pytest.MonkeyPatch):
    recebido = {}

    def falso(url, **kwargs):
        recebido.update(kwargs)
        return _Resposta()

    monkeypatch.setattr(requests, "get", falso)
    rede.obter("https://exemplo.test/a")
    assert recebido["headers"] == {"User-Agent": AGENTE}


def test_cabecalho_explicito_vence_e_os_outros_ficam(monkeypatch: pytest.MonkeyPatch):
    recebido = {}
    monkeypatch.setattr(
        requests, "get", lambda url, **kw: recebido.update(kw) or _Resposta()
    )
    rede.obter(
        "https://exemplo.test/a", headers={"user-agent": "SEC contato", "Range": "x"}
    )
    assert recebido["headers"] == {"user-agent": "SEC contato", "Range": "x"}
    rede.obter("https://exemplo.test/a", headers={"Range": "x"})
    assert recebido["headers"] == {"Range": "x", "User-Agent": AGENTE}


def test_get_com_agente_manda_o_agente(monkeypatch: pytest.MonkeyPatch):
    recebido = {}
    monkeypatch.setattr(
        requests, "get", lambda url, **kw: recebido.update(kw) or _Resposta()
    )
    rede.get_com_agente("https://exemplo.test/a", timeout=5)
    assert recebido["headers"]["User-Agent"] == AGENTE
    assert recebido["timeout"] == 5
