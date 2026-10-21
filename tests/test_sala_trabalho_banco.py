"""O trabalho na sala no banco (src/banco/sala_trabalho.py, B-20 PR 4).

SQLite na memória com as chaves estrangeiras ligadas. O que estes testes travam: o isolamento por
conta (outra conta recebe `None`, nunca o dado), as contradições abertas e fechadas pela regra, o
que a pessoa já marcou ficar como está, e os estados do checklist ("recebido" automático,
"revisado" só da pessoa).
"""

import inspect
import uuid
from datetime import date
from decimal import Decimal

import pytest
import sqlalchemy as sa

from src.banco import sala, sala_trabalho
from src.banco.modelo import contradicoes_da_sala, metadata
from src.banco.usuarios import entrar
from src.sala import checklists

HOJE = date(2026, 10, 21)


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


def _operacao(conexao, dono, tipo="ma"):
    return sala.criar_operacao(
        conexao, usuario_id=dono.id, tipo=tipo, nome="Alfa", hoje=HOJE
    )


def _documento(conexao, dono, operacao, letra="a"):
    return sala.registrar_documento(
        conexao,
        usuario_id=dono.id,
        operacao_id=operacao.id,
        nome_original=f"{letra}.pdf",
        tipo="pdf",
        tamanho_bytes=10,
        sha256=letra * 64,
    )


def _evidencia(conexao, dono, operacao, documento, valor="1000", **mudar):
    dados = {
        "metrica": "receita_liquida",
        "periodo": "2025",
        "valor_numero": Decimal(valor),
        "valor_texto": None,
        "unidade": "milhares",
        "moeda": "brl",
        "pagina": 3,
        "secao": None,
        "tabela": None,
        "trecho": "Receita líquida",
        "conferida": True,
        **mudar,
    }
    return sala_trabalho.criar_evidencia(
        conexao,
        usuario_id=dono.id,
        operacao_id=operacao.id,
        documento_id=documento.id,
        **dados,
    )


def _contradicoes(conexao, dono, operacao):
    return sala_trabalho.listar_contradicoes(
        conexao, usuario_id=dono.id, operacao_id=operacao.id
    )


@pytest.fixture
def duas_evidencias(conexao, ana):
    operacao = _operacao(conexao, ana)
    primeiro = _documento(conexao, ana, operacao, "a")
    segundo = _documento(conexao, ana, operacao, "b")
    return (
        operacao,
        _evidencia(conexao, ana, operacao, primeiro, "1000"),
        _evidencia(conexao, ana, operacao, segundo, "1200"),
    )


# --- evidências ---------------------------------------------------------------------------


def test_evidencia_guarda_o_que_a_pessoa_disse_e_normaliza_a_moeda(conexao, ana):
    operacao = _operacao(conexao, ana)
    documento = _documento(conexao, ana, operacao)
    evidencia = _evidencia(conexao, ana, operacao, documento, "1234.5")
    assert evidencia is not None
    assert evidencia.moeda == "BRL"
    assert evidencia.valor_numero == Decimal("1234.5")
    assert evidencia.extraido_por == "pessoa"
    assert evidencia.estado_de_revisao == "automatico"
    assert evidencia.conferida is True


@pytest.mark.parametrize(
    "mudar",
    [
        {"metrica": "   "},
        {"periodo": ""},
        {"valor_numero": None},  # sem valor nenhum
        {"pagina": 0},
        {"moeda": "REAL"},
        {"moeda": "B1L"},
        {"metrica": "x" * 121},
    ],
)
def test_evidencia_invalida_e_recusada(conexao, ana, mudar):
    operacao = _operacao(conexao, ana)
    documento = _documento(conexao, ana, operacao)
    with pytest.raises(ValueError):
        _evidencia(conexao, ana, operacao, documento, **mudar)


def test_evidencia_so_com_valor_em_texto_vale(conexao, ana):
    operacao = _operacao(conexao, ana)
    documento = _documento(conexao, ana, operacao)
    evidencia = _evidencia(
        conexao, ana, operacao, documento, valor_numero=None, valor_texto="Big 4"
    )
    assert evidencia is not None and evidencia.valor_numero is None


def test_evidencia_de_documento_que_nao_e_da_sala_nao_entra(conexao, ana, bia):
    sala_da_ana = _operacao(conexao, ana)
    sala_da_bia = _operacao(conexao, bia)
    documento_da_bia = _documento(conexao, bia, sala_da_bia)
    # o id é de outra conta; o documento da Bia também não é desta sala
    assert _evidencia(conexao, ana, sala_da_ana, documento_da_bia) is None
    documento_da_ana = _documento(conexao, ana, sala_da_ana)
    assert _evidencia(conexao, ana, sala_da_bia, documento_da_ana) is None


def test_apagar_o_documento_leva_as_evidencias(conexao, ana):
    operacao = _operacao(conexao, ana)
    documento = _documento(conexao, ana, operacao)
    _evidencia(conexao, ana, operacao, documento)
    sala.apagar_documento(
        conexao,
        usuario_id=ana.id,
        operacao_id=operacao.id,
        documento_id=documento.id,
    )
    assert (
        sala_trabalho.listar_evidencias(
            conexao, usuario_id=ana.id, operacao_id=operacao.id
        )
        == []
    )


# --- contradições -------------------------------------------------------------------------


def test_valores_que_diferem_em_documentos_diferentes_abrem_uma_contradicao(
    conexao, ana, duas_evidencias
):
    operacao, a, b = duas_evidencias
    (contradicao,) = _contradicoes(conexao, ana, operacao)
    assert contradicao.estado == "aberta"
    assert contradicao.diferenca == Decimal(200)
    assert {contradicao.evidencia_a, contradicao.evidencia_b} == {a.id, b.id}


def test_valores_dentro_da_tolerancia_nao_abrem(conexao, ana):
    operacao = _operacao(conexao, ana)
    _evidencia(conexao, ana, operacao, _documento(conexao, ana, operacao, "a"), "1000")
    _evidencia(conexao, ana, operacao, _documento(conexao, ana, operacao, "b"), "1004")
    assert _contradicoes(conexao, ana, operacao) == []


def test_a_mesma_contradicao_nao_se_repete_a_cada_evidencia_nova(
    conexao, ana, duas_evidencias
):
    operacao, _, _ = duas_evidencias
    terceiro = _documento(conexao, ana, operacao, "c")
    _evidencia(conexao, ana, operacao, terceiro, "1000", metrica="ebitda")
    assert len(_contradicoes(conexao, ana, operacao)) == 1


def test_rejeitar_a_evidencia_fecha_a_contradicao_aberta(conexao, ana, duas_evidencias):
    operacao, _, b = duas_evidencias
    sala_trabalho.mudar_revisao_da_evidencia(
        conexao,
        usuario_id=ana.id,
        operacao_id=operacao.id,
        evidencia_id=b.id,
        estado="rejeitado",
    )
    assert _contradicoes(conexao, ana, operacao) == []
    sala_trabalho.mudar_revisao_da_evidencia(
        conexao,
        usuario_id=ana.id,
        operacao_id=operacao.id,
        evidencia_id=b.id,
        estado="automatico",
    )
    assert len(_contradicoes(conexao, ana, operacao)) == 1


def test_apagar_a_evidencia_leva_a_contradicao(conexao, ana, duas_evidencias):
    operacao, a, _ = duas_evidencias
    assert sala_trabalho.apagar_evidencia(
        conexao, usuario_id=ana.id, operacao_id=operacao.id, evidencia_id=a.id
    )
    assert _contradicoes(conexao, ana, operacao) == []


def _marcar(conexao, dono, operacao, contradicao, estado, nota):
    return sala_trabalho.mudar_contradicao(
        conexao,
        usuario_id=dono.id,
        operacao_id=operacao.id,
        contradicao_id=contradicao.id,
        estado=estado,
        nota=nota,
    )


def test_explicar_ou_descartar_exige_nota_e_o_que_foi_marcado_fica(
    conexao, ana, duas_evidencias
):
    operacao, _, b = duas_evidencias
    (contradicao,) = _contradicoes(conexao, ana, operacao)
    for estado in ("explicada", "descartada"):
        with pytest.raises(ValueError):
            _marcar(conexao, ana, operacao, contradicao, estado, "  ")
    marcada = _marcar(
        conexao, ana, operacao, contradicao, "explicada", "Uma é consolidada."
    )
    assert marcada is not None and marcada.estado == "explicada"
    # uma evidência nova refaz a regra, mas não mexe no que a pessoa já marcou
    terceiro = _documento(conexao, ana, operacao, "c")
    _evidencia(conexao, ana, operacao, terceiro, "5000")
    sala_trabalho.mudar_revisao_da_evidencia(
        conexao,
        usuario_id=ana.id,
        operacao_id=operacao.id,
        evidencia_id=b.id,
        estado="rejeitado",
    )
    explicada = [
        c for c in _contradicoes(conexao, ana, operacao) if c.id == contradicao.id
    ]
    assert explicada[0].estado == "explicada"
    assert explicada[0].nota == "Uma é consolidada."


def test_reabrir_nao_exige_nota(conexao, ana, duas_evidencias):
    operacao, _, _ = duas_evidencias
    (contradicao,) = _contradicoes(conexao, ana, operacao)
    _marcar(conexao, ana, operacao, contradicao, "descartada", "Erro de digitação.")
    reaberta = _marcar(conexao, ana, operacao, contradicao, "aberta", None)
    assert reaberta is not None and reaberta.estado == "aberta"


def test_o_banco_nao_liga_evidencias_de_salas_diferentes(conexao, ana):
    um = _operacao(conexao, ana)
    dois = _operacao(conexao, ana)
    a = _evidencia(conexao, ana, um, _documento(conexao, ana, um, "a"))
    b = _evidencia(conexao, ana, dois, _documento(conexao, ana, dois, "b"))
    with pytest.raises(sa.exc.IntegrityError):
        conexao.execute(
            sa.insert(contradicoes_da_sala).values(
                id=uuid.uuid4(),
                usuario_id=ana.id,
                operacao_id=um.id,
                evidencia_a=a.id,
                evidencia_b=b.id,
            )
        )


# --- checklist ----------------------------------------------------------------------------


def _itens(conexao, dono, operacao):
    itens = sala_trabalho.ler_checklist(
        conexao, usuario_id=dono.id, operacao_id=operacao.id
    )
    assert itens is not None
    return {i.codigo: i for i in itens}


def _mudar(conexao, dono, operacao, codigo, **mudancas):
    return sala_trabalho.mudar_item_do_checklist(
        conexao,
        usuario_id=dono.id,
        operacao_id=operacao.id,
        codigo=codigo,
        **mudancas,
    )


@pytest.mark.parametrize("tipo", ["ma", "divida", "credito", "fidc"])
def test_o_checklist_sai_do_tipo_da_operacao_tudo_pendente(conexao, ana, tipo):
    operacao = _operacao(conexao, ana, tipo)
    itens = sala_trabalho.ler_checklist(
        conexao, usuario_id=ana.id, operacao_id=operacao.id
    )
    assert [i.codigo for i in itens] == [
        i.codigo for i in checklists.itens_do_tipo(tipo)
    ]
    assert {i.estado for i in itens} == {"pendente"}


def test_ligar_documento_a_item_pendente_recebe_sozinho(conexao, ana):
    operacao = _operacao(conexao, ana)
    documento = _documento(conexao, ana, operacao)
    item = _mudar(conexao, ana, operacao, "ma_estatuto", documento_id=documento.id)
    assert item.estado == "recebido"
    assert item.documento_id == documento.id


def test_soltar_o_documento_volta_a_pendente_mas_revisado_fica(conexao, ana):
    operacao = _operacao(conexao, ana)
    documento = _documento(conexao, ana, operacao)
    _mudar(conexao, ana, operacao, "ma_estatuto", documento_id=documento.id)
    assert (
        _mudar(conexao, ana, operacao, "ma_estatuto", documento_id=None).estado
        == "pendente"
    )
    _mudar(conexao, ana, operacao, "ma_dfs", documento_id=documento.id)
    revisado = _mudar(conexao, ana, operacao, "ma_dfs", estado="revisado")
    assert revisado.estado == "revisado"
    assert (
        _mudar(conexao, ana, operacao, "ma_dfs", documento_id=None).estado == "revisado"
    )


def test_ligar_documento_nao_marca_revisado(conexao, ana):
    operacao = _operacao(conexao, ana)
    documento = _documento(conexao, ana, operacao)
    for codigo in ("ma_estatuto", "ma_dfs"):
        _mudar(conexao, ana, operacao, codigo, documento_id=documento.id)
    assert "revisado" not in {i.estado for i in _itens(conexao, ana, operacao).values()}


def test_recebido_nao_se_escolhe_a_mao(conexao, ana):
    operacao = _operacao(conexao, ana)
    with pytest.raises(ValueError):
        _mudar(conexao, ana, operacao, "ma_estatuto", estado="recebido")


def test_nota_so_muda_quando_vem_no_pedido(conexao, ana):
    operacao = _operacao(conexao, ana)
    _mudar(conexao, ana, operacao, "ma_estatuto", nota="Falta a alteração de 2024.")
    item = _mudar(conexao, ana, operacao, "ma_estatuto", estado="contestado")
    assert item.nota == "Falta a alteração de 2024."
    assert item.estado == "contestado"
    assert _mudar(conexao, ana, operacao, "ma_estatuto", nota=None).nota is None


def test_item_de_outro_tipo_ou_inexistente_nao_existe(conexao, ana):
    operacao = _operacao(conexao, ana, "ma")
    assert _mudar(conexao, ana, operacao, "fidc_regulamento", estado="revisado") is None
    assert _mudar(conexao, ana, operacao, "nao_existe", estado="revisado") is None


def test_documento_de_outra_sala_nao_liga(conexao, ana, bia):
    operacao = _operacao(conexao, ana)
    de_outra_conta = _documento(conexao, bia, _operacao(conexao, bia))
    with pytest.raises(ValueError):
        _mudar(conexao, ana, operacao, "ma_estatuto", documento_id=de_outra_conta.id)


def test_apagar_o_documento_solta_o_item_do_checklist(conexao, ana):
    operacao = _operacao(conexao, ana)
    documento = _documento(conexao, ana, operacao)
    _mudar(conexao, ana, operacao, "ma_estatuto", documento_id=documento.id)
    sala.apagar_documento(
        conexao,
        usuario_id=ana.id,
        operacao_id=operacao.id,
        documento_id=documento.id,
    )
    item = _itens(conexao, ana, operacao)["ma_estatuto"]
    assert item.estado == "pendente" and item.documento_id is None


# --- isolamento (D11) ---------------------------------------------------------------------


def test_outra_conta_nao_ve_nem_muda_nada_do_trabalho(
    conexao, ana, bia, duas_evidencias
):
    operacao, a, _ = duas_evidencias
    (contradicao,) = _contradicoes(conexao, ana, operacao)
    ids = {"usuario_id": bia.id, "operacao_id": operacao.id}
    assert sala_trabalho.listar_evidencias(conexao, **ids) == []
    assert sala_trabalho.listar_contradicoes(conexao, **ids) == []
    assert sala_trabalho.ler_checklist(conexao, **ids) is None
    assert sala_trabalho.buscar_evidencia(conexao, evidencia_id=a.id, **ids) is None
    assert (
        sala_trabalho.mudar_revisao_da_evidencia(
            conexao, evidencia_id=a.id, estado="rejeitado", **ids
        )
        is None
    )
    assert not sala_trabalho.apagar_evidencia(conexao, evidencia_id=a.id, **ids)
    assert (
        sala_trabalho.mudar_contradicao(
            conexao, contradicao_id=contradicao.id, estado="aberta", nota=None, **ids
        )
        is None
    )
    assert _mudar(conexao, bia, operacao, "ma_estatuto", estado="revisado") is None
    # nada mudou para a dona
    assert len(_contradicoes(conexao, ana, operacao)) == 1
    assert _itens(conexao, ana, operacao)["ma_estatuto"].estado == "pendente"


def test_toda_funcao_publica_recebe_conta_e_operacao_pelo_nome():
    sem_operacao = set()
    publicas = [
        (nome, funcao)
        for nome, funcao in inspect.getmembers(sala_trabalho, inspect.isfunction)
        if funcao.__module__ == sala_trabalho.__name__ and not nome.startswith("_")
    ]
    assert len(publicas) >= 8
    for nome, funcao in publicas:
        parametros = inspect.signature(funcao).parameters
        assert parametros["usuario_id"].kind is inspect.Parameter.KEYWORD_ONLY, nome
        if nome not in sem_operacao:
            assert parametros["operacao_id"].kind is inspect.Parameter.KEYWORD_ONLY, (
                nome
            )
