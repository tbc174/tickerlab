"""A página de boas-vindas do beta por convite (ADR 0109, item 11 e Emenda 1; linha 211 da fila).

O convidado entra como qualquer conta (login com o Google ou por e-mail com código): nada de dado novo
da conta nem de plano diferente. Aqui fica só o **texto** da página e o **roteiro dos 10 minutos**, ligado
às páginas que já existem; a tela só mostra. Tipos simples (texto e tuplas), para virar JSON na API.

Sem recomendação de investimento e sem promessa: o beta é grátis e pode mudar.
"""

from dataclasses import dataclass

TITULO = "Boas-vindas ao beta do TickerLab"
ABERTURA = (
    "Você foi convidado para usar o TickerLab antes do lançamento. Em 10 minutos dá para ver o que ele faz: "
    "dados públicos de empresas brasileiras, com a fonte e a data de cada número."
)
SOBRE_O_BETA = (
    "O beta é grátis e pode mudar: telas e números podem ser corrigidos sem aviso. "
    "Nada aqui é recomendação de investimento."
)
COMO_RESPONDER = (
    "Para dizer o que travou, o que faltou ou o que funcionou, responda ao e-mail do convite: "
    "a cada duas semanas chegam 5 perguntas curtas, e a sua resposta por e-mail basta."
)


@dataclass(frozen=True)
class Passo:
    """Um passo do roteiro: o que fazer, em quanto tempo, e a página do app onde fazer."""

    ordem: int
    minutos: int
    titulo: str
    o_que_fazer: str
    url: str  # o endereço da página no app, sem a barra (src/paginas.py)


ROTEIRO = (
    Passo(
        1,
        3,
        "Relatório do setor",
        "Escolha um setor e veja quem está nele, o tamanho do mercado e a concentração (CR4 e HHI), "
        "com a fonte de cada número. Se quiser levar para uma reunião, baixe o deck do relatório.",
        "relatorio-do-setor",
    ),
    Passo(
        2,
        4,
        "Relatório de uma empresa",
        "Abra o relatório de uma empresa da bolsa que você conhece: resultado, dívida, caixa e comparação "
        "com o setor. Confira se algum número não bate com o que você sabe e confira a fonte.",
        "relatorio-empresa",
    ),
    Passo(
        3,
        2,
        "Busca por CNPJ",
        "Digite o CNPJ de uma empresa fora da bolsa (um cliente, um alvo, uma contraparte) e veja o que "
        "é público sobre ela, com a data e a fonte de cada linha.",
        "busca-por-cnpj",
    ),
    Passo(
        4,
        1,
        "Conte o que faltou",
        "Anote uma coisa que você esperava achar e não achou. É a resposta mais útil que o beta pode receber.",
        "boas-vindas-beta",
    ),
)

TOTAL_DE_MINUTOS = sum(passo.minutos for passo in ROTEIRO)
