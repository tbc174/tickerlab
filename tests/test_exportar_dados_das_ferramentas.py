"""O arquivo de dados das ferramentas do site (scripts/exportar_dados_das_ferramentas.py), sem internet.

Só dados abertos do Banco Central e do Tesouro Nacional (licença ODbL, citando a fonte): nada do
Yahoo, da B3 nem de corretora entra.
"""

import json
from datetime import date, datetime
from urllib.parse import unquote

import pytest
import requests

from scripts import exportar_dados_das_ferramentas as exp
from src.bcb import FUSO

HOJE = date(2026, 10, 14)
AGORA = datetime(2026, 10, 14, 13, 40, tzinfo=FUSO)


class Resposta:
    def __init__(self, conteudo: object) -> None:
        self.conteudo = conteudo
        self.status_code = 200

    def raise_for_status(self) -> None:
        pass

    def json(self) -> object:
        return self.conteudo


def _ptax(venda: float) -> dict:
    return {
        "value": [
            {"cotacaoCompra": venda - 0.001, "cotacaoVenda": venda,
             "dataHoraCotacao": "2026-10-13 13:04:00.0", "tipoBoletim": "Fechamento"},
        ]
    }  # fmt: skip


RESPOSTAS = {
    "Moedas": {
        "value": [
            {"simbolo": "EUR", "nomeFormatado": "Euro", "tipoMoeda": "B"},
            {
                "simbolo": "USD",
                "nomeFormatado": "Dólar dos Estados Unidos",
                "tipoMoeda": "A",
            },
        ]
    },
    "sgs.12/": [{"data": "13/10/2026", "valor": "0.050788"}],
    "sgs.432/": [
        {"data": "13/10/2026", "valor": "13.75"},
        {"data": "04/11/2026", "valor": "13.75"},  # depois de hoje: não entra
    ],
    "sgs.195/": [
        {"data": "01/09/2026", "dataFim": "01/10/2026", "valor": "0.6500"},
        {
            "data": "01/10/2026",
            "dataFim": "01/11/2026",
            "valor": "0.6600",
        },  # mês corrente
        {"data": "13/10/2026", "dataFim": "13/11/2026", "valor": "0.6704"},
        {"data": "15/10/2026", "dataFim": "15/11/2026", "valor": "0.6800"},  # futuro
    ],
    "sgs.25/": [
        {"data": "01/05/2012", "dataFim": "01/06/2012", "valor": "0.5500"},
        {
            "data": "02/05/2012",
            "dataFim": "02/06/2012",
            "valor": "0.5400",
        },  # não é dia 1
        {
            "data": "01/06/2012",
            "dataFim": "01/07/2012",
            "valor": "0.5300",
        },  # já é regra nova
    ],
    "sgs.4391/": [
        {"data": "01/08/2026", "valor": "1.09"},
        {"data": "01/09/2026", "valor": "1.08"},
        {"data": "01/10/2026", "valor": "0.41"},  # o mês ainda não acabou
    ],
    "sgs.433/": [
        {"data": "01/07/1994", "valor": "6.84"},
        {"data": "01/08/1994", "valor": "1.86"},
        {"data": "01/09/2026", "valor": "0.82"},
    ],
}


def _focus(indicador: str) -> dict:
    base = {"IPCA": 4.5, "Selic": 13.0}[indicador]
    linhas = [
        {"Indicador": indicador, "Data": "2026-10-03", "DataReferencia": "2026",
         "Mediana": base + 1, "Media": 0, "Minimo": 0, "Maximo": 0, "numeroRespondentes": 1},
    ] + [
        {"Indicador": indicador, "Data": "2026-10-10", "DataReferencia": str(ano),
         "Mediana": base - (ano - 2026) * 0.25, "Media": 0, "Minimo": 0, "Maximo": 0,
         "numeroRespondentes": 1}
        for ano in range(2025, 2031)
    ]  # fmt: skip
    return {"value": linhas}


TESOURO = (
    "Tipo Titulo;Data Vencimento;Data Base;Taxa Compra Manha;Taxa Venda Manha;"
    "PU Compra Manha;PU Venda Manha;PU Base Manha\n"
    "Tesouro Prefixado;01/01/2032;13/10/2026;12,51;12,63;512,01;508,96;508,96\n"
    "Tesouro IPCA+;15/05/2035;13/10/2026;6,69;6,81;1980,33;1965,12;1965,12\n"
).encode("latin-1")


class RespostaDoTesouro:
    status_code = 206
    content = TESOURO


def _buscar_do_bc(falhar: tuple[str, ...] = ()):
    def buscar(url, params=None, timeout=None, headers=None):
        if any(trecho in url for trecho in falhar):
            raise requests.HTTPError("400", response=None)
        if "tesourotransparente" in url:
            return RespostaDoTesouro()
        if "ExpectativasMercadoAnuais" in url:
            return Resposta(_focus("IPCA" if "'IPCA'" in unquote(url) else "Selic"))
        if "CotacaoMoedaPeriodo" in url:
            return Resposta(_ptax({"'EUR'": 6.1, "'USD'": 5.45}[params["@moeda"]]))
        for trecho, conteudo in RESPOSTAS.items():
            if trecho in url:
                return Resposta(conteudo)
        raise AssertionError(f"pedido inesperado: {url}")

    return buscar


def test_monta_o_arquivo_com_tudo_do_banco_central():
    dados, falhas = exp.coletar(HOJE, _buscar_do_bc())
    assert falhas == []
    arquivo = exp.montar(dados, {}, AGORA)
    assert arquivo["gerado_em"] == "2026-10-14T13:40:00-03:00"
    assert "Banco Central" in arquivo["fonte"]
    assert arquivo["moedas"] == [
        {"codigo": "EUR", "nome": "Euro", "compra": pytest.approx(6.099),
         "venda": 6.1, "data": "2026-10-13", "historico": [["2026-10-13", 6.1]]},
        {"codigo": "USD", "nome": "Dólar dos Estados Unidos",
         "compra": pytest.approx(5.449), "venda": 5.45, "data": "2026-10-13",
         "historico": [["2026-10-13", 5.45]]},
    ]  # fmt: skip
    assert arquivo["cdi"] == {
        "ao_ano": pytest.approx(1.00050788**252 - 1),
        "data": "2026-10-13",
    }
    assert arquivo["selic_meta"] == {
        "ao_ano": pytest.approx(0.1375),
        "data": "2026-10-13",
    }
    assert arquivo["poupanca"] == {
        "ao_mes": pytest.approx(0.006704),
        "data": "2026-10-13",
    }
    assert arquivo["ipca"]["meses"][:2] == [
        ["1994-07", pytest.approx(0.0684)],
        ["1994-08", pytest.approx(0.0186)],
    ]
    assert arquivo["ipca"]["ultimo"] == "2026-09"


def test_dados_novos_das_ferramentas_v2():
    dados, falhas = exp.coletar(HOJE, _buscar_do_bc())
    assert falhas == []
    arquivo = exp.montar(dados, {}, AGORA)
    # Focus: a pesquisa mais nova, do ano corrente aos 3 seguintes, em fração
    assert arquivo["focus"]["ipca"] == {
        "data": "2026-10-10",
        "anos": {"2026": pytest.approx(0.045), "2027": pytest.approx(0.0425),
                 "2028": pytest.approx(0.04), "2029": pytest.approx(0.0375)},
    }  # fmt: skip
    assert arquivo["focus"]["selic"]["anos"]["2026"] == pytest.approx(0.13)
    # CDI mês a mês, sem o mês que ainda não acabou
    assert arquivo["cdi_mensal"] == {
        "meses": [
            ["2026-08", pytest.approx(0.0109)],
            ["2026-09", pytest.approx(0.0108)],
        ],
        "ultimo": "2026-09",
    }
    # poupança: o aniversário do dia 1; regra antiga (25) até mai/2012, nova (195) depois
    assert arquivo["poupanca_mensal"] == {
        "meses": [
            ["2012-05", pytest.approx(0.0055)],
            ["2026-09", pytest.approx(0.0065)],
        ],
        "ultimo": "2026-09",
    }
    assert arquivo["tesouro"]["data"] == "2026-10-13"
    assert [t["titulo"] for t in arquivo["tesouro"]["titulos"]] == [
        "Tesouro IPCA+",
        "Tesouro Prefixado",
    ]


def test_so_entram_as_partes_conhecidas_e_so_de_fontes_abertas():
    dados, _ = exp.coletar(HOJE, _buscar_do_bc())
    arquivo = exp.montar(dados, {}, AGORA)
    assert set(arquivo) == {"gerado_em", "fonte", *exp.PARTES}
    assert exp.FONTE.startswith("Banco Central do Brasil")
    assert "Tesouro Nacional" in exp.FONTE
    assert "ODbL" in exp.FONTE
    for proibida in ("Yahoo", "B3", "corretora"):
        assert proibida not in exp.FONTE


def test_tesouro_fora_do_ar_entra_nas_falhas_e_o_resto_segue():
    dados, falhas = exp.coletar(HOJE, _buscar_do_bc(falhar=("tesourotransparente",)))
    assert [f.split(" ")[0] for f in falhas] == ["tesouro"]
    assert "cdi" in dados


def test_parte_que_falha_fica_com_a_anterior_e_entra_nas_falhas():
    anterior = {"cdi": {"ao_ano": 0.13, "data": "2026-10-10"}}
    dados, falhas = exp.coletar(HOJE, _buscar_do_bc(falhar=("sgs.12/",)))
    assert [f.split(" ")[0] for f in falhas] == ["cdi"]
    arquivo = exp.montar(dados, anterior, AGORA)
    assert arquivo["cdi"] == {
        "ao_ano": 0.13,
        "data": "2026-10-10",
    }  # a data diz que é velho
    assert arquivo["selic_meta"]["data"] == "2026-10-13"


def test_parte_que_falha_sem_anterior_fica_fora():
    dados, _ = exp.coletar(HOJE, _buscar_do_bc(falhar=("Moedas",)))
    assert "moedas" not in exp.montar(dados, {}, AGORA)


def test_grava_sem_deixar_arquivo_pela_metade(tmp_path):
    destino = tmp_path / "dados" / "ferramentas.json"
    exp.gravar(destino, {"a": 1})
    assert json.loads(destino.read_text(encoding="utf-8")) == {"a": 1}
    assert list(destino.parent.iterdir()) == [destino]  # o temporário sumiu


def test_main_le_o_anterior_e_avisa_as_falhas(tmp_path, monkeypatch, capsys):
    destino = tmp_path / "ferramentas.json"
    destino.write_text(
        json.dumps({"poupanca": {"ao_mes": 0.006, "data": "2026-10-01"}})
    )
    monkeypatch.setattr(exp, "_agora", lambda: AGORA)
    codigo = exp.main(["--destino", str(destino)], _buscar_do_bc(falhar=("sgs.195/",)))
    assert codigo == 1
    assert (
        capsys.readouterr().out.strip().splitlines()[-1].startswith("FALHAS: poupanca")
    )
    gravado = json.loads(destino.read_text(encoding="utf-8"))
    assert gravado["poupanca"] == {"ao_mes": 0.006, "data": "2026-10-01"}
    assert gravado["cdi"]["data"] == "2026-10-13"


def test_main_sem_falhas_sai_com_zero(tmp_path, monkeypatch):
    monkeypatch.setattr(exp, "_agora", lambda: AGORA)
    destino = tmp_path / "ferramentas.json"
    assert exp.main(["--destino", str(destino)], _buscar_do_bc()) == 0
    assert destino.exists()
