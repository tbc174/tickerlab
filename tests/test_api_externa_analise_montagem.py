"""A montagem da análise completa do CNPJ (`conjuntos/analise.py`), com blocos de mentira.

O que é da rota (chave, contratos, portão de verdade, consumo) está em `test_api_externa_analise.py`; aqui fica
o que é da montagem: qual bloco abre pelo que o portão libera, o prazo (o bloco lento é interrompido e o resto
sai), o portão que fecha quando o prazo acaba, o contexto do pedido nos blocos, a linha do tempo sem o futuro, a
frase só com o que o cadastro serviu e as leituras marcadas como dedução.
"""

import contextvars
import threading
import time
from concurrent.futures import wait
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
        # as tabelas do registro ligadas pelo CNPJ (linha 978, lote 1)
        "financials",
        "funds",
        # CGU, IBAMA e MTE, só com o conjunto de integridade no contrato (ADR 0122, Emenda 1)
        "integrity",
        # Anatel, ANM, ANP e o PAT do MTE, só com o conjunto no contrato (ADR 0122, Emenda 2)
        "extended_sources",
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


def test_bloco_que_acaba_depois_do_fim_do_prazo_sai_como_atrasado_e_nao_como_sem_dado(
    porta, blocos, monkeypatch
):
    """Revisão cruzada: o bloco que pergunta ao portão já fechado e devolve nada não é "não encontrado"."""

    def espera_o_fim(_porta, permitido, *_):
        limite = time.monotonic() + 5
        while permitido("rfb-cnpj", "campo", False) and time.monotonic() < limite:
            time.sleep(0.01)
        # o portão fechou: o leitor de verdade não traria dado (devolve None)

    original = analise._terminou

    def termina_antes_de_olhar(tarefa):
        wait(
            [tarefa.futuro], timeout=5
        )  # o bloco acaba entre o fim do prazo e a conferência
        return original(tarefa)

    monkeypatch.setattr(analise, "_terminou", termina_antes_de_olhar)
    blocos(_bloco("eventos", espera_o_fim))
    corpo = _montar(porta, conjuntos=("profiles", "eventos"), prazo=0.2).corpo  # type: ignore[union-attr]
    assert [n["bloco"] for n in corpo["nao_respondeu_a_tempo"]] == ["events"]
    assert "events" not in {n["bloco"] for n in corpo["nao_encontrado"]}


def test_erro_de_um_bloco_nao_deixa_o_atrasado_sem_interromper(porta, blocos):
    acabou = threading.Event()

    def quebra(*_):
        raise RuntimeError("bloco quebrou")

    def lento(porta_do_bloco, *_):
        try:
            porta_do_bloco.con.execute(
                "SELECT count(*) FROM range(100000000000) a"
            ).fetchall()
        finally:
            acabou.set()

    blocos(_bloco("vinculos", quebra), _bloco("eventos", lento))
    with pytest.raises(RuntimeError, match="bloco quebrou"):
        _montar(porta, conjuntos=("profiles", "vinculos", "eventos"), prazo=0.5)
    assert acabou.wait(10), "a consulta do bloco atrasado não foi interrompida"


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


def test_linha_do_tempo_dos_eventos_tem_a_troca_de_auditor_e_o_fato_relevante_so(
    porta, blocos
):
    def documento(categoria: str, dia: str) -> dict:
        return {"categoria": _envelope(categoria), "referencia": _envelope(dia)}

    servido = {
        "eventos": [
            {
                "tipo_de_evento": analise.eventos.TROCA_DE_AUDITOR,
                "novo": _envelope("AUDITORA B"),
                "efetiva_em": _envelope("2021-01-01"),
            },
            documento(analise.FATO_RELEVANTE, "2022-03-10"),
            documento(
                "Comunicado ao Mercado", "2022-04-10"
            ),  # comunicado não vira marco
            documento(analise.FATO_RELEVANTE, "2025-07-15"),  # depois do dia: fora
        ]
    }
    blocos(_bloco("eventos", lambda *_: _Servido(servido)))
    corpo = _montar(porta, conjuntos=("profiles", "eventos")).corpo  # type: ignore[union-attr]
    dos_eventos = [m for m in corpo["linha_do_tempo"] if m["bloco"] == "events"]
    assert [(m["dia"], m["o_que"]) for m in dos_eventos] == [
        ("2021-01-01", "Troca de auditor para AUDITORA B"),
        ("2022-03-10", "Fato relevante (CVM)"),
    ]


def test_perfil_com_muitas_entregas_leva_as_mais_novas_e_diz_que_cortou(monkeypatch):
    entregas = [{"n": n} for n in range(analise.LINHAS_POR_BLOCO + 3)]
    inteiro = _Servido({"entregas": entregas}, linhas=len(entregas) + 1)

    class _Ficha:
        def __init__(self, *_):
            pass

        def ficha(self, *_):
            return inteiro

    monkeypatch.setattr(analise.ficha, "LeitorDeFicha", _Ficha)
    servido = analise._perfil(None, None, 0, CNPJ, DIA)  # type: ignore[arg-type]
    assert servido is not None
    assert servido.corpo["entregas"] == entregas[: analise.LINHAS_POR_BLOCO]
    assert servido.corpo["cortada"] is True
    assert servido.linhas == analise.LINHAS_POR_BLOCO + 1


# --- tempo por bloco (frente 1 de 24/11/2026: o ensaio de 19/11 viu blocos em `timed_out`) ---------------


def _tempos(montada) -> dict:
    return {t.bloco: t for t in montada.tempos}


def _linhas_do_log(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == analise.__name__]


def test_cada_bloco_tem_o_tempo_e_o_estado_dele(porta, blocos):
    def lento(porta_do_bloco, *_):
        porta_do_bloco.con.execute(
            "SELECT count(*) FROM range(100000000000) a"
        ).fetchall()

    def demora(*_):
        time.sleep(0.15)
        return _Servido({"vinculos": [{}]})

    blocos(_bloco("vinculos", demora), _bloco("eventos", lento))
    montada = _montar(porta, conjuntos=("profiles", "vinculos", "eventos"), prazo=0.6)
    tempos = _tempos(montada)
    assert set(tempos) == {
        "profile",
        "links",
        "events",
    }  # nomes de fora, como no `timed_out`
    assert tempos["profile"].estado == analise.RESPONDEU
    assert tempos["links"].estado == analise.RESPONDEU
    assert tempos["links"].duracao_ms >= 100  # o relógio do Windows anda de ~15 ms
    assert tempos["events"].estado == analise.ATRASADO
    assert tempos["events"].duracao_ms is None  # não acabou dentro do prazo
    assert all(t.comecou_ms is not None and t.comecou_ms >= 0 for t in tempos.values())


def test_bloco_que_quebra_sai_com_estado_de_erro_no_log(porta, blocos, caplog):
    def quebra(*_):
        raise RuntimeError("bloco quebrou")

    blocos(_bloco("vinculos", quebra))
    caplog.set_level("INFO", logger=analise.__name__)
    with pytest.raises(RuntimeError):
        _montar(porta, conjuntos=("profiles", "vinculos"))
    assert any(
        "bloco=links" in linha and f"estado={analise.ERRO}" in linha
        for linha in _linhas_do_log(caplog)
    )


def test_o_tempo_no_portao_e_a_fila_da_trava_sao_contados_por_bloco(porta, blocos):
    """A trava do portão atende um bloco de cada vez: o que espera por ela aparece na fila do portão."""
    juntos = threading.Barrier(2)

    def pergunta_junto(_porta, permitido, *_):
        juntos.wait(timeout=5)
        permitido("rfb-cnpj", "campo", False)
        return _Servido({"vinculos": [{}]})

    def portao_lento(_conjunto, _finalidade):
        def permitido(*_):
            time.sleep(0.2)
            return True

        return permitido

    blocos(_bloco("vinculos", pergunta_junto), _bloco("eventos", pergunta_junto))
    montada = _montar(
        porta, conjuntos=("profiles", "vinculos", "eventos"), portao=portao_lento
    )
    tempos = _tempos(montada)
    assert tempos["links"].portao_ms >= 150
    assert tempos["events"].portao_ms >= 150
    # um dos dois esperou o outro sair do portão
    assert max(tempos["links"].fila_ms, tempos["events"].fila_ms) >= 100


def test_o_log_tem_uma_linha_por_bloco_e_o_total_so_com_ids(porta, blocos, caplog):
    blocos(_bloco("vinculos", lambda *_: _Servido({"vinculos": [{}]})))
    caplog.set_level("INFO", logger=analise.__name__)
    _montar(porta, conjuntos=("profiles", "vinculos"))
    linhas = _linhas_do_log(caplog)
    por_bloco = [linha for linha in linhas if "bloco=" in linha]
    assert sorted(linha.split("bloco=")[1].split()[0] for linha in por_bloco) == [
        "links",
        "profile",
    ]
    assert any("total_ms=" in linha and "atrasados=0" in linha for linha in linhas)
    # um pedido, um id: as linhas de pedidos ao mesmo tempo se separam por ele
    assert len({linha.split("pedido=")[1].split()[0] for linha in linhas}) == 1
    # só ids e tempos: nem o CNPJ nem o que o bloco leu
    assert not any(CNPJ in linha or "ALFA" in linha for linha in linhas)


def test_sem_cadastro_aberto_nao_ha_tempo_nem_log(porta, blocos, caplog):
    blocos()
    caplog.set_level("INFO", logger=analise.__name__)
    assert _montar(porta, conjuntos=()) is None
    assert _linhas_do_log(caplog) == []
