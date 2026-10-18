"""A versão clássica do app (o Streamlit) e o caminho dela: `app.tickerlab.com.br/classico/`.

Desde o plano de 18/10 (ADR 0062, Emenda 1) o app em React é o principal, na raiz, e o Streamlit
mora em `/classico`. O caminho vem da variável que o próprio Streamlit lê (`server.baseUrlPath`
pela variável de ambiente): o `compose.yaml` a dá ao serviço, a imagem confere a saúde nela e o
`app.py` mostra o aviso com a volta ao app novo. Sem a variável (PC, testes, CI) o app está na
raiz, como sempre.

Sem Streamlit aqui: o `HEALTHCHECK` do Dockerfile importa este módulo.
"""

import os
from collections.abc import Mapping

from src import paginas

VARIAVEL_DO_CAMINHO_BASE = "STREAMLIT_SERVER_BASE_URL_PATH"
# o app novo (React) é o principal: está na raiz do mesmo endereço
ENDERECO_DO_APP_NOVO = "/"
PORTA_DO_STREAMLIT = 8501
AVISO_DA_VERSAO_CLASSICA = (
    "Esta é a **versão clássica** do TickerLab. As telas novas estão no "
    f"[app principal]({ENDERECO_DO_APP_NOVO}); o que ainda não migrou continua aqui, "
    "com os mesmos números."
)


def caminho_base(ambiente: Mapping[str, str] | None = None) -> str:
    """O caminho onde o Streamlit está servido: `"/classico"` no servidor, `""` na raiz."""
    valor = (os.environ if ambiente is None else ambiente).get(
        VARIAVEL_DO_CAMINHO_BASE, ""
    )
    limpo = valor.strip().strip("/")
    return f"/{limpo}" if limpo else ""


def esta_no_classico(ambiente: Mapping[str, str] | None = None) -> bool:
    """O app está servido como a versão clássica (fora da raiz)?"""
    return caminho_base(ambiente) != ""


def url_da_saude(ambiente: Mapping[str, str] | None = None) -> str:
    """O endereço do teste de saúde do Streamlit, de dentro do contêiner (Dockerfile)."""
    return (
        f"http://127.0.0.1:{PORTA_DO_STREAMLIT}{caminho_base(ambiente)}/_stcore/health"
    )


def enderecos_das_paginas(ambiente: Mapping[str, str] | None = None) -> list[str]:
    """O endereço de cada página no navegador (o Streamlit guarda o tema por endereço)."""
    base = caminho_base(ambiente)
    return [f"{base}/", *(f"{base}/{p.url}" for p in paginas.paginas_do_classico())]
