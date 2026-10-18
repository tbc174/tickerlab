"""Múltiplos implícitos das operações de M&A (série 1, PR 4 do plano da base de M&A): o preço da operação
dividido pelos números da alvo **já entregues à CVM antes do anúncio**.

**Sem olhar o futuro:** o anúncio é o 1º dia público da operação (`primeira_data_publica`, PR 3); só
entram DFP e ITR com `recebido_em` **antes** desse dia. Os arquivos abertos da CVM guardam só a versão
mais nova de cada documento: se ela foi entregue no dia do anúncio ou depois, o documento inteiro fica de
fora (vale o anterior), em vez de usar um número que ainda não existia.

De onde vem cada parte:
- **a alvo**: a companhia que entregou um documento da operação e cujo nome é o da alvo
  (`mesma_empresa`). Alvo que não é companhia aberta não tem DFP nem ITR e fica sem múltiplo;
- **o valor**: o valor da empresa (EV) lido, ou o preço por ação lido × as ações em circulação (o valor
  do patrimônio), do documento mais antigo da operação que o trouxe, só em reais. O valor de uma
  participação fica de fora: a fração comprada não é lida com segurança (quem compra pode já ter parte);
- **os números da alvo**, com as mesmas regras do Research (`src.fundamentos`): receita, EBIT e lucro
  dos últimos 12 meses (o último DFP mais o ITR mais novo), o balanço mais recente e as ações em
  circulação conferidas pelo lucro por ação declarado (a CVM às vezes as informa em milhares).

Múltiplos: EV/receita, EV/EBIT, P/L e P/VP, com EV = patrimônio + dívida bruta − caixa e aplicações (e o
contrário quando só o EV foi lido). Denominador zero ou negativo → sem múltiplo. Banco e seguradora
(`e_financeira`) ficam sem EV: a dívida é o negócio deles. O EV/EBITDA do plano fica para depois (a
depreciação está no fluxo de caixa); o EV/EBIT compara o mesmo preço.
"""

from dataclasses import dataclass
from datetime import date

import pandas as pd

from base import ma_extracao as mx
from base import ma_operacoes as mo
from src import fundamentos as fu
from src.demonstracoes import e_financeira

MOEDA = "BRL"
VALOR_DA_EMPRESA, PRECO_POR_ACAO = "valor_empresa", "preco_por_acao"

# por que a operação ficou sem múltiplo (um motivo só: o primeiro que falta)
ALVO_FECHADA = "alvo sem documento próprio na CVM (não é companhia aberta que entregou)"
VARIAS_ALVOS = "mais de uma companhia que entregou bate com a alvo"
SEM_VALOR = "sem valor da empresa nem preço por ação lido"
SO_PARTICIPACAO = "só o valor de uma participação (a fração comprada não é lida)"
OUTRA_MOEDA = "valor lido só em outra moeda"
SEM_DOCUMENTO = "nenhum DFP ou ITR da alvo entregue antes do anúncio"
SEM_ACOES = "sem a quantidade de ações conferida"


@dataclass(frozen=True)
class Emissora:
    """A companhia que entregou o documento ao IPE (`ma_candidatos`: `cnpj` e `empresa`)."""

    cnpj: str
    empresa: str


def _alvos(membros: list[mo.DocumentoLido]) -> list[str]:
    return [p.nome for d in membros for p in d.leitura.partes if p.papel == "alvo"]


def alvo_aberta(
    membros: list[mo.DocumentoLido], emissoras: dict[str, Emissora]
) -> tuple[str | None, str]:
    """(CNPJ da alvo, motivo quando não há): a emissora de algum documento cujo nome é o da alvo."""
    alvos = _alvos(membros)
    achadas = {
        emissora.cnpj
        for d in membros
        if (emissora := emissoras.get(d.protocolo))
        and any(mx.mesma_empresa(emissora.empresa, alvo) for alvo in alvos)
    }
    if len(achadas) == 1:
        return achadas.pop(), ""
    return None, VARIAS_ALVOS if achadas else ALVO_FECHADA


def valor_lido(
    membros: list[mo.DocumentoLido],
) -> tuple[mx.ValorLido | None, str, str]:
    """(valor, protocolo de onde veio, motivo quando não há): o EV antes do preço por ação; do mais
    antigo documento da operação que o trouxe (`membros` em ordem de data)."""
    lidos = [(v, d.protocolo) for d in membros for v in d.leitura.valores]
    for campo in (VALOR_DA_EMPRESA, PRECO_POR_ACAO):
        do_campo = [(v, p) for v, p in lidos if v.campo == campo]
        em_reais = [(v, p) for v, p in do_campo if v.moeda == MOEDA]
        if em_reais:
            return em_reais[0][0], em_reais[0][1], ""
        if do_campo:
            return None, "", OUTRA_MOEDA
    if lidos:
        return None, "", SO_PARTICIPACAO
    return None, "", SEM_VALOR


def entregues_antes(
    contas: pd.DataFrame, documentos: pd.DataFrame, cnpj: str, dia: date
) -> tuple[pd.DataFrame, date | None]:
    """As contas da companhia só dos documentos recebidos pela CVM antes de `dia`, e a entrega mais nova
    entre eles (`src.demonstracoes.ler_demonstracoes`: contas e documentos, versão mais nova)."""
    recebidos = documentos[
        (documentos["cnpj"] == cnpj) & (documentos["recebido_em"] < dia)
    ][["cnpj", "documento", "referencia", "versao", "recebido_em"]]
    antes = contas[contas["cnpj"] == cnpj].merge(
        recebidos, on=["cnpj", "documento", "referencia", "versao"]
    )
    if antes.empty:
        return antes, None
    return antes.drop(columns="recebido_em"), max(antes["recebido_em"])


def _divisao(numerador: float | None, denominador: float | None) -> float | None:
    if numerador is None or denominador is None or denominador <= 0:
        return None
    return numerador / denominador


def _lucro(valores: dict) -> float | None:
    """Lucro dos controladores; sem a divisão, o consolidado (como no Research)."""
    return valores.get("lucro_controladores", valores.get("lucro_liquido"))


def _divida_liquida(saldo: dict) -> float | None:
    if not ({"divida_cp", "divida_lp"} & set(saldo)):
        return None
    divida = saldo.get("divida_cp", 0.0) + saldo.get("divida_lp", 0.0)
    return divida - saldo.get("caixa", 0.0) - saldo.get("aplicacoes", 0.0)


def calcular(valor: mx.ValorLido, contas: pd.DataFrame) -> dict:
    """Os números da alvo e os múltiplos de uma operação (`contas` já só de antes do anúncio)."""
    ttm, base_12m, _ = fu.doze_meses(contas)
    saldo, balanco_em, _ = fu.balanco_mais_recente(contas)
    acoes, nota, _ = fu.acoes_em_circulacao(saldo, contas)
    financeira = e_financeira("", contas["conta"].unique())
    divida_liquida = None if financeira else _divida_liquida(saldo)
    if valor.campo == VALOR_DA_EMPRESA:
        ev = valor.em_unidades
        patrimonio = None if divida_liquida is None else ev - divida_liquida
    else:
        patrimonio = None if acoes is None else valor.em_unidades * acoes
        ev = (
            None
            if patrimonio is None or divida_liquida is None
            else patrimonio + divida_liquida
        )
    receita, ebit, lucro = ttm.get("receita"), ttm.get("ebit"), _lucro(ttm)
    pl = saldo.get("patrimonio_liquido")
    return {
        "valor_da_empresa": ev,
        "valor_do_patrimonio": patrimonio,
        "acoes": acoes,
        "receita_12m": receita,
        "ebit_12m": None if financeira else ebit,
        "lucro_12m": lucro,
        "patrimonio_liquido": pl,
        "divida_liquida": divida_liquida,
        "base_12m": base_12m,
        "balanco_em": balanco_em,
        "ev_receita": _divisao(ev, receita),
        "ev_ebit": None if financeira else _divisao(ev, ebit),
        "p_l": _divisao(patrimonio, lucro),
        "p_vp": _divisao(patrimonio, pl),
        "nota": nota,
        "motivo": SEM_ACOES if patrimonio is None and acoes is None else "",
    }


def multiplos(
    documentos: list[mo.DocumentoLido],
    emissoras: dict[str, Emissora],
    contas: pd.DataFrame,
    documentos_da_cvm: pd.DataFrame,
) -> pd.DataFrame:
    """Uma linha por operação (`ma_operacoes.operacoes`), com os múltiplos ou o motivo de não ter."""
    tabela, ligacoes = mo.operacoes(documentos)
    por_protocolo = {d.protocolo: d for d in documentos}
    membros_da = {
        operacao: sorted(
            (por_protocolo[p] for p in grupo["protocolo"]),
            key=lambda d: (d.publico_em, d.protocolo),
        )
        for operacao, grupo in ligacoes.groupby("operacao")
    }
    linhas = []
    for operacao in tabela.itertuples():
        membros = membros_da[operacao.operacao]
        anuncio: date = operacao.primeira_data_publica
        linha: dict = {
            "operacao": operacao.operacao,
            "alvo": operacao.alvo,
            "anuncio": anuncio,
        }
        cnpj, motivo = alvo_aberta(membros, emissoras)
        valor, protocolo, motivo_do_valor = valor_lido(membros)
        linha |= {"alvo_cnpj": cnpj, "valor_campo": valor.campo if valor else None,
                  "valor_lido": valor.em_unidades if valor else None, "valor_protocolo": protocolo or None}  # fmt: skip
        if cnpj is None or valor is None:
            linhas.append(linha | {"motivo": motivo or motivo_do_valor})
            continue
        antes, entregue_ate = entregues_antes(contas, documentos_da_cvm, cnpj, anuncio)
        if antes.empty:
            linhas.append(linha | {"motivo": SEM_DOCUMENTO})
            continue
        linhas.append(linha | {"entregue_ate": entregue_ate} | calcular(valor, antes))
    return pd.DataFrame(linhas, columns=COLUNAS)


COLUNAS = [
    "operacao", "alvo", "alvo_cnpj", "anuncio", "valor_campo", "valor_lido", "valor_protocolo",
    "valor_da_empresa", "valor_do_patrimonio", "acoes", "receita_12m", "ebit_12m", "lucro_12m",
    "patrimonio_liquido", "divida_liquida", "base_12m", "balanco_em", "entregue_ate",
    "ev_receita", "ev_ebit", "p_l", "p_vp", "nota", "motivo",
]  # fmt: skip
