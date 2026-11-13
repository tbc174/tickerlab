"""Quem já se mexeu num setor, na tela do analista (linha 903, PR D): só pessoa jurídica.

A tela lê pelo mesmo `LeitorDeCompradores` da API externa (`GET /data/v1/buyers`, linha 810) e pelo mesmo
portão da ficha (`leitura.permitido_na_tela`): o analista vê só o que a chave dele veria pela API. Nada do leitor
muda aqui; esta camada só pede o setor (o CNAE, de 5 ou 7 dígitos, e a UF, se houver), troca o nome de campo para
quem programa (`known_at`) pelo que a tela diz e devolve os sinais pelos nomes de dentro (`entrou_como_socio`,
`fundo_socio`, `controla_no_setor`), que a tela traduz em frase.

Os estados são os da ficha (`leitura`): `pronta` (a lista, que pode ser vazia) e `nao_liberada` (o portão não
libera o setor, nenhum sinal, ou a base deste servidor não tem o retrato da Receita do dia): a tela diz que o
dado ainda não foi liberado, sem dizer o motivo. O sinal que o portão não libera não some em silêncio: vai em
`sinais_nao_disponiveis` e os limites avisam que a lista não diz nada sobre ele.

O que ficou de fora de propósito: a contagem por UF e as aberturas por ano do setor (não há leitor com login para
elas; a tela diz isso à vista e leva a busca de empresas já filtrada).
"""

from datetime import date

from base.porta import Porta
from src.analista import leitura
from src.api_externa import nao_disponivel
from src.api_externa.conjuntos import compradores as compradores_
from src.api_externa.conjuntos import perfil_do_setor
from src.api_externa.envelope import fontes_da_resposta
from src.portao_externo import Regras

PedidoInvalido = compradores_.PedidoInvalido
LINHAS_MAXIMAS = compradores_.LIMITE_MAXIMO
LIMITE_DA_LISTA = 20

# o nome de fora do sinal (o da lista `sinais_nao_disponiveis` do leitor) volta ao nome de dentro das provas
DE_FORA_PARA_DENTRO = {
    fora: dentro for dentro, fora in compradores_.NOME_DE_FORA.items()
}
AVISO_DA_API = "sinais_nao_disponiveis"
DIA_DA_CONSULTA = "o dia da consulta"


def limites_da_tela(limites: list[str], aviso: str = AVISO_DA_API) -> list[str]:
    """Os limites do leitor sem o nome de campo para quem programa: `known_at` vira "o dia da consulta" e o
    aviso da parte não disponível (`aviso`, o nome de dentro da lista) fala do campo da tela, como na API."""
    de_fora = nao_disponivel.NOMES_DE_FORA[aviso]
    return [_frase_da_tela(limite.replace(de_fora, aviso)) for limite in limites]


def _frase_da_tela(limite: str) -> str:
    """Troca o `known_at` por "o dia da consulta" com a preposição certa e tira o "para esta organização",
    que esta tela não usa (o portão é o da API, sem contrato de organização)."""
    limite = limite.replace("em known_at", "no dia da consulta")
    limite = limite.replace("de known_at", "do dia da consulta")
    limite = limite.replace("known_at", DIA_DA_CONSULTA)
    return limite.replace(" para esta organização", "")


def compradores(
    porta: Porta,
    cnae: str,
    uf: str | None,
    anos: int | None,
    *,
    hoje: date,
    regras: Regras | None = None,
) -> leitura.Resposta:
    """Os compradores do setor como eram hoje, no máximo `LIMITE_DA_LISTA`.

    `PedidoInvalido` (um `ValueError`) se o CNAE, a UF ou os anos estão fora da forma (a rota responde 422)."""
    pedido = compradores_.pedido_dos_parametros(cnae, uf, anos, LIMITE_DA_LISTA)
    permitido = leitura.permitido_na_tela(compradores_.CONJUNTO, hoje, regras)
    leitor = compradores_.LeitorDeCompradores(porta, permitido, LINHAS_MAXIMAS)
    servidos = leitor.compradores(pedido, hoje)
    if servidos is None:
        return leitura.Resposta(leitura.NAO_LIBERADA)
    corpo = dict(servidos.corpo)
    corpo[AVISO_DA_API] = [
        DE_FORA_PARA_DENTRO[nome] for nome in corpo.get(AVISO_DA_API, [])
    ]
    corpo["limites"] = limites_da_tela(list(corpo["limites"]))
    return leitura.Resposta(
        leitura.PRONTA, corpo, fontes_da_resposta(servidos.fontes), servidos.linhas
    )


def perfil(
    porta: Porta, cnae: str, *, hoje: date, regras: Regras | None = None
) -> leitura.Resposta:
    """Os números do setor (empresas ativas, por UF, aberturas por ano), só contagens e só pessoa jurídica.

    `PedidoInvalido` (um `ValueError`) se o CNAE está fora da forma. Sem o CNAE liberado, sem as tabelas ou sem
    retrato público, `nao_liberada`. O bloco que o portão não libera vem `None` (nunca zero) e o nome dele em
    `blocos_nao_disponiveis`."""
    permitido = leitura.permitido_na_tela(perfil_do_setor.CONJUNTO, hoje, regras)
    servido = perfil_do_setor.LeitorDoPerfilDoSetor(porta, permitido).perfil(cnae, hoje)
    if servido is None:
        return leitura.Resposta(leitura.NAO_LIBERADA)
    corpo = dict(servido.corpo)
    corpo["limites"] = limites_da_tela(
        list(corpo["limites"]), perfil_do_setor.NAO_DISPONIVEIS
    )
    return leitura.Resposta(
        leitura.PRONTA, corpo, fontes_da_resposta(servido.fontes), servido.linhas
    )
