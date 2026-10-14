"""O arquivo de dados das ferramentas do site (scripts/exportar_dados_das_ferramentas.py), sem internet.

Só dados do Banco Central (licença ODbL, citando a fonte): nada do Yahoo nem de corretora entra.
"""

import json
from datetime import date, datetime

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
        {"data": "13/10/2026", "dataFim": "13/11/2026", "valor": "0.6704"},
        {"data": "15/10/2026", "dataFim": "15/11/2026", "valor": "0.6800"},  # futuro
    ],
    "sgs.433/": [
        {"data": "01/07/1994", "valor": "6.84"},
        {"data": "01/08/1994", "valor": "1.86"},
        {"data": "01/09/2026", "valor": "0.82"},
    ],
}


def _buscar_do_bc(falhar: tuple[str, ...] = ()):
    def buscar(url, params=None, timeout=None):
        if any(trecho in url for trecho in falhar):
            raise requests.HTTPError("400", response=None)
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
         "venda": 6.1, "data": "2026-10-13"},
        {"codigo": "USD", "nome": "Dólar dos Estados Unidos",
         "compra": pytest.approx(5.449), "venda": 5.45, "data": "2026-10-13"},
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


def test_so_entram_as_partes_conhecidas_e_so_do_banco_central():
    dados, _ = exp.coletar(HOJE, _buscar_do_bc())
    arquivo = exp.montar(dados, {}, AGORA)
    assert set(arquivo) == {"gerado_em", "fonte", *exp.PARTES}
    assert exp.FONTE.startswith("Banco Central do Brasil")


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
