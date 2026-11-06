"""O evento de pessoa jurídica com três estados e o motor que o tira das leituras de uma fonte (N5).

Sem o estado "fonte falhou", um mês em que a coleta caiu parece um mês calmo. Por isso cada leitura
de uma fonte diz se ela foi lida, e o motor separa três casos:

- **mudou** (`MUDOU`): a fonte foi lida e um campo do objeto tem outro valor que na leitura boa
  anterior. A evidência leva o campo, o valor de antes e o de depois.
- **não observado** (`NAO_OBSERVADO`): a fonte foi lida e o objeto esperado não apareceu (o FIDC que
  não entregou o mês, a companhia que saiu do cadastro).
- **fonte falhou** (`FONTE_FALHOU`): a coleta do período não rodou ou falhou; um evento para cada
  objeto esperado, e a comparação seguinte é com a última leitura boa.

**Esperados:** os objetos pedidos (`esperados`) ou, sem pedido, os da leitura boa anterior. Objeto
novo não gera evento, e objeto que sumiu gera um "não observado" e deixa de ser esperado (só volta
pedido ou quando reaparece).

**Sem olhar o futuro:** o evento só existe a partir de `publico_em`, o dia em que a leitura ficou
pública. O motor anda as leituras na ordem de publicação, então cortar o futuro só tira o fim da
lista: os eventos de antes do corte não mudam (`tests/test_eventos_de_pj.py`).

**Público e só com CNPJ:** `usuario_id` é sempre None, o objeto é o CNPJ (14 caracteres, sem
pontuação) e o motor recusa objeto sem forma de CNPJ: nome de pessoa ou CPF não entram. O texto
que o usuário lê vem com a tela (C-PR05), não daqui. Tipos simples: `como_dict` dá o JSON que uma
rota (`GET /v1/eventos/{cnpj}`) devolveria.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any, Literal

from base.cnpj import normalizar_cnpj
from src.rastro import DocumentoUsado, Rastro

Estado = Literal["mudou", "nao_observado", "fonte_falhou"]
ObjetoTipo = Literal["pj", "fundo"]
MUDOU: Estado = "mudou"
NAO_OBSERVADO: Estado = "nao_observado"
FONTE_FALHOU: Estado = "fonte_falhou"
ORDEM_DO_ESTADO = {FONTE_FALHOU: 0, NAO_OBSERVADO: 1, MUDOU: 2}
ASSUNTO_DA_LEITURA = (
    "leitura"  # o assunto de "não observado" e "fonte falhou": a leitura toda
)
TAMANHO_DO_ID = 16  # caracteres do hash que viram o id do evento


@dataclass(frozen=True)
class Evidencia:
    """Onde está o fato: o arquivo ou quadro, o campo e os valores antes e depois."""

    onde: str
    campo: str
    antes: object
    depois: object


@dataclass(frozen=True)
class EventoDePJ:
    """Um fato público sobre uma PJ ou um fundo, numa fonte, num período, num dos três estados."""

    evento_id: str
    usuario_id: None  # sempre None: evento público
    objeto_tipo: ObjetoTipo
    objeto_id: str  # o CNPJ, 14 caracteres sem pontuação
    estado: Estado
    fonte: str  # o id da coleta em `src/banco/coletas.py`
    assunto: str  # o campo que mudou, a regra que disparou ou "leitura"
    ocorrido_em: date  # o período do fato (o mês do informe, o dia da versão)
    publico_em: date  # desde quando o evento existe
    evidencia: tuple[Evidencia, ...]
    rastro: Rastro

    def como_dict(self) -> dict[str, Any]:
        return _em_dicionario(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class DescricaoDaFonte:
    """O que o motor precisa saber de uma fonte para montar o evento e o rastro."""

    fonte: str
    objeto_tipo: ObjetoTipo
    documento: (
        str  # o nome do arquivo lido, para o rastro ("cadastro de companhias abertas")
    )
    versao_do_calculo: str
    formula: str


@dataclass(frozen=True)
class Tentativa:
    """Uma tentativa de ler o período `periodo` no dia `dia`, que deu certo (`ok`) ou não."""

    periodo: date
    dia: date
    ok: bool


@dataclass(frozen=True)
class Leitura:
    """O que uma fonte mostrou de um período: por objeto (CNPJ), os campos lidos.

    `ok=False` quer dizer que a leitura do período falhou (e então `objetos` não conta).
    """

    periodo: date
    publico_em: date
    ok: bool
    objetos: Mapping[str, Mapping[str, object]]


def leitura_ok(tentativas: Iterable[Tentativa], periodo: date, ate: date) -> bool:
    """Se o período foi lido com sucesso até o dia `ate`."""
    return any(t.ok and t.periodo == periodo and t.dia <= ate for t in tentativas)


def cnpj_do_objeto(valor: str) -> str:
    """O CNPJ normalizado do objeto; recusa o que não tem forma de CNPJ (um nome, um CPF)."""
    cnpj = normalizar_cnpj(valor)
    if cnpj is None:
        raise ValueError("objeto do evento sem forma de CNPJ")
    return cnpj


def _em_dicionario(objeto: object) -> object:
    if isinstance(objeto, date):
        return objeto.isoformat()
    if isinstance(objeto, dict):
        return {k: _em_dicionario(v) for k, v in objeto.items()}
    if isinstance(objeto, (list, tuple)):
        return [_em_dicionario(v) for v in objeto]
    if hasattr(objeto, "__dataclass_fields__"):
        return _em_dicionario(asdict(objeto))  # type: ignore[arg-type]
    return objeto


def id_do_evento(
    descricao: DescricaoDaFonte,
    cnpj: str,
    estado: Estado,
    assunto: str,
    ocorrido_em: date,
    publico_em: date,
) -> str:
    partes = (descricao.fonte, cnpj, estado, assunto, ocorrido_em.isoformat(),
              publico_em.isoformat(), descricao.versao_do_calculo)  # fmt: skip
    return hashlib.sha256("|".join(partes).encode()).hexdigest()[:TAMANHO_DO_ID]


def novo_evento(
    descricao: DescricaoDaFonte,
    cnpj: str,
    estado: Estado,
    assunto: str,
    ocorrido_em: date,
    publico_em: date,
    evidencia: tuple[Evidencia, ...] = (),
) -> EventoDePJ:
    """O evento com o id e o rastro da fonte (o documento lido, público em `publico_em`)."""
    return EventoDePJ(
        evento_id=id_do_evento(
            descricao, cnpj, estado, assunto, ocorrido_em, publico_em
        ),
        usuario_id=None,
        objeto_tipo=descricao.objeto_tipo,
        objeto_id=cnpj,
        estado=estado,
        fonte=descricao.fonte,
        assunto=assunto,
        ocorrido_em=ocorrido_em,
        publico_em=publico_em,
        evidencia=evidencia,
        rastro=Rastro(
            descricao.formula,
            descricao.versao_do_calculo,
            descricao.fonte,
            publico_em,
            documentos=(DocumentoUsado(descricao.documento, publico_em),),
        ),
    )


def _por_cnpj(
    objetos: Mapping[str, Mapping[str, object]],
) -> dict[str, Mapping[str, object]]:
    return {cnpj_do_objeto(chave): campos for chave, campos in objetos.items()}


def _mudancas(
    descricao: DescricaoDaFonte,
    leitura: Leitura,
    cnpj: str,
    antes: Mapping[str, object],
    depois: Mapping[str, object],
) -> list[EventoDePJ]:
    """Um "mudou" por campo que tem outro valor (campo que só um dos lados tem não conta)."""
    return [
        novo_evento(
            descricao,
            cnpj,
            MUDOU,
            campo,
            leitura.periodo,
            leitura.publico_em,
            (Evidencia(descricao.documento, campo, antes[campo], depois[campo]),),
        )
        for campo in sorted(set(antes) & set(depois))
        if antes[campo] != depois[campo]
    ]


def _eventos_da_leitura(
    descricao: DescricaoDaFonte,
    leitura: Leitura,
    anterior: Mapping[str, Mapping[str, object]],
    esperados: Sequence[str],
) -> list[EventoDePJ]:
    def da_leitura(cnpj: str, estado: Estado) -> EventoDePJ:
        return novo_evento(
            descricao,
            cnpj,
            estado,
            ASSUNTO_DA_LEITURA,
            leitura.periodo,
            leitura.publico_em,
        )

    if not leitura.ok:
        return [da_leitura(cnpj, FONTE_FALHOU) for cnpj in esperados]
    objetos = _por_cnpj(leitura.objetos)
    eventos = []
    for cnpj in sorted(set(esperados) | (set(objetos) & set(anterior))):
        if cnpj not in objetos:
            eventos.append(da_leitura(cnpj, NAO_OBSERVADO))
        elif cnpj in anterior:
            eventos.extend(
                _mudancas(descricao, leitura, cnpj, anterior[cnpj], objetos[cnpj])
            )
    return eventos


def eventos_das_leituras(
    leituras: Iterable[Leitura],
    descricao: DescricaoDaFonte,
    *,
    esperados: Iterable[str] | None = None,
) -> list[EventoDePJ]:
    """Os eventos das leituras de uma fonte, na ordem em que ficaram públicas.

    Com `esperados`, só esses objetos contam (os outros são ignorados); sem eles, espera-se quem
    estava na leitura boa anterior.
    """
    pedidos = (
        None if esperados is None else sorted({cnpj_do_objeto(c) for c in esperados})
    )
    anterior: dict[str, Mapping[str, object]] = {}
    eventos: list[EventoDePJ] = []
    for leitura in sorted(leituras, key=lambda item: (item.publico_em, item.periodo)):
        objetos = _por_cnpj(leitura.objetos) if leitura.ok else {}
        if pedidos is not None:
            objetos = {
                cnpj: campos for cnpj, campos in objetos.items() if cnpj in pedidos
            }
        esperados_agora = sorted(anterior) if pedidos is None else pedidos
        eventos.extend(
            _eventos_da_leitura(
                descricao, _com_objetos(leitura, objetos), anterior, esperados_agora
            )
        )
        if leitura.ok:
            anterior = objetos
    return eventos


def _com_objetos(
    leitura: Leitura, objetos: Mapping[str, Mapping[str, object]]
) -> Leitura:
    return Leitura(leitura.periodo, leitura.publico_em, leitura.ok, objetos)


def como_era_em(eventos: Iterable[EventoDePJ], data: date) -> list[EventoDePJ]:
    """Só os eventos que já existiam no dia `data` (`publico_em ≤ data`), na mesma ordem."""
    return [evento for evento in eventos if evento.publico_em <= data]


def em_ordem(eventos: Iterable[EventoDePJ]) -> list[EventoDePJ]:
    """Na ordem da publicação; no mesmo dia e período, falha, ausência e mudança (ordem estável)."""
    return sorted(
        eventos,
        key=lambda e: (e.publico_em, e.ocorrido_em, ORDEM_DO_ESTADO[e.estado]),
    )
