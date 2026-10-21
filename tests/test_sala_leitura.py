"""A leitura dos documentos da sala em processo separado (B-20, PR 2, decisão D7).

O filho roda de verdade (Python em modo isolado): lê os quatro tipos, recusa pelo PDFium o que a
conferência por fora não pega, e qualquer falha, demora ou resposta estranha vira
`erro_na_leitura` sem derrubar quem chamou.
"""

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from src.sala import arquivos, leitura
from tests import ajudantes_da_sala as gerar


def test_le_o_pdf_pagina_por_pagina():
    resultado = leitura.ler_em_subprocesso(gerar.pdf("Receita 100", "Lucro 20"), "pdf")
    assert resultado == leitura.Leitura("lido", ("Receita 100", "Lucro 20"))


def test_le_a_planilha_aba_por_aba_sem_avaliar_formula():
    import io

    import openpyxl

    livro = openpyxl.Workbook()
    aba = livro.worksheets[0]
    aba.append(["receita", 100])
    aba.append(["dobro", "=B1*2"])
    segunda = livro.create_sheet("Outra")
    segunda.append(["x"])
    saida = io.BytesIO()
    livro.save(saida)
    resultado = leitura.ler_em_subprocesso(saida.getvalue(), "xlsx")
    assert resultado.situacao == "lido"
    # sem valor gravado (openpyxl não calcula), a fórmula fica vazia: nada é executado
    assert resultado.paginas == ("receita\t100\ndobro\t", "x")


def test_le_o_docx_e_separa_nas_quebras_de_pagina():
    conteudo = gerar.docx(["Contrato", "Cláusula 1"], ["Anexo"])
    resultado = leitura.ler_em_subprocesso(conteudo, "docx")
    assert resultado == leitura.Leitura("lido", ("Contrato\nCláusula 1", "Anexo"))


def test_le_o_csv_em_utf8_e_em_cp1252():
    for codificacao in ("utf-8", "cp1252"):
        conteudo = "nome;valor\nação;1\n".encode(codificacao)
        assert leitura.ler_em_subprocesso(conteudo, "csv").paginas == (
            "nome;valor\nação;1\n",
        )


def test_documento_sem_texto():
    assert leitura.ler_em_subprocesso(gerar.pdf("", ""), "pdf").situacao == "sem_texto"


@pytest.mark.parametrize(
    ("gerador", "motivo"),
    [
        pytest.param(gerar.pdf_com_javascript, arquivos.PDF_ATIVO, id="javascript"),
        pytest.param(gerar.pdf_com_anexo, arquivos.PDF_ATIVO, id="anexo"),
        pytest.param(gerar.pdf_cifrado, arquivos.PDF_CIFRADO, id="com-senha"),
        pytest.param(
            lambda: gerar.pdf_cifrado(""), arquivos.PDF_CIFRADO, id="cifrado-sem-senha"
        ),
        pytest.param(
            lambda: b"%PDF-1.7 lixo", arquivos.ARQUIVO_DANIFICADO, id="quebrado"
        ),
    ],
)
def test_o_filho_confere_de_novo_pelo_pdfium(gerador, motivo):
    """Segunda barreira: mesmo que a conferência por fora deixasse passar, o filho recusa."""
    assert leitura.ler_em_subprocesso(gerador(), "pdf") == leitura.Leitura(
        "erro_na_leitura", motivo=motivo
    )


def test_docx_com_entidade_externa_nao_le_arquivo_do_servidor():
    resultado = leitura.ler_em_subprocesso(gerar.docx_com_entidade_externa(), "docx")
    assert resultado == leitura.ERRO


def test_tipo_desconhecido_e_erro_de_programa():
    with pytest.raises(ValueError, match="Tipo"):
        leitura.ler_em_subprocesso(b"x", "exe")


# --- o filho que trava, falha ou mente ---------------------------------------------------


def _filho_que_roda(monkeypatch, codigo: str) -> None:
    monkeypatch.setattr(
        leitura, "_comando_do_filho", lambda _: [sys.executable, "-c", codigo]
    )


def test_leitura_que_passa_do_tempo_vira_erro_e_o_filho_morre(monkeypatch):
    _filho_que_roda(monkeypatch, "import time; time.sleep(60)")
    inicio = time.monotonic()
    assert leitura.ler_em_subprocesso(b"x", "pdf", tempo_maximo=1) == leitura.ERRO
    assert time.monotonic() - inicio < 15


def test_filho_que_quebra_vira_erro(monkeypatch):
    _filho_que_roda(monkeypatch, "import sys; sys.exit(3)")
    assert leitura.ler_em_subprocesso(b"x", "pdf") == leitura.ERRO


@pytest.mark.parametrize(
    "saida",
    [
        b"",
        b"nao e json",
        b"[1, 2]",
        b'{"paginas": "texto"}',
        b'{"paginas": [1, 2]}',
        b'{"outra": 1}',
        b"\xff\xfe",
    ],
)
def test_resposta_estranha_do_filho_vira_erro(saida):
    assert leitura._interpretar(saida) == leitura.ERRO


def test_motivo_fora_da_lista_nao_passa_adiante():
    resposta = json.dumps({"recusa": "<script>texto livre</script>"}).encode()
    assert leitura._interpretar(resposta) == leitura.Leitura(
        "erro_na_leitura", motivo=None
    )


def test_o_filho_nao_herda_nenhuma_variavel_do_servidor(monkeypatch):
    monkeypatch.setenv("TICKERLAB_CHAVE_DA_SALA", "v1:segredo")
    monkeypatch.setenv("TICKERLAB_DATABASE_URL", "postgresql://segredo")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_segredo")
    ambiente = leitura._ambiente_do_filho()
    assert set(ambiente) <= set(leitura._VARIAVEIS_PASSADAS_AO_FILHO)
    assert "segredo" not in json.dumps(ambiente)


def test_o_filho_roda_em_modo_isolado():
    comando = leitura._comando_do_filho("pdf")
    assert comando[:3] == [sys.executable, "-I", "-c"]
    assert comando[-1] == "pdf"


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="limites do Linux")
def test_no_linux_o_filho_se_limita_antes_de_ler(tmp_path):
    codigo = (
        "import resource, sys; sys.path.insert(0, sys.argv[1]);"
        "from src.sala.leitura import _limitar_o_proprio_processo as limitar; limitar();"
        "print(resource.getrlimit(resource.RLIMIT_AS)[0], resource.getrlimit(resource.RLIMIT_FSIZE)[0]);"
        "sys.stdout.flush();"
        "open('proibido.txt', 'w').write('x')"
    )
    resultado = subprocess.run(
        [sys.executable, "-I", "-c", codigo, str(leitura.RAIZ_DO_PROJETO)],
        cwd=tmp_path,
        capture_output=True,
        check=False,
    )
    memoria, arquivo = resultado.stdout.split()[:2]
    assert int(memoria) == leitura.MEMORIA_MAXIMA_EM_BYTES and int(arquivo) == 0
    assert resultado.returncode != 0  # gravar arquivo é proibido (SIGXFSZ ou EFBIG)
    assert (
        not (tmp_path / "proibido.txt").exists()
        or (tmp_path / "proibido.txt").stat().st_size == 0
    )


def test_o_filho_roda_numa_pasta_vazia_que_some_depois(monkeypatch, tmp_path):
    """Nada que o filho (ou o sistema, por ele) grave cai na pasta do projeto."""
    onde = tmp_path / "onde.txt"
    _filho_que_roda(
        monkeypatch,
        f"import os; open({str(onde)!r}, 'w').write(os.getcwd()); open('rastro', 'w')",
    )
    leitura.ler_em_subprocesso(b"x", "pdf")
    pasta_do_filho = Path(onde.read_text())
    assert pasta_do_filho != leitura.RAIZ_DO_PROJETO
    assert not pasta_do_filho.exists()
    assert not (leitura.RAIZ_DO_PROJETO / "rastro").exists()


@pytest.mark.skipif(sys.platform != "win32", reason="variável do Windows")
def test_no_windows_o_filho_sabe_o_disco_do_sistema():
    """Sem SYSTEMDRIVE, o Windows grava um cache numa pasta chamada "%SystemDrive%"."""
    assert "SYSTEMDRIVE" in leitura._ambiente_do_filho()
