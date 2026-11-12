"""As DFP e os ITR como eram na API externa (B-32a, PR 3): `/data/v1/companies/{cnpj}/financials`.

Base de mentira, sem internet; o CNPJ é de ninguém. As linhas de direito são as de verdade
(`DIREITOS_DA_API_EXTERNA`); o teste só põe a tabela pronta (D10), como a A7 fará. Risco do plano:
olhar o futuro (uma reapresentação ou o balanço seguinte aparecendo antes do dia em que ficaram públicos).
A receita de 2024 da empresa tem três valores: a versão 1 da DFP (100), a reapresentação (110) e o
balanço de 2025 refazendo o ano anterior (105).
"""

import dataclasses
from datetime import UTC, date, datetime

import duckdb
import pandas as pd
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from base import prontidao
from base.ponto_no_tempo import COLUNAS_DA_BASE, como_era_em
from base.porta import Porta
from base.prontidao import Prontidao, Prova
from src import portao_externo as portao
from src.api_externa import acesso, rotas
from src.api_externa.conjuntos import demonstracoes
from src.banco import chaves_da_api as cb
from tests import ajudantes_da_api_externa as aj

AGORA = datetime(2026, 11, 10, 12, tzinfo=UTC)  # o beta começa em 03/11
EMPRESA = "11111111000191"
SEM_DEMONSTRACOES = "22222222000191"
CNPJ_DA_BASE = "11.111.111/0001-91"
TABELA = "demonstracoes_como_era"
ROTA = f"/data/v1/companies/{EMPRESA}/financials"
FATO = ["demonstracao", "grupo", "conta", "inicio", "fim"]


# a receita de 2024 (versão 1, reapresentação e o balanço de 2025 refazendo o ano), o terceiro trimestre de
# 2025 (ITR), o ano de 2025 e o ativo total, um saldo numa data (sem começo de período)
COLUNAS_DO_EXEMPLO = (
    "demonstracao", "conta", "descricao", "inicio", "fim", "valor", "documento", "referencia",
    "versao", "ordem", "origem", "divulgado_em", "ate",
)  # fmt: skip
# fmt: off
EXEMPLO = [
    ("DRE", "3.01", "Receita", "2024-01-01", "2024-12-31", 100.0, "DFP", "2024-12-31", 1, "ultimo", "enet", "2025-03-20", "2025-06-10"),
    ("DRE", "3.01", "Receita", "2024-01-01", "2024-12-31", 110.0, "DFP", "2024-12-31", 2, "ultimo", "enet", "2025-06-10", "2026-03-15"),
    ("DRE", "3.01", "Receita", "2024-01-01", "2024-12-31", 105.0, "DFP", "2025-12-31", 1, "penultimo", "dados_abertos", "2026-03-15", None),
    ("DRE", "3.01", "Receita", "2025-07-01", "2025-09-30", 50.0, "ITR", "2025-09-30", 1, "ultimo", "dados_abertos", "2025-11-10", None),
    ("DRE", "3.01", "Receita", "2025-01-01", "2025-12-31", 200.0, "DFP", "2025-12-31", 1, "ultimo", "dados_abertos", "2026-03-15", None),
    ("BPA", "1", "Ativo Total", None, "2025-12-31", 1000.0, "DFP", "2025-12-31", 1, "ultimo", "dados_abertos", "2026-03-15", None),
]
# fmt: on


def _base() -> pd.DataFrame:
    base = pd.DataFrame(EXEMPLO, columns=list(COLUNAS_DO_EXEMPLO)).assign(
        cnpj=CNPJ_DA_BASE, empresa="ALFA ENERGIA S.A.", grupo="con"
    )[list(COLUNAS_DA_BASE)]
    for coluna in ("inicio", "fim", "referencia", "divulgado_em", "ate"):
        base[coluna] = pd.to_datetime(base[coluna])
    return base


@pytest.fixture
def pasta(tmp_path, monkeypatch):
    base = tmp_path / "base"
    arquivo = base / "demonstracoes" / "2025.parquet"
    arquivo.parent.mkdir(parents=True)
    _base().to_parquet(arquivo, index=False)
    monkeypatch.setattr(rotas, "abrir_porta", lambda banco_: Porta(base, banco_))
    return base


def _regras_das_demonstracoes() -> portao.Regras:
    """As regras de verdade, com a tabela das demonstrações pronta (provas do D10) no dia do teste."""
    prova = Prova(AGORA.date(), "conferida no teste", "teste")
    versao = prontidao.versoes_maiores()[TABELA]
    return dataclasses.replace(
        portao.regras_vigentes(),
        prontidao={TABELA: Prontidao(versao, prova, prova, prova)},
    )


@pytest.fixture
def cenario(banco, monkeypatch, pasta):
    """Uma organização com chave e contrato de `financials`, e a tabela pronta."""
    ator = aj.admin(banco)
    org = aj.organizacao(banco, ator)
    chave = aj.chave(banco, ator, org)
    aj.contrato(banco, ator, org, conjunto="financials")
    monkeypatch.setattr(rotas, "regras_da_api", _regras_das_demonstracoes)
    return ator, org, chave


@pytest.fixture
def cliente(monkeypatch, cenario):
    return aj.cliente_da_api(monkeypatch, AGORA)


def _get(cliente, cenario, rota: str = ROTA, **parametros):
    _ator, _org, chave = cenario
    return cliente.get(rota, params=parametros, headers=aj.bearer(chave.valor))


def _receita_de_2024(corpo: dict) -> dict:
    (linha,) = [
        r
        for r in corpo["rows"]
        if r["account"]["value"] == "3.01" and r["end"]["value"] == "2024-12-31"
    ]
    return linha


def _consumo(banco, org):
    with banco.connect() as conexao:
        return cb.consumo_do_mes(conexao, org.id, AGORA.date())


# ---------------------------------------------------------------- o que sai


def test_demonstracoes_saem_com_fonte_data_e_atribuicao_em_ingles(cliente, cenario):
    resposta = _get(cliente, cenario)
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["cnpj"] == EMPRESA
    assert corpo["known_at"] == "2026-11-10"
    assert corpo["truncated"] is False
    # o mais novo primeiro: o fim do período em ordem decrescente
    fins = [r["end"]["value"] for r in corpo["rows"]]
    assert fins == sorted(fins, reverse=True)
    assert len(corpo["rows"]) == 4  # um valor por fato (a receita de 2024 só uma vez)
    receita = _receita_de_2024(corpo)
    assert receita["value"] == {
        "value": 105.0,
        "source": "cvm-hist-dfp",
        "published_at": "2026-03-15",
        "observed_at": None,
    }
    fontes = {f["source"]: f for f in corpo["sources"]}
    assert set(fontes) == {"cvm-hist-dfp", "cvm-hist-itr"}
    assert all("CVM" in f["attribution"] for f in fontes.values())


def test_campo_tem_documento_versao_origem(cliente, cenario):
    receita = _receita_de_2024(_get(cliente, cenario, known_at="2025-07-01").json())
    assert receita["document"]["value"] == "DFP"
    assert receita["reference_period"]["value"] == "2024-12-31"
    assert receita["revision"]["value"] == 2
    assert receita["origin"]["value"] == "enet"
    assert receita["start"]["value"] == "2024-01-01"
    assert receita["statement"]["value"] == "DRE"
    assert receita["group"]["value"] == "con"
    assert receita["description"]["value"] == "Receita"
    # numa foto de D, o fim que só veio depois não aparece
    assert receita["valid_until"]["value"] is None


def test_balanco_sai_sem_comeco_de_periodo(cliente, cenario):
    corpo = _get(cliente, cenario).json()
    (ativo,) = [r for r in corpo["rows"] if r["statement"]["value"] == "BPA"]
    assert ativo["start"]["value"] is None
    assert ativo["value"]["value"] == 1000.0


def test_itr_sai_com_a_fonte_do_itr(cliente, cenario):
    corpo = _get(cliente, cenario, known_at="2025-12-01").json()
    (trimestre,) = [r for r in corpo["rows"] if r["document"]["value"] == "ITR"]
    assert trimestre["value"]["source"] == "cvm-hist-itr"
    assert trimestre["value"]["published_at"] == "2025-11-10"


@pytest.mark.parametrize(
    ("dia", "valor", "versao", "referencia"),
    [
        (
            "2025-03-20",
            100.0,
            1,
            "2024-12-31",
        ),  # a versão 1 vale a partir do dia da entrega
        ("2025-06-09", 100.0, 1, "2024-12-31"),
        ("2025-06-10", 110.0, 2, "2024-12-31"),  # a reapresentação
        ("2026-03-14", 110.0, 2, "2024-12-31"),
        (
            "2026-03-15",
            105.0,
            1,
            "2025-12-31",
        ),  # o balanço de 2025 refaz o ano anterior
    ],
)
def test_reapresentacao_mostra_a_versao_de_cada_dia(
    cliente, cenario, dia, valor, versao, referencia
):
    receita = _receita_de_2024(_get(cliente, cenario, known_at=dia).json())
    assert receita["value"]["value"] == valor
    assert receita["revision"]["value"] == versao
    assert receita["reference_period"]["value"] == referencia
    assert receita["value"]["published_at"] <= dia


def test_period_end_filtra_o_periodo(cliente, cenario):
    corpo = _get(cliente, cenario, period_end="2024-12-31").json()
    assert [r["end"]["value"] for r in corpo["rows"]] == ["2024-12-31"]


def test_period_end_com_known_at_mostra_o_periodo_como_era(cliente, cenario):
    corpo = _get(
        cliente, cenario, period_end="2024-12-31", known_at="2025-06-10"
    ).json()
    (receita,) = corpo["rows"]
    assert (receita["value"]["value"], receita["revision"]["value"]) == (110.0, 2)
    # o período que ainda não tinha saído em D não aparece
    vazio = _get(cliente, cenario, period_end="2025-12-31", known_at="2026-03-14")
    assert vazio.status_code == 404


def test_limite_exato_nao_corta(cliente, cenario, monkeypatch):
    monkeypatch.setattr(acesso, "linhas_por_resposta", lambda _contexto: 4)
    corpo = _get(cliente, cenario).json()
    assert (len(corpo["rows"]), corpo["truncated"]) == (4, False)


def test_linhas_cortadas_pelo_plano(cliente, cenario, banco, monkeypatch):
    monkeypatch.setattr(acesso, "linhas_por_resposta", lambda _contexto: 2)
    corpo = _get(cliente, cenario).json()
    assert len(corpo["rows"]) == 2
    assert corpo["truncated"] is True
    _ator, org, _chave = cenario
    consumo = _consumo(banco, org)
    assert (consumo.pedidos, consumo.linhas) == (1, 2)


def test_consulta_servida_conta_um_pedido_e_as_linhas(cliente, cenario, banco):
    assert _get(cliente, cenario).status_code == 200
    _ator, org, _chave = cenario
    consumo = _consumo(banco, org)
    assert (consumo.pedidos, consumo.linhas, consumo.negados) == (1, 4, 0)


# ---------------------------------------------------------------- sem olhar o futuro


@settings(
    max_examples=40,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(dia=st.dates(min_value=date(2025, 1, 1), max_value=AGORA.date()))
def test_known_at_nunca_mostra_o_futuro(pasta, dia):
    """Para todo D: só o que era público em D, e de cada fato o valor que valia em D."""
    with Porta(pasta) as porta:
        servido = demonstracoes.LeitorDeDemonstracoes(
            porta, lambda *_: True, 1_000
        ).demonstracoes(EMPRESA, dia)
    esperado = como_era_em(_base(), dia)
    if esperado.empty:
        assert servido is None
        return
    assert servido is not None
    linhas = servido.corpo["linhas"]
    assert all(r["valor"]["publico_em"] <= dia.isoformat() for r in linhas)
    obtido = {
        tuple(r[c]["valor"] for c in FATO): (r["valor"]["valor"], r["versao"]["valor"])
        for r in linhas
    }
    assert len(obtido) == len(linhas)  # um valor por fato
    datas = esperado.assign(
        inicio=esperado.inicio.dt.strftime("%Y-%m-%d").where(esperado.inicio.notna()),
        fim=esperado.fim.dt.strftime("%Y-%m-%d"),
    )
    assert obtido == {
        tuple(None if pd.isna(x[c]) else x[c] for c in FATO): (x["valor"], x["versao"])
        for x in datas.to_dict("records")
    }


def test_cortar_o_futuro_nao_muda_o_passado(tmp_path):
    """A resposta de D é a mesma com a base inteira e com a base que só tinha o publicado até D."""
    dia = date(2025, 12, 1)
    so_ate_o_dia = _base()[lambda b: b.divulgado_em.dt.date <= dia].assign(
        ate=lambda b: b.ate.where(b.ate.dt.date <= dia)
    )
    respostas = []
    for nome, base in (("inteira", _base()), ("cortada", so_ate_o_dia)):
        arquivo = tmp_path / nome / "demonstracoes" / "2025.parquet"
        arquivo.parent.mkdir(parents=True)
        base.to_parquet(arquivo, index=False)
        with Porta(tmp_path / nome) as porta:
            leitor = demonstracoes.LeitorDeDemonstracoes(porta, lambda *_: True, 1_000)
            respostas.append(leitor.demonstracoes(EMPRESA, dia))
    assert respostas[0] is not None
    assert respostas[0] == respostas[1]


def test_documento_sem_fonte_conhecida_nao_sai(tmp_path):
    """Só DFP e ITR têm fonte e direito: outro documento na base não vira linha sem fonte."""
    base = _base().assign(documento="FRE")
    arquivo = tmp_path / "demonstracoes" / "2025.parquet"
    arquivo.parent.mkdir(parents=True)
    base.to_parquet(arquivo, index=False)
    with Porta(tmp_path) as porta:
        leitor = demonstracoes.LeitorDeDemonstracoes(porta, lambda *_: True, 1_000)
        assert leitor.demonstracoes(EMPRESA, AGORA.date()) is None


def test_known_at_antes_de_qualquer_entrega_da_404(cliente, cenario):
    resposta = _get(cliente, cenario, known_at="2025-03-19")
    assert resposta.status_code == 404
    assert resposta.json() == {"detail": "not_available"}


def test_known_at_no_futuro_da_400(cliente, cenario):
    resposta = _get(cliente, cenario, known_at="2026-11-11")
    assert resposta.status_code == 400
    assert resposta.json() == {"detail": "invalid_known_at"}


def test_cnpj_invalido_da_400(cliente, cenario):
    resposta = _get(cliente, cenario, "/data/v1/companies/11111111000192/financials")
    assert resposta.status_code == 400
    assert resposta.json() == {"detail": "invalid_cnpj"}


# ---------------------------------------------------------------- o que não sai


def test_negado_pelo_portao_da_not_available(cliente, cenario, banco):
    inexistente = _get(cliente, cenario, f"/data/v1/companies/{SEM_DEMONSTRACOES}/financials")  # fmt: skip
    assert inexistente.status_code == 404
    assert inexistente.json() == {"detail": "not_available"}
    ator, org, _chave = cenario
    with banco.begin() as conexao:
        cb.suspender_conjunto(
            conexao, conjunto="financials", motivo="fonte", ator_id=ator.id
        )
    negado = _get(cliente, cenario)
    assert negado.status_code == 404
    assert negado.json() == inexistente.json()
    assert _consumo(banco, org).negados == 2


def test_fonte_negada_some_e_as_outras_ficam(cliente, cenario, monkeypatch):
    def regras():
        return dataclasses.replace(
            _regras_das_demonstracoes(), negadas=frozenset({"cvm-hist-itr"})
        )

    monkeypatch.setattr(rotas, "regras_da_api", regras)
    corpo = _get(cliente, cenario).json()
    assert {r["document"]["value"] for r in corpo["rows"]} == {"DFP"}
    assert [f["source"] for f in corpo["sources"]] == ["cvm-hist-dfp"]
    # o ITR barrado não some em silêncio (linha 882): sem ele, as linhas leriam como "não entregou ITR"
    assert corpo["unavailable_filings"] == ["ITR"]
    assert corpo["limits"] == [demonstracoes.LIMITE_DO_DOCUMENTO_NAO_DISPONIVEL]
    assert "unavailable_filings" in corpo["limits"][0]


def test_com_tudo_liberado_a_lista_dos_documentos_sai_vazia(cliente, cenario):
    corpo = _get(cliente, cenario).json()
    assert corpo["unavailable_filings"] == []
    assert corpo["limits"] == []


def test_sem_documento_liberado_nada_e_consultado(tmp_path):
    class PortaQueNaoPodeSerLida:
        def ler(self, *_args, **_kwargs):
            raise AssertionError("o leitor não consulta a base sem documento liberado")

    leitor = demonstracoes.LeitorDeDemonstracoes(
        PortaQueNaoPodeSerLida(),  # type: ignore[arg-type]
        lambda *_: False,
        1_000,
    )
    assert leitor.demonstracoes(EMPRESA, AGORA.date()) is None


def test_duas_organizacoes_so_a_do_contrato_ve_a_lista(banco, monkeypatch, pasta):
    # a do contrato de `financials`, sem o ITR, recebe a lista; a outra (só `funds`), 404 sem ela
    ator = aj.admin(banco)
    com = aj.organizacao(banco, ator)
    chave_com = aj.chave(banco, ator, com)
    aj.contrato(banco, ator, com, conjunto="financials")
    sem = aj.organizacao(banco, ator)
    chave_sem = aj.chave(banco, ator, sem)
    aj.contrato(banco, ator, sem, conjunto="funds")

    def regras():
        return dataclasses.replace(
            _regras_das_demonstracoes(), negadas=frozenset({"cvm-hist-itr"})
        )

    monkeypatch.setattr(rotas, "regras_da_api", regras)
    cliente = aj.cliente_da_api(monkeypatch, AGORA)
    deu = cliente.get(ROTA, headers=aj.bearer(chave_com.valor))
    assert deu.status_code == 200
    assert deu.json()["unavailable_filings"] == ["ITR"]
    negou = cliente.get(ROTA, headers=aj.bearer(chave_sem.valor))
    assert negou.status_code == 404
    assert negou.json() == {"detail": "not_available"}


def test_campo_sem_direito_nao_aparece(cliente, cenario, monkeypatch):
    def regras():
        vigentes = _regras_das_demonstracoes()
        sem_descricao = tuple(
            linha
            for linha in vigentes.linhas
            if not (linha.conjunto == "financials" and linha.campo == "descricao")
        )
        return dataclasses.replace(vigentes, linhas=sem_descricao)

    monkeypatch.setattr(rotas, "regras_da_api", regras)
    corpo = _get(cliente, cenario).json()
    assert corpo["rows"]
    assert all("description" not in r for r in corpo["rows"])
    assert all("value" in r for r in corpo["rows"])


def test_hoje_sem_a_prontidao_nada_sai(cliente, cenario, monkeypatch):
    monkeypatch.setattr(rotas, "regras_da_api", lambda: None)  # as regras de verdade
    resposta = _get(cliente, cenario)
    assert resposta.status_code == 404
    assert resposta.json() == {"detail": "not_available"}


def test_organizacao_sem_contrato_de_financials_recebe_404(banco, monkeypatch, pasta):
    ator = aj.admin(banco)
    org = aj.organizacao(banco, ator)
    chave = aj.chave(banco, ator, org)
    aj.contrato(banco, ator, org, conjunto="funds")
    monkeypatch.setattr(rotas, "regras_da_api", _regras_das_demonstracoes)
    cliente = aj.cliente_da_api(monkeypatch, AGORA)
    resposta = cliente.get(ROTA, headers=aj.bearer(chave.valor))
    assert resposta.status_code == 404
    assert resposta.json() == {"detail": "not_available"}


def test_chave_revogada_da_401(cliente, cenario, banco):
    ator, org, chave = cenario
    with banco.begin() as conexao:
        cb.revogar_chave(
            conexao, organizacao_id=org.id, chave_id=chave.chave_id, ator_id=ator.id
        )
    assert _get(cliente, cenario).status_code == 401


def test_falha_na_leitura_da_base_da_503_e_nao_conta(
    cliente, cenario, banco, monkeypatch
):
    def quebra(*_args, **_kwargs):
        raise duckdb.IOException("arquivo sumiu no meio da leitura")

    monkeypatch.setattr(Porta, "ler", quebra)
    resposta = _get(cliente, cenario)
    assert resposta.status_code == 503
    assert resposta.json() == {"detail": "service_unavailable"}
    _ator, org, _chave = cenario
    assert _consumo(banco, org).pedidos == 0


def test_sem_base_neste_servidor_da_503(cliente, cenario, monkeypatch):
    def sem_base(_banco):
        raise ValueError("TICKERLAB_ACERVO não definida")

    monkeypatch.setattr(rotas, "abrir_porta", sem_base)
    assert _get(cliente, cenario).status_code == 503


def test_404_de_hoje_e_so_a_falta_de_prontidao_da_tabela():
    """Linha 792: com as regras de verdade o portão nega `/financials` por `sem_prontidao`, não por
    contrato, marca ou licença; quando a 784 der a prontidão de `demonstracoes_como_era`, a rota abre."""
    hoje = AGORA.date()
    for fonte in ("cvm-hist-dfp", "cvm-hist-itr"):
        pedido = portao.Pedido(
            fonte, demonstracoes.CONJUNTO, "valor", portao.Canal.API_EXTERNA.value,
            portao.Finalidade.ANALISE.value,
        )  # fmt: skip
        assert portao.decidir(pedido, hoje).motivo is portao.Motivo.SEM_PRONTIDAO
        assert portao.decidir(pedido, hoje, _regras_das_demonstracoes()).libera
