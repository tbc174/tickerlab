"""Relatório de qualidade de cada montagem da base (ADR 0027, exigência 7; critério de pronto do
modelo 8, PR D).

Uma montagem que falha em silêncio (a das demonstrações de 14/10/2026 gravou anos vazios e o log
dizia "saída 0") só aparece quando alguém olha. Aqui cada tabela montada vira um `Resumo` (linhas por
ano, chaves duplicadas e, quando houver valor em reais, a mediana por ano) e `alertas` compara com a
montagem anterior:

- chave duplicada: qualquer uma;
- ano faltando entre o primeiro e o último;
- ano que caiu mais de 10% em linhas, ou sumiu (crescer e ganhar ano novo é o normal);
- escala: a mediana de um ano que mudou 10 vezes ou mais (reais que viraram milhares).

Quem lê a base e monta o resumo é o montador (`scripts/montar_modelo_8.py`); aqui só a regra.
"""

from dataclasses import asdict, dataclass

QUEDA_MAXIMA = 0.10
FATOR_DE_ESCALA = 10


@dataclass(frozen=True)
class Resumo:
    tabela: str
    linhas_por_ano: dict[int, int]
    chaves_duplicadas: int
    escala_por_ano: dict[int, float]

    def para_json(self) -> dict:
        return asdict(self)

    @classmethod
    def do_json(cls, dados: dict) -> "Resumo":
        return cls(
            dados["tabela"],
            {int(a): int(n) for a, n in dados["linhas_por_ano"].items()},
            int(dados["chaves_duplicadas"]),
            {int(a): float(v) for a, v in dados["escala_por_ano"].items()},
        )


def _faltando(anos: list[int]) -> list[int]:
    return sorted(set(range(min(anos), max(anos) + 1)) - set(anos)) if anos else []


def alertas(atual: Resumo, anterior: Resumo | None) -> list[str]:
    """O que está fora na montagem `atual` (lista vazia: tudo certo)."""
    nome = atual.tabela
    saida = []
    if atual.chaves_duplicadas:
        saida.append(f"{nome}: {atual.chaves_duplicadas} chaves duplicadas")
    faltando = _faltando(list(atual.linhas_por_ano))
    if faltando:
        saida.append(f"{nome}: ano faltando: {', '.join(map(str, faltando))}")
    if anterior is None:
        return saida
    for ano, antes in sorted(anterior.linhas_por_ano.items()):
        agora = atual.linhas_por_ano.get(ano)
        if agora is None:
            saida.append(f"{nome}: {ano} sumiu (tinha {antes} linhas)")
        elif agora < antes * (1 - QUEDA_MAXIMA):
            queda = round(100 * (agora - antes) / antes)
            saida.append(
                f"{nome}: {ano} caiu de {antes} para {agora} linhas ({queda}%)"
            )
    for ano, antes in sorted(anterior.escala_por_ano.items()):
        agora = atual.escala_por_ano.get(ano)
        if not agora or not antes:
            continue
        fator = max(agora / antes, antes / agora)
        if fator >= FATOR_DE_ESCALA:
            saida.append(
                f"{nome}: escala de {ano} mudou {fator:.0f} vezes "
                f"(mediana {antes:.0e} → {agora:.0e})"
            )
    return saida
