"""O script que escolhe os gráficos (plano de 23/10/2026) com um cliente de mentira: nada vai à rede.

O que importa: estimar não gasta; nada é enviado acima do teto (contando o que já foi gasto); a
resposta guardada não é paga de novo; o texto de outra ficha fica de fora; sem a porta 2 só a reserva
vai ao ar; o item que a porta 2 reprova sai e a reserva completa o mínimo.
"""

import copy
import json
import re
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from scripts import escolher_graficos as eg
from scripts import escrever_analises as ea
from src.analise_escrita import entrada as en
from src.analise_escrita import graficos as gr
from src.analise_escrita import pedido, saida
from src.analise_escrita import porta2_dos_graficos as p2g
from src.analise_escrita import reserva_dos_graficos as rg
from tests.ajudantes_da_analise import PAR_DA_CPFL

ARQUIVO_DA_ENTRADA = PAR_DA_CPFL / "entrada.json"
ENTRADA = json.loads(ARQUIVO_DA_ENTRADA.read_text(encoding="utf-8"))
TEXTO = json.loads((PAR_DA_CPFL / "gabarito.json").read_text(encoding="utf-8"))[
    "analise"
]
_ROTULO = re.compile(r"^\[((?:grafico|destaque)\.\d+)\] ", re.MULTILINE)


def _do_modelo(tabela: str, tipo: str, eixo: str, coluna: str, parte: str) -> dict:
    return {
        "tipo": tipo, "tabela": tabela, "eixo": eixo, "colunas": [coluna],
        "titulo": "Um gráfico", "parte": parte, "paragrafo": 0,
        "por_que": {"texto": "A ficha traz a tabela.", "notas": [f"{tabela}.0"]},
    }  # fmt: skip


ESCOLHA = {
    "graficos": [
        _do_modelo("ofertas_e_fundos.fundos_por_mes", "linha_no_tempo", "Mês",
                   "Fundos", "quem_manda"),
        _do_modelo("negocios.negocios_por_ano", "barras_no_tempo", "Ano",
                   "Documentos", "o_que_mudou"),
    ],
    "destaques": [
        {"secao": "resultado", "parte": "o_que_os_numeros_mostram",
         "por_que": {"texto": "A cascata mostra os passos.",
                     "notas": ["resultado.cascata.0"]}},
    ],
}  # fmt: skip


def _mensagem(texto: str, stop="end_turn"):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=texto)],
        stop_reason=stop,
        usage=SimpleNamespace(input_tokens=30_000, output_tokens=2_000,
                              cache_creation_input_tokens=0, cache_read_input_tokens=0),
    )  # fmt: skip


class ClienteDeMentira:
    """Escolhe `ESCOLHA` e, na porta 2, dá `mostra` a tudo (menos aos rótulos de `ruins`)."""

    def __init__(
        self, ruins: frozenset[str] = frozenset(), resposta: str | None = None
    ):
        self.ruins = ruins
        self.resposta = (
            json.dumps(ESCOLHA, ensure_ascii=False) if resposta is None else resposta
        )
        self.criados: list[dict] = []
        self.messages = SimpleNamespace(
            stream=self._fluxo,
            count_tokens=lambda **_: SimpleNamespace(input_tokens=30_000),
        )

    def _texto(self, params: dict) -> str:
        if params["output_config"]["format"]["schema"] == p2g.ESQUEMA:
            rotulos = _ROTULO.findall(params["messages"][0]["content"])
            itens = [
                {"item": r, "motivo": "",
                 "veredito": p2g.NAO_MOSTRA if r in self.ruins else p2g.MOSTRA}
                for r in rotulos
            ]  # fmt: skip
            return json.dumps({"itens": itens})
        return self.resposta

    @contextmanager
    def _fluxo(self, **params):
        self.criados.append(params)
        yield SimpleNamespace(get_final_message=lambda: _mensagem(self._texto(params)))


@pytest.fixture
def analises(tmp_path):
    """A pasta do `escrever_analises` com o texto da CPFL já montado."""
    pasta = tmp_path / "texto"
    ea._gravar(
        ea.arquivo_da_analise(pasta, ENTRADA),
        {"hash_da_entrada_atual": en.hash_da_entrada(ENTRADA), "analise": TEXTO},
    )
    return pasta


def _montado(cliente, analises, pasta, modelo=pedido.SONNET, cegas=True) -> dict:
    eg.piloto(cliente, [ENTRADA], analises, pasta, [modelo], teto=2)
    if cegas:
        eg.cegas(cliente, [ENTRADA], analises, pasta, [modelo], teto=2)
    eg.conferir([ENTRADA], analises, pasta, [modelo])
    arquivo = eg.arquivo_dos_graficos(pasta, ENTRADA, modelo)
    return json.loads(arquivo.read_text(encoding="utf-8"))


def _origens(montado: dict) -> list[str]:
    return [g["origem"] for g in montado["escolha"]["graficos"]]


def test_estimar_nao_gasta(analises, tmp_path):
    cliente = ClienteDeMentira()
    modelos = [pedido.HAIKU, pedido.SONNET, pedido.OPUS]
    custos = eg.estimar(cliente, [ENTRADA], analises, tmp_path / "g", modelos)
    assert cliente.criados == []
    # a escolha e a porta 2: o Sonnet julgado pelo Opus custa o que o Opus julgado pelo Sonnet
    assert 0 < custos[pedido.HAIKU] < custos[pedido.SONNET] == custos[pedido.OPUS]


def test_teto_trava_antes_de_gastar(analises, tmp_path):
    cliente = ClienteDeMentira()
    with pytest.raises(eg.TetoPassado):
        eg.piloto(
            cliente, [ENTRADA], analises, tmp_path / "g", [pedido.SONNET], teto=0.01
        )
    assert cliente.criados == []
    assert not (tmp_path / "g").exists()


def test_teto_conta_o_que_ja_foi_gasto(analises, tmp_path):
    pasta = tmp_path / "g"
    pasta.mkdir()
    (pasta / "manifesto.json").write_text(json.dumps({"gasto_em_dolares": 1.99}))
    with pytest.raises(eg.TetoPassado):
        eg.piloto(
            ClienteDeMentira(), [ENTRADA], analises, pasta, [pedido.SONNET], teto=2
        )


def test_resposta_guardada_nao_paga_de_novo(analises, tmp_path):
    cliente, pasta = ClienteDeMentira(), tmp_path / "g"
    assert eg.piloto(cliente, [ENTRADA], analises, pasta, [pedido.SONNET], teto=2) == 1
    gasto = eg.ler_manifesto(pasta)["gasto_em_dolares"]
    assert gasto > 0
    assert eg.piloto(cliente, [ENTRADA], analises, pasta, [pedido.SONNET], teto=2) == 0
    assert eg.cegas(cliente, [ENTRADA], analises, pasta, [pedido.SONNET], teto=2) == 1
    assert eg.cegas(cliente, [ENTRADA], analises, pasta, [pedido.SONNET], teto=2) == 0
    assert len(cliente.criados) == 2


def test_texto_de_outra_ficha_fica_de_fora(analises, tmp_path):
    outra = copy.deepcopy(ENTRADA)
    outra["linhas"][0]["texto"] = "CPFL ENERGIA S/A"  # mesma chave, outra ficha
    cliente = ClienteDeMentira()
    assert (
        eg.piloto(cliente, [outra], analises, tmp_path / "g", [pedido.SONNET], teto=2)
        == 0
    )
    assert cliente.criados == []


def test_sem_a_porta_2_so_a_reserva(analises, tmp_path):
    montado = _montado(ClienteDeMentira(), analises, tmp_path / "g", cegas=False)
    assert set(_origens(montado)) == {rg.ORIGEM_REGRAS}
    assert montado["escolha"]["destaques"] == []
    assert montado["linhagem"]["porta2"] is None
    assert montado["linhagem"]["escolha_do_modelo"] is not None


def test_com_a_porta_2_a_escolha_do_modelo_vai_ao_ar(analises, tmp_path):
    montado = _montado(ClienteDeMentira(), analises, tmp_path / "g")
    assert _origens(montado) == [saida.ORIGEM_MODELO] * 2
    assert len(montado["escolha"]["destaques"]) == 1
    linhagem = montado["linhagem"]
    assert linhagem["porta1"] == []
    assert linhagem["porta2"]["conferente"] == pedido.OPUS  # o Sonnet não julga a si
    assert linhagem["porta2"]["reprovados"] == []
    assert linhagem["custo_em_dolares"] > 0


def test_reprovado_na_porta_2_da_lugar_a_reserva(analises, tmp_path):
    cliente = ClienteDeMentira(ruins=frozenset({"grafico.1", "destaque.0"}))
    montado = _montado(cliente, analises, tmp_path / "g")
    assert _origens(montado) == [saida.ORIGEM_MODELO, rg.ORIGEM_REGRAS]
    assert montado["escolha"]["destaques"] == []
    assert montado["linhagem"]["porta2"]["reprovados"] == ["destaque.0", "grafico.1"]


def test_resposta_fora_do_formato_nao_vai_a_porta_2(analises, tmp_path):
    cliente = ClienteDeMentira(resposta='{"graficos": "nenhum"}')
    montado = _montado(cliente, analises, tmp_path / "g")
    assert len(cliente.criados) == 1  # só a escolha; a porta 2 não gasta com ela
    assert set(_origens(montado)) == {rg.ORIGEM_REGRAS}
    assert "gráficos" in montado["linhagem"]["motivo"]
    assert len(montado["escolha"]["graficos"]) == gr.MINIMO_DE_GRAFICOS


def test_passos_que_gastam_exigem_o_teto(analises, tmp_path):
    for passo in eg.GASTAM:
        with pytest.raises(SystemExit):
            eg.main([passo, "--entradas", str(ARQUIVO_DA_ENTRADA),
                     "--analises", str(analises), "--pasta", str(tmp_path / "g")])  # fmt: skip


def test_main_estimar_mostra_o_custo_sem_gastar(
    analises, tmp_path, monkeypatch, capsys
):
    cliente = ClienteDeMentira()
    monkeypatch.setattr(eg.ri, "cliente", lambda: cliente)
    argumentos = [
        "estimar",
        "--entradas",
        str(ARQUIVO_DA_ENTRADA),
        "--analises",
        str(analises),
    ]
    assert (
        eg.main([*argumentos, "--pasta", str(tmp_path / "g"), "--teto-dolares", "2"])
        == 0
    )
    assert "cabe no teto" in capsys.readouterr().out
    assert cliente.criados == []


def test_main_conferir_nao_usa_a_api(analises, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        eg.ri, "cliente", lambda: pytest.fail("conferir não chama a API")
    )
    argumentos = [
        "conferir",
        "--entradas",
        str(ARQUIVO_DA_ENTRADA),
        "--analises",
        str(analises),
    ]
    assert eg.main([*argumentos, "--pasta", str(tmp_path / "g")]) == 0
    assert "1 escolhas montadas" in capsys.readouterr().out
