"""`GET /data/v1/companies/{cnpj}/people` (ADR 0128, Emenda 4): sócios e donos pela chave da organização.

Riscos que estes testes pegam: (1) a chave de uma organização sem a permissão `pessoa_no_conector` (ou com ela
suspensa, vencida, ou só com a da tela) ver pessoa, ou a rota dizer pelo trabalho que faz se o CNPJ tem sócio;
(2) chave desconhecida, revogada ou de organização suspensa passar; (3) sair CPF (inteiro, mascarado ou os
dígitos que a razão social do MEI traz), menor de idade, endereço ou contato; (4) quem se opôs aparecer;
(5) a consulta não ir para a auditoria, ou ir com o CNPJ ou um nome, ou um dos dois ir para o log. Todo nome e
todo CPF aqui é inventado.
"""

import logging
import re
from datetime import date, timedelta

import pytest
import sqlalchemy as sa

from base import oposicao_na_tela
from src import auditoria
from src.analista import pessoa
from src.api_externa import pessoas, rotas
from src.banco import chaves_da_api as cb
from src.banco import membros_da_organizacao as mb
from src.banco.modelo import auditoria as tabela_da_auditoria
from src.pessoa_no_texto import ONZE_DIGITOS, cpf_valido
from tests import ajudantes_da_api_externa as aj
from tests import test_montar_acervo_pessoa as montar_de_mentira
from tests.ajudantes_de_cpf import cpf_que_confere, formatado, meio

SOCIEDADE = "11222333000181"  # FULANA (adulta), uma criança e uma holding no quadro
INDIVIDUAL = "22333444000181"  # empresário individual: BELTRANO, com o CPF colado na razão social
SEM_NINGUEM = "99888777000100"
ROTA = "/data/v1/companies/{}/people"
INEXISTENTE = "/data/v1/companies/{}/nao-existe"
CPF_DE_MENTIRA = cpf_que_confere("888123456")


def _montar(tmp_path, opostos=montar_de_mentira.SEM_OPOSTOS):
    cnpj, bruto = montar_de_mentira._acervo(tmp_path / "origem")
    destino = tmp_path / "fora" / "acervo_pessoa"
    montar_de_mentira.montar.carregar(
        cnpj, bruto, destino, montar_de_mentira.AGORA, opostos
    )
    return destino


@pytest.fixture(autouse=True)
def acervo(tmp_path, monkeypatch):
    """O acervo de pessoa montado de mentira neste servidor (sócios, titular e contato)."""
    destino = _montar(tmp_path)
    monkeypatch.setenv(pessoa.VARIAVEL, str(destino))
    return destino


@pytest.fixture
def ator(banco):
    return aj.admin(banco)


def _org(banco, ator, nome, *conjuntos):
    org = aj.organizacao(banco, ator, nome)
    for conjunto in conjuntos:
        aj.contrato(banco, ator, org, conjunto=conjunto)
    return org, aj.chave(banco, ator, org)


@pytest.fixture
def com_permissao(banco, ator):
    return _org(banco, ator, "Casa Exemplo", pessoas.CONJUNTO)


@pytest.fixture
def sem_permissao(banco, ator):
    return _org(banco, ator, "Outra Exemplo", "links")


@pytest.fixture
def cliente(monkeypatch, com_permissao, sem_permissao):
    return aj.cliente_da_api(monkeypatch)


def _get(cliente, chave, cnpj=SOCIEDADE, rota=ROTA):
    return cliente.get(rota.format(cnpj), headers=aj.bearer(chave.valor))


def _nao_le(*_argumentos, **_nomeados):
    raise AssertionError(
        "o acervo de pessoa não pode ser tocado para quem não pode ver"
    )


def _sem_acervo(monkeypatch):
    for nome in ("pasta_do_acervo", "socios_da_empresa", "titular_da_empresa"):
        monkeypatch.setattr(pessoa, nome, _nao_le)


def _vistas(banco) -> list[sa.Row]:
    tabela = tabela_da_auditoria
    with banco.connect() as conexao:
        return list(
            conexao.execute(
                sa.select(tabela).where(tabela.c.acao == auditoria.ACAO_PESSOA_VISTA)
            )
        )


def _consumo(banco, org) -> cb.ConsumoDoMes:
    with banco.connect() as conexao:
        return cb.consumo_do_mes(conexao, org.id, aj.HOJE)


def _igual_a_rota_que_nao_existe(cliente, chave, cnpj=SOCIEDADE) -> None:
    resposta = _get(cliente, chave, cnpj)
    inexistente = _get(cliente, chave, cnpj, INEXISTENTE)
    assert resposta.status_code == inexistente.status_code == 404
    assert resposta.content == inexistente.content
    assert resposta.headers["content-type"] == inexistente.headers["content-type"]


# ---------------------------------------------------------------- quem pode


def test_organizacao_com_a_permissao_ve_so_o_socio_adulto_pessoa_fisica(
    cliente, com_permissao
):
    resposta = _get(cliente, com_permissao[1])
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["status"] == "ready"
    assert corpo["partners"] == [
        {"name": "FULANA EXEMPLO", "role": "Sócio-Administrador", "since": "2020-01-31"}
    ]
    assert corpo["partners_total"] == 1
    assert corpo["owners"] == [] and corpo["owners_status"] == "none"
    assert corpo["source"] == pessoa.FONTE and corpo["snapshot_month"] == "2026-10"
    texto = resposta.text
    assert (
        "CRIANCA" not in texto and "HOLDING" not in texto
    )  # menor e sócio PJ ficam fora
    assert resposta.headers["Cache-Control"] == "no-store"


def test_o_titular_do_empresario_individual_sai_so_com_o_nome_sem_o_cpf(
    cliente, com_permissao
):
    resposta = _get(cliente, com_permissao[1], INDIVIDUAL)
    corpo = resposta.json()
    assert corpo["owners"] == [{"name": "BELTRANO EXEMPLO"}]
    assert corpo["owners_status"] == "ready"
    assert "REPRESENTADO" not in resposta.text  # quem tem representante legal fica fora
    assert "88800000127" not in resposta.text


def test_empresa_sem_pessoa_no_acervo_sai_vazia(cliente, com_permissao):
    corpo = _get(cliente, com_permissao[1], SEM_NINGUEM).json()
    assert corpo["status"] == "no_people"
    assert corpo["partners"] == [] and corpo["owners"] == []


def test_aceita_o_cnpj_com_pontuacao(cliente, com_permissao):
    corpo = _get(cliente, com_permissao[1], "11.222.333.0001-81").json()
    assert [p["name"] for p in corpo["partners"]] == ["FULANA EXEMPLO"]


def test_organizacao_sem_a_permissao_recebe_o_404_de_uma_rota_que_nao_existe(
    cliente, sem_permissao, banco, monkeypatch
):
    _sem_acervo(monkeypatch)
    for cnpj in (SOCIEDADE, INDIVIDUAL, SEM_NINGUEM, "123"):
        _igual_a_rota_que_nao_existe(cliente, sem_permissao[1], cnpj)
    assert _vistas(banco) == []
    assert _consumo(banco, sem_permissao[0]) == cb.ConsumoDoMes(0, 0, 0)


def test_a_permissao_da_tela_nao_abre_a_api(cliente, banco, ator, monkeypatch):
    _, chave = _org(banco, ator, "So Tela Exemplo", mb.CONJUNTO_DE_PESSOA_NA_TELA)
    _sem_acervo(monkeypatch)
    _igual_a_rota_que_nao_existe(cliente, chave)


def test_a_permissao_em_outra_finalidade_nao_vale(cliente, banco, ator, monkeypatch):
    org = aj.organizacao(banco, ator, "Credito Exemplo")
    aj.contrato(banco, ator, org, conjunto=pessoas.CONJUNTO, finalidade="credito")
    _sem_acervo(monkeypatch)
    _igual_a_rota_que_nao_existe(cliente, aj.chave(banco, ator, org))


def test_permissao_suspensa_para_de_valer_no_pedido_seguinte(
    cliente, com_permissao, banco, ator, monkeypatch
):
    org, chave = com_permissao
    assert _get(cliente, chave).status_code == 200
    with banco.begin() as conexao:
        direito = next(
            d for d in cb.direitos_vigentes(conexao, org.id, aj.HOJE)
            if d.conjunto == pessoas.CONJUNTO
        )  # fmt: skip
        cb.suspender_direito(
            conexao, organizacao_id=org.id, direito_id=direito.id, ator_id=ator.id
        )
    _sem_acervo(monkeypatch)
    _igual_a_rota_que_nao_existe(cliente, chave)


def test_permissao_suspensa_para_todos_para_de_valer(
    cliente, com_permissao, banco, ator, monkeypatch
):
    with banco.begin() as conexao:
        cb.suspender_conjunto(
            conexao, conjunto=pessoas.CONJUNTO, motivo="contrato", ator_id=ator.id
        )
    _sem_acervo(monkeypatch)
    _igual_a_rota_que_nao_existe(cliente, com_permissao[1])


def test_permissao_vencida_nao_vale(cliente, banco, ator, monkeypatch):
    org = aj.organizacao(banco, ator, "Vencida Exemplo")
    with banco.begin() as conexao:
        cb.conceder_direito(
            conexao,
            organizacao_id=org.id,
            conjunto=pessoas.CONJUNTO,
            finalidade="analise",
            vigente_desde=date(2026, 9, 1),
            vigente_ate=aj.HOJE - timedelta(days=1),
            ator_id=ator.id,
        )
    _sem_acervo(monkeypatch)
    _igual_a_rota_que_nao_existe(cliente, aj.chave(banco, ator, org))


def test_chave_desconhecida_nao_entra_nem_toca_o_acervo(cliente, monkeypatch, banco):
    _sem_acervo(monkeypatch)
    resposta = cliente.get(
        ROTA.format(SOCIEDADE), headers=aj.bearer("tld_abcdefgh_" + "B" * 43)
    )
    assert resposta.status_code == 401
    sem_chave = cliente.get(ROTA.format(SOCIEDADE))
    assert sem_chave.status_code == 401
    assert _vistas(banco) == []


def test_chave_revogada_e_organizacao_suspensa_nao_entram(
    cliente, com_permissao, banco, ator, monkeypatch
):
    org, chave = com_permissao
    with banco.begin() as conexao:
        cb.revogar_chave(
            conexao, organizacao_id=org.id, chave_id=chave.chave_id, ator_id=ator.id
        )
    outra = aj.chave(banco, ator, org)
    with banco.begin() as conexao:
        cb.suspender_organizacao(
            conexao, organizacao_id=org.id, motivo="contrato", ator_id=ator.id
        )
    _sem_acervo(monkeypatch)
    assert _get(cliente, chave).status_code == 401
    assert _get(cliente, outra).status_code in (401, 403)
    assert _vistas(banco) == []


def test_cnpj_invalido_de_quem_pode_400_sem_repetir_o_que_veio(
    cliente, com_permissao, banco
):
    resposta = _get(cliente, com_permissao[1], "12345678901")
    assert resposta.status_code == 400
    assert resposta.json() == {"detail": "invalid_cnpj"}
    assert "12345678901" not in resposta.text
    assert _vistas(banco) == []


def test_acervo_fora_do_servidor_503_sem_dizer_onde(
    cliente, com_permissao, monkeypatch, banco
):
    monkeypatch.delenv(pessoa.VARIAVEL)
    resposta = _get(cliente, com_permissao[1])
    assert resposta.status_code == 503
    assert resposta.json() == {"detail": "service_unavailable"}
    assert _vistas(banco) == []


def test_sem_a_tabela_dos_titulares_os_socios_saem_e_os_donos_dizem_que_faltam(
    cliente, com_permissao, acervo
):
    for arquivo in (acervo / pessoa.INDIVIDUAIS).glob("*"):
        arquivo.unlink()
    (acervo / pessoa.INDIVIDUAIS).rmdir()
    corpo = _get(cliente, com_permissao[1]).json()
    assert [p["name"] for p in corpo["partners"]] == ["FULANA EXEMPLO"]
    assert corpo["owners"] == [] and corpo["owners_status"] == "unavailable"


# ---------------------------------------------------------------- oposição do titular


def test_quem_se_opos_nao_sai_e_os_outros_ficam(
    cliente, com_permissao, sem_permissao, tmp_path, monkeypatch
):
    opostos = montar_de_mentira._opostos(("***123456**", "FULANA EXEMPLO"))
    destino = _montar(tmp_path / "com_oposicao", opostos)
    monkeypatch.setenv(pessoa.VARIAVEL, str(destino))
    da_fulana = _get(cliente, com_permissao[1]).json()
    assert da_fulana["partners"] == [] and da_fulana["partners_total"] == 0
    do_beltrano = _get(cliente, com_permissao[1], INDIVIDUAL).json()
    assert [p["name"] for p in do_beltrano["partners"]] == ["BELTRANO EXEMPLO"]
    _igual_a_rota_que_nao_existe(cliente, sem_permissao[1], INDIVIDUAL)


def test_oposicao_registrada_hoje_some_sem_esperar_a_montagem(
    cliente, com_permissao, acervo
):
    antes = _get(cliente, com_permissao[1]).json()
    assert [p["name"] for p in antes["partners"]] == ["FULANA EXEMPLO"]
    ids = montar_de_mentira._opostos(("***123456**", "FULANA EXEMPLO")).ids
    oposicao_na_tela.aplicar_no_acervo(acervo, set(ids))
    depois = _get(cliente, com_permissao[1]).json()
    assert depois["partners"] == [] and depois["partners_total"] == 0


def test_o_titular_que_se_opos_some_dos_donos(cliente, com_permissao, acervo):
    ids = montar_de_mentira._opostos(("88800000127", "BELTRANO EXEMPLO")).ids
    oposicao_na_tela.aplicar_no_acervo(acervo, set(ids))
    corpo = _get(cliente, com_permissao[1], INDIVIDUAL).json()
    assert corpo["owners"] == []


# ---------------------------------------------------------------- varredura por máquina


ERROS_SEM_ECO = {"Not Found", "invalid_cnpj"}


def _cpfs_soltos(texto: str) -> list[str]:
    return [m for m in ONZE_DIGITOS.findall(texto) if cpf_valido(m)]


def test_toda_resposta_passa_na_varredura_zero_cpf_zero_menor_zero_endereco(
    cliente, com_permissao, sem_permissao
):
    """Cada resposta desta rota, de quem pode e de quem não pode, pela mesma varredura que a rota usa e por
    uma conferência independente: só as chaves da lista fechada, nenhum CPF, e-mail, telefone ou CEP."""
    respostas = [
        _get(cliente, chave, cnpj)
        for chave in (com_permissao[1], sem_permissao[1])
        for cnpj in (SOCIEDADE, INDIVIDUAL, SEM_NINGUEM, "123")
    ]
    for resposta in respostas:
        corpo = resposta.json()
        if "detail" in corpo:  # erro: só o código, nada do pedido
            assert set(corpo) == {"detail"} and corpo["detail"] in ERROS_SEM_ECO, (
                resposta.text
            )
        else:
            assert pessoas.falhas_da_resposta(corpo) == [], resposta.text
        assert aj.chaves_de(corpo) <= pessoas.CHAVES_DA_RESPOSTA | {"detail"}
        texto = resposta.text
        assert not _cpfs_soltos(texto) and "***" not in texto
        assert not re.search(r"\d{5}-?\d{3}(?!\d)", texto)  # CEP
        assert "@" not in texto
        for proibida in ("CRIANCA", "REPRESENTADO", "birth", "age", "address", "phone"):
            assert proibida not in texto


@pytest.mark.parametrize(
    "sujo",
    [
        {"partners": [{"name": "FULANA EXEMPLO", "cpf": "x"}]},
        {"partners": [{"name": f"FULANA {formatado(CPF_DE_MENTIRA)}"}]},
        {"partners": [{"name": f"FULANA ***{meio(CPF_DE_MENTIRA)}**"}]},
        {"owners": [{"name": f"BELTRANO EXEMPLO {CPF_DE_MENTIRA}"}]},
        {"owners": [{"name": "fulana@exemplo.com"}]},
        {"owners": [{"name": "(11) 91234-5678"}]},
        {"owners": [{"name": "RUA EXEMPLO 01310-100"}]},
        {"partners": [{"name": "FULANA", "birth_date": "2010-01-01"}]},
        {"age_range": "0-12"},
    ],
)
def test_a_varredura_pega_o_que_nunca_pode_sair(sujo):
    assert pessoas.falhas_da_resposta(sujo)


def test_a_varredura_nao_diz_o_valor_so_onde():
    falhas = pessoas.falhas_da_resposta(
        {"partners": [{"name": f"FULANA {formatado(CPF_DE_MENTIRA)}"}]}
    )
    assert falhas == ["partners[0].name"]
    assert CPF_DE_MENTIRA not in str(falhas)


def test_resposta_que_falha_na_varredura_nao_sai_nem_vai_para_a_auditoria(
    cliente, com_permissao, monkeypatch, banco, caplog
):
    def sujo(_pasta, _cnpj):
        return pessoa.Socios(
            [{"nome": "FULANA EXEMPLO", "qualificacao": f"Sócio {formatado(CPF_DE_MENTIRA)}",
              "entrou_em": None}],
            1,
            "2026-10",
        )  # fmt: skip

    monkeypatch.setattr(pessoa, "socios_da_empresa", sujo)
    with caplog.at_level(logging.DEBUG):
        resposta = _get(cliente, com_permissao[1])
    assert resposta.status_code == 503
    assert resposta.json() == {"detail": "service_unavailable"}
    assert _vistas(banco) == []
    do_servidor = _log_do_servidor(caplog)
    assert formatado(CPF_DE_MENTIRA) not in do_servidor and "FULANA" not in do_servidor


def test_digitos_no_nome_do_titular_saem_mesmo_se_o_acervo_falhar(
    cliente, com_permissao, monkeypatch
):
    """Segunda tranca: o montador já tira o CPF da razão social; se um dia não tirar, a rota tira os dígitos."""
    monkeypatch.setattr(
        pessoa,
        "titular_da_empresa",
        lambda _p, _c: pessoa.Titular(
            [{"nome": f"BELTRANO EXEMPLO {CPF_DE_MENTIRA}"}], 1, "2026-10"
        ),
    )
    resposta = _get(cliente, com_permissao[1], INDIVIDUAL)
    assert resposta.status_code == 200
    assert resposta.json()["owners"] == [{"name": "BELTRANO EXEMPLO"}]


# ---------------------------------------------------------------- auditoria, consumo e log


def test_cada_consulta_vai_para_a_auditoria_so_com_ids(cliente, com_permissao, banco):
    org, chave = com_permissao
    _get(cliente, chave)
    _get(cliente, chave, INDIVIDUAL)
    vistas = _vistas(banco)
    assert len(vistas) == 2
    for vista in vistas:
        assert vista.ator_id is None and vista.alvo_id == org.id
        assert set(vista.detalhes) == {"tipo", "linhas", "canal", "chave_id"}
        assert vista.detalhes["tipo"] == pessoas.TIPO_DA_AUDITORIA
        assert vista.detalhes["canal"] == "api_externa"
        assert vista.detalhes["chave_id"] == str(chave.chave_id)
        texto = str(vista.detalhes)
        assert "11222333" not in texto and "22333444" not in texto
        assert "EXEMPLO" not in texto
    assert [v.detalhes["linhas"] for v in vistas] == [
        1,
        2,
    ]  # Fulana; Beltrano sócio e titular


def test_sem_auditoria_nada_sai(cliente, com_permissao, monkeypatch):
    def falhar(*_argumentos, **_nomeados):
        raise RuntimeError("banco fora")

    monkeypatch.setattr(rotas.auditoria, "registrar", falhar)
    with pytest.raises(RuntimeError):
        _get(cliente, com_permissao[1])


def test_a_consulta_conta_no_consumo_da_organizacao(cliente, com_permissao, banco):
    org, chave = com_permissao
    _get(cliente, chave)
    assert _consumo(banco, org) == cb.ConsumoDoMes(1, 1, 0)


def _log_do_servidor(caplog) -> str:
    """O que o código do TickerLab escreveu no log (o cliente de teste, `httpx`, anota o endereço pedido)."""
    return " | ".join(
        r.getMessage() for r in caplog.records if r.name.startswith("src")
    )


def test_o_log_nao_leva_cnpj_nem_nome(cliente, com_permissao, caplog):
    with caplog.at_level(logging.DEBUG):
        _get(cliente, com_permissao[1])
        _get(cliente, com_permissao[1], INDIVIDUAL)
    do_servidor = _log_do_servidor(caplog)
    assert "11222333" not in do_servidor and "22333444" not in do_servidor
    assert "EXEMPLO" not in do_servidor
    assert "pessoas da empresa: ready" in do_servidor


# ---------------------------------------------------------------- catálogo


def _conjuntos_do_catalogo(cliente, chave) -> set[str]:
    corpo = cliente.get("/data/v1/catalog", headers=aj.bearer(chave.valor)).json()
    return {item["dataset"] for item in corpo["datasets"]}


def test_o_catalogo_lista_a_permissao_so_para_quem_a_tem(
    cliente, com_permissao, sem_permissao
):
    assert pessoas.CONJUNTO in _conjuntos_do_catalogo(cliente, com_permissao[1])
    assert pessoas.CONJUNTO not in _conjuntos_do_catalogo(cliente, sem_permissao[1])


def test_a_rota_nao_entra_no_contrato_publicado():
    """O esquema público da `/data/v1` não anuncia a rota de pessoa (texto público; ADR 0128, Emenda 4)."""
    from scripts.gerar_openapi_data import openapi_data_v1

    assert not any("people" in caminho for caminho in openapi_data_v1()["paths"])
