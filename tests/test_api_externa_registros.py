"""A rota `GET /companies/{cnpj}/registrations` (linha 980, onda 2, PR 5): só os registros nas agências.

Abre só os blocos do registro que dizem o que a empresa tem nas agências reguladoras, cada um pelo portão do
conjunto dele: `regulados` (ANEEL e ANS, no `profiles`) e `registros_adicionais` (Anatel, ANM, ANP e PAT, no
`extended_sources`). É o mesmo leitor e o mesmo portão da análise completa, sem abrir o resto da análise. Base
de mentira, sem internet; os CNPJs são de ninguém. Riscos que estes testes pegam: bloco fechado vazando pelo nome
ou pelo tamanho (duas organizações; resposta igual com e sem o dado), linha de pessoa física saindo, olhar o
futuro, pessoa física pedida pelo CNPJ (MEI, empresário individual, CPF), o consumo contado no conjunto errado e
a varredura de pessoa que falha virando "não achou".
"""

import dataclasses
from datetime import date

import pytest
from sqlalchemy import select

from base import prontidao
from base.porta import Porta
from base.prontidao import AVISO_DE_PILOTO, Prontidao, ProntidaoDePiloto, Prova
from src import portao_externo as portao
from src.api_externa import rotas, tabelas_por_cnpj
from src.api_externa.conjuntos import empresas, ficha, por_tabela
from src.api_externa.pessoas import RespostaComPessoaProibida
from src.banco.modelo import consumo_da_api
from tests import ajudantes_da_api_externa as aj
from tests import test_api_externa_analise as analise_de_mentira
from tests import test_api_externa_empresas as empresas_de_mentira
from tests import test_api_externa_sem_trava as sem_trava
from tests import test_api_externa_socios_pj as socios_de_mentira
from tests import test_api_externa_tabelas_por_cnpj as regulados_de_mentira
from tests.ajudantes_de_cpf import cpf_que_confere

AGORA = regulados_de_mentira.AGORA
DIA = regulados_de_mentira.DIA
EMPRESA = regulados_de_mentira.EMPRESA
ROTA = f"/data/v1/companies/{EMPRESA}/registrations"
NOMES_DOS_REGULADOS = (
    "regulated_activities",
    "aneel_commercial_indicators",
    "aneel-fiscalizacao",
)


def _regras() -> portao.Regras:
    """O perfil e as tabelas do `extended_sources` com a prontidão cheia; as do lote 1 (ANEEL e ANS) só na de
    piloto, como hoje em produção (a prova com a data do teste)."""
    prova = Prova(AGORA.date(), "conferida no teste", "teste")
    versoes = prontidao.versoes_maiores()
    vigentes = portao.regras_vigentes()
    cheias = (*analise_de_mentira.DO_PERFIL, *sem_trava.TABELAS)
    do_piloto = {
        e.tabela for e in tabelas_por_cnpj.do_bloco(tabelas_por_cnpj.REGULADOS)
    }
    return dataclasses.replace(
        vigentes,
        prontidao={t: Prontidao(versoes[t], prova, prova, prova) for t in cheias},
        prontidao_de_piloto={
            **vigentes.prontidao_de_piloto,
            **{t: ProntidaoDePiloto(versoes[t], prova, prova) for t in do_piloto},
        },
    )


def _pasta(tmp_path, monkeypatch, nome="base", aneel=True, adicionais=True):
    pasta = socios_de_mentira.base_com_socios(tmp_path / nome)
    if aneel:
        regulados_de_mentira.gravar(
            pasta, regulados_de_mentira.ANEEL, regulados_de_mentira._aneel()
        )
    if adicionais:
        sem_trava._gravar_tudo(pasta)
    monkeypatch.setattr(rotas, "abrir_porta", lambda banco_: Porta(pasta, banco_))
    return pasta


def _pedir(monkeypatch, chave, cnpj=EMPRESA, dia=DIA):
    monkeypatch.setattr(rotas, "regras_da_api", _regras)
    cliente = aj.cliente_da_api(monkeypatch, AGORA)
    return cliente.get(
        f"/data/v1/companies/{cnpj}/registrations",
        params={"known_at": dia.isoformat()},
        headers=aj.bearer(chave.valor),
    )


def _org(banco, nome, *conjuntos, piloto=False):
    return regulados_de_mentira._organizacao(
        banco, aj.admin(banco), nome, *conjuntos, piloto=piloto
    )


# ---------------------------------------------------------------- o que sai


def test_com_os_dois_conjuntos_saem_os_dois_blocos_com_fonte_data_e_aviso_de_piloto(
    tmp_path, banco, monkeypatch
):
    _pasta(tmp_path, monkeypatch)
    chave = _org(banco, "Alfa", ficha.CONJUNTO, sem_trava.CONJUNTO, piloto=True)
    resposta = _pedir(monkeypatch, chave)
    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["cnpj"] == EMPRESA and corpo["known_at"] == DIA.isoformat()
    aneel = corpo["blocks"]["regulated_activities"]["aneel_commercial_indicators"]
    campo = aneel["items"][0]["active_consumer_units"]
    assert (campo["value"], campo["source"], campo["published_at"]) == (
        300, "aneel-fiscalizacao", "2025-05-10",
    )  # fmt: skip
    assert campo["pilot"] is True and corpo["pilot_notice"] == AVISO_DE_PILOTO
    pados = corpo["blocks"]["additional_records"]["anatel_enforcement_proceedings"]
    assert pados["found"] is True
    assert pados["items"][0]["fine_imposed_brl"]["source"] == "anatel-pados"
    fontes = {f["source"] for f in corpo["sources"]}
    assert {"aneel-fiscalizacao", *sem_trava.FONTES} <= fontes
    assert corpo["requests_used"] == 2  # um pedido por conjunto aberto
    assert corpo["limits"]
    for nunca in (sem_trava.DE_PESSOA, "PADO-PESSOA", "OUTRA-EMPRESA"):
        assert nunca not in resposta.text


def test_a_rota_nao_abre_o_resto_da_analise(tmp_path, banco, monkeypatch):
    _pasta(tmp_path, monkeypatch)
    chave = _org(banco, "Alfa", ficha.CONJUNTO, sem_trava.CONJUNTO, piloto=True)
    corpo = _pedir(monkeypatch, chave).json()
    assert set(corpo["blocks"]) == {"regulated_activities", "additional_records"}
    for de_fora in ("registration", "summary", "timeline", "corporate_ownership"):
        assert de_fora not in corpo


def test_bloco_aberto_que_nao_achou_vai_em_not_found(tmp_path, banco, monkeypatch):
    _pasta(tmp_path, monkeypatch, adicionais=False)
    chave = _org(banco, "Alfa", ficha.CONJUNTO, sem_trava.CONJUNTO, piloto=True)
    corpo = _pedir(monkeypatch, chave).json()
    assert [n["block"] for n in corpo["not_found"]] == ["additional_records"]
    assert corpo["blocks"]["regulated_activities"]["aneel_commercial_indicators"][
        "found"
    ]


# ---------------------------------------------------------------- o que não sai


def test_sem_o_conjunto_o_bloco_nao_aparece_nem_pelo_nome_nem_pelo_tamanho(
    tmp_path, banco, monkeypatch
):
    chave = _org(banco, "Beta", ficha.CONJUNTO, piloto=True)
    respostas = []
    for nome, com_dado in (("com", True), ("sem", False)):
        _pasta(tmp_path, monkeypatch, nome, adicionais=com_dado)
        resposta = _pedir(monkeypatch, chave)
        assert resposta.status_code == 200
        respostas.append(resposta.content)
    assert respostas[0] == respostas[1]
    for nome in sem_trava.NOMES_DE_FORA:
        assert nome not in respostas[0].decode()


def test_duas_organizacoes_cada_uma_ve_so_o_seu_contrato(tmp_path, banco, monkeypatch):
    _pasta(tmp_path, monkeypatch)
    alfa = _org(banco, "Alfa", sem_trava.CONJUNTO)
    beta = _org(banco, "Beta", ficha.CONJUNTO, piloto=True)
    da_alfa = _pedir(monkeypatch, alfa)
    da_beta = _pedir(monkeypatch, beta)
    assert set(da_alfa.json()["blocks"]) == {"additional_records"}
    for nome in NOMES_DOS_REGULADOS:
        assert nome not in da_alfa.text
    assert set(da_beta.json()["blocks"]) == {"regulated_activities"}
    for nome in sem_trava.NOMES_DE_FORA:
        assert nome not in da_beta.text


def test_sem_a_marca_de_piloto_os_regulados_nao_saem(tmp_path, banco, monkeypatch):
    _pasta(tmp_path, monkeypatch)
    chave = _org(banco, "Gama", ficha.CONJUNTO, sem_trava.CONJUNTO)
    resposta = _pedir(monkeypatch, chave)
    assert resposta.status_code == 200
    for nome in NOMES_DOS_REGULADOS:
        assert nome not in resposta.text
    assert "pilot_notice" not in resposta.text


def test_sem_nenhum_dos_conjuntos_responde_nao_disponivel_sem_dizer_o_nome(
    tmp_path, banco, monkeypatch
):
    _pasta(tmp_path, monkeypatch)
    chave = _org(banco, "Delta", empresas.CONJUNTO)
    resposta = _pedir(monkeypatch, chave)
    assert resposta.status_code == 404
    assert resposta.json()["detail"] == "not_available"
    for nome in (*NOMES_DOS_REGULADOS, *sem_trava.NOMES_DE_FORA):
        assert nome not in resposta.text


def test_chave_invalida_nao_ve_nada(tmp_path, monkeypatch):
    _pasta(tmp_path, monkeypatch)
    monkeypatch.setattr(rotas, "regras_da_api", _regras)
    cliente = aj.cliente_da_api(monkeypatch, AGORA)
    resposta = cliente.get(ROTA, headers=aj.bearer("tl_chave_que_nao_existe"))
    assert resposta.status_code == 401


# ---------------------------------------------------------------- pessoa física


@pytest.mark.parametrize(
    "cnpj",
    [
        pytest.param(empresas_de_mentira.MEI, id="mei"),
        pytest.param(
            empresas_de_mentira.EMPRESARIO_INDIVIDUAL,
            id="empresario_individual",
        ),
    ],
)
def test_mei_e_empresario_individual_saem_nao_disponivel(
    cnpj, tmp_path, banco, monkeypatch
):
    _pasta(tmp_path, monkeypatch)
    chave = _org(banco, "Alfa", ficha.CONJUNTO, sem_trava.CONJUNTO, piloto=True)
    resposta = _pedir(monkeypatch, chave, cnpj=cnpj)
    assert resposta.status_code == 404
    assert resposta.json()["detail"] == "not_available"


def test_cpf_no_lugar_do_cnpj_e_recusado(tmp_path, banco, monkeypatch):
    _pasta(tmp_path, monkeypatch)
    chave = _org(banco, "Alfa", ficha.CONJUNTO, sem_trava.CONJUNTO, piloto=True)
    resposta = _pedir(monkeypatch, chave, cnpj=cpf_que_confere("123456789"))
    assert resposta.status_code == 400
    assert resposta.json()["detail"] == "invalid_cnpj"


def test_varredura_de_pessoa_que_falha_derruba_a_resposta_sem_o_valor(
    tmp_path, banco, monkeypatch
):
    _pasta(tmp_path, monkeypatch)
    chave = _org(banco, "Alfa", ficha.CONJUNTO, sem_trava.CONJUNTO, piloto=True)

    def falha(*_args: object, **_kwargs: object) -> None:
        raise RespostaComPessoaProibida(["anatel_pados.texto"])

    monkeypatch.setattr(por_tabela.LeitorPorTabela, "bloco", falha)
    resposta = _pedir(monkeypatch, chave)
    assert resposta.status_code == 503
    assert "anatel" not in resposta.text


# ---------------------------------------------------------------- sem olhar o futuro


def test_o_mes_publicado_depois_do_dia_nao_sai(tmp_path, banco, monkeypatch):
    _pasta(tmp_path, monkeypatch)
    chave = _org(banco, "Alfa", ficha.CONJUNTO, piloto=True)
    texto = _pedir(monkeypatch, chave).text
    assert "2025-04-01" not in texto  # a referência de abril só ficou pública em 15/07
    depois = _pedir(monkeypatch, chave, dia=date(2025, 7, 31)).json()
    referencias = {
        item["reference_period"]["value"]
        for item in depois["blocks"]["regulated_activities"][
            "aneel_commercial_indicators"
        ]["items"]
    }
    assert "2025-04-01" in referencias


def test_cortar_o_futuro_nao_muda_o_passado(tmp_path, banco, monkeypatch):
    chave = _org(banco, "Alfa", ficha.CONJUNTO, piloto=True)
    _pasta(tmp_path, monkeypatch, "inteira", adicionais=False)
    inteira = _pedir(monkeypatch, chave).json()
    pasta = socios_de_mentira.base_com_socios(tmp_path / "cortada")
    aneel = regulados_de_mentira._aneel()
    regulados_de_mentira.gravar(
        pasta, regulados_de_mentira.ANEEL, aneel[aneel["disponivel_em"] <= DIA]
    )
    monkeypatch.setattr(rotas, "abrir_porta", lambda banco_: Porta(pasta, banco_))
    assert _pedir(monkeypatch, chave).json() == inteira


# ---------------------------------------------------------------- consumo


def test_cada_bloco_conta_um_pedido_no_conjunto_dele(tmp_path, banco, monkeypatch):
    _pasta(tmp_path, monkeypatch)
    chave = _org(banco, "Alfa", ficha.CONJUNTO, sem_trava.CONJUNTO, piloto=True)
    assert _pedir(monkeypatch, chave).status_code == 200
    with banco.connect() as conexao:
        linhas = conexao.execute(
            select(consumo_da_api.c.conjunto, consumo_da_api.c.pedidos)
        ).all()  # uma organização só no teste
    por_conjunto = {conjunto: pedidos for conjunto, pedidos in linhas}
    assert por_conjunto == {ficha.CONJUNTO: 1, sem_trava.CONJUNTO: 1}
