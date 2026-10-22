"""Memorando de M&A (B-26), PR 1: as evidências e a conferência antes da tela.

Frase sem fonte derruba; evidência incompleta ou de depois da data derruba; preço-alvo, "vale X" e
"recomendamos comprar/vender" derrubam; a porta 1 da análise escrita confere números e nomes.
"""

import json
from datetime import date

import pytest

from src.analise_escrita import porta1
from src.analise_escrita.saida import Conta, Frase, Operando
from src.memorando_ma import conferencia as co
from src.memorando_ma import evidencia as ev
from src.memorando_ma.formato import Memorando, SecaoDoMemorando
from src.rastro import Rastro
from src.relatorio_empresa import Item

DIA = date(2025, 6, 30)
RASTRO = Rastro(
    "mediana dos múltiplos", "comps por transação 1", "cvm-ipe", date(2025, 3, 10)
)
MEDIANA = ev.do_rastro(
    "comps.ev_ebitda.mediana",
    "Mediana do EV/EBITDA pago nos precedentes do setor: 8,10 vezes",
    8.1,
    RASTRO,
)
PRECEDENTES = ev.do_rastro(
    "comps.ev_ebitda.precedentes",
    "Precedentes do setor com EV/EBITDA",
    5.0,
    RASTRO,
)
AUDITOR = ev.Evidencia(
    "perfil.auditor_atual",
    ev.TRECHO,
    "Auditor atual: KPMG Auditores Independentes",
    date(2025, 5, 31),
    documento="FRE entregue à CVM",
)
SEM_INSOLVENCIA = ev.lacuna(
    "red_flags.desligado",
    "Dívida com a União e atrasos de pagamento: esperam um parecer jurídico.",
)
EVIDENCIAS = (MEDIANA, PRECEDENTES, AUDITOR, SEM_INSOLVENCIA)


def _memorando(
    *secoes: SecaoDoMemorando, evidencias=EVIDENCIAS, limites=()
) -> Memorando:
    return Memorando(
        "00.000.000/0001-00", "Alvo S.A.", DIA, secoes, evidencias, limites
    )


def _so(frase: Frase, chave: str = "comps_por_transacao", **outros) -> Memorando:
    return _memorando(SecaoDoMemorando(chave, (frase,)), **outros)


def _regras(memorando: Memorando) -> set[str]:
    return {r.regra for r in co.conferir(memorando).reprovacoes}


BOA = Frase(
    "A mediana do EV/EBITDA pago em 5 precedentes do setor foi de 8,10 vezes.",
    (MEDIANA.id, PRECEDENTES.id),
)


def test_memorando_com_fonte_em_cada_frase_passa():
    memorando = _memorando(
        SecaoDoMemorando("perfil", (Frase("O auditor atual é a KPMG Auditores Independentes.", (AUDITOR.id,)),)),
        SecaoDoMemorando("comps_por_transacao", (BOA,)),
        SecaoDoMemorando("red_flags", (Frase(SEM_INSOLVENCIA.afirmacao, (SEM_INSOLVENCIA.id,)),)),
        limites=("É uma régua do que foi pago, não um preço nem uma recomendação.",),
    )  # fmt: skip
    assert co.conferir(memorando).aprovada
    assert co.para_mostrar(memorando) is memorando


def test_frase_sem_fonte_derruba():
    assert co.SEM_FONTE in _regras(_so(Frase("O setor é concentrado.")))


def test_frase_sem_fonte_nao_vai_para_a_tela():
    with pytest.raises(co.MemorandoReprovadoError, match=co.SEM_FONTE):
        co.para_mostrar(_so(Frase("O setor é concentrado.")))


def test_nota_que_nao_e_evidencia_derruba():
    assert porta1.ID_INEXISTENTE in _regras(_so(Frase("Texto.", ("comps.inventado",))))


def test_numero_que_nao_esta_na_evidencia_citada_derruba():
    frase = Frase("A mediana foi de 9,30 vezes.", (MEDIANA.id,))
    assert porta1.NUMERO in _regras(_so(frase))


def test_conta_declarada_e_refeita():
    dobro = Conta(
        "produto", (Operando(MEDIANA.id, 8.1), Operando(PRECEDENTES.id, 5.0)), 40.5
    )
    certa = Frase("O produto dá 40,5.", (MEDIANA.id, PRECEDENTES.id), (dobro,))
    assert co.conferir(_so(certa)).aprovada
    errada = Conta("produto", dobro.de, 50.0)
    assert porta1.CONTA in _regras(
        _so(Frase("O produto dá 50.", certa.notas, (errada,)))
    )


@pytest.mark.parametrize(
    "evidencia",
    [
        ev.Evidencia("x", ev.NUMERO, "Um número", DIA, valor=None, rastro=RASTRO),
        ev.Evidencia("x", ev.NUMERO, "Um número: 3", DIA, valor=3.0, rastro=None),
        ev.Evidencia(
            "x", ev.NUMERO, "Um número: 3", DIA, 3.0, rastro=Rastro("", "v", "cvm", DIA)
        ),
        ev.Evidencia("x", ev.TRECHO, "Um fato", DIA, documento=""),
        ev.Evidencia("x", ev.TRECHO, "Um fato", None, documento="FRE"),
        ev.Evidencia("x", ev.LACUNA, "", None),
    ],
)
def test_evidencia_incompleta_derruba(evidencia):
    assert evidencia.o_que_falta()
    memorando = _so(Frase("Um fato.", ("x",)), evidencias=(evidencia,))
    assert co.EVIDENCIA_INCOMPLETA in _regras(memorando)


def test_evidencia_publicada_depois_da_data_derruba():
    depois = ev.do_rastro(
        "comps.depois", "Mediana: 8,10 vezes", 8.1,
        Rastro("f", "v", "cvm-ipe", date(2025, 7, 1)),
    )  # fmt: skip
    frase = Frase("A mediana foi de 8,10 vezes.", (depois.id,))
    assert co.EVIDENCIA_FUTURA in _regras(_so(frase, evidencias=(depois,)))


@pytest.mark.parametrize(
    "texto",
    [
        "Recomendamos comprar a companhia pela mediana de 8,10 vezes.",
        "O preço-alvo sai da mediana de 8,10 vezes.",
        "Pela mediana de 8,10 vezes, a empresa vale R$ 4,5 bilhões.",
        "Com a mediana de 8,10 vezes, a companhia valeria mais.",
        "O valor justo sai da mediana de 8,10 vezes.",
        "Com a mediana de 8,10 vezes, o comprador deveria comprar.",
        "Pela mediana de 8,10 vezes, sugerimos vender.",
        "A mediana de 8,10 vezes mostra uma oportunidade.",
    ],
)
def test_preco_alvo_vale_x_e_recomendacao_derrubam(texto):
    regras = _regras(_so(Frase(texto, (MEDIANA.id,))))
    assert regras & {co.VALOR_DA_EMPRESA, porta1.PALAVRA}


def test_negar_a_recomendacao_passa():
    frase = Frase(
        "Nada aqui é recomendação: a mediana de 8,10 vezes é o que foi pago.",
        (MEDIANA.id,),
    )
    assert co.conferir(_so(frase)).aprovada


def test_previsao_derruba():
    frase = Frase("A mediana de 8,10 vezes deve subir.", (MEDIANA.id,))
    assert porta1.PREVISAO in _regras(_so(frase))


def test_nome_fora_das_evidencias_derruba():
    frase = Frase("A mediana foi de 8,10 vezes, como na Eletrobras.", (MEDIANA.id,))
    assert porta1.NOME in _regras(_so(frase))


@pytest.mark.parametrize(
    ("chaves", "detalhe"),
    [
        (("comps_por_transacao", "perfil"), "seção fora de ordem"),
        (("perfil", "perfil"), "seção repetida"),
        (("conclusao",), "seção desconhecida"),
    ],
)
def test_estrutura_reprova(chaves, detalhe):
    frase = Frase("O auditor atual é a KPMG Auditores Independentes.", (AUDITOR.id,))
    memorando = _memorando(*(SecaoDoMemorando(c, (frase,)) for c in chaves))
    detalhes = {r.detalhe for r in co.conferir(memorando).reprovacoes}
    assert detalhe in detalhes


def test_secao_vazia_reprova():
    memorando = _memorando(SecaoDoMemorando("lbo", ()))
    assert porta1.ESTRUTURA in _regras(memorando)


def test_limite_que_recomenda_reprova_e_o_que_nega_passa():
    assert porta1.PALAVRA in _regras(_so(BOA, limites=("Recomendamos a compra.",)))
    assert co.conferir(_so(BOA, limites=("Nada aqui é recomendação.",))).aprovada


def test_item_com_rastro_e_valor_vira_numero():
    rastro = Rastro("contagem das controladas", "dossiê 1", "cvm", date(2025, 5, 31))
    item = Item(
        "controladas",
        "Controladas",
        "12",
        12.0,
        "sociedades",
        "FRE de 2025",
        rastro=rastro,
    )
    evidencia = ev.do_item("perfil", item)
    assert evidencia is not None
    assert (evidencia.id, evidencia.tipo, evidencia.valor) == (
        "perfil.controladas",
        ev.NUMERO,
        12.0,
    )
    assert evidencia.publicado_em == date(2025, 5, 31)
    assert not evidencia.o_que_falta()


def test_item_do_cadastro_vira_trecho_com_o_dia_da_base():
    item = Item(
        "setor", "Setor", "Energia Elétrica", None, "texto", "cadastro da CVM em 20/06/2025",
        fonte="cadastro de companhias abertas da CVM",
    )  # fmt: skip
    evidencia = ev.do_item("perfil", item)
    assert evidencia is not None
    assert evidencia.tipo == ev.TRECHO
    assert evidencia.publicado_em == date(2025, 6, 20)
    assert evidencia.afirmacao == "Setor: Energia Elétrica"


def test_item_sem_fonte_nem_rastro_nao_vira_evidencia():
    item = Item("x", "X", "algo", None, "texto", "sem dia")
    assert ev.do_item("perfil", item) is None


def test_como_dict_vira_json():
    memorando = _so(BOA)
    dado = json.loads(json.dumps(memorando.como_dict(), ensure_ascii=False))
    assert dado["secoes"][0]["frases"][0]["notas"] == list(BOA.notas)
    assert dado["evidencias"][0]["rastro"]["publicado_em"] == "2025-03-10"
    assert (
        "[comps.ev_ebitda.mediana, comps.ev_ebitda.precedentes]"
        in memorando.como_texto()
    )
