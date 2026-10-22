"""Os planos do TickerLab (Gratuito, Plus e Pro) e o que cada um permite.

Este é o único lugar onde os limites são definidos: a tela, o banco e os testes leem daqui.
Mudar um limite é mudar um número neste arquivo.
"""

from dataclasses import dataclass
from datetime import datetime

from src.banco.modelo import PLANOS, PLANOS_DA_API, TIPOS_DE_RELATORIO

PLANO_DO_MODO_LOCAL = "pro"  # sem contas (desenvolvimento) não há o que limitar

# Pré-lançamento (Tiago, 17/10/2026; emenda à ADR 0029): toda conta usa os limites do Pro, de
# graça, para as pessoas conhecerem o app inteiro. O plano guardado no banco não muda. Desligar
# (False) no mesmo PR que liga a cobrança real e troca `ASSINATURA_SO_PARA_ADMINS`.
TUDO_LIBERADO_NO_PRE_LANCAMENTO = True

APRENDIZADO_DE_MAQUINA = "aprendizado_de_maquina"
PARES = "pares"
CARTEIRA_NO_RESEARCH = (
    "carteira_no_research"  # Research, etapa 5 (PRD, seção 15: no Pro)
)
# relatório da empresa: as seções da base de ML (auditor, ofertas, setor regulado, negócios), ADR 0076
DOSSIE_DA_BASE = "dossie_da_base"
NOMES_DOS_RECURSOS = {
    APRENDIZADO_DE_MAQUINA: "Aprendizado de máquina",
    PARES: "Pairs trading",
    CARTEIRA_NO_RESEARCH: "Carteira no Research",
    DOSSIE_DA_BASE: "Dossiê da base",
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
    # sala de dados por operação (B-20, D6 do plano): só admins por enquanto, os mesmos números
    # em todos os planos até a sala abrir para clientes (o tamanho de cada arquivo e as 300
    # páginas ficam em src/sala/arquivos.py: são regra de segurança, não de plano)
    operacoes_na_sala: int = 20
    documentos_por_operacao: int = 100
    bytes_por_operacao: int = 250 * 1024 * 1024
    envios_por_hora: int = 30


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
        recursos=frozenset(
            {APRENDIZADO_DE_MAQUINA, PARES, CARTEIRA_NO_RESEARCH, DOSSIE_DA_BASE}
        ),
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
    """Os limites que valem para quem está no plano (todas as travas do app passam por aqui).

    No pré-lançamento, os do Pro para todo mundo. Depois, um plano desconhecido ou vazio vale
    como Gratuito (o mais restrito). A tabela de comparação lê `LIMITES_DOS_PLANOS` direto.
    """
    if TUDO_LIBERADO_NO_PRE_LANCAMENTO:
        return LIMITES_DOS_PLANOS["pro"]
    return LIMITES_DOS_PLANOS.get(plano or "", LIMITES_DOS_PLANOS["gratuito"])


def pode_usar(plano: str | None, recurso: str) -> bool:
    return recurso in limites_do(plano).recursos


def plano_que_libera(recurso: str) -> str:
    """O plano mais barato que tem o recurso (a ordem de `PLANOS` vai do Gratuito ao Pro)."""
    for plano in PLANOS:
        if recurso in LIMITES_DOS_PLANOS[plano].recursos:
            return plano
    raise ValueError(f"Nenhum plano tem o recurso {recurso!r}.")


def motivo_sem_acesso(plano: str | None, recurso: str) -> str | None:
    """Por que o plano não usa o recurso (o mesmo texto no app e na API), ou None se usa."""
    if pode_usar(plano, recurso):
        return None
    return (
        f"{NOMES_DOS_RECURSOS[recurso]} faz parte do plano "
        f"{limites_do(plano_que_libera(recurso)).nome}. "
        f"Você está no plano {limites_do(plano).nome}."
    )


def descrever_limite(limite: int | None) -> str:
    return "Ilimitadas" if limite is None else str(limite)


# API externa (N7, ADR 0108): as quotas de cada organização. O plano da API é do contrato com a
# organização, não da conta de uma pessoa, e o pré-lançamento não mexe nele (sem "tudo liberado").
@dataclass(frozen=True)
class LimitesDaApi:
    nome: str
    pedidos_por_minuto: int
    pedidos_por_mes: int
    linhas_por_resposta: int
    chaves_ativas: int  # a antiga de uma rotação e as revogadas não contam


PLANO_DA_API_MAIS_RESTRITO = "piloto"
LIMITES_DA_API = {
    "piloto": LimitesDaApi(
        nome="Piloto",
        pedidos_por_minuto=60,
        pedidos_por_mes=10_000,
        linhas_por_resposta=1_000,
        chaves_ativas=3,
    ),
}
# um plano da API novo no banco exige quotas aqui
assert set(LIMITES_DA_API) == set(PLANOS_DA_API)


def limites_da_api(plano_da_api: str | None) -> LimitesDaApi:
    """As quotas da organização; um plano desconhecido ou vazio vale o mais restrito."""
    return LIMITES_DA_API.get(
        plano_da_api or "", LIMITES_DA_API[PLANO_DA_API_MAIS_RESTRITO]
    )


# a página de planos (o Streamlit e o app novo mostram as mesmas frases)
AVISO_DO_MODO_DE_TESTE = (
    "Pagamento em modo de teste do Stripe: nenhum dinheiro real é cobrado."
)
AVISO_DO_PRE_LANCAMENTO = (
    "Pré-lançamento: todas as contas usam tudo o que o Pro inclui, de graça, até a "
    "cobrança começar. A tabela mostra o que cada plano vai incluir depois."
)


def aviso_da_pagina_de_planos() -> str:
    """O aviso no pé da página de planos (o Streamlit e o app novo mostram o mesmo)."""
    if TUDO_LIBERADO_NO_PRE_LANCAMENTO:
        return f"{AVISO_DO_PRE_LANCAMENTO} {AVISO_DO_MODO_DE_TESTE}"
    return AVISO_DO_MODO_DE_TESTE


def texto_do_uso(usados: int | None, limite: int | None) -> str:
    """ "2 de 5", "3 de ilimitadas" ou "—" (não deu para contar)."""
    return "—" if usados is None else f"{usados} de {descrever_limite(limite).lower()}"


def frase_da_assinatura(
    periodo_fim: datetime | None, cancela_no_fim: bool
) -> str | None:
    """ "Sua assinatura renova (ou termina) em dd/mm/aaaa."; None sem data."""
    if periodo_fim is None:
        return None
    verbo = "termina" if cancela_no_fim else "renova"
    return f"Sua assinatura {verbo} em {periodo_fim:%d/%m/%Y}."


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
    planos = [LIMITES_DOS_PLANOS[p] for p in PLANOS]

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
        linha("Dossiê da base", sim_nao(DOSSIE_DA_BASE)),
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
