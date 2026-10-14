"""O script da rotulagem por IA (ADR 0072) com um cliente de mentira: nada vai para a rede.

O que importa: estimar não gasta, nada é enviado acima do teto (contando o que já foi gasto), cada
resposta fica guardada com a entrada em hash, o que já foi feito não é pago de novo e o script nunca
encosta na página das 21h.
"""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import rotular_com_ia as rc
from src import leitura
from src import rotulos_ia as ri

EVENTOS = [
    {"id": f"0001IPE{i:02d}-1", "empresa": "ALFA BETA PARTICIPACOES S.A", "setor": "Energia",
     "entrega": f"2024-01-0{i + 1}", "categoria": "Aviso aos Acionistas", "tipo": "",
     "especie": "", "assunto": f"Pagamento de dividendos {i}", "link": f"https://cvm/{i}"}
    for i in range(4)
]  # fmt: skip


def _mensagem(texto: str, stop="end_turn", entrada=4_000, saida=300):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=texto)],
        stop_reason=stop,
        usage=SimpleNamespace(input_tokens=entrada, output_tokens=saida,
                              cache_creation_input_tokens=0, cache_read_input_tokens=0),
    )  # fmt: skip


def _resposta_para(params: dict) -> str:
    conteudo = params["messages"][0]["content"]
    assunto = next(
        linha for linha in conteudo.splitlines() if linha.startswith("Assunto: ")
    )
    return json.dumps({"nota": 3, "tema": "dividendos", "confianca": "alta",
                       "trecho": assunto.removeprefix("Assunto: ")})  # fmt: skip


class ClienteDeMentira:
    def __init__(self, tokens_por_evento=4_500, resposta=None):
        self.criados: list[dict] = []
        self.contagens = 0
        self.lotes: list[list] = []
        self.estado = "in_progress"
        self.palpite = "NAO_SEI"
        self._tokens, self._resposta = tokens_por_evento, resposta
        self.messages = SimpleNamespace(
            create=self._criar,
            count_tokens=self._contar,
            batches=SimpleNamespace(
                create=self._lote, retrieve=self._ver, results=self._resultados
            ),
        )

    def _criar(self, **params):
        self.criados.append(params)
        if "empresa" in params["output_config"]["format"]["schema"]["properties"]:
            return _mensagem(json.dumps({"empresa": self.palpite}))
        return _mensagem(self._resposta or _resposta_para(params))

    def _contar(self, **_):
        self.contagens += 1
        return SimpleNamespace(input_tokens=self._tokens)

    def _lote(self, requests):
        self.lotes.append(list(requests))
        return SimpleNamespace(id=f"lote_{len(self.lotes)}")

    def _ver(self, _id):
        return SimpleNamespace(processing_status=self.estado)

    def _resultados(self, _id):
        for pedido in self.lotes[-1]:
            yield SimpleNamespace(
                custom_id=pedido["custom_id"],
                result=SimpleNamespace(
                    type="succeeded",
                    message=_mensagem(_resposta_para(pedido["params"])),
                ),
            )


@pytest.fixture
def pasta(tmp_path: Path) -> Path:
    textos = tmp_path / "textos"
    textos.mkdir()
    for e in EVENTOS:
        (textos / f"{e['id']}.txt").write_text(
            "A Alfa Beta Participacoes paga dividendos.", encoding="utf-8"
        )
    return tmp_path


def test_estimar_nao_gasta(pasta):
    cliente = ClienteDeMentira()
    estimativa = rc.estimar(cliente, EVENTOS, pasta)
    assert cliente.criados == [] and cliente.lotes == []
    assert cliente.contagens == len(EVENTOS)  # amostra de até 50
    esperado = ri.custo_em_dolares(
        4_500 * 4, ri.SAIDA_ESTIMADA_POR_EVENTO * 4, lote=True
    )
    assert estimativa == pytest.approx(esperado)


def test_para_se_estimativa_passa_do_teto(pasta):
    cliente = ClienteDeMentira()
    with pytest.raises(rc.TetoPassado):
        rc.enviar(cliente, EVENTOS, pasta, teto=0.001)
    with pytest.raises(rc.TetoPassado):
        rc.piloto(cliente, EVENTOS, pasta, n=2, teto=0.001)
    assert cliente.lotes == [] and cliente.criados == []


def test_teto_conta_o_que_ja_foi_gasto(pasta):
    (pasta / "manifesto.json").write_text(
        json.dumps({"gasto_em_dolares": 59.99, "lotes": []})
    )
    with pytest.raises(rc.TetoPassado):
        rc.enviar(ClienteDeMentira(), EVENTOS, pasta, teto=60)


def test_grava_jsonl_e_manifesto_com_sha256(pasta):
    assert rc.piloto(ClienteDeMentira(), EVENTOS, pasta, n=2, teto=60) == 2
    linhas = (pasta / "rotulos.jsonl").read_text(encoding="utf-8").splitlines()
    registros = [json.loads(linha) for linha in linhas]
    assert [r["por"] for r in registros] == ["ia", "ia"]
    assert all(
        r["modelo"] == ri.MODELO and len(r["hash_da_entrada"]) == 64 for r in registros
    )
    assert all(r["resposta_bruta"] and r["tinha_texto"] for r in registros)
    manifesto = json.loads((pasta / "manifesto.json").read_text(encoding="utf-8"))
    assert (
        manifesto["sha256_do_jsonl"]
        == hashlib.sha256((pasta / "rotulos.jsonl").read_bytes()).hexdigest()
    )
    assert manifesto["rotulados"] == 2 and manifesto["gasto_em_dolares"] > 0


def test_o_texto_enviado_nao_tem_o_nome_da_empresa(pasta):
    cliente = ClienteDeMentira()
    rc.piloto(cliente, EVENTOS, pasta, n=1, teto=60)
    assert "Alfa Beta" not in json.dumps(cliente.criados, ensure_ascii=False)


def test_retoma_sem_repetir_os_ja_feitos(pasta):
    cliente = ClienteDeMentira()
    rc.piloto(cliente, EVENTOS, pasta, n=2, teto=60)
    rc.enviar(cliente, EVENTOS, pasta, teto=60)
    enviados = [p["custom_id"] for p in cliente.lotes[0]]
    assert enviados == [EVENTOS[2]["id"], EVENTOS[3]["id"]]


def test_resposta_com_erro_volta_para_a_fila(pasta):
    rc.piloto(ClienteDeMentira(resposta="não é json"), EVENTOS, pasta, n=1, teto=60)
    registro = rc.ler_rotulos(pasta)[EVENTOS[0]["id"]]
    assert "erro" in registro and registro["resposta_bruta"] == "não é json"
    assert EVENTOS[0] in rc.pendentes(EVENTOS, pasta)


def test_buscar_grava_quando_o_lote_termina(pasta):
    cliente = ClienteDeMentira()
    rc.enviar(cliente, EVENTOS, pasta, teto=60)
    with pytest.raises(RuntimeError, match="buscar"):
        rc.enviar(cliente, EVENTOS, pasta, teto=60)  # lote pendente
    assert rc.buscar(cliente, EVENTOS, pasta) == 0  # ainda processando
    cliente.estado = "ended"
    assert rc.buscar(cliente, EVENTOS, pasta) == 4
    manifesto = rc.ler_manifesto(pasta)
    assert manifesto["lotes"][0]["estado"] == "gravado" and manifesto["rotulados"] == 4
    assert rc.pendentes(EVENTOS, pasta) == []
    assert rc.enviar(cliente, EVENTOS, pasta, teto=60) is None  # nada mais a pagar


def test_enviar_recusa_sem_texto_baixado(pasta):
    (pasta / "textos" / f"{EVENTOS[0]['id']}.txt").unlink()
    with pytest.raises(RuntimeError, match="baixar"):
        rc.enviar(ClienteDeMentira(), EVENTOS, pasta, teto=60)
    assert rc.enviar(
        ClienteDeMentira(), EVENTOS, pasta, teto=60, permitir_sem_texto=True
    )


def test_baixar_para_no_limite_da_cvm(tmp_path, monkeypatch):
    monkeypatch.setattr(
        leitura,
        "texto_do_pdf",
        lambda _: "Texto do documento com várias palavras para ler aqui.",
    )
    respostas = iter(
        [
            b"%PDF-1.4 ... %%EOF",
            b"%PDF-1.4 ... %%EOF",
            b"<html>limite</html>",
            b"%PDF-%%EOF",
        ]
    )
    baixados = rc.baixar(
        EVENTOS, tmp_path, maximo=10, obter=lambda _: next(respostas), pausa=0
    )
    assert baixados == 2
    assert rc.texto_guardado(tmp_path, EVENTOS[0]["id"]).startswith(
        "Texto do documento"
    )
    assert rc.texto_guardado(tmp_path, EVENTOS[2]["id"]) is None  # fica para a próxima


def test_pdf_sem_texto_fica_marcado(tmp_path, monkeypatch):
    monkeypatch.setattr(leitura, "texto_do_pdf", lambda _: "")
    rc.baixar(EVENTOS[:1], tmp_path, maximo=1, obter=lambda _: b"%PDF-%%EOF", pausa=0)
    assert rc.texto_guardado(tmp_path, EVENTOS[0]["id"]) == ""


def test_script_nao_escreve_na_pagina():
    for modulo in (rc, ri):
        fonte = Path(modulo.__file__).read_text(encoding="utf-8").lower()
        assert "claude.ai/artifact" not in fonte and "artifactdata" not in fonte


def test_main_exige_o_teto(pasta, tmp_path):
    caminho = tmp_path / "eventos.json"
    caminho.write_text(json.dumps({"eventos": EVENTOS}), encoding="utf-8")
    assert rc.main(["estimar", "--eventos", str(caminho), "--pasta", str(pasta)]) == 2


# --- identificar e auditar ---------------------------------------------------------------------


def _humanos(n=None):
    return {e["id"]: {"evento_id": e["id"], "nota": 3, "tema": "dividendos", "assunto": None}
            for e in EVENTOS[:n]}  # fmt: skip


def test_identificar_grava_o_palpite_e_respeita_o_teto(pasta):
    cliente = ClienteDeMentira()
    cliente.palpite = "Alfa Beta"
    with pytest.raises(rc.TetoPassado):
        rc.identificar(cliente, EVENTOS, pasta, _humanos(), teto=0.0001)
    assert rc.identificar(cliente, EVENTOS, pasta, _humanos(2), teto=60) == 2
    assert rc.ler_identificacoes(pasta) == {
        EVENTOS[0]["id"]: True,
        EVENTOS[1]["id"]: True,
    }
    assert "Alfa Beta" not in json.dumps(
        cliente.criados, ensure_ascii=False
    )  # o pedido segue anonimizado
    assert (
        rc.identificar(cliente, EVENTOS, pasta, _humanos(2), teto=60) == 0
    )  # não repete


def test_auditar_grava_o_veredito(pasta, monkeypatch):
    cliente = ClienteDeMentira()
    rc.piloto(cliente, EVENTOS, pasta, n=4, teto=60)
    rc.identificar(cliente, EVENTOS, pasta, _humanos(), teto=60)
    veredito = rc.auditar(pasta, _humanos())
    assert veredito.incompleto  # só 4 eventos de prova: não decide
    salvo = json.loads((pasta / "auditoria.json").read_text(encoding="utf-8"))
    assert (
        salvo["passou"] is False
        and salvo["n"] == 4
        and salvo["limites"]["min_eventos"] == 300
    )


def test_ler_humanos_aceita_lista_ou_objeto(tmp_path):
    rotulos = list(_humanos().values())
    (tmp_path / "a.json").write_text(json.dumps(rotulos), encoding="utf-8")
    (tmp_path / "b.json").write_text(json.dumps({"rotulos": rotulos}), encoding="utf-8")
    assert (
        rc.ler_humanos(tmp_path / "a.json")
        == rc.ler_humanos(tmp_path / "b.json")
        == _humanos()
    )


def test_main_auditar_exige_os_rotulos_humanos(pasta, tmp_path):
    caminho = tmp_path / "eventos.json"
    caminho.write_text(json.dumps({"eventos": EVENTOS}), encoding="utf-8")
    assert rc.main(["auditar", "--eventos", str(caminho), "--pasta", str(pasta)]) == 2


def test_id_fora_do_formato_nao_vira_caminho(tmp_path):
    ruins = [
        {**EVENTOS[0], "id": ""},
        {**EVENTOS[1], "id": EVENTOS[2]["id"]},
    ]  # sem id e repetido
    caminho = tmp_path / "eventos.json"
    caminho.write_text(json.dumps({"eventos": [EVENTOS[2], *ruins]}), encoding="utf-8")
    assert rc.ler_eventos(caminho) == [EVENTOS[2]]
    assert rc.chave("../../fora") == "______fora"
    assert rc.chave("22616 IPE1401-54") == "22616_IPE1401-54"


def test_id_com_espaco_vai_e_volta_do_lote(pasta):
    eventos = [{**EVENTOS[0], "id": "0001 IPE00-1"}]
    (pasta / "textos" / "0001_IPE00-1.txt").write_text(
        "A Alfa Beta paga dividendos.", encoding="utf-8"
    )
    cliente = ClienteDeMentira()
    rc.enviar(cliente, eventos, pasta, teto=60)
    assert cliente.lotes[0][0]["custom_id"] == "0001_IPE00-1"
    cliente.estado = "ended"
    rc.buscar(cliente, eventos, pasta)
    assert "0001 IPE00-1" in rc.ler_rotulos(pasta)


# --- texto só nos fatos relevantes (Tiago, 14/10/2026) ------------------------------------------

FATO = {
    **EVENTOS[0],
    "id": "0001IPE99-1",
    "categoria": "Fato Relevante",
    "assunto": "Aquisição",
}


def test_baixar_fatos_relevantes_primeiro(tmp_path, monkeypatch):
    monkeypatch.setattr(
        leitura,
        "texto_do_pdf",
        lambda _: "Texto do documento com várias palavras para ler aqui.",
    )
    pedidos = []
    rc.baixar(
        [*EVENTOS, FATO],
        tmp_path,
        maximo=1,
        obter=lambda url: pedidos.append(url) or b"%PDF-%%EOF",
        pausa=0,
    )
    assert pedidos == [FATO["link"]]


def test_texto_so_nos_fatos_manda_os_outros_so_com_o_assunto(pasta):
    eventos = [*EVENTOS, FATO]
    (pasta / "textos" / f"{EVENTOS[0]['id']}.txt").unlink()  # aviso sem texto baixado
    (pasta / "textos" / f"{FATO['id']}.txt").write_text(
        "A empresa anuncia a aquisição.", encoding="utf-8"
    )
    cliente = ClienteDeMentira()
    with pytest.raises(RuntimeError, match="baixar"):
        rc.enviar(cliente, eventos, pasta, teto=60)  # sem a regra, falta texto
    rc.enviar(cliente, eventos, pasta, teto=60, so_fatos=True)
    conteudos = {
        p["custom_id"]: p["params"]["messages"][0]["content"] for p in cliente.lotes[0]
    }
    assert (
        ri.SEM_TEXTO in conteudos[rc.chave(EVENTOS[1]["id"])]
    )  # o aviso foi só com o assunto
    assert "aquisição" in conteudos[rc.chave(FATO["id"])]  # o fato foi com o texto
    assert rc.ler_manifesto(pasta)["lotes"][0]["texto_so_nos_fatos"] is True


def test_buscar_confere_o_trecho_pela_mesma_regra(pasta):
    eventos = [EVENTOS[1]]
    cliente = ClienteDeMentira()
    rc.enviar(cliente, eventos, pasta, teto=60, so_fatos=True)
    cliente.estado = "ended"
    rc.buscar(cliente, eventos, pasta)
    registro = rc.ler_rotulos(pasta)[EVENTOS[1]["id"]]
    assert "erro" not in registro
    assert registro["tinha_texto"] is False and registro["texto_so_nos_fatos"] is True


def test_piloto_so_com_eventos_prontos_pela_regra(pasta):
    eventos = [FATO, *EVENTOS]  # o fato vem primeiro, mas não tem o texto baixado
    (pasta / "textos" / f"{EVENTOS[0]['id']}.txt").unlink()
    cliente = ClienteDeMentira()
    rc.piloto(cliente, eventos, pasta, n=10, teto=60)
    assert set(rc.ler_rotulos(pasta)) == {
        e["id"] for e in EVENTOS[1:]
    }  # sem regra: só os com texto
    rc.piloto(cliente, eventos, pasta, n=10, teto=60, so_fatos=True)
    assert EVENTOS[0]["id"] in rc.ler_rotulos(pasta)  # aviso só pelo assunto
    assert FATO["id"] not in rc.ler_rotulos(pasta)  # fato sem texto continua esperando
