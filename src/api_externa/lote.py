"""A consulta em lote da API externa: até 100 CNPJs por chamada (B-32a, PR 1).

O cliente-norte é o raio-x de carteira no lote noturno: uma chamada com os CNPJs da carteira em vez de
uma por empresa. A regra da quota (plano da B-32a, risco 4): **um lote de N CNPJs distintos e válidos
conta N** na quota do mês e **1** no limite do minuto (que é de chamadas). A rota confere a quota de N
**antes** de servir (`acesso.exigir_quota`) e o lote que não cabe volta inteiro com 429, sem servir
metade.

Só entra CNPJ de 14 caracteres com o DV certo (`base.cnpj.completo`): um CPF de 11 dígitos nunca vira
"CNPJ" completado com zeros, então o lote não serve de busca por pessoa. O item inválido não conta na
quota; volta com o status `invalid_cnpj` (`nomes.situacao_do_item`).
"""

from dataclasses import dataclass

from base.cnpj import completo, dv_confere

MAXIMO_DO_LOTE = 100
ECO_MAXIMO = 32  # o item inválido volta como veio, cortado: um CNPJ formatado tem 18


class LoteInvalidoError(ValueError):
    """Lote vazio ou com mais itens que `MAXIMO_DO_LOTE`: a rota responde 400."""


@dataclass(frozen=True)
class Lote:
    """Os CNPJs do lote: os válidos, sem repetição e na ordem do pedido, e os inválidos como vieram."""

    validos: list[str]
    invalidos: list[str]

    @property
    def pedidos(self) -> int:
        """Quanto o lote conta na quota do mês: um por CNPJ válido, e ao menos um pela chamada."""
        return max(1, len(self.validos))


def _cnpj_do_item(item: object) -> str | None:
    cnpj = completo(item)
    return cnpj if cnpj is not None and dv_confere(cnpj) else None


def ler_lote(itens: list[object]) -> Lote:
    """Separa os CNPJs válidos (desduplicados) dos inválidos; recusa o lote vazio ou grande demais.

    O teto conta os itens enviados, não os distintos: ele protege o servidor, a quota é a dos válidos.
    """
    if not itens:
        raise LoteInvalidoError("lote vazio")
    if len(itens) > MAXIMO_DO_LOTE:
        raise LoteInvalidoError(f"mais de {MAXIMO_DO_LOTE} itens")
    validos: dict[str, None] = {}  # dict guarda a ordem do pedido
    invalidos: list[str] = []
    for item in itens:
        cnpj = _cnpj_do_item(item)
        if cnpj is None:
            invalidos.append(str(item)[:ECO_MAXIMO])
        else:
            validos.setdefault(cnpj)
    return Lote(validos=list(validos), invalidos=invalidos)
