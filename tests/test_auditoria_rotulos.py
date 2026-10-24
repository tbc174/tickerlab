"""A auditoria dos rótulos da IA contra os do Tiago (ADR 0072), sem rede.

Os valores de referência do kappa foram conferidos com `sklearn.metrics.cohen_kappa_score` (14/10/2026);
o critério de aprovação é o da ADR, escrito antes de existir qualquer rótulo da IA.
"""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from src import auditoria_rotulos as ar


def test_kappa_exemplo_conhecido():
    assert ar.kappa([1, 1, 2, 2], [1, 2, 2, 2]) == pytest.approx(0.5)


@pytest.mark.parametrize(
    ("a", "b", "esperado"),
    [
        ([1, 2, 3, 4, 5, 3], [1, 2, 3, 4, 4, 5], 0.7619047619),
        ([1, 1, 1, 2, 3], [1, 2, 1, 3, 3], 0.75),
    ],
)
def test_kappa_ponderado_exemplo_conhecido(a, b, esperado):
    assert ar.kappa_ponderado(a, b) == pytest.approx(esperado)


@given(st.lists(st.integers(1, 5), min_size=2).filter(lambda xs: len(set(xs)) > 1))
def test_kappa_um_quando_iguais(notas):
    assert ar.kappa_ponderado(notas, notas) == pytest.approx(1.0)
    assert ar.kappa(notas, notas) == pytest.approx(1.0)


def test_kappa_sem_variacao_nao_divide_por_zero():
    assert ar.kappa([3, 3], [3, 3]) == 1.0
    assert ar.kappa([3, 3], [3, 4]) == 0.0


def test_diferenca_ate_um():
    assert ar.perto([1, 2, 5, 3], [2, 2, 3, 3]) == pytest.approx(0.75)


def test_acerto_do_assunto_ignora_nulos():
    assert ar.acerto(["A", None, "B", "C"], ["A", "X", "C", "C"]) == pytest.approx(
        2 / 3
    )
    assert ar.acerto([None], ["A"]) is None


# --- identificação da empresa --------------------------------------------------------------


def test_identificou_pela_palavra_que_distingue():
    nome = "VIVER INCORPORADORA E CONSTRUTORA S.A"
    assert ar.identificou("Viver", nome)
    assert ar.identificou("Acho que é a Viver Incorporadora", nome)
    assert not ar.identificou("NAO_SEI", nome)
    assert not ar.identificou(
        "Uma incorporadora de São Paulo", nome
    )  # palavra genérica não conta


def test_identificou_sem_acento():
    assert ar.identificou("Sao Martinho", "SÃO MARTINHO S.A.")


# --- o veredito ---------------------------------------------------------------------------


def _humanos_e_ia(n=300, erra_nota_a_cada=0, erra_tema_a_cada=0):
    humanos, ia = {}, {}
    for i in range(n):
        nota = i % 5 + 1
        tema = ("resultado", "dividendos", "governanca")[i % 3]
        humanos[f"e{i}"] = {
            "evento_id": f"e{i}",
            "nota": nota,
            "tema": tema,
            "assunto": None,
        }
        nota_ia = (
            (nota % 5) + 1 if erra_nota_a_cada and i % erra_nota_a_cada == 0 else nota
        )
        tema_ia = "operacao" if erra_tema_a_cada and i % erra_tema_a_cada == 0 else tema
        ia[f"e{i}"] = {
            "evento_id": f"e{i}",
            "nota": nota_ia,
            "tema": tema_ia,
            "assunto": None,
            "por": "ia",
        }
    return humanos, ia


def test_veredito_passa_com_concordancia_alta():
    humanos, ia = _humanos_e_ia(erra_nota_a_cada=10)
    veredito = ar.auditar(humanos, ia, identificadas=dict.fromkeys(humanos, False))
    assert veredito.passou and veredito.n == 300 and not veredito.motivos


def test_veredito_usa_os_limites_da_adr_0072():
    assert ar.LIMITES == {
        "kappa_nota": 0.60,
        "perto_nota": 0.90,
        "kappa_tema": 0.70,
        "acerto_assunto": 0.80,
        "max_identificadas": 0.10,
        "min_eventos": 300,
    }
    humanos, ia = _humanos_e_ia(erra_tema_a_cada=2)
    veredito = ar.auditar(humanos, ia, identificadas={})
    assert not veredito.passou and any("tema" in m for m in veredito.motivos)


def test_poucos_rotulos_humanos_nao_decide():
    humanos, ia = _humanos_e_ia(n=120)
    veredito = ar.auditar(humanos, ia, identificadas={})
    assert not veredito.passou and veredito.incompleto


def test_pulados_nao_contam():
    humanos, ia = _humanos_e_ia(n=301)
    humanos["e0"] |= {"pulado": True, "nota": None}
    assert ar.auditar(humanos, ia, identificadas={}).n == 300


def test_falta_rotulo_da_ia_para_um_evento_de_prova():
    humanos, ia = _humanos_e_ia()
    ia["e5"] = {"evento_id": "e5", "erro": "trecho não está no documento"}
    with pytest.raises(ValueError, match="e5"):
        ar.auditar(humanos, ia, identificadas={})


def test_vazamento_reprova():
    humanos, ia = _humanos_e_ia()
    identificadas = {f"e{i}": i < 40 for i in range(300)}  # 13% reconhecidas
    veredito = ar.auditar(humanos, ia, identificadas=identificadas)
    assert not veredito.passou and any("empresa" in m for m in veredito.motivos)
    assert veredito.identificadas == pytest.approx(40 / 300)


def test_sem_teste_de_identificacao_nao_passa():
    humanos, ia = _humanos_e_ia()
    veredito = ar.auditar(humanos, ia, identificadas=None)
    assert not veredito.passou and veredito.incompleto


# --- Sonnet × Opus (Emenda 1, 17/10/2026) ------------------------------------------------------


def _rotulo(nota=3, tema="resultado", assunto=None):
    return {"nota": nota, "tema": tema, "assunto": assunto}


def _fila(n_primeiros=300, n_lote=4):
    """Os eventos como o script lê: `ordem` é a posição na fila; o lote do leitor vem no fim."""
    primeiros = [
        {"id": f"A{i}", "ordem": i, "amostra": None} for i in range(n_primeiros + 5)
    ]
    lote = [{"id": f"L{i}", "ordem": n_primeiros + 5 + i, "amostra": ar.LOTE_DO_LEITOR}
            for i in range(n_lote)]  # fmt: skip
    return primeiros + lote


def test_conjunto_de_prova_sao_os_300_primeiros_e_o_lote_do_leitor():
    primeiros, lote = ar.conjunto_de_prova(_fila())
    assert primeiros == [f"A{i}" for i in range(300)]
    assert lote == ["L0", "L1", "L2", "L3"]


def _variados(ids):
    """Notas e temas que variam (com tudo igual, o kappa não diz nada)."""
    temas = ("resultado", "dividendos", "divida", "governanca")
    return {i: _rotulo(1 + k % 5, temas[k % 4]) for k, i in enumerate(ids)}


def test_modelos_que_concordam_passam():
    ids = [f"A{i}" for i in range(300)]
    veredito = ar.comparar_modelos(_variados(ids), _variados(ids), ids)
    assert veredito.passou and veredito.n == 300
    assert veredito.kappa_nota == pytest.approx(1.0)
    assert (
        veredito.identificadas is None
    )  # a identificação é do Sonnet, não da comparação


def test_comparacao_com_menos_de_300_fica_incompleta():
    ids = [f"A{i}" for i in range(299)]
    veredito = ar.comparar_modelos(_variados(ids), _variados(ids), ids)
    assert veredito.incompleto and not veredito.passou


def test_rotulo_faltando_ou_com_erro_deixa_incompleta():
    ids = [f"A{i}" for i in range(300)]
    opus = _variados(ids)
    del opus["A0"]
    opus["A1"] = {"erro": "trecho não está no documento"}
    veredito = ar.comparar_modelos(_variados(ids), opus, ids)
    assert veredito.incompleto and not veredito.passou
    assert any("2" in m and "sem rótulo" in m for m in veredito.motivos)


def test_notas_distantes_reprovam_pela_nota():
    ids = [f"A{i}" for i in range(300)]
    sonnet = _variados(ids)
    opus = {
        i: {**r, "nota": 6 - r["nota"]} for i, r in sonnet.items()
    }  # nota invertida
    veredito = ar.comparar_modelos(sonnet, opus, ids)
    assert not veredito.passou and not veredito.incompleto
    assert any("kappa da nota" in m for m in veredito.motivos)
    assert veredito.kappa_tema == pytest.approx(1.0)


def test_assunto_conta_so_nos_fatos_relevantes():
    ids = [f"A{i}" for i in range(300)]
    sonnet = _variados(ids)
    opus = _variados(ids)
    for k in range(10):  # 10 fatos relevantes; os dois discordam em 3 (70% < 80%)
        sonnet[f"A{k}"]["assunto"] = "DIVIDENDOS"
        opus[f"A{k}"]["assunto"] = "DIVIDENDOS" if k >= 3 else "OUTROS"
    veredito = ar.comparar_modelos(sonnet, opus, ids)
    assert veredito.n_assunto == 10 and veredito.acerto_assunto == pytest.approx(0.7)
    assert any("assunto" in m for m in veredito.motivos)


def test_referencia_do_leitor_sao_os_eventos_em_que_os_dois_concordam_no_assunto():
    sonnet = {
        "L0": _rotulo(4, "fusao", "FUSAO_INCORPORACAO"),
        "L1": _rotulo(3, "divida", "OUTROS"),
        "L2": _rotulo(2, "governanca", "OUTROS"),
        "L3": _rotulo(3, "resultado", "OUTROS"),
    }
    opus = {
        "L0": _rotulo(4, "fusao", "FUSAO_INCORPORACAO"),
        "L1": _rotulo(5, "divida", "OUTROS"),  # mesma coisa, nota diferente
        "L2": _rotulo(
            2, "governanca", "FECHAMENTO_CAPITAL"
        ),  # assunto diferente: fica de fora
        "L3": {"erro": "parada: max_tokens"},  # sem rótulo do Opus: fica de fora
    }
    referencia = ar.referencia_do_leitor(sonnet, opus, ["L0", "L1", "L2", "L3"])
    assert referencia == [
        {
            "evento_id": "L0",
            "assunto": "FUSAO_INCORPORACAO",
            "nota": 4,
            "tema": "fusao",
        },
        {"evento_id": "L1", "assunto": "OUTROS", "nota": None, "tema": "divida"},
    ]


# --- Emenda 1: identificação sem o Tiago e estabilidade -----------------------------------------


def test_identificacao_reprova_acima_de_10_por_cento_dos_eventos_de_prova():
    ids = [f"E{i}" for i in range(20)]
    passa = ar.veredito_da_identificacao({i: i in ("E0", "E1") for i in ids}, ids)
    assert passa.passou and passa.identificadas == pytest.approx(0.10)
    reprova = ar.veredito_da_identificacao(
        {i: i in ("E0", "E1", "E2") for i in ids}, ids
    )
    assert not reprova.passou and "15%" in reprova.motivos[0]


def test_identificacao_sem_todos_os_eventos_fica_incompleta():
    ids = ["E0", "E1", "E2"]
    veredito = ar.veredito_da_identificacao({"E0": False}, ids)
    assert veredito.incompleto and not veredito.passou and veredito.n == 3


def _rotulos(n, erro=()):
    return {f"E{i}": ({"erro": "x"} if i in erro else {"nota": 1 + i % 5, "tema": "divida"})
            for i in range(n)}  # fmt: skip


def test_sorteio_da_estabilidade_e_fixo_e_so_de_rotulos_validos():
    eventos = [{"id": f"E{i}"} for i in range(400)]
    rotulos = _rotulos(400, erro=range(0, 400, 7))
    sorteio = ar.sorteio_da_estabilidade(eventos, rotulos)
    assert len(sorteio) == len(set(sorteio)) == ar.EVENTOS_DA_ESTABILIDADE == 100
    assert all(ar.valido(rotulos, i) for i in sorteio)
    assert sorteio == ar.sorteio_da_estabilidade(eventos, rotulos)  # a semente fixa
    assert sorteio == ar.sorteio_da_estabilidade(list(reversed(eventos)), rotulos)


def test_sorteio_com_menos_de_100_validos_leva_todos():
    eventos = [{"id": f"E{i}"} for i in range(5)]
    assert sorted(ar.sorteio_da_estabilidade(eventos, _rotulos(5, erro=(2,)))) == [
        "E0",
        "E1",
        "E3",
        "E4",
    ]


def test_estabilidade_mede_a_concordancia_ia_x_ia_sem_limite():
    primeira = {
        "A": {"nota": 3, "tema": "divida", "assunto": None},
        "B": {"nota": 2, "tema": "resultado", "assunto": "OUTROS"},
        "C": {"nota": 5, "tema": "fusao", "assunto": "FUSAO_INCORPORACAO"},
        "D": {"nota": 1, "tema": "governanca", "assunto": None},
    }
    segunda = {
        "A": {"nota": 3, "tema": "divida", "assunto": None},
        "B": {"nota": 4, "tema": "resultado", "assunto": "OUTROS"},
        "C": {"nota": 5, "tema": "operacao", "assunto": "FECHAMENTO_CAPITAL"},
        "D": {"erro": "trecho não está no documento"},
    }
    medida = ar.estabilidade(primeira, segunda, ["A", "B", "C", "D"])
    assert medida["sorteados"] == 4 and medida["pares"] == 3 and medida["erros"] == 1
    assert medida["nota_igual"] == pytest.approx(2 / 3)
    assert medida["perto_nota"] == pytest.approx(2 / 3)
    assert medida["tema_igual"] == pytest.approx(2 / 3)
    assert medida["assunto_igual"] == pytest.approx(1 / 2) and medida["n_assunto"] == 2
    assert "kappa_nota" in medida and "kappa_tema" in medida
    assert "passou" not in medida  # a emenda só pede publicar


# --- segunda tentativa da rotina (Emenda 4 da ADR 0072) ---------------------------------------


def _com_assunto(ids):
    """Fatos relevantes com nota, tema e assunto que variam."""
    assuntos = ("OUTROS", "AQUISICAO", "DIVIDA")
    return {
        i: r | {"assunto": assuntos[k % 3]}
        for k, (i, r) in enumerate(_variados(ids).items())
    }


def test_conjunto_da_segunda_tentativa_sao_os_fatos_fora_dos_300():
    eventos = _fila()
    api = _variados([e["id"] for e in eventos])
    for i in ("A5", "A301", "A303", "L1"):
        api[i]["assunto"] = "OUTROS"
    api["A303"] = {"erro": "x"}  # sem rótulo válido da API: não entra
    assert ar.conjunto_da_segunda_tentativa(eventos, api) == ["A301", "L1"]


def test_segunda_tentativa_passa_com_ate_5_por_cento_faltando():
    ids = [f"F{i}" for i in range(100)]
    rotina = _com_assunto(ids)
    for i in ids[:5]:
        rotina[i] = {"erro": "trecho não está no documento"}
    veredito, faltantes = ar.comparar_segunda_tentativa(_com_assunto(ids), rotina, ids)
    assert veredito.passou and veredito.n == 100 and veredito.n_assunto == 95
    assert faltantes == ids[:5]


def test_segunda_tentativa_reprova_com_mais_de_5_por_cento_faltando():
    ids = [f"F{i}" for i in range(100)]
    rotina = {i: r for i, r in _com_assunto(ids).items() if i not in ids[:6]}
    veredito, faltantes = ar.comparar_segunda_tentativa(_com_assunto(ids), rotina, ids)
    assert not veredito.passou and len(faltantes) == 6
    assert any("6 de 100" in m for m in veredito.motivos)


def test_segunda_tentativa_reprova_no_assunto_abaixo_de_80_por_cento():
    ids = [f"F{i}" for i in range(100)]
    api, rotina = _com_assunto(ids), _com_assunto(ids)
    for i in ids[:21]:
        rotina[i] = rotina[i] | {"assunto": "REORG"}
    veredito, _ = ar.comparar_segunda_tentativa(api, rotina, ids)
    assert veredito.acerto_assunto == pytest.approx(0.79) and not veredito.passou


def test_segunda_tentativa_sem_conjunto_nao_passa():
    veredito, faltantes = ar.comparar_segunda_tentativa({}, {}, [])
    assert not veredito.passou and faltantes == []
