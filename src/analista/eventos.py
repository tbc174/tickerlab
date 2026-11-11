"""Os eventos da empresa na ficha do analista (linha 798, PR 4): documentos à CVM e trocas de auditor.

A tela lê pelo mesmo `LeitorDeEventos` da API externa (linha 736) e pelo mesmo portão da ficha
(`leitura.permitido_na_tela`): o analista vê só o que a chave dele veria pela API. Nada de pessoa: o leitor já
esconde o assunto livre do documento e a troca com auditor que pode ser pessoa física.

Os três estados são os da ficha (`leitura`): `pronta` (o corpo do leitor, com `proximo_cursor` quando a lista
é maior que a página), `nao_liberada` (o portão ainda não libera nenhum campo de nenhum tipo; decide-se sem
ler o CNPJ) e `nao_disponivel` (o leitor não serve o CNPJ: não existe, é pessoa ou a rede não o conhece como
empresa), sem dizer o motivo.
"""

from collections.abc import Callable
from datetime import date

from base import cnpj as cnpj_
from base.porta import Porta
from src.analista import leitura
from src.api_externa.conjuntos import eventos as eventos_
from src.api_externa.envelope import fontes_da_resposta
from src.portao_externo import Regras

LINHAS_POR_PAGINA = 50
# o texto do cursor que a API grava tem perto de cinquenta caracteres; a rota recusa mais que isto
TAMANHO_MAXIMO_DO_CURSOR = 200


# os limites do leitor, sem o nome de campo para quem programa (`known_at`): a tela fala do "dia da ficha"
LIMITES = tuple(
    leitura.DIA_DA_FICHA if "known_at" in limite else limite
    for limite in eventos_.LIMITES
)


class PedidoInvalido(ValueError):
    """O cursor não é nosso. A rota responde 422, sem repetir o que veio."""


def _algum_campo_liberado(permitido: Callable[[str, str, bool], bool]) -> bool:
    return any(
        permitido(origem.fonte, nome, nome in origem.derivados)
        for origem in eventos_.ORIGENS.values()
        for nome in origem.campos
    )


def eventos(
    porta: Porta,
    cnpj: str,
    *,
    hoje: date,
    cursor: str | None = None,
    regras: Regras | None = None,
) -> leitura.Resposta:
    """Os eventos do CNPJ como eram hoje, do mais novo ao mais velho, `LINHAS_POR_PAGINA` por vez.

    `ValueError` se o CNPJ é inválido; `PedidoInvalido` se o cursor não é nosso (a rota responde 422)."""
    if not cnpj_.normalizar_cnpj(cnpj):
        raise ValueError("CNPJ inválido")
    permitido = leitura.permitido_na_tela(eventos_.CONJUNTO, hoje, regras)
    if not _algum_campo_liberado(permitido):
        return leitura.Resposta(leitura.NAO_LIBERADA)
    leitor = eventos_.LeitorDeEventos(porta, permitido, LINHAS_POR_PAGINA)
    try:
        servidos = leitor.eventos(cnpj, hoje, cursor=cursor)
    except eventos_.PedidoInvalido as erro:
        raise PedidoInvalido from erro
    if servidos is None:
        return leitura.Resposta(leitura.NAO_DISPONIVEL)
    corpo = {**servidos.corpo, "limites": list(LIMITES)}
    return leitura.Resposta(
        leitura.PRONTA, corpo, fontes_da_resposta(servidos.fontes), servidos.linhas
    )
