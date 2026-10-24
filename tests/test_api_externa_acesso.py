"""A porta de entrada da API externa pela chave da organização (N7, PR 2, tarefa 2.3; plano D3 a D10).

Um app FastAPI montado só aqui: nenhuma rota de produção nova (as rotas são da B-32). Riscos do plano,
de ponta a ponta: (2) chave revogada, vencida ou de organização suspensa entrar; (3) a chave vazar
(URL, log); (4) recusa que diz demais; (5) a chave abrir o app; (6) quota furada. E as duas travas do
D8: o contrato da organização e o portão da N3 precisam deixar.
"""

import dataclasses
import logging
from datetime import UTC, date, datetime, timedelta
from typing import Annotated

import pytest
import sqlalchemy as sa
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from src import api
from src import portao_externo as portao
from src.api_externa import acesso
from src.api_v1 import VARIAVEL_DA_CHAVE
from src.banco import chaves_da_api as cb
from src.banco.coletas import Coleta, ColetaEGuarda, Guarda
from src.banco.conexao import obter_engine
from src.banco.modelo import consumo_da_api
from src.banco.usuarios import entrar
from src.chaves_da_api import ContextoDaChave
from src.planos import limites_da_api
from src.portao_externo import (
    Canal,
    Categoria,
    Finalidade,
    LinhaDeDireito,
    Motivo,
)

AGORA = datetime(2026, 10, 22, 12, tzinfo=UTC)
HOJE = AGORA.date()
CONJUNTO = "dfp"
ROTA = "/teste/dados"


def _app_do_teste() -> FastAPI:
    """Uma rota como a da B-32 vai ser: a chave entra, o pedido conta no consumo."""
    app = FastAPI()

    @app.get(ROTA)
    def dados(
        contexto: Annotated[ContextoDaChave, Depends(acesso.exigir_chave)],
    ) -> dict:
        with obter_engine().begin() as conexao:
            cb.registrar_consumo(
                conexao,
                contexto,
                conjunto=CONJUNTO,
                finalidade="analise",
                linhas=1,
                agora=acesso.agora(),
            )
        return {
            "organizacao_id": str(contexto.organizacao_id),
            "canal": contexto.canal.value,
        }

    return app


@pytest.fixture
def relogio(monkeypatch):
    momento = {"agora": AGORA}
    monkeypatch.setattr(acesso, "agora", lambda: momento["agora"])
    return momento


@pytest.fixture
def cliente(banco, relogio):
    acesso.zerar_limites()
    return TestClient(_app_do_teste())


@pytest.fixture
def admin(banco):
    with banco.begin() as conexao:
        return entrar(conexao, "g-admin-n7", "admin-n7@exemplo.com")[0]


def _organizacao(banco, admin, nome="Alfa Gestora"):
    with banco.begin() as conexao:
        return cb.criar_organizacao(conexao, nome=nome, ator_id=admin.id, agora=AGORA)


def _chave(banco, admin, organizacao):
    with banco.begin() as conexao:
        return cb.emitir_chave(
            conexao, organizacao_id=organizacao.id, ator_id=admin.id, agora=AGORA
        )


@pytest.fixture
def alfa(banco, admin):
    return _organizacao(banco, admin)


@pytest.fixture
def chave(banco, admin, alfa):
    return _chave(banco, admin, alfa)


def _bearer(valor: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {valor}"}


# ---------------------------------------------------------------- a chave entra (D4, D6)


def test_chave_no_bearer_abre_o_contexto_da_organizacao(cliente, alfa, chave):
    resposta = cliente.get(ROTA, headers=_bearer(chave.valor))
    assert resposta.status_code == 200
    assert resposta.json() == {"organizacao_id": str(alfa.id), "canal": "api_externa"}


def test_chave_no_x_api_key_tambem_entra(cliente, alfa, chave):
    resposta = cliente.get(ROTA, headers={"X-API-Key": chave.valor})
    assert resposta.status_code == 200
    assert resposta.json()["organizacao_id"] == str(alfa.id)


@pytest.mark.parametrize("parametro", ["api_key", "chave", "q"])
def test_chave_na_url_recusada_sem_eco(cliente, chave, parametro):
    # a URL vai para o log de acesso do servidor e da Cloudflare: nem com o cabeçalho certo
    resposta = cliente.get(
        ROTA, params={parametro: chave.valor}, headers=_bearer(chave.valor)
    )
    assert resposta.status_code == 400
    assert chave.valor not in resposta.text
    assert chave.prefixo not in resposta.text


@pytest.mark.parametrize("parametro", ["api_key", "apikey", "key", "token", "chave"])
def test_parametro_com_nome_de_chave_recusado(cliente, chave, parametro):
    resposta = cliente.get(
        ROTA, params={parametro: "qualquer"}, headers=_bearer(chave.valor)
    )
    assert resposta.status_code == 400


# ---------------------------------------------------------------- recusa uniforme (D3; riscos 2 e 4)


def _recusas(banco, admin, cliente):
    """Uma resposta para cada jeito de a chave não entrar."""
    revogada_org = _organizacao(banco, admin, nome="Revogada")
    revogada = _chave(banco, admin, revogada_org)
    suspensa_org = _organizacao(banco, admin, nome="Suspensa")
    da_suspensa = _chave(banco, admin, suspensa_org)
    girada_org = _organizacao(banco, admin, nome="Girada")
    antiga = _chave(banco, admin, girada_org)
    with banco.begin() as conexao:
        cb.revogar_chave(
            conexao,
            organizacao_id=revogada_org.id,
            chave_id=revogada.chave_id,
            ator_id=admin.id,
            agora=AGORA,
        )
        cb.suspender_organizacao(
            conexao,
            organizacao_id=suspensa_org.id,
            motivo="pagamento",
            ator_id=admin.id,
            agora=AGORA,
        )
        cb.rotacionar_chave(
            conexao,
            organizacao_id=girada_org.id,
            chave_id=antiga.chave_id,
            ator_id=admin.id,
            agora=AGORA - timedelta(days=8),
        )
    segredo_trocado = antiga.valor[:-1] + ("A" if antiga.valor[-1] != "A" else "B")
    cabecalhos = {
        "sem_chave": {},
        "bearer_vazio": {"Authorization": "Bearer "},
        "outro_esquema": {"Authorization": f"Basic {revogada.valor}"},
        "formato": _bearer("tld_nada"),
        "segredo_trocado": _bearer(segredo_trocado),
        "revogada": _bearer(revogada.valor),
        "suspensa": _bearer(da_suspensa.valor),
        "vencida": _bearer(antiga.valor),
    }
    return {
        caso: cliente.get(ROTA, headers=valores) for caso, valores in cabecalhos.items()
    }, [revogada, da_suspensa, antiga]


def test_toda_recusa_da_chave_e_o_mesmo_401(banco, admin, cliente, relogio):
    respostas, _ = _recusas(banco, admin, cliente)
    formas = {
        caso: (r.status_code, r.content, dict(r.headers))
        for caso, r in respostas.items()
    }
    assert {forma[0] for forma in formas.values()} == {401}
    assert len({repr(forma) for forma in formas.values()}) == 1, formas
    assert respostas["revogada"].headers["WWW-Authenticate"] == "Bearer"


def test_recusa_nao_conta_no_consumo(banco, admin, cliente, relogio):
    _recusas(banco, admin, cliente)
    with banco.connect() as conexao:
        assert (
            conexao.execute(
                sa.select(sa.func.count()).select_from(consumo_da_api)
            ).scalar_one()
            == 0
        )


def test_chave_nunca_aparece_no_log(banco, admin, cliente, relogio, chave, caplog):
    caplog.set_level(logging.DEBUG)
    _, chaves = _recusas(banco, admin, cliente)
    cliente.get(ROTA, headers=_bearer(chave.valor))
    cliente.get(ROTA, params={"api_key": chave.valor})
    # o httpx é o cliente do teste (o lado de fora) e anota a URL que pediu: é por isso que a chave na
    # URL é recusada (D4). Aqui conta o que o servidor grava.
    do_servidor = "\n".join(
        r.getMessage() for r in caplog.records if not r.name.startswith("httpx")
    )
    assert "chave da API recusada" in do_servidor  # o log das recusas foi capturado
    for usada in [chave, *chaves]:
        # tld_<prefixo>_<segredo>: o segredo (token_urlsafe) também pode ter "_", então corta no 2º
        segredo = usada.valor.split("_", 2)[2]
        assert usada.valor not in do_servidor
        assert segredo not in do_servidor


def test_chave_nao_abre_as_rotas_do_app(banco, monkeypatch, chave):
    # D6: a v1 do app é só do cookie da sessão; a chave da organização não vale lá
    monkeypatch.setenv(VARIAVEL_DA_CHAVE, "1")
    app = api.criar_app({VARIAVEL_DA_CHAVE: "1"})
    resposta = TestClient(app).get("/api/v1/eu", headers=_bearer(chave.valor))
    assert resposta.status_code == 401


# ---------------------------------------------------------------- quotas (D7; risco 6)


def test_pedido_alem_do_limite_do_minuto_da_429(cliente, chave, relogio):
    por_minuto = limites_da_api("piloto").pedidos_por_minuto
    for _ in range(por_minuto):
        assert cliente.get(ROTA, headers=_bearer(chave.valor)).status_code == 200
    estourou = cliente.get(ROTA, headers=_bearer(chave.valor))
    assert estourou.status_code == 429
    assert int(estourou.headers["Retry-After"]) > 0
    relogio["agora"] = AGORA + timedelta(seconds=61)
    assert cliente.get(ROTA, headers=_bearer(chave.valor)).status_code == 200


def test_limite_do_minuto_e_da_organizacao_nao_da_chave(
    banco, admin, cliente, alfa, chave, monkeypatch
):
    monkeypatch.setattr(acesso, "_por_minuto", lambda plano: 2)
    acesso.zerar_limites()
    outra_da_alfa = _chave(banco, admin, alfa)
    beta = _chave(banco, admin, _organizacao(banco, admin, nome="Beta"))
    assert cliente.get(ROTA, headers=_bearer(chave.valor)).status_code == 200
    assert cliente.get(ROTA, headers=_bearer(outra_da_alfa.valor)).status_code == 200
    assert cliente.get(ROTA, headers=_bearer(chave.valor)).status_code == 429
    assert cliente.get(ROTA, headers=_bearer(outra_da_alfa.valor)).status_code == 429
    assert cliente.get(ROTA, headers=_bearer(beta.valor)).status_code == 200


def _gastar_do_mes(banco, alfa, chave, pedidos, dia=HOJE):
    with banco.begin() as conexao:
        conexao.execute(
            sa.insert(consumo_da_api).values(
                organizacao_id=alfa.id,
                chave_id=chave.chave_id,
                dia=dia,
                canal="api_externa",
                finalidade="analise",
                conjunto="outro",
                pedidos=pedidos,
            )
        )


def test_pedido_alem_da_quota_do_mes_da_429_ate_a_virada(
    banco, cliente, alfa, chave, relogio
):
    por_mes = limites_da_api("piloto").pedidos_por_mes
    _gastar_do_mes(banco, alfa, chave, por_mes - 1)
    assert cliente.get(ROTA, headers=_bearer(chave.valor)).status_code == 200
    estourou = cliente.get(ROTA, headers=_bearer(chave.valor))
    assert estourou.status_code == 429
    virada = datetime(2026, 11, 1, tzinfo=UTC)
    assert int(estourou.headers["Retry-After"]) == int((virada - AGORA).total_seconds())
    relogio["agora"] = virada
    assert cliente.get(ROTA, headers=_bearer(chave.valor)).status_code == 200


def test_quota_do_mes_nao_le_o_mes_passado(banco, cliente, alfa, chave):
    por_mes = limites_da_api("piloto").pedidos_por_mes
    _gastar_do_mes(banco, alfa, chave, por_mes, dia=date(2026, 9, 30))
    assert cliente.get(ROTA, headers=_bearer(chave.valor)).status_code == 200


def test_limite_de_linhas_por_resposta_vem_do_plano(chave, alfa):
    contexto = ContextoDaChave(alfa.id, chave.chave_id, chave.prefixo, "piloto")
    assert acesso.linhas_por_resposta(contexto) == 1_000


# ---------------------------------------------------------------- as duas travas (D8)


def _linha_do_portao(**outros) -> LinhaDeDireito:
    base = {
        "fonte": "cvm-dfp",
        "conjunto": CONJUNTO,
        "campo": "receita_liquida",
        "canal": Canal.API_EXTERNA,
        "finalidade": Finalidade.ANALISE,
        "categoria": Categoria.FATO_DE_PJ,
        "vigente_desde": date(2026, 10, 1),
        "prova": "teste",
    }
    return LinhaDeDireito(**(base | outros))  # type: ignore[arg-type]


def _portao_liberando(*linhas: LinhaDeDireito) -> portao.Regras:
    """O portão com tudo em ordem para a família `cvm`: só a linha decide."""
    respostas = ColetaEGuarda(Coleta.ABERTA, Guarda.SEM_PRAZO)
    return dataclasses.replace(
        portao.regras_vigentes(),
        linhas=linhas or (_linha_do_portao(),),
        coleta_e_guarda={"cvm": respostas},
        termos_lidos_em={"cvm": date(2026, 10, 1)},
    )


def _contexto(banco, chave) -> ContextoDaChave:
    with banco.begin() as conexao:
        contexto = cb.conferir_chave(conexao, chave.valor, agora=AGORA)
    assert isinstance(contexto, ContextoDaChave)
    return contexto


def _conceder(banco, admin, organizacao, **outros):
    valores = {"conjunto": CONJUNTO, "finalidade": "analise", "vigente_desde": HOJE}
    with banco.begin() as conexao:
        return cb.conceder_direito(
            conexao,
            organizacao_id=organizacao.id,
            ator_id=admin.id,
            agora=AGORA,
            **(valores | outros),
        )


def _autorizar(banco, contexto, regras, **outros):
    pedido = {
        "fonte": "cvm-dfp",
        "conjunto": CONJUNTO,
        "campo": "receita_liquida",
        "finalidade": "analise",
    }
    with banco.connect() as conexao:
        return acesso.autorizar(
            conexao, contexto, hoje=HOJE, regras=regras, **(pedido | outros)
        )


def test_contrato_e_portao_liberando_sai(banco, admin, alfa, chave):
    _conceder(banco, admin, alfa)
    decisao = _autorizar(banco, _contexto(banco, chave), _portao_liberando())
    assert decisao.libera
    assert decisao.motivo is Motivo.LIBERADO


def test_sem_contrato_nega_mesmo_com_o_portao_liberando(banco, admin, alfa, chave):
    decisao = _autorizar(banco, _contexto(banco, chave), _portao_liberando())
    assert not decisao.libera
    assert decisao.motivo is Motivo.SEM_CONTRATO_DA_ORGANIZACAO
    assert portao.codigo_publico(decisao) == portao.CODIGO_PUBLICO_DA_NEGACAO


def test_contrato_sem_o_portao_nega(banco, admin, alfa, chave):
    _conceder(banco, admin, alfa)
    # as regras de hoje: nenhuma linha de direito no portão, nada sai
    decisao = _autorizar(banco, _contexto(banco, chave), None)
    assert not decisao.libera
    assert decisao.motivo is Motivo.SEM_LINHA_DE_DIREITO


@pytest.mark.parametrize(
    "mudanca",
    [{"conjunto": "itr"}, {"finalidade": "credito"}],
)
def test_contrato_vale_so_para_o_proprio_conjunto_e_finalidade(
    banco, admin, alfa, chave, mudanca
):
    _conceder(banco, admin, alfa)
    linha = _linha_do_portao(
        **{
            **mudanca,
            "finalidade": Finalidade(mudanca.get("finalidade", "analise")),
        }
    )
    decisao = _autorizar(
        banco, _contexto(banco, chave), _portao_liberando(linha), **mudanca
    )
    assert decisao.motivo is Motivo.SEM_CONTRATO_DA_ORGANIZACAO


def test_direito_suspenso_nega(banco, admin, alfa, chave):
    direito = _conceder(banco, admin, alfa)
    with banco.begin() as conexao:
        cb.suspender_direito(
            conexao,
            organizacao_id=alfa.id,
            direito_id=direito.id,
            ator_id=admin.id,
            agora=AGORA,
        )
    decisao = _autorizar(banco, _contexto(banco, chave), _portao_liberando())
    assert decisao.motivo is Motivo.SEM_CONTRATO_DA_ORGANIZACAO


@pytest.mark.parametrize(
    "vigencia",
    [
        {"vigente_desde": HOJE + timedelta(days=1)},
        {
            "vigente_desde": HOJE - timedelta(days=30),
            "vigente_ate": HOJE - timedelta(days=1),
        },
    ],
)
def test_direito_fora_da_vigencia_nega(banco, admin, alfa, chave, vigencia):
    _conceder(banco, admin, alfa, **vigencia)
    decisao = _autorizar(banco, _contexto(banco, chave), _portao_liberando())
    assert decisao.motivo is Motivo.SEM_CONTRATO_DA_ORGANIZACAO


def test_finalidade_de_treino_nunca_sai(banco, admin, alfa, chave):
    _conceder(banco, admin, alfa)
    linha = _linha_do_portao(finalidade=Finalidade.TREINO)
    decisao = _autorizar(
        banco, _contexto(banco, chave), _portao_liberando(linha), finalidade="treino"
    )
    assert not decisao.libera


def test_contrato_de_outra_organizacao_nao_vale(banco, admin, alfa, chave):
    beta = _organizacao(banco, admin, nome="Beta")
    _conceder(banco, admin, beta)
    decisao = _autorizar(banco, _contexto(banco, chave), _portao_liberando())
    assert decisao.motivo is Motivo.SEM_CONTRATO_DA_ORGANIZACAO


def test_portao_recebe_sempre_o_canal_da_api_externa(
    banco, admin, alfa, chave, monkeypatch
):
    _conceder(banco, admin, alfa)
    vistos = []
    original = portao.decidir

    def espiao(pedido, hoje, regras=None):
        vistos.append(pedido)
        return original(pedido, hoje, regras)

    monkeypatch.setattr(acesso, "decidir", espiao)
    _autorizar(banco, _contexto(banco, chave), _portao_liberando())
    assert [pedido.canal for pedido in vistos] == [Canal.API_EXTERNA]
