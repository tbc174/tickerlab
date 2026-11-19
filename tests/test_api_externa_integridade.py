"""CGU, IBAMA e MTE na análise completa, só no conjunto de integridade (ADR 0122, Emenda 1; linha 981).

Base de mentira, sem internet; os CNPJs são de ninguém e o CPF é o de exemplo de dígito certo. O leitor
(`conjuntos/por_tabela.py`) com a porta de verdade, e a rota da análise com o portão e as linhas de direito de
verdade. Riscos: linha de pessoa física saindo ou contando (a marca `trata_como_pessoa` verdadeira ou vazia), CPF
ou e-mail num texto servido (a rota cai, 503), olhar o futuro (o registro mensal vale do último dia do mês), bloco
fechado vazando pelo nome ou pelo tamanho (duas organizações, chave inválida, resposta idêntica com e sem o dado).
"""

import dataclasses
from datetime import date

import pandas as pd
import pytest

from base import prontidao
from base.porta import Porta
from base.prontidao import Prontidao, Prova
from src import portao_externo as portao
from src.api_externa import rotas, tabelas_por_cnpj
from src.api_externa.conjuntos import analise, ficha
from src.api_externa.pessoas import RespostaComPessoaProibida
from src.banco import coletas
from tests import ajudantes_da_api_externa as aj
from tests import test_api_externa_analise as analise_de_mentira
from tests import test_api_externa_socios_pj as socios_de_mentira
from tests.test_api_externa_tabelas_por_cnpj import (
    AGORA,
    DIA,
    EMPRESA,
    OUTRA_RAIZ,
    RAIZ,
    _ler,
    _organizacao,
    gravar,
)

SANCOES = "sancoes_cgu"
EMBARGOS = "ibama_embargos"
LISTA_SUJA = "mte_lista_suja"
CPF_DE_EXEMPLO = "111.444.777-35"  # dígito certo, de ninguém
DE_PESSOA = "ORGAO-DE-PESSOA"  # marca do texto que só a linha de pessoa tem
TABELAS = (SANCOES, EMBARGOS, LISTA_SUJA)
BLOCOS_DE_FORA = ("sanctions", "environmental_embargoes", "forced_labor_registry")
NOMES_DE_FORA = (
    *BLOCOS_DE_FORA,
    "cgu_sanctions",
    "ibama_embargoes",
    "mte_forced_labor_registry",
    "cgu-ceis",
    "ibama-embargos",
    "mte-lista-suja",
)


def _comum(tabela: pd.DataFrame) -> pd.DataFrame:
    for coluna in ("disponivel_em", "visto_em"):
        tabela[coluna] = pd.to_datetime(tabela[coluna]).dt.date
    return tabela.assign(
        cnpj_basico=tabela["cnpj"].str[:8],
        id_na_fonte=[f"id-{i}" for i in range(len(tabela))],
        origem_sha256="0" * 64,
    )


def _sancoes(texto_do_orgao: str = "MINISTERIO DE MENTIRA") -> pd.DataFrame:
    # fmt: off
    linhas = [
        # cadastro, cnpj, categoria, órgão, início, multa, disponível em, consta, é pessoa
        ("ceis", EMPRESA, "Inidoneidade", texto_do_orgao, "2024-01-10", None, "2024-02-05", True, False),
        ("cnep", EMPRESA, "Multa", "CONTROLADORIA", "2025-05-02", 1000.0, "2025-06-10", True, False),
        ("ceis", RAIZ + "000270", "Suspensão", DE_PESSOA, "2024-03-01", None, "2024-04-05", True, True),
        ("cepim", RAIZ + "000351", "Impedimento", DE_PESSOA, "2024-03-01", None, "2024-04-05", True, None),
        ("leniencia", EMPRESA, "Acordo", "SAIU-DO-ARQUIVO", "2023-01-01", None, "2023-02-01", False, False),
        ("ceis", OUTRA_RAIZ + "000100", "Suspensão", "OUTRA-EMPRESA", "2024-01-01", None, "2024-02-01", True, False),
    ]
    # fmt: on
    tabela = pd.DataFrame(
        linhas,
        columns=[
            "cadastro",
            "cnpj",
            "categoria",
            "orgao",
            "inicio",
            "valor_multa",
            "disponivel_em",
            "consta",
            "trata_como_pessoa",
        ],
    )
    tabela["inicio"] = pd.to_datetime(tabela["inicio"]).dt.date
    tabela["visto_em"] = tabela["disponivel_em"]
    return _comum(tabela).assign(situacao="Vigente", uf_do_orgao="SP")


def _embargos() -> pd.DataFrame:
    tabela = pd.DataFrame(
        {
            "cnpj": [EMPRESA, RAIZ + "000270"],
            "numero_do_termo": ["T-1", "T-PESSOA"],
            "nome": ["EMPRESA DE MENTIRA", "FULANO DE TAL"],
            "embargada_em": pd.to_datetime(["2024-05-01", "2024-05-01"]).date,
            "area_embargada_ha": [12.5, 3.0],
            "uf": ["MT", "MT"],
            "disponivel_em": ["2024-06-03", "2024-06-03"],
            "consta": [True, True],
            "trata_como_pessoa": [False, True],
        }
    )
    tabela["visto_em"] = tabela["disponivel_em"]
    return _comum(tabela)


def _lista_suja() -> pd.DataFrame:
    tabela = pd.DataFrame(
        {
            "cnpj": [OUTRA_RAIZ + "000100", RAIZ + "000270"],
            "ano_da_acao": [2023, 2023],
            "uf": ["PA", "PA"],
            "empregador": ["OUTRA EMPRESA", "FULANO DE TAL"],
            "estabelecimento": ["FAZENDA X", "FAZENDA Y"],
            "cnae": ["0151201", "0151201"],
            "trabalhadores": [7, 4],
            "incluida_em": pd.to_datetime(["2024-04-05", "2024-04-05"]).date,
            "disponivel_em": ["2024-04-10", "2024-04-10"],
            "consta": [True, True],
            "trata_como_pessoa": [False, True],
        }
    )
    tabela["visto_em"] = tabela["disponivel_em"]
    return _comum(tabela)


def _gravar_tudo(pasta, sancoes: pd.DataFrame | None = None) -> None:
    gravar(pasta, SANCOES, _sancoes() if sancoes is None else sancoes)
    gravar(pasta, EMBARGOS, _embargos())
    gravar(pasta, LISTA_SUJA, _lista_suja())


@pytest.fixture
def base(tmp_path):
    pasta = tmp_path / "base"
    _gravar_tudo(pasta)
    return pasta


def _corpo(pasta, bloco, dia=DIA):
    lido = _ler(pasta, bloco, dia=dia)
    assert lido is not None
    return lido


# ---------------------------------------------------------------- o registro e as marcas


def test_as_tres_tabelas_estao_so_no_conjunto_de_integridade_com_a_marca_de_pessoa():
    entradas = {
        e.tabela: e
        for e in tabelas_por_cnpj.REGISTRO
        if e.conjunto == tabelas_por_cnpj.INTEGRIDADE
    }
    assert set(entradas) == set(TABELAS)
    for entrada in entradas.values():
        assert entrada.marca_de_pessoa == tabelas_por_cnpj.TRATA_COMO_PESSOA
        assert entrada.onde_sai == tabelas_por_cnpj.ANALISE
        assert set(entrada.campos).isdisjoint(
            {"nome", "empregador", "estabelecimento", "processo", "cnpj"}
        )


def test_fora_do_conjunto_de_integridade_a_marca_continua_de_uso_interno():
    for fonte in ("cgu-ceis", "ibama-embargos", "mte-lista-suja"):
        assert coletas.sai_no_conjunto_de_integridade(
            fonte, coletas.CONJUNTO_DE_INTEGRIDADE
        )
        assert not coletas.sai_no_conjunto_de_integridade(fonte, "profiles")
    assert not coletas.sai_no_conjunto_de_integridade(
        "cvm-hist-dfp", coletas.CONJUNTO_DE_INTEGRIDADE
    )


def test_o_mte_sai_como_publicado_e_toda_fonte_tem_atribuicao():
    from src.api_externa.envelope import ATRIBUICOES_DA_API

    assert "mte-lista-suja" in portao.SO_COMO_PUBLICADO
    for entrada in tabelas_por_cnpj.REGISTRO:
        if entrada.conjunto == tabelas_por_cnpj.INTEGRIDADE:
            for fonte in entrada.fontes:
                assert ATRIBUICOES_DA_API[fonte]


def test_ainda_nao_traz_tira_so_a_linha_do_bloco_aberto():
    todas = analise.ainda_nao_traz(())
    assert todas == list(analise.AINDA_NAO_TRAZ)
    sem_cgu = analise.ainda_nao_traz((tabelas_por_cnpj.SANCOES,))
    assert len(sem_cgu) == len(todas) - 1
    assert not any("(CGU)" in frase for frase in sem_cgu)
    assert any("(IBAMA)" in frase for frase in sem_cgu)


# ---------------------------------------------------------------- o leitor


def test_so_a_linha_de_empresa_sai_e_a_de_pessoa_nao_conta(base):
    lido = _corpo(base, tabelas_por_cnpj.SANCOES)
    sub = lido.corpo["sancoes_da_cgu"]
    assert sub["achou"] is True
    assert [item["categoria"]["valor"] for item in sub["itens"]] == [
        "Multa",
        "Inidoneidade",
    ]
    assert lido.linhas == 2  # as duas de pessoa (marca verdadeira e vazia) nem contam
    texto = str(lido.corpo)
    for fora in (DE_PESSOA, "SAIU-DO-ARQUIVO", "OUTRA-EMPRESA"):
        assert fora not in texto
    assert lido.fontes == {"cgu-ceis", "cgu-cnep"}


def test_embargo_e_lista_suja_sem_nome_nem_linha_de_pessoa(base):
    embargos = _corpo(base, tabelas_por_cnpj.EMBARGOS_AMBIENTAIS).corpo
    itens = embargos["embargos_do_ibama"]["itens"]
    assert [i["numero_do_termo"]["valor"] for i in itens] == ["T-1"]
    assert "FULANO" not in str(embargos) and "EMPRESA DE MENTIRA" not in str(embargos)
    lista = _corpo(base, tabelas_por_cnpj.LISTA_SUJA)
    sub = lista.corpo["lista_suja_do_mte"]
    assert sub["achou"] is False  # nada encontrado: só a de outra empresa e a de pessoa
    assert sub["itens"] == [] and sub["cobertura"]
    assert lista.linhas == 0
    assert "FULANO" not in str(lista.corpo) and "FAZENDA" not in str(lista.corpo)


def _lista_com_saida() -> pd.DataFrame:
    """Dois registros da empresa (um saiu da lista em 10/10/2024) e um de pessoa visto depois."""
    # fmt: off
    linhas = [
        # id, cnpj, ano da ação, inclusão, visto em, consta, é pessoa
        ("id-a", EMPRESA, 2022, "2023-10-05", "2023-10-10", True, False),
        ("id-a", EMPRESA, 2022, "2023-10-05", "2024-10-10", False, False),  # saiu da lista
        ("id-b", EMPRESA, 2024, "2024-04-05", "2024-04-10", True, False),
        ("id-c", RAIZ + "000270", 2024, "2025-01-10", "2025-01-15", True, True),
    ]
    # fmt: on
    tabela = pd.DataFrame(
        linhas,
        columns=[
            "id_na_fonte",
            "cnpj",
            "ano_da_acao",
            "incluida_em",
            "visto_em",
            "consta",
            "trata_como_pessoa",
        ],
    )
    tabela["incluida_em"] = pd.to_datetime(tabela["incluida_em"]).dt.date
    tabela["disponivel_em"] = tabela["visto_em"]
    ids = tabela.pop("id_na_fonte")
    return _comum(tabela.assign(uf="PA", cnae="0151201", trabalhadores=3)).assign(
        id_na_fonte=ids
    )


def test_a_lista_suja_diz_o_retrato_e_o_registro_que_saiu_nao_aparece(tmp_path):
    pasta = tmp_path / "base"
    gravar(pasta, LISTA_SUJA, _lista_com_saida())
    sub = _corpo(pasta, tabelas_por_cnpj.LISTA_SUJA).corpo["lista_suja_do_mte"]
    assert [i["ano_da_acao"]["valor"] for i in sub["itens"]] == [
        2024
    ]  # 2022 saiu: nem como fato atual
    # a mudança mais nova da lista é a saída de 10/10/2024; a linha de pessoa (15/01/2025) não conta
    assert sub["retrato_da_lista"] == "2024-10-10"
    antes = _corpo(pasta, tabelas_por_cnpj.LISTA_SUJA, dia=date(2024, 6, 30)).corpo[
        "lista_suja_do_mte"
    ]
    assert sorted(i["ano_da_acao"]["valor"] for i in antes["itens"]) == [
        2022,
        2024,
    ]  # em 06/2024 constava
    assert antes["retrato_da_lista"] == "2024-04-10"


def test_so_a_lista_suja_leva_o_retrato(base):
    for bloco, chave in (
        (tabelas_por_cnpj.SANCOES, "sancoes_da_cgu"),
        (tabelas_por_cnpj.EMBARGOS_AMBIENTAIS, "embargos_do_ibama"),
    ):
        assert "retrato_da_lista" not in _corpo(base, bloco).corpo[chave]


def test_tabela_sem_a_coluna_da_marca_responde_nao_achou(tmp_path):
    pasta = tmp_path / "sem_marca"
    gravar(pasta, SANCOES, _sancoes().drop(columns=["trata_como_pessoa"]))
    sub = _corpo(pasta, tabelas_por_cnpj.SANCOES).corpo["sancoes_da_cgu"]
    assert sub["achou"] is False and sub["itens"] == []


@pytest.mark.parametrize(
    "texto", [f"MINISTERIO {CPF_DE_EXEMPLO}", "11144477735", "fulano@exemplo.com"]
)
def test_cpf_ou_email_num_texto_servido_derruba_a_leitura(tmp_path, texto):
    pasta = tmp_path / "com_cpf"
    gravar(pasta, SANCOES, _sancoes(texto))
    with pytest.raises(RespostaComPessoaProibida) as erro:
        _ler(pasta, tabelas_por_cnpj.SANCOES)
    assert erro.value.caminhos == ["sancoes_da_cgu.orgao"]
    assert texto not in str(erro.value)


def test_o_registro_mensal_vale_do_ultimo_dia_do_mes(base):
    antes = _corpo(base, tabelas_por_cnpj.SANCOES, dia=date(2025, 6, 20)).corpo
    assert "Multa" not in str(
        antes
    )  # disponível em 10/06, público pela porta só em 30/06
    depois = _corpo(base, tabelas_por_cnpj.SANCOES, dia=date(2025, 6, 30)).corpo
    multa = depois["sancoes_da_cgu"]["itens"][0]
    assert multa["categoria"]["valor"] == "Multa"
    assert multa["categoria"]["publico_em"] == "2025-06-30"
    assert multa["categoria"]["fonte"] == "cgu-cnep"


def test_cortar_o_futuro_nao_muda_o_passado(tmp_path, base):
    sem_futuro = tmp_path / "sem"
    dia = date(2024, 12, 31)
    publico = lambda t: t[t["disponivel_em"] <= dia]
    gravar(sem_futuro, SANCOES, publico(_sancoes()))
    gravar(sem_futuro, EMBARGOS, publico(_embargos()))
    gravar(sem_futuro, LISTA_SUJA, publico(_lista_suja()))
    for bloco in (
        tabelas_por_cnpj.SANCOES,
        tabelas_por_cnpj.EMBARGOS_AMBIENTAIS,
        tabelas_por_cnpj.LISTA_SUJA,
    ):
        assert (
            _ler(sem_futuro, bloco, dia=dia).corpo == _ler(base, bloco, dia=dia).corpo
        )  # type: ignore[union-attr]


# ---------------------------------------------------------------- a análise, com o portão de verdade


def _regras() -> portao.Regras:
    """As regras de verdade com o perfil e as três tabelas com a prontidão cheia, a leitura dos termos em dia e a
    coleta e guarda do MTE respondidas (a prova com a data do teste), para ver o que o conjunto abre; hoje a
    produção nega só pela prontidão (as marcas, a leitura dos termos e a guarda já passam)."""
    prova = Prova(AGORA.date(), "conferida no teste", "teste")
    versoes = prontidao.versoes_maiores()
    vigentes = portao.regras_vigentes()
    cheias = (*analise_de_mentira.DO_PERFIL, *TABELAS)
    return dataclasses.replace(
        vigentes,
        prontidao={t: Prontidao(versoes[t], prova, prova, prova) for t in cheias},
        termos_lidos_em={
            **vigentes.termos_lidos_em,
            **dict.fromkeys(("cgu", "ibama", "mte"), AGORA.date()),
        },
        coleta_e_guarda={
            **vigentes.coleta_e_guarda,
            "mte": coletas.ColetaEGuarda(
                coletas.Coleta.ABERTA, coletas.Guarda.SEM_PRAZO
            ),
        },
    )


def _analise(monkeypatch, valor_da_chave, regras=_regras):
    monkeypatch.setattr(rotas, "regras_da_api", regras)
    cliente = aj.cliente_da_api(monkeypatch, AGORA)
    return cliente.get(
        f"/data/v1/companies/{EMPRESA}/analysis",
        params={"known_at": DIA.isoformat()},
        headers=aj.bearer(valor_da_chave),
    )


def _pasta(tmp_path, monkeypatch, nome="base", sancoes=None, com_dado=True):
    pasta = socios_de_mentira.base_com_socios(tmp_path / nome)
    if com_dado:
        _gravar_tudo(pasta, sancoes)
    monkeypatch.setattr(rotas, "abrir_porta", lambda banco_: Porta(pasta, banco_))
    return pasta


def test_com_o_conjunto_os_tres_blocos_saem_com_fonte_e_data(
    tmp_path, banco, monkeypatch
):
    _pasta(tmp_path, monkeypatch)
    ator = aj.admin(banco)
    chave = _organizacao(
        banco, ator, "Alfa", ficha.CONJUNTO, tabelas_por_cnpj.INTEGRIDADE
    )
    resposta = _analise(monkeypatch, chave.valor)
    assert resposta.status_code == 200
    corpo = resposta.json()
    sancoes = corpo["blocks"]["sanctions"]["cgu_sanctions"]
    assert sancoes["found"] is True
    multa = sancoes["items"][0]
    assert multa["category"]["value"] == "Multa"
    assert multa["category"]["source"] == "cgu-cnep"
    assert multa["category"]["published_at"] == "2025-06-30"
    assert multa["fine_brl"]["value"] == 1000.0
    embargo = corpo["blocks"]["environmental_embargoes"]["ibama_embargoes"]["items"][0]
    assert embargo["embargo_term_number"]["value"] == "T-1"
    nao_achados = {item["block"] for item in corpo["not_found"]}
    assert nao_achados == {"forced_labor_registry"}  # nada encontrado no MTE
    lista = corpo["blocks"]["forced_labor_registry"]["mte_forced_labor_registry"]
    assert lista["found"] is False and lista["list_snapshot_date"] == "2024-04-10"
    fontes = {f["source"] for f in corpo["sources"]}
    assert {"cgu-cnep", "cgu-ceis", "ibama-embargos"} <= fontes
    fora = " ".join(corpo["not_included"])
    for orgao in ("(CGU)", "(IBAMA)", "(MTE)"):
        assert (
            orgao not in fora
        )  # o bloco foi consultado: sai da lista do que não consulta
    texto = resposta.text
    for nunca in (DE_PESSOA, "FULANO", "FAZENDA", "EMPRESA DE MENTIRA", CPF_DE_EXEMPLO):
        assert nunca not in texto


def test_sem_o_conjunto_nada_aparece_nem_pelo_nome_nem_pelo_tamanho(
    tmp_path, banco, monkeypatch
):
    ator = aj.admin(banco)
    chave = _organizacao(banco, ator, "Beta", ficha.CONJUNTO)
    respostas = []
    for nome, com_dado in (("com", True), ("sem", False)):
        _pasta(tmp_path, monkeypatch, nome, com_dado=com_dado)
        resposta = _analise(monkeypatch, chave.valor)
        assert resposta.status_code == 200
        respostas.append(resposta.content)
    assert respostas[0] == respostas[1]
    texto = respostas[0].decode()
    for nome in NOMES_DE_FORA:
        assert nome not in texto
    marcados = [
        frase
        for frase in _analise(monkeypatch, chave.valor).json()["not_included"]
        if frase.endswith(": não disponível nesta chave")
    ]
    assert len(marcados) == 3


def test_o_conjunto_de_outra_organizacao_nao_abre_nada(tmp_path, banco, monkeypatch):
    _pasta(tmp_path, monkeypatch)
    ator = aj.admin(banco)
    _organizacao(banco, ator, "Alfa", ficha.CONJUNTO, tabelas_por_cnpj.INTEGRIDADE)
    beta = _organizacao(banco, ator, "Beta", ficha.CONJUNTO)
    texto = _analise(monkeypatch, beta.valor).text
    for nome in NOMES_DE_FORA:
        assert nome not in texto


def test_chave_invalida_nao_ve_nada(tmp_path, monkeypatch):
    _pasta(tmp_path, monkeypatch)
    resposta = _analise(monkeypatch, "tl_chave_que_nao_existe")
    assert resposta.status_code == 401
    for nome in NOMES_DE_FORA:
        assert nome not in resposta.text


def test_sem_a_prontidao_o_conjunto_nao_libera_como_hoje_em_producao(
    tmp_path, banco, monkeypatch
):
    _pasta(tmp_path, monkeypatch)
    ator = aj.admin(banco)
    chave = _organizacao(
        banco, ator, "Alfa", ficha.CONJUNTO, tabelas_por_cnpj.INTEGRIDADE
    )
    so_o_perfil = lambda: dataclasses.replace(
        _regras(),
        prontidao={t: p for t, p in _regras().prontidao.items() if t not in TABELAS},
    )
    texto = _analise(monkeypatch, chave.valor, regras=so_o_perfil).text
    for nome in NOMES_DE_FORA:
        assert nome not in texto


def test_cpf_num_texto_servido_responde_503_sem_o_valor(tmp_path, banco, monkeypatch):
    _pasta(tmp_path, monkeypatch, sancoes=_sancoes(f"ORGAO {CPF_DE_EXEMPLO}"))
    ator = aj.admin(banco)
    chave = _organizacao(
        banco, ator, "Alfa", ficha.CONJUNTO, tabelas_por_cnpj.INTEGRIDADE
    )
    resposta = _analise(monkeypatch, chave.valor)
    assert resposta.status_code == 503
    assert CPF_DE_EXEMPLO not in resposta.text
    assert "11144477735" not in resposta.text
