"""Linha de comando do arquivista (scripts/arquivar_fontes.py)."""

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
    monkeypatch.setattr(arquivar_fontes.time, "sleep", esperas.append)
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
