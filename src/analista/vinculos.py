"""Os vínculos da empresa na ficha do analista (linha 798, PR 5): controle, coligação, participação e auditoria.

A tela lê pelo mesmo `LeitorDeVinculos` da API externa (linha 736) e pelo mesmo portão da ficha
(`leitura.permitido_na_tela`): o analista vê só o que a chave dele veria pela API. Um salto a partir da empresa
(a rede inteira fica para quem programa), todos os tipos. Nada de pessoa: o leitor já tira a ponta que é pessoa
natural ou que a rede trata como pessoa.

Os estados são os da ficha (`leitura`): `pronta` (a lista, que pode ser vazia), `nao_liberada` (o portão ainda
não libera nenhum campo de nenhum tipo; decide-se sem ler o CNPJ) e `nao_disponivel` (o leitor não serve o
CNPJ: não existe, é pessoa ou a rede não o conhece como empresa), sem dizer o motivo.
"""

from collections.abc import Callable
from datetime import date

from base import cnpj as cnpj_
from base.porta import Porta
from src.analista import leitura
from src.api_externa.conjuntos import vinculos as vinculos_
from src.api_externa.envelope import fontes_da_resposta
from src.portao_externo import Regras

LINHAS_MAXIMAS = 100
PROFUNDIDADE = 1

# os limites do leitor, sem o nome de campo para quem programa (`known_at`): a tela fala do "dia da ficha"
LIMITES = tuple(
    leitura.DIA_DA_FICHA if "known_at" in limite else limite
    for limite in vinculos_.LIMITES
)


def _algum_campo_liberado(permitido: Callable[[str, str, bool], bool]) -> bool:
    return any(
        permitido(tipo.fonte, nome, False)
        for tipo in vinculos_.TIPOS.values()
        for nome in tipo.campos
    )


def vinculos(
    porta: Porta,
    cnpj: str,
    *,
    hoje: date,
    regras: Regras | None = None,
) -> leitura.Resposta:
    """Os vínculos do CNPJ como eram hoje, a um salto, no máximo `LINHAS_MAXIMAS`.

    `ValueError` se o CNPJ é inválido (a rota responde 422)."""
    if not cnpj_.normalizar_cnpj(cnpj):
        raise ValueError("CNPJ inválido")
    permitido = leitura.permitido_na_tela(vinculos_.CONJUNTO, hoje, regras)
    if not _algum_campo_liberado(permitido):
        return leitura.Resposta(leitura.NAO_LIBERADA)
    leitor = vinculos_.LeitorDeVinculos(porta, permitido, LINHAS_MAXIMAS)
    servidos = leitor.vinculos(cnpj, hoje, PROFUNDIDADE)
    if servidos is None:
        return leitura.Resposta(leitura.NAO_DISPONIVEL)
    corpo = {**servidos.corpo, "limites": list(LIMITES)}
    return leitura.Resposta(
        leitura.PRONTA, corpo, fontes_da_resposta(servidos.fontes), servidos.linhas
    )
