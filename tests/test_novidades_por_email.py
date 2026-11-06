"""Novidades e ofertas por e-mail (migração 0037): opt-in, campanha, e-mail, envio sem duplicar,
saída sem login, as telas (1º acesso e Meus dados) e a LGPD (exportação e exclusão)."""

import json

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from scripts import enviar_novidades
from src import api, auditoria, conformidade, envio_newsletter
from src import envio_novidades as envio
from src.banco import novidades_por_email as repo
from src.banco import usuarios as contas
from src.banco.modelo import auditoria as tabela_da_auditoria
from src.conformidade import apagar_conta, exportar_meus_dados
from tests.ajudantes_da_conta import abrir_app, entrar_como, id_do_usuario, ir_para

VERSAO = envio.VERSAO_DO_CONSENTIMENTO
CHAVE = "re_teste"  # chave falsa: o Resend é simulado em todos os testes
ADMINS = ("ana@exemplo.com",)
CAMPANHA_OK = """# O TickerLab abriu as assinaturas

Agora dá para assinar o plano Plus.
Os primeiros 100 ganham um mês.

- Relatório completo de empresa
- Newsletter do Research

https://tickerlab.com.br/planos
"""


def _campanha(texto: str = CAMPANHA_OK, id_: str = "2026-11-lancamento"):
    return envio.ler_campanha(id_, texto)


# --- a campanha -----------------------------------------------------------------------------------
def test_campanha_le_assunto_paragrafos_itens_e_link():
    campanha = _campanha()
    assert campanha.id == "2026-11-lancamento"
    assert campanha.assunto == "O TickerLab abriu as assinaturas"
    assert campanha.blocos[0] == (
        "Agora dá para assinar o plano Plus.",
        "Os primeiros 100 ganham um mês.",
    )
    assert len(campanha.blocos) == 3


@pytest.mark.parametrize(
    "texto",
    [
        "",
        "Sem assunto\n\ntexto",
        "# \n\ntexto",
        "# Só o assunto",
    ],
)
def test_campanha_sem_assunto_ou_sem_corpo_e_recusada(texto):
    with pytest.raises(envio.CampanhaInvalidaError):
        _campanha(texto)


@pytest.mark.parametrize("id_", ["Lançamento", "com espaço", "", "a" * 81])
def test_id_da_campanha_fora_do_padrao_e_recusado(id_):
    with pytest.raises(envio.CampanhaInvalidaError):
        _campanha(id_=id_)


@pytest.mark.parametrize(
    "promessa",
    [
        "Rentabilidade GARANTIDA",
        "retorno garantido",
        "lucro certo",
        "investir sem risco",
    ],
)
def test_campanha_que_promete_rentabilidade_e_recusada(promessa):
    """O AGENTS.md: nunca prometer rentabilidade."""
    with pytest.raises(envio.CampanhaInvalidaError, match="promete"):
        _campanha(f"# Novidade\n\n{promessa} com o TickerLab.")


# --- o e-mail -------------------------------------------------------------------------------------
def test_email_tem_o_texto_o_aviso_e_o_link_para_sair():
    email = envio.montar_email(_campanha(), "https://x/novidades/sair?codigo=abc")
    assert email.assunto == "TickerLab · O TickerLab abriu as assinaturas"
    for corpo in (email.html, email.texto):
        assert "plano Plus" in corpo and "Relatório completo de empresa" in corpo
        assert "não é recomendação de investimento" in corpo
        assert "novidades/sair?codigo=abc" in corpo
    assert "<li>Newsletter do Research</li>" in email.html
    assert 'href="https://tickerlab.com.br/planos"' in email.html


def test_email_escapa_o_html():
    campanha = _campanha("# A <b>novidade</b>\n\n<script>x</script> & mais")
    email = envio.montar_email(campanha, "https://x/sair?codigo=a&b")
    assert "<script>" not in email.html and "&lt;script&gt;" in email.html
    assert "<b>novidade</b>" not in email.html
    assert 'href="https://x/sair?codigo=a&amp;b"' in email.html


def test_link_para_sair_usa_a_api(monkeypatch):
    monkeypatch.setenv(envio.VARIAVEL_DA_API, "https://api.exemplo.com/")
    assert (
        envio.link_para_sair("abc")
        == "https://api.exemplo.com/novidades/sair?codigo=abc"
    )


def test_remetente_proprio_das_novidades(monkeypatch):
    monkeypatch.delenv(envio.VARIAVEL_DO_REMETENTE, raising=False)
    assert envio.remetente() == envio.REMETENTE_PADRAO
    pedidos = []

    class _Resposta:
        ok, status_code = True, 200

        def json(self):
            return {"id": "msg"}

    def transporte(url, **kwargs):
        pedidos.append(kwargs)
        return _Resposta()

    email = envio.montar_email(_campanha(), "https://x")
    envio_newsletter.enviar_pelo_resend("ana@exemplo.com", email, "https://x", "k", CHAVE,
                                        transporte, remetente=envio.remetente())  # fmt: skip
    assert pedidos[0]["json"]["from"] == envio.REMETENTE_PADRAO
    assert pedidos[0]["json"]["headers"]["List-Unsubscribe"] == "<https://x>"


# --- inscrição ------------------------------------------------------------------------------------
def _usuario(conexao, sub):
    usuario, _ = contas.entrar(conexao, sub, f"{sub}@exemplo.com")
    return usuario.id


def test_inscrever_renovar_e_cancelar(banco):
    with banco.begin() as c:
        ana = _usuario(c, "ana")
        primeira = repo.inscrever(c, ana, VERSAO)
        segunda = repo.inscrever(c, ana, VERSAO)
        assert segunda.codigo_para_sair != primeira.codigo_para_sair
        assert not repo.sair_pelo_codigo(c, primeira.codigo_para_sair)
        assert repo.cancelar(c, ana) and repo.inscricao(c, ana) is None
        assert not repo.cancelar(c, ana)
        acoes = [l.acao for l in c.execute(sa.select(tabela_da_auditoria.c.acao)
                 .where(tabela_da_auditoria.c.alvo_id == ana)
                 .order_by(tabela_da_auditoria.c.criado_em))]  # fmt: skip
    assert acoes == [auditoria.ACAO_NOVIDADES_INSCRITA] * 2 + [
        auditoria.ACAO_NOVIDADES_CANCELADA
    ]


def test_so_quem_se_inscreveu_e_destinatario(banco):
    """O e-mail do cadastro não basta: sem o consentimento próprio, ninguém recebe."""
    with banco.begin() as c:
        ana = _usuario(c, "ana")
        _usuario(c, "bia")  # tem conta, não pediu
        repo.inscrever(c, ana, VERSAO)
        assert [d.email for d in repo.destinatarios(c)] == ["ana@exemplo.com"]


def test_isolamento_cada_um_so_mexe_na_propria_inscricao(banco):
    with banco.begin() as c:
        ana, bia = _usuario(c, "ana"), _usuario(c, "bia")
        repo.inscrever(c, ana, VERSAO)
        assert repo.inscricao(c, bia) is None
        assert not repo.cancelar(c, bia)
        assert repo.inscricao(c, ana) is not None


def test_inscricao_e_envios_na_exportacao_e_somem_com_a_conta(banco):
    with banco.begin() as c:
        ana = _usuario(c, "ana")
        repo.inscrever(c, ana, VERSAO)
        repo.registrar_envio(c, ana, "2026-11-lancamento", "enviado")
        exportados = exportar_meus_dados(c, ana)
        assert exportados["novidades_por_email"][0]["versao_do_consentimento"] == VERSAO
        assert "codigo_para_sair" not in exportados["novidades_por_email"][0]
        assert exportados["envios_de_novidades"][0]["campanha"] == "2026-11-lancamento"
        json.dumps(exportados)
        assert apagar_conta(c, ana)
        assert repo.inscricao(c, ana) is None
        assert repo.situacao_do_envio(c, ana, "2026-11-lancamento") is None


def test_migracao_0037_liga_as_tabelas_ao_usuario_em_cascata(banco):
    inspecao = sa.inspect(banco)
    for tabela in ("inscricoes_de_novidades", "envios_de_novidades"):
        (estrangeira,) = inspecao.get_foreign_keys(tabela)
        assert estrangeira["referred_table"] == "usuarios"
        assert estrangeira["options"].get("ondelete") == "CASCADE"


# --- o envio (script) -----------------------------------------------------------------------------
class _Resend:
    def __init__(self, falhar: bool = False):
        self.enviados: list[tuple[str, str, str]] = []
        self.falhar = falhar

    def __call__(self, para, email, link, idempotencia, chave, remetente=None):
        if self.falhar:
            raise envio_newsletter.EnvioFalhouError("o Resend recusou (HTTP 500)")
        self.enviados.append((para, idempotencia, remetente))
        return "msg"


def _processar(banco, sub, so_admins=ADMINS, resend=None):
    with banco.begin() as c:
        destinatario = next(d for d in repo.destinatarios(c) if d.email.startswith(sub))
        return enviar_novidades.processar(
            c, destinatario, _campanha(), CHAVE, so_admins, resend or _Resend()
        )


def test_previa_vai_so_para_admins_e_depois_todos_uma_vez(banco):
    with banco.begin() as c:
        ana, bia = _usuario(c, "ana"), _usuario(c, "bia")
        repo.inscrever(c, ana, VERSAO)
        repo.inscrever(c, bia, VERSAO)
    resend = _Resend()
    assert _processar(banco, "ana", resend=resend) == "enviado"
    assert _processar(banco, "bia", resend=resend) is None  # prévia: bia ainda não
    assert _processar(banco, "ana", so_admins=None, resend=resend) is None  # já recebeu
    assert _processar(banco, "bia", so_admins=None, resend=resend) == "enviado"
    assert [(p, i) for p, i, _ in resend.enviados] == [
        ("ana@exemplo.com", f"novidades-{ana}-2026-11-lancamento"),
        ("bia@exemplo.com", f"novidades-{bia}-2026-11-lancamento"),
    ]
    assert {r for _, _, r in resend.enviados} == {envio.remetente()}


def test_falha_e_tentada_de_novo(banco):
    with banco.begin() as c:
        repo.inscrever(c, _usuario(c, "ana"), VERSAO)
    assert _processar(banco, "ana", resend=_Resend(falhar=True)) == "falhou"
    assert _processar(banco, "ana") == "enviado"


def test_script_sem_chave_nao_envia(banco, monkeypatch, tmp_path):
    monkeypatch.delenv(envio_newsletter.VARIAVEL_DA_CHAVE, raising=False)
    arquivo = tmp_path / "2026-11-lancamento.md"
    arquivo.write_text(CAMPANHA_OK, encoding="utf-8")
    resend = _Resend()
    assert enviar_novidades.main([str(arquivo), "--todos"], enviar=resend) == 0
    assert resend.enviados == []


def test_script_recusa_campanha_com_promessa(banco, monkeypatch, tmp_path):
    monkeypatch.setenv(envio_newsletter.VARIAVEL_DA_CHAVE, CHAVE)
    arquivo = tmp_path / "promessa.md"
    arquivo.write_text("# Oferta\n\nLucro garantido!", encoding="utf-8")
    assert enviar_novidades.main([str(arquivo)]) == 1


def test_script_envia_a_previa_aos_admins(banco, monkeypatch, tmp_path):
    monkeypatch.setenv(envio_newsletter.VARIAVEL_DA_CHAVE, CHAVE)
    monkeypatch.setenv("TICKERLAB_ADMINS", "ana@exemplo.com")
    with banco.begin() as c:
        repo.inscrever(c, _usuario(c, "ana"), VERSAO)
        repo.inscrever(c, _usuario(c, "bia"), VERSAO)
    arquivo = tmp_path / "2026-11-lancamento.md"
    arquivo.write_text(CAMPANHA_OK, encoding="utf-8")
    resend = _Resend()
    assert enviar_novidades.main([str(arquivo)], enviar=resend) == 0
    assert [p for p, _, _ in resend.enviados] == ["ana@exemplo.com"]


# --- sair pelo link, sem login --------------------------------------------------------------------
def test_link_do_email_pede_confirmacao_e_o_post_tira_da_lista(banco):
    with banco.begin() as c:
        ana = _usuario(c, "ana")
        codigo = repo.inscrever(c, ana, VERSAO).codigo_para_sair
    cliente = TestClient(api.app)
    pagina = cliente.get(f"/novidades/sair?codigo={codigo}")
    assert pagina.status_code == 200 and 'method="post"' in pagina.text
    with banco.connect() as c:
        assert repo.inscricao(c, ana) is not None  # abrir o link não tira
    resposta = cliente.post(
        f"/api/novidades/sair?codigo={codigo}", data={"List-Unsubscribe": "One-Click"}
    )
    assert resposta.status_code == 200 and "não recebe mais" in resposta.text
    with banco.connect() as c:
        assert repo.inscricao(c, ana) is None
    assert "já foi usado" in cliente.post(f"/novidades/sair?codigo={codigo}").text


def test_codigo_na_pagina_e_escapado(banco):
    texto = TestClient(api.app).get('/novidades/sair?codigo="><script>').text
    assert "<script>" not in texto


# --- as telas -------------------------------------------------------------------------------------
def test_primeiro_acesso_tem_a_caixa_desmarcada_e_nao_inscreve_sem_marcar(
    banco, monkeypatch
):
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    app = abrir_app(aceitar_termos=False)
    caixa = app.checkbox(key="aceite_das_novidades")
    assert caixa.value is False
    app.checkbox(key="aceite_dos_termos").check().run()
    next(b for b in app.button if b.label == "Continuar").click().run()
    assert not app.exception
    with banco.connect() as c:
        assert repo.inscricao(c, id_do_usuario(banco, "ana")) is None


def test_primeiro_acesso_marcando_a_caixa_inscreve(banco, monkeypatch):
    entrar_como(monkeypatch, "bia", "bia@exemplo.com")
    app = abrir_app(aceitar_termos=False)
    app.checkbox(key="aceite_dos_termos").check()
    app.checkbox(key="aceite_das_novidades").check().run()
    next(b for b in app.button if b.label == "Continuar").click().run()
    assert not app.exception
    with banco.connect() as c:
        inscrita = repo.inscricao(c, id_do_usuario(banco, "bia"))
    assert inscrita is not None and inscrita.versao_do_consentimento == VERSAO


def test_meus_dados_inscreve_e_cancela(banco, monkeypatch):
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    app = abrir_app("meus_dados")
    ana = id_do_usuario(banco, "ana")
    assert app.button(key="novidades_inscrever").disabled  # sem o consentimento
    app.checkbox(key="novidades_consentimento").check().run()
    app.button(key="novidades_inscrever").click().run()
    assert not app.exception
    with banco.connect() as c:
        assert repo.inscricao(c, ana) is not None
    ir_para(app, "meus_dados")
    app.button(key="novidades_cancelar").click().run()
    with banco.connect() as c:
        assert repo.inscricao(c, ana) is None


# --- a política -----------------------------------------------------------------------------------
def test_politica_de_privacidade_cita_as_novidades_e_o_opt_in():
    texto = conformidade.carregar_texto("privacidade")
    assert "Novidades e ofertas" in texto and "**Só se você marcar**" in texto
    assert "não os usamos para publicidade de terceiros" in texto
    assert "não os usamos para publicidade." not in texto
