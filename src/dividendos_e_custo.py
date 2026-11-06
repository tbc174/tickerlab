"""Proventos recebidos e custo médio de cada ativo, a partir da movimentação da B3.

A planilha de movimentação da Área do Investidor é lida em `src/movimentacao_b3.py` e vira uma
lista de `Lancamento` (compra, venda, desdobro, provento...). Aqui ficam as contas, em tipos simples
(prontas para a API e para outra interface, ADR 0044):

- **Proventos:** dividendos, juros sobre capital próprio (JCP) e rendimentos de fundos, por ativo,
  por ano e nos últimos 12 meses; junto, a taxa do aluguel de ações (não é provento, mas é renda
  do ativo e cai na mesma conta).
- **Custo médio pela regra da Receita:** a compra soma ao custo o que se pagou; a venda baixa a
  quantidade pelo preço médio, que não muda; desdobro e grupamento mudam a quantidade sem mudar o
  custo total. Se a movimentação começa depois da primeira compra (vendeu mais do que comprou),
  o ativo fica "incompleto", sem número: um médio errado seria pior do que nenhum.

Nada aqui é recomendação nem cálculo de imposto: só descreve o que já aconteceu.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from src.carteira_b3 import CarteiraB3

TIPOS_DE_PROVENTO = (
    "dividendo",
    "jcp",
    "rendimento",
    "reembolso",  # o provento da ação enquanto ela está emprestada
    "aluguel",  # a taxa paga por quem tomou as ações emprestadas
)
# entram ou saem ações sem dinheiro: o custo total não muda
ENTRAM_SEM_CUSTO = ("desdobro", "bonificacao")
SAEM_SEM_CUSTO = ("grupamento",)
# devolução de capital de FII: não é provento, reduz o custo de aquisição e não mexe na quantidade
TIPOS_QUE_ABATEM_O_CUSTO = ("amortizacao",)
TIPOS_DE_LANCAMENTO = (
    "compra",
    "venda",
    *ENTRAM_SEM_CUSTO,
    *SAEM_SEM_CUSTO,
    *TIPOS_QUE_ABATEM_O_CUSTO,
    *TIPOS_DE_PROVENTO,
)
# a ordem dentro de um mesmo dia: o que entra antes do que sai (uma compra e uma venda liquidadas
# no mesmo dia não podem parecer uma venda sem compra)
_ORDEM_NO_DIA = {
    "compra": 0,
    "desdobro": 0,
    "bonificacao": 0,
    "amortizacao": 1,
    "grupamento": 1,
    "venda": 1,
}
_QUASE_ZERO = 1e-9

# ---- textos da tela (aqui, para a API e outra interface usarem os mesmos) ----
COMO_BAIXAR_A_MOVIMENTACAO = (
    "1. Na **Área do Investidor** da B3, abra **Extratos → Movimentação**.\n"
    "2. Escolha o período (desde a primeira compra, se der: o custo médio precisa dela) e "
    "baixe em **Excel**.\n"
    "3. Envie o arquivo aqui. Como a posição, ele é lido **só na memória** e não fica guardado."
)
AVISO_DA_MOVIMENTACAO_DE_EXEMPLO = (
    "**Exemplo demonstrativo:** movimentação fictícia, não é a sua."
)
NOMES_DOS_PROVENTOS = {
    "dividendo": "Dividendos",
    "jcp": "JCP (líquido)",
    "rendimento": "Rendimentos",
    "reembolso": "Reembolsos",
    "aluguel": "Aluguel",
}
NOTA_DOS_PROVENTOS = (
    "O que caiu na conta, como a B3 registra. O JCP já vem com os 15% de imposto retidos na "
    "fonte. Reembolso é o provento pago enquanto a ação estava emprestada; Aluguel é a taxa que "
    "quem tomou as ações emprestadas paga (não é provento, mas é renda do ativo). Os últimos "
    "12 meses contam só o que já foi pago até hoje."
)
NOTA_DO_CUSTO = (
    "Custo médio pela regra da Receita: a compra soma ao custo o que se pagou, a venda não muda "
    "o médio, desdobro e grupamento mudam a quantidade sem mudar o custo. A planilha da B3 não "
    "traz corretagem nem emolumentos, que a Receita manda somar ao custo: confira com as notas "
    "de corretagem. Não é cálculo de imposto nem recomendação."
)
SEM_PROVENTOS = "A movimentação não tem proventos no período."
SEM_A_POSICAO = (
    "Envie também a planilha de posição, no começo da página, para ver o ganho ou a perda de "
    "hoje de cada ativo."
)


def formatar_reais(valor: float) -> str:
    """R$ 1.234,56, como se escreve no Brasil."""
    texto = f"{abs(valor):,.2f}".replace(",", "#").replace(".", ",").replace("#", ".")
    return f"{'-' if valor < 0 else ''}R$ {texto}"


AVISO_DA_BONIFICACAO = (
    "Recebeu bonificação: a Receita manda somar ao custo o valor que a empresa atribuiu a cada "
    "ação nova, e esse valor não vem na planilha da B3. O custo médio aqui fica um pouco menor "
    "que o oficial; confira no informe da empresa."
)
AVISO_DA_AMORTIZACAO_ACIMA_DO_CUSTO = (
    "Uma amortização passou do custo que sobrava: o custo ficou em zero e o que passou é ganho "
    "de capital (pode haver imposto retido pelo administrador). Confira no informe do fundo."
)
MOTIVO_HISTORICO_INCOMPLETO = (
    "A movimentação começa depois da primeira compra (saíram mais ações do que entraram). "
    "Baixe a movimentação desde a primeira compra para ver o custo médio."
)
MOTIVO_COMPRA_SEM_VALOR = (
    "Uma compra veio sem o valor pago, então não dá para saber o custo médio."
)


@dataclass(frozen=True)
class Lancamento:
    """Uma linha da movimentação, já entendida. `quantidade` é sempre positiva: o tipo diz se
    as ações entram ou saem. `valor` é o dinheiro da operação em reais (0 quando não há)."""

    data: date
    codigo: str
    tipo: str
    quantidade: float = 0.0
    valor: float = 0.0

    def __post_init__(self) -> None:
        if self.tipo not in TIPOS_DE_LANCAMENTO:
            raise ValueError(f"Lançamento de tipo desconhecido: {self.tipo!r}")


@dataclass(frozen=True)
class VendaRealizada:
    """Uma venda com o resultado dela: o que entrou menos o custo das ações vendidas."""

    data: date
    codigo: str
    quantidade: float
    valor: float  # o que entrou com a venda
    custo: float  # preço médio do momento × quantidade vendida

    @property
    def resultado(self) -> float:
        return (
            self.valor - self.custo
        )  # lucro (+) ou prejuízo (−), sem corretagem e taxas


@dataclass(frozen=True)
class CustoDoAtivo:
    codigo: str
    quantidade: float | None  # None quando incompleto
    custo_total: float | None  # None quando incompleto
    preco_medio: float | None  # None quando incompleto ou sem ações
    completo: bool
    motivo: str | None = None  # por que ficou incompleto
    avisos: tuple[str, ...] = ()
    vendas: tuple[VendaRealizada, ...] = ()  # vazio quando incompleto


MOTIVO_SEM_COMPRA = (
    "Não aparece compra na movimentação: o ativo foi comprado antes do período baixado."
)
MOTIVO_QUANTIDADE_DIFERENTE = (
    "A quantidade da posição não bate com a da movimentação (compra fora do período, "
    "transferência de outra pessoa ou um tipo de movimentação que o TickerLab não conhece)."
)


@dataclass(frozen=True)
class ResultadoDoAtivo:
    """Um ativo da posição de hoje com o custo dele: o ganho ou a perda ainda não realizados."""

    codigo: str
    quantidade: float  # da posição
    valor_hoje: float
    quantidade_na_movimentacao: float | None
    preco_medio: float | None
    custo_total: float | None
    resultado: (
        float | None
    )  # valor de hoje menos o custo; None quando não dá para saber
    resultado_percentual: float | None  # 0,5 = +50%
    motivo: str | None = None


@dataclass(frozen=True)
class ProventosDoAtivo:
    codigo: str
    total: float
    ultimos_12_meses: float
    por_ano: dict[int, float] = field(default_factory=dict)
    por_tipo: dict[str, float] = field(default_factory=dict)


def _incompleto(codigo: str, motivo: str) -> CustoDoAtivo:
    return CustoDoAtivo(codigo, None, None, None, False, motivo)


def _custo_de_um_ativo(codigo: str, lancamentos: list[Lancamento]) -> CustoDoAtivo:
    quantidade = custo = 0.0
    avisos: list[str] = []
    vendas: list[VendaRealizada] = []
    for lancamento in sorted(
        lancamentos, key=lambda lanc: (lanc.data, _ORDEM_NO_DIA[lanc.tipo])
    ):
        q = lancamento.quantidade
        if lancamento.tipo == "compra":
            if lancamento.valor <= 0:
                return _incompleto(codigo, MOTIVO_COMPRA_SEM_VALOR)
            quantidade, custo = quantidade + q, custo + lancamento.valor
        elif lancamento.tipo in ENTRAM_SEM_CUSTO:
            quantidade += q
            if lancamento.tipo == "bonificacao" and AVISO_DA_BONIFICACAO not in avisos:
                avisos.append(AVISO_DA_BONIFICACAO)
        elif lancamento.tipo in TIPOS_QUE_ABATEM_O_CUSTO:
            if quantidade <= _QUASE_ZERO:
                return _incompleto(codigo, MOTIVO_SEM_COMPRA)
            if lancamento.valor > custo + _QUASE_ZERO:
                if AVISO_DA_AMORTIZACAO_ACIMA_DO_CUSTO not in avisos:
                    avisos.append(AVISO_DA_AMORTIZACAO_ACIMA_DO_CUSTO)
                custo = 0.0
            else:
                custo -= lancamento.valor
        else:  # venda ou grupamento: saem ações
            if q > quantidade + _QUASE_ZERO:
                return _incompleto(codigo, MOTIVO_HISTORICO_INCOMPLETO)
            if lancamento.tipo == "venda":
                custo_da_venda = (
                    custo / quantidade * q
                )  # pelo preço médio, que não muda
                custo -= custo_da_venda
                vendas.append(
                    VendaRealizada(
                        lancamento.data, codigo, q, lancamento.valor, custo_da_venda
                    )
                )
            quantidade -= q
            if quantidade <= _QUASE_ZERO:
                # vendeu tudo: a próxima compra recomeça o médio
                quantidade = custo = 0.0
    medio = custo / quantidade if quantidade > 0 else None
    return CustoDoAtivo(
        codigo, quantidade, custo, medio, True, None, tuple(avisos), tuple(vendas)
    )


def custo_medio(lancamentos: list[Lancamento]) -> tuple[CustoDoAtivo, ...]:
    """O custo médio de cada ativo que teve compra, venda ou evento, ordenado pelo código."""
    por_ativo: dict[str, list[Lancamento]] = defaultdict(list)
    for lancamento in lancamentos:
        if lancamento.tipo not in TIPOS_DE_PROVENTO:
            por_ativo[lancamento.codigo].append(lancamento)
    return tuple(_custo_de_um_ativo(c, por_ativo[c]) for c in sorted(por_ativo))


def _um_ano_antes(dia: date) -> date:
    try:
        return dia.replace(year=dia.year - 1)
    except ValueError:  # 29 de fevereiro
        return dia.replace(year=dia.year - 1, day=28)


def custos_de_hoje(custos: tuple[CustoDoAtivo, ...]) -> tuple[CustoDoAtivo, ...]:
    """Os ativos que ainda estão na carteira (ou que não dá para saber): sem os vendidos inteiros."""
    return tuple(c for c in custos if not c.completo or c.quantidade)


def proventos(
    lancamentos: list[Lancamento], hoje: date
) -> tuple[ProventosDoAtivo, ...]:
    """Os proventos de cada ativo, do maior total ao menor.

    Os "últimos 12 meses" vão de um ano antes de `hoje` até `hoje`: um provento com data depois
    de hoje (anunciado, ainda não pago) entra no total, mas não nos 12 meses.
    """
    um_ano_antes = _um_ano_antes(hoje)
    soma: dict[str, float] = defaultdict(float)
    doze_meses: dict[str, float] = defaultdict(float)
    por_ano: dict[str, dict[int, float]] = defaultdict(lambda: defaultdict(float))
    por_tipo: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for lanc in lancamentos:
        if lanc.tipo not in TIPOS_DE_PROVENTO:
            continue
        soma[lanc.codigo] += lanc.valor
        por_ano[lanc.codigo][lanc.data.year] += lanc.valor
        por_tipo[lanc.codigo][lanc.tipo] += lanc.valor
        if um_ano_antes < lanc.data <= hoje:
            doze_meses[lanc.codigo] += lanc.valor
    resultado = [
        ProventosDoAtivo(
            codigo,
            soma[codigo],
            doze_meses[codigo],
            dict(sorted(por_ano[codigo].items())),
            dict(sorted(por_tipo[codigo].items())),
        )
        for codigo in soma
    ]
    return tuple(sorted(resultado, key=lambda p: (-p.total, p.codigo)))


def total_por_ano(
    proventos_dos_ativos: tuple[ProventosDoAtivo, ...],
) -> dict[int, float]:
    """Os proventos de todos os ativos somados por ano."""
    soma: dict[int, float] = defaultdict(float)
    for ativo in proventos_dos_ativos:
        for ano, valor in ativo.por_ano.items():
            soma[ano] += valor
    return dict(sorted(soma.items()))


def _por_que_sem_resultado(custo: CustoDoAtivo | None, quantidade: float) -> str | None:
    if custo is None:
        return MOTIVO_SEM_COMPRA
    if not custo.completo:
        return custo.motivo
    if abs((custo.quantidade or 0.0) - quantidade) > _QUASE_ZERO:
        return MOTIVO_QUANTIDADE_DIFERENTE
    return None


def com_a_posicao(
    custos: tuple[CustoDoAtivo, ...], carteira: CarteiraB3
) -> tuple[ResultadoDoAtivo, ...]:
    """Cada ativo da posição com o custo da movimentação, na ordem da posição.

    O resultado só aparece quando a quantidade da posição é a mesma que a movimentação explica:
    com quantidades diferentes, o custo seria de outra quantidade de ações.
    """
    por_codigo = {custo.codigo: custo for custo in custos}
    resultados = []
    for linha in carteira.posicoes.itertuples(index=False):
        codigo, quantidade, valor = (
            str(linha.codigo),
            float(linha.quantidade),
            float(linha.valor),
        )
        custo = por_codigo.get(codigo)
        motivo = _por_que_sem_resultado(custo, quantidade)
        # só usa o custo quando ele explica exatamente a quantidade de hoje
        usado = custo if motivo is None else None
        custo_total = usado.custo_total if usado else None
        resultado = percentual = None
        if custo_total is not None:
            resultado = valor - custo_total
            percentual = resultado / custo_total if custo_total else None
        resultados.append(
            ResultadoDoAtivo(
                codigo=codigo,
                quantidade=quantidade,
                valor_hoje=valor,
                quantidade_na_movimentacao=custo.quantidade if custo else None,
                preco_medio=usado.preco_medio if usado else None,
                custo_total=custo_total,
                resultado=resultado,
                resultado_percentual=percentual,
                motivo=motivo,
            )
        )
    return tuple(resultados)
