"""O comando que roda a extração de M&A na amostra de ouro: teto antes de gastar, lote, medida."""

import json
from types import SimpleNamespace

import pandas as pd
import pytest

from base import ma_extracao as mx
from base import ma_multiplos as mm
from scripts import extrair_ma
from scripts.rotular_com_ia import TetoPassado

TEXTO = "A Alfa S.A. comunica a aquisição da Beta Ltda. pelo valor de R$ 10 milhões."
RESPOSTA = {
    "tipo": "AQ_CONTROLE", "etapa": "ASSINATURA", "trecho_do_tipo": "comunica a aquisição da Beta",
    "partes": [{"nome": "Beta Ltda.", "papel": "alvo", "participacao_depois": None,
                "trecho": "aquisição da Beta Ltda."}],
    "valores": [{"campo": "valor_participacao", "valor": 10, "unidade": "milhoes",
                 "moeda": "BRL", "trecho": "pelo valor de R$ 10 milhões"}],
    "datas": [], "forma_pagamento": "nao_informado",
}  # fmt: skip


class _ClienteFalso:
    """Guarda o lote enviado e devolve a mesma resposta para cada pedido."""

    def __init__(self):
        self.enviados: list[dict] = []
        usage = SimpleNamespace(
            input_tokens=3000, output_tokens=500,
            cache_creation_input_tokens=0, cache_read_input_tokens=0,
        )  # fmt: skip
        mensagem = SimpleNamespace(
            stop_reason="end_turn", usage=usage,
            content=[SimpleNamespace(type="text", text=json.dumps(RESPOSTA))],
        )  # fmt: skip

        def criar(requests):
            self.enviados = requests
            return SimpleNamespace(id="lote_1")

        def resultados(_id):
            return [
                SimpleNamespace(
                    custom_id=r["custom_id"],
                    result=SimpleNamespace(type="succeeded", message=mensagem),
                )
                for r in self.enviados
            ]

        self.messages = SimpleNamespace(
            batches=SimpleNamespace(
                create=criar,
                retrieve=lambda _id: SimpleNamespace(processing_status="ended"),
                results=resultados,
            )
        )


@pytest.fixture
def amostra(tmp_path):
    textos = tmp_path / "textos"
    textos.mkdir()
    (textos / "P-1.txt").write_text(TEXTO, encoding="utf-8")
    (textos / "P-2.txt").write_text(
        "", encoding="utf-8"
    )  # documento sem texto: fica de fora
    ouro = pd.DataFrame(
        {"Protocolo_Entrega": ["P-1", "P-2", "P-3"], "Data_Entrega": ["2024-05-02"] * 3,
         "confere_tiago": ["ok"] * 3, "tipo_conferido": ["AQ_CONTROLE"] * 3,
         "alvo": ["Beta", None, None], "comprador": [None] * 3, "vendedor": [None] * 3,
         "valor": ["R$ 10 milhões", None, None]}
    )  # fmt: skip
    arquivo = tmp_path / "ouro.csv"
    ouro.to_csv(arquivo, sep=";", index=False, encoding="utf-8-sig")
    return SimpleNamespace(textos=textos, ouro=arquivo, saida=tmp_path / "saida")


def test_documentos_sao_os_da_amostra_com_texto(amostra):
    documentos = extrair_ma.documentos(amostra.ouro, amostra.textos)
    assert [d.protocolo for d in documentos] == ["P-1"]
    assert str(documentos[0].publico_em) == "2024-05-02"


def test_enviar_recusa_quando_a_estimativa_passa_do_teto(amostra):
    cliente = _ClienteFalso()
    with pytest.raises(TetoPassado):
        extrair_ma.enviar(
            cliente, amostra.ouro, amostra.textos, amostra.saida, mx.MODELO, teto=0.0
        )
    assert cliente.enviados == []


def test_enviar_buscar_e_medir_sem_repetir_o_que_ja_foi_lido(amostra):
    cliente = _ClienteFalso()
    args = (amostra.ouro, amostra.textos, amostra.saida, mx.MODELO)
    assert extrair_ma.enviar(cliente, *args, teto=1.0) == "lote_1"
    assert [r["custom_id"] for r in cliente.enviados] == ["P-1"]
    with pytest.raises(RuntimeError):  # lote ainda não gravado
        extrair_ma.enviar(cliente, *args, teto=1.0)
    assert extrair_ma.buscar(cliente, amostra.saida, mx.MODELO) == 1
    assert extrair_ma.enviar(cliente, *args, teto=1.0) is None  # nada pendente

    manifesto = extrair_ma.ler_manifesto(amostra.saida, mx.MODELO)
    assert manifesto["gasto_em_dolares"] == pytest.approx(
        mx.custo_em_dolares(3000, 500, modelo=mx.MODELO)
    )
    resultado = extrair_ma.medir_modelo(
        amostra.ouro, amostra.textos, amostra.saida, mx.MODELO
    )
    placar = resultado.placar.set_index("campo")
    assert placar.loc["tipo", ["casos", "acertos"]].tolist() == [3, 1]
    assert placar.loc["valor", ["casos", "acertos"]].tolist() == [1, 1]
    assert resultado.lidos == 1
    assert resultado.custo_por_documento == pytest.approx(manifesto["gasto_em_dolares"])


def test_estimar_nao_precisa_de_chave(amostra, monkeypatch, capsys):
    monkeypatch.delenv(extrair_ma.VARIAVEL_DA_CHAVE, raising=False)
    assert extrair_ma.main(["estimar", "--ouro", str(amostra.ouro), "--textos",
                            str(amostra.textos), "--saida", str(amostra.saida)]) == 0  # fmt: skip
    assert "1 documentos" in capsys.readouterr().out


def test_enviar_sem_a_chave_propria_para_antes_de_chamar(amostra, monkeypatch):
    monkeypatch.delenv(extrair_ma.VARIAVEL_DA_CHAVE, raising=False)
    with pytest.raises(SystemExit):
        extrair_ma.main(["enviar", "--ouro", str(amostra.ouro), "--textos", str(amostra.textos),
                         "--saida", str(amostra.saida), "--teto-dolares", "1"])  # fmt: skip


def test_operacoes_da_amostra_sem_duplicadas(tmp_path):
    # a alvo e a compradora publicam a mesma aquisição no mesmo dia: uma operação só
    textos, saida = tmp_path / "textos", tmp_path / "saida"
    textos.mkdir()
    saida.mkdir()
    for protocolo in ("P-1", "P-4"):
        (textos / f"{protocolo}.txt").write_text(TEXTO, encoding="utf-8")
    ouro = pd.DataFrame(
        {"Protocolo_Entrega": ["P-1", "P-4"], "Data_Entrega": ["2024-05-02"] * 2,
         "confere_tiago": ["ok"] * 2, "tipo_conferido": ["AQ_CONTROLE"] * 2,
         "alvo": ["Beta Ltda.", "Beta"], "comprador": ["Alfa S.A.", None],
         "vendedor": [None] * 2, "valor": [None] * 2}
    )  # fmt: skip
    arquivo = tmp_path / "ouro.csv"
    ouro.to_csv(arquivo, sep=";", index=False, encoding="utf-8-sig")
    registros = [
        {"protocolo": p, "resposta_bruta": json.dumps(RESPOSTA)} for p in ("P-1", "P-4")
    ]
    (saida / f"leituras-{mx.CONFERENTE}.jsonl").write_text(
        "\n".join(json.dumps(r) for r in registros), encoding="utf-8"
    )
    tabela, ligacoes, comparacao = extrair_ma.operacoes_da_amostra(
        arquivo, textos, saida, mx.CONFERENTE
    )
    assert tabela[["operacao", "documentos"]].to_dict("records") == [
        {"operacao": "P-1", "documentos": 2}
    ]
    assert ligacoes["operacao"].tolist() == ["P-1", "P-1"]
    assert comparacao == {
        "no_gabarito": [["P-1", "P-4"]],
        "separadas": [],
        "juntadas": [],
    }
    texto = extrair_ma.relatorio_das_operacoes(mx.CONFERENTE, tabela, comparacao)
    assert "2 documentos de operação viraram 1 operações" in texto


def test_multiplos_da_amostra_pede_so_as_emissoras_e_os_anos_do_anuncio(
    tmp_path, monkeypatch
):
    textos, saida = tmp_path / "textos", tmp_path / "saida"
    textos.mkdir()
    saida.mkdir()
    (textos / "P-1.txt").write_text(TEXTO, encoding="utf-8")
    ouro = pd.DataFrame(
        {"Protocolo_Entrega": ["P-1"], "Data_Entrega": ["2024-05-02"], "confere_tiago": ["ok"],
         "CNPJ_Companhia": ["11.111.111/0001-11"], "Nome_Companhia": ["BETA LTDA"],
         "tipo_conferido": ["AQ_CONTROLE"], "alvo": ["Beta Ltda."], "comprador": [None],
         "vendedor": [None], "valor": [None]}
    )  # fmt: skip
    arquivo = tmp_path / "ouro.csv"
    ouro.to_csv(arquivo, sep=";", index=False, encoding="utf-8-sig")
    (saida / f"leituras-{mx.CONFERENTE}.jsonl").write_text(
        json.dumps({"protocolo": "P-1", "resposta_bruta": json.dumps(RESPOSTA)}),
        encoding="utf-8",
    )
    fontes = []
    monkeypatch.setattr(
        extrair_ma,
        "originais_mais_recentes",
        lambda _, fonte: fontes.append(fonte) or [],
    )
    tabela = extrair_ma.multiplos_da_amostra(
        None, arquivo, textos, saida, mx.CONFERENTE
    )  # type: ignore[arg-type]
    assert fontes == ["cvm-hist-dfp", "cvm-hist-itr"]
    # a leitura só traz o valor de uma participação: a operação fica, com o motivo
    assert tabela[["alvo_cnpj", "motivo"]].to_dict("records") == [
        {"alvo_cnpj": "11.111.111/0001-11", "motivo": mm.SO_PARTICIPACAO}
    ]
    texto = extrair_ma.relatorio_dos_multiplos(mx.CONFERENTE, tabela)
    assert "0 de 1 operações com algum múltiplo" in texto
