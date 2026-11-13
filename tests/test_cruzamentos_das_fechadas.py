"""Os cruzamentos de empresa fechada da página inicial (linha 925): só contagens, só pessoa jurídica.

Base de mentira, sem internet; as raízes são de ninguém. A porta é a de verdade (`base.porta.Porta`) sobre
parquets numa pasta do teste, com os mesmos apelidos de data que o servidor usa. Riscos: contar companhia
aberta, empresa baixada ou linha de pessoa; olhar o futuro (retrato, entrada de sócia, contrato ou lista da
PGFN ainda não públicos no dia); sair número com contagem abaixo do mínimo; e um cartão de tabela sem
licença ou fora da porta ficar de pé.
"""

from dataclasses import replace
from datetime import date

import pandas as pd
import pytest

from base import cruzamentos_das_fechadas as fechadas
from base.contrato import catalogo
from base.porta import Porta

DIA = date(2026, 11, 10)
FUTURO = "2026-11-20"  # público só depois do dia da medição
CARIMBOS = {
    "origem_sha256": "0" * 64,
    "montado_em": pd.Timestamp("2026-11-05", tz="UTC"),
    "versao_do_codigo": "teste",
}
TI, INDUSTRIA, VAREJO = "6201501", "1091101", "4711302"


def r(numero: int) -> str:
    """Uma raiz de mentira (8 dígitos)."""
    return f"310000{numero:02d}"


def cnpj(numero: int, ordem: str = "0001") -> str:
    return f"{r(numero)}{ordem}00"


ABERTA, BAIXADA, SO_NO_FUTURO = 4, 5, 16
# raiz: (situação, CNAE da matriz, porte)
EMPRESAS = {
    1: ("02", TI, "micro"),
    2: ("02", TI, "micro"),
    3: ("02", TI, "micro"),
    ABERTA: ("02", TI, "demais"),
    BAIXADA: ("08", TI, "micro"),
    6: ("02", TI, "micro"),
    7: ("02", TI, "micro"),
    8: ("02", INDUSTRIA, "demais"),
    9: ("02", INDUSTRIA, "demais"),
    10: ("02", INDUSTRIA, "pequeno"),
    11: ("02", VAREJO, "demais"),
    12: ("02", TI, "micro"),
    13: ("02", TI, "micro"),
    14: ("02", TI, "micro"),
    15: ("02", TI, "micro"),
}
ATIVAS_FECHADAS = len(
    [n for n, (s, *_) in EMPRESAS.items() if s == "02" and n != ABERTA]
)
# filiais: raiz, ordem, início de atividade
FILIAIS = [
    (6, "0002", "2026-01-10"), (6, "0003", "2026-02-10"), (6, "0004", "2026-03-10"),  # 3 na janela
    (7, "0002", "2025-06-01"), (7, "0003", "2026-02-01"), (7, "0004", "2026-03-01"),  # 1 fora da janela
]  # fmt: skip


def _gravar(arquivo, tabela: pd.DataFrame) -> None:
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    tabela.to_parquet(arquivo, index=False)


def _dia(texto: str):
    return pd.Timestamp(texto).date()


def _estabelecimentos() -> pd.DataFrame:
    linhas = [
        (cnpj(n), r(n), True, s, "2010-01-01", cnae, "2026-10", "2026-10-20")
        for n, (s, cnae, _) in EMPRESAS.items()
    ]
    linhas += [
        (cnpj(n, o), r(n), False, "02", inicio, EMPRESAS[n][1], "2026-10", "2026-10-20")
        for n, o, inicio in FILIAIS
    ]
    # um retrato que só fica público depois do dia, com uma empresa nova: não entra
    linhas.append(
        (
            cnpj(SO_NO_FUTURO),
            r(SO_NO_FUTURO),
            True,
            "02",
            "2026-10-01",
            TI,
            "2026-11",
            FUTURO,
        )
    )
    tabela = pd.DataFrame(
        linhas,
        columns=["cnpj", "cnpj_basico", "matriz", "situacao_cadastral", "data_inicio_atividade",
                 "cnae_principal", "mes_do_retrato", "disponivel_em"],
    )  # fmt: skip
    tabela["data_inicio_atividade"] = pd.to_datetime(tabela["data_inicio_atividade"])
    tabela["disponivel_em"] = tabela["disponivel_em"].map(_dia)
    return tabela.assign(uf="SP", municipio="7107", **CARIMBOS)


def _empresas() -> pd.DataFrame:
    linhas = [
        (r(n), porte, "2026-10", "2026-10-20") for n, (_, _, porte) in EMPRESAS.items()
    ]
    linhas.append((r(SO_NO_FUTURO), "demais", "2026-11", FUTURO))
    tabela = pd.DataFrame(
        linhas, columns=["cnpj_basico", "porte", "mes_do_retrato", "disponivel_em"]
    )
    tabela["disponivel_em"] = tabela["disponivel_em"].map(_dia)
    return tabela.assign(
        razao_social="EMPRESA DE TESTE LTDA",
        natureza_juridica="2062",
        capital_social=1_000_000.0,
        n_estabelecimentos=1,
        **CARIMBOS,
    )


def _fca() -> pd.DataFrame:
    linhas = [
        (cnpj(ABERTA), "2020-01-10"),  # companhia aberta: sai de todas as contas
        (
            cnpj(12),
            FUTURO,
        ),  # o registro na CVM só fica público depois do dia: ainda é fechada
    ]
    tabela = pd.DataFrame(linhas, columns=["cnpj", "conhecido_em"])
    tabela["conhecido_em"] = pd.to_datetime(tabela["conhecido_em"])
    return tabela.assign(
        id_documento=1, referencia=pd.Timestamp("2019-12-31"), empresa="COMPANHIA DE TESTE",
        categoria="A", origem_coletada_em=pd.Timestamp("2020-01-10"), ano_do_arquivo=2020, versao=1,
        **CARIMBOS,
    )  # fmt: skip


def _simples() -> pd.DataFrame:
    linhas = [
        (1, "2025-09", "2025-09-15", True), (1, "2026-09", "2026-09-15", False),  # saiu
        (2, "2025-09", "2025-09-15", True),  # continua
        (3, "2025-09", "2025-09-15", True), (3, "2026-11", FUTURO, False),  # a saída ainda não é pública
        (ABERTA, "2025-09", "2025-09-15", True), (ABERTA, "2026-09", "2026-09-15", False),
        (BAIXADA, "2025-09", "2025-09-15", True), (BAIXADA, "2026-09", "2026-09-15", False),
    ]  # fmt: skip
    tabela = pd.DataFrame(
        [(r(n), m, _dia(d), o) for n, m, d, o in linhas],
        columns=["cnpj_basico", "mes_do_retrato", "disponivel_em", "optante_simples"],
    )
    return tabela.assign(consta=True, optante_mei=False, **CARIMBOS)


def _socias() -> pd.DataFrame:
    linhas = [
        (
            12,
            13,
            "entrou",
            "2026-05-01",
            "2026-05",
            "2026-05-15",
        ),  # entrou na janela; 3 níveis
        (13, 14, "entrou", "2020-01-01", "2020-02", "2020-02-15"),
        (14, 15, "entrou", "2024-01-01", "2024-02", "2024-02-15"),
        (
            2,
            99,
            "entrou",
            "2026-10-01",
            "2026-11",
            FUTURO,
        ),  # a entrada ainda não é pública
        (1, 3, "entrou", "2025-03-01", "2025-04", "2025-04-15"),
        (1, 3, "saiu", "2025-03-01", "2026-06", "2026-06-15"),  # saiu: não é mais sócia
    ]
    tabela = pd.DataFrame(
        [(r(a), r(b), mov, ent, mes, _dia(d)) for a, b, mov, ent, mes, d in linhas],
        columns=["cnpj_basico", "raiz_socio_pj", "movimento", "data_entrada", "mes_do_retrato",
                 "disponivel_em"],
    )  # fmt: skip
    tabela["data_entrada"] = pd.to_datetime(tabela["data_entrada"])
    return tabela.assign(qualificacao="22", **CARIMBOS)


def _arquivista(linhas, **extras) -> pd.DataFrame:
    """id, visto em (= público em), consta, é pessoa, documento: o formato do arquivista."""
    tabela = pd.DataFrame(
        linhas,
        columns=["id_na_fonte", "visto_em", "consta", "trata_como_pessoa", "cnpj"],
    )
    tabela["visto_em"] = pd.to_datetime(tabela["visto_em"])
    tabela["disponivel_em"] = tabela["visto_em"].dt.date
    tabela["cnpj_basico"] = tabela["cnpj"].str[:8]
    tabela["origem_coletada_em"] = tabela["visto_em"]
    return tabela.assign(**extras, **CARIMBOS)


def _credito(linhas) -> pd.DataFrame:
    """Linhas de crédito: as do arquivista mais a data do contrato."""
    tabela = _arquivista([linha[:5] for linha in linhas])
    tabela["contratado_em"] = pd.to_datetime([linha[5] for linha in linhas])
    return tabela.assign(modalidade="nao_automatica")


def _bndes() -> pd.DataFrame:
    return _credito([
        ("b1", "2026-11-04", True, False, cnpj(6), "2016-05-01"),
        ("b2", "2026-11-04", True, False, cnpj(7), "2012-01-01"),  # antes de 2015
        ("b3", "2026-11-04", True, True, cnpj(8), "2018-01-01"),  # marcada como pessoa
        ("b4", "2026-11-04", True, False, cnpj(9), "2019-01-01"),
        ("b4", "2026-11-05", False, False, cnpj(9), "2019-01-01"),  # saiu da fonte
        ("b5", FUTURO, True, False, cnpj(11), "2020-01-01"),  # ainda não visto no dia
        ("b6", "2026-11-04", True, False, cnpj(ABERTA), "2020-01-01"),
    ])  # fmt: skip


def _finep() -> pd.DataFrame:
    return _credito([
        ("f1", "2026-11-04", True, False, cnpj(6), "2017-01-01"),
        ("f2", "2026-11-04", True, False, cnpj(10), "2019-01-01"),
        ("f3", "2026-11-04", True, False, "00000000000", "2019-01-01"),  # 11 dígitos: não é empresa
    ])  # fmt: skip


def _rde() -> pd.DataFrame:
    tabela = _arquivista([
        ("e1", "2026-10-29", True, False, cnpj(8)),
        ("e2", "2026-10-29", True, True, cnpj(9)),  # marcada como pessoa
        ("e3", FUTURO, True, False, cnpj(10)),  # ainda não vista
    ])  # fmt: skip
    return tabela.drop(columns="cnpj").assign(
        codigo_rde="X", pais="PT", ocorrencia="registro", uf="SP", mes="2026-09"
    )


def _inpi(*numeros: int) -> pd.DataFrame:
    linhas = [(f"i{n}", "2026-10-14", True, False, cnpj(n)) for n in numeros]
    return _arquivista(linhas, numero_inpi="BR000")


def _pgfn() -> pd.DataFrame:
    linhas = [
        ("2024-12-31", "2025-01-10", 13, "2020-01-01"),
        (
            "2024-12-31",
            "2025-01-10",
            2,
            "2024-09-01",
        ),  # inscrita menos de 12 meses antes da RJ
        ("2026-09-30", "2026-10-10", 6, "2020-01-01"),
        ("2026-09-30", "2026-10-10", 12, "2021-01-01"),
        ("2026-09-30", "2026-10-10", 2, "2024-09-01"),
        ("2026-10-31", FUTURO, 7, "2020-01-01"),  # retrato ainda não público
    ]
    tabela = pd.DataFrame(
        [(pd.Timestamp(d).date(), _dia(p), cnpj(n), pd.Timestamp(i).date()) for d, p, n, i in linhas],
        columns=["data_do_retrato", "disponivel_em", "cnpj", "primeira_inscricao"],
    )  # fmt: skip
    tabela["cnpj_basico"] = tabela["cnpj"].str[:8]
    return tabela.assign(
        trata_como_pessoa=False, tipo_devedor="principal", valor_consolidado=1000.0,
        origem_coletada_em=pd.Timestamp("2026-10-10"), **CARIMBOS,
    )  # fmt: skip


def _anvisa() -> pd.DataFrame:
    linhas = [
        (12, "2026-01-01", 2),
        (13, "2026-01-01", 1),
        (14, "2026-01-01", 3), (14, "2026-06-01", 0),  # a autorização mais nova não está ativa
    ]  # fmt: skip
    tabela = pd.DataFrame(
        [(r(n), _dia(d), a) for n, d, a in linhas],
        columns=["cnpj_basico", "disponivel_em", "afe_ativos"],
    )
    return tabela.assign(trata_como_pessoa=False, afe_total=3, **CARIMBOS)


def _situacao_especial() -> pd.DataFrame:
    linhas = [
        (
            13,
            "2025-06-01",
            "2025-06-10",
        ),  # devia havia mais de 12 meses na lista pública do dia
        (2, "2025-03-01", "2025-03-10"),  # devia, mas inscrita havia menos de 12 meses
        (
            3,
            "2024-06-01",
            "2024-06-10",
        ),  # sem lista da PGFN pública no dia: fica de fora
        (1, "2026-10-01", FUTURO),  # a recuperação ainda não é pública
    ]
    tabela = pd.DataFrame(
        [(cnpj(n), r(n), pd.Timestamp(e).date(), d[:7], _dia(d)) for n, e, d in linhas],
        columns=["cnpj", "cnpj_basico", "data_situacao_especial", "mes_do_retrato",
                 "disponivel_em"],
    )  # fmt: skip
    return tabela.assign(
        rotulo=fechadas.RECUPERACAO_JUDICIAL, situacao_especial="RECUPERACAO JUDICIAL", matriz=True,
        trata_como_pessoa=False, origem_coletada_em=pd.Timestamp("2026-10-10"), **CARIMBOS,
    )  # fmt: skip


ARQUIVOS = {
    "cnpj_estabelecimentos_pj/1.parquet": _estabelecimentos,
    "cnpj_empresas_pj/1.parquet": _empresas,
    "fca_geral/1.parquet": _fca,
    "cnpj_simples_historico/1.parquet": _simples,
    "entradas_de_socio_pj/1.parquet": _socias,
    "financiamentos_bndes/1.parquet": _bndes,
    "financiamentos_finep/1.parquet": _finep,
    "bcb_rde_ied/1.parquet": _rde,
    "pgfn_divida/2026/1.parquet": _pgfn,
    "anvisa_por_empresa/1.parquet": _anvisa,
    "cnpj_situacao_especial/1.parquet": _situacao_especial,
    "inpi_marcas_titulares/1.parquet": lambda: _inpi(8, 10),
    "inpi_patentes_depositantes/1.parquet": lambda: _inpi(10),
}


def _montar(pasta, sem: tuple[str, ...] = ()):
    for caminho, fazer in ARQUIVOS.items():
        if caminho.split("/")[0] not in sem:
            _gravar(pasta / caminho, fazer())
    return pasta


@pytest.fixture
def porta(tmp_path, banco):
    return Porta(_montar(tmp_path / "base"), banco)


@pytest.fixture
def sem_minimo(monkeypatch):
    """A base de mentira é pequena: as contas são conferidas uma a uma, sem o mínimo de 10."""
    monkeypatch.setattr(fechadas, "MINIMO_DA_CONTAGEM", 1)


# (todo, parte) de cada cartão, contado à mão na base acima
ESPERADO = {
    "saiu_do_simples": (
        3,
        1,
    ),  # 1, 2 e 3 eram optantes; só a 1 saiu (a saída da 3 é do futuro)
    "tres_filiais": (ATIVAS_FECHADAS, 1),  # só a 6 abriu 3 filiais na janela
    "bndes_e_finep": (
        2,
        1,
    ),  # BNDES: 6 e 7 (8 é pessoa, 9 saiu, 11 é do futuro); Finep: 6
    "socia_entrou": (ATIVAS_FECHADAS, 1),  # a 12 (a entrada na 2 é do futuro)
    "capital_estrangeiro": (ATIVAS_FECHADAS, 1),  # a 8 (a 9 é pessoa, a 10 é do futuro)
    "tres_niveis": (3, 1),  # 12 → 13 → 14 → 15
    "bndes_e_divida": (1, 1),  # só a 6 contratou desde 2015, e deve
    "anvisa_e_divida": (
        2,
        1,
    ),  # 12 e 13 têm AFE ativa (a da 14 não está mais); a 12 deve
    "recuperacao_e_divida": (
        2,
        1,
    ),  # 13 e 2 tinham lista pública; só a 13 devia havia 12 meses
    "industria_e_marca": (2, 1),  # 8 e 9 (a 10 é pequena, a 11 é varejo); a 8 tem marca
    "finep_e_patente": (2, 1),  # 6 e 10 têm Finep; a 10 tem patente
}


def _medicao(porta) -> fechadas.MedicaoDasFechadas:
    return fechadas.medir_fechadas(porta, catalogo(), DIA)


@pytest.mark.usefixtures("sem_minimo")
def test_cada_cartao_conta_o_que_a_base_diz(porta):
    medicao = _medicao(porta)
    contas = {c.chave: (c.todo, c.parte) for c in medicao.cartoes}
    assert contas == ESPERADO
    assert medicao.medido_em == DIA.isoformat()


@pytest.mark.usefixtures("sem_minimo")
def test_a_lista_da_cgu_e_so_de_uso_interno_e_derruba_o_cartao(porta):
    caidos = {c.chave: c.motivo for c in _medicao(porta).caidos}
    assert set(caidos) == {"tce_e_sancao"}
    assert "sancoes_cgu" in caidos["tce_e_sancao"]


def test_os_cartoes_seguem_os_grupos_da_pagina():
    nos_grupos = [c for g in fechadas.GRUPOS for c in g.cartoes]
    assert sorted(nos_grupos) == sorted(m.chave for m in fechadas.MOLDES)
    assert len(nos_grupos) == len(set(nos_grupos)) == 12


@pytest.mark.usefixtures("sem_minimo")
def test_sem_olhar_o_futuro_a_medicao_antiga_nao_muda_com_o_que_veio_depois(
    tmp_path, banco
):
    """Cortar o futuro não muda o passado: a base inteira e a base só com o que era público no dia dão o
    mesmo número."""
    inteira = _medicao(Porta(_montar(tmp_path / "inteira"), banco))
    cortada = tmp_path / "cortada"
    _montar(cortada)
    for arquivo in cortada.rglob("*.parquet"):
        tabela = pd.read_parquet(arquivo)
        coluna = "conhecido_em" if "conhecido_em" in tabela else "disponivel_em"
        publico = pd.to_datetime(tabela[coluna]).dt.date
        _gravar(arquivo, tabela[publico < _dia(FUTURO)])
    assert _medicao(Porta(cortada, banco)) == inteira


def test_com_o_minimo_de_verdade_a_base_pequena_nao_mostra_nada(porta):
    medicao = _medicao(porta)
    assert medicao.cartoes == ()
    motivos = {c.chave: c.motivo for c in medicao.caidos}
    assert set(motivos) == {m.chave for m in fechadas.MOLDES}
    assert {m for k, m in motivos.items() if k != "tce_e_sancao"} == {
        "contagem abaixo de 10"
    }
    assert not fechadas.de_pe_o_bastante(medicao)


@pytest.mark.parametrize("minimo, de_pe", [(1, True), (2, False)])
def test_a_contagem_abaixo_do_minimo_cai_inteira(porta, monkeypatch, minimo, de_pe):
    """O cartão cai se a parte ou o todo ficam abaixo do mínimo: nenhum número parcial sai."""
    monkeypatch.setattr(fechadas, "MINIMO_DA_CONTAGEM", minimo)
    chaves = {c.chave for c in _medicao(porta).cartoes}
    assert ("saiu_do_simples" in chaves) is de_pe


@pytest.mark.usefixtures("sem_minimo")
def test_tabela_fora_da_porta_derruba_so_os_cartoes_dela(tmp_path, banco):
    porta = Porta(
        _montar(tmp_path / "base", sem=("inpi_patentes_depositantes",)), banco
    )
    medicao = _medicao(porta)
    caidos = {c.chave: c.motivo for c in medicao.caidos}
    assert (
        caidos["finep_e_patente"]
        == "inpi_patentes_depositantes: não está montada na porta"
    )
    assert {c.chave for c in medicao.cartoes} == set(ESPERADO) - {"finep_e_patente"}


def test_sem_a_base_da_receita_nada_e_medido(tmp_path, banco):
    porta = Porta(_montar(tmp_path / "base", sem=("cnpj_empresas_pj",)), banco)
    medicao = _medicao(porta)
    assert medicao.cartoes == ()
    assert {c.motivo for c in medicao.caidos if c.chave != "tce_e_sancao"} == {
        "cnpj_empresas_pj: não está montada na porta"
    }


def test_antes_de_qualquer_retrato_publico_nada_e_medido(porta):
    medicao = fechadas.medir_fechadas(porta, catalogo(), date(2026, 1, 1))
    assert medicao.cartoes == ()
    assert {c.motivo for c in medicao.caidos} >= {
        "sem retrato da Receita público no dia"
    }


@pytest.mark.parametrize(
    "mexer, motivo",
    [
        (lambda c: c["tabelas"].pop("pgfn_divida"), "pgfn_divida: fora do catálogo"),
        (lambda c: None, None),
    ],
)
def test_as_travas_da_tabela(mexer, motivo):
    entrada = catalogo()
    mexer(entrada)
    assert fechadas.motivo_da_tabela("pgfn_divida", entrada, {"pgfn_divida"}) == motivo
    assert "não é vendável" in (
        fechadas.motivo_da_tabela("sancoes_cgu", entrada, {"sancoes_cgu"}) or ""
    )


def test_as_tabelas_dos_cartoes_tem_as_colunas_que_o_sql_le():
    """Os cartões leem colunas do contrato de cada tabela; a que guarda pessoa tem a marca que a separa."""
    from base.dicionario import TABELAS

    precisa = {
        fechadas.EMPRESAS: {"cnpj_basico", "porte", "mes_do_retrato"},
        fechadas.ESTABELECIMENTOS: {"cnpj_basico", "matriz", "situacao_cadastral",
                                    "data_inicio_atividade", "cnae_principal", "mes_do_retrato"},
        fechadas.FCA: {"cnpj"},
        fechadas.SIMPLES: {"cnpj_basico", "optante_simples", "consta", "mes_do_retrato"},
        fechadas.SOCIAS: {"cnpj_basico", "raiz_socio_pj", "movimento", "data_entrada", "mes_do_retrato"},
        fechadas.BNDES: {"id_na_fonte", "cnpj", "contratado_em", "consta", "trata_como_pessoa"},
        fechadas.FINEP: {"id_na_fonte", "cnpj", "contratado_em", "consta", "trata_como_pessoa"},
        fechadas.RDE: {"id_na_fonte", "visto_em", "cnpj_basico", "consta", "trata_como_pessoa"},
        fechadas.PGFN: {"cnpj", "data_do_retrato", "primeira_inscricao"},
        fechadas.ANVISA: {"cnpj_basico", "afe_ativos"},
        fechadas.SITUACAO_ESPECIAL: {"cnpj_basico", "rotulo", "data_situacao_especial"},
        fechadas.MARCAS: {"id_na_fonte", "visto_em", "cnpj", "consta", "trata_como_pessoa"},
        fechadas.PATENTES: {"id_na_fonte", "visto_em", "cnpj", "consta", "trata_como_pessoa"},
    }  # fmt: skip
    for nome, colunas in precisa.items():
        assert colunas <= set(TABELAS[nome].colunas), (
            nome,
            colunas - set(TABELAS[nome].colunas),
        )
        assert "publico_em" in TABELAS[nome].datas, nome


@pytest.mark.usefixtures("sem_minimo")
def test_a_fotografia_volta_igual(porta):
    medicao = _medicao(porta)
    assert (
        fechadas.fechadas_da_fotografia(fechadas.para_a_fotografia(medicao)) == medicao
    )
    with pytest.raises(TypeError):
        fechadas.fechadas_da_fotografia(
            {
                **fechadas.para_a_fotografia(medicao),
                "cartoes": [{"chave": "x", "parte": 1}],
            }
        )


def test_o_minimo_de_cartoes_de_pe():
    um = fechadas.CartaoMedido("saiu_do_simples", parte=10, todo=20)
    poucos = fechadas.MedicaoDasFechadas("2026-11-10", (um,) * 7, ())
    assert not fechadas.de_pe_o_bastante(poucos)
    assert fechadas.de_pe_o_bastante(replace(poucos, cartoes=(um,) * 8))


def test_doze_meses_antes():
    assert fechadas.doze_meses_antes(date(2026, 11, 10)) == date(2025, 11, 10)
    assert fechadas.doze_meses_antes(date(2024, 2, 29)) == date(2023, 2, 28)
