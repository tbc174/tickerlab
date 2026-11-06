"""A busca por CNPJ com as empresas fechadas (PR 6 do plano da base de CNPJ com sócios, 20/10/2026).

A vista publicada (`scripts.montar_vista_do_cnpj`) leva da base de casa só o que a busca mostra: cadastro até o
município, Simples e MEI, o quadro de sócios sem o pseudônimo e as mudanças de 12 meses. O nome da pessoa
física só sairia por `base.pessoas.consulta.socios_da_empresa`, com o portão aberto (aqui, fechado).
"""

import json
import logging
from datetime import date

import pandas as pd
import pytest

from base import cnpj as cnpj_da_base
from base.pessoas import proibidas
from scripts import montar_vista_do_cnpj
from src import busca_por_cnpj as busca
from src.banco.coletas import FRASE_DA_RECEITA
from src.banco.usuarios import mudar_plano
from src.relatorio_do_cnpj_pdf import relatorio_do_cnpj
from tests import ajudantes_do_cnpj as exemplo
from tests import test_api_v1_rotas as rotas
from tests.test_busca_por_cnpj_pdf import _texto_do_pdf

chave = rotas.chave  # as fixtures da conta logada, as mesmas dos outros testes da API
cliente = rotas.cliente

HOJE = date(2026, 10, 24)
LIMITADA = exemplo.cnpj(exemplo.LIMITADA)
FILIAL = exemplo.cnpj(exemplo.LIMITADA, "0002")
MEI = exemplo.cnpj(exemplo.MEI)
SECOES_DA_FECHADA = [
    "cadastro_da_receita",
    "simples_e_mei",
    "socios_da_receita",
    "estabelecimentos",
    "mudancas_da_receita",
]


@pytest.fixture
def vista(tmp_path):
    base = exemplo.gravar_base(tmp_path / "base")
    destino = tmp_path / "vista"
    montar_vista_do_cnpj.montar(base, destino)
    # o restrito ao lado da vista, com o nome: mesmo à mão, o portão fechado não deixa sair
    exemplo.gravar_restrito(destino / "restrito")
    return destino


@pytest.fixture
def sem_fichas(tmp_path):
    pasta = tmp_path / "dossies"
    (pasta / "atual").mkdir(parents=True)
    return pasta


def _buscar(banco, sem_fichas, vista, texto=LIMITADA, plano="pro"):
    with banco.connect() as conexao:
        return busca.buscar_por_cnpj(conexao, texto, plano, HOJE, sem_fichas, vista)


def _tudo(relatorio) -> str:
    return json.dumps(relatorio.como_dict(), ensure_ascii=False)


def _secao(relatorio, chave):
    return next(s for s in relatorio.secoes if s.chave == chave)


def _itens(relatorio, chave="cadastro_da_receita"):
    return {i.chave: i for i in _secao(relatorio, chave).itens}


# --- o relatório da fechada --------------------------------------------------------------------------


def test_busca_mostra_fechada(banco, sem_fichas, vista) -> None:
    rel = _buscar(banco, sem_fichas, vista)
    assert rel.situacao == busca.CADASTRO_DA_RECEITA
    assert rel.cnpj == cnpj_da_base.formatar(LIMITADA)
    assert [s.chave for s in rel.secoes] == SECOES_DA_FECHADA
    itens = _itens(rel)
    assert itens["cnpj"].texto == cnpj_da_base.formatar(LIMITADA)
    assert itens["situacao"].texto == "Ativa, desde 01/02/2010"
    assert itens["inicio_atividade"].texto == "01/02/2010"
    assert itens["atividade"].texto == (
        "Desenvolvimento de programas de computador sob encomenda (CNAE 6201-5/01)"
    )
    assert itens["local"].texto == "SAO PAULO/SP"
    assert itens["estabelecimentos"].texto == "2 (1 ativo)"
    for item in itens.values():
        assert item.fonte == FRASE_DA_RECEITA
        assert item.base == "dados abertos do CNPJ de 09/2024"
    assert rel.como_era_em == date(2024, 9, 21)
    assert FRASE_DA_RECEITA in rel.fontes
    assert rel.empresa == "" and rel.tickers == []


def test_simples_estabelecimentos_e_mudancas(banco, sem_fichas, vista) -> None:
    rel = _buscar(banco, sem_fichas, vista)
    simples = _itens(rel, "simples_e_mei")
    assert simples["simples"].texto == "Optante desde 01/08/2024"
    assert simples["mei"].texto == "Não"
    estabelecimentos = _secao(rel, "estabelecimentos").tabelas["estabelecimentos"]
    assert estabelecimentos[1] == {
        "cnpj": cnpj_da_base.formatar(FILIAL),
        "tipo": "filial",
        "situacao": "Baixada, desde 02/09/2024",
        "inicio": "01/02/2010",
        "atividade": "Desenvolvimento de programas de computador sob encomenda",
        "local": "RIO DE JANEIRO/RJ",
    }
    mudancas = _secao(rel, "mudancas_da_receita").tabelas["mudancas_da_receita"]
    assert mudancas == [
        {
            "mes": "09/2024",
            "onde": f"estabelecimento {cnpj_da_base.formatar(FILIAL)}",
            "mudanca": "situação: Ativa → Baixada",
        },
        {
            "mes": "08/2024",
            "onde": "Simples e MEI",
            "mudanca": "passou a optar pelo Simples",
        },
        {
            "mes": "08/2024",
            "onde": "sócios",
            "mudanca": "entrou: pessoa jurídica 33.000.167, sócio",
        },
    ]


def test_socio_pf_sem_nome_com_portao_fechado(banco, sem_fichas, vista) -> None:
    rel = _buscar(banco, sem_fichas, vista)
    socios = _secao(rel, "socios_da_receita").tabelas["socios_da_receita"]
    assert socios == [
        {
            "socio": "sócio pessoa física",
            "qualificacao": "administrador",
            "desde": "03/2019",
        },
        {
            "socio": "pessoa jurídica 33.000.167",
            "qualificacao": "sócio",
            "desde": "08/2024",
        },
    ]
    tudo = _tudo(rel)
    assert exemplo.NOME_DO_SOCIO not in tudo and exemplo.ID_DO_SOCIO not in tudo
    # o pseudônimo não sai de casa: a vista guarda o quadro com o id vazio
    qsa = pd.read_parquet(vista / "vigente" / "qsa")
    assert set(qsa["id_pessoa"]) == {""}
    assert "id_pessoa" not in pd.read_parquet(vista / "mudancas" / "qsa").columns


def test_sem_contatos_na_busca(banco, sem_fichas, vista) -> None:
    arquivos = [a for a in vista.rglob("*.parquet") if "restrito" not in a.parts]
    assert arquivos
    for arquivo in arquivos:
        tabela = pd.read_parquet(arquivo)
        assert proibidas.procurar(tabela, arquivo.name) == []
        finos = {"logradouro", "numero", "complemento", "bairro", "cep"}
        assert not finos & {
            c.removesuffix("_antes").removesuffix("_depois") for c in tabela
        }
    for texto in (LIMITADA, MEI):
        tudo = _tudo(_buscar(banco, sem_fichas, vista, texto))
        for contato in (
            exemplo.TELEFONE_DO_MEI,
            exemplo.EMAIL_DO_MEI,
            exemplo.RUA_DO_MEI,
            exemplo.CEP_DO_MEI,
            "DAS EMPRESAS",
            "CENTRO",
        ):
            assert contato not in tudo


def test_mei_so_municipio(banco, sem_fichas, vista) -> None:
    rel = _buscar(banco, sem_fichas, vista, MEI)
    itens = _itens(rel)
    assert itens["local"].texto == "SAO PAULO/SP"
    assert _itens(rel, "simples_e_mei")["mei"].texto == "Sim, desde 12/03/2019"
    # nenhum sinal negativo de MEI nas seções: nem a situação especial nem o motivo da situação
    tudo = json.dumps(rel.como_dict()["secoes"], ensure_ascii=False).upper()
    assert "RECUPERACAO" not in tudo and "RECUPERAÇÃO" not in tudo
    assert "OMISS" not in tudo
    assert not {"situacao_especial", "motivo"} & set(itens)


def test_filial_da_fechada_mostra_o_estabelecimento_pedido(
    banco, sem_fichas, vista
) -> None:
    rel = _buscar(banco, sem_fichas, vista, FILIAL)
    assert rel.situacao == busca.CADASTRO_DA_RECEITA
    assert rel.cnpj == cnpj_da_base.formatar(FILIAL)
    itens = _itens(rel)
    assert itens["situacao"].texto == "Baixada, desde 02/09/2024"
    assert itens["local"].texto == "RIO DE JANEIRO/RJ"


def test_desconhecido_e_sem_vista_continuam_fora(
    banco, sem_fichas, vista, tmp_path
) -> None:
    desconhecido = exemplo.cnpj("11222333")
    sem_estabelecimento = exemplo.cnpj(exemplo.LIMITADA, "0003")
    for texto in (desconhecido, sem_estabelecimento):
        assert _buscar(banco, sem_fichas, vista, texto).situacao == busca.FORA
    # antes de a vista chegar ao servidor, a busca segue como antes
    assert _buscar(banco, sem_fichas, tmp_path / "nao_existe").situacao == busca.FORA


def test_sem_o_plano_a_fechada_vem_trancada(banco, sem_fichas, vista) -> None:
    rel = _buscar(banco, sem_fichas, vista, plano="gratuito")
    assert [s.chave for s in rel.secoes] == SECOES_DA_FECHADA
    assert not _secao(rel, "cadastro_da_receita").trancada
    trancadas = [s for s in rel.secoes if s.trancada]
    assert len(trancadas) == len(SECOES_DA_FECHADA) - 1
    assert all(not s.itens and not s.tabelas and s.paragrafos for s in trancadas)
    assert "administrador" not in json.dumps(rel.como_dict()["secoes"])


def test_desligado_sem_as_linhas_das_fechadas(banco, sem_fichas, vista) -> None:
    for texto in (LIMITADA, exemplo.cnpj("11222333")):
        desligado = _buscar(banco, sem_fichas, vista, texto).desligado
        assert not any(linha.startswith("Empresas fechadas") for linha in desligado)
        assert not any(
            linha.startswith("Natureza jurídica e MEI") for linha in desligado
        )
        # o memorando de M&A procura esta linha pela palavra (src/memorando_ma/montagem.py)
        assert any("Dívida com a União" in linha for linha in desligado)


def test_cnpj_da_fechada_nao_vai_para_o_log(banco, sem_fichas, vista, caplog) -> None:
    with caplog.at_level(logging.DEBUG):
        _buscar(banco, sem_fichas, vista, MEI)
        _buscar(banco, sem_fichas, vista, LIMITADA)
    todo = " ".join(r.getMessage() for r in caplog.records)
    for raiz in (exemplo.MEI, exemplo.LIMITADA, "98.765.432", "12.345.678"):
        assert raiz not in todo


# --- a vista publicada -------------------------------------------------------------------------------


def test_vista_so_com_as_mudancas_dos_ultimos_12_meses(vista) -> None:
    manifesto = json.loads((vista / "manifesto.json").read_text(encoding="utf-8"))
    assert manifesto["mes"] == "2024-09"
    assert manifesto["meses_das_mudancas"] == ["2023-10", "2024-08", "2024-09"]
    meses = set(pd.read_parquet(vista / "mudancas" / "qsa")["mes"])
    assert meses == {"2024-08"}  # 2023-09 ficou fora; 2024-09 só trocou o pseudônimo


def test_vista_ordenada_pela_raiz_para_a_leitura_filtrada(vista) -> None:
    for tabela in ("estabelecimentos", "simples", "qsa"):
        for arquivo in (vista / "vigente" / tabela).glob("*.parquet"):
            raizes = list(pd.read_parquet(arquivo)["cnpj_basico"])
            assert raizes == sorted(raizes)


# --- o PDF e a rota ----------------------------------------------------------------------------------


def test_pdf_da_fechada(banco, sem_fichas, vista) -> None:
    texto = _texto_do_pdf(relatorio_do_cnpj(_buscar(banco, sem_fichas, vista)))
    assert f"Relatório do CNPJ {cnpj_da_base.formatar(LIMITADA)}" in texto
    assert "Cadastro da Receita de 09/2024" in texto
    assert "sócio pessoa física" in texto and "Limites e cuidados" in texto
    assert FRASE_DA_RECEITA in texto
    assert exemplo.NOME_DO_SOCIO not in texto


@pytest.fixture
def vista_no_servidor(vista, sem_fichas, monkeypatch):
    monkeypatch.setenv("TICKERLAB_CNPJ", str(vista))
    monkeypatch.setenv("TICKERLAB_DOSSIES", str(sem_fichas))
    return vista


def test_rota_da_fechada(cliente, banco, vista_no_servidor, caplog) -> None:
    with banco.begin() as conexao:
        mudar_plano(conexao, rotas._id_da_ana_no(banco), "pro")
    with caplog.at_level(logging.DEBUG):
        resposta = cliente.post("/api/v1/busca-por-cnpj", json={"cnpj": MEI})
        pdf = cliente.post("/api/v1/busca-por-cnpj/pdf", json={"cnpj": LIMITADA})
    assert resposta.status_code == 200, resposta.text
    dados = resposta.json()
    assert dados["situacao"] == "cadastro_da_receita"
    assert [s["chave"] for s in dados["secoes"]] == SECOES_DA_FECHADA
    assert all(not s["trancada"] for s in dados["secoes"])
    for contato in (exemplo.TELEFONE_DO_MEI, exemplo.EMAIL_DO_MEI, exemplo.RUA_DO_MEI):
        assert contato not in resposta.text
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    todo = " ".join(r.getMessage() for r in caplog.records)
    assert exemplo.MEI not in todo and exemplo.LIMITADA not in todo
    assert "busca por cnpj: cadastro_da_receita" in todo


# --- as frases das mudanças -------------------------------------------------------------------------


def _linha(**campos):
    return next(pd.DataFrame([campos]).itertuples())


def test_mudancas_de_socio_nunca_dizem_o_nome() -> None:
    from src import relatorio_da_receita as receita

    pf = {"tipo_socio": "2", "raiz_socio_pj": ""}
    saiu = _linha(tipo="saiu", qualificacao_antes="05", **pf)
    assert (
        receita._mudancas_de_socio(saiu) == "saiu: sócio pessoa física, administrador"
    )
    mudou = _linha(
        tipo="mudou",
        qualificacao_antes="22",
        qualificacao_depois="05",
        data_entrada_antes=pd.Timestamp("2019-03-15"),
        data_entrada_depois=pd.Timestamp("2020-01-10"),
        **pf,
    )
    assert receita._mudancas_de_socio(mudou) == (
        "sócio pessoa física: qualificação sócio → administrador; "
        "sócio pessoa física: entrada 03/2019 → 01/2020"
    )
    assert receita._quem("3", "", "105") == "sócio estrangeiro (BRASIL)"


def test_mudancas_de_estabelecimento_e_do_simples() -> None:
    from src import relatorio_da_receita as receita

    comum = {
        "situacao_cadastral_antes": "02",
        "situacao_cadastral_depois": "02",
        "uf_antes": "SP",
        "uf_depois": "RJ",
        "municipio_antes": "7107",
        "municipio_depois": "6001",
    }
    mudou = _linha(
        tipo="mudou",
        cnae_principal_antes="6201501",
        cnae_principal_depois="9602501",
        **comum,
    )
    texto = receita._mudancas_de_estabelecimento(mudou)
    assert texto.startswith("atividade: Desenvolvimento de programas")
    assert texto.endswith("município: SAO PAULO/SP → RIO DE JANEIRO/RJ")
    assert (
        receita._mudancas_de_estabelecimento(_linha(tipo="entrou"))
        == "entrou no cadastro"
    )
    assert (
        receita._mudancas_do_simples(_linha(tipo="saiu"))
        == "saiu do registro do Simples"
    )
    deixou = _linha(
        tipo="mudou",
        optante_simples_antes=True,
        optante_simples_depois=True,
        optante_mei_antes=True,
        optante_mei_depois=False,
    )
    assert receita._mudancas_do_simples(deixou) == "deixou de ser MEI"
