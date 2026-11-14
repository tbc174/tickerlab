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
depender do filtro: coluna fora da lista (gestor, nome), raiz fora da lista sem pessoa, CNPJ que não confere,
controlada sem CNPJ com tipo ou participação, fundo que não é FIP, cópia vazia. A mensagem leva só contagens, nunca
um CNPJ ou um nome (vai ao log e ao aviso do Kuma).

**CNPJ que confere**, no filtro e na trava: 14 caracteres sem pontuação e dígito verificador de CNPJ certo
(`cnpj_que_confere`). Para a controlada e o fundo vale ainda a regra dos três zeros (`cnpj_de_empresa`): o `cnpj14`
do FRE completa com zeros o valor de 8 a 13 dígitos, e um CPF de 11 vira `000` + CPF, com 14 caracteres e raiz que
pode estar na lista. Quase sempre o dígito do CNPJ já não confere; quando confere por acaso (cerca de 1 em 70), a
regra recusa o valor que começa com `000` e cujo resto confere como CPF. O preço é perder a PJ de verdade com essa
cara: na dúvida, não sai. A companhia (`cnpj_companhia`) fica só com o dígito: é a emissora registrada na CVM,
sempre PJ, e há companhia aberta de verdade cuja raiz começa com `000` e cujo resto confere como CPF.
"""

import re
from collections.abc import Mapping, Sequence
from pathlib import Path

import duckdb

from base.cnpj import cpf_confere, dv_confere
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
TAMANHO_DO_CNPJ = 14  # sem pontuação
# o `cnpj14` do FRE completa um CPF (11 dígitos) com estes zeros à esquerda
ZEROS_DO_CPF = "000"
# nomes das funções que o filtro e a trava chamam no DuckDB (registradas em cada conexão)
FUNCAO_CNPJ_QUE_CONFERE = "tl_cnpj_que_confere"
FUNCAO_CNPJ_DE_EMPRESA = "tl_cnpj_de_empresa"


class ReduzidaComPessoa(Exception):
    """A cópia reduzida tem (ou pode ter) pessoa ou gestor: nada sai de casa."""


def _aspas(texto: str) -> str:
    return "'" + texto.replace("'", "''") + "'"


def _raiz(coluna: str) -> str:
    """A raiz do CNPJ como a lista de compradores a lê: os 8 primeiros caracteres sem pontuação."""
    return f"substr(regexp_replace(CAST({coluna} AS VARCHAR), '[^0-9A-Za-z]', '', 'g'), 1, {TAMANHO_DA_RAIZ})"


def _sem_pontuacao(valor: str | None) -> str:
    return "" if valor is None else re.sub(r"[^0-9A-Za-z]", "", str(valor)).upper()


def cnpj_que_confere(valor: str | None) -> bool:
    """14 caracteres sem pontuação, não todos iguais, e o dígito verificador de CNPJ certo."""
    texto = _sem_pontuacao(valor)
    return len(texto) == TAMANHO_DO_CNPJ and len(set(texto)) > 1 and dv_confere(texto)


def cnpj_de_empresa(valor: str | None) -> bool:
    """Um CNPJ que confere e não tem a cara de um CPF completado com zeros (ver o topo do módulo)."""
    texto = _sem_pontuacao(valor)
    cpf_completado = texto.startswith(ZEROS_DO_CPF) and cpf_confere(
        texto[len(ZEROS_DO_CPF) :]
    )
    return cnpj_que_confere(texto) and not cpf_completado


def _registrar_funcoes(con: duckdb.DuckDBPyConnection) -> None:
    """Põe as duas funções na conexão (uma vez por conexão) para o filtro e a trava as chamarem no SQL."""
    for nome, funcao in (
        (FUNCAO_CNPJ_QUE_CONFERE, cnpj_que_confere),
        (FUNCAO_CNPJ_DE_EMPRESA, cnpj_de_empresa),
    ):
        ja_tem = con.execute(
            "SELECT count(*) FROM duckdb_functions() WHERE function_name = ?", [nome]
        ).fetchone()
        if ja_tem and ja_tem[0]:
            continue
        con.create_function(
            nome,
            funcao,
            [duckdb.sqltype("VARCHAR")],
            duckdb.sqltype("BOOLEAN"),
            null_handling="special",
        )


def _cnpj_inteiro(coluna: str, *, companhia: bool = False) -> str:
    """O CNPJ confere; fora da companhia, também não é um CPF completado. Pede `_registrar_funcoes` antes."""
    funcao = FUNCAO_CNPJ_QUE_CONFERE if companhia else FUNCAO_CNPJ_DE_EMPRESA
    return f"{funcao}(CAST({coluna} AS VARCHAR))"


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
    _registrar_funcoes(con)
    fonte = fonte_dos_arquivos(origem)
    da_lista = (
        f"{_cnpj_inteiro('cnpj_companhia', companhia=True)} AND {_raiz('cnpj_companhia')} IN ({pj}) "
        "AND conhecido_em IS NOT NULL"
    )
    consulta = (
        "SELECT cnpj_companhia, cnpj, tipo, participacao, referencia, versao, conhecido_em AS publico_em "
        f"FROM {fonte} WHERE {da_lista} AND cnpj IS NOT NULL AND {_cnpj_inteiro('cnpj')} "
        f"AND {_raiz('cnpj')} IN ({pj}) "
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
    _registrar_funcoes(con)
    consulta = (
        f"SELECT DISTINCT {', '.join(COLUNAS[FIPS_REGISTRADOS])} FROM {fonte_dos_arquivos(origem)} "
        f"WHERE Tipo_Fundo = {_aspas(FIP)} AND {_cnpj_inteiro('CNPJ_Fundo')} "
        f"AND {_raiz('CNPJ_Fundo')} IN ({pj}) "
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
            "linha(s) com CNPJ que não confere (sem os 14 caracteres, dígito errado ou CPF completado com zeros)": (
                f"SELECT * FROM {fonte} WHERE NOT {_cnpj_inteiro('cnpj_companhia', companhia=True)} "
                f"OR (cnpj IS NOT NULL AND NOT {_cnpj_inteiro('cnpj')})"
            ),
            "linha(s) sem CNPJ com tipo ou participação (só a marca do documento pode)": (
                f"SELECT * FROM {fonte} WHERE cnpj IS NULL AND (tipo IS NOT NULL OR participacao IS NOT NULL)"
            ),
        }
    return {
        "linha(s) com a raiz fora da lista sem pessoa": (
            f"SELECT * FROM {fonte} WHERE CNPJ_Fundo IS NULL OR {_raiz('CNPJ_Fundo')} NOT IN ({pj})"
        ),
        "linha(s) com CNPJ que não confere (sem os 14 caracteres, dígito errado ou CPF completado com zeros)": (
            f"SELECT * FROM {fonte} WHERE NOT {_cnpj_inteiro('CNPJ_Fundo')}"
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
    _registrar_funcoes(con)
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
        if not linhas[nome]:
            problemas.append(f"{nome}: cópia vazia (trocaria a do VPS por nada)")
    if problemas:
        raise ReduzidaComPessoa("; ".join(problemas))
    return linhas
