"""Eventos de PJ com três estados (src/eventos_de_pj/, N5 do mapa do Plano Mestre v3.1).

O motor e as três fontes do primeiro corte: o informe mensal de FIDC, o cadastro da Receita (a vista do CNPJ)
e o cadastro de companhias abertas da CVM. Cada fonte mostra os três estados: **mudou**, **não observado** e
**fonte falhou**. Tudo sintético, menos a vista do CNPJ de exemplo (`tests/ajudantes_do_cnpj.py`).
"""

import json
from datetime import UTC, date, datetime, timedelta

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from base import cnpj as cnpj_base
from base.receita_diff import disponivel_em as publicacao_da_receita
from scripts import montar_vista_do_cnpj
from src.banco.coletas import registrar_arquivo
from src.cadastro_da_receita import CadastroDaReceita
from src.eventos_de_pj import cadastro_cvm, cadastro_receita, fidc, registro
from src.eventos_de_pj.evento import (
    FONTE_FALHOU,
    MUDOU,
    NAO_OBSERVADO,
    DescricaoDaFonte,
    Leitura,
    Tentativa,
    como_era_em,
    eventos_das_leituras,
    leitura_ok,
)
from src.securitizacao.monitoramento import eventos_do_mes
from tests import ajudantes_do_cnpj as exemplo


def _cnpj(k: int) -> str:
    base12 = f"{k:08d}0001"
    return base12 + cnpj_base.digitos_verificadores(base12)


A, B, C = _cnpj(1), _cnpj(2), _cnpj(3)
FONTE = DescricaoDaFonte(
    "teste", "pj", "arquivo de teste", "eventos_teste 1", "campo lido como veio"
)


def _leitura(dia: date, objetos=None, ok=True) -> Leitura:
    return Leitura(periodo=dia, publico_em=dia, ok=ok, objetos=objetos or {})


def _estados(eventos) -> list[tuple[str, str, str]]:
    return [(e.objeto_id, e.estado, e.assunto) for e in eventos]


# ---------------------------------------------------------------- o motor


def test_campo_diferente_da_leitura_anterior_vira_mudou_com_antes_e_depois():
    eventos = eventos_das_leituras(
        [
            _leitura(date(2026, 8, 1), {A: {"situacao": "ATIVO"}}),
            _leitura(date(2026, 9, 1), {A: {"situacao": "CANCELADA"}}),
        ],
        FONTE,
    )
    assert _estados(eventos) == [(A, MUDOU, "situacao")]
    (evento,) = eventos
    assert evento.publico_em == evento.ocorrido_em == date(2026, 9, 1)
    assert [(e.campo, e.antes, e.depois) for e in evento.evidencia] == [
        ("situacao", "ATIVO", "CANCELADA")
    ]


def test_esperado_que_sumiu_vira_nao_observado():
    eventos = eventos_das_leituras(
        [
            _leitura(date(2026, 8, 1), {A: {}, B: {}}),
            _leitura(date(2026, 9, 1), {A: {}}),
        ],
        FONTE,
    )
    assert _estados(eventos) == [(B, NAO_OBSERVADO, "leitura")]


def test_leitura_que_falhou_nao_parece_um_mes_calmo():
    calmo = eventos_das_leituras(
        [_leitura(date(2026, 8, 1), {A: {}}), _leitura(date(2026, 9, 1), {A: {}})],
        FONTE,
    )
    falhou = eventos_das_leituras(
        [_leitura(date(2026, 8, 1), {A: {}}), _leitura(date(2026, 9, 1), ok=False)],
        FONTE,
    )
    assert calmo == []
    assert _estados(falhou) == [(A, FONTE_FALHOU, "leitura")]


def test_depois_da_falha_a_comparacao_e_com_a_ultima_leitura_boa():
    eventos = eventos_das_leituras(
        [
            _leitura(date(2026, 8, 1), {A: {"uf": "SP"}}),
            _leitura(date(2026, 9, 1), ok=False),
            _leitura(date(2026, 10, 1), {A: {"uf": "RJ"}}),
        ],
        FONTE,
    )
    assert _estados(eventos) == [(A, FONTE_FALHOU, "leitura"), (A, MUDOU, "uf")]
    assert eventos[1].evidencia[0].antes == "SP"


def test_esperados_dados_valem_mesmo_sem_leitura_anterior():
    eventos = eventos_das_leituras(
        [_leitura(date(2026, 9, 1), {A: {}}), _leitura(date(2026, 10, 1), {B: {}})],
        FONTE,
        esperados=[cnpj_base.formatar(B)],
    )
    # B não estava em setembro: não observado; A não é esperado: nada
    assert _estados(eventos) == [(B, NAO_OBSERVADO, "leitura")]


def test_evento_publico_so_com_cnpj_e_rastro():
    (evento,) = eventos_das_leituras(
        [
            _leitura(date(2026, 8, 1), {cnpj_base.formatar(A): {}}),
            _leitura(date(2026, 9, 1)),
        ],
        FONTE,
    )
    assert evento.usuario_id is None
    assert evento.objeto_id == A  # os 14 caracteres, sem pontuação
    assert evento.rastro.fonte_id == "teste"
    assert evento.rastro.publicado_em == evento.publico_em
    dicionario = evento.como_dict()
    assert json.loads(json.dumps(dicionario)) == dicionario
    assert dicionario["estado"] == NAO_OBSERVADO


def test_mesmo_calculo_mesmo_id_e_ids_diferentes_entre_eventos():
    leituras = [
        _leitura(date(2026, 8, 1), {A: {"x": 1}, B: {}}),
        _leitura(date(2026, 9, 1), {A: {"x": 2}}),
        _leitura(date(2026, 10, 1), ok=False),
    ]
    um, outro = (
        eventos_das_leituras(leituras, FONTE),
        eventos_das_leituras(leituras, FONTE),
    )
    assert [e.evento_id for e in um] == [e.evento_id for e in outro]
    assert len({e.evento_id for e in um}) == len(um) == 3


def test_objeto_sem_forma_de_cnpj_e_recusado():
    with pytest.raises(ValueError, match="CNPJ"):
        eventos_das_leituras([_leitura(date(2026, 8, 1), {"FULANA DE TAL": {}})], FONTE)


def test_leitura_boa_e_a_que_teve_tentativa_ok_ate_o_dia():
    setembro = date(2026, 9, 1)
    tentativas = [
        Tentativa(setembro, date(2026, 9, 3), ok=False),
        Tentativa(setembro, date(2026, 9, 5), ok=True),
        Tentativa(date(2026, 10, 1), date(2026, 9, 4), ok=True),  # outro período
    ]
    assert not leitura_ok(tentativas, setembro, date(2026, 9, 4))
    assert leitura_ok(tentativas, setembro, date(2026, 9, 5))


_dias = st.dates(date(2026, 1, 1), date(2026, 3, 31))
_objetos = st.dictionaries(
    st.sampled_from([A, B, C]),
    st.dictionaries(st.sampled_from(["x", "y"]), st.integers(0, 2), max_size=2),
    max_size=3,
)
_leituras = st.lists(
    st.builds(
        Leitura, periodo=_dias, publico_em=_dias, ok=st.booleans(), objetos=_objetos
    ),
    max_size=8,
)


@settings(max_examples=150, deadline=None)
@given(leituras=_leituras, corte=_dias)
def test_cortar_o_futuro_nao_muda_o_passado(leituras, corte):
    """Só com as leituras públicas até o corte, saem os mesmos eventos de antes do corte."""
    com_tudo = eventos_das_leituras(leituras, FONTE)
    so_o_passado = eventos_das_leituras(
        [leitura for leitura in leituras if leitura.publico_em <= corte], FONTE
    )
    assert so_o_passado == como_era_em(com_tudo, corte)
    assert all(e.publico_em <= corte for e in so_o_passado)


# ---------------------------------------------------------------- FIDC (informe mensal da CVM)

JULHO, AGOSTO = pd.Timestamp("2026-07-31"), pd.Timestamp("2026-08-31")
PRAZO_DE_AGOSTO = date(2026, 10, 15)  # 31/08 + 45 dias


def _informe(cnpj: str, mes: pd.Timestamp, publico: str, inadimplente=10) -> dict:
    return {
        "cnpj_fundo": cnpj_base.formatar(cnpj),
        "nome": "FIDC EXEMPLO",
        "competencia": mes,
        "disponivel_em": pd.Timestamp(publico),
        "pl_das_classes": 1000.0,
        "pl_subordinado": 300.0,
        "carteira": 1000.0,
        "inadimplente": float(inadimplente),
        "maior_cedente": 0.2,
        "TAB_IV_A_VL_PL": 1000.0,
    }


@pytest.fixture
def informes() -> pd.DataFrame:
    return pd.DataFrame(
        [
            _informe(A, JULHO, "2026-08-14"),
            _informe(B, JULHO, "2026-08-14"),
            _informe(C, JULHO, "2026-08-14"),
            _informe(A, AGOSTO, "2026-09-14", inadimplente=120),  # 12%: quebra (B-15)
            _informe(C, AGOSTO, "2026-10-20"),  # entregou depois do prazo
            # B não entregou agosto
        ]
    )


def _tentativas_boas():
    return [
        Tentativa(JULHO.date(), date(2026, 8, 20), ok=True),
        Tentativa(AGOSTO.date(), date(2026, 9, 20), ok=True),
    ]


def test_fidc_os_eventos_da_b15_viram_mudou(informes):
    eventos = fidc.eventos_do_fidc(informes, _tentativas_boas())
    mudou = [e for e in eventos if e.estado == MUDOU]
    b15 = eventos_do_mes(informes, AGOSTO)
    assert [(e.objeto_id, e.assunto, e.objeto_tipo) for e in mudou] == [
        (A, "fidc_inadimplencia_limite_quebra", "fundo"),  # 12% da carteira
        (A, "fidc_inadimplencia_subindo", "fundo"),  # de 1% para 12%
    ]
    assert mudou == [evento.como_evento_de_pj() for evento in b15]
    assert {e.publico_em for e in mudou} == {date(2026, 9, 14)}
    assert [e.rastro for e in mudou] == [e.rastro for e in b15]
    assert [e.evento_id for e in mudou] == [e.evento_id for e in b15]


def test_fidc_quem_nao_entregou_no_prazo_vira_nao_observado(informes):
    eventos = fidc.eventos_do_fidc(informes, _tentativas_boas())
    ausentes = [e for e in eventos if e.estado == NAO_OBSERVADO]
    assert [(e.objeto_id, e.ocorrido_em, e.publico_em) for e in ausentes] == [
        (B, AGOSTO.date(), PRAZO_DE_AGOSTO),
        (C, AGOSTO.date(), PRAZO_DE_AGOSTO),  # a entrega atrasada não apaga o atraso
    ]


def test_fidc_sem_leitura_boa_do_mes_vira_fonte_falhou_e_nao_ausencia(informes):
    so_julho = [Tentativa(JULHO.date(), date(2026, 8, 20), ok=True),
                Tentativa(AGOSTO.date(), date(2026, 10, 1), ok=False)]  # fmt: skip
    eventos = fidc.eventos_do_fidc(informes, so_julho)
    falhas = [e for e in eventos if e.estado == FONTE_FALHOU]
    assert [(e.objeto_id, e.publico_em) for e in falhas] == [
        (A, PRAZO_DE_AGOSTO),
        (B, PRAZO_DE_AGOSTO),
        (C, PRAZO_DE_AGOSTO),
    ]
    assert not [e for e in eventos if e.estado == NAO_OBSERVADO]


def test_fidc_antes_do_prazo_a_ausencia_ainda_nao_existe(informes):
    eventos = fidc.eventos_do_fidc(
        informes, _tentativas_boas(), como_em=date(2026, 10, 14)
    )
    assert {e.estado for e in eventos} == {MUDOU}
    assert all(e.publico_em <= date(2026, 10, 14) for e in eventos)


@pytest.mark.parametrize(
    "corte",
    [date(2026, 9, 13), date(2026, 9, 30), date(2026, 10, 15), date(2026, 10, 21)],
)
def test_fidc_cortar_o_futuro_nao_muda_o_passado(informes, corte):
    publicos = informes[informes["disponivel_em"] <= pd.Timestamp(corte)]
    tentativas = [t for t in _tentativas_boas() if t.dia <= corte]
    assert fidc.eventos_do_fidc(publicos, tentativas, como_em=corte) == como_era_em(
        fidc.eventos_do_fidc(informes, _tentativas_boas()), corte
    )


def test_fidc_filtra_os_fundos_pedidos(informes):
    eventos = fidc.eventos_do_fidc(
        informes, _tentativas_boas(), cnpjs=[cnpj_base.formatar(B)]
    )
    assert {e.objeto_id for e in eventos} == {B}


# ---------------------------------------------------------------- cadastro da Receita (vista do CNPJ)

HOJE = date(2024, 10, 30)  # setembro de 2024 publicado em 21/09; outubro em 21/10
LIMITADA = exemplo.cnpj(exemplo.LIMITADA)


@pytest.fixture
def vista(tmp_path):
    destino = tmp_path / "vista"
    montar_vista_do_cnpj.montar(exemplo.gravar_base(tmp_path / "base"), destino)
    exemplo.gravar_restrito(destino / "restrito")  # o nome está ao lado e não pode sair
    return destino


def test_receita_cada_mudanca_da_vista_vira_mudou(vista):
    eventos = cadastro_receita.eventos_do_cnpj(LIMITADA, HOJE, vista)
    mudou = [e for e in eventos if e.estado == MUDOU]
    assert mudou, "a vista de exemplo tem mudanças na janela"
    for evento in mudou:
        mes = evento.ocorrido_em.strftime("%Y-%m")
        assert evento.publico_em == publicacao_da_receita(mes)
        assert evento.objeto_id == LIMITADA
        assert evento.fonte == "rfb-cnpj"
        assert evento.evidencia


def test_receita_a_mudanca_do_estabelecimento_e_so_do_cnpj_dele(vista):
    filial = exemplo.cnpj(exemplo.LIMITADA, "0002")
    da_filial = cadastro_receita.eventos_do_cnpj(filial, HOJE, vista)
    da_matriz = cadastro_receita.eventos_do_cnpj(LIMITADA, HOJE, vista)
    situacao = "estabelecimentos.situacao_cadastral"
    (evento,) = [e for e in da_filial if e.assunto == situacao]
    assert (evento.evidencia[0].antes, evento.evidencia[0].depois) == ("02", "08")
    assert evento.ocorrido_em == date(2024, 9, 1)
    assert not [e for e in da_matriz if e.assunto.startswith("estabelecimentos.")]


def test_receita_o_socio_que_entrou_ou_saiu_vai_sem_nome_nem_id(vista):
    eventos = cadastro_receita.eventos_do_cnpj(LIMITADA, HOJE, vista)
    texto = json.dumps([e.como_dict() for e in eventos], ensure_ascii=False)
    assert exemplo.NOME_DO_SOCIO not in texto
    assert exemplo.ID_DO_SOCIO not in texto
    assert any(e.assunto.startswith("qsa.") for e in eventos)


def test_receita_mes_publicado_fora_da_vista_vira_fonte_falhou(vista):
    eventos = cadastro_receita.eventos_do_cnpj(LIMITADA, HOJE, vista)
    meses = [
        e.ocorrido_em.strftime("%Y-%m") for e in eventos if e.estado == FONTE_FALHOU
    ]
    # a janela de 12 meses até outubro de 2024; a vista tem só 2024-08 e 2024-09 nela
    assert meses == [
        "2023-11", "2023-12", "2024-01", "2024-02", "2024-03", "2024-04", "2024-05",
        "2024-06", "2024-07", "2024-10",
    ]  # fmt: skip
    outubro = next(e for e in eventos if e.ocorrido_em == date(2024, 10, 1))
    assert outubro.publico_em == publicacao_da_receita("2024-10")


def test_receita_cnpj_fora_do_retrato_vigente_vira_nao_observado(vista):
    fora = exemplo.cnpj("11111111")
    eventos = cadastro_receita.eventos_do_cnpj(fora, HOJE, vista)
    nao_observados = [e for e in eventos if e.estado == NAO_OBSERVADO]
    assert [(e.objeto_id, e.ocorrido_em) for e in nao_observados] == [
        (fora, date(2024, 9, 1))
    ]


def test_receita_sem_vista_no_servidor_nao_inventa_evento(tmp_path):
    assert cadastro_receita.eventos_do_cnpj(LIMITADA, HOJE, tmp_path / "sem") == []


def _mudanca_da_situacao(mes: str, antes: str, depois: str) -> pd.DataFrame:
    return pd.DataFrame(
        [{"mes": mes, "tipo": "mudou", "cnpj_basico": LIMITADA[:8], "cnpj": LIMITADA,
          "situacao_cadastral_antes": antes, "situacao_cadastral_depois": depois,
          "cnae_principal_antes": "6201501", "cnae_principal_depois": "6201501",
          "uf_antes": None, "uf_depois": None,
          "municipio_antes": "7107", "municipio_depois": "7107"}]
    )  # fmt: skip


def test_receita_so_o_campo_que_mudou_vira_evento():
    cadastro = CadastroDaReceita(
        mes="2024-09",
        disponivel_em=publicacao_da_receita("2024-09"),
        estabelecimentos=pd.DataFrame({"cnpj": [LIMITADA]}),
        simples=None,
        socios=pd.DataFrame(),
        mudancas={"estabelecimentos": _mudanca_da_situacao("2024-09", "02", "08")},
    )
    manifesto = {"mes": "2024-09", "disponivel_em": "2024-09-21",
                 "meses_das_mudancas": ["2024-09"]}  # fmt: skip
    eventos = cadastro_receita.eventos_do_cadastro(
        LIMITADA, manifesto, cadastro, hoje=date(2024, 9, 25)
    )
    mudou = [e for e in eventos if e.estado == MUDOU]
    assert [
        (e.assunto, e.evidencia[0].antes, e.evidencia[0].depois) for e in mudou
    ] == [("estabelecimentos.situacao_cadastral", "02", "08")]
    # o mesmo cálculo, num dia antes da publicação de setembro: a mudança ainda não existe
    antes = cadastro_receita.eventos_do_cadastro(
        LIMITADA, manifesto, cadastro, hoje=date(2024, 9, 20)
    )
    assert not [e for e in antes if e.estado == MUDOU]


# ---------------------------------------------------------------- cadastro de companhias abertas (CVM)


def _cadastro_cvm(*linhas: tuple[str, str, str]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "cnpj": cnpj_base.formatar(cnpj),
                "empresa": empresa,
                "registro": pd.Timestamp("2010-01-04"),
                "cancelamento": pd.NaT
                if situacao == "ATIVO"
                else pd.Timestamp("2026-09-10"),
                "motivo_cancelamento": ""
                if situacao == "ATIVO"
                else "CANCELAMENTO VOLUNTÁRIO",
                "situacao": situacao,
                "setor": "Energia Elétrica",
                "uf": "SP",
            }
            for cnpj, empresa, situacao in linhas
        ]
    )


VERSOES_CVM = [
    (date(2026, 8, 3), _cadastro_cvm((A, "ALFA SA", "ATIVO"), (B, "BETA SA", "ATIVO"))),
    (
        date(2026, 9, 12),
        _cadastro_cvm((A, "ALFA SA", "CANCELADA"), (B, "BETA SA", "ATIVO")),
    ),
    (date(2026, 10, 2), _cadastro_cvm((A, "ALFA SA", "CANCELADA"))),
]


def _tentativas_diarias(*meses: int) -> list[Tentativa]:
    dias = [date(2026, mes, dia) for mes in meses for dia in (3, 12, 20)]
    return [Tentativa(dia, dia, ok=True) for dia in dias]


def test_cvm_mudanca_de_situacao_e_saida_do_arquivo():
    eventos = cadastro_cvm.eventos_do_cadastro_cvm(
        VERSOES_CVM, _tentativas_diarias(8, 9, 10), ate=date(2026, 10, 20)
    )
    assert _estados(eventos) == [
        (A, MUDOU, "cancelamento"),
        (A, MUDOU, "motivo_cancelamento"),
        (A, MUDOU, "situacao"),
        (B, NAO_OBSERVADO, "leitura"),
    ]
    situacao = eventos[2]
    assert (situacao.evidencia[0].antes, situacao.evidencia[0].depois) == (
        "ATIVO",
        "CANCELADA",
    )
    assert situacao.publico_em == date(2026, 9, 12)
    assert eventos[0].evidencia[0].depois == "2026-09-10"


def test_cvm_mes_sem_tentativa_boa_vira_fonte_falhou_no_ultimo_dia():
    tentativas = _tentativas_diarias(8, 10) + [
        Tentativa(date(2026, 9, 15), date(2026, 9, 15), ok=False)
    ]
    versoes = VERSOES_CVM[:1] + VERSOES_CVM[2:]  # setembro não foi lido
    eventos = cadastro_cvm.eventos_do_cadastro_cvm(
        versoes, tentativas, ate=date(2026, 10, 31)
    )
    falhas = [e for e in eventos if e.estado == FONTE_FALHOU]
    assert [(e.objeto_id, e.ocorrido_em, e.publico_em) for e in falhas] == [
        (A, date(2026, 9, 1), date(2026, 9, 30)),
        (B, date(2026, 9, 1), date(2026, 9, 30)),
    ]


def test_cvm_mes_ainda_aberto_nao_falhou():
    eventos = cadastro_cvm.eventos_do_cadastro_cvm(
        VERSOES_CVM[:1], _tentativas_diarias(8), ate=date(2026, 9, 29)
    )
    assert eventos == []


def test_cvm_filtra_as_companhias_pedidas():
    eventos = cadastro_cvm.eventos_do_cadastro_cvm(
        VERSOES_CVM, _tentativas_diarias(8, 9, 10), ate=date(2026, 10, 20), cnpjs=[B]
    )
    assert _estados(eventos) == [(B, NAO_OBSERVADO, "leitura")]


# ---------------------------------------------------------------- tentativas pelo registro de coletas


def test_tentativas_saem_do_registro_de_coletas(banco):
    url = "https://dados.cvm.gov.br/dados/FIDC/DOC/INF_MENSAL/DADOS/inf_mensal_fidc_202608.zip"
    dia = datetime(2026, 9, 20, 12, tzinfo=UTC)
    with banco.begin() as conexao:
        registrar_arquivo(conexao, "cvm-fidc", url, None, None, "falhou", "erro", dia)
        registrar_arquivo(
            conexao, "cvm-fidc", url, "abc", 10, "ok", None, dia + timedelta(days=1)
        )
        registrar_arquivo(conexao, "cvm-fidc", url + "x", "abc", 10, "ok", None, dia)
    with banco.connect() as conexao:
        tentativas = registro.tentativas_da_url(conexao, url, periodo=AGOSTO.date())
    assert tentativas == [
        Tentativa(AGOSTO.date(), date(2026, 9, 20), ok=False),
        Tentativa(AGOSTO.date(), date(2026, 9, 21), ok=True),
    ]
