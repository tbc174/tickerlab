"""Cadastros do Banco Central em retrato (linha 904, lote 3): entidades supervisionadas, cooperativas,
correspondentes, filiais de consórcio e regimes especiais. Só pessoa jurídica (o CPF sai), nome, endereço,
contato e o liquidante fora, MEI marcado como pessoa, uma posição por dia de coleta e sem olhar o futuro.
Arquivos de mentira, no formato conferido em 13/11/2026; nenhum documento real."""

import hashlib
import json
from datetime import UTC, date, datetime

import pandas as pd
import pytest
import sqlalchemy as sa

from base import bcb_cadastros as bcb
from base import cadastros_em_retrato as montagem
from base import cnpj as cnpjs
from base.parquet import LINHAGEM
from src.banco import coletas
from src.banco.coletas import com_registro
from tests.ajudantes_de_cpf import CPF_DE_TESTE

AGORA = datetime(2026, 12, 1, 22, tzinfo=UTC)
PRIMEIRO_DIA = date(2026, 11, 14)
SEGUNDO_DIA = date(2026, 12, 1)
OLINDA = "https://olinda.bcb.gov.br/olinda/servico/"
URL_DAS_SUPERVISIONADAS = (
    OLINDA + "BcBase/EntidadesSupervisionadas(dataBase=@d)?@d='{}'"
)
URL_DAS_COOPERATIVAS = OLINDA + "BcBase/Cooperativas(dataBase=@d)?@d='{}'"
URL_DOS_CORRESPONDENTES = OLINDA + "Informes_Correspondentes/Correspondentes"
URL_DAS_FILIAIS = OLINDA + "Informes_FiliaisAdministradorasConsorcios/Filiais"
URL_DOS_REGIMES = OLINDA + "regimes_especiais/Regimes"
PROIBIDAS = (
    "nome", "razao", "cpf", "endereco", "cep", "mail", "telefone", "ddd", "respons", "bairro", "numero",
)  # fmt: skip
NOME_INVENTADO = "BANCO INVENTADO DE TESTE S.A."


def _cnpj(raiz: str, filial: str = "0001") -> str:
    for dv in range(100):
        if cnpjs.dv_confere(bruto := f"{raiz}{filial}{dv:02d}"):
            return bruto
    raise AssertionError(raiz)


EMPRESA = _cnpj("11222333")
MEI = _cnpj("44555666")
DV_ERRADO = EMPRESA[:-1] + str((int(EMPRESA[-1]) + 1) % 10)


def _olinda(*registros: dict[str, str | None]) -> bytes:
    return json.dumps({"value": list(registros)}).encode("utf-8")


def _entidade(cnpj: str | None, codigo: str, **mudancas: str | None) -> dict:
    return {
        "database": "2026-10-31", "codigoIdentificadorBacen": codigo, "codigoSisbacen": "32681",
        "nomeDaUnidadeFederativa": "Mato Grosso", "codigoDoMunicipioNoIBGE": "5107909",
        "nomeDoMunicipio": "Sinop", "nomeEntidadeInteresse": NOME_INVENTADO,
        "nomeEntidadeInteresseNaoFormatado": NOME_INVENTADO, "codigoCNPJ14": cnpj,
        "codigoCNPJ8": cnpj[:8] if cnpj else None, "codigoTipoSituacaoPessoaJuridica": "3",
        "descricaoTipoSituacaoPessoaJuridica": "Autorizada em Atividade",
        "codigoTipoEntidadeSupervisionada": "9", "descricaoTipoEntidadeSupervisionada": "Cooperativa de Crédito",
        "codigoNaturezaJuridica": "4", "descricaoNaturezaJuridica": "Sociedade Cooperativa",
        "codigoClasseCooperativa": "2", "descricaoClasseCooperativa": "Singular",
        "codigoTipoCooperativa": "17", "descricaoTipoCooperativa": "Atividade Profissional",
        "codigoCategoriaCooperativa": "3", "descricaoCategoriaCooperativa": "Capital e Empréstimo",
        "nomeReduzido": NOME_INVENTADO, "siglaDaPessoaJuridica": "INVENT", "nomeFantasia": None,
        "indicadorEsferaPublica": "2", **mudancas,
    }  # fmt: skip


def _correspondente(
    contratante: str, correspondente: str, ordem: str = "I00001"
) -> dict:
    return {
        "CnpjContratante": contratante, "NomeContratante": NOME_INVENTADO, "CnpjCorrespondente": correspondente,
        "NomeCorrespondente": NOME_INVENTADO, "Tipo": "Sede", "Ordem": ordem, "MunicipioIBGE": "2611606",
        "Municipio": "RECIFE", "UF": "PE", "ServicosCorrespondentes": "Inc. V", "Posicao": "12/11/2026",
    }  # fmt: skip


def _filial(raiz: str, endereco: str = "AV INVENTADA", **mudancas: str) -> dict:
    return {
        "CNPJ": raiz, "NomeInstituicao": NOME_INVENTADO, "Endereco": endereco, "Numero": "10",
        "Complemento": "SALA 2", "Bairro": "CENTRO", "CEP": "69060-000", "MunicipioIbge": "1302603",
        "Municipio": "MANAUS", "UF": "AM", "DataInicio": "2026-07-02", "DDD": "61", "Telefone": "33147190",
        "Posicao": "12/11/2026", **mudancas,
    }  # fmt: skip


def _regime(cnpj: str, **mudancas: str) -> dict:
    return {
        "CnpjInstituicao": cnpj, "CnpjRaiz": cnpj[:8], "NomeInstituicao": NOME_INVENTADO, "Inicio": "27/03/2026",
        "Tipo": "LIQUIDAÇÃO EXTRAJUDICIAL", "Responsavel": "FULANO INVENTADO DE TAL", "Endereco": "Rua Inventada, 1",
        "Municipio": "São Paulo", "UF": "SP", "CEP": "01311-000", "Emails": "liquidante@exemplo.invalid",
        "Telefones": "(11)40001829", **mudancas,
    }  # fmt: skip


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


def _montar(banco, pasta, pessoas=frozenset()) -> dict:
    with banco.connect() as conexao:
        return bcb.montar(conexao, pasta, AGORA, pessoas=set(pessoas))


def _ler(pasta, tabela: str, nome: str) -> pd.DataFrame:
    return pd.read_parquet(pasta / tabela / f"{nome}.parquet")


def test_supervisionadas_so_cnpj_e_sem_nome_nem_municipio_por_extenso():
    tabela, contagem = bcb.ler_supervisionadas(
        _olinda(
            _entidade(EMPRESA, "A1"),
            _entidade(MEI, "A2", nomeFantasia=None, siglaDaPessoaJuridica=""),
            _entidade(DV_ERRADO, "A3"),
            _entidade(CPF_DE_TESTE, "A4"),
            _entidade(None, "A5"),
        )
    )
    assert contagem == {
        "linhas": 5, "pessoa_fisica": 1, "cnpj_invalido": 1, "sem_cnpj": 1, "id_repetido": 0,
    }  # fmt: skip
    assert list(tabela["id_na_fonte"]) == ["A1", "A2"]
    assert tabela["sigla"].isna().tolist() == [False, True]
    assert tabela.loc[0, "situacao"] == "Autorizada em Atividade"
    assert tabela.loc[0, "municipio_ibge"] == "5107909"
    assert not tabela.astype(str).isin([NOME_INVENTADO, "Sinop"]).any().any()


def test_cooperativas_trazem_classe_tipo_e_categoria():
    tabela, contagem = bcb.ler_cooperativas(_olinda(_entidade(EMPRESA, "C1")))
    assert contagem["sem_cnpj"] == 0
    linha = tabela.iloc[0]
    assert (linha["classe"], linha["tipo_da_cooperativa"], linha["categoria"]) == (
        "Singular", "Atividade Profissional", "Capital e Empréstimo",
    )  # fmt: skip


def test_lista_vazia_ou_coluna_que_sumiu_e_erro_nunca_arquivo_vazio():
    with pytest.raises(ValueError, match="não tem registros"):
        bcb.ler_supervisionadas(_olinda())
    sem_a_coluna = _entidade(EMPRESA, "A1")
    del sem_a_coluna["siglaDaPessoaJuridica"]
    with pytest.raises(KeyError, match="siglaDaPessoaJuridica"):
        bcb.ler_supervisionadas(_olinda(sem_a_coluna))


def test_correspondentes_so_a_raiz_sem_nome_e_conta_a_repetida_e_a_raiz_ruim():
    tabela, contagem = bcb.ler_correspondentes(
        _olinda(
            _correspondente("59285411", "48630167"),
            _correspondente("59285411", "48630167"),  # repetida por inteiro
            _correspondente("59285411", "48630167", ordem="I00002"),
            _correspondente("59285411", CPF_DE_TESTE),  # 11 dígitos: não é raiz
            _correspondente("59285411", ""),
        )
    )
    assert contagem == {"linhas": 5, "raiz_invalida": 2, "id_repetido": 1}
    assert list(tabela["id_na_fonte"]) == [
        "59285411|48630167|I00001", "59285411|48630167|I00002",
    ]  # fmt: skip
    assert set(tabela["cnpj_basico_contratante"]) == {"59285411"}
    assert not tabela.astype(str).isin([NOME_INVENTADO, "RECIFE"]).any().any()


def test_filiais_distinguem_o_mesmo_municipio_pelo_selo_sem_guardar_o_endereco():
    tabela, contagem = bcb.ler_filiais(
        _olinda(
            _filial("02010478"),
            _filial("02010478", endereco="OUTRA AV INVENTADA"),
            _filial("02010478", DataInicio=""),
            _filial("123"),
        )
    )
    assert contagem["raiz_invalida"] == 1
    assert len(tabela) == 2  # a 3ª é o mesmo endereço da 1ª: repetida
    assert contagem["id_repetido"] == 1
    assert tabela["id_na_fonte"].is_unique
    assert "AV INVENTADA" not in " ".join(tabela["id_na_fonte"])
    assert tabela.loc[0, "inicio_em"] == pd.Timestamp(2026, 7, 2)


def test_regimes_sem_o_liquidante_o_endereco_e_o_contato():
    tabela, contagem = bcb.ler_regimes(
        _olinda(_regime(EMPRESA), _regime(CPF_DE_TESTE), _regime(DV_ERRADO))
    )
    assert contagem["pessoa_fisica"] == 1
    assert contagem["cnpj_invalido"] == 1
    assert len(tabela) == 1
    assert tabela.loc[0, "inicio_em"] == pd.Timestamp(2026, 3, 27)
    assert tabela.loc[0, "tipo"] == "LIQUIDAÇÃO EXTRAJUDICIAL"
    assert not [c for c in tabela.columns if any(p in c.lower() for p in PROIBIDAS)]
    assert not tabela.astype(str).isin(["FULANO INVENTADO DE TAL"]).any().any()


def _coletar_tudo(banco, dia: date, entidades: list[dict]) -> None:
    posicao = dia.strftime("%m-%d-%Y")
    correspondentes = _olinda(
        _correspondente("59285411", EMPRESA[:8]),
        _correspondente("59285411", MEI[:8], ordem="I00002"),
    )
    cadastros = (
        (bcb.FONTE_DAS_SUPERVISIONADAS, URL_DAS_SUPERVISIONADAS.format(posicao), _olinda(*entidades)),
        (bcb.FONTE_DAS_COOPERATIVAS, URL_DAS_COOPERATIVAS.format(posicao), _olinda(*entidades)),
        (bcb.FONTE_DOS_CORRESPONDENTES, URL_DOS_CORRESPONDENTES, correspondentes),
        (bcb.FONTE_DAS_FILIAIS, URL_DAS_FILIAIS, _olinda(_filial(EMPRESA[:8]), _filial(MEI[:8]))),
        (bcb.FONTE_DOS_REGIMES, URL_DOS_REGIMES, _olinda(_regime(EMPRESA), _regime(MEI))),
    )  # fmt: skip
    for fonte, url, conteudo in cadastros:
        _coletar(banco, fonte, url, conteudo, dia)


def test_montar_grava_as_cinco_tabelas_e_marca_o_mei(banco, tmp_path):
    _coletar_tudo(banco, PRIMEIRO_DIA, [_entidade(EMPRESA, "A1"), _entidade(MEI, "A2")])
    resumo = _montar(banco, tmp_path, pessoas={MEI[:8]})
    assert set(resumo) == {
        "supervisionadas", "cooperativas", "correspondentes", "filiais", "regimes",
    }  # fmt: skip
    for cadastro in bcb.CADASTROS:
        tabela = _ler(tmp_path, cadastro.tabela, cadastro.nome)
        assert list(tabela.columns) == [
            *cadastro.colunas, *montagem.CARIMBOS_DA_LINHA, *LINHAGEM,
        ]  # fmt: skip
        assert not [c for c in tabela.columns if any(p in c.lower() for p in PROIBIDAS)]
        assert dict(zip(tabela["cnpj_basico"], tabela["trata_como_pessoa"], strict=True)) == {
            EMPRESA[:8]: False, MEI[:8]: True,
        }  # fmt: skip
        assert set(tabela["disponivel_em"]) == {
            PRIMEIRO_DIA
        }  # o arquivo não diz quando foi publicado


def test_o_contratante_que_e_pessoa_marca_a_linha_do_correspondente(banco, tmp_path):
    _coletar_tudo(banco, PRIMEIRO_DIA, [_entidade(EMPRESA, "A1")])
    _montar(banco, tmp_path, pessoas={"59285411"})
    tabela = _ler(tmp_path, "bcb_correspondentes", "correspondentes")
    assert tabela["trata_como_pessoa"].all()


def test_cada_dia_de_coleta_e_uma_posicao_e_quem_sai_da_lista_ganha_consta_falso(
    banco, tmp_path
):
    _coletar_tudo(banco, PRIMEIRO_DIA, [_entidade(EMPRESA, "A1"), _entidade(MEI, "A2")])
    _montar(banco, tmp_path / "so_o_primeiro")
    paralisada = _entidade(
        EMPRESA, "A1", descricaoTipoSituacaoPessoaJuridica="Paralisada"
    )
    _coletar_tudo(banco, SEGUNDO_DIA, [paralisada])
    _montar(banco, tmp_path / "os_dois")
    depois = _ler(tmp_path / "os_dois", "bcb_supervisionadas", "supervisionadas")
    antes = _ler(tmp_path / "so_o_primeiro", "bcb_supervisionadas", "supervisionadas")
    ja_valiam = depois[depois["disponivel_em"] <= PRIMEIRO_DIA]
    pd.testing.assert_frame_equal(
        ja_valiam.drop(columns=list(LINHAGEM)).reset_index(drop=True),
        antes.drop(columns=list(LINHAGEM)),
    )
    mudancas = depois[depois["disponivel_em"] == SEGUNDO_DIA].set_index("id_na_fonte")
    assert mudancas.loc["A1", "situacao"] == "Paralisada"
    assert bool(mudancas.loc["A2", "consta"]) is False
    assert (depois["disponivel_em"] <= depois["visto_em"]).all()


def test_segundo_montar_sem_retrato_novo_e_ja_montado(banco, tmp_path):
    _coletar_tudo(banco, PRIMEIRO_DIA, [_entidade(EMPRESA, "A1")])
    _montar(banco, tmp_path)
    assert _montar(banco, tmp_path) == dict.fromkeys(
        ("supervisionadas", "cooperativas", "correspondentes", "filiais", "regimes"),
        montagem.JA_MONTADO,
    )
