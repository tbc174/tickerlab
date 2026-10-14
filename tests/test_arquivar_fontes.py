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


def test_resumo_longo_e_cortado():
    linha = arquivar_fontes.resumo_das_falhas(["x" * 1000])
    assert len(linha) == arquivar_fontes.TAMANHO_MAXIMO_DO_RESUMO
    assert linha.endswith("...")
