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


def test_documento_antigo_vai_ao_lote_com_o_nome_seguro_e_volta_com_o_link(tmp_path):
    # o custom_id da Batch API só aceita letras, números, _ e -; o protocolo antigo é um link
    link = (
        "https://www.rad.cvm.gov.br/ENET/frmDownloadDocumento.aspx?Tela=ext&descTipo=IPE"
        "&CodigoInstituicao=1&numProtocolo=25694&numSequencia=0&numVersao=0"
    )
    textos = tmp_path / "textos"
    textos.mkdir()
    (textos / "cvm-25694-0-0.txt").write_text(TEXTO, encoding="utf-8")
    ouro = tmp_path / "ouro.csv"
    pd.DataFrame({"Protocolo_Entrega": [link], "Data_Entrega": ["2004-02-11"]}).to_csv(
        ouro, sep=";", index=False, encoding="utf-8-sig"
    )
    cliente, saida = _ClienteFalso(), tmp_path / "saida"
    extrair_ma.enviar(cliente, ouro, textos, saida, mx.MODELO, teto=1.0)
    assert [r["custom_id"] for r in cliente.enviados] == ["cvm-25694-0-0"]
    assert extrair_ma.buscar(cliente, saida, mx.MODELO) == 1
    assert list(extrair_ma.ler_leituras(saida, mx.MODELO)) == [link]
    assert extrair_ma.enviar(cliente, ouro, textos, saida, mx.MODELO, teto=1.0) is None


# --- modo base inteira ---------------------------------------------------------------------------


@pytest.fixture
def base(tmp_path):
    """Três candidatos (um fato relevante com tipo, um genérico, um comunicado), um sem texto e uma
    reentrega do mesmo protocolo."""
    textos = tmp_path / "textos"
    textos.mkdir()
    for nome in ("B-1", "B-2", "B-3"):
        (textos / f"{nome}.txt").write_text(TEXTO, encoding="utf-8")
    (textos / "B-4.sem_texto").write_text("", encoding="utf-8")
    linhas = [
        ("B-1", 1, "Fato Relevante", "assunto", "2024-05-02"),
        ("B-2", 1, "Fato Relevante", "assunto_generico", "2025-01-10"),
        ("B-3", 1, "Comunicado ao Mercado", "assunto", "2025-06-01"),
        ("B-4", 1, "Fato Relevante", "assunto", "2025-07-01"),
        ("B-1", 2, "Fato Relevante", "assunto", "2024-05-09"),
    ]
    candidatos = pd.DataFrame(
        linhas, columns=["protocolo", "versao", "categoria", "evidencia", "publico_em"]
    )
    candidatos["publico_em"] = pd.to_datetime(candidatos["publico_em"])
    arquivo = tmp_path / "candidatos.parquet"
    candidatos.to_parquet(arquivo)
    return SimpleNamespace(textos=textos, candidatos=arquivo, saida=tmp_path / "saida")


def test_documentos_da_base_seguem_a_ordem_da_coleta_e_pulam_o_sem_texto(base):
    documentos = extrair_ma.documentos_da_base(base.candidatos, base.textos)
    # com tipo (B-1, reentrega única) → genérico (B-2) → comunicado (B-3); B-4 não tem texto
    assert [d.protocolo for d in documentos] == ["B-1", "B-2", "B-3"]
    assert str(documentos[0].publico_em) == "2024-05-09"  # a reentrega mais nova


def test_pendentes_da_base_respeitam_o_limite_e_o_que_ja_foi_lido(base):
    args = (base.candidatos, base.textos, base.saida, mx.MODELO)
    assert [d.protocolo for d in extrair_ma.pendentes_da_base(*args, limite=2)] == [
        "B-1",
        "B-2",
    ]
    cliente = _ClienteFalso()
    extrair_ma.enviar_documentos(
        cliente,
        extrair_ma.pendentes_da_base(*args, limite=1),
        base.saida,
        mx.MODELO,
        1.0,
    )
    extrair_ma.buscar(cliente, base.saida, mx.MODELO)
    assert [d.protocolo for d in extrair_ma.pendentes_da_base(*args, limite=2)] == [
        "B-2",
        "B-3",
    ]


def test_base_enviar_recusa_quando_o_lote_passa_do_teto(base):
    cliente = _ClienteFalso()
    fila = extrair_ma.pendentes_da_base(
        base.candidatos, base.textos, base.saida, mx.MODELO, limite=3
    )
    with pytest.raises(TetoPassado):
        extrair_ma.enviar_documentos(cliente, fila, base.saida, mx.MODELO, teto=0.0)
    assert cliente.enviados == []


def test_teto_conta_o_que_o_manifesto_ja_gastou(base):
    cliente = _ClienteFalso()
    args = (base.candidatos, base.textos, base.saida, mx.MODELO)
    extrair_ma.enviar_documentos(
        cliente,
        extrair_ma.pendentes_da_base(*args, limite=1),
        base.saida,
        mx.MODELO,
        1.0,
    )
    extrair_ma.buscar(cliente, base.saida, mx.MODELO)
    gasto = extrair_ma.ler_manifesto(base.saida, mx.MODELO)["gasto_em_dolares"]
    seguinte = extrair_ma.pendentes_da_base(*args, limite=1)
    with pytest.raises(
        TetoPassado
    ):  # o teto cobre o que já foi gasto, não só o lote novo
        extrair_ma.enviar_documentos(
            cliente, seguinte, base.saida, mx.MODELO, teto=gasto
        )


def test_quantos_cabem_na_verba(base):
    fila = extrair_ma.documentos_da_base(base.candidatos, base.textos)
    um = mx.estimar_custo([fila[0].texto], mx.MODELO)
    assert extrair_ma.quantos_cabem(fila, mx.MODELO, 0.0) == 0
    assert extrair_ma.quantos_cabem(fila, mx.MODELO, um) == 1
    assert extrair_ma.quantos_cabem(fila, mx.MODELO, 100.0) == 3


def test_base_estimar_nao_precisa_de_chave_e_mostra_quantos_cabem(
    base, monkeypatch, capsys
):
    monkeypatch.delenv(extrair_ma.VARIAVEL_DA_CHAVE, raising=False)
    assert extrair_ma.main(["base-estimar", "--candidatos", str(base.candidatos), "--textos",
                            str(base.textos), "--saida", str(base.saida), "--limite", "2",
                            "--teto-dolares", "30"]) == 0  # fmt: skip
    saida = capsys.readouterr().out
    assert "2 documentos" in saida and "Cabem 2 no teto" in saida


def test_base_enviar_exige_limite_e_teto_e_a_chave_propria(base, monkeypatch):
    monkeypatch.delenv(extrair_ma.VARIAVEL_DA_CHAVE, raising=False)
    comum = ["base-enviar", "--candidatos", str(base.candidatos), "--textos",
             str(base.textos), "--saida", str(base.saida)]  # fmt: skip
    with pytest.raises(SystemExit):  # sem limite e sem teto: o argparse recusa
        extrair_ma.main(comum)
    with pytest.raises(
        SystemExit
    ):  # com os dois, mas sem a chave: para antes de chamar a API
        extrair_ma.main([*comum, "--limite", "1", "--teto-dolares", "1"])
