"""Camada A3: critérios travados, universo mecânico, leitura da nota e a regra que monta a carteira."""

import json
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from tests import ajudantes_f_b3 as ajudantes
from trader import criterio_quant
from trader.agentes import criterios, rodada
from trader.agentes import registro as reg
from trader.estrategias import fatores_b3 as fb

BRASILIA = ZoneInfo("America/Sao_Paulo")
DATAS = pd.bdate_range("2024-01-02", "2026-10-30")
TICKERS = [f"T{numero:02d}3" for numero in range(35)]
CNPJS = {t: f"{i:02d}.111.111/0001-00" for i, t in enumerate(TICKERS)}


def _dados():
    """35 ações; a de número i negocia R$ (i + 1) milhões por dia: 31 passam do piso de R$ 5 milhões."""
    fechamento = ajudantes.precos(datas=DATAS, tickers=TICKERS)
    volume = pd.DataFrame(
        {t: float(i + 1) * 1e6 for i, t in enumerate(TICKERS)}, index=DATAS
    )
    cadastro = pd.DataFrame(
        {
            "cnpj": [CNPJS[t] for t in TICKERS],
            "classe": "ON",
            "inicio_negociacao": pd.Timestamp("2020-01-02"),
            "fim_negociacao": pd.NaT,
        },
        index=pd.Index(TICKERS, name="ticker"),
    )
    fundamentos = ajudantes.fundamentos(cnpjs=list(CNPJS.values()))
    fundamentos["divulgado_em"] = fundamentos["divulgado_em"] + pd.DateOffset(years=6)
    return fb.Dados(
        fechamento=fechamento,
        abertura=fechamento,
        volume=volume,
        cadastro=cadastro,
        fundamentos=fundamentos,
        acoes=ajudantes.acoes(cnpjs=list(CNPJS.values())),
        cdi=pd.Series(0.0004, index=DATAS),
    )


@pytest.fixture
def aprovado(monkeypatch):
    """Faz de conta que o Tiago aprovou o texto atual (o hash real só entra com o "pode" dele)."""
    monkeypatch.setattr(criterios, "HASH_APROVADO", criterios.hash_atual())


def _resposta(notas, vetos=(), fontes=True):
    itens = {
        codigo: {
            "nota": nota,
            "fontes": ["DFP 2025, CVM, 31/03/2026"] if fontes else [],
        }
        for codigo, nota in notas.items()
    }
    bloco = {
        "vetos": [{"codigo": v, "fonte": "CVM, 01/10/2026"} for v in vetos],
        "itens": itens,
        "resumo": "Uma frase.",
    }
    return (
        '# Dossiê\n\nTexto com ```json {"falso": 1}``` no meio.\n\n```json\n'
        + json.dumps(bloco)
        + "\n```\n"
    )


TODAS_7 = dict.fromkeys(criterios.PESOS, 7)


# --- os critérios --------------------------------------------------------------------------------


def test_texto_aprovado_confere_sem_dublê():
    # o hash do "pode" do Tiago (03/11/2026) bate com o texto do repositório
    assert criterios.HASH_APROVADO is not None
    assert criterios.conferir() == criterios.hash_atual()
    assert "APROVADO pelo Tiago" in criterios.texto()


def test_rascunho_sem_hash_aprovado_nao_roda(monkeypatch):
    monkeypatch.setattr(criterios, "HASH_APROVADO", None)
    with pytest.raises(criterios.CriteriosNaoAprovadosError, match="rascunho"):
        criterios.conferir()


def test_texto_diferente_do_aprovado_nao_roda(monkeypatch):
    monkeypatch.setattr(criterios, "HASH_APROVADO", "0" * 64)
    with pytest.raises(criterios.CriteriosNaoAprovadosError, match="mudou"):
        criterios.conferir()


def test_conferir_devolve_o_hash_aprovado(aprovado):
    assert criterios.conferir() == criterios.hash_atual()


def test_numeros_do_codigo_estao_no_texto():
    texto = criterios.texto()
    assert sum(criterios.PESOS.values()) == 100
    for codigo, peso in criterios.PESOS.items():
        assert re.search(rf"\| {codigo} \|[^\n]*\| {peso} \|", texto), codigo
    for codigo in criterios.VETOS:
        assert f"| {codigo} |" in texto
    assert (
        "7,0" in texto
        and "as até 5 maiores" in texto
        and "as 30 mais líquidas" in texto
    )
    assert "no máximo 5" in texto and "40%" in texto and "12 meses" in texto
    assert criterios.PISO_DE_LIQUIDEZ == criterio_quant.PISO_DE_LIQUIDEZ_EM_REAIS
    assert "R$ 5 milhões" in texto


def test_pedido_tem_a_empresa_a_data_e_os_criterios_inteiros():
    candidata = rodada.Candidata("T103", "10.111.111/0001-00", 1.1e7)
    texto = rodada.pedido(candidata, date(2026, 11, 3))
    assert "T103" in texto and "10.111.111/0001-00" in texto and "2026-11-03" in texto
    assert criterios.texto() in texto
    assert "$" not in texto.replace("R$", "")  # nenhum marcador sobrou
    for codigo in criterios.PESOS:
        assert f'"{codigo}"' in texto


# --- o universo ----------------------------------------------------------------------------------


def test_candidatas_sao_as_30_mais_liquidas_acima_do_piso():
    escolhidas = rodada.candidatas(DATAS[-1], _dados())
    assert len(escolhidas) == criterios.MAXIMO_DE_CANDIDATAS
    assert escolhidas[0].ticker == "T343"  # a mais líquida primeiro
    assert {c.ticker for c in escolhidas} == set(
        TICKERS[5:]
    )  # T043 (R$ 5 mi) fica de fora
    assert all(c.liquidez >= criterios.PISO_DE_LIQUIDEZ for c in escolhidas)


def test_universo_nao_olha_o_futuro():
    dados = _dados()
    dia = DATAS[-40]
    antes = rodada.candidatas(dia, dados)
    dados.volume.loc[dados.volume.index > dia] = 0.0  # o futuro some
    dados.fechamento.loc[dados.fechamento.index > dia] = float("nan")
    assert rodada.candidatas(dia, dados) == antes


def test_poucos_pregoes_nao_fazem_rodada():
    with pytest.raises(rodada.PoucosPregoesError, match="60"):
        rodada.candidatas(DATAS[30], _dados())


# --- a resposta do agente ------------------------------------------------------------------------


def test_le_o_ultimo_bloco_json_e_calcula_a_nota_final():
    notas = {"C1": 10, "C2": 5, "C3": 5, "C4": 5, "C5": 10, "C6": 5}
    avaliacao = rodada.ler_resposta("T103", _resposta(notas))
    assert avaliacao.notas == notas
    assert avaliacao.nota_final == pytest.approx(7.0)  # (200 + 75·4 + 200) ÷ 100
    assert avaliacao.vetos == ()


def test_veto_zera_a_nota_final():
    avaliacao = rodada.ler_resposta("T103", _resposta(TODAS_7, vetos=["V2"]))
    assert avaliacao.nota_final == 0.0
    assert avaliacao.vetos[0]["codigo"] == "V2"


@pytest.mark.parametrize(
    ("estragar", "mensagem"),
    [
        (lambda b: b["itens"].pop("C3"), "C3"),
        (lambda b: b["itens"]["C1"].update(nota=11), "0 a 10"),
        (lambda b: b["itens"]["C1"].update(nota=7.5), "inteira"),
        (lambda b: b["itens"]["C1"].update(fontes=[]), "fonte"),
        (lambda b: b["vetos"].append({"codigo": "V9", "fonte": "x"}), "V9"),
        (lambda b: b["vetos"].append({"codigo": "V1", "fonte": ""}), "fonte"),
        (lambda b: b["itens"].update(C7={"nota": 1, "fontes": []}), "C7"),
    ],
)
def test_resposta_fora_do_formato_e_recusada(estragar, mensagem):
    texto = _resposta(TODAS_7)
    bloco = json.loads(texto.split("```json\n")[-1].split("\n```")[0])
    estragar(bloco)
    with pytest.raises(rodada.RespostaInvalidaError, match=mensagem):
        rodada.ler_resposta("T103", "```json\n" + json.dumps(bloco) + "\n```")


def test_nota_ate_5_pode_ficar_sem_fonte():
    avaliacao = rodada.ler_resposta(
        "T103", _resposta(dict.fromkeys(criterios.PESOS, 5), fontes=False)
    )
    assert avaliacao.nota_final == 5.0


def test_resposta_sem_bloco_json_e_recusada():
    with pytest.raises(rodada.RespostaInvalidaError, match="bloco"):
        rodada.ler_resposta("T103", "# Dossiê sem nota")


# --- a regra -------------------------------------------------------------------------------------


def _avaliacao(ticker, nota):
    return rodada.Avaliacao(ticker, dict.fromkeys(criterios.PESOS, nota), {}, (), "")


def test_regra_pega_as_5_maiores_do_corte_para_cima_com_pesos_iguais():
    avaliacoes = [
        _avaliacao(f"X{n}", nota) for n, nota in enumerate([9, 8, 8, 7, 7, 7, 6, 10])
    ]
    liquidez = {f"X{n}": float(n) for n in range(8)}
    escolhidas = rodada.escolher(avaliacoes, liquidez)
    # 10 (X7), 9 (X0), 8 e 8 (X1, X2) e, entre os três 7, o mais líquido (X5).
    assert escolhidas == dict.fromkeys(["X7", "X0", "X2", "X1", "X5"], 0.2)


def test_sem_ninguem_no_corte_a_camada_fica_em_cdi():
    assert rodada.escolher([_avaliacao("X0", 6)], {"X0": 1.0}) == {}


def test_menos_de_5_deixa_o_resto_em_cdi():
    escolhidas = rodada.escolher(
        [_avaliacao("X0", 8), _avaliacao("X1", 7)], {"X0": 1, "X1": 2}
    )
    assert escolhidas == {"X0": 0.2, "X1": 0.2}
    assert sum(escolhidas.values()) == pytest.approx(0.4)


@pytest.mark.parametrize(
    ("dia", "dentro"),
    [
        (date(2026, 12, 1), True),  # 1º pregão de dezembro
        (date(2026, 12, 7), True),  # 5º
        (date(2026, 12, 8), False),  # 6º
        (date(2027, 1, 4), True),  # 1º de 2027 (1º de janeiro é feriado)
    ],
)
def test_janela_da_rodada_sao_os_5_primeiros_pregoes_do_mes(dia, dentro):
    assert rodada.dentro_da_janela(dia) is dentro


# --- preparar e registrar ------------------------------------------------------------------------


def test_preparar_recusa_rascunho(tmp_path, monkeypatch):
    monkeypatch.setattr(criterios, "HASH_APROVADO", None)
    with pytest.raises(criterios.CriteriosNaoAprovadosError):
        rodada.preparar(_dados(), tmp_path, hoje=date(2026, 11, 3))
    assert not any(tmp_path.iterdir())


def test_preparar_fora_da_janela_e_recusado(tmp_path, aprovado):
    with pytest.raises(rodada.ForaDaJanelaError):
        rodada.preparar(_dados(), tmp_path, hoje=date(2026, 11, 13))


def test_preparar_com_dados_velhos_e_recusado(tmp_path, aprovado):
    with pytest.raises(rodada.DadosVelhosError):
        rodada.preparar(_dados(), tmp_path, hoje=date(2027, 2, 1))


def test_rodada_inteira_vai_para_o_registro(tmp_path, aprovado):
    pasta = tmp_path / "2026-11"
    pedidos = rodada.preparar(_dados(), pasta, hoje=date(2026, 11, 3))
    assert len(pedidos) == criterios.MAXIMO_DE_CANDIDATAS
    candidatas = json.loads(
        (pasta / rodada.ARQUIVO_DAS_CANDIDATAS).read_text(encoding="utf-8")
    )
    assert candidatas["dia_dos_dados"] == "2026-10-30"
    respostas = pasta / rodada.PASTA_DAS_RESPOSTAS
    respostas.mkdir()
    for numero, candidata in enumerate(candidatas["candidatas"]):
        nota = 9 if numero < 2 else 4
        (respostas / f"{candidata['ticker']}.md").write_text(
            _resposta(dict.fromkeys(criterios.PESOS, nota)), encoding="utf-8"
        )
    registro = reg.RegistroDeAgentes(tmp_path / "registro")
    linha = rodada.registrar(
        pasta,
        registro,
        modelo="claude-sonnet-5-5",
        agora=datetime(2026, 11, 3, 15, tzinfo=BRASILIA),
    )
    assert linha["data"] == "2026-11-03"
    assert linha["hash_dos_criterios"] == criterios.hash_atual()
    assert linha["escolhidas"] == {"T343": 0.2, "T333": 0.2}
    assert len(linha["avaliacoes"]) == criterios.MAXIMO_DE_CANDIDATAS
    dossie = registro.ler_dossie(linha["avaliacoes"][0]["hash_do_dossie"])
    assert dossie.startswith("# Dossiê")
    registro.verificar()


def test_registrar_sem_todas_as_respostas_nao_grava_nada(tmp_path, aprovado):
    pasta = tmp_path / "2026-11"
    rodada.preparar(_dados(), pasta, hoje=date(2026, 11, 3))
    (pasta / rodada.PASTA_DAS_RESPOSTAS).mkdir()
    registro = reg.RegistroDeAgentes(tmp_path / "registro")
    with pytest.raises(FileNotFoundError, match="faltam 30 respostas"):
        rodada.registrar(
            pasta,
            registro,
            modelo="m",
            agora=datetime(2026, 11, 3, 15, tzinfo=BRASILIA),
        )
    assert registro.linhas() == []


def test_registrar_noutro_dia_que_nao_o_da_preparacao_e_recusado(tmp_path, aprovado):
    pasta = tmp_path / "2026-11"
    rodada.preparar(_dados(), pasta, hoje=date(2026, 11, 3))
    registro = reg.RegistroDeAgentes(tmp_path / "registro")
    with pytest.raises(reg.RodadaRecusadaError, match="preparada em 2026-11-03"):
        rodada.registrar(
            pasta, registro, modelo="m", agora=datetime(2026, 11, 4, 9, tzinfo=BRASILIA)
        )
