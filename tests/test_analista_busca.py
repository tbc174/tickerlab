"""Encontrar empresas na tela do analista (linha 798, PR 3): `src/analista/busca.py`.

A tela busca pelo mesmo leitor da API externa (`LeitorDeProspeccao`), com o mesmo portão e a mesma prontidão,
e só pelos filtros que o analista entende: setor (a seção do CNAE do IBGE), UF e idade mínima. Riscos que
estes testes pegam:

1. a tela mostrar mais que a API (sem prontidão nada sai; o corpo é o do leitor da API, sem campo a mais);
2. baixar a base inteira (sem filtro nenhum, nada é lido; a página tem tamanho fixo);
3. filtro que a API recusaria (setor ou UF fora da lista, idade fora da faixa, cursor forjado);
4. olhar o futuro (o retrato só vale desde que ficou público; a idade conta a partir de hoje).

Base de mentira, sem internet: a mesma de `test_api_externa_prospeccao.py` (CNPJs de ninguém).
"""

import dataclasses
from datetime import date

import pandas as pd
import pytest

from base import cnae, prontidao
from base.porta import Porta
from base.prontidao import Prontidao, Prova
from src import portao_externo as portao
from src.analista import busca, leitura
from src.api_externa.conjuntos import prospeccao
from tests import test_api_externa_prospeccao as base_de_mentira

HOJE = base_de_mentira.AGORA.date()  # 10/11/2026: vale o retrato de outubro


def _regras() -> portao.Regras:
    prova = Prova(HOJE, "conferida no teste", "teste")
    versoes = prontidao.versoes_maiores()
    tabelas = (prospeccao.ESTABELECIMENTOS, prospeccao.EMPRESAS)
    return dataclasses.replace(
        portao.regras_vigentes(),
        prontidao={t: Prontidao(versoes[t], prova, prova, prova) for t in tabelas},
    )


def _sem_prontidao() -> portao.Regras:
    return dataclasses.replace(portao.regras_vigentes(), prontidao={})


def base_de_teste(tmp_path):
    """A base de mentira da prospecção numa pasta (os testes da rota usam a mesma)."""
    base = tmp_path / "base"
    base_de_mentira._gravar(
        base, prospeccao.ESTABELECIMENTOS, base_de_mentira._estabelecimentos()
    )
    base_de_mentira._gravar(base, prospeccao.EMPRESAS, base_de_mentira._empresas())
    return base


@pytest.fixture
def pasta(tmp_path):
    return base_de_teste(tmp_path)


def _buscar(pasta, regras=None, hoje=HOJE, **filtros):
    with Porta(pasta) as porta:
        return busca.buscar(
            porta, busca.Filtros(**filtros), hoje=hoje, regras=regras or _regras()
        )


def _cnpjs(resposta) -> list[str]:
    return [e["cnpj"] for e in resposta.corpo["empresas"]]


# ---------------------------------------------------------------- o que sai


def test_por_setor_sai_a_matriz_ativa_com_o_corpo_do_leitor_da_api(pasta):
    # J (Informação e comunicação) pega o CNAE 6201501: a matriz ativa da ALFA; a filial e a baixada não
    resposta = _buscar(pasta, setores=("J",))
    assert resposta.estado == leitura.PRONTA
    assert _cnpjs(resposta) == ["11111111000191"]
    (empresa,) = resposta.corpo["empresas"]
    assert empresa["razao_social"]["valor"] == "ALFA TECNOLOGIA S.A."
    assert empresa["razao_social"]["fonte"] == "rfb-cnpj"
    assert empresa["uf"]["valor"] == "MG"  # o retrato de outubro, já público em 10/11
    assert {f["fonte"] for f in resposta.fontes} == {"rfb-cnpj"}
    assert resposta.linhas == 1
    # risco 1: o mesmo corpo do leitor da API, com a mesma busca
    with Porta(pasta) as porta:
        da_api = prospeccao.LeitorDeProspeccao(
            porta,
            leitura.permitido_na_tela(prospeccao.CONJUNTO, HOJE, _regras()),
            busca.TAMANHO_DA_PAGINA,
        ).buscar(busca.busca_da_api(busca.Filtros(setores=("J",)), HOJE), HOJE)
    assert da_api is not None
    assert resposta.corpo == da_api.corpo


def test_por_uf_e_por_idade_minima(pasta):
    assert _cnpjs(_buscar(pasta, ufs=("SP",))) == ["22222222000191"]
    # aberta há pelo menos 10 anos (antes de 10/11/2016): só a ALFA, de 2010
    assert _cnpjs(_buscar(pasta, idade_minima=10)) == ["11111111000191"]
    assert _cnpjs(_buscar(pasta, setores=("G",), idade_minima=10)) == []


def test_varios_setores_e_ufs_somam(pasta):
    assert _cnpjs(_buscar(pasta, setores=("J", "G"))) == [
        "11111111000191",
        "22222222000191",
    ]
    assert _cnpjs(_buscar(pasta, ufs=("SP", "MG"))) == [
        "11111111000191",
        "22222222000191",
    ]


def test_risco_4_retrato_publicado_depois_de_hoje_nao_vale(tmp_path):
    # o mesmo retrato de outubro, mas publicado só em 20/11: em 10/11 vale o de setembro (a ALFA em SP)
    base = tmp_path / "base"
    adiado = pd.Timestamp("2026-11-20").date()
    for nome, tabela in (
        (prospeccao.ESTABELECIMENTOS, base_de_mentira._estabelecimentos()),
        (prospeccao.EMPRESAS, base_de_mentira._empresas()),
    ):
        outubro = tabela["mes_do_retrato"] == "2026-10"
        tabela.loc[outubro, "disponivel_em"] = adiado
        base_de_mentira._gravar(base, nome, tabela)
    resposta = _buscar(base, ufs=("SP",))
    assert _cnpjs(resposta) == ["11111111000191", "22222222000191"]
    assert resposta.corpo["como_era_em"] == HOJE.isoformat()


def test_a_pagina_tem_tamanho_fixo_e_cursor(pasta, monkeypatch):
    monkeypatch.setattr(busca, "TAMANHO_DA_PAGINA", 1)
    primeira = _buscar(pasta, ufs=("SP", "MG"))
    assert _cnpjs(primeira) == ["11111111000191"]
    assert primeira.corpo["cortada"] is True
    segunda = _buscar(pasta, ufs=("SP", "MG"), cursor=primeira.corpo["proximo_cursor"])
    assert _cnpjs(segunda) == ["22222222000191"]


# ---------------------------------------------------------------- o que não sai


def test_risco_2_sem_filtro_nada_e_lido(pasta):
    resposta = _buscar(pasta)
    assert resposta.estado == busca.SEM_FILTRO
    assert resposta.corpo is None


def test_risco_1_sem_prontidao_nada_sai_e_o_estado_nao_depende_do_filtro(pasta):
    for filtros in ({"setores": ("J",)}, {"ufs": ("AC",)}):
        resposta = _buscar(pasta, regras=_sem_prontidao(), **filtros)
        assert resposta == leitura.Resposta(leitura.NAO_LIBERADA)


@pytest.mark.parametrize(
    "filtros",
    [
        {"setores": ("Z",)},
        {
            "setores": ("T",)
        },  # serviços domésticos: empregador pessoa física, fora da busca
        {"setores": ("O",)},  # administração pública: não é alvo de mandato
        {"setores": ("A", "C", "G", "J")},  # mais setores que o máximo
        {"ufs": ("XX",)},
        {"idade_minima": 0},
        {"idade_minima": busca.IDADE_MAXIMA + 1},
        {"ufs": ("SP",), "cursor": "nao-e-cursor"},
    ],
)
def test_risco_3_filtro_que_a_api_recusaria_e_erro(pasta, filtros):
    with pytest.raises(busca.FiltroInvalido):
        _buscar(pasta, **filtros)


# ---------------------------------------------------------------- as peças


def test_cada_setor_vira_as_divisoes_do_cnae_da_secao():
    assert busca.divisoes("A") == ("01", "02", "03")
    assert busca.divisoes("Q") == ("86", "87", "88")
    for setor in busca.SETORES:
        assert all(
            cnae.secao_do_cnae(f"{d}00000") == cnae.SECOES[setor]
            for d in busca.divisoes(setor)
        )


def test_os_setores_sao_as_secoes_do_ibge_menos_as_fora_da_busca():
    assert set(busca.SETORES) == set(cnae.SECOES) - {"O", "T", "U"}
    assert busca.SETORES["Q"] == cnae.SECOES["Q"]


def test_a_idade_conta_de_hoje_e_aguenta_29_de_fevereiro():
    assert busca.aberta_ate(date(2026, 11, 10), 10) == date(2016, 11, 10)
    assert busca.aberta_ate(date(2028, 2, 29), 1) == date(2027, 2, 28)


def test_opcoes_e_limites_em_tipos_simples():
    assert busca.setores_como_lista()[0] == {"codigo": "A", "nome": cnae.SECOES["A"]}
    assert len(busca.UFS) == 27
    assert all(
        isinstance(limite, str) and limite.endswith(".") for limite in busca.LIMITES
    )
    assert not any(c.isdigit() for limite in busca.LIMITES for c in limite)


def test_legivel_poe_o_nome_ao_lado_do_codigo_sem_mudar_o_que_veio(pasta):
    (empresa,) = _buscar(pasta, setores=("J",)).corpo["empresas"]
    legivel = busca.legivel(empresa)
    assert (
        legivel["cnae_descricao"]
        == "Desenvolvimento de programas de computador sob encomenda"
    )
    assert legivel["municipio_nome"] == "BELO HORIZONTE"
    assert legivel["porte_descricao"] == "Demais"
    assert {k: v for k, v in legivel.items() if k in empresa} == empresa


def test_legivel_nao_inventa_nome_de_campo_que_o_portao_nao_serviu():
    so_o_cnpj = {"cnpj": "11111111000191"}
    assert busca.legivel(so_o_cnpj) == so_o_cnpj


def test_planilha_junta_as_paginas_ate_o_teto(pasta, monkeypatch):
    monkeypatch.setattr(busca, "TAMANHO_DA_PAGINA", 1)
    with Porta(pasta) as porta:
        filtros = busca.Filtros(ufs=("SP", "MG"))
        tudo = busca.para_planilha(porta, filtros, hoje=HOJE, regras=_regras())
        monkeypatch.setattr(busca, "PAGINAS_DA_PLANILHA", 1)
        cortada = busca.para_planilha(porta, filtros, hoje=HOJE, regras=_regras())
    assert [e["cnpj"] for e in tudo.corpo["empresas"]] == [
        "11111111000191",
        "22222222000191",
    ]
    assert tudo.corpo["cortada"] is False
    assert tudo.linhas == 2
    assert "proximo_cursor" not in tudo.corpo
    assert tudo.corpo["empresas"][0]["municipio_nome"] == "BELO HORIZONTE"
    assert [e["cnpj"] for e in cortada.corpo["empresas"]] == ["11111111000191"]
    assert cortada.corpo["cortada"] is True


def test_planilha_sem_filtro_ou_sem_prontidao_nao_le(pasta):
    with Porta(pasta) as porta:
        vazia = busca.para_planilha(porta, busca.Filtros(), hoje=HOJE, regras=_regras())
        negada = busca.para_planilha(
            porta, busca.Filtros(ufs=("SP",)), hoje=HOJE, regras=_sem_prontidao()
        )
    assert vazia.corpo is None and negada.corpo is None
