"""As instruções que o modelo do chat recebe (linha 903): o texto de `conteudo/instrucoes_do_chat.md` e o
mapa de qual ferramenta responde a cada pergunta, que é o mesmo do conector (um lugar só para cada verdade).

O texto é lido pelo analista indiretamente (é o que molda cada resposta): mudar o arquivo passa pelas duas
revisões, como texto público.
"""

from functools import cache
from pathlib import Path

ARQUIVO = (
    Path(__file__).resolve().parent.parent.parent / "conteudo" / "instrucoes_do_chat.md"
)
TITULO_DO_MAPA = "## Qual ferramenta para cada pergunta"


@cache
def instrucoes_do_chat() -> str:
    """O texto inteiro das instruções (lido uma vez por processo)."""
    from conector_remoto.servidor import LACUNAS, MAPA_DAS_PERGUNTAS

    texto = ARQUIVO.read_text(encoding="utf-8").strip()
    mapa = f"{MAPA_DAS_PERGUNTAS.strip()} {LACUNAS.strip()}"
    return f"{texto}\n\n{TITULO_DO_MAPA}\n\n{mapa}"
