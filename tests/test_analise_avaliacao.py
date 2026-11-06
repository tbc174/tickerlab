"""Os 5 critérios do gabarito (o que a avaliação do texto do modelo pede) e o relatório lado a lado."""

import copy
import json

from src.analise_escrita import avaliacao, saida
from tests.ajudantes_da_analise import PAR_DA_CPFL

ENTRADA = json.loads((PAR_DA_CPFL / "entrada.json").read_text(encoding="utf-8"))
RESPOSTA = json.loads((PAR_DA_CPFL / "gabarito.json").read_text(encoding="utf-8"))[
    "analise"
]
GABARITO = saida.ler_analise(RESPOSTA)
MARCADA = "De 2023 a 09/09/2026, foram 32 ofertas"


def _avaliar(resposta: dict) -> dict[int, avaliacao.Criterio]:
    criterios = avaliacao.avaliar(saida.ler_analise(resposta), ENTRADA, GABARITO)
    return {c.numero: c for c in criterios}


def _parte(resposta: dict, chave: str) -> dict:
    (parte,) = [p for p in resposta["partes"] if p["chave"] == chave]
    return parte


def _frases(resposta: dict):
    for parte in resposta["partes"]:
        for paragrafo in parte["paragrafos"]:
            yield from paragrafo["frases"]


def test_gabarito_passa_nos_5_criterios():
    criterios = _avaliar(RESPOSTA)
    assert sorted(criterios) == [1, 2, 3, 4, 5]
    assert {n: c.falhas for n, c in criterios.items() if not c.passou} == {}


def test_numero_errado_reprova_o_1():
    resposta = copy.deepcopy(RESPOSTA)
    for frase in _frases(resposta):
        frase["texto"] = frase["texto"].replace("94 ofertas", "95 ofertas")
    criterios = _avaliar(resposta)
    assert not criterios[1].passou
    assert any("dinheiro" in falha for falha in criterios[1].falhas)


def test_texto_que_cala_a_lacuna_reprova_o_2():
    resposta = copy.deepcopy(RESPOSTA)
    obrigatorias = set(ENTRADA["obrigatorias"])
    for frase in _frases(resposta):
        frase["notas"] = [n for n in frase["notas"] if n not in obrigatorias]
    assert not _avaliar(resposta)[2].passou


def test_conta_nossa_sem_a_conta_declarada_reprova_o_3_e_nao_o_1():
    """A frase diz que o número é conta nossa, mas não dá a conta: a porta 1 não tem o que refazer."""
    resposta = copy.deepcopy(RESPOSTA)
    (frase,) = [f for f in _frases(resposta) if f["texto"].startswith(MARCADA)]
    frase["contas"] = []
    criterios = _avaliar(resposta)
    assert criterios[1].passou
    assert not criterios[3].passou
    assert all(falha.startswith("dinheiro.1.") for falha in criterios[3].falhas)
    assert any("não declara a conta" in falha for falha in criterios[3].falhas)


def test_conta_errada_reprova_o_3():
    resposta = copy.deepcopy(RESPOSTA)
    (frase,) = [f for f in _frases(resposta) if f["texto"].startswith(MARCADA)]
    frase["contas"][-1]["resultado"] *= 2
    assert not _avaliar(resposta)[3].passou


def test_previsao_reprova_o_4():
    resposta = copy.deepcopy(RESPOSTA)
    frase = _parte(resposta, "o_que_mudaria")["paragrafos"][0]["frases"][0]
    frase["texto"] += " A dívida vai subir."
    assert not _avaliar(resposta)[4].passou


def test_parte_sem_leitura_reprova_o_5():
    resposta = copy.deepcopy(RESPOSTA)
    parte = _parte(resposta, "dinheiro")
    parte["paragrafos"] = [p for p in parte["paragrafos"] if p["tipo"] == saida.FATO]
    criterio = _avaliar(resposta)[5]
    assert not criterio.passou
    assert "dinheiro: sem leitura" in criterio.falhas


def test_parte_curta_reprova_o_5():
    """Menos de 60% das palavras da parte no gabarito: é a tabela repetida em frase, não análise."""
    resposta = copy.deepcopy(RESPOSTA)
    parte = _parte(resposta, "o_que_e")
    for paragrafo in parte["paragrafos"]:
        paragrafo["frases"] = paragrafo["frases"][:1]
    criterio = _avaliar(resposta)[5]
    assert not criterio.passou
    (falha,) = criterio.falhas
    assert falha.startswith("o_que_e: ") and "palavras" in falha


def test_relatorio_lado_a_lado_mostra_as_partes_e_os_criterios():
    resposta = copy.deepcopy(RESPOSTA)
    (frase,) = [f for f in _frases(resposta) if f["texto"].startswith(MARCADA)]
    frase["texto"] += " | sem marca"
    frase["contas"] = []
    texto = saida.ler_analise(resposta)
    criterios = avaliacao.avaliar(texto, ENTRADA, GABARITO)
    relatorio = avaliacao.relatorio(
        {"Modelo": texto, "Gabarito": GABARITO}, {"Modelo": criterios}
    )
    for titulo in (saida.TITULOS[c] for c in saida.PARTES):
        assert f"## {titulo}" in relatorio
    assert "| Modelo | Gabarito |" in relatorio
    assert "\\| sem marca" in relatorio  # a barra do texto não quebra a tabela
    assert "3. contas nossas marcadas | reprovou" in relatorio
    assert "*Leitura:*" in relatorio
