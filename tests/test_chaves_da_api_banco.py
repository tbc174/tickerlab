"""Organizações e chaves da API externa no banco (N7, PR 1, tarefa 1.3; plano D1 a D5, D8, D9 e D12).

Riscos do plano que estes testes pegam: (1) uma organização ver ou mexer no que é de outra; (2) chave
revogada, vencida ou de organização suspensa ainda entrar; (3) a chave vazar (banco, auditoria, log);
(4) a recusa dizer demais ou o tempo dizer demais.
"""

import hashlib
import logging
from datetime import UTC, date, datetime, timedelta

import pytest
import sqlalchemy as sa

from src import auditoria
from src import chaves_da_api as ch
from src.banco import chaves_da_api as cb
from src.banco.modelo import auditoria as tabela_da_auditoria
from src.banco.modelo import chaves_da_api, direitos_da_organizacao, organizacoes
from src.banco.usuarios import apagar_conta, entrar

AGORA = datetime(2026, 10, 22, 12, tzinfo=UTC)
HOJE = AGORA.date()
Recusa = ch.MotivoDaRecusa


@pytest.fixture
def conexao(banco):
    with banco.begin() as conexao:
        yield conexao


@pytest.fixture
def admin(conexao):
    return entrar(conexao, "g-admin-n7", "admin-n7@exemplo.com")[0]


def _organizacao(conexao, admin, nome="Alfa Gestora", **extras):
    return cb.criar_organizacao(
        conexao, nome=nome, ator_id=admin.id, agora=AGORA, **extras
    )


def _emitir(conexao, admin, organizacao, agora=AGORA):
    return cb.emitir_chave(
        conexao, organizacao_id=organizacao.id, ator_id=admin.id, agora=agora
    )


# ---------------------------------------------------------------- organização (D1)


def test_criar_organizacao_com_plano_piloto(conexao, admin):
    alfa = _organizacao(conexao, admin, cnpj="12.345.678/0001-95")
    assert alfa.nome == "Alfa Gestora"
    assert alfa.cnpj == "12345678000195"  # só os dígitos
    assert alfa.plano_da_api == "piloto"
    assert alfa.suspensa_em is None
    assert cb.buscar_organizacao(conexao, alfa.id) == alfa


@pytest.mark.parametrize("cnpj", ["123", "1234567800019", "abcdefghijklmn"])
def test_cnpj_invalido_recusado(conexao, admin, cnpj):
    with pytest.raises(cb.OrganizacaoInvalidaError):
        _organizacao(conexao, admin, cnpj=cnpj)


@pytest.mark.parametrize("nome", ["", "   ", "x" * 121])
def test_nome_invalido_recusado(conexao, admin, nome):
    with pytest.raises(cb.OrganizacaoInvalidaError):
        _organizacao(conexao, admin, nome=nome)


def test_plano_da_api_desconhecido_recusado(conexao, admin):
    with pytest.raises(cb.OrganizacaoInvalidaError):
        _organizacao(conexao, admin, plano_da_api="ouro")


def test_organizacao_nao_guarda_dado_de_pessoa(banco):
    colunas = {c["name"] for c in sa.inspect(banco).get_columns("organizacoes")}
    assert not colunas & {"email", "telefone", "contato", "responsavel", "cpf"}


# ---------------------------------------------------------------- chave (D2, D3, D5)


def test_emitir_devolve_a_chave_uma_vez_e_grava_so_o_hash(conexao, admin):
    alfa = _organizacao(conexao, admin)
    nova = _emitir(conexao, admin, alfa)
    linha = conexao.execute(sa.select(chaves_da_api)).one()
    assert nova.valor.startswith(f"tld_{nova.prefixo}_")
    assert linha.prefixo == nova.prefixo
    assert linha.hash_da_chave == hashlib.sha256(nova.valor.encode()).hexdigest()
    segredo = nova.valor.split("_", 2)[2]
    assert nova.valor not in str(tuple(linha)) and segredo not in str(tuple(linha))
    listadas = cb.listar_chaves(conexao, alfa.id)
    assert [c.prefixo for c in listadas] == [nova.prefixo]
    assert not hasattr(listadas[0], "hash_da_chave")


def test_chave_abre_o_contexto_da_organizacao_dela(conexao, admin):
    alfa = _organizacao(conexao, admin)
    nova = _emitir(conexao, admin, alfa)
    contexto = cb.conferir_chave(conexao, nova.valor, agora=AGORA)
    assert isinstance(contexto, ch.ContextoDaChave)
    assert contexto.organizacao_id == alfa.id
    assert contexto.chave_id == nova.chave_id
    assert contexto.plano_da_api == "piloto"
    assert contexto.canal.value == "api_externa"


@pytest.mark.parametrize(
    ("texto", "motivo"),
    [
        ("", Recusa.FORMATO),
        ("Bearer qualquer", Recusa.FORMATO),
        ("tld_abcdefgh_" + "a" * 43, Recusa.DESCONHECIDA),
    ],
)
def test_texto_que_nao_e_chave_de_ninguem(conexao, texto, motivo):
    assert cb.conferir_chave(conexao, texto, agora=AGORA) is motivo


def test_segredo_trocado_com_prefixo_certo_e_desconhecida(conexao, admin):
    nova = _emitir(conexao, admin, _organizacao(conexao, admin))
    trocada = nova.valor[:-1] + ("A" if nova.valor[-1] != "A" else "B")
    assert cb.conferir_chave(conexao, trocada, agora=AGORA) is Recusa.DESCONHECIDA


def test_comparacao_em_tempo_constante_nos_dois_caminhos(conexao, admin, monkeypatch):
    nova = _emitir(conexao, admin, _organizacao(conexao, admin))
    chamadas = []
    original = cb.hmac.compare_digest

    def espiao(a, b):
        chamadas.append((len(a), len(b)))
        return original(a, b)

    monkeypatch.setattr(cb.hmac, "compare_digest", espiao)
    cb.conferir_chave(conexao, nova.valor, agora=AGORA)  # prefixo existe
    cb.conferir_chave(conexao, "tld_zzzzzzzz_" + "a" * 43, agora=AGORA)  # não existe
    assert chamadas == [(ch.TAMANHO_DO_HASH, ch.TAMANHO_DO_HASH)] * 2


def test_chave_revogada_recusada_no_pedido_seguinte(conexao, admin):
    alfa = _organizacao(conexao, admin)
    nova = _emitir(conexao, admin, alfa)
    assert cb.revogar_chave(
        conexao, organizacao_id=alfa.id, chave_id=nova.chave_id, ator_id=admin.id
    )
    assert cb.conferir_chave(conexao, nova.valor, agora=AGORA) is Recusa.REVOGADA
    # revogar de novo não muda nada
    assert not cb.revogar_chave(
        conexao, organizacao_id=alfa.id, chave_id=nova.chave_id, ator_id=admin.id
    )


def test_rotacao_deixa_as_duas_valerem_por_sete_dias(conexao, admin):
    alfa = _organizacao(conexao, admin)
    antiga = _emitir(conexao, admin, alfa)
    nova = cb.rotacionar_chave(
        conexao,
        organizacao_id=alfa.id,
        chave_id=antiga.chave_id,
        ator_id=admin.id,
        agora=AGORA,
    )
    assert nova.chave_id != antiga.chave_id
    dia_6 = AGORA + timedelta(days=6)
    dia_8 = AGORA + timedelta(days=8)
    assert isinstance(
        cb.conferir_chave(conexao, antiga.valor, agora=dia_6), ch.ContextoDaChave
    )
    assert cb.conferir_chave(conexao, antiga.valor, agora=dia_8) is Recusa.VENCIDA
    assert isinstance(
        cb.conferir_chave(conexao, nova.valor, agora=dia_8), ch.ContextoDaChave
    )


def test_rotacionar_chave_revogada_nao_emite_outra(conexao, admin):
    alfa = _organizacao(conexao, admin)
    antiga = _emitir(conexao, admin, alfa)
    cb.revogar_chave(
        conexao, organizacao_id=alfa.id, chave_id=antiga.chave_id, ator_id=admin.id
    )
    with pytest.raises(cb.ChaveInexistenteError):
        cb.rotacionar_chave(
            conexao, organizacao_id=alfa.id, chave_id=antiga.chave_id, ator_id=admin.id
        )


def test_limite_de_chaves_ativas_do_plano(conexao, admin):
    alfa = _organizacao(conexao, admin)
    chaves = [_emitir(conexao, admin, alfa) for _ in range(3)]
    with pytest.raises(cb.LimiteDeChavesError):
        _emitir(conexao, admin, alfa)
    # a rotação não esbarra no limite: a antiga está de saída
    cb.rotacionar_chave(
        conexao, organizacao_id=alfa.id, chave_id=chaves[0].chave_id, ator_id=admin.id
    )
    # revogar abre a vaga
    cb.revogar_chave(
        conexao, organizacao_id=alfa.id, chave_id=chaves[1].chave_id, ator_id=admin.id
    )
    _emitir(conexao, admin, alfa)


def test_ultimo_uso_gravado_no_maximo_uma_vez_por_hora(conexao, admin):
    alfa = _organizacao(conexao, admin)
    nova = _emitir(conexao, admin, alfa)
    cb.conferir_chave(conexao, nova.valor, agora=AGORA + timedelta(minutes=1))
    cb.conferir_chave(conexao, nova.valor, agora=AGORA + timedelta(minutes=30))
    [listada] = cb.listar_chaves(conexao, alfa.id)
    assert listada.ultimo_uso == AGORA + timedelta(minutes=1)
    cb.conferir_chave(conexao, nova.valor, agora=AGORA + timedelta(hours=2))
    [listada] = cb.listar_chaves(conexao, alfa.id)
    assert listada.ultimo_uso == AGORA + timedelta(hours=2)


# ---------------------------------------------------------------- suspender (D9)


def test_organizacao_suspensa_recusa_todas_as_chaves_e_reativa(conexao, admin):
    alfa = _organizacao(conexao, admin)
    nova = _emitir(conexao, admin, alfa)
    assert cb.suspender_organizacao(
        conexao,
        organizacao_id=alfa.id,
        motivo="contrato",
        ator_id=admin.id,
        agora=AGORA,
    )
    assert (
        cb.conferir_chave(conexao, nova.valor, agora=AGORA)
        is Recusa.ORGANIZACAO_SUSPENSA
    )
    with pytest.raises(cb.OrganizacaoSuspensaError):
        _emitir(conexao, admin, alfa)
    assert cb.reativar_organizacao(conexao, organizacao_id=alfa.id, ator_id=admin.id)
    assert isinstance(
        cb.conferir_chave(conexao, nova.valor, agora=AGORA), ch.ContextoDaChave
    )
    # nada foi apagado
    assert (
        conexao.execute(
            sa.select(sa.func.count()).select_from(chaves_da_api)
        ).scalar_one()
        == 1
    )


def test_motivo_da_suspensao_e_uma_lista_fechada(conexao, admin):
    alfa = _organizacao(conexao, admin)
    with pytest.raises(ValueError, match="Motivo"):
        cb.suspender_organizacao(
            conexao, organizacao_id=alfa.id, motivo="porque sim", ator_id=admin.id
        )


def test_conceder_e_suspender_direito_sem_apagar(conexao, admin):
    alfa = _organizacao(conexao, admin)
    direito = cb.conceder_direito(
        conexao,
        organizacao_id=alfa.id,
        conjunto="cvm-dfp-itr",
        finalidade="analise",
        vigente_desde=HOJE,
        ator_id=admin.id,
    )
    assert [d.id for d in cb.direitos_vigentes(conexao, alfa.id, HOJE)] == [direito.id]
    assert cb.suspender_direito(
        conexao,
        organizacao_id=alfa.id,
        direito_id=direito.id,
        ator_id=admin.id,
        agora=AGORA,
    )
    assert cb.direitos_vigentes(conexao, alfa.id, HOJE) == []
    assert (
        conexao.execute(sa.select(direitos_da_organizacao)).one().suspenso_em
        is not None
    )
    assert cb.reativar_direito(
        conexao, organizacao_id=alfa.id, direito_id=direito.id, ator_id=admin.id
    )
    assert [d.id for d in cb.direitos_vigentes(conexao, alfa.id, HOJE)] == [direito.id]


def test_direito_fora_da_vigencia_nao_vale(conexao, admin):
    alfa = _organizacao(conexao, admin)
    cb.conceder_direito(
        conexao,
        organizacao_id=alfa.id,
        conjunto="cvm-dfp-itr",
        finalidade="credito",
        vigente_desde=date(2026, 11, 1),
        vigente_ate=date(2026, 11, 30),
        ator_id=admin.id,
    )
    assert cb.direitos_vigentes(conexao, alfa.id, date(2026, 10, 31)) == []
    assert len(cb.direitos_vigentes(conexao, alfa.id, date(2026, 11, 30))) == 1
    assert cb.direitos_vigentes(conexao, alfa.id, date(2026, 12, 1)) == []


@pytest.mark.parametrize("finalidade", ["treino", "qualquer"])
def test_direito_de_treino_ou_desconhecido_recusado(conexao, admin, finalidade):
    alfa = _organizacao(conexao, admin)
    with pytest.raises(ValueError, match="finalidade"):
        cb.conceder_direito(
            conexao,
            organizacao_id=alfa.id,
            conjunto="cvm-dfp-itr",
            finalidade=finalidade,
            vigente_desde=HOJE,
            ator_id=admin.id,
        )


def test_vigencia_ao_contrario_recusada(conexao, admin):
    alfa = _organizacao(conexao, admin)
    with pytest.raises(ValueError, match="vigência"):
        cb.conceder_direito(
            conexao,
            organizacao_id=alfa.id,
            conjunto="cvm-dfp-itr",
            finalidade="analise",
            vigente_desde=HOJE,
            vigente_ate=HOJE - timedelta(days=1),
            ator_id=admin.id,
        )


# ---------------------------------------------------------------- isolamento (risco 1)


def test_uma_organizacao_nao_mexe_no_que_e_da_outra(conexao, admin):
    alfa = _organizacao(conexao, admin)
    beta = _organizacao(conexao, admin, nome="Beta Crédito")
    chave_da_beta = _emitir(conexao, admin, beta)
    direito_da_beta = cb.conceder_direito(
        conexao,
        organizacao_id=beta.id,
        conjunto="cvm-dfp-itr",
        finalidade="analise",
        vigente_desde=HOJE,
        ator_id=admin.id,
    )
    pela_alfa = {"organizacao_id": alfa.id, "ator_id": admin.id}
    assert not cb.revogar_chave(conexao, chave_id=chave_da_beta.chave_id, **pela_alfa)
    assert not cb.suspender_direito(conexao, direito_id=direito_da_beta.id, **pela_alfa)
    with pytest.raises(cb.ChaveInexistenteError):
        cb.rotacionar_chave(conexao, chave_id=chave_da_beta.chave_id, **pela_alfa)
    assert cb.listar_chaves(conexao, alfa.id) == []
    assert cb.direitos_vigentes(conexao, alfa.id, HOJE) == []
    # a chave da Beta continua abrindo só a Beta
    contexto = cb.conferir_chave(conexao, chave_da_beta.valor, agora=AGORA)
    assert (
        isinstance(contexto, ch.ContextoDaChave) and contexto.organizacao_id == beta.id
    )
    assert len(cb.direitos_vigentes(conexao, beta.id, HOJE)) == 1


def test_banco_recusa_consumo_com_chave_de_outra_organizacao(conexao, admin):
    from src.banco.modelo import consumo_da_api

    alfa = _organizacao(conexao, admin)
    beta = _organizacao(conexao, admin, nome="Beta Crédito")
    chave_da_beta = _emitir(conexao, admin, beta)
    with pytest.raises(sa.exc.IntegrityError), conexao.begin_nested():
        conexao.execute(
            sa.insert(consumo_da_api).values(
                organizacao_id=alfa.id,
                chave_id=chave_da_beta.chave_id,
                dia=HOJE,
                canal="api_externa",
                finalidade="analise",
                conjunto="cvm-dfp-itr",
            )
        )


# ---------------------------------------------------------------- auditoria e LGPD (D12)


def test_auditoria_so_com_ids_e_prefixo(conexao, admin):
    alfa = _organizacao(conexao, admin)
    nova = _emitir(conexao, admin, alfa)
    direito = cb.conceder_direito(
        conexao,
        organizacao_id=alfa.id,
        conjunto="cvm-dfp-itr",
        finalidade="analise",
        vigente_desde=HOJE,
        ator_id=admin.id,
    )
    cb.suspender_direito(
        conexao, organizacao_id=alfa.id, direito_id=direito.id, ator_id=admin.id
    )
    nova_2 = cb.rotacionar_chave(
        conexao, organizacao_id=alfa.id, chave_id=nova.chave_id, ator_id=admin.id
    )
    cb.revogar_chave(
        conexao, organizacao_id=alfa.id, chave_id=nova_2.chave_id, ator_id=admin.id
    )
    cb.suspender_organizacao(
        conexao, organizacao_id=alfa.id, motivo="pagamento", ator_id=admin.id
    )
    cb.reativar_organizacao(conexao, organizacao_id=alfa.id, ator_id=admin.id)
    registros = conexao.execute(sa.select(tabela_da_auditoria)).all()
    acoes = {r.acao for r in registros}
    assert acoes >= {
        auditoria.ACAO_ORGANIZACAO_CRIADA,
        auditoria.ACAO_CHAVE_EMITIDA,
        auditoria.ACAO_CHAVE_ROTACIONADA,
        auditoria.ACAO_CHAVE_REVOGADA,
        auditoria.ACAO_DIREITO_CONCEDIDO,
        auditoria.ACAO_DIREITO_SUSPENSO,
        auditoria.ACAO_ORGANIZACAO_SUSPENSA,
        auditoria.ACAO_ORGANIZACAO_REATIVADA,
    }
    tudo = str([tuple(r) for r in registros])
    for chave in (nova.valor, nova_2.valor):
        assert chave not in tudo and chave.split("_", 2)[2] not in tudo
    assert "Alfa Gestora" not in tudo  # nem o nome da organização
    assert all(r.ator_id == admin.id for r in registros)


def test_chave_nunca_aparece_no_log(conexao, admin, caplog):
    caplog.set_level(logging.DEBUG)
    alfa = _organizacao(conexao, admin)
    nova = _emitir(conexao, admin, alfa)
    cb.conferir_chave(conexao, nova.valor, agora=AGORA)
    cb.conferir_chave(conexao, nova.valor[:-1] + "x", agora=AGORA)
    nova_2 = cb.rotacionar_chave(
        conexao, organizacao_id=alfa.id, chave_id=nova.chave_id, ator_id=admin.id
    )
    cb.revogar_chave(
        conexao, organizacao_id=alfa.id, chave_id=nova_2.chave_id, ator_id=admin.id
    )
    cb.conferir_chave(conexao, nova_2.valor, agora=AGORA)
    for chave in (nova.valor, nova_2.valor):
        assert chave.split("_", 2)[2] not in caplog.text


def test_apagar_a_conta_do_admin_deixa_organizacao_e_chaves(banco):
    with banco.begin() as conexao:
        admin = entrar(conexao, "g-admin-sai", "admin-sai@exemplo.com")[0]
        alfa = _organizacao(conexao, admin)
        nova = _emitir(conexao, admin, alfa)
        cb.conceder_direito(
            conexao,
            organizacao_id=alfa.id,
            conjunto="cvm-dfp-itr",
            finalidade="analise",
            vigente_desde=HOJE,
            ator_id=admin.id,
        )
        assert apagar_conta(conexao, admin.id)
        assert cb.buscar_organizacao(conexao, alfa.id) is not None
        linha = conexao.execute(sa.select(organizacoes)).one()
        assert linha.criada_por is None
        assert conexao.execute(sa.select(chaves_da_api)).one().criada_por is None
        assert isinstance(
            cb.conferir_chave(conexao, nova.valor, agora=AGORA), ch.ContextoDaChave
        )
