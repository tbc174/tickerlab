"""A medida de uso do conector (linha 901): uma linha por chamada, sem argumento, sem pessoa e sem erro.

Riscos: a linha de uso levar ao disco do VPS o que o analista digitou (um nome, um CNPJ), a mensagem de erro
(que repete o pedido) ou a chave inteira; uma chamada passar sem linha; a linha não sair no contêiner.
"""

import io
import json
import logging

import httpx
import pytest

from conector_remoto import uso
from conector_remoto.ferramentas import CONJUNTOS_DA_FERRAMENTA
from tests import ajudantes_do_conector as aj

CNPJ = "11111111000191"
EMPRESA = {"cnpj": CNPJ, "legal_name": {"value": "ALFA TECNOLOGIA S.A."}}
CAMPOS = {"evento", "hora", "ferramenta", "resultado", "duracao_ms", "chave"}
ID_DA_CHAVE = "tld_abcdefgh"


@pytest.fixture
def linhas(caplog):
    """As linhas de uso gravadas no teste, já lidas do JSON."""
    caplog.set_level(
        logging.INFO, logger="conector_remoto"
    )  # o uso e os demais registros do conector

    def ler() -> list[dict]:
        return [
            json.loads(r.getMessage())
            for r in caplog.records
            if r.name == uso.registro_de_uso.name
        ]

    return ler


@pytest.fixture
def registro_limpo():
    """Devolve o registro de uso como estava (o `ligar_registro_de_uso` mexe nele)."""
    antes = (
        list(uso.registro_de_uso.handlers),
        uso.registro_de_uso.level,
        uso.registro_de_uso.propagate,
    )
    yield
    uso.registro_de_uso.handlers[:] = antes[0]
    uso.registro_de_uso.setLevel(antes[1])
    uso.registro_de_uso.propagate = antes[2]


def _do_conector(caplog) -> str:
    """O texto gravado pelos registros do conector.

    O httpx e o SDK do MCP também registram em INFO (a URL com o CNPJ, o nome da ferramenta recusada); no
    contêiner a raiz fica em WARNING e eles não saem, mas na suíte inteira outro teste pode baixar a raiz para
    INFO. A medida aqui é a do conector.
    """
    return "\n".join(
        r.getMessage() for r in caplog.records if r.name.startswith("conector_remoto")
    )


def _conector(rotas=None, conjuntos=None):
    argumentos = {"conjuntos": conjuntos} if conjuntos else {}
    return aj.conector(aj.api_de_mentira(rotas or {}, **argumentos))


def test_chamada_que_deu_certo_vira_uma_linha_so_com_os_campos_da_medida(
    linhas, caplog
):
    rotas = {f"/companies/{CNPJ}": httpx.Response(200, json=EMPRESA)}
    with _conector(rotas) as cliente:
        aj.chamar_ok(cliente, aj.CHAVE_DE_MENTIRA, "ficha_da_empresa", cnpj=CNPJ)
    (linha,) = linhas()
    assert set(linha) == CAMPOS
    assert linha["evento"] == uso.EVENTO
    assert linha["ferramenta"] == "ficha_da_empresa"
    assert linha["resultado"] == "ok"
    assert linha["chave"] == ID_DA_CHAVE
    assert isinstance(linha["duracao_ms"], int) and linha["duracao_ms"] >= 0
    # nem o argumento, nem a resposta, nem a chave inteira
    assert CNPJ not in _do_conector(caplog)
    assert "ALFA" not in _do_conector(caplog)
    assert aj.CHAVE_DE_MENTIRA not in _do_conector(caplog)


def test_erro_da_api_vira_resultado_erro_sem_a_mensagem(linhas):
    with _conector() as cliente:
        erro, texto = aj.chamar(cliente, aj.CHAVE_DE_MENTIRA, "setor", chave="energia")
    assert erro
    (linha,) = linhas()
    assert linha["ferramenta"] == "setor"
    assert linha["resultado"] == "erro"
    assert texto not in json.dumps(linha, ensure_ascii=False)


def test_parametro_invalido_nao_leva_o_que_foi_digitado_ao_log(linhas, caplog):
    digitado = "TEXTO DIGITADO PELO ANALISTA"
    with _conector() as cliente:
        erro, _ = aj.chamar(
            cliente, aj.CHAVE_DE_MENTIRA, "buscar_empresas", limite=digitado
        )
    assert erro
    (linha,) = linhas()
    assert linha["resultado"] == "erro"
    assert digitado not in _do_conector(caplog)


def test_ferramenta_que_a_chave_nao_ve_vira_recusada(linhas):
    with _conector(conjuntos=("financials",)) as cliente:
        erro, _ = aj.chamar(cliente, aj.CHAVE_DE_MENTIRA, "vinculos", cnpj=CNPJ)
    assert erro
    (linha,) = linhas()
    assert linha["ferramenta"] == "vinculos"
    assert linha["resultado"] == "recusada"
    assert linha["chave"] == ID_DA_CHAVE


def test_nome_inventado_vira_desconhecida_e_nao_vai_ao_log(linhas, caplog):
    inventado = "FULANO_DE_TAL"
    with _conector() as cliente:
        erro, _ = aj.chamar(cliente, aj.CHAVE_DE_MENTIRA, inventado)
    assert erro
    (linha,) = linhas()
    assert linha["ferramenta"] == uso.FERRAMENTA_DESCONHECIDA
    assert linha["resultado"] == "recusada"
    assert inventado not in _do_conector(caplog)


def test_lista_de_ferramentas_nao_conta_como_chamada(linhas):
    with _conector() as cliente:
        aj.nomes_das_ferramentas(cliente, aj.CHAVE_DE_MENTIRA)
    assert linhas() == []


def test_toda_ferramenta_registrada_tem_nome_na_medida():
    # a medida reconhece pelo mapa de conjuntos: ferramenta nova fora dele sairia como "desconhecida"
    with _conector() as cliente:
        nomes = aj.nomes_das_ferramentas(cliente, aj.CHAVE_DE_MENTIRA)
    assert set(nomes) == set(CONJUNTOS_DA_FERRAMENTA)


@pytest.mark.usefixtures("registro_limpo")
def test_ligar_o_registro_escreve_uma_linha_de_json_por_chamada():
    saida = io.StringIO()
    uso.ligar_registro_de_uso(saida)
    uso.ligar_registro_de_uso(saida)  # ligar de novo não duplica a linha
    uso.registrar_chamada("setores", uso.Resultado.OK, 0.0123, ID_DA_CHAVE)
    (texto,) = saida.getvalue().splitlines()
    linha = json.loads(texto)
    assert set(linha) == CAMPOS
    assert linha["duracao_ms"] == 12
    assert uso.registro_de_uso.propagate is False
