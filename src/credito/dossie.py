"""O contrato do dossiê de crédito de pessoa jurídica (C-PR01 do Plano Mestre v3.1; N4, linha 113 da fila).

O dossiê junta o que a base pública sabe de uma empresa (pelo CNPJ) **como era num dia**: identificação, situação,
documentos, fundamentos, vínculos com outras pessoas jurídicas (com o grau de confirmação) e operações públicas.
É o primeiro artefato do item 12 do lançamento (crédito de PJ). As regras são conferidas na criação; dossiê que
quebra uma delas não é montado (melhor nenhum dossiê do que um dossiê errado):

1. **Só fato.** Nada de score, nota, semáforo, selo nem opinião de crédito (B-31 e a Resolução CVM 9 esperam
   parecer; ADR 0103): chave com essas palavras ou texto com palavra vedada derruba (`NotaNoDossieError`).
2. **Sem olhar o futuro.** Cada fato tem `Rastro` completo e `publico_em`; nem ele nem os documentos do rastro
   podem ser de depois de `data_de_referencia` (`OlhouOFuturoError`). Vínculo encerrado precisa dizer desde
   quando o fim era público (`ate_publico_em`, a regra D5 da porta).
3. **Ausência nunca é vazio.** Seção sem fato precisa de lacuna escrita (`SecaoSemLacunaError`), com o tipo:
   não observável, sem registro na fonte, bloqueada ou fonte indisponível. Fato sem valor é lacuna, não fato.
4. **Só pessoa jurídica.** A outra parte de um vínculo é uma entidade da rede ("E..."), nunca uma pessoa ("P...");
   nenhum CPF, inteiro ou mascarado, em texto nenhum (`PessoaNoDossieError`). O nome de sócio pessoa física só
   sairia pelo portão dos nomes (`base/porta/pessoas.py`), que segue fechado: aqui ele é lacuna bloqueada.
5. **Tipos simples.** `como_dict()` dá JSON (datas em texto ISO), para a API e uma tela futura.

Os eventos de PJ (mudou, não observado, fonte falhou) entram depois, com o motor da N5 (linha 115).

**Rota futura (C-PR05, depois de N4 e N5; não criada aqui):** `GET /v1/credito/dossies/{cnpj}?em=AAAA-MM-DD` em
`src/api_v1/`, devolvendo `como_dict()`, atrás dos portões compartilhados do crédito (plano Casa e o beta Crédito
autorizado pelo Tiago), com o CNPJ pedido fora do log como na busca por CNPJ (o CNPJ de um MEI é dado pessoal).
"""

import re
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from datetime import date
from typing import Literal

from base import cnpj as cnpj_
from base.contrapartes.cafe import palavras_vedadas_em
from base.rede.ids import PREFIXO_DE_PESSOA
from src.credito.features import OlhouOFuturoError
from src.rastro import Rastro, datas_em_texto

VERSAO_DO_CONTRATO = "1.0.0"

Secao = Literal[
    "identificacao",
    "situacao",
    "documentos",
    "fundamentos",
    "vinculos",
    "operacoes_publicas",
]
SECOES: tuple[Secao, ...] = (
    "identificacao",
    "situacao",
    "documentos",
    "fundamentos",
    "vinculos",
    "operacoes_publicas",
)

TipoDeLacuna = Literal[
    "nao_observavel", "sem_registro", "bloqueada", "fonte_indisponivel"
]
NAO_OBSERVAVEL: TipoDeLacuna = (
    "nao_observavel"  # o dado não é público: a base não tem como ver
)
# procurado na fonte até o dia, sem achar: ausência de evidência não é evidência de ausência
SEM_REGISTRO: TipoDeLacuna = "sem_registro"
BLOQUEADA: TipoDeLacuna = (
    "bloqueada"  # a base vê, mas não mostra até a regra deixar (parecer, portão)
)
# a fonte não estava na base no dia (tabela ausente, vista que não chegou ao servidor)
FONTE_INDISPONIVEL: TipoDeLacuna = "fonte_indisponivel"
TIPOS_DE_LACUNA: tuple[TipoDeLacuna, ...] = (
    NAO_OBSERVAVEL,
    SEM_REGISTRO,
    BLOQUEADA,
    FONTE_INDISPONIVEL,
)

GrauDeConfirmacao = Literal[
    "documento_oficial", "tabela_conferida", "declarado_por_terceiro"
]
# declarado num documento ou cadastro oficial (FRE, FCA, carteira da CVM, IF.data, quadro de sócios da Receita),
# com as duas pontas ligadas por regra de código
DOCUMENTO_OFICIAL: GrauDeConfirmacao = "documento_oficial"
# documento oficial, mas uma das pontas só foi ligada pela tabela conferida à mão (`conferido_por` = tabela)
TABELA_CONFERIDA: GrauDeConfirmacao = "tabela_conferida"
# só um terceiro diz (o post da assessoria de M&A), sem confirmação numa fonte oficial
DECLARADO_POR_TERCEIRO: GrauDeConfirmacao = "declarado_por_terceiro"
GRAUS: tuple[GrauDeConfirmacao, ...] = (
    DOCUMENTO_OFICIAL,
    TABELA_CONFERIDA,
    DECLARADO_POR_TERCEIRO,
)

Sentido = Literal["da_empresa", "para_a_empresa"]
DA_EMPRESA: Sentido = "da_empresa"  # a empresa do dossiê é `tipo` da outra parte (controlada_de: é controlada)
PARA_A_EMPRESA: Sentido = (
    "para_a_empresa"  # a outra parte é `tipo` da empresa (controlada_de: controla)
)
SENTIDOS: tuple[Sentido, ...] = (DA_EMPRESA, PARA_A_EMPRESA)

PREFIXO_DE_ENTIDADE = "E"
# palavras que fazem de um número uma nota (pedaços da chave entre "_")
PEDACOS_DE_NOTA = frozenset({"score", "nota", "semaforo", "selo"})
# CPF inteiro (com ou sem pontuação, sem encostar em outro dígito: o CNPJ tem 14) ou mascarado como a Receita
CPF = re.compile(
    r"(?<![\d./-])\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?![\d./-])|\*{3}\.?\d{3}\.?\d{3}-?\*{2}"
)
CAMPOS_SEM_TEXTO_LIVRE = frozenset(
    {"url"}
)  # links da fonte: números de protocolo não são CPF

LIMITES = (
    "Cada fato vem com a fonte, a data em que ficou público e o rastro; só entra o que era público no dia.",
    "O que a base não vê, não achou ou não pode mostrar aparece como lacuna, com o motivo: nada é estimado.",
    "Só pessoas jurídicas: nenhum nome nem CPF de pessoa física.",
    (
        "Nada aqui é nota, score, rating nem opinião de crédito, e nada é recomendação de investimento ou "
        "de concessão de crédito."
    ),
)


class SecaoSemLacunaError(ValueError):
    """Uma seção ficou vazia sem a lacuna que diz por quê."""


class PessoaNoDossieError(ValueError):
    """O dossiê traria uma pessoa física (id de pessoa ou CPF)."""


class NotaNoDossieError(ValueError):
    """O dossiê traria uma nota, um score ou um julgamento."""


@dataclass(frozen=True)
class Fato:
    """Um fato da empresa: o valor, o rastro e desde quando é público."""

    chave: str  # "razao_social", "situacao_cadastral", "alavancagem"
    valor: str | int | float | bool
    rastro: Rastro
    publico_em: date
    aconteceu_em: date | None = (
        None  # a data do fato, quando difere da publicação ("ativa desde")
    )
    unidade: str = ""
    periodo: str = ""  # de quando é o número ("12 meses até 31/03/2025")


@dataclass(frozen=True)
class Documento:
    """Um documento oficial da empresa que era público no dia (DFP, ITR, FRE, FCA, cadastro da Receita)."""

    tipo: str
    referente_a: (
        date | None
    )  # a data-base (o fim do exercício na DFP); None quando não há
    publico_em: date
    rastro: Rastro
    versao: str = ""
    url: str = ""


@dataclass(frozen=True)
class ParteJuridica:
    """A outra ponta de um vínculo ou de uma operação: uma entidade da rede, nunca uma pessoa."""

    id_entidade: str  # "E" + 20 hexadecimais (`base/rede/ids.py`)
    tipo: str  # empresa, fundo, valor_mobiliario ou auditor
    nome: str
    cnpj: str | None = None


@dataclass(frozen=True)
class Vinculo:
    """Uma ligação da empresa com outra pessoa jurídica, como era no dia."""

    tipo: str  # o tipo de `ligacoes` (controlada_de, coligada_de, audita, emite, detem...)
    sentido: Sentido
    outra_parte: ParteJuridica
    grau: GrauDeConfirmacao
    rastro: Rastro
    publico_em: date
    desde: date | None = None  # `aconteceu_em` da ligação
    ate: date | None = (
        None  # o fim (sem incluir o dia), só quando já era público no dia
    )
    ate_publico_em: date | None = None  # desde quando se sabia do fim
    participacao: float | None = None  # % do capital, quando a fonte diz


@dataclass(frozen=True)
class Operacao:
    """Uma operação pública em que a empresa aparece (debênture, CRI, CRA, FIDC, nota comercial)."""

    papel: str  # emissor, cedente, devedor, securitizadora, administrador, gestor
    instrumento: str
    identificador: str  # ISIN ou o código da CVM
    rastro: Rastro
    publico_em: date
    descricao: str = ""
    contraparte: ParteJuridica | None = None


@dataclass(frozen=True)
class Lacuna:
    """O que a base não sabe da empresa, escrito: o assunto, o tipo da ausência e o motivo."""

    secao: Secao
    assunto: str  # "nome dos sócios pessoa física"
    tipo: TipoDeLacuna
    motivo: str
    fonte_id: str = ""  # a fonte procurada, quando há uma


@dataclass(frozen=True)
class DossieCredito:
    """O dossiê de crédito de um CNPJ como era em `data_de_referencia` (só o público até esse dia, D5)."""

    cnpj: str  # 14 caracteres, sem pontuação
    data_de_referencia: date
    identificacao: tuple[Fato, ...]
    situacao: tuple[Fato, ...]
    documentos: tuple[Documento, ...]
    fundamentos: tuple[Fato, ...]
    vinculos: tuple[Vinculo, ...]
    operacoes_publicas: tuple[Operacao, ...]
    lacunas: tuple[Lacuna, ...]
    versao_do_contrato: str = VERSAO_DO_CONTRATO
    limites: tuple[str, ...] = LIMITES

    def __post_init__(self) -> None:
        if cnpj_.normalizar_cnpj(self.cnpj) != self.cnpj:
            raise ValueError(
                f"{self.cnpj!r} não é um CNPJ de 14 caracteres sem pontuação"
            )
        _conferir_lacunas(self.lacunas)
        ordem = {secao: posicao for posicao, secao in enumerate(SECOES)}
        object.__setattr__(
            self, "lacunas", tuple(sorted(self.lacunas, key=lambda l: ordem[l.secao]))
        )
        _conferir_secoes(self)
        _conferir_ponto_no_tempo(self)
        _conferir_vinculos(self.vinculos)
        _conferir_sem_nota(self)
        _conferir_sem_pessoa(self)

    def lacunas_da(self, secao: Secao) -> tuple[Lacuna, ...]:
        return tuple(lacuna for lacuna in self.lacunas if lacuna.secao == secao)

    def como_dict(self) -> dict:
        """Para a API: tipos simples, datas em texto ISO."""
        return {k: datas_em_texto(v) for k, v in asdict(self).items()}


# --- as conferências ------------------------------------------------------------------------------
def _conferir_lacunas(lacunas: tuple[Lacuna, ...]) -> None:
    for lacuna in lacunas:
        if lacuna.secao not in SECOES:
            raise ValueError(f"lacuna de seção desconhecida: {lacuna.secao!r}")
        if lacuna.tipo not in TIPOS_DE_LACUNA:
            raise ValueError(f"lacuna de tipo desconhecido: {lacuna.tipo!r}")
        if not lacuna.assunto.strip() or not lacuna.motivo.strip():
            raise ValueError(
                f"lacuna sem assunto ou sem motivo na seção {lacuna.secao}"
            )


def _conferir_secoes(dossie: DossieCredito) -> None:
    for secao in SECOES:
        if not getattr(dossie, secao) and not dossie.lacunas_da(secao):
            raise SecaoSemLacunaError(
                f"a seção {secao} está vazia e sem lacuna que diga por quê"
            )
    for fato in (*dossie.identificacao, *dossie.situacao, *dossie.fundamentos):
        if fato.valor is None or (
            isinstance(fato.valor, str) and not fato.valor.strip()
        ):
            raise ValueError(f"{fato.chave}: fato sem valor é lacuna, não fato")


def _datados(dossie: DossieCredito) -> Iterator[tuple[str, date, Rastro]]:
    """Cada item do dossiê com o nome, o `publico_em` e o rastro."""
    for fato in (*dossie.identificacao, *dossie.situacao, *dossie.fundamentos):
        yield fato.chave, fato.publico_em, fato.rastro
    for documento in dossie.documentos:
        yield f"documento {documento.tipo}", documento.publico_em, documento.rastro
    for vinculo in dossie.vinculos:
        yield f"vínculo {vinculo.tipo}", vinculo.publico_em, vinculo.rastro
    for operacao in dossie.operacoes_publicas:
        yield f"operação {operacao.identificador}", operacao.publico_em, operacao.rastro


def _conferir_ponto_no_tempo(dossie: DossieCredito) -> None:
    dia = dossie.data_de_referencia
    for nome, publico_em, rastro in _datados(dossie):
        if rastro.o_que_falta():
            raise ValueError(f"{nome}: rastro sem {', '.join(rastro.o_que_falta())}")
        dias = [publico_em] + [
            d.publicado_em for d in rastro.documentos if d.publicado_em
        ]
        if futuros := [d for d in dias if d > dia]:
            raise OlhouOFuturoError(
                f"{nome}: usa o publicado em {max(futuros):%d/%m/%Y}, depois de {dia:%d/%m/%Y}"
            )
    for vinculo in dossie.vinculos:
        if vinculo.ate_publico_em and vinculo.ate_publico_em > dia:
            raise OlhouOFuturoError(
                f"vínculo {vinculo.tipo}: o fim só ficou público em {vinculo.ate_publico_em:%d/%m/%Y}"
            )


def _conferir_vinculos(vinculos: tuple[Vinculo, ...]) -> None:
    for vinculo in vinculos:
        if vinculo.grau not in GRAUS:
            raise ValueError(
                f"vínculo {vinculo.tipo}: grau de confirmação desconhecido"
            )
        if vinculo.sentido not in SENTIDOS:
            raise ValueError(f"vínculo {vinculo.tipo}: sentido desconhecido")
        if vinculo.ate and not vinculo.ate_publico_em:
            raise ValueError(f"vínculo {vinculo.tipo}: fim sem ate_publico_em")


def _partes(dossie: DossieCredito) -> Iterator[ParteJuridica]:
    yield from (vinculo.outra_parte for vinculo in dossie.vinculos)
    yield from (o.contraparte for o in dossie.operacoes_publicas if o.contraparte)


def _textos(valor: object, campo: str = "") -> Iterator[str]:
    """Todo texto do dossiê já em tipos simples, menos os links."""
    if campo in CAMPOS_SEM_TEXTO_LIVRE:
        return
    if isinstance(valor, str):
        yield valor
    elif isinstance(valor, dict):
        for chave, dentro in valor.items():
            yield from _textos(dentro, chave)
    elif isinstance(valor, list | tuple):
        for dentro in valor:
            yield from _textos(dentro)


def _conferir_sem_pessoa(dossie: DossieCredito) -> None:
    for parte in _partes(dossie):
        if parte.id_entidade.startswith(
            PREFIXO_DE_PESSOA
        ) or not parte.id_entidade.startswith(PREFIXO_DE_ENTIDADE):
            raise PessoaNoDossieError(
                "a outra parte precisa ser uma entidade da rede, não uma pessoa"
            )
    sem_os_limites = {k: v for k, v in dossie.como_dict().items() if k != "limites"}
    if any(CPF.search(texto) for texto in _textos(sem_os_limites)):
        raise PessoaNoDossieError("há um CPF (inteiro ou mascarado) no dossiê")


def _conferir_sem_nota(dossie: DossieCredito) -> None:
    for fato in (*dossie.identificacao, *dossie.situacao, *dossie.fundamentos):
        if PEDACOS_DE_NOTA & set(fato.chave.lower().split("_")):
            raise NotaNoDossieError(
                f"{fato.chave}: o dossiê traz fatos, não notas nem scores"
            )
    sem_os_limites = {k: v for k, v in dossie.como_dict().items() if k != "limites"}
    for texto in _textos(sem_os_limites):
        if vedadas := palavras_vedadas_em(texto):
            raise NotaNoDossieError(f"palavra vedada no dossiê: {', '.join(vedadas)}")
