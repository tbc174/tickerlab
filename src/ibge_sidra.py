"""Séries do IBGE pela API do SIDRA (dados abertos do IBGE; citar o IBGE como fonte).

Aqui só se **monta o pedido e lê a resposta**; guardar com a safra (cada versão fica, nunca se
sobrescreve) é o acervo de séries (`src/banco/series.py`, ADR 0024) e o coletor
`scripts/atualizar_series_ibge.py`. Sem Streamlit: entradas e saídas em tipos simples.

Tabelas da primeira leva (número do SIDRA entre parênteses):

- **LSPA** (6588): safra estimada por produto e UF, **revista todo mês**; café arábica e canephora
  (no id: `arabica`, `conilon`, e `total` somado aqui, porque o SIDRA deixa o total em branco);
- **PAM** (1613): lavouras permanentes por **município**, anual; café arábica, canephora e total;
- **PMC** (8880 restrito, 8881 ampliado): volume e receita do varejo, Brasil e UF;
- **PIM-PF** (8888 seções e atividades, 8887 grandes categorias econômicas), Brasil;
- **IPCA por grupo e item** (7060): café, alimentação, combustíveis, energia.

Símbolos do SIDRA: "-" é zero de verdade; "X" (sigilo), ".." (não se aplica) e "..." (não
disponível) **não são número**: viram `None` e nunca entram como zero. Símbolo que não conhecemos
para a leitura, em vez de chutar.

Sem olhar o futuro: `cortar_futuro` tira o que ainda não aconteceu em `hoje`.
"""

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date
from urllib.parse import quote

from src.banco.series import SerieDoAcervo

URL_DO_SIDRA = "https://apisidra.ibge.gov.br/values"
UFS = (
    11, 12, 13, 14, 15, 16, 17, 21, 22, 23, 24, 25, 26, 27, 28, 29,
    31, 32, 33, 35, 41, 42, 43, 50, 51, 52, 53,
)  # fmt: skip
SEM_NUMERO = {"X", "..", "...", ""}  # sigilo, não se aplica, não disponível
ZERO_ABSOLUTO = "-"
TAMANHO_DO_MES = 6  # AAAAMM
TAMANHO_DO_ANO = 4  # AAAA
VALORES_POR_PEDIDO_NO_SIDRA = (
    50_000  # acima disso o SIDRA responde 400 (visto em 19/10/2026)
)
MUNICIPIOS_DE_MG = 853  # a maior UF cafeeira: ela decide o tamanho do pedido
ANOS_POR_PEDIDO_MUNICIPAL = (
    4  # 853 municípios x 4 variáveis x 3 classes x 4 anos = 40.944 valores
)

# café: as categorias de cada tabela → o tipo que vai no id (canephora é o conilon dos produtores)
CAFE_ARABICA, CAFE_CONILON, CAFE_TOTAL = "arabica", "conilon", "total"
LSPA_CAFE_ARABICA, LSPA_CAFE_CANEPHORA, LSPA_CAFE_TOTAL = 39454, 39455, 40527
PAM_CAFE_ARABICA, PAM_CAFE_CANEPHORA, PAM_CAFE_TOTAL = 31619, 31620, 2723
TIPOS_DE_CAFE = {
    6588: {
        LSPA_CAFE_ARABICA: CAFE_ARABICA,
        LSPA_CAFE_CANEPHORA: CAFE_CONILON,
        LSPA_CAFE_TOTAL: CAFE_TOTAL,
    },
    1613: {
        PAM_CAFE_ARABICA: CAFE_ARABICA,
        PAM_CAFE_CANEPHORA: CAFE_CONILON,
        PAM_CAFE_TOTAL: CAFE_TOTAL,
    },
}
# na LSPA a produção, a área plantada e a área colhida somam; o rendimento não
LSPA_VARIAVEIS_QUE_SOMAM = {35, 109, 216}


class RespostaInesperada(ValueError):
    """O SIDRA devolveu algo que não é uma tabela de valores (erro com status 200, símbolo novo)."""


@dataclass(frozen=True)
class Valor:
    """Uma célula da resposta do SIDRA: onde, qual variável, que período, que categorias."""

    nivel: str  # "1" Brasil, "3" UF, "6" município
    local: str  # código do Brasil, da UF ou do município
    variavel: int
    periodo: str  # AAAAMM ou AAAA
    categorias: tuple[int, ...]
    valor: float | None
    unidade: str
    nome_do_local: str = field(default="", compare=False)
    nome_da_variavel: str = field(default="", compare=False)
    nome_da_categoria: str = field(default="", compare=False)

    @property
    def referencia(self) -> date:
        return data_de_referencia(self.periodo)


def montar_url(
    tabela: int,
    variaveis: Sequence[int],
    classificacoes: Mapping[int, Sequence[int]],
    periodo: str,
    territorio: str = "n1/all",
) -> str:
    """O pedido ao SIDRA: `/t/<tabela>/<território>/v/<variáveis>/p/<período>/c<classif>/<cats>`.

    `territorio` já vem no formato do SIDRA ("n1/all", "n3/all", "n6/in n3 31")."""
    partes = [
        f"t/{tabela}",
        quote(territorio, safe="/"),
        f"v/{','.join(str(v) for v in variaveis)}",
        f"p/{quote(periodo, safe='-,')}",
    ]
    for classificacao, categorias in classificacoes.items():
        partes.append(f"c{classificacao}/{','.join(str(c) for c in categorias)}")
    return f"{URL_DO_SIDRA}/{'/'.join(partes)}"


def data_de_referencia(periodo: str) -> date:
    """AAAAMM → 1º dia do mês (como as séries mensais do BC); AAAA → 31/12 (como o Focus anual)."""
    if len(periodo) == TAMANHO_DO_MES and periodo.isdigit():
        return date(int(periodo[:4]), int(periodo[4:]), 1)
    if len(periodo) == TAMANHO_DO_ANO and periodo.isdigit():
        return date(int(periodo), 12, 31)
    raise RespostaInesperada(f"Período que não conheço: {periodo!r}")


def _numero(texto: str) -> float | None:
    texto = texto.strip()
    if texto == ZERO_ABSOLUTO:
        return 0.0
    if texto in SEM_NUMERO:
        return None
    try:
        return float(texto)
    except ValueError:
        raise RespostaInesperada(f"Valor que não conheço: {texto!r}") from None


def _colunas_de_categoria(linha: Mapping[str, str]) -> list[int]:
    """As dimensões depois da 3ª (território, variável, período) são as classificações."""
    posicoes = sorted(
        int(chave[1:-1]) for chave in linha if chave[0] == "D" and chave.endswith("C")
    )
    return [p for p in posicoes if p > 3]


def ler_resposta(linhas: Sequence[Mapping[str, str]]) -> list[Valor]:
    """A resposta JSON do SIDRA (a 1ª linha é o cabeçalho) em valores."""
    if not isinstance(linhas, list):
        raise RespostaInesperada(
            f"O SIDRA não devolveu uma tabela: {str(linhas)[:200]}"
        )
    valores = []
    for linha in linhas[1:]:
        categorias = _colunas_de_categoria(linha)
        valores.append(
            Valor(
                nivel=linha["NC"],
                local=linha["D1C"],
                variavel=int(linha["D2C"]),
                periodo=linha["D3C"],
                categorias=tuple(int(linha[f"D{p}C"]) for p in categorias),
                valor=_numero(linha["V"]),
                unidade=linha["MN"],
                nome_do_local=linha["D1N"],
                nome_da_variavel=linha["D2N"],
                nome_da_categoria=" ".join(linha[f"D{p}N"] for p in categorias),
            )
        )
    return valores


def rotulo_da_categoria(tabela: int, categoria: int) -> str:
    """O tipo do café (`arabica`, `conilon`, `total`) nas tabelas dele; nas outras, o código."""
    return TIPOS_DE_CAFE.get(tabela, {}).get(categoria, str(categoria))


def _rotulo_do_local(valor: Valor) -> str:
    prefixo = {"1": "br", "3": "uf", "6": "mun"}[valor.nivel]
    return prefixo if valor.nivel == "1" else f"{prefixo}{valor.local}"


def codigo_da_serie(tabela: int, valor: Valor) -> str:
    """`ibge-sidra-<tabela>-<variável>-<categoria ou tipo do café>-<local>`; o prefixo `ibge`
    dá a licença (src/banco/coletas.py)."""
    categoria = (
        "-".join(rotulo_da_categoria(tabela, c) for c in valor.categorias) or "0"
    )
    return f"ibge-sidra-{tabela}-{valor.variavel}-{categoria}-{_rotulo_do_local(valor)}"


def serie_do_acervo(tabela: int, valor: Valor, frequencia: str) -> SerieDoAcervo:
    partes = [valor.nome_da_variavel, valor.nome_da_categoria, valor.nome_do_local]
    return SerieDoAcervo(
        codigo_da_serie(tabela, valor),
        " · ".join(p for p in partes if p) + " (IBGE/SIDRA)",
        valor.unidade,
        frequencia,
    )


def somar_total_do_cafe(valores: Sequence[Valor]) -> list[Valor]:
    """Acrescenta o café total da LSPA (arábica + canephora) onde a soma faz sentido.

    O SIDRA deixa o "Café total" em branco. Só soma produção e áreas; se um dos tipos está em
    sigilo ou ausente, o total também fica sem número (não vale um total só de um tipo)."""
    por_ponto: dict[tuple, dict[int, Valor]] = defaultdict(dict)
    for v in valores:
        tipo = v.categorias[0] if v.categorias else None
        if v.variavel in LSPA_VARIAVEIS_QUE_SOMAM and tipo in (
            LSPA_CAFE_ARABICA,
            LSPA_CAFE_CANEPHORA,
        ):
            por_ponto[(v.nivel, v.local, v.variavel, v.periodo)][tipo] = v
    totais = []
    for tipos in por_ponto.values():
        arabica, canephora = (
            tipos.get(LSPA_CAFE_ARABICA),
            tipos.get(LSPA_CAFE_CANEPHORA),
        )
        base = arabica or canephora
        assert base is not None
        soma = (
            arabica.valor + canephora.valor
            if arabica
            and canephora
            and arabica.valor is not None
            and canephora.valor is not None
            else None
        )
        totais.append(
            replace(
                base,
                categorias=(LSPA_CAFE_TOTAL,),
                valor=soma,
                nome_da_categoria="Café total (arábica + canephora)",
            )
        )
    return [*valores, *totais]


def cortar_futuro(valores: Sequence[Valor], hoje: date) -> list[Valor]:
    """Sem olhar o futuro: fica só o que tem data de referência até `hoje`."""
    return [v for v in valores if v.referencia <= hoje]


def descartar_series_vazias(valores: Sequence[Valor]) -> list[Valor]:
    """Tira as séries em que nenhum período tem número diferente de zero (no PAM por município,
    quase todos os 5.570 não têm café: guardar só zeros inflaria o acervo sem informar nada)."""
    com_numero = {
        (v.nivel, v.local, v.variavel, v.categorias) for v in valores if v.valor
    }
    return [
        v for v in valores if (v.nivel, v.local, v.variavel, v.categorias) in com_numero
    ]


@dataclass(frozen=True)
class Coleta:
    """Uma tabela do SIDRA que o coletor busca, com o que pedir e como guardar."""

    nome: str
    tabela: int
    variaveis: tuple[int, ...]
    classificacoes: Mapping[int, tuple[int, ...]]
    territorios: tuple[str, ...]
    frequencia: str  # "mensal" ou "anual"
    soma_o_total_do_cafe: bool = False
    descarta_series_vazias: bool = False

    def urls(self, periodo: str) -> list[str]:
        """Um pedido por território; o PAM municipal ainda divide o período em blocos."""
        periodos = self._blocos(periodo) if self.descarta_series_vazias else [periodo]
        return [
            montar_url(self.tabela, self.variaveis, self.classificacoes, p, t)
            for t in self.territorios
            for p in periodos
        ]

    def _blocos(self, periodo: str) -> list[str]:
        if "-" not in periodo:
            return [periodo]
        primeiro, ultimo = (int(p) for p in periodo.split("-"))
        return [
            f"{inicio}-{min(inicio + ANOS_POR_PEDIDO_MUNICIPAL - 1, ultimo)}"
            for inicio in range(primeiro, ultimo + 1, ANOS_POR_PEDIDO_MUNICIPAL)
        ]


def _municipios_da_uf(uf: int) -> str:
    return f"n6/in n3 {uf}"


PMC_VARIAVEIS = (
    7169,
    7170,
    11708,
    11709,
    11710,
    11711,
)  # índice, com ajuste, variações
PMC_TIPOS = {11046: (56733, 56734)}  # receita nominal e volume
PIMPF_VARIAVEIS = (12606, 12607, 11601, 11602, 11603, 11604)
# Indústria geral, extrativas, transformação e as atividades da transformação (ids do SIDRA)
PIMPF_ATIVIDADES = (
    129314, 129315, 129316, 129317, 129318, 129319, 129320, 129321, 129322, 129323, 129324,
    129325, 129326, 56689, 129330, 129331, 129332, 129333, 129334, 129335, 129336, 129337,
    129338, 129339, 129340, 129341, 129342,
)  # fmt: skip
IPCA_ITENS = (
    7169,  # índice geral
    7170, 7171, 7392, 7393,  # alimentação e bebidas, no domicílio, café moído e solúvel
    7432,  # alimentação fora do domicílio
    7479, 7480, 7484,  # combustíveis e energia, combustíveis domésticos, energia residencial
    7656, 7657, 7658, 7659,  # combustíveis de veículos: gasolina, etanol, diesel
)  # fmt: skip
# bens de capital, intermediários, de consumo (duráveis e semi e não duráveis)
CATEGORIAS_ECONOMICAS = {543: (129278, 129283, 129300, 129301, 129305)}

COLETAS = (
    Coleta(
        "lspa", 6588, (35, 36, 109, 216), {48: (LSPA_CAFE_ARABICA, LSPA_CAFE_CANEPHORA)},
        ("n1/all", "n3/all"), "mensal", soma_o_total_do_cafe=True,
    ),
    Coleta(
        "pam-municipal", 1613, (216, 214, 112, 2313),
        {82: (PAM_CAFE_ARABICA, PAM_CAFE_CANEPHORA, PAM_CAFE_TOTAL)},
        tuple(_municipios_da_uf(uf) for uf in UFS), "anual", descarta_series_vazias=True,
    ),
    Coleta("pmc-restrito", 8880, PMC_VARIAVEIS, PMC_TIPOS, ("n1/all", "n3/all"), "mensal"),
    Coleta("pmc-ampliado", 8881, PMC_VARIAVEIS, PMC_TIPOS, ("n1/all", "n3/all"), "mensal"),
    Coleta("pimpf-atividades", 8888, PIMPF_VARIAVEIS, {544: PIMPF_ATIVIDADES}, ("n1/all",), "mensal"),
    Coleta("pimpf-categorias", 8887, PIMPF_VARIAVEIS, CATEGORIAS_ECONOMICAS, ("n1/all",), "mensal"),
    Coleta("ipca-itens", 7060, (63, 69, 2265, 66), {315: IPCA_ITENS}, ("n1/all",), "mensal"),
)  # fmt: skip
COLETAS_POR_NOME = {c.nome: c for c in COLETAS}
