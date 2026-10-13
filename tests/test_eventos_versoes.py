"""Versões dos eventos (Radar, PR 3): a reapresentação de um documento não apaga a anterior, e
"como estava em D" tem resposta. Sem internet (amostra real da CVM em `tests/arquivos/cvm/`)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

from src import eventos as ev
from src.banco import eventos as repo
from src.banco.conexao import criar_engine, desfazer_ate, migrar_para
from src.banco.modelo import eventos, eventos_versoes
from tests.test_eventos import _zip

ANTES = datetime(2026, 10, 1, 7, tzinfo=UTC)
DEPOIS = ANTES + timedelta(days=5)


@pytest.fixture(scope="module")
def ipe():
    return ev.ler_ipe(_zip("ipe_cia_aberta_2026.csv", "ipe_amostra.csv"))


@pytest.fixture
def url(tmp_path):
    return f"sqlite:///{(tmp_path / 'v.sqlite').as_posix()}"


@pytest.fixture
def motor(url):
    migrar_para("head", url=url)
    motor = criar_engine(url)
    yield motor
    motor.dispose()


def _reapresentado(ipe):
    primeiro = ipe.head(1)
    return primeiro.assign(versao=primeiro["versao"] + 1, assunto="corrigido")


def test_reapresentacao_guarda_as_duas_versoes(motor, ipe):
    protocolo = ipe["protocolo"].iloc[0]
    with motor.begin() as c:
        repo.gravar_eventos(c, ipe, agora=ANTES)
        repo.gravar_eventos(c, ipe, agora=ANTES)  # repetir não cria versão
        repo.gravar_eventos(c, _reapresentado(ipe), agora=DEPOIS)
        versoes = repo.versoes_do_evento(c, "cvm_ipe", protocolo)
    assert [v.assunto == "corrigido" for v in versoes] == [False, True]
    assert versoes[0].substituido_em is not None
    assert versoes[1].substituido_em is None


def test_como_estava_antes_e_depois_da_reapresentacao(motor, ipe):
    protocolo = ipe["protocolo"].iloc[0]
    with motor.begin() as c:
        repo.gravar_eventos(c, ipe, agora=ANTES)
        repo.gravar_eventos(c, _reapresentado(ipe), agora=DEPOIS)

        def assunto_em(momento):
            linhas = repo.eventos_como_estavam_em(c, momento)
            return {l.protocolo: l.assunto for l in linhas}.get(protocolo)

        assert assunto_em(ANTES - timedelta(days=1)) is None  # ainda não conhecido
        assert assunto_em(ANTES + timedelta(days=1)) != "corrigido"
        assert assunto_em(DEPOIS + timedelta(days=1)) == "corrigido"
        # um evento por protocolo em cada momento, e o total bate com a tabela vigente
        agora = repo.eventos_como_estavam_em(c, DEPOIS + timedelta(days=1))
        assert len(agora) == len({l.protocolo for l in agora})
        assert len(agora) == c.execute(sa.text("select count(*) from eventos")).scalar()
        cnpj = ipe["cnpj"].iloc[0]
        assert {l.cnpj for l in repo.eventos_como_estavam_em(c, DEPOIS, cnpj)} == {cnpj}


def test_migracao_copia_os_eventos_que_ja_existiam_e_volta(url, ipe):
    migrar_para("0023", url=url)
    motor = criar_engine(url)
    try:
        with motor.begin() as c:
            # gravação de antes da PR 3: só a tabela vigente
            c.execute(
                sa.insert(eventos),
                [
                    {
                        "id": uuid.uuid4(), "fonte": "cvm_ipe", "protocolo": l.protocolo,
                        "versao": 1, "cnpj": l.cnpj, "empresa": "X", "categoria": "Fato",
                        "rotulo": "Fato relevante", "tema": "outros", "materialidade": 3,
                        "publicado_em": l.publicado_em, "link": "https://x",
                        "ingerido_em": ANTES,
                    }
                    for l in ipe.head(3).itertuples(index=False)
                ],
            )  # fmt: skip
        migrar_para("head", url=url)
        with motor.connect() as c:
            copiadas = c.execute(
                sa.select(sa.func.count()).select_from(eventos_versoes)
            )
            assert copiadas.scalar() == 3
            assert len(repo.eventos_como_estavam_em(c, DEPOIS)) == 3
            assert repo.eventos_como_estavam_em(c, ANTES - timedelta(seconds=1)) == []
        desfazer_ate("0023", url=url)
        with motor.connect() as c:
            assert "eventos_versoes" not in sa.inspect(c).get_table_names()
            assert (
                c.execute(sa.select(sa.func.count()).select_from(eventos)).scalar() == 3
            )
    finally:
        motor.dispose()
