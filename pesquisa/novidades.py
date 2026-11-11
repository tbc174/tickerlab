"""As novidades da pesquisa (linha 830): as fontes que o bot conferente provou na semana, num arquivo só.

Lê a memória do bot (`Memoria`, tabela `fato`) e monta o `novidades.json`: cada item com o órgão, a data, o
trecho literal e o sha256 do original. Só sai o que tem **prova gravada** (veredito `confirmado`, trecho, hash e
o endereço de onde o original veio) e só de **órgão público da tabela `ORGAOS`**. O trecho é uma citação curta
(`TRECHO_MAXIMO`). Pessoa física: CPF no texto **derruba o exportador** (não descarta calado); marca de pessoa
(tratamento, documento) descarta o item e conta o motivo. O envio do arquivo ao servidor é outro passo.
"""

import json
import sqlite3
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pesquisa.memoria import Memoria
from src.novidades_da_pesquisa import (
    MARCAS_DE_PESSOA,
    TRECHO_MAXIMO,
    achar_cpf,
    cnpjs_validos,
    fonte_liberada,
    orgao_da_url,
)

DIAS_PADRAO = 7
VERSAO = 1

MOTIVO_SEM_PROVA = "sem trecho, hash ou endereço da fonte"
MOTIVO_ORGAO = "domínio fora da tabela de órgãos"
MOTIVO_PESSOA = "marca de pessoa física no texto"
MOTIVO_FORA_DA_JANELA = "fora da janela de dias"
MOTIVO_NAO_CONFIRMADO = "veredito não confirmado"
MOTIVO_REPETIDO = "mesmo original e mesmo trecho já exportados"
MOTIVO_TRECHO_LONGO = "trecho acima do máximo"
MOTIVO_SEM_CNPJ = "sem CNPJ válido na afirmação nem no trecho"
MOTIVO_CNPJ_FORA_DA_LISTA = "CNPJ fora da lista sem pessoa do acervo"
MOTIVO_SEM_REVENDA = "fonte sem licença ou sem revenda liberada"


class CpfNoTrechoError(Exception):
    """Achou algo com cara de CPF: o exportador para, em vez de descartar calado."""


@dataclass
class Exportacao:
    itens: list[dict[str, str]]
    descartados: dict[str, int] = field(default_factory=dict)
    gerado_em: str = ""

    def contar(self, motivo: str) -> None:
        self.descartados[motivo] = self.descartados.get(motivo, 0) + 1

    def para_dict(self) -> dict[str, object]:
        return {"versao": VERSAO, "gerado_em": self.gerado_em, "itens": self.itens}


def _consultar(caminho: Path) -> list[sqlite3.Row]:
    with closing(sqlite3.connect(caminho)) as conexao:
        conexao.row_factory = sqlite3.Row
        return conexao.execute(
            "SELECT f.fato, f.veredito, f.quando, "
            "(SELECT COALESCE(v.url_final, v.url) FROM visto v "
            "WHERE v.sha256 = json_extract(f.fato, '$.sha256') LIMIT 1) AS url "
            "FROM fato f ORDER BY f.quando DESC, f.id DESC"
        ).fetchall()


def _item(fato: dict[str, object], url: str, quando: str) -> dict[str, str]:
    fonte, orgao = orgao_da_url(url) or ("", "")
    return {
        "orgao": orgao,
        "fonte": fonte,
        "fonte_url": url,
        "data": quando[:10],
        "afirmacao": str(fato.get("afirmacao") or ""),
        "trecho": str(fato["trecho"]),
        "sha256": str(fato["sha256"]),
        "posicao": str(fato.get("posicao") or ""),
    }


def _por_que_nao(
    linha: sqlite3.Row,
    fato: dict[str, object],
    corte: str,
    e_empresa: Callable[[str], bool],
) -> str | None:
    if linha["veredito"] != "confirmado":
        return MOTIVO_NAO_CONFIRMADO
    if linha["quando"] < corte:
        return MOTIVO_FORA_DA_JANELA
    url = linha["url"] or ""
    if not (fato.get("trecho") and fato.get("sha256") and url):
        return MOTIVO_SEM_PROVA
    achado = orgao_da_url(url)
    if achado is None:
        return MOTIVO_ORGAO
    if not fonte_liberada(achado[0]):
        return MOTIVO_SEM_REVENDA
    texto = f"{fato.get('afirmacao', '')}\n{fato['trecho']}"
    if achar_cpf(f"{texto}\n{url}\n{fato.get('posicao', '')}"):
        raise CpfNoTrechoError(
            "um trecho confirmado tem cara de CPF: revise a memória do bot antes de exportar"
        )
    if MARCAS_DE_PESSOA.search(texto):
        return MOTIVO_PESSOA
    cnpjs = cnpjs_validos(texto)
    if not cnpjs:
        return MOTIVO_SEM_CNPJ
    if not all(e_empresa(cnpj) for cnpj in cnpjs):
        return MOTIVO_CNPJ_FORA_DA_LISTA
    if len(str(fato["trecho"])) > TRECHO_MAXIMO:
        return MOTIVO_TRECHO_LONGO
    return None


def exportar(
    memoria: Memoria,
    *,
    e_empresa: Callable[[str], bool],
    dias: int = DIAS_PADRAO,
    agora: datetime | None = None,
) -> Exportacao:
    """Os itens provados nos últimos `dias`, mais novos primeiro. CPF no texto levanta `CpfNoTrechoError`.

    `e_empresa(cnpj)` diz se o CNPJ (14 caracteres) está na lista sem pessoa do acervo; só sai o fato cujos
    CNPJs estão todos nela (sem CNPJ válido, não sai). Sem acervo não há como responder: quem chama não exporta."""
    agora = agora or datetime.now(UTC)
    corte = (agora - timedelta(days=dias)).isoformat()
    saida = Exportacao(itens=[], gerado_em=agora.isoformat(timespec="seconds"))
    vistos: set[tuple[str, str]] = set()
    for linha in _consultar(memoria.caminho):
        fato = json.loads(linha["fato"])
        motivo = _por_que_nao(linha, fato, corte, e_empresa)
        chave = (str(fato.get("sha256")), str(fato.get("trecho")))
        if motivo is None and chave in vistos:
            motivo = MOTIVO_REPETIDO
        if motivo is not None:
            saida.contar(motivo)
            continue
        vistos.add(chave)
        saida.itens.append(_item(fato, linha["url"], linha["quando"]))
    return saida


def gravar(exportacao: Exportacao, destino: Path) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(
        json.dumps(exportacao.para_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
