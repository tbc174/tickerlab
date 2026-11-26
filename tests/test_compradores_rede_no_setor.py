"""A rede do comprador no setor (linha 1121, bot Analista, simulação 6): `GET /data/v1/buyers`.

O caso: uma rede de postos de outra UF, que já opera na UF do alvo por filial e abriu um lote de filiais no mesmo
dia (compra incorporada vira filial), não aparecia entre os compradores porque o único sinal da Receita era a
entrada como sócia PJ. Agora cada comprador traz a rede no setor (estabelecimentos ativos da raiz no CNAE, por UF) e
há dois sinais novos: `branch_in_state` (filial ativa do CNAE na UF pedida, com a matriz em outra UF) e
`same_day_branches` (3 ou mais filiais ativas do CNAE abertas no mesmo dia, na janela), com a ordem opcional pelo
tamanho da rede (`order=network`).

Base de mentira, sem internet; as raízes são de ninguém e só há pessoa jurídica. Riscos: vazar pessoa (quem não está
na lista sem pessoa não sai), olhar o futuro (abertura depois do dia não conta) e chamar de rede o que não é (filial
baixada, filial da própria UF da matriz, lote fora da janela).
"""

import dataclasses
import re
from datetime import UTC, date, datetime

import pandas as pd
import pytest

from base import prontidao
from base.porta import Porta
from base.prontidao import Prontidao, Prova
from src import portao_externo as portao
from src.api_externa import rotas
from src.api_externa.conjuntos import compradores
from tests import ajudantes_da_api_externa as aj

AGORA = datetime(2026, 11, 10, 12, tzinfo=UTC)
ROTA = "/data/v1/buyers"
POSTOS = "4731800"
CARIMBOS = {
    "origem_sha256": "0" * 64,
    "montado_em": pd.Timestamp("2026-11-05", tz="UTC"),
    "versao_do_codigo": "teste",
}
REDE, PEQUENA, LOCAL, VELHA, HOLDING, ALVO, SEM_LISTA, FORA = (
    "31000001",  # rede de fora (matriz no PR): 39 postos, 3 em SC, lote de 10 filiais no mesmo dia
    "31000002",  # matriz no PR e uma filial em SC
    "31000003",  # rede só de SC, sem lote
    "31000004",  # lote de 4 filiais fora da janela de 3 anos
    "31000005",  # holding que entrou como sócia do alvo
    "31000006",  # o alvo, em SC
    "31000007",  # filial em SC, mas fora da lista sem pessoa
    "31000008",  # matriz no PR com filial em SC de outro CNAE
)
OUTRA_HOLDING = "31000009"  # entrou como sócia da REDE: comprador de sempre
# rede do PR com lote de 3 filiais em 2024, cujo único posto em SC abre depois do dia pedido (achado do Revisor)
FUTURA_EM_SC = "31000010"
LOTE = "2024-04-04"
NOMES = {
    REDE: "REDE DE POSTOS DE FORA LTDA",
    PEQUENA: "POSTO PEQUENO LTDA",
    LOCAL: "REDE LOCAL LTDA",
    VELHA: "REDE ANTIGA LTDA",
    HOLDING: "HOLDING PARTICIPACOES LTDA",
    OUTRA_HOLDING: "OUTRA HOLDING LTDA",
    FUTURA_EM_SC: "REDE QUE CHEGA DEPOIS LTDA",
    ALVO: "ALVO POSTOS LTDA",
    FORA: "OUTRO RAMO LTDA",
}  # SEM_LISTA fica fora: não está na lista sem pessoa


def _rede() -> list[tuple]:
    """Os 39 postos ativos da REDE (PR 19, RS 11, SP 6, SC 3), a matriz no PR; o lote de 04/04/2024 tem 10
    filiais em PR, RS e SC. Mais uma filial baixada em SC, que não conta."""
    linhas = [(REDE, "02", "2015-01-01", "PR", True)]
    linhas += [(REDE, "02", LOTE, "SC", False)] * 3
    linhas += [(REDE, "02", LOTE, "PR", False)] * 4
    linhas += [(REDE, "02", LOTE, "RS", False)] * 3
    linhas += [(REDE, "02", "2018-05-01", "PR", False)] * 14
    linhas += [(REDE, "02", "2019-05-01", "RS", False)] * 8
    linhas += [(REDE, "02", "2020-05-01", "SP", False)] * 6
    linhas += [(REDE, "08", "2021-05-01", "SC", False)]  # baixada
    return linhas


# raiz, situação, abertura, UF, matriz (CNAE de postos, salvo a FORA)
ESTABELECIMENTOS = [
    *_rede(),
    (PEQUENA, "02", "2016-01-01", "PR", True),
    (PEQUENA, "02", "2025-02-01", "SC", False),
    (
        PEQUENA,
        "02",
        "2026-11-20",
        "SC",
        False,
    ),  # abertura depois do dia pedido: não conta
    (FUTURA_EM_SC, "02", "2015-01-01", "PR", True),
    *[(FUTURA_EM_SC, "02", "2024-06-01", "PR", False)] * 3,  # o lote, no PR
    (
        FUTURA_EM_SC,
        "02",
        "2026-11-20",
        "SC",
        False,
    ),  # o único posto em SC, depois do dia pedido
    (LOCAL, "02", "2010-01-01", "SC", True),
    (LOCAL, "02", "2024-06-01", "SC", False),
    (LOCAL, "02", "2024-07-01", "SC", False),
    (VELHA, "02", "2005-01-01", "SC", True),
    *[(VELHA, "02", "2019-03-01", "SC", False)] * 4,
    (ALVO, "02", "2012-01-01", "SC", True),
    (ALVO, "02", "2013-01-01", "SC", False),
    (SEM_LISTA, "02", "2014-01-01", "PR", True),
    (SEM_LISTA, "02", "2025-01-01", "SC", False),
    (
        HOLDING,
        "02",
        "2011-01-01",
        "SC",
        True,
    ),  # a holding em outro CNAE (vai trocado abaixo)
    (FORA, "02", "2011-01-01", "PR", True),
    (FORA, "02", "2025-01-01", "SC", False),  # outro CNAE (vai trocado abaixo)
]
OUTRO_CNAE = {HOLDING: "6462000", FORA: "4711302"}


def _estabelecimentos() -> pd.DataFrame:
    tabela = pd.DataFrame(
        ESTABELECIMENTOS,
        columns=[
            "cnpj_basico",
            "situacao_cadastral",
            "data_inicio_atividade",
            "uf",
            "matriz",
        ],
    )
    tabela["cnae_principal"] = tabela["cnpj_basico"].map(OUTRO_CNAE).fillna(POSTOS)
    tabela["cnpj"] = [
        f"{r}{n:04d}00" for n, r in enumerate(tabela["cnpj_basico"], start=1)
    ]
    tabela["municipio"] = "8105"
    tabela["mes_do_retrato"] = "2026-10"
    tabela["disponivel_em"] = date(2026, 10, 31)
    tabela["data_inicio_atividade"] = pd.to_datetime(tabela["data_inicio_atividade"])
    return tabela.assign(**CARIMBOS)


def _empresas() -> pd.DataFrame:
    tabela = pd.DataFrame(
        [(raiz, nome) for raiz, nome in NOMES.items()],
        columns=["cnpj_basico", "razao_social"],
    )
    return tabela.assign(
        mes_do_retrato="2026-10",
        disponivel_em=date(2026, 10, 31),
        natureza_juridica="2062",
        porte="demais",
        capital_social=1_000_000.0,
        n_estabelecimentos=1,
        **CARIMBOS,
    )


def _entradas() -> pd.DataFrame:
    return pd.DataFrame({
        # a PEQUENA também entrou como sócia da LOCAL: comprador de sempre que ganha o sinal novo da filial
        "raiz_socio_pj": [HOLDING, OUTRA_HOLDING, PEQUENA],
        "cnpj_basico": [ALVO, REDE, LOCAL],
        "data_entrada": [date(2025, 5, 1), date(2025, 7, 1), date(2025, 9, 1)],
        "mes_do_retrato": ["2025-05", "2025-07", "2025-09"],
        "disponivel_em": [date(2025, 6, 30), date(2025, 8, 31), date(2025, 10, 31)],
        "movimento": ["entrou", "entrou", "entrou"],
    }).assign(qualificacao="22", **CARIMBOS)  # fmt: skip


@pytest.fixture
def pasta(tmp_path, monkeypatch):
    base = tmp_path / "base"
    for tabela, dados in (
        (compradores.ESTABELECIMENTOS, _estabelecimentos()),
        (compradores.EMPRESAS, _empresas()),
        (compradores.ENTRADAS, _entradas()),
    ):
        (base / tabela).mkdir(parents=True)
        dados.to_parquet(base / tabela / "parte.parquet", index=False)
    monkeypatch.setattr(rotas, "abrir_porta", lambda banco_: Porta(base, banco_))
    return base


TABELAS = (compradores.ESTABELECIMENTOS, compradores.EMPRESAS, compradores.ENTRADAS)


def _regras(sem_campo: str | None = None) -> portao.Regras:
    """As regras de verdade, com as tabelas prontas no dia; `sem_campo` tira do portão a linha daquele campo."""
    prova = Prova(AGORA.date(), "conferida no teste", "teste")
    versoes = prontidao.versoes_maiores()
    regras = portao.regras_vigentes()
    if sem_campo is not None:
        regras = dataclasses.replace(
            regras,
            linhas=tuple(
                d
                for d in regras.linhas
                if not (d.conjunto == compradores.CONJUNTO and d.campo == sem_campo)
            ),
        )
    return dataclasses.replace(
        regras,
        prontidao={t: Prontidao(versoes[t], prova, prova, prova) for t in TABELAS},
    )


@pytest.fixture
def cenario(banco, monkeypatch, pasta):
    ator = aj.admin(banco)
    org = aj.organizacao(banco, ator)
    chave = aj.chave(banco, ator, org)
    aj.contrato(banco, ator, org, conjunto=compradores.CONJUNTO)
    monkeypatch.setattr(rotas, "regras_da_api", lambda: _regras())
    return ator, org, chave


@pytest.fixture
def cliente(monkeypatch, cenario):
    return aj.cliente_da_api(monkeypatch, AGORA)


def _get(cliente, cenario, **parametros):
    _ator, _org, chave = cenario
    resposta = cliente.get(
        ROTA, params={"cnae": POSTOS, **parametros}, headers=aj.bearer(chave.valor)
    )
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


def _raizes(corpo) -> list[str]:
    return [c["cnpj_root"] for c in corpo["buyers"]]


def _comprador(corpo, raiz: str) -> dict:
    (achado,) = [c for c in corpo["buyers"] if c["cnpj_root"] == raiz]
    return achado


# ---------------------------------------------------------------- o caso de aceite


def test_a_rede_de_fora_aparece_em_sc_com_3_postos_na_uf_39_no_total_e_o_lote(
    cliente, cenario
):
    """O pronto da linha 1121: CNAE de postos em SC, pela rede, mostra a rede de fora em primeiro, com 3
    estabelecimentos em SC, 39 no total e o lote de 04/04/2024."""
    corpo = _get(cliente, cenario, state="SC", order="network")
    assert _raizes(corpo)[0] == REDE
    rede = _comprador(corpo, REDE)
    assert rede["signals"] == ["branch_in_state", "same_day_branches"]
    no_setor = rede["network_in_sector"]
    assert no_setor["active_establishments"]["value"] == 39
    assert no_setor["active_establishments"]["source"] == "rfb-cnpj"
    assert no_setor["active_establishments"]["published_at"] == "2026-10-31"
    por_uf = {
        u["state_code"]: u["establishments"]["value"] for u in no_setor["by_state"]
    }
    assert por_uf == {"PR": 19, "RS": 11, "SP": 6, "SC": 3}
    # do maior para o menor
    assert [u["state_code"] for u in no_setor["by_state"]] == ["PR", "RS", "SP", "SC"]

    filiais = rede["evidence"]["branch_in_state"]
    assert filiais["count"] == 3  # a baixada não conta
    exemplo = filiais["examples"][0]
    assert exemplo["sector_company"]["cnpj_root"] == REDE
    assert exemplo["state_code"] == "SC"
    assert exemplo["opened_on"]["value"] == LOTE
    assert exemplo["head_office_state"]["value"] == "PR"

    (lote,) = rede["evidence"]["same_day_branches"]["examples"]
    assert lote["opened_on"]["value"] == LOTE
    assert lote["branches"]["value"] == 10
    assert lote["states"]["value"] == ["PR", "RS", "SC"]
    assert "state_code" not in lote


def test_a_ordem_padrao_segue_a_de_hoje_e_os_sinais_novos_vem_depois_das_entradas(
    cliente, cenario
):
    corpo = _get(cliente, cenario, state="SC")
    # os de sempre na ordem de sempre (uma entrada cada; a raiz desempata) e, depois deles, quem só tem sinal da
    # rede; a PEQUENA, que também tem filial em SC, ganha o sinal novo sem mudar de lugar
    assert _raizes(corpo) == [PEQUENA, HOLDING, OUTRA_HOLDING, REDE]
    assert _comprador(corpo, PEQUENA)["signals"] == ["took_stake", "branch_in_state"]
    # a holding não tem posto: a rede dela no setor é zero, dito com todas as letras
    holding = _comprador(corpo, HOLDING)["network_in_sector"]
    assert holding["active_establishments"]["value"] == 0
    assert holding["by_state"] == []


def test_pela_rede_quem_tem_mais_postos_vem_antes(cliente, cenario):
    assert _raizes(_get(cliente, cenario, state="SC", order="network")) == [
        REDE,
        PEQUENA,
        HOLDING,
        OUTRA_HOLDING,
    ]


# ---------------------------------------------------------------- o que não é rede


def test_rede_so_da_uf_filial_de_outro_cnae_e_quem_esta_fora_da_lista_sem_pessoa_nao_entram(
    cliente, cenario
):
    raizes = set(_raizes(_get(cliente, cenario, state="SC")))
    # LOCAL: matriz em SC e sem lote; FORA: a filial em SC é de outro CNAE; SEM_LISTA: não é da lista sem pessoa;
    # VELHA: o lote é de 2019, fora da janela de 3 anos; ALVO: só filial na própria UF
    assert not raizes & {LOCAL, FORA, SEM_LISTA, VELHA, ALVO}


def test_o_lote_fora_da_janela_conta_com_a_janela_maior(cliente, cenario):
    corpo = _get(cliente, cenario, state="SC", years=10)
    velha = _comprador(corpo, VELHA)
    assert velha["signals"] == ["same_day_branches"]
    (lote,) = velha["evidence"]["same_day_branches"]["examples"]
    assert (lote["opened_on"]["value"], lote["branches"]["value"]) == ("2019-03-01", 4)


def test_sem_uf_a_filial_na_uf_nao_se_aplica_e_o_lote_ainda_acha_a_rede(
    cliente, cenario
):
    corpo = _get(cliente, cenario)
    assert _comprador(corpo, REDE)["signals"] == ["same_day_branches"]
    # sem UF a PEQUENA sai só pela entrada como sócia: a filial na UF não se aplica
    assert _comprador(corpo, PEQUENA)["signals"] == ["took_stake"]
    # não se aplica não é "não disponível"
    assert "branch_in_state" not in corpo["unavailable_signals"]


def test_abertura_depois_do_dia_nao_conta(cliente, cenario):
    """A filial da PEQUENA aberta em 20/11 está no retrato (base de mentira), mas o pedido é de 10/11: não entra na
    rede nem na prova da filial na UF."""
    pequena = _comprador(_get(cliente, cenario, state="SC"), PEQUENA)
    assert pequena["network_in_sector"]["active_establishments"]["value"] == 2
    assert pequena["evidence"]["branch_in_state"]["count"] == 1
    assert [
        e["opened_on"]["value"]
        for e in pequena["evidence"]["branch_in_state"]["examples"]
    ] == ["2025-02-01"]


def test_lote_nao_vale_para_quem_so_chega_na_uf_depois_do_dia(cliente, cenario):
    """Achado P0 do Revisor no #1336: a rede do PR com lote em 2024 cujo único posto em SC abre em 20/11 não pode
    sair na lista de SC de 10/11 (nem pelo lote, nem pela filial na UF). No país todo ela sai: o lote do PR é real."""
    assert FUTURA_EM_SC not in _raizes(_get(cliente, cenario, state="SC"))
    assert FUTURA_EM_SC not in _raizes(
        _get(cliente, cenario, state="SC", order="network")
    )
    no_pais = _comprador(_get(cliente, cenario), FUTURA_EM_SC)
    assert no_pais["signals"] == ["same_day_branches"]
    assert (
        no_pais["network_in_sector"]["active_establishments"]["value"] == 4
    )  # a de 20/11 não conta


def test_os_limites_dizem_que_rede_e_lote_sao_deducao(cliente, cenario):
    limites = " ".join(_get(cliente, cenario, state="SC")["limits"])
    assert "network_in_sector" in limites
    assert "dedução" in limites
    assert "mesmo grupo" in limites  # a rede é só da raiz: não soma o grupo
    # a ordem padrão não conta os dois sinais da rede, e o texto diz isso (P2 da revisão cruzada no #1336)
    assert (
        "branch_in_state e same_day_branches não entram na conta dos sinais" in limites
    )


# ---------------------------------------------------------------- portão e pedido


def test_sem_o_campo_matriz_no_portao_os_dois_sinais_ficam_de_fora_e_dizem_isso(
    cliente, cenario, monkeypatch
):
    monkeypatch.setattr(rotas, "regras_da_api", lambda: _regras(sem_campo="matriz"))
    corpo = _get(cliente, cenario, state="SC")
    assert set(corpo["unavailable_signals"]) >= {"branch_in_state", "same_day_branches"}
    assert _raizes(corpo) == [PEQUENA, HOLDING, OUTRA_HOLDING]


def test_ordem_desconhecida_e_recusada(cliente, cenario):
    _ator, _org, chave = cenario
    resposta = cliente.get(
        ROTA,
        params={"cnae": POSTOS, "order": "chance"},
        headers=aj.bearer(chave.valor),
    )
    assert resposta.status_code == 400
    assert "invalid_order" in resposta.text


def test_o_pedido_aceita_a_ordem_e_guarda_o_padrao():
    assert (
        compradores.pedido_dos_parametros(POSTOS, None, None, None).ordem == "entries"
    )
    assert (
        compradores.pedido_dos_parametros(POSTOS, "sc", None, None, "network").ordem
        == "network"
    )
    with pytest.raises(compradores.PedidoInvalido):
        compradores.pedido_dos_parametros(POSTOS, None, None, None, "chance")


def test_a_tela_do_analista_nao_recebe_a_rede(pasta):
    """O app (tela do analista) usa o mesmo leitor sem a rede: os sinais e o bloco novos são só da API e do
    conector por enquanto (a tela ganha as frases depois)."""
    leitor = compradores.LeitorDeCompradores(
        Porta(pasta, None), lambda *_: True, compradores.LIMITE_MAXIMO
    )
    servido = leitor.compradores(
        compradores.PedidoDeCompradores(POSTOS, "SC"), AGORA.date()
    )
    assert servido is not None
    assert [c["raiz_do_cnpj"] for c in servido.corpo["compradores"]] == [
        PEQUENA,
        HOLDING,
        OUTRA_HOLDING,
    ]
    assert servido.corpo["compradores"][0]["sinais"] == ["took_stake"]
    assert "rede_no_setor" not in servido.corpo["compradores"][0]


def _leitor(pasta, rede: bool) -> compradores.LeitorDeCompradores:
    return compradores.LeitorDeCompradores(
        Porta(pasta, None), lambda *_: True, compradores.LIMITE_MAXIMO, rede=rede
    )


@pytest.mark.parametrize("limite", [1, 2, 50])
def test_so_acrescimo_quem_ja_estava_na_lista_sai_igual_e_no_mesmo_lugar(pasta, limite):
    """Condição da Diretoria (26/11): sem o parâmetro novo, quem já aparecia fica no mesmo lugar e com os mesmos
    sinais de sempre e as mesmas provas, nada some nem muda de valor; o que ele ganha é só acréscimo (o bloco da rede
    e, se tiver, os sinais novos da filial e do lote). Os compradores só da rede vêm depois de todos eles, inclusive
    no corte."""
    pedido = compradores.PedidoDeCompradores(POSTOS, "SC", limite=limite)
    antes = _leitor(pasta, rede=False).compradores(pedido, AGORA.date())
    agora = _leitor(pasta, rede=True).compradores(pedido, AGORA.date())
    assert antes is not None and agora is not None
    de_antes = antes.corpo["compradores"]
    de_agora = agora.corpo["compradores"]
    assert len(de_agora) >= len(de_antes)
    novos = {compradores.NOME_DE_FORA[s] for s in compradores.SINAIS_DA_REDE}
    for velho, novo in zip(de_antes, de_agora, strict=False):
        sem_o_acrescimo = {
            **{k: v for k, v in novo.items() if k != "rede_no_setor"},
            "sinais": [s for s in novo["sinais"] if s not in novos],
            "provas": {
                k: v
                for k, v in novo["provas"].items()
                if k not in compradores.SINAIS_DA_REDE
            },
        }
        assert sem_o_acrescimo == velho
    # o caso que o Revisor apontou: comprador de sempre com filial na UF ganha o sinal, sem mudar de lugar
    pequena = next(c for c in de_agora if c["raiz_do_cnpj"] == PEQUENA)
    assert "branch_in_state" in pequena["sinais"]
    # os limites de antes seguem lá, na mesma ordem
    assert [
        lim for lim in agora.corpo["limites"] if lim in antes.corpo["limites"]
    ] == antes.corpo["limites"]


def _varrer(valor):
    """Toda chave ("chave", nome) e todo texto ("texto", valor) da resposta, em qualquer profundidade."""
    if isinstance(valor, dict):
        for chave, dentro in valor.items():
            yield "chave", chave
            yield from _varrer(dentro)
    elif isinstance(valor, list):
        for item in valor:
            yield from _varrer(item)
    elif isinstance(valor, str):
        yield "texto", valor


@pytest.mark.parametrize(
    "parametros", [{"state": "SC", "order": "network"}, {"years": 10}]
)
def test_varredura_sem_municipio_cnpj_de_filial_nem_quem_esta_fora_da_lista(
    cliente, cenario, parametros
):
    """Condição da Diretoria (26/11): nada de município, CNPJ (de filial ou inteiro), CPF, nem empresa fora da lista
    sem pessoa (MEI e empresário individual ficam fora dela) em lugar nenhum da resposta."""
    corpo = _get(cliente, cenario, **parametros)
    for tipo, texto in _varrer(corpo):
        baixo = texto.lower()
        assert "munic" not in baixo and "city" not in baixo, texto
        assert not re.search(r"\d{11,}", texto), texto  # CNPJ inteiro (14) ou CPF (11)
        assert SEM_LISTA not in texto, texto
        if tipo == "chave" and "cnpj" in baixo:
            assert texto == "cnpj_root", (
                texto
            )  # só a raiz, nunca o CNPJ do estabelecimento
