"""Prontidão de cada tabela para a API externa (ADR 0108, Emenda 1, D10).

A API externa só serve tabela **pronta**: que passou nas exigências 6 (conferência cruzada), 7
(qualidade automática) e 8 (dicionário) da ADR 0027, na régua de vender (Emenda 2 da 0027). Este
módulo é a fonte única desse registro, escrito à mão: por tabela, a data e a prova de cada exigência e
a versão maior do contrato que foi conferida. O portão (`src/portao_externo.py`) nega o que não
estiver aqui; o catálogo (`base/contrato.py`) mostra o registro de cada tabela pronta.

Quem grava (D10.5): **tirar** uma tabela daqui é nível 3 (o placar ficou vermelho, achou-se um erro);
**dar** prontidão é nível 2 da mesa Dados, só com as três provas e, na da 8, a data e as palavras da
revisão do dicionário. A prova é um identificador curto, sem caminho, IP, endereço ou e-mail: o
catálogo também vai para o site público.
"""

import os
import re
from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from functools import cache
from typing import NamedTuple

# D10.4: o placar (linha 427) renova a 6 e a 7; prova mais velha que isto já não vale
PRAZO_DA_PROVA = timedelta(days=90)
# o que não pode aparecer numa prova publicada: caminho, endereço, IPv4 e e-mail
_FORA_DA_PROVA = re.compile(r"[/\\@]|https?:|\b\d{1,3}(?:\.\d{1,3}){3}\b")


class Prova(NamedTuple):
    """Uma exigência cumprida: em que dia e o que prova. `independencia` só na 6: por que as duas
    fontes são independentes, ou qual é o par "mesmo documento, outro canal" (D10.6)."""

    data: date
    prova: str
    independencia: str = ""


class Prontidao(NamedTuple):
    """As três provas de uma tabela e a versão maior do contrato conferida. Vazio = falta."""

    versao_maior: int
    cruzada: Prova | None  # exigência 6
    qualidade: Prova | None  # exigência 7
    dicionario: Prova | None  # exigência 8


class Falta(StrEnum):
    """Por que a tabela não está pronta (os mesmos valores do `Motivo` do portão, para o log)."""

    SEM_TABELA = "sem_tabela"  # a linha de direito não diz de que tabela o campo sai
    SEM_PRONTIDAO = (
        "sem_prontidao"  # sem registro, ou alguma exigência sem data e prova
    )
    PRONTIDAO_VENCIDA = "prontidao_vencida"  # prova da 6 ou da 7 com mais de 90 dias
    CONTRATO_MUDOU = "contrato_mudou"  # versão maior diferente da conferida


# Nenhuma tabela está pronta ainda: falta a prova da 6, que vem do placar (linha 427, API A2b).
PRONTIDAO: dict[str, Prontidao] = {}


def versao_maior(versao: str) -> int:
    """O primeiro número de "maior.menor.correção"."""
    return int(versao.split(".", 1)[0])


@cache
def versoes_maiores() -> Mapping[str, int]:
    """A versão maior de hoje de cada tabela do dicionário (lida uma vez por processo)."""
    from base.dicionario import (
        TABELAS,
    )  # o dicionário é grande: só quando o portão precisa

    return {
        nome: versao_maior(tabela.versao_do_contrato)
        for nome, tabela in TABELAS.items()
    }


def prova_publicavel(texto: str) -> bool:
    """A prova pode ir para o catálogo público: não é vazia e não tem caminho, IP ou e-mail."""
    return bool(texto.strip()) and _FORA_DA_PROVA.search(texto) is None


def _valida(prova: Prova | None, hoje: date) -> bool:
    return prova is not None and bool(prova.prova.strip()) and prova.data <= hoje


def _vencida(prova: Prova, hoje: date) -> bool:
    return hoje - prova.data > PRAZO_DA_PROVA


def _falta_da_tabela(
    registro: Prontidao | None, versao_de_hoje: int | None, hoje: date
) -> Falta | None:
    if registro is None:
        return Falta.SEM_PRONTIDAO
    provas = (registro.cruzada, registro.qualidade, registro.dicionario)
    if not all(_valida(prova, hoje) for prova in provas):
        return Falta.SEM_PRONTIDAO
    cruzada, qualidade = registro.cruzada, registro.qualidade
    assert cruzada is not None and qualidade is not None  # conferido em `_valida`
    if not cruzada.independencia.strip():
        return Falta.SEM_PRONTIDAO
    if versao_de_hoje != registro.versao_maior:
        return Falta.CONTRATO_MUDOU
    if _vencida(cruzada, hoje) or _vencida(qualidade, hoje):
        return Falta.PRONTIDAO_VENCIDA
    return None


def negacao_da_prontidao(
    tabelas: Iterable[str],
    registro: Mapping[str, Prontidao],
    versoes: Mapping[str, int],
    hoje: date,
) -> Falta | None:
    """Por que estas tabelas não podem servir hoje, ou None se **todas** estão prontas (campo
    calculado de duas tabelas exige as duas). Sem tabela nenhuma, nega."""
    tabelas = tuple(tabelas)
    if not tabelas:
        return Falta.SEM_TABELA
    for tabela in tabelas:
        falta = _falta_da_tabela(registro.get(tabela), versoes.get(tabela), hoje)
        if falta is not None:
            return falta
    return None


# Ensaio local (linha 800): no PC, com `TICKERLAB_AMBIENTE=ensaio`, toda tabela do dicionário vale como pronta,
# para a apresentação responder sem o VPS. Qualquer outro valor, inclusive vazio, e "producao", deixa o registro
# de verdade intacto (falha fechada: só o valor exato liga).
VARIAVEL_DO_AMBIENTE = "TICKERLAB_AMBIENTE"
AMBIENTE_DE_ENSAIO = "ensaio"
PROVA_DE_ENSAIO = "ensaio-local"
CABECALHO_DO_ENSAIO = "X-TickerLab-Ensaio"
AVISO_DO_ENSAIO = "ensaio local: dado sem prontidao conferida"


def em_ensaio(ambiente: Mapping[str, str] | None = None) -> bool:
    """O processo roda no ensaio local (`TICKERLAB_AMBIENTE=ensaio`, valor exato)?"""
    texto = (ambiente if ambiente is not None else os.environ).get(
        VARIAVEL_DO_AMBIENTE, ""
    )
    return texto.strip().lower() == AMBIENTE_DE_ENSAIO


def registro_vigente(
    ambiente: Mapping[str, str] | None = None, hoje: date | None = None
) -> Mapping[str, Prontidao]:
    """O registro que o portão e o catálogo leem: o de verdade, ou, só no ensaio, o de verdade mais uma prova
    de ensaio (datada de ontem) nas tabelas que ainda não têm registro. Fora do ensaio devolve `PRONTIDAO`
    mesmo (o mesmo objeto)."""
    if not em_ensaio(ambiente):
        return PRONTIDAO
    # ontem (UTC): vale em qualquer fuso do Brasil, e a prova de ensaio nunca vence no dia
    dia = hoje or datetime.now(UTC).date() - timedelta(days=1)
    prova = Prova(dia, PROVA_DE_ENSAIO, PROVA_DE_ENSAIO)
    de_ensaio = {
        nome: Prontidao(versao, prova, prova, prova)
        for nome, versao in versoes_maiores().items()
    }
    return {**de_ensaio, **PRONTIDAO}
