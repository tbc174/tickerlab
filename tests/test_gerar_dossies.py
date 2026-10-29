"""As fichas do dossiê gravadas a partir de uma mini-base (plano de 17/10/2026, PR 1, tarefa 8; PR 1b:
tudo lido pela porta da base, `base.porta`).

A mini-base: a CPFL (ticker CPFE3, auditor, uma distribuidora na ANEEL, um fato relevante de aquisição)
e a Sem Nada S.A. (ticker, mas nenhuma tabela fala dela). Um auditor pessoa física na rede.
"""

import json
from pathlib import Path

import pandas as pd
import pytest

from base import dossie
from base.porta import Porta
from scripts import gerar_dossies
from tests import test_dossie_geracao_de_caixa as geracao_de_caixa
from tests import test_dossie_governanca_e_credito as governanca_e_credito
from tests.test_porta import _entidades, _identificadores, _ligacoes

D = pd.Timestamp
CPFL, SEM_NADA = "02.429.144/0001-93", "11.111.111/0001-11"
CPFL_DIGITOS = "02429144000193"
DISTRIBUIDORA = "33050196000188"


def _gravar(pasta: Path, relativo: str, tabela: pd.DataFrame) -> None:
    destino = pasta / relativo
    destino.parent.mkdir(parents=True, exist_ok=True)
    tabela.to_parquet(destino)
    destino.with_suffix(".json").write_text(
        json.dumps({"sha256_da_tabela": f"hash-{destino.stem}"}), encoding="utf-8"
    )


def _mini_base(pasta: Path) -> None:
    _gravar(
        pasta,
        "fca/tickers.parquet",
        pd.DataFrame(
            {
                "codigo": ["CPFE3", "SNDA3", "VELH3"],
                "cnpj": [CPFL, SEM_NADA, "22.222.222/0001-22"],
                "empresa": ["CPFL ENERGIA S.A.", "SEM NADA S.A.", "VELHA S.A."],
                "valido_ate": [pd.NaT, pd.NaT, D("2020-01-01")],
            }
        ),
    )
    _gravar(
        pasta,
        "auditores/2025.parquet",
        pd.DataFrame(
            {
                "cnpj": [CPFL],
                "referencia": [D("2025-01-01")],
                "versao": [1],
                "auditor_id": ["rede:deloitte"],
                "auditor": ["Deloitte"],
                "auditor_cnpj": ["49928567000111"],
                "inicio": [D("2025-04-01")],
                "fim": [pd.NaT],
            }
        ),
    )
    _gravar(
        pasta,
        "eventos/2025.parquet",
        pd.DataFrame(
            {
                "cnpj": [CPFL, CPFL],
                "rotulo": ["Fato relevante", "Fato relevante"],
                "assunto": ["Aquisição da Enercan", "Resultado do 2T25"],
                "publicado_em": [D("2025-03-01"), D("2025-08-01")],
                "link": ["l1", "l2"],
            }
        ),
    )
    _gravar(
        pasta,
        "empresa_serie/empresa_serie.parquet",
        pd.DataFrame(
            {
                "fonte": ["aneel-samp"],
                "chave": [DISTRIBUIDORA],
                "nome": ["CPFL Paulista"],
                "cnpj_companhia": [CPFL_DIGITOS],
                "via": ["controlada"],
                "principal": [True],
                "desde": [D("2010-05-01")],
            }
        ),
    )
    _gravar(
        pasta,
        "setoriais/aneel/2025.parquet",
        pd.DataFrame(
            {
                "competencia": [D("2025-11-30"), D("2025-12-31"), D("2025-12-31")],
                "cnpj": [DISTRIBUIDORA, DISTRIBUIDORA, "99999999000199"],
                "valor": [100.0, 110.0, 890.0],
                "detalhe_do_mercado": ["Número de consumidores"] * 3,
                "tipo_de_mercado": ["Regular"] * 3,
            }
        ),
    )
    _gravar(
        pasta,
        "rede/entidades.parquet",
        pd.DataFrame(
            {
                "id_entidade": ["E1"],
                "nome": ["Fulano de Tal"],
                "trata_como_pessoa": [True],
            }
        ),
    )


def _montar(pasta: Path, saida: Path) -> gerar_dossies.Resumo:
    return gerar_dossies.montar(pasta, saida, D("2026-10-17 07:00"), "abc1234")


def test_grava_uma_ficha_por_empresa_com_dados(tmp_path: Path) -> None:
    _mini_base(tmp_path / "base")
    resumo = _montar(tmp_path / "base", tmp_path / "dossies")
    pasta_do_dia = tmp_path / "dossies" / "2026-10-17"
    assert sorted(p.name for p in pasta_do_dia.iterdir()) == [
        f"{CPFL_DIGITOS}.json",
        "manifesto.json",
    ]
    ficha = json.loads(
        (pasta_do_dia / f"{CPFL_DIGITOS}.json").read_text(encoding="utf-8")
    )
    chaves = [s["chave"] for s in ficha["secoes"]]
    assert chaves == ["auditor_e_controladas", "setor_regulado", "setor", "negocios"]
    setor = ficha["secoes"][1]["tabelas"]["aneel_consumidores"][0]
    assert setor == {
        "ano": 2025,
        "valor": 110.0,
        "participacao": pytest.approx(0.11),
        "meses": 2,
        "ultimo_mes": "2025-12-31",
    }
    assert resumo.fichas == 1
    assert resumo.empresas == 2  # o ticker que deixou de valer fica fora
    assert resumo.falhas == []


def test_manifesto_traz_versao_hashes_e_tabelas_que_faltam(tmp_path: Path) -> None:
    _mini_base(tmp_path / "base")
    _montar(tmp_path / "base", tmp_path / "dossies")
    manifesto = json.loads(
        (tmp_path / "dossies" / "2026-10-17" / "manifesto.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifesto["versao_do_esquema"] == dossie.VERSAO_DO_ESQUEMA
    assert manifesto["versao_do_codigo"] == "abc1234"
    assert manifesto["tabelas"]["auditores/2025"] == "hash-2025"
    assert "trocas_de_auditor" in manifesto["faltando"]  # o nome da tabela na porta
    assert manifesto["fichas"] == 1


def test_secao_que_quebra_nao_derruba_as_outras(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mini_base(tmp_path / "base")

    def quebra(*_: object) -> None:
        raise ValueError("coluna sumiu")

    monkeypatch.setattr(gerar_dossies.dossie, "secao_negocios", quebra)
    resumo = _montar(tmp_path / "base", tmp_path / "dossies")
    assert resumo.fichas == 1
    assert resumo.falhas == ["negocios: ValueError: coluna sumiu (2 empresas)"]


def test_ficha_com_pessoa_nao_e_gravada(tmp_path: Path) -> None:
    _mini_base(tmp_path / "base")
    # uma "controlada" que é um empresário individual: o nome é o de uma pessoa da rede
    _gravar(
        tmp_path / "base",
        "controladas/2025.parquet",
        pd.DataFrame(
            {
                "cnpj_companhia": [CPFL_DIGITOS],
                "referencia": [D("2025-01-01")],
                "versao": [1],
                "cnpj": [""],
                "razao_social": ["Fulano de Tal"],
                "tipo": ["controlada"],
                "participacao": [100.0],
            }
        ),
    )
    resumo = _montar(tmp_path / "base", tmp_path / "dossies")
    assert resumo.fichas == 0
    assert resumo.falhas == [f"{CPFL_DIGITOS}: PessoaNaFichaError"]


def test_mesmo_dia_regrava_a_pasta_inteira(tmp_path: Path) -> None:
    _mini_base(tmp_path / "base")
    sobra = tmp_path / "dossies" / "2026-10-17" / "00000000000000.json"
    sobra.parent.mkdir(parents=True)
    sobra.write_text("{}", encoding="utf-8")
    _montar(tmp_path / "base", tmp_path / "dossies")
    assert not sobra.exists()


def test_main_avisa_as_falhas_na_ultima_linha(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(gerar_dossies, "exigir_versao_do_codigo", lambda: "abc1234")
    saida = gerar_dossies.main(
        ["--pasta", str(tmp_path / "nada"), "--saida", str(tmp_path / "d")]
    )
    assert saida == 1
    assert (
        capsys.readouterr().out.strip().splitlines()[-1].startswith("FALHAS: dossiês:")
    )


def test_fundos_da_ficha_param_no_ultimo_mes_completo_do_cda(tmp_path: Path) -> None:
    _mini_base(tmp_path / "base")
    meses = pd.date_range("2025-01-31", periods=14, freq="ME")
    _gravar(
        tmp_path / "base",
        "fundos/painel_empresa/2025.parquet",
        pd.DataFrame(
            {
                "competencia": meses,
                "cnpj": [CPFL_DIGITOS] * 14,
                "tipo": ["comprado"] * 14,
                "fundos": [400] * 13 + [75],
                "valor": [9.0e9] * 13 + [1.0e9],
            }
        ),
    )
    # o último mês só tem 20% das carteiras: ainda está chegando
    # o painel por emissor mora na mesma tabela da porta e não pode somar na empresa
    _gravar(
        tmp_path / "base",
        "fundos/painel_emissor/2025.parquet",
        pd.DataFrame(
            {
                "competencia": meses,
                "emissor": ["CPFL ENERGIA"] * 14,
                "tipo": ["comprado"] * 14,
                "fundos": [999] * 14,
                "valor": [1.0e12] * 14,
            }
        ),
    )
    _gravar(
        tmp_path / "base",
        "fundos/cobertura.parquet",
        pd.DataFrame({"competencia": meses, "valor_comprado": [100.0] * 13 + [20.0]}),
    )
    _montar(tmp_path / "base", tmp_path / "dossies")
    ficha = json.loads(
        (tmp_path / "dossies" / "2026-10-17" / f"{CPFL_DIGITOS}.json").read_text(
            encoding="utf-8"
        )
    )
    fundos = next(s for s in ficha["secoes"] if s["chave"] == "ofertas_e_fundos")
    itens = {i["chave"]: i for i in fundos["itens"]}
    rastro = itens["fundos_com_a_acao"].pop("rastro")
    assert itens["fundos_com_a_acao"] == {
        "chave": "fundos_com_a_acao",
        "nome": "Fundos com a empresa na carteira",
        "valor": 400,
        "unidade": "fundos",
        "base": "2026-01-31",
    }
    # o painel deste teste não tem a coluna da publicação: o rastro sai sem o dia, nunca inventado
    assert (rastro["fonte_id"], rastro["publicado_em"]) == ("cvm", None)


def _lucro_e_capital(pasta: Path) -> None:
    """O lucro de 2023 refeito na DFP de 2024, um release diferente, insiders e um desdobramento."""
    dre = {
        "cnpj": [CPFL] * 3,
        "grupo": ["con"] * 3,
        "demonstracao": ["DRE"] * 3,
        "documento": ["DFP"] * 3,
        "conta": ["3.11", "3.11", "3.04"],
        "descricao": ["Lucro/Prejuízo Consolidado do Período"] * 2 + ["Despesas"],
        "inicio": [D("2023-01-01")] * 3,
        "fim": [D("2023-12-31")] * 3,
        "valor": [100e6, 80e6, -5e6],
        "divulgado_em": [D("2024-03-10"), D("2025-03-12"), D("2024-03-10")],
    }
    _gravar(pasta, "demonstracoes/2023.parquet", pd.DataFrame(dre))
    _gravar(
        pasta,
        "release_x_oficial/release_x_oficial.parquet",
        pd.DataFrame(
            {
                "cnpj": [CPFL],
                "protocolo": ["p1"],
                "versao": [1],
                "periodo": ["3T25"],
                "referencia": [D("2025-09-30")],
                "data_entrega": [D("2025-11-10")],
                "link": ["l"],
                "linha": ["receita_liquida"],
                "periodo_lido": ["3T25"],
                "leitura": [1],
                "valor_release_reais": [110e6],
                "valor_oficial_reais": [100e6],
                "diferenca_pct": [10.0],
                "classe": ["diferente"],
                "publico_em": [D("2025-11-10")],
            }
        ),
    )
    _gravar(
        pasta,
        "negociacoes/2026.parquet",
        pd.DataFrame(
            {
                "cnpj": [CPFL] * 2,
                "cargo": ["diretoria"] * 2,
                "operacao": ["compra"] * 2,
                "data": [D("2026-05-10"), D("2026-10-02")],
                "entregue_em": [
                    D("2026-06-10"),
                    D("2026-11-10"),
                ],  # a 2ª ainda não entregue
                "valor": [2e6, 9e6],
            }
        ),
    )
    _gravar(
        pasta,
        "eventos_de_capital/2025.parquet",
        pd.DataFrame(
            {
                "cnpj": [CPFL],
                "referencia": [D("2025-01-01")],
                "versao": [1],
                "tipo": ["desdobramento"],
                "data": [D("2021-04-30")],
                "fator": [2.0],
                "acoes_novas": [1e9],
                "valor": [None],
            }
        ),
    )


def test_ficha_traz_qualidade_do_lucro_e_capital(tmp_path: Path) -> None:
    _mini_base(tmp_path / "base")
    _lucro_e_capital(tmp_path / "base")
    resumo = _montar(tmp_path / "base", tmp_path / "dossies")
    assert resumo.falhas == []
    secoes = {s["chave"]: s for s in _ficha_da_cpfl(tmp_path / "dossies")["secoes"]}
    lucro = {i["chave"]: i["valor"] for i in secoes["qualidade_do_lucro"]["itens"]}
    assert lucro["exercicios_reapresentados"] == 1
    assert lucro["releases_diferentes"] == 1
    capital = {i["chave"]: i["valor"] for i in secoes["capital_e_acionistas"]["itens"]}
    assert (
        capital["insiders_compras_12m"] == 2e6
    )  # a declaração entregue depois de hoje fica fora
    assert capital["eventos_de_capital"] == 1


def _governanca_e_credito(pasta: Path) -> None:
    """O FRE da CPFL (conselho, comitês, remuneração), os ratings e as assembleias de debenturistas."""
    _gravar(pasta, "fre_conselho/2026.parquet", governanca_e_credito._conselho())
    _gravar(pasta, "fre_comites/2026.parquet", governanca_e_credito._comites())
    _gravar(pasta, "fre_remuneracao/2026.parquet", governanca_e_credito._remuneracao())
    _gravar(pasta, "ratings/ratings.parquet", governanca_e_credito._ratings())
    _gravar(
        pasta,
        "debentures_assembleias/assembleias.parquet",
        governanca_e_credito._assembleias(),
    )
    # os proventos não têm data de publicação: a noite a tira da entrega do FRE (fre_remuneracao);
    # o exercício de 2026 vem de um FRE que a base não conhece e fica fora
    _gravar(
        pasta,
        "proventos/2026.parquet",
        pd.DataFrame(
            {
                "cnpj": [CPFL] * 2,
                "referencia": [D("2026-01-01"), D("2027-01-01")],
                "versao": [2, 1],
                "exercicio": [D("2025-12-31"), D("2026-12-31")],
                "lucro_ajustado": [100e6, 10e6],
                "dividendo_total": [130e6, 90e6],
                "payout": [1.3, 9.0],
            }
        ),
    )


def test_ficha_traz_governanca_e_credito(tmp_path: Path) -> None:
    _mini_base(tmp_path / "base")
    _governanca_e_credito(tmp_path / "base")
    resumo = _montar(tmp_path / "base", tmp_path / "dossies")
    assert resumo.falhas == []
    secoes = {s["chave"]: s for s in _ficha_da_cpfl(tmp_path / "dossies")["secoes"]}
    governanca = {i["chave"]: i["valor"] for i in secoes["governanca"]["itens"]}
    assert (
        governanca["conselho_membros"] == 10
    )  # o FRE de 2027, entregue depois de hoje, fica fora
    assert governanca["remuneracao_da_administracao"] == 51e6
    assert "mulheres_no_conselho" not in governanca  # sem fre_diversidade na base
    credito = {i["chave"]: i["valor"] for i in secoes["credito"]["itens"]}
    assert credito["ratings_rebaixamentos_12m"] == 1
    assert credito["assembleias_de_debenturistas_12m"] == 2
    # o rótulo de aperto da base vira a tabela `assembleias_de_aperto`, só com os fatos (sem a coluna)
    assert len(secoes["credito"]["tabelas"]["assembleias_de_aperto"]) == 3
    assert "estresse" not in json.dumps(secoes["credito"])
    assert "acoes_de_rating" in secoes["credito"]["tabelas"]
    assert "remuneracao_da_diretoria_por_exercicio" in secoes["governanca"]["tabelas"]
    proventos = secoes["capital_e_acionistas"]["tabelas"]["proventos_por_exercicio"]
    assert [(p["exercicio"], p["conhecido_em"]) for p in proventos] == [
        (2025, "2026-07-10")
    ]


def test_ficha_traz_a_geracao_de_caixa_da_dfc(tmp_path: Path) -> None:
    """A noite lê a DRE, a DFC e a DVA da DFP e grava EBITDA, capex e FCF, sem a DFP de depois de hoje."""
    _mini_base(tmp_path / "base")
    _gravar(
        tmp_path / "base",
        "demonstracoes/2025.parquet",
        geracao_de_caixa._como_era().assign(cnpj=CPFL),
    )
    resumo = _montar(tmp_path / "base", tmp_path / "dossies")
    assert resumo.falhas == []
    secoes = {s["chave"]: s for s in _ficha_da_cpfl(tmp_path / "dossies")["secoes"]}
    caixa = {i["chave"]: i["valor"] for i in secoes["geracao_de_caixa"]["itens"]}
    assert caixa == {"ebitda": 2_500e6, "capex": 900e6, "fcf": 1_300e6}
    exercicios = secoes["geracao_de_caixa"]["tabelas"]["caixa_por_exercicio"]
    assert [linha["exercicio"] for linha in exercicios] == [2025, 2024]


def test_controladoras_saem_da_rede_como_era_hoje(tmp_path: Path) -> None:
    """A situação de hoje vem do `como_era_em` da porta: a ligação que só fica pública depois não entra."""
    pasta = tmp_path / "base"
    _gravar(pasta, "rede/entidades.parquet", _entidades("EA", "EDONA", "ENOVA"))
    _gravar(
        pasta,
        "rede/identificadores.parquet",
        _identificadores(
            ("EA", "cnpj", CPFL_DIGITOS, "2010-01-01", None, "2010-01-01"),
            ("EDONA", "cnpj", "33333333000133", "2010-01-01", None, "2010-01-01"),
            ("ENOVA", "cnpj", "44444444000144", "2010-01-01", None, "2010-01-01"),
        ),
    )
    _gravar(
        pasta,
        "rede/ligacoes.parquet",
        _ligacoes(
            {
                "de": "EA",
                "para": "EDONA",
                "tipo": "controlada_de",
                "publico_em": "2020-05-31",
            },
            {
                "de": "EA",
                "para": "ENOVA",
                "tipo": "controlada_de",
                "publico_em": "2026-12-01",
            },
        ),
    )
    with Porta(pasta) as porta:
        controladoras = gerar_dossies._controladoras(
            gerar_dossies.Leitor(porta),
            D("2026-10-17 07:00"),
            _entidades("EA", "EDONA", "ENOVA"),
        )
    assert controladoras["cnpj_controladora"].tolist() == ["33333333000133"]


def test_serie_da_anatel_nao_soma_o_recorte_por_tecnologia(tmp_path: Path) -> None:
    """A Anatel repete a móvel por modalidade e por tecnologia: só uma das duas entra na soma."""
    _gravar(
        tmp_path / "base",
        "setoriais/anatel/Acessos_Telefonia_Movel_2025.parquet",
        pd.DataFrame(
            {
                "competencia": [D("2025-12-31")] * 3,
                "servico": ["telefonia_movel"] * 3,
                "recorte": ["modalidade", "modalidade", "tecnologia"],
                "cnpj": ["02.558.157/0001-62"] * 3,
                "acessos": [10.0, 5.0, 15.0],
            }
        ),
    )
    serie = next(
        s for s in dossie.SERIES_DAS_AGENCIAS if s.nome == "anatel_telefonia_movel"
    )
    with Porta(tmp_path / "base") as porta:
        anual = gerar_dossies.ler_serie(gerar_dossies.Leitor(porta), serie)
    assert anual[["ano", "chave", "valor"]].to_dict("records") == [
        {"ano": 2025, "chave": "02558157000162", "valor": 15.0}
    ]


def _linhas_da_agencia(tabela: dict[str, list], valor: str) -> pd.DataFrame:
    """Dois meses de uma agência: dezembro de 2024 (público em 2025-03) e dezembro de 2025 (público só
    em 2026-03, depois do dia da ficha)."""
    linhas = len(tabela["competencia"])
    return pd.DataFrame(
        {
            **tabela,
            valor: [10.0, 99.0][:linhas],
            "disponivel_em": [D("2025-03-31"), D("2026-03-31")][:linhas],
        }
    )


@pytest.mark.parametrize(
    ("nome", "pasta", "colunas", "valor"),
    [
        (
            "anatel_telefonia_movel",
            "anatel/Acessos_Telefonia_Movel_2025",
            {
                "servico": ["telefonia_movel"] * 2,
                "recorte": ["modalidade"] * 2,
                "cnpj": ["02.558.157/0001-62"] * 2,
            },
            "acessos",
        ),
        (
            "ans_beneficiarios",
            "ans/beneficiarios_2025",
            {"cd_operadora": ["123456"] * 2},
            "beneficiarios",
        ),
        (
            "susep_premio_ganho",
            "susep/seguros_2025",
            {"coenti": ["1111"] * 2},
            "premio_ganho",
        ),
    ],
)
def test_serie_da_agencia_e_lida_como_era_no_dia(
    tmp_path: Path, nome: str, pasta: str, colunas: dict[str, list], valor: str
) -> None:
    """Cortar o futuro não muda o passado: o mês que a agência só publica depois do dia da ficha não
    entra na série (ANS, Anatel e SUSEP gravam `disponivel_em`)."""
    tabela = {"competencia": [D("2024-12-31"), D("2025-12-31")], **colunas}
    _gravar(
        tmp_path / "base",
        f"setoriais/{pasta}.parquet",
        _linhas_da_agencia(tabela, valor),
    )
    serie = next(s for s in dossie.SERIES_DAS_AGENCIAS if s.nome == nome)
    with Porta(tmp_path / "base") as porta:
        anual = gerar_dossies.ler_serie(
            gerar_dossies.Leitor(porta), serie, D("2025-06-30")
        )
    assert anual["ano"].tolist() == [2024]


def test_le_a_base_so_pela_porta() -> None:
    """O gerador só lê (não grava a base): não tem a exceção dos montadores do `test_porta_unica`."""
    from tests.test_porta_unica import _montador

    assert not _montador("scripts/gerar_dossies.py")


def _rede_da_cpfl(pasta: Path, com_o_futuro: bool) -> None:
    """A CPFL (EA) com uma controlada pública desde 2015; `com_o_futuro`: mais uma, pública só em
    dezembro de 2026, e um FRE entregue em 2027 (depois do dia da ficha)."""
    controladas = ["EC"] + (["ENOVA"] if com_o_futuro else [])
    _gravar(pasta, "rede/entidades.parquet", _entidades("EA", *controladas))
    _gravar(
        pasta,
        "rede/identificadores.parquet",
        _identificadores(
            ("EA", "cnpj_raiz", CPFL_DIGITOS[:8], None, None, "2010-01-01"),
            ("EA", "cnpj", CPFL_DIGITOS, None, None, "2010-01-01"),
            ("EC", "cnpj", DISTRIBUIDORA, None, None, "2010-01-01"),
            ("ENOVA", "cnpj", "44444444000144", None, None, "2026-12-01"),
        ),
    )
    ligacoes = [
        {"de": "EC", "para": "EA", "tipo": "controlada_de", "publico_em": "2016-05-31"}
    ]
    if com_o_futuro:
        ligacoes.append(
            {
                "de": "ENOVA",
                "para": "EA",
                "tipo": "controlada_de",
                "publico_em": "2026-12-01",
            }
        )
    _gravar(pasta, "rede/ligacoes.parquet", _ligacoes(*ligacoes))
    fres = [("2025-12-31", D("2026-05-31"), DISTRIBUIDORA)]
    if com_o_futuro:
        fres.append(("2026-09-30", D("2027-01-15"), "44444444000144"))
    _gravar(
        pasta,
        "controladas/2025.parquet",
        pd.DataFrame(
            {
                "cnpj_companhia": [CPFL_DIGITOS] * len(fres),
                "referencia": [D(r) for r, _, _ in fres],
                "versao": [1] * len(fres),
                "conhecido_em": [c for _, c, _ in fres],
                "cnpj": [s for _, _, s in fres],
                "razao_social": ["CPFL Paulista", "Nova"][: len(fres)],
                "tipo": ["Controlada"] * len(fres),
                "participacao": [100.0] * len(fres),
            }
        ),
    )


def _ficha_da_cpfl(saida: Path) -> dict:
    return json.loads(
        (saida / "2026-10-17" / f"{CPFL_DIGITOS}.json").read_text(encoding="utf-8")
    )


def test_ficha_traz_a_secao_da_rede_por_ultimo(tmp_path: Path) -> None:
    _mini_base(tmp_path / "base")
    _rede_da_cpfl(tmp_path / "base", com_o_futuro=False)
    resumo = _montar(tmp_path / "base", tmp_path / "dossies")
    assert resumo.falhas == []
    secoes = _ficha_da_cpfl(tmp_path / "dossies")["secoes"]
    assert secoes[-1]["chave"] == "rede"
    linhas = secoes[-1]["tabelas"]["ligacoes_da_rede"]
    assert [(linha["relacao"], linha["cnpj"]) for linha in linhas] == [
        ("Controlada", "33.050.196/0001-88")
    ]


def test_rede_cortar_o_futuro_nao_muda_o_passado(tmp_path: Path) -> None:
    """A ficha de um dia é a mesma com ou sem o que só ficou público depois dele."""
    fichas = []
    for com_o_futuro in (False, True):
        pasta = tmp_path / f"base-{com_o_futuro}"
        _mini_base(pasta)
        _rede_da_cpfl(pasta, com_o_futuro)
        _montar(pasta, tmp_path / f"dossies-{com_o_futuro}")
        ficha = _ficha_da_cpfl(tmp_path / f"dossies-{com_o_futuro}")
        fichas.append([s for s in ficha["secoes"] if s["chave"] == "rede"])
    assert fichas[0] == fichas[1]
    assert fichas[0]  # a seção existe nas duas


# --- setor (molde D, plano de 19/10/2026, PR 1, tarefa 1.5) -----------------------------------------


def _manifesto(saida: Path) -> dict:
    return json.loads(
        (saida / "2026-10-17" / "manifesto.json").read_text(encoding="utf-8")
    )


def test_ficha_do_membro_traz_a_secao_setor(tmp_path: Path) -> None:
    _mini_base(tmp_path / "base")
    resumo = _montar(tmp_path / "base", tmp_path / "dossies")
    assert resumo.falhas == []
    setor = next(
        s
        for s in _ficha_da_cpfl(tmp_path / "dossies")["secoes"]
        if s["chave"] == "setor"
    )
    (linha,) = setor["tabelas"]["concentracao_aneel_consumidores"]
    # dezembro de 2025: a distribuidora da CPFL com 110 e uma fora da base com 890
    assert linha["hhi"] == pytest.approx(11**2 + 89**2)
    assert linha["delta_hhi"] is None  # um ano só: nada a comparar
    assert [m["cnpj"] for m in setor["tabelas"]["membros"]] == [CPFL_DIGITOS]


def test_manifesto_lista_os_setores(tmp_path: Path) -> None:
    _mini_base(tmp_path / "base")
    _montar(tmp_path / "base", tmp_path / "dossies")
    assert _manifesto(tmp_path / "dossies")["setores"] == {
        "eletricas": {"ficha": CPFL_DIGITOS, "membros": [CPFL_DIGITOS]}
    }


def test_setor_da_ficha_que_nao_foi_gravada_nao_vai_no_manifesto(
    tmp_path: Path,
) -> None:
    _mini_base(tmp_path / "base")
    _gravar(  # a ficha da CPFL cai no filtro de pessoas (como em test_ficha_com_pessoa_nao_e_gravada)
        tmp_path / "base",
        "controladas/2025.parquet",
        pd.DataFrame(
            {
                "cnpj_companhia": [CPFL_DIGITOS],
                "referencia": [D("2025-01-01")],
                "versao": [1],
                "cnpj": [""],
                "razao_social": ["Fulano de Tal"],
                "tipo": ["controlada"],
                "participacao": [100.0],
            }
        ),
    )
    _montar(tmp_path / "base", tmp_path / "dossies")
    assert _manifesto(tmp_path / "dossies")["setores"] == {}


def test_setor_que_quebra_nao_derruba_a_noite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mini_base(tmp_path / "base")

    def quebra(*_: object) -> None:
        raise ValueError("coluna sumiu")

    monkeypatch.setattr(gerar_dossies.dossie, "secao_setor", quebra)
    resumo = _montar(tmp_path / "base", tmp_path / "dossies")
    assert resumo.fichas == 1
    assert resumo.falhas == ["setor eletricas: ValueError: coluna sumiu"]
    chaves = [s["chave"] for s in _ficha_da_cpfl(tmp_path / "dossies")["secoes"]]
    assert "setor" not in chaves


def test_membro_de_dois_setores_leva_so_um() -> None:
    """Cada setor vai na ficha de um membro só; quem já leva um setor passa o outro adiante."""
    seguros = {"chave": "setor", "titulo": "seguros"}
    saude = {"chave": "setor", "titulo": "saúde"}
    fichas, falhas = gerar_dossies.distribuir_setores(
        [("seguros", ["A", "B"], seguros), ("saude_suplementar", ["A"], saude)]
    )
    assert fichas == {"A": ("seguros", seguros)}
    assert falhas == ["setor saude_suplementar: todos os membros já levam outro setor"]
    fichas, _ = gerar_dossies.distribuir_setores(
        [("saude_suplementar", ["A"], saude), ("seguros", ["A", "B"], seguros)]
    )
    assert fichas == {"A": ("saude_suplementar", saude), "B": ("seguros", seguros)}


def test_grupos_da_anatel_saem_do_ultimo_mes_do_ano(tmp_path: Path) -> None:
    _gravar(
        tmp_path / "base",
        "setoriais/anatel/Acessos_Telefonia_Movel_2025.parquet",
        pd.DataFrame(
            {
                "competencia": [D("2025-11-30"), D("2025-12-31"), D("2025-12-31")],
                "servico": ["telefonia_movel"] * 3,
                "recorte": ["modalidade"] * 3,
                "cnpj": ["02.558.157/0001-62", "02558157000162", "33.000.118/0001-79"],
                "grupo_economico": ["Antigo", "Telefônica", ""],
                "acessos": [10.0, 5.0, 3.0],
            }
        ),
    )
    serie = next(
        s for s in dossie.SERIES_DAS_AGENCIAS if s.nome == "anatel_telefonia_movel"
    )
    with Porta(tmp_path / "base") as porta:
        grupos = gerar_dossies.ler_grupos(gerar_dossies.Leitor(porta), serie)
    assert grupos.to_dict("records") == [
        {"ano": 2025, "chave": "02558157000162", "grupo": "Telefônica"}
    ]


def test_serie_sem_coluna_de_grupo_nao_tem_grupos(tmp_path: Path) -> None:
    _gravar(
        tmp_path / "base",
        "setoriais/anatel/Acessos_Telefonia_Movel_2025.parquet",
        pd.DataFrame(
            {
                "competencia": [D("2025-12-31")],
                "servico": ["telefonia_movel"],
                "recorte": ["modalidade"],
                "cnpj": ["02558157000162"],
                "acessos": [5.0],
            }
        ),
    )
    serie = next(
        s for s in dossie.SERIES_DAS_AGENCIAS if s.nome == "anatel_telefonia_movel"
    )
    with Porta(tmp_path / "base") as porta:
        assert gerar_dossies.ler_grupos(gerar_dossies.Leitor(porta), serie).empty


def test_setor_cortar_o_futuro_nao_muda_o_passado_na_noite(tmp_path: Path) -> None:
    """Um mês de 2026 na ANEEL não muda a linha de 2025 da concentração."""
    linhas = []
    for com_o_futuro in (False, True):
        pasta = tmp_path / f"base-{com_o_futuro}"
        _mini_base(pasta)
        if com_o_futuro:
            _gravar(
                pasta,
                "setoriais/aneel/2026.parquet",
                pd.DataFrame(
                    {
                        "competencia": [D("2026-01-31")] * 2,
                        "cnpj": [DISTRIBUIDORA, "99999999000199"],
                        "valor": [500.0, 500.0],
                        "detalhe_do_mercado": ["Número de consumidores"] * 2,
                        "tipo_de_mercado": ["Regular"] * 2,
                    }
                ),
            )
        _montar(pasta, tmp_path / f"dossies-{com_o_futuro}")
        ficha = _ficha_da_cpfl(tmp_path / f"dossies-{com_o_futuro}")
        setor = next(s for s in ficha["secoes"] if s["chave"] == "setor")
        tabela = setor["tabelas"]["concentracao_aneel_consumidores"]
        linhas.append([linha for linha in tabela if linha["ano"] == 2025])
    assert linhas[0] == linhas[1]
    assert linhas[0]


def _insolvencia_da_cpfl(pasta: Path) -> None:
    """Um pedido de falência na CVM (entregue em duas versões) e uma situação especial na Receita
    (repetida na matriz e na filial, em dois meses), mais um fato que ainda não é público."""
    _gravar(
        pasta,
        "insolvencia/insolvencia.parquet",
        pd.DataFrame(
            {
                "cnpj": [CPFL, CPFL, CPFL],
                "rotulo": ["pedido_de_falencia", "pedido_de_falencia", "falencia"],
                "evento": ["x", "x", "y"],
                "assunto": ["a", "a", "b"],
                "origem_coletada_em": [D("2026-10-01")] * 3,
                "protocolo": ["P1", "P1", "P2"],
                "versao": [1, 2, 1],
                "referencia": [D("2026-03-10")] * 2 + [D("2026-12-01")],
                "conhecido_em": [D("2026-03-12"), D("2026-04-01"), D("2026-12-02")],
                "link": ["l1", "l2", "l3"],
            }
        ),
    )
    _gravar(
        pasta,
        "cnpj_situacao_especial/2026-09.parquet",
        pd.DataFrame(
            {
                "cnpj": [CPFL_DIGITOS, "02429144000274"],
                "cnpj_basico": ["02429144"] * 2,
                "matriz": [True, False],
                "situacao_especial": ["RECUPERACAO JUDICIAL"] * 2,
                "rotulo": ["recuperacao_judicial"] * 2,
                "data_situacao_especial": [D("2026-08-20")] * 2,
                "mes_do_retrato": [D("2026-09-01")] * 2,
                "origem_coletada_em": [D("2026-10-01")] * 2,
                "disponivel_em": [D("2026-09-15")] * 2,
            }
        ),
    )


def test_ficha_traz_a_d2_so_com_fatos_ja_publicos(tmp_path: Path) -> None:
    _mini_base(tmp_path / "base")
    _insolvencia_da_cpfl(tmp_path / "base")
    resumo = _montar(tmp_path / "base", tmp_path / "dossies")
    assert resumo.falhas == []
    secoes = {s["chave"]: s for s in _ficha_da_cpfl(tmp_path / "dossies")["secoes"]}
    linhas = secoes["insolvencia"]["tabelas"]["registros_de_insolvencia"]
    assert (
        [(l["registro"], l["publico_em"]) for l in linhas]
        == [
            ("Recuperação judicial", "2026-09-15"),
            ("Pedido de falência", "2026-03-12"),
        ]
    )  # a falência entregue depois de hoje fica fora; versão e filial não repetem o fato
    assert all(l["situacao"] is None for l in linhas)
    assert "não prova que não exista" in json.dumps(
        secoes["insolvencia"], ensure_ascii=False
    )


def test_ficha_sem_as_tabelas_diz_que_nao_consultou(tmp_path: Path) -> None:
    _mini_base(tmp_path / "base")
    _montar(tmp_path / "base", tmp_path / "dossies")
    secoes = {s["chave"]: s for s in _ficha_da_cpfl(tmp_path / "dossies")["secoes"]}
    assert (
        "insolvencia" not in secoes
    )  # nenhuma das duas fontes lida: sem seção, sem promessa
