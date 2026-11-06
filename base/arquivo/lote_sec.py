"""Lote SEC do arquivista: mais conjuntos da Data Library (rodada 4, 23/10/2026).

Complementa o `lote_eua` (que já guarda o Form D, o 13F, os índices do EDGAR e a busca de texto das
emissoras brasileiras) com os conjuntos que ele deixou de fora: demonstrações financeiras de todos
os 10-K e 10-Q (`sub`, `num`, `pre`, `tag` e as notas), Forms 3, 4 e 5 dos insiders, N-PORT, N-CEN,
N-MFP, Reg A, crowdfunding, BDC, Form ADV, consultores municipais, corretoras ativas, registros de
pedidos FOIA e os dois pacotes diários do EDGAR (`submissions.zip` e `companyfacts.zip`). São todos
domínio público do governo dos EUA (`sec` em `LICENCAS`); nenhum pede chave.

Escolhas (testes em `tests/test_base_arquivo_lote_sec.py`):
- **os arquivos saem da própria página da Data Library**, que lista do mais novo ao mais antigo: a
  fonte semanal leva os `recentes` e a carga única `-historico` leva o resto (só pelo id);
- **ritmo pelo calendário:** conjunto trimestral ou mensal é `semanal` com `pesada=True` (a coleta
  confere o ETag e só baixa quando mudou); os dois pacotes do EDGAR são `diaria` com `pesada=True`
  (~1,5 GB cada, ETag): a carga deles roda no servidor, nunca no PC;
- **SEC:** o `User-Agent` é o de `cliente_http`; a SEC responde 403 ao `curl` simples e permite 10
  pedidos por segundo. Página que não lista arquivo é erro (a SEC mudou o layout), e o 403 de
  bloqueio não vira "página sem arquivo";
- **LGPD:** os insiders (Forms 3, 4 e 5) e o Form ADV trazem nomes de pessoas (dado público nos
  EUA). O arquivo é guardado como a SEC publica, a mesma regra do Form D e do 13F do `lote_eua`;
  nenhuma tabela derivada leva pessoa física e nada cruza com dado de brasileiros;
- **ficam de fora:** os dados de variable insurance product (sem uso previsto), as páginas de
  estatística (planilhas soltas) e o que o `lote_eua` já guarda. Os ids não repetem os dele.
"""

import re
from collections.abc import Callable
from datetime import datetime

from base.arquivo.coleta import Alvo, Cliente, Descobrir, ErroDeDescoberta, Fonte

SEC = "https://www.sec.gov"
SEMANAL = "semanal"
CARGA_UNICA = "carga-unica"
CONJUNTOS = "/data-research/sec-markets-data/"
RECENTES = 2  # a página lista do mais novo ao mais antigo

# pacotes diários do EDGAR (cada um tem ~1,5 GB e ETag)
PACOTES_DO_EDGAR = {
    "sec-bulk-submissions": SEC
    + "/Archives/edgar/daily-index/bulkdata/submissions.zip",
    "sec-bulk-companyfacts": SEC + "/Archives/edgar/daily-index/xbrl/companyfacts.zip",
}

FOIA = "/foia/frequently-requested-documents/"
# id → (página, extensão dos arquivos, quantos são os recentes); páginas conferidas em 23/10/2026
CONJUNTOS_DA_DATA_LIBRARY = {
    "sec-demonstracoes-financeiras": (
        CONJUNTOS + "financial-statement-data-sets",
        "zip",
        RECENTES,
    ),
    "sec-notas-das-demonstracoes": (
        CONJUNTOS + "financial-statement-notes-data-sets",
        "zip",
        RECENTES,
    ),
    "sec-insiders": (CONJUNTOS + "insider-transactions-data-sets", "zip", RECENTES),
    "sec-nport": (CONJUNTOS + "form-n-port-data-sets", "zip", RECENTES),
    "sec-ncen": (CONJUNTOS + "form-n-cen-data-sets", "zip", RECENTES),
    "sec-nmfp": (CONJUNTOS + "dera-form-n-mfp-data-sets", "zip", RECENTES),
    "sec-reg-a": (CONJUNTOS + "regulation-data-sets", "zip", RECENTES),
    "sec-crowdfunding": (
        CONJUNTOS + "crowdfunding-offerings-data-sets",
        "zip",
        RECENTES,
    ),
    "sec-bdc": (CONJUNTOS + "bdc-data-sets", "zip", RECENTES),
    # exempt e registered saem juntos em cada mês: os dois mais novos são o mês corrente
    "sec-form-adv": (
        CONJUNTOS
        + "information-about-registered-investment-advisers-exempt-reporting-advisers",
        "zip",
        RECENTES,
    ),
    "sec-consultores-municipais": (
        CONJUNTOS + "information-about-registered-municipal-advisors",
        "zip",
        RECENTES,
    ),
    "sec-corretoras": (
        FOIA + "company-information-about-active-broker-dealers",
        "txt",
        RECENTES,
    ),
    # cada mês traz o registro e o registro dos pedidos negados pela exceção b7a
    "sec-foia-registros": (FOIA + "foia-logs", "csv", 4),
}


def arquivos_da_pagina(pagina: bytes, extensao: str) -> list[str]:
    """Os caminhos `/files/...` com a extensão, sem repetir e na ordem da página."""
    padrao = re.compile(rb'href="(/files/[^"]+\.' + extensao.encode() + rb')"')
    return list(dict.fromkeys(m.decode() for m in padrao.findall(pagina)))


def _da_pagina(
    caminho: str, extensao: str, recorte: Callable[[list[str]], list[str]]
) -> Descobrir:
    def descobrir(cliente: Cliente, agora: datetime) -> list[Alvo]:
        arquivos = arquivos_da_pagina(cliente.ler(SEC + caminho).conteudo, extensao)
        if not arquivos:
            raise ErroDeDescoberta(f"nenhum .{extensao} linkado em {SEC + caminho}")
        return [Alvo(SEC + arquivo) for arquivo in recorte(arquivos)]

    return descobrir


def _recentes(quantos: int) -> Callable[[list[str]], list[str]]:
    return lambda arquivos: arquivos[:quantos]


def _antigos(quantos: int) -> Callable[[list[str]], list[str]]:
    return lambda arquivos: arquivos[quantos:]


def _tipo(extensao: str) -> str:
    return "zip" if extensao == "zip" else "arquivo"


def _data_library() -> list[Fonte]:
    fontes = []
    for id_, (caminho, extensao, recentes) in CONJUNTOS_DA_DATA_LIBRARY.items():
        tipo = _tipo(extensao)
        fontes.append(
            Fonte(
                id_,
                SEMANAL,
                _da_pagina(caminho, extensao, _recentes(recentes)),
                tipo,
                pesada=True,
            )
        )
        # a carga única da história: só roda pelo id
        fontes.append(
            Fonte(
                f"{id_}-historico",
                CARGA_UNICA,
                _da_pagina(caminho, extensao, _antigos(recentes)),
                tipo,
                pesada=True,
            )
        )
    return fontes


def _pacotes_do_edgar() -> list[Fonte]:
    return [
        Fonte(
            id_,
            "diaria",
            lambda cliente, agora, url=url: [Alvo(url, ".zip")],
            "zip",
            pesada=True,
        )
        for id_, url in PACOTES_DO_EDGAR.items()
    ]


def fontes() -> list[Fonte]:
    """Todas as fontes do lote, na ordem: pacotes diários e conjuntos da Data Library."""
    return [*_pacotes_do_edgar(), *_data_library()]
