"""O estado do chat para a tela "Perguntar" (linha 903): se dá para perguntar agora e por que não.

A rota `GET /v1/chat/estado` (`src/api_v1/chat.py`) junta o que só o servidor sabe (a chave de ligar, a
organização da conta, a cota e o teto do mês) e esta função escreve a resposta em tipos simples. As frases de
recusa são as mesmas da rota `POST /v1/chat`: a tela mostra antes o que a pergunta ouviria depois.

O gasto em dinheiro não sai daqui: a tela só sabe se o teto do mês pausou o chat.
"""

from dataclasses import dataclass
from typing import Literal

from src.planos import LimitesDoChat

Situacao = Literal[
    "desligado",
    "sem_organizacao",
    "sem_chave",
    "pausado",
    "cota_do_dia",
    "cota_do_mes",
    "pronto",
]

MENSAGEM_DESLIGADO = "Chat não disponível."
MENSAGEM_SEM_ORGANIZACAO = "O chat é da equipe de uma organização com contrato no TickerLab: a sua conta não está numa."
MENSAGEM_SEM_CHAVE = "A organização não tem uma chave da API ativa: quem administra a conta cria uma na página da organização."
MENSAGEM_COTA_DO_DIA = "Você chegou ao limite de perguntas de hoje; ele volta amanhã."
MENSAGEM_COTA_DO_MES = "Você chegou ao limite de perguntas do mês; ele volta no dia 1º."
MENSAGEM_PAUSADO = "O chat está pausado até o fim do mês: o TickerLab chegou ao teto de gasto do mês com o modelo."
# a tela não diz só "não disponível": diz que ainda não foi ligado e o que o chat vai fazer
MENSAGEM_AINDA_NAO_LIGADO = (
    "O chat de IA ainda não foi ligado. Quando estiver, você pergunta aqui em português e a resposta vem "
    "da base do TickerLab, com a fonte e a data de cada número e as consultas que foram feitas."
)

COMO_FUNCIONA = (
    "O modelo só lê a base pelas 12 ferramentas do conector e da CLI: não busca na internet, não escreve e "
    "não envia nada. Pessoa física não entra na conversa, nem para a organização que vê sócios na tela."
)
EXEMPLOS_DE_PERGUNTA = (
    "Quais fabricantes de embalagens plásticas de Santa Catarina têm mais de 15 anos?",
    "Quem compraria uma empresa de software de gestão para hospitais?",
    "Compare as maiores companhias abertas de saneamento pela receita e pela dívida.",
)

_MENSAGENS: dict[Situacao, str | None] = {
    "desligado": MENSAGEM_AINDA_NAO_LIGADO,
    "sem_organizacao": MENSAGEM_SEM_ORGANIZACAO,
    "sem_chave": MENSAGEM_SEM_CHAVE,
    "pausado": MENSAGEM_PAUSADO,
    "cota_do_dia": MENSAGEM_COTA_DO_DIA,
    "cota_do_mes": MENSAGEM_COTA_DO_MES,
    "pronto": None,
}


@dataclass(frozen=True)
class FatosDoChat:
    """O que a rota apurou para a conta, na ordem em que a pergunta seria recusada."""

    ligado: bool  # a chave de ligar, a chave do modelo e o modelo com preço
    tem_organizacao: bool
    tem_chave_da_api: bool
    perguntas_hoje: int
    perguntas_no_mes: int
    pausado: bool  # o teto do mês, somando todas as contas, não cabe mais uma pergunta


def situacao_do_chat(fatos: FatosDoChat, limites: LimitesDoChat) -> Situacao:
    """A primeira recusa que a pergunta ouviria, na ordem da rota `POST /v1/chat`; ou "pronto"."""
    if not fatos.ligado:
        return "desligado"
    if not fatos.tem_organizacao:
        return "sem_organizacao"
    if not fatos.tem_chave_da_api:
        return "sem_chave"
    if fatos.perguntas_hoje >= limites.perguntas_por_dia:
        return "cota_do_dia"
    if fatos.perguntas_no_mes >= limites.perguntas_por_mes:
        return "cota_do_mes"
    if fatos.pausado:
        return "pausado"
    return "pronto"


def _milhar(numero: int) -> str:
    """2000 → "2.000" (o separador de milhar do português)."""
    return f"{numero:_}".replace("_", ".")


def limites_para_a_tela(limites: LimitesDoChat) -> list[str]:
    """A seção "Limites e cuidados" do chat, com os números de `LIMITES_DO_CHAT`."""
    return [
        f"Até {limites.perguntas_por_dia} perguntas por dia e {limites.perguntas_por_mes} por mês por conta.",
        (
            f"Cada pergunta faz no máximo {limites.voltas_de_ferramenta} rodadas de consultas à base; a "
            "resposta diz o que faltou quando o limite chega antes."
        ),
        (
            f"A pergunta tem até {_milhar(limites.caracteres_da_pergunta)} caracteres, e o modelo lembra as "
            f"{limites.perguntas_no_historico} últimas trocas desta conversa."
        ),
        (
            "A resposta é escrita por IA com os dados do TickerLab: confira a fonte e a data de cada número "
            "antes de usar."
        ),
        "O chat só tem o que a base tem: faturamento de empresa fechada, por exemplo, não está nela.",
        "Nada aqui é recomendação de investimento.",
    ]


def estado_para_a_tela(fatos: FatosDoChat, limites: LimitesDoChat) -> dict[str, object]:
    """A resposta de `GET /v1/chat/estado` (esquema `EstadoDoChatV1`)."""
    situacao = situacao_do_chat(fatos, limites)
    return {
        "situacao": situacao,
        "pode_perguntar": situacao == "pronto",
        "mensagem": _MENSAGENS[situacao],
        "perguntas_hoje": fatos.perguntas_hoje,
        "perguntas_por_dia": limites.perguntas_por_dia,
        "perguntas_no_mes": fatos.perguntas_no_mes,
        "perguntas_por_mes": limites.perguntas_por_mes,
        "caracteres_da_pergunta": limites.caracteres_da_pergunta,
        "perguntas_no_historico": limites.perguntas_no_historico,
        "caracteres_do_historico": limites.caracteres_do_historico,
        "como_funciona": COMO_FUNCIONA,
        "exemplos": list(EXEMPLOS_DE_PERGUNTA),
        "limites": limites_para_a_tela(limites),
    }
