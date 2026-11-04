"""ESTBAN do Banco Central (A3 da rodada de fontes de 03/11/2026): balancete mensal por agência e município,
com crédito, depósitos e demais verbetes contábeis (Documento 4500).

- **Fonte:** `https://www.bcb.gov.br/content/estatisticas/estatistica_bancaria_estban/agencia/AAAAMM_ESTBAN_AG.csv.zip`,
  um ZIP por competência com um CSV (`AAAAMM_ESTBAN_AG.CSV`). Página:
  `https://www.bcb.gov.br/estatisticas/estatisticabancariamunicipios`.
- **Formato** (conferido em 202512, 202602 e 202606): cp1252, `;`, 53 colunas. Duas linhas de preâmbulo
  (título e `Data de geracao dos dados: AAAA-MM-DD`), depois o cabeçalho com `#` na frente de `DATA_BASE`.
  A agência vem com apóstrofo e 14 dígitos (a raiz do CNPJ da instituição, 8, e o código da agência, 6).
  45 colunas de verbete; seis são somas (`VERBETE_141_... + VERBETE_142_...`) e dois cabeçalhos trazem
  tabulação no meio do `+`. Os valores são inteiros em reais, como o BC publica (o leiaute 4500 não foi lido
  aqui).
- **A instituição, não o tomador:** o CNPJ é o da raiz do banco que mantém a agência. O dado diz quanto
  crédito e quanto depósito há em cada município, nunca quem deve ou quem depositou.
- **Chave:** competência + raiz do CNPJ + agência + município IBGE (o código da agência repete entre
  instituições no mesmo município: 4 casos em Brasília em 202602, conferido com o arquivo real); a tabela larga tem uma linha por isso e
  `em_formato_longo` vira uma linha por verbete.

**Sem olhar o futuro:** o dado sai com cerca de 7 meses de atraso (202512 foi gerado em 03/08/2026), então
data-base + 90 dias seria cedo demais. `disponivel_em` é a mais tardia entre a data de geração do preâmbulo
e a data de modificação do arquivo no servidor (202602: gerado em 01/10, modificado em 13/10/2026), quando
quem chama a tem. O calendário do BC (Comunicado 44.132/2025: jan a mar em 31/5, abr a jun em 31/8, jul a
set em 30/11, out a dez em 31/3 do ano seguinte) é só a promessa de um prazo máximo; a competência pode sair
antes, e a data real do arquivo manda. O BC regrava as seis últimas competências todo mês: o arquivo de hoje
vale a partir de hoje, e quem quiser o histórico das revisões guarda cada baixada (o arquivista).

**Licença** (Política de Privacidade e Termos de Uso do BC, atualizada em 24/02/2022, lida em 04/11/2026
em `https://www.bcb.gov.br/acessoinformacao/politicaprivacidade`): "É permitida a reprodução total ou
parcial do conteúdo do site e dos serviços digitais do BC, preservada a integridade das informações e citada
a fonte." A página do ESTBAN não traz licença própria (nem ODbL, que é a do SCR.data): vale a regra geral,
com a atribuição abaixo e os números sem alteração. Marcada "a confirmar" no registro de fontes; só uso
interno até alguém decidir exibir.

Sem Streamlit; pandas só.
"""

import io
import re
import zipfile
from datetime import date

import pandas as pd

FONTE = "estban-agencia"
ATRIBUICAO = (
    "Fonte: Banco Central do Brasil, Estatística Bancária Mensal por município (ESTBAN), "
    "https://www.bcb.gov.br/estatisticas/estatisticabancariamunicipios"
)
AVISO = (
    "O ESTBAN mostra o balancete de cada agência: o CNPJ é o da instituição financeira, não o do tomador do "
    "crédito nem o do depositante. Sai com cerca de 7 meses de atraso."
)
ENDERECO = (
    "https://www.bcb.gov.br/content/estatisticas/estatistica_bancaria_estban/agencia/"
    "{competencia}_ESTBAN_AG.csv.zip"
)
CODIFICACAO = "cp1252"

VERBETE_CREDITO = "160"  # operações de crédito
VERBETE_POUPANCA = "420"  # depósitos de poupança
VERBETE_DEPOSITO_A_PRAZO = "432"
VERBETE_TOTAL_DO_ATIVO = "399"

COLUNAS_DE_IDENTIFICACAO = (
    "competencia", "data_base", "uf", "codigo_municipio_bcb", "municipio", "codigo_ibge_municipio",
    "cnpj_raiz", "instituicao", "agencia",
)  # fmt: skip
COLUNAS_DE_DATA = ("gerado_em", "disponivel_em")
CHAVE = ["competencia", "cnpj_raiz", "agencia", "codigo_ibge_municipio"]
CHAVE_LONGA = [*CHAVE, "verbete"]

_ROTULO_DA_GERACAO = "data de geracao dos dados:"
_CABECALHO = "#DATA_BASE"
_CODIGO_DE_VERBETE = re.compile(r"VERBETE_(\d+)")


def endereco_da_competencia(competencia: int) -> str:
    return ENDERECO.format(competencia=competencia)


def _linhas_do_arquivo(conteudo_do_zip: bytes) -> list[str]:
    with zipfile.ZipFile(io.BytesIO(conteudo_do_zip)) as arquivo:
        nomes = arquivo.namelist()
        if len(nomes) != 1:
            raise ValueError(f"ESTBAN: o ZIP deveria ter 1 arquivo, tem {len(nomes)}")
        texto = arquivo.read(nomes[0]).decode(CODIFICACAO)
    return texto.splitlines()


def _geracao_e_cabecalho(linhas: list[str]) -> tuple[date, int]:
    """A data de geração do preâmbulo e o índice da linha do cabeçalho."""
    geracao = None
    for indice, linha in enumerate(linhas[:5]):
        if linha.lower().startswith(_ROTULO_DA_GERACAO):
            geracao = date.fromisoformat(linha.split(":", 1)[1].strip())
        if linha.startswith(_CABECALHO):
            if geracao is None:
                raise ValueError("ESTBAN: o preâmbulo não traz a data de geração")
            return geracao, indice
    raise ValueError(f"ESTBAN: não achei o cabeçalho {_CABECALHO}")


def codigo_do_verbete(cabecalho: str) -> str:
    """`VERBETE_141_X + VERBETE_142_Y` vira `141+142`; `VERBETE_160_Z` vira `160`."""
    codigos = _CODIGO_DE_VERBETE.findall(cabecalho)
    if not codigos:
        raise ValueError(f"ESTBAN: cabeçalho de verbete sem código: {cabecalho!r}")
    return "+".join(codigos)


def nome_da_coluna(codigo: str) -> str:
    return "verbete_" + codigo.replace("+", "_")


def _numero(coluna: pd.Series) -> pd.Series:
    return pd.to_numeric(coluna.str.replace(",", ".", regex=False)).astype("Int64")


def _tabela_bruta(linhas: list[str], indice_do_cabecalho: int) -> pd.DataFrame:
    corpo = [linha for linha in linhas[indice_do_cabecalho:] if linha.strip()]
    bruto = pd.read_csv(
        io.StringIO("\n".join(corpo)), sep=";", dtype=str, keep_default_na=False
    )
    bruto.columns = [coluna.lstrip("#").strip() for coluna in bruto.columns]
    return bruto


def _identificacao(bruto: pd.DataFrame) -> pd.DataFrame:
    data_base = pd.to_datetime(bruto["DATA_BASE"], format="%Y%m")
    return pd.DataFrame(
        {
            "competencia": data_base.dt.year * 100 + data_base.dt.month,
            "data_base": data_base,
            "uf": bruto["UF"].str.strip(),
            "codigo_municipio_bcb": bruto["CODMUN"].str.strip(),
            "municipio": bruto["MUNICIPIO"].str.strip(),
            "codigo_ibge_municipio": bruto["CODMUN_IBGE"].str.strip().str.zfill(7),
            "cnpj_raiz": bruto["CNPJ"].str.strip().str.zfill(8),
            "instituicao": bruto["NOME_INSTITUICAO"].str.strip(),
            "agencia": bruto["AGENCIA"].str.strip().str.lstrip("'"),
        }
    )


def disponivel_em(gerado_em: date, modificado_em: date | None = None) -> pd.Timestamp:
    """Desde quando a competência era pública: a mais tardia entre a geração do arquivo e (se houver) a
    modificação dele no servidor. Nunca data-base + prazo fixo: o atraso real é de ~7 meses."""
    return pd.Timestamp(max(gerado_em, modificado_em or gerado_em))


def ler_competencia(
    conteudo_do_zip: bytes, modificado_em: date | None = None
) -> pd.DataFrame:
    """A competência do ZIP numa tabela larga: uma linha por agência e município, uma coluna por verbete.

    Levanta ValueError para preâmbulo/cabeçalho fora do formato, mais de uma competência no arquivo ou
    agência repetida no mesmo município."""
    linhas = _linhas_do_arquivo(conteudo_do_zip)
    gerado_em, indice = _geracao_e_cabecalho(linhas)
    bruto = _tabela_bruta(linhas, indice)
    tabela = _identificacao(bruto)
    if tabela["competencia"].nunique() > 1:
        raise ValueError("ESTBAN: o arquivo mistura competências")
    for cabecalho in bruto.columns:
        if cabecalho.startswith("VERBETE_"):
            nome = nome_da_coluna(codigo_do_verbete(cabecalho))
            tabela[nome] = _numero(bruto[cabecalho])
    if tabela.duplicated(CHAVE).any():
        raise ValueError(
            "ESTBAN: agência repetida (mesma instituição, agência e município) na competência"
        )
    tabela["gerado_em"] = pd.Timestamp(gerado_em)
    pronto = disponivel_em(gerado_em, modificado_em)
    tabela["disponivel_em"] = pronto
    return tabela.reset_index(drop=True)


def colunas_de_verbete(tabela: pd.DataFrame) -> list[str]:
    return [c for c in tabela.columns if c.startswith("verbete_")]


def em_formato_longo(tabela: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por agência, município, competência e verbete (`verbete` = `160`, `141+142`...)."""
    verbetes = colunas_de_verbete(tabela)
    fixas = [c for c in tabela.columns if c not in verbetes]
    longa = tabela.melt(
        id_vars=fixas, value_vars=verbetes, var_name="verbete", value_name="saldo"
    )
    longa["verbete"] = (
        longa["verbete"].str.removeprefix("verbete_").str.replace("_", "+")
    )
    return longa.reset_index(drop=True)


def atraso_de_publicacao_em_dias(tabela: pd.DataFrame) -> pd.Series:
    """Dias entre o fim do mês da data-base e `disponivel_em`: o atraso real, medido."""
    fim_do_mes = tabela["data_base"] + pd.offsets.MonthEnd(0)
    return (tabela["disponivel_em"] - fim_do_mes).dt.days


def por_municipio(tabela: pd.DataFrame, verbete: str) -> pd.DataFrame:
    """Saldo do verbete somado por município e competência (todas as instituições)."""
    coluna = nome_da_coluna(verbete)
    return (
        tabela.groupby(["competencia", "codigo_ibge_municipio"], as_index=False)
        .agg(saldo=(coluna, "sum"), agencias=("agencia", "nunique"))
        .assign(verbete=verbete)
    )
