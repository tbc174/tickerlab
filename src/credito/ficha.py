"""A ficha de crédito de um CNPJ (linha 754): os fatos da base e as regras de elegibilidade num papel.

Para quem tokeniza duplicatas, o FIDC e a securitizadora: a empresa como cedente (quem vende o
recebível) ou como sacado (quem vai pagar). A ficha junta as features da base (`features_da_base`),
os sinais da ficha (`sinais`), as das demonstrações quando a companhia é aberta e se tem os `dados`,
e as regras do papel (`elegibilidade`). Tudo como era no dia: a ficha inteira passa por
`conferir_ponto_no_tempo`. Pessoa natural (MEI, empresário individual) não tem ficha com fato nenhum
(ADR 0075), e nada aqui é nota, score, selo ou semáforo (ADR 0103): a ficha falha se aparecer.
"""

from dataclasses import asdict, dataclass
from datetime import date

from base import cnpj as cnpj_
from base.palavras_vedadas import palavras_vedadas_em
from base.porta import Porta
from src.banco.demonstracoes import DadosDaEmpresa
from src.credito import features_da_base as fb
from src.credito import sinais
from src.credito.dicionario import DA_FICHA
from src.credito.dossie import (
    CPF,
    PEDACOS_DE_NOTA,
    NotaNoDossieError,
    PessoaNoDossieError,
    _textos,
)
from src.credito.elegibilidade import ACIONA, ResultadoDaRegra, regras_de_elegibilidade
from src.credito.features import (
    Feature,
    conferir_ponto_no_tempo,
    features_das_demonstracoes,
)
from src.credito.sinais import DO_FIDC, sinais_da_ficha
from src.rastro import datas_em_texto

LIMITES_DA_FICHA = (
    (
        "Cada fato tem fonte e a data em que ficou público, como era no dia da ficha: nada publicado "
        "depois entra."
    ),
    (
        "O que a base não tem fica não observado, com o motivo; não estar numa lista só vale para as "
        "listas que a base já olhava no dia."
    ),
    (
        "As regras dizem se acionam, uma por fato, sem somar nem pesar: a ficha não é nota, score, "
        "selo nem opinião de crédito, e nada aqui é recomendação de investimento."
    ),
    "Pessoa natural (MEI, empresário individual) não tem ficha: os dados de pessoa ficam de fora.",
    "O histórico de pagamento das duplicatas, trazido pelo cedente com o consentimento, ainda não entra.",
)


@dataclass(frozen=True)
class FichaDeCredito:
    """A ficha de um CNPJ num papel, como era em `data_da_analise`."""

    cnpj: str
    papel: str
    data_da_analise: date
    fatos: tuple[Feature, ...]
    regras: tuple[ResultadoDaRegra, ...]
    limites: tuple[str, ...] = LIMITES_DA_FICHA

    def __getitem__(self, chave: str) -> Feature:
        return next(fato for fato in self.fatos if fato.chave == chave)

    def acionadas(self) -> tuple[ResultadoDaRegra, ...]:
        return tuple(regra for regra in self.regras if regra.resultado == ACIONA)

    def lacunas(self) -> dict[str, str]:
        """Fato não observado → o motivo (o que a ficha não sabe, à vista)."""
        return {fato.chave: fato.motivo for fato in self.fatos if fato.valor is None}

    def como_dict(self) -> dict:
        """Para a API: tipos simples e datas em texto ISO."""
        return {k: datas_em_texto(v) for k, v in asdict(self).items()}


def _como_pessoa(fatos: tuple[Feature, ...]) -> tuple[Feature, ...]:
    """Os mesmos fatos sem valor nem documento: a ficha de pessoa não guarda nada dela."""
    return tuple(
        fb._nao_observadas([fato.chave], fb.COMO_PESSOA, fato.rastro.fonte_id)[0]
        for fato in fatos
    )


def _conferir(ficha: FichaDeCredito) -> None:
    """A ficha não é nota (ADR 0103) nem leva CPF (ADR 0075); derruba se aparecer."""
    for chave in (
        *(fato.chave for fato in ficha.fatos),
        *(regra.chave for regra in ficha.regras),
    ):
        if PEDACOS_DE_NOTA & set(chave.lower().split("_")):
            raise NotaNoDossieError(
                f"{chave}: a ficha traz fatos e regras, não notas nem scores"
            )
    sem_os_limites = {k: v for k, v in ficha.como_dict().items() if k != "limites"}
    for texto in _textos(sem_os_limites):
        if vedadas := palavras_vedadas_em(texto):
            raise NotaNoDossieError(f"palavra vedada na ficha: {', '.join(vedadas)}")
        if CPF.search(texto):
            raise PessoaNoDossieError("há um CPF (inteiro ou mascarado) na ficha")


def ficha_de_credito(
    porta: Porta,
    cnpj: str,
    papel: str,
    data_da_analise: date,
    dados: DadosDaEmpresa | None = None,
    secao_do_cnae: str | None = None,
) -> FichaDeCredito:
    """A ficha de crédito do CNPJ no papel (`cedente` ou `sacado`), com o que era público no dia.

    `dados` são as demonstrações da companhia aberta (sem eles, a ficha fica só com a base);
    `secao_do_cnae` vai para as features do SCR, como em `features_da_base`."""
    normal = fb._cnpj(cnpj)
    raiz = normal[: cnpj_.TAMANHO_DA_RAIZ]
    das_demonstracoes = (
        features_das_demonstracoes(dados, data_da_analise, normal).features
        if dados
        else ()
    )
    fatos = (
        *das_demonstracoes,
        *fb.features_da_base(porta, normal, data_da_analise, secao_do_cnae),
        *sinais_da_ficha(porta, normal, data_da_analise),
    )
    if fb._pessoa_natural(porta, raiz, data_da_analise):
        fatos = _como_pessoa(fatos)
    conferir_ponto_no_tempo(fatos, data_da_analise)
    ficha = FichaDeCredito(
        cnpj=normal,
        papel=papel,
        data_da_analise=data_da_analise,
        fatos=fatos,
        regras=regras_de_elegibilidade(fatos, papel),
    )
    _conferir(ficha)
    return ficha


# Os fatos que `fatos_da_ficha` sabe calcular sem montar a ficha inteira: os que a API externa serve
# (`src/api_externa/conjuntos/credito.FATOS`; linha 1015).
SITUACAO_ESPECIAL = "situacao_especial_na_receita"
SITUACAO_CADASTRAL = "situacao_cadastral_na_receita"
SOZINHOS = frozenset({SITUACAO_ESPECIAL, *fb.DO_IPE, SITUACAO_CADASTRAL, *DO_FIDC})


def fatos_da_ficha(
    porta: Porta, cnpj: str, data_da_analise: date, chaves: frozenset[str]
) -> tuple[Feature, ...]:
    """Só os fatos `chaves` da ficha do CNPJ, sem calcular os outros (PGFN, SCR, listas, rating...).

    Dão o mesmo que `ficha_de_credito(...).fatos` filtrado por `chaves`, sem as demonstrações (`dados`), na
    mesma ordem, com a mesma trava de pessoa (ADR 0075), o mesmo ponto no tempo e as mesmas conferências de
    nota e CPF; só não há regras. Serve a API externa, que mostra poucos fatos e não pode pagar a ficha
    inteira no prazo da análise. Uma chave fora de `SOZINHOS` é recusada."""
    if fora := chaves - SOZINHOS:
        raise ValueError(
            f"fatos que a ficha só calcula inteira: {', '.join(sorted(fora))}"
        )
    normal = fb._cnpj(cnpj)
    raiz, formatado = normal[: cnpj_.TAMANHO_DA_RAIZ], cnpj_.formatar(normal)
    pessoa = fb._pessoa_natural(porta, raiz, data_da_analise)
    da_base: list[Feature] = []
    if SITUACAO_ESPECIAL in chaves:
        da_base.append(fb._situacao_especial(porta, raiz, data_da_analise))
    if chaves & set(fb.DO_IPE):
        da_base.extend(fb._ipe(porta, formatado, data_da_analise))
    dos_sinais = [chave for chave in DA_FICHA if chave in chaves]
    if pessoa:  # como `sinais_da_ficha`: a pessoa não tem sinal nenhum
        sinais_ = sinais._nao_observados(dos_sinais, fb.COMO_PESSOA)
    else:
        sinais_ = [
            *([sinais._situacao_cadastral(porta, raiz, data_da_analise)] if SITUACAO_CADASTRAL in chaves else []),
            *(sinais._fidc(porta, formatado, data_da_analise) if chaves & set(DO_FIDC) else []),
        ]  # fmt: skip
        sinais_.sort(key=lambda sinal: DA_FICHA.index(sinal.chave))
    fatos = tuple(fato for fato in (*da_base, *sinais_) if fato.chave in chaves)
    if pessoa:
        fatos = _como_pessoa(fatos)
    conferir_ponto_no_tempo(fatos, data_da_analise)
    _conferir(FichaDeCredito(normal, "", data_da_analise, fatos, regras=()))
    return fatos
