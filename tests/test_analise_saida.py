"""O formato da análise escrita: 8 partes, parágrafos de fato ou leitura, frases com notas e contas."""

import pytest

from src.analise_escrita import saida as sa


def _frase(texto="O ROE é 26,4%.", notas=("retorno.roe",), contas=()):
    return {"texto": texto, "notas": list(notas), "contas": list(contas)}


def _resposta(**trocas):
    partes = [
        {"chave": chave, "paragrafos": [{"tipo": "fato", "frases": [_frase()]}]}
        for chave in sa.PARTES
    ]
    return {"partes": partes, **trocas}


def test_resposta_valida_vira_analise():
    conta = {
        "operacao": "produto",
        "de": [
            {"id": "retorno.dupont_margem", "valor": None, "conta": None},
            {"id": "retorno.dupont_giro", "valor": None, "conta": None},
        ],
        "resultado": 0.072,
    }
    resposta = _resposta()
    resposta["partes"][4]["paragrafos"].append(
        {"tipo": "leitura", "frases": [_frase("Dá 7,2%.", contas=[conta])]}
    )
    analise = sa.ler_analise(resposta)
    assert [p.chave for p in analise.partes] == list(sa.PARTES)
    leitura = analise.parte("o_que_os_numeros_mostram").paragrafos[1]
    assert leitura.tipo == "leitura"
    (lida,) = leitura.frases[0].contas
    assert lida.operacao == "produto" and lida.de[0].id == "retorno.dupont_margem"
    assert all(p.origem == sa.ORIGEM_MODELO for p in analise.partes)
    assert sa.ler_analise(analise.como_dict()) == analise


@pytest.mark.parametrize(
    ("estrago", "motivo"),
    [
        (lambda r: r["partes"][0].update(chave="opiniao"), "parte desconhecida"),
        (lambda r: r["partes"][0]["paragrafos"][0].update(tipo="opiniao"), "tipo"),
        (
            lambda r: r["partes"][0]["paragrafos"][0]["frases"][0].update(
                contas=[{"operacao": "soma", "de": [], "resultado": 1.0}]
            ),
            "sem operandos",
        ),
        (
            lambda r: r["partes"][0]["paragrafos"][0]["frases"][0].update(
                contas=[{"operacao": "media", "de": [{"id": "a"}], "resultado": 1.0}]
            ),
            "operação",
        ),
        (
            lambda r: r["partes"][0]["paragrafos"][0]["frases"][0].update(
                contas=[
                    {
                        "operacao": "soma",
                        "de": [{"id": "a", "valor": 1}],
                        "resultado": 1.0,
                    }
                ]
            ),
            "um só",
        ),
        (
            lambda r: r["partes"][0]["paragrafos"][0]["frases"][0].update(
                contas=[{"operacao": "soma", "de": [{"conta": 0}], "resultado": 1.0}]
            ),
            "conta anterior",
        ),
        (
            lambda r: r["partes"][0]["paragrafos"][0]["frases"][0].update(texto=" "),
            "vazia",
        ),
        (lambda r: r.pop("partes"), "partes"),
    ],
)
def test_resposta_fora_do_formato_da_erro(estrago, motivo):
    resposta = _resposta()
    estrago(resposta)
    with pytest.raises(sa.RespostaInvalidaError, match=motivo):
        sa.ler_analise(resposta)


PALAVRAS_DO_ESQUEMA = {
    "type",
    "properties",
    "required",
    "additionalProperties",
    "items",
    "enum",
    "description",
}


def _objetos(esquema):
    if isinstance(esquema, dict):
        if esquema.get("type") == "object":
            yield esquema
        for valor in esquema.values():
            yield from _objetos(valor)
    elif isinstance(esquema, list):
        for valor in esquema:
            yield from _objetos(valor)


def _palavras(esquema, dentro_de_properties=False):
    if isinstance(esquema, dict):
        for chave, valor in esquema.items():
            if not dentro_de_properties:
                yield chave
            yield from _palavras(
                valor, chave == "properties" and not dentro_de_properties
            )
    elif isinstance(esquema, list):
        for valor in esquema:
            yield from _palavras(valor)


def test_esquema_usa_so_o_que_a_saida_estruturada_aceita():
    """Todo objeto fechado e com todos os campos obrigatórios; nada de mínimo, máximo ou padrão."""
    objetos = list(_objetos(sa.ESQUEMA))
    assert len(objetos) >= 6
    for objeto in objetos:
        assert objeto["additionalProperties"] is False
        assert set(objeto["required"]) == set(objeto["properties"])
    assert set(_palavras(sa.ESQUEMA)) <= PALAVRAS_DO_ESQUEMA
    partes = sa.ESQUEMA["properties"]["partes"]["items"]["properties"]["chave"]
    assert partes["enum"] == list(sa.PARTES)


def test_titulos_das_partes():
    assert set(sa.TITULOS) == set(sa.PARTES)
    assert sa.TITULOS["limites"] == "Limites e perguntas em aberto"
