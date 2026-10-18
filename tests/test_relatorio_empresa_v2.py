"""Relatórios v2, PR 1 (plano de 17/10/2026): a ficha da empresa ganha leitura.

A ficha inteira da CPFL Energia, montada com dados reais: as demonstrações recortadas dos dados abertos
da CVM (DFP de 2024 e 2025, ITR de 2026), os padrões do setor de energia calculados com as mesmas
demonstrações de todas as companhias (corte de 31/08/2026) e a ficha do dossiê de exemplo.
"""

import json
import re
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pytest

from src import demonstracoes as dm
from src import dossie, notas
from src import o_que_os_dados_mostram as leitura_da_ficha
from src import relatorio_empresa as re_
from src.banco.demonstracoes import DadosDaEmpresa
from src.padroes import INDICADORES

PASTA = Path(__file__).parent / "arquivos" / "cvm" / "cpfl"
CPFL = "02.429.144/0001-93"
SETOR = "Emp. Adm. Part. - Energia Elétrica"
ARQUIVOS = (
    ("dfp_cia_aberta_2024.zip", "DFP"),
    ("dfp_cia_aberta_2025.zip", "DFP"),
    ("itr_cia_aberta_2026.zip", "ITR"),
)
PRECO = 35.0  # um preço fixo, só para os múltiplos saírem
DIA_DA_FICHA = date(2026, 10, 17)
TICKERS = pd.DataFrame(
    {
        "codigo": ["CPFE3"],
        "valor_mobiliario": ["Ações Ordinárias"],
        "atualizado_em": [datetime(2026, 10, 17, 9, tzinfo=UTC)],
    }
)
# as seções feitas das demonstrações: todo número delas compara com algo (nunca "sem comparação")
SECOES_DAS_DEMONSTRACOES = (
    "resultado",
    "retorno",
    "endividamento",
    "caixa",
    "notas_classicas",
    "valuation",
)


def _dados() -> DadosDaEmpresa:
    contas, documentos = [], []
    for arquivo, tipo in ARQUIVOS:
        c, d = dm.ler_demonstracoes((PASTA / arquivo).read_bytes(), tipo)
        contas.append(c[c["cnpj"] == CPFL])
        documentos.append(d[d["cnpj"] == CPFL])
    return DadosDaEmpresa(
        pd.concat(contas).drop(columns="cnpj"), pd.concat(documentos), SETOR
    )


def _padroes() -> tuple[date, pd.DataFrame]:
    bruto = json.loads((PASTA / "padroes_energia.json").read_text(encoding="utf-8"))
    return date.fromisoformat(bruto["corte"]), pd.DataFrame(bruto["padroes"])


@pytest.fixture(scope="module")
def entradas_da_cpfl() -> re_.Entradas:
    ficha = dossie.ler_ficha(dossie.FICHA_DE_EXEMPLO)
    assert ficha is not None
    return re_.Entradas(
        dados=_dados(),
        cnpj=CPFL,
        empresa="CPFL ENERGIA S.A.",
        ticker="CPFE3.SA",
        preco=PRECO,
        padroes=_padroes(),
        tickers=TICKERS,
        dossie=dossie.dossie_da_ficha(dossie.cortar(ficha), DIA_DA_FICHA),
    )


@pytest.fixture(scope="module")
def ficha_da_cpfl(entradas_da_cpfl) -> re_.Relatorio:
    return re_.montar(entradas_da_cpfl, plano="pro")


def _faltas(relatorio: re_.Relatorio) -> list[str]:
    faltas = []
    for secao in relatorio.secoes:
        for item in secao.itens:
            onde = f"{secao.chave}.{item.chave}"
            if item.texto == "—":  # sem número: tem de dizer por quê
                if not item.motivo:
                    faltas.append(f"{onde}: sem número e sem o motivo")
                continue
            falta = item.numero.o_que_falta()
            if falta:
                faltas.append(f"{onde} ({item.texto}): falta {', '.join(falta)}")
    return faltas


def test_todo_numero_tem_data_fonte_e_comparacao(ficha_da_cpfl):
    """O contrato do número: valor, de quando é, de onde veio e contra o quê comparar."""
    assert sum(len(s.itens) for s in ficha_da_cpfl.secoes) > 40
    assert _faltas(ficha_da_cpfl) == []


def test_numeros_das_demonstracoes_sempre_comparam(ficha_da_cpfl):
    """ "Sem comparação" é só para o que não tem par (uma contagem do FRE), nunca para um número
    das demonstrações: esses comparam com o setor, uma faixa, o artigo ou o balanço anterior."""
    for chave in SECOES_DAS_DEMONSTRACOES:
        for item in ficha_da_cpfl.secao(chave).itens:
            if item.texto != "—":
                assert item.comparacao is not None, f"{chave}.{item.chave}"
                assert item.comparacao.contra and item.comparacao.texto


def test_nota_contra_o_setor_compara_com_a_mediana(ficha_da_cpfl):
    roe = next(i for i in ficha_da_cpfl.secao("retorno").itens if i.chave == "roe")
    assert roe.comparacao is not None
    assert "energia" in roe.comparacao.contra.lower()
    assert "31/08/2026" in roe.comparacao.contra
    assert "mediana" in roe.comparacao.texto


def test_sem_plano_pro_o_contrato_vale_igual(entradas_da_cpfl):
    assert _faltas(re_.montar(entradas_da_cpfl)) == []


def test_numero_do_dossie_compara_com_o_ano_ou_o_mes_anterior(ficha_da_cpfl):
    ofertas = ficha_da_cpfl.secao("ofertas_e_fundos")
    fundos = next(i for i in ofertas.itens if i.chave == "fundos_com_a_acao")
    assert fundos.comparacao is not None and "mar/2025" in fundos.comparacao.texto
    assert "CDA" in fundos.fonte


def _itens(relatorio: re_.Relatorio, secao: str) -> dict[str, re_.Item]:
    return {i.chave: i for i in relatorio.secao(secao).itens}


def test_ficha_tecnica_cpfl(ficha_da_cpfl):
    """Quem é a empresa, com de quando e de onde vem cada linha."""
    ficha = _itens(ficha_da_cpfl, "ficha_tecnica")
    assert ficha["nome"].texto == "CPFL ENERGIA S.A."
    assert ficha["nome"].comparacao is not None  # o nome nos documentos mais antigos
    assert ficha["cnpj"].texto == CPFL
    assert ficha["tickers"].texto == "CPFE3 (Ações Ordinárias)"
    assert ficha["tickers"].base == "cadastro de 17/10/2026"
    assert (
        "desde quando" in ficha["tickers"].sem_comparacao
    )  # o que a base ainda não traz
    assert ficha["setor"].texto == SETOR
    assert "Energia elétrica" in ficha["setor"].comparacao.texto
    assert ficha["auditor"].texto == (
        "PRICEWATERHOUSECOOPERS AUDITORES INDEPENDENTES LTDA, desde 01/01/2022"
    )
    assert "KPMG" in ficha["auditor"].comparacao.texto
    assert ficha["controlador"].texto == "—"
    assert "FRE" in ficha["controlador"].motivo
    ultima = ficha["ultima_demonstracao"]
    assert ultima.texto == "ITR de 30/06/2026, versão 1"
    assert ultima.base == "recebido em 13/08/2026"
    assert "44 dias" in ultima.comparacao.texto
    assert "14/08/2026" in ultima.comparacao.texto  # 45 dias depois do trimestre
    datas = {
        linha["fonte"]: linha["data"]
        for linha in ficha_da_cpfl.secao("ficha_tecnica").tabelas["datas_das_fontes"]
    }
    assert datas == {
        "Demonstrações (DFP e ITR na CVM)": "13/08/2026",
        "Padrões do setor": "31/08/2026",
        "Dossiê da base": "17/10/2026",
        "Cadastro de tickers": "17/10/2026",
    }


def test_ficha_tecnica_sem_o_pro_nao_mostra_o_auditor(entradas_da_cpfl):
    ficha = _itens(re_.montar(entradas_da_cpfl), "ficha_tecnica")
    assert ficha["auditor"].texto == "—"
    assert "Pro" in ficha["auditor"].motivo
    assert "Dossiê da base" not in str(
        re_.montar(entradas_da_cpfl).secao("ficha_tecnica").tabelas
    )


def test_ficha_tecnica_prazo_da_dfp_reapresentada():
    documentos = pd.DataFrame(
        {
            "empresa": ["X S.A.", "X S.A."],
            "documento": ["DFP", "DFP"],
            "referencia": [date(2025, 12, 31), date(2025, 12, 31)],
            "versao": [1, 2],
            "recebido_em": [date(2026, 3, 20), date(2026, 5, 4)],
        }
    )
    item = re_.ultima_demonstracao(documentos)
    assert item.texto == "DFP de 31/12/2025, versão 2 (reapresentada)"
    assert item.base == "recebido em 04/05/2026"
    assert "versão 1 recebida em 20/03/2026" in item.comparacao.texto
    assert "31/03/2026" in item.comparacao.texto  # 3 meses depois do exercício


# --- o que os dados mostram -----------------------------------------------------------------------
PROIBIDAS = (
    "compre",
    "venda",
    "alvo",
    "vai",
)  # palavras inteiras ("vendas" é conta, passa)
RAIZ_PROIBIDA = "recomend"  # recomendo, recomendação...
PROIBIDAS_EM_FRASE = ("deve subir",)


def _palavras(texto: str) -> list[str]:
    return re.findall(r"\w+", texto.lower())


def _recomenda(texto: str) -> list[str]:
    achadas = [
        p for p in _palavras(texto) if p in PROIBIDAS or p.startswith(RAIZ_PROIBIDA)
    ]
    return achadas + [f for f in PROIBIDAS_EM_FRASE if f in texto.lower()]


def test_o_que_os_dados_mostram_sem_recomendacao(ficha_da_cpfl):
    secao = ficha_da_cpfl.secao("o_que_os_dados_mostram")
    fortes = [p for p in secao.pontos if p.lado == leitura_da_ficha.FORTE]
    atencao = [p for p in secao.pontos if p.lado == leitura_da_ficha.ATENCAO]
    assert 3 <= len(fortes) <= 5 and 3 <= len(atencao) <= 5
    for ponto in secao.pontos:
        assert ponto.numero and ponto.medido_em and ponto.tabela, ponto
        assert _recomenda(ponto.texto) == [], ponto.texto
    textos = " ".join(p.texto for p in secao.pontos)
    assert "ROE" in textos  # ótimo contra o setor
    assert "Altman" in textos  # zona cinzenta do artigo
    assert "fundos" in textos  # 370 contra 455 um ano antes


def test_o_que_os_dados_mostram_vem_das_regras(ficha_da_cpfl):
    """Cada ponto sai de uma regra fixa, com o número, a data e a tabela do item de origem."""
    secao = ficha_da_cpfl.secao("o_que_os_dados_mostram")
    roe = next(p for p in secao.pontos if p.indicador == "roe")
    assert roe.lado == leitura_da_ficha.FORTE
    assert roe.numero == "26,4%"
    assert "DFP e ITR" in roe.tabela
    divida = next(p for p in secao.pontos if p.indicador == "divida_sobre_pl")
    assert (
        divida.lado == leitura_da_ficha.ATENCAO
    )  # subiu de 1,07× para 1,21× (menor é melhor)
    assert "1,07×" in divida.texto


def test_palavras_proibidas_pegam_recomendacao():
    assert _recomenda("Compre agora: preço-alvo de R$ 40") == ["compre", "alvo"]
    assert _recomenda("A ação deve subir") == ["deve subir"]
    assert (
        _recomenda("Receita de vendas cresceu") == []
    )  # "vendas" é conta, não conselho


def test_sem_numeros_nao_inventa_pontos():
    vazio = leitura_da_ficha.pontos([], [])
    assert vazio == []


def _secao_com_pontos():
    from src import o_que_os_dados_mostram as leitura_da_ficha
    from src.relatorio_empresa import Secao
    from telas.research.relatorio_empresa import _mostrar_secao

    ponto = leitura_da_ficha.Ponto(
        leitura_da_ficha.ATENCAO,
        "Altman Z'' de 1,89.",
        "1,89",
        "DFP de 2025",
        "DFP",
        "altman",
    )
    _mostrar_secao(
        Secao("o_que_os_dados_mostram", "O que os dados mostram", pontos=[ponto])
    )


def test_tela_mostra_os_pontos_com_a_fonte():
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_function(_secao_com_pontos).run()
    assert not app.exception
    textos = [m.value for m in app.markdown]
    assert "**Pontos de atenção**" in textos
    assert "- Altman Z'' de 1,89. Fonte: DFP." in textos
    assert (
        "**Pontos fortes nos dados**" not in textos
    )  # lado sem ponto não aparece vazio


def test_pdf_mostra_os_pontos(ficha_da_cpfl):
    from src.relatorio_empresa_pdf import relatorio_da_empresa

    assert relatorio_da_empresa(ficha_da_cpfl).startswith(b"%PDF")


def test_api_leva_os_pontos(ficha_da_cpfl):
    from src.api_v1.esquemas import de_relatorio_da_empresa

    api = de_relatorio_da_empresa(ficha_da_cpfl)
    secao = next(s for s in api.secoes if s.chave == "o_que_os_dados_mostram")
    assert len(secao.pontos) >= 6 and all(p.tabela for p in secao.pontos)


# --- o que mudaria esta leitura -------------------------------------------------------------------
PERCENTIS = {
    "20": 0.05,
    "25": 0.06,
    "40": 0.09,
    "50": 0.11,
    "60": 0.14,
    "75": 0.18,
    "80": 0.20,
}


def _nota(valor: float, indicador: str = "roe") -> notas.Nota:
    maior = INDICADORES[indicador][1]
    return notas.Nota(
        indicador, indicador, valor, notas.qualidade(valor, PERCENTIS, maior), "energia", 100,
        PERCENTIS, date(2026, 8, 31),
    )  # fmt: skip


@pytest.mark.parametrize(
    ("valor", "indicador", "sobe", "cai"),
    [
        (0.10, "roe", (0.14, "bom"), (0.09, "ruim")),  # médio: entre p40 e p60
        (0.26, "roe", None, (0.20, "bom")),  # ótimo: só pode cair
        (0.01, "roe", (0.05, "ruim"), None),  # péssimo: só pode subir
    ],
)
def test_gatilhos_das_notas(valor, indicador, sobe, cai):
    """Para cada nota, o valor que muda a faixa (o quintil vizinho do setor), sem previsão."""
    gatilhos = notas.gatilhos(_nota(valor, indicador), INDICADORES[indicador][1])
    por_sentido = {g.sentido: (g.limite, g.nota) for g in gatilhos}
    assert por_sentido.get(notas.SOBE) == sobe
    assert por_sentido.get(notas.CAI) == cai
    for g in gatilhos:  # cruzar o limite dá mesmo a nota anunciada
        passo = 1e-9 if g.sentido == notas.SOBE else -1e-9
        cruzado = g.limite if g.inclusive else g.limite + passo
        assert notas.qualidade(cruzado, PERCENTIS, INDICADORES[indicador][1]) == g.nota


def test_gatilhos_quando_menor_e_melhor():
    """Dívida / patrimônio: subir piora a nota e cair melhora."""
    gatilhos = notas.gatilhos(_nota(0.10, "divida_sobre_pl"), False)  # médio
    por_sentido = {g.sentido: (g.limite, g.nota) for g in gatilhos}
    assert por_sentido == {notas.SOBE: (0.14, "ruim"), notas.CAI: (0.09, "bom")}
    for g in gatilhos:
        passo = 1e-9 if g.sentido == notas.SOBE else -1e-9
        cruzado = g.limite if g.inclusive else g.limite + passo
        assert notas.qualidade(cruzado, PERCENTIS, False) == g.nota


def test_o_que_mudaria_esta_leitura_cpfl(ficha_da_cpfl):
    secao = ficha_da_cpfl.secao("o_que_mudaria")
    linhas = {linha["indicador"]: linha for linha in secao.tabelas["gatilhos"]}
    roe = linhas["ROE (retorno sobre o patrimônio)"]
    assert roe["hoje"] == "26,4% (ótimo)"
    assert roe["se_subir"] == "—"  # já está no topo
    assert re.fullmatch(
        r"abaixo de \d+,\d%( \(colado no valor de hoje\))?: bom", roe["se_cair"]
    )
    assert "Energia elétrica" in roe["comparado_com"]
    altman = linhas["Altman Z''"]
    assert altman["se_subir"] == "acima de 2,60: segura"
    assert altman["se_cair"] == "abaixo de 1,10: de aflição"
    assert "não é previsão" in " ".join(secao.paragrafos).lower()
    assert all(
        _recomenda(" ".join(linha.values())) == []
        for linha in secao.tabelas["gatilhos"]
    )


# --- Tarefa 5: a ordem do molde A e os limites ------------------------------------------------------
ORDEM_V2 = [
    "ficha_tecnica",
    "o_que_os_dados_mostram",
    "o_que_mudou",
    "resultado",
    "retorno",
    "endividamento",
    "caixa",
    "qualidade",
    "dividendos",
    "ofertas_e_fundos",
    "auditor_e_controladas",
    "pares",
    "setor_regulado",
    "eventos",
    "negocios",
    "notas_classicas",
    "padroes_e_notas",
    "valuation",
    "historico",
    "o_que_mudaria",
    "metodologia",
    "limites",
]


@pytest.mark.parametrize("plano", ["pro", None])
def test_ordem_das_secoes_v2(entradas_da_cpfl, plano):
    """A ordem do molde A (pesquisa de mercado de 10/2026): quem é, o que os dados mostram e o que
    mudou no topo; as contas; capital, governança, setor e eventos; notas, valuation e histórico;
    o que mudaria, metodologia e limites no fim. Com ou sem o Pro, a mesma ordem."""
    relatorio = re_.montar(entradas_da_cpfl, plano)
    assert [s.chave for s in relatorio.secoes] == ORDEM_V2
    assert list(re_.SECOES) == [c for c in ORDEM_V2 if c in re_.SECOES]
    assert "resumo" not in re_.SECOES  # "O que os dados mostram" tomou o lugar dele


def test_secao_da_base_desconhecida_vai_com_os_eventos():
    secoes = [re_.Secao(c, c) for c in ("limites", "nova_da_base", "ficha_tecnica")]
    assert [s.chave for s in re_.na_ordem(secoes)] == [
        "ficha_tecnica",
        "nova_da_base",
        "limites",
    ]


def test_limites_dizem_o_que_nao_temos(ficha_da_cpfl):
    secao = ficha_da_cpfl.secao("limites")
    assert secao.titulo == "Limites e perguntas em aberto"
    texto = " ".join(secao.paragrafos)
    for falta in ("protestos", "processos", "pagamentos"):
        assert falta in texto
    assert "Nada aqui é recomendação" in texto  # os cuidados de antes continuam
    abertas = [p for p in secao.paragrafos if p.startswith(re_.EM_ABERTO)]
    # o que a ficha mostrou como "—" vira pergunta, uma por motivo e sem repetir
    assert any("Controlador" in p and "FRE" in p for p in abertas)
    crescimento = [p for p in abertas if "Crescimento da receita" in p]
    assert len(crescimento) == 1 and "Crescimento do lucro" in crescimento[0]
    assert len(abertas) == len(set(abertas))


def test_perguntas_em_aberto_nao_repetem_a_tranca_do_plano(entradas_da_cpfl):
    limites = re_.montar(entradas_da_cpfl, None).secao("limites")
    assert not any(
        "Pro" in p for p in limites.paragrafos if p.startswith(re_.EM_ABERTO)
    )


def test_metodologia_vem_recolhida(ficha_da_cpfl):
    assert ficha_da_cpfl.secao("metodologia").recolhida
    assert not ficha_da_cpfl.secao("resultado").recolhida


def _secao_recolhida():
    from src.relatorio_empresa import Item, Secao
    from telas.research.relatorio_empresa import _mostrar_secao

    nota = Item("roe", "ROE", "26,4%", 0.264, "%", "12 meses", nota="ótimo",
                nota_texto="Acima de 80% das empresas do setor.")  # fmt: skip
    _mostrar_secao(Secao("resultado", "Resultado", itens=[nota]))
    _mostrar_secao(
        Secao(
            "metodologia",
            "Metodologia e fontes",
            paragrafos=["Fórmulas."],
            recolhida=True,
        )
    )


def test_tela_recolhe_as_explicacoes():
    """O corpo fica sóbrio: a explicação da nota vai no (?) do número e a metodologia, fechada."""
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_function(_secao_recolhida).run()
    assert not app.exception
    assert "Acima de 80%" in app.metric[0].help
    assert not any("Acima de 80%" in c.value for c in app.caption)
    assert [e.label for e in app.expander] == ["Ver a explicação"]
    assert app.expander[0].markdown[0].value == "Fórmulas."


def test_api_leva_a_ordem_e_a_secao_recolhida(ficha_da_cpfl):
    from src.api_v1.esquemas import de_relatorio_da_empresa

    api = de_relatorio_da_empresa(ficha_da_cpfl)
    assert [s.chave for s in api.secoes] == ORDEM_V2
    assert [s.chave for s in api.secoes if s.recolhida] == ["metodologia"]
