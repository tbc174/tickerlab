"""Os gráficos e os destaques que o modelo escolhe para cada relatório (plano de 23/10/2026).

A IA escolhe, o código desenha: o modelo devolve só a forma do gráfico (um tipo do `CARDAPIO`), a
tabela da ficha, a coluna do eixo, as colunas dos valores, um título e uma frase que diz por que o
gráfico está ali, presa a um parágrafo da análise. Nenhum número sai do modelo: os pontos são lidos
da própria ficha, e a porta 1 (`porta1_dos_graficos`) confere que a tabela e as colunas existem e
servem à forma escolhida. O destaque é uma seção da ficha que o modelo puxa para perto de uma parte
do texto, com a frase do porquê.

O cardápio é por forma, não por tabela: qualquer tabela da entrada que tenha a coluna certa serve, e
o relatório do setor usa o mesmo cardápio com as tabelas dele.
"""

import json
from dataclasses import asdict, dataclass
from typing import Any

from src.analise_escrita import numeros, saida

TEMPO, CATEGORIA = "tempo", "categoria"
MAXIMO_DE_GRAFICOS = 5
MINIMO_DE_GRAFICOS = 2  # menos que isso, a reserva por regras completa
MAXIMO_DE_DESTAQUES = 2


@dataclass(frozen=True)
class Forma:
    """O que um tipo de gráfico aceita: o eixo, quantas colunas de valor e quantos pontos no mínimo."""

    eixo: str  # TEMPO (ano, mês, data) ou CATEGORIA (passo, empresa, parcela)
    colunas: tuple[int, int]  # mínimo e máximo de colunas de valor
    pontos: int  # pontos com valor, no mínimo, em cada coluna
    quando_serve: str  # vai para o guia do modelo


CARDAPIO: dict[str, Forma] = {
    "linha_no_tempo": Forma(
        TEMPO, (1, 3), 3,
        "tendência de vários anos ou meses de um a três indicadores (margem, dívida, fundos com a ação)",
    ),
    "barras_no_tempo": Forma(
        TEMPO, (1, 2), 2,
        "quantidades ou valores por período, que se comparam lado a lado (ofertas por ano, consumidores)",
    ),
    "barras_por_categoria": Forma(
        CATEGORIA, (1, 1), 2,
        "um número para cada item de uma lista (empresas do setor, parcelas de uma nota)",
    ),
    "dispersao": Forma(
        CATEGORIA, (2, 2), 3,
        "dois indicadores juntos para cada item, para ver quem fica onde (margem contra dívida)",
    ),
    "cascata": Forma(
        CATEGORIA, (1, 1), 3,
        "passos que somam de um total a outro (da receita ao lucro, da dívida de antes à de agora)",
    ),
    "antes_e_agora": Forma(
        CATEGORIA, (2, 2), 1,
        "o mesmo indicador em dois momentos, item por item (o balanço anterior e o de agora)",
    ),
}  # fmt: skip


@dataclass(frozen=True)
class Grafico:
    tipo: str
    tabela: str  # o id da tabela na entrada: `secao.tabela` (as linhas são `secao.tabela.i`)
    eixo: str  # a coluna das datas ou dos nomes
    colunas: tuple[str, ...]  # as colunas dos valores
    titulo: str
    parte: str  # a parte da análise onde o gráfico entra
    paragrafo: int  # depois de qual parágrafo da parte (contando do zero)
    por_que: saida.Frase  # conferida como qualquer frase da análise
    origem: str = saida.ORIGEM_MODELO


@dataclass(frozen=True)
class Destaque:
    secao: str  # a seção da ficha puxada para perto do texto
    parte: str
    por_que: saida.Frase
    origem: str = saida.ORIGEM_MODELO


@dataclass(frozen=True)
class Escolha:
    graficos: tuple[Grafico, ...]
    destaques: tuple[Destaque, ...] = ()

    def como_dict(self) -> dict[str, Any]:
        """Pronto para JSON: é o que se guarda junto da análise e o que a API devolve."""
        return json.loads(json.dumps(asdict(self), ensure_ascii=False))


@dataclass(frozen=True)
class LinhaDaTabela:
    id: str
    celulas: dict[str, Any]
    so_pro: bool


def _texto_obrigatorio(dado: dict[str, Any], campo: str) -> str:
    texto = str(dado.get(campo) or "").strip()
    if not texto:
        raise saida.RespostaInvalidaError(f"{campo} vazio")
    return texto


def _grafico(dado: dict[str, Any]) -> Grafico:
    tipo = dado.get("tipo")
    if tipo not in CARDAPIO:
        raise saida.RespostaInvalidaError(f"gráfico fora do cardápio: {tipo}")
    colunas = tuple(str(c) for c in dado.get("colunas") or [])
    if not colunas:
        raise saida.RespostaInvalidaError("gráfico sem coluna de valor")
    paragrafo = int(dado.get("paragrafo", -1))
    if paragrafo < 0:
        raise saida.RespostaInvalidaError(f"parágrafo inválido: {paragrafo}")
    return Grafico(
        tipo=tipo,
        tabela=_texto_obrigatorio(dado, "tabela"),
        eixo=_texto_obrigatorio(dado, "eixo"),
        colunas=colunas,
        titulo=_texto_obrigatorio(dado, "titulo"),
        parte=_texto_obrigatorio(dado, "parte"),
        paragrafo=paragrafo,
        por_que=saida.ler_frase(dado.get("por_que") or {}),
        origem=dado.get("origem", saida.ORIGEM_MODELO),
    )


def _destaque(dado: dict[str, Any]) -> Destaque:
    return Destaque(
        secao=_texto_obrigatorio(dado, "secao"),
        parte=_texto_obrigatorio(dado, "parte"),
        por_que=saida.ler_frase(dado.get("por_que") or {}),
        origem=dado.get("origem", saida.ORIGEM_MODELO),
    )


def ler_escolha(dado: dict[str, Any]) -> Escolha:
    """A resposta (ou o JSON guardado) como `Escolha`; `RespostaInvalidaError` se sair do formato.

    Tabela, coluna ou parte que não existem não são erro de formato: a porta 1 reprova o gráfico.
    """
    if not isinstance(dado, dict) or not isinstance(dado.get("graficos"), list):
        raise saida.RespostaInvalidaError("a resposta não tem a lista de gráficos")
    return Escolha(
        graficos=tuple(_grafico(g) for g in dado["graficos"]),
        destaques=tuple(_destaque(d) for d in dado.get("destaques") or []),
    )


def esquema(partes: tuple[str, ...] = saida.PARTES) -> dict[str, Any]:
    """A saída estruturada da escolha, com as partes do roteiro (empresa ou setor)."""
    parte = {"type": "string", "enum": list(partes)}
    grafico = saida.objeto_fechado(
        {
            "tipo": {"type": "string", "enum": list(CARDAPIO)},
            "tabela": {
                "type": "string",
                "description": "secao.tabela, sem o número da linha",
            },
            "eixo": {
                "type": "string",
                "description": "a coluna das datas ou dos nomes",
            },
            "colunas": saida.lista_de({"type": "string"}),
            "titulo": {"type": "string"},
            "parte": parte,
            "paragrafo": {
                "type": "integer",
                "description": "depois de qual parágrafo, do zero",
            },
            "por_que": saida.ESQUEMA_DA_FRASE,
        }
    )
    destaque = saida.objeto_fechado(
        {"secao": {"type": "string"}, "parte": parte, "por_que": saida.ESQUEMA_DA_FRASE}
    )
    return saida.objeto_fechado(
        {"graficos": saida.lista_de(grafico), "destaques": saida.lista_de(destaque)}
    )


ESQUEMA: dict[str, Any] = esquema()


def tabelas_da_entrada(entrada: dict[str, Any]) -> dict[str, list[LinhaDaTabela]]:
    """As linhas de tabela da entrada juntadas pela tabela (`secao.tabela`), na ordem da ficha."""
    tabelas: dict[str, list[LinhaDaTabela]] = {}
    for linha in entrada["linhas"]:
        if linha.get("tipo") != "linha":
            continue
        tabela = linha["id"].rsplit(".", 1)[0]
        tabelas.setdefault(tabela, []).append(
            LinhaDaTabela(linha["id"], linha["celulas"], bool(linha.get("so_pro")))
        )
    return tabelas


def valor_da_celula(celula: object) -> float | None:
    """O número de uma célula: o próprio número, ou o único número escrito no texto ("R$ 655,8 mi").

    Verdadeiro e falso não são números (a coluna "cumpriu"), nem o texto com dois números ou nenhum.
    """
    if isinstance(celula, bool):
        return None
    if isinstance(celula, int | float):
        return float(celula)
    if isinstance(celula, str):
        lidos = numeros.numeros(celula)
        return lidos[0].valor if len(lidos) == 1 else None
    return None


def momento_da_celula(celula: object) -> numeros.DataEscrita | None:
    """A data de uma célula do eixo do tempo: um ano inteiro (2024) ou uma única data no texto."""
    if isinstance(celula, bool):
        return None
    if isinstance(celula, int | float) and float(celula).is_integer():
        ano = int(celula)
        if numeros.PRIMEIRO_ANO <= ano <= numeros.ULTIMO_ANO:
            return numeros.DataEscrita(ano, None, None, str(ano))
        return None
    if isinstance(celula, str):
        lidas = numeros.datas(celula)
        return lidas[0] if len(lidas) == 1 else None
    return None


@dataclass(frozen=True)
class Ponto:
    """Uma linha da tabela vista pelo gráfico: o rótulo do eixo, a data dele e os valores."""

    id: str
    rotulo: str
    momento: numeros.DataEscrita | None
    valores: tuple[float | None, ...]  # um por coluna, na ordem do gráfico


def pontos(grafico: Grafico, linhas: list[LinhaDaTabela]) -> list[Ponto]:
    """Os pontos do gráfico lidos da ficha, na ordem da tabela: é daqui, e só daqui, que saem os
    números do desenho."""
    return [
        Ponto(
            id=linha.id,
            rotulo=str(linha.celulas.get(grafico.eixo) or "").strip(),
            momento=momento_da_celula(linha.celulas.get(grafico.eixo)),
            valores=tuple(
                valor_da_celula(linha.celulas.get(c)) for c in grafico.colunas
            ),
        )
        for linha in linhas
    ]
