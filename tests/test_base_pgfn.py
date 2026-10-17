"""Dívida ativa da União (PGFN) na base: só pessoa jurídica, sem nome e sem CPF (ADR 0075).

Layout conferido no servidor de casa em 16/10/2026 (retrato de 2026-06, coletado em 14/10): três ZIPs
(SIDA, Previdência e FGTS), um CSV por região da PGFN dentro de cada um; `;`, latin-1, com cabeçalho;
o CPF da pessoa física já vem mascarado (`XXX123.456XX`), mas o nome dela vem inteiro. Arquivos de
mentira.
"""

import io
import json
import zipfile
from datetime import UTC, date, datetime

import pandas as pd
import sqlalchemy as sa

from base import cnpj as cnpjs
from base import pgfn
from base.ancoragem import parquets_sem_manifesto
from src.banco import coletas
from src.banco.coletas import com_registro

AGORA = datetime(2026, 10, 16, 22, tzinfo=UTC)
GERADO = (2026, 7, 23, 14, 31, 0)
CABECALHO_SIDA = (
    "CPF_CNPJ;TIPO_PESSOA;TIPO_DEVEDOR;NOME_DEVEDOR;UF_DEVEDOR;UNIDADE_RESPONSAVEL;"
    "NUMERO_INSCRICAO;TIPO_SITUACAO_INSCRICAO;SITUACAO_INSCRICAO;RECEITA_PRINCIPAL;"
    "DATA_INSCRICAO;INDICADOR_AJUIZADO;VALOR_CONSOLIDADO"
)
CABECALHO_FGTS = (
    "CPF_CNPJ;TIPO_PESSOA;TIPO_DEVEDOR;NOME_DEVEDOR;UF_DEVEDOR;UNIDADE_RESPONSAVEL;"
    "ENTIDADE_RESPONSAVEL;UNIDADE_INSCRICAO;NUMERO_INSCRICAO;TIPO_SITUACAO_INSCRICAO;"
    "SITUACAO_INSCRICAO;RECEITA_PRINCIPAL;DATA_INSCRICAO;INDICADOR_AJUIZADO;VALOR_CONSOLIDADO"
)
URL_SIDA = "https://dadosabertos.pgfn.gov.br/2026_trimestre_02/Dados_abertos_Nao_Previdenciario.zip"
URL_FGTS = "https://dadosabertos.pgfn.gov.br/2026_trimestre_02/Dados_abertos_FGTS.zip"


def _numeros(*raizes: str):
    """As raízes como o conjunto de números que a montagem usa (`base/cnpj.py`)."""
    return cnpjs.ordenados(cnpjs.raizes_em_numeros(pd.Series(list(raizes), dtype=str)))


def _cnpj(raiz: str, filial: str = "0001") -> str:
    """Um CNPJ com o dígito certo, formatado como a PGFN escreve."""
    for dv in range(100):
        bruto = f"{raiz}{filial}{dv:02d}"
        if cnpjs.dv_confere(bruto):
            return cnpjs.formatar(bruto)
    raise AssertionError(raiz)


EMPRESA = _cnpj("11222333")
FILIAL = _cnpj("11222333", "0002")
OUTRA = _cnpj("33000167")
MEI = _cnpj("44555666")
SEM_RECEITA = _cnpj("77888999")
COM_LETRAS = _cnpj("AB222333")  # CNPJ alfanumérico (desde 07/2026)
INVALIDO = EMPRESA[:-1] + str((int(EMPRESA[-1]) + 1) % 10)
NOME_DA_PESSOA = "MARIA DA SILVA DE MENTIRA"
CPF_MASCARADO = "XXX123.456XX"


def _sida(
    documento: str,
    pessoa: str = "Pessoa jurídica",
    devedor: str = "PRINCIPAL",
    nome: str = "EMPRESA DE MENTIRA LTDA",
    situacao: str = "ATIVA AJUIZADA",
    data: str = "15/03/2019",
    ajuizado: str = "SIM",
    valor: str = "1000.50",
) -> str:
    return (
        f"{documento};{pessoa};{devedor};{nome};SP;PGFN SP;FGSP001;Em cobrança;{situacao};"
        f"IRPJ;{data};{ajuizado};{valor}"
    )


def _fgts(documento: str, valor: str = "200.00") -> str:
    return (
        f"{documento};Pessoa jurídica;Principal;EMPRESA LTDA;BA;ACRE;PGFN ACRE;"
        f"FGBA2019;FGBA201900928;Em cobrança;INSCRITA;Contribuições FGTS;30/07/2019;NAO;{valor}"
    )


def _zip(membros: dict[str, list[str]]) -> bytes:
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as arquivo:
        for nome, linhas in membros.items():
            info = zipfile.ZipInfo(nome, date_time=GERADO)
            arquivo.writestr(info, "\n".join(linhas).encode("latin-1"))
    return saida.getvalue()


def _ler(pasta, arquivo: str) -> pd.DataFrame:
    """Os 11 pedaços de um CSV (pelo 1º caractere do CNPJ) numa tabela só."""
    pedacos = sorted(pasta.glob(f"{arquivo}-*.parquet"))
    assert len(pedacos) == len(pgfn.PREFIXOS), arquivo
    return pd.concat([pd.read_parquet(p) for p in pedacos], ignore_index=True)


def _sida_zip(*linhas: str, regiao: str = "1") -> io.BytesIO:
    return io.BytesIO(
        _zip({f"arquivo_lai_SIDA_{regiao}_202606.csv": [CABECALHO_SIDA, *linhas]})
    )


def _lido(*linhas: str, pessoas: frozenset[str] = frozenset()) -> pd.DataFrame:
    arquivo = _sida_zip(*linhas)
    (membro,) = pgfn.membros(arquivo)
    tabela, _ = pgfn.ler_membro(arquivo, membro, set(pessoas))
    return tabela


def test_membro_diz_sistema_regiao_retrato_e_quando_foi_gerado():
    arquivo = io.BytesIO(
        _zip(
            {
                "arquivo_lai_SIDA_3_202606.csv": [CABECALHO_SIDA],
                "arquivo_lai_FGTS_NA_202606.csv": [CABECALHO_FGTS],
                "leiame.txt": ["nada"],
            }
        )
    )
    achados = {(m.tipo_divida, m.regiao): m for m in pgfn.membros(arquivo)}
    assert set(achados) == {("nao_previdenciaria", "3"), ("fgts", "NA")}
    sida = achados[("nao_previdenciaria", "3")]
    assert sida.data_do_retrato == date(2026, 6, 30)  # o último dia do mês do retrato
    assert sida.gerado_em == date(2026, 7, 23)


def test_pessoa_fisica_nunca_entra_nem_o_nome_nem_o_cpf():
    tabela = _lido(
        _sida(EMPRESA),
        _sida(CPF_MASCARADO, pessoa="Pessoa física", devedor="CORRESPONSAVEL", nome=NOME_DA_PESSOA),
    )  # fmt: skip
    assert tabela["cnpj"].tolist() == [EMPRESA]
    texto = tabela.astype(str).to_string()
    assert "MARIA" not in texto and "XXX" not in texto and "MENTIRA" not in texto
    assert "nome" not in " ".join(tabela.columns).lower()


def test_linha_marcada_como_pessoa_fisica_sai_mesmo_com_documento_de_cnpj():
    """Duas travas: o tipo de pessoa e o formato do CNPJ (o CPF mascarado já cai na segunda)."""
    tabela = _lido(
        _sida(EMPRESA), _sida(OUTRA, pessoa="Pessoa física", nome=NOME_DA_PESSOA)
    )
    assert tabela["cnpj"].tolist() == [EMPRESA]


def test_cnpj_com_digito_errado_fica_de_fora_e_e_contado():
    arquivo = _sida_zip(
        _sida(EMPRESA),
        _sida(INVALIDO),
        _sida(CPF_MASCARADO, pessoa="Pessoa física", nome=NOME_DA_PESSOA),
    )
    (membro,) = pgfn.membros(arquivo)
    tabela, contagem = pgfn.ler_membro(arquivo, membro, set())
    assert tabela["cnpj"].tolist() == [EMPRESA]
    assert contagem == {
        "linhas": 3,
        "pessoa_fisica": 1,
        "cnpj_invalido": 1,
        "na_tabela": 1,
    }


def test_inscricoes_iguais_somam_valor_e_contam():
    tabela = _lido(
        _sida(EMPRESA, data="15/03/2019", valor="1000.50"),
        _sida(EMPRESA, data="02/01/2024", valor=".50"),
        _sida(EMPRESA, situacao="ATIVA EM COBRANCA", ajuizado="NAO", valor="10.00"),
        _sida(FILIAL, valor="7.00"),
    )
    linha = tabela[
        (tabela["cnpj"] == EMPRESA) & (tabela["situacao_inscricao"] == "ATIVA AJUIZADA")
    ].iloc[0]
    assert linha["inscricoes"] == 2
    assert linha["valor_consolidado"] == 1001.0
    assert linha["primeira_inscricao"] == date(2019, 3, 15)
    assert linha["ultima_inscricao"] == date(2024, 1, 2)
    assert bool(linha["ajuizado"]) is True
    assert len(tabela) == 3  # a filial e a situação diferente são linhas próprias
    assert set(tabela["cnpj_basico"]) == {"11222333"}


def test_devedor_e_tipo_de_divida_padronizados():
    tabela = _lido(
        _sida(EMPRESA, devedor="CORRESPONSAVEL"), _sida(OUTRA, devedor="Principal")
    )
    assert set(tabela["tipo_devedor"]) == {"corresponsavel", "principal"}
    assert set(tabela["tipo_divida"]) == {"nao_previdenciaria"}
    assert set(tabela["regiao"]) == {"1"}
    assert set(tabela["data_do_retrato"]) == {date(2026, 6, 30)}


def test_data_de_mentira_da_pgfn_vira_vazia():
    """A PGFN escreve 01/01/1000 quando não tem a data (crédito de sucumbência, por exemplo)."""
    tabela = _lido(_sida(EMPRESA, data="01/01/1000", valor=".00"))
    assert pd.isna(tabela["primeira_inscricao"].iloc[0])
    assert tabela["valor_consolidado"].iloc[0] == 0.0


def test_empresario_individual_e_mei_marcados_como_pessoa():
    tabela = _lido(_sida(EMPRESA), _sida(MEI), pessoas=frozenset({"44555666"}))
    marca = dict(zip(tabela["cnpj"], tabela["trata_como_pessoa"], strict=True))
    assert marca == {EMPRESA: False, MEI: True}


def test_raizes_de_pessoa_pela_natureza_pelo_mei_e_pela_falta_da_receita():
    naturezas = pd.DataFrame(
        {
            "cnpj_basico": ["11222333", "44555666", "55666777", "66777888"],
            "natureza_juridica": ["2062", "2062", "2135", "4090"],
        }
    )
    meis = pd.DataFrame({"cnpj_basico": ["44555666", "11222333"], "mei": [True, False]})
    raizes = _numeros("11222333", "44555666", "55666777", "66777888", "77888999")
    assert (
        pgfn.raizes_de_pessoa(raizes, naturezas, meis).tolist()
        == _numeros(
            "44555666",  # MEI
            "55666777",  # empresário individual (213-5)
            "66777888",  # grupo 4 da tabela de naturezas
            "77888999",  # a Receita não tem: o conservador (ADR 0075)
        ).tolist()
    )


def test_raizes_dos_devedores_so_de_pessoa_juridica_valida():
    arquivo = _sida_zip(
        _sida(EMPRESA),
        _sida(FILIAL),
        _sida(INVALIDO),
        _sida(OUTRA),
        _sida(CPF_MASCARADO, pessoa="Pessoa física", nome=NOME_DA_PESSOA),
    )
    assert (
        pgfn.raizes_dos_devedores(arquivo).tolist()
        == _numeros("11222333", "33000167").tolist()
    )


def test_leitura_em_pedacos_da_o_mesmo_resultado(monkeypatch):
    linhas = [_sida(EMPRESA, valor="1.00")] * 7 + [_sida(OUTRA, valor="2.00")] * 5
    inteiro = _lido(*linhas)
    monkeypatch.setattr(pgfn, "TAMANHO_DA_PARTE", 2)
    monkeypatch.setattr(pgfn, "JUNTAR_A_CADA", 3)
    em_pedacos = _lido(*linhas)
    pd.testing.assert_frame_equal(inteiro, em_pedacos)
    assert dict(zip(inteiro["cnpj"], inteiro["inscricoes"], strict=True)) == {
        EMPRESA: 7,
        OUTRA: 5,
    }


def test_fgts_le_pelo_nome_das_colunas():
    arquivo = io.BytesIO(
        _zip({"arquivo_lai_FGTS_NA_202606.csv": [CABECALHO_FGTS, _fgts(OUTRA)]})
    )
    (membro,) = pgfn.membros(arquivo)
    tabela, _ = pgfn.ler_membro(arquivo, membro, set())
    linha = tabela.iloc[0]
    assert (linha["tipo_divida"], linha["regiao"], linha["situacao_inscricao"]) == (
        "fgts",
        "NA",
        "INSCRITA",
    )
    assert bool(linha["ajuizado"]) is False and linha["valor_consolidado"] == 200.0


def test_montar_grava_um_parquet_por_arquivo_com_manifesto(
    banco, tmp_path, monkeypatch
):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    sida = _zip(
        {
            "arquivo_lai_SIDA_1_202606.csv": [CABECALHO_SIDA, _sida(EMPRESA), _sida(MEI), _sida(COM_LETRAS)],
            "arquivo_lai_SIDA_2_202606.csv": [CABECALHO_SIDA, _sida(SEM_RECEITA)],
        }
    )  # fmt: skip
    fgts = _zip({"arquivo_lai_FGTS_NA_202606.csv": [CABECALHO_FGTS, _fgts(OUTRA)]})
    com_registro("pgfn-divida", lambda _url: sida)(URL_SIDA)
    com_registro("pgfn-divida", lambda _url: fgts)(URL_FGTS)
    with banco.connect() as conexao:
        resumo = pgfn.montar(conexao, tmp_path / "base", AGORA, pessoas={"44555666"})
    pasta = tmp_path / "base" / "pgfn_divida" / "2026-06"
    assert sorted(p.name for p in pasta.glob("*.parquet")) == sorted(
        f"{arquivo}-{prefixo}.parquet"
        for arquivo in ("fgts-NA", "sida-1", "sida-2")
        for prefixo in pgfn.PREFIXOS
    )  # sempre os 11 pedaços, vazios também: nunca sobra pedaço de um retrato antigo
    assert len(pd.read_parquet(pasta / "sida-1-1.parquet")) == 1  # 11.222.333/...
    assert len(pd.read_parquet(pasta / "sida-1-letras.parquet")) == 1
    assert len(pd.read_parquet(pasta / "sida-1-9.parquet")) == 0
    assert resumo["2026-06/sida-1"]["na_tabela"] == 3
    tabela = _ler(pasta, "sida-1")
    assert len(tabela["origem_sha256"].iloc[0]) == 64
    assert tabela["versao_do_codigo"].iloc[0] == "0123abc"
    assert tabela["montado_em"].iloc[0] == AGORA.isoformat()
    assert dict(zip(tabela["cnpj"], tabela["trata_como_pessoa"], strict=True)) == {
        EMPRESA: False,
        MEI: True,
        COM_LETRAS: False,  # aqui as pessoas vêm dadas (sem a Receita)
    }
    assert parquets_sem_manifesto(tmp_path / "base") == []
    for manifesto in pasta.glob("*.json"):
        conferencia = json.loads(manifesto.read_text(encoding="utf-8"))
        assert conferencia["conferencia_do_contrato"]["aprovada"], manifesto.name


def test_disponivel_em_e_o_dia_em_que_o_arquivo_foi_visto_pela_primeira_vez(
    banco, tmp_path, monkeypatch
):
    """A PGFN não diz quando publicou: vale o dia em que o arquivista viu o arquivo (o conservador)."""
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    sida = _zip({"arquivo_lai_SIDA_1_202606.csv": [CABECALHO_SIDA, _sida(EMPRESA)]})
    com_registro("pgfn-divida", lambda _url: sida)(URL_SIDA)
    # a 1ª coleta foi em 14/10; a de hoje achou o mesmo arquivo
    with banco.begin() as conexao:
        conexao.execute(
            sa.update(coletas.coletas).values(
                baixado_em=datetime(2026, 10, 14, 2, 33, tzinfo=UTC)
            )
        )
    com_registro("pgfn-divida", lambda _url: sida)(URL_SIDA)
    with banco.connect() as conexao:
        pgfn.montar(conexao, tmp_path / "base", AGORA, pessoas=set())
    tabela = _ler(tmp_path / "base" / "pgfn_divida" / "2026-06", "sida-1")
    assert tabela["disponivel_em"].tolist() == [date(2026, 10, 14)]
    assert tabela["gerado_em"].tolist() == [date(2026, 7, 23)]


def test_comando_monta_e_sem_a_receita_todos_ficam_como_pessoa(
    banco, tmp_path, monkeypatch
):
    """Sem a Receita guardada não dá para saber quem é MEI: todos marcados (o conservador)."""
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    from scripts import carga_pgfn

    assert carga_pgfn.main(["--pasta", str(tmp_path / "b")]) == 1  # nada guardado ainda
    sida = _zip(
        {
            "arquivo_lai_SIDA_1_202606.csv": [
                CABECALHO_SIDA,
                _sida(EMPRESA),
                _sida(OUTRA),
            ]
        }
    )
    com_registro("pgfn-divida", lambda _url: sida)(URL_SIDA)
    assert carga_pgfn.main(["--pasta", str(tmp_path / "b")]) == 0
    tabela = _ler(tmp_path / "b" / "pgfn_divida" / "2026-06", "sida-1")
    assert tabela["trata_como_pessoa"].all()


def test_zip_ja_montado_e_pulado_sem_reler(banco, tmp_path, monkeypatch):
    """A PGFN muda por trimestre e a carga roda todo mês: o mesmo ZIP não é relido (~40 min)."""
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    sida = _zip({"arquivo_lai_SIDA_1_202606.csv": [CABECALHO_SIDA, _sida(EMPRESA)]})
    com_registro("pgfn-divida", lambda _url: sida)(URL_SIDA)
    ler_de_verdade = pgfn.ler_membro
    with banco.connect() as conexao:
        pgfn.montar(conexao, tmp_path / "base", AGORA, pessoas=set())
        monkeypatch.setattr(
            pgfn, "ler_membro", lambda *_: (_ for _ in ()).throw(AssertionError)
        )
        assert pgfn.montar(conexao, tmp_path / "base", AGORA) == {
            "2026-06/sida-1": pgfn.JA_MONTADO
        }
        monkeypatch.setattr(pgfn, "ler_membro", ler_de_verdade)
        refeito = pgfn.montar(
            conexao, tmp_path / "base", AGORA, pessoas=set(), refazer=True
        )
    assert refeito["2026-06/sida-1"]["na_tabela"] == 1
