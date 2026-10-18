"""Testes do banco de dados do SaaS: migrações, esquema e usuários.

Rodam em SQLite por padrão. Para rodar no PostgreSQL de verdade (como o GitHub Actions faz), defina
TICKERLAB_TEST_DATABASE_URL com a URL de um banco de TESTE (as tabelas dele são apagadas).
"""

import os
import time
import traceback
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

from src.banco import usuarios as repo
from src.banco.conexao import (
    SEGUNDOS_PARA_CONECTAR,
    banco_esta_saudavel,
    criar_engine,
    migrar_para,
)
from src.banco.dados_do_usuario import apagar_simulacao, salvar_simulacao
from src.banco.modelo import (
    compartilhamentos,
    favoritos,
    pdfs_originais,
    preferencias,
    relatorios,
    simulacoes,
    teses,
    teses_estrategias,
    usuarios,
)
from src.banco.teses import escrever as escrever_tese
from src.banco.teses import listar as listar_teses
from src.configuracao import (
    VARIAVEL_DO_BANCO,
    normalizar_url_do_banco,
    url_do_banco,
    url_sem_senha,
)

URL_DE_TESTE = os.environ.get("TICKERLAB_TEST_DATABASE_URL")

# No CI estes testes usam um único banco PostgreSQL (e apagam as tabelas dele): com os testes em
# paralelo (pytest -n ... --dist loadgroup), o grupo os mantém todos no mesmo processo, um por vez.
pytestmark = pytest.mark.xdist_group("postgres")


@pytest.fixture
def motor(tmp_path):
    url = URL_DE_TESTE or f"sqlite:///{(tmp_path / 'saas.sqlite').as_posix()}"
    if URL_DE_TESTE:
        # banco de teste compartilhado: começa vazio a cada teste
        migrar_para("base", url)
    migrar_para("head", url)
    motor = criar_engine(url)
    yield motor
    motor.dispose()
    if URL_DE_TESTE:
        migrar_para("base", url)


# --- configuração -------------------------------------------------------------------------


def test_url_do_postgres_usa_o_driver_psycopg():
    assert (
        normalizar_url_do_banco("postgresql://u:s@h:5432/d")
        == "postgresql+psycopg://u:s@h:5432/d"
    )
    assert normalizar_url_do_banco("postgres://u@h/d").startswith(
        "postgresql+psycopg://"
    )
    assert normalizar_url_do_banco("sqlite:///x.db") == "sqlite:///x.db"


def test_postgres_tem_tempo_maximo_para_conectar_e_sqlite_nao_precisa(monkeypatch):
    # regressão do achado D-1 (Master v3): sem limite, um banco travado prendia cada página
    recebidos = {}

    def criar(url, **opcoes):
        recebidos[str(url).split(":")[0]] = opcoes.get("connect_args")
        return original(url, **opcoes)

    original = sa.create_engine
    monkeypatch.setattr("src.banco.conexao.sa.create_engine", criar)
    criar_engine("postgresql://u:s@127.0.0.1:1/x")
    criar_engine("sqlite://")
    assert recebidos["postgresql+psycopg"] == {
        "connect_timeout": SEGUNDOS_PARA_CONECTAR
    }
    assert recebidos["sqlite"] == {}


def test_banco_que_nao_responde_falha_em_segundos_em_vez_de_travar():
    motor = criar_engine("postgresql://ninguem:x@127.0.0.1:1/fora_do_ar")
    inicio = time.monotonic()
    with pytest.raises(sa.exc.OperationalError):
        motor.connect()
    assert time.monotonic() - inicio < SEGUNDOS_PARA_CONECTAR * 3
    assert not banco_esta_saudavel(motor)  # o /saude responde "fora" sem travar


def test_url_do_banco_vem_da_variavel_de_ambiente(monkeypatch):
    monkeypatch.setenv(VARIAVEL_DO_BANCO, "postgresql://u:s@h/d")
    assert url_do_banco() == "postgresql+psycopg://u:s@h/d"
    monkeypatch.delenv(VARIAVEL_DO_BANCO)
    assert url_do_banco().startswith("sqlite:///")


def test_senha_nunca_aparece_na_url_dos_logs():
    texto = url_sem_senha(
        "postgresql+psycopg://tickerlab:segredo123@servidor:5432/tickerlab"
    )
    assert "segredo123" not in texto and "***" in texto


# --- migrações e esquema ------------------------------------------------------------------


def test_migracao_cria_todas_as_tabelas(motor):
    tabelas = set(sa.inspect(motor).get_table_names())
    assert {
        "usuarios",
        "preferencias",
        "favoritos",
        "simulacoes",
        "alembic_version",
    } <= tabelas


def test_migracao_0027_cria_as_tentativas_ligadas_ao_usuario(motor):
    inspecao = sa.inspect(motor)
    colunas = {c["name"] for c in inspecao.get_columns("tentativas")}
    assert colunas == {"usuario_id", "ticker", "impressao", "criada_em"}
    chave = inspecao.get_pk_constraint("tentativas")["constrained_columns"]
    assert set(chave) == {"usuario_id", "ticker", "impressao"}
    (estrangeira,) = inspecao.get_foreign_keys("tentativas")
    assert estrangeira["referred_table"] == "usuarios"
    assert estrangeira["options"].get("ondelete") == "CASCADE"


def test_migracao_0031_cria_o_pulse_ligado_ao_usuario(motor):
    inspecao = sa.inspect(motor)
    colunas = {c["name"] for c in inspecao.get_columns("pulse")}
    assert colunas == {"usuario_id", "visto_em", "vereditos"}
    assert inspecao.get_pk_constraint("pulse")["constrained_columns"] == ["usuario_id"]
    (estrangeira,) = inspecao.get_foreign_keys("pulse")
    assert estrangeira["referred_table"] == "usuarios"
    assert estrangeira["options"].get("ondelete") == "CASCADE"


def test_migracao_0035_cria_a_origem_do_cadastro_ligada_ao_usuario(motor):
    inspecao = sa.inspect(motor)
    colunas = {c["name"] for c in inspecao.get_columns("origens_do_cadastro")}
    assert colunas == {
        "usuario_id",
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_content",
        "ref",
        "primeira_visita",
        "gravada_em",
    }
    chave = inspecao.get_pk_constraint("origens_do_cadastro")["constrained_columns"]
    assert chave == ["usuario_id"]
    (estrangeira,) = inspecao.get_foreign_keys("origens_do_cadastro")
    assert estrangeira["referred_table"] == "usuarios"
    assert estrangeira["options"].get("ondelete") == "CASCADE"


def test_migracao_0032_cria_o_diario_ligado_ao_usuario_e_as_simulacoes(motor):
    inspecao = sa.inspect(motor)
    colunas = {c["name"] for c in inspecao.get_columns("teses")}
    assert colunas == {"id", "usuario_id", "ticker", "texto", "criada_em"}
    (do_usuario,) = inspecao.get_foreign_keys("teses")
    assert do_usuario["referred_table"] == "usuarios"
    assert do_usuario["options"].get("ondelete") == "CASCADE"
    ligacoes = inspecao.get_foreign_keys("teses_estrategias")
    assert {e["referred_table"] for e in ligacoes} == {"teses", "simulacoes"}
    assert all(e["options"].get("ondelete") == "CASCADE" for e in ligacoes)
    chave = inspecao.get_pk_constraint("teses_estrategias")["constrained_columns"]
    assert set(chave) == {"tese_id", "simulacao_id"}


def test_banco_recusa_tese_vazia_ou_longa_demais(motor):
    """A trava do tamanho também vale no banco, não só no código."""
    with motor.begin() as conexao:
        usuario = repo.entrar(conexao, "sub-teses", "teses@exemplo.com", "Teses")[0]
    for texto in ("", "x" * 2001):
        with pytest.raises(sa.exc.IntegrityError), motor.begin() as conexao:
            conexao.execute(
                sa.insert(teses).values(
                    id=uuid.uuid4(),
                    usuario_id=usuario.id,
                    ticker="PETR4.SA",
                    texto=texto,
                )
            )


def test_diario_sai_com_a_conta_e_o_backtest_so_leva_a_ligacao(motor):
    """A cascata das duas tabelas do Diário no banco migrado (PostgreSQL no CI)."""
    with motor.begin() as conexao:
        ana = repo.entrar(conexao, "sub-ana-d", "ana-d@exemplo.com", "Ana")[0]
        bia = repo.entrar(conexao, "sub-bia-d", "bia-d@exemplo.com", "Bia")[0]
        backtest = salvar_simulacao(
            conexao, ana.id, "backtest", "Cruzamento", {"ticker": "PETR4.SA"}, {}
        )
        escrever_tese(conexao, ana.id, "PETR4", "Tese da Ana", [backtest.id])
        escrever_tese(conexao, bia.id, "PETR4", "Tese da Bia")
    with motor.begin() as conexao:
        apagar_simulacao(conexao, ana.id, backtest.id)
        assert conexao.execute(sa.select(teses_estrategias)).all() == []
        assert len(listar_teses(conexao, ana.id)) == 1
        repo.apagar_conta(conexao, ana.id)
        assert listar_teses(conexao, ana.id) == []
        assert [t.texto for t in listar_teses(conexao, bia.id)] == ["Tese da Bia"]


def test_migracao_0034_cria_os_links_ligados_ao_usuario_e_ao_pdf(motor):
    inspecao = sa.inspect(motor)
    colunas = {c["name"] for c in inspecao.get_columns("compartilhamentos")}
    assert colunas == {
        "id", "usuario_id", "codigo_hash", "tipo", "relatorio_id", "ficha", "titulo",
        "criado_em", "expira_em", "revogado_em", "visitas", "ultima_visita_em",
    }  # fmt: skip
    estrangeiras = inspecao.get_foreign_keys("compartilhamentos")
    assert {e["referred_table"] for e in estrangeiras} == {"usuarios", "pdfs_originais"}
    assert all(e["options"].get("ondelete") == "CASCADE" for e in estrangeiras)
    unicas = inspecao.get_unique_constraints("compartilhamentos")
    assert [u["column_names"] for u in unicas] == [["codigo_hash"]]


def _link(usuario_id, **mudar):
    agora = datetime(2026, 10, 13, tzinfo=UTC)
    return {
        "id": uuid.uuid4(),
        "usuario_id": usuario_id,
        "codigo_hash": uuid.uuid4().hex * 2,
        "tipo": "ficha",
        "relatorio_id": None,
        "ficha": {"versao": 1},
        "titulo": "Foi sorte? Teste",
        "criado_em": agora,
        "expira_em": agora + timedelta(days=30),
        **mudar,
    }


def _pdf_guardado(conexao, usuario_id):
    relatorio_id = uuid.uuid4()
    conexao.execute(
        sa.insert(relatorios).values(
            id=relatorio_id, usuario_id=usuario_id, tipo="ativo"
        )
    )
    conexao.execute(
        sa.insert(pdfs_originais).values(
            relatorio_id=relatorio_id,
            usuario_id=usuario_id,
            pdf=b"%PDF-1.4",
            sha256="0" * 64,
            tamanho=8,
            versoes={},
        )
    )
    return relatorio_id


def test_banco_recusa_link_incoerente(motor):
    """As travas do tipo, do prazo e do contador também valem no banco, não só no código."""
    with motor.begin() as conexao:
        usuario = repo.entrar(conexao, "sub-links", "links@exemplo.com", "Links")[0]
        relatorio_id = _pdf_guardado(conexao, usuario.id)
    agora = datetime(2026, 10, 13, tzinfo=UTC)
    incoerentes = [
        {"tipo": "carteira"},
        {"tipo": "ficha", "ficha": sa.null()},
        {"tipo": "ficha", "relatorio_id": relatorio_id},
        {"tipo": "pdf", "ficha": sa.null()},
        {"tipo": "pdf", "relatorio_id": relatorio_id},  # com a ficha também
        {"expira_em": agora},
        {"visitas": -1},
        {"titulo": ""},
    ]
    for mudar in incoerentes:
        with pytest.raises(sa.exc.IntegrityError), motor.begin() as conexao:
            conexao.execute(
                sa.insert(compartilhamentos).values(_link(usuario.id, **mudar))
            )
    with motor.begin() as conexao:
        conexao.execute(
            sa.insert(compartilhamentos).values(
                _link(
                    usuario.id, tipo="pdf", ficha=sa.null(), relatorio_id=relatorio_id
                )
            )
        )


def test_codigo_repetido_e_recusado_no_banco(motor):
    with motor.begin() as conexao:
        usuario = repo.entrar(conexao, "sub-rep", "rep@exemplo.com", "Rep")[0]
        conexao.execute(
            sa.insert(compartilhamentos).values(_link(usuario.id, codigo_hash="a" * 64))
        )
    with pytest.raises(sa.exc.IntegrityError), motor.begin() as conexao:
        conexao.execute(
            sa.insert(compartilhamentos).values(_link(usuario.id, codigo_hash="a" * 64))
        )


def test_links_saem_com_a_conta_e_com_o_pdf(motor):
    """A cascata no banco migrado (PostgreSQL no CI): sem a conta ou sem o PDF, o link some."""
    with motor.begin() as conexao:
        ana = repo.entrar(conexao, "sub-ana-l", "ana-l@exemplo.com", "Ana")[0]
        bia = repo.entrar(conexao, "sub-bia-l", "bia-l@exemplo.com", "Bia")[0]
        relatorio_id = _pdf_guardado(conexao, ana.id)
        conexao.execute(
            sa.insert(compartilhamentos).values(
                [
                    _link(
                        ana.id, tipo="pdf", ficha=sa.null(), relatorio_id=relatorio_id
                    ),
                    _link(ana.id),
                    _link(bia.id),
                ]
            )
        )
    with motor.begin() as conexao:
        conexao.execute(
            sa.delete(pdfs_originais).where(
                pdfs_originais.c.relatorio_id == relatorio_id
            )
        )
        donos = (
            conexao.execute(sa.select(compartilhamentos.c.usuario_id)).scalars().all()
        )
        assert sorted(map(str, donos)) == sorted([str(ana.id), str(bia.id)])
        repo.apagar_conta(conexao, ana.id)
        donos = (
            conexao.execute(sa.select(compartilhamentos.c.usuario_id)).scalars().all()
        )
        assert donos == [bia.id]


def test_migracao_pode_ser_desfeita_e_refeita(motor):
    url = motor.url.render_as_string(hide_password=False)
    migrar_para("base", url)
    assert "usuarios" not in sa.inspect(criar_engine(url)).get_table_names()
    migrar_para("head", url)
    assert "usuarios" in sa.inspect(criar_engine(url)).get_table_names()


def test_banco_responde_ao_teste_de_saude(motor):
    assert banco_esta_saudavel(motor)
    assert not banco_esta_saudavel(
        sa.create_engine("sqlite:////pasta/que/nao/existe/x.db")
    )


# --- usuários -----------------------------------------------------------------------------


def test_primeiro_login_cria_o_usuario_com_papel_e_plano_padrao(motor):
    with motor.begin() as conexao:
        usuario, novo = repo.entrar(
            conexao, "google-1", "Ana@Exemplo.com", "Ana", "http://f/1"
        )
    assert novo
    assert usuario.email == "ana@exemplo.com"  # e-mail sempre em minúsculas
    assert (usuario.papel, usuario.plano) == ("usuario", "gratuito")
    assert isinstance(usuario.id, uuid.UUID) and usuario.ultimo_acesso is not None


def test_segundo_login_atualiza_em_vez_de_duplicar(motor):
    with motor.begin() as conexao:
        primeiro, _ = repo.entrar(conexao, "google-1", "ana@exemplo.com", "Ana")
    with motor.begin() as conexao:
        segundo, novo = repo.entrar(
            conexao, "google-1", "ana@novo.com", "Ana Maria", "http://f/2"
        )
        assert repo.contar(conexao) == 1
    assert not novo and segundo.id == primeiro.id
    assert segundo.nome == "Ana Maria" and segundo.email == "ana@novo.com"
    assert segundo.foto_url == "http://f/2"


def test_email_de_administrador_vira_admin_no_cadastro_e_depois(motor):
    admins = ("chefe@exemplo.com",)
    with motor.begin() as conexao:
        chefe, _ = repo.entrar(
            conexao, "g-chefe", "Chefe@Exemplo.com", emails_de_admin=admins
        )
        comum, _ = repo.entrar(
            conexao, "g-comum", "comum@exemplo.com", emails_de_admin=admins
        )
    assert chefe.e_admin and not comum.e_admin
    with (
        motor.begin() as conexao
    ):  # quem já existia e entra na lista de admins vira admin
        promovido, _ = repo.entrar(
            conexao,
            "g-comum",
            "comum@exemplo.com",
            emails_de_admin=(*admins, "comum@exemplo.com"),
        )
    assert promovido.e_admin


def test_login_com_dados_invalidos_e_recusado(motor):
    with motor.begin() as conexao:
        with pytest.raises(ValueError, match="identificador"):
            repo.entrar(conexao, "", "ana@exemplo.com")
        with pytest.raises(ValueError, match="identificador"):
            repo.entrar(conexao, "x" * 65, "ana@exemplo.com")
        with pytest.raises(ValueError, match="e-mail"):
            repo.entrar(conexao, "g1", "sem-arroba")


def test_buscas_por_id_e_por_google_sub(motor):
    with motor.begin() as conexao:
        criado, _ = repo.entrar(conexao, "g1", "a@exemplo.com")
        assert repo.buscar_por_id(conexao, criado.id) == criado
        assert repo.buscar_por_google_sub(conexao, "g1") == criado
        assert repo.buscar_por_google_sub(conexao, "outro") is None
        assert repo.buscar_por_id(conexao, uuid.uuid4()) is None


def test_mudar_plano_e_papel_validam_os_valores(motor):
    with motor.begin() as conexao:
        usuario, _ = repo.entrar(conexao, "g1", "a@exemplo.com")
        repo.mudar_plano(conexao, usuario.id, "pro")
        repo.mudar_papel(conexao, usuario.id, "admin")
        atual = repo.buscar_por_id(conexao, usuario.id)
        assert (atual.plano, atual.papel) == ("pro", "admin")
        with pytest.raises(ValueError, match="Plano desconhecido"):
            repo.mudar_plano(conexao, usuario.id, "ouro")
        with pytest.raises(ValueError, match="Papel desconhecido"):
            repo.mudar_papel(conexao, usuario.id, "dono")
        with pytest.raises(LookupError):
            repo.mudar_plano(conexao, uuid.uuid4(), "pro")


def test_o_banco_recusa_plano_invalido_mesmo_sem_passar_pelo_codigo(motor):
    with motor.begin() as conexao:
        usuario, _ = repo.entrar(conexao, "g1", "a@exemplo.com")
    with pytest.raises(sa.exc.IntegrityError), motor.begin() as conexao:
        conexao.execute(
            sa.update(usuarios).where(usuarios.c.id == usuario.id).values(plano="vip")
        )


def test_google_sub_e_unico_no_banco(motor):
    with motor.begin() as conexao:
        repo.entrar(conexao, "g1", "a@exemplo.com")
    with pytest.raises(sa.exc.IntegrityError), motor.begin() as conexao:
        conexao.execute(
            sa.insert(usuarios).values(
                id=uuid.uuid4(), google_sub="g1", email="b@exemplo.com"
            )
        )


def test_apagar_a_conta_apaga_tudo_do_usuario_e_so_dele(motor):
    with motor.begin() as conexao:
        ana, _ = repo.entrar(conexao, "g-ana", "ana@exemplo.com")
        bia, _ = repo.entrar(conexao, "g-bia", "bia@exemplo.com")
        for dono in (ana, bia):
            conexao.execute(
                sa.insert(preferencias).values(
                    usuario_id=dono.id, dados={"periodo": "2y"}
                )
            )
            conexao.execute(
                sa.insert(favoritos).values(usuario_id=dono.id, ticker="PETR4.SA")
            )
            conexao.execute(
                sa.insert(simulacoes).values(
                    id=uuid.uuid4(),
                    usuario_id=dono.id,
                    tipo="backtest",
                    nome="teste",
                    parametros={"a": 1},
                    resultado={"b": 2},
                )
            )
    with motor.begin() as conexao:
        assert repo.apagar_conta(conexao, ana.id)
        assert not repo.apagar_conta(conexao, ana.id)  # já não existe
    with motor.connect() as conexao:
        for tabela in (preferencias, favoritos, simulacoes):
            donos = {linha.usuario_id for linha in conexao.execute(sa.select(tabela))}
            assert donos == {bia.id}, tabela.name


def test_json_guarda_e_devolve_estruturas(motor):
    parametros = {
        "estrategia": "Cruzamento de médias",
        "curta": 20,
        "usar_cdi": True,
        "lista": [1, 2.5],
    }
    with motor.begin() as conexao:
        usuario, _ = repo.entrar(conexao, "g1", "a@exemplo.com")
        conexao.execute(
            sa.insert(simulacoes).values(
                id=uuid.uuid4(),
                usuario_id=usuario.id,
                tipo="backtest",
                nome="n",
                parametros=parametros,
                resultado={"retorno": 0.12},
            )
        )
        linha = conexao.execute(sa.select(simulacoes)).one()
    assert linha.parametros == parametros and linha.resultado == {"retorno": 0.12}


def test_erros_do_banco_nao_citam_os_valores_da_consulta(motor):
    """Os valores (e-mails, nomes) não podem vazar para os logs pelas mensagens de erro."""
    segredo = "pessoa.secreta@exemplo.com"
    with pytest.raises(sa.exc.IntegrityError) as erro, motor.begin() as conexao:
        conexao.execute(
            sa.insert(usuarios).values(
                # papel fora da regra (o google_sub vazio deixou de ser erro na 0039)
                id=uuid.uuid4(),
                google_sub="g",
                email=segredo,
                papel="intruso",
            )
        )
    assert segredo not in str(erro.value)
    # nem no traceback completo (o erro original vem encadeado e iria junto para um log)
    assert segredo not in "".join(traceback.format_exception(erro.value))


def test_identificador_duplicado_nao_aparece_no_erro(motor):
    """No PostgreSQL, a violação de unicidade traz "Key (google_sub)=(...) already exists"."""
    segredo = "google-sub-secreto-123"
    with motor.begin() as conexao:
        repo.entrar(conexao, segredo, "a@exemplo.com")
    with pytest.raises(sa.exc.IntegrityError) as erro, motor.begin() as conexao:
        conexao.execute(
            sa.insert(usuarios).values(
                id=uuid.uuid4(),
                google_sub=segredo,
                email="b@exemplo.com",
                papel="usuario",
            )
        )
    assert segredo not in "".join(traceback.format_exception(erro.value))


def test_mensagem_sem_valores_usa_so_identificadores():
    from types import SimpleNamespace

    from src.banco.conexao import mensagem_sem_valores

    class UniqueViolation(Exception):
        sqlstate = "23505"
        diag = SimpleNamespace(
            table_name="usuarios",
            column_name=None,
            constraint_name="usuarios_email_key",
            message_detail="Key (email)=(x@y.com) already exists.",
        )

    texto = mensagem_sem_valores(
        UniqueViolation("Key (email)=(x@y.com) already exists.")
    )
    assert texto == (
        "UniqueViolation (código 23505); tabela usuarios; restrição usuarios_email_key"
    )
    assert mensagem_sem_valores(ValueError("não é do banco")) is None


def test_tentativas_no_banco_de_verdade_nao_repetem_e_somem_com_a_conta(motor):
    """No CI roda no PostgreSQL: confere o ON CONFLICT DO NOTHING e a cascata reais."""
    from src.banco import tentativas

    with motor.begin() as conexao:
        ana, _ = repo.entrar(conexao, "g-ana", "ana@exemplo.com")
        bia, _ = repo.entrar(conexao, "g-bia", "bia@exemplo.com")
        for marca in ("a" * 64, "a" * 64, "b" * 64):
            tentativas.registrar_tentativa(conexao, ana.id, "PETR4.SA", marca)
        tentativas.registrar_tentativa(conexao, bia.id, "PETR4.SA", "a" * 64)
    with motor.begin() as conexao:
        assert tentativas.contar_tentativas(conexao, ana.id, "PETR4.SA") == 2
        assert tentativas.contar_tentativas(conexao, bia.id, "PETR4.SA") == 1
        repo.apagar_conta(conexao, ana.id)
    with motor.connect() as conexao:
        assert tentativas.contar_por_ativo(conexao, ana.id) == {}
        assert tentativas.contar_por_ativo(conexao, bia.id) == {"PETR4.SA": 1}


def test_pulse_no_banco_de_verdade_nao_volta_o_relogio_e_some_com_a_conta(motor):
    """No CI roda no PostgreSQL: confere o ON CONFLICT DO UPDATE ... WHERE e a cascata reais."""
    from datetime import UTC, datetime, timedelta

    from src.banco import pulse

    agora = datetime(2026, 10, 13, 18, 0, tzinfo=UTC)
    with motor.begin() as conexao:
        ana, _ = repo.entrar(conexao, "g-ana", "ana@exemplo.com")
        bia, _ = repo.entrar(conexao, "g-bia", "bia@exemplo.com")
        pulse.marcar_visita(conexao, ana.id, agora, {"s1": "passou"})
        pulse.marcar_visita(
            conexao, ana.id, agora - timedelta(hours=1), {"s1": "não passou"}
        )
        pulse.marcar_visita(conexao, bia.id, agora + timedelta(days=1))
    with motor.begin() as conexao:
        assert pulse.ultima_visita(conexao, ana.id) == agora
        assert pulse.vereditos_vistos(conexao, ana.id) == {"s1": "passou"}
        repo.apagar_conta(conexao, ana.id)
    with motor.connect() as conexao:
        assert pulse.ultima_visita(conexao, ana.id) is None
        assert pulse.ultima_visita(conexao, bia.id) == agora + timedelta(days=1)
