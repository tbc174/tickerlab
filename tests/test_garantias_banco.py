"""Garantias (B-17): exposição e garantia por operação, isoladas por conta e sem dado pessoal de terceiros.

Os riscos são três: uma conta ver as garantias de outra (R-09), nome ou CPF de titular entrar em coluna
nova, e a validade vencida apagar ou mudar uma garantia sozinha. Rodam em SQLite na memória; as chaves
compostas no banco migrado (inclusive no PostgreSQL do CI) ficam em `test_garantias_migracao.py`.
"""

import inspect
import json
import uuid
from datetime import date
from decimal import Decimal

import pytest
import sqlalchemy as sa

from src import auditoria, conformidade
from src.banco import garantias, sala
from src.banco.modelo import auditoria as tabela_da_auditoria
from src.banco.modelo import (
    documentos_da_sala,
    exposicoes_da_operacao,
    garantias_da_operacao,
    metadata,
    operacoes,
)
from src.banco.usuarios import apagar_conta, entrar

HOJE = date(2026, 10, 21)
D = Decimal


@pytest.fixture
def conexao():
    motor = sa.create_engine("sqlite://", poolclass=sa.pool.StaticPool)
    sa.event.listen(motor, "connect", lambda c, _: c.execute("PRAGMA foreign_keys=ON"))
    metadata.create_all(motor)
    with motor.begin() as conexao:
        yield conexao


@pytest.fixture
def ana(conexao):
    return entrar(conexao, "ana", "ana@exemplo.com", "Ana")[0]


@pytest.fixture
def bia(conexao):
    return entrar(conexao, "bia", "bia@exemplo.com", "Bia")[0]


def _operacao(conexao, dono):
    return sala.criar_operacao(
        conexao, usuario_id=dono.id, tipo="credito", nome="CCB da Alfa", hoje=HOJE
    )


def _exposicao(conexao, dono, operacao=None, valor="500"):
    operacao = operacao or _operacao(conexao, dono)
    return garantias.registrar_exposicao(
        conexao,
        usuario_id=dono.id,
        operacao_id=operacao.id,
        rotulo="CCB principal",
        valor=D(valor),
        moeda="brl",
    )


def _garantia(conexao, dono, exposicao, **mudar):
    dados = {
        "tipo": "imovel",
        "valor_avaliado": D("1000"),
        "moeda": "BRL",
        "avaliado_em": HOJE,
        "haircut": D("0.30"),
        "liquidez": "media",
        "onus_anteriores": D("100"),
        **mudar,
    }
    return garantias.registrar_garantia(
        conexao,
        usuario_id=dono.id,
        operacao_id=exposicao.operacao_id,
        exposicao_id=exposicao.id,
        **dados,
    )


def _documento(conexao, dono, operacao):
    return sala.registrar_documento(
        conexao,
        usuario_id=dono.id,
        operacao_id=operacao.id,
        nome_original="laudo.pdf",
        tipo="pdf",
        tamanho_bytes=10,
        sha256="a" * 64,
    )


# --- exposição e garantia -----------------------------------------------------------------


def test_registrar_exposicao_e_garantia_guarda_os_campos(conexao, ana):
    exposicao = _exposicao(conexao, ana)
    assert exposicao.moeda == "BRL" and exposicao.valor == D("500")
    garantia = _garantia(
        conexao, ana, exposicao, titular_ref="entidade:123", prioridade=2
    )
    assert garantia.tipo == "imovel" and garantia.prioridade == 2
    assert garantia.titular_ref == "entidade:123"
    assert garantia.haircut == D("0.3") and garantia.laudo_id is None
    assert garantias.listar_garantias(
        conexao, usuario_id=ana.id, operacao_id=exposicao.operacao_id
    ) == [garantia]


@pytest.mark.parametrize(
    "mudar",
    [
        {"tipo": "ouro"},
        {"liquidez": "enorme"},
        {"haircut": D("1.01")},
        {"haircut": D("-0.1")},
        {"valor_avaliado": D("-1")},
        {"onus_anteriores": D("-1")},
        {"prioridade": 0},
        {"moeda": "REAL"},
        {"valor_avaliado": 1000},  # número solto, não Decimal
    ],
)
def test_garantia_recusa_dado_invalido(conexao, ana, mudar):
    exposicao = _exposicao(conexao, ana)
    with pytest.raises(ValueError):
        _garantia(conexao, ana, exposicao, **mudar)


@pytest.mark.parametrize("valor", [D("0"), D("-5")])
def test_exposicao_exige_valor_maior_que_zero(conexao, ana, valor):
    with pytest.raises(ValueError):
        _exposicao(conexao, ana, valor=str(valor))


@pytest.mark.parametrize(
    "titular",
    [
        "123.456.789-09",
        "12345678909",
        "123-456-789-09",
        "Maria da Silva",
        "Banco S.A.",
        "a/b",
    ],
)
def test_titular_so_por_id_recusa_cpf_e_nome(conexao, ana, titular):
    exposicao = _exposicao(conexao, ana)
    with pytest.raises(ValueError):
        _garantia(conexao, ana, exposicao, titular_ref=titular)


def test_titular_vazio_vira_sem_titular_e_id_de_cnpj_passa(conexao, ana):
    exposicao = _exposicao(conexao, ana)
    assert _garantia(conexao, ana, exposicao, titular_ref="  ").titular_ref is None
    assert _garantia(conexao, ana, exposicao, titular_ref="12345678000190").titular_ref


def test_cobertura_da_exposicao_usa_a_formula_e_so_vigentes(conexao, ana):
    exposicao = _exposicao(conexao, ana)
    _garantia(conexao, ana, exposicao)  # 1000 × 0,7 − 100 = 600
    _garantia(conexao, ana, exposicao, valido_ate=date(2026, 10, 1))  # vencida
    resultado = garantias.cobertura_da_exposicao(
        conexao,
        usuario_id=ana.id,
        operacao_id=exposicao.operacao_id,
        exposicao_id=exposicao.id,
        hoje=HOJE,
    )
    assert D(resultado["cobertura"]) == D("1.2")
    assert D(resultado["cobertura_contando_as_vencidas"]) == D("2.4")
    assert resultado["fora_da_conta"][0]["motivo"] == "vencida"
    json.dumps(resultado)  # vira JSON sem Decimal


def test_validade_vencida_nao_apaga_nem_muda_a_garantia(conexao, ana):
    exposicao = _exposicao(conexao, ana)
    garantia = _garantia(conexao, ana, exposicao, valido_ate=date(2020, 1, 1))
    garantias.cobertura_da_exposicao(
        conexao,
        usuario_id=ana.id,
        operacao_id=exposicao.operacao_id,
        exposicao_id=exposicao.id,
        hoje=HOJE,
    )
    assert (
        garantias.buscar_garantia(
            conexao,
            usuario_id=ana.id,
            operacao_id=exposicao.operacao_id,
            garantia_id=garantia.id,
        )
        == garantia
    )


# --- laudo --------------------------------------------------------------------------------


def test_laudo_e_documento_da_sala_com_a_pagina_citada(conexao, ana):
    exposicao = _exposicao(conexao, ana)
    operacao = sala.buscar_operacao(
        conexao, usuario_id=ana.id, operacao_id=exposicao.operacao_id
    )
    documento = _documento(conexao, ana, operacao)
    garantia = _garantia(conexao, ana, exposicao, laudo_id=documento.id, laudo_pagina=4)
    assert (garantia.laudo_id, garantia.laudo_pagina) == (documento.id, 4)
    for mudar in (
        {"laudo_id": documento.id},  # sem página
        {"laudo_pagina": 3},  # página sem documento
        {"laudo_id": documento.id, "laudo_pagina": 0},
        {"laudo_id": uuid.uuid4(), "laudo_pagina": 1},  # documento que não existe
    ):
        with pytest.raises(ValueError):
            _garantia(conexao, ana, exposicao, **mudar)


def test_laudo_de_outra_operacao_e_recusado(conexao, ana):
    exposicao = _exposicao(conexao, ana)
    outra = _operacao(conexao, ana)
    documento = _documento(conexao, ana, outra)
    with pytest.raises(ValueError):
        _garantia(conexao, ana, exposicao, laudo_id=documento.id, laudo_pagina=1)


def test_apagar_o_documento_solta_o_laudo_mas_a_garantia_fica(conexao, ana):
    exposicao = _exposicao(conexao, ana)
    operacao = sala.buscar_operacao(
        conexao, usuario_id=ana.id, operacao_id=exposicao.operacao_id
    )
    documento = _documento(conexao, ana, operacao)
    garantia = _garantia(conexao, ana, exposicao, laudo_id=documento.id, laudo_pagina=4)
    assert sala.apagar_documento(
        conexao, usuario_id=ana.id, operacao_id=operacao.id, documento_id=documento.id
    )
    depois = garantias.buscar_garantia(
        conexao, usuario_id=ana.id, operacao_id=operacao.id, garantia_id=garantia.id
    )
    assert depois is not None
    assert (depois.laudo_id, depois.laudo_pagina) == (None, None)
    assert depois.valor_avaliado == garantia.valor_avaliado


# --- isolamento ---------------------------------------------------------------------------


def test_outra_conta_nao_ve_nem_mexe_nas_garantias(conexao, ana, bia):
    exposicao = _exposicao(conexao, ana)
    garantia = _garantia(conexao, ana, exposicao)
    chaves = {"usuario_id": bia.id, "operacao_id": exposicao.operacao_id}
    assert garantias.listar_exposicoes(conexao, **chaves) == []
    assert garantias.listar_garantias(conexao, **chaves) == []
    assert (
        garantias.buscar_exposicao(conexao, exposicao_id=exposicao.id, **chaves) is None
    )
    assert garantias.buscar_garantia(conexao, garantia_id=garantia.id, **chaves) is None
    assert (
        garantias.cobertura_da_exposicao(conexao, exposicao_id=exposicao.id, **chaves)
        is None
    )
    assert not garantias.apagar_garantia(conexao, garantia_id=garantia.id, **chaves)
    assert not garantias.apagar_exposicao(conexao, exposicao_id=exposicao.id, **chaves)
    assert (
        garantias.registrar_garantia(
            conexao,
            exposicao_id=exposicao.id,
            tipo="imovel",
            valor_avaliado=D(1),
            moeda="BRL",
            avaliado_em=HOJE,
            haircut=D(0),
            liquidez="alta",
            **chaves,
        )
        is None
    )
    assert garantias.buscar_garantia(
        conexao,
        usuario_id=ana.id,
        operacao_id=exposicao.operacao_id,
        garantia_id=garantia.id,
    )


def test_nao_se_registra_exposicao_na_operacao_de_outra_conta(conexao, ana, bia):
    operacao = _operacao(conexao, ana)
    assert (
        garantias.registrar_exposicao(
            conexao,
            usuario_id=bia.id,
            operacao_id=operacao.id,
            rotulo="x",
            valor=D(1),
            moeda="BRL",
        )
        is None
    )


def test_exposicao_de_outra_operacao_da_mesma_conta_nao_serve(conexao, ana):
    exposicao = _exposicao(conexao, ana)
    outra = _operacao(conexao, ana)
    assert (
        garantias.registrar_garantia(
            conexao,
            usuario_id=ana.id,
            operacao_id=outra.id,
            exposicao_id=exposicao.id,
            tipo="imovel",
            valor_avaliado=D(1),
            moeda="BRL",
            avaliado_em=HOJE,
            haircut=D(0),
            liquidez="alta",
        )
        is None
    )


def test_toda_funcao_publica_pede_a_conta_e_a_operacao_pelo_nome():
    publicas = [
        (nome, funcao)
        for nome, funcao in inspect.getmembers(garantias, inspect.isfunction)
        if not nome.startswith("_") and funcao.__module__ == garantias.__name__
    ]
    assert publicas
    for nome, funcao in publicas:
        parametros = inspect.signature(funcao).parameters
        assert parametros["usuario_id"].kind is inspect.Parameter.KEYWORD_ONLY, nome
        if nome != "dados_para_exportar":
            assert parametros["operacao_id"].kind is inspect.Parameter.KEYWORD_ONLY, (
                nome
            )


def test_as_tabelas_nao_tem_coluna_de_nome_cpf_ou_contato():
    proibidas = ("nome", "cpf", "email", "telefone", "endereco", "avalista")
    for tabela in (exposicoes_da_operacao, garantias_da_operacao):
        for coluna in tabela.c:
            assert not any(p in coluna.name for p in proibidas), coluna.name


# --- exportar, apagar, auditoria ----------------------------------------------------------


def test_exportar_meus_dados_leva_so_as_garantias_da_conta(conexao, ana, bia):
    exposicao = _exposicao(conexao, ana)
    _garantia(conexao, ana, exposicao, titular_ref="entidade:1")
    _garantia(conexao, bia, _exposicao(conexao, bia))
    exportado = conformidade.exportar_meus_dados(conexao, ana.id)["garantias"]
    assert len(exportado["exposicoes"]) == 1 and len(exportado["garantias"]) == 1
    assert exportado["garantias"][0]["titular_ref"] == "entidade:1"
    assert exportado["garantias"][0]["haircut"] == "0.300000"
    json.dumps(conformidade.exportar_meus_dados(conexao, ana.id))  # vira JSON


def test_apagar_a_conta_leva_as_garantias_e_so_as_dela(conexao, ana, bia):
    _garantia(conexao, ana, _exposicao(conexao, ana))
    _garantia(conexao, bia, _exposicao(conexao, bia))
    assert apagar_conta(conexao, ana.id)
    for tabela in (operacoes, exposicoes_da_operacao, garantias_da_operacao):
        donos = set(conexao.execute(sa.select(tabela.c.usuario_id)).scalars())
        assert donos == {bia.id}, tabela.name


def test_apagar_a_operacao_ou_a_exposicao_leva_as_garantias(conexao, ana):
    exposicao = _exposicao(conexao, ana)
    _garantia(conexao, ana, exposicao)
    assert garantias.apagar_exposicao(
        conexao,
        usuario_id=ana.id,
        operacao_id=exposicao.operacao_id,
        exposicao_id=exposicao.id,
    )
    assert conexao.execute(sa.select(garantias_da_operacao.c.id)).all() == []
    exposicao = _exposicao(conexao, ana)
    _garantia(conexao, ana, exposicao)
    assert sala.apagar_operacao(
        conexao, usuario_id=ana.id, operacao_id=exposicao.operacao_id
    )
    for tabela in (exposicoes_da_operacao, garantias_da_operacao):
        assert conexao.execute(sa.select(tabela.c.id)).all() == []


def test_auditoria_guarda_so_ids_e_o_tipo(conexao, ana):
    exposicao = _exposicao(conexao, ana)
    garantia = _garantia(conexao, ana, exposicao, titular_ref="entidade:segredo")
    garantias.apagar_garantia(
        conexao,
        usuario_id=ana.id,
        operacao_id=exposicao.operacao_id,
        garantia_id=garantia.id,
    )
    linhas = conexao.execute(
        sa.select(tabela_da_auditoria.c.acao, tabela_da_auditoria.c.detalhes).where(
            tabela_da_auditoria.c.acao.in_(
                [
                    auditoria.ACAO_EXPOSICAO_REGISTRADA,
                    auditoria.ACAO_GARANTIA_REGISTRADA,
                    auditoria.ACAO_GARANTIA_APAGADA,
                ]
            )
        )
    ).all()
    assert len(linhas) == 3
    texto = json.dumps([dict(l.detalhes) for l in linhas])
    for segredo in ("CCB principal", "entidade:segredo", "1000", "0.30"):
        assert segredo not in texto


def test_pagina_do_laudo_maior_que_o_documento_e_recusada_quando_o_total_e_conhecido(
    conexao, ana
):
    exposicao = _exposicao(conexao, ana)
    operacao = sala.buscar_operacao(
        conexao, usuario_id=ana.id, operacao_id=exposicao.operacao_id
    )
    documento = _documento(conexao, ana, operacao)
    conexao.execute(
        sa.update(documentos_da_sala)
        .where(documentos_da_sala.c.id == documento.id)
        .values(paginas=5)
    )
    with pytest.raises(ValueError):
        _garantia(conexao, ana, exposicao, laudo_id=documento.id, laudo_pagina=6)
    assert _garantia(conexao, ana, exposicao, laudo_id=documento.id, laudo_pagina=5)
