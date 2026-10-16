"""Ofertas públicas de valores mobiliários registradas na CVM (série 4 da base de ML, PR 6): emissões
de ações, debêntures, notas, CRI, CRA e cotas, por CNPJ do emissor, no formato da CVM.

Dois arquivos dentro de `OFERTA/DISTRIB/DADOS/oferta_distribuicao.zip` (ODbL), regerado todo dia:
- `oferta_distribuicao.csv`: as ofertas até a Resolução CVM 160 (ICVM 400, 476 e 555), desde 1989;
- `oferta_resolucao_160.csv`: os requerimentos pela Resolução 160, de 2023 em diante.

Uma linha por série ou ativo da oferta, como a CVM publica: nas antigas não há chave única (a ICVM
476 não tem número de processo; ~5% das linhas repetem as colunas da chave do contrato). Só entra
oferta com CNPJ do emissor (os fundos sem CNPJ no arquivo saem). O nome do vendedor (na
oferta secundária pode ser pessoa física) nunca entra, nem o nome e o documento do ofertante sem
CNPJ (às vezes um CPF); dos
requerimentos da 160 saem os textos livres (devedores, garantias, lastro), que podem citar pessoas.

"Como era na data", medido em 16/10/2026 sobre o arquivo de 15/10:
- `anunciada_em`: quando a oferta ficou pública na CVM. É o registro (ICVM 400 com registro, 555 e
  160), a dispensa (ICVM 400 dispensada) ou o comunicado de encerramento (ICVM 476, oferta restrita,
  que a CVM só via no fim);
- `disponivel_em`: quando a linha inteira era pública: o mais tarde entre o anúncio e o encerramento
  (ou o comunicado), porque a quantidade final e os investidores por tipo só saem no fim; oferta
  ainda aberta usa o anúncio. Pode atrasar, nunca adiantar. Requerimento sem registro (em análise)
  não entra.
"""

import io
import re
import zipfile

import pandas as pd

FONTE = "cvm-ofertas"
URL = "https://dados.cvm.gov.br/dados/OFERTA/DISTRIB/DADOS/oferta_distribuicao.zip"
CODIFICACAO = "latin-1"
ANTIGAS = "oferta_distribuicao.csv"
RESOLUCAO_160 = "oferta_resolucao_160.csv"
FORA_DAS_ANTIGAS = ("Nome_Vendedor",)
FORA_DA_160 = (
    "Identificacao_devedores_coobrigados",
    "Descricao_garantias",
    "Descricao_lastro",
    "Destinacao_recursos",  # texto livre: um trazia um número com cara de CPF (16/10/2026)
)
NUMERO = re.compile(r"^(Valor|Preco|Quantidade|Qtde?|Qdte?|QtD|Nr|Num)_", re.IGNORECASE)
TEXTOS_COM_NOME_DE_NUMERO = (
    "Valor_Mobiliario",
)  # o tipo do título na 160 ("Debêntures")
CNPJ = re.compile(r"^\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}$")
CPF = re.compile(r"\d{3}\.\d{3}\.\d{3}-\d{2}")
# a ordem é a da preferência: a primeira data que existe é o anúncio
ANUNCIO_DAS_ANTIGAS = (
    "data_registro_oferta",
    "data_dispensa_oferta",
    "data_comunicado",
)
FIM_DAS_ANTIGAS = ("data_encerramento_oferta", "data_comunicado")
ANUNCIO_DA_160 = ("data_registro",)
FIM_DA_160 = ("data_encerramento",)


def _ler_csv(conteudo_do_zip: bytes, nome: str, fora: tuple[str, ...]) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(conteudo_do_zip)) as arquivo:
        bruto = pd.read_csv(
            arquivo.open(nome), sep=";", encoding=CODIFICACAO, encoding_errors="replace",
            dtype=str, keep_default_na=False, usecols=lambda coluna: coluna not in fora,
        )  # fmt: skip
    return bruto


def _tipos(bruto: pd.DataFrame) -> pd.DataFrame:
    """Colunas em minúsculas; datas e números convertidos; o vazio vira vazio."""
    tabela = pd.DataFrame(index=bruto.index)
    for coluna in bruto.columns:
        valores = bruto[coluna].str.strip()
        nome = coluna.lower()
        if nome.startswith("data_"):
            tabela[nome] = pd.to_datetime(valores, errors="coerce")
        elif NUMERO.match(coluna) and coluna not in TEXTOS_COM_NOME_DE_NUMERO:
            tabela[nome] = pd.to_numeric(valores, errors="coerce").astype(float)
        else:  # rede de segurança: texto com um CPF no meio vira vazio
            com_cpf = valores.str.contains(CPF)
            tabela[nome] = valores.replace("", None).mask(com_cpf, None)
    return tabela


def _primeira(tabela: pd.DataFrame, colunas: tuple[str, ...]) -> pd.Series:
    datas = tabela[list(colunas)]
    return datas.bfill(axis=1).iloc[:, 0]


def _com_datas(
    tabela: pd.DataFrame, anuncio: tuple[str, ...], fim: tuple[str, ...]
) -> pd.DataFrame:
    anunciada = _primeira(tabela, anuncio)
    encerrada = _primeira(tabela, fim)
    # a maior das duas: na ICVM 476 o encerramento vem antes do comunicado, que é o anúncio
    disponivel = pd.concat([anunciada, encerrada], axis=1).max(axis=1)
    tabela = tabela.assign(anunciada_em=anunciada, disponivel_em=disponivel)
    com_cnpj = tabela["cnpj_emissor"].fillna("").str.match(CNPJ)
    validas = tabela[com_cnpj & tabela["anunciada_em"].notna()]
    return validas.drop_duplicates().reset_index(drop=True)


def ler_antigas(conteudo_do_zip: bytes) -> pd.DataFrame:
    """As ofertas até a Resolução 160 (ICVM 400, 476 e 555), com as datas "como era"."""
    tabela = _tipos(_ler_csv(conteudo_do_zip, ANTIGAS, FORA_DAS_ANTIGAS))
    sem_cnpj = ~tabela["cnpj_ofertante"].fillna("").str.match(CNPJ)
    # o ofertante sem CNPJ pode ser pessoa física: sem nome e sem o documento (às vezes um CPF)
    for coluna in ("cnpj_ofertante", "nome_ofertante"):
        tabela[coluna] = tabela[coluna].mask(sem_cnpj, None)
    return _com_datas(tabela, ANUNCIO_DAS_ANTIGAS, FIM_DAS_ANTIGAS)


def ler_resolucao_160(conteudo_do_zip: bytes) -> pd.DataFrame:
    """Os requerimentos de oferta pela Resolução 160 (2023 em diante), com as datas "como era"."""
    tabela = _tipos(_ler_csv(conteudo_do_zip, RESOLUCAO_160, FORA_DA_160))
    return _com_datas(tabela, ANUNCIO_DA_160, FIM_DA_160)
