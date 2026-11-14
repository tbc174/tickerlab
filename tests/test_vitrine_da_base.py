"""A vitrine da base: o catálogo de contratos vira as fontes, os módulos e as tabelas que o site mostra
(plano do site para quem analisa, 18/10/2026, PR 3, tarefa 4).

Funções puras sobre o dicionário do `catalogo.json`; nenhum número da página é digitado à mão.
"""

import json
import re
from dataclasses import asdict
from datetime import date

import pandas as pd
import pytest

from base import cruzamentos_das_fechadas as fechadas
from base import vitrine
from base.contrato import PASTA
from base.dicionario import TABELAS
from base.dossie import (
    conferir_sem_pessoas,
    normalizar_nome,
    pode_consultar_aberto,
)

CVM = "ODbL (dados abertos da CVM; citar a fonte)"
BCB = "ODbL (dados abertos do Banco Central; citar a fonte)"
PGFN = "Dados abertos da PGFN (rodapé CC BY-ND do site: perguntar a licença)"
VENDAVEL = "vendável com atribuição, sob a ODbL (compartilhar igual)"
A_CONFIRMAR = "a confirmar (sem resposta escrita sobre uso comercial)"


def _tabela(
    nome: str,
    modulo: str,
    licenca: str,
    desde: str,
    revenda: str = VENDAVEL,
    **extra: str,
) -> dict:
    return {
        "tabela": nome,
        "modulo": modulo,
        "licenca": licenca,
        "revenda": revenda,
        "historico_desde": desde,
        "frequencia": "Mensal",
        "atraso": "Até 45 dias depois do trimestre",
        **extra,
    }


def _catalogo_falso() -> dict:
    return {
        "tabelas": {
            "a": _tabela("a", "mercado_e_empresas", CVM, "2010-01-01"),
            "b": _tabela("b", "mercado_e_empresas", CVM, "2005-01-31"),
            "c": _tabela("c", "credito_e_fidc", BCB, "2015-01-01"),
        }
    }


def _catalogo_real() -> dict:
    """O catálogo como o site o vê (sem as tabelas só internas)."""
    return vitrine.catalogo_publico(
        json.loads((PASTA / "catalogo.json").read_text(encoding="utf-8"))
    )


# --- fontes --------------------------------------------------------------------------------------


def test_fontes_do_catalogo():
    fontes = vitrine.fontes_do_catalogo(_catalogo_falso())

    assert [f.orgao for f in fontes] == [
        "CVM",
        "Banco Central",
    ]  # mais tabelas primeiro
    cvm, bcb = fontes
    assert cvm.licenca == CVM
    assert cvm.repasse == vitrine.REPASSE_ODBL
    assert cvm.modulos == ("mercado_e_empresas",)
    assert cvm.tabelas == 2
    assert cvm.historico_desde == "2005-01-31"  # a mais antiga das tabelas da fonte
    assert (bcb.tabelas, bcb.modulos) == (1, ("credito_e_fidc",))
    assert cvm.situacao == bcb.situacao == "licenciada"


def test_fonte_junta_os_modulos_sem_repetir():
    catalogo = _catalogo_falso()
    catalogo["tabelas"]["d"] = _tabela("d", "credito_e_fidc", CVM, "2020-01-01")

    cvm = vitrine.fontes_do_catalogo(catalogo)[0]

    assert cvm.modulos == ("credito_e_fidc", "mercado_e_empresas")
    assert cvm.tabelas == 3


def test_licenca_em_consulta():
    """ "Perguntar a licença" (Receita, PGFN) e "a confirmar" não aparecem como licença escrita."""
    catalogo = _catalogo_falso()
    catalogo["tabelas"]["p"] = _tabela(
        "p", "governo_e_sancoes", PGFN, "2026-10-14", revenda=A_CONFIRMAR
    )

    por_orgao = {f.orgao: f for f in vitrine.fontes_do_catalogo(catalogo)}

    assert por_orgao["PGFN"].situacao == "em consulta"
    assert por_orgao["CVM"].situacao == "licenciada"


def test_licenca_do_site_perde_a_decisao_interna():
    assert (
        vitrine.licenca_do_site("Posts públicos de M&A: só fatos, sem texto (ADR 0082)")
        == "Posts públicos de M&A: só fatos, sem texto"
    )
    em_consulta = vitrine.licenca_do_site(PGFN)
    assert "perguntar" not in em_consulta
    assert em_consulta.endswith("reuso em consulta)")


def test_repasse_do_site():
    assert vitrine.repasse_do_site(CVM, "licenciada") == vitrine.REPASSE_ODBL
    assert (
        vitrine.repasse_do_site("CC BY (dados abertos da ANP)", "licenciada")
        == vitrine.REPASSE_COM_ATRIBUICAO
    )
    assert vitrine.repasse_do_site(PGFN, "em consulta") == vitrine.REPASSE_EM_CONSULTA
    for texto in (
        vitrine.REPASSE_ODBL,
        vitrine.REPASSE_COM_ATRIBUICAO,
        vitrine.REPASSE_EM_CONSULTA,
    ):
        assert not re.search(r"\bML\b|revenda|ADR", texto)


@pytest.mark.parametrize(
    "revenda",
    [
        A_CONFIRMAR,
        "não comercial (uso pessoal, só pesquisa)",
        # a CGU (sanções): a página não pode dizer que o dado é repassado
        "só uso interno (entra em modelo; nunca vender nem exportar o dado)",
    ],
)
def test_revenda_nao_confirmada_tambem_fica_em_consulta(revenda: str):
    assert vitrine.situacao_da_licenca(CVM, revenda) == "em consulta"


def test_licenca_sem_orgao_conhecido_acusa():
    catalogo = _catalogo_falso()
    catalogo["tabelas"]["z"] = _tabela(
        "z", "macro", "Licença nova de ninguém", "2020-01-01"
    )

    with pytest.raises(ValueError, match="Licença nova de ninguém"):
        vitrine.fontes_do_catalogo(catalogo)


def test_todo_texto_de_licenca_do_catalogo_real_cai_em_um_orgao():
    licencas = {t["licenca"] for t in _catalogo_real()["tabelas"].values()}

    orgaos = {vitrine.orgao_da_licenca(licenca) for licenca in licencas}

    assert len(orgaos) == len(licencas) == len(vitrine.ORGAOS)


# --- módulos -------------------------------------------------------------------------------------


def test_orgaos_publicos_tira_quem_nao_e_do_estado_e_nao_repete_o_mesmo_orgao():
    nomes = [
        "CVM",
        "Receita Federal",
        "Assessorias de M&A",
        "Receita Federal (renúncias)",
        "CMED (Anvisa)",
        "GLEIF",
        "Anvisa",
        "Receita Federal (transações)",
        "Imprensa e páginas públicas",
    ]

    assert vitrine.orgaos_publicos(nomes) == ["CVM", "Receita Federal", "Anvisa"]


def test_as_listas_da_conta_de_orgaos_so_citam_nomes_que_existem():
    nomes = {orgao for _, orgao in vitrine.ORGAOS}

    assert nomes >= vitrine.ORGAOS_QUE_NAO_SAO_PUBLICOS
    assert nomes >= set(vitrine.MESMO_ORGAO)
    assert (
        set(vitrine.MESMO_ORGAO.values()) <= nomes - vitrine.ORGAOS_QUE_NAO_SAO_PUBLICOS
    )


# os nomes de `ORGAOS` que alguém já conferiu serem órgão ou entidade pública (linha 927)
ORGAOS_PUBLICOS_CONFERIDOS = frozenset(
    {
        "ANAC", "ANEEL", "ANM", "ANP", "ANS", "ANTT", "Anatel", "Ancine", "Anvisa", "BNDES", "Banco Central",
        "CFTC", "CGU", "CNJ", "CONAB", "CVM", "Finep", "Governo do ES", "IBAMA", "INPI", "MAPA", "MDIC", "MME",
        "MTE", "Ministério da Saúde (DATASUS)", "PGFN", "Receita Federal", "SEF-MG", "SEFAZ-PE", "SUSEP",
        "Sefa-PR", "TCE-CE", "TCE-PE", "TCE-RS", "TCE-SP", "Tesouro Nacional", "USDA",
    }
)  # fmt: skip


def test_nome_novo_de_orgao_obriga_a_decidir_se_entra_na_conta():
    """Fonte nova em `ORGAOS` não entra na conta sozinha: ou vai para uma das listas, ou para cá, conferida."""
    nomes = {orgao for _, orgao in vitrine.ORGAOS}

    assert set(vitrine.orgaos_publicos(sorted(nomes))) == ORGAOS_PUBLICOS_CONFERIDOS


def test_a_conta_de_orgaos_do_catalogo_real_so_tem_orgao_publico():
    catalogo = vitrine.catalogo_publico(_catalogo_real())
    ligadas = vitrine.tabelas_ligadas_pelo_cnpj(catalogo)
    todos = vitrine._orgaos(catalogo, ligadas)

    contados = vitrine.orgaos_publicos(todos)

    assert vitrine.ligado_pelo_cnpj(catalogo)["orgaos"] == len(contados)
    assert not set(contados) & vitrine.ORGAOS_QUE_NAO_SAO_PUBLICOS
    assert not set(contados) & set(vitrine.MESMO_ORGAO)
    assert len(contados) < len(
        todos
    )  # hoje há fonte privada e a Receita com três nomes


def test_modulos_do_catalogo():
    modulos = vitrine.modulos_do_catalogo(_catalogo_falso())

    assert [(m.chave, m.nome, m.tabelas) for m in modulos] == [
        ("mercado_e_empresas", "Mercado e empresas", 2),
        ("credito_e_fidc", "Crédito e FIDC", 1),
    ]


def test_modulo_sem_nome_acusa():
    catalogo = {"tabelas": {"x": _tabela("x", "modulo_novo", CVM, "2020-01-01")}}

    with pytest.raises(ValueError, match="modulo_novo"):
        vitrine.modulos_do_catalogo(catalogo)


def test_todo_modulo_do_catalogo_real_tem_nome():
    modulos = vitrine.modulos_do_catalogo(_catalogo_real())

    assert sum(m.tabelas for m in modulos) == len(_catalogo_real()["tabelas"])


# --- tabelas, uma linha cada ---------------------------------------------------------------------


def test_tabelas_do_catalogo_levam_o_que_a_linha_mostra():
    frases = {"a": "Uma linha por conta.", "b": "Outra.", "c": "Terceira."}

    linhas = vitrine.tabelas_do_catalogo(_catalogo_falso(), frases)

    a = next(t for t in linhas if t.tabela == "a")
    assert a.modulo == "mercado_e_empresas"
    assert a.frase == "Uma linha por conta."
    assert (a.orgao, a.situacao) == ("CVM", "licenciada")
    assert a.frequencia == "Mensal"
    assert a.atraso == "Até 45 dias depois do trimestre"
    assert a.historico_desde == "2010-01-01"
    assert (
        a.consultavel is False
    )  # "a" não está no dicionário: só tabela real entra na consulta
    assert [t.tabela for t in linhas] == ["a", "b", "c"]  # a ordem do catálogo


def test_consultavel_segue_a_regra_de_mostrar_e_a_porta():
    """`consultavel` sai da mesma regra da API aberta (`pode_consultar`): tabela que pode ser mostrada
    e que a porta serve por Parquet; a de pessoa, a barrada e a fora da porta ficam só na ficha."""
    frases = dict.fromkeys(TABELAS, "Uma frase.")

    linhas = {
        t.tabela: t for t in vitrine.tabelas_do_catalogo(_catalogo_real(), frases)
    }

    assert linhas["pgfn_divida"].consultavel is True
    assert (
        linhas["cnpj_simples"].consultavel is False
    )  # pode mostrar, mas está fora da porta
    assert linhas["sancoes_cgu"].consultavel is False  # tabela de pessoa
    assert all(
        t.consultavel == pode_consultar_aberto(nome) for nome, t in linhas.items()
    )
    assert sum(t.consultavel for t in linhas.values()) > 50


# --- texto que sai para o site aberto ------------------------------------------------------------


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("Diária no servidor de casa (carga do ENET às 0h30)", "Diária"),
        ("Toda noite no servidor de casa", "Diária"),
        ("Semanal, junto da extração", "Semanal"),
        ("Mensal; de 2005 a 2022 um arquivo por ano", "Mensal"),
        ("Um corte por fim de mês", "Mensal"),
        ("Trimestral (a PGFN publica um retrato por trimestre)", "Trimestral"),
        ("Anual e a cada alteração", "Anual"),
        ("Refeita a cada montagem", "Sem calendário fixo"),
    ],
)
def test_frequencia_vira_um_rotulo_curto(texto: str, esperado: str):
    assert vitrine.frequencia_do_site(texto) == esperado


def test_primeira_frase_sem_codigo_nem_decisao_interna():
    texto = (
        "Uma linha por valor que a conta já teve (ADR 0075), com o dia em que ficou público. "
        "`como_era_em(base, data)` dá a foto."
    )

    frase = vitrine.primeira_frase(texto)

    assert (
        frase
        == "Uma linha por valor que a conta já teve, com o dia em que ficou público."
    )


def test_primeira_frase_tira_o_parentese_que_cita_arquivo_e_nao_corta_em_ponto_de_parentese():
    frase = vitrine.primeira_frase(
        "Os padrões (src/setores.py) do cadastro (atual, histórico, classe... e outros) por setor. Segunda."
    )

    assert (
        frase
        == "Os padrões do cadastro (atual, histórico, classe... e outros) por setor."
    )


def test_primeira_frase_termina_em_ponto_e_corta_antes_do_termo_interno():
    assert vitrine.primeira_frase("Uma linha por fato") == "Uma linha por fato."
    frase = vitrine.primeira_frase(
        "Cada fato, montado no servidor de casa toda noite. Outra."
    )
    assert frase == "Cada fato."


def test_primeira_frase_corta_o_que_fala_de_produto_ou_de_trabalho_interno():
    capital = vitrine.primeira_frase(
        "O cadastro de fundos da CVM, com o gestor de cada FIDC: a lista de clientes possíveis do Capital."
    )
    assert capital == "O cadastro de fundos da CVM, com o gestor de cada FIDC."
    trabalho = vitrine.primeira_frase(
        "Os emissores sem CNPJ, do maior valor para o menor: a lista de trabalho para a próxima conferência."
    )
    assert trabalho == "Os emissores sem CNPJ, do maior valor para o menor."
    modelo = vitrine.primeira_frase(
        "Colunas do modelo de atraso (modelo 8) como eram na data da previsão."
    )
    assert "modelo 8" not in modelo


def test_primeira_frase_longa_prefere_terminar_numa_virgula():
    inicio = (
        "Uma linha por valor diferente que cada conta de cada período já teve, "
        "com o dia em que ficou público e o dia em que a empresa reapresentou"
    )
    frase = vitrine.primeira_frase(inicio + ", " + "texto sem fim " * 15)

    assert frase == f"{inicio}."


def test_primeira_frase_longa_corta_numa_palavra():
    frase = vitrine.primeira_frase("palavra " * 100)

    assert len(frase) <= vitrine.LIMITE_DA_FRASE + 1
    assert frase.endswith("…")
    assert not frase.endswith(" …")


def test_atraso_do_site_descarta_o_que_e_conversa_interna():
    assert (
        vitrine.atraso_do_site("Até 10 dias depois (prazo da CVM)")
        == "Até 10 dias depois"
    )
    assert (
        vitrine.atraso_do_site("`disponivel_em` usa o dia em que o arquivista viu")
        is None
    )
    assert vitrine.atraso_do_site("Texto " * 40) is None


def test_atraso_que_termina_sem_o_fim_da_frase_nao_sai():
    """O código entre crases some do texto e deixa a frase pendurada ("a partir de desde")."""
    assert vitrine.atraso_do_site("A ligação vale a partir de `desde`") is None


# --- a base em números (plano do site para quem analisa, PR 4) ---------------------------------------


class _PortaFalsa:
    """Só o que `numeros_da_base` pede da porta: contar linhas e listar valores diferentes."""

    def __init__(
        self,
        cnpjs: set[str],
        linhas: int,
        reapresentadas: int,
        eventos: int,
        hashes: set[str],
    ):
        self.cnpjs, self.linhas, self.reapresentadas = cnpjs, linhas, reapresentadas
        self.eventos, self.hashes = eventos, hashes

    def distintos(self, tabela: str, coluna: str) -> set[object]:
        return (
            self.cnpjs
            if (tabela, coluna) == ("demonstracoes_como_era", "cnpj")
            else self.hashes
        )

    def contar(self, tabela: str, ao_menos: dict[str, float] | None = None) -> int:
        if tabela == "eventos":
            return self.eventos
        return self.reapresentadas if ao_menos else self.linhas


def _catalogo_com(*tabelas: str) -> dict:
    return {"tabelas": {nome: {"tabela": nome} for nome in tabelas}}


def test_numeros_da_base():
    porta = _PortaFalsa({"1", "2", "3"}, 1_000, 120, 40, {"a", "b"})
    catalogo = _catalogo_com("demonstracoes_como_era", "eventos")

    numeros = vitrine.numeros_da_base(porta, catalogo, date(2026, 10, 26))

    assert numeros == vitrine.NumerosDaBase(
        empresas=3,
        linhas_de_demonstracoes=1_000,
        versoes=120,
        eventos=40,
        originais_com_hash=2,
        medido_em="2026-10-26",
    )


def test_numeros_recusa_tabela_interna():
    """Tabela que o catálogo não tem (ou que a licença não deixa mostrar) nunca vira número público."""
    porta = _PortaFalsa(set(), 0, 0, 0, set())
    with pytest.raises(ValueError, match="eventos"):
        vitrine.numeros_da_base(
            porta, _catalogo_com("demonstracoes_como_era"), date(2026, 10, 26)
        )


def test_base_json_vem_da_fotografia():
    from scripts import exportar_conteudo as exp

    fotografia = json.loads(vitrine.FOTOGRAFIA.read_text(encoding="utf-8"))
    base = exp.conteudo()["base"]

    assert base["numeros"] == fotografia
    assert base["medido_em_curto"] == vitrine.dia_e_mes(fotografia["medido_em"])
    assert vitrine.dia_e_mes("2026-10-26") == "26/10"


def test_fotografia_com_campo_a_menos_nao_passa():
    with pytest.raises(TypeError):
        vitrine.numeros_da_fotografia({"empresas": 1})


# --- vagas da vitrine (plano do site para quem analisa, PR 5, tarefa 8) ---------------------------

SITE = PASTA.parent.parent / "site"


def test_vagas_na_ordem_do_plano():
    assert [v.chave for v in vitrine.VAGAS_DA_VITRINE] == [
        "setor",
        "ficha",
        "cnpj",
        "ma",
        "cruzamentos",
    ]


def test_vaga_pronta_aponta_para_pagina_que_existe():
    prontas = [v for v in vitrine.VAGAS_DA_VITRINE if v.estado == "pronta"]
    assert prontas, "a vitrine precisa de ao menos uma vaga pronta"
    for vaga in prontas:
        assert vaga.link and vaga.link.startswith("/")
        caminho, _, ancora = vaga.link.partition("#")
        pagina = SITE / (caminho.lstrip("/") or "index.html")
        assert pagina.is_file(), vaga.link
        # a vaga que leva a uma seção da própria página aponta para um id que existe
        if ancora:
            assert f'id="{ancora}"' in pagina.read_text(encoding="utf-8"), vaga.link


def test_vaga_em_breve_nao_tem_link_nem_data():
    for vaga in vitrine.VAGAS_DA_VITRINE:
        assert vaga.estado in {"pronta", "em_breve"}
        if vaga.estado == "em_breve":
            assert vaga.link is None
            # "em breve" sem prazo: nenhuma data prometida no texto
            assert not re.search(r"\d{1,2}/\d{1,2}|20\d\d", vaga.para_que_serve)


def test_toda_vaga_diz_para_que_serve_em_uma_linha():
    for vaga in vitrine.VAGAS_DA_VITRINE:
        assert vaga.titulo and vaga.para_que_serve
        assert "\n" not in vaga.para_que_serve
        assert len(vaga.para_que_serve) <= 160, vaga.chave


@pytest.mark.parametrize(
    ("estado", "link"),
    [("pronta", None), ("em_breve", "/dados.html"), ("talvez", None)],
)
def test_vaga_mal_formada_nao_passa(estado, link):
    with pytest.raises(ValueError):
        vitrine.Vaga("x", "X", "Serve para x.", estado, link)


def test_vitrine_json_leva_as_vagas():
    from scripts import exportar_conteudo as exp

    assert exp.conteudo()["vitrine"] == [asdict(v) for v in vitrine.VAGAS_DA_VITRINE]


# --- cruzamentos da base (plano do site para quem analisa, PR 6, tarefa 10) -----------------------

ALFA, BETA, GAMA_CONTROLADA, DELTA = (
    "11.111.111/0001-11",
    "22.222.222/0001-22",
    "33.333.333/0001-33",
    "44.444.444/0001-44",
)
NOMES_DO_MUNDO_FALSO = (
    "ALFA ENERGIA S.A.",
    "BETA SANEAMENTO S.A.",
    "GAMA TRANSMISSORA S.A.",
    "DELTA PAPEL S.A.",
    "AUDITORES UM",
    "AUDITORES DOIS",
    "PESSOA INVENTADA LICITACAO",
)
LUCRO = "Lucro/Prejuízo Consolidado do Período"
MILHAO = 1e6


def _lucro(
    cnpj: str,
    fim: str,
    milhoes: float,
    referencia: str,
    ordem: str = "ultimo",
    publico_em: str | None = None,
) -> dict:
    divulgado = pd.Timestamp(referencia) + pd.Timedelta(days=89)
    return {
        "cnpj": cnpj,
        "grupo": "con",
        "demonstracao": "DRE",
        "documento": "DFP",
        "conta": "3.11",
        "descricao": LUCRO,
        "fim": pd.Timestamp(fim),
        "referencia": pd.Timestamp(referencia),
        "valor": milhoes * MILHAO,
        "versao": 1,
        "ordem": ordem,
        "divulgado_em": divulgado,
        "publico_em": pd.Timestamp(publico_em) if publico_em else divulgado,
    }


def _remuneracao(
    cnpj: str,
    ano: str,
    milhoes: float,
    referencia: str,
    versao: int = 1,
    orgao: str = vitrine.DIRETORIA,
) -> dict:
    """Uma linha do FRE de `referencia` sobre o exercício `ano`, entregue 150 dias depois (fim de maio)."""
    return {
        "cnpj": cnpj,
        "referencia": pd.Timestamp(referencia),
        "versao": versao,
        "inicio_do_exercicio": pd.Timestamp(f"{ano}-01-01"),
        "fim_do_exercicio": pd.Timestamp(f"{ano}-12-31"),
        "orgao": orgao,
        "total_do_orgao": milhoes * MILHAO,
        "publico_em": pd.Timestamp(referencia) + pd.Timedelta(days=150),
    }


def _provento(cnpj: str, ano: str, milhoes: float, referencia: str) -> dict:
    return {
        "cnpj": cnpj,
        "referencia": pd.Timestamp(referencia),
        "versao": 1,
        "exercicio": pd.Timestamp(f"{ano}-12-31"),
        "dividendo_total": milhoes * MILHAO,
    }


def _parecer(
    cnpj: str, ano: str, continuidade: str, publico_em: str, versao: int = 1
) -> dict:
    return {
        "cnpj": cnpj,
        "referencia": pd.Timestamp(f"{ano}-12-31"),
        "versao": versao,
        "continuidade_operacional": continuidade,
        "publico_em": pd.Timestamp(publico_em),
    }


def _mundo_falso() -> dict[str, pd.DataFrame]:
    """Alfa troca de auditor e refaz o lucro de 2020 no balanço de 2021 (de 100 para 90 milhões), que
    saiu atrasado; Beta troca também e não refaz nada, mas vira prejuízo em 2021, paga dividendo mesmo
    assim, ouve o auditor duvidar da continuidade e pede recuperação em 2022. Gama ouve a dúvida e nada
    acontece; Delta já estava falida."""
    demonstracoes = pd.DataFrame(
        [
            _lucro(ALFA, "2020-12-31", 100, "2020-12-31"),
            _lucro(ALFA, "2021-12-31", 200, "2021-12-31"),
            _lucro(ALFA, "2020-12-31", 90, "2021-12-31", ordem="penultimo"),
            _lucro(ALFA, "2022-12-31", 300, "2022-12-31"),
            _lucro(BETA, "2020-12-31", 50, "2020-12-31"),
            _lucro(BETA, "2021-12-31", -30, "2021-12-31"),
            # o balanço de 2022 da Beta ainda não era público no dia da medição
            _lucro(BETA, "2022-12-31", 70, "2022-12-31", publico_em="2027-01-01"),
        ]
    )
    trocas = pd.DataFrame(
        {
            "cnpj": [ALFA, BETA],
            "empresa": ["ALFA ENERGIA S.A.", "BETA SANEAMENTO S.A."],
            "anterior": ["AUDITORES UM", "AUDITORES DOIS"],
            "novo": ["AUDITORES DOIS", "AUDITORES UM"],
            "publico_em": pd.to_datetime(["2021-06-01", "2021-06-01"]),
        }
    )
    # a DFP de 2020 da Alfa saiu em maio, depois do prazo (e grave); as outras, no prazo; o ITR não conta
    atrasos = pd.DataFrame(
        {
            "cnpj": [ALFA, ALFA, BETA, ALFA],
            "empresa": ["ALFA ENERGIA S.A."] * 2
            + ["BETA SANEAMENTO S.A.", "ALFA ENERGIA S.A."],
            "documento": ["DFP", "DFP", "DFP", "ITR"],
            "referencia": pd.to_datetime(
                ["2020-12-31", "2021-12-31", "2020-12-31", "2021-03-31"]
            ),
            "atrasou": [True, False, False, True],
            "atraso_grave": [True, False, False, True],
            "publico_em": pd.to_datetime(
                ["2021-05-13", "2022-03-30", "2021-03-30", "2021-06-01"]
            ),
        }
    )
    remuneracao = pd.DataFrame(
        [
            # Alfa: 10, 12 e 11 milhões; a versão 2 do FRE de 2022 corrige o exercício de 2021 (11 → 12)
            _remuneracao(ALFA, "2020", 10, "2021-01-01"),
            _remuneracao(ALFA, "2021", 11, "2022-01-01"),
            _remuneracao(ALFA, "2021", 12, "2022-01-01", versao=2),
            _remuneracao(ALFA, "2022", 11, "2023-01-01"),
            # o valor previsto para o ano em curso (o FRE sai em maio) não é remuneração paga
            _remuneracao(ALFA, "2023", 99, "2023-01-01"),
            # o conselho não entra
            _remuneracao(
                ALFA, "2021", 1, "2022-01-01", orgao="Conselho de Administração"
            ),
            _remuneracao(BETA, "2020", 5, "2021-01-01"),
            _remuneracao(BETA, "2021", 6, "2022-01-01"),
        ]
    )
    proventos = pd.DataFrame(
        [
            _provento(ALFA, "2020", 150, "2021-01-01"),  # acima do lucro de 100 milhões
            _provento(ALFA, "2021", 50, "2022-01-01"),
            # o FRE cujo prazo ainda não passou no dia da medição não entra (ele mudaria o de 2021)
            _provento(ALFA, "2021", 999, "2026-08-01"),
            _provento(BETA, "2020", 0, "2021-01-01"),  # sem dividendo
            _provento(BETA, "2021", 10, "2022-01-01"),  # com prejuízo de 30 milhões
        ]
    )
    pareceres = pd.DataFrame(
        [
            _parecer(ALFA, "2020", "nao", "2021-03-30"),
            _parecer(ALFA, "2021", "nao", "2022-03-30"),
            _parecer(BETA, "2020", "nao", "2021-03-30"),
            _parecer(
                BETA, "2020", "sim", "2021-06-01", versao=2
            ),  # a reapresentação é a que vale
            _parecer(BETA, "2021", "sim", "2022-03-30"),
            _parecer(GAMA_CONTROLADA, "2022", "sim", "2023-03-30"),
            _parecer(DELTA, "2020", "sim", "2021-03-30"),  # a Delta já estava falida
            _parecer(
                ALFA, "2022", "nao_classificado", "2023-03-30"
            ),  # relatório curto: nem sim nem não
            _parecer(
                GAMA_CONTROLADA, "2024", "sim", "2025-03-30"
            ),  # ainda não fez 24 meses
        ]
    )
    insolvencia = pd.DataFrame(
        {
            "cnpj": [BETA, DELTA, ALFA],
            "empresa": [
                "BETA SANEAMENTO S.A.",
                "DELTA PAPEL S.A.",
                "ALFA ENERGIA S.A.",
            ],
            "rotulo": ["recuperacao_judicial", "falencia", "exposicao_a_terceiro"],
            "publico_em": pd.to_datetime(["2022-09-01", "2019-05-01", "2021-01-01"]),
        }
    )
    return {
        vitrine.DEMONSTRACOES: demonstracoes,
        vitrine.TROCAS_DE_AUDITOR: trocas,
        vitrine.ROTULOS_DE_ATRASO: atrasos,
        vitrine.REMUNERACAO: remuneracao,
        vitrine.PROVENTOS: proventos,
        vitrine.PARECERES: pareceres,
        vitrine.INSOLVENCIA: insolvencia,
    }


class _PortaQueLe:
    """O que `medir_cruzamentos` pede da porta: ler com filtros de igualdade, colunas e "como era"."""

    def __init__(self, tabelas: dict[str, pd.DataFrame]):
        self.tabelas = tabelas

    def ler(
        self,
        tabela: str,
        versao: str | None = None,
        como_era_em: object = None,
        filtros: dict[str, object] | None = None,
        colunas: list[str] | None = None,
    ) -> pd.DataFrame:
        linhas = self.tabelas[tabela]
        for coluna, valor in (filtros or {}).items():
            valores = valor if isinstance(valor, (list, tuple, set)) else [valor]
            linhas = linhas[linhas[coluna].isin(valores)]
        if como_era_em is not None:
            linhas = linhas[linhas["publico_em"] <= pd.Timestamp(como_era_em)]
        if colunas is not None:
            linhas = linhas[list(colunas)]
        return linhas.reset_index(drop=True)


DIA_DA_MEDICAO = date(2026, 10, 26)


def _cruzamentos() -> vitrine.Cruzamentos:
    catalogo = _catalogo_com(*vitrine.TABELAS_DOS_CRUZAMENTOS)
    return vitrine.medir_cruzamentos(
        _PortaQueLe(_mundo_falso()), catalogo, DIA_DA_MEDICAO
    )


def test_lucros_refeitos_no_balanco_seguinte():
    """Só conta o balanço que já tem o do ano seguinte; lucro sem linha "penúltimo" não mudou."""
    assert (
        _cruzamentos().lucros
        == vitrine.LucrosRefeitos(
            balancos=3,  # Alfa 2020 e 2021, Beta 2020 (o de 2022 da Beta ainda não era público)
            refeitos=1,
            companhias_refeitas=1,
            companhias=2,
            primeiro_exercicio=2020,
            ultimo_exercicio=2021,
        )
    )


def test_troca_de_auditor_olha_o_primeiro_balanco_depois_dela():
    """A troca de junho de 2021 vale para o balanço de 2021, que refaz (ou não) o lucro de 2020."""
    assert _cruzamentos().auditor == vitrine.TrocasDeAuditor(
        trocas=2,
        trocas_com_balanco=2,
        trocas_refeitas=1,
        balancos_sem_troca=1,  # Alfa 2021
        refeitos_sem_troca=0,
    )


def test_atraso_na_dfp_e_lucro_refeito():
    """Só a DFP (o ITR não é balanço anual) e só os balanços que já têm o seguinte."""
    assert _cruzamentos().atraso == vitrine.AtrasoERefeito(
        atrasados=1,  # Alfa 2020, que refez
        atrasados_refeitos=1,
        graves=1,
        graves_refeitos=1,
        no_prazo=2,  # Alfa 2021 e Beta 2020
        no_prazo_refeitos=0,
    )


def test_remuneracao_da_diretoria_e_lucro_em_pares_de_anos():
    """A última versão do FRE vale; o ano em curso (previsto) e o conselho ficam de fora."""
    assert _cruzamentos().remuneracao == vitrine.RemuneracaoELucro(
        pares=3,  # Alfa 2021 e 2022, Beta 2021
        remuneracao_subiu=2,  # Alfa 2021 (10 → 12) e Beta 2021 (5 → 6)
        lucro_caiu=1,  # Beta 2021 virou prejuízo
        lucro_caiu_e_remuneracao_subiu=1,
        lucro_subiu=2,  # Alfa 2021 e 2022
        lucro_subiu_e_remuneracao_subiu=1,
        companhias=2,
        primeiro_exercicio=2021,
        ultimo_exercicio=2022,
    )


def test_dividendo_acima_do_lucro_do_ano():
    """O FRE cujo prazo não passou não entra; exercício sem dividendo não conta."""
    assert _cruzamentos().dividendo == vitrine.DividendoELucro(
        exercicios=3,  # Alfa 2020 e 2021, Beta 2021
        companhias=2,
        acima_do_lucro=2,  # Alfa 2020 (150 > 100) e Beta 2021 (10 > -30)
        companhias_acima=2,
        com_prejuizo=1,
        primeiro_exercicio=2020,
        ultimo_exercicio=2021,
    )


def test_parecer_com_duvida_e_insolvencia_em_24_meses():
    """A reapresentação é a que vale; parecer novo demais, companhia já insolvente e relatório não
    classificado ficam de fora; a exposição a terceiro não é insolvência da companhia."""
    assert _cruzamentos().parecer == vitrine.ParecerEInsolvencia(
        com_duvida=3,  # Beta 2020 (versão 2), Beta 2021, Gama 2022
        com_duvida_e_insolvencia=2,  # a Beta pediu recuperação em setembro de 2022
        sem_duvida=2,  # Alfa 2020 e 2021
        sem_duvida_e_insolvencia=0,
        companhias_com_duvida=2,
        primeiro_exercicio=2020,
        ultimo_exercicio=2022,
    )


def test_todas_as_tabelas_dos_cruzamentos_podem_ser_mostradas():
    """Desde a virada de 5/11/2026 o rótulo de atraso sai como fato datado, como as outras tabelas dos
    cruzamentos: nenhuma é só contagem."""
    from base import dossie

    assert vitrine.ROTULOS_DE_ATRASO in vitrine.TABELAS_DOS_CRUZAMENTOS
    for tabela in vitrine.TABELAS_DOS_CRUZAMENTOS:
        assert dossie.pode_mostrar(tabela)


def test_cruzamentos_recusam_tabela_fora_do_catalogo():
    catalogo = _catalogo_com(
        *[t for t in vitrine.TABELAS_DOS_CRUZAMENTOS if t != vitrine.INSOLVENCIA]
    )
    with pytest.raises(ValueError, match="insolvencia"):
        vitrine.medir_cruzamentos(_PortaQueLe(_mundo_falso()), catalogo, DIA_DA_MEDICAO)


def test_fatos_agregados_tem_fonte_e_data():
    fatos = vitrine.fatos_agregados(_cruzamentos())
    assert [f.chave for f in fatos] == [
        "lucros",
        "auditor",
        "atraso",
        "remuneracao",
        "dividendo",
        "parecer",
    ]
    for fato in fatos:
        assert fato.texto and fato.numero and fato.como_foi_calculado
        assert fato.fonte.startswith("CVM")
        assert len(fato.tabelas) >= 2 or fato.chave == "lucros"
        assert set(fato.tabelas) <= set(vitrine.TABELAS_DOS_CRUZAMENTOS)
        assert fato.data == "2026-10-26"
    assert fatos[0].numero == "33,3%"
    assert "1 de 2 companhias" in fatos[0].texto
    assert fatos[2].numero == "100,0%" and "no prazo, foram 0,0%" in fatos[2].texto
    assert fatos[3].numero == "100,0%" and "subiu em 50,0% dos 2" in fatos[3].texto
    assert fatos[4].numero == "2" and "Em 1 deles" in fatos[4].texto
    assert fatos[5].numero == "66,7%" and "foram 0,0%" in fatos[5].texto


def test_fatos_sem_pessoas():
    """Nenhum nome do que entrou na conta (companhia, auditor, administrador) sai no fato: só contagens."""
    nomes = {normalizar_nome(n) for n in NOMES_DO_MUNDO_FALSO}
    for fato in vitrine.fatos_agregados(_cruzamentos()):
        conferir_sem_pessoas(asdict(fato), nomes)
        palavras = normalizar_nome(
            f"{fato.texto} {fato.fonte} {fato.como_foi_calculado}"
        ).split()
        for nome in nomes:
            assert nome.split()[0] not in palavras, (fato.chave, nome)


# o que o site não diz (as mesmas da página inicial) e o que insinuaria culpa num fato agregado
PROIBIDAS_NOS_FATOS = re.compile(
    r"recomend|vai subir|vai cair|oportunidade|mais dados que|maior base|fraude|manipul|suspeit"
    r"|escond|maquia|Bloomberg|FactSet|Refinitiv|Economatica|brapi|Status ?Invest",
    re.IGNORECASE,
)


def test_fatos_passam_pela_lista_proibida():
    for fato in vitrine.fatos_agregados(_cruzamentos()):
        for texto in (fato.texto, fato.como_foi_calculado):
            assert not PROIBIDAS_NOS_FATOS.search(texto), (fato.chave, texto)
        assert len(fato.texto) <= vitrine.LIMITE_DO_FATO, fato.chave


def test_fatos_da_base_vem_da_fotografia():
    from scripts import exportar_conteudo as exp

    fotografia = json.loads(
        vitrine.FOTOGRAFIA_DOS_CRUZAMENTOS.read_text(encoding="utf-8")
    )
    das_fechadas = fotografia.pop(vitrine.CHAVE_DAS_FECHADAS, None)
    fatos = exp.conteudo()["fatos_da_base"]

    cruzamentos = vitrine.cruzamentos_da_fotografia(fotografia)
    medicao = (
        None if das_fechadas is None else fechadas.fechadas_da_fotografia(das_fechadas)
    )
    # o recorte por estado e setor vem do arquivo ao lado, quando a fotografia o tem
    arquivo_dos_recortes = vitrine.FOTOGRAFIA_DOS_CRUZAMENTOS.with_name(
        vitrine.NOME_DOS_RECORTES
    )
    recortes = (
        fechadas.recortes_da_fotografia(
            json.loads(arquivo_dos_recortes.read_text(encoding="utf-8"))
        )
        if arquivo_dos_recortes.exists()
        else None
    )
    assert fatos["grupos"] == vitrine.grupos_dos_fatos(cruzamentos, medicao, recortes)
    for grupo in fatos["grupos"]:
        for fato in grupo["fatos"]:
            assert len(fato["texto"]) <= vitrine.LIMITE_DO_FATO, fato["chave"]
    medido_em = cruzamentos.medido_em if medicao is None else medicao.medido_em
    assert fatos["medido_em_curto"] == vitrine.dia_e_mes(medido_em)
    assert f"medidas em {fatos['medido_em_curto']}" in fatos["subtitulo"]


# --- os cartões de empresa fechada (linha 925) --------------------------------------------------------

_MOLDES_COM_TEXTO = [m.chave for m in fechadas.MOLDES if m.sql is not None]


def _medicao_das_fechadas(*chaves: str) -> fechadas.MedicaoDasFechadas:
    return fechadas.MedicaoDasFechadas(
        medido_em="2026-11-14",
        cartoes=tuple(fechadas.CartaoMedido(c, parte=1234, todo=98765) for c in chaves),
        caidos=(fechadas.CartaoCaido("tce_e_sancao", "sancoes_cgu: só uso interno"),),
    )


def test_todo_cartao_medivel_tem_texto_e_so_ele():
    assert set(vitrine.MOLDES_DOS_FATOS) == set(_MOLDES_COM_TEXTO)


@pytest.mark.parametrize("chave", _MOLDES_COM_TEXTO)
def test_o_cartao_da_fechada_tem_fonte_data_e_conta_sem_palavra_proibida(chave):
    fato = vitrine.fato_da_fechada(
        fechadas.CartaoMedido(chave, parte=1234, todo=98765), "2026-11-14"
    )
    assert fato.numero in {"1.234", "1,2%"}
    assert fato.fonte and fato.tabelas and fato.data == "2026-11-14"
    assert vitrine.FECHADA_E_ATIVA in fato.como_foi_calculado
    assert len(fato.texto) <= vitrine.LIMITE_DO_FATO
    for texto in (fato.texto, fato.fonte, fato.como_foi_calculado):
        assert not PROIBIDAS_NOS_FATOS.search(texto), texto
        assert not re.search(r"\bpre[çc]o\b|R\$|garant[ei] (retorno|lucro)", texto), (
            texto
        )
    assert "98.765" in fato.texto
    conferir_sem_pessoas(asdict(fato), set())


def test_os_grupos_poem_as_fechadas_primeiro_e_as_abertas_por_ultimo():
    medicao = _medicao_das_fechadas("finep_e_patente", "saiu_do_simples", "tres_niveis")
    grupos = vitrine.grupos_dos_fatos(_cruzamentos(), medicao)
    assert [g["chave"] for g in grupos] == [
        "crescendo",
        "se_mexeu",
        "fora_do_balanco",
        "abertas",
    ]
    assert [[f["chave"] for f in g["fatos"]] for g in grupos] == [
        ["saiu_do_simples"],
        ["tres_niveis"],
        ["finep_e_patente"],
        ["lucros", "parecer"],
    ]
    assert all(f["data"] == "2026-11-14" for g in grupos[:-1] for f in g["fatos"])


def test_sem_a_medicao_das_fechadas_ficam_so_as_abertas():
    grupos = vitrine.grupos_dos_fatos(_cruzamentos(), None)
    assert [g["chave"] for g in grupos] == ["abertas"]


def test_fatos_da_base_le_as_fechadas_da_fotografia(tmp_path):
    """O script grava a medição das fechadas na chave dela do `fatos.json`, e a página a lê de volta."""
    from scripts.medir_base_para_o_site import fatos_com_as_fechadas, gravar

    medicao = _medicao_das_fechadas(*_MOLDES_COM_TEXTO)
    arquivo = tmp_path / "fatos.json"
    gravar(fatos_com_as_fechadas(_cruzamentos(), medicao), arquivo)
    fatos = vitrine.fatos_da_base(arquivo)
    assert [g["chave"] for g in fatos["grupos"]] == [
        *(g.chave for g in fechadas.GRUPOS),
        "abertas",
    ]
    assert fatos["medido_em_curto"] == vitrine.dia_e_mes("2026-11-14")
    assert fatos["subtitulo"].startswith(
        "Contagens de empresas fechadas e de companhias abertas"
    )
    assert "medidas em" in fatos["subtitulo"]


def test_fatos_da_base_sem_as_fechadas_mantem_o_paragrafo_das_abertas(tmp_path):
    arquivo = tmp_path / "fatos.json"
    arquivo.write_text(json.dumps(asdict(_cruzamentos())), encoding="utf-8")
    fatos = vitrine.fatos_da_base(arquivo)
    assert [g["chave"] for g in fatos["grupos"]] == ["abertas"]
    assert fatos["subtitulo"].startswith("Contagens das companhias abertas")


# --- o recorte por estado e por setor de cada cartão (linha 925, 2º PR) ----------------------------------


def _recorte(chave: str) -> fechadas.RecorteDoCartao:
    return fechadas.RecorteDoCartao(
        chave,
        por_uf=fechadas.celulas_que_saem(
            {"SP": (5000, 1000), "MG": (3000, 500), "nd": (400, 120), "AC": (5, 1)}
        ),
        por_setor=fechadas.celulas_que_saem({"C": (6000, 1300), "J": (2405, 321)}),
    )


def _recortes(
    *chaves: str, medido_em: str = "2026-11-14"
) -> fechadas.RecortesDasFechadas:
    return fechadas.RecortesDasFechadas(
        medido_em, tuple(_recorte(c) for c in chaves), ()
    )


def test_o_recorte_vira_barras_da_maior_parte_para_a_menor():
    recorte = vitrine.recorte_do_fato(_recorte("saiu_do_simples"))
    por_uf = recorte["por_uf"]
    # a AC é pequena e a "nd", a menor das outras, cai junto (senão a AC sairia pela subtração)
    assert [b["rotulo"] for b in por_uf["barras"]] == ["SP", "MG"]
    assert por_uf["escondidas"] == sorted(["AC", vitrine.ROTULO_SEM_INFORMACAO])
    assert por_uf["barras"][0] == {
        "rotulo": "SP",
        "parte": "1.000",
        "todo": "5.000",
        "porcento": "20,0%",
        "largura": 100.0,
        "filtro_no_app": {"uf": "SP"},
    }
    assert por_uf["barras"][1]["largura"] == 50.0
    setores = [b["rotulo"] for b in recorte["por_setor"]["barras"]]
    assert setores == [fechadas.cnae.SECOES["C"], fechadas.cnae.SECOES["J"]]
    for texto in (recorte["como_foi_calculado"], *setores):
        assert not PROIBIDAS_NOS_FATOS.search(texto), texto
    conferir_sem_pessoas(recorte, set())


def test_cada_barra_leva_o_filtro_que_o_app_le_e_so_quando_a_busca_tem_o_valor():
    from src.analista import busca

    celulas = fechadas.celulas_que_saem(
        {"SP": (900, 300), "MG": (800, 200), "nd": (700, 100)}
    )
    filtros = {
        b["rotulo"]: b["filtro_no_app"]
        for b in vitrine.barras_do_recorte(celulas, "uf")["barras"]
    }
    assert filtros == {
        "SP": {"uf": "SP"},
        "MG": {"uf": "MG"},
        vitrine.ROTULO_SEM_INFORMACAO: None,
    }
    # a seção fora da busca do app (O, T e U) sai sem link; a que está nela leva a letra da seção
    assert "O" not in busca.SETORES
    setores = fechadas.celulas_que_saem({"C": (900, 300), "O": (800, 200)})
    assert [
        b["filtro_no_app"]
        for b in vitrine.barras_do_recorte(setores, "setor")["barras"]
    ] == [{"setor": "C"}, None]


def test_fatos_da_base_le_o_recorte_ao_lado_da_fotografia(tmp_path):
    from scripts.medir_base_para_o_site import fatos_com_as_fechadas, gravar

    medicao = _medicao_das_fechadas(*_MOLDES_COM_TEXTO)
    arquivo = tmp_path / "fatos.json"
    gravar(fatos_com_as_fechadas(_cruzamentos(), medicao), arquivo)
    gravar(
        fechadas.recortes_para_a_fotografia(
            _recortes("saiu_do_simples", "tres_niveis")
        ),
        tmp_path / vitrine.NOME_DOS_RECORTES,
    )
    fatos = vitrine.fatos_da_base(arquivo)
    com_recorte = {
        f["chave"] for g in fatos["grupos"] for f in g["fatos"] if "recorte" in f
    }
    assert com_recorte == {"saiu_do_simples", "tres_niveis"}


def test_recorte_de_outra_medicao_nao_entra():
    medicao = _medicao_das_fechadas("saiu_do_simples")
    recortes = _recortes("saiu_do_simples", medido_em="2026-11-13")
    grupos = vitrine.grupos_dos_fatos(_cruzamentos(), medicao, recortes)
    assert all("recorte" not in f for g in grupos for f in g["fatos"])


def test_fotografia_do_recorte_volta_igual_e_recusa_celula_pequena():
    recortes = _recortes("saiu_do_simples")
    dados = json.loads(json.dumps(fechadas.recortes_para_a_fotografia(recortes)))
    assert fechadas.recortes_da_fotografia(dados) == recortes
    dados["cartoes"][0]["por_uf"][0] = {"chave": "AC", "parte": 1, "todo": 5}
    with pytest.raises(ValueError, match="célula AC"):
        fechadas.recortes_da_fotografia(dados)
    dados["cartoes"][0]["por_uf"][0] = {"chave": "AC", "parte": None, "todo": 5}
    with pytest.raises(ValueError, match="pela metade"):
        fechadas.recortes_da_fotografia(dados)


def test_fotografia_dos_cruzamentos_volta_igual():
    cruzamentos = _cruzamentos()
    assert vitrine.cruzamentos_da_fotografia(asdict(cruzamentos)) == cruzamentos


# --- ligado pelo CNPJ: o que a base junta de cada empresa (página inicial, 04/11/2026) -----------


def _com_colunas(nome: str, modulo: str, licenca: str, *colunas: str) -> dict:
    return {
        **_tabela(nome, modulo, licenca, "2020-01-01"),
        "colunas": {c: {} for c in colunas},
    }


def test_coluna_de_cnpj():
    for coluna in (
        "cnpj",
        "cnpj_basico",
        "cnpj_raiz",
        "auditor_cnpj",
        "raiz",
        "CNPJ_FUNDO",
        "CPF_CNPJ_GESTOR",
    ):
        assert vitrine.e_coluna_de_cnpj(coluna), coluna
    # a cobertura conta CNPJs, não liga uma linha a uma empresa
    for coluna in (
        "valor_com_cnpj",
        "fracao_com_cnpj",
        "cnpjota",
        "competencia",
        "tipo",
    ):
        assert not vitrine.e_coluna_de_cnpj(coluna), coluna


def test_tabelas_ligadas_pelo_cnpj_incluem_a_rede():
    catalogo = {
        "tabelas": {
            "a": _com_colunas("a", "mercado_e_empresas", CVM, "cnpj", "valor"),
            "b": _com_colunas("b", "macro", BCB, "data", "valor_com_cnpj"),
            "ligacoes": _com_colunas("ligacoes", "rede", CVM, "de", "para"),
        }
    }

    assert vitrine.tabelas_ligadas_pelo_cnpj(catalogo) == ["a", "ligacoes"]


def test_ligado_pelo_cnpj_conta_tabelas_e_orgaos_do_catalogo():
    tema = vitrine.TemaDoCnpj("donos", "Quem é dono", "Sócios.", ("a", "c"))
    catalogo = {
        "tabelas": {
            "a": _com_colunas("a", "mercado_e_empresas", CVM, "cnpj"),
            "b": _com_colunas("b", "mercado_e_empresas", CVM, "data"),
            "c": _com_colunas("c", "governo_e_sancoes", PGFN, "cnpj_basico"),
        }
    }

    ligado = vitrine.ligado_pelo_cnpj(catalogo, (tema,))

    assert ligado == {
        "tabelas": 2,
        "orgaos": 2,
        "temas": [
            {
                "chave": "donos",
                "titulo": "Quem é dono",
                "texto": "Sócios.",
                "orgaos": ["CVM", "PGFN"],
                "tabelas": 2,
            }
        ],
    }


def test_tema_com_tabela_fora_do_catalogo_acusa():
    tema = vitrine.TemaDoCnpj("x", "X", "X.", ("sumiu",))

    with pytest.raises(ValueError, match="sumiu"):
        vitrine.ligado_pelo_cnpj({"tabelas": {}}, (tema,))


def test_tema_com_tabela_sem_cnpj_acusa():
    tema = vitrine.TemaDoCnpj("x", "X", "X.", ("b",))
    catalogo = {"tabelas": {"b": _com_colunas("b", "macro", BCB, "data")}}

    with pytest.raises(ValueError, match="sem coluna de CNPJ: b"):
        vitrine.ligado_pelo_cnpj(catalogo, (tema,))


def test_temas_do_cnpj_valem_no_catalogo_real():
    catalogo = _catalogo_real()

    ligado = vitrine.ligado_pelo_cnpj(catalogo)

    assert [t["chave"] for t in ligado["temas"]] == [
        t.chave for t in vitrine.TEMAS_DO_CNPJ
    ]
    assert 0 < ligado["tabelas"] < len(catalogo["tabelas"])
    assert ligado["orgaos"] <= len(vitrine.fontes_do_catalogo(catalogo))
    # nenhuma tabela em dois temas: a soma dos cartões não conta duas vezes
    nomes = [n for t in vitrine.TEMAS_DO_CNPJ for n in t.tabelas]
    assert len(nomes) == len(set(nomes))


def test_tabela_sem_tema_so_cobra_os_modulos_dos_orgaos_publicos():
    tema = vitrine.TemaDoCnpj("x", "X", "X.", ("a",))
    catalogo = {
        "tabelas": {
            "a": _com_colunas("a", "governo_e_sancoes", PGFN, "cnpj"),
            "b": _com_colunas("b", "governo_e_sancoes", PGFN, "cnpj_basico"),
            "c": _com_colunas("c", "mercado_e_empresas", CVM, "cnpj"),
            "d": _com_colunas("d", "governo_e_sancoes", PGFN, "data"),
        }
    }

    assert vitrine.tabelas_sem_tema(catalogo, (tema,)) == ["b"]


def test_toda_tabela_nova_de_orgao_publico_com_cnpj_entra_num_tema():
    sem_tema = vitrine.tabelas_sem_tema(_catalogo_real())

    assert not sem_tema, (
        f"tabela nova ligada pelo CNPJ fora da página inicial: {', '.join(sem_tema)}. Ponha-a num "
        "tema de base/vitrine.py::TEMAS_DO_CNPJ (e o órgão na frase do tema), rode os geradores do "
        "site e faça o commit junto"
    )


def test_temas_do_cnpj_sem_numero_digitado_nem_conversa_interna():
    for tema in vitrine.TEMAS_DO_CNPJ:
        for texto in (tema.titulo, tema.texto):
            assert not re.search(r"\d", texto), tema.chave
            assert not re.search(r"\w+_\w+|\bADR\b|servidor", texto), tema.chave
        assert tema.texto.endswith("."), tema.chave
