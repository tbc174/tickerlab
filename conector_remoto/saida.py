"""O que o conector faz com a resposta da API antes de entregá-la à IA: limpa o texto e confere o tamanho.

O texto da base vem de terceiros (a razão social, a descrição de uma conta, o nome de um setor). Antes de
chegar à IA, ele perde os caracteres que não se veem e servem para esconder instrução: os de controle, os
de largura zero e os que invertem a direção do texto. As quebras de linha e o tab ficam.
"""

import json
import re

from conector_remoto.pessoa import exigir_sem_pessoa

# O Claude aceita até ~150 mil caracteres por resposta de ferramenta; a sobra é para o envelope do MCP.
TETO_DE_CARACTERES = 120_000
# C0 (menos tab e quebra de linha), DEL e C1; largura zero e marcas de direção; controles bidirecionais;
# o BOM e os "tag characters" do Unicode, que carregam texto invisível
_INVISIVEIS = re.compile(
    "[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069\ufeff\U000e0000-\U000e007f]"
)


class RespostaGrandeDemais(Exception):
    """A resposta passou do teto de caracteres; `tamanho` é quantos ela tinha."""

    def __init__(self, tamanho: int) -> None:
        super().__init__(
            f"resposta com {tamanho} caracteres (teto {TETO_DE_CARACTERES})"
        )
        self.tamanho = tamanho


def limpar_texto(valor: object) -> object:
    """O mesmo JSON, sem caracteres invisíveis nas chaves nem nos textos (em qualquer profundidade)."""
    if isinstance(valor, str):
        return _INVISIVEIS.sub("", valor)
    if isinstance(valor, dict):
        return {
            limpar_texto(chave): limpar_texto(filho) for chave, filho in valor.items()
        }
    if isinstance(valor, list):
        return [limpar_texto(filho) for filho in valor]
    return valor


def tamanho_em_caracteres(valor: object) -> int:
    """Quantos caracteres o JSON tem, como a IA o recebe (acentos contam um)."""
    return len(json.dumps(valor, ensure_ascii=False, separators=(",", ":")))


def preparar_saida(corpo: object) -> object:
    """A resposta pronta para a IA: limpa, sem pessoa e dentro do teto (ou a exceção do que falhou)."""
    limpo = limpar_texto(corpo)
    exigir_sem_pessoa(limpo)
    tamanho = tamanho_em_caracteres(limpo)
    if tamanho > TETO_DE_CARACTERES:
        raise RespostaGrandeDemais(tamanho)
    return limpo
