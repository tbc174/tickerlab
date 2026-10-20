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
  balanço; o dia do fechamento, no preço), e os `documentos` usados, com o link de cada um.

É o subconjunto do `Rastro` do `data_model.md` que os números do relatório usam hoje. Tipos simples,
sem Streamlit: a página, o PDF e a API leem a mesma coisa (ADR 0044).
"""

from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import date

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


@dataclass(frozen=True)
class Rastro:
    formula: str
    versao_do_calculo: str
    fonte_id: str
    publicado_em: date | None
    documentos: tuple[DocumentoUsado, ...] = ()
    outras_fontes: tuple[str, ...] = ()

    @classmethod
    def dos_documentos(
        cls,
        formula: str,
        versao_do_calculo: str,
        fonte_id: str,
        documentos: Iterable[DocumentoUsado],
        outras_fontes: tuple[str, ...] = (),
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

    rotulo: str  # "Fórmula", "Versão do cálculo", "Fonte", "Publicado em", "Documento"
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
    return linhas + [
        LinhaDoRastro(DOCUMENTO.capitalize(), _documento(d), d.url)
        for d in rastro.documentos
    ]


def _documento(documento: DocumentoUsado) -> str:
    if documento.publicado_em is None:
        return f"{documento.nome} (dia da publicação não conhecido)"
    return f"{documento.nome}, publicado em {_dia(documento.publicado_em)}"


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
        return {k: _datas_em_texto(v) for k, v in asdict(self).items()}


def _datas_em_texto(valor: object) -> object:
    if isinstance(valor, dict):
        return {k: _datas_em_texto(v) for k, v in valor.items()}
    if isinstance(valor, list | tuple):
        return [_datas_em_texto(v) for v in valor]
    if isinstance(valor, date):
        return valor.isoformat()
    return valor
