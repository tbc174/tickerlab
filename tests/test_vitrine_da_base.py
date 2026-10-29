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

from base import vitrine
from base.contrato import PASTA
from base.dossie import conferir_sem_pessoas, normalizar_nome

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
    "JOAO DA SILVA",
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


def _mundo_falso() -> dict[str, pd.DataFrame]:
    """Alfa troca de auditor e refaz o lucro de 2020 no balanço de 2021 (de 100 para 90 milhões); Beta
    troca também e não refaz nada. Gama é controlada da Alfa e emite uma oferta em 2025; Delta é só
    coligada."""
    demonstracoes = pd.DataFrame(
        [
            _lucro(ALFA, "2020-12-31", 100, "2020-12-31"),
            _lucro(ALFA, "2021-12-31", 200, "2021-12-31"),
            _lucro(ALFA, "2020-12-31", 90, "2021-12-31", ordem="penultimo"),
            _lucro(ALFA, "2022-12-31", 300, "2022-12-31"),
            _lucro(BETA, "2020-12-31", 50, "2020-12-31"),
            _lucro(BETA, "2021-12-31", 60, "2021-12-31"),
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
    registros = pd.to_datetime(
        [
            "2025-05-01",
            "2025-08-01",
            "2025-09-01",
            "2025-10-01",
            "2024-03-01",
            "2025-11-01",
        ]
    )
    ofertas = pd.DataFrame(
        {
            "cnpj_emissor": [ALFA, GAMA_CONTROLADA, DELTA, ALFA, ALFA, ALFA],
            "nome_emissor": [
                "ALFA ENERGIA S.A.",
                "GAMA TRANSMISSORA S.A.",
                "DELTA PAPEL S.A.",
                "ALFA ENERGIA S.A.",
                "ALFA ENERGIA S.A.",
                "ALFA ENERGIA S.A.",
            ],
            "administrador": ["JOAO DA SILVA"] * 6,
            "valor_mobiliario": ["Debêntures"] * 5
            + ["Certificados de Recebíveis Imobiliários"],
            "data_registro": registros,
            "status_requerimento": [
                "Oferta Encerrada",
                "Registro Concedido",
                "Oferta Encerrada",
                "Oferta Revogada",
                "Oferta Encerrada",
                "Oferta Encerrada",
            ],
            "valor_total_registrado": [500e6, 200e6, 100e6, 999e6, 300e6, 50e6],
            "publico_em": registros,
        }
    )
    controladas = pd.DataFrame(
        {
            "cnpj_companhia": ["11111111000111", "11111111000111"],
            "companhia": ["ALFA ENERGIA S.A.", "ALFA ENERGIA S.A."],
            "cnpj": ["33333333000133", "44444444000144"],
            "razao_social": ["GAMA TRANSMISSORA S.A.", "DELTA PAPEL S.A."],
            "tipo": ["controlada", "coligada"],
            "publico_em": pd.to_datetime(["2025-06-01", "2025-06-01"]),
        }
    )
    return {
        vitrine.DEMONSTRACOES: demonstracoes,
        vitrine.TROCAS_DE_AUDITOR: trocas,
        vitrine.OFERTAS: ofertas,
        vitrine.CONTROLADAS: controladas,
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

    def distintos(self, tabela: str, coluna: str) -> set[object]:
        return set(self.tabelas[tabela][coluna].dropna())


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


def test_ofertas_do_grupo_no_ultimo_ano_completo():
    assert _cruzamentos().ofertas == vitrine.OfertasDoGrupo(
        ano=2025,
        ofertas=3,  # a revogada, a de 2024 e o CRI (da securitização) ficam de fora
        valor=800e6,
        do_grupo=2,  # Alfa e a controlada Gama; a Delta é só coligada
        valor_do_grupo=700e6,
        grupos=1,
        por_controlada=1,
        valor_por_controlada=200e6,
    )


def test_cruzamentos_recusam_tabela_fora_do_catalogo():
    catalogo = _catalogo_com(
        vitrine.DEMONSTRACOES, vitrine.TROCAS_DE_AUDITOR, vitrine.OFERTAS
    )
    with pytest.raises(ValueError, match="controladas"):
        vitrine.medir_cruzamentos(_PortaQueLe(_mundo_falso()), catalogo, DIA_DA_MEDICAO)


def test_fatos_agregados_tem_fonte_e_data():
    fatos = vitrine.fatos_agregados(_cruzamentos())
    assert [f.chave for f in fatos] == ["lucros", "auditor", "ofertas"]
    for fato in fatos:
        assert fato.texto and fato.numero and fato.como_foi_calculado
        assert fato.fonte.startswith("CVM")
        assert fato.tabelas and set(fato.tabelas) <= set(
            vitrine.TABELAS_DOS_CRUZAMENTOS
        )
        assert fato.data == "2026-10-26"
    assert fatos[0].numero == "33,3%"
    assert "1 de 2 companhias" in fatos[0].texto


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
    fatos = exp.conteudo()["fatos_da_base"]

    cruzamentos = vitrine.cruzamentos_da_fotografia(fotografia)
    assert fatos["fatos"] == [asdict(f) for f in vitrine.fatos_agregados(cruzamentos)]
    assert fatos["medido_em_curto"] == vitrine.dia_e_mes(fotografia["medido_em"])


def test_fotografia_dos_cruzamentos_volta_igual():
    cruzamentos = _cruzamentos()
    assert vitrine.cruzamentos_da_fotografia(asdict(cruzamentos)) == cruzamentos
