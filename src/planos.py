"""Os planos do TickerLab (Gratuito, Plus e Pro) e o que cada um permite.

Este é o único lugar onde os limites são definidos: a tela, o banco e os testes leem daqui.
Mudar um limite é mudar um número neste arquivo.
"""

from dataclasses import dataclass

from src.banco.modelo import PLANOS, TIPOS_DE_RELATORIO

PLANO_DO_MODO_LOCAL = "pro"  # sem contas (desenvolvimento) não há o que limitar

APRENDIZADO_DE_MAQUINA = "aprendizado_de_maquina"
PARES = "pares"
CARTEIRA_NO_RESEARCH = (
    "carteira_no_research"  # Research, etapa 5 (PRD, seção 15: no Pro)
)
NOMES_DOS_RECURSOS = {
    APRENDIZADO_DE_MAQUINA: "Aprendizado de máquina",
    PARES: "Pairs trading",
    CARTEIRA_NO_RESEARCH: "Carteira no Research",
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
    # Research: ativos com parâmetros próprios (o "seu padrão" vale em todos os planos)
    ativos_com_parametros: int = 0
    # Research: listas com nome e quantos ativos cabem em cada uma
    watchlists: int = 1
    ativos_por_watchlist: int = 10
    # Research (etapa 6): alertas compostos salvos
    alertas: int = 1
    # PDFs originais guardados na biblioteca (ADR 0021): o mais antigo sai quando passa daqui
    pdfs_guardados: int = 10
    # links compartilhados ativos (onda 4): vencidos e revogados não contam
    links_ativos: int = 3


LIMITES_DOS_PLANOS = {
    "gratuito": Limites(
        nome="Gratuito",
        simulacoes=5,
        favoritos=3,
        ativos_na_carteira=4,
        recursos=frozenset(),
        relatorios_por_dia=3,
        tipos_de_relatorio=frozenset({"ativo"}),
        ativos_com_parametros=0,
        watchlists=1,
        ativos_por_watchlist=10,
    ),
    "plus": Limites(
        nome="Plus",
        simulacoes=30,
        favoritos=10,
        ativos_na_carteira=6,
        recursos=frozenset(),  # Aprendizado de máquina e Pairs trading ficam no Pro
        relatorios_por_dia=20,
        tipos_de_relatorio=frozenset(TIPOS_DE_RELATORIO),
        ativos_com_parametros=10,  # Research (confirmado pelo Tiago em 11/10/2026)
        watchlists=3,
        ativos_por_watchlist=20,
        alertas=5,
        pdfs_guardados=50,
        links_ativos=20,
    ),
    "pro": Limites(
        nome="Pro",
        simulacoes=None,
        favoritos=20,
        ativos_na_carteira=8,
        recursos=frozenset({APRENDIZADO_DE_MAQUINA, PARES, CARTEIRA_NO_RESEARCH}),
        relatorios_por_dia=None,
        tipos_de_relatorio=frozenset(TIPOS_DE_RELATORIO),
        ativos_com_parametros=50,
        watchlists=10,
        ativos_por_watchlist=50,
        alertas=20,
        pdfs_guardados=200,
        links_ativos=100,
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


def conferir_links(plano: str | None, ativos: int) -> None:
    """Levanta `LimiteDoPlanoError` se o usuário não pode criar mais um link compartilhado."""
    limites = limites_do(plano)
    if ativos >= limites.links_ativos:
        raise LimiteDoPlanoError(
            f"O plano {limites.nome} mantém até {limites.links_ativos} links ativos. "
            "Revogue algum ou espere um vencer."
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


def conferir_parametros_por_ativo(
    plano: str | None, ativos_ja_personalizados: int, ja_tem_este: bool
) -> None:
    """Levanta `LimiteDoPlanoError` se o plano não permite parâmetros próprios para mais um ativo.

    Mudar um ativo que já tem parâmetros próprios sempre pode (inclusive para restaurar).
    """
    limites = limites_do(plano)
    if ja_tem_este:
        return
    if limites.ativos_com_parametros == 0:
        raise LimiteDoPlanoError(
            f"No plano {limites.nome}, os parâmetros valem para todos os ativos (o seu padrão). "
            "Parâmetros só para um ativo fazem parte dos planos Plus e Pro."
        )
    if ativos_ja_personalizados >= limites.ativos_com_parametros:
        raise LimiteDoPlanoError(
            f"O plano {limites.nome} guarda parâmetros próprios para até "
            f"{limites.ativos_com_parametros} ativos. Restaure algum ou conheça o plano Pro."
        )


def conferir_watchlist(
    plano: str | None, listas_ja_criadas: int, ativos: int, e_nova: bool
) -> None:
    """Levanta `LimiteDoPlanoError` se a lista passaria dos limites do plano."""
    limites = limites_do(plano)
    if e_nova and listas_ja_criadas >= limites.watchlists:
        raise LimiteDoPlanoError(
            f"O plano {limites.nome} permite {limites.watchlists} "
            f"{'lista' if limites.watchlists == 1 else 'listas'} com nome. "
            "Apague alguma ou conheça os planos Plus e Pro."
        )
    if ativos > limites.ativos_por_watchlist:
        raise LimiteDoPlanoError(
            f"No plano {limites.nome}, cada lista tem até {limites.ativos_por_watchlist} ativos."
        )


def conferir_alerta(plano: str | None, alertas_ja_criados: int) -> None:
    """Levanta `LimiteDoPlanoError` se um alerta novo passaria do limite do plano."""
    limites = limites_do(plano)
    if alertas_ja_criados >= limites.alertas:
        raise LimiteDoPlanoError(
            f"O plano {limites.nome} permite {limites.alertas} "
            f"{'alerta' if limites.alertas == 1 else 'alertas'}. "
            "Apague algum ou conheça os planos Plus e Pro."
        )


def conferir_carteira(plano: str | None) -> None:
    """Levanta `LimiteDoPlanoError` se o plano não guarda a carteira no Research."""
    if not pode_usar(plano, CARTEIRA_NO_RESEARCH):
        raise LimiteDoPlanoError(
            f"O plano {limites_do(plano).nome} não guarda a carteira no Research. Ela faz "
            "parte do Pro."
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


COM_COBRANCA = ("pro",)  # o Plus existe, mas a assinatura dele ainda não está à venda


def tabela_de_planos() -> list[dict[str, str]]:
    """Linhas da tabela de comparação mostrada na tela (uma coluna por plano)."""
    planos = [limites_do(p) for p in PLANOS]

    def linha(recurso: str, valor) -> dict[str, str]:  # noqa: ANN001 (função de cada linha)
        return {"Recurso": recurso, **{l.nome: valor(l) for l in planos}}

    def sim_nao(recurso: str):  # noqa: ANN202
        return lambda l: "Sim" if recurso in l.recursos else "Não"

    def relatorios(l: Limites) -> str:
        tipos = "todos os tipos" if len(l.tipos_de_relatorio) > 1 else "do ativo"
        if l.relatorios_por_dia is None:
            return f"{tipos.capitalize()}, ilimitados"
        return f"{tipos.capitalize()}, {l.relatorios_por_dia} por dia"

    return [
        linha("Simulações salvas", lambda l: descrever_limite(l.simulacoes)),
        linha("Favoritos", lambda l: str(l.favoritos)),
        linha("Ativos na carteira", lambda l: str(l.ativos_na_carteira)),
        linha("Relatórios em PDF", relatorios),
        linha("PDFs originais guardados (1 ano)", lambda l: str(l.pdfs_guardados)),
        linha("Aprendizado de máquina", sim_nao(APRENDIZADO_DE_MAQUINA)),
        linha("Pairs trading", sim_nao(PARES)),
        linha("Carteira no Research", sim_nao(CARTEIRA_NO_RESEARCH)),
        linha("Parâmetros só para um ativo", lambda l: str(l.ativos_com_parametros)),
        linha(
            "Listas do Research",
            lambda l: f"{l.watchlists} de até {l.ativos_por_watchlist} ativos",
        ),
        linha(
            "Alertas compostos",
            lambda l: str(l.alertas),
        ),
        linha("Exportar CSV", lambda l: "Sim"),
    ]
