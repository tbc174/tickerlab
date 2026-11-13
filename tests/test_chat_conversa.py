"""As voltas de uma pergunta ao chat (linha 903), com o dublê do modelo: nenhuma chamada paga.

Riscos que estes testes pegam: (1) a conversa rodar ferramentas para sempre (sem limite de voltas);
(2) o "Como cheguei aqui" sair do modelo e não do código (lista do que foi consultado de verdade);
(3) uma recusa ou uma resposta cortada passarem como respondidas; (4) o histórico mandado pela tela
passar do teto; (5) o resultado da ferramenta voltar ao modelo sem a marca de dado; (6) o uso de uma
volta se perder na soma.
"""

import asyncio
import dataclasses

from src.chat import conversa as cv
from src.chat.custo import UsoDoModelo
from src.planos import LIMITES_DO_CHAT
from tests.ajudantes_do_chat import (
    USO_DA_VOLTA,
    ModeloDeMentira,
    caixa_de_mentira,
    pede,
    responde,
)

INSTRUCOES = "instruções de teste"


def _conversa(modelo, limites=LIMITES_DO_CHAT, caixa=None):
    return cv.Conversa(
        modelo=modelo,
        caixa=caixa or caixa_de_mentira(limites=limites),
        instrucoes=INSTRUCOES,
        limites=limites,
    )


def _eventos(conversa, pergunta="Quais setores vocês acompanham?", historico=()):
    async def juntar():
        return [e async for e in conversa.eventos(pergunta, historico)]

    return asyncio.run(juntar())


def test_pergunta_com_uma_consulta_e_a_resposta():
    modelo = ModeloDeMentira(
        pede(("setores", {})), responde("O TickerLab ", "acompanha Bancos.")
    )
    conversa = _conversa(modelo)
    eventos = _eventos(conversa)
    assert [e["tipo"] for e in eventos] == ["ferramenta", "texto", "texto", "fim"]
    assert eventos[0] == {
        "tipo": "ferramenta",
        "nome": "setores",
        "titulo": conversa.caixa.titulo("setores"),
        "filtros": {},
    }
    fim = eventos[-1]
    (consulta,) = fim["como_cheguei_aqui"]
    assert consulta["nome"] == "setores" and consulta["ok"] is True
    assert fim["avisos"] == [] and fim["aviso_final"] == cv.AVISO_FINAL
    assert conversa.estado == cv.RESPONDIDA
    assert conversa.chamadas == 1
    assert conversa.uso == USO_DA_VOLTA + USO_DA_VOLTA


def test_o_modelo_recebe_as_instrucoes_as_ferramentas_e_o_resultado_marcado():
    modelo = ModeloDeMentira(pede(("setores", {})), responde("ok"))
    _eventos(_conversa(modelo))
    primeiro, segundo = modelo.pedidos
    assert primeiro.sistema == INSTRUCOES
    assert primeiro.max_tokens == LIMITES_DO_CHAT.tokens_por_volta
    assert {f["name"] for f in primeiro.ferramentas} == {
        "buscar_empresas", "ficha_da_empresa", "comparaveis", "demonstracoes", "setores",
        "setor", "o_que_posso_ver", "novidades", "eventos", "vinculos",
        "compradores_do_setor", "fundo",
    }  # fmt: skip
    # a segunda volta leva o pedido do modelo inteiro e o resultado, marcado como dado
    assert segundo.mensagens[1]["role"] == "assistant"
    (resultado,) = segundo.mensagens[2]["content"]
    assert resultado["type"] == "tool_result" and resultado["tool_use_id"] == "toolu_0"
    assert resultado["content"].startswith("<dados_da_ferramenta")
    assert "is_error" not in resultado


def test_ferramenta_que_falha_volta_como_erro_e_entra_no_como_cheguei_aqui():
    modelo = ModeloDeMentira(
        pede(("fundo", {"cnpj": "11111111000191"}), ("web_search", {"q": "x"})),
        responde("Não temos."),
    )
    eventos = _eventos(_conversa(modelo))
    consultas = eventos[-1]["como_cheguei_aqui"]
    assert [(c["nome"], c["ok"]) for c in consultas] == [
        ("fundo", False),
        ("web_search", False),
    ]
    resultados = modelo.pedidos[1].mensagens[2]["content"]
    assert all(r["is_error"] for r in resultados)


def test_limite_de_voltas():
    limites = dataclasses.replace(LIMITES_DO_CHAT, voltas_de_ferramenta=2)
    voltas = [pede(("setores", {})) for _ in range(4)]
    modelo = ModeloDeMentira(*voltas)
    conversa = _conversa(modelo, limites)
    eventos = _eventos(conversa)
    fim = eventos[-1]
    # duas voltas de verdade, uma em que o modelo recebe o aviso do limite e a última, cortada
    assert len(modelo.pedidos) == 4
    assert conversa.chamadas == 2
    assert len(fim["como_cheguei_aqui"]) == 2
    terceira = modelo.pedidos[3].mensagens[-1]["content"][0]
    assert terceira["is_error"] and terceira["content"] == cv.MENSAGEM_LIMITE_DE_VOLTAS
    assert fim["avisos"] == [cv.AVISO_VOLTAS]


def test_recusa_do_modelo():
    conversa = _conversa(ModeloDeMentira(responde("", parada="refusal")))
    fim = _eventos(conversa)[-1]
    assert conversa.estado == cv.RECUSADA
    assert fim["avisos"] == [cv.AVISO_RECUSA]


def test_recusa_no_meio_nao_roda_a_ferramenta_pedida():
    volta = pede(("setores", {}))
    fim_da_volta = volta[-1]
    assert isinstance(fim_da_volta, cv.FimDoTurno)
    recusada = dataclasses.replace(fim_da_volta, parada="refusal")
    conversa = _conversa(ModeloDeMentira([recusada]))
    eventos = _eventos(conversa)
    assert conversa.chamadas == 0
    assert [e["tipo"] for e in eventos] == ["fim"]


def test_resposta_cortada_no_tamanho():
    volta = pede(("setores", {}))
    fim_da_volta = volta[-1]
    assert isinstance(fim_da_volta, cv.FimDoTurno)
    cortada = dataclasses.replace(fim_da_volta, parada="max_tokens")
    conversa = _conversa(ModeloDeMentira([cortada]))
    fim = _eventos(conversa)[-1]
    assert conversa.chamadas == 0
    assert fim["avisos"] == [cv.AVISO_CORTADA]
    assert conversa.estado == cv.RESPONDIDA


def test_recomeco_vira_evento():
    modelo = ModeloDeMentira([cv.Recomeco(), *responde("ok")])
    conversa = _conversa(modelo)
    eventos = _eventos(conversa)
    assert [e["tipo"] for e in eventos] == ["recomeco", "texto", "fim"]
    assert conversa.recomecos == 1


def test_volta_sem_fim_e_erro():
    conversa = _conversa(ModeloDeMentira([cv.TextoParcial("meio")]))
    try:
        _eventos(conversa)
    except RuntimeError:
        pass
    else:  # pragma: no cover - o teste falha se chegar aqui
        raise AssertionError("a volta sem fim deveria ter falhado")


# ---------------------------------------------------------------- o histórico


def test_historico_entra_antes_da_pergunta():
    historico = [cv.TrocaAnterior("p1", "r1"), cv.TrocaAnterior("p2", "r2")]
    mensagens = cv.mensagens_iniciais("nova", historico, LIMITES_DO_CHAT)
    assert mensagens == [
        {"role": "user", "content": "p1"},
        {"role": "assistant", "content": "r1"},
        {"role": "user", "content": "p2"},
        {"role": "assistant", "content": "r2"},
        {"role": "user", "content": "nova"},
    ]


def test_historico_fica_no_teto_de_trocas_e_de_caracteres():
    limites = dataclasses.replace(
        LIMITES_DO_CHAT, perguntas_no_historico=2, caracteres_do_historico=25
    )
    historico = [
        cv.TrocaAnterior("velha", "x" * 5),
        cv.TrocaAnterior("grande", "y" * 30),
        cv.TrocaAnterior("p3", "r3"),
    ]
    mensagens = cv.mensagens_iniciais("nova", historico, limites)
    # só as 2 últimas cabem pela conta; e a grande passa do teto de caracteres: fica só a última
    assert [m["content"] for m in mensagens] == ["p3", "r3", "nova"]


def test_pergunta_e_cortada_no_teto():
    limites = dataclasses.replace(LIMITES_DO_CHAT, caracteres_da_pergunta=5)
    (mensagem,) = cv.mensagens_iniciais("abcdefghij", (), limites)
    assert mensagem["content"] == "abcde"


def test_resumo_dos_filtros_tira_vazios_e_corta_texto():
    resumo = cv.resumo_dos_filtros(
        {
            "cnpj": "1" * 200,
            "uf": None,
            "lista": [],
            "vazio": "",
            "limite": 5,
            "x": [1, 2],
        }
    )
    assert resumo == {
        "cnpj": "1" * cv.CARACTERES_DO_FILTRO,
        "limite": 5,
        "x": "[1, 2]",
    }
    assert cv.resumo_dos_filtros("texto") == {}


def test_uso_soma_as_voltas():
    assert UsoDoModelo(1, 2, 3, 4) + UsoDoModelo(10, 20, 30, 40) == UsoDoModelo(
        11, 22, 33, 44
    )
