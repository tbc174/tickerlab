"""As evidências do memorando: o número com rastro, o trecho de documento ou a lacuna da base.

É o subconjunto do `Evidence` do `data_model.md` que o memorando usa. Três tipos:
- **número:** um valor com o `Rastro` completo (fórmula, versão do cálculo, fonte e dia público);
- **trecho:** um fato escrito (o auditor, o setor, o achado de um cruzamento) com o documento ou a
  fonte de onde saiu e o dia em que ficou público;
- **lacuna:** o que a base não tem ou não pode mostrar ("insolvência espera um parecer jurídico"),
  para o memorando dizer o que falta em vez de calar.

Cada evidência vira uma linha da entrada da porta 1 (`como_linha`): a frase só pode escrever os
números, as datas e os nomes das evidências que cita.
"""

from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

from src.analise_escrita import numeros
from src.rastro import Rastro, datas_em_texto
from src.relatorio_empresa import Item

NUMERO, TRECHO, LACUNA = "numero", "trecho", "lacuna"
TIPOS = (NUMERO, TRECHO, LACUNA)
VALOR, AFIRMACAO, DOCUMENTO, PUBLICADO_EM = (
    "valor",
    "afirmação",
    "documento",
    "publicado em",
)


@dataclass(frozen=True)
class Evidencia:
    id: str
    tipo: str
    afirmacao: str  # o que a evidência diz ("Mediana do EV/EBITDA pago: 8,10 vezes")
    publicado_em: date | None  # o dia em que ficou público (a lacuna não tem)
    valor: float | None = None
    unidade: str = ""
    rastro: Rastro | None = None  # o do número
    documento: str = ""  # o do trecho: o documento ou a fonte de onde saiu
    medido_em: str = ""  # de quando é ("12 meses até 30/06/2026")

    def o_que_falta(self) -> list[str]:
        """As partes que faltam para a evidência sustentar uma frase (vazia: completa)."""
        if self.tipo == LACUNA:
            return [] if self.afirmacao else [AFIRMACAO]
        if self.tipo == TRECHO:
            partes = (
                (AFIRMACAO, self.afirmacao),
                (DOCUMENTO, self.documento),
                (PUBLICADO_EM, self.publicado_em),
            )
            return [nome for nome, valor in partes if not valor]
        falta = [] if self.valor is not None else [VALOR]
        if self.rastro is None:
            return [*falta, "rastro"]
        return falta + self.rastro.o_que_falta()

    def como_linha(self) -> dict[str, Any]:
        """A linha da entrada da porta 1: o id e o que a frase que a cita pode escrever."""
        linha: dict[str, Any] = {
            "id": self.id,
            "tipo": self.tipo,
            "afirmacao": self.afirmacao,
            "valor": self.valor,
            "unidade": self.unidade,
            "medido_em": self.medido_em,
            "documento": self.documento,
            "fonte": self.rastro.fonte_id if self.rastro else "",
            "publicado_em": f"{self.publicado_em:%d/%m/%Y}"
            if self.publicado_em
            else "",
        }
        return {k: v for k, v in linha.items() if v not in (None, "")}

    def como_dict(self) -> dict[str, Any]:
        return datas_em_texto(asdict(self))  # type: ignore[return-value]


def do_rastro(
    id: str,
    afirmacao: str,
    valor: float | None,
    rastro: Rastro,
    unidade: str = "",
    medido_em: str = "",
) -> Evidencia:
    """Um número calculado aqui (comps, LBO, pares) com o rastro do cálculo."""
    return Evidencia(
        id,
        NUMERO,
        afirmacao,
        rastro.publicado_em,
        valor,
        unidade,
        rastro,
        "",
        medido_em,
    )


def lacuna(id: str, afirmacao: str) -> Evidencia:
    """O que a base não tem ou não pode mostrar, dito com as palavras de onde a regra mora."""
    return Evidencia(id, LACUNA, afirmacao, None)


def _dia_da_base(base: str) -> date | None:
    """O dia escrito na base do item ("cadastro da CVM em 20/10/2026"); None sem dia completo."""
    dias = [d for d in numeros.datas(base) if d.mes and d.dia]
    return date(dias[-1].ano, dias[-1].mes, dias[-1].dia) if dias else None  # type: ignore[arg-type]


def do_item(secao: str, item: Item) -> Evidencia | None:
    """O item de uma seção da ficha (ou do cadastro) como evidência; None se não há como sustentar.

    Com rastro e valor: número. Com rastro e só texto (o auditor): trecho da fonte do rastro. Sem
    rastro (o cadastro): trecho da fonte do item, com o dia escrito na base.
    """
    id = f"{secao}.{item.chave}"
    afirmacao = f"{item.nome}: {item.texto}"
    if item.rastro is not None and item.valor is not None:
        return Evidencia(
            id,
            NUMERO,
            afirmacao,
            item.rastro.publicado_em,
            float(item.valor),
            item.unidade,
            item.rastro,
            medido_em=item.base,
        )
    if item.rastro is not None:
        documento = item.fonte or item.rastro.fonte_id
        return Evidencia(
            id, TRECHO, afirmacao, item.rastro.publicado_em, documento=documento,
            medido_em=item.base,
        )  # fmt: skip
    if item.fonte and (dia := _dia_da_base(item.base)):
        return Evidencia(
            id, TRECHO, afirmacao, dia, documento=item.fonte, medido_em=item.base
        )
    return None
