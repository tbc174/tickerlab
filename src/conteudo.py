"""Textos do app (glossário e explicações), lidos da pasta conteudo/."""

from pathlib import Path

import pandas as pd

from src.indicadores import PiorDrawdown

PASTA_RAIZ = Path(__file__).resolve().parent.parent
CAMINHO_GLOSSARIO = PASTA_RAIZ / "conteudo" / "glossario.md"
CAMINHO_ESTRATEGIAS = PASTA_RAIZ / "conteudo" / "estrategias.md"
CAMINHO_SOBRE = PASTA_RAIZ / "conteudo" / "sobre.md"
MARCA_DE_TERMO = "## "


def carregar_glossario(caminho: Path = CAMINHO_GLOSSARIO) -> dict[str, str]:
    """Lê o glossário em Markdown e devolve {termo: texto}, um item por "## Termo"."""
    glossario: dict[str, str] = {}
    termo = None  # termo que estamos lendo agora (None = ainda no cabeçalho)
    linhas: list[str] = []  # linhas do texto desse termo

    for linha in caminho.read_text(encoding="utf-8").splitlines():
        if linha.startswith(MARCA_DE_TERMO):
            if termo is not None:  # fecha o termo anterior
                glossario[termo] = "\n".join(linhas).strip()
            termo = linha[len(MARCA_DE_TERMO) :].strip()
            linhas = []
        elif termo is not None:
            linhas.append(linha)

    if termo is not None:  # o último termo não é fechado por outro "## "
        glossario[termo] = "\n".join(linhas).strip()

    return glossario


def _data_br(data: pd.Timestamp) -> str:
    return f"{data:%d/%m/%Y}"


def descrever_pior_drawdown(pior: PiorDrawdown, negrito: bool = True) -> str:
    """Frase em português que conta a pior queda do período, para quem está começando. Sem
    `negrito`, sai sem o Markdown (para a API e o app em React, que mostram só texto)."""
    if not negrito:
        return descrever_pior_drawdown(pior).replace("**", "")
    if pd.isna(pior.queda):
        return "Não há dados suficientes para calcular a pior queda."
    if pior.data_fundo is None:
        return "Neste período o preço nunca ficou abaixo de um topo anterior."

    queda = f"{pior.queda:.1%}".replace(".", ",")
    frase = (
        f"Pior queda: **{queda}**. O preço estava no topo em {_data_br(pior.data_topo)} "
        f"e chegou ao fundo em {_data_br(pior.data_fundo)}"
    )
    if pior.data_recuperacao is None:
        return frase + ". Ainda **não voltou** ao topo anterior."
    dias = (pior.data_recuperacao - pior.data_fundo).days
    return (
        frase
        + f", e só voltou ao topo em {_data_br(pior.data_recuperacao)} ({dias} dias depois)."
    )


def proteger_cifrao(texto: str | None) -> str | None:
    """Põe uma barra antes de cada "$": o Streamlit lê "R$ 1 e US$ 2" como fórmula matemática."""
    return texto.replace("$", r"\$") if texto else texto


def carregar_estrategias(caminho: Path = CAMINHO_ESTRATEGIAS) -> dict[str, str]:
    """Explicações das estratégias (um verbete por estratégia), no mesmo formato do glossário."""
    return carregar_glossario(caminho)


def carregar_sobre(caminho: Path = CAMINHO_SOBRE) -> dict[str, str]:
    """As seções da página Sobre, na ordem do arquivo (mesmo formato do glossário)."""
    return carregar_glossario(caminho)
