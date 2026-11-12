"""As cópias reduzidas que a lista de compradores lê no VPS (linha 844): o filtro e a trava.

A lista de compradores por setor (`src/api_externa/conjuntos/compradores.py`) tem dois sinais que vêm de tabelas
que ficam em casa: a controlada no setor (`controladas`, do FRE, com a razão social de cada sociedade, que pode
ser pessoa) e o fundo sócio (`registro_de_fundos`, com o gestor e o administrador). Ao VPS vai uma cópia **com
nome próprio**, mais estreita que a tabela inteira:

- **controladas_pj**: só `cnpj_companhia`, `cnpj`, `tipo`, `participacao`, `referencia`, `versao` e `publico_em`
  (o `conhecido_em` do FRE), só da companhia cuja raiz está na `cnpj_empresas_pj` da mesma saída e só a
  controlada cuja raiz também está lá. Sem `razao_social` nem `companhia`. Cada documento (companhia,
  referência, versão) ganha ainda **uma linha de marca**, com `cnpj`, `tipo` e `participacao` vazios: sem ela,
  o FRE novo que só tem controladas fora da lista sumiria, e o antigo voltaria a valer como o mais recente.
- **fips_registrados**: só `CNPJ_Fundo`, `Tipo_Fundo`, `Data_Registro` e `Data_Cancelamento`, só FIP, só raiz da
  `cnpj_empresas_pj` da saída, sem repetir o fundo por gestor. Sem gestor, administrador, nome nem CPF. A CVM
  não dá carimbo de público por linha: a data é a do registro, como na tabela inteira.

`conferir_reduzidas` lê **a saída** e derruba a montagem (`ReduzidaComPessoa`) em qualquer coisa fora disso, sem
depender do filtro: coluna fora da lista (gestor, nome), raiz fora da lista sem pessoa, controlada sem CNPJ com
tipo ou participação, fundo que não é FIP. A mensagem leva só contagens, nunca um CNPJ ou um nome (vai ao log e
ao aviso do Kuma).
"""

from collections.abc import Mapping, Sequence
from pathlib import Path

import duckdb

from base.porta.duckdb import fonte_dos_arquivos

CONTROLADAS_PJ, FIPS_REGISTRADOS = "controladas_pj", "fips_registrados"
REDUZIDAS = (CONTROLADAS_PJ, FIPS_REGISTRADOS)
# de que tabela inteira cada cópia sai
ORIGEM = {CONTROLADAS_PJ: "controladas", FIPS_REGISTRADOS: "registro_de_fundos"}
COLUNAS: dict[str, tuple[str, ...]] = {
    CONTROLADAS_PJ: ("cnpj_companhia", "cnpj", "tipo", "participacao", "referencia", "versao", "publico_em"),
    FIPS_REGISTRADOS: ("CNPJ_Fundo", "Tipo_Fundo", "Data_Registro", "Data_Cancelamento"),
}  # fmt: skip
# pedaços de nome de coluna que nunca saem (o teste confere que a lista acima não tem nenhum)
PEDACOS_PROIBIDOS = (
    "gestor",
    "administrador",
    "cpf",
    "razao",
    "denominacao",
    "companhia_nome",
    "nome",
)
FIP = "FIP"
TAMANHO_DA_RAIZ = 8


class ReduzidaComPessoa(Exception):
    """A cópia reduzida tem (ou pode ter) pessoa ou gestor: nada sai de casa."""


def _aspas(texto: str) -> str:
    return "'" + texto.replace("'", "''") + "'"


def _raiz(coluna: str) -> str:
    """A raiz do CNPJ como a lista de compradores a lê: os 8 primeiros caracteres sem pontuação."""
    return f"substr(regexp_replace(CAST({coluna} AS VARCHAR), '[^0-9A-Za-z]', '', 'g'), 1, {TAMANHO_DA_RAIZ})"


def _lista_pj(empresas_pj: Sequence[Path]) -> str:
    if not empresas_pj:
        raise ReduzidaComPessoa(
            "sem cnpj_empresas_pj na saída: não dá para conferir as raízes"
        )
    return f"SELECT DISTINCT cnpj_basico FROM {fonte_dos_arquivos(empresas_pj)} WHERE cnpj_basico IS NOT NULL"


def _contar(con: duckdb.DuckDBPyConnection, consulta: str) -> int:
    linha = con.execute(f"SELECT count(*) FROM ({consulta})").fetchone()
    return int(linha[0]) if linha else 0


def _copiar(con: duckdb.DuckDBPyConnection, consulta: str, destino: Path) -> int:
    destino.parent.mkdir(parents=True, exist_ok=True)
    con.execute(
        f"COPY ({consulta}) TO {_aspas(destino.as_posix())} (FORMAT PARQUET, COMPRESSION ZSTD)"
    )
    return _contar(con, f"SELECT * FROM {fonte_dos_arquivos([destino])}")


def montar_controladas_pj(
    con: duckdb.DuckDBPyConnection,
    origem: Sequence[Path],
    empresas_pj: Sequence[Path],
    destino: Path,
) -> int:
    """Escreve `controladas_pj` em `destino` a partir dos Parquets de `controladas`; devolve as linhas que saíram."""
    pj = _lista_pj(empresas_pj)
    fonte = fonte_dos_arquivos(origem)
    da_lista = f"{_raiz('cnpj_companhia')} IN ({pj}) AND conhecido_em IS NOT NULL"
    consulta = (
        "SELECT cnpj_companhia, cnpj, tipo, participacao, referencia, versao, conhecido_em AS publico_em "
        f"FROM {fonte} WHERE {da_lista} AND cnpj IS NOT NULL AND {_raiz('cnpj')} IN ({pj}) "
        # a marca de cada documento: guarda qual é o FRE mais recente da companhia
        "UNION ALL SELECT DISTINCT cnpj_companhia, NULL::VARCHAR, NULL::VARCHAR, NULL::DOUBLE, referencia, versao, "
        f"conhecido_em FROM {fonte} WHERE {da_lista} "
        "ORDER BY cnpj_companhia, referencia, versao, cnpj NULLS LAST"
    )
    return _copiar(con, consulta, destino)


def montar_fips_registrados(
    con: duckdb.DuckDBPyConnection,
    origem: Sequence[Path],
    empresas_pj: Sequence[Path],
    destino: Path,
) -> int:
    """Escreve `fips_registrados` em `destino` a partir do `registro_de_fundos`; devolve as linhas que saíram."""
    pj = _lista_pj(empresas_pj)
    consulta = (
        f"SELECT DISTINCT {', '.join(COLUNAS[FIPS_REGISTRADOS])} FROM {fonte_dos_arquivos(origem)} "
        f"WHERE Tipo_Fundo = {_aspas(FIP)} AND {_raiz('CNPJ_Fundo')} IN ({pj}) "
        "ORDER BY CNPJ_Fundo, Data_Registro"
    )
    return _copiar(con, consulta, destino)


# --- a trava ----------------------------------------------------------------------------------------


def _problemas_de_coluna(
    con: duckdb.DuckDBPyConnection, nome: str, fonte: str
) -> list[str]:
    colunas = [
        c for (c, *_) in con.execute(f"DESCRIBE SELECT * FROM {fonte}").fetchall()
    ]
    problemas = []
    if fora := [c for c in colunas if c not in COLUNAS[nome]]:
        de_gestor = sum(any(p in c.lower() for p in PEDACOS_PROIBIDOS) for c in fora)
        problemas.append(
            f"{nome}: {len(fora)} coluna(s) fora da lista ({de_gestor} de nome, gestor ou CPF)"
        )
    if faltam := sorted(set(COLUNAS[nome]) - set(colunas)):
        problemas.append(f"{nome}: sem {faltam}")
    return problemas


def _consultas_de_linha(nome: str, fonte: str, pj: str) -> dict[str, str]:
    if nome == CONTROLADAS_PJ:
        return {
            "linha(s) com a raiz fora da lista sem pessoa": (
                f"SELECT * FROM {fonte} WHERE cnpj_companhia IS NULL OR {_raiz('cnpj_companhia')} NOT IN ({pj}) "
                f"OR (cnpj IS NOT NULL AND {_raiz('cnpj')} NOT IN ({pj}))"
            ),
            "linha(s) sem CNPJ com tipo ou participação (só a marca do documento pode)": (
                f"SELECT * FROM {fonte} WHERE cnpj IS NULL AND (tipo IS NOT NULL OR participacao IS NOT NULL)"
            ),
        }
    return {
        "linha(s) com a raiz fora da lista sem pessoa": (
            f"SELECT * FROM {fonte} WHERE CNPJ_Fundo IS NULL OR {_raiz('CNPJ_Fundo')} NOT IN ({pj})"
        ),
        "linha(s) de fundo que não é FIP": (
            f"SELECT * FROM {fonte} WHERE Tipo_Fundo IS DISTINCT FROM {_aspas(FIP)}"
        ),
    }


def conferir_reduzidas(
    con: duckdb.DuckDBPyConnection,
    destinos: Mapping[str, Path],
    empresas_pj: Sequence[Path],
) -> dict[str, int]:
    """Lê as cópias reduzidas da saída e falha (`ReduzidaComPessoa`) em qualquer coisa fora da regra.

    Devolve as linhas de cada uma (as contagens que acompanham o pedido de envio)."""
    pj = _lista_pj(empresas_pj)
    problemas: list[str] = []
    linhas: dict[str, int] = {}
    for nome, arquivo in destinos.items():
        if nome not in COLUNAS:
            raise ReduzidaComPessoa(
                f"{nome}: não é uma cópia reduzida da lista de compradores"
            )
        fonte = fonte_dos_arquivos([arquivo])
        de_coluna = _problemas_de_coluna(con, nome, fonte)
        problemas += de_coluna
        if de_coluna:
            continue
        for descricao, consulta in _consultas_de_linha(nome, fonte, pj).items():
            if achadas := _contar(con, consulta):
                problemas.append(f"{nome}: {achadas} {descricao}")
        linhas[nome] = _contar(con, f"SELECT * FROM {fonte}")
    if problemas:
        raise ReduzidaComPessoa("; ".join(problemas))
    return linhas
