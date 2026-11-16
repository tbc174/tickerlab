"""A consulta em lote da API externa (B-32a, PR 1; cliente-norte: raio-x de carteira no lote noturno).

Um lote de N CNPJs conta N na quota do mês e 1 no limite do minuto. Riscos do plano: (4) furar a quota
com o lote (100 CNPJs contando 1, ou um lote servido pela metade) e (2) o lote virar busca por pessoa
(um CPF completado com zeros passaria por CNPJ).
"""

from typing import Annotated

import pytest
from fastapi import Body, Depends, FastAPI
from fastapi.testclient import TestClient

from src.api_externa import acesso, lote
from src.banco import chaves_da_api as cb
from src.banco.conexao import obter_engine
from src.chaves_da_api import ContextoDaChave
from tests import ajudantes_da_api_externa as aj

PETROBRAS = "33000167000101"
VALE = "33592510000154"
ROTA = "/teste/lote"


# ---------------------------------------------------------------- ler o lote


def test_lote_aceita_cnpj_formatado_e_desduplica():
    lido = lote.ler_lote(["33.000.167/0001-01", PETROBRAS, VALE])
    assert lido.validos == [PETROBRAS, VALE]
    assert lido.invalidos == []
    assert lido.pedidos == 2


def test_cnpj_com_dv_errado_e_cpf_ficam_de_fora():
    cpf_de_exemplo = (
        "88800000127"  # CPF válido de 11 dígitos: nunca vira CNPJ com zeros
    )
    lido = lote.ler_lote([PETROBRAS, "33000167000102", cpf_de_exemplo, "", 123])
    assert lido.validos == [PETROBRAS]
    assert lido.invalidos == ["33000167000102", cpf_de_exemplo, "", "123"]


def test_lote_so_com_invalidos_conta_um_pedido():
    assert lote.ler_lote(["x"]).pedidos == 1


def test_lote_vazio_e_recusado():
    with pytest.raises(lote.LoteInvalidoError):
        lote.ler_lote([])


def test_lote_acima_do_teto_e_recusado():
    with pytest.raises(lote.LoteInvalidoError):
        lote.ler_lote([PETROBRAS] * (lote.MAXIMO_DO_LOTE + 1))


def test_o_teto_conta_os_itens_enviados_nao_os_distintos():
    # 101 repetidos também é recusado: o teto protege o servidor, não a quota
    with pytest.raises(lote.LoteInvalidoError):
        lote.ler_lote([PETROBRAS] * 50 + [VALE] * 51)


# ---------------------------------------------------------------- o lote conta N


def _app_do_teste() -> FastAPI:
    """Uma rota de lote como as do PR 4 e 5: confere a quota de N antes de servir, soma N depois."""
    app = FastAPI()

    @app.post(ROTA)
    def servir(
        contexto: Annotated[ContextoDaChave, Depends(acesso.exigir_chave)],
        cnpjs: Annotated[list[object], Body(embed=True)],
    ) -> dict:
        lido = lote.ler_lote(cnpjs)
        with obter_engine().begin() as conexao:
            acesso.exigir_quota(conexao, contexto, lido.pedidos, acesso.agora())
            cb.registrar_consumo(
                conexao,
                contexto,
                conjunto=aj.CONJUNTO,
                finalidade="analise",
                linhas=len(lido.validos),
                pedidos=lido.pedidos,
                agora=acesso.agora(),
            )
        return {"servidos": len(lido.validos)}

    return app


@pytest.fixture
def cliente(banco, monkeypatch):
    monkeypatch.setattr(acesso, "agora", lambda: aj.AGORA)
    acesso.zerar_limites()
    return TestClient(_app_do_teste())


@pytest.fixture
def org_e_chave(banco):
    ator = aj.admin(banco)
    org = aj.organizacao(banco, ator)
    return org, aj.chave(banco, ator, org)


def _cnpjs(n: int) -> list[str]:
    """N CNPJs distintos com o DV certo."""
    from base.cnpj import digitos_verificadores

    return [
        f"{i:08d}0001" + digitos_verificadores(f"{i:08d}0001") for i in range(1, n + 1)
    ]


def _gastar(banco, chave, pedidos: int):
    with banco.begin() as conexao:
        contexto = cb.conferir_chave(conexao, chave.valor, agora=aj.AGORA)
        assert isinstance(contexto, ContextoDaChave)
        cb.registrar_consumo(
            conexao,
            contexto,
            conjunto=aj.CONJUNTO,
            finalidade="analise",
            linhas=0,
            pedidos=pedidos,
            agora=aj.AGORA,
        )


def _pedidos_do_mes(banco, org) -> int:
    with banco.connect() as conexao:
        return cb.consumo_do_mes(conexao, org.id, aj.HOJE).pedidos


def test_lote_de_n_conta_n_na_quota_do_mes(cliente, banco, org_e_chave):
    org, chave = org_e_chave
    resposta = cliente.post(
        ROTA, json={"cnpjs": _cnpjs(40)}, headers=aj.bearer(chave.valor)
    )
    assert resposta.status_code == 200
    assert _pedidos_do_mes(banco, org) == 40


def test_lote_que_passa_da_quota_volta_inteiro_e_nao_grava(cliente, banco, org_e_chave):
    org, chave = org_e_chave
    _gastar(banco, chave, pedidos=10_000 - 10)  # sobram 10
    resposta = cliente.post(
        ROTA, json={"cnpjs": _cnpjs(11)}, headers=aj.bearer(chave.valor)
    )
    assert resposta.status_code == 429
    assert resposta.json() == {"detail": "monthly_quota_exceeded"}
    assert _pedidos_do_mes(banco, org) == 10_000 - 10


def test_lote_que_cabe_exatamente_na_quota_passa(cliente, banco, org_e_chave):
    org, chave = org_e_chave
    _gastar(banco, chave, pedidos=10_000 - 10)
    resposta = cliente.post(
        ROTA, json={"cnpjs": _cnpjs(10)}, headers=aj.bearer(chave.valor)
    )
    assert resposta.status_code == 200
    assert _pedidos_do_mes(banco, org) == 10_000


def test_lote_conta_um_no_limite_do_minuto(cliente, org_e_chave):
    # 60 lotes de 100 num minuto: o limite é de chamadas, a quota do mês é de CNPJs
    _org, chave = org_e_chave
    cnpjs = _cnpjs(100)
    for _ in range(60):
        resposta = cliente.post(
            ROTA, json={"cnpjs": cnpjs}, headers=aj.bearer(chave.valor)
        )
        assert resposta.status_code == 200
    resposta = cliente.post(ROTA, json={"cnpjs": cnpjs}, headers=aj.bearer(chave.valor))
    assert resposta.json() == {"detail": "rate_limited"}


def test_quota_de_um_pedido_nao_aceita_zero(banco, org_e_chave):
    _org, chave = org_e_chave
    with banco.begin() as conexao:
        contexto = cb.conferir_chave(conexao, chave.valor, agora=aj.AGORA)
        assert isinstance(contexto, ContextoDaChave)
        with pytest.raises(ValueError):
            acesso.exigir_quota(conexao, contexto, 0, aj.AGORA)
        with pytest.raises(ValueError):
            cb.registrar_consumo(
                conexao,
                contexto,
                conjunto=aj.CONJUNTO,
                finalidade="analise",
                linhas=0,
                pedidos=0,
            )


def test_negado_em_lote_conta_n_negados_e_nenhum_pedido(banco, org_e_chave):
    org, chave = org_e_chave
    with banco.begin() as conexao:
        contexto = cb.conferir_chave(conexao, chave.valor, agora=aj.AGORA)
        assert isinstance(contexto, ContextoDaChave)
        cb.registrar_consumo(
            conexao,
            contexto,
            conjunto=aj.CONJUNTO,
            finalidade="analise",
            linhas=0,
            negado=True,
            pedidos=5,
            agora=aj.AGORA,
        )
        consumo = cb.consumo_do_mes(conexao, org.id, aj.HOJE)
    assert (consumo.pedidos, consumo.negados) == (0, 5)
