"""A resposta de uma companhia aberta cabe na conversa (ensaio de 19/11/2026, ordem da Diretoria).

Dois defeitos achados pelo conector de produção: `demonstracoes` de uma companhia grande dava "grande demais"
mesmo com `fim_do_periodo` (cada linha leva 12 valores com fonte, dia e, no piloto, a frase de piloto: uns 2,5 mil
caracteres; um período passa de 300 linhas), e `ficha_da_empresa` trazia 60 e poucas entregas de DFP e ITR
inteiras. Os testes rodam o conector e a API de verdade (`httpx.ASGITransport`), sem rede, com uma base de
mentira do tamanho de uma companhia grande; o CNPJ é de ninguém. Risco: a ferramenta falhar de novo, ou cortar sem
dizer o que cortou, ou perder a frase de piloto do que entrega (D11.3).
"""

import json

import httpx
import pandas as pd
import pytest

from base.ponto_no_tempo import COLUNAS_DA_BASE
from base.porta import Porta
from base.prontidao import AVISO_DE_PILOTO
from conector_remoto import enxugar
from conector_remoto.saida import TETO_DE_CARACTERES
from src import api
from src.api_externa import VARIAVEL_DA_CHAVE, rotas
from tests import ajudantes_da_api_externa as aj_api
from tests import ajudantes_do_conector as aj
from tests.test_api_externa_demonstracoes import CNPJ_DA_BASE, EMPRESA, ROTA
from tests.test_api_externa_piloto import (  # noqa: F401 (fixtures)
    _envelopes,
    _sem_aviso,
    duas,
)

CHAVE = aj.CHAVE_DE_MENTIRA
# quantas contas tem cada demonstrativo da companhia de mentira (os números de uma companhia grande)
CONTAS = {"DRE": 35, "BPA": 45, "BPP": 55, "DFC_MI": 45, "DVA": 30, "DMPL": 60}
INICIOS = {"DRE": "2025-01-01", "DFC_MI": "2025-01-01", "DVA": "2025-01-01"}


def _linhas(
    grupo: str,
    demonstracao: str,
    fim: str,
    versao: int,
    documento: str = "DFP",
    divulgado_em: str = "2026-03-15",
    ate: str | None = None,
) -> list[tuple]:
    return [
        (
            demonstracao,
            f"{demonstracao}.{n:02d}" if demonstracao != "DRE" else f"3.{n:02d}",
            f"Conta {n} do {demonstracao}",
            INICIOS.get(demonstracao) if documento == "DFP" else None,
            fim,
            float(versao * 1000 + n),
            documento,
            fim,
            versao,
            "ultimo",
            "dados_abertos",
            divulgado_em,
            ate,
            grupo,
        )
        for n in range(1, CONTAS[demonstracao] + 1)
    ]


def _base_grande() -> pd.DataFrame:
    """Uma companhia grande: seis demonstrativos, consolidado e individual, o ano de 2025 em duas versões, o
    de 2024 e o primeiro trimestre de 2026 (ITR)."""
    linhas: list[tuple] = []
    for grupo in ("con", "ind"):
        for demonstracao in CONTAS:
            linhas += _linhas(
                grupo, demonstracao, "2025-12-31", 1, ate="2026-04-10"
            )  # a versão antiga
            linhas += _linhas(
                grupo, demonstracao, "2025-12-31", 2, divulgado_em="2026-04-10"
            )
            linhas += _linhas(
                grupo, demonstracao, "2024-12-31", 1, divulgado_em="2025-03-20"
            )
    for demonstracao in (
        "DRE",
        "BPA",
    ):  # só o consolidado do ITR tem DRE e BPA aqui; o individual só o BPA
        linhas += _linhas(
            "con", demonstracao, "2026-03-31", 1, "ITR", divulgado_em="2026-05-10"
        )
    linhas += _linhas("ind", "BPA", "2026-03-31", 1, "ITR", divulgado_em="2026-05-10")
    colunas = (
        "demonstracao", "conta", "descricao", "inicio", "fim", "valor", "documento", "referencia",
        "versao", "ordem", "origem", "divulgado_em", "ate", "grupo",
    )  # fmt: skip
    base = pd.DataFrame(linhas, columns=list(colunas)).assign(
        cnpj=CNPJ_DA_BASE, empresa="ALFA ENERGIA S.A."
    )[list(COLUNAS_DA_BASE)]
    for coluna in ("inicio", "fim", "referencia", "divulgado_em", "ate"):
        base[coluna] = pd.to_datetime(base[coluna])
    return base


@pytest.fixture
def pasta(tmp_path, monkeypatch):
    """A base grande no lugar da pequena: a fixture `duas` usa esta."""
    base = tmp_path / "base"
    arquivo = base / "demonstracoes" / "2025.parquet"
    arquivo.parent.mkdir(parents=True)
    _base_grande().to_parquet(arquivo, index=False)
    monkeypatch.setattr(rotas, "abrir_porta", lambda banco_: Porta(base, banco_))
    return base


@pytest.fixture
def conector(duas):  # noqa: F811 (a fixture importada)
    cliente_da_api, chaves, _ator, _org = duas
    transporte = httpx.ASGITransport(app=api.criar_app({VARIAVEL_DA_CHAVE: "1"}))
    with aj.conector(transporte) as cliente:
        yield cliente, chaves, cliente_da_api


def _demonstracoes(conector, **argumentos) -> dict:
    cliente, chaves, _api = conector
    corpo = aj.chamar_ok(
        cliente, chaves["piloto"], "demonstracoes", cnpj=EMPRESA, **argumentos
    )
    assert isinstance(corpo, dict)
    return corpo


def _chaves_das_linhas(corpo: dict) -> list[tuple]:
    return [
        (l["statement"]["value"], l["group"]["value"], l["account"]["value"])
        for l in corpo["rows"]
    ]


# ---------------------------------------------------------------- o defeito: um período já passava do teto


def test_a_resposta_crua_da_api_de_um_periodo_passa_do_teto(conector) -> None:
    """Reproduz o ensaio: sem o recorte do conector, um período só já não cabia na conversa."""
    _cliente, chaves, cliente_da_api = conector
    crua = cliente_da_api.get(
        ROTA,
        params={"period_end": "2025-12-31"},
        headers=aj_api.bearer(chaves["piloto"]),
    )
    assert crua.status_code == 200
    assert len(crua.text) > TETO_DE_CARACTERES


def test_um_periodo_de_companhia_grande_cabe_na_conversa(conector) -> None:
    cliente, chaves, _api = conector
    erro, texto = aj.chamar(
        cliente,
        chaves["piloto"],
        "demonstracoes",
        cnpj=EMPRESA,
        fim_do_periodo="2025-12-31",
    )
    assert not erro, texto[:300]
    assert len(texto) < TETO_DE_CARACTERES
    corpo = json.loads(texto)
    assert corpo["truncated"] is True
    assert corpo["limits"]


def test_o_que_cabe_e_so_a_versao_nova_e_o_consolidado(conector) -> None:
    corpo = _demonstracoes(conector, fim_do_periodo="2025-12-31")
    chaves = _chaves_das_linhas(corpo)
    assert chaves, "nenhuma linha entregue"
    assert {grupo for _d, grupo, _c in chaves} == {"con"}
    assert len(chaves) == len(set(chaves))  # cada conta uma vez só
    versoes = {l["revision"]["value"] for l in corpo["rows"]}
    assert versoes == {2}
    assert {l["end"]["value"] for l in corpo["rows"]} == {"2025-12-31"}


def test_a_ordem_vai_do_resultado_para_o_resto(conector) -> None:
    corpo = _demonstracoes(conector, fim_do_periodo="2025-12-31")
    demonstrativos = [d for d, _g, _c in _chaves_das_linhas(corpo)]
    assert demonstrativos[0] == "DRE"
    primeiro_do_bpa = demonstrativos.index("BPA")
    assert set(demonstrativos[:primeiro_do_bpa]) == {"DRE"}


def test_o_que_ficou_de_fora_aparece_em_limits(conector) -> None:
    corpo = _demonstracoes(conector, fim_do_periodo="2025-12-31")
    limites = " ".join(corpo["limits"])
    assert "`visao`" in limites  # o individual ficou de fora
    assert "`demonstrativo`" in limites and "`conta`" in limites  # o corte para caber


def test_a_frase_de_piloto_segue_em_cada_valor_que_sai(conector) -> None:
    corpo = _demonstracoes(conector, fim_do_periodo="2025-12-31")
    assert list(_envelopes(corpo)), "nenhum valor com fonte e data"
    assert _sem_aviso(corpo) == []
    assert corpo["pilot_notice"] == AVISO_DE_PILOTO


# ---------------------------------------------------------------- escolher o demonstrativo, a conta, a visão


def test_demonstrativo_traz_so_ele_e_inteiro(conector) -> None:
    corpo = _demonstracoes(conector, fim_do_periodo="2025-12-31", demonstrativo="dre")
    chaves = _chaves_das_linhas(corpo)
    assert {d for d, _g, _c in chaves} == {"DRE"}
    assert len(chaves) == CONTAS["DRE"]
    assert not any("cortada" in l for l in corpo["limits"])


def test_demonstrativo_dfc_vale_para_o_fluxo_de_caixa_dos_dois_metodos(
    conector,
) -> None:
    corpo = _demonstracoes(conector, fim_do_periodo="2025-12-31", demonstrativo="DFC")
    assert {d for d, _g, _c in _chaves_das_linhas(corpo)} == {"DFC_MI"}


def test_conta_traz_a_conta_e_as_de_dentro_dela(conector) -> None:
    corpo = _demonstracoes(
        conector, fim_do_periodo="2025-12-31", demonstrativo="DRE", conta="3.01"
    )
    assert [c for _d, _g, c in _chaves_das_linhas(corpo)] == ["3.01"]


def test_visao_ambos_traz_os_dois_grupos(conector) -> None:
    corpo = _demonstracoes(
        conector, fim_do_periodo="2025-12-31", demonstrativo="DRE", visao="ambos"
    )
    assert {g for _d, g, _c in _chaves_das_linhas(corpo)} == {"con", "ind"}


def test_visao_individual_traz_so_o_individual(conector) -> None:
    corpo = _demonstracoes(
        conector, fim_do_periodo="2025-12-31", demonstrativo="DRE", visao="individual"
    )
    assert {g for _d, g, _c in _chaves_das_linhas(corpo)} == {"ind"}


def test_sem_fim_do_periodo_vem_o_mais_novo_e_diz_quais_ha(conector) -> None:
    corpo = _demonstracoes(conector)
    assert {l["end"]["value"] for l in corpo["rows"]} == {"2026-03-31"}
    avisos = " ".join(corpo["limits"])
    assert "2025-12-31" in avisos and "2024-12-31" in avisos
    assert "`fim_do_periodo`" in avisos


def test_o_consolidado_ausente_cai_no_individual(conector) -> None:
    """No ITR de 2026 o BPA tem os dois grupos e a DRE só o consolidado: o consolidado vale onde existe."""
    corpo = _demonstracoes(conector, fim_do_periodo="2026-03-31")
    chaves = _chaves_das_linhas(corpo)
    assert {g for _d, g, _c in chaves} == {"con"}
    assert {d for d, _g, _c in chaves} == {"DRE", "BPA"}


def test_pedido_que_nao_acha_nada_diz_o_que_a_api_mandou(conector) -> None:
    corpo = _demonstracoes(
        conector, fim_do_periodo="2025-12-31", demonstrativo="DRE", conta="9.99"
    )
    assert corpo["rows"] == []
    assert "Nada foi estimado" in " ".join(corpo["limits"])


@pytest.mark.parametrize(
    "argumentos",
    [
        {"demonstrativo": "DRE; DROP"},
        {"demonstrativo": "x"},
        {"conta": "abc"},
        {"conta": "3."},
        {"visao": "tudo"},
    ],
)
def test_pedido_mal_formado_e_recusado(conector, argumentos) -> None:
    cliente, chaves, _api = conector
    erro, _texto = aj.chamar(
        cliente, chaves["piloto"], "demonstracoes", cnpj=EMPRESA, **argumentos
    )
    assert erro


# ---------------------------------------------------------------- o recorte em si, sem a API


def _linha(
    demonstracao: str,
    grupo: str,
    conta: str,
    fim: str,
    versao: int,
    publicado: str = "2026-03-15",
) -> dict:
    def envelope(valor: object) -> dict:
        return {
            "value": valor,
            "source": "cvm-hist-dfp",
            "published_at": publicado,
            "observed_at": None,
        }

    return {
        "statement": envelope(demonstracao),
        "group": envelope(grupo),
        "account": envelope(conta),
        "end": envelope(fim),
        "start": envelope(None),
        "revision": envelope(versao),
        "value": envelope(1.0),
    }


def test_corpo_que_nao_e_o_esperado_passa_como_veio() -> None:
    for corpo in (None, "texto", [1], {"outra": []}, {"rows": "texto"}, {"rows": [1]}):
        assert enxugar.enxugar_demonstracoes(corpo) == corpo


def test_o_corte_deixa_a_resposta_dentro_do_teto(monkeypatch) -> None:
    linhas = [_linha("DRE", "con", f"3.{n:02d}", "2025-12-31", 1) for n in range(50)]
    corpo = {"cnpj": EMPRESA, "rows": linhas}
    monkeypatch.setattr(enxugar.saida, "TETO_DE_CARACTERES", 12_000)
    saida = enxugar.enxugar_demonstracoes(corpo, periodo_pedido=True)
    assert isinstance(saida, dict)
    assert 0 < len(saida["rows"]) < 50
    assert enxugar.saida.tamanho_em_caracteres(saida) <= 12_000
    assert saida["truncated"] is True
    assert "DRE" in " ".join(saida["limits"])


def test_as_linhas_do_mesmo_fato_viram_uma_a_mais_nova() -> None:
    antiga = _linha("DRE", "con", "3.01", "2025-12-31", 1, "2026-03-15")
    nova = _linha("DRE", "con", "3.01", "2025-12-31", 2, "2026-04-10")
    saida = enxugar.enxugar_demonstracoes({"rows": [antiga, nova]}, periodo_pedido=True)
    assert isinstance(saida, dict)
    assert saida["rows"] == [nova]


def test_o_aviso_da_api_nao_some() -> None:
    corpo = {
        "rows": [_linha("DRE", "con", "3.01", "2025-12-31", 1)],
        "limits": ["da API"],
        "truncated": False,
    }
    antiga = _linha("DRE", "con", "3.01", "2025-12-31", 0, "2026-01-01")
    corpo["rows"].append(antiga)
    saida = enxugar.enxugar_demonstracoes(corpo, periodo_pedido=True)
    assert isinstance(saida, dict)
    assert saida["limits"][0] == "da API"
    assert saida["truncated"] is True


# ---------------------------------------------------------------- a ficha: as entregas mais novas


CNPJ = "11111111000191"


def _entrega(n: int) -> dict:
    envelope = {
        "value": f"DFP {n}",
        "source": "cvm-hist-dfp",
        "published_at": "2026-03-15",
        "observed_at": None,
    }
    return {"document": envelope, "reference": {**envelope, "value": f"2026-{n:02d}"}}


def _ficha(entregas: int, **mais: object) -> dict:
    return {
        "cnpj": CNPJ,
        "periodic_filings": [_entrega(n) for n in range(entregas)],
        **mais,
    }


def _chamar_ficha(corpo: dict, conjuntos=("profiles",), **argumentos) -> dict:
    transporte = aj.api_de_mentira(
        {
            f"/companies/{CNPJ}/profile": httpx.Response(200, json=corpo),
            f"/companies/{CNPJ}": httpx.Response(200, json=corpo),
        },
        conjuntos=conjuntos,
    )
    with aj.conector(transporte) as cliente:
        saida = aj.chamar_ok(
            cliente, CHAVE, "ficha_da_empresa", cnpj=CNPJ, **argumentos
        )
    assert isinstance(saida, dict)
    return saida


@pytest.mark.parametrize("conjuntos", [("profiles",), ("companies",)])
def test_a_ficha_traz_so_as_oito_entregas_mais_novas(conjuntos) -> None:
    saida = _chamar_ficha(_ficha(64), conjuntos)
    assert saida["periodic_filings"] == _ficha(64)["periodic_filings"][:8]
    assert saida["truncated"] is True
    aviso = " ".join(saida["limits"])
    assert "64" in aviso and "`limite_de_entregas`" in aviso


def test_a_ficha_deixa_pedir_mais_entregas() -> None:
    saida = _chamar_ficha(_ficha(64), limite_de_entregas=20)
    assert len(saida["periodic_filings"]) == 20


def test_a_ficha_com_poucas_entregas_passa_como_veio() -> None:
    corpo = _ficha(5, limits=["da API"])
    saida = _chamar_ficha(corpo)
    assert saida["periodic_filings"] == corpo["periodic_filings"]
    assert "truncated" not in saida and saida["limits"] == ["da API"]


def test_a_ficha_de_empresa_fechada_nao_muda() -> None:
    corpo = {"cnpj": CNPJ, "registration": {"value": "ativa"}, "limits": ["x"]}
    assert _chamar_ficha(corpo) == corpo


def test_a_ficha_recusa_limite_fora_da_faixa() -> None:
    transporte = aj.api_de_mentira(
        {f"/companies/{CNPJ}/profile": httpx.Response(200, json=_ficha(3))}
    )
    with aj.conector(transporte) as cliente:
        for limite in (0, enxugar.LIMITE_MAXIMO_DAS_ENTREGAS + 1):
            erro, _texto = aj.chamar(
                cliente, CHAVE, "ficha_da_empresa", cnpj=CNPJ, limite_de_entregas=limite
            )
            assert erro


def test_o_aviso_de_corte_cita_so_parametro_que_a_ferramenta_tem() -> None:
    transporte = aj.api_de_mentira({})
    with aj.conector(transporte) as cliente:
        lista = aj.rpc(cliente, CHAVE, "tools/list").json()["result"]["tools"]
    parametros = {f["name"]: set(f["inputSchema"].get("properties", {})) for f in lista}
    assert "limite_de_entregas" in parametros["ficha_da_empresa"]
    assert {"demonstrativo", "visao", "conta", "fim_do_periodo"} <= parametros[
        "demonstracoes"
    ]
