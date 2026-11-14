"""A leitura da tela do analista (linha 798): a ficha de uma empresa, pelo mesmo leitor da API externa.

A tela pergunta ao portão como a API externa (`Canal.API_EXTERNA`, finalidade de análise), com as mesmas
regras e a mesma prontidão das tabelas (D10). A única coisa que fica de fora é o contrato da organização: quem
entra na tela é a conta com login e o plano da página (`src/paginas.py`). É a leitura mais estreita: o canal
do app (ADR 0102) é mais solto e não vale aqui. Resultado: o analista vê na tela só o que a chave dele veria
pela API.

A prontidão de piloto (D11) vale na tela como na API: só para a conta de uma organização com a marca de piloto
(`permitido_na_tela(..., piloto=True)`, conferida no servidor pela rota) e sempre com o aviso de piloto na
resposta. Hoje só a busca de empresas a usa (`src/analista/busca.py`); as outras leituras seguem só com a
prontidão cheia.

Três estados, para a tela nunca mostrar erro onde o certo é explicar:

- `pronta`: o corpo do leitor, com as chaves em português (a rota do app não traduz);
- `nao_liberada`: o portão ainda não deixa sair o cadastro (a âncora da ficha), por exemplo porque a tabela não
  tem prontidão. Decide-se sem ler o CNPJ: o estado não diz se o CNPJ existe nem se é de pessoa;
- `nao_disponivel`: o leitor não serve o CNPJ (não existe, é pessoa, MEI ou empresário individual, ou a rede
  não o conhece como empresa), sem dizer o motivo, como o 404 da API.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date
from functools import cache

from base import cnpj as cnpj_
from base.porta import Porta
from src.api_externa import piloto as piloto_
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


def limites_da_tela(
    limites: Iterable[str], avisos_da_tela: Mapping[str, str]
) -> tuple[str, ...]:
    """Os limites do leitor da API sem os nomes de campo para quem programa: `known_at` vira o "dia da ficha" e
    o aviso da parte não disponível, que cita o campo da API externa, vira o da tela (molde do #1088)."""
    return tuple(
        DIA_DA_FICHA if "known_at" in limite else avisos_da_tela.get(limite, limite)
        for limite in limites
    )


# o aviso do leitor fala do campo da API externa; a tela usa o nome do campo dela (linha 897)
LIMITE_DO_DOCUMENTO_NAO_DISPONIVEL = (
    "Os documentos em entregas_nao_disponiveis não estão liberados para a tela e não foram consultados: a lista "
    "de entregas não diz nada sobre eles."
)
# o campo do cadastro barrado (o Simples sem prontidão, por exemplo): o cadastro da tela não fala dele (linha 897)
LIMITE_DO_CAMPO_DO_CADASTRO_NAO_DISPONIVEL = (
    "Os campos em campos_do_cadastro_nao_disponiveis não estão liberados para a tela e não foram consultados: o "
    "cadastro mostrado aqui não diz nada sobre eles."
)
AVISOS_DA_TELA = {
    ficha_.LIMITE_DO_DOCUMENTO_NAO_DISPONIVEL: LIMITE_DO_DOCUMENTO_NAO_DISPONIVEL,
    ficha_.LIMITE_DO_CAMPO_DO_CADASTRO_NAO_DISPONIVEL: LIMITE_DO_CAMPO_DO_CADASTRO_NAO_DISPONIVEL,
}
# os limites com os dois documentos consultados: os das respostas sem ficha (não liberada, não disponível)
LIMITES = limites_da_tela(ficha_.LIMITES, AVISOS_DA_TELA)


@dataclass(frozen=True)
class Bloco:
    """Um bloco da ficha, para a tela dizer o que vem antes de o dado ser liberado (sem data nem número)."""

    titulo: str
    fonte: str
    o_que_traz: str


BLOCOS = (
    Bloco(
        "Cadastro na Receita Federal",
        "Receita Federal, dados abertos do CNPJ",
        "Razão social, natureza jurídica, situação cadastral e desde quando, se é matriz ou filial e a "
        "opção pelo Simples Nacional.",
    ),
    Bloco(
        "Entregas de balanço à CVM",
        "CVM, demonstrações financeiras anuais e trimestrais",
        "Só da companhia aberta: cada balanço entregue, o prazo, o dia da entrega e se atrasou.",
    ),
)


def blocos_como_lista() -> list[dict[str, str]]:
    """Os blocos em tipos simples (a rota devolve sempre; a tela os mostra quando a ficha não sai)."""
    return [
        {"titulo": b.titulo, "fonte": b.fonte, "o_que_traz": b.o_que_traz}
        for b in BLOCOS
    ]


@dataclass(frozen=True)
class Resposta:
    """O que a tela recebe: o estado, o corpo do leitor (só quando pronta), as fontes com a atribuição e
    quantas linhas foram servidas (a planilha e o medidor contam por aqui)."""

    estado: str
    corpo: dict | None = None
    fontes: list[dict[str, str]] = field(default_factory=list)
    linhas: int = 0


def permitido_na_tela(
    conjunto: str, hoje: date, regras: Regras | None = None, *, piloto: bool = False
) -> Permitido:
    """O portão da tela para um conjunto: o da API externa, campo a campo, sem o contrato da organização.

    `piloto` diz se a conta é de uma organização com a marca de piloto (D11; quem confere é a rota, no
    servidor): só então o portão libera a tabela que tem o registro de piloto e ainda não a prontidão cheia.
    O campo liberado pelo piloto só sai com um registro aberto (`piloto.anotar`), que é como quem chama fica
    sabendo que deve o aviso; sem ele, é negado.
    """

    @cache
    def permitido(fonte: str, campo: str, derivado: bool) -> bool:
        pedido = Pedido(
            fonte=fonte,
            conjunto=conjunto,
            campo=campo,
            canal=Canal.API_EXTERNA,
            finalidade=Finalidade.ANALISE,
            derivado=derivado,
            piloto=piloto,
        )
        return piloto_.registrar(fonte, campo, decidir(pedido, hoje, regras))

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

    `ValueError` se o CNPJ é inválido (a rota responde 422)."""
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
    # os limites são os do leitor (só dos documentos consultados, com o aviso do que ficou de fora), não o texto
    # fixo: linha 897
    limites = limites_da_tela(servida.corpo["limites"], AVISOS_DA_TELA)
    corpo = {**servida.corpo, "limites": list(limites)}
    return Resposta(PRONTA, corpo, fontes_da_resposta(servida.fontes), servida.linhas)
