"""A vitrine da base: o catálogo de contratos vira as fontes, os módulos e as tabelas que o site mostra
(plano do site para quem analisa, 18/10/2026, PR 3, tarefa 4).

Funções puras sobre o dicionário do `catalogo.json`; nenhum número da página é digitado à mão.
"""

import json
import re
from datetime import date

import pytest

from base import vitrine
from base.contrato import PASTA

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
    return json.loads((PASTA / "catalogo.json").read_text(encoding="utf-8"))


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
    assert [t.tabela for t in linhas] == ["a", "b", "c"]  # a ordem do catálogo


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
        assert (SITE / vaga.link.lstrip("/")).is_file(), vaga.link


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
    from dataclasses import asdict

    from scripts import exportar_conteudo as exp

    assert exp.conteudo()["vitrine"] == [asdict(v) for v in vitrine.VAGAS_DA_VITRINE]
