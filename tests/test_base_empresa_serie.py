"""B13: controladas pelo FRE e a ligação empresa ↔ série da prévia do balanço."""

import io
import json
import zipfile
from datetime import UTC, date, datetime

import pandas as pd

from base import controladas, empresa_serie, historico
from src.banco.coletas import com_registro

AGORA = datetime(2026, 10, 14, 7, tzinfo=UTC)
ULTRAPAR = "33.256.439/0001-39"
IPIRANGA = "33337122000127.0"  # o FRE às vezes traz o CNPJ como número
HAPVIDA = "05.197.443/0001-38"
HAPVIDA_OPERADORA = "63554067000198"
PARTICIPACOES = (
    "CNPJ_Companhia;Data_Referencia;Versao;ID_Documento;Nome_Companhia;ID_Sociedade;"
    "Razao_Social;CNPJ;Tipo_Sociedade;Descricao_Atividades;Pais_Sede;UF_Sede;Municipio_Sede;"
    "Participacao_Emissor;Possui_Registro_CVM;Codigo_CVM;Razao_Aquisicao_Manutencao;"
    "Data_Valor_Mercado;Data_Valor_Contabil;Valor_Mercado;Valor_Contabil"
)
PRINCIPAL = (
    "CNPJ_CIA;DT_REFER;VERSAO;DENOM_CIA;CD_CVM;CATEG_DOC;ID_DOC;DT_RECEB;LINK_DOC"
)


def _participacao(cia, nome_cia, versao, documento, razao, cnpj, tipo, pct):
    campos = [cia, "2026-01-01", versao, documento, nome_cia, "1", razao, cnpj, tipo]
    return ";".join(campos + ["", "Brasil", "SP", "", pct] + [""] * 7)


def _fre() -> bytes:
    participacoes = [
        PARTICIPACOES,
        # versão 1 (velha) e 2 (a que vale) do documento da Ultrapar
        _participacao(
            ULTRAPAR,
            "ULTRAPAR PARTICIPAÇÕES",
            "1",
            "10",
            "Velha S.A.",
            "1",
            "Controlada",
            "1",
        ),
        _participacao(
            ULTRAPAR,
            "ULTRAPAR PARTICIPAÇÕES",
            "2",
            "11",
            "Ipiranga Produtos de Petróleo S.A.",
            IPIRANGA,
            "Controlada",
            "100.00",
        ),
        _participacao(
            ULTRAPAR,
            "ULTRAPAR PARTICIPAÇÕES",
            "2",
            "11",
            "Ultra Argentina",
            "",
            "Controlada",
            "100.00",
        ),
        _participacao(
            HAPVIDA,
            "HAPVIDA PARTICIPAÇÕES",
            "1",
            "20",
            "Hapvida Assistência Médica S.A.",
            HAPVIDA_OPERADORA,
            "Controlada",
            "99.9",
        ),
    ]
    principal = [
        PRINCIPAL,
        f"{ULTRAPAR};2026-12-31;1;ULTRAPAR;1;FRE;10;2026-05-01;x",
        f"{ULTRAPAR};2026-12-31;2;ULTRAPAR;1;FRE;11;2026-06-10;x",
        f"{HAPVIDA};2026-12-31;1;HAPVIDA;2;FRE;20;2026-05-20;x",
    ]
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as arquivo:
        arquivo.writestr(
            "fre_cia_aberta_participacao_sociedade_2026.csv",
            "\n".join(participacoes).encode("latin-1"),
        )
        arquivo.writestr(
            "fre_cia_aberta_2026.csv", "\n".join(principal).encode("latin-1")
        )
    return saida.getvalue()


def test_cnpj14_aceita_texto_numero_e_raiz():
    assert controladas.cnpj14("33.256.439/0001-39") == "33256439000139"
    assert controladas.cnpj14("8884213000135.0") == "08884213000135"
    assert controladas.cnpj14("03645752") == "00000003645752"
    assert controladas.cnpj14("") is None
    assert controladas.cnpj14("0.0") is None
    assert controladas.cnpj14(float("nan")) is None


def test_controladas_do_fre_com_a_data_de_entrega_e_a_versao_mais_nova():
    tabela = controladas.ler_controladas_do_fre(_fre())
    ultrapar = tabela[tabela["cnpj_companhia"] == "33256439000139"]
    assert set(ultrapar["razao_social"]) == {
        "Ipiranga Produtos de Petróleo S.A.",
        "Ultra Argentina",
    }  # a versão 1 ficou de fora
    ipiranga = ultrapar[ultrapar["razao_social"].str.startswith("Ipiranga")].iloc[0]
    assert ipiranga["cnpj"] == "33337122000127"
    assert ipiranga["conhecido_em"] == date(2026, 6, 10)
    assert ipiranga["tipo"] == "controlada"
    assert ultrapar[ultrapar["razao_social"] == "Ultra Argentina"]["cnpj"].isna().all()
    assert "controladas" in historico.TABELAS


def test_nome_normalizado():
    assert (
        empresa_serie.nome_normalizado("Ipiranga Produtos de Petróleo S.A.")
        == "IPIRANGA PRODUTOS DE PETROLEO"
    )
    assert empresa_serie.nome_normalizado("IPIRANGA PRODUTOS DE PETROLEO SA") == (
        "IPIRANGA PRODUTOS DE PETROLEO"
    )
    assert empresa_serie.nome_normalizado("  ") is None


def _entidades():
    return pd.DataFrame(
        [
            # ANS: CNPJ da operadora = controlada da Hapvida
            ("ans-beneficiarios", "368253", "HAPVIDA ASSISTENCIA MEDICA", "63554067"),
            # Pix: ISPB = raiz da própria companhia
            ("bcb-pix-chaves", "05197443", "HAPVIDA PARTICIPACOES", "05197443"),
            # ANP: só o nome, igual à razão social da controlada depois de normalizar
            (
                "anp-vendas-distribuidora",
                "IPIRANGA PRODUTOS DE PETRÓLEO S.A",
                None,
                None,
            ),
            # nome parecido não liga
            ("anp-vendas-distribuidora", "IPIRANGA PRODUTOS", None, None),
            ("ans-beneficiarios", "999999", "OUTRA OPERADORA", "11111111"),
        ],
        columns=["fonte", "chave", "nome", "raiz"],
    ).assign(nome=lambda t: t["nome"].fillna(t["chave"]))


def test_liga_pelo_cnpj_proprio_ou_da_controlada_e_pelo_nome_exato():
    tabela = empresa_serie.ligar(
        _entidades(), controladas.ler_controladas_do_fre(_fre())
    )
    por_chave = tabela.set_index(["fonte", "chave"])
    operadora = por_chave.loc[("ans-beneficiarios", "368253")]
    assert (operadora["cnpj_companhia"], operadora["via"], operadora["por"]) == (
        "05197443000138",
        "controlada",
        "cnpj",
    )
    assert operadora["desde"] == date(2026, 5, 20)  # não vale antes da entrega do FRE
    assert por_chave.loc[("bcb-pix-chaves", "05197443"), "via"] == "propria"
    ipiranga = por_chave.loc[
        ("anp-vendas-distribuidora", "IPIRANGA PRODUTOS DE PETRÓLEO S.A")
    ]
    assert (ipiranga["cnpj_companhia"], ipiranga["por"]) == ("33256439000139", "nome")
    # sem ligação, mas presentes (a revisão vê o que faltou)
    assert pd.isna(
        por_chave.loc[
            ("anp-vendas-distribuidora", "IPIRANGA PRODUTOS"), "cnpj_companhia"
        ]
    )
    assert pd.isna(por_chave.loc[("ans-beneficiarios", "999999"), "cnpj_companhia"])
    assert len(tabela) == len(_entidades())


def test_leitores_de_cada_fonte():
    pix = json.dumps(
        {"value": [{"ISPB": "00416968", "Nome": "BANCO INTER", "Data": "2026-09-30"}]}
    ).encode()
    assert empresa_serie.entidades_pix(pix)[["chave", "raiz"]].values.tolist() == [
        ["00416968", "00416968"]
    ]
    anatel = (
        "CNPJ;Empresa;Grupo Econômico;2026-07\n"
        "2421421000111;TIM;TELECOM ITALIA;10\n2421421000111;TIM;TELECOM ITALIA;12\n"
    ).encode("utf-8-sig")
    linha = empresa_serie.entidades_anatel(anatel).iloc[0]
    assert (linha["chave"], linha["nome"], linha["raiz"]) == (
        "02421421000111",
        "TIM (TELECOM ITALIA)",
        "02421421",
    )
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as arquivo:
        arquivo.writestr(
            "Liquidos_Vendas_Atual.csv",
            "Ano;Agente Regulado;Qtd\n2026;VIBRA ENERGIA S.A;1\n2026;VIBRA ENERGIA S.A;2\n".encode(
                "latin-1"
            ),
        )
        arquivo.writestr("Liquidos_Entregas_Atual.csv", b"Ano;Fornecedor\n2026;X\n")
    anp = empresa_serie.entidades_anp(saida.getvalue())
    assert anp["chave"].tolist() == ["VIBRA ENERGIA S.A"]
    assert anp["raiz"].isna().all()
    samp = io.BytesIO()
    pd.DataFrame(
        {
            "NumCNPJAgenteDistribuidora": [17155730000164.0],
            "NomAgenteDistribuidora": ["CEMIG-D"],
        }
    ).to_parquet(samp)
    assert empresa_serie.entidades_samp(samp.getvalue())["raiz"].tolist() == [
        "17155730"
    ]


def test_escolhe_a_safra_mais_recente_de_cada_fonte():
    zip_anatel = "https://www.anatel.gov.br/x/acessos_telefonia_movel.zip"
    anatel = {
        f"{zip_anatel}#Acessos_Telefonia_Movel_2026_1S_Colunas.csv",
        f"{zip_anatel}#Acessos_Telefonia_Movel_2025_2S_Colunas.csv",
    }
    assert empresa_serie.escolher("anatel-acessos", list(anatel)) == {
        f"{zip_anatel}#Acessos_Telefonia_Movel_2026_1S_Colunas.csv"
    }
    ans = [
        "https://d/202607/pda-024-icb-AC-2026_07.zip",
        "https://d/202608/pda-024-icb-AC-2026_08.zip",
    ]
    assert empresa_serie.escolher("ans-beneficiarios", ans) == {ans[1]}
    pix = [
        f"https://o/ChavesPix(Data=@Data)?@Data='2026-0{m}-30'&$format=json"
        for m in (7, 9)
    ]
    assert empresa_serie.escolher("bcb-pix-chaves", pix) == {pix[1]}


def test_montagem_grava_a_tabela_com_as_ligacoes(banco, tmp_path):
    pasta = tmp_path / "base"
    (pasta / "controladas").mkdir(parents=True)
    controladas.ler_controladas_do_fre(_fre()).to_parquet(
        pasta / "controladas" / "2026.parquet", index=False
    )
    pix = json.dumps(
        {"value": [{"ISPB": "05197443", "Nome": "HAPVIDA", "Data": "2026-09-30"}]}
    ).encode()
    com_registro("bcb-pix-chaves", lambda _url: pix)(
        "https://olinda.bcb.gov.br/ChavesPix(Data=@Data)?@Data='2026-09-30'&$format=json"
    )
    with banco.connect() as conexao:
        assert empresa_serie.montar(conexao, pasta, AGORA) == 1
    tabela = pd.read_parquet(pasta / "empresa_serie" / "empresa_serie.parquet")
    assert tabela["cnpj_companhia"].tolist() == ["05197443000138"]
    assert tabela["montado_em"].iloc[0] == AGORA.isoformat()


def test_sem_controladas_nada_e_gravado(banco, tmp_path):
    with banco.connect() as conexao:
        assert empresa_serie.montar(conexao, tmp_path, AGORA) == 0
    assert not (tmp_path / "empresa_serie").exists()


def test_principal_prefere_a_propria_e_depois_a_ligacao_mais_recente():
    controladas_ = pd.DataFrame(
        {
            "cnpj_companhia": ["11111111000111", "22222222000122", "33333333000133"],
            "companhia": ["ANTIGA DONA S.A.", "DONA ATUAL S.A.", "ENEVA S.A."],
            "referencia": [date(2015, 1, 1), date(2026, 1, 1), date(2026, 1, 1)],
            "versao": ["1", "1", "1"],
            "id_documento": ["1", "2", "3"],
            "conhecido_em": [date(2015, 5, 1), date(2026, 5, 1), date(2026, 5, 1)],
            "cnpj": ["44444444000144", "44444444000144", "55555555000155"],
            "razao_social": ["Distribuidora X", "Distribuidora X", "Outra"],
            "tipo": ["coligada", "controlada", ""],
            "participacao": [30.0, 90.0, 10.0],
        }
    )
    entidades = pd.DataFrame(
        [
            ("aneel-samp", "44444444000144", "DISTRIBUIDORA X", "44444444"),
            ("ons-capacidade-geracao", "ENEVA", "ENEVA", None),
        ],
        columns=["fonte", "chave", "nome", "raiz"],
    )
    tabela = empresa_serie.ligar(entidades, controladas_)
    principal = tabela[tabela["principal"]].set_index("fonte")
    assert principal.loc["aneel-samp", "companhia"] == "DONA ATUAL S.A."
    assert (
        len(tabela[tabela["fonte"] == "aneel-samp"]) == 2
    )  # a antiga fica como histórico
    # a própria companhia também liga pelo nome (a Eneva é listada)
    assert principal.loc["ons-capacidade-geracao", "via"] == "propria"


def test_principal_prefere_a_companhia_que_tem_ticker_hoje():
    """O Banco Inter S.A. saiu da bolsa; a Inter & Co (BDR INBR32) é a que se usa."""
    ligacoes = pd.DataFrame(
        {
            "fonte": ["bcb-pix-chaves"] * 2,
            "chave": ["00416968"] * 2,
            "cnpj_companhia": ["00416968000101", "99999999000199"],
            "via": ["propria", "controlada"],
            "ultima_referencia": ["2026-01-01", "2026-01-01"],
            "participacao": [100.0, 100.0],
            "tickers": [None, "INBR32"],
        }
    )
    assert empresa_serie._principal(ligacoes).tolist() == [False, True]
