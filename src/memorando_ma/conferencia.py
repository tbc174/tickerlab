"""A conferência do memorando antes de qualquer tela: a porta 1 da ADR 0100 e as regras do M&A.

Frase a frase:
- **sem fonte:** a frase sem nenhuma nota reprova (no memorando, toda frase aponta para evidência);
- **evidência:** cada nota tem de ser uma evidência do memorando, completa (`Evidencia.o_que_falta`)
  e já pública no dia do memorando (sem olhar o futuro);
- **porta 1:** números, datas e nomes só das evidências citadas, contas refeitas, nada de pessoa,
  palavra proibida nem previsão (`src/analise_escrita/porta1.py`, a mesma régua da análise escrita);
- **valor da empresa:** nada de preço-alvo, preço justo, "vale X" nem "deveria comprar ou vender".

E a estrutura: seções conhecidas, sem repetir, na ordem de `formato.SECOES` e nenhuma vazia. Os
limites (notas de método) só passam pelas regras de palavra.
"""

import re
from collections.abc import Iterator
from typing import Any

from src.analise_escrita import porta1
from src.analise_escrita.porta1 import Conferencia, Reprovacao
from src.analise_escrita.saida import Frase
from src.memorando_ma.formato import SECOES, Memorando

SEM_FONTE = "sem_fonte"
EVIDENCIA_INCOMPLETA = "evidencia_incompleta"
EVIDENCIA_FUTURA = "evidencia_futura"
VALOR_DA_EMPRESA = "valor_da_empresa"
PARTE_DOS_LIMITES = "limites"
REGRAS_DOS_LIMITES = (porta1.PALAVRA, porta1.PREVISAO, porta1.PESSOA)

# o memorando mostra a régua (o que foi pago, o que o preço supõe), nunca o valor da empresa
_VALOR_DA_EMPRESA = re.compile(
    r"\b(?:valem?|valeria|valeriam)\s+(?:r\$|us\$|\d|cerca|mais|menos|ate|entre)"
    r"|\bvalor (?:justo|intrinseco)\b"
    r"|\b(?:deve|devem|deveria|deveriam|vale a pena)\s+(?:comprar|vender)\b"
    r"|\bhora de (?:comprar|vender)\b"
    r"|\b(?:sugerimos|sugere-se|indicamos)\b"
)


def entrada_das_evidencias(memorando: Memorando) -> dict[str, Any]:
    """As evidências no formato da entrada que a porta 1 lê (uma linha por evidência)."""
    return {
        "corte": memorando.como_era_em.isoformat(),
        "empresa": memorando.empresa,
        "linhas": [e.como_linha() for e in memorando.evidencias],
    }


def _falhas_das_notas(frase: Frase, memorando: Memorando) -> Iterator[tuple[str, str]]:
    if not frase.notas:
        yield SEM_FONTE, "frase sem evidência"
    for nota in frase.notas:
        evidencia = memorando.evidencia(nota)
        if evidencia is None:
            yield porta1.ID_INEXISTENTE, nota
            continue
        falta = evidencia.o_que_falta()
        if falta:
            yield EVIDENCIA_INCOMPLETA, f"{nota} sem {', '.join(falta)}"
        publicado = evidencia.publicado_em
        if publicado is not None and publicado > memorando.como_era_em:
            yield EVIDENCIA_FUTURA, f"{nota} pública em {publicado:%d/%m/%Y}"


def _falhas_de_valor(texto: str) -> Iterator[tuple[str, str]]:
    achados = _VALOR_DA_EMPRESA.findall(porta1.normalizar(texto))
    if achados:
        yield VALOR_DA_EMPRESA, ", ".join(achados)


def _conferir_frases(memorando: Memorando) -> Iterator[Reprovacao]:
    ficha = porta1.ler_ficha(entrada_das_evidencias(memorando))
    for secao in memorando.secoes:
        for posicao, frase in enumerate(secao.frases):
            falhas = [
                *_falhas_das_notas(frase, memorando),
                *porta1.falhas_da_frase(frase, ficha),
                *_falhas_de_valor(frase.texto),
            ]
            for regra, detalhe in falhas:
                yield Reprovacao(
                    secao.chave, None, posicao, regra, f"{frase.texto} [{detalhe}]"
                )


def _conferir_estrutura(memorando: Memorando) -> Iterator[Reprovacao]:
    ordem = list(SECOES)
    vistas: list[str] = []
    for secao in memorando.secoes:
        if secao.chave not in SECOES:
            detalhe = "seção desconhecida"
        elif secao.chave in vistas:
            detalhe = "seção repetida"
        elif vistas and ordem.index(secao.chave) < ordem.index(vistas[-1]):
            detalhe = "seção fora de ordem"
        elif not secao.frases:
            detalhe = "seção vazia"
        else:
            vistas.append(secao.chave)
            continue
        yield Reprovacao(secao.chave, None, None, porta1.ESTRUTURA, detalhe)


def _conferir_limites(memorando: Memorando) -> Iterator[Reprovacao]:
    """Nota de método não cita evidência: só as regras de palavra, de previsão e de valor valem."""
    sem_linhas = porta1.ler_ficha(
        {"corte": memorando.como_era_em.isoformat(), "linhas": []}
    )
    for posicao, texto in enumerate(memorando.limites):
        da_porta = porta1.falhas_da_frase(Frase(texto), sem_linhas)
        falhas = [
            *(f for f in da_porta if f[0] in REGRAS_DOS_LIMITES),
            *_falhas_de_valor(texto),
        ]
        for regra, detalhe in falhas:
            yield Reprovacao(
                PARTE_DOS_LIMITES, None, posicao, regra, f"{texto} [{detalhe}]"
            )


def conferir(memorando: Memorando) -> Conferencia:
    """Todas as reprovações do memorando (nenhuma: pode ir para a tela)."""
    return Conferencia(
        (
            *_conferir_estrutura(memorando),
            *_conferir_frases(memorando),
            *_conferir_limites(memorando),
        )
    )


class MemorandoReprovadoError(ValueError):
    """O memorando não passou na conferência: nada dele vai para a tela."""


def para_mostrar(memorando: Memorando) -> Memorando:
    """O memorando conferido; `MemorandoReprovadoError` com a primeira reprovação se não passou."""
    conferencia = conferir(memorando)
    if not conferencia.aprovada:
        primeira = conferencia.reprovacoes[0]
        raise MemorandoReprovadoError(
            f"{primeira.parte}, frase {primeira.frase}: {primeira.regra} ({primeira.detalhe})"
        )
    return memorando
