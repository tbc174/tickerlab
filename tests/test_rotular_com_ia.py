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
from src import auditoria_rotulos as ar
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
    def __init__(self, tokens_por_evento=4_500, resposta=None, tokens_do_prefixo=1_500):
        self.criados: list[dict] = []
        self.contagens = 0
        self.modelos_contados: set[str] = set()
        self.lotes: list[list] = []
        self.estado = "in_progress"
        self.palpite = "NAO_SEI"
        self._tokens, self._resposta = tokens_por_evento, resposta
        self._prefixo = tokens_do_prefixo
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

    def _contar(self, **pedido):
        self.contagens += 1
        self.modelos_contados.add(pedido["model"])
        sonda = pedido["messages"][0]["content"] == rc.SONDA_DO_PREFIXO
        return SimpleNamespace(input_tokens=self._prefixo if sonda else self._tokens)

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
    assert cliente.contagens == len(EVENTOS) + 1  # amostra de até 50 + o prefixo fixo
    n, prefixo = len(EVENTOS), 1_500
    sonnet = ri.MODELOS[ri.MODELO]
    entrada = (4_500 - prefixo) * n + prefixo * (
        rc.PESO_DA_ESCRITA_NO_CACHE + sonnet.leitura_do_cache * (n - 1)
    )
    esperado = ri.custo_em_dolares(
        round(entrada), sonnet.saida_estimada_por_evento * n, lote=True
    )
    assert estimativa == pytest.approx(esperado)


def test_estimativa_conta_o_cache_do_lote_de_15_10():
    """O lote msgbatch_01WUXkiJ... (2.849 eventos) custou US$ 1,84 de verdade (entrada 570.175, cache
    lido 4.216.952, escrito 7.650, saída 167.640) e foi estimado em US$ 10,72 sem contar o cache. A
    estimativa nova fica acima do real (o teto não pode furar) e a no máximo 30% dele."""
    n = 2_849
    eventos = [{**EVENTOS[0], "id": f"E{i}"} for i in range(n)]
    por_evento = round((570_175 + 4_216_952 + 7_650) / n)
    prefixo = round(4_216_952 / n)
    cliente = ClienteDeMentira(por_evento, tokens_do_prefixo=prefixo)
    estimativa = rc.estimar(cliente, eventos, Path("."), so_fatos=True)
    real = rc._custo_da_resposta(
        SimpleNamespace(
            input_tokens=570_175,
            output_tokens=167_640,
            cache_creation_input_tokens=7_650,
            cache_read_input_tokens=4_216_952,
        ),
        lote=True,
    )
    assert real == pytest.approx(1.84, abs=0.01)
    assert real <= estimativa <= real * 1.3


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


def _lido(texto: str) -> leitura.TextoDoDocumento:
    """O que `leitura.ler_documento` devolveria para um PDF com esse texto ("" = sem texto)."""
    if not texto:
        return leitura.TextoDoDocumento("", "", "O PDF é só imagem.", 1)
    return leitura.TextoDoDocumento(texto, leitura.TEXTO, None, 1)


def test_baixar_para_no_limite_da_cvm(tmp_path, monkeypatch):
    monkeypatch.setattr(
        leitura,
        "ler_documento",
        lambda _: _lido("Texto do documento com várias palavras para ler aqui."),
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
    monkeypatch.setattr(leitura, "ler_documento", lambda _: _lido(""))
    rc.baixar(EVENTOS[:1], tmp_path, maximo=1, obter=lambda _: b"%PDF-%%EOF", pausa=0)
    assert rc.texto_guardado(tmp_path, EVENTOS[0]["id"]) == ""


def test_documento_que_nao_e_pdf_fica_sem_texto_e_a_fila_segue(tmp_path):
    """Um .doc antigo não é o limite da CVM: fica marcado sem texto e o próximo é baixado."""
    doc_antigo = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 100
    respostas = iter([doc_antigo, b"<html>limite</html>"])
    baixados = rc.baixar(
        EVENTOS[:2], tmp_path, maximo=2, obter=lambda _: next(respostas), pausa=0
    )
    assert baixados == 1
    assert rc.texto_guardado(tmp_path, EVENTOS[0]["id"]) == ""
    assert rc.texto_guardado(tmp_path, EVENTOS[1]["id"]) is None  # parou no limite


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
    dois = [EVENTOS[0]["id"], EVENTOS[1]["id"]]
    with pytest.raises(rc.TetoPassado):
        rc.identificar(cliente, EVENTOS, pasta, list(_humanos()), teto=0.0001)
    assert cliente.criados == []
    veredito = rc.identificar(cliente, EVENTOS, pasta, dois, teto=60)
    assert len(cliente.criados) == 2 and veredito.identificadas == 1.0
    assert rc.ler_identificacoes(pasta) == {
        EVENTOS[0]["id"]: True,
        EVENTOS[1]["id"]: True,
    }
    assert "Alfa Beta" not in json.dumps(
        cliente.criados, ensure_ascii=False
    )  # o pedido segue anonimizado
    rc.identificar(cliente, EVENTOS, pasta, dois, teto=60)
    assert len(cliente.criados) == 2  # não repete


def test_identificar_confere_o_teto_pelo_gasto_real_antes_de_cada_envio(pasta):
    """Emenda 2 da ADR 0072: o teto é do gasto real; a estimativa a preço cheio só diz quanto custa
    um envio a mais. Para no envio que passaria do teto e guarda o gasto no manifesto."""
    cliente = ClienteDeMentira()
    um_envio = ri.custo_em_dolares(4_500, rc.SAIDA_POR_IDENTIFICACAO, lote=False)
    real = ri.custo_em_dolares(4_000, 300, lote=False)  # a resposta de mentira
    tres = [e["id"] for e in EVENTOS[:3]]
    with pytest.raises(rc.TetoPassado):
        rc.identificar(cliente, EVENTOS, pasta, tres, teto=real + um_envio / 2)
    assert len(cliente.criados) == 1  # o 1º cabia; o 2º passaria do teto
    manifesto = rc.ler_manifesto(pasta)
    assert manifesto["gasto_em_dolares"] == pytest.approx(real)
    assert manifesto["identificacao"] == {"eventos": 1, "gasto": pytest.approx(real)}
    assert len(rc.ler_identificacoes(pasta)) == 1
    veredito = rc.identificar(cliente, EVENTOS, pasta, tres, teto=60)  # continua
    assert len(cliente.criados) == 3 and not veredito.incompleto


def test_auditar_grava_o_veredito(pasta, monkeypatch):
    cliente = ClienteDeMentira()
    rc.piloto(cliente, EVENTOS, pasta, n=4, teto=60)
    rc.identificar(cliente, EVENTOS, pasta, list(_humanos()), teto=60)
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
    assert rc.ler_eventos(caminho) == [{**EVENTOS[2], "ordem": 0}]
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
        "ler_documento",
        lambda _: _lido("Texto do documento com várias palavras para ler aqui."),
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


def test_enviar_so_os_prontos_e_o_resto_no_proximo_lote(pasta):
    eventos = [FATO, *EVENTOS]  # o fato ainda não tem texto
    cliente = ClienteDeMentira()
    rc.enviar(cliente, eventos, pasta, teto=60, so_fatos=True, so_prontos=True)
    assert [p["custom_id"] for p in cliente.lotes[0]] == [
        rc.chave(e["id"]) for e in EVENTOS
    ]
    cliente.estado = "ended"
    rc.buscar(cliente, eventos, pasta)
    assert (
        rc.enviar(cliente, eventos, pasta, teto=60, so_fatos=True, so_prontos=True)
        is None
    )
    (pasta / "textos" / f"{FATO['id']}.txt").write_text(
        "A empresa anuncia a aquisição.", encoding="utf-8"
    )
    rc.enviar(cliente, eventos, pasta, teto=60, so_fatos=True, so_prontos=True)
    assert [p["custom_id"] for p in cliente.lotes[1]] == [rc.chave(FATO["id"])]


# --- segundo modelo às cegas (Emenda 1 da ADR 0072, 17/10/2026) ---------------------------------

OPUS = ri.MODELO_CONFERENTE


def test_ler_eventos_guarda_a_posicao_na_fila(tmp_path):
    """`ordem` é a posição na página (o evento sem id não desloca os seguintes)."""
    arquivo = tmp_path / "eventos.json"
    fila = [EVENTOS[0], {**EVENTOS[1], "id": ""}, EVENTOS[2]]
    arquivo.write_text(json.dumps({"eventos": fila}), encoding="utf-8")
    assert [e["ordem"] for e in rc.ler_eventos(arquivo)] == [0, 2]


def test_opus_grava_em_arquivo_separado_e_nao_ve_o_sonnet(pasta):
    rc.piloto(ClienteDeMentira(), EVENTOS, pasta, n=2, teto=60)  # Sonnet
    cliente = ClienteDeMentira()
    rc.enviar(cliente, EVENTOS, pasta, teto=10, modelo=OPUS)
    assert [p["custom_id"] for p in cliente.lotes[0]] == [e["id"] for e in EVENTOS]
    assert {p["params"]["model"] for p in cliente.lotes[0]} == {OPUS}
    cliente.estado = "ended"
    assert rc.buscar(cliente, EVENTOS, pasta, modelo=OPUS) == 4
    opus = rc.ler_rotulos(pasta, OPUS)
    assert {r["modelo"] for r in opus.values()} == {OPUS}
    assert all(
        r["por"] == "ia" and len(r["hash_da_entrada"]) == 64 for r in opus.values()
    )
    assert len(rc.ler_rotulos(pasta)) == 2  # o arquivo do Sonnet não mudou
    assert (pasta / f"rotulos.{OPUS}.jsonl").exists()
    manifesto = json.loads(
        (pasta / f"manifesto.{OPUS}.json").read_text(encoding="utf-8")
    )
    assert manifesto["modelo"] == OPUS and manifesto["rotulados"] == 4
    sonnet = json.loads((pasta / "manifesto.json").read_text(encoding="utf-8"))
    assert sonnet["modelo"] == ri.MODELO


def test_teto_do_opus_conta_so_o_gasto_do_opus(pasta):
    """O teto do Opus é outro "pode" (US$ 10 sugeridos): o gasto do Sonnet não entra nele."""
    (pasta / "manifesto.json").write_text(
        json.dumps({"gasto_em_dolares": 59.99, "lotes": []})
    )
    assert rc.enviar(ClienteDeMentira(), EVENTOS, pasta, teto=10, modelo=OPUS)
    (pasta / f"manifesto.{OPUS}.json").write_text(
        json.dumps({"gasto_em_dolares": 9.99, "lotes": []})
    )
    with pytest.raises(rc.TetoPassado):
        rc.piloto(ClienteDeMentira(), EVENTOS, pasta, n=2, teto=10, modelo=OPUS)


def test_estimar_usa_preco_e_cache_do_modelo(pasta):
    cliente = ClienteDeMentira()
    estimativa = rc.estimar(cliente, EVENTOS, pasta, modelo=OPUS)
    assert cliente.modelos_contados == {OPUS}
    opus = ri.MODELOS[OPUS]
    n, prefixo = len(EVENTOS), 1_500
    entrada = (4_500 - prefixo) * n + prefixo * (
        rc.PESO_DA_ESCRITA_NO_CACHE + opus.leitura_do_cache * (n - 1)
    )
    esperado = ri.custo_em_dolares(
        round(entrada), opus.saida_estimada_por_evento * n, modelo=OPUS
    )
    assert estimativa == pytest.approx(esperado)


def test_custo_real_do_opus_le_o_cache_a_5_por_cento():
    usage = SimpleNamespace(input_tokens=0, output_tokens=0,
                            cache_creation_input_tokens=0, cache_read_input_tokens=1_000_000)  # fmt: skip
    # 1 milhão lido do cache: 0,05 x US$ 4, metade no lote = US$ 0,10 (no Sonnet, 0,1 x US$ 2 / 2)
    assert rc._custo_da_resposta(usage, lote=True, modelo=OPUS) == pytest.approx(0.10)
    assert rc._custo_da_resposta(usage, lote=True) == pytest.approx(0.10)


def _fila_com_lote(tmp_path, n=305, lote=(303,)):
    fila = [{**EVENTOS[0], "id": f"E{i}",
             **({"amostra": "lote-leitor-v1", "categoria": "Fato Relevante"} if i in lote else {})}
            for i in range(n)]  # fmt: skip
    arquivo = tmp_path / "eventos.json"
    arquivo.write_text(json.dumps({"eventos": fila}), encoding="utf-8")
    return arquivo


def test_main_estima_o_opus_so_no_conjunto_de_prova(tmp_path, monkeypatch, capsys):
    cliente = ClienteDeMentira()
    monkeypatch.setattr(ri, "cliente", lambda: cliente)
    codigo = rc.main(["estimar", "--eventos", str(_fila_com_lote(tmp_path)),
                      "--pasta", str(tmp_path / "v1"), "--teto-dolares", "10",
                      "--modelo", OPUS, "--so-prova"])  # fmt: skip
    assert codigo == 0
    saida = capsys.readouterr().out
    assert "Pendentes: 301" in saida and OPUS in saida  # 300 primeiros + 1 do lote
    assert cliente.modelos_contados == {OPUS} and cliente.criados == []


@pytest.mark.parametrize("passo", ["identificar", "auditar", "estabilidade"])
def test_identificar_e_auditar_ficam_com_o_sonnet(tmp_path, passo):
    """O teste de identificação, a estabilidade e a auditoria contra o Tiago são do rotulador."""
    codigo = rc.main([passo, "--eventos", str(_fila_com_lote(tmp_path, n=3, lote=())),
                      "--pasta", str(tmp_path / "v1"), "--humanos", "x.json",
                      "--teto-dolares", "10", "--modelo", OPUS])  # fmt: skip
    assert codigo == 2


def _gravar(pasta: Path, eventos: list[dict], modelo: str, rotulos: dict) -> None:
    """Rótulos com o hash da entrada de verdade (os eventos não têm texto baixado: vão só com o
    assunto, como pela regra `--texto-so-nos-fatos`)."""
    por_id = {e["id"]: e for e in eventos}
    linhas = [
        json.dumps({"evento_id": i, "por": "ia", "modelo": modelo, "texto_so_nos_fatos": True,
                    "hash_da_entrada": ri.hash_da_entrada(ri.pedido(por_id[i], "", modelo)), **r})
        for i, r in rotulos.items()
    ]  # fmt: skip
    rc.arquivo_dos_rotulos(pasta, modelo).write_text(
        "\n".join(linhas) + "\n", encoding="utf-8"
    )


def _dois_modelos(tmp_path):
    eventos = rc.ler_eventos(_fila_com_lote(tmp_path))
    pasta = tmp_path / "v1"
    pasta.mkdir()
    temas = ("resultado", "dividendos", "divida", "governanca")
    rotulos = {e["id"]: {"nota": 1 + k % 5, "tema": temas[k % 4], "assunto": None}
               for k, e in enumerate(eventos)}  # fmt: skip
    rotulos["E303"]["assunto"] = "OUTROS"
    _gravar(pasta, eventos, ri.MODELO, rotulos)
    _gravar(pasta, eventos, OPUS, rotulos)
    return eventos, pasta


def test_comparar_grava_o_veredito_e_a_referencia_do_leitor(tmp_path):
    eventos, pasta = _dois_modelos(tmp_path)
    veredito = rc.comparar(pasta, eventos)
    assert veredito.passou and veredito.n == 300
    gravado = json.loads(
        (pasta / "comparacao-modelos.json").read_text(encoding="utf-8")
    )
    assert gravado["passou"] and gravado["modelos"] == [ri.MODELO, OPUS]
    assert gravado["entradas_diferentes"] == []
    assert gravado["lote_do_leitor"]["eventos"] == 1
    referencia = gravado["lote_do_leitor"]["referencia"]
    assert [r["evento_id"] for r in referencia] == ["E303"]
    assert len(gravado["sha256"][OPUS]) == 64


def test_comparar_so_conta_pares_que_leram_o_mesmo_texto(tmp_path):
    """A emenda pede o mesmo texto anonimizado: se o texto do evento mudou entre um modelo e o outro
    (baixado depois, outra regra), o par fica de fora e o veredito fica incompleto."""
    eventos, pasta = _dois_modelos(tmp_path)
    (pasta / "textos").mkdir()
    (pasta / "textos" / "E303.txt").write_text(
        "Texto que chegou depois.", encoding="utf-8"
    )
    opus = rc.ler_rotulos(pasta, OPUS)
    opus["E7"]["hash_da_entrada"] = "0" * 64
    linhas = [json.dumps(r) for r in opus.values()]
    rc.arquivo_dos_rotulos(pasta, OPUS).write_text(
        "\n".join(linhas) + "\n", encoding="utf-8"
    )
    veredito = rc.comparar(pasta, eventos)
    assert veredito.incompleto and not veredito.passou
    gravado = json.loads(
        (pasta / "comparacao-modelos.json").read_text(encoding="utf-8")
    )
    assert gravado["entradas_diferentes"] == ["E7", "E303"]
    assert gravado["lote_do_leitor"]["referencia"] == []


# --- Emenda 1: identificação no conjunto de prova e estabilidade --------------------------------


def _fila_rotulada(tmp_path, n=305, lote=(303,)):
    """A fila de `_fila_com_lote` com um rótulo válido do Sonnet em cada evento (só com o assunto)."""
    eventos = rc.ler_eventos(_fila_com_lote(tmp_path, n, lote))
    pasta = tmp_path / "v1"
    pasta.mkdir()
    _gravar(pasta, eventos, ri.MODELO,
            {e["id"]: {"nota": 2, "tema": "dividendos", "assunto": None} for e in eventos})  # fmt: skip
    return eventos, pasta


def test_identificar_sem_o_tiago_usa_o_conjunto_de_prova(tmp_path):
    eventos, pasta = _fila_rotulada(tmp_path)
    cliente = ClienteDeMentira()
    veredito = rc.identificar(
        cliente, eventos, pasta, rc.ids_de_prova(eventos), teto=60
    )
    assert len(cliente.criados) == 301  # 300 primeiros + 1 do lote do leitor
    assert veredito.passou and veredito.n == 301 and veredito.identificadas == 0
    gravado = json.loads((pasta / "identificacao.json").read_text(encoding="utf-8"))
    assert gravado["passou"] and gravado["n"] == 301 and gravado["modelo"] == ri.MODELO
    assert gravado["limite"] == ar.LIMITES["max_identificadas"]


def test_identificar_le_o_mesmo_documento_que_o_rotulo_leu(tmp_path):
    """O rótulo do Sonnet saiu só com o assunto (regra `--texto-so-nos-fatos`): se o texto chegou
    depois, a identificação continua sem ele, para ler o mesmo documento que o rotulador leu."""
    eventos, pasta = _fila_rotulada(tmp_path, n=300, lote=())
    (pasta / "textos").mkdir()
    (pasta / "textos" / "E0.txt").write_text(
        "Texto que chegou depois.", encoding="utf-8"
    )
    cliente = ClienteDeMentira()
    rc.identificar(cliente, eventos, pasta, ["E0"], teto=60)
    assert "chegou depois" not in cliente.criados[0]["messages"][0]["content"]


def test_estimar_a_identificacao_nao_gasta(tmp_path):
    eventos, pasta = _fila_rotulada(tmp_path)
    cliente = ClienteDeMentira(tokens_por_evento=1_000)
    estimativa = rc.estimar_identificacao(
        cliente, eventos, pasta, rc.ids_de_prova(eventos)
    )
    assert cliente.criados == [] and cliente.contagens == rc.AMOSTRA_DA_ESTIMATIVA
    saida = rc.SAIDA_POR_IDENTIFICACAO
    assert estimativa == pytest.approx(
        ri.custo_em_dolares(1_000 * 301, saida * 301, lote=False)
    )


def test_estabilidade_sorteia_antes_e_grava_em_arquivo_separado(tmp_path):
    eventos, pasta = _fila_rotulada(
        tmp_path, lote=()
    )  # sem fato relevante: o de mentira não dá assunto
    antes = rc.arquivo_dos_rotulos(pasta).read_bytes()
    cliente = ClienteDeMentira()
    medida = rc.estabilidade(cliente, eventos, pasta, teto=60)
    sorteio = json.loads(
        (pasta / "estabilidade-sorteio.json").read_text(encoding="utf-8")
    )
    assert sorteio["semente"] == ar.SEMENTE_DA_ESTABILIDADE
    assert sorteio["eventos"] == ar.sorteio_da_estabilidade(
        eventos, rc.ler_rotulos(pasta)
    )
    assert sorteio["sha256_dos_rotulos"] == hashlib.sha256(antes).hexdigest()
    assert len(cliente.criados) == 100
    assert (
        rc.arquivo_dos_rotulos(pasta).read_bytes() == antes
    )  # o rótulo da fila não muda
    assert len(rc.ler_estabilidade(pasta)) == 100
    # o de mentira responde nota 3 onde o rótulo tem 2: nunca igual, sempre a 1 ponto
    assert (
        medida["pares"] == 100
        and medida["nota_igual"] == 0
        and medida["perto_nota"] == 1
    )
    gravado = json.loads((pasta / "estabilidade.json").read_text(encoding="utf-8"))
    assert gravado["tema_igual"] == 1 and gravado["modelo"] == ri.MODELO
    manifesto = rc.ler_manifesto(pasta)
    assert (
        manifesto["estabilidade"]["eventos"] == 100
        and manifesto["gasto_em_dolares"] > 0
    )


def test_estabilidade_nao_resorteia_nem_paga_de_novo(tmp_path):
    eventos, pasta = _fila_rotulada(tmp_path)
    cliente = ClienteDeMentira()
    rc.estabilidade(cliente, eventos, pasta, teto=60)
    sorteio = (pasta / "estabilidade-sorteio.json").read_text(encoding="utf-8")
    _gravar(pasta, eventos[:50], ri.MODELO,
            {e["id"]: {"nota": 2, "tema": "dividendos", "assunto": None} for e in eventos[:50]})  # fmt: skip
    rc.estabilidade(cliente, eventos, pasta, teto=60)
    assert len(cliente.criados) == 100
    assert (pasta / "estabilidade-sorteio.json").read_text(encoding="utf-8") == sorteio


def test_estabilidade_respeita_o_teto_antes_de_gastar(tmp_path):
    eventos, pasta = _fila_rotulada(tmp_path)
    cliente = ClienteDeMentira()
    with pytest.raises(rc.TetoPassado):
        rc.estabilidade(cliente, eventos, pasta, teto=0.0001)
    assert cliente.criados == []
    assert (
        pasta / "estabilidade-sorteio.json"
    ).exists()  # o sorteio fica escrito antes


def test_estabilidade_pula_o_evento_cuja_entrada_mudou(tmp_path):
    """A segunda rodada tem de ler o mesmo pedido da primeira; se não, o evento fica de fora."""
    eventos, pasta = _fila_rotulada(tmp_path)
    mudado = ar.sorteio_da_estabilidade(eventos, rc.ler_rotulos(pasta))[0]
    rotulos = rc.ler_rotulos(pasta)
    rotulos[mudado]["hash_da_entrada"] = "0" * 64
    rc.arquivo_dos_rotulos(pasta).write_text(
        "\n".join(json.dumps(r) for r in rotulos.values()) + "\n", encoding="utf-8"
    )
    cliente = ClienteDeMentira()
    medida = rc.estabilidade(cliente, eventos, pasta, teto=60)
    assert len(cliente.criados) == 99 and medida["entradas_diferentes"] == [mudado]


def test_main_identifica_e_mede_a_estabilidade_sem_o_tiago(
    tmp_path, monkeypatch, capsys
):
    _, pasta = _fila_rotulada(tmp_path)
    cliente = ClienteDeMentira()
    monkeypatch.setattr(ri, "cliente", lambda: cliente)
    base = ["--eventos", str(tmp_path / "eventos.json"), "--pasta", str(pasta),
            "--teto-dolares", "10"]  # fmt: skip
    for passo in ("identificar", "estabilidade"):
        assert rc.main([passo, *base, "--so-estimar"]) == 0
        assert "Estimativa" in capsys.readouterr().out
    assert cliente.criados == []
    assert rc.main(["identificar", *base]) == 0 and len(cliente.criados) == 301
    assert "PASSOU" in capsys.readouterr().out
    assert rc.main(["estabilidade", *base]) == 0 and len(cliente.criados) == 401
    assert "Nota igual" in capsys.readouterr().out


def _com_erro_de_trecho(pasta: Path, ids: list[str]) -> None:
    """O Sonnet com o trecho juntado (dois campos com " - ") nos `ids`: erro, com a resposta bruta."""
    rotulos = rc.ler_rotulos(pasta)
    for i in ids:
        bruta = {"nota": 1 + int(i[1:]) % 5, "tema": "dividendos", "confianca": "media",
                 "trecho": "Aviso aos Acionistas - Pagamento de dividendos"}  # fmt: skip
        rotulos[i] = {
            k: v for k, v in rotulos[i].items() if k not in ("nota", "tema", "assunto")
        }
        rotulos[i] |= {
            "erro": "trecho não está no documento",
            "resposta_bruta": json.dumps(bruta),
        }
    rc.arquivo_dos_rotulos(pasta).write_text(
        "\n".join(json.dumps(r) for r in rotulos.values()) + "\n", encoding="utf-8"
    )


def test_comparar_conta_os_3_eventos_do_desvio_pela_resposta_bruta(
    tmp_path, monkeypatch
):
    """Desvio registrado (Tiago, 17/10/2026): só nos eventos da lista, o erro de trecho conta pela
    nota e pelo tema da resposta bruta; o rotulos.jsonl não muda (o treino continua sem eles)."""
    eventos, pasta = _dois_modelos(tmp_path)
    _com_erro_de_trecho(pasta, ["E5", "E6"])
    monkeypatch.setattr(ar, "DESVIO_DO_TRECHO", frozenset({"E5"}))
    antes = rc.arquivo_dos_rotulos(pasta).read_bytes()
    veredito = rc.comparar(pasta, eventos)
    assert veredito.incompleto  # o E6 não está na lista: continua faltando
    assert veredito.motivos == [
        "1 eventos sem rótulo válido dos dois modelos: rode os pendentes de novo"
    ]
    gravado = json.loads(
        (pasta / "comparacao-modelos.json").read_text(encoding="utf-8")
    )
    assert gravado["desvios"] == ["E5"]
    assert rc.arquivo_dos_rotulos(pasta).read_bytes() == antes
    monkeypatch.setattr(ar, "DESVIO_DO_TRECHO", frozenset({"E5", "E6"}))
    assert rc.comparar(pasta, eventos).passou


# --- vazamento (v2, 17/10/2026): a conferência sem custo antes do teste de identificação ---


def _fila_com_nomes(tmp_path):
    eventos = [
        {**EVENTOS[0], "id": "A", "empresa": "COSAN S.A.", "categoria": "Fato Relevante"},
        {**EVENTOS[0], "id": "B", "empresa": "CIELO S.A. - INSTITUIÇÃO DE PAGAMENTO",
         "categoria": "Fato Relevante"},
    ]  # fmt: skip
    pasta = tmp_path / "v2"
    (pasta / "textos").mkdir(parents=True)
    (pasta / "textos" / "A.txt").write_text("A Cosan vendeu.", encoding="utf-8")
    (pasta / "textos" / "B.txt").write_text(
        "A Cielo, instituição de pagamento.", encoding="utf-8"
    )
    return eventos, pasta


def test_vazamento_sem_gastar_na_v2_fica_so_a_palavra_comum(tmp_path):
    eventos, pasta = _fila_com_nomes(tmp_path)
    resultado = rc.vazamento(eventos, pasta, ["A", "B"])
    assert resultado["n"] == 2 and resultado["com_palavra_distinta"] == 0
    assert (
        resultado["com_palavra_comum"] == 1
    )  # "instituição" e "pagamento" ficam no texto
    gravado = json.loads((pasta / "vazamento.json").read_text(encoding="utf-8"))
    assert gravado["versao_do_prompt"] == ri.VERSAO_DO_PROMPT and gravado["n"] == 2


def test_vazamento_acha_o_nome_que_escapou(tmp_path, monkeypatch):
    eventos, pasta = _fila_com_nomes(tmp_path)
    monkeypatch.setattr(
        ri, "anonimizar", lambda texto, nomes: texto
    )  # como se nada fosse trocado
    resultado = rc.vazamento(eventos, pasta, ["A", "B"])
    assert resultado["com_palavra_distinta"] == 2
    assert resultado["palavras_distintas"] == {"cosan": 1, "cielo": 1}
    assert resultado["eventos_com_palavra_distinta"] == ["A", "B"]


def test_main_vazamento_nao_chama_a_api(tmp_path, monkeypatch, capsys):
    eventos, pasta = _fila_com_nomes(tmp_path)
    caminho = tmp_path / "eventos.json"
    caminho.write_text(json.dumps({"eventos": eventos}), encoding="utf-8")
    monkeypatch.setattr(ri, "cliente", lambda: pytest.fail("vazamento não usa a API"))
    assert rc.main(["vazamento", "--eventos", str(caminho), "--pasta", str(pasta)]) == 0
    assert "palavra que distingue a empresa: 0" in capsys.readouterr().out


# --- vazamento (v3, 17/10/2026): quantos documentos ganharam cada marcador do conteúdo ---


def test_vazamento_conta_os_marcadores_do_conteudo(tmp_path, monkeypatch):
    eventos, pasta = _fila_com_nomes(tmp_path)
    (pasta / "textos" / "A.txt").write_text(
        "São Paulo, 1 de março de 2025. A Cosan e a Cielo S.A. assinaram.",
        encoding="utf-8",
    )
    monkeypatch.setattr(ri, "OUTRAS_EMPRESAS", ())
    ri.definir_outras_empresas(e["empresa"] for e in eventos)
    resultado = rc.vazamento(eventos, pasta, ["A", "B"])
    assert resultado["documentos_com_marcador"][ri.OUTRA_EMPRESA] == 1
    assert resultado["documentos_com_marcador"][ri.LOCAL] == 1
    assert resultado["documentos_com_marcador"][ri.EMPRESA] == 2


def test_main_define_as_outras_empresas_pelo_cadastro_inteiro(
    tmp_path, monkeypatch, capsys
):
    eventos, pasta = _fila_com_nomes(tmp_path)
    caminho = tmp_path / "eventos.json"
    caminho.write_text(json.dumps({"eventos": eventos}), encoding="utf-8")
    monkeypatch.setattr(ri, "OUTRAS_EMPRESAS", ())
    assert rc.main(["vazamento", "--eventos", str(caminho), "--pasta", str(pasta)]) == 0
    assert set(ri.OUTRAS_EMPRESAS) == {e["empresa"] for e in eventos}
    assert "[OUTRA EMPRESA]" in capsys.readouterr().out
