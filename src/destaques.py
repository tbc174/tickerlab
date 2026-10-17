"""Os destaques "O que a base mostra": o que só o cruzamento das fontes revela, em uma frase cada
(plano do relatório-modelo, 17/10/2026, PR 1, tarefa 3).

Cada destaque é um molde fixo (`MOLDES`) com os números da ficha encaixados: nenhuma frase é escrita
por modelo de linguagem (ADR 0028, item 5; ADR 0087). O texto da empresa entra só entre aspas, como
ela escreveu. Sem o dado, o destaque não aparece; nenhum molde julga a empresa (nada é recomendação).
"""

import unicodedata
from collections.abc import Callable
from dataclasses import dataclass

from base import dossie as dossie_da_base
from src.dossie import (
    Ficha,
    SecaoDaFicha,
    decimal,
    dia,
    fracao,
    inteiro,
    mes,
    para_data,
    reais,
)

MOLDES = {
    "fundos": (
        "{fundos} fundos tinham papéis da empresa nas carteiras de {mes}, o último mês com as "
        "carteiras completas na CVM, somando {valor}."
    ),
    "fundos_um_ano_antes": " Doze meses antes eram {fundos} fundos, com {valor}.",
    "ofertas": (
        "Em {ano}, o grupo registrou {ofertas} ofertas na CVM, somando {valor} pelo valor "
        "registrado"
    ),
    "ofertas_emissores": ", emitidas por {emissores} empresas do grupo",
    "auditor": (
        "{novo} audita a companhia desde {ano}. Antes, {anterior} ficou {anos} anos. Foram "
        "{trocas} trocas de auditor desde {primeira}."
    ),
    "setor": "{medida}: {valor} em {base}, {parte} do total da agência.",
    "controladas": (
        "O FRE de {ano} lista {controladas} controladas e {outras} coligada ou outra "
        "participação."
    ),
    "controladas_plural": (
        "O FRE de {ano} lista {controladas} controladas e {outras} coligadas ou outras "
        "participações."
    ),
    "negocios": (
        "A base acha {documentos} fatos relevantes e comunicados da companhia sobre aquisições, "
        "alienações, fusões ou reorganizações. O último, em {data}: “{assunto}”."
    ),
}


TITULOS = {
    "fundos": "Fundos com a empresa",
    "ofertas": "Ofertas do grupo",
    "setor": "Setor regulado",
    "auditor": "Rodízio do auditor",
    "controladas": "Controladas",
    "negocios": "Negócios na CVM",
}


@dataclass(frozen=True)
class Destaque:
    chave: str
    texto: str
    fonte: str  # a licença da fonte (a atribuição que ela pede)
    data: str  # de quando é o dado, já escrito
    secao: str  # a seção da ficha onde está o detalhe
    link: str = ""  # o documento original, quando há um

    @property
    def titulo(self) -> str:
        return TITULOS[self.chave]


def _secao(ficha: Ficha, chave: str) -> SecaoDaFicha | None:
    return next((s for s in ficha.secoes if s.chave == chave), None)


def _fonte(secao: SecaoDaFicha) -> str:
    return secao.fontes[0] if secao.fontes else ""


def _item(secao: SecaoDaFicha, chave: str) -> object:
    return next((i.valor for i in secao.itens if i.chave == chave), None)


def _normalizar(nome: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    return " ".join(
        "".join(c if c.isalnum() else " " for c in sem_acento.upper()).split()
    )


# --- cada destaque ---------------------------------------------------------------------------------


def _fundos(ficha: Ficha) -> Destaque | None:
    secao = _secao(ficha, "ofertas_e_fundos")
    meses = secao.tabelas.get("fundos_por_mes", []) if secao else []
    if not secao or not meses:
        return None
    ultimo = meses[-1]
    texto = MOLDES["fundos"].format(
        fundos=inteiro(ultimo["fundos"]),
        mes=mes(ultimo["competencia"]),
        valor=reais(ultimo["valor"]),
    )
    fim = para_data(ultimo["competencia"])
    antes = next(
        (
            linha
            for linha in meses
            if (
                para_data(linha["competencia"]).year,
                para_data(linha["competencia"]).month,
            )
            == (fim.year - 1, fim.month)
        ),
        None,
    )
    if antes is not None:
        texto += MOLDES["fundos_um_ano_antes"].format(
            fundos=inteiro(antes["fundos"]), valor=reais(antes["valor"])
        )
    return Destaque(
        "fundos", texto, _fonte(secao), mes(ultimo["competencia"]), secao.chave
    )


def _ofertas(ficha: Ficha) -> Destaque | None:
    secao = _secao(ficha, "ofertas_e_fundos")
    if not secao:
        return None
    # o ano corrente ainda não acabou: o último ano completo diz mais
    anos = [
        linha
        for linha in secao.tabelas.get("ofertas_por_ano", [])
        if int(linha["ano"]) < ficha.gerado_em.year
    ]
    if not anos:
        return None
    ano = max(anos, key=lambda linha: int(linha["ano"]))
    texto = MOLDES["ofertas"].format(
        ano=int(ano["ano"]),
        ofertas=inteiro(ano["ofertas"]),
        valor=reais(ano["valor_total"]),
    )
    do_ano = [
        linha
        for linha in secao.tabelas.get("ofertas", [])
        if para_data(linha["data"]).year == int(ano["ano"])
    ]
    # a lista guarda só as últimas ofertas: os emissores só contam se o ano inteiro está nela
    if len(do_ano) == int(ano["ofertas"]):
        emissores = {_normalizar(str(linha["emissor"])) for linha in do_ano}
        texto += MOLDES["ofertas_emissores"].format(emissores=len(emissores))
    return Destaque(
        "ofertas", texto + ".", _fonte(secao), str(int(ano["ano"])), secao.chave
    )


def _setor(ficha: Ficha) -> Destaque | None:
    secao = _secao(ficha, "setor_regulado")
    if not secao:
        return None
    series = [
        (serie, secao.tabelas[serie.nome])
        for serie in dossie_da_base.SERIES_DAS_AGENCIAS
        if secao.tabelas.get(serie.nome)
    ]
    if not series:
        return None
    serie, linhas = max(
        series,
        key=lambda par: max(float(linha["participacao"] or 0) for linha in par[1]),
    )
    recente = max(linhas, key=lambda linha: int(linha["ano"]))
    base = mes(recente["ultimo_mes"])
    texto = MOLDES["setor"].format(
        medida=serie.medida,
        valor=inteiro(recente["valor"]),
        base=base,
        parte=fracao(recente["participacao"]),
    )
    fontes = dossie_da_base.fontes_das_tabelas([serie.tabela])
    return Destaque("setor", texto, fontes[0] if fontes else "", base, secao.chave)


def _auditor(ficha: Ficha) -> Destaque | None:
    secao = _secao(ficha, "auditor_e_controladas")
    trocas = secao.tabelas.get("trocas_de_auditor", []) if secao else []
    if not secao or not trocas:
        return None
    ordem = sorted(trocas, key=lambda linha: str(linha["efetiva_em"]))
    ultima, primeira = ordem[-1], ordem[0]
    texto = MOLDES["auditor"].format(
        novo=ultima["novo"],
        ano=para_data(ultima["efetiva_em"]).year,
        anterior=ultima["anterior"],
        anos=decimal(ultima["anos_com_o_anterior"]),
        trocas=len(ordem),
        primeira=para_data(primeira["efetiva_em"]).year,
    )
    return Destaque(
        "auditor", texto, _fonte(secao), dia(ultima["efetiva_em"]), secao.chave
    )


def _controladas(ficha: Ficha) -> Destaque | None:
    secao = _secao(ficha, "auditor_e_controladas")
    if not secao:
        return None
    controladas = _item(secao, "controladas")
    outras = _item(secao, "coligadas_e_outras")
    base = next((i.base for i in secao.itens if i.chave == "controladas"), None)
    if controladas is None or outras is None or not base:
        return None
    molde = MOLDES["controladas"] if outras == 1 else MOLDES["controladas_plural"]
    ano = para_data(base).year
    texto = molde.format(
        ano=ano, controladas=inteiro(controladas), outras=inteiro(outras)
    )
    return Destaque("controladas", texto, _fonte(secao), f"FRE de {ano}", secao.chave)


def _negocios(ficha: Ficha) -> Destaque | None:
    secao = _secao(ficha, "negocios")
    lista = secao.tabelas.get("negocios", []) if secao else []
    documentos = _item(secao, "negocios") if secao else None
    if not secao or not lista or documentos is None:
        return None
    ultimo = max(lista, key=lambda linha: str(linha["publicado_em"]))
    texto = MOLDES["negocios"].format(
        documentos=inteiro(documentos),
        data=dia(ultimo["publicado_em"]),
        assunto=" ".join(str(ultimo["assunto"]).split()),
    )
    return Destaque(
        "negocios",
        texto,
        _fonte(secao),
        dia(ultimo["publicado_em"]),
        secao.chave,
        str(ultimo.get("link") or ""),
    )


ORDEM: tuple[Callable[[Ficha], Destaque | None], ...] = (
    _fundos,
    _ofertas,
    _setor,
    _auditor,
    _controladas,
    _negocios,
)


def destaques_da_ficha(ficha: Ficha) -> list[Destaque]:
    """Os destaques da ficha (já cortada), na ordem do que é mais difícil de achar sozinho."""
    return [d for montar in ORDEM if (d := montar(ficha)) is not None]
