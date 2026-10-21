"""As rotas da sala de dados (src/api_v1/sala.py, B-20 PR 3).

Banco SQLite com as migrações, disco numa pasta temporária, chave-mestra gerada no teste e a
leitura num subprocesso de verdade. O que estes testes travam: só admin entra; uma conta nunca vê,
baixa, muda nem apaga a sala da outra (nem trocando o id na URL); o arquivo sai sempre como anexo;
os limites valem; e nome de arquivo nunca vai para a auditoria.
"""

import dataclasses
import io
import json
import uuid
import zipfile

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from src import api, auditoria
from src.api_v1 import VARIAVEL_DA_CHAVE, acesso
from src.api_v1 import sala as rotas_da_sala
from src.banco.modelo import auditoria as tabela_da_auditoria
from src.banco.usuarios import entrar, mudar_papel
from src.conformidade import registrar_aceite
from src.sala import arquivos, cofre, guarda
from tests import ajudantes_da_sala as gerar
from tests.ajudantes_da_api import AGORA, da_sessao

NOME_SENSIVEL = "Laudo da Fulana de Tal 123.pdf"
OPERACAO = {"tipo": "ma", "nome": "Aquisição da Alfa", "prazo_em_dias": 180}
ID_QUE_NAO_EXISTE = uuid.uuid4()


@pytest.fixture(autouse=True)
def ambiente(monkeypatch, tmp_path):
    monkeypatch.setenv(cofre.VARIAVEL_DA_CHAVE_MESTRA, cofre.gerar_chave_mestra())
    monkeypatch.setenv(guarda.VARIAVEL_DA_PASTA, str(tmp_path / "dados_sala"))
    monkeypatch.setenv(VARIAVEL_DA_CHAVE, "1")
    monkeypatch.setattr(acesso, "agora", lambda: AGORA)
    acesso.LIMITE.zerar()
    rotas_da_sala.LIMITE_DE_ENVIOS.zerar()


@pytest.fixture
def app():
    return api.criar_app({VARIAVEL_DA_CHAVE: "1"})


def _conta(banco, app, sub, admin=True):
    with banco.begin() as conexao:
        usuario = entrar(conexao, sub, f"{sub}@exemplo.com", sub.title())[0]
        registrar_aceite(conexao, usuario.id)
        if admin:
            mudar_papel(conexao, usuario.id, "admin")
    return TestClient(app, headers=da_sessao(banco, usuario))


@pytest.fixture
def ana(banco, app):
    return _conta(banco, app, "ana")


@pytest.fixture
def bia(banco, app):
    return _conta(banco, app, "bia")


@pytest.fixture
def carla(banco, app):
    """Uma conta que não é admin."""
    return _conta(banco, app, "carla", admin=False)


def _criar(cliente, **mudancas):
    resposta = cliente.post("/v1/operacoes", json={**OPERACAO, **mudancas})
    assert resposta.status_code == 201, resposta.text
    return resposta.json()["id"]


def _enviar(cliente, operacao_id, conteudo=None, nome=NOME_SENSIVEL):
    conteudo = conteudo if conteudo is not None else gerar.pdf("Receita 100")
    return cliente.post(
        f"/v1/operacoes/{operacao_id}/documentos",
        files={"arquivo": (nome, conteudo, "application/pdf")},
    )


def _documento(cliente, operacao_id, conteudo=None, nome=NOME_SENSIVEL):
    resposta = _enviar(cliente, operacao_id, conteudo, nome)
    assert resposta.status_code == 201, resposta.text
    return resposta.json()["id"]


# --- quem entra ---------------------------------------------------------------------------


def _chamadas(operacao_id, documento_id):
    """Cada rota da sala, como (método, endereço, corpo JSON ou None)."""
    base = f"/v1/operacoes/{operacao_id}"
    return [
        ("GET", "/v1/operacoes", None),
        ("POST", "/v1/operacoes", OPERACAO),
        ("GET", base, None),
        ("POST", f"{base}/encerrar", None),
        ("POST", f"{base}/prorrogar", {"dias": 30}),
        ("DELETE", base, None),
        ("GET", f"{base}/documentos", None),
        ("GET", f"{base}/documentos/{documento_id}/arquivo", None),
        ("DELETE", f"{base}/documentos/{documento_id}", None),
        ("GET", f"{base}/sala", None),
    ]


def test_toda_rota_da_sala_exige_conta_de_admin():
    """Rota nova na sala sem a trava de admin falha aqui, antes de chegar à produção."""
    for rota in rotas_da_sala.router.routes:
        dependencias = {d.call for d in rota.dependant.dependencies}  # type: ignore[attr-defined]
        assert rotas_da_sala.conta_da_sala in dependencias, rota.path  # type: ignore[attr-defined]


def test_quem_nao_e_admin_nao_ve_a_sala(carla, ana):
    operacao = _criar(ana)
    documento = _documento(ana, operacao)
    for metodo, endereco, corpo in _chamadas(operacao, documento):
        resposta = carla.request(metodo, endereco, json=corpo)
        assert resposta.status_code == 404, (metodo, endereco)
    resposta = carla.post(
        f"/v1/operacoes/{operacao}/documentos",
        files={"arquivo": ("a.pdf", gerar.pdf("x"), "application/pdf")},
    )
    assert resposta.status_code == 404


def test_sem_login_a_sala_responde_401(app):
    anonimo = TestClient(app)
    assert anonimo.get("/v1/operacoes").status_code == 401
    assert anonimo.delete(f"/v1/operacoes/{ID_QUE_NAO_EXISTE}").status_code == 401


def test_pedido_que_muda_a_sala_precisa_vir_do_proprio_app(banco, app, ana):
    operacao = _criar(ana)
    de_fora = TestClient(
        app, headers={"Cookie": ana.headers["Cookie"]}
    )  # sem o cabeçalho do app
    assert de_fora.delete(f"/v1/operacoes/{operacao}").status_code == 403
    assert ana.get(f"/v1/operacoes/{operacao}").status_code == 200  # nada foi apagado


def test_a_api_desligada_nao_tem_sala(monkeypatch, banco):
    monkeypatch.delenv(VARIAVEL_DA_CHAVE)
    desligada = TestClient(api.criar_app({}))
    assert desligada.get("/v1/operacoes").status_code == 404


# --- operações ----------------------------------------------------------------------------


def test_criar_listar_ver_encerrar_prorrogar_e_apagar(ana):
    operacao = _criar(ana)
    assert [o["id"] for o in ana.get("/v1/operacoes").json()] == [operacao]
    visto = ana.get(f"/v1/operacoes/{operacao}").json()
    assert visto["nome"] == "Aquisição da Alfa" and visto["situacao"] == "aberta"
    prorrogada = ana.post(f"/v1/operacoes/{operacao}/prorrogar", json={"dias": 365})
    assert prorrogada.json()["retencao_ate"] > visto["retencao_ate"]
    encerrada = ana.post(f"/v1/operacoes/{operacao}/encerrar").json()
    assert encerrada["situacao"] == "encerrada"
    assert ana.delete(f"/v1/operacoes/{operacao}").status_code == 204
    assert ana.get(f"/v1/operacoes/{operacao}").status_code == 404
    assert ana.delete(f"/v1/operacoes/{operacao}").status_code == 404


@pytest.mark.parametrize(
    "pedido",
    [
        {**OPERACAO, "tipo": "outro"},
        {**OPERACAO, "prazo_em_dias": 45},
        {**OPERACAO, "nome": "   "},
        {**OPERACAO, "nome": "x" * 501},
    ],
)
def test_operacao_com_pedido_invalido_da_422(ana, pedido):
    assert ana.post("/v1/operacoes", json=pedido).status_code == 422


@pytest.mark.parametrize("dias", [0, 366, -1])
def test_prorrogar_fora_de_1_a_365_dias_da_422(ana, dias):
    operacao = _criar(ana)
    resposta = ana.post(f"/v1/operacoes/{operacao}/prorrogar", json={"dias": dias})
    assert resposta.status_code == 422


def test_limite_de_operacoes_por_conta(ana, monkeypatch):
    pequeno = dataclasses.replace(rotas_da_sala.limites_do(None), operacoes_na_sala=2)
    monkeypatch.setattr(rotas_da_sala, "limites_do", lambda _plano: pequeno)
    _criar(ana)
    _criar(ana)
    resposta = ana.post("/v1/operacoes", json=OPERACAO)
    assert resposta.status_code == 409 and "2 operações" in resposta.json()["detail"]


def test_o_limite_de_operacoes_e_por_conta(ana, bia, monkeypatch):
    pequeno = dataclasses.replace(rotas_da_sala.limites_do(None), operacoes_na_sala=1)
    monkeypatch.setattr(rotas_da_sala, "limites_do", lambda _plano: pequeno)
    _criar(ana)
    _criar(bia)  # a sala cheia da Ana não conta para a Bia


# --- documentos ---------------------------------------------------------------------------


def test_enviar_ler_baixar_e_apagar_um_documento(ana):
    operacao = _criar(ana)
    original = gerar.pdf("Receita líquida 100")
    enviado = _enviar(ana, operacao, original)
    assert enviado.status_code == 201
    documento = enviado.json()
    assert documento["situacao"] == "na_fila" and documento["tipo"] == "pdf"
    assert set(documento) == {
        "id",
        "nome",
        "tipo",
        "tamanho_bytes",
        "paginas",
        "situacao",
        "recebido_em",
    }
    # a leitura roda em segundo plano, depois da resposta (o cliente de teste espera por ela)
    listados = ana.get(f"/v1/operacoes/{operacao}/documentos").json()
    assert [d["id"] for d in listados] == [documento["id"]]
    assert listados[0]["situacao"] == "lido" and listados[0]["paginas"] == 1

    baixado = ana.get(f"/v1/operacoes/{operacao}/documentos/{documento['id']}/arquivo")
    assert baixado.status_code == 200 and baixado.content == original
    apagado = ana.delete(f"/v1/operacoes/{operacao}/documentos/{documento['id']}")
    assert apagado.status_code == 204
    assert ana.get(f"/v1/operacoes/{operacao}/documentos").json() == []
    nao_acha = ana.get(f"/v1/operacoes/{operacao}/documentos/{documento['id']}/arquivo")
    assert nao_acha.status_code == 404


def test_o_arquivo_baixa_sempre_como_anexo_sem_ser_aberto(ana):
    operacao = _criar(ana)
    documento = _documento(ana, operacao)
    resposta = ana.get(f"/v1/operacoes/{operacao}/documentos/{documento}/arquivo")
    assert resposta.headers["content-type"] == "application/octet-stream"
    assert resposta.headers["x-content-type-options"] == "nosniff"
    assert resposta.headers["content-security-policy"] == "sandbox"
    assert resposta.headers["cache-control"] == "no-store"
    assert resposta.headers["content-disposition"].startswith("attachment;")


def test_nome_estranho_nao_quebra_o_cabecalho_do_download(ana):
    operacao = _criar(ana)
    nome = 'a\r\nSet-Cookie: x=1"/../laudo.pdf'
    documento = _documento(ana, operacao, nome=nome)
    resposta = ana.get(f"/v1/operacoes/{operacao}/documentos/{documento}/arquivo")
    cabecalho = resposta.headers["content-disposition"]
    assert "\r" not in cabecalho and "\n" not in cabecalho
    assert "set-cookie" not in resposta.headers
    assert "/" not in cabecalho.split("filename*=UTF-8''")[1].replace("%2F", "")


@pytest.mark.parametrize(
    ("conteudo", "motivo"),
    [
        (gerar.pdf_com_javascript(), arquivos.PDF_ATIVO),
        (gerar.pdf_cifrado(), arquivos.PDF_CIFRADO),
        (gerar.xlsx_com_macro(), arquivos.COM_MACRO),
        (b"MZ\x90\x00 isto nao e documento", arquivos.TIPO_NAO_ACEITO),
        (b"", arquivos.VAZIO),
    ],
)
def test_arquivo_recusado_volta_422_com_o_codigo_e_nao_entra(ana, conteudo, motivo):
    operacao = _criar(ana)
    resposta = _enviar(ana, operacao, conteudo, nome="arquivo.pdf")
    assert resposta.status_code == 422
    assert resposta.json()["motivo"] == motivo
    assert resposta.json()["detail"]
    assert ana.get(f"/v1/operacoes/{operacao}/documentos").json() == []


def test_arquivo_acima_de_25_mb_e_recusado(ana):
    operacao = _criar(ana)
    grande = b"%PDF-" + b"0" * arquivos.TAMANHO_MAXIMO_DO_ARQUIVO
    resposta = _enviar(ana, operacao, grande, nome="grande.pdf")
    assert resposta.status_code == 422
    assert resposta.json()["motivo"] == arquivos.GRANDE_DEMAIS


def test_a_recusa_fica_na_auditoria_so_com_o_codigo(banco, ana):
    operacao = _criar(ana)
    _enviar(ana, operacao, gerar.pdf_com_javascript(), nome=NOME_SENSIVEL)
    with banco.connect() as conexao:
        recusas = conexao.execute(
            sa.select(tabela_da_auditoria).where(
                tabela_da_auditoria.c.acao == auditoria.ACAO_DOCUMENTO_RECUSADO
            )
        ).all()
    assert len(recusas) == 1
    assert recusas[0].detalhes["motivo"] == arquivos.PDF_ATIVO
    assert "Fulana" not in json.dumps(dict(recusas[0].detalhes))


def test_o_mesmo_arquivo_duas_vezes_na_mesma_sala_da_409(ana):
    operacao = _criar(ana)
    conteudo = gerar.pdf("igual")
    _documento(ana, operacao, conteudo)
    assert _enviar(ana, operacao, conteudo).status_code == 409


def test_o_mesmo_arquivo_em_salas_diferentes_entra(ana):
    conteudo = gerar.pdf("igual")
    _documento(ana, _criar(ana), conteudo)
    _documento(ana, _criar(ana, nome="Outra"), conteudo)


def test_operacao_encerrada_nao_recebe_documento(ana):
    operacao = _criar(ana)
    ana.post(f"/v1/operacoes/{operacao}/encerrar")
    assert _enviar(ana, operacao).status_code == 409


def test_envio_sem_o_campo_arquivo_da_422(ana):
    operacao = _criar(ana)
    resposta = ana.post(f"/v1/operacoes/{operacao}/documentos", data={"x": "1"})
    assert resposta.status_code == 422


def test_limite_de_documentos_e_de_tamanho_por_operacao(ana, monkeypatch):
    base = rotas_da_sala.limites_do(None)
    pequeno = dataclasses.replace(base, documentos_por_operacao=2)
    monkeypatch.setattr(rotas_da_sala, "limites_do", lambda _plano: pequeno)
    operacao = _criar(ana)
    _documento(ana, operacao, gerar.pdf("um"))
    _documento(ana, operacao, gerar.pdf("dois"))
    resposta = _enviar(ana, operacao, gerar.pdf("três"))
    assert resposta.status_code == 409 and "2 documentos" in resposta.json()["detail"]

    apertado = dataclasses.replace(base, bytes_por_operacao=3 * arquivos.MEGABYTE)
    monkeypatch.setattr(rotas_da_sala, "limites_do", lambda _plano: apertado)
    outra = _criar(ana, nome="Outra")
    resposta = _enviar(ana, outra, gerar.pdf("a"))  # pequeno: cabe
    assert resposta.status_code == 201
    cheio = gerar.pdf("b") + b"\n%" + b"0" * (4 * arquivos.MEGABYTE)
    resposta = _enviar(ana, outra, cheio)
    assert resposta.status_code == 409 and "MB" in resposta.json()["detail"]


def test_trinta_envios_por_hora_e_o_31o_da_429(ana, monkeypatch):
    assert limites_de_envio() == 30
    monkeypatch.setattr(rotas_da_sala.LIMITE_DE_ENVIOS, "por_minuto", 2)
    operacao = _criar(ana)
    _documento(ana, operacao, gerar.pdf("um"))
    # o envio recusado também conta: ninguém testa a conferência em massa
    assert _enviar(ana, operacao, gerar.pdf_com_javascript()).status_code == 422
    assert _enviar(ana, operacao, gerar.pdf("três")).status_code == 429


def limites_de_envio():
    return rotas_da_sala.limites_do("gratuito").envios_por_hora


def test_o_limite_de_envios_e_por_conta(ana, bia, monkeypatch):
    monkeypatch.setattr(rotas_da_sala.LIMITE_DE_ENVIOS, "por_minuto", 1)
    _documento(ana, _criar(ana), gerar.pdf("um"))
    assert _enviar(ana, _criar(ana, nome="B")).status_code == 429
    _documento(bia, _criar(bia), gerar.pdf("um"))  # a Bia não paga pela Ana


def test_sem_a_chave_mestra_o_envio_da_503_e_nada_fica(ana, monkeypatch, banco):
    operacao = _criar(ana)
    monkeypatch.delenv(cofre.VARIAVEL_DA_CHAVE_MESTRA)
    assert _enviar(ana, operacao).status_code == 503
    assert ana.get(f"/v1/operacoes/{operacao}/documentos").json() == []


def test_documento_que_sumiu_do_disco_da_503_sem_dizer_onde(ana, tmp_path):
    operacao = _criar(ana)
    documento = _documento(ana, operacao)
    for arquivo in (tmp_path / "dados_sala").rglob("*.bin"):
        arquivo.unlink()
    resposta = ana.get(f"/v1/operacoes/{operacao}/documentos/{documento}/arquivo")
    assert resposta.status_code == 503
    assert str(tmp_path) not in resposta.text


# --- Baixar a sala ------------------------------------------------------------------------


def test_baixar_a_sala_devolve_um_zip_com_todos_os_documentos(banco, ana):
    operacao = _criar(ana)
    um, dois = gerar.pdf("um"), gerar.pdf("dois")
    _documento(ana, operacao, um, nome="relatorio.pdf")
    _documento(ana, operacao, dois, nome="relatorio.pdf")  # o mesmo nome, outro arquivo
    resposta = ana.get(f"/v1/operacoes/{operacao}/sala")
    assert resposta.status_code == 200
    assert resposta.headers["content-disposition"].startswith("attachment;")
    assert resposta.headers["x-content-type-options"] == "nosniff"
    assert int(resposta.headers["content-length"]) == len(resposta.content)
    with zipfile.ZipFile(io.BytesIO(resposta.content)) as zip_:
        assert sorted(zip_.namelist()) == ["001-relatorio.pdf", "002-relatorio.pdf"]
        assert {zip_.read(n) for n in zip_.namelist()} == {um, dois}
    with banco.connect() as conexao:
        registro = conexao.execute(
            sa.select(tabela_da_auditoria).where(
                tabela_da_auditoria.c.acao == auditoria.ACAO_SALA_BAIXADA
            )
        ).one()
    assert dict(registro.detalhes) == {
        "documentos": 2,
        "tamanho_bytes": len(um) + len(dois),
    }


def test_o_zip_nao_leva_caminho_nem_nome_perigoso(ana):
    operacao = _criar(ana)
    _documento(ana, operacao, nome="../../etc/passwd.pdf")
    with zipfile.ZipFile(
        io.BytesIO(ana.get(f"/v1/operacoes/{operacao}/sala").content)
    ) as z:
        for nome in z.namelist():
            assert "/" not in nome and "\\" not in nome


def test_sala_vazia_baixa_um_zip_vazio(ana):
    operacao = _criar(ana)
    resposta = ana.get(f"/v1/operacoes/{operacao}/sala")
    assert resposta.status_code == 200
    with zipfile.ZipFile(io.BytesIO(resposta.content)) as zip_:
        assert zip_.namelist() == []


def test_documento_ilegivel_derruba_o_zip_inteiro_e_nao_audita(banco, ana, tmp_path):
    operacao = _criar(ana)
    _documento(ana, operacao)
    for arquivo in (tmp_path / "dados_sala").rglob("*.bin"):
        arquivo.unlink()
    assert ana.get(f"/v1/operacoes/{operacao}/sala").status_code == 503
    with banco.connect() as conexao:
        baixadas = conexao.execute(
            sa.select(sa.func.count()).where(
                tabela_da_auditoria.c.acao == auditoria.ACAO_SALA_BAIXADA
            )
        ).scalar_one()
    assert baixadas == 0


# --- isolamento entre contas --------------------------------------------------------------


def test_a_conta_b_com_os_ids_da_a_nao_ve_nem_muda_nada(ana, bia):
    operacao = _criar(ana)
    documento = _documento(ana, operacao)
    for metodo, endereco, corpo in _chamadas(operacao, documento):
        if endereco == "/v1/operacoes":
            continue  # listar e criar são da própria conta
        resposta = bia.request(metodo, endereco, json=corpo)
        assert resposta.status_code == 404, (metodo, endereco, resposta.text)
        assert str(operacao) not in resposta.text
    envio = _enviar(bia, operacao)
    assert envio.status_code == 404
    assert bia.get("/v1/operacoes").json() == []
    # nada da Ana mudou
    assert ana.get(f"/v1/operacoes/{operacao}").json()["situacao"] == "aberta"
    assert len(ana.get(f"/v1/operacoes/{operacao}/documentos").json()) == 1
    arquivo = ana.get(f"/v1/operacoes/{operacao}/documentos/{documento}/arquivo")
    assert arquivo.status_code == 200


def test_trocar_o_id_do_documento_na_url_de_outra_sala_da_404(ana, bia):
    sala_da_ana = _criar(ana)
    documento_da_ana = _documento(ana, sala_da_ana)
    sala_da_bia = _criar(bia)
    # a sala é da Bia, o documento é da Ana
    base = f"/v1/operacoes/{sala_da_bia}/documentos/{documento_da_ana}"
    assert bia.get(f"{base}/arquivo").status_code == 404
    assert bia.delete(base).status_code == 404
    # e dentro da própria Ana, o documento numa sala que não é a dele
    outra_da_ana = _criar(ana, nome="Outra")
    base = f"/v1/operacoes/{outra_da_ana}/documentos/{documento_da_ana}"
    assert ana.get(f"{base}/arquivo").status_code == 404
    assert ana.delete(base).status_code == 404
    assert ana.get(f"/v1/operacoes/{sala_da_ana}/documentos").json()[0]["id"]


def test_id_que_nao_existe_responde_igual_ao_de_outra_conta(ana, bia):
    operacao = _criar(ana)
    de_outra = bia.get(f"/v1/operacoes/{operacao}")
    inexistente = bia.get(f"/v1/operacoes/{ID_QUE_NAO_EXISTE}")
    assert (de_outra.status_code, de_outra.json()) == (
        inexistente.status_code,
        inexistente.json(),
    )


def test_id_que_nao_e_uuid_da_422_sem_tocar_no_banco(ana):
    assert ana.get("/v1/operacoes/1; DROP TABLE operacoes").status_code == 422


def test_apagar_a_operacao_apaga_os_arquivos_do_disco(ana, tmp_path):
    operacao = _criar(ana)
    _documento(ana, operacao)
    assert list((tmp_path / "dados_sala").rglob("*.bin"))
    assert ana.delete(f"/v1/operacoes/{operacao}").status_code == 204
    assert not list((tmp_path / "dados_sala").rglob("*.bin"))


def test_a_auditoria_da_sala_leva_so_ids(banco, ana):
    operacao = _criar(ana)
    documento = _documento(ana, operacao)
    ana.get(f"/v1/operacoes/{operacao}/documentos/{documento}/arquivo")
    ana.get(f"/v1/operacoes/{operacao}/sala")
    ana.delete(f"/v1/operacoes/{operacao}/documentos/{documento}")
    ana.delete(f"/v1/operacoes/{operacao}")
    with banco.connect() as conexao:
        registros = conexao.execute(sa.select(tabela_da_auditoria)).all()
    acoes = {r.acao for r in registros}
    assert {
        auditoria.ACAO_OPERACAO_CRIADA,
        auditoria.ACAO_DOCUMENTO_ENVIADO,
        auditoria.ACAO_DOCUMENTO_BAIXADO,
        auditoria.ACAO_SALA_BAIXADA,
        auditoria.ACAO_DOCUMENTO_APAGADO,
        auditoria.ACAO_OPERACAO_APAGADA,
    } <= acoes
    texto = json.dumps([dict(r.detalhes) for r in registros])
    assert "Fulana" not in texto and "Aquisição" not in texto


def test_o_log_da_sala_nao_leva_nome_de_arquivo(ana, caplog):
    caplog.set_level("DEBUG")
    operacao = _criar(ana)
    _enviar(ana, operacao, gerar.pdf_com_javascript(), nome=NOME_SENSIVEL)
    _documento(ana, operacao, nome=NOME_SENSIVEL)
    assert "Fulana" not in caplog.text and "Laudo" not in caplog.text
