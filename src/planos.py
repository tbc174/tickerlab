"""Os planos do TickerLab (Gratuito, Plus e Pro) e o que cada um permite.

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
    # Research: ativos com parâmetros próprios (o "seu padrão" vale em todos os planos)
    ativos_com_parametros: int = 0


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
    ),
    "plus": Limites(
        nome="Plus",
        simulacoes=30,
        favoritos=10,
        ativos_na_carteira=6,
        recursos=frozenset(),  # Aprendizado de máquina e Pairs trading ficam no Pro
        relatorios_por_dia=20,
        tipos_de_relatorio=frozenset(TIPOS_DE_RELATORIO),
        ativos_com_parametros=10,  # provisório: aguardando a decisão do Tiago
    ),
    "pro": Limites(
        nome="Pro",
        simulacoes=None,
        favoritos=20,
        ativos_na_carteira=8,
        recursos=frozenset({APRENDIZADO_DE_MAQUINA, PARES}),
        relatorios_por_dia=None,
        tipos_de_relatorio=frozenset(TIPOS_DE_RELATORIO),
        ativos_com_parametros=50,
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
        linha("Aprendizado de máquina", sim_nao(APRENDIZADO_DE_MAQUINA)),
        linha("Pairs trading", sim_nao(PARES)),
        linha("Parâmetros só para um ativo", lambda l: str(l.ativos_com_parametros)),
        linha("Exportar CSV", lambda l: "Sim"),
    ]
