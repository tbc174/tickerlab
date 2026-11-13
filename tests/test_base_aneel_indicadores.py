"""Inadimplência e indicadores comerciais (INDGER) das distribuidoras da ANEEL em retrato (linha 904):
formato com vírgula decimal, só CNPJ de DV certo, MEI marcado como pessoa, a data de geração fora da
comparação dos retratos e sem olhar o futuro. Arquivos de mentira, no formato conferido em 13/11/2026."""

import hashlib
from datetime import UTC, date, datetime

import pandas as pd
import sqlalchemy as sa

from base import aneel_indicadores as aneel
from base import cadastros_em_retrato as montagem
from base import cnpj as cnpjs
from base.parquet import LINHAGEM
from src.banco import coletas
from src.banco.coletas import com_registro

AGORA = datetime(2026, 12, 1, 22, tzinfo=UTC)
PRIMEIRO_DIA = date(2026, 11, 4)
SEGUNDO_DIA = date(2026, 12, 1)
PASTA = "https://dadosabertos.aneel.gov.br/dataset/x/resource"
URL_DA_INADIMPLENCIA = f"{PASTA}/1/download/inadimplencia.csv"
URL_DO_DICIONARIO = f"{PASTA}/2/download/dm-inadimplencia.pdf"
URL_DO_DOMINIO = f"{PASTA}/3/download/dominio-indicadores.csv"
URL_COMERCIAL = f"{PASTA}/4/download/indger-dados-comerciais.csv"
PROIBIDAS = (
    "nome",
    "nomagente",
    "razao",
    "cpf",
    "email",
    "telefone",
    "endereco",
    "contato",
    "dthcarga",
)


def _cnpj(raiz: str, filial: str = "0001") -> str:
    for dv in range(100):
        bruto = f"{raiz}{filial}{dv:02d}"
        if cnpjs.dv_confere(bruto):
            return bruto
    raise AssertionError(raiz)


EMPRESA = _cnpj("11222333")
OUTRA = _cnpj("33000167")
MEI = _cnpj("44555666")
DV_ERRADO = EMPRESA[:-1] + str((int(EMPRESA[-1]) + 1) % 10)


def _cpf(primeiros_9: str) -> str:
    for dv in range(100):
        if cnpjs.cpf_confere(bruto := f"{primeiros_9}{dv:02d}"):
            return bruto
    raise AssertionError(primeiros_9)


CPF = _cpf("888000005")


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


def _csv(cabecalho: list[str], linhas: list[list[str]], codificacao: str) -> bytes:
    def linha(campos: list[str]) -> str:
        return ";".join(f'"{c}"' for c in campos)

    return "\r\n".join([linha(cabecalho), *map(linha, linhas)]).encode(codificacao)


def _inadimplencia(gerado: str, *linhas: tuple[str, str, str, str, str, str]) -> bytes:
    """`linhas`: (sigla do agente, CNPJ, indicador, ano, mês, valor)."""
    cabecalho = [
        "DatGeracaoConjuntoDados", "SigAgente", "NumCNPJ", "SigIndicador", "AnoIndice",
        "NumPeriodoIndice", "VlrIndiceEnviado",
    ]  # fmt: skip
    return _csv(cabecalho, [[gerado, *linha] for linha in linhas], "ascii")


def _dominio(*pares: tuple[str, str]) -> bytes:
    return _csv(
        ["DatGeracaoConjuntoDados", "SigIndicador", "DscIndicador"],
        [["2026-08-05", sigla, descricao] for sigla, descricao in pares],
        "utf-8",
    )


CABECALHO_COMERCIAL = [
    "DatGeracaoConjuntoDados", "NumCNPJ", "SigAgente", "NomAgente", "NomTipoOutorga",
    "DatReferenciaInformada", "CodMunicipioIBGE", *aneel.NUMEROS_COMERCIAIS,
    "QtdFaturaAcerto", "DthCarga",
]  # fmt: skip


def _comerciais(gerado: str, *linhas: dict[str, str]) -> bytes:
    """Cada linha diz o que muda do padrão (as quantidades são `0`)."""
    padrao = {
        "DatGeracaoConjuntoDados": gerado,
        "NomAgente": "DISTRIBUIDORA X DE ENERGIA",
        "NomTipoOutorga": "Concessão",
        "DatReferenciaInformada": "2026-06-01",
        "CodMunicipioIBGE": "3550308",
        "DthCarga": "2026-10-19 03:00:00",
        **dict.fromkeys(aneel.NUMEROS_COMERCIAIS, "0"),
        "QtdFaturaAcerto": "9",
    }
    return _csv(
        CABECALHO_COMERCIAL,
        [[{**padrao, **linha}[c] for c in CABECALHO_COMERCIAL] for linha in linhas],
        "utf-8",
    )


def _montar(banco, pasta, pessoas=frozenset()) -> dict:
    with banco.connect() as conexao:
        return aneel.montar(conexao, pasta, AGORA, pessoas=set(pessoas))


def _ler(pasta, tabela: str, nome: str) -> pd.DataFrame:
    return pd.read_parquet(pasta / tabela / f"{nome}.parquet")


def test_le_a_inadimplencia_com_virgula_decimal_e_a_descricao_do_dominio():
    conteudo = _inadimplencia(
        "21-10-2026",
        ("DISTRIBUIDORA X", EMPRESA, "ITotCrt", "2012", "1", "2884,00"),
        ("DISTRIBUIDORA X", EMPRESA, "ITot24", "2012", "12", "1,46"),
    )
    tabela, contagem = aneel.ler_inadimplencia(
        conteudo, {"ITotCrt": "Inadimplência total, em reais"}
    )
    assert contagem == {
        "linhas": 2, "pessoa_fisica": 0, "cnpj_invalido": 0, "referencia_invalida": 0,
        "sem_valor": 0, "id_repetido": 0,
    }  # fmt: skip
    assert list(tabela["valor"]) == [2884.0, 1.46]
    assert list(tabela["referencia"]) == [
        pd.Timestamp(2012, 1, 1),
        pd.Timestamp(2012, 12, 1),
    ]
    assert list(tabela["id_na_fonte"]) == [
        f"{EMPRESA}|ITotCrt|2012|1",
        f"{EMPRESA}|ITot24|2012|12",
    ]
    assert tabela["cnpj"].iloc[0] == cnpjs.formatar(EMPRESA)
    assert tabela["cnpj_basico"].iloc[0] == EMPRESA[:8]
    assert tabela["descricao_do_indicador"].iloc[0] == "Inadimplência total, em reais"
    assert pd.isna(tabela["descricao_do_indicador"].iloc[1])  # sigla fora do domínio
    assert tabela[aneel.GERADO_EM].iloc[0] == pd.Timestamp(2026, 10, 21)


def test_le_o_indger_com_decimal_sem_zero_a_esquerda_e_tira_o_nome_do_agente():
    conteudo = _comerciais(
        "2026-10-19",
        {"NumCNPJ": EMPRESA, "SigAgente": "DISTRIBUIDORA X", "QtdUCAtiva": "2870,000000000",
         "VlrPagoRessarcDano": ",500000000"},
        {"NumCNPJ": EMPRESA, "SigAgente": "DISTRIBUIDORA X", "CodMunicipioIBGE": "0"},
        {"NumCNPJ": EMPRESA, "SigAgente": "DISTRIBUIDORA X", "CodMunicipioIBGE": "0"},
    )  # fmt: skip
    tabela, contagem = aneel.ler_comerciais(conteudo)
    assert contagem["id_repetido"] == 1  # a fonte repete linhas idênticas
    assert len(tabela) == 2
    primeira = tabela.iloc[0]
    assert primeira["unidades_ativas"] == 2870.0
    assert primeira["valor_pago_de_ressarcimento"] == 0.5
    assert primeira["municipio_ibge"] == "3550308"
    assert primeira["tipo_de_outorga"] == "Concessão"
    assert primeira["referencia"] == pd.Timestamp(2026, 6, 1)
    assert primeira["id_na_fonte"] == f"{EMPRESA}|3550308|2026-06-01"
    assert pd.isna(tabela["municipio_ibge"].iloc[1])  # o `0` da fonte não é município
    assert "DISTRIBUIDORA X DE ENERGIA" not in tabela.astype(str).to_csv()


def test_cnpj_de_dv_errado_e_cpf_saem_e_sao_contados():
    inadimplencia, contagem = aneel.ler_inadimplencia(
        _inadimplencia(
            "21-10-2026",
            ("DISTRIBUIDORA X", EMPRESA, "ITot1", "2020", "3", "1,0"),
            ("DISTRIBUIDORA Y", DV_ERRADO, "ITot1", "2020", "3", "1,0"),
            ("PESSOA", CPF, "ITot1", "2020", "3", "1,0"),
        ),
        {},
    )
    assert contagem["pessoa_fisica"] == 1 and contagem["cnpj_invalido"] == 1
    assert list(inadimplencia["cnpj_basico"]) == [EMPRESA[:8]]
    comerciais, contagem = aneel.ler_comerciais(
        _comerciais(
            "2026-10-19",
            {"NumCNPJ": OUTRA, "SigAgente": "DISTRIBUIDORA X"},
            {"NumCNPJ": DV_ERRADO, "SigAgente": "DISTRIBUIDORA Y"},
            {"NumCNPJ": CPF, "SigAgente": "PESSOA"},
        )
    )
    assert contagem["pessoa_fisica"] == 1 and contagem["cnpj_invalido"] == 1
    assert list(comerciais["cnpj_basico"]) == [OUTRA[:8]]


def _dd_mm_aaaa(aaaa_mm_dd: str) -> str:
    return date.fromisoformat(aaaa_mm_dd).strftime("%d-%m-%Y")


def _coletar_os_dois(banco, dia: date, gerado: str, valor: str = "1,5") -> None:
    """Um retrato da inadimplência e um do INDGER no `dia`, gerados em `gerado` (`AAAA-MM-DD`)."""
    _coletar(
        banco,
        aneel.FONTE_DA_INADIMPLENCIA,
        URL_DA_INADIMPLENCIA,
        _inadimplencia(
            _dd_mm_aaaa(gerado),
            ("DISTRIBUIDORA X", EMPRESA, "ITot1", "2020", "3", valor),
            ("DISTRIBUIDORA M", MEI, "ITot1", "2020", "3", "2,0"),
        ),
        dia,
    )
    _coletar(
        banco,
        aneel.FONTE_COMERCIAL,
        URL_COMERCIAL,
        _comerciais(
            gerado,
            {"NumCNPJ": EMPRESA, "SigAgente": "DISTRIBUIDORA X", "QtdFatura": valor},
            {"NumCNPJ": MEI, "SigAgente": "DISTRIBUIDORA M"},
        ),
        dia,
    )


def test_montar_grava_as_duas_tabelas_com_as_colunas_certas_e_marca_o_mei(
    banco, tmp_path
):
    _coletar_os_dois(banco, PRIMEIRO_DIA, "2026-10-21")
    _coletar(
        banco,
        aneel.FONTE_DA_INADIMPLENCIA,
        URL_DO_DICIONARIO,
        b"%PDF-1.4",
        PRIMEIRO_DIA,
    )
    _coletar(
        banco,
        aneel.FONTE_DA_INADIMPLENCIA,
        URL_DO_DOMINIO,
        _dominio(("ITot1", "Inadimplência total")),
        PRIMEIRO_DIA,
    )
    resumo = _montar(banco, tmp_path, pessoas={MEI[:8]})
    assert set(resumo) == {"inadimplencia", "comerciais"}
    assert (
        resumo["inadimplencia"]["retratos"] == 1
    )  # o PDF e o domínio não são retratos
    for cadastro in aneel.CADASTROS:
        tabela = _ler(tmp_path, cadastro.tabela, cadastro.nome)
        assert list(tabela.columns) == [
            *cadastro.colunas, *montagem.CARIMBOS_DA_LINHA, *LINHAGEM,
        ]  # fmt: skip
        assert aneel.GERADO_EM not in tabela.columns
        assert not [c for c in tabela.columns if any(p in c.lower() for p in PROIBIDAS)]
        assert dict(
            zip(tabela["cnpj_basico"], tabela["trata_como_pessoa"], strict=True)
        ) == {EMPRESA[:8]: False, MEI[:8]: True}
    inadimplencia = _ler(tmp_path, aneel.TABELA_DA_INADIMPLENCIA, "inadimplencia")
    assert set(inadimplencia["descricao_do_indicador"]) == {"Inadimplência total"}
    assert set(inadimplencia["referencia"]) == {date(2020, 3, 1)}


def test_disponivel_em_e_a_data_de_geracao_nunca_depois_do_retrato(banco, tmp_path):
    _coletar_os_dois(banco, PRIMEIRO_DIA, "2026-10-21")
    _montar(banco, tmp_path)
    for cadastro in aneel.CADASTROS:
        tabela = _ler(tmp_path, cadastro.tabela, cadastro.nome)
        assert set(tabela["disponivel_em"]) == {date(2026, 10, 21)}
    gerado_depois = pd.DataFrame(
        {aneel.GERADO_EM: [pd.Timestamp(2026, 12, 25), pd.NaT]}
    )
    dia = pd.Timestamp(PRIMEIRO_DIA)
    assert list(aneel.disponivel_no_primeiro(gerado_depois, dia)) == [dia, dia]


def test_nova_data_de_geracao_com_os_mesmos_valores_nao_cria_linha(banco, tmp_path):
    _coletar_os_dois(banco, PRIMEIRO_DIA, "2026-10-21")
    _montar(banco, tmp_path)
    _coletar_os_dois(banco, SEGUNDO_DIA, "2026-11-28")
    resumo = _montar(banco, tmp_path)
    assert resumo["inadimplencia"]["retratos"] == 2
    assert resumo["inadimplencia"]["na_tabela"] == 2
    assert resumo["comerciais"]["na_tabela"] == 2


def test_cortar_o_futuro_nao_muda_o_passado(banco, tmp_path):
    _coletar_os_dois(banco, PRIMEIRO_DIA, "2026-10-21")
    _montar(banco, tmp_path / "so_o_primeiro")
    _coletar_os_dois(banco, SEGUNDO_DIA, "2026-11-28", valor="9,5")
    _montar(banco, tmp_path / "com_os_dois")
    for cadastro in aneel.CADASTROS:
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


def test_dominio_guardado_depois_do_retrato_nao_da_descricao(banco, tmp_path):
    _coletar_os_dois(banco, PRIMEIRO_DIA, "2026-10-21")
    _coletar(
        banco,
        aneel.FONTE_DA_INADIMPLENCIA,
        URL_DO_DOMINIO,
        _dominio(("ITot1", "Inadimplência total")),
        SEGUNDO_DIA,
    )
    _montar(banco, tmp_path)
    tabela = _ler(tmp_path, aneel.TABELA_DA_INADIMPLENCIA, "inadimplencia")
    assert tabela["descricao_do_indicador"].isna().all()


def test_segundo_montar_sem_retrato_novo_e_ja_montado(banco, tmp_path):
    _coletar_os_dois(banco, PRIMEIRO_DIA, "2026-10-21")
    _montar(banco, tmp_path)
    assert _montar(banco, tmp_path) == {
        "inadimplencia": montagem.JA_MONTADO,
        "comerciais": montagem.JA_MONTADO,
    }
