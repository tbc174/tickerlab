"""Registro de coletas (Radar, PR 1): cada arquivo baixado deixa uma linha, e o registro nunca
derruba a coleta."""

import hashlib
import logging
from datetime import UTC, datetime, timedelta

import pytest

from src.banco import coletas
from src.banco.coletas import com_registro, licenca_da_fonte, registrar, ultimas

URL = "https://dados.cvm.gov.br/arquivo.zip"


def _todas(banco):
    with banco.connect() as conexao:
        return ultimas(conexao)


def test_arquivo_baixado_fica_registrado_com_tamanho_e_sha256(banco):
    baixar = com_registro("cvm-eventos", lambda url: b"conteudo")
    assert baixar(URL) == b"conteudo"
    [linha] = _todas(banco)
    assert linha.fonte == "cvm-eventos"
    assert linha.url == URL
    assert linha.situacao == "ok"
    assert linha.bytes == len(b"conteudo")
    assert linha.sha256 == hashlib.sha256(b"conteudo").hexdigest()
    assert linha.licenca.startswith("ODbL")


def test_404_fica_registrado_como_nao_encontrado(banco):
    assert com_registro("sec-13f", lambda url: None)(URL) is None
    [linha] = _todas(banco)
    assert (linha.situacao, linha.bytes, linha.sha256) == ("nao_encontrado", None, None)


def test_erro_fica_registrado_e_segue_para_a_coleta(banco):
    def baixar(url):
        raise TimeoutError("demorou")

    with pytest.raises(TimeoutError):
        com_registro("cvm-cda", baixar)(URL)
    [linha] = _todas(banco)
    assert (linha.situacao, linha.detalhe) == ("falhou", "TimeoutError")


def test_os_outros_argumentos_chegam_a_funcao_de_baixar(banco):
    recebidos = []

    def baixar(url, cabecalhos=None):
        recebidos.append((url, cabecalhos))
        return b"x"

    com_registro("sec-eventos", baixar)(URL, cabecalhos={"User-Agent": "teste"})
    assert recebidos == [(URL, {"User-Agent": "teste"})]


def test_banco_fora_do_ar_nao_derruba_a_coleta(monkeypatch, caplog):
    monkeypatch.setattr(
        coletas, "obter_engine", lambda: (_ for _ in ()).throw(OSError("sem banco"))
    )
    with caplog.at_level(logging.ERROR, logger=coletas.__name__):
        assert com_registro("cvm-vlmo", lambda url: b"x")(URL) == b"x"
    assert "Falha ao registrar a coleta de cvm-vlmo" in caplog.text


@pytest.mark.parametrize(
    ("fonte", "comeco"),
    [
        ("cvm-documentos", "ODbL"),
        ("bcb-sgs", "ODbL"),
        ("yahoo-precos", "Uso pessoal: só interno"),
        ("iex", "Termos do IEX"),
        ("cftc-tff", "Obra do governo dos EUA"),
        ("rfb-cripto", "Dados abertos da Receita"),
        ("wiki-acessos", "CC0"),
        ("gdelt-cripto", "GDELT"),
        ("btc-no", "Blockchain pública"),
        ("kraken-ohlc", "Sem termo de dados de mercado"),
        ("mb-candles", "Sem termo de dados de mercado"),
        ("desconhecida", "Desconhecida"),
    ],
)
def test_licenca_vem_da_familia_da_fonte(fonte, comeco):
    assert licenca_da_fonte(fonte).startswith(comeco)


def test_ultimas_vem_da_mais_nova_e_filtram_pela_fonte(banco):
    agora = datetime(2026, 10, 12, 3, tzinfo=UTC)
    with banco.begin() as conexao:
        for horas, fonte in [(2, "cvm-eventos"), (0, "cvm-eventos"), (1, "sec-13f")]:
            registrar(
                conexao, fonte, URL, b"x", "ok", agora=agora - timedelta(hours=horas)
            )
    with banco.connect() as conexao:
        assert [r.fonte for r in ultimas(conexao)] == [
            "cvm-eventos",
            "sec-13f",
            "cvm-eventos",
        ]
        so_cvm = ultimas(conexao, fonte="cvm-eventos", quantas=1)
    assert [r.baixado_em.replace(tzinfo=UTC) for r in so_cvm] == [agora]


def test_url_e_detalhe_longos_sao_cortados(banco):
    with banco.begin() as conexao:
        registrar(conexao, "cvm-eventos", "h" * 2000, None, "falhou", "d" * 500)
    [linha] = _todas(banco)
    assert len(linha.url) == coletas.LIMITE_DA_URL
    assert len(linha.detalhe) == coletas.LIMITE_DO_DETALHE


def test_familias_do_arquivo_tem_licenca_e_as_com_dado_pessoal_sao_so_internas():
    assert "CGU" in licenca_da_fonte("cgu-ceis")
    assert "CNPJ" in licenca_da_fonte("rfb-cnpj")
    assert (
        licenca_da_fonte("rfb-cripto") == coletas.LICENCAS["rfb"]
    )  # a planilha de cripto não muda
    assert licenca_da_fonte("gleif-br").startswith("CC0")
    for fonte in ("cgu-ceis", "ibama-autos", "mte-lista-suja"):
        assert coletas.revenda_da_fonte(fonte) == coletas.SO_USO_INTERNO, fonte
    # só o rodapé CC BY-ND do site: perguntar a licença (ADR 0008, Emenda 1: não entra em modelo)
    assert coletas.revenda_da_fonte("pgfn-divida") == coletas.A_CONFIRMAR
    assert coletas.revenda_da_fonte("rfb-cnpj") == coletas.VENDAVEL_COM_ATRIBUICAO
    assert coletas.revenda_da_fonte("gleif-br") == coletas.VENDAVEL_COM_ATRIBUICAO
    assert coletas.revenda_da_fonte("termos-b3") == coletas.SO_USO_INTERNO


def test_b3_cita_a_politica_de_consumo_e_e_nao_comercial():
    # negócios do pregão: só pesquisa até a B3 autorizar por escrito (ADRs 0019 e 0073)
    assert "Política de Consumo" in licenca_da_fonte("b3-negocios")
    assert coletas.revenda_da_fonte("b3-negocios") == coletas.NAO_COMERCIAL
    assert coletas.revenda_da_fonte("b3-boletim-pr") == coletas.NAO_COMERCIAL


def test_registrar_arquivo_grande_usa_o_sha256_e_o_tamanho_ja_calculados(banco):
    agora = datetime(2026, 10, 14, 2, tzinfo=UTC)
    with banco.begin() as conexao:
        coletas.registrar_arquivo(
            conexao,
            "rfb-cnpj",
            URL,
            "a" * 64,
            6_000_000_000,
            "ok",
            "lm=x",
            agora,
            "bruto/x.zip",
        )
        coletas.registrar_arquivo(
            conexao, "rfb-cnpj", URL, None, None, "falhou", "Timeout", agora
        )
    with banco.connect() as conexao:
        ultima = coletas.ultima_coleta_ok(conexao, URL)
        assert coletas.ultima_coleta_ok(conexao, "https://outra") is None
    assert ultima is not None
    assert (ultima.sha256, ultima.bytes, ultima.detalhe) == (
        "a" * 64,
        6_000_000_000,
        "lm=x",
    )


def test_licencas_das_fontes_abertas_novas():
    assert "CCEE" in licenca_da_fonte("ccee-pld")
    assert "ANTT" in licenca_da_fonte("antt-pedagio")
    assert "Tesouro Nacional" in licenca_da_fonte("tesouro-br-divida")
    assert licenca_da_fonte("tesouro-eua-10a") == coletas.LICENCAS["tesouro"]
    assert coletas.revenda_da_fonte("ccee-pld") == coletas.VENDAVEL_COM_ATRIBUICAO
    assert coletas.revenda_da_fonte("tesouro-br-divida") == coletas.VENDAVEL_ODBL
    # a família "tesouro" sozinha é o Tesouro dos EUA: as fontes do Tesouro Nacional têm a sua
    for fonte in ("tesouro-br-direto", "tesouro-br-leiloes"):
        assert "Tesouro Nacional" in licenca_da_fonte(fonte)
        assert coletas.revenda_da_fonte(fonte) == coletas.VENDAVEL_ODBL


def test_licencas_da_previa_do_balanco():
    """Licença declarada no conjunto do dados.gov.br (lida em 14/10/2026), não o rodapé do site."""
    for fonte in (
        "anp-vendas-distribuidora",
        "anac-estatistico",
        "ans-beneficiarios",
        "ons-geracao-usina",
    ):
        assert "CC BY" in licenca_da_fonte(fonte)
        assert coletas.revenda_da_fonte(fonte) == coletas.VENDAVEL_COM_ATRIBUICAO
    assert "ANTT" in licenca_da_fonte("antt-siade")
    # Comex Stat: licença aberta sem nome; não vender antes da resposta do MDIC
    assert coletas.revenda_da_fonte("comexstat") == coletas.A_CONFIRMAR


def test_toda_licenca_cabe_na_coluna_do_registro():
    """A coluna `licenca` tem 80 caracteres: um texto maior derruba o registro (Comex, 14/10/2026)."""
    limite = coletas.coletas.c.licenca.type.length
    assert all(len(texto) <= limite for texto in coletas.LICENCAS.values())
    assert len(coletas.SEM_LICENCA_CONHECIDA) <= limite
    assert "SAMP sem CPF" in licenca_da_fonte("aneel-samp")
    assert coletas.revenda_da_fonte("anatel-acessos") == coletas.VENDAVEL_COM_ATRIBUICAO
    assert coletas.revenda_da_fonte("bcb-pix-chaves") == coletas.VENDAVEL_ODBL


def test_coleta_registra_a_versao_do_codigo(banco, monkeypatch):
    """Série 3, PR 3 (exigência 13 da ADR 0055): cada arquivo registrado diz qual commit o baixou."""
    from src import versao_do_codigo as vc

    monkeypatch.setenv(vc.VARIAVEL, "587cb6c4d2e1f0a9b8c7d6e5f4a3b2c1d0e9f8a7")
    com_registro("cvm-eventos", lambda url: b"conteudo")(URL)
    [linha] = _todas(banco)
    assert linha.versao_do_codigo == "587cb6c4d2e1f0a9b8c7d6e5f4a3b2c1d0e9f8a7"


def test_migracao_da_versao_do_codigo_sobe_e_desce(tmp_path):
    import sqlalchemy as sa

    from src.banco.conexao import criar_engine, desfazer_ate, migrar_para

    url = f"sqlite:///{(tmp_path / 'm.sqlite').as_posix()}"
    migrar_para("head", url=url)
    motor = criar_engine(url)

    def colunas() -> set[str]:
        return {c["name"] for c in sa.inspect(motor).get_columns("coletas")}

    try:
        assert "versao_do_codigo" in colunas()
        desfazer_ate("0035", url=url)
        assert "versao_do_codigo" not in colunas()
        migrar_para("head", url=url)
        assert "versao_do_codigo" in colunas()
    finally:
        motor.dispose()


def test_versoes_guardadas_sem_ler_e_ausencia_antes_da_primeira(banco):
    """A data em que cada informe apareceu (`base/publicacao.py`) sai das versões guardadas."""
    from src import acervo

    dia = datetime(2026, 11, 1, 5, 0, tzinfo=UTC)
    with banco.begin() as conexao:
        registrar(conexao, "cvm-fidc-recente", URL, None, "nao_encontrado", agora=dia)
        for n, conteudo in enumerate((b"v1", b"v1", b"v2")):
            quando = dia + timedelta(days=n + 1)
            caminho = acervo.guardar_original("cvm-fidc-recente", URL, conteudo, quando)
            registrar(
                conexao, "cvm-fidc-recente", URL, conteudo, "ok", None, quando, caminho
            )
    with banco.connect() as conexao:
        versoes = coletas.versoes_guardadas(conexao, URL)
        assert [v.sha256 for v in versoes] == [
            hashlib.sha256(b"v1").hexdigest(),
            hashlib.sha256(b"v2").hexdigest(),
        ]  # a repetida não conta
        assert acervo.ler_original(versoes[1].caminho) == b"v2"
        assert coletas.ausente_antes(conexao, URL, versoes[0].baixado_em)
        assert not coletas.ausente_antes(conexao, URL, dia)
        assert coletas.versoes_guardadas(conexao, URL + "x") == []


def test_marca_do_tce_pr_e_vendavel_com_atribuicao():
    # regras de utilização do PIT: "livre para qualquer finalidade ou atividade" (lidas em 16/10/2026)
    for fonte in ("tce-pr", "tce-pr-pit", "tce-pr-despesa"):
        assert coletas.revenda_da_fonte(fonte) == coletas.VENDAVEL_COM_ATRIBUICAO, fonte
        assert "TCE-PR" in licenca_da_fonte(fonte)
    assert (
        coletas.revenda_da_fonte("tce-rs-empenhos") == coletas.VENDAVEL_COM_ATRIBUICAO
    )


def test_licitacon_fica_a_confirmar():
    # o LicitaCon do TCE-RS espera a resposta da Ouvidoria (ADR 0085)
    assert coletas.revenda_da_fonte("tce-rs") == coletas.A_CONFIRMAR
    assert coletas.revenda_da_fonte("tce-rs-licitacon") == coletas.A_CONFIRMAR
