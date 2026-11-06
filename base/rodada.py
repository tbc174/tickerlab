"""Rodada das regras de qualidade sobre os arquivos anuais da CVM (série 1 da base de ML, PR 3).

Junta os arquivos lidos por `base/contas_cvm.py` e decide que regras de `base/regras.py` rodam com
o que existe. Devolve **rodadas**: as regras que rodaram, sobre que documento e datas, e os achados
(o banco só fecha achados das regras que rodaram; ver `src/banco/qualidade.py`).

- **Um documento só** (R1, R2, R11, R4, R10, R9): todo arquivo.
- **R3:** precisa do arquivo do ano anterior. **R6:** do ano seguinte (o achado vale a partir da
  entrega do documento seguinte). **R7:** do próprio arquivo e dos eventos do IPE. **R8:** do ano
  anterior (quem entregou lá deve entregar de novo) e do cadastro (registrada e não cancelada na
  data do prazo).
- **R5** (reapresentação) fica para o leitor do ENET (PR 5): o arquivo anual da CVM só traz as
  contas da versão mais nova.
- **De quando vale:** achado sem data própria vale a partir da entrega da versão mais nova do
  documento (o arquivo traz as contas dessa versão): nunca antes do que se podia saber.
- **Uma regra quebrada** (erro inesperado nos dados) fica de fora da rodada e vai para `falhas`;
  as outras seguem.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field, replace

import pandas as pd

from base.contas_cvm import LeituraDeContas
from base.regras import (
    Achado,
    contas_principais,
    r1_ativo_passivo,
    r2_subtotais,
    r3_escala,
    r4_impossivel,
    r6_refeito_no_seguinte,
    r7_salto_fora_do_padrao,
    r8_atraso,
    r9_repetidas,
    r10_lucro_em_branco,
    r11_mae_em_branco,
)
from src.prazos import prazo

log = logging.getLogger(__name__)

REGRAS_DE_UM_DOCUMENTO = ("R1", "R2", "R11", "R4", "R10", "R9")
UM_ANO = pd.DateOffset(years=1)


@dataclass(frozen=True)
class Arquivo:
    """O que fica de um arquivo anual depois das regras de um documento só (cabe na memória)."""

    documento: str  # DFP ou ITR
    ano: int
    principais: pd.DataFrame  # `contas_principais` (R3, R6 e R7 só usam essas)
    indice: pd.DataFrame  # `ler_indice`: todas as entregas, com a data


@dataclass(frozen=True)
class Rodada:
    regras: tuple[str, ...]  # as que rodaram (só os achados delas podem ser fechados)
    documento: str
    referencias: tuple[pd.Timestamp, ...]
    achados: list[Achado]
    falhas: tuple[str, ...] = field(default=())


def principais(contas: pd.DataFrame) -> pd.DataFrame:
    """As contas que as regras entre documentos usam (ativo total, receita, lucro, patrimônio)."""
    return contas_principais(contas).reset_index(drop=True)


def _tentar(regra: str, funcao: Callable[[], list[Achado]]) -> list[Achado] | None:
    try:
        return funcao()
    except Exception:  # um dado inesperado não pode derrubar as outras regras
        log.exception("Regra %s falhou", regra)
        return None


def _rodar(
    regras: dict[str, Callable[[], list[Achado]]],
) -> tuple[list[Achado], tuple[str, ...], tuple[str, ...]]:
    achados: list[Achado] = []
    rodaram, falharam = [], []
    for regra, funcao in regras.items():
        resultado = _tentar(regra, funcao)
        if resultado is None:
            falharam.append(regra)
        else:
            rodaram.append(regra)
            achados += resultado
    return achados, tuple(rodaram), tuple(falharam)


def _entrega_mais_nova(
    indice: pd.DataFrame,
) -> dict[tuple[str, pd.Timestamp], pd.Timestamp]:
    """(cnpj, referencia) → data de entrega da versão mais nova (a das contas do arquivo)."""
    datas = indice.groupby(["cnpj", "referencia"])["recebido_em"].max()
    return {chave: pd.Timestamp(data) for chave, data in datas.items()}  # type: ignore[misc]


def _com_data(
    achados: list[Achado], documento: str, indice: pd.DataFrame, hoje: pd.Timestamp
) -> list[Achado]:
    """Preenche o documento (a R9 não sabe) e a data de quem não tem data própria."""
    mais_nova = _entrega_mais_nova(indice)
    return [
        replace(
            a,
            documento=documento,
            valido_desde=a.valido_desde
            if a.valido_desde is not None
            else mais_nova.get((a.cnpj, pd.Timestamp(a.referencia)), hoje),
        )
        for a in achados
    ]


def _referencias(*colunas: pd.Series) -> tuple[pd.Timestamp, ...]:
    datas = pd.concat([pd.Series(c, dtype="datetime64[ns]") for c in colunas]).dropna()
    return tuple(sorted({pd.Timestamp(d) for d in datas}))


def regras_de_um_documento(
    leitura: LeituraDeContas, documento: str, indice: pd.DataFrame, hoje: pd.Timestamp
) -> Rodada:
    """R1, R2, R11, R4, R10 e R9 sobre um arquivo anual inteiro."""
    contas = leitura.contas
    achados, rodaram, falharam = _rodar(
        {
            "R1": lambda: r1_ativo_passivo(contas),
            "R2": lambda: r2_subtotais(contas),
            "R11": lambda: r11_mae_em_branco(contas),
            "R4": lambda: r4_impossivel(contas),
            "R10": lambda: r10_lucro_em_branco(contas),
            "R9": lambda: r9_repetidas(leitura),
        }
    )
    referencias = _referencias(
        contas["referencia"], leitura.repetidas["referencia"], indice["referencia"]
    )
    return Rodada(
        rodaram,
        documento,
        referencias,
        _com_data(achados, documento, indice, hoje),
        falharam,
    )


def _r6(atual: Arquivo, seguinte: Arquivo) -> list[Achado]:
    """R6 contra cada documento do arquivo seguinte (o ITR tem três), com a data de cada um."""
    mais_nova = _entrega_mais_nova(seguinte.indice)
    achados: list[Achado] = []
    for referencia, contas in seguinte.principais.groupby("referencia"):
        recebido = {
            cnpj: data for (cnpj, ref), data in mais_nova.items() if ref == referencia
        }
        achados += r6_refeito_no_seguinte(atual.principais, contas, recebido)
    return achados


def esperadas(
    anterior: pd.DataFrame, cadastro: pd.DataFrame, limite: pd.Timestamp
) -> pd.DataFrame:
    """Quem deve o documento: entregou o do ano anterior e estava registrada no prazo.

    Leva a `uf` da sede quando o cadastro a tem (o prazo do ITR de 2024 muda no RS).
    """
    registrada = (cadastro["registro"].isna() | (cadastro["registro"] <= limite)) & (
        cadastro["cancelamento"].isna() | (cadastro["cancelamento"] > limite)
    )
    ativas = set(cadastro.loc[registrada, "cnpj"])
    devem = (
        anterior[anterior["cnpj"].isin(ativas)][["cnpj", "empresa"]]
        .drop_duplicates("cnpj")
        .reset_index(drop=True)
    )
    if "uf" in cadastro:
        uf = cadastro.drop_duplicates("cnpj").set_index("cnpj")["uf"]
        devem["uf"] = devem["cnpj"].map(uf).fillna("")
    return devem


def _r8(
    atual: Arquivo, anterior: Arquivo, cadastro: pd.DataFrame, hoje: pd.Timestamp
) -> tuple[tuple[pd.Timestamp, ...], list[Achado]]:
    achados: list[Achado] = []
    referencias = []
    for ref_anterior, deles in anterior.indice.groupby("referencia"):
        referencia = pd.Timestamp(ref_anterior) + UM_ANO  # type: ignore[arg-type]
        referencias.append(referencia)
        limite = pd.Timestamp(prazo(atual.documento, referencia.date()))
        devem = esperadas(deles, cadastro, limite)
        achados += r8_atraso(devem, atual.indice, atual.documento, referencia, hoje)
    return tuple(sorted(referencias)), achados


def regras_entre_documentos(
    atual: Arquivo,
    anterior: Arquivo | None,
    seguinte: Arquivo | None,
    eventos: pd.DataFrame,
    cadastro: pd.DataFrame | None,
    hoje: pd.Timestamp,
) -> list[Rodada]:
    """As regras que comparam o arquivo com o anterior, o seguinte ou os eventos do IPE.

    Uma rodada por regra, porque cada uma cobre datas diferentes (a R8 olha as datas que o arquivo
    deveria ter, não as que ele tem).
    """
    datas = _referencias(atual.principais["referencia"], atual.indice["referencia"])
    regras: dict[str, Callable[[], list[Achado]]] = {
        "R7": lambda: r7_salto_fora_do_padrao(atual.principais, eventos)
    }
    if anterior is not None:
        regras["R3"] = lambda: r3_escala(atual.principais, anterior.principais)
    if seguinte is not None:
        regras["R6"] = lambda: _r6(atual, seguinte)
    rodadas = []
    for regra, funcao in regras.items():
        achados, rodaram, falharam = _rodar({regra: funcao})
        com_data = _com_data(achados, atual.documento, atual.indice, hoje)
        rodadas.append(Rodada(rodaram, atual.documento, datas, com_data, falharam))
    if anterior is not None and cadastro is not None:
        rodadas.append(_rodada_r8(atual, anterior, cadastro, hoje))
    return rodadas


def _rodada_r8(
    atual: Arquivo, anterior: Arquivo, cadastro: pd.DataFrame, hoje: pd.Timestamp
) -> Rodada:
    try:
        referencias, achados = _r8(atual, anterior, cadastro, hoje)
    except Exception:  # mesma regra das outras: falha não derruba a rodada
        log.exception("Regra R8 falhou")
        return Rodada((), atual.documento, (), [], ("R8",))
    return Rodada(("R8",), atual.documento, referencias, achados)
