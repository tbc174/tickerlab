"""A busca por CNPJ (molde B, PR 2): o pedido, a filial, o cadastro, o relatório e o que fica de fora."""

import json
import logging
from datetime import date
from pathlib import Path

import pytest

from base import cnpj as cnpj_da_base
from base import dossie as dossie_da_base
from src import busca_por_cnpj as busca
from src import dossie
from src.banco import demonstracoes as repo

PETROBRAS = "33000167000101"
HOJE = date(2026, 10, 19)
SECAO_DA_REDE = {
    "chave": "rede",
    "titulo": "Ligações na rede",
    "itens": [
        {
            "chave": "ligacoes",
            "nome": "Ligações na rede",
            "valor": 1,
            "unidade": "empresas",
        }
    ],
    "tabelas": {
        "ligacoes_da_rede": [
            {
                "relacao": "Controlada",
                "entidade": "CPFL Paulista",
                "cnpj": "33.050.196/0001-88",
                "participacao": 100.0,
                "desde": "2015-01-01",
                "documento": "Formulário de Referência (CVM)",
            }
        ]
    },
    "paragrafos": [],
    "fontes": ["ODbL (dados abertos da CVM; citar a fonte)"],
}


def _filial(matriz: str, numero: str = "0002") -> str:
    base = matriz[:8] + numero
    return base + cnpj_da_base.digitos_verificadores(base)


def _gravar_ficha(pasta: Path, cnpj: str = PETROBRAS) -> Path:
    bruta = json.loads(dossie.FICHA_DE_EXEMPLO.read_text(encoding="utf-8"))
    bruta["secoes"].append(SECAO_DA_REDE)
    atual = pasta / "atual"
    atual.mkdir(exist_ok=True)
    (atual / f"{cnpj}.json").write_text(
        json.dumps(bruta | {"cnpj": cnpj}), encoding="utf-8"
    )
    return pasta


@pytest.fixture
def com_a_petrobras(banco, tmp_path):
    from tests.test_fundamentos_no_app import _coletar

    _coletar(banco)
    return _gravar_ficha(tmp_path)


# --- o pedido ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "texto",
    [PETROBRAS, "33.000.167/0001-01", " 33000167 0001 01 ", "33.000.167/0001-01\n"],
)
def test_cnpj_com_e_sem_pontuacao(texto) -> None:
    assert busca.normalizar_pedido(texto) == PETROBRAS


def test_cnpj_com_letras() -> None:
    assert busca.normalizar_pedido("12.abc.345/01de-35") == "12ABC34501DE35"


@pytest.mark.parametrize(
    "texto",
    ["", "abc", "33000167000102", "3300016700010", "00000000000000", "33.000.167"],
)
def test_cnpj_com_digito_errado_ou_incompleto(texto) -> None:
    with pytest.raises(busca.PedidoInvalidoError):
        busca.normalizar_pedido(texto)


# --- a filial acha a matriz -------------------------------------------------------------------------


def test_filial_mostra_a_matriz(tmp_path) -> None:
    pasta = _gravar_ficha(tmp_path)
    filial = _filial(PETROBRAS)
    assert cnpj_da_base.dv_confere(filial)
    ficha, aviso = busca.ficha_pela_raiz(filial, pasta)
    assert ficha is not None and ficha.cnpj == PETROBRAS
    assert aviso is not None and "filial" in aviso and "33.000.167/0001-01" in aviso


def test_matriz_nao_traz_aviso(tmp_path) -> None:
    ficha, aviso = busca.ficha_pela_raiz(PETROBRAS, _gravar_ficha(tmp_path))
    assert ficha is not None and aviso is None


def test_sem_ficha_nem_da_matriz(tmp_path) -> None:
    (tmp_path / "atual").mkdir()
    assert busca.ficha_pela_raiz(_filial(PETROBRAS), tmp_path) == (None, None)


# --- o cadastro -------------------------------------------------------------------------------------


def test_secao_cadastro_da_cvm(banco, com_a_petrobras) -> None:
    with banco.connect() as conexao:
        secao = busca.secao_cadastro(conexao, PETROBRAS)
    assert secao is not None and secao.chave == "cadastro"
    itens = {i.chave: i for i in secao.itens}
    assert "PETR4" in itens["tickers"].texto
    assert itens["razao_social"].texto and itens["setor"].texto
    assert itens["cnpj"].texto == "33.000.167/0001-01"
    assert all(i.fonte and i.base for i in secao.itens)


def test_secao_cadastro_sem_natureza_da_receita(banco, com_a_petrobras) -> None:
    with banco.connect() as conexao:
        secao = busca.secao_cadastro(conexao, PETROBRAS)
    assert secao is not None
    texto = json.dumps(
        [(i.nome, i.texto) for i in secao.itens] + secao.paragrafos,
        ensure_ascii=False,
    ).lower()
    for proibido in ("natureza", "mei", "receita federal", "situação cadastral"):
        assert proibido not in texto


def test_secao_cadastro_de_cnpj_sem_cadastro(banco) -> None:
    with banco.connect() as conexao:
        assert busca.secao_cadastro(conexao, PETROBRAS) is None


# --- o relatório ------------------------------------------------------------------------------------


def _relatorio(banco, pasta, plano="pro", texto=PETROBRAS):
    with banco.connect() as conexao:
        return busca.buscar_por_cnpj(conexao, texto, plano, HOJE, pasta)


def test_relatorio_do_cnpj_ordem_das_secoes(banco, com_a_petrobras) -> None:
    rel = _relatorio(banco, com_a_petrobras)
    assert rel.situacao == "encontrada"
    chaves = [s.chave for s in rel.secoes]
    assert chaves[:3] == ["cadastro", "auditor_e_controladas", "rede"]
    assert not set(chaves) & dossie_da_base.SECOES_DO_MOLDE_D
    assert rel.como_era_em == date(2026, 10, 17)
    assert rel.empresa and "PETR4" in rel.tickers
    assert any("ODbL" in f for f in rel.fontes)


def test_sem_o_plano_vem_trancado(banco, com_a_petrobras) -> None:
    rel = _relatorio(banco, com_a_petrobras, plano="gratuito")
    por_chave = {s.chave: s for s in rel.secoes}
    assert not por_chave["cadastro"].trancada
    trancadas = [s for s in rel.secoes if s.trancada]
    assert {"auditor_e_controladas", "rede"} <= {s.chave for s in trancadas}
    assert all(not s.itens and not s.tabelas and s.paragrafos for s in trancadas)
    assert "CPFL Paulista" not in json.dumps(rel.como_dict(), ensure_ascii=False)


def test_limites_e_desligado_sempre_presentes(banco, com_a_petrobras) -> None:
    for plano in ("pro", "gratuito"):
        rel = _relatorio(banco, com_a_petrobras, plano=plano)
        assert rel.limites and rel.desligado
        assert any("recomendação" in item for item in rel.limites)
    fora = _relatorio(banco, com_a_petrobras, texto="12.ABC.345/01DE-35")
    assert fora.limites and fora.desligado


def test_filial_traz_o_relatorio_da_matriz_com_o_aviso(banco, com_a_petrobras) -> None:
    rel = _relatorio(banco, com_a_petrobras, texto=_filial(PETROBRAS))
    assert rel.situacao == "encontrada" and rel.cnpj == "33.000.167/0001-01"
    assert rel.avisos and "filial" in rel.avisos[0]


def test_fechada_e_desconhecido_dao_a_mesma_resposta(banco, com_a_petrobras) -> None:
    """Quem a base conhece (tem cadastro) mas sem ficha responde igual a quem ela não conhece."""
    conhecida_sem_ficha = "00000000000191"
    with banco.begin() as conexao:
        repo.gravar_setor(conexao, "00.000.000/0001-91", "Bancos")
    desconhecida = "11222333000181"
    assert cnpj_da_base.dv_confere(conhecida_sem_ficha)
    assert cnpj_da_base.dv_confere(desconhecida)
    a = _relatorio(banco, com_a_petrobras, texto=conhecida_sem_ficha).como_dict()
    b = _relatorio(banco, com_a_petrobras, texto=desconhecida).como_dict()
    assert a.pop("cnpj") != b.pop("cnpj")
    assert a == b
    assert a["situacao"] == "fora_da_base_aberta"
    assert a["secoes"] == [] and a["empresa"] == "" and a["tickers"] == []
    assert busca.FORA_DA_BASE_ABERTA in a["avisos"]


def test_cnpj_pedido_nao_vai_para_o_log(banco, com_a_petrobras, caplog) -> None:
    with caplog.at_level(logging.DEBUG):
        _relatorio(banco, com_a_petrobras)
        _relatorio(banco, com_a_petrobras, texto="11.222.333/0001-81")
    todo = " ".join(r.getMessage() for r in caplog.records)
    for cnpj in (PETROBRAS, "33.000.167", "11222333", "11.222.333"):
        assert cnpj not in todo
