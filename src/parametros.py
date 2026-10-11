"""O catálogo dos parâmetros configuráveis do TickerLab Research (PRD v2, seções 9.2 e 9.4).

Cada parâmetro tem chave (`dominio.nome`), tipo, padrão do sistema, limites, unidade e uma frase do
que ele muda. As **regras** ligam parâmetros entre si (média rápida menor que a lenta, pesos somando
100%). Este módulo só valida: não calcula nada e não conhece banco nem tela.

Os padrões são valores didáticos e comuns na literatura, **não** valores comprovadamente ótimos. Mudar
um parâmetro muda a leitura; nunca muda os dados de preço nem os fatos de uma fonte.
"""

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Literal

Tipo = Literal["inteiro", "decimal", "escolha", "temas"]
Valor = int | float | str | tuple[str, ...]

DOMINIOS = {
    "quant": "Quantitativa",
    "tecnica": "Técnica",
    "fundamentalista": "Fundamentalista",
    "relevancia": "Relevância (o que aparece primeiro no Research)",
    "editorial": "Peso de cada assunto na edição",
    "newsletter": "Newsletter",
}


class ParametroInvalidoError(ValueError):
    """Um valor que o catálogo não aceita (tipo, limite, opção ou combinação)."""


@dataclass(frozen=True)
class ParametroConfiguravel:
    chave: str  # "dominio.nome"
    rotulo: str
    tipo: Tipo
    padrao: Valor
    ajuda: str  # o que muda quando se mexe nele
    minimo: float | None = None
    maximo: float | None = None
    unidade: str = ""
    opcoes: tuple = ()  # valores aceitos (escolha) ou temas disponíveis (temas)

    @property
    def dominio(self) -> str:
        return self.chave.split(".", 1)[0]

    def validar(self, valor: object) -> Valor:
        """Devolve o valor normalizado (ex.: 21.0 vira 21) ou explica por que não serve."""
        nome = f"{self.rotulo} ({self.chave})"
        if isinstance(valor, bool):
            raise ParametroInvalidoError(
                f"{nome}: verdadeiro/falso não é um valor válido."
            )
        if self.tipo in ("inteiro", "decimal"):
            if not isinstance(valor, int | float):
                raise ParametroInvalidoError(f"{nome}: precisa ser um número.")
            if not math.isfinite(valor):
                raise ParametroInvalidoError(f"{nome}: o número precisa ser finito.")
            if self.tipo == "inteiro":
                if isinstance(valor, float) and not valor.is_integer():
                    raise ParametroInvalidoError(
                        f"{nome}: precisa ser um número inteiro."
                    )
                valor = int(valor)
            else:
                valor = float(valor)
            if self.minimo is not None and valor < self.minimo:
                raise ParametroInvalidoError(
                    f"{nome}: o mínimo é {_numero(self.minimo)}{self.unidade_curta}."
                )
            if self.maximo is not None and valor > self.maximo:
                raise ParametroInvalidoError(
                    f"{nome}: o máximo é {_numero(self.maximo)}{self.unidade_curta}."
                )
            if self.opcoes and valor not in self.opcoes:
                raise ParametroInvalidoError(
                    f"{nome}: escolha entre {', '.join(_numero(o) for o in self.opcoes)}."
                )
            return valor
        if self.tipo == "escolha":
            if valor not in self.opcoes:
                raise ParametroInvalidoError(
                    f"{nome}: escolha entre {', '.join(map(str, self.opcoes))}."
                )
            return valor  # type: ignore[return-value]
        # temas: uma seleção (sem repetir) entre as opções, na ordem do catálogo
        if isinstance(valor, str) or not isinstance(
            valor, list | tuple | set | frozenset
        ):
            raise ParametroInvalidoError(f"{nome}: precisa ser uma lista de temas.")
        desconhecidos = [t for t in valor if t not in self.opcoes]
        if desconhecidos:
            raise ParametroInvalidoError(
                f"{nome}: temas desconhecidos: {', '.join(map(str, desconhecidos))}."
            )
        if not valor:
            raise ParametroInvalidoError(f"{nome}: escolha pelo menos um tema.")
        return tuple(t for t in self.opcoes if t in set(valor))

    @property
    def unidade_curta(self) -> str:
        return (
            "%" if self.unidade == "%" else (f" {self.unidade}" if self.unidade else "")
        )


def _numero(valor: float) -> str:
    return (
        str(int(valor)) if float(valor).is_integer() else str(valor).replace(".", ",")
    )


def _p(
    chave: str, rotulo: str, tipo: Tipo, padrao: Valor, ajuda: str, **extra: object
) -> ParametroConfiguravel:
    return ParametroConfiguravel(chave, rotulo, tipo, padrao, ajuda, **extra)


_PESO = {"minimo": 0, "maximo": 100, "unidade": "%"}
TEMAS = (
    "resultados",
    "proventos",
    "eventos",
    "risco",
    "tecnica",
    "valuation",
    "fundamentos",
)

PARAMETROS: tuple[ParametroConfiguravel, ...] = (
    # --- quantitativa ------------------------------------------------------------------------
    _p("quant.janela_volatilidade", "Janela da volatilidade", "inteiro", 252,
       "Quantos pregões entram no cálculo da volatilidade: janelas curtas reagem rápido e "
       "oscilam mais.", minimo=20, maximo=756, unidade="pregões"),
    _p("quant.janela_correlacao", "Janela da correlação e do beta", "inteiro", 120,
       "Quantos pregões entram na correlação e no beta móveis.", minimo=20, maximo=756,
       unidade="pregões"),
    _p("quant.var_confianca", "Confiança do VaR", "inteiro", 95,
       "Com 99%, o VaR olha para dias mais raros e fica maior. É uma estimativa, não um "
       "limite de perda.", opcoes=(95, 99), unidade="%"),
    _p("quant.benchmark", "Índice de referência", "escolha", "^BVSP",
       "Contra qual índice beta e comparações são calculados.",
       opcoes=("^BVSP", "^GSPC", "^IXIC")),
    _p("quant.taxa_livre_de_risco", "Taxa livre de risco", "escolha", "zero",
       "O que o Sharpe desconta do retorno: zero ou o CDI do Banco Central.",
       opcoes=("zero", "cdi")),
    # --- técnica -----------------------------------------------------------------------------
    _p("tecnica.tipo_de_media", "Tipo de média", "escolha", "simples",
       "A exponencial dá mais peso aos dias recentes.", opcoes=("simples", "exponencial")),
    _p("tecnica.media_rapida", "Média rápida", "inteiro", 50,
       "Período da média curta (tem de ser menor que a lenta).", minimo=2, maximo=400,
       unidade="pregões"),
    _p("tecnica.media_lenta", "Média lenta", "inteiro", 200,
       "Período da média longa.", minimo=3, maximo=500, unidade="pregões"),
    _p("tecnica.rsi_periodo", "Período do RSI", "inteiro", 14,
       "Períodos curtos deixam o RSI mais nervoso.", minimo=2, maximo=100, unidade="pregões"),
    _p("tecnica.rsi_inferior", "RSI: faixa de baixo", "inteiro", 30,
       "Abaixo dela o RSI é lido como \"sobrevendido\" (não é sinal de compra).",
       minimo=10, maximo=90),
    _p("tecnica.rsi_superior", "RSI: faixa de cima", "inteiro", 70,
       "Acima dela o RSI é lido como \"sobrecomprado\" (não é sinal de venda).",
       minimo=10, maximo=90),
    _p("tecnica.macd_rapida", "MACD: média rápida", "inteiro", 12,
       "Período da média rápida do MACD.", minimo=2, maximo=100, unidade="pregões"),
    _p("tecnica.macd_lenta", "MACD: média lenta", "inteiro", 26,
       "Período da média lenta do MACD.", minimo=3, maximo=200, unidade="pregões"),
    _p("tecnica.macd_sinal", "MACD: linha de sinal", "inteiro", 9,
       "Período da média do próprio MACD.", minimo=2, maximo=50, unidade="pregões"),
    _p("tecnica.bollinger_periodo", "Bollinger: período", "inteiro", 20,
       "Janela da média e do desvio das bandas.", minimo=2, maximo=200, unidade="pregões"),
    _p("tecnica.bollinger_desvios", "Bollinger: desvios", "decimal", 2.0,
       "Quantos desvios padrão separam as bandas da média.", minimo=1, maximo=4),
    _p("tecnica.atr_periodo", "Período do ATR", "inteiro", 14,
       "Janela da amplitude média dos pregões.", minimo=2, maximo=100, unidade="pregões"),
    _p("tecnica.periodicidade", "Periodicidade do gráfico", "escolha", "diario",
       "Diário ou semanal: os mesmos números de período não significam o mesmo tempo.",
       opcoes=("diario", "semanal")),
    # --- fundamentalista ---------------------------------------------------------------------
    _p("fundamentalista.anos", "Horizonte dos fundamentos", "inteiro", 5,
       "Quantos anos de demonstrações entram nas comparações e no crescimento.",
       minimo=1, maximo=10, unidade="anos"),
    _p("fundamentalista.roic_minimo", "ROIC mínimo do filtro", "decimal", 8.0,
       "Filtro educacional: só destaca empresas acima dele (não é classificação de compra).",
       minimo=-100, maximo=100, unidade="%"),
    _p("fundamentalista.pl_maximo", "P/L máximo do filtro", "decimal", 30.0,
       "Filtro educacional de valuation; P/L negativo é tratado como \"não se aplica\".",
       minimo=0, maximo=500),
    _p("fundamentalista.janela_proventos", "Janela dos proventos", "inteiro", 24,
       "Quantos meses de proventos entram no dividend yield. Yield passado não indica o futuro.",
       opcoes=(12, 24, 60), unidade="meses"),
    # --- relevância: soma 100 ----------------------------------------------------------------
    _p("relevancia.exposicao", "Peso da exposição", "inteiro", 25,
       "Quanto pesa o tamanho da posição ou o fato de você acompanhar o ativo.", **_PESO),
    _p("relevancia.materialidade", "Peso da materialidade", "inteiro", 25,
       "Quanto pesa a importância do evento (resultado, fato relevante, provento).", **_PESO),
    _p("relevancia.novidade", "Peso da novidade", "inteiro", 15,
       "Quanto pesa ser algo que você ainda não viu.", **_PESO),
    _p("relevancia.qualidade_da_fonte", "Peso da qualidade da fonte", "inteiro", 15,
       "Quanto pesa a fonte ser primária (CVM, SEC, RI) em vez de uma notícia.", **_PESO),
    _p("relevancia.preferencias", "Peso dos seus temas", "inteiro", 15,
       "Quanto pesam os temas que você escolheu.", **_PESO),
    _p("relevancia.recencia", "Peso da data", "inteiro", 5,
       "Quanto pesa ser recente.", **_PESO),
    # --- editorial: soma 100 -----------------------------------------------------------------
    _p("editorial.eventos", "Espaço para eventos", "inteiro", 35,
       "Parte da edição dedicada a fatos relevantes, resultados e comunicados.", **_PESO),
    _p("editorial.risco", "Espaço para risco", "inteiro", 25,
       "Parte dedicada a concentração, quedas e volatilidade.", **_PESO),
    _p("editorial.fundamentos", "Espaço para fundamentos", "inteiro", 25,
       "Parte dedicada a margens, endividamento, caixa e valuation.", **_PESO),
    _p("editorial.tecnica", "Espaço para técnica", "inteiro", 15,
       "Parte dedicada a médias, RSI e outros indicadores de preço.", **_PESO),
    # --- newsletter --------------------------------------------------------------------------
    _p("newsletter.cadencia", "Frequência", "escolha", "semanal",
       "Sob demanda, semanal, diária ou só quando um gatilho seu acontecer.",
       opcoes=("sob_demanda", "semanal", "diaria", "gatilhos")),
    _p("newsletter.max_itens", "Itens por edição", "inteiro", 7,
       "Mais itens dão mais cobertura e menos foco.", minimo=1, maximo=20),
    _p("newsletter.temas", "Temas", "temas", ("resultados", "proventos", "risco"),
       "Os assuntos que entram na edição.", opcoes=TEMAS),
    _p("newsletter.canal", "Onde ler", "escolha", "web",
       "No site ou em PDF. E-mail chega numa etapa futura, com opt-in.",
       opcoes=("web", "pdf")),
)  # fmt: skip
CATALOGO: dict[str, ParametroConfiguravel] = {p.chave: p for p in PARAMETROS}


# --- regras entre parâmetros -----------------------------------------------------------------
@dataclass(frozen=True)
class Regra:
    descricao: str
    chaves: tuple[str, ...]
    vale: Callable[[Mapping[str, Valor]], bool] = field(repr=False)


def _menor(a: str, b: str) -> Callable[[Mapping[str, Valor]], bool]:
    return lambda v: v[a] < v[b]  # type: ignore[operator]


def _soma_100(prefixo: str) -> Regra:
    chaves = tuple(c for c in CATALOGO if c.startswith(prefixo + "."))
    return Regra(
        f'Os pesos de "{DOMINIOS[prefixo]}" precisam somar 100%.',
        chaves,
        lambda v: sum(v[c] for c in chaves) == 100,  # type: ignore[misc]
    )


REGRAS: tuple[Regra, ...] = (
    Regra(
        "A média rápida precisa ser menor que a lenta.",
        ("tecnica.media_rapida", "tecnica.media_lenta"),
        _menor("tecnica.media_rapida", "tecnica.media_lenta"),
    ),
    Regra(
        "No MACD, a média rápida precisa ser menor que a lenta.",
        ("tecnica.macd_rapida", "tecnica.macd_lenta"),
        _menor("tecnica.macd_rapida", "tecnica.macd_lenta"),
    ),
    Regra(
        "A faixa de baixo do RSI precisa ser menor que a de cima.",
        ("tecnica.rsi_inferior", "tecnica.rsi_superior"),
        _menor("tecnica.rsi_inferior", "tecnica.rsi_superior"),
    ),
    _soma_100("relevancia"),
    _soma_100("editorial"),
)


def padroes_do_sistema() -> dict[str, Valor]:
    return {p.chave: p.padrao for p in PARAMETROS}


def validar_valores(valores: Mapping[str, object]) -> dict[str, Valor]:
    """Confere cada valor (chave conhecida, tipo, limites) e devolve os valores normalizados."""
    desconhecidas = sorted(set(valores) - set(CATALOGO))
    if desconhecidas:
        raise ParametroInvalidoError(
            f"Parâmetros desconhecidos: {', '.join(desconhecidas)}."
        )
    return {chave: CATALOGO[chave].validar(valor) for chave, valor in valores.items()}


def problemas_de_combinacao(valores: Mapping[str, Valor]) -> list[str]:
    """As regras quebradas por um conjunto completo de valores (vazio: está tudo certo)."""
    return [
        r.descricao
        for r in REGRAS
        if all(c in valores for c in r.chaves) and not r.vale(valores)
    ]


def conferir_padroes() -> None:
    """Os padrões do próprio catálogo passam em todas as validações (conferido nos testes)."""
    padroes = validar_valores(padroes_do_sistema())
    problemas = problemas_de_combinacao(padroes)
    if problemas:
        raise ParametroInvalidoError("; ".join(problemas))
