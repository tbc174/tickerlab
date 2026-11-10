"""O contrato publicado da API externa (`docs/api/openapi-data-v1.json`): quem integra confia nele.

Linha 736 da fila (API por CNPJ). O arquivo é o que a CLI (`cli/`) e a Ficha Clara leem para saber as
rotas, os parâmetros e os erros da `/data/v1`; ficar velho é quebrar o cliente sem avisar.
"""

import json
import re
from pathlib import Path

from scripts.gerar_openapi_data import ARQUIVO, ERROS, openapi_data_v1

RAIZ = Path(__file__).resolve().parent.parent
LEVANTA = re.compile(
    r'(?:detail=|_recusa\(|(?:CODIGO_\w+|NAO_DISPONIVEL)\s*=\s*)"([a-z]+(?:_[a-z]+)+)"'
)

ROTAS_QUE_JA_EXISTEM = {
    "/data/v1/catalog",
    "/data/v1/usage",
    "/data/v1/companies/{cnpj}",
    "/data/v1/companies/{cnpj}/financials",
    "/data/v1/companies/batch",
    "/data/v1/funds/{cnpj}",
    "/data/v1/funds/batch",
}


def _parametros(operacao: dict) -> dict[str, dict]:
    return {p["name"]: p for p in operacao.get("parameters", [])}


def _operacoes(esquema: dict):
    for caminho, metodos in esquema["paths"].items():
        for metodo, operacao in metodos.items():
            yield caminho, metodo, operacao


def test_o_esquema_publicado_esta_em_dia():
    """Mudou uma rota da `/data/v1`? Rode `python -m scripts.gerar_openapi_data` e revise o diff."""
    publicado = json.loads(ARQUIVO.read_text(encoding="utf-8"))
    assert publicado == openapi_data_v1(), "docs/api/openapi-data-v1.json está velho"


def test_o_esquema_tem_as_rotas_que_ja_existem():
    """Rota nova entra sem quebrar este teste; rota que some quebra (o cliente dependia dela)."""
    assert set(openapi_data_v1()["paths"]) >= ROTAS_QUE_JA_EXISTEM


def test_o_esquema_so_tem_a_api_externa():
    """Nenhuma rota da API de leitura (`/v1`, da conta) vaza para o contrato de quem integra."""
    assert all(c.startswith("/data/v1/") for c in openapi_data_v1()["paths"])


def test_toda_rota_de_um_cnpj_aceita_o_known_at():
    """A data do "como era em" (ADR 0108, D7) vale em toda leitura por CNPJ, sem exceção."""
    for caminho, metodo, operacao in _operacoes(openapi_data_v1()):
        if "{cnpj}" in caminho and metodo == "get":
            parametro = _parametros(operacao).get("known_at")
            assert parametro is not None, caminho
            assert parametro["in"] == "query", caminho
            assert parametro["schema"]["anyOf"][0]["format"] == "date", caminho


def test_a_chave_nunca_e_parametro_do_endereco():
    """A chave vai só no cabeçalho: um parâmetro de URL com ela iria para os logs de acesso."""
    for caminho, _, operacao in _operacoes(openapi_data_v1()):
        nomes = {
            n.lower() for n, p in _parametros(operacao).items() if p["in"] == "query"
        }
        assert not nomes & {"api_key", "apikey", "key", "token"}, caminho


def _codigos_no_esquema(esquema: dict) -> set[str]:
    return {
        codigo
        for _, _, operacao in _operacoes(esquema)
        for status, resposta in operacao["responses"].items()
        if int(status) >= 400 and status != "422"
        for codigo in resposta["content"]["application/json"]["schema"]["properties"][
            "detail"
        ]["enum"]
    }


def _codigos_no_codigo() -> set[str]:
    """Os códigos que `src/api_externa/` levanta: o texto de `detail=`, de `_recusa(...)` e das constantes
    `CODIGO_*` e `NAO_DISPONIVEL`."""
    pasta = RAIZ / "src" / "api_externa"
    texto = "\n".join(a.read_text(encoding="utf-8") for a in pasta.rglob("*.py"))
    return set(LEVANTA.findall(texto))


def test_todo_erro_do_esquema_existe_no_codigo_e_vice_versa():
    """O contrato não inventa erro, e nenhum código que o código levanta fica sem documentar."""
    assert set(ERROS) == _codigos_no_codigo()
    assert _codigos_no_esquema(openapi_data_v1()) == set(ERROS)


def test_a_rota_de_um_cnpj_documenta_o_404_e_a_de_catalogo_nao():
    """O cliente distingue "não há o que servir" (404) de chave, quota e CNPJ inválido."""
    caminhos = openapi_data_v1()["paths"]
    respostas = caminhos["/data/v1/companies/{cnpj}"]["get"]["responses"]
    assert {"400", "401", "404", "429", "503"} <= set(respostas)
    catalogo = caminhos["/data/v1/catalog"]["get"]["responses"]
    assert "404" not in catalogo and "503" not in catalogo
    detalhe_429 = catalogo["429"]["content"]["application/json"]["schema"]
    assert detalhe_429["properties"]["detail"]["enum"] == ["rate_limited"]


def test_o_arquivo_e_estavel_entre_duas_geracoes():
    """Gerar duas vezes dá o mesmo texto (chaves ordenadas): o diff do PR mostra só o que mudou."""
    assert json.dumps(openapi_data_v1(), sort_keys=True) == json.dumps(
        openapi_data_v1(), sort_keys=True
    )
