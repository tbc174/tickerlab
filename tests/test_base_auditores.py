"""Auditor por empresa e data e o rótulo "trocou de auditor" (série B3), "como era na data"."""

import hashlib
import io
import json
import zipfile
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from base import auditores, historico
from base.ancoragem import parquets_sem_manifesto
from base.ponto_no_tempo import divulgacao_publica
from src.banco.coletas import com_registro

PRINCIPAL = (
    "CNPJ_CIA;DT_REFER;VERSAO;DENOM_CIA;CD_CVM;CATEG_DOC;ID_DOC;DT_RECEB;LINK_DOC"
)
AUDITOR = (
    "CNPJ_Companhia;Data_Referencia;Versao;ID_Documento;Nome_Empresarial;Auditor;"
    "CPF_CNPJ_Auditor;Codigo_CVM_Auditor;Origem_Auditor;Data_Inicio_Atuacao_Auditor;"
    "Data_Fim_Atuacao_Auditor;Responsavel_Tecnico;CPF_Responsavel_Tecnico;"
    "Data_Inicio_Atuacao_Responsavel_Tecnico;Data_Fim_Atuacao_Responsavel_Tecnico"
)
KPMG = ("KPMG Auditores Independentes", "57.755.217/0001-29", "004189")
EY = ("Ernst & Young Auditores Independentes", "61.366.936/0001-25", "004715")
PWC = ("PricewaterhouseCoopers Auditores", "61.562.112/0002-01", "002879")
CIA = "11.111.111/0001-11"


def _mandato(firma, inicio, fim="", cnpj=CIA, documento="10", ano=2020, versao="2"):
    nome, cpf_cnpj, codigo = firma
    return (
        f"{cnpj};{ano}-01-01;{versao};{documento};EMPRESA UM;{nome};{cpf_cnpj};{codigo};"
        f"Nacional;{inicio};{fim};FULANO DE TAL;123.456.789-00;{inicio};"
    )


def _documento(documento, recebido, cnpj=CIA, ano=2020, versao="2"):
    return (
        f"{cnpj};{ano}-01-01;{versao};EMPRESA UM;001;FCA;{documento};{recebido};"
        f"http://rad/{documento}"
    )


def _zip(principal: list[str], mandatos: list[str], ano=2020) -> bytes:
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as z:
        z.writestr(
            f"fca_cia_aberta_{ano}.csv",
            "\n".join([PRINCIPAL, *principal]).encode("latin-1"),
        )
        z.writestr(
            f"fca_cia_aberta_auditor_{ano}.csv",
            "\n".join([AUDITOR, *mandatos]).encode("latin-1"),
        )
    return saida.getvalue()


def _ano(ano, recebido, *mandatos, documento=None, cnpj=CIA) -> pd.DataFrame:
    documento = documento or str(ano)
    linhas = [_mandato(*m, cnpj=cnpj, documento=documento, ano=ano) for m in mandatos]
    return auditores.ler_auditores_do_fca(
        _zip([_documento(documento, recebido, cnpj=cnpj, ano=ano)], linhas, ano=ano)
    )


def test_mandato_leva_a_data_em_que_a_cvm_recebeu_o_documento():
    tabela = auditores.ler_auditores_do_fca(
        _zip(
            # a versão 1 e a 2 estão no arquivo principal; a tabela de auditor só traz a mais nova
            [_documento("9", "2020-05-25", versao="1"), _documento("10", "2020-08-25")],
            [_mandato(KPMG, "2018-01-01")],
        )
    )
    assert len(tabela) == 1
    linha = tabela.iloc[0]
    assert linha["conhecido_em"] == date(2020, 8, 25)
    assert linha["referencia"] == date(2020, 1, 1)
    assert linha["inicio"] == date(2018, 1, 1)
    assert pd.isna(linha["fim"])
    assert linha["auditor_id"] == "rede:kpmg"
    assert linha["codigo_cvm_auditor"] == "004189"


def test_responsavel_tecnico_e_cpf_nunca_entram():
    """LGPD: só a firma de auditoria; o sócio responsável e auditor pessoa física ficam sem nome."""
    pessoa = ("João da Silva", "123.456.789-00", "009999")
    tabela = _ano(2020, "2020-05-01", (KPMG, "2018-01-01"), (pessoa, "2019-01-01"))
    texto = tabela.astype(str).to_string()
    assert "FULANO" not in texto and "123.456.789" not in texto
    assert "João" not in texto
    assert not any("respons" in coluna.lower() for coluna in tabela.columns)
    fisica = tabela[tabela["codigo_cvm_auditor"] == "009999"].iloc[0]
    assert fisica["auditor"] is None and fisica["auditor_cnpj"] is None
    assert fisica["auditor_id"] == "cvm:009999"


def test_linhas_iguais_sem_o_responsavel_viram_uma():
    # o BB em 2024: a mesma KPMG duas vezes, uma por sócio responsável
    tabela = _ano(2024, "2024-05-01", (KPMG, "2024-01-01"), (KPMG, "2024-01-01"))
    assert len(tabela) == 1


def test_rede_vem_do_nome_mesmo_com_erro_de_digitacao_cnpj_ou_codigo_trocado():
    nomes = {
        "Delloitte Touche Tohmatsu Auditores Independentes": "deloitte",
        "Deloitte Touche Tohmatsu (código da BDO)": "deloitte",
        "Enerst & Young Auditores Independentes S/S": "ey",
        "Ernest & Young Auditores Independentes S.S.": "ey",
        "Ernst & Young Terco Auditores Independentes": "ey",
        # a Terco entrou na EY em 2010: é a mesma rede, não uma troca da empresa auditada
        "Terco Grant Thornton Aud Indep Soc Simples": "ey",
        "GRANT THORTON AUDITORES INDEPENDENTES": "grant_thornton",
        "PRICEWATERHOUSECOOPERS AUDITORES INDEPENDENTES": "pwc",
        "KPMG AUDITORES INDEPENDENTES LTDA": "kpmg",
        "KMPG Auditores Independentes": "kpmg",
        "BDO RCS Auditores Independentes SS": "bdo",
        # achados pelo relatório de qualidade da montagem do modelo 8 (16/10/2026)
        "Delotite Touche Tohmatsu Auditores Independentes": "deloitte",
        "Esconder detalhesBDO RCS AUDITORES INDEPENDENTES -SS": "bdo",
    }
    for nome, rede in nomes.items():
        # o BB informou o próprio CNPJ no lugar do da firma (FCA de 2011); o código é de outra firma
        firma = (nome, "00.000.000/0001-91", "002100")
        tabela = _ano(2020, "2020-05-01", (firma, "2018-01-01"))
        assert tabela["auditor_id"].tolist() == [f"rede:{rede}"], nome


def test_firma_fora_das_redes_e_o_codigo_da_cvm_mesmo_com_outro_cnpj():
    pequena_cnpj_errado = ("AUDITORA PEQUENA", "00.000.000/0001-91", "012345")
    pequena_outra_raiz = ("AUDITORA PEQUENA S/S", "33.256.439/0001-39", "012345")
    tabela = pd.concat(
        [
            _ano(2020, "2020-05-01", (pequena_cnpj_errado, "2015-01-01")),
            _ano(2021, "2021-05-01", (pequena_outra_raiz, "2015-01-01")),
        ]
    )
    assert set(tabela["auditor_id"]) == {"cvm:012345"}
    assert auditores.trocas_de_auditor(tabela).empty


def test_codigo_vazio_vem_da_mesma_raiz_de_cnpj_no_mesmo_arquivo():
    outra = "22.222.222/0001-22"
    sem_codigo = ("AUDITORA PEQUENA", "12.345.678/0002-00", "")
    com_codigo = ("AUDITORA PEQUENA S/S", "12.345.678/0001-90", "012345")
    tabela = auditores.ler_auditores_do_fca(
        _zip(
            [_documento("1", "2020-05-01"), _documento("2", "2020-05-02", cnpj=outra)],
            [
                _mandato(sem_codigo, "2018-01-01", documento="1"),
                _mandato(com_codigo, "2018-01-01", cnpj=outra, documento="2"),
            ],
        )
    )
    assert tabela["auditor_id"].tolist() == ["cvm:012345", "cvm:012345"]
    assert tabela["codigo_cvm_auditor"].isna().tolist() == [True, False]


def test_sem_codigo_em_nenhuma_linha_fica_a_raiz_do_cnpj():
    sem_codigo = ("AUDITORA PEQUENA S/S", "12.345.678/0001-90", "")
    tabela = _ano(2020, "2020-05-01", (sem_codigo, "2018-01-01"))
    assert tabela["auditor_id"].tolist() == ["cnpj:12345678"]


def test_troca_entre_dois_anos_vale_na_entrega_do_fca_que_a_mostra():
    tabela = pd.concat(
        [
            _ano(2019, "2019-05-10", (KPMG, "2014-01-01")),
            _ano(
                2020,
                "2020-06-15",
                (KPMG, "2014-01-01", "2020-03-31"),
                (EY, "2020-04-01"),
            ),
        ]
    )
    trocas = auditores.trocas_de_auditor(tabela)
    assert len(trocas) == 1
    troca = trocas.iloc[0]
    assert troca["cnpj"] == CIA
    assert troca["conhecido_em"] == date(2020, 6, 15)
    assert troca["efetiva_em"] == date(2020, 4, 1)
    assert troca["anterior_id"] == "rede:kpmg"
    assert troca["novo_id"] == "rede:ey"
    assert troca["anterior"] == KPMG[0] and troca["novo"] == EY[0]
    assert troca["anos_com_o_anterior"] == 6.2


def test_troca_no_primeiro_fca_da_empresa_aparece_pelo_mandato_encerrado():
    # 2010 é o primeiro ano guardado: a troca só se vê pelo fim do mandato anterior no mesmo documento
    tabela = _ano(
        2010,
        "2010-05-25",
        (KPMG, "2005-01-01", "2009-12-31"),
        (PWC, "2010-01-01"),
    )
    trocas = auditores.trocas_de_auditor(tabela)
    assert trocas[["anterior_id", "novo_id"]].values.tolist() == [
        ["rede:kpmg", "rede:pwc"]
    ]
    assert trocas.iloc[0]["conhecido_em"] == date(2010, 5, 25)


def test_mandato_antigo_encerrado_ha_anos_nao_vira_troca_no_primeiro_fca():
    tabela = _ano(
        2010,
        "2010-05-25",
        (KPMG, "2001-01-01", "2004-12-31"),
        (PWC, "2005-01-01"),
    )
    assert auditores.trocas_de_auditor(tabela).empty


def test_contrato_renovado_com_a_mesma_firma_nao_e_troca():
    tabela = pd.concat(
        [
            _ano(2019, "2019-05-01", (KPMG, "2019-01-01", "2019-12-31")),
            _ano(2020, "2020-05-01", (KPMG, "2020-01-01", "2020-12-31")),
            _ano(2021, "2021-05-01", (KPMG, "2021-01-01")),
        ]
    )
    assert auditores.trocas_de_auditor(tabela).empty


def test_auditoria_conjunta_nao_vira_troca_mas_a_saida_de_um_com_entrada_de_outro_vira():
    tabela = pd.concat(
        [
            _ano(2019, "2019-05-01", (KPMG, "2015-01-01")),
            _ano(2020, "2020-05-01", (KPMG, "2015-01-01"), (EY, "2020-01-01")),
            _ano(2021, "2021-05-01", (EY, "2020-01-01")),
            _ano(
                2022,
                "2022-05-01",
                (EY, "2020-01-01", "2021-12-31"),
                (PWC, "2022-01-01"),
            ),
        ]
    )
    trocas = auditores.trocas_de_auditor(tabela)
    assert trocas[["anterior_id", "novo_id"]].values.tolist() == [
        ["rede:ey", "rede:pwc"]
    ]
    # com a EY desde 2020 (a entrada na auditoria conjunta), não desde a saída da KPMG
    assert trocas.iloc[0]["anos_com_o_anterior"] == 2.0


def test_ano_sem_auditor_vigente_nao_apaga_o_anterior():
    tabela = pd.concat(
        [
            _ano(2019, "2019-05-01", (KPMG, "2015-01-01")),
            _ano(2020, "2020-05-01", (KPMG, "2015-01-01", "2019-12-31")),
            _ano(2021, "2021-05-01", (EY, "2021-01-01")),
        ]
    )
    trocas = auditores.trocas_de_auditor(tabela)
    assert trocas[["anterior_id", "novo_id", "conhecido_em"]].values.tolist() == [
        ["rede:kpmg", "rede:ey", date(2021, 5, 1)]
    ]


def test_fca_antigo_reapresentado_depois_do_novo_nao_desfaz_a_troca():
    tabela = pd.concat(
        [
            _ano(2019, "2021-02-01", (KPMG, "2014-01-01")),  # reapresentado em 2021
            _ano(
                2020,
                "2020-06-15",
                (KPMG, "2014-01-01", "2019-12-31"),
                (EY, "2020-01-01"),
            ),
        ]
    )
    trocas = auditores.trocas_de_auditor(tabela)
    assert trocas[["anterior_id", "novo_id"]].values.tolist() == [
        ["rede:kpmg", "rede:ey"]
    ]


def test_mandato_ja_visto_que_volta_num_fca_novo_nao_e_troca():
    """FCA desatualizado (Cielo, Fibria): um ano volta a listar o auditor antigo sem o fim do mandato
    e o seguinte lista o novo de novo. Mandato já visto (mesma firma, mesmo início) que volta não é
    troca: a troca de 2017 aparecia outra vez em 2026 (relatório de qualidade de 16/10/2026)."""
    tabela = pd.concat(
        [
            _ano(2016, "2016-05-20", (KPMG, "2010-01-01")),
            _ano(
                2017,
                "2017-05-20",
                (KPMG, "2010-01-01", "2016-12-31"),
                (PWC, "2017-01-01"),
            ),
            _ano(2025, "2025-05-20", (KPMG, "2010-01-01")),  # desatualizado
            _ano(2026, "2026-05-20", (PWC, "2017-01-01")),
        ]
    )
    trocas = auditores.trocas_de_auditor(tabela)
    assert trocas[["anterior_id", "novo_id"]].values.tolist() == [
        ["rede:kpmg", "rede:pwc"]
    ]


def test_mandato_novo_da_mesma_firma_depois_de_outra_e_troca():
    """A volta de uma firma com um mandato novo (outro início) é troca de verdade."""
    tabela = pd.concat(
        [
            _ano(2016, "2016-05-20", (KPMG, "2010-01-01")),
            _ano(
                2017,
                "2017-05-20",
                (KPMG, "2010-01-01", "2016-12-31"),
                (PWC, "2017-01-01"),
            ),
            _ano(
                2022,
                "2022-05-20",
                (PWC, "2017-01-01", "2021-12-31"),
                (KPMG, "2022-01-01"),
            ),
        ]
    )
    trocas = auditores.trocas_de_auditor(tabela)
    assert trocas[["anterior_id", "novo_id"]].values.tolist() == [
        ["rede:kpmg", "rede:pwc"],
        ["rede:pwc", "rede:kpmg"],
    ]


def test_mandato_sem_data_de_inicio_da_a_troca_sem_os_anos():
    tabela = pd.concat(
        [
            _ano(2019, "2019-05-01", (KPMG, "")),
            _ano(2020, "2020-05-01", (EY, "")),
        ]
    )
    trocas = auditores.trocas_de_auditor(tabela)
    assert len(trocas) == 1
    assert trocas.iloc[0]["efetiva_em"] is None
    assert trocas.iloc[0]["anos_com_o_anterior"] is None


def test_empresas_diferentes_nao_se_misturam():
    outra = "22.222.222/0001-22"
    tabela = pd.concat(
        [
            _ano(2019, "2019-05-01", (KPMG, "2015-01-01")),
            _ano(2020, "2020-05-01", (EY, "2020-01-01"), documento="b", cnpj=outra),
        ]
    )
    assert auditores.trocas_de_auditor(tabela).empty


def test_auditores_entram_na_base_historica():
    assert historico.TABELAS["auditores"].fonte == "cvm-hist-fca"
    assert historico.TABELAS["auditores"].ler is auditores.ler_auditores_do_fca


FIRMAS = st.sampled_from([KPMG, EY, PWC])


@st.composite
def _historias(desenho):
    """Uma ou duas empresas, 1 a 6 FCAs cada, com 1 ou 2 mandatos sorteados por FCA."""
    partes = []
    for cnpj in desenho(st.sampled_from([[CIA], [CIA, "22.222.222/0001-22"]])):
        anos = desenho(
            st.lists(st.integers(2010, 2024), min_size=1, max_size=6, unique=True)
        )
        for ano in anos:
            mandatos = []
            for firma in desenho(st.lists(FIRMAS, min_size=1, max_size=2)):
                inicio = date(desenho(st.integers(2005, ano)), 1, 1)
                encerrado = desenho(st.booleans())
                fim = date(ano - 1, 12, 31) if encerrado and inicio.year < ano else ""
                mandatos.append((firma, inicio.isoformat(), str(fim)))
            # o FCA de um ano pode ser reapresentado no ano seguinte (o acervo só tem a última versão)
            entrega = ano + desenho(st.integers(0, 1))
            dia = desenho(st.integers(1, 28))
            mes = desenho(st.integers(1, 12))
            partes.append(
                _ano(
                    ano,
                    f"{entrega}-{mes:02d}-{dia:02d}",
                    *mandatos,
                    documento=f"{cnpj[:2]}{ano}",
                    cnpj=cnpj,
                )
            )
    return pd.concat(partes, ignore_index=True)


@settings(max_examples=150, deadline=None)
@given(_historias(), st.dates(date(2010, 1, 1), date(2025, 1, 1)))
def test_trocas_conhecidas_ate_uma_data_nao_dependem_do_futuro(tabela, corte):
    """Montar só com os FCAs entregues até o corte dá as mesmas trocas que montar com tudo e cortar."""
    com_tudo = auditores.trocas_de_auditor(tabela)
    ate_o_corte = auditores.trocas_de_auditor(tabela[tabela["conhecido_em"] <= corte])
    esperado = com_tudo[com_tudo["conhecido_em"] <= corte].reset_index(drop=True)
    pd.testing.assert_frame_equal(
        ate_o_corte.reset_index(drop=True), esperado, check_dtype=False
    )


def test_trocas_saem_dos_anos_de_auditores_gravados_na_base(tmp_path, monkeypatch):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    for ano, tabela in {
        2019: _ano(2019, "2019-05-10", (KPMG, "2014-01-01")),
        2020: _ano(2020, "2020-06-15", (EY, "2020-04-01")),
    }.items():
        (tmp_path / "auditores").mkdir(exist_ok=True)
        tabela.to_parquet(tmp_path / "auditores" / f"{ano}.parquet", index=False)
    agora = datetime(2026, 10, 14, 12, tzinfo=UTC)

    assert auditores.montar_trocas(tmp_path, agora) == 1

    gravada = pd.read_parquet(tmp_path / "trocas_de_auditor" / "trocas.parquet")
    assert gravada["novo_id"].tolist() == ["rede:ey"]
    assert parquets_sem_manifesto(tmp_path / "trocas_de_auditor") == []
    assert str(gravada["conhecido_em"].iloc[0])[:10] == "2020-06-15"
    assert gravada["montado_em"].iloc[0] == agora.isoformat()
    assert gravada["versao_do_codigo"].iloc[0] == "0123abc"


def test_sem_auditores_gravados_nao_monta_trocas(tmp_path):
    assert auditores.montar_trocas(tmp_path, datetime(2026, 10, 14, tzinfo=UTC)) == 0
    assert not (tmp_path / "trocas_de_auditor").exists()


URL_DO_CADASTRO = (
    "https://dados.cvm.gov.br/dados/CIA_ABERTA/CAD/DADOS/cad_cia_aberta.csv"
)
URL_DO_FCA = (
    "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/FCA/DADOS/fca_cia_aberta_{}.zip"
)


def _guardar_cadastro(registro: str) -> str:
    """O `cad_cia_aberta.csv` no acervo, com a companhia registrada em `registro`."""
    conteudo = (
        "CNPJ_CIA;DENOM_SOCIAL;DT_REG;DT_CANCEL;MOTIVO_CANCEL;SIT;SETOR_ATIV;UF\n"
        f"{CIA};EMPRESA UM;{registro};;;ATIVO;Energia;SP\n"
    ).encode("latin-1")
    com_registro("cvm-cadastros", lambda _url: conteudo)(URL_DO_CADASTRO)
    return hashlib.sha256(conteudo).hexdigest()


def _guardar_fca(ano: int, recebido: str, firma) -> None:
    conteudo = _zip(
        [_documento(str(ano), recebido, ano=ano)],
        [_mandato(firma, f"{ano}-01-01", documento=str(ano), ano=ano)],
        ano=ano,
    )
    com_registro("cvm-hist-fca", lambda _url: conteudo)(URL_DO_FCA.format(ano))


def test_fca_do_pedido_de_registro_vale_a_partir_do_registro(banco, tmp_path):
    """O FCA mandado com a empresa em registro só fica público perto do registro: em 20 de 59
    páginas do ENET, 18 a 213 dias depois do `DT_RECEB`, e sempre antes do registro (conferência
    de 16/10/2026, `base/conferidas/fca_pedido_de_registro_enet.csv`)."""
    sha_do_cadastro = _guardar_cadastro("2022-03-29")
    _guardar_fca(2021, "2021-12-21", KPMG)  # em registro: vale a partir de 29/03/2022
    _guardar_fca(2022, "2022-05-20", EY)  # já registrada: vale o dia do recebimento
    with banco.connect() as conexao:
        historico.montar(
            "auditores", conexao, tmp_path, datetime(2026, 10, 16, tzinfo=UTC)
        )

    datas = {
        ano: pd.read_parquet(tmp_path / "auditores" / f"{ano}.parquet")[
            "conhecido_em"
        ].iloc[0]
        for ano in (2021, 2022)
    }
    assert datas == {2021: date(2022, 3, 29), 2022: date(2022, 5, 20)}
    manifesto = json.loads(
        (tmp_path / "auditores" / "2021.json").read_text(encoding="utf-8")
    )
    assert sha_do_cadastro in {o["sha256"] for o in manifesto["origens"]}


def test_sem_cadastro_no_acervo_os_auditores_nao_sao_montados(banco, tmp_path):
    _guardar_fca(2021, "2021-12-21", KPMG)
    with banco.connect() as conexao, pytest.raises(historico.ArquivoIlegivel):
        historico.montar(
            "auditores", conexao, tmp_path, datetime(2026, 10, 16, tzinfo=UTC)
        )
    assert not (tmp_path / "auditores").exists()


def test_comando_monta_auditores_e_depois_as_trocas(banco, tmp_path, monkeypatch):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    from scripts import montar_base_historica

    _guardar_cadastro("2001-01-01")
    for ano, recebido, firma in ((2019, "2019-05-10", KPMG), (2020, "2020-06-15", EY)):
        conteudo = _zip(
            [_documento(str(ano), recebido, ano=ano)],
            [_mandato(firma, f"{ano}-01-01", documento=str(ano), ano=ano)],
            ano=ano,
        )
        url = f"https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/FCA/DADOS/fca_cia_aberta_{ano}.zip"
        com_registro("cvm-hist-fca", lambda _url, c=conteudo: c)(url)
    pasta = tmp_path / "b"

    saida = montar_base_historica.main(
        ["auditores", "trocas_de_auditor", "--pasta", str(pasta)]
    )

    assert saida == 0
    assert (pasta / "auditores" / "2020.parquet").exists()
    trocas = pd.read_parquet(pasta / "trocas_de_auditor" / "trocas.parquet")
    assert trocas["anterior_id"].tolist() == ["rede:kpmg"]


def test_cnpj_alfanumerico_atravessa_auditores():
    """Firma de auditoria com CNPJ novo (com letras) continua pessoa jurídica, com nome e raiz."""
    nova = ("Nova Auditores", "12.ABC.345/01DE-35", "")
    linha = _ano(2027, "2027-05-01", (nova, "2027-01-01")).iloc[0]
    assert linha["auditor_cnpj"] == "12ABC34501DE35"
    assert linha["auditor"] == "Nova Auditores"
    assert linha["auditor_id"] == "cnpj:12ABC345"


def test_trocas_ignoram_versoes_guardadas_dos_auditores(tmp_path, monkeypatch):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    (tmp_path / "auditores").mkdir()
    _ano(2019, "2019-05-10", (KPMG, "2014-01-01")).to_parquet(
        tmp_path / "auditores" / "2019.parquet", index=False
    )
    _ano(2020, "2020-06-15", (EY, "2020-04-01")).to_parquet(
        tmp_path / "auditores" / "2019.v1.parquet", index=False
    )
    assert auditores.montar_trocas(tmp_path, datetime(2026, 10, 14, tzinfo=UTC)) == 0


CONFERIDAS = Path(__file__).resolve().parent.parent / "base" / "conferidas"


def test_no_fca_do_pedido_de_registro_o_registro_seguinte_nunca_e_cedo_demais():
    """60 FCAs sorteados entre os 397 com `DT_RECEB` antes do 1º registro (semente 20261018), com a
    "Data do Envio" da página do ENET: a data que a base usa nunca vem antes do dia público."""
    conferidos = pd.read_csv(
        CONFERIDAS / "fca_pedido_de_registro_enet.csv", sep=";", dtype=str
    ).fillna("")
    recebido = pd.to_datetime(conferidos["recebido_em"])
    cadastro = pd.DataFrame(
        {
            "cnpj": conferidos["cnpj"],
            "registro": pd.to_datetime(conferidos["primeiro_registro"]),
            "cancelamento": pd.NaT,
        }
    ).drop_duplicates("cnpj")
    publica = divulgacao_publica(conferidos["cnpj"], recebido, cadastro)
    enviado = pd.to_datetime(conferidos["enviado_no_enet"]).dt.normalize()
    com_pagina = enviado.notna()

    assert len(conferidos) == 60
    assert (recebido < pd.to_datetime(conferidos["primeiro_registro"])).all()
    assert (publica[com_pagina] >= enviado[com_pagina]).all()
    # o que a conferência mediu: o recebimento sozinho erraria 1 em 3
    diferem = enviado[com_pagina] > recebido[com_pagina]
    assert (int(diferem.sum()), int((~com_pagina).sum())) == (20, 1)
