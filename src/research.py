"""O motor de relevância do Research (PRD v2, seção 10): o que aparece primeiro e por quê.

Separa três coisas, como pede o PRD: **pertinência** (o evento é de uma empresa que você
acompanha), **materialidade** (o tipo de documento costuma importar) e **urgência** (é recente, é
novo). O resultado só ordena a leitura; **não é nota de atratividade do investimento**.

    relevância = soma(peso × componente) / 100, com cada componente entre 0 e 1

Os pesos vêm dos parâmetros `relevancia.*` (somam 100; editáveis na página Parâmetros). Cada item
traz as razões em português ("Você acompanha PETR4 na lista Favoritos"), para a tela mostrar
"Por que isso aparece?". Sem evidência não há item: todo evento tem o link do documento original.
"""

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date

from src.banco.eventos import Evento

COMPONENTES = (
    "exposicao",
    "materialidade",
    "novidade",
    "qualidade_da_fonte",
    "preferencias",
    "recencia",
)
# fontes primárias oficiais (o documento entregue pela própria empresa); notícias valeriam menos
QUALIDADE_DAS_FONTES = {"cvm_ipe": 1.0, "sec_edgar": 1.0}
NOMES_DAS_FONTES = {
    "cvm_ipe": "CVM (documento entregue pela empresa)",
    "sec_edgar": "SEC, dos EUA (documento entregue pela empresa)",
}
SIGLAS_DAS_FONTES = {"cvm_ipe": "CVM", "sec_edgar": "SEC"}
DEMONSTRACAO = (
    "PETR4.SA",
    "VALE3.SA",
    "ITUB4.SA",
    "WEGE3.SA",
    "BBAS3.SA",
    "AAPL",
    "MSFT",
)
NOME_DA_DEMONSTRACAO = "Demonstração"
MAXIMO_POR_EMPRESA = (
    3  # supressão de ruído: nenhuma empresa ocupa mais lugares que isso
)


@dataclass(frozen=True)
class ItemDoResearch:
    evento: Evento
    relevancia: float  # 0 a 1
    componentes: dict[str, float]
    razoes: list[str]


def pontuar(
    evento: Evento,
    pesos: Mapping[str, float],
    temas: Iterable[str],
    hoje: date,
    janela_em_dias: int,
    nome_da_lista: str,
) -> ItemDoResearch:
    """A relevância de um evento e as razões, a partir dos pesos (`relevancia.*`, somando 100)."""
    temas = set(temas)
    idade = max((hoje - evento.publicado_em).days, 0)
    componentes = {
        "exposicao": 1.0,  # numa watchlist, todo ativo pesa igual (sem tamanho de posição)
        "materialidade": evento.materialidade / 100,
        "novidade": 1.0 if evento.versao == 1 else 0.5,  # reapresentação vale menos
        "qualidade_da_fonte": QUALIDADE_DAS_FONTES.get(evento.fonte, 0.5),
        "preferencias": 1.0 if evento.tema in temas else 0.0,
        "recencia": max(0.0, 1 - idade / max(janela_em_dias, 1)),
    }
    total = sum(pesos[c] * componentes[c] for c in COMPONENTES) / 100
    codigo = evento.ticker.removesuffix(".SA")
    razoes = [
        f"Você acompanha {codigo} na lista {nome_da_lista}.",
        f"{evento.rotulo}: materialidade {evento.materialidade} de 100 para este tipo de documento.",
        (
            f'O tema "{evento.tema}" está entre os seus temas.'
            if componentes["preferencias"]
            else f'O tema "{evento.tema}" não está entre os seus temas (pesa menos).'
        ),
        f"Publicado em {evento.publicado_em:%d/%m/%Y} ({_ha(idade)}).",
        f"Fonte: {NOMES_DAS_FONTES.get(evento.fonte, evento.fonte)}"
        + ("" if evento.versao == 1 else f", reapresentação (versão {evento.versao})")
        + ".",
    ]
    return ItemDoResearch(evento, round(total, 4), componentes, razoes)


def _ha(dias: int) -> str:
    if dias == 0:
        return "hoje"
    return "há 1 dia" if dias == 1 else f"há {dias} dias"


def ordenar(
    eventos: Iterable[Evento],
    pesos: Mapping[str, float],
    temas: Iterable[str],
    hoje: date,
    janela_em_dias: int,
    nome_da_lista: str,
    maximo_por_ativo: int | None = MAXIMO_POR_EMPRESA,
    maximo: int | None = None,
) -> list[ItemDoResearch]:
    """Os eventos por relevância (empate: o mais recente), sem que uma empresa domine a lista.

    `maximo_por_ativo` (supressão de ruído, PRD 10.4): o resto da empresa aparece com `None`
    (na tela, "Mostrar todos"); só não ocupa o topo por padrão.
    """
    pontuados = sorted(
        (
            pontuar(e, pesos, temas, hoje, janela_em_dias, nome_da_lista)
            for e in eventos
        ),
        key=lambda i: (i.relevancia, i.evento.publicado_em),
        reverse=True,
    )
    por_ativo: Counter[str] = Counter()
    saida = []
    for item in pontuados:
        if (
            maximo_por_ativo is not None
            and por_ativo[item.evento.ticker] >= maximo_por_ativo
        ):
            continue
        por_ativo[item.evento.ticker] += 1
        saida.append(item)
        if maximo is not None and len(saida) >= maximo:
            break
    return saida


def pesos_da_resolucao(valores_de_relevancia: Mapping[str, object]) -> dict[str, float]:
    """`{"relevancia.exposicao": 25, ...}` → `{"exposicao": 25.0, ...}`."""
    return {c: float(valores_de_relevancia[f"relevancia.{c}"]) for c in COMPONENTES}
