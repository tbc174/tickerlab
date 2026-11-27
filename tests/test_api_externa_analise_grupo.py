"""Fila 1036: holdings e conferências do grupo, só empresas fictícias, sem internet."""

import dataclasses
import threading
import time

import pandas as pd
import pytest

from base.porta import Porta
from src.api_externa import rotas, tabelas_por_cnpj
from src.api_externa.conjuntos import analise, compradores, empresas, ficha, por_tabela
from src.api_externa.nomes import traduzir_chaves
from tests import ajudantes_da_api_externa as aj
from tests import test_api_externa_empresas as cadastro
from tests import test_api_externa_integridade as integridade
from tests import test_api_externa_por_cnpj_ficha as perfil
from tests import test_api_externa_socios_pj as socios

RAIZ = socios.RAIZ
HOLDING, ACIMA = socios.HOLDING, socios.VELHA
DIA = socios.DIA
ABERTURAS = {RAIZ: "2010-05-01", HOLDING: "2007-03-02", ACIMA: "2001-02-03"}
LIGACOES = [
    (HOLDING, RAIZ, "2012-01-01", "2023-05", "2023-06-30", "entrou"),
    (ACIMA, HOLDING, "2013-01-01", "2023-05", "2023-06-30", "entrou"),
    (socios.FUTURA, ACIMA, "2025-07-01", "2025-07", "2025-08-31", "entrou"),
    (socios.EMPRESARIO, HOLDING, "2014-01-01", "2023-05", "2023-06-30", "entrou"),
    (socios.SEM_LISTA, ACIMA, "2014-01-01", "2023-05", "2023-06-30", "entrou"),
]


def gravar_grupo(tmp_path, ligacoes=LIGACOES, extras=()):
    pasta = socios.base_com_socios(tmp_path)
    socios.gravar_socios(pasta, socios._entradas(ligacoes))
    if extras:
        lista = socios._lista() + [
            (raiz, f"EMPRESA FICTICIA {i}", "2062", "05", mes, publico)
            for i, raiz in enumerate(extras)
            for mes, publico in socios.MESES
        ]
        cadastro._lista_pj(lista).to_parquet(
            pasta / empresas.LISTA_DE_EMPRESAS / "00.parquet", index=False
        )
    linhas = [
        (raiz + "000191", mes, publico, abertura, "6462000", "SP", "7107")
        for raiz, abertura in ABERTURAS.items()
        for mes, publico in (("2025-01", "2025-01-31"), ("2025-07", "2025-07-31"))
    ]
    perfil._estabelecimentos(linhas).to_parquet(
        pasta / ficha.TABELA_DO_ESTABELECIMENTO / f"{RAIZ[:2]}.parquet", index=False
    )
    # Só linhas de PJ, com um achado em cada holding e nenhum no CNPJ consultado.
    for tabela, dados, raiz in (
        (integridade.SANCOES, integridade._sancoes().iloc[:1].copy(), HOLDING),
        (integridade.EMBARGOS, integridade._embargos().iloc[:1].copy(), ACIMA),
        (integridade.LISTA_SUJA, integridade._lista_suja().iloc[:1].copy(), ACIMA),
    ):
        dados["cnpj"] = raiz + "000191"
        dados["cnpj_basico"] = raiz
        integridade.gravar(pasta, tabela, dados)
    return pasta


@pytest.fixture
def pasta(tmp_path):
    return gravar_grupo(tmp_path)


def montar(
    pasta, *, dia=DIA, grupo=True, conferir=True, linhas=10, portao=None, prazo=20
):
    liberadas = {(ficha.CONJUNTO, analise.ANALISE, "rfb-cnpj", "razao_social")}
    if grupo:
        liberadas |= {
            (compradores.CONJUNTO, analise.ANALISE, f, c)
            for f, c in socios.socios_pj.CAMPOS
        }
    if conferir:
        liberadas |= {
            (e.conjunto, analise.ANALISE, f, c)
            for e in tabelas_por_cnpj.REGISTRO
            if e.conjunto == tabelas_por_cnpj.INTEGRIDADE
            for f, c in por_tabela.pares(e)
        }
    with Porta(pasta) as porta:
        return analise.montar_analise(
            socios.EMPRESA,
            dia,
            porta=porta,
            liberadas=liberadas,
            portao=portao or (lambda *_: lambda *_: True),
            linhas=linhas,
            prazo=prazo,
        )


def test_analise_sobe_duas_holdings_com_abertura_atividade_e_datas(pasta):
    resultado = montar(pasta)
    grupo = resultado.corpo["blocos"]["socios_pj"]["grupo"]
    por_raiz = {e["raiz_do_cnpj"]: e for e in grupo["empresas"]}
    assert set(por_raiz) == set(ABERTURAS)
    for raiz, abertura in ABERTURAS.items():
        assert por_raiz[raiz]["data_inicio_atividade"]["valor"] == abertura
        assert por_raiz[raiz]["cnae_principal"]["valor"] == "6462000"
        assert por_raiz[raiz]["data_inicio_atividade"]["publico_em"] <= DIA.isoformat()
    assert grupo["completo"] is True
    assert len(grupo["ligacoes"]) == 2
    assert por_raiz[ACIMA]["passos"] == 2
    assert {r: e["papel"] for r, e in por_raiz.items()} == {
        RAIZ: "alvo",
        HOLDING: "holding nível 1",
        ACIMA: "holding nível 2",
    }
    assert grupo["tipo"] == "inference"
    assert any(
        l["tipo"] == "inference" and "composição do grupo" in l["texto"]
        for l in resultado.corpo["leituras"]
    )
    texto = str(grupo)
    assert (
        socios.FUTURA not in texto
        and socios.EMPRESARIO not in texto
        and socios.SEM_LISTA not in texto
    )


@pytest.mark.parametrize(
    "bloco,chave,raiz",
    [
        (tabelas_por_cnpj.SANCOES, "sancoes_da_cgu", HOLDING),
        (tabelas_por_cnpj.EMBARGOS_AMBIENTAIS, "embargos_do_ibama", ACIMA),
        (tabelas_por_cnpj.LISTA_SUJA, "lista_suja_do_mte", ACIMA),
    ],
)
def test_conferencias_alcancam_as_holdings_sem_atribuir_o_achado_a_consultada(
    pasta, bloco, chave, raiz
):
    resultado = montar(pasta)
    corpo = resultado.corpo["blocos"][bloco]
    assert corpo[chave]["achou"] is False
    por_raiz = {e["raiz_do_cnpj"]: e for e in corpo["conferencias_do_grupo"]}
    assert set(por_raiz) == set(ABERTURAS)
    assert por_raiz[raiz]["resultado"][chave]["achou"] is True
    assert por_raiz[RAIZ]["resultado"][chave]["achou"] is False
    assert traduzir_chaves({bloco: 0}).keys() <= {
        i["bloco"] for i in resultado.corpo["nao_encontrado"]
    }
    assert resultado.consumo[(tabelas_por_cnpj.INTEGRIDADE, analise.ANALISE)][0] == 3


def test_sem_contrato_do_grupo_nao_inclui_holdings_nas_conferencias(pasta):
    corpo = montar(pasta, grupo=False).corpo
    assert "socios_pj" not in corpo["blocos"]
    assert "conferencias_do_grupo" not in str(corpo)
    assert HOLDING not in str(corpo) and ACIMA not in str(corpo)


def test_sem_integridade_o_grupo_nao_abre_conferencias(pasta):
    corpo = montar(pasta, conferir=False).corpo
    assert "grupo" in corpo["blocos"]["socios_pj"]
    assert tabelas_por_cnpj.SANCOES not in corpo["blocos"]


def test_campo_do_cadastro_negado_nao_sai_pelo_contrato_de_socios(pasta):
    def portao(conjunto, _finalidade):
        return lambda _fonte, campo, _derivado: (
            conjunto != ficha.CONJUNTO or campo != "data_inicio_atividade"
        )

    grupo = montar(pasta, portao=portao).corpo["blocos"]["socios_pj"]["grupo"]
    assert all("data_inicio_atividade" not in e for e in grupo["empresas"])


def test_limite_do_grupo_avisa_que_as_conferencias_sao_parciais(pasta):
    corpo = montar(pasta, linhas=2).corpo
    grupo = corpo["blocos"]["socios_pj"]["grupo"]
    assert len(grupo["empresas"]) == 2 and grupo["completo"] is False
    assert corpo["blocos"][tabelas_por_cnpj.SANCOES]["grupo_completo"] is False


def test_cortar_ligacoes_futuras_nao_muda_a_analise(tmp_path, pasta):
    sem = gravar_grupo(
        tmp_path / "sem", [l for l in LIGACOES if l[4] <= DIA.isoformat()]
    )
    assert montar(sem).corpo == montar(pasta).corpo


def test_ciclo_societario_nao_repete_empresa_nem_trava(tmp_path):
    ciclo = (RAIZ, ACIMA, "2014-01-01", "2023-05", "2023-06-30", "entrou")
    pasta = gravar_grupo(tmp_path, [*LIGACOES, ciclo])
    grupo = montar(pasta).corpo["blocos"]["socios_pj"]["grupo"]
    assert len(grupo["empresas"]) == 3 and len(grupo["ligacoes"]) == 3
    assert grupo["completo"] is True


def test_grupo_lento_nao_vira_ausencia_de_sancao_nem_prende_a_analise(
    pasta, monkeypatch
):
    from src.api_externa.conjuntos import grupo_da_analise

    liberado = threading.Event()
    original = grupo_da_analise.ampliar

    def lento(*args):
        liberado.wait(5)
        return original(*args)

    monkeypatch.setattr(grupo_da_analise, "ampliar", lento)
    # Dado da própria alvo deve sobreviver ao atraso do grupo.
    integridade.gravar(
        pasta, integridade.SANCOES, integridade._sancoes().iloc[:1].copy()
    )
    inicio = time.monotonic()
    try:
        corpo = montar(pasta, prazo=1).corpo
        assert time.monotonic() - inicio < 3
        atrasados = {b["bloco"] for b in corpo["nao_respondeu_a_tempo"]}
        assert atrasados == {"corporate_ownership"}
        sancoes = corpo["blocos"][tabelas_por_cnpj.SANCOES]
        assert sancoes["sancoes_da_cgu"]["achou"] is True
        assert sancoes["estado_conferencias_do_grupo"] == "timed_out"
        assert sancoes["conferencias_do_grupo"] == []
    finally:
        liberado.set()


def test_contrato_do_grupo_e_integridade_sao_isolados_por_organizacao(
    pasta, banco, monkeypatch
):
    from base.prontidao import Prontidao, Prova, versoes_maiores

    regras = integridade._regras()
    prova = Prova(integridade.AGORA.date(), "teste", "teste")
    regras = dataclasses.replace(
        regras,
        prontidao={
            **regras.prontidao,
            compradores.ENTRADAS: Prontidao(
                versoes_maiores()[compradores.ENTRADAS], prova, prova, prova
            ),
        },
    )
    monkeypatch.setattr(rotas, "abrir_porta", lambda b: Porta(pasta, b))
    ator = aj.admin(banco)
    completa = integridade._organizacao(
        banco,
        ator,
        "Grupo com conferencias",
        ficha.CONJUNTO,
        compradores.CONJUNTO,
        tabelas_por_cnpj.INTEGRIDADE,
    )
    simples = integridade._organizacao(
        banco, ator, "Grupo sem conferencias", ficha.CONJUNTO, compradores.CONJUNTO
    )
    com = integridade._analise(monkeypatch, completa.valor, regras=lambda: regras)
    sem = integridade._analise(monkeypatch, simples.valor, regras=lambda: regras)
    assert com.status_code == sem.status_code == 200
    assert len(com.json()["blocks"]["corporate_ownership"]["group"]["companies"]) == 3
    assert "group_checks" in com.text and "group_checks" not in sem.text
    assert "cgu_sanctions" not in sem.text
    for texto in (com.text, sem.text):
        assert socios.SEM_LISTA not in texto and socios.EMPRESARIO not in texto


def test_irma_coinvestidora_e_participada_da_holding_nao_entram_no_grupo(tmp_path):
    filha, irma, coinvestidora = "20000001", "20000002", "20000003"
    vinculos = [
        (s, e, "2015-01-01", "2023-05", "2023-06-30", "entrou")
        for s, e in (
            (RAIZ, filha),
            (HOLDING, irma),
            (coinvestidora, filha),
        )
    ]
    pasta = gravar_grupo(tmp_path, [*LIGACOES, *vinculos], (filha, irma, coinvestidora))
    embargo = integridade._embargos().iloc[:1].copy()
    embargo["cnpj"] = irma + "000191"
    embargo["cnpj_basico"] = irma
    integridade.gravar(pasta, integridade.EMBARGOS, embargo)
    corpo = montar(pasta).corpo
    grupo = corpo["blocos"]["socios_pj"]["grupo"]
    assert {e["raiz_do_cnpj"] for e in grupo["empresas"]} == {
        RAIZ,
        HOLDING,
        ACIMA,
        filha,
    }
    assert (
        next(e["papel"] for e in grupo["empresas"] if e["raiz_do_cnpj"] == filha)
        == "participada direta"
    )
    for bloco in (
        tabelas_por_cnpj.SANCOES,
        tabelas_por_cnpj.EMBARGOS_AMBIENTAIS,
        tabelas_por_cnpj.LISTA_SUJA,
    ):
        conferidas = {
            e["raiz_do_cnpj"] for e in corpo["blocos"][bloco]["conferencias_do_grupo"]
        }
        assert conferidas == {RAIZ, HOLDING, ACIMA, filha}


def test_holdings_tem_prioridade_sobre_nove_participadas(tmp_path):
    filhas = [
        f"1000000{i}" for i in range(9)
    ]  # ordenação por raiz favoreceria as filhas
    vinculos = [
        (RAIZ, f, "2020-01-01", "2023-05", "2023-06-30", "entrou") for f in filhas
    ]
    pasta = gravar_grupo(tmp_path, [LIGACOES[0], *vinculos], filhas)
    grupo = montar(pasta, linhas=10).corpo["blocos"]["socios_pj"]["grupo"]
    assert len(grupo["empresas"]) == 10
    assert grupo["empresas"][1]["raiz_do_cnpj"] == HOLDING
    assert grupo["completo"] is False


def test_abertura_e_entrada_da_holding_acima_entram_na_linha_do_tempo(pasta):
    marcos = montar(pasta).corpo["linha_do_tempo"]
    acima = [
        m
        for m in marcos
        if m.get("raiz_do_cnpj") == ACIMA and m.get("papel") == "holding nível 2"
    ]
    assert {m["dia"] for m in acima} >= {ABERTURAS[ACIMA], "2013-01-01"}
    assert all(
        m["fonte"] == "rfb-cnpj" and m["publico_em"] <= DIA.isoformat() for m in acima
    )


def test_retrato_da_lista_suja_e_lido_uma_vez_por_pedido(pasta, monkeypatch):
    original = Porta.ler
    leituras = []

    def ler(self, tabela, **opcoes):
        if tabela == integridade.LISTA_SUJA and not opcoes.get("filtros"):
            leituras.append(tabela)
        return original(self, tabela, **opcoes)

    monkeypatch.setattr(Porta, "ler", ler)
    montar(pasta)
    assert len(leituras) == 1
    montar(pasta)
    assert len(leituras) == 2  # a memória não atravessa pedidos


def test_camadas_do_qsa_tem_limite_no_sql_e_ligacoes_tem_teto(tmp_path, monkeypatch):
    filhas = [f"2000{i:04}" for i in range(50)]
    vinculos = [
        (RAIZ, f, "2020-01-01", "2023-05", "2023-06-30", "entrou") for f in filhas
    ]
    pasta = gravar_grupo(tmp_path, [LIGACOES[0], *vinculos], filhas)
    original = analise._Consultas.execute
    consultas = []

    def executar(self, sql, parametros=None):
        if compradores.ENTRADAS in sql and "SELECT" in sql and "DESCRIBE" not in sql:
            consultas.append(sql)
        return original(self, sql, parametros)

    monkeypatch.setattr(analise._Consultas, "execute", executar)
    grupo = montar(pasta).corpo["blocos"]["socios_pj"]["grupo"]
    assert consultas and all("LIMIT" in sql.upper() for sql in consultas)
    assert len(grupo["ligacoes"]) <= 30
    assert grupo["completo"] is False


def test_tres_niveis_ascendentes_tem_prioridade_e_quarto_fica_fora(tmp_path):
    terceira, quarta = "20000001", "20000002"
    filhas = [f"1000000{i}" for i in range(9)]
    vinculos = [
        (s, e, "2020-01-01", "2023-05", "2023-06-30", "entrou")
        for s, e in [
            (terceira, ACIMA),
            (quarta, terceira),
            *((RAIZ, f) for f in filhas),
        ]
    ]
    pasta = gravar_grupo(tmp_path, [*LIGACOES, *vinculos], [terceira, quarta, *filhas])
    grupo = montar(pasta).corpo["blocos"]["socios_pj"]["grupo"]
    assert [e["raiz_do_cnpj"] for e in grupo["empresas"][:4]] == [
        RAIZ,
        HOLDING,
        ACIMA,
        terceira,
    ]
    assert grupo["empresas"][3]["papel"] == "holding nível 3"
    assert quarta not in str(grupo)
    assert len(grupo["empresas"]) == 10


def test_ciclo_denso_corta_ligacoes_e_avisa_incompleto(tmp_path):
    holdings = [f"2000000{i}" for i in range(9)]
    vinculos = [
        (s, e, "2020-01-01", "2023-05", "2023-06-30", "entrou")
        for s in holdings
        for e in [RAIZ, *holdings]
        if s != e
    ]
    pasta = gravar_grupo(tmp_path, vinculos, holdings)
    grupo = montar(pasta).corpo["blocos"]["socios_pj"]["grupo"]
    assert len(grupo["empresas"]) == 10
    assert len(grupo["ligacoes"]) == 30
    assert grupo["completo"] is False


def test_conferencia_lenta_da_holding_preserva_leitura_direta(pasta, monkeypatch):
    liberado = threading.Event()
    original = por_tabela.LeitorPorTabela.bloco_por_raiz

    def lento(self, *args):
        liberado.wait(10)
        return original(self, *args)

    monkeypatch.setattr(por_tabela.LeitorPorTabela, "bloco_por_raiz", lento)
    integridade.gravar(
        pasta, integridade.SANCOES, integridade._sancoes().iloc[:1].copy()
    )
    try:
        corpo = montar(pasta, prazo=3).corpo
        assert corpo["blocos"]["socios_pj"]["grupo"]["completo"] is True
        sancoes = corpo["blocos"][tabelas_por_cnpj.SANCOES]
        assert sancoes["sancoes_da_cgu"]["achou"] is True
        assert sancoes["estado_conferencias_do_grupo"] == "timed_out"
        assert "sanctions" not in {b["bloco"] for b in corpo["nao_respondeu_a_tempo"]}
    finally:
        liberado.set()


@pytest.mark.parametrize("registros_por_empresa", [1, 10])
def test_dez_empresas_tres_conferencias_cabem_no_conector(
    tmp_path, registros_por_empresa, record_property
):
    from conector_remoto import enxugar, saida

    filhas = [f"2000000{i}" for i in range(7)]
    vinculos = [
        (RAIZ, f, "2020-01-01", "2023-05", "2023-06-30", "entrou") for f in filhas
    ]
    pasta = gravar_grupo(tmp_path, [*LIGACOES, *vinculos], filhas)
    raizes = [RAIZ, HOLDING, ACIMA, *filhas]
    for tabela, dados in (
        (integridade.SANCOES, integridade._sancoes().iloc[:1]),
        (integridade.EMBARGOS, integridade._embargos().iloc[:1]),
        (integridade.LISTA_SUJA, integridade._lista_suja().iloc[:1]),
    ):
        linhas = [
            dados.assign(cnpj=raiz + "000191", cnpj_basico=raiz, id_na_fonte=f"{i}-{j}")
            for i, raiz in enumerate(raizes)
            for j in range(registros_por_empresa)
        ]
        integridade.gravar(pasta, tabela, pd.concat(linhas, ignore_index=True))
    corpo = traduzir_chaves(montar(pasta).corpo)
    for bloco in integridade.BLOCOS_DE_FORA:
        assert len(corpo["blocks"][bloco]["group_checks"]) == 10
    pronta = saida.preparar_saida(enxugar.enxugar_analise(corpo))
    bruto = saida.tamanho_em_caracteres(corpo)
    final = saida.tamanho_em_caracteres(pronta)
    record_property("caracteres_api", bruto)
    record_property("caracteres_conector", final)
    assert final < saida.TETO_DE_CARACTERES
    if registros_por_empresa == 1:
        assert bruto < saida.TETO_DE_CARACTERES
