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
from base.prontidao import AVISO_DE_PILOTO, Prontidao, ProntidaoDePiloto, Prova
from src import portao_externo as portao
from src.analista import busca, leitura
from src.api_externa import piloto as piloto_
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


def _buscar(pasta, regras=None, hoje=HOJE, piloto=False, **filtros):
    with Porta(pasta) as porta:
        return busca.buscar(
            porta,
            busca.Filtros(**filtros),
            hoje=hoje,
            regras=regras or _regras(),
            piloto=piloto,
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


def test_capital_e_estabelecimentos_filtram_e_saem_com_fonte(pasta):
    # outubro: ALFA (MG) com capital de 6 milhões e um estabelecimento ativo; BETA (SP) com 100 mil e um
    assert _cnpjs(_buscar(pasta, capital_minimo=1_000_000)) == ["11111111000191"]
    assert _cnpjs(_buscar(pasta, ufs=("SP", "MG"), capital_maximo=200_000)) == [
        "22222222000191"
    ]
    assert _cnpjs(_buscar(pasta, ufs=("SP", "MG"), estabelecimentos_minimo=2)) == []
    (empresa,) = _buscar(pasta, setores=("J",)).corpo["empresas"]
    assert empresa["capital_social"]["valor"] == 6_000_000.0
    assert empresa["capital_social"]["fonte"] == "rfb-cnpj"
    assert empresa["n_estabelecimentos"]["valor"] == 1


def test_ordem_por_capital_com_cursor(pasta, monkeypatch):
    todas = ("SP", "MG")
    assert _cnpjs(_buscar(pasta, ufs=todas, ordem="maior_capital")) == [
        "11111111000191",
        "22222222000191",
    ]
    assert _cnpjs(_buscar(pasta, ufs=todas, ordem="menor_capital")) == [
        "22222222000191",
        "11111111000191",
    ]
    monkeypatch.setattr(busca, "TAMANHO_DA_PAGINA", 1)
    primeira = _buscar(pasta, ufs=todas, ordem="menor_capital")
    assert _cnpjs(primeira) == ["22222222000191"]
    cursor = primeira.corpo["proximo_cursor"]
    segunda = _buscar(pasta, ufs=todas, ordem="menor_capital", cursor=cursor)
    assert _cnpjs(segunda) == ["11111111000191"]
    # o cursor de uma ordem não serve para outra
    with pytest.raises(busca.FiltroInvalido):
        _buscar(pasta, ufs=todas, cursor=cursor)


def test_a_ordem_sozinha_nao_e_filtro(pasta):
    assert _buscar(pasta, ordem="maior_capital").estado == busca.SEM_FILTRO


def test_tabela_sem_capital_nao_responde_ao_filtro_de_capital(tmp_path):
    # a tabela montada antes da linha 584 não tem as colunas: a tela diz "não liberado", nunca inventa
    base = tmp_path / "base"
    base_de_mentira._gravar(
        base, prospeccao.ESTABELECIMENTOS, base_de_mentira._estabelecimentos()
    )
    antiga = base_de_mentira._empresas().drop(
        columns=["capital_social", "n_estabelecimentos"]
    )
    base_de_mentira._gravar(base, prospeccao.EMPRESAS, antiga)
    resposta = _buscar(base, capital_minimo=1)
    assert resposta == leitura.Resposta(leitura.NAO_LIBERADA)
    assert _cnpjs(_buscar(base, ufs=("SP",))) == ["22222222000191"]


def test_as_ordens_da_tela_sao_as_da_api():
    assert [o["codigo"] for o in busca.ordens_como_lista()] == list(busca.ORDENS)
    for codigo, (ordem_da_api, _nome) in busca.ORDENS.items():
        assert prospeccao.busca_dos_pedidos(
            cnae=[], state=["SP"], municipality=[], size=[], legal_nature=[],
            registration_status=[], opened_before=None, opened_after=None,
            head_office=True, cursor=None, limit=None, sort=ordem_da_api,
        ).ordem, codigo  # fmt: skip


def test_os_limites_dizem_que_capital_e_so_aproximacao_e_nao_mede_faturamento():
    texto = " ".join(busca.LIMITES).lower()
    assert "aproximação" in texto and "capital social" in texto
    assert "nenhum dos dois mede faturamento" in texto


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
        {"capital_minimo": -1},
        {"capital_minimo": 2_000_000, "capital_maximo": 1_000_000},
        {"capital_maximo": 1e16},
        {"estabelecimentos_minimo": 0},
        {"ufs": ("SP",), "ordem": "faturamento"},
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


# ---------------------------------------------------------------- piloto (D11)


def _so_de_piloto() -> portao.Regras:
    """Como a produção em 13/11/2026: nenhuma tabela com a prontidão cheia; as da busca só no registro de
    piloto."""
    prova = Prova(HOJE, "conferida no teste", "teste")
    versoes = prontidao.versoes_maiores()
    tabelas = (prospeccao.ESTABELECIMENTOS, prospeccao.EMPRESAS)
    return dataclasses.replace(
        portao.regras_vigentes(),
        prontidao={},
        prontidao_de_piloto={
            t: ProntidaoDePiloto(versoes[t], prova, prova) for t in tabelas
        },
    )


def _envelopes(empresa: dict) -> list[dict]:
    return [valor for valor in empresa.values() if isinstance(valor, dict)]


def test_conta_do_piloto_busca_com_o_aviso_em_todo_campo_e_no_topo(pasta):
    resposta = _buscar(pasta, _so_de_piloto(), piloto=True, setores=("J",))
    assert resposta.estado == leitura.PRONTA
    assert _cnpjs(resposta) == ["11111111000191"]
    # D11.3: bloco de piloto sem o aviso é defeito
    assert resposta.corpo[piloto_.AVISO] == AVISO_DE_PILOTO
    (empresa,) = resposta.corpo["empresas"]
    assert _envelopes(empresa)
    for envelope in _envelopes(empresa):
        assert envelope[piloto_.MARCA] is True
        assert envelope[piloto_.AVISO] == AVISO_DE_PILOTO


def test_so_com_o_registro_de_piloto_a_conta_comum_continua_sem_a_busca(pasta):
    resposta = _buscar(pasta, _so_de_piloto(), setores=("J",))
    assert resposta.estado == leitura.NAO_LIBERADA
    assert resposta.corpo is None and resposta.fontes == []


def test_conta_do_piloto_sem_registro_de_piloto_continua_sem_a_busca(pasta):
    resposta = _buscar(pasta, _sem_prontidao_nem_piloto(), piloto=True, ufs=("SP",))
    assert resposta.estado == leitura.NAO_LIBERADA


def _sem_prontidao_nem_piloto() -> portao.Regras:
    return dataclasses.replace(_sem_prontidao(), prontidao_de_piloto={})


def test_prontidao_cheia_sai_sem_aviso_de_piloto_ate_para_a_conta_do_piloto(pasta):
    resposta = _buscar(pasta, piloto=True, setores=("J",))
    assert resposta.estado == leitura.PRONTA
    assert piloto_.AVISO not in resposta.corpo
    (empresa,) = resposta.corpo["empresas"]
    assert all(piloto_.MARCA not in envelope for envelope in _envelopes(empresa))


def test_portao_da_tela_nao_serve_piloto_sem_o_registro_que_marca_o_aviso():
    # quem chama sem abrir `piloto.anotar()` não tem como pôr o aviso: o campo de piloto não sai
    permitido = leitura.permitido_na_tela(
        prospeccao.CONJUNTO, HOJE, _so_de_piloto(), piloto=True
    )
    assert permitido(prospeccao.FONTE, "razao_social", False) is False
    with piloto_.anotar():
        aberto = leitura.permitido_na_tela(
            prospeccao.CONJUNTO, HOJE, _so_de_piloto(), piloto=True
        )
        assert aberto(prospeccao.FONTE, "razao_social", False) is True


def test_planilha_do_piloto_leva_o_aviso_em_todas_as_paginas(pasta, monkeypatch):
    monkeypatch.setattr(busca, "TAMANHO_DA_PAGINA", 1)
    with Porta(pasta) as porta:
        resposta = busca.para_planilha(
            porta,
            busca.Filtros(ufs=("SP", "MG")),
            hoje=HOJE,
            regras=_so_de_piloto(),
            piloto=True,
        )
    assert _cnpjs(resposta) == ["11111111000191", "22222222000191"]
    assert resposta.corpo[piloto_.AVISO] == AVISO_DE_PILOTO
    for empresa in resposta.corpo["empresas"]:
        assert all(envelope[piloto_.MARCA] for envelope in _envelopes(empresa))
