"""Exporta o conteúdo do Python para o site em React (web/conteudo/*.json).

O Python continua a fonte da verdade (ADR 0048, item 3): módulos (`src/modulos.py`), páginas do app
(`src/paginas.py`), planos (`src/planos.py`), marca e cores do site (`src/marca.py`), estilos do
Report Studio, ativos de exemplo (`src/catalogo.py`) e a metodologia das notas
(`src/metodologia_das_notas.py`). O React lê estes JSON no build;
há teste que acusa quando um deles fica velho.

Uso: python -m scripts.exportar_conteudo
"""

import json
import re
from dataclasses import asdict
from pathlib import Path

import numpy as np

from scripts import gerar_site
from scripts.markdown_simples import markdown_para_html
from src import (
    analises,
    catalogo,
    comparacao,
    conformidade,
    ficha,
    formatos,
    marca,
    metodologia_das_notas,
    modulos,
    novidades,
    paginas,
    planos,
    qualidade_texto,
    regras_de_imposto,
)
from src import graficos_pdf as gp
from src import indicadores as ind
from src import juros_e_inflacao as ji
from src import linha_do_tempo as ldt
from src.autenticacao import AVISO_DA_ENTRADA
from src.conteudo import carregar_glossario
from src.envio_novidades import TEXTO_DO_CONSENTIMENTO as TEXTO_DAS_NOVIDADES
from src.envio_novidades import VERSAO_DO_CONSENTIMENTO as VERSAO_DAS_NOVIDADES
from src.estilos_pdf import ESTILOS
from src.estrategias import ESTRATEGIAS

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "web" / "conteudo"
# pontos do desenho do painel da página inicial (cinco anos: um ponto a cada ~4 semanas)
PONTOS_DO_PAINEL = 64
# a fita da página inicial: só o código (do catálogo) e um nome curto, nenhum preço
ATIVOS_DA_FITA = (
    ("PETR4.SA", "Petrobras"),
    ("VALE3.SA", "Vale"),
    ("ITUB4.SA", "Itaú Unibanco"),
    ("WEGE3.SA", "WEG"),
    ("BBAS3.SA", "Banco do Brasil"),
    ("TAEE11.SA", "Taesa"),
    ("HGLG11.SA", "Pátria Log · FII"),
    ("IVVB11.SA", "iShares S&P 500 · ETF"),
    ("^BVSP", "Ibovespa"),
    ("^GSPC", "S&P 500"),
    ("AAPL", "Apple"),
    ("MSFT", "Microsoft"),
    ("NVDA", "Nvidia"),
    ("GOOGL", "Alphabet"),
    ("BTC-USD", "Bitcoin"),
    ("ETH-USD", "Ethereum"),
    ("BRL=X", "Dólar em reais"),
)


def _modulos() -> list[dict]:
    return [
        {
            "chave": m.chave,
            "nome": m.nome,
            "objetivo": m.objetivo,
            "frase": m.frase,
            "funcionalidades": [
                {
                    "nome": f.nome,
                    "descricao": f.descricao,
                    "pagina_do_app": f.pagina_do_app,
                    "pagina_do_site": f.pagina_do_site,
                    "ticker": f.ticker,
                    "disponivel": f.disponivel,
                }
                for f in m.funcionalidades
            ],
        }
        for m in modulos.MODULOS
    ]


def _paginas() -> list[dict]:
    return [
        {
            "chave": p.chave,
            "titulo": p.titulo,
            "url": p.url,
            "grupo": p.grupo,
            "descricao": p.descricao,
            "e_pro": p.e_pro,
            "no_menu": p.no_menu,
            "somente_admin": p.somente_admin,
            "contrato": asdict(p.contrato) if p.contrato else None,
        }
        for p in paginas.PAGINAS
    ]


def _marca() -> dict:
    return {
        "fonte": marca.FONTE,
        "fonte_mono": marca.FONTE_MONO,
        "marinho": marca.MARINHO,
        "azul": marca.AZUL,
        "claro": marca.CLARO,
        "azul_claro": marca.AZUL_CLARO,
        "paleta_clara": asdict(marca.PALETA_CLARA),
        "paleta_escura": asdict(marca.PALETA_ESCURA),
        "simbolo_svg": marca.simbolo_svg(topo="currentColor"),
        "site_claro": [
            list(p) for p in marca.SITE_CLARO.items()
        ],  # lista: a ordem vira a do CSS
        "site_escuro": [list(p) for p in marca.SITE_ESCURO.items()],
        "site_faixa_marinha": [list(p) for p in marca.SITE_FAIXA_MARINHA.items()],
    }


def _planos() -> dict:
    return {
        "tabela": planos.tabela_de_planos(),
        "com_cobranca": list(planos.COM_COBRANCA),
        "nomes": [planos.limites_do(p).nome for p in planos.PLANOS],
        "nomes_com_cobranca": [planos.limites_do(p).nome for p in planos.COM_COBRANCA],
        # pagos que ainda não estão à venda (os limites já valem)
        "nomes_em_breve": [
            planos.limites_do(p).nome
            for p in planos.PLANOS
            if p != "gratuito" and p not in planos.COM_COBRANCA
        ],
    }


def _site() -> dict:
    """O que só o site usa e vem do app: os estilos do Report Studio, os ativos de exemplo e a fita
    e o total de ativos da busca da página inicial."""
    tabela = catalogo.carregar()
    return {
        "total_de_ativos": len(tabela),
        "fita": [
            {"simbolo": s, "codigo": tabela.loc[s, "codigo"], "nome": nome}
            for s, nome in ATIVOS_DA_FITA
        ],
        "estilos_do_relatorio": [
            {"chave": chave, "nome": estilo.nome} for chave, estilo in ESTILOS.items()
        ],
        "exemplos": [
            {"simbolo": s, "rotulo": catalogo.codigo(s)} for s in catalogo.EXEMPLOS
        ],
    }


def _variacao(valor: float) -> dict[str, float | str]:
    """Um retorno como o PDF mostra: com sinal e a seta (a cor sozinha não basta)."""
    return {
        "valor": round(valor, 4),
        "texto": f"{marca.seta(valor)} {gp.pct_br(valor, 1, sinal=True)}",
    }


def painel_de_exemplo() -> dict[str, object]:
    """O painel da página inicial do site: os números do PDF de exemplo, calculados pelas mesmas
    funções do relatório (ADR 0065, item 4: nunca escritos à mão), e o preço em base 100."""
    ticker = gerar_site.TICKER_DO_EXEMPLO
    fechamento = gerar_site.dados_de_exemplo(ticker)["Close"].dropna()
    retorno = ind.calcular_retorno_diario(fechamento)
    queda = float(ind.calcular_drawdown(fechamento).min())
    volatilidade = ind.calcular_volatilidade_anual(retorno)
    sharpe = ind.calcular_indice_sharpe(
        retorno
    )  # sem taxa livre de risco, como no PDF de exemplo
    pontos = np.linspace(0, len(fechamento) - 1, PONTOS_DO_PAINEL).round().astype(int)
    base_100 = fechamento.iloc[pontos] / fechamento.iloc[0] * 100
    return {
        "ticker": ticker,
        "codigo": catalogo.codigo(ticker),
        "inicio": f"{fechamento.index[0]:%Y-%m-%d}",
        "fim": f"{fechamento.index[-1]:%Y-%m-%d}",
        "retorno_total": _variacao(
            float(ind.calcular_retorno_acumulado(retorno).iloc[-1])
        ),
        "retorno_ao_ano": _variacao(ind.retorno_anualizado_para_mostrar(retorno)),
        "maior_queda": {"valor": round(queda, 4), "texto": gp.pct_br(queda)},
        "volatilidade": {
            "valor": round(volatilidade, 4),
            "texto": gp.pct_br(volatilidade),
        },
        "sharpe": {"valor": round(sharpe, 4), "texto": gp.numero_br(sharpe, 2)},
        "serie": [round(float(v), 1) for v in base_100],
    }


def _legal() -> dict[str, str]:
    """Os Termos e a Política em HTML; o título do arquivo vira o h1 da página."""
    textos = {}
    for nome in ("termos", "privacidade"):
        texto = (RAIZ / "conteudo" / f"{nome}.md").read_text(encoding="utf-8")
        textos[nome] = markdown_para_html(re.sub(r"^#\s+.*\n", "", texto, count=1))
    return textos


def _qualidade() -> dict:
    """O selo "dado em conferência" e as regras fixas, com os mesmos textos do app."""
    return {
        "titulo_do_selo": qualidade_texto.TITULO_DO_SELO,
        "ancora": qualidade_texto.ANCORA_NO_SITE,
        "explicacao": qualidade_texto.EXPLICACAO_DO_SELO,
        "regras": [
            {"titulo": r.titulo, "o_que_confere": r.o_que_confere}
            for r in qualidade_texto.REGRAS.values()
        ],
    }


_ROTULO = re.compile(r"^\*\*(.+?):\*\*\s*(.*)$", re.DOTALL)
_ENFASE = re.compile(r"\*+([^*]+)\*+")


def _partes_da_ajuda(texto: str) -> list[dict[str, str | None]]:
    """Um termo do glossário em partes ({rotulo: "O que é", texto}), sem Markdown: o React só mostra
    texto (nada de HTML pronto vindo daqui)."""
    partes: list[dict[str, str | None]] = []
    for paragrafo in texto.split("\n\n"):
        achado = _ROTULO.match(paragrafo.strip())
        rotulo, corpo = achado.groups() if achado else (None, paragrafo.strip())
        partes.append({"rotulo": rotulo, "texto": _ENFASE.sub(r"\1", corpo).strip()})
    return partes


def _app() -> dict[str, object]:
    """O que o app em React mostra e vem do Python: o painel da visão geral e o "?" de cada número."""
    glossario = carregar_glossario()
    termos = dict.fromkeys(
        [
            *(i.termo for i in analises.ITENS_DO_PAINEL),
            *ji.TERMO_DO_GLOSSARIO.values(),
            "Boletim Focus",
            "Volatilidade móvel",
            "Sazonalidade",
            "Retorno mensal",
            "Base 100",
            ficha.TERMO_DO_GLOSSARIO,
            ficha.TERMO_DA_TOLERANCIA,
        ]
    )
    return {
        "painel": {
            "itens": [asdict(i) for i in analises.ITENS_DO_PAINEL],
            "legenda": analises.LEGENDA_DO_PAINEL,
            "frase_do_cvar": analises.FRASE_DO_CVAR,
        },
        "glossario": {t: _partes_da_ajuda(glossario[t]) for t in termos},
        "juros": {
            "termos": ji.TERMO_DO_GLOSSARIO,
            "fonte_focus": ji.FONTE_FOCUS,
            "nota_do_focus": ji.NOTA_DO_FOCUS,
        },
        "retorno_mensal": {
            "meses": list(ind.NOMES_DOS_MESES),
            "legenda": analises.LEGENDA_DO_MAPA_MENSAL,
        },
        "comparacao": {
            "atalhos": [
                {"nome": n, "ticker": t} for n, t in comparacao.ATALHOS.items()
            ],
            "padrao": list(comparacao.ATALHOS_PADRAO),
            "max_ativos": comparacao.MAX_ATIVOS,
            "colunas": [
                {"rotulo": rotulo, "formato": formato}
                for rotulo, formato in comparacao.FORMATO_DAS_COLUNAS.items()
            ],
            "aviso_do_limite": comparacao.AVISO_DO_LIMITE,
            "aviso_sem_dados": comparacao.AVISO_SEM_DADOS,
        },
        "backtest": {
            "estrategias": [
                {
                    "nome": e.nome,
                    "grupo": e.grupo,
                    "parametros": [asdict(p) for p in e.parametros],
                }
                for e in ESTRATEGIAS.values()
            ],
            "metricas_por_formato": {
                "pct_com_sinal": sorted(formatos.METRICAS_EM_PORCENTAGEM_COM_SINAL),
                "pct": sorted(formatos.METRICAS_EM_PORCENTAGEM),
                "inteiro": sorted(formatos.METRICAS_INTEIRAS),
            },
            "ficha": {
                "termo": ficha.TERMO_DO_GLOSSARIO,
                "termo_da_tolerancia": ficha.TERMO_DA_TOLERANCIA,
                "explicacao": ficha.EXPLICACAO,
            },
        },
        "entrada": {"aviso": AVISO_DA_ENTRADA},
        "aceite": {
            "versao": conformidade.VERSAO_DOS_TERMOS,
            "titulo": conformidade.TITULO_DO_ACEITE,
            "introducao": conformidade.INTRODUCAO_DO_ACEITE,
            "caixa": conformidade.CAIXA_DO_ACEITE,
            "novidades": {
                "texto": f"Opcional: {TEXTO_DAS_NOVIDADES}",
                "versao": VERSAO_DAS_NOVIDADES,
            },
        },
        "linha_do_tempo": {
            "relevancias": [
                {"nome": nome, "valor": valor}
                for nome, valor in ldt.RELEVANCIAS.items()
            ],
            "padrao": ldt.MATERIALIDADE_PADRAO,
        },
    }


def conteudo() -> dict[str, object]:
    """{nome do arquivo: dados}."""
    return {
        "marca": _marca(),
        "modulos": _modulos(),
        "paginas": _paginas(),
        "planos": _planos(),
        "site": _site(),
        "legal": _legal(),
        "qualidade": _qualidade(),
        "metodologia": metodologia_das_notas.como_dicionario(),
        "app": _app(),
        "formatacao": formatos.casos_de_formatacao(),
        "novidades": novidades.como_lista(),
        "exemplo": painel_de_exemplo(),
        "regras_de_imposto": regras_de_imposto.para_o_site(),
    }


def em_json(dados: object) -> str:
    """Texto estável (chaves em ordem, acentos legíveis), para o diff do PR mostrar só o que mudou."""
    return json.dumps(dados, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> None:
    DESTINO.mkdir(parents=True, exist_ok=True)
    for nome, dados in conteudo().items():
        (DESTINO / f"{nome}.json").write_text(em_json(dados), encoding="utf-8")
    print(f"Conteúdo exportado para {DESTINO}")


if __name__ == "__main__":
    main()
