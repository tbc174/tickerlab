"""Linha de comando do arquivista (scripts/arquivar_fontes.py)."""

import socket
import threading

import pytest
import requests

from base.arquivo import cliente_http
from scripts import arquivar_fontes


def test_listar_mostra_as_fontes(capsys):
    assert arquivar_fontes.main(["--listar"]) == 0
    saida = capsys.readouterr().out
    assert "cvm-fiagro" in saida
    assert "rfb-cnpj" in saida


def test_fonte_desconhecida_sai_com_2(capsys):
    assert arquivar_fontes.main(["nao-existe"]) == 2


def test_escolhe_por_grupo_ou_por_id():
    mensais = {f.id for f in arquivar_fontes.escolher("mensal")}
    assert {"rfb-cnpj", "pgfn-divida", "cvm-hist-ipe"} <= mensais
    assert "cvm-fiagro" not in mensais
    assert [f.id for f in arquivar_fontes.escolher("cvm-fiagro")] == ["cvm-fiagro"]
    assert arquivar_fontes.escolher("nada") == []


def _rodar_com(monkeypatch, resultados):
    """Roda `main` numa fonte só, com `arquivar` devolvendo (ou levantando) cada item da lista."""
    from base.arquivo.coleta import Resultado

    chamadas = []

    def arquivar_falso(fonte, cliente, agora, pasta):
        chamadas.append(fonte.id)
        item = resultados[len(chamadas) - 1]
        if isinstance(item, Exception):
            raise item
        return Resultado(fonte.id, novos=1, falhas=item)

    esperas = []
    monkeypatch.setattr(arquivar_fontes, "arquivar", arquivar_falso)
    monkeypatch.setattr(arquivar_fontes, "esperar", esperas.append)
    return arquivar_fontes.main(["cvm-fiagro"]), chamadas, esperas


def test_falha_passageira_tenta_de_novo_depois_de_esperar(monkeypatch):
    # o firewall do BC bloqueia por alguns minutos e depois libera (14/10/2026)
    saida, chamadas, esperas = _rodar_com(monkeypatch, [["https://x/a.zip"], []])
    assert saida == 0
    assert chamadas == ["cvm-fiagro", "cvm-fiagro"]
    assert esperas == [arquivar_fontes.ESPERA_PARA_TENTAR_DE_NOVO]


def test_erro_de_descoberta_tambem_tenta_de_novo(monkeypatch):
    from base.arquivo.coleta import ErroDeDescoberta

    saida, chamadas, _ = _rodar_com(monkeypatch, [ErroDeDescoberta("bloqueio"), []])
    assert saida == 0
    assert len(chamadas) == 2


def test_falha_que_continua_sai_com_1(monkeypatch):
    saida, chamadas, _ = _rodar_com(
        monkeypatch, [["https://x/a.zip"], ["https://x/a.zip"]]
    )
    assert saida == 1
    assert len(chamadas) == 2  # uma tentativa a mais, não um laço


def test_falha_deixa_o_motivo_na_ultima_linha(monkeypatch, capsys):
    # o aviso do Kuma de 14/10/2026 só dizia "saída 1": sem o log do servidor, ninguém sabia o porquê
    from base.arquivo.coleta import ErroDeDescoberta

    erro = ErroDeDescoberta("nenhum arquivo na pasta")
    saida, _, _ = _rodar_com(monkeypatch, [erro, erro])
    assert saida == 1
    ultima = capsys.readouterr().out.strip().splitlines()[-1]
    assert ultima == "FALHAS: cvm-fiagro (ErroDeDescoberta: nenhum arquivo na pasta)"


def test_falha_de_arquivo_aparece_no_resumo(monkeypatch, capsys):
    _rodar_com(monkeypatch, [["https://x/a.zip"], ["https://x/a.zip"]])
    ultima = capsys.readouterr().out.strip().splitlines()[-1]
    assert ultima == "FALHAS: cvm-fiagro (1 arquivos; 1º: https://x/a.zip)"


def test_sem_falha_nao_imprime_resumo(monkeypatch, capsys):
    _rodar_com(monkeypatch, [[]])
    assert "FALHAS" not in capsys.readouterr().out


def test_resumo_nao_e_cortado_a_lista_completa_vai_para_o_log():
    # a linha cortada em 300 caracteres escondia as outras falhas (rodada de 17/11/2026)
    linha = arquivar_fontes.resumo_das_falhas(["x" * 1000, "y"])
    assert linha == "FALHAS: " + "x" * 1000 + "; y"


class _RespostaFalsa:
    def __init__(self, status: int):
        self.status_code = status
        self.content = b"x" * 10

    def __enter__(self):
        return self

    def __exit__(self, *erro):
        return False

    def raise_for_status(self):
        return None


def test_trecho_recusa_servidor_que_manda_o_arquivo_inteiro(monkeypatch):
    """Se o servidor ignora o Range (HTTP 200), para antes de ler: seriam GBs na memória."""
    cliente = arquivar_fontes.ClienteHttp()
    pedidos = []

    def get(url, **opcoes):
        pedidos.append(opcoes["headers"]["Range"])
        return _RespostaFalsa(200 if "ignora" in url else 206)

    monkeypatch.setattr(cliente.sessao, "get", get)
    assert cliente.ler_trecho("https://x/ok.zip", 10, 19) == b"x" * 10
    with pytest.raises(ValueError, match="ignorou o pedido de trecho"):
        cliente.ler_trecho("https://x/ignora.zip", 0, 9)
    assert pedidos == ["bytes=10-19", "bytes=0-9"]


class _ServidorQueDerruba:
    """Servidor HTTP local: as `derrubar` primeiras conexões recebem o pedido e fecham sem
    responder (o `RemoteDisconnected` da Receita, 14/10/2026); as outras respondem `status`."""

    def __init__(self, derrubar: int, status: int = 200) -> None:
        self.derrubar = derrubar
        self.status = status
        self.pedidos: list[str] = []
        self.soquete = socket.create_server(("127.0.0.1", 0))
        self.url = f"http://127.0.0.1:{self.soquete.getsockname()[1]}/Qualificacoes.zip"
        threading.Thread(target=self._atender, daemon=True).start()

    def _atender(self) -> None:
        while True:
            try:
                conexao, _ = self.soquete.accept()
            except OSError:
                return
            with conexao:
                pedido = b""
                while b"\r\n\r\n" not in pedido:
                    pedido += conexao.recv(4096)
                self.pedidos.append(pedido.split(b" ", 1)[0].decode())
                if len(self.pedidos) <= self.derrubar:
                    continue  # fecha sem responder
                corpo = b"PK\x03\x04dados"
                conexao.sendall(
                    f"HTTP/1.1 {self.status} X\r\nContent-Length: {len(corpo)}\r\n"
                    "Connection: close\r\n\r\n".encode()
                    + corpo
                )

    def fechar(self) -> None:
        self.soquete.close()


@pytest.fixture
def servidor_que_derruba():
    servidores: list[_ServidorQueDerruba] = []

    def criar(derrubar: int, status: int = 200) -> _ServidorQueDerruba:
        servidores.append(_ServidorQueDerruba(derrubar, status))
        return servidores[-1]

    yield criar
    for servidor in servidores:
        servidor.fechar()


def test_conexao_que_cai_antes_da_resposta_tenta_de_novo(
    servidor_que_derruba, tmp_path
):
    cliente = arquivar_fontes.ClienteHttp()
    baixar = servidor_que_derruba(derrubar=2)
    cliente.baixar(baixar.url, tmp_path / "q.zip")
    assert (tmp_path / "q.zip").read_bytes() == b"PK\x03\x04dados"
    assert baixar.pedidos == ["GET"] * 3
    cabecalhos = servidor_que_derruba(derrubar=1)
    assert cliente.cabecalhos(cabecalhos.url)["Content-Length"] == "9"
    propfind = servidor_que_derruba(derrubar=1)
    assert cliente.ler(propfind.url, metodo="PROPFIND").conteudo.startswith(b"PK")


def test_conexao_que_sempre_cai_desiste_depois_de_algumas_tentativas(
    servidor_que_derruba, tmp_path
):
    servidor = servidor_que_derruba(derrubar=99)
    with pytest.raises(requests.ConnectionError):
        arquivar_fontes.ClienteHttp().baixar(servidor.url, tmp_path / "q.zip")
    assert len(servidor.pedidos) == 1 + cliente_http.TENTATIVAS_SE_A_CONEXAO_CAI


def test_resposta_de_erro_nao_e_repetida(servidor_que_derruba, tmp_path):
    # o 404 da B3 quer dizer "sem arquivo": perguntar de novo só gastaria tempo
    servidor = servidor_que_derruba(derrubar=0, status=404)
    with pytest.raises(requests.HTTPError):
        arquivar_fontes.ClienteHttp().baixar(servidor.url, tmp_path / "q.zip")
    assert servidor.pedidos == ["GET"]


class _PaginaDaCloudflare:
    status_code = 403
    url = "https://exemplo.gov.br/termos"

    def __init__(self):
        self.headers = {"cf-mitigated": "challenge"}

    def __enter__(self):
        return self

    def __exit__(self, *erro):
        return False

    def raise_for_status(self):
        raise requests.HTTPError("403", response=self)


def test_desafio_da_cloudflare_vira_bloqueio_e_erro_comum_continua_http(
    monkeypatch, tmp_path
):
    from base.arquivo.coleta import BloqueioAntiRobo

    cliente = arquivar_fontes.ClienteHttp()
    monkeypatch.setattr(cliente.sessao, "get", lambda url, **o: _PaginaDaCloudflare())
    with pytest.raises(BloqueioAntiRobo, match="403"):
        cliente.baixar("https://exemplo.gov.br/termos", tmp_path / "q.html")
    pagina = _PaginaDaCloudflare()
    pagina.headers = {}
    monkeypatch.setattr(cliente.sessao, "get", lambda url, **o: pagina)
    with pytest.raises(requests.HTTPError):
        cliente.baixar("https://exemplo.gov.br/termos", tmp_path / "q.html")


def test_vigia_bloqueada_sai_com_2_sem_tentar_de_novo(monkeypatch, capsys):
    from base.arquivo.coleta import Resultado

    chamadas = []

    def arquivar_falso(fonte, cliente, agora, pasta):
        chamadas.append(fonte.id)
        return Resultado(fonte.id, bloqueadas=["https://x/termos"])

    monkeypatch.setattr(arquivar_fontes, "arquivar", arquivar_falso)
    monkeypatch.setattr(arquivar_fontes, "esperar", lambda s: None)
    assert arquivar_fontes.main(["termos-ibge"]) == 2
    assert chamadas == ["termos-ibge"]
    assert "FALHAS" not in capsys.readouterr().out


# --- páginas de termos (licença) que não abrem: aviso próprio, ficha só depois de 7 dias (25/11/2026)
def _rodar_termos(monkeypatch, capsys, ultima_ok, ids=("termos-senado",), dado=False):
    """Roda `main` nas fontes dadas; a de termos falha sempre, a de dado falha se `dado`."""
    from datetime import UTC, datetime

    from base.arquivo.coleta import Fonte, Resultado

    esperas = []

    def arquivar_falso(fonte, cliente, agora, pasta):
        quebra = fonte.id.startswith("termos-") or dado
        return Resultado(fonte.id, falhas=[f"https://x/{fonte.id}"] if quebra else [])

    fontes = [Fonte(i, "diaria", lambda c, a: []) for i in ids]
    monkeypatch.setattr(arquivar_fontes, "arquivar", arquivar_falso)
    monkeypatch.setattr(arquivar_fontes, "esperar", esperas.append)
    monkeypatch.setattr(arquivar_fontes, "escolher", lambda alvo: fontes)
    monkeypatch.setattr(arquivar_fontes, "ultima_ok_em", lambda url: ultima_ok)
    monkeypatch.setattr(
        arquivar_fontes, "agora", lambda: datetime(2026, 11, 25, 3, tzinfo=UTC)
    )
    saida = arquivar_fontes.main(["diaria"])
    return saida, capsys.readouterr().out, esperas


def test_termo_fora_ha_menos_de_7_dias_e_so_aviso_com_a_data(monkeypatch, capsys):
    from datetime import UTC, datetime

    saida, texto, _ = _rodar_termos(
        monkeypatch, capsys, datetime(2026, 11, 20, tzinfo=UTC)
    )
    assert saida == 0
    assert "FALHAS" not in texto and "FICHA" not in texto
    assert "AVISO: termos-senado sem resposta desde 2026-11-20" in texto


def test_termo_fora_ha_7_dias_ou_mais_vira_ficha_com_saida_2(monkeypatch, capsys):
    from datetime import UTC, datetime

    saida, texto, _ = _rodar_termos(
        monkeypatch, capsys, datetime(2026, 11, 18, tzinfo=UTC)
    )
    assert saida == 2
    assert "FICHA: termos-senado sem resposta desde 2026-11-18" in texto
    assert "FALHAS" not in texto


def test_termo_que_nunca_respondeu_vira_ficha(monkeypatch, capsys):
    saida, texto, _ = _rodar_termos(monkeypatch, capsys, None)
    assert saida == 2
    assert "FICHA: termos-senado nunca respondeu" in texto


def test_falha_de_dado_sai_com_1_e_a_linha_de_falhas_nao_traz_os_termos(
    monkeypatch, capsys
):
    saida, texto, _ = _rodar_termos(
        monkeypatch, capsys, None, ids=("termos-senado", "cvm-fiagro"), dado=True
    )
    assert saida == 1
    ultima = texto.strip().splitlines()[-1]
    assert ultima.startswith("FALHAS: cvm-fiagro")
    assert "termos-senado" not in ultima
    assert "FICHA: termos-senado nunca respondeu" in texto


def test_termo_cuja_rodada_inteira_cai_na_rede_e_so_aviso_sem_ficha(
    monkeypatch, capsys
):
    """Sem o endereço que falhou (a descoberta ou a rede caiu), não dá para dizer "nunca respondeu":
    a página pode ter respondido ontem. Fica o aviso da rodada, sem ficha."""
    import requests

    from base.arquivo.coleta import Fonte

    def arquivar_falso(fonte, cliente, agora, pasta):
        raise requests.ConnectionError("sem rede")

    monkeypatch.setattr(arquivar_fontes, "arquivar", arquivar_falso)
    monkeypatch.setattr(arquivar_fontes, "esperar", lambda s: None)
    monkeypatch.setattr(
        arquivar_fontes,
        "escolher",
        lambda alvo: [Fonte("termos-senado", "diaria", lambda c, a: [])],
    )
    monkeypatch.setattr(arquivar_fontes, "ultima_ok_em", lambda url: None)
    saida = arquivar_fontes.main(["diaria"])
    texto = capsys.readouterr().out
    assert saida == 0
    assert "FICHA" not in texto and "FALHAS" not in texto
    assert "AVISO: termos-senado sem resposta nesta rodada" in texto


def test_pagina_de_termos_que_falha_espera_30_s_e_nao_300(monkeypatch, capsys):
    _, _, esperas = _rodar_termos(monkeypatch, capsys, None)
    assert esperas == [arquivar_fontes.ESPERA_DOS_TERMOS] == [30]


def test_a_rodada_tem_um_orcamento_de_espera_e_depois_nao_tenta_de_novo(
    monkeypatch, capsys
):
    ids = tuple(f"cvm-fonte{n}" for n in range(20))
    _, _, esperas = _rodar_termos(monkeypatch, capsys, None, ids=ids, dado=True)
    assert sum(esperas) <= arquivar_fontes.ORCAMENTO_DE_ESPERA
    assert len(esperas) == 6  # 6 x 300 s = 30 min; as outras 14 não esperam


def test_termos_fora_do_ar_nao_gastam_a_espera_das_fontes_de_dado(monkeypatch, capsys):
    """58 páginas de termos caindo juntas (rede fora) não podem comer a segunda tentativa do dado."""
    ids = tuple(f"termos-p{n}" for n in range(58)) + ("catalogo-bc",)
    _, _, esperas = _rodar_termos(monkeypatch, capsys, None, ids=ids, dado=True)
    assert esperas.count(arquivar_fontes.ESPERA_PARA_TENTAR_DE_NOVO) == 1
    assert sum(esperas) <= (
        arquivar_fontes.ORCAMENTO_DE_ESPERA + arquivar_fontes.ORCAMENTO_DOS_TERMOS
    )


def test_ultima_ok_em_diz_quando_o_endereco_respondeu_pela_ultima_vez(
    tmp_path, monkeypatch
):
    from datetime import UTC, datetime

    from base.arquivo.coleta import ultima_ok_em
    from src.banco.coletas import registrar_arquivo
    from src.banco.conexao import criar_engine, migrar_para

    url = f"sqlite:///{(tmp_path / 'b.sqlite').as_posix()}"
    monkeypatch.setenv("TICKERLAB_DATABASE_URL", url)
    migrar_para("head", url=url)
    motor = criar_engine(url)
    endereco = "https://x/termos"
    assert ultima_ok_em(endereco) is None
    with motor.begin() as c:
        for dia, situacao in ((10, "ok"), (18, "falhou")):
            registrar_arquivo(
                c, "termos-x", endereco, "a" * 64 if situacao == "ok" else None,
                1 if situacao == "ok" else None, situacao, None,
                datetime(2026, 11, dia, 6, tzinfo=UTC), None,
            )  # fmt: skip
    motor.dispose()
    ultima = ultima_ok_em(endereco)
    assert ultima is not None and ultima.date().isoformat() == "2026-11-10"
