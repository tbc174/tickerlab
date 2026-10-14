"""Relatório completo de empresa (série 2 da base de ML, PR 7; ADR 0032, itens 5 a 8).

Uma estrutura de seções em tipos simples (ADR 0044): a página, o PDF e a futura API leem a mesma
coisa, então os números são os mesmos nos três. Cada número traz de quando é (a base) e, quando falta,
por quê; as notas da ADR 0033 vêm ao lado, com o padrão e o aviso; o selo de qualidade aparece quando
há achado aberto. Junta o que já existe: indicadores da tela (`src/fundamentos.py`), os cálculos novos
(`src/fundamentalista.py`), as notas clássicas, os padrões e as notas, o valuation e o FRE.

Premissas padrão do valuation (a pessoa troca na página): desconto de 12% ao ano, perpetuidade de 3%,
10 anos de projeção e crescimento de 5% no DCF. São um ponto de partida declarado, não uma opinião.
"""

import math
from dataclasses import asdict, dataclass, field, replace
from datetime import date

import pandas as pd

from src import fundamentalista, fundamentos, notas, notas_classicas, valuation
from src.banco.demonstracoes import DadosDaEmpresa
from src.metodologia_das_notas import URL_NO_SITE as URL_DA_METODOLOGIA
from src.negociacoes import formatar_valor
from src.padroes import INDICADORES, MULTIPLOS
from src.qualidade_texto import texto_do_selo
from src.setores import NOMES, SEM_GRUPO, grupo_do_setor, grupo_para_comparar

SECOES: dict[str, str] = {
    "resumo": "Resumo",
    "resultado": "Resultado",
    "retorno": "Retorno",
    "endividamento": "Endividamento",
    "caixa": "Caixa e capital de giro",
    "notas_classicas": "Notas clássicas",
    "padroes_e_notas": "Notas contra o setor",
    "valuation": "Valuation",
    "dividendos": "Dividendos e diluição",
    "historico": "Histórico de até 10 anos",
    "eventos": "Acontecimentos recentes",
    "qualidade": "Qualidade dos dados",
    "o_que_mudou": "O que mudou desde o balanço anterior",
    "pares": "Pares do mesmo setor",
    "metodologia": "Metodologia e fontes",
    "limites": "Limites e cuidados",
}
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
QUANTOS_PARES = 5
NOMES_DAS_TABELAS = {  # o título de cada tabela, igual na página e no PDF
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
FONTES = (
    "CVM: dados abertos de DFP, ITR, FRE, cadastro e eventos do IPE (ODbL)",
    "Preço da ação: Yahoo Finance (uso interno, só para os múltiplos)",
)
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
)


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


@dataclass(frozen=True)
class Secao:
    chave: str
    titulo: str
    itens: list[Item] = field(default_factory=list)
    paragrafos: list[str] = field(default_factory=list)
    tabelas: dict[str, list[dict]] = field(default_factory=dict)


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

    def secao(self, chave: str) -> Secao:
        return next(s for s in self.secoes if s.chave == chave)

    def como_dict(self) -> dict:
        """Para a API: datas em texto ISO e números que faltam como None."""
        return _para_json(asdict(self))


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
    premissas: Premissas = field(default_factory=Premissas)


# --- números escritos ------------------------------------------------------------------------------
def _para_json(valor: object) -> object:
    if isinstance(valor, dict):
        return {str(k): _para_json(v) for k, v in valor.items()}
    if isinstance(valor, list | tuple):
        return [_para_json(v) for v in valor]
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
    """`dividendo_total` → "Dividendo total" (cabeçalho das tabelas)."""
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


def _item(
    indicador: fundamentos.Indicador,
    nota: notas.Nota | notas.NotaPorFaixa | None = None,
) -> Item:
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
    )


def _tabela(tabela: pd.DataFrame, indice: str = "ano") -> list[dict]:
    if tabela.empty:
        return []
    registros = (
        tabela.reset_index().rename(columns={"index": indice}).to_dict("records")
    )
    return [_para_json(r) for r in registros]  # type: ignore[misc]


# --- seções ----------------------------------------------------------------------------------------
@dataclass(frozen=True)
class _Calculos:
    indicadores: dict[str, fundamentos.Indicador]
    notas_por_indicador: dict[str, notas.Nota | notas.NotaPorFaixa]
    classicas: dict[str, notas_classicas.NotaClassica]
    historico: fundamentalista.Historico
    dividendos: fundamentalista.DividendosEDiluicao
    grupo: str


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
    return _Calculos(
        indicadores,
        {n.indicador: n for n in [*lista, *por_faixa]},
        notas_classicas.calcular(e.dados),
        extra.historico,
        fundamentalista.dividendos_e_diluicao(
            e.dados, e.proventos, e.eventos_de_capital
        ),
        grupo,
    )


def _secao_de_itens(chave: str, c: _Calculos) -> Secao:
    itens = [
        _item(c.indicadores[i], c.notas_por_indicador.get(i))
        for i in CHAVES_DAS_SECOES[chave]
        if i in c.indicadores
    ]
    return Secao(chave, SECOES[chave], itens)


def _resumo(c: _Calculos) -> Secao:
    frases = []
    for chave in ("receita", "margem_liquida", "roe", "divida_sobre_pl"):
        indicador = c.indicadores.get(chave)
        if indicador and indicador.disponivel:
            nota = c.notas_por_indicador.get(chave)
            sufixo = f" ({nota.nota} contra o setor)" if nota else ""
            frases.append(
                f"{indicador.nome}: {escrever(indicador.valor, indicador.unidade)}{sufixo}."
            )
    altman = c.classicas["altman"]
    if altman.valor is not None:
        frases.append(
            f"Altman Z'': {altman.valor:.2f}, faixa {altman.faixa} do artigo.".replace(
                ".", ",", 1
            )
        )
    return Secao("resumo", SECOES["resumo"], paragrafos=frases)


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


def _percentis_do_setor(
    e: Entradas, grupo: str, multiplo: str
) -> dict[str, float] | None:
    if e.padroes is None:
        return None
    _, padroes = e.padroes
    do_multiplo = padroes[padroes["indicador"] == multiplo]
    contagem = dict(zip(do_multiplo["grupo"], do_multiplo["empresas"], strict=True))
    usado, _ = grupo_para_comparar(grupo, {g: int(n) for g, n in contagem.items()})
    linha = do_multiplo[do_multiplo["grupo"] == usado]
    return (
        None if usado == SEM_GRUPO or linha.empty else dict(linha.iloc[0]["percentis"])
    )


def _item_de_preco(
    c: _Calculos, e: Entradas, chave: str, historico: pd.DataFrame
) -> Item:
    indicador = c.indicadores[chave]
    item = _item(indicador)
    setor = _percentis_do_setor(e, c.grupo, chave)
    if indicador.valor is None or setor is None:
        return item
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
        _item_de_preco(c, e, m, historico) for m in MULTIPLOS if m in c.indicadores
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


def _dividendos(c: _Calculos) -> Secao:
    d = c.dividendos
    itens = [
        Item("anos_pagando", "Anos pagando dividendos", str(d.anos_pagando), float(d.anos_pagando), "anos", "DFPs guardadas"),
        Item("diluicao", "Diluição ao ano", escrever(d.diluicao_anual, fundamentos.FRACAO), d.diluicao_anual,
             fundamentos.FRACAO, "ações em circulação ajustadas por desdobramentos"),
    ]  # fmt: skip
    return Secao(
        "dividendos",
        SECOES["dividendos"],
        itens,
        list(d.avisos),
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
    contas = e.dados.contas
    saldos = (
        contas[contas["periodo"] == fundamentos.POSICAO] if not contas.empty else contas
    )
    datas = sorted(set(saldos["referencia"])) if not saldos.empty else []
    if len(datas) < 2:
        return Secao(
            "o_que_mudou",
            SECOES["o_que_mudou"],
            paragrafos=["Só há um balanço guardado."],
        )
    antes = replace(e.dados, contas=contas[contas["referencia"] < datas[-1]])
    anterior = {
        **fundamentos.calcular(antes, e.preco).indicadores,
        **fundamentalista.calcular(antes).indicadores,
    }
    linhas = []
    for chave in INDICADORES_DO_QUE_MUDOU:
        agora, antes_i = c.indicadores.get(chave), anterior.get(chave)
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
        }
        for linha in perto.itertuples(index=False)
    ]
    return Secao("pares", SECOES["pares"], paragrafos=[
        f"As {len(tabela)} empresas do grupo {NOMES.get(c.grupo, c.grupo)} com a receita mais parecida."
    ], tabelas={"pares": tabela})  # fmt: skip


def _metodologia() -> Secao:
    return Secao("metodologia", SECOES["metodologia"], paragrafos=[
        ("Indicadores de 12 meses: o último DFP mais o acumulado do ano no último ITR, menos o mesmo "
        "período do ano anterior."),
        f"Fórmulas, padrões e notas na página de metodologia: {URL_DA_METODOLOGIA}.",
        *FONTES,
    ])  # fmt: skip


def montar(entradas: Entradas) -> Relatorio:
    """O relatório completo de uma empresa, pronto para a página, o PDF e a API."""
    c = _calcular(entradas)
    secoes = [
        _resumo(c),
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
        _qualidade(entradas),
        _o_que_mudou(entradas, c),
        _pares(entradas, c),
        _metodologia(),
        Secao("limites", SECOES["limites"], paragrafos=list(LIMITES)),
    ]
    _graficos_de_contas(c, secoes)
    return Relatorio(
        empresa=entradas.empresa,
        cnpj=entradas.cnpj,
        ticker=entradas.ticker,
        setor=entradas.dados.setor,
        grupo=NOMES.get(c.grupo, c.grupo),
        secoes=secoes,
        fontes=FONTES,
        aviso_das_notas=notas.AVISO,
        em_conferencia=bool(entradas.achados),
    )
