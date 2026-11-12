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


# --- D11 (ADR 0108, Emenda 2): prontidão de piloto, só para a organização marcada como piloto ---
#
# Separada do registro cheio: a tabela tem a exigência 7 (qualidade automática) em dia e o dicionário **escrito**
# (a 8 sem a leitura do Tiago), e a versão maior do contrato conferida. A 6 (conferência cruzada) fica dispensada,
# e por isso todo bloco servido assim leva o aviso abaixo. Dar piloto a uma tabela é nível 2 da mesa Dados com as
# duas provas; tirar é nível 3. A tabela sai daqui quando ganha a prontidão cheia.

# Texto público (D11.3): a frase de todo bloco servido pelo caminho de piloto. Um lugar só.
AVISO_DE_PILOTO = "Dado de piloto: passou na qualidade automática, mas ainda não na conferência cruzada com outra fonte."


class ProntidaoDePiloto(NamedTuple):
    """As duas provas do piloto (7 e 8 escrita) e a versão maior conferida. Vazio = falta."""

    versao_maior: int
    qualidade: Prova | None  # exigência 7, vence em `PRAZO_DA_PROVA`
    dicionario: Prova | None  # exigência 8 escrita


# As entradas são da mesa Dados (linha 784), só com as duas provas existindo e a marca de pessoa decidida:
# as cinco abaixo passaram em `scripts.conferir_sem_pessoa` (todo CNPJ dentro da `cnpj_empresas_pj`) em 12/11/2026.
PRONTIDAO_DE_PILOTO: dict[str, ProntidaoDePiloto] = {
    "carteiras_dos_fundos": ProntidaoDePiloto(
        versao_maior=1,
        qualidade=Prova(date(2026, 11, 12), "placar-qualidade-2026-11-12"),
        dicionario=Prova(date(2026, 11, 12), "dicionario-escrito-2026-11-12"),
    ),
    "demonstracoes_como_era": ProntidaoDePiloto(
        versao_maior=3,
        qualidade=Prova(date(2026, 11, 12), "placar-qualidade-2026-11-12"),
        dicionario=Prova(date(2026, 11, 12), "dicionario-escrito-2026-11-12"),
    ),
    "eventos": ProntidaoDePiloto(
        versao_maior=1,
        qualidade=Prova(date(2026, 11, 12), "placar-qualidade-2026-11-12"),
        dicionario=Prova(date(2026, 11, 12), "dicionario-escrito-2026-11-12"),
    ),
    "fca_geral": ProntidaoDePiloto(
        versao_maior=1,
        qualidade=Prova(date(2026, 11, 12), "placar-qualidade-2026-11-12"),
        dicionario=Prova(date(2026, 11, 12), "dicionario-escrito-2026-11-12"),
    ),
    "rotulos_atraso": ProntidaoDePiloto(
        versao_maior=1,
        qualidade=Prova(date(2026, 11, 12), "placar-qualidade-2026-11-12"),
        dicionario=Prova(date(2026, 11, 12), "dicionario-escrito-2026-11-12"),
    ),
}

# A marca de pessoa decidida (D11.4), pelas mesmas regras de `tests/test_porta_sem_pessoa.py`: a rede não tem
# marca por linha (a porta a filtra pelas entidades), a montagem de três tabelas já tira a pessoa, e só tabela
# com coluna de CNPJ, raiz ou CPF precisa da marca.
TABELAS_DA_REDE = frozenset({"entidades", "ligacoes", "identificadores"})
# sem pessoa por construção: a montagem nem deixa entrar o empresário individual nem o grupo 4 (linha 584)
# sem pessoa pela raiz (linha 789): as 5 últimas têm todo CNPJ dentro da cnpj_empresas_pj, medido por scripts.conferir_sem_pessoa antes de cada concessão de piloto
SEM_PESSOA_NA_MONTAGEM = frozenset(
    {
        "carteiras_dos_fundos",
        "cnpj_empresas_pj",
        "cnpj_estabelecimentos_pj",
        "demonstracoes_como_era",
        "entradas_de_socio_pj",
        "eventos",
        "fca_geral",
        "rotulos_atraso",
    }
)
COLUNA_DE_CNPJ = re.compile(r"cnpj|raiz|cpf")


def pessoa_decidida(
    nome: str, *, pessoa: bool, colunas: Iterable[str], linhas_de_pessoa: str
) -> bool:
    """A tabela não guarda pessoa e tem a marca de pessoa decidida (ou não precisa dela)?"""
    if pessoa:
        return False
    if nome in TABELAS_DA_REDE or nome in SEM_PESSOA_NA_MONTAGEM:
        return True
    if not any(COLUNA_DE_CNPJ.search(coluna) for coluna in colunas):
        return True
    return bool(linhas_de_pessoa.strip())


@cache
def tabelas_com_pessoa_decidida() -> frozenset[str]:
    """As tabelas do dicionário sem pessoa e com a marca de pessoa decidida: só estas podem sair pelo piloto.

    Fica fora a tabela marcada com pessoa e a que tem coluna de CNPJ sem `linhas_de_pessoa` nem ser da rede (o
    inventário `AINDA_SEM_A_MARCA`). `pessoa_tirada_na_rota` não basta: na dúvida, a leitura mais estreita.
    """
    from base.dicionario import TABELAS

    return frozenset(
        nome
        for nome, tabela in TABELAS.items()
        if pessoa_decidida(
            nome,
            pessoa=tabela.pessoa,
            colunas=tabela.colunas,
            linhas_de_pessoa=tabela.linhas_de_pessoa,
        )
    )


def _falta_do_piloto(
    registro: ProntidaoDePiloto | None,
    versao_de_hoje: int | None,
    pessoa_decidida: bool,
    hoje: date,
) -> Falta | None:
    if registro is None or not pessoa_decidida:
        return Falta.SEM_PRONTIDAO
    qualidade, dicionario = registro.qualidade, registro.dicionario
    if not (_valida(qualidade, hoje) and _valida(dicionario, hoje)):
        return Falta.SEM_PRONTIDAO
    assert qualidade is not None  # conferido em `_valida`
    if versao_de_hoje != registro.versao_maior:
        return Falta.CONTRATO_MUDOU
    if _vencida(qualidade, hoje):
        return Falta.PRONTIDAO_VENCIDA
    return None


def negacao_do_piloto(
    tabelas: Iterable[str],
    registro: Mapping[str, ProntidaoDePiloto],
    versoes: Mapping[str, int],
    pessoa_decidida: frozenset[str],
    hoje: date,
) -> Falta | None:
    """Por que estas tabelas não podem servir hoje nem pelo piloto, ou None se **todas** têm o registro de
    piloto em dia e a marca de pessoa decidida. Sem tabela nenhuma, nega."""
    tabelas = tuple(tabelas)
    if not tabelas:
        return Falta.SEM_TABELA
    for tabela in tabelas:
        falta = _falta_do_piloto(
            registro.get(tabela), versoes.get(tabela), tabela in pessoa_decidida, hoje
        )
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


# Ensaio do piloto (linha 865): com `TICKERLAB_ENSAIO_DO_PILOTO=1` **e** o ensaio ligado, a prova de ensaio vai para
# o registro de piloto, e não para o cheio, para ensaiar a organização do piloto e o aviso. Fora do ensaio, nada.
VARIAVEL_DO_ENSAIO_DO_PILOTO = "TICKERLAB_ENSAIO_DO_PILOTO"
ENSAIO_DO_PILOTO_LIGADO = "1"


def em_ensaio_do_piloto(ambiente: Mapping[str, str] | None = None) -> bool:
    """O ensaio local ensaia o piloto (`TICKERLAB_ENSAIO_DO_PILOTO=1`, valor exato, só dentro do ensaio)?"""
    ambiente = ambiente if ambiente is not None else os.environ
    texto = ambiente.get(VARIAVEL_DO_ENSAIO_DO_PILOTO, "")
    return em_ensaio(ambiente) and texto.strip() == ENSAIO_DO_PILOTO_LIGADO


def _prova_de_ensaio(hoje: date | None) -> Prova:
    # ontem (UTC): vale em qualquer fuso do Brasil, e a prova de ensaio nunca vence no dia
    dia = hoje or datetime.now(UTC).date() - timedelta(days=1)
    return Prova(dia, PROVA_DE_ENSAIO, PROVA_DE_ENSAIO)


def registro_vigente(
    ambiente: Mapping[str, str] | None = None, hoje: date | None = None
) -> Mapping[str, Prontidao]:
    """O registro que o portão e o catálogo leem: o de verdade, ou, só no ensaio, o de verdade mais uma prova
    de ensaio (datada de ontem) nas tabelas que ainda não têm registro. Fora do ensaio, e no ensaio do piloto,
    devolve `PRONTIDAO` mesmo (o mesmo objeto)."""
    if not em_ensaio(ambiente) or em_ensaio_do_piloto(ambiente):
        return PRONTIDAO
    prova = _prova_de_ensaio(hoje)
    de_ensaio = {
        nome: Prontidao(versao, prova, prova, prova)
        for nome, versao in versoes_maiores().items()
    }
    return {**de_ensaio, **PRONTIDAO}


def registro_de_piloto_vigente(
    ambiente: Mapping[str, str] | None = None, hoje: date | None = None
) -> Mapping[str, ProntidaoDePiloto]:
    """O registro de piloto que o portão lê: o de verdade (o mesmo objeto) ou, só no ensaio do piloto, o de
    verdade mais a prova de ensaio nas tabelas que ainda não o têm. A marca de pessoa vale igual no ensaio."""
    if not em_ensaio_do_piloto(ambiente):
        return PRONTIDAO_DE_PILOTO
    prova = _prova_de_ensaio(hoje)
    de_ensaio = {
        nome: ProntidaoDePiloto(versao, prova, prova)
        for nome, versao in versoes_maiores().items()
    }
    return {**de_ensaio, **PRONTIDAO_DE_PILOTO}
