"""A coleta das comunicações do DJEN por companhia (`base/arquivo/djen.py`). Tudo aqui é inventado:
as partes, os advogados e os processos não existem (os números só têm o dígito verificador certo)."""

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from base.arquivo import djen
from base.arquivo.coleta import ErroDeDescoberta, Resposta

AGORA = datetime(2026, 11, 3, 6, tzinfo=UTC)  # uma terça-feira
EMPRESA = "ENERGIA EXEMPLO S.A."
ESTADUAL = "0000001-15.2024.8.26.0100"
DO_TRABALHO = "0000002-75.2024.5.02.0001"


def _item(numero: str, sigla: str, advogados: int = 2) -> dict:
    return {
        "id": hash(numero) % 10_000,
        "hash": f"h-{numero}",
        "numero_processo": numero.replace("-", "").replace(".", ""),
        "siglaTribunal": sigla,
        "destinatarios": [{"nome": EMPRESA, "polo": "P"}],
        "destinatarioadvogados": [
            {"advogado": {"nome": f"ADVOGADO INVENTADO {n}", "numero_oab": "1"}}
            for n in range(advogados)
        ],
        "texto": "Intimação de teste.",
    }


def _corpo(itens: list[dict], total: int | None = None) -> bytes:
    conteudo = {
        "status": "success",
        "message": "",
        "count": total or len(itens),
        "items": itens,
    }
    return json.dumps(conteudo).encode()


class Djen:
    """A API em memória: endereço -> corpo."""

    def __init__(self, respostas: dict[str, bytes]):
        self.respostas = respostas
        self.lidos: list[str] = []

    def ler(self, url, *, metodo="GET", cabecalhos=None, corpo=None):
        self.lidos.append(url)
        return Resposta(url, self.respostas[url], {"Content-Type": "application/json"})

    def cabecalhos(self, url):
        return {}

    def baixar(self, url, destino: Path):
        raise AssertionError("o DJEN é lido pela consulta, nunca baixado inteiro")


def test_a_consulta_volta_para_o_nome_e_o_periodo():
    endereco = djen.consulta("A & B S/A", date(2026, 10, 26), date(2026, 11, 1))
    assert endereco.startswith(djen.API + "?")
    assert djen.da_consulta(endereco) == (
        "A & B S/A",
        date(2026, 10, 26),
        date(2026, 11, 1),
    )


@pytest.mark.parametrize(
    ("hoje", "semana"),
    [
        (date(2026, 11, 3), (date(2026, 10, 26), date(2026, 11, 1))),  # terça
        (date(2026, 11, 2), (date(2026, 10, 26), date(2026, 11, 1))),  # segunda
        (
            date(2026, 11, 1),
            (date(2026, 10, 19), date(2026, 10, 25)),
        ),  # domingo ainda não fechou
    ],
)
def test_ultima_semana_fechada(hoje: date, semana: tuple[date, date]):
    assert djen.ultima_semana_fechada(hoje) == semana


def test_meses_fechados_do_mais_novo_ao_mais_antigo():
    meses = djen.meses_fechados(date(2026, 3, 15), desde=date(2025, 12, 10))
    assert meses == [
        (date(2026, 2, 1), date(2026, 2, 28)),
        (date(2026, 1, 1), date(2026, 1, 31)),
        (date(2025, 12, 1), date(2025, 12, 31)),
    ]


def test_a_justica_do_trabalho_fica_de_fora():
    assert djen.da_justica_do_trabalho(_item(DO_TRABALHO, "TRT2"))
    assert djen.da_justica_do_trabalho(_item(DO_TRABALHO, ""))  # só pelo número
    assert djen.da_justica_do_trabalho({"siglaTribunal": "TST"})
    assert not djen.da_justica_do_trabalho(_item(ESTADUAL, "TJSP"))


def test_obter_pagina_tira_o_trabalho_e_os_advogados(tmp_path: Path):
    inicio, fim = date(2026, 10, 26), date(2026, 11, 1)
    primeira = djen.consulta(EMPRESA, inicio, fim)
    segunda = djen.consulta(EMPRESA, inicio, fim, pagina=2)
    pagina_1 = [_item(ESTADUAL, "TJSP")] * djen.ITENS_POR_PAGINA
    cliente = Djen(
        {
            primeira: _corpo(pagina_1, total=102),
            segunda: _corpo(
                [_item(ESTADUAL, "TJSP"), _item(DO_TRABALHO, "TRT2")], total=102
            ),
        }
    )
    destino = tmp_path / "consulta.json"
    djen.obter_consulta(primeira)(cliente, destino)

    guardado = json.loads(destino.read_text(encoding="utf-8"))
    assert cliente.lidos == [primeira, segunda]
    assert guardado["consulta"] == {
        "nome": EMPRESA,
        "inicio": "2026-10-26",
        "fim": "2026-11-01",
    }
    assert (guardado["total_na_fonte"], guardado["lidas"]) == (102, 102)
    assert guardado["fora_por_ser_do_trabalho"] == 1
    assert not guardado["cortada"]
    assert len(guardado["items"]) == 101
    assert all(i["siglaTribunal"] != "TRT2" for i in guardado["items"])
    assert "ADVOGADO" not in destino.read_text(encoding="utf-8")
    assert guardado["items"][0]["quantidade_de_advogados"] == 2


def test_obter_para_no_maximo_de_paginas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(djen, "MAXIMO_DE_PAGINAS", 2)
    inicio, fim = date(2026, 10, 26), date(2026, 11, 1)
    paginas = {
        djen.consulta(EMPRESA, inicio, fim, p): _corpo(
            [_item(ESTADUAL, "TJSP")], total=50
        )
        for p in (1, 2, 3)
    }
    cliente = Djen(paginas)
    destino = tmp_path / "consulta.json"
    djen.obter_consulta(djen.consulta(EMPRESA, inicio, fim))(cliente, destino)
    guardado = json.loads(destino.read_text(encoding="utf-8"))
    assert len(cliente.lidos) == 2
    assert guardado["cortada"]


def test_resposta_sem_sucesso_e_falha(tmp_path: Path):
    endereco = djen.consulta(EMPRESA, date(2026, 10, 26), date(2026, 11, 1))
    cliente = Djen({endereco: json.dumps({"status": "error", "message": "x"}).encode()})
    with pytest.raises(ValueError, match="DJEN"):
        djen.obter_consulta(endereco)(cliente, tmp_path / "x.json")


def test_descobrir_a_semana_de_todas_e_o_historico_que_falta(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(djen, "HISTORICO_DESDE", date(2026, 9, 1))
    monkeypatch.setattr(djen, "MAXIMO_DO_HISTORICO_POR_RODADA", 3)
    empresas = ["A S.A.", "B S.A."]
    outubro_de_a = djen.consulta("A S.A.", date(2026, 10, 1), date(2026, 10, 31))
    descobrir = djen.descobrir(lambda: empresas, lambda: frozenset({outubro_de_a}))

    alvos = [a.url for a in descobrir(Djen({}), AGORA)]

    semana = (date(2026, 10, 26), date(2026, 11, 1))
    assert alvos[:2] == [djen.consulta(e, *semana) for e in empresas]
    setembro = (date(2026, 9, 1), date(2026, 9, 30))
    assert alvos[2:] == [
        djen.consulta("B S.A.", date(2026, 10, 1), date(2026, 10, 31)),
        djen.consulta("A S.A.", *setembro),
        djen.consulta("B S.A.", *setembro),
    ]
    assert outubro_de_a not in alvos


def test_descobrir_sem_cadastro_falha():
    with pytest.raises(ErroDeDescoberta, match="cadastro"):
        djen.descobrir(lambda: [], frozenset)(Djen({}), AGORA)
