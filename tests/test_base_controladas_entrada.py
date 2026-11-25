"""Linha 1045: a primeira vez que cada controlada aparece no FRE da companhia (`base/controladas_entrada.py`).

A data de referência do FRE é o fim do exercício (2026-12-31 num FRE entregue em junho de 2026); quem quer saber
"desde quando a companhia tem essa controlada" precisa da data em que a CVM recebeu o primeiro FRE que a trazia.
"""

from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pytest

from base import controladas_entrada as entrada
from base.cnpj import digitos_verificadores
from base.parquet import arquivos_atuais

AGORA = datetime(2026, 11, 25, 5, tzinfo=UTC)
EXEMPLO = (
    Path(__file__).resolve().parent.parent
    / "dados_de_exemplo"
    / "base"
    / "controladas_tres_pares.csv"
)

# os três pares do pedido do bot Analista, pelos CNPJs que o FRE da CVM traz
GRANJA_FARIA, VITAGEMA = "81616807000155", "08148596000183"
DASA, IMPAR = (
    "61486650000183",
    "60884855",
)  # a Ímpar muda de filial dentro da mesma raiz
CANTU, CPX = "41096674000119", "10158356000101"


def _cnpj(raiz: str, filial: str = "0001") -> str:
    """Um CNPJ de mentira com os dígitos verificadores certos (a trava de pessoa confere o dígito)."""
    doze = raiz + filial
    return doze + digitos_verificadores(doze)


def _linha(
    companhia: str,
    referencia: str,
    conhecido_em: str,
    cnpj: str | None,
    tipo: str = "controlada",
) -> dict[str, object]:
    return {
        "cnpj_companhia": companhia,
        "referencia": date.fromisoformat(referencia),
        "versao": 1,
        "conhecido_em": date.fromisoformat(conhecido_em),
        "cnpj": cnpj,
        "tipo": tipo,
        "participacao": 100.0,
    }


def _tabela(*linhas: dict[str, object]) -> pd.DataFrame:
    return pd.DataFrame(list(linhas))


def _exemplo() -> pd.DataFrame:
    quadro = pd.read_csv(EXEMPLO, dtype=str, keep_default_na=False)
    for coluna in ("referencia", "conhecido_em"):
        quadro[coluna] = pd.to_datetime(quadro[coluna]).dt.date
    quadro["tipo"] = quadro["tipo"].replace("", None)
    return quadro


def _par(tabela: pd.DataFrame, companhia: str, raiz: str) -> pd.Series:
    achado = tabela[
        (tabela["cnpj_companhia"] == companhia) & (tabela["raiz_da_controlada"] == raiz)
    ]
    assert len(achado) == 1, f"o par {companhia}/{raiz} devia sair uma vez"
    return achado.iloc[0]


# --- os três pares do pedido, com o FRE real ------------------------------------------------------------


def test_granja_faria_e_vitagema_entram_em_2024():
    par = _par(entrada.primeira_entrada(_exemplo()).tabela, GRANJA_FARIA, VITAGEMA[:8])
    assert par["primeiro_ano_no_fre"] == 2024
    assert par["conhecido_em"] == date(
        2025, 4, 29
    )  # quando a CVM recebeu o FRE de 2024
    # a companhia já entregava o FRE de 2023 sem a Vitagema: a entrada foi vista, não é "desde o começo"
    assert bool(par["entrada_observada"]) is True


def test_dasa_e_impar_contam_uma_vez_mesmo_trocando_de_filial():
    tabela = entrada.primeira_entrada(_exemplo()).tabela
    par = _par(tabela, DASA, IMPAR)
    assert par["primeiro_ano_no_fre"] == 2023
    assert par["conhecido_em"] == date(2024, 5, 10)
    assert (
        par["cnpj"] == "60884855000316"
    )  # o CNPJ da primeira vez; em 2025 a Dasa passou a informar outro
    assert bool(par["entrada_observada"]) is True


def test_cantu_e_cpx_ja_estavam_no_primeiro_fre_da_companhia():
    par = _par(entrada.primeira_entrada(_exemplo()).tabela, CANTU, CPX[:8])
    assert par["primeiro_ano_no_fre"] == 2022
    assert par["conhecido_em"] == date(2023, 4, 26)
    # não há FRE anterior da Cantu na base: a entrada é "não depois de 2022", nunca "em 2022"
    assert bool(par["entrada_observada"]) is False


# --- regras -----------------------------------------------------------------------------------------------


def test_a_data_de_referencia_futura_nao_vira_a_data_da_entrada():
    """O FRE de 2026 traz referência 2026-12-31 e foi entregue em junho: vale o recebimento."""
    companhia, alvo = _cnpj("11111111"), _cnpj("22222222")
    tabela = _tabela(
        _linha(companhia, "2025-12-31", "2026-04-10", None),
        _linha(companhia, "2026-12-31", "2026-06-01", alvo),
    )
    par = entrada.primeira_entrada(tabela).tabela.iloc[0]
    assert par["conhecido_em"] == date(2026, 6, 1)
    assert par["primeira_referencia"] == date(2026, 12, 31)
    assert par["primeiro_ano_no_fre"] == 2026


def test_fica_a_primeira_entrega_e_nao_a_mais_nova():
    companhia, alvo = _cnpj("11111111"), _cnpj("22222222")
    tabela = _tabela(
        _linha(companhia, "2023-12-31", "2024-04-01", alvo, tipo="coligada"),
        _linha(companhia, "2024-12-31", "2025-04-01", alvo, tipo="controlada"),
    )
    saida = entrada.primeira_entrada(tabela).tabela
    assert len(saida) == 1
    assert saida.iloc[0]["conhecido_em"] == date(2024, 4, 1)
    assert saida.iloc[0]["tipo_na_entrada"] == "coligada"


def test_entrega_atrasada_de_fre_velho_nao_adianta_a_entrada():
    """Um FRE de 2020 reentregue em 2025 não faz a ligação existir antes de 2024 para quem olhava em 2024."""
    companhia, alvo = _cnpj("11111111"), _cnpj("22222222")
    tabela = _tabela(
        _linha(companhia, "2019-12-31", "2020-04-01", None),
        _linha(companhia, "2020-12-31", "2025-11-12", alvo),
        _linha(companhia, "2023-12-31", "2024-05-08", alvo),
    )
    par = entrada.primeira_entrada(tabela).tabela.iloc[0]
    assert par["conhecido_em"] == date(2024, 5, 8)
    assert par["primeira_referencia"] == date(
        2023, 12, 31
    )  # a referência da entrega que a tornou pública


def test_sociedade_sem_cnpj_ou_com_cpf_completado_fica_de_fora_e_e_contada():
    companhia, alvo = _cnpj("11111111"), _cnpj("22222222")
    cpf_completado = (
        "000" + "52998224725"
    )  # o `cnpj14` do FRE completa um CPF com zeros
    tabela = _tabela(
        _linha(companhia, "2024-12-31", "2025-04-01", alvo),
        _linha(
            companhia, "2024-12-31", "2025-04-01", None
        ),  # estrangeira ou sem CNPJ: nunca pelo nome
        _linha(companhia, "2024-12-31", "2025-04-01", cpf_completado),
        _linha(
            companhia, "2024-12-31", "2025-04-01", "12345678000100"
        ),  # dígito verificador errado
    )
    resultado = entrada.primeira_entrada(tabela)
    assert resultado.tabela["raiz_da_controlada"].tolist() == [alvo[:8]]
    assert resultado.sem_cnpj == 1
    assert resultado.nao_confere == 2
    assert "52998224" not in resultado.tabela.to_csv()


def test_sem_olhar_o_futuro_cortar_o_futuro_nao_muda_o_passado():
    """Princípio do projeto: a linha de um dia não muda com o que veio depois dele."""
    cortes = [
        date(2023, 1, 1),
        date(2024, 6, 30),
        date(2025, 6, 30),
        date(2026, 12, 31),
    ]
    completa = entrada.primeira_entrada(_exemplo()).tabela
    for corte in cortes:
        antes = _exemplo()
        antes = antes[antes["conhecido_em"] <= corte]
        recortada = entrada.primeira_entrada(antes).tabela
        da_completa = completa[completa["conhecido_em"] <= corte]
        chaves = ["cnpj_companhia", "raiz_da_controlada"]
        juntas = recortada.merge(
            da_completa, on=chaves, suffixes=("_corte", "_inteira")
        )
        assert len(juntas) == len(da_completa) == len(recortada)
        for coluna in (
            "cnpj", "primeiro_ano_no_fre", "primeira_referencia", "conhecido_em",
            "tipo_na_entrada", "entrada_observada",
        ):  # fmt: skip
            # vazio (None ou NaN) vale como igual a vazio
            do_corte = juntas[f"{coluna}_corte"].astype(object).fillna("")
            da_inteira = juntas[f"{coluna}_inteira"].astype(object).fillna("")
            assert (do_corte == da_inteira).all(), (corte, coluna)


def test_entrada_ate_so_mostra_o_que_ja_era_publico_no_dia():
    tabela = entrada.primeira_entrada(_exemplo()).tabela
    antes = entrada.entradas_ate(
        tabela, date(2025, 4, 28), companhias=[GRANJA_FARIA], controladas=[VITAGEMA]
    )
    assert antes == []  # a CVM só recebeu o FRE de 2024 da Granja Faria em 29/04/2025
    depois = entrada.entradas_ate(
        tabela, date(2025, 4, 29), companhias=[GRANJA_FARIA], controladas=[VITAGEMA]
    )
    assert [e["raiz_da_controlada"] for e in depois] == [VITAGEMA[:8]]
    assert depois[0]["conhecido_em"] == "2025-04-29"
    assert depois[0]["primeiro_ano_no_fre"] == 2024
    assert all(isinstance(v, str | int | bool | None) for v in depois[0].values())


def test_entradas_ate_filtra_por_controlada():
    tabela = entrada.primeira_entrada(_exemplo()).tabela
    achadas = entrada.entradas_ate(tabela, date(2026, 11, 25), controladas=[CPX])
    assert [(e["cnpj_companhia"], e["raiz_da_controlada"]) for e in achadas] == [
        (CANTU, CPX[:8])
    ]


# --- a montagem ---------------------------------------------------------------------------------------------


def test_montagem_le_as_controladas_do_acervo_e_grava_com_manifesto(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    pasta = tmp_path / "base"
    (pasta / "controladas").mkdir(parents=True)
    exemplo = _exemplo()
    for ano, parte in exemplo.groupby(exemplo["referencia"].map(lambda d: d.year)):
        parte.to_parquet(pasta / "controladas" / f"{ano}.parquet", index=False)
    linhas = entrada.montar(pasta, AGORA)
    gravada = pd.read_parquet(
        pasta / "controladas_entrada" / "controladas_entrada.parquet"
    )
    assert linhas == len(gravada) > 0
    assert (pasta / "controladas_entrada" / "controladas_entrada.json").exists()
    assert arquivos_atuais(pasta / "controladas_entrada")
    assert gravada["montado_em"].iloc[0] == AGORA.isoformat()
    assert set(gravada["versao_do_codigo"]) == {"0123abc"}
    assert _par(gravada, CANTU, CPX[:8])["primeiro_ano_no_fre"] == 2022
    # sem razão social, nome nem CPF: só CNPJs e datas
    assert not [c for c in gravada.columns if "razao" in c or "nome" in c or "cpf" in c]


def test_sem_controladas_nada_e_gravado(tmp_path):
    assert entrada.montar(tmp_path, AGORA) == 0
    assert not (tmp_path / "controladas_entrada").exists()


def test_montagem_repetida_nao_regrava_o_que_nao_mudou(tmp_path, monkeypatch):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    pasta = tmp_path / "base"
    (pasta / "controladas").mkdir(parents=True)
    _exemplo().to_parquet(pasta / "controladas" / "2026.parquet", index=False)
    entrada.montar(pasta, AGORA)
    destino = pasta / "controladas_entrada" / "controladas_entrada.parquet"
    antes = destino.stat().st_mtime_ns
    entrada.montar(pasta, datetime(2026, 11, 26, tzinfo=UTC))
    assert destino.stat().st_mtime_ns == antes


@pytest.mark.parametrize("coluna", ["raiz_da_controlada", "cnpj_companhia"])
def test_a_chave_do_par_nao_repete(coluna):
    tabela = entrada.primeira_entrada(_exemplo()).tabela
    assert not tabela.duplicated(["cnpj_companhia", "raiz_da_controlada"]).any()
    assert tabela[coluna].notna().all()


def test_comando_monta_a_tabela_pelo_nome(banco, tmp_path, monkeypatch):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    from scripts import montar_base_historica

    pasta = tmp_path / "base"
    (pasta / "controladas").mkdir(parents=True)
    _exemplo().to_parquet(pasta / "controladas" / "2026.parquet", index=False)
    assert (
        montar_base_historica.main(["controladas_entrada", "--pasta", str(pasta)]) == 0
    )
    assert (pasta / "controladas_entrada" / "controladas_entrada.parquet").exists()
