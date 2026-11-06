"""Exemplos e rótulo do modelo de atraso na entrega da DFP/ITR (modelo 8, ADR 0030; plano do
modelo 8, PR 2). Sem internet: o índice e o cadastro são montados à mão."""

import pandas as pd

from base.modelos.atraso.rotulo import COLUNAS, montar_exemplos, montar_exemplos_e_fora

A = "11.111.111/0001-11"
B = "22.222.222/0001-22"
HOJE = pd.Timestamp("2026-10-15")


def _indice(*entregas: tuple[str, str, str, int, str]) -> pd.DataFrame:
    """(cnpj, documento, referência, versão, recebido em)."""
    return pd.DataFrame(
        [
            {
                "cnpj": cnpj,
                "empresa": f"EMPRESA {cnpj[:2]}",
                "documento": documento,
                "referencia": pd.Timestamp(referencia),
                "versao": versao,
                "recebido_em": pd.Timestamp(recebido),
                "link": "https://x",
            }
            for cnpj, documento, referencia, versao, recebido in entregas
        ]
    )


def _cadastro(*registros: tuple[str, str | None, str | None, str]) -> pd.DataFrame:
    """(cnpj, registro, cancelamento, uf)."""
    return pd.DataFrame(
        [
            {
                "cnpj": cnpj,
                "empresa": f"EMPRESA {cnpj[:2]}",
                "registro": pd.Timestamp(registro) if registro else pd.NaT,
                "cancelamento": pd.Timestamp(cancelamento) if cancelamento else pd.NaT,
                "uf": uf,
            }
            for cnpj, registro, cancelamento, uf in registros
        ]
    )


ATIVA_A = _cadastro((A, "2001-01-01", None, "SP"))


def _linha(exemplos: pd.DataFrame, documento: str, referencia: str) -> pd.Series:
    linhas = exemplos[
        (exemplos["documento"] == documento)
        & (exemplos["referencia"] == pd.Timestamp(referencia))
    ]
    assert len(linhas) == 1
    return linhas.iloc[0]


def test_colunas_e_data_da_previsao():
    exemplos = montar_exemplos(
        _indice((A, "DFP", "2024-12-31", 1, "2025-03-20")), ATIVA_A, HOJE
    )
    assert list(exemplos.columns) == list(COLUNAS)
    linha = exemplos.iloc[0]
    assert linha["data_da_previsao"] == pd.Timestamp("2024-12-31")
    assert linha["prazo"] == pd.Timestamp("2025-03-31")
    assert (linha["atrasou"], linha["dias_uteis_de_atraso"]) == (False, 0)


def test_primeira_entrega_vale_e_reapresentacao_tardia_nao_e_atraso():
    indice = _indice(
        (A, "DFP", "2024-12-31", 1, "2025-03-28"),
        (A, "DFP", "2024-12-31", 2, "2025-06-30"),
    )
    linha = _linha(montar_exemplos(indice, ATIVA_A, HOJE), "DFP", "2024-12-31")
    assert linha["primeira_entrega"] == pd.Timestamp("2025-03-28")
    assert not linha["atrasou"]


def test_atraso_em_dias_uteis_e_zona_cinzenta():
    # ITR de 30/09/2021: prazo 16/11/2021 (domingo 14/11 e feriado 15/11); entregue na quinta, 18/11
    indice = _indice((A, "ITR", "2021-09-30", 1, "2021-11-18"))
    linha = _linha(montar_exemplos(indice, ATIVA_A, HOJE), "ITR", "2021-09-30")
    assert linha["prazo"] == pd.Timestamp("2021-11-16")
    assert linha["dias_uteis_de_atraso"] == 2
    assert linha["atrasou"] and linha["zona_cinzenta"] and not linha["atraso_grave"]


def test_atraso_grave_passa_de_30_dias():
    indice = _indice((A, "DFP", "2024-12-31", 1, "2025-05-20"))
    linha = _linha(montar_exemplos(indice, ATIVA_A, HOJE), "DFP", "2024-12-31")
    assert linha["atrasou"] and linha["atraso_grave"] and not linha["zona_cinzenta"]


def test_nao_entregue_com_prazo_vencido_e_atraso():
    # entregou a DFP de 2023 e não a de 2024, ainda registrada: atrasou e é grave
    indice = _indice(
        (A, "DFP", "2023-12-31", 1, "2024-03-25"),
        (B, "DFP", "2024-12-31", 1, "2025-03-25"),
    )
    exemplos = montar_exemplos(indice, ATIVA_A, HOJE)
    linha = _linha(exemplos[exemplos["cnpj"] == A], "DFP", "2024-12-31")
    assert pd.isna(linha["primeira_entrega"])
    assert linha["atrasou"] and linha["atraso_grave"]
    assert linha["empresa"] == "EMPRESA 11"
    assert (exemplos["cnpj"] == A).sum() == 2  # a de 2025 não entra: a de 2024 não veio


def test_prazo_ainda_aberto_fica_de_fora():
    indice = _indice((A, "DFP", "2024-12-31", 1, "2025-03-25"))
    exemplos = montar_exemplos(indice, ATIVA_A, pd.Timestamp("2026-03-20"))
    assert exemplos["referencia"].tolist() == [pd.Timestamp("2024-12-31")]


def test_entrega_depois_de_hoje_ainda_nao_existia():
    # refazer a base "em 10/04/2025": a entrega de 20/04 ainda não tinha acontecido
    indice = _indice(
        (A, "DFP", "2023-12-31", 1, "2024-03-25"),
        (A, "DFP", "2024-12-31", 1, "2025-04-20"),
        (B, "DFP", "2024-12-31", 1, "2025-03-25"),
    )
    exemplos = montar_exemplos(indice, ATIVA_A, pd.Timestamp("2025-04-10"))
    linha = _linha(exemplos[exemplos["cnpj"] == A], "DFP", "2024-12-31")
    assert pd.isna(linha["primeira_entrega"]) and linha["atrasou"]


def test_empresa_cancelada_continua_nos_anos_ativos():
    cadastro = _cadastro((B, "1990-01-01", "2023-11-30", "RJ"))
    indice = _indice(
        (B, "DFP", "2021-12-31", 1, "2022-03-30"),
        (B, "DFP", "2022-12-31", 1, "2023-03-30"),
    )
    exemplos = montar_exemplos(indice, cadastro, HOJE)
    # 2021 e 2022 ficam; a DFP de 2023 (prazo em 2024) não era devida: saiu antes
    assert exemplos["referencia"].dt.year.tolist() == [2021, 2022]


def test_registrada_depois_do_prazo_nao_deve_o_documento():
    # cancelou em 10/01/2021 e voltou em 01/06/2021: não devia a DFP de 2020 (prazo 31/03/2021)
    cadastro = _cadastro(
        (B, "1995-01-01", "2021-01-10", "RJ"), (B, "2021-06-01", None, "RJ")
    )
    indice = _indice(
        (B, "DFP", "2019-12-31", 1, "2020-05-20"),
        (A, "DFP", "2020-12-31", 1, "2021-03-25"),
    )
    exemplos = montar_exemplos(indice, cadastro, pd.Timestamp("2021-12-31"))
    assert exemplos.loc[exemplos["cnpj"] == B, "referencia"].dt.year.tolist() == [2019]


def test_empresa_fora_do_cadastro_nao_e_exemplo():
    # quase todas são emissores estrangeiros (GP Investments, Cosan Ltd., Nu Holdings): sem o
    # cadastro não se sabe se deviam o documento nem qual prazo valia (conferência de 16/10/2026)
    indice = _indice(
        (A, "DFP", "2023-12-31", 1, "2024-03-25"),
        (B, "DFP", "2023-12-31", 1, "2024-03-25"),
    )
    exemplos, fora = montar_exemplos_e_fora(indice, ATIVA_A, HOJE)
    assert exemplos["cnpj"].tolist() == [A]
    assert fora["empresa_fora_do_cadastro"] == {"exemplos": 1, "atrasou": 0}


def test_documento_com_prazo_entre_dois_registros_nao_e_exemplo():
    # Linha Amarela (LAMSA): registro de 1998 a 2003 e de novo em 08/04/2020; os ITRs de 2019
    # foram mandados para pedir o registro de volta, sem prazo a cumprir
    cadastro = _cadastro(
        (B, "1998-02-02", "2003-05-06", "RJ"), (B, "2020-04-08", None, "RJ")
    )
    indice = _indice(
        (B, "ITR", "2019-09-30", 1, "2019-11-21"),
        (B, "DFP", "2020-12-31", 1, "2021-03-25"),
    )
    exemplos, fora = montar_exemplos_e_fora(indice, cadastro, HOJE)
    assert exemplos["referencia"].dt.year.tolist() == [2020]
    assert fora["prazo_entre_dois_registros"] == {"exemplos": 1, "atrasou": 1}


def test_documento_com_prazo_depois_do_cancelamento_nao_e_exemplo():
    # securitizadora cancelada em 01/06/2022 que continuou mandando ITR: não devia mais nada
    cadastro = _cadastro((B, "2019-02-13", "2022-06-01", "SP"))
    indice = _indice(
        (B, "ITR", "2022-03-31", 1, "2022-05-10"),
        (B, "ITR", "2022-06-30", 1, "2022-08-10"),
    )
    exemplos, fora = montar_exemplos_e_fora(indice, cadastro, HOJE)
    assert exemplos["referencia"].tolist() == [pd.Timestamp("2022-03-31")]
    assert fora["prazo_depois_do_cancelamento"] == {"exemplos": 1, "atrasou": 0}


def test_sede_no_rio_grande_do_sul_usa_a_prorrogacao_de_2024():
    cadastro = _cadastro((A, "2001-01-01", None, "RS"))
    indice = _indice((A, "ITR", "2024-03-31", 1, "2024-06-20"))
    linha = _linha(montar_exemplos(indice, cadastro, HOJE), "ITR", "2024-03-31")
    assert (linha["uf"], linha["prazo"]) == ("RS", pd.Timestamp("2024-07-01"))
    assert not linha["atrasou"]


def test_exercicio_que_fecha_em_marco():
    # DFP de 31/03: o ITR de 30/06/2020 é o 1º trimestre, com +45 dias (prazo 28/09/2020)
    indice = _indice(
        (A, "DFP", "2020-03-31", 1, "2020-08-20"),
        (A, "ITR", "2020-06-30", 1, "2020-09-10"),
    )
    linha = _linha(montar_exemplos(indice, ATIVA_A, HOJE), "ITR", "2020-06-30")
    assert linha["mes_fim_do_exercicio"] == 3
    assert linha["prazo"] == pd.Timestamp("2020-09-28")
    assert not linha["atrasou"]


def test_indice_vazio():
    vazio = _indice().reindex(
        columns=[
            "cnpj",
            "empresa",
            "documento",
            "referencia",
            "versao",
            "recebido_em",
            "link",
        ]
    )
    assert montar_exemplos(vazio, ATIVA_A, HOJE).empty


def test_data_base_sem_nenhuma_entrega_no_indice_nao_vira_falta():
    # sem o arquivo do ano no índice (download que falhou), ninguém "deixou de entregar"
    indice = _indice((A, "ITR", "2021-03-31", 1, "2021-05-10"))
    exemplos = montar_exemplos(indice, ATIVA_A, HOJE)
    assert exemplos["referencia"].tolist() == [pd.Timestamp("2021-03-31")]


def test_dfp_fora_do_exercicio_nao_cria_falta_no_ano_seguinte():
    # exercício em dezembro e uma DFP especial de 31/03/2023: não se espera outra em 31/03/2024
    indice = _indice(
        (A, "DFP", "2022-12-31", 1, "2023-03-20"),
        (A, "DFP", "2023-03-31", 1, "2023-06-20"),
        (A, "DFP", "2023-12-31", 1, "2024-03-20"),
        (B, "DFP", "2024-03-31", 1, "2024-06-20"),
    )
    exemplos = montar_exemplos(indice, ATIVA_A, HOJE)
    datas_de_a = exemplos.loc[exemplos["cnpj"] == A, "referencia"].dt.strftime("%Y-%m")
    assert datas_de_a.tolist() == ["2022-12", "2023-03", "2023-12"]


def test_falta_so_conta_se_o_arquivo_do_ano_foi_visto_depois_do_prazo():
    # o arquivo de 2024 coletado em 20/03/2025 não diz nada sobre o prazo de 31/03/2025
    indice = _indice(
        (A, "DFP", "2023-12-31", 1, "2024-03-25"),
        (B, "DFP", "2024-12-31", 1, "2025-03-10"),
    )
    cedo = {
        ("DFP", 2023): pd.Timestamp("2025-03-20"),
        ("DFP", 2024): pd.Timestamp("2025-03-20"),
    }
    depois = {**cedo, ("DFP", 2024): pd.Timestamp("2025-05-01")}
    sem_falta = montar_exemplos(indice, ATIVA_A, HOJE, vistos_em=cedo)
    com_falta = montar_exemplos(indice, ATIVA_A, HOJE, vistos_em=depois)
    assert (sem_falta["cnpj"] == A).sum() == 1
    assert (com_falta["cnpj"] == A).sum() == 2


# --- documentos do pedido de registro (conferência da data de entrega da CVM, 15/10/2026) --------
MANAUS = "09.584.854/0001-37"  # registro em 29/03/2022
TURBI = "26.982.634/0001-80"  # registro em 11/05/2023
NATURA_CO = "32.785.497/0001-97"  # Natura &Co Holding, registro em 25/09/2019
REGISTROS = _cadastro(
    (MANAUS, "2022-03-29", None, "RJ"),
    (TURBI, "2023-05-11", None, "SP"),
    (NATURA_CO, "2019-09-25", None, "SP"),
)
ENTREGAS_DO_PEDIDO_DE_REGISTRO = _indice(
    (MANAUS, "ITR", "2021-03-31", 1, "2021-12-21"),  # ID_DOC 110848
    (MANAUS, "DFP", "2021-12-31", 1, "2022-03-31"),
    (TURBI, "DFP", "2022-12-31", 1, "2023-04-13"),  # ID_DOC 125242
    (TURBI, "ITR", "2023-03-31", 1, "2023-05-15"),
    (NATURA_CO, "ITR", "2019-03-31", 1, "2019-07-26"),
    (NATURA_CO, "ITR", "2019-09-30", 1, "2019-11-08"),
)


def test_documento_com_prazo_antes_do_registro_nao_e_exemplo():
    # a empresa mandou o documento para pedir o registro: não tinha prazo a cumprir
    exemplos = montar_exemplos(ENTREGAS_DO_PEDIDO_DE_REGISTRO, REGISTROS, HOJE)
    exemplos = exemplos[exemplos["primeira_entrega"].notna()]
    ficaram = set(
        zip(
            exemplos["cnpj"], exemplos["documento"], exemplos["referencia"], strict=True
        )
    )
    assert ficaram == {
        (MANAUS, "DFP", pd.Timestamp("2021-12-31")),
        (TURBI, "ITR", pd.Timestamp("2023-03-31")),
        (NATURA_CO, "ITR", pd.Timestamp("2019-09-30")),
    }


def test_fora_do_registro_fica_contado_por_motivo():
    _exemplos, fora = montar_exemplos_e_fora(
        ENTREGAS_DO_PEDIDO_DE_REGISTRO, REGISTROS, HOJE
    )
    assert fora == {
        "prazo_antes_do_primeiro_registro": {"exemplos": 3, "atrasou": 3},
        "prazo_entre_dois_registros": {"exemplos": 0, "atrasou": 0},
        "prazo_depois_do_cancelamento": {"exemplos": 0, "atrasou": 0},
        "empresa_fora_do_cadastro": {"exemplos": 0, "atrasou": 0},
    }
