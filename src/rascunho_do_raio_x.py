"""O rascunho do Raio-X em dia de evento (plano `2026-10-28-raio-x-todo-dia`, PR 6b, Tarefa 11).

Em dia de evento (`src/eventos_do_pregao.py`) o gerador do pregão grava, no acervo, o Raio-X do dia
(`src/raio_x.py`) em JSON, HTML e PDF. **Não é publicado:** texto novo é nível 1 e espera o "pode" do
Tiago, que lê o rascunho e decide se vira página. Por isso o HTML diz "RASCUNHO" no topo.

`secoes` monta o texto em tipos simples (título, parágrafos e uma tabela já escrita), e o HTML e o PDF
só desenham o mesmo conteúdo. "Fontes" e "Limites e cuidados" saem sempre.
"""

import html
from dataclasses import dataclass
from datetime import date, datetime

from src.relatorio_pdf import RelatorioPDF

TITULO = "Raio-X do pregão"
TITULO_DOS_LIMITES = "Limites e cuidados"
MENOS = "−"
LIMITES = (
    (
        "Rascunho gerado sozinho na madrugada seguinte ao pregão, com os arquivos oficiais da B3 e da "
        "CVM. Não foi revisado por uma pessoa e não está publicado."
    ),
    (
        "Só entram as empresas com giro de R$ 20 milhões ou mais na véspera; papel com evento (desdobramento, "
        "grupamento, provento grande) fica de fora até ser conferido."
    ),
    (
        "A dívida e o EBITDA são os do último balanço entregue à CVM até a véspera: podem ter meses de "
        "atraso. Bancos, seguradoras e financeiras ficam fora dessa conta."
    ),
    (
        "Os choques anteriores mostram o que o Ibovespa fez depois de outras quedas fortes. O passado não diz "
        "o que vem agora: poucas quedas, cada uma com a sua causa."
    ),
    "Nada aqui é recomendação de investimento.",
)
SEM_BALANCO = (
    "Sem os balanços da CVM nesta rodada: a queda por faixa de dívida ficou de fora."
)
SEM_CHOQUES = (
    "Nenhuma queda do Ibovespa desse tamanho antes deste pregão na série guardada."
)
AVISO_DO_RODAPE = "Rascunho, não publicado. Nada aqui é recomendação de investimento. Dados públicos da B3 e da CVM."


@dataclass(frozen=True)
class Tabela:
    cabecalho: list[str]
    linhas: list[list[str]]


@dataclass(frozen=True)
class Secao:
    titulo: str
    paragrafos: list[str]
    tabela: Tabela | None = None


def _numero(valor: float, casas: int = 1) -> str:
    """12345.6 → "12.345,6"; o menos vira o sinal tipográfico."""
    texto = f"{valor:,.{casas}f}".replace(",", "#").replace(".", ",").replace("#", ".")
    return texto.replace("-", MENOS)


def _percentual(fracao: float | None) -> str:
    """−0.1 → "−10,0%"; vazio → "—"."""
    if fracao is None:
        return "—"
    texto = _numero(fracao * 100)
    return f"+{texto}%" if round(fracao * 100, 1) > 0 else f"{texto}%"


def _data(iso: str) -> str:
    return f"{date.fromisoformat(iso):%d/%m/%Y}"


def _abertura(raio_x: dict) -> Secao:
    queda = raio_x["queda"]
    frase = (
        f"Em {_data(raio_x['pregao'])}, o Ibovespa variou {_percentual(raio_x['ibovespa']['variacao'])} "
        f"sobre o fechamento de {_data(raio_x['vespera'])}. Das {queda['empresas']} empresas com giro de "
        f"R$ 20 milhões ou mais na véspera, a mediana variou {_percentual(queda['mediana'])}: "
        f"{queda['subiram']} subiram, {queda['cairam']} caíram e {queda['quedas_fortes']} caíram "
        f"{_numero(abs(queda['limite_da_queda_forte']) * 100, 0)}% ou mais."
    )
    return Secao("O pregão", [frase])


def _setores(raio_x: dict) -> Secao:
    linhas = [
        [
            s["setor"],
            str(s["empresas"]),
            _percentual(s["mediana"]),
            _percentual(s["contra_o_indice"]),
        ]
        for s in raio_x["setores"]
    ]
    return Secao(
        "Setores",
        ["A mediana de cada setor, do que mais caiu ao que menos caiu."],
        Tabela(["Setor", "Empresas", "Mediana", "Contra o índice"], linhas),
    )


def _lista(titulo: str, papeis: list[dict]) -> Secao:
    linhas = [
        [p["simbolo"], p["empresa"], p["setor"], _percentual(p["variacao"])]
        for p in papeis
    ]
    return Secao(
        titulo,
        [],
        Tabela(["Papel", "Empresa", "Setor", "Variação"], linhas),
    )


def _divida(raio_x: dict) -> Secao:
    alavancagem = raio_x["alavancagem"]
    if not alavancagem or not alavancagem["faixas"]:
        return Secao("Queda e dívida", [SEM_BALANCO])
    paragrafos = [
        (
            f"A mediana do dia por faixa de dívida líquida / EBITDA, das {alavancagem['empresas']} "
            "empresas não financeiras com balanço público na véspera."
        )
    ]
    if alavancagem["spearman"] is not None:
        paragrafos.append(
            "Correlação de postos (Spearman) entre a alavancagem e a variação do dia: "
            f"{_numero(alavancagem['spearman'], 2)}."
        )
    linhas = [
        [f["faixa"], str(f["empresas"]), _percentual(f["mediana"])]
        for f in alavancagem["faixas"]
    ]
    return Secao(
        "Queda e dívida",
        paragrafos,
        Tabela(["Dívida líquida / EBITDA", "Empresas", "Mediana"], linhas),
    )


def _choques(raio_x: dict) -> Secao:
    choques = raio_x["choques_anteriores"]
    if not choques:
        return Secao("Choques anteriores do Ibovespa", [SEM_CHOQUES])
    prazos = list(choques[0]["depois"])
    linhas = [
        [_data(c["dia"]), _percentual(c["queda"])]
        + [_percentual(c["depois"][prazo]) for prazo in prazos]
        for c in choques
    ]
    return Secao(
        "Choques anteriores do Ibovespa",
        [
            "As quedas fortes do índice antes deste pregão e o que ele fez depois de cada uma."
        ],
        Tabela(["Dia", "Queda", *prazos], linhas),
    )


def secoes(raio_x: dict) -> list[Secao]:
    """O texto do rascunho, na ordem: o pregão, setores, listas, dívida, choques, fontes e limites."""
    return [
        _abertura(raio_x),
        _setores(raio_x),
        _lista("Maiores quedas", raio_x["maiores"]["quedas"]),
        _lista("Maiores altas", raio_x["maiores"]["altas"]),
        _divida(raio_x),
        _choques(raio_x),
        Secao("Fontes", [item["fonte"] for item in raio_x["fontes"].values()]),
        Secao(TITULO_DOS_LIMITES, list(LIMITES)),
    ]


# --- HTML ----------------------------------------------------------------------------------------


def _tabela_em_html(tabela: Tabela) -> str:
    cabecalho = "".join(f"<th>{html.escape(c)}</th>" for c in tabela.cabecalho)
    linhas = "".join(
        "<tr>" + "".join(f"<td>{html.escape(c)}</td>" for c in linha) + "</tr>"
        for linha in tabela.linhas
    )
    return f"<table><thead><tr>{cabecalho}</tr></thead><tbody>{linhas}</tbody></table>"


def em_html(raio_x: dict) -> str:
    """Uma página só, sem script nem arquivo de fora, para o Tiago ler o rascunho."""
    corpo = []
    for secao in secoes(raio_x):
        corpo.append(f"<h2>{html.escape(secao.titulo)}</h2>")
        corpo += [f"<p>{html.escape(p)}</p>" for p in secao.paragrafos]
        if secao.tabela:
            corpo.append(_tabela_em_html(secao.tabela))
    titulo = html.escape(f"{TITULO} de {_data(raio_x['pregao'])}")
    return (
        '<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
        f"<title>RASCUNHO · {titulo}</title>"
        "<style>body{font-family:sans-serif;max-width:860px;margin:2em auto;padding:0 16px}"
        "table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #ddd;padding:4px;"
        "text-align:left}.rascunho{background:#fff3cd;padding:8px}</style></head><body>"
        f'<p class="rascunho">RASCUNHO, não publicado: espera o "pode".</p><h1>{titulo}</h1>'
        + "".join(corpo)
        + "</body></html>"
    )


# --- PDF -----------------------------------------------------------------------------------------


def em_pdf(raio_x: dict, gerado_em: datetime) -> bytes:
    """O mesmo texto no papel timbrado (`src/relatorio_pdf.py`)."""
    todas = secoes(raio_x)
    pdf = RelatorioPDF(
        f"{TITULO} (rascunho)",
        _data(raio_x["pregao"]),
        gerado_em,
        aviso=AVISO_DO_RODAPE,
    )
    pdf.capa(
        [
            ("Pregão", _data(raio_x["pregao"])),
            ("Gerado em", f"{gerado_em:%d/%m/%Y às %H:%M}"),
        ],
        [s.titulo for s in todas],
    )
    pdf.add_page()
    pdf.aviso_destacado('Rascunho, não publicado: espera o "pode".')
    for secao in todas:
        pdf.secao(secao.titulo, reservar=40, numerada=True)
        for paragrafo in secao.paragrafos:
            pdf.paragrafo(paragrafo)
        if secao.tabela:
            pdf.tabela_de_texto(secao.tabela.cabecalho, secao.tabela.linhas)
    return pdf.para_bytes()
