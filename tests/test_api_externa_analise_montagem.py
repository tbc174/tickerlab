"""A montagem da análise completa do CNPJ (`conjuntos/analise.py`), com blocos de mentira.

O que é da rota (chave, contratos, portão de verdade, consumo) está em `test_api_externa_analise.py`; aqui fica
o que é da montagem: qual bloco abre pelo que o portão libera, o prazo (o bloco lento é interrompido e o resto
sai), o portão que fecha quando o prazo acaba, o contexto do pedido nos blocos, a linha do tempo sem o futuro, a
frase só com o que o cadastro serviu e as leituras marcadas como dedução.
"""

import contextvars
import threading
import time
from dataclasses import dataclass, field
from datetime import date

import duckdb
import pytest

from base.porta import Porta
from src.api_externa.conjuntos import analise, socios_pj

DIA = date(2025, 6, 30)
CNPJ = "11111111000191"
A, C = analise.ANALISE, analise.CREDITO


@dataclass(frozen=True)
class _Servido:
    corpo: dict
    fontes: set[str] = field(default_factory=lambda: {"rfb-cnpj"})
    linhas: int = 1


def _envelope(valor, publico_em="2025-01-31"):
    return {
        "valor": valor,
        "fonte": "rfb-cnpj",
        "publico_em": publico_em,
        "visto_em": None,
    }


CADASTRO = {
    "cnpj": CNPJ,
    "como_era_em": DIA.isoformat(),
    "razao_social": _envelope("ALFA S.A."),
    "situacao_cadastral_texto": _envelope("Ativa"),
    "data_inicio_atividade": _envelope("2010-05-01"),
    "data_situacao_cadastral": _envelope(
        "2025-08-01"
    ),  # adiante do dia: não entra na linha do tempo
    "limites": ["limite do cadastro"],
}


def _ler_cadastro(_porta, _permitido, _linhas, _cnpj, _dia):
    return _Servido(dict(CADASTRO))


def _bloco(
    nome: str, ler, conjunto: str | None = None, finalidade: str = A, **outros
) -> analise.Bloco:
    return analise.Bloco(nome, conjunto or nome, finalidade, ler, **outros)


def _liberadas(*conjuntos: str, finalidade: str = A) -> set:
    return {(conjunto, finalidade, "rfb-cnpj", "campo") for conjunto in conjuntos}


@pytest.fixture
def porta(tmp_path):
    (tmp_path / "base").mkdir()
    with Porta(tmp_path / "base") as aberta:
        yield aberta


@pytest.fixture
def blocos(monkeypatch):
    """Troca os blocos de verdade pelos do teste: `blocos(*bloco)`."""
    monkeypatch.setattr(
        analise, "CADASTROS", (_bloco(analise.CADASTRO, _ler_cadastro, "profiles"),)
    )

    def trocar(*outros: analise.Bloco) -> None:
        monkeypatch.setattr(analise, "BLOCOS", outros)

    return trocar


def _tudo(_conjunto, _finalidade):
    return lambda _fonte, _campo, _derivado: True


def _montar(porta, conjuntos=("profiles",), prazo=5.0, portao=_tudo, dia=DIA, **outros):
    liberadas = set().union(
        *(_liberadas(c) for c in conjuntos), outros.pop("liberadas", set())
    )
    return analise.montar_analise(
        CNPJ,
        dia,
        porta=porta,
        liberadas=liberadas,
        portao=portao,
        linhas=20,
        prazo=prazo,
    )


# --- quais blocos abrem ----------------------------------------------------------------------------


def test_cadastro_e_o_perfil_quando_a_chave_tem_os_dois_e_a_situacao_sem_o_perfil():
    perfil, situacao = analise.CADASTROS
    assert analise.blocos_abertos(_liberadas("profiles", "companies"))[0] == perfil
    assert analise.blocos_abertos(_liberadas("companies"))[0] == situacao
    assert analise.blocos_abertos(_liberadas("links", "events"))[0] is None


def test_bloco_abre_so_com_o_conjunto_e_a_finalidade_do_contrato_dele():
    _, abertos = analise.blocos_abertos(_liberadas("companies", "credit", "links"))
    nomes = {bloco.nome for bloco in abertos}
    assert "vinculos" in nomes
    assert "credito" not in nomes  # o crédito é da finalidade crédito, não da análise
    _, abertos = analise.blocos_abertos(
        _liberadas("companies") | _liberadas("credit", finalidade=C)
    )
    assert "credito" in {bloco.nome for bloco in abertos}


def test_socios_pj_so_abre_com_a_data_de_entrada_e_o_nome_liberados():
    so_o_nome = {(socios_pj.CONJUNTO, A, "rfb-cnpj", "razao_social")}
    _, abertos = analise.blocos_abertos(_liberadas("companies") | so_o_nome)
    assert "socios_pj" not in {bloco.nome for bloco in abertos}
    os_dois = {
        (socios_pj.CONJUNTO, A, fonte, campo) for fonte, campo in socios_pj.CAMPOS
    }
    _, abertos = analise.blocos_abertos(_liberadas("companies") | os_dois)
    assert "socios_pj" in {bloco.nome for bloco in abertos}


def test_cada_rota_por_cnpj_da_analise_tem_um_bloco_com_o_conjunto_dela():
    conjuntos = {bloco.conjunto for bloco in (*analise.CADASTROS, *analise.BLOCOS)}
    assert conjuntos == {
        "profiles",
        "companies",
        "buyers",
        "links",
        "events",
        "credit",
        "assets",
        "comparables",
    }


def test_sem_cadastro_aberto_nao_ha_analise(porta, blocos):
    blocos(_bloco("vinculos", lambda *_: _Servido({"vinculos": []})))
    assert _montar(porta, conjuntos=("vinculos",)) is None


def test_cadastro_que_nao_sai_deixa_a_analise_vazia_e_negada(
    porta, blocos, monkeypatch
):
    monkeypatch.setattr(
        analise, "CADASTROS", (_bloco(analise.CADASTRO, lambda *_: None, "profiles"),)
    )
    blocos(_bloco("vinculos", lambda *_: pytest.fail("não lê bloco sem cadastro")))
    montada = _montar(porta, conjuntos=("profiles", "vinculos"))
    assert montada is not None
    assert montada.corpo == {}
    assert montada.consumo == {("profiles", A): (0, True)}


def test_bloco_fechado_nao_e_lido_nem_aparece(porta, blocos):
    blocos(
        _bloco("vinculos", lambda *_: _Servido({"vinculos": [{}]})),
        _bloco("eventos", lambda *_: pytest.fail("bloco fechado não é lido")),
    )
    montada = _montar(porta, conjuntos=("profiles", "vinculos"))
    assert montada is not None
    assert set(montada.corpo["blocos"]) == {analise.CADASTRO, "vinculos"}
    assert "eventos" not in str(montada.corpo)
    assert set(montada.consumo) == {("profiles", A), ("vinculos", A)}
    assert montada.corpo["pedidos_usados"] == 2


# --- o que não foi achado ----------------------------------------------------------------------------


def test_bloco_vazio_e_bloco_sem_dado_vao_para_o_nao_encontrado_e_contam_como_negados(
    porta, blocos
):
    blocos(
        _bloco(
            "vinculos",
            lambda *_: _Servido({"vinculos": []}, linhas=0),
            listas=("vinculos",),
        ),
        _bloco("ativos", lambda *_: None),
    )
    montada = _montar(porta, conjuntos=("profiles", "vinculos", "ativos"))
    assert montada is not None
    assert [n["bloco"] for n in montada.corpo["nao_encontrado"]] == ["links", "assets"]
    assert all(
        n["por_que"] == analise.NAO_ACHADO for n in montada.corpo["nao_encontrado"]
    )
    assert montada.consumo[("ativos", A)] == (0, True)
    assert "ativos" not in montada.corpo["blocos"]


# --- prazo ---------------------------------------------------------------------------------------


def test_bloco_lento_e_interrompido_sai_no_nao_respondeu_e_o_resto_sai(porta, blocos):
    acabou = threading.Event()
    depois_do_prazo: list[bool] = []

    def lento(porta_do_bloco, permitido, *_):
        try:
            porta_do_bloco.con.execute(
                "SELECT count(*) FROM range(100000000000) a"
            ).fetchall()
        except duckdb.Error:
            depois_do_prazo.append(permitido("rfb-cnpj", "campo", False))
            raise
        finally:
            acabou.set()

    blocos(
        _bloco("eventos", lento),
        _bloco("vinculos", lambda *_: _Servido({"vinculos": [{}]})),
    )
    inicio = time.monotonic()
    montada = _montar(porta, conjuntos=("profiles", "eventos", "vinculos"), prazo=0.5)
    assert time.monotonic() - inicio < 5
    assert montada is not None
    assert montada.corpo["nao_respondeu_a_tempo"] == [
        {"bloco": "events", "por_que": analise.NAO_RESPONDEU}
    ]
    assert "vinculos" in montada.corpo["blocos"]
    assert "eventos" not in montada.corpo["blocos"]
    assert "events" not in {n["bloco"] for n in montada.corpo["nao_encontrado"]}
    assert montada.consumo[("eventos", A)] == (0, True)
    assert acabou.wait(10), "a consulta do bloco atrasado não foi interrompida"
    assert depois_do_prazo == [
        False
    ]  # o portão fechou para o bloco que passou do prazo


def test_erro_de_um_bloco_que_respondeu_sobe(porta, blocos):
    def quebra(*_):
        raise RuntimeError("bloco quebrou")

    blocos(_bloco("vinculos", quebra))
    with pytest.raises(RuntimeError, match="bloco quebrou"):
        _montar(porta, conjuntos=("profiles", "vinculos"))


def test_cada_bloco_le_no_proprio_cursor_e_o_fecha(porta, blocos):
    cursores = []

    def anota(porta_do_bloco, *_):
        cursores.append(porta_do_bloco)
        assert porta_do_bloco.con is not porta.con
        assert porta_do_bloco.banco is None
        return _Servido({"vinculos": [{}]})

    blocos(_bloco("vinculos", anota))
    _montar(porta, conjuntos=("profiles", "vinculos"))
    with pytest.raises(duckdb.Error):
        cursores[0].con.execute("SELECT 1")
    assert porta.con.execute("SELECT 1").fetchone() == (
        1,
    )  # a porta do pedido segue aberta


def test_contexto_do_pedido_vai_para_os_blocos(porta, blocos):
    pedido = contextvars.ContextVar("pedido", default=None)
    vistos = []

    def le_o_contexto(*_):
        vistos.append(pedido.get())
        return _Servido({"vinculos": [{}]})

    blocos(_bloco("vinculos", le_o_contexto), _bloco("eventos", le_o_contexto))
    pedido.set("este pedido")
    _montar(porta, conjuntos=("profiles", "vinculos", "eventos"))
    assert vistos == ["este pedido", "este pedido"]


def test_portao_de_cada_bloco_e_o_do_conjunto_e_da_finalidade_dele(porta, blocos):
    pedidos = []

    def portao(conjunto, finalidade):
        pedidos.append((conjunto, finalidade))
        return lambda *_: True

    blocos(_bloco("credito", lambda *_: _Servido({}), "credit", C))
    _montar(porta, liberadas=_liberadas("credit", finalidade=C), portao=portao)
    assert sorted(pedidos) == [("credit", C), ("profiles", A)]


# --- frase, linha do tempo e leituras -----------------------------------------------------------------


def test_frase_so_usa_o_que_o_cadastro_serviu_e_e_fato(porta, blocos):
    blocos()
    frase = _montar(porta).corpo["frase"]  # type: ignore[union-attr]
    assert (
        frase["texto"]
        == "ALFA S.A.; situação ativa na Receita; início da atividade em 2010-05-01."
    )
    assert frase["tipo"] == analise.FATO
    assert "municipality" not in str(frase["a_partir_de"])


def test_linha_do_tempo_em_ordem_e_sem_data_depois_do_dia(porta, blocos):
    socios = {
        socios_pj.SOCIAS: [
            {
                "raiz_do_cnpj": "12000004",
                "razao_social": _envelope("HOLDING LTDA"),
                "data_entrada": _envelope("2015-03-01"),
            }
        ],
        socios_pj.PARTICIPACOES: [],
    }
    blocos(_bloco("socios_pj", lambda *_: _Servido(socios), socios_pj.CONJUNTO))
    corpo = _montar(porta, conjuntos=("profiles", socios_pj.CONJUNTO)).corpo  # type: ignore[union-attr]
    dias = [marco["dia"] for marco in corpo["linha_do_tempo"]]
    assert dias == ["2010-05-01", "2015-03-01"]
    assert all(dia <= DIA.isoformat() for dia in dias)
    # o nome do bloco já sai com o nome de fora: quem integra procura o bloco pela chave dele
    assert corpo["linha_do_tempo"][1]["bloco"] == "corporate_ownership"
    assert corpo["linha_do_tempo"][1]["fonte"] == "rfb-cnpj"


def test_leituras_sao_deducao_e_dizem_de_que_bloco_vem(porta, blocos):
    blocos()
    leituras = _montar(porta).corpo["leituras"]  # type: ignore[union-attr]
    assert leituras
    assert all(leitura["tipo"] == analise.DEDUCAO for leitura in leituras)
    assert all(leitura["a_partir_de"] == ["profile"] for leitura in leituras)
    assert "15 anos" in leituras[0]["texto"]


def test_limites_juntam_os_da_analise_e_os_dos_blocos_sem_repetir(porta, blocos):
    blocos(
        _bloco(
            "vinculos",
            lambda *_: _Servido(
                {"vinculos": [{}], "limites": ["limite do cadastro", "outro"]}
            ),
        )
    )
    corpo = _montar(porta, conjuntos=("profiles", "vinculos")).corpo  # type: ignore[union-attr]
    assert corpo["limites"][: len(analise.LIMITES)] == list(analise.LIMITES)
    assert corpo["limites"].count("limite do cadastro") == 1
    assert "outro" in corpo["limites"]
    assert "limites" not in corpo["blocos"]["vinculos"]


def test_ainda_nao_traz_e_o_mesmo_para_toda_chave(porta, blocos):
    blocos()
    assert _montar(porta).corpo["ainda_nao_traz"] == list(analise.AINDA_NAO_TRAZ)  # type: ignore[union-attr]
