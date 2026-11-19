"""As regras de elegibilidade da ficha de crédito (linha 754): cada uma olha um fato e diz se aciona.

Quem tokeniza duplicatas decide com regras simples e explicadas, uma por fato: "sacado com
recuperação judicial ou extrajudicial nos últimos 24 meses: inelegível". Cada regra tem o texto, o
efeito em cada papel (cedente ou sacado), o sinal que olha e o limiar; o resultado é "aciona", "não
aciona" ou "não dá para saber" (o sinal não observado, com o motivo dele), sempre com o valor que
decidiu. Nenhuma regra soma com outra nem dá peso: não há nota, score, selo nem semáforo (ADR 0103).
"""

from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from datetime import date

from src.credito.features import Feature
from src.credito.features_da_base import NENHUMA  # sem situação especial
from src.rastro import datas_em_texto

CEDENTE, SACADO = "cedente", "sacado"
PAPEIS = (CEDENTE, SACADO)
INELEGIVEL, VERIFICAR = "inelegível", "verificar"
ACIONA, NAO_ACIONA, NAO_DA_PARA_SABER = "aciona", "não aciona", "não dá para saber"
ATIVA = "Ativa"  # o texto de `base.receita_codigos.situacao_cadastral("02")`
LIMITE_DE_INADIMPLENCIA_DO_FUNDO = 0.10  # 10% da carteira do fundo inadimplente
SEM_O_SINAL = "O sinal `{chave}` não está na ficha."


class PapelDesconhecidoError(ValueError):
    """O papel da empresa na operação não é cedente nem sacado."""


@dataclass(frozen=True)
class Regra:
    """Uma regra: um fato, um limiar e o efeito em cada papel (None: a regra não vale no papel)."""

    chave: str
    texto: str
    sinal: str
    aciona_quando: Callable[[float | str], bool]
    para_o_cedente: str | None
    para_o_sacado: str | None

    def efeito(self, papel: str) -> str | None:
        return self.para_o_cedente if papel == CEDENTE else self.para_o_sacado


@dataclass(frozen=True)
class ResultadoDaRegra:
    """O que a regra disse para a empresa no papel, com o valor que decidiu e de quando ele é."""

    chave: str
    texto: str
    efeito: str
    resultado: str
    sinal: str
    valor: float | str | None
    disponivel_em: date | None
    motivo: str = ""

    def como_dict(self) -> dict:
        return {k: datas_em_texto(v) for k, v in asdict(self).items()}


def _positivo(valor: float | str) -> bool:
    return float(valor) > 0


def _diferente(esperado: str) -> Callable[[float | str], bool]:
    return lambda valor: str(valor) != esperado


def _acima(limite: float) -> Callable[[float | str], bool]:
    return lambda valor: float(valor) > limite


REGRAS: tuple[Regra, ...] = (
    Regra(
        "insolvencia_nos_ultimos_24_meses",
        "Recuperação judicial ou extrajudicial, falência ou liquidação comunicada à CVM nos últimos "
        "24 meses",
        "insolvencia_24_meses", _positivo, VERIFICAR, INELEGIVEL,
    ),
    Regra(
        "cnpj_fora_da_situacao_ativa",
        "CNPJ que não está com a situação cadastral Ativa na Receita",
        "situacao_cadastral_na_receita", _diferente(ATIVA), INELEGIVEL, INELEGIVEL,
    ),
    Regra(
        "cnpj_com_situacao_especial",
        "CNPJ com situação especial na Receita (falência, recuperação, liquidação, intervenção)",
        "situacao_especial_na_receita", _diferente(NENHUMA), INELEGIVEL, INELEGIVEL,
    ),
    Regra(
        "sancao_vigente_na_cgu",
        "Sanção vigente nos cadastros da CGU (CEIS, CNEP, CEPIM, acordos de leniência)",
        "sancoes_vigentes_na_cgu", _positivo, VERIFICAR, VERIFICAR,
    ),
    Regra(
        "registro_na_lista_suja",
        "Registro na lista de empregadores do Ministério do Trabalho (trabalho análogo ao escravo)",
        "registros_na_lista_suja", _positivo, VERIFICAR, VERIFICAR,
    ),
    Regra(
        "embargo_vigente_no_ibama",
        "Embargo ambiental vigente no IBAMA",
        "embargos_vigentes_no_ibama", _positivo, VERIFICAR, VERIFICAR,
    ),
    Regra(
        "divida_ativa_da_uniao_em_cobranca",
        "Dívida ativa da União em cobrança, sem garantia, suspensão nem negociação (PGFN)",
        "divida_ativa_em_cobranca", _positivo, VERIFICAR, VERIFICAR,
    ),
    Regra(
        "atraso_de_entrega_na_cvm",
        "Atraso na entrega de DFP ou ITR à CVM nas últimas entregas",
        "atrasos_de_entrega_na_cvm", _positivo, VERIFICAR, VERIFICAR,
    ),
    Regra(
        "fundo_do_cedente_com_inadimplencia_alta",
        f"FIDC em que a empresa cede com mais de {LIMITE_DE_INADIMPLENCIA_DO_FUNDO:.0%} da carteira "
        "inadimplente",
        "maior_inadimplencia_dos_fundos_em_que_cede", _acima(LIMITE_DE_INADIMPLENCIA_DO_FUNDO),
        VERIFICAR, None,
    ),
)  # fmt: skip


def _avaliar(regra: Regra, efeito: str, sinal: Feature | None) -> ResultadoDaRegra:
    comum = {
        "chave": regra.chave,
        "texto": regra.texto,
        "efeito": efeito,
        "sinal": regra.sinal,
    }
    if sinal is None:
        return ResultadoDaRegra(
            **comum, resultado=NAO_DA_PARA_SABER, valor=None, disponivel_em=None,
            motivo=SEM_O_SINAL.format(chave=regra.sinal),
        )  # fmt: skip
    if sinal.valor is None:
        return ResultadoDaRegra(
            **comum, resultado=NAO_DA_PARA_SABER, valor=None,
            disponivel_em=sinal.disponivel_em, motivo=sinal.motivo,
        )  # fmt: skip
    resultado = ACIONA if regra.aciona_quando(sinal.valor) else NAO_ACIONA
    return ResultadoDaRegra(
        **comum,
        resultado=resultado,
        valor=sinal.valor,
        disponivel_em=sinal.disponivel_em,
    )


def regras_de_elegibilidade(
    sinais: Iterable[Feature], papel: str
) -> tuple[ResultadoDaRegra, ...]:
    """As regras que valem no papel, cada uma com o resultado, na ordem de `REGRAS`."""
    if papel not in PAPEIS:
        raise PapelDesconhecidoError(f"{papel!r}: o papel é {' ou '.join(PAPEIS)}")
    por_chave = {sinal.chave: sinal for sinal in sinais}
    return tuple(
        _avaliar(regra, efeito, por_chave.get(regra.sinal))
        for regra in REGRAS
        if (efeito := regra.efeito(papel)) is not None
    )
