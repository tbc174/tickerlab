"""Negócios do pregão da B3 no arquivista (fonte `b3-negocios`, plano dos intradiários grátis, PR 1).

A B3 deixa no ar só os últimos ~20 pregões (`arquivos.b3.com.br/rapinegocios/tickercsv/AAAA-MM-DD`).
Medido em 14/10/2026: dia que já saiu da janela responde **200 com 0 bytes**; feriado e dia que
ainda não saiu respondem **404**; `HEAD` responde 405 (sem ETag nem Last-Modified). Só pesquisa
(ADRs 0019 e 0073).
"""

import dataclasses
import io
import json
import zipfile
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
import requests

from base import intradiario_b3
from base.arquivo import coleta, fontes
from src.banco import coletas

AGORA = datetime(2026, 10, 14, 5, tzinfo=UTC)  # 2h em Brasília
DIA = date(2026, 10, 13)
URL = "https://arquivos.b3.com.br/rapinegocios/tickercsv/2026-10-13"


def _zip(tamanho: int = 1000) -> bytes:
    """Um zip de verdade, como o da B3 (um TXT com `;`), com ~`tamanho` bytes."""
    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, "w", zipfile.ZIP_STORED) as arquivo_zip:
        arquivo_zip.writestr("13-10-2026_NEGOCIOSAVISTA.txt", b"x" * tamanho)
    return memoria.getvalue()


class B3Falsa:
    """O servidor da B3 em memória: url -> conteúdo (`None` = 404). `HEAD` dá 405, como lá."""

    def __init__(self, arquivos: dict[str, bytes | None]):
        self.arquivos = arquivos
        self.baixados: list[str] = []

    def cabecalhos(self, url):
        raise AssertionError(
            "a B3 não aceita HEAD (405): a fonte não pode depender dele"
        )

    def baixar(self, url, destino: Path):
        self.baixados.append(url)
        conteudo = self.arquivos[url]
        if conteudo is None:
            resposta = requests.Response()
            resposta.status_code = 404
            raise requests.HTTPError("404 Client Error: Not Found", response=resposta)
        destino.write_bytes(conteudo)
        return {"Content-Type": "application/zip"}


def _fonte_de_um_dia(dia: date = DIA) -> coleta.Fonte:
    """A fonte de verdade, mas só com o alvo de `dia` (a janela inteira tem 22 endereços)."""
    alvo = fontes.alvo_dos_negocios_b3(dia)
    return dataclasses.replace(
        fontes.POR_ID["b3-negocios"], descobrir=lambda cliente, agora: [alvo]
    )


def _rodar(cliente, tmp_path, fonte=None, rodada=0):
    """`rodada` avança o relógio (horas): a "última coleta" é a de hora mais recente."""
    return coleta.arquivar(
        fonte or _fonte_de_um_dia(),
        cliente,
        AGORA + timedelta(hours=rodada),
        tmp_path / "temporario",
        pausa=0,
        espaco=lambda pasta: (900 * 1024**3, 800 * 1024**3),
    )


def _linhas(banco):
    with banco.connect() as conexao:
        return coletas.ultimas(conexao)


def test_b3_no_catalogo_diaria_pesada_e_zip():
    fonte = fontes.POR_ID["b3-negocios"]
    assert (fonte.grupo, fonte.tipo, fonte.pesada) == ("diaria", "zip", True)


def test_alvos_da_janela():
    alvos = fontes.POR_ID["b3-negocios"].descobrir(None, AGORA)
    dias = [a.url.rsplit("/", 1)[-1] for a in alvos]
    # dias úteis de 15/09 a 14/10 (o feriado de 12/10 e o dia de hoje entram: respondem 404)
    assert dias[0] == "2026-09-15"
    assert dias[-1] == "2026-10-14"
    assert len(dias) == len(set(dias)) == 22
    assert "2026-10-12" in dias
    assert not any(date.fromisoformat(d).weekday() >= 5 for d in dias)
    assert all(a.url.startswith(fontes.NEGOCIOS_DA_B3.format(dia="")) for a in alvos)
    assert {a.extensao for a in alvos} == {".zip"}


def test_rodada_das_22h_usa_o_dia_de_brasilia():
    # 22h de 14/10 em Brasília já é 15/10 em UTC: o dia de amanhã não entra
    alvos = fontes.POR_ID["b3-negocios"].descobrir(
        None, datetime(2026, 10, 15, 1, tzinfo=UTC)
    )
    assert alvos[-1].url.endswith("/2026-10-14")


def test_zip_do_dia_e_guardado_e_registrado(banco, tmp_path):
    resultado = _rodar(B3Falsa({URL: _zip()}), tmp_path)
    assert (resultado.novos, resultado.falhas, resultado.sem_arquivo) == (1, [], 0)
    [linha] = _linhas(banco)
    assert (linha.situacao, linha.fonte) == ("ok", "b3-negocios")
    assert linha.caminho_do_original.endswith(".zip")


def test_resposta_vazia_nao_e_arquivo(banco, tmp_path):
    # dia que já saiu da janela: a B3 responde 200 com 0 bytes
    resultado = _rodar(B3Falsa({URL: b""}), tmp_path)
    assert (resultado.novos, resultado.iguais, resultado.falhas) == (0, 0, [])
    assert resultado.sem_arquivo == 1
    [linha] = _linhas(banco)
    assert linha.situacao == "nao_encontrado"
    assert linha.caminho_do_original is None
    assert "0 bytes" in linha.detalhe
    assert not list((tmp_path / "acervo").rglob("*.zip"))


def test_feriado_e_dia_que_nao_saiu_respondem_404_e_nao_e_arquivo(banco, tmp_path):
    resultado = _rodar(B3Falsa({URL: None}), tmp_path)
    assert (resultado.novos, resultado.falhas, resultado.sem_arquivo) == (0, [], 1)
    [linha] = _linhas(banco)
    assert linha.situacao == "nao_encontrado"
    assert "404" in linha.detalhe


def test_zip_quebrado_falha(banco, tmp_path):
    cortado = _zip()[:-200]  # o download parou no meio
    resultado = _rodar(B3Falsa({URL: cortado}), tmp_path)
    assert resultado.falhas == [URL]
    assert resultado.sem_arquivo == 0
    [linha] = _linhas(banco)
    assert (linha.situacao, linha.caminho_do_original) == ("falhou", None)


def test_html_no_lugar_do_zip_falha(banco, tmp_path):
    resultado = _rodar(
        B3Falsa({URL: b"<!DOCTYPE html><html>manutencao</html>"}), tmp_path
    )
    assert resultado.falhas == [URL]


def test_outro_erro_http_continua_sendo_falha(banco, tmp_path):
    class Fora(B3Falsa):
        def baixar(self, url, destino):
            resposta = requests.Response()
            resposta.status_code = 503
            raise requests.HTTPError("503", response=resposta)

    resultado = _rodar(Fora({}), tmp_path)
    assert resultado.falhas == [URL]
    assert resultado.sem_arquivo == 0


def test_dia_bom_ja_guardado_nao_e_baixado_de_novo(banco, tmp_path, monkeypatch):
    monkeypatch.setattr(fontes, "TAMANHO_MINIMO_DE_UM_DIA_BOM", 500)
    cliente = B3Falsa({URL: _zip(2000)})
    _rodar(cliente, tmp_path)
    resultado = _rodar(cliente, tmp_path)
    assert resultado.pulados == 1
    assert cliente.baixados == [URL]


def test_dia_suspeito_e_baixado_de_novo_para_ver_se_a_b3_corrigiu(
    banco, tmp_path, monkeypatch
):
    monkeypatch.setattr(fontes, "TAMANHO_MINIMO_DE_UM_DIA_BOM", 10_000)
    cliente = B3Falsa({URL: _zip(2000)})  # pequeno demais: dia que veio incompleto
    _rodar(cliente, tmp_path)
    assert _rodar(cliente, tmp_path, rodada=1).iguais == 1  # a B3 não mudou
    cliente.arquivos[URL] = _zip(20_000)  # a B3 corrigiu: versão nova, guardada ao lado
    assert _rodar(cliente, tmp_path, rodada=2).novos == 1
    assert len(cliente.baixados) == 3
    assert len(list((tmp_path / "acervo").rglob("*.zip"))) == 2
    # agora está bom: não baixa mais
    assert _rodar(cliente, tmp_path, rodada=3).pulados == 1


@pytest.mark.parametrize("resposta", [b"", None])
def test_sem_arquivo_nao_conta_como_falha_nem_apaga_o_que_ja_foi_guardado(
    banco, tmp_path, monkeypatch, resposta
):
    # a B3 tira o dia da janela depois de guardado: o "ok" anterior continua valendo
    monkeypatch.setattr(fontes, "TAMANHO_MINIMO_DE_UM_DIA_BOM", 10_000)
    cliente = B3Falsa({URL: _zip(2000)})
    _rodar(cliente, tmp_path)
    cliente.arquivos[URL] = resposta
    assert _rodar(cliente, tmp_path, rodada=1).sem_arquivo == 1
    with banco.connect() as conexao:
        assert coletas.ultima_coleta_ok(conexao, URL) is not None
    assert len(list((tmp_path / "acervo").rglob("*.zip"))) == 1


# --- PR 2: o selo decide se o dia guardado vale (no lugar dos 40 MB) ------------------------------


def _gravar_selo(tmp_path, sha256: str, selo: str, dia: date = DIA) -> None:
    caminho = intradiario_b3.caminho_do_resumo(dia, tmp_path / "acervo")
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(
        json.dumps({"sha256_do_arquivo": sha256, "selo_do_dia": selo}), "utf-8"
    )


def test_dia_pequeno_com_selo_completo_nao_e_baixado_de_novo(banco, tmp_path):
    cliente = B3Falsa({URL: _zip(2000)})  # menor que 40 MB, mas o selo diz que bate
    _rodar(cliente, tmp_path)
    _gravar_selo(tmp_path, _linhas(banco)[0].sha256, "completo")
    assert _rodar(cliente, tmp_path, rodada=1).pulados == 1
    assert cliente.baixados == [URL]


def test_dia_grande_com_selo_incompleto_e_baixado_de_novo(banco, tmp_path, monkeypatch):
    """O 15/09 tem 84 MB e veio quebrado: só o selo percebe."""
    monkeypatch.setattr(fontes, "TAMANHO_MINIMO_DE_UM_DIA_BOM", 500)
    cliente = B3Falsa({URL: _zip(2000)})
    _rodar(cliente, tmp_path)
    _gravar_selo(tmp_path, _linhas(banco)[0].sha256, "incompleto")
    assert _rodar(cliente, tmp_path, rodada=1).iguais == 1
    assert len(cliente.baixados) == 2


def test_selo_de_outra_versao_do_arquivo_nao_vale(banco, tmp_path, monkeypatch):
    monkeypatch.setattr(fontes, "TAMANHO_MINIMO_DE_UM_DIA_BOM", 10_000)
    cliente = B3Falsa({URL: _zip(2000)})
    _rodar(cliente, tmp_path)
    _gravar_selo(tmp_path, "outro-sha", "completo")
    assert _rodar(cliente, tmp_path, rodada=1).iguais == 1  # volta à regra do tamanho


# --- boletins oficiais do dia: PR (BVBG.086) e COTAHIST -------------------------------------------

URL_DO_PR = "https://www.b3.com.br/pesquisapregao/download?filelist=PR261013.zip"
URL_DO_COTAHIST = (
    "https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_D13102026.ZIP"
)


def _zip_vazio() -> bytes:
    memoria = io.BytesIO()
    zipfile.ZipFile(memoria, "w").close()
    return memoria.getvalue()  # 22 bytes, como o PR de 12/10/2026 (feriado)


@pytest.mark.parametrize(
    ("fonte", "primeiro", "ultimo"),
    [
        ("b3-boletim-pr", "filelist=PR260915.zip", "filelist=PR261014.zip"),
        ("b3-cotahist-dia", "COTAHIST_D15092026.ZIP", "COTAHIST_D14102026.ZIP"),
    ],
)
def test_boletins_da_janela(fonte, primeiro, ultimo):
    alvos = fontes.POR_ID[fonte].descobrir(None, AGORA)
    assert alvos[0].url.endswith(primeiro)
    assert alvos[-1].url.endswith(ultimo)
    assert len(alvos) == 22
    assert {a.extensao for a in alvos} == {".zip"}
    assert fontes.POR_ID[fonte].grupo == "diaria"


def _fonte_do_boletim(fonte_id: str, url: str) -> coleta.Fonte:
    alvo = next(
        a for a in fontes.POR_ID[fonte_id].descobrir(None, AGORA) if a.url == url
    )
    return dataclasses.replace(
        fontes.POR_ID[fonte_id], descobrir=lambda cliente, agora: [alvo]
    )


def test_pr_vazio_no_feriado_nao_e_arquivo(banco, tmp_path):
    fonte = _fonte_do_boletim("b3-boletim-pr", URL_DO_PR)
    resultado = _rodar(B3Falsa({URL_DO_PR: _zip_vazio()}), tmp_path, fonte)
    assert (resultado.novos, resultado.sem_arquivo, resultado.falhas) == (0, 1, [])


def test_cotahist_404_no_feriado_nao_e_arquivo(banco, tmp_path):
    fonte = _fonte_do_boletim("b3-cotahist-dia", URL_DO_COTAHIST)
    resultado = _rodar(B3Falsa({URL_DO_COTAHIST: None}), tmp_path, fonte)
    assert (resultado.novos, resultado.sem_arquivo, resultado.falhas) == (0, 1, [])


def test_boletim_baixado_na_noite_do_pregao_e_baixado_de_novo_no_dia_seguinte(
    banco, tmp_path
):
    """O PR sai em várias versões até ~21h: o das 22h pode não ser o último; o das 2h é."""
    fonte = _fonte_do_boletim("b3-boletim-pr", URL_DO_PR)
    cliente = B3Falsa({URL_DO_PR: _zip()})
    noite = datetime(2026, 10, 14, 0, 30, tzinfo=UTC)  # 13/10 às 21h30 em Brasília
    madrugada = datetime(2026, 10, 14, 5, tzinfo=UTC)  # 14/10 às 2h

    def rodar(agora):
        return coleta.arquivar(
            fonte,
            cliente,
            agora,
            tmp_path / "temporario",
            pausa=0,
            espaco=lambda pasta: (900 * 1024**3, 800 * 1024**3),
        )

    rodar(noite)
    assert rodar(madrugada).iguais == 1
    assert rodar(madrugada + timedelta(hours=20)).pulados == 1
    assert len(cliente.baixados) == 2
