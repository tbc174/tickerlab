"""O perfil de uma empresa na API externa (linha 736, PR 2): `/data/v1/companies/{cnpj}/profile`, como era.

`LeitorDeFicha(porta, permitido).ficha(cnpj, como_era_em)` junta, em tipos simples e com as chaves em
português (a rota traduz na saída), o que a base sabia da empresa no dia, campo a campo pelo portão:

- `cadastro_na_receita`: a situação cadastral, a razão social, a natureza jurídica e o Simples como eram, pelo mesmo
  leitor de `companies` (`LeitorDeEmpresas`): o perfil não lê nada da Receita por outro caminho;
- `entregas`: cada DFP e ITR que a companhia aberta devia até o dia, com o prazo da CVM, a primeira
  entrega e a situação da entrega, pela mesma regra da ficha da noite (`base.dossie.entregas_conhecidas_em`).

Cada campo sai no envelope, com a fonte e o dia em que ficou público. O perfil não lê a ficha da noite
(`dossies/atual`, que é só de hoje): monta tudo na hora para o dia pedido. A entrega que ainda não tinha
acontecido no dia sai como `not_filed`, sem a data dela; a falta de um documento conta como pública no dia
do prazo e só sai até o dia em que a base a conferiu (a montagem da tabela). A dívida com a União (PGFN)
fica fora: o portão não a deixa sair (sem a guarda dita, como na ficha de crédito).

Pessoa não sai (ADR 0108 D2.2): o CNPJ só é servido se a rede o conhece como empresa que não é pessoa
(`empresas.e_empresa`, dentro do `LeitorDeEmpresas`); sem o cadastro, nada sai, e o resto é `not_available`,
sem dizer o motivo. Campo negado pelo portão some da resposta, sem `null`. O documento (DFP, ITR) que o portão
não libera não some em silêncio (linha 881, `src/api_externa/nao_disponivel.py`): ele vai em
`entregas_nao_disponiveis` e os limites avisam que a lista de entregas não diz nada sobre ele; com algum
documento consultado, `entregas` sai sempre, vazia quando a empresa não tem entrega.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from base import cnpj as cnpj_
from base.dias_uteis import dias_uteis
from base.dossie import entregas_conhecidas_em
from base.porta import Porta
from base.porta.rede import views
from src.api_externa import nao_disponivel
from src.api_externa.conjuntos import Permitido
from src.api_externa.conjuntos.empresas import LeitorDeEmpresas
from src.api_externa.envelope import campo

CONJUNTO = "profiles"
TABELA_DAS_ENTREGAS = "rotulos_atraso"
FONTES_DAS_ENTREGAS = {"DFP": "cvm-hist-dfp", "ITR": "cvm-hist-itr"}
CAMPOS_DAS_ENTREGAS = (
    "documento", "referencia", "prazo", "primeira_entrega", "dias_uteis_de_atraso",
    "situacao_da_entrega",
)  # fmt: skip
# contas nossas sobre o índice da CVM (o rótulo e os dias úteis), não o dado como a fonte publicou
DERIVADOS = frozenset({"dias_uteis_de_atraso", "situacao_da_entrega"})
# as colunas de `rotulos_atraso` de onde sai a situação da entrega (`_situacao_entregue`)
COLUNAS_DA_SITUACAO = ("atrasou", "atraso_grave", "zona_cinzenta")
CHAVES_DO_PEDIDO = ("cnpj", "como_era_em")

# a situação de cada entrega, em código de fora (D7): a regra de cada rótulo é a da tabela (`rotulos_atraso`)
NO_PRAZO = "on_time"
ATRASOU = "late"
ZONA_CINZENTA = "gray_zone"  # atraso curto, que um feriado local pode explicar
ATRASO_GRAVE = "severely_late"
NAO_ENTREGUE = "not_filed"  # até o dia pedido (ou até o dia em que a base conferiu)

# os limites que valem para todo perfil; os das entregas só entram quando algum documento foi consultado
LIMITES_GERAIS = (
    "Cada campo traz a fonte e o dia em que ficou público: nada publicado depois de known_at entra.",
    "Pessoa natural (MEI, empresário individual) não é servida.",
)
_FRASES_DAS_ENTREGAS = (
    (
        "As entregas cobrem só as companhias do cadastro de companhias abertas da CVM; uma empresa sem "
        "entregas não quer dizer que nada era devido."
    ),
    (
        "A situação de cada entrega é a regra do TickerLab sobre o índice público da CVM (prazo com feriados "
        "e prorrogações); não é opinião sobre a empresa, e nada aqui é recomendação de investimento."
    ),
)
LIMITES_DO_DOCUMENTO = {
    documento: _FRASES_DAS_ENTREGAS for documento in FONTES_DAS_ENTREGAS
}
# o nome de dentro da lista dos documentos (DFP, ITR) que o portão não libera (ou sem a tabela na base)
NAO_DISPONIVEIS = "entregas_nao_disponiveis"
LIMITE_DO_DOCUMENTO_NAO_DISPONIVEL = nao_disponivel.aviso(
    NAO_DISPONIVEIS, "documentos", "a lista de entregas"
)


def limites(
    documentos_servidos: Iterable[str], nao_disponiveis: Sequence[str] = ()
) -> list[str]:
    """Os limites de um perfil: os gerais, as frases das entregas quando algum documento foi consultado e,
    quando algum ficou de fora, o aviso de que a lista de entregas não diz nada sobre ele."""
    return nao_disponivel.limites(
        LIMITES_GERAIS,
        LIMITES_DO_DOCUMENTO,
        documentos_servidos,
        nao_disponiveis,
        LIMITE_DO_DOCUMENTO_NAO_DISPONIVEL,
    )


# os limites com os dois documentos consultados
LIMITES = tuple(limites(FONTES_DAS_ENTREGAS))


@dataclass(frozen=True)
class FichaServida:
    """O que sai de um perfil: o corpo, as fontes usadas (para a atribuição) e as linhas servidas."""

    corpo: dict
    fontes: set[str] = field(default_factory=set)
    linhas: int = 0


def _sim(valor: object) -> bool:
    return False if pd.isna(valor) else bool(valor)  # type: ignore[arg-type]


def _dia(valor: object) -> str | None:
    return None if pd.isna(valor) else pd.Timestamp(valor).date().isoformat()  # type: ignore[arg-type]


def _situacao_entregue(linha: pd.Series) -> str:
    """O rótulo que a tabela deu à entrega, pelas colunas booleanas dela (a rota não recalcula)."""
    if not _sim(linha["atrasou"]):
        return NO_PRAZO
    if _sim(linha["atraso_grave"]):
        return ATRASO_GRAVE
    if _sim(linha["zona_cinzenta"]):
        return ZONA_CINZENTA
    return ATRASOU


def _dias_uteis_desde(prazo: pd.Timestamp, dia: pd.Timestamp) -> int:
    """Os dias úteis do prazo (conta) até `dia` (não conta), como a tabela conta até a entrega."""
    return max(int(dias_uteis(pd.Series([prazo]), pd.Series([dia]))[0]), 0)


def entrega_no_dia(
    linha: pd.Series, dia: pd.Timestamp
) -> tuple[dict[str, object], pd.Timestamp]:
    """Uma linha de `entregas_conhecidas_em` como a base a conhecia em `dia`, e o dia em que esse fato
    ficou público: a entrega até `dia` vale pela entrega; a que ainda não tinha acontecido (ou que a tabela
    não tem) sai `not_filed`, sem data de entrega, e a falta vale pelo prazo."""
    entrega = linha["primeira_entrega"]
    entregue = not pd.isna(entrega) and entrega <= dia
    valores: dict[str, object] = {
        "documento": str(linha["documento"]),
        "referencia": _dia(linha["referencia"]),
        "prazo": _dia(linha["prazo"]),
    }
    if entregue:
        atraso = linha["dias_uteis_de_atraso"]
        valores |= {
            "primeira_entrega": _dia(entrega),
            "dias_uteis_de_atraso": None if pd.isna(atraso) else int(atraso),  # type: ignore[call-overload]
            "situacao_da_entrega": _situacao_entregue(linha),
        }
        return valores, pd.Timestamp(entrega)
    ate = dia if not pd.isna(entrega) else linha["conferido_ate"]
    valores |= {
        "dias_uteis_de_atraso": _dias_uteis_desde(linha["prazo"], ate),
        "situacao_da_entrega": NAO_ENTREGUE,
    }
    return valores, pd.Timestamp(linha["prazo"])


class LeitorDeFicha:
    """Lê o perfil de uma empresa de uma porta para um pedido."""

    def __init__(self, porta: Porta, permitido: Permitido) -> None:
        self.porta = porta
        self.permitido = permitido

    def _rotulos(self, normal: str) -> pd.DataFrame | None:
        """As linhas da companhia em `rotulos_atraso`, lidas sem `como_era_em`: o documento sem entrega
        não tem `publico_em` e a porta o esconderia; o corte do dia fica em `entregas_conhecidas_em`."""
        if TABELA_DAS_ENTREGAS not in views(self.porta.con):
            return None
        return self.porta.ler(
            TABELA_DAS_ENTREGAS, filtros={"cnpj": cnpj_.formatar(normal)}
        )

    def _entrega_servida(
        self, linha: pd.Series, dia: pd.Timestamp
    ) -> tuple[dict, str] | None:
        """A entrega com os campos que o portão libera, cada um no envelope; None se nada sai dela."""
        fonte = FONTES_DAS_ENTREGAS.get(str(linha["documento"]))
        if fonte is None:
            return None
        valores, publico_em = entrega_no_dia(linha, dia)
        # só os campos da lista saem, nesta ordem: um campo novo em `entrega_no_dia` não escapa sozinho
        servidos = {
            nome: campo(valores[nome], fonte=fonte, publico_em=publico_em.date(), visto_em=None)
            for nome in CAMPOS_DAS_ENTREGAS
            if nome in valores and self.permitido(fonte, nome, nome in DERIVADOS)
        }  # fmt: skip
        return (servidos, fonte) if servidos else None

    def _documentos_servidos(self) -> dict[str, list[str]]:
        """Os campos que o portão libera de cada documento (DFP, ITR), na ordem de `CAMPOS_DAS_ENTREGAS`;
        sem a tabela na base, nenhum documento é consultado."""
        tem_a_tabela = TABELA_DAS_ENTREGAS in views(self.porta.con)
        return {
            documento: [
                nome
                for nome in CAMPOS_DAS_ENTREGAS
                if tem_a_tabela and self.permitido(fonte, nome, nome in DERIVADOS)
            ]
            for documento, fonte in FONTES_DAS_ENTREGAS.items()
        }

    def _entregas(self, normal: str, como_era_em: date) -> tuple[list[dict], set[str]]:
        """As entregas que a base conhecia no dia, da mais nova à mais velha, só dos documentos com campo
        liberado (a entrega sem nenhum campo liberado não sai); a lista vazia é a empresa sem entrega."""
        rotulos = self._rotulos(normal)
        if rotulos is None:
            return [], set()
        dia = pd.Timestamp(como_era_em).normalize()
        servidas = [
            servida
            for _, linha in entregas_conhecidas_em(rotulos, dia).iterrows()
            if (servida := self._entrega_servida(linha, dia)) is not None
        ]
        return [linha for linha, _ in servidas], {fonte for _, fonte in servidas}

    def ficha(self, cnpj: str, como_era_em: date) -> FichaServida | None:
        """O perfil do CNPJ como era em `como_era_em`, só com o que o portão libera; None se o CNPJ não é
        de empresa ou se o cadastro não sai (sem cadastro, nada sai)."""
        normal = cnpj_.normalizar_cnpj(cnpj)
        if not normal:
            raise ValueError(f"CNPJ inválido: {cnpj!r}")
        cadastro = LeitorDeEmpresas(self.porta, self.permitido).empresa(
            normal, como_era_em
        )
        if cadastro is None:
            return None
        blocos: dict[str, object] = {
            "cadastro_na_receita": {
                nome: valor
                for nome, valor in cadastro.corpo.items()
                if nome not in CHAVES_DO_PEDIDO
            }
        }
        fontes = set(cadastro.fontes)
        linhas = cadastro.linhas
        documentos = self._documentos_servidos()
        servidos = [documento for documento, campos in documentos.items() if campos]
        nao_disponiveis = nao_disponivel.nao_disponiveis(documentos)
        if servidos:
            # o bloco sai sempre que algum documento foi consultado, mesmo vazio: sumir é só "não consultado"
            entregas, fontes_das_entregas = self._entregas(normal, como_era_em)
            blocos["entregas"] = entregas
            fontes |= fontes_das_entregas
            linhas += len(entregas)
        corpo = {
            "cnpj": normal,
            "como_era_em": como_era_em.isoformat(),
            **blocos,
            NAO_DISPONIVEIS: nao_disponiveis,
            "limites": limites(servidos, nao_disponiveis),
        }
        return FichaServida(corpo, fontes, linhas)
