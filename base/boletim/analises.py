"""A análise do dia do boletim: um cruzamento curto da base, num rodízio pelo dia.

Cada análise consulta a base **pela porta** (`base.porta`, ADR 0077: SQL do DuckDB sobre as views
das tabelas, só com as colunas que usa e, quando dá, já somando) e devolve uma `Secao` (título, pergunta, números de destaque,
uma tabela, o achado em uma frase, os limites e os números para o parágrafo da IA).

**Travas (ADR 0075, LGPD; regras do boletim):**
- só lê tabelas da lista `TABELAS_PERMITIDAS` (nenhuma tem pessoas; `consultar` recusa as outras);
- **só números somados:** nenhuma empresa, fundo ou pessoa aparece com nome (o teste procura um nome
  plantado em todas as tabelas);
- nada de "crise" ou "fraude"; insolvência é só a contagem do que a empresa informou à CVM.
"""

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from base.boletim import fotografia as fo
from base.boletim.formato import grande, num, pct, reais, tamanho
from base.porta import Porta
from base.porta.rede import views

TABELAS_PERMITIDAS = frozenset(
    {"ratings", "pgfn_divida", "insolvencia", "trocas_de_auditor", "curva_juros", "eventos",
     "ofertas_resolucao_160", "ligacoes"}
)  # fmt: skip


class TabelaProibidaError(ValueError):
    """A análise tentou ler uma tabela fora da lista permitida."""


class TabelaFaltandoError(LookupError):
    """A tabela da análise não está na base (o rodízio passa para a próxima)."""


@dataclass(frozen=True)
class Contexto:
    raiz: Path  # a pasta base/ do acervo
    hoje: date
    foto: dict[str, Any]
    porta: Porta  # aberta na mesma `raiz`


@dataclass(frozen=True)
class Secao:
    nome: str
    titulo: str
    pergunta: str
    kpis: list[tuple[str, str]]
    cabecalho: list[str]
    linhas: list[list[str]]
    achado: str
    limites: str
    fonte: str
    numeros: dict[str, Any] = field(default_factory=dict)


def consultar(
    ctx: Contexto, tabela: str, sql: str, parametros: dict[str, object] | None = None
) -> pd.DataFrame:
    """Uma consulta à view `tabela` da porta (`{t}` no SQL é o nome dela)."""
    if tabela not in TABELAS_PERMITIDAS:
        raise TabelaProibidaError(f"o boletim não lê {tabela}")
    if tabela not in views(ctx.porta.con):
        raise TabelaFaltandoError(tabela)
    return ctx.porta.con.execute(
        sql.replace("{t}", f'"{tabela}"'), parametros or {}
    ).df()


# --- 1. retrato da base (só a fotografia) ---------------------------------------------------------
def retrato(ctx: Contexto) -> Secao:
    grupos = fo.por_grupo(ctx.foto)
    tabelas = ctx.foto["tabelas"]
    total = sum(g["linhas"] for g in grupos.values()) or 1
    por_licenca: dict[str, int] = {}
    for t in tabelas.values():
        marca = t["licenca"] or "sem marca"
        por_licenca[marca] = por_licenca.get(marca, 0) + (t["linhas"] or 0)
    maiores = sorted(grupos.items(), key=lambda kv: -kv[1]["linhas"])[:10]
    sem_marca = por_licenca.get("sem marca", 0) / total
    vendavel = por_licenca.get("vendavel", 0) / total
    return Secao(
        nome="retrato",
        titulo="Do que a base é feita hoje",
        pergunta="Quais conjuntos pesam mais e quanto já tem a marca de licença no manifesto?",
        kpis=[
            ("tabelas", num(len(tabelas))),
            ("linhas", grande(total)),
            ("no disco", tamanho(sum(g["bytes"] for g in grupos.values()))),
            ("linhas vendáveis", pct(vendavel)),
        ],
        cabecalho=["Conjunto", "Tabelas", "Linhas", "% das linhas", "Disco"],
        linhas=[
            [
                nome,
                num(g["tabelas"]),
                grande(g["linhas"]),
                pct(g["linhas"] / total),
                tamanho(g["bytes"]),
            ]
            for nome, g in maiores
        ],
        achado=(
            f"{pct(sem_marca)} das linhas ainda estão em tabelas sem marca de licença no manifesto; "
            f"{pct(vendavel)} já estão marcadas como vendáveis (ADR 0008, Emenda 1)."
        ),
        limites="Conta linhas pelos manifestos; tabela sem manifesto entra sem linhas.",
        fonte="manifestos da base",
        numeros={
            "tabelas": len(tabelas),
            "linhas": total,
            "linhas_por_licenca": por_licenca,
        },
    )


# --- 2. ratings ------------------------------------------------------------------------------------
FAIXAS = ["AAA", "AA", "A", "BBB", "BB", "B", "CCC ou abaixo", "RD, SD ou D"]
GRAU_DE_INVESTIMENTO = {"AAA", "AA", "A", "BBB"}
_NOTA = re.compile(r"AAA|Aaa|AA|Aa|BBB|Baa|BB|Ba|CCC|Caa|CC|Ca|RD|SD|A|B|C|D")
_FAIXA_DA_NOTA = {
    "AAA": "AAA", "Aaa": "AAA", "AA": "AA", "Aa": "AA", "A": "A", "BBB": "BBB", "Baa": "BBB",
    "BB": "BB", "Ba": "BB", "B": "B", "CCC": "CCC ou abaixo", "Caa": "CCC ou abaixo",
    "CC": "CCC ou abaixo", "Ca": "CCC ou abaixo", "C": "CCC ou abaixo",
    "RD": "RD, SD ou D", "SD": "RD, SD ou D", "D": "RD, SD ou D",
}  # fmt: skip
AGENCIAS = {"fitch": "Fitch", "sp": "S&P", "moodys": "Moody's"}


def faixa(nota: str | None) -> str:
    """A faixa da nota, igual nas três agências e nas escalas nacional e global."""
    if not isinstance(nota, str) or not nota.strip():
        return "sem nota"
    achada = _NOTA.search(nota)
    return _FAIXA_DA_NOTA[achada.group(0)] if achada else "sem nota"


def ratings(ctx: Contexto) -> Secao:
    t = consultar(ctx, "ratings", "SELECT agencia, nota, publico_em FROM {t}")
    t["faixa"] = t["nota"].map(faixa)
    t["agencia"] = t["agencia"].map(
        lambda a: AGENCIAS.get(a, a) if isinstance(a, str) else "sem agência"
    )
    contagem = pd.crosstab(t["agencia"], t["faixa"])
    linhas = [
        [ag, *[str(int(contagem.loc[ag].get(f, 0))) for f in FAIXAS], str(int(contagem.loc[ag].sum()))]
        for ag in contagem.index
    ]  # fmt: skip
    publico = pd.to_datetime(t["publico_em"])
    recentes = int((publico > pd.Timestamp(ctx.hoje - timedelta(days=30))).sum())
    grau = int(t["faixa"].isin(GRAU_DE_INVESTIMENTO).sum())
    abaixo = len(t) - grau
    return Secao(
        nome="ratings",
        titulo="Ratings publicados na CVM",
        pergunta="Como se distribuem as notas das agências nos documentos de rating já lidos?",
        kpis=[
            ("ratings lidos", num(len(t))),
            ("grau de investimento", pct(grau / len(t)) if len(t) else "—"),
            ("publicados em 30 dias", num(recentes)),
        ],
        cabecalho=["Agência", *FAIXAS, "Total"],
        linhas=linhas,
        achado=(
            f"{num(grau)} de {num(len(t))} notas estão no grau de investimento (BBB ou acima); "
            f"{num(abaixo)} estão abaixo ou sem nota legível. A tabela cresce com o coletor de "
            "PDFs (de hora em hora), então a mistura ainda muda."
        ),
        limites=(
            "Só os documentos de rating que as companhias mandaram à CVM e o extrator conseguiu ler; "
            "escalas nacional e global juntas na mesma faixa."
        ),
        fonte="CVM, IPE (documentos de rating)",
        numeros={
            "ratings": len(t),
            "grau_de_investimento": grau,
            "ultimos_30_dias": recentes,
        },
    )


def _origens(pasta: Path) -> set[str]:
    """Os SHA-256 dos originais anotados nos manifestos de uma pasta (um retrato da PGFN)."""
    achados = set()
    for manifesto in pasta.glob("*.json"):
        try:
            origens = (
                json.loads(manifesto.read_text(encoding="utf-8")).get("origens") or []
            )
        except (OSError, ValueError):
            continue
        achados |= {
            o["sha256"] for o in origens if isinstance(o, dict) and o.get("sha256")
        }
    return achados


# --- 3. PGFN ---------------------------------------------------------------------------------------
TIPOS_DE_DIVIDA = {
    "nao_previdenciaria": "Não previdenciária",
    "previdenciaria": "Previdenciária",
    "fgts": "FGTS",
}


def pgfn(ctx: Contexto) -> Secao:
    retratos = sorted(
        {n.split("/")[1] for n in ctx.foto["tabelas"] if n.startswith("pgfn_divida/") and n.count("/") == 2}
    )  # fmt: skip
    if not retratos:
        raise TabelaFaltandoError("pgfn_divida")
    mais_novo = retratos[-1]
    origens = sorted(_origens(ctx.raiz / "pgfn_divida" / mais_novo))
    if (
        len(retratos) > 1 and not origens
    ):  # sem como separar os retratos: melhor não somar
        raise TabelaFaltandoError(
            "pgfn_divida (retrato mais novo sem origens no manifesto)"
        )
    so_o_retrato = (
        "AND origem_sha256 IN (SELECT unnest($origens))" if len(retratos) > 1 else ""
    )
    soma = consultar(
        ctx,
        "pgfn_divida",
        "SELECT tipo_divida, sum(inscricoes) AS inscricoes, sum(valor_consolidado) AS valor_consolidado, "
        "sum(CASE WHEN ajuizado THEN valor_consolidado ELSE 0 END) AS valor_ajuizado "
        f"FROM {{t}} WHERE NOT coalesce(trata_como_pessoa, false) {so_o_retrato} "
        "GROUP BY tipo_divida ORDER BY valor_consolidado DESC",
        {"origens": origens} if so_o_retrato else None,
    ).set_index("tipo_divida")  # fmt: skip
    valor = float(soma["valor_consolidado"].sum())
    ajuizado = float(soma["valor_ajuizado"].sum()) / valor if valor else 0.0
    inscricoes = int(soma["inscricoes"].sum())
    linhas = [
        [TIPOS_DE_DIVIDA.get(str(tipo), str(tipo)), grande(int(l["inscricoes"])), reais(l["valor_consolidado"]),
         pct(l["valor_consolidado"] / valor if valor else None), pct(l["valor_ajuizado"] / l["valor_consolidado"] if l["valor_consolidado"] else None)]
        for tipo, l in soma.iterrows()
    ]  # fmt: skip
    maior = (
        TIPOS_DE_DIVIDA.get(str(soma.index[0]), str(soma.index[0]))
        if len(soma)
        else "—"
    )
    return Secao(
        nome="pgfn",
        titulo="Dívida ativa da União (empresas)",
        pergunta="Quanto as empresas devem à União, de que tipo e quanto já está na Justiça?",
        kpis=[
            ("retrato", mais_novo),
            ("valor consolidado", reais(valor)),
            ("inscrições", grande(inscricoes)),
            ("ajuizado (valor)", pct(ajuizado)),
        ],
        cabecalho=["Tipo de dívida", "Inscrições", "Valor", "% do valor", "% ajuizado"],
        linhas=linhas,
        achado=(
            f"A maior parte do valor é de dívida {maior.lower()}; {pct(ajuizado)} do valor total já "
            "está em execução fiscal."
        ),
        limites="Só pessoas jurídicas; retrato trimestral da PGFN, somado. Licença ainda a confirmar.",
        fonte="PGFN, dados abertos da dívida ativa",
        numeros={
            "retrato": mais_novo,
            "valor": valor,
            "inscricoes": inscricoes,
            "ajuizado": ajuizado,
        },
    )


# --- 4. insolvência (só contagem) -------------------------------------------------------------------
EVENTOS_DE_INSOLVENCIA = {
    "recuperacao_judicial": "Recuperação judicial",
    "recuperacao_extrajudicial": "Recuperação extrajudicial",
    "falencia": "Falência",
    "liquidacao": "Liquidação",
}


def insolvencia(ctx: Contexto) -> Secao:
    t = consultar(ctx, "insolvencia", "SELECT cnpj, rotulo, referencia FROM {t}")
    t = t[t["rotulo"].isin(EVENTOS_DE_INSOLVENCIA)]  # sem "exposicao_a_terceiro"
    t["ano"] = pd.to_datetime(t["referencia"]).dt.year
    t = t[t["ano"] >= ctx.hoje.year - 9]
    por = t.groupby(["ano", "rotulo"])["cnpj"].nunique().unstack(fill_value=0)
    linhas = []
    for ano in sorted(por.index, reverse=True):
        valores = [int(por.loc[ano].get(r, 0)) for r in EVENTOS_DE_INSOLVENCIA]
        linhas.append(
            [
                str(ano),
                *[str(v) for v in valores],
                str(t[t["ano"] == ano]["cnpj"].nunique()),
            ]
        )
    empresas = int(t["cnpj"].nunique())
    rj = (
        por["recuperacao_judicial"]
        if "recuperacao_judicial" in por
        else pd.Series(dtype=int)
    )
    ano_pico = int(rj.idxmax()) if len(rj) and rj.max() > 0 else None
    return Secao(
        nome="insolvencia",
        titulo="Recuperação judicial, falência e liquidação por ano",
        pergunta="Quantas companhias informaram à CVM um evento de insolvência próprio, ano a ano?",
        kpis=[
            ("companhias em 10 anos", num(empresas)),
            ("ano com mais RJ", str(ano_pico) if ano_pico else "—"),
        ],
        cabecalho=["Ano", *EVENTOS_DE_INSOLVENCIA.values(), "Companhias"],
        linhas=linhas,
        achado=(
            f"{num(empresas)} companhias informaram algum desses eventos nos últimos 10 anos"
            + (
                f"; {ano_pico} foi o ano com mais recuperações judiciais."
                if ano_pico
                else "."
            )
        ),
        limites=(
            "Conta companhias (CNPJ) com documento sobre o evento no ano, não documentos: uma RJ em "
            "curso conta em cada ano em que há documento. Só o que foi informado à CVM e lido pela "
            "regra do rótulo (exposição a um terceiro fica de fora). Nenhuma é nomeada."
        ),
        fonte="CVM, IPE (fatos relevantes e comunicados)",
        numeros={"empresas": empresas, "ano_com_mais_rj": ano_pico},
    )


# --- 5. trocas de auditor --------------------------------------------------------------------------
def trocas_de_auditor(ctx: Contexto) -> Secao:
    t = consultar(
        ctx, "trocas_de_auditor", "SELECT efetiva_em, anos_com_o_anterior FROM {t}"
    )
    t["ano"] = pd.to_datetime(t["efetiva_em"]).dt.year
    t = t[t["ano"] >= ctx.hoje.year - 14]
    por = t.groupby("ano").agg(
        trocas=("ano", "size"), mediana=("anos_com_o_anterior", "median")
    )
    ano_com_mais = int(por["trocas"].idxmax()) if len(por) else None
    return Secao(
        nome="trocas_de_auditor",
        titulo="Trocas de auditor por ano",
        pergunta="Quando as companhias trocam de auditor, e depois de quantos anos com o anterior?",
        kpis=[
            ("trocas em 15 anos", num(int(por["trocas"].sum()))),
            ("ano com mais", str(ano_com_mais) if ano_com_mais else "—"),
            (
                "mediana com o anterior",
                f"{num(t['anos_com_o_anterior'].median(), 1)} anos",
            ),
        ],
        cabecalho=["Ano", "Trocas", "Mediana de anos com o anterior"],
        linhas=[
            [str(a), str(int(l["trocas"])), num(l["mediana"], 1)]
            for a, l in por.iterrows()
        ],
        achado=(
            "Os picos de cinco em cinco anos combinam com o rodízio obrigatório de auditor da CVM "
            f"(no máximo 5 anos seguidos com o mesmo); {ano_com_mais} foi o ano com mais trocas."
        ),
        limites="Ano em que a troca vale (efetiva_em); só companhias abertas com FRE na CVM.",
        fonte="CVM, FRE (auditores)",
        numeros={"ano_com_mais": ano_com_mais, "trocas": int(por["trocas"].sum())},
    )


# --- 6. curva de juros -----------------------------------------------------------------------------
PRAZOS = [1.0, 2.0, 5.0, 10.0]


def _taxa(t: pd.DataFrame, dia: pd.Timestamp, curva: str, prazo: float) -> float | None:
    linha = t[
        (t["data_base"] == dia) & (t["curva"] == curva) & (t["prazo_anos"] == prazo)
    ]
    return float(linha["taxa"].iloc[0]) if len(linha) else None


def _dia_ate(t: pd.DataFrame, limite: pd.Timestamp) -> pd.Timestamp | None:
    dias = t.loc[t["data_base"] <= limite, "data_base"]
    return dias.max() if len(dias) else None


def curva_juros(ctx: Contexto) -> Secao:
    t = consultar(
        ctx,
        "curva_juros",
        "SELECT data_base, curva, prazo_anos, taxa FROM {t} WHERE data_base >= $desde",
        {"desde": date(ctx.hoje.year - 1, 1, 1)},
    )
    t["data_base"] = pd.to_datetime(t["data_base"])
    hoje = t["data_base"].max()
    mes = _dia_ate(t, hoje - pd.Timedelta(days=30))
    ano = _dia_ate(t, hoje - pd.Timedelta(days=365))
    linhas, numeros = [], {"data_base": hoje.date().isoformat()}
    for curva, nome in (("nominal", "Nominal (prefixado)"), ("real", "Real (IPCA+)")):
        for prazo in PRAZOS:
            agora = _taxa(t, hoje, curva, prazo)
            if agora is None:
                continue
            antes_mes = _taxa(t, mes, curva, prazo) if mes is not None else None
            antes_ano = _taxa(t, ano, curva, prazo) if ano is not None else None
            linhas.append(
                [
                    nome,
                    f"{num(prazo, 0)} ano(s)",
                    pct(agora, 2),
                    pct(antes_mes, 2),
                    pct(antes_ano, 2),
                ]
            )
            chave = f"{curva}_{int(prazo)}a"
            numeros |= {
                chave: agora,
                f"{chave}_ha_um_mes": antes_mes,
                f"{chave}_ha_um_ano": antes_ano,
            }
    curto = numeros.get("nominal_1a")
    prazo_longo = max(
        (int(p) for p in PRAZOS if numeros.get(f"nominal_{int(p)}a") is not None),
        default=None,
    )
    longo = (
        numeros.get(f"nominal_{prazo_longo}a")
        if prazo_longo and prazo_longo > 1
        else None
    )
    inclinacao = longo - curto if curto is not None and longo is not None else None
    numeros |= {"inclinacao_nominal": inclinacao, "prazo_longo_nominal": prazo_longo}
    if inclinacao is None:
        achado = "Falta o prazo longo da curva prefixada nesta data-base."
    else:
        forma = (
            "invertida (o curto paga mais que o longo)" if inclinacao < -0.001
            else "positiva (o longo paga mais)" if inclinacao > 0.001
            else "quase plana"
        )  # fmt: skip
        achado = f"A curva prefixada está {forma} entre 1 e {prazo_longo} anos."
    return Secao(
        nome="curva_juros",
        titulo="Curva de juros do Tesouro",
        pergunta="Como estão os juros de 1 a 10 anos hoje, contra um mês e um ano atrás?",
        kpis=[
            ("data-base", hoje.strftime("%d/%m/%Y")),
            ("prefixado 1 ano", pct(curto, 2)),
            (
                f"{prazo_longo} anos − 1 ano"
                if inclinacao is not None
                else "inclinação",
                f"{num(100 * inclinacao, 2)} p.p." if inclinacao is not None else "—",
            ),
        ],
        cabecalho=["Curva", "Prazo", "Hoje", "Há ~1 mês", "Há ~1 ano"],
        linhas=linhas,
        achado=achado,
        limites="Curva ajustada aos títulos públicos do dia; prazos fixos interpolados.",
        fonte="Tesouro Nacional, títulos do Tesouro Direto (curva_juros da base)",
        numeros=numeros,
    )


# --- 7. documentos das companhias ------------------------------------------------------------------
def eventos(ctx: Contexto) -> Secao:
    t = consultar(
        ctx,
        "eventos",
        "SELECT categoria, publicado_em FROM {t} WHERE publicado_em >= $desde",
        {"desde": date(ctx.hoje.year - 1, 1, 1)},
    )
    t["publicado_em"] = pd.to_datetime(t["publicado_em"])
    ate = t["publicado_em"].max()
    janela = t[
        (t["publicado_em"] > ate - pd.Timedelta(days=30)) & (t["publicado_em"] <= ate)
    ]
    um_ano = ate - pd.DateOffset(years=1)
    antes = t[
        (t["publicado_em"] > um_ano - pd.Timedelta(days=30))
        & (t["publicado_em"] <= um_ano)
    ]
    agora_por, antes_por = (
        janela["categoria"].value_counts(),
        antes["categoria"].value_counts(),
    )
    linhas = [
        [str(cat), num(int(n)), num(int(antes_por.get(cat, 0)))]
        for cat, n in agora_por.head(10).items()
    ]
    fatos = int(agora_por.get("Fato Relevante", 0))
    fatos_antes = int(antes_por.get("Fato Relevante", 0))
    return Secao(
        nome="eventos",
        titulo="O que as companhias publicaram nos últimos 30 dias",
        pergunta="Quantos documentos de cada tipo saíram no IPE, contra a mesma janela de um ano antes?",
        kpis=[
            ("documentos em 30 dias", num(len(janela))),
            ("fatos relevantes", num(fatos)),
            ("fatos relevantes, 1 ano antes", num(fatos_antes)),
        ],
        cabecalho=[
            "Categoria",
            "30 dias até " + ate.strftime("%d/%m"),
            "Mesma janela, 1 ano antes",
        ],
        linhas=linhas,
        achado=(
            f"{num(fatos)} fatos relevantes nos 30 dias até {ate.strftime('%d/%m/%Y')}, contra "
            f"{num(fatos_antes)} na mesma janela de {um_ano.year}."
        ),
        limites="A janela termina no documento mais novo da base, que chega com alguns dias de atraso.",
        fonte="CVM, IPE",
        numeros={
            "ate": ate.date().isoformat(),
            "documentos_30_dias": len(janela),
            "fatos_relevantes_30_dias": fatos,
            "fatos_relevantes_ano_anterior": fatos_antes,
        },
    )


# --- 8. ofertas públicas ---------------------------------------------------------------------------
def ofertas(ctx: Contexto) -> Secao:
    t = consultar(
        ctx,
        "ofertas_resolucao_160",
        "SELECT valor_mobiliario, data_registro, valor_total_registrado FROM {t}",
    )
    t["data_registro"] = pd.to_datetime(t["data_registro"])
    hoje = pd.Timestamp(ctx.hoje)
    ultimos = t[
        (t["data_registro"] > hoje - pd.DateOffset(years=1))
        & (t["data_registro"] <= hoje)
    ]
    antes = t[
        (t["data_registro"] > hoje - pd.DateOffset(years=2))
        & (t["data_registro"] <= hoje - pd.DateOffset(years=1))
    ]
    soma = ultimos.groupby("valor_mobiliario")["valor_total_registrado"].agg(
        ["sum", "size"]
    )
    soma_antes = antes.groupby("valor_mobiliario")["valor_total_registrado"].sum()
    soma = soma.sort_values("sum", ascending=False).head(10)
    valor, valor_antes = (
        float(ultimos["valor_total_registrado"].sum()),
        float(antes["valor_total_registrado"].sum()),
    )
    linhas = [
        [str(tipo), num(int(l["size"])), reais(l["sum"]), reais(soma_antes.get(tipo))]
        for tipo, l in soma.iterrows()
    ]
    variacao = valor / valor_antes - 1 if valor_antes else None
    return Secao(
        nome="ofertas",
        titulo="Ofertas públicas registradas (Resolução CVM 160)",
        pergunta="Quanto foi registrado em ofertas nos últimos 12 meses, e em quê?",
        kpis=[
            ("valor em 12 meses", reais(valor)),
            ("ofertas", num(len(ultimos))),
            (
                "contra os 12 anteriores",
                ("+" if variacao and variacao > 0 else "") + pct(variacao),
            ),
        ],
        cabecalho=[
            "Valor mobiliário",
            "Ofertas",
            "Valor (12 meses)",
            "Valor (12 meses antes)",
        ],
        linhas=linhas,
        achado=(
            f"{soma.index[0] if len(soma) else '—'} lidera o valor registrado nos últimos 12 meses."
        ),
        limites="Valor registrado, não o colocado; só o rito da Resolução 160 (desde 2023).",
        fonte="CVM, ofertas públicas",
        numeros={
            "valor_12_meses": valor,
            "valor_12_meses_antes": valor_antes,
            "ofertas": len(ultimos),
        },
    )


# --- 9. rede de entidades --------------------------------------------------------------------------
TIPOS_DE_LIGACAO = {
    "detem": "fundo detém ativo", "controlada_de": "controlada de", "participada_de": "participada de",
    "audita": "audita", "coligada_de": "coligada de", "emite": "emite", "do_conglomerado_de": "do conglomerado de",
    "opera_para": "opera para",
}  # fmt: skip


def rede(ctx: Contexto) -> Secao:
    t = consultar(ctx, "ligacoes", "SELECT tipo, fonte, ate, publico_em FROM {t}")
    ativas = t["ate"].isna()
    publico = pd.to_datetime(t["publico_em"])
    recentes = publico > pd.Timestamp(ctx.hoje - timedelta(days=30))
    por = t.assign(ativa=ativas, recente=recentes).groupby("tipo").agg(
        total=("tipo", "size"), ativas=("ativa", "sum"), recentes=("recente", "sum")
    ).sort_values("total", ascending=False)  # fmt: skip
    linhas = [
        [TIPOS_DE_LIGACAO.get(str(tipo), str(tipo)), grande(int(l["total"])), grande(int(l["ativas"])), num(int(l["recentes"]))]
        for tipo, l in por.iterrows()
    ]  # fmt: skip
    entre_empresas = t["tipo"] != "detem"
    sem_fundos = int(entre_empresas.sum())
    valendo = float(ativas[entre_empresas].mean()) if sem_fundos else None
    return Secao(
        nome="rede",
        titulo="A rede de entidades",
        pergunta="Que ligações a rede guarda, quantas seguem valendo e quantas ficaram públicas no mês?",
        kpis=[
            ("ligações", grande(len(t))),
            ("entre empresas", grande(sem_fundos)),
            ("delas, valendo hoje", pct(valendo)),
            ("públicas em 30 dias", num(int(recentes.sum()))),
        ],
        cabecalho=["Tipo de ligação", "Total", "Valendo", "Públicas em 30 dias"],
        linhas=linhas,
        achado=(
            f"Fora as posições mensais dos fundos, a rede tem {grande(sem_fundos)} ligações entre "
            f"empresas (controle, participação, auditoria, emissão); {pct(valendo)} delas seguem valendo."
        ),
        limites="Cada ligação tem a data em que ficou pública; o fim ainda usa a data do fato (ver o quadro).",
        fonte="CVM (CDA, FRE, FCA), BCB (IF.data)",
        numeros={
            "ligacoes": len(t),
            "ativas": int(ativas.sum()),
            "publicas_30_dias": int(recentes.sum()),
        },
    )


ANALISES: list[Callable[[Contexto], Secao]] = [
    retrato, ratings, pgfn, insolvencia, trocas_de_auditor, curva_juros, eventos, ofertas, rede,
]  # fmt: skip


TITULOS = {
    "retrato": "Do que a base é feita hoje",
    "ratings": "Ratings publicados na CVM",
    "pgfn": "Dívida ativa da União (empresas)",
    "insolvencia": "Recuperação judicial, falência e liquidação por ano",
    "trocas_de_auditor": "Trocas de auditor por ano",
    "curva_juros": "Curva de juros do Tesouro",
    "eventos": "O que as companhias publicaram nos últimos 30 dias",
    "ofertas": "Ofertas públicas registradas (Resolução CVM 160)",
    "rede": "A rede de entidades",
}


def titulo_do_dia(dia: date) -> str:
    """O título da análise que o rodízio escolhe para `dia` (se a tabela dela estiver na base)."""
    return TITULOS[ANALISES[dia.toordinal() % len(ANALISES)].__name__]


def analise_do_dia(ctx: Contexto) -> Secao:
    """A análise do rodízio para `ctx.hoje`; se a tabela dela faltar, a próxima da lista."""
    inicio = ctx.hoje.toordinal() % len(ANALISES)
    for passo in range(len(ANALISES)):
        try:
            return ANALISES[(inicio + passo) % len(ANALISES)](ctx)
        except TabelaFaltandoError:
            continue
    return retrato(ctx)
