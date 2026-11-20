"""O piloto (D11) na ficha, nos eventos, nos vínculos, na análise completa e no Comparar da tela do analista (linha 905).

Em produção estas tabelas ainda não têm a prontidão cheia: só a conta de uma organização com a marca de piloto,
conferida no servidor a cada pedido, vê o dado, e a resposta leva o aviso de piloto (em cada campo e no topo; na
planilha, na coluna `piloto` e na aba das fontes). Riscos que estes testes cobrem: a marca de uma organização
valer para a conta de outra (ou de nenhuma); o dado de piloto sair sem o aviso; um campo sem registro de piloto
sair junto com os que têm. A busca tem os testes dela em `test_api_v1_analista_busca.py`; os leitores, nos
arquivos de cada um. Tudo com a base de mentira dos outros testes: nenhuma empresa nem pessoa de verdade.
"""

import dataclasses
import io
from collections.abc import Callable, Iterator
from datetime import timedelta
from pathlib import Path
from typing import NamedTuple

import openpyxl
import pytest
from fastapi.testclient import TestClient

from base import prontidao
from base.porta import Porta
from base.prontidao import AVISO_DE_PILOTO, Prontidao, ProntidaoDePiloto, Prova
from src import portao_externo as portao
from src.analista import analise, comparacao, eventos, leitura, vinculos
from src.api_externa import piloto as piloto_
from src.api_externa import rotas as rotas_da_api_externa
from src.api_v1 import analista
from src.banco import chaves_da_api as cb
from src.banco import membros_da_organizacao as mb
from src.banco.usuarios import entrar, mudar_plano
from src.conformidade import registrar_aceite
from tests import test_analista_comparacao as comparacao_de_mentira
from tests import test_api_externa_empresas as empresas_de_mentira
from tests import test_api_externa_por_cnpj_eventos as eventos_de_mentira
from tests import test_api_externa_por_cnpj_ficha as ficha_de_mentira
from tests import test_api_externa_por_cnpj_vinculos as vinculos_de_mentira
from tests import test_api_v1_rotas as rotas
from tests.ajudantes_da_api import da_sessao

chave = rotas.chave  # as fixtures da conta logada, as mesmas dos outros testes da API
cliente = rotas.cliente
HOJE = (
    comparacao_de_mentira.HOJE
)  # 10/11/2026, o mesmo dia de todas as bases de mentira
EMPRESA = empresas_de_mentira.EMPRESA
SIMPLES = "cnpj_simples_historico"


class Tela(NamedTuple):
    """Uma das quatro partes da tela: a rota, o pedido, a base de mentira, as tabelas que ela lê e a leitura."""

    rota: str
    pedido: dict
    gravar: Callable[[Path], Path]
    tabelas: tuple[str, ...]
    ler: Callable[..., leitura.Resposta]


FICHA = Tela(
    "/api/v1/analista/ficha",
    {"cnpj": EMPRESA},
    lambda pasta: ficha_de_mentira._base(pasta, ficha_de_mentira._rotulos()),
    comparacao_de_mentira.TABELAS_DA_FICHA,
    lambda porta, **kw: leitura.ficha(porta, EMPRESA, **kw),
)
EVENTOS = Tela(
    "/api/v1/analista/ficha/eventos",
    {"cnpj": eventos_de_mentira.ALFA},
    lambda pasta: eventos_de_mentira.gravar_base(pasta / "base"),
    ("eventos", "trocas_de_auditor"),
    lambda porta, **kw: eventos.eventos(porta, eventos_de_mentira.ALFA, **kw),
)
VINCULOS = Tela(
    "/api/v1/analista/ficha/vinculos",
    {"cnpj": vinculos_de_mentira.ALFA},
    lambda pasta: vinculos_de_mentira.gravar_base(pasta / "base"),
    ("ligacoes", "entidades", "identificadores", "cnpj_empresas_pj"),
    lambda porta, **kw: vinculos.vinculos(porta, vinculos_de_mentira.ALFA, **kw),
)
COMPARAR = Tela(
    "/api/v1/analista/comparar",
    {"cnpjs": [EMPRESA, empresas_de_mentira.MEI]},
    comparacao_de_mentira.base_de_teste,
    (*comparacao_de_mentira.TABELAS_DA_FICHA, *comparacao_de_mentira.TABELAS_DA_BUSCA),
    lambda porta, **kw: comparacao.comparar(
        porta, [EMPRESA, empresas_de_mentira.MEI], **kw
    ),
)
# a análise completa (19/11/2026) lê a ficha pela mesma montagem da API: com só as tabelas da ficha no registro de
# piloto, abre o cadastro e os blocos que dependem só dele
ANALISE = Tela(
    "/api/v1/analista/ficha/analise",
    {"cnpj": EMPRESA},
    FICHA.gravar,
    comparacao_de_mentira.TABELAS_DA_FICHA,
    lambda porta, **kw: analise.analise(porta, EMPRESA, **kw),
)
TELAS = pytest.mark.parametrize(
    "tela",
    [FICHA, EVENTOS, VINCULOS, COMPARAR, ANALISE],
    ids=lambda t: t.rota.rsplit("/", 1)[-1],
)
PLANILHAS = pytest.mark.parametrize(
    "tela", [FICHA, COMPARAR], ids=lambda t: t.rota.rsplit("/", 1)[-1]
)


def _so_de_piloto(tabelas, *, pessoa_decidida: bool = True) -> portao.Regras:
    """Como a produção hoje: nenhuma tabela com a prontidão cheia; as pedidas só no registro de piloto.

    `pessoa_decidida`: as tabelas pedidas com a marca de pessoa decidida (o piloto exige; a situação cadastral e
    o Simples ainda esperam a linha 740 em produção)."""
    prova = Prova(HOJE, "conferida no teste", "teste")
    versoes = prontidao.versoes_maiores()
    vigentes = portao.regras_vigentes()
    return dataclasses.replace(
        vigentes,
        prontidao={},
        prontidao_de_piloto={
            t: ProntidaoDePiloto(versoes[t], prova, prova) for t in tabelas
        },
        pessoa_decidida=vigentes.pessoa_decidida
        | (frozenset(tabelas) if pessoa_decidida else frozenset()),
    )


def _prontas(tabelas) -> portao.Regras:
    """As tabelas pedidas com a prontidão cheia (o dado sai para todas as contas, sem aviso)."""
    prova = Prova(HOJE, "conferida no teste", "teste")
    versoes = prontidao.versoes_maiores()
    return dataclasses.replace(
        portao.regras_vigentes(),
        prontidao={t: Prontidao(versoes[t], prova, prova, prova) for t in tabelas},
    )


def _usar(monkeypatch, pasta: Path, regras: portao.Regras) -> None:
    monkeypatch.setattr(
        rotas_da_api_externa, "abrir_porta", lambda banco_: Porta(pasta, banco_)
    )
    monkeypatch.setattr(rotas_da_api_externa, "regras_da_api", lambda: regras)


@pytest.fixture(autouse=True)
def conta_no_pro(cliente, banco, monkeypatch):
    with banco.begin() as conexao:
        mudar_plano(conexao, rotas._id_da_ana_no(banco), "pro")
    monkeypatch.setattr(analista, "hoje", lambda: HOJE)


@pytest.fixture
def da_bia(cliente, banco):
    """Outra conta logada no Pro, com os termos aceitos (a Bia)."""
    with banco.begin() as conexao:
        bia = entrar(conexao, "g-bia-piloto", "bia-piloto@exemplo.com")[0]
        registrar_aceite(conexao, bia.id)
        mudar_plano(conexao, bia.id, "pro")
    return bia, TestClient(cliente.app, headers=da_sessao(banco, bia))


def _organizacao_com(banco, nome: str, conta_id: int, *, marca: bool = True):
    """Uma organização com a conta de membro e, se `marca`, a marca de piloto vigente desde ontem."""
    with banco.begin() as conexao:
        admin = entrar(conexao, f"g-admin-{nome}", f"admin-{len(nome)}@exemplo.com")[0]
        organizacao = cb.criar_organizacao(conexao, nome=nome, ator_id=admin.id)
        mb.vincular_membro(
            conexao,
            organizacao_id=organizacao.id,
            usuario_id=conta_id,
            ator_id=admin.id,
        )
        if marca:
            cb.conceder_direito(
                conexao,
                organizacao_id=organizacao.id,
                conjunto=cb.CONJUNTO_DO_PILOTO,
                finalidade=mb.FINALIDADE_DA_TELA,
                vigente_desde=HOJE - timedelta(days=1),
                vigente_ate=None,
                ator_id=admin.id,
            )
    return organizacao


def _da_ana(banco) -> int:
    return rotas._id_da_ana_no(banco)


def _envelopes(dado) -> Iterator[dict]:
    """Todo bloco com fonte (valor, fonte e dia em que ficou público), em qualquer nível do corpo. O marco da linha do
    tempo da análise (dia, fonte e dia público, sem `valor`) é índice de um campo, não campo: fica sob o aviso do
    topo, como na rota `/analysis` da API (`piloto.marcar`)."""
    if isinstance(dado, dict):
        if {"valor", "fonte", "publico_em"} <= dado.keys():
            yield dado
        for valor in dado.values():
            yield from _envelopes(valor)
    elif isinstance(dado, list):
        for item in dado:
            yield from _envelopes(item)


# ---------------------------------------------------------------- a leitura (src/analista)


@TELAS
def test_conta_do_piloto_le_com_o_aviso_em_todo_campo_e_no_topo(tmp_path, tela):
    with Porta(tela.gravar(tmp_path)) as porta:
        resposta = tela.ler(
            porta, hoje=HOJE, regras=_so_de_piloto(tela.tabelas), piloto=True
        )
    assert resposta.estado == leitura.PRONTA
    assert (
        resposta.corpo[piloto_.AVISO] == AVISO_DE_PILOTO
    )  # D11.3: sem o aviso é defeito
    envelopes = list(_envelopes(resposta.corpo))
    assert envelopes
    for envelope in envelopes:
        assert envelope[piloto_.MARCA] is True
        assert envelope[piloto_.AVISO] == AVISO_DE_PILOTO


@TELAS
def test_so_com_o_registro_de_piloto_a_conta_comum_continua_sem_o_dado(tmp_path, tela):
    with Porta(tela.gravar(tmp_path)) as porta:
        resposta = tela.ler(porta, hoje=HOJE, regras=_so_de_piloto(tela.tabelas))
    assert resposta.estado == leitura.NAO_LIBERADA
    assert resposta.corpo is None


@TELAS
def test_prontidao_cheia_sai_sem_o_aviso_mesmo_para_a_conta_do_piloto(tmp_path, tela):
    with Porta(tela.gravar(tmp_path)) as porta:
        resposta = tela.ler(
            porta, hoje=HOJE, regras=_prontas(tela.tabelas), piloto=True
        )
    assert resposta.estado == leitura.PRONTA
    assert piloto_.AVISO not in resposta.corpo
    assert all(piloto_.MARCA not in e for e in _envelopes(resposta.corpo))


def test_campo_sem_registro_de_piloto_continua_barrado_na_ficha(tmp_path):
    tabelas = tuple(t for t in FICHA.tabelas if t != SIMPLES)
    with Porta(FICHA.gravar(tmp_path)) as porta:
        resposta = FICHA.ler(
            porta, hoje=HOJE, regras=_so_de_piloto(tabelas), piloto=True
        )
    assert resposta.estado == leitura.PRONTA and resposta.corpo is not None
    ficha = resposta.corpo  # o corpo da leitura é a ficha (a rota o põe em `ficha`)
    assert "simples_nacional" in ficha["campos_do_cadastro_nao_disponiveis"]
    assert "optante_simples" not in ficha["cadastro_na_receita"]
    assert resposta.corpo[piloto_.AVISO] == AVISO_DE_PILOTO


def test_conta_do_piloto_sem_a_ancora_no_registro_continua_sem_a_ficha(tmp_path):
    # a situação cadastral é a âncora: sem ela no registro, nem a ficha nem o Comparar saem (linha 905)
    sem_ancora = tuple(t for t in COMPARAR.tabelas if t != "cnpj_situacao_cadastral")
    with Porta(COMPARAR.gravar(tmp_path)) as porta:
        ficha = FICHA.ler(
            porta, hoje=HOJE, regras=_so_de_piloto(sem_ancora), piloto=True
        )
        lado_a_lado = COMPARAR.ler(
            porta, hoje=HOJE, regras=_so_de_piloto(sem_ancora), piloto=True
        )
    assert ficha.estado == leitura.NAO_LIBERADA
    assert lado_a_lado.estado == leitura.NAO_LIBERADA


def test_ancora_sem_a_marca_de_pessoa_decidida_continua_barrada_no_piloto(tmp_path):
    # o piloto não pula a marca de pessoa: é o estado da produção até a linha 740 (situação cadastral)
    regras = _so_de_piloto(FICHA.tabelas, pessoa_decidida=False)
    if "cnpj_situacao_cadastral" in portao.regras_vigentes().pessoa_decidida:
        pytest.skip("a marca de pessoa da situação cadastral já foi decidida")
    with Porta(FICHA.gravar(tmp_path)) as porta:
        resposta = FICHA.ler(porta, hoje=HOJE, regras=regras, piloto=True)
    assert resposta.estado == leitura.NAO_LIBERADA


# ---------------------------------------------------------------- a rota (duas organizações e a conta sem)


@TELAS
def test_membro_da_organizacao_do_piloto_ve_com_o_aviso(
    tmp_path, monkeypatch, cliente, banco, tela
):
    _usar(monkeypatch, tela.gravar(tmp_path), _so_de_piloto(tela.tabelas))
    _organizacao_com(banco, "Casa Exemplo", _da_ana(banco))
    resposta = cliente.post(tela.rota, json=tela.pedido)
    assert resposta.status_code == 200, resposta.text
    dados = resposta.json()
    assert dados["estado"] == leitura.PRONTA
    assert dados["aviso_de_piloto"] == AVISO_DE_PILOTO


@TELAS
def test_conta_sem_organizacao_ou_de_organizacao_sem_a_marca_continua_sem_o_dado(
    tmp_path, monkeypatch, cliente, banco, tela
):
    _usar(monkeypatch, tela.gravar(tmp_path), _so_de_piloto(tela.tabelas))
    sem_organizacao = cliente.post(tela.rota, json=tela.pedido).json()
    assert sem_organizacao["estado"] == leitura.NAO_LIBERADA
    assert sem_organizacao["aviso_de_piloto"] is None
    _organizacao_com(banco, "Casa sem marca", _da_ana(banco), marca=False)
    sem_marca = cliente.post(tela.rota, json=tela.pedido).json()
    assert sem_marca["estado"] == leitura.NAO_LIBERADA
    assert sem_marca["aviso_de_piloto"] is None


@TELAS
def test_a_marca_de_uma_organizacao_nao_vale_para_a_conta_de_outra(
    tmp_path, monkeypatch, cliente, banco, da_bia, tela
):
    bia, cliente_da_bia = da_bia
    _usar(monkeypatch, tela.gravar(tmp_path), _so_de_piloto(tela.tabelas))
    _organizacao_com(banco, "Casa Exemplo", _da_ana(banco))
    _organizacao_com(banco, "Outra Casa", bia.id, marca=False)
    assert cliente.post(tela.rota, json=tela.pedido).json()["estado"] == leitura.PRONTA
    da_outra = cliente_da_bia.post(tela.rota, json=tela.pedido).json()
    assert da_outra["estado"] == leitura.NAO_LIBERADA
    assert da_outra["aviso_de_piloto"] is None


@TELAS
def test_prontidao_cheia_responde_sem_aviso_de_piloto(
    tmp_path, monkeypatch, cliente, banco, tela
):
    _usar(monkeypatch, tela.gravar(tmp_path), _prontas(tela.tabelas))
    _organizacao_com(banco, "Casa Exemplo", _da_ana(banco))
    dados = cliente.post(tela.rota, json=tela.pedido).json()
    assert dados["estado"] == leitura.PRONTA and dados["aviso_de_piloto"] is None


@PLANILHAS
def test_planilha_do_piloto_leva_o_aviso_nos_campos_e_nas_fontes(
    tmp_path, monkeypatch, cliente, banco, tela
):
    _usar(monkeypatch, tela.gravar(tmp_path), _so_de_piloto(tela.tabelas))
    _organizacao_com(banco, "Casa Exemplo", _da_ana(banco))
    resposta = cliente.post(f"{tela.rota}/planilha", json=tela.pedido)
    assert resposta.status_code == 200, resposta.text
    pasta = openpyxl.load_workbook(io.BytesIO(resposta.content))
    assert ("aviso de piloto", AVISO_DE_PILOTO, None) in list(pasta["fontes"].values)
    com_a_coluna = [aba for aba in pasta.worksheets if "piloto" in next(aba.values, ())]
    assert com_a_coluna  # a coluna `piloto`, com a frase, em alguma aba de dados
    for aba in com_a_coluna:
        linhas = list(aba.values)
        coluna = linhas[0].index("piloto")
        assert AVISO_DE_PILOTO in [linha[coluna] for linha in linhas[1:]]


@PLANILHAS
def test_planilha_de_quem_nao_e_do_piloto_nao_sai(
    tmp_path, monkeypatch, cliente, banco, da_bia, tela
):
    bia, cliente_da_bia = da_bia
    _usar(monkeypatch, tela.gravar(tmp_path), _so_de_piloto(tela.tabelas))
    _organizacao_com(banco, "Outra Casa", bia.id, marca=False)
    assert cliente.post(f"{tela.rota}/planilha", json=tela.pedido).status_code == 404
    assert (
        cliente_da_bia.post(f"{tela.rota}/planilha", json=tela.pedido).status_code
        == 404
    )
