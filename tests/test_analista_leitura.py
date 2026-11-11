"""A leitura da tela do analista (linha 798): `src/analista/leitura.py`.

A tela mostra exatamente o que a API externa mostraria, sem o contrato da organização: o mesmo leitor
(`LeitorDeFicha`) e o mesmo portão, com as mesmas regras e a mesma prontidão. Riscos que estes testes pegam:

1. pessoa física na tela (MEI e empresário individual saem "não disponível", igual a um CNPJ que não existe);
2. a tela mostrar mais que a API (campo negado pelo portão some; sem prontidão nada sai);
3. consulta divergente (o corpo é o do leitor da API, sem tradução e sem campo a mais).

Base de mentira, sem internet: a mesma de `test_api_externa_por_cnpj_ficha.py`.
"""

import dataclasses
from datetime import date

import pytest

from base import prontidao
from base.porta import Porta
from base.prontidao import Prontidao, Prova
from src import portao_externo as portao
from src.analista import leitura
from src.api_externa.conjuntos import empresas, ficha
from tests import test_api_externa_empresas as empresas_de_mentira
from tests import test_api_externa_por_cnpj_ficha as ficha_de_mentira

AGORA = empresas_de_mentira.AGORA
HOJE = AGORA.date()
EMPRESA = empresas_de_mentira.EMPRESA
TABELAS_DA_FICHA = (*empresas.TABELAS, ficha.TABELA_DAS_ENTREGAS)


def _regras(tabelas=TABELAS_DA_FICHA) -> portao.Regras:
    """As regras de verdade, com as tabelas pedidas prontas (provas do D10) no dia do teste."""
    prova = Prova(HOJE, "conferida no teste", "teste")
    versoes = prontidao.versoes_maiores()
    return dataclasses.replace(
        portao.regras_vigentes(),
        prontidao={t: Prontidao(versoes[t], prova, prova, prova) for t in tabelas},
    )


def _sem_prontidao() -> portao.Regras:
    return dataclasses.replace(portao.regras_vigentes(), prontidao={})


@pytest.fixture
def pasta(tmp_path):
    return ficha_de_mentira._base(tmp_path, ficha_de_mentira._rotulos())


def _ficha(pasta, cnpj: str = EMPRESA, regras=None, como_era_em=None):
    with Porta(pasta) as porta:
        return leitura.ficha(
            porta,
            cnpj,
            hoje=HOJE,
            como_era_em=como_era_em,
            regras=regras or _regras(),
        )


# ---------------------------------------------------------------- o que sai


def test_ficha_pronta_traz_o_corpo_do_leitor_da_api_e_as_fontes(pasta):
    resposta = _ficha(pasta)
    assert resposta.estado == leitura.PRONTA
    with Porta(pasta) as porta:
        da_api = ficha.LeitorDeFicha(
            porta, leitura.permitido_na_tela(ficha.CONJUNTO, HOJE, _regras())
        ).ficha(EMPRESA, HOJE)
    assert da_api is not None
    # risco 3: o mesmo corpo, sem tradução nem campo a mais; só os limites são os da tela
    assert resposta.corpo == {**da_api.corpo, "limites": list(leitura.LIMITES)}
    assert resposta.linhas == da_api.linhas
    assert {f["fonte"] for f in resposta.fontes} == da_api.fontes
    assert resposta.corpo["cadastro_na_receita"]["razao_social"]["fonte"] == "rfb-cnpj"
    assert resposta.corpo["entregas"]


def test_ficha_aceita_o_cnpj_com_pontuacao(pasta):
    formatado = empresas_de_mentira._formatado(EMPRESA)
    assert _ficha(pasta, cnpj=formatado).corpo["cnpj"] == EMPRESA


def test_como_era_em_corta_o_que_veio_depois(pasta):
    resposta = _ficha(pasta, como_era_em=date(2025, 6, 30))
    assert resposta.corpo["como_era_em"] == "2025-06-30"
    envelopes = [
        *resposta.corpo["cadastro_na_receita"].values(),
        *(e for linha in resposta.corpo["entregas"] for e in linha.values()),
    ]
    assert all(e["publico_em"] <= "2025-06-30" for e in envelopes)


def test_como_era_em_no_futuro_vale_hoje(pasta):
    """A tela não deixa pedir um dia depois de hoje: vale o dia de hoje."""
    resposta = _ficha(pasta, como_era_em=date(2030, 1, 1))
    assert resposta.corpo["como_era_em"] == HOJE.isoformat()


def test_limites_da_tela_em_portugues_sem_nome_de_campo_da_api(pasta):
    """Os limites da ficha da API falam em `known_at`, o nome do campo para quem programa; o analista lê
    "o dia da ficha". Os outros limites são os mesmos, e o corpo (a planilha lê dele) traz os da tela."""
    assert all("known_at" not in limite for limite in leitura.LIMITES)
    assert len(leitura.LIMITES) == len(ficha.LIMITES)
    assert set(ficha.LIMITES) - set(leitura.LIMITES) == {
        limite for limite in ficha.LIMITES if "known_at" in limite
    }
    assert _ficha(pasta).corpo["limites"] == list(leitura.LIMITES)


# ---------------------------------------------------------------- pessoa e o que não existe


@pytest.mark.parametrize(
    "cnpj",
    [
        empresas_de_mentira.MEI,
        empresas_de_mentira.EMPRESARIO_INDIVIDUAL,
        empresas_de_mentira.FORA_DA_REDE,
        empresas_de_mentira.FUNDO,
        empresas_de_mentira.INEXISTENTE,
    ],
)
def test_pessoa_e_quem_nao_e_empresa_saem_nao_disponivel_sem_motivo(tmp_path, cnpj):
    """Risco 1: a resposta do MEI é igual, campo a campo, à de um CNPJ que não existe."""
    pasta = ficha_de_mentira._base(
        tmp_path,
        ficha_de_mentira.pd.concat(
            [ficha_de_mentira._rotulos(), ficha_de_mentira._rotulos(cnpj=cnpj)]
        ),
    )
    resposta = _ficha(pasta, cnpj=cnpj)
    inexistente = _ficha(pasta, cnpj=empresas_de_mentira.INEXISTENTE)
    assert resposta.estado == leitura.NAO_DISPONIVEL
    assert resposta == inexistente
    assert resposta.corpo is None and resposta.fontes == [] and resposta.linhas == 0


def test_cnpj_invalido_e_erro_de_quem_chama(pasta):
    with pytest.raises(ValueError):
        _ficha(pasta, cnpj="123")


# ---------------------------------------------------------------- o portão e a prontidão


def test_sem_prontidao_a_ficha_sai_nao_liberada_sem_ler_o_cnpj(pasta):
    """Condição (a) da Diretoria: sem prontidão é estado da tela, nunca erro, e nada sai."""
    assert _ficha(pasta, regras=_sem_prontidao()).estado == leitura.NAO_LIBERADA
    # o mesmo para um MEI e para um CNPJ que não existe: "não liberado" não diz se o CNPJ existe
    for cnpj in (empresas_de_mentira.MEI, empresas_de_mentira.INEXISTENTE):
        resposta = _ficha(pasta, cnpj=cnpj, regras=_sem_prontidao())
        assert resposta == leitura.Resposta(leitura.NAO_LIBERADA)


def test_entregas_sem_prontidao_somem_e_o_cadastro_continua(pasta):
    """Risco 2: a tabela das entregas sem prontidão tira o bloco, como na API."""
    resposta = _ficha(pasta, regras=_regras(empresas.TABELAS))
    assert resposta.estado == leitura.PRONTA
    assert "entregas" not in resposta.corpo
    assert {f["fonte"] for f in resposta.fontes} == {"rfb-cnpj"}


def test_campo_que_o_portao_nega_some_da_ficha(pasta):
    """Risco 2: a palavra que nunca sai (D2) vale na tela também."""
    regras = dataclasses.replace(
        _regras(),
        palavras_que_nunca_saem=_regras().palavras_que_nunca_saem | {"razao"},
    )
    cadastro = _ficha(pasta, regras=regras).corpo["cadastro_na_receita"]
    assert "razao_social" not in cadastro
    assert "situacao_cadastral" in cadastro


def test_permitido_na_tela_usa_o_canal_da_api_externa_nao_o_do_app():
    """O canal do app é mais solto (ADR 0102): a tela pergunta como a API externa, sem o contrato."""
    permitido = leitura.permitido_na_tela(ficha.CONJUNTO, HOJE, _sem_prontidao())
    assert not permitido("rfb-cnpj", "razao_social", False)
    permitido = leitura.permitido_na_tela(ficha.CONJUNTO, HOJE, _regras())
    assert permitido("rfb-cnpj", "razao_social", False)
    # campo fora das linhas de `profiles` nunca sai, mesmo de fonte liberada
    assert not permitido("rfb-cnpj", "telefone", False)


# ---------------------------------------------------------------- o que a ficha traz (sem prontidão)


def test_blocos_dizem_o_que_a_ficha_traz_e_a_fonte_sem_data_nem_numero():
    """Diretoria (10/11): sem prontidão, a tela diz o que vem e de onde, sem data prometida nem número."""
    titulos = [bloco.titulo for bloco in leitura.BLOCOS]
    assert titulos == ["Cadastro na Receita Federal", "Entregas de balanço à CVM"]
    for bloco in leitura.BLOCOS:
        assert bloco.fonte and bloco.o_que_traz.endswith(".")
        texto = f"{bloco.titulo} {bloco.fonte} {bloco.o_que_traz}"
        assert not any(caractere.isdigit() for caractere in texto), texto


def test_blocos_em_tipos_simples():
    assert leitura.blocos_como_lista()[0] == {
        "titulo": "Cadastro na Receita Federal",
        "fonte": leitura.BLOCOS[0].fonte,
        "o_que_traz": leitura.BLOCOS[0].o_que_traz,
    }
