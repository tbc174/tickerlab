"""A cifra da sala de dados (B-20, PR 2): AES-256-GCM, uma chave por operação, presa aos ids."""

import base64
import uuid

import pytest

from src.sala import cofre


@pytest.fixture(autouse=True)
def chave_mestra(monkeypatch):
    valor = cofre.gerar_chave_mestra()
    monkeypatch.setenv(cofre.VARIAVEL_DA_CHAVE_MESTRA, valor)
    return valor


OPERACAO = uuid.uuid4()
DOCUMENTO = uuid.uuid4()
IDS = {"operacao_id": OPERACAO, "documento_id": DOCUMENTO, "parte": "original"}


def _chave():
    chave, _, _ = cofre.nova_chave_da_operacao(OPERACAO)
    return chave


def test_cifra_e_decifra_e_o_arquivo_nao_tem_o_texto():
    chave = _chave()
    cifrado = cofre.cifrar_documento(chave, b"balanco confidencial", **IDS)
    assert b"confidencial" not in cifrado
    assert cofre.decifrar_documento(chave, cifrado, **IDS) == b"balanco confidencial"


def test_cada_cifra_tem_nonce_novo():
    chave = _chave()
    nonces = {
        cofre.nonce_de(cofre.cifrar_documento(chave, b"x", **IDS)) for _ in range(50)
    }
    assert len(nonces) == 50
    assert all(len(nonce) == cofre.BYTES_DO_NONCE for nonce in nonces)


@pytest.mark.parametrize(
    "outro",
    [
        {"operacao_id": uuid.uuid4()},  # o arquivo copiado para outra sala
        {"documento_id": uuid.uuid4()},  # trocado com outro documento da mesma sala
        {"parte": "texto"},  # o original posto no lugar do texto
    ],
)
def test_o_arquivo_so_abre_na_sala_no_documento_e_na_parte_dele(outro):
    chave = _chave()
    cifrado = cofre.cifrar_documento(chave, b"x", **IDS)
    with pytest.raises(cofre.CifraInvalidaError):
        cofre.decifrar_documento(chave, cifrado, **(IDS | outro))


def test_arquivo_adulterado_ou_cortado_nao_abre():
    chave = _chave()
    cifrado = bytearray(cofre.cifrar_documento(chave, b"conteudo", **IDS))
    cifrado[-1] ^= 1
    with pytest.raises(cofre.CifraInvalidaError):
        cofre.decifrar_documento(chave, bytes(cifrado), **IDS)
    with pytest.raises(cofre.CifraInvalidaError):
        cofre.decifrar_documento(chave, bytes(cifrado[:5]), **IDS)


def test_a_chave_de_outra_operacao_nao_abre():
    cifrado = cofre.cifrar_documento(_chave(), b"x", **IDS)
    with pytest.raises(cofre.CifraInvalidaError):
        cofre.decifrar_documento(_chave(), cifrado, **IDS)


def test_a_chave_da_operacao_volta_pela_chave_mestra_e_so_para_a_operacao_dela():
    chave, embrulhada, versao = cofre.nova_chave_da_operacao(OPERACAO)
    assert versao == 1 and chave not in embrulhada
    assert cofre.abrir_chave_da_operacao(embrulhada, versao, OPERACAO) == chave
    with pytest.raises(cofre.CifraInvalidaError):
        cofre.abrir_chave_da_operacao(embrulhada, versao, uuid.uuid4())


def test_a_chave_embrulhada_nao_abre_como_arquivo():
    """Usos separados da mesma chave: o que é chave nunca decifra como documento."""
    mestra = cofre.chaves_mestras()[1]
    _, embrulhada, _ = cofre.nova_chave_da_operacao(OPERACAO)
    with pytest.raises(cofre.CifraInvalidaError):
        cofre.decifrar_documento(mestra, embrulhada, **IDS)


def test_outra_chave_mestra_nao_abre(monkeypatch):
    _, embrulhada, versao = cofre.nova_chave_da_operacao(OPERACAO)
    monkeypatch.setenv(cofre.VARIAVEL_DA_CHAVE_MESTRA, cofre.gerar_chave_mestra())
    with pytest.raises(cofre.CifraInvalidaError):
        cofre.abrir_chave_da_operacao(embrulhada, versao, OPERACAO)


def test_troca_da_chave_mestra_sem_recifrar(monkeypatch, chave_mestra):
    chave_antiga, embrulhada_antiga, versao_antiga = cofre.nova_chave_da_operacao(
        OPERACAO
    )
    nova = "v2:" + cofre.gerar_chave_mestra().removeprefix("v1:")
    monkeypatch.setenv(cofre.VARIAVEL_DA_CHAVE_MESTRA, f"{nova},{chave_mestra}")
    assert cofre.abrir_chave_da_operacao(
        embrulhada_antiga, versao_antiga, OPERACAO
    ) == (chave_antiga)
    _, _, versao_nova = cofre.nova_chave_da_operacao(OPERACAO)
    assert versao_nova == 2
    monkeypatch.setenv(cofre.VARIAVEL_DA_CHAVE_MESTRA, nova)  # a v1 saiu cedo demais
    with pytest.raises(cofre.ChaveDaSalaAusenteError):
        cofre.abrir_chave_da_operacao(embrulhada_antiga, versao_antiga, OPERACAO)


@pytest.mark.parametrize(
    "valor",
    [
        "",
        "   ",
        "abc",
        "v1:nao-e-base64!",
        "v1:" + base64.b64encode(b"curta").decode(),
        "v0:" + base64.b64encode(b"x" * 32).decode(),
        "v1:{0},v1:{0}".format(base64.b64encode(b"x" * 32).decode()),
    ],
)
def test_chave_mestra_ausente_ou_fora_do_formato(monkeypatch, valor):
    monkeypatch.setenv(cofre.VARIAVEL_DA_CHAVE_MESTRA, valor)
    with pytest.raises(cofre.ChaveDaSalaAusenteError) as erro:
        cofre.nova_chave_da_operacao(OPERACAO)
    assert valor.strip() == "" or valor.split(":")[-1] not in str(
        erro.value
    )  # nem um pedaço


def test_sem_a_variavel_avisa_qual_configurar(monkeypatch):
    monkeypatch.delenv(cofre.VARIAVEL_DA_CHAVE_MESTRA)
    with pytest.raises(
        cofre.ChaveDaSalaAusenteError, match=cofre.VARIAVEL_DA_CHAVE_MESTRA
    ):
        cofre.chaves_mestras()


def test_chave_mestra_gerada_tem_32_bytes_e_o_formato_da_variavel():
    valor = cofre.gerar_chave_mestra()
    assert valor.startswith("v1:")
    assert len(cofre.chaves_mestras(valor)[1]) == cofre.BYTES_DA_CHAVE
    assert cofre.gerar_chave_mestra() != valor


def test_parte_desconhecida_e_erro_de_programa():
    with pytest.raises(ValueError, match="Parte"):
        cofre.cifrar_documento(_chave(), b"x", **(IDS | {"parte": "../x"}))
