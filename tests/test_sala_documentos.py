"""Os documentos da sala de ponta a ponta (B-20, PR 2): receber, ler, baixar e apagar.

Banco em SQLite na memória, disco numa pasta temporária, chave-mestra gerada no teste e a leitura
num subprocesso de verdade. Os riscos que estes testes travam: uma conta abrir o arquivo de outra,
o arquivo ficar legível no disco, o CPF sair sem máscara e o nome do arquivo ir para log ou
auditoria.
"""

import ast
import json
import logging
import shutil
import uuid
from datetime import date
from pathlib import Path

import pytest
import sqlalchemy as sa

from src import auditoria, conformidade
from src.banco import sala
from src.banco.modelo import auditoria as tabela_da_auditoria
from src.banco.modelo import documentos_da_sala, metadata, operacoes
from src.banco.usuarios import entrar
from src.sala import arquivos, cofre, documentos, guarda, leitura
from tests import ajudantes_da_sala as gerar

HOJE = date(2026, 10, 21)
NOME_SENSIVEL = "Laudo da Fulana de Tal 123.pdf"
PASTA_DA_SALA = Path(__file__).resolve().parent.parent / "src" / "sala"


@pytest.fixture(autouse=True)
def chave_mestra(monkeypatch):
    monkeypatch.setenv(cofre.VARIAVEL_DA_CHAVE_MESTRA, cofre.gerar_chave_mestra())


@pytest.fixture
def raiz(tmp_path, monkeypatch):
    pasta = tmp_path / "dados_sala"
    monkeypatch.setenv(guarda.VARIAVEL_DA_PASTA, str(pasta))
    return pasta


@pytest.fixture
def motor():
    motor = sa.create_engine("sqlite://", poolclass=sa.pool.StaticPool)
    sa.event.listen(motor, "connect", lambda c, _: c.execute("PRAGMA foreign_keys=ON"))
    metadata.create_all(motor)
    return motor


@pytest.fixture
def conexao(motor):
    with motor.begin() as conexao:
        yield conexao


@pytest.fixture
def ana(conexao):
    return entrar(conexao, "ana", "ana@exemplo.com", "Ana")[0]


@pytest.fixture
def bia(conexao):
    return entrar(conexao, "bia", "bia@exemplo.com", "Bia")[0]


def _operacao(conexao, dono, nome="Aquisição da Alfa"):
    return sala.criar_operacao(
        conexao, usuario_id=dono.id, tipo="ma", nome=nome, hoje=HOJE
    )


def _receber(conexao, dono, operacao, conteudo=None, nome=NOME_SENSIVEL):
    return documentos.receber_documento(
        conexao,
        usuario_id=dono.id,
        operacao_id=operacao.id,
        nome_original=nome,
        conteudo=gerar.pdf("Balanço da Alfa") if conteudo is None else conteudo,
    )


def _ids(dono, documento):
    return {
        "usuario_id": dono.id,
        "operacao_id": documento.operacao_id,
        "documento_id": documento.id,
    }


def _auditoria(conexao):
    return conexao.execute(
        sa.select(tabela_da_auditoria).order_by(tabela_da_auditoria.c.criado_em)
    ).all()


# --- receber ------------------------------------------------------------------------------


def test_recebe_cifra_e_guarda_e_o_disco_nao_tem_o_conteudo(conexao, ana, raiz):
    operacao = _operacao(conexao, ana)
    conteudo = gerar.pdf("Balanço da Alfa")
    recebimento = _receber(conexao, ana, operacao, conteudo)
    documento = recebimento.documento
    assert recebimento.recusa is None and documento.tipo == "pdf"
    assert documento.situacao == "na_fila" and documento.tamanho_bytes == len(conteudo)
    arquivo = guarda.caminho_do_documento(raiz, operacao.id, documento.id, "original")
    no_disco = arquivo.read_bytes()
    assert b"Balan" not in no_disco and b"%PDF" not in no_disco
    nonce = sala.nonce_do_documento(conexao, **_ids(ana, documento))
    assert nonce == no_disco[: cofre.BYTES_DO_NONCE]
    aberto = documentos.abrir_documento(conexao, **_ids(ana, documento))
    assert aberto.conteudo == conteudo


def test_a_chave_da_operacao_nasce_no_primeiro_envio_e_fica(conexao, ana, raiz):
    operacao = _operacao(conexao, ana)
    da_sala = {"usuario_id": ana.id, "operacao_id": operacao.id}
    assert sala.chave_da_operacao(conexao, **da_sala) is None
    _receber(conexao, ana, operacao, gerar.pdf("um"))
    primeira = sala.chave_da_operacao(conexao, **da_sala)
    _receber(conexao, ana, operacao, gerar.pdf("dois"))
    assert sala.chave_da_operacao(conexao, **da_sala) == primeira
    assert primeira[1] == 1


def test_dois_envios_ao_mesmo_tempo_numa_sala_nova_ficam_com_a_mesma_chave(
    conexao, ana, raiz, monkeypatch
):
    """Se outro envio gravou a chave entre a leitura e a gravação, usa a que ficou."""
    operacao = _operacao(conexao, ana)
    da_sala = {"usuario_id": ana.id, "operacao_id": operacao.id}
    chave_do_outro, embrulhada, versao = cofre.nova_chave_da_operacao(operacao.id)
    original = sala.guardar_chave_da_operacao

    def outro_chegou_antes(conexao, **kwargs):
        original(conexao, **da_sala, chave_cifrada=embrulhada, versao_da_chave=versao)
        return original(conexao, **kwargs)

    monkeypatch.setattr(sala, "guardar_chave_da_operacao", outro_chegou_antes)
    documento = _receber(conexao, ana, operacao).documento
    assert sala.chave_da_operacao(conexao, **da_sala) == (embrulhada, versao)
    cifrado = guarda.ler(
        guarda.caminho_do_documento(raiz, operacao.id, documento.id, "original")
    )
    ids = {
        "operacao_id": operacao.id,
        "documento_id": documento.id,
        "parte": "original",
    }
    assert cofre.decifrar_documento(chave_do_outro, cifrado, **ids).startswith(b"%PDF")


@pytest.mark.parametrize(
    ("gerador", "nome", "motivo"),
    [
        pytest.param(gerar.pdf_com_javascript, "a.pdf", arquivos.PDF_ATIVO, id="js"),
        pytest.param(gerar.xlsx_com_macro, "a.xlsx", arquivos.COM_MACRO, id="macro"),
        pytest.param(gerar.zip_bomba, "a.xlsx", arquivos.ZIP_GRANDE_DEMAIS, id="bomba"),
        pytest.param(lambda: gerar.OLE, "a.xls", arquivos.TIPO_NAO_ACEITO, id="xls"),
    ],
)
def test_arquivo_recusado_fica_na_auditoria_so_com_o_motivo(
    conexao, ana, raiz, gerador, nome, motivo
):
    operacao = _operacao(conexao, ana)
    conteudo = gerador()
    recebimento = _receber(conexao, ana, operacao, conteudo, nome=f"Fulana {nome}")
    assert recebimento == documentos.Recebimento(None, motivo)
    assert (
        sala.listar_documentos(conexao, usuario_id=ana.id, operacao_id=operacao.id)
        == []
    )
    assert not (raiz / str(operacao.id)).exists()
    recusa = [
        r for r in _auditoria(conexao) if r.acao == auditoria.ACAO_DOCUMENTO_RECUSADO
    ]
    assert len(recusa) == 1
    assert recusa[0].alvo_id == operacao.id
    detalhes = recusa[0].detalhes
    if isinstance(detalhes, str):
        detalhes = json.loads(detalhes)
    assert detalhes == {"motivo": motivo, "tamanho_bytes": len(conteudo)}


def test_o_mesmo_arquivo_duas_vezes_na_sala_e_recusado(conexao, ana, raiz):
    operacao = _operacao(conexao, ana)
    # Os mesmos bytes nas duas vezes: cada `gerar.pdf` grava a hora de criação (ao segundo)
    # dentro do PDF, e duas chamadas na virada do segundo dariam hashes diferentes.
    conteudo = gerar.pdf("Balanço da Alfa")
    _receber(conexao, ana, operacao, conteudo)
    with pytest.raises(sala.DocumentoRepetidoError):
        _receber(conexao, ana, operacao, conteudo)


def test_sem_a_chave_mestra_nada_entra(conexao, ana, raiz, monkeypatch):
    operacao = _operacao(conexao, ana)
    monkeypatch.delenv(cofre.VARIAVEL_DA_CHAVE_MESTRA)
    with pytest.raises(cofre.ChaveDaSalaAusenteError):
        _receber(conexao, ana, operacao)


def test_com_o_disco_quase_cheio_nada_entra(conexao, ana, raiz, monkeypatch):
    operacao = _operacao(conexao, ana)
    monkeypatch.setattr(guarda, "conferir_espaco_livre", _sem_espaco)
    with pytest.raises(guarda.SalaSemEspacoError):
        _receber(conexao, ana, operacao)


def _sem_espaco(_):
    raise guarda.SalaSemEspacoError("cheio")


# --- isolamento entre contas --------------------------------------------------------------


def test_outra_conta_nao_envia_abre_baixa_le_nem_apaga(motor, conexao, ana, bia, raiz):
    operacao = _operacao(conexao, ana)
    documento = _receber(conexao, ana, operacao).documento
    da_bia = _ids(bia, documento)
    assert _receber(conexao, bia, operacao) is None
    assert documentos.abrir_documento(conexao, **da_bia) is None
    assert documentos.baixar_documento(conexao, **da_bia) is None
    assert documentos.texto_do_documento(conexao, **da_bia) is None
    assert documentos.apagar_documento(conexao, **da_bia) is False
    assert (
        documentos.apagar_operacao(conexao, usuario_id=bia.id, operacao_id=operacao.id)
        is False
    )
    conexao.commit()
    assert documentos.ler_documento(motor, **da_bia) is None
    assert guarda.caminho_do_documento(
        raiz, operacao.id, documento.id, "original"
    ).exists()
    with motor.begin() as outra:
        assert documentos.abrir_documento(outra, **_ids(ana, documento)) is not None


def test_sala_sem_chave_nao_abre(conexao, ana, raiz):
    """O arquivo copiado para outra sala (mesmo com o nonce certo no banco) não decifra."""
    sala_a, sala_b = _operacao(conexao, ana), _operacao(conexao, ana, nome="Outra")
    doc_a = _receber(conexao, ana, sala_a, gerar.pdf("A")).documento
    doc_b = _receber(conexao, ana, sala_b, gerar.pdf("B")).documento
    de_a = guarda.caminho_do_documento(raiz, sala_a.id, doc_a.id, "original")
    em_b = guarda.caminho_do_documento(raiz, sala_b.id, doc_b.id, "original")
    shutil.copyfile(de_a, em_b)
    with pytest.raises(cofre.CifraInvalidaError):  # o nonce do banco não bate
        documentos.abrir_documento(conexao, **_ids(ana, doc_b))
    sala.guardar_nonce(
        conexao, **_ids(ana, doc_b), nonce=de_a.read_bytes()[: cofre.BYTES_DO_NONCE]
    )
    with pytest.raises(
        cofre.CifraInvalidaError
    ):  # e a cifra é presa à sala e ao documento
        documentos.abrir_documento(conexao, **_ids(ana, doc_b))


def test_abrir_e_ler_nunca_criam_chave(motor, ana, raiz):
    """Só o envio cria a chave da operação; sem ela, abrir e ler dão erro e não gravam nada."""
    with motor.begin() as conexao:
        operacao = _operacao(conexao, ana)
        documento = _receber(conexao, ana, operacao).documento
        sem_chave = {"chave_cifrada": None, "versao_da_chave": None}
        conexao.execute(sa.update(operacoes).values(**sem_chave))
        with pytest.raises(cofre.CifraInvalidaError):
            documentos.abrir_documento(conexao, **_ids(ana, documento))
    situacao = documentos.ler_documento(motor, **_ids(ana, documento))
    assert situacao == "erro_na_leitura"
    with motor.begin() as conexao:
        da_sala = {"usuario_id": ana.id, "operacao_id": operacao.id}
        assert sala.chave_da_operacao(conexao, **da_sala) is None


def test_apagar_a_operacao_some_com_a_chave(conexao, ana, raiz):
    operacao = _operacao(conexao, ana)
    _receber(conexao, ana, operacao)
    assert documentos.apagar_operacao(
        conexao, usuario_id=ana.id, operacao_id=operacao.id
    )
    assert not (raiz / str(operacao.id)).exists()
    assert conexao.execute(sa.select(operacoes.c.id)).all() == []


# --- baixar -------------------------------------------------------------------------------


def test_baixar_fica_na_auditoria_so_com_ids(conexao, ana, raiz):
    operacao = _operacao(conexao, ana)
    documento = _receber(conexao, ana, operacao).documento
    aberto = documentos.baixar_documento(conexao, **_ids(ana, documento))
    assert aberto.conteudo.startswith(b"%PDF")
    baixados = [
        r for r in _auditoria(conexao) if r.acao == auditoria.ACAO_DOCUMENTO_BAIXADO
    ]
    assert [r.alvo_id for r in baixados] == [documento.id]


def test_arquivo_adulterado_ou_sumido_no_disco(conexao, ana, raiz):
    operacao = _operacao(conexao, ana)
    documento = _receber(conexao, ana, operacao).documento
    caminho = guarda.caminho_do_documento(raiz, operacao.id, documento.id, "original")
    adulterado = bytearray(caminho.read_bytes())
    adulterado[-1] ^= 1
    caminho.write_bytes(bytes(adulterado))
    with pytest.raises(cofre.CifraInvalidaError):
        documentos.abrir_documento(conexao, **_ids(ana, documento))
    caminho.unlink()
    with pytest.raises(FileNotFoundError):
        documentos.abrir_documento(conexao, **_ids(ana, documento))


# --- ler ----------------------------------------------------------------------------------


def _recebido(motor, dono, conteudo, nome=NOME_SENSIVEL):
    with motor.begin() as conexao:
        operacao = _operacao(conexao, dono)
        return _receber(conexao, dono, operacao, conteudo, nome=nome).documento


def test_ler_guarda_o_texto_cifrado_e_com_o_cpf_mascarado(motor, ana, raiz):
    conteudo = gerar.pdf(f"Socio CPF {gerar.CPF_VALIDO}", "Receita 100")
    documento = _recebido(motor, ana, conteudo)
    assert documentos.ler_documento(motor, **_ids(ana, documento)) == "lido"
    with motor.begin() as conexao:
        lido = sala.buscar_documento(conexao, **_ids(ana, documento))
        texto = documentos.texto_do_documento(conexao, **_ids(ana, documento))
    assert lido.situacao == "lido" and lido.paginas == 2
    assert lido.lido_por == leitura.VERSAO_DO_LEITOR
    assert texto == ["Socio CPF ***.***.***-25", "Receita 100"]
    no_disco = guarda.caminho_do_documento(
        raiz, documento.operacao_id, documento.id, "texto"
    )
    cifrado = no_disco.read_bytes()
    assert b"Receita" not in cifrado and b"529" not in cifrado


def test_documento_sem_texto_nao_grava_texto(motor, ana, raiz):
    documento = _recebido(motor, ana, gerar.pdf(""))
    assert documentos.ler_documento(motor, **_ids(ana, documento)) == "sem_texto"
    with motor.begin() as conexao:
        assert documentos.texto_do_documento(conexao, **_ids(ana, documento)) is None
    texto = guarda.caminho_do_documento(
        raiz, documento.operacao_id, documento.id, "texto"
    )
    assert not texto.exists()


def test_leitura_que_falha_marca_erro_e_nao_derruba(motor, ana, raiz, monkeypatch):
    documento = _recebido(motor, ana, gerar.pdf("x"))
    monkeypatch.setattr(leitura, "ler_em_subprocesso", lambda *_: leitura.ERRO)
    assert documentos.ler_documento(motor, **_ids(ana, documento)) == "erro_na_leitura"
    with motor.begin() as conexao:
        assert sala.buscar_documento(conexao, **_ids(ana, documento)).situacao == (
            "erro_na_leitura"
        )


def test_arquivo_sumido_do_disco_vira_erro_na_leitura(motor, ana, raiz):
    documento = _recebido(motor, ana, gerar.pdf("x"))
    guarda.apagar_documento(raiz, documento.operacao_id, documento.id)
    assert documentos.ler_documento(motor, **_ids(ana, documento)) == "erro_na_leitura"


def test_documento_apagado_durante_a_leitura_nao_volta(motor, ana, raiz, monkeypatch):
    documento = _recebido(motor, ana, gerar.pdf("x"))
    lido = leitura.Leitura("lido", ("texto",))

    def apaga_enquanto_le(*_):
        with motor.begin() as conexao:
            documentos.apagar_documento(conexao, **_ids(ana, documento))
        return lido

    monkeypatch.setattr(leitura, "ler_em_subprocesso", apaga_enquanto_le)
    assert documentos.ler_documento(motor, **_ids(ana, documento)) is None
    assert not (raiz / str(documento.operacao_id) / f"{documento.id}.txt.bin").exists()


def test_a_leitura_nao_segura_transacao_aberta(motor, ana, raiz, monkeypatch):
    """Enquanto o filho lê (até um minuto), o banco fica livre: nenhuma conexão emprestada."""
    documento = _recebido(motor, ana, gerar.pdf("x"))
    abertas = [0]
    sa.event.listen(
        motor, "checkout", lambda *_: abertas.__setitem__(0, abertas[0] + 1)
    )
    sa.event.listen(motor, "checkin", lambda *_: abertas.__setitem__(0, abertas[0] - 1))
    emprestadas = []
    original = leitura.ler_em_subprocesso

    def conta_conexoes(*args):
        emprestadas.append(abertas[0])
        return original(*args)

    monkeypatch.setattr(leitura, "ler_em_subprocesso", conta_conexoes)
    documentos.ler_documento(motor, **_ids(ana, documento))
    assert emprestadas == [0]


# --- apagar e LGPD ------------------------------------------------------------------------


def test_apagar_documento_tira_do_banco_e_do_disco(motor, ana, raiz):
    documento = _recebido(motor, ana, gerar.pdf("x"))
    documentos.ler_documento(motor, **_ids(ana, documento))
    with motor.begin() as conexao:
        assert documentos.apagar_documento(conexao, **_ids(ana, documento))
        assert conexao.execute(sa.select(documentos_da_sala.c.id)).all() == []
    assert list((raiz / str(documento.operacao_id)).iterdir()) == []


def test_apagar_a_conta_leva_os_arquivos_dela_e_so_os_dela(conexao, ana, bia, raiz):
    da_ana = _receber(conexao, ana, _operacao(conexao, ana)).documento
    da_bia = _receber(conexao, bia, _operacao(conexao, bia)).documento
    assert conformidade.apagar_conta(conexao, ana.id)
    assert not (raiz / str(da_ana.operacao_id)).exists()
    assert (raiz / str(da_bia.operacao_id) / f"{da_bia.id}.bin").exists()


# --- o que não pode vazar ----------------------------------------------------------------


def test_nome_do_arquivo_e_texto_nunca_vao_para_log_nem_auditoria(
    motor, ana, raiz, caplog
):
    caplog.set_level(logging.DEBUG)
    conteudo = gerar.pdf(f"CPF {gerar.CPF_VALIDO} segredo")
    documento = _recebido(motor, ana, conteudo)
    documentos.ler_documento(motor, **_ids(ana, documento))
    with motor.begin() as conexao:
        operacao = sala.buscar_operacao(
            conexao, usuario_id=ana.id, operacao_id=documento.operacao_id
        )
        _receber(conexao, ana, operacao, gerar.pdf_com_javascript(), nome="Fulana.pdf")
        documentos.baixar_documento(conexao, **_ids(ana, documento))
        documentos.apagar_documento(conexao, **_ids(ana, documento))
        registros = " ".join(str(tuple(r)) for r in _auditoria(conexao))
    logs = caplog.text
    for vazamento in ("Fulana", "segredo", "529.982", "52998"):
        assert vazamento not in logs, vazamento
        assert vazamento not in registros, vazamento


def test_a_sala_nao_importa_modelo_de_linguagem_nem_cliente_de_rede():
    """D9: nenhum modelo lê o documento, e nada da sala fala com a internet."""
    proibidos = {
        "anthropic",
        "httpx",
        "requests",
        "urllib",
        "socket",
        "curl_cffi",
        "http",
    }
    for arquivo in PASTA_DA_SALA.glob("*.py"):
        for no in ast.walk(ast.parse(arquivo.read_text(encoding="utf-8"))):
            nomes = []
            if isinstance(no, ast.Import):
                nomes = [a.name for a in no.names]
            elif isinstance(no, ast.ImportFrom) and no.module:
                nomes = [no.module]
            for nome in nomes:
                assert nome.split(".")[0] not in proibidos, (arquivo.name, nome)
                assert not nome.startswith("src.analise_escrita"), (arquivo.name, nome)


def test_toda_funcao_publica_pede_a_conta_pelo_nome():
    funcoes = [
        documentos.receber_documento,
        documentos.abrir_documento,
        documentos.baixar_documento,
        documentos.ler_documento,
        documentos.texto_do_documento,
        documentos.apagar_documento,
        documentos.apagar_operacao,
        documentos.apagar_arquivos_da_conta,
    ]
    import inspect

    for funcao in funcoes:
        parametro = inspect.signature(funcao).parameters["usuario_id"]
        assert parametro.kind is inspect.Parameter.KEYWORD_ONLY, funcao.__name__


def test_uuid_qualquer_nao_e_documento(conexao, ana, raiz):
    operacao = _operacao(conexao, ana)
    ids = {
        "usuario_id": ana.id,
        "operacao_id": operacao.id,
        "documento_id": uuid.uuid4(),
    }
    assert documentos.abrir_documento(conexao, **ids) is None
