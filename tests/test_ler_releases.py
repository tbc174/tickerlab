"""A medição dos releases de resultado (vitrine, PR 1, sem API)."""

import pandas as pd

from base import releases
from scripts import ler_releases


def _release(cnpj, referencia, entrega, protocolo):
    return {
        "cnpj": cnpj, "codigo_cvm": "1", "periodo": "x", "referencia": pd.Timestamp(referencia),
        "data_entrega": pd.Timestamp(entrega), "protocolo": protocolo, "versao": 1, "link": "https://www.rad.cvm.gov.br/x.pdf",
    }  # fmt: skip


def test_medir_conta_por_ano_e_casa_com_itr():
    achados = pd.DataFrame(
        [
            _release("11.111.111/0001-11", "2024-09-30", "2024-11-05", "a"),
            _release("11.111.111/0001-11", "2025-09-30", "2025-11-05", "b"),
            _release("22.222.222/0001-22", "2025-09-30", "2025-11-06", "c"),
            _release("22.222.222/0001-22", "2025-12-31", "2026-02-20", "d"),
        ],
        columns=list(releases.COLUNAS),
    )
    demonstracoes = pd.DataFrame(
        {
            "cnpj": ["11111111000111", "11111111000111", "22222222000122"],
            "documento": ["ITR", "ITR", "ITR"],
            "referencia": pd.to_datetime(["2024-09-30", "2025-09-30", "2025-09-30"]),
        }
    )
    medida = ler_releases.medir(achados, demonstracoes).set_index("ano")
    assert medida.loc[2024, "releases"] == 1 and medida.loc[2024, "com_itr_dfp"] == 1
    assert medida.loc[2025, "releases"] == 2 and medida.loc[2025, "com_itr_dfp"] == 2
    assert medida.loc[2026, "releases"] == 1 and medida.loc[2026, "com_itr_dfp"] == 0
    assert medida.loc[2025, "empresas"] == 2
    assert medida.loc[2026, "percentual_com_itr_dfp"] == 0.0


# --- o leitor com cliente falso (PR 2): nada chama a API de verdade ---------------------------

import json
from types import SimpleNamespace

import pytest

from base import leitor_release as lr
from scripts.rotular_com_ia import TetoPassado

TEXTO_DO_RELEASE = (
    "Receita líquida de R$ 1.234,5 milhões no 3T25. Lucro líquido de R$ 210 milhões."
)
RESPOSTA = {
    "linhas": [
        {"linha": "receita_liquida", "valor": 1234.5, "unidade": "milhoes", "periodo": "trimestre",
         "trecho": "Receita líquida de R$ 1.234,5 milhões", "pagina": 2},
        {"linha": "lucro_liquido_controladores", "valor": 999.0, "unidade": "milhoes",
         "periodo": "trimestre", "trecho": "Lucro líquido de R$ 210 milhões", "pagina": 2},
    ],
    "ajustes": [],
}  # fmt: skip


class _ClienteFalso:
    """Conta as chamadas; devolve sempre a mesma resposta."""

    def __init__(self, tokens=1000):
        self.criados = self.lotes = 0
        usage = SimpleNamespace(
            input_tokens=tokens, output_tokens=200,
            cache_creation_input_tokens=0, cache_read_input_tokens=0,
        )  # fmt: skip
        mensagem = SimpleNamespace(
            stop_reason="end_turn", usage=usage,
            content=[SimpleNamespace(type="text", text=json.dumps(RESPOSTA))],
        )  # fmt: skip

        def criar(**_):
            self.criados += 1
            return mensagem

        def lote(**_):
            self.lotes += 1
            return SimpleNamespace(id="lote_1")

        self.messages = SimpleNamespace(
            count_tokens=lambda **_: SimpleNamespace(input_tokens=tokens),
            create=criar,
            batches=SimpleNamespace(create=lote),
        )


def _achados(*protocolos):
    return pd.DataFrame(
        [
            _release("11.111.111/0001-11", "2025-09-30", "2025-11-05", p)
            for p in protocolos
        ],
        columns=list(releases.COLUNAS),
    )


def _com_texto(tmp_path, protocolo, texto=TEXTO_DO_RELEASE):
    ler_releases.guardar_texto(tmp_path, protocolo, texto, "sha-do-pdf")


def test_nada_e_enviado_se_passa_do_teto(tmp_path):
    _com_texto(tmp_path, "a")
    cliente = _ClienteFalso(tokens=1_000_000)
    with pytest.raises(TetoPassado):
        ler_releases.enviar(cliente, _achados("a"), tmp_path, teto=0.001)
    with pytest.raises(TetoPassado):
        ler_releases.piloto(cliente, _achados("a"), tmp_path, n=1, teto=0.001)
    assert cliente.lotes == 0 and cliente.criados == 0


def test_reusa_resposta_guardada(tmp_path):
    _com_texto(tmp_path, "a")
    _com_texto(tmp_path, "b")  # o mesmo texto: a mesma entrada (texto + guia + modelo)
    cliente = _ClienteFalso()
    achados = _achados("a", "b")
    ler_releases.piloto(cliente, achados, tmp_path, n=2, teto=1.0)
    assert cliente.criados == 1  # o segundo reaproveitou a leitura do primeiro
    ler_releases.piloto(cliente, achados, tmp_path, n=2, teto=1.0)
    assert cliente.criados == 1  # e nada pendente não chama a API
    assert len(ler_releases.ler_leituras(tmp_path, lr.MODELO)) == 2


def test_linhagem_completa(tmp_path):
    _com_texto(tmp_path, "a")
    ler_releases.piloto(_ClienteFalso(), _achados("a"), tmp_path, n=1, teto=1.0)
    registro = ler_releases.ler_leituras(tmp_path, lr.MODELO)["a"]
    for campo in (
        "protocolo", "sha256_do_documento", "modelo", "versao_do_guia", "lido_em",
        "hash_da_entrada", "resposta_bruta", "link",
    ):  # fmt: skip
        assert registro[campo], campo
    assert registro["sha256_do_documento"] == "sha-do-pdf"
    assert registro["hash_da_entrada"] == lr.chave_da_entrada(TEXTO_DO_RELEASE)
    # só o par que o código provou no texto fica; o outro vai para os descartes
    assert [linha["valor"] for linha in registro["linhas"]] == [1234.5]
    assert registro["linhas"][0]["trecho"] and registro["linhas"][0]["pagina"] == 2
    assert registro["descartes"][0]["motivo"] == lr.NUMERO_FORA_DO_TRECHO


def test_pdf_ilegivel_vai_para_a_fila_de_revisao(tmp_path, monkeypatch):
    monkeypatch.setattr(ler_releases.leitura, "texto_do_pdf", lambda _: "")
    pdf = b"%PDF-1.4\n%%EOF"
    ler_releases.baixar(_achados("a"), tmp_path, maximo=5, obter=lambda _: pdf, pausa=0)
    cliente = _ClienteFalso()
    ler_releases.piloto(cliente, _achados("a"), tmp_path, n=1, teto=1.0)
    assert cliente.criados == 0
    assert ler_releases.fila_de_revisao(_achados("a"), tmp_path) == ["a"]


def test_so_baixa_link_https_da_cvm():
    assert ler_releases.link_da_cvm("https://www.rad.cvm.gov.br/ENET/x.pdf")
    for fora in (
        "http://www.rad.cvm.gov.br/x",
        "https://cvm.gov.br.evil.com/x",
        "https://evil.com/x",
        "file:///c:/x",
    ):
        assert not ler_releases.link_da_cvm(fora)


def test_cliente_da_vitrine_exige_a_chave_propria(monkeypatch):
    from scripts import ler_releases

    monkeypatch.delenv(ler_releases.VARIAVEL_DA_CHAVE, raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-dos-rotulos")
    with pytest.raises(SystemExit, match="ANTHROPIC_API_KEY_VITRINE"):
        ler_releases.cliente_da_vitrine()
    monkeypatch.setenv(ler_releases.VARIAVEL_DA_CHAVE, "sk-ant-da-vitrine")
    assert ler_releases.cliente_da_vitrine().api_key == "sk-ant-da-vitrine"
