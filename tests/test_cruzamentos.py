"""Os cruzamentos do bloco comum (item 5): regra, fonte, data, "sem achado" e sem olhar o futuro."""

import copy
import inspect
from datetime import UTC, date, datetime

import pytest

from src import cruzamentos
from src.cruzamentos import (
    AUDITOR,
    CAPITAL_E_DIVIDENDO,
    DEBENTURISTAS,
    DIVIDENDO,
    FUNDOS,
    INSIDERS,
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


def test_o_bloco_nao_le_a_divida_ativa_nem_nomes_de_pessoas():
    """ADR 0103: `pgfn_divida` bloqueada até o ponto 9; insiders só agregados."""
    codigo = inspect.getsource(cruzamentos).replace(cruzamentos.__doc__ or "", "")
    assert "pgfn" not in codigo.lower()
    for coluna in ("nome", "cpf", "pessoa"):
        assert f'["{coluna}"]' not in codigo


ORDEM = [
    FUNDOS, REFEITO, AUDITOR, INSIDERS,
    REMUNERACAO, DIVIDENDO, PARECER, RATING, DEBENTURISTAS, CAPITAL_E_DIVIDENDO,
]  # fmt: skip


def test_os_dez_cruzamentos_sempre_na_mesma_ordem():
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
def test_a_secao_traz_os_dez_com_data_e_fonte_em_cada_frase():
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


# --- R2: dividendo acima do lucro -----------------------------------------------------------------


def _provento(
    exercicio: int,
    lucro_ajustado: float,
    dividendo_total: float,
    conhecido_em: str = "2026-05-29",
) -> dict:
    return {
        "exercicio": exercicio,
        "lucro_ajustado": lucro_ajustado,
        "dividendo_total": dividendo_total,
        "payout": dividendo_total / lucro_ajustado if lucro_ajustado else None,
        "conhecido_em": conhecido_em,
    }


def test_dividendo_acima_do_lucro_ajustado_do_ultimo_exercicio():
    ficha = _ficha(
        _capital(
            proventos=[_provento(2025, 100e6, 130e6), _provento(2024, 100e6, 50e6)]
        )
    )
    achado = _achar(ficha, DIVIDENDO)
    assert achado.achado
    assert (
        "R$ 130,0 mi" in achado.frase
        and "R$ 100,0 mi" in achado.frase
        and "2025" in achado.frase
    )
    assert achado.medido_em == "2026-05-29" and achado.fontes == (FONTE,)
    assert achado.numeros == {"lucro_ajustado": 100e6, "dividendo_total": 130e6}


def test_dividendo_com_prejuizo_e_achado():
    achado = _achar(
        _ficha(_capital(proventos=[_provento(2025, -20e6, 10e6)])), DIVIDENDO
    )
    assert achado.achado and "prejuízo" in achado.frase
    assert "R$ 10,0 mi" in achado.frase


def test_dividendo_abaixo_do_lucro_diz_sem_achado_com_os_numeros():
    achado = _achar(
        _ficha(_capital(proventos=[_provento(2025, 100e6, 50e6)])), DIVIDENDO
    )
    assert not achado.achado and achado.frase.startswith("Sem achado.")
    assert "R$ 50,0 mi" in achado.frase and achado.medido_em == "2026-05-29"
    sem_dividendo = _achar(
        _ficha(_capital(proventos=[_provento(2025, -20e6, 0.0)])), DIVIDENDO
    )
    assert not sem_dividendo.achado


def test_dividendo_sem_proventos_nao_inventa_e_nao_le_o_fre_do_futuro():
    assert _achar(_ficha(_capital()), DIVIDENDO).medido_em is None
    futuro = _ficha(_capital(proventos=[
        _provento(2026, 10e6, 90e6, "2027-05-29"), _provento(2025, 100e6, 50e6),
    ]))  # fmt: skip
    assert not _achar(futuro, DIVIDENDO).achado


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


def _evento(data: str, tipo="aumento", valor=300e6) -> dict:
    return {
        "data": data,
        "tipo": tipo,
        "fator": None,
        "acoes_novas": 5e6,
        "valor": valor,
    }


def test_aumento_de_capital_e_dividendo_no_mesmo_exercicio():
    ficha = _ficha(_capital(
        proventos=[_provento(2025, 100e6, 50e6)],
        eventos=[_evento("2025-08-01"), _evento("2024-02-01")],
    ))  # fmt: skip
    achado = _achar(ficha, CAPITAL_E_DIVIDENDO)
    assert achado.achado
    assert (
        "2025" in achado.frase
        and "R$ 300,0 mi" in achado.frase
        and "R$ 50,0 mi" in achado.frase
    )
    assert "01/08/2025" in achado.frase
    assert achado.medido_em == "2026-05-29" and achado.fontes == (FONTE,)
    assert achado.numeros == {
        "aumentos": 1.0,
        "aumento_valor": 300e6,
        "dividendo_total": 50e6,
    }


def test_aumento_sem_valor_informado_ainda_e_achado():
    ficha = _ficha(
        _capital(
            proventos=[_provento(2025, 100e6, 50e6)],
            eventos=[_evento("2025-08-01", valor=None)],
        )
    )
    achado = _achar(ficha, CAPITAL_E_DIVIDENDO)
    assert achado.achado and "sem valor informado" in achado.frase


def test_aumento_em_outro_exercicio_desdobramento_ou_sem_dividendo_nao_e_achado():
    outro_ano = _ficha(
        _capital(
            proventos=[_provento(2025, 100e6, 50e6)], eventos=[_evento("2024-08-01")]
        )
    )
    achado = _achar(outro_ano, CAPITAL_E_DIVIDENDO)
    assert (
        not achado.achado
        and achado.frase.startswith("Sem achado.")
        and achado.medido_em == "2026-05-29"
    )
    desdobrou = _ficha(
        _capital(
            proventos=[_provento(2025, 100e6, 50e6)],
            eventos=[_evento("2025-08-01", "desdobramento")],
        )
    )
    assert not _achar(desdobrou, CAPITAL_E_DIVIDENDO).achado
    sem_dividendo = _ficha(
        _capital(
            proventos=[_provento(2025, 100e6, 0.0)], eventos=[_evento("2025-08-01")]
        )
    )
    assert not _achar(sem_dividendo, CAPITAL_E_DIVIDENDO).achado
    assert (
        _achar(
            _ficha(_capital(eventos=[_evento("2025-08-01")])), CAPITAL_E_DIVIDENDO
        ).medido_em
        is None
    )


def test_aumento_e_dividendo_nao_olham_o_futuro():
    passado = _ficha(
        _capital(
            proventos=[_provento(2024, 100e6, 50e6)], eventos=[_evento("2024-08-01")]
        )
    )
    futuro = _ficha(_capital(
        proventos=[_provento(2025, 100e6, 90e6, "2027-05-29"), _provento(2024, 100e6, 50e6)],
        eventos=[_evento("2027-01-05"), _evento("2024-08-01")],
    ))  # fmt: skip
    assert _achar(futuro, CAPITAL_E_DIVIDENDO) == _achar(passado, CAPITAL_E_DIVIDENDO)


# --- as seis regras novas no setor e no texto do limite -------------------------------------------


def test_setor_soma_as_regras_novas_tambem():
    com = _ficha(_capital(proventos=[_provento(2025, 100e6, 130e6)]))
    sem = _ficha(_capital(proventos=[_provento(2025, 100e6, 50e6)]))
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
