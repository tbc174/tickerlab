"""O medidor da API externa (linha 567): percentis, resumo, carteiras e o freio de 5xx."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from scripts import medir_api_externa as m


def test_percentil_posto_mais_proximo():
    assert m.percentil([10, 20, 30, 40], 50) == 20
    assert m.percentil([10, 20, 30, 40], 95) == 40
    assert m.percentil([], 50) == 0.0


def test_resumir_conta_codigos_e_vazao():
    r = m.resumir([10, 20], [200, 429], [100, 300], 2.0)
    assert r["codigos"] == {"200": 1, "429": 1}
    assert r["pedidos_por_s"] == 1.0
    assert r["bytes_medio"] == 200


def test_carteiras_giram_pela_lista():
    assert m.carteiras(["a", "b", "c"], 2, 2) == [["a", "b"], ["c", "a"]]
    assert m.carteiras([], 2, 2) == []


def test_freio_de_5xx_para_a_rota():
    tarefas = [lambda: (500, 1.0, 0)] * 200
    r = m.medir_rota("x", tarefas, 1, 0.02, None)
    assert r["parou_antes"] is True
    assert r["pedidos"] < 200


def test_main_contra_servidor_falso_sem_gravar_a_chave(tmp_path, monkeypatch):
    class Falso(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *_args):
            pass

    servidor = HTTPServer(("127.0.0.1", 0), Falso)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    monkeypatch.setenv("TICKERLAB_CHAVE_MEDIDA", "tl_segredo_longo_123")
    saida = tmp_path / "s.json"
    codigo = m.main(
        [
            "--base", f"http://127.0.0.1:{servidor.server_port}",
            "--chamadas", "5",
            "--concorrencia", "2",
            "--saida", str(saida),
        ]
    )  # fmt: skip
    servidor.shutdown()
    assert codigo == 0
    texto = saida.read_text(encoding="utf-8")
    assert "segredo_longo" not in texto
    assert json.loads(texto)["rotas"][0]["pedidos"] == 5
