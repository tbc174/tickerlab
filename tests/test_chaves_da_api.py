"""Regras da chave da API externa, sem banco (N7, PR 1, tarefa 1.1; plano D2, D6 e D7).

A chave tem o formato `tld_<prefixo>_<segredo>`: o prefixo (8 caracteres, não é segredo) acha a linha
no banco; o banco guarda só o SHA-256 da chave inteira. O contexto que a chave abre é sempre o da API
externa: não há como ele dizer `api_interna`.
"""

import dataclasses
import hashlib
import re

import pytest
from hypothesis import given
from hypothesis import strategies as st

from src import chaves_da_api as ch
from src.banco.modelo import FINALIDADES_DA_ORGANIZACAO, PLANOS_DA_API
from src.planos import LIMITES_DA_API, limites_da_api
from src.portao_externo import Canal, Finalidade

FORMATO = re.compile(r"^tld_[a-z2-7]{8}_[A-Za-z0-9_-]{43}$")


def test_gerar_chave_no_formato_e_com_o_prefixo_dentro():
    prefixo, chave = ch.gerar_chave()
    assert FORMATO.match(chave)
    assert chave.startswith(f"tld_{prefixo}_")
    assert ch.separar(chave) == prefixo


def test_duas_chaves_nunca_iguais():
    chaves = {ch.gerar_chave()[1] for _ in range(200)}
    assert len(chaves) == 200


@pytest.mark.parametrize(
    "texto",
    [
        "",
        "tld_",
        "tld_abcdefgh",
        "tld_abcdefgh_",
        "tld_ABCDEFGH_" + "a" * 43,  # prefixo em maiúsculas
        "tld_abcdefg1_" + "a" * 43,  # 1 não é base32
        "tld_abcdefgh_" + "a" * 42,
        "tld_abcdefgh_" + "a" * 44,
        "xyz_abcdefgh_" + "a" * 43,
        " tld_abcdefgh_" + "a" * 43,
        "tld_abcdefgh_" + "a" * 42 + "!",
        "tld_abcdefgh_" + "a" * 5000,
    ],
)
def test_separar_recusa_o_que_nao_e_chave(texto):
    assert ch.separar(texto) is None


@given(st.text(max_size=80))
def test_separar_nunca_quebra(texto):
    resultado = ch.separar(texto)
    assert resultado is None or FORMATO.match(texto)


def test_hash_e_o_sha256_da_chave_inteira():
    _, chave = ch.gerar_chave()
    assert ch.hash_da_chave(chave) == hashlib.sha256(chave.encode()).hexdigest()
    assert len(ch.hash_da_chave(chave)) == ch.TAMANHO_DO_HASH


def test_chave_nova_nao_mostra_o_valor_no_repr():
    prefixo, chave = ch.gerar_chave()
    nova = ch.ChaveNova(chave_id=ch.uuid.uuid4(), prefixo=prefixo, valor=chave)
    assert chave not in repr(nova)
    assert chave not in str(nova)
    assert prefixo in repr(nova)


def test_contexto_da_chave_e_sempre_da_api_externa():
    campos = {campo.name for campo in dataclasses.fields(ch.ContextoDaChave)}
    assert "canal" not in campos  # não há como construir um contexto de outro canal
    contexto = ch.ContextoDaChave(
        organizacao_id=ch.uuid.uuid4(),
        chave_id=ch.uuid.uuid4(),
        prefixo="abcdefgh",
        plano_da_api="piloto",
    )
    assert contexto.canal is Canal.API_EXTERNA
    with pytest.raises(dataclasses.FrozenInstanceError):
        contexto.canal = Canal.API_INTERNA  # type: ignore[misc]


def test_organizacao_nunca_recebe_a_finalidade_de_treino():
    assert set(FINALIDADES_DA_ORGANIZACAO) == {
        Finalidade.ANALISE.value,
        Finalidade.CREDITO.value,
    }
    assert Finalidade.TREINO.value not in FINALIDADES_DA_ORGANIZACAO


def test_motivos_da_recusa_sao_uma_lista_fechada():
    assert {m.value for m in ch.MotivoDaRecusa} == {
        "formato",
        "desconhecida",
        "revogada",
        "vencida",
        "organizacao_suspensa",
    }


def test_limites_do_plano_piloto():
    piloto = limites_da_api("piloto")
    assert piloto.pedidos_por_minuto == 60
    assert piloto.pedidos_por_mes == 10_000
    assert piloto.linhas_por_resposta == 1_000
    assert piloto.chaves_ativas == 3


def test_plano_da_api_desconhecido_vale_o_mais_restrito():
    assert (
        limites_da_api("nao-existe") == limites_da_api(None) == limites_da_api("piloto")
    )


def test_todo_plano_da_api_do_banco_tem_limites():
    assert set(LIMITES_DA_API) == set(PLANOS_DA_API)


def test_pre_lancamento_nao_mexe_na_quota_da_api(monkeypatch):
    monkeypatch.setattr("src.planos.TUDO_LIBERADO_NO_PRE_LANCAMENTO", True)
    assert limites_da_api("piloto").pedidos_por_mes == 10_000
