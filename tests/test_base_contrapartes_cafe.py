"""Ficha pública das contrapartes do café (base/contrapartes/cafe.py, PR 12 do plano do café).

Regras da passagem: só CNPJ e nome da entidade, nada de pessoa física; todo fato com fonte (endereço
público) e data; palavras vedadas; recuperação judicial ou fechamento só com documento oficial ou
notícia de veículo identificado guardada pelo arquivista (enquanto não guardada, fica em "o que não
sabemos" com o link); o que não tem fonte vai para "o que não sabemos", nunca estimado.
"""

import re
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pytest

from base.arquivo import coleta, contrapartes, fontes
from base.arquivo.coleta import Alvo, ErroDeDescoberta, Resposta
from base.arquivo.destinos import DESTINOS
from base.contrapartes import cafe
from base.porta.duckdb import CONFERIDAS
from src.banco import coletas

AGORA = datetime(2026, 10, 19, 5, tzinfo=UTC)
CPF = re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b|\b\d{11}\b")
# cargo seguido de nome: ninguém da diretoria, conselho ou quadro de associados entra na ficha
CARGOS = re.compile(
    r"\b(presidente|diretor|diretora|diretoria|conselheir[oa]|s[óo]ci[oa]|propriet[áa]ri[oa]|"
    r"dono|dona|fundador|fundadora|ceo|superintendente|cooperad[oa])\b",
    re.IGNORECASE,
)
SITUACAO_ESPECIAL = pd.DataFrame(
    {
        "cnpj": ["03.936.815/0001-75", "03.936.815/0002-56"],
        "cnpj_basico": ["03936815", "03936815"],
        "matriz": [True, False],
        "situacao_especial": ["RECUPERACAO JUDICIAL", "RECUPERACAO JUDICIAL"],
        "rotulo": ["recuperacao_judicial", "recuperacao_judicial"],
        "data_situacao_especial": [date(2025, 3, 19), date(2025, 3, 19)],
        "mes_do_retrato": [date(2025, 4, 1), date(2025, 4, 1)],
        "disponivel_em": [date(2025, 4, 13), date(2025, 4, 13)],
    }
)
NOTICIA_DO_PEDIDO = (
    "https://www.bloomberglinea.com.br/agro/"
    "gigante-do-cafe-pede-recuperacao-judicial-com-r-21-bilhoes-em-dividas/"
)
GUARDADAS = frozenset({NOTICIA_DO_PEDIDO})
# o que "o que não sabemos" pode ter de algarismo: a data e o link da notícia ainda não guardada
DATA_OU_LINK = re.compile(r"https://\S+|\d{2}/\d{2}/\d{4}")
CRA = pd.DataFrame(
    {
        "competencia": pd.to_datetime(["2023-01-01", "2023-02-01", "2024-06-01"]),
        "codigo_certificado": ["CRA0001", "CRA0001", "CRA0002"],
        "CNPJ": ["20.770.566/0001-00"] * 3,
        "disponivel_em": pd.to_datetime(["2023-03-01", "2023-04-01", "2024-08-01"]),
    }
)


@pytest.fixture(scope="module")
def fatos() -> pd.DataFrame:
    return cafe.ler()


def _todas(fatos: pd.DataFrame) -> list[cafe.FichaDaContraparte]:
    return cafe.fichas(fatos, situacao_especial=SITUACAO_ESPECIAL, cra=CRA)


def _textos(fichas: list[cafe.FichaDaContraparte]) -> list[str]:
    textos = []
    for ficha in fichas:
        textos += [ficha.nome, *ficha.o_que_nao_sabemos]
        textos += [f.descricao for f in ficha.fatos]
    return textos


def test_tabela_conferida_tem_as_colunas_do_dicionario_e_esta_na_porta(fatos):
    assert list(fatos.columns) == list(cafe.COLUNAS)
    assert CONFERIDAS["contraparte_cafe"] == "base/conferidas/contrapartes_cafe.csv"
    assert set(fatos["tipo"]) <= set(cafe.TIPOS)
    assert set(fatos["tipo_de_fonte"]) <= set(cafe.TIPOS_DE_FONTE)


def test_ficha_tem_so_fatos_com_fonte_e_data(fatos):
    riscos = tuple(cafe.NOMES_DOS_FATOS_DE_RISCO.values())
    for ficha in _todas(fatos) + cafe.fichas(fatos, guardadas=GUARDADAS):
        assert ficha.fatos or ficha.o_que_nao_sabemos[0].startswith(riscos), ficha.id
        for fato in ficha.fatos:
            assert fato.fonte.startswith("https://"), (ficha.id, fato.fato)
            assert fato.veiculo, (ficha.id, fato.fato)
            assert isinstance(fato.data, date) and isinstance(fato.divulgado_em, date)
            assert fato.data <= fato.divulgado_em, (ficha.id, fato.fato)


@pytest.mark.parametrize("coluna", ["fonte", "data", "divulgado_em", "veiculo"])
def test_fato_sem_fonte_ou_data_nao_entra(fatos, coluna):
    quebrada = fatos.copy()
    quebrada.loc[0, coluna] = None
    with pytest.raises(ValueError, match=coluna):
        cafe.validar(quebrada)


def test_fonte_que_nao_e_endereco_publico_nao_entra(fatos):
    quebrada = fatos.copy()
    quebrada.loc[0, "fonte"] = "conversa com o setor"
    with pytest.raises(ValueError, match="fonte"):
        cafe.validar(quebrada)


def test_palavras_vedadas_nao_aparecem(fatos):
    textos = _textos(_todas(fatos)) + _textos(cafe.fichas(fatos))
    for texto in textos:
        assert not cafe.palavras_vedadas_em(texto), texto
    # e a régua pega o que deve pegar, sem acento nem caixa importarem
    assert cafe.palavras_vedadas_em("A empresa QUEBROU e é Nao Confiável") == [
        "quebrou",
        "não confiável",
        "confiável",
    ]
    assert cafe.palavras_vedadas_em("assegurar, inseguro") == []


def test_isolamento_nenhum_dado_pessoal(fatos):
    assert set(fatos.columns) == set(cafe.COLUNAS)  # nada de coluna de pessoa
    for texto in _textos(_todas(fatos)):
        assert not CPF.search(texto), texto
        assert not CARGOS.search(texto), texto
    for cnpj in fatos["cnpj"].dropna():
        assert cafe.cnpj_valido(cnpj), cnpj
    assert not cafe.cnpj_valido("123.456.789-09")


def test_fato_de_recuperacao_judicial_ou_fechamento_tem_documento_ou_noticia_guardada(
    fatos,
):
    risco = fatos[fatos["fato"].isin(cafe.FATOS_DE_RISCO)]
    assert len(risco) >= 3
    a_guardar = set(contrapartes.paginas_a_guardar(fatos))
    for _, linha in risco.iterrows():
        assert linha["tipo_de_fonte"] in {"documento_oficial", "noticia"}
        assert linha["fonte"] in a_guardar, linha["fonte"]  # a página vira prova
    # sem a página guardada, a notícia do pedido não vira fato: fica em "o que não sabemos"
    # (as sacas a receber, do Brazil Journal, não são fato de risco: entram sem cópia)
    sem_copia = cafe.montar_ficha("atlantica", fatos)
    assert sem_copia is not None
    assert [f.fato for f in sem_copia.fatos] == ["sacas_a_receber_a_termo"]
    pendente = sem_copia.o_que_nao_sabemos[0]
    assert pendente.startswith("Pedido de recuperação judicial: noticiado por")
    assert "Bloomberg Línea" in pendente and "05/03/2025" in pendente
    assert NOTICIA_DO_PEDIDO in pendente and "2,13" not in pendente
    # com a página guardada, entra
    com_copia = cafe.montar_ficha("atlantica", fatos, guardadas=GUARDADAS)
    assert com_copia is not None
    assert [f.fato for f in com_copia.fatos] == [
        "sacas_a_receber_a_termo",
        "pedido_de_recuperacao_judicial",
    ]
    assert not any(NOTICIA_DO_PEDIDO in t for t in com_copia.o_que_nao_sabemos)
    # documento oficial não precisa de cópia
    coocafeg = cafe.montar_ficha("coocafeg", fatos)
    assert coocafeg is not None
    assert [f.fato for f in coocafeg.fatos] == ["apuracao_publica"]


def test_corte_em_d_nao_mostra_o_que_ainda_nao_tinha_saido(fatos):
    nada = cafe.montar_ficha("atlantica", fatos, em=date(2024, 12, 2))
    assert nada is None  # a primeira notícia (Brazil Journal) saiu em 03/12/2024
    antes = cafe.montar_ficha("atlantica", fatos, em=date(2025, 3, 4))
    assert antes is not None  # a notícia do pedido saiu em 05/03/2025
    assert [f.fato for f in antes.fatos] == ["sacas_a_receber_a_termo"]
    depois = cafe.montar_ficha(
        "atlantica",
        fatos,
        em=date(2025, 3, 5),
        situacao_especial=SITUACAO_ESPECIAL,
        guardadas=GUARDADAS,
    )
    assert depois is not None
    assert [f.fato for f in depois.fatos] == [
        "sacas_a_receber_a_termo",
        "pedido_de_recuperacao_judicial",
    ]
    hoje = cafe.montar_ficha(
        "atlantica",
        fatos,
        em=date(2026, 10, 18),
        situacao_especial=SITUACAO_ESPECIAL,
        guardadas=GUARDADAS,
    )
    assert hoje is not None
    assert [f.fato for f in hoje.fatos] == [
        "sacas_a_receber_a_termo",
        "pedido_de_recuperacao_judicial",
        "situacao_especial_na_receita",
    ]
    # cortar o futuro não muda o passado
    assert hoje.fatos[:2] == depois.fatos[:2]


def test_situacao_especial_da_receita_vira_fato_oficial_so_da_matriz(fatos):
    ficha = cafe.montar_ficha("atlantica", fatos, situacao_especial=SITUACAO_ESPECIAL)
    assert ficha is not None
    receita = [f for f in ficha.fatos if f.fato == "situacao_especial_na_receita"]
    assert len(receita) == 1
    assert receita[0].tipo_de_fonte == "documento_oficial"
    assert receita[0].data == date(2025, 3, 19)
    assert receita[0].fonte.startswith("https://arquivos.receitafederal.gov.br/")


def test_cra_vira_fato_com_primeiro_e_ultimo_mes(fatos):
    ficha = cafe.montar_ficha("cooxupe", fatos, cra=CRA)
    assert ficha is not None
    cra = [f for f in ficha.fatos if f.fato == "cedente_ou_devedor_de_cra"]
    assert len(cra) == 1
    assert cra[0].valor == 2  # dois certificados
    assert "2023-01 a 2024-06" in cra[0].descricao
    assert cra[0].divulgado_em == date(2024, 8, 1)
    corte = cafe.montar_ficha("cooxupe", fatos, cra=CRA, em=date(2023, 3, 15))
    assert corte is not None
    cra_no_corte = [f for f in corte.fatos if f.fato == "cedente_ou_devedor_de_cra"]
    assert cra_no_corte[0].valor == 1
    assert "2023-01 a 2023-01" in cra_no_corte[0].descricao


def test_o_que_nao_sabemos_diz_o_que_falta_sem_estimar(fatos):
    cooxupe = cafe.montar_ficha("cooxupe", fatos)
    assert cooxupe is not None
    faltas = " ".join(cooxupe.o_que_nao_sabemos)
    assert "Patrimônio líquido" in faltas
    assert "Sacas recebidas" not in faltas  # a Cooxupé publicou
    assert "CRA" in faltas and "Receita" in faltas  # não cruzados nesta ficha
    assert "não prova" in faltas
    coocafeg = cafe.montar_ficha("coocafeg", fatos)
    assert coocafeg is not None and coocafeg.cnpj is None
    assert any("CNPJ" in t for t in coocafeg.o_que_nao_sabemos)
    # nenhum número sem fonte: "o que não sabemos" só tem algarismo na data e no link da notícia
    for ficha in _todas(fatos):
        for texto in ficha.o_que_nao_sabemos:
            assert not re.search(r"\d", DATA_OU_LINK.sub("", texto)), texto


def test_ficha_em_dicionario_so_tem_tipos_simples_e_nenhuma_nota(fatos):
    ficha = cafe.montar_ficha("cooxupe", fatos, cra=CRA)
    assert ficha is not None
    dado = cafe.ficha_em_dicionario(ficha)
    assert set(dado) == {
        "id",
        "cnpj",
        "nome",
        "tipo",
        "uf",
        "fatos",
        "o_que_nao_sabemos",
    }
    assert {f["data"] for f in dado["fatos"]} == {"2025-12-31", "2024-06-01"}
    assert all(isinstance(f["divulgado_em"], str) for f in dado["fatos"])


# arquivista: a cópia das páginas dos fatos, só de sites que não proíbem (licencas-por-fonte.md)


class Sites:
    """Páginas em memória: url -> conteúdo. Guarda o que foi pedido."""

    def __init__(self, paginas: dict[str, bytes]):
        self.paginas = paginas
        self.lidos: list[str] = []

    def ler(self, url, *, metodo="GET", cabecalhos=None):
        self.lidos.append(url)
        return Resposta(url, self.paginas.get(url, b""), {})

    def cabecalhos(self, url):
        return {}

    def baixar(self, url, destino: Path):
        destino.write_bytes(self.paginas[url])
        return {}


def _fatos_de(*fontes_: str) -> pd.DataFrame:
    return pd.DataFrame({"fonte": list(fontes_)})


def test_guarda_a_pagina_de_todo_fato_uma_vez_so_e_na_ordem():
    # ADR 0102 (PR 4): os termos de cada site viram marca registrada, não filtro
    fatos = _fatos_de(
        "https://www.almg.gov.br/a.html",
        "https://agfeed.com.br/?p=1",
        "https://braziljournal.com/x",
        "https://www.comprerural.com/y/",
        "https://www.almg.gov.br/a.html",
    )
    assert contrapartes.paginas_a_guardar(fatos) == [
        "https://www.almg.gov.br/a.html",
        "https://agfeed.com.br/?p=1",
        "https://braziljournal.com/x",
        "https://www.comprerural.com/y/",
    ]


def test_coocem_e_expocacer_entram_pela_adr_0102(fatos):
    # Coocem: fechamento noticiado pela Compre Rural; sem a página guardada fica em "o que não sabemos"
    sem_copia = cafe.montar_ficha("coocem", fatos)
    assert sem_copia is not None and sem_copia.fatos == [] and sem_copia.cnpj is None
    pendente = sem_copia.o_que_nao_sabemos[0]
    assert pendente.startswith(
        "Encerramento das atividades: noticiado por Compre Rural em 18/02/2025"
    )
    noticia = fatos[fatos["id"] == "coocem"]["fonte"].iloc[0]
    com_copia = cafe.montar_ficha("coocem", fatos, guardadas=frozenset({noticia}))
    assert com_copia is not None
    assert [f.fato for f in com_copia.fatos] == ["encerramento"]
    assert "11/02/2025" in com_copia.fatos[0].descricao
    # Expocacer: as sacas recebidas de 2025 vêm do AgFeed, com as nossas palavras
    expocacer = cafe.montar_ficha("expocacer", fatos)
    assert expocacer is not None
    sacas = next(f for f in expocacer.fatos if f.fato == "sacas_recebidas")
    assert sacas.veiculo == "AgFeed" and sacas.valor == 1_100_000
    assert not any("Sacas recebidas" in t for t in expocacer.o_que_nao_sabemos)
    # Brazil Journal: as sacas a receber das tradings; toda página da tabela vai para o arquivista
    assert {"Compre Rural", "AgFeed", "Brazil Journal"} <= set(fatos["veiculo"])
    assert set(fatos["fonte"]) == set(contrapartes.paginas_a_guardar(fatos))


def test_descobrir_le_o_robots_de_cada_site_antes():
    fatos = _fatos_de(
        "https://www.almg.gov.br/a.html", "https://revistacultivar.com.br/n/b"
    )
    sites = Sites({})
    alvos = contrapartes.descobrir(lambda: fatos)(sites, AGORA)
    assert sites.lidos == [
        "https://www.almg.gov.br/robots.txt",
        "https://revistacultivar.com.br/robots.txt",
    ]
    assert alvos == [
        Alvo("https://www.almg.gov.br/a.html", ".html"),
        Alvo("https://revistacultivar.com.br/n/b", ".html"),
    ]


@pytest.mark.parametrize(
    "robots",
    [b"User-agent: *\nDisallow: /\n", b"User-agent: *\nCrawl-delay: 30\n"],
)
def test_robots_que_proibe_ou_pede_mais_espera_para_a_coleta(robots):
    fatos = _fatos_de("https://www.almg.gov.br/a.html")
    sites = Sites({"https://www.almg.gov.br/robots.txt": robots})
    with pytest.raises(ErroDeDescoberta, match="robots.txt"):
        contrapartes.descobrir(lambda: fatos)(sites, AGORA)


def test_fonte_do_arquivista_esta_no_catalogo_com_destino_e_licenca(fatos):
    # ligada com o "pode" do Tiago de 18/10/2026 e ampliada a toda página pela ADR 0102
    fonte = next(f for f in fontes.FONTES if f.id == contrapartes.ID)
    assert fonte.pausa_minima >= 3
    assert fontes.FONTES[-1].id == contrapartes.ID
    assert DESTINOS[contrapartes.ID].tabelas == ("contraparte_cafe",)
    assert coletas.revenda_da_fonte(contrapartes.ID) == coletas.A_CONFIRMAR
    assert "contrapartes" in coletas.REVENDA  # escrito, não só o padrão
    assert (
        coletas.licenca_da_fonte("contrapartes-cafe") != coletas.SEM_LICENCA_CONHECIDA
    )


def test_pagina_guardada_leva_o_fato_de_risco_para_a_ficha(fatos, banco, tmp_path):
    sites = Sites({NOTICIA_DO_PEDIDO: b"<html>pedido</html>"})
    fonte = contrapartes.fonte(lambda: _fatos_de(NOTICIA_DO_PEDIDO))
    with banco.connect() as conexao:
        assert contrapartes.paginas_guardadas(conexao) == frozenset()
    coleta.arquivar(fonte, sites, AGORA, tmp_path / "t", pausa=0)
    with banco.connect() as conexao:
        guardadas = contrapartes.paginas_guardadas(conexao)
    assert guardadas == GUARDADAS
    ficha = cafe.montar_ficha("atlantica", fatos, guardadas=guardadas)
    assert ficha is not None
    assert [f.fato for f in ficha.fatos] == [
        "sacas_a_receber_a_termo",
        "pedido_de_recuperacao_judicial",
    ]


def test_pagina_ja_guardada_nao_e_baixada_de_novo(banco, tmp_path):
    fatos = _fatos_de("https://www.almg.gov.br/a.html")
    sites = Sites({"https://www.almg.gov.br/a.html": b"<html>ALMG</html>"})
    fonte = contrapartes.fonte(lambda: fatos)
    primeira = coleta.arquivar(fonte, sites, AGORA, tmp_path / "t", pausa=0)
    segunda = coleta.arquivar(fonte, sites, AGORA, tmp_path / "t", pausa=0)
    assert (primeira.novos, segunda.novos, segunda.pulados) == (1, 0, 1)
