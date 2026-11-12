"""Quem já se mexeu num setor, na API externa (linha 810, PR 4): `GET /data/v1/buyers`, só pessoa jurídica.

Base de mentira, sem internet; as raízes são de ninguém. As linhas de direito são as de verdade
(`DIREITOS_DA_API_EXTERNA`) e o teste só põe as tabelas prontas (D10). Riscos: vazar pessoa (o comprador fora
da lista sem pessoa não sai, e nenhuma chave de sócio sai), olhar o futuro (entrada, retrato e FRE só contam
depois de públicos) e contar como compra o que não é (fundador, mesmo grupo, fora da janela, fora do setor).
"""

import dataclasses
import shutil
from datetime import UTC, datetime

import duckdb
import pandas as pd
import pytest

from base import prontidao
from base import recorte_dos_compradores as reduzidas
from base.cnpj import digitos_verificadores
from base.porta import Porta
from base.prontidao import Prontidao, Prova
from src import portao_externo as portao
from src.api_externa import rotas
from src.api_externa.conjuntos import compradores
from tests import ajudantes_da_api_externa as aj

AGORA = datetime(2026, 11, 10, 12, tzinfo=UTC)
ROTA = "/data/v1/buyers"
SETOR = "6201501"
CARIMBOS = {
    "origem_sha256": "0" * 64,
    "montado_em": pd.Timestamp("2026-11-05", tz="UTC"),
    "versao_do_codigo": "teste",
}
# as empresas do setor (e uma fora dele) e quem entrou nelas
ALVO_SP, ALVO_RJ, BAIXADA, FORA, NOVA = (
    "11000001",
    "11000002",
    "11000003",
    "11000004",
    "11000005",
)
COMPRADORA, FUNDADORA, IRMA, HOLDING = "12000001", "12000002", "12000003", "12000004"
VELHA, SEM_LISTA, FUTURA, FUNDO, ABERTA = (
    "12000005",
    "12000006",
    "12000007",
    "13000001",
    "14000001",
)
NOMES = {
    ALVO_SP: "ALVO SP LTDA",
    ALVO_RJ: "ALVO RJ LTDA",
    BAIXADA: "BAIXADA LTDA",
    FORA: "FORA DO SETOR LTDA",
    NOVA: "NOVA NO SETOR LTDA",
    COMPRADORA: "COMPRADORA PARTICIPACOES S.A.",
    FUNDADORA: "FUNDADORA LTDA",
    IRMA: "IRMA LTDA",
    HOLDING: "HOLDING LTDA",
    VELHA: "VELHA LTDA",
    FUTURA: "FUTURA LTDA",
    FUNDO: "FUNDO DE PARTICIPACOES EXEMPLO",
    ABERTA: "ABERTA S.A.",
}  # fmt: skip  (SEM_LISTA fica fora: não está na lista sem pessoa)
# a Receita publica o retrato de um mês no mês seguinte; o de outubro só vale a partir de 31/10
# fmt: off
ESTABELECIMENTOS = [
    # raiz, situação, abertura, cnae, uf, mês, disponível em
    (ALVO_SP, "02", "2010-01-01", SETOR, "SP", "2026-09", "2026-09-30"),
    (ALVO_RJ, "02", "2024-01-01", SETOR, "RJ", "2026-09", "2026-09-30"),
    (BAIXADA, "08", "2012-01-01", SETOR, "SP", "2026-09", "2026-09-30"),
    (FORA, "02", "2012-01-01", "4711302", "SP", "2026-09", "2026-09-30"),
    (ALVO_SP, "02", "2010-01-01", SETOR, "SP", "2026-10", "2026-10-31"),
    (ALVO_RJ, "02", "2024-01-01", SETOR, "RJ", "2026-10", "2026-10-31"),
    (BAIXADA, "08", "2012-01-01", SETOR, "SP", "2026-10", "2026-10-31"),
    (FORA, "02", "2012-01-01", "4711302", "SP", "2026-10", "2026-10-31"),
    (NOVA, "02", "2026-10-01", SETOR, "SP", "2026-10", "2026-10-31"),
]
ENTRADAS = [
    # sócia, empresa, data de entrada, mês do retrato, disponível em, movimento
    (HOLDING, ALVO_SP, "2010-01-01", "2023-05", "2023-06-30", "entrou"),  # sócia antiga (o retrato de partida)
    (HOLDING, IRMA, "2020-01-01", "2023-05", "2023-06-30", "entrou"),
    (VELHA, ALVO_SP, "2018-01-01", "2023-05", "2023-06-30", "entrou"),  # fora da janela de 3 anos
    (FUNDADORA, ALVO_RJ, "2024-01-01", "2024-02", "2024-03-31", "entrou"),  # entrou na abertura
    (FUNDO, ALVO_RJ, "2024-06-01", "2024-07", "2024-08-31", "entrou"),  # o FIP
    (SEM_LISTA, ALVO_SP, "2025-01-01", "2025-02", "2025-03-31", "entrou"),  # não está na lista sem pessoa
    (COMPRADORA, ALVO_SP, "2025-03-10", "2025-04", "2025-05-31", "entrou"),  # a compra no setor
    (COMPRADORA, FORA, "2025-03-10", "2025-04", "2025-05-31", "entrou"),  # fora do setor
    (COMPRADORA, BAIXADA, "2025-03-10", "2025-04", "2025-05-31", "entrou"),  # empresa baixada
    (IRMA, ALVO_SP, "2025-06-01", "2025-07", "2025-08-31", "entrou"),  # tem a HOLDING em comum: mesmo grupo
    (FUTURA, ALVO_SP, "2026-10-20", "2026-11", "2026-11-30", "entrou"),  # ainda não pública em 10/11
]
# fmt: on


def _cnpj(raiz: str) -> str:
    """O CNPJ da matriz com o dígito verificador certo (a cópia reduzida só leva CNPJ que confere)."""
    return f"{raiz}0001{digitos_verificadores(f'{raiz}0001')}"


def _estabelecimentos() -> pd.DataFrame:
    tabela = pd.DataFrame(
        ESTABELECIMENTOS,
        columns=["cnpj_basico", "situacao_cadastral", "data_inicio_atividade", "cnae_principal", "uf",
                 "mes_do_retrato", "disponivel_em"],
    )  # fmt: skip
    tabela["cnpj"] = tabela["cnpj_basico"] + "000100"
    tabela["matriz"] = True
    tabela["municipio"] = "7107"
    tabela["data_inicio_atividade"] = pd.to_datetime(tabela["data_inicio_atividade"])
    tabela["disponivel_em"] = pd.to_datetime(tabela["disponivel_em"]).dt.date
    return tabela.assign(**CARIMBOS)


def _empresas() -> pd.DataFrame:
    linhas = [
        (raiz, nome, mes, disponivel)
        for mes, disponivel in (("2026-09", "2026-09-30"), ("2026-10", "2026-10-31"))
        for raiz, nome in NOMES.items()
    ]
    tabela = pd.DataFrame(
        linhas,
        columns=["cnpj_basico", "razao_social", "mes_do_retrato", "disponivel_em"],
    )
    tabela["disponivel_em"] = pd.to_datetime(tabela["disponivel_em"]).dt.date
    return tabela.assign(
        natureza_juridica="2062",
        porte="demais",
        capital_social=1_000_000.0,
        n_estabelecimentos=1,
        **CARIMBOS,
    )


def _entradas() -> pd.DataFrame:
    tabela = pd.DataFrame(
        ENTRADAS,
        columns=[
            "raiz_socio_pj",
            "cnpj_basico",
            "data_entrada",
            "mes_do_retrato",
            "disponivel_em",
            "movimento",
        ],
    )
    tabela["data_entrada"] = pd.to_datetime(tabela["data_entrada"]).dt.date
    tabela["disponivel_em"] = pd.to_datetime(tabela["disponivel_em"]).dt.date
    return tabela.assign(qualificacao="22", **CARIMBOS)


def _fundos() -> pd.DataFrame:
    return pd.DataFrame({
        "ID_Registro_Fundo": ["1", "2"],
        "CNPJ_Fundo": [f"{FUNDO[:2]}.{FUNDO[2:5]}.{FUNDO[5:]}/0001-{_cnpj(FUNDO)[-2:]}", _cnpj(FUNDADORA)],
        "Tipo_Fundo": ["FIP", "FIP"],
        "Data_Registro": pd.to_datetime(["2020-01-01", "2015-01-01"]).date,
        "Data_Cancelamento": [None, pd.Timestamp("2020-01-01").date()],  # o FIP cancelado não conta
        "CPF_CNPJ_Gestor": ["99999999000100", "99999999000100"],
    })  # fmt: skip


def _controladas() -> pd.DataFrame:
    # a versão 2 do FRE de 2025 só chega em 20/10/2026; a do RJ é de um FRE antigo, que o de 2025 substitui
    return pd.DataFrame({
        "cnpj_companhia": [_cnpj(ABERTA)] * 3,
        "referencia": pd.to_datetime(["2025-12-31", "2025-12-31", "2020-12-31"]).date,
        "versao": [1, 2, 1],
        "conhecido_em": pd.to_datetime(["2026-05-30", "2026-10-20", "2021-05-30"]).date,
        "origem_coletada_em": pd.to_datetime(["2026-06-01", "2026-10-21", "2021-06-01"]).date,
        "cnpj": [_cnpj(ALVO_SP), _cnpj(ALVO_SP), _cnpj(ALVO_RJ)],
        "tipo": ["controlada", "controlada", "coligada"],
        "participacao": [60.0, 70.0, 20.0],
    }).assign(**CARIMBOS)  # fmt: skip


def _gravar(arquivo, tabela: pd.DataFrame) -> None:
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    tabela.to_parquet(arquivo, index=False)


@pytest.fixture
def pasta(tmp_path, monkeypatch):
    base = tmp_path / "base"
    _gravar(base / compradores.ESTABELECIMENTOS / "11.parquet", _estabelecimentos())
    _gravar(base / compradores.EMPRESAS / "11.parquet", _empresas())
    _gravar(base / compradores.ENTRADAS / "parte.parquet", _entradas())
    _gravar(base / "fidc" / "cadastro" / "registro_fundo.parquet", _fundos())
    _gravar(base / compradores.CONTROLADAS / "2025.parquet", _controladas())
    monkeypatch.setattr(rotas, "abrir_porta", lambda banco_: Porta(base, banco_))
    return base


TABELAS = (
    compradores.ESTABELECIMENTOS,
    compradores.EMPRESAS,
    compradores.ENTRADAS,
    compradores.FUNDOS,
    compradores.CONTROLADAS,
)


def _regras(*prontas: str) -> portao.Regras:
    """As regras de verdade, com as tabelas dadas prontas (provas do D10) no dia do teste."""
    prova = Prova(AGORA.date(), "conferida no teste", "teste")
    versoes = prontidao.versoes_maiores()
    return dataclasses.replace(
        portao.regras_vigentes(),
        prontidao={t: Prontidao(versoes[t], prova, prova, prova) for t in prontas},
    )


@pytest.fixture
def cenario(banco, monkeypatch, pasta):
    ator = aj.admin(banco)
    org = aj.organizacao(banco, ator)
    chave = aj.chave(banco, ator, org)
    aj.contrato(banco, ator, org, conjunto=compradores.CONJUNTO)
    monkeypatch.setattr(rotas, "regras_da_api", lambda: _regras(*TABELAS))
    return ator, org, chave


@pytest.fixture
def cliente(monkeypatch, cenario):
    return aj.cliente_da_api(monkeypatch, AGORA)


def _get(cliente, cenario, **parametros):
    _ator, _org, chave = cenario
    return cliente.get(
        ROTA, params={"cnae": SETOR, **parametros}, headers=aj.bearer(chave.valor)
    )


def _raizes(resposta) -> list[str]:
    return [c["cnpj_root"] for c in resposta.json()["buyers"]]


def _comprador(resposta, raiz: str) -> dict:
    (achado,) = [c for c in resposta.json()["buyers"] if c["cnpj_root"] == raiz]
    return achado


# ---------------------------------------------------------------- o que sai


def test_os_compradores_saem_pelos_sinais_em_ordem(cliente, cenario):
    resposta = _get(cliente, cenario)
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["known_at"] == "2026-11-10"
    # o FIP tem dois sinais; entre os de um, quem entrou vem antes de quem só controla
    assert _raizes(resposta) == [FUNDO, COMPRADORA, ABERTA]
    assert _comprador(resposta, FUNDO)["signals"] == [
        "took_stake",
        "fund_stake",
    ]
    assert _comprador(resposta, COMPRADORA)["signals"] == ["took_stake"]
    assert _comprador(resposta, ABERTA)["signals"] == ["controls_in_sector"]
    assert corpo["total_buyers"] == 3
    assert corpo["truncated"] is False
    assert corpo["limits"] and "não intenção de compra" in corpo["limits"][0]
    assert {f["source"] for f in corpo["sources"]} >= {
        "rfb-cnpj",
        "cvm-fidc-base",
        "cvm-hist-fre",
    }


def test_o_setor_diz_o_pedido_e_quantas_empresas_ativas(cliente, cenario):
    setor = _get(cliente, cenario, years=2).json()["sector"]
    assert setor == {
        "cnae_code": SETOR,
        "state_code": None,
        "years": 2,
        "since": "2024-11-10",
        "active_companies": 3,  # a baixada e a de fora do setor não contam
    }


def test_a_prova_traz_a_empresa_do_setor_e_cada_campo_com_fonte_e_dia(cliente, cenario):
    resposta = _get(cliente, cenario)
    compradora = _comprador(resposta, COMPRADORA)
    assert compradora["legal_name"]["value"] == NOMES[COMPRADORA]
    assert compradora["legal_name"]["source"] == "rfb-cnpj"
    entradas = compradora["evidence"]["took_stake"]
    assert (
        entradas["count"] == 1
    )  # a de fora do setor e a da empresa baixada não contam
    (exemplo,) = entradas["examples"]
    assert exemplo["sector_company"]["cnpj_root"] == ALVO_SP
    assert exemplo["sector_company"]["legal_name"]["value"] == NOMES[ALVO_SP]
    assert exemplo["state_code"] == "SP"
    assert exemplo["entry_date"]["value"] == "2025-03-10"
    assert exemplo["entry_date"]["published_at"] == "2025-05-31"
    assert exemplo["stake_still_held"] is True
    (controlada,) = _comprador(resposta, ABERTA)["evidence"]["controls_in_sector"][
        "examples"
    ]
    assert (
        controlada["sector_company"]["cnpj_root"] == ALVO_SP
    )  # o FRE antigo, com a do RJ, ficou para trás
    assert controlada["kind"]["value"] == "controlada"
    assert controlada["ownership_pct"]["value"] == 70.0
    assert controlada["reference_period"]["value"] == "2025-12-31"


def test_fundador_mesmo_grupo_janela_e_futuro_nao_contam(cliente, cenario):
    raizes = set(_raizes(_get(cliente, cenario)))
    assert not raizes & {FUNDADORA, IRMA, HOLDING, VELHA, FUTURA}
    # com uma janela de 10 anos a entrada de 2018 conta (a sócia de 2010 é de antes da janela)
    assert VELHA in _raizes(_get(cliente, cenario, years=10))


def test_comprador_fora_da_lista_sem_pessoa_nao_sai(cliente, cenario):
    resposta = _get(cliente, cenario)
    assert SEM_LISTA not in _raizes(resposta)
    texto = resposta.text
    assert SEM_LISTA not in texto
    chaves = aj.chaves_de(resposta.json())
    assert not chaves & {
        "cpf",
        "id_pessoa",
        "nome_socio",
        "qualificacao",
        "raiz_socio_pj",
        "tipo_socio",
    }


def test_a_uf_corta_o_setor(cliente, cenario):
    resposta = _get(cliente, cenario, state="sp")
    assert resposta.json()["sector"]["state_code"] == "SP"
    assert _raizes(resposta) == [COMPRADORA, ABERTA]  # o FIP é sócio da empresa do RJ


def test_o_limite_corta_e_avisa(cliente, cenario):
    corpo = _get(cliente, cenario, limit=1).json()
    assert [c["cnpj_root"] for c in corpo["buyers"]] == [FUNDO]
    assert corpo["truncated"] is True
    assert corpo["total_buyers"] == 3


def test_setor_sem_comprador_sai_com_a_lista_vazia(cliente, cenario):
    corpo = _get(cliente, cenario, cnae="0111301").json()
    assert corpo["buyers"] == []
    assert corpo["total_buyers"] == 0


# ---------------------------------------------------------------- sem olhar o futuro


def test_como_era_antes_da_versao_nova_do_fre_e_do_retrato_de_outubro(cliente, cenario):
    resposta = _get(cliente, cenario, known_at="2026-10-15")
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert (
        corpo["sector"]["active_companies"] == 2
    )  # a NOVA só aparece no retrato de outubro
    (controlada,) = _comprador(resposta, ABERTA)["evidence"]["controls_in_sector"][
        "examples"
    ]
    assert controlada["ownership_pct"]["value"] == 60.0  # a versão 2 só chegou em 20/10


def test_versao_nova_do_fre_sem_a_controlada_tira_o_sinal(cliente, cenario, pasta):
    # a versão 2 do FRE de 2025 já não traz a controlada do setor: vale a versão mais nova da companhia
    fre = _controladas().iloc[:2].assign(cnpj=[_cnpj(ALVO_SP), _cnpj(FORA)])
    _gravar(pasta / compradores.CONTROLADAS / "2025.parquet", fre)
    assert ABERTA not in _raizes(_get(cliente, cenario))
    assert ABERTA in _raizes(_get(cliente, cenario, known_at="2026-10-15"))


def test_sem_retrato_publico_na_data_e_404(cliente, cenario):
    assert _get(cliente, cenario, known_at="2026-01-01").status_code == 404


# ---------------------------------------------------------------- recusas


@pytest.mark.parametrize(
    ("parametros", "codigo"),
    [
        ({"cnae": "62"}, "invalid_cnae"),
        ({"cnae": "62015011"}, "invalid_cnae"),
        ({"cnae": "abcde"}, "invalid_cnae"),
        ({"state": "XX"}, "invalid_state"),
        ({"years": 0}, "invalid_years"),
        ({"years": 11}, "invalid_years"),
        ({"limit": 0}, "invalid_limit"),
        ({"limit": 51}, "invalid_limit"),
        ({"known_at": "2026-12-01"}, "invalid_known_at"),
    ],
)
def test_pedido_fora_da_forma_e_400(cliente, cenario, parametros, codigo):
    resposta = _get(cliente, cenario, **parametros)
    assert resposta.status_code == 400
    assert codigo in resposta.text


def test_sem_cnae_e_422(cliente, cenario):
    _ator, _org, chave = cenario
    assert cliente.get(ROTA, headers=aj.bearer(chave.valor)).status_code == 422


def test_cnae_com_pontuacao_vale():
    pedido = compradores.pedido_dos_parametros("62.01-5/01", " rj ", None, None)
    assert pedido == compradores.PedidoDeCompradores("6201501", "RJ", 3, 20)


# ---------------------------------------------------------------- o portão


def test_sem_as_tabelas_prontas_nada_sai(cliente, cenario, monkeypatch):
    monkeypatch.setattr(rotas, "regras_da_api", lambda: _regras())
    assert _get(cliente, cenario).status_code == 404


def test_sinal_com_tabela_nao_pronta_fica_de_fora(cliente, cenario, monkeypatch):
    sem_fre = tuple(t for t in TABELAS if t != compradores.CONTROLADAS)
    monkeypatch.setattr(rotas, "regras_da_api", lambda: _regras(*sem_fre))
    resposta = _get(cliente, cenario)
    assert resposta.status_code == 200
    assert ABERTA not in _raizes(resposta)
    assert "cvm-hist-fre" not in {f["source"] for f in resposta.json()["sources"]}


def test_sem_contrato_do_conjunto_e_404(banco, monkeypatch, pasta):
    ator = aj.admin(banco)
    org = aj.organizacao(banco, ator)
    chave = aj.chave(banco, ator, org)
    aj.contrato(banco, ator, org, conjunto="prospecting")
    monkeypatch.setattr(rotas, "regras_da_api", lambda: _regras(*TABELAS))
    cliente = aj.cliente_da_api(monkeypatch, AGORA)
    resposta = cliente.get(ROTA, params={"cnae": SETOR}, headers=aj.bearer(chave.valor))
    assert resposta.status_code == 404


# ---------------------------------------------------------------- sinal não disponível (linha 881)


def test_com_todos_os_sinais_a_lista_de_fora_sai_vazia(cliente, cenario):
    corpo = _get(cliente, cenario).json()
    assert corpo["unavailable_signals"] == []
    assert corpo["limits"] == list(compradores.LIMITES)
    assert compradores.LIMITE_DO_SINAL_NAO_DISPONIVEL not in corpo["limits"]


def test_sem_a_tabela_na_base_o_sinal_tambem_fica_de_fora(cliente, cenario, pasta):
    """A base sem a tabela do FRE: o sinal não foi consultado, como se o portão o barrasse."""
    for arquivo in (pasta / compradores.CONTROLADAS).iterdir():
        arquivo.unlink()
    (pasta / compradores.CONTROLADAS).rmdir()
    corpo = _get(cliente, cenario).json()
    assert corpo["unavailable_signals"] == ["controls_in_sector"]


@pytest.fixture
def duas(banco, monkeypatch, pasta):
    """Duas organizações: uma com o contrato de `buyers`, outra só com o de `prospecting`; o FRE sem
    prontidão (o sinal das controladas barrado pelo portão)."""
    ator = aj.admin(banco)
    com_buyers = aj.organizacao(banco, ator, "Organização com compradores")
    sem_buyers = aj.organizacao(banco, ator, "Organização sem compradores")
    aj.contrato(banco, ator, com_buyers, conjunto=compradores.CONJUNTO)
    aj.contrato(banco, ator, sem_buyers, conjunto="prospecting")
    sem_fre = tuple(t for t in TABELAS if t != compradores.CONTROLADAS)
    monkeypatch.setattr(rotas, "regras_da_api", lambda: _regras(*sem_fre))
    cliente = aj.cliente_da_api(monkeypatch, AGORA)
    return (
        cliente,
        aj.chave(banco, ator, com_buyers).valor,
        aj.chave(banco, ator, sem_buyers).valor,
    )


def test_o_sinal_barrado_vem_como_nao_disponivel_e_os_limites_nao_falam_dele(duas):
    """Sem a lista de fora, a falta da companhia aberta leria como "ninguém controla empresa no setor"."""
    cliente, com_buyers, _sem_buyers = duas
    resposta = cliente.get(ROTA, params={"cnae": SETOR}, headers=aj.bearer(com_buyers))
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert ABERTA not in _raizes(resposta)
    assert corpo["unavailable_signals"] == ["controls_in_sector"]
    assert compradores.LIMITE_DO_SINAL_NAO_DISPONIVEL in corpo["limits"]
    assert "unavailable_signals" in compradores.LIMITE_DO_SINAL_NAO_DISPONIVEL
    assert compradores.LIMITES_DO_SINAL[compradores.CONTROLA] not in corpo["limits"]
    assert compradores.LIMITES_DO_SINAL[compradores.ENTROU] in corpo["limits"]
    assert corpo["limits"][0] == compradores.LIMITES_GERAIS[0]
    assert corpo["limits"][-1] == compradores.LIMITES_GERAIS[-1]


def test_a_organizacao_sem_o_contrato_recebe_404_e_nao_a_lista(duas):
    cliente, _com_buyers, sem_buyers = duas
    resposta = cliente.get(ROTA, params={"cnae": SETOR}, headers=aj.bearer(sem_buyers))
    assert resposta.status_code == 404
    assert resposta.json() == {"detail": "not_available"}


def test_o_fundo_barrado_tira_so_o_sinal_do_fundo(cliente, cenario, monkeypatch):
    sem_fundos = tuple(t for t in TABELAS if t != compradores.FUNDOS)
    monkeypatch.setattr(rotas, "regras_da_api", lambda: _regras(*sem_fundos))
    corpo = _get(cliente, cenario).json()
    assert corpo["unavailable_signals"] == ["fund_stake"]
    assert compradores.LIMITES_DO_SINAL[compradores.FUNDO] not in corpo["limits"]


def test_a_lista_de_fora_acompanha_o_portao_mesmo_com_a_resposta_guardada(
    cliente, cenario, monkeypatch
):
    """A mesma pergunta com outro portão não pode receber a lista guardada do primeiro (o cache da 848)."""
    assert _get(cliente, cenario).json()["unavailable_signals"] == []
    sem_fre = tuple(t for t in TABELAS if t != compradores.CONTROLADAS)
    monkeypatch.setattr(rotas, "regras_da_api", lambda: _regras(*sem_fre))
    assert _get(cliente, cenario).json()["unavailable_signals"] == [
        "controls_in_sector"
    ]


# ---------------------------------------------------------------- as cópias reduzidas do VPS (linha 844)


def _so_reduzidas(pasta) -> None:
    """Troca as tabelas inteiras do FRE e do registro de fundos pelas cópias reduzidas, como no VPS: montadas
    e conferidas pela mesma trava do recorte."""
    con = duckdb.connect()
    empresas = sorted((pasta / compradores.EMPRESAS).glob("*.parquet"))
    origens = {
        reduzidas.CONTROLADAS_PJ: sorted(
            (pasta / compradores.CONTROLADAS).glob("*.parquet")
        ),
        reduzidas.FIPS_REGISTRADOS: [
            pasta / "fidc" / "cadastro" / "registro_fundo.parquet"
        ],
    }
    montar = {
        reduzidas.CONTROLADAS_PJ: reduzidas.montar_controladas_pj,
        reduzidas.FIPS_REGISTRADOS: reduzidas.montar_fips_registrados,
    }
    destinos = {nome: pasta / nome / f"{nome}.parquet" for nome in reduzidas.REDUZIDAS}
    for nome, destino in destinos.items():
        montar[nome](con, origens[nome], empresas, destino)
    reduzidas.conferir_reduzidas(con, destinos, empresas)
    shutil.rmtree(pasta / compradores.CONTROLADAS)
    shutil.rmtree(pasta / "fidc")


def test_so_com_as_copias_reduzidas_a_resposta_e_a_mesma(cliente, cenario, pasta):
    antes = [
        _get(cliente, cenario, known_at=dia).json()
        for dia in ("2026-11-10", "2026-10-15")
    ]
    _so_reduzidas(pasta)
    depois = [
        _get(cliente, cenario, known_at=dia).json()
        for dia in ("2026-11-10", "2026-10-15")
    ]
    assert depois == antes
    assert _comprador(_get(cliente, cenario), FUNDO)["signals"] == [
        "took_stake",
        "fund_stake",
    ]
    assert ABERTA in _raizes(_get(cliente, cenario))


def test_na_copia_reduzida_a_versao_nova_sem_a_controlada_tambem_tira_o_sinal(
    cliente, cenario, pasta
):
    # a versão 2 só tem uma controlada fora da lista sem pessoa (MEI, por exemplo): ela não vai à cópia, mas a
    # marca do documento vai, e a versão 1 não volta a valer
    sem_lista = "99000099"
    assert sem_lista not in NOMES
    fre = _controladas().iloc[:2].assign(cnpj=[_cnpj(ALVO_SP), _cnpj(sem_lista)])
    _gravar(pasta / compradores.CONTROLADAS / "2025.parquet", fre)
    _so_reduzidas(pasta)
    assert ABERTA not in _raizes(_get(cliente, cenario))
    assert ABERTA in _raizes(_get(cliente, cenario, known_at="2026-10-15"))


def test_na_copia_reduzida_o_portao_segue_pela_tabela_inteira(
    cliente, cenario, pasta, monkeypatch
):
    # a prontidão é a da tabela de onde a cópia sai: sem a do FRE, o sinal não sai nem pela cópia
    _so_reduzidas(pasta)
    sem_fre = tuple(t for t in TABELAS if t != compradores.CONTROLADAS)
    monkeypatch.setattr(rotas, "regras_da_api", lambda: _regras(*sem_fre))
    resposta = _get(cliente, cenario)
    assert resposta.status_code == 200
    assert ABERTA not in _raizes(resposta)
