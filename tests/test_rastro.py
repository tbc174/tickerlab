"""O rastro de todo número do relatório da empresa (B-02; item 7 do lançamento: "como foi calculado"
em um clique). Todo número devolve a fórmula, a versão do cálculo, a fonte (o id da coleta, que leva a
licença) e quando o documento usado ficou público; o gabarito fixa cada indicador da WEG real das
amostras, para que mudar uma fórmula sem subir a versão quebre aqui."""

import json
from dataclasses import asdict, replace
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from src import demonstracoes as dm
from src import fundamentalista, fundamentos, notas_classicas
from src import relatorio_empresa as re_
from src.api_v1.esquemas import de_relatorio_da_empresa
from src.banco.coletas import LICENCAS
from src.banco.demonstracoes import DadosDaEmpresa
from src.rastro import (
    FONTE,
    FORMULA,
    PUBLICADO_EM,
    VERSAO,
    DocumentoUsado,
    Entrada,
    Rastro,
    como_foi_calculado,
    nome_do_documento,
)

PASTA = Path(__file__).parent / "arquivos" / "cvm" / "fundamentos"
GABARITO = Path(__file__).parent / "arquivos" / "rastro" / "weg.json"
WEG = "84.429.695/0001-11"
DFP_DE_2025_RECEBIDA = date(
    2026, 2, 25
)  # o recebido_em da DFP de 2025 da WEG na amostra
ULTIMO_FECHAMENTO = date(2026, 10, 16)


@pytest.fixture(scope="module")
def dados_da_weg():
    return _ler_a_weg()


def _ler_a_weg(com_o_itr: bool = False) -> DadosDaEmpresa:
    """A WEG das DFPs de 2024 e 2025; com o ITR de 2026, os 12 meses passam a ir até 30/06/2026."""
    partes, documentos = [], []
    arquivos = [("dfp_cia_aberta_2024.zip", "DFP"), ("dfp_cia_aberta_2025.zip", "DFP")]
    if com_o_itr:
        arquivos.append(("itr_cia_aberta_2026.zip", "ITR"))
    for arquivo, tipo in arquivos:
        contas, docs = dm.ler_demonstracoes((PASTA / arquivo).read_bytes(), tipo)
        partes.append(contas[contas["cnpj"] == WEG])
        documentos.append(docs[docs["cnpj"] == WEG])
    return DadosDaEmpresa(
        contas=pd.concat(partes).drop(columns="cnpj"),
        documentos=pd.concat(documentos),
        setor="Máquinas, Equipamentos, Veículos e Peças",
    )


def _entradas(dados, **outros):
    fechamentos = pd.Series(
        [49.0, 50.0], index=pd.to_datetime([date(2026, 10, 15), ULTIMO_FECHAMENTO])
    )
    campos = {"dados": dados, "cnpj": WEG, "empresa": "WEG S.A.", "ticker": "WEGE3.SA",
              "preco": 50.0, "fechamentos": fechamentos}  # fmt: skip
    return re_.Entradas(**(campos | outros))


def _numeros(relatorio: re_.Relatorio) -> dict[str, re_.Item]:
    """Os itens que são número (não frase), de todas as seções."""
    return {
        i.chave: i for s in relatorio.secoes for i in s.itens if i.unidade != re_.TEXTO
    }


# --- o contrato ------------------------------------------------------------------------------------
def _completo(**mudar) -> Rastro:
    documento = DocumentoUsado(
        "DFP de 31/12/2025, versão 1", date(2026, 2, 25), "https://x"
    )
    campos = {"formula": "lucro ÷ receita", "versao_do_calculo": "fundamentos 2",
              "fonte_id": "cvm", "publicado_em": date(2026, 2, 25), "documentos": (documento,)}  # fmt: skip
    return Rastro(**(campos | mudar))


def test_rastro_completo_nao_tem_o_que_faltar():
    assert _completo().o_que_falta() == []


def test_rastro_diz_cada_parte_que_falta():
    falta = _completo(formula="", versao_do_calculo="", fonte_id="", publicado_em=None)
    assert falta.o_que_falta() == [FORMULA, VERSAO, FONTE, PUBLICADO_EM]


def test_publicado_em_e_o_documento_mais_recente():
    documentos = (
        DocumentoUsado("DFP de 31/12/2025, versão 1", date(2026, 2, 25)),
        DocumentoUsado("ITR de 30/06/2026, versão 1", date(2026, 8, 1)),
        DocumentoUsado("fechamento sem data", None),
    )
    rastro = Rastro.dos_documentos("x", "fundamentos 2", "cvm", documentos)
    assert rastro.publicado_em == date(2026, 8, 1)
    assert Rastro.dos_documentos("x", "v", "cvm", ()).publicado_em is None


# --- o "como foi calculado" para quem lê ------------------------------------------------------------
def test_como_foi_calculado_mostra_cada_parte_e_o_documento_com_link():
    linhas = como_foi_calculado(_completo(outras_fontes=("yahoo",)))
    assert [(linha.rotulo, linha.texto, linha.url) for linha in linhas] == [
        ("Fórmula", "lucro ÷ receita", ""),
        ("Versão do cálculo", "fundamentos 2", ""),
        ("Fonte", "cvm (também yahoo)", ""),
        ("Publicado em", "25/02/2026", ""),
        (
            "Documento",
            "DFP de 31/12/2025, versão 1, publicado em 25/02/2026",
            "https://x",
        ),
    ]


def test_como_foi_calculado_diz_quando_o_dia_nao_e_conhecido():
    sem_dia = DocumentoUsado("fechamento de WEGE3.SA (Yahoo Finance)", None)
    linhas = como_foi_calculado(_completo(publicado_em=None, documentos=(sem_dia,)))
    textos = {linha.rotulo: linha.texto for linha in linhas}
    assert textos["Publicado em"] == "dia não conhecido"
    assert textos["Documento"] == (
        "fechamento de WEGE3.SA (Yahoo Finance) (dia da publicação não conhecido)"
    )


def _entrada(conta: str, codigo: str, nome: str, valor: float, periodo: str) -> Entrada:
    return Entrada(conta, codigo, nome, valor, periodo, "DFP", date(2025, 12, 31), 1,
                   DFP_DE_2025_RECEBIDA)  # fmt: skip


def test_como_foi_calculado_mostra_as_contas_usadas_com_o_valor_e_o_documento():
    entradas = (
        _entrada("receita", "3.01", "Receita de Venda de Bens e/ou Serviços",
                 40_804_110_000.0, "exercicio"),
        _entrada("caixa", "1.01.01 ou 1.01", "Caixa e Equivalentes de Caixa", 1_500.4, "posicao"),
        _entrada("acoes_total", "QT_ACAO_TOTAL_CAP_INTEGR",
                 "Composição do capital: ações do capital integralizado", 4_197_317_998.0, "posicao"),
        _entrada("lpa_basico", "3.99.01.xx", "Lucro Básico por Ação (a 1ª classe com valor)",
                 1.5234, "acumulado"),
        _entrada("fco", "6.01", "Caixa Líquido das Atividades Operacionais", -2_000.0,
                 "acumulado_anterior"),
    )  # fmt: skip
    linhas = como_foi_calculado(_completo(entradas=entradas))
    abertura, *contas = linhas[5:]
    assert abertura.rotulo == "Contas usadas"
    assert abertura.texto == (
        "as linhas da demonstração que entram no número, com o valor guardado: com elas, "
        "dá para refazer a conta."
    )
    assert {linha.rotulo for linha in contas} == {"Conta"}
    doc = "(DFP de 31/12/2025, versão 1)"
    assert [linha.texto for linha in contas] == [
        ("Receita de Venda de Bens e/ou Serviços (código 3.01 na CVM): "
         f"R$ 40.804.110.000 no exercício {doc}"),
        ("Caixa e Equivalentes de Caixa (código 1.01.01 ou 1.01 na CVM): R$ 1.500 "
         f"no saldo do balanço {doc}"),
        ("Composição do capital: ações do capital integralizado (campo "
         f"QT_ACAO_TOTAL_CAP_INTEGR na CVM): 4.197.317.998 ações no saldo do balanço {doc}"),
        ("Lucro Básico por Ação (a 1ª classe com valor) (código 3.99.01.xx na CVM): "
         f"R$ 1,52 por ação no acumulado do ano {doc}"),
        ("Caixa Líquido das Atividades Operacionais (código 6.01 na CVM): R$ -2.000 "
         f"no acumulado do mesmo período do ano anterior {doc}"),
    ]  # fmt: skip


def test_sem_entradas_o_como_foi_calculado_nao_fala_de_contas():
    rotulos = [linha.rotulo for linha in como_foi_calculado(_completo())]
    assert "Contas usadas" not in rotulos and "Conta" not in rotulos


def test_toda_conta_guardada_e_todo_periodo_tem_texto():
    """Conta nova em `CONTAS_DA_CVM` ou período novo de `src/demonstracoes.py` sem texto quebra aqui."""
    for conta, (codigo, nome) in dm.CONTAS_DA_CVM.items():
        for periodo in (dm.EXERCICIO, dm.POSICAO, dm.ACUMULADO, dm.ACUMULADO_ANTERIOR):
            entrada = _entrada(conta, codigo, nome, 1.0, periodo)
            texto = como_foi_calculado(_completo(entradas=(entrada,)))[-1].texto
            assert texto.startswith(f"{nome} (") and "None" not in texto


# --- as fórmulas ficam ao lado do código que calcula -----------------------------------------------
def test_todo_indicador_calculado_tem_formula(dados_da_weg):
    tela = fundamentos.calcular(dados_da_weg, 50.0).indicadores
    extra = fundamentalista.calcular(dados_da_weg).indicadores
    assert set(tela) == set(fundamentos.FORMULAS)
    assert set(extra) == set(fundamentalista.FORMULAS) - {
        *fundamentalista.DOS_DIVIDENDOS,
        *fundamentalista.DA_COMPOSICAO_DO_CAPITAL,
    }
    assert all(fundamentos.FORMULAS.values()) and all(fundamentalista.FORMULAS.values())


def test_notas_classicas_tem_versao():
    assert notas_classicas.VERSAO_DAS_NOTAS_CLASSICAS


# --- todo número do relatório tem o rastro inteiro -------------------------------------------------
def test_todo_numero_do_relatorio_tem_o_rastro_inteiro(dados_da_weg):
    numeros = _numeros(re_.montar(_entradas(dados_da_weg)))
    assert (
        len(numeros) > 30
    )  # os indicadores da tela, os novos, as notas, o valuation e os dividendos
    sem_rastro = {
        c: i.rastro.o_que_falta() if i.rastro else ["rastro"]
        for c, i in numeros.items()
    }
    assert {c: f for c, f in sem_rastro.items() if f} == {}


def test_fonte_do_rastro_e_uma_coleta_com_licenca(dados_da_weg):
    for item in _numeros(re_.montar(_entradas(dados_da_weg))).values():
        assert item.rastro is not None
        assert {item.rastro.fonte_id, *item.rastro.outras_fontes} <= set(LICENCAS)


def test_publicado_em_e_a_entrega_da_dfp_nao_a_data_do_balanco(dados_da_weg):
    receita = _numeros(re_.montar(_entradas(dados_da_weg)))["receita"]
    assert receita.rastro is not None
    assert receita.rastro.publicado_em == DFP_DE_2025_RECEBIDA
    (documento,) = receita.rastro.documentos
    assert documento.nome == "DFP de 31/12/2025, versão 1"
    assert documento.url.startswith("https://www.rad.cvm.gov.br/")


def test_numero_com_preco_cita_o_yahoo_e_o_dia_do_fechamento(dados_da_weg):
    numeros = _numeros(re_.montar(_entradas(dados_da_weg)))
    for chave in ("p_l", "p_vp", "valor_de_mercado", "dividend_yield"):
        rastro = numeros[chave].rastro
        assert rastro is not None
        assert rastro.fonte_id == "cvm" and rastro.outras_fontes == ("yahoo",)
        fechamento = rastro.documentos[-1]
        assert (
            fechamento.publicado_em == ULTIMO_FECHAMENTO and "WEGE3" in fechamento.nome
        )
        assert rastro.publicado_em == ULTIMO_FECHAMENTO  # o insumo mais novo é o preço
    assert numeros["receita"].rastro.outras_fontes == ()  # type: ignore[union-attr]


def test_preco_sem_fechamentos_fica_sem_dia_e_o_rastro_segue_pela_dfp(dados_da_weg):
    p_l = _numeros(re_.montar(_entradas(dados_da_weg, fechamentos=None)))["p_l"].rastro
    assert p_l is not None and p_l.documentos[-1].publicado_em is None
    assert p_l.publicado_em == DFP_DE_2025_RECEBIDA


def test_crescimento_e_notas_classicas_citam_as_dfps_dos_anos_usados(dados_da_weg):
    numeros = _numeros(re_.montar(_entradas(dados_da_weg)))
    piotroski = numeros["piotroski"].rastro
    assert piotroski is not None
    assert [d.nome for d in piotroski.documentos] == [
        "DFP de 31/12/2024, versão 1",
        "DFP de 31/12/2025, versão 1",
    ]
    assert piotroski.formula == notas_classicas.PIOTROSKI_FORMULA
    assert piotroski.versao_do_calculo.startswith("notas clássicas ")
    crescimento = numeros["crescimento_receita"].rastro
    assert crescimento is not None and len(crescimento.documentos) == 2


def test_numero_indisponivel_tambem_diz_como_seria_calculado(dados_da_weg):
    sem_preco = _numeros(
        re_.montar(_entradas(dados_da_weg, preco=None, fechamentos=None))
    )
    p_l = sem_preco["p_l"]
    assert p_l.valor is None and p_l.rastro is not None and p_l.rastro.formula


def test_rastro_vai_no_json_e_na_api(dados_da_weg):
    relatorio = re_.montar(_entradas(dados_da_weg))
    texto = json.dumps(relatorio.como_dict(), ensure_ascii=False)
    assert '"publicado_em": "2026-02-25"' in texto
    api = de_relatorio_da_empresa(relatorio)
    receita = next(i for s in api.secoes for i in s.itens if i.chave == "receita")
    assert receita.rastro is not None and receita.rastro.fonte_id == "cvm"
    original = next(
        i for s in relatorio.secoes for i in s.itens if i.chave == "receita"
    )
    assert original.rastro is not None
    assert [linha.model_dump() for linha in receita.rastro.linhas] == [
        asdict(linha) for linha in como_foi_calculado(original.rastro)
    ]  # o app novo mostra o mesmo texto da página e do PDF


def test_metricas_do_relatorio(dados_da_weg):
    relatorio = re_.montar(_entradas(dados_da_weg))
    metricas = relatorio.metricas()
    receita = next(m for m in metricas if m.chave == "receita")
    item = _numeros(relatorio)["receita"]
    assert (receita.entidade_id, receita.periodo, receita.valor) == (
        WEG,
        item.base,
        item.valor,
    )
    assert receita.rastro == item.rastro
    assert len({m.chave for m in metricas}) == len(
        metricas
    )  # um indicador, uma métrica
    texto = json.dumps([m.como_dict() for m in metricas], ensure_ascii=False)
    assert '"publicado_em": "2026-02-25"' in texto


def test_secao_trancada_nao_devolve_metrica():
    item = re_.Item("a", "A", "1", 1.0, "reais", "", rastro=_completo())
    trancada = re_.Secao("auditor_e_controladas", "x", [item], trancada=True)
    relatorio = re_.Relatorio("E", WEG, "X", "s", "g", [trancada], (), "", False)
    assert relatorio.metricas() == []


# --- as entradas: as contas da DFP e do ITR que entram em cada número ------------------------------
def _documento_da(entrada: Entrada) -> str:
    return nome_do_documento(entrada.documento, entrada.referencia, entrada.versao)


def _so_as_entradas(
    dados: DadosDaEmpresa, entradas: tuple[Entrada, ...]
) -> DadosDaEmpresa:
    """A empresa só com as linhas das entradas, como a tabela de contas guardada as teria."""
    linhas = [
        {"documento": e.documento, "referencia": e.referencia, "versao": e.versao,
         "periodo": e.periodo, "inicio": None, "fim": e.referencia, "conta": e.conta,
         "valor": e.valor}
        for e in entradas
    ]  # fmt: skip
    contas = pd.DataFrame(linhas, columns=dados.contas.columns)
    return replace(dados, contas=contas, documentos=dados.documentos.iloc[0:0])


@pytest.mark.parametrize("com_o_itr", [False, True], ids=["so_a_dfp", "com_o_itr"])
def test_as_entradas_refazem_cada_indicador_dos_fundamentos(com_o_itr, monkeypatch):
    """Quem confere o número refaz a conta: só com as linhas das entradas, o cálculo dá o mesmo.
    (Banco ou não sai do setor e da DRE inteira; aqui fica o da WEG, que não é banco.)"""
    dados = _ler_a_weg(com_o_itr)
    numeros = {
        chave: item
        for chave, item in _numeros(re_.montar(_entradas(dados))).items()
        if chave in fundamentos.FORMULAS and item.valor is not None
    }
    assert len(numeros) > 20
    monkeypatch.setattr(fundamentos, "e_financeira", lambda *_: False)
    for chave, item in numeros.items():
        assert item.rastro is not None and item.rastro.entradas, chave
        refeito = fundamentos.calcular(
            _so_as_entradas(dados, item.rastro.entradas), 50.0
        )
        assert refeito[chave].valor == pytest.approx(item.valor, rel=1e-12), chave


# os dividendos e as ações em circulação saem de `dividendos_e_diluicao` e `acoes_por_especie`
_FORA_DE_CALCULAR = (
    *fundamentalista.DOS_DIVIDENDOS,
    *fundamentalista.DA_COMPOSICAO_DO_CAPITAL,
)


@pytest.mark.parametrize("com_o_itr", [False, True], ids=["so_a_dfp", "com_o_itr"])
def test_as_entradas_refazem_cada_indicador_do_fundamentalista(com_o_itr, monkeypatch):
    dados = _ler_a_weg(com_o_itr)
    numeros = {
        chave: item
        for chave, item in _numeros(re_.montar(_entradas(dados))).items()
        if chave in fundamentalista.CONTAS_DOS_INDICADORES
        and chave not in _FORA_DE_CALCULAR
        and item.valor is not None
    }
    assert len(numeros) > 15
    monkeypatch.setattr(fundamentalista, "e_financeira", lambda *_: False)
    for chave, item in numeros.items():
        assert item.rastro is not None and item.rastro.entradas, chave
        refeito = fundamentalista.calcular(_so_as_entradas(dados, item.rastro.entradas))
        assert refeito[chave].valor == pytest.approx(item.valor, rel=1e-12), chave


def test_o_saldo_medio_cita_o_balanco_e_o_de_um_ano_antes(dados_da_weg):
    """O prazo de recebimento usa a média entre 31/12/2025 e 31/12/2024: as duas DFPs entram."""
    pmr = fundamentalista.todas_as_entradas(dados_da_weg)["pmr"]
    receber = [e.referencia for e in pmr if e.conta == "contas_a_receber"]
    assert receber == [date(2025, 12, 31), date(2024, 12, 31)]
    assert {e.conta for e in pmr} == {"contas_a_receber", "receita"}


def test_o_saldo_medio_sem_o_ano_antes_cita_so_o_fim():
    """Com o ITR de 30/06/2026 e sem o de 30/06/2025, o prazo usa o saldo do fim (como o texto diz)."""
    pmr = fundamentalista.todas_as_entradas(_ler_a_weg(com_o_itr=True))["pmr"]
    receber = [
        (e.documento, e.referencia) for e in pmr if e.conta == "contas_a_receber"
    ]
    assert receber == [("ITR", date(2026, 6, 30))]


def _dos_dividendos_e_do_capital(dados: DadosDaEmpresa) -> dict[str, float | None]:
    d = fundamentalista.dividendos_e_diluicao(dados)
    return {
        **{
            chave: i.valor
            for chave, i in fundamentalista.indicadores_dos_dividendos(d).items()
        },
        "anos_pagando": float(d.anos_pagando),
        "diluicao": d.diluicao_anual,
        "acoes_em_circulacao": fundamentalista.acoes_por_especie(dados).total.valor,
    }


def _seis_anos_de_dividendos() -> DadosDaEmpresa:
    """Seis DFPs com dividendos pagos, lucro e ações que crescem 1% ao ano (sem desdobramento)."""
    linhas = []
    for ano in range(2020, 2026):
        valores = {
            "dividendos_pagos": -10.0 * (ano - 2019),
            "lucro_controladores": 40.0 * (ano - 2019),
            "lpa_basico": 40.0 * (ano - 2019) / (1_000.0 * 1.01 ** (ano - 2020)),
            "acoes_total": 1_000.0 * 1.01 ** (ano - 2020) + 5.0,
            "acoes_tesouraria": 5.0,
        }
        for conta, valor in valores.items():
            periodo = dm.POSICAO if conta.startswith("acoes") else dm.EXERCICIO
            linhas.append({"documento": "DFP", "referencia": date(ano, 12, 31), "versao": 1,
                           "periodo": periodo, "inicio": None, "fim": date(ano, 12, 31),
                           "conta": conta, "valor": valor})  # fmt: skip
    documentos = pd.DataFrame(
        [{"empresa": "X", "documento": "DFP", "referencia": date(ano, 12, 31), "versao": 1,
          "recebido_em": date(ano + 1, 3, 1), "link": ""} for ano in range(2020, 2026)]
    )  # fmt: skip
    return DadosDaEmpresa(
        contas=pd.DataFrame(linhas), documentos=documentos, setor="Comércio"
    )


@pytest.mark.parametrize("empresa", ["weg", "seis_anos"])
def test_as_entradas_refazem_os_dividendos_e_as_acoes(empresa):
    dados = _ler_a_weg() if empresa == "weg" else _seis_anos_de_dividendos()
    todas = fundamentalista.todas_as_entradas(dados)
    valores = {
        chave: valor
        for chave, valor in _dos_dividendos_e_do_capital(dados).items()
        if valor is not None
    }
    assert {"anos_pagando", "diluicao", "payout", "acoes_em_circulacao"} <= set(valores)
    if empresa == "seis_anos":
        assert "crescimento_do_dividendo" in valores
    for chave, valor in valores.items():
        assert todas[chave], chave
        refeito = _dos_dividendos_e_do_capital(
            _com_um_exercicio(_so_as_entradas(dados, todas[chave]))
        )
        assert refeito[chave] == pytest.approx(valor, rel=1e-12), chave


def _com_um_exercicio(dados: DadosDaEmpresa) -> DadosDaEmpresa:
    """A diluição só lê saldos de ações, mas `anuais` só monta a tabela de uma DFP que tem algum
    exercício (sem DRE, não há ano): uma linha de exercício de uma conta que nenhum número lê."""
    if (dados.contas["periodo"] == dm.EXERCICIO).any():
        return dados
    ultima = dados.contas["referencia"].max()
    linha = {"documento": "DFP", "referencia": ultima, "versao": 1, "periodo": dm.EXERCICIO,
             "inicio": None, "fim": ultima, "conta": "conta_que_nenhum_numero_le", "valor": 1.0}  # fmt: skip
    return replace(dados, contas=pd.concat([dados.contas, pd.DataFrame([linha])]))


def test_o_crescimento_do_dividendo_cita_o_ultimo_ano_e_o_de_cinco_antes():
    pagos = [
        e.referencia.year
        for e in fundamentalista.todas_as_entradas(_seis_anos_de_dividendos())[
            "crescimento_do_dividendo"
        ]
        if e.conta == "dividendos_pagos"
    ]
    assert pagos == [2020, 2025]


def test_os_dividendos_e_as_acoes_do_relatorio_tem_entradas(dados_da_weg):
    numeros = _numeros(re_.montar(_entradas(dados_da_weg)))
    for chave in ("anos_pagando", "diluicao", "payout", "acoes_em_circulacao"):
        rastro = numeros[chave].rastro
        assert rastro is not None and rastro.entradas, chave
    assert numeros["crescimento_do_dividendo"].rastro.entradas == ()  # type: ignore[union-attr]


def test_os_12_meses_com_o_itr_somam_a_dfp_e_o_acumulado_e_tiram_o_do_ano_antes():
    receita = _numeros(re_.montar(_entradas(_ler_a_weg(com_o_itr=True))))["receita"]
    assert receita.rastro is not None
    partes = [(e.documento, e.referencia, e.periodo) for e in receita.rastro.entradas]
    assert partes == [
        ("DFP", date(2025, 12, 31), dm.EXERCICIO),
        ("ITR", date(2026, 6, 30), dm.ACUMULADO),
        ("ITR", date(2026, 6, 30), dm.ACUMULADO_ANTERIOR),
    ]
    dfp, acumulado, anterior = (e.valor for e in receita.rastro.entradas)
    assert receita.valor == pytest.approx(dfp + acumulado - anterior)
    assert {(e.codigo, e.nome) for e in receita.rastro.entradas} == {
        dm.CONTAS_DA_CVM["receita"]
    }


def _seis_anos_de_receita() -> DadosDaEmpresa:
    anos = range(2020, 2026)
    contas = pd.DataFrame(
        [{"documento": "DFP", "referencia": date(ano, 12, 31), "versao": 1,
          "periodo": dm.EXERCICIO, "inicio": date(ano, 1, 1), "fim": date(ano, 12, 31),
          "conta": "receita", "valor": 100.0 * (ano - 2019)} for ano in anos]
    )  # fmt: skip
    documentos = pd.DataFrame(
        [{"empresa": "X", "documento": "DFP", "referencia": date(ano, 12, 31), "versao": 1,
          "recebido_em": date(ano + 1, 3, 1), "link": ""} for ano in anos]
    )  # fmt: skip
    return DadosDaEmpresa(contas=contas, documentos=documentos, setor="Comércio")


def test_o_crescimento_cita_o_primeiro_e_o_ultimo_ano():
    dados = _seis_anos_de_receita()
    primeira, ultima = fundamentos.entradas("crescimento_receita", dados)
    assert (primeira.referencia.year, ultima.referencia.year) == (2020, 2025)
    assert (primeira.publicado_em, ultima.publicado_em) == (
        date(2021, 3, 1),
        date(2026, 3, 1),
    )
    valor = fundamentos.calcular(dados, None)["crescimento_receita"].valor
    assert valor == pytest.approx((ultima.valor / primeira.valor) ** (1 / 5) - 1)


@pytest.mark.parametrize("com_o_itr", [False, True], ids=["so_a_dfp", "com_o_itr"])
def test_nenhuma_entrada_e_de_documento_publicado_depois_do_numero(com_o_itr):
    """Sem olhar o futuro: toda entrada vem de um documento do rastro, publicado até a data dele."""
    dados = _ler_a_weg(com_o_itr)
    for chave, item in _numeros(re_.montar(_entradas(dados))).items():
        rastro = item.rastro
        assert rastro is not None
        documentos = {d.nome: d.publicado_em for d in rastro.documentos}
        for entrada in rastro.entradas:
            assert entrada.publicado_em is not None and rastro.publicado_em is not None
            assert entrada.publicado_em <= rastro.publicado_em, chave
            assert documentos[_documento_da(entrada)] == entrada.publicado_em, chave


def test_cortar_o_futuro_nao_muda_as_entradas_do_passado():
    """O ITR de 2026 ainda não existia em 31/12/2025: cortado, as entradas são as só das DFPs."""
    com_o_itr, so_a_dfp = _ler_a_weg(com_o_itr=True), _ler_a_weg()
    ate_2025 = date(2025, 12, 31)
    cortada = replace(
        com_o_itr,
        contas=com_o_itr.contas[com_o_itr.contas["referencia"] <= ate_2025],
        documentos=com_o_itr.documentos[com_o_itr.documentos["referencia"] <= ate_2025],
    )
    for chave in fundamentos.FORMULAS:
        assert fundamentos.entradas(chave, cortada) == fundamentos.entradas(
            chave, so_a_dfp
        ), chave
    assert fundamentalista.todas_as_entradas(
        cortada
    ) == fundamentalista.todas_as_entradas(so_a_dfp)


def test_numero_indisponivel_nao_tem_entradas(dados_da_weg):
    sem_preco = _numeros(
        re_.montar(_entradas(dados_da_weg, preco=None, fechamentos=None))
    )
    assert (
        sem_preco["p_l"].rastro is not None and sem_preco["p_l"].rastro.entradas == ()
    )
    assert (
        fundamentos.entradas("crescimento_receita", dados_da_weg) == ()
    )  # só dois anos


def test_toda_conta_das_entradas_tem_codigo_e_nome_da_cvm():
    usadas = {
        conta
        for modulo in (fundamentos, fundamentalista)
        for contas in modulo.CONTAS_DOS_INDICADORES.values()
        for _, conta in contas
    }
    usadas = (usadas - {fundamentos.LUCRO}) | {"lucro_controladores", "lucro_liquido"}
    assert usadas <= set(dm.CONTAS_DA_CVM)
    assert set(fundamentos.CONTAS_DOS_INDICADORES) == set(fundamentos.FORMULAS)
    assert set(fundamentalista.CONTAS_DOS_INDICADORES) == set(fundamentalista.FORMULAS)
    assert all(codigo and nome for codigo, nome in dm.CONTAS_DA_CVM.values())


def test_entradas_vao_no_json_e_na_api(dados_da_weg):
    relatorio = re_.montar(_entradas(dados_da_weg))
    api = de_relatorio_da_empresa(relatorio)
    receita = next(i for s in api.secoes for i in s.itens if i.chave == "receita")
    assert receita.rastro is not None
    (entrada,) = receita.rastro.entradas
    assert (entrada.conta, entrada.codigo, entrada.periodo) == (
        "receita",
        "3.01",
        dm.EXERCICIO,
    )
    assert (entrada.referencia, entrada.publicado_em) == (
        date(2025, 12, 31),
        DFP_DE_2025_RECEBIDA,
    )
    texto = json.dumps(relatorio.como_dict(), ensure_ascii=False)
    assert '"conta": "receita"' in texto


# --- o gabarito por indicador ----------------------------------------------------------------------
def _como_no_gabarito(item: re_.Item) -> dict:
    assert item.rastro is not None
    return {
        "valor": item.valor,
        "formula": item.rastro.formula,
        "versao_do_calculo": item.rastro.versao_do_calculo,
        "fonte_id": item.rastro.fonte_id,
        "outras_fontes": list(item.rastro.outras_fontes),
        "publicado_em": item.rastro.publicado_em.isoformat()
        if item.rastro.publicado_em
        else None,
        "documentos": [d.nome for d in item.rastro.documentos],
        "entradas": [
            [e.conta, e.codigo, e.periodo, _documento_da(e), e.valor]
            for e in item.rastro.entradas
        ],
    }


def _atual(dados) -> dict[str, dict]:
    numeros = _numeros(re_.montar(_entradas(dados)))
    return {chave: _como_no_gabarito(item) for chave, item in sorted(numeros.items())}


def test_gabarito_por_indicador(dados_da_weg):
    """Cada indicador da WEG com valor, fórmula, versão, fonte e documentos fixos. Mudou a fórmula?
    Suba a versão do cálculo no módulo dela e refaça o gabarito (`python -m tests.test_rastro`)."""
    gabarito = json.loads(GABARITO.read_text(encoding="utf-8"))
    atual = _atual(dados_da_weg)
    assert set(atual) == set(gabarito), "indicador novo ou removido: refaça o gabarito"
    for chave, esperado in gabarito.items():
        agora = atual[chave]
        if esperado["formula"] != agora["formula"]:
            assert esperado["versao_do_calculo"] != agora["versao_do_calculo"], (
                f"{chave}: a fórmula mudou sem subir a versão do cálculo"
            )
        valor = esperado["valor"]
        aproximado = valor if valor is None else pytest.approx(valor, rel=1e-9)
        assert agora == {**esperado, "valor": aproximado}, chave


if __name__ == "__main__":  # refaz o gabarito: python -m tests.test_rastro
    GABARITO.parent.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(_atual(_ler_a_weg()), ensure_ascii=False, indent=2)
    GABARITO.write_text(texto + "\n", encoding="utf-8")
