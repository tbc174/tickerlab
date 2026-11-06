"""Contrato comum dos **fatos financeiros documentais** (linha 718 da fila; ADR 0124): o que o TickerLab
guarda de um número lido num documento público (balanço no jornal oficial, prospecto, relatório de fundo
regional, CSV da Receita), sempre com a prova de onde saiu.

Quatro tabelas, cada linha com o carimbo do documento de onde veio (`consta`, `disponivel_em`,
`visto_em`, `origem_sha256`, `origem_coletada_em`, os mesmos de `base/retratos.py`):

- `documento`: o arquivo guardado, pela chave `sha256`;
- `identidade_documental`: quem o documento diz que é cada parte (CNPJ de 14 dígitos ou raiz de 8), com
  o papel e a página da prova; nome aproximado sem CNPJ só entra como `candidato`;
- `fato_financeiro`: um valor como está impresso (`valor_original`) e já na unidade (`valor`), com a
  página, a célula ou linha, a data-base e a visão;
- `vinculo_economico`: a relação entre dois documentos da mesma operação; nunca soma.

Regras do briefing de 04/11/2026 que o código trava:

- **Nulo, traço e zero são três valores**: `valor` nulo com `valor_original` vazio ou `-`; `0` é zero.
- **Conflito guarda as duas provas** (`conflito`): duas linhas com `estado = "conflito"` e o mesmo
  `grupo_de_conflito`, cada uma com a própria página e o próprio texto. Nunca uma média, nunca "a mais
  recente": quem decide é a conferência, com as duas provas à vista.
- **Vínculo nunca soma** (`aditivo` é sempre `False`), e **reconciliação não é saldo**: nominal menos
  juros a transcorrer vira `vinculo_economico` com `relacao = "reconciliacao"`, não um terceiro número.
- **Pessoa física não entra**: CPF (11 dígitos) e papel terminado em `-pf` são recusados.
- Um vínculo só fica público quando os dois documentos estão: o carimbo é o do que saiu por último.

Este módulo só monta as tabelas em memória (`montar`) e diz o esquema delas (`esquemas`, `como_arrow`);
quem lê os documentos e quem grava o parquet vem nas tarefas seguintes do plano.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pyarrow as pa

from base.retratos import CARIMBOS

PAPEIS = (
    "devedora",
    "emissora",
    "credora",
    "avalista-pj",
    "coordenador",
    "beneficiaria",
    "executora",
    "securitizadora",
)
VISOES = ("individual", "consolidada")
NATUREZAS = ("estoque", "fluxo", "acumulado")
ESTADOS = ("extraido", "conferido", "conflito")
RELACOES = ("mesma-operacao", "emissao-saldo", "contrato-liberacao", "reconciliacao")
FORMATOS = ("pdf", "csv", "xlsx", "html")
# quanto vale 1 na unidade que o documento declara (a escala vem da nota de políticas contábeis)
ESCALAS = {"unidade": Decimal(1), "mil": Decimal(1_000), "milhao": Decimal(1_000_000)}
# a fonte escreve traço onde não há valor: não é zero
TRACOS = frozenset({"-", "–", "—"})
# `valor` guarda duas casas (decimal128(18, 2)); não arredonda
CASAS_DA_TABELA = Decimal("0.01")
TIPO_DO_DINHEIRO = pa.decimal128(18, 2)
# os valores de aceite do briefing de 04/11/2026, conferidos na pesquisa (um por linha, com a prova)
CAMINHO_DO_GABARITO = (
    Path(__file__).resolve().parent / "conferidas" / "fatos_documentais_gabarito.csv"
)
TIPO_DO_INSTANTE = pa.timestamp("us", tz="UTC")
DIGITOS_DO_CNPJ = 14
DIGITOS_DA_RAIZ = 8
DIGITOS_DO_CPF = 11
TAMANHO_DO_SHA256 = 64
SUFIXO_DE_PESSOA_FISICA = "-pf"
SEPARADOR_DA_CHAVE = "|"
# um número como se imprime em português: "41.250", "70.584.033,86", "R$ 1.500", "3,63%", "-12"
NUMERO_IMPRESSO = re.compile(
    r"^(?P<sinal>-)?\s*(?:R\$\s*)?(?P<inteiro>\d{1,3}(?:\.\d{3})+|\d+)(?:,(?P<casas>\d+))?\s*%?$"
)


class TextoNaoENumero(ValueError):
    """O texto não é um número como se imprime em português (41.250 ou 3,63)."""


def _exigir(valor: str, aceitos: Sequence[str], nome: str) -> None:
    if valor not in aceitos:
        raise ValueError(
            f"{nome} {valor!r} não é um dos aceitos: {', '.join(aceitos)}."
        )


def _exigir_instante(instante: datetime, nome: str) -> None:
    if instante.tzinfo is None:
        raise ValueError(
            f"{nome} precisa de fuso horário (UTC): sem ele não se sabe quando foi."
        )


@dataclass(frozen=True)
class Documento:
    """Um arquivo guardado no acervo, pela chave `sha256`, e a página que o publicou.

    `disponivel_em` é o dia em que o arquivo ficou público (nos CSV, o `Last-Modified`); é dele que
    sai o carimbo de cada linha tirada do documento. `guardado_em` é o caminho no acervo (`restrito/`
    quando há pessoa). `licenca` e `familia` dizem o que se pode fazer com o conteúdo (ADR 0124).
    """

    sha256: str
    url_observada: str
    pagina_que_publicou: str
    bytes: int
    coletado_em: datetime
    disponivel_em: date
    formato: str
    familia: str
    guardado_em: str
    licenca: str
    data_declarada: date | None = None
    paginas: int | None = None

    def __post_init__(self) -> None:
        e_sha256 = len(self.sha256) == TAMANHO_DO_SHA256 and all(
            c in "0123456789abcdef" for c in self.sha256
        )
        if not e_sha256:
            raise ValueError("sha256 precisa de 64 caracteres hexadecimais minúsculos.")
        if self.bytes <= 0:
            raise ValueError(
                "Documento sem bytes não é documento: tentativa vazia não é coleta."
            )
        _exigir(self.formato, FORMATOS, "formato")
        _exigir_instante(self.coletado_em, "coletado_em")


@dataclass(frozen=True)
class Identidade:
    """Quem o documento diz que é uma parte: CNPJ (14 dígitos) ou raiz (8), o papel e a prova.

    Nome aproximado sem CNPJ só entra como `candidato` (e candidato não leva CNPJ: quando a conferência
    acha o CNPJ, tira o candidato). Pessoa física nunca entra: CPF e papel `-pf` são recusados.
    """

    documento: str
    identificador_na_fonte: str
    papel: str
    evidencia: str
    cnpj: str = ""
    cnpj_raiz: str = ""
    vigencia_inicio: date | None = None
    vigencia_fim: date | None = None
    candidato: bool = False
    conferido_em: date | None = None

    def __post_init__(self) -> None:
        if self.papel.endswith(SUFIXO_DE_PESSOA_FISICA):
            raise ValueError(
                f"Papel {self.papel!r}: pessoa física não entra na base (só pessoa jurídica)."
            )
        _exigir(self.papel, PAPEIS, "papel")
        _conferir_digitos("CNPJ", self.cnpj, DIGITOS_DO_CNPJ)
        _conferir_digitos("raiz do CNPJ", self.cnpj_raiz, DIGITOS_DA_RAIZ)
        _conferir_candidato(self)

    @property
    def chave(self) -> str:
        """Como o fato aponta para a identidade dentro do documento: identificador e papel."""
        return f"{self.identificador_na_fonte}{SEPARADOR_DA_CHAVE}{self.papel}"


def _conferir_digitos(nome: str, valor: str, digitos: int) -> None:
    if valor == "" or (valor.isdigit() and len(valor) == digitos):
        return
    pessoa_fisica = "; 11 dígitos é CPF, pessoa física, que não entra na base"
    complemento = pessoa_fisica if len(valor) == DIGITOS_DO_CPF else ""
    raise ValueError(f"{nome} {valor!r} precisa de {digitos} dígitos{complemento}.")


def _conferir_candidato(identidade: Identidade) -> None:
    if identidade.cnpj and identidade.cnpj_raiz:
        raise ValueError("Identidade leva CNPJ ou raiz do CNPJ, não os dois.")
    tem_cnpj = bool(identidade.cnpj or identidade.cnpj_raiz)
    if identidade.candidato and tem_cnpj:
        raise ValueError("Nome aproximado não leva CNPJ: confira e tire o `candidato`.")
    if not identidade.candidato and not tem_cnpj:
        raise ValueError(
            "Identidade sem CNPJ nem raiz só entra como candidato (nome aproximado)."
        )


@dataclass(frozen=True)
class Vinculo:
    """A relação entre dois documentos da mesma operação (emissão e saldo, contrato e liberação,
    nominal e juros a transcorrer). Nunca soma: `aditivo` é sempre `False`, e a reconciliação não
    vira um terceiro saldo."""

    operacao: str
    documento_a: str
    documento_b: str
    relacao: str
    aditivo: bool = False

    def __post_init__(self) -> None:
        if self.aditivo:
            raise ValueError(
                "Vínculo econômico nunca soma: é a mesma operação vista em dois documentos."
            )
        _exigir(self.relacao, RELACOES, "relação")


@dataclass(frozen=True)
class Fato:
    """Um valor lido num documento, como está impresso e já na unidade, com a prova de onde saiu.

    `valor` sai do texto quando o texto é um número ("41.250" em mil é 41.250.000,00). Quando a fonte
    escreve o número dentro de uma frase ("DI + 1,60% a.a."), quem leu informa o `valor`, e a frase
    fica inteira em `valor_original`. Medida que é uma data (vencimento) usa `valor_data`. Percentual
    fica em pontos percentuais (3,63), como impresso. Mais casas que a tabela guarda é erro.
    """

    documento: str
    identidade: str
    medida: str
    data_base: date
    visao: str
    pagina_pdf: int
    celula_ou_linha: str
    valor_original: str
    unidade_declarada: str
    natureza: str
    valor: Decimal | None = None
    valor_data: date | None = None
    moeda: str = "BRL"
    periodo_inicio: date | None = None
    periodo_fim: date | None = None
    pagina_impressa: int | None = None
    versao_do_documento: str | None = None
    estado: str = "extraido"
    grupo_de_conflito: str | None = None
    conferido_em: date | None = None

    def __post_init__(self) -> None:
        _exigir(self.visao, VISOES, "visão")
        _exigir(self.natureza, NATUREZAS, "natureza")
        _exigir(self.estado, ESTADOS, "estado")
        object.__setattr__(self, "valor", _valor_do_fato(self))

    @property
    def classe_do_valor(self) -> str:
        """`nulo` (célula vazia), `traco`, `zero`, `numero` ou `data`: nulo, traço e zero são três."""
        if self.valor_data is not None:
            return "data"
        texto = _texto_limpo(self.valor_original)
        if texto == "":
            return "nulo"
        if texto in TRACOS:
            return "traco"
        return "zero" if self.valor == 0 else "numero"


def _texto_limpo(texto: str) -> str:
    return texto.replace("\xa0", " ").strip()


def numero_impresso(texto: str, unidade_declarada: str) -> Decimal | None:
    """O número de um texto como se imprime em português ("70.584.033,86", "(12.823)", "3,63%"), já
    na unidade declarada; célula vazia e traço devolvem nulo; outro texto levanta `TextoNaoENumero`.
    Mais casas que a tabela guarda (duas) é erro, não arredondamento."""
    limpo = _texto_limpo(texto)
    if limpo == "" or limpo in TRACOS:
        return None
    entre_parenteses = limpo.startswith("(") and limpo.endswith(")")
    partes = NUMERO_IMPRESSO.match(limpo[1:-1].strip() if entre_parenteses else limpo)
    if partes is None:
        raise TextoNaoENumero(
            f"{texto!r} não é um número como se imprime em português (41.250)."
        )
    if unidade_declarada not in ESCALAS:
        raise ValueError(
            f"Unidade {unidade_declarada!r} desconhecida; aceitas: {', '.join(ESCALAS)}."
        )
    inteiro = partes.group("inteiro").replace(".", "")
    valor = (
        Decimal(f"{inteiro}.{partes.group('casas') or '0'}")
        * ESCALAS[unidade_declarada]
    )
    if entre_parenteses or partes.group("sinal"):
        valor = -valor
    return _com_as_casas_da_tabela(valor, texto)


def _com_as_casas_da_tabela(valor: Decimal, texto: str) -> Decimal:
    nas_casas = valor.quantize(CASAS_DA_TABELA)
    if nas_casas != valor:
        raise ValueError(
            f"{texto!r} tem mais casas que a tabela guarda (duas): não arredondo."
        )
    return nas_casas


def _valor_do_fato(fato: Fato) -> Decimal | None:
    """O `valor` já na unidade: do texto quando ele é um número; o informado por quem leu quando não."""
    if fato.valor_data is not None:
        if fato.valor is not None:
            raise ValueError(
                "Fato com `valor_data` não leva `valor`: ou é número ou é data."
            )
        return None
    try:
        lido = numero_impresso(fato.valor_original, fato.unidade_declarada)
    except TextoNaoENumero:
        if fato.valor is None:
            raise
        return _com_as_casas_da_tabela(fato.valor, fato.valor_original)
    if fato.valor is not None and fato.valor != lido:
        raise ValueError(
            f"`valor` {fato.valor} não bate com o texto {fato.valor_original!r} ({lido} na unidade)."
        )
    return lido


@dataclass(frozen=True)
class Registros:
    """O que foi lido de um lote de documentos, antes de virar tabela."""

    documentos: Sequence[Documento] = ()
    identidades: Sequence[Identidade] = ()
    fatos: Sequence[Fato] = ()
    vinculos: Sequence[Vinculo] = ()


def _assunto(fato: Fato) -> tuple[str, str, str, str]:
    return (fato.identidade, fato.medida, fato.data_base.isoformat(), fato.visao)


def _mesmo_valor(a: Fato, b: Fato) -> bool:
    if a.valor_original == b.valor_original:
        return True
    if a.valor is not None and a.valor == b.valor:
        return True
    return a.valor_data is not None and a.valor_data == b.valor_data


def conflito(a: Fato, b: Fato) -> tuple[Fato, Fato]:
    """Marca dois fatos que dizem coisas diferentes sobre a mesma medida (Santander vence em nov/2030
    numa página e em jul/2030 noutra; IPCA + 3,63% na capa e 3,87% na nota): os dois voltam com
    `estado = "conflito"` e o mesmo `grupo_de_conflito`, cada um com a própria página e o próprio
    texto. Nunca uma média, nunca "o mais recente": quem decide é a conferência, com as duas provas."""
    if _assunto(a) != _assunto(b):
        raise ValueError(
            "Conflito só entre fatos da mesma identidade, medida, data-base e visão; "
            f"aqui {_assunto(a)} × {_assunto(b)}."
        )
    if _mesmo_valor(a, b):
        raise ValueError(
            f"Não é conflito: os dois fatos trazem o mesmo valor ({a.valor_original!r})."
        )
    grupo = SEPARADOR_DA_CHAVE.join(_assunto(a))
    marcar = {"estado": "conflito", "grupo_de_conflito": grupo}
    return replace(a, **marcar), replace(b, **marcar)


_CAMPOS: dict[str, list[tuple[str, pa.DataType]]] = {
    "documento": [
        ("sha256", pa.string()),
        ("url_observada", pa.string()),
        ("pagina_que_publicou", pa.string()),
        ("bytes", pa.int64()),
        ("coletado_em", TIPO_DO_INSTANTE),
        ("data_declarada", pa.date32()),
        ("formato", pa.string()),
        ("paginas", pa.int64()),
        ("familia", pa.string()),
        ("guardado_em", pa.string()),
        ("licenca", pa.string()),
    ],
    "identidade_documental": [
        ("documento", pa.string()),
        ("identificador_na_fonte", pa.string()),
        ("papel", pa.string()),
        ("cnpj", pa.string()),
        ("cnpj_raiz", pa.string()),
        ("vigencia_inicio", pa.date32()),
        ("vigencia_fim", pa.date32()),
        ("evidencia", pa.string()),
        ("candidato", pa.bool_()),
        ("conferido_em", pa.date32()),
    ],
    "fato_financeiro": [
        ("documento", pa.string()),
        ("identidade", pa.string()),
        ("medida", pa.string()),
        ("data_base", pa.date32()),
        ("visao", pa.string()),
        ("pagina_pdf", pa.int64()),
        ("celula_ou_linha", pa.string()),
        ("valor_original", pa.string()),
        ("valor", TIPO_DO_DINHEIRO),
        ("valor_data", pa.date32()),
        ("moeda", pa.string()),
        ("unidade_declarada", pa.string()),
        ("periodo_inicio", pa.date32()),
        ("periodo_fim", pa.date32()),
        ("natureza", pa.string()),
        ("pagina_impressa", pa.int64()),
        ("versao_do_documento", pa.string()),
        ("estado", pa.string()),
        ("grupo_de_conflito", pa.string()),
        ("conferido_em", pa.date32()),
    ],
    "vinculo_economico": [
        ("operacao", pa.string()),
        ("documento_a", pa.string()),
        ("documento_b", pa.string()),
        ("relacao", pa.string()),
        ("aditivo", pa.bool_()),
    ],
}
_TIPOS_DOS_CARIMBOS = {
    "disponivel_em": pa.date32(),
    "visto_em": TIPO_DO_INSTANTE,
    "origem_sha256": pa.string(),
    "origem_coletada_em": TIPO_DO_INSTANTE,
}
_CARIMBOS = [("consta", pa.bool_()), *((c, _TIPOS_DOS_CARIMBOS[c]) for c in CARIMBOS)]


def esquemas() -> dict[str, pa.Schema]:
    """O esquema Arrow de cada uma das quatro tabelas, com os carimbos no fim (`valor` é
    `decimal128(18, 2)`; instantes em UTC; datas sem hora)."""
    return {nome: pa.schema([*campos, *_CARIMBOS]) for nome, campos in _CAMPOS.items()}


def como_arrow(nome: str, tabela: pd.DataFrame) -> pa.Table:
    """A tabela no esquema do contrato (o que o parquet grava): tipo errado ou coluna a mais é erro."""
    return pa.Table.from_pandas(tabela, schema=esquemas()[nome], preserve_index=False)


def montar(registros: Registros, agora: datetime) -> dict[str, pd.DataFrame]:
    """As quatro tabelas do contrato, em memória, na ordem dos registros, cada linha com o carimbo do
    documento de onde saiu (`consta=True`, `visto_em=agora`, `disponivel_em`, `origem_sha256` e
    `origem_coletada_em` do documento; o vínculo leva o documento que ficou público por último).
    Linha que aponta para documento ou identidade ausente é erro: sem prova não entra."""
    _exigir_instante(agora, "agora")
    documentos = _documentos_por_sha(registros.documentos)
    _conferir_referencias(registros, documentos)
    linhas = {
        "documento": [
            _linha("documento", d) | _carimbos(d, agora) for d in registros.documentos
        ],
        "identidade_documental": [
            _linha("identidade_documental", i)
            | _carimbos(documentos[i.documento], agora)
            for i in registros.identidades
        ],
        "fato_financeiro": [
            _linha("fato_financeiro", f) | _carimbos(documentos[f.documento], agora)
            for f in registros.fatos
        ],
        "vinculo_economico": [
            _linha("vinculo_economico", v)
            | _carimbos(_ultimo_publico(v, documentos), agora)
            for v in registros.vinculos
        ],
    }
    return {
        nome: pd.DataFrame(linhas[nome], columns=esquema.names)
        for nome, esquema in esquemas().items()
    }


def _documentos_por_sha(documentos: Sequence[Documento]) -> dict[str, Documento]:
    por_sha = {d.sha256: d for d in documentos}
    if len(por_sha) != len(documentos):
        raise ValueError(
            "Há documento repetido nos registros: cada sha256 entra uma vez."
        )
    return por_sha


def _conferir_referencias(
    registros: Registros, documentos: Mapping[str, Documento]
) -> None:
    for identidade in registros.identidades:
        _exigir_documento(
            identidade.documento, documentos, f"identidade {identidade.chave!r}"
        )
    identidades = {(i.documento, i.chave) for i in registros.identidades}
    for fato in registros.fatos:
        _exigir_documento(fato.documento, documentos, f"fato {fato.medida!r}")
        if (fato.documento, fato.identidade) not in identidades:
            raise ValueError(
                f"Fato {fato.medida!r} aponta para a identidade {fato.identidade!r}, "
                f"que não está registrada no documento {fato.documento[:8]}."
            )
    for vinculo in registros.vinculos:
        for sha256 in (vinculo.documento_a, vinculo.documento_b):
            _exigir_documento(sha256, documentos, f"vínculo {vinculo.operacao!r}")


def _exigir_documento(
    sha256: str, documentos: Mapping[str, Documento], quem: str
) -> None:
    if sha256 not in documentos:
        raise ValueError(
            f"{quem} aponta para o documento {sha256[:8]}, que não está nos registros: "
            "linha sem prova não entra."
        )


def _linha(tabela: str, registro: object) -> dict[str, object]:
    return {nome: getattr(registro, nome) for nome, _ in _CAMPOS[tabela]}


def _carimbos(documento: Documento, agora: datetime) -> dict[str, object]:
    return {
        "consta": True,
        "disponivel_em": documento.disponivel_em,
        "visto_em": agora,
        "origem_sha256": documento.sha256,
        "origem_coletada_em": documento.coletado_em,
    }


def _ultimo_publico(vinculo: Vinculo, documentos: Mapping[str, Documento]) -> Documento:
    """O documento que ficou público por último: só então o vínculo entre os dois é conhecido."""
    dois = (documentos[vinculo.documento_a], documentos[vinculo.documento_b])
    return max(dois, key=lambda d: (d.disponivel_em, d.coletado_em))


def gabarito() -> pd.DataFrame:
    """Os fatos de aceite congelados (`conferidas/fatos_documentais_gabarito.csv`): cada um com o
    documento (SHA-256), a página ou a célula, a data-base e o dia da conferência. Tudo como texto, para
    que vazio e "0.00" continuem diferentes; `valor` está em reais (`BRL`), em pontos percentuais ao ano
    (`pp_aa`) ou é uma data (`data`), como diz a coluna `unidade`. Conflitos ficam nas duas linhas."""
    return pd.read_csv(CAMINHO_DO_GABARITO, sep=";", dtype=str, keep_default_na=False)
