"""O texto do pregão do dia: só frases do molde, com os números do resumo."""

import copy
import json
import re

import pytest

from src import texto_do_pregao as texto

FONTE_ACOES = "B3, COTAHIST"

RESUMO_DE_QUEDA: dict = {
    "pregao": "2026-10-26",
    "vespera": "2026-10-23",
    "ibovespa": {
        "pontos": 112_345.67,
        "variacao": -0.13879,
        "pregoes_comparados": 6_650,
        "pregoes_tao_extremos": 2,
        "ultima_vez": "2020-03-16",
        "desde": "2000-01-04",
        "fonte": "B3, estatísticas do índice",
        "data": "2026-10-26",
    },
    "amplitude": {
        "subiram": 8,
        "cairam": 110,
        "estaveis": 2,
        "liquidez_minima": 20_000_000,
        "fonte": FONTE_ACOES,
        "data": "2026-10-26",
    },
    "setores": {
        "lista": [
            {
                "setor": "Saneamento",
                "empresas": 5,
                "mediana": -0.051,
                "contra_o_indice": 0.08779,
            },
            {
                "setor": "Bancos",
                "empresas": 9,
                "mediana": -0.12,
                "contra_o_indice": 0.01879,
            },
            {
                "setor": "Varejo",
                "empresas": 11,
                "mediana": -0.41,
                "contra_o_indice": -0.27121,
            },
        ],
        "empresas_por_setor_minimo": 3,
        "fonte": "CVM, cadastro",
        "data": "2026-10-26",
    },
    "maiores": {
        "altas": [
            {
                "simbolo": "SBSP3",
                "empresa": "Sabesp",
                "setor": "Saneamento",
                "variacao": 0.031,
                "fechamento": 120.5,
            }
        ],
        "quedas": [
            {
                "simbolo": "MGLU3",
                "empresa": "Magazine Luiza",
                "setor": "Varejo",
                "variacao": -0.582,
                "fechamento": 4.18,
            },
            {
                "simbolo": "VAMO3",
                "empresa": "Vamos",
                "setor": "Logística",
                "variacao": -0.568,
                "fechamento": 2.1,
            },
        ],
        "fonte": FONTE_ACOES,
        "data": "2026-10-26",
    },
    "juros": {
        "simbolo": "DI1F29",
        "taxa": 16.26,
        "taxa_vespera": 14.85,
        "variacao_em_pontos_base": 140.5,
        "fonte": "B3, boletim de negociação",
        "data": "2026-10-26",
    },
    "dolar": {
        "simbolo": "DOLX26",
        "reais_por_dolar": 6.1234,
        "variacao": 0.0921,
        "fonte": "B3, boletim de negociação",
        "data": "2026-10-26",
    },
    "a_conferir": [
        {
            "simbolo": "DESD3",
            "empresa": "Desdobra",
            "setor": "Bancos",
            "variacao": -0.5,
            "fechamento": 50.0,
        }
    ],
}


def _de_alta() -> dict:
    resumo = copy.deepcopy(RESUMO_DE_QUEDA)
    resumo["ibovespa"].update(
        variacao=0.021, pregoes_tao_extremos=180, ultima_vez="2026-08-12"
    )
    resumo["maiores"]["quedas"] = []
    resumo["juros"]["variacao_em_pontos_base"] = -12.0
    resumo["dolar"]["variacao"] = -0.0104
    resumo["a_conferir"] = []
    return resumo


def _de_lado() -> dict:
    resumo = copy.deepcopy(RESUMO_DE_QUEDA)
    resumo["ibovespa"].update(variacao=-0.0021)
    resumo["juros"]["variacao_em_pontos_base"] = 0.0
    resumo["dolar"]["variacao"] = 0.00004
    resumo["setores"]["lista"] = resumo["setores"]["lista"][:1]
    resumo["a_conferir"] = []
    return resumo


@pytest.fixture(scope="module")
def molde() -> dict:
    return texto.ler_molde()


def _modelo_em_regex(modelo: str) -> re.Pattern[str]:
    partes = re.split(r"\{[a-z_]+\}", modelo)
    return re.compile(".+?".join(re.escape(parte) for parte in partes))


def _todos_os_modelos(molde: dict) -> list[str]:
    return [modelo for grupo in molde["frases"].values() for modelo in grupo.values()]


# --- o molde ---------------------------------------------------------------------------------------


def _textos_do_molde(molde: dict) -> list[str]:
    return [*_todos_os_modelos(molde), *molde["limites"]]


def test_molde_sem_palavras_proibidas(molde: dict) -> None:
    """Nenhuma frase recomenda, promete, explica a causa ou fala de política."""
    for frase in _textos_do_molde(molde):
        assert not texto.palavras_proibidas(frase), frase


@pytest.mark.parametrize(
    "frase",
    [
        "Bom momento para comprar.",
        "A ação deve subir amanhã.",
        "Caiu por causa da eleição.",
        "O PT e o PL disputam o segundo turno.",
        "O mercado reagiu ao governo.",
        "Ficou barata.",
        "Recomendamos cautela.",
    ],
)
def test_palavras_proibidas_pegam(frase: str) -> None:
    assert texto.palavras_proibidas(frase)


def test_aviso_de_recomendacao_nao_e_palavra_proibida() -> None:
    assert not texto.palavras_proibidas("Nada aqui é recomendação de investimento.")


def test_impressao_digital_do_molde_muda_com_qualquer_letra(molde: dict) -> None:
    trocado = copy.deepcopy(molde)
    trocado["frases"]["abertura"]["alta"] = trocado["frases"]["abertura"][
        "alta"
    ].replace("subiu", "Subiu")
    assert texto.impressao_digital(molde) != texto.impressao_digital(trocado)
    assert texto.impressao_digital(molde) == texto.impressao_digital(
        copy.deepcopy(molde)
    )
    assert re.fullmatch(r"[0-9a-f]{64}", texto.impressao_digital(molde))


# --- o texto pelo molde ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "resumo",
    [RESUMO_DE_QUEDA, _de_alta(), _de_lado()],
    ids=["queda", "alta", "de_lado"],
)
def test_texto_so_tem_frases_do_molde(resumo: dict, molde: dict) -> None:
    modelos = [_modelo_em_regex(m) for m in _todos_os_modelos(molde)]
    pronto = texto.texto_do_pregao(resumo, molde)
    for frase in pronto["frases"]:
        assert any(m.fullmatch(frase["texto"]) for m in modelos), frase
        assert frase["texto"] == molde["frases"][frase["grupo"]][
            frase["variante"]
        ].format_map(frase["lacunas"])
    escritos = [f["texto"] for f in pronto["frases"]] + pronto["limites"]
    assert not [
        t for t in escritos if "{" in t or "}" in t
    ]  # nenhuma lacuna sem preencher


def _frase(pronto: dict, grupo: str) -> str:
    return next(f["texto"] for f in pronto["frases"] if f["grupo"] == grupo)


def _grupos(pronto: dict) -> list[str]:
    return [f["grupo"] for f in pronto["frases"]]


def test_texto_numero_igual_ao_dos_dados(molde: dict) -> None:
    """Cada número do texto é o do resumo, com a vírgula, o sinal de menos e o separador de milhar."""
    pronto = texto.texto_do_pregao(RESUMO_DE_QUEDA, molde)
    # "caiu" já diz o sentido: o número vai sem sinal ("caiu −13,9%" diria a queda duas vezes)
    assert (
        _frase(pronto, "abertura")
        == "O Ibovespa caiu 13,9% em 26/10/2026, para 112.346 pontos."
    )
    assert _frase(pronto, "historia") == (
        "Desde 04/01/2000, 2 dos 6.650 pregões caíram tanto ou mais; o último foi em 16/03/2020."
    )
    assert _frase(pronto, "amplitude") == (
        "Das 120 empresas com R$ 20 milhões ou mais negociados na véspera: 8 em alta, 110 em queda "
        "e 2 sem variação."
    )
    setores = [f["texto"] for f in pronto["frases"] if f["grupo"] == "setores"]
    assert setores == [
        (
            "Na ponta de cima dos setores, Saneamento: mediana de −5,1% em 5 empresas (+8,8 "
            "pontos percentuais em relação ao Ibovespa)."
        ),
        (
            "Na ponta de baixo, Varejo: mediana de −41,0% em 11 empresas (−27,1 pontos "
            "percentuais em relação ao Ibovespa)."
        ),
    ]
    maiores = [f["texto"] for f in pronto["frases"] if f["grupo"] == "maiores"]
    assert maiores == [
        "Maior alta: Sabesp (SBSP3), +3,1%.",
        "Maior queda: Magazine Luiza (MGLU3), −58,2%.",
    ]
    assert _frase(pronto, "juros") == (
        "A taxa do DI de janeiro de 2029 (DI1F29) subiu 140,5 pontos-base, para 16,26% ao ano."
    )
    assert (
        _frase(pronto, "dolar") == "O dólar futuro (DOLX26) subiu 9,2%, para R$ 6,1234."
    )
    assert _frase(pronto, "a_conferir") == (
        "Ficaram fora das contas, por desdobramento ou grupamento no dia: DESD3."
    )


def test_dia_de_alta(molde: dict) -> None:
    pronto = texto.texto_do_pregao(_de_alta(), molde)
    assert _frase(pronto, "abertura").startswith("O Ibovespa subiu 2,1% em 26/10/2026")
    assert "180 dos 6.650 pregões subiram tanto ou mais" in _frase(pronto, "historia")
    assert "Nenhuma dessas empresas caiu." in [f["texto"] for f in pronto["frases"]]
    assert _frase(pronto, "juros").endswith("caiu 12 pontos-base, para 16,26% ao ano.")
    assert (
        _frase(pronto, "dolar") == "O dólar futuro (DOLX26) caiu 1,0%, para R$ 6,1234."
    )
    assert "a_conferir" not in _grupos(pronto)


def test_historia_so_em_dia_raro(molde: dict) -> None:
    """Em 27/10/2026 o Ibovespa caiu 0,5%: 2.186 dos 6.647 pregões caíram tanto ou mais. Dizer isso é
    verdade, mas não informa nada; a frase da história só sai quando poucos pregões foram tão longe."""
    resumo = copy.deepcopy(RESUMO_DE_QUEDA)
    resumo["ibovespa"].update(
        variacao=-0.0051, pregoes_comparados=6_647, pregoes_tao_extremos=2_186
    )
    assert "historia" not in _grupos(texto.texto_do_pregao(resumo, molde))
    no_limite = round(6_647 * texto.FRACAO_DE_DIA_RARO)
    resumo["ibovespa"]["pregoes_tao_extremos"] = no_limite
    assert "historia" in _grupos(texto.texto_do_pregao(resumo, molde))


def test_dia_de_lado(molde: dict) -> None:
    """Dia de lado não ganha frase de história (metade dos pregões varia mais que isso), e juros e
    dólar que não mudam na casa mostrada ficam "como na véspera"."""
    pronto = texto.texto_do_pregao(_de_lado(), molde)
    assert _frase(pronto, "abertura") == (
        "O Ibovespa variou pouco em 26/10/2026: −0,2%, para 112.346 pontos."
    )
    assert "historia" not in _grupos(pronto)
    assert _frase(pronto, "juros").endswith("ficou em 16,26% ao ano, como na véspera.")
    assert (
        _frase(pronto, "dolar")
        == "O dólar futuro (DOLX26) ficou em R$ 6,1234, como na véspera."
    )
    # com um setor só, não há ponta de cima e de baixo
    assert "setores" not in _grupos(pronto)


@pytest.mark.parametrize(
    ("tao_extremos", "ultima_vez", "esperado"),
    [
        (0, None, "Nenhum dos 6.650 pregões desde 04/01/2000 caiu tanto."),
        (
            1,
            "2020-03-16",
            "Desde 04/01/2000, só 1 dos 6.650 pregões caiu tanto ou mais, em 16/03/2020.",
        ),
    ],
)
def test_historia_no_singular_e_sem_precedente(
    tao_extremos: int, ultima_vez: str | None, esperado: str, molde: dict
) -> None:
    resumo = copy.deepcopy(RESUMO_DE_QUEDA)
    resumo["ibovespa"].update(pregoes_tao_extremos=tao_extremos, ultima_vez=ultima_vez)
    assert _frase(texto.texto_do_pregao(resumo, molde), "historia") == esperado


def test_limites_preenchidos_e_aviso_no_fim(molde: dict) -> None:
    pronto = texto.texto_do_pregao(RESUMO_DE_QUEDA, molde)
    assert (
        "Só entram as empresas com R$ 20 milhões ou mais negociados na véspera"
        in pronto["limites"][3]
    )
    assert "menos de 3 empresas" in pronto["limites"][4]
    assert pronto["limites"][-1] == "Nada aqui é recomendação de investimento."


def test_impressao_digital_e_fontes_no_texto(molde: dict) -> None:
    pronto = texto.texto_do_pregao(RESUMO_DE_QUEDA, molde)
    assert pronto["impressao_digital"] == texto.impressao_digital(molde)
    assert pronto["fontes"] == [
        "B3, estatísticas do índice",
        FONTE_ACOES,
        "CVM, cadastro",
        "B3, boletim de negociação",
    ]
    assert pronto["pregao"] == "2026-10-26"


def test_texto_recusa_molde_com_palavra_proibida(molde: dict) -> None:
    trocado = copy.deepcopy(molde)
    trocado["frases"]["abertura"]["queda"] = (
        "O Ibovespa caiu {variacao} por causa do governo."
    )
    with pytest.raises(ValueError, match="proibida"):
        texto.texto_do_pregao(RESUMO_DE_QUEDA, trocado)


def test_texto_volta_e_vai_como_json(molde: dict) -> None:
    pronto = texto.texto_do_pregao(RESUMO_DE_QUEDA, molde)
    assert json.loads(json.dumps(pronto, ensure_ascii=False)) == pronto


# --- as tabelas, o gráfico e o JSON do site ---------------------------------------------------------


def test_tabelas_com_os_titulos_do_molde_e_os_numeros_escritos(molde: dict) -> None:
    pronto = texto.texto_do_pregao(RESUMO_DE_QUEDA, molde)
    tabelas = {t["chave"]: t for t in pronto["tabelas"]}
    assert list(tabelas) == ["setores", "altas", "quedas"]
    for chave, tabela in tabelas.items():
        assert tabela["titulo"] == molde["tabelas"][chave]["titulo"]
        assert tabela["colunas"] == molde["tabelas"][chave]["colunas"]
        assert all(len(linha) == len(tabela["colunas"]) for linha in tabela["linhas"])
    assert tabelas["setores"]["linhas"][0] == ["Saneamento", "5", "−5,1%", "+8,8"]
    assert tabelas["quedas"]["linhas"][1] == [
        "Vamos",
        "VAMO3",
        "Logística",
        "−56,8%",
        "2,10",
    ]
    assert tabelas["altas"]["linhas"] == [
        ["Sabesp", "SBSP3", "Saneamento", "+3,1%", "120,50"]
    ]


def test_grafico_dos_setores_em_pontos_percentuais(molde: dict) -> None:
    grafico = texto.texto_do_pregao(RESUMO_DE_QUEDA, molde)["grafico"]
    assert grafico["titulo"] == molde["grafico_dos_setores"]
    assert grafico["barras"] == [
        {"nome": "Saneamento", "valor": pytest.approx(8.779), "texto": "+8,8"},
        {"nome": "Bancos", "valor": pytest.approx(1.879), "texto": "+1,9"},
        {"nome": "Varejo", "valor": pytest.approx(-27.121), "texto": "−27,1"},
    ]


def test_tabelas_e_grafico_tambem_passam_pela_trava(molde: dict) -> None:
    trocado = copy.deepcopy(molde)
    trocado["tabelas"]["altas"]["titulo"] = "Ações para comprar"
    with pytest.raises(ValueError, match="proibida"):
        texto.conferir_molde(trocado)
    trocado = copy.deepcopy(molde)
    trocado["grafico_dos_setores"] = "Setores que devem subir"
    with pytest.raises(ValueError, match="proibida"):
        texto.conferir_molde(trocado)


def test_molde_do_arquivo_e_o_aprovado(molde: dict) -> None:
    """Mudar uma letra do molde exige trocar a impressão aprovada no mesmo PR: é texto público novo,
    que só entra com o "pode" do Tiago."""
    assert texto.impressao_digital(molde) == texto.IMPRESSAO_DO_MOLDE_APROVADO


def test_para_o_site_le_o_ultimo_pregao_guardado(tmp_path, molde: dict) -> None:
    for dia in ("2026-10-26", "2026-10-27"):
        resumo = copy.deepcopy(RESUMO_DE_QUEDA) | {"pregao": dia}
        (tmp_path / f"{dia}.json").write_text(json.dumps(resumo), encoding="utf-8")
    (tmp_path / "LEIA.md").write_text("não é pregão", encoding="utf-8")
    site = texto.para_o_site(pasta=tmp_path)
    assert site["molde_aprovado"] == texto.IMPRESSAO_DO_MOLDE_APROVADO
    assert site["pregao"]["pregao"] == "2026-10-27"
    assert site["pregao"]["impressao_digital"] == texto.impressao_digital(molde)


def test_pregao_guardado_no_repositorio_monta_o_texto() -> None:
    """O pregão que o site mostra (conteudo/pregao/) passa pelo molde sem erro e sem lacuna."""
    site = texto.para_o_site()
    assert site["pregao"]["frases"]
    assert site["pregao"]["impressao_digital"] == site["molde_aprovado"]
