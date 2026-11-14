"""Os cruzamentos de empresa fechada da página inicial (linha 925): só contagens, só pessoa jurídica.

Base de mentira, sem internet; as raízes são de ninguém. A porta é a de verdade (`base.porta.Porta`) sobre
parquets numa pasta do teste, com os mesmos apelidos de data que o servidor usa. Riscos: contar companhia
aberta, empresa baixada, associação, empresa do Estado ou linha de pessoa; olhar o futuro (retrato, entrada de sócia, contrato ou lista da
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


ABERTA, BAIXADA, SO_NO_FUTURO, ASSOCIACAO, EMPRESA_PUBLICA = 4, 5, 16, 17, 18
# natureza jurídica fora da sociedade empresária privada: ativas, mas não são empresa fechada
NATUREZAS = {ASSOCIACAO: "3999", EMPRESA_PUBLICA: "2011"}
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
    ASSOCIACAO: ("02", TI, "micro"),
    EMPRESA_PUBLICA: ("02", INDUSTRIA, "demais"),
}
ATIVAS_FECHADAS = len(
    [
        n
        for n, (s, *_) in EMPRESAS.items()
        if s == "02" and n != ABERTA and n not in NATUREZAS
    ]
)


# UF da matriz, para o recorte: ímpar em SP, par em MG, e a 15 sem UF no retrato
def uf(numero: int) -> str:
    return "" if numero == 15 else ("SP" if numero % 2 else "MG")


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
    tabela["uf"] = [uf(int(raiz[-2:])) for raiz in tabela["cnpj_basico"]]
    return tabela.assign(municipio="7107", **CARIMBOS)


def _empresas() -> pd.DataFrame:
    linhas = [
        (r(n), porte, NATUREZAS.get(n, "2062"), "2026-10", "2026-10-20")
        for n, (_, _, porte) in EMPRESAS.items()
    ]
    linhas.append((r(SO_NO_FUTURO), "demais", "2062", "2026-11", FUTURO))
    tabela = pd.DataFrame(
        linhas,
        columns=[
            "cnpj_basico",
            "porte",
            "natureza_juridica",
            "mes_do_retrato",
            "disponivel_em",
        ],
    )
    tabela["disponivel_em"] = tabela["disponivel_em"].map(_dia)
    return tabela.assign(
        razao_social="EMPRESA DE TESTE LTDA",
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
        (1, "2025-09", "2025-09-15", True, True), (1, "2026-09", "2026-09-15", False, True),  # saiu
        # continua: a linha mais nova não consta no retrato e não vale como saída
        (2, "2025-09", "2025-09-15", True, True), (2, "2026-09", "2026-09-15", False, False),
        (3, "2025-09", "2025-09-15", True, True), (3, "2026-11", FUTURO, False, True),  # saída do futuro
        (ABERTA, "2025-09", "2025-09-15", True, True), (ABERTA, "2026-09", "2026-09-15", False, True),
        (BAIXADA, "2025-09", "2025-09-15", True, True), (BAIXADA, "2026-09", "2026-09-15", False, True),
        (ASSOCIACAO, "2025-09", "2025-09-15", True, True),
        (ASSOCIACAO, "2026-09", "2026-09-15", False, True),
    ]  # fmt: skip
    tabela = pd.DataFrame(
        [(r(n), m, _dia(d), o, c) for n, m, d, o, c in linhas],
        columns=[
            "cnpj_basico",
            "mes_do_retrato",
            "disponivel_em",
            "optante_simples",
            "consta",
        ],
    )
    return tabela.assign(optante_mei=False, **CARIMBOS)


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
    linhas += [
        ("i9a", "2026-10-14", False, False, cnpj(9)),  # saiu da fonte: não conta
        ("i9b", "2026-10-14", True, True, cnpj(9)),  # marcada como pessoa: não conta
    ]  # fmt: skip
    return _arquivista(linhas, numero_inpi="BR000")


def _pgfn() -> pd.DataFrame:
    linhas = [
        ("2024-12-31", "2025-01-10", cnpj(13), "2020-01-01", False),
        (
            "2024-12-31",
            "2025-01-10",
            cnpj(2),
            "2024-09-01",
            False,
        ),  # inscrita < 12 meses antes da RJ
        ("2026-09-30", "2026-10-10", cnpj(6), "2020-01-01", False),
        ("2026-09-30", "2026-10-10", cnpj(12), "2021-01-01", False),
        ("2026-09-30", "2026-10-10", cnpj(2), "2024-09-01", False),
        # a 13 tem AFE ativa e não deve: um documento de 11 dígitos que começa pela raiz dela não é CNPJ,
        # e a linha marcada como pessoa também não conta
        ("2026-09-30", "2026-10-10", f"{r(13)}123", "2021-01-01", False),
        ("2026-09-30", "2026-10-10", cnpj(13), "2021-01-01", True),
        (
            "2026-10-31",
            FUTURO,
            cnpj(7),
            "2020-01-01",
            False,
        ),  # retrato ainda não público
    ]
    tabela = pd.DataFrame(
        [(pd.Timestamp(d).date(), _dia(p), c, pd.Timestamp(i).date(), pessoa)
         for d, p, c, i, pessoa in linhas],
        columns=["data_do_retrato", "disponivel_em", "cnpj", "primeira_inscricao", "trata_como_pessoa"],
    )  # fmt: skip
    tabela["cnpj_basico"] = tabela["cnpj"].str[:8]
    return tabela.assign(
        tipo_devedor="principal", valor_consolidado=1000.0,
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
    # 8 e 9 (a 10 é pequena, a 11 é varejo, a 18 é empresa pública); a 8 tem marca (as da 9 não valem)
    "industria_e_marca": (2, 1),
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
                                    "data_inicio_atividade", "cnae_principal", "mes_do_retrato", "uf"},
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


@pytest.mark.parametrize(
    "todo, parte, cai",
    [
        (20, 10, False),
        (20, 20, False),  # todas: o que sobra é zero, nada aponta para ninguém
        (20, 9, True),  # parte abaixo do mínimo
        (9, 9, True),  # todo abaixo do mínimo
        (105, 100, True),  # sobram 5: o complemento também aponta para poucas empresas
        (110, 100, False),
        (10, 11, True),  # parte maior que o todo é erro
    ],
)
def test_motivo_da_contagem(todo, parte, cai):
    assert (fechadas.motivo_da_contagem(todo, parte) is not None) is cai


@pytest.mark.parametrize("todo, parte", [(105, 100), (20, 9), (10, 11)])
def test_a_fotografia_com_contagem_que_nao_sai_e_recusada(todo, parte):
    gravada = {
        "medido_em": "2026-11-14",
        "cartoes": [{"chave": "tres_filiais", "parte": parte, "todo": todo}],
        "caidos": [],
    }
    with pytest.raises(ValueError, match="tres_filiais"):
        fechadas.fechadas_da_fotografia(gravada)


def test_o_minimo_de_cartoes_de_pe():
    um = fechadas.CartaoMedido("saiu_do_simples", parte=10, todo=20)
    poucos = fechadas.MedicaoDasFechadas("2026-11-10", (um,) * 7, ())
    assert not fechadas.de_pe_o_bastante(poucos)
    assert fechadas.de_pe_o_bastante(replace(poucos, cartoes=(um,) * 8))


def test_doze_meses_antes():
    assert fechadas.doze_meses_antes(date(2026, 11, 10)) == date(2025, 11, 10)
    assert fechadas.doze_meses_antes(date(2024, 2, 29)) == date(2023, 2, 28)


# --- o recorte por UF e por setor (2º PR da linha 925) -----------------------------------------------------


@pytest.fixture
def sem_minimo_nenhum(monkeypatch):
    """Sem mínimo nenhum: a célula com parte zero também sai, para conferir a conta crua."""
    monkeypatch.setattr(fechadas, "MINIMO_DA_CONTAGEM", 0)


def _recortes(
    porta,
) -> tuple[fechadas.MedicaoDasFechadas, fechadas.RecortesDasFechadas]:
    return fechadas.medir_fechadas_e_recortes(porta, catalogo(), DIA)


def _celulas(*trios) -> tuple[fechadas.Celula, ...]:
    return tuple(fechadas.Celula(chave, parte, todo) for chave, todo, parte in trios)


@pytest.mark.usefixtures("sem_minimo_nenhum")
def test_o_recorte_conta_cada_uf_e_cada_setor_da_matriz(porta):
    medicao, recortes = _recortes(porta)
    assert medicao == _medicao(porta)  # o recorte não muda a medição dos cartões
    assert recortes.caidos == ()
    por_cartao = {r.chave: r for r in recortes.cartoes}
    assert set(por_cartao) == set(ESPERADO)
    # 1, 2 e 3 eram optantes (1 e 3 em SP, 2 em MG); só a 1 saiu; todas de TI (seção J)
    assert por_cartao["saiu_do_simples"].por_uf == _celulas(("MG", 1, 0), ("SP", 2, 1))
    assert por_cartao["saiu_do_simples"].por_setor == _celulas(("J", 3, 1))
    # 8 (MG, com marca) e 9 (SP), as duas da indústria de transformação (seção C)
    assert por_cartao["industria_e_marca"].por_uf == _celulas(
        ("MG", 1, 1), ("SP", 1, 0)
    )
    assert por_cartao["industria_e_marca"].por_setor == _celulas(("C", 2, 1))
    # 13 (SP) devia havia 12 meses; 2 (MG) não
    assert por_cartao["recuperacao_e_divida"].por_uf == _celulas(
        ("MG", 1, 0), ("SP", 1, 1)
    )
    # a 15 não tem UF no retrato: fica na célula "nd"
    assert "nd" in {c.chave for c in por_cartao["tres_filiais"].por_uf}


@pytest.mark.usefixtures("sem_minimo_nenhum")
def test_as_celulas_de_cada_recorte_somam_o_cartao(porta):
    medicao, recortes = _recortes(porta)
    cartoes = {c.chave: c for c in medicao.cartoes}
    for recorte in recortes.cartoes:
        cartao = cartoes[recorte.chave]
        for celulas in (recorte.por_uf, recorte.por_setor):
            assert sum(c.todo or 0 for c in celulas) == cartao.todo, recorte.chave
            assert sum(c.parte or 0 for c in celulas) == cartao.parte, recorte.chave


@pytest.mark.usefixtures("sem_minimo_nenhum")
def test_sem_olhar_o_futuro_o_recorte_antigo_nao_muda_com_o_que_veio_depois(
    tmp_path, banco
):
    inteira = _recortes(Porta(_montar(tmp_path / "inteira"), banco))
    cortada = tmp_path / "cortada"
    _montar(cortada)
    for arquivo in cortada.rglob("*.parquet"):
        tabela = pd.read_parquet(arquivo)
        coluna = "conhecido_em" if "conhecido_em" in tabela else "disponivel_em"
        publico = pd.to_datetime(tabela[coluna]).dt.date
        _gravar(arquivo, tabela[publico < _dia(FUTURO)])
    assert _recortes(Porta(cortada, banco)) == inteira


@pytest.mark.usefixtures("sem_minimo_nenhum")
def test_recorte_que_nao_fecha_com_o_total_cai_inteiro(porta, monkeypatch):
    """Se as partes do recorte contam outra coisa que o cartão, o recorte daquele cartão cai e os outros
    seguem; o cartão em si fica de pé."""
    torto = fechadas.Partes(
        "SELECT raiz FROM ativas LIMIT 1", "SELECT raiz FROM ativas LIMIT 0"
    )
    moldes = tuple(
        replace(m, partes=lambda: torto) if m.chave == "tres_filiais" else m
        for m in fechadas.MOLDES
    )
    monkeypatch.setattr(fechadas, "MOLDES", moldes)
    medicao, recortes = _recortes(porta)
    assert "tres_filiais" in {c.chave for c in medicao.cartoes}
    assert {c.chave: c.motivo for c in recortes.caidos} == {
        "tres_filiais": "o recorte não fecha com o total do cartão"
    }
    assert {r.chave for r in recortes.cartoes} == set(ESPERADO) - {"tres_filiais"}


def test_com_o_minimo_de_verdade_nao_ha_recorte(porta):
    medicao, recortes = _recortes(porta)
    assert medicao.cartoes == () and recortes.cartoes == () and recortes.caidos == ()


@pytest.mark.parametrize(
    "contagens, escondidas",
    [
        ({"SP": (50, 20), "MG": (30, 15)}, set()),  # todas saem
        # a AC é pequena; sozinha, sairia pela subtração: a menor das outras (MG) cai junto
        ({"SP": (50, 20), "MG": (30, 15), "AC": (3, 1)}, {"AC", "MG"}),
        # AC e RJ somadas ainda têm parte 6: cai também a MG
        (
            {"SP": (50, 20), "MG": (30, 15), "RJ": (12, 5), "AC": (3, 1)},
            {"AC", "RJ", "MG"},
        ),
        # AC e RJ somadas (todo 30, parte 15) já podem sair: nada mais cai
        (
            {"SP": (50, 20), "MG": (30, 15), "RJ": (21, 10), "AC": (9, 5)},
            {"AC"} | {"RJ"},
        ),
        ({"SP": (5, 1), "MG": (3, 1)}, {"SP", "MG"}),  # nenhuma sai
        ({"SP": (100, 95)}, {"SP"}),  # o complemento (5) também é pequeno
    ],
)
def test_celulas_que_saem(contagens, escondidas):
    celulas = fechadas.celulas_que_saem(contagens)
    assert [c.chave for c in celulas] == sorted(contagens)
    assert {c.chave for c in celulas if c.todo is None} == escondidas
    for celula in celulas:
        assert (celula.todo is None) is (celula.parte is None)
        if celula.todo is not None:
            assert (celula.todo, celula.parte) == contagens[celula.chave]
            assert fechadas.motivo_da_contagem(celula.todo, celula.parte) is None
    tiradas = [contagens[c.chave] for c in celulas if c.todo is None]
    if tiradas and len(tiradas) < len(contagens):
        soma = (sum(t for t, _ in tiradas), sum(p for _, p in tiradas))
        assert (
            fechadas.motivo_da_contagem(*soma) is None
        )  # o que some não se deduz pela subtração


def test_as_divisoes_do_cnae_tem_secao():
    secoes = dict(fechadas.SECAO_DA_DIVISAO)
    assert secoes["62"] == "J" and secoes["10"] == "C" and secoes["47"] == "G"
    assert set(secoes.values()) <= set(fechadas.cnae.SECOES)
