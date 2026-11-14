"""Comparar empresas na tela do analista (linha 798, PR 2): `src/analista/comparacao.py`.

De dois a cinco CNPJs lado a lado. Cada um passa pela ficha (o mesmo leitor e o mesmo portão da API externa); o
porte, a abertura, a atividade, a UF, o município, o capital e os estabelecimentos vêm do leitor da busca, lido
só para quem a ficha serviu. Riscos que estes testes pegam:

1. pessoa física na tela: o MEI sai `nao_disponivel`, igual a um CNPJ que não existe, e nada da busca sai dele
   (na base de teste o CNPJ do MEI tem linha nas tabelas da busca: a ficha é quem barra);
2. a tela mostrar mais que a API: sem prontidão nada sai; campo que o portão nega some;
3. pedido fora da regra: menos de dois, mais de cinco, CNPJ inválido ou repetido;
4. olhar o futuro: vale o retrato da busca já público no dia.

Base de mentira, sem internet: a da ficha (`test_api_externa_por_cnpj_ficha.py`) com as tabelas da busca
(`test_api_externa_prospeccao.py`) na mesma pasta.
"""

import dataclasses
import shutil

import pytest

from base import prontidao
from base.porta import Porta
from base.prontidao import Prontidao, Prova
from src import portao_externo as portao
from src.analista import comparacao, leitura
from src.api_externa.conjuntos import empresas, ficha, prospeccao
from tests import test_api_externa_empresas as empresas_de_mentira
from tests import test_api_externa_por_cnpj_ficha as ficha_de_mentira
from tests import test_api_externa_prospeccao as busca_de_mentira

HOJE = (
    empresas_de_mentira.AGORA.date()
)  # 10/11/2026: vale o retrato de outubro da busca
EMPRESA = empresas_de_mentira.EMPRESA
MEI = empresas_de_mentira.MEI
INEXISTENTE = empresas_de_mentira.INEXISTENTE
TABELAS_DA_FICHA = (*empresas.TABELAS, ficha.TABELA_DAS_ENTREGAS)
TABELAS_DA_BUSCA = (prospeccao.ESTABELECIMENTOS, prospeccao.EMPRESAS)


def _regras(tabelas=(*TABELAS_DA_FICHA, *TABELAS_DA_BUSCA)) -> portao.Regras:
    prova = Prova(HOJE, "conferida no teste", "teste")
    versoes = prontidao.versoes_maiores()
    return dataclasses.replace(
        portao.regras_vigentes(),
        prontidao={t: Prontidao(versoes[t], prova, prova, prova) for t in tabelas},
    )


def base_de_teste(tmp_path):
    """A base da ficha com as tabelas da busca na mesma pasta (os testes da rota usam a mesma)."""
    pasta = ficha_de_mentira._base(tmp_path, ficha_de_mentira._rotulos())
    busca_de_mentira._gravar(
        pasta, prospeccao.ESTABELECIMENTOS, busca_de_mentira._estabelecimentos()
    )
    # a lista sem pessoa é uma só: a da busca substitui a que a base da ficha gravou (linha 861)
    shutil.rmtree(pasta / prospeccao.EMPRESAS)
    busca_de_mentira._gravar(pasta, prospeccao.EMPRESAS, busca_de_mentira._empresas())
    return pasta


@pytest.fixture
def pasta(tmp_path):
    return base_de_teste(tmp_path)


def _comparar(pasta, cnpjs, regras=None):
    with Porta(pasta) as porta:
        return comparacao.comparar(porta, cnpjs, hoje=HOJE, regras=regras or _regras())


def _por_cnpj(resposta) -> dict[str, dict]:
    return {empresa["cnpj"]: empresa for empresa in resposta.corpo["empresas"]}


# ---------------------------------------------------------------- o que sai


def test_cada_empresa_traz_o_cadastro_da_ficha_e_os_campos_da_busca(pasta):
    resposta = _comparar(pasta, [EMPRESA, INEXISTENTE])
    assert resposta.estado == leitura.PRONTA
    assert resposta.corpo["como_era_em"] == HOJE.isoformat()
    empresa = _por_cnpj(resposta)[EMPRESA]
    assert empresa["estado"] == leitura.PRONTA
    with Porta(pasta) as porta:
        da_ficha = leitura.ficha(porta, EMPRESA, hoje=HOJE, regras=_regras())
    cadastro = da_ficha.corpo["cadastro_na_receita"]
    # o cadastro é o da ficha, campo a campo, sem tradução
    for nome, valor in cadastro.items():
        assert empresa[nome] == valor
    # da busca, o retrato de outubro (o de hoje): a UF mudou para MG e o capital para 6 milhões
    assert empresa["uf"]["valor"] == "MG"
    assert empresa["capital_social"]["valor"] == 6_000_000.0
    assert empresa["n_estabelecimentos"]["valor"] == 1
    assert empresa["data_inicio_atividade"]["valor"] == "2010-05-01"
    assert empresa["cnae_principal"]["fonte"] == prospeccao.FONTE
    assert empresa["porte"]["valor"] == "other"  # o código de fora; o nome vem ao lado
    assert empresa["porte_descricao"]
    # o nome ao lado do código, como na busca
    assert empresa["cnae_descricao"]
    # o que a ficha e a busca têm, sai da ficha; o CNPJ não se repete
    assert empresa["razao_social"] == cadastro["razao_social"]
    assert list(empresa).count("cnpj") == 1
    assert {f["fonte"] for f in resposta.fontes} >= {"rfb-cnpj"}


def test_a_ordem_e_a_do_pedido_e_o_cnpj_sai_sem_pontuacao(pasta):
    formatado = empresas_de_mentira._formatado(EMPRESA)
    resposta = _comparar(pasta, [INEXISTENTE, formatado])
    assert [e["cnpj"] for e in resposta.corpo["empresas"]] == [INEXISTENTE, EMPRESA]


def test_entregas_a_cvm_viram_a_ultima_entrega_e_a_conta_dos_atrasos(pasta):
    empresa = _por_cnpj(_comparar(pasta, [EMPRESA, INEXISTENTE]))[EMPRESA]
    with Porta(pasta) as porta:
        entregas = leitura.ficha(porta, EMPRESA, hoje=HOJE, regras=_regras()).corpo[
            "entregas"
        ]
    ultima = entregas[0]  # a ficha vem da mais nova à mais velha
    assert empresa["ultima_entrega_documento"] == ultima["documento"]
    assert empresa["ultima_entrega_referencia"] == ultima["referencia"]
    assert empresa["ultima_entrega_situacao"] == ultima["situacao_da_entrega"]
    assert empresa["entregas_conhecidas"] == len(entregas)
    com_atraso = [
        e
        for e in entregas
        if e["situacao_da_entrega"]["valor"] in comparacao.SITUACOES_COM_ATRASO
    ]
    assert empresa["entregas_com_atraso"] == len(com_atraso)


def test_limites_dizem_o_que_a_comparacao_nao_e(pasta):
    limites = _comparar(pasta, [EMPRESA, INEXISTENTE]).corpo["limites"]
    assert limites == list(comparacao.LIMITES)
    texto = " ".join(limites)
    assert "zona cinzenta" in texto
    assert "nenhum dos dois mede faturamento" in texto
    assert "known_at" not in texto


# ---------------------------------------------------------------- risco 1: pessoa fora


@pytest.mark.parametrize(
    "cnpj",
    [
        empresas_de_mentira.MEI,
        empresas_de_mentira.EMPRESARIO_INDIVIDUAL,
        empresas_de_mentira.FORA_DA_REDE,
        empresas_de_mentira.FUNDO,
    ],
)
def test_pessoa_e_quem_nao_e_empresa_saem_iguais_a_um_cnpj_que_nao_existe(pasta, cnpj):
    resposta = _por_cnpj(_comparar(pasta, [cnpj, INEXISTENTE]))
    assert resposta[cnpj] == {"cnpj": cnpj, "estado": leitura.NAO_DISPONIVEL}
    assert resposta[INEXISTENTE] == {
        "cnpj": INEXISTENTE,
        "estado": leitura.NAO_DISPONIVEL,
    }


def test_o_mei_tem_linha_na_busca_e_nem_chega_a_ela(pasta, monkeypatch):
    """A base de teste põe o CNPJ do MEI nas tabelas da busca: a ficha barra antes de a busca ser lida."""
    assert MEI in {linha[0] for linha in busca_de_mentira.ESTABELECIMENTOS}
    pedidos: list[tuple[str, ...]] = []
    buscar = prospeccao.LeitorDeProspeccao.buscar

    def espiao(self, busca, como_era_em):
        pedidos.append(busca.cnpjs)
        return buscar(self, busca, como_era_em)

    monkeypatch.setattr(prospeccao.LeitorDeProspeccao, "buscar", espiao)
    resposta = _comparar(pasta, [EMPRESA, MEI])
    assert _por_cnpj(resposta)[MEI] == {"cnpj": MEI, "estado": leitura.NAO_DISPONIVEL}
    assert pedidos == [(EMPRESA,)]


def test_so_pessoa_nao_le_a_busca(pasta, monkeypatch):
    def proibido(*_args):
        raise AssertionError("a busca não pode ser lida sem empresa servida pela ficha")

    monkeypatch.setattr(prospeccao.LeitorDeProspeccao, "buscar", proibido)
    resposta = _comparar(pasta, [MEI, INEXISTENTE])
    assert resposta.estado == leitura.PRONTA
    assert all(
        e["estado"] == leitura.NAO_DISPONIVEL for e in resposta.corpo["empresas"]
    )


# ---------------------------------------------------------------- risco 2: o portão e a prontidão


def test_sem_prontidao_sai_nao_liberada_sem_dizer_nada_dos_cnpjs(pasta):
    sem = dataclasses.replace(portao.regras_vigentes(), prontidao={})
    assert _comparar(pasta, [EMPRESA, MEI], regras=sem) == leitura.Resposta(
        leitura.NAO_LIBERADA
    )


def test_sem_prontidao_da_busca_o_cadastro_continua_e_os_campos_dela_somem(pasta):
    resposta = _comparar(pasta, [EMPRESA, INEXISTENTE], _regras(TABELAS_DA_FICHA))
    empresa = _por_cnpj(resposta)[EMPRESA]
    assert empresa["estado"] == leitura.PRONTA
    assert "situacao_cadastral" in empresa
    for nome in comparacao.CAMPOS_DA_BUSCA:
        assert nome not in empresa


def test_sem_prontidao_das_entregas_o_resumo_some(pasta):
    regras = _regras((*empresas.TABELAS, *TABELAS_DA_BUSCA))
    empresa = _por_cnpj(_comparar(pasta, [EMPRESA, INEXISTENTE], regras))[EMPRESA]
    assert not any(nome.startswith("ultima_entrega") for nome in empresa)
    assert "entregas_conhecidas" not in empresa and "entregas_com_atraso" not in empresa


# ---------------------------------------------------------------- risco 3: o pedido


@pytest.mark.parametrize(
    "cnpjs",
    [
        [],
        [EMPRESA],
        [EMPRESA, "123"],
        [EMPRESA, empresas_de_mentira._formatado(EMPRESA)],  # o mesmo, com pontuação
        [
            EMPRESA,
            MEI,
            INEXISTENTE,
            "11111111000272",
            "22222222000191",
            "44444444000191",
        ],
    ],
)
def test_pedido_fora_da_regra_e_erro_de_quem_chama(pasta, cnpjs):
    with pytest.raises(comparacao.PedidoInvalido):
        _comparar(pasta, cnpjs)


def test_pedido_invalido_e_value_error_e_decide_antes_do_portao(pasta):
    sem = dataclasses.replace(portao.regras_vigentes(), prontidao={})
    with pytest.raises(ValueError):
        _comparar(pasta, [EMPRESA], regras=sem)


# ---------------------------------------------------------------- tipos simples


def test_corpo_vira_json(pasta):
    import json

    resposta = _comparar(pasta, [EMPRESA, MEI])
    json.dumps(resposta.corpo)
    json.dumps(resposta.fontes)
