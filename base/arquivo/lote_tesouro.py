"""Lote Tesouro do arquivista: mais pacotes do Tesouro Transparente e a dívida ativa da PGFN de todos os
trimestres (23/10/2026, linha 202 da fila).

Cada fonte do Tesouro é um `Fonte` que guarda os arquivos do pacote como o portal os publica (licença
ODbL, já marcada em `src/banco/coletas.py`; o portal CKAN não pede chave). O catálogo respondeu em
`www.tesourotransparente.gov.br/ckan` (o mesmo `PORTAL_DO_TESOURO` de `fontes.py`); o domínio
`apidatalake.tesouro.gov.br`, que o levantamento de 22/10 citou, devolve 404 para `/ckan`.

Escolhas (testes em `tests/test_base_arquivo_lote_tesouro.py`):
- **LGPD (ADR 0088): nada de dado por pessoa.** Os pacotes abaixo foram abertos em 23/10/2026 e só
  trazem União, estados, municípios, títulos e estatais. Ficaram de fora `investidores-do-tesouro-direto`
  (um registro por investidor: gênero, idade, profissão e cidade) e `operacoes-do-tesouro-direto` (as
  operações de cada código de investidor, que ligam o investidor ao que ele comprou): entram depois,
  agregados antes de guardar (linha da fila);
- **fora também:** `seriestemporaisdotesouronacional` (o pacote só aponta para uma página de
  visualização, sem arquivo) e as APIs que o catálogo lista (`API Séries Temporais`);
- **só os arquivos de dados:** o catálogo mistura CSV, XLSX, PDF de metadados e PNG; cada fonte pede os
  formatos do dado (`formatos`), menos a dos subsídios ao BNDES, que só existe em PDF;
- **ritmo pelo calendário do pacote:** o RTN e os pacotes mensais rodam `mensal`; o que o portal regrava
  toda semana (Tesouro Direto) roda `semanal`. As grandes (despesas da União 74 MB, transferências com
  300 arquivos e CAPAG dos municípios 200 MB) são `pesada`: o Arquivista só baixa o que mudou (ETag);
- **PGFN histórica:** a `pgfn-divida` guarda só o último trimestre; a `pgfn-divida-historico` guarda
  todos os outros (25 pastas em 23/10/2026, três ZIPs cada), em carga única, só pelo id. O leitor
  `base/pgfn.py` lê só a `pgfn-divida`: a tabela da evolução é uma linha da fila;
- **o pacote que o portal trocar de nome ou esvaziar** falha na descoberta com o nome dele (um pacote
  sem arquivo é erro, nunca "ok").

Este módulo não importa `fontes.py` (que importa este): usa a descoberta de `lote_brasil2`.
"""

import re
from datetime import datetime

from base.arquivo.coleta import Alvo, Cliente, Descobrir, ErroDeDescoberta, Fonte
from base.arquivo.lote_brasil2 import descobrir_ckan

PORTAL_DO_TESOURO = "https://www.tesourotransparente.gov.br/ckan"
RAIZ_DA_PGFN = "https://dadosabertos.pgfn.gov.br/"
PASTA_DO_TRIMESTRE = re.compile(rb'href="(\d{4}_trimestre_\d{2})/"')
ZIP_NA_PASTA = re.compile(rb'href="([^"/]+\.zip)"')

SEMANAL = "semanal"
MENSAL = "mensal"
CARGA_UNICA = "carga-unica"

CSV = ("csv",)
XLSX = ("xlsx",)
PDF = ("pdf",)


def _pacote(
    ritmo: str,
    pacotes: tuple[str, ...],
    formatos: tuple[str, ...],
    *,
    pesada: bool = False,
) -> tuple[str, tuple[str, ...], tuple[str, ...], bool]:
    return ritmo, pacotes, formatos, pesada


# id da fonte -> (ritmo, pacotes do portal, formatos, pesada)
PACOTES: dict[str, tuple[str, tuple[str, ...], tuple[str, ...], bool]] = {
    # macro fiscal
    "tesouro-br-rtn": _pacote(MENSAL, ("resultado-do-tesouro-nacional",), XLSX),
    "tesouro-br-receitas": _pacote(MENSAL, ("receita-orcamentaria-da-uniao",), CSV),
    "tesouro-br-despesas": _pacote(
        MENSAL, ("despesas-da-uniao-mensais-desde-2008",), XLSX, pesada=True
    ),
    "tesouro-br-restos-a-pagar": _pacote(MENSAL, ("restos-a-pagar-da-uniao",), CSV),
    "tesouro-br-fatores-divida": _pacote(
        MENSAL, ("fatores-de-variacao-da-divida-publica-federal",), XLSX
    ),
    "tesouro-br-paf": _pacote(MENSAL, ("metas-paf",), CSV),
    "tesouro-br-bspn": _pacote(MENSAL, ("planilhas-bspn",), XLSX),
    "tesouro-br-limites-lrf": _pacote(MENSAL, ("limites-lrf-uniao",), CSV),
    # estatais, bancos públicos e garantias
    "tesouro-br-dividendos-estatais": _pacote(
        MENSAL, ("dividendos-arrecadados-pela-uniao",), XLSX
    ),
    "tesouro-br-subsidios-bndes": _pacote(
        MENSAL, ("relatorio-de-subsidios-ao-bndes",), PDF
    ),
    "tesouro-br-garantias": _pacote(
        MENSAL,
        (
            "garantias-concedidas-em-operacoes-de-credito",
            "garantias-concedidas-em-operacoes-de-credito-internas",
        ),
        CSV,
    ),
    # estados e municípios
    "tesouro-br-transferencias": _pacote(
        MENSAL,
        (
            "transferencias-constitucionais-para-estados",
            "transferencias-constitucionais-para-municipios",
        ),
        CSV,
        pesada=True,
    ),
    "tesouro-br-capag-municipios": _pacote(
        MENSAL, ("capag-municipios",), XLSX, pesada=True
    ),
    # Tesouro Direto agregado por título (sem investidor)
    "tesouro-br-td-vendas": _pacote(SEMANAL, ("vendas-do-tesouro-direto",), CSV),
    "tesouro-br-td-resgates": _pacote(SEMANAL, ("resgates-do-tesouro-direto",), CSV),
    "tesouro-br-td-estoque": _pacote(SEMANAL, ("estoque-do-tesouro-direto",), CSV),
}


def _do_portal(pacotes: tuple[str, ...], formatos: tuple[str, ...]) -> Descobrir:
    def descobrir(cliente: Cliente, agora: datetime) -> list[Alvo]:
        return descobrir_ckan(cliente, PORTAL_DO_TESOURO, *pacotes, formatos=formatos)

    return descobrir


def descobrir_pgfn_historico(cliente: Cliente, agora: datetime) -> list[Alvo]:
    """Os ZIPs de todos os trimestres da dívida ativa menos o último (que é da `pgfn-divida`)."""
    raiz = cliente.ler(RAIZ_DA_PGFN).conteudo
    trimestres = sorted(m.decode() for m in PASTA_DO_TRIMESTRE.findall(raiz))
    if len(trimestres) < 2:
        raise ErroDeDescoberta("PGFN histórica: menos de dois trimestres na página")
    alvos: list[Alvo] = []
    for trimestre in trimestres[:-1]:
        pasta = f"{RAIZ_DA_PGFN}{trimestre}/"
        zips = dict.fromkeys(
            m.decode() for m in ZIP_NA_PASTA.findall(cliente.ler(pasta).conteudo)
        )
        if not zips:
            raise ErroDeDescoberta(f"PGFN histórica: nenhum ZIP em {pasta}")
        alvos += [Alvo(pasta + nome) for nome in zips]
    return alvos


def fontes() -> list[Fonte]:
    """Todas as fontes do lote, para o `FONTES` do arquivista."""
    return [
        *(
            Fonte(id_, ritmo, _do_portal(pacotes, formatos), pesada=pesada)
            for id_, (ritmo, pacotes, formatos, pesada) in PACOTES.items()
        ),
        Fonte(
            "pgfn-divida-historico",
            CARGA_UNICA,
            descobrir_pgfn_historico,
            pesada=True,
        ),
    ]
