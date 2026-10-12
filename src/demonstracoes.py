"""Demonstrações financeiras das companhias abertas, a partir dos dados abertos da CVM (Research,
etapa 3a).

- **DFP** (anual) e **ITR** (trimestral): DRE, balanço (ativo e passivo), fluxo de caixa e a
  composição do capital (quantidade de ações). Cada arquivo anual traz um índice com a **data de
  entrega** e o **link** de cada documento: a evidência de cada número e a data em que ele ficou
  público (para nunca usar um balanço antes de ele existir).
- **Cadastro** (`cad_cia_aberta.csv`): o setor de cada companhia (bancos e seguradoras usam outro
  plano de contas e são tratados à parte no cálculo).

Daqui sai uma tabela "longa" com poucas **contas-chave** por documento (receita, lucro, EBIT,
caixa, dívida, patrimônio, ações...), já em reais (a CVM informa em milhares). O plano de contas da
CVM muda de código entre empresas comuns e financeiras (no Itaú o lucro é a conta 3.09; na
Petrobras, a 3.11), por isso cada conta é achada pelo **código e pela descrição**, não só pelo
código. Funções puras, testadas com amostras reais em `tests/arquivos/cvm/`.
"""

import io
import unicodedata
import zipfile
from collections.abc import Iterable

import pandas as pd

URL_DO_DFP = (
    "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/DADOS/dfp_cia_aberta_{ano}.zip"
)
URL_DO_ITR = (
    "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/ITR/DADOS/itr_cia_aberta_{ano}.zip"
)
URL_DO_CADASTRO = (
    "https://dados.cvm.gov.br/dados/CIA_ABERTA/CAD/DADOS/cad_cia_aberta.csv"
)
CODIFICACAO_DA_CVM = "cp1252"
ESCALAS = {"MIL": 1_000, "UNIDADE": 1}
POSICAO = "posicao"  # saldo numa data (balanço, ações)
EXERCICIO = "exercicio"  # fluxo do ano inteiro (DFP)
ACUMULADO = "acumulado"  # fluxo do começo do ano até o trimestre (ITR)
ACUMULADO_ANTERIOR = "acumulado_anterior"  # o mesmo período do ano anterior (ITR)
# setores da CVM cujo balanço não segue o plano das empresas comuns
SETORES_FINANCEIROS = (
    "bancos",
    "seguradoras",
    "arrendamento mercantil",
    "intermediacao",
)
COLUNAS = [
    "cnpj", "documento", "referencia", "versao", "periodo", "inicio", "fim", "conta", "valor",
]  # fmt: skip


def _sem_acento(texto: str) -> str:
    texto = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in texto if unicodedata.category(c) != "Mn").lower().strip()


def _ler(arquivo: zipfile.ZipFile, contem: str) -> pd.DataFrame:
    nomes = [n for n in arquivo.namelist() if contem in n]
    if not nomes:
        return pd.DataFrame()
    return pd.read_csv(
        arquivo.open(nomes[0]),
        sep=";",
        encoding=CODIFICACAO_DA_CVM,
        encoding_errors="replace",
        dtype=str,
        keep_default_na=False,
    )


def _profundidade(codigo: str) -> int:
    return codigo.count(".")


def _contas_da_dre(dre: pd.DataFrame) -> pd.DataFrame:
    """Receita, resultado bruto, EBIT, lucro e lucro dos controladores, pelo código e descrição."""
    ds = dre["DS_CONTA"].map(_sem_acento)
    cd = dre["CD_CONTA"]
    nivel_2 = cd.map(_profundidade) == 1
    escolhas = {
        "receita": cd == "3.01",
        "resultado_bruto": (cd == "3.03") & ds.str.startswith("resultado bruto"),
        "ebit": nivel_2
        & ds.str.startswith("resultado antes do resultado financeiro e dos tributos"),
        "lucro_liquido": nivel_2
        & (
            ds.str.startswith("lucro/prejuizo consolidado do periodo")
            | ds.str.startswith("lucro/prejuizo do periodo")
            | ds.str.startswith("lucro ou prejuizo liquido")
        ),
        "lucro_controladores": (cd.map(_profundidade) == 2)
        & ds.str.match(r"atribuido (a|aos) socios da empresa controladora"),
        # lucro básico por ação da 1ª classe (em reais por ação, sem a escala "MIL"): serve
        # para conferir se a quantidade de ações foi informada em milhares
        "lpa_basico": cd == "3.99.01.01",
    }
    return _marcar(dre, escolhas)


def _contas_do_balanco(bpa: pd.DataFrame, bpp: pd.DataFrame) -> pd.DataFrame:
    partes = []
    if not bpa.empty:
        ds, cd = bpa["DS_CONTA"].map(_sem_acento), bpa["CD_CONTA"]
        partes.append(
            _marcar(
                bpa,
                {
                    "ativo_total": cd == "1",
                    "caixa": (cd == "1.01.01") & ds.str.startswith("caixa"),
                    "aplicacoes": (cd == "1.01.02") & ds.str.startswith("aplicacoes"),
                },
            )
        )
    if not bpp.empty:
        ds, cd = bpp["DS_CONTA"].map(_sem_acento), bpp["CD_CONTA"]
        partes.append(
            _marcar(
                bpp,
                {
                    "divida_cp": (cd == "2.01.04")
                    & ds.str.startswith("emprestimos e financiamentos"),
                    "divida_lp": (cd == "2.02.01")
                    & ds.str.startswith("emprestimos e financiamentos"),
                    "patrimonio_liquido": (cd.map(_profundidade) == 1)
                    & ds.str.startswith("patrimonio liquido"),
                    "minoritarios": (cd.map(_profundidade) == 2)
                    & ds.str.startswith(
                        "participacao dos acionistas nao controladores"
                    ),
                },
            )
        )
    return pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()


def _contas_do_fluxo(dfc: pd.DataFrame) -> pd.DataFrame:
    if dfc.empty:
        return dfc
    ds = dfc["DS_CONTA"].map(_sem_acento)
    return _marcar(
        dfc, {"fco": (dfc["CD_CONTA"] == "6.01") & ds.str.startswith("caixa liquido")}
    )


def _marcar(tabela: pd.DataFrame, escolhas: dict[str, pd.Series]) -> pd.DataFrame:
    partes = []
    for conta, filtro in escolhas.items():
        escolhidas = tabela[filtro].copy()
        escolhidas["conta"] = conta
        partes.append(escolhidas)
    return pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()


def _periodos(contas: pd.DataFrame, documento: str) -> pd.Series:
    """Que tipo de valor é cada linha: saldo, ano inteiro, acumulado do ano ou o do ano anterior.

    "ÚLTIMO" é o período do documento; "PENÚLTIMO", o de comparação. Balanço não tem data de
    início: fica só o saldo da data do documento. No ITR, o trimestre isolado não é usado (os 12
    meses saem dos acumulados do ano). Linhas que não servem ficam vazias (None).
    """
    inicio = contas["DT_INI_EXERC"].fillna("") if "DT_INI_EXERC" in contas else ""
    ultimo = contas["ORDEM_EXERC"].astype(str).str.startswith("Ú")
    saldo = pd.Series(inicio, index=contas.index).eq("")
    periodo = pd.Series(None, index=contas.index, dtype=object)
    periodo[saldo & ultimo] = POSICAO
    if documento == "DFP":
        periodo[~saldo & ultimo] = EXERCICIO
    else:
        do_ano = pd.Series(inicio, index=contas.index).str.endswith("-01-01")
        periodo[~saldo & do_ano & ultimo] = ACUMULADO
        periodo[~saldo & do_ano & ~ultimo] = ACUMULADO_ANTERIOR
    return periodo


def ler_demonstracoes(
    conteudo_do_zip: bytes, documento: str
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(contas, documentos) de um arquivo anual de DFP ou ITR da CVM.

    `contas`: uma linha por empresa, documento, período e conta-chave, em reais; só a versão mais
    nova de cada documento e, por empresa, o consolidado (ou o individual, se não houver
    consolidado). Colunas: cnpj, documento, referencia, versao, periodo, inicio, fim, conta, valor.
    `documentos`: cnpj, empresa, documento, referencia, versao, recebido_em, link.
    """
    prefixo = documento.lower()
    with zipfile.ZipFile(io.BytesIO(conteudo_do_zip)) as arquivo:
        indice = _ler(arquivo, f"{prefixo}_cia_aberta_20")
        partes = []
        for tipo in ("con", "ind"):
            dre = _ler(arquivo, f"_DRE_{tipo}_")
            bpa, bpp = _ler(arquivo, f"_BPA_{tipo}_"), _ler(arquivo, f"_BPP_{tipo}_")
            fluxo = pd.concat(
                [_ler(arquivo, f"_DFC_MI_{tipo}_"), _ler(arquivo, f"_DFC_MD_{tipo}_")],
                ignore_index=True,
            )
            contas = pd.concat(
                [
                    _contas_da_dre(dre) if not dre.empty else pd.DataFrame(),
                    _contas_do_balanco(bpa, bpp),
                    _contas_do_fluxo(fluxo),
                ],
                ignore_index=True,
            )
            if not contas.empty:
                contas["tipo"] = tipo
                partes.append(contas)
        capital = _ler(arquivo, "composicao_capital")
    contas = _normalizar(
        pd.concat(partes, ignore_index=True) if partes else pd.DataFrame(), documento
    )
    contas = pd.concat([contas, _acoes(capital, documento)], ignore_index=True)
    contas = _so_a_versao_mais_nova(contas)
    return contas[COLUNAS].reset_index(drop=True), _documentos(indice, documento)


def _normalizar(contas: pd.DataFrame, documento: str) -> pd.DataFrame:
    if contas.empty:
        return pd.DataFrame(columns=[*COLUNAS, "tipo"])
    # por empresa: o consolidado quando existir (o individual ignora as controladas)
    tem_consolidado = set(contas.loc[contas["tipo"] == "con", "CNPJ_CIA"])
    contas = contas[
        (contas["tipo"] == "con") | ~contas["CNPJ_CIA"].isin(tem_consolidado)
    ].copy()
    contas["periodo"] = _periodos(contas, documento)
    contas = contas.dropna(subset=["periodo"])
    escala = contas["ESCALA_MOEDA"].str.upper().map(ESCALAS).fillna(1)
    escala = escala.where(
        contas["conta"] != "lpa_basico", 1
    )  # reais por ação: sem escala
    return pd.DataFrame(
        {
            "cnpj": contas["CNPJ_CIA"].str.strip(),
            "documento": documento,
            "referencia": pd.to_datetime(contas["DT_REFER"]).dt.date,
            "versao": pd.to_numeric(contas["VERSAO"], errors="coerce")
            .fillna(1)
            .astype(int),
            "periodo": contas["periodo"],
            "inicio": pd.to_datetime(
                contas.get("DT_INI_EXERC"), errors="coerce"
            ).dt.date,
            "fim": pd.to_datetime(contas["DT_FIM_EXERC"]).dt.date,
            "conta": contas["conta"],
            "valor": pd.to_numeric(contas["VL_CONTA"], errors="coerce") * escala,
            "tipo": contas["tipo"],
        }
    ).dropna(subset=["valor"])


def _acoes(capital: pd.DataFrame, documento: str) -> pd.DataFrame:
    """Total de ações e ações em tesouraria (para lucro e patrimônio por ação)."""
    if capital.empty:
        return pd.DataFrame(columns=COLUNAS)
    partes = []
    for conta, coluna in (
        ("acoes_total", "QT_ACAO_TOTAL_CAP_INTEGR"),
        ("acoes_tesouraria", "QT_ACAO_TOTAL_TESOURO"),
    ):
        referencia = pd.to_datetime(capital["DT_REFER"]).dt.date
        partes.append(
            pd.DataFrame(
                {
                    "cnpj": capital["CNPJ_CIA"].str.strip(),
                    "documento": documento,
                    "referencia": referencia,
                    "versao": pd.to_numeric(capital["VERSAO"], errors="coerce")
                    .fillna(1)
                    .astype(int),
                    "periodo": POSICAO,
                    "inicio": None,
                    "fim": referencia,
                    "conta": conta,
                    "valor": pd.to_numeric(capital[coluna], errors="coerce"),
                }
            )
        )
    return pd.concat(partes, ignore_index=True).dropna(subset=["valor"])


def _so_a_versao_mais_nova(contas: pd.DataFrame) -> pd.DataFrame:
    """Reapresentações: fica só a versão mais nova de cada documento (empresa + data)."""
    if contas.empty:
        return contas
    mais_nova = contas.groupby(["cnpj", "referencia"])["versao"].transform("max")
    contas = contas[contas["versao"] == mais_nova]
    # a mesma conta e período com duas datas de início (empresa aberta no meio do ano declara o
    # exercício duas vezes): fica a de início mais cedo
    chave = ["cnpj", "referencia", "periodo", "fim", "conta"]
    contas = contas.sort_values("inicio", key=lambda d: d.map(str), na_position="last")
    return contas.drop_duplicates(chave, keep="first")


def _documentos(indice: pd.DataFrame, documento: str) -> pd.DataFrame:
    colunas = [
        "cnpj",
        "empresa",
        "documento",
        "referencia",
        "versao",
        "recebido_em",
        "link",
    ]
    if indice.empty:
        return pd.DataFrame(columns=colunas)
    tabela = _todas_as_versoes(indice, documento)
    tabela = tabela.sort_values("versao").drop_duplicates(
        ["cnpj", "referencia"], keep="last"
    )
    return tabela[colunas].reset_index(drop=True)


def _todas_as_versoes(indice: pd.DataFrame, documento: str) -> pd.DataFrame:
    """O índice da CVM com nomes nossos, uma linha por versão de cada documento."""
    return pd.DataFrame(
        {
            "cnpj": indice["CNPJ_CIA"].str.strip(),
            "empresa": indice["DENOM_CIA"].str.strip(),
            "documento": documento,
            "referencia": pd.to_datetime(indice["DT_REFER"]).dt.date,
            "versao": pd.to_numeric(indice["VERSAO"], errors="coerce")
            .fillna(1)
            .astype(int),
            "recebido_em": pd.to_datetime(indice["DT_RECEB"], errors="coerce").dt.date,
            "link": indice["LINK_DOC"]
            .str.strip()
            .str.replace("http://", "https://", n=1),
        }
    )


def ler_primeiras_entregas(conteudo_do_zip: bytes, documento: str) -> pd.DataFrame:
    """A primeira entrega de cada documento (versão 1) do índice de um arquivo de DFP ou ITR.

    Colunas: cnpj, empresa, documento, referencia, primeira_entrega, link. O índice da CVM guarda
    todas as versões; a primeira é a que conta para o prazo.
    """
    with zipfile.ZipFile(io.BytesIO(conteudo_do_zip)) as arquivo:
        indice = _ler(arquivo, f"{documento.lower()}_cia_aberta_20")
    colunas = ["cnpj", "empresa", "documento", "referencia", "primeira_entrega", "link"]
    if indice.empty:
        return pd.DataFrame(columns=colunas)
    tabela = _todas_as_versoes(indice, documento)
    tabela = tabela.sort_values("versao").drop_duplicates(["cnpj", "referencia"])
    tabela = tabela.rename(columns={"recebido_em": "primeira_entrega"})
    return tabela[colunas].reset_index(drop=True)


def ler_setores(conteudo_csv: bytes) -> pd.DataFrame:
    """CNPJ → setor de atividade (do registro ativo, quando houver mais de um)."""
    cadastro = pd.read_csv(
        io.BytesIO(conteudo_csv),
        sep=";",
        encoding=CODIFICACAO_DA_CVM,
        encoding_errors="replace",
        dtype=str,
        keep_default_na=False,
    )
    cadastro["ativo"] = cadastro["SIT"].str.upper().eq("ATIVO")
    cadastro = cadastro.sort_values("ativo").drop_duplicates("CNPJ_CIA", keep="last")
    return pd.DataFrame(
        {
            "cnpj": cadastro["CNPJ_CIA"].str.strip(),
            "setor": cadastro["SETOR_ATIV"].str.strip(),
        }
    ).reset_index(drop=True)


def e_financeira(setor: str, contas_da_empresa: Iterable[str] = ()) -> bool:
    """Banco, seguradora ou parecido: pelo setor da CVM, ou pela falta da conta de EBIT na DRE."""
    setor = _sem_acento(setor)
    if any(s in setor for s in SETORES_FINANCEIROS):
        return True
    contas = set(contas_da_empresa)
    return bool(contas) and "receita" in contas and "ebit" not in contas
