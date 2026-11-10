"""Grava o contrato da API externa (`/data/v1`) em docs/api/openapi-data-v1.json.

É o arquivo que quem integra lê (a CLI, a Ficha Clara, o cliente que gera código a partir dele): as
rotas, os parâmetros (`known_at` em toda leitura por CNPJ), os esquemas e os erros de cada rota, com o
código que sai em `detail`. Há teste que confere se está em dia e se os códigos batem com os que o código
levanta (`tests/test_api_externa_por_cnpj_contrato.py`); mudou uma rota da `/data/v1`, rode de novo e
revise o diff no PR.

Uso: python -m scripts.gerar_openapi_data

Roda: manual (python -m scripts.gerar_openapi_data), quando uma rota da /data/v1 muda; coberto por
test_api_externa_por_cnpj_contrato.py; ver docs/api/README.md.
"""

import json
from collections import defaultdict
from pathlib import Path

from fastapi import FastAPI

from src.api_externa.rotas import router

ARQUIVO = (
    Path(__file__).resolve().parent.parent / "docs" / "api" / "openapi-data-v1.json"
)
TITULO = "TickerLab Data API"
VERSAO = "1"
ESQUEMA_DO_ERRO = "Error"

# código em `detail` → (status HTTP, quando sai). Os códigos são os de `src/api_externa/` (o teste confere).
ERROS: dict[str, tuple[int, str]] = {
    "api_key_in_url": (400, "a chave veio na URL; ela vai só no cabeçalho"),
    "invalid_api_key": (
        401,
        "chave ausente, errada ou revogada, ou organização suspensa (o motivo não sai)",
    ),
    "rate_limited": (429, "passou do limite de pedidos por minuto do plano"),
    "monthly_quota_exceeded": (
        429,
        "passou da quota do mês do plano (o lote inteiro volta, sem ler nenhum CNPJ)",
    ),
    "invalid_known_at": (400, "`known_at` no futuro"),
    "invalid_cnpj": (400, "o CNPJ do endereço não é um CNPJ"),
    "invalid_assumed_return": (
        400,
        "`assumed_return` não é um número ou está fora do plausível",
    ),
    "invalid_batch": (400, "o lote está vazio ou passa de 100 CNPJs"),
    "not_available": (
        404,
        (
            "nada a servir: o CNPJ não existe na base, não é empresa (MEI, empresário individual), "
            "o contrato ou o direito de redistribuir não cobre, ou a tabela não está pronta; a "
            "resposta não diz qual (D2.2)"
        ),
    ),
    "service_unavailable": (503, "a base não está disponível neste servidor agora"),
}
SEMPRE = ("api_key_in_url", "invalid_api_key", "rate_limited")
DE_DADO = ("monthly_quota_exceeded", "invalid_known_at", "service_unavailable")
DE_UM_CNPJ = ("invalid_cnpj", "not_available")


def _parametros(operacao: dict) -> set[str]:
    return {p["name"] for p in operacao.get("parameters", [])}


def _lote(operacao: dict) -> bool:
    return "requestBody" in operacao


def codigos_da_operacao(caminho: str, operacao: dict) -> list[str]:
    """Os códigos de erro que uma rota pode dar, pela forma dela: toda rota passa pela chave e pelo
    limite do minuto; a de dado (com `known_at` ou lote) gasta a quota e lê a base; a de um CNPJ pode não
    ter o que servir."""
    parametros = _parametros(operacao)
    codigos = list(SEMPRE)
    if "known_at" in parametros or _lote(operacao):
        codigos += DE_DADO
    if "{cnpj}" in caminho:
        codigos += DE_UM_CNPJ
    if "assumed_return" in parametros:
        codigos.append("invalid_assumed_return")
    if _lote(operacao):
        codigos.append("invalid_batch")
    return codigos


def _respostas_de_erro(codigos: list[str]) -> dict[str, dict]:
    por_status: dict[int, list[str]] = defaultdict(list)
    for codigo in codigos:
        por_status[ERROS[codigo][0]].append(codigo)
    respostas = {}
    for status, deste in sorted(por_status.items()):
        respostas[str(status)] = {
            "description": "; ".join(f"`{c}`: {ERROS[c][1]}" for c in deste),
            "content": {
                "application/json": {
                    "schema": {
                        "allOf": [{"$ref": f"#/components/schemas/{ESQUEMA_DO_ERRO}"}],
                        "properties": {"detail": {"enum": deste}},
                    }
                }
            },
        }
    return respostas


def _com_os_erros(esquema: dict) -> dict:
    esquema.setdefault("components", {}).setdefault("schemas", {})[ESQUEMA_DO_ERRO] = {
        "type": "object",
        "required": ["detail"],
        "properties": {
            "detail": {"type": "string", "description": "o código do erro, em inglês"}
        },
    }
    for caminho, metodos in esquema["paths"].items():
        for operacao in metodos.values():
            operacao["responses"].update(
                _respostas_de_erro(codigos_da_operacao(caminho, operacao))
            )
    return esquema


def openapi_data_v1() -> dict:
    """O esquema OpenAPI só da `/data/v1`, montado num app à parte (a API de leitura `/v1` e o prefixo
    `/api` do serviço não entram no contrato de quem integra), com os erros de cada rota."""
    app = FastAPI(title=TITULO, version=VERSAO)
    app.include_router(router)
    return _com_os_erros(app.openapi())


def main() -> None:
    texto = json.dumps(openapi_data_v1(), ensure_ascii=False, indent=2, sort_keys=True)
    ARQUIVO.write_text(texto + "\n", encoding="utf-8")
    print(f"Gravado: {ARQUIVO}")


if __name__ == "__main__":
    main()
