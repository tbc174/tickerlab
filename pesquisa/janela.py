"""Recorte literal de um trecho provado: uma janela de até N caracteres em volta do valor (linha 830).

O bot guarda, como prova, o trecho inteiro que a fonte traz (pode ser uma linha de planilha enorme) e o
valor provado. Para a vitrine basta a janela em volta do valor. Regras: a janela é uma fatia **contígua e
literal** do trecho (nada reescrito, nenhuma reticência dentro do texto), contém o valor, e quem a mostra
marca o corte **fora** das aspas (`recorte`). O hash continua sendo o do original inteiro.
"""

from dataclasses import dataclass

from src.novidades_da_pesquisa import (
    CORTE_NO_FIM,
    CORTE_NO_INICIO,
    CORTE_NOS_DOIS,
    SEM_CORTE,
)


@dataclass(frozen=True)
class Janela:
    texto: str
    recorte: str  # SEM_CORTE, CORTE_NO_INICIO, CORTE_NO_FIM ou CORTE_NOS_DOIS


def _recorte(comeco: int, fim: int, tamanho: int) -> str:
    antes, depois = comeco > 0, fim < tamanho
    if antes and depois:
        return CORTE_NOS_DOIS
    if antes:
        return CORTE_NO_INICIO
    return CORTE_NO_FIM if depois else SEM_CORTE


def _sem_cortar_palavra(
    trecho: str, comeco: int, fim: int, achado: int, ate: int
) -> tuple[int, int]:
    """Recua o começo e o fim até um espaço, sem deixar o valor (`achado`..`ate`) de fora."""
    if comeco > 0:
        espaco = trecho.find(" ", comeco, achado)
        if espaco != -1:
            comeco = espaco + 1
    if fim < len(trecho):
        espaco = trecho.rfind(" ", ate, fim)
        if espaco != -1:
            fim = espaco
    return comeco, fim


def janela_do_valor(trecho: str, valor: str, maximo: int) -> Janela | None:
    """A janela de até `maximo` caracteres do `trecho` que contém o `valor`; None se não dá.

    Trecho que já cabe sai igual (sem corte). Valor vazio, que não aparece no trecho (a busca ignora a
    caixa) ou maior que o máximo: None (o fato fica de fora, nunca um texto inventado).
    """
    if len(trecho) <= maximo:
        return Janela(trecho, SEM_CORTE)
    achado = trecho.lower().find(valor.lower()) if valor.strip() else -1
    if achado == -1 or len(valor) > maximo:
        return None
    ate = achado + len(valor)
    folga = (maximo - len(valor)) // 2
    comeco = max(0, min(achado - folga, len(trecho) - maximo))
    fim = min(len(trecho), comeco + maximo)
    comeco, fim = _sem_cortar_palavra(trecho, comeco, fim, achado, ate)
    texto = trecho[comeco:fim]
    # as garantias, conferidas de novo: fatia literal do original, dentro do máximo, com o valor dentro
    if (
        not texto
        or len(texto) > maximo
        or texto not in trecho
        or valor.lower() not in texto.lower()
    ):
        return None
    return Janela(texto, _recorte(comeco, fim, len(trecho)))
