"""Agentes do setor elétrico, autos de infração e termos de notificação da ANEEL em retrato (linha 904,
lote 2): só CNPJ de DV certo (o CPF sai, inclusive o que tem "000" na frente e passa como CNPJ de filial),
nome e texto livre fora, MEI marcado como pessoa e sem olhar o futuro. Arquivos de mentira, no formato
conferido em 13/11/2026; nenhum documento real."""

import hashlib
from datetime import UTC, date, datetime

import pandas as pd
import sqlalchemy as sa

from base import aneel_fiscalizacao as fiscalizacao
from base import aneel_indicadores as comum
from base import cadastros_em_retrato as montagem
from base import cnpj as cnpjs
from base.parquet import LINHAGEM
from src.banco import coletas
from src.banco.coletas import com_registro
from tests.ajudantes_de_cpf import CPF_DE_TESTE, cpf_que_tambem_passa_como_cnpj

AGORA = datetime(2026, 12, 1, 22, tzinfo=UTC)
PRIMEIRO_DIA = date(2026, 11, 14)
SEGUNDO_DIA = date(2026, 12, 1)
PASTA = "https://dadosabertos.aneel.gov.br/dataset/x/resource"
URL_DOS_AGENTES = f"{PASTA}/1/download{fiscalizacao.ARQUIVO_DOS_AGENTES}"
URL_DOS_AUTOS = f"{PASTA}/2/download{fiscalizacao.ARQUIVO_DOS_AUTOS}"
URL_DOS_TERMOS = f"{PASTA}/3/download{fiscalizacao.ARQUIVO_DOS_TERMOS}"
PROIBIDAS = ("nom", "razao", "dsc", "cpf", "descricao", "enquadramento", "ato")
NOME_INVENTADO = "EMPRESA INVENTADA DE TESTE LTDA"


def _cnpj(raiz: str, filial: str = "0001") -> str:
    for dv in range(100):
        if cnpjs.dv_confere(bruto := f"{raiz}{filial}{dv:02d}"):
            return bruto
    raise AssertionError(raiz)


EMPRESA = _cnpj("11222333")
MEI = _cnpj("44555666")
DV_ERRADO = EMPRESA[:-1] + str((int(EMPRESA[-1]) + 1) % 10)
CPF_COM_ZEROS = (
    "000" + cpf_que_tambem_passa_como_cnpj()
)  # passa no DV de CNPJ, filial não é 0001


def _csv(
    cabecalho: list[str], padrao: dict[str, str], linhas: list[dict[str, str]]
) -> bytes:
    def linha(campos: list[str]) -> str:
        return ";".join(f'"{c}"' for c in campos)

    corpo = [
        [{**padrao, **mudanca}.get(c, "") for c in cabecalho] for mudanca in linhas
    ]
    return "\r\n".join([linha(cabecalho), *map(linha, corpo)]).encode("utf-8")


CABECALHO_DOS_AGENTES = [
    "DatGeracaoConjuntoDados", "NumCnpj", "SigPessoa", "NomRazaoSocial", "IdcAtivo",
    "IdcComercializacao", "IdcDistribuicao", "IdcGeracao", "IdcTransmissao",
]  # fmt: skip
CABECALHO_DOS_AUTOS = [
    "DatGeracaoConjuntoDados", "SigAgenteFiscalizador", "NumAutoInfracao", "DatLavraturaAutoInfracao",
    "NomNaturezaFiscalizacao", "DscObjetoFiscalizado", "CodObjetoFiscalizado", "NomAgenteFiscalizado",
    "NumCPFCNPJAgenteFiscalizado", "NumProcessoPunitivo", "NumProcessoPunitivoANEEL",
    "DatRecebimentoAutoInfracao", "DscTipoPenalidade", "VlrPenalidade", "DtRecebimentoRecurso",
    "DatDecisaoJuizo", "DscDecisaoCompletaJuizo", "DscAtoJuizo", "VlrMultaAposJuizo", "DatDecisaoDiretoria",
    "DscDecisaoCompletaDiretoria", "DscAtoDiretoria", "VlrMultaAposDiretoria", "NumTermoEncerramento",
    "DatLavraturaTE", "DscEnquadramentoAI", "NumTermoNotificacao", "NumProcessoFiscalizacao",
]  # fmt: skip
CABECALHO_DOS_TERMOS = [
    "DatGeracaoConjuntoDados", "NomNaturezaFiscalizacao", "SigAgenteFiscalizador", "SigArea", "SigSubArea",
    "DscObjeto", "CodObjeto", "NomAgenteFiscalizado", "NumCNPJ", "NumProcesso", "NumTermoNotificacao",
    "DatLavraturaTN", "DatAvisoRecebimento", "DatManifestacao", "SigDecisao", "NumDocumentoDecisao",
    "DatLavraturaDecisao",
]  # fmt: skip


def _agentes(gerado: str, *linhas: dict[str, str]) -> bytes:
    padrao = {
        "DatGeracaoConjuntoDados": gerado, "SigPessoa": "INVENT", "NomRazaoSocial": NOME_INVENTADO,
        "IdcAtivo": "A", "IdcComercializacao": "0", "IdcDistribuicao": "0", "IdcGeracao": "1",
        "IdcTransmissao": "0",
    }  # fmt: skip
    return _csv(CABECALHO_DOS_AGENTES, padrao, list(linhas))


def _autos(gerado: str, *linhas: dict[str, str]) -> bytes:
    padrao = {
        "DatGeracaoConjuntoDados": gerado, "SigAgenteFiscalizador": "ANEEL", "NumAutoInfracao": "001/2026",
        "DatLavraturaAutoInfracao": "2026-03-10", "NomNaturezaFiscalizacao": "Técnica",
        "DscObjetoFiscalizado": "Usina inventada", "CodObjetoFiscalizado": "123",
        "NomAgenteFiscalizado": NOME_INVENTADO, "DatRecebimentoAutoInfracao": "2026-03-15",
        "DscTipoPenalidade": "Multa", "VlrPenalidade": "150000,50", "VlrMultaAposJuizo": "",
        "DscDecisaoCompletaJuizo": "Decisão inventada", "DscEnquadramentoAI": "Artigo inventado",
    }  # fmt: skip
    return _csv(CABECALHO_DOS_AUTOS, padrao, list(linhas))


def _termos(gerado: str, *linhas: dict[str, str]) -> bytes:
    padrao = {
        "DatGeracaoConjuntoDados": gerado, "NomNaturezaFiscalizacao": "Técnica",
        "SigAgenteFiscalizador": "ANEEL", "SigArea": "SFE", "SigSubArea": "Geração",
        "DscObjeto": "Usina inventada", "CodObjeto": "123", "NomAgenteFiscalizado": NOME_INVENTADO,
        "NumProcesso": "48500.000001/2026-00", "NumTermoNotificacao": "TN 1/2026",
        "DatLavraturaTN": "2026-02-01", "DatAvisoRecebimento": "2026-02-05", "SigDecisao": "AI",
        "NumDocumentoDecisao": "D1", "DatLavraturaDecisao": "2026-03-01",
    }  # fmt: skip
    return _csv(CABECALHO_DOS_TERMOS, padrao, list(linhas))


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


def _coletar_os_tres(banco, dia: date, gerado: str, multa: str = "150000,50") -> None:
    agentes = _agentes(gerado, {"NumCnpj": EMPRESA}, {"NumCnpj": MEI})
    autos = _autos(
        gerado,
        {"NumCPFCNPJAgenteFiscalizado": EMPRESA, "VlrPenalidade": multa},
        {"NumCPFCNPJAgenteFiscalizado": MEI, "NumAutoInfracao": "002/2026"},
    )
    termos = _termos(
        gerado, {"NumCNPJ": EMPRESA, "SigSubArea": multa}, {"NumCNPJ": MEI}
    )
    _coletar(banco, fiscalizacao.FONTE_DOS_AGENTES, URL_DOS_AGENTES, agentes, dia)
    _coletar(banco, fiscalizacao.FONTE_DA_FISCALIZACAO, URL_DOS_AUTOS, autos, dia)
    _coletar(banco, fiscalizacao.FONTE_DA_FISCALIZACAO, URL_DOS_TERMOS, termos, dia)


def _montar(banco, pasta, pessoas=frozenset()) -> dict:
    with banco.connect() as conexao:
        return fiscalizacao.montar(conexao, pasta, AGORA, pessoas=set(pessoas))


def _ler(pasta, tabela: str, nome: str) -> pd.DataFrame:
    return pd.read_parquet(pasta / tabela / f"{nome}.parquet")


def test_agentes_so_cnpj_com_atividade_e_ativo_sem_a_razao_social():
    tabela, contagem = fiscalizacao.ler_agentes(
        _agentes(
            "2026-11-01",
            {"NumCnpj": EMPRESA, "IdcAtivo": "A", "IdcDistribuicao": "1"},
            {"NumCnpj": MEI, "IdcAtivo": "I", "SigPessoa": ""},
            {"NumCnpj": DV_ERRADO},
            {"NumCnpj": CPF_DE_TESTE},
            {"NumCnpj": CPF_COM_ZEROS},
        )
    )
    assert contagem == {
        "linhas": 5,
        "pessoa_fisica": 2,
        "cnpj_invalido": 1,
        "id_repetido": 0,
    }
    assert list(tabela["id_na_fonte"]) == [EMPRESA, MEI]
    assert list(tabela["ativo"]) == [True, False]
    assert list(tabela["distribuicao"]) == [1, 0]
    assert tabela["sigla_do_agente"].isna().tolist() == [False, True]
    assert not tabela.astype(str).isin([NOME_INVENTADO]).any().any()


def test_autos_tiram_o_cpf_o_nome_e_o_texto_e_leem_a_virgula_decimal():
    tabela, contagem = fiscalizacao.ler_autos(
        _autos(
            "2026-11-01",
            {"NumCPFCNPJAgenteFiscalizado": EMPRESA, "VlrMultaAposJuizo": "75000,25"},
            {
                "NumCPFCNPJAgenteFiscalizado": CPF_DE_TESTE,
                "NumAutoInfracao": "003/2026",
            },
            {
                "NumCPFCNPJAgenteFiscalizado": CPF_COM_ZEROS,
                "NumAutoInfracao": "004/2026",
            },
            {
                "NumCPFCNPJAgenteFiscalizado": EMPRESA
            },  # o mesmo auto repetido no retrato
            {"NumCPFCNPJAgenteFiscalizado": EMPRESA, "NumAutoInfracao": ""},
        )
    )
    assert contagem["pessoa_fisica"] == 2
    assert contagem["id_repetido"] == 1
    assert contagem["sem_numero_do_auto"] == 1
    assert len(tabela) == 1
    linha = tabela.iloc[0]
    assert linha["valor_da_penalidade"] == 150000.50
    assert linha["multa_apos_juizo"] == 75000.25
    assert pd.isna(linha["multa_apos_diretoria"])
    assert linha["lavrado_em"] == pd.Timestamp(2026, 3, 10)
    assert pd.isna(linha["recurso_recebido_em"])
    assert (
        not tabela.astype(str)
        .isin([NOME_INVENTADO, "Decisão inventada", "Usina inventada"])
        .any()
        .any()
    )


def test_termo_com_duas_decisoes_vira_duas_linhas():
    tabela, contagem = fiscalizacao.ler_termos(
        _termos(
            "2026-11-01",
            {"NumCNPJ": EMPRESA},
            {"NumCNPJ": EMPRESA, "SigDecisao": "TA", "NumDocumentoDecisao": "D2"},
            {"NumCNPJ": CPF_DE_TESTE},
        )
    )
    assert contagem["pessoa_fisica"] == 1
    assert list(tabela["decisao"]) == ["AI", "TA"]
    assert tabela["id_na_fonte"].is_unique


def test_montar_grava_as_tres_tabelas_com_as_colunas_certas_e_marca_o_mei(
    banco, tmp_path
):
    _coletar_os_tres(banco, PRIMEIRO_DIA, "2026-11-01")
    resumo = _montar(banco, tmp_path, pessoas={MEI[:8]})
    assert set(resumo) == {"agentes", "autos", "termos"}
    for cadastro in fiscalizacao.CADASTROS:
        tabela = _ler(tmp_path, cadastro.tabela, cadastro.nome)
        assert list(tabela.columns) == [
            *cadastro.colunas, *montagem.CARIMBOS_DA_LINHA, *LINHAGEM,
        ]  # fmt: skip
        assert comum.GERADO_EM not in tabela.columns
        assert not [c for c in tabela.columns if any(p in c.lower() for p in PROIBIDAS)]
        assert dict(
            zip(tabela["cnpj_basico"], tabela["trata_como_pessoa"], strict=True)
        ) == {
            EMPRESA[:8]: False,
            MEI[:8]: True,
        }
        assert set(tabela["disponivel_em"]) == {date(2026, 11, 1)}


def test_cortar_o_futuro_nao_muda_o_passado(banco, tmp_path):
    _coletar_os_tres(banco, PRIMEIRO_DIA, "2026-11-01")
    _montar(banco, tmp_path / "so_o_primeiro")
    _coletar_os_tres(banco, SEGUNDO_DIA, "2026-11-28", multa="9,5")
    _montar(banco, tmp_path / "com_os_dois")
    for cadastro in fiscalizacao.CADASTROS[
        1:
    ]:  # o cadastro de agentes não muda entre os dois
        antes = _ler(tmp_path / "so_o_primeiro", cadastro.tabela, cadastro.nome)
        depois = _ler(tmp_path / "com_os_dois", cadastro.tabela, cadastro.nome)
        ja_valiam = depois[depois["disponivel_em"] <= PRIMEIRO_DIA]
        pd.testing.assert_frame_equal(
            ja_valiam.drop(columns=list(LINHAGEM)).reset_index(drop=True),
            antes.drop(columns=list(LINHAGEM)),
        )
        mudou = depois[depois["disponivel_em"] > PRIMEIRO_DIA]
        assert list(mudou["cnpj_basico"]) == [EMPRESA[:8]]
        assert list(mudou["disponivel_em"]) == [SEGUNDO_DIA]
        assert (depois["disponivel_em"] <= depois["visto_em"]).all()


def test_segundo_montar_sem_retrato_novo_e_ja_montado(banco, tmp_path):
    _coletar_os_tres(banco, PRIMEIRO_DIA, "2026-11-01")
    _montar(banco, tmp_path)
    assert _montar(banco, tmp_path) == dict.fromkeys(
        ("agentes", "autos", "termos"), montagem.JA_MONTADO
    )


def test_cpf_com_zeros_que_passa_como_cnpj_de_filial_conta_como_pessoa_e_a_matriz_nao():
    cnpj, de_cpf = comum.documentos(
        pd.Series([CPF_COM_ZEROS, EMPRESA, "00000000000191"])
    )
    assert cnpj.isna().tolist() == [True, False, False]
    assert de_cpf.tolist() == [True, False, False]
