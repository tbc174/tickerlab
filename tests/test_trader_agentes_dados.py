"""Os dados da rodada dos agentes: COTAHIST anual e diário da B3, cadastro, balanços e insolvência."""

import json
import zipfile
from datetime import date

import pandas as pd
import pytest

from trader import calendario
from trader.agentes import dados as dados_da_rodada
from trader.agentes import rodada
from trader.estrategias import dados_f_b3

DIA_DOS_DADOS = date(2026, 11, 30)  # o pregão anterior à rodada de 01/12/2026
PREGOES = calendario.pregoes(date(2026, 6, 1), DIA_DOS_DADOS)
DIARIOS = PREGOES[-3:]  # os três últimos pregões chegam pelo COTAHIST do dia
DEPOIS = date(2026, 12, 1)
# ticker → (CNPJ, volume financeiro diário em reais); a BBBB está em recuperação judicial
EMPRESAS = {
    "AAAA3": ("11.111.111/0001-11", 10_000_000),
    "BBBB3": ("22.222.222/0001-22", 20_000_000),
    "CCCC3": ("33.333.333/0001-33", 1_000_000),
}
ESPECIFICACAO = "ON NM"


def _linha(dia, ticker, fechamento=1000, volume=None):
    """Um registro 01 do mercado à vista; preços e volume em centavos, como no arquivo."""
    if volume is None:
        volume = EMPRESAS[ticker][1] * dados_f_b3.CENTAVOS
    campos = {
        "tipo": "01",
        "data": f"{dia:%Y%m%d}",
        "ticker": f"{ticker:<12}",
        "mercado": dados_f_b3.MERCADO_A_VISTA,
        "especificacao": f"{ESPECIFICACAO:<10}",
        "abertura": f"{fechamento:013d}",
        "fechamento": f"{fechamento:013d}",
        "volume": f"{volume:018d}",
        "isin": f"BR{ticker[:4]}ACNOR1",
    }
    linha = [" "] * 245
    for nome, valor in campos.items():
        inicio, fim = dados_f_b3.CAMPOS[nome]
        linha[inicio:fim] = list(valor)
    return "".join(linha)


def _zip(caminho, nome_do_txt, linhas):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    conteudo = "\n".join(
        ["00COTAHIST.2026BOVESPA".ljust(245), *linhas, "99".ljust(245)]
    )
    with zipfile.ZipFile(caminho, "w") as pacote:
        pacote.writestr(nome_do_txt, conteudo.encode("latin-1"))


def _pregao(dia, fechamento=1000):
    return [_linha(dia, ticker, fechamento) for ticker in EMPRESAS]


def _insolvencia(linhas):
    return pd.DataFrame(
        {
            "cnpj": [cnpj for cnpj, _, _ in linhas],
            "rotulo": [rotulo for _, rotulo, _ in linhas],
            "conhecido_em": [pd.Timestamp(dia) for _, _, dia in linhas],
        }
    )


def _acervo(tmp_path, pregoes_do_anual=PREGOES, extras_do_anual=()):
    """Um acervo de mentira: anual de 2026, três diários, FCA, balanços e insolvência."""
    anuais = tmp_path / "anuais"
    diarios = tmp_path / "bruto" / "b3-cotahist-dia"
    base = tmp_path / "base"
    linhas = [linha for dia in pregoes_do_anual for linha in _pregao(dia)]
    _zip(
        anuais / "COTAHIST_A2026.ZIP",
        "COTAHIST_A2026.TXT",
        [*linhas, *extras_do_anual],
    )
    for dia in DIARIOS:
        _zip(
            diarios / "2026" / f"{dia:%Y%m%d}.zip",
            f"COTAHIST_D{dia:%d%m%Y}.TXT",
            _pregao(dia, fechamento=2000),
        )
    (base / "fca").mkdir(parents=True)
    pd.DataFrame(
        {
            "emissor": [t[:4] for t in EMPRESAS],
            "cnpj": [cnpj for cnpj, _ in EMPRESAS.values()],
        }
    ).to_parquet(base / "fca" / "emissores.parquet")
    pd.DataFrame(
        {"codigo": list(EMPRESAS), "inicio_negociacao": pd.Timestamp("2015-01-02")}
    ).to_parquet(base / "fca" / "tickers.parquet")
    (base / "demonstracoes").mkdir()
    pd.DataFrame(
        {
            "cnpj": [cnpj for cnpj, _ in EMPRESAS.values()],
            "grupo": "con",
            "demonstracao": "DRE",
            "conta": "3.11",
            "inicio": pd.Timestamp("2026-01-01"),
            "fim": pd.Timestamp("2026-06-30"),
            "valor": 100.0,
            "divulgado_em": pd.Timestamp("2026-08-10"),
            "ate": pd.NaT,
            "versao": 1,
        }
    ).to_parquet(base / "demonstracoes" / "2026.parquet")
    (base / "insolvencia").mkdir()
    _insolvencia(
        [("22.222.222/0001-22", "recuperacao_judicial", "2026-08-01")]
    ).to_parquet(base / "insolvencia" / "2026.parquet")
    return {
        "pasta_do_acervo": base,
        "pasta_dos_anuais": anuais,
        "pasta_dos_diarios": diarios,
    }


def test_carrega_os_pregoes_ate_o_dia_dos_dados(tmp_path):
    dados = dados_da_rodada.carregar(DIA_DOS_DADOS, **_acervo(tmp_path))
    assert [dia.date() for dia in dados.fechamento.index] == PREGOES
    assert sorted(dados.fechamento.columns) == sorted(EMPRESAS)
    assert dados.volume.loc[pd.Timestamp(PREGOES[0]), "AAAA3"] == 10_000_000
    assert dados.cadastro.loc["AAAA3", "cnpj"] == "11.111.111/0001-11"
    assert dados.cadastro.loc["AAAA3", "inicio_negociacao"] == pd.Timestamp(
        "2015-01-02"
    )


def test_no_mesmo_pregao_vale_o_diario(tmp_path):
    ultimo = DIARIOS[-1]
    so_no_anual = _linha(ultimo, "ZZZZ3", volume=1)
    dados = dados_da_rodada.carregar(
        DIA_DOS_DADOS, **_acervo(tmp_path, extras_do_anual=[so_no_anual])
    )
    assert dados.fechamento.loc[pd.Timestamp(ultimo), "AAAA3"] == 20.0
    assert dados.fechamento.loc[pd.Timestamp(PREGOES[0]), "AAAA3"] == 10.0
    assert "ZZZZ3" not in dados.fechamento.columns


def test_corta_o_que_veio_depois_do_dia_dos_dados(tmp_path):
    futuro = _pregao(DEPOIS, fechamento=9999)
    dados = dados_da_rodada.carregar(
        DIA_DOS_DADOS, **_acervo(tmp_path, extras_do_anual=futuro)
    )
    assert dados.fechamento.index.max() == pd.Timestamp(DIA_DOS_DADOS)


def test_pregao_faltando_para_listando_as_datas_e_o_arquivo(tmp_path):
    buraco = PREGOES[-10]
    sem_um = [dia for dia in PREGOES if dia != buraco]
    with pytest.raises(dados_da_rodada.FaltamPregoesError) as erro:
        dados_da_rodada.carregar(DIA_DOS_DADOS, **_acervo(tmp_path, sem_um))
    assert buraco.isoformat() in str(erro.value)
    assert "COTAHIST_A2026.ZIP" in str(erro.value)


def test_so_os_diarios_nao_bastam_para_a_liquidez(tmp_path):
    acervo = _acervo(tmp_path)
    (acervo["pasta_dos_anuais"] / "COTAHIST_A2026.ZIP").unlink()
    with pytest.raises(dados_da_rodada.FaltamPregoesError):
        dados_da_rodada.carregar(DIA_DOS_DADOS, **acervo)


def test_recuperacao_judicial_pelo_que_a_cvm_recebeu():
    insolvencia = _insolvencia(
        [
            ("11.111.111/0001-11", "recuperacao_judicial", "2026-03-01"),
            ("11.111.111/0001-11", "recuperacao_judicial", "2026-05-01"),
            ("22.222.222/0001-22", "exposicao_a_terceiro", "2026-04-01"),
            ("33.333.333/0001-33", "falencia", "2026-12-05"),
        ]
    )
    tabela = dados_da_rodada.recuperacao_judicial(insolvencia, DIA_DOS_DADOS)
    assert tabela.to_dict("records") == [
        {
            "cnpj": "11.111.111/0001-11",
            "inicio": pd.Timestamp("2026-03-01"),
            "fim": pd.Timestamp("2027-05-01"),
        }
    ]


def test_candidatas_com_os_dados_carregados(tmp_path):
    """A BBBB passa da liquidez, mas está em recuperação judicial; a CCCC não passa do piso."""
    dados = dados_da_rodada.carregar(DIA_DOS_DADOS, **_acervo(tmp_path))
    lista = rodada.candidatas(pd.Timestamp(DIA_DOS_DADOS), dados)
    assert [(c.ticker, c.cnpj) for c in lista] == [("AAAA3", "11.111.111/0001-11")]


def test_preparar_pela_linha_de_comando(tmp_path, monkeypatch):
    acervo = _acervo(tmp_path / "acervo")
    pedidos = []
    original = dados_da_rodada.carregar

    def carregar(dia):
        pedidos.append(dia)
        return original(dia, **acervo)

    monkeypatch.setattr(rodada, "_hoje", lambda: DEPOIS)
    monkeypatch.setattr(dados_da_rodada, "carregar", carregar)
    pasta = tmp_path / "agentes"
    assert rodada.main(["preparar", "--pasta", str(pasta)]) == 0
    assert pedidos == [DIA_DOS_DADOS]
    preparo = json.loads((pasta / "2026-12" / "candidatas.json").read_text("utf-8"))
    assert preparo["dia_dos_dados"] == DIA_DOS_DADOS.isoformat()
    assert [c["ticker"] for c in preparo["candidatas"]] == ["AAAA3"]
    assert (pasta / "2026-12" / "pedidos" / "AAAA3.md").exists()


def test_recuperacao_judicial_com_anos_juntados_sem_refazer_o_indice():
    """Dois anos da insolvência lidos e juntados repetem o índice (0, 1, ... de cada arquivo)."""
    um_ano = _insolvencia(
        [
            ("22.222.222/0001-22", "exposicao_a_terceiro", "2025-10-01"),
            ("11.111.111/0001-11", "recuperacao_judicial", "2025-11-03"),
        ]
    )
    outro = _insolvencia([("11.111.111/0001-11", "recuperacao_judicial", "2026-02-02")])
    tabela = dados_da_rodada.recuperacao_judicial(
        pd.concat([um_ano, outro]), DIA_DOS_DADOS
    )
    assert tabela["inicio"].tolist() == [pd.Timestamp("2025-11-03")]
    assert tabela["fim"].tolist() == [pd.Timestamp("2027-02-02")]
