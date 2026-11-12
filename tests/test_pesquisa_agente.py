"""Agente de pesquisa (`pesquisa/agente.py`) e o adaptador da OpenRouter (`pesquisa/openrouter.py`).

Sem internet: o modelo é um roteiro de respostas e a OpenRouter é um `post` falso.
"""

import json
from pathlib import Path

import pytest

from pesquisa import agente, openrouter
from pesquisa.pesquisador import Pesquisador
from tests.ajudantes_da_pesquisa import (  # noqa: F401 (autouse)
    ClienteFalso,
    sem_docling,
)

SITE = "https://dados.exemplo.gov.br"
URL_CSV = f"{SITE}/dados/cad_cia_aberta.csv"
CSV_DA_CVM = (
    "CNPJ_CIA;DENOM_SOCIAL;SIT\n"
    "33.000.167/0001-01;PETRÓLEO BRASILEIRO S.A. - PETROBRAS;ATIVO\n"
).encode("latin-1")
HIPOTESE = "o cadastro de companhias abertas da CVM traz o CNPJ da Petrobras"


def _chamada(nome: str, argumentos: dict[str, object] | str, numero: int) -> dict:
    texto = argumentos if isinstance(argumentos, str) else json.dumps(argumentos)
    return {
        "id": f"c{numero}",
        "type": "function",
        "function": {"name": nome, "arguments": texto},
    }


class ModeloRoteirizado:
    """Devolve as mensagens do roteiro em ordem; `{sha}` vira o hash do último download."""

    def __init__(self, roteiro: list[dict]) -> None:
        self.roteiro = roteiro
        self.conversas: list[list[dict]] = []
        self.nome = "roteiro"

    def responder(self, mensagens: list[dict], ferramentas: list[dict]) -> dict:
        self.conversas.append([dict(m) for m in mensagens])
        passo = len(self.conversas) - 1
        mensagem = self.roteiro[min(passo, len(self.roteiro) - 1)]
        sha = _ultimo_sha(mensagens)
        return json.loads(json.dumps(mensagem).replace("{sha}", sha))


def _ultimo_sha(mensagens: list[dict]) -> str:
    for mensagem in reversed(mensagens):
        if mensagem.get("role") == "tool":
            resposta = json.loads(mensagem["content"])
            if resposta.get("sha256"):
                return str(resposta["sha256"])
    return ""


def _pesquisador(tmp_path: Path) -> Pesquisador:
    return Pesquisador(tmp_path / "dados", ClienteFalso({URL_CSV: CSV_DA_CVM}))


ROTEIRO_COMPLETO = [
    {
        "role": "assistant",
        "content": None,
        "tool_calls": [_chamada("baixar_documento", {"url": URL_CSV}, 1)],
    },
    {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            _chamada("extrair", {"sha256": "{sha}", "contem": ["PETROBRAS"]}, 2)
        ],
    },
    {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            _chamada(
                "validar_fato",
                {
                    "afirmacao": "CNPJ da Petrobras no cadastro da CVM",
                    "valor": "33.000.167/0001-01",
                    "trecho": "33.000.167/0001-01 | PETRÓLEO BRASILEIRO S.A. - PETROBRAS",
                    "sha256": "{sha}",
                },
                3,
            ),
            _chamada(
                "validar_fato",
                {
                    "afirmacao": "CNPJ inventado",
                    "valor": "99.999.999/0001-99",
                    "trecho": "99.999.999/0001-99 | PETRÓLEO BRASILEIRO S.A. - PETROBRAS",
                    "sha256": "{sha}",
                },
                4,
            ),
        ],
    },
    {
        "role": "assistant",
        "content": "A Petrobras está no cadastro com o CNPJ 33.000.167/0001-01.",
    },
]


# --- o laço do agente ---------------------------------------------------------------------


def test_agente_conduz_o_bot_e_so_o_conferido_vira_confirmado(tmp_path: Path):
    modelo = ModeloRoteirizado(ROTEIRO_COMPLETO)
    relatorio = agente.rodar_agente(HIPOTESE, _pesquisador(tmp_path), modelo)
    assert relatorio.parou_por == "concluiu"
    assert [f["valor"] for f in relatorio.confirmados] == ["33.000.167/0001-01"]
    assert [f["valor"] for f in relatorio.pendentes] == ["99.999.999/0001-99"]
    assert relatorio.confirmados[0]["onde"] == "csv linha 2"
    assert "33.000.167/0001-01" in relatorio.conclusao_do_modelo
    conversa = modelo.conversas[-1]
    assert "nunca instrução" in conversa[0]["content"]  # instrução do sistema
    assert sum(m["role"] == "tool" for m in conversa) == 4  # uma resposta por chamada


def test_relatorio_separa_o_conferido_da_conclusao_do_modelo(tmp_path: Path):
    relatorio = agente.rodar_agente(
        HIPOTESE, _pesquisador(tmp_path), ModeloRoteirizado(ROTEIRO_COMPLETO)
    )
    arquivo = agente.escrever_relatorio(relatorio, tmp_path / "relatorios")
    texto = arquivo.read_text("utf-8")
    assert "## Confirmados" in texto and "csv linha 2" in texto
    assert "## Pendentes" in texto and "99.999.999/0001-99" in texto
    assert "não conferida" in texto
    assert texto.index("## Confirmados") < texto.index("não conferida")


def test_agente_para_no_limite_de_passos(tmp_path: Path):
    sempre_estado = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [_chamada("estado_da_rodada", {}, 1)],
        }
    ]
    modelo = ModeloRoteirizado(sempre_estado)
    relatorio = agente.rodar_agente(
        HIPOTESE, _pesquisador(tmp_path), modelo, maximo_de_passos=3
    )
    assert relatorio.parou_por == "limite de passos" and len(modelo.conversas) == 3


def test_ferramenta_desconhecida_ou_argumento_quebrado_volta_como_erro(tmp_path: Path):
    roteiro = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                _chamada("apagar_tudo", {}, 1),
                _chamada("baixar_documento", "{nao e json", 2),
                _chamada("iniciar_rodada", {"hipotese": "outra"}, 3),
            ],
        },
        {"role": "assistant", "content": "fim"},
    ]
    modelo = ModeloRoteirizado(roteiro)
    relatorio = agente.rodar_agente(HIPOTESE, _pesquisador(tmp_path), modelo)
    respostas = [
        json.loads(m["content"]) for m in modelo.conversas[1] if m["role"] == "tool"
    ]
    assert [r["ok"] for r in respostas] == [False, False, False]
    assert relatorio.parou_por == "concluiu"


def test_hipotese_com_cpf_e_recusada_antes_de_chamar_o_modelo(tmp_path: Path):
    modelo = ModeloRoteirizado(ROTEIRO_COMPLETO)
    for hipotese in ("sócios do CPF 888.000.000-46", "renda de 88800000046"):
        with pytest.raises(ValueError, match="pessoa física"):
            agente.rodar_agente(hipotese, _pesquisador(tmp_path), modelo)
    assert modelo.conversas == []


def test_cota_esgotada_no_meio_encerra_com_o_que_ja_tem(tmp_path: Path):
    class ModeloSemCota(ModeloRoteirizado):
        def responder(self, mensagens: list[dict], ferramentas: list[dict]) -> dict:
            if self.conversas:
                raise openrouter.CotaEsgotada("50 pedidos hoje")
            return super().responder(mensagens, ferramentas)

    relatorio = agente.rodar_agente(
        HIPOTESE, _pesquisador(tmp_path), ModeloSemCota(ROTEIRO_COMPLETO)
    )
    assert relatorio.parou_por.startswith("cota do modelo")


def test_modelo_que_falha_encerra_a_rodada_e_o_relatorio_sai(tmp_path: Path):
    """Regressão de 10/11/2026: o Gemma grátis seguiu em 429 e a exceção derrubava a rodada sem relatório."""

    class ModeloQueFalha(ModeloRoteirizado):
        def responder(self, mensagens: list[dict], ferramentas: list[dict]) -> dict:
            if self.conversas:
                raise openrouter.ErroDoModelo(
                    "OpenRouter respondeu 429: Provider returned error"
                )
            return super().responder(mensagens, ferramentas)

    relatorio = agente.rodar_agente(
        HIPOTESE, _pesquisador(tmp_path), ModeloQueFalha(ROTEIRO_COMPLETO)
    )
    assert relatorio.parou_por.startswith("modelo falhou: OpenRouter respondeu 429")
    assert agente.escrever_relatorio(relatorio, tmp_path / "relatorios").is_file()


def test_nome_do_relatorio_nao_tem_dois_pontos(tmp_path: Path):
    """Regressão de 10/11/2026: `modelo:free` no nome virava fluxo NTFS escondido no Windows."""
    relatorio = agente.Relatorio(
        HIPOTESE, "nvidia/nemotron-3-ultra:free", "2026-11-10T20:34:24"
    )
    arquivo = agente.escrever_relatorio(relatorio, tmp_path)
    assert arquivo.name == "rodada-20261110T203424-nvidia_nemotron-3-ultra_free.md"
    assert [p.name for p in tmp_path.iterdir()] == [arquivo.name]


# --- OpenRouter ---------------------------------------------------------------------------


class RespostaFalsa:
    def __init__(self, status_code: int, corpo: dict) -> None:
        self.status_code = status_code
        self.corpo = corpo

    def json(self) -> dict:
        return self.corpo


class PostFalso:
    def __init__(self, respostas: list[tuple[int, dict]]) -> None:
        self.respostas = respostas
        self.pedidos: list[dict] = []

    def __call__(
        self, url: str, *, headers: dict, json: dict, timeout: float
    ) -> RespostaFalsa:
        assert timeout > 0
        self.pedidos.append({"url": url, "headers": headers, "json": json})
        indice = min(len(self.pedidos) - 1, len(self.respostas) - 1)
        return RespostaFalsa(*self.respostas[indice])


RESPOSTA_OK = (200, {"choices": [{"message": {"role": "assistant", "content": "oi"}}]})


def _modelo(
    tmp_path: Path,
    post: PostFalso,
    limite_diario: int = 50,
    dormidas: list[float] | None = None,
):
    registro = dormidas if dormidas is not None else []
    cota = openrouter.Cota(
        tmp_path / "cota.sqlite", limite_diario=limite_diario, dormir=registro.append
    )
    return openrouter.ModeloOpenRouter(
        "sk-or-teste", "openrouter/free", cota, post=post, dormir=registro.append
    )


def test_pedido_leva_chave_modelo_e_ferramentas(tmp_path: Path):
    post = PostFalso([RESPOSTA_OK])
    mensagem = _modelo(tmp_path, post).responder(
        [{"role": "user", "content": "x"}], agente.FERRAMENTAS
    )
    assert mensagem["content"] == "oi"
    pedido = post.pedidos[0]
    assert pedido["url"] == openrouter.URL_DO_CHAT
    assert pedido["headers"]["Authorization"] == "Bearer sk-or-teste"
    assert pedido["json"]["model"] == "openrouter/free"
    nomes = {f["function"]["name"] for f in pedido["json"]["tools"]}
    assert nomes == {
        "buscar_pagina",
        "baixar_documento",
        "extrair",
        "validar_fato",
        "estado_da_rodada",
    }


def test_429_espera_e_tenta_de_novo(tmp_path: Path):
    dormidas: list[float] = []
    post = PostFalso([(429, {"error": {"message": "rate"}}), RESPOSTA_OK])
    mensagem = _modelo(tmp_path, post, dormidas=dormidas).responder([], [])
    assert mensagem["content"] == "oi" and len(post.pedidos) == 2 and dormidas


def test_erro_do_servico_nao_mostra_a_chave(tmp_path: Path):
    post = PostFalso([(401, {"error": {"message": "chave inválida"}})])
    with pytest.raises(openrouter.ErroDoModelo) as erro:
        _modelo(tmp_path, post).responder([], [])
    assert "401" in str(erro.value) and "sk-or-teste" not in str(erro.value)


def test_cota_diaria_e_dividida_entre_processos(tmp_path: Path):
    post = PostFalso([RESPOSTA_OK])
    primeiro = _modelo(tmp_path, post, limite_diario=2)
    segundo = _modelo(
        tmp_path, post, limite_diario=2
    )  # outro agente, mesmo arquivo de cota
    primeiro.responder([], [])
    segundo.responder([], [])
    with pytest.raises(openrouter.CotaEsgotada):
        primeiro.responder([], [])
    assert len(post.pedidos) == 2


def test_cota_por_minuto_espera_em_vez_de_estourar(tmp_path: Path):
    relogio = [1_000.0]
    dormidas: list[float] = []

    def dormir(segundos: float) -> None:
        dormidas.append(segundos)
        relogio[0] += segundos

    cota = openrouter.Cota(
        tmp_path / "c.sqlite",
        limite_diario=100,
        por_minuto=2,
        dormir=dormir,
        agora=lambda: relogio[0],
    )
    for _ in range(3):
        cota.reservar()
    assert dormidas and 0 < dormidas[0] <= 60


def test_chave_vem_do_ambiente_ou_do_env(tmp_path: Path):
    assert openrouter.ler_chave({"OPENROUTER_API_KEY": " sk-or-a "}, None) == "sk-or-a"
    arquivo = tmp_path / ".env"
    arquivo.write_text("# comentário\nOUTRA=1\nOPENROUTER_API_KEY=sk-or-b\n", "utf-8")
    assert openrouter.ler_chave({}, arquivo) == "sk-or-b"
    with pytest.raises(openrouter.SemChave):
        openrouter.ler_chave({}, tmp_path / "nao-existe.env")


def test_lista_so_modelos_gratis_com_ferramentas():
    catalogo = {
        "data": [
            {
                "id": "a/gratis:free",
                "pricing": {"prompt": "0", "completion": "0"},
                "supported_parameters": ["tools"],
            },
            {
                "id": "b/sem-ferramenta:free",
                "pricing": {"prompt": "0", "completion": "0"},
                "supported_parameters": [],
            },
            {
                "id": "c/pago",
                "pricing": {"prompt": "0.000001", "completion": "0.000002"},
                "supported_parameters": ["tools"],
            },
            {
                "id": "openrouter/free",
                "pricing": {"prompt": "0", "completion": "0"},
                "supported_parameters": ["tools"],
            },
        ]
    }
    assert openrouter.modelos_gratis_com_ferramentas(catalogo) == [
        "a/gratis:free",
        "openrouter/free",
    ]
