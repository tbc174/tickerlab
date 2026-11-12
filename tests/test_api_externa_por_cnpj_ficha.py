"""O perfil de uma empresa na API externa (linha 736, PR 2): o leitor `conjuntos/ficha.py`.

O cadastro vem do leitor de `companies` (a mesma base de mentira de `test_api_externa_empresas.py`); as
entregas de DFP e ITR vêm de `rotulos_atraso`, com a regra da ficha da noite. Sem olhar o futuro: nada
publicado depois do dia pedido sai, e a entrega que ainda não tinha acontecido sai como `not_filed`.
"""

import shutil
from datetime import date

import pandas as pd
import pytest

from base.porta import Porta
from src.api_externa.conjuntos import empresas, ficha
from src.api_externa.nomes import NOMES_DE_FORA
from tests import test_api_externa_empresas as empresas_de_mentira

EMPRESA = empresas_de_mentira.EMPRESA
CVM_DFP, CVM_ITR, RECEITA = "cvm-hist-dfp", "cvm-hist-itr", "rfb-cnpj"
# a situação de jan/2025 é pública em 31/01/2025; a tabela das entregas foi montada em 01/10/2025
DIA = date(2025, 6, 30)
MONTADA_EM = "2025-10-01"

# documento, referência, prazo, primeira entrega, dias úteis de atraso, atrasou, grave, zona cinzenta
# fmt: off
ENTREGAS = [
    ("DFP", "2023-12-31", "2024-04-01", "2024-03-20", 0, False, False, False),  # no prazo
    ("ITR", "2024-03-31", "2024-05-15", "2024-05-17", 2, True, False, True),  # zona cinzenta
    ("DFP", "2024-12-31", "2025-03-31", "2025-08-11", 90, True, True, False),  # entregou depois de DIA
    ("ITR", "2025-03-31", "2025-05-15", None, 99, True, True, False),  # nunca entregou
    ("ITR", "2025-06-30", "2025-08-14", "2025-08-10", 0, False, False, False),  # prazo depois de DIA
]
# fmt: on


def _rotulos(linhas=ENTREGAS, cnpj: str = EMPRESA) -> pd.DataFrame:
    colunas = [
        "documento", "referencia", "prazo", "primeira_entrega", "dias_uteis_de_atraso", "atrasou",
        "atraso_grave", "zona_cinzenta",
    ]  # fmt: skip
    tabela = pd.DataFrame(linhas, columns=colunas)
    for data in ("referencia", "prazo", "primeira_entrega"):
        tabela[data] = pd.to_datetime(tabela[data])
    tabela["data_da_previsao"] = tabela["referencia"]
    return tabela.assign(
        cnpj=empresas_de_mentira._formatado(cnpj),
        empresa="ALFA S.A.",
        uf="SP",
        mes_fim_do_exercicio=12,
        montado_em=pd.Timestamp(MONTADA_EM, tz="UTC"),
        versao_do_codigo="teste",
    )


def _base(tmp_path, rotulos: pd.DataFrame | None = None):
    pasta = tmp_path / "base"
    empresas_de_mentira._gravar_base(pasta, empresas_de_mentira._retratos())
    if rotulos is not None:
        (pasta / ficha.TABELA_DAS_ENTREGAS).mkdir()
        rotulos.to_parquet(
            pasta / ficha.TABELA_DAS_ENTREGAS / "rotulos_atraso.parquet", index=False
        )
    return pasta


def _tudo(_fonte: str, _campo: str, _derivado: bool) -> bool:
    return True


def _ler(
    pasta, cnpj: str = EMPRESA, dia: date = DIA, permitido=_tudo
) -> ficha.FichaServida | None:
    with Porta(pasta) as porta:
        return ficha.LeitorDeFicha(porta, permitido).ficha(cnpj, dia)


def _corpo(pasta, **pedido) -> dict:
    servida = _ler(pasta, **pedido)
    assert servida is not None
    return servida.corpo


@pytest.fixture
def pasta(tmp_path):
    return _base(tmp_path, _rotulos())


def _valores(linha: dict) -> dict:
    return {nome: envelope["valor"] for nome, envelope in linha.items()}


# ---------------------------------------------------------------- o que sai


def test_perfil_junta_o_cadastro_e_as_entregas_com_fonte_e_data(pasta):
    servida = _ler(pasta)
    assert servida is not None
    corpo = servida.corpo
    assert corpo["cnpj"] == EMPRESA and corpo["como_era_em"] == "2025-06-30"
    situacao = corpo["cadastro_na_receita"]["situacao_cadastral"]
    assert situacao == {
        "valor": "02",
        "fonte": RECEITA,
        "publico_em": "2025-01-31",
        "visto_em": None,
    }
    assert corpo["cadastro_na_receita"]["razao_social"]["valor"] == "ALFA S.A."
    assert (
        "cnpj" not in corpo["cadastro_na_receita"]
        and "como_era_em" not in corpo["cadastro_na_receita"]
    )
    entregas = [_valores(linha) for linha in corpo["entregas"]]
    assert [e["situacao_da_entrega"] for e in entregas] == [
        ficha.NAO_ENTREGUE, ficha.NAO_ENTREGUE, ficha.ZONA_CINZENTA, ficha.NO_PRAZO,
    ]  # fmt: skip
    assert entregas[-1] == {
        "documento": "DFP",
        "referencia": "2023-12-31",
        "prazo": "2024-04-01",
        "primeira_entrega": "2024-03-20",
        "dias_uteis_de_atraso": 0,
        "situacao_da_entrega": ficha.NO_PRAZO,
    }
    assert servida.fontes == {RECEITA, CVM_DFP, CVM_ITR}
    assert servida.linhas == 1 + 4
    assert corpo["limites"] == list(ficha.LIMITES)


def test_cada_entrega_tem_a_fonte_do_documento_e_o_dia_em_que_ficou_publica(pasta):
    entregas = _corpo(pasta)["entregas"]
    fontes = [linha["documento"]["fonte"] for linha in entregas]
    assert fontes == [CVM_ITR, CVM_DFP, CVM_ITR, CVM_DFP]
    # a entrega vale pela entrega; a falta, pelo prazo
    publicos = [linha["prazo"]["publico_em"] for linha in entregas]
    assert publicos == ["2025-05-15", "2025-03-31", "2024-05-17", "2024-03-20"]


def test_entrega_que_veio_depois_do_dia_sai_como_nao_entregue_sem_a_data(pasta):
    """A DFP de 2024 foi entregue em 11/08/2025: em 30/06 ela faltava, com os dias úteis até o dia."""
    dfp_2024 = _valores(_corpo(pasta)["entregas"][1])
    assert dfp_2024["referencia"] == "2024-12-31"
    assert dfp_2024["situacao_da_entrega"] == ficha.NAO_ENTREGUE
    assert "primeira_entrega" not in dfp_2024
    assert 0 < dfp_2024["dias_uteis_de_atraso"] < 90  # type: ignore[operator]


def test_depois_da_entrega_vale_o_rotulo_da_tabela(pasta):
    entregas = [_valores(e) for e in _corpo(pasta, dia=date(2025, 9, 1))["entregas"]]
    dfp_2024 = next(e for e in entregas if e["referencia"] == "2024-12-31")
    assert dfp_2024["situacao_da_entrega"] == ficha.ATRASO_GRAVE
    assert dfp_2024["primeira_entrega"] == "2025-08-11"
    assert dfp_2024["dias_uteis_de_atraso"] == 90
    itr_2025 = next(e for e in entregas if e["referencia"] == "2025-06-30")
    assert itr_2025["situacao_da_entrega"] == ficha.NO_PRAZO


def test_atraso_que_nao_e_grave_nem_zona_cinzenta_sai_como_late(tmp_path):
    atrasou = [("ITR", "2023-09-30", "2023-11-14", "2023-11-24", 8, True, False, False)]
    entregas = _corpo(_base(tmp_path, _rotulos(atrasou)))["entregas"]
    assert [_valores(e)["situacao_da_entrega"] for e in entregas] == [ficha.ATRASOU]


def test_falta_so_sai_ate_o_dia_em_que_a_base_conferiu(pasta):
    """A tabela foi montada em 01/10/2025: o ITR que nunca veio não ganha falta datada depois disso."""
    entregas = [_valores(e) for e in _corpo(pasta, dia=date(2026, 6, 30))["entregas"]]
    nunca = next(e for e in entregas if e["referencia"] == "2025-03-31")
    assert nunca["situacao_da_entrega"] == ficha.NAO_ENTREGUE
    ate_a_montagem = _corpo(pasta, dia=date(2025, 10, 1))["entregas"]
    nunca_na_montagem = next(
        _valores(e) for e in ate_a_montagem if e["referencia"]["valor"] == "2025-03-31"
    )
    assert nunca["dias_uteis_de_atraso"] == nunca_na_montagem["dias_uteis_de_atraso"]


@pytest.mark.parametrize(
    "dia",
    [
        date(2025, 1, 31),
        date(2025, 4, 1),
        DIA,
        date(2025, 8, 10),
        date(2025, 8, 11),
        date(2026, 1, 1),
    ],
)
def test_nada_publicado_depois_do_dia_sai(pasta, dia):
    corpo = _corpo(pasta, dia=dia)
    envelopes = [
        *corpo["cadastro_na_receita"].values(),
        *(e for linha in corpo.get("entregas", []) for e in linha.values()),
    ]
    assert all(date.fromisoformat(e["publico_em"]) <= dia for e in envelopes)
    for linha in corpo.get("entregas", []):
        if "primeira_entrega" in linha:
            assert date.fromisoformat(linha["primeira_entrega"]["valor"]) <= dia
        assert date.fromisoformat(linha["prazo"]["valor"]) <= dia


# ---------------------------------------------------------------- o que não sai


@pytest.mark.parametrize(
    "cnpj",
    [
        empresas_de_mentira.MEI,
        empresas_de_mentira.EMPRESARIO_INDIVIDUAL,
        empresas_de_mentira.FORA_DA_REDE,
        empresas_de_mentira.FUNDO,
        empresas_de_mentira.INEXISTENTE,
    ],
)
def test_pessoa_e_quem_a_rede_nao_conhece_como_empresa_nao_saem(tmp_path, cnpj):
    """Mesmo com entregas na tabela, quem não é empresa não sai: o leitor devolve None (a rota, 404)."""
    pasta = _base(tmp_path, pd.concat([_rotulos(), _rotulos(cnpj=cnpj)]))
    assert _ler(pasta, cnpj=cnpj) is None


def test_antes_do_primeiro_retrato_nada_sai_nem_as_entregas(pasta):
    """Sem o cadastro, nada sai: a entrega de 2024 era pública, mas o retrato da Receita ainda não."""
    assert _ler(pasta, dia=date(2025, 1, 30)) is None


def test_base_sem_a_tabela_das_entregas_serve_so_o_cadastro(tmp_path):
    servida = _ler(_base(tmp_path))
    assert servida is not None
    assert "entregas" not in servida.corpo
    assert servida.fontes == {RECEITA} and servida.linhas == 1


def test_portao_que_nega_as_contas_nossas_tira_so_elas(pasta):
    corpo = _corpo(pasta, permitido=lambda _f, _c, derivado: not derivado)
    assert corpo["entregas"]
    for linha in corpo["entregas"]:
        assert set(linha) <= {"documento", "referencia", "prazo", "primeira_entrega"}


def test_portao_que_nega_a_cvm_tira_o_bloco_sem_null(pasta):
    servida = _ler(pasta, permitido=lambda fonte, _c, _d: fonte == RECEITA)
    assert servida is not None
    assert "entregas" not in servida.corpo
    assert servida.fontes == {RECEITA}


# ---------------------------------------------------------------- documento não disponível (linha 881)


def test_com_tudo_liberado_nenhum_documento_fica_de_fora(pasta):
    corpo = _corpo(pasta)
    assert corpo["entregas_nao_disponiveis"] == []
    assert ficha.LIMITE_DO_DOCUMENTO_NAO_DISPONIVEL not in corpo["limites"]


def test_documento_que_o_portao_nao_libera_vai_na_lista_e_no_aviso(pasta):
    """Sem o ITR, a lista de entregas só tem DFP: sem a lista de fora, leria como "nenhum ITR devido"."""
    corpo = _corpo(pasta, permitido=lambda fonte, _c, _d: fonte != CVM_ITR)
    assert {linha["documento"]["valor"] for linha in corpo["entregas"]} == {"DFP"}
    assert corpo["entregas_nao_disponiveis"] == ["ITR"]
    assert ficha.LIMITE_DO_DOCUMENTO_NAO_DISPONIVEL in corpo["limites"]
    # as frases das entregas continuam: o DFP foi consultado
    assert set(ficha.LIMITES) <= set(corpo["limites"])


def test_sem_nenhum_documento_o_bloco_some_e_os_limites_nao_falam_das_entregas(pasta):
    servida = _ler(pasta, permitido=lambda fonte, _c, _d: fonte == RECEITA)
    assert servida is not None
    corpo = servida.corpo
    assert "entregas" not in corpo
    assert corpo["entregas_nao_disponiveis"] == ["DFP", "ITR"]
    assert corpo["limites"] == [
        ficha.LIMITES_GERAIS[0],
        ficha.LIMITE_DO_DOCUMENTO_NAO_DISPONIVEL,
        *ficha.LIMITES_GERAIS[1:],
    ]
    assert not any("entregas cobrem" in limite for limite in corpo["limites"])


def test_documento_com_so_conta_nossa_negada_continua_consultado(pasta):
    """Negar só os derivados tira os campos, não o documento: ele não vai para a lista de fora."""
    corpo = _corpo(pasta, permitido=lambda _f, _c, derivado: not derivado)
    assert corpo["entregas_nao_disponiveis"] == []


def test_base_sem_a_tabela_conta_os_dois_documentos_como_nao_consultados(tmp_path):
    corpo = _corpo(_base(tmp_path))
    assert "entregas" not in corpo
    assert corpo["entregas_nao_disponiveis"] == ["DFP", "ITR"]
    assert ficha.LIMITE_DO_DOCUMENTO_NAO_DISPONIVEL in corpo["limites"]


def test_portao_que_nega_a_receita_nao_serve_nada(pasta):
    """Sem cadastro, nada sai, nem as entregas que o portão liberaria."""
    assert _ler(pasta, permitido=lambda fonte, _c, _d: fonte != RECEITA) is None


def test_documento_que_nao_e_dfp_nem_itr_nao_sai(tmp_path):
    estranho = [
        ("FRE", "2023-12-31", "2024-05-31", "2024-05-30", 0, False, False, False)
    ]
    servida = _ler(_base(tmp_path, _rotulos(estranho)))
    # os dois documentos foram consultados: a lista sai vazia, não some
    assert servida is not None and servida.corpo["entregas"] == []
    assert servida.corpo["entregas_nao_disponiveis"] == []


def test_cnpj_invalido_e_erro_de_quem_chama(pasta):
    with pytest.raises(ValueError):
        _ler(pasta, cnpj="123")


# ---------------------------------------------------------------- campo do cadastro não disponível (linha 891)

# no piloto, a situação e o Simples ficaram fora do registro: o portão não libera os campos das duas tabelas
SITUACAO = list(empresas.CAMPOS)
SIMPLES = ["optante_simples", "data_opcao_simples", "data_exclusao_simples"]
CAMPOS_DE_FORA = "campos_do_cadastro_nao_disponiveis"


def _de_fora(*campos: str) -> list[str]:
    return [NOMES_DE_FORA[nome] for nome in campos]


def _sem(*campos: str):
    return lambda _fonte, campo, _derivado: campo not in campos


def test_com_tudo_liberado_nenhum_campo_do_cadastro_fica_de_fora(pasta):
    """No dia, a raiz já tinha saído do arquivo do Simples: o Simples falta por não ter dado, não pelo portão,
    e não vai para a lista."""
    corpo = _corpo(pasta)
    assert "optante_simples" not in corpo["cadastro_na_receita"]
    assert corpo[CAMPOS_DE_FORA] == []
    assert ficha.LIMITE_DO_CAMPO_DO_CADASTRO_NAO_DISPONIVEL not in corpo["limites"]


def test_situacao_e_simples_barrados_vao_na_lista_e_no_aviso(pasta):
    """O caso do piloto: sem a lista, o cadastro só com o nome leria como "a empresa não tem situação"."""
    corpo = _corpo(pasta, permitido=_sem(*SITUACAO, *SIMPLES))
    cadastro = corpo["cadastro_na_receita"]
    assert "razao_social" in cadastro
    assert not set(cadastro) & {*SITUACAO, *SIMPLES}
    assert corpo[CAMPOS_DE_FORA] == _de_fora(*SITUACAO, *SIMPLES)
    assert ficha.LIMITE_DO_CAMPO_DO_CADASTRO_NAO_DISPONIVEL in corpo["limites"]
    # as entregas continuam consultadas: a lista delas e as frases não mudam
    assert corpo["entregas_nao_disponiveis"] == []
    assert set(ficha.LIMITES) <= set(corpo["limites"])


def test_um_campo_barrado_vai_sozinho_na_lista(pasta):
    corpo = _corpo(pasta, permitido=_sem("motivo_situacao"))
    assert "situacao_cadastral" in corpo["cadastro_na_receita"]
    assert corpo[CAMPOS_DE_FORA] == ["registration_status_reason"]


def test_base_sem_o_historico_do_simples_conta_os_campos_dele_como_nao_consultados(
    tmp_path,
):
    base = _base(tmp_path, _rotulos())
    shutil.rmtree(base / empresas_de_mentira.SIMPLES_HISTORICO)
    corpo = _corpo(base, dia=date(2025, 4, 30))
    assert corpo[CAMPOS_DE_FORA] == _de_fora(*SIMPLES)
    assert ficha.LIMITE_DO_CAMPO_DO_CADASTRO_NAO_DISPONIVEL in corpo["limites"]


def test_com_o_historico_o_simples_que_valia_sai_e_nao_vai_na_lista(pasta):
    corpo = _corpo(pasta, dia=date(2025, 4, 30))
    assert corpo["cadastro_na_receita"]["optante_simples"]["valor"] is False
    assert corpo[CAMPOS_DE_FORA] == []


def test_o_aviso_do_cadastro_vem_antes_do_das_entregas(pasta):
    corpo = _corpo(
        pasta,
        permitido=lambda fonte, campo, _d: fonte != CVM_ITR and campo not in SIMPLES,
    )
    limites = corpo["limites"]
    assert limites.index(
        ficha.LIMITE_DO_CAMPO_DO_CADASTRO_NAO_DISPONIVEL
    ) < limites.index(ficha.LIMITE_DO_DOCUMENTO_NAO_DISPONIVEL)


def test_sem_nenhum_campo_do_cadastro_liberado_nada_sai(pasta):
    """Sem campo do cadastro, nada sai, como antes: a lista não abre o 404."""
    todos = [
        *SITUACAO,
        *SIMPLES,
        "razao_social",
        "natureza_juridica",
        "mes_do_retrato_do_cadastro",
    ]
    assert _ler(pasta, permitido=_sem(*todos)) is None
