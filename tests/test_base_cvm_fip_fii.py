"""Informes dos FIP e dos FII e cadastro dos administradores de FII, da CVM (linha 904, lote 1 das 300
tabelas pelo CNPJ). Só CNPJ de DV certo, nada de contato, endereço ou nome do administrador, MEI marcado
como pessoa (no fundo e no emissor), `disponivel_em` nunca depois do arquivo e o passado igual quando o
futuro é cortado. Arquivos de mentira, no formato conferido em 13/11/2026; nomes e números inventados."""

import hashlib
import io
import zipfile
from datetime import UTC, date, datetime

import pandas as pd
import sqlalchemy as sa

from base import cadastros_em_retrato as montagem
from base import cnpj as cnpjs
from base import cvm_fip_fii
from base.ancoragem import parquets_sem_manifesto
from base.arquivo.destinos import DESTINOS, TABELA
from base.dicionario import TABELAS
from src.banco import coletas
from src.banco.coletas import com_registro

AGORA = datetime(2026, 12, 1, 22, tzinfo=UTC)
PRIMEIRO_DIA = date(2026, 11, 4)
SEGUNDO_DIA = date(2026, 12, 1)
CVM = "https://dados.cvm.gov.br/dados"
URL_FIP_2021 = f"{CVM}/FIP/DOC/INF_TRIMESTRAL/DADOS/inf_trimestral_fip_2021.csv"
URL_FIP_2024 = f"{CVM}/FIP/DOC/INF_QUADRIMESTRAL/DADOS/inf_quadrimestral_fip_2024.csv"
URL_META_DO_FIP = f"{CVM}/FIP/DOC/INF_TRIMESTRAL/META/meta_inf_trimestral_fip.csv"
URL_MENSAL_2025 = f"{CVM}/FII/DOC/INF_MENSAL/DADOS/inf_mensal_fii_2025.zip"
URL_META_DO_MENSAL = f"{CVM}/FII/DOC/INF_MENSAL/META/meta_inf_mensal_fii.zip"
URL_TRIMESTRAL_2025 = f"{CVM}/FII/DOC/INF_TRIMESTRAL/DADOS/inf_trimestral_fii_2025.zip"
URL_ADMINISTRADORES = f"{CVM}/ADM_FII/CAD/DADOS/cad_adm_fii.csv"

TABELAS_NOVAS = (
    cvm_fip_fii.TABELA_DOS_FIP,
    cvm_fip_fii.TABELA_DO_MENSAL,
    cvm_fip_fii.TABELA_DOS_ATIVOS,
    cvm_fip_fii.TABELA_DOS_ADMINISTRADORES,
)
# nenhuma coluna de CPF, de nome de pessoa nem de contato (ADR 0075)
PEDACOS_DE_PESSOA = (
    "cpf", "telefone", "email", "e_mail", "endereco", "logradouro", "bairro", "cep",
    "complemento", "site", "nome_administrador", "vinculo_familiar", "ddd", "tel",
)  # fmt: skip


def _cnpj(raiz: str, filial: str = "0001") -> str:
    for dv in range(100):
        bruto = f"{raiz}{filial}{dv:02d}"
        if cnpjs.dv_confere(bruto):
            return bruto
    raise AssertionError(raiz)


FUNDO = _cnpj("11222333")
OUTRO_FUNDO = _cnpj("33000167")
FUNDO_MEI = _cnpj("44555666")
EMISSOR = _cnpj("55666777")
EMISSOR_MEI = _cnpj("66777888")
ADMINISTRADORA = _cnpj("77888999")
CPF = "888.000.005-51"


def _coletar(banco, fonte: str, url: str, conteudo: bytes, dia: date) -> None:
    com_registro(fonte, lambda _url: conteudo)(url)
    with banco.begin() as conexao:
        conexao.execute(
            sa.update(coletas.coletas)
            .where(
                coletas.coletas.c.url == url,
                coletas.coletas.c.sha256 == hashlib.sha256(conteudo).hexdigest(),
            )
            .values(baixado_em=datetime(dia.year, dia.month, dia.day, 3, tzinfo=UTC))
        )


def _csv(cabecalho: str, *linhas: str) -> bytes:
    return "\r\n".join([cabecalho, *linhas]).encode("latin-1")


def _zip(**membros: bytes) -> bytes:
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as zip_:
        for nome, conteudo in membros.items():
            zip_.writestr(f"{nome}.csv", conteudo)
    return saida.getvalue()


def _montar(banco, tmp_path, pessoas=frozenset()) -> dict:
    with banco.connect() as conexao:
        return cvm_fip_fii.montar(
            conexao, tmp_path / "base", AGORA, pessoas=set(pessoas)
        )


def _ler(tmp_path, tabela: str, nome: str) -> pd.DataFrame:
    return pd.read_parquet(tmp_path / "base" / tabela / f"{nome}.parquet")


# --- FIP --------------------------------------------------------------------------------------------

CABECALHO_FIP_2021 = (
    "CNPJ_FUNDO;DENOM_SOCIAL;DT_COMPTC;VL_PATRIM_LIQ;QT_COTA;VL_PATRIM_COTA;NR_COTST;ENTID_INVEST;"
    "PUBLICO_ALVO;VL_CAP_COMPROM;QT_COTA_SUBSCR;VL_CAP_SUBSCR;QT_COTA_INTEGR;VL_CAP_INTEGR;"
    "VL_INVEST_FIP_COTA;NR_COTST_SUBSCR_PF;PR_COTA_SUBSCR_PF;NR_COTST_SUBSCR_PJ_NAO_FINANC;"
    "NR_COTST_SUBSCR_INVNR;NR_COTST_SUBSCR_EFPC;NR_COTST_SUBSCR_RPPS"
)
CABECALHO_FIP_2024 = "TP_FUNDO_CLASSE;" + CABECALHO_FIP_2021.replace(
    "CNPJ_FUNDO;", "CNPJ_FUNDO_CLASSE;"
)


def _fip(cnpj: str, nome: str, competencia: str, patrimonio: str) -> str:
    return (
        f"{cnpj};{nome};{competencia};{patrimonio};1000;{patrimonio};3;N;Profissional;"
        "5000000;1000;4000000;800;3000000;0;1;10,5;1;0;1;0"
    )


def test_fip_junta_o_trimestral_e_o_quadrimestral_so_com_cnpj_de_dv_certo(
    banco, tmp_path
):
    _coletar(
        banco,
        "cvm-fip-trimestral",
        URL_FIP_2021,
        _csv(
            CABECALHO_FIP_2021,
            _fip(cnpjs.formatar(FUNDO), "FIP INVENTADO", "2021-03-31", "1234567,89"),
            _fip(FUNDO_MEI, "FIP DO MEI", "2021-03-31", "10"),
            _fip(CPF, "SEM CNPJ", "2021-03-31", "1"),
            _fip("11.111.111/0001-11", "DV ERRADO", "2021-03-31", "1"),
        ),
        PRIMEIRO_DIA,
    )
    _coletar(
        banco,
        "cvm-fip-trimestral",
        URL_META_DO_FIP,
        b"dicionario",
        PRIMEIRO_DIA,
    )
    _coletar(
        banco,
        "cvm-fip-quadrimestral",
        URL_FIP_2024,
        _csv(
            CABECALHO_FIP_2024,
            "FIP;" + _fip(OUTRO_FUNDO, "FIP CLASSE", "2024-04-30", "99"),
        ),
        PRIMEIRO_DIA,
    )
    resumo = _montar(banco, tmp_path, pessoas={FUNDO_MEI[:8]})
    assert set(resumo) == {"inf_trimestral_fip_2021", "inf_quadrimestral_fip_2024"}
    assert resumo["inf_trimestral_fip_2021"]["cnpj_invalido"] == 2

    antigo = _ler(tmp_path, "fip_informe", "inf_trimestral_fip_2021")
    assert list(antigo["cnpj"]) == [cnpjs.formatar(FUNDO), cnpjs.formatar(FUNDO_MEI)]
    assert list(antigo["trata_como_pessoa"]) == [False, True]
    assert antigo["periodicidade"].unique().tolist() == ["trimestral"]
    assert antigo["patrimonio_liquido"].iloc[0] == 1234567.89
    assert antigo["id_na_fonte"].iloc[0] == f"{cnpjs.formatar(FUNDO)}|2021-03-31"
    assert set(antigo["disponivel_em"]) == {
        PRIMEIRO_DIA
    }  # sem data de entrega: o dia do arquivo

    novo = _ler(tmp_path, "fip_informe", "inf_quadrimestral_fip_2024")
    assert novo[["cnpj", "tipo_fundo_classe", "periodicidade"]].values.tolist() == [
        [cnpjs.formatar(OUTRO_FUNDO), "FIP", "quadrimestral"]
    ]
    assert list(antigo.columns) == list(novo.columns)
    assert parquets_sem_manifesto(tmp_path / "base") == []


def test_fip_repetido_no_arquivo_fica_com_a_ultima_linha():
    tabela, contagem = cvm_fip_fii.ler_fip(
        _csv(
            CABECALHO_FIP_2021,
            _fip(FUNDO, "FIP", "2021-03-31", "1"),
            _fip(FUNDO, "FIP", "2021-03-31", "2"),
        ),
        "trimestral",
    )
    assert contagem["repetido_no_arquivo"] == 1
    assert list(tabela["patrimonio_liquido"]) == [2.0]


# --- FII: informe mensal ----------------------------------------------------------------------------

CABECALHO_GERAL = (
    "Tipo_Fundo_Classe;CNPJ_Fundo_Classe;Data_Referencia;Versao;Data_Entrega;Nome_Fundo_Classe;"
    "Data_Funcionamento;Publico_Alvo;Codigo_ISIN;Quantidade_Cotas_Emitidas;Fundo_Exclusivo;"
    "Cotistas_Vinculo_Familiar;Mandato;Segmento_Atuacao;Tipo_Gestao;Prazo_Duracao;Data_Prazo_Duracao;"
    "Encerramento_Exercicio_Social;Mercado_Negociacao_Bolsa;Mercado_Negociacao_MBO;"
    "Mercado_Negociacao_MB;Entidade_Administradora_BVMF;Entidade_Administradora_CETIP;"
    "Nome_Administrador;CNPJ_Administrador;Logradouro;Numero;Complemento;Bairro;Cidade;Estado;CEP;"
    "Telefone1;Telefone2;Telefone3;Site;Email"
)
CABECALHO_COMPLEMENTO = (
    "CNPJ_Fundo_Classe;Data_Referencia;Versao;Data_Informacao_Numero_Cotistas;Total_Numero_Cotistas;"
    "Numero_Cotistas_Pessoa_Fisica;Valor_Ativo;Patrimonio_Liquido;Cotas_Emitidas;"
    "Valor_Patrimonial_Cotas;Percentual_Despesas_Taxa_Administracao;"
    "Percentual_Rentabilidade_Efetiva_Mes;Percentual_Rentabilidade_Patrimonial_Mes;"
    "Percentual_Dividend_Yield_Mes"
)


def _geral(cnpj: str, referencia: str, versao: str, entrega: str) -> str:
    return (
        f"Classe;{cnpj};{referencia};{versao};{entrega};FII INVENTADO;2010-01-01;Geral;BRXXXXCTF000;"
        "1000;N;N;Renda;Logística;Ativa;Indeterminado;;12;S;N;N;S;N;"
        f"ADMINISTRADORA INVENTADA;{cnpjs.formatar(ADMINISTRADORA)};Rua Inventada;1;sala 2;Centro;"
        "Cidade;SP;01000-000;(11) 0000-0000;;;exemplo.invalid;contato@exemplo.invalid"
    )


def _complemento(cnpj: str, referencia: str, versao: str, patrimonio: str) -> str:
    return (
        f"{cnpj};{referencia};{versao};{referencia};120;100;{patrimonio};{patrimonio};1000;"
        "98,5;0,08;1,1;0,9;0,7"
    )


def test_fii_mensal_junta_geral_e_complemento_sem_contato_e_vale_a_data_de_entrega(
    banco, tmp_path
):
    conteudo = _zip(
        inf_mensal_fii_geral_2025=_csv(
            CABECALHO_GERAL,
            _geral(FUNDO, "2025-01-01", "1", "2025-02-10"),
            _geral(FUNDO, "2025-01-01", "2", "2025-03-05"),
            # entrega depois do arquivo (data errada na fonte): nunca passa do dia em que foi visto
            _geral(OUTRO_FUNDO, "2025-01-01", "1", "2027-01-01"),
            _geral(CPF, "2025-01-01", "1", "2025-02-10"),
        ),
        inf_mensal_fii_complemento_2025=_csv(
            CABECALHO_COMPLEMENTO,
            _complemento(FUNDO, "2025-01-01", "1", "1000,5"),
            _complemento(FUNDO, "2025-01-01", "2", "1001,5"),
        ),
    )
    _coletar(banco, "cvm-fii-mensal", URL_MENSAL_2025, conteudo, PRIMEIRO_DIA)
    _coletar(banco, "cvm-fii-mensal", URL_META_DO_MENSAL, _zip(meta=b"x"), PRIMEIRO_DIA)
    resumo = _montar(banco, tmp_path)
    assert set(resumo) == {"inf_mensal_fii_2025"}
    assert resumo["inf_mensal_fii_2025"]["cnpj_invalido"] == 1

    mensal = _ler(tmp_path, "fii_informe_mensal", "inf_mensal_fii_2025")
    por_id = mensal.set_index("id_na_fonte")
    versao_2 = por_id.loc[f"{cnpjs.formatar(FUNDO)}|2025-01-01|2"]
    assert versao_2["patrimonio_liquido"] == 1001.5
    assert versao_2["dividend_yield_no_mes"] == 0.7
    assert versao_2["cnpj_administrador"] == cnpjs.formatar(ADMINISTRADORA)
    assert versao_2["segmento_de_atuacao"] == "Logística"
    assert versao_2["disponivel_em"] == date(2025, 3, 5)
    outro = por_id.loc[f"{cnpjs.formatar(OUTRO_FUNDO)}|2025-01-01|1"]
    assert outro["disponivel_em"] == PRIMEIRO_DIA
    assert pd.isna(outro["patrimonio_liquido"])  # sem complemento: vazio, não zero
    assert (mensal["disponivel_em"] <= mensal["visto_em"]).all()
    assert "ADMINISTRADORA INVENTADA" not in mensal.astype(str).to_numpy()


# --- FII: ativos ------------------------------------------------------------------------------------

CABECALHO_ATIVO = (
    "CNPJ_Fundo_Classe;Data_Referencia;Versao;Tipo;Emissor;CNPJ_Emissor;Emissao;Serie;Codigo_Acao;"
    "Nome_Ativo;Data_Vencimento;Quantidade;Valor"
)
CABECALHO_GERAL_TRIMESTRAL = (
    CABECALHO_GERAL + ";Fundo_Nao_Listado_Exclusivo;Data_Encerramento_Trimestre"
)


def _ativo(emissor: str, cnpj_emissor: str, valor: str) -> str:
    return f"{FUNDO};2025-03-01;1;CRI;{emissor};{cnpj_emissor};1;2;;CRI INVENTADO;2030-12-15;10;{valor}"


def _trimestral(*ativos: str) -> bytes:
    return _zip(
        inf_trimestral_fii_ativo_2025=_csv(CABECALHO_ATIVO, *ativos),
        inf_trimestral_fii_ativo_garantia_rentabilidade_2025=_csv("CNPJ_Fundo_Classe"),
        inf_trimestral_fii_geral_2025=_csv(
            CABECALHO_GERAL_TRIMESTRAL,
            _geral(FUNDO, "2025-03-01", "1", "2025-05-02") + ";N;2025-03-31",
        ),
    )


def test_fii_ativos_marca_o_emissor_mei_e_nao_guarda_nome_de_emissor_sem_cnpj(
    banco, tmp_path
):
    _coletar(
        banco,
        "cvm-fii-trimestral",
        URL_TRIMESTRAL_2025,
        _trimestral(
            _ativo("SECURITIZADORA INVENTADA", cnpjs.formatar(EMISSOR), "100,5"),
            _ativo("SECURITIZADORA INVENTADA", cnpjs.formatar(EMISSOR), "100,5"),
            _ativo("EMISSOR MEI", EMISSOR_MEI, "7"),
            _ativo("PESSOA INVENTADA", CPF, "3"),
        ),
        PRIMEIRO_DIA,
    )
    resumo = _montar(banco, tmp_path, pessoas={EMISSOR_MEI[:8]})
    assert resumo["inf_trimestral_fii_2025"]["emissor_sem_cnpj"] == 1
    ativos = _ler(tmp_path, "fii_ativos", "inf_trimestral_fii_2025")
    assert ativos["id_na_fonte"].is_unique  # o mesmo ativo duas vezes: duas linhas
    assert len(ativos) == 4
    pela_raiz = dict(
        zip(ativos["cnpj_basico_emissor"], ativos["trata_como_pessoa"], strict=True)
    )
    assert not pela_raiz[EMISSOR[:8]]
    assert pela_raiz[EMISSOR_MEI[:8]]
    sem_cnpj = ativos[ativos["cnpj_emissor"].isna()].iloc[0]
    assert pd.isna(sem_cnpj["emissor"])
    assert not sem_cnpj["trata_como_pessoa"]
    assert set(ativos["disponivel_em"]) == {date(2025, 5, 2)}
    assert ativos["valor"].iloc[0] == 100.5


# --- FII: administradores ---------------------------------------------------------------------------

CABECALHO_ADMINISTRADORES = (
    "CNPJ;DENOM_SOCIAL;DENOM_COMERC;DT_REG;DT_CANCEL;MOTIVO_CANCEL;SIT;DT_INI_SIT;TP_ENDER;LOGRADOURO;"
    "COMPL;BAIRRO;MUN;UF;CEP;DDD;TEL;EMAIL"
)


def _administrador(cnpj: str, situacao: str) -> str:
    return (
        f"{cnpj};ADMINISTRADORA INVENTADA S.A.;INVENTADA;1999-01-01;;;{situacao};1999-01-01;Sede;"
        "Rua Inventada;sala 1;Centro;Cidade;RJ;20000-000;21;00000000;contato@exemplo.invalid"
    )


def test_administradores_sem_endereco_nem_contato(banco, tmp_path):
    _coletar(
        banco,
        "cvm-fii-administradores",
        URL_ADMINISTRADORES,
        _csv(
            CABECALHO_ADMINISTRADORES,
            _administrador(cnpjs.formatar(ADMINISTRADORA), "EM FUNCIONAMENTO NORMAL"),
            _administrador(CPF, "EM FUNCIONAMENTO NORMAL"),
        ),
        PRIMEIRO_DIA,
    )
    resumo = _montar(banco, tmp_path)
    assert resumo["administradores"]["cnpj_invalido"] == 1
    tabela = _ler(tmp_path, "fii_administradores", "administradores")
    assert list(tabela["cnpj"]) == [cnpjs.formatar(ADMINISTRADORA)]
    assert tabela["uf"].tolist() == ["RJ"]
    texto = tabela.astype(str).to_numpy()
    assert "Rua Inventada" not in texto
    assert "contato@exemplo.invalid" not in texto


def test_administrador_que_sai_do_cadastro_ganha_a_linha_consta_falso(banco, tmp_path):
    fonte = "cvm-fii-administradores"
    todos = [
        _administrador(cnpjs.formatar(cnpj), "EM FUNCIONAMENTO NORMAL")
        for cnpj in (ADMINISTRADORA, EMISSOR, OUTRO_FUNDO, FUNDO)
    ]
    _coletar(
        banco,
        fonte,
        URL_ADMINISTRADORES,
        _csv(CABECALHO_ADMINISTRADORES, *todos),
        PRIMEIRO_DIA,
    )
    _coletar(
        banco,
        fonte,
        URL_ADMINISTRADORES,
        _csv(CABECALHO_ADMINISTRADORES, *todos[:3]),
        SEGUNDO_DIA,
    )
    _montar(banco, tmp_path)
    tabela = _ler(tmp_path, "fii_administradores", "administradores")
    saida = tabela[tabela["visto_em"] == SEGUNDO_DIA]
    assert saida["cnpj"].tolist() == [cnpjs.formatar(FUNDO)]
    assert not saida["consta"].iloc[0]
    assert saida["disponivel_em"].iloc[0] == SEGUNDO_DIA


# --- regras comuns ----------------------------------------------------------------------------------


def test_nenhuma_coluna_de_cpf_nome_de_pessoa_ou_contato():
    for colunas in (
        cvm_fip_fii.COLUNAS_DO_FIP,
        cvm_fip_fii.COLUNAS_DO_MENSAL,
        cvm_fip_fii.COLUNAS_DOS_ATIVOS,
        cvm_fip_fii.COLUNAS_DOS_ADMINISTRADORES,
    ):
        for coluna in colunas:
            partes = coluna.split("_")
            assert not any(p in partes or p == coluna for p in PEDACOS_DE_PESSOA), (
                coluna
            )


def test_cortar_o_futuro_nao_muda_o_passado_e_retrato_repetido_e_pulado(
    banco, tmp_path
):
    primeiro = _zip(
        inf_mensal_fii_geral_2025=_csv(
            CABECALHO_GERAL, _geral(FUNDO, "2025-01-01", "1", "2025-02-10")
        ),
        inf_mensal_fii_complemento_2025=_csv(
            CABECALHO_COMPLEMENTO, _complemento(FUNDO, "2025-01-01", "1", "10")
        ),
    )
    _coletar(banco, "cvm-fii-mensal", URL_MENSAL_2025, primeiro, PRIMEIRO_DIA)
    _montar(banco, tmp_path)
    passado = _ler(tmp_path, "fii_informe_mensal", "inf_mensal_fii_2025")
    assert _montar(banco, tmp_path)["inf_mensal_fii_2025"] == montagem.JA_MONTADO

    segundo = _zip(
        inf_mensal_fii_geral_2025=_csv(
            CABECALHO_GERAL,
            _geral(FUNDO, "2025-01-01", "1", "2025-02-10"),
            _geral(FUNDO, "2025-02-01", "1", "2025-03-10"),
        ),
        inf_mensal_fii_complemento_2025=_csv(
            CABECALHO_COMPLEMENTO,
            _complemento(FUNDO, "2025-01-01", "1", "10"),
            _complemento(FUNDO, "2025-02-01", "1", "11"),
        ),
    )
    _coletar(banco, "cvm-fii-mensal", URL_MENSAL_2025, segundo, SEGUNDO_DIA)
    assert _montar(banco, tmp_path)["inf_mensal_fii_2025"]["retratos"] == 2
    tudo = _ler(tmp_path, "fii_informe_mensal", "inf_mensal_fii_2025")
    ate_o_primeiro = tudo[tudo["visto_em"] <= PRIMEIRO_DIA].drop(
        columns=["origem_coletada_em", "montado_em", "versao_do_codigo"]
    )
    pd.testing.assert_frame_equal(
        ate_o_primeiro.reset_index(drop=True),
        passado.drop(columns=["origem_coletada_em", "montado_em", "versao_do_codigo"]),
    )
    novo = tudo[tudo["visto_em"] == SEGUNDO_DIA].iloc[0]
    assert (
        novo["disponivel_em"] == SEGUNDO_DIA
    )  # visto só no 2º arquivo: vale o dia dele


def test_cada_tabela_tem_dicionario_contrato_de_pessoa_e_destino():
    for tabela in TABELAS_NOVAS:
        assert tabela in TABELAS
        assert not TABELAS[tabela].pessoa
        assert TABELAS[tabela].linhas_de_pessoa == "trata_como_pessoa"
    for fonte, tabelas in {
        "cvm-fip-trimestral": ("fip_informe",),
        "cvm-fip-quadrimestral": ("fip_informe",),
        "cvm-fii-mensal": ("fii_informe_mensal",),
        "cvm-fii-trimestral": ("fii_ativos",),
        "cvm-fii-administradores": ("fii_administradores",),
    }.items():
        assert DESTINOS[fonte].tipo == TABELA
        assert DESTINOS[fonte].tabelas == tabelas


def test_comando_de_carga_sem_nada_guardado_sai_com_1_e_com_arquivo_sai_com_0(
    banco, tmp_path, monkeypatch
):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    from scripts import carga_fundos_e_reguladores

    assert carga_fundos_e_reguladores.main(["--pasta", str(tmp_path / "b")]) == 1
    _coletar(
        banco,
        "cvm-fii-administradores",
        URL_ADMINISTRADORES,
        _csv(CABECALHO_ADMINISTRADORES, _administrador(ADMINISTRADORA, "NORMAL")),
        PRIMEIRO_DIA,
    )
    assert carga_fundos_e_reguladores.main(["--pasta", str(tmp_path / "b")]) == 0
    tabela = pd.read_parquet(tmp_path / "b/fii_administradores/administradores.parquet")
    assert list(tabela["cnpj"]) == [cnpjs.formatar(ADMINISTRADORA)]
