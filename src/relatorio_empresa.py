"""Relatório completo de empresa (série 2 da base de ML, PR 7; ADR 0032, itens 5 a 8).

Uma estrutura de seções em tipos simples (ADR 0044): a página, o PDF e a futura API leem a mesma
coisa, então os números são os mesmos nos três. Cada número traz de quando é (a base) e, quando falta,
por quê; as notas da ADR 0033 vêm ao lado, com o padrão e o aviso; o selo de qualidade aparece quando
há achado aberto. Junta o que já existe: indicadores da tela (`src/fundamentos.py`), os cálculos novos
(`src/fundamentalista.py`), as notas clássicas, os padrões e as notas, o valuation e o FRE.

As seções do dossiê da base (auditor, ofertas, setor regulado, negócios; plano do dossiê da empresa no
app, 17/10/2026) entram no lugar delas na ordem do molde A (relatórios v2, `ORDEM_DAS_SECOES`) e são
**trancadas aqui, no servidor**: quem não é Pro recebe só os títulos e o convite, sem nenhum número, na
página, no PDF e na API. A ordem é decidida aqui; os desenhos (PDF, página, React) só a seguem.

Premissas padrão do valuation (a pessoa troca na página): desconto de 12% ao ano, perpetuidade de 3%,
10 anos de projeção e crescimento de 5% no DCF. São um ponto de partida declarado, não uma opinião.
"""

import math
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field, replace
from datetime import date, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from src import fundamentalista, fundamentos, notas, notas_classicas, valuation
from src import o_que_os_dados_mostram as leitura_da_ficha
from src.analise_escrita.modelo_da_tela import AnaliseDaTela
from src.banco.coletas import MOSTRAR, citacoes_das_fontes, exigir_licenca
from src.banco.demonstracoes import DadosDaEmpresa
from src.metodologia_das_notas import URL_NO_SITE as URL_DA_METODOLOGIA
from src.negociacoes import formatar_valor
from src.numero import Comparacao, Numero
from src.padroes import INDICADORES, MULTIPLOS
from src.planos import DOSSIE_DA_BASE, motivo_sem_acesso
from src.qualidade_texto import texto_do_selo
from src.rastro import DocumentoUsado, Metrica, Rastro
from src.setores import NOMES, SEM_GRUPO, grupo_do_setor, grupo_para_comparar

# as seções na ordem do molde A (relatórios v2): quem é, o que os dados mostram e o que mudou no
# topo; as contas e a qualidade delas; capital, setor e acontecimentos; as notas, o valuation e o
# histórico; o que mudaria a leitura, a metodologia e os limites no fim
SECOES: dict[str, str] = {
    "ficha_tecnica": "Ficha técnica",
    "o_que_os_dados_mostram": "O que os dados mostram",
    "o_que_mudou": "O que mudou desde o balanço anterior",
    "resultado": "Resultado",
    "retorno": "Retorno",
    "endividamento": "Endividamento",
    "caixa": "Caixa e capital de giro",
    "qualidade": "Qualidade dos dados",
    "dividendos": "Dividendos e diluição",
    "pares": "Pares do mesmo setor",
    "eventos": "Acontecimentos recentes",
    "notas_classicas": "Notas clássicas",
    "padroes_e_notas": "Notas contra o setor",
    "valuation": "Valuation",
    "historico": "Histórico de até 10 anos",
    "o_que_mudaria": "O que mudaria esta leitura",
    "metodologia": "Metodologia e fontes",
    "limites": "Limites e perguntas em aberto",
}
# onde entram as seções do dossiê da base (`base/dossie.py`), entre as do relatório
ORDEM_DAS_SECOES = (
    *list(SECOES)[: list(SECOES).index("endividamento") + 1],
    "credito",  # a dívida e o crédito
    "caixa",
    "geracao_de_caixa",  # EBITDA, capex e FCF da DFP (série T1)
    "qualidade",
    "qualidade_do_lucro",  # as contas e a qualidade delas
    "dividendos",
    "ofertas_e_fundos",
    "capital_e_acionistas",  # capital e acionistas
    "auditor_e_controladas",
    "governanca",  # governança
    "pares",
    "setor_regulado",  # setor e pares
    "eventos",
    "negocios",  # negócios e acontecimentos
    *list(SECOES)[list(SECOES).index("notas_classicas") :],
)
# uma seção nova da base, que a ordem ainda não conhece, vai com os negócios e acontecimentos
POSICAO_DA_SECAO_NOVA = ORDEM_DAS_SECOES.index("negocios") + 0.5
CHAVES_DAS_SECOES = {
    "resultado": ("receita", "lucro", "margem_bruta", "margem_ebit", "margem_liquida",
                  "crescimento_receita", "crescimento_lucro"),
    "retorno": ("roe", "roic", "dupont_margem", "dupont_giro", "dupont_alavancagem"),
    "endividamento": ("divida_bruta", "caixa", "divida_liquida", "divida_sobre_pl",
                      "cobertura_de_juros"),
    "caixa": ("conversao_de_caixa", "caixa_livre", "capex", "capex_sobre_depreciacao", "pmr",
              "pme", "pmp", "ciclo_de_caixa"),
}  # fmt: skip
INDICADORES_DO_QUE_MUDOU = (
    "receita",
    "lucro",
    "margem_liquida",
    "roe",
    "divida_sobre_pl",
)
# o sentido de cada indicador do "o que mudou" (os de fora do padrão do setor: maior é melhor)
MAIOR_E_MELHOR = {chave: maior for chave, (_, maior) in INDICADORES.items()}
QUANTOS_PARES = 5
AINDA_SEM_DADO = (
    "ainda sem dado"  # o par ainda não tem a geração de caixa na ficha da noite
)
SOBRE_O_CAIXA_DOS_PARES = (
    "Margem EBITDA e FCF do último exercício (DFP) de cada par, da geração de caixa da ficha dele; "
    f'"{AINDA_SEM_DADO}" quando a ficha ainda não tem a DFC ou a linha.'
)
ROTULOS_DAS_COLUNAS = {  # o cabeçalho que a regra geral (`rotulo_da_coluna`) escreveria errado
    "margem_ebitda": "Margem EBITDA",
    "fcf": "FCF",
    "exercicio_do_caixa": "Exercício da margem e do FCF",
}
NOMES_DAS_TABELAS = {  # o título de cada tabela, igual na página e no PDF
    "datas_das_fontes": "Última data de cada fonte",
    "gatilhos": "O valor que mudaria cada nota",
    "cascata": "Da receita ao lucro (último ano)",
    "ponte": "Da dívida líquida do ano anterior à de agora",
    "sensibilidade": "Valor por ação conforme o desconto e o crescimento",
    "historico": "Ano a ano",
    "contas": "Contas ano a ano",
    "vertical": "Análise vertical (cada conta sobre a receita ou o ativo)",
    "eventos": "Acontecimentos recentes",
    "indicadores": "Antes e agora",
    "pares": "Empresas parecidas",
    "piotroski": "Parcelas do Piotroski",
    "altman": "Parcelas do Altman Z''",
    "beneish": "Parcelas do Beneish",
}
MIL = 1_000  # daqui para cima, a célula é dinheiro (R$ mil, mi, bi)
QUANTOS_EVENTOS = 15
FONTES = ("CVM: dados abertos de DFP, ITR, FRE, cadastro e eventos do IPE (ODbL)",)
# as fontes em `src/banco/coletas.py` que a ficha usa: a CVM sempre; o Yahoo quando há preço (os
# múltiplos, o histórico deles e o P/L e P/VP dos padrões setoriais). A citação do Yahoo vem da
# lista dos usos sem cobrança (ADR 0008, Emenda 3), e a trava barra a ficha se ele sair dela.
FONTE_DA_CVM = "cvm"
FONTE_DO_PRECO = "yahoo"
ONDE_A_TRAVA_BARRA = "relatório da empresa"
LIMITES = (
    (
        "Nada aqui é recomendação de compra ou venda. As notas comparam números com os de empresas "
        "parecidas por regras públicas; não dizem o que vai acontecer."
    ),
    (
        "Os números vêm do que a empresa entregou à CVM e podem ser reapresentados depois; o selo de "
        "qualidade mostra os que pediram uma segunda olhada."
    ),
    (
        "O valuation depende das premissas: mudar o desconto ou o crescimento muda o resultado. O "
        "TickerLab não dá preço-alvo."
    ),
    "Bancos e seguradoras têm outro plano de contas: vários indicadores não se aplicam a eles.",
    (
        "O que a base ainda não tem: protestos em cartório, processos na Justiça (além dos que a "
        "empresa declara nos documentos à CVM) e atrasos de pagamentos a fornecedores e bancos. Esta "
        "ficha não diz nada sobre eles; não aparecer aqui não quer dizer que não existam."
    ),
)
EM_ABERTO = "Em aberto:"  # o começo de cada pergunta que a ficha não respondeu
CONVITE_DO_DOSSIE = (
    "Com ele, esta seção mostra o que a base do TickerLab reuniu da companhia nos dados abertos da "
    "CVM e das agências reguladoras, com a fonte de cada número."
)
# de onde vem cada número (o contrato do número, `src/numero.py`)
FONTE_DAS_DEMONSTRACOES = "DFP e ITR entregues à CVM (demonstrações consolidadas)"
FONTE_DOS_MULTIPLOS = "preço da ação (Yahoo Finance) e DFP e ITR entregues à CVM"
FONTE_DAS_ACOES = "DFP entregues à CVM (fluxo de caixa e composição do capital)"
SEM_O_ANTERIOR = "O balanço anterior guardado não tem este número para comparar."
# os múltiplos de mercado além de P/L e P/VP (D3 mudada em 20/10/2026); o DY fica nos dividendos
MULTIPLOS_DE_MERCADO = tuple(m for m in fundamentos.DE_MERCADO if m != "dividend_yield")
COMO_SAI_O_DY = (
    "Dividend yield: dividendos e JCP pagos em caixa nos últimos 12 meses (fluxo de caixa da "
    "DFP e do ITR), divididos pelo valor de mercado de hoje. O caixa pago pode incluir o que as "
    "controladas pagaram aos acionistas minoritários delas, e o mesmo preço vale para todas as "
    "classes de ação."
)
SEM_DILUICAO = (
    "Sem dois anos de ações em circulação, ou com um salto sem desdobramento explicado."
)


def _dec(valor: float) -> str:
    return f"{valor:.2f}".replace(".", ",").replace("-", "−")


ESCALAS_DO_ARTIGO = {
    "altman": (
        f"segura acima de {_dec(notas_classicas.ALTMAN_SEGURA)}; aflição abaixo de "
        f"{_dec(notas_classicas.ALTMAN_AFLICAO)}; cinzenta entre as duas"
    ),
    "beneish": (
        f"limite de {_dec(notas_classicas.BENEISH_LIMITE)}: acima dele, o artigo separa o caso "
        "para uma segunda olhada"
    ),
    "piotroski": (
        f"de 0 a 9 pontos; o artigo compara as empresas com {notas_classicas.PIOTROSKI_ALTO} ou "
        f"mais com as de {notas_classicas.PIOTROSKI_BAIXO} ou menos"
    ),
}


@dataclass(frozen=True)
class Premissas:
    desconto: float = 0.12
    perpetuidade: float = 0.03
    anos: int = 10
    crescimento: float = 0.05


@dataclass(frozen=True)
class Item:
    chave: str
    nome: str
    texto: str  # o número já escrito ("R$ 12,3 bi", "18,5%")
    valor: float | None
    unidade: str
    base: str
    motivo: str = ""
    nota: str | None = None
    nota_texto: str = ""
    fonte: str = ""  # de onde veio (o contrato do número, `src/numero.py`)
    comparacao: Comparacao | None = None
    sem_comparacao: str = ""  # por que não há com o quê comparar
    rastro: Rastro | None = None  # como foi calculado e de onde veio (`src/rastro.py`)

    @property
    def numero(self) -> Numero:
        return Numero(
            self.valor, self.base, self.fonte, self.comparacao, self.sem_comparacao
        )


@dataclass(frozen=True)
class Secao:
    chave: str
    titulo: str
    itens: list[Item] = field(default_factory=list)
    paragrafos: list[str] = field(default_factory=list)
    tabelas: dict[str, list[dict]] = field(default_factory=dict)
    pontos: list[leitura_da_ficha.Ponto] = field(
        default_factory=list
    )  # o que os dados mostram
    trancada: bool = False  # só o título e o convite: o plano não inclui a seção
    recolhida: bool = False  # explicação: a tela mostra fechada (o PDF, por inteiro)


@dataclass(frozen=True)
class Dossie:
    """As seções do dossiê da base (a ficha da noite, de `src/dossie.py`), antes da tranca do plano."""

    secoes: list[Secao]
    fontes: tuple[str, ...]
    limites: list[str]
    dia: date
    velha: bool  # a ficha não chegou nas últimas noites


@dataclass(frozen=True)
class Relatorio:
    empresa: str
    cnpj: str
    ticker: str
    setor: str
    grupo: str
    secoes: list[Secao]
    fontes: tuple[str, ...]
    aviso_das_notas: str
    em_conferencia: bool
    analise: AnaliseDaTela | None = None  # a análise escrita, quando há texto aprovado

    def secao(self, chave: str) -> Secao:
        return next(s for s in self.secoes if s.chave == chave)

    def como_dict(self) -> dict:
        """Para a API: datas em texto ISO e números que faltam como None."""
        return para_json(asdict(self))

    def metricas(self) -> list[Metrica]:
        """Cada número com rastro como dado (o `Metric` do `data_model.md`), sem as seções
        trancadas: quem não tem o plano não recebe o número por aqui também."""
        return [
            Metrica(
                self.cnpj,
                i.chave,
                i.nome,
                i.valor,
                i.unidade,
                i.base,
                i.rastro,
                i.motivo,
            )
            for s in self.secoes
            if not s.trancada
            for i in s.itens
            if i.rastro is not None
        ]


@dataclass(frozen=True)
class Entradas:
    dados: DadosDaEmpresa
    cnpj: str
    empresa: str
    ticker: str
    preco: float | None = None
    fechamentos: pd.Series | None = None
    padroes: tuple[date, pd.DataFrame] | None = None  # (corte, padrões) de `padroes_em`
    achados: list = field(default_factory=list)  # achados abertos (`achados_de`)
    eventos: pd.DataFrame | None = None  # publicado_em, rotulo, assunto, link
    proventos: pd.DataFrame | None = None  # do FRE
    eventos_de_capital: pd.DataFrame | None = None  # do FRE
    pares: pd.DataFrame | None = None  # cnpj, empresa, receita (do mesmo grupo)
    # a geração de caixa de um par pela ficha da noite dele (`src.dossie.caixa_do_par`)
    caixa_do_par: Callable[[str], dict | None] | None = None
    dossie: Dossie | None = None  # a ficha da base do CNPJ (`src/dossie.py`)
    tickers: pd.DataFrame | None = (
        None  # codigo, valor_mobiliario, atualizado_em (do FCA)
    )
    premissas: Premissas = field(default_factory=Premissas)


# --- números escritos ------------------------------------------------------------------------------
def para_json(valor: object) -> object:
    if isinstance(valor, dict):
        return {str(k): para_json(v) for k, v in valor.items()}
    if isinstance(valor, list | tuple):
        return [para_json(v) for v in valor]
    if isinstance(valor, date | pd.Timestamp):
        return valor.isoformat()
    if isinstance(valor, float) and not math.isfinite(valor):
        return None
    return valor


def escrever(valor: float | None, unidade: str) -> str:
    if valor is None or (isinstance(valor, float) and not math.isfinite(valor)):
        return "—"
    if unidade == fundamentos.REAIS:
        return formatar_valor(valor, "BRL")
    if unidade == fundamentos.FRACAO:
        return f"{valor * 100:.1f}%".replace(".", ",")
    if unidade == fundamentos.REAIS_POR_ACAO:
        return f"R$ {valor:.2f}".replace(".", ",")
    if unidade == fundamentalista.DIAS:
        return f"{valor:.0f} dias"
    return f"{valor:.2f}×".replace(".", ",")


def nome_da_tabela(chave: str) -> str:
    return NOMES_DAS_TABELAS.get(chave, rotulo_da_coluna(chave))


def rotulo_da_coluna(coluna: str) -> str:
    """`dividendo_total` → "Dividendo total" (cabeçalho das tabelas); siglas e acentos pelo mapa."""
    if coluna in ROTULOS_DAS_COLUNAS:
        return ROTULOS_DAS_COLUNAS[coluna]
    return str(coluna).replace("_", " ").capitalize()


def escrever_celula(valor: object) -> str:
    """Uma célula das tabelas do relatório, igual na página e no PDF (valores em reais acima de
    mil viram "R$ 1,2 bi"; frações e contagens ficam com duas casas)."""
    if valor is None or (isinstance(valor, float) and not math.isfinite(valor)):
        return "—"
    if isinstance(valor, bool):
        return "sim" if valor else "não"
    if isinstance(valor, int | float):
        if abs(valor) >= MIL:
            return formatar_valor(float(valor), "BRL")
        return f"{valor:.2f}".replace(".", ",")
    return str(valor)


def _pct(fracao: float) -> str:
    return escrever(fracao, fundamentos.FRACAO)


def _o_setor(grupo: str, empresas: int, corte: date) -> str:
    return f"setor {NOMES.get(grupo, grupo)} ({empresas} empresas, corte de {corte:%d/%m/%Y})"


def _contra_o_setor(nota: notas.Nota, unidade: str) -> Comparacao:
    p = nota.percentis
    return Comparacao(
        _o_setor(nota.grupo, nota.empresas, nota.data_de_corte),
        f"mediana {escrever(p['50'], unidade)}; metade entre {escrever(p['25'], unidade)} e "
        f"{escrever(p['75'], unidade)}",
    )


def _contra_a_faixa(chave: str) -> Comparacao:
    f = notas.FAIXAS_FIXAS[chave]
    baixo, alto = escrever(f.abaixo_de, f.unidade), escrever(f.ate, f.unidade)
    return Comparacao(
        "faixa fixa e pública do TickerLab",
        f"{f.notas[1]} de {baixo} a {alto}; abaixo, {f.notas[0]}; acima, {f.notas[2]}",
    )


def _contra_o_anterior(chave: str, unidade: str, c: "_Calculos") -> Comparacao | None:
    antes = c.anterior.get(chave)
    if c.data_anterior is None or antes is None or antes.valor is None:
        return None
    return Comparacao(
        f"balanço de {c.data_anterior:%d/%m/%Y}",
        f"era {escrever(antes.valor, unidade)}",
        antes.valor,
    )


# --- o rastro de cada número (`src/rastro.py`) -----------------------------------------------------
CALCULO_DOS_FUNDAMENTOS = f"fundamentos {fundamentos.VERSAO_DOS_FUNDAMENTOS}"
CALCULO_DO_FUNDAMENTALISTA = (
    f"fundamentalista {fundamentalista.VERSAO_DO_FUNDAMENTALISTA}"
)
CALCULO_DAS_NOTAS_CLASSICAS = (
    f"notas clássicas {notas_classicas.VERSAO_DAS_NOTAS_CLASSICAS}"
)
CRESCIMENTOS = ("crescimento_receita", "crescimento_lucro")
# quantos exercícios cada nota clássica lê: o Altman só o último; as outras comparam com o anterior
ANOS_DAS_NOTAS_CLASSICAS = {"piotroski": 2, "altman": 1, "beneish": 2}


def _ultimas_versoes(documentos: pd.DataFrame) -> list[pd.Series]:
    """Uma linha por demonstração: a versão mais recente, que é a dos números guardados."""
    if documentos.empty:
        return []
    ultimas = documentos.sort_values(["referencia", "versao"]).drop_duplicates(
        ["documento", "referencia"], keep="last"
    )
    return [linha for _, linha in ultimas.iterrows()]


def _documento(linha: pd.Series) -> DocumentoUsado:  # uma linha de `_ultimas_versoes`
    link = linha["link"]
    return DocumentoUsado(
        f"{linha['documento']} de {_dia(linha['referencia']):%d/%m/%Y}, "
        f"versão {int(linha['versao'])}",
        _dia(linha["recebido_em"]),
        link if isinstance(link, str) else "",
    )


def documentos_usados(documentos: pd.DataFrame) -> tuple[DocumentoUsado, ...]:
    """Os documentos da CVM, com o dia em que a CVM os recebeu e o link do original."""
    return tuple(_documento(linha) for linha in _ultimas_versoes(documentos))


def _dfps_por_ano(documentos: pd.DataFrame) -> dict[int, DocumentoUsado]:
    dfps = (
        documentos[documentos["documento"] == "DFP"]
        if not documentos.empty
        else documentos
    )
    return {
        _dia(linha["referencia"]).year: _documento(linha)
        for linha in _ultimas_versoes(dfps)
    }


def _fechamento(e: "Entradas") -> DocumentoUsado:
    """O preço usado: o último fechamento guardado (sem a série, o dia não é conhecido)."""
    dia = (
        _dia(e.fechamentos.index.max())
        if e.fechamentos is not None and not e.fechamentos.empty
        else None
    )
    return DocumentoUsado(f"fechamento de {e.ticker} (Yahoo Finance)", dia)


def _dfps(c: "_Calculos", anos: Iterable[int]) -> tuple[DocumentoUsado, ...]:
    return tuple(c.dfps[ano] for ano in sorted(anos) if ano in c.dfps)


def _ultimos_anos(c: "_Calculos", quantos: int) -> range:
    ultimo = max(c.dfps, default=0)
    return range(ultimo - quantos + 1, ultimo + 1)


def _rastro(chave: str, c: "_Calculos") -> Rastro:
    """O rastro de um indicador da tela (`fundamentos`) ou dos novos (`fundamentalista`)."""
    if chave in fundamentos.FORMULAS:
        formula, versao = fundamentos.FORMULAS[chave], CALCULO_DOS_FUNDAMENTOS
    else:
        formula, versao = fundamentalista.FORMULAS[chave], CALCULO_DO_FUNDAMENTALISTA
    documentos = (
        _dfps(c, _ultimos_anos(c, fundamentos.ANOS_DO_CRESCIMENTO + 1))
        if chave in CRESCIMENTOS
        else c.documentos
    )
    return Rastro.dos_documentos(formula, versao, FONTE_DA_CVM, documentos)


def _com_o_preco(rastro: Rastro, c: "_Calculos") -> Rastro:
    return Rastro.dos_documentos(
        rastro.formula,
        rastro.versao_do_calculo,
        rastro.fonte_id,
        (*rastro.documentos, c.fechamento),
        (FONTE_DO_PRECO,),
    )


def _item(indicador: fundamentos.Indicador, c: "_Calculos") -> Item:
    """O indicador escrito, com a nota ao lado e a comparação: a do setor quando há nota contra o
    setor, a faixa fixa quando a nota é por faixa e, nos outros, o balanço anterior."""
    nota = c.notas_por_indicador.get(indicador.chave)
    if isinstance(nota, notas.Nota):
        comparacao = _contra_o_setor(nota, indicador.unidade)
    elif isinstance(nota, notas.NotaPorFaixa):
        comparacao = _contra_a_faixa(indicador.chave)
    else:
        comparacao = _contra_o_anterior(indicador.chave, indicador.unidade, c)
    return Item(
        indicador.chave,
        indicador.nome,
        escrever(indicador.valor, indicador.unidade),
        indicador.valor,
        indicador.unidade,
        indicador.base,
        indicador.motivo,
        nota.nota if nota else None,
        nota.texto if nota else "",
        fonte=FONTE_DAS_DEMONSTRACOES,
        comparacao=comparacao,
        sem_comparacao="" if comparacao else SEM_O_ANTERIOR,
        rastro=_rastro(indicador.chave, c),
    )


def _tabela(tabela: pd.DataFrame, indice: str = "ano") -> list[dict]:
    if tabela.empty:
        return []
    registros = (
        tabela.reset_index().rename(columns={"index": indice}).to_dict("records")
    )
    return [para_json(r) for r in registros]  # type: ignore[misc]


# --- seções ----------------------------------------------------------------------------------------
@dataclass(frozen=True)
class _Calculos:
    indicadores: dict[str, fundamentos.Indicador]
    notas_por_indicador: dict[str, notas.Nota | notas.NotaPorFaixa]
    classicas: dict[str, notas_classicas.NotaClassica]
    historico: fundamentalista.Historico
    dividendos: fundamentalista.DividendosEDiluicao
    grupo: str
    balancos: list[date]  # as datas dos balanços guardados, em ordem
    anterior: dict[str, fundamentos.Indicador]  # os indicadores até o balanço anterior
    documentos: tuple[DocumentoUsado, ...]  # os dos 12 meses e do balanço mais recente
    dfps: dict[
        int, DocumentoUsado
    ]  # a DFP de cada exercício (crescimento, notas, dividendos)
    fechamento: DocumentoUsado  # o preço usado nos múltiplos

    @property
    def data_anterior(self) -> date | None:
        return self.balancos[-2] if len(self.balancos) > 1 else None


def _balancos(contas: pd.DataFrame) -> list[date]:
    if contas.empty:
        return []
    saldos = contas[contas["periodo"] == fundamentos.POSICAO]
    return sorted(set(saldos["referencia"]))


def _indicadores_de_antes(
    e: Entradas, balancos: list[date]
) -> dict[str, fundamentos.Indicador]:
    """Os indicadores como estavam no balanço anterior (cortando o mais recente)."""
    if len(balancos) < 2:
        return {}
    contas = e.dados.contas
    antes = replace(e.dados, contas=contas[contas["referencia"] < balancos[-1]])
    return {
        **fundamentos.calcular(antes, e.preco).indicadores,
        **fundamentalista.calcular(antes).indicadores,
    }


def _calcular(e: Entradas) -> _Calculos:
    tela = fundamentos.calcular(e.dados, e.preco)
    extra = fundamentalista.calcular(e.dados)
    indicadores = {**tela.indicadores, **extra.indicadores}
    grupo = grupo_do_setor(e.dados.setor)
    lista: list[notas.Nota] = []
    if e.padroes is not None:
        corte, padroes = e.padroes
        valores = {
            chave: indicadores[chave].valor
            for chave in INDICADORES
            if chave in indicadores
        }
        lista = notas.notas_da_empresa(valores, grupo, padroes, corte, bool(e.achados))
    por_faixa = [
        nota
        for chave in notas.FAIXAS_FIXAS
        if chave in indicadores
        and indicadores[chave].valor is not None
        and (nota := notas.nota_por_faixa(chave, indicadores[chave].valor)) is not None
    ]
    balancos = _balancos(e.dados.contas)
    return _Calculos(
        indicadores,
        {n.indicador: n for n in [*lista, *por_faixa]},
        notas_classicas.calcular(e.dados),
        extra.historico,
        fundamentalista.dividendos_e_diluicao(
            e.dados, e.proventos, e.eventos_de_capital
        ),
        grupo,
        balancos,
        _indicadores_de_antes(e, balancos),
        documentos_usados(tela.documentos),
        _dfps_por_ano(e.dados.documentos),
        _fechamento(e),
    )


def _secao_de_itens(chave: str, c: _Calculos) -> Secao:
    itens = [
        _item(c.indicadores[i], c)
        for i in CHAVES_DAS_SECOES[chave]
        if i in c.indicadores
    ]
    return Secao(chave, SECOES[chave], itens)


def _notas_classicas(c: _Calculos) -> Secao:
    itens, tabelas = [], {}
    for nota in c.classicas.values():
        texto = "—" if nota.valor is None else f"{nota.valor:.2f}".replace(".", ",")
        itens.append(
            Item(
                nota.chave,
                nota.nome,
                texto,
                nota.valor,
                fundamentos.VEZES,
                nota.base,
                nota.motivo,
                nota.faixa or None,
                fonte=FONTE_DAS_DEMONSTRACOES,
                comparacao=Comparacao(
                    "escala do artigo", ESCALAS_DO_ARTIGO[nota.chave]
                ),
                rastro=Rastro.dos_documentos(
                    nota.formula,
                    CALCULO_DAS_NOTAS_CLASSICAS,
                    FONTE_DA_CVM,
                    _dfps(c, _ultimos_anos(c, ANOS_DAS_NOTAS_CLASSICAS[nota.chave])),
                ),
            )
        )
        tabelas[nota.chave] = [
            {
                "parcela": p.nome,
                "valor": None if p.valor is None else p.valor,
                "cumpriu": p.passou,
            }
            for p in nota.parcelas
        ]
    paragrafos = [
        f"{n.nome}: {n.formula} ({n.referencia})." for n in c.classicas.values()
    ]
    return Secao(
        "notas_classicas", SECOES["notas_classicas"], itens, paragrafos, tabelas
    )


def _padroes_e_notas(c: _Calculos, e: Entradas) -> Secao:
    if e.padroes is None:
        return Secao("padroes_e_notas", SECOES["padroes_e_notas"], paragrafos=[
            "Ainda não há padrões do setor calculados para comparar.", notas.AVISO,
        ])  # fmt: skip
    # as de faixa fixa não comparam com o setor: ficam só ao lado do número
    textos = [
        n.texto for n in c.notas_por_indicador.values() if isinstance(n, notas.Nota)
    ]
    if not textos:
        textos = [f"Sem padrão para o grupo {NOMES.get(c.grupo, c.grupo)} nesta data."]
    return Secao(
        "padroes_e_notas", SECOES["padroes_e_notas"], paragrafos=[*textos, notas.AVISO]
    )


@dataclass(frozen=True)
class _PadraoDoMultiplo:
    grupo: str  # o usado (pode ser o mercado)
    empresas: int
    percentis: dict[str, float]
    corte: date

    def comparacao(self, unidade: str) -> Comparacao:
        p = self.percentis
        return Comparacao(
            _o_setor(self.grupo, self.empresas, self.corte),
            f"mediana {escrever(p['50'], unidade)}; um terço abaixo de "
            f"{escrever(p[notas.TERCIL_BAIXO], unidade)} e um terço acima de "
            f"{escrever(p[notas.TERCIL_ALTO], unidade)}",
        )


def _padrao_do_multiplo(
    e: Entradas, grupo: str, multiplo: str
) -> _PadraoDoMultiplo | None:
    if e.padroes is None:
        return None
    corte, padroes = e.padroes
    do_multiplo = padroes[padroes["indicador"] == multiplo]
    contagem = dict(zip(do_multiplo["grupo"], do_multiplo["empresas"], strict=True))
    usado, _ = grupo_para_comparar(grupo, {g: int(n) for g, n in contagem.items()})
    linha = do_multiplo[do_multiplo["grupo"] == usado]
    if usado == SEM_GRUPO or linha.empty:
        return None
    primeira = linha.iloc[0]
    return _PadraoDoMultiplo(
        usado, int(primeira["empresas"]), dict(primeira["percentis"]), corte
    )


def _item_com_o_preco(indicador: fundamentos.Indicador, c: _Calculos) -> Item:
    """O item de um número que usa o preço: cita o Yahoo, e o balanço anterior usa o preço de hoje."""
    item = _item(indicador, c)
    item = replace(
        item,
        fonte=FONTE_DOS_MULTIPLOS,
        rastro=_com_o_preco(_rastro(indicador.chave, c), c),
    )
    if item.comparacao is None:
        return item
    contra = f"{item.comparacao.contra}, com o preço de hoje"
    return replace(item, comparacao=replace(item.comparacao, contra=contra))


def _item_de_preco(
    c: _Calculos, e: Entradas, chave: str, historico: pd.DataFrame
) -> Item:
    indicador = c.indicadores[chave]
    item = _item_com_o_preco(indicador, c)
    padrao = _padrao_do_multiplo(e, c.grupo, chave)
    if indicador.valor is None or padrao is None:
        return item
    item = replace(
        item, comparacao=padrao.comparacao(indicador.unidade), sem_comparacao=""
    )
    setor = padrao.percentis
    proprio = (
        valuation.percentis_do_historico(historico[chave])
        if chave in historico
        else None
    )
    preco = notas.preco(indicador.valor, setor, proprio)
    if preco.nota is None:
        return replace(item, nota_texto=preco.motivo)
    texto = (
        f"{preco.nota}: contra o setor, {preco.pelo_setor}; contra o próprio histórico, "
        f"{preco.pelo_historico or 'sem anos suficientes'}. {preco.motivo}"
    ).strip()
    return replace(item, nota=preco.nota, nota_texto=texto)


def _valuation(c: _Calculos, e: Entradas) -> Secao:
    historico = (
        valuation.multiplos_do_historico(
            fundamentos.anuais(e.dados.contas), e.fechamentos
        )
        if e.fechamentos is not None
        else pd.DataFrame()
    )
    itens = [
        _item_de_preco(c, e, m, historico)
        for m in (*MULTIPLOS, *MULTIPLOS_DE_MERCADO)
        if m in c.indicadores
    ]
    p = e.premissas
    origem = (
        "Premissas padrão (dá para trocar na página)"
        if p == Premissas()
        else "Premissas escolhidas por você"
    )
    paragrafos = [
        (
            f"{origem}: desconto de {_pct(p.desconto)} ao ano, perpetuidade de "
            f"{_pct(p.perpetuidade)}, {p.anos} anos e crescimento de {_pct(p.crescimento)} "
            "no DCF. São um ponto de partida declarado, não uma opinião sobre a empresa."
        )
    ]
    tabelas: dict[str, list[dict]] = {}
    livre = c.indicadores.get("caixa_livre")
    acoes, divida = _acoes_e_divida(c)
    if livre and livre.valor and livre.valor > 0 and acoes:
        args = {"caixa_livre": livre.valor, "anos": p.anos, "perpetuidade": p.perpetuidade,
                "acoes": acoes, "divida_liquida": divida}  # fmt: skip
        tabela = valuation.sensibilidade(
            **args, descontos=(p.desconto - 0.02, p.desconto, p.desconto + 0.02),
            crescimentos=(p.crescimento - 0.03, p.crescimento, p.crescimento + 0.03),
        )  # fmt: skip
        tabelas["sensibilidade"] = [
            {
                "desconto": d,
                **{f"crescimento {g:.0%}": tabela.loc[d, g] for g in tabela.columns},
            }
            for d in tabela.index
        ]
        if e.preco:
            implicito = valuation.crescimento_implicito(
                e.preco, desconto=p.desconto, **args
            )
            paragrafos.append(
                f"O preço de hoje supõe o caixa livre crescendo {_pct(implicito)} ao ano "
                f"por {p.anos} anos."
                if implicito is not None
                else "Nenhum crescimento razoável explica o preço de hoje com essas premissas."
            )
    else:
        tabelas["sensibilidade"] = []
        paragrafos.append(
            "Sem caixa livre positivo ou sem a quantidade de ações: o DCF não sai."
        )
    return Secao("valuation", SECOES["valuation"], itens, paragrafos, tabelas)


def _acoes_e_divida(c: _Calculos) -> tuple[float | None, float]:
    lucro, lpa = c.indicadores.get("lucro"), c.indicadores.get("lpa")
    acoes = (
        lucro.valor / lpa.valor if lucro and lpa and lucro.valor and lpa.valor else None
    )
    divida = c.indicadores.get("divida_liquida")
    return acoes, (divida.valor or 0.0) if divida else 0.0


def _acoes(quantidade: float) -> str:
    return f"{quantidade:,.0f}".replace(",", ".")


def _dividendos(c: _Calculos) -> Secao:
    d = c.dividendos
    anos = [int(a) for a in d.historico.index] if not d.historico.empty else []
    base = f"DFP de {anos[0]} a {anos[-1]}" if anos else ""
    ajustadas = (
        d.historico["acoes_ajustadas"].dropna() if anos else pd.Series(dtype=float)
    )
    diluicao = (
        Comparacao(
            f"ações em circulação em {ajustadas.index[0]}",
            f"{_acoes(ajustadas.iloc[0])} em {ajustadas.index[0]} e "
            f"{_acoes(ajustadas.iloc[-1])} em {ajustadas.index[-1]}",
        )
        if len(ajustadas) > 1
        else None
    )
    dy = c.indicadores.get("dividend_yield")
    itens = [] if dy is None else [_item_com_o_preco(dy, c)]

    def rastro(chave: str) -> Rastro:
        return Rastro.dos_documentos(fundamentalista.FORMULAS[chave], CALCULO_DO_FUNDAMENTALISTA,
                                     FONTE_DA_CVM, _dfps(c, anos))  # fmt: skip

    itens += [
        Item("anos_pagando", "Anos pagando dividendos", str(d.anos_pagando), float(d.anos_pagando),
             "anos", base, fonte=FONTE_DAS_ACOES,
             comparacao=Comparacao("anos com DFP guardada", f"{d.anos_pagando} de {len(anos)}"),
             rastro=rastro("anos_pagando")),
        Item("diluicao", "Diluição ao ano", escrever(d.diluicao_anual, fundamentos.FRACAO), d.diluicao_anual,
             fundamentos.FRACAO, base,
             "" if d.diluicao_anual is not None else SEM_DILUICAO,
             fonte=FONTE_DAS_ACOES, comparacao=diluicao, rastro=rastro("diluicao")),
    ]  # fmt: skip
    return Secao(
        "dividendos",
        SECOES["dividendos"],
        itens,
        # no fim: os avisos guardam a posição (o id deles na análise escrita)
        [*d.avisos, *([COMO_SAI_O_DY] if dy is not None else [])],
        {"historico": _tabela(d.historico)},
    )


def _historico(c: _Calculos) -> Secao:
    h = c.historico
    paragrafos = [
        (
            f"Crescimento composto da receita: {escrever(h.crescimento.get('receita'), fundamentos.FRACAO)} ao ano; "
            f"do lucro: {escrever(h.crescimento.get('lucro'), fundamentos.FRACAO)}."
        ),
        f"Anos com lucro: {h.consistencia.get('anos_com_lucro', 0)} de {h.consistencia.get('anos_com_dado', 0)}.",
    ]
    return Secao("historico", SECOES["historico"], paragrafos=paragrafos,
                 tabelas={"contas": _tabela(h.contas), "vertical": _tabela(h.vertical)})  # fmt: skip


def _eventos(e: Entradas) -> Secao:
    if e.eventos is None or e.eventos.empty:
        return Secao(
            "eventos",
            SECOES["eventos"],
            paragrafos=["Nenhum acontecimento recente guardado."],
        )
    recentes = e.eventos.sort_values("publicado_em", ascending=False).head(
        QUANTOS_EVENTOS
    )
    return Secao(
        "eventos",
        SECOES["eventos"],
        tabelas={"eventos": _tabela(recentes.reset_index(drop=True), "n")},
    )


def _qualidade(e: Entradas) -> Secao:
    if not e.achados:
        return Secao(
            "qualidade",
            SECOES["qualidade"],
            paragrafos=["Nenhum número em conferência."],
        )
    return Secao(
        "qualidade",
        SECOES["qualidade"],
        paragrafos=[texto_do_selo(a) for a in e.achados],
    )


Passo = tuple[str, float]


def _conta(contas: dict, nome: str) -> float | None:
    valor = contas.get(nome)
    if valor is None or (isinstance(valor, float) and math.isnan(valor)):
        return None
    return float(valor)


def cascata_do_lucro(contas: dict) -> list[Passo]:
    """Da receita ao lucro de um ano, passo a passo (o último é o total; os outros somam a ele).

    O que não tem conta própria entra num passo de "outros", para a cascata sempre fechar.
    """
    receita = _conta(contas, "receita")
    lucro = _conta(contas, "lucro_liquido")
    if receita is None or lucro is None:
        return []
    custo = _conta(contas, "custo")
    bruto = _conta(contas, "resultado_bruto")
    if bruto is None:
        bruto = receita + (custo or 0.0)
    ebit = _conta(contas, "ebit")
    if ebit is None:
        ebit = bruto
    vendas = _conta(contas, "despesas_com_vendas") or 0.0
    administrativas = _conta(contas, "despesas_administrativas") or 0.0
    passos = [
        ("Receita", receita),
        ("Custo", bruto - receita),
        ("Despesas com vendas", vendas),
        ("Despesas administrativas", administrativas),
        ("Outras operacionais", ebit - bruto - vendas - administrativas),
        ("Resultado financeiro, impostos e outros", lucro - ebit),
    ]
    return [p for p in passos if p[1] != 0 or p[0] == "Receita"] + [
        ("Lucro consolidado", lucro)
    ]


def _divida_liquida(contas: dict) -> float | None:
    if _conta(contas, "divida_liquida") is not None:
        return _conta(contas, "divida_liquida")
    if _conta(contas, "divida_cp") is None and _conta(contas, "divida_lp") is None:
        return None
    divida = (_conta(contas, "divida_cp") or 0.0) + (_conta(contas, "divida_lp") or 0.0)
    caixa = (_conta(contas, "caixa") or 0.0) + (_conta(contas, "aplicacoes") or 0.0)
    return divida - caixa


def ponte_da_divida(anterior: dict, atual: dict) -> list[Passo]:
    """Da dívida líquida de um ano à do seguinte: o caixa gerado reduz, capex e dividendos
    aumentam; o resto (aquisições, juros, câmbio) fica em "outros", para a ponte fechar."""
    comeco, fim = _divida_liquida(anterior), _divida_liquida(atual)
    if comeco is None or fim is None:
        return []
    fluxos = [
        ("Caixa operacional", -(_conta(atual, "fco") or 0.0)),
        ("Capex", abs(_conta(atual, "capex") or 0.0)),
        ("Dividendos pagos", abs(_conta(atual, "dividendos_pagos") or 0.0)),
    ]
    outros = fim - comeco - sum(v for _, v in fluxos)
    passos = [("Dívida líquida no começo", comeco), *fluxos, ("Outros", outros)]
    return [p for p in passos if p[1] != 0 or p[0].startswith("Dívida")] + [
        ("Dívida líquida no fim", fim)
    ]


def _passos_em_tabela(passos: list[Passo]) -> list[dict]:
    return [{"passo": nome, "valor": valor} for nome, valor in passos]


def _graficos_de_contas(c: _Calculos, secoes: list[Secao]) -> None:
    """A cascata do lucro (último ano) no Resultado e a ponte da dívida no Endividamento."""
    anos = c.historico.contas.dropna(how="all")
    if anos.empty:
        return
    por_chave = {s.chave: s for s in secoes}
    ultimo = anos.iloc[-1].to_dict()
    por_chave["resultado"].tabelas["cascata"] = _passos_em_tabela(
        cascata_do_lucro(ultimo)
    )
    ponte = ponte_da_divida(anos.iloc[-2].to_dict(), ultimo) if len(anos) > 1 else []
    por_chave["endividamento"].tabelas["ponte"] = _passos_em_tabela(ponte)


def _o_que_mudou(e: Entradas, c: _Calculos) -> Secao:
    datas = c.balancos
    if c.data_anterior is None:
        return Secao(
            "o_que_mudou",
            SECOES["o_que_mudou"],
            paragrafos=["Só há um balanço guardado."],
        )
    linhas = []
    for chave in INDICADORES_DO_QUE_MUDOU:
        agora, antes_i = c.indicadores.get(chave), c.anterior.get(chave)
        if agora and antes_i:
            linhas.append({"indicador": agora.nome, "antes": escrever(antes_i.valor, agora.unidade),
                           "agora": escrever(agora.valor, agora.unidade)})  # fmt: skip
    paragrafos = [
        f"Comparando o balanço de {datas[-2]:%d/%m/%Y} com o de {datas[-1]:%d/%m/%Y}."
    ]
    refeitos = [a for a in e.achados if a.regra in ("R5", "R6")]
    paragrafos += [texto_do_selo(a) for a in refeitos]
    return Secao(
        "o_que_mudou",
        SECOES["o_que_mudou"],
        paragrafos=paragrafos,
        tabelas={"indicadores": linhas},
    )


def _mudancas(c: _Calculos) -> list[leitura_da_ficha.Mudanca]:
    """Os indicadores do "o que mudou" com o sentido de cada um, para a leitura."""
    if c.data_anterior is None:
        return []
    mudancas = []
    for chave in INDICADORES_DO_QUE_MUDOU:
        agora, antes = c.indicadores.get(chave), c.anterior.get(chave)
        if agora is None or antes is None or agora.valor is None or antes.valor is None:
            continue
        mudancas.append(
            leitura_da_ficha.Mudanca(
                chave,
                agora.nome,
                antes.valor,
                agora.valor,
                escrever(antes.valor, agora.unidade),
                escrever(agora.valor, agora.unidade),
                c.data_anterior,
                _item(agora, c),
                MAIOR_E_MELHOR.get(chave, True),
            )
        )
    return mudancas


def _o_que_os_dados_mostram(secoes: list[Secao], c: _Calculos) -> Secao:
    pontos = leitura_da_ficha.pontos(secoes, _mudancas(c))
    vazios = [
        f"{titulo}: {leitura_da_ficha.SEM_PONTOS}"
        for lado, titulo in leitura_da_ficha.TITULOS_DOS_LADOS.items()
        if not any(p.lado == lado for p in pontos)
    ]
    return Secao(
        "o_que_os_dados_mostram",
        SECOES["o_que_os_dados_mostram"],
        paragrafos=vazios,
        pontos=pontos,
    )


def _caixa_do_par(e: Entradas, cnpj: str) -> dict[str, str]:
    """A margem EBITDA e o FCF do último exercício do par ("ainda sem dado" se a ficha não os tem)."""
    if e.caixa_do_par is None:
        return {}
    caixa = e.caixa_do_par(cnpj) or {}
    exercicio, margem, fcf = (
        caixa.get(c) for c in ("exercicio", "margem_ebitda", "fcf")
    )
    return {
        "margem_ebitda": AINDA_SEM_DADO
        if margem is None
        else escrever(margem, fundamentos.FRACAO),
        "fcf": AINDA_SEM_DADO if fcf is None else escrever(fcf, fundamentos.REAIS),
        "exercicio_do_caixa": AINDA_SEM_DADO if exercicio is None else str(exercicio),
    }


def _pares(e: Entradas, c: _Calculos) -> Secao:
    receita = c.indicadores.get("receita")
    if (
        e.pares is None
        or e.pares.empty
        or not receita
        or not receita.valor
        or receita.valor <= 0
    ):
        return Secao("pares", SECOES["pares"], paragrafos=["Sem pares para comparar."])
    outros = e.pares[(e.pares["cnpj"] != e.cnpj) & (e.pares["receita"] > 0)].copy()
    outros["distancia"] = (outros["receita"] / receita.valor).map(
        lambda r: abs(math.log(r))
    )
    perto = outros.sort_values("distancia").head(QUANTOS_PARES)
    tabela = [
        {
            "empresa": linha.empresa,
            "receita": escrever(linha.receita, fundamentos.REAIS),
            **_caixa_do_par(e, str(linha.cnpj)),
        }
        for linha in perto.itertuples(index=False)
    ]
    paragrafos = [
        f"As {len(tabela)} empresas do grupo {NOMES.get(c.grupo, c.grupo)} com a receita mais parecida."
    ]
    if e.caixa_do_par is not None:
        paragrafos.append(SOBRE_O_CAIXA_DOS_PARES)
    return Secao(
        "pares", SECOES["pares"], paragrafos=paragrafos, tabelas={"pares": tabela}
    )


NAO_E_PREVISAO = (
    "Não é previsão: cada linha mostra só o valor que mudaria a nota, pela mesma régua de hoje. "
    "Os padrões do setor mudam a cada corte, e com eles os limites."
)
FAIXA_FIXA = "faixa fixa e pública do TickerLab"
PERTO_DE_HOJE = "colado no valor de hoje"
ESCALA_DO_ARTIGO = "escala do artigo"
PREFIXOS_DOS_GATILHOS = {  # (sentido, o limite já dá a nota nova?) → como escrever
    (notas.SOBE, True): "a partir de",
    (notas.SOBE, False): "acima de",
    (notas.CAI, True): "até",
    (notas.CAI, False): "abaixo de",
}


def _linha_de_gatilhos(
    nome: str,
    hoje: str,
    nota: str,
    regua: notas.Regua,
    escrever_limite: Callable[[float], str],
    comparado_com: str,
) -> dict:
    por_sentido = {}
    for g in regua.gatilhos(nota):
        limite = escrever_limite(g.limite)
        if limite == hoje:  # o limite arredonda para o número de hoje: está colado nele
            limite += f" ({PERTO_DE_HOJE})"
        por_sentido[g.sentido] = (
            f"{PREFIXOS_DOS_GATILHOS[g.sentido, g.inclusive]} {limite}: {g.nota}"
        )
    return {
        "indicador": nome,
        "hoje": f"{hoje} ({nota})",
        "se_subir": por_sentido.get(notas.SOBE, "—"),
        "se_cair": por_sentido.get(notas.CAI, "—"),
        "comparado_com": comparado_com,
    }


def _gatilhos_das_notas(c: _Calculos) -> list[dict]:
    linhas = []
    for chave, nota in c.notas_por_indicador.items():
        indicador = c.indicadores[chave]
        unidade = indicador.unidade

        def no_formato(valor: float, unidade: str = unidade) -> str:
            return escrever(valor, unidade)

        if isinstance(nota, notas.Nota):
            regua = notas.regua_do_setor(nota, MAIOR_E_MELHOR.get(chave, True))
            contra = _o_setor(nota.grupo, nota.empresas, nota.data_de_corte)
        else:
            regua, contra = notas.regua_da_faixa(chave), FAIXA_FIXA
        hoje = escrever(indicador.valor, unidade)
        linhas.append(
            _linha_de_gatilhos(
                indicador.nome, hoje, nota.nota, regua, no_formato, contra
            )
        )
    for chave, regua in notas_classicas.REGUAS.items():
        classica = c.classicas.get(chave)
        if classica is not None and classica.valor is not None and classica.faixa:
            linhas.append(
                _linha_de_gatilhos(classica.nome, _dec(classica.valor), classica.faixa, regua, _dec,
                                   ESCALA_DO_ARTIGO)
            )  # fmt: skip
    return linhas


def _o_que_mudaria(c: _Calculos) -> Secao:
    """Para cada nota, o valor que a faria mudar (o limite vizinho da régua), sem previsão."""
    linhas = _gatilhos_das_notas(c)
    if not linhas:
        return Secao("o_que_mudaria", SECOES["o_que_mudaria"], paragrafos=["Sem notas para esta empresa."])  # fmt: skip
    return Secao(
        "o_que_mudaria",
        SECOES["o_que_mudaria"],
        paragrafos=[NAO_E_PREVISAO],
        tabelas={"gatilhos": linhas},
    )


def _metodologia() -> Secao:
    return Secao("metodologia", SECOES["metodologia"], recolhida=True, paragrafos=[
        ("Indicadores de 12 meses: o último DFP mais o acumulado do ano no último ITR, menos o mesmo "
        "período do ano anterior."),
        f"Fórmulas, padrões e notas na página de metodologia: {URL_DA_METODOLOGIA}.",
        *FONTES,
    ])  # fmt: skip


def data_do_dossie(d: Dossie) -> str:
    if d.velha:
        return (
            f"Dados da base do TickerLab de {d.dia:%d/%m/%Y}: a atualização das últimas noites não "
            "chegou, então os números podem estar atrasados."
        )
    return f"Dados da base do TickerLab de {d.dia:%d/%m/%Y}."


def _secoes_do_dossie(e: Entradas, plano: str | None) -> list[Secao]:
    """As seções da base: inteiras para o Pro; para os outros, só o título e o convite."""
    if e.dossie is None:
        return []
    motivo = motivo_sem_acesso(plano, DOSSIE_DA_BASE)
    if motivo is not None:
        convite = [f"{motivo} {CONVITE_DO_DOSSIE}"]
        return [
            Secao(s.chave, s.titulo, paragrafos=convite, trancada=True)
            for s in e.dossie.secoes
        ]
    data = data_do_dossie(e.dossie)
    return [replace(s, paragrafos=[data, *s.paragrafos]) for s in e.dossie.secoes]


# --- ficha técnica: quem é a empresa, com de quando e de onde vem cada linha -----------------------
TEXTO = "texto"  # a unidade de um item que é uma frase (nome, auditor), não um número
FUSO = ZoneInfo("America/Sao_Paulo")
FONTE_DOS_DOCUMENTOS = "DFP e ITR entregues à CVM (tabela documentos)"
FONTE_DO_SETOR = "cadastro de companhias da CVM (setor de atividade)"
FONTE_DOS_TICKERS = "FCA entregue à CVM (valores mobiliários negociados na B3)"
FONTE_DO_CONTROLADOR = "FRE entregue à CVM pela controladora (tabela controladas)"
MEDIDO_NO_CADASTRO = "cadastro atual da CVM"
IDENTIFICACAO = "Identificação: não há com o quê comparar."
SEM_DESDE_QUANDO = (
    "Falta saber desde quando o ticker negocia: a base guarda o histórico dos tickers, mas a "
    "ficha ainda não o traz ao app."
)
SEM_CONTROLADORA = (
    "A ficha não traz a controladora: ela só aparece quando a controladora também entrega o FRE "
    "à CVM (uma controladora de fora do Brasil, por exemplo, não entrega)."
)
SEM_FICHA_DA_BASE = "A ficha da base desta empresa ainda não chegou ao app."
DIAS_DO_ITR = 45  # prazo da CVM: o ITR sai até 45 dias depois do fim do trimestre
MESES_DA_DFP = 3  # e a DFP até 3 meses depois do fim do exercício


def _dia(valor: object) -> date:
    """O dia de uma data em qualquer formato (um momento com fuso vira o dia no Brasil)."""
    momento = pd.Timestamp(valor)  # type: ignore[arg-type]
    if momento.tzinfo is not None:
        momento = momento.tz_convert(FUSO)
    return momento.date()


def _prazo_da_cvm(documento: str, referencia: date) -> tuple[date, str]:
    if documento == "ITR":
        return referencia + timedelta(
            days=DIAS_DO_ITR
        ), f"{DIAS_DO_ITR} dias depois do trimestre"
    prazo = (pd.Timestamp(referencia) + pd.DateOffset(months=MESES_DA_DFP)).date()
    return prazo, f"{MESES_DA_DFP} meses depois do exercício"


def ultima_demonstracao(documentos: pd.DataFrame) -> Item:
    """A demonstração mais recente e a versão, comparada com o prazo da CVM pela 1ª entrega
    (reapresentar depois do prazo é normal; atrasar a primeira, não)."""
    nome = "Última demonstração"
    if documentos.empty:
        return Item("ultima_demonstracao", nome, "—", None, TEXTO, "",
                    "Nenhuma demonstração guardada.")  # fmt: skip
    ordenados = documentos.sort_values(["referencia", "versao", "recebido_em"])
    ultimo = ordenados.iloc[-1]
    documento, referencia = str(ultimo["documento"]), _dia(ultimo["referencia"])
    versao = int(ultimo["versao"])
    mesmo = ordenados[
        (ordenados["documento"] == documento)
        & (ordenados["referencia"] == ultimo["referencia"])
    ]
    primeira = mesmo.iloc[0]
    entregue = _dia(primeira["recebido_em"])
    prazo, regra = _prazo_da_cvm(documento, referencia)
    dentro = (
        leitura_da_ficha.DENTRO_DO_PRAZO
        if entregue <= prazo
        else leitura_da_ficha.DEPOIS_DO_PRAZO
    )
    reapresentada = f" {leitura_da_ficha.REAPRESENTADA}" if versao > 1 else ""
    return Item(
        "ultima_demonstracao",
        nome,
        f"{documento} de {referencia:%d/%m/%Y}, versão {versao}{reapresentada}",
        None,
        TEXTO,
        f"recebido em {_dia(ultimo['recebido_em']):%d/%m/%Y}",
        fonte=FONTE_DOS_DOCUMENTOS,
        comparacao=Comparacao(
            "prazo da CVM",
            f"versão {int(primeira['versao'])} recebida em {entregue:%d/%m/%Y}, "
            f"{(entregue - referencia).days} dias depois do fim do período, {dentro} "
            f"(até {prazo:%d/%m/%Y}, {regra})",
        ),
    )


def _nome_e_cnpj(e: Entradas) -> list[Item]:
    documentos = e.dados.documentos
    if documentos.empty:
        return [
            Item("nome", "Nome", e.empresa, None, TEXTO, MEDIDO_NO_CADASTRO,
                 fonte=FONTE_DOS_TICKERS, sem_comparacao=IDENTIFICACAO),
            Item("cnpj", "CNPJ", e.cnpj, None, TEXTO, MEDIDO_NO_CADASTRO,
                 fonte=FONTE_DOS_TICKERS, sem_comparacao=IDENTIFICACAO),
        ]  # fmt: skip
    ordenados = documentos.sort_values(["referencia", "versao"])
    primeiro, ultimo = ordenados.iloc[0], ordenados.iloc[-1]
    base = f"{ultimo['documento']} de {_dia(ultimo['referencia']):%d/%m/%Y}"
    antes = f"{primeiro['documento']} de {_dia(primeiro['referencia']):%d/%m/%Y}"
    nome_antes = str(primeiro["empresa"])
    mudou = nome_antes != str(ultimo["empresa"])
    return [
        Item("nome", "Nome", str(ultimo["empresa"]), None, TEXTO, base,
             fonte=FONTE_DOS_DOCUMENTOS,
             comparacao=Comparacao(antes, f"era {nome_antes}" if mudou else "o mesmo nome")),
        Item("cnpj", "CNPJ", e.cnpj, None, TEXTO, base, fonte=FONTE_DOS_DOCUMENTOS,
             sem_comparacao=IDENTIFICACAO),
    ]  # fmt: skip


def _tickers(e: Entradas) -> Item:
    if e.tickers is None or e.tickers.empty:
        return Item("tickers", "Tickers", e.ticker.removesuffix(".SA"), None, TEXTO,
                    "o ticker pedido nesta página", fonte=FONTE_DOS_TICKERS,
                    sem_comparacao=SEM_DESDE_QUANDO)  # fmt: skip
    texto = "; ".join(
        f"{linha.codigo} ({linha.valor_mobiliario})"
        for linha in e.tickers.sort_values("codigo").itertuples(index=False)
    )
    quando = _dia(e.tickers["atualizado_em"].max())
    return Item("tickers", "Tickers", texto, None, TEXTO, f"cadastro de {quando:%d/%m/%Y}",
                fonte=FONTE_DOS_TICKERS, sem_comparacao=SEM_DESDE_QUANDO)  # fmt: skip


def _empresas_no_padrao(e: Entradas, grupo: str) -> int:
    if e.padroes is None:
        return 0
    padroes = e.padroes[1]
    do_grupo = padroes.loc[padroes["grupo"] == grupo, "empresas"]
    return int(do_grupo.max()) if not do_grupo.empty else 0


def _setor(e: Entradas, c: _Calculos) -> Item:
    if not e.dados.setor:
        return Item("setor", "Setor", "—", None, TEXTO, "",
                    "O cadastro da CVM não informa o setor.")  # fmt: skip
    texto = f"grupo {NOMES.get(c.grupo, c.grupo)}"
    empresas = _empresas_no_padrao(e, c.grupo)
    if e.padroes is not None and empresas:
        texto += f", com {empresas} empresas nos padrões de {e.padroes[0]:%d/%m/%Y}"
    return Item("setor", "Setor", e.dados.setor, None, TEXTO, MEDIDO_NO_CADASTRO,
                fonte=FONTE_DO_SETOR,
                comparacao=Comparacao("grupos de setores do TickerLab", texto))  # fmt: skip


def _sem_o_dossie(chave: str, nome: str, e: Entradas, plano: str | None) -> Item:
    motivo = motivo_sem_acesso(plano, DOSSIE_DA_BASE)
    if e.dossie is None or motivo is None:
        return Item(chave, nome, "—", None, TEXTO, "", SEM_FICHA_DA_BASE)
    return Item(chave, nome, "—", None, TEXTO, "", f"{motivo} Vem do dossiê da base.")


def _controlador(secao: Secao, base: str) -> Item:
    controladoras = secao.tabelas.get("controladoras", [])
    if not controladoras:
        return Item(
            "controlador", "Controlador", "—", None, TEXTO, "", SEM_CONTROLADORA
        )
    texto = "; ".join(
        f"{c['Controladora']} ({c['Participação']})" for c in controladoras
    )
    return Item("controlador", "Controlador", texto, None, TEXTO, base,
                fonte=FONTE_DO_CONTROLADOR, sem_comparacao=IDENTIFICACAO)  # fmt: skip


def _auditor_e_controlador(
    e: Entradas, do_dossie: list[Secao], plano: str | None
) -> list[Item]:
    secao = next(
        (s for s in do_dossie if s.chave == "auditor_e_controladas" and not s.trancada),
        None,
    )
    if secao is None:
        return [
            _sem_o_dossie("auditor", "Auditor", e, plano),
            _sem_o_dossie("controlador", "Controlador", e, plano),
        ]
    itens = {i.chave: i for i in secao.itens}
    atual, desde = itens.get("auditor_atual"), itens.get("auditor_desde")
    if atual is None:
        auditor = Item(
            "auditor", "Auditor", "—", None, TEXTO, "", "A ficha não traz o auditor."
        )
        return [auditor, _controlador(secao, "")]
    texto = f"{atual.texto}, desde {desde.texto}" if desde else atual.texto
    auditor = replace(atual, chave="auditor", nome="Auditor", texto=texto)
    return [auditor, _controlador(secao, atual.base)]


def _ultimo_dia(tabela: pd.DataFrame | None, coluna: str) -> date | None:
    if tabela is None or tabela.empty:
        return None
    return _dia(tabela[coluna].max())


def _datas_das_fontes(e: Entradas, do_dossie: list[Secao]) -> list[dict]:
    """A última data de cada fonte que o relatório usa (só as que chegaram e aparecem)."""
    dossie_aberto = e.dossie is not None and any(not s.trancada for s in do_dossie)
    datas: list[tuple[str, date | None]] = [
        (
            "Demonstrações (DFP e ITR na CVM)",
            _ultimo_dia(e.dados.documentos, "recebido_em"),
        ),
        ("Padrões do setor", e.padroes[0] if e.padroes is not None else None),
        (
            "Dossiê da base",
            e.dossie.dia if e.dossie is not None and dossie_aberto else None,
        ),
        ("Acontecimentos (IPE na CVM)", _ultimo_dia(e.eventos, "publicado_em")),
        ("Cadastro de tickers", _ultimo_dia(e.tickers, "atualizado_em")),
    ]
    return [{"fonte": f, "data": f"{d:%d/%m/%Y}"} for f, d in datas if d is not None]


def _ficha_tecnica(
    e: Entradas, c: _Calculos, do_dossie: list[Secao], plano: str | None
) -> Secao:
    itens = [
        *_nome_e_cnpj(e),
        _tickers(e),
        _setor(e, c),
        *_auditor_e_controlador(e, do_dossie, plano),
        ultima_demonstracao(e.dados.documentos),
    ]
    return Secao(
        "ficha_tecnica",
        SECOES["ficha_tecnica"],
        itens,
        tabelas={"datas_das_fontes": _datas_das_fontes(e, do_dossie)},
    )


def na_ordem(secoes: list[Secao]) -> list[Secao]:
    """As seções na ordem do molde A (`ORDEM_DAS_SECOES`); a ordem que todos os desenhos seguem."""
    posicoes = {chave: i for i, chave in enumerate(ORDEM_DAS_SECOES)}
    return sorted(secoes, key=lambda s: posicoes.get(s.chave, POSICAO_DA_SECAO_NOVA))


def perguntas_em_aberto(secoes: list[Secao], tranca: str | None) -> list[str]:
    """O que a ficha mostrou como "—": uma pergunta por motivo, com os números que ele explica.

    Fica de fora o que só falta pelo plano (`tranca`): isso é convite, não pergunta sobre a empresa.
    """
    por_motivo: dict[str, list[str]] = {}
    for secao in secoes:
        if secao.trancada:
            continue
        for item in secao.itens:
            if item.texto != "—" or not item.motivo:
                continue
            if tranca and tranca in item.motivo:
                continue
            por_motivo.setdefault(item.motivo, []).append(item.nome)
    return [
        f"{EM_ABERTO} {' e '.join(dict.fromkeys(nomes))}. {motivo}"
        for motivo, nomes in por_motivo.items()
    ]


def fontes_do_relatorio(e: Entradas) -> tuple[str, ...]:
    """As fontes (de `coletas.REVENDA`) que a ficha vai mostrar com estas entradas."""
    com_preco = (
        e.preco is not None or e.fechamentos is not None or e.padroes is not None
    )
    return (FONTE_DA_CVM, *([FONTE_DO_PRECO] if com_preco else []))


def montar(entradas: Entradas, plano: str | None = None) -> Relatorio:
    """O relatório completo de uma empresa, pronto para a página, o PDF e a API.

    `plano` é o de quem vai ver (None vale como Gratuito): só o Pro recebe os números do dossiê.
    Erro (`LicencaNaoPermiteError`) se uma fonte da ficha não pode ser mostrada (ADR 0008, Emenda 3).
    """
    usadas = fontes_do_relatorio(entradas)
    exigir_licenca(MOSTRAR, usadas, onde=ONDE_A_TRAVA_BARRA)
    c = _calcular(entradas)
    do_dossie = _secoes_do_dossie(entradas, plano)
    mostrado = entradas.dossie if any(not s.trancada for s in do_dossie) else None
    limites = [*LIMITES, *(mostrado.limites if mostrado else [])]
    fontes = (
        *FONTES,
        *citacoes_das_fontes(usadas),
        *(mostrado.fontes if mostrado else ()),
    )
    secoes = [
        _ficha_tecnica(entradas, c, do_dossie, plano),
        *(
            _secao_de_itens(chave, c)
            for chave in ("resultado", "retorno", "endividamento", "caixa")
        ),
        _notas_classicas(c),
        _padroes_e_notas(c, entradas),
        _valuation(c, entradas),
        _dividendos(c),
        _historico(c),
        _eventos(entradas),
        *do_dossie,
        _qualidade(entradas),
        _o_que_mudou(entradas, c),
        _pares(entradas, c),
        _o_que_mudaria(c),
        _metodologia(),
    ]
    _graficos_de_contas(c, secoes)
    secoes.append(_o_que_os_dados_mostram(secoes, c))
    em_aberto = perguntas_em_aberto(secoes, motivo_sem_acesso(plano, DOSSIE_DA_BASE))
    secoes.append(
        Secao("limites", SECOES["limites"], paragrafos=[*limites, *em_aberto])
    )
    secoes = na_ordem(secoes)
    return Relatorio(
        empresa=entradas.empresa,
        cnpj=entradas.cnpj,
        ticker=entradas.ticker,
        setor=entradas.dados.setor,
        grupo=NOMES.get(c.grupo, c.grupo),
        secoes=secoes,
        fontes=tuple(dict.fromkeys(fontes)),
        aviso_das_notas=notas.AVISO,
        em_conferencia=bool(entradas.achados),
    )
