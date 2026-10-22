"""Os 5 critérios que o gabarito pede do texto do modelo (0087, regra 6), como código. Valem para
os dois gabaritos: o da CPFL (uma empresa) e o do setor elétrico (molde D).

Os critérios 1 a 4 são as regras da porta 1 agrupadas. No 3, a marca da conta nossa é a conta
declarada em `contas` (plano, decisão 5: a porta 1 refaz cada uma; o gabarito aprovado nem sempre
escreve "conta nossa" na frase, como em "de cada R$ 100"); a frase que se diz conta nossa e não
declara a conta, ou declara uma que não sustenta o número, reprova o 3. O 5 compara
cada parte com a mesma parte do gabarito: tem de haver leitura onde o gabarito tem e pelo menos
60% das palavras (parágrafo que só repete a tabela em frase não conta como análise).
"""

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any

from src.analise_escrita import porta1, saida

NOMES = {
    1: "fato e leitura separados",
    2: "os buracos aparecem",
    3: "contas nossas marcadas",
    4: "nenhuma palavra proibida",
    5: "profundidade mínima",
}
REGRAS_DA_PORTA1 = {
    1: frozenset(
        {
            porta1.ID_INEXISTENTE,
            porta1.NUMERO,
            porta1.DATA,
            porta1.DATA_FUTURA,
            porta1.NOME,
            porta1.ESTRUTURA,
        }
    ),
    2: frozenset({porta1.LACUNA, porta1.ANO_PARCIAL}),
    3: frozenset({porta1.CONTA}),
    4: frozenset({porta1.PALAVRA, porta1.PREVISAO, porta1.PESSOA}),
}
MARCA_DA_CONTA = "conta nossa"
MINIMO_DE_PALAVRAS = 0.6  # da mesma parte no gabarito
Posicao = tuple[str, int, int]  # parte, parágrafo, frase


@dataclass(frozen=True)
class Criterio:
    numero: int
    nome: str
    falhas: tuple[str, ...]  # vazio: passou

    @property
    def passou(self) -> bool:
        return not self.falhas


def _onde(reprovacao: porta1.Reprovacao) -> str:
    if reprovacao.paragrafo is None:
        return reprovacao.parte
    return f"{reprovacao.parte}.{reprovacao.paragrafo}.{reprovacao.frase}"


def _texto_da_falha(reprovacao: porta1.Reprovacao) -> str:
    return f"{_onde(reprovacao)} {reprovacao.regra}: {reprovacao.detalhe}"


# --- critério 3: a conta que diz que é nossa ------------------------------------------------------
def _marcada(frase: saida.Frase) -> bool:
    return MARCA_DA_CONTA in porta1.normalizar(frase.texto)


def _marcadas(analise: saida.Analise) -> dict[Posicao, saida.Frase]:
    return {
        (parte.chave, i, j): frase
        for parte in analise.partes
        for i, paragrafo in enumerate(parte.paragrafos)
        for j, frase in enumerate(paragrafo.frases)
        if _marcada(frase)
    }


def _posicao(reprovacao: porta1.Reprovacao) -> tuple[str, int | None, int | None]:
    return reprovacao.parte, reprovacao.paragrafo, reprovacao.frase


def _criterio_da_reprovacao(
    reprovacao: porta1.Reprovacao, marcadas: dict[Posicao, saida.Frase]
) -> int | None:
    """O número sem fonte numa frase que se diz conta nossa é conta mal declarada (3), não nota (1)."""
    if reprovacao.regra == porta1.NUMERO and _posicao(reprovacao) in marcadas:
        return 3
    return next((n for n, r in REGRAS_DA_PORTA1.items() if reprovacao.regra in r), None)


def _marcadas_sem_conta(marcadas: dict[Posicao, saida.Frase]) -> Iterator[str]:
    for (parte, i, j), frase in marcadas.items():
        if not frase.contas:
            yield f'{parte}.{i}.{j}: diz "{MARCA_DA_CONTA}" e não declara a conta'


# --- critério 5: profundidade ----------------------------------------------------------------------
def _palavras(parte: saida.Parte) -> int:
    return sum(len(f.texto.split()) for p in parte.paragrafos for f in p.frases)


def _tem_leitura(parte: saida.Parte) -> bool:
    return any(p.tipo == saida.LEITURA and p.frases for p in parte.paragrafos)


def _rasas(analise: saida.Analise, gabarito: saida.Analise) -> Iterator[str]:
    escritas = {p.chave: p for p in analise.partes}
    for alvo in gabarito.partes:
        parte = escritas.get(alvo.chave)
        if parte is None:
            continue  # parte faltando é o critério 1 (estrutura)
        if _tem_leitura(alvo) and not _tem_leitura(parte):
            yield f"{parte.chave}: sem leitura"
        minimo = MINIMO_DE_PALAVRAS * _palavras(alvo)
        if _palavras(parte) < minimo:
            yield f"{parte.chave}: {_palavras(parte)} palavras (o gabarito tem {_palavras(alvo)})"


def avaliar(
    analise: saida.Analise, entrada: dict[str, Any], gabarito: saida.Analise
) -> list[Criterio]:
    """Os 5 critérios, em ordem, cada um com o que reprovou."""
    marcadas = _marcadas(analise)
    falhas: dict[int, list[str]] = {numero: [] for numero in NOMES}
    for reprovacao in porta1.conferir(analise, entrada).reprovacoes:
        numero = _criterio_da_reprovacao(reprovacao, marcadas)
        if numero is not None:
            falhas[numero].append(_texto_da_falha(reprovacao))
    falhas[3] += _marcadas_sem_conta(marcadas)
    falhas[5] += _rasas(analise, gabarito)
    return [Criterio(n, NOMES[n], tuple(falhas[n])) for n in sorted(NOMES)]


# --- o relatório lado a lado ----------------------------------------------------------------------
def _celula(texto: str) -> str:
    return texto.replace("|", "\\|").replace("\n", " ")


def _texto_do_paragrafo(paragrafo: saida.Paragrafo) -> str:
    texto = " ".join(f.texto for f in paragrafo.frases)
    return f"*Leitura:* {texto}" if paragrafo.tipo == saida.LEITURA else texto


def _tabela(cabecalho: list[str], linhas: list[list[str]]) -> list[str]:
    return [
        "| " + " | ".join(cabecalho) + " |",
        "|" + " --- |" * len(cabecalho),
        *("| " + " | ".join(_celula(c) for c in linha) + " |" for linha in linhas),
    ]


def _resultado(criterio: Criterio) -> str:
    return "passou" if criterio.passou else f"reprovou ({len(criterio.falhas)})"


def _secao_dos_criterios(por_texto: Mapping[str, list[Criterio]]) -> list[str]:
    nomes = list(por_texto)
    linhas = [
        [f"{n}. {NOMES[n]}", *(_resultado(por_texto[t][n - 1]) for t in nomes)]
        for n in sorted(NOMES)
    ]
    saida_ = ["## Critérios do gabarito", "", *_tabela(["Critério", *nomes], linhas)]
    for nome, criterios in por_texto.items():
        falhas = [f"- {c.numero}: {f}" for c in criterios for f in c.falhas]
        if falhas:
            saida_ += ["", f"**{nome}, o que reprovou:**", "", *falhas]
    return saida_


def _secao_da_parte(chave: str, textos: Mapping[str, saida.Analise]) -> list[str]:
    partes = {
        nome: {p.chave: p for p in analise.partes}.get(chave)
        for nome, analise in textos.items()
    }
    maximo = max((len(p.paragrafos) for p in partes.values() if p), default=0)
    linhas = []
    for i in range(maximo):
        celulas = [
            _texto_do_paragrafo(p.paragrafos[i]) if p and i < len(p.paragrafos) else "—"
            for p in partes.values()
        ]
        linhas.append([str(i), *celulas])
    palavras = [str(_palavras(p)) if p else "—" for p in partes.values()]
    linhas.append(["palavras", *palavras])
    return [f"## {saida.TITULOS[chave]}", "", *_tabela(["#", *textos], linhas)]


def relatorio(
    textos: Mapping[str, saida.Analise],
    criterios: Mapping[str, list[Criterio]],
) -> str:
    """Markdown com os critérios de cada texto e as partes lado a lado, parágrafo por parágrafo."""
    linhas = _secao_dos_criterios(criterios) if criterios else []
    # as partes na ordem do roteiro dos textos (o da empresa ou o do setor)
    chaves = dict.fromkeys(
        p.chave for analise in textos.values() for p in analise.partes
    )
    for chave in chaves:
        linhas += ["", *_secao_da_parte(chave, textos)]
    return "\n".join(linhas).strip() + "\n"
