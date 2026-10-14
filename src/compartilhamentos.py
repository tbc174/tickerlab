"""Compartilhamento seguro (onda 4 da ADR 0046): as regras do link, sem banco e sem tela.

A pessoa cria um link secreto, com prazo e que pode revogar, para mostrar a alguém sem conta a
ficha "Foi sorte?" de um backtest ou o PDF original de um relatório da biblioteca.

- **O código** tem 256 bits (`secrets`) e o banco guarda só o hash SHA-256 dele: se o banco
  vazar, os links não vazam. Por isso o link aparece uma vez só, na hora de criar.
- **A ficha é congelada:** guarda o que a tela mostrou, com a data do cálculo. Quem abre o link
  vê exatamente aquilo; nada é recalculado (nem baixado) na visita. Não leva o capital nem os
  preços.
- **O que volta do banco não é confiável:** `ler_ficha_congelada` confere tipo e tamanho de
  cada campo e que o veredito é o que as checagens dão, e recusa o resto com `ValueError`.
"""

import hashlib
import math
import re
import secrets
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta

from src import ficha
from src.ficha import Checagem, Ficha, PedidoDaFicha, Resultado, Situacao, Veredito
from src.link import ticker_valido
from src.protecoes import Protecoes

TIPOS = ("ficha", "pdf")
PRAZOS_EM_DIAS = (7, 30, 90)
PRAZO_PADRAO = 30
BYTES_DO_CODIGO = 32  # 256 bits: adivinhar um link é impossível na prática
FORMATO_DO_CODIGO = re.compile(r"[A-Za-z0-9_-]{43}")  # base64 de URL, sem o "=" do fim

VERSAO_DA_FICHA = 1
MAXIMO_DE_CHECAGENS = 10
MAXIMO_DE_PARAMETROS = 30
TAMANHO_MAXIMO_DO_NOME = 40  # nome de um parâmetro ou de uma proteção
TAMANHO_MAXIMO_DO_VALOR = 60  # parâmetro de texto (ex.: "Simples")
TAMANHO_MAXIMO_DA_ESTRATEGIA = 80
TAMANHO_MAXIMO_DA_PERGUNTA = 200
TAMANHO_MAXIMO_DO_TEXTO = 2000
TAMANHO_MAXIMO_DA_FONTE = 200
CUSTO_MAXIMO = 0.2  # 20% por operação: acima disso não é um custo, é um erro
TENTATIVAS_MAXIMAS = 10_000_000


ENDERECO_DA_PAGINA = (
    "https://app.tickerlab.com.br/novo/c"  # a página pública (web/, PR 3)
)
NOMES_DOS_TIPOS = {"ficha": 'Ficha "Foi sorte?"', "pdf": "PDF original"}
O_QUE_FICA_VISIVEL = {
    "ficha": "Quem tiver o link vê esta ficha como está agora, com a data de hoje, sem o seu nome "
    "nem o seu e-mail. Nada é recalculado depois.",
    "pdf": "Quem tiver o link baixa este PDF como foi gerado, sem ver o seu nome nem o seu e-mail.",
}
AVISO_DO_LINK_CRIADO = (
    "Copie agora: o TickerLab guarda só uma impressão do link, então ele não aparece de novo. "
    "Se perder, revogue em Meus dados e crie outro."
)


# Meus dados › Links compartilhados (o Streamlit e o app novo mostram as mesmas frases)
SEM_LINKS = (
    'Você ainda não compartilhou nada. A ficha "Foi sorte?" do backtest e os PDFs '
    'guardados na biblioteca têm o botão "Compartilhar".'
)
EXPLICACAO_DOS_LINKS = (
    "Quem tem o link vê o que você compartilhou, sem o seu nome nem o seu e-mail. "
    "Revogar tira o acesso na hora."
)


def descrever_link(
    tipo: str, situacao: str, criado_em: datetime, expira_em: datetime, visitas: int
) -> str:
    """ "Ficha "Foi sorte?" · ativo · criado em 14/10/2026 · vale até 13/11/2026 · 2 visita(s)"."""
    return " · ".join(
        [
            NOMES_DOS_TIPOS[tipo],
            situacao,
            f"criado em {criado_em:%d/%m/%Y}",
            f"vale até {expira_em:%d/%m/%Y}",
            f"{visitas} visita(s)",
        ]
    )


def endereco_do_link(codigo: str) -> str:
    """O código vai depois do "#": o navegador não o manda a servidor nenhum nem ao Referer."""
    return f"{ENDERECO_DA_PAGINA}#{codigo}"


def rotulo_do_prazo(dias: int) -> str:
    return f"{dias} dias"


def fonte_dos_precos(origem: object) -> str:
    """De onde vieram os preços da ficha, pela `dados.attrs["origem"]` (como na Visão geral)."""
    from src.analise import (
        FONTES,
    )  # aqui: o módulo da análise é pesado e só a tela precisa

    return FONTES.get(origem, str(origem))  # type: ignore[arg-type]


# --- o código e o prazo --------------------------------------------------------------------


def novo_codigo() -> str:
    """Um código novo para o link (43 caracteres). Só existe aqui: o banco guarda o hash."""
    return secrets.token_urlsafe(BYTES_DO_CODIGO)


def hash_do_codigo(codigo: str) -> str:
    """O que o banco guarda: SHA-256 em hexadecimal (64 caracteres)."""
    return hashlib.sha256(codigo.encode()).hexdigest()


def codigo_valido(texto: object) -> bool:
    """O texto tem o formato de um código? (Nem vai ao banco se não tiver.)"""
    return isinstance(texto, str) and FORMATO_DO_CODIGO.fullmatch(texto) is not None


def expira_em(agora: datetime, dias: int) -> datetime:
    if dias not in PRAZOS_EM_DIAS:
        raise ValueError(f"O link vale {', '.join(map(str, PRAZOS_EM_DIAS))} dias.")
    return agora + timedelta(days=dias)


# --- a ficha congelada ---------------------------------------------------------------------


@dataclass(frozen=True)
class FichaCongelada:
    """A ficha "Foi sorte?" como a pessoa viu, pronta para a página pública."""

    ticker: str
    estrategia: str
    parametros: dict[str, int | float | str | bool]
    protecoes: dict[str, int | float]  # só as que a pessoa mudou
    custo_por_operacao: float  # o que a ficha usou (nunca abaixo do padrão do app)
    inicio: date
    fim: date
    checagens: tuple[Checagem, ...]
    tentativas: int
    veredito: Veredito
    texto_das_tentativas: str
    fonte: str
    calculada_em: datetime


def titulo_da_ficha(ticker: str, estrategia: str) -> str:
    return f"Foi sorte? {estrategia} em {ticker.removesuffix('.SA')}"


def congelar_ficha(
    resultado: Ficha,
    pedido: PedidoDaFicha,
    ticker: str,
    texto_das_tentativas: str,
    fonte: str,
    agora: datetime,
) -> dict:
    """A ficha que a tela acabou de mostrar, em tipos simples (JSON), com a data do cálculo."""
    veredito = resultado.veredito
    # só o que a pessoa mudou: as janelas sempre têm número, mesmo com a proteção desligada
    padrao = asdict(Protecoes())
    escolhidas = {} if pedido.protecoes is None else asdict(pedido.protecoes)
    return {
        "versao": VERSAO_DA_FICHA,
        "ticker": ticker,
        "estrategia": pedido.estrategia,
        "parametros": dict(pedido.parametros),
        "protecoes": {k: v for k, v in escolhidas.items() if v != padrao[k]},
        "custo_por_operacao": float(ficha.custo_da_checagem(pedido.custo_por_operacao)),
        "inicio": pedido.dados.index[0].date().isoformat(),
        "fim": pedido.dados.index[-1].date().isoformat(),
        "checagens": [
            {
                "pergunta": c.pergunta,
                "situacao": c.situacao.value,
                "explicacao": c.explicacao,
            }
            for c in resultado.checagens
        ],
        "tentativas": int(resultado.tentativas),
        "resultado": veredito.resultado.value,
        "titulo": veredito.titulo,
        "texto": veredito.texto,
        "texto_das_tentativas": texto_das_tentativas,
        "fonte": fonte,
        "calculada_em": agora.isoformat(),
    }


def _recusar(motivo: str) -> ValueError:
    return ValueError(f"A ficha compartilhada não vale: {motivo}.")


def _texto(valor: object, maximo: int, nome: str) -> str:
    if not isinstance(valor, str) or not 1 <= len(valor) <= maximo:
        raise _recusar(nome)
    return valor


def _numero(valor: object, minimo: float, maximo: float, nome: str) -> float:
    if (
        isinstance(valor, bool)
        or not isinstance(valor, int | float)
        or not math.isfinite(valor)
        or not minimo <= valor <= maximo
    ):
        raise _recusar(nome)
    return valor


def _valores(guardados: object, aceita_texto: bool, nome: str) -> dict:
    """Um dicionário pequeno de nome → número (ou texto curto, nos parâmetros)."""
    if not isinstance(guardados, Mapping) or len(guardados) > MAXIMO_DE_PARAMETROS:
        raise _recusar(nome)
    validos: dict = {}
    for chave, valor in guardados.items():
        _texto(chave, TAMANHO_MAXIMO_DO_NOME, nome)
        if aceita_texto and isinstance(valor, str):
            validos[chave] = _texto(valor, TAMANHO_MAXIMO_DO_VALOR, nome)
        elif aceita_texto and isinstance(valor, bool):
            validos[chave] = valor
        else:
            validos[chave] = _numero(valor, -1e12, 1e12, nome)
    return validos


def _data(valor: object, nome: str) -> date:
    try:
        return date.fromisoformat(_texto(valor, 10, nome))
    except ValueError:
        raise _recusar(nome) from None


def _checagens(guardadas: object) -> tuple[Checagem, ...]:
    if (
        not isinstance(guardadas, list)
        or not 1 <= len(guardadas) <= MAXIMO_DE_CHECAGENS
    ):
        raise _recusar("checagens")
    lidas = []
    for guardada in guardadas:
        if not isinstance(guardada, Mapping):
            raise _recusar("checagem")
        try:
            situacao = Situacao(guardada.get("situacao"))
        except ValueError:
            raise _recusar("situação da checagem") from None
        lidas.append(
            Checagem(
                _texto(
                    guardada.get("pergunta"), TAMANHO_MAXIMO_DA_PERGUNTA, "pergunta"
                ),
                situacao,
                _texto(
                    guardada.get("explicacao"), TAMANHO_MAXIMO_DO_TEXTO, "explicação"
                ),
            )
        )
    return tuple(lidas)


def ler_ficha_congelada(dados: object) -> FichaCongelada:
    """A ficha guardada de volta. Vem do banco: qualquer campo estranho levanta ValueError."""
    if not isinstance(dados, Mapping):
        raise _recusar("formato")
    if dados.get("versao") != VERSAO_DA_FICHA:
        raise _recusar("versão")
    ticker = dados.get("ticker")
    if not isinstance(ticker, str) or not ticker_valido(ticker):
        raise _recusar("ativo")
    inicio, fim = _data(dados.get("inicio"), "início"), _data(dados.get("fim"), "fim")
    if fim < inicio:
        raise _recusar("período")
    checagens = _checagens(dados.get("checagens"))
    tentativas = dados.get("tentativas")
    if (
        isinstance(tentativas, bool)
        or not isinstance(tentativas, int)
        or not 0 <= tentativas <= TENTATIVAS_MAXIMAS
    ):
        raise _recusar("tentativas")
    try:
        resultado = Resultado(dados.get("resultado"))
    except ValueError:
        raise _recusar("resultado") from None
    if resultado != ficha.montar_veredito(checagens).resultado:
        raise _recusar("o veredito não é o que as checagens dão")
    try:
        calculada_em = datetime.fromisoformat(
            _texto(dados.get("calculada_em"), 40, "data do cálculo")
        )
    except ValueError:
        raise _recusar("data do cálculo") from None
    if calculada_em.tzinfo is None:
        raise _recusar("data do cálculo sem fuso")
    return FichaCongelada(
        ticker=ticker,
        estrategia=_texto(
            dados.get("estrategia"), TAMANHO_MAXIMO_DA_ESTRATEGIA, "estratégia"
        ),
        parametros=_valores(dados.get("parametros"), True, "parâmetros"),
        protecoes=_valores(dados.get("protecoes"), False, "proteções"),
        custo_por_operacao=_numero(
            dados.get("custo_por_operacao"), 0, CUSTO_MAXIMO, "custo"
        ),
        inicio=inicio,
        fim=fim,
        checagens=checagens,
        tentativas=tentativas,
        veredito=Veredito(
            resultado,
            _texto(dados.get("titulo"), TAMANHO_MAXIMO_DA_PERGUNTA, "título"),
            _texto(dados.get("texto"), TAMANHO_MAXIMO_DO_TEXTO, "texto"),
        ),
        texto_das_tentativas=_texto(
            dados.get("texto_das_tentativas"), TAMANHO_MAXIMO_DO_TEXTO, "tentativas"
        ),
        fonte=_texto(dados.get("fonte"), TAMANHO_MAXIMO_DA_FONTE, "fonte"),
        calculada_em=calculada_em,
    )
