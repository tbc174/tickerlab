"""O grupo econômico pelo QSA (`base/rede/grupo_do_qsa.py`; Ficha Clara, etapa 5): dados de mentira, sem internet."""

import json

import pandas as pd
import pyarrow.parquet as pq
import pytest

from base.porta import vista_do_cnpj
from base.rede import grupo_do_qsa as grupo
from scripts import montar_vista_do_cnpj
from tests import ajudantes_do_cnpj as exemplo

# A ← B (B é sócia de A); B ← D; B é sócia também de C (C é irmã de A); E ← D (prima)
EMPRESA, SOCIA, IRMA, AVO, PRIMA = (
    "AAAA0001",
    "BBBB0002",
    "CCCC0003",
    "DDDD0004",
    "EEEE0005",
)
PESSOA = "f0a1b2c3d4e5f6a7"


def _linha(empresa: str, socia: str = "", tipo: str = "1", **campos) -> dict:
    return {
        "cnpj_basico": empresa,
        "tipo_socio": tipo,
        "raiz_socio_pj": socia,
        "qualificacao": campos.get("qualificacao", "22"),
        "data_entrada": pd.Timestamp(campos.get("entrada", "2020-01-02")),
        "id_pessoa": campos.get("id_pessoa", ""),
    }


def _leituras(linhas: list[dict]):
    qsa = pd.DataFrame(linhas)
    socias_de = lambda r: qsa[qsa["cnpj_basico"] == r]
    participadas_de = lambda r: qsa[qsa["raiz_socio_pj"] == r]
    return socias_de, participadas_de


FAMILIA = [
    _linha(EMPRESA, SOCIA),
    _linha(EMPRESA, tipo="2", id_pessoa=PESSOA, qualificacao="49"),
    _linha(SOCIA, AVO),
    _linha(IRMA, SOCIA, qualificacao="49"),
    _linha(PRIMA, AVO),
]


def _raizes(resultado: grupo.Grupo) -> dict[str, int]:
    return {e.raiz: e.passos for e in resultado.empresas}


def test_grupo_anda_nos_dois_sentidos_com_os_passos():
    resultado = grupo.montar_grupo(EMPRESA, *_leituras(FAMILIA))
    assert _raizes(resultado) == {EMPRESA: 0, SOCIA: 1, AVO: 2, IRMA: 2, PRIMA: 3}
    assert resultado.empresas[0].raiz == EMPRESA
    assert {(v.socia, v.empresa) for v in resultado.ligacoes} == {
        (SOCIA, EMPRESA),
        (AVO, SOCIA),
        (SOCIA, IRMA),
        (AVO, PRIMA),
    }
    assert resultado.completo and resultado.ligacoes_de_fora == 0


def test_profundidade_corta_e_diz_que_ha_mais():
    resultado = grupo.montar_grupo(EMPRESA, *_leituras(FAMILIA), profundidade=1)
    assert _raizes(resultado) == {EMPRESA: 0, SOCIA: 1}
    assert not resultado.completo
    assert resultado.ligacoes_de_fora == 2  # B ← D e B → C ficaram de fora
    assert {(v.socia, v.empresa) for v in resultado.ligacoes} == {(SOCIA, EMPRESA)}


def test_limite_corta_em_ordem_de_raiz_e_e_sempre_o_mesmo():
    holding = "HHHH0000"
    linhas = [_linha(f"{i:08d}", holding) for i in range(30)] + [
        _linha(EMPRESA, holding)
    ]
    primeiro = grupo.montar_grupo(EMPRESA, *_leituras(linhas), limite=5)
    segundo = grupo.montar_grupo(EMPRESA, *_leituras(list(reversed(linhas))), limite=5)
    assert primeiro == segundo
    assert len(primeiro.empresas) == 5
    assert _raizes(primeiro) == {
        EMPRESA: 0,
        holding: 1,
        "00000000": 2,
        "00000001": 2,
        "00000002": 2,
    }
    assert not primeiro.completo
    assert primeiro.ligacoes_de_fora == 27
    assert all(v.socia == holding for v in primeiro.ligacoes)


def test_participacao_cruzada_nao_trava():
    linhas = [_linha(EMPRESA, SOCIA), _linha(SOCIA, EMPRESA)]
    resultado = grupo.montar_grupo(EMPRESA, *_leituras(linhas))
    assert _raizes(resultado) == {EMPRESA: 0, SOCIA: 1}
    assert len(resultado.ligacoes) == 2 and resultado.completo


def test_so_pessoa_juridica_de_raiz_boa_entra():
    linhas = [
        _linha(EMPRESA, tipo="2", id_pessoa=PESSOA),
        _linha(EMPRESA, tipo="3"),
        _linha(EMPRESA, "123"),  # raiz curta
        _linha(EMPRESA, EMPRESA),  # sócia de si mesma
        _linha(EMPRESA, "ab12cd34"),  # alfanumérico em minúsculas: vira maiúsculas
    ]
    resultado = grupo.montar_grupo(EMPRESA.lower(), *_leituras(linhas))
    assert _raizes(resultado) == {EMPRESA: 0, "AB12CD34": 1}
    assert PESSOA not in json.dumps(resultado.como_dict())


def test_ligacao_leva_qualificacao_e_data_da_fonte():
    linhas = [_linha(EMPRESA, SOCIA, qualificacao="49", entrada="2019-03-15")]
    (ligacao,) = grupo.montar_grupo(EMPRESA, *_leituras(linhas)).ligacoes
    assert ligacao == grupo.Ligacao(SOCIA, EMPRESA, "49", "2019-03-15")
    sem_data = [_linha(EMPRESA, SOCIA) | {"data_entrada": pd.NaT}]
    assert (
        grupo.montar_grupo(EMPRESA, *_leituras(sem_data)).ligacoes[0].entrada_em is None
    )


def test_empresa_sem_socia_pj_e_um_grupo_de_uma():
    resultado = grupo.montar_grupo(EMPRESA, *_leituras([_linha(EMPRESA, tipo="2")]))
    assert _raizes(resultado) == {EMPRESA: 0}
    assert resultado.ligacoes == () and resultado.completo


# --- na vista do CNPJ ---------------------------------------------------------------------------------


@pytest.fixture
def vista(tmp_path):
    destino = tmp_path / "vista"
    montar_vista_do_cnpj.montar(exemplo.gravar_base(tmp_path / "base"), destino)
    return destino


def test_vista_leva_o_qsa_virado_so_com_a_socia_pj(vista):
    arquivos = sorted(
        (vista / "vigente" / vista_do_cnpj.PARTICIPACOES).glob("*.parquet")
    )
    assert [a.name for a in arquivos] == [f"{exemplo.SOCIO_PJ[:2]}.parquet"]
    tabela = pq.read_table(arquivos[0])
    assert tabela.column_names == list(vista_do_cnpj.COLUNAS_DAS_PARTICIPACOES)
    assert tabela.column("raiz_socio_pj").to_pylist() == [exemplo.SOCIO_PJ]
    assert tabela.column("cnpj_basico").to_pylist() == [exemplo.LIMITADA]
    manifesto = vista_do_cnpj.manifesto(vista)
    assert manifesto is not None
    assert manifesto["tabelas"]["vigente/participacoes"]["linhas"] == 1


def test_participacoes_da_raiz_e_vazia_sem_arquivo(vista):
    assert vista_do_cnpj.participacoes_da_raiz(vista, "99999999").empty
    achadas = vista_do_cnpj.participacoes_da_raiz(vista, exemplo.SOCIO_PJ)
    assert achadas["cnpj_basico"].tolist() == [exemplo.LIMITADA]


def test_grupo_na_vista_dos_dois_lados_com_o_mes(vista):
    da_empresa = grupo.grupo_na_vista(vista, exemplo.LIMITADA)
    da_socia = grupo.grupo_na_vista(vista, exemplo.SOCIO_PJ)
    assert da_empresa is not None and da_socia is not None
    assert _raizes(da_empresa) == {exemplo.LIMITADA: 0, exemplo.SOCIO_PJ: 1}
    assert _raizes(da_socia) == {exemplo.SOCIO_PJ: 0, exemplo.LIMITADA: 1}
    assert da_empresa.ligacoes == da_socia.ligacoes
    assert da_empresa.retrato == exemplo.ULTIMO_MES
    assert da_empresa.disponivel_em
    texto = json.dumps(da_empresa.como_dict(), ensure_ascii=False)
    assert exemplo.ID_DO_SOCIO not in texto and exemplo.NOME_DO_SOCIO not in texto


def test_sem_vista_nao_ha_grupo(tmp_path):
    assert grupo.grupo_na_vista(tmp_path / "nada", exemplo.LIMITADA) is None
