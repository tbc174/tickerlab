"""As perguntas ao chat no banco (linha 903): cota por conta, gasto do mês, isolamento e LGPD.

Riscos que estes testes pegam: (1) a cota de uma conta contar as perguntas de outra; (2) o dia e o mês
virarem no horário de UTC e não no de Brasília; (3) a pergunta em curso não entrar no gasto do mês (duas ao
mesmo tempo passariam do teto); (4) a exportação da LGPD levar outra conta, o texto ou o id da
organização; (5) apagar a conta levar o gasto junto; (6) a organização suspensa ou a chave revogada ou
vencida ainda servirem de contexto para o chat.
"""

import os
import threading
import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

from src.banco import chaves_da_api as cb
from src.banco import membros_da_organizacao as mb
from src.banco import perguntas_do_chat as pc
from src.banco.conexao import criar_engine
from src.banco.modelo import perguntas_do_chat
from src.banco.usuarios import entrar
from src.conformidade import apagar_conta, exportar_meus_dados

# 13/11/2026 às 02h UTC ainda é 12/11 (23h) em Brasília
VIRADA_DO_DIA = datetime(2026, 11, 13, 2, tzinfo=UTC)
# 01/12/2026 às 02h UTC ainda é novembro em Brasília
VIRADA_DO_MES = datetime(2026, 12, 1, 2, tzinfo=UTC)
AGORA = datetime(2026, 11, 13, 15, tzinfo=UTC)
MODELO = "claude-opus-5-5"
RESERVA = 600_000


def _conta(banco, nome: str):
    with banco.begin() as conexao:
        return entrar(conexao, f"g-{nome}", f"{nome}@exemplo.com")[0]


def _organizacao(banco, nome: str = "Casa Exemplo"):
    admin = _conta(banco, f"admin-{uuid.uuid4().hex[:6]}")
    with banco.begin() as conexao:
        org = cb.criar_organizacao(conexao, nome=nome, ator_id=admin.id, agora=AGORA)
    return org, admin


def _perguntar(banco, conta_id, org_id, quando: datetime, *, custo: int | None = None):
    with banco.begin() as conexao:
        pergunta = pc.reservar(
            conexao,
            usuario_id=conta_id,
            organizacao_id=org_id,
            modelo=MODELO,
            agora=quando,
        )
        if custo is not None:
            pc.concluir(
                conexao,
                pergunta,
                estado="respondida",
                uso=pc.UsoDaPergunta(custo_em_microdolares=custo, tokens_de_entrada=10),
                latencia_ms=1200,
            )
    return pergunta


def _desde(banco, conta_id, desde):
    with banco.connect() as conexao:
        return pc.perguntas_desde(conexao, conta_id, desde)


def _gasto(banco, agora=AGORA):
    with banco.connect() as conexao:
        return pc.gasto_do_mes(conexao, agora, reserva_em_microdolares=RESERVA)


# ---------------------------------------------------------------- dia e mês de Brasília


def test_inicio_do_dia_e_do_mes_sao_os_de_brasilia():
    assert pc.inicio_do_dia(VIRADA_DO_DIA) == datetime(2026, 11, 12, 3, tzinfo=UTC)
    assert pc.inicio_do_mes(VIRADA_DO_MES) == datetime(2026, 11, 1, 3, tzinfo=UTC)


def test_hora_sem_fuso_e_recusada(banco):
    ana = _conta(banco, "ana")
    org, _ = _organizacao(banco)
    with pytest.raises(ValueError), banco.begin() as conexao:
        pc.reservar(
            conexao,
            usuario_id=ana.id,
            organizacao_id=org.id,
            modelo=MODELO,
            agora=datetime(2026, 11, 13, 12),  # noqa: DTZ001 - a falta do fuso é o que se testa
        )


def test_cota_do_dia_conta_pelo_dia_de_brasilia(banco):
    ana = _conta(banco, "ana")
    org, _ = _organizacao(banco)
    _perguntar(banco, ana.id, org.id, VIRADA_DO_DIA)  # 12/11 em Brasília
    _perguntar(banco, ana.id, org.id, VIRADA_DO_DIA + timedelta(hours=2))  # 13/11
    assert _desde(banco, ana.id, pc.inicio_do_dia(AGORA)) == 1
    assert _desde(banco, ana.id, pc.inicio_do_dia(VIRADA_DO_DIA)) == 2


def test_pergunta_de_30_11_a_noite_conta_em_novembro(banco):
    ana = _conta(banco, "ana")
    org, _ = _organizacao(banco)
    _perguntar(banco, ana.id, org.id, VIRADA_DO_MES, custo=1_000)
    assert _desde(banco, ana.id, pc.inicio_do_mes(VIRADA_DO_MES)) == 1
    assert _gasto(banco, VIRADA_DO_MES) == 1_000
    dezembro = datetime(2026, 12, 1, 12, tzinfo=UTC)
    assert _desde(banco, ana.id, pc.inicio_do_mes(dezembro)) == 0
    assert _gasto(banco, dezembro) == 0


# ---------------------------------------------------------------- isolamento e gasto


def test_cota_de_uma_conta_nao_conta_a_da_outra(banco):
    ana, bia = _conta(banco, "ana"), _conta(banco, "bia")
    org, _ = _organizacao(banco)
    for _ in range(3):
        _perguntar(banco, ana.id, org.id, AGORA)
    _perguntar(banco, bia.id, org.id, AGORA)
    inicio = pc.inicio_do_mes(AGORA)
    assert _desde(banco, ana.id, inicio) == 3
    assert _desde(banco, bia.id, inicio) == 1


def test_gasto_do_mes_soma_todas_as_contas_e_a_reserva_das_em_curso(banco):
    ana, bia = _conta(banco, "ana"), _conta(banco, "bia")
    org, _ = _organizacao(banco)
    outra, _ = _organizacao(banco, "Outra Casa")
    _perguntar(banco, ana.id, org.id, AGORA, custo=150_000)
    _perguntar(banco, bia.id, outra.id, AGORA, custo=50_000)
    _perguntar(banco, bia.id, outra.id, AGORA)  # em curso: conta a reserva inteira
    _perguntar(banco, ana.id, org.id, AGORA - timedelta(days=31), custo=9_999_999)
    assert _gasto(banco) == 150_000 + 50_000 + RESERVA


def test_concluir_em_curso_e_recusado(banco):
    ana = _conta(banco, "ana")
    org, _ = _organizacao(banco)
    pergunta = _perguntar(banco, ana.id, org.id, AGORA)
    with pytest.raises(ValueError), banco.begin() as conexao:
        pc.concluir(
            conexao, pergunta, estado=pc.EM_CURSO, uso=pc.UsoDaPergunta(), latencia_ms=1
        )


def _estados(banco) -> dict:
    with banco.connect() as conexao:
        linhas = conexao.execute(
            sa.select(
                perguntas_do_chat.c.id,
                perguntas_do_chat.c.estado,
                perguntas_do_chat.c.custo_em_microdolares,
            )
        )
        return {l.id: (l.estado, l.custo_em_microdolares) for l in linhas}


def test_em_curso_ha_muito_tempo_fecha_como_erro_pela_reserva(banco):
    """O processo morreu no meio (deploy): a linha não pode ficar em curso para sempre."""
    ana = _conta(banco, "ana")
    org, _ = _organizacao(banco)
    limite = timedelta(minutes=pc.MINUTOS_PARA_ABANDONAR)
    velha = _perguntar(banco, ana.id, org.id, AGORA - limite - timedelta(seconds=1))
    recente = _perguntar(banco, ana.id, org.id, AGORA - limite + timedelta(seconds=1))
    pronta = _perguntar(banco, ana.id, org.id, AGORA - 2 * limite, custo=7)
    with banco.begin() as conexao:
        fechadas = pc.fechar_abandonadas(
            conexao, AGORA, reserva_em_microdolares=RESERVA
        )
    assert fechadas == 1
    estados = _estados(banco)
    assert estados[velha] == (pc.ERRO, RESERVA)
    assert estados[recente] == (pc.EM_CURSO, 0)
    assert estados[pronta] == ("respondida", 7)
    # o gasto do mês não muda: a abandonada já contava pela reserva
    assert _gasto(banco) == 2 * RESERVA + 7


def test_no_sqlite_a_trava_das_reservas_nao_faz_nada(banco):
    with banco.begin() as conexao:
        pc.travar_reservas(conexao)
        assert pc.perguntas_desde(conexao, uuid.uuid4(), AGORA) == 0


URL_DO_POSTGRES = os.environ.get("TICKERLAB_TEST_DATABASE_URL")


@pytest.mark.xdist_group("postgres")
@pytest.mark.skipif(
    not URL_DO_POSTGRES,
    reason="a trava é do PostgreSQL (defina TICKERLAB_TEST_DATABASE_URL)",
)
def test_reserva_espera_quem_segura_a_trava():
    """Dois pedidos ao mesmo tempo: o segundo só conta as perguntas depois que o primeiro gravou."""
    assert URL_DO_POSTGRES
    motor = criar_engine(URL_DO_POSTGRES)
    alta, baixa = divmod(pc.CHAVE_DA_TRAVA_DAS_RESERVAS, 2**32)
    esperando = sa.text(
        "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND NOT granted"
        " AND classid = :alta AND objid = :baixa"
    )
    pegou = threading.Event()

    def reservar() -> None:
        with motor.begin() as conexao:
            pc.travar_reservas(conexao)
            pegou.set()

    try:
        with motor.begin() as primeiro:
            pc.travar_reservas(primeiro)
            linha = threading.Thread(target=reservar)
            linha.start()
            prazo = time.monotonic() + 30
            with motor.connect() as olhar:
                while not olhar.execute(
                    esperando, {"alta": alta, "baixa": baixa}
                ).scalar():
                    assert time.monotonic() < prazo, (
                        "a segunda reserva não esperou a trava"
                    )
                    time.sleep(0.05)
            assert not pegou.is_set()
        # o fim da transação solta a trava
        assert pegou.wait(30)
        linha.join()
    finally:
        motor.dispose()


# ---------------------------------------------------------------- LGPD


def test_exportacao_traz_so_as_perguntas_da_conta_sem_texto_nem_organizacao(banco):
    ana, bia = _conta(banco, "ana"), _conta(banco, "bia")
    org, _ = _organizacao(banco)
    _perguntar(banco, ana.id, org.id, AGORA, custo=1_234)
    _perguntar(banco, bia.id, org.id, AGORA, custo=9)
    with banco.connect() as conexao:
        exportado = exportar_meus_dados(conexao, ana.id)["perguntas_ao_chat"]
    assert exportado == [
        {
            "feita_em": AGORA.isoformat(),
            "modelo": MODELO,
            "estado": "respondida",
            "tokens_de_entrada": 10,
            "tokens_de_saida": 0,
            "tokens_lidos_do_cache": 0,
            "tokens_gravados_no_cache": 0,
            "custo_em_microdolares": 1_234,
            "latencia_ms": 1200,
            "chamadas_de_ferramenta": 0,
        }
    ]


def test_apagar_a_conta_solta_o_id_e_o_gasto_do_mes_continua(banco):
    ana = _conta(banco, "ana")
    org, _ = _organizacao(banco)
    _perguntar(banco, ana.id, org.id, AGORA, custo=70_000)
    with banco.begin() as conexao:
        assert apagar_conta(conexao, ana.id)
    with banco.connect() as conexao:
        (linha,) = conexao.execute(sa.select(perguntas_do_chat)).all()
    assert linha.usuario_id is None
    assert _gasto(banco) == 70_000


# ---------------------------------------------------------------- organização e chave do chat


def test_organizacao_da_conta(banco):
    ana, bia = _conta(banco, "ana"), _conta(banco, "bia")
    org, admin = _organizacao(banco)
    with banco.begin() as conexao:
        mb.vincular_membro(
            conexao, organizacao_id=org.id, usuario_id=ana.id, ator_id=admin.id
        )
    with banco.connect() as conexao:
        assert mb.organizacao_da_conta(conexao, ana.id) == org.id
        assert mb.organizacao_da_conta(conexao, bia.id) is None


def _contexto(banco, org_id, agora=AGORA):
    with banco.connect() as conexao:
        return cb.contexto_da_organizacao(conexao, org_id, agora=agora)


def _emitir(banco, org, admin, quando=AGORA):
    with banco.begin() as conexao:
        return cb.emitir_chave(
            conexao, organizacao_id=org.id, ator_id=admin.id, agora=quando
        )


def test_contexto_e_o_da_chave_mais_nova_e_nunca_leva_o_segredo(banco):
    org, admin = _organizacao(banco)
    assert _contexto(banco, org.id) is None
    _emitir(banco, org, admin, AGORA - timedelta(days=2))
    nova = _emitir(banco, org, admin, AGORA - timedelta(days=1))
    contexto = _contexto(banco, org.id)
    assert contexto is not None
    assert (contexto.chave_id, contexto.prefixo) == (nova.chave_id, nova.prefixo)
    assert contexto.organizacao_id == org.id
    assert nova.valor not in repr(contexto)


def test_chave_revogada_nao_serve_de_contexto(banco):
    org, admin = _organizacao(banco)
    chave = _emitir(banco, org, admin)
    with banco.begin() as conexao:
        cb.revogar_chave(
            conexao, organizacao_id=org.id, chave_id=chave.chave_id, ator_id=admin.id
        )
    assert _contexto(banco, org.id) is None


def test_chave_rotacionada_vale_ate_vencer(banco):
    org, admin = _organizacao(banco)
    antiga = _emitir(banco, org, admin, AGORA - timedelta(days=1))
    with banco.begin() as conexao:
        nova = cb.rotacionar_chave(
            conexao,
            organizacao_id=org.id,
            chave_id=antiga.chave_id,
            ator_id=admin.id,
            agora=AGORA,
        )
        cb.revogar_chave(
            conexao, organizacao_id=org.id, chave_id=nova.chave_id, ator_id=admin.id
        )
    contexto = _contexto(banco, org.id)
    assert contexto is not None and contexto.chave_id == antiga.chave_id
    depois = AGORA + cb.PRAZO_DA_ROTACAO + timedelta(minutes=1)
    assert _contexto(banco, org.id, depois) is None


def test_organizacao_suspensa_nao_serve_de_contexto(banco):
    org, admin = _organizacao(banco)
    _emitir(banco, org, admin)
    with banco.begin() as conexao:
        cb.suspender_organizacao(
            conexao, organizacao_id=org.id, motivo="contrato", ator_id=admin.id
        )
    assert _contexto(banco, org.id) is None
