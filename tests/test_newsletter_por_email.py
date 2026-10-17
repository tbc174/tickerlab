"""Newsletter por e-mail (Research, etapa 5c; decisão 0020): período, trava até o parecer,
o e-mail, o Resend (simulado), a inscrição, o envio sem duplicar, a saída sem login e a LGPD."""

import json
import subprocess
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
import requests
import sqlalchemy as sa
from fastapi.testclient import TestClient

from scripts import enviar_newsletter
from src import api, auditoria, carteira_research, research
from src import envio_newsletter as envio
from src.banco import dados_do_usuario as dados
from src.banco import newsletter_por_email as repo
from src.banco import usuarios as contas
from src.banco.modelo import auditoria as tabela_da_auditoria
from src.banco.usuarios import mudar_papel, mudar_plano
from src.conformidade import apagar_conta, exportar_meus_dados
from src.newsletter import Edicao, Item, Secao
from tests.ajudantes_da_conta import abrir_app, entrar_como, id_do_usuario

RAIZ = Path(__file__).parent.parent
SEGUNDA = datetime(2026, 10, 12, 8, 0, tzinfo=UTC)
TERCA = datetime(2026, 10, 13, 8, 0, tzinfo=UTC)
ADMINS = ("ana@exemplo.com",)
VERSAO = envio.VERSAO_DO_CONSENTIMENTO
CHAVE = "re_teste"  # chave falsa: o Resend é simulado em todos os testes


# --- quando e para quem --------------------------------------------------------------------------
def test_periodo_diario_e_semanal():
    assert envio.periodo_da_edicao("diaria", date(2026, 10, 13)) == "2026-10-13"
    assert envio.periodo_da_edicao("semanal", date(2026, 10, 12)) == "2026-W42"
    assert (
        envio.periodo_da_edicao("semanal", date(2026, 10, 13)) is None
    )  # só às segundas


def test_trava_so_admins_e_configuravel_e_comeca_ligada(monkeypatch):
    monkeypatch.delenv(envio.VARIAVEL_DA_TRAVA, raising=False)
    assert (
        envio.so_para_admins()
    )  # sem a variável, a trava fica ligada (seguro por padrão)
    assert envio.pode_receber(" Ana@Exemplo.com ", ADMINS)
    assert not envio.pode_receber("bia@exemplo.com", ADMINS)


def test_decisao_0020_emenda_1_libera_para_todos_com_a_variavel(monkeypatch):
    for desligada in ("0", "false", "NAO", " off "):
        monkeypatch.setenv(envio.VARIAVEL_DA_TRAVA, desligada)
        assert not envio.so_para_admins()
        assert envio.pode_receber("bia@exemplo.com", ADMINS)
    monkeypatch.setenv(envio.VARIAVEL_DA_TRAVA, "1")
    assert envio.so_para_admins()
    assert not envio.pode_receber("bia@exemplo.com", ADMINS)


def test_consentimento_diz_que_nao_ha_notas_e_tem_versao_nova():
    assert "sem notas" in envio.TEXTO_DO_CONSENTIMENTO
    assert envio.VERSAO_DO_CONSENTIMENTO == "2026-10-17"


def test_edicao_nao_usa_notas_nem_linguagem_de_recomendacao():
    """ADR 0089 (regras 5 e 9) e Emenda 1 da 0020: Newsletter sem notas barato/caro."""
    import re
    from pathlib import Path

    import src.newsletter as modulo_da_edicao

    fonte = Path(modulo_da_edicao.__file__).read_text(encoding="utf-8")
    assert not re.search(r"^\s*(from|import)\s+src\.notas", fonte, re.MULTILINE)
    email = envio.montar_email(_edicao(), "https://x/sair?codigo=abc")
    corpo = (email.html + email.texto).lower()
    for proibida in ("compre", "oportunidade", "recomendamos", "garantid"):
        assert proibida not in corpo


# --- o e-mail -------------------------------------------------------------------------------------
def _edicao() -> Edicao:
    item = Item(
        titulo="PETR4 · Fato relevante · 10/10/2026",
        texto="Aquisição <b>anunciada</b> & aprovada",
        link="https://www.rad.cvm.gov.br/x?a=1&b=2",
        sigla_da_fonte="CVM",
        razoes=(
            "A posição em PETR4 era 28,8% da sua carteira na fotografia de 10/10/2026.",
        ),
        trechos=("A Companhia aprovou a aquisição de 100% da Fábrica Modelo.",),
    )
    return Edicao(
        lista="Minha carteira",
        tickers=("PETR4.SA",),
        inicio=date(2026, 10, 5),
        fim=date(2026, 10, 12),
        gerada_em=SEGUNDA,
        secoes=(
            Secao("destaques", "Destaques", (item,), "Nada."),
            Secao(
                "alertas", "Sinais de alerta", (), "Nenhum sinal de alerta no período."
            ),
        ),
        fontes=(),
        parametros=(
            "Exposição: o peso de cada ativo na fotografia da carteira de 10/10/2026.",
        ),
    )


def test_email_tem_os_itens_os_limites_e_o_link_para_sair():
    email = envio.montar_email(
        _edicao(), "https://api.tickerlab.com.br/newsletter/sair?codigo=abc"
    )
    assert email.assunto == "TickerLab · Newsletter Minha carteira: 05/10 a 12/10"
    for corpo in (email.html, email.texto):
        assert "Fábrica Modelo" in corpo and "Nenhum sinal de alerta" in corpo
        assert "não é recomendação de investimento" in corpo
        assert "newsletter/sair?codigo=abc" in corpo


def test_email_abre_com_a_assinatura_da_marca_em_cores_legiveis_no_branco():
    from src import marca

    email = envio.montar_email(_edicao(), "https://x/sair?codigo=abc")
    assert email.html.index("Ticker") < email.html.index("Fábrica Modelo")
    assert f'color:{marca.AZUL}">Lab</span>' in email.html
    # as cores do tema escuro somem no fundo branco do e-mail
    assert marca.TEXTO_SUTIL not in email.html and marca.TEXTO_APAGADO not in email.html


def test_email_escapa_o_html_e_nao_leva_os_pesos_da_carteira():
    email = envio.montar_email(_edicao(), "https://x/sair?codigo=abc")
    assert "<b>anunciada</b>" not in email.html and "&lt;b&gt;anunciada" in email.html
    assert 'href="https://www.rad.cvm.gov.br/x?a=1&amp;b=2"' in email.html
    for corpo in (email.html, email.texto):
        assert (
            "28,8%" not in corpo and "fotografia" not in corpo
        )  # as razões ficam no app


class _Resposta:
    def __init__(self, status: int, corpo: dict | None = None):
        self.status_code, self.ok, self._corpo = status, status < 400, corpo or {}

    def json(self) -> dict:
        return self._corpo


def test_resend_recebe_a_chave_de_idempotencia_e_o_cancelamento_de_um_clique():
    pedidos = []

    def transporte(url, **kwargs):
        pedidos.append((url, kwargs))
        return _Resposta(200, {"id": "msg_1"})

    email = envio.montar_email(_edicao(), "https://x/sair?codigo=abc")
    assert envio.enviar_pelo_resend("ana@exemplo.com", email, "https://x/sair?codigo=abc",
                                    "newsletter-1-2026-W42", CHAVE, transporte) == "msg_1"  # fmt: skip
    url, kwargs = pedidos[0]
    assert url == envio.URL_DO_RESEND
    assert kwargs["headers"] == {
        "Authorization": f"Bearer {CHAVE}",
        "Idempotency-Key": "newsletter-1-2026-W42",
    }
    assert kwargs["json"]["to"] == ["ana@exemplo.com"]
    assert (
        kwargs["json"]["headers"]["List-Unsubscribe"] == "<https://x/sair?codigo=abc>"
    )
    assert (
        kwargs["json"]["headers"]["List-Unsubscribe-Post"]
        == "List-Unsubscribe=One-Click"
    )


@pytest.mark.parametrize(
    "transporte",
    [
        lambda url, **kwargs: _Resposta(422),
        lambda url, **kwargs: (_ for _ in ()).throw(requests.ConnectionError("x")),
    ],
)
def test_resend_falhando_vira_erro_sem_o_email(transporte):
    email = envio.montar_email(_edicao(), "https://x")
    with pytest.raises(envio.EnvioFalhouError) as erro:
        envio.enviar_pelo_resend(
            "ana@exemplo.com", email, "https://x", "k", CHAVE, transporte
        )
    assert "ana@" not in str(erro.value)


# --- inscrição --------------------------------------------------------------------------------
def _usuario(conexao, sub, plano="gratuito"):
    usuario, _ = contas.entrar(conexao, sub, f"{sub}@exemplo.com")
    mudar_plano(conexao, usuario.id, plano)
    return usuario.id


def test_inscrever_trocar_e_cancelar(banco):
    with banco.begin() as c:
        ana = _usuario(c, "ana")
        primeira = repo.inscrever(c, ana, "Demonstração", "diaria", VERSAO)
        segunda = repo.inscrever(c, ana, "Favoritos", "semanal", VERSAO)
        assert (segunda.lista, segunda.cadencia) == ("Favoritos", "semanal")
        assert (
            segunda.codigo_para_sair != primeira.codigo_para_sair
        )  # o link antigo não vale
        assert not repo.sair_pelo_codigo(c, primeira.codigo_para_sair)
        assert repo.cancelar(c, ana) and repo.inscricao(c, ana) is None
        assert not repo.cancelar(c, ana)
        with pytest.raises(repo.InscricaoInvalidaError):
            repo.inscrever(c, ana, "Demonstração", "mensal", VERSAO)
        acoes = [l.acao for l in c.execute(sa.select(tabela_da_auditoria.c.acao)
                 .where(tabela_da_auditoria.c.alvo_id == ana)
                 .order_by(tabela_da_auditoria.c.criado_em))]  # fmt: skip
    assert acoes == [auditoria.ACAO_NEWSLETTER_INSCRITA] * 2 + [
        auditoria.ACAO_NEWSLETTER_CANCELADA
    ]


def test_inscricao_e_envios_na_exportacao_e_somem_com_a_conta(banco):
    with banco.begin() as c:
        ana = _usuario(c, "ana")
        repo.inscrever(c, ana, "Demonstração", "diaria", VERSAO)
        repo.registrar_envio(c, ana, "2026-10-12", "enviado")
        exportados = exportar_meus_dados(c, ana)
        assert exportados["newsletter_por_email"][0]["lista"] == "Demonstração"
        assert "codigo_para_sair" not in exportados["newsletter_por_email"][0]
        assert exportados["envios_da_newsletter"][0]["situacao"] == "enviado"
        assert apagar_conta(c, ana)
        assert repo.inscricao(c, ana) is None
        assert repo.situacao_do_envio(c, ana, "2026-10-12") is None


# --- o envio (script do VPS) -------------------------------------------------------------------
class _Resend:
    """O Resend simulado: guarda o que mandaria, ou falha quando pedido."""

    def __init__(self, falhar: bool = False):
        self.enviados: list[tuple[str, str]] = []
        self.falhar = falhar

    def __call__(self, para, email, link, idempotencia, chave):
        if self.falhar:
            raise envio.EnvioFalhouError("o Resend recusou (HTTP 500)")
        self.enviados.append((para, idempotencia))
        return "msg"


def _destinatario(c, uid):
    return next(d for d in repo.destinatarios(c) if d.inscricao.usuario_id == uid)


def _processar(banco, uid, momento=SEGUNDA, chave=CHAVE, resend=None):
    with banco.begin() as c:
        return enviar_newsletter.processar(
            c, _destinatario(c, uid), momento, chave, ADMINS, resend or _Resend()
        )


def test_admin_recebe_uma_vez_por_periodo(banco):
    with banco.begin() as c:
        ana = _usuario(c, "ana")
        repo.inscrever(c, ana, "Demonstração", "diaria", VERSAO)
    resend = _Resend()
    assert _processar(banco, ana, resend=resend) == "enviado"
    assert (
        _processar(banco, ana, resend=resend) is None
    )  # o mesmo dia não manda de novo
    assert _processar(banco, ana, TERCA, resend=resend) == "enviado"
    assert resend.enviados == [
        ("ana@exemplo.com", f"newsletter-{ana}-2026-10-12"),
        ("ana@exemplo.com", f"newsletter-{ana}-2026-10-13"),
    ]


def test_quem_nao_e_admin_fica_retido_ate_o_parecer(banco):
    with banco.begin() as c:
        bia = _usuario(c, "bia")
        repo.inscrever(c, bia, "Demonstração", "diaria", VERSAO)
    resend = _Resend()
    assert _processar(banco, bia, resend=resend) == "retido"
    assert resend.enviados == []


def test_sem_a_chave_do_resend_monta_e_retem(banco):
    with banco.begin() as c:
        ana = _usuario(c, "ana")
        repo.inscrever(c, ana, "Demonstração", "diaria", VERSAO)
    assert _processar(banco, ana, chave=None) == "retido"
    with banco.connect() as c:
        assert repo.situacao_do_envio(c, ana, "2026-10-12") == "retido"


def test_falha_e_tentada_de_novo(banco):
    with banco.begin() as c:
        ana = _usuario(c, "ana")
        repo.inscrever(c, ana, "Demonstração", "diaria", VERSAO)
    assert _processar(banco, ana, resend=_Resend(falhar=True)) == "falhou"
    assert _processar(banco, ana) == "enviado"


def test_semanal_so_na_segunda_e_lista_apagada_fica_retida(banco):
    with banco.begin() as c:
        ana = _usuario(c, "ana")
        repo.inscrever(c, ana, "Lista que não existe", "semanal", VERSAO)
    assert _processar(banco, ana, TERCA) is None
    assert _processar(banco, ana) == "retido"


def test_lista_da_carteira_usa_a_fotografia(banco):
    foto = carteira_research.Fotografia(
        {"PETR4.SA": 0.3, "VALE3.SA": 0.1}, date(2026, 10, 10)
    )
    with banco.begin() as c:
        ana = _usuario(c, "ana", plano="pro")
        dados.salvar_carteira(c, ana, foto)
        assert enviar_newsletter.tickers_da_lista(c, ana, "pro", research.NOME_DA_CARTEIRA) == (
            ["PETR4.SA", "VALE3.SA"], foto,
        )  # fmt: skip
        # se o plano deixou de ser Pro, a carteira não é usada
        assert (
            enviar_newsletter.tickers_da_lista(
                c, ana, "plus", research.NOME_DA_CARTEIRA
            )
            is None
        )


def test_script_sem_chave_sai_sem_erro(banco, monkeypatch):
    monkeypatch.delenv(envio.VARIAVEL_DA_CHAVE, raising=False)
    monkeypatch.setenv("TICKERLAB_ADMINS", "ana@exemplo.com")
    with banco.begin() as c:
        repo.inscrever(c, _usuario(c, "ana"), "Demonstração", "diaria", VERSAO)
    assert enviar_newsletter.main([]) == 0


# --- sair pelo link, sem login --------------------------------------------------------------------
def test_link_do_email_pede_confirmacao_e_o_post_descadastra(banco):
    with banco.begin() as c:
        ana = _usuario(c, "ana")
        codigo = repo.inscrever(
            c, ana, "Demonstração", "diaria", VERSAO
        ).codigo_para_sair
    cliente = TestClient(api.app)
    pagina = cliente.get(f"/newsletter/sair?codigo={codigo}")
    assert pagina.status_code == 200 and 'method="post"' in pagina.text
    with banco.connect() as c:
        assert repo.inscricao(c, ana) is not None  # abrir o link não descadastra
    resposta = cliente.post(
        f"/api/newsletter/sair?codigo={codigo}", data={"List-Unsubscribe": "One-Click"}
    )
    assert resposta.status_code == 200 and "não recebe mais" in resposta.text
    with banco.connect() as c:
        assert repo.inscricao(c, ana) is None
    assert "já foi usado" in cliente.post(f"/newsletter/sair?codigo={codigo}").text


def test_codigo_na_pagina_e_escapado(banco):
    texto = TestClient(api.app).get('/newsletter/sair?codigo="><script>').text
    assert "<script>" not in texto


# --- a tela ---------------------------------------------------------------------------------------
def test_admin_se_inscreve_pela_newsletter(banco, monkeypatch):
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    abrir_app()
    ana = id_do_usuario(banco, "ana")
    with banco.begin() as c:
        mudar_papel(c, ana, "admin")
    app = abrir_app("newsletter")
    assert app.button(key="newsletter_email_inscrever").disabled  # sem o consentimento
    app.selectbox(key="newsletter_email_cadencia").set_value("semanal")
    app.checkbox(key="newsletter_email_consentimento").check().run()
    app.button(key="newsletter_email_inscrever").click().run()
    assert not app.exception
    with banco.connect() as c:
        inscrita = repo.inscricao(c, ana)
    assert (inscrita.lista, inscrita.cadencia) == ("Demonstração", "semanal")
    app.button(key="newsletter_email_cancelar").click().run()
    with banco.connect() as c:
        assert repo.inscricao(c, ana) is None


def test_quem_nao_e_admin_nao_ve_a_inscricao(banco, monkeypatch):
    entrar_como(monkeypatch, "bia", "bia@exemplo.com")
    app = abrir_app("newsletter")
    assert not app.exception
    assert not any(b.key == "newsletter_email_inscrever" for b in app.button)


def test_json_da_exportacao_continua_serializavel(banco):
    with banco.begin() as c:
        ana = _usuario(c, "ana")
        repo.inscrever(c, ana, "Demonstração", "diaria", VERSAO)
        json.dumps(exportar_meus_dados(c, ana))


def test_a_api_continua_leve():
    """A rota de saída não pode puxar a Newsletter inteira: o contêiner da API tem 256 MB."""
    codigo = "import sys, src.api; print('pandas' in sys.modules)"
    saida = subprocess.run(
        [sys.executable, "-c", codigo],
        capture_output=True,
        text=True,
        check=True,
        cwd=RAIZ,
    )
    assert saida.stdout.strip() == "False"
