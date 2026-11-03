"""Ajudantes dos testes das rotas da API externa (B-32a): organizações, chaves e o portão aberto.

Cada teste monta o app de verdade (`src.api.criar_app`) com a API externa ligada e um banco SQLite novo
(fixture `banco` do `conftest.py`); a hora do pedido é fixa (`acesso.agora`).
"""

import dataclasses
from datetime import UTC, date, datetime

from fastapi.testclient import TestClient

from src import api
from src import portao_externo as portao
from src.api_externa import VARIAVEL_DA_CHAVE, acesso
from src.banco import chaves_da_api as cb
from src.banco.coletas import Coleta, ColetaEGuarda, Guarda
from src.banco.usuarios import entrar
from src.portao_externo import Canal, Categoria, Finalidade, LinhaDeDireito

AGORA = datetime(2026, 10, 22, 12, tzinfo=UTC)
HOJE = AGORA.date()
CONJUNTO = "dfp"


def cliente_da_api(monkeypatch, momento: datetime = AGORA) -> TestClient:
    """O app de verdade, com a API externa ligada e o relógio parado em `momento`."""
    monkeypatch.setattr(acesso, "agora", lambda: momento)
    acesso.zerar_limites()
    return TestClient(api.criar_app({VARIAVEL_DA_CHAVE: "1"}))


def admin(banco):
    with banco.begin() as conexao:
        return entrar(conexao, "g-admin-b32a", "admin-b32a@exemplo.com")[0]


def organizacao(banco, ator, nome: str = "Alfa Gestora"):
    with banco.begin() as conexao:
        return cb.criar_organizacao(conexao, nome=nome, ator_id=ator.id, agora=AGORA)


def chave(banco, ator, org):
    with banco.begin() as conexao:
        return cb.emitir_chave(
            conexao, organizacao_id=org.id, ator_id=ator.id, agora=AGORA
        )


def contrato(banco, ator, org, conjunto: str = CONJUNTO, finalidade: str = "analise"):
    with banco.begin() as conexao:
        return cb.conceder_direito(
            conexao,
            organizacao_id=org.id,
            conjunto=conjunto,
            finalidade=finalidade,
            vigente_desde=date(2026, 10, 1),
            ator_id=ator.id,
            agora=AGORA,
        )


def bearer(valor: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {valor}"}


def linha_do_portao(**outros) -> LinhaDeDireito:
    base = {
        "fonte": "cvm-dfp",
        "conjunto": CONJUNTO,
        "campo": "valor",
        "canal": Canal.API_EXTERNA,
        "finalidade": Finalidade.ANALISE,
        "categoria": Categoria.FATO_DE_PJ,
        "vigente_desde": date(2026, 10, 1),
        "prova": "teste",
    }
    return LinhaDeDireito(**(base | outros))  # type: ignore[arg-type]


def portao_liberando(*linhas: LinhaDeDireito) -> portao.Regras:
    """O portão com tudo em ordem para a família `cvm`: só as linhas decidem."""
    respostas = ColetaEGuarda(Coleta.ABERTA, Guarda.SEM_PRAZO)
    return dataclasses.replace(
        portao.regras_vigentes(),
        linhas=linhas or (linha_do_portao(),),
        coleta_e_guarda={"cvm": respostas},
        termos_lidos_em={"cvm": date(2026, 10, 1)},
    )


def chaves_de(resposta: object) -> set[str]:
    """Todas as chaves de um JSON, em qualquer profundidade."""
    if isinstance(resposta, dict):
        return set(resposta) | {
            k for valor in resposta.values() for k in chaves_de(valor)
        }
    if isinstance(resposta, list):
        return {k for item in resposta for k in chaves_de(item)}
    return set()
