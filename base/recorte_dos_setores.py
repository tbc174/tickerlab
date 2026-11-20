"""As cópias reduzidas da ligação das entidades às companhias e dos acessos da Anatel que vão ao VPS (linha 978, PR B dos setores): o filtro e a trava.

A `empresa_serie` (de que companhia listada é cada entidade que os reguladores enxergam) e a `anatel_acessos` (acessos
por prestadora, mês e UF) sustentam as linhas do conjunto `sectors`: o mercado do setor e a participação das
companhias. As tabelas inteiras ficam em casa e nada que as lê hoje (app, modo dono, outras rotas) muda. Ao VPS vai uma
cópia **com o mesmo nome e o mesmo caminho** (a API lê a tabela pelo nome), mais estreita que a inteira, no mesmo molde
das cópias dos cadastros (`base/recorte_dos_cadastros.py`):

- **Só a entidade de pessoa jurídica:** a raiz da entidade (a coluna `raiz` da `empresa_serie`, os oito primeiros
  dígitos do `cnpj` da prestadora na `anatel_acessos`) está na `cnpj_empresas_pj` da mesma saída (a lista sem MEI depois
  de `tirar_raizes_de_mei`). A linha sem raiz (a entidade que só tem nome ou sigla, como o capítulo do NCM do Comex) e a
  linha com raiz fora da lista não saem: na dúvida é pessoa. O CNPJ da prestadora tem de conferir (14 caracteres, dígito
  certo e sem a cara de CPF completado com zeros) e o da companhia ligada, quando há, também, com a raiz na lista.
- **Só as colunas de `COLUNAS`:** sem o nome da entidade, o nome da companhia, o nome da prestadora nem o grupo
  econômico (os nomes vêm do cadastro da CVM, que é de empresa). A `chave` da `empresa_serie` (registro, CNPJ, ISPB, sigla
  ou nome) fica, e a linha em que ela traz CPF ou e-mail não sai.

`conferir_setores` lê **a saída** e derruba o envio (`SetorComPessoa`) em qualquer coisa fora disso, sem depender do
filtro: coluna fora da lista ou faltando, linha sem raiz ou com a raiz fora da lista, CNPJ que não confere, valor
inteiro com cara de CPF que confere numa coluna de texto, CPF ou e-mail dentro da `chave`, tabela vazia. A mensagem
leva só contagens, nunca um CNPJ ou um nome.
"""

from collections.abc import Mapping, Sequence
from pathlib import Path

import duckdb

from base.porta.duckdb import fonte_dos_arquivos
from base.recorte_dos_cadastros import (
    FUNCAO_CNPJ_DE_EMPRESA,
    FUNCAO_CPF_INTEIRO,
    FUNCAO_PESSOA_NO_TEXTO,
    TAMANHO_DA_RAIZ,
    CadastroComPessoa,
    _aspas,
    _registrar_funcoes,
)
from base.recorte_dos_cadastros import (
    _lista_pj as _lista_pj_dos_cadastros,
)

EMPRESA_SERIE = "empresa_serie"
ANATEL_ACESSOS = "anatel_acessos"
SETORES = (EMPRESA_SERIE, ANATEL_ACESSOS)
COLUNAS: dict[str, tuple[str, ...]] = {
    EMPRESA_SERIE: (
        "fonte", "chave", "raiz", "cnpj_companhia", "via", "por", "participacao", "desde", "ultima_referencia",
        "ate", "ate_publico_em", "vigente", "principal", "tickers", "origem_sha256", "montado_em",
        "versao_do_codigo",
    ),
    ANATEL_ACESSOS: (
        "competencia", "servico", "recorte", "cnpj", "porte_da_prestadora", "uf", "regiao_pgo", "codigo_nacional",
        "modalidade_de_cobranca", "tecnologia", "geracao", "tipo_de_pessoa", "tipo_de_produto",
        "faixa_de_velocidade", "meio_de_acesso", "tipo_de_acesso_tv", "acessos", "arquivo", "disponivel_em",
        "visto_em",
    ),
}  # fmt: skip
# colunas que o contrato pede mas o arquivo gravado antes delas pode não ter ainda: a cópia leva as que existem
COLUNAS_QUE_PODEM_FALTAR: dict[str, tuple[str, ...]] = {
    EMPRESA_SERIE: ("ate", "ate_publico_em", "vigente"),
}
# a coluna de cada tabela com o CNPJ (ou a raiz) de quem a linha descreve, e a que ordena a cópia
RAIZ_DA_ENTIDADE = {EMPRESA_SERIE: "raiz", ANATEL_ACESSOS: "cnpj"}
CNPJ_DA_COMPANHIA = {EMPRESA_SERIE: "cnpj_companhia"}
# a coluna que, na `empresa_serie`, é o CNPJ da entidade quando a fonte traz um (a Anatel põe o CPF de prestadora pessoa
# física na coluna de CNPJ, e o contrato o completa com zeros: `000` + CPF). Em forma de CNPJ, tem de conferir como empresa
CHAVE_COM_FORMA_DE_CNPJ = {EMPRESA_SERIE: "chave"}
ORDEM = {
    EMPRESA_SERIE: "fonte, chave, cnpj_companhia, desde",
    ANATEL_ACESSOS: "competencia, servico, recorte, cnpj, visto_em",
}
# as colunas de texto livre da cópia: CPF ou e-mail dentro delas derruba a linha (filtro) e o envio (trava)
TEXTOS_LIVRES: dict[str, tuple[str, ...]] = {EMPRESA_SERIE: ("chave",)}
# colunas de nome que as tabelas inteiras trazem e a cópia nunca leva (o teste confere que `COLUNAS` não tem nenhuma)
COLUNAS_DE_NOME = (
    "nome",
    "razao_social",
    "nome_fantasia",
    "companhia",
    "empresa",
    "grupo_economico",
    "cpf",
)
FORMA_DA_RAIZ = f"[0-9A-Z]{{{TAMANHO_DA_RAIZ}}}"
TAMANHO_DO_CNPJ = 14


class SetorComPessoa(CadastroComPessoa):
    """A cópia reduzida tem (ou pode ter) pessoa ou texto livre: nada sai de casa."""


def _lista_pj(empresas_pj: Sequence[Path]) -> str:
    """A consulta das raízes sem pessoa; sem a `cnpj_empresas_pj` da saída nada se confere."""
    try:
        return _lista_pj_dos_cadastros(empresas_pj)
    except CadastroComPessoa as erro:
        raise SetorComPessoa(str(erro)) from erro


def _limpo(coluna: str) -> str:
    """O texto da coluna sem pontuação, em maiúsculas (o CNPJ alfanumérico tem letras)."""
    return f"""upper(regexp_replace(CAST("{coluna}" AS VARCHAR), '[^0-9A-Za-z]', '', 'g'))"""


def _raiz(coluna: str) -> str:
    """A raiz de 8 posições da coluna ('?' quando o texto está fora da forma: conta como fora, o lado seguro)."""
    limpo = _limpo(coluna)
    return f"CASE WHEN regexp_full_match({limpo}, '{FORMA_DA_RAIZ}[0-9A-Z]*') THEN left({limpo}, {TAMANHO_DA_RAIZ}) ELSE '?' END"


def _sem_pessoa_no_texto(nome: str) -> str:
    return "".join(
        f' AND NOT coalesce({FUNCAO_PESSOA_NO_TEXTO}(CAST("{coluna}" AS VARCHAR)), false)'
        for coluna in TEXTOS_LIVRES.get(nome, ())
    )


def _forma_de_cnpj_que_nao_confere(coluna: str) -> str:
    """Verdadeiro quando o texto tem 14 posições (forma de CNPJ) e não confere como CNPJ de empresa (dígito errado ou CPF
    completado com zeros); texto de outra forma (sigla, nome de entidade sem documento) não entra na conta."""
    return (
        f"(regexp_full_match({_limpo(coluna)}, '[0-9A-Z]{{{TAMANHO_DO_CNPJ}}}') AND NOT coalesce("
        f'{FUNCAO_CNPJ_DE_EMPRESA}(CAST("{coluna}" AS VARCHAR)), false))'
    )


def _raiz_de_8_posicoes(coluna: str) -> str:
    """Verdadeiro quando a coluna limpa tem exatamente as 8 posições da raiz (nem a mais, nem a menos)."""
    return f"length({_limpo(coluna)}) = {TAMANHO_DA_RAIZ}"


def _so_pj(pj: str, nome: str) -> str:
    """A condição da linha que pode sair (a mesma que a trava confere ao contrário)."""
    entidade = RAIZ_DA_ENTIDADE[nome]
    condicao = f"{_raiz(entidade)} IN ({pj})"
    if nome == ANATEL_ACESSOS:
        condicao += f' AND {FUNCAO_CNPJ_DE_EMPRESA}(CAST("{entidade}" AS VARCHAR))'
    if chave := CHAVE_COM_FORMA_DE_CNPJ.get(nome):
        condicao += f" AND {_raiz_de_8_posicoes(entidade)} AND NOT {_forma_de_cnpj_que_nao_confere(chave)}"
    if companhia := CNPJ_DA_COMPANHIA.get(nome):
        condicao += (
            f' AND ("{companhia}" IS NULL OR ({FUNCAO_CNPJ_DE_EMPRESA}(CAST("{companhia}" AS VARCHAR))'
            f" AND {_raiz(companhia)} IN ({pj})))"
        )
    return condicao + _sem_pessoa_no_texto(nome)


def _selecao(con: duckdb.DuckDBPyConnection, nome: str, fonte: str) -> str:
    """As colunas da lista que o arquivo de origem tem (as que podem faltar, se faltarem, ficam de fora)."""
    presentes = {
        c for (c, *_) in con.execute(f"DESCRIBE SELECT * FROM {fonte}").fetchall()
    }
    podem_faltar = set(COLUNAS_QUE_PODEM_FALTAR.get(nome, ()))
    return ", ".join(
        f'"{coluna}"'
        for coluna in COLUNAS[nome]
        if coluna in presentes or coluna not in podem_faltar
    )


def _contar(con: duckdb.DuckDBPyConnection, consulta: str) -> int:
    linha = con.execute(f"SELECT count(*) FROM ({consulta})").fetchone()
    return int(linha[0]) if linha else 0


def montar_setor(
    con: duckdb.DuckDBPyConnection,
    nome: str,
    origem: Path,
    empresas_pj: Sequence[Path],
    destino: Path,
) -> tuple[int, int]:
    """Escreve em `destino` a cópia reduzida de um arquivo da tabela; devolve (linhas que saíram, tiradas)."""
    if nome not in COLUNAS:
        raise SetorComPessoa(f"{nome}: não é uma das tabelas dos setores")
    pj = _lista_pj(empresas_pj)
    _registrar_funcoes(con)
    fonte = fonte_dos_arquivos([origem])
    destino.parent.mkdir(parents=True, exist_ok=True)
    con.execute(
        f"COPY (SELECT {_selecao(con, nome, fonte)} FROM {fonte} WHERE {_so_pj(pj, nome)} ORDER BY {ORDEM[nome]}) "
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
        de_nome = sum(c.lower() in COLUNAS_DE_NOME for c in fora)
        problemas.append(
            f"{nome}: {len(fora)} coluna(s) fora da lista ({de_nome} de nome ou texto livre)"
        )
    podem_faltar = set(COLUNAS_QUE_PODEM_FALTAR.get(nome, ()))
    if faltam := sorted(set(COLUNAS[nome]) - set(colunas) - podem_faltar):
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
    entidade = RAIZ_DA_ENTIDADE[nome]
    consultas = {
        "linha(s) com a raiz fora da lista sem pessoa (ou sem raiz)": (
            f"SELECT * FROM {fonte} WHERE {_raiz(entidade)} NOT IN ({pj})"
        ),
    }
    if nome == ANATEL_ACESSOS:
        consultas[
            "linha(s) com CNPJ que não confere (sem os 14 caracteres, dígito errado ou CPF completado com zeros)"
        ] = f'SELECT * FROM {fonte} WHERE NOT coalesce({FUNCAO_CNPJ_DE_EMPRESA}(CAST("{entidade}" AS VARCHAR)), false)'
    if chave := CHAVE_COM_FORMA_DE_CNPJ.get(nome):
        consultas["linha(s) com a raiz que não tem 8 posições"] = (
            f"SELECT * FROM {fonte} WHERE NOT coalesce({_raiz_de_8_posicoes(entidade)}, false)"
        )
        consultas[
            "linha(s) com a chave em forma de CNPJ que não confere (dígito errado ou CPF completado com zeros)"
        ] = f"SELECT * FROM {fonte} WHERE {_forma_de_cnpj_que_nao_confere(chave)}"
    if companhia := CNPJ_DA_COMPANHIA.get(nome):
        consultas[
            "linha(s) com a companhia ligada de CNPJ que não confere ou fora da lista sem pessoa"
        ] = (
            f'SELECT * FROM {fonte} WHERE "{companhia}" IS NOT NULL AND NOT coalesce('
            f'{FUNCAO_CNPJ_DE_EMPRESA}(CAST("{companhia}" AS VARCHAR)) AND {_raiz(companhia)} IN ({pj}), false)'
        )
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
    return consultas


def conferir_setores(
    con: duckdb.DuckDBPyConnection,
    destinos: Mapping[str, Sequence[Path]],
    empresas_pj: Sequence[Path],
) -> dict[str, int]:
    """Lê as cópias reduzidas da saída e falha (`SetorComPessoa`) em qualquer coisa fora da regra.

    Devolve as linhas de cada tabela (as contagens que acompanham o pedido de envio)."""
    pj = _lista_pj(empresas_pj)
    _registrar_funcoes(con)
    problemas: list[str] = []
    linhas: dict[str, int] = {}
    for nome, arquivos in destinos.items():
        if nome not in COLUNAS:
            raise SetorComPessoa(f"{nome}: não é uma das tabelas dos setores")
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
        raise SetorComPessoa("; ".join(problemas))
    return linhas
