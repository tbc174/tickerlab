"""A base em pasta versionada (linha 1099, parte a, passo 1: só o código da API; desenho aceito pela Diretoria em 26/11).

No formato novo, `<acervo>/base` é um link simbólico RELATIVO para `versoes/<carimbo>`, que o recebedor troca numa
operação só (como o acervo de pessoa). A versão apontada nunca é regravada. A porta dona resolve o link uma vez e
monta as views no caminho resolvido; `porta_do_pedido` descobre a troca pelo destino do link (sem a impressão de
todos os arquivos). Um pedido que cruza a troca termina inteiro na versão em que começou; o seguinte abre na nova.

O formato antigo (`base` é pasta de verdade) continua como hoje, com a trava da troca (parte b) de pé: o código entra
antes do recebedor novo e lê os dois.

Este PC não cria link simbólico sem privilégio: os testes da lógica injetam o destino do link
(`_versao_da_base`); os com link de verdade rodam onde o sistema deixa criar (o CI) e pulam aqui. Base de mentira,
sem internet.
"""

import os
import shutil
from pathlib import Path

import pytest
from fastapi import HTTPException

from base.porta import Porta
from src.api_externa import porta_compartilhada as compartilhada
from src.api_externa import rotas
from src.api_externa.conjuntos import empresas
from tests import test_api_externa_e_empresa as listas_de_mentira
from tests import test_api_externa_retrato_guardado as guardado
from tests import test_api_externa_trava_da_troca as trava

NOVA = trava.NOVA  # só está na versão nova


def _versoes(raiz: Path) -> tuple[Path, Path]:
    """Duas versões da base: a de antes (sem a NOVA) e a nova (com a NOVA no retrato de 2026-11)."""
    velha = raiz / "versoes" / "20261125-0830"
    guardado._gravar_listas(velha)
    nova = raiz / "versoes" / "20261126-0830"
    shutil.copytree(velha, nova)
    trava._retrato_novo_com_a_nova(nova)
    return velha, nova


class _Link:
    """O destino do link `base`, trocável no meio do teste (o `mv -T` do recebedor)."""

    def __init__(self, destino: Path) -> None:
        self.destino = destino

    def __call__(self, pasta: Path) -> Path:
        return self.destino


@pytest.fixture
def versionada(tmp_path, monkeypatch):
    raiz = tmp_path / "acervo_api"
    velha, nova = _versoes(raiz)
    link = _Link(velha)
    compartilhada.zerar()
    monkeypatch.setattr(compartilhada, "_pasta_da_base", lambda: raiz / "base")
    monkeypatch.setattr(compartilhada, "_versao_da_base", link)
    monkeypatch.setattr(rotas, "abrir_porta", compartilhada.porta_do_pedido)
    yield link, velha, nova
    compartilhada.zerar()


def test_a_porta_abre_no_caminho_resolvido_da_versao(versionada):
    _, velha, _ = versionada
    with rotas._porta(None) as porta:
        assert Path(porta.pasta) == velha
        assert empresas.e_empresa(porta, listas_de_mentira.EMPRESA)


def test_o_link_trocado_no_meio_do_pedido_termina_inteiro_na_versao_de_antes(
    versionada, monkeypatch
):
    """O cenário do Revisor no #1329, no formato novo: a troca cai logo depois de achar o mês das duas listas,
    antes da consulta que o usa. O pedido responde inteiro pela versão de antes (a NOVA não está nela), sem 503;
    o seguinte abre na versão nova e a aceita."""
    link, velha, nova = versionada
    achar_o_mes = empresas._retrato_das_duas_listas
    trocou: list[str] = []

    def achar_e_trocar(porta):
        mes = achar_o_mes(porta)
        if not trocou:
            link.destino = nova
            trocou.append(mes)
        return mes

    monkeypatch.setattr(empresas, "_retrato_das_duas_listas", achar_e_trocar)
    with rotas._porta(None) as porta:
        assert not empresas.e_empresa(
            porta, NOVA
        )  # a resposta certa da versão de antes
        assert Path(porta.pasta) == velha
    assert trocou == [guardado.NOVO]
    monkeypatch.setattr(empresas, "_retrato_das_duas_listas", achar_o_mes)
    with rotas._porta(None) as porta:
        assert Path(porta.pasta) == nova
        assert empresas.e_empresa(porta, NOVA)


def test_a_mesma_versao_nao_abre_a_porta_de_novo(versionada, monkeypatch):
    aberturas: list[Path | None] = []
    abrir = compartilhada.abrir_a_base

    def contar(pasta=None):
        aberturas.append(pasta)
        return abrir(pasta)

    monkeypatch.setattr(compartilhada, "abrir_a_base", contar)
    link, velha, nova = versionada
    for _ in range(3):
        with rotas._porta(None) as porta:
            empresas.e_empresa(porta, listas_de_mentira.EMPRESA)
    link.destino = nova
    with rotas._porta(None) as porta:
        empresas.e_empresa(porta, listas_de_mentira.EMPRESA)
    assert aberturas == [velha, nova]


def test_no_formato_versionado_a_descoberta_nao_le_os_arquivos_da_base(
    versionada, monkeypatch
):
    """A troca se descobre pelo destino do link: nem o começo nem o fim do pedido tiram a impressão de todos os
    arquivos (custava de 6,5 a 9,7 ms por vez no servidor, duas por pedido; linha 1100)."""

    def proibida(*_args, **_kwargs):
        raise AssertionError("impressão da base inteira no formato versionado")

    monkeypatch.setattr(compartilhada, "impressao_da_base", proibida)
    real = compartilhada._impressao

    def so_de_tabelas(pasta, arquivos):
        if (
            len(arquivos) > 2
        ):  # o `lembrar` confere uma ou duas tabelas; a base inteira é proibida
            proibida()
        return real(pasta, arquivos)

    monkeypatch.setattr(compartilhada, "_impressao", so_de_tabelas)
    link, _, nova = versionada
    with rotas._porta(None) as porta:
        assert empresas.e_empresa(porta, listas_de_mentira.EMPRESA)
    link.destino = nova
    with rotas._porta(None) as porta:
        assert empresas.e_empresa(porta, NOVA)


def test_a_porta_aberta_enquanto_o_link_troca_le_so_a_versao_que_resolveu(
    versionada, monkeypatch
):
    """O link troca entre a leitura do destino e a abertura: a porta abre no caminho que resolveu (a versão de
    antes, que o recebedor guarda como `anterior`), e o pedido seguinte abre na nova."""
    link, velha, nova = versionada
    abrir = compartilhada.abrir_a_base

    def trocar_e_abrir(pasta=None):
        link.destino = nova
        return abrir(pasta)

    monkeypatch.setattr(compartilhada, "abrir_a_base", trocar_e_abrir)
    with rotas._porta(None) as porta:
        assert Path(porta.pasta) == velha
        assert not empresas.e_empresa(porta, NOVA)
    monkeypatch.setattr(compartilhada, "abrir_a_base", abrir)
    with rotas._porta(None) as porta:
        assert Path(porta.pasta) == nova


def test_a_memoria_da_versao_velha_nao_serve_a_nova(versionada):
    link, _, nova = versionada
    with rotas._porta(None) as porta:
        assert empresas._retrato_das_duas_listas(porta) == guardado.NOVO
    link.destino = nova
    with rotas._porta(None) as porta:
        assert empresas._retrato_das_duas_listas(porta) == guardado.NOVISSIMO


# ---------------------------------------------------------------- o formato antigo continua como hoje


def test_pasta_de_verdade_nao_e_versao(tmp_path):
    pasta = tmp_path / "base"
    pasta.mkdir()
    assert compartilhada._versao_da_base(pasta) is None


def test_no_formato_antigo_a_trava_da_troca_continua(trava_listas):
    """Sem link, a troca no mesmo caminho no meio do pedido continua dando o 503 da parte (b)."""
    with pytest.raises(HTTPException) as erro, rotas._porta(None) as porta:
        empresas.e_empresa(porta, listas_de_mentira.EMPRESA)
        trava._retrato_novo_com_a_nova(trava_listas)
    trava._base_em_atualizacao(erro)


@pytest.fixture
def trava_listas(tmp_path, monkeypatch):
    """A base como pasta de verdade, com o `_versao_da_base` de verdade (o formato de hoje)."""
    pasta = tmp_path / "base"
    guardado._gravar_listas(pasta)
    compartilhada.zerar()
    monkeypatch.setattr(compartilhada, "_pasta_da_base", lambda: pasta)
    monkeypatch.setattr(
        compartilhada, "abrir_a_base", lambda versao=None: Porta(versao or pasta)
    )
    monkeypatch.setattr(rotas, "abrir_porta", compartilhada.porta_do_pedido)
    yield pasta
    compartilhada.zerar()


def test_no_formato_antigo_sem_troca_o_pedido_responde(trava_listas):
    with rotas._porta(None) as porta:
        assert empresas.e_empresa(porta, listas_de_mentira.EMPRESA)


# ---------------------------------------------------------------- com link de verdade (onde o sistema deixa)


def _sem_link_simbolico(pasta: Path) -> bool:
    try:
        os.symlink("x", pasta / ".teste-de-link", target_is_directory=True)
    except (OSError, NotImplementedError):
        return True
    (pasta / ".teste-de-link").unlink()
    return False


def _apontar(raiz: Path, versao: Path) -> None:
    """O `mv -T` do recebedor: link novo ao lado e rename por cima do `base` (uma operação só)."""
    novo = raiz / ".novo"
    os.symlink(os.path.relpath(versao, raiz), novo, target_is_directory=True)
    os.replace(novo, raiz / "base")


@pytest.fixture
def com_link(tmp_path, monkeypatch):
    raiz = tmp_path / "acervo_api"
    raiz.mkdir()
    if _sem_link_simbolico(raiz):
        pytest.skip("este sistema não cria link simbólico sem privilégio (o CI cria)")
    velha, nova = _versoes(raiz)
    _apontar(raiz, velha)
    compartilhada.zerar()
    monkeypatch.setattr(compartilhada, "_pasta_da_base", lambda: raiz / "base")
    monkeypatch.setattr(rotas, "abrir_porta", compartilhada.porta_do_pedido)
    yield raiz, velha, nova
    compartilhada.zerar()


def test_com_link_de_verdade_a_versao_e_o_destino_resolvido(com_link):
    raiz, velha, _ = com_link
    assert os.readlink(raiz / "base") == os.path.join("versoes", velha.name)  # relativo
    assert compartilhada._versao_da_base(raiz / "base") == Path(os.path.realpath(velha))


def test_com_link_de_verdade_a_troca_no_meio_do_pedido_nao_mistura(com_link):
    raiz, velha, nova = com_link
    with rotas._porta(None) as porta:
        assert Path(porta.pasta) == Path(os.path.realpath(velha))
        _apontar(raiz, nova)
        assert not empresas.e_empresa(porta, NOVA)
    with rotas._porta(None) as porta:
        assert Path(porta.pasta) == Path(os.path.realpath(nova))
        assert empresas.e_empresa(porta, NOVA)


# ---------------------------------------------------------------- a transição e o link errado


@pytest.fixture
def transicao(tmp_path, monkeypatch):
    """A virada do formato: `base` começa pasta de verdade e vira link (e volta)."""
    raiz = tmp_path / "acervo_api"
    velha, nova = _versoes(raiz)
    antiga = raiz / "base"
    shutil.copytree(velha, antiga)
    link = _Link(None)
    compartilhada.zerar()
    monkeypatch.setattr(compartilhada, "_pasta_da_base", lambda: antiga)
    monkeypatch.setattr(compartilhada, "_versao_da_base", link)
    monkeypatch.setattr(
        compartilhada, "abrir_a_base", lambda versao=None: Porta(versao or antiga)
    )
    monkeypatch.setattr(rotas, "abrir_porta", compartilhada.porta_do_pedido)
    yield link, antiga, nova
    compartilhada.zerar()


def test_a_virada_de_pasta_para_link_e_de_volta_reabre_a_porta(transicao):
    link, antiga, nova = transicao
    with rotas._porta(None) as porta:
        assert Path(porta.pasta) == antiga
        assert not empresas.e_empresa(porta, NOVA)
    link.destino = nova  # a virada: `base` passa a ser link para a versão nova
    with rotas._porta(None) as porta:
        assert Path(porta.pasta) == nova
        assert empresas.e_empresa(porta, NOVA)
    link.destino = None  # o desfazer do formato: pasta de verdade de novo
    with rotas._porta(None) as porta:
        assert Path(porta.pasta) == antiga
        assert not empresas.e_empresa(porta, NOVA)


@pytest.mark.parametrize("fora", ["acervo_pessoa/atual", "versoes/../outra"])
def test_versao_fora_de_versoes_responde_fora_do_ar(versionada, fora):
    """Um link que resolve fora de `<acervo>/versoes` (absoluto, com `..`, ou para o acervo de pessoa) não abre
    porta: 503 sem dizer onde, como a base ausente."""
    link, velha, _ = versionada
    destino = velha.parent.parent / fora
    destino.mkdir(parents=True)
    link.destino = destino
    with pytest.raises(HTTPException) as erro, rotas._porta(None):
        pass
    assert (erro.value.status_code, erro.value.detail) == (503, "service_unavailable")


def test_link_pendurado_responde_fora_do_ar_e_nao_guarda_porta_vazia(versionada):
    """O link aponta para uma versão que não existe (o recebedor quebrou): 503, e nenhuma porta vazia fica como
    dona; quando o link volta a uma versão de verdade, o pedido seguinte abre nela."""
    link, velha, _ = versionada
    link.destino = velha.parent / "20261127-0830"  # não existe
    with pytest.raises(HTTPException) as erro, rotas._porta(None):
        pass
    assert (erro.value.status_code, erro.value.detail) == (503, "service_unavailable")
    link.destino = velha
    with rotas._porta(None) as porta:
        assert empresas.e_empresa(porta, listas_de_mentira.EMPRESA)
