"""A leitura da tela do analista (linha 798): a ficha de uma empresa, pelo mesmo leitor da API externa.

A tela pergunta ao portão como a API externa (`Canal.API_EXTERNA`, finalidade de análise), com as mesmas
regras e a mesma prontidão das tabelas (D10). A única coisa que fica de fora é o contrato da organização: quem
entra na tela é a conta com login e o plano da página (`src/paginas.py`). É a leitura mais estreita: o canal
do app (ADR 0102) é mais solto e não vale aqui. Resultado: o analista vê na tela só o que a chave dele veria
pela API.

Três estados, para a tela nunca mostrar erro onde o certo é explicar:

- `pronta`: o corpo do leitor, com as chaves em português (a rota do app não traduz);
- `nao_liberada`: o portão ainda não deixa sair o cadastro (a âncora da ficha), por exemplo porque a tabela não
  tem prontidão. Decide-se sem ler o CNPJ: o estado não diz se o CNPJ existe nem se é de pessoa;
- `nao_disponivel`: o leitor não serve o CNPJ (não existe, é pessoa, MEI ou empresário individual, ou a rede
  não o conhece como empresa), sem dizer o motivo, como o 404 da API.
"""

from dataclasses import dataclass, field
from datetime import date
from functools import cache

from base import cnpj as cnpj_
from base.porta import Porta
from src.api_externa.conjuntos import Permitido
from src.api_externa.conjuntos import empresas as empresas_
from src.api_externa.conjuntos import ficha as ficha_
from src.api_externa.envelope import fontes_da_resposta
from src.portao_externo import Canal, Finalidade, Pedido, Regras, decidir

PRONTA = "pronta"
NAO_LIBERADA = "nao_liberada"
NAO_DISPONIVEL = "nao_disponivel"
# a âncora da ficha: sem a situação cadastral, o leitor não serve nada (`LeitorDeEmpresas`)
ANCORA = (empresas_.FONTE, "situacao_cadastral")

# os limites da ficha da API, menos o nome de campo para quem programa (`known_at`): o analista lê "o dia da
# ficha", que a tela mostra no topo; os outros são os mesmos, na mesma ordem
DIA_DA_FICHA = "Cada campo traz a fonte e o dia em que ficou público: nada publicado depois do dia da ficha entra."
LIMITES = tuple(
    DIA_DA_FICHA if "known_at" in limite else limite for limite in ficha_.LIMITES
)


@dataclass(frozen=True)
class Resposta:
    """O que a tela recebe: o estado, o corpo do leitor (só quando pronta), as fontes com a atribuição e
    quantas linhas foram servidas (a planilha e o medidor contam por aqui)."""

    estado: str
    corpo: dict | None = None
    fontes: list[dict[str, str]] = field(default_factory=list)
    linhas: int = 0


def permitido_na_tela(
    conjunto: str, hoje: date, regras: Regras | None = None
) -> Permitido:
    """O portão da tela para um conjunto: o da API externa, campo a campo, sem o contrato da organização."""

    @cache
    def permitido(fonte: str, campo: str, derivado: bool) -> bool:
        pedido = Pedido(
            fonte=fonte,
            conjunto=conjunto,
            campo=campo,
            canal=Canal.API_EXTERNA,
            finalidade=Finalidade.ANALISE,
            derivado=derivado,
        )
        return decidir(pedido, hoje, regras).libera

    return permitido


def ficha(
    porta: Porta,
    cnpj: str,
    *,
    hoje: date,
    como_era_em: date | None = None,
    regras: Regras | None = None,
) -> Resposta:
    """A ficha do CNPJ como era em `como_era_em` (hoje, se vazio ou no futuro), pelo `LeitorDeFicha` da API.

    `ValueError` se o CNPJ é inválido (a rota responde 400)."""
    if not cnpj_.normalizar_cnpj(cnpj):
        raise ValueError("CNPJ inválido")
    dia = hoje if como_era_em is None else min(como_era_em, hoje)
    permitido = permitido_na_tela(ficha_.CONJUNTO, hoje, regras)
    fonte, campo = ANCORA
    if not permitido(fonte, campo, False):
        return Resposta(NAO_LIBERADA)
    servida = ficha_.LeitorDeFicha(porta, permitido).ficha(cnpj, dia)
    if servida is None:
        return Resposta(NAO_DISPONIVEL)
    corpo = {**servida.corpo, "limites": list(LIMITES)}
    return Resposta(PRONTA, corpo, fontes_da_resposta(servida.fontes), servida.linhas)
