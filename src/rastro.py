"""O rastro de um número: como foi calculado e de onde veio (B-02 do dossiê da plataforma, 20/10/2026).

O contrato do número (`src/numero.py`) diz de quando ele é, de onde veio e contra o quê comparar, em
texto para quem lê. O rastro é a parte que uma máquina confere (item 7 do lançamento: "como foi
calculado" em um clique e o documento original):

- `formula`: a conta, escrita ao lado do código que a faz (`FORMULAS` em `src/fundamentos.py` e em
  `src/fundamentalista.py`; a fórmula do artigo nas notas clássicas);
- `versao_do_calculo`: o módulo e a versão dele ("fundamentos 2"); sobe quando a fórmula muda, e o
  gabarito por indicador (`tests/test_rastro.py`) quebra se ela mudar sem subir;
- `fonte_id`: o id da coleta em `src/banco/coletas.py` ("cvm"), o mesmo que a trava de licença usa;
  `outras_fontes`, as outras que entram na conta ("yahoo", pelo preço);
- `publicado_em`: o dia em que o insumo mais novo ficou público (a entrega à CVM, não a data do
  balanço; o dia do fechamento, no preço), e os `documentos` usados, com o link de cada um;
- `entradas`: as contas da DFP e do ITR que entram na conta, com o código e o nome na CVM, o valor
  guardado e o documento de onde vieram (`CONTAS_DOS_INDICADORES` em `src/fundamentos.py`): só com
  elas, quem confere refaz o número.

É o subconjunto do `Rastro` do `data_model.md` que os números do relatório usam hoje. Tipos simples,
sem Streamlit: a página, o PDF e a API leem a mesma coisa (ADR 0044).
"""

from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import date

from src.demonstracoes import (
    ACUMULADO,
    ACUMULADO_ANTERIOR,
    COLUNAS_DAS_ACOES,
    EXERCICIO,
    POSICAO,
)

FORMULA, VERSAO, FONTE, PUBLICADO_EM = (
    "fórmula",
    "versão do cálculo",
    "fonte",
    "publicado em",
)


@dataclass(frozen=True)
class DocumentoUsado:
    nome: str  # "DFP de 31/12/2025, versão 1", "fechamento de WEGE3.SA (Yahoo Finance)"
    publicado_em: date | None  # quando ficou público (None: o dia não é conhecido)
    url: str = ""  # o documento original, quando há link


def nome_do_documento(documento: str, referencia: date, versao: int) -> str:
    """O nome de uma demonstração da CVM como o rastro a cita: "DFP de 31/12/2025, versão 1"."""
    return f"{documento} de {referencia:%d/%m/%Y}, versão {int(versao)}"


@dataclass(frozen=True)
class Entrada:
    """Uma conta da demonstração que entra no número, com o valor guardado: só com as entradas,
    quem confere refaz a conta (o gabarito de `tests/test_rastro.py` cobra)."""

    conta: str  # o nome no TickerLab ("receita"), o mesmo de `src/demonstracoes.py`
    codigo: (
        str  # o código na CVM ("3.01"; com "xx" quando é a soma das linhas de um grupo)
    )
    nome: str  # o nome da conta na CVM ("Receita de Venda de Bens e/ou Serviços")
    valor: float  # como na tabela de contas (em reais; ações em unidades)
    periodo: str  # "exercicio", "posicao", "acumulado" ou "acumulado_anterior"
    documento: str  # "DFP" ou "ITR"
    referencia: date  # a data da demonstração
    versao: int
    publicado_em: date | None  # quando a CVM recebeu o documento


@dataclass(frozen=True)
class Rastro:
    formula: str
    versao_do_calculo: str
    fonte_id: str
    publicado_em: date | None
    documentos: tuple[DocumentoUsado, ...] = ()
    outras_fontes: tuple[str, ...] = ()
    entradas: tuple[Entrada, ...] = ()  # vazia quando o número está indisponível

    @classmethod
    def dos_documentos(
        cls,
        formula: str,
        versao_do_calculo: str,
        fonte_id: str,
        documentos: Iterable[DocumentoUsado],
        outras_fontes: tuple[str, ...] = (),
        entradas: tuple[Entrada, ...] = (),
    ) -> "Rastro":
        """O rastro com `publicado_em` tirado dos documentos (o mais recente que tem dia)."""
        documentos = tuple(documentos)
        dias = [d.publicado_em for d in documentos if d.publicado_em is not None]
        return cls(
            formula,
            versao_do_calculo,
            fonte_id,
            max(dias) if dias else None,
            documentos,
            outras_fontes,
            entradas,
        )

    def o_que_falta(self) -> list[str]:
        """As partes do rastro que faltam (vazia quando o número está completo)."""
        partes = (
            (FORMULA, self.formula),
            (VERSAO, self.versao_do_calculo),
            (FONTE, self.fonte_id),
            (PUBLICADO_EM, self.publicado_em),
        )
        return [nome for nome, valor in partes if not valor]


DOCUMENTO = "documento"
SEM_DIA = "dia não conhecido"


@dataclass(frozen=True)
class LinhaDoRastro:
    """Uma linha do "como foi calculado": o rótulo, o texto e o link do documento original."""

    rotulo: str  # "Fórmula", "Versão do cálculo", "Fonte", "Publicado em", "Documento", "Conta"
    texto: str
    url: str = ""


def _dia(dia: date | None) -> str:
    return f"{dia:%d/%m/%Y}" if dia else SEM_DIA


def como_foi_calculado(rastro: Rastro) -> list[LinhaDoRastro]:
    """O rastro para quem lê, parte por parte: a página, o PDF e o app novo mostram estas linhas
    (item 7 do lançamento: "como foi calculado" em um clique e o documento original)."""
    fontes = rastro.fonte_id
    if rastro.outras_fontes:
        fontes += f" (também {', '.join(rastro.outras_fontes)})"
    linhas = [
        LinhaDoRastro(FORMULA.capitalize(), rastro.formula),
        LinhaDoRastro(VERSAO.capitalize(), rastro.versao_do_calculo),
        LinhaDoRastro(FONTE.capitalize(), fontes),
        LinhaDoRastro(PUBLICADO_EM.capitalize(), _dia(rastro.publicado_em)),
    ]
    linhas += [
        LinhaDoRastro(DOCUMENTO.capitalize(), _documento(d), d.url)
        for d in rastro.documentos
    ]
    if not rastro.entradas:
        return linhas
    return [
        *linhas,
        LinhaDoRastro(CONTAS_USADAS.capitalize(), O_QUE_SAO_AS_CONTAS),
        *(LinhaDoRastro(CONTA.capitalize(), _conta(e)) for e in rastro.entradas),
    ]


def _documento(documento: DocumentoUsado) -> str:
    if documento.publicado_em is None:
        return f"{documento.nome} (dia da publicação não conhecido)"
    return f"{documento.nome}, publicado em {_dia(documento.publicado_em)}"


CONTAS_USADAS, CONTA = "contas usadas", "conta"
O_QUE_SAO_AS_CONTAS = (
    "as linhas da demonstração que entram no número, com o valor guardado: com elas, dá para "
    "refazer a conta."
)
PERIODO_EM_TEXTO = {
    EXERCICIO: "no exercício",
    POSICAO: "no saldo do balanço",
    ACUMULADO: "no acumulado do ano",
    ACUMULADO_ANTERIOR: "no acumulado do mesmo período do ano anterior",
}
_EM_ACOES = {conta for conta, _ in COLUNAS_DAS_ACOES}
_POR_ACAO = {"lpa_basico"}


def _conta(entrada: Entrada) -> str:
    """'Receita de Venda (código 3.01 na CVM): R$ 40.804.110.000 no exercício (DFP de ...)'."""
    # as ações vêm de uma coluna do arquivo da composição do capital, não de um código do plano
    tipo = "campo" if entrada.codigo[:1].isalpha() else "código"
    documento = nome_do_documento(entrada.documento, entrada.referencia, entrada.versao)
    return (
        f"{entrada.nome} ({tipo} {entrada.codigo} na CVM): {_valor(entrada)} "
        f"{PERIODO_EM_TEXTO[entrada.periodo]} ({documento})"
    )


def _valor(entrada: Entrada) -> str:
    """O valor guardado: reais inteiros, ações em unidades, o lucro por ação com centavos."""
    if entrada.conta in _POR_ACAO:
        return f"R$ {entrada.valor:.2f} por ação".replace(".", ",")
    inteiro = f"{entrada.valor:,.0f}".replace(",", ".")
    return f"{inteiro} ações" if entrada.conta in _EM_ACOES else f"R$ {inteiro}"


@dataclass(frozen=True)
class Metrica:
    """Um número do relatório como dado (o `Metric` do `data_model.md`), para a API e a base."""

    entidade_id: str  # o CNPJ da companhia
    chave: str
    nome: str
    valor: float | None
    unidade: str
    periodo: str  # de quando é ("12 meses até 30/06/2026", "balanço de 30/06/2026")
    rastro: Rastro
    motivo: str = ""  # por que está indisponível

    def como_dict(self) -> dict:
        """Para a API: datas em texto ISO."""
        return {k: datas_em_texto(v) for k, v in asdict(self).items()}


def datas_em_texto(valor: object) -> object:
    """O valor pronto para JSON: toda data (também dentro de dicionários e listas) vira texto ISO."""
    if isinstance(valor, dict):
        return {k: datas_em_texto(v) for k, v in valor.items()}
    if isinstance(valor, list | tuple):
        return [datas_em_texto(v) for v in valor]
    if isinstance(valor, date):
        return valor.isoformat()
    return valor
