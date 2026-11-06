"""Debêntures pelos documentos da CVM (modelo 18, ADR 0030, Emenda 1): assembleias de debenturistas,
avisos aos debenturistas e notificações do agente fiduciário que as companhias entregam no IPE.

Medição e plano: `relatorio-modelo-18-agente-fiduciario.md` (pasta do projeto, 17/10/2026). PR 1: o tema
de cada documento sai **só do assunto** que a companhia preencheu no IPE, sem abrir o PDF (a metade
dos assuntos é genérica, "Ata da AGD", e fica marcada `generico`). Os relatórios anuais do agente
fiduciário, com a folga dos *covenants*, entram no PR 3, pelo texto do PDF.

**Data pública** (`publico_em`) = entrega daquela versão do documento à CVM. `referencia` é a data que a
companhia informou (no edital, o dia da assembleia, que pode vir depois da entrega). Cada versão
reapresentada é uma linha, com a própria data. Licença: ODbL (CVM).
"""

import re
import unicodedata
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import sqlalchemy as sa

from base import ratings
from base.parquet import LINHAGEM, gravar_se_mudou
from base.ratings import ler_ipe_bruto
from src import acervo
from src.banco.coletas import originais_mais_recentes
from src.links_das_fontes import link_da_fonte
from src.versao_do_codigo import versao_do_codigo

FONTE_DO_IPE = (
    ratings.FONTE_DO_IPE
)  # os arquivos anuais do IPE, os mesmos que os ratings leem
URL_DO_IPE = ratings.URL_DO_IPE


def simples(texto: object) -> str:
    """Sem acento e em minúsculas ("10ª Emissão" vira "10a emissao"), como `base/ratings.py` compara."""
    sem_acento = unicodedata.normalize("NFKD", str(texto or "")).encode(
        "ascii", "ignore"
    )
    return sem_acento.decode().lower().strip()


ASSEMBLEIA, AVISO, NOTIFICACAO = "assembleia", "aviso", "notificacao_do_agente"
# o assunto sem acento e em minúsculas ("10ª" vira "10a"); a ordem é a das colunas
TEMAS: dict[str, re.Pattern[str]] = {
    "vencimento_antecipado": re.compile(r"vencimento antecipad|vto\.? antecipad"),
    "waiver": re.compile(r"\bwaiver|renuncia|perdao|anuencia|consentimento previo"),
    "covenant": re.compile(
        r"covenant|(?:indices?|indicadores?|limites?) financeiros?|alavancagem"
        r"|divida liquida|ebitda"
    ),
    "repactuacao": re.compile(
        r"repactua|reperfil|prorroga|posterga|carencia|novo cronograma"
        r"|suspensao d[oa]s? (?:pagamento|amortizac|remunerac)"
        r"|alteracao d[aoe]s? (?:remuneracao|taxa|juros|prazo|data de vencimento|datas? de pagamento"
        r"|cronograma|amortizac)"
    ),
    "inadimplemento": re.compile(
        r"inadimpl|nao pagamento|\bdefault|recuperacao (?:judicial|extrajudicial)|falencia"
    ),
    "garantia": re.compile(
        r"garantia|alienacao fiduciaria|cessao fiduciaria|fianca|\baval\b|conta vinculada"
    ),
    "resgate": re.compile(
        r"resgate antecipado|amortizacao extraordinaria|oferta de resgate|aquisicao facultativa"
    ),
    "reorganizacao": re.compile(
        r"incorpora|\bcisao|\bfusao|reorganiza|controle (?:acionario|societario)"
        r"|(?:transferencia|alteracao|mudanca|troca|alienacao|aquisicao) d[eo] controle"
        r"|oferta publica inicial|\bipo\b|oferta publica (?:de distribuicao )?de acoes"
    ),
    "pagamento": re.compile(
        r"^(?:aviso de )?pagamento|pagamento de (?:juros|remuneracao|amortizac|premio|principal)"
    ),
}
# temas de aperto de crédito: o pedido de *waiver* só conta quando não é para vender, reorganizar ou
# abrir o capital da empresa, nem o prêmio (*waiver fee*) de uma oferta de resgate; no aviso, repactuação é a programada na escritura, e só vencimento e inadimplemento contam
ESTRESSE = ("vencimento_antecipado", "covenant", "repactuacao", "inadimplemento")
ESTRESSE_NO_AVISO = ("vencimento_antecipado", "inadimplemento")

_ORDINAIS = [
    "primeira",
    "segunda",
    "terceira",
    "quarta",
    "quinta",
    "sexta",
    "setima",
    "oitava",
    "nona",
]
# "décima segunda emissão" → 12; do mais longo ao mais curto, para "decima primeira" vencer "decima"
_POR_EXTENSO = sorted(
    [
        *[(o, i + 1) for i, o in enumerate(_ORDINAIS)],
        ("decima", 10),
        *[(f"decima {o}", 11 + i) for i, o in enumerate(_ORDINAIS)],
        ("vigesima", 20),
    ],
    key=lambda par: -len(par[0]),
)
_VALOR_POR_EXTENSO = dict(_POR_EXTENSO)
EMISSAO = re.compile(
    r"\b(?:(?P<numero>\d{1,3})\s*[ao]?|(?P<extenso>"
    + "|".join(p for p, _ in _POR_EXTENSO)
    + r"))\s+emiss"
)

COLUNAS = (
    "cnpj",
    "empresa",
    "codigo_cvm",
    "documento",
    "especie",
    "assunto",
    "emissao",
    *(f"tema_{t}" for t in TEMAS),
    "estresse",
    "generico",
    "referencia",
    "publico_em",
    "protocolo",
    "versao",
    "link",
)
ORDEM = ["publico_em", "protocolo", "versao"]
PASTA_DA_TABELA = "debentures_assembleias"


def emissao_do_assunto(assunto: str) -> int | None:
    """O número da emissão citada no assunto, ou None se não há nenhuma ou se há mais de uma."""
    numeros = {
        int(a["numero"]) if a["numero"] else _VALOR_POR_EXTENSO[a["extenso"]]
        for a in EMISSAO.finditer(simples(assunto))
    }
    return numeros.pop() if len(numeros) == 1 else None


def _documento(bruto: pd.DataFrame) -> pd.Series:
    categoria, tipo = bruto["Categoria"].map(simples), bruto["Tipo"].map(simples)
    escolha = pd.Series(None, index=bruto.index, dtype=object)
    escolha[(categoria == "assembleia") & (tipo == "agdeb")] = ASSEMBLEIA
    escolha[categoria == "aviso aos debenturistas"] = AVISO
    escolha[tipo == "notificacao do agente fiduciario aos debenturistas"] = NOTIFICACAO
    return escolha


def _temas(assuntos: pd.Series, documento: pd.Series) -> pd.DataFrame:
    sem_acento = assuntos.map(simples)
    temas = pd.DataFrame(
        {f"tema_{t}": sem_acento.str.contains(rx) for t, rx in TEMAS.items()},
        index=assuntos.index,
    )
    no_aviso = documento == AVISO
    aperto = temas[[f"tema_{t}" for t in ESTRESSE]].any(axis=1) | (
        temas["tema_waiver"] & ~temas["tema_reorganizacao"] & ~temas["tema_resgate"]
    )
    aperto_no_aviso = temas[[f"tema_{t}" for t in ESTRESSE_NO_AVISO]].any(axis=1)
    temas["estresse"] = aperto.where(~no_aviso, aperto_no_aviso)
    temas["generico"] = ~temas[[f"tema_{t}" for t in TEMAS]].any(axis=1)
    return temas


def documentos_de_debenturistas(
    bruto: pd.DataFrame, ate: date | None = None
) -> pd.DataFrame:
    """Uma linha por versão entregue de cada assembleia de debenturistas (`AGDEB`), aviso aos
    debenturistas e notificação do agente fiduciário do IPE, com os temas lidos do assunto. `ate`: a
    base como era nesse dia (nada entregue depois)."""
    documento = _documento(bruto)
    linhas = bruto[documento.notna()]
    documento = documento[documento.notna()]
    protocolo = linhas["Protocolo_Entrega"].str.strip()
    tabela = pd.concat(
        [
            pd.DataFrame(
                {
                    "cnpj": linhas["CNPJ_Companhia"].str.strip(),
                    "empresa": linhas["Nome_Companhia"].str.strip(),
                    "codigo_cvm": linhas["Codigo_CVM"].str.strip(),
                    "documento": documento,
                    "especie": linhas["Especie"].str.strip(),
                    "assunto": linhas["Assunto"].str.strip(),
                    "emissao": linhas["Assunto"]
                    .map(emissao_do_assunto)
                    .astype("Int64"),
                }
            ),
            _temas(linhas["Assunto"], documento),
            pd.DataFrame(
                {
                    "referencia": pd.to_datetime(
                        linhas["Data_Referencia"], errors="coerce"
                    ).dt.date,
                    "publico_em": pd.to_datetime(
                        linhas["Data_Entrega"], errors="coerce"
                    ).dt.date,
                    # de 2003 a 2014 o protocolo vem vazio: o link identifica o documento
                    "protocolo": protocolo.where(
                        protocolo != "", linhas["Link_Download"]
                    ),
                    "versao": pd.to_numeric(linhas["Versao"], errors="coerce").astype(
                        "Int64"
                    ),
                    "link": linhas["Link_Download"].map(link_da_fonte),
                }
            ),
        ],
        axis=1,
    ).loc[:, list(COLUNAS)]
    tabela = tabela.dropna(subset=["publico_em", "link"]).drop_duplicates("link")
    if ate is not None:
        tabela = tabela[tabela["publico_em"] <= ate]
    return tabela.sort_values(ORDEM, kind="stable").reset_index(drop=True)


# --- montagem pelo acervo (servidor de casa) -----------------------------------------------------
def montar(conexao: sa.Connection, pasta: Path, agora: datetime) -> dict[str, int]:
    """`<pasta>/debentures_assembleias/debentures_assembleias.parquet` com todos os arquivos anuais do
    IPE guardados; devolve quantos documentos, quantos com estresse e quantos genéricos. Remontada
    inteira a cada rodada (`gravar_se_mudou` só regrava o que mudou; o passado que muda vira `.vN`)."""
    anuais = [
        o
        for o in originais_mais_recentes(conexao, FONTE_DO_IPE)
        if "ipe_cia_aberta_" in o.url
    ]
    partes = [
        documentos_de_debenturistas(ler_ipe_bruto(conteudo)).assign(
            origem_sha256=o.sha256,
            origem_coletada_em=pd.Timestamp(o.baixado_em).isoformat(),
        )
        for o in anuais
        if (conteudo := acervo.ler_original(o.caminho_do_original))
    ]
    colunas = [*COLUNAS, "origem_sha256", "origem_coletada_em"]
    tabela = (
        pd.concat(partes, ignore_index=True).drop_duplicates("link")
        if partes
        else pd.DataFrame(columns=colunas)
    )
    tabela = tabela.sort_values(ORDEM, kind="stable").reset_index(drop=True)
    gravar_se_mudou(
        tabela.assign(
            montado_em=agora.isoformat(), versao_do_codigo=versao_do_codigo()
        ),
        pasta / PASTA_DA_TABELA / PASTA_DA_TABELA,
        [{"url": o.url, "sha256": o.sha256} for o in anuais],
        ORDEM,
        carimbos=LINHAGEM,
    )
    return {
        "documentos": len(tabela),
        "estresse": int(tabela["estresse"].sum()) if len(tabela) else 0,
        "generico": int(tabela["generico"].sum()) if len(tabela) else 0,
    }
