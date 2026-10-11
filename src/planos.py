"""Os planos do TickerLab (Gratuito e Pro) e o que cada um permite.

Este é o único lugar onde os limites são definidos: a tela, o banco e os testes leem daqui.
Mudar um limite é mudar um número neste arquivo.
"""

from dataclasses import dataclass

from src.banco.modelo import PLANOS, TIPOS_DE_RELATORIO

PLANO_DO_MODO_LOCAL = "pro"  # sem contas (desenvolvimento) não há o que limitar

APRENDIZADO_DE_MAQUINA = "aprendizado_de_maquina"
PARES = "pares"
NOMES_DOS_RECURSOS = {
    APRENDIZADO_DE_MAQUINA: "Aprendizado de máquina",
    PARES: "Pairs trading",
}


@dataclass(frozen=True)
class Limites:
    nome: str
    simulacoes: int | None  # None = sem limite
    favoritos: int
    ativos_na_carteira: int
    recursos: frozenset[str]
    relatorios_por_dia: (
        int | None
    )  # relatórios em PDF a cada 24 horas (None = sem limite)
    tipos_de_relatorio: frozenset[str]


LIMITES_DOS_PLANOS = {
    "gratuito": Limites(
        nome="Gratuito",
        simulacoes=5,
        favoritos=3,
        ativos_na_carteira=4,
        recursos=frozenset(),
        relatorios_por_dia=3,
        tipos_de_relatorio=frozenset({"ativo"}),
    ),
    "pro": Limites(
        nome="Pro",
        simulacoes=None,
        favoritos=20,
        ativos_na_carteira=8,
        recursos=frozenset({APRENDIZADO_DE_MAQUINA, PARES}),
        relatorios_por_dia=None,
        tipos_de_relatorio=frozenset(TIPOS_DE_RELATORIO),
    ),
}
assert set(LIMITES_DOS_PLANOS) == set(
    PLANOS
)  # um plano novo no banco exige limites aqui


class LimiteDoPlanoError(ValueError):
    """O plano do usuário não permite esta ação (a mensagem já sugere o Pro)."""


def limites_do(plano: str | None) -> Limites:
    """Os limites do plano. Um plano desconhecido ou vazio vale como Gratuito (o mais restrito)."""
    return LIMITES_DOS_PLANOS.get(plano or "", LIMITES_DOS_PLANOS["gratuito"])


def pode_usar(plano: str | None, recurso: str) -> bool:
    return recurso in limites_do(plano).recursos


def descrever_limite(limite: int | None) -> str:
    return "Ilimitadas" if limite is None else str(limite)


def conferir_simulacoes(plano: str | None, ja_salvas: int) -> None:
    """Levanta `LimiteDoPlanoError` se o usuário não pode salvar mais uma simulação."""
    maximo = limites_do(plano).simulacoes
    if maximo is not None and ja_salvas >= maximo:
        raise LimiteDoPlanoError(
            f"O plano {limites_do(plano).nome} guarda até {maximo} simulações. "
            "Apague alguma ou conheça o plano Pro."
        )


def conferir_relatorio(plano: str | None, tipo: str, gerados_em_24h: int) -> None:
    """Levanta `LimiteDoPlanoError` se o plano não gera este tipo ou já chegou ao limite do dia."""
    limites = limites_do(plano)
    if tipo not in limites.tipos_de_relatorio:
        raise LimiteDoPlanoError(
            f"O plano {limites.nome} gera só o relatório do ativo. "
            "Comparação, backtest e carteira em PDF fazem parte do plano Pro."
        )
    maximo = limites.relatorios_por_dia
    if maximo is not None and gerados_em_24h >= maximo:
        raise LimiteDoPlanoError(
            f"O plano {limites.nome} gera até {maximo} relatórios a cada 24 horas. "
            "Tente mais tarde ou conheça o plano Pro."
        )


def conferir_favoritos(plano: str | None, total_antes: int, total_depois: int) -> None:
    """Levanta `LimiteDoPlanoError` se a lista de favoritos CRESCERIA além do limite do plano.

    Quem tem mais favoritos que o plano atual permite (por ter voltado do Pro para o Gratuito)
    mantém o que tem e pode tirar favoritos; só não pode adicionar.
    """
    maximo = limites_do(plano).favoritos
    if total_depois > maximo and total_depois > total_antes:
        raise LimiteDoPlanoError(
            f"O plano {limites_do(plano).nome} permite até {maximo} favoritos. "
            "Tire algum ou conheça o plano Pro."
        )


def tabela_de_planos() -> list[dict[str, str]]:
    """Linhas da tabela de comparação mostrada na tela."""

    def sim_nao(plano: str, recurso: str) -> str:
        return "Sim" if pode_usar(plano, recurso) else "Não"

    gratuito, pro = limites_do("gratuito"), limites_do("pro")
    return [
        {
            "Recurso": "Simulações salvas",
            "Gratuito": descrever_limite(gratuito.simulacoes),
            "Pro": descrever_limite(pro.simulacoes),
        },
        {
            "Recurso": "Favoritos",
            "Gratuito": str(gratuito.favoritos),
            "Pro": str(pro.favoritos),
        },
        {
            "Recurso": "Ativos na carteira",
            "Gratuito": str(gratuito.ativos_na_carteira),
            "Pro": str(pro.ativos_na_carteira),
        },
        {
            "Recurso": "Aprendizado de máquina",
            "Gratuito": sim_nao("gratuito", APRENDIZADO_DE_MAQUINA),
            "Pro": sim_nao("pro", APRENDIZADO_DE_MAQUINA),
        },
        {
            "Recurso": "Pairs trading",
            "Gratuito": sim_nao("gratuito", PARES),
            "Pro": sim_nao("pro", PARES),
        },
        {
            "Recurso": "Relatórios em PDF",
            "Gratuito": f"Do ativo, {gratuito.relatorios_por_dia} por dia",
            "Pro": "Todos os tipos, ilimitados",
        },
        {"Recurso": "Exportar CSV", "Gratuito": "Sim", "Pro": "Sim"},
    ]
