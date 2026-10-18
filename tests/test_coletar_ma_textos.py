"""Coleta em gotas dos documentos de M&A do IPE: a fila põe primeiro o que mais rende, para no limite da
CVM, não deixa um documento quebrado travar a fila e grava o texto como o da amostra de ouro. Sem
internet: o IPE é montado aqui e o RAD é falso."""

from datetime import UTC, datetime

import pandas as pd
import pytest
import sqlalchemy as sa
from fpdf import FPDF

from base import ma_ipe
from base import ma_textos as mt
from scripts import coletar_ma_textos as coletor
from scripts import rotular_com_ia
from src import acervo
from src import versao_do_codigo as vc
from src.banco.coletas import registrar
from src.banco.conexao import criar_engine, migrar_para
from src.banco.modelo import coletas
from tests.test_base_ma_ipe import COMUNICADO, FATO, OPA
from tests.test_ratings import _linha, _zip

VERSAO = "9b1e0c4d2e1f0a9b8c7d6e5f4a3b2c1d0e9f8a7c"
PAGINA_DE_LIMITE = b"\r\n<!DOCTYPE html><html><body>Limite de acessos</body></html>"
TEXTO = (
    "COMPANHIA BETA S.A. CNPJ 11.111.111/0001-11 FATO RELEVANTE A Companhia Beta S.A. comunica que "
    "assinou contrato para adquirir a totalidade das ações da Gama Ltda. por R$ 120 milhões, sujeito "
    "à aprovação do CADE. São Paulo, 5 de março de 2024. Diretor de Relações com Investidores"
)


def _pdf(texto: str = TEXTO) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("helvetica", size=11)
    pdf.multi_cell(0, 6, texto)
    return bytes(pdf.output())


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'b.sqlite').as_posix()}"
    monkeypatch.setenv("TICKERLAB_DATABASE_URL", url)
    monkeypatch.setenv(acervo.VARIAVEL_DA_PASTA, str(tmp_path / "acervo"))
    monkeypatch.setenv(vc.VARIAVEL, VERSAO)
    monkeypatch.setattr(coletor, "PAUSA_ENTRE_DOWNLOADS", 0)
    migrar_para("head", url=url)
    ipe = _zip(
        _linha(*COMUNICADO, "Aquisição da Delta", entrega="2024-06-01", protocolo="4"),
        _linha(*FATO, "Fato Relevante", entrega="2024-05-01", protocolo="3"),
        _linha(*FATO, "Aquisição da Beta", entrega="2024-03-05", protocolo="1"),
        _linha(
            *FATO, "Aquisição da Beta", entrega="2024-03-09", protocolo="6", versao="2"
        ),
        _linha(*OPA, "Edital", entrega="2024-02-01", protocolo="2"),
    )
    endereco = ma_ipe.URL_DO_IPE.format(ano=2024)
    quando = datetime(2026, 10, 18, 23, tzinfo=UTC)
    caminho = acervo.guardar_original(ma_ipe.FONTE_DO_IPE, endereco, ipe, quando)
    with criar_engine().begin() as c:
        registrar(c, ma_ipe.FONTE_DO_IPE, endereco, ipe, "ok", agora=quando,
                  caminho_do_original=caminho)  # fmt: skip
    return tmp_path


def _rad_falso(monkeypatch, respostas: dict[str, bytes | None]) -> list[str]:
    """O RAD de mentira: a resposta de cada `protocolo-versao`; quem não está, página de limite."""
    pedidos: list[str] = []

    def baixar(endereco: str) -> bytes | None:
        chave = endereco.split("numProtocolo=")[1].replace("&numVersao=", "-")
        pedidos.append(chave)
        return coletor.conferir_documento(respostas.get(chave, PAGINA_DE_LIMITE))

    monkeypatch.setattr(
        coletor, "baixar", coletor.com_registro(mt.FONTE_DOS_DOCUMENTOS, baixar)
    )
    return pedidos


def _situacoes() -> list[str]:
    with criar_engine().connect() as c:
        return sorted(
            c.execute(
                sa.select(coletas.c.situacao).where(
                    coletas.c.fonte == mt.FONTE_DOS_DOCUMENTOS
                )
            ).scalars()
        )


def _textos(ambiente) -> list[str]:
    return sorted(p.name for p in (ambiente / "acervo" / mt.PASTA_DOS_TEXTOS).iterdir())


# --- a fila ---------------------------------------------------------------------------------------
def _candidatos(ambiente) -> pd.DataFrame:
    with criar_engine().connect() as c:
        return ma_ipe.candidatos_guardados(c)[0]


def _ordem(fila: pd.DataFrame) -> list[str]:
    return [f"{p}-{v}" for p, v in zip(fila["protocolo"], fila["versao"], strict=True)]


def test_fila_com_tipo_e_opa_antes_do_generico_e_do_comunicado(ambiente):
    fila = mt.fila(_candidatos(ambiente), set(), {})
    # com tipo e OPA, do mais novo ao mais velho; depois o genérico; o comunicado por último
    assert _ordem(fila) == ["6-2", "1-1", "2-1", "3-1", "4-1"]


def test_fila_pedidos_primeiro_e_sem_o_que_ja_veio(ambiente):
    candidatos = _candidatos(ambiente)
    veio = set(candidatos.loc[candidatos["protocolo"].eq("2"), "link"])
    fila = mt.fila(candidatos, veio, {}, pedidos={"4"})
    assert _ordem(fila) == ["4-1", "6-2", "1-1", "3-1"]


def test_documento_que_voltou_pagina_tres_vezes_vai_para_o_fim(ambiente):
    candidatos = _candidatos(ambiente)
    link = candidatos.loc[candidatos["protocolo"].eq("2"), "link"].iloc[0]
    assert _ordem(mt.fila(candidatos, set(), {link: 2}))[2] == "2-1"
    assert _ordem(mt.fila(candidatos, set(), {link: 3}))[-1] == "2-1"


def test_fila_aceita_documento_antigo_sem_versao(ambiente):
    # até 2015 o IPE não traz a versão (~8.600 candidatos)
    candidatos = _candidatos(ambiente)
    candidatos.loc[candidatos["protocolo"].eq("3"), "versao"] = pd.NA
    assert len(mt.fila(candidatos, set(), {})) == len(candidatos)


# --- a coleta -------------------------------------------------------------------------------------
def test_baixa_guarda_o_original_e_grava_o_texto(ambiente, monkeypatch):
    pedidos = _rad_falso(
        monkeypatch, {"6-2": _pdf(), "1-1": None, "2-1": b"PK\x03\x04[Content_Types]"}
    )
    assert coletor.main(["--maximo", "3"]) == 0
    assert pedidos == ["6-2", "1-1", "2-1"]
    assert _situacoes() == ["nao_encontrado", "ok", "ok"]
    # o Word não tem texto que a leitura aceite: fica marcado, para não pedir de novo
    assert _textos(ambiente) == ["2.sem_texto", "6.txt"]
    texto = (ambiente / "acervo" / mt.PASTA_DOS_TEXTOS / "6.txt").read_text("utf-8")
    assert "adquirir a totalidade das ações da Gama" in texto


def test_nao_pede_de_novo_o_que_ja_veio(ambiente, monkeypatch):
    pedidos = _rad_falso(monkeypatch, {"6-2": _pdf(), "1-1": None})
    coletor.main(["--maximo", "2"])
    _rad_falso(monkeypatch, {"2-1": _pdf(), "3-1": _pdf()})
    pedidos = _rad_falso(monkeypatch, {"2-1": _pdf(), "3-1": _pdf()})
    coletor.main(["--maximo", "2"])
    assert pedidos == ["2-1", "3-1"]


def test_duas_paginas_seguidas_param_sem_erro(ambiente, monkeypatch):
    pedidos = _rad_falso(monkeypatch, {})
    assert coletor.main(["--maximo", "10"]) == 0  # o limite não é erro
    assert pedidos == ["6-2", "1-1"]
    assert _situacoes() == ["falhou", "falhou"]


def test_documento_quebrado_nao_trava_a_fila(ambiente, monkeypatch):
    # o 1º volta página (quebrado na fonte), os seguintes vêm: a rodada segue
    pedidos = _rad_falso(monkeypatch, {"1-1": _pdf(), "2-1": _pdf()})
    coletor.main(["--maximo", "3"])
    assert pedidos == ["6-2", "1-1", "2-1"]
    # na 4ª rodada ele já voltou página 3 vezes e vai para o fim
    for _ in range(2):
        coletor.main(["--maximo", "1"])
    pedidos = _rad_falso(monkeypatch, {"3-1": _pdf()})
    coletor.main(["--maximo", "1"])
    assert pedidos == ["3-1"]


def test_pedidos_vem_de_um_arquivo(ambiente, monkeypatch, tmp_path):
    lista = tmp_path / "pedidos.txt"
    lista.write_text("# conferência\n3\n\n", encoding="utf-8")
    assert coletor.ler_pedidos(lista) == {"3"}
    pedidos = _rad_falso(monkeypatch, {"3-1": _pdf()})
    coletor.main(["--maximo", "1", "--pedidos", str(lista)])
    assert pedidos == ["3-1"]


# --- o texto ------------------------------------------------------------------------------------
@pytest.mark.parametrize("categoria", ["Fato Relevante", "Comunicado ao Mercado"])
def test_texto_igual_ao_da_rotulagem_que_baixou_a_amostra_de_ouro(categoria):
    # a medida da extração (91,5%) foi feita com os textos da rotulagem: a base precisa do mesmo
    conteudo = _pdf()
    assert mt.texto_do_documento(conteudo, categoria) == (
        rotular_com_ia.texto_do_conteudo(conteudo, {"categoria": categoria})
    )


def test_texto_do_fato_sem_cabecalho_e_cortado_no_maximo():
    texto = mt.texto_do_documento(_pdf(" ".join([TEXTO] * 100)), "Fato Relevante")
    assert texto.startswith("A Companhia Beta")  # sem o cabeçalho até o título
    assert len(texto) == mt.MAX_CARACTERES_GUARDADOS
    assert mt.MAX_CARACTERES_GUARDADOS == rotular_com_ia.MAX_CARACTERES_GUARDADOS
    assert mt.texto_do_documento(PAGINA_DE_LIMITE, "Fato Relevante") == ""


# --- documentos antigos: o "protocolo" é o link do RAD ---------------------------------------------
LINK_ANTIGO = (
    "https://www.rad.cvm.gov.br/ENET/frmDownloadDocumento.aspx?Tela=ext&descTipo=IPE"
    "&CodigoInstituicao=1&numProtocolo=25694&numSequencia=0&numVersao=0"
)


@pytest.mark.parametrize(
    ("protocolo", "nome"),
    [
        ("002437IPE100420190104356511-54", "002437IPE100420190104356511-54"),
        (LINK_ANTIGO, "cvm-25694-0-0"),
    ],
)
def test_nome_do_texto_e_o_protocolo_ou_os_numeros_do_link(protocolo, nome):
    assert mt.nome_do_texto(protocolo) == nome


def test_nome_do_texto_nunca_tem_pasta():
    nome = mt.nome_do_texto("https://outro.endereco/doc?id=7")
    assert mt.NOME_SEGURO.fullmatch(nome) and nome.startswith("doc-")


def test_documento_antigo_grava_o_texto_com_o_nome_seguro(tmp_path, monkeypatch):
    # até ~2010 o IPE traz o link no lugar do protocolo: gravar com ele criaria pastas "https:/..."
    monkeypatch.setattr(coletor, "baixar", lambda _link: _pdf())
    fila = pd.DataFrame(
        {
            "protocolo": [LINK_ANTIGO],
            "link": [LINK_ANTIGO],
            "categoria": [mt.FATO_RELEVANTE],
        }
    )
    rodada = coletor.coletar(fila, 1, tmp_path)
    assert (rodada.pedidos, rodada.textos) == (1, 1)
    assert [p.name for p in tmp_path.iterdir()] == ["cvm-25694-0-0.txt"]
