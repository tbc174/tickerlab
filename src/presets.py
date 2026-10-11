"""Presets e o resolvedor de parâmetros do TickerLab Research (PRD v2, seções 9.1, 9.3 a 9.5).

Um **preset** é um conjunto de valores para alguns parâmetros do catálogo (`src/parametros.py`),
válido num **escopo**. Valores de escopos mais específicos vencem os mais gerais:

    sistema  <  global  <  watchlist  <  ativo  <  simulação

O resolvedor junta tudo e devolve, para cada parâmetro, o valor efetivo **e de onde ele veio**
(para a tela mostrar a origem e o botão "Restaurar padrão"). As regras entre parâmetros (média
rápida < lenta, pesos = 100%) são conferidas no conjunto final, porque um valor válido sozinho pode
ficar inválido ao se combinar com outro escopo.

Presets nunca são alterados: cada mudança cria uma nova versão (`com_valores`, `sem`). Assim, um
resultado salvo com a versão 3 continua reprodutível mesmo depois da versão 4. A `assinatura` (hash dos
valores) identifica exatamente o conjunto usado num cálculo.

Os presets prontos são **modos de leitura**, não perfis de risco nem recomendação.
"""

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.dados import normalizar_ticker
from src.parametros import (
    CATALOGO,
    ParametroInvalidoError,
    Valor,
    padroes_do_sistema,
    problemas_de_combinacao,
    validar_valores,
)

SISTEMA = "sistema"
GLOBAL = "global"
WATCHLIST = "watchlist"
ATIVO = "ativo"
SIMULACAO = "simulacao"
ESCOPOS = (
    SISTEMA,
    GLOBAL,
    WATCHLIST,
    ATIVO,
    SIMULACAO,
)  # do mais geral ao mais específico
NOMES_DOS_ESCOPOS = {
    SISTEMA: "Padrão do sistema",
    GLOBAL: "Seu padrão",
    WATCHLIST: "Da watchlist",
    ATIVO: "Do ativo",
    SIMULACAO: "Desta simulação",
}
Escopo = Literal["global", "watchlist", "ativo", "simulacao"]


class CombinacaoInvalidaError(ParametroInvalidoError):
    """Os valores são válidos um a um, mas não juntos (ex.: média rápida maior que a lenta)."""

    def __init__(self, problemas: list[str]) -> None:
        super().__init__(" ".join(problemas))
        self.problemas = problemas


def _assinatura(valores: Mapping[str, Valor]) -> str:
    texto = json.dumps(
        {k: list(v) if isinstance(v, tuple) else v for k, v in sorted(valores.items())},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()[:16]


class Preset(BaseModel):
    """Valores de alguns parâmetros num escopo. Imutável: mudar cria uma versão nova."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    escopo: Escopo
    alvo: str | None = (
        None  # nome da watchlist ou ticker; vazio nos escopos global e simulação
    )
    nome: str = Field(default="", max_length=80)
    versao: int = Field(default=1, ge=1)
    parametros: dict[str, Valor] = Field(default_factory=dict)

    @field_validator("parametros", mode="before")
    @classmethod
    def _validar_parametros(cls, valores: object) -> dict[str, Valor]:
        if not isinstance(valores, Mapping):
            # ValueError (não TypeError): é o que o Pydantic converte em erro de validação
            raise ValueError("os parâmetros precisam ser um dicionário")  # noqa: TRY004
        try:
            return validar_valores(valores)
        except ParametroInvalidoError as erro:
            raise ValueError(str(erro)) from erro

    @model_validator(mode="before")
    @classmethod
    def _normalizar_ticker(cls, dados: object) -> object:
        if (
            isinstance(dados, Mapping)
            and dados.get("escopo") == ATIVO
            and dados.get("alvo")
        ):
            return {**dados, "alvo": normalizar_ticker(str(dados["alvo"]))}
        return dados

    @model_validator(mode="after")
    def _conferir_alvo(self) -> "Preset":
        precisa_de_alvo = self.escopo in (WATCHLIST, ATIVO)
        if precisa_de_alvo and not (self.alvo or "").strip():
            raise ValueError(
                f"um preset de {self.escopo} precisa dizer a qual se aplica"
            )
        if not precisa_de_alvo and self.alvo:
            raise ValueError(f"um preset {self.escopo} não tem alvo")
        return self

    @property
    def assinatura(self) -> str:
        return _assinatura(self.parametros)

    def com_valores(self, valores: Mapping[str, Valor]) -> "Preset":
        """Uma versão nova com estes valores trocados (chaves do catálogo, "dominio.nome")."""
        return self.model_copy(
            update={
                "versao": self.versao + 1,
                "parametros": validar_valores({**self.parametros, **valores}),
            }
        )

    def sem(self, chave: str) -> "Preset":
        """ "Restaurar padrão" de um parâmetro neste escopo: o valor volta a vir de um escopo
        mais geral (ou do sistema). Também cria uma versão nova."""
        if chave not in CATALOGO:
            raise ParametroInvalidoError(f"Parâmetro desconhecido: {chave}.")
        restantes = {k: v for k, v in self.parametros.items() if k != chave}
        return self.model_copy(
            update={"versao": self.versao + 1, "parametros": restantes}
        )


@dataclass(frozen=True)
class ValorEfetivo:
    valor: Valor
    origem: str  # um dos ESCOPOS
    versao: int | None  # versão do preset de onde veio (None: padrão do sistema)

    @property
    def nome_da_origem(self) -> str:
        return NOMES_DOS_ESCOPOS[self.origem]


@dataclass(frozen=True)
class Diferenca:
    chave: str
    valor_a: Valor
    valor_b: Valor
    origem_a: str
    origem_b: str


@dataclass(frozen=True)
class Resolucao:
    """O valor efetivo de cada parâmetro do catálogo e de onde ele veio."""

    efetivos: dict[str, ValorEfetivo]

    def __getitem__(self, chave: str) -> Valor:
        return self.efetivos[chave].valor

    def valores(self, dominio: str | None = None) -> dict[str, Valor]:
        return {
            k: e.valor
            for k, e in self.efetivos.items()
            if dominio is None or k.startswith(dominio + ".")
        }

    def origem(self, chave: str) -> str:
        return self.efetivos[chave].origem

    def personalizados(self) -> dict[str, ValorEfetivo]:
        """Só o que não é o padrão do sistema (o que a tela destaca)."""
        return {k: e for k, e in self.efetivos.items() if e.origem != SISTEMA}

    @property
    def assinatura(self) -> str:
        """Identifica o conjunto exato de valores efetivos (vai junto de cada resultado)."""
        return _assinatura(self.valores())

    def comparar(self, outra: "Resolucao") -> list[Diferenca]:
        """O que muda entre duas configurações (A × B), na ordem do catálogo."""
        return [
            Diferenca(k, self[k], outra[k], self.origem(k), outra.origem(k))
            for k in CATALOGO
            if self[k] != outra[k]
        ]


def _unico(presets: list[Preset], escopo: str, alvo: str | None) -> Preset | None:
    candidatos = [p for p in presets if p.escopo == escopo and p.alvo == alvo]
    if len(candidatos) > 1:
        raise ParametroInvalidoError(
            f"Há {len(candidatos)} presets no escopo {escopo}"
            + (f" para {alvo}" if alvo else "")
            + "; só um pode valer."
        )
    return candidatos[0] if candidatos else None


def resolver(
    presets: Iterable[Preset],
    watchlist: str | None = None,
    ticker: str | None = None,
    simulacao: Mapping[str, Valor] | None = None,
) -> Resolucao:
    """Junta padrão do sistema < global < watchlist < ativo < simulação e confere as regras.

    Só entram o preset da `watchlist` e o do `ticker` pedidos; presets de outras watchlists e
    outros ativos são ignorados (uma carteira não vaza para outra). `simulacao` são valores
    temporários, que não viram preset.
    """
    lista = list(presets)
    efetivos = {
        k: ValorEfetivo(v, SISTEMA, None) for k, v in padroes_do_sistema().items()
    }
    camadas = [
        _unico(lista, GLOBAL, None),
        _unico(lista, WATCHLIST, watchlist) if watchlist else None,
        _unico(lista, ATIVO, normalizar_ticker(ticker)) if ticker else None,
    ]
    for preset in camadas:
        if preset is not None:
            for chave, valor in preset.parametros.items():
                efetivos[chave] = ValorEfetivo(valor, preset.escopo, preset.versao)
    if simulacao:
        for chave, valor in validar_valores(simulacao).items():
            efetivos[chave] = ValorEfetivo(valor, SIMULACAO, None)
    problemas = problemas_de_combinacao({k: e.valor for k, e in efetivos.items()})
    if problemas:
        raise CombinacaoInvalidaError(problemas)
    return Resolucao(efetivos)


def substituir(atuais: Iterable[Preset], novo: Preset) -> list[Preset]:
    """A lista de presets com `novo` no lugar do preset do mesmo escopo e alvo."""
    outros = [
        p for p in atuais if not (p.escopo == novo.escopo and p.alvo == novo.alvo)
    ]
    return [*outros, novo] if novo.parametros else outros


def conferir_ao_salvar(atuais: Iterable[Preset], novo: Preset) -> None:
    """Recusa um preset que quebra as regras no conjunto final.

    Confere o próprio escopo e, quando o novo é o padrão do usuário (global), também cada ativo
    com parâmetros próprios, que herda esse padrão. Levanta `CombinacaoInvalidaError`.
    """
    lista = list(atuais)
    juntos = substituir(lista, novo)
    if novo.escopo == ATIVO:
        tickers: list[str | None] = [novo.alvo]
    else:
        tickers = [None, *(p.alvo for p in lista if p.escopo == ATIVO and p.alvo)]
    for ticker in tickers:
        try:
            resolver(juntos, ticker=ticker)
        except CombinacaoInvalidaError as erro:
            if ticker and novo.escopo != ATIVO:
                raise CombinacaoInvalidaError(
                    [f"{problema} (no {ticker}, que tem parâmetros próprios)"
                     for problema in erro.problemas]
                ) from erro  # fmt: skip
            raise


# --- presets prontos (PRD 9.3): modos de leitura, todos editáveis ----------------------------
@dataclass(frozen=True)
class PresetPronto:
    chave: str
    nome: str
    enfatiza: str
    parametros: dict[str, Valor]

    def como_preset(self) -> Preset:
        return Preset(escopo=GLOBAL, nome=self.nome, parametros=self.parametros)


def _editorial(
    eventos: int, risco: int, fundamentos: int, tecnica: int
) -> dict[str, int]:
    return {
        "editorial.eventos": eventos,
        "editorial.risco": risco,
        "editorial.fundamentos": fundamentos,
        "editorial.tecnica": tecnica,
    }


PRESETS_PRONTOS: dict[str, PresetPronto] = {
    p.chave: p
    for p in (
        PresetPronto(
            "visao_equilibrada",
            "Visão equilibrada",
            "Eventos, risco, fundamentos e um resumo técnico.",
            {**_editorial(35, 25, 25, 15), "newsletter.cadencia": "semanal"},
        ),
        PresetPronto(
            "longo_prazo",
            "Longo prazo",
            "Qualidade, endividamento, caixa, comunicados ao mercado e valuation.",
            {
                **_editorial(35, 20, 45, 0),
                "fundamentalista.anos": 5,
                "tecnica.periodicidade": "semanal",
                "newsletter.temas": (
                    "resultados",
                    "eventos",
                    "valuation",
                    "fundamentos",
                ),
            },
        ),
        PresetPronto(
            "trader_quantitativo",
            "Leitura quantitativa",
            "Tendência, volatilidade e regime, com avisos só quando um gatilho acontece.",
            {
                **_editorial(20, 30, 10, 40),
                "tecnica.media_rapida": 20,
                "tecnica.media_lenta": 50,
                "tecnica.rsi_periodo": 14,
                "quant.janela_volatilidade": 63,
                "newsletter.cadencia": "gatilhos",
                "newsletter.temas": ("risco", "tecnica"),
            },
        ),
        PresetPronto(
            "renda_e_proventos",
            "Renda e proventos",
            "Proventos anunciados e a sustentabilidade do fluxo de caixa.",
            {
                **_editorial(40, 20, 40, 0),
                "fundamentalista.janela_proventos": 24,
                "newsletter.temas": ("resultados", "proventos", "fundamentos"),
            },
        ),
        PresetPronto(
            "monitoramento_de_risco",
            "Monitoramento de risco",
            "Concentração, quedas, correlações e eventos que mexem com o risco.",
            {
                **_editorial(30, 50, 10, 10),
                "quant.janela_correlacao": 120,
                "quant.var_confianca": 95,
                "newsletter.temas": ("risco", "eventos"),
            },
        ),
    )
}
