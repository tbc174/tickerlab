"""Perfil de vencimentos da dívida de um emissor: quanto vence em cada ano, por indexador.

Soma o **valor emitido** dos instrumentos (`src/divida/instrumentos.py`) que já eram públicos no dia
e ainda não tinham vencido. Não é o saldo devedor: a oferta não diz o que foi amortizado ou
resgatado. O instrumento sem vencimento na fonte fica numa faixa própria (`ano` None), que pode
incluir dívida já paga; o sem valor conta na faixa, mas não soma. Cada faixa tem o rastro, com os
documentos de todos os instrumentos que entraram nela.
"""

from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import date

from base.ofertas import FONTE
from src.divida.instrumentos import VERSAO_DO_CALCULO, DebtInstrument
from src.rastro import Rastro, datas_em_texto

TODOS = "todos"  # o indexador da linha que soma o ano inteiro
FORMULA_DA_FAIXA = (
    "soma de valor_emitido dos instrumentos públicos até D e não vencidos em D, "
    "por ano de vencimento e indexador"
)
FORMULA_DO_ANO = (
    "soma de valor_emitido dos instrumentos públicos até D e não vencidos em D, "
    "por ano de vencimento"
)
LIMITES = (
    (
        "Valor emitido na oferta, não o saldo devedor: amortizações, resgates e recompras não "
        "aparecem nesta fonte."
    ),
    (
        "Só a dívida emitida por oferta registrada na CVM com o CNPJ do próprio emissor: "
        "empréstimos bancários, BNDES, dívida no exterior e a dívida das controladas ficam de fora."
    ),
    (
        "Instrumento sem vencimento na fonte fica na faixa sem ano (pode já ter vencido); sem "
        "indexador legível, na faixa 'não observado'. Nada é estimado."
    ),
)


@dataclass(frozen=True)
class FaixaDoPerfil:
    """Uma célula do perfil: um ano de vencimento (None: não observado) e um indexador."""

    ano: int | None
    indexador: str  # um dos de `DebtInstrument.indexador`, ou TODOS
    valor_emitido: float  # em reais
    instrumentos: tuple[str, ...]  # os ids que entraram, com ou sem valor
    sem_valor: tuple[str, ...]  # os que entraram sem valor observado (não somam)
    rastro: Rastro


@dataclass(frozen=True)
class PerfilDeVencimentos:
    """O perfil de um emissor como era em `como_era_em` (tipos simples, para JSON)."""

    emissor_cnpj: str | None
    como_era_em: date
    faixas: tuple[FaixaDoPerfil, ...]  # por ano e indexador
    por_ano: tuple[FaixaDoPerfil, ...]  # por ano (indexador TODOS)
    ja_vencidos: int  # públicos até D, mas vencidos antes de D
    limites: tuple[str, ...] = LIMITES

    def como_dict(self) -> dict:
        """Para a API: datas em texto ISO."""
        return {k: datas_em_texto(v) for k, v in asdict(self).items()}


def _ordem_do_ano(ano: int | None) -> tuple[bool, int]:
    return (ano is None, ano or 0)  # os anos em ordem, o "sem ano" por último


def _faixa(
    ano: int | None, indexador: str, formula: str, grupo: list[DebtInstrument]
) -> FaixaDoPerfil:
    com_valor = [i.valor_emitido for i in grupo if i.valor_emitido is not None]
    return FaixaDoPerfil(
        ano=ano,
        indexador=indexador,
        valor_emitido=float(sum(com_valor)),
        instrumentos=tuple(i.instrumento_id for i in grupo),
        sem_valor=tuple(i.instrumento_id for i in grupo if i.valor_emitido is None),
        rastro=Rastro.dos_documentos(
            formula,
            VERSAO_DO_CALCULO,
            FONTE,
            [d for i in grupo for d in i.rastro.documentos],
        ),
    )


def _agrupar(
    vivos: list[DebtInstrument], por_indexador: bool
) -> dict[tuple[int | None, str], list[DebtInstrument]]:
    grupos: dict[tuple[int | None, str], list[DebtInstrument]] = {}
    for instrumento in vivos:
        ano = instrumento.vencimento.year if instrumento.vencimento else None
        chave = (ano, instrumento.indexador if por_indexador else TODOS)
        grupos.setdefault(chave, []).append(instrumento)
    return dict(
        sorted(grupos.items(), key=lambda par: (_ordem_do_ano(par[0][0]), par[0][1]))
    )


def perfil_de_vencimentos(
    instrumentos: Iterable[DebtInstrument], como_era_em: date
) -> PerfilDeVencimentos:
    """O perfil dos instrumentos que eram públicos em `como_era_em` e ainda não tinham vencido."""
    publicos = [i for i in instrumentos if i.publico_em <= como_era_em]
    vivos = [i for i in publicos if i.vencimento is None or i.vencimento >= como_era_em]
    emissores = {i.emissor_cnpj for i in publicos}
    return PerfilDeVencimentos(
        emissor_cnpj=emissores.pop() if len(emissores) == 1 else None,
        como_era_em=como_era_em,
        faixas=tuple(
            _faixa(ano, indexador, FORMULA_DA_FAIXA, grupo)
            for (ano, indexador), grupo in _agrupar(vivos, por_indexador=True).items()
        ),
        por_ano=tuple(
            _faixa(ano, TODOS, FORMULA_DO_ANO, grupo)
            for (ano, _), grupo in _agrupar(vivos, por_indexador=False).items()
        ),
        ja_vencidos=len(publicos) - len(vivos),
    )
