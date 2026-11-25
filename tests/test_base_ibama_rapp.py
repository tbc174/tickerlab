"""RAPP do IBAMA em retrato (linha 1074): emissões, efluentes, energia e a cadeia dos resíduos sólidos. Só pessoa
jurídica (o CPF de quem declara sai; o da outra ponta vira vazio), os dois formatos de número, a célula ilegível,
a linha quebrada e sem olhar o futuro (a linha vale desde o dia do arquivo, nunca desde o ano declarado). Arquivos
de mentira, no formato conferido em 25/11/2026; nenhum documento real."""

import hashlib
from datetime import UTC, date, datetime

import pandas as pd
import pytest
import sqlalchemy as sa

from base import cadastros_em_retrato as montagem
from base import cnpj as cnpjs
from base import ibama_rapp as rapp
from base.parquet import LINHAGEM
from src.banco import coletas
from src.banco.coletas import com_registro
from tests.ajudantes_de_cpf import CPF_DE_TESTE

AGORA = datetime(2026, 12, 1, 22, tzinfo=UTC)
DIA = date(2026, 11, 25)
NOME_INVENTADO = "INDUSTRIA INVENTADA DE TESTE LTDA"
LUGAR_INVENTADO = "CIDADE INVENTADA"
# o que a fonte traz e a tabela não leva: nome, lugar e texto livre
DA_FONTE_QUE_SAI = {
    "Razão Social": NOME_INVENTADO,
    "Município": LUGAR_INVENTADO,
    "Estado": "XX",
    "Latitude": "-1.5",
    "Longitude": "-2.5",
    "Observação": "TEXTO LIVRE INVENTADO",
}
PROIBIDAS = (
    "razao",
    "nome",
    "municipio",
    "estado",
    "latitude",
    "longitude",
    "observ",
    "cpf",
)


def _cnpj(raiz: str, filial: str = "0001") -> str:
    for dv in range(100):
        if cnpjs.dv_confere(bruto := f"{raiz}{filial}{dv:02d}"):
            return bruto
    raise AssertionError(raiz)


EMPRESA = _cnpj("11222333")
OUTRA = _cnpj("22333444")
MEI = _cnpj("44555666")
DV_ERRADO = EMPRESA[:-1] + str((int(EMPRESA[-1]) + 1) % 10)


def _formatado(cnpj: str) -> str:
    return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"


def _arquivo(relatorio: rapp.Relatorio, *linhas: dict[str, str]) -> bytes:
    """O CSV do relatório: as colunas que a tabela lê mais as que saem, cada linha com um valor padrão."""
    cabecalho = [*relatorio.colunas_da_fonte, *DA_FONTE_QUE_SAI]
    padrao = {
        **{c: "TEXTO" for c in relatorio.colunas_da_fonte},
        relatorio.cnpj: _formatado(EMPRESA),
        relatorio.ano: "2024",
        **{c: "10" for c in [*relatorio.numeros, *relatorio.percentuais]},
        **{c: _formatado(OUTRA) for c in relatorio.outras_pontas},
        **DA_FONTE_QUE_SAI,
    }
    corpo = [";".join({**padrao, **linha}[c] for c in cabecalho) for linha in linhas]
    return "\n".join([";".join(cabecalho), *corpo]).encode("utf-8")


def _sem_nada_de_pessoa_nem_do_que_sai(tabela: pd.DataFrame) -> None:
    assert not [c for c in tabela.columns if any(p in c.lower() for p in PROIBIDAS)]
    texto = set(tabela.astype(str).to_numpy().ravel())
    assert not {NOME_INVENTADO, LUGAR_INVENTADO, CPF_DE_TESTE} & texto


def test_emissoes_leem_o_numero_com_virgula_de_milhar_e_a_tabela_tem_so_as_colunas_dela():
    tabela, contagem = rapp.ler(
        rapp.EMISSOES,
        _arquivo(rapp.EMISSOES, {"Quantidade": "1,234.5", "Poluente emitido": "NOx"}),
    )
    assert list(tabela.columns) == list(rapp.EMISSOES.colunas)
    assert tabela["quantidade"].tolist() == [1234.5]
    assert tabela["poluente"].tolist() == ["NOx"]
    assert tabela["ano"].tolist() == [2024]
    assert tabela["cnpj"].tolist() == [_formatado(EMPRESA)]
    assert tabela["cnpj_basico"].tolist() == [EMPRESA[:8]]
    assert contagem["linhas"] == 1
    _sem_nada_de_pessoa_nem_do_que_sai(tabela)


def test_efluentes_leem_o_numero_com_ponto_de_milhar_e_a_celula_ilegivel_vira_vazio_contado():
    tabela, contagem = rapp.ler(
        rapp.EFLUENTES,
        _arquivo(
            rapp.EFLUENTES,
            {"Quantidade": "1.234,5", "Eficiência do tratamento": "85,5%"},
            {"Quantidade": "#####", "Eficiência do tratamento": "90"},
        ),
    )
    assert tabela["quantidade"].tolist()[0] == 1234.5
    assert pd.isna(tabela["quantidade"].iloc[1])
    assert tabela["eficiencia_do_tratamento"].tolist() == [85.5, 90.0]
    assert contagem["numero_ilegivel"] == 1


def test_quem_declara_com_cpf_ou_cnpj_de_digito_errado_sai_e_e_contado():
    tabela, contagem = rapp.ler(
        rapp.EMISSOES,
        _arquivo(
            rapp.EMISSOES,
            {},
            {"CNPJ": CPF_DE_TESTE},
            {"CNPJ": DV_ERRADO},
        ),
    )
    assert tabela["cnpj_basico"].tolist() == [EMPRESA[:8]]
    assert contagem["pessoa_fisica"] == 1
    assert contagem["cnpj_invalido"] == 1
    _sem_nada_de_pessoa_nem_do_que_sai(tabela)


def test_linha_quebrada_sai_e_e_contada_e_o_ponto_e_virgula_entre_aspas_nao_quebra():
    inteira = _arquivo(rapp.ENERGIA, {"Observação": '"um; dois"'})
    quebrada = inteira + b"\nPEDACO;DE;OBSERVACAO\n"
    tabela, contagem = rapp.ler(rapp.ENERGIA, quebrada)
    assert len(tabela) == 1
    assert contagem["linha_quebrada"] == 1


def test_coluna_que_o_ibama_tirou_e_erro_nunca_tabela_vazia():
    sem_o_ano = b"CNPJ;Quantidade\n" + EMPRESA.encode() + b";10"
    with pytest.raises(KeyError, match="o IBAMA deixou de trazer"):
        rapp.ler(rapp.EMISSOES, sem_o_ano)


def test_a_outra_ponta_com_cpf_fica_vazia_e_contada_e_a_com_cnpj_ganha_a_raiz():
    tabela, contagem = rapp.ler(
        rapp.RESIDUOS_DESTINADOS,
        _arquivo(
            rapp.RESIDUOS_DESTINADOS,
            {"Quant. destinada": "2.000,25"},
            {"CNPJ do gerador do resíduo": CPF_DE_TESTE},
        ),
    )
    assert tabela["cnpj_gerador"].iloc[0] == _formatado(OUTRA)
    assert tabela["cnpj_basico_gerador"].iloc[0] == OUTRA[:8]
    assert tabela["quantidade"].iloc[0] == 2000.25
    assert pd.isna(tabela["cnpj_gerador"].iloc[1])
    assert pd.isna(tabela["cnpj_basico_gerador"].iloc[1])
    assert contagem["outra_ponta_pessoa_fisica"] == 1
    _sem_nada_de_pessoa_nem_do_que_sai(tabela)


def _alfanumerico(primeiros_12: str) -> str:
    return primeiros_12 + cnpjs.digitos_verificadores(primeiros_12)


ALFANUMERICO = _alfanumerico("12ABC34501DE")


def test_cnpj_alfanumerico_entra_nas_duas_pontas_com_as_letras():
    tabela, contagem = rapp.ler(
        rapp.RESIDUOS_DESTINADOS,
        _arquivo(
            rapp.RESIDUOS_DESTINADOS,
            {
                "CNPJ do destinador": _formatado(ALFANUMERICO),
                "CNPJ do gerador do resíduo": _formatado(ALFANUMERICO),
            },
        ),
    )
    assert contagem["cnpj_invalido"] == 0
    assert tabela["cnpj_basico"].tolist() == [ALFANUMERICO[:8]]
    assert tabela["cnpj_basico_gerador"].tolist() == [ALFANUMERICO[:8]]
    assert tabela["cnpj_gerador"].tolist() == [_formatado(ALFANUMERICO)]


def test_a_outra_ponta_com_digito_errado_fica_vazia_e_e_contada_a_parte_do_cpf():
    tabela, contagem = rapp.ler(
        rapp.RESIDUOS_TRANSPORTADOS,
        _arquivo(
            rapp.RESIDUOS_TRANSPORTADOS,
            {"CNPJ da origem": DV_ERRADO},
            {"CNPJ da origem": ""},
        ),
    )
    assert tabela["cnpj_origem"].isna().all()
    assert contagem["outra_ponta_invalida"] == 1  # o vazio não conta
    assert contagem["outra_ponta_pessoa_fisica"] == 0


def test_duas_declaracoes_iguais_continuam_duas_com_chaves_diferentes_e_estaveis():
    arquivo = _arquivo(rapp.EMISSOES, {}, {})
    tabela, _ = rapp.ler(rapp.EMISSOES, arquivo)
    de_novo, _ = rapp.ler(rapp.EMISSOES, arquivo)
    assert len(tabela) == 2
    assert tabela["id_na_fonte"].nunique() == 2
    assert tabela["id_na_fonte"].tolist() == de_novo["id_na_fonte"].tolist()


def _coletar(banco, relatorio: rapp.Relatorio, conteudo: bytes, dia: date) -> None:
    com_registro(relatorio.fonte, lambda _url: conteudo)(relatorio.url)
    with banco.begin() as conexao:
        conexao.execute(
            sa.update(coletas.coletas)
            .where(
                coletas.coletas.c.url == relatorio.url,
                coletas.coletas.c.sha256 == hashlib.sha256(conteudo).hexdigest(),
            )
            .values(baixado_em=datetime(dia.year, dia.month, dia.day, 3, tzinfo=UTC))
        )


def _coletar_os_seis(banco, dia: date) -> None:
    """Em cada relatório, uma linha da empresa e uma do MEI; nos de resíduos, uma da empresa com o MEI na outra
    ponta."""
    for relatorio in rapp.RELATORIOS:
        linhas = [{}, {relatorio.cnpj: _formatado(MEI)}]
        linhas += [{c: _formatado(MEI)} for c in relatorio.outras_pontas]
        _coletar(banco, relatorio, _arquivo(relatorio, *linhas), dia)


def test_montar_grava_as_seis_tabelas_marca_o_mei_tambem_na_outra_ponta_e_vale_desde_o_dia_do_arquivo(
    banco, tmp_path
):
    _coletar_os_seis(banco, DIA)
    with banco.connect() as conexao:
        resumo = rapp.montar(conexao, tmp_path, AGORA, pessoas={MEI[:8]})
    assert set(resumo) == {r.nome for r in rapp.RELATORIOS}
    for cadastro, relatorio in zip(rapp.CADASTROS, rapp.RELATORIOS, strict=True):
        tabela = pd.read_parquet(
            tmp_path / cadastro.tabela / f"{cadastro.nome}.parquet"
        )
        assert list(tabela.columns) == [
            *cadastro.colunas,
            *montagem.CARIMBOS_DA_LINHA,
            *LINHAGEM,
        ]
        pontas_do_mei = [
            (tabela[f"cnpj_basico_{s}"] == MEI[:8]).fillna(False)
            for s in relatorio.outras_pontas.values()
        ]
        do_mei = (tabela["cnpj_basico"] == MEI[:8]) | pd.concat(
            [pd.Series(False, index=tabela.index), *pontas_do_mei], axis=1
        ).any(axis=1)
        assert tabela["trata_como_pessoa"].tolist() == do_mei.tolist(), cadastro.tabela
        assert do_mei.sum() == 1 + len(relatorio.outras_pontas)
        # declarado para 2024, mas só público a partir do dia em que o arquivo foi baixado
        assert set(tabela["ano"]) == {2024}
        assert set(tabela["disponivel_em"]) == {DIA}
        _sem_nada_de_pessoa_nem_do_que_sai(tabela)


def test_segundo_montar_sem_arquivo_novo_e_ja_montado(banco, tmp_path):
    _coletar_os_seis(banco, DIA)
    with banco.connect() as conexao:
        rapp.montar(conexao, tmp_path, AGORA, pessoas=set())
        assert rapp.montar(conexao, tmp_path, AGORA, pessoas=set()) == {
            r.nome: montagem.JA_MONTADO for r in rapp.RELATORIOS
        }
