"""As dez perguntas do analista pelo conector MCP (linha 831), uma a uma, pelo servidor MCP de verdade.

As dez vêm do relatório de 11/11 (`reports/2026-11-11-tema-0-dados-empresariais-por-ia.md`, seção 5). Cada
pergunta é feita como o Claude da casa de M&A a faria: `tools/call` no `/mcp` do conector, com a chave de
mentira, contra a API de mentira (`ajudantes_do_conector.api_de_mentira`); as respostas de mentira têm a
forma da API (campo com `value`, `source` e `published_at`), e os CNPJs são de ninguém. O teste confere o
caminho (qual ferramenta, quais parâmetros chegam à API) e a forma da resposta: tem fonte e data, não tem
pessoa física e, onde a base não tem o dado, a frase honesta. Não confere o dado em si: isso é da API.

A tabela abaixo é a fonte única do placar: o teste a lê daqui e falha se ela deixar de bater com o conector
(ferramenta citada que não existe, ferramenta que existe e está marcada "sem ferramenta", ferramenta
registrada que nenhuma pergunta usa). A ferramenta `ativos` (linha 901) entrou em 16/11 e a linha 7 virou
"fraca": ela só cobre petróleo e gás da ANP. Situações: "respondida" (a pergunta fecha
com as ferramentas da linha), "fraca" (responde em parte e diz o que falta) e "sem ferramenta" (ainda não
há ferramenta, e o conector não finge que há).

| # | situação | ferramentas | o que falta |
|---|---|---|---|
| 1 | respondida | ficha_da_empresa | nada: cadastro, situação e matriz ou filial |
| 2 | respondida | buscar_empresas | a primeira página não é o universo: o `next_cursor` avisa |
| 3 | fraca | demonstracoes | faturamento de empresa fechada não existe na base: diz "não temos" |
| 4 | respondida | vinculos | só pessoa jurídica; controle e coligação só da companhia aberta |
| 5 | respondida | compradores_do_setor | é movimento passado, não intenção de compra |
| 6 | fraca | compradores_do_setor, fundo | só os FIPs que são sócios de empresas do setor; sem busca por segmento |
| 7 | fraca | ativos | só contratos de petróleo e gás da ANP; mineração e o resto vêm em `not_covered` |
| 8 | fraca | eventos, novidades | sem protesto, baixa ou atraso de crédito; sinal não é intenção de venda |
| 9 | respondida | comparaveis, setores, setor | só companhia aberta; sem múltiplo de transação |
| 10 | fraca | buscar_empresas, ficha_da_empresa, eventos, vinculos, comparaveis, o_que_posso_ver | o conector devolve texto: não exporta arquivo |
"""

import json
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import date

import httpx
import pandas as pd
import pytest
from starlette.testclient import TestClient

from base.porta import Porta
from conector_remoto import ferramentas, servidor
from conector_remoto.pessoa import sinais_de_pessoa
from conector_remoto.saida import TETO_DE_CARACTERES
from src.api_externa import rotas
from src.api_externa.conjuntos import prospeccao
from tests import ajudantes_do_conector as aj
from tests.ajudantes_de_cpf import CPF_DE_TESTE, formatado, meio
from tests.test_api_externa_prospeccao import CARIMBOS, _gravar
from tests.test_conector_remoto_ponta_a_ponta import (  # noqa: F401 (fixtures)
    cenario,
    cliente,
)

HOJE = date(2026, 11, 16)
ALFA = "11111111000191"  # companhia aberta de mentira
ALFA_FILIAL = "11111111000272"
GAMA = "33333333000191"  # empresa fechada de mentira
FIP = "44444444000191"  # um fundo de mentira
CNAE_DO_SETOR = "62015"
# os conjuntos do catálogo de mentira: os 11 de sempre e o dos ativos (linha 845)
CONJUNTOS = (
    "prospecting", "profiles", "companies", "comparables", "financials", "sectors", "funds",
    "events", "links", "buyers", "research", "assets",
)  # fmt: skip
_LINHA_DA_TABELA = re.compile(
    r"^\| (\d+) \| (respondida|fraca|sem ferramenta) \| ([a-z_, ]+) \|", re.MULTILINE
)
# uma frase de erro cabe em poucas linhas; erro grande seria dado vazando
TAMANHO_MAXIMO_DA_FRASE_DE_ERRO = 1000
FRASE_SEM_FATURAMENTO = "Faturamento de empresa fechada a base não tem"


def _campo(valor: object, fonte: str = "rfb-cnpj", dia: str = "2026-09-30") -> dict:
    return {"value": valor, "source": fonte, "published_at": dia, "observed_at": None}


def _fontes(*nomes: str) -> list[dict]:
    return [
        {"source": n, "license": "CC BY", "attribution": f"Fonte: {n}"} for n in nomes
    ]


def _json(corpo: dict) -> httpx.Response:
    return httpx.Response(200, json=corpo)


def _cadastro(cnpj: str, nome: str, matriz: bool) -> dict:
    return {
        "cnpj": cnpj,
        "legal_name": _campo(nome),
        "head_office": _campo(matriz),
        "registration_status": _campo("ativa"),
        "opened_at": _campo("2010-05-01"),
        "cnae_code": _campo("6201501"),
        "size": _campo("other"),
    }


def _empresa_da_busca(cnpj: str, nome: str) -> dict:
    return _cadastro(cnpj, nome, matriz=True) | {"state_code": _campo("SP")}


def _exemplo(alvo: str, sinal: str) -> dict:
    return {
        "target_cnpj": alvo,
        "signal": sinal,
        "source": "rfb-cnpj",
        "published_at": "2026-09-30",
    }


def _comprador(cnpj: str, nome: str, tipo: str, sinal: str) -> dict:
    return {
        "cnpj": cnpj,
        "legal_name": _campo(nome),
        "buyer_type": tipo,
        "signal_count": 2,
        "signals": [{"signal": sinal, "examples": [_exemplo(ALFA, sinal)]}],
    }


def _par(cnpj: str, nome: str, receita: float) -> dict:
    return {
        "cnpj": cnpj,
        "legal_name": _campo(nome, "cvm-dfp", "2026-03-31"),
        "revenue": _campo(receita, "cvm-dfp", "2026-03-31"),
        "ebitda": _campo(receita / 4, "cvm-dfp", "2026-03-31"),
    }


def _rotas_de_mentira() -> dict[str, httpx.Response]:
    """O que a API de mentira responde a cada rota que as dez perguntas usam."""
    limites = [{"code": "sem_pessoa", "text": "Só pessoa jurídica."}]
    return {
        f"/companies/{ALFA}/profile": _json(
            _cadastro(ALFA, "ALFA TECNOLOGIA S.A.", True)
            | {"sources": _fontes("rfb-cnpj"), "limits": limites}
        ),
        f"/companies/{ALFA_FILIAL}/profile": _json(
            _cadastro(ALFA_FILIAL, "ALFA TECNOLOGIA S.A.", False)
            | {"sources": _fontes("rfb-cnpj")}
        ),
        "/companies": _json(
            {
                "known_at": HOJE.isoformat(),
                "companies": [
                    _empresa_da_busca(ALFA, "ALFA TECNOLOGIA S.A."),
                    _empresa_da_busca("22222222000191", "BETA SOFTWARE LTDA"),
                ],
                "truncated": True,
                "next_cursor": "MjIyMjIyMjIwMDAxOTE",
                "sources": _fontes("rfb-cnpj"),
            }
        ),
        # GAMA e CNPJ sem demonstração: 404 `not_available`, que é a resposta padrão do dublê
        f"/companies/{ALFA}/links": _json(
            {
                "known_at": HOJE.isoformat(),
                "links": [
                    {
                        "type": "subsidiary_of",
                        "from": {
                            "cnpj_root": "11111111",
                            "legal_name": "ALFA TECNOLOGIA S.A.",
                        },
                        "to": {
                            "cnpj_root": "55555555",
                            "legal_name": "OMEGA HOLDING S.A.",
                        },
                        "capital_share": _campo(60.0, "cvm-fre", "2026-05-31"),
                        "valid_from": "2026-05-31",
                    },
                    {
                        "type": "audits",
                        "from": {
                            "cnpj_root": "66666666",
                            "legal_name": "AUDITORES ASSOCIADOS",
                        },
                        "to": {
                            "cnpj_root": "11111111",
                            "legal_name": "ALFA TECNOLOGIA S.A.",
                        },
                        "source": "cvm-fca",
                        "published_at": "2026-05-31",
                    },
                ],
                "limits": [
                    {
                        "code": "so_companhia_aberta",
                        "text": "Controle: só companhia aberta.",
                    }
                ],
                "sources": _fontes("cvm-fre", "cvm-fca"),
            }
        ),
        "/buyers": _json(
            {
                "known_at": HOJE.isoformat(),
                "buyers": [
                    _comprador(
                        "77777777000191",
                        "SIGMA PARTICIPACOES S.A.",
                        "company",
                        "entered_as_partner",
                    ),
                    _comprador(FIP, "FIP TECNOLOGIA I", "fund", "fip_partner"),
                ],
                "limits": [
                    {
                        "code": "movimento_passado",
                        "text": "Movimento passado, não intenção.",
                    }
                ],
                "sources": _fontes("rfb-cnpj"),
            }
        ),
        f"/funds/{FIP}": _json(
            {
                "cnpj": FIP,
                "class": _campo("FIP", "cvm-fundos", "2026-10-31"),
                "net_assets": _campo(250_000_000.0, "cvm-fundos", "2026-10-31"),
                "sources": _fontes("cvm-fundos"),
            }
        ),
        f"/companies/{ALFA}/financials": _json(
            {
                "cnpj": ALFA,
                "periods": [
                    {
                        "period_end": "2025-12-31",
                        "accounts": [
                            {
                                "code": "3.01",
                                "name": "Receita de Venda de Bens e/ou Serviços",
                                "amount": _campo(1_000_000.0, "cvm-dfp", "2026-03-31"),
                            }
                        ],
                    }
                ],
                "limits": limites,
            }
        ),
        f"/companies/{ALFA}/assets": _json(
            {
                "cnpj": ALFA,
                "known_at": HOJE.isoformat(),
                "oil_gas_contracts": {
                    "found": True,
                    "truncated": False,
                    "source": "anp-concessionarios",
                    "latest_published_at": "2025-03-01",
                    "coverage": "contratos de E&P vigentes",
                    "items": [
                        {
                            "contract_number": _campo(
                                "48000.001/2010", "anp-concessionarios", "2025-03-01"
                            ),
                            "phase": _campo(
                                "Produção", "anp-concessionarios", "2025-03-01"
                            ),
                            "basin": _campo(
                                "Santos", "anp-concessionarios", "2025-03-01"
                            ),
                            "contract_share_pct": _campo(
                                60.0, "anp-concessionarios", "2025-03-01"
                            ),
                            "is_operator": _campo(
                                True, "anp-concessionarios", "2025-03-01"
                            ),
                        }
                    ],
                },
                "not_covered": ["mineração (barragens e royalties da ANM)"],
                "limits": limites,
                "sources": _fontes("anp-concessionarios"),
            }
        ),
        f"/companies/{ALFA}/events": _json(
            {
                "known_at": HOJE.isoformat(),
                "events": [
                    {
                        "type": "ipe_filing",
                        "category": _campo("Fato Relevante", "cvm-ipe", "2026-10-20"),
                        "protocol": _campo("00000000001", "cvm-ipe", "2026-10-20"),
                    },
                    {
                        "type": "auditor_change",
                        "new_auditor": _campo(
                            "AUDITORES ASSOCIADOS", "cvm-fca", "2026-08-15"
                        ),
                    },
                ],
                "sources": _fontes("cvm-ipe", "cvm-fca"),
            }
        ),
        "/research/news": _json(
            {
                "news": [
                    {
                        "agency": "CADE",
                        "source": "cade-atos",
                        "published_at": "2026-11-12",
                        "excerpt": "Ato de concentração envolvendo empresa do setor de software.",
                        "excerpt_cut": None,
                        "sha256": "a" * 64,
                    }
                ],
                "sources": _fontes("cade-atos"),
            }
        ),
        f"/companies/{ALFA}/comparables": _json(
            {
                "known_at": HOJE.isoformat(),
                "company": _par(ALFA, "ALFA TECNOLOGIA S.A.", 800.0),
                "peers": [
                    _par("88888888000191", "PI TECNOLOGIA S.A.", 900.0),
                    _par("99999999000191", "TAU SISTEMAS S.A.", 700.0),
                ],
                "peer_median": {"revenue": _campo(800.0, "cvm-dfp", "2026-03-31")},
                "sources": _fontes("cvm-dfp"),
            }
        ),
        "/sectors": _json(
            {
                "sectors": [{"key": "software", "name": "Software"}],
                "sources": _fontes("cvm-dfp"),
            }
        ),
        "/sectors/software": _json(
            {
                "key": "software",
                "concentration": {"cr4": _campo(0.4, "cvm-dfp", "2026-03-31")},
                "sources": _fontes("cvm-dfp"),
            }
        ),
        "/usage": _json(
            {
                "month": "2026-11",
                "requests": {"used": 12, "limit": 5000},
                "rows": {"used": 340},
            }
        ),
    }


@dataclass(frozen=True)
class Chamada:
    """Uma chamada de ferramenta: o que voltou do servidor MCP."""

    ferramenta: str
    erro: bool
    texto: str

    @property
    def corpo(self) -> dict:
        assert not self.erro, self.texto
        corpo = json.loads(self.texto)
        assert isinstance(corpo, dict)
        return corpo


@dataclass
class Analista:
    """O Claude do analista: faz as chamadas ao conector e guarda cada uma, e o que chegou à API."""

    cliente: TestClient
    pedidos: list[httpx.Request]
    chamadas: list[Chamada] = field(default_factory=list)

    def perguntar(self, ferramenta: str, **argumentos: object) -> Chamada:
        erro, texto = aj.chamar(
            self.cliente, aj.CHAVE_DE_MENTIRA, ferramenta, **argumentos
        )
        chamada = Chamada(ferramenta, erro, texto)
        self.chamadas.append(chamada)
        return chamada

    def pedido_a_api(self, caminho: str) -> httpx.Request:
        (pedido,) = [p for p in self.pedidos if p.url.path == f"/data/v1{caminho}"]
        return pedido


@pytest.fixture
def analista() -> Iterator[Analista]:
    pedidos: list[httpx.Request] = []
    transporte = aj.api_de_mentira(
        _rotas_de_mentira(), conjuntos=CONJUNTOS, pedidos=pedidos
    )
    with aj.conector(transporte) as cliente_mcp:
        yield Analista(cliente_mcp, pedidos)


# ---------------------------------------------------------------- a tabela do topo


def tabela_do_topo() -> dict[int, tuple[str, tuple[str, ...]]]:
    """número da pergunta -> (situação, ferramentas), lido da tabela do docstring deste arquivo."""
    linhas = _LINHA_DA_TABELA.findall(__doc__ or "")
    return {
        int(numero): (
            situacao,
            tuple(f.strip() for f in lista.split(",")),
        )
        for numero, situacao, lista in linhas
    }


def _ferramentas_do_conector(cliente_mcp: TestClient) -> dict[str, dict]:
    resposta = aj.rpc(cliente_mcp, aj.CHAVE_DE_MENTIRA, "tools/list")
    assert resposta.status_code == 200, resposta.text
    return {f["name"]: f for f in resposta.json()["result"]["tools"]}


def _descricao(ferramenta: dict) -> str:
    """A descrição como a IA a lê: o docstring quebra linha no meio das frases."""
    return " ".join(ferramenta["description"].split())


def _instrucoes(cliente_mcp: TestClient) -> str:
    resposta = aj.rpc(
        cliente_mcp,
        aj.CHAVE_DE_MENTIRA,
        "initialize",
        {
            "protocolVersion": aj.VERSAO_DO_PROTOCOLO,
            "capabilities": {},
            "clientInfo": {"name": "ensaio-dez-perguntas", "version": "1"},
        },
    )
    assert resposta.status_code == 200, resposta.text
    return resposta.json()["result"]["instructions"]


def test_a_tabela_do_topo_tem_as_dez_perguntas_em_ordem():
    assert list(tabela_do_topo()) == list(range(1, 11))


def test_a_tabela_do_topo_bate_com_as_ferramentas_do_conector(analista):
    no_conector = _ferramentas_do_conector(analista.cliente)
    for numero, (situacao, citadas) in tabela_do_topo().items():
        existem = [f in no_conector for f in citadas]
        if situacao == "sem ferramenta":
            assert not all(existem), (
                f"Pergunta {numero}: a tabela diz 'sem ferramenta', mas {citadas} já estão no "
                "conector. Troque a situação da linha na tabela do topo do arquivo (e confira a "
                "chamada da pergunta)."
            )
        else:
            assert all(existem), (
                f"Pergunta {numero}: a tabela diz '{situacao}', mas faltam no conector: "
                f"{[f for f in citadas if f not in no_conector]}."
            )


def test_toda_ferramenta_do_conector_serve_a_alguma_pergunta(analista):
    citadas = {f for _s, lista in tabela_do_topo().values() for f in lista}
    sobram = set(_ferramentas_do_conector(analista.cliente)) - citadas
    assert not sobram, (
        f"Ferramenta nova no conector sem pergunta na tabela do topo: {sorted(sobram)}. "
        "Ponha-a na linha da pergunta que ela responde (ou explique por que nenhuma)."
    )


def test_so_as_ferramentas_do_conector_estao_na_tabela_ou_em_ativos():
    registradas = set(ferramentas.CONJUNTOS_DA_FERRAMENTA)
    citadas = {f for _s, lista in tabela_do_topo().values() for f in lista}
    assert citadas - registradas <= {"ativos"}, citadas - registradas


def test_as_instrucoes_citam_as_ferramentas_das_perguntas_que_o_conector_responde(
    analista,
):
    instrucoes = _instrucoes(analista.cliente)
    no_conector = _ferramentas_do_conector(analista.cliente)
    for numero, (situacao, citadas) in tabela_do_topo().items():
        if situacao == "sem ferramenta":
            # o conector não promete o que não tem
            assert not any(f"`{f}`" in instrucoes for f in citadas), numero
            continue
        for ferramenta in citadas:
            assert ferramenta in no_conector
            assert f"`{ferramenta}`" in instrucoes, (
                f"Pergunta {numero}: as instruções do servidor não citam `{ferramenta}`."
            )


# ---------------------------------------------------------------- a forma de toda resposta


def _campos_sem_fonte_e_data(no: object, caminho: str = "") -> Iterator[str]:
    """Onde há um campo com `value` sem `source` ou sem `published_at` (o caminho, sem o valor)."""
    if isinstance(no, dict):
        if "value" in no and not (no.get("source") and no.get("published_at")):
            yield caminho or "(raiz)"
        for chave, filho in no.items():
            yield from _campos_sem_fonte_e_data(filho, f"{caminho}.{chave}")
    elif isinstance(no, list):
        for indice, filho in enumerate(no):
            yield from _campos_sem_fonte_e_data(filho, f"{caminho}[{indice}]")


def _blocos_com_fonte_e_data(no: object) -> int:
    """Quantos objetos trazem `source` e `published_at` preenchidos, em qualquer profundidade."""
    if isinstance(no, dict):
        aqui = 1 if no.get("source") and no.get("published_at") else 0
        return aqui + sum(_blocos_com_fonte_e_data(f) for f in no.values())
    if isinstance(no, list):
        return sum(_blocos_com_fonte_e_data(f) for f in no)
    return 0


# resposta que não é dado de empresa e, por isso, não tem bloco com fonte e dia
SEM_BLOCO_DE_FONTE = {
    "setores": "só a lista de chaves dos setores",
    "o_que_posso_ver": "catálogo e consumo da própria chave",
}


def conferir_a_forma(chamada: Chamada) -> None:
    """Resposta de dado: JSON, fonte e data em TODO campo com `value`, nenhuma pessoa física."""
    corpo = chamada.corpo
    if chamada.ferramenta not in SEM_BLOCO_DE_FONTE:
        assert _blocos_com_fonte_e_data(corpo), (
            f"{chamada.ferramenta}: nenhum bloco com fonte e data"
        )
        sem_fonte = list(_campos_sem_fonte_e_data(corpo))
        assert not sem_fonte, (
            f"{chamada.ferramenta}: campo sem fonte ou data: {sem_fonte}"
        )
    # o mesmo filtro do conector (chaves por palavra, CPF com ou sem pontos, e-mail), não uma lista nossa
    assert not sinais_de_pessoa(corpo), chamada.ferramenta


# ---------------------------------------------------------------- as dez perguntas


def pergunta_1(analista: Analista) -> None:
    """Quem é esta empresa pelo CNPJ, e é matriz ou filial?"""
    matriz = analista.perguntar("ficha_da_empresa", cnpj=ALFA)
    filial = analista.perguntar("ficha_da_empresa", cnpj="11.111.111/0002-72")
    assert matriz.corpo["head_office"]["value"] is True
    assert filial.corpo["head_office"]["value"] is False
    assert matriz.corpo["legal_name"]["value"] == "ALFA TECNOLOGIA S.A."
    assert analista.pedido_a_api(
        f"/companies/{ALFA_FILIAL}/profile"
    )  # a pontuação saiu


def pergunta_2(analista: Analista) -> None:
    """Quais matrizes ativas, com mais de cinco anos, atuam neste segmento e região?"""
    cinco_anos_atras = HOJE.replace(year=HOJE.year - 5).isoformat()
    busca = analista.perguntar(
        "buscar_empresas",
        cnae=["62"],
        uf=["SP"],
        so_matriz=True,
        aberta_antes_de=cinco_anos_atras,
        limite=20,
    )
    parametros = analista.pedido_a_api("/companies").url.params
    assert parametros["head_office"] == "true"
    assert parametros["opened_before"] == cinco_anos_atras
    assert parametros["state"] == "SP" and parametros["cnae"] == "62"
    assert [e["cnpj"] for e in busca.corpo["companies"]] == [ALFA, "22222222000191"]
    # a primeira página não é o universo: a resposta diz que há mais
    assert busca.corpo["truncated"] is True and busca.corpo["next_cursor"]


def pergunta_3(analista: Analista) -> None:
    """Quanto a empresa fechada fatura, em qual ano e com qual prova?"""
    aberta = analista.perguntar("demonstracoes", cnpj=ALFA)
    assert aberta.corpo["periods"][0]["accounts"][0]["amount"]["source"] == "cvm-dfp"
    resposta = analista.perguntar("demonstracoes", cnpj=GAMA)
    assert resposta.erro
    assert FRASE_SEM_FATURAMENTO in resposta.texto
    assert "não estima" in resposta.texto
    # a frase é a resposta: nada de número no lugar dela
    assert not re.search(r"R\$\s*\d", resposta.texto)


def pergunta_4(analista: Analista) -> None:
    """Quais empresas controlam esta empresa e quais controladas ela tem?"""
    vinculos = analista.perguntar("vinculos", cnpj=ALFA, profundidade=1)
    assert analista.pedido_a_api(f"/companies/{ALFA}/links").url.params["depth"] == "1"
    tipos = {v["type"] for v in vinculos.corpo["links"]}
    assert "subsidiary_of" in tipos
    # só pessoa jurídica (raiz de CNPJ nas duas pontas) e a ressalva de quem informa o controle
    assert all(
        "cnpj_root" in v["from"] and "cnpj_root" in v["to"]
        for v in vinculos.corpo["links"]
    )
    assert any(
        "companhia aberta" in limite["text"] for limite in vinculos.corpo["limits"]
    )


def pergunta_5(analista: Analista) -> None:
    """Quem comprou empresas deste setor e poderia integrar uma lista inicial de compradores?"""
    compradores = analista.perguntar(
        "compradores_do_setor", cnae=CNAE_DO_SETOR, uf="SP", anos=3, limite=10
    )
    parametros = analista.pedido_a_api("/buyers").url.params
    assert parametros["cnae"] == CNAE_DO_SETOR and parametros["state"] == "SP"
    assert parametros["years"] == "3"
    assert {b["cnpj"] for b in compradores.corpo["buyers"]} == {
        "77777777000191",
        FIP,
    }
    # a ressalva "movimento passado, não intenção de compra" vem na resposta
    assert compradores.corpo["limits"]


def pergunta_6(analista: Analista) -> None:
    """Quais fundos já investem em empresas deste segmento?"""
    compradores = analista.perguntar(
        "compradores_do_setor", cnae=CNAE_DO_SETOR, uf="SP"
    ).corpo["buyers"]
    (fip,) = [b["cnpj"] for b in compradores if b["buyer_type"] == "fund"]
    fundo = analista.perguntar("fundo", cnpj=fip)
    assert fundo.corpo["class"]["value"] == "FIP"
    assert fundo.corpo["class"]["source"] == "cvm-fundos"


def pergunta_7(analista: Analista) -> None:
    """Quais ativos ou autorizações regulatórias estão vinculados a este CNPJ?"""
    ativos = analista.perguntar("ativos", cnpj=ALFA)
    assert analista.pedido_a_api(f"/companies/{ALFA}/assets")
    bloco = ativos.corpo["oil_gas_contracts"]
    assert bloco["found"] is True and bloco["source"] == "anp-concessionarios"
    assert bloco["items"][0]["is_operator"]["value"] is True
    # a lacuna vem na resposta: o que a ferramenta não cobre (mineração) e a ressalva de achar ou não
    assert ativos.corpo["not_covered"] and ativos.corpo["limits"]


def pergunta_8(analista: Analista) -> None:
    """Quais sinais públicos justificam investigar esta empresa agora?"""
    eventos = analista.perguntar("eventos", cnpj=ALFA, limite=20)
    novidades = analista.perguntar("novidades", dias=7)
    tipos = {e["type"] for e in eventos.corpo["events"]}
    assert tipos == {"ipe_filing", "auditor_change"}
    assert analista.pedido_a_api("/research/news").url.params["days"] == "7"
    (noticia,) = novidades.corpo["news"]
    # o trecho vem com o hash do original: a prova de que o texto está lá
    assert len(noticia["sha256"]) == 64 and noticia["excerpt"]


def pergunta_9(analista: Analista) -> None:
    """Quais pares são comparáveis e quais valores podem ser comparados?"""
    pares = analista.perguntar("comparaveis", cnpj=ALFA)
    lista = analista.perguntar("setores")
    (setor,) = lista.corpo["sectors"]
    contexto = analista.perguntar("setor", chave=setor["key"])
    assert len(pares.corpo["peers"]) == 2
    assert pares.corpo["peer_median"]["revenue"]["source"] == "cvm-dfp"
    assert contexto.corpo["concentration"]["cr4"]["published_at"]


def pergunta_10(analista: Analista) -> None:
    """Monte uma lista curta e uma ficha com fontes, lacunas e consumo, e exporte o resultado."""
    lista = analista.perguntar("buscar_empresas", cnae=["62"], uf=["SP"], limite=3)
    alvo = lista.corpo["companies"][0]["cnpj"]
    # a ficha do dossiê: as quatro ferramentas, com o mesmo CNPJ, na ordem das instruções
    analista.perguntar("ficha_da_empresa", cnpj=alvo)
    analista.perguntar("eventos", cnpj=alvo)
    analista.perguntar("vinculos", cnpj=alvo, profundidade=1)
    analista.perguntar("comparaveis", cnpj=alvo)
    # a lacuna: companhia fechada não tem comparáveis, e a ferramenta diz "Não disponível"
    sem_pares = analista.perguntar("comparaveis", cnpj=GAMA)
    consumo = analista.perguntar("o_que_posso_ver")
    assert sem_pares.erro and "Não disponível" in sem_pares.texto
    assert consumo.corpo["usage"]["requests"]["used"] == 12
    assert consumo.corpo["catalog"]["datasets"]


RESPONDEDORES: dict[int, Callable[[Analista], None]] = {
    1: pergunta_1,
    2: pergunta_2,
    3: pergunta_3,
    4: pergunta_4,
    5: pergunta_5,
    6: pergunta_6,
    7: pergunta_7,
    8: pergunta_8,
    9: pergunta_9,
    10: pergunta_10,
}


def _responder(numero: int, analista: Analista) -> None:
    """Faz a pergunta e confere o que ela confere sozinha; a forma geral é de quem chama."""
    RESPONDEDORES[numero](analista)


@pytest.mark.parametrize("numero", range(1, 11))
def test_a_pergunta_usa_so_as_ferramentas_da_tabela(numero, analista):
    _responder(numero, analista)
    usadas = {c.ferramenta for c in analista.chamadas}
    assert usadas == set(tabela_do_topo()[numero][1])


@pytest.mark.parametrize("numero", range(1, 11))
def test_toda_resposta_de_dado_tem_fonte_e_data_e_nenhuma_pessoa(numero, analista):
    _responder(numero, analista)
    for chamada in analista.chamadas:
        # erro é a frase honesta (conferida na pergunta); só dado entra aqui
        if not chamada.erro:
            conferir_a_forma(chamada)


@pytest.mark.parametrize("numero", range(1, 11))
def test_nenhuma_resposta_leva_a_chave_e_o_erro_e_uma_frase_curta(numero, analista):
    _responder(numero, analista)
    for chamada in analista.chamadas:
        assert aj.CHAVE_DE_MENTIRA not in chamada.texto
        if chamada.erro:
            assert len(chamada.texto) < TAMANHO_MAXIMO_DA_FRASE_DE_ERRO


# ---------------------------------------------------------------- as frases honestas das lacunas


# a lacuna que o conector confessa em cada pergunta "fraca": (onde, trecho). "instrucoes" é o texto do
# `initialize`; o resto é o nome da ferramenta, e o trecho está na descrição dela.
LACUNA_DITA_POR_PERGUNTA_FRACA = {
    # faturamento de fechada
    3: (
        ("instrucoes", "faturamento de empresa fechada"),
        ("demonstracoes", "Não traz: faturamento de empresa fechada"),
    ),
    # os fundos são só os FIPs sócios de empresas do setor
    6: (("instrucoes", "FIPs que entraram como sócios"),),
    # sem nada novo, a lista vem vazia e a ferramenta manda dizer que não há fonte provada
    8: (("novidades", "Não traz: fonte sem prova gravada"),),
    # os ativos são só contratos de petróleo e gás da ANP: o resto (mineração) o conector diz que não traz
    7: (("ativos", "mineração, por exemplo"),),
    # o dossiê é composto pela IA, com a lacuna anotada em vez de preenchida
    10: (("instrucoes", servidor.ORIENTACAO_DO_DOSSIE),),
}


def _onde_esta(onde: str, no_conector: dict[str, dict], instrucoes: str) -> str:
    return instrucoes if onde == "instrucoes" else _descricao(no_conector[onde])


def test_toda_pergunta_fraca_da_tabela_tem_a_lacuna_conferida(analista):
    """A coluna 'situação' vale: virar 'fraca' sem lacuna dita (ou 'respondida' com uma) falha."""
    fracas = {
        n for n, (situacao, _f) in tabela_do_topo().items() if situacao == "fraca"
    }
    assert fracas == set(LACUNA_DITA_POR_PERGUNTA_FRACA), (
        f"A tabela do topo marca como fracas {sorted(fracas)}, e as lacunas conferidas são "
        f"{sorted(LACUNA_DITA_POR_PERGUNTA_FRACA)}. Ajuste os dois lados juntos."
    )
    no_conector = _ferramentas_do_conector(analista.cliente)
    instrucoes = _instrucoes(analista.cliente)
    for numero, trechos in LACUNA_DITA_POR_PERGUNTA_FRACA.items():
        for onde, trecho in trechos:
            assert trecho in _onde_esta(onde, no_conector, instrucoes), (
                f"Pergunta {numero}: o conector deixou de dizer {trecho!r} em {onde}."
            )


def test_a_pergunta_5_avisa_que_compradores_sao_movimento_passado(analista):
    # 5 é "respondida", mas a ressalva "não intenção de compra" é o que a mantém honesta
    no_conector = _ferramentas_do_conector(analista.cliente)
    assert "nem intenção de compra" in _descricao(no_conector["compradores_do_setor"])


def test_as_instrucoes_dizem_que_a_base_nao_tem_pessoa_fisica(analista):
    instrucoes = _instrucoes(analista.cliente)
    assert "dado de pessoa física (sócio pessoa física, CPF, contato)" in instrucoes


# o que a API não deveria mandar, mas, se mandar, o conector tem de barrar (sem repetir o valor)
RESPOSTAS_COM_PESSOA = {
    "campo de sócio": {"partners": [{"name": _campo("NOME DE MENTIRA")}]},
    "campo de sócio em outra grafia": {"socio_nome": _campo("NOME DE MENTIRA")},
    "e-mail no texto": {"contact": _campo("pessoa@exemplo.invalid")},
    "CPF formatado no texto": {"note": _campo(f"titular {formatado(CPF_DE_TESTE)}")},
}


@pytest.mark.parametrize("sinal", RESPOSTAS_COM_PESSOA)
def test_o_conector_barra_pessoa_fisica_que_a_api_mandar(sinal):
    """Sem isto, as conferências de 'sem pessoa' do arquivo só olhariam o próprio dublê."""
    pessoa = RESPOSTAS_COM_PESSOA[sinal]
    perfil = _json(_cadastro(ALFA, "ALFA TECNOLOGIA S.A.", matriz=True) | pessoa)
    rotas_de_mentira = _rotas_de_mentira() | {f"/companies/{ALFA}/profile": perfil}
    transporte = aj.api_de_mentira(rotas_de_mentira, conjuntos=CONJUNTOS)
    with aj.conector(transporte) as cliente_mcp:
        erro, texto = aj.chamar(
            cliente_mcp, aj.CHAVE_DE_MENTIRA, "ficha_da_empresa", cnpj=ALFA
        )
    assert erro and ferramentas.MENSAGEM_DE_PESSOA in texto
    assert "NOME DE MENTIRA" not in texto and meio(CPF_DE_TESTE) not in texto
    assert "exemplo.invalid" not in texto


# ---------------------------------------------------------------- o tamanho das respostas


def test_a_maior_resposta_de_dado_de_cada_ferramenta_cabe_no_teto(analista):
    """Mede só resposta de dado (frase de erro não conta). Com dado de mentira (poucas centenas de
    caracteres) isto só prova que toda ferramenta foi medida; o pior caso de verdade, a busca com 100
    empresas pela API de verdade, é o teste de baixo. As outras páginas cheias se medem em produção
    (roteiro privado do ensaio das dez perguntas)."""
    for numero in range(1, 11):
        _responder(numero, analista)
    maiores: dict[str, int] = {}
    for chamada in analista.chamadas:
        if chamada.erro:
            continue
        maiores[chamada.ferramenta] = max(
            maiores.get(chamada.ferramenta, 0), len(chamada.texto)
        )
    medidas = {
        f: t for f, t in maiores.items() if f in ferramentas.CONJUNTOS_DA_FERRAMENTA
    }
    assert set(medidas) == set(ferramentas.CONJUNTOS_DA_FERRAMENTA), (
        "ferramenta sem resposta medida: "
        f"{sorted(set(ferramentas.CONJUNTOS_DA_FERRAMENTA) - set(medidas))}"
    )
    acima = {f: t for f, t in medidas.items() if t >= TETO_DE_CARACTERES}
    assert not acima, f"resposta acima do teto de {TETO_DE_CARACTERES}: {acima}"
    print("maior resposta por ferramenta (caracteres):", medidas)


LINHAS_DA_PAGINA_CHEIA = 100


@pytest.fixture
def pasta(tmp_path, monkeypatch):
    """100 empresas de mentira do mesmo CNAE e UF, para a busca devolver a página inteira."""
    base = tmp_path / "base"
    estabelecimentos, empresas = [], []
    for i in range(LINHAS_DA_PAGINA_CHEIA + 20):
        raiz = f"{20_000_000 + i:08d}"
        estabelecimentos.append(
            (raiz + "000191", raiz, True, "02", "2010-05-01", "6201501", "SP", "7107", "2026-09", "2026-09-30")
        )  # fmt: skip
        empresas.append(
            (raiz, f"EMPRESA DE TESTE {i:03d} TECNOLOGIA E SERVICOS LTDA", "2062", "pequeno", 100_000.0, 1, "2026-09", "2026-09-30")
        )  # fmt: skip
    tabela = pd.DataFrame(
        estabelecimentos,
        columns=[
            "cnpj", "cnpj_basico", "matriz", "situacao_cadastral", "data_inicio_atividade",
            "cnae_principal", "uf", "municipio", "mes_do_retrato", "disponivel_em",
        ],
    )  # fmt: skip
    tabela["data_inicio_atividade"] = pd.to_datetime(tabela["data_inicio_atividade"])
    tabela["disponivel_em"] = pd.to_datetime(tabela["disponivel_em"]).dt.date
    donas = pd.DataFrame(
        empresas,
        columns=[
            "cnpj_basico", "razao_social", "natureza_juridica", "porte", "capital_social",
            "n_estabelecimentos", "mes_do_retrato", "disponivel_em",
        ],
    )  # fmt: skip
    donas["disponivel_em"] = pd.to_datetime(donas["disponivel_em"]).dt.date
    _gravar(base, prospeccao.ESTABELECIMENTOS, tabela.assign(**CARIMBOS))
    _gravar(base, prospeccao.EMPRESAS, donas.assign(**CARIMBOS))
    monkeypatch.setattr(rotas, "abrir_porta", lambda banco_: Porta(base, banco_))
    return base


def test_a_pagina_cheia_da_busca_com_a_api_de_verdade_cabe_no_teto(cliente, cenario):  # noqa: F811
    """A maior página da ferramenta que mais pesa (100 empresas), com a API de verdade e sem rede."""
    erro, texto = aj.chamar(
        cliente,
        cenario["chave_com_busca"].valor,
        "buscar_empresas",
        cnae=["62"],
        uf=["SP"],
        limite=ferramentas.LIMITE_MAXIMO_DA_BUSCA,
    )
    assert not erro, texto[:300]
    empresas = json.loads(texto)["companies"]
    assert len(empresas) == ferramentas.LIMITE_MAXIMO_DA_BUSCA
    print(
        f"busca com {len(empresas)} empresas: {len(texto)} caracteres "
        f"({len(texto) * 100 // TETO_DE_CARACTERES}% do teto de {TETO_DE_CARACTERES})"
    )
    assert len(texto) < TETO_DE_CARACTERES
