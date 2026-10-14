"""O mapa de páginas precisa ser coerente: sem repetição, todos os grupos usados, recursos conhecidos."""

import pytest

from src import paginas
from src.planos import LIMITES_DOS_PLANOS


def test_chaves_e_enderecos_sao_unicos():
    chaves = [p.chave for p in paginas.PAGINAS]
    assert len(chaves) == len(set(chaves))
    enderecos = [p.url for p in paginas.PAGINAS]
    assert len(enderecos) == len(set(enderecos))


def test_todo_grupo_tem_paginas_e_toda_pagina_tem_grupo_conhecido():
    for grupo in paginas.GRUPOS:
        assert paginas.paginas_do_grupo(grupo), grupo
        assert grupo in paginas.FRASE_DE_CADA_GRUPO
    assert {p.grupo for p in paginas.PAGINAS} <= set(paginas.GRUPOS)


def test_pagina_inicial_existe_e_e_a_primeira():
    assert paginas.PAGINAS[0].chave == paginas.PAGINA_INICIAL
    assert not paginas.pagina(paginas.PAGINA_INICIAL).precisa_do_ativo


@pytest.mark.parametrize("pagina", paginas.PAGINAS, ids=lambda p: p.chave)
def test_textos_completos(pagina):
    assert pagina.titulo and pagina.descricao.endswith((".", "?"))
    assert pagina.icone.startswith(":material/") and pagina.icone.endswith(":")
    assert pagina.url == pagina.url.lower() and " " not in pagina.url


def test_recursos_exigidos_existem_em_algum_plano():
    conhecidos = set().union(*(p.recursos for p in LIMITES_DOS_PLANOS.values()))
    for p in paginas.PAGINAS:
        if p.recurso:
            assert p.recurso in conhecidos


def test_o_grupo_avancado_tem_so_paginas_pro_e_so_ele():
    for p in paginas.PAGINAS:
        assert p.e_pro == (p.grupo == paginas.GRUPO_AVANCADO)


def test_paginas_de_conta_e_ajuda_nao_pedem_ativo():
    for chave in (
        "inicio",
        "guia",
        "termos",
        "privacidade",
        "simulacoes",
        "meus_dados",
        "planos",
        "admin",
    ):
        assert not paginas.pagina(chave).precisa_do_ativo


def test_so_o_grupo_de_administracao_e_restrito_a_administradores():
    for p in paginas.PAGINAS:
        assert p.somente_admin == (p.grupo == paginas.GRUPO_ADMIN)


# --- Contrato de entradas e saídas (preparação 3 da ADR 0044; ADR 0048) ---


def _contratos():
    from src.paginas import PAGINAS

    return {p.chave: p.contrato for p in PAGINAS if p.contrato is not None}


def _openapi():
    from src.api_v1.rotas import openapi_v1

    return openapi_v1()


def _faixa(esquema: dict) -> dict:
    """Junta os limites de um parâmetro, inclusive quando ele aceita null (anyOf)."""
    partes = [esquema, *esquema.get("anyOf", [])]
    juntos: dict = {}
    for parte in partes:
        for chave in ("minimum", "maximum", "enum", "default", "type"):
            if chave in parte and parte.get("type") != "null":
                juntos.setdefault(chave, parte[chave])
    return juntos


def _entradas_da_rota(operacao: dict, esquemas: dict) -> dict[str, tuple[bool, dict]]:
    """{nome: (obrigatória?, limites)} de uma rota, pela query (GET) ou pelo corpo (POST)."""
    if "requestBody" in operacao:
        ref = operacao["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        corpo = esquemas[ref.rsplit("/", 1)[-1]]
        obrigatorias = set(corpo.get("required", []))
        return {
            nome: (nome in obrigatorias, _faixa(esquema))
            for nome, esquema in corpo["properties"].items()
        }
    return {
        p["name"]: (p["required"], _faixa(p["schema"]))
        for p in operacao["parameters"]
        if p["in"] == "query"
    }


def test_as_paginas_de_analise_tem_contrato():
    assert set(_contratos()) == {
        "visao_geral",
        "risco",
        "retorno_mensal",
        "comparar",
        "backtest",
        "juros_e_inflacao",
        "linha_do_tempo",
    }


def test_cada_contrato_bate_com_a_rota_de_verdade():
    """Nome, obrigatoriedade, limites, opções e padrão de cada entrada iguais aos da API."""
    esquema = _openapi()
    for chave, contrato in _contratos().items():
        operacao = esquema["paths"][contrato.rota][contrato.metodo.lower()]
        rota = _entradas_da_rota(operacao, esquema["components"]["schemas"])
        assert set(rota) == {e.nome for e in contrato.entradas}, chave
        for entrada in contrato.entradas:
            obrigatoria, limites = rota[entrada.nome]
            assert obrigatoria == entrada.obrigatoria, (chave, entrada.nome)
            assert limites.get("minimum") == entrada.minimo, (chave, entrada.nome)
            assert limites.get("maximum") == entrada.maximo, (chave, entrada.nome)
            assert tuple(limites.get("enum", ())) == entrada.opcoes, (
                chave,
                entrada.nome,
            )
            assert limites.get("default") == entrada.padrao, (chave, entrada.nome)
        resposta = operacao["responses"]["200"]["content"]["application/json"]["schema"]
        assert resposta["$ref"].rsplit("/", 1)[-1] == contrato.resposta, chave


def test_toda_rota_de_leitura_pertence_a_uma_pagina():
    usadas = {c.rota for c in _contratos().values()}
    # /eu, /conta e o aceite são da conta e /configuracao é do login, não de uma página
    assert set(_openapi()["paths"]) - usadas == {
        "/v1/eu",
        "/v1/conta",
        "/v1/aceite-dos-termos",
        "/v1/configuracao",
    }


def test_periodos_do_contrato_sao_os_do_app():
    from src.dados import PERIODOS_VALIDOS
    from src.paginas import PERIODOS

    assert list(PERIODOS) == PERIODOS_VALIDOS


# --- Quem pode abrir cada página (ADR 0062): a mesma regra no Streamlit e na API ---


def test_motivo_da_pagina_paga_e_o_do_recurso():
    assert paginas.motivo_da_pagina("gratuito", "aprendizado") == (
        "Aprendizado de máquina faz parte do plano Pro. Você está no plano Gratuito."
    )
    assert paginas.motivo_da_pagina("pro", "aprendizado") is None


@pytest.mark.parametrize("plano", [None, "", "gratuito", "plus", "pro", "empresa"])
def test_pagina_livre_abre_em_qualquer_plano(plano):
    assert paginas.motivo_da_pagina(plano, "visao_geral") is None


@pytest.mark.parametrize("rota", ["/v1/risco", "/api/v1/risco"])
def test_pagina_da_rota_acha_pelo_contrato(rota):
    assert paginas.pagina_da_rota(rota) is paginas.pagina("risco")


@pytest.mark.parametrize(
    "rota", ["/v1/nada", "/v1/eu", "/api/risco", "/apiv1/risco", ""]
)
def test_pagina_da_rota_sem_contrato_e_none(rota):
    assert paginas.pagina_da_rota(rota) is None


def test_cada_rota_de_contrato_e_unica():
    rotas = [p.contrato.rota for p in paginas.PAGINAS if p.contrato is not None]
    assert len(rotas) == len(set(rotas))
    assert set(paginas.POR_ROTA) == set(rotas)
