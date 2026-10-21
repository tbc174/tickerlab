"""Originação (B-33): o funil das operações no banco, isolado por conta e sem contato automático.

Os riscos são três: uma conta ver o funil de outra (R-09), a fase mudar sem a pessoa pedir e o
código passar a enviar e-mail ou mensagem. Rodam em SQLite na memória; as chaves compostas no
banco migrado (inclusive no PostgreSQL do CI) ficam em `test_originacao_migracao.py`.
"""

import ast
import inspect
import json
import re
from datetime import date
from pathlib import Path

import pytest
import sqlalchemy as sa

from src import auditoria, conformidade
from src.banco import originacao, sala
from src.banco.modelo import (
    FASES_DO_NEGOCIO,
    contatos_do_negocio,
    metadata,
    negocios_da_originacao,
    operacoes,
)
from src.banco.modelo import auditoria as tabela_da_auditoria
from src.banco.usuarios import apagar_conta, entrar

HOJE = date(2026, 10, 21)
ORIGEM = "Régua de M&A, evento IPE de 20/10"
RAIZ = Path(__file__).resolve().parent.parent


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


def _operacao(conexao, dono, nome="Aquisição da Alfa"):
    return sala.criar_operacao(
        conexao, usuario_id=dono.id, tipo="ma", nome=nome, hoje=HOJE
    )


def _negocio(conexao, dono, operacao=None, **mudar):
    operacao = operacao or _operacao(conexao, dono)
    dados = {"origem": ORIGEM, "hoje": HOJE, **mudar}
    return originacao.abrir_negocio(
        conexao, usuario_id=dono.id, operacao_id=operacao.id, **dados
    )


# --- o negócio e a fase ---------------------------------------------------------------------


def test_abrir_negocio_comeca_na_ideia_com_os_campos_limpos(conexao, ana):
    negocio = _negocio(
        conexao,
        ana,
        origem="  Indicação  ",
        alvo="Alfa S.A.",
        proximo_passo="   ",
        responsavel="Carla",
    )
    assert (negocio.fase, negocio.fase_desde) == ("ideia", HOJE)
    assert (
        negocio.origem,
        negocio.alvo,
        negocio.proximo_passo,
        negocio.responsavel,
    ) == (
        "Indicação",
        "Alfa S.A.",
        None,
        "Carla",
    )


def test_so_um_negocio_por_operacao(conexao, ana):
    operacao = _operacao(conexao, ana)
    _negocio(conexao, ana, operacao)
    with pytest.raises(originacao.NegocioJaExisteError):
        _negocio(conexao, ana, operacao)


@pytest.mark.parametrize(
    "mudar", [{"origem": "  "}, {"origem": "x" * 301}, {"alvo": "x" * 301}]
)
def test_abrir_negocio_recusa_dado_invalido(conexao, ana, mudar):
    with pytest.raises(ValueError):
        _negocio(conexao, ana, **mudar)


def test_a_fase_so_muda_quando_a_pessoa_pede(conexao, ana):
    operacao = _operacao(conexao, ana)
    negocio = _negocio(conexao, ana, operacao)
    # editar os campos, anotar contato e listar não mexem na fase
    originacao.atualizar_negocio(
        conexao, usuario_id=ana.id, operacao_id=operacao.id, proximo_passo="Ligar"
    )
    originacao.registrar_contato(
        conexao, usuario_id=ana.id, operacao_id=operacao.id, descricao="Falei com o CFO"
    )
    originacao.listar_negocios(conexao, usuario_id=ana.id)
    assert (
        originacao.buscar_negocio(
            conexao, usuario_id=ana.id, operacao_id=operacao.id
        ).fase
        == negocio.fase
        == "ideia"
    )
    mudou = originacao.mudar_fase(
        conexao,
        usuario_id=ana.id,
        operacao_id=operacao.id,
        fase="analise",
        hoje=date(2026, 10, 25),
    )
    assert (mudou.fase, mudou.fase_desde) == ("analise", date(2026, 10, 25))


def test_so_mudar_fase_escreve_a_fase():
    """Nenhuma outra função do módulo escreve a coluna `fase` (a fase não avança sozinha)."""
    fontes = {
        nome: inspect.getsource(funcao)
        for nome, funcao in inspect.getmembers(originacao, inspect.isfunction)
        if funcao.__module__ == originacao.__name__
    }
    escrevem = {n for n, f in fontes.items() if re.search(r"\bfase=", f)}
    assert escrevem <= {"mudar_fase", "abrir_negocio"}
    assert "fase" not in originacao.CAMPOS_DO_NEGOCIO


def test_mudar_para_a_mesma_fase_nao_muda_nada_e_fase_invalida_e_recusada(conexao, ana):
    operacao = _operacao(conexao, ana)
    _negocio(conexao, ana, operacao)
    antes = conexao.execute(sa.select(tabela_da_auditoria.c.id)).all()
    originacao.mudar_fase(
        conexao, usuario_id=ana.id, operacao_id=operacao.id, fase="ideia"
    )
    assert conexao.execute(sa.select(tabela_da_auditoria.c.id)).all() == antes
    with pytest.raises(ValueError):
        originacao.mudar_fase(
            conexao, usuario_id=ana.id, operacao_id=operacao.id, fase="aprovado"
        )


def test_a_fase_pode_voltar_e_listar_filtra_por_fase(conexao, ana):
    alfa, beta = _operacao(conexao, ana, "Alfa"), _operacao(conexao, ana, "Beta")
    _negocio(conexao, ana, alfa)
    _negocio(conexao, ana, beta)
    for fase in ("proposta", "analise"):
        originacao.mudar_fase(
            conexao, usuario_id=ana.id, operacao_id=alfa.id, fase=fase
        )
    por_fase = originacao.listar_negocios(conexao, usuario_id=ana.id, fase="analise")
    assert [n.operacao_id for n in por_fase] == [alfa.id]
    assert len(originacao.listar_negocios(conexao, usuario_id=ana.id)) == 2


def test_atualizar_negocio_troca_e_limpa_campos_mas_a_origem_e_obrigatoria(
    conexao, ana
):
    operacao = _operacao(conexao, ana)
    _negocio(conexao, ana, operacao, proximo_passo="Ligar", responsavel="Carla")
    novo = originacao.atualizar_negocio(
        conexao,
        usuario_id=ana.id,
        operacao_id=operacao.id,
        proximo_passo="",
        responsavel="Davi",
    )
    assert (novo.proximo_passo, novo.responsavel) == (None, "Davi")
    for invalido in ({"origem": ""}, {"fase": "fechado"}):
        with pytest.raises(ValueError):
            originacao.atualizar_negocio(
                conexao, usuario_id=ana.id, operacao_id=operacao.id, **invalido
            )


# --- contatos anotados à mão ----------------------------------------------------------------


def test_registrar_listar_e_apagar_contato(conexao, ana):
    operacao = _operacao(conexao, ana)
    _negocio(conexao, ana, operacao)
    primeiro = originacao.registrar_contato(
        conexao,
        usuario_id=ana.id,
        operacao_id=operacao.id,
        descricao="  Reunião com o CFO  ",
        ocorreu_em=date(2026, 10, 20),
    )
    originacao.registrar_contato(
        conexao,
        usuario_id=ana.id,
        operacao_id=operacao.id,
        descricao="Ligação com o jurídico",
        ocorreu_em=date(2026, 10, 21),
    )
    lista = originacao.listar_contatos(
        conexao, usuario_id=ana.id, operacao_id=operacao.id
    )
    assert [c.descricao for c in lista] == [
        "Ligação com o jurídico",
        "Reunião com o CFO",
    ]
    assert originacao.apagar_contato(
        conexao, usuario_id=ana.id, operacao_id=operacao.id, contato_id=primeiro.id
    )
    assert not originacao.apagar_contato(
        conexao, usuario_id=ana.id, operacao_id=operacao.id, contato_id=primeiro.id
    )


@pytest.mark.parametrize("descricao", ["", "   ", "x" * 501])
def test_contato_recusa_texto_vazio_ou_longo(conexao, ana, descricao):
    operacao = _operacao(conexao, ana)
    _negocio(conexao, ana, operacao)
    with pytest.raises(ValueError):
        originacao.registrar_contato(
            conexao, usuario_id=ana.id, operacao_id=operacao.id, descricao=descricao
        )


def test_contato_exige_negocio_aberto(conexao, ana):
    operacao = _operacao(conexao, ana)
    assert (
        originacao.registrar_contato(
            conexao, usuario_id=ana.id, operacao_id=operacao.id, descricao="Oi"
        )
        is None
    )


# --- isolamento entre contas ----------------------------------------------------------------


def test_outra_conta_nao_ve_nem_mexe_no_negocio(conexao, ana, bia):
    operacao = _operacao(conexao, ana)
    _negocio(conexao, ana, operacao)
    contato = originacao.registrar_contato(
        conexao, usuario_id=ana.id, operacao_id=operacao.id, descricao="Segredo"
    )
    com_os_ids_da_ana = {"usuario_id": bia.id, "operacao_id": operacao.id}
    assert originacao.buscar_negocio(conexao, **com_os_ids_da_ana) is None
    assert originacao.listar_negocios(conexao, usuario_id=bia.id) == []
    assert originacao.mudar_fase(conexao, **com_os_ids_da_ana, fase="fechado") is None
    assert (
        originacao.atualizar_negocio(conexao, **com_os_ids_da_ana, responsavel="Bia")
        is None
    )
    assert originacao.listar_contatos(conexao, **com_os_ids_da_ana) == []
    assert not originacao.apagar_contato(
        conexao, **com_os_ids_da_ana, contato_id=contato.id
    )
    assert (
        originacao.registrar_contato(conexao, **com_os_ids_da_ana, descricao="x")
        is None
    )
    # nada mudou para a Ana
    negocio = originacao.buscar_negocio(
        conexao, usuario_id=ana.id, operacao_id=operacao.id
    )
    assert (negocio.fase, negocio.responsavel) == ("ideia", None)
    assert (
        len(
            originacao.listar_contatos(
                conexao, usuario_id=ana.id, operacao_id=operacao.id
            )
        )
        == 1
    )


def test_nao_se_abre_negocio_na_operacao_de_outra_conta(conexao, ana, bia):
    operacao = _operacao(conexao, ana)
    assert (
        originacao.abrir_negocio(
            conexao, usuario_id=bia.id, operacao_id=operacao.id, origem=ORIGEM
        )
        is None
    )
    assert conexao.execute(sa.select(negocios_da_originacao)).all() == []


def test_toda_funcao_publica_pede_a_conta_e_a_operacao_pelo_nome():
    publicas = [
        (nome, funcao)
        for nome, funcao in inspect.getmembers(originacao, inspect.isfunction)
        if not nome.startswith("_") and funcao.__module__ == originacao.__name__
    ]
    assert publicas
    de_todas_as_operacoes = {"listar_negocios", "dados_para_exportar"}
    for nome, funcao in publicas:
        parametros = inspect.signature(funcao).parameters
        assert parametros["usuario_id"].kind is inspect.Parameter.KEYWORD_ONLY, nome
        if nome not in de_todas_as_operacoes:
            assert parametros["operacao_id"].kind is inspect.Parameter.KEYWORD_ONLY, (
                nome
            )


# --- nada contata ninguém ---------------------------------------------------------------------

MODULOS_DE_ENVIO = {
    "smtplib",
    "email",
    "requests",
    "httpx",
    "urllib",
    "aiohttp",
    "http",
    "socket",
    "resend",
    "stripe",
    "anthropic",
}


def _importados(arquivo: Path) -> set[str]:
    nomes: set[str] = set()
    for no in ast.walk(ast.parse(arquivo.read_text(encoding="utf-8"))):
        if isinstance(no, ast.Import):
            nomes |= {a.name for a in no.names}
        elif isinstance(no, ast.ImportFrom) and no.module:
            nomes.add(no.module)
    return nomes


def test_o_modulo_nao_importa_nada_de_envio_nem_de_rede():
    importados = _importados(RAIZ / "src" / "banco" / "originacao.py")
    raizes = {nome.split(".")[0] for nome in importados}
    assert not raizes & MODULOS_DE_ENVIO, raizes & MODULOS_DE_ENVIO
    assert not {n for n in importados if n.startswith(("src.envio", "src.email"))}


def test_as_tabelas_nao_tem_coluna_de_contato_externo():
    colunas = {
        c.name for t in (negocios_da_originacao, contatos_do_negocio) for c in t.c
    }
    proibidas = {
        "email",
        "e_mail",
        "telefone",
        "celular",
        "whatsapp",
        "endereco",
        "url",
    }
    assert not colunas & proibidas


# --- LGPD e auditoria -------------------------------------------------------------------------


def test_exportar_meus_dados_leva_o_funil_so_da_conta(conexao, ana, bia):
    operacao = _operacao(conexao, ana)
    _negocio(conexao, ana, operacao, alvo="Alfa S.A.")
    originacao.registrar_contato(
        conexao,
        usuario_id=ana.id,
        operacao_id=operacao.id,
        descricao="Falei com o CFO",
        ocorreu_em=date(2026, 10, 20),
    )
    _negocio(conexao, bia)
    (item,) = conformidade.exportar_meus_dados(conexao, ana.id)["originacao"]
    assert (item["fase"], item["alvo"], item["fase_desde"]) == (
        "ideia",
        "Alfa S.A.",
        "2026-10-21",
    )
    assert [c["descricao"] for c in item["contatos"]] == ["Falei com o CFO"]
    assert "usuario_id" not in item
    json.dumps(conformidade.exportar_meus_dados(conexao, ana.id))  # vira JSON


def test_apagar_a_conta_leva_o_funil_e_so_o_dela(conexao, ana, bia):
    for dono in (ana, bia):
        operacao = _operacao(conexao, dono)
        _negocio(conexao, dono, operacao)
        originacao.registrar_contato(
            conexao, usuario_id=dono.id, operacao_id=operacao.id, descricao="Oi"
        )
    assert apagar_conta(conexao, ana.id)
    for tabela in (negocios_da_originacao, contatos_do_negocio):
        donos = set(conexao.execute(sa.select(tabela.c.usuario_id)).scalars())
        assert donos == {bia.id}, tabela.name


def test_apagar_a_operacao_leva_o_negocio_e_os_contatos(conexao, ana):
    operacao = _operacao(conexao, ana)
    _negocio(conexao, ana, operacao)
    originacao.registrar_contato(
        conexao, usuario_id=ana.id, operacao_id=operacao.id, descricao="Oi"
    )
    assert sala.apagar_operacao(conexao, usuario_id=ana.id, operacao_id=operacao.id)
    for tabela in (operacoes, negocios_da_originacao, contatos_do_negocio):
        assert conexao.execute(sa.select(tabela)).all() == [], tabela.name


def test_auditoria_guarda_so_ids_e_codigos_de_fase(conexao, ana):
    operacao = _operacao(conexao, ana)
    _negocio(
        conexao,
        ana,
        operacao,
        origem="ORIGEM-SECRETA",
        alvo="ALVO-SECRETO",
        proximo_passo="PASSO-SECRETO",
        responsavel="RESPONSAVEL-SECRETO",
    )
    contato = originacao.registrar_contato(
        conexao, usuario_id=ana.id, operacao_id=operacao.id, descricao="CONTATO-SECRETO"
    )
    originacao.atualizar_negocio(
        conexao,
        usuario_id=ana.id,
        operacao_id=operacao.id,
        proximo_passo="OUTRO-SECRETO",
    )
    originacao.mudar_fase(
        conexao, usuario_id=ana.id, operacao_id=operacao.id, fase="negociacao"
    )
    originacao.apagar_contato(
        conexao, usuario_id=ana.id, operacao_id=operacao.id, contato_id=contato.id
    )
    registros = [
        r
        for r in conexao.execute(sa.select(tabela_da_auditoria)).mappings()
        if r["acao"].startswith(("negocio_", "contato_"))
    ]
    assert {r["acao"] for r in registros} == {
        auditoria.ACAO_NEGOCIO_ABERTO,
        auditoria.ACAO_NEGOCIO_ATUALIZADO,
        auditoria.ACAO_NEGOCIO_FASE_MUDADA,
        auditoria.ACAO_CONTATO_REGISTRADO,
        auditoria.ACAO_CONTATO_APAGADO,
    }
    texto = json.dumps([str(r["detalhes"]) for r in registros])
    assert "SECRET" not in texto
    mudanca = next(
        r for r in registros if r["acao"] == auditoria.ACAO_NEGOCIO_FASE_MUDADA
    )
    assert mudanca["detalhes"] == {"de": "ideia", "para": "negociacao"}
    assert set(FASES_DO_NEGOCIO) >= {"ideia", "negociacao"}
