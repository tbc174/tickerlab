"""O molde: o texto de reserva por regras, parte por parte, montado das próprias linhas da entrada.

Sai quando a parte do modelo não passa nas portas, quando não há resposta ou quando a ficha mudou
desde que o texto foi escrito (0093, regra 3; 0100). Cada frase repete o que a linha da ficha já
diz, com a nota da linha, e a frase que a porta 1 reprovaria fica de fora: o molde sempre passa.
É seco de propósito: lista os números, não lê nada (nenhum parágrafo de leitura). A entrada de um
setor (molde D) tem o próprio roteiro e deixa de fora o ano parcial: ele só aparece pela lacuna.
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from src.analise_escrita import porta1, saida

VERSAO_DO_MOLDE = 1  # vai para a linhagem: mudou o molde, sobe a versão
SEM_DADOS = "A ficha desta empresa não traz dados para esta parte."
SEM_DADOS_DO_SETOR = "O relatório deste setor não traz dados para esta parte."

# De qual parte é cada linha, pelo começo do id; vale o primeiro que casa. Fora daqui (metodologia,
# notas contra o setor) não entra: a tela já mostra.
ROTEIRO = (
    ("o_que_os_dados_mostram", "em_meia_pagina"),
    ("ficha_tecnica.nome", "o_que_e"),
    ("ficha_tecnica.setor", "o_que_e"),
    ("auditor_e_controladas.sociedades", "o_que_e"),
    ("auditor_e_controladas.controladas", "o_que_e"),
    ("auditor_e_controladas.coligadas_e_outras", "o_que_e"),
    ("setor_regulado", "o_que_e"),
    ("ficha_tecnica", "quem_manda"),
    ("auditor_e_controladas", "quem_manda"),
    ("dividendos.diluicao", "quem_manda"),
    ("o_que_mudou", "o_que_mudou"),
    ("negocios", "o_que_mudou"),
    ("eventos", "o_que_mudou"),
    ("resultado", "o_que_os_numeros_mostram"),
    ("retorno", "o_que_os_numeros_mostram"),
    ("endividamento", "o_que_os_numeros_mostram"),
    ("caixa", "o_que_os_numeros_mostram"),
    ("notas_classicas", "o_que_os_numeros_mostram"),
    ("qualidade_do_lucro", "o_que_os_numeros_mostram"),
    ("historico", "o_que_os_numeros_mostram"),
    ("dividendos", "dinheiro"),
    ("ofertas_e_fundos", "dinheiro"),
    ("o_que_mudaria", "o_que_mudaria"),
    ("lacuna", "limites"),
    ("pares", "limites"),
    ("limites", "limites"),
)
# Tabelas viram frase só onde cada linha é curta e só de texto (antes e agora; os gatilhos): as
# outras (negócios, ofertas, histórico) dariam dezenas de frases que a tela já mostra em tabela.
SECOES_COM_TABELA = ("o_que_mudou", "o_que_mudaria")
# Parágrafos que dizem algo da empresa; nas outras seções o parágrafo é nota de método e licença
# ("Dados da base de...", "Fonte: ODbL..."), que a tela já mostra embaixo da seção.
SECOES_COM_PARAGRAFO = (
    "o_que_mudou",
    "eventos",
    "qualidade_do_lucro",
    "historico",
    "pares",
    "o_que_mudaria",
    "limites",
)
REPETIDAS = (
    "ficha_tecnica.auditor",
)  # o auditor sai pelas linhas de auditor_e_controladas
# O roteiro do setor: as frases por regra abrem; tamanho e concentração viram frase linha a linha (são
# poucas: uma por ano); participação e lado a lado ficam nas tabelas da tela (dezenas de linhas).
ROTEIRO_DO_SETOR = (
    ("o_que_os_dados_mostram", "em_meia_pagina"),
    ("membros", "quem_esta"),
    ("tamanho", "tamanho_e_concentracao"),
    ("concentracao", "tamanho_e_concentracao"),
    ("participacao", "participacao"),
    ("lado_a_lado", "lado_a_lado"),
    ("nao_temos", "o_que_mudaria"),
    ("lacuna", "limites"),
    ("limites", "limites"),
)
SECOES_COM_TABELA_DO_SETOR = ("tamanho", "concentracao", "nao_temos")
SECOES_COM_PARAGRAFO_DO_SETOR = (
    "o_que_os_dados_mostram",
    "membros",
    "concentracao",
    "limites",
)
MAIOR_ABREVIACAO = 4  # "Emp.", "Adm.", "Part.": palavra curta com maiúscula antes do ponto não fecha frase
SEM_TEXTO = ("", "—")

_FIM_DE_SENTENCA = re.compile(r"[.!?]\s+")


@dataclass(frozen=True)
class Roteiro:
    """De qual parte é cada linha e quais tabelas e parágrafos viram frase."""

    partes: tuple[str, ...]
    linhas: tuple[tuple[str, str], ...]
    secoes_com_tabela: tuple[str, ...]
    secoes_com_paragrafo: tuple[str, ...]
    repetidas: tuple[str, ...]
    sem_dados: str


DA_EMPRESA = Roteiro(
    saida.PARTES, ROTEIRO, SECOES_COM_TABELA, SECOES_COM_PARAGRAFO, REPETIDAS, SEM_DADOS
)
DO_SETOR = Roteiro(
    saida.PARTES_DO_SETOR,
    ROTEIRO_DO_SETOR,
    SECOES_COM_TABELA_DO_SETOR,
    SECOES_COM_PARAGRAFO_DO_SETOR,
    (),
    SEM_DADOS_DO_SETOR,
)


def roteiro_de(entrada: dict[str, Any]) -> Roteiro:
    return DO_SETOR if entrada.get("tipo") == saida.TIPO_SETOR else DA_EMPRESA


def _parte_da_linha(id_: str, roteiro: Roteiro) -> str | None:
    for comeco, parte in roteiro.linhas:
        if id_ == comeco or id_.startswith(comeco + "."):
            return parte
    return None


def _sentencas(texto: str) -> list[str]:
    """O parágrafo em sentenças, sem cortar abreviações ("Emp. Adm. Part. - Energia Elétrica")."""
    sentencas, inicio = [], 0
    for achado in _FIM_DE_SENTENCA.finditer(texto):
        palavra = texto[inicio : achado.start()].split()[-1:] or [""]
        abreviacao = len(palavra[0]) <= MAIOR_ABREVIACAO and palavra[0][:1].isupper()
        if not abreviacao:
            sentencas.append(texto[inicio : achado.start() + 1].strip())
            inicio = achado.end()
    sentencas.append(texto[inicio:].strip())
    return [s for s in sentencas if s]


def _com_ponto(texto: str) -> str:
    return texto if texto.endswith((".", "!", "?")) else texto + "."


def _texto_do_numero(linha: dict[str, Any]) -> str | None:
    nome = linha.get("nome", "")
    if linha.get("motivo"):
        return f"{nome}: {linha['motivo']}"
    if linha.get("texto", "") in SEM_TEXTO:
        return None
    texto = f"{nome}: {linha['texto']}"
    if linha.get("medido_em"):
        texto += f" ({linha['medido_em']})"
    comparacao = linha.get("comparacao") or {}
    if comparacao.get("texto"):
        texto += f"; {comparacao['contra']}: {comparacao['texto']}"
    return texto


def _texto_da_tabela(linha: dict[str, Any], roteiro: Roteiro) -> str | None:
    celulas = list((linha.get("celulas") or {}).items())
    if linha["secao"] not in roteiro.secoes_com_tabela or not celulas:
        return None
    if not all(isinstance(valor, str) for _, valor in celulas):
        return None
    (_, primeira), resto = celulas[0], celulas[1:]
    colunas = "; ".join(f"{chave.replace('_', ' ')} {valor}" for chave, valor in resto)
    return f"{linha['tabela']}, {primeira}: {colunas}"


def _textos_da_linha(linha: dict[str, Any], roteiro: Roteiro) -> list[str]:
    tipo = linha["tipo"]
    if tipo == "numero":
        texto = _texto_do_numero(linha)
    elif tipo == "linha":
        texto = _texto_da_tabela(linha, roteiro)
    elif tipo == "paragrafo" and linha["secao"] not in roteiro.secoes_com_paragrafo:
        return []
    else:  # ponto, parágrafo, lacuna: o texto já é frase
        return _sentencas(linha.get("texto", ""))
    return [_com_ponto(texto)] if texto else []


def _entra(linha: dict[str, Any], incluir_so_pro: bool, obrigatorias: set[str]) -> bool:
    """Sem o dossiê, fica de fora a linha `so_pro`, menos a lacuna obrigatória (ela não mostra
    número do dossiê: diz o que falta). A linha do ano parcial nunca entra: a lacuna fala dela."""
    if linha.get(porta1.ANO_PARCIAL):
        return False
    return incluir_so_pro or not linha.get("so_pro") or linha["id"] in obrigatorias


def _frases_por_parte(
    entrada: dict[str, Any], incluir_so_pro: bool
) -> Iterator[tuple[str, str, saida.Frase]]:
    """(parte, seção, frase) na ordem da entrada, só as frases que passam sozinhas na porta 1."""
    ficha = porta1.ler_ficha(entrada)
    roteiro = roteiro_de(entrada)
    obrigatorias = set(entrada.get("obrigatorias", []))
    for linha in entrada["linhas"]:
        parte = _parte_da_linha(linha["id"], roteiro)
        if parte is None or linha["id"] in roteiro.repetidas:
            continue
        if not _entra(linha, incluir_so_pro, obrigatorias):
            continue
        for texto in _textos_da_linha(linha, roteiro):
            frase = saida.Frase(texto, (linha["id"],))
            if not porta1.falhas_da_frase(frase, ficha):
                yield parte, linha["secao"], frase


def _paragrafos(
    frases: list[tuple[str, saida.Frase]], sem_dados: str
) -> tuple[saida.Paragrafo, ...]:
    """Um parágrafo de fato por seção da ficha, na ordem em que aparecem."""
    por_secao: dict[str, list[saida.Frase]] = {}
    for secao, frase in frases:
        por_secao.setdefault(secao, []).append(frase)
    paragrafos = tuple(
        saida.Paragrafo(saida.FATO, tuple(f)) for f in por_secao.values()
    )
    return paragrafos or (saida.Paragrafo(saida.FATO, (saida.Frase(sem_dados),)),)


def molde(entrada: dict[str, Any], incluir_so_pro: bool = True) -> saida.Analise:
    """As partes do roteiro por regras, com `origem` molde. `incluir_so_pro=False` é o molde de
    quem não é Pro: sem as linhas do dossiê (D4)."""
    roteiro = roteiro_de(entrada)
    por_parte: dict[str, list[tuple[str, saida.Frase]]] = {
        c: [] for c in roteiro.partes
    }
    for parte, secao, frase in _frases_por_parte(entrada, incluir_so_pro):
        por_parte[parte].append((secao, frase))
    return saida.Analise(
        tuple(
            saida.Parte(
                chave, _paragrafos(frases, roteiro.sem_dados), saida.ORIGEM_MOLDE
            )
            for chave, frases in por_parte.items()
        )
    )
