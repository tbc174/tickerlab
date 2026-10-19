"""Levantamentos de safra de café da CONAB, como publicados (PR 7 do plano do café).

A CONAB faz quatro levantamentos por safra (jan/fev, mai, set e dez) e cada um traz a safra em curso e a
anterior. Cada planilha (`site_previsao-de-safra-cafe-*.xls`) tem abas por tipo: "1 Café Total",
"2 Café Arábica", "3 Café Conilon" (área em produção, produtividade e produção) e "4", "5" e "6 ... - Área"
(área em formação, em produção e total). Linhas: regiões, UFs (com sub-regiões de MG e BA recuadas),
"OUTROS (*)" e "BRASIL".

Regras (testes em `tests/test_base_conab_cafe.py`):
- **Nunca sobrescreve:** a linha é (safra, levantamento, tipo, uf, divulgado_em); um levantamento
  revisado depois fica ao lado do primeiro. Só a coluna da safra do levantamento entra: a coluna do ano
  anterior repete um número já guardado pelo levantamento daquele ano.
- **Como publicado:** os números ficam como na planilha (licença CC BY-ND 3.0: nada de recorte, soma ou
  gráfico sai daqui sem a resposta da CONAB; os derivados de `src/commodities/cafe` ficam sem tela).
- **Sem olhar o futuro:** `como_estava_em(tabela, dia)` só usa o que já tinha sido divulgado em `dia`.
- **A data é a da CONAB:** vem do "Publicado em" da página de cada levantamento (o arquivista guarda a página).
  Sem a página, ou com uma data fora de ordem na safra, a linha usa o dia da coleta e fica marcada em
  `divulgado_aproximado` (o dia da coleta nunca adianta o dado, mas pode atrasá-lo).
- **Arábica e conilon separados:** `tipo` em {arabica, conilon, total} em toda linha.
"""

import io
import re
import unicodedata
from datetime import date

import pandas as pd

FONTE = "conab-cafe-safra"
FONTE_DA_PAGINA = "conab-cafe-publicacao"
LEVANTAMENTOS = (1, 2, 3, 4)
COLUNAS = (
    "safra", "levantamento", "tipo", "uf", "area_formacao_ha", "area_producao_ha",
    "produtividade_sc_ha", "producao_mil_sacas", "divulgado_em", "divulgado_aproximado",
)  # fmt: skip
CHAVE = ("safra", "levantamento", "tipo", "uf", "divulgado_em")
TIPOS = {"total": "total", "arabica": "arabica", "conilon": "conilon"}
UFS = frozenset(
    [
        "RO",
        "AC",
        "AM",
        "RR",
        "PA",
        "AP",
        "TO",
        "MA",
        "PI",
        "CE",
        "RN",
        "PB",
        "PE",
        "AL",
        "SE",
        "BA",
        "MG",
        "ES",
        "RJ",
        "SP",
        "PR",
        "SC",
        "RS",
        "MS",
        "MT",
        "GO",
        "DF",
    ]
)
# o que cada bloco de três colunas da planilha mede (título normalizado → coluna da tabela)
BLOCOS_DE_PRODUCAO = {
    "AREA EM PRODUCAO": "area_producao_ha",
    "PRODUTIVIDADE": "produtividade_sc_ha",
    "PRODUCAO": "producao_mil_sacas",
}
BLOCOS_DE_AREA = {"AREA EM FORMACAO": "area_formacao_ha"}
ABA = re.compile(r"^(\d+)\s+cafe\s+(total|arabica|conilon)(\s+-\s+area)?\s*$")
SAFRA_NO_ENDERECO = re.compile(r"/(\d)o-levantamento-de-cafe-safra-(\d{4})/")
PAGINA_DOS_LEVANTAMENTOS = "https://www.gov.br/conab/pt-br/atuacao/informacoes-agropecuarias/safras/safra-de-cafe"
PUBLICADO_EM = re.compile(
    rb'documentPublished.*?class="value">\s*(\d{2})/(\d{2})/(\d{4})', re.DOTALL
)
LINHAS_DE_CABECALHO = 3  # títulos, safras e letras (a), (b)...


class ErroDeLeitura(ValueError):
    """A planilha não tem o desenho que a CONAB vinha publicando."""


def _simples(texto: object) -> str:
    sem_acento = (
        unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    )
    return " ".join(sem_acento.lower().split())


def identificar(url: str) -> tuple[int, int] | None:
    """(levantamento, safra) pelo endereço da planilha; None se o endereço não diz."""
    achado = SAFRA_NO_ENDERECO.search(url)
    return (int(achado.group(1)), int(achado.group(2))) if achado else None


def pagina_do_levantamento(levantamento: int, safra: int) -> str:
    """Endereço da página do levantamento, onde a CONAB escreve o "Publicado em"."""
    nome = f"{levantamento}o-levantamento-de-cafe-safra-{safra}"
    return f"{PAGINA_DOS_LEVANTAMENTOS}/{nome}/{nome}"


def data_de_publicacao(pagina: bytes) -> date | None:
    """O dia do "Publicado em" da página de um levantamento; None se a página não o traz."""
    achado = PUBLICADO_EM.search(pagina)
    if achado is None:
        return None
    try:
        return date(int(achado.group(3)), int(achado.group(2)), int(achado.group(1)))
    except ValueError:
        return None


def datas_em_ordem(
    datas: dict[tuple[int, int], date | None],
) -> dict[tuple[int, int], date | None]:
    """Tira a data que contraria os outros levantamentos da mesma safra (virou None).

    Dentro de uma safra o levantamento 2 não sai antes do 1. Uma página reeditada pode trazer outra data
    (a CONAB mostra o 1º de 2024 publicado depois do 3º): fica a maior sequência em ordem, o resto vira
    None, e a linha usa o dia da coleta marcado como aproximado.
    """
    boas: dict[tuple[int, int], date | None] = {}
    for safra in {s for s, _ in datas}:
        itens = sorted((lev, d) for (s, lev), d in datas.items() if s == safra and d)
        melhor: list[tuple[int, date]] = []
        cadeias: list[list[tuple[int, date]]] = []
        for i, item in enumerate(itens):
            anteriores = [c for c in cadeias[:i] if c[-1][1] <= item[1]]
            cadeias.append(max(anteriores, key=len, default=[]) + [item])
            melhor = max(melhor, cadeias[-1], key=len)
        certas = {lev for lev, _ in melhor}
        for (s, lev), d in datas.items():
            if s == safra:
                boas[(s, lev)] = d if lev in certas else None
    return boas


def _uf_da_linha(rotulo: object) -> str | None:
    texto = str(rotulo).strip()
    if texto in UFS or texto == "BRASIL":
        return texto
    return "OUTROS" if texto.startswith("OUTROS") else None


def _linha_do_cabecalho(aba: pd.DataFrame) -> int:
    for i in range(len(aba)):
        if _simples(aba.iat[i, 0]).startswith("regi"):
            return i
    raise ErroDeLeitura("aba sem a linha de cabeçalho 'REGIÃO/UF'")


def _safra_da_aba(aba: pd.DataFrame, cabecalho: int) -> int:
    anos = [
        int(m.group(1))
        for v in aba.iloc[cabecalho + 1]
        if (m := re.fullmatch(r"\s*Safra\s+(\d{4})\s*", str(v)))
    ]
    if not anos:
        raise ErroDeLeitura("aba sem colunas 'Safra AAAA'")
    return max(anos)


def _colunas_da_safra(aba: pd.DataFrame, cabecalho: int, safra: int) -> dict[str, int]:
    """Título normalizado de cada bloco → índice da coluna da safra do levantamento."""
    achadas: dict[str, int] = {}
    titulos = aba.iloc[cabecalho]
    anos = aba.iloc[cabecalho + 1]
    for c in range(1, aba.shape[1]):
        titulo = _simples(titulos.iat[c]).upper().split(" (")[0]
        if not titulo or titulo == "NAN":
            continue
        for k in range(c, min(c + 3, aba.shape[1])):
            if re.fullmatch(rf"\s*Safra\s+{safra}\s*", str(anos.iat[k])):
                achadas[titulo] = k
                break
    return achadas


def _ler_aba(aba: pd.DataFrame, blocos: dict[str, str]) -> tuple[int, pd.DataFrame]:
    cabecalho = _linha_do_cabecalho(aba)
    safra = _safra_da_aba(aba, cabecalho)
    colunas = _colunas_da_safra(aba, cabecalho, safra)
    faltam = [t for t in blocos if t not in colunas]
    if faltam:
        raise ErroDeLeitura(f"aba sem o bloco {faltam[0]!r}")
    linhas = []
    for i in range(cabecalho + LINHAS_DE_CABECALHO, len(aba)):
        if (uf := _uf_da_linha(aba.iat[i, 0])) is None:
            continue
        linha = {"uf": uf}
        for titulo, coluna in blocos.items():
            linha[coluna] = pd.to_numeric(aba.iat[i, colunas[titulo]], errors="coerce")
        linhas.append(linha)
    return safra, pd.DataFrame(linhas)


def _abas_por_tipo(
    livro: dict[str, pd.DataFrame],
) -> dict[tuple[str, bool], pd.DataFrame]:
    abas = {}
    for nome, aba in livro.items():
        if achado := ABA.match(_simples(nome)):
            abas[(achado.group(2), achado.group(3) is not None)] = aba
    return abas


def ler_levantamento(
    conteudo: bytes,
    levantamento: int,
    divulgado_em: date,
    aproximada: bool = False,
) -> pd.DataFrame:
    """Um levantamento (.xls ou .xlsx) como tabela de `COLUNAS`: uma linha por tipo e UF da safra em curso.

    `aproximada`: `divulgado_em` é o dia da coleta, porque a data da CONAB não foi achada.
    """
    if levantamento not in LEVANTAMENTOS:
        raise ValueError(f"levantamento deve ser 1 a 4, veio {levantamento}")
    try:
        livro = pd.read_excel(io.BytesIO(conteudo), sheet_name=None, header=None)
    except Exception as erro:
        raise ErroDeLeitura(f"planilha da CONAB ilegível: {erro}") from erro
    abas = _abas_por_tipo(livro)
    partes = []
    for tipo in TIPOS:
        if (tipo, False) not in abas or (tipo, True) not in abas:
            raise ErroDeLeitura(f"faltam as abas de {tipo} (produção e área)")
        safra, producao = _ler_aba(abas[(tipo, False)], BLOCOS_DE_PRODUCAO)
        safra_da_area, area = _ler_aba(abas[(tipo, True)], BLOCOS_DE_AREA)
        if safra != safra_da_area:
            raise ErroDeLeitura(
                f"safras diferentes nas abas de {tipo}: {safra} e {safra_da_area}"
            )
        parte = producao.merge(area, on="uf", how="left")
        parte.insert(0, "tipo", tipo)
        parte.insert(0, "safra", safra)
        partes.append(parte)
    tabela = pd.concat(partes, ignore_index=True)
    tabela["levantamento"] = levantamento
    tabela["divulgado_em"] = pd.Timestamp(divulgado_em)
    tabela["divulgado_aproximado"] = aproximada
    return tabela.reindex(columns=list(COLUNAS))


def acrescentar(guardada: pd.DataFrame, nova: pd.DataFrame) -> pd.DataFrame:
    """Junta um levantamento ao que já está guardado, sem apagar nada: só a mesma linha, da mesma data, não repete."""
    juntas = pd.concat(
        [guardada.astype(nova.dtypes.to_dict()) if len(guardada) else guardada, nova]
    )
    return juntas.drop_duplicates(list(CHAVE), keep="first").reset_index(drop=True)


def como_estava_em(tabela: pd.DataFrame, dia: date) -> pd.DataFrame:
    """Para cada (safra, tipo, uf), o levantamento mais novo já divulgado até `dia` (inclusive)."""
    publicadas = tabela[tabela["divulgado_em"] <= pd.Timestamp(dia)]
    ordem = publicadas.sort_values(["divulgado_em", "levantamento"])
    ultimas = ordem.drop_duplicates(["safra", "tipo", "uf"], keep="last")
    return ultimas.sort_values(["safra", "tipo", "uf"]).reset_index(drop=True)
