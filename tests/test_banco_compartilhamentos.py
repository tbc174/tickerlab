"""Testes de src/banco/compartilhamentos.py: os links compartilhados de cada pessoa (onda 4)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

from src import compartilhamentos as comp
from src.banco import compartilhamentos as links
from src.banco import dados_do_usuario as repo
from src.banco import pdfs_originais as pdfs
from src.banco.modelo import compartilhamentos, metadata, pdfs_originais
from src.banco.usuarios import entrar, mudar_plano
from src.planos import LimiteDoPlanoError
from tests.test_compartilhamentos import _congelada

AGORA = datetime(2026, 10, 13, 23, 30, tzinfo=UTC)
PDF = b"%PDF-1.7 relatorio de exemplo"


@pytest.fixture
def conexao():
    motor = sa.create_engine("sqlite://", poolclass=sa.pool.StaticPool)
    sa.event.listen(motor, "connect", lambda c, _: c.execute("PRAGMA foreign_keys=ON"))
    metadata.create_all(motor)
    with motor.begin() as conexao:
        yield conexao


def _conta(conexao, sub, plano="gratuito"):
    usuario = entrar(conexao, sub, f"{sub}@exemplo.com", sub.title())[0]
    mudar_plano(conexao, usuario.id, plano)
    return usuario.id


@pytest.fixture
def ana(conexao):
    return _conta(conexao, "ana")


@pytest.fixture
def bia(conexao):
    return _conta(conexao, "bia")


def _pdf(conexao, usuario_id, tipo="ativo", titulo="PETR4"):
    rid = repo.registrar_relatorio(
        conexao, usuario_id, tipo, titulo=titulo, agora=AGORA
    )
    assert pdfs.guardar_pdf_original(
        conexao, usuario_id, rid, "pro", PDF, {"tipo": tipo}, agora=AGORA
    )
    return rid


def _ficha(conexao, usuario_id, plano="gratuito", dias=30, agora=AGORA):
    return links.criar_link_da_ficha(
        conexao, usuario_id, plano, _congelada(), dias, agora=agora
    )


# --- criar, listar e revogar (a conta) -----------------------------------------------------


def test_criar_link_da_ficha_guarda_so_o_hash(conexao, ana):
    codigo = _ficha(conexao, ana)
    assert comp.codigo_valido(codigo)
    (linha,) = conexao.execute(sa.select(compartilhamentos)).all()
    assert linha.codigo_hash == comp.hash_do_codigo(codigo)
    assert codigo not in repr(tuple(linha))
    assert linha.tipo == "ficha" and linha.relatorio_id is None
    assert linha.titulo == "Foi sorte? Cruzamento de médias em PETR4"


def test_listar_so_os_da_conta(conexao, ana, bia):
    _ficha(conexao, ana)
    _ficha(conexao, bia, dias=7)
    (da_ana,) = links.listar_links(conexao, ana, agora=AGORA)
    assert da_ana.tipo == "ficha"
    assert da_ana.expira_em == AGORA + timedelta(days=30)
    assert da_ana.situacao == "ativo" and da_ana.visitas == 0
    assert [l.expira_em for l in links.listar_links(conexao, bia, agora=AGORA)] == [
        AGORA + timedelta(days=7)
    ]


def test_lista_vem_do_mais_novo_e_diz_a_situacao(conexao, ana):
    _ficha(conexao, ana, dias=7, agora=AGORA - timedelta(days=10))
    _ficha(conexao, ana, agora=AGORA - timedelta(days=1))
    revogar = _ficha(conexao, ana)
    (ultimo, *_) = links.listar_links(conexao, ana, agora=AGORA)
    assert links.revogar_link(conexao, ana, ultimo.id, agora=AGORA)
    situacoes = [l.situacao for l in links.listar_links(conexao, ana, agora=AGORA)]
    assert situacoes == ["revogado", "ativo", "vencido"]
    assert links.abrir_link(conexao, revogar, agora=AGORA) is None


def test_revogar_link_de_outra_conta_nao_faz_nada(conexao, ana, bia):
    codigo = _ficha(conexao, ana)
    (link,) = links.listar_links(conexao, ana, agora=AGORA)
    assert not links.revogar_link(conexao, bia, link.id, agora=AGORA)
    assert links.listar_links(conexao, ana, agora=AGORA)[0].situacao == "ativo"
    assert links.abrir_link(conexao, codigo, agora=AGORA) is not None


def test_revogar_duas_vezes_guarda_a_primeira_data(conexao, ana):
    _ficha(conexao, ana)
    (link,) = links.listar_links(conexao, ana, agora=AGORA)
    assert links.revogar_link(conexao, ana, link.id, agora=AGORA)
    assert not links.revogar_link(
        conexao, ana, link.id, agora=AGORA + timedelta(hours=1)
    )
    assert links.listar_links(conexao, ana, agora=AGORA)[0].revogado_em == AGORA


def test_limite_de_links_ativos_por_plano(conexao, ana):
    for _ in range(3):
        _ficha(conexao, ana)
    with pytest.raises(LimiteDoPlanoError, match="3 links ativos"):
        _ficha(conexao, ana)
    (mais_novo, *_) = links.listar_links(conexao, ana, agora=AGORA)
    links.revogar_link(conexao, ana, mais_novo.id, agora=AGORA)
    _ficha(conexao, ana)  # o revogado não conta mais
    # 8 dias depois, um link de 7 dias venceu e deixa de contar
    _ficha(conexao, ana, plano="pro")  # o Pro tem mais espaço
    assert links.contar_ativos(conexao, ana, agora=AGORA) == 4


def test_vencido_nao_conta_no_limite(conexao, ana):
    for _ in range(3):
        _ficha(conexao, ana, dias=7)
    _ficha(conexao, ana, agora=AGORA + timedelta(days=8))


def test_ficha_invalida_nao_e_guardada(conexao, ana):
    estragada = {**_congelada(), "resultado": "ótimo"}
    with pytest.raises(ValueError):
        links.criar_link_da_ficha(conexao, ana, "pro", estragada, 30, agora=AGORA)
    with pytest.raises(ValueError):
        links.criar_link_da_ficha(conexao, ana, "pro", _congelada(), 31, agora=AGORA)
    assert conexao.execute(sa.select(compartilhamentos)).all() == []


def test_criar_link_do_pdf(conexao, ana):
    rid = _pdf(conexao, ana, titulo="Petrobras em 2026")
    codigo = links.criar_link_do_pdf(conexao, ana, "gratuito", rid, 90, agora=AGORA)
    (link,) = links.listar_links(conexao, ana, agora=AGORA)
    assert (link.tipo, link.titulo) == ("pdf", "Petrobras em 2026")
    assert links.pdf_do_link(conexao, codigo, agora=AGORA) == (
        "TickerLab-Petrobras-em-2026.pdf",
        PDF,
    )


def test_pdf_sem_titulo_usa_o_tipo(conexao, ana):
    rid = _pdf(conexao, ana, tipo="comparacao", titulo="")
    links.criar_link_do_pdf(conexao, ana, "pro", rid, 30, agora=AGORA)
    assert links.listar_links(conexao, ana, agora=AGORA)[0].titulo == (
        "Relatório em PDF (comparacao)"
    )


def test_pdf_de_outra_conta_nao_compartilha(conexao, ana, bia):
    rid = _pdf(conexao, ana)
    with pytest.raises(links.LinkInvalidoError):
        links.criar_link_do_pdf(conexao, bia, "pro", rid, 30, agora=AGORA)
    with pytest.raises(links.LinkInvalidoError):
        links.criar_link_do_pdf(conexao, ana, "pro", uuid.uuid4(), 30, agora=AGORA)
    assert conexao.execute(sa.select(compartilhamentos)).all() == []


def test_minha_carteira_nunca(conexao, ana):
    """O PDF dela nunca é guardado; mesmo que um apareça no banco, o link é recusado."""
    rid = repo.registrar_relatorio(conexao, ana, "minha_carteira", agora=AGORA)
    conexao.execute(
        sa.insert(pdfs_originais).values(
            relatorio_id=rid,
            usuario_id=ana,
            pdf=PDF,
            sha256=comp.hash_do_codigo("x"),
            tamanho=len(PDF),
            versoes={},
            gerado_em=AGORA,
        )
    )
    with pytest.raises(links.LinkInvalidoError):
        links.criar_link_do_pdf(conexao, ana, "pro", rid, 30, agora=AGORA)


# --- abrir pelo código (o lado público) ----------------------------------------------------


def test_abrir_a_ficha_devolve_a_ficha_congelada(conexao, ana):
    codigo = _ficha(conexao, ana)
    aberto = links.abrir_link(conexao, codigo, agora=AGORA)
    assert aberto is not None and aberto.tipo == "ficha"
    assert aberto.ficha == comp.ler_ficha_congelada(_congelada())
    assert aberto.pdf is None
    assert aberto.expira_em == AGORA + timedelta(days=30)


def test_abrir_conta_a_visita(conexao, ana):
    codigo = _ficha(conexao, ana)
    links.abrir_link(conexao, codigo, agora=AGORA)
    links.abrir_link(conexao, codigo, agora=AGORA + timedelta(hours=2))
    (link,) = links.listar_links(conexao, ana, agora=AGORA)
    assert link.visitas == 2
    assert link.ultima_visita_em == AGORA + timedelta(hours=2)


def test_abrir_vencido_revogado_ou_sem_pdf_da_none(conexao, ana):
    vencido = _ficha(conexao, ana, dias=7, agora=AGORA - timedelta(days=7))
    assert links.abrir_link(conexao, vencido, agora=AGORA) is None

    revogado = _ficha(conexao, ana)
    (mais_novo, *_) = links.listar_links(conexao, ana, agora=AGORA)
    links.revogar_link(conexao, ana, mais_novo.id, agora=AGORA)
    assert links.abrir_link(conexao, revogado, agora=AGORA) is None

    rid = _pdf(conexao, ana)
    sem_pdf = links.criar_link_do_pdf(conexao, ana, "pro", rid, 30, agora=AGORA)
    pdfs.apagar_pdf_original(conexao, ana, rid)
    assert links.abrir_link(conexao, sem_pdf, agora=AGORA) is None
    assert links.pdf_do_link(conexao, sem_pdf, agora=AGORA) is None

    assert links.abrir_link(conexao, comp.novo_codigo(), agora=AGORA) is None


def test_link_sai_quando_o_pdf_passa_de_um_ano(conexao, ana):
    rid = _pdf(conexao, ana)
    codigo = links.criar_link_do_pdf(conexao, ana, "pro", rid, 90, agora=AGORA)
    depois = AGORA + timedelta(days=pdfs.DIAS_GUARDADO + 1)
    assert links.pdf_do_link(conexao, codigo, agora=depois) is None


def test_abrir_pdf_confere_o_hash(conexao, ana):
    rid = _pdf(conexao, ana)
    codigo = links.criar_link_do_pdf(conexao, ana, "pro", rid, 30, agora=AGORA)
    aberto = links.abrir_link(conexao, codigo, agora=AGORA)
    assert aberto is not None and aberto.pdf is not None
    assert (aberto.pdf.tamanho, aberto.pdf.sha256) == (len(PDF), pdfs._hash(PDF))
    conexao.execute(
        sa.update(pdfs_originais)
        .where(pdfs_originais.c.relatorio_id == rid)
        .values(pdf=b"%PDF-1.7 trocado")
    )
    assert links.pdf_do_link(conexao, codigo, agora=AGORA) is None
    assert links.abrir_link(conexao, codigo, agora=AGORA) is None


def test_ficha_estragada_no_banco_nao_abre(conexao, ana):
    codigo = _ficha(conexao, ana)
    conexao.execute(sa.update(compartilhamentos).values(ficha={"versao": 99}))
    assert links.abrir_link(conexao, codigo, agora=AGORA) is None


class _ConexaoQueNaoPodeSerUsada:
    def execute(self, *_args, **_kwargs):
        raise AssertionError("o formato inválido não pode chegar ao banco")


@pytest.mark.parametrize("codigo", ["", "curto", "a" * 44, "x" * 42 + "/", None])
def test_formato_invalido_nem_consulta_o_banco(codigo):
    falsa = _ConexaoQueNaoPodeSerUsada()
    assert links.abrir_link(falsa, codigo, agora=AGORA) is None  # type: ignore[arg-type]
    assert links.pdf_do_link(falsa, codigo, agora=AGORA) is None  # type: ignore[arg-type]


# --- os dados da pessoa ---------------------------------------------------------------------


def test_exportar_sem_o_hash(conexao, ana, bia):
    _ficha(conexao, ana)
    _ficha(conexao, bia)
    (exportado,) = links.dados_para_exportar(conexao, ana, agora=AGORA)
    assert set(exportado) == {
        "tipo", "titulo", "criado_em", "expira_em", "revogado_em", "visitas",
        "ultima_visita_em", "situacao", "ficha",
    }  # fmt: skip
    assert exportado["situacao"] == "ativo"
    assert exportado["ficha"]["ticker"] == "PETR4.SA"
    assert "hash" not in repr(exportado)
