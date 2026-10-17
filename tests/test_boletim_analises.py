"""Análise do dia do boletim (`base/boletim/analises.py`): cada cruzamento com uma base pequena feita à
mão, o rodízio e as travas (só tabelas permitidas, nenhum nome de empresa no que sai)."""

import json
from datetime import date

import pandas as pd
import pytest

from base.boletim import analises as an
from base.boletim import fotografia as fo
from base.porta import Porta

HOJE = date(2026, 10, 17)
NOME_SECRETO = "EMPRESA QUE NAO PODE APARECER SA"


def _grava(raiz, nome, tabela, origens=None):
    destino = raiz / f"{nome}.parquet"
    destino.parent.mkdir(parents=True, exist_ok=True)
    tabela.to_parquet(destino, index=False)
    if origens is not None:  # o manifesto, só com o que o boletim lê dele
        texto = json.dumps({"linhas": len(tabela), "origens": origens})
        destino.with_suffix(".json").write_text(texto, encoding="utf-8")


@pytest.fixture
def raiz(tmp_path):
    r = tmp_path / "base"
    _grava(r, "ratings/ratings", pd.DataFrame({
        "empresa": [NOME_SECRETO] * 5,
        "agencia": ["fitch", "fitch", "sp", "moodys", None],
        "nota": ["AAA", "AA-", "brBB+", "Baa2", "RD"],
        "publico_em": pd.to_datetime(["2026-10-01", "2026-09-01", "2026-10-10", "2025-01-01", "2026-10-15"]).date,
    }))  # fmt: skip
    _grava(r, "pgfn_divida/2026-03/a", pd.DataFrame({
        "tipo_divida": ["X"], "ajuizado": [True], "inscricoes": [9], "valor_consolidado": [1.0], "trata_como_pessoa": [False],
        "origem_sha256": ["antigo"],
    }), origens=[{"url": "x", "sha256": "antigo"}])  # fmt: skip
    _grava(r, "pgfn_divida/2026-06/a", pd.DataFrame({
        "tipo_divida": ["Previdenciária", "Previdenciária", "Não previdenciária"],
        "ajuizado": [True, False, True],
        "inscricoes": [2, 3, 5],
        "valor_consolidado": [100.0, 300.0, 600.0],
        "trata_como_pessoa": [False, False, False],
        "origem_sha256": ["novo"] * 3,
    }), origens=[{"url": "y", "sha256": "novo"}])  # fmt: skip
    _grava(r, "insolvencia/2025", pd.DataFrame({
        "cnpj": ["1", "1", "2", "3"],
        "empresa": [NOME_SECRETO] * 4,
        "rotulo": ["recuperacao_judicial", "recuperacao_judicial", "falencia", "exposicao_a_terceiro"],
        "assunto": ["x"] * 4,
        "referencia": pd.to_datetime(["2025-03-01", "2025-04-01", "2025-05-01", "2025-06-01"]).date,
    }))  # fmt: skip
    _grava(r, "insolvencia/2024", pd.DataFrame({
        "cnpj": ["4"], "empresa": [NOME_SECRETO], "rotulo": ["recuperacao_judicial"], "assunto": ["x"],
        "referencia": pd.to_datetime(["2024-02-01"]).date,
    }))  # fmt: skip
    _grava(r, "trocas_de_auditor/trocas", pd.DataFrame({
        "cnpj": ["1"] * 4, "empresa": [NOME_SECRETO] * 4, "anterior": ["X"] * 4, "novo": ["Y"] * 4,
        "efetiva_em": pd.to_datetime(["2022-01-01", "2022-01-01", "2023-01-01", "2017-01-01"]).date,
        "anos_com_o_anterior": [5.0, 5.0, 2.0, 5.0],
    }))  # fmt: skip
    datas = ["2026-10-13", "2026-09-12", "2025-10-13"]
    _grava(r, "curva_juros/2026", pd.DataFrame({
        "data_base": pd.to_datetime([datas[0]] * 4 + [datas[1]] * 4),
        "curva": ["nominal", "nominal", "real", "real"] * 2,
        "prazo_anos": [1.0, 10.0] * 4,
        "taxa": [0.14, 0.13, 0.08, 0.07, 0.15, 0.135, 0.085, 0.072],
    }))  # fmt: skip
    _grava(r, "curva_juros/2025", pd.DataFrame({
        "data_base": pd.to_datetime([datas[2]] * 2), "curva": ["nominal"] * 2,
        "prazo_anos": [1.0, 10.0], "taxa": [0.11, 0.12],
    }))  # fmt: skip
    _grava(r, "eventos/2026", pd.DataFrame({
        "cnpj": ["1"] * 4, "rotulo": ["x"] * 4, "assunto": ["x"] * 4, "empresa": [NOME_SECRETO] * 4,
        "categoria": ["Fato Relevante", "Fato Relevante", "Assembleia", "Assembleia"],
        "publicado_em": pd.to_datetime(["2026-10-08", "2026-09-20", "2026-09-01", "2026-10-01"]).date,
    }))  # fmt: skip
    _grava(r, "eventos/2025", pd.DataFrame({
        "cnpj": ["1"], "rotulo": ["x"], "assunto": ["x"], "empresa": [NOME_SECRETO], "categoria": ["Fato Relevante"],
        "publicado_em": pd.to_datetime(["2025-09-25"]).date,
    }))  # fmt: skip
    _grava(r, "ofertas/resolucao_160", pd.DataFrame({
        "nome_emissor": [NOME_SECRETO] * 4, "nome_lider": [NOME_SECRETO] * 4,
        "valor_mobiliario": ["Debêntures", "Debêntures", "Cotas de FIDC", "Debêntures"],
        "data_registro": pd.to_datetime(["2026-10-01", "2026-01-15", "2026-05-01", "2025-06-01"]),
        "valor_total_registrado": [100.0, 50.0, 30.0, 40.0],
    }))  # fmt: skip
    _grava(r, "rede/ligacoes", pd.DataFrame({
        "tipo": ["detem", "detem", "audita", "controlada_de"],
        "fonte": ["cvm-cda", "cvm-cda", "cvm-fca", "cvm-fre"],
        "ate": pd.to_datetime([None, "2025-01-01", None, None]),
        "publico_em": pd.to_datetime(["2026-10-01", "2024-01-01", "2026-01-01", "2026-10-10"]),
    }))  # fmt: skip
    return r


def _contexto(raiz, hoje=HOJE):
    return an.Contexto(
        raiz=raiz, hoje=hoje, foto=fo.fotografar(raiz), porta=Porta(raiz)
    )


def test_faixa_das_notas():
    assert an.faixa("AAA") == "AAA" and an.faixa("Aaa") == "AAA"
    assert an.faixa("AA-") == "AA" and an.faixa("Aa3") == "AA"
    assert an.faixa("brBB+") == "BB" and an.faixa("Baa2") == "BBB"
    assert an.faixa("A(bra)") == "A"
    assert an.faixa("Caa1") == "CCC ou abaixo"
    assert an.faixa("RD") == "RD, SD ou D" and an.faixa("D") == "RD, SD ou D"
    assert an.faixa(None) == "sem nota"


def test_ratings_por_agencia_e_faixa(raiz):
    s = an.ratings(_contexto(raiz))
    assert s.numeros["ratings"] == 5
    assert s.numeros["grau_de_investimento"] == 3  # AAA, AA-, Baa2
    assert s.numeros["ultimos_30_dias"] == 3
    assert ["Fitch", "1", "1", "0", "0", "0", "0", "0", "0", "2"] in s.linhas


def test_pgfn_usa_o_retrato_mais_novo_e_soma_por_tipo(raiz):
    s = an.pgfn(_contexto(raiz))
    assert s.numeros["retrato"] == "2026-06"
    assert s.numeros["valor"] == 1000.0
    assert s.numeros["inscricoes"] == 10
    assert s.numeros["ajuizado"] == pytest.approx(0.7)
    assert s.linhas[0][0] == "Não previdenciária"  # o maior valor primeiro


def test_insolvencia_conta_empresas_por_ano_sem_terceiro(raiz):
    s = an.insolvencia(_contexto(raiz))
    por_ano = {l[0]: l for l in s.linhas}
    assert por_ano["2025"][1:4] == [
        "1",
        "0",
        "1",
    ]  # RJ: 1 empresa (2 documentos); falência: 1
    assert por_ano["2024"][1] == "1"
    assert s.numeros["empresas"] == 3  # a exposição a terceiro não entra


def test_trocas_de_auditor_por_ano(raiz):
    s = an.trocas_de_auditor(_contexto(raiz))
    por_ano = {l[0]: l[1] for l in s.linhas}
    assert por_ano == {"2017": "1", "2022": "2", "2023": "1"}
    assert s.numeros["ano_com_mais"] == 2022


def test_curva_hoje_ha_um_mes_e_ha_um_ano(raiz):
    s = an.curva_juros(_contexto(raiz))
    assert s.numeros["data_base"] == "2026-10-13"
    assert s.numeros["nominal_1a"] == pytest.approx(0.14)
    assert s.numeros["nominal_1a_ha_um_mes"] == pytest.approx(0.15)
    assert s.numeros["nominal_1a_ha_um_ano"] == pytest.approx(0.11)
    assert s.numeros["inclinacao_nominal"] == pytest.approx(-0.01)


def test_eventos_ultimos_30_dias_contra_o_ano_anterior(raiz):
    s = an.eventos(_contexto(raiz))
    assert s.numeros["ate"] == "2026-10-08"  # a janela termina no documento mais novo
    assert s.numeros["documentos_30_dias"] == 3  # 08/10, 20/09 e 01/10
    assert s.numeros["fatos_relevantes_30_dias"] == 2
    assert s.numeros["fatos_relevantes_ano_anterior"] == 1


def test_ofertas_12_meses(raiz):
    s = an.ofertas(_contexto(raiz))
    assert s.numeros["valor_12_meses"] == 180.0
    assert s.numeros["valor_12_meses_antes"] == 40.0
    assert s.linhas[0][0] == "Debêntures"


def test_rede_por_tipo(raiz):
    s = an.rede(_contexto(raiz))
    assert s.numeros["ligacoes"] == 4
    assert s.numeros["ativas"] == 3
    assert s.numeros["publicas_30_dias"] == 2


def test_retrato_sai_so_da_fotografia(raiz):
    s = an.retrato(_contexto(raiz))
    assert s.numeros["tabelas"] == len(fo.fotografar(raiz)["tabelas"])


def test_nenhuma_analise_mostra_nome_de_empresa(raiz):
    ctx = _contexto(raiz)
    for analise in an.ANALISES:
        s = analise(ctx)
        texto = repr(s)
        assert NOME_SECRETO not in texto, analise.__name__


def test_so_le_tabelas_permitidas(raiz):
    with pytest.raises(an.TabelaProibidaError):
        an.consultar(_contexto(raiz), "fre_conselho", "SELECT cnpj FROM {t}")


def test_rodizio_escolhe_pelo_dia_e_pula_a_que_falta(raiz):
    n = len(an.ANALISES)
    dias = [date.fromordinal(HOJE.toordinal() + i) for i in range(n)]
    nomes = [an.analise_do_dia(_contexto(raiz, d)).nome for d in dias]
    assert sorted(nomes) == sorted(
        a.__name__ for a in an.ANALISES
    )  # cada uma uma vez em n dias
    for pasta in (raiz / "ratings").iterdir():
        pasta.unlink()
    nomes = [an.analise_do_dia(_contexto(raiz, d)).nome for d in dias]
    assert "ratings" not in nomes


def test_titulos_batem_com_as_secoes(raiz):
    ctx = _contexto(raiz)
    for analise in an.ANALISES:
        assert an.TITULOS[analise.__name__] == analise(ctx).titulo
    assert an.titulo_do_dia(HOJE) == an.analise_do_dia(ctx).titulo
