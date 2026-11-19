"""As cópias reduzidas dos cinco cadastros em retrato e das sanções da CGU que vão ao VPS (linhas 915 e 981): o filtro e a trava.

Os cinco cadastros (`base/cadastros_em_retrato.py`: ANS, SUSEP, Lista Suja do MTE, ponte da GLEIF e embargos do
IBAMA) e as sanções da CGU (`base/sancoes.py`: CEIS, CNEP, CEPIM e leniência, um arquivo por cadastro, só CNPJ)
são tabelas de pessoa no dicionário: guardam a razão social ou o nome como a fonte escreve, e a linha de
empresário individual e de MEI fica, marcada em `trata_como_pessoa` (ADR 0075). A tabela inteira fica em casa. Ao
VPS vai uma cópia **com o mesmo nome e o mesmo caminho** (`<tabela>/<cadastro>.parquet`), porque a API lê a
tabela pelo nome (os sinais de crédito, `src/credito/sinais.py`, leem `mte_lista_suja` e `ibama_embargos`), e mais
estreita que a inteira:

- **Só a linha de pessoa jurídica:** `trata_como_pessoa` falso (verdadeiro ou vazio não sai: na dúvida é pessoa),
  CNPJ que confere (14 caracteres, dígito certo e sem a cara de CPF completado com zeros: `cnpj_de_empresa`),
  `cnpj_basico` igual à raiz do CNPJ e raiz que está na `cnpj_empresas_pj` da mesma saída (a lista sem MEI depois
  de `tirar_raizes_de_mei`). Linha da SUSEP sem CNPJ não sai.
- **Só as colunas de `COLUNAS`:** códigos, datas, situação e as colunas de controle. Sem nome, razão social, nome
  fantasia, empregador, estabelecimento (texto livre: o endereço da fazenda) nem o motivo do descredenciamento
  da ANS (texto livre). Nas sanções da CGU sai o número do processo (do convênio, no CEPIM) e a linha que traz CPF
  ou e-mail dentro de um texto livre (inclusive o CPF mascarado como a CGU publica). A situação do termo do IBAMA (`situacao_do_termo`) também não sai: o sinal usa só as marcas
  `cancelado` e `desembargado`.
- **A chave da Lista Suja vira impressão digital:** o `id_na_fonte` do MTE junta CNPJ, ano e estabelecimento
  (texto livre); sai o `sha256` dele, que separa as linhas igual e não leva o texto.

`conferir_cadastros` lê **a saída** e derruba o envio (`CadastroComPessoa`) em qualquer coisa fora disso, sem
depender do filtro: coluna fora da lista ou faltando, linha marcada ou sem marca, CNPJ que não confere, raiz
trocada ou fora da lista sem pessoa, valor inteiro com cara de CPF que confere numa coluna de texto, CPF ou e-mail
dentro do texto livre das sanções, chave do MTE que não é impressão digital, tabela vazia. A mensagem leva só contagens, nunca um CNPJ ou um nome.
"""

import re
from collections.abc import Mapping, Sequence
from pathlib import Path

import duckdb

from base.cnpj import cpf_confere
from base.porta.duckdb import fonte_dos_arquivos
from base.recorte_dos_compradores import cnpj_de_empresa

ANS, SUSEP, MTE, GLEIF, IBAMA = (
    "ans_operadoras",
    "susep_cadastro",
    "mte_lista_suja",
    "gleif_ponte",
    "ibama_embargos",
)
# as sanções da CGU (linha 981): a tabela inteira é de pessoa no dicionário, mas o servidor guarda só esta cópia
SANCOES = "sancoes_cgu"
CADASTROS = (ANS, SUSEP, MTE, GLEIF, IBAMA, SANCOES)
# as colunas de controle que toda cópia leva (a chave, o CNPJ, a marca e a linhagem)
CONTROLE = (
    "id_na_fonte", "cnpj", "cnpj_basico", "consta", "trata_como_pessoa", "visto_em", "disponivel_em",
    "origem_sha256", "origem_coletada_em", "montado_em", "versao_do_codigo",
)  # fmt: skip
COLUNAS: dict[str, tuple[str, ...]] = {
    ANS: (*CONTROLE, "modalidade", "uf", "registrada_em", "descredenciada_em", "situacao"),
    SUSEP: (*CONTROLE, "codigo_do_mercado", "autorizada_em"),
    MTE: (*CONTROLE, "ano_da_acao", "uf", "cnae", "trabalhadores", "incluida_em"),
    GLEIF: (*CONTROLE, "lei", "autoridade", "categoria", "situacao_do_lei", "conflito"),
    IBAMA: (
        *CONTROLE, "numero_do_termo", "cancelado", "codigo_do_municipio", "uf", "desembargado",
        "numero_do_auto", "area_embargada_ha", "embargada_em", "desembargada_em",
    ),
    SANCOES: (
        *CONTROLE, "cadastro", "categoria", "situacao", "assunto", "orgao", "uf_do_orgao", "esfera_do_orgao",
        "origem_da_informacao", "fundamentacao_legal", "abrangencia", "inicio", "fim", "publicado_em",
        "transito_em_julgado", "informado_em", "valor_multa",
    ),
}  # fmt: skip
# as colunas de texto livre da cópia: CPF ou e-mail dentro delas derruba a linha (filtro) e o envio (trava)
TEXTOS_LIVRES: dict[str, tuple[str, ...]] = {
    SANCOES: (
        "categoria", "situacao", "assunto", "orgao", "uf_do_orgao", "esfera_do_orgao", "origem_da_informacao",
        "fundamentacao_legal", "abrangencia",
    ),
}  # fmt: skip
# pedaços de nome de coluna que nunca saem (o teste confere que a lista acima não tem nenhum)
PEDACOS_PROIBIDOS = (
    "nome",
    "razao",
    "fantasia",
    "empregador",
    "estabelecimento",
    "motivo",
    "cpf",
)
# a tabela cuja chave leva texto livre: sai a impressão digital da chave
CHAVE_COM_TEXTO = {MTE}
TAMANHO_DA_RAIZ = 8
TAMANHO_DO_CPF = 11
TAMANHO_DA_IMPRESSAO = 64  # sha256 em hexadecimal
# nomes das funções que o filtro e a trava chamam no DuckDB (registradas em cada conexão)
FUNCAO_CNPJ_DE_EMPRESA = "tl_cadastro_cnpj_de_empresa"
FUNCAO_CPF_INTEIRO = "tl_cadastro_cpf_inteiro"
FUNCAO_PESSOA_NO_TEXTO = "tl_cadastro_pessoa_no_texto"
# um CPF (com ou sem a pontuação) solto no texto, o CPF mascarado como a CGU publica (***.123.456-**) e um e-mail
CPF_NO_TEXTO = re.compile(r"(?<!\d)(\d{3})\.?(\d{3})\.?(\d{3})-?(\d{2})(?!\d)")
CPF_MASCARADO = re.compile(r"\*{3}\.?\d{3}\.?\d{3}-?\*{2}")
EMAIL_NO_TEXTO = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")


class CadastroComPessoa(Exception):
    """A cópia reduzida tem (ou pode ter) pessoa ou texto livre: nada sai de casa."""


def _aspas(texto: str) -> str:
    return "'" + texto.replace("'", "''") + "'"


def cpf_inteiro(valor: str | None) -> bool:
    """O valor inteiro tem a cara de um CPF (11 dígitos, com ou sem a pontuação de CPF) e o dígito confere."""
    if valor is None:
        return False
    texto = str(valor).strip()
    so_digitos = texto.replace(".", "").replace("-", "")
    return (
        len(so_digitos) == TAMANHO_DO_CPF
        and so_digitos.isdigit()
        and cpf_confere(so_digitos)
    )


def pessoa_no_texto(valor: str | None) -> bool:
    """O texto traz um CPF que confere (com ou sem pontuação), um CPF mascarado ou um e-mail."""
    if valor is None:
        return False
    texto = str(valor)
    if CPF_MASCARADO.search(texto) or EMAIL_NO_TEXTO.search(texto):
        return True
    return any(cpf_confere("".join(partes)) for partes in CPF_NO_TEXTO.findall(texto))


def _registrar_funcoes(con: duckdb.DuckDBPyConnection) -> None:
    """Põe as funções na conexão (uma vez por conexão) para o filtro e a trava as chamarem no SQL."""
    for nome, funcao in (
        (FUNCAO_CNPJ_DE_EMPRESA, cnpj_de_empresa),
        (FUNCAO_CPF_INTEIRO, cpf_inteiro),
        (FUNCAO_PESSOA_NO_TEXTO, pessoa_no_texto),
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


def _raiz_do_cnpj() -> str:
    return f"substr(regexp_replace(CAST(cnpj AS VARCHAR), '[^0-9A-Za-z]', '', 'g'), 1, {TAMANHO_DA_RAIZ})"


def _lista_pj(empresas_pj: Sequence[Path]) -> str:
    if not empresas_pj:
        raise CadastroComPessoa(
            "sem cnpj_empresas_pj na saída: não dá para conferir as raízes"
        )
    return f"SELECT DISTINCT cnpj_basico FROM {fonte_dos_arquivos(empresas_pj)} WHERE cnpj_basico IS NOT NULL"


def _sem_pessoa_no_texto(nome: str) -> str:
    """A condição de que nenhum texto livre da cópia traz CPF nem e-mail (vazia se a cópia não tem texto livre)."""
    return "".join(
        f' AND NOT coalesce({FUNCAO_PESSOA_NO_TEXTO}(CAST("{coluna}" AS VARCHAR)), false)'
        for coluna in TEXTOS_LIVRES.get(nome, ())
    )


def _so_pj(pj: str, nome: str) -> str:
    """A condição da linha que pode sair (a mesma que a trava confere ao contrário)."""
    return (
        "trata_como_pessoa IS NOT DISTINCT FROM false "
        f"AND {FUNCAO_CNPJ_DE_EMPRESA}(CAST(cnpj AS VARCHAR)) "
        f"AND cnpj_basico IS NOT DISTINCT FROM {_raiz_do_cnpj()} "
        f"AND cnpj_basico IN ({pj})" + _sem_pessoa_no_texto(nome)
    )


def _selecao(nome: str) -> str:
    return ", ".join(
        "sha256(CAST(id_na_fonte AS VARCHAR)) AS id_na_fonte"
        if coluna == "id_na_fonte" and nome in CHAVE_COM_TEXTO
        else f'"{coluna}"'
        for coluna in COLUNAS[nome]
    )


def _contar(con: duckdb.DuckDBPyConnection, consulta: str) -> int:
    linha = con.execute(f"SELECT count(*) FROM ({consulta})").fetchone()
    return int(linha[0]) if linha else 0


def montar_cadastro(
    con: duckdb.DuckDBPyConnection,
    nome: str,
    origem: Path,
    empresas_pj: Sequence[Path],
    destino: Path,
) -> tuple[int, int]:
    """Escreve em `destino` a cópia reduzida de um arquivo do cadastro; devolve (linhas que saíram, tiradas)."""
    if nome not in COLUNAS:
        raise CadastroComPessoa(f"{nome}: não é um dos cadastros")
    pj = _lista_pj(empresas_pj)
    _registrar_funcoes(con)
    fonte = fonte_dos_arquivos([origem])
    destino.parent.mkdir(parents=True, exist_ok=True)
    con.execute(
        f"COPY (SELECT {_selecao(nome)} FROM {fonte} WHERE {_so_pj(pj, nome)} ORDER BY id_na_fonte, visto_em) "
        f"TO {_aspas(destino.as_posix())} (FORMAT PARQUET, COMPRESSION ZSTD)"
    )
    antes = _contar(con, f"SELECT * FROM {fonte}")
    depois = _contar(con, f"SELECT * FROM {fonte_dos_arquivos([destino])}")
    return depois, antes - depois


# --- a trava ----------------------------------------------------------------------------------------


def _problemas_de_coluna(
    con: duckdb.DuckDBPyConnection, nome: str, fonte: str
) -> list[str]:
    colunas = [
        c for (c, *_) in con.execute(f"DESCRIBE SELECT * FROM {fonte}").fetchall()
    ]
    problemas = []
    if fora := [c for c in colunas if c not in COLUNAS[nome]]:
        de_nome = sum(any(p in c.lower() for p in PEDACOS_PROIBIDOS) for c in fora)
        problemas.append(
            f"{nome}: {len(fora)} coluna(s) fora da lista ({de_nome} de nome ou texto livre)"
        )
    if faltam := sorted(set(COLUNAS[nome]) - set(colunas)):
        problemas.append(f"{nome}: sem {faltam}")
    return problemas


def _colunas_de_texto(con: duckdb.DuckDBPyConnection, fonte: str) -> list[str]:
    return [
        c
        for (c, tipo, *_) in con.execute(f"DESCRIBE SELECT * FROM {fonte}").fetchall()
        if tipo == "VARCHAR"
    ]


def _consultas_de_linha(
    con: duckdb.DuckDBPyConnection, nome: str, fonte: str, pj: str
) -> dict[str, str]:
    consultas = {
        "linha(s) marcada(s) como pessoa ou sem a marca": (
            f"SELECT * FROM {fonte} WHERE trata_como_pessoa IS DISTINCT FROM false"
        ),
        "linha(s) com CNPJ que não confere (sem os 14 caracteres, dígito errado ou CPF completado com zeros)": (
            f"SELECT * FROM {fonte} WHERE NOT coalesce({FUNCAO_CNPJ_DE_EMPRESA}(CAST(cnpj AS VARCHAR)), false)"
        ),
        "linha(s) com a raiz diferente da do CNPJ": (
            f"SELECT * FROM {fonte} WHERE cnpj_basico IS DISTINCT FROM {_raiz_do_cnpj()}"
        ),
        "linha(s) com a raiz fora da lista sem pessoa": (
            f"SELECT * FROM {fonte} WHERE cnpj_basico IS NULL OR cnpj_basico NOT IN ({pj})"
        ),
    }
    textos = _colunas_de_texto(con, fonte)
    if textos:
        com_cpf = " OR ".join(f'{FUNCAO_CPF_INTEIRO}("{c}")' for c in textos)
        consultas["valor(es) com cara de CPF que confere numa coluna de texto"] = (
            f"SELECT * FROM {fonte} WHERE {com_cpf}"
        )
    if textos_livres := TEXTOS_LIVRES.get(nome):
        com_pessoa = " OR ".join(
            f'{FUNCAO_PESSOA_NO_TEXTO}(CAST("{c}" AS VARCHAR))' for c in textos_livres
        )
        consultas["linha(s) com CPF ou e-mail dentro de texto livre"] = (
            f"SELECT * FROM {fonte} WHERE {com_pessoa}"
        )
    if nome in CHAVE_COM_TEXTO:
        consultas["chave(s) que não são a impressão digital"] = (
            f"SELECT * FROM {fonte} WHERE NOT coalesce(regexp_full_match(id_na_fonte, "
            f"'[0-9a-f]{{{TAMANHO_DA_IMPRESSAO}}}'), false)"
        )
    return consultas


def conferir_cadastros(
    con: duckdb.DuckDBPyConnection,
    destinos: Mapping[str, Sequence[Path]],
    empresas_pj: Sequence[Path],
) -> dict[str, int]:
    """Lê as cópias reduzidas da saída e falha (`CadastroComPessoa`) em qualquer coisa fora da regra.

    Devolve as linhas de cada tabela (as contagens que acompanham o pedido de envio)."""
    pj = _lista_pj(empresas_pj)
    _registrar_funcoes(con)
    problemas: list[str] = []
    linhas: dict[str, int] = {}
    for nome, arquivos in destinos.items():
        if nome not in COLUNAS:
            raise CadastroComPessoa(f"{nome}: não é um dos cadastros")
        if not arquivos:
            problemas.append(f"{nome}: nenhum arquivo na saída")
            continue
        for arquivo in arquivos:
            fonte = fonte_dos_arquivos([arquivo])
            de_coluna = _problemas_de_coluna(con, nome, fonte)
            problemas += [f"{p} ({arquivo.name})" for p in de_coluna]
            if de_coluna:
                continue
            for descricao, consulta in _consultas_de_linha(
                con, nome, fonte, pj
            ).items():
                if achadas := _contar(con, consulta):
                    problemas.append(f"{nome}: {achadas} {descricao} ({arquivo.name})")
            linhas[nome] = linhas.get(nome, 0) + _contar(con, f"SELECT * FROM {fonte}")
        if not linhas.get(nome):
            problemas.append(f"{nome}: cópia vazia (trocaria a do VPS por nada)")
    if problemas:
        raise CadastroComPessoa("; ".join(problemas))
    return linhas
