"""Cruzamentos que um analista não pensaria em pedir: o bloco comum da ficha e do relatório do setor.

Item 5 da lista do lançamento (plano dos relatórios v2, seção "Cruzamentos"). Cada cruzamento é uma
função que lê as seções da ficha da noite (`src.dossie.Ficha`) e devolve um `Cruzamento`: o achado
escrito por uma regra fixa, com a data e a fonte, ou "sem achado" dizendo o que foi olhado. Nada aqui
chama modelo de texto (ADR 0100: fonte em cada frase) nem recomenda coisa alguma.

Os quatro de hoje: fundos entrando e saindo, número refeito no balanço seguinte, troca de auditor e
gente de dentro comprando e vendendo (só o agregado, sem nomes: ADR 0103). A dívida ativa de quem cede
recebíveis a FIDC fica de fora: a ADR 0103 a bloqueia até o ponto 9 (direito de resposta), e nada
deste módulo lê `pgfn_divida`.

Sem olhar o futuro: `hoje` corta tudo o que tem data depois dele; o resultado de uma data passada é o
mesmo se a ficha trouxer linhas de depois.

O mesmo bloco serve ao relatório do setor: `cruzamentos_do_setor` soma, por cruzamento, quantas
companhias têm achado. Tipos simples (texto, número, data ISO), prontos para virar JSON.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date
from typing import Any

from src.dossie import Ficha, SecaoDaFicha, dia, para_data, reais
from src.relatorio_empresa import Dossie, Secao

SECAO_DE_CAPITAL = "capital_e_acionistas"
SECAO_DE_QUALIDADE = "qualidade_do_lucro"
SECAO_DO_AUDITOR = "auditor_e_controladas"

PARTICIPACAO_RELEVANTE = (
    0.25  # saldo de 25% ou mais do volume negociado vira "entrando" ou "saindo"
)
PREDOMINIO_DOS_INSIDERS = (
    0.75  # um lado com 75% ou mais do valor negociado por insiders predomina
)
ANOS_DA_TROCA_RECENTE = 3  # auditor trocado há menos que isto vira achado
TOLERANCIA_ZERO = 0.0

FUNDOS, REFEITO, AUDITOR, INSIDERS = "fundos", "refeito", "auditor", "insiders"
TITULOS = {
    FUNDOS: "Fundos entrando e saindo",
    REFEITO: "Número refeito depois de publicado",
    AUDITOR: "Troca de auditor",
    INSIDERS: "Gente de dentro comprando e vendendo (agregado)",
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


REGRAS: tuple[Callable[[Ficha, date], Cruzamento], ...] = (
    fundos,
    refeito,
    auditor,
    insiders,
)


def cruzamentos_da_ficha(ficha: Ficha, hoje: date) -> list[Cruzamento]:
    """Os quatro cruzamentos da ficha, na mesma ordem sempre (com achado ou "sem achado")."""
    return [regra(ficha, hoje) for regra in REGRAS]


# --- a seção da ficha ----------------------------------------------------------------------------
CHAVE_DA_SECAO = "cruzamentos"
TITULO_DA_SECAO = "Cruzamentos"
SEM_FONTE = "Sem dado da ficha para olhar."
LIMITE_DOS_CRUZAMENTOS = (
    "Os cruzamentos são regras fixas sobre a ficha da noite (fundos, número refeito, auditor e o "
    "agregado dos insiders, sem nomes); mostram o que os dados registram até o dia da ficha, "
    "nunca o que vem depois, e não são recomendação de investimento."
)


def _paragrafo(c: Cruzamento) -> str:
    """O achado (ou o que foi olhado), a data do dado e a fonte: nenhuma frase sem lastro (ADR 0100)."""
    texto = c.frase if c.frase.startswith(c.titulo) else f"{c.titulo}: {c.frase}"
    if not (c.medido_em and c.fontes):
        return f"{texto} {SEM_FONTE}"
    return f"{texto} Dado de {dia(c.medido_em)}. Fonte: {'; '.join(c.fontes)}."


def secao_dos_cruzamentos(ficha: Ficha, hoje: date) -> Secao:
    """Os quatro cruzamentos da ficha como seção do relatório (tela, PDF e API leem os parágrafos)."""
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
