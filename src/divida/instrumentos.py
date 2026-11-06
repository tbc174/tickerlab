"""A dívida que um emissor já tem, instrumento por instrumento (`DebtInstrument` do `data_model.md`).

Fonte: as ofertas públicas registradas na CVM (`base/ofertas.py`, ODbL), lidas **só pela porta** e
"como eram" no dia pedido. Duas tabelas:

- `ofertas_antigas` (ICVM 400 e 476, até 2022): trazem emissão, vencimento, atualização monetária e
  juros em texto livre, como a companhia preencheu. Na ICVM 476 quase tudo vem vazio (85% das
  debêntures sem vencimento no arquivo de 15/10/2026);
- `ofertas_resolucao_160` (2023 em diante): só o valor registrado; vencimento e indexador não vêm.

O que a oferta não diz fica **não observado** (None ou `NAO_OBSERVADO`), nunca estimado. CRI e CRA
ficam de fora: o emissor deles é a securitizadora, e o arquivo não diz (sem os textos livres, que
podem citar pessoas) quem é o devedor. Oferta secundária e mista também: não é dívida nova.
"""

import re
from collections import Counter
from dataclasses import asdict, dataclass, replace
from datetime import date

import pandas as pd

from base import cnpj as cnpj_
from base.debentures import simples
from base.ofertas import FONTE, URL
from base.porta import Porta
from src.rastro import DocumentoUsado, Rastro, datas_em_texto

VERSAO_DO_CALCULO = "divida 1"
FORMULA_DO_INSTRUMENTO = "copiado da linha da oferta na CVM, sem conta"
NAO_OBSERVADO = "nao_observado"
MOEDA = "BRL"
TABELA_ANTIGAS, TABELA_160 = "ofertas_antigas", "ofertas_resolucao_160"
PRIMARIA = "primaria"  # `tipo_oferta` sem acento e em minúsculas, nas duas tabelas
ENCERRADA = "oferta encerrada"  # na 160, só a oferta encerrada virou dívida

# o tipo do título como a CVM escreve (sem acento, minúsculas) → o tipo do instrumento
TIPOS: tuple[tuple[str, str], ...] = (
    ("debentures", "debenture"),
    ("notas promissorias", "nota_promissoria"),
    ("notas comerciais", "nota_comercial"),
)

# a ordem importa: a atualização monetária manda (IPCA + juros é IPCA), depois os juros flutuantes
INDEXADOR_NA_ATUALIZACAO: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("ipca", re.compile(r"\bipca\b")),
    ("igpm", re.compile(r"\bigp\s*-?\s*m\b")),
    ("inpc", re.compile(r"\binpc\b")),
)
INDEXADOR_NOS_JUROS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("cdi", re.compile(r"\bc?di\b")),
    ("tjlp", re.compile(r"\btjlp\b")),
    ("selic", re.compile(r"\bselic\b")),
)
SEM_ATUALIZACAO = re.compile(
    r"^(?:nao|nao ha|sem atualizacao(?: monetaria)?|o valor nominal nao sera atualizado)\.?$"
)
TAXA_FIXA = re.compile(
    r"^(?:remuneracao fixa(?: de)?\s*)?\d+(?:[.,]\d+)?\s*%\s*(?:a\.?\s*a\.?|aa|ao ano)?\.?$"
)


@dataclass(frozen=True)
class DebtInstrument:
    """Um título de dívida do emissor, com o que a fonte diz e nada mais (tipos simples, para JSON)."""

    instrumento_id: str
    emissor_cnpj: str  # 14 caracteres, sem pontuação
    emissor_nome: str
    tipo: str  # "debenture", "nota_comercial", "nota_promissoria"
    moeda: str
    valor_emitido: float | None  # em reais; None: a oferta não diz (ou diz zero)
    saldo: (
        float | None
    )  # quanto ainda se deve; a oferta nunca diz (amortização e resgate)
    indexador: (
        str  # "pre", "cdi", "ipca", "igpm", "inpc", "tjlp", "selic" ou NAO_OBSERVADO
    )
    remuneracao: str | None  # o texto da CVM ("IPCA; 6,50% a.a."), como veio
    emissao: date | None
    vencimento: date | None
    numero_da_emissao: str | None
    serie: str | None
    publico_em: date  # quando a linha inteira ficou pública na CVM
    rastro: Rastro

    def como_dict(self) -> dict:
        """Para a API: datas em texto ISO."""
        return {k: datas_em_texto(v) for k, v in asdict(self).items()}


def indexador_por_regra(atualizacao: object, juros: object) -> str:
    """O indexador lido dos dois textos livres da oferta; NAO_OBSERVADO quando a regra não decide.

    Pré só quando a oferta diz que não há atualização **e** os juros são uma taxa fixa: taxa fixa
    sem dizer nada da atualização pode ser IPCA + taxa com a coluna em branco."""
    atualizacao_, juros_ = simples(_texto(atualizacao)), simples(_texto(juros))
    for nome, regra in INDEXADOR_NA_ATUALIZACAO:
        if regra.search(atualizacao_):
            return nome
    for nome, regra in INDEXADOR_NOS_JUROS:
        if regra.search(juros_):
            return nome
    if SEM_ATUALIZACAO.match(atualizacao_) and TAXA_FIXA.match(juros_):
        return "pre"
    return NAO_OBSERVADO


def _texto(valor: object) -> str:
    return "" if valor is None or pd.isna(valor) else str(valor).strip()  # type: ignore[arg-type]


def _ou_none(valor: object) -> str | None:
    return _texto(valor) or None


def _dia(valor: object) -> date | None:
    return None if valor is None or pd.isna(valor) else pd.Timestamp(valor).date()  # type: ignore[arg-type]


def _valor(valor: object) -> float | None:
    if valor is None or pd.isna(valor) or float(valor) <= 0:  # type: ignore[arg-type]
        return None
    return float(valor)  # type: ignore[arg-type]


def _tipo(titulo: object) -> str | None:
    titulo_ = simples(_texto(titulo))
    return next((tipo for prefixo, tipo in TIPOS if titulo_.startswith(prefixo)), None)


def _rastro(nome_do_documento: str, publico_em: date) -> Rastro:
    documento = DocumentoUsado(nome_do_documento, publico_em, URL)
    return Rastro.dos_documentos(
        FORMULA_DO_INSTRUMENTO, VERSAO_DO_CALCULO, FONTE, [documento]
    )


def _da_antiga(linha: pd.Series, cnpj: str) -> DebtInstrument:
    registro = _texto(linha["numero_registro_oferta"]) or _texto(
        linha["numero_processo"]
    )
    emissao, serie = _ou_none(linha["emissao"]), _ou_none(linha["serie"])
    publico_em = _dia(linha["disponivel_em"])
    assert publico_em is not None  # a porta só traz o que tem dia público
    remuneracao = "; ".join(
        t for t in (_texto(linha["atualizacao_monetaria"]), _texto(linha["juros"])) if t
    )
    return DebtInstrument(
        instrumento_id=f"{FONTE}/antigas/{registro}/{emissao}/{serie}",
        emissor_cnpj=cnpj,
        emissor_nome=_texto(linha["nome_emissor"]),
        tipo=_tipo(linha["tipo_ativo"]) or "",
        moeda=MOEDA,
        valor_emitido=_valor(linha["valor_total"]),
        saldo=None,
        indexador=indexador_por_regra(linha["atualizacao_monetaria"], linha["juros"]),
        remuneracao=remuneracao or None,
        emissao=_dia(linha["data_emissao"]),
        vencimento=_dia(linha["data_vencimento"]),
        numero_da_emissao=emissao,
        serie=serie,
        publico_em=publico_em,
        rastro=_rastro(
            f"Oferta {registro} ({_texto(linha['tipo_ativo'])}, emissão {emissao}, "
            f"série {serie}), arquivo de ofertas públicas da CVM",
            publico_em,
        ),
    )


def _da_160(linha: pd.Series, cnpj: str) -> DebtInstrument:
    requerimento = _texto(linha["numero_requerimento"])
    publico_em = _dia(linha["disponivel_em"])
    assert publico_em is not None
    return DebtInstrument(
        instrumento_id=f"{FONTE}/160/{requerimento}",
        emissor_cnpj=cnpj,
        emissor_nome=_texto(linha["nome_emissor"]),
        tipo=_tipo(linha["valor_mobiliario"]) or "",
        moeda=MOEDA,
        valor_emitido=_valor(linha["valor_total_registrado"]),
        saldo=None,
        indexador=NAO_OBSERVADO,  # a 160 não traz atualização nem juros
        remuneracao=None,
        emissao=None,  # o registro da oferta não é a data de emissão do título
        vencimento=None,
        numero_da_emissao=_ou_none(linha["emissao"]),
        serie=None,
        publico_em=publico_em,
        rastro=_rastro(
            f"Requerimento {requerimento} da Resolução CVM 160 "
            f"({_texto(linha['valor_mobiliario'])}), arquivo de ofertas públicas da CVM",
            publico_em,
        ),
    )


def _divida_primaria(
    tabela: pd.DataFrame, coluna_do_titulo: str, cnpj: str
) -> pd.DataFrame:
    """As linhas de dívida nova (título de dívida, oferta primária) deste CNPJ."""
    if tabela.empty:
        return tabela
    do_emissor = tabela["cnpj_emissor"].map(cnpj_.normalizar_cnpj) == cnpj
    primaria = tabela["tipo_oferta"].map(lambda t: simples(_texto(t))) == PRIMARIA
    divida = tabela[coluna_do_titulo].map(_tipo).notna()
    return tabela[do_emissor & primaria & divida]


def _com_ids_unicos(instrumentos: list[DebtInstrument]) -> list[DebtInstrument]:
    """A ICVM 476 não tem chave única: a 2ª linha com o mesmo id ganha "#2", e assim por diante."""
    vistos: Counter[str] = Counter()
    unicos = []
    for instrumento in instrumentos:
        vistos[instrumento.instrumento_id] += 1
        vezes = vistos[instrumento.instrumento_id]
        if vezes > 1:
            instrumento = replace(
                instrumento, instrumento_id=f"{instrumento.instrumento_id}#{vezes}"
            )
        unicos.append(instrumento)
    return unicos


def instrumentos_das_ofertas(
    antigas: pd.DataFrame, novas: pd.DataFrame, cnpj: str
) -> list[DebtInstrument]:
    """Os instrumentos de dívida do CNPJ nas duas tabelas de ofertas, por ordem de publicação."""
    cnpj_normal = cnpj_.normalizar_cnpj(cnpj)
    if cnpj_normal is None:
        raise ValueError(f"{cnpj!r} não é um CNPJ")
    novas = _divida_primaria(novas, "valor_mobiliario", cnpj_normal)
    if not novas.empty:
        novas = novas[
            novas["status_requerimento"].map(lambda s: simples(_texto(s))) == ENCERRADA
        ]
    instrumentos = [
        *(_da_antiga(linha, cnpj_normal) for _, linha in _divida_primaria(antigas, "tipo_ativo", cnpj_normal).iterrows()),
        *(_da_160(linha, cnpj_normal) for _, linha in novas.iterrows()),
    ]  # fmt: skip
    instrumentos.sort(key=lambda i: (i.publico_em, i.instrumento_id))
    return _com_ids_unicos(instrumentos)


def instrumentos_do_emissor(
    porta: Porta, cnpj: str, como_era_em: date
) -> list[DebtInstrument]:
    """A dívida do emissor que já era pública em `como_era_em`, lida pela porta da base."""
    cnpj_normal = cnpj_.normalizar_cnpj(cnpj)
    if cnpj_normal is None:
        raise ValueError(f"{cnpj!r} não é um CNPJ")
    filtro = {"cnpj_emissor": cnpj_.formatar(cnpj_normal)}
    antigas = porta.ler(TABELA_ANTIGAS, como_era_em=como_era_em, filtros=filtro)
    novas = porta.ler(TABELA_160, como_era_em=como_era_em, filtros=filtro)
    return instrumentos_das_ofertas(antigas, novas, cnpj_normal)
