"""`base.mapa_de_operacoes`: o mapa de FIDC, CRI e CRA por CNPJ (N6, C-PR04). Base de mentira, sem
internet; os CNPJs são de ninguém."""

import pandas as pd
import pytest

from base.mapa_de_operacoes import COLUNAS, mapa_de_operacoes
from base.porta import Porta

FUNDO = "11.111.111/0001-91"
ADMIN = "22.222.222/0001-91"
OUTRO_ADMIN = "33.333.333/0001-91"
GESTOR = "44.444.444/0001-91"
CEDENTE = "55.555.555/0001-91"
SECURITIZADORA = "66.666.666/0001-91"


def _gravar(pasta, caminho: str, tabela: pd.DataFrame) -> None:
    arquivo = pasta / caminho
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    tabela.to_parquet(arquivo, index=False)


def _informe(*meses: tuple[str, str, str, str | None]) -> pd.DataFrame:
    """(competência, disponível em, CNPJ do administrador, cedente 1) de um mês cada."""
    return pd.DataFrame(
        {
            "competencia": pd.to_datetime([m[0] for m in meses]),
            "cnpj_fundo": FUNDO,
            "disponivel_em": pd.to_datetime([m[1] for m in meses]),
            "DENOM_SOCIAL": "FIDC UM",
            "CNPJ_ADMIN": [m[2] for m in meses],
            "ADMIN": ["ADMINISTRADORA"] * len(meses),
            "TAB_I2A12_CPF_CNPJ_CEDENTE_1": [m[3] for m in meses],
            "TAB_I2A12_PR_CEDENTE_1": [10.0] * len(meses),
        }
    )


def _cadastro(gestor: str | None = GESTOR) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "TP_FUNDO": ["FIDC"],
            "CNPJ_FUNDO": [FUNDO],
            "DENOM_SOCIAL": ["FIDC UM"],
            "DT_REG": pd.to_datetime(["2015-01-01"]),
            "PF_PJ_GESTOR": ["PJ" if gestor else "PF"],
            "CPF_CNPJ_GESTOR": [gestor],
            "GESTOR": ["GESTORA" if gestor else None],
        }
    )


def _antigas() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "cnpj_emissor": [SECURITIZADORA] * 3,
            "nome_emissor": ["SECURITIZADORA SA"] * 3,
            "tipo_ativo": [
                "CERTIFICADOS DE RECEBÍVEIS IMOBILIÁRIOS",
                "CERTIFICADOS DE RECEBÍVEIS DO AGRONEGÓCIO",
                "DEBÊNTURES SIMPLES",
            ],
            "numero_registro_oferta": ["CVM/SRE/CRI/2019/1", "CVM/SRE/CRA/2022/2", "X"],
            "numero_processo": [None, None, None],
            "emissao": ["1", "2", "3"],
            "anunciada_em": pd.to_datetime(["2019-05-01", "2022-06-01", "2022-07-01"]),
            "disponivel_em": pd.to_datetime(["2019-06-01", "2022-07-01", "2022-07-01"]),
        }
    )


def _recente() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "cnpj_emissor": [SECURITIZADORA],
            "nome_emissor": ["SECURITIZADORA SA"],
            "valor_mobiliario": ["Certificado de Recebíveis Imobiliários"],
            "numero_requerimento": ["REQ-9"],
            "emissao": ["7"],
            "anunciada_em": pd.to_datetime(["2025-03-01"]),
            "disponivel_em": pd.to_datetime(["2025-03-10"]),
        }
    )


@pytest.fixture
def base(tmp_path):
    informe = _informe(
        ("2024-01-31", "2024-03-16", ADMIN, CEDENTE),
        ("2024-02-29", "2024-04-15", ADMIN, CEDENTE),
        ("2025-01-31", "2025-03-17", OUTRO_ADMIN, None),
    )
    _gravar(tmp_path, "fidc/informe/tab_I/2024.parquet", informe)
    _gravar(tmp_path, "fidc/cadastro/cad_fi.parquet", _cadastro())
    _gravar(tmp_path, "ofertas/antigas.parquet", _antigas())
    _gravar(tmp_path, "ofertas/resolucao_160.parquet", _recente())
    with Porta(tmp_path) as porta:
        yield porta


def _papeis(mapa) -> set[tuple[str, str, str]]:
    v = mapa.vinculos
    return set(zip(v["tipo"], v["papel"], v["cnpj_papel"], strict=True))


def test_o_fundo_tem_administradores_cedente_e_gestor_com_fonte_e_data(base):
    mapa = mapa_de_operacoes(base, FUNDO)
    assert list(mapa.vinculos.columns) == list(COLUNAS)
    assert _papeis(mapa) == {
        ("FIDC", "administrador", ADMIN),
        ("FIDC", "administrador", OUTRO_ADMIN),
        ("FIDC", "cedente", CEDENTE),
        ("FIDC", "gestor", GESTOR),
    }
    admin = mapa.vinculos[mapa.vinculos["cnpj_papel"] == ADMIN].iloc[0]
    assert (admin["referencia_desde"], admin["referencia_ate"]) == (
        pd.Timestamp("2024-01-31"),
        pd.Timestamp("2024-02-29"),
    )
    assert admin["publico_em"] == pd.Timestamp(
        "2024-03-16"
    )  # o 1º mês que ficou público
    assert admin["fonte"] == "fidc_informe" and admin["campo"] == "CNPJ_ADMIN"
    assert pd.isna(mapa.vinculos.query("papel == 'gestor'")["publico_em"]).all()


def test_o_administrador_acha_os_fundos_dele(base):
    mapa = mapa_de_operacoes(base, ADMIN)
    assert _papeis(mapa) == {("FIDC", "administrador", ADMIN)}
    assert list(mapa.vinculos["operacao"]) == [FUNDO]


def test_o_gestor_acha_os_fundos_dele(base):
    mapa = mapa_de_operacoes(base, GESTOR)
    assert _papeis(mapa) == {("FIDC", "gestor", GESTOR)}


def test_a_securitizadora_tem_cri_e_cra_e_nao_debenture(base):
    mapa = mapa_de_operacoes(base, "66.666.666/0001-91")
    assert _papeis(mapa) == {
        ("CRI", "securitizadora", SECURITIZADORA),
        ("CRA", "securitizadora", SECURITIZADORA),
    }
    assert (
        len(mapa.vinculos) == 3
    )  # CRI de 2019, CRA de 2022 e o CRI pela Resolução 160
    cri_novo = mapa.vinculos[mapa.vinculos["operacao"].str.startswith("160:")].iloc[0]
    assert cri_novo["tipo"] == "CRI" and cri_novo["fonte"] == "ofertas_resolucao_160"


def test_cedente_e_devedor_de_cri_e_cra_ficam_como_nao_observaveis(base):
    lacunas = " ".join(mapa_de_operacoes(base, SECURITIZADORA).lacunas)
    assert "cedente e devedor" in lacunas and "não observável" in lacunas
    assert "ANBIMA" in lacunas


def test_aceita_cnpj_sem_pontuacao(base):
    assert _papeis(mapa_de_operacoes(base, "22222222000191")) == {
        ("FIDC", "administrador", ADMIN)
    }


def test_cnpj_invalido_da_erro(base):
    with pytest.raises(ValueError, match="CNPJ inválido"):
        mapa_de_operacoes(base, "abc")


def test_como_era_em_corta_o_que_ainda_nao_era_publico(base):
    mapa = mapa_de_operacoes(base, FUNDO, como_era_em="2024-03-31")
    admin = mapa.vinculos[mapa.vinculos["cnpj_papel"] == ADMIN].iloc[0]
    assert admin["referencia_ate"] == pd.Timestamp(
        "2024-01-31"
    )  # fevereiro só em abril
    assert OUTRO_ADMIN not in set(mapa.vinculos["cnpj_papel"])


def test_como_era_em_nao_mostra_gestor_e_diz_por_que(base):
    mapa = mapa_de_operacoes(base, FUNDO, como_era_em="2024-12-31")
    assert "gestor" not in set(mapa.vinculos["papel"])
    assert any("retrato" in lacuna for lacuna in mapa.lacunas)


@pytest.mark.parametrize(
    "dia", ["2019-12-31", "2022-12-31", "2024-03-31", "2024-12-31"]
)
def test_sem_olhar_o_futuro_cortar_o_futuro_nao_muda_o_passado(base, tmp_path, dia):
    """O mapa em D (com a base inteira) é igual ao mapa montado só com a base até D."""
    for cnpj in (FUNDO, ADMIN, SECURITIZADORA):
        inteiro = mapa_de_operacoes(base, cnpj, como_era_em=dia).vinculos
        pasta = tmp_path / f"corte-{dia}-{cnpj[:2]}"
        corte = pd.Timestamp(dia)
        informe = _informe(
            ("2024-01-31", "2024-03-16", ADMIN, CEDENTE),
            ("2024-02-29", "2024-04-15", ADMIN, CEDENTE),
            ("2025-01-31", "2025-03-17", OUTRO_ADMIN, None),
        )
        antigas, recente = _antigas(), _recente()
        _gravar(
            pasta,
            "fidc/informe/tab_I/2024.parquet",
            informe[informe["disponivel_em"] <= corte],
        )
        _gravar(
            pasta, "ofertas/antigas.parquet", antigas[antigas["disponivel_em"] <= corte]
        )
        _gravar(
            pasta,
            "ofertas/resolucao_160.parquet",
            recente[recente["disponivel_em"] <= corte],
        )
        with Porta(pasta) as so_ate_d:
            cortado = mapa_de_operacoes(so_ate_d, cnpj, como_era_em=dia).vinculos
        pd.testing.assert_frame_equal(inteiro, cortado)


def test_base_sem_nada_devolve_mapa_vazio_e_diz_o_que_falta(tmp_path):
    (tmp_path / "vazia").mkdir()
    with Porta(tmp_path / "vazia") as porta:
        mapa = mapa_de_operacoes(porta, FUNDO)
    assert mapa.vinculos.empty and list(mapa.vinculos.columns) == list(COLUNAS)
    assert any("informe mensal" in lacuna for lacuna in mapa.lacunas)
    assert any("cadastro" in lacuna for lacuna in mapa.lacunas)


def test_gestor_pessoa_fisica_vira_lacuna_sem_nome(tmp_path):
    _gravar(
        tmp_path,
        "fidc/informe/tab_I/2024.parquet",
        _informe(("2024-01-31", "2024-03-16", ADMIN, None)),
    )
    _gravar(tmp_path, "fidc/cadastro/cad_fi.parquet", _cadastro(gestor=None))
    with Porta(tmp_path) as porta:
        mapa = mapa_de_operacoes(porta, FUNDO)
    assert "gestor" not in set(mapa.vinculos["papel"])
    assert any("pessoa física" in lacuna for lacuna in mapa.lacunas)
