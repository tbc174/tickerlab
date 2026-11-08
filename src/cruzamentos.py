"""Cruzamentos que um analista não pensaria em pedir: o bloco comum da ficha e do relatório do setor.

Item 5 da lista do lançamento (plano dos relatórios v2, seção "Cruzamentos"). Cada cruzamento é uma
função que lê as seções da ficha da noite (`src.dossie.Ficha`) e devolve um `Cruzamento`: o achado
escrito por uma regra fixa, com a data e a fonte, ou "sem achado" dizendo o que foi olhado. Nada aqui
chama modelo de texto (ADR 0100: fonte em cada frase) nem recomenda coisa alguma.

Os catorze de hoje: fundos entrando e saindo, número refeito no balanço seguinte, troca de auditor,
gente de dentro comprando e vendendo (só o agregado, sem nomes: ADR 0103), remuneração da diretoria
subindo em ano de lucro menor, dividendo acima do lucro, parecer com ressalva ou dúvida de continuidade,
rating rebaixado, assembleias de debenturistas de aperto e aumento de capital com dividendo no mesmo
exercício (plano "mais cruzamentos da base", 29/10/2026). Depois da virada de 5/11/2026, que liberou a
dívida ativa da PGFN e os rótulos de atraso (`docs/virada-empresas-fechadas.md`), mais quatro (7/11/2026):
dívida ativa com a União em cobrança e dividendo pago, DFP entregue atrasada e refeita depois,
dividendo pago com fluxo de caixa livre negativo e lucro sem caixa operacional em dois exercícios
seguidos. Estes leem o dividendo pago na DFC: o FRE de 2023 em diante não traz mais a distribuição.

Sem olhar o futuro: `hoje` corta tudo o que tem data depois dele; o resultado de uma data passada é o
mesmo se a ficha trouxer linhas de depois.

O mesmo bloco serve ao relatório do setor: `cruzamentos_do_setor` soma, por cruzamento, quantas
companhias têm achado. Tipos simples (texto, número, data ISO), prontos para virar JSON.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date
from typing import Any

from src.dossie import Ficha, SecaoDaFicha, agencia_de_rating, dia, para_data, reais
from src.relatorio_empresa import Dossie, Secao

SECAO_DE_CAPITAL = "capital_e_acionistas"
SECAO_DE_QUALIDADE = "qualidade_do_lucro"
SECAO_DO_AUDITOR = "auditor_e_controladas"
SECAO_DE_GOVERNANCA = "governanca"
SECAO_DE_CREDITO = "credito"

PARTICIPACAO_RELEVANTE = (
    0.25  # saldo de 25% ou mais do volume negociado vira "entrando" ou "saindo"
)
PREDOMINIO_DOS_INSIDERS = (
    0.75  # um lado com 75% ou mais do valor negociado por insiders predomina
)
ANOS_DA_TROCA_RECENTE = 3  # auditor trocado há menos que isto vira achado
QUEDA_DO_LUCRO = (
    0.20  # lucro 20% menor que o do exercício anterior conta como "ano de lucro menor"
)
ANOS_DO_CREDITO_RECENTE = (
    2  # rating e assembleias de debenturistas: só os últimos 24 meses
)
TOLERANCIA_ZERO = 0.0

FUNDOS, REFEITO, AUDITOR, INSIDERS = "fundos", "refeito", "auditor", "insiders"
REMUNERACAO, DIVIDENDO, PARECER = "remuneracao", "dividendo", "parecer"
RATING, DEBENTURISTAS, CAPITAL_E_DIVIDENDO = (
    "rating",
    "debenturistas",
    "capital_e_dividendo",
)
DIVIDA_E_DIVIDENDO, ATRASO_E_REFEITO = "divida_e_dividendo", "atraso_e_refeito"
CAIXA_E_DIVIDENDO, LUCRO_SEM_CAIXA = "caixa_e_dividendo", "lucro_sem_caixa"
TITULOS = {
    FUNDOS: "Fundos entrando e saindo",
    REFEITO: "Número refeito depois de publicado",
    AUDITOR: "Troca de auditor",
    INSIDERS: "Gente de dentro comprando e vendendo (agregado)",
    REMUNERACAO: "Remuneração da diretoria subiu em ano de lucro menor",
    DIVIDENDO: "Dividendo acima do lucro",
    PARECER: "Parecer do auditor com ressalva ou dúvida de continuidade",
    RATING: "Rating rebaixado",
    DEBENTURISTAS: "Assembleias de debenturistas de aperto",
    CAPITAL_E_DIVIDENDO: "Aumento de capital e dividendo no mesmo exercício",
    DIVIDA_E_DIVIDENDO: "Dívida ativa com a União em cobrança e dividendo pago",
    ATRASO_E_REFEITO: "Balanço entregue atrasado e refeito depois",
    CAIXA_E_DIVIDENDO: "Dividendo pago com fluxo de caixa livre negativo",
    LUCRO_SEM_CAIXA: "Lucro sem caixa operacional em dois exercícios seguidos",
}


@dataclass(frozen=True)
class Cruzamento:
    chave: str
    titulo: str
    achado: bool
    frase: str  # o achado, ou o que foi olhado quando não há
    medido_em: str | None  # data ISO do dado mais recente usado
    fontes: tuple[str, ...]
    numeros: Mapping[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class CruzamentoDoSetor:
    chave: str
    titulo: str
    com_achado: int
    avaliadas: int  # companhias que tinham o dado do cruzamento
    frase: str
    empresas: tuple[str, ...]  # as que têm achado
    fontes: tuple[str, ...]


def _secao(ficha: Ficha, chave: str) -> SecaoDaFicha | None:
    return next((s for s in ficha.secoes if s.chave == chave), None)


def _ate_hoje(
    linhas: Sequence[Mapping[str, Any]], coluna: str, hoje: date
) -> list[Mapping[str, Any]]:
    """As linhas da tabela cuja data não passa de `hoje` (as sem data ficam de fora)."""
    return [
        linha
        for linha in linhas
        if linha.get(coluna) and para_data(linha[coluna]) <= hoje
    ]


def _sem_achado(
    chave: str, frase: str, fontes: Sequence[str] = (), medido_em: str | None = None
) -> Cruzamento:
    return Cruzamento(chave, TITULOS[chave], False, frase, medido_em, tuple(fontes))


def _cruzamento(
    chave: str,
    achado: bool,
    frase: str,
    medido_em: str | None,
    fontes: Sequence[str],
    numeros: Mapping[str, float] | None = None,
) -> Cruzamento:
    return Cruzamento(
        chave, TITULOS[chave], achado, frase, medido_em, tuple(fontes), numeros or {}
    )


def _ultima_data(linhas: Sequence[Mapping[str, Any]], coluna: str) -> str:
    return max(str(linha[coluna])[:10] for linha in linhas)


def _ha_anos(hoje: date, anos: int) -> date:
    """O mesmo dia `anos` anos antes (29 de fevereiro cai em 28)."""
    try:
        return hoje.replace(year=hoje.year - anos)
    except ValueError:
        return hoje.replace(year=hoje.year - anos, day=28)


def _recentes(
    linhas: Sequence[Mapping[str, Any]], coluna: str, hoje: date
) -> list[Mapping[str, Any]]:
    """As linhas dos últimos `ANOS_DO_CREDITO_RECENTE` anos até hoje."""
    desde = _ha_anos(hoje, ANOS_DO_CREDITO_RECENTE)
    return [linha for linha in linhas if para_data(linha[coluna]) > desde]


def _porcento(variacao: float) -> str:
    return f"{variacao * 100:+.0f}%"


def _plural(quantos: int, singular: str, plural: str) -> str:
    return f"{quantos} {singular if quantos == 1 else plural}"


def _saldo_e_volume(compras: float, vendas: float) -> tuple[float, float]:
    return compras - vendas, compras + vendas


# --- fundos entrando e saindo --------------------------------------------------------------------


def _sentido_dos_fundos(
    atual: tuple[float, float], anterior: tuple[float, float]
) -> str:
    """ "entrando", "saindo", "virada" ou "" (sem achado), pelo saldo e pelo volume dos 12 meses."""
    saldo, volume = _saldo_e_volume(*atual)
    saldo_antes, _ = _saldo_e_volume(*anterior)
    if volume <= TOLERANCIA_ZERO:
        return ""
    if saldo * saldo_antes < 0:
        return "virada"
    if abs(saldo) / volume >= PARTICIPACAO_RELEVANTE:
        return "entrando" if saldo > 0 else "saindo"
    return ""


def fundos(ficha: Ficha, hoje: date) -> Cruzamento:
    """Os fundos compraram ou venderam mais que o outro lado nos 12 meses, contra os 12 anteriores."""
    secao = _secao(ficha, SECAO_DE_CAPITAL)
    linhas = (
        _ate_hoje(secao.tabelas.get("fundos_janelas", []), "ate", hoje) if secao else []
    )
    if secao is None or len(linhas) < 2:
        return _sem_achado(
            FUNDOS, "Sem as duas janelas de 12 meses das carteiras dos fundos."
        )
    linhas = sorted(linhas, key=lambda linha: str(linha["ate"]), reverse=True)
    agora, antes = linhas[0], linhas[1]
    atual = (float(agora["compras"]), float(agora["vendas"]))
    anterior = (float(antes["compras"]), float(antes["vendas"]))
    saldo, _ = _saldo_e_volume(*atual)
    saldo_antes, _ = _saldo_e_volume(*anterior)
    numeros = {
        "compras": atual[0],
        "vendas": atual[1],
        "saldo": saldo,
        "saldo_anterior": saldo_antes,
    }
    quando = str(agora["ate"])[:10]
    sentido = _sentido_dos_fundos(atual, anterior)
    base = (
        f"Os fundos compraram {reais(atual[0])} e venderam {reais(atual[1])} da ação nos 12 meses "
        f"até {dia(quando)} (saldo de {reais(saldo)}); nos 12 meses anteriores o saldo foi de "
        f"{reais(saldo_antes)}."
    )
    if not sentido:
        return Cruzamento(
            FUNDOS,
            TITULOS[FUNDOS],
            False,
            f"Sem achado. {base}",
            quando,
            tuple(secao.fontes),
            numeros,
        )
    titulo = {
        "entrando": "Fundos entrando",
        "saindo": "Fundos saindo",
        "virada": "Fundos viraram o saldo",
    }[sentido]
    return Cruzamento(
        FUNDOS,
        TITULOS[FUNDOS],
        True,
        f"{titulo}. {base}",
        quando,
        tuple(secao.fontes),
        numeros,
    )


# --- número refeito no balanço seguinte ----------------------------------------------------------


def refeito(ficha: Ficha, hoje: date) -> Cruzamento:
    """Lucro ou receita refeitos depois de publicados, e o release que difere do oficial."""
    secao = _secao(ficha, SECAO_DE_QUALIDADE)
    if secao is None:
        return _sem_achado(
            REFEITO, "Sem as demonstrações como eram na época para comparar."
        )
    refeitos = _ate_hoje(secao.tabelas.get("reapresentacoes", []), "trocado_em", hoje)
    itens = {
        item.chave: item
        for item in secao.itens
        if item.base and para_data(item.base) <= hoje
    }
    olhados = (
        int(itens["exercicios_olhados"].valor or 0)
        if "exercicios_olhados" in itens
        else 0
    )
    diferentes = (
        int(itens["releases_diferentes"].valor or 0)
        if "releases_diferentes" in itens
        else 0
    )
    fontes = tuple(secao.fontes)
    if not refeitos and not diferentes:
        if not olhados:
            return _sem_achado(
                REFEITO, "Sem exercícios publicados para comparar.", fontes
            )
        return _sem_achado(
            REFEITO,
            f"Sem achado. Nenhum dos {olhados} exercícios olhados teve lucro ou receita refeitos depois de publicado.",
            fontes,
            max(item.base for item in itens.values() if item.base),
        )
    partes = []
    if refeitos:
        exercicios = sorted({int(linha["exercicio"]) for linha in refeitos})
        ultima = max(str(linha["trocado_em"])[:10] for linha in refeitos)
        partes.append(
            f"{len(exercicios)} de {olhados} exercícios olhados tiveram lucro ou receita refeitos "
            f"depois de publicados (última troca em {dia(ultima)})."
        )
    if diferentes:
        partes.append(f"{diferentes} valores do release diferem do oficial na CVM.")
    quando = max(item.base for item in itens.values() if item.base)
    numeros = {
        "exercicios_refeitos": float(len({linha["exercicio"] for linha in refeitos})),
        "releases_diferentes": float(diferentes),
    }
    return Cruzamento(
        REFEITO, TITULOS[REFEITO], True, " ".join(partes), quando, fontes, numeros
    )


# --- troca de auditor ----------------------------------------------------------------------------


def auditor(ficha: Ficha, hoje: date) -> Cruzamento:
    """Auditor trocado há menos de `ANOS_DA_TROCA_RECENTE` anos (as firmas; pessoa física já vem mascarada)."""
    secao = _secao(ficha, SECAO_DO_AUDITOR)
    if secao is None:
        return _sem_achado(AUDITOR, "Sem o histórico de auditores para comparar.")
    trocas = _ate_hoje(secao.tabelas.get("trocas_de_auditor", []), "efetiva_em", hoje)
    fontes = tuple(secao.fontes)
    if not trocas:
        return _sem_achado(
            AUDITOR, "Sem achado. Nenhuma troca de auditor nas tabelas da base.", fontes
        )
    ultima = max(trocas, key=lambda linha: str(linha["efetiva_em"]))
    quando = str(ultima["efetiva_em"])[:10]
    anos = (hoje - para_data(quando)).days / 365.25
    if anos >= ANOS_DA_TROCA_RECENTE:
        return Cruzamento(
            AUDITOR, TITULOS[AUDITOR], False,
            f"Sem achado. A última troca de auditor foi em {dia(quando)}, há mais de {ANOS_DA_TROCA_RECENTE} anos.",
            quando, fontes, {"trocas": float(len(trocas))},
        )  # fmt: skip
    com = ultima.get("anos_com_o_anterior")
    depois_de = (
        f", depois de {float(com):.0f} anos com o anterior" if com is not None else ""
    )
    frase = (
        f"O auditor passou de {ultima['anterior']} para {ultima['novo']} em {dia(quando)}{depois_de} "
        f"(há menos de {ANOS_DA_TROCA_RECENTE} anos)."
    )
    return Cruzamento(
        AUDITOR,
        TITULOS[AUDITOR],
        True,
        frase,
        quando,
        fontes,
        {"trocas": float(len(trocas))},
    )


# --- gente de dentro comprando e vendendo --------------------------------------------------------


def insiders(ficha: Ficha, hoje: date) -> Cruzamento:
    """Compras e vendas declaradas por administradores e controladores, somadas (nunca por pessoa)."""
    secao = _secao(ficha, SECAO_DE_CAPITAL)
    linhas = (
        _ate_hoje(secao.tabelas.get("insiders_janelas", []), "ate", hoje)
        if secao
        else []
    )
    if secao is None or not linhas:
        return _sem_achado(
            INSIDERS, "Sem declarações de negociação dos insiders para somar."
        )
    agora = max(linhas, key=lambda linha: str(linha["ate"]))
    compras, vendas = float(agora["compras"]), float(agora["vendas"])
    quando = str(agora["ate"])[:10]
    fontes = tuple(secao.fontes)
    numeros = {
        "compras": compras,
        "vendas": vendas,
        "negociacoes": float(agora["negociacoes"]),
    }
    base = (
        f"Insiders (agregado, sem nomes) compraram {reais(compras)} e venderam {reais(vendas)} nos "
        f"12 meses até {dia(quando)}, em {int(agora['negociacoes'])} negociações."
    )
    volume = compras + vendas
    if volume <= TOLERANCIA_ZERO:
        return Cruzamento(
            INSIDERS,
            TITULOS[INSIDERS],
            False,
            f"Sem achado. {base}",
            quando,
            fontes,
            numeros,
        )
    if vendas / volume >= PREDOMINIO_DOS_INSIDERS:
        return Cruzamento(
            INSIDERS,
            TITULOS[INSIDERS],
            True,
            f"Predominam as vendas. {base}",
            quando,
            fontes,
            numeros,
        )
    if compras / volume >= PREDOMINIO_DOS_INSIDERS:
        return Cruzamento(
            INSIDERS,
            TITULOS[INSIDERS],
            True,
            f"Predominam as compras. {base}",
            quando,
            fontes,
            numeros,
        )
    return Cruzamento(
        INSIDERS,
        TITULOS[INSIDERS],
        False,
        f"Sem achado. {base}",
        quando,
        fontes,
        numeros,
    )


# --- remuneração da diretoria em ano de lucro menor ----------------------------------------------


def _por_exercicio(
    secao: SecaoDaFicha | None, tabela: str, data: str, hoje: date, valor: str
) -> dict[int, Mapping[str, Any]]:
    """As linhas já públicas de uma tabela por exercício, pelo ano (`exercicio`), só as que têm o
    `valor` (a ficha traz vazio quando a DFP não tem a linha: vazio não vira zero nem quebra a conta)."""
    if secao is None:
        return {}
    linhas = _ate_hoje(secao.tabelas.get(tabela, []), data, hoje)
    return {
        int(linha["exercicio"]): linha
        for linha in linhas
        if linha.get(valor) is not None
    }


def _lucro_menor(lucro: float, lucro_antes: float) -> bool:
    """Caiu mais de `QUEDA_DO_LUCRO` ou virou prejuízo, partindo de um exercício com lucro."""
    if lucro_antes <= 0:
        return False
    return lucro <= 0 or (lucro - lucro_antes) / lucro_antes <= -QUEDA_DO_LUCRO


def remuneracao(ficha: Ficha, hoje: date) -> Cruzamento:
    """A Diretoria Estatutária ganhou mais no exercício em que o lucro caiu mais de 20% ou virou prejuízo.

    Compara os dois exercícios seguidos mais recentes que têm a remuneração (FRE, total do órgão) e o
    lucro do período (DFP). Só o total do órgão, sem nomes (ADR 0103).
    """
    governanca = _secao(ficha, SECAO_DE_GOVERNANCA)
    qualidade = _secao(ficha, SECAO_DE_QUALIDADE)
    pagos = _por_exercicio(
        governanca,
        "remuneracao_da_diretoria_por_exercicio",
        "conhecido_em",
        hoje,
        "total",
    )
    lucros = _por_exercicio(
        qualidade, "lucro_por_exercicio", "divulgado_em", hoje, "lucro"
    )
    comuns = sorted(set(pagos) & set(lucros), reverse=True)
    if len(comuns) < 2 or comuns[0] - comuns[1] != 1:
        return _sem_achado(
            REMUNERACAO,
            "Sem dois exercícios seguidos com a remuneração da diretoria (FRE) e o lucro (DFP).",
        )
    atual, anterior = comuns[0], comuns[1]
    pago, pago_antes = float(pagos[atual]["total"]), float(pagos[anterior]["total"])
    lucro, lucro_antes = float(lucros[atual]["lucro"]), float(lucros[anterior]["lucro"])
    fontes = tuple(
        dict.fromkeys(
            [
                *(governanca.fontes if governanca else []),
                *(qualidade.fontes if qualidade else []),
            ]
        )
    )
    quando = max(
        str(pagos[atual]["conhecido_em"])[:10], str(lucros[atual]["divulgado_em"])[:10]
    )
    numeros = {
        "remuneracao": pago,
        "remuneracao_anterior": pago_antes,
        "lucro": lucro,
        "lucro_anterior": lucro_antes,
    }
    if lucro_antes:
        numeros["lucro_variacao"] = (lucro - lucro_antes) / abs(lucro_antes)
    if not (pago > pago_antes and _lucro_menor(lucro, lucro_antes)):
        frase = (
            f"Sem achado. A remuneração da Diretoria Estatutária (total do órgão, sem nomes) foi de "
            f"{reais(pago_antes)} em {anterior} e {reais(pago)} em {atual}; o lucro do período, de "
            f"{reais(lucro_antes)} e {reais(lucro)}."
        )
        return _cruzamento(REMUNERACAO, False, frase, quando, fontes, numeros)
    variacao = _porcento(numeros["lucro_variacao"])
    o_lucro = (
        f"virou prejuízo: de {reais(lucro_antes)} para {reais(lucro)} ({variacao})"
        if lucro <= 0
        else f"caiu de {reais(lucro_antes)} para {reais(lucro)} ({variacao})"
    )
    frase = (
        f"A remuneração da Diretoria Estatutária (total do órgão, sem nomes) subiu de {reais(pago_antes)} "
        f"em {anterior} para {reais(pago)} em {atual}, enquanto o lucro do período {o_lucro}."
    )
    return _cruzamento(REMUNERACAO, True, frase, quando, fontes, numeros)


# --- dividendo acima do lucro --------------------------------------------------------------------


def _proventos_publicos(
    secao: SecaoDaFicha | None, hoje: date
) -> list[Mapping[str, Any]]:
    """Os proventos por exercício do FRE já entregue até hoje."""
    if secao is None:
        return []
    return _ate_hoje(
        secao.tabelas.get("proventos_por_exercicio", []), "conhecido_em", hoje
    )


def dividendo(ficha: Ficha, hoje: date) -> Cruzamento:
    """O dividendo declarado sobre o último exercício passou do lucro ajustado, ou houve dividendo com prejuízo."""
    secao = _secao(ficha, SECAO_DE_CAPITAL)
    proventos = [
        linha
        for linha in _proventos_publicos(secao, hoje)
        if linha.get("lucro_ajustado") is not None
        and linha.get("dividendo_total") is not None
    ]
    if secao is None or not proventos:
        return _sem_achado(
            DIVIDENDO, "Sem o lucro ajustado e o dividendo por exercício do FRE."
        )
    ultimo = max(proventos, key=lambda linha: int(linha["exercicio"]))
    exercicio = int(ultimo["exercicio"])
    lucro, pago = float(ultimo["lucro_ajustado"]), float(ultimo["dividendo_total"])
    quando = str(ultimo["conhecido_em"])[:10]
    numeros = {"lucro_ajustado": lucro, "dividendo_total": pago}
    fontes = tuple(secao.fontes)
    if pago <= TOLERANCIA_ZERO or pago <= lucro:
        frase = (
            f"Sem achado. Sobre {exercicio} a companhia declarou {reais(pago)} de dividendos, com lucro "
            f"ajustado de {reais(lucro)} (FRE)."
        )
        return _cruzamento(DIVIDENDO, False, frase, quando, fontes, numeros)
    if lucro <= TOLERANCIA_ZERO:
        frase = (
            f"A companhia declarou {reais(pago)} de dividendos sobre {exercicio}, exercício com prejuízo "
            f"ajustado de {reais(lucro)} (FRE)."
        )
    else:
        frase = (
            f"O dividendo declarado sobre {exercicio}, {reais(pago)}, passou do lucro ajustado do "
            f"exercício, {reais(lucro)} (FRE)."
        )
    return _cruzamento(DIVIDENDO, True, frase, quando, fontes, numeros)


# --- parecer com ressalva ou dúvida de continuidade ----------------------------------------------

OPINIOES_COM_PROBLEMA = {
    "com_ressalva": "veio com ressalva",
    "adversa": "foi adverso",
    "abstencao": "foi uma abstenção de opinião",
}
DUVIDA_DE_CONTINUIDADE = (
    "sim"  # o campo `continuidade_operacional` da tabela `pareceres_dfp`
)


def _problema_do_parecer(linha: Mapping[str, Any]) -> str:
    """O que há de errado no parecer, em palavras ("" quando nada)."""
    partes = []
    opiniao = OPINIOES_COM_PROBLEMA.get(str(linha.get("opiniao")))
    if opiniao:
        partes.append(opiniao)
    if str(linha.get("continuidade_operacional")) == DUVIDA_DE_CONTINUIDADE:
        partes.append("aponta incerteza relevante sobre a continuidade operacional")
    return " e ".join(partes)


def parecer(ficha: Ficha, hoje: date) -> Cruzamento:
    """O relatório do auditor sobre a DFP com ressalva, adverso, abstenção ou dúvida de continuidade."""
    secao = _secao(ficha, SECAO_DO_AUDITOR)
    pareceres = (
        _ate_hoje(secao.tabelas.get("pareceres_do_auditor", []), "disponivel_em", hoje)
        if secao
        else []
    )
    if secao is None or not pareceres:
        return _sem_achado(PARECER, "Sem o relatório do auditor sobre a DFP na base.")
    fontes = tuple(secao.fontes)
    exercicios = {str(linha["referencia"])[:4] for linha in pareceres}
    quantos = _plural(len(exercicios), "parecer", "pareceres")
    com_problema = [linha for linha in pareceres if _problema_do_parecer(linha)]
    numeros = {
        "pareceres": float(len(exercicios)),
        "com_problema": float(len({str(l["referencia"])[:4] for l in com_problema})),
    }
    if not com_problema:
        quando = _ultima_data(pareceres, "disponivel_em")
        frase = (
            f"Sem achado. {quantos} do auditor sobre a DFP, nenhum com ressalva nem dúvida sobre a "
            f"continuidade (o mais recente em {dia(quando)})."
        )
        return _cruzamento(PARECER, False, frase, quando, fontes, numeros)
    ultimo = max(
        com_problema,
        key=lambda linha: (str(linha["referencia"]), int(linha.get("versao") or 0)),
    )
    quando = str(ultimo["disponivel_em"])[:10]
    frase = (
        f"O parecer do auditor sobre a DFP de {str(ultimo['referencia'])[:4]}, público em {dia(quando)}, "
        f"{_problema_do_parecer(ultimo)}."
    )
    return _cruzamento(PARECER, True, frase, quando, fontes, numeros)


# --- rating rebaixado ----------------------------------------------------------------------------

PERSPECTIVA_NEGATIVA = "negativa"


def _piorou(acao: Mapping[str, Any]) -> bool:
    """Rebaixamento, nota pior que a anterior (nível maior: 1 = AAA) ou perspectiva negativa."""
    nivel, anterior = acao.get("nivel"), acao.get("nivel_anterior")
    return (
        str(acao.get("acao")) == "rebaixamento"
        or (
            nivel is not None
            and anterior is not None
            and float(nivel) > float(anterior)
        )
        or str(acao.get("perspectiva")) == PERSPECTIVA_NEGATIVA
    )


def _frase_da_acao(acao: Mapping[str, Any]) -> str:
    agencia = agencia_de_rating(acao["agencia"])
    quando = dia(acao["publico_em"])
    negativa = str(acao.get("perspectiva")) == PERSPECTIVA_NEGATIVA
    anterior = acao.get("nota_anterior")
    if str(acao.get("acao")) == "rebaixamento" or (
        acao.get("nivel") is not None
        and acao.get("nivel_anterior") is not None
        and float(acao["nivel"]) > float(acao["nivel_anterior"])
    ):
        de = f" de {anterior}" if anterior else ""
        com = ", com perspectiva negativa" if negativa else ""
        return f"A {agencia} rebaixou a nota{de} para {acao['nota']} em {quando}{com}."
    return f"A {agencia} manteve a nota {acao['nota']} com perspectiva negativa em {quando}."


def rating(ficha: Ficha, hoje: date) -> Cruzamento:
    """Alguma agência rebaixou a nota ou pôs perspectiva negativa nos últimos 24 meses (opinião da agência, com data)."""
    secao = _secao(ficha, SECAO_DE_CREDITO)
    acoes = (
        _ate_hoje(secao.tabelas.get("acoes_de_rating", []), "publico_em", hoje)
        if secao
        else []
    )
    if secao is None or not acoes:
        return _sem_achado(RATING, "Sem ações de agências de rating na base.")
    fontes = tuple(secao.fontes)
    recentes = _recentes(acoes, "publico_em", hoje)
    pioras = [acao for acao in recentes if _piorou(acao)]
    numeros = {"acoes_24m": float(len(recentes)), "pioras_24m": float(len(pioras))}
    if not pioras:
        quando = _ultima_data(acoes, "publico_em")
        frase = (
            f"Sem achado. {_plural(len(recentes), 'ação', 'ações')} de agências de rating nos últimos "
            f"24 meses, nenhuma rebaixando a nota nem com perspectiva negativa (a última em {dia(quando)})."
        )
        return _cruzamento(RATING, False, frase, quando, fontes, numeros)
    ultima = max(pioras, key=lambda acao: str(acao["publico_em"]))
    quando = str(ultima["publico_em"])[:10]
    varias = (
        f"{len(pioras)} ações de agências pioraram a nota ou a perspectiva nos últimos 24 meses; a última: "
        if len(pioras) > 1
        else ""
    )
    return _cruzamento(
        RATING, True, f"{varias}{_frase_da_acao(ultima)}", quando, fontes, numeros
    )


# --- assembleias de debenturistas de aperto ------------------------------------------------------

APERTO = "waiver, covenant, vencimento antecipado ou repactuação"


def debenturistas(ficha: Ficha, hoje: date) -> Cruzamento:
    """Assembleias de debenturistas marcadas como aperto de crédito pelo assunto, nos últimos 24 meses."""
    secao = _secao(ficha, SECAO_DE_CREDITO)
    aperto = (
        _ate_hoje(secao.tabelas.get("assembleias_de_aperto", []), "publico_em", hoje)
        if secao
        else []
    )
    if secao is None or not aperto:
        return _sem_achado(
            DEBENTURISTAS, "Sem assembleias de debenturistas de aperto na base."
        )
    fontes = tuple(secao.fontes)
    recentes = _recentes(aperto, "publico_em", hoje)
    ultima = max(aperto, key=lambda linha: str(linha["publico_em"]))
    quando = str(ultima["publico_em"])[:10]
    numeros = {"assembleias": float(len(recentes))}
    if not recentes:
        frase = (
            f"Sem achado. A última assembleia de debenturistas de aperto ({APERTO}) foi em {dia(quando)}, "
            f"há mais de 24 meses."
        )
        return _cruzamento(DEBENTURISTAS, False, frase, quando, fontes, numeros)
    frase = (
        f"{_plural(len(recentes), 'assembleia', 'assembleias')} de debenturistas de aperto ({APERTO}) "
        f"nos últimos 24 meses; a última, em {dia(quando)}: {ultima.get('assunto') or 'sem assunto'}."
    )
    return _cruzamento(DEBENTURISTAS, True, frase, quando, fontes, numeros)


# --- aumento de capital e dividendo no mesmo exercício -------------------------------------------

AUMENTO_DE_CAPITAL = "aumento"  # o `tipo` do evento na tabela `eventos_de_capital`


def _valor_dos_aumentos(aumentos: Sequence[Mapping[str, Any]]) -> tuple[float, str]:
    """A soma dos valores informados e como escrevê-la (o FRE nem sempre traz o valor)."""
    informados = [float(a["valor"]) for a in aumentos if a.get("valor") is not None]
    soma = sum(informados)
    if not informados:
        return soma, "sem valor informado"
    if len(informados) < len(aumentos):
        return soma, f"{reais(soma)} nos que informam valor"
    return soma, reais(soma)


def capital_e_dividendo(ficha: Ficha, hoje: date) -> Cruzamento:
    """A companhia aumentou o capital e declarou dividendo sobre o mesmo exercício (o mais recente do FRE)."""
    secao = _secao(ficha, SECAO_DE_CAPITAL)
    proventos = [
        linha
        for linha in _proventos_publicos(secao, hoje)
        if linha.get("dividendo_total") is not None
    ]
    if secao is None or not proventos:
        return _sem_achado(
            CAPITAL_E_DIVIDENDO,
            "Sem o dividendo por exercício do FRE para cruzar com os eventos de capital.",
        )
    ultimo = max(proventos, key=lambda linha: int(linha["exercicio"]))
    exercicio = int(ultimo["exercicio"])
    pago = float(ultimo["dividendo_total"])
    quando = str(ultimo["conhecido_em"])[:10]
    eventos = _ate_hoje(secao.tabelas.get("eventos_de_capital", []), "data", hoje)
    aumentos = sorted(
        (
            evento
            for evento in eventos
            if str(evento.get("tipo")) == AUMENTO_DE_CAPITAL
            and para_data(evento["data"]).year == exercicio
        ),
        key=lambda evento: str(evento["data"]),
    )
    valor, valor_escrito = _valor_dos_aumentos(aumentos)
    numeros = {
        "aumentos": float(len(aumentos)),
        "aumento_valor": valor,
        "dividendo_total": pago,
    }
    fontes = tuple(secao.fontes)
    if not aumentos or pago <= TOLERANCIA_ZERO:
        houve = (
            f"houve {_plural(len(aumentos), 'aumento', 'aumentos')} de capital"
            if aumentos
            else "não houve aumento de capital"
        )
        frase = (
            f"Sem achado. Em {exercicio} {houve} e o dividendo declarado sobre o exercício foi de "
            f"{reais(pago)} (FRE)."
        )
        return _cruzamento(CAPITAL_E_DIVIDENDO, False, frase, quando, fontes, numeros)
    datas = ", ".join(dia(evento["data"]) for evento in aumentos)
    frase = (
        f"Em {exercicio} a companhia aumentou o capital ({_plural(len(aumentos), 'aumento', 'aumentos')} "
        f"no FRE, em {datas}; {valor_escrito}) e declarou {reais(pago)} de dividendos sobre o mesmo "
        f"exercício."
    )
    return _cruzamento(CAPITAL_E_DIVIDENDO, True, frase, quando, fontes, numeros)


def _fontes(*secoes: SecaoDaFicha | None) -> tuple[str, ...]:
    """As fontes das seções, na ordem e sem repetir."""
    return tuple(
        dict.fromkeys(f for secao in secoes if secao is not None for f in secao.fontes)
    )


def _soma(linhas: Sequence[Mapping[str, Any]], coluna: str) -> float:
    """A soma da coluna, sem contar o vazio como zero inventado (o vazio só não soma)."""
    return sum(
        float(linha[coluna]) for linha in linhas if linha.get(coluna) is not None
    )


# --- dívida ativa com a União e dividendo pago ---------------------------------------------------

SECAO_DA_DIVIDA = "divida_com_a_uniao"
EM_COBRANCA = "em cobrança"  # o `tipo_situacao` da PGFN: fora dele, garantia, suspensão ou benefício


def _em_cobranca(linha: Mapping[str, Any]) -> bool:
    return str(linha.get("tipo_situacao") or "").strip().lower() == EM_COBRANCA


def divida_e_dividendo(ficha: Ficha, hoje: date) -> Cruzamento:
    """O retrato mais novo da PGFN tem inscrição em cobrança e a companhia pagou dividendos ou JCP num
    exercício que não é posterior ao retrato (a DFC mais recente já divulgada).

    Só conta a inscrição "em cobrança": a garantida, a suspensa por decisão judicial e a com benefício
    fiscal (parcelamento) ficam de fora. O valor é o consolidado na data do retrato, não o saldo de hoje.
    O dividendo vem da DFC, não do FRE: o FRE de 2023 em diante não traz mais a distribuição. A seção
    da ficha já vem sem as linhas de pessoa natural.
    """
    divida = _secao(ficha, SECAO_DA_DIVIDA)
    caixa = _secao(ficha, SECAO_DO_CAIXA)
    pagos = _dividendos_pagos(caixa, hoje)
    if divida is None or not pagos:
        return _sem_achado(
            DIVIDA_E_DIVIDENDO,
            "Sem os retratos da dívida ativa da União (PGFN) e os dividendos pagos na DFC.",
        )
    exercicio = max(pagos)
    pago = pagos[exercicio]
    divulgado = str(
        _caixa_publico(caixa, "divulgado_em", hoje)[exercicio]["divulgado_em"]
    )[:10]
    pagamento = f"{reais(pago)} de dividendos e JCP pagos em {exercicio} (DFC)"
    fontes = _fontes(divida, caixa)
    publicas = _ate_hoje(
        divida.tabelas.get("inscricoes_na_divida_ativa", []), "publico_em", hoje
    )
    if not publicas:
        frase = (
            f"Sem achado. Nenhuma inscrição em dívida ativa da União nos retratos da PGFN públicos até "
            f"{dia(hoje)}; {pagamento}."
        )
        return _cruzamento(DIVIDA_E_DIVIDENDO, False, frase, divulgado, fontes)
    retrato = _ultima_data(publicas, "aconteceu_em")
    do_retrato = [
        linha for linha in publicas if str(linha["aconteceu_em"])[:10] == retrato
    ]
    cobrando = [linha for linha in do_retrato if _em_cobranca(linha)]
    inscricoes, valor = (
        _soma(cobrando, "inscricoes"),
        _soma(cobrando, "valor_consolidado"),
    )
    numeros = {
        "inscricoes_em_cobranca": inscricoes,
        "valor_em_cobranca": valor,
        "inscricoes": _soma(do_retrato, "inscricoes"),
        "dividendos_pagos": pago,
    }
    quando = max(_ultima_data(do_retrato, "publico_em"), divulgado)
    em_cobranca = (
        f"{_plural(int(inscricoes), 'inscrição', 'inscrições')} em cobrança na dívida ativa da "
        f"União ({reais(valor)} de valor consolidado na data do retrato)"
    )
    if (
        inscricoes <= TOLERANCIA_ZERO
        or pago <= TOLERANCIA_ZERO
        or int(retrato[:4]) < exercicio
    ):
        frase = f"Sem achado. O retrato da PGFN de {dia(retrato)} traz {em_cobranca}; {pagamento}."
        return _cruzamento(DIVIDA_E_DIVIDENDO, False, frase, quando, fontes, numeros)
    frase = (
        f"O retrato da PGFN de {dia(retrato)} traz {em_cobranca}, e a companhia teve {pagamento}. "
        f"O retrato não diz se a cobrança é contestada na Justiça."
    )
    return _cruzamento(DIVIDA_E_DIVIDENDO, True, frase, quando, fontes, numeros)


# --- balanço entregue atrasado e refeito depois --------------------------------------------------

SECAO_DAS_ENTREGAS = "entrega_das_demonstracoes"
DFP = "DFP"
# os rótulos de `base.dossie` (ATRASOU, ATRASO_GRAVE_NO_ROTULO): a zona cinzenta, atraso de poucos dias
# úteis que um feriado local pode explicar, não conta
ROTULOS_DE_ATRASO = ("atrasou", "atraso grave")


def _frase_da_atrasada(linha: Mapping[str, Any]) -> str:
    dias = linha.get("dias_uteis_de_atraso")
    contados = (
        ""
        if dias is None
        else f", {_plural(int(dias), 'dia útil', 'dias úteis')} depois do prazo"
    )
    return f"a de {str(linha['referencia'])[:4]} ({linha['rotulo']}{contados})"


def atraso_e_refeito(ficha: Ficha, hoje: date) -> Cruzamento:
    """A DFP de um exercício foi entregue à CVM depois do prazo e teve o lucro ou a receita refeitos."""
    entregas = _secao(ficha, SECAO_DAS_ENTREGAS)
    qualidade = _secao(ficha, SECAO_DE_QUALIDADE)
    dfps = [
        linha
        for linha in (
            _ate_hoje(
                entregas.tabelas.get("entregas_de_dfp_e_itr", []), "publico_em", hoje
            )
            if entregas
            else []
        )
        if str(linha.get("documento")) == DFP
    ]
    if qualidade is None or not dfps:
        return _sem_achado(
            ATRASO_E_REFEITO,
            "Sem as DFPs entregues à CVM com o rótulo de prazo e as demonstrações como eram na época.",
        )
    atrasadas = {
        int(str(linha["referencia"])[:4]): linha
        for linha in dfps
        if str(linha.get("rotulo")) in ROTULOS_DE_ATRASO
    }
    refeitos = _ate_hoje(
        qualidade.tabelas.get("reapresentacoes", []), "trocado_em", hoje
    )
    anos = sorted(set(atrasadas) & {int(linha["exercicio"]) for linha in refeitos})
    quando = max(
        [
            _ultima_data(dfps, "publico_em"),
            *(str(r["trocado_em"])[:10] for r in refeitos),
        ]
    )
    fontes = _fontes(entregas, qualidade)
    numeros = {
        "dfps": float(len(dfps)),
        "atrasadas": float(len(atrasadas)),
        "atrasadas_e_refeitas": float(len(anos)),
    }
    if not anos:
        atraso = (
            f"{_plural(len(atrasadas), 'com atraso', 'com atraso')}, nenhuma refeita depois"
            if atrasadas
            else "nenhuma com atraso"
        )
        frase = (
            f"Sem achado. {_plural(len(dfps), 'DFP entregue', 'DFPs entregues')} à CVM até "
            f"{dia(hoje)}: {atraso}."
        )
        return _cruzamento(ATRASO_E_REFEITO, False, frase, quando, fontes, numeros)
    quais = "; ".join(_frase_da_atrasada(atrasadas[ano]) for ano in anos)
    frase = (
        f"{_plural(len(anos), 'DFP entregue', 'DFPs entregues')} à CVM depois do prazo "
        f"{'teve' if len(anos) == 1 else 'tiveram'} o lucro ou a receita refeitos depois: {quais}."
    )
    return _cruzamento(ATRASO_E_REFEITO, True, frase, quando, fontes, numeros)


# --- caixa livre, caixa operacional, dividendo e lucro -------------------------------------------

SECAO_DO_CAIXA = "geracao_de_caixa"
SEM_EBITDA = (
    "a DFP de {ano} não tem o EBITDA: em bancos e seguradoras ele não sai, e o caixa operacional "
    "deles mistura a intermediação financeira; a regra não olha esse caixa"
)


def _caixa_publico(
    secao: SecaoDaFicha | None, coluna: str, hoje: date
) -> dict[int, Mapping[str, Any]]:
    """Os exercícios da DFP já divulgados até hoje que têm a `coluna` do caixa."""
    return _por_exercicio(secao, "caixa_por_exercicio", "divulgado_em", hoje, coluna)


DFC = "DFC"  # DFC_MI e DFC_MD, os dois métodos da demonstração dos fluxos de caixa
FINANCIAMENTO = "6.03."  # as contas das atividades de financiamento na DFC
# a linha de dividendos ou JCP pagos, como as companhias a escrevem (o mesmo padrão de
# `base.indicadores_de_caixa`); "recebidos" é de quem recebe da investida, não de quem paga
DIVIDENDOS_E_JCP = re.compile(r"dividend|juros sobre (?:o )?capital|jcp|jscp")
RECEBIDOS = re.compile(r"receb")


def _e_dividendo_pago(linha: Mapping[str, Any]) -> bool:
    descricao = str(linha.get("descricao") or "").lower()
    return (
        str(linha.get("demonstracao") or "").startswith(DFC)
        and str(linha.get("conta") or "").startswith(FINANCIAMENTO)
        and linha.get("valor") is not None
        and float(linha["valor"]) < TOLERANCIA_ZERO
        and DIVIDENDOS_E_JCP.search(descricao) is not None
        and RECEBIDOS.search(descricao) is None
    )


def _sem_a_mae(linhas: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """As linhas cuja conta mãe não está entre elas: a mãe e a filha não somam duas vezes."""
    contas = {(linha["exercicio"], str(linha["conta"])) for linha in linhas}
    return [
        linha
        for linha in linhas
        if not any(
            exercicio == linha["exercicio"]
            and str(linha["conta"]).startswith(f"{conta}.")
            for exercicio, conta in contas
        )
    ]


def _dividendos_pagos(secao: SecaoDaFicha | None, hoje: date) -> dict[int, float]:
    """Por exercício da DFP já divulgada até hoje que tem a DFC na ficha: os dividendos e JCP pagos no
    ano, em valor positivo (zero quando a DFC não tem a linha). Sem a DFC do ano, o ano não entra: o
    vazio não vira zero inventado. Um método só por ano (DFC_MD ou DFC_MI): o mesmo pagamento não
    soma duas vezes."""
    publicos = _caixa_publico(secao, "divulgado_em", hoje)
    da_dfc = [
        linha
        for linha in (secao.tabelas.get("dfc_dva_por_exercicio", []) if secao else [])
        if str(linha.get("demonstracao") or "").startswith(DFC)
        and int(linha["exercicio"]) in publicos
    ]
    metodo: dict[int, str] = {}
    for linha in da_dfc:
        ano = int(linha["exercicio"])
        metodo[ano] = min(metodo.get(ano, linha["demonstracao"]), linha["demonstracao"])
    linhas = [
        linha
        for linha in da_dfc
        if linha["demonstracao"] == metodo[int(linha["exercicio"])]
    ]
    pagas = _sem_a_mae([linha for linha in linhas if _e_dividendo_pago(linha)])
    return {
        ano: -sum(
            float(paga["valor"]) for paga in pagas if int(paga["exercicio"]) == ano
        )
        for ano in {int(linha["exercicio"]) for linha in linhas}
    }


def caixa_e_dividendo(ficha: Ficha, hoje: date) -> Cruzamento:
    """A companhia pagou dividendos ou JCP num exercício de fluxo de caixa livre negativo (o mais
    recente que tem os dois). FCF = caixa operacional − capex, da DFP; o pago, das atividades de
    financiamento da DFC (o FRE de 2023 em diante não traz mais a distribuição)."""
    caixa = _secao(ficha, SECAO_DO_CAIXA)
    fluxos = _caixa_publico(caixa, "fcf", hoje)
    pagos = _dividendos_pagos(caixa, hoje)
    comuns = sorted(set(fluxos) & set(pagos), reverse=True)
    if not comuns:
        return _sem_achado(
            CAIXA_E_DIVIDENDO,
            "Sem um exercício com o fluxo de caixa livre e os dividendos pagos na DFC.",
        )
    ano = comuns[0]
    linha, pago = fluxos[ano], pagos[ano]
    if linha.get("ebitda") is None:
        return _sem_achado(
            CAIXA_E_DIVIDENDO, f"Sem achado: {SEM_EBITDA.format(ano=ano)}."
        )
    fcf = float(linha["fcf"])
    operacional, capex = float(linha["caixa_operacional"]), float(linha["capex"])
    quando = str(linha["divulgado_em"])[:10]
    fontes = _fontes(caixa)
    numeros = {
        "fcf": fcf,
        "caixa_operacional": operacional,
        "capex": capex,
        "dividendos_pagos": pago,
    }
    conta = (
        f"caixa operacional de {reais(operacional)} menos capex de {reais(capex)}, DFP"
    )
    if fcf >= TOLERANCIA_ZERO or pago <= TOLERANCIA_ZERO:
        frase = (
            f"Sem achado. Em {ano} o fluxo de caixa livre foi de {reais(fcf)} ({conta}) e os "
            f"dividendos e JCP pagos no ano, {reais(pago)} (DFC)."
        )
        return _cruzamento(CAIXA_E_DIVIDENDO, False, frase, quando, fontes, numeros)
    frase = (
        f"Em {ano} o fluxo de caixa livre foi negativo, {reais(fcf)} ({conta}), e a companhia pagou "
        f"{reais(pago)} de dividendos e JCP no ano (DFC)."
    )
    return _cruzamento(CAIXA_E_DIVIDENDO, True, frase, quando, fontes, numeros)


def _lucro_e_caixa(lucro: float, operacional: float) -> str:
    return f"lucro de {reais(lucro)} e caixa operacional de {reais(operacional)}"


def lucro_sem_caixa(ficha: Ficha, hoje: date) -> Cruzamento:
    """Lucro com caixa operacional negativo em dois exercícios seguidos (os dois mais recentes que têm
    os dois números na DFP). Um ano só pode ser capital de giro de quem cresce; dois seguidos, não."""
    qualidade = _secao(ficha, SECAO_DE_QUALIDADE)
    caixa = _secao(ficha, SECAO_DO_CAIXA)
    lucros = _por_exercicio(
        qualidade, "lucro_por_exercicio", "divulgado_em", hoje, "lucro"
    )
    caixas = _caixa_publico(caixa, "caixa_operacional", hoje)
    comuns = sorted(set(lucros) & set(caixas), reverse=True)
    if len(comuns) < 2 or comuns[0] - comuns[1] != 1:
        return _sem_achado(
            LUCRO_SEM_CAIXA,
            "Sem dois exercícios seguidos com o lucro e o caixa operacional da DFP.",
        )
    atual, anterior = comuns[0], comuns[1]
    if caixas[atual].get("ebitda") is None or caixas[anterior].get("ebitda") is None:
        return _sem_achado(
            LUCRO_SEM_CAIXA, f"Sem achado: {SEM_EBITDA.format(ano=atual)}."
        )
    lucro, lucro_antes = float(lucros[atual]["lucro"]), float(lucros[anterior]["lucro"])
    operacional = float(caixas[atual]["caixa_operacional"])
    operacional_antes = float(caixas[anterior]["caixa_operacional"])
    numeros = {
        "lucro": lucro,
        "caixa_operacional": operacional,
        "lucro_anterior": lucro_antes,
        "caixa_operacional_anterior": operacional_antes,
    }
    quando = max(
        str(lucros[atual]["divulgado_em"])[:10], str(caixas[atual]["divulgado_em"])[:10]
    )
    fontes = _fontes(qualidade, caixa)
    anos = (
        f"em {anterior}, {_lucro_e_caixa(lucro_antes, operacional_antes)}; em {atual}, "
        f"{_lucro_e_caixa(lucro, operacional)} (DFP)"
    )
    sem_caixa = [
        lucro > TOLERANCIA_ZERO > operacional,
        lucro_antes > TOLERANCIA_ZERO > operacional_antes,
    ]
    if not all(sem_caixa):
        frase = f"Sem achado. {anos[0].upper()}{anos[1:]}."
        return _cruzamento(LUCRO_SEM_CAIXA, False, frase, quando, fontes, numeros)
    frase = f"A companhia lucrou sem gerar caixa operacional em dois exercícios seguidos: {anos}."
    return _cruzamento(LUCRO_SEM_CAIXA, True, frase, quando, fontes, numeros)


REGRAS: tuple[Callable[[Ficha, date], Cruzamento], ...] = (
    fundos,
    refeito,
    auditor,
    insiders,
    remuneracao,
    dividendo,
    parecer,
    rating,
    debenturistas,
    capital_e_dividendo,
    divida_e_dividendo,
    atraso_e_refeito,
    caixa_e_dividendo,
    lucro_sem_caixa,
)


def cruzamentos_da_ficha(ficha: Ficha, hoje: date) -> list[Cruzamento]:
    """Os cruzamentos da ficha (`REGRAS`), na mesma ordem sempre (com achado ou "sem achado")."""
    return [regra(ficha, hoje) for regra in REGRAS]


# --- a seção da ficha ----------------------------------------------------------------------------
CHAVE_DA_SECAO = "cruzamentos"
TITULO_DA_SECAO = "Cruzamentos"
SEM_FONTE = "Sem dado da ficha para olhar."
LIMITE_DOS_CRUZAMENTOS = (
    "Os cruzamentos são regras fixas sobre a ficha da noite: fundos, número refeito, auditor e o "
    "agregado dos insiders (sem nomes); a remuneração da Diretoria Estatutária contra o lucro (FRE e "
    "DFP, total do órgão); o dividendo declarado contra o lucro ajustado e o aumento de capital no mesmo "
    "exercício (FRE); o parecer do auditor sobre a DFP; o rating (opinião da agência, com a data) e as "
    "assembleias de debenturistas de aperto (rótulo do TickerLab sobre o assunto que a empresa "
    "escreveu); a dívida ativa com a União em cobrança no retrato mais novo da PGFN (o valor é o da "
    "data do retrato, e a PGFN não diz se a cobrança é contestada); a DFP entregue à CVM depois do "
    "prazo (rótulo do TickerLab sobre o índice da CVM; a zona cinzenta não conta) e refeita depois; o "
    "fluxo de caixa livre e o caixa operacional da DFP contra os dividendos e JCP pagos (DFC) e o "
    "lucro, que não se olham em bancos e seguradoras (sem EBITDA na DFP); a holding que lucra pela "
    "equivalência patrimonial pode receber o caixa das investidas fora do caixa operacional. Mostram o que os dados registram até o dia da ficha, "
    "nunca o que vem depois, e não são recomendação de investimento."
)


def _paragrafo(c: Cruzamento) -> str:
    """O achado (ou o que foi olhado), a data do dado e a fonte: nenhuma frase sem lastro (ADR 0100)."""
    texto = c.frase if c.frase.startswith(c.titulo) else f"{c.titulo}: {c.frase}"
    if not (c.medido_em and c.fontes):
        return f"{texto} {SEM_FONTE}"
    return f"{texto} Dado de {dia(c.medido_em)}. Fonte: {'; '.join(c.fontes)}."


def secao_dos_cruzamentos(ficha: Ficha, hoje: date) -> Secao:
    """Os cruzamentos da ficha como seção do relatório (tela, PDF e API leem os parágrafos)."""
    cruzados = cruzamentos_da_ficha(ficha, hoje)
    return Secao(
        CHAVE_DA_SECAO,
        TITULO_DA_SECAO,
        paragrafos=[_paragrafo(c) for c in cruzados],
    )


def com_os_cruzamentos(dossie: Dossie, ficha: Ficha, hoje: date) -> Dossie:
    """O dossiê com a seção de cruzamentos e o cuidado dela; `hoje` corta o futuro."""
    return replace(
        dossie,
        secoes=[*dossie.secoes, secao_dos_cruzamentos(ficha, hoje)],
        limites=[*dossie.limites, LIMITE_DOS_CRUZAMENTOS],
    )


# --- o relatório do setor ------------------------------------------------------------------------


def _frase_do_setor(titulo: str, com_achado: int, avaliadas: int) -> str:
    if not avaliadas:
        return f"{titulo}: nenhuma companhia do setor tinha o dado para olhar."
    return f"{titulo}: {com_achado} de {avaliadas} companhias do setor com dado têm achado."


def cruzamentos_do_setor(
    fichas: Mapping[str, Ficha], hoje: date
) -> list[CruzamentoDoSetor]:
    """Por cruzamento, quantas companhias do setor (nome → ficha) têm achado.

    Uma companhia sem o dado ("Sem as duas janelas...") não entra na conta das avaliadas: o
    relatório não diz "0 de 12" quando só 3 tinham o que olhar.
    """
    por_empresa = {nome: cruzamentos_da_ficha(f, hoje) for nome, f in fichas.items()}
    resultado = []
    for posicao, regra in enumerate(REGRAS):
        chave = regra.__name__
        achados = {n: c[posicao] for n, c in por_empresa.items() if c[posicao].achado}
        avaliadas = sum(1 for c in por_empresa.values() if c[posicao].medido_em)
        fontes = tuple(
            dict.fromkeys(f for c in por_empresa.values() for f in c[posicao].fontes)
        )
        titulo = TITULOS[chave]
        resultado.append(
            CruzamentoDoSetor(
                chave, titulo, len(achados), avaliadas,
                _frase_do_setor(titulo, len(achados), avaliadas),
                tuple(sorted(achados)), fontes,
            )
        )  # fmt: skip
    return resultado
