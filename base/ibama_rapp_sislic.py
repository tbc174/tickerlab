"""RAPP de madeira e lenha e SISLIC do Ibama (B9 da rodada de fontes de 03/11/2026).

Os dois conjuntos são de domínio público (Open Definition, no portal de dados abertos do Ibama) e entram como
dado declarado, nunca como veredito:

- **RAPP, madeira e lenha** (`ibama/rapp/madeira_lenha`): uma linha por estabelecimento (CNPJ pontuado de 14
  dígitos) e ano. O CNPJ é normalizado para só dígitos. A unidade da lenha ("estéreo ou m³") vem do cabeçalho
  e fica numa coluna, **sem converter**. 0,00 é guardado como 0,0 (declarou zero); estabelecimento que não
  aparece no arquivo não declarou, o que **não é o mesmo que zero** (`AVISO_RAPP`).
- **SISLIC** (`ibama/sislic/licencas`): licenças ambientais federais. A ligação com autos e embargos do Ibama é
  **só pelo número do processo** (`NUM_PROCESSO_IBAMA`); o nome nunca liga, nem como candidato. O campo PAC
  fica como veio ("Sim"/"No"), sem interpretar, porque o dicionário do portal não o descreve.

Nada de pessoa física: linha do RAPP cujo documento não tem 14 dígitos é descartada, e o nome do titular do
SISLIC só fica quando parece de pessoa jurídica (a ligação é pelo processo, então o nome não faz falta).

**Sem olhar o futuro:** nenhum dos arquivos traz data de divulgação por linha (o RAPP é sobrescrito, sem
histórico). `disponivel_em` é a data da coleta; o ano de referência nunca serve de disponibilidade.

Sem Streamlit; pandas só.
"""

import io
import re
from datetime import date

import pandas as pd

FONTE_RAPP = "ibama-rapp-madeira-lenha"
FONTE_SISLIC = "ibama-sislic-licencas"
ATRIBUICAO = (
    "Fonte: Ibama, Dados Abertos (domínio público), https://dadosabertos.ibama.gov.br"
)
AVISO_RAPP = (
    "Dado declarado pelo próprio estabelecimento no RAPP do Ibama. Quem não declarou não aparece, e não "
    "declarar não é o mesmo que zero; 0,00 quer dizer que o estabelecimento declarou zero."
)
AVISO_SISLIC = (
    "Licenças ambientais federais (SISLIC). Ligam-se a autos e embargos do Ibama só pelo número do processo; "
    "o nome do empreendimento ou do titular nunca liga."
)

COLUNAS_RAPP_BRUTAS = (
    "CNPJ", "Razão Social", "Estado", "Município", "Ano", "Lenha (estéreo ou m³)", "Tora (m³)",
    "Área Total Explorada (ha)", "Situação Cadastral",
)  # fmt: skip
COLUNAS_RAPP = (
    "cnpj", "cnpj_raiz", "razao_social", "uf", "municipio", "ano", "lenha", "lenha_unidade", "tora",
    "tora_unidade", "area_explorada", "area_unidade", "situacao_cadastral", "disponivel_em",
)  # fmt: skip
CHAVE_RAPP = ["cnpj", "ano"]

COLUNAS_SISLIC_BRUTAS = (
    "DES_TIPOLICENCA", "NUM_LICENCA", "DAT_EMISSAO", "DAT_VENCIMENTO", "NOM_EMPREENDIMENTO", "NOM_PESSOA",
    "NUM_PROCESSO_IBAMA", "DES_TIPOLOGIA", "PAC", "ultima_atualizacao_relatorio",
)  # fmt: skip
COLUNAS_SISLIC = (
    "tipo_licenca", "numero_licenca", "emitida_em", "vence_em", "empreendimento", "titular",
    "processo_ibama", "tipologia", "pac", "atualizado_no_relatorio", "disponivel_em",
)  # fmt: skip
CHAVE_SISLIC = ["processo_ibama", "tipo_licenca", "numero_licenca", "emitida_em"]

_DIGITOS_DO_CNPJ = 14
_UNIDADE_ENTRE_PARENTESES = re.compile(r"\(([^)]*)\)\s*$")
# o que marca um titular como pessoa jurídica ou órgão público; sem isso o nome não é guardado
_MARCA_DE_PJ = re.compile(
    r"\b(S\.? ?A\.?|S/A|LTDA\.?|EIRELI|EPP|ME|COMPANHIA|CIA\.?|EMPRESA|CONS[OÓ]RCIO|COOPERATIVA|"
    r"ASSOCIA[CÇ][AÃ]O|FUNDA[CÇ][AÃ]O|INSTITUTO|SECRETARIA|MINIST[EÉ]RIO|PREFEITURA|UNI[AÃ]O|"
    r"PETROBRAS|ELETROBRAS|CONCESSION[AÁ]RIA|TRANSMISSORA|DEPARTAMENTO|AUTARQUIA|ESTADO|MUNIC[IÍ]PIO)\b",
    re.IGNORECASE,
)


def _tabela_bruta(conteudo: bytes, colunas: tuple[str, ...], nome: str) -> pd.DataFrame:
    """O CSV (UTF-8 com BOM, separado por ponto e vírgula) tudo como texto, conferindo o cabeçalho."""
    try:
        texto = conteudo.decode("utf-8-sig")
    except UnicodeDecodeError as erro:
        raise ValueError(f"{nome}: o arquivo não é UTF-8") from erro
    tabela = pd.read_csv(
        io.StringIO(texto), sep=";", dtype=str, keep_default_na=False, na_filter=False
    )
    if tuple(tabela.columns) != colunas:
        raise ValueError(f"{nome}: cabeçalho inesperado: {list(tabela.columns)}")
    return tabela


def normalizar_cnpj(texto: str) -> str:
    """Só os dígitos do CNPJ ("00.001.180/0001-26" → "00001180000126"); vazio se não tiver 14."""
    digitos = re.sub(r"\D", "", texto or "")
    return digitos if len(digitos) == _DIGITOS_DO_CNPJ else ""


def _numero_brasileiro(texto: str) -> float:
    """ "20.000,00" → 20000.0; vazio → nulo. 0,00 continua sendo 0.0, nunca nulo."""
    limpo = texto.strip().replace(".", "").replace(",", ".")
    return float(limpo) if limpo else float("nan")


def _unidade(cabecalho: str) -> str:
    achado = _UNIDADE_ENTRE_PARENTESES.search(cabecalho)
    if not achado:
        raise ValueError(f"RAPP: não achei a unidade no cabeçalho {cabecalho!r}")
    return achado.group(1)


def ler_rapp_madeira_lenha(conteudo: bytes, coletado_em: date) -> pd.DataFrame:
    """RAPP de madeira e lenha, uma linha por CNPJ de estabelecimento e ano, coletado em `coletado_em`."""
    bruta = _tabela_bruta(conteudo, COLUNAS_RAPP_BRUTAS, "RAPP")
    cnpj = bruta["CNPJ"].map(normalizar_cnpj)
    bruta, cnpj = (
        bruta[cnpj != ""],
        cnpj[cnpj != ""],
    )  # pessoa física (e lixo) fica de fora
    lenha, tora, area = COLUNAS_RAPP_BRUTAS[5:8]
    tabela = pd.DataFrame(
        {
            "cnpj": cnpj,
            "cnpj_raiz": cnpj.str[:8],
            "razao_social": bruta["Razão Social"].str.strip(),
            "uf": bruta["Estado"].str.strip(),
            "municipio": bruta["Município"].str.strip(),
            "ano": bruta["Ano"].astype(int),
            "lenha": bruta[lenha].map(_numero_brasileiro),
            "lenha_unidade": _unidade(lenha),
            "tora": bruta[tora].map(_numero_brasileiro),
            "tora_unidade": _unidade(tora),
            "area_explorada": bruta[area].map(_numero_brasileiro),
            "area_unidade": _unidade(area),
            "situacao_cadastral": bruta["Situação Cadastral"].str.strip(),
            "disponivel_em": pd.Timestamp(coletado_em),
        }
    )
    return tabela[list(COLUNAS_RAPP)].reset_index(drop=True)


def _data_brasileira(coluna: pd.Series, formato: str = "%d/%m/%Y") -> pd.Series:
    return pd.to_datetime(coluna.str.strip(), format=formato, errors="coerce")


def _titular_sem_pessoa_fisica(nome: str) -> str:
    return nome.strip() if _MARCA_DE_PJ.search(nome) else ""


def normalizar_processo(texto: str) -> str:
    """O número do processo do Ibama só com dígitos ("02001.002739/2004-11" → "02001002739200411")."""
    return re.sub(r"\D", "", texto or "")


def ler_sislic(conteudo: bytes, coletado_em: date) -> pd.DataFrame:
    """Licenças do SISLIC (arquivo ordenado por tipo e data), coletadas em `coletado_em`.

    O processo fica como veio (a chave de ligação é `normalizar_processo` dele); o PAC não é interpretado.
    """
    bruta = _tabela_bruta(conteudo, COLUNAS_SISLIC_BRUTAS, "SISLIC")
    tabela = pd.DataFrame(
        {
            "tipo_licenca": bruta["DES_TIPOLICENCA"].str.strip(),
            "numero_licenca": bruta["NUM_LICENCA"].str.strip(),
            "emitida_em": _data_brasileira(bruta["DAT_EMISSAO"]),
            "vence_em": _data_brasileira(bruta["DAT_VENCIMENTO"]),
            "empreendimento": bruta["NOM_EMPREENDIMENTO"].str.strip(),
            "titular": bruta["NOM_PESSOA"].map(_titular_sem_pessoa_fisica),
            "processo_ibama": bruta["NUM_PROCESSO_IBAMA"].str.strip(),
            "tipologia": bruta["DES_TIPOLOGIA"].str.strip(),
            "pac": bruta["PAC"],
            "atualizado_no_relatorio": _data_brasileira(
                bruta["ultima_atualizacao_relatorio"], "%d/%m/%Y %H:%M"
            ),
            "disponivel_em": pd.Timestamp(coletado_em),
        }
    )
    return tabela[list(COLUNAS_SISLIC)].reset_index(drop=True)


def ligar_por_processo(
    licencas: pd.DataFrame, outra: pd.DataFrame, coluna_processo: str
) -> pd.DataFrame:
    """As licenças ligadas às linhas de `outra` (autos, embargos) pelo número do processo, e só por ele."""
    esquerda = licencas.assign(
        _processo=licencas["processo_ibama"].map(normalizar_processo)
    )
    direita = outra.assign(_processo=outra[coluna_processo].map(normalizar_processo))
    ligadas = esquerda[esquerda["_processo"] != ""].merge(
        direita[direita["_processo"] != ""], on="_processo", suffixes=("", "_outra")
    )
    return ligadas.drop(columns="_processo").reset_index(drop=True)
