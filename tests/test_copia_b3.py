"""Cópia da B3 no VPS e reconciliação com o servidor de casa (plano dos intradiários grátis, PR 4).

O VPS guarda uma segunda cópia dos negócios do pregão da B3 **fora do banco do app** (ADR 0073: só
pesquisa): `<pasta>/brutos/AAAA-MM-DD/<sha256>.zip`. Todo dia, o servidor de casa compara as duas
cópias, traz para o acervo o que só o VPS tem e acusa (`FALHAS:`) dia faltando ou diferente.
"""

import io
import json
import os
import zipfile
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
import requests

from base.arquivo import coleta, copia_b3, fontes
from src import acervo
from src.banco import coletas

AGORA = datetime(2026, 10, 14, 5, tzinfo=UTC)  # 2h em Brasília
DIA = date(2026, 10, 13)
URL = fontes.NEGOCIOS_DA_B3.format(dia=DIA.isoformat())
SHA_A = "a" * 64
SHA_B = "b" * 64


def _zip(tamanho: int = 1000) -> bytes:
    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, "w", zipfile.ZIP_STORED) as arquivo_zip:
        arquivo_zip.writestr("13-10-2026_NEGOCIOSAVISTA.txt", b"x" * tamanho)
    return memoria.getvalue()


def _sha(conteudo: bytes) -> str:
    import hashlib

    return hashlib.sha256(conteudo).hexdigest()


class B3Falsa:
    """O servidor da B3 em memória: url -> conteúdo (`None` = 404); dia fora do dicionário = 404."""

    def __init__(self, arquivos: dict[str, bytes | None]):
        self.arquivos = arquivos
        self.baixados: list[str] = []

    def baixar(self, url, destino: Path):
        self.baixados.append(url)
        conteudo = self.arquivos.get(url)
        if conteudo is None:
            resposta = requests.Response()
            resposta.status_code = 404
            raise requests.HTTPError("404", response=resposta)
        destino.write_bytes(conteudo)
        return {}


def _copiar(cliente, pasta: Path, agora: datetime = AGORA, livre_gb: int = 80):
    return copia_b3.copiar_janela(
        cliente,
        pasta,
        agora,
        pausa=0,
        espaco=lambda _: (96 * 1024**3, livre_gb * 1024**3),
    )


def _versoes(pasta: Path, dia: date = DIA) -> list[Path]:
    return sorted((pasta / "brutos" / dia.isoformat()).glob("*.zip"))


# --- a cópia no VPS -------------------------------------------------------------------------------


def test_copia_guarda_cada_dia_numa_pasta_com_o_sha_no_nome(tmp_path):
    conteudo = _zip()
    rodada = _copiar(B3Falsa({URL: conteudo}), tmp_path)
    assert (rodada.novos, rodada.falhas) == (1, [])
    # os outros 21 dias da janela respondem 404 (feriado ou dia que não saiu): não é falha
    assert rodada.sem_arquivo == 21
    [guardado] = _versoes(tmp_path)
    assert guardado.name == f"{_sha(conteudo)}.zip"
    assert guardado.read_bytes() == conteudo
    [linha] = (tmp_path / "manifesto.jsonl").read_text(encoding="utf-8").splitlines()
    registro = json.loads(linha)
    assert (registro["dia"], registro["sha256"], registro["bytes"]) == (
        "2026-10-13",
        _sha(conteudo),
        len(conteudo),
    )
    assert not list((tmp_path / ".temporario").glob("*"))  # nada pela metade


def test_copia_nao_usa_banco(tmp_path, monkeypatch):
    # ADR 0073: no VPS, o dado da B3 fica fora do banco do app
    def proibido(*_args, **_kwargs):
        raise AssertionError("a cópia da B3 no VPS não pode tocar no banco")

    monkeypatch.setattr(coleta, "obter_engine", proibido)
    assert _copiar(B3Falsa({URL: _zip()}), tmp_path).novos == 1


def test_resposta_vazia_e_404_nao_viram_arquivo(tmp_path):
    rodada = _copiar(B3Falsa({URL: b""}), tmp_path)
    assert (rodada.novos, rodada.falhas, rodada.sem_arquivo) == (0, [], 22)
    assert not list((tmp_path / "brutos").rglob("*.zip"))


def test_zip_quebrado_e_falha_e_nao_e_guardado(tmp_path):
    rodada = _copiar(B3Falsa({URL: _zip()[:-200]}), tmp_path)
    assert rodada.novos == 0
    assert len(rodada.falhas) == 1
    assert "2026-10-13" in rodada.falhas[0]
    assert not list((tmp_path / "brutos").rglob("*.zip"))


def test_dia_bom_ja_guardado_nao_e_baixado_de_novo(tmp_path, monkeypatch):
    monkeypatch.setattr(fontes, "TAMANHO_MINIMO_DE_UM_DIA_BOM", 500)
    cliente = B3Falsa({URL: _zip(2000)})
    _copiar(cliente, tmp_path)
    rodada = _copiar(cliente, tmp_path)
    assert rodada.pulados == 1
    assert cliente.baixados.count(URL) == 1


def test_dia_suspeito_e_baixado_de_novo_e_versao_nova_fica_ao_lado(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(fontes, "TAMANHO_MINIMO_DE_UM_DIA_BOM", 10_000)
    cliente = B3Falsa({URL: _zip(2000)})  # pequeno demais: veio incompleto
    _copiar(cliente, tmp_path)
    assert _copiar(cliente, tmp_path).iguais == 1  # a B3 não corrigiu
    assert len(_versoes(tmp_path)) == 1
    cliente.arquivos[URL] = _zip(20_000)  # a B3 corrigiu
    assert _copiar(cliente, tmp_path).novos == 1
    assert len(_versoes(tmp_path)) == 2
    assert _copiar(cliente, tmp_path).pulados == 1  # agora está bom


def test_freio_de_disco_para_antes_de_baixar(tmp_path):
    cliente = B3Falsa({URL: _zip()})
    with pytest.raises(coleta.FreioDeDisco):
        _copiar(cliente, tmp_path, livre_gb=10)
    assert cliente.baixados == []


def test_retencao_apaga_so_os_dias_antigos(tmp_path):
    brutos = tmp_path / "brutos"
    for nome in ("2026-07-15", "2026-07-16", "2026-10-13", "outra-coisa"):
        (brutos / nome).mkdir(parents=True)
        (brutos / nome / f"{SHA_A}.zip").write_bytes(b"PK")
    apagados = copia_b3.apagar_antigos(tmp_path, date(2026, 10, 14), dias=90)
    assert apagados == [date(2026, 7, 15)]  # 91 dias atrás; 16/07 tem 90
    assert sorted(p.name for p in brutos.iterdir()) == [
        "2026-07-16",
        "2026-10-13",
        "outra-coisa",
    ]


# --- a lista que o VPS manda para casa ------------------------------------------------------------


def test_lista_do_vps_fica_com_a_versao_mais_recente_de_cada_dia():
    texto = (
        f"2026-10-13 {SHA_A} {SHA_A} 100 5000\n"
        f"2026-10-13 {SHA_B} {SHA_B} 200 9000\n"
        f"2026-10-09 {SHA_A} {SHA_A} 50 5000\n"
    )
    ultimas, problemas = copia_b3.ler_lista_do_vps(texto)
    assert problemas == []
    assert ultimas[date(2026, 10, 13)].sha256 == SHA_B
    assert ultimas[date(2026, 10, 9)].sha256 == SHA_A


def test_arquivo_estragado_no_vps_e_problema():
    # o nome é o SHA-256 da hora do download; o calculado agora não bate: o disco estragou o arquivo
    ultimas, problemas = copia_b3.ler_lista_do_vps(
        f"2026-10-13 {SHA_A} {SHA_B} 100 5000\n"
    )
    assert ultimas == {}
    assert problemas == ["2026-10-13: arquivo aaaaaaaaaaaa estragado no VPS"]


def test_linha_estranha_na_lista_e_problema():
    _, problemas = copia_b3.ler_lista_do_vps("isso não é uma linha\n\n")
    assert problemas == ["linha estranha na lista do VPS: 'isso não é uma linha'"]


# --- a comparação ---------------------------------------------------------------------------------


def _v(dia: date, sha: str) -> copia_b3.Versao:
    return copia_b3.Versao(dia, sha, 0.0)


def test_comparar_acusa_dia_faltando_ou_diferente():
    d1, d2, d3, d4, d5 = (date(2026, 10, d) for d in (6, 7, 8, 9, 13))
    casa = {d1: _v(d1, SHA_A), d2: _v(d2, SHA_A), d4: _v(d4, SHA_A)}
    vps = {d1: _v(d1, SHA_A), d3: _v(d3, SHA_A), d4: _v(d4, SHA_B)}
    problemas = copia_b3.comparar(casa, vps, [d1, d2, d3, d4, d5])
    assert (
        problemas
        == [
            "2026-10-07: falta no VPS",
            "2026-10-08: faltava em casa",
            "2026-10-09: diferente (casa aaaaaaaaaaaa, VPS bbbbbbbbbbbb)",
        ]
    )  # 06/10 igual; 13/10 em nenhum dos dois (feriado ou perdido: o alarme da janela, PR 3)


def test_comparar_ignora_dias_fora_da_janela():
    antigo = date(2026, 7, 1)
    assert copia_b3.comparar({antigo: _v(antigo, SHA_A)}, {}, [DIA]) == []


def test_janela_e_a_mesma_do_arquivista():
    dias = copia_b3.dias_da_janela(AGORA)
    assert dias[0] == date(2026, 9, 15)
    assert dias[-1] == date(2026, 10, 14)
    assert len(dias) == 22


# --- o lado de casa: acervo, registro e manifesto -------------------------------------------------


def _guardar_em_casa(conteudo: bytes, quando: datetime = AGORA) -> str:
    """Um dia baixado pelo arquivista de casa (acervo + registro + manifesto)."""
    temporario = Path(os.environ[acervo.VARIAVEL_DA_PASTA]) / "t.parcial"
    temporario.parent.mkdir(parents=True, exist_ok=True)
    temporario.write_bytes(conteudo)
    return coleta.guardar_copia(
        "b3-negocios",
        URL,
        temporario,
        _sha(conteudo),
        quando,
        origem="teste",
        extensao=".zip",
    )


def test_ultimas_da_casa_vem_do_manifesto(banco, tmp_path):
    velho, novo = _zip(1000), _zip(2000)
    _guardar_em_casa(velho, datetime(2026, 10, 13, 23, tzinfo=UTC))
    _guardar_em_casa(novo, datetime(2026, 10, 14, 5, tzinfo=UTC))
    ultimas = copia_b3.ultimas_da_casa(tmp_path / "acervo", [DIA])
    assert ultimas[DIA].sha256 == _sha(novo)
    assert copia_b3.conferir_casa(tmp_path / "acervo", ultimas) == []


def test_arquivo_de_casa_estragado_ou_sumido_e_problema(banco, tmp_path):
    caminho = _guardar_em_casa(_zip())
    ultimas = copia_b3.ultimas_da_casa(tmp_path / "acervo", [DIA])
    (tmp_path / "acervo" / caminho).write_bytes(b"PK estragado")
    assert copia_b3.conferir_casa(tmp_path / "acervo", ultimas) == [
        "2026-10-13: arquivo de casa não bate com o manifesto"
    ]
    (tmp_path / "acervo" / caminho).unlink()
    assert copia_b3.conferir_casa(tmp_path / "acervo", ultimas) == [
        "2026-10-13: arquivo de casa sumiu do acervo"
    ]


def test_guardar_copia_registra_ok_com_a_origem(banco, tmp_path):
    conteudo = _zip()
    caminho = _guardar_em_casa(conteudo)
    assert (tmp_path / "acervo" / caminho).read_bytes() == conteudo
    with banco.connect() as conexao:
        linha = coletas.ultima_coleta_ok(conexao, URL)
    assert linha is not None
    assert (linha.sha256, linha.bytes) == (_sha(conteudo), len(conteudo))
    assert "cópia do teste" in linha.detalhe
    [manifesto] = (tmp_path / "acervo" / "manifesto").glob("*.jsonl")
    registro = json.loads(manifesto.read_text(encoding="utf-8"))
    assert (registro["fonte"], registro["origem"]) == ("b3-negocios", "teste")


def test_recebidos_do_vps_entram_no_acervo(banco, tmp_path):
    conteudo = _zip()
    recebidos = tmp_path / "recebidos"
    (recebidos / DIA.isoformat()).mkdir(parents=True)
    (recebidos / DIA.isoformat() / f"{_sha(conteudo)}.zip").write_bytes(conteudo)
    trazidos, problemas = copia_b3.guardar_recebidos(recebidos, AGORA)
    assert (trazidos, problemas) == (1, [])
    ultimas = copia_b3.ultimas_da_casa(tmp_path / "acervo", [DIA])
    assert ultimas[DIA].sha256 == _sha(conteudo)
    assert not list(recebidos.rglob("*.zip"))


def test_recebido_estragado_no_caminho_nao_entra(banco, tmp_path):
    recebidos = tmp_path / "recebidos"
    (recebidos / DIA.isoformat()).mkdir(parents=True)
    (recebidos / DIA.isoformat() / f"{SHA_A}.zip").write_bytes(_zip())
    trazidos, problemas = copia_b3.guardar_recebidos(recebidos, AGORA)
    assert trazidos == 0
    assert problemas == ["2026-10-13: chegou estragado do VPS (aaaaaaaaaaaa)"]
    assert copia_b3.ultimas_da_casa(tmp_path / "acervo", [DIA]) == {}


# --- os scripts: `copiar_b3_negocios` (VPS) e `reconciliar_b3_vps` (casa) --------------------------


# Três momentos: dia útil, sábado e domingo 23h em Brasília (já segunda em UTC).
MOMENTOS = [
    pytest.param(datetime(2026, 10, 14, 15, tzinfo=UTC), id="dia-util"),
    pytest.param(datetime(2026, 10, 17, 15, tzinfo=UTC), id="sabado"),
    pytest.param(datetime(2026, 10, 19, 2, tzinfo=UTC), id="domingo-a-noite"),
]


def _hoje_util(agora: datetime) -> date:
    """O último dia útil da janela do momento dado (o script usa o mesmo relógio)."""
    return copia_b3.dias_da_janela(agora)[-1]


def _fixar_relogio_do_script(monkeypatch, agora: datetime) -> None:
    from scripts import copiar_b3_negocios

    monkeypatch.setattr(copiar_b3_negocios, "agora", lambda: agora)


@pytest.mark.parametrize("agora", MOMENTOS)
def test_script_do_vps_guarda_e_sai_com_zero(tmp_path, monkeypatch, agora):
    from scripts import copiar_b3_negocios

    _fixar_relogio_do_script(monkeypatch, agora)
    dia = _hoje_util(agora)
    url = fontes.NEGOCIOS_DA_B3.format(dia=dia.isoformat())
    monkeypatch.setattr(
        copiar_b3_negocios, "ClienteHttp", lambda: B3Falsa({url: _zip()})
    )
    monkeypatch.setattr(copiar_b3_negocios, "PAUSA", 0)
    assert copiar_b3_negocios.main(["--pasta", str(tmp_path)]) == 0
    assert len(_versoes(tmp_path, dia)) == 1


@pytest.mark.parametrize("agora", MOMENTOS)
def test_script_do_vps_avisa_a_falha_numa_linha(tmp_path, monkeypatch, capsys, agora):
    from scripts import copiar_b3_negocios

    _fixar_relogio_do_script(monkeypatch, agora)
    dia = _hoje_util(agora)
    url = fontes.NEGOCIOS_DA_B3.format(dia=dia.isoformat())
    monkeypatch.setattr(
        copiar_b3_negocios, "ClienteHttp", lambda: B3Falsa({url: _zip()[:-200]})
    )
    monkeypatch.setattr(copiar_b3_negocios, "PAUSA", 0)
    assert copiar_b3_negocios.main(["--pasta", str(tmp_path)]) == 1
    ultima = capsys.readouterr().out.strip().splitlines()[-1]
    assert ultima.startswith(f"FALHAS: b3-negocios no VPS: {dia}")


def test_script_do_vps_para_no_freio_de_disco(tmp_path, monkeypatch, capsys):
    from scripts import copiar_b3_negocios

    monkeypatch.setattr(copiar_b3_negocios, "ClienteHttp", lambda: B3Falsa({}))
    monkeypatch.setattr(
        copiar_b3_negocios, "espaco_do_disco", lambda _: (96 * 1024**3, 10 * 1024**3)
    )
    assert copiar_b3_negocios.main(["--pasta", str(tmp_path)]) == 1
    assert "FALHAS: b3-negocios no VPS: FreioDeDisco" in capsys.readouterr().out


def _trabalho_da_reconciliacao(tmp_path: Path, lista: str) -> Path:
    trabalho = tmp_path / "trabalho"
    (trabalho / "recebidos").mkdir(parents=True)
    (trabalho / "lista.txt").write_text(lista, encoding="utf-8")
    return trabalho


def _guardar_dia_em_casa(dia: date, conteudo: bytes) -> None:
    temporario = Path(os.environ[acervo.VARIAVEL_DA_PASTA]) / "t.parcial"
    temporario.parent.mkdir(parents=True, exist_ok=True)
    temporario.write_bytes(conteudo)
    coleta.guardar_copia(
        "b3-negocios",
        fontes.NEGOCIOS_DA_B3.format(dia=dia.isoformat()),
        temporario,
        _sha(conteudo),
        datetime.now(UTC),
        origem="teste",
        extensao=".zip",
    )


def test_reconciliacao_sem_diferenca_sai_com_zero(banco, tmp_path, capsys):
    from scripts import reconciliar_b3_vps

    dia, conteudo = _hoje_util(datetime.now(UTC)), _zip()
    _guardar_dia_em_casa(dia, conteudo)
    sha = _sha(conteudo)
    trabalho = _trabalho_da_reconciliacao(tmp_path, f"{dia} {sha} {sha} 100 1000\n")
    assert reconciliar_b3_vps.main(["--trabalho", str(trabalho)]) == 0
    assert "FALHAS" not in capsys.readouterr().out


def test_reconciliacao_traz_o_dia_que_faltava_e_acusa(banco, tmp_path, capsys):
    from scripts import reconciliar_b3_vps

    dia, conteudo = _hoje_util(datetime.now(UTC)), _zip()
    sha = _sha(conteudo)
    trabalho = _trabalho_da_reconciliacao(tmp_path, f"{dia} {sha} {sha} 100 1000\n")
    (trabalho / "recebidos" / dia.isoformat()).mkdir()
    (trabalho / "recebidos" / dia.isoformat() / f"{sha}.zip").write_bytes(conteudo)
    assert reconciliar_b3_vps.main(["--trabalho", str(trabalho)]) == 1
    ultima = capsys.readouterr().out.strip().splitlines()[-1]
    assert ultima == f"FALHAS: B3 casa x VPS: {dia}: faltava em casa"
    # agora a casa tem: a rodada seguinte não acusa nada
    assert reconciliar_b3_vps.main(["--trabalho", str(trabalho)]) == 0


def test_reconciliacao_acusa_dia_que_falta_no_vps(banco, tmp_path, capsys):
    from scripts import reconciliar_b3_vps

    dia = _hoje_util(datetime.now(UTC))
    _guardar_dia_em_casa(dia, _zip())
    trabalho = _trabalho_da_reconciliacao(tmp_path, "")
    assert reconciliar_b3_vps.main(["--trabalho", str(trabalho)]) == 1
    assert f"{dia}: falta no VPS" in capsys.readouterr().out
