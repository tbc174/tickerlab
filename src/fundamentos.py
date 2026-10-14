"""Indicadores fundamentalistas a partir das demonstrações da CVM (Research, etapa 3b).

Tudo sai das contas guardadas por `src/demonstracoes.py` e das fórmulas abaixo, escritas aqui para
qualquer um conferir. Regras (PRD v2, seções 4.3 e 5):

- **Últimos 12 meses:** anual do último DFP + acumulado do ano no último ITR − acumulado do mesmo
  período do ano anterior (que o próprio ITR traz). Sem ITR mais novo que o DFP, vale o ano do DFP.
- **Balanço:** o saldo mais recente (do ITR, se for mais novo que o DFP).
- **"Não se aplica" com motivo**, nunca zero: bancos e seguradoras (outro plano de contas, sem
  margem bruta, EBIT nem dívida comparáveis), prejuízo (P/L sem sentido), patrimônio negativo,
  base negativa no crescimento, falta de preço ou de quantidade de ações.
- **Hipóteses explícitas:** ROIC com alíquota de 34% de IR/CS; P/L e P/VP usam o preço do ticker
  escolhido para **todas** as classes de ação (aproximação quando ON e PN valem diferente).
- **Quantidade de ações conferida:** algumas companhias a informam em milhares (o arquivo da CVM
  não diz). Ela é comparada com lucro ÷ lucro por ação declarado na DRE: perto de 1, vale; perto
  de 1.000, é multiplicada por mil; fora disso, os indicadores por ação ficam indisponíveis.

Os filtros (ROIC mínimo, P/L máximo) vêm da página Parâmetros e são **educacionais**: dizem se o
número passa do limite que a pessoa escolheu, não se a ação é boa ou ruim.
"""

from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from src.banco.demonstracoes import DadosDaEmpresa
from src.demonstracoes import (
    ACUMULADO,
    ACUMULADO_ANTERIOR,
    EXERCICIO,
    POSICAO,
    e_financeira,
)

VERSAO_DOS_FUNDAMENTOS = "1"  # sobe quando uma fórmula abaixo mudar
ALIQUOTA_DE_IR_CS = 0.34  # hipótese do ROIC (alíquota nominal de IR + CSLL no Brasil)
ALIQUOTA_DOS_EUA = (
    0.21  # imposto federal sobre o lucro das empresas nos EUA (sem os estaduais)
)
FAIXA_DE_ACOES_CONFERIDAS = (
    0.8,
    1.25,
)  # razão aceitável entre ações implícitas e informadas
MIL = 1_000
DIAS_DE_UM_ANO = 371  # 53 semanas: o maior exercício possível
NAO_SE_APLICA_A_FINANCEIRAS = (
    "Não se aplica a bancos e seguradoras: o balanço deles é organizado de outro jeito "
    "(não há margem bruta, EBIT nem dívida comparáveis)."
)
REAIS, FRACAO, VEZES, REAIS_POR_ACAO = "reais", "fração", "vezes", "reais por ação"


@dataclass(frozen=True)
class Indicador:
    chave: str
    nome: str
    valor: float | None
    unidade: str
    base: (
        str  # de quando é o número ("12 meses até 30/06/2026", "balanço de 30/06/2026")
    )
    motivo: str = ""  # por que está indisponível

    @property
    def disponivel(self) -> bool:
        return self.valor is not None


@dataclass(frozen=True)
class Fundamentos:
    empresa: str
    setor: str
    financeira: bool
    indicadores: dict[str, Indicador]
    anual: (
        pd.DataFrame
    )  # um ano por linha: receita, lucro, margem líquida, patrimônio, dívida
    documentos: pd.DataFrame  # documento, referencia, recebido_em, link (os usados)
    notas: list[str] = field(
        default_factory=list
    )  # avisos sobre os dados (ex.: ações em milhares)
    filtros: list[str] = field(default_factory=list)
    versao: str = VERSAO_DOS_FUNDAMENTOS

    def __getitem__(self, chave: str) -> Indicador:
        return self.indicadores[chave]


def _data(d: date) -> str:
    return f"{d:%d/%m/%Y}"


def _contas_em(
    contas: pd.DataFrame, documento: str | None, referencia: date, periodo: str
) -> dict:
    filtro = (contas["referencia"] == referencia) & (contas["periodo"] == periodo)
    if documento:
        filtro &= contas["documento"] == documento
    return dict(
        zip(contas.loc[filtro, "conta"], contas.loc[filtro, "valor"], strict=True)
    )


def _lucro(valores: dict) -> float | None:
    """Lucro dos controladores (o que é do acionista da empresa); sem a divisão, o consolidado."""
    return valores.get("lucro_controladores", valores.get("lucro_liquido"))


def _positivo(valor: float | None) -> bool:
    return valor is not None and valor > 0


# --- de onde vêm os números -----------------------------------------------------------------
def anuais(contas: pd.DataFrame) -> pd.DataFrame:
    """As contas de cada exercício (DFP, fluxos e saldos), um ano por linha, do mais antigo."""
    dfp = contas[contas["documento"] == "DFP"]
    exercicios = dfp[dfp["periodo"].isin([EXERCICIO, POSICAO])]
    if exercicios.empty or not (exercicios["periodo"] == EXERCICIO).any():
        return pd.DataFrame()
    tabela = exercicios.pivot_table(
        index="referencia", columns="conta", values="valor", aggfunc="first"
    ).sort_index()
    tabela.index = pd.Index([d.year for d in tabela.index], name="ano")
    return tabela[~tabela.index.duplicated(keep="last")]


def doze_meses(contas: pd.DataFrame) -> tuple[dict, str, list[tuple[str, date]]]:
    """(contas dos últimos 12 meses, descrição da base, documentos usados)."""
    dfp = contas[(contas["documento"] == "DFP") & (contas["periodo"] == EXERCICIO)]
    if dfp.empty:
        return {}, "", []
    ultimo_dfp = max(dfp["referencia"])
    so_o_dfp = (
        _contas_em(contas, "DFP", ultimo_dfp, EXERCICIO),
        f"exercício encerrado em {_data(ultimo_dfp)}",
        [("DFP", ultimo_dfp)],
    )
    itr = contas[(contas["documento"] == "ITR") & (contas["periodo"] == ACUMULADO)]
    mais_novo = max(itr["referencia"]) if not itr.empty else None
    if mais_novo is None or mais_novo <= ultimo_dfp:
        return so_o_dfp
    # o último anual antes do trimestre, a no máximo um ano dele: funciona com ano fiscal fora
    # do calendário (Apple termina em setembro; Walmart, em janeiro)
    base = [
        r
        for r in dfp["referencia"].unique()
        if r < mais_novo and (mais_novo - r).days <= DIAS_DE_UM_ANO
    ]
    if not base:
        return so_o_dfp
    base = [max(base)]
    anual = _contas_em(contas, "DFP", base[0], EXERCICIO)
    acumulado = _contas_em(contas, "ITR", mais_novo, ACUMULADO)
    anterior = _contas_em(contas, "ITR", mais_novo, ACUMULADO_ANTERIOR)
    ttm = {
        conta: anual[conta] + acumulado[conta] - anterior[conta]
        for conta in anual
        if conta in acumulado and conta in anterior and conta != "lpa_basico"
    }
    return (
        ttm,
        f"12 meses até {_data(mais_novo)}",
        [("DFP", base[0]), ("ITR", mais_novo)],
    )


def balanco_mais_recente(contas: pd.DataFrame) -> tuple[dict, date | None, str]:
    """(saldos, data, documento) do balanço mais recente (o ITR vence o DFP na mesma data)."""
    saldos = contas[contas["periodo"] == POSICAO]
    if saldos.empty:
        return {}, None, ""
    referencia = max(saldos["referencia"])
    documentos = set(saldos.loc[saldos["referencia"] == referencia, "documento"])
    documento = "ITR" if "ITR" in documentos else "DFP"
    return _contas_em(contas, documento, referencia, POSICAO), referencia, documento


def acoes_em_circulacao(
    saldo: dict, contas: pd.DataFrame
) -> tuple[float | None, str, str]:
    """(ações, nota, motivo de indisponibilidade), conferindo com o lucro por ação declarado."""
    if "acoes_total" not in saldo:
        return None, "", "Sem a quantidade de ações no documento."
    acoes = saldo["acoes_total"] - saldo.get("acoes_tesouraria", 0.0)
    if acoes <= 0:  # visto em documentos reais: dividir por zero derrubava a página
        return None, "", "Quantidade de ações zerada ou negativa no documento."
    tabela = anuais(contas)
    if tabela.empty or "lpa_basico" not in tabela or "acoes_total" not in tabela:
        return (
            acoes,
            "Quantidade de ações não conferida (sem lucro por ação declarado).",
            "",
        )
    ano = tabela.iloc[-1]
    lucro, lpa, informadas = (
        _lucro(ano.dropna().to_dict()),
        ano.get("lpa_basico"),
        ano.get("acoes_total"),
    )
    if not (_positivo(lucro) and _positivo(lpa) and _positivo(informadas)):
        return (
            acoes,
            "Quantidade de ações não conferida (sem lucro por ação declarado).",
            "",
        )
    razao = (lucro / lpa) / informadas
    minimo, maximo = FAIXA_DE_ACOES_CONFERIDAS
    if minimo <= razao <= maximo:
        return acoes, "", ""
    if minimo * MIL <= razao <= maximo * MIL:
        nota = (
            "A quantidade de ações veio em milhares na CVM; corrigida pelo lucro por ação "
            "declarado na DRE."
        )
        return acoes * MIL, nota, ""
    return (
        None,
        "",
        "A quantidade de ações informada não bate com o lucro por ação declarado.",
    )


# --- indicadores ---------------------------------------------------------------------------------
class _Lista:
    """Junta os indicadores, transformando ausência de dado em "indisponível com motivo"."""

    def __init__(self) -> None:
        self.itens: dict[str, Indicador] = {}

    def add(
        self,
        chave: str,
        nome: str,
        valor: float | None,
        unidade: str,
        base: str,
        motivo: str = "",
    ) -> None:
        if motivo:
            valor = None
        elif valor is not None and (pd.isna(valor) or abs(valor) == float("inf")):
            valor, motivo = None, "Não há dados suficientes para calcular."
        elif valor is None:
            motivo = "A conta não aparece nas demonstrações guardadas."
        self.itens[chave] = Indicador(chave, nome, valor, unidade, base, motivo)


def _resultado(lista: _Lista, ttm: dict, base: str, financeira: bool) -> None:
    receita, lucro_total = ttm.get("receita"), ttm.get("lucro_liquido")
    lista.add("receita", "Receita (12 meses)", receita, REAIS, base)
    lista.add("lucro", "Lucro dos acionistas (12 meses)", _lucro(ttm), REAIS, base)
    sem_receita = "" if _positivo(receita) else "Sem receita positiva no período."
    for chave, nome, conta in (
        ("margem_bruta", "Margem bruta", "resultado_bruto"),
        ("margem_ebit", "Margem EBIT", "ebit"),
    ):
        motivo = NAO_SE_APLICA_A_FINANCEIRAS if financeira else sem_receita
        valor = ttm.get(conta)
        lista.add(
            chave,
            nome,
            None if valor is None or motivo else valor / receita,
            FRACAO,
            base,
            motivo,
        )
    lista.add(
        "margem_liquida", "Margem líquida (lucro consolidado)",
        None if lucro_total is None or sem_receita else lucro_total / receita, FRACAO, base, sem_receita,
    )  # fmt: skip


def _retornos_e_divida(
    lista: _Lista,
    ttm: dict,
    saldo: dict,
    base_12m: str,
    base_balanco: str,
    financeira: bool,
    aliquota: float = ALIQUOTA_DE_IR_CS,
) -> None:
    pl_total = saldo.get("patrimonio_liquido")
    pl = None if pl_total is None else pl_total - saldo.get("minoritarios", 0.0)
    pl_ruim = "" if _positivo(pl) else "Patrimônio líquido negativo ou zero."
    lucro = _lucro(ttm)
    lista.add(
        "roe", "ROE (retorno sobre o patrimônio)",
        None if lucro is None or pl_ruim else lucro / pl, FRACAO, f"{base_12m}; {base_balanco}", pl_ruim,
    )  # fmt: skip
    nomes = (
        ("roic", "ROIC (retorno sobre o capital investido)", FRACAO),
        ("divida_bruta", "Dívida bruta", REAIS),
        ("caixa", "Caixa e aplicações", REAIS),
        ("divida_liquida", "Dívida líquida", REAIS),
        ("divida_sobre_pl", "Dívida líquida / patrimônio", VEZES),
        ("conversao_de_caixa", "Caixa operacional / lucro", VEZES),
    )
    if financeira:
        for chave, nome, unidade in nomes:
            lista.add(
                chave, nome, None, unidade, base_balanco, NAO_SE_APLICA_A_FINANCEIRAS
            )
        return
    divida = (
        saldo.get("divida_cp", 0.0) + saldo.get("divida_lp", 0.0)
        if "divida_cp" in saldo or "divida_lp" in saldo
        else None
    )
    caixa = (
        saldo.get("caixa", 0.0) + saldo.get("aplicacoes", 0.0)
        if "caixa" in saldo or "aplicacoes" in saldo
        else None
    )
    investido = (
        None
        if pl_total is None or divida is None or caixa is None
        else pl_total + divida - caixa
    )
    sem_capital = "" if _positivo(investido) else "Capital investido negativo ou zero."
    ebit = ttm.get("ebit")
    lista.add(
        "roic", nomes[0][1], None if ebit is None or sem_capital else ebit * (1 - aliquota) / investido,
        FRACAO, f"{base_12m}; {base_balanco}", sem_capital,
    )  # fmt: skip
    liquida = None if divida is None or caixa is None else divida - caixa
    lista.add("divida_bruta", "Dívida bruta", divida, REAIS, base_balanco)
    lista.add("caixa", "Caixa e aplicações", caixa, REAIS, base_balanco)
    lista.add("divida_liquida", "Dívida líquida", liquida, REAIS, base_balanco)
    lista.add(
        "divida_sobre_pl", "Dívida líquida / patrimônio",
        None if liquida is None or pl_ruim else liquida / pl, VEZES, base_balanco, pl_ruim,
    )  # fmt: skip
    lucro_total, fco = ttm.get("lucro_liquido"), ttm.get("fco")
    sem_lucro = "" if _positivo(lucro_total) else "Sem lucro positivo no período."
    lista.add(
        "conversao_de_caixa", "Caixa operacional / lucro",
        None if fco is None or sem_lucro else fco / lucro_total, VEZES, base_12m, sem_lucro,
    )  # fmt: skip


def _cagr(serie: pd.Series | None, anos: int) -> tuple[float | None, str]:
    serie = pd.Series(dtype=float) if serie is None else serie.dropna()
    if len(serie) < anos + 1:
        return (
            None,
            f"Só há {len(serie)} anos de demonstrações guardados; o horizonte pede {anos + 1}.",
        )
    inicio, fim = float(serie.iloc[-(anos + 1)]), float(serie.iloc[-1])
    if inicio <= 0 or fim <= 0:
        return None, "Base negativa ou zero: crescimento composto não tem sentido."
    return (fim / inicio) ** (1 / anos) - 1, ""


def _crescimento(lista: _Lista, tabela: pd.DataFrame, anos: int) -> None:
    lucro = (
        None
        if tabela.empty
        else tabela.get("lucro_controladores", tabela.get("lucro_liquido"))
    )
    for chave, serie, nome in (
        (
            "crescimento_receita",
            None if tabela.empty else tabela.get("receita"),
            "da receita",
        ),
        ("crescimento_lucro", lucro, "do lucro"),
    ):
        base = (
            ""
            if tabela.empty
            else f"DFP de {tabela.index[-1] - anos} a {tabela.index[-1]}"
        )
        valor, motivo = _cagr(serie, anos)
        lista.add(
            chave,
            f"Crescimento {nome} ({anos} anos, ao ano)",
            valor,
            FRACAO,
            base,
            motivo,
        )


def _por_acao(
    lista: _Lista,
    ttm: dict,
    saldo: dict,
    acoes: tuple,
    preco: float | None,
    bases: tuple[str, str],
) -> None:
    quantidade, _, sem_acoes = acoes
    base_12m, base_balanco = bases
    lucro = _lucro(ttm)
    pl = (
        None
        if "patrimonio_liquido" not in saldo
        else saldo["patrimonio_liquido"] - saldo.get("minoritarios", 0.0)
    )
    lpa = None if sem_acoes or lucro is None else lucro / quantidade
    vpa = None if sem_acoes or pl is None else pl / quantidade
    lista.add(
        "lpa", "Lucro por ação (12 meses)", lpa, REAIS_POR_ACAO, base_12m, sem_acoes
    )
    lista.add(
        "vpa", "Patrimônio por ação", vpa, REAIS_POR_ACAO, base_balanco, sem_acoes
    )
    sem_preco = "" if _positivo(preco) else "Sem o preço do ativo."
    motivo_pl = (
        sem_preco
        or sem_acoes
        or (
            ""
            if _positivo(lpa)
            else "Prejuízo nos últimos 12 meses: o P/L não tem sentido."
        )
    )
    motivo_pvp = (
        sem_preco
        or sem_acoes
        or ("" if _positivo(vpa) else "Patrimônio líquido negativo ou zero.")
    )
    lista.add(
        "p_l",
        "P/L (preço / lucro por ação)",
        None if motivo_pl else preco / lpa,
        VEZES,
        base_12m,
        motivo_pl,
    )
    lista.add(
        "p_vp",
        "P/VP (preço / patrimônio por ação)",
        None if motivo_pvp else preco / vpa,
        VEZES,
        base_balanco,
        motivo_pvp,
    )


def _tabela_anual(tabela: pd.DataFrame) -> pd.DataFrame:
    """Receita, lucro, margem líquida, patrimônio e dívida líquida de cada ano (vazio = NaN)."""
    if tabela.empty:
        return tabela
    vazio = pd.Series(float("nan"), index=tabela.index)

    def coluna(nome: str) -> pd.Series:
        return tabela.get(nome, vazio)

    lucro = coluna("lucro_controladores").fillna(coluna("lucro_liquido"))
    saida = pd.DataFrame(index=tabela.index)
    saida["receita"] = coluna("receita")
    saida["lucro"] = lucro
    saida["margem_liquida"] = coluna("lucro_liquido") / coluna("receita")
    saida["patrimonio"] = coluna("patrimonio_liquido")
    if "divida_cp" in tabela or "divida_lp" in tabela:
        divida = coluna("divida_cp").fillna(0) + coluna("divida_lp").fillna(0)
        caixa = coluna("caixa").fillna(0) + coluna("aplicacoes").fillna(0)
        saida["divida_liquida"] = divida - caixa
    return saida


def _filtros(
    itens: dict[str, Indicador], roic_minimo: float | None, pl_maximo: float | None
) -> list[str]:
    """Frases neutras: o número passa ou não do limite escolhido na página Parâmetros."""
    frases = []
    roic, pl = itens["roic"], itens["p_l"]
    if (
        roic_minimo is not None and roic.valor is not None
    ):  # o mesmo que roic.disponivel
        lado = "acima" if roic.valor * 100 >= roic_minimo else "abaixo"
        valor = f"{roic.valor:.1%}".replace(".", ",")
        frases.append(
            f"ROIC de {valor}: {lado} do seu filtro de {roic_minimo:g}%.".replace(
                ".0%", "%"
            )
        )
    if pl_maximo is not None and pl.valor is not None:
        lado = "dentro" if pl.valor <= pl_maximo else "fora"
        frases.append(
            f"P/L de {pl.valor:.1f}".replace(".", ",")
            + f": {lado} do seu filtro de até {pl_maximo:g}."
        )
    return frases


def calcular(
    dados: DadosDaEmpresa,
    preco: float | None,
    anos: int = 5,
    roic_minimo: float | None = None,
    pl_maximo: float | None = None,
    aliquota: float = ALIQUOTA_DE_IR_CS,
) -> Fundamentos:
    """Os indicadores da companhia. `preco`: último fechamento do ticker, na moeda do balanço;
    `aliquota`: o imposto usado no ROIC (34% no Brasil, `ALIQUOTA_DOS_EUA` nos EUA)."""
    contas = dados.contas
    financeira = e_financeira(
        dados.setor, contas["conta"].unique() if not contas.empty else ()
    )
    ttm, base_12m, usados = doze_meses(contas)
    saldo, data_do_balanco, documento_do_balanco = balanco_mais_recente(contas)
    base_balanco = f"balanço de {_data(data_do_balanco)}" if data_do_balanco else ""
    if data_do_balanco:
        usados.append((documento_do_balanco, data_do_balanco))
    acoes = acoes_em_circulacao(saldo, contas)
    tabela = anuais(contas)
    lista = _Lista()
    _resultado(lista, ttm, base_12m, financeira)
    _retornos_e_divida(lista, ttm, saldo, base_12m, base_balanco, financeira, aliquota)
    _crescimento(lista, tabela, anos)
    _por_acao(lista, ttm, saldo, acoes, preco, (base_12m, base_balanco))
    docs = dados.documentos
    if not docs.empty:
        usados_set = set(usados)
        docs = docs[
            [
                (d, r) in usados_set
                for d, r in zip(docs["documento"], docs["referencia"], strict=True)
            ]
        ]
    empresa = (
        dados.documentos.sort_values("referencia")["empresa"].iloc[-1]
        if not dados.documentos.empty
        else ""
    )
    notas = [acoes[1]] if acoes[1] else []
    return Fundamentos(
        empresa=empresa,
        setor=dados.setor,
        financeira=financeira,
        indicadores=lista.itens,
        anual=_tabela_anual(tabela),
        documentos=docs.sort_values("referencia") if not docs.empty else docs,
        notas=notas,
        filtros=_filtros(lista.itens, roic_minimo, pl_maximo),
    )
