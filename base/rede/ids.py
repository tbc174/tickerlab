"""Id determinístico de cada entidade da rede (ADR 0077, item 1; plano da série, D4).

O id é `"E"` + os 20 primeiros hexadecimais do SHA-256 de `tipo|sistema|valor` do **identificador
primário**: montar a base de novo, em qualquer ordem, dá os mesmos ids, sem tabela de sequência. 80 bits
sobram para milhões de entidades, e uma colisão (duas entidades com o mesmo id) é erro, nunca fusão.

O primário segue a ordem da ADR: raiz do CNPJ (empresa) > CNPJ de 14 (fundo) > LEI > ISIN (valor
mobiliário) > código de regulador (`codigo_*`) > nome normalizado com a fonte (`nome:*`). Ticker e
emissor não dão identidade (mudam de dono). Quando a regra mudaria o id de uma entidade que já existe
(uma incorporação que troca a raiz), `base/conferidas/entidades.csv` fixa o id antigo.
"""

import hashlib
from collections.abc import Iterable
from pathlib import Path

import pandas as pd

PREFIXO = "E"
# o id de pessoa (esquema `pessoas`, PR 6) começa por "P": só existe na vista interna, nunca sai de casa
PREFIXO_DE_PESSOA = "P"
HEXADECIMAIS = 20
TABELA_CONFERIDA = (
    Path(__file__).resolve().parent.parent / "conferidas" / "entidades.csv"
)
ORDEM_DOS_SISTEMAS = ("cnpj_raiz", "cnpj", "lei", "isin")
PREFIXO_DE_REGULADOR = "codigo_"
PREFIXO_DE_NOME = "nome:"
Chave = tuple[str, str, str]  # (tipo, sistema, valor)


def id_entidade(tipo: str, sistema: str, valor: str) -> str:
    """'E' + 20 hexadecimais do SHA-256 de `tipo|sistema|valor`."""
    texto = f"{tipo}|{sistema}|{valor}".encode()
    return PREFIXO + hashlib.sha256(texto).hexdigest()[:HEXADECIMAIS]


def _posicao(sistema: str) -> int | None:
    if sistema in ORDEM_DOS_SISTEMAS:
        return ORDEM_DOS_SISTEMAS.index(sistema)
    if sistema.startswith(PREFIXO_DE_REGULADOR):
        return len(ORDEM_DOS_SISTEMAS)
    if sistema.startswith(PREFIXO_DE_NOME):
        return len(ORDEM_DOS_SISTEMAS) + 1
    return None  # ticker, emissor, NIRE: identificam, mas não dão identidade


def identificador_primario(
    identificadores: Iterable[tuple[str, str]],
) -> tuple[str, str]:
    """O (sistema, valor) que dá o id, pela ordem fixa; entre códigos de regulador, o menor.

    Dois valores no mesmo sistema primário (duas raízes) é erro: a entidade está mal montada.
    """
    candidatos = sorted(
        (posicao, sistema, valor)
        for sistema, valor in set(identificadores)
        if (posicao := _posicao(sistema)) is not None
    )
    if not candidatos:
        raise ValueError("entidade sem identificador primário (só ticker ou emissor?)")
    posicao, sistema, valor = candidatos[0]
    repetidos = [v for p, s, v in candidatos if s == sistema and v != valor]
    if repetidos:
        raise ValueError(
            f"entidade com dois valores em {sistema}: {valor} e {repetidos[0]}"
        )
    return sistema, valor


def ids_fixados(caminho: Path = TABELA_CONFERIDA) -> dict[Chave, str]:
    """(tipo, sistema, valor) -> id antigo, da tabela conferida à mão."""
    tabela = pd.read_csv(
        caminho, sep=";", dtype=str, keep_default_na=False, encoding="utf-8"
    )
    return {
        (linha.tipo, linha.sistema, linha.valor): linha.id_entidade
        for linha in tabela.itertuples(index=False)
    }


def atribuir_ids(primarios: pd.DataFrame, fixados: dict[Chave, str]) -> pd.Series:
    """O id de cada linha (`tipo`, `sistema`, `valor` do primário); colisão é erro."""
    chaves = list(
        zip(primarios["tipo"], primarios["sistema"], primarios["valor"], strict=True)
    )
    unicas = {chave: fixados.get(chave) or id_entidade(*chave) for chave in set(chaves)}
    donos: dict[str, Chave] = {}
    for chave, id_ in sorted(unicas.items()):
        if id_ in donos:
            raise ValueError(f"colisão de id {id_}: {donos[id_]} e {chave}")
        donos[id_] = chave
    return pd.Series(
        [unicas[c] for c in chaves], index=primarios.index, name="id_entidade"
    )
