"""Sala de dados por operação (B-20, PR 1): operações e documentos no banco, isolados por conta.

O risco principal é uma conta ver ou mexer na sala de outra (R-09 do plano). Cada função de
`src/banco/sala.py` recebe `usuario_id` (e, quando é de uma operação, `operacao_id`) e, para outra
conta, responde como se o id não existisse (a rota devolve 404, não 403). Os testes daqui rodam em
SQLite na memória; as chaves estrangeiras compostas no PostgreSQL ficam em `test_sala_migracao.py`.
"""

import inspect
import json
import uuid
from datetime import date, timedelta

import pytest
import sqlalchemy as sa

from src import auditoria, conformidade
from src.banco import sala
from src.banco.modelo import auditoria as tabela_da_auditoria
from src.banco.modelo import (
    checklist_da_sala,
    contradicoes_da_sala,
    documentos_da_sala,
    evidencias_da_sala,
    metadata,
    operacoes,
)
from src.banco.usuarios import entrar
from src.sala import retencao

HOJE = date(2026, 10, 21)
SHA_A = "a" * 64
SHA_B = "b" * 64


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


def _operacao(conexao, dono, nome="Aquisição da Alfa", **mudar):
    return sala.criar_operacao(
        conexao, usuario_id=dono.id, tipo="ma", nome=nome, hoje=HOJE, **mudar
    )


def _documento(conexao, dono, operacao, sha=SHA_A, nome="contrato.pdf"):
    return sala.registrar_documento(
        conexao,
        usuario_id=dono.id,
        operacao_id=operacao.id,
        nome_original=nome,
        tipo="pdf",
        tamanho_bytes=1234,
        sha256=sha,
    )


def _evidencia(conexao, dono, operacao, documento, valor="100"):
    evidencia_id = uuid.uuid4()
    conexao.execute(
        sa.insert(evidencias_da_sala).values(
            id=evidencia_id,
            usuario_id=dono.id,
            operacao_id=operacao.id,
            documento_id=documento.id,
            metrica="receita_liquida",
            periodo="2025",
            valor_numero=valor,
            unidade="milhares",
            moeda="BRL",
            pagina=3,
            trecho="Receita líquida 100",
            extraido_por="pessoa",
        )
    )
    return evidencia_id


def _contradicao(conexao, dono, operacao, evidencia_a, evidencia_b):
    conexao.execute(
        sa.insert(contradicoes_da_sala).values(
            id=uuid.uuid4(),
            usuario_id=dono.id,
            operacao_id=operacao.id,
            evidencia_a=evidencia_a,
            evidencia_b=evidencia_b,
            diferenca="20",
        )
    )


def _item_do_checklist(conexao, dono, operacao, documento=None, codigo="balanco"):
    conexao.execute(
        sa.insert(checklist_da_sala).values(
            id=uuid.uuid4(),
            usuario_id=dono.id,
            operacao_id=operacao.id,
            codigo=codigo,
            estado="recebido" if documento else "pendente",
            documento_id=documento.id if documento else None,
        )
    )


def _sala_cheia(conexao, dono, nome="Aquisição da Alfa"):
    """Uma operação com dois documentos, duas evidências, uma contradição e o checklist."""
    operacao = _operacao(conexao, dono, nome=nome)
    primeiro = _documento(conexao, dono, operacao, SHA_A)
    segundo = _documento(conexao, dono, operacao, SHA_B, nome="laudo.pdf")
    a = _evidencia(conexao, dono, operacao, primeiro, "100")
    b = _evidencia(conexao, dono, operacao, segundo, "120")
    _contradicao(conexao, dono, operacao, a, b)
    _item_do_checklist(conexao, dono, operacao, primeiro)
    return operacao


def _donos(conexao, tabela):
    return set(conexao.execute(sa.select(tabela.c.usuario_id)).scalars())


TABELAS_DA_SALA = (
    operacoes,
    documentos_da_sala,
    evidencias_da_sala,
    contradicoes_da_sala,
    checklist_da_sala,
)


# --- prazos de guarda (regra pura) -------------------------------------------------------


def test_prazo_padrao_e_de_180_dias_e_so_aceita_90_180_ou_365():
    assert retencao.prazo_inicial(HOJE) == HOJE + timedelta(days=180)
    assert retencao.prazo_inicial(HOJE, 90) == HOJE + timedelta(days=90)
    with pytest.raises(ValueError):
        retencao.prazo_inicial(HOJE, 30)


def test_encerrar_deixa_30_dias_para_baixar_a_sala():
    assert retencao.prazo_ao_encerrar(HOJE) == HOJE + timedelta(days=30)


def test_prorrogar_vai_ate_365_dias_por_vez_e_nunca_encurta():
    atual = HOJE + timedelta(days=100)
    assert retencao.prazo_prorrogado(atual, HOJE, 365) == HOJE + timedelta(days=365)
    assert retencao.prazo_prorrogado(atual, HOJE, 10) == atual
    for dias in (0, 366):
        with pytest.raises(ValueError):
            retencao.prazo_prorrogado(atual, HOJE, dias)


# --- operações ----------------------------------------------------------------------------


def test_criar_operacao_aberta_com_prazo_e_sem_chave_ainda(conexao, ana):
    operacao = _operacao(conexao, ana, nome="  Dívida da Beta  ")
    assert operacao.nome == "Dívida da Beta"
    assert operacao.situacao == "aberta"
    assert operacao.retencao_ate == HOJE + timedelta(days=180)
    assert not hasattr(operacao, "chave_cifrada")  # a chave nunca sai do banco
    assert sala.listar_operacoes(conexao, usuario_id=ana.id) == [operacao]


@pytest.mark.parametrize(
    "mudar",
    [{"tipo": "imovel"}, {"nome": "   "}, {"nome": "x" * 201}, {"prazo_em_dias": 30}],
)
def test_criar_operacao_recusa_dado_invalido(conexao, ana, mudar):
    dados = {"tipo": "ma", "nome": "Alfa", "prazo_em_dias": 180} | mudar
    with pytest.raises(ValueError):
        sala.criar_operacao(conexao, usuario_id=ana.id, hoje=HOJE, **dados)


def test_encerrar_e_prorrogar_mudam_o_prazo(conexao, ana):
    operacao = _operacao(conexao, ana)
    encerrada = sala.encerrar_operacao(
        conexao, usuario_id=ana.id, operacao_id=operacao.id, hoje=HOJE
    )
    assert encerrada.situacao == "encerrada"
    assert encerrada.retencao_ate == HOJE + timedelta(days=30)
    prorrogada = sala.prorrogar_operacao(
        conexao, usuario_id=ana.id, operacao_id=operacao.id, dias=365, hoje=HOJE
    )
    assert prorrogada.retencao_ate == HOJE + timedelta(days=365)


def test_encerrar_de_novo_nao_mexe_no_prazo(conexao, ana):
    operacao = _operacao(conexao, ana)
    sala.encerrar_operacao(
        conexao, usuario_id=ana.id, operacao_id=operacao.id, hoje=HOJE
    )
    depois = sala.encerrar_operacao(
        conexao,
        usuario_id=ana.id,
        operacao_id=operacao.id,
        hoje=HOJE + timedelta(days=20),
    )
    assert depois.retencao_ate == HOJE + timedelta(days=30)


def test_apagar_operacao_leva_documentos_evidencias_contradicoes_e_checklist(
    conexao, ana
):
    operacao = _sala_cheia(conexao, ana)
    assert sala.apagar_operacao(conexao, usuario_id=ana.id, operacao_id=operacao.id)
    for tabela in TABELAS_DA_SALA:
        assert _donos(conexao, tabela) == set(), tabela.name
    assert not sala.apagar_operacao(conexao, usuario_id=ana.id, operacao_id=operacao.id)


# --- documentos ---------------------------------------------------------------------------


def test_registrar_documento_na_fila_e_listar(conexao, ana):
    operacao = _operacao(conexao, ana)
    documento = _documento(conexao, ana, operacao)
    assert documento.situacao == "na_fila"
    assert documento.operacao_id == operacao.id
    assert sala.listar_documentos(
        conexao, usuario_id=ana.id, operacao_id=operacao.id
    ) == [documento]


def test_mesmo_arquivo_duas_vezes_na_sala_e_recusado_mas_em_outra_sala_entra(
    conexao, ana
):
    alfa = _operacao(conexao, ana)
    beta = _operacao(conexao, ana, nome="Beta")
    _documento(conexao, ana, alfa)
    with pytest.raises(sala.DocumentoRepetidoError):
        _documento(conexao, ana, alfa)
    assert _documento(conexao, ana, beta) is not None


@pytest.mark.parametrize(
    "mudar",
    [
        {"tipo": "exe"},
        {"tamanho_bytes": 0},
        {"sha256": "curto"},
        {"nome_original": ""},
    ],
)
def test_registrar_documento_recusa_dado_invalido(conexao, ana, mudar):
    operacao = _operacao(conexao, ana)
    dados = {
        "nome_original": "a.pdf",
        "tipo": "pdf",
        "tamanho_bytes": 10,
        "sha256": SHA_A,
    } | mudar
    with pytest.raises(ValueError):
        sala.registrar_documento(
            conexao, usuario_id=ana.id, operacao_id=operacao.id, **dados
        )


def test_apagar_documento_leva_as_evidencias_e_solta_o_checklist(conexao, ana):
    operacao = _sala_cheia(conexao, ana)
    # o documento ligado ao checklist (a ordem da lista empata no mesmo instante de chegada)
    primeiro_id = conexao.execute(
        sa.select(checklist_da_sala.c.documento_id)
    ).scalar_one()
    primeiro = next(
        d
        for d in sala.listar_documentos(
            conexao, usuario_id=ana.id, operacao_id=operacao.id
        )
        if d.id == primeiro_id
    )
    assert sala.apagar_documento(
        conexao, usuario_id=ana.id, operacao_id=operacao.id, documento_id=primeiro.id
    )
    documentos = set(conexao.execute(sa.select(evidencias_da_sala.c.documento_id)))
    assert (primeiro.id,) not in documentos
    assert conexao.execute(sa.select(contradicoes_da_sala)).first() is None
    item = conexao.execute(sa.select(checklist_da_sala)).one()
    assert item.documento_id is None and item.estado == "pendente"


# --- isolamento entre contas (R-09) -------------------------------------------------------


def test_outra_conta_nao_ve_nem_mexe_na_operacao(conexao, ana, bia):
    operacao = _sala_cheia(conexao, ana)
    de_bia = {"usuario_id": bia.id, "operacao_id": operacao.id}
    assert sala.listar_operacoes(conexao, usuario_id=bia.id) == []
    assert sala.buscar_operacao(conexao, **de_bia) is None
    assert sala.encerrar_operacao(conexao, **de_bia, hoje=HOJE) is None
    assert sala.prorrogar_operacao(conexao, **de_bia, dias=90, hoje=HOJE) is None
    assert sala.apagar_operacao(conexao, **de_bia) is False
    assert sala.listar_documentos(conexao, **de_bia) == []
    # e a sala da Ana continua como estava
    da_ana = sala.buscar_operacao(conexao, usuario_id=ana.id, operacao_id=operacao.id)
    assert da_ana.situacao == "aberta"
    assert (
        len(sala.listar_documentos(conexao, usuario_id=ana.id, operacao_id=operacao.id))
        == 2
    )
    assert _donos(conexao, operacoes) == {ana.id}


def test_outra_conta_nao_poe_nem_apaga_documento_na_sala_alheia(conexao, ana, bia):
    operacao = _operacao(conexao, ana)
    documento = _documento(conexao, ana, operacao)
    assert _documento(conexao, bia, operacao, SHA_B) is None
    assert not sala.apagar_documento(
        conexao, usuario_id=bia.id, operacao_id=operacao.id, documento_id=documento.id
    )
    # nem trocando a operação: o documento da Ana pelo id dele, numa sala da Bia
    sala_da_bia = _operacao(conexao, bia)
    assert not sala.apagar_documento(
        conexao,
        usuario_id=bia.id,
        operacao_id=sala_da_bia.id,
        documento_id=documento.id,
    )
    # nem a própria Ana apaga pela sala errada
    outra_da_ana = _operacao(conexao, ana, nome="Beta")
    assert not sala.apagar_documento(
        conexao,
        usuario_id=ana.id,
        operacao_id=outra_da_ana.id,
        documento_id=documento.id,
    )
    assert _donos(conexao, documentos_da_sala) == {ana.id}


def test_banco_recusa_documento_de_uma_conta_na_operacao_de_outra(conexao, ana, bia):
    operacao = _operacao(conexao, ana)
    with pytest.raises(sa.exc.IntegrityError):
        conexao.execute(
            sa.insert(documentos_da_sala).values(
                id=uuid.uuid4(),
                usuario_id=bia.id,
                operacao_id=operacao.id,
                nome_original="x.pdf",
                tipo="pdf",
                tamanho_bytes=1,
                sha256=SHA_A,
            )
        )


def test_contradicao_nao_liga_duas_salas(conexao, ana):
    alfa = _operacao(conexao, ana)
    beta = _operacao(conexao, ana, nome="Beta")
    a = _evidencia(conexao, ana, alfa, _documento(conexao, ana, alfa))
    b = _evidencia(conexao, ana, beta, _documento(conexao, ana, beta))
    with pytest.raises(sa.exc.IntegrityError):
        _contradicao(conexao, ana, alfa, a, b)


def test_toda_funcao_publica_pede_a_conta_e_a_operacao_pelo_nome():
    """Inspeção: ninguém chama uma função da sala sem dizer de quem é (nem por posição)."""
    sem_operacao = {"criar_operacao", "listar_operacoes", "dados_para_exportar"}
    publicas = [
        (nome, funcao)
        for nome, funcao in inspect.getmembers(sala, inspect.isfunction)
        if funcao.__module__ == sala.__name__ and not nome.startswith("_")
    ]
    assert len(publicas) >= 9
    for nome, funcao in publicas:
        parametros = inspect.signature(funcao).parameters
        assert parametros["usuario_id"].kind is inspect.Parameter.KEYWORD_ONLY, nome
        if nome not in sem_operacao:
            assert parametros["operacao_id"].kind is inspect.Parameter.KEYWORD_ONLY, (
                nome
            )


# --- auditoria só com ids (R-18) ----------------------------------------------------------


def test_auditoria_da_sala_guarda_so_ids_tamanho_e_tipo(conexao, ana):
    operacao = _operacao(conexao, ana, nome="Projeto Fulana")
    documento = _documento(conexao, ana, operacao, nome="Laudo da Fulana.pdf")
    sala.apagar_documento(
        conexao, usuario_id=ana.id, operacao_id=operacao.id, documento_id=documento.id
    )
    sala.apagar_operacao(conexao, usuario_id=ana.id, operacao_id=operacao.id)
    registros = conexao.execute(
        sa.select(tabela_da_auditoria).order_by(tabela_da_auditoria.c.criado_em)
    ).all()
    assert [r.acao for r in registros] == [
        auditoria.ACAO_OPERACAO_CRIADA,
        auditoria.ACAO_DOCUMENTO_ENVIADO,
        auditoria.ACAO_DOCUMENTO_APAGADO,
        auditoria.ACAO_OPERACAO_APAGADA,
    ]
    assert {r.ator_id for r in registros} == {ana.id}
    texto = json.dumps([dict(r.detalhes) for r in registros])
    assert "Fulana" not in texto and SHA_A not in texto
    assert registros[1].detalhes == {
        "operacao_id": str(operacao.id),
        "tipo": "pdf",
        "tamanho_bytes": 1234,
    }


def test_acoes_novas_da_auditoria_tem_nomes_unicos():
    acoes = [
        auditoria.ACAO_OPERACAO_CRIADA,
        auditoria.ACAO_DOCUMENTO_ENVIADO,
        auditoria.ACAO_DOCUMENTO_RECUSADO,
        auditoria.ACAO_DOCUMENTO_BAIXADO,
        auditoria.ACAO_DOCUMENTO_APAGADO,
        auditoria.ACAO_OPERACAO_APAGADA,
        auditoria.ACAO_OPERACAO_EXPIRADA,
        auditoria.ACAO_OPERACAO_ENCERRADA,
        auditoria.ACAO_OPERACAO_PRORROGADA,
        auditoria.ACAO_SALA_BAIXADA,
    ]
    assert len(set(acoes)) == len(acoes)


def _acoes_da_auditoria(conexao, *acoes):
    return conexao.execute(
        sa.select(tabela_da_auditoria)
        .where(tabela_da_auditoria.c.acao.in_(acoes))
        .order_by(tabela_da_auditoria.c.criado_em)
    ).all()


def test_encerrar_e_prorrogar_gravam_a_acao_com_ids_e_datas(conexao, ana):
    operacao = _operacao(conexao, ana, nome="Projeto Fulana")
    sala.encerrar_operacao(
        conexao, usuario_id=ana.id, operacao_id=operacao.id, hoje=HOJE
    )
    sala.prorrogar_operacao(
        conexao, usuario_id=ana.id, operacao_id=operacao.id, dias=90, hoje=HOJE
    )
    encerrou, prorrogou = _acoes_da_auditoria(
        conexao, auditoria.ACAO_OPERACAO_ENCERRADA, auditoria.ACAO_OPERACAO_PRORROGADA
    )
    assert (encerrou.ator_id, encerrou.alvo_id) == (ana.id, operacao.id)
    assert encerrou.detalhes == {"retencao_ate": str(HOJE + timedelta(days=30))}
    assert (prorrogou.ator_id, prorrogou.alvo_id) == (ana.id, operacao.id)
    assert prorrogou.detalhes == {
        "dias": 90,
        "retencao_ate": str(HOJE + timedelta(days=90)),
    }
    assert "Fulana" not in json.dumps(
        [dict(encerrou.detalhes), dict(prorrogou.detalhes)]
    )


def test_encerrar_de_novo_nao_grava_outra_acao(conexao, ana):
    operacao = _operacao(conexao, ana)
    for _ in range(2):
        sala.encerrar_operacao(
            conexao, usuario_id=ana.id, operacao_id=operacao.id, hoje=HOJE
        )
    assert len(_acoes_da_auditoria(conexao, auditoria.ACAO_OPERACAO_ENCERRADA)) == 1


def test_encerrar_e_prorrogar_de_outra_conta_nao_gravam_nada(conexao, ana, bia):
    operacao = _operacao(conexao, ana)
    de_bia = {"usuario_id": bia.id, "operacao_id": operacao.id}
    sala.encerrar_operacao(conexao, **de_bia, hoje=HOJE)
    sala.prorrogar_operacao(conexao, **de_bia, dias=90, hoje=HOJE)
    assert not _acoes_da_auditoria(
        conexao, auditoria.ACAO_OPERACAO_ENCERRADA, auditoria.ACAO_OPERACAO_PRORROGADA
    )


def test_se_a_auditoria_falha_a_mudanca_nao_fica(conexao, ana, monkeypatch):
    operacao = _operacao(conexao, ana)

    def falha(*_, **__):
        raise RuntimeError("auditoria fora do ar")

    monkeypatch.setattr(sala.auditoria, "registrar", falha)
    with pytest.raises(RuntimeError), conexao.begin_nested():
        sala.encerrar_operacao(
            conexao, usuario_id=ana.id, operacao_id=operacao.id, hoje=HOJE
        )
    monkeypatch.undo()
    atual = sala.buscar_operacao(conexao, usuario_id=ana.id, operacao_id=operacao.id)
    assert atual.situacao == "aberta"
    assert not _acoes_da_auditoria(conexao, auditoria.ACAO_OPERACAO_ENCERRADA)


# --- LGPD: exportar e apagar a conta ------------------------------------------------------


def test_exportar_leva_a_sala_sem_chave_nem_nonce_e_so_da_pessoa(conexao, ana, bia):
    _sala_cheia(conexao, ana)
    _sala_cheia(conexao, bia, nome="Sala da Bia")
    conexao.execute(
        sa.update(operacoes).values(chave_cifrada=b"CHAVE-SECRETA", versao_da_chave=1)
    )
    conexao.execute(sa.update(documentos_da_sala).values(nonce=b"NONCE-SECRETO"))
    dados = conformidade.exportar_meus_dados(conexao, ana.id)
    (operacao,) = dados["sala_de_dados"]
    assert operacao["nome"] == "Aquisição da Alfa"
    assert "chave_cifrada" not in operacao and "versao_da_chave" not in operacao
    assert len(operacao["documentos"]) == 2
    assert {d["nome_original"] for d in operacao["documentos"]} == {
        "contrato.pdf",
        "laudo.pdf",
    }
    assert "nonce" not in operacao["documentos"][0]
    assert {e["valor_numero"] for e in operacao["evidencias"]} == {"100", "120"}
    assert len(operacao["contradicoes"]) == 1
    assert [i["codigo"] for i in operacao["checklist"]] == ["balanco"]
    texto = json.dumps(dados)  # tudo vira JSON (datas e números decimais também)
    assert "SECRET" not in texto and "Sala da Bia" not in texto


def test_exportar_sem_sala_traz_lista_vazia(conexao, ana):
    assert conformidade.exportar_meus_dados(conexao, ana.id)["sala_de_dados"] == []


def test_apagar_conta_leva_a_sala_inteira_e_so_a_da_pessoa(conexao, ana, bia):
    _sala_cheia(conexao, ana)
    _sala_cheia(conexao, bia, nome="Sala da Bia")
    assert conformidade.apagar_conta(conexao, ana.id) is True
    for tabela in TABELAS_DA_SALA:
        assert _donos(conexao, tabela) == {bia.id}, tabela.name


def test_toda_coluna_da_sala_ou_sai_no_exportar_ou_esta_na_lista_do_que_nao_sai():
    """Coluna nova numa tabela da sala quebra este teste até alguém decidir se ela sai."""
    campos_da_operacao = set(sala.Operacao.__dataclass_fields__)
    for tabela in (operacoes, *TABELAS_DA_SALA[1:]):
        colunas = set(tabela.c.keys())
        saem = set(sala.COLUNAS_EXPORTADAS.get(tabela.name, campos_da_operacao))
        nao_saem = sala.COLUNAS_QUE_NAO_SAEM[tabela.name]
        assert saem | nao_saem == colunas, tabela.name
        assert not saem & nao_saem, tabela.name


def test_exportar_traz_exatamente_as_colunas_da_lista(conexao, ana):
    _sala_cheia(conexao, ana)
    (operacao,) = conformidade.exportar_meus_dados(conexao, ana.id)["sala_de_dados"]
    partes = {
        "documentos": "documentos_da_sala",
        "evidencias": "evidencias_da_sala",
        "contradicoes": "contradicoes_da_sala",
        "checklist": "checklist_da_sala",
    }
    for chave, tabela in partes.items():
        for linha in operacao[chave]:
            assert tuple(linha) == sala.COLUNAS_EXPORTADAS[tabela], chave
    assert set(operacao) - set(partes) == set(sala.Operacao.__dataclass_fields__)


# --- chave, nonce e leitura (PR 2) --------------------------------------------------------


def test_chave_da_operacao_e_gravada_uma_vez_e_so_para_a_dona(conexao, ana, bia):
    operacao = _operacao(conexao, ana)
    da_ana = {"usuario_id": ana.id, "operacao_id": operacao.id}
    da_bia = {"usuario_id": bia.id, "operacao_id": operacao.id}
    assert not sala.guardar_chave_da_operacao(
        conexao, **da_bia, chave_cifrada=b"da-bia", versao_da_chave=1
    )
    assert sala.chave_da_operacao(conexao, **da_ana) is None
    assert sala.guardar_chave_da_operacao(
        conexao, **da_ana, chave_cifrada=b"primeira", versao_da_chave=1
    )
    assert not sala.guardar_chave_da_operacao(
        conexao, **da_ana, chave_cifrada=b"segunda", versao_da_chave=2
    )
    assert sala.chave_da_operacao(conexao, **da_ana) == (b"primeira", 1)
    assert sala.chave_da_operacao(conexao, **da_bia) is None


def test_nonce_e_leitura_so_mexem_no_documento_da_conta(conexao, ana, bia):
    operacao = _operacao(conexao, ana)
    documento = _documento(conexao, ana, operacao)
    do_documento = {"operacao_id": operacao.id, "documento_id": documento.id}
    assert not sala.guardar_nonce(
        conexao, usuario_id=bia.id, **do_documento, nonce=b"n" * 12
    )
    assert sala.nonce_do_documento(conexao, usuario_id=ana.id, **do_documento) is None
    assert sala.guardar_nonce(
        conexao, usuario_id=ana.id, **do_documento, nonce=b"n" * 12
    )
    assert (
        sala.nonce_do_documento(conexao, usuario_id=ana.id, **do_documento) == b"n" * 12
    )
    assert sala.nonce_do_documento(conexao, usuario_id=bia.id, **do_documento) is None
    leitura = {"situacao": "lido", "paginas": 3, "lido_por": "teste"}
    assert not sala.marcar_leitura(
        conexao, usuario_id=bia.id, **do_documento, **leitura
    )
    assert sala.buscar_documento(conexao, usuario_id=bia.id, **do_documento) is None
    assert sala.marcar_leitura(conexao, usuario_id=ana.id, **do_documento, **leitura)
    lido = sala.buscar_documento(conexao, usuario_id=ana.id, **do_documento)
    assert (lido.situacao, lido.paginas, lido.lido_por) == ("lido", 3, "teste")


def test_marcar_leitura_so_aceita_o_resultado_de_uma_leitura(conexao, ana):
    operacao = _operacao(conexao, ana)
    documento = _documento(conexao, ana, operacao)
    with pytest.raises(ValueError, match="Situação"):
        sala.marcar_leitura(
            conexao,
            usuario_id=ana.id,
            operacao_id=operacao.id,
            documento_id=documento.id,
            situacao="na_fila",
            paginas=None,
            lido_por="teste",
        )
