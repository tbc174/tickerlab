"""Features de crédito das demonstrações, como eram num dia (B-30; protótipo C, parte 1).

Cada feature é um fato com data e fonte: alavancagem, cobertura de juros, liquidez e crescimento da
receita, calculados pelas mesmas funções da ficha (`src/fundamentos.py`) e dos insumos da capacidade
de endividamento (`src/divida/capacidade.py`), sobre as demonstrações que a CVM **já tinha recebido**
no dia da análise. A feature vale a partir de `disponivel_em` (o dia em que o documento mais novo que
ela usa ficou público), nunca a partir do fim do período.

O que falta fica "não observado" (`valor` None, com o motivo); nada é estimado. Nada aqui é nota,
score, semáforo nem opinião de crédito: isso é o B-31, que espera parecer. Fórmulas, fontes e
defasagens no dicionário (`src/credito/dicionario.py`). Tipos simples, sem Streamlit.
"""

from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from datetime import date

import sqlalchemy as sa

from base import cnpj as cnpj_
from src import fundamentos as fu
from src.banco.demonstracoes import DadosDaEmpresa, dados_da_empresa
from src.credito.dicionario import DICIONARIO, VERSAO_DAS_FEATURES
from src.divida import capacidade as ca
from src.rastro import DocumentoUsado, Rastro, datas_em_texto
from src.relatorio_empresa import FONTE_DA_CVM, documentos_usados

CRESCIMENTO = {"crescimento_da_receita_1_ano": 1, "crescimento_da_receita_5_anos": 5}
SEM_A_CONTA = "A conta não aparece nas demonstrações públicas no dia."
DENOMINADOR_NAO_POSITIVO = (
    "{nome} negativo ou zero no período: a razão não tem sentido."
)
REAPRESENTADO = (
    "Reapresentado depois do dia, sem a versão que era pública nele: {documentos}."
)
LIMITES = (
    (
        "Cada feature é um fato com data e fonte, como era no dia da análise: só entra o documento "
        "que a CVM já tinha recebido naquele dia."
    ),
    "O que falta fica não observado, com o motivo; nada é estimado nem preenchido.",
    (
        "Nada aqui é nota, score, semáforo nem opinião de crédito, e nada é recomendação de "
        "investimento: o uso em modelo de crédito (B-31) espera parecer jurídico."
    ),
    "Uso interno da pesquisa: estas features não aparecem no app.",
)


class OlhouOFuturoError(ValueError):
    """Uma feature usa um número que ainda não era público no dia da análise."""


@dataclass(frozen=True)
class Feature:
    """Um fato de crédito: valor (ou não observado), de quando é, desde quando é público e de onde vem."""

    chave: str  # uma chave do DICIONARIO
    valor: float | str | None  # None: não observado (ver `motivo`)
    periodo: str  # "12 meses até 30/06/2026; balanço de 30/06/2026"
    rastro: Rastro
    disponivel_em: date | None = None  # o dia em que o insumo mais novo ficou público
    motivo: str = ""


@dataclass(frozen=True)
class FeaturesDeCredito:
    """As features de um emissor, como eram em `data_da_analise`."""

    cnpj: str | None
    data_da_analise: date
    features: tuple[Feature, ...]
    limites: tuple[str, ...] = LIMITES

    def __getitem__(self, chave: str) -> Feature:
        return next(f for f in self.features if f.chave == chave)

    def valores(self) -> dict[str, float | str | None]:
        """Chave → valor (None: não observado), na ordem do dicionário."""
        return {f.chave: f.valor for f in self.features}

    def como_dict(self) -> dict:
        """Para a API: datas em texto ISO."""
        return {k: datas_em_texto(v) for k, v in asdict(self).items()}


def conferir_ponto_no_tempo(features: Iterable[Feature], data_da_analise: date) -> None:
    """Derruba (`OlhouOFuturoError`) a feature que usa algo publicado depois do dia da análise.

    Confere a data da feature e a de cada documento do rastro; e um número observado sem data não
    passa (sem data não há como provar que já era público)."""
    for feature in features:
        dias = [feature.disponivel_em] + [
            d.publicado_em for d in feature.rastro.documentos
        ]
        futuros = [d for d in dias if d is not None and d > data_da_analise]
        if futuros:
            raise OlhouOFuturoError(
                f"{feature.chave}: usa o publicado em {max(futuros):%d/%m/%Y}, depois de "
                f"{data_da_analise:%d/%m/%Y}"
            )
        if feature.valor is not None and feature.disponivel_em is None:
            raise OlhouOFuturoError(
                f"{feature.chave}: número observado sem data de publicação"
            )


# --- as contas ------------------------------------------------------------------------------------
def _documentos(
    dados: DadosDaEmpresa, usados: Iterable[tuple[str, date]]
) -> list[DocumentoUsado]:
    usados_ = set(usados)
    documentos = dados.documentos
    if documentos.empty:
        return []
    escolhidos = documentos[
        [
            (d, r) in usados_
            for d, r in zip(
                documentos["documento"], documentos["referencia"], strict=True
            )
        ]
    ]
    return list(documentos_usados(escolhidos))


def _juntar(*listas: Sequence[DocumentoUsado]) -> list[DocumentoUsado]:
    vistos: dict[str, DocumentoUsado] = {}
    for documento in (d for lista in listas for d in lista):
        vistos.setdefault(documento.nome, documento)
    return list(vistos.values())


def nova_feature(
    chave: str,
    valor: float | str | None,
    periodo: str,
    documentos: Sequence[DocumentoUsado],
    motivo: str = "",
    fonte: str = FONTE_DA_CVM,
) -> Feature:
    """A feature com o rastro (fórmula do dicionário, `disponivel_em` do documento mais novo); com
    motivo, ou sem valor, fica não observada."""
    if valor is None and not motivo:
        motivo = SEM_A_CONTA
    rastro = Rastro.dos_documentos(
        DICIONARIO[chave].formula, VERSAO_DAS_FEATURES, fonte, documentos
    )
    return Feature(
        chave, None if motivo else valor, periodo, rastro, rastro.publicado_em, motivo
    )


def _razao(
    chave: str,
    numerador: float | None,
    denominador: float | None,
    nome_do_denominador: str,
    periodo: str,
    documentos: Sequence[DocumentoUsado],
    motivo: str = "",
) -> Feature:
    """numerador ÷ denominador; falta um dos dois ou o denominador não é positivo: não observado."""
    if (
        not motivo
        and numerador is not None
        and denominador is not None
        and denominador <= 0
    ):
        motivo = DENOMINADOR_NAO_POSITIVO.format(nome=nome_do_denominador)
    valor = (
        None
        if numerador is None or denominador is None or motivo
        else numerador / denominador
    )
    return nova_feature(chave, valor, periodo, documentos, motivo)


def _de_um_insumo(chave: str, insumo: ca.Insumo, motivo: str) -> Feature:
    """Não observado porque o insumo não foi observado (o motivo dele vem junto)."""
    texto = motivo or f"{insumo.nome}: {insumo.motivo or SEM_A_CONTA}"
    return nova_feature(chave, None, insumo.periodo, insumo.rastro.documentos, texto)


def _alavancagem_e_cobertura(
    insumos: ca.Insumos, pl: fu.Indicador, motivo: str
) -> list[Feature]:
    ebitda, ebit, despesa, liquida = (
        insumos.ebitda, insumos.ebit, insumos.despesa_financeira, insumos.divida_liquida
    )  # fmt: skip
    doze_e_balanco = f"{ebitda.periodo}; {liquida.periodo}"
    pares = (
        ("divida_liquida_sobre_ebitda", liquida, ebitda, "EBITDA", doze_e_balanco),
        (
            "cobertura_de_juros_ebitda",
            ebitda,
            despesa,
            "Despesa financeira",
            ebitda.periodo,
        ),
        ("cobertura_de_juros_ebit", ebit, despesa, "Despesa financeira", ebit.periodo),
    )
    features = []
    for chave, cima, baixo, nome, periodo in pares:
        faltando = next((i for i in (cima, baixo) if i.valor is None), None)
        if faltando is not None:
            features.append(_de_um_insumo(chave, faltando, motivo))
            continue
        documentos = _juntar(cima.rastro.documentos, baixo.rastro.documentos)
        features.append(
            _razao(chave, cima.valor, baixo.valor, nome, periodo, documentos, motivo)
        )
    do_balanco = list(liquida.rastro.documentos)
    features.insert(1, nova_feature(
        "divida_liquida_sobre_pl", pl.valor, pl.base, do_balanco, motivo or pl.motivo
    ))  # fmt: skip
    return features


def _liquidez(dados: DadosDaEmpresa, insumos: ca.Insumos, motivo: str) -> list[Feature]:
    saldo, dia, documento = fu.balanco_mais_recente(dados.contas)
    periodo = f"balanço de {dia:%d/%m/%Y}" if dia else ""
    documentos = _documentos(dados, [(documento, dia)] if dia else [])
    caixa = insumos.caixa
    return [
        _razao(
            "liquidez_corrente", saldo.get("ativo_circulante"), saldo.get("passivo_circulante"),
            "Passivo circulante", periodo, documentos, motivo,
        ),
        _razao(
            "caixa_sobre_divida_de_curto_prazo", caixa.valor, saldo.get("divida_cp"),
            "Dívida de curto prazo", periodo, documentos, motivo or caixa.motivo,
        ),
    ]  # fmt: skip


def _dfps_dos_anos(dados: DadosDaEmpresa, anos: Iterable[int]) -> list[DocumentoUsado]:
    """Os DFPs dos exercícios pedidos (o ano é o da data de referência, como em `fu.anuais`)."""
    anos_ = set(anos)
    contas = dados.contas
    if contas.empty:
        return []
    dfps = contas.loc[contas["documento"] == "DFP", "referencia"].unique()
    return _documentos(dados, [("DFP", r) for r in dfps if r.year in anos_])


def _crescimento(dados: DadosDaEmpresa, motivo: str) -> list[Feature]:
    """O crescimento composto da receita, nos horizontes de `CRESCIMENTO`, pela conta da ficha."""
    receita = fu.anuais(dados.contas).get("receita")
    anos_com_receita = [] if receita is None else list(receita.dropna().index)
    features = []
    for chave, anos in CRESCIMENTO.items():
        indicador = fu.calcular(dados, preco=None, anos=anos)["crescimento_receita"]
        # a conta usa só o primeiro e o último ano do horizonte
        usados = (
            anos_com_receita[-(anos + 1) :: anos]
            if len(anos_com_receita) > anos
            else []
        )
        features.append(nova_feature(
            chave, indicador.valor, indicador.base, _dfps_dos_anos(dados, usados),
            motivo or indicador.motivo,
        ))  # fmt: skip
    return features


def _reapresentados(
    cortadas: ca.DemonstracoesComoEram, documento: str | None = None
) -> str:
    """O motivo comum quando um documento do período foi reapresentado depois do dia."""
    sem = [
        s
        for s in cortadas.sem_a_versao_do_dia
        if documento is None or s.startswith(documento)
    ]
    return REAPRESENTADO.format(documentos=", ".join(sem)) if sem else ""


def features_das_demonstracoes(
    dados: DadosDaEmpresa, data_da_analise: date, cnpj: str | None = None
) -> FeaturesDeCredito:
    """As features das demonstrações (ordem do dicionário), com o que era público no dia."""
    cortadas = ca.demonstracoes_como_eram(dados, data_da_analise)
    publicas = cortadas.dados
    ficha = fu.calcular(publicas, preco=None)
    motivo = _reapresentados(cortadas) or (
        fu.NAO_SE_APLICA_A_FINANCEIRAS if ficha.financeira else ""
    )
    insumos = ca.insumos_das_demonstracoes(dados, data_da_analise)
    features = [
        *_alavancagem_e_cobertura(insumos, ficha["divida_sobre_pl"], motivo),
        *_liquidez(publicas, insumos, motivo),
        *_crescimento(publicas, _reapresentados(cortadas, "DFP")),
    ]
    return FeaturesDeCredito(cnpj, data_da_analise, tuple(features))


def features_do_emissor(
    conexao: sa.Connection, cnpj: str, data_da_analise: date
) -> FeaturesDeCredito:
    """As features de uma companhia aberta, como eram em `data_da_analise`."""
    cnpj_normal = cnpj_.normalizar_cnpj(cnpj)
    if cnpj_normal is None:
        raise ValueError(f"{cnpj!r} não é um CNPJ")
    dados = dados_da_empresa(conexao, cnpj_.formatar(cnpj_normal))
    return features_das_demonstracoes(dados, data_da_analise, cnpj_normal)
