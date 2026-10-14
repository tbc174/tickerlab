"""Exporta o conteúdo do Python para o site em React (web/conteudo/*.json).

O Python continua a fonte da verdade (ADR 0048, item 3): módulos (`src/modulos.py`), páginas do app
(`src/paginas.py`), planos (`src/planos.py`), marca e cores do site (`src/marca.py`), estilos do
Report Studio e ativos de exemplo (`src/catalogo.py`). O React lê estes JSON no build;
há teste que acusa quando um deles fica velho.

Uso: python -m scripts.exportar_conteudo
"""

import json
import re
from dataclasses import asdict
from pathlib import Path

from scripts.markdown_simples import markdown_para_html
from src import (
    analises,
    catalogo,
    comparacao,
    formatos,
    marca,
    modulos,
    novidades,
    paginas,
    planos,
    qualidade_texto,
)
from src import indicadores as ind
from src import juros_e_inflacao as ji
from src import linha_do_tempo as ldt
from src.conteudo import carregar_glossario
from src.estilos_pdf import ESTILOS
from src.estrategias import ESTRATEGIAS

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "web" / "conteudo"


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
    """O que só o site usa e vem do app: os estilos do Report Studio e os ativos de exemplo."""
    return {
        "estilos_do_relatorio": [
            {"chave": chave, "nome": estilo.nome} for chave, estilo in ESTILOS.items()
        ],
        "exemplos": [
            {"simbolo": s, "rotulo": catalogo.rotulo(s).split(" · ")[0]}
            for s in catalogo.EXEMPLOS
        ],
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
        "app": _app(),
        "formatacao": formatos.casos_de_formatacao(),
        "novidades": novidades.como_lista(),
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
