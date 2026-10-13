"""Gera a parte do site público (pasta `site/`) que precisa do Python.

    python -m scripts.gerar_site

Desde a ADR 0048, as páginas do site (HTML), o CSS, o JavaScript, o `robots.txt` e o `sitemap.xml`
vêm do React (`web/`, com `npm run site`). Aqui fica só o que depende do código do app:

- fontes, marca e o cálculo do sol do tema, copiados de `static/` (sem Google Fonts);
- o relatório de exemplo (PDF) e as imagens das duas primeiras páginas em cada estilo, gerados agora
  pelo mesmo código do app, com os dados de exemplo guardados no projeto (rotulados como exemplo);
- o catálogo da busca do topo (`conteudo/catalogo_de_ativos.csv`).

O site inteiro, do zero: `python -m scripts.gerar_site`, `python -m scripts.exportar_conteudo` e, em
`web/`, `npm run site`. Há testes que conferem que cada parte de `site/` está em dia.
"""

import json
import shutil
import sys
from datetime import datetime
from io import BytesIO
from pathlib import Path

import pandas as pd
from PIL import Image

from src import catalogo, previa_pdf, relatorios
from src.estilos_pdf import ESTILOS

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "site"
TICKER_DO_EXEMPLO = "PETR4.SA"

# o que vem pronto de static/ (pasta → arquivos)
COPIADOS = (
    (
        "fontes",
        (
            "Manrope-VariableFont_wght.ttf",
            "JetBrainsMono-VariableFont_wght.ttf",
            "OFL-Manrope.txt",
            "OFL-JetBrainsMono.txt",
        ),
    ),
    ("marca", ("simbolo.svg", "icone.png", "compartilhamento.png")),
    ("tema", ("sol.js",)),
)
# pastas e arquivos de site/ que são deste script (o resto é do React)
PASTAS_DO_PYTHON = ("fontes", "marca", "tema", "relatorio")
ARQUIVOS_DO_PYTHON = ("catalogo.json",)


def _dados_de_exemplo(ticker: str) -> pd.DataFrame:
    nome = ticker.replace("^", "_")
    return pd.read_csv(
        RAIZ / "dados_de_exemplo" / f"{nome}.csv", index_col=0, parse_dates=True
    )


def gerar_relatorio_de_exemplo(destino: Path) -> list[str]:
    """O PDF de exemplo (Pesquisa completa, estilo Research) e as imagens de 2 páginas em cada
    estilo, com a data fixa do último dado de exemplo (o arquivo não muda a cada geração)."""
    pasta = destino / "relatorio"
    pasta.mkdir(parents=True, exist_ok=True)
    dados = _dados_de_exemplo(TICKER_DO_EXEMPLO)
    gerado_em = datetime.combine(dados.index[-1].date(), datetime.min.time()).replace(
        hour=18, tzinfo=relatorios.FUSO
    )
    estilos = list(ESTILOS)
    for estilo in estilos:
        pdf = relatorios.relatorio_do_ativo(
            TICKER_DO_EXEMPLO,
            dados,
            periodo="5 anos",
            gerado_em=gerado_em,
            exemplo=True,
            config=relatorios.Configuracao(estilo=estilo),
        )
        if estilo == "research":
            (pasta / f"exemplo-{TICKER_DO_EXEMPLO}.pdf").write_bytes(pdf)
        for numero, png in enumerate(previa_pdf.paginas_em_png(pdf, 2, 560), start=1):
            imagem = Image.open(BytesIO(png)).convert("RGB")
            imagem.save(pasta / f"{estilo}-{numero}.webp", "WEBP", quality=82, method=6)
    return estilos


def arquivos_do_python(pasta: Path) -> set[Path]:
    """Os arquivos de `pasta` que este script gera (caminhos relativos)."""
    arquivos = {Path(n) for n in ARQUIVOS_DO_PYTHON if (pasta / n).exists()}
    for sub in PASTAS_DO_PYTHON:
        if (pasta / sub).exists():
            arquivos |= {
                p.relative_to(pasta) for p in (pasta / sub).rglob("*") if p.is_file()
            }
    return arquivos


def gerar(destino: Path = DESTINO) -> None:
    """Escreve em `destino` só a parte do Python; as páginas do React ficam como estão."""
    destino.mkdir(parents=True, exist_ok=True)
    for sub in PASTAS_DO_PYTHON:
        shutil.rmtree(destino / sub, ignore_errors=True)  # nada velho fica para trás
    for pasta, nomes in COPIADOS:
        (destino / pasta).mkdir()
        for nome in nomes:
            shutil.copyfile(RAIZ / "static" / pasta / nome, destino / pasta / nome)
    gerar_relatorio_de_exemplo(destino)
    tabela = catalogo.carregar().reset_index()
    (destino / "catalogo.json").write_text(
        json.dumps(
            tabela[["simbolo", "codigo", "nome", "bolsa", "tipo"]].values.tolist(),
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )


def main() -> int:
    destino = Path(sys.argv[1]) if len(sys.argv) > 1 else DESTINO
    gerar(destino)
    print(f"parte do Python do site gerada em {destino}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
