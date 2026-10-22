"""FRE completo para a governança (série T, T3): capital social, empregados, acionistas e partes
relacionadas lidos de um recorte real
do FRE 2024 (cinco documentos: Lifemed, Estrela e Petrobras em duas versões, mais uma versão antiga
sem linhas; nome e CPF de pessoa trocados por valores fictícios ainda no servidor), com a data de
entrega de cada versão, sem olhar o futuro e com pessoa física só somada (ADR 0075)."""

import io
import json
import re
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from base import fre_governanca as governanca
from base.parquet import conferir_tabela
from scripts import carga_ofertas_e_conselhos as carga
from src import acervo
from src import versao_do_codigo as vc
from src.banco.coletas import registrar
from src.banco.conexao import criar_engine, migrar_para

RECORTE = (Path(__file__).parent / "arquivos" / "fre" / "fre_t3_2024.zip").read_bytes()
URL_DO_FRE = (
    "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/FRE/DADOS/fre_cia_aberta_2024.zip"
)
VERSAO = "6a2b0c4d2e1f0a9b8c7d6e5f4a3b2c1d0e9f8a7c"
PRINCIPAL = "fre_cia_aberta_2024.csv"
LIFEMED, ESTRELA, PETROBRAS = "144295", "146667", "148031"
CPF = re.compile(r"\d{3}\.\d{3}\.\d{3}-\d{2}")
LEITORES = {
    "fre_capital_social": governanca.ler_capital_social,
    "fre_empregados": governanca.ler_empregados,
    "fre_acionistas": governanca.ler_acionistas,
    "fre_partes_relacionadas": governanca.ler_partes_relacionadas,
}
ACIONISTAS = "fre_cia_aberta_posicao_acionaria_2024.csv"
PARTES = "fre_cia_aberta_transacao_parte_relacionada_2024.csv"


def _csv(conteudo_do_zip: bytes, nome: str) -> tuple[list[str], list[list[str]]]:
    with zipfile.ZipFile(io.BytesIO(conteudo_do_zip)) as arquivo:
        linhas = arquivo.read(nome).decode("latin-1").splitlines()
    return linhas[0].split(";"), [linha.split(";") for linha in linhas[1:]]


def _trocar(conteudo_do_zip: bytes, nome: str, linhas: list[list[str]]) -> bytes:
    """O ZIP com as linhas de um CSV trocadas (o cabeçalho fica)."""
    with zipfile.ZipFile(io.BytesIO(conteudo_do_zip)) as original:
        arquivos = {n: original.read(n) for n in original.namelist()}
    cabecalho, _ = _csv(conteudo_do_zip, nome)
    texto = "\r\n".join(";".join(campos) for campos in [cabecalho, *linhas]) + "\r\n"
    arquivos[nome] = texto.encode("latin-1")
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as novo:
        for n, conteudo in arquivos.items():
            novo.writestr(n, conteudo)
    return saida.getvalue()


def _acrescentar(
    conteudo_do_zip: bytes, nome: str, linhas: list[dict[str, str]]
) -> bytes:
    """O ZIP com linhas novas num CSV, dadas pelo nome das colunas (as que faltam ficam vazias)."""
    cabecalho, antigas = _csv(conteudo_do_zip, nome)
    novas = [[linha.get(coluna, "") for coluna in cabecalho] for linha in linhas]
    return _trocar(conteudo_do_zip, nome, [*antigas, *novas])


def _documento(id_documento: str) -> dict[str, str]:
    """As colunas do documento de uma versão do recorte, para montar linhas sintéticas."""
    cabecalho, linhas = _csv(RECORTE, PRINCIPAL)
    campos = dict(
        zip(
            cabecalho,
            next(c for c in linhas if c[cabecalho.index("ID_DOC")] == id_documento),
            strict=True,
        )
    )
    return {
        "CNPJ_Companhia": campos["CNPJ_CIA"],
        "Data_Referencia": campos["DT_REFER"],
        "Versao": campos["VERSAO"],
        "ID_Documento": id_documento,
    }


def _ate(corte: str) -> bytes:
    """O FRE como estava publicado no dia do `corte`: só as versões entregues até ali."""
    cabecalho, linhas = _csv(RECORTE, PRINCIPAL)
    entrega = cabecalho.index("DT_RECEB")
    return _trocar(RECORTE, PRINCIPAL, [c for c in linhas if c[entrega] <= corte])


# --- capital social ---------------------------------------------------------------------------------
def test_capital_social_com_os_quatro_tipos_e_as_classes():
    capital = governanca.ler_capital_social(RECORTE)
    assert set(capital["tipo_capital"]) <= {
        "integralizado",
        "subscrito",
        "emitido",
        "autorizado",
    }
    estrela = capital[
        (capital["id_documento"] == ESTRELA)
        & (capital["tipo_capital"] == "integralizado")
    ].iloc[0]
    assert estrela["acoes_ordinarias"] == 2_694_500
    assert estrela["acoes_preferenciais"] == 5_389_000
    assert (
        estrela["acoes_total"]
        == estrela["acoes_ordinarias"] + estrela["acoes_preferenciais"]
    )
    assert (
        estrela["acoes_por_classe"]
        == "Preferencial Classe A=5389000; Ordinária Classe A=2694500"
    )
    assert estrela["autorizado_em"] == pd.Timestamp("1995-12-31")
    assert estrela["conhecido_em"] == pd.Timestamp("2025-04-30")
    petrobras = capital[capital["id_documento"] == PETROBRAS]
    assert petrobras["valor_capital"].iloc[0] == pytest.approx(
        205_432_000_000, rel=1e-3
    )
    assert (
        petrobras["acoes_por_classe"].isna().all()
    )  # sem classe preferencial declarada
    assert pd.api.types.is_string_dtype(capital["titulos_conversiveis"])


def test_titulo_conversivel_guarda_o_nome_sem_as_condicoes_nem_o_que_diz_que_nao_ha():
    linhas = [
        {**_documento(LIFEMED), "ID_Capital_Social": capital, "Titulo_Conversivel_Acao": nome,
         "Condicoes_Conversao": "texto livre que não entra"}
        for capital, nome in (
            ("327310", "Debêntures conversíveis 3ª emissão"), ("327310", "NÃO HÁ"),
            ("327309", "N/A"), ("327309", "Não se aplica."), ("327309", "-"),
        )
    ]  # fmt: skip
    com_titulos = _acrescentar(
        RECORTE, "fre_cia_aberta_capital_social_titulo_conversivel_2024.csv", linhas
    )
    capital = governanca.ler_capital_social(com_titulos).set_index("id_capital_social")
    assert (
        capital.loc["327310", "titulos_conversiveis"]
        == "Debêntures conversíveis 3ª emissão"
    )
    assert pd.isna(capital.loc["327309", "titulos_conversiveis"])  # só "não há": vazio
    assert "texto livre" not in capital.to_string()


# --- empregados -------------------------------------------------------------------------------------
def test_empregados_por_regiao_e_por_posicao_numa_linha_cada():
    empregados = governanca.ler_empregados(RECORTE)
    chave = ["id_documento", "recorte", "grupo"]
    assert not empregados.duplicated(subset=chave).any()
    assert set(empregados["recorte"]) == {"local", "posicao"}
    por_regiao = empregados[empregados["recorte"] == "local"]
    assert set(por_regiao["grupo"]) == {
        "Norte", "Nordeste", "Centro-Oeste", "Sudeste", "Sul", "Exterior"
    }  # fmt: skip
    sul = por_regiao.set_index(["id_documento", "grupo"]).loc[(LIFEMED, "Sul")]
    assert (sul["genero_feminino"], sul["genero_masculino"]) == (232, 127)
    assert sul["idade_ate_30"] + sul["idade_30_a_50"] + sul["idade_acima_50"] == 359
    assert pd.isna(sul["regiao_sul"])  # a região por posição só no recorte por posição
    por_posicao = empregados[empregados["recorte"] == "posicao"]
    assert por_posicao["regiao_sudeste"].notna().all()


def test_pcd_entra_junto_da_posicao():
    linhas = [
        {**_documento(ESTRELA), "Codigo_Posicao": "1", "Posicao": posicao,
         "Quantidade_PCD": pcd, "Quantidade_Nao_PCD": "90", "Quantidade_Sem_Resposta": "0"}
        for posicao, pcd in (("Liderança", "1"), ("Não-liderança", "7"))
    ]  # fmt: skip
    com_pcd = _acrescentar(RECORTE, "fre_cia_aberta_empregado_PCD_2024.csv", linhas)
    empregados = governanca.ler_empregados(com_pcd)
    estrela = empregados[
        (empregados["id_documento"] == ESTRELA) & (empregados["recorte"] == "posicao")
    ].set_index("grupo")
    assert estrela.loc["Não-liderança", "pcd_sim"] == 7
    assert estrela.loc["Liderança", "pcd_nao"] == 90
    assert len(estrela) == 2  # juntou com o gênero e a raça, não criou linha nova


def test_fre_sem_as_tabelas_da_vazio_com_as_colunas():
    """O FRE antes de 2023 não tem empregados; um ZIP só com o arquivo principal não quebra."""
    with zipfile.ZipFile(io.BytesIO(RECORTE)) as original:
        principal = original.read(PRINCIPAL)
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as novo:
        novo.writestr(PRINCIPAL, principal)
    for ler, colunas in (
        (governanca.ler_capital_social, governanca.COLUNAS_DO_CAPITAL),
        (governanca.ler_empregados, governanca.COLUNAS_DOS_EMPREGADOS),
    ):
        vazia = ler(saida.getvalue())
        assert vazia.empty
        assert list(vazia.columns) == list(colunas)


# --- acionistas -------------------------------------------------------------------------------------
def test_acionistas_empresa_com_nome_e_cnpj_e_pessoa_so_somada():
    acionistas = governanca.ler_acionistas(RECORTE)
    lifemed = acionistas[acionistas["id_documento"] == LIFEMED].set_index(
        "id_acionista"
    )
    assert lifemed.loc["7596991", "acionista"] == "Kumla SP Participações S.A."
    assert lifemed.loc["7596991", "cnpj_acionista"] == "20.918.377/0001-31"
    assert lifemed.loc["7596991", "controlador"]
    # a pessoa que controla a Kumla: uma linha somada, sem nada que a identifique
    pessoa = lifemed.loc["pf:7596991:S:S"]
    assert pessoa["tipo_acionista"] == "pf_somada"
    assert pessoa["percentual_total"] == pytest.approx(99.875)
    assert pessoa["acionistas_no_grupo"] == 1
    assert pd.isna(pessoa["acionista"]) and pd.isna(pessoa["cnpj_acionista"])
    assert pd.isna(pessoa["uf"]) and pd.isna(pessoa["nacionalidade"])
    assert set(acionistas["tipo_acionista"]) == {
        "pj",
        "pf_somada",
        "outros",
        "tesouraria",
    }
    petrobras = acionistas[acionistas["id_documento"] == PETROBRAS].set_index(
        "id_acionista"
    )
    assert pd.isna(
        petrobras.loc["7685020", "cnpj_acionista"]
    )  # BlackRock: CNPJ só com zeros
    assert petrobras.loc["7685033", "percentual_total"] == pytest.approx(
        52.678
    )  # "Outros"


def test_pessoas_do_mesmo_grupo_viram_uma_linha_e_quem_e_acionista_de_pessoa_perde_o_id():
    linhas = [
        {**_documento(ESTRELA), "ID_Acionista": "1", "Acionista": "PESSOA FICTICIA A",
         "Tipo_Pessoa_Acionista": "PF", "CPF_CNPJ_Acionista": "123.456.789-09",
         "Quantidade_Total_Acoes_Circulacao": "100", "Percentual_Total_Acoes_Circulacao": "1.5",
         "Acionista_Controlador": "N", "Participante_Acordo_Acionistas": "N",
         "Representante_Legal": "REPRESENTANTE FICTICIA A"},
        {**_documento(ESTRELA), "ID_Acionista": "2", "Acionista": "PESSOA FICTICIA B",
         "Tipo_Pessoa_Acionista": "PJ", "CPF_CNPJ_Acionista": "98765432100",
         "Quantidade_Total_Acoes_Circulacao": "50", "Percentual_Total_Acoes_Circulacao": "0.5",
         "Acionista_Controlador": "N", "Participante_Acordo_Acionistas": "N"},
        {**_documento(ESTRELA), "ID_Acionista": "3", "Acionista": "PESSOA FICTICIA C",
         "Tipo_Pessoa_Acionista": "", "Percentual_Total_Acoes_Circulacao": "2",
         "Acionista_Controlador": "N", "Participante_Acordo_Acionistas": "N"},
        {**_documento(ESTRELA), "ID_Acionista": "4", "Acionista": "Holding Fictícia Ltda.",
         "Tipo_Pessoa_Acionista": "PJ", "CPF_CNPJ_Acionista": "11.222.333/0001-81",
         "ID_Acionista_Relacionado": "7657227", "Tipo_Pessoa_Acionista_Relacionado": "PF",
         "CPF_CNPJ_Acionista_Relacionado": "123.456.789-09", "Percentual_Total_Acoes_Circulacao": "10",
         "Acionista_Controlador": "N", "Participante_Acordo_Acionistas": "N"},
    ]  # fmt: skip
    acionistas = governanca.ler_acionistas(_acrescentar(RECORTE, ACIONISTAS, linhas))
    estrela = acionistas[acionistas["id_documento"] == ESTRELA].set_index(
        "id_acionista"
    )
    # PF declarada, "PJ" com CPF e sem tipo com nome de gente: as três somadas numa linha
    somadas = estrela.loc["pf:raiz:N:N"]
    assert somadas["acionistas_no_grupo"] == 3
    assert somadas["percentual_total"] == pytest.approx(4.0)
    assert somadas["acoes_total"] == 150
    holding = estrela.loc["4"]
    assert holding["acionista"] == "Holding Fictícia Ltda."
    assert holding["tipo_relacionado"] == "PF"
    assert pd.isna(holding["id_acionista_relacionado"])
    assert pd.isna(holding["cnpj_acionista_relacionado"])
    assert "REPRESENTANTE" not in acionistas.astype(str).to_string()


def test_cpf_que_escapa_da_regra_para_a_carga():
    for texto in ("Empresa Fictícia S.A. 123.456.789-09", "Empresa 12345678909"):
        with pytest.raises(ValueError, match="CPF"):
            governanca.conferir_sem_cpf(
                pd.DataFrame({"acionista": [texto]}), ("acionista",)
            )
    empresa = pd.DataFrame(
        {"acionista": ["Empresa Fictícia S.A."], "cnpj": ["11.222.333/0001-81"]}
    )
    assert governanca.conferir_sem_cpf(empresa, ("acionista", "cnpj")) is empresa


@pytest.mark.parametrize(
    ("nome", "empresa"),
    [
        ("Kumla SP Participações S.A.", True), ("Fundo BBI Financial I", True),
        ("BlackRock Inc", True), ("União Federal", True), ("Banco do Brasil S.A.", True),
        ("Editora Estrela Cultural Ltda", True), ("JOSE DA SILVA", False),
        ("JOSE DA SILVA ME", False), ("MARIA SOUZA EIRELI", False),
    ],
)  # fmt: skip
def test_nome_de_empresa(nome, empresa):
    assert governanca.parece_empresa(nome) is empresa


# --- partes relacionadas ----------------------------------------------------------------------------
def test_partes_relacionadas_empresa_com_nome_e_pessoa_somada_por_relacao():
    partes = governanca.ler_partes_relacionadas(RECORTE)
    estrela = partes[partes["id_documento"] == ESTRELA]
    assert set(estrela["relacao"]) == {"controlada"}
    assert estrela["contraparte"].str.startswith(("Estrela", "Editora")).all()
    assert estrela["transacoes"].eq(1).all()
    lifemed = partes[partes["id_documento"] == LIFEMED].set_index("linha")
    pessoas = lifemed.loc[
        "pf:PF:controladora"
    ]  # as duas pessoas controladoras, somadas
    assert pessoas["transacoes"] == 2
    assert pessoas["montante_envolvido"] == 19_200_000
    assert pd.isna(pessoas["contraparte"]) and pd.isna(pessoas["data_transacao"])
    assert (
        lifemed.loc["3", "relacao"] == "acionista"
    )  # o BNDES, sem tipo, fica com o nome
    assert lifemed.loc["3", "taxa_de_juros"] == pytest.approx(7.34)
    petrobras = partes[partes["id_documento"] == PETROBRAS]
    assert set(petrobras["posicao_contratual"].dropna()) == {"credor", "devedor"}
    assert petrobras["taxa_de_juros"].isna().any()  # "Meta atuarial", "N/A": vazio
    assert (
        len(partes) < 53 and partes["transacoes"].sum() == 53
    )  # nenhuma transação some


@pytest.mark.parametrize(
    ("texto", "categoria"),
    [
        ("Sociedade sob controle comum", "controle_comum"),
        ("Ambas são controladas pela Neoenergia", "controle_comum"),
        ("Joint venture", "controle_conjunto"), ("Controladora", "controladora"),
        ("Acionista controlador", "controladora"), ("Controlada Direta", "controlada"),
        ("Coligada", "coligada"), ("Diretor estatutário", "administracao"),
        ("Cônjuge de conselheiro", "administracao"), ("Filho do fundador", "familiar"),
        ("Acionista", "acionista"), ("Fornecedor", "outra"), ("", "nao_informada"),
    ],
)  # fmt: skip
def test_categoria_da_relacao(texto, categoria):
    assert governanca.categoria_da_relacao(texto) == categoria


def test_parte_pessoa_sem_tipo_e_cpf_no_documento_sao_somadas():
    linhas = [
        {**_documento(ESTRELA), "Parte_Relacionada": "PESSOA FICTICIA X", "Tipo_Pessoa": "",
         "Relacao_Emissor": "Diretor", "Montante_Envolvido": "1000.00", "Taxa_Juros": "3,5%"},
        {**_documento(ESTRELA), "Parte_Relacionada": "Outra Ficticia Ltda",
         "Tipo_Pessoa": "PJ", "Documento_Parte_Relacionada": "123.456.789-09",
         "Relacao_Emissor": "Diretor", "Montante_Envolvido": "500.00"},
        {**_documento(ESTRELA), "Parte_Relacionada": "Fornecedora Fictícia S.A.",
         "Tipo_Pessoa": "PJ", "Documento_Parte_Relacionada": "11.222.333/0001-81",
         "Relacao_Emissor": "Controle comum", "Taxa_Juros": "3,5%", "Emprestimo_Divida": "S"},
    ]  # fmt: skip
    partes = governanca.ler_partes_relacionadas(_acrescentar(RECORTE, PARTES, linhas))
    estrela = partes[partes["id_documento"] == ESTRELA].set_index("linha")
    assert estrela.loc["pf:nao_informado:administracao", "montante_envolvido"] == 1000
    assert estrela.loc["pf:PJ:administracao", "montante_envolvido"] == 500
    empresa = estrela.loc["9"]
    assert empresa["contraparte"] == "Fornecedora Fictícia S.A."
    assert empresa["cnpj_contraparte"] == "11.222.333/0001-81"
    assert empresa["taxa_de_juros"] == pytest.approx(3.5)
    assert empresa["emprestimo"]


# --- regras de toda tabela --------------------------------------------------------------------------
@pytest.mark.parametrize("pasta", LEITORES)
def test_nenhum_cpf_nem_nome_de_pessoa(pasta):
    tabela = LEITORES[pasta](RECORTE)
    assert not tabela.empty
    texto = tabela.astype(str).to_string()
    assert not CPF.search(texto)
    assert "FICTICI" not in texto.upper()
    assert tabela["conhecido_em"].notna().all()


@pytest.mark.parametrize(
    "corte", ["2025-01-15", "2025-04-29", "2025-05-18", "2025-12-31"]
)
@pytest.mark.parametrize("pasta", LEITORES)
def test_cortar_o_futuro_nao_muda_o_passado(pasta, corte):
    """Ler o FRE como estava no dia do corte dá o mesmo que ler tudo e olhar só o já entregue."""
    ler = LEITORES[pasta]
    naquele_dia = ler(_ate(corte))
    visto_hoje = governanca.conhecidas_ate(ler(RECORTE), pd.Timestamp(corte))
    pd.testing.assert_frame_equal(
        naquele_dia.reset_index(drop=True), visto_hoje, check_dtype=False
    )


# --- carga ------------------------------------------------------------------------------------------
@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'b.sqlite').as_posix()}"
    monkeypatch.setenv("TICKERLAB_DATABASE_URL", url)
    monkeypatch.setenv(acervo.VARIAVEL_DA_PASTA, str(tmp_path / "acervo"))
    monkeypatch.setenv(vc.VARIAVEL, VERSAO)
    migrar_para("head", url=url)
    quando = datetime(2026, 10, 22, 5, tzinfo=UTC)
    with criar_engine(url).begin() as c:
        caminho = acervo.guardar_original(
            carga.FONTE_DO_FRE, URL_DO_FRE, RECORTE, quando
        )
        registrar(
            c, carga.FONTE_DO_FRE, URL_DO_FRE, RECORTE, "ok", agora=quando,
            caminho_do_original=caminho,
        )  # fmt: skip
    return tmp_path / "acervo" / "base"


def test_carga_grava_as_quatro_tabelas_com_manifesto(ambiente):
    assert carga.main(["--base", str(ambiente)]) == 0
    for pasta, ler in LEITORES.items():
        arquivo = ambiente / pasta / "2024.parquet"
        assert conferir_tabela(arquivo), arquivo
        manifesto = json.loads(arquivo.with_suffix(".json").read_text(encoding="utf-8"))
        assert manifesto["versao_do_codigo"] == VERSAO
        assert len(pd.read_parquet(arquivo)) == len(ler(RECORTE))
