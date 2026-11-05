"""SINISA do Ministério das Cidades (S01 da rodada de fontes de 03/11/2026): indicadores do módulo de
água por município e prestador, no formato longo (uma linha por prestador e indicador).

- **Fonte:** `https://www.gov.br/cidades/pt-br/acesso-a-informacao/acoes-e-programas/saneamento/sinisa/resultados-sinisa/resultados-sinisa-2025`,
  um ZIP por módulo (`SINISA_Resultados_Ref2024.zip` é o de água, 19.078.026 bytes, baixado em 04/11/2026
  e lido planilha a planilha; esgoto, resíduos e águas pluviais têm ZIP próprio, ainda não lidos aqui).
- **Planilhas de indicadores** (`SINISA_AGUA_Indicadores_Base Municipal_...xlsx` e `..._Locais e Regionais_...xlsx`,
  lidas em 04/11/2026, ano de referência 2024): a primeira aba tem um preâmbulo de 8 linhas (ministério,
  sistema, módulo, "Ano de referência AAAA", "Data de publicação: DD/MM/AAAA", "Data de retificação:
  DD/MM/AAAA"), uma linha de grupos, uma de descrições, uma de unidades e a de siglas (`cod_IBGE`,
  `CAD0002`... `IAG0001`... `IFA2016`), depois os dados. Os campos `cod_IBGE`, `Macrorregião`, `Município` e
  `UF` identificam o município e `CAD0002`, `CAD0003`, `CAD0005` e `CAD0006` o prestador (natureza jurídica,
  abrangência, nome e sigla). Na planilha "Base Municipal" os valores vêm como número; na de "Locais e
  Regionais", como texto com vírgula decimal. Onde o indicador não pôde ser calculado o texto é
  `Não calculado (motivo)`: vira vazio, com o motivo numa coluna.
- **Chave:** código IBGE do município + prestador + indicador.

**Sem olhar o futuro:** `disponivel_em` é a data de retificação da planilha, se houver, senão a de publicação.
A planilha de hoje já é a retificada (25/05/2026) e traz valores diferentes da publicada em 18/12/2025: o
valor de antes da retificação não está aqui, e quem quiser o histórico guarda cada baixada (o arquivista).

**Licença:** Creative Commons Atribuição-SemDerivações 3.0 (CC BY-ND 3.0), no rodapé da página, que não
permite obra derivada. O Tiago aceitou o risco e decidiu transformar mesmo assim, com atribuição em toda
saída (ADR 0121, item 5, 03/11/2026; risco registrado em `licencas-por-fonte.md` para a lista de perguntas
ao advogado). Por isso o texto de `ATRIBUICAO` vai em cada linha e o valor nunca é alterado: só se muda o
formato (de planilha larga para tabela longa), sem arredondar nem recalcular indicador.

Sem Streamlit; pandas e openpyxl.
"""

import io
import re
from datetime import date

import pandas as pd
from openpyxl import load_workbook

FONTE = "mcid-sinisa"
ATRIBUICAO = (
    "Fonte: Ministério das Cidades, Sistema Nacional de Informações em Saneamento Básico (SINISA), "
    "https://www.gov.br/cidades/pt-br/acesso-a-informacao/acoes-e-programas/saneamento/sinisa. "
    "Licença CC BY-ND 3.0; o TickerLab reorganizou a planilha em tabela, sem alterar os valores."
)
AVISO = (
    "O SINISA é anual e declarado pelos prestadores: o dado de 2024 saiu em dezembro de 2025 e foi retificado "
    "em maio de 2026. Um município pode ter mais de um prestador."
)
CHAVE = ["cod_ibge", "prestador", "indicador"]

_CAMPOS_DO_MUNICIPIO = {
    "cod_IBGE": "cod_ibge",
    "Macrorregião": "macrorregiao",
    "Município": "municipio",
    "UF": "uf",
}
_CAMPOS_DO_PRESTADOR = {
    "CAD0002": "natureza_juridica",
    "CAD0003": "abrangencia",
    "CAD0005": "prestador",
    "CAD0006": "sigla_prestador",
}
_SIGLA_DE_INDICADOR = re.compile(r"^I[A-Z]{2}\d{4}$")
_ANO = re.compile(r"Ano de refer[êe]ncia\s+(\d{4})", re.IGNORECASE)
_PUBLICACAO = re.compile(
    r"Data de publica[çc][ãa]o:\s*(\d{2})/(\d{2})/(\d{4})", re.IGNORECASE
)
_RETIFICACAO = re.compile(
    r"Data de retifica[çc][ãa]o:\s*(\d{2})/(\d{2})/(\d{4})", re.IGNORECASE
)
_NAO_CALCULADO = re.compile(r"^N[ãa]o calculado\s*\((.*)\)\s*$", re.IGNORECASE)
_LINHAS_DO_PREAMBULO = 10
_LINHAS_PARA_ACHAR_AS_SIGLAS = 30


def _data(padrao: re.Pattern[str], texto: str) -> date | None:
    achado = padrao.search(texto)
    return date(int(achado[3]), int(achado[2]), int(achado[1])) if achado else None


def _preambulo(linhas: list[tuple]) -> tuple[int, date, date | None]:
    """Ano de referência, publicação e (se houver) retificação, lidos do texto do preâmbulo."""
    texto = "\n".join(
        str(c) for linha in linhas[:_LINHAS_DO_PREAMBULO] for c in linha if c
    )
    ano = _ANO.search(texto)
    publicacao = _data(_PUBLICACAO, texto)
    if ano is None or publicacao is None:
        raise ValueError(
            "SINISA: o preâmbulo não traz o ano de referência e a data de publicação"
        )
    return int(ano[1]), publicacao, _data(_RETIFICACAO, texto)


def _indice_das_siglas(linhas: list[tuple]) -> int:
    for indice, linha in enumerate(linhas[:_LINHAS_PARA_ACHAR_AS_SIGLAS]):
        if linha and linha[0] == "cod_IBGE":
            return indice
    raise ValueError("SINISA: não achei a linha de siglas (cod_IBGE)")


def disponivel_em(
    publicado_em: date, retificado_em: date | None = None
) -> pd.Timestamp:
    """A retificação manda, quando existe: a planilha de hoje é a retificada, não a publicada antes."""
    return pd.Timestamp(retificado_em or publicado_em)


def valor_e_motivo(celula: object) -> tuple[float | None, str | None]:
    """`60,35` ou `60.35` viram 60.35; `Não calculado (divisão por zero)` vira (None, `divisão por zero`)."""
    if celula is None or celula == "":
        return None, None
    if isinstance(celula, (int, float)):
        return float(celula), None
    texto = str(celula).strip()
    nao_calculado = _NAO_CALCULADO.match(texto)
    if nao_calculado:
        return None, nao_calculado[1].strip()
    try:
        return float(
            texto.replace(".", "").replace(",", ".") if "," in texto else texto
        ), None
    except ValueError as erro:
        raise ValueError(
            f"SINISA: valor que não é número nem 'Não calculado': {texto!r}"
        ) from erro


def _linhas_da_primeira_aba(conteudo_xlsx: bytes) -> list[tuple]:
    pasta = load_workbook(io.BytesIO(conteudo_xlsx), read_only=True, data_only=True)
    return list(pasta.worksheets[0].iter_rows(values_only=True))


def _prestadores(corpo: list[tuple], siglas: list) -> pd.DataFrame:
    posicao = {sigla: i for i, sigla in enumerate(siglas) if sigla}
    campos = {**_CAMPOS_DO_MUNICIPIO, **_CAMPOS_DO_PRESTADOR}
    faltando = [c for c in campos if c not in posicao]
    if faltando:
        raise ValueError(f"SINISA: colunas de identificação ausentes: {faltando}")
    dados = [
        {nome: linha[posicao[sigla]] for sigla, nome in campos.items()}
        for linha in corpo
    ]
    tabela = pd.DataFrame(dados, columns=list(campos.values()))
    tabela["cod_ibge"] = tabela["cod_ibge"].astype(str).str.strip().str.zfill(7)
    for coluna in ("prestador", "sigla_prestador", "municipio", "uf"):
        tabela[coluna] = tabela[coluna].astype("string").str.strip()
    return tabela


def ler_indicadores(conteudo_xlsx: bytes) -> pd.DataFrame:
    """A planilha de indicadores numa tabela longa: uma linha por município, prestador e indicador.

    Levanta ValueError para preâmbulo ou cabeçalho fora do formato, valor que não é número e prestador
    repetido no mesmo município."""
    linhas = _linhas_da_primeira_aba(conteudo_xlsx)
    ano, publicado_em, retificado_em = _preambulo(linhas)
    indice = _indice_das_siglas(linhas)
    siglas, unidades, descricoes = (
        linhas[indice],
        linhas[indice - 1],
        linhas[indice - 2],
    )
    corpo = [linha for linha in linhas[indice + 1 :] if linha and linha[0] is not None]
    quem = _prestadores(corpo, list(siglas))
    if quem.duplicated(["cod_ibge", "prestador"]).any():
        raise ValueError("SINISA: prestador repetido no mesmo município")
    colunas = [
        i
        for i, sigla in enumerate(siglas)
        if isinstance(sigla, str) and _SIGLA_DE_INDICADOR.match(sigla)
    ]
    if not colunas:
        raise ValueError("SINISA: nenhuma coluna de indicador (siglas IAG0001...)")
    pedacos = []
    for posicao in colunas:
        valores = [valor_e_motivo(linha[posicao]) for linha in corpo]
        pedaco = quem.copy()
        pedaco["indicador"] = siglas[posicao]
        pedaco["descricao"] = descricoes[posicao]
        pedaco["unidade"] = unidades[posicao]
        pedaco["valor"] = pd.array([v for v, _ in valores], dtype="Float64")
        pedaco["motivo_nao_calculado"] = pd.array(
            [m for _, m in valores], dtype="string"
        )
        pedacos.append(pedaco)
    longa = pd.concat(pedacos, ignore_index=True)
    longa["ano_referencia"] = ano
    longa["publicado_em"] = pd.Timestamp(publicado_em)
    longa["retificado_em"] = pd.Timestamp(retificado_em) if retificado_em else pd.NaT
    longa["disponivel_em"] = disponivel_em(publicado_em, retificado_em)
    longa["fonte"] = FONTE
    longa["atribuicao"] = ATRIBUICAO
    return longa.sort_values(CHAVE, ignore_index=True)


def por_municipio(tabela: pd.DataFrame, indicador: str) -> pd.DataFrame:
    """Os valores de um indicador (por exemplo `IAG0001`) com uma linha por município e prestador."""
    recorte = tabela[tabela["indicador"] == indicador]
    colunas = [
        "cod_ibge",
        "municipio",
        "uf",
        "prestador",
        "sigla_prestador",
        "valor",
        "unidade",
        "ano_referencia",
    ]
    return recorte[colunas].reset_index(drop=True)
