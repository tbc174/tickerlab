"""Porta 1 (ADR 0093): todo número, data e nome da análise conferido por código contra a entrada.

Cada regra tem a frase que ela pega; a régua aprovada (o gabarito da CPFL) passa sem nenhuma
reprovação (`test_analise_par_da_cpfl.py`).
"""

import pytest

from src.analise_escrita import porta1, saida

ENTRADA = {
    "empresa": "CPFL ENERGIA S.A.",
    "setor": "Emp. Adm. Part. - Energia Elétrica",
    "corte": "2026-10-17",
    "secoes": {"retorno": "Retorno"},
    "fontes": ["CVM: dados abertos (ODbL)"],
    "linhas": [
        {
            "id": "retorno.roe",
            "tipo": "numero",
            "texto": "26,4%",
            "valor": 0.26433,
            "medido_em": "12 meses até 30/06/2026",
            "comparacao": {"contra": "setor", "texto": "mediana 11,8%", "valor": None},
        },
        {
            "id": "endividamento.divida_liquida",
            "tipo": "numero",
            "texto": "R$ 27,6 bi",
            "valor": 27563883000.0,
            "medido_em": "balanço de 30/06/2026",
            "comparacao": {
                "contra": "balanço de 31/03/2026",
                "texto": "era R$ 26,0 bi",
                "valor": 25962216000.0,
            },
        },
        {
            "id": "endividamento.ponte.1",
            "tipo": "linha",
            "tabela": "Ponte",
            "celulas": {"passo": "Caixa operacional", "valor": -7162797000.0},
        },
        {
            "id": "resultado.lucro",
            "tipo": "numero",
            "texto": "-R$ 1,2 bi",
            "valor": -1.2e9,
            "medido_em": "DFP de 2025",
        },
        {
            "id": "negocios.negocios.0",
            "tipo": "linha",
            "tabela": "Negócios",
            "celulas": {
                "Data": "02/02/2026",
                "Assunto": "Aquisição da CEEE-T pela CPFL Cone Sul",
            },
        },
        {
            "id": "ficha_tecnica.controlador",
            "tipo": "numero",
            "texto": "—",
            "motivo": "A ficha não traz a controladora.",
        },
        {"id": "lacuna.segmentos", "tipo": "lacuna", "texto": "A base não separa."},
        {
            "id": "ofertas.por_ano.0",
            "tipo": "linha",
            "tabela": "Ofertas por ano",
            "celulas": {"Ano": "2023", "Ofertas": "4"},
        },
        {
            "id": "ofertas.por_ano.1",
            "tipo": "linha",
            "tabela": "Ofertas por ano",
            "celulas": {"Ano": "2017", "Ofertas": "2"},
        },
    ],
    "obrigatorias": ["ficha_tecnica.controlador", "lacuna.segmentos"],
}
FRASE_NEUTRA = saida.Frase("A empresa entrega as contas à CVM.")


def _analise(
    frase: saida.Frase, parte: str = "o_que_os_numeros_mostram", tipo: str = "fato"
):
    """As 8 partes com uma frase neutra cada, e a frase em teste na parte pedida."""
    partes = []
    for chave in saida.PARTES:
        paragrafos = [saida.Paragrafo("fato", (FRASE_NEUTRA,))]
        if chave == "limites":
            notas = ("ficha_tecnica.controlador", "lacuna.segmentos")
            paragrafos.append(
                saida.Paragrafo(
                    "fato", (saida.Frase("A base não tem o controlador.", notas),)
                )
            )
        if chave == parte:
            paragrafos.append(saida.Paragrafo(tipo, (frase,)))
        partes.append(saida.Parte(chave, tuple(paragrafos)))
    return saida.Analise(tuple(partes))


def _regras(frase: saida.Frase, **kw) -> list[str]:
    return [
        r.regra for r in porta1.conferir(_analise(frase, **kw), ENTRADA).reprovacoes
    ]


def _conta(operacao, *de, resultado):
    return saida.Conta(operacao, tuple(de), resultado)


def _de(id_=None, valor=None, conta=None):
    return saida.Operando(id_, valor, conta)


def test_analise_limpa_passa():
    conferencia = porta1.conferir(_analise(FRASE_NEUTRA), ENTRADA)
    assert conferencia.reprovacoes == ()
    assert conferencia.partes_reprovadas == frozenset()


def test_numero_com_nota_passa_e_arredondado_errado_reprova():
    assert _regras(saida.Frase("O ROE é 26,4%, contra 11,8%.", ("retorno.roe",))) == []
    assert _regras(saida.Frase("O ROE é 26,5%.", ("retorno.roe",))) == ["numero"]
    assert _regras(saida.Frase("O ROE é 26,4%.")) == ["numero"]  # sem nota


def test_nota_que_nao_existe():
    assert "id_inexistente" in _regras(saida.Frase("O ROE é alto.", ("retorno.roa",)))


def test_sinal_so_e_ignorado_em_saida_de_dinheiro():
    caixa = saida.Frase("A operação gerou R$ 7,2 bilhões.", ("endividamento.ponte.1",))
    assert _regras(caixa) == []
    lucro = saida.Frase("O lucro foi de R$ 1,2 bilhão.", ("resultado.lucro",))
    assert _regras(lucro) == ["numero"]  # prejuízo escrito como lucro


def test_conta_declarada_e_refeita():
    de = (
        _de("endividamento.divida_liquida", 25962216000.0),
        _de("endividamento.divida_liquida", 27563883000.0),
    )
    certa = _conta("variacao", *de, resultado=0.0617)
    frase = saida.Frase(
        "A dívida líquida subiu 6,2%.", ("endividamento.divida_liquida",), (certa,)
    )
    assert _regras(frase) == []
    errada = _conta("variacao", *de, resultado=0.09)
    frase = saida.Frase(
        "A dívida líquida subiu 9%.", ("endividamento.divida_liquida",), (errada,)
    )
    assert _regras(frase) == ["conta"]


def test_operando_tem_de_estar_na_linha():
    conta = _conta(
        "diferenca",
        _de("retorno.roe", 0.30),
        _de("retorno.roe", 0.118),
        resultado=0.182,
    )
    frase = saida.Frase("A diferença é de 18,2 pontos.", ("retorno.roe",), (conta,))
    assert "conta" in _regras(frase)


def test_constante_so_o_100_e_conta_encadeada():
    cem = _conta(
        "produto", _de("retorno.roe", 0.26433), _de(valor=100.0), resultado=26.433
    )
    assert (
        _regras(saida.Frase("De cada R$ 100, R$ 26 voltam.", ("retorno.roe",), (cem,)))
        == []
    )
    mil = _conta(
        "produto", _de("retorno.roe", 0.26433), _de(valor=1000.0), resultado=264.33
    )
    assert "conta" in _regras(
        saida.Frase("De cada R$ 1.000, R$ 264.", ("retorno.roe",), (mil,))
    )
    dobro = _conta("produto", _de(conta=0), _de(valor=100.0), resultado=2643.3)
    frase = saida.Frase("Dá 2.643.", ("retorno.roe",), (cem, dobro))
    assert _regras(frase) == []


def test_contagem_de_linhas_citadas():
    ids = ("retorno.roe", "resultado.lucro")
    duas = _conta("contagem", *(_de(i) for i in ids), resultado=2.0)
    assert _regras(saida.Frase("São 2 números.", ids, (duas,))) == []
    tres = _conta("contagem", *(_de(i) for i in ids), resultado=3.0)
    assert _regras(saida.Frase("São 3 números.", ids, (tres,))) == ["conta"]
    fora = _conta("contagem", _de("retorno.roa"), resultado=1.0)
    assert "conta" in _regras(saida.Frase("É 1 número.", (), (fora,)))


def test_leitura_usa_o_numero_do_fato_logo_acima():
    fato = saida.Paragrafo("fato", (saida.Frase("O ROE é 26,4%.", ("retorno.roe",)),))
    leitura = saida.Paragrafo("leitura", (saida.Frase("Os 26,4% vêm da dívida."),))
    analise = _analise(FRASE_NEUTRA)
    partes = list(analise.partes)
    i = saida.PARTES.index("o_que_os_numeros_mostram")
    partes[i] = saida.Parte(partes[i].chave, (*partes[i].paragrafos, fato, leitura))
    assert porta1.conferir(saida.Analise(tuple(partes)), ENTRADA).reprovacoes == ()
    sozinha = saida.Frase("Os 26,4% vêm da dívida.")
    assert _regras(sozinha, tipo="leitura") == ["numero"]


def test_data_conferida_e_data_depois_do_corte():
    ok = saida.Frase("Em 30/06/2026, o ROE era 26,4%.", ("retorno.roe",))
    assert _regras(ok) == []
    assert _regras(
        saida.Frase("Em 30/09/2026, o ROE era 26,4%.", ("retorno.roe",))
    ) == ["data"]
    futuro = _regras(saida.Frase("Em 2027, o ROE cai.", ("retorno.roe",)))
    assert "data_futura" in futuro


def test_ano_solto_vale_no_ano_do_corte_ou_entre_os_anos_das_notas():
    assert _regras(saida.Frase("Desde 2026 a dívida cresce.")) == []
    assert _regras(saida.Frase("Desde 2025 a dívida cresce.")) == ["data"]
    por_ano = ("ofertas.por_ano.0", "ofertas.por_ano.1")
    lacuna = saida.Frase("Nenhuma oferta entre 2018 e 2022.", por_ano)
    assert _regras(lacuna) == []
    assert _regras(saida.Frase("Nenhuma oferta em 2015.", por_ano)) == ["data"]
    lucro = saida.Frase("O lucro de 2024 foi -R$ 1,2 bilhão.", ("resultado.lucro",))
    assert _regras(lucro) == ["data"]


def test_nome_que_nao_esta_na_entrada():
    assert (
        _regras(
            saida.Frase(
                "A compra da CEEE-T pela CPFL Cone Sul.", ("negocios.negocios.0",)
            )
        )
        == []
    )
    assert _regras(saida.Frase("A compra foi feita pela Eletrobras.")) == ["nome"]
    assert _regras(saida.Frase("O CADE e a ANEEL aprovaram; a PwC audita.")) == []


@pytest.mark.parametrize(
    "texto",
    [
        "O CFO Fulano Beltrano assinou o balanço.",
        "Fulano Beltrano, Diretor-Presidente, assinou.",
        "O CPF 123.456.789-09 aparece no documento.",
    ],
)
def test_pessoa(texto):
    assert "pessoa" in _regras(saida.Frase(texto))


@pytest.mark.parametrize(
    "texto",
    [
        "É uma oportunidade.",
        "Recomendamos a ação.",
        "Compre agora.",
        "A ação está barata.",
        "O balanço é forte.",
        "O lucro surpreendeu.",
        "A margem despencou.",
        "O resultado é garantido.",
        "Há sinal de fraude.",
        "O lucro bateu recorde.",
        "O preço-alvo é outro.",
    ],
)
def test_palavra_proibida(texto):
    assert _regras(saida.Frase(texto)) == ["palavra"]


@pytest.mark.parametrize(
    "texto",
    [
        "O lucro vai subir.",
        "A margem deve cair.",
        "A dívida tende a crescer.",
        "Esperamos melhora.",
    ],
)
def test_previsao(texto):
    assert _regras(saida.Frase(texto)) == ["previsao"]


@pytest.mark.parametrize(
    "texto",
    [
        "Não é previsão: é a régua de hoje.",
        "Nada aqui é recomendação de compra ou venda, preço-alvo ou previsão.",
        "A venda de energia no mercado livre.",
        "O recorde de 26,4% do ROE.",
    ],
)
def test_frases_permitidas(texto):
    notas = ("retorno.roe",) if "26,4%" in texto else ()
    assert _regras(saida.Frase(texto, notas)) == []


def test_lacuna_obrigatoria_omitida_reprova_os_limites():
    analise = _analise(FRASE_NEUTRA)
    partes = [
        p if p.chave != "limites" else saida.Parte("limites", p.paragrafos[:1])
        for p in analise.partes
    ]
    conferencia = porta1.conferir(saida.Analise(tuple(partes)), ENTRADA)
    assert {r.regra for r in conferencia.reprovacoes} == {"lacuna"}
    assert conferencia.partes_reprovadas == frozenset({"limites"})


def test_estrutura_parte_faltando_vazia_ou_fora_de_ordem():
    analise = _analise(FRASE_NEUTRA)
    sem_uma = saida.Analise(analise.partes[1:])
    conferencia = porta1.conferir(sem_uma, ENTRADA)
    assert conferencia.partes_reprovadas == frozenset({"em_meia_pagina"})
    vazia = list(analise.partes)
    vazia[2] = saida.Parte(vazia[2].chave, ())
    assert porta1.conferir(saida.Analise(tuple(vazia)), ENTRADA).partes_reprovadas == {
        "quem_manda"
    }
    trocada = list(analise.partes)
    trocada[0], trocada[1] = trocada[1], trocada[0]
    assert "estrutura" in {
        r.regra
        for r in porta1.conferir(saida.Analise(tuple(trocada)), ENTRADA).reprovacoes
    }


def test_reprovacao_diz_onde_e_o_que():
    (reprovacao,) = porta1.conferir(
        _analise(saida.Frase("O ROE é 26,5%.", ("retorno.roe",))), ENTRADA
    ).reprovacoes
    assert reprovacao.parte == "o_que_os_numeros_mostram"
    assert (reprovacao.paragrafo, reprovacao.frase) == (1, 0)
    assert "26,5%" in reprovacao.detalhe
