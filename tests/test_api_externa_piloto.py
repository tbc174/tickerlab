"""A prontidão de piloto pela rota (ADR 0108, Emenda 2, D11): a marca por organização e o aviso em cada bloco.

Base de mentira das demonstrações (a mesma de `test_api_externa_demonstracoes.py`), sem internet; o CNPJ é de
ninguém. A tabela das demonstrações fica **sem** a prontidão cheia e com o registro de piloto em dia: só a
organização com a marca (a linha de contrato `prontidao_de_piloto`) a recebe, e cada bloco leva a marca e a frase.
"""

import dataclasses
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from base import prontidao
from base.porta import Porta
from base.prontidao import AVISO_DE_PILOTO, Prontidao, ProntidaoDePiloto, Prova
from src import portao_externo as portao
from src.api_externa import piloto, rotas
from src.banco import chaves_da_api as cb
from src.portao_externo import Decisao, Motivo
from tests import ajudantes_da_api_externa as aj
from tests.test_api_externa_demonstracoes import AGORA, ROTA, _base

TABELA = "demonstracoes_como_era"
SO_DO_PILOTO = "so_do_piloto"  # tabela de mentira de onde sai só o `valor` no teste da resposta misturada
PROVA = Prova(AGORA.date(), "qualidade-no-teste")
NOME_DE_FORA = {"piloto": "pilot", "aviso_de_piloto": "pilot_notice"}


@pytest.fixture
def pasta(tmp_path, monkeypatch):
    base = tmp_path / "base"
    arquivo = base / "demonstracoes" / "2025.parquet"
    arquivo.parent.mkdir(parents=True)
    _base().to_parquet(arquivo, index=False)
    monkeypatch.setattr(rotas, "abrir_porta", lambda banco_: Porta(base, banco_))
    return base


def _regras(
    piloto_de: tuple[str, ...] = (TABELA,),
    prontas: tuple[str, ...] = (),
    linhas: tuple[portao.LinhaDeDireito, ...] | None = None,
    **outros: object,
) -> portao.Regras:
    """As regras de verdade, com as tabelas `prontas` na prontidão cheia e as `piloto_de` no registro de piloto."""
    versoes = {
        **prontidao.versoes_maiores(),
        SO_DO_PILOTO: 1,
    }
    cheia = {
        tabela: Prontidao(
            versoes[tabela], PROVA._replace(independencia="teste"), PROVA, PROVA
        )
        for tabela in prontas
    }
    de_piloto = {
        tabela: ProntidaoDePiloto(versoes[tabela], PROVA, PROVA) for tabela in piloto_de
    }
    regras = dataclasses.replace(
        portao.regras_vigentes(),
        prontidao=cheia,
        prontidao_de_piloto=de_piloto,
        versoes_maiores=versoes,
        # a marca de pessoa das demonstrações é da fila 789; aqui o teste a dá, e outro teste a tira
        pessoa_decidida=frozenset({TABELA, SO_DO_PILOTO}),
    )
    if linhas is not None:
        regras = dataclasses.replace(regras, linhas=linhas)
    return dataclasses.replace(regras, **outros)


def _marca_de_piloto(banco, ator, org, **outros):
    with banco.begin() as conexao:
        return cb.conceder_direito(
            conexao,
            organizacao_id=org.id,
            conjunto=cb.CONJUNTO_DO_PILOTO,
            finalidade="analise",
            vigente_desde=outros.get("vigente_desde", date(2026, 11, 1)),
            ator_id=ator.id,
            agora=AGORA,
        )


@pytest.fixture
def duas(banco, monkeypatch, pasta):
    """Duas organizações com o contrato de `financials`; só a primeira tem a marca de piloto."""
    ator = aj.admin(banco)
    do_piloto = aj.organizacao(banco, ator, "Organização do piloto")
    comum = aj.organizacao(banco, ator, "Organização comum")
    for org in (do_piloto, comum):
        aj.contrato(banco, ator, org, conjunto="financials")
    _marca_de_piloto(banco, ator, do_piloto)
    monkeypatch.setattr(rotas, "regras_da_api", _regras)
    cliente = aj.cliente_da_api(monkeypatch, AGORA)
    chaves = {
        "piloto": aj.chave(banco, ator, do_piloto).valor,
        "comum": aj.chave(banco, ator, comum).valor,
    }
    return cliente, chaves, ator, do_piloto


def _get(cliente, chave: str):
    return cliente.get(ROTA, headers=aj.bearer(chave))


def _envelopes(corpo: object, nome: str | None = None):
    """(nome, envelope) de todo bloco com valor, fonte e data, em qualquer profundidade."""
    if isinstance(corpo, dict):
        if {"value", "source", "published_at"} <= corpo.keys():
            yield nome, corpo
            yield from _envelopes(corpo["value"])
            return
        for chave, valor in corpo.items():
            yield from _envelopes(valor, chave)
    elif isinstance(corpo, list):
        for item in corpo:
            yield from _envelopes(item, nome)


def _sem_aviso(corpo: object) -> list[str]:
    return [
        str(nome)
        for nome, envelope in _envelopes(corpo)
        if envelope.get("pilot") is not True
        or envelope.get("pilot_notice") != AVISO_DE_PILOTO
    ]


# ---------------------------------------------------------------- duas organizações, a mesma tabela


def test_so_a_organizacao_do_piloto_recebe_a_tabela_sem_prontidao_cheia(duas) -> None:
    cliente, chaves, _ator, _org = duas
    do_piloto, comum = _get(cliente, chaves["piloto"]), _get(cliente, chaves["comum"])
    assert do_piloto.status_code == 200
    assert comum.status_code == 404
    assert comum.json() == {"detail": "not_available"}


def test_todo_bloco_de_piloto_leva_a_marca_e_a_frase(duas) -> None:
    """Bloco de piloto sem aviso é defeito P1 (D11.3)."""
    cliente, chaves, _ator, _org = duas
    corpo = _get(cliente, chaves["piloto"]).json()
    assert list(_envelopes(corpo))
    assert _sem_aviso(corpo) == []
    assert corpo["pilot_notice"] == AVISO_DE_PILOTO


def test_a_frase_sai_ao_lado_da_fonte_e_da_data(duas) -> None:
    cliente, chaves, _ator, _org = duas
    corpo = _get(cliente, chaves["piloto"]).json()
    _nome, envelope = next(_envelopes(corpo))
    assert {
        "value",
        "source",
        "published_at",
        "observed_at",
        "pilot",
        "pilot_notice",
    } <= envelope.keys()
    assert envelope["source"].startswith("cvm-hist-")


def test_marca_suspensa_desliga_o_piloto_na_hora(duas, banco) -> None:
    cliente, chaves, ator, org = duas
    with banco.begin() as conexao:
        (marca,) = [
            d
            for d in cb.direitos_vigentes(conexao, org.id, AGORA.date())
            if d.conjunto == cb.CONJUNTO_DO_PILOTO
        ]
        cb.suspender_direito(
            conexao,
            organizacao_id=org.id,
            direito_id=marca.id,
            ator_id=ator.id,
            agora=AGORA,
        )
    assert _get(cliente, chaves["piloto"]).status_code == 404


def test_marca_que_ainda_nao_vale_nao_libera(banco, monkeypatch, pasta) -> None:
    ator = aj.admin(banco)
    org = aj.organizacao(banco, ator)
    aj.contrato(banco, ator, org, conjunto="financials")
    _marca_de_piloto(banco, ator, org, vigente_desde=AGORA.date() + timedelta(days=1))
    monkeypatch.setattr(rotas, "regras_da_api", _regras)
    cliente = aj.cliente_da_api(monkeypatch, AGORA)
    assert _get(cliente, aj.chave(banco, ator, org).valor).status_code == 404


def test_marca_sem_o_contrato_do_conjunto_nao_libera(banco, monkeypatch, pasta) -> None:
    """A marca não é contrato: sem a linha de `financials`, a organização do piloto não recebe nada."""
    ator = aj.admin(banco)
    org = aj.organizacao(banco, ator)
    _marca_de_piloto(banco, ator, org)
    monkeypatch.setattr(rotas, "regras_da_api", _regras)
    cliente = aj.cliente_da_api(monkeypatch, AGORA)
    assert _get(cliente, aj.chave(banco, ator, org).valor).status_code == 404


def test_pedido_sem_chave_nao_chega_ao_piloto(duas) -> None:
    cliente, _chaves, _ator, _org = duas
    assert cliente.get(ROTA).status_code == 401


# ---------------------------------------------------------------- o que nega mesmo para o piloto


def test_prova_7_vencida_nega_para_o_piloto(duas, monkeypatch) -> None:
    cliente, chaves, _ator, _org = duas
    velha = PROVA._replace(
        data=AGORA.date() - prontidao.PRAZO_DA_PROVA - timedelta(days=1)
    )
    versao = prontidao.versoes_maiores()[TABELA]
    monkeypatch.setattr(
        rotas,
        "regras_da_api",
        lambda: _regras(
            prontidao_de_piloto={TABELA: ProntidaoDePiloto(versao, velha, PROVA)}
        ),
    )
    assert _get(cliente, chaves["piloto"]).status_code == 404


def test_versao_maior_diferente_nega_para_o_piloto(duas, monkeypatch) -> None:
    cliente, chaves, _ator, _org = duas
    versao = prontidao.versoes_maiores()[TABELA]
    monkeypatch.setattr(
        rotas,
        "regras_da_api",
        lambda: _regras(
            prontidao_de_piloto={TABELA: ProntidaoDePiloto(versao + 1, PROVA, PROVA)}
        ),
    )
    assert _get(cliente, chaves["piloto"]).status_code == 404


def test_tabela_sem_a_marca_de_pessoa_decidida_nunca_sai(duas, monkeypatch) -> None:
    cliente, chaves, _ator, _org = duas
    monkeypatch.setattr(
        rotas, "regras_da_api", lambda: _regras(pessoa_decidida=frozenset())
    )
    assert _get(cliente, chaves["piloto"]).status_code == 404


def test_com_a_marca_de_pessoa_do_dicionario_as_demonstracoes_nao_saem_hoje(
    duas, monkeypatch
) -> None:
    """As demonstrações ainda estão no inventário sem a marca (fila 789): com a regra de verdade, nem o piloto."""
    cliente, chaves, _ator, _org = duas
    monkeypatch.setattr(
        rotas,
        "regras_da_api",
        lambda: _regras(pessoa_decidida=prontidao.tabelas_com_pessoa_decidida()),
    )
    assert TABELA not in prontidao.tabelas_com_pessoa_decidida()
    assert _get(cliente, chaves["piloto"]).status_code == 404


# ---------------------------------------------------------------- um campo pronto e outro só de piloto


def _linhas_misturadas() -> tuple[portao.LinhaDeDireito, ...]:
    """As linhas de verdade de `financials`, com o `valor` saindo de uma tabela que só tem o piloto."""
    return tuple(
        linha._replace(tabelas=(SO_DO_PILOTO,))
        if linha.conjunto == "financials" and linha.campo == "valor"
        else linha
        for linha in portao.DIREITOS_DA_API_EXTERNA
    )


def test_resposta_com_campo_pronto_e_campo_de_piloto_marca_todos(
    duas, monkeypatch
) -> None:
    """Com um campo de piloto na resposta, o campo pronto também leva a marca (D11.3, leitura mais estreita)."""
    cliente, chaves, _ator, _org = duas
    monkeypatch.setattr(
        rotas,
        "regras_da_api",
        lambda: _regras(
            piloto_de=(SO_DO_PILOTO,), prontas=(TABELA,), linhas=_linhas_misturadas()
        ),
    )
    do_piloto = _get(cliente, chaves["piloto"]).json()
    comum = _get(cliente, chaves["comum"]).json()

    for linha in do_piloto["rows"]:
        assert linha["value"]["pilot"] is True
        assert linha["value"]["pilot_notice"] == AVISO_DE_PILOTO
        prontos = [envelope for nome, envelope in linha.items() if nome != "value"]
        assert prontos
        assert all(
            envelope["pilot"] is True and envelope["pilot_notice"] == AVISO_DE_PILOTO
            for envelope in prontos
        )
    assert do_piloto["pilot_notice"] == AVISO_DE_PILOTO
    # a comum recebe só o que está pronto, sem marca nenhuma
    assert all("value" not in linha for linha in comum["rows"])
    assert "pilot" not in aj.chaves_de(comum) and "pilot_notice" not in aj.chaves_de(
        comum
    )


def test_sem_campo_de_piloto_a_resposta_nao_muda(duas, monkeypatch) -> None:
    """Tudo pronto: a organização do piloto recebe a mesma resposta da comum, sem marca."""
    cliente, chaves, _ator, _org = duas
    monkeypatch.setattr(
        rotas, "regras_da_api", lambda: _regras(piloto_de=(), prontas=(TABELA,))
    )
    do_piloto = _get(cliente, chaves["piloto"]).json()
    assert do_piloto == _get(cliente, chaves["comum"]).json()
    assert "pilot_notice" not in aj.chaves_de(do_piloto)


def _campos_do_catalogo(cliente, chave: str) -> tuple[dict, list[dict]]:
    corpo = cliente.get("/data/v1/catalog", headers=aj.bearer(chave)).json()
    datasets = corpo["datasets"]
    financials = next((c for c in datasets if c["dataset"] == "financials"), {})
    return corpo, financials.get("fields", [])


def test_catalogo_marca_o_campo_que_so_sai_pelo_piloto(duas, monkeypatch) -> None:
    cliente, chaves, _ator, _org = duas
    monkeypatch.setattr(
        rotas,
        "regras_da_api",
        lambda: _regras(
            piloto_de=(SO_DO_PILOTO,), prontas=(TABELA,), linhas=_linhas_misturadas()
        ),
    )
    corpo, campos = _campos_do_catalogo(cliente, chaves["piloto"])
    marcados = {c["field"] for c in campos if c.get("pilot") is True}
    assert marcados == {"value"}
    assert len(campos) > len(marcados)
    assert corpo["pilot_notice"] == AVISO_DE_PILOTO

    corpo_comum, campos_comuns = _campos_do_catalogo(cliente, chaves["comum"])
    assert "value" not in {c["field"] for c in campos_comuns}
    assert "pilot" not in aj.chaves_de(corpo_comum)
    assert "pilot_notice" not in aj.chaves_de(corpo_comum)


# ---------------------------------------------------------------- o registro do pedido falha fechado

LIBERADO_PELO_PILOTO = Decisao(True, Motivo.LIBERADO_PELO_PILOTO)


def test_piloto_sem_registro_aberto_nao_sai() -> None:
    assert piloto.registrar("cvm-dfp", "valor", LIBERADO_PELO_PILOTO) is False


def test_o_json_abre_o_registro_e_o_deck_nao(banco, monkeypatch) -> None:
    """O deck (linha 782) ainda não leva a frase: sem o registro aberto, campo de piloto não entra no `.pptx`."""
    monkeypatch.setattr(rotas, "obter_engine", lambda: banco)
    monkeypatch.setattr(rotas, "registrar_consumo", lambda *_a, **_k: None)
    saiu: list[bool] = []

    def ler(_conexao):
        saiu.append(piloto.registrar("cvm-dfp", "valor", LIBERADO_PELO_PILOTO))
        return SimpleNamespace(corpo={}, fontes=set(), linhas=1)

    rotas._servido_contado(SimpleNamespace(), "financials", ler)  # o caminho do deck
    rotas._pedido_contado(SimpleNamespace(), "financials", ler)  # o caminho do JSON
    assert saiu == [False, True]


def test_registro_anota_cada_caminho() -> None:
    with piloto.anotar() as liberados:
        assert piloto.registrar("cvm-dfp", "valor", LIBERADO_PELO_PILOTO)
        assert piloto.registrar("cvm-dfp", "conta", Decisao(True, Motivo.LIBERADO))
        assert not piloto.registrar("cvm-dfp", "cpf", Decisao(False, Motivo.NUNCA_SAI))
    assert liberados.piloto == {("cvm-dfp", "valor")}
    assert (
        piloto.registrar("cvm-dfp", "valor", LIBERADO_PELO_PILOTO) is False
    )  # fechou com o `with`


def _envelope(fonte: str = "cvm-dfp") -> dict:
    return {"valor": 1, "fonte": fonte, "publico_em": "2026-01-01", "visto_em": None}


def test_com_piloto_todo_envelope_leva_a_marca() -> None:
    """Com piloto na resposta, todo envelope leva a marca: o de outro nome (lista, mediana...), o de outra fonte
    e o da prontidão cheia (D11.3, leitura mais estreita)."""
    liberados = piloto.Liberados(piloto={("cvm-dfp", "medianas")})
    corpo = {
        "medianas": [_envelope()],
        "conta": _envelope(),
        "outra": _envelope("rfb-cnpj"),
    }
    marcado = piloto.marcar(corpo, liberados)
    assert marcado["medianas"][0][piloto.MARCA] is True
    assert marcado["outra"][piloto.AVISO] == AVISO_DE_PILOTO
    assert marcado["conta"][piloto.MARCA] is True
    assert marcado[piloto.AVISO] == AVISO_DE_PILOTO


def test_campo_de_piloto_que_so_filtrou_marca_todos_os_blocos() -> None:
    """D11.3: o campo de piloto que não virou bloco (a data que escolhe quais compradores saem) tocou blocos
    que não se sabe quais; todos levam a marca, inclusive o da prontidão cheia."""
    liberados = piloto.Liberados(piloto={("rfb-cnpj", "data_entrada")})
    marcado = piloto.marcar({"conta": _envelope(), "lista": [_envelope()]}, liberados)
    assert marcado["conta"][piloto.MARCA] is True
    assert marcado["conta"][piloto.AVISO] == AVISO_DE_PILOTO
    assert marcado["lista"][0][piloto.MARCA] is True
    assert marcado[piloto.AVISO] == AVISO_DE_PILOTO


def test_envelope_dentro_do_valor_de_outro_tambem_leva_a_marca() -> None:
    """O bloco aninhado no valor de outro envelope é visto e marcado, como o de fora."""
    liberados = piloto.Liberados(piloto={("rfb-cnpj", "porte")})
    corpo = {
        "conta": _envelope(),
        "empresa": {**_envelope("rfb-cnpj"), "valor": {"porte": _envelope("rfb-cnpj")}},
    }
    marcado = piloto.marcar(corpo, liberados)
    assert marcado["conta"][piloto.MARCA] is True
    assert marcado["empresa"][piloto.MARCA] is True
    assert marcado["empresa"]["valor"]["porte"][piloto.MARCA] is True


def test_sem_piloto_marcar_devolve_o_mesmo_corpo() -> None:
    corpo = {"conta": _envelope()}
    assert piloto.marcar(corpo, piloto.Liberados()) is corpo


def test_os_nomes_da_marca_tem_traducao() -> None:
    from src.api_externa.nomes import para_fora

    assert {
        nome: para_fora(nome) for nome in (piloto.MARCA, piloto.AVISO)
    } == NOME_DE_FORA
