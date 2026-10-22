"""Conferência do trecho de uma evidência contra o texto da página (B-20, PR 4, D10)."""

import re

_ESPACOS = re.compile(r"\s+")


def _limpar(texto: str) -> str:
    return _ESPACOS.sub(" ", texto).strip().casefold()


def trecho_confere(
    paginas: list[str] | None, pagina: int | None, trecho: str | None
) -> bool:
    """O trecho aparece no texto da página (sem diferença de caixa nem de quebras de linha)?

    `False` quando não dá para conferir: documento ainda sem texto lido, página que não existe,
    página ou trecho em branco. "Não conferida" nunca é erro, só aviso para a pessoa.
    """
    if not paginas or pagina is None or not trecho or not trecho.strip():
        return False
    if not 1 <= pagina <= len(paginas):
        return False
    return _limpar(trecho) in _limpar(paginas[pagina - 1])
