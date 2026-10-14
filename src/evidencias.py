"""Evidências: o formato único que todo modelo entrega para os porquês (etapa 1 do desenho em
`docs/desenho-achados-e-porques.md`).

Uma **evidência** é um número com a frase que o explica, de quando ele é, quando ficou público, de
onde veio e por qual regra (com a versão). Os modelos macro, técnicos, fundamentalistas e
quantitativos entregam listas de evidências; a síntese (etapa 3) liga as evidências em porquês.
O nome não é "achado" porque achado já é o problema de qualidade de dados (`base/regras.py`).

Três forças que o relatório nunca mistura:
- **fato:** o número como foi publicado (a Selic é 10,5%);
- **padrão:** o número comparado por uma regra fixa e pública (a margem está no pior quinto do setor);
- **modelo:** a saída de um modelo, que só vale com o `Acerto` contra a previsão ingênua.

Esta etapa traz o tipo e o adaptador das notas que a tela já mostra (`src/notas.py`): a frase e o
número são os mesmos da tela. Tudo em tipos simples: `como_dict` é o que a futura rota da API devolve.
"""

import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import date

import pandas as pd

from src import notas
from src.padroes import (
    INDICADORES,
    UNIDADES,
    VERSAO_DOS_PADROES,
    contas_como_estavam,
    indicadores_da_empresa,
)
from src.setores import grupo_do_setor

MACRO, TECNICO, FUNDAMENTALISTA, QUANTITATIVO = (
    "macro",
    "tecnico",
    "fundamentalista",
    "quantitativo",
)
TIPOS = (MACRO, TECNICO, FUNDAMENTALISTA, QUANTITATIVO)
FATO, PADRAO, MODELO = "fato", "padrao", "modelo"
FORCAS = (FATO, PADRAO, MODELO)
PREFIXO_FUNDAMENTALISTA = "fund"
LIMITE_DA_FAIXA = (
    "A faixa é uma regra fixa e pública: diz como o número está, não o que vai acontecer. "
    "Não é recomendação de compra ou venda."
)


class EvidenciaInvalidaError(ValueError):
    """A evidência quebra uma regra do formato (tipo, força, data ou acerto)."""


@dataclass(frozen=True)
class Acerto:
    """Quanto um modelo venceu a previsão ingênua, fora da amostra (só para força "modelo")."""

    metrica: str  # "erro médio absoluto"
    modelo: float
    ingenuo: float
    periodo: str  # "2015-2025"
    testado_em: date


@dataclass(frozen=True)
class Evidencia:
    id: str  # estável entre versões: "fund.cobertura_de_juros.ruim"
    tipo: str
    ativo: str | None  # "PETR4.SA"; None para evidência de mercado (a Selic)
    frase: str
    valor: float | None  # None: indisponível, e a frase diz o motivo
    unidade: str
    data_de_corte: date
    divulgado_em: date | None  # quando o número ficou público; nunca depois do corte
    fonte: str
    regra: str  # a regra e a versão dela: "padroes/roe@1"
    forca: str
    acerto: Acerto | None = None
    limites: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        _conferir_classificacao(self)
        _conferir_datas(self)
        _conferir_acerto(self)

    def como_dict(self) -> dict:
        """Para a API: datas em texto ISO."""
        return _datas_em_texto(asdict(self))


def _conferir_classificacao(evidencia: Evidencia) -> None:
    if evidencia.tipo not in TIPOS:
        raise EvidenciaInvalidaError(f"Tipo desconhecido: {evidencia.tipo}.")
    if evidencia.forca not in FORCAS:
        raise EvidenciaInvalidaError(f"Força desconhecida: {evidencia.forca}.")


def _conferir_datas(evidencia: Evidencia) -> None:
    """Sem olhar o futuro: o número precisa ter sido público na data de corte."""
    if evidencia.divulgado_em is None:
        if evidencia.valor is not None:
            raise EvidenciaInvalidaError("Número sem data de divulgação.")
        return
    if evidencia.divulgado_em > evidencia.data_de_corte:
        raise EvidenciaInvalidaError(
            f"{evidencia.id}: divulgado em {evidencia.divulgado_em}, depois do corte "
            f"{evidencia.data_de_corte}."
        )


def _conferir_acerto(evidencia: Evidencia) -> None:
    """Modelo só fala com o acerto contra a previsão ingênua; fato e padrão não têm acerto."""
    if evidencia.forca == MODELO and evidencia.acerto is None:
        raise EvidenciaInvalidaError(f"{evidencia.id}: modelo sem o acerto medido.")
    if evidencia.forca != MODELO and evidencia.acerto is not None:
        raise EvidenciaInvalidaError(f"{evidencia.id}: só modelo leva acerto.")


def _datas_em_texto(valor: object) -> object:
    if isinstance(valor, dict):
        return {chave: _datas_em_texto(v) for chave, v in valor.items()}
    if isinstance(valor, list | tuple):
        return [_datas_em_texto(v) for v in valor]
    return valor.isoformat() if isinstance(valor, date) else valor


# --- adaptador das notas (src/notas.py) ------------------------------------------------------------
def _sem_acento(texto: str) -> str:
    decomposto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in decomposto if not unicodedata.combining(c))


def _id_fundamentalista(indicador: str, nota: str) -> str:
    rotulo = _sem_acento(nota).lower().replace(" ", "-")
    return f"{PREFIXO_FUNDAMENTALISTA}.{indicador}.{rotulo}"


def de_nota(
    nota: notas.Nota | notas.NotaPorFaixa,
    ativo: str | None,
    data_de_corte: date,
    divulgado_em: date,
) -> Evidencia:
    """A evidência de uma nota da tela: a mesma frase (`nota.texto`) e o mesmo número.

    `divulgado_em`: a entrega à CVM mais recente usada no cálculo (`ultima_divulgacao`).
    """
    if isinstance(nota, notas.NotaPorFaixa):
        faixa = notas.FAIXAS_FIXAS[nota.indicador]
        unidade = faixa.unidade
        regra = f"faixa-fixa/{nota.indicador}@{notas.VERSAO_DAS_FAIXAS}"
        limites: tuple[str, ...] = (LIMITE_DA_FAIXA,)
    else:
        unidade = UNIDADES[nota.indicador]
        regra = f"padroes/{nota.indicador}@{VERSAO_DOS_PADROES}"
        limites = (notas.AVISO,)
    return Evidencia(
        id=_id_fundamentalista(nota.indicador, nota.nota),
        tipo=FUNDAMENTALISTA,
        ativo=ativo,
        frase=nota.texto,
        valor=nota.valor,
        unidade=unidade,
        data_de_corte=data_de_corte,
        divulgado_em=divulgado_em,
        fonte=notas.FONTE,
        regra=regra,
        forca=PADRAO,
        limites=limites,
    )


def ultima_divulgacao(documentos: pd.DataFrame, data_de_corte: date) -> date | None:
    """A entrega à CVM mais recente até o corte (inclusive), ou None se nada era público."""
    recebidos = pd.to_datetime(documentos["recebido_em"])
    ate_o_corte = recebidos[recebidos <= pd.Timestamp(data_de_corte)]
    return None if ate_o_corte.empty else ate_o_corte.max().date()


@dataclass(frozen=True)
class EntradaFundamentalista:
    """O que a etapa fundamentalista precisa de uma empresa, com todas as versões guardadas."""

    contas: (
        pd.DataFrame
    )  # cnpj, documento, referencia, versao, periodo, inicio, fim, conta, valor
    documentos: pd.DataFrame  # cnpj, documento, referencia, versao, recebido_em
    setor: str
    padroes: pd.DataFrame  # os padrões do mesmo corte (`padroes.calcular_padroes`)
    ativo: str | None = None
    em_conferencia: bool = False


def fundamentalistas_em(
    entrada: EntradaFundamentalista, data_de_corte: date
) -> list[Evidencia]:
    """As evidências das notas da empresa só com o que era público na data de corte.

    Usa as mesmas funções dos padrões e da tela: versões entregues até o corte
    (`contas_como_estavam`), indicadores (`indicadores_da_empresa`) e notas (`notas_da_empresa`).
    """
    divulgado_em = ultima_divulgacao(entrada.documentos, data_de_corte)
    if divulgado_em is None:
        return []
    contas = contas_como_estavam(
        entrada.contas, entrada.documentos, pd.Timestamp(data_de_corte)
    )
    valores = indicadores_da_empresa(contas.drop(columns="cnpj"), entrada.setor)
    com_padrao = {chave: valores[chave] for chave in INDICADORES}
    lista = notas.notas_da_empresa(
        com_padrao,
        grupo_do_setor(entrada.setor),
        entrada.padroes,
        data_de_corte,
        entrada.em_conferencia,
    )
    return [de_nota(n, entrada.ativo, data_de_corte, divulgado_em) for n in lista]
