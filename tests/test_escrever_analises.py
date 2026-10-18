"""O lote que escreve as análises (ADR 0100) com um cliente de mentira: nada vai para a rede.

O que importa: estimar não gasta; nada é enviado acima do teto (contando o que já foi gasto); a
resposta guardada não é paga de novo; cada análise guarda a linhagem inteira; sem a porta 2 nada do
modelo vai ao ar; a porta 3 é uma nota no Obsidian e o veredito conta para o critério de saída.
"""

import copy
import json
import re
from types import SimpleNamespace

import pytest

from scripts import escrever_analises as ea
from src.analise_escrita import pedido, porta2, porta3, saida
from tests.ajudantes_da_analise import PAR_DA_CPFL

ARQUIVO_DA_ENTRADA = PAR_DA_CPFL / "entrada.json"
ENTRADA = json.loads(ARQUIVO_DA_ENTRADA.read_text(encoding="utf-8"))
RESPOSTA = json.loads((PAR_DA_CPFL / "gabarito.json").read_text(encoding="utf-8"))[
    "analise"
]
_ROTULO = re.compile(r"^\[([^\]]+)\] \(", re.MULTILINE)


def _mensagem(texto: str, stop="end_turn", entrada=30_000, saida_=9_000):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=texto)],
        stop_reason=stop,
        usage=SimpleNamespace(input_tokens=entrada, output_tokens=saida_,
                              cache_creation_input_tokens=0, cache_read_input_tokens=0),
    )  # fmt: skip


class ClienteDeMentira:
    """Escreve o gabarito e, na porta 2, dá `sustentada` a tudo (menos às frases de `ruins`)."""

    def __init__(self, ruins: frozenset[str] = frozenset()):
        self.criados: list[dict] = []
        self.lotes: list[list] = []
        self.estado = "in_progress"
        self.ruins = ruins
        self.messages = SimpleNamespace(
            create=self._criar,
            count_tokens=lambda **_: SimpleNamespace(input_tokens=30_000),
            batches=SimpleNamespace(
                create=self._lote, retrieve=self._ver, results=self._resultados
            ),
        )

    def _texto(self, params: dict) -> str:
        if params["output_config"]["format"]["schema"] == porta2.ESQUEMA:
            rotulos = _ROTULO.findall(params["messages"][0]["content"])
            frases = [
                {"frase": r, "motivo": "",
                 "veredito": porta2.FORA_DOS_DADOS if r in self.ruins else porta2.SUSTENTADA}
                for r in rotulos
            ]  # fmt: skip
            return json.dumps({"frases": frases})
        return json.dumps(RESPOSTA, ensure_ascii=False)

    def _criar(self, **params):
        self.criados.append(params)
        return _mensagem(self._texto(params))

    def _lote(self, requests):
        self.lotes.append(list(requests))
        return SimpleNamespace(id=f"lote_{len(self.lotes)}")

    def _ver(self, _id):
        return SimpleNamespace(processing_status=self.estado)

    def _resultados(self, _id):
        for pedido_ in self.lotes[-1]:
            yield SimpleNamespace(
                custom_id=pedido_["custom_id"],
                result=SimpleNamespace(
                    type="succeeded", message=_mensagem(self._texto(pedido_["params"]))
                ),
            )


def _escrita_e_conferida(cliente, pasta, modelo=pedido.SONNET):
    ea.piloto(cliente, [ENTRADA], pasta, [modelo], teto=3)
    ea.cegas(cliente, [ENTRADA], pasta, [modelo], teto=3)
    ea.conferir([ENTRADA], pasta, modelo)
    return json.loads(ea.arquivo_da_analise(pasta, ENTRADA).read_text(encoding="utf-8"))


def _origens(analise: dict) -> dict[str, str]:
    return {p["chave"]: p["origem"] for p in analise["analise"]["partes"]}


def test_estimar_nao_gasta(tmp_path):
    cliente = ClienteDeMentira()
    estimativa = ea.estimar(cliente, [ENTRADA], tmp_path, pedido.ESCRITORES)
    assert cliente.criados == [] and cliente.lotes == []
    assert set(estimativa) == set(pedido.ESCRITORES)
    assert all(custo > 0 for custo in estimativa.values())
    assert (
        estimativa[pedido.HAIKU] < estimativa[pedido.SONNET] < estimativa[pedido.OPUS]
    )


def test_teto_trava_antes_de_gastar(tmp_path):
    cliente = ClienteDeMentira()
    with pytest.raises(ea.TetoPassado):
        ea.piloto(cliente, [ENTRADA], tmp_path, pedido.ESCRITORES, teto=0.01)
    assert cliente.criados == []
    assert not list(tmp_path.rglob("*.json"))


def test_teto_conta_o_que_ja_foi_gasto(tmp_path):
    (tmp_path / "manifesto.json").write_text(json.dumps({"gasto_em_dolares": 2.99}))
    with pytest.raises(ea.TetoPassado):
        ea.piloto(ClienteDeMentira(), [ENTRADA], tmp_path, [pedido.SONNET], teto=3)


def test_resposta_guardada_nao_paga_de_novo(tmp_path):
    cliente = ClienteDeMentira()
    assert ea.piloto(cliente, [ENTRADA], tmp_path, [pedido.SONNET], teto=3) == 1
    gasto = ea.ler_manifesto(tmp_path)["gasto_em_dolares"]
    assert ea.piloto(cliente, [ENTRADA], tmp_path, [pedido.SONNET], teto=3) == 0
    assert len(cliente.criados) == 1
    assert ea.ler_manifesto(tmp_path)["gasto_em_dolares"] == gasto
    nova = copy.deepcopy(ENTRADA)
    nova["linhas"][0]["texto"] = "CPFL ENERGIA S/A"
    assert ea.piloto(cliente, [nova], tmp_path, [pedido.SONNET], teto=3) == 1


def test_linhagem_completa(tmp_path):
    analise = _escrita_e_conferida(ClienteDeMentira(), tmp_path)
    linhagem = analise["linhagem"]
    assert linhagem["modelo"] == pedido.SONNET
    assert linhagem["versao_do_guia"] == pedido.VERSAO_DO_GUIA
    assert linhagem["versao_do_molde"] >= 1
    assert len(linhagem["hash_da_entrada"]) == 64
    assert json.loads(linhagem["resposta_bruta"]) == RESPOSTA
    assert linhagem["tokens"]["entrada"] == 30_000
    assert linhagem["custo_em_dolares"] > 0
    assert linhagem["porta1"] == []
    assert linhagem["porta2"]["conferente"] == pedido.OPUS
    assert linhagem["porta2"]["reprovadas"] == []
    assert linhagem["porta3"] is None
    assert set(_origens(analise).values()) == {saida.ORIGEM_MODELO}
    assert analise["publicavel"] is False  # a porta 3 é total: só vai ao ar o aprovado


def test_sem_a_porta_2_nada_do_modelo_vai_ao_ar(tmp_path):
    cliente = ClienteDeMentira()
    ea.piloto(cliente, [ENTRADA], tmp_path, [pedido.SONNET], teto=3)
    ea.conferir([ENTRADA], tmp_path, pedido.SONNET)
    analise = json.loads(ea.arquivo_da_analise(tmp_path, ENTRADA).read_text("utf-8"))
    assert set(_origens(analise).values()) == {saida.ORIGEM_MOLDE}
    assert analise["linhagem"]["porta2"] is None


def test_frase_reprovada_na_porta_2_manda_a_parte_ao_molde(tmp_path):
    cliente = ClienteDeMentira(ruins=frozenset({"dinheiro.1.1"}))
    origens = _origens(_escrita_e_conferida(cliente, tmp_path))
    assert origens.pop("dinheiro") == saida.ORIGEM_MOLDE
    assert set(origens.values()) == {saida.ORIGEM_MODELO}


def test_lote_envia_e_busca(tmp_path):
    cliente = ClienteDeMentira()
    assert ea.enviar(cliente, [ENTRADA], tmp_path, pedido.SONNET, teto=3) == "lote_1"
    with pytest.raises(RuntimeError, match="buscar"):
        ea.enviar(cliente, [ENTRADA], tmp_path, pedido.SONNET, teto=3)
    assert ea.buscar(cliente, [ENTRADA], tmp_path) == 0  # ainda processando
    cliente.estado = "ended"
    assert ea.buscar(cliente, [ENTRADA], tmp_path) == 1
    resposta = ea.resposta_guardada(tmp_path, ENTRADA, pedido.SONNET)
    assert resposta is not None and resposta["origem"] == "lote lote_1"
    assert ea.enviar(cliente, [ENTRADA], tmp_path, pedido.SONNET, teto=3) is None
    assert cliente.criados == []


def test_revisar_escreve_a_nota_do_obsidian(tmp_path):
    _escrita_e_conferida(ClienteDeMentira(), tmp_path)
    notas = tmp_path / "revisao"
    (arquivo,) = ea.revisar([ENTRADA], tmp_path, notas)
    texto = arquivo.read_text(encoding="utf-8")
    assert porta3.propriedades(texto)["tipo"] == "revisao"
    assert porta3.propriedades(texto)["situacao"] == porta3.ESPERANDO
    arquivo.write_text(texto + "\nanotação do Tiago\n", encoding="utf-8")
    assert ea.revisar([ENTRADA], tmp_path, notas) == []  # nunca sobrescreve a nota
    assert "anotação do Tiago" in arquivo.read_text(encoding="utf-8")


def test_aprovar_conta_o_criterio_de_saida(tmp_path):
    _escrita_e_conferida(ClienteDeMentira(), tmp_path)
    notas = tmp_path / "revisao"
    (arquivo,) = ea.revisar([ENTRADA], tmp_path, notas)
    texto = arquivo.read_text(encoding="utf-8")
    arquivo.write_text(
        texto.replace("veredito: \n", "veredito: aprovado\n", 1), encoding="utf-8"
    )
    saida_ = ea.aprovar(tmp_path, notas)
    assert (saida_.seguidos, saida_.por_tom, saida_.atingido) == (1, 0, False)
    analise = json.loads(ea.arquivo_da_analise(tmp_path, ENTRADA).read_text("utf-8"))
    assert analise["linhagem"]["porta3"]["veredito"] == porta3.APROVADO
    assert analise["publicavel"] is True
    assert (
        ea.aprovar(tmp_path, notas).seguidos == 1
    )  # o mesmo veredito não conta duas vezes


def test_passos_que_gastam_exigem_o_teto(tmp_path):
    for passo in ("estimar", "piloto", "enviar", "cegas"):
        with pytest.raises(SystemExit):
            ea.main(
                [passo, "--entradas", str(ARQUIVO_DA_ENTRADA), "--pasta", str(tmp_path)]
            )


def test_main_estimar_mostra_o_custo_sem_gastar(tmp_path, monkeypatch, capsys):
    cliente = ClienteDeMentira()
    monkeypatch.setattr(ea.ri, "cliente", lambda: cliente)
    argumentos = ["estimar", "--entradas", str(ARQUIVO_DA_ENTRADA)]
    assert ea.main([*argumentos, "--pasta", str(tmp_path), "--teto-dolares", "3"]) == 0
    assert "US$" in capsys.readouterr().out
    assert cliente.criados == []
