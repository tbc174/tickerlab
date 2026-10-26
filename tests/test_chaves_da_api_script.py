"""Script de administração das chaves da API (N7, PR 3, tarefa 3.1; plano D11).

Só quem está em `TICKERLAB_ADMINS` **e** é administrador no banco usa o script. A chave nova sai uma
vez no terminal (stdout), depois do commit, e em nenhum outro lugar: nem log, nem stderr, nem
auditoria (risco 3 do plano).
"""

import logging
import uuid
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa

from scripts import chaves_da_api as script
from src.banco import chaves_da_api as cb
from src.banco.modelo import auditoria, chaves_da_api, organizacoes
from src.banco.usuarios import entrar
from src.chaves_da_api import FORMATO, MotivoDaRecusa, gerar_chave, hash_da_chave

ADMIN = "admin-n7@exemplo.com"
HOJE = datetime.now(UTC).date()


@pytest.fixture
def admin(banco, monkeypatch):
    monkeypatch.setenv("TICKERLAB_ADMINS", ADMIN)
    with banco.begin() as conexao:
        usuario = entrar(
            conexao,
            "g-admin-script",
            ADMIN,
            emails_de_admin=(ADMIN,),
            email_confirmado=True,
        )[0]
    assert usuario.e_admin
    return usuario


def _rodar(capsys, *argumentos, admin=ADMIN):
    prefixo = ["--admin", admin] if admin else []
    codigo = script.main([*prefixo, *argumentos])
    saida = capsys.readouterr()
    return codigo, saida.out, saida.err


def _criar_organizacao(capsys, nome="Alfa Gestora"):
    codigo, saida, _ = _rodar(capsys, "criar-organizacao", "--nome", nome)
    assert codigo == 0
    return _id_na_saida(saida)


def _id_na_saida(saida):
    for palavra in saida.split():
        try:
            return uuid.UUID(palavra)
        except ValueError:
            continue
    raise AssertionError(f"nenhum id na saída: {saida!r}")


def _chave_na_saida(saida):
    achadas = [m.group(0) for m in FORMATO.finditer(saida)]
    assert len(achadas) == 1, "a chave nova sai exatamente uma vez"
    return achadas[0]


def _emitir(capsys, organizacao_id):
    codigo, saida, erro = _rodar(capsys, "emitir-chave", str(organizacao_id))
    assert codigo == 0, erro
    return _chave_na_saida(saida), saida, erro


def _segredo_da_chave(chave):
    """O segredo é tudo depois de `tld_<prefixo>_`; ele mesmo pode ter `_` (base64 para URL)."""
    return chave.split("_", 2)[2]


def test_segredo_da_chave_e_inteiro_mesmo_com_sublinhado_nele():
    for _ in range(500):
        prefixo, chave = gerar_chave()
        assert _segredo_da_chave(chave) == chave.removeprefix(f"tld_{prefixo}_")
        assert len(_segredo_da_chave(chave)) == 43


def _conferir(banco, chave):
    with banco.begin() as conexao:
        return cb.conferir_chave(conexao, chave)


def _auditoria_em_texto(banco):
    with banco.connect() as conexao:
        return repr(conexao.execute(sa.select(auditoria)).all())


def test_criar_organizacao_mostra_o_id_e_grava(banco, admin, capsys):
    organizacao_id = _criar_organizacao(capsys)
    with banco.connect() as conexao:
        organizacao = cb.buscar_organizacao(conexao, organizacao_id)
    assert organizacao is not None
    assert organizacao.nome == "Alfa Gestora"
    assert organizacao.plano_da_api == "piloto"


def test_chave_nova_sai_uma_vez_no_stdout_e_em_nenhum_outro_lugar(
    banco, admin, capsys, caplog
):
    caplog.set_level(logging.DEBUG)
    organizacao_id = _criar_organizacao(capsys)
    chave, _, erro = _emitir(capsys, organizacao_id)
    segredo = _segredo_da_chave(chave)
    assert len(segredo) == 43
    assert chave not in erro and segredo not in erro
    assert chave not in caplog.text and segredo not in caplog.text
    auditado = _auditoria_em_texto(banco)
    assert chave not in auditado and segredo not in auditado
    assert hash_da_chave(chave) not in auditado
    with banco.connect() as conexao:
        guardado = repr(conexao.execute(sa.select(chaves_da_api)).all())
    assert chave not in guardado and segredo not in guardado
    assert isinstance(_conferir(banco, chave), cb.ContextoDaChave)


def test_rotacionar_mostra_a_nova_e_a_antiga_ganha_prazo(banco, admin, capsys):
    organizacao_id = _criar_organizacao(capsys)
    antiga, _, _ = _emitir(capsys, organizacao_id)
    contexto = _conferir(banco, antiga)
    codigo, saida, _ = _rodar(
        capsys, "rotacionar-chave", str(organizacao_id), str(contexto.chave_id)
    )
    assert codigo == 0
    nova = _chave_na_saida(saida)
    assert nova != antiga
    assert isinstance(_conferir(banco, nova), cb.ContextoDaChave)
    with banco.connect() as conexao:
        expira_em = conexao.execute(
            sa.select(chaves_da_api.c.expira_em).where(
                chaves_da_api.c.id == contexto.chave_id
            )
        ).scalar_one()
    assert expira_em is not None


def test_revogar_recusa_a_chave_no_pedido_seguinte(banco, admin, capsys):
    organizacao_id = _criar_organizacao(capsys)
    chave, _, _ = _emitir(capsys, organizacao_id)
    chave_id = _conferir(banco, chave).chave_id
    codigo, _, _ = _rodar(capsys, "revogar-chave", str(organizacao_id), str(chave_id))
    assert codigo == 0
    assert _conferir(banco, chave) is MotivoDaRecusa.REVOGADA
    # de novo: nada muda, e o script avisa com erro
    codigo, _, erro = _rodar(
        capsys, "revogar-chave", str(organizacao_id), str(chave_id)
    )
    assert codigo == 1
    assert "nada mudou" in erro.lower()


def test_revogar_pelo_id_de_outra_organizacao_nao_muda_nada(banco, admin, capsys):
    alfa = _criar_organizacao(capsys)
    beta = _criar_organizacao(capsys, nome="Beta Crédito")
    chave, _, _ = _emitir(capsys, alfa)
    chave_id = _conferir(banco, chave).chave_id
    codigo, _, _ = _rodar(capsys, "revogar-chave", str(beta), str(chave_id))
    assert codigo == 1
    assert isinstance(_conferir(banco, chave), cb.ContextoDaChave)


def test_suspender_e_reativar_organizacao(banco, admin, capsys):
    organizacao_id = _criar_organizacao(capsys)
    chave, _, _ = _emitir(capsys, organizacao_id)
    codigo, _, _ = _rodar(
        capsys,
        "suspender-organizacao",
        str(organizacao_id),
        "--motivo",
        "pagamento",
    )
    assert codigo == 0
    assert _conferir(banco, chave) is MotivoDaRecusa.ORGANIZACAO_SUSPENSA
    # suspensa não ganha chave nova; o erro explica, sem traceback
    codigo, saida, erro = _rodar(capsys, "emitir-chave", str(organizacao_id))
    assert codigo == 1
    assert "suspensa" in erro
    assert not FORMATO.search(saida + erro)
    codigo, _, _ = _rodar(capsys, "reativar-organizacao", str(organizacao_id))
    assert codigo == 0
    assert isinstance(_conferir(banco, chave), cb.ContextoDaChave)


def test_motivo_fora_da_lista_e_recusado_pelo_argparse(banco, admin, capsys):
    organizacao_id = _criar_organizacao(capsys)
    with pytest.raises(SystemExit) as saida:
        _rodar(
            capsys,
            "suspender-organizacao",
            str(organizacao_id),
            "--motivo",
            "porque sim",
        )
    assert saida.value.code == 2


def test_conceder_suspender_e_reativar_direito(banco, admin, capsys):
    organizacao_id = _criar_organizacao(capsys)
    codigo, saida, _ = _rodar(
        capsys,
        "conceder-direito",
        str(organizacao_id),
        "--conjunto",
        "cvm-dfp-itr",
        "--finalidade",
        "credito",
        "--desde",
        HOJE.isoformat(),
    )
    assert codigo == 0
    direito_id = _id_na_saida(saida)

    def permite():
        with banco.connect() as conexao:
            return cb.contrato_permite(
                conexao,
                organizacao_id,
                conjunto="cvm-dfp-itr",
                finalidade="credito",
                dia=HOJE,
            )

    assert permite()
    argumentos = (str(organizacao_id), str(direito_id))
    assert _rodar(capsys, "suspender-direito", *argumentos)[0] == 0
    assert not permite()
    assert _rodar(capsys, "reativar-direito", *argumentos)[0] == 0
    assert permite()


def test_finalidade_treino_nunca_e_concedida(banco, admin, capsys):
    organizacao_id = _criar_organizacao(capsys)
    with pytest.raises(SystemExit):
        _rodar(
            capsys,
            "conceder-direito",
            str(organizacao_id),
            "--conjunto",
            "cvm-dfp-itr",
            "--finalidade",
            "treino",
            "--desde",
            HOJE.isoformat(),
        )


def test_ver_mostra_chaves_pelo_prefixo_direitos_e_consumo(banco, admin, capsys):
    organizacao_id = _criar_organizacao(capsys)
    chave, _, _ = _emitir(capsys, organizacao_id)
    _rodar(
        capsys,
        "conceder-direito",
        str(organizacao_id),
        "--conjunto",
        "cnpj",
        "--finalidade",
        "analise",
        "--desde",
        HOJE.isoformat(),
    )
    with banco.begin() as conexao:
        contexto = cb.conferir_chave(conexao, chave)
        cb.registrar_consumo(
            conexao, contexto, conjunto="cnpj", finalidade="analise", linhas=42
        )
        cb.registrar_consumo(
            conexao,
            contexto,
            conjunto="cnpj",
            finalidade="analise",
            linhas=0,
            negado=True,
        )
    codigo, saida, _ = _rodar(capsys, "ver", str(organizacao_id))
    assert codigo == 0
    assert contexto.prefixo in saida
    assert chave not in saida and hash_da_chave(chave) not in saida
    assert "cnpj" in saida and "analise" in saida
    assert "pedidos 1" in saida and "linhas 42" in saida and "negados 1" in saida


def test_ver_organizacao_inexistente_da_erro(banco, admin, capsys):
    codigo, _, erro = _rodar(capsys, "ver", str(uuid.uuid4()))
    assert codigo == 1
    assert "inexistente" in erro


@pytest.mark.parametrize("admins", ["", "outra-pessoa@exemplo.com"])
def test_recusa_quem_nao_esta_em_tickerlab_admins(
    banco, admin, capsys, monkeypatch, admins
):
    monkeypatch.setenv("TICKERLAB_ADMINS", admins)
    codigo, _, erro = _rodar(capsys, "criar-organizacao", "--nome", "Gama")
    assert codigo == 2
    assert "TICKERLAB_ADMINS" in erro
    with banco.connect() as conexao:
        assert (
            conexao.execute(
                sa.select(sa.func.count()).select_from(organizacoes)
            ).scalar_one()
            == 0
        )


def test_recusa_quem_esta_na_lista_mas_nao_e_admin_no_banco(
    banco, admin, capsys, monkeypatch
):
    monkeypatch.setenv("TICKERLAB_ADMINS", f"{ADMIN},nunca-entrou@exemplo.com")
    codigo, _, erro = _rodar(
        capsys, "criar-organizacao", "--nome", "Gama", admin="nunca-entrou@exemplo.com"
    )
    assert codigo == 2
    assert "administrador" in erro


def test_sem_admin_usa_o_unico_da_lista(banco, admin, capsys):
    codigo, saida, _ = _rodar(
        capsys, "criar-organizacao", "--nome", "Delta", admin=None
    )
    assert codigo == 0
    with banco.connect() as conexao:
        assert cb.buscar_organizacao(conexao, _id_na_saida(saida)) is not None


def test_sem_admin_e_lista_com_varios_pede_o_admin(banco, admin, capsys, monkeypatch):
    monkeypatch.setenv("TICKERLAB_ADMINS", f"{ADMIN},outro@exemplo.com")
    codigo, _, erro = _rodar(capsys, "criar-organizacao", "--nome", "Delta", admin=None)
    assert codigo == 2
    assert "--admin" in erro


def test_ver_mostra_o_estado_de_cada_chave(banco, admin, capsys):
    organizacao_id = _criar_organizacao(capsys)
    girada, _, _ = _emitir(capsys, organizacao_id)
    revogada, _, _ = _emitir(capsys, organizacao_id)
    for comando, chave in (("rotacionar-chave", girada), ("revogar-chave", revogada)):
        chave_id = _conferir(banco, chave).chave_id
        assert _rodar(capsys, comando, str(organizacao_id), str(chave_id))[0] == 0
    codigo, saida, _ = _rodar(capsys, "ver", str(organizacao_id))
    assert codigo == 0
    assert "de saída, vale até" in saida
    assert "revogada em" in saida
    assert "ativa" in saida  # a substituta da rotação
