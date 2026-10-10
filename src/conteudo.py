"""Textos do app (glossário e explicações), lidos da pasta conteudo/."""

from pathlib import Path

PASTA_RAIZ = Path(__file__).resolve().parent.parent
CAMINHO_GLOSSARIO = PASTA_RAIZ / "conteudo" / "glossario.md"
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
