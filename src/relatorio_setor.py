"""O relatório do setor (molde D, plano de 19/10/2026, PR 3): quem está no setor, o tamanho, a
concentração, a participação de cada companhia aberta, as empresas lado a lado e o que não temos.

A parte do mercado vem pronta da noite: a seção `setor` viaja dentro da ficha de um membro
(`src/dossie.py`, `secao_do_setor`). Aqui ela se junta ao que só o app tem: os membros pelo setor da
CVM (o cadastro no banco do app) e os indicadores de cada membro (as DFP e os ITR do banco do app).
Cada número sai com a data e a fonte; as frases de "O que os dados mostram" saem de regras fixas e
levam o id do número de onde vieram. Nada de previsão, nota ou ordem por juízo (ADR 0100, item 5).
"""

import re
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field, replace
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal

import sqlalchemy as sa

from base import cnpj as cnpj_da_base
from base import dossie as dossie_da_base
from src import cruzamentos, dossie, fundamentalista, fundamentos
from src.banco.demonstracoes import dados_da_empresa
from src.banco.modelo import setores_cvm, tickers_dos_emissores
from src.contestacao import com_a_contestacao
from src.dossie import Ficha
from src.planos import DOSSIE_DA_BASE, motivo_sem_acesso
from src.relatorio_empresa import (
    AINDA_SEM_DADO,
    CONVITE_DO_DOSSIE,
    FONTE_DAS_DEMONSTRACOES,
    FONTE_DO_SETOR,
    FONTE_DOS_TICKERS,
    FUSO,
    IDENTIFICACAO,
    MEDIDO_NO_CADASTRO,
    Dossie,
    Item,
    Secao,
    data_do_dossie,
    escrever,
    para_json,
)

# --- os setores do relatório ---------------------------------------------------------------------

# aviação fica na reserva da lista do lançamento: o código serve, mas a rota não a abre
RESERVA = frozenset({"aviacao"})
SETORES_DO_RELATORIO = tuple(
    s for s in dossie_da_base.SETORES_DO_LANCAMENTO if s.chave not in RESERVA
)
POR_CHAVE = {s.chave: s for s in SETORES_DO_RELATORIO}

# os nomes exatos do setor de atividade no cadastro da CVM (conferidos contra os 53 que existiam em
# 13/10/2026, `tests/test_setores.py`); saúde suplementar não tem setor próprio na CVM ("Serviços
# Médicos" junta hospitais e laboratórios), então entra só pela ligação com a ANS
SETORES_DA_CVM: dict[str, tuple[str, ...]] = {
    "eletricas": ("Energia Elétrica", "Emp. Adm. Part. - Energia Elétrica"),
    "bancos": ("Bancos", "Emp. Adm. Part. - Bancos"),
    "seguros": (
        "Seguradoras e Corretoras",
        "Emp. Adm. Part. - Seguradoras e Corretoras",
    ),
    "telecom": ("Telecomunicações", "Emp. Adm. Part. - Telecomunicações"),
}


class SetorDesconhecidoError(KeyError):
    """O setor pedido não está entre os do relatório."""


def setor_do_relatorio(chave: str) -> dossie_da_base.SetorDoLancamento:
    """O setor do relatório pela chave; `SetorDesconhecidoError` fora da lista (aviação inclusive)."""
    if chave not in POR_CHAVE:
        raise SetorDesconhecidoError(chave)
    return POR_CHAVE[chave]


# --- a matriz KPI × setor (da P-B) ---------------------------------------------------------------

Situacao = Literal["tem", "parcial", "falta"]
TEM: Situacao = "tem"
PARCIAL: Situacao = "parcial"
FALTA: Situacao = "falta"
TODOS = "todos"  # o KPI vale para todos os setores
DO_BANCO_DO_APP = (
    "demonstracoes"  # a DFP e o ITR que o app coleta da CVM (não passa pela base)
)
DA_FICHA = (
    "demonstracoes_como_era"  # a geração de caixa da ficha da noite (a T1, depois)
)

# de onde viria o KPI que falta (códigos da P-B)
DO_RELEASE = "release ou ITR da empresa (R)"
DE_PEDIDO = "pedido ou coleta pública nova (P)"
PAGO = "dado pago ($)"


def _da_serie(codigo: str) -> str:
    return f"série {codigo} da mesa Dados"


@dataclass(frozen=True)
class KpiDoSetor:
    """Um KPI da matriz: em que setor vale, se a base o tem, de que tabela e onde ele aparece."""

    id: str
    nome: str
    setores: tuple[str, ...]
    situacao: Situacao
    tabela: str | None = (
        None  # de onde vem (da base: `pode_mostrar`; ou o banco do app)
    )
    fonte: str = ""  # "falta": de onde viria
    o_que_falta: str = ""  # "parcial": o que falta nele
    no_relatorio: str | None = (
        None  # a coluna do lado a lado ou a série; None: ainda não sai
    )


Setores = tuple[str, ...]


def _tem(
    id_: str, nome: str, setores: Setores, tabela: str, no_relatorio: str | None = None
) -> KpiDoSetor:
    return KpiDoSetor(id_, nome, setores, TEM, tabela, no_relatorio=no_relatorio)


def _parcial(
    id_: str, nome: str, setores: Setores, tabela: str, o_que_falta: str
) -> KpiDoSetor:
    return KpiDoSetor(id_, nome, setores, PARCIAL, tabela, o_que_falta=o_que_falta)


def _falta(id_: str, nome: str, setores: Setores, fonte: str) -> KpiDoSetor:
    return KpiDoSetor(id_, nome, setores, FALTA, fonte=fonte)


_COMUNS = (
    _tem("receita", "Receita (12 meses)", (TODOS,), DO_BANCO_DO_APP, "receita"),
    _tem("lucro", "Lucro dos acionistas (12 meses)", (TODOS,), DO_BANCO_DO_APP, "lucro"),
    _tem("margem_liquida", "Margem líquida", (TODOS,), DO_BANCO_DO_APP, "margem_liquida"),
    _tem("roe", "ROE pelo DuPont", (TODOS,), DO_BANCO_DO_APP, "dupont_roe"),
    _tem("divida_liquida", "Dívida líquida", (TODOS,), DO_BANCO_DO_APP, "divida_liquida"),
    _tem("capex", "Capex (12 meses)", (TODOS,), DO_BANCO_DO_APP, "capex"),
    _tem("caixa_livre", "Caixa livre (12 meses)", (TODOS,), DO_BANCO_DO_APP, "caixa_livre"),
    _tem("margem_ebitda", "Margem EBITDA (último exercício)", (TODOS,), DA_FICHA, "margem_ebitda"),
)  # fmt: skip
_DO_BANCO_DO_APP = tuple(k for k in _COMUNS if k.tabela == DO_BANCO_DO_APP)
_DA_GERACAO_DE_CAIXA = next(k for k in _COMUNS if k.tabela == DA_FICHA)
_B, _S, _E, _H, _T, _A = (
    ("bancos",),
    ("seguros",),
    ("eletricas",),
    ("saude_suplementar",),
    ("telecom",),
    ("aviacao",),
)
_DRE_DO_BANCO = "conta da DRE do banco: nem toda linha vem igual em todos"
_DOS_BANCOS = (
    _tem("ativo_total", "Ativo total", _B, "ifdata_valores", "bcb_ativo_total"),
    _tem("carteira_de_credito", "Carteira de crédito", _B, "ifdata_valores", "bcb_carteira_de_credito"),
    _tem("captacoes", "Captações", _B, "ifdata_valores", "bcb_captacoes"),
    _tem("basileia", "Índice de Basileia", _B, "ifdata_valores", "bcb_indice_de_basileia"),
    _tem("carteira_pf", "Carteira PF por modalidade", _B, "ifdata_valores", "bcb_carteira_pf_por_modalidade"),
    _tem("carteira_pj", "Carteira PJ por modalidade", _B, "ifdata_valores", "bcb_carteira_pj_por_modalidade"),
    _tem("receita_de_servicos", "Receita de serviços", _B, "demonstracoes_como_era"),
    _parcial("nii_nim", "Margem financeira (NII e NIM)", _B, "demonstracoes_como_era", _DRE_DO_BANCO),
    _parcial("custo_do_credito", "Custo do crédito", _B, "demonstracoes_como_era", _DRE_DO_BANCO),
    _parcial("eficiencia", "Índice de eficiência", _B, "demonstracoes_como_era", _DRE_DO_BANCO),
    _parcial("npl", "Inadimplência (NPL 90 e 15-90)", _B, "scr_credito", "só o sistema inteiro, não por banco"),
    _falta("spread_gerencial", "Spread gerencial", _B, DO_RELEASE),
    _falta("cobertura", "Índice de cobertura", _B, DO_RELEASE),
    _falta("juros_por_instituicao", "Juros por instituição", _B, DE_PEDIDO),
    _falta("guidance", "Projeções da própria empresa (guidance)", _B, DO_RELEASE),
)  # fmt: skip
_DOS_SEGUROS = (
    _tem("premio_ganho", "Prêmio ganho", _S, "susep_seguros", "susep_premio_ganho"),
    _tem("premios_por_ramo", "Prêmios emitidos e ganhos por ramo", _S, "susep_seguros"),
    _tem("sinistralidade", "Sinistralidade", _S, "susep_seguros"),
    _tem("comissionamento", "Comissionamento", _S, "susep_seguros"),
    _tem("participacao_por_ramo", "Participação de mercado por ramo", _S, "susep_seguros"),
    _tem("resseguro", "Resseguro", _S, "susep_seguros"),
    _tem("capitalizacao", "Capitalização", _S, "susep_seguros"),
    _parcial("indice_combinado", "Índice combinado", _S, "susep_seguros", "falta a despesa administrativa por entidade"),
    _parcial("resultado_financeiro", "Resultado financeiro", _S, "demonstracoes_como_era", "só na DRE da companhia"),
    _falta("previdencia", "Previdência", _S, DE_PEDIDO),
    _falta("solvencia", "Solvência", _S, DE_PEDIDO),
    _falta("roae", "ROAE", _S, DO_RELEASE),
)  # fmt: skip
_DAS_ELETRICAS = (
    _tem("consumidores", "Consumidores atendidos", _E, "aneel_samp", "aneel_consumidores"),
    _tem("energia_vendida", "Energia vendida e mercado faturado", _E, "aneel_samp"),
    _tem("geracao_por_usina", "Geração por usina", _E, "ons_geracao"),
    _parcial("perdas", "Perdas de energia", _E, "aneel_samp", "só o que a SAMP dá"),
    _falta("pld_cmo", "PLD e CMO", _E, _da_serie("T6")),
    _falta("curtailment", "Curtailment", _E, _da_serie("T6")),
    _falta("capacidade", "Capacidade instalada", _E, _da_serie("T6")),
    _falta("gsf", "GSF", _E, _da_serie("S8")),
    _falta("ena_ear", "ENA e EAR", _E, _da_serie("S8")),
    _falta("dec_fec", "DEC e FEC", _E, _da_serie("S8")),
    _falta("rap", "RAP", _E, _da_serie("S8")),
    _falta("reajuste_tarifario", "Reajuste tarifário", _E, _da_serie("S8")),
    _falta("mercado_livre_e_gd", "Mercado livre e geração distribuída", _E, _da_serie("S8")),
    _falta("inadimplencia", "Inadimplência dos consumidores", _E, DO_RELEASE),
    _falta("ebitda_regulatorio", "EBITDA regulatório", _E, DO_RELEASE),
)  # fmt: skip
_DA_SAUDE = (
    _tem("beneficiarios", "Beneficiários", _H, "ans_beneficiarios", "ans_beneficiarios"),
    _tem("margem_bruta", "Margem bruta", _H, "demonstracoes_como_era"),
    _falta("sinistralidade_ans", "Sinistralidade (DIOPS)", _H, _da_serie("S9")),
    _falta("reajuste_dos_planos", "Reajuste dos planos", _H, DE_PEDIDO),
    _falta("leitos_e_internacoes", "Leitos e internações", _H, _da_serie("S5")),
    _falta("ocupacao", "Taxa de ocupação", _H, DO_RELEASE),
    _falta("verticalizacao", "Verticalização", _H, DO_RELEASE),
    _falta("anvisa", "Registros da Anvisa", _H, _da_serie("S9")),
    _falta("reclamacoes_ans", "Reclamações", _H, DE_PEDIDO),
    _falta("sell_out", "Sell-out", _H, PAGO),
)  # fmt: skip
_DAS_TELES = (
    _tem("telefonia_movel", "Acessos da telefonia móvel", _T, "anatel_acessos", "anatel_telefonia_movel"),
    _tem("banda_larga_fixa", "Acessos da banda larga fixa", _T, "anatel_acessos", "anatel_banda_larga_fixa"),
    _tem("adicoes_liquidas", "Adições líquidas", _T, "anatel_acessos"),
    _tem("participacao_por_grupo", "Participação de mercado por grupo", _T, "anatel_acessos"),
    _tem("acessos_por_tecnologia", "Acessos por tecnologia", _T, "anatel_acessos"),
    _parcial("capex_sobre_receita", "Capex sobre receita", _T, DO_BANCO_DO_APP, "o capex do app; o da T1 depois"),
    _parcial("divida_com_arrendamento", "Dívida com arrendamento", _T, DO_BANCO_DO_APP, "a linha de arrendamento não vem separada em todas"),
    _falta("arpu", "ARPU", _T, DO_RELEASE),
    _falta("churn", "Churn", _T, DO_RELEASE),
    _falta("receita_por_servico", "Receita por serviço", _T, DO_RELEASE),
    _falta("cobertura_da_rede", "Cobertura da rede", _T, DE_PEDIDO),
    _falta("reclamacoes_anatel", "Reclamações", _T, DE_PEDIDO),
)  # fmt: skip
_DA_AVIACAO = (
    _tem("passageiros", "Passageiros pagos", _A, "anac_estatistico", "anac_passageiros"),
    _tem("rpk_ask", "RPK, ASK, RTK e ATK", _A, "anac_estatistico"),
    _parcial("rask_cask", "RASK e CASK", _A, "anac_estatistico", "receita e custo da DRE divididos pelo ASK"),
    _falta("yield", "Yield", _A, DO_RELEASE),
    _falta("pontualidade", "Pontualidade", _A, DE_PEDIDO),
    _falta("querosene", "Querosene", _A, DE_PEDIDO),
)  # fmt: skip
KPIS_DO_SETOR: tuple[KpiDoSetor, ...] = (
    *_COMUNS,
    *_DOS_BANCOS,
    *_DOS_SEGUROS,
    *_DAS_ELETRICAS,
    *_DA_SAUDE,
    *_DAS_TELES,
    *_DA_AVIACAO,
)


def kpis_do_setor(chave: str) -> list[KpiDoSetor]:
    """Os KPIs da matriz que valem para o setor (os comuns primeiro)."""
    return [k for k in KPIS_DO_SETOR if TODOS in k.setores or chave in k.setores]


# --- o que não temos ------------------------------------------------------------------------------


@dataclass(frozen=True)
class FaltaNoSetor:
    kpi: str
    motivo: str
    fonte: str  # de onde viria (ou a tabela da base que já o tem)


SEM_NA_BASE = "A base ainda não tem este número."
AINDA_NAO_SAI = "A base tem este número, mas o relatório do setor ainda não o traz."


def _na_base(tabela: str | None) -> str:
    if tabela == DO_BANCO_DO_APP:
        return f"{FONTE_DAS_DEMONSTRACOES}, no banco do app"
    return f"base do TickerLab (tabela {tabela})"


def _falta_do_kpi(kpi: KpiDoSetor) -> FaltaNoSetor:
    if kpi.situacao == FALTA:
        return FaltaNoSetor(kpi.nome, SEM_NA_BASE, kpi.fonte)
    motivo = AINDA_NAO_SAI
    if kpi.situacao == PARCIAL:
        motivo = f"Parcial: {kpi.o_que_falta}. {AINDA_NAO_SAI}"
    return FaltaNoSetor(kpi.nome, motivo, _na_base(kpi.tabela))


def nao_temos(chave: str) -> list[FaltaNoSetor]:
    """Cada KPI do setor que o relatório não mostra, com o motivo e de onde viria."""
    return [_falta_do_kpi(k) for k in kpis_do_setor(chave) if k.no_relatorio is None]


# --- quem está no setor ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Membro:
    cnpj: str  # só os 14 caracteres
    empresa: str
    tickers: list[str]
    motivo: str


def _so_digitos(cnpj: str) -> str:
    return re.sub(r"[^0-9A-Za-z]", "", cnpj).upper()


def membros_pela_cvm(conexao: sa.Connection, chave: str) -> dict[str, tuple[str, str]]:
    """CNPJ → (empresa, setor) das companhias com ticker e setor da CVM do setor (banco do app)."""
    nomes = SETORES_DA_CVM.get(chave, ())
    if not nomes:
        return {}
    t = tickers_dos_emissores
    linhas = conexao.execute(
        sa.select(setores_cvm.c.cnpj, setores_cvm.c.setor, t.c.empresa)
        .join(t, t.c.cnpj == setores_cvm.c.cnpj)
        .where(setores_cvm.c.setor.in_(nomes))
        .order_by(t.c.empresa)
    ).all()
    return {_so_digitos(l.cnpj): (l.empresa, l.setor) for l in linhas}


def tickers_dos(conexao: sa.Connection, cnpjs: Iterable[str]) -> dict[str, list[str]]:
    """CNPJ (só os caracteres) → os códigos de negociação na B3, em ordem."""
    formatados = [cnpj_da_base.formatar(c) for c in cnpjs]
    if not formatados:
        return {}
    t = tickers_dos_emissores
    linhas = conexao.execute(
        sa.select(t.c.cnpj, t.c.codigo).where(t.c.cnpj.in_(formatados))
    ).all()
    tickers: dict[str, set[str]] = {}
    for linha in linhas:
        tickers.setdefault(_so_digitos(linha.cnpj), set()).add(linha.codigo)
    return {cnpj: sorted(codigos) for cnpj, codigos in tickers.items()}


def juntar_membros(
    da_noite: list[dict[str, Any]],
    da_cvm: Mapping[str, tuple[str, str]],
    tickers: Mapping[str, list[str]],
) -> list[Membro]:
    """Os membros da noite (ligação com a agência) e os do setor da CVM, cada um com o motivo."""
    motivos: dict[str, list[str]] = {}
    empresas: dict[str, str] = {}
    for linha in da_noite:
        cnpj = _so_digitos(str(linha["cnpj"]))
        empresas[cnpj] = str(linha["empresa"])
        motivos.setdefault(cnpj, []).append(str(linha["motivo"]))
    for cnpj, (empresa, setor) in da_cvm.items():
        empresas.setdefault(cnpj, empresa)
        motivos.setdefault(cnpj, []).append(f"setor da CVM: {setor}")
    membros = [
        Membro(cnpj, empresas[cnpj], list(tickers.get(cnpj, [])), "; ".join(motivo))
        for cnpj, motivo in motivos.items()
        if tickers.get(cnpj)  # sem ticker não é companhia da base aberta
    ]
    return sorted(membros, key=lambda m: m.empresa)


# --- as empresas lado a lado ----------------------------------------------------------------------

COLUNA_DA_EMPRESA = "Companhia"
COLUNA_DOS_TICKERS = "Tickers"
COLUNA_DE_QUANDO = "De quando"


def indicadores_do_membro(
    conexao: sa.Connection, cnpj: str
) -> dict[str, fundamentos.Indicador]:
    """Os indicadores do app (DFP e ITR) de um membro; {} sem demonstrações no banco."""
    dados = dados_da_empresa(conexao, cnpj_da_base.formatar(cnpj))
    if dados.contas.empty:
        return {}
    return {
        **fundamentos.calcular(dados, None).indicadores,
        **fundamentalista.calcular(dados).indicadores,
    }


def _texto_do_indicador(indicador: fundamentos.Indicador | None) -> str:
    if indicador is None or indicador.valor is None:
        return AINDA_SEM_DADO if indicador is None else "—"
    return escrever(indicador.valor, indicador.unidade)


def _margem_ebitda(caixa: Mapping[str, Any] | None) -> tuple[str, str]:
    """(margem EBITDA escrita, de quando): "ainda sem dado" sem a geração de caixa na ficha."""
    margem = (caixa or {}).get("margem_ebitda")
    if margem is None:
        return AINDA_SEM_DADO, ""
    return escrever(
        float(margem), fundamentos.FRACAO
    ), f"EBITDA: exercício {caixa['exercicio']}"  # type: ignore[index]


def _ultima_participacao(
    linhas: list[dict[str, Any]], cnpj: str, serie: str
) -> dict[str, Any] | None:
    """A linha mais recente da participação do membro na série (None: sem número)."""
    do_membro = [l for l in linhas if l["cnpj"] == cnpj and l["serie"] == serie]
    return max(do_membro, key=lambda l: l["ano"], default=None)


def _participacoes(
    setor: dossie_da_base.SetorDoLancamento,
    participacao: list[dict[str, Any]],
    cnpj: str,
) -> tuple[dict[str, str], list[str]]:
    """As colunas da parte do mercado de cada série do setor e de quando é cada uma."""
    colunas, quando = {}, []
    for nome in setor.series:
        medida = dossie.SERIES_DO_SETOR[nome].medida
        linha = _ultima_participacao(participacao, cnpj, nome)
        colunas[f"Parte do mercado: {medida}"] = (
            "—" if linha is None else dossie.fracao(linha["participacao"])
        )
        if linha is not None:
            quando.append(
                f"{medida.rsplit(' (', 1)[0]}: {dossie.mes(linha['ultimo_mes'])}"
            )
    return colunas, quando


def _linha_do_membro(
    setor: dossie_da_base.SetorDoLancamento,
    membro: Membro,
    indicadores: Mapping[str, fundamentos.Indicador],
    caixa: Mapping[str, Any] | None,
    participacao: list[dict[str, Any]],
) -> dict[str, str]:
    linha = {
        COLUNA_DA_EMPRESA: membro.empresa,
        COLUNA_DOS_TICKERS: ", ".join(membro.tickers),
    }
    for kpi in _DO_BANCO_DO_APP:
        linha[kpi.nome] = _texto_do_indicador(indicadores.get(kpi.no_relatorio or ""))
    linha[_DA_GERACAO_DE_CAIXA.nome], quando_do_ebitda = _margem_ebitda(caixa)
    partes, quando_da_parte = _participacoes(setor, participacao, membro.cnpj)
    linha |= partes
    receita = indicadores.get("receita")
    quando = [
        *([receita.base] if receita and receita.base else []),
        *([quando_do_ebitda] if quando_do_ebitda else []),
        *quando_da_parte,
    ]
    linha[COLUNA_DE_QUANDO] = "; ".join(quando) or "—"
    return linha


def lado_a_lado(
    setor: dossie_da_base.SetorDoLancamento,
    membros: list[Membro],
    indicadores: Mapping[str, Mapping[str, fundamentos.Indicador]],
    caixas: Mapping[str, Mapping[str, Any] | None],
    participacao: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Uma linha por membro, na ordem do nome: os KPIs comuns do app, a margem EBITDA da ficha e a
    parte do mercado de cada série do setor, com a coluna de quando é cada número."""
    return [
        _linha_do_membro(
            setor,
            membro,
            indicadores.get(membro.cnpj, {}),
            caixas.get(membro.cnpj),
            participacao,
        )
        for membro in membros
    ]


# --- o que os dados mostram (frases por regra) ----------------------------------------------------


@dataclass(frozen=True)
class Frase:
    """Uma frase de "O que os dados mostram", com o id de cada número de onde ela saiu."""

    texto: str
    ids: tuple[str, ...]


MINIMO_DE_FRASES, MAXIMO_DE_FRASES = 3, 5
MESES_DO_ANO_COMPLETO = 12


def _nome_curto(medida: str) -> str:
    """ "Beneficiários de planos de saúde (ANS)" → "beneficiários de planos de saúde (ANS)"."""
    return medida[:1].lower() + medida[1:]


def _mais_nova(linhas: list[dict[str, Any]]) -> dict[str, Any]:
    return max(linhas, key=lambda linha: linha["ano"])


def _frase_do_hhi(nome: str, concentracao: list[dict[str, Any]]) -> Frase | None:
    if not concentracao:
        return None
    linha = _mais_nova(concentracao)
    medida = _nome_curto(dossie.SERIES_DO_SETOR[nome].medida)
    texto = (
        f"Em {linha['ano']}, o HHI de {medida} foi de {dossie.inteiro(linha['hhi'])} pontos, "
        f"na faixa {linha['faixa']} do Guia H do CADE"
    )
    delta = linha.get("delta_hhi")
    if delta is not None:
        anterior = int(linha["ano"]) - 1
        if delta == 0:
            texto += f", igual a {anterior}"
        else:
            sentido = "acima" if delta > 0 else "abaixo"
            texto += f", {dossie.inteiro(abs(delta))} pontos {sentido} de {anterior}"
    ids = (f"hhi_{nome}", f"concentracao_{nome}/{linha['ano']}")
    return Frase(texto + ".", ids)


def _frase_da_cr4(nome: str, concentracao: list[dict[str, Any]]) -> Frase | None:
    if not concentracao:
        return None
    linha = _mais_nova(concentracao)
    medida = _nome_curto(dossie.SERIES_DO_SETOR[nome].medida)
    texto = (
        f"Os 4 maiores participantes somaram {dossie.fracao(linha['cr4'])} de {medida} em "
        f"{linha['ano']}, entre {dossie.inteiro(linha['participantes'])} participantes."
    )
    return Frase(texto, (f"cr4_{nome}", f"concentracao_{nome}/{linha['ano']}"))


def _do_ano(
    participacao: list[dict[str, Any]], nome: str
) -> tuple[int, list[dict[str, Any]]]:
    """O ano mais recente da série na participação e as linhas dele."""
    da_serie = [l for l in participacao if l["serie"] == nome]
    if not da_serie:
        return 0, []
    ano = max(l["ano"] for l in da_serie)
    return ano, [l for l in da_serie if l["ano"] == ano]


def _id_da_participacao(linha: Mapping[str, Any]) -> str:
    return f"participacao_dos_membros/{linha['cnpj']}/{linha['serie']}/{linha['ano']}"


def _frase_da_soma(nome: str, participacao: list[dict[str, Any]]) -> Frase | None:
    ano, linhas = _do_ano(participacao, nome)
    if not linhas:
        return None
    soma = sum(float(l["participacao"]) for l in linhas)
    medida = _nome_curto(dossie.SERIES_DO_SETOR[nome].medida)
    quantas = (
        "a única companhia aberta da base tinha"
        if len(linhas) == 1
        else f"as {len(linhas)} companhias abertas da base somavam"
    )
    texto = f"Em {ano}, {quantas} {dossie.fracao(soma)} de {medida}."
    return Frase(texto, ("membros", *(_id_da_participacao(l) for l in linhas)))


def _frase_da_maior_parte(
    nome: str, participacao: list[dict[str, Any]]
) -> Frase | None:
    ano, linhas = _do_ano(participacao, nome)
    if len(linhas) < 2:  # com uma só, a maior é a soma (a frase de cima já diz)
        return None
    maior = max(linhas, key=lambda l: float(l["participacao"]))
    medida = _nome_curto(dossie.SERIES_DO_SETOR[nome].medida)
    texto = (
        f"Entre as companhias abertas da base, a maior parte de {medida} em {ano} é a da "
        f"{maior['empresa']}: {dossie.fracao(maior['participacao'])}."
    )
    return Frase(texto, (_id_da_participacao(maior),))


def _variacoes(
    participacao: list[dict[str, Any]], nome: str
) -> list[tuple[float, dict, dict]]:
    """(variação, linha anterior, linha do ano) de cada membro entre os dois anos completos mais novos."""
    completos = sorted(
        {
            l["ano"]
            for l in participacao
            if l["serie"] == nome and l["meses"] == MESES_DO_ANO_COMPLETO
        },
        reverse=True,
    )
    if len(completos) < 2 or completos[0] - completos[1] != 1:
        return []
    por_ano = {
        ano: {
            l["cnpj"]: l for l in participacao if l["serie"] == nome and l["ano"] == ano
        }
        for ano in completos[:2]
    }
    novo, velho = por_ano[completos[0]], por_ano[completos[1]]
    return [
        (
            float(novo[c]["participacao"]) - float(velho[c]["participacao"]),
            velho[c],
            novo[c],
        )
        for c in novo.keys() & velho.keys()
    ]


def _frase_da_variacao(nome: str, participacao: list[dict[str, Any]]) -> Frase | None:
    variacoes = _variacoes(participacao, nome)
    if not variacoes:
        return None
    variacao, velha, nova = max(variacoes, key=lambda v: (abs(v[0]), v[2]["cnpj"]))
    medida = _nome_curto(dossie.SERIES_DO_SETOR[nome].medida)
    pontos = dossie.decimal(abs(variacao) * 100)
    sentido = "subiu" if variacao > 0 else "caiu" if variacao < 0 else "ficou igual"
    unidade = "ponto percentual" if pontos == "1,0" else "pontos percentuais"
    detalhe = "" if variacao == 0 else f" {pontos} {unidade}"
    texto = (
        f"De {velha['ano']} para {nova['ano']}, a maior variação de parte de {medida} entre as "
        f"companhias abertas da base foi a da {nova['empresa']}: {sentido}{detalhe}, de "
        f"{dossie.fracao(velha['participacao'])} para {dossie.fracao(nova['participacao'])}."
    )
    return Frase(texto, (_id_da_participacao(velha), _id_da_participacao(nova)))


def frases_por_regra(
    setor: dossie_da_base.SetorDoLancamento, secao: dossie.SecaoDaFicha
) -> list[Frase]:
    """De 3 a 5 frases fixas sobre a série principal do setor (a 1ª que a noite trouxe): a faixa do
    HHI e quanto ele mudou, a CR4, quanto as companhias abertas somam, a maior parte entre elas e a
    maior variação de parte. Menos de 3 números, nenhuma frase."""
    participacao = secao.tabelas.get("participacao_dos_membros", [])
    nome = next(
        (n for n in setor.series if secao.tabelas.get(f"concentracao_{n}")), None
    )
    if nome is None:
        return []
    concentracao = secao.tabelas[f"concentracao_{nome}"]
    regras = (
        _frase_do_hhi(nome, concentracao),
        _frase_da_cr4(nome, concentracao),
        _frase_da_soma(nome, participacao),
        _frase_da_maior_parte(nome, participacao),
        _frase_da_variacao(nome, participacao),
    )
    frases = [f for f in regras if f is not None]
    return frases[:MAXIMO_DE_FRASES] if len(frases) >= MINIMO_DE_FRASES else []


# --- o relatório ----------------------------------------------------------------------------------

TITULOS = {
    "membros": "Quem está no setor",
    "tamanho": "Tamanho do setor",
    "concentracao": "Concentração",
    "participacao": "Participação de cada companhia aberta",
    "lado_a_lado": "Empresas lado a lado",
    "cruzamentos": "Cruzamentos",
    "o_que_os_dados_mostram": "O que os dados mostram",
    "nao_temos": "O que não temos",
    "metodologia": "Metodologia",
}
ORDEM_DAS_SECOES = tuple(TITULOS)
# as seções com números da base: trancadas sem o dossiê da base no plano
DA_BASE = frozenset(
    {
        "tamanho",
        "concentracao",
        "participacao",
        "lado_a_lado",
        "cruzamentos",
        "o_que_os_dados_mostram",
    }
)
TITULOS_DAS_TABELAS = {
    "membros": "Companhias abertas do setor",
    "lado_a_lado": "Indicadores de cada companhia",
    "nao_temos": "KPIs que o relatório ainda não mostra",
}
_TITULO_POR_PREFIXO = (
    ("tamanho_", "Tamanho do mercado: {}"),
    ("participacao_", "Participação das companhias abertas: {}"),
)


def titulo_da_tabela(chave: str) -> str:
    """O título de uma tabela do relatório do setor (o mesmo na página, na API e no PDF)."""
    if chave in TITULOS_DAS_TABELAS:
        return TITULOS_DAS_TABELAS[chave]
    for prefixo, titulo in _TITULO_POR_PREFIXO:
        serie = dossie.SERIES_DO_SETOR.get(chave.removeprefix(prefixo))
        if chave.startswith(prefixo) and serie is not None:
            return titulo.format(serie.medida)
    return dossie.titulo_da_tabela(chave)


SEM_A_NOITE = (
    "A ficha deste setor ainda não chegou da base do TickerLab: por enquanto só aparecem as "
    "companhias pelo setor da CVM e os números do banco do app."
)
SEM_FICHAS_PARA_CRUZAR = "Nenhuma companhia do setor tem a ficha da noite na base ainda: sem ela não há o que cruzar."
SEM_FRASES = "Ainda não há números suficientes do setor para as frases desta seção."
SOBRE_AS_FRASES = (
    "Frases montadas por regras fixas sobre os números acima (não por um modelo de linguagem): "
    "cada uma diz de qual número saiu. Não são previsão nem recomendação de investimento."
)
SOBRE_O_LADO_A_LADO = (
    "Os indicadores são os mesmos do relatório da empresa, das DFP e dos ITR no banco do app. A "
    'margem EBITDA vem da ficha da noite de cada companhia e aparece como "ainda sem dado" até a '
    "ficha trazer a geração de caixa. A ordem das linhas é a do nome, não um ranking."
)
SOBRE_OS_MEMBROS = (
    "Entra a companhia aberta com ticker que a base liga a uma entidade da agência do setor ({agencia}) "
    "ou que tem o setor da CVM {setores}. A coluna do motivo diz qual das duas regras valeu."
)
SOBRE_O_QUE_NAO_TEMOS = (
    "Cada KPI que um analista do setor procuraria e que o relatório não mostra, com o motivo e de "
    "onde viria. Os códigos: R, release ou ITR da empresa; P, pedido ou coleta pública nova; S e T, "
    "séries da mesa Dados; $, dado pago."
)
LIMITES_DO_SETOR = (
    (
        "A concentração é a do mercado nacional que a agência publica, não o mercado relevante do "
        "CADE (região e produto, caso a caso). A faixa é a do Guia H do CADE, não um juízo do "
        "TickerLab."
    ),
    "A participação e o lado a lado mostram só as companhias abertas da base.",
    "Nada aqui é recomendação de investimento, previsão do setor ou nota das empresas.",
)


@dataclass(frozen=True)
class RelatorioDoSetor:
    setor: str
    nome: str
    # o dia da ficha da noite (None: a noite não trouxe o setor)
    como_era_em: date | None
    membros: list[Membro]
    secoes: list[Secao]
    frases: list[Frase]
    nao_temos: list[FaltaNoSetor]
    fontes: list[str]
    limites: list[str]
    avisos: list[str] = field(default_factory=list)

    def como_dict(self) -> dict:
        return para_json(asdict(self))  # type: ignore[return-value]


@dataclass(frozen=True)
class EntradasDoSetor:
    """O que o relatório do setor lê, já buscado (a montagem não abre banco nem arquivo)."""

    setor: dossie_da_base.SetorDoLancamento
    membros: list[Membro]
    da_noite: dossie.SecaoDoSetor | None
    indicadores: Mapping[str, Mapping[str, fundamentos.Indicador]]
    caixas: Mapping[str, Mapping[str, Any] | None]
    # a ficha da noite de cada companhia (nome → ficha) para os cruzamentos; sem ficha, fora da conta
    fichas: Mapping[str, Ficha] = field(default_factory=dict)


def _item_dos_membros(membros: list[Membro]) -> Item:
    return Item(
        "membros",
        "Companhias abertas no setor",
        str(len(membros)),
        float(len(membros)),
        "companhias",
        MEDIDO_NO_CADASTRO,
        fonte=f"{FONTE_DO_SETOR} e ligações da base com a agência",
        sem_comparacao=IDENTIFICACAO,
    )


def _secao_dos_membros(e: EntradasDoSetor) -> Secao:
    linhas = [
        {
            COLUNA_DA_EMPRESA: m.empresa,
            "CNPJ": cnpj_da_base.formatar(m.cnpj),
            COLUNA_DOS_TICKERS: ", ".join(m.tickers),
            "Por que está no setor": m.motivo,
        }
        for m in e.membros
    ]
    nomes = SETORES_DA_CVM.get(e.setor.chave, ())
    setores = (
        " ou ".join(f'"{n}"' for n in nomes) if nomes else "(nenhum para este setor)"
    )
    sobre = SOBRE_OS_MEMBROS.format(agencia=e.setor.agencia, setores=setores)
    fontes = f"Fonte: {FONTE_DO_SETOR}; {FONTE_DOS_TICKERS}."
    return Secao(
        "membros",
        TITULOS["membros"],
        [_item_dos_membros(e.membros)],
        [sobre, fontes],
        {"membros": linhas} if linhas else {},
    )


def _itens(
    noite: dossie.SecaoDoSetor, prefixo: str, series: Iterable[str]
) -> list[Item]:
    return [
        noite.itens[f"{prefixo}{n}"] for n in series if f"{prefixo}{n}" in noite.itens
    ]


def _fontes_da_noite(noite: dossie.SecaoDoSetor) -> list[str]:
    return [f"Fonte: {fonte}." for fonte in noite.secao.fontes]


def _secao_do_tamanho(e: EntradasDoSetor, noite: dossie.SecaoDoSetor) -> Secao:
    tabelas = {}
    for nome in e.setor.series:
        linhas = noite.secao.tabelas.get(f"concentracao_{nome}", [])
        colunas = [c for c in dossie.colunas_da_tabela(f"concentracao_{nome}") or [] if c[0] in ("ano", "total", "meses", "ultimo_mes")]  # fmt: skip
        if linhas:
            tabelas[f"tamanho_{nome}"] = dossie.escrever_linhas(colunas, linhas)
    return Secao(
        "tamanho",
        TITULOS["tamanho"],
        _itens(noite, "mercado_", e.setor.series),
        _fontes_da_noite(noite),
        tabelas,
    )


def _secao_da_concentracao(e: EntradasDoSetor, noite: dossie.SecaoDoSetor) -> Secao:
    itens = [
        *_itens(noite, "hhi_", e.setor.series),
        *_itens(noite, "cr4_", e.setor.series),
    ]
    tabelas = {
        chave: dossie.escrever_linhas(dossie.colunas_da_tabela(chave) or [], linhas)
        for nome in e.setor.series
        if (linhas := noite.secao.tabelas.get(chave := f"concentracao_{nome}"))
    }
    return Secao(
        "concentracao",
        TITULOS["concentracao"],
        itens,
        [*noite.secao.paragrafos[:-1], *_fontes_da_noite(noite)],
        tabelas,
    )


def _secao_da_participacao(e: EntradasDoSetor, noite: dossie.SecaoDoSetor) -> Secao:
    participacao = noite.secao.tabelas.get("participacao_dos_membros", [])
    tabelas = {}
    for nome in e.setor.series:
        linhas = [l for l in participacao if l["serie"] == nome]
        if linhas:
            colunas = dossie.colunas_da_participacao(nome)
            tabelas[f"participacao_{nome}"] = dossie.escrever_linhas(colunas, linhas)
    return Secao(
        "participacao", TITULOS["participacao"], [], _fontes_da_noite(noite), tabelas
    )


def _secao_do_lado_a_lado(e: EntradasDoSetor) -> Secao:
    noite = e.da_noite
    participacao = (
        noite.secao.tabelas.get("participacao_dos_membros", []) if noite else []
    )
    linhas = lado_a_lado(e.setor, e.membros, e.indicadores, e.caixas, participacao)
    tabelas: dict[str, list[dict]] = {"lado_a_lado": linhas} if linhas else {}
    for chave, linhas_da_noite in noite.secao.tabelas.items() if noite else []:
        if chave.startswith(dossie.PREFIXO_DO_LADO_A_LADO) and linhas_da_noite:
            colunas = dossie.colunas_da_tabela(chave) or []
            tabelas[chave] = dossie.escrever_linhas(colunas, linhas_da_noite)
    fontes = [
        f"Fonte: {FONTE_DAS_DEMONSTRACOES}.",
        *(_fontes_da_noite(noite) if noite else []),
    ]
    return Secao(
        "lado_a_lado",
        TITULOS["lado_a_lado"],
        [],
        [SOBRE_O_LADO_A_LADO, *fontes],
        tabelas,
    )


def _paragrafo_do_cruzamento(c: cruzamentos.CruzamentoDoSetor) -> str:
    """O "K de N" do cruzamento, quem tem achado e a fonte: nenhuma frase sem lastro (ADR 0100)."""
    quem = f" Com achado: {', '.join(c.empresas)}." if c.empresas else ""
    fonte = f" Fonte: {'; '.join(c.fontes)}." if c.fontes else ""
    return f"{c.frase}{quem}{fonte}"


def _secao_dos_cruzamentos(e: EntradasDoSetor, hoje: date) -> Secao:
    paragrafos = [
        _paragrafo_do_cruzamento(c)
        for c in cruzamentos.cruzamentos_do_setor(e.fichas, hoje)
    ]
    if not e.fichas:
        paragrafos = [SEM_FICHAS_PARA_CRUZAR]
    return Secao(
        "cruzamentos",
        TITULOS["cruzamentos"],
        paragrafos=[*paragrafos, cruzamentos.LIMITE_DOS_CRUZAMENTOS],
    )


def _secao_das_frases(frases: list[Frase]) -> Secao:
    paragrafos = [f.texto for f in frases] if frases else [SEM_FRASES]
    return Secao(
        "o_que_os_dados_mostram",
        TITULOS["o_que_os_dados_mostram"],
        paragrafos=[*paragrafos, SOBRE_AS_FRASES],
    )


def _secao_do_que_nao_temos(faltas: list[FaltaNoSetor]) -> Secao:
    linhas = [
        {"KPI": f.kpi, "Motivo": f.motivo, "De onde viria": f.fonte} for f in faltas
    ]
    return Secao(
        "nao_temos",
        TITULOS["nao_temos"],
        paragrafos=[SOBRE_O_QUE_NAO_TEMOS],
        tabelas={"nao_temos": linhas},
    )


def _secao_da_metodologia() -> Secao:
    return Secao(
        "metodologia",
        TITULOS["metodologia"],
        paragrafos=[dossie_da_base.LIMITES["setor"]],
        recolhida=True,
    )


def _secoes_da_noite(e: EntradasDoSetor) -> list[Secao]:
    if e.da_noite is None:
        return []
    return [
        _secao_do_tamanho(e, e.da_noite),
        _secao_da_concentracao(e, e.da_noite),
        _secao_da_participacao(e, e.da_noite),
    ]


def _trancar(secoes: list[Secao], motivo: str) -> list[Secao]:
    convite = [f"{motivo} {CONVITE_DO_DOSSIE}"]
    return [
        Secao(s.chave, s.titulo, paragrafos=convite, trancada=True)
        if s.chave in DA_BASE
        else s
        for s in secoes
    ]


def _data_da_noite(dia: date, hoje: date) -> str:
    velha = (hoje - dia).days > dossie.DIAS_ATE_FICAR_VELHA
    return data_do_dossie(Dossie([], (), [], dia, velha))


def montar_relatorio_do_setor(
    e: EntradasDoSetor, plano: str | None, hoje: date
) -> RelatorioDoSetor:
    """O relatório do setor na ordem fixa; sem o dossiê da base no plano, as seções com números da
    base vêm trancadas (só o título e o convite). "O que não temos" vem sempre."""
    noite = e.da_noite
    frases = frases_por_regra(e.setor, noite.secao) if noite else []
    faltas = nao_temos(e.setor.chave)
    secoes = [
        _secao_dos_membros(e),
        *_secoes_da_noite(e),
        _secao_do_lado_a_lado(e),
        _secao_dos_cruzamentos(e, hoje),
        _secao_das_frases(frases),
        _secao_do_que_nao_temos(faltas),
        _secao_da_metodologia(),
    ]
    motivo = motivo_sem_acesso(plano, DOSSIE_DA_BASE)
    if motivo is None and noite is not None:
        data = _data_da_noite(noite.dia, hoje)
        secoes = [replace(s, paragrafos=[data, *s.paragrafos]) if s.chave in DA_BASE else s for s in secoes]  # fmt: skip
    if motivo is not None:
        secoes, frases = _trancar(secoes, motivo), []
    fontes = [FONTE_DO_SETOR, FONTE_DOS_TICKERS]
    if motivo is None:
        fontes += [FONTE_DAS_DEMONSTRACOES, *(noite.secao.fontes if noite else [])]
    return RelatorioDoSetor(
        setor=e.setor.chave,
        nome=e.setor.nome,
        como_era_em=noite.dia if noite else None,
        membros=e.membros,
        secoes=secoes,
        frases=frases,
        nao_temos=faltas,
        fontes=list(dict.fromkeys(fontes)),
        limites=com_a_contestacao(list(LIMITES_DO_SETOR)),
        avisos=[] if noite else [SEM_A_NOITE],
    )


# --- o pedido inteiro -----------------------------------------------------------------------------


def _membros(
    conexao: sa.Connection, chave: str, noite: dossie.SecaoDoSetor | None
) -> list[Membro]:
    da_noite = noite.secao.tabelas.get("membros", []) if noite else []
    da_cvm = membros_pela_cvm(conexao, chave)
    cnpjs = {*(_so_digitos(str(l["cnpj"])) for l in da_noite), *da_cvm}
    return juntar_membros(da_noite, da_cvm, tickers_dos(conexao, cnpjs))


def _fichas_dos_membros(membros: list[Membro], pasta: Path | None) -> dict[str, Ficha]:
    fichas = ((m.empresa, dossie.ficha_do(m.cnpj, pasta)) for m in membros)
    return {nome: ficha for nome, ficha in fichas if ficha is not None}


def entradas_do_setor(
    conexao: sa.Connection, chave: str, pasta: Path | None = None
) -> EntradasDoSetor:
    """Tudo o que o relatório do setor lê: a seção da noite, os membros e os números de cada um."""
    setor = setor_do_relatorio(chave)
    noite = dossie.secao_do_setor(chave, pasta)
    membros = _membros(conexao, chave, noite)
    return EntradasDoSetor(
        setor=setor,
        membros=membros,
        da_noite=noite,
        indicadores={m.cnpj: indicadores_do_membro(conexao, m.cnpj) for m in membros},
        caixas={m.cnpj: dossie.caixa_do_par(m.cnpj, pasta) for m in membros},
        fichas=_fichas_dos_membros(membros, pasta),
    )


def relatorio_do_setor(
    conexao: sa.Connection,
    chave: str,
    plano: str | None,
    hoje: date | None = None,
    pasta: Path | None = None,
) -> RelatorioDoSetor:
    """O relatório do setor para o plano de quem pede; `SetorDesconhecidoError` fora da lista."""
    entradas = entradas_do_setor(conexao, chave, pasta)
    return montar_relatorio_do_setor(entradas, plano, hoje or datetime.now(FUSO).date())


@dataclass(frozen=True)
class SetorDisponivel:
    chave: str
    nome: str
    empresas: int  # quantas companhias abertas estão no setor
    # o dia da ficha da noite (None: a noite não trouxe o setor)
    como_era_em: date | None


def setores_disponiveis(
    conexao: sa.Connection, pasta: Path | None = None
) -> list[SetorDisponivel]:
    """Os setores do relatório, na ordem da lista do lançamento, com quantas companhias cada um tem."""
    disponiveis = []
    for setor in SETORES_DO_RELATORIO:
        noite = dossie.secao_do_setor(setor.chave, pasta)
        membros = _membros(conexao, setor.chave, noite)
        disponiveis.append(
            SetorDisponivel(
                setor.chave, setor.nome, len(membros), noite.dia if noite else None
            )
        )
    return disponiveis
