"""Migração 0042 (garantias, B-17): sobe, desce e as chaves compostas valem no banco.

Rodam em SQLite por padrão e no PostgreSQL de verdade no CI (TICKERLAB_TEST_DATABASE_URL), como os
testes da originação: o que importa é que o banco migrado, não só o código, recuse uma conta trocada,
um laudo de outra sala e um haircut fora de 0 a 1.
"""

import os
import uuid
from datetime import date
from decimal import Decimal

import pytest
import sqlalchemy as sa

from src.banco import garantias, sala
from src.banco.conexao import criar_engine, desfazer_ate, migrar_para
from src.banco.modelo import exposicoes_da_operacao, garantias_da_operacao, operacoes
from src.banco.usuarios import apagar_conta, entrar

URL_DE_TESTE = os.environ.get("TICKERLAB_TEST_DATABASE_URL")
TABELAS = {"exposicoes_da_operacao", "garantias_da_operacao"}
HOJE = date(2026, 10, 21)

pytestmark = pytest.mark.xdist_group("postgres")


@pytest.fixture
def motor(tmp_path):
    url = URL_DE_TESTE or f"sqlite:///{(tmp_path / 'garantias.sqlite').as_posix()}"
    if URL_DE_TESTE:
        migrar_para("base", url)
    migrar_para("head", url)
    motor = criar_engine(url)
    yield motor
    motor.dispose()
    if URL_DE_TESTE:
        migrar_para("base", url)


def _url(motor):
    return motor.url.render_as_string(hide_password=False)


def _tabelas(url):
    motor = criar_engine(url)
    try:
        return set(sa.inspect(motor).get_table_names())
    finally:
        motor.dispose()


def _contas(motor):
    with motor.begin() as conexao:
        ana = entrar(conexao, "sub-ana-gar", "ana-gar@exemplo.com", "Ana")[0]
        bia = entrar(conexao, "sub-bia-gar", "bia-gar@exemplo.com", "Bia")[0]
    return ana, bia


def _garantia_da(motor, dono, sha="a" * 64):
    """Uma operação com exposição, garantia e um documento; devolve (operação, exposição, garantia, doc)."""
    with motor.begin() as conexao:
        operacao = sala.criar_operacao(
            conexao, usuario_id=dono.id, tipo="credito", nome="CCB da Alfa"
        )
        exposicao = garantias.registrar_exposicao(
            conexao,
            usuario_id=dono.id,
            operacao_id=operacao.id,
            rotulo="CCB",
            valor=Decimal(500),
            moeda="BRL",
        )
        documento = sala.registrar_documento(
            conexao,
            usuario_id=dono.id,
            operacao_id=operacao.id,
            nome_original="laudo.pdf",
            tipo="pdf",
            tamanho_bytes=10,
            sha256=sha,
        )
        garantia = garantias.registrar_garantia(
            conexao,
            usuario_id=dono.id,
            operacao_id=operacao.id,
            exposicao_id=exposicao.id,
            tipo="imovel",
            valor_avaliado=Decimal(1000),
            moeda="BRL",
            avaliado_em=HOJE,
            haircut=Decimal("0.3"),
            liquidez="media",
            laudo_id=documento.id,
            laudo_pagina=2,
        )
    return operacao, exposicao, garantia, documento


def _linha(garantia, **mudar):
    return {
        "id": uuid.uuid4(),
        "usuario_id": garantia.usuario_id,
        "operacao_id": garantia.operacao_id,
        "exposicao_id": garantia.exposicao_id,
        "tipo": "imovel",
        "valor_avaliado": Decimal(1),
        "moeda": "BRL",
        "avaliado_em": HOJE,
        "haircut": Decimal("0.1"),
        "liquidez": "alta",
        **mudar,
    }


class _Chaves:
    """As chaves da garantia criada (a dataclass da sala não guarda `usuario_id`)."""

    def __init__(self, dono, operacao, exposicao):
        self.usuario_id = dono.id
        self.operacao_id = operacao.id
        self.exposicao_id = exposicao.id


def _tentar(motor, linha):
    with pytest.raises(sa.exc.IntegrityError), motor.begin() as conexao:
        conexao.execute(sa.insert(garantias_da_operacao).values(linha))


def test_migracao_0042_desce_para_a_0041_e_sobe_de_novo(motor):
    url = _url(motor)
    assert _tabelas(url) >= TABELAS
    desfazer_ate("0041", url)
    tabelas = _tabelas(url)
    assert not TABELAS & tabelas
    assert "operacoes" in tabelas and "negocios_da_originacao" in tabelas
    migrar_para("head", url)
    assert _tabelas(url) >= TABELAS


def test_toda_tabela_tem_dono_e_sai_com_a_conta_e_com_a_operacao(motor):
    inspecao = sa.inspect(motor)
    for tabela in TABELAS:
        colunas = {c["name"]: c for c in inspecao.get_columns(tabela)}
        assert colunas["usuario_id"]["nullable"] is False, tabela
        estrangeiras = inspecao.get_foreign_keys(tabela)
        assert any(e["referred_table"] == "usuarios" for e in estrangeiras), tabela
        compostas = [
            e["constrained_columns"]
            for e in estrangeiras
            if e["referred_table"] == "operacoes"
        ]
        assert compostas == [["operacao_id", "usuario_id"]], tabela
    laudo = [
        e
        for e in inspecao.get_foreign_keys("garantias_da_operacao")
        if e["referred_table"] == "documentos_da_sala"
    ]
    assert [e["constrained_columns"] for e in laudo] == [
        ["laudo_id", "operacao_id", "usuario_id"]
    ]


def test_banco_recusa_conta_trocada_na_exposicao_e_na_garantia(motor):
    ana, bia = _contas(motor)
    operacao, exposicao, _, _ = _garantia_da(motor, ana)
    with pytest.raises(sa.exc.IntegrityError), motor.begin() as conexao:
        conexao.execute(
            sa.insert(exposicoes_da_operacao).values(
                id=uuid.uuid4(),
                usuario_id=bia.id,
                operacao_id=operacao.id,
                rotulo="Intruso",
                valor=Decimal(1),
                moeda="BRL",
            )
        )
    base = _linha(_Chaves(ana, operacao, exposicao))
    _tentar(motor, {**base, "usuario_id": bia.id})


def test_banco_recusa_laudo_de_outra_sala(motor):
    ana, _ = _contas(motor)
    operacao, exposicao, _, _ = _garantia_da(motor, ana)
    with motor.begin() as conexao:
        outra = sala.criar_operacao(
            conexao, usuario_id=ana.id, tipo="credito", nome="Outra"
        )
        documento = sala.registrar_documento(
            conexao,
            usuario_id=ana.id,
            operacao_id=outra.id,
            nome_original="outro.pdf",
            tipo="pdf",
            tamanho_bytes=10,
            sha256="b" * 64,
        )
    base = _linha(_Chaves(ana, operacao, exposicao))
    _tentar(motor, {**base, "laudo_id": documento.id, "laudo_pagina": 1})


@pytest.mark.parametrize(
    "mudar",
    [
        {"haircut": Decimal("1.5")},
        {"haircut": Decimal("-0.1")},
        {"valor_avaliado": Decimal(-1)},
        {"onus_anteriores": Decimal(-1)},
        {"prioridade": 0},
        {"tipo": "ouro"},
        {"liquidez": "extra"},
        {"laudo_pagina": 3},  # página sem documento
    ],
)
def test_banco_recusa_garantia_fora_das_regras(motor, mudar):
    ana, _ = _contas(motor)
    operacao, exposicao, _, _ = _garantia_da(motor, ana)
    _tentar(motor, {**_linha(_Chaves(ana, operacao, exposicao)), **mudar})


def test_banco_recusa_exposicao_sem_valor(motor):
    ana, _ = _contas(motor)
    operacao, _, _, _ = _garantia_da(motor, ana)
    with pytest.raises(sa.exc.IntegrityError), motor.begin() as conexao:
        conexao.execute(
            sa.insert(exposicoes_da_operacao).values(
                id=uuid.uuid4(),
                usuario_id=ana.id,
                operacao_id=operacao.id,
                rotulo="Zero",
                valor=Decimal(0),
                moeda="BRL",
            )
        )


def test_apagar_a_conta_no_banco_migrado_leva_as_garantias_e_so_as_dela(motor):
    ana, bia = _contas(motor)
    _garantia_da(motor, ana)
    _garantia_da(motor, bia)
    with motor.begin() as conexao:
        assert apagar_conta(conexao, ana.id)
    with motor.connect() as conexao:
        for tabela in (operacoes, exposicoes_da_operacao, garantias_da_operacao):
            donos = set(conexao.execute(sa.select(tabela.c.usuario_id)).scalars())
            assert donos == {bia.id}, tabela.name


def test_apagar_o_documento_no_banco_migrado_solta_o_laudo_e_mantem_a_garantia(motor):
    ana, _ = _contas(motor)
    operacao, _, garantia, documento = _garantia_da(motor, ana)
    with motor.begin() as conexao:
        assert sala.apagar_documento(
            conexao,
            usuario_id=ana.id,
            operacao_id=operacao.id,
            documento_id=documento.id,
        )
        depois = garantias.buscar_garantia(
            conexao,
            usuario_id=ana.id,
            operacao_id=operacao.id,
            garantia_id=garantia.id,
        )
    assert depois is not None and depois.laudo_id is None


def test_apagar_a_operacao_no_banco_migrado_leva_exposicoes_e_garantias(motor):
    ana, _ = _contas(motor)
    operacao, _, _, _ = _garantia_da(motor, ana)
    with motor.begin() as conexao:
        assert sala.apagar_operacao(conexao, usuario_id=ana.id, operacao_id=operacao.id)
    with motor.connect() as conexao:
        for tabela in (exposicoes_da_operacao, garantias_da_operacao):
            assert conexao.execute(sa.select(tabela.c.usuario_id)).all() == []
