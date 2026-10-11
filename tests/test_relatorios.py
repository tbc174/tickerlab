"""Relatórios em PDF: abrem, batem com os números do site, trazem o aviso e respeitam o plano."""

import uuid
from datetime import UTC, datetime, timedelta
from io import BytesIO

import pandas as pd
import pytest
from pypdf import PdfReader

from src import graficos_pdf as gp
from src import indicadores as ind
from src import relatorios
from src.banco import dados_do_usuario as repo
from src.banco import usuarios as contas
from src.carteiras import ESTRATEGIAS_DE_CARTEIRA
from src.comparacao import alinhar_fechamentos
from src.conformidade import apagar_conta, exportar_meus_dados
from src.planos import LimiteDoPlanoError, conferir_relatorio

AGORA = datetime(2026, 10, 11, 15, 0, tzinfo=UTC)


def _dados(ticker):
    return pd.read_csv(f"dados_de_exemplo/{ticker}.csv", index_col=0, parse_dates=True)


def _texto(pdf: bytes) -> str:
    assert pdf.startswith(b"%PDF")
    leitor = PdfReader(BytesIO(pdf))
    texto = " ".join(pagina.extract_text() for pagina in leitor.pages)
    return " ".join(texto.split())  # as frases quebram de linha no PDF


def _paginas(pdf: bytes) -> int:
    return len(PdfReader(BytesIO(pdf)).pages)


# --- os PDFs --------------------------------------------------------------------------------
def test_relatorio_do_ativo_bate_com_os_numeros_do_site():
    dados = _dados("PETR4.SA")
    pdf = relatorios.relatorio_do_ativo("PETR4.SA", dados, 0.0, "5 anos", exemplo=True)
    texto = _texto(pdf)
    retorno = ind.calcular_retorno_diario(dados["Close"].dropna())
    total = ind.calcular_retorno_acumulado(retorno).iloc[-1]
    assert gp.pct_br(total, 1, sinal=True) in texto  # o mesmo número da Visão geral
    assert "▲" in texto or "▼" in texto  # alta e queda sempre com seta
    assert "nada aqui é recomendação de investimento" in texto
    assert "Glossário" in texto and "Índice de Sharpe" in texto
    assert "de exemplo" in texto  # avisa que os dados são de exemplo
    assert "**" not in texto  # o Markdown do site não vaza para o PDF
    assert _paginas(pdf) >= 2


def test_relatorio_de_comparacao_tem_todos_os_ativos():
    alinhado, _ = alinhar_fechamentos(
        {t: _dados(t)["Close"] for t in ("PETR4.SA", "VALE3.SA", "_BVSP")}
    )
    texto = _texto(relatorios.relatorio_de_comparacao(alinhado))
    for ticker in ("PETR4.SA", "VALE3.SA", "_BVSP"):
        assert ticker in texto
    assert "Base 100" in texto  # o termo do glossário (o título do gráfico é imagem)


def test_relatorio_de_backtest_compara_com_comprar_e_segurar_e_avisa_da_sorte():
    texto = _texto(
        relatorios.relatorio_de_backtest(
            "PETR4.SA", _dados("PETR4.SA"), "Cruzamento de médias"
        )
    )
    assert "Comprar e segurar" in texto and "Cruzamento de médias" in texto
    assert "pode ser sorte" in texto


def test_relatorio_de_carteira_mostra_o_giro_legivel():
    fechamentos = pd.DataFrame(
        {t: _dados(t)["Close"] for t in ("PETR4.SA", "VALE3.SA", "ITUB4.SA")}
    ).dropna()
    nome = list(ESTRATEGIAS_DE_CARTEIRA)[1]
    texto = _texto(relatorios.relatorio_de_carteira(fechamentos, nome))
    assert "× o capital" in texto and "Cada ativo sozinho" in texto


def test_cada_relatorio_tem_um_nome():
    assert set(relatorios.NOMES_DOS_RELATORIOS) == set(repo.TIPOS_DE_RELATORIO)


# --- limites do plano -----------------------------------------------------------------------
def test_gratuito_gera_so_o_do_ativo_e_ate_3_por_dia():
    conferir_relatorio("gratuito", "ativo", 2)
    with pytest.raises(LimiteDoPlanoError, match="3 relatórios"):
        conferir_relatorio("gratuito", "ativo", 3)
    with pytest.raises(LimiteDoPlanoError, match="plano Pro"):
        conferir_relatorio("gratuito", "backtest", 0)


def test_pro_gera_todos_sem_limite():
    for tipo in repo.TIPOS_DE_RELATORIO:
        conferir_relatorio("pro", tipo, 10_000)


# --- banco: contagem, isolamento e LGPD -----------------------------------------------------
def _usuario(conexao, sub):
    usuario, _ = contas.entrar(conexao, sub, f"{sub}@exemplo.com")
    return usuario.id


def test_contagem_e_das_ultimas_24_horas_e_de_cada_usuario(banco):
    with banco.begin() as conexao:
        ana, bia = _usuario(conexao, "ana"), _usuario(conexao, "bia")
        repo.registrar_relatorio(
            conexao, ana, "ativo", agora=AGORA - timedelta(hours=30)
        )
        repo.registrar_relatorio(
            conexao, ana, "ativo", agora=AGORA - timedelta(hours=2)
        )
        repo.registrar_relatorio(
            conexao, bia, "ativo", agora=AGORA - timedelta(hours=1)
        )
        assert (
            repo.contar_relatorios_recentes(conexao, ana, AGORA) == 1
        )  # o de 30 h não conta
        assert repo.contar_relatorios_recentes(conexao, bia, AGORA) == 1


def test_o_limite_e_conferido_antes_de_registrar(banco):
    with banco.begin() as conexao:
        ana = _usuario(conexao, "ana")
        for _ in range(3):
            repo.registrar_relatorio(
                conexao, ana, "ativo", plano="gratuito", agora=AGORA
            )
        with pytest.raises(LimiteDoPlanoError):
            repo.registrar_relatorio(
                conexao, ana, "ativo", plano="gratuito", agora=AGORA
            )
        assert (
            repo.contar_relatorios_recentes(conexao, ana, AGORA) == 3
        )  # o recusado não entrou


def test_tipo_desconhecido_e_recusado(banco):
    with banco.begin() as conexao, pytest.raises(repo.DadosInvalidosError):
        repo.registrar_relatorio(conexao, _usuario(conexao, "ana"), "qualquer")


def test_relatorios_entram_na_exportacao_e_somem_com_a_conta(banco):
    with banco.begin() as conexao:
        ana = _usuario(conexao, "ana")
        repo.registrar_relatorio(conexao, ana, "ativo", agora=AGORA)
        exportado = exportar_meus_dados(conexao, ana)
        assert [r["tipo"] for r in exportado["relatorios_em_pdf"]] == ["ativo"]
        assert apagar_conta(conexao, ana)
        assert repo.listar_relatorios(conexao, ana) == []
        assert repo.contar_relatorios_recentes(conexao, uuid.uuid4(), AGORA) == 0


# --- Report Studio: seções, modelos, estilos e prévia ----------------------------------------
def _titulos_numerados(pdf: bytes) -> list[str]:
    """Os títulos de seção, na ordem, pelos marcadores (outline) do PDF."""
    return [item.title for item in PdfReader(BytesIO(pdf)).outline]


def test_todo_tipo_tem_limites_obrigatorio_e_executivo_valido():
    for tipo, secoes in relatorios.SECOES.items():
        chaves = [s.chave for s in secoes]
        assert len(chaves) == len(set(chaves))
        assert [s.chave for s in secoes if s.obrigatoria] == ["limites"]
        executivo = relatorios.secoes_do_modelo(tipo, relatorios.EXECUTIVO)
        assert set(executivo) <= set(chaves) and "limites" in executivo
        assert relatorios.secoes_do_modelo(tipo, "qualquer") == chaves


def test_normalizar_secoes_tira_repetidas_e_desconhecidas_e_devolve_a_obrigatoria():
    assert relatorios.normalizar_secoes(
        "ativo", ["preco", "preco", "xyz", "resumo"]
    ) == [
        "preco",
        "resumo",
        "limites",
    ]
    assert relatorios.normalizar_secoes("ativo", None) == relatorios.secoes_do_modelo(
        "ativo", relatorios.COMPLETO
    )


def test_ordem_das_secoes_no_pdf_segue_a_escolha_e_a_capa_tem_o_sumario():
    config = relatorios.Configuracao(secoes=("preco", "resumo"), modelo="personalizado")
    pdf = relatorios.relatorio_do_ativo("PETR4.SA", _dados("PETR4.SA"), config=config)
    assert _titulos_numerados(pdf) == [
        "1. Preço no período",
        "2. Resumo executivo",
        "3. Limites e cuidados",  # a obrigatória volta sozinha
    ]
    capa = PdfReader(BytesIO(pdf)).pages[0].extract_text()
    assert "NESTE RELATÓRIO" in capa and "Limites e cuidados" in capa


def test_executivo_e_curto_e_completo_tem_tudo():
    dados = _dados("PETR4.SA")
    exec_ = relatorios.relatorio_do_ativo(
        "PETR4.SA", dados,
        config=relatorios.Configuracao(
            secoes=tuple(relatorios.secoes_do_modelo("ativo", "executivo"))
        ),
    )  # fmt: skip
    completo = relatorios.relatorio_do_ativo("PETR4.SA", dados)
    assert 2 <= _paginas(exec_) <= 4
    assert len(_titulos_numerados(completo)) == len(relatorios.SECOES["ativo"])
    assert "Metodologia e reprodutibilidade" in _texto(completo)
    assert "Metodologia" not in _texto(exec_)


def test_aviso_do_backtest_continua_mesmo_sem_as_outras_secoes():
    config = relatorios.Configuracao(secoes=("curva",))
    pdf = relatorios.relatorio_de_backtest(
        "PETR4.SA", _dados("PETR4.SA"), "Cruzamento de médias", config=config
    )
    assert "pode ser sorte" in _texto(pdf)


def test_estilo_muda_as_cores_mas_nao_os_numeros():
    dados = _dados("PETR4.SA")
    textos = {}
    for chave in ("research", "terminal", "institucional"):
        pdf = relatorios.relatorio_do_ativo(
            "PETR4.SA", dados, gerado_em=AGORA,
            config=relatorios.Configuracao(estilo=chave),
        )  # fmt: skip
        textos[chave] = (
            _texto(pdf)
            .replace("Research · Claro", "X")
            .replace("Terminal · Escuro", "X")
            .replace("Institucional · Branco e azul", "X")
        )
    assert textos["research"] == textos["terminal"] == textos["institucional"]


def test_estilo_desconhecido_volta_ao_padrao():
    from src import estilos_pdf

    assert estilos_pdf.estilo("nao-existe") is estilos_pdf.PADRAO
    assert estilos_pdf.estilo(None) is estilos_pdf.PADRAO
    assert estilos_pdf.TERMINAL.escuro and not estilos_pdf.RESEARCH.escuro


def test_resumo_executivo_so_usa_numeros_do_relatorio():
    dados = _dados("PETR4.SA")
    achados = relatorios.achados_do_ativo("PETR4.SA", dados["Close"].dropna())
    assert 3 <= len(achados) <= 5
    texto = _texto(relatorios.relatorio_do_ativo("PETR4.SA", dados))
    retorno = ind.calcular_retorno_diario(dados["Close"].dropna())
    total = ind.calcular_retorno_acumulado(retorno).iloc[-1]
    assert gp.pct_br(total, 1, sinal=True) in achados[0]
    assert gp.pct_br(total, 1, sinal=True) in texto
    proibidas = ("compre", "venda agora", "recomendamos", "vai subir", "vai cair")
    assert not any(p in " ".join(achados).lower() for p in proibidas)


def test_etapas_reais_sao_avisadas_em_ordem():
    etapas = []
    relatorios.relatorio_do_ativo(
        "PETR4.SA", _dados("PETR4.SA"), ao_avancar=etapas.append
    )
    assert etapas == ["Compondo seções", "Criando PDF"]


def test_previa_e_o_proprio_pdf_em_imagens():
    from src import previa_pdf

    pdf = relatorios.relatorio_do_ativo("PETR4.SA", _dados("PETR4.SA"))
    imagens = previa_pdf.paginas_em_png(pdf, 2, largura_px=300)
    assert len(imagens) == 2 and all(i.startswith(b"\x89PNG") for i in imagens)
    assert int.from_bytes(imagens[0][16:20], "big") == 300
    assert previa_pdf.contar_paginas(pdf) == _paginas(pdf)
    assert len(previa_pdf.paginas_em_png(pdf)) == _paginas(pdf)


# --- biblioteca no banco -----------------------------------------------------------------------
def test_biblioteca_guarda_parametros_e_cada_um_ve_so_os_seus(banco):
    with banco.begin() as conexao:
        ana, bia = _usuario(conexao, "ana"), _usuario(conexao, "bia")
        id_ana = repo.registrar_relatorio(
            conexao, ana, "ativo", titulo="PETR4", parametros={"ticker": "PETR4.SA"},
            agora=AGORA,
        )  # fmt: skip
        repo.registrar_relatorio(conexao, bia, "ativo", titulo="VALE3", agora=AGORA)
        (item,) = repo.biblioteca_de_relatorios(conexao, ana)
        assert item.id == id_ana and item.parametros == {"ticker": "PETR4.SA"}
        # bia não exclui o relatório da ana
        assert not repo.excluir_relatorio(conexao, bia, id_ana)
        assert repo.biblioteca_de_relatorios(conexao, ana)


def test_excluir_apaga_titulo_e_parametros_mas_o_limite_continua(banco):
    with banco.begin() as conexao:
        ana = _usuario(conexao, "ana")
        rid = repo.registrar_relatorio(
            conexao, ana, "ativo", titulo="PETR4", parametros={"ticker": "PETR4.SA"},
            agora=AGORA,
        )  # fmt: skip
        assert repo.excluir_relatorio(conexao, ana, rid, agora=AGORA)
        assert not repo.excluir_relatorio(conexao, ana, rid)  # já excluído
        assert repo.biblioteca_de_relatorios(conexao, ana) == []
        assert repo.contar_relatorios_recentes(conexao, ana, AGORA) == 1
        exportado = exportar_meus_dados(conexao, ana)["relatorios_em_pdf"]
        assert exportado[0]["titulo"] is None and exportado[0]["parametros"] is None
        assert exportado[0]["excluido_da_biblioteca_em"]


def test_parametros_grandes_demais_sao_recusados(banco):
    with banco.begin() as conexao, pytest.raises(repo.DadosInvalidosError):
        repo.registrar_relatorio(
            conexao, _usuario(conexao, "ana"), "ativo", parametros={"x": "a" * 30_000}
        )


def test_migracao_0006_vai_e_volta_sem_perder_os_relatorios(tmp_path):
    import sqlalchemy as sa

    from src.banco.conexao import criar_engine, migrar_para

    url = f"sqlite:///{(tmp_path / 'm.sqlite').as_posix()}"
    migrar_para("head", url=url)
    motor = criar_engine(url)
    with motor.begin() as conexao:
        ana = _usuario(conexao, "ana")
        repo.registrar_relatorio(conexao, ana, "ativo", titulo="T", agora=AGORA)
    migrar_para("-2", url=url)  # volta para a 0005 (desfaz a 0007 e a 0006)
    colunas = {
        c["name"] for c in sa.inspect(criar_engine(url)).get_columns("relatorios")
    }
    assert "titulo" not in colunas and "parametros" not in colunas
    migrar_para("head", url=url)
    with criar_engine(url).connect() as conexao:
        assert repo.contar_relatorios_recentes(conexao, ana, AGORA) == 1
    motor.dispose()
