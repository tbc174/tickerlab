"""Os cruzamentos do bloco comum (item 5): regra, fonte, data, "sem achado" e sem olhar o futuro."""

import copy
import inspect
from datetime import UTC, date, datetime

import pytest

from src import cruzamentos
from src.cruzamentos import (
    ATRASO_E_REFEITO,
    AUDITOR,
    CAIXA_E_DIVIDENDO,
    CAPITAL_E_DIVIDENDO,
    DEBENTURISTAS,
    DIVIDA_E_DIVIDENDO,
    DIVIDENDO,
    FUNDOS,
    INSIDERS,
    LUCRO_SEM_CAIXA,
    PARECER,
    RATING,
    REFEITO,
    REMUNERACAO,
    cruzamentos_da_ficha,
    cruzamentos_do_setor,
)
from src.dossie import Ficha, SecaoDaFicha

HOJE = date(2026, 10, 19)
FONTE = "CVM, tabela de teste"


def _ficha(*secoes: SecaoDaFicha) -> Ficha:
    return Ficha(
        versao_do_esquema=1,
        cnpj="02429144000193",
        empresa="Empresa Teste",
        gerado_em=datetime(2026, 10, 19, 6, 0, tzinfo=UTC),
        secoes=list(secoes),
    )


def _capital(fundos=None, insiders=None, proventos=None, eventos=None) -> SecaoDaFicha:
    return SecaoDaFicha(
        chave="capital_e_acionistas",
        titulo="Capital e acionistas",
        tabelas={
            "fundos_janelas": fundos or [],
            "insiders_janelas": insiders or [],
            "proventos_por_exercicio": proventos or [],
            "eventos_de_capital": eventos or [],
        },
        fontes=[FONTE],
    )


def _janelas(compras, vendas, compras_antes, vendas_antes, ate="2026-09-30"):
    return [
        {"janela": "últimos 12 meses", "ate": ate, "compras": compras, "vendas": vendas},
        {"janela": "12 meses anteriores", "ate": "2025-09-30", "compras": compras_antes, "vendas": vendas_antes},
    ]  # fmt: skip


def _qualidade(refeitos=(), olhados=10, diferentes=0, lucros=()) -> SecaoDaFicha:
    return SecaoDaFicha(
        chave="qualidade_do_lucro",
        titulo="Qualidade do lucro",
        itens=[
            {
                "chave": "exercicios_olhados",
                "nome": "olhados",
                "valor": olhados,
                "unidade": "exercícios",
                "base": "2026-03-20",
            },
            {
                "chave": "releases_diferentes",
                "nome": "diferentes",
                "valor": diferentes,
                "unidade": "valores",
                "base": "2026-08-14",
            },
        ],
        tabelas={
            "reapresentacoes": list(refeitos),
            "lucro_por_exercicio": list(lucros),
        },
        fontes=[FONTE],
    )


def _troca(efetiva_em: str) -> dict:
    return {
        "efetiva_em": efetiva_em,
        "anterior": "Firma A",
        "novo": "Firma B",
        "anos_com_o_anterior": 8.0,
    }


def _auditor(*trocas, pareceres=()) -> SecaoDaFicha:
    return SecaoDaFicha(
        chave="auditor_e_controladas",
        titulo="Auditor",
        tabelas={
            "trocas_de_auditor": list(trocas),
            "pareceres_do_auditor": list(pareceres),
        },
        fontes=[FONTE],
    )


def _achar(ficha: Ficha, chave: str, hoje: date = HOJE):
    return {c.chave: c for c in cruzamentos_da_ficha(ficha, hoje)}[chave]


# --- fundos ---------------------------------------------------------------------------------------


def test_fundos_entrando_quando_o_saldo_passa_de_25_por_cento_do_volume():
    ficha = _ficha(_capital(fundos=_janelas(900.0, 100.0, 500.0, 400.0)))
    achado = _achar(ficha, FUNDOS)
    assert achado.achado
    assert achado.frase.startswith("Fundos entrando.")
    assert achado.medido_em == "2026-09-30" and achado.fontes == (FONTE,)
    assert "30/09/2026" in achado.frase


def test_fundos_saindo_e_virada_de_saldo():
    saindo = _achar(
        _ficha(_capital(fundos=_janelas(100.0, 900.0, 400.0, 500.0))), FUNDOS
    )
    assert saindo.frase.startswith("Fundos saindo.")
    virada = _achar(
        _ficha(_capital(fundos=_janelas(480.0, 520.0, 700.0, 300.0))), FUNDOS
    )
    assert virada.achado and virada.frase.startswith("Fundos viraram o saldo.")


def test_fundos_equilibrados_dizem_sem_achado_com_os_numeros():
    achado = _achar(
        _ficha(_capital(fundos=_janelas(520.0, 480.0, 510.0, 490.0))), FUNDOS
    )
    assert not achado.achado and achado.frase.startswith("Sem achado.")


def test_fundos_sem_as_duas_janelas_nao_inventa():
    achado = _achar(_ficha(_capital(fundos=_janelas(1.0, 1.0, 1.0, 1.0)[:1])), FUNDOS)
    assert not achado.achado and achado.medido_em is None


# --- número refeito -------------------------------------------------------------------------------


def test_refeito_conta_exercicios_e_datas():
    refeitos = [
        {"exercicio": 2023, "linha": "Lucro do período", "trocado_em": "2024-05-10"},
        {"exercicio": 2023, "linha": "Receita", "trocado_em": "2024-05-10"},
        {"exercicio": 2024, "linha": "Receita", "trocado_em": "2025-04-02"},
    ]
    achado = _achar(_ficha(_qualidade(refeitos)), REFEITO)
    assert achado.achado
    assert "2 de 10 exercícios" in achado.frase and "02/04/2025" in achado.frase
    assert achado.numeros["exercicios_refeitos"] == 2


def test_refeito_com_release_diferente_tambem_e_achado():
    achado = _achar(_ficha(_qualidade(diferentes=3)), REFEITO)
    assert achado.achado and "3 valores do release" in achado.frase


def test_refeito_limpo_diz_quantos_olhou():
    achado = _achar(_ficha(_qualidade()), REFEITO)
    assert not achado.achado and "Nenhum dos 10 exercícios" in achado.frase


# --- troca de auditor -----------------------------------------------------------------------------


def test_troca_recente_de_auditor_e_achado_e_antiga_nao():
    recente = _achar(_ficha(_auditor(_troca("2025-06-30"))), AUDITOR)
    assert recente.achado and "Firma A para Firma B" in recente.frase
    antiga = _achar(_ficha(_auditor(_troca("2019-06-30"))), AUDITOR)
    assert not antiga.achado and "há mais de 3 anos" in antiga.frase


def test_sem_troca_nenhuma_diz_sem_achado():
    assert not _achar(_ficha(_auditor()), AUDITOR).achado


# --- insiders -------------------------------------------------------------------------------------


def _insiders(compras, vendas, negociacoes=7) -> SecaoDaFicha:
    return _capital(
        insiders=[{"janela": "últimos 12 meses", "ate": "2026-10-19", "compras": compras, "vendas": vendas, "negociacoes": negociacoes}]
    )  # fmt: skip


def test_insiders_predominam_vendas_ou_compras_so_no_agregado():
    vendas = _achar(_ficha(_insiders(100.0, 900.0)), INSIDERS)
    assert vendas.achado and vendas.frase.startswith("Predominam as vendas.")
    assert "sem nomes" in vendas.frase and "7 negociações" in vendas.frase
    compras = _achar(_ficha(_insiders(900.0, 100.0)), INSIDERS)
    assert compras.frase.startswith("Predominam as compras.")


def test_insiders_equilibrados_ou_sem_volume_nao_sao_achado():
    assert not _achar(_ficha(_insiders(500.0, 500.0)), INSIDERS).achado
    assert not _achar(_ficha(_insiders(0.0, 0.0, 0)), INSIDERS).achado


# --- sem olhar o futuro ---------------------------------------------------------------------------


def test_linhas_do_futuro_nao_mudam_o_passado():
    """Cortar o futuro não muda o passado: o que tem data depois de `hoje` é ignorado."""
    passado = [_troca("2025-06-30")]
    futuro = [*passado, {**_troca("2027-01-01"), "novo": "Firma Futura"}]
    refeitos = [{"exercicio": 2023, "linha": "Receita", "trocado_em": "2024-05-10"}]
    com_futuro = [
        *refeitos,
        {"exercicio": 2025, "linha": "Receita", "trocado_em": "2027-02-01"},
    ]
    janelas = _janelas(900.0, 100.0, 500.0, 400.0)
    com_janela_futura = [
        {"janela": "x", "ate": "2027-09-30", "compras": 1.0, "vendas": 9e9},
        *janelas,
    ]
    insiders = [
        {
            "janela": "x",
            "ate": "2030-01-01",
            "compras": 9e9,
            "vendas": 0.0,
            "negociacoes": 1,
        }
    ]
    sem = _ficha(_capital(janelas), _qualidade(refeitos), _auditor(*passado))
    com = _ficha(
        _capital(com_janela_futura, insiders),
        _qualidade(com_futuro),
        _auditor(*futuro),
    )
    assert cruzamentos_da_ficha(sem, HOJE)[:3] == cruzamentos_da_ficha(com, HOJE)[:3]
    assert not _achar(com, INSIDERS).achado


# --- dívida ativa e pessoas -----------------------------------------------------------------------


def test_o_bloco_nao_le_nomes_de_pessoas():
    """Insiders só agregados (ADR 0103); a dívida ativa entra pela seção da ficha, que já vem sem as
    linhas de pessoa natural (a porta da `pgfn_divida` as tira, ADR 0075)."""
    codigo = inspect.getsource(cruzamentos).replace(cruzamentos.__doc__ or "", "")
    assert "tipo_devedor" not in codigo
    for coluna in ("nome", "cpf", "pessoa"):
        assert f'["{coluna}"]' not in codigo


ORDEM = [
    FUNDOS, REFEITO, AUDITOR, INSIDERS,
    REMUNERACAO, DIVIDENDO, PARECER, RATING, DEBENTURISTAS, CAPITAL_E_DIVIDENDO,
    DIVIDA_E_DIVIDENDO, ATRASO_E_REFEITO, CAIXA_E_DIVIDENDO, LUCRO_SEM_CAIXA,
]  # fmt: skip


def test_os_cruzamentos_sempre_na_mesma_ordem():
    chaves = [c.chave for c in cruzamentos_da_ficha(_ficha(), HOJE)]
    assert chaves == ORDEM
    assert all(not c.achado and c.frase for c in cruzamentos_da_ficha(_ficha(), HOJE))


# --- o setor --------------------------------------------------------------------------------------


def test_setor_soma_quem_tem_achado_e_nao_conta_quem_nao_tinha_dado():
    entra = _ficha(_capital(fundos=_janelas(900.0, 100.0, 500.0, 400.0)))
    equilibrada = _ficha(_capital(fundos=_janelas(520.0, 480.0, 510.0, 490.0)))
    sem_dado = _ficha()
    setor = {c.chave: c for c in cruzamentos_do_setor(
        {"Alfa": entra, "Beta": equilibrada, "Gama": sem_dado}, HOJE
    )}  # fmt: skip
    fundos = setor[FUNDOS]
    assert (fundos.com_achado, fundos.avaliadas) == (1, 2)
    assert fundos.empresas == ("Alfa",) and fundos.fontes == (FONTE,)
    assert (
        fundos.frase
        == "Fundos entrando e saindo: 1 de 2 companhias do setor com dado têm achado."
    )
    assert setor[AUDITOR].avaliadas == 0
    assert "nenhuma companhia" in setor[AUDITOR].frase


def test_cruzamentos_nao_mudam_a_ficha_recebida():
    ficha = _ficha(_capital(fundos=_janelas(900.0, 100.0, 500.0, 400.0)))
    antes = copy.deepcopy(ficha)
    cruzamentos_da_ficha(ficha, HOJE)
    assert ficha == antes


@pytest.mark.parametrize("regra", cruzamentos.REGRAS)
def test_cada_regra_aceita_ficha_vazia(regra):
    assert not regra(_ficha(), HOJE).achado


# --- a seção da ficha ------------------------------------------------------------------------------
def test_a_secao_traz_todos_com_data_e_fonte_em_cada_frase():
    ficha = _ficha(_capital(fundos=_janelas(900.0, 100.0, 500.0, 400.0)))
    secao = cruzamentos.secao_dos_cruzamentos(ficha, HOJE)
    assert secao.chave == "cruzamentos" and len(secao.paragrafos) == len(ORDEM)
    fundos_ = secao.paragrafos[0]
    assert "Fundos entrando." in fundos_
    assert "Dado de 30/09/2026." in fundos_ and f"Fonte: {FONTE}." in fundos_
    sem_dado = secao.paragrafos[
        1
    ]  # nada da qualidade na ficha: diz o que faltou, sem inventar
    assert sem_dado.endswith(cruzamentos.SEM_FONTE)


def test_a_secao_corta_o_futuro_como_os_cruzamentos():
    janelas = _janelas(900.0, 100.0, 500.0, 400.0)
    futuro = [{"janela": "x", "ate": "2027-09-30", "compras": 1.0, "vendas": 9e9}]
    antes = cruzamentos.secao_dos_cruzamentos(_ficha(_capital(fundos=janelas)), HOJE)
    depois = cruzamentos.secao_dos_cruzamentos(
        _ficha(_capital(fundos=[*futuro, *janelas])), HOJE
    )
    assert antes.paragrafos == depois.paragrafos


def test_o_dossie_ganha_a_secao_e_o_cuidado_sem_perder_o_que_tinha():
    from src.dossie import dossie_da_ficha

    ficha = _ficha(_capital(fundos=_janelas(900.0, 100.0, 500.0, 400.0)))
    base = dossie_da_ficha(ficha, HOJE)
    com = cruzamentos.com_os_cruzamentos(base, ficha, HOJE)
    assert [s.chave for s in com.secoes][-1] == "cruzamentos"
    assert com.secoes[:-1] == base.secoes
    assert com.limites[-1] == cruzamentos.LIMITE_DOS_CRUZAMENTOS
    assert "recomendação" in com.limites[-1]


def test_a_secao_entra_depois_da_governanca_na_ordem_do_relatorio():
    from src.relatorio_empresa import ORDEM_DAS_SECOES

    ordem = list(ORDEM_DAS_SECOES)
    assert ordem.index("cruzamentos") == ordem.index("governanca") + 1


# --- R1: remuneração da diretoria em ano de lucro menor -------------------------------------------


def _governanca(*diretoria) -> SecaoDaFicha:
    return SecaoDaFicha(
        chave="governanca",
        titulo="Governança",
        tabelas={"remuneracao_da_diretoria_por_exercicio": list(diretoria)},
        fontes=[FONTE],
    )


def _diretoria(exercicio: int, total: float, conhecido_em: str = "2026-05-29") -> dict:
    return {"exercicio": exercicio, "total": total, "conhecido_em": conhecido_em}


def _lucro(exercicio: int, lucro: float, divulgado_em: str = "2026-03-20") -> dict:
    return {"exercicio": exercicio, "lucro": lucro, "divulgado_em": divulgado_em}


def test_remuneracao_sobe_com_o_lucro_caindo_mais_de_20_por_cento():
    ficha = _ficha(
        _governanca(_diretoria(2025, 44e6), _diretoria(2024, 40e6, "2025-05-31")),
        _qualidade(lucros=[_lucro(2025, 70e6), _lucro(2024, 100e6, "2025-03-12")]),
    )
    achado = _achar(ficha, REMUNERACAO)
    assert achado.achado
    assert "Diretoria Estatutária" in achado.frase and "sem nomes" in achado.frase
    assert "R$ 40,0 mi" in achado.frase and "R$ 44,0 mi" in achado.frase
    assert "R$ 100,0 mi" in achado.frase and "R$ 70,0 mi" in achado.frase
    assert "2024" in achado.frase and "2025" in achado.frase and "-30%" in achado.frase
    assert achado.medido_em == "2026-05-29" and achado.fontes == (FONTE,)
    assert achado.numeros["lucro_variacao"] == pytest.approx(-0.3)


def test_remuneracao_sobe_com_o_lucro_virando_prejuizo_tambem_e_achado():
    ficha = _ficha(
        _governanca(_diretoria(2025, 41e6), _diretoria(2024, 40e6)),
        _qualidade(lucros=[_lucro(2025, -5e6), _lucro(2024, 100e6)]),
    )
    achado = _achar(ficha, REMUNERACAO)
    assert achado.achado and "prejuízo" in achado.frase


def test_remuneracao_sem_achado_quando_o_lucro_cai_pouco_ou_a_remuneracao_tambem_cai():
    cai_pouco = _ficha(
        _governanca(_diretoria(2025, 44e6), _diretoria(2024, 40e6)),
        _qualidade(lucros=[_lucro(2025, 90e6), _lucro(2024, 100e6)]),
    )
    achado = _achar(cai_pouco, REMUNERACAO)
    assert not achado.achado and achado.frase.startswith("Sem achado.")
    assert achado.medido_em == "2026-05-29"
    ambos_caem = _ficha(
        _governanca(_diretoria(2025, 30e6), _diretoria(2024, 40e6)),
        _qualidade(lucros=[_lucro(2025, 50e6), _lucro(2024, 100e6)]),
    )
    assert not _achar(ambos_caem, REMUNERACAO).achado


def test_remuneracao_precisa_de_dois_exercicios_em_comum():
    so_um = _ficha(
        _governanca(_diretoria(2025, 44e6)),
        _qualidade(lucros=[_lucro(2025, 70e6), _lucro(2024, 100e6)]),
    )
    achado = _achar(so_um, REMUNERACAO)
    assert not achado.achado and achado.medido_em is None
    assert not _achar(_ficha(_governanca(_diretoria(2025, 44e6))), REMUNERACAO).achado


def test_remuneracao_nao_olha_o_fre_nem_a_dfp_do_futuro():
    diretoria = [
        _diretoria(2024, 40e6, "2025-05-31"),
        _diretoria(2023, 30e6, "2024-05-31"),
    ]
    lucros = [_lucro(2024, 100e6, "2025-03-12"), _lucro(2023, 90e6, "2024-03-12")]
    passado = _ficha(_governanca(*diretoria), _qualidade(lucros=lucros))
    futuro = _ficha(
        _governanca(_diretoria(2025, 44e6, "2027-05-29"), *diretoria),
        _qualidade(lucros=[_lucro(2025, 1e6, "2027-03-20"), *lucros]),
    )
    assert _achar(futuro, REMUNERACAO) == _achar(passado, REMUNERACAO)


# --- R2: dividendo pago acima do lucro ------------------------------------------------------------


def _pagou_e_lucrou(exercicio: int, pago: float, lucro: float | None, **caixa) -> tuple:
    """A DFC com os dividendos pagos e a DFP com o lucro do mesmo exercício."""
    return (
        _caixa(
            _ano_de_caixa(exercicio, 90e6, 20e6, **caixa),
            dfc=[_linha_da_dfc(exercicio, -pago)],
        ),
        _qualidade(lucros=[_lucro(exercicio, lucro)]),
    )


def test_dividendo_pago_acima_do_lucro_do_ano():
    ficha = _ficha(*_pagou_e_lucrou(2025, 130e6, 100e6, divulgado_em="2026-03-25"))
    achado = _achar(ficha, DIVIDENDO)
    assert achado.achado
    assert "R$ 130,0 mi" in achado.frase and "R$ 100,0 mi" in achado.frase
    assert (
        "2025" in achado.frase and "(DFC)" in achado.frase and "(DFP)" in achado.frase
    )
    assert achado.medido_em == "2026-03-25"
    assert achado.fontes == (FONTE_DO_CAIXA, FONTE)
    assert achado.numeros == {"lucro": 100e6, "dividendos_pagos": 130e6}


def test_dividendo_pago_com_prejuizo_e_achado():
    achado = _achar(_ficha(*_pagou_e_lucrou(2025, 10e6, -20e6)), DIVIDENDO)
    assert achado.achado and "prejuízo" in achado.frase
    assert "R$ 10,0 mi" in achado.frase


def test_dividendo_pago_abaixo_do_lucro_diz_sem_achado_com_os_numeros():
    achado = _achar(_ficha(*_pagou_e_lucrou(2025, 50e6, 100e6)), DIVIDENDO)
    assert not achado.achado and achado.frase.startswith("Sem achado.")
    assert "R$ 50,0 mi" in achado.frase and achado.medido_em == "2026-03-20"
    sem_linha = _ficha(
        _caixa(
            _ano_de_caixa(2025, 90e6, 20e6),
            dfc=[_linha_da_dfc(2025, 50e6, "6.03.01", "Captação de empréstimos")],
        ),
        _qualidade(lucros=[_lucro(2025, -20e6)]),
    )
    c = _achar(sem_linha, DIVIDENDO)
    assert not c.achado and c.medido_em and c.numeros["dividendos_pagos"] == 0.0


def test_dividendo_sem_dfc_ou_lucro_nao_inventa_e_nao_le_o_futuro():
    assert (
        _achar(_ficha(_qualidade(lucros=[_lucro(2025, 100e6)])), DIVIDENDO).medido_em
        is None
    )
    assert (
        _achar(_ficha(_pagou_e_lucrou(2025, 50e6, None)[0]), DIVIDENDO).medido_em
        is None
    )
    passado = _ficha(*_pagou_e_lucrou(2025, 50e6, 100e6))
    futuro = _ficha(
        _caixa(
            _ano_de_caixa(2025, 90e6, 20e6),
            _ano_de_caixa(2026, 90e6, 20e6, divulgado_em="2027-03-20"),
            dfc=[_linha_da_dfc(2025, -50e6), _linha_da_dfc(2026, -90e6)],
        ),
        _qualidade(lucros=[_lucro(2025, 100e6), _lucro(2026, 10e6, "2027-03-20")]),
    )
    assert _achar(futuro, DIVIDENDO) == _achar(passado, DIVIDENDO)


# --- R3: parecer com ressalva ou dúvida de continuidade -------------------------------------------


def _parecer(
    referencia: str, opiniao="sem_ressalva", continuidade="nao", disponivel_em=None
) -> dict:
    ano = int(referencia[:4])
    return {
        "referencia": referencia,
        "versao": 1,
        "disponivel_em": disponivel_em or f"{ano + 1}-03-20",
        "opiniao": opiniao,
        "enfase": "nao",
        "continuidade_operacional": continuidade,
    }


def test_parecer_com_ressalva_e_achado_com_o_exercicio_e_a_data():
    ficha = _ficha(
        _auditor(
            pareceres=[_parecer("2025-12-31", "com_ressalva"), _parecer("2024-12-31")]
        )
    )
    achado = _achar(ficha, PARECER)
    assert achado.achado and "ressalva" in achado.frase
    assert "2025" in achado.frase and "20/03/2026" in achado.frase
    assert achado.medido_em == "2026-03-20" and achado.fontes == (FONTE,)


def test_parecer_com_duvida_de_continuidade_e_achado_mesmo_sem_ressalva():
    ficha = _ficha(_auditor(pareceres=[_parecer("2025-12-31", continuidade="sim")]))
    achado = _achar(ficha, PARECER)
    assert achado.achado and "continuidade" in achado.frase


def test_parecer_limpo_ou_nao_classificado_nao_e_achado():
    limpo = _achar(
        _ficha(_auditor(pareceres=[_parecer("2025-12-31"), _parecer("2024-12-31")])),
        PARECER,
    )
    assert (
        not limpo.achado
        and limpo.frase.startswith("Sem achado.")
        and "2 " in limpo.frase
    )
    assert limpo.medido_em == "2026-03-20"
    ilegivel = _parecer("2025-12-31", "nao_classificado", "nao_classificado")
    assert not _achar(_ficha(_auditor(pareceres=[ilegivel])), PARECER).achado
    assert _achar(_ficha(_auditor()), PARECER).medido_em is None


def test_parecer_entregue_depois_de_hoje_fica_fora():
    ficha = _ficha(_auditor(pareceres=[
        _parecer("2026-12-31", "adversa", disponivel_em="2027-03-20"), _parecer("2025-12-31"),
    ]))  # fmt: skip
    assert not _achar(ficha, PARECER).achado


# --- R4: rating rebaixado -------------------------------------------------------------------------


def _credito(acoes=(), aperto=()) -> SecaoDaFicha:
    return SecaoDaFicha(
        chave="credito",
        titulo="Crédito",
        tabelas={"acoes_de_rating": list(acoes), "assembleias_de_aperto": list(aperto)},
        fontes=[FONTE],
    )


def _acao(
    acao: str, nota: str, nivel: int, publico_em: str, *, nota_anterior=None, nivel_anterior=None,
    perspectiva="estavel", agencia="fitch", escala="nacional",
) -> dict:  # fmt: skip
    return {
        "agencia": agencia,
        "escala": escala,
        "acao": acao,
        "nota": nota,
        "nota_anterior": nota_anterior,
        "nivel": nivel,
        "nivel_anterior": nivel_anterior,
        "perspectiva": perspectiva,
        "publico_em": publico_em,
        "link": "https://cvm/p",
    }


def test_rebaixamento_nos_ultimos_24_meses_diz_a_agencia_de_onde_para_onde_e_a_data():
    ficha = _ficha(_credito(acoes=[
        _acao("rebaixamento", "AA-(bra)", 4, "2026-03-03", nota_anterior="AA(bra)", nivel_anterior=3,
              perspectiva="negativa"),
        _acao("afirmacao", "AA(bra)", 3, "2024-09-11"),
    ]))  # fmt: skip
    achado = _achar(ficha, RATING)
    assert achado.achado
    assert "Fitch" in achado.frase and "AA(bra) para AA-(bra)" in achado.frase
    assert "03/03/2026" in achado.frase and "negativa" in achado.frase
    assert achado.medido_em == "2026-03-03" and achado.fontes == (FONTE,)
    assert "recomend" not in achado.frase.lower()


def test_nota_que_piorou_sem_a_palavra_rebaixamento_e_perspectiva_negativa_tambem_sao_achado():
    piorou = _ficha(_credito(acoes=[
        _acao("afirmacao", "A+(bra)", 5, "2026-01-10", nota_anterior="AA-(bra)", nivel_anterior=4),
    ]))  # fmt: skip
    assert _achar(piorou, RATING).achado
    negativa = _ficha(
        _credito(
            acoes=[
                _acao("afirmacao", "AA(bra)", 3, "2026-01-10", perspectiva="negativa")
            ]
        )
    )
    achado = _achar(negativa, RATING)
    assert achado.achado and "perspectiva negativa" in achado.frase


def test_rating_elevado_afirmado_ou_rebaixado_ha_mais_de_24_meses_nao_e_achado():
    ficha = _ficha(_credito(acoes=[
        _acao("elevacao", "AA+(bra)", 2, "2026-05-02", nota_anterior="AA(bra)", nivel_anterior=3),
        _acao("rebaixamento", "AA(bra)", 3, "2023-09-11", nota_anterior="AA+(bra)", nivel_anterior=2),
    ]))  # fmt: skip
    achado = _achar(ficha, RATING)
    assert not achado.achado and achado.frase.startswith("Sem achado.")
    assert achado.medido_em == "2026-05-02"
    assert _achar(_ficha(_credito()), RATING).medido_em is None


def test_rating_publicado_depois_de_hoje_fica_fora():
    ficha = _ficha(_credito(acoes=[
        _acao("rebaixamento", "A(bra)", 6, "2027-01-01", nota_anterior="AA(bra)", nivel_anterior=3),
    ]))  # fmt: skip
    assert not _achar(ficha, RATING).achado


# --- R5: assembleias de debenturistas de aperto ---------------------------------------------------


def _aperto(publico_em: str, assunto="AGD 5ª emissão: waiver de covenant") -> dict:
    return {
        "publico_em": publico_em,
        "especie": "Ata",
        "assunto": assunto,
        "link": "https://cvm/a",
    }


def test_assembleias_de_aperto_nos_ultimos_24_meses_contam_e_dizem_a_ultima():
    ficha = _ficha(
        _credito(
            aperto=[_aperto("2026-03-05"), _aperto("2025-05-05"), _aperto("2023-01-10")]
        )
    )
    achado = _achar(ficha, DEBENTURISTAS)
    assert achado.achado
    assert "2 assembleias" in achado.frase and "05/03/2026" in achado.frase
    assert achado.medido_em == "2026-03-05" and achado.numeros == {"assembleias": 2.0}
    assert "waiver" in achado.frase.lower()


def test_assembleias_de_aperto_antigas_ou_nenhuma_nao_sao_achado():
    antigas = _achar(_ficha(_credito(aperto=[_aperto("2023-01-10")])), DEBENTURISTAS)
    assert not antigas.achado and antigas.frase.startswith("Sem achado.")
    assert antigas.medido_em == "2023-01-10"
    nenhuma = _achar(
        _ficha(_credito(acoes=[_acao("afirmacao", "AA(bra)", 3, "2026-01-10")])),
        DEBENTURISTAS,
    )
    assert not nenhuma.achado and nenhuma.medido_em is None
    assert not _achar(
        _ficha(_credito(aperto=[_aperto("2027-03-05")])), DEBENTURISTAS
    ).achado


# --- R6: aumento de capital e dividendo no mesmo exercício ----------------------------------------


def _aumento(
    exercicio: int, valor: float = 300e6, descricao="Aumento de capital"
) -> dict:
    return _linha_da_dfc(exercicio, valor, "6.03.02", descricao)


def test_aumento_de_capital_e_dividendo_no_mesmo_exercicio():
    ficha = _ficha(
        _caixa(
            _ano_de_caixa(2025, 90e6, 20e6),
            _ano_de_caixa(2024, 90e6, 20e6, divulgado_em="2025-03-20"),
            dfc=[
                _aumento(2025, 200e6),
                _aumento(2025, 100e6, "Adiantamento para futuro aumento de capital"),
                _linha_da_dfc(2025, -50e6),
                _aumento(2024),
            ],
        )
    )
    achado = _achar(ficha, CAPITAL_E_DIVIDENDO)
    assert achado.achado
    assert "2025" in achado.frase and "R$ 300,0 mi" in achado.frase
    assert "R$ 50,0 mi" in achado.frase and "DFC" in achado.frase
    assert achado.medido_em == "2026-03-20" and achado.fontes == (FONTE_DO_CAIXA,)
    assert achado.numeros == {"aumento_de_capital": 300e6, "dividendos_pagos": 50e6}


def test_aumento_em_outro_ano_tesouraria_custo_ou_sem_dividendo_nao_e_achado():
    outro_ano = _ficha(
        _caixa(
            _ano_de_caixa(2025, 90e6, 20e6),
            _ano_de_caixa(2024, 90e6, 20e6, divulgado_em="2025-03-20"),
            dfc=[_aumento(2024), _linha_da_dfc(2025, -50e6), _linha_da_dfc(2024, -1e6)],
        )
    )
    achado = _achar(outro_ano, CAPITAL_E_DIVIDENDO)
    assert not achado.achado and achado.frase.startswith("Sem achado.")
    assert "nenhuma entrada de aumento de capital" in achado.frase
    assert achado.medido_em == "2026-03-20"
    nao_e_aumento = _ficha(
        _caixa(
            _ano_de_caixa(2025, 90e6, 20e6),
            dfc=[
                _aumento(2025, 9e6, "Alienação de ações em tesouraria"),
                _aumento(2025, 9e6, "Aumento de capital de não controladores"),
                _aumento(2025, -2e6, "Gastos com emissão de ações"),
                _aumento(2025, -40e6, "Redução de capital"),
                _linha_da_dfc(2025, -50e6),
            ],
        )
    )
    assert (
        _achar(nao_e_aumento, CAPITAL_E_DIVIDENDO).numeros["aumento_de_capital"] == 0.0
    )
    sem_dividendo = _ficha(
        _caixa(_ano_de_caixa(2025, 90e6, 20e6), dfc=[_aumento(2025)])
    )
    c = _achar(sem_dividendo, CAPITAL_E_DIVIDENDO)
    assert not c.achado and "R$ 300,0 mi recebidos" in c.frase
    assert (
        _achar(
            _ficha(_caixa(_ano_de_caixa(2025, 90e6, 20e6))), CAPITAL_E_DIVIDENDO
        ).medido_em
        is None
    )


def test_aumento_e_dividendo_nao_olham_o_futuro():
    ano_2024 = _ano_de_caixa(2024, 90e6, 20e6, divulgado_em="2025-03-20")
    passado = _ficha(_caixa(ano_2024, dfc=[_aumento(2024), _linha_da_dfc(2024, -50e6)]))
    futuro = _ficha(
        _caixa(
            ano_2024,
            _ano_de_caixa(2025, 90e6, 20e6, divulgado_em="2026-11-20"),
            dfc=[
                _aumento(2024),
                _linha_da_dfc(2024, -50e6),
                _linha_da_dfc(2025, -90e6),
            ],
        )
    )
    assert _achar(futuro, CAPITAL_E_DIVIDENDO) == _achar(passado, CAPITAL_E_DIVIDENDO)


# --- as regras no setor e no texto do limite ------------------------------------------------------


def test_setor_soma_as_regras_novas_tambem():
    com = _ficha(*_pagou_e_lucrou(2025, 130e6, 100e6))
    sem = _ficha(*_pagou_e_lucrou(2025, 50e6, 100e6))
    setor = {
        c.chave: c
        for c in cruzamentos_do_setor(
            {"Alfa": com, "Beta": sem, "Gama": _ficha()}, HOJE
        )
    }
    assert (setor[DIVIDENDO].com_achado, setor[DIVIDENDO].avaliadas) == (1, 2)
    assert setor[DIVIDENDO].empresas == ("Alfa",)
    assert set(setor) == set(ORDEM)


def test_o_limite_cita_as_regras_novas_e_a_fonte_de_cada_uma():
    limite = cruzamentos.LIMITE_DOS_CRUZAMENTOS
    for palavra in (
        "remuneração",
        "dividendo",
        "parecer",
        "rating",
        "debenturistas",
        "aumento de capital",
    ):
        assert palavra in limite, palavra
    assert "recomendação" in limite


def test_o_limite_cita_as_quatro_regras_de_novembro():
    limite = cruzamentos.LIMITE_DOS_CRUZAMENTOS
    for palavra in (
        "dívida ativa",
        "PGFN",
        "prazo",
        "caixa livre",
        "caixa operacional",
    ):
        assert palavra in limite, palavra
    assert "bancos e seguradoras" in limite


# --- R9 e R10: caixa livre, caixa operacional, dividendo e lucro ----------------------------------

FONTE_DO_CAIXA = "CVM, DFP de teste"


def _caixa(*exercicios, dfc=()) -> SecaoDaFicha:
    return SecaoDaFicha(
        chave="geracao_de_caixa",
        titulo="Geração de caixa",
        tabelas={
            "caixa_por_exercicio": list(exercicios),
            "dfc_dva_por_exercicio": list(dfc),
        },
        fontes=[FONTE_DO_CAIXA],
    )


def _linha_da_dfc(
    exercicio: int,
    valor: float,
    conta: str = "6.03.04",
    descricao: str = "Dividendos pagos",
    demonstracao: str = "DFC_MI",
) -> dict:
    return {
        "demonstracao": demonstracao,
        "conta": conta,
        "descricao": descricao,
        "exercicio": exercicio,
        "valor": valor,
    }


def _pagou(exercicio: int, valor: float = 40e6) -> SecaoDaFicha:
    """Só o caixa de um exercício (FCF positivo) com os dividendos pagos na DFC."""
    return _caixa(
        _ano_de_caixa(exercicio, 90e6, 20e6),
        dfc=[_linha_da_dfc(exercicio, -valor)],
    )


def _ano_de_caixa(
    exercicio: int,
    caixa_operacional: float,
    capex: float,
    ebitda: float | None = 50e6,
    divulgado_em: str = "2026-03-20",
) -> dict:
    return {
        "exercicio": exercicio,
        "fim": f"{exercicio}-12-31",
        "ebitda": ebitda,
        "caixa_operacional": caixa_operacional,
        "capex": capex,
        "fcf": caixa_operacional - capex,
        "divulgado_em": divulgado_em,
    }


# --- R7: dívida ativa com a União e dividendo pago -------------------------------------------

FONTE_DA_PGFN = "PGFN, dados abertos de teste"


def _divida(*inscricoes) -> SecaoDaFicha:
    return SecaoDaFicha(
        chave="divida_com_a_uniao",
        titulo="Dívida ativa com a União (PGFN)",
        tabelas={"inscricoes_na_divida_ativa": list(inscricoes)},
        fontes=[FONTE_DA_PGFN],
    )


def _inscricao(
    inscricoes: int,
    valor: float | None,
    situacao: str = "Em cobrança",
    retrato: str = "2026-06-30",
    publico_em: str = "2026-07-15",
) -> dict:
    return {
        "tipo_divida": "nao_previdenciaria",
        "tipo_situacao": situacao,
        "situacao_inscricao": "ATIVA EM COBRANCA",
        "ajuizado": False,
        "inscricoes": inscricoes,
        "valor_consolidado": valor,
        "aconteceu_em": retrato,
        "publico_em": publico_em,
    }


def test_divida_em_cobranca_e_dividendo_pago_e_achado():
    ficha = _ficha(
        _divida(_inscricao(3, 12e6), _inscricao(1, 5e6, situacao="Garantia")),
        _pagou(2025),
    )
    c = _achar(ficha, DIVIDA_E_DIVIDENDO)
    assert c.achado
    assert "30/06/2026" in c.frase and "3 inscrições" in c.frase and "2025" in c.frase
    assert "em cobrança" in c.frase
    assert c.numeros["inscricoes_em_cobranca"] == 3.0
    assert c.numeros["valor_em_cobranca"] == 12e6
    assert c.numeros["inscricoes"] == 4.0
    assert c.medido_em == "2026-07-15"
    assert c.numeros["dividendos_pagos"] == 40e6 and "DFC" in c.frase
    assert c.fontes == (FONTE_DA_PGFN, FONTE_DO_CAIXA)


def test_divida_so_com_garantia_ou_sem_dividendo_nao_e_achado():
    garantida = _ficha(
        _divida(_inscricao(2, 5e6, situacao="Garantia")),
        _pagou(2025),
    )
    c = _achar(garantida, DIVIDA_E_DIVIDENDO)
    assert not c.achado and c.frase.startswith("Sem achado.") and c.medido_em
    sem_dividendo = _ficha(_divida(_inscricao(3, 12e6)), _pagou(2025, 0.0))
    assert not _achar(sem_dividendo, DIVIDA_E_DIVIDENDO).achado


def test_retrato_anterior_ao_exercicio_do_dividendo_nao_e_achado():
    """Inscrição de um retrato de 2024 não diz nada sobre o dividendo de 2025."""
    ficha = _ficha(
        _divida(_inscricao(3, 12e6, retrato="2024-12-31", publico_em="2025-01-20")),
        _pagou(2025),
    )
    assert not _achar(ficha, DIVIDA_E_DIVIDENDO).achado


def test_divida_sem_inscricao_diz_sem_achado_e_sem_secao_nao_avalia():
    sem_linha = _ficha(_divida(), _pagou(2025))
    c = _achar(sem_linha, DIVIDA_E_DIVIDENDO)
    assert not c.achado and c.frase.startswith("Sem achado.") and c.medido_em
    sem_secao = _achar(_ficha(_pagou(2025)), DIVIDA_E_DIVIDENDO)
    assert not sem_secao.achado and sem_secao.medido_em is None


def test_divida_usa_o_retrato_mais_novo_ja_publico_e_nao_o_do_futuro():
    passado = _ficha(
        _divida(_inscricao(2, 1e6, situacao="Garantia")),
        _pagou(2025),
    )
    futuro = _ficha(
        _divida(
            _inscricao(2, 1e6, situacao="Garantia"),
            _inscricao(9, 9e9, retrato="2026-09-30", publico_em="2026-10-25"),
        ),
        _pagou(2025),
    )
    assert _achar(futuro, DIVIDA_E_DIVIDENDO) == _achar(passado, DIVIDA_E_DIVIDENDO)
    retrato_antigo_com_divida = _ficha(
        _divida(
            _inscricao(5, 2e6, retrato="2026-03-31", publico_em="2026-04-15"),
            _inscricao(2, 1e6, situacao="Garantia"),
        ),
        _pagou(2025),
    )
    assert not _achar(retrato_antigo_com_divida, DIVIDA_E_DIVIDENDO).achado


# --- R8: balanço entregue atrasado e refeito depois -----------------------------------------------


def _entregas(*linhas) -> SecaoDaFicha:
    return SecaoDaFicha(
        chave="entrega_das_demonstracoes",
        titulo="Entrega das demonstrações",
        tabelas={"entregas_de_dfp_e_itr": list(linhas)},
        fontes=["CVM, índice de entregas de teste"],
    )


def _entrega(
    referencia: str, rotulo: str, publico_em: str | None, dias: int = 0, documento="DFP"
) -> dict:
    return {
        "documento": documento,
        "referencia": referencia,
        "prazo": f"{int(referencia[:4]) + 1}-03-31",
        "primeira_entrega": publico_em,
        "publico_em": publico_em,
        "dias_uteis_de_atraso": dias,
        "rotulo": rotulo,
    }


def _refeito(exercicio: int, trocado_em: str) -> dict:
    return {"exercicio": exercicio, "trocado_em": trocado_em, "linha": "lucro"}


def test_os_rotulos_do_atraso_sao_os_da_ficha():
    from base import dossie

    assert cruzamentos.ROTULOS_DE_ATRASO == (
        dossie.ATRASOU,
        dossie.ATRASO_GRAVE_NO_ROTULO,
    )


def test_dfp_atrasada_e_refeita_depois_e_achado():
    ficha = _ficha(
        _entregas(
            _entrega("2024-12-31", "atraso grave", "2025-05-20", dias=34),
            _entrega("2025-12-31", "no prazo", "2026-03-30"),
        ),
        _qualidade(refeitos=[_refeito(2024, "2026-03-30")]),
    )
    c = _achar(ficha, ATRASO_E_REFEITO)
    assert c.achado
    assert (
        "2024" in c.frase and "atraso grave" in c.frase and "34 dias úteis" in c.frase
    )
    assert c.numeros == {"dfps": 2.0, "atrasadas": 1.0, "atrasadas_e_refeitas": 1.0}
    assert c.medido_em == "2026-03-30"


def test_atraso_sem_refeito_zona_cinzenta_ou_itr_nao_e_achado():
    so_atraso = _ficha(
        _entregas(_entrega("2024-12-31", "atrasou", "2025-04-10", dias=7)),
        _qualidade(refeitos=[_refeito(2023, "2025-04-10")]),
    )
    c = _achar(so_atraso, ATRASO_E_REFEITO)
    assert not c.achado and c.frase.startswith("Sem achado.") and c.medido_em
    cinzenta = _ficha(
        _entregas(_entrega("2024-12-31", "zona cinzenta", "2025-04-02", dias=1)),
        _qualidade(refeitos=[_refeito(2024, "2026-03-30")]),
    )
    assert not _achar(cinzenta, ATRASO_E_REFEITO).achado
    itr = _ficha(
        _entregas(
            _entrega("2024-09-30", "atrasou", "2024-12-01", dias=10, documento="ITR")
        ),
        _qualidade(refeitos=[_refeito(2024, "2026-03-30")]),
    )
    assert not _achar(itr, ATRASO_E_REFEITO).achado


def test_atraso_e_refeito_nao_olham_o_futuro():
    entregas = _entregas(_entrega("2024-12-31", "atrasou", "2025-04-10", dias=7))
    passado = _ficha(entregas, _qualidade())
    futuro = _ficha(entregas, _qualidade(refeitos=[_refeito(2024, "2026-11-30")]))
    assert _achar(futuro, ATRASO_E_REFEITO) == _achar(passado, ATRASO_E_REFEITO)
    nao_entregue = _ficha(
        _entregas(_entrega("2025-12-31", "não entregue até 19/10/2026", None)),
        _qualidade(refeitos=[_refeito(2025, "2026-01-10")]),
    )
    assert _achar(nao_entregue, ATRASO_E_REFEITO).medido_em is None


def test_dividendo_com_caixa_livre_negativo_e_achado():
    ficha = _ficha(
        _caixa(
            _ano_de_caixa(2025, 30e6, 80e6),
            dfc=[
                _linha_da_dfc(2025, -30e6),
                _linha_da_dfc(
                    2025, -10e6, "6.03.05", "Juros sobre o capital próprio pagos"
                ),
            ],
        )
    )
    c = _achar(ficha, CAIXA_E_DIVIDENDO)
    assert c.achado and "2025" in c.frase and "DFC" in c.frase
    assert c.numeros["fcf"] == -50e6 and c.numeros["dividendos_pagos"] == 40e6
    assert c.medido_em == "2026-03-20"
    assert c.fontes == (FONTE_DO_CAIXA,)


def test_caixa_livre_positivo_ou_sem_dividendo_nao_e_achado():
    positivo = _ficha(_pagou(2025))
    c = _achar(positivo, CAIXA_E_DIVIDENDO)
    assert not c.achado and c.frase.startswith("Sem achado.")
    sem_linha = _ficha(
        _caixa(
            _ano_de_caixa(2025, 30e6, 80e6),
            dfc=[_linha_da_dfc(2025, 50e6, "6.03.01", "Captação de empréstimos")],
        )
    )
    c = _achar(sem_linha, CAIXA_E_DIVIDENDO)
    assert not c.achado and c.medido_em and c.numeros["dividendos_pagos"] == 0.0


def test_banco_ou_seguradora_sem_ebitda_nao_e_avaliado_no_caixa():
    ficha = _ficha(
        _caixa(
            _ano_de_caixa(2025, -30e6, 5e6, ebitda=None),
            _ano_de_caixa(2024, -10e6, 5e6, ebitda=None),
            dfc=[_linha_da_dfc(2025, -40e6)],
        ),
        _qualidade(lucros=[_lucro(2025, 100e6), _lucro(2024, 90e6)]),
    )
    for chave in (CAIXA_E_DIVIDENDO, LUCRO_SEM_CAIXA):
        c = _achar(ficha, chave)
        assert not c.achado and c.medido_em is None
        assert "bancos e seguradoras" in c.frase


def test_caixa_e_dividendo_nao_olham_o_futuro():
    passado = _ficha(
        _caixa(
            _ano_de_caixa(2024, 90e6, 20e6, divulgado_em="2025-03-20"),
            dfc=[_linha_da_dfc(2024, -40e6)],
        )
    )
    futuro = _ficha(
        _caixa(
            _ano_de_caixa(2024, 90e6, 20e6, divulgado_em="2025-03-20"),
            _ano_de_caixa(2025, 30e6, 80e6, divulgado_em="2026-11-20"),
            dfc=[_linha_da_dfc(2024, -40e6), _linha_da_dfc(2025, -40e6)],
        )
    )
    assert _achar(futuro, CAIXA_E_DIVIDENDO) == _achar(passado, CAIXA_E_DIVIDENDO)


def test_lucro_com_caixa_operacional_negativo_dois_anos_seguidos_e_achado():
    ficha = _ficha(
        _caixa(_ano_de_caixa(2025, -20e6, 5e6), _ano_de_caixa(2024, -15e6, 5e6)),
        _qualidade(lucros=[_lucro(2025, 100e6), _lucro(2024, 90e6)]),
    )
    c = _achar(ficha, LUCRO_SEM_CAIXA)
    assert c.achado and "2024" in c.frase and "2025" in c.frase
    assert c.numeros["caixa_operacional"] == -20e6 and c.numeros["lucro"] == 100e6
    assert c.fontes == (FONTE, FONTE_DO_CAIXA)


def test_lucro_sem_caixa_em_um_ano_so_ou_com_prejuizo_nao_e_achado():
    um_ano = _ficha(
        _caixa(_ano_de_caixa(2025, -20e6, 5e6), _ano_de_caixa(2024, 40e6, 5e6)),
        _qualidade(lucros=[_lucro(2025, 100e6), _lucro(2024, 90e6)]),
    )
    c = _achar(um_ano, LUCRO_SEM_CAIXA)
    assert not c.achado and c.frase.startswith("Sem achado.") and c.medido_em
    prejuizo = _ficha(
        _caixa(_ano_de_caixa(2025, -20e6, 5e6), _ano_de_caixa(2024, -15e6, 5e6)),
        _qualidade(lucros=[_lucro(2025, -10e6), _lucro(2024, 90e6)]),
    )
    assert not _achar(prejuizo, LUCRO_SEM_CAIXA).achado


def test_lucro_sem_caixa_precisa_de_dois_exercicios_seguidos():
    salto = _ficha(
        _caixa(_ano_de_caixa(2025, -20e6, 5e6), _ano_de_caixa(2023, -15e6, 5e6)),
        _qualidade(lucros=[_lucro(2025, 100e6), _lucro(2023, 90e6)]),
    )
    c = _achar(salto, LUCRO_SEM_CAIXA)
    assert not c.achado and c.medido_em is None


def test_setor_conta_as_quatro_regras_de_novembro():
    com = _ficha(
        _caixa(_ano_de_caixa(2025, 30e6, 80e6), dfc=[_linha_da_dfc(2025, -40e6)])
    )
    setor = {
        c.chave: c for c in cruzamentos_do_setor({"Alfa": com, "Beta": _ficha()}, HOJE)
    }
    caixa = setor[CAIXA_E_DIVIDENDO]
    assert (caixa.com_achado, caixa.avaliadas) == (1, 1)
    assert setor[DIVIDA_E_DIVIDENDO].avaliadas == 0


def test_lucro_vazio_na_dfp_nao_quebra_a_remuneracao_nem_o_caixa():
    """Regressão (07/11/2026): 22 das 412 fichas de 03/11 trazem um exercício com o lucro vazio (a DFP
    sem a linha); a remuneração quebrava com `float(None)` e derrubava a seção inteira."""
    ficha = _ficha(
        _governanca(_diretoria(2025, 12e6), _diretoria(2024, 10e6)),
        _qualidade(lucros=[_lucro(2025, None), _lucro(2024, 90e6), _lucro(2023, 80e6)]),
        _caixa(_ano_de_caixa(2025, -20e6, 5e6), _ano_de_caixa(2024, -15e6, 5e6)),
    )
    remuneracao = _achar(ficha, REMUNERACAO)
    assert not remuneracao.achado and remuneracao.medido_em is None
    sem_caixa = _achar(ficha, LUCRO_SEM_CAIXA)
    assert not sem_caixa.achado and sem_caixa.medido_em is None


def test_dividendos_pagos_na_dfc_sem_contar_a_mae_recebidos_nem_entradas():
    """A soma sai das atividades de financiamento: a filha não soma junto com a mãe, o dividendo
    recebido da investida e a linha positiva não entram, e um método só por ano."""
    secao = _caixa(
        _ano_de_caixa(2025, 30e6, 80e6),
        dfc=[
            _linha_da_dfc(2025, -50e6, "6.03.04", "Dividendos e JCP pagos"),
            _linha_da_dfc(2025, -30e6, "6.03.04.01", "Dividendos pagos"),
            _linha_da_dfc(2025, -20e6, "6.03.04.02", "JCP pagos"),
            _linha_da_dfc(
                2025, -9e6, "6.02.03", "Dividendos pagos a não controladores"
            ),
            _linha_da_dfc(2025, 7e6, "6.03.06", "Dividendos recebidos de controladas"),
            _linha_da_dfc(2025, -7e6, "6.03.07", "Dividendos recebidos (devolvidos)"),
            _linha_da_dfc(2025, 3e6, "6.03.08", "Dividendos prescritos"),
            _linha_da_dfc(2025, -50e6, "6.03.04", "Dividendos pagos", "DFC_MD"),
        ],
    )
    assert cruzamentos._dividendos_pagos(secao, HOJE) == {2025: 50e6}


def test_ano_sem_dfc_na_ficha_nao_vira_dividendo_zero():
    secao = _caixa(
        _ano_de_caixa(2025, 30e6, 80e6),
        _ano_de_caixa(2024, 30e6, 80e6),
        dfc=[_linha_da_dfc(2024, -10e6)],
    )
    assert cruzamentos._dividendos_pagos(secao, HOJE) == {2024: 10e6}
    so_caixa = _ficha(_caixa(_ano_de_caixa(2025, 30e6, 80e6)))
    assert _achar(so_caixa, CAIXA_E_DIVIDENDO).medido_em is None


def test_as_regras_de_dividendo_nao_leem_mais_o_fre():
    """O FRE parou de trazer os proventos em 2022 e os aumentos de capital em 2023: olhar para ele
    fazia as regras compararem exercícios velhos. Só o FRE na ficha não avalia nenhuma delas."""
    so_fre = _ficha(
        _capital(
            proventos=[{"exercicio": 2021, "lucro_ajustado": 10e6, "dividendo_total": 90e6,
                        "conhecido_em": "2022-05-29"}],
            eventos=[{"data": "2021-08-01", "tipo": "aumento", "valor": 300e6}],
        )
    )  # fmt: skip
    for chave in (
        DIVIDENDO,
        CAPITAL_E_DIVIDENDO,
        DIVIDA_E_DIVIDENDO,
        CAIXA_E_DIVIDENDO,
    ):
        assert _achar(so_fre, chave).medido_em is None, chave
