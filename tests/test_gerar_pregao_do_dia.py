"""Script diário do pregão do dia (plano `2026-10-28-raio-x-todo-dia`, PR 4b).

Lê o que o arquivista guardou no acervo (pelo manifesto), monta os números do pregão e grava em
`<acervo>/pregao/AAAA-MM-DD.json`. Dia sem pregão não gera; arquivo que falta ou número que não sai
vira `FALHAS:` na última linha, e a B3 corrigir o dia refaz o resumo.
"""

import json
import shutil
import zipfile
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pytest

from base import indices_b3
from scripts import gerar_pregao_do_dia as script
from src import acervo as modulo_do_acervo
from src import eventos_do_pregao
from src import texto_do_pregao as tp
from tests.test_base_intradiario_b3 import (
    registro_do_cotahist,
    relatorio,
    xml_do_boletim,
    zip_do_boletim,
)

VESPERA = date(2026, 10, 26)
DIA = date(2026, 10, 27)
QUARTA = date(2026, 10, 28)
QUINTA = date(2026, 10, 29)
SEXTA = date(2026, 10, 30)
HOJE = ["--hoje", QUARTA.isoformat()]
LIQUIDO = 50_000_000.0
EMPRESAS = {
    "PETR4": ("11", "Petróleo", 30.0, 33.0),
    "VALE3": ("22", "Mineração", 60.0, 54.0),
    "ITUB4": ("33", "Bancos", 40.0, 40.0),
}
PRECOS_DA_VESPERA = {simbolo: e[2] for simbolo, e in EMPRESAS.items()}
PRECOS_DO_DIA = {simbolo: e[3] for simbolo, e in EMPRESAS.items()}


def guardar(acervo: Path, fonte: str, url: str, origem: Path, hora: str, sha: str):
    """Põe o arquivo no acervo e a linha no manifesto, como o arquivista faz."""
    relativo = f"bruto/{fonte}/{sha}{origem.suffix}"
    (acervo / relativo).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(origem, acervo / relativo)
    manifesto = acervo / "manifesto" / f"{hora[:10]}.jsonl"
    manifesto.parent.mkdir(parents=True, exist_ok=True)
    with manifesto.open("a", encoding="utf-8") as arquivo:
        linha = {
            "fonte": fonte,
            "url": url,
            "sha256": sha,
            "caminho": relativo,
            "hora": hora,
        }
        arquivo.write(json.dumps(linha) + "\n")


def guardar_cotahist(
    acervo: Path, dia: date, precos: dict[str, float], versao: str = "a"
) -> None:
    linhas = [
        registro_do_cotahist(simbolo, "010", (p, p, p, p), volume_financeiro=LIQUIDO)
        for simbolo, p in precos.items()
    ]
    nome = f"COTAHIST_D{dia:%d%m%Y}.ZIP"
    origem = acervo.parent / nome
    with zipfile.ZipFile(origem, "w") as arquivo:
        arquivo.writestr("COTAHIST.TXT", "\r\n".join(linhas).encode("latin-1"))
    url = f"https://bvmf.bmfbovespa.com.br/InstDados/SerHist/{nome}"
    hora = f"{dia.isoformat()}T23:0{ord(versao) - ord('a')}:00+00:00"
    guardar(acervo, script.FONTE_DO_COTAHIST, url, origem, hora, f"{nome}-{versao}")


def guardar_pr(acervo: Path, dia: date) -> None:
    contratos = [
        relatorio("DI1F29", AdjstdQtTax="14.76", PrvsAdjstdQtTax="15.22"),
        relatorio("DOLX26", AdjstdQt="5350.3", PrvsAdjstdQt="5422.9"),
    ]
    quando = datetime(dia.year, dia.month, dia.day, 21, 0, tzinfo=UTC)
    pasta = acervo.parent / f"pr-{dia.isoformat()}"
    pasta.mkdir()
    origem = zip_do_boletim(
        pasta, {"BVBG.086.01_A.xml": (quando, xml_do_boletim(contratos))}
    )
    url = f"https://www.b3.com.br/pesquisapregao/download?filelist=PR{dia:%y%m%d}.zip"
    hora = f"{dia.isoformat()}T23:30:00+00:00"
    guardar(acervo, script.FONTE_DO_PR, url, origem, hora, f"PR{dia:%y%m%d}")


def guardar_ibovespa(acervo: Path, ate: date) -> None:
    """Os arquivos do índice, um por ano, como a B3 entrega: uma linha por dia do mês. O último dia
    de cada arquivo define a versão dele; nos anos fechados, o conteúdo não muda."""
    for ano in range(indices_b3.PRIMEIRO_ANO, ate.year + 1):
        if ano < ate.year:
            linhas = [{"day": 2, "rateValue1": "100,00"}]
            versao = "fechado"
        else:
            linhas = [
                {"day": dia, "rateValue10": f"100.{dia:03d},00"}
                for dia in range(23, ate.day + 1)
                if date(ano, 10, dia).weekday() < 5
            ]
            versao = ate.isoformat()
        origem = acervo.parent / f"ibov-{ano}.json"
        origem.write_text(json.dumps({"results": linhas}), "utf-8")
        guardar(
            acervo,
            script.FONTE_DO_IBOVESPA,
            indices_b3.endereco_do_ano(ano, indices_b3.IBOVESPA),
            origem,
            f"{ate.isoformat()}T23:40:00+00:00",
            f"ibov-{ano}-{versao}",
        )


def guardar_o_dia(acervo: Path, dia: date) -> None:
    guardar_cotahist(acervo, dia, PRECOS_DO_DIA)
    guardar_pr(acervo, dia)
    guardar_ibovespa(acervo, dia)


def tirar_do_manifesto(acervo: Path, trecho: str) -> None:
    for manifesto in (acervo / "manifesto").glob("*.jsonl"):
        linhas = manifesto.read_text("utf-8").splitlines()
        ficam = [linha for linha in linhas if trecho not in linha]
        manifesto.write_text("\n".join(ficam) + "\n", "utf-8")


@pytest.fixture
def acervo(tmp_path, monkeypatch):
    pasta = tmp_path / "acervo"
    pasta.mkdir()
    monkeypatch.setenv(modulo_do_acervo.VARIAVEL_DA_PASTA, str(pasta))
    (pasta / "base" / "fca").mkdir(parents=True)
    pd.DataFrame(
        {
            "codigo": list(EMPRESAS),
            "cnpj": [e[0] for e in EMPRESAS.values()],
            "inicio_negociacao": ["2000-01-01"] * 3,
            "fim_negociacao": [None] * 3,
        }
    ).to_parquet(pasta / "base" / "fca" / "tickers.parquet")
    (pasta / "base" / "fca_geral").mkdir()
    pd.DataFrame(
        {
            "cnpj": [e[0] for e in EMPRESAS.values()],
            "setor": [e[1] for e in EMPRESAS.values()],
            "conhecido_em": pd.to_datetime(["2026-01-01"] * 3),
        }
    ).to_parquet(pasta / "base" / "fca_geral" / "2026.parquet")
    guardar_cotahist(pasta, VESPERA, PRECOS_DA_VESPERA)
    guardar_o_dia(pasta, DIA)
    return pasta


def resumo_gravado(acervo: Path, dia: date = DIA) -> dict:
    return json.loads(script.caminho_do_resumo(acervo, dia).read_text("utf-8"))


def ultima_linha(capsys) -> str:
    return capsys.readouterr().out.strip().splitlines()[-1]


def test_grava_o_resumo_com_os_numeros_dos_arquivos(acervo, capsys) -> None:
    assert script.main(HOJE) == 0
    resumo = resumo_gravado(acervo)
    assert resumo["pregao"] == "2026-10-27"
    assert resumo["vespera"] == "2026-10-26"
    assert resumo["maiores"]["altas"][0]["simbolo"] == "PETR4"
    assert resumo["maiores"]["altas"][0]["empresa"] == "Petrobras"
    assert resumo["maiores"]["altas"][0]["variacao"] == pytest.approx(0.10)
    assert resumo["maiores"]["quedas"][0]["simbolo"] == "VALE3"
    assert resumo["amplitude"]["estaveis"] == 1
    assert resumo["ibovespa"]["pontos"] == 100_027.0
    assert resumo["juros"]["simbolo"] == "DI1F29"
    assert resumo["juros"]["taxa"] == 14.76
    assert resumo["dolar"]["simbolo"] == "DOLX26"
    assert "2026-10-27" in capsys.readouterr().out


def test_o_texto_aprovado_sai_do_resumo_gravado(acervo) -> None:
    script.main(HOJE)
    texto = tp.texto_do_pregao(resumo_gravado(acervo), tp.ler_molde())
    assert texto["pregao"] == "2026-10-27"
    assert texto["impressao_digital"] == tp.IMPRESSAO_DO_MOLDE_APROVADO


def test_quem_le_a_pasta_do_acervo_acha_o_ultimo_resumo(acervo) -> None:
    script.main(HOJE)
    assert tp.ultimo_resumo(acervo / script.PASTA_NO_ACERVO)["pregao"] == "2026-10-27"


def test_papel_com_evento_fica_a_conferir_e_fora_das_contas(acervo) -> None:
    """Grupamento: o preço salta, o código é o mesmo e o DISMES mudou. Sem isso, seria a maior alta."""
    tirar_do_manifesto(acervo, "COTAHIST_D27102026")
    linhas = [
        registro_do_cotahist(
            simbolo,
            "010",
            (p, p, p, p),
            volume_financeiro=LIQUIDO,
            distribuicao="102" if simbolo == "VALE3" else "101",
        )
        for simbolo, p in (PRECOS_DO_DIA | {"VALE3": 600.0}).items()
    ]
    origem = acervo.parent / "COTAHIST_D27102026.ZIP"
    with zipfile.ZipFile(origem, "w") as arquivo:
        arquivo.writestr("COTAHIST.TXT", "\r\n".join(linhas).encode("latin-1"))
    guardar(
        acervo,
        script.FONTE_DO_COTAHIST,
        "https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_D27102026.ZIP",
        origem,
        "2026-10-27T23:00:00+00:00",
        "cotahist-com-evento",
    )
    assert script.main(HOJE) == 0
    resumo = resumo_gravado(acervo)
    assert [papel["simbolo"] for papel in resumo["a_conferir"]] == ["VALE3"]
    assert resumo["maiores"]["altas"][0]["simbolo"] == "PETR4"


def test_dia_de_evento_vai_no_resumo(acervo, capsys) -> None:
    """28/10/2026 teve decisão do Fed (FOMC) no calendário; 27/10 foi um dia comum."""
    guardar_o_dia(acervo, QUARTA)
    assert script.main(["--hoje", QUINTA.isoformat()]) == 0
    assert "2026-10-28: " in capsys.readouterr().out
    assert resumo_gravado(acervo, DIA)["evento"] is None
    evento = resumo_gravado(acervo, QUARTA)["evento"]
    assert [m["evento"] for m in evento["calendario"]] == ["Decisão do Fed (FOMC)"]
    assert evento["variacao_forte_do_ibovespa"] is False


def test_data_nova_no_calendario_refaz_so_o_pregao_dela(acervo, monkeypatch) -> None:
    script.main(HOJE)
    caminho = script.caminho_do_resumo(acervo, DIA)
    antes = caminho.stat().st_mtime_ns
    calendario = acervo.parent / "calendario.csv"
    calendario.write_text(
        "data,evento,momento,fonte\n2026-11-12,IPCA,antes_do_fechamento,https://ibge\n",
        "utf-8",
    )
    monkeypatch.setattr(eventos_do_pregao, "CAMINHO_DO_CALENDARIO", calendario)
    script.main(HOJE)
    assert caminho.stat().st_mtime_ns == antes
    calendario.write_text(
        "data,evento,momento,fonte\n2026-10-27,IPCA,antes_do_fechamento,https://ibge\n",
        "utf-8",
    )
    script.main(HOJE)
    assert caminho.stat().st_mtime_ns > antes
    assert resumo_gravado(acervo)["evento"]["calendario"][0]["evento"] == "IPCA"


def test_calendario_estragado_falha_com_aviso(acervo, monkeypatch, capsys) -> None:
    calendario = acervo.parent / "calendario.csv"
    calendario.write_text(
        "data,evento,momento,fonte\n2026-10-27,IPCA,quando,x\n", "utf-8"
    )
    monkeypatch.setattr(eventos_do_pregao, "CAMINHO_DO_CALENDARIO", calendario)
    assert script.main(HOJE) == 1
    assert "calendário de eventos não abriu" in ultima_linha(capsys)


def test_sem_nada_novo_nao_refaz(acervo) -> None:
    script.main(HOJE)
    caminho = script.caminho_do_resumo(acervo, DIA)
    antes = caminho.stat().st_mtime_ns
    assert script.main(HOJE) == 0
    assert caminho.stat().st_mtime_ns == antes


def test_dia_novo_no_ibovespa_nao_refaz_os_pregoes_passados(acervo) -> None:
    """O arquivo do ano muda todo dia; o resumo de ontem só muda se a série até ontem mudar."""
    script.main(HOJE)
    caminho = script.caminho_do_resumo(acervo, DIA)
    antes = caminho.stat().st_mtime_ns
    guardar_o_dia(acervo, QUARTA)
    assert script.main(["--hoje", QUINTA.isoformat()]) == 0
    assert caminho.stat().st_mtime_ns == antes
    assert resumo_gravado(acervo, QUARTA)["vespera"] == "2026-10-27"


def test_refaz_quando_a_b3_corrige_o_dia(acervo) -> None:
    script.main(HOJE)
    guardar_cotahist(acervo, DIA, PRECOS_DO_DIA | {"PETR4": 36.0}, versao="b")
    assert script.main(HOJE) == 0
    altas = resumo_gravado(acervo)["maiores"]["altas"]
    assert altas[0]["variacao"] == pytest.approx(0.20)


def test_refaz_quando_a_regra_muda(acervo, monkeypatch) -> None:
    script.main(HOJE)
    caminho = script.caminho_do_resumo(acervo, DIA)
    antes = caminho.stat().st_mtime_ns
    monkeypatch.setattr(script, "VERSAO_DA_REGRA", script.VERSAO_DA_REGRA + 1)
    script.main(HOJE)
    assert caminho.stat().st_mtime_ns > antes


def test_refaz_um_pregao_pedido_mesmo_em_dia(acervo) -> None:
    script.main(HOJE)
    caminho = script.caminho_do_resumo(acervo, DIA)
    antes = caminho.stat().st_mtime_ns
    assert script.main(["--pregao", DIA.isoformat(), *HOJE]) == 0
    assert caminho.stat().st_mtime_ns > antes


def test_feriado_nao_gera(acervo, capsys) -> None:
    natal = date(2026, 12, 25)
    guardar_cotahist(acervo, natal, PRECOS_DO_DIA)
    assert script.main(["--pregao", natal.isoformat(), *HOJE]) == 0
    assert not script.caminho_do_resumo(acervo, natal).exists()
    assert "não houve pregão" in capsys.readouterr().out


def test_arquivo_guardado_em_feriado_nao_entra_na_rodada(acervo) -> None:
    natal = date(2026, 12, 25)
    guardar_cotahist(acervo, natal, PRECOS_DO_DIA)
    assert script.main(HOJE) == 0
    assert not script.caminho_do_resumo(acervo, natal).exists()


def test_sem_cotahist_falha_com_aviso(acervo, capsys) -> None:
    assert script.main(["--hoje", QUINTA.isoformat()]) == 1
    linha = ultima_linha(capsys)
    assert linha.startswith("FALHAS:")
    assert script.FONTE_DO_COTAHIST in linha
    assert QUARTA.isoformat() in linha
    assert script.caminho_do_resumo(acervo, DIA).exists()  # o que dá para fazer, faz


def test_fim_de_semana_cobra_so_o_ultimo_pregao(acervo) -> None:
    for dia in (QUARTA, QUINTA, SEXTA):
        guardar_o_dia(acervo, dia)
    assert script.main(["--hoje", "2026-11-01"]) == 0  # domingo


def test_sem_a_vespera_falha_em_vez_de_comparar_com_dois_dias_antes(
    acervo, capsys
) -> None:
    guardar_o_dia(acervo, QUINTA)  # 28/10 não foi guardado
    assert script.main(["--hoje", SEXTA.isoformat()]) == 1
    assert QUARTA.isoformat() in ultima_linha(capsys)
    assert not script.caminho_do_resumo(acervo, QUINTA).exists()


def test_sem_o_boletim_pr_falha(acervo, capsys) -> None:
    tirar_do_manifesto(acervo, script.FONTE_DO_PR)
    assert script.main(HOJE) == 1
    assert script.FONTE_DO_PR in ultima_linha(capsys)
    assert not script.caminho_do_resumo(acervo, DIA).exists()


def test_ano_faltando_no_ibovespa_falha(acervo, capsys) -> None:
    tirar_do_manifesto(acervo, indices_b3.endereco_do_ano(2013, indices_b3.IBOVESPA))
    assert script.main(HOJE) == 1
    assert "2013" in ultima_linha(capsys)
    assert not script.caminho_do_resumo(acervo, DIA).exists()


def test_ibovespa_sem_a_vespera_falha(acervo, capsys) -> None:
    """Sem isso, a variação do índice seria sobre dois dias, com a data de um."""
    origem = acervo.parent / "ibov-buraco.json"
    linhas = [
        {"day": 23, "rateValue10": "100,00"},
        {"day": 27, "rateValue10": "101,00"},
    ]
    origem.write_text(json.dumps({"results": linhas}), "utf-8")
    guardar(
        acervo,
        script.FONTE_DO_IBOVESPA,
        indices_b3.endereco_do_ano(2026, indices_b3.IBOVESPA),
        origem,
        "2026-10-27T23:50:00+00:00",
        "ibov-2026-buraco",
    )
    assert script.main(HOJE) == 1
    assert "Ibovespa" in ultima_linha(capsys)
    assert not script.caminho_do_resumo(acervo, DIA).exists()


def test_arquivo_estragado_falha_sem_derrubar_os_outros_dias(acervo, capsys) -> None:
    guardar_o_dia(acervo, QUARTA)
    assert script.main(["--hoje", QUINTA.isoformat()]) == 0
    origem = acervo.parent / "estragado.zip"
    origem.write_bytes(b"isto nao e um zip")
    guardar(
        acervo,
        script.FONTE_DO_PR,
        "https://www.b3.com.br/pesquisapregao/download?filelist=PR261027.zip",
        origem,
        "2026-10-29T01:00:00+00:00",
        "pr-estragado",
    )
    assert script.main(["--hoje", QUINTA.isoformat()]) == 1
    assert DIA.isoformat() in ultima_linha(capsys)


def test_molde_diferente_do_aprovado_nao_gera(acervo, monkeypatch, capsys) -> None:
    monkeypatch.setattr(tp, "IMPRESSAO_DO_MOLDE_APROVADO", "outra")
    assert script.main(HOJE) == 1
    assert "molde" in ultima_linha(capsys)
    assert not script.caminho_do_resumo(acervo, DIA).exists()


def test_antes_do_primeiro_pregao_nao_gera(acervo) -> None:
    assert script.main(HOJE) == 0
    assert not script.caminho_do_resumo(acervo, VESPERA).exists()


def test_acervo_desligado_nao_faz_nada(monkeypatch, capsys) -> None:
    monkeypatch.setenv(modulo_do_acervo.VARIAVEL_DA_PASTA, modulo_do_acervo.DESLIGADO)
    assert script.main(HOJE) == 0
    assert "Acervo desligado" in capsys.readouterr().out
