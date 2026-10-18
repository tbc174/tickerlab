"""A prova da CPFL (Tarefa 10): os textos que Haiku, Sonnet e Opus escreveram, guardados como vieram.

Cada resposta bruta está em `resposta_<modelo>.json` e a porta 2 às cegas (Sonnet conferindo) em
`cega_<modelo>.json`. Os testes não chamam a API: leem o que foi pago uma vez e prendem o que a
prova mostrou. As reprovações da porta 1 listadas aqui são erros reais de citação (a data está na
ficha, mas numa nota que a frase não citou); se a porta mudar e uma delas sumir, o teste avisa.
"""

import json

import pytest

from src.analise_escrita import avaliacao, montagem, pedido, porta1, saida
from tests.ajudantes_da_analise import PAR_DA_CPFL

# os dois escritores que passam nos critérios 2 a 5; o Sonnet erra uma conta nossa
CANDIDATOS = ("haiku", "opus")
# as partes que voltam ao molde: a da porta 1 e as da porta 2
MOLDE_NA_MONTAGEM = {
    "haiku": {"limites", "quem_manda", "o_que_mudaria"},
    "opus": {"o_que_os_numeros_mostram", "o_que_e", "o_que_mudaria"},
}
# (parte, regra, data escrita sem a nota que a sustenta)
REPROVACOES_DA_PORTA1 = {
    "haiku": [
        ("limites", porta1.DATA, "30/06/2026"),
        ("limites", porta1.DATA, "31/03/2026"),
    ],
    "opus": [("o_que_os_numeros_mostram", porta1.DATA, "2024; 2025")],
}


def _ler(nome: str) -> dict:
    return json.loads((PAR_DA_CPFL / nome).read_text(encoding="utf-8"))


def _entrada() -> dict:
    return _ler("entrada.json")


def _texto(modelo: str) -> saida.Analise:
    registro = _ler(f"resposta_{modelo}.json")
    return saida.ler_analise(
        pedido.ler_resposta(registro["stop_reason"], registro["resposta_bruta"])
    )


def _gabarito() -> saida.Analise:
    return saida.ler_analise(_ler("gabarito.json")["analise"])


def _montagem(modelo: str) -> montagem.Montagem:
    registro = _ler(f"resposta_{modelo}.json")
    return montagem.da_resposta_bruta(
        registro["stop_reason"],
        registro["resposta_bruta"],
        _entrada(),
        registro["hash_da_entrada"],
        _ler(f"cega_{modelo}.json")["reprovadas"],
    )


@pytest.mark.parametrize("modelo", ("haiku", "sonnet", "opus"))
def test_respostas_sao_da_entrada_guardada(modelo):
    """Se a entrada for refeita, as respostas ficam velhas e a montagem vira molde inteira."""
    registro = _ler(f"resposta_{modelo}.json")
    assert registro["hash_da_entrada"] == _ler("resposta_opus.json")["hash_da_entrada"]
    assert registro["stop_reason"] == "end_turn"


@pytest.mark.parametrize("modelo", CANDIDATOS)
def test_texto_da_cpfl_passa_na_porta1(modelo):
    """A análise que iria para a tela: o que o modelo acertou mais o molde, sem nenhuma reprovação."""
    montada = _montagem(modelo)
    assert montada.motivo is None
    assert porta1.conferir(montada.analise, _entrada()).reprovacoes == ()
    do_molde = {p.chave for p in montada.analise.partes if p.origem == "molde"}
    assert do_molde == MOLDE_NA_MONTAGEM[modelo]


@pytest.mark.parametrize("modelo", CANDIDATOS)
def test_reprovacoes_da_porta1_sao_as_conhecidas(modelo):
    reprovacoes = porta1.conferir(_texto(modelo), _entrada()).reprovacoes
    achadas = [
        (r.parte, r.regra, r.detalhe.rsplit("[", 1)[1].rstrip("]")) for r in reprovacoes
    ]
    assert achadas == REPROVACOES_DA_PORTA1[modelo]


@pytest.mark.parametrize("modelo", CANDIDATOS)
def test_texto_da_cpfl_contra_o_gabarito(modelo):
    """Critérios 2 a 5 passam; o 1 só cai pelas datas sem a nota (as reprovações acima)."""
    criterios = avaliacao.avaliar(_texto(modelo), _entrada(), _gabarito())
    assert [c.numero for c in criterios if not c.passou] == [1]
    (primeiro,) = (c for c in criterios if c.numero == 1)
    assert all(f" {porta1.DATA}: " in falha for falha in primeiro.falhas)


def test_porta1_pega_a_conta_errada_do_sonnet():
    """O Sonnet declarou a dívida líquida em milhares e escreveu bilhões: a porta 1 refaz a conta."""
    reprovacoes = porta1.conferir(_texto("sonnet"), _entrada()).reprovacoes
    assert ("o_que_mudou", porta1.CONTA) in {(r.parte, r.regra) for r in reprovacoes}


@pytest.mark.parametrize("modelo", CANDIDATOS)
def test_porta2_conferiu_todas_as_frases(modelo):
    cega = _ler(f"cega_{modelo}.json")
    total = sum(
        len(p.frases) for parte in _texto(modelo).partes for p in parte.paragrafos
    )
    assert len(cega["frases"]) == total
    assert cega["conferente"] == pedido.SONNET
