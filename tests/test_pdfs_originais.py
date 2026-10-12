"""PDF original dos relatórios na biblioteca (Master v3, Fase C.4; ADR 0021 do autor)."""

import io
import uuid
import zipfile
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

from src.banco import dados_do_usuario as repo
from src.banco import pdfs_originais as pdfs
from src.banco import usuarios as contas
from src.banco.conexao import criar_engine, desfazer_ate, migrar_para
from src.banco.modelo import pdfs_originais
from src.conformidade import apagar_conta, exportar_meus_dados
from src.planos import limites_do

AGORA = datetime(2026, 10, 12, 15, 0, tzinfo=UTC)
PDF = b"%PDF-1.7 relatorio de exemplo"
VERSOES = {"tipo": "ativo", "formulas": {"rsi": 1}, "relatorios": "2"}


def _usuario(conexao, sub, plano="gratuito"):
    usuario, _ = contas.entrar(conexao, sub, f"{sub}@exemplo.com")
    contas.mudar_plano(conexao, usuario.id, plano)
    return usuario.id


def _relatorio(conexao, usuario_id, tipo="ativo", agora=AGORA):
    return repo.registrar_relatorio(
        conexao, usuario_id, tipo, titulo="PETR4", agora=agora
    )


def _guardar(conexao, usuario_id, rid, plano="gratuito", pdf=PDF, agora=AGORA):
    return pdfs.guardar_pdf_original(
        conexao, usuario_id, rid, plano, pdf, VERSOES, agora=agora
    )


def test_guarda_e_devolve_o_mesmo_arquivo_com_hash(banco):
    with banco.begin() as c:
        ana = _usuario(c, "ana")
        rid = _relatorio(c, ana)
        assert _guardar(c, ana, rid)
        (guardado,) = pdfs.pdfs_guardados(c, ana, agora=AGORA).values()
        assert guardado.tamanho == len(PDF)
        assert len(guardado.sha256) == 64
        assert pdfs.baixar_pdf_original(c, ana, rid, agora=AGORA) == PDF


def test_cada_um_so_ve_e_baixa_os_seus(banco):
    with banco.begin() as c:
        ana, bia = _usuario(c, "ana"), _usuario(c, "bia")
        rid_ana = _relatorio(c, ana)
        _guardar(c, ana, rid_ana)
        assert pdfs.baixar_pdf_original(c, bia, rid_ana, agora=AGORA) is None
        assert pdfs.pdfs_guardados(c, bia, agora=AGORA) == {}
        # a bia não consegue guardar um PDF no relatório da ana
        assert not _guardar(c, bia, rid_ana, pdf=b"%PDF outro")
        assert pdfs.baixar_pdf_original(c, ana, rid_ana, agora=AGORA) == PDF
        # nem apagar o da ana
        pdfs.apagar_pdf_original(c, bia, rid_ana)
        assert repo.excluir_relatorio(c, bia, rid_ana) is False
        assert pdfs.baixar_pdf_original(c, ana, rid_ana, agora=AGORA) == PDF


def test_minha_carteira_nunca_e_guardada(banco):
    with banco.begin() as c:
        ana = _usuario(c, "ana", "pro")
        rid = _relatorio(c, ana, tipo="minha_carteira")
        assert not _guardar(c, ana, rid, plano="pro")
        assert pdfs.pdfs_guardados(c, ana, agora=AGORA) == {}


@pytest.mark.parametrize("plano", ["gratuito", "plus"])
def test_cota_do_plano_tira_os_mais_antigos(banco, plano):
    cota = limites_do(plano).pdfs_guardados
    with banco.begin() as c:
        ana = _usuario(c, "ana", plano)
        ids = []
        for i in range(cota + 3):
            quando = AGORA + timedelta(minutes=i)
            rid = _relatorio(c, ana, agora=quando)
            _guardar(c, ana, rid, plano=plano, agora=quando)
            ids.append(rid)
        guardados = pdfs.pdfs_guardados(c, ana, agora=AGORA + timedelta(hours=1))
        assert set(guardados) == set(ids[-cota:])  # os 3 mais antigos saíram


def test_depois_de_um_ano_o_pdf_some(banco):
    depois = AGORA + timedelta(days=pdfs.DIAS_GUARDADO + 1)
    with banco.begin() as c:
        ana = _usuario(c, "ana")
        rid = _relatorio(c, ana)
        _guardar(c, ana, rid)
        assert pdfs.baixar_pdf_original(c, ana, rid, agora=depois) is None
        assert pdfs.pdfs_guardados(c, ana, agora=depois) == {}
        # a manutenção apaga de verdade (de todos os usuários), sem ler nada
        assert pdfs.apagar_pdfs_vencidos(c, agora=depois) == 1
        assert (
            c.execute(sa.select(sa.func.count()).select_from(pdfs_originais)).scalar()
            == 0
        )


def test_guardar_um_novo_apaga_os_vencidos_da_mesma_pessoa(banco):
    depois = AGORA + timedelta(days=pdfs.DIAS_GUARDADO + 1)
    with banco.begin() as c:
        ana = _usuario(c, "ana")
        velho = _relatorio(c, ana)
        _guardar(c, ana, velho)
        novo = _relatorio(c, ana, agora=depois)
        _guardar(c, ana, novo, agora=depois)
        linhas = c.execute(sa.select(pdfs_originais.c.relatorio_id)).scalars().all()
        assert linhas == [novo]


def test_arquivo_alterado_no_banco_nao_e_entregue(banco):
    with banco.begin() as c:
        ana = _usuario(c, "ana")
        rid = _relatorio(c, ana)
        _guardar(c, ana, rid)
        c.execute(
            sa.update(pdfs_originais)
            .where(pdfs_originais.c.relatorio_id == rid)
            .values(pdf=b"%PDF adulterado")
        )
        assert pdfs.baixar_pdf_original(c, ana, rid, agora=AGORA) is None


@pytest.mark.parametrize(
    "tamanho", [0, pdfs.TAMANHO_MAXIMO_DO_PDF + 1], ids=["vazio", "enorme"]
)
def test_pdf_vazio_ou_enorme_e_recusado(banco, tamanho):
    with banco.begin() as c:
        ana = _usuario(c, "ana")
        rid = _relatorio(c, ana)
        with pytest.raises(ValueError, match="vazio ou é grande demais"):
            _guardar(c, ana, rid, pdf=b"x" * tamanho)


def test_excluir_da_biblioteca_apaga_o_original(banco):
    with banco.begin() as c:
        ana = _usuario(c, "ana")
        rid = _relatorio(c, ana)
        _guardar(c, ana, rid)
        assert repo.excluir_relatorio(c, ana, rid, agora=AGORA)
        assert pdfs.baixar_pdf_original(c, ana, rid, agora=AGORA) is None


def test_apagar_a_conta_apaga_os_originais(banco):
    with banco.begin() as c:
        ana, bia = _usuario(c, "ana"), _usuario(c, "bia")
        _guardar(c, ana, _relatorio(c, ana))
        _guardar(c, bia, _relatorio(c, bia))
        assert apagar_conta(c, ana)
        donos = c.execute(sa.select(pdfs_originais.c.usuario_id)).scalars().all()
        assert donos == [bia]


def test_exportacao_lista_o_hash_e_o_zip_traz_os_arquivos(banco):
    with banco.begin() as c:
        ana = _usuario(c, "ana")
        rid = _relatorio(c, ana)
        _guardar(c, ana, rid)
        _relatorio(c, ana, tipo="minha_carteira")  # sem original
        exportado = exportar_meus_dados(c, ana)["relatorios_em_pdf"]
        com_original = [r for r in exportado if r["pdf_original"]]
        assert len(exportado) == 2 and len(com_original) == 1
        assert com_original[0]["pdf_original"]["tamanho"] == len(PDF)
        with zipfile.ZipFile(io.BytesIO(pdfs.pdfs_em_zip(c, ana, agora=AGORA))) as z:
            (nome,) = z.namelist()
            assert nome.endswith(".pdf") and z.read(nome) == PDF


def test_zip_sem_pdf_guardado_ainda_abre(banco):
    with banco.begin() as c:
        ana = _usuario(c, "ana")
        with zipfile.ZipFile(io.BytesIO(pdfs.pdfs_em_zip(c, ana, agora=AGORA))) as z:
            assert z.namelist() == ["LEIA-ME.txt"]


def test_migracao_0019_vai_e_volta(tmp_path):
    url = f"sqlite:///{(tmp_path / 'm.sqlite').as_posix()}"
    migrar_para("head", url=url)
    desfazer_ate("0018", url=url)
    motor = criar_engine(url)
    assert "pdfs_originais" not in sa.inspect(motor).get_table_names()
    motor.dispose()
    migrar_para("head", url=url)
    motor = criar_engine(url)
    assert "pdfs_originais" in sa.inspect(motor).get_table_names()
    motor.dispose()


def test_relatorio_de_outro_id_nao_existe(banco):
    with banco.begin() as c:
        ana = _usuario(c, "ana")
        assert not _guardar(c, ana, uuid.uuid4())
