"""Dados abertos da ANM: CFEM, SIGBM e Anuário Mineral (B1, B3 e B10 da rodada de fontes de 03/11/2026).

A licença da ANM não está declarada no diretório (https://dadosabertos.anm.gov.br): **PENDENTE, só uso
interno**, e ninguém escreve à fonte (ADR 0102, Emenda 2). Os três conjuntos entram como dado declarado:

- **CFEM, arrecadação** (`anm/cfem/arrecadacao`): royalty recolhido por titular do processo, substância e
  município. O CNPJ completo vira 14 caracteres; linha sem CNPJ completo (pessoa física, CPF ou documento
  mascarado) é descartada e contada em `tabela.attrs["descartadas"]`. `DataCriacao` da linha é o
  `disponivel_em` (a coleta só vale se a fonte vier sem data).
- **SIGBM, barragens** (`anm/sigbm/barragens`): categoria de risco (CRI) e dano potencial (DPA) ficam como
  vieram, com a data da finalização da declaração (DCE) em que foram informados. O CNPJ é o do empreendedor,
  que **não é necessariamente quem opera a mina**; empreendedor sem CNPJ completo fica sem documento e sem nome.
- **AMB, Anuário Mineral** (`anm/amb/*`): produção bruta, beneficiada e água mineral por ano, UF e substância.
  Série setorial, sem CNPJ. O arquivo real é CP1252, com vírgula e aspas (não o ";" do dicionário), e
  ",000000" é 0. A unidade do contido fica por linha. Chave repetida (ano, UF, substância, indicação) **não
  é somada nem descartada**: `chaves_repetidas` lista.

**Sem olhar o futuro:** só o CFEM traz data por linha. SIGBM e AMB são sobrescritos pela ANM, sem histórico:
`disponivel_em` é a data da coleta; o ano-base nunca serve de disponibilidade.

Sem Streamlit; pandas só.
"""

import io
from datetime import date

import pandas as pd

from base import cnpj as cnpj_mod

FONTE_CFEM = "anm-cfem-arrecadacao"
FONTE_SIGBM = "anm-sigbm-barragens"
FONTE_AMB_BRUTA = "anm-amb-producao-bruta"
FONTE_AMB_BENEFICIADA = "anm-amb-producao-beneficiada"
FONTE_AMB_AGUA = "anm-amb-agua-mineral"
ATRIBUICAO = "Fonte: ANM, Dados Abertos, https://dadosabertos.anm.gov.br"
AVISO_SIGBM = (
    "Categoria de risco e dano potencial declarados pelo empreendedor no SIGBM da ANM, como vieram. O CNPJ "
    "é o do empreendedor, que não é necessariamente quem opera a mina."
)

CFEM_BRUTO_PARA_COLUNA = {
    "Ano": "ano",
    "Mês": "mes",
    "Processo": "processo",
    "AnoDoProcesso": "ano_processo",
    "Substância": "substancia",
    "UF": "uf",
    "CodigoMunicipio": "codigo_municipio",
    "Município": "municipio",
    "UnidadeDeMedida": "unidade",
}
COLUNAS_CFEM_BRUTAS = (
    "Ano", "Mês", "Processo", "AnoDoProcesso", "Tipo_PF_PJ", "CPF_CNPJ", "Substância", "UF",
    "CodigoMunicipio", "Município", "QuantidadeComercializada", "UnidadeDeMedida", "ValorRecolhido",
    "DataCriacao",
)  # fmt: skip
COLUNAS_CFEM = (
    "ano", "mes", "processo", "ano_processo", "cnpj", "cnpj_raiz", "substancia", "uf", "codigo_municipio",
    "municipio", "quantidade", "unidade", "valor_recolhido", "criado_em", "disponivel_em",
)  # fmt: skip

SIGBM_BRUTO_PARA_COLUNA = {
    "ID": "id",
    "Nome": "nome",
    "Empreendedor": "empreendedor",
    "Nome da mina": "nome_mina",
    "UF": "uf",
    "Município": "municipio",
    "Categoria de Risco - CRI": "categoria_risco",
    "Dano Potencial Associado - DPA": "dano_potencial",
    "Nível de Emergência": "nivel_emergencia",
    "Situação Operacional": "situacao_operacional",
    "Motivo de Envio": "motivo_envio",
    "Unidade Gestora": "unidade_gestora",
}
SIGBM_EXIGIDAS = (
    *SIGBM_BRUTO_PARA_COLUNA,
    "CPF_CNPJ",
    "Latitude",
    "Longitude",
    "Data da Finalização da DCE",
    "Altura máxima atual (m)",
    "Volume atual do Reservatório (m³)",
)  # fmt: skip
COLUNAS_SIGBM = (
    "id", "nome", "empreendedor", "cnpj", "cnpj_raiz", "nome_mina", "uf", "municipio", "latitude",
    "longitude", "categoria_risco", "dano_potencial", "classificado_em", "nivel_emergencia",
    "situacao_operacional", "motivo_envio", "altura_atual_m", "volume_atual_m3", "unidade_gestora",
    "disponivel_em",
)  # fmt: skip

_AMB_BASE = {"Ano base": "ano", "UF": "uf"}
AMB_BRUTA_PARA_COLUNA = {
    **_AMB_BASE,
    "Classe Substância": "classe",
    "Substância Mineral": "substancia",
    "Quantidade Produção - Minério ROM (t)": "producao_rom_t",
    "Quantidade Contido": "contido",
    "Unidade de Medida - Contido": "contido_unidade",
    "Indicação Contido": "contido_indicacao",
    "Quantidade Venda (t)": "venda_t",
    "Valor Venda (R$)": "venda_valor",
    "Quantidade Transformação / Consumo / Utilização (t)": "consumo_t",
    "Valor Transformação / Consumo / Utilização nesta mina (R$)": "consumo_valor",
    "Quantidade Transferência para Transformação / Utilização / Consumo (t)": "transferencia_t",
    "Valor Transferência para Transformação / Utilização / Consumo (R$)": "transferencia_valor",
}  # fmt: skip
AMB_BENEFICIADA_PARA_COLUNA = {
    **_AMB_BASE,
    "Classe Substância": "classe",
    "Substância Mineral": "substancia",
    "Quantidade Produção": "producao",
    "Unidade de Medida - Produção": "producao_unidade",
    "Quantidade Contido": "contido",
    "Unidade de Medida - Contido": "contido_unidade",
    "Indicação Contido": "contido_indicacao",
    "Quantidade Venda": "venda",
    "Unidade de Medida - Venda": "venda_unidade",
    "Valor Venda (R$)": "venda_valor",
    "Quantidade Consumo/Utilização na Usina": "consumo",
    "Unidade de Medida - Consumo/Utilização na Usina": "consumo_unidade",
    "Valor Consumo / Utilização na Usina (R$)": "consumo_valor",
    "Quantidade Transferência para Transformação / Utilização / Consumo": "transferencia",
    "Unidade de Medida - Transferência para Transformação / Utilização / Consumo": "transferencia_unidade",
    "Valor Transferência para Transformação / Utilização / Consumo (R$)": "transferencia_valor",
}  # fmt: skip
AMB_AGUA_PARA_COLUNA = {
    **_AMB_BASE,
    "Classe Substância Mineral": "classe",
    "Substância Mineral": "substancia",
    "Quantidade (litros) Garrafão": "litros_garrafao",
    "Quantidade (litros) Garrafa Plástica": "litros_garrafa_plastica",
    "Quantidade (litros) Garrafa de Vidro": "litros_garrafa_vidro",
    "Quantidade (litros) Copo": "litros_copo",
    "Quantidade (litros) Outras Embalagens": "litros_outras",
    "Valor (R$) Garrafão": "valor_garrafao",
    "Valor (R$) Garrafa Plástica": "valor_garrafa_plastica",
    "Valor (R$) Garrafa de Vidro": "valor_garrafa_vidro",
    "Valor (R$) Copo": "valor_copo",
    "Valor (R$) Outras Embalagens": "valor_outras",
    "Quantidade (litros) Composição Produtos Industrializados": "litros_industrializados",
    "Valor (R$) Composição Produtos Industrializados": "valor_industrializados",
    "Unidade de Medida": "unidade",
}  # fmt: skip
CHAVE_AMB_COM_INDICACAO = ["ano", "uf", "substancia", "contido_indicacao"]
CHAVE_AMB_AGUA = ["ano", "uf", "substancia"]

_FORMATOS_DE_DATA = (
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%d/%m/%Y",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d",
)


def _texto(conteudo: bytes, nome: str) -> str:
    """O arquivo da ANM é CP1252; UTF-8 (com ou sem BOM) também passa, caso ela mude."""
    try:
        return conteudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass
    try:
        return conteudo.decode("cp1252")
    except UnicodeDecodeError as erro:
        raise ValueError(f"{nome}: o arquivo não é UTF-8 nem CP1252") from erro


def _tabela_bruta(
    conteudo: bytes, nome: str, colunas: tuple[str, ...], *, exato: bool = True
) -> pd.DataFrame:
    """O CSV (vírgula, aspas) tudo como texto. `exato`: o cabeçalho tem de ser o conhecido; senão, basta
    ter as colunas exigidas (o SIGBM tem mais de cem)."""
    tabela = pd.read_csv(
        io.StringIO(_texto(conteudo, nome)),
        sep=",",
        dtype=str,
        keep_default_na=False,
        na_filter=False,
    )
    tabela.columns = [coluna.strip() for coluna in tabela.columns]
    faltam = [c for c in colunas if c not in tabela.columns]
    sobram = [c for c in tabela.columns if c not in colunas]
    if faltam or (exato and sobram):
        raise ValueError(
            f"{nome}: cabeçalho inesperado (faltam {faltam}, sobram {sobram if exato else '-'})"
        )
    return tabela


def numero(texto: str) -> float:
    """ "155024,500000" → 155024.5; ",000000" → 0.0; vazio → nulo. Vírgula é o decimal; o ponto, se vier
    junto com a vírgula, é milhar."""
    limpo = texto.strip()
    if not limpo:
        return float("nan")
    if "," in limpo:
        limpo = limpo.replace(".", "").replace(",", ".")
    return float(limpo)


def _numeros(coluna: pd.Series) -> pd.Series:
    return coluna.map(numero)


def _datas(coluna: pd.Series) -> pd.Series:
    """Datas em qualquer um dos formatos conhecidos; o que não casa vira NaT."""
    texto = coluna.str.strip()
    datas = pd.Series(pd.NaT, index=coluna.index, dtype="datetime64[ns]")
    for formato in _FORMATOS_DE_DATA:
        datas = datas.fillna(pd.to_datetime(texto, format=formato, errors="coerce"))
    return datas


def _cnpj_completo(coluna: pd.Series) -> pd.Series:
    """Os 14 caracteres do CNPJ ou vazio (CPF, documento mascarado e lixo ficam vazios)."""
    return coluna.map(lambda valor: cnpj_mod.completo(valor) or "")


def ler_cfem(conteudo: bytes, coletado_em: date) -> pd.DataFrame:
    """CFEM, arrecadação: uma linha por recolhimento de pessoa jurídica com CNPJ completo."""
    bruta = _tabela_bruta(conteudo, "CFEM", COLUNAS_CFEM_BRUTAS)
    cnpj = _cnpj_completo(bruta["CPF_CNPJ"])
    com_cnpj = cnpj != ""
    bruta, cnpj = bruta[com_cnpj], cnpj[com_cnpj]
    criado_em = _datas(bruta["DataCriacao"])
    tabela = pd.DataFrame(
        {
            **{
                coluna: bruta[bruto].str.strip()
                for bruto, coluna in CFEM_BRUTO_PARA_COLUNA.items()
            },
            "cnpj": cnpj,
            "cnpj_raiz": cnpj.str[:8],
            "quantidade": _numeros(bruta["QuantidadeComercializada"]),
            "valor_recolhido": _numeros(bruta["ValorRecolhido"]),
            "criado_em": criado_em,
            "disponivel_em": criado_em.fillna(pd.Timestamp(coletado_em)),
        }
    )
    tabela = tabela[list(COLUNAS_CFEM)].reset_index(drop=True)
    tabela.attrs["descartadas"] = int((~com_cnpj).sum())
    return tabela


def ligar_ao_qsa(
    tabela: pd.DataFrame, qsa: pd.DataFrame, coluna_raiz: str = "cnpj_basico"
) -> pd.DataFrame:
    """As linhas da tabela (CFEM ou SIGBM) ligadas ao quadro de sócios da Receita pela raiz do CNPJ.

    A raiz é a empresa; a filial não importa para o quadro de sócios. Uma linha sai por sócio.
    """
    return tabela.merge(
        qsa,
        left_on="cnpj_raiz",
        right_on=coluna_raiz,
        how="inner",
        suffixes=("", "_qsa"),
    ).reset_index(drop=True)


def ler_sigbm(conteudo: bytes, coletado_em: date) -> pd.DataFrame:
    """SIGBM, barragens: uma linha por barragem, com a classificação (CRI e DPA) como veio."""
    bruta = _tabela_bruta(conteudo, "SIGBM", SIGBM_EXIGIDAS, exato=False)
    cnpj = _cnpj_completo(bruta["CPF_CNPJ"])
    tabela = pd.DataFrame(
        {
            **{
                coluna: bruta[bruto].str.strip()
                for bruto, coluna in SIGBM_BRUTO_PARA_COLUNA.items()
            },
            "cnpj": cnpj,
            "cnpj_raiz": cnpj.str[:8],
            "latitude": _numeros(bruta["Latitude"]),
            "longitude": _numeros(bruta["Longitude"]),
            "classificado_em": _datas(bruta["Data da Finalização da DCE"]),
            "altura_atual_m": _numeros(bruta["Altura máxima atual (m)"]),
            "volume_atual_m3": _numeros(bruta["Volume atual do Reservatório (m³)"]),
            "disponivel_em": pd.Timestamp(coletado_em),
        }
    )
    # sem CNPJ completo o empreendedor pode ser uma pessoa: nem o nome fica
    tabela.loc[tabela["cnpj"] == "", "empreendedor"] = ""
    return tabela[list(COLUNAS_SIGBM)].reset_index(drop=True)


def _ler_amb(
    conteudo: bytes, nome: str, bruto_para_coluna: dict[str, str], coletado_em: date
) -> pd.DataFrame:
    bruta = _tabela_bruta(conteudo, nome, tuple(bruto_para_coluna))
    texto = {"ano", "uf", "classe", "substancia", "contido_indicacao", "unidade"}
    colunas = {}
    for bruto, coluna in bruto_para_coluna.items():
        e_texto = coluna in texto or coluna.endswith("_unidade")
        colunas[coluna] = (
            bruta[bruto].str.strip() if e_texto else _numeros(bruta[bruto])
        )
    tabela = pd.DataFrame(colunas)
    tabela["ano"] = tabela["ano"].astype(int)
    tabela["disponivel_em"] = pd.Timestamp(coletado_em)
    return tabela.reset_index(drop=True)


def ler_amb_producao_bruta(conteudo: bytes, coletado_em: date) -> pd.DataFrame:
    """AMB, produção bruta (minério ROM) por ano, UF e substância."""
    return _ler_amb(conteudo, "AMB bruta", AMB_BRUTA_PARA_COLUNA, coletado_em)


def ler_amb_producao_beneficiada(conteudo: bytes, coletado_em: date) -> pd.DataFrame:
    """AMB, produção beneficiada por ano, UF e substância, com a unidade de cada quantidade."""
    return _ler_amb(
        conteudo, "AMB beneficiada", AMB_BENEFICIADA_PARA_COLUNA, coletado_em
    )


def ler_amb_agua_mineral(conteudo: bytes, coletado_em: date) -> pd.DataFrame:
    """AMB, água mineral (litros e valor por tipo de embalagem) por ano e UF."""
    return _ler_amb(conteudo, "AMB água mineral", AMB_AGUA_PARA_COLUNA, coletado_em)


def chaves_repetidas(tabela: pd.DataFrame, chave: list[str]) -> pd.DataFrame:
    """As linhas cuja chave aparece mais de uma vez, todas elas e na ordem do arquivo; nada é somado."""
    return tabela[tabela.duplicated(subset=chave, keep=False)]
