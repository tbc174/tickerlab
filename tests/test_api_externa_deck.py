"""O deck (`.pptx`) pela API externa (linha 782): `/data/v1/sectors/{key}/deck` e `/data/v1/companies/{cnpj}/deck`.

O deck sai do mesmo leitor e do mesmo portão das rotas JSON do setor (`test_api_externa_setores.py`) e do
perfil (`test_api_externa_por_cnpj_perfil.py`), com as mesmas bases de mentira: o que o contrato não libera
não entra no arquivo. Riscos: pessoa física dentro do deck, uma organização lendo o que é da outra, texto do
dado quebrando o arquivo, arquivo grande demais e o pedido fora da quota.
"""

from datetime import UTC, datetime
from io import BytesIO

import pytest
from pptx import Presentation

from base.porta import Porta
from scripts.gerar_openapi_data import openapi_data_v1
from src import apresentacao
from src.api_externa import acesso, deck, rotas
from src.api_externa.conjuntos import empresas, ficha, setores
from src.banco import chaves_da_api as cb
from tests import ajudantes_da_api_externa as aj
from tests import test_api_externa_empresas as empresas_de_mentira
from tests import test_api_externa_por_cnpj_ficha as ficha_de_mentira
from tests import test_api_externa_por_cnpj_perfil as perfil
from tests import test_api_externa_setores as do_setor
from tests.test_relatorio_setor import gravar_noite, secao_da_noite

AGORA = do_setor.AGORA
PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
DECK_DO_SETOR = "/data/v1/sectors/eletricas/deck"
EMPRESA = empresas_de_mentira.EMPRESA
DECK_DA_EMPRESA = f"/data/v1/companies/{EMPRESA}/deck"
UM_MEGA = 1024 * 1024


def _textos(conteudo: bytes) -> str:
    """Todo texto do arquivo: as caixas, as células das tabelas e o título do documento."""
    arquivo = Presentation(BytesIO(conteudo))
    partes = [arquivo.core_properties.title or ""]
    for slide in arquivo.slides:
        for forma in slide.shapes:
            if forma.has_text_frame:
                partes.append(forma.text_frame.text)
            if forma.has_table:
                partes += [
                    celula.text for linha in forma.table.rows for celula in linha.cells
                ]
    return "\n".join(partes)


def _slides(conteudo: bytes) -> int:
    return len(Presentation(BytesIO(conteudo)).slides)


def _consumo(banco, org) -> cb.ConsumoDoMes:
    with banco.connect() as conexao:
        return cb.consumo_do_mes(conexao, org.id, AGORA.date())


def _organizacao_com(banco, conjunto: str, nome: str):
    ator = aj.admin(banco)  # o mesmo admin cria as duas organizações
    org = aj.organizacao(banco, ator, nome=nome)
    chave = aj.chave(banco, ator, org)
    aj.contrato(banco, ator, org, conjunto=conjunto)
    return org, chave


def _get(cliente, chave, rota: str, **parametros):
    return cliente.get(rota, params=parametros, headers=aj.bearer(chave.valor))


# ---------------------------------------------------------------- o deck do setor


@pytest.fixture
def noite(tmp_path, monkeypatch):
    gravar_noite(tmp_path)
    monkeypatch.setenv("TICKERLAB_DOSSIES", str(tmp_path))
    monkeypatch.setattr(rotas, "regras_da_api", do_setor._regras)
    return tmp_path


@pytest.fixture
def setor(banco, monkeypatch, noite):
    """Uma organização com contrato de `sectors` e o cliente da API."""
    org, chave = _organizacao_com(banco, setores.CONJUNTO, "Alfa Gestora")
    return aj.cliente_da_api(monkeypatch, AGORA), org, chave


def _regravar(pasta, mudar) -> None:
    secao = secao_da_noite()
    mudar(secao)
    gravar_noite(pasta, secao)


def test_deck_do_setor_sai_em_pptx_com_fonte_e_data(setor):
    cliente, _org, chave = setor
    resposta = _get(cliente, chave, DECK_DO_SETOR)
    assert resposta.status_code == 200
    assert resposta.headers["content-type"] == PPTX
    assert resposta.headers["content-disposition"] == (
        'attachment; filename="tickerlab-setor-eletricas.pptx"'
    )
    assert resposta.headers["cache-control"] == "no-store"
    texto = _textos(resposta.content)
    assert "Elétricas" in texto
    assert "17/10/2026" in texto  # o dia da noite (o `known_at` da resposta)
    assert "CPFL ENERGIA S.A." in texto and "OUTRA ENERGIA S.A." in texto
    assert "11,0%" in texto  # a participação da CPFL, como a tela escreve
    assert "HHI (pontos)" in texto and "4.626" in texto
    assert "Fonte: aneel-samp · público em 17/10/2026" in texto
    assert "ANEEL" in texto and "CVM" in texto  # as atribuições das fontes
    assert apresentacao.TITULO_DOS_LIMITES in texto
    assert apresentacao.AVISO_DO_DECK in texto


def test_deck_do_setor_tem_so_o_que_o_portao_libera(setor, monkeypatch):
    # sem a prontidão da tabela da ANEEL, a série some do deck como some do JSON
    cliente, _org, chave = setor
    sem_a_aneel = ("empresa_serie", "cadastro_das_companhias")
    monkeypatch.setattr(rotas, "regras_da_api", lambda: do_setor._regras(sem_a_aneel))
    resposta = _get(cliente, chave, DECK_DO_SETOR)
    assert resposta.status_code == 200
    texto = _textos(resposta.content)
    assert "HHI (pontos)" not in texto and "aneel-samp" not in texto
    assert "CPFL ENERGIA S.A." in texto  # os membros, da CVM, continuam
    # e o deck diz, como o JSON, que a série não foi consultada (linha 882)
    assert "unavailable_series" in texto


def test_deck_do_setor_sem_pessoa_fisica(setor, noite):
    def plantar(secao: dict) -> None:
        pessoa = {"cnpj": "12345678909", "empresa": "FULANO", "motivo": "ligada"}
        secao["tabelas"]["membros"].append(pessoa)
        linha = dict(secao["tabelas"]["participacao_dos_membros"][0])
        secao["tabelas"]["participacao_dos_membros"].append(
            linha | {"cnpj": "12345678909", "empresa": "FULANO"}
        )

    _regravar(noite, plantar)
    cliente, _org, chave = setor
    texto = _textos(_get(cliente, chave, DECK_DO_SETOR).content)
    assert "FULANO" not in texto
    assert "123.456.789-09" not in texto and "12345678909" not in texto


def test_texto_do_dado_com_caractere_de_controle_nao_quebra_o_arquivo(setor, noite):
    def sujar(secao: dict) -> None:
        secao["tabelas"]["membros"][0]["empresa"] = "CPFL\x00 ENERGIA\x0b S.A.\x1f"
        secao["paragrafos"] = [*secao.get("paragrafos", []), "aviso\x07 com sino"]

    _regravar(noite, sujar)
    cliente, _org, chave = setor
    resposta = _get(cliente, chave, DECK_DO_SETOR)
    assert resposta.status_code == 200
    texto = _textos(resposta.content)
    assert "CPFL ENERGIA S.A." in texto
    assert "aviso com sino" in texto


def test_tabela_longa_e_cortada_no_deck_e_o_arquivo_fica_pequeno(
    setor, noite, monkeypatch
):
    def inflar(secao: dict) -> None:
        secao["tabelas"]["membros"] += [
            {
                "cnpj": f"{i:08d}000191",
                "empresa": f"COMPANHIA {i} S.A.",
                "motivo": "x" * 200,
            }
            for i in range(1, 900)
        ]

    _regravar(noite, inflar)
    monkeypatch.setattr(acesso, "linhas_por_resposta", lambda contexto: 1000)
    cliente, _org, chave = setor
    resposta = _get(cliente, chave, DECK_DO_SETOR)
    assert resposta.status_code == 200
    assert len(resposta.content) < UM_MEGA
    assert _slides(resposta.content) <= deck.SLIDES_NO_MAXIMO
    texto = _textos(resposta.content)
    assert f"{deck.LINHAS_POR_TABELA} de 901 linhas" in texto
    assert "/data/v1/sectors/eletricas" in texto  # onde a tabela inteira sai


def test_deck_cortado_pelo_plano_avisa(setor, monkeypatch):
    monkeypatch.setattr(acesso, "linhas_por_resposta", lambda contexto: 3)
    cliente, _org, chave = setor
    texto = _textos(_get(cliente, chave, DECK_DO_SETOR).content)
    assert deck.AVISO_DO_CORTE in texto


def test_duas_organizacoes_cada_uma_com_o_seu_contrato(banco, monkeypatch, noite):
    com, chave_com = _organizacao_com(banco, setores.CONJUNTO, "Alfa Gestora")
    sem, chave_sem = _organizacao_com(banco, "funds", "Beta Capital")
    cliente = aj.cliente_da_api(monkeypatch, AGORA)
    negado = _get(cliente, chave_sem, DECK_DO_SETOR)
    assert negado.status_code == 404
    assert negado.json() == {"detail": rotas.NAO_DISPONIVEL}
    assert _get(cliente, chave_com, DECK_DO_SETOR).status_code == 200
    # cada pedido conta só na organização da chave
    assert (_consumo(banco, com).pedidos, _consumo(banco, com).negados) == (1, 0)
    assert (_consumo(banco, sem).pedidos, _consumo(banco, sem).negados) == (0, 1)


def test_deck_do_setor_conta_como_o_json(setor, banco):
    cliente, org, chave = setor
    _get(cliente, chave, DECK_DO_SETOR)
    _get(cliente, chave, do_setor.ROTA)
    consumo = _consumo(banco, org)
    assert consumo.pedidos == 2 and consumo.negados == 0
    assert consumo.linhas % 2 == 0  # as mesmas linhas nas duas formas


@pytest.mark.parametrize(
    ("rota", "parametros", "status", "detalhe"),
    [
        (DECK_DO_SETOR, {"known_at": "2026-11-11"}, 400, "invalid_known_at"),
        (DECK_DO_SETOR, {"known_at": "2026-10-16"}, 404, "not_available"),
        ("/data/v1/sectors/nao_existe/deck", {}, 404, "not_available"),
        ("/data/v1/sectors/ELETRICAS/deck", {}, 404, "not_available"),
    ],
)
def test_erros_do_deck_do_setor(setor, rota, parametros, status, detalhe):
    cliente, _org, chave = setor
    resposta = _get(cliente, chave, rota, **parametros)
    assert resposta.status_code == status
    assert resposta.json() == {"detail": detalhe}
    assert "content-disposition" not in resposta.headers


def test_deck_do_setor_sem_chave_da_401(setor):
    cliente, _org, _chave = setor
    assert cliente.get(DECK_DO_SETOR).status_code == 401


# ---------------------------------------------------------------- o deck da empresa


def _base_do_perfil(tmp_path, monkeypatch) -> None:
    """A base de mentira do perfil (a de `test_api_externa_por_cnpj_perfil.py`) e as regras dele."""
    base = ficha_de_mentira._base(tmp_path, ficha_de_mentira._rotulos())
    monkeypatch.setattr(rotas, "abrir_porta", lambda banco_: Porta(base, banco_))
    monkeypatch.setattr(rotas, "regras_da_api", perfil._regras)


@pytest.fixture
def empresa(banco, monkeypatch, tmp_path):
    _base_do_perfil(tmp_path, monkeypatch)
    org, chave = _organizacao_com(banco, ficha.CONJUNTO, "Alfa Gestora")
    return aj.cliente_da_api(monkeypatch, AGORA), org, chave


def test_deck_da_empresa_sai_em_pptx_com_fonte_e_data(empresa):
    cliente, _org, chave = empresa
    resposta = _get(cliente, chave, DECK_DA_EMPRESA)
    assert resposta.status_code == 200
    assert resposta.headers["content-type"] == PPTX
    assert resposta.headers["content-disposition"] == (
        f'attachment; filename="tickerlab-empresa-{EMPRESA}.pptx"'
    )
    assert resposta.headers["cache-control"] == "no-store"
    texto = _textos(resposta.content)
    assert "11.111.111/0001-91" in texto
    assert "10/11/2026" in texto  # como era em (sem `known_at`, hoje)
    assert "Baixada" in texto  # a situação 08, escrita
    assert "DFP" in texto and "ITR" in texto
    assert "No prazo" in texto and "Zona cinzenta" in texto
    assert "Fonte: rfb-cnpj" in texto and "Fonte: cvm-hist-dfp" in texto
    assert "Receita" in texto and "CVM" in texto  # as atribuições
    assert ficha.LIMITES[1] in texto
    assert apresentacao.AVISO_DO_DECK in texto


def test_deck_da_empresa_no_passado_nao_mostra_o_que_veio_depois(empresa):
    cliente, _org, chave = empresa
    texto = _textos(
        _get(cliente, chave, DECK_DA_EMPRESA, known_at="2025-06-30").content
    )
    assert "30/06/2025" in texto
    assert "11/08/2025" not in texto  # a DFP de 2024 só veio em 11/08/2025
    assert "Não entregue" in texto


@pytest.mark.parametrize(
    "cnpj", [empresas_de_mentira.MEI, empresas_de_mentira.EMPRESARIO_INDIVIDUAL]
)
def test_pessoa_no_deck_da_o_mesmo_404_de_quem_nao_existe(
    tmp_path, empresa, monkeypatch, cnpj
):
    base = ficha_de_mentira._base(
        tmp_path / "com_pessoa", ficha_de_mentira._rotulos(cnpj=cnpj)
    )
    monkeypatch.setattr(rotas, "abrir_porta", lambda banco_: Porta(base, banco_))
    cliente, _org, chave = empresa
    inexistente = _get(
        cliente, chave, f"/data/v1/companies/{empresas_de_mentira.INEXISTENTE}/deck"
    )
    resposta = _get(cliente, chave, f"/data/v1/companies/{cnpj}/deck")
    assert resposta.status_code == inexistente.status_code == 404
    assert resposta.json() == inexistente.json() == {"detail": "not_available"}


def test_contrato_de_companies_nao_abre_o_deck_da_empresa(banco, monkeypatch, tmp_path):
    _base_do_perfil(tmp_path, monkeypatch)
    com, chave_com = _organizacao_com(banco, ficha.CONJUNTO, "Alfa Gestora")
    sem, chave_sem = _organizacao_com(banco, empresas.CONJUNTO, "Beta Capital")
    cliente = aj.cliente_da_api(monkeypatch, AGORA)
    assert _get(cliente, chave_sem, DECK_DA_EMPRESA).json() == {
        "detail": "not_available"
    }
    assert _get(cliente, chave_com, DECK_DA_EMPRESA).status_code == 200
    assert (_consumo(banco, com).pedidos, _consumo(banco, sem).negados) == (1, 1)


def test_deck_da_empresa_conta_um_pedido(empresa, banco):
    cliente, org, chave = empresa
    _get(cliente, chave, DECK_DA_EMPRESA)
    consumo = _consumo(banco, org)
    assert (consumo.pedidos, consumo.linhas, consumo.negados) == (
        1,
        1 + len(ficha_de_mentira.ENTREGAS),
        0,
    )


@pytest.mark.parametrize(
    ("rota", "parametros", "status", "detalhe"),
    [
        (DECK_DA_EMPRESA, {"known_at": "2026-11-11"}, 400, "invalid_known_at"),
        ("/data/v1/companies/123/deck", {}, 400, "invalid_cnpj"),
    ],
)
def test_erros_do_deck_da_empresa(empresa, rota, parametros, status, detalhe):
    cliente, _org, chave = empresa
    resposta = _get(cliente, chave, rota, **parametros)
    assert resposta.status_code == status
    assert resposta.json() == {"detail": detalhe}


def test_deck_da_empresa_sem_chave_da_401(empresa):
    cliente, _org, _chave = empresa
    assert cliente.get(DECK_DA_EMPRESA).status_code == 401


# ---------------------------------------------------------------- o contrato publicado


def test_o_contrato_publicado_tem_os_dois_decks_como_arquivo():
    caminhos = openapi_data_v1()["paths"]
    do_setor_ = caminhos["/data/v1/sectors/{key}/deck"]["get"]["responses"]
    da_empresa = caminhos["/data/v1/companies/{cnpj}/deck"]["get"]["responses"]
    for respostas in (do_setor_, da_empresa):
        assert PPTX in respostas["200"]["content"]
        assert {"400", "401", "404", "429"} <= set(respostas)
    assert "503" not in do_setor_  # lê a ficha da noite, não a base
    assert "503" in da_empresa


# ---------------------------------------------------------------- o tamanho do deck


def _envelope(valor: object) -> dict:
    return {
        "valor": valor,
        "fonte": "aneel-samp",
        "publico_em": "2026-10-17",
        "visto_em": None,
    }


def test_deck_com_series_demais_para_no_maximo_e_mantem_o_fechamento():
    linha = {"ano": _envelope(2025), "hhi": _envelope(1000.0)}
    serie = {
        "serie": "aneel_consumidores",
        "concentracao": [linha] * deck.LINHAS_POR_TABELA,
        "participacao_dos_membros": [],
    }
    corpo = {
        "setor": "eletricas",
        "nome": "Elétricas",
        "como_era_em": "2026-10-17",
        "por_serie": [serie] * 20,  # 20 séries de 5 slides cada: passaria de 100
        "membros": [],
        "avisos": [],
        "cortada": False,
    }
    feito = deck.do_setor(corpo, [], datetime(2026, 11, 10, 9, tzinfo=UTC))
    assert len(feito.slides) == deck.SLIDES_NO_MAXIMO
    titulos = [s.titulo for s in feito.slides]
    assert titulos[-3] == "O deck parou aqui"
    assert titulos[-2:] == [
        apresentacao.TITULO_DAS_FONTES,
        apresentacao.TITULO_DOS_LIMITES,
    ]
