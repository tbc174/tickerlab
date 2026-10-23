"""LGPD: aceite dos termos, exportação dos meus dados e exclusão da conta."""

import json
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
import stripe

from src import auditoria, conformidade
from src.banco import compartilhamentos as links
from src.banco import dados_do_usuario as repo
from src.banco import origens, pulse, sessoes, tentativas
from src.banco import teses as diario
from src.banco.modelo import assinaturas, identidades, metadata, sessoes_de_login
from src.banco.usuarios import buscar_por_id, entrar
from src.cobranca import Assinatura, encerrar_cobranca
from src.origem import Origem
from tests.test_compartilhamentos import _congelada


@pytest.fixture
def conexao():
    motor = sa.create_engine("sqlite://", poolclass=sa.pool.StaticPool)
    sa.event.listen(motor, "connect", lambda c, _: c.execute("PRAGMA foreign_keys=ON"))
    metadata.create_all(motor)
    with motor.begin() as conexao:
        yield conexao


@pytest.fixture
def ana(conexao):
    return entrar(
        conexao, "ana", "ana@exemplo.com", "Ana", "https://exemplo.com/f.png"
    )[0]


@pytest.fixture
def bia(conexao):
    return entrar(conexao, "bia", "bia@exemplo.com", "Bia")[0]


# --- aceite dos termos ---
def test_usuario_novo_precisa_aceitar(ana):
    assert conformidade.precisa_aceitar_os_termos(ana)


def test_aceitar_grava_versao_data_e_auditoria(conexao, ana):
    conformidade.registrar_aceite(conexao, ana.id)
    depois = buscar_por_id(conexao, ana.id)
    assert depois.termos_versao == conformidade.VERSAO_DOS_TERMOS
    assert depois.termos_aceitos_em is not None
    assert not conformidade.precisa_aceitar_os_termos(depois)
    registro = auditoria.listar_recentes(conexao)[0]
    assert registro.acao == auditoria.ACAO_TERMOS_ACEITOS
    assert registro.detalhes == {"versao": conformidade.VERSAO_DOS_TERMOS}


def test_nova_versao_dos_termos_pede_novo_aceite(conexao, ana, monkeypatch):
    conformidade.registrar_aceite(conexao, ana.id)
    monkeypatch.setattr(conformidade, "VERSAO_DOS_TERMOS", "2099-01-01")
    assert conformidade.precisa_aceitar_os_termos(buscar_por_id(conexao, ana.id))


def test_o_aceite_continua_depois_de_novo_login(conexao, ana):
    conformidade.registrar_aceite(conexao, ana.id)
    de_novo = entrar(conexao, "ana", "ana@exemplo.com", "Ana Souza")[0]
    assert not conformidade.precisa_aceitar_os_termos(de_novo)


# --- textos ---
@pytest.mark.parametrize("nome", ["termos", "privacidade"])
def test_textos_legais_existem_e_citam_o_essencial(nome):
    texto = conformidade.carregar_texto(nome)
    assert len(texto) > 800
    # o que o TickerLab é: plataforma de inteligência financeira, por assinatura
    assert "inteligência financeira" in texto.lower()


def test_termos_dizem_que_nada_e_recomendacao_de_investimento():
    termos = conformidade.carregar_texto("termos").lower()
    assert "nada aqui é recomendação de investimento" in termos
    assert "projeto educacional" not in termos  # produto comercial desde 13/10/2026


def test_texto_desconhecido():
    with pytest.raises(ValueError):
        conformidade.carregar_texto("../app")


def test_politica_de_privacidade_cobre_os_dados_e_os_direitos():
    texto = conformidade.carregar_texto("privacidade").lower()
    for termo in ("google", "stripe", "e-mail", "exportar", "apagar", "lgpd", "cookie"):
        assert termo in texto, termo


# --- exportar ---
def test_exportar_traz_tudo_da_pessoa_e_so_dela(conexao, ana, bia):
    repo.salvar_preferencias(conexao, ana.id, {"periodo": "5y"})
    repo.salvar_favoritos(conexao, ana.id, ["AAPL", "PETR4.SA"])
    repo.salvar_simulacao(
        conexao, ana.id, "backtest", "Minha", {"a": 1}, {"numeros": {"x": "1"}}
    )
    repo.salvar_favoritos(conexao, bia.id, ["VALE3.SA"])
    repo.salvar_simulacao(conexao, bia.id, "backtest", "Da Bia", {}, {})
    tentativas.registrar_tentativa(conexao, ana.id, "PETR4.SA", "a" * 64)
    tentativas.registrar_tentativa(conexao, bia.id, "VALE3.SA", "b" * 64)
    pulse.marcar_visita(conexao, ana.id, datetime(2026, 10, 13, 18, 0, tzinfo=UTC))
    pulse.marcar_visita(conexao, bia.id, datetime(2026, 10, 14, 9, 0, tzinfo=UTC))
    dados = conformidade.exportar_meus_dados(conexao, ana.id)
    assert dados["pulse"] == {"visto_em": "2026-10-13T18:00:00+00:00", "vereditos": {}}
    assert dados["tentativas_por_ativo"] == {"PETR4.SA": 1}
    assert dados["perfil"]["email"] == "ana@exemplo.com"
    assert dados["preferencias"] == {"periodo": "5y"}
    assert dados["favoritos"] == ["AAPL", "PETR4.SA"]
    assert [s["nome"] for s in dados["simulacoes"]] == ["Minha"]
    texto = json.dumps(dados)
    assert (
        "bia@exemplo.com" not in texto
        and "Da Bia" not in texto
        and "VALE3" not in texto
    )


def test_exportar_traz_a_origem_do_cadastro(conexao, ana, bia):
    origens.gravar_origem(
        conexao, ana.id, Origem(source="google", medium="cpc", ref="clube-do-robo")
    )
    origens.gravar_origem(conexao, bia.id, Origem(source="instagram"))

    origem = conformidade.exportar_meus_dados(conexao, ana.id)["origem_do_cadastro"]

    assert origem["utm_source"] == "google"
    assert origem["utm_medium"] == "cpc"
    assert origem["ref"] == "clube-do-robo"
    assert origem["gravada_em"]


def test_exportar_sem_origem_traz_none(conexao, ana):
    assert (
        conformidade.exportar_meus_dados(conexao, ana.id)["origem_do_cadastro"] is None
    )


def test_exportar_traz_os_links_compartilhados_so_da_pessoa(conexao, ana, bia):
    links.criar_link_da_ficha(conexao, ana.id, "gratuito", _congelada(), 30)
    outra = {**_congelada(), "ticker": "VALE3.SA"}
    links.criar_link_da_ficha(conexao, bia.id, "gratuito", outra, 30)
    (exportado,) = conformidade.exportar_meus_dados(conexao, ana.id)[
        "links_compartilhados"
    ]
    assert exportado["situacao"] == "ativo"
    assert exportado["ficha"]["ticker"] == "PETR4.SA"
    assert "VALE3" not in json.dumps(exportado)


def test_politica_de_privacidade_cita_as_tentativas_do_backtest():
    texto = conformidade.carregar_texto("privacidade")
    assert "tentativas" in texto and "SHA-256" in texto


def test_politica_de_privacidade_cita_os_links_compartilhados():
    """Sem subir a versão dos termos (Tiago, 14/10): o parágrafo fica só na política."""
    texto = conformidade.carregar_texto("privacidade")
    assert "Links compartilhados" in texto and "Quem tiver um link" in texto
    assert "os links compartilhados e a assinatura" in texto


def test_texto_14_descreve_a_ficha_de_originacao_e_as_garantias_da_sala():
    """Texto 14 (22/10, linha 194): o que a sala guarda além dos documentos, sem novo aceite."""
    privacidade = conformidade.carregar_texto("privacidade")
    assert "versão 14" in privacidade
    assert "**Ficha de originação e garantias:**" in privacidade
    assert "a ficha **não envia nada**" in privacidade
    assert "não são cifrados com a chave da operação" in privacidade
    assert (
        "e a ficha de originação, as exposições e as garantias de cada operação"
        in privacidade
    )
    assert (
        "as operações, os documentos, as fichas de originação e as garantias"
        in privacidade
    )


def test_texto_15_diz_os_6_digitos_do_meio_do_cpf_so_com_homonimo():
    """Texto 15 (23/10, linha 219): com homônimo no quadro da mesma empresa, só os 6 dígitos do meio.

    O que o #586 faz (`base.pessoas.oposicoes.achar_titular`) a política passa a dizer: nunca o CPF
    inteiro, só os dígitos que a Receita publica, só para casar o pedido com a linha certa. Sem novo
    aceite: o parágrafo fala com o sócio da base, não com quem tem conta, e não cria uso novo.
    """
    assert conformidade.VERSAO_DOS_TERMOS == "2026-10-22.13"
    privacidade = conformidade.carregar_texto("privacidade")
    assert "versão 15" in privacidade
    assert "dizendo qual empresa e o seu nome como a Receita o publica" in privacidade
    assert "só os **6 dígitos do meio do seu CPF**" in privacidade
    assert "**Nunca pedimos o CPF inteiro**" in privacidade
    assert "guardamos com a nossa resposta por 5 anos" in privacidade


def test_versao_13_dos_termos_diz_o_registro_de_acesso_ao_servidor_por_12_meses():
    """Versão 13 (22/10): quem entra no servidor e usa sudo fica 12 meses, cifrado, em outro computador."""
    assert conformidade.VERSAO_DOS_TERMOS == "2026-10-22.13"
    privacidade = conformidade.carregar_texto("privacidade")
    assert "usa privilégios de administrador" in privacidade
    assert "guardado por **12 meses**, cifrado, em outro computador" in privacidade
    assert "o comando executado" in privacidade


def test_versao_12_dos_termos_pede_novo_aceite_e_diz_as_copias_mensais_e_anuais():
    """Versão 8 (19/10): sessão de 30 dias (#461), encarregado e privacidade@, base legal.

    Versão 9 (21/10): transferência internacional provedor por provedor (P-35): o Stripe tem
    as cláusulas da ANPD, o Google e a Microsoft são responsáveis próprios no login e o IP de
    quem só visita o site vai à Cloudflare.

    Versão 10 (21/10): os sócios do cadastro público do CNPJ aparecem com o nome que a Receita
    publica, só no quadro de sócios da empresa consultada, com as regras da ADR 0106 (sem busca
    por pessoa, ligação sem dizer o sócio, um CNPJ por consulta, oposição em 15 dias).

    Versão 11 (21/10): a sala de dados (B-20, D13): nos dados de terceiros dentro dos documentos
    o cliente é o controlador e o TickerLab é o operador (LGPD, art. 39); os prazos e o apagamento
    batem com `src/sala/retencao.py`; nenhum modelo lê os documentos; cópias de 14 dias; aviso
    de incidente em 3 dias úteis. Termos e privacidade dizem a mesma coisa.

    Versão 12 (22/10): as cópias de segurança do banco (linha 155 da fila): além das diárias,
    apagadas em 14 dias, o recebedor guarda a primeira de cada mês por 12 meses e a primeira de
    cada ano por 5 anos (antes o texto prometia só os 14 dias); o que foi apagado fica nelas sem
    uso até vencerem e é apagado de novo numa restauração; a sala fica fora das cópias longas.
    """
    assert conformidade.VERSAO_DOS_TERMOS >= "2026-10-22.12"
    privacidade = conformidade.carregar_texto("privacidade")
    assert "Cada cópia é apagada depois de **14 dias**" not in privacidade
    assert "não aparecem no app" not in privacidade
    for trecho in (
        "## A sala de dados",
        "**Você é o controlador** dos dados de terceiros",
        "**O TickerLab é o operador** (LGPD, art. 39)",
        "**Nenhum modelo de linguagem** recebe os documentos da sala",
        "**90, 180 ou 365 dias** (180, se não escolher)",
        "mais **30 dias** para baixar",
        "apagar a operação apaga a chave dela",
        "separadas das do resto do app e apagadas depois de **14 dias**",
        "**primeira cópia de cada mês, por 12 meses**",
        "**primeira cópia de cada ano, por 5 anos**",
        "as contas apagadas depois dela são apagadas de novo",
        "ficam fora das cópias mensais e anuais",
        "as operações, os documentos, as fichas de originação e as garantias da sala de dados",
        "não consegue procurar documentos por nome nem por CPF",
        "no quadro de sócios da empresa que você consulta pelo CNPJ",
        "CPF mascarado como a Receita publica",
        "têm um sócio em comum, sem dizer qual",
        "uma empresa** de cada vez e fica registrada",
        "legítimo interesse (LGPD, art. 7º, IX, e art. 10)",
        "prospecção, marketing, montagem de perfil de pessoa ou revenda de listas",
        "não tem busca por nome de pessoa nem por CPF",
        "Fonte: Receita Federal, dados abertos do CNPJ",
        "sai da tela e da API em até 15 dias",
        "privacidade@tickerlab.com.br",
        "Encarregado",
        "__Host-tl_sessao",
        "Base legal",
        "tl_origem",
        "Transferência internacional",
        "Registros técnicos de acesso",
        'O contrato do Stripe traz também as cláusulas-padrão da ANPD (LGPD, art. 33, II, "b"',
        "o Google e a Microsoft tratam a sua conta como responsáveis próprios",
        "Quem só visita o site, sem conta, tem o endereço IP",
        "Os contratos da Cloudflare, do Resend e da Anthropic trazem só as cláusulas-padrão",
    ):
        assert trecho in privacidade, trecho
    termos = conformidade.carregar_texto("termos")
    assert "Pré-lançamento" in termos and "30 dias" in termos
    assert "modelo de linguagem" in termos and "nunca são acusação" in termos
    for trecho in (
        "## Sala de dados",
        "**você é o controlador** desses dados",
        "O TickerLab é o **operador** (LGPD, art. 39)",
        "**nunca** vão a um modelo nem a outro serviço",
        "**90, 180 ou 365 dias** (180, se não escolher)",
        "disponível para baixar por mais **30 dias**",
        "apagar a operação apaga a chave dela",
        "apagadas depois de **14 dias**",
        "em até **3 dias úteis**",
    ):
        assert trecho in termos, trecho


def test_os_prazos_da_sala_nos_textos_legais_batem_com_o_codigo():
    """Os textos prometem os prazos de `src/sala/retencao.py`: quem mudar um, muda o outro."""
    from src.sala import retencao

    assert retencao.PRAZOS_DE_GUARDA_EM_DIAS == (90, 180, 365)
    assert retencao.PRAZO_PADRAO_EM_DIAS == 180
    assert retencao.DIAS_PARA_BAIXAR_DEPOIS_DE_ENCERRAR == 30
    assert retencao.PRORROGACAO_MAXIMA_EM_DIAS == 365
    for nome in ("termos", "privacidade"):
        texto = conformidade.carregar_texto(nome)
        assert "**90, 180 ou 365 dias** (180, se não escolher)" in texto, nome
        assert "365 dias de cada vez" in texto and "**30 dias**" in texto, nome


def test_politica_de_privacidade_cita_o_pulse():
    texto = conformidade.carregar_texto("privacidade")
    assert "Pulse" in texto


def test_exportar_sem_pulse_aberto_traz_vazio(conexao, ana):
    assert conformidade.exportar_meus_dados(conexao, ana.id)["pulse"] is None


def test_politica_de_privacidade_cita_o_diario_de_teses():
    texto = conformidade.carregar_texto("privacidade")
    assert "Diário de Teses" in texto and "anotações do Diário de Teses" in texto


def test_exportar_meus_dados_inclui_o_diario(conexao, ana, bia):
    diario.escrever(conexao, ana.id, "PETR4", "Tese da Ana")
    diario.escrever(conexao, bia.id, "VALE3", "Tese da Bia")
    exportado = conformidade.exportar_meus_dados(conexao, ana.id)["diario_de_teses"]
    assert [(t["ticker"], t["texto"]) for t in exportado] == [
        ("PETR4.SA", "Tese da Ana")
    ]


def test_apagar_a_conta_apaga_o_diario(conexao, ana, bia):
    diario.escrever(conexao, ana.id, "PETR4", "Tese da Ana")
    diario.escrever(conexao, bia.id, "PETR4", "Tese da Bia")
    assert conformidade.apagar_conta(conexao, ana.id) is True
    assert diario.listar(conexao, ana.id) == []
    assert len(diario.listar(conexao, bia.id)) == 1


def test_exportar_vira_json_e_registra_na_auditoria(conexao, ana):
    dados = conformidade.exportar_meus_dados(conexao, ana.id)
    json.dumps(dados)  # não pode ter nada que o JSON não aceite (datas, UUIDs)
    assert auditoria.listar_recentes(conexao)[0].acao == auditoria.ACAO_DADOS_EXPORTADOS


def test_exportar_nao_vaza_ids_do_stripe(conexao, ana):
    conexao.execute(
        sa.insert(assinaturas).values(
            usuario_id=ana.id,
            stripe_customer_id="cus_SECRETO",
            stripe_subscription_id="sub_SECRETO",
            status="active",
            cancela_no_fim=False,
            evento_em=1,
        )
    )
    dados = conformidade.exportar_meus_dados(conexao, ana.id)
    assert dados["assinatura"]["status"] == "active"
    assert "SECRETO" not in json.dumps(dados)


def test_exportar_traz_as_formas_de_entrar_e_as_sessoes_sem_segredo(conexao, ana, bia):
    sessoes.abrir(conexao, ana.id, "google")
    sessoes.abrir(conexao, bia.id, "google")
    dados = conformidade.exportar_meus_dados(conexao, ana.id)
    (forma,) = dados["formas_de_entrar"]
    assert forma["provedor"] == "google" and forma["email"] == "ana@exemplo.com"
    assert set(forma) == {
        "provedor",
        "email",
        "email_confirmado",
        "criada_em",
        "ultimo_uso",
    }
    (sessao,) = dados["sessoes_de_login"]
    assert sessao["provedor"] == "google" and sessao["encerrada_em"] is None
    assert set(sessao) == {
        "provedor",
        "criada_em",
        "expira_em",
        "ultimo_uso",
        "encerrada_em",
    }
    texto = json.dumps(dados)
    # nem o hash do token nem o identificador do provedor saem no arquivo
    hashes = conexao.execute(sa.select(sessoes_de_login.c.hash_do_token)).scalars()
    assert all(h not in texto for h in hashes)
    assert '"ana"' not in texto and "bia@exemplo.com" not in texto


def test_apagar_conta_apaga_as_formas_de_entrar_e_as_sessoes(conexao, ana, bia):
    sessoes.abrir(conexao, ana.id, "google")
    sessoes.abrir(conexao, bia.id, "google")
    assert conformidade.apagar_conta(conexao, ana.id) is True
    for tabela in (identidades, sessoes_de_login):
        donos = conexao.execute(sa.select(tabela.c.usuario_id)).scalars().all()
        assert donos == [bia.id]


def test_exportar_de_quem_nao_existe(conexao):
    with pytest.raises(LookupError):
        conformidade.exportar_meus_dados(conexao, uuid.uuid4())


# --- apagar a conta ---
def test_apagar_conta_remove_tudo_da_pessoa_e_so_dela(conexao, ana, bia):
    repo.salvar_favoritos(conexao, ana.id, ["AAPL"])
    repo.salvar_preferencias(conexao, ana.id, {"periodo": "5y"})
    repo.salvar_simulacao(conexao, ana.id, "backtest", "Minha", {}, {})
    repo.salvar_simulacao(conexao, bia.id, "backtest", "Da Bia", {}, {})
    assert conformidade.apagar_conta(conexao, ana.id) is True
    assert buscar_por_id(conexao, ana.id) is None
    assert repo.listar_simulacoes(conexao, ana.id) == []
    assert repo.listar_favoritos(conexao, ana.id) == []
    assert repo.carregar_preferencias(conexao, ana.id) == {}
    assert len(repo.listar_simulacoes(conexao, bia.id)) == 1  # a da Bia continua


def test_apagar_deixa_so_um_registro_sem_dado_pessoal(conexao, ana):
    conformidade.registrar_aceite(conexao, ana.id)  # a auditoria dela aponta para ela
    conformidade.apagar_conta(conexao, ana.id)
    registros = auditoria.listar_recentes(conexao)
    assert registros[0].acao == auditoria.ACAO_CONTA_APAGADA
    assert registros[0].alvo_id == ana.id and registros[0].ator_id is None
    assert all(r.ator_id is None for r in registros)  # os do aceite perderam o vínculo
    texto = str([(r.detalhes, r.acao) for r in registros])
    assert "ana@exemplo.com" not in texto


def test_apagar_quem_nao_existe(conexao):
    assert conformidade.apagar_conta(conexao, uuid.uuid4()) is False
    assert auditoria.listar_recentes(conexao) == []


# --- encerrar a cobrança no Stripe ---
class StripeFalso:
    def __init__(self, falha_ao_cancelar=False, falha_ao_apagar=False):
        self.chamadas = []

        def cancelar(id_):
            self.chamadas.append(("cancelar", id_))
            if falha_ao_cancelar:
                raise stripe.InvalidRequestError("já cancelada", "id")

        def apagar(id_):
            self.chamadas.append(("apagar", id_))
            if falha_ao_apagar:
                raise stripe.InvalidRequestError("não existe", "id")

        self.v1 = SimpleNamespace(
            subscriptions=SimpleNamespace(cancel=cancelar),
            customers=SimpleNamespace(delete=apagar),
        )


def _assinatura(status="active"):
    return Assinatura(uuid.uuid4(), "cus_1", "sub_1", status, None, False)


def test_encerrar_cancela_a_assinatura_e_apaga_o_cliente():
    stripe_falso = StripeFalso()
    encerrar_cobranca(_assinatura(), cliente=stripe_falso)
    assert stripe_falso.chamadas == [("cancelar", "sub_1"), ("apagar", "cus_1")]


def test_encerrar_nao_cancela_de_novo_o_que_ja_esta_cancelado():
    stripe_falso = StripeFalso()
    encerrar_cobranca(_assinatura("canceled"), cliente=stripe_falso)
    assert stripe_falso.chamadas == [("apagar", "cus_1")]


def test_encerrar_tolera_o_que_ja_nao_existe_no_stripe():
    stripe_falso = StripeFalso(falha_ao_cancelar=True, falha_ao_apagar=True)
    encerrar_cobranca(_assinatura(), cliente=stripe_falso)  # não levanta erro


def test_encerrar_sem_assinatura_nao_faz_nada():
    stripe_falso = StripeFalso()
    encerrar_cobranca(None, cliente=stripe_falso)
    assert stripe_falso.chamadas == []
