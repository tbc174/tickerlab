"""Painel do café (plano do café, PR 11): cada bloco com data e fonte, e nada divulgado depois de D.

As tabelas da base são montadas à mão (o painel recebe `TabelasDoCafe` pronto) e os preços e o câmbio
vão para o acervo de séries do banco de teste. Em cada fonte há um dado divulgado **depois** de D, com
valor diferente, para o teste pegar quem olhar o futuro.

O exemplo do React (`web/testes/app/exemplos/painel_do_cafe.json`) sai daqui. Mudou o painel ou a API?
Regrave:

    .venv\\Scripts\\python -m tests.test_painel_do_cafe
"""

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from base.contrapartes import cafe as contrapartes_cafe
from src import precos_de_referencia as precos
from src.banco import series as acervo
from src.commodities.cafe import painel
from src.commodities.cafe.regioes import ARABICA, CONILON
from tests import ajudantes_do_cafe

DIA = date(2026, 5, 1)
DEPOIS = pd.Timestamp(
    "2026-05-10"
)  # tudo o que sai nesta data não pode aparecer no painel de DIA
EXEMPLO = (
    Path(__file__).resolve().parent.parent
    / "web"
    / "testes"
    / "app"
    / "exemplos"
    / "painel_do_cafe.json"
)
PTAX = acervo.SerieDoAcervo("bcb-ptax-venda", "PTAX (venda)", "R$ por US$", "diária")


# --- as tabelas da base, à mão ---------------------------------------------------------------------
def _conab() -> pd.DataFrame:
    fechadas = {
        s: {1: 50_000.0 + 1_000 * (s % 2), 4: 48_000.0} for s in range(2018, 2026)
    }
    arabica = ajudantes_do_cafe.tabela({**fechadas, 2026: {1: 55_000.0, 2: 99_999.0}})
    mg = ajudantes_do_cafe.tabela({2026: {1: 30_000.0}}, uf="MG")
    conilon = ajudantes_do_cafe.tabela(
        {2025: {1: 20_000.0, 4: 22_000.0}, 2026: {1: 24_000.0}}, tipo=CONILON
    )
    return pd.concat([arabica, mg, conilon], ignore_index=True)


def _cftc() -> pd.DataFrame:
    relatorios = pd.date_range("2025-01-07", "2026-04-28", freq="7D")
    tabela = pd.DataFrame(
        {
            "relatorio": relatorios,
            "contrato": painel.CONTRATO_DO_ARABICA,
            "open_interest": 200_000.0,
            "managed_money_long": 60_000.0,
            "managed_money_short": 20_000.0,
            "managed_money_spread": 5_000.0,
            "disponivel_em": relatorios + pd.Timedelta(days=4),
        }
    )
    tabela.loc[tabela.index[-1], "managed_money_long"] = (
        150_000.0  # o de 28/04 só vale em 02/05
    )
    return tabela


def _usda() -> pd.DataFrame:
    linhas = []
    for pais, producao in (("BR", 60_000.0), ("VM", 30_000.0)):
        for safra in range(2015, 2026):
            for atributo, tipo, valor in (
                ("producao", "total", producao),
                ("producao", ARABICA, producao * 0.7),
                ("producao", CONILON, producao * 0.3),
                ("consumo_domestico", "total", producao / 3),
                ("estoque_final", "total", producao / 6),
            ):
                linhas.append(
                    (
                        pais,
                        pais,
                        safra,
                        atributo,
                        tipo,
                        valor,
                        "mil sacas",
                        pd.Timestamp("2025-12-31"),
                    )
                )
    linhas.append(
        ("BR", "BR", 2025, "estoque_final", "total", 99_999.0, "mil sacas", DEPOIS)
    )
    return pd.DataFrame(linhas, columns=["codigo_do_pais", "pais", "ano_safra", "atributo", "tipo", "valor",
                                         "unidade", "divulgado_em"])  # fmt: skip


def _comex() -> pd.DataFrame:
    linhas = []
    for competencia in pd.date_range("2025-02-28", "2026-04-30", freq="ME"):
        divulgado = competencia + pd.Timedelta(days=10)
        for uf, pais, sacas in (
            ("MG", "Estados Unidos", 300.0),
            ("MG", "Alemanha", 200.0),
            ("ES", "Bélgica", 100.0),
        ):
            linhas.append({
                "competencia": competencia, "ncm": "09011110", "uf_origem": uf, "codigo_do_pais": pais[:3],
                "pais_destino": pais, "vl_fob_usd": sacas * 250, "kg_liquido": sacas * 60, "sacas": sacas,
                "tipo": "total", "proxy_conilon": uf == "ES", "divulgado_em": divulgado,
            })  # fmt: skip
    return pd.DataFrame(linhas)


def _clima() -> pd.DataFrame:
    regiao = painel.regiao_padrao(ARABICA).id
    competencias = pd.date_range("2025-01-31", "2026-03-31", freq="ME")
    return pd.DataFrame(
        {
            "regiao": regiao, "competencia": competencias, "fonte": "inmet", "chuva_mm": 100.0,
            "tmin_media_c": 15.0, "dias_tmin_abaixo_de_2c": 0.0, "tmax_media_c": 28.0, "n_estacoes": 5,
            "chuva_normal_mm": 120.0, "chuva_anomalia_mm": -20.0, "tmin_normal_c": 14.0,
            "tmin_anomalia_c": 1.0, "tmax_normal_c": 27.0, "tmax_anomalia_c": 1.0, "anos_na_normal": 30,
            "disponivel_em": competencias + pd.Timedelta(days=45),  # março só sai em 15/05
        }
    )  # fmt: skip


def tabelas_de_exemplo() -> painel.TabelasDoCafe:
    tabelas = {
        "cftc": _cftc(),
        "comex": _comex(),
        "usda": _usda(),
        "conab": _conab(),
        "clima": _clima(),
    }
    return painel.TabelasDoCafe(tabelas)


# --- os preços e o câmbio, no acervo ---------------------------------------------------------------
def semear_acervo(conexao) -> None:
    meses = pd.date_range("2021-04-01", "2026-03-01", freq="MS")
    for chave, base in (("cafe-arabica", 8.0), ("cafe-robusta", 4.0)):
        codigo = f"bm-pink-{chave}"
        acervo.garantir_serie(conexao, precos.serie_do_acervo(codigo))
        valores = pd.Series(
            [base + 0.01 * i for i in range(len(meses))], index=meses, dtype=float
        )
        acervo.gravar(conexao, codigo, valores, date(2026, 4, 5))
        abril = pd.Series([base * 10], index=[pd.Timestamp("2026-04-01")], dtype=float)
        acervo.gravar(conexao, codigo, abril, DEPOIS.date())  # o de abril sai em maio
    acervo.garantir_serie(conexao, PTAX)
    dias = pd.bdate_range("2025-01-02", "2026-04-30")
    acervo.gravar(
        conexao, PTAX.codigo, pd.Series(5.0, index=dias, dtype=float), date(2026, 4, 30)
    )
    depois = pd.Series([9.0], index=[DEPOIS], dtype=float)
    acervo.gravar(conexao, PTAX.codigo, depois, DEPOIS.date())


@pytest.fixture
def conexao(banco):
    with banco.begin() as escrita:
        semear_acervo(escrita)
    with banco.connect() as leitura:
        yield leitura


def _montar(conexao, tipo=ARABICA, **opcoes) -> painel.PainelDoCafe:
    opcoes.setdefault("tabelas", tabelas_de_exemplo())
    return painel.montar_painel(conexao, tipo, DIA, **opcoes)


# --- os testes -------------------------------------------------------------------------------------
@pytest.mark.parametrize("tipo", painel.TIPOS)
def test_cada_bloco_tem_o_que_e_fonte_e_data_ou_o_motivo(conexao, tipo):
    resultado = _montar(conexao, tipo)
    for bloco in resultado.blocos:
        assert bloco.titulo and bloco.o_que_e and bloco.fonte, bloco.chave
        if bloco.conteudo is None:
            assert bloco.motivo_sem_dado, bloco.chave
        else:
            assert bloco.data is not None and bloco.data <= DIA, bloco.chave
    assert (
        resultado.aviso_diario
        == "Preço de referência mensal; o diário depende de licença."
    )


def test_painel_como_estava_em_d(conexao):
    """Nada divulgado depois de D entra: o 2º levantamento da CONAB, o COT de 28/04, a revisão do
    USDA, o Comex de abril, o clima de março, o preço de abril e a PTAX de maio."""
    p = _montar(conexao)
    assert p.safra.conteudo is not None
    assert (p.safra.conteudo.safra, p.safra.conteudo.levantamento) == (2026, 1)
    assert p.safra.conteudo.linhas[0].uf == "BRASIL"
    assert p.safra.conteudo.linhas[0].producao_mil_sacas == 55_000.0
    assert p.fundos.conteudo is not None
    assert p.fundos.conteudo.relatorio == date(2026, 4, 21)
    assert p.fundos.conteudo.comprados_lotes == 60_000.0
    assert p.balanco.conteudo is not None
    ultima = p.balanco.conteudo.estoque_consumo_brasil[-1]
    assert ultima.ano_safra == 2025 and ultima.valor == pytest.approx(0.5)
    assert p.exportacoes.data == date(2026, 3, 31)
    assert p.clima.data == date(2026, 2, 28)
    assert p.preco_de_referencia.conteudo is not None
    assert p.preco_de_referencia.conteudo.item.ultimo_mes == date(2026, 3, 1)
    assert p.cambio.conteudo is not None
    assert p.cambio.conteudo.ultimo_valor == 5.0
    for ficha in p.contrapartes.conteudo.fichas if p.contrapartes.conteudo else ():
        assert all(f.divulgado_em <= DIA for f in ficha.fatos)


def test_um_dia_depois_o_dado_novo_aparece(conexao):
    depois = painel.montar_painel(
        conexao, ARABICA, date(2026, 5, 25), tabelas=tabelas_de_exemplo()
    )
    assert depois.safra.conteudo is not None and depois.safra.conteudo.levantamento == 2
    assert depois.fundos.conteudo is not None
    assert depois.fundos.conteudo.relatorio == date(2026, 4, 28)
    assert (
        depois.cambio.conteudo is not None
        and depois.cambio.conteudo.ultimo_valor == 9.0
    )


def test_fundos_em_lotes_sacas_e_fracao_do_interesse_aberto(conexao):
    fundos = _montar(conexao).fundos.conteudo
    assert fundos is not None
    assert fundos.liquido_lotes == 40_000.0
    assert fundos.liquido_sacas == pytest.approx(40_000 * 283.5, rel=1e-3)
    assert fundos.fracao_do_interesse_aberto == pytest.approx(0.2)
    assert "não é consenso" in fundos.legenda


def test_conilon_sem_fundos_e_sem_bienalidade_com_o_motivo(conexao):
    p = _montar(conexao, CONILON)
    assert p.fundos.conteudo is None and "Londres" in (p.fundos.motivo_sem_dado or "")
    assert p.bienalidade.conteudo is None and "cheia e vazia" in (
        p.bienalidade.motivo_sem_dado or ""
    )
    assert (
        p.preco_de_referencia.conteudo is not None
        and p.preco_de_referencia.conteudo.item.chave == "cafe-robusta"
    )
    assert p.balanco.conteudo is not None
    assert {pais.codigo_do_pais for pais in p.balanco.conteudo.paises} == {"BR", "VM"}
    assert p.regiao == painel.regiao_padrao(CONILON).id


def test_termometro_mostra_o_erro_historico_sem_a_safra_em_curso(conexao):
    termo = _montar(conexao).termometro.conteudo
    assert termo is not None
    assert [e.safra for e in termo.erros] == list(range(2018, 2026))
    assert termo.maior_erro_pct == pytest.approx(100 * 3_000 / 48_000)
    assert termo.menor_erro_pct == pytest.approx(100 * 2_000 / 48_000)
    assert termo.vies_medio_pct is not None


def test_exportacoes_dos_ultimos_12_meses_por_destino(conexao):
    exportacoes = _montar(conexao).exportacoes.conteudo
    assert exportacoes is not None
    assert (exportacoes.primeiro_mes, exportacoes.ultimo_mes) == (
        date(2025, 4, 1),
        date(2026, 3, 31),
    )
    assert exportacoes.sacas == 12 * 600
    assert [d.pais for d in exportacoes.destinos] == [
        "Estados Unidos",
        "Alemanha",
        "Bélgica",
    ]
    assert exportacoes.fracao_do_espirito_santo == pytest.approx(1 / 6)


def test_clima_chuva_de_tres_meses_contra_a_normal(conexao):
    clima = _montar(conexao).clima.conteudo
    assert clima is not None
    assert clima.chuva["valor"] == 300.0 and clima.chuva["normal"] == 360.0
    assert (clima.chuva["inicio"], clima.chuva["fim"]) == ("2025-12-01", "2026-02-28")
    assert clima.temperatura.tmin_anomalia_c == 1.0


def test_sem_as_tabelas_da_base_cada_bloco_diz_o_motivo(banco):
    with banco.connect() as vazio:
        p = painel.montar_painel(vazio, ARABICA, DIA, tabelas=painel.TabelasDoCafe())
    for chave, tabela in (("fundos", "cftc_cot_agro"), ("exportacoes", "comex_cafe"), ("balanco", "usda_psd_cafe"),
                          ("safra", "conab_cafe"), ("clima", "clima_regiao_cafe")):  # fmt: skip
        bloco = getattr(p, chave)
        assert bloco.conteudo is None and tabela in (bloco.motivo_sem_dado or ""), chave
    assert p.preco_de_referencia.conteudo is None and "Banco Mundial" in (
        p.preco_de_referencia.motivo_sem_dado or ""
    )
    assert p.cambio.conteudo is None and "PTAX" in (p.cambio.motivo_sem_dado or "")
    assert (
        p.calendario.conteudo is not None
    )  # o calendário não depende de dado coletado


def test_acervo_desligado_vira_motivo_e_nao_erro(monkeypatch):
    from src import acervo as acervo_de_arquivos

    monkeypatch.setattr(acervo_de_arquivos, "pasta_do_acervo", lambda: None)
    tabelas = painel.tabelas_pela_porta()
    assert not tabelas.tabelas
    assert "ainda não chega a este servidor" in tabelas.motivo("conab")


def test_base_sem_as_tabelas_do_cafe_vira_motivo_por_tabela(tmp_path, monkeypatch):
    from src import acervo as acervo_de_arquivos

    (tmp_path / "base").mkdir()
    monkeypatch.setattr(acervo_de_arquivos, "pasta_do_acervo", lambda: tmp_path)
    tabelas = painel.tabelas_pela_porta()
    assert not tabelas.tabelas
    assert tabelas.motivo("cftc") == painel.motivo_sem_tabela("cftc_cot_agro")


def test_tipo_e_regiao_invalidos(conexao):
    with pytest.raises(ValueError, match="tipo"):
        _montar(conexao, "robusta")
    with pytest.raises(ValueError, match="região"):
        _montar(conexao, regiao="marte")


def _textos(valor: object):
    if isinstance(valor, dict):
        for v in valor.values():
            yield from _textos(v)
    elif isinstance(valor, list):
        for v in valor:
            yield from _textos(v)
    elif isinstance(valor, str):
        yield valor


@pytest.mark.parametrize("tipo", painel.TIPOS)
def test_nenhuma_palavra_vedada_e_o_json_e_simples(conexao, tipo):
    dado = painel.em_dicionario(_montar(conexao, tipo))
    json.dumps(dado, allow_nan=False)
    for texto in _textos(dado):
        assert not contrapartes_cafe.palavras_vedadas_em(texto), texto


# --- o exemplo do React ----------------------------------------------------------------------------
def exemplo_do_react() -> dict:
    """A resposta da API para os dados deste arquivo (o teste do React desenha a tela com ela)."""
    from tempfile import TemporaryDirectory

    from src.api_v1 import esquemas
    from src.banco.conexao import criar_engine, migrar_para

    with TemporaryDirectory() as pasta:
        url = f"sqlite:///{(Path(pasta) / 'exemplo.sqlite').as_posix()}"
        migrar_para("head", url=url)
        motor = criar_engine(url)
        with motor.begin() as escrita:
            semear_acervo(escrita)
        with motor.connect() as leitura:
            resultado = painel.montar_painel(
                leitura, ARABICA, DIA, tabelas=tabelas_de_exemplo()
            )
        motor.dispose()
    return {"resposta": esquemas.de_painel_do_cafe(resultado).model_dump(mode="json")}


def _em_json(dados: dict) -> str:
    return json.dumps(dados, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def test_o_exemplo_do_react_esta_em_dia():
    assert EXEMPLO.exists(), "rode: python -m tests.test_painel_do_cafe"
    gravado = json.loads(EXEMPLO.read_text(encoding="utf-8"))
    assert gravado == json.loads(_em_json(exemplo_do_react())), (
        "o exemplo do React está velho: python -m tests.test_painel_do_cafe"
    )


if __name__ == "__main__":
    EXEMPLO.write_text(_em_json(exemplo_do_react()), encoding="utf-8")
    print(f"gravado: {EXEMPLO}")
