"""Os relatórios em PDF do TickerLab: do ativo, de comparação, de backtest e de carteira.

Cada função recebe os dados já baixados e devolve os bytes do PDF. Os números saem das MESMAS
funções que o site usa (`indicadores`, `comparacao`, `backtest`, `metricas`, `carteiras`), então o
relatório bate com a tela. Não conhece o Streamlit: quem chama é o app.py.

Report Studio (blueprint, seção 12): cada relatório é um conjunto de **seções com nome**
(`SECOES`). O modelo (Executivo ou Pesquisa completa) ou a própria pessoa escolhe quais entram e
em que ordem, e o estilo (`estilos_pdf`) escolhe as cores. Nada disso muda um cálculo: só a
organização. A seção "Limites e cuidados" é obrigatória (não dá para tirar os avisos), e o
resumo executivo só repete, em frases neutras, números que o relatório já mostra.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from src import graficos_pdf as gp
from src import indicadores as ind
from src.analises import MIN_DIAS_PARA_ANALISE
from src.backtest import CUSTO_PADRAO_POR_OPERACAO, executar_backtest
from src.carteira_b3 import (
    CarteiraB3,
    numero_efetivo_de_ativos,
    retorno_com_os_pesos_de_hoje,
)
from src.carteiras import (
    ESTRATEGIAS_DE_CARTEIRA,
    MIN_DIAS_NA_CARTEIRA,
    simular_carteira,
)
from src.comparacao import montar_tabela_comparativa, rebasear_para_100
from src.conteudo import carregar_glossario, descrever_pior_drawdown
from src.estilos_pdf import Estilo
from src.estilos_pdf import estilo as estilo_pela_chave
from src.estrategias import ESTRATEGIAS, gerar_posicao, posicao_comprar_e_segurar
from src.ficha import (
    TOLERANCIA_PADRAO_DE_QUEDA,
    Ficha,
    PedidoDaFicha,
    montar_ficha,
    texto_das_tentativas,
)
from src.metricas import resumir_desempenho
from src.relatorio_pdf import RelatorioPDF
from src.tentativas import TETO_POR_PESSOA

FUSO = ZoneInfo("America/Sao_Paulo")
# sobe quando o conteúdo ou a organização dos relatórios mudar (vai no anexo de reprodutibilidade)
VERSAO_DOS_RELATORIOS = "2"
ATIVO = "ativo"
COMPARACAO = "comparacao"
BACKTEST = "backtest"
CARTEIRA = "carteira"
MINHA_CARTEIRA = "minha_carteira"
NEWSLETTER = "newsletter"
NOMES_DOS_RELATORIOS = {
    ATIVO: "Relatório do ativo",
    COMPARACAO: "Comparação de ativos",
    BACKTEST: "Relatório de backtest",
    CARTEIRA: "Relatório de carteira",
    MINHA_CARTEIRA: "Minha carteira (B3)",
    NEWSLETTER: "Newsletter do Research",
}
AVISO_DA_MINHA_CARTEIRA = (
    "Esta análise mostra como a carteira de HOJE, com os pesos de hoje, teria se comportado no "
    "passado. Não é o seu resultado real: você comprou em outras datas e preços, e pode ter "
    "mudado a carteira no caminho. Serve para entender o risco e a concentração do que você tem."
)
AVISO_DO_BACKTEST = (
    "Um bom resultado no passado pode ser sorte: com muitas estratégias e parâmetros, alguma "
    'sempre parece ótima. A seção "Foi sorte?" confere isso em cinco perguntas; o detalhe '
    "técnico (treino e teste, walk-forward, teste contra o acaso e Sharpe deflacionado) está na "
    "página Backtest do site."
)
# o relatório não pergunta o capital: o imposto da ficha é calculado sobre o mesmo valor que a
# página Backtest abre por padrão
CAPITAL_DO_RELATORIO = 10_000.0
FONTE_DOS_DADOS = (
    "Yahoo Finance, preços de fechamento ajustados por dividendos e desdobramentos"
)


# --- seções e modelos (Report Studio) -------------------------------------------------------
class DadosInsuficientesError(ValueError):
    """Poucos pregões para os números dizerem algo: o relatório não sai (a tela faz o mesmo).

    É um ValueError porque a tela do estúdio já mostra esse erro e não conta no limite do plano.
    """


def _exigir_pregoes(pregoes: int, minimo: int, onde: str = "") -> None:
    """Recusa com poucos pregões: o mesmo mínimo da tela, numa frase que a tela mostra inteira."""
    if pregoes < minimo:
        palavra = "pregão" if pregoes == 1 else "pregões"
        raise DadosInsuficientesError(
            f"só há {pregoes} {palavra}{onde}, e são necessários pelo menos {minimo}. "
            "Escolha um período mais longo"
        )


# um pregão a mais que o mínimo de retornos (cada retorno liga dois pregões)
MIN_PREGOES = MIN_DIAS_PARA_ANALISE + 1
EM_COMUM = " em comum entre os ativos"


@dataclass(frozen=True)
class Secao:
    chave: str
    titulo: str
    descricao: str  # o que a seção traz (mostrado no estúdio)
    obrigatoria: bool = False


_RESUMO = Secao(
    "resumo",
    "Resumo executivo",
    "3 a 5 achados em frases curtas, só com números do relatório.",
)
_METODOLOGIA = Secao(
    "metodologia",
    "Metodologia e reprodutibilidade",
    "Fonte, momento da coleta, período, parâmetros e como cada número foi calculado.",
)
_GLOSSARIO = Secao("glossario", "Glossário", "O que cada número quer dizer.")
_LIMITES = Secao(
    "limites",
    "Limites e cuidados",
    "O que o relatório não diz. Obrigatória: os avisos não podem sair.",
    obrigatoria=True,
)
SECOES: dict[str, tuple[Secao, ...]] = {
    ATIVO: (
        _RESUMO,
        Secao("numeros", "Números-chave", "Retorno, risco, Sharpe, melhor e pior dia."),
        Secao("preco", "Preço no período", "Gráfico do preço de fechamento."),
        Secao("quedas", "Risco: as quedas", "A pior queda e o gráfico de drawdown."),
        Secao("mensal", "Retorno mês a mês", "Mapa de calor dos meses e anos."),
        _METODOLOGIA,
        _GLOSSARIO,
        _LIMITES,
    ),
    COMPARACAO: (
        _RESUMO,
        Secao("tabela", "Lado a lado", "As mesmas métricas para todos os ativos."),
        Secao("base100", "Quanto R$ 100 viraram", "Gráfico em base 100."),
        _METODOLOGIA,
        _GLOSSARIO,
        _LIMITES,
    ),
    BACKTEST: (
        _RESUMO,
        Secao(
            "resultado",
            "Resultado",
            "Retorno, queda, Sharpe, tempo comprado, operações.",
        ),
        Secao(
            "foi_sorte",
            "Foi sorte?",
            "O veredito e as cinco perguntas que separam padrão de sorte.",
        ),
        Secao(
            "curva", "Curva de capital", "Quanto R$ 1 virou, contra comprar e segurar."
        ),
        Secao(
            "tabela",
            "Estratégia contra comprar e segurar",
            "Tabela de métricas lado a lado.",
        ),
        _METODOLOGIA,
        _GLOSSARIO,
        _LIMITES,
    ),
    CARTEIRA: (
        _RESUMO,
        Secao("resultado", "Resultado da carteira", "Retorno, risco, Sharpe e giro."),
        Secao("curva", "Curva de capital", "Quanto R$ 1 virou, contra pesos iguais."),
        Secao("pesos", "Composição ao longo do tempo", "Como os pesos mudaram."),
        Secao(
            "ativos", "Cada ativo sozinho", "Os ativos da carteira, cada um por conta."
        ),
        _METODOLOGIA,
        _GLOSSARIO,
        _LIMITES,
    ),
    MINHA_CARTEIRA: (
        _RESUMO,
        Secao(
            "composicao",
            "Composição e concentração",
            "Maior posição, 3 maiores e número efetivo de ativos.",
        ),
        Secao(
            "comportamento",
            "Como esta carteira se comportou",
            "A carteira de hoje no passado, contra o Ibovespa.",
        ),
        Secao("ativos", "Cada ativo", "Valor, peso e comportamento de cada posição."),
        _METODOLOGIA,
        _GLOSSARIO,
        _LIMITES,
    ),
    NEWSLETTER: (
        Secao("destaques", "Destaques", "Os eventos mais relevantes pelos seus pesos."),
        Secao(
            "alertas",
            "Sinais de alerta",
            "Troca de auditor, atrasos, balanço refeito...",
        ),
        Secao(
            "por_dentro",
            "Pessoas de dentro e participações",
            "Compras e vendas de diretores, conselheiros e controladores; fatias de 5%.",
        ),
        Secao(
            "resultados", "Resultados e documentos", "Balanços e relatórios entregues."
        ),
        Secao(
            "donos", "Donos e fundos", "Quantos fundos e gestores entraram ou saíram."
        ),
        Secao(
            "parametros",
            "Parâmetros e fontes",
            "Janela, pesos, temas e quando cada fonte foi coletada.",
        ),
        _LIMITES,
    ),
}
EXECUTIVO = "executivo"
COMPLETO = "completo"
MODELOS = {
    EXECUTIVO: "Executivo (2 a 4 páginas)",
    COMPLETO: "Pesquisa completa",
}
DESCRICAO_DOS_MODELOS = {
    EXECUTIVO: "O essencial: resumo, números principais, o gráfico central e os limites.",
    COMPLETO: "Tudo: gráficos, tabelas, metodologia, glossário e limites.",
}
_SECOES_DO_EXECUTIVO = {
    ATIVO: ("resumo", "numeros", "preco", "limites"),
    COMPARACAO: ("resumo", "tabela", "base100", "limites"),
    BACKTEST: ("resumo", "resultado", "foi_sorte", "curva", "limites"),
    CARTEIRA: ("resumo", "resultado", "curva", "limites"),
    MINHA_CARTEIRA: ("resumo", "composicao", "comportamento", "limites"),
    NEWSLETTER: ("destaques", "alertas", "limites"),
}


def secoes_do_modelo(tipo: str, modelo: str) -> list[str]:
    """As seções (na ordem) de um modelo; um modelo desconhecido vira a pesquisa completa."""
    if modelo == EXECUTIVO:
        return list(_SECOES_DO_EXECUTIVO[tipo])
    return [s.chave for s in SECOES[tipo]]


def normalizar_secoes(
    tipo: str, escolhidas: list[str] | tuple[str, ...] | None
) -> list[str]:
    """A ordem final: só seções que existem, sem repetir, e as obrigatórias sempre presentes.

    `None` é a pesquisa completa na ordem padrão. Uma obrigatória que ficou de fora entra no fim.
    """
    if escolhidas is None:
        return secoes_do_modelo(tipo, COMPLETO)
    existentes = {s.chave for s in SECOES[tipo]}
    ordem = list(dict.fromkeys(c for c in escolhidas if c in existentes))
    ordem += [s.chave for s in SECOES[tipo] if s.obrigatoria and s.chave not in ordem]
    return ordem


@dataclass(frozen=True)
class Configuracao:
    """Como montar o PDF: estilo (cores) e seções (quais e em que ordem). Não muda cálculos."""

    estilo: str = "research"
    secoes: tuple[str, ...] | None = None  # None: pesquisa completa
    modelo: str = COMPLETO  # só para registro (anexo e biblioteca)


AoAvancar = Callable[[str], None] | None


def _avancar(ao_avancar: AoAvancar, etapa: str) -> None:
    if ao_avancar is not None:
        ao_avancar(etapa)


def _montar(
    pdf: RelatorioPDF,
    tipo: str,
    config: Configuracao,
    capa: list[tuple[str, str]],
    partes: dict[str, Callable[[], None]],
    ao_avancar: AoAvancar,
) -> bytes:
    """Capa com sumário, depois cada seção escolhida, na ordem, com o título numerado."""
    _avancar(ao_avancar, "Compondo seções")
    titulos = {s.chave: s.titulo for s in SECOES[tipo]}
    ordem = [c for c in normalizar_secoes(tipo, config.secoes) if c in partes]
    pdf.capa(capa, sumario=[titulos[c] for c in ordem])
    pdf.add_page()
    for chave in ordem:
        partes[chave]()
    _avancar(ao_avancar, "Criando PDF")
    return pdf.para_bytes()


def _cabecalho(pdf: RelatorioPDF, tipo: str) -> Callable[..., None]:
    titulos = {s.chave: s.titulo for s in SECOES[tipo]}

    def secao(chave: str, texto: str | None = None, reservar: float = 70) -> None:
        pdf.secao(titulos[chave], texto, reservar, numerada=True)

    return secao


# --- ajudantes de texto ---------------------------------------------------------------------
def agora() -> datetime:
    return datetime.now(FUSO)


def _o_que_e(termos: list[str]) -> dict[str, str]:
    """A primeira frase ("O que é") de cada termo do glossário do site, sem a formatação."""
    glossario = carregar_glossario()
    saida = {}
    for termo in termos:
        texto = glossario.get(termo, "")
        for linha in texto.splitlines():
            if linha.startswith("**O que é:**"):
                limpo = (
                    linha.removeprefix("**O que é:**")
                    .replace("*", "")  # negrito e itálico do Markdown
                    .replace("`", "")
                    .strip()
                )
                saida[termo] = limpo[:1].upper() + limpo[1:]
                break
    return saida


def _cor(valor: float, estilo: Estilo) -> str | None:
    if pd.isna(valor) or valor == 0:
        return None
    return estilo.alta if valor > 0 else estilo.queda


def _variacao(valor: float, casas: int = 1) -> str:
    """Retorno com sinal e seta (a cor sozinha não basta para quem não distingue verde e vermelho)."""
    if pd.isna(valor):
        return "—"
    seta = "▲" if valor > 0 else "▼" if valor < 0 else "■"
    return f"{seta} {gp.pct_br(valor, casas, sinal=True)}"


def _numero(valor: float, casas: int = 2) -> str:
    return "—" if pd.isna(valor) else gp.numero_br(valor, casas)


def _data(d: pd.Timestamp) -> str:
    return f"{d:%d/%m/%Y}"


def _intervalo(indice: pd.Index) -> str:
    return f"{_data(indice[0])} a {_data(indice[-1])}"


def _fonte(exemplo: bool) -> str:
    return "dados de exemplo, guardados no projeto" if exemplo else FONTE_DOS_DADOS


def _rodape_de_dados(exemplo: bool) -> list[tuple[str, str]]:
    return [
        ("Dados", "de exemplo, guardados no projeto" if exemplo else "Yahoo Finance")
    ]


def _pontos(a: float, b: float) -> str:
    """Diferença entre dois retornos em pontos percentuais ("12,3 pontos")."""
    return f"{gp.numero_br(abs(a - b) * 100, 1)} pontos percentuais"


def _metodologia(
    pdf: RelatorioPDF,
    secao: Callable[..., None],
    config: Configuracao,
    gerado_em: datetime,
    exemplo: bool,
    periodo_rotulo: str,
    indice: pd.Index,
    extras: list[tuple[str, str]],
) -> None:
    secao(
        "metodologia", "Com estes dados e parâmetros, o site chega aos mesmos números."
    )
    pdf.pares(
        [
            ("Fonte dos dados", _fonte(exemplo)),
            ("Coleta", f"{gerado_em:%d/%m/%Y às %H:%M} (horário de Brasília)"),
            ("Período", (f"{periodo_rotulo + ': ' if periodo_rotulo else ''}"
                        f"{_intervalo(indice)}, {len(indice)} pregões")),
            *extras,
            ("Cálculo", ("retornos diários do fechamento; ano de 252 pregões; Sharpe = "
                        "retorno anualizado menos a taxa livre de risco, dividido pela "
                        "volatilidade anual.")),
            ("Relatório", (f"TickerLab, relatórios versão {VERSAO_DOS_RELATORIOS}; modelo "
                          f"{MODELOS.get(config.modelo, 'Personalizado')}; estilo "
                          f"{estilo_pela_chave(config.estilo).nome}")),
        ]
    )  # fmt: skip


def _limites(
    pdf: RelatorioPDF, secao: Callable[..., None], itens: list[str], aviso: str | None
) -> None:
    secao("limites", "O que este relatório não diz.", reservar=50)
    if aviso:
        pdf.aviso_destacado(aviso)
    pdf.lista(
        [
            (
                "Descreve o que aconteceu no passado; não é previsão nem recomendação de compra "
                "ou venda."
            ),
            *itens,
            (
                "Os dados do Yahoo Finance podem ter atraso, falhas ou ajustes posteriores; "
                "confira números importantes em outra fonte."
            ),
            (
                "Impostos não entram nos cálculos, e o dinheiro fora do mercado não rende juros "
                "nas simulações."
            ),
        ]
    )


def _glossario(
    pdf: RelatorioPDF, secao: Callable[..., None], termos: list[str]
) -> None:
    secao("glossario", "O que cada número deste relatório quer dizer.")
    pdf.glossario(_o_que_e(termos))


# --- 1. do ativo ----------------------------------------------------------------------------
def achados_do_ativo(
    ticker: str, fechamento: pd.Series, taxa_livre_de_risco: float = 0.0
) -> list[str]:
    """3 a 5 frases do resumo executivo, só com números já calculados no relatório."""
    retorno = ind.calcular_retorno_diario(fechamento)
    total = float(ind.calcular_retorno_acumulado(retorno).iloc[-1])
    anual = ind.calcular_retorno_anualizado(retorno)
    vol = ind.calcular_volatilidade_anual(retorno)
    queda = float(ind.calcular_drawdown(fechamento).min())
    data_melhor, melhor = ind.encontrar_melhor_dia(retorno)
    data_pior, pior = ind.encontrar_pior_dia(retorno)
    sharpe = ind.calcular_indice_sharpe(retorno, taxa_livre_de_risco)
    achados = [
        (
            f"De {_intervalo(fechamento.index)}, o preço de {ticker} variou {_variacao(total)} "
            f"no total, o equivalente a {_variacao(anual)} ao ano."
        ),
        (
            f"A maior queda a partir de um topo foi de {gp.pct_br(queda)}: quem comprou no topo "
            "chegou a ver esse prejuízo no papel."
        ),
        (
            f"A volatilidade foi de {gp.pct_br(vol)} ao ano, perto de "
            f"{gp.pct_br(vol / 252**0.5)} de oscilação num dia típico."
        ),
        (
            f"Fechou em alta em {gp.pct_br(ind.calcular_percentual_dias_positivos(retorno))} dos "
            f"pregões; o melhor dia foi {_data(data_melhor)} ({_variacao(melhor)}) e o pior, "
            f"{_data(data_pior)} ({_variacao(pior)})."
        ),
    ]
    if not pd.isna(sharpe):
        achados.append(
            f"O índice de Sharpe foi de {_numero(sharpe)}: "
            + (
                "o retorno ficou acima da taxa livre de risco, considerando o risco."
                if sharpe > 0
                else "o retorno não superou a taxa livre de risco no período."
            )
        )
    return achados


def relatorio_do_ativo(
    ticker: str,
    dados: pd.DataFrame,
    taxa_livre_de_risco: float = 0.0,
    periodo: str = "",
    gerado_em: datetime | None = None,
    exemplo: bool = False,
    config: Configuracao | None = None,
    ao_avancar: AoAvancar = None,
) -> bytes:
    config = config or Configuracao()
    e = estilo_pela_chave(config.estilo)
    gerado_em = gerado_em or agora()
    fechamento = dados["Close"].dropna()
    _exigir_pregoes(len(fechamento), MIN_PREGOES)
    retorno = ind.calcular_retorno_diario(fechamento)
    total = float(ind.calcular_retorno_acumulado(retorno).iloc[-1])
    anual = ind.calcular_retorno_anualizado(retorno)
    data_melhor, melhor = ind.encontrar_melhor_dia(retorno)
    data_pior, pior = ind.encontrar_pior_dia(retorno)
    queda = float(ind.calcular_drawdown(fechamento).min())
    sharpe = ind.calcular_indice_sharpe(retorno, taxa_livre_de_risco)

    pdf = RelatorioPDF(
        f"{ticker}: retorno, risco e comportamento",
        f"Relatório do ativo {ticker}" + (f", período de {periodo}" if periodo else ""),
        gerado_em,
        e,
    )
    secao = _cabecalho(pdf, ATIVO)

    def resumo() -> None:
        secao("resumo", reservar=50)
        pdf.lista(achados_do_ativo(ticker, fechamento, taxa_livre_de_risco))

    def numeros() -> None:
        secao("numeros", "Retorno e risco no período, depois de juntar todos os dias.")
        pdf.cartoes(
            [
                ("Retorno total", _variacao(total), _cor(total, e)),
                ("Retorno anualizado", _variacao(anual), _cor(anual, e)),
                ("Volatilidade anual", gp.pct_br(ind.calcular_volatilidade_anual(retorno)),
                 None),
                ("Maior queda", gp.pct_br(queda), e.queda),
                ("Índice de Sharpe", _numero(sharpe), None),
                ("Dias de alta", gp.pct_br(ind.calcular_percentual_dias_positivos(retorno)),
                 None),
                (f"Melhor dia ({_data(data_melhor)})", _variacao(melhor), _cor(melhor, e)),
                (f"Pior dia ({_data(data_pior)})", _variacao(pior), _cor(pior, e)),
            ]
        )  # fmt: skip

    def preco() -> None:
        secao("preco", reservar=75)
        pdf.imagem(
            gp.grafico_de_preco(
                fechamento, f"Preço de fechamento de {ticker}", estilo=e
            )
        )

    def quedas() -> None:
        secao(
            "quedas", descrever_pior_drawdown(ind.encontrar_pior_drawdown(fechamento))
        )
        pdf.imagem(gp.grafico_de_drawdown(fechamento, estilo=e))

    def mensal() -> None:
        tabela = ind.montar_tabela_retornos(ind.calcular_retorno_mensal(retorno))
        if tabela.empty:
            return
        secao(
            "mensal",
            "Verde para meses de alta, vermelho para meses de queda. A última coluna é o ano.",
        )
        pdf.imagem(gp.grafico_de_retorno_mensal(tabela, estilo=e))

    partes = {
        "resumo": resumo,
        "numeros": numeros,
        "preco": preco,
        "quedas": quedas,
        "mensal": mensal,
        "metodologia": lambda: _metodologia(
            pdf,
            secao,
            config,
            gerado_em,
            exemplo,
            periodo,
            fechamento.index,
            [
                ("Ativo", ticker),
                ("Taxa livre de risco", f"{gp.pct_br(taxa_livre_de_risco, 2)} ao ano"),
            ],
        ),
        "glossario": lambda: _glossario(
            pdf,
            secao,
            [
                "Retorno acumulado",
                "Retorno anualizado",
                "Volatilidade",
                "Drawdown",
                "Índice de Sharpe",
                "Dias de alta",
                "Melhor e pior dia",
                "Retorno mensal",
            ],
        ),
        "limites": lambda: _limites(
            pdf,
            secao,
            [
                (
                    "Um único ativo concentra o risco: o comportamento de uma empresa pode mudar "
                    "por motivos que os preços passados não mostram."
                )
            ],
            None,
        ),
    }
    capa = [
        ("Ativo", ticker),
        ("Período", _intervalo(fechamento.index)),
        ("Pregões analisados", str(len(fechamento))),
        ("Último fechamento", gp.numero_br(float(fechamento.iloc[-1]))),
        *_rodape_de_dados(exemplo),
        ("Gerado em", f"{gerado_em:%d/%m/%Y %H:%M}"),
    ]
    return _montar(pdf, ATIVO, config, capa, partes, ao_avancar)


# --- 2. comparação --------------------------------------------------------------------------
def achados_da_comparacao(tabela: pd.DataFrame, pregoes: int) -> list[str]:
    melhor = tabela["Retorno total"].idxmax()
    calmo = tabela["Volatilidade anual"].idxmin()
    fundo = tabela["Maior queda"].idxmin()
    achados = [
        f"Comparação em {pregoes} pregões em comum, os mesmos dias para todos.",
        f"Maior retorno no período: {melhor} ({_variacao(tabela.loc[melhor, 'Retorno total'])}).",
        (
            f"Menor volatilidade: {calmo} ({gp.pct_br(tabela.loc[calmo, 'Volatilidade anual'])} "
            "ao ano)."
        ),
        (
            f"Maior queda a partir de um topo: {fundo} "
            f"({gp.pct_br(tabela.loc[fundo, 'Maior queda'])})."
        ),
    ]
    sharpe = tabela["Índice de Sharpe"].dropna()
    if not sharpe.empty:
        achados.append(
            f"Melhor retorno por unidade de risco (Sharpe): {sharpe.idxmax()} "
            f"({_numero(sharpe.max())})."
        )
    return achados


def relatorio_de_comparacao(
    alinhado: pd.DataFrame,
    taxa_livre_de_risco: float = 0.0,
    periodo: str = "",
    gerado_em: datetime | None = None,
    exemplo: bool = False,
    config: Configuracao | None = None,
    ao_avancar: AoAvancar = None,
) -> bytes:
    """`alinhado`: fechamentos dos ativos nos mesmos dias (de `comparacao.alinhar_fechamentos`)."""
    config = config or Configuracao()
    e = estilo_pela_chave(config.estilo)
    gerado_em = gerado_em or agora()
    _exigir_pregoes(len(alinhado), MIN_PREGOES, EM_COMUM)
    tickers = list(alinhado.columns)
    tabela = montar_tabela_comparativa(alinhado, taxa_livre_de_risco)
    pdf = RelatorioPDF(
        "Comparação de ativos",
        ", ".join(tickers) + (f", período de {periodo}" if periodo else ""),
        gerado_em,
        e,
    )
    secao = _cabecalho(pdf, COMPARACAO)

    def resumo() -> None:
        secao("resumo", reservar=50)
        pdf.lista(achados_da_comparacao(tabela, len(alinhado)))

    def lado_a_lado() -> None:
        secao(
            "tabela",
            "Os mesmos números para todos, calculados só nos dias em que todos negociaram.",
        )
        linhas, cores = [], []
        for ticker, linha in tabela.iterrows():
            linhas.append(
                [
                    str(ticker),
                    _variacao(linha["Retorno total"]),
                    _variacao(linha["Retorno anualizado"]),
                    gp.pct_br(linha["Volatilidade anual"]),
                    gp.pct_br(linha["Maior queda"]),
                    _numero(linha["Índice de Sharpe"]),
                ]
            )
            cores.append(
                [None, _cor(linha["Retorno total"], e), _cor(linha["Retorno anualizado"], e),
                 None, e.queda, None]
            )  # fmt: skip
        pdf.tabela(
            [
                "Ativo",
                "Retorno total",
                "Ao ano",
                "Volatilidade",
                "Maior queda",
                "Sharpe",
            ],
            linhas,
            [34, 30, 26, 28, 28, 28],
            cores,
            tickers=True,
        )

    def base100() -> None:
        secao("base100", "Todos começam em 100 no primeiro dia em comum.", reservar=75)
        base_100 = rebasear_para_100(alinhado)
        pdf.imagem(
            gp.grafico_de_linhas(
                {t: base_100[t] for t in tickers},
                "Quanto R$ 100 viraram em cada ativo (base 100)",
                destaque=tickers[0],
                estilo=e,
            )
        )

    partes = {
        "resumo": resumo,
        "tabela": lado_a_lado,
        "base100": base100,
        "metodologia": lambda: _metodologia(
            pdf,
            secao,
            config,
            gerado_em,
            exemplo,
            periodo,
            alinhado.index,
            [
                ("Ativos", ", ".join(tickers)),
                ("Alinhamento", "só os dias em que todos os ativos negociaram"),
                ("Taxa livre de risco", f"{gp.pct_br(taxa_livre_de_risco, 2)} ao ano"),
            ],
        ),
        "glossario": lambda: _glossario(
            pdf,
            secao,
            [
                "Base 100",
                "Retorno anualizado",
                "Volatilidade",
                "Drawdown",
                "Índice de Sharpe",
            ],
        ),
        "limites": lambda: _limites(
            pdf,
            secao,
            [
                (
                    "Ativos em moedas diferentes (real, dólar) comparam retornos em moedas "
                    "diferentes, a não ser que a conversão para reais esteja ligada no site."
                ),
                "Quem foi melhor neste período pode não ser no próximo.",
            ],
            None,
        ),
    }
    capa = [
        ("Ativos", ", ".join(tickers)),
        ("Período", _intervalo(alinhado.index)),
        ("Pregões em comum", str(len(alinhado))),
        *_rodape_de_dados(exemplo),
        ("Gerado em", f"{gerado_em:%d/%m/%Y %H:%M}"),
    ]
    return _montar(pdf, COMPARACAO, config, capa, partes, ao_avancar)


# --- 3. backtest ----------------------------------------------------------------------------
def _descrever_parametros(nome: str, parametros: dict) -> str:
    estrategia = ESTRATEGIAS[nome]
    valores = {**estrategia.parametros_padrao(), **parametros}
    partes = [f"{p.rotulo}: {valores[p.nome]}" for p in estrategia.parametros]
    return "; ".join(partes) if partes else "sem parâmetros"


def achados_do_backtest(
    estrategia: str, resumo: dict, resumo_ref: dict, operacoes: int, custo: float
) -> list[str]:
    a, b = resumo["Retorno total"], resumo_ref["Retorno total"]
    comparacao = "acima de" if a > b else "abaixo de" if a < b else "igual a"
    achados = [
        f"A estratégia {estrategia} rendeu {_variacao(a)} no período, {comparacao} comprar e "
        f"segurar ({_variacao(b)})"
        + (f": diferença de {_pontos(a, b)}." if a != b else "."),
        (
            f"A maior queda foi de {gp.pct_br(resumo['Maior queda'])}, contra "
            f"{gp.pct_br(resumo_ref['Maior queda'])} de comprar e segurar."
        ),
        f"Foram {operacoes} operações, cada uma pagando {gp.pct_br(custo, 2)} de custo.",
    ]
    exposicao = resumo.get("Exposição média", float("nan"))
    if not pd.isna(exposicao):
        achados.append(
            f"Ficou comprada em {gp.pct_br(exposicao)} do tempo; no resto, o dinheiro "
            "ficou parado (sem render juros na simulação)."
        )
    achados.append(
        "Um resultado do passado não prova que a regra funciona: veja a seção de limites."
    )
    return achados


def _secao_foi_sorte(
    pdf: RelatorioPDF,
    secao: Callable[..., None],
    resultado: Ficha,
    texto_do_contador: str,
) -> None:
    """A ficha "Foi sorte?" (ADR 0037, D1): o veredito em destaque e as cinco perguntas."""
    secao(
        "foi_sorte",
        "Cinco perguntas que separam um padrão de um resultado de sorte. A ficha nunca usa custo "
        "menor que o padrão do app e calcula o imposto simplificado da B3 sobre R$ 10.000.",
        reservar=90,
    )
    veredito = resultado.veredito
    pdf.aviso_destacado(f"{veredito.titulo}. {veredito.texto}")
    for checagem in resultado.checagens:
        pdf.item(
            f"{checagem.situacao.value.capitalize()}: {checagem.pergunta}",
            checagem.explicacao,
        )
    pdf.paragrafo(texto_do_contador, apagado=True)


def relatorio_de_backtest(
    ticker: str,
    dados: pd.DataFrame,
    estrategia: str,
    parametros: dict | None = None,
    custo_por_operacao: float = CUSTO_PADRAO_POR_OPERACAO,
    taxa_livre_de_risco: float = 0.0,
    periodo: str = "",
    gerado_em: datetime | None = None,
    exemplo: bool = False,
    config: Configuracao | None = None,
    ao_avancar: AoAvancar = None,
    tentativas_da_pessoa: int = 1,
    tolerancia_de_queda: float = TOLERANCIA_PADRAO_DE_QUEDA,
) -> bytes:
    """O PDF do backtest; `tentativas_da_pessoa` e `tolerancia_de_queda` alimentam a ficha."""
    config = config or Configuracao()
    e = estilo_pela_chave(config.estilo)
    gerado_em = gerado_em or agora()
    parametros = parametros or {}
    fechamento = dados["Close"]
    _exigir_pregoes(int(fechamento.notna().sum()), MIN_PREGOES)
    pedido_da_ficha = PedidoDaFicha(
        dados=dados,
        estrategia=estrategia,
        parametros=parametros,
        custo_por_operacao=custo_por_operacao,
        capital_inicial=CAPITAL_DO_RELATORIO,
        taxa_livre_de_risco=taxa_livre_de_risco,
        tolerancia_de_queda=tolerancia_de_queda,
        tentativas_da_pessoa=tentativas_da_pessoa,
    )
    resultado = executar_backtest(
        fechamento, gerar_posicao(estrategia, dados, **parametros), custo_por_operacao
    )
    referencia = executar_backtest(
        fechamento, posicao_comprar_e_segurar(dados), custo_por_operacao
    )
    resumo = resumir_desempenho(
        resultado.retorno, resultado.posicao, resultado.operacoes, taxa_livre_de_risco
    )
    resumo_ref = resumir_desempenho(
        referencia.retorno, taxa_livre_de_risco=taxa_livre_de_risco
    )
    operacoes = int(resumo.get("Operações", len(resultado.operacoes)))

    pdf = RelatorioPDF(
        f"Backtest: {estrategia} em {ticker}",
        "E se eu tivesse seguido esta regra de compra e venda?",
        gerado_em,
        e,
    )
    secao = _cabecalho(pdf, BACKTEST)

    def achados() -> None:
        secao("resumo", reservar=50)
        pdf.lista(
            achados_do_backtest(
                estrategia, resumo, resumo_ref, operacoes, custo_por_operacao
            )
        )

    def resultado_() -> None:
        secao(
            "resultado",
            "A decisão de cada dia só vale no dia seguinte (sem olhar o futuro), e cada compra "
            "e venda paga o custo por operação.",
        )
        total = resumo["Retorno total"]
        pdf.cartoes(
            [
                ("Retorno total da estratégia", _variacao(total), _cor(total, e)),
                ("Comprar e segurar", _variacao(resumo_ref["Retorno total"]),
                 _cor(resumo_ref["Retorno total"], e)),
                ("Maior queda", gp.pct_br(resumo["Maior queda"]), e.queda),
                ("Índice de Sharpe", _numero(resumo["Índice de Sharpe"]), None),
                ("Tempo comprado", gp.pct_br(resumo.get("Exposição média", float("nan"))),
                 None),
                ("Operações", str(operacoes), None),
            ]
        )  # fmt: skip

    def curva() -> None:
        secao("curva", reservar=75)
        pdf.imagem(
            gp.grafico_de_linhas(
                {
                    estrategia: resultado.curva_de_capital,
                    "Comprar e segurar": referencia.curva_de_capital,
                },
                "Quanto R$ 1 virou",
                destaque=estrategia,
                estilo=e,
            )
        )

    def tabela() -> None:
        secao("tabela", reservar=8 * 8 + 15)
        metricas = [
            ("Retorno total", True, True),
            ("Retorno anualizado", True, True),
            ("Volatilidade anual", True, False),
            ("Maior queda", True, False),
            ("Índice de Sharpe", False, False),
            ("Índice de Sortino", False, False),
            ("Índice de Calmar", False, False),
        ]
        linhas, cores = [], []
        for nome, em_pct, com_seta in metricas:
            a, b = resumo.get(nome, float("nan")), resumo_ref.get(nome, float("nan"))

            def formatar(
                v: float, em_pct: bool = em_pct, com_seta: bool = com_seta
            ) -> str:
                if com_seta:
                    return _variacao(v)
                return gp.pct_br(v) if em_pct else _numero(v)

            linhas.append([nome, formatar(a), formatar(b)])
            cores.append(
                [
                    None,
                    _cor(a, e) if com_seta else None,
                    _cor(b, e) if com_seta else None,
                ]
            )
        pdf.tabela(
            ["Métrica", estrategia[:28], "Comprar e segurar"],
            linhas,
            [70, 52, 52],
            cores,
        )

    partes = {
        "resumo": achados,
        "resultado": resultado_,
        # só calculada se a seção foi escolhida
        "foi_sorte": lambda: _secao_foi_sorte(
            pdf,
            secao,
            montar_ficha(pedido_da_ficha),
            texto_das_tentativas(tentativas_da_pessoa, ticker, TETO_POR_PESSOA),
        ),
        "curva": curva,
        "tabela": tabela,
        "metodologia": lambda: _metodologia(
            pdf,
            secao,
            config,
            gerado_em,
            exemplo,
            periodo,
            fechamento.index,
            [
                ("Ativo", ticker),
                ("Estratégia", estrategia),
                ("Parâmetros", _descrever_parametros(estrategia, parametros)),
                ("Custo por operação", gp.pct_br(custo_por_operacao, 2)),
                (
                    "Execução",
                    (
                        "a posição decidida com o fechamento de um dia vale a partir do "
                        "dia seguinte (sem olhar o futuro)"
                    ),
                ),
                ("Taxa livre de risco", f"{gp.pct_br(taxa_livre_de_risco, 2)} ao ano"),
            ],
        ),
        "glossario": lambda: _glossario(
            pdf,
            secao,
            [
                "Backtest",
                "Foi sorte?",
                "Comprar e segurar (buy and hold)",
                "Custo de operação",
                "Look-ahead bias",
                "Overfitting (sobreajuste)",
                "Drawdown",
                "Índice de Sharpe",
            ],
        ),
        "limites": lambda: _limites(
            pdf,
            secao,
            [
                (
                    "Na vida real há derrapagem (o preço muda entre a decisão e a ordem) e a "
                    "liquidez pode faltar; a simulação não considera isso."
                )
            ],
            AVISO_DO_BACKTEST,
        ),
    }
    capa = [
        ("Ativo", ticker),
        ("Estratégia", estrategia),
        ("Parâmetros", _descrever_parametros(estrategia, parametros)),
        ("Custo por operação", gp.pct_br(custo_por_operacao, 2)),
        ("Período", _intervalo(fechamento.index)),
        *_rodape_de_dados(exemplo),
    ]
    return _montar(pdf, BACKTEST, config, capa, partes, ao_avancar)


# --- 4. carteira ----------------------------------------------------------------------------
def achados_da_carteira(
    estrategia: str, resumo: dict, resumo_ref: dict | None, giro: float, ativos: int
) -> list[str]:
    total = resumo["Retorno total"]
    achados = [
        (
            f"A carteira {estrategia} com {ativos} ativos rendeu {_variacao(total)} no período "
            f"({_variacao(resumo['Retorno anualizado'])} ao ano)."
        ),
        (
            f"A volatilidade foi de {gp.pct_br(resumo['Volatilidade anual'])} ao ano e a maior "
            f"queda, de {gp.pct_br(resumo['Maior queda'])}."
        ),
    ]
    if resumo_ref is not None:
        ref = resumo_ref["Retorno total"]
        lado = "acima" if total > ref else "abaixo" if total < ref else "no mesmo nível"
        achados.append(
            f"Ficou {lado} da carteira de pesos iguais ({_variacao(ref)})"
            + (f", diferença de {_pontos(total, ref)}." if total != ref else ".")
        )
    achados.append(
        f"O giro foi de {gp.numero_br(giro, 1)} vezes o capital: quanto maior, mais custo."
    )
    return achados


def relatorio_de_carteira(
    fechamentos: pd.DataFrame,
    estrategia: str,
    parametros: dict | None = None,
    custo_por_operacao: float = CUSTO_PADRAO_POR_OPERACAO,
    taxa_livre_de_risco: float = 0.0,
    periodo: str = "",
    gerado_em: datetime | None = None,
    exemplo: bool = False,
    config: Configuracao | None = None,
    ao_avancar: AoAvancar = None,
) -> bytes:
    """`fechamentos`: um ativo por coluna, nos mesmos dias."""
    config = config or Configuracao()
    e = estilo_pela_chave(config.estilo)
    gerado_em = gerado_em or agora()
    parametros = parametros or {}
    _exigir_pregoes(len(fechamentos.dropna()), MIN_DIAS_NA_CARTEIRA, EM_COMUM)
    tickers = list(fechamentos.columns)
    resultado = simular_carteira(
        estrategia, fechamentos, custo_por_operacao, **parametros
    )
    referencia_nome = next(iter(ESTRATEGIAS_DE_CARTEIRA))  # pesos iguais
    referencia = simular_carteira(referencia_nome, fechamentos, custo_por_operacao)
    resumo = resumir_desempenho(
        resultado.retorno, taxa_livre_de_risco=taxa_livre_de_risco
    )
    resumo_ref = (
        resumir_desempenho(referencia.retorno, taxa_livre_de_risco=taxa_livre_de_risco)
        if estrategia != referencia_nome
        else None
    )

    pdf = RelatorioPDF(
        f"Carteira: {estrategia}",
        f"{len(tickers)} ativos: " + ", ".join(tickers),
        gerado_em,
        e,
    )
    secao = _cabecalho(pdf, CARTEIRA)

    def achados() -> None:
        secao("resumo", reservar=50)
        pdf.lista(
            achados_da_carteira(
                estrategia, resumo, resumo_ref, resultado.giro, len(tickers)
            )
        )

    def resultado_() -> None:
        secao(
            "resultado",
            "Os pesos são decididos com o que se sabia até o dia da decisão e rebalanceados "
            "com custo.",
        )
        total = resumo["Retorno total"]
        pdf.cartoes(
            [
                ("Retorno total da carteira", _variacao(total), _cor(total, e)),
                ("Retorno anualizado", _variacao(resumo["Retorno anualizado"]),
                 _cor(resumo["Retorno anualizado"], e)),
                ("Volatilidade anual", gp.pct_br(resumo["Volatilidade anual"]), None),
                ("Maior queda", gp.pct_br(resumo["Maior queda"]), e.queda),
                ("Índice de Sharpe", _numero(resumo["Índice de Sharpe"]), None),
                ("Giro (compras + vendas)",
                 f"{gp.numero_br(resultado.giro, 1)}× o capital", None),
            ]
        )  # fmt: skip

    def curva() -> None:
        secao("curva", reservar=75)
        curvas = {estrategia: resultado.curva_de_capital}
        if estrategia != referencia_nome:
            curvas["Pesos iguais"] = referencia.curva_de_capital
        pdf.imagem(
            gp.grafico_de_linhas(
                curvas, "Quanto R$ 1 virou", destaque=estrategia, estilo=e
            )
        )

    def pesos() -> None:
        secao("pesos", reservar=75)
        pdf.imagem(gp.grafico_de_pesos(resultado.pesos, estilo=e))

    def ativos() -> None:
        secao(
            "ativos",
            "Para comparar: os ativos da carteira, cada um por conta.",
            reservar=8 * (len(tickers) + 1) + 15,
        )
        tabela = montar_tabela_comparativa(fechamentos.dropna(), taxa_livre_de_risco)
        linhas = [
            [str(t), _variacao(l["Retorno total"]), gp.pct_br(l["Volatilidade anual"]),
             gp.pct_br(l["Maior queda"]), _numero(l["Índice de Sharpe"])]
            for t, l in tabela.iterrows()
        ]  # fmt: skip
        cores = [[None, _cor(l["Retorno total"], e), None, e.queda, None]
                 for _, l in tabela.iterrows()]  # fmt: skip
        pdf.tabela(
            ["Ativo", "Retorno total", "Volatilidade", "Maior queda", "Sharpe"],
            linhas,
            [38, 36, 34, 32, 34],
            cores,
            tickers=True,
        )

    partes = {
        "resumo": achados,
        "resultado": resultado_,
        "curva": curva,
        "pesos": pesos,
        "ativos": ativos,
        "metodologia": lambda: _metodologia(
            pdf,
            secao,
            config,
            gerado_em,
            exemplo,
            periodo,
            fechamentos.index,
            [
                ("Ativos", ", ".join(tickers)),
                ("Estratégia", estrategia),
                ("Custo por operação", gp.pct_br(custo_por_operacao, 2)),
                ("Pesos", "decididos com o que se sabia até o dia da decisão"),
                ("Taxa livre de risco", f"{gp.pct_br(taxa_livre_de_risco, 2)} ao ano"),
            ],
        ),
        "glossario": lambda: _glossario(
            pdf,
            secao,
            [
                "Diversificação",
                "Rebalanceamento",
                "Custo de operação",
                "Drawdown",
                "Índice de Sharpe",
            ],
        ),
        "limites": lambda: _limites(
            pdf,
            secao,
            [
                (
                    "A escolha dos ativos foi feita hoje, olhando para trás: ativos que quebraram "
                    "ou saíram da bolsa não aparecem (viés de sobrevivência)."
                )
            ],
            None,
        ),
    }
    capa = [
        ("Ativos", ", ".join(tickers)),
        ("Estratégia", estrategia),
        ("Custo por operação", gp.pct_br(custo_por_operacao, 2)),
        ("Período", _intervalo(fechamentos.index)),
        *_rodape_de_dados(exemplo),
    ]
    return _montar(pdf, CARTEIRA, config, capa, partes, ao_avancar)


# --- 5. minha carteira (arquivo da Área do Investidor da B3) ---------------------------------
def achados_da_minha_carteira(
    pesos: pd.Series, efetivo: float, resumo: dict, retorno_ibov: float | None
) -> list[str]:
    achados = []
    if len(pesos):
        maior = pesos.idxmax().removesuffix(".SA")
        achados.append(
            f"A maior posição é {maior}, com {gp.pct_br(pesos.max())} do valor em ativos "
            f"com cotação; as 3 maiores somam {gp.pct_br(pesos.nlargest(3).sum())}."
        )
        achados.append(
            f"Com {len(pesos)} ativos, a concentração equivale a "
            f"{gp.numero_br(efetivo, 1)} ativos de mesmo peso (número efetivo)."
        )
    ret = resumo["Retorno total"]
    frase = (
        f"Com os pesos de hoje, a carteira teria variado {_variacao(ret)} no período"
    )
    if retorno_ibov is not None and not pd.isna(retorno_ibov):
        frase += f", contra {_variacao(retorno_ibov)} do Ibovespa"
    achados.append(frase + ".")
    achados.append(
        f"A maior queda dessa carteira no período teria sido de "
        f"{gp.pct_br(resumo['Maior queda'])}."
    )
    achados.append(
        "Não é o seu resultado real: as datas e preços de compra não entram."
    )
    return achados


def relatorio_da_minha_carteira(
    carteira: CarteiraB3,
    fechamentos: pd.DataFrame,
    referencia: pd.Series | None = None,
    taxa_livre_de_risco: float = 0.0,
    periodo: str = "",
    gerado_em: datetime | None = None,
    exemplo: bool = False,
    config: Configuracao | None = None,
    ao_avancar: AoAvancar = None,
    demonstracao: bool = False,
) -> bytes:
    """`fechamentos`: um ativo da carteira por coluna (tickers com .SA); `referencia`: o Ibovespa.

    `demonstracao`: a carteira é a fictícia de exemplo; o PDF diz isso na capa e no subtítulo
    de todas as páginas (blueprint: dado de demonstração sempre rotulado)."""
    config = config or Configuracao()
    e = estilo_pela_chave(config.estilo)
    gerado_em = gerado_em or agora()
    _exigir_pregoes(len(fechamentos.dropna(how="all")), MIN_PREGOES)
    pesos = carteira.pesos()
    total = carteira.valor_total
    efetivo = numero_efetivo_de_ativos(pesos)
    retorno = retorno_com_os_pesos_de_hoje(fechamentos, pesos)
    resumo = resumir_desempenho(retorno, taxa_livre_de_risco=taxa_livre_de_risco)
    curvas = {"Minha carteira": (1 + retorno).cumprod() * 100}
    retorno_ibov = None
    if referencia is not None and not referencia.dropna().empty:
        ref = referencia.reindex(retorno.index).ffill().dropna()
        if len(ref) > 1:
            curvas["Ibovespa"] = ref / ref.iloc[0] * 100
            retorno_ibov = float(ref.iloc[-1] / ref.iloc[0] - 1)
    indice = fechamentos.dropna(how="all").index

    pdf = RelatorioPDF(
        "Carteira de exemplo (fictícia)" if demonstracao else "Minha carteira",
        "EXEMPLO DEMONSTRATIVO: carteira fictícia, para conhecer o relatório"
        if demonstracao
        else "A sua posição na B3: composição, concentração, risco e como ela se comportou",
        gerado_em,
        e,
    )
    secao = _cabecalho(pdf, MINHA_CARTEIRA)

    def achados() -> None:
        secao("resumo", reservar=50)
        pdf.lista(achados_da_minha_carteira(pesos, efetivo, resumo, retorno_ibov))

    def composicao() -> None:
        secao(
            "composicao",
            "Pelo valor de hoje de cada posição (ativos com cotação na bolsa).",
        )
        maior = pesos.max() if len(pesos) else float("nan")
        tres = pesos.nlargest(3).sum() if len(pesos) else float("nan")
        pdf.cartoes(
            [
                ("Maior posição", f"{pesos.idxmax().removesuffix('.SA')}: {gp.pct_br(maior)}"
                 if len(pesos) else "—", None),
                ("3 maiores juntas", gp.pct_br(tres), None),
                ("Número efetivo de ativos", gp.numero_br(efetivo, 1), None),
                ("Tesouro e renda fixa",
                 gp.pct_br(carteira.sem_cotacao["valor"].sum() / total) if total else "—",
                 None),
            ]
        )  # fmt: skip
        if len(pesos):
            pdf.imagem(
                gp.grafico_de_composicao(
                    pesos.rename(lambda t: t.removesuffix(".SA")), estilo=e
                )
            )
        pdf.paragrafo(
            f"O número efetivo de ativos ({gp.numero_br(efetivo, 1)}) diz quantos ativos de "
            f"mesmo peso dariam a mesma concentração. Com {len(pesos)} ativos, quanto mais "
            f"perto de {len(pesos)}, mais dividido está o dinheiro.",
            apagado=True,
        )

    def comportamento() -> None:
        secao("comportamento", reservar=40)
        pdf.aviso_destacado(AVISO_DA_MINHA_CARTEIRA)
        ret = resumo["Retorno total"]
        pdf.cartoes(
            [
                ("Retorno no período", _variacao(ret), _cor(ret, e)),
                ("Ao ano", _variacao(resumo["Retorno anualizado"]),
                 _cor(resumo["Retorno anualizado"], e)),
                ("Volatilidade anual", gp.pct_br(resumo["Volatilidade anual"]), None),
                ("Maior queda", gp.pct_br(resumo["Maior queda"]), e.queda),
                ("Índice de Sharpe", _numero(resumo["Índice de Sharpe"]), None),
            ]
        )  # fmt: skip
        pdf.imagem(
            gp.grafico_de_linhas(
                curvas, "Base 100: a carteira de hoje no passado",
                destaque="Minha carteira", estilo=e,
            )
        )  # fmt: skip

    def cada_ativo() -> None:
        secao(
            "ativos",
            "O valor e o peso de hoje, e como cada um se comportou no período.",
            reservar=8 * (len(pesos) + 1) + 15,
        )
        tabela = montar_tabela_comparativa(fechamentos.dropna(), taxa_livre_de_risco)
        linhas, cores = [], []
        for _, p in carteira.posicoes.iterrows():
            dados = tabela.loc[p["ticker"]] if p["ticker"] in tabela.index else None
            r = dados["Retorno total"] if dados is not None else float("nan")
            linhas.append(
                [
                    p["codigo"],
                    p["tipo"][:14],
                    f"R$ {gp.numero_br(p['valor'])}",
                    gp.pct_br(pesos.get(p["ticker"], float("nan"))),
                    _variacao(r),
                    gp.pct_br(dados["Maior queda"]) if dados is not None else "—",
                ]
            )
            cores.append([None, None, None, None, _cor(r, e), e.queda])
        pdf.tabela(
            ["Ativo", "Tipo", "Valor", "Peso", "Retorno", "Maior queda"],
            linhas,
            [24, 34, 34, 22, 30, 30],
            cores,
            tickers=True,
        )
        if carteira.avisos:
            pdf.paragrafo(
                "Avisos da leitura do arquivo: " + " ".join(carteira.avisos),
                apagado=True,
            )

    partes = {
        "resumo": achados,
        "composicao": composicao,
        "comportamento": comportamento,
        "ativos": cada_ativo,
        "metodologia": lambda: _metodologia(
            pdf,
            secao,
            config,
            gerado_em,
            exemplo,
            periodo,
            indice,
            [
                (
                    "Posição",
                    (
                        "arquivo da Área do Investidor da B3, lido só na memória (não fica "
                        "guardado)"
                    ),
                ),
                (
                    "Pesos",
                    "valor de hoje de cada posição com cotação, mantidos fixos no período",
                ),
                ("Comparação", "Ibovespa (^BVSP), quando disponível"),
            ],
        ),
        "glossario": lambda: _glossario(
            pdf,
            secao,
            [
                "Diversificação",
                "Retorno anualizado",
                "Volatilidade",
                "Drawdown",
                "Índice de Sharpe",
                "Base 100",
            ],
        ),
        "limites": lambda: _limites(
            pdf,
            secao,
            [
                (
                    "Tesouro Direto e renda fixa não têm cotação diária aqui e ficam fora da "
                    "análise de risco."
                )
            ],
            AVISO_DA_MINHA_CARTEIRA,
        ),
    }
    capa = [
        ("Ativos com cotação", str(len(carteira.posicoes))),
        ("Tesouro e renda fixa", str(len(carteira.sem_cotacao))),
        ("Valor total (posição)", f"R$ {gp.numero_br(total)}"),
        ("Período analisado", _intervalo(indice)),
        (
            "Fonte da posição",
            "carteira FICTÍCIA de exemplo (demonstração)"
            if demonstracao
            else "arquivo da Área do Investidor da B3",
        ),
        ("Gerado em", f"{gerado_em:%d/%m/%Y %H:%M}"),
    ]
    return _montar(pdf, MINHA_CARTEIRA, config, capa, partes, ao_avancar)
