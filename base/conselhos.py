"""Conselhos, comitês e remuneração da administração pelo FRE (série 4 da base de ML, PR 6).

O FRE traz cada administrador com nome, CPF, data de nascimento e currículo: **nada disso entra**. As
colunas pessoais nem são lidas (`usecols`), e a base guarda só contagens por documento e órgão:
quantos membros, quantos independentes, quantos eleitos pelo controlador ou pelos minoritários, a
média de mandatos seguidos. A remuneração e a diversidade (gênero, raça e PCD, do FRE de 2023 em
diante) já vêm por órgão, sem pessoas, e entram como a CVM publica, sem os campos de texto livre.

"Como era na data": cada linha leva o `conhecido_em`, a entrega do documento à CVM (`DT_RECEB` do
arquivo principal, pelo `ID_Documento`). O arquivo da CVM traz só a versão mais nova de cada
formulário, então a data é a dessa versão (pode atrasar, nunca adiantar); as baixadas antigas do
acervo trazem as versões de antes (`juntar_baixadas`).
"""

import io
import re
import zipfile

import pandas as pd

from base import fre

DOCUMENTO = ("CNPJ_Companhia", "Data_Referencia", "Versao", "ID_Documento")
COLUNAS_DO_DOCUMENTO = ("cnpj", "referencia", "versao", "id_documento")
# o que o FRE traz de cada pessoa e nunca entra (o teste confere que nenhuma tabela tem)
PESSOAIS = (
    "Nome", "CPF", "Data_Nascimento", "Profissao", "Experiencia_Profissional",
    "Outro_Cargo_Funcao", "Complemento_Cargo_Eletivo_Ocupado", "Descricao_Outro_Cargo_Ocupado",
    "Observacao", "Descricao_Outros_Remuneracoes_Fixas", "Descricao_Outros_Remuneracoes_Variaveis",
)  # fmt: skip
INDEPENDENTE = "Independente"
SUPLENTE = "Suplent"  # "(Suplente)" e "C.F.(Suplent)"
MINORITARIOS = "Minor"
PREFERENCIALISTAS = "preferencialistas"

COLUNAS_DO_CONSELHO = (
    *COLUNAS_DO_DOCUMENTO, "orgao", "membros", "suplentes", "independentes",
    "eleitos_pelo_controlador", "eleitos_por_minoritarios", "eleitos_por_preferencialistas",
    "mandatos_consecutivos_medio", "participacao_em_reunioes_media", "conhecido_em",
)  # fmt: skip
COLUNAS_DOS_COMITES = (
    *COLUNAS_DO_DOCUMENTO, "tipo_de_comite", "membros", "suplentes", "conhecido_em",
)  # fmt: skip
REMUNERACAO = {
    "Data_Inicio_Exercicio_Social": "inicio_do_exercicio", "Data_Fim_Exercicio_Social": "fim_do_exercicio",
    "Orgao_Administracao": "orgao", "Total_Remuneracao": "total_remuneracao",
    "Numero_Membros": "membros", "Total_Remuneracao_Orgao": "total_do_orgao",
    "Numero_Membros_Remunerados": "membros_remunerados", "Salario": "salario",
    "Beneficios_Diretos_Indiretos": "beneficios", "Participacoes_Comites": "participacao_em_comites",
    "Outros_Valores_Fixos": "outros_fixos", "Bonus": "bonus",
    "Participacao_Resultados": "participacao_nos_resultados", "Participacao_Reunioes": "participacao_em_reunioes",
    "Outros_Valores_Variaveis": "outros_variaveis", "Comissoes": "comissoes",
    "Pos_emprego": "pos_emprego", "Cessacao_Cargo": "cessacao_do_cargo", "Baseada_Acoes": "baseada_em_acoes",
}  # fmt: skip
EXTREMOS = {
    "Data_Inicio_Exercicio_Social": "inicio_do_exercicio", "Data_Fim_Exercicio_Social": "fim_do_exercicio",
    "Orgao_Administracao": "orgao", "Numero_Membros": "membros",
    "Numero_Membros_Remunerados": "membros_remunerados", "Valor_Maior_Remuneracao": "maior",
    "Valor_Menor_Remuneracao": "menor", "Valor_Medio_Remuneracao": "media",
}  # fmt: skip
DIVERSIDADE = {  # tabela do FRE -> colunas de contagem (do FRE de 2023 em diante)
    "administrador_declaracao_genero": (
        "Quantidade_Feminino", "Quantidade_Masculino", "Quantidade_Nao_Binario", "Quantidade_Outros",
        "Quantidade_Sem_Resposta", "Nao_Aplicavel",
    ),
    "administrador_declaracao_raca": (
        "Quantidade_Amarelo", "Quantidade_Branco", "Quantidade_Preto", "Quantidade_Pardo",
        "Quantidade_Indigena", "Quantidade_Outros", "Quantidade_Sem_Resposta", "Nao_Aplicavel",
    ),
    "administrador_PCD": ("Quantidade_PCD", "Quantidade_Nao_PCD", "Quantidade_Sem_Resposta", "Nao_Aplicavel"),
}  # fmt: skip
PREFIXOS_DA_DIVERSIDADE = {
    "administrador_declaracao_genero": "genero",
    "administrador_declaracao_raca": "raca",
    "administrador_PCD": "pcd",
}
PRINCIPAL = re.compile(r"^fre_cia_aberta_\d{4}\.csv$")


def _snake(nome: str) -> str:
    return nome.lower()


def _tabela(conteudo_do_zip: bytes, tabela: str, colunas: list[str]) -> pd.DataFrame:
    """Só as `colunas` da tabela `fre_cia_aberta_<tabela>_<ano>.csv` (vazia se não existe)."""
    nome = re.compile(rf"^fre_cia_aberta_{tabela}_\d{{4}}\.csv$")
    pedidas = set(colunas)
    with zipfile.ZipFile(io.BytesIO(conteudo_do_zip)) as arquivo:
        nomes = [n for n in arquivo.namelist() if nome.match(n)]
        if not nomes:
            return pd.DataFrame(columns=colunas)
        return pd.read_csv(
            arquivo.open(nomes[0]), sep=";", encoding=fre.CODIFICACAO_DA_CVM,
            encoding_errors="replace", dtype=str, keep_default_na=False,
            usecols=lambda coluna: coluna in pedidas,
        ).reindex(columns=colunas)  # fmt: skip


def entregas(conteudo_do_zip: bytes) -> dict[str, pd.Timestamp]:
    """`ID_DOC` -> `DT_RECEB` do arquivo principal do FRE."""
    with zipfile.ZipFile(io.BytesIO(conteudo_do_zip)) as arquivo:
        nome = next((n for n in arquivo.namelist() if PRINCIPAL.match(n)), None)
        if nome is None:
            return {}
        principal = pd.read_csv(
            arquivo.open(nome), sep=";", encoding=fre.CODIFICACAO_DA_CVM, dtype=str,
            keep_default_na=False, usecols=["ID_DOC", "DT_RECEB"],
        )  # fmt: skip
    datas = pd.to_datetime(principal["DT_RECEB"], errors="coerce")
    return dict(zip(principal["ID_DOC"].str.strip(), datas, strict=True))


def _documento(bruto: pd.DataFrame, recebidos: dict[str, pd.Timestamp]) -> pd.DataFrame:
    """As colunas do documento e o `conhecido_em`; sem data de entrega, a linha sai."""
    documento = pd.DataFrame(
        {
            "cnpj": bruto["CNPJ_Companhia"].str.strip(),
            "referencia": pd.to_datetime(bruto["Data_Referencia"], errors="coerce"),
            "versao": pd.to_numeric(bruto["Versao"], errors="coerce").astype("Int64"),
            "id_documento": bruto["ID_Documento"].str.strip(),
        },
        index=bruto.index,
    )
    documento["conhecido_em"] = documento["id_documento"].map(recebidos)
    return documento


def _contem(coluna: pd.Series, trecho: str) -> pd.Series:
    return coluna.str.contains(trecho, case=False, regex=False)


def ler_conselho(conteudo_do_zip: bytes) -> pd.DataFrame:
    """Por documento e órgão: as contagens dos administradores e conselheiros fiscais, sem pessoas."""
    colunas = [
        *DOCUMENTO, "Orgao_Administracao", "Cargo_Eletivo_Ocupado", "Eleito_Controlador",
        "Numero_Mandatos_Consecutivos", "Percentual_Participacao_Reunioes",
    ]  # fmt: skip
    bruto = _tabela(conteudo_do_zip, "administrador_membro_conselho_fiscal", colunas)
    if bruto.empty:
        return pd.DataFrame(columns=list(COLUNAS_DO_CONSELHO))
    cargo = bruto["Cargo_Eletivo_Ocupado"]
    pessoas = _documento(bruto, entregas(conteudo_do_zip)).assign(
        orgao=bruto["Orgao_Administracao"].str.strip(),
        membros=1,
        suplentes=_contem(cargo, SUPLENTE).astype(int),
        independentes=_contem(cargo, INDEPENDENTE).astype(int),
        eleitos_pelo_controlador=bruto["Eleito_Controlador"]
        .str.strip()
        .eq("S")
        .astype(int),
        eleitos_por_minoritarios=_contem(cargo, MINORITARIOS).astype(int),
        eleitos_por_preferencialistas=_contem(cargo, PREFERENCIALISTAS).astype(int),
        mandatos=pd.to_numeric(bruto["Numero_Mandatos_Consecutivos"], errors="coerce"),
        reunioes=pd.to_numeric(
            bruto["Percentual_Participacao_Reunioes"].str.replace(
                ",", ".", regex=False
            ),
            errors="coerce",
        ),
    )
    chaves = [*COLUNAS_DO_DOCUMENTO, "orgao", "conhecido_em"]
    somas = pessoas.groupby(chaves, dropna=False, sort=False).agg(
        membros=("membros", "sum"), suplentes=("suplentes", "sum"),
        independentes=("independentes", "sum"),
        eleitos_pelo_controlador=("eleitos_pelo_controlador", "sum"),
        eleitos_por_minoritarios=("eleitos_por_minoritarios", "sum"),
        eleitos_por_preferencialistas=("eleitos_por_preferencialistas", "sum"),
        mandatos_consecutivos_medio=("mandatos", "mean"),
        participacao_em_reunioes_media=("reunioes", "mean"),
    )  # fmt: skip
    return _so_com_data(somas.reset_index()).reindex(columns=list(COLUNAS_DO_CONSELHO))


def ler_comites(conteudo_do_zip: bytes) -> pd.DataFrame:
    """Por documento e tipo de comitê: quantos membros e suplentes, sem pessoas."""
    colunas = [*DOCUMENTO, "Tipo_Comite", "Cargo_Ocupado"]
    bruto = _tabela(conteudo_do_zip, "membro_comite", colunas)
    if bruto.empty:
        return pd.DataFrame(columns=list(COLUNAS_DOS_COMITES))
    pessoas = _documento(bruto, entregas(conteudo_do_zip)).assign(
        tipo_de_comite=bruto["Tipo_Comite"].str.strip(),
        membros=1,
        suplentes=_contem(bruto["Cargo_Ocupado"], SUPLENTE).astype(int),
    )
    chaves = [*COLUNAS_DO_DOCUMENTO, "tipo_de_comite", "conhecido_em"]
    somas = pessoas.groupby(chaves, dropna=False, sort=False)[
        ["membros", "suplentes"]
    ].sum()
    return _so_com_data(somas.reset_index()).reindex(columns=list(COLUNAS_DOS_COMITES))


def _por_orgao(
    conteudo_do_zip: bytes, tabela: str, nomes: dict[str, str]
) -> pd.DataFrame:
    bruto = _tabela(conteudo_do_zip, tabela, [*DOCUMENTO, *nomes])
    colunas = [*COLUNAS_DO_DOCUMENTO, *nomes.values(), "conhecido_em"]
    if bruto.empty:
        return pd.DataFrame(columns=colunas)
    tabela_lida = _documento(bruto, entregas(conteudo_do_zip))
    for velho, novo in nomes.items():
        valores = bruto[velho].str.strip()
        if velho.startswith("Data_"):
            tabela_lida[novo] = pd.to_datetime(valores, errors="coerce")
        elif novo == "orgao" or novo.endswith("nao_aplicavel"):  # "S" ou "N"
            tabela_lida[novo] = valores.replace("", None)
        else:
            tabela_lida[novo] = pd.to_numeric(valores, errors="coerce").astype(float)
    return _so_com_data(tabela_lida.drop_duplicates()).reindex(columns=colunas)


def ler_remuneracao(conteudo_do_zip: bytes) -> pd.DataFrame:
    """A remuneração total por órgão e exercício, como a CVM publica (sem os textos livres)."""
    return _por_orgao(conteudo_do_zip, "remuneracao_total_orgao", REMUNERACAO)


def ler_remuneracao_extremos(conteudo_do_zip: bytes) -> pd.DataFrame:
    """A maior, a menor e a média da remuneração individual por órgão e exercício."""
    return _por_orgao(conteudo_do_zip, "remuneracao_maxima_minima_media", EXTREMOS)


def colunas_da_diversidade() -> list[str]:
    contagens = [
        f"{PREFIXOS_DA_DIVERSIDADE[tabela]}_{_snake(coluna.removeprefix('Quantidade_'))}"
        for tabela, colunas in DIVERSIDADE.items()
        for coluna in colunas
    ]
    return [*COLUNAS_DO_DOCUMENTO, "orgao", *contagens, "conhecido_em"]


def ler_diversidade(conteudo_do_zip: bytes) -> pd.DataFrame:
    """Gênero, raça e PCD por documento e órgão (FRE de 2023 em diante), numa linha por órgão."""
    chaves = [*COLUNAS_DO_DOCUMENTO, "orgao", "conhecido_em"]
    juntas: pd.DataFrame | None = None
    for tabela, colunas in DIVERSIDADE.items():
        prefixo = PREFIXOS_DA_DIVERSIDADE[tabela]
        nomes = {"Orgao_Administracao": "orgao"} | {
            c: f"{prefixo}_{_snake(c.removeprefix('Quantidade_'))}" for c in colunas
        }
        parte = _por_orgao(conteudo_do_zip, tabela, nomes)
        if parte.empty:
            continue
        juntas = (
            parte if juntas is None else juntas.merge(parte, on=chaves, how="outer")
        )
    if juntas is None:
        return pd.DataFrame(columns=colunas_da_diversidade())
    return juntas.reindex(columns=colunas_da_diversidade())


def _so_com_data(tabela: pd.DataFrame) -> pd.DataFrame:
    """Linha sem data de entrega não entra: a base nunca adivinha quando o número ficou público."""
    return tabela[tabela["conhecido_em"].notna()].reset_index(drop=True)


def juntar_baixadas(tabelas: list[pd.DataFrame]) -> pd.DataFrame:
    """As tabelas de cada baixada guardada de um ano, sem repetir linha: a versão antiga de um
    formulário, que a CVM já tirou do arquivo, continua valendo com a data dela."""
    partes = [t for t in tabelas if not t.empty]
    if not partes:
        return tabelas[0] if tabelas else pd.DataFrame()
    return pd.concat(partes, ignore_index=True).drop_duplicates().reset_index(drop=True)
