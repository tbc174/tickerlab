"""As novidades da pesquisa na API externa (linha 830): `GET /data/v1/research/news`.

Arquivo `novidades.json` de mentira em `tmp_path`; nomes e CPF inventados. A leitura repete as regras do
exportador item a item, porque o arquivo chega por um passo à parte.
"""

import json
from datetime import UTC, datetime

import pytest

from src.api_externa.conjuntos import novidades
from tests import ajudantes_da_api_externa as aj

AGORA = datetime(2026, 11, 11, 12, tzinfo=UTC)
ROTA = "/data/v1/research/news"
HASH = "a" * 64


def _item(**outros) -> dict:
    base = {
        "orgao": "CVM",
        "fonte": "cvm",
        "fonte_url": "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/exemplo.csv",
        "data": "2026-11-10",
        "afirmacao": "Parque Exemplo (CNPJ 11.222.333/0001-81): 120 MW",
        "trecho": "Parque Exemplo Eólico: 120 MW, vigência 2035, CNPJ 11.222.333/0001-81",
        "sha256": HASH,
        "posicao": "linha 3",
    }
    return base | outros


def _publicar(tmp_path, monkeypatch, itens, gerado_em="2026-11-11T09:00:00+00:00"):
    arquivo = tmp_path / "novidades.json"
    arquivo.write_text(
        json.dumps({"versao": 1, "gerado_em": gerado_em, "itens": itens}),
        encoding="utf-8",
    )
    monkeypatch.setenv(novidades.VARIAVEL_DO_ARQUIVO, str(arquivo))


@pytest.fixture
def chave(banco):
    ator = aj.admin(banco)
    org = aj.organizacao(banco, ator)
    aj.contrato(banco, ator, org, conjunto=novidades.CONJUNTO)
    return aj.chave(banco, ator, org)


@pytest.fixture
def cliente(monkeypatch, chave):
    return aj.cliente_da_api(monkeypatch, AGORA)


def _get(cliente, chave, **parametros):
    return cliente.get(ROTA, params=parametros, headers=aj.bearer(chave.valor))


def test_item_provado_sai_com_orgao_data_trecho_hash_e_atribuicao(
    cliente, chave, tmp_path, monkeypatch
):
    _publicar(tmp_path, monkeypatch, [_item()])
    resposta = _get(cliente, chave)
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["generated_at"] == "2026-11-11T09:00:00+00:00"
    assert corpo["total_news"] == 1
    assert corpo["items"] == [
        {
            "agency": "CVM",
            "source": "cvm",
            "source_url": "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/exemplo.csv",
            "date": "2026-11-10",
            "excerpt": "Parque Exemplo Eólico: 120 MW, vigência 2035, CNPJ 11.222.333/0001-81",
            "excerpt_cut": "",
            "original_sha256": HASH,
            "location": "linha 3",
        }
    ]
    assert [f["source"] for f in corpo["sources"]] == ["cvm"]


def test_sem_arquivo_a_lista_vem_vazia_e_sem_data_de_geracao(
    cliente, chave, monkeypatch, tmp_path
):
    monkeypatch.setenv(novidades.VARIAVEL_DO_ARQUIVO, str(tmp_path / "nao-existe.json"))
    corpo = _get(cliente, chave).json()
    assert corpo["generated_at"] is None
    assert corpo["items"] == []
    assert corpo["total_news"] == 0


def test_arquivo_ilegivel_tambem_vem_vazio(cliente, chave, monkeypatch, tmp_path):
    arquivo = tmp_path / "novidades.json"
    arquivo.write_text("{não é json", encoding="utf-8")
    monkeypatch.setenv(novidades.VARIAVEL_DO_ARQUIVO, str(arquivo))
    assert _get(cliente, chave).json()["items"] == []


def test_janela_de_dias_corta_e_a_mais_nova_vem_primeiro(
    cliente, chave, tmp_path, monkeypatch
):
    antigo = _item(data="2026-10-20", sha256="b" * 64)
    novo = _item(data="2026-11-11", sha256="c" * 64)
    _publicar(tmp_path, monkeypatch, [_item(), antigo, novo])
    assert [i["date"] for i in _get(cliente, chave).json()["items"]] == [
        "2026-11-11",
        "2026-11-10",
    ]
    assert len(_get(cliente, chave, days=30).json()["items"]) == 3


@pytest.mark.parametrize("dias", [0, 31, -1])
def test_dias_fora_de_1_a_30_e_400(cliente, chave, dias):
    resposta = _get(cliente, chave, days=dias)
    assert resposta.status_code == 400
    assert "invalid_days" in resposta.text


def test_recorte_do_trecho_passa_adiante(cliente, chave, tmp_path, monkeypatch):
    _publicar(tmp_path, monkeypatch, [_item(recorte="ambos")])
    assert _get(cliente, chave).json()["items"][0]["excerpt_cut"] == "ambos"


@pytest.mark.parametrize(
    "ruim",
    [
        _item(fonte_url="https://blog.exemplo.com.br/x"),  # domínio fora da tabela
        _item(fonte_url="https://www.ibama.gov.br/x"),  # órgão fora da tabela
        _item(
            fonte_url="https://dadosabertos.ibama.gov.br/x"
        ),  # fonte só de uso interno
        _item(sha256="curto"),
        _item(sha256="A" * 64),
        _item(trecho=""),
        _item(trecho="x" * 400),
        _item(trecho="Sócio com CPF 888.000.001-27 entrou em 2025"),
        _item(trecho="Sócio 88800000127 entrou em 2025"),
        _item(trecho="O Sr. Fulano Inventado assinou o contrato em 2025"),
        _item(trecho="NOME FICTICIO | multa | 120.000,00"),  # sem CNPJ no trecho
        _item(
            afirmacao="Multa (CNPJ 11.222.333/0001-81)",
            trecho="NOME FICTICIO | multa | 120.000,00",
        ),  # CNPJ só na afirmação não basta
        _item(trecho="Empresa 11.222.333/0001-80 | multa"),  # CNPJ com DV errado
        _item(trecho="11.222.333/0001-81 | contato fulano@exemplo.invalid | 120"),
        _item(trecho="11.222.333/0001-81 | tel (11) 91234-5678 | 120"),
        _item(trecho="11.222.333/0001-81 | tel +55 11 3456 7890 | 120"),
        _item(afirmacao="fale com fulano@exemplo.invalid"),  # e-mail em qualquer texto
        _item(posicao="coluna do Sr. Fulano"),  # marca de pessoa na posição
        _item(afirmacao="CPF 888.000.001-27"),
        _item(
            fonte_url="https://dados.cvm.gov.br/dados/CIA_ABERTA/CAD/cad_cia_aberta.csv"
        ),
        _item(fonte_url="https://dados.cvm.gov.br/dados/FI/CAD/DADOS/cad_fi.csv"),
        _item(
            fonte_url="https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/../../CAD/x.csv"
        ),
        _item(fonte_url="https://[dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/x.csv"),
        _item(
            fonte_url="https://dadosabertos.tcu.gov.br/x"
        ),  # fonte com linha de pessoa
        _item(fonte_url="https://portaldatransparencia.gov.br/x"),
        _item(data="ontem"),
        _item(recorte="meio"),
        _item(recorte=["ambos"]),  # lista no JSON: item inválido, não erro 500
        _item(recorte={"a": 1}),
        _item(afirmacao=7),
        _item(trecho=7),
        "não é um item",
    ],
)
def test_item_que_falha_qualquer_regra_nao_sai(
    cliente, chave, tmp_path, monkeypatch, ruim
):
    _publicar(tmp_path, monkeypatch, [ruim, _item(sha256="d" * 64)])
    corpo = _get(cliente, chave).json()
    assert [i["original_sha256"] for i in corpo["items"]] == ["d" * 64]


def test_o_orgao_e_o_da_tabela_e_nao_o_que_o_arquivo_diz(
    cliente, chave, tmp_path, monkeypatch
):
    _publicar(tmp_path, monkeypatch, [_item(orgao="Órgão Inventado", fonte="outra")])
    (item,) = _get(cliente, chave).json()["items"]
    assert (item["agency"], item["source"]) == ("CVM", "cvm")


def test_o_limite_de_linhas_do_plano_corta(cliente, chave, tmp_path, monkeypatch):
    itens = [_item(sha256=f"{n:064x}") for n in range(5)]
    _publicar(tmp_path, monkeypatch, itens)
    monkeypatch.setattr(
        "src.api_externa.rotas.acesso.linhas_por_resposta", lambda _c: 2
    )
    assert len(_get(cliente, chave).json()["items"]) == 2


def test_sem_chave_e_401(cliente):
    assert cliente.get(ROTA).status_code in (400, 401)


def test_sem_contrato_do_conjunto_a_rota_nega(banco, cliente, tmp_path, monkeypatch):
    _publicar(tmp_path, monkeypatch, [_item()])
    ator = aj.admin(banco)
    org = aj.organizacao(banco, ator)
    aj.contrato(banco, ator, org, conjunto="companies")  # outro conjunto não vale
    sem_contrato = aj.chave(banco, ator, org)
    resposta = _get(cliente, sem_contrato)
    assert resposta.status_code == 404
    assert "trecho" not in resposta.text and "excerpt" not in resposta.text


def test_catalogo_lista_research_so_com_contrato(banco, cliente, chave):
    corpo = cliente.get("/data/v1/catalog", headers=aj.bearer(chave.valor)).json()
    assert "research" in {c["dataset"] for c in corpo["datasets"]}


def test_a_afirmacao_do_bot_nunca_sai(cliente, chave, tmp_path, monkeypatch):
    _publicar(tmp_path, monkeypatch, [_item(afirmacao="texto livre do modelo")])
    (item,) = _get(cliente, chave).json()["items"]
    assert "claim" not in item and "afirmacao" not in item
    assert "texto livre" not in json.dumps(item)
