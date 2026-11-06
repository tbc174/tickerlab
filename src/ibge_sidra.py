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

from calendar import monthrange
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
MESES_DO_TRIMESTRE = 3
TRIMESTRES_POR_ANO = 4
NOME_MAXIMO_DA_SERIE = 120  # a coluna `series.nome`
VALORES_POR_PEDIDO_NO_SIDRA = (
    50_000  # acima disso o SIDRA responde 400 (visto em 19/10/2026)
)
MUNICIPIOS_DE_MG = 853  # a maior UF cafeeira: ela decide o tamanho do pedido
# quantas células cada território põe em um período do pedido (município: o pior caso, MG)
CELULAS_POR_TERRITORIO = {"n1": 1, "n3": len(UFS), "n6": MUNICIPIOS_DE_MG}

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
    frequencia: str = field(
        default="mensal", compare=False
    )  # lê o período: AAAAMM ou AAAATT

    @property
    def referencia(self) -> date:
        return data_de_referencia(self.periodo, self.frequencia)


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


def data_de_referencia(periodo: str, frequencia: str = "mensal") -> date:
    """AAAAMM → 1º dia do mês (como as séries mensais do BC); AAAA → 31/12 (como o Focus anual).

    Nas tabelas **trimestrais** os 6 dígitos são AAAATT (`202602` = 2º trimestre de 2026) e vão
    para o último dia do trimestre, como o anual vai para 31/12: pela leitura mensal, `202602`
    viraria fevereiro. A PNAD (trimestre móvel) devolve AAAAMM do mês em que o trimestre termina
    e segue como mensal."""
    if frequencia == "trimestral":
        return _fim_do_trimestre(periodo)
    if len(periodo) == TAMANHO_DO_MES and periodo.isdigit():
        return date(int(periodo[:4]), int(periodo[4:]), 1)
    if len(periodo) == TAMANHO_DO_ANO and periodo.isdigit():
        return date(int(periodo), 12, 31)
    raise RespostaInesperada(f"Período que não conheço: {periodo!r}")


def _fim_do_trimestre(periodo: str) -> date:
    if len(periodo) == TAMANHO_DO_MES and periodo.isdigit():
        ano, trimestre = int(periodo[:4]), int(periodo[4:])
        if 1 <= trimestre <= TRIMESTRES_POR_ANO:
            mes = trimestre * MESES_DO_TRIMESTRE
            return date(ano, mes, monthrange(ano, mes)[1])
    raise RespostaInesperada(f"Trimestre que não conheço: {periodo!r}")


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


def ler_resposta(
    linhas: Sequence[Mapping[str, str]], frequencia: str = "mensal"
) -> list[Valor]:
    """A resposta JSON do SIDRA (a 1ª linha é o cabeçalho) em valores; `frequencia` diz como ler
    o período de 6 dígitos (mês ou trimestre)."""
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
                frequencia=frequencia,
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


SEPARADOR_DO_NOME = " · "


def _encurtar(partes: list[str], orcamento: int) -> list[str]:
    """Corta, de um caractere por vez, a mais longa das partes (com "…") até caberem no orçamento."""
    cortes = [0] * len(partes)

    def texto() -> list[str]:
        return [
            parte[: len(parte) - corte].rstrip(" ,") + "…" if corte else parte
            for parte, corte in zip(partes, cortes, strict=True)
        ]

    while (
        sum(map(len, texto())) + len(SEPARADOR_DO_NOME) * (len(partes) - 1) > orcamento
    ):
        restante = [
            len(parte) - corte for parte, corte in zip(partes, cortes, strict=True)
        ]
        if max(restante) <= 1:
            break
        cortes[restante.index(max(restante))] += 1
    return texto()


def _nome_da_serie(valor: Valor, rotulo_do_periodo: str) -> str:
    """`variável · categoria · local (rótulo; IBGE/SIDRA)`, em até 120 caracteres: se passar,
    cortam-se a variável e a categoria (as partes longas), nunca o local nem o rótulo do período."""
    fonte = (
        f" ({rotulo_do_periodo}; IBGE/SIDRA)" if rotulo_do_periodo else " (IBGE/SIDRA)"
    )
    fixa = f"{SEPARADOR_DO_NOME}{valor.nome_do_local}" if valor.nome_do_local else ""
    longas = [p for p in (valor.nome_da_variavel, valor.nome_da_categoria) if p]
    orcamento = NOME_MAXIMO_DA_SERIE - len(fixa) - len(fonte)
    return SEPARADOR_DO_NOME.join(_encurtar(longas, orcamento)) + fixa + fonte


def serie_do_acervo(
    tabela: int, valor: Valor, frequencia: str, rotulo_do_periodo: str = ""
) -> SerieDoAcervo:
    return SerieDoAcervo(
        codigo_da_serie(tabela, valor),
        _nome_da_serie(valor, rotulo_do_periodo),
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
    frequencia: str  # "mensal", "trimestral" (AAAATT) ou "anual"
    soma_o_total_do_cafe: bool = False
    descarta_series_vazias: bool = False
    rotulo_do_periodo: str = (
        ""  # vai no nome da série (PNAD: o período é um trimestre móvel)
    )

    def urls(self, periodo: str) -> list[str]:
        """Um pedido por território; o período se divide em blocos que cabem no limite do SIDRA."""
        return [
            montar_url(self.tabela, self.variaveis, self.classificacoes, p, t)
            for t in self.territorios
            for p in self._blocos(periodo, t)
        ]

    def _celulas_por_periodo(self, territorio: str) -> int:
        categorias = 1
        for ids in self.classificacoes.values():
            categorias *= len(ids)
        return (
            len(self.variaveis)
            * categorias
            * CELULAS_POR_TERRITORIO[territorio.split("/")[0]]
        )

    def blocos_de_periodos(self, territorio: str) -> int:
        """Quantos períodos (meses, trimestres ou anos) cabem em um pedido deste território."""
        return max(
            1, VALORES_POR_PEDIDO_NO_SIDRA // self._celulas_por_periodo(territorio)
        )

    def _blocos(self, periodo: str, territorio: str = "n1/all") -> list[str]:
        """`AAAA-AAAA`, `AAAAMM-AAAAMM` ou `AAAATT-AAAATT` em blocos; outro formato ("last 3")
        vai inteiro."""
        primeiro, _, ultimo = periodo.partition("-")
        if not (ultimo and primeiro.isdigit() and ultimo.isdigit()):
            return [periodo]
        por_pedido = self.blocos_de_periodos(territorio)
        de, ate = _indice(primeiro, self.frequencia), _indice(ultimo, self.frequencia)
        return [
            f"{_texto(inicio, self.frequencia)}-"
            f"{_texto(min(inicio + por_pedido - 1, ate), self.frequencia)}"
            for inicio in range(de, ate + 1, por_pedido)
        ]


def _periodos_por_ano(frequencia: str) -> int:
    return TRIMESTRES_POR_ANO if frequencia == "trimestral" else 12


def _indice(periodo: str, frequencia: str | None = None) -> int:
    """AAAAMM → meses desde o ano 0; AAAATT → trimestres desde o ano 0; AAAA → o ano.

    Sem `frequencia`, 6 dígitos são um mês (como as coletas mensais sempre leram)."""
    if len(periodo) == TAMANHO_DO_MES:
        por_ano = _periodos_por_ano(frequencia or "mensal")
        return int(periodo[:4]) * por_ano + int(periodo[4:]) - 1
    return int(periodo)


def _texto(indice: int, frequencia: str) -> str:
    if frequencia == "anual":
        return str(indice)
    por_ano = _periodos_por_ano(frequencia)
    return f"{indice // por_ano}{indice % por_ano + 1:02d}"


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

# PMC por atividade (8882 restrito, 8883 ampliado): os tipos de índice mudam de id entre as duas tabelas
PMC_ATIVIDADES_RESTRITO = (
    90671, 90672, 103154, 90673, 2759, 31555, 31556, 103155, 103156, 103157, 103158,
)  # fmt: skip
PMC_ATIVIDADES_AMPLIADO = (*PMC_ATIVIDADES_RESTRITO, 103159, 2762, 56741)
# PIM-PF por grupos e classes (8885): alimentos, papel e celulose, químicos, minerais e metais, veículos
PIMPF_CLASSES_VARIAVEIS = (12606, 11602, 11603, 11604)
PIMPF_CLASSES = (
    129177, 129178, 129189, 129190, 31761, 129204, 129209, 129210, 129213, 129214,
    129226, 129233, 129238, 129268, 129269, 129271,
)  # fmt: skip
# LSPA além do café (6588): algodão, arroz, feijão (3 safras), milho (2), soja, trigo, cacau, cana, laranja
LSPA_OUTROS_PRODUTOS = (
    39429, 39432, 39436, 39437, 39438, 39441, 39442, 39443, 39445, 39453, 39456, 39463,
)  # fmt: skip
# PMS (8688): total, alojamento, alimentação, telecom, TI, transporte de cargas e de passageiros
PMS_VARIAVEIS = (7167, 7168, 11623, 11624, 11625, 11626)
PMS_TIPOS = {11046: (56725, 56726)}  # receita nominal e volume
PMS_ATIVIDADES = (107071, 56692, 56693, 39321, 39322, 56696, 56697)
# IPP (6903): indústria geral, extrativas, transformação e as 23 divisões
IPP_VARIAVEIS = (10008, 1396, 1394, 1395)
IPP_ATIVIDADES = (
    46608, 46609, 46610, 46611, 46618, 46619, 46620, 46621, 46622, 46625, 46626, 46627, 46628,
    46633, 46629, 46634, 46635, 46638, 46641, 46643, 46644, 46647, 46650, 46653, 46655, 46656,
)  # fmt: skip
SINAPI_VARIAVEIS = (
    48,
    2119,
    2120,
    49,
    1196,
    1197,
    1198,
)  # custo do m², material, mão de obra, índice, variações
IPCA15_VARIAVEIS = (355, 356, 1120, 357)  # mensal, no ano, 12 meses, peso
INPC_VARIAVEIS = (44, 68, 2292, 45)
# PAM lavouras temporárias (1612): algodão, arroz, cana, milho, soja, trigo; área, colhida, produção, rendimento, valor
PAM_TEMPORARIAS = (2689, 2692, 2696, 2711, 2713, 2716)
PAM_TEMPORARIAS_VARIAVEIS = (109, 216, 214, 112, 215)
# silvicultura: madeira em tora para papel e celulose (eucalipto e pinus) e carvão vegetal; área por espécie
PEVS_PRODUTOS = (0, 3455, 3458, 33253, 33254)
PEVS_AREA_ESPECIES = (0, 39326, 39327)
PPM_REBANHOS = (2670, 32794, 32796)  # bovino, suíno e galináceos
PPM_PRODUTOS = (2682, 2685)  # leite e ovos de galinha
# lote 2, trimestral (ids conferidos nos metadados do SIDRA em 05/11/2026)
# PIB (5932 taxas, 1621 índice com ajuste sazonal, 1846 valores correntes), Brasil: o total, três
# setores e a demanda; as taxas são ano contra ano, trimestre contra trimestre e 4 trimestres
PIB_SETORES = (90707, 90687, 90691, 90696, 93404, 93406, 93407, 93408)
PIB_TAXAS_VARIAVEIS = (6561, 6564, 6562)
# abate (1092 bovinos, 1093 suínos, 1094 frangos) e leite (1086): total do trimestre, inspeção total
ABATE_VARIAVEIS = (284, 285)  # cabeças e peso das carcaças (kg)
TOTAL_DO_TRIMESTRE, INSPECAO_TOTAL, REBANHO_BOVINO_TOTAL = 115236, 118225, 992
# as classificações na ordem das colunas da resposta (o SIDRA devolve na ordem da tabela)
ABATE_TOTAIS = {12716: (TOTAL_DO_TRIMESTRE,), 12529: (INSPECAO_TOTAL,)}
ABATE_BOVINOS_TOTAIS = {
    12716: (TOTAL_DO_TRIMESTRE,),
    18: (REBANHO_BOVINO_TOTAL,),
    12529: (INSPECAO_TOTAL,),
}
LEITE_VARIAVEIS = (282, 2522)  # adquirido (mil litros) e preço médio (R$ por litro)
# PNAD contínua mensal: o período é o trimestre móvel que termina no mês (AAAAMM), e a data da
# série é o 1º dia desse mês
ROTULO_DA_PNAD = "trimestre móvel terminado em"

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
    Coleta("pmc-atividades-restrito", 8882, PMC_VARIAVEIS, {11046: (56733, 56734), 85: PMC_ATIVIDADES_RESTRITO}, ("n1/all", "n3/all"), "mensal"),
    Coleta("pmc-atividades-ampliado", 8883, PMC_VARIAVEIS, {11046: (56735, 56736), 85: PMC_ATIVIDADES_AMPLIADO}, ("n1/all", "n3/all"), "mensal"),
    Coleta("pimpf-classes", 8885, PIMPF_CLASSES_VARIAVEIS, {542: PIMPF_CLASSES}, ("n1/all",), "mensal"),
    Coleta("lspa-outros", 6588, (35, 36, 109, 216), {48: LSPA_OUTROS_PRODUTOS}, ("n1/all", "n3/all"), "mensal"),
    Coleta("pms", 8688, PMS_VARIAVEIS, {**PMS_TIPOS, 12355: PMS_ATIVIDADES}, ("n1/all",), "mensal"),
    Coleta("ipp", 6903, IPP_VARIAVEIS, {842: IPP_ATIVIDADES}, ("n1/all",), "mensal"),
    Coleta("sinapi", 2296, SINAPI_VARIAVEIS, {}, ("n1/all", "n3/all"), "mensal"),
    Coleta("ipca15-itens", 7062, IPCA15_VARIAVEIS, {315: IPCA_ITENS}, ("n1/all",), "mensal"),
    Coleta("inpc-itens", 7063, INPC_VARIAVEIS, {315: IPCA_ITENS}, ("n1/all",), "mensal"),
    Coleta("pam-temporarias", 1612, PAM_TEMPORARIAS_VARIAVEIS, {81: PAM_TEMPORARIAS}, ("n1/all", "n3/all"), "anual"),
    Coleta("pevs-producao", 291, (142, 143), {194: PEVS_PRODUTOS}, ("n1/all", "n3/all"), "anual"),
    Coleta("pevs-area", 5930, (6549,), {734: PEVS_AREA_ESPECIES}, ("n1/all", "n3/all"), "anual"),
    Coleta("ppm-rebanhos", 3939, (105,), {79: PPM_REBANHOS}, ("n1/all", "n3/all"), "anual"),
    Coleta("ppm-origem-animal", 74, (106, 215), {80: PPM_PRODUTOS}, ("n1/all", "n3/all"), "anual"),
    Coleta("populacao", 6579, (9324,), {}, ("n1/all", "n3/all"), "anual"),
    Coleta("pib-taxas", 5932, PIB_TAXAS_VARIAVEIS, {11255: PIB_SETORES}, ("n1/all",), "trimestral"),
    Coleta("pib-indice", 1621, (584,), {11255: PIB_SETORES}, ("n1/all",), "trimestral"),
    Coleta("pib-valores", 1846, (585,), {11255: PIB_SETORES}, ("n1/all",), "trimestral"),
    Coleta("abate-bovinos", 1092, ABATE_VARIAVEIS, ABATE_BOVINOS_TOTAIS, ("n1/all", "n3/all"), "trimestral"),
    Coleta("abate-suinos", 1093, ABATE_VARIAVEIS, ABATE_TOTAIS, ("n1/all", "n3/all"), "trimestral"),
    Coleta("abate-frangos", 1094, ABATE_VARIAVEIS, ABATE_TOTAIS, ("n1/all", "n3/all"), "trimestral"),
    Coleta("leite", 1086, LEITE_VARIAVEIS, ABATE_TOTAIS, ("n1/all", "n3/all"), "trimestral"),
    Coleta("pnad-desocupacao", 6381, (4099,), {}, ("n1/all",), "mensal", rotulo_do_periodo=ROTULO_DA_PNAD),
    Coleta("pnad-rendimento", 6390, (5933,), {}, ("n1/all",), "mensal", rotulo_do_periodo=ROTULO_DA_PNAD),
    Coleta("pnad-massa", 6392, (6293,), {}, ("n1/all",), "mensal", rotulo_do_periodo=ROTULO_DA_PNAD),
)  # fmt: skip
COLETAS_POR_NOME = {c.nome: c for c in COLETAS}
