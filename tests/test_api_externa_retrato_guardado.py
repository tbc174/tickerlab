"""O mês do retrato das listas sem pessoa, guardado na memória da porta dona (linha 1015, item f, PR 6).

Medido no PC (três análises completas de empresas fechadas ao mesmo tempo, meia CPU): o cadastro levava 16 s, e
três quartos disso eram quatro varreduras inteiras das listas da Receita para achar o mês mais novo. Duas não
dependem do dia (a trava do "é empresa", `_retrato_das_duas_listas`); uma depende (o estabelecimento da ficha).

O que estes testes seguram (as condições da Diretoria):
1. o que fica guardado tem por chave só os arquivos da base: arquivo novo ou trocado abre a porta de novo e a
   resposta muda sem reiniciar;
2. com o guardado quente, quem não é empresa continua `not_available` sem abrir bloco nenhum, nas duas ordens;
5. nada de olhar o futuro: o mês das duas listas não depende do dia (mostrado aqui); o do estabelecimento
   depende, e o dia entra na chave;
e que o guardado é calculado uma vez só quando vários pedidos chegam juntos, sem prender a chave de outro.
Base de mentira, sem internet.
"""

import inspect
import os
import threading
from datetime import date

import pandas as pd
import pytest

from base.porta import Porta
from src.api_externa import porta_compartilhada as compartilhada
from src.api_externa import rotas
from src.api_externa.conjuntos import empresas, ficha
from tests import test_api_externa_analise as rota_da_analise
from tests import test_api_externa_e_empresa as listas_de_mentira
from tests import test_api_externa_empresas as empresas_de_mentira
from tests import test_api_externa_socios_pj as socios_de_mentira

EMPRESA = listas_de_mentira.EMPRESA
MEI = listas_de_mentira.MEI
NOVA = "12121212000191"  # só entra no retrato de 2026-11
VELHO, NOVO, NOVISSIMO = "2026-09", "2026-10", "2026-11"
PUBLICO = {
    VELHO: date(2026, 9, 30),
    NOVO: date(2026, 10, 31),
    NOVISSIMO: date(2026, 11, 30),
}


def _no_mes(tabela: pd.DataFrame) -> pd.DataFrame:
    """Cada retrato público no último dia do mês dele (as listas de mentira põem todos em 31/10)."""
    return tabela.assign(disponivel_em=tabela["mes_do_retrato"].map(PUBLICO))


def _gravar_listas(base, empresas_=None, estabelecimentos=None) -> None:
    listas_de_mentira._gravar(
        base,
        empresas.LISTA_DE_EMPRESAS,
        _no_mes(listas_de_mentira._empresas(empresas_ or listas_de_mentira.EMPRESAS)),
    )
    listas_de_mentira._gravar(
        base,
        empresas.LISTA_DE_ESTABELECIMENTOS,
        _no_mes(
            listas_de_mentira._estabelecimentos(
                estabelecimentos or listas_de_mentira.ESTABELECIMENTOS
            )
        ),
    )


class _BaseDeMentira:
    def __init__(self, pasta) -> None:
        self.pasta = pasta
        self.aberturas = 0

    def abrir(self) -> Porta:
        self.aberturas += 1
        return Porta(self.pasta)


@pytest.fixture
def base(tmp_path, monkeypatch):
    pasta = tmp_path / "base"
    _gravar_listas(pasta)
    falsa = _BaseDeMentira(pasta)
    compartilhada.zerar()
    monkeypatch.setattr(compartilhada, "abrir_a_base", falsa.abrir)
    monkeypatch.setattr(compartilhada, "_pasta_da_base", lambda: pasta)
    yield falsa
    compartilhada.zerar()


@pytest.fixture
def contadas(monkeypatch):
    """Quantas vezes o mês das duas listas foi lido da base (a varredura inteira)."""
    leituras: list[int] = []
    ler = empresas._ler_o_retrato_das_duas_listas

    def contar(porta):
        leituras.append(1)
        return ler(porta)

    monkeypatch.setattr(empresas, "_ler_o_retrato_das_duas_listas", contar)
    return leituras


def _e_empresa(cnpj: str) -> bool:
    with compartilhada.porta_do_pedido() as porta:
        return empresas.e_empresa(porta, cnpj)


# ---------------------------------------------------------------- 1. a chave é só a dos arquivos


def test_o_mes_das_duas_listas_e_lido_uma_vez_por_base(base, contadas):
    assert _e_empresa(EMPRESA)
    assert not _e_empresa(MEI)
    assert _e_empresa(listas_de_mentira.FILIAL)
    assert len(contadas) == 1
    with compartilhada.porta_do_pedido() as porta:
        guardadas = [
            chave
            for chave in porta.memoria_da_base
            if "retrato_das_duas_listas" in str(chave)
        ]  # type: ignore[attr-defined]
    # nada do pedido na chave: nem o CNPJ, nem o dia, nem quem pediu
    assert guardadas == [empresas.CHAVE_DO_RETRATO_DAS_DUAS_LISTAS]
    assert empresas.CHAVE_DO_RETRATO_DAS_DUAS_LISTAS == ("retrato_das_duas_listas",)


def test_retrato_novo_entra_e_a_resposta_muda_sem_reiniciar(base, contadas):
    assert _e_empresa(EMPRESA)
    assert not _e_empresa(NOVA)
    # chega o retrato de 2026-11 nas duas listas: a NOVA entra e a EMPRESA não está nele
    listas_de_mentira._gravar(
        base.pasta,
        empresas.LISTA_DE_EMPRESAS,
        _no_mes(listas_de_mentira._empresas([(NOVA[:8], "2062", NOVISSIMO)])),
    )
    listas_de_mentira._gravar(
        base.pasta,
        empresas.LISTA_DE_ESTABELECIMENTOS,
        _no_mes(listas_de_mentira._estabelecimentos([(NOVA, NOVISSIMO)])),
    )
    assert _e_empresa(NOVA)
    assert not _e_empresa(EMPRESA)
    assert base.aberturas == 2
    assert len(contadas) == 2  # a porta nova leu de novo; nada da velha serviu


def test_arquivo_trocado_com_outro_mes_muda_a_resposta_sem_reiniciar(base, contadas):
    assert _e_empresa(EMPRESA)
    # a lista de estabelecimentos é regravada só com o mês velho: os meses das duas listas não batem mais
    for arquivo in (base.pasta / empresas.LISTA_DE_ESTABELECIMENTOS).glob("*.parquet"):
        tabela = pd.read_parquet(arquivo)
        tabela.assign(mes_do_retrato=VELHO).to_parquet(arquivo, index=False)
        os.utime(
            arquivo, ns=(1, 1)
        )  # a data muda mesmo que a gravação caia no mesmo instante
    assert not _e_empresa(EMPRESA)
    assert len(contadas) == 2


# ---------------------------------------------------------------- 2. quem não é empresa, com o guardado quente


@pytest.mark.parametrize("ordem", [(EMPRESA, MEI), (MEI, EMPRESA)])
def test_com_o_guardado_quente_quem_nao_e_empresa_continua_nao(base, contadas, ordem):
    # a primeira consulta esquenta a memória; a segunda já a usa
    respostas = {cnpj: _e_empresa(cnpj) for cnpj in (*ordem, *ordem)}
    assert respostas == {EMPRESA: True, MEI: False}
    assert len(contadas) == 1


@pytest.mark.parametrize("ordem", [(EMPRESA, MEI), (MEI, EMPRESA)])
def test_o_lote_com_o_guardado_quente_da_o_mesmo_que_um_a_um(base, contadas, ordem):
    assert _e_empresa(ordem[0]) == (ordem[0] == EMPRESA)  # esquenta a memória
    with compartilhada.porta_do_pedido() as porta:
        lote = empresas.e_empresas(porta, [*ordem, listas_de_mentira.FILIAL, NOVA])
    assert lote == {
        EMPRESA: True,
        MEI: False,
        listas_de_mentira.FILIAL: True,
        NOVA: False,
    }
    assert len(contadas) == 1


@pytest.fixture
def analise_com_memoria(tmp_path, monkeypatch):
    """A rota da análise com a porta de produção: um cursor da porta dona e a memória dela, a mesma em todos
    os pedidos (a `Porta` dos outros testes da rota não guarda nada)."""
    pasta = socios_de_mentira.base_com_socios(tmp_path)
    dona = Porta(pasta)
    memoria: dict = {}
    monkeypatch.setattr(
        rotas,
        "abrir_porta",
        lambda banco_: compartilhada.PortaEmprestada(dona, banco_, memoria),
    )
    monkeypatch.setattr(rotas, "regras_da_api", rota_da_analise._regras)
    yield memoria
    dona.fechar()


@pytest.mark.parametrize(
    "ordem",
    [
        (empresas_de_mentira.EMPRESA, empresas_de_mentira.FORA_DA_REDE),
        (empresas_de_mentira.FORA_DA_REDE, empresas_de_mentira.EMPRESA),
    ],
)
def test_na_rota_com_o_guardado_quente_quem_nao_e_empresa_nao_abre_nada(
    analise_com_memoria, monkeypatch, banco, ordem
):
    """A EMPRESA a rede decide; a FORA_DA_REDE, as listas (com o mês guardado). Na mesma porta, uma depois da
    outra, nas duas ordens: a que não é empresa dá o 404 de quem não existe e só o cadastro conta."""
    cliente = rota_da_analise.aj.cliente_da_api(monkeypatch, rota_da_analise.AGORA)
    ator = rota_da_analise.aj.admin(banco)
    org, chave = rota_da_analise._organizacao(
        banco, ator, "Alfa", ficha.CONJUNTO, rota_da_analise.compradores.CONJUNTO
    )
    fora = empresas_de_mentira.FORA_DA_REDE
    respostas = {}
    for cnpj in (*ordem, *ordem):
        respostas.setdefault(cnpj, []).append(
            rota_da_analise._get(cliente, chave, cnpj)
        )
    assert empresas.CHAVE_DO_RETRATO_DAS_DUAS_LISTAS in analise_com_memoria
    inexistente = rota_da_analise._get(cliente, chave, rota_da_analise.INEXISTENTE)
    for resposta in respostas[fora]:
        assert resposta.status_code == inexistente.status_code == 404
        assert resposta.json() == inexistente.json() == {"detail": "not_available"}
    for resposta in respostas[empresas_de_mentira.EMPRESA]:
        assert resposta.status_code == 200
    # os dois pedidos da EMPRESA leram o cadastro e os compradores; os da FORA_DA_REDE e o inexistente, só o
    # cadastro (negado), e nenhum outro bloco correu para eles
    assert rota_da_analise._por_conjunto(banco, org) == {
        ficha.CONJUNTO: (2, 3),
        rota_da_analise.compradores.CONJUNTO: (2, 0),
    }


# ---------------------------------------------------------------- 5. nada de olhar o futuro


def test_o_mes_das_duas_listas_nao_depende_do_dia():
    """A trava do "é empresa" usa o retrato mais novo, qualquer que seja o `known_at` do pedido (como antes do
    guardado): nem ela nem o mês guardado recebem um dia, e por isso o dia não entra na chave."""
    assert list(inspect.signature(empresas.e_empresa).parameters) == ["porta", "cnpj"]
    assert list(inspect.signature(empresas._retrato_das_duas_listas).parameters) == [
        "porta"
    ]
    assert list(
        inspect.signature(empresas._ler_o_retrato_das_duas_listas).parameters
    ) == ["porta"]


DIAS = {VELHO: date(2026, 10, 15), NOVO: date(2026, 11, 15), None: date(2026, 9, 1)}


@pytest.mark.parametrize("ordem", [list(DIAS), list(reversed(DIAS))])
def test_o_mes_do_estabelecimento_guardado_e_o_do_dia_pedido(tmp_path, ordem):
    """O retrato de 2026-10 só é público em 31/10: quem pergunta por 15/10 recebe o de 2026-09, mesmo que outro
    pedido já tenha guardado o de 2026-10; e antes de 30/09, nenhum. Nas duas ordens, igual à porta sem memória."""
    pasta = tmp_path / "base"
    _gravar_listas(pasta)
    with Porta(pasta) as dona, Porta(pasta) as sem_memoria:
        memoria: dict = {}
        for esperado in ordem:
            dia = DIAS[esperado]
            with compartilhada.PortaEmprestada(dona, None, memoria) as porta:
                guardado = ficha.LeitorDeFicha(
                    porta, lambda *_: True
                )._retrato_do_estabelecimento(dia)
            sem = ficha.LeitorDeFicha(
                sem_memoria, lambda *_: True
            )._retrato_do_estabelecimento(dia)
            assert guardado == sem == esperado
        assert {
            chave for chave in memoria if "retrato_do_estabelecimento" in str(chave)
        } == {ficha.chave_do_retrato_do_estabelecimento(dia) for dia in DIAS.values()}
    assert ficha.chave_do_retrato_do_estabelecimento(date(2026, 10, 15)) == (
        "retrato_do_estabelecimento",
        "2026-10-15",
    )


# ---------------------------------------------------------------- calculado uma vez com pedidos juntos


def _porta_com_memoria(memoria: dict):
    class _Porta:
        memoria_da_base = memoria

    return _Porta()


def test_pedidos_juntos_calculam_a_mesma_chave_uma_vez():
    memoria: dict = {}
    calculando, pode_terminar = threading.Event(), threading.Event()
    calculos: list[int] = []

    def demorado() -> str:
        calculos.append(1)
        calculando.set()
        pode_terminar.wait(5)
        return "2026-10"

    respostas: list[str] = []
    primeiro = threading.Thread(
        target=lambda: respostas.append(
            compartilhada.lembrar(_porta_com_memoria(memoria), "mes", demorado)
        )
    )
    primeiro.start()
    assert calculando.wait(5)
    segundo = threading.Thread(
        target=lambda: respostas.append(
            compartilhada.lembrar(_porta_com_memoria(memoria), "mes", demorado)
        )
    )
    segundo.start()
    segundo.join(0.2)
    assert segundo.is_alive()  # espera o primeiro em vez de varrer a base de novo
    pode_terminar.set()
    primeiro.join(5)
    segundo.join(5)
    assert respostas == ["2026-10", "2026-10"]
    assert len(calculos) == 1


def test_a_espera_de_uma_chave_nao_prende_outra():
    memoria: dict = {}
    calculando, pode_terminar = threading.Event(), threading.Event()

    def demorado() -> str:
        calculando.set()
        pode_terminar.wait(5)
        return "lento"

    linha = threading.Thread(
        target=lambda: compartilhada.lembrar(
            _porta_com_memoria(memoria), "uma", demorado
        )
    )
    linha.start()
    assert calculando.wait(5)
    try:
        assert (
            compartilhada.lembrar(
                _porta_com_memoria(memoria), "outra", lambda: "rápido"
            )
            == "rápido"
        )
    finally:
        pode_terminar.set()
        linha.join(5)


def test_se_o_calculo_falha_quem_esperava_calcula_e_nada_fica_guardado():
    """O prazo de um pedido interrompe a consulta dele (erro): quem esperava calcula sozinho, e o erro não fica
    guardado para os próximos."""
    memoria: dict = {}
    calculando, pode_falhar = threading.Event(), threading.Event()

    def falha() -> str:
        calculando.set()
        pode_falhar.wait(5)
        raise RuntimeError("interrompida")

    erros: list[BaseException] = []

    def primeiro() -> None:
        try:
            compartilhada.lembrar(_porta_com_memoria(memoria), "mes", falha)
        except RuntimeError as erro:
            erros.append(erro)

    linha = threading.Thread(target=primeiro)
    linha.start()
    assert calculando.wait(5)
    respostas: list[str] = []
    segundo = threading.Thread(
        target=lambda: respostas.append(
            compartilhada.lembrar(_porta_com_memoria(memoria), "mes", lambda: "2026-10")
        )
    )
    segundo.start()
    segundo.join(0.2)
    assert segundo.is_alive()  # parado na trava, esperando o primeiro
    pode_falhar.set()
    linha.join(5)
    segundo.join(5)
    assert len(erros) == 1
    assert respostas == ["2026-10"]
    # o erro não ficou guardado; o valor de quem esperou, sim
    nunca = lambda: pytest.fail("calculou de novo")
    assert compartilhada.lembrar(_porta_com_memoria(memoria), "mes", nunca) == "2026-10"


def test_as_travas_tem_limite_como_a_memoria():
    """O dia variado de quem pede (`known_at`) não cresce a lista de travas sem fim."""
    memoria: dict = {}
    for i in range(compartilhada.MEMORIA_MAXIMA * 2 + 3):
        assert (
            compartilhada.lembrar(
                _porta_com_memoria(memoria), ("dia", i), lambda i=i: i
            )
            == i
        )
    assert len(compartilhada._TRAVAS) <= compartilhada.MEMORIA_MAXIMA
    assert len(memoria) <= compartilhada.MEMORIA_MAXIMA


# ---------------------------------------------------------------- a troca da base com um pedido em andamento
# Achado P1 do Revisor no #1325 (linha 1098): as views leem os Parquets pelo caminho. Se a carga troca um arquivo no
# mesmo caminho enquanto um pedido ainda está com a porta, o mês guardado antes da troca não pode servir aos arquivos
# novos: a porta aberta tem de responder o que uma porta aberta depois da troca responde (o que o `max` na hora dava).
TROCADA = "13131313000191"  # entra no retrato de 2026-11 no mesmo arquivo da EMPRESA (prefixo 1)


def _acrescentar_no_mesmo_arquivo(pasta, tabela: str, novas: pd.DataFrame) -> None:
    """Regrava o arquivo do prefixo das linhas novas no mesmo caminho, com as linhas velhas e as novas."""
    prefixo = novas["cnpj_basico"].str[:2].iloc[0]
    arquivo = pasta / tabela / f"{prefixo}.parquet"
    velhas = pd.read_parquet(arquivo)
    pd.concat([velhas, novas[velhas.columns]], ignore_index=True).to_parquet(
        arquivo, index=False
    )
    os.utime(
        arquivo, ns=(1, 1)
    )  # a data muda mesmo que a gravação caia no mesmo instante


def _retrato_novissimo_no_mesmo_caminho(pasta) -> None:
    empresas_novas = _no_mes(
        listas_de_mentira._empresas([(EMPRESA[:8], "2062", NOVISSIMO)])
    )
    estabelecimentos_novos = _no_mes(
        listas_de_mentira._estabelecimentos([(EMPRESA, NOVISSIMO)])
    )
    _acrescentar_no_mesmo_arquivo(pasta, empresas.LISTA_DE_EMPRESAS, empresas_novas)
    _acrescentar_no_mesmo_arquivo(
        pasta, empresas.LISTA_DE_ESTABELECIMENTOS, estabelecimentos_novos
    )


def _depois_da_troca(pasta, ler):
    """O que uma porta aberta depois da troca responde (sem memória: o cálculo na hora)."""
    with Porta(pasta) as nova:
        return ler(nova)


def test_porta_aberta_durante_a_troca_ve_o_mes_novo_do_estabelecimento(base):
    dia = date(2026, 12, 15)
    porta = compartilhada.porta_do_pedido()
    try:
        leitor = ficha.LeitorDeFicha(porta, lambda *_: True)
        assert (
            leitor._retrato_do_estabelecimento(dia) == NOVO
        )  # esquenta a memória com o mês de antes
        _retrato_novissimo_no_mesmo_caminho(base.pasta)
        depois = _depois_da_troca(
            base.pasta,
            lambda p: ficha.LeitorDeFicha(
                p, lambda *_: True
            )._retrato_do_estabelecimento(dia),
        )
        assert depois == NOVISSIMO
        assert leitor._retrato_do_estabelecimento(dia) == depois
    finally:
        porta.fechar()


def test_porta_aberta_durante_a_troca_ve_o_mes_novo_das_duas_listas(base):
    porta = compartilhada.porta_do_pedido()
    try:
        assert empresas._retrato_das_duas_listas(porta) == NOVO
        _retrato_novissimo_no_mesmo_caminho(base.pasta)
        depois = _depois_da_troca(base.pasta, empresas._retrato_das_duas_listas)
        assert depois == NOVISSIMO
        assert empresas._retrato_das_duas_listas(porta) == depois
        # e a trava do "é empresa" segue o mês novo: a EMPRESA está nele; o MEI, que só está em 2026-10, não
        assert empresas.e_empresa(porta, EMPRESA)
        assert not empresas.e_empresa(porta, listas_de_mentira.FILIAL)
    finally:
        porta.fechar()


def test_porta_aberta_durante_a_troca_ve_o_mes_publico_novo_das_empresas(base):
    dia = date(2026, 12, 15)
    porta = compartilhada.porta_do_pedido()
    try:
        assert empresas.mes_do_retrato_publico(porta, dia) == NOVO
        _retrato_novissimo_no_mesmo_caminho(base.pasta)
        depois = _depois_da_troca(
            base.pasta, lambda p: empresas.mes_do_retrato_publico(p, dia)
        )
        assert depois == NOVISSIMO
        assert empresas.mes_do_retrato_publico(porta, dia) == depois
    finally:
        porta.fechar()


def test_sem_troca_a_memoria_continua_valendo(base, contadas):
    """A conferência dos arquivos não desfaz o guardado: sem troca, o mês das duas listas é lido uma vez."""
    porta = compartilhada.porta_do_pedido()
    try:
        for _ in range(3):
            assert empresas._retrato_das_duas_listas(porta) == NOVO
        assert len(contadas) == 1
    finally:
        porta.fechar()
