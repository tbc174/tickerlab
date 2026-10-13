"""Grupos de setores da CVM (série 2 da base de ML, PR 4): toda empresa cai num grupo para os padrões
das notas (ADR 0033), as holdings vão para o setor que administram e grupo pequeno compara com o
mercado, avisando."""

import pytest

from src import setores

# os 53 setores das empresas que entregaram a DFP 2025 (cadastro da CVM, 13/10/2026)
SETORES_REAIS = (
    "Serviços Transporte e Logística", "Energia Elétrica",
    "Construção Civil, Mat. Constr. e Decoração", "Comércio (Atacado e Varejo)",
    "Saneamento, Serv. Água e Gás", "Emp. Adm. Part. - Sem Setor Principal",
    "Emp. Adm. Part. - Energia Elétrica", "Máquinas, Equipamentos, Veículos e Peças",
    "Emp. Adm. Part. - Serviços Transporte e Logística", "Bancos", "Têxtil e Vestuário",
    "Metalurgia e Siderurgia", "Telecomunicações", "Serviços Médicos",
    "Comunicação e Informática", "Alimentos", "Securitização de Recebíveis",
    "Agricultura (Açúcar, Álcool e Cana)", "Emp. Adm. Part. - Const. Civil, Mat. Const. e Decoração",
    "Emp. Adm. Part. - Comércio (Atacado e Varejo)", "Educação", "Petróleo e Gás",
    "Farmacêutico e Higiene", "Petroquímicos e Borracha", "Emp. Adm. Part. - Telecomunicações",
    "Emp. Adm. Part. - Saneamento, Serv. Água e Gás", "Emp. Adm. Part. - Petróleo e Gás",
    "Emp. Adm. Part. - Intermediação Financeira", "Brinquedos e Lazer",
    "Emp. Adm. Part. - Educação", "Hospedagem e Turismo", "Intermediação Financeira",
    "Emp. Adm. Part. - Alimentos", "Extração Mineral", "Papel e Celulose",
    "Seguradoras e Corretoras", "Emp. Adm. Part. - Metalurgia e Siderurgia",
    "Emp. Adm. Part. - Máqs., Equip., Veíc. e Peças", "Emp. Adm. Part. - Seguradoras e Corretoras",
    "Emp. Adm. Part. - Extração Mineral", "Emp. Adm. Part. - Comunicação e Informática",
    "Bebidas e Fumo", "Emp. Adm. Part. - Crédito Imobiliário", "Arrendamento Mercantil",
    "Emp. Adm. Part. - Agricultura (Açúcar, Álcool e Cana)",
    "Bolsas de Valores/Mercadorias e Futuros", "Emp. Adm. Part. - Bancos", "Embalagens",
    "Emp. Adm. Part. - Serviços médicos", "Emp. Adm. Part. - Brinquedos e Lazer",
    "Emp. Adm. Part. - Hospedagem e Turismo", "Reflorestamento",
    "Emp. Adm. Part. - Papel e Celulose",
)  # fmt: skip


def test_todo_setor_da_cvm_tem_grupo():
    sem_grupo = [
        s for s in SETORES_REAIS if setores.grupo_do_setor(s) == setores.SEM_GRUPO
    ]
    assert sem_grupo == []
    assert set(setores.GRUPOS) >= {setores.grupo_do_setor(s) for s in SETORES_REAIS}


@pytest.mark.parametrize(
    ("setor", "grupo"),
    [
        ("Emp. Adm. Part. - Energia Elétrica", "energia"),
        ("Energia Elétrica", "energia"),
        ("Emp. Adm. Part. - Máqs., Equip., Veíc. e Peças", "bens_de_capital"),
        ("Bancos", "financeiro"),
        ("Securitização de Recebíveis", "financeiro"),
        ("Emp. Adm. Part. - Sem Setor Principal", "holdings"),
        ("", setores.SEM_GRUPO),
        ("Setor que ainda não existe", setores.SEM_GRUPO),
    ],
)
def test_holding_vai_para_o_setor_que_administra(setor, grupo):
    assert setores.grupo_do_setor(setor) == grupo


def test_grupo_pequeno_usa_o_mercado_e_avisa():
    contagem = {"energia": 40, "educacao": 5}
    usado, aviso = setores.grupo_para_comparar("educacao", contagem)
    assert usado == setores.MERCADO
    assert "5 empresas" in aviso and "mercado" in aviso.lower()
    assert setores.grupo_para_comparar("energia", contagem) == ("energia", "")


def test_financeiro_nunca_cai_no_mercado_das_nao_financeiras():
    usado, aviso = setores.grupo_para_comparar("financeiro", {"financeiro": 3})
    assert usado == setores.SEM_GRUPO and aviso
