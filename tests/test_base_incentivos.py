"""Incentivos por CNPJ na base (linha 525 da fila; Ficha Clara, etapa 4b): REIDI (MME), CDE (ANEEL)
e RDE-IED (BC). Só CNPJ inteiro de dígito certo (no RDE, a raiz bem formada); nome nenhum entra; toda
linha vale desde o dia do arquivo.

Layout conferido em 29/10/2026 nos arquivos de verdade: o REIDI vem em UTF-8 com BOM, datas AAAA-MM-DD
e valores "17.959.886,51"; o CSV mensal da CDE (dentro do ZIP) mistura CPF e CNPJ e traz o mês como
"05/2026"; a rede básica dá o ano e o nome do mês ("Janeiro"); o RDE-IED traz a moeda e o valor sempre
vazios. A coleta grava os CSVs com ";", só com as colunas da lista. Os arquivos daqui são de mentira.
"""

import csv
import hashlib
import io
import json
from datetime import UTC, date, datetime

import pandas as pd
import pytest
import sqlalchemy as sa

from base import cnpj as cnpjs
from base import incentivos
from base.ancoragem import parquets_sem_manifesto
from base.arquivo import fontes
from base.setoriais.revisoes import como_era_em
from src.banco import coletas
from src.banco.coletas import com_registro

AGORA = datetime(2026, 12, 1, 22, tzinfo=UTC)
PRIMEIRO_DIA = date(2026, 10, 29)
SEGUNDO_DIA = date(2026, 11, 29)
URL_DA_CDE = "https://dadosabertos.aneel.gov.br/dataset/x/resource/y/download/cde-beneficiarios-01{mes}.zip"
URL_DA_REDE_BASICA = "https://dadosabertos.aneel.gov.br/dataset/x/resource/z/download/cde-rede-basica-2024.csv"


def _cnpj(raiz: str, filial: str = "0001") -> str:
    """Um CNPJ com o dígito certo, só com os 14 caracteres."""
    for dv in range(100):
        bruto = f"{raiz}{filial}{dv:02d}"
        if cnpjs.dv_confere(bruto):
            return bruto
    raise AssertionError(raiz)


EMPRESA = _cnpj("11222333")
FILIAL = _cnpj("11222333", "0002")
OUTRA = _cnpj("33000167")
DISTRIBUIDORA = _cnpj("86448057")
INVALIDO = EMPRESA[:-1] + str((int(EMPRESA[-1]) + 1) % 10)
CPF = "12345678909"


def _csv(linhas: list[dict[str, str]], codificacao: str) -> bytes:
    """Um CSV como a coleta grava: ";", o cabeçalho com os nomes da fonte."""
    saida = io.StringIO()
    escritor = csv.DictWriter(saida, list(linhas[0]), delimiter=";")
    escritor.writeheader()
    escritor.writerows(linhas)
    return saida.getvalue().encode(codificacao)


def _coletar(banco, fonte: str, url: str, conteudo: bytes, dia: date) -> None:
    """Uma coleta guardada no acervo, como se o arquivista a tivesse baixado no `dia`."""
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


def _reidi(documento: str, processo: str, beneficio: str = "1.394.298,67") -> dict:
    return {
        "Processo": processo,
        "CNPJ": documento,
        "Municipio": "Não Identificado",
        "UF": "MS",
        "idt_projeto": "262",
        "Nome_do_Projeto": "UTE DE MENTIRA",
        "Portaria": "1",
        "Data_inicio_portaria": "2015-01-13",
        "vlr_Total_Com_Incidencia_PISPASEP_COFINS": "17.959.886,51",
        "vlr_Total_Sem_Incidencia_PISPASEP_COFINS": "16.565.587,84",
        "vlr_Beneficio_Fiscal": beneficio,
        "dat_Execucao_Inicio": "2013-06-15",
        "dat_Execucao_Termino": "2015-05-15",
    }


def _cde(
    documento: str, valor: str, tipo: str = "SubsCARFI", mes: str = "05/2026"
) -> dict:
    return {
        "DatGeracaoConjuntoDados": "10/07/2026",
        "AnmReferencia": mes,
        "SigAgente": "COORSEL",
        "NumCNPJDistribuidora": DISTRIBUIDORA,
        "CodIbgeMunicipio": "4218400",
        "IdcTipoFaturamento": "1",
        "IdcClasseConsumidor": "2",
        "IdcSubclasse": "3.31",
        "IdcSubgrupoTarifario": "6",
        "IdcTipoCompraEnergia": "2",
        "NumCPFCNPJCliente": documento,
        "DscTipoSubsidio": tipo,
        "VlrSubsidio": valor,
    }


def _rede_basica(documento: str, valor: str, mes: str = "Janeiro") -> dict:
    return {
        "DatGeracaoConjuntoDados": "23/07/2026 09:24:34",
        "NumAno": "2024",
        "NomMes": mes,
        "NumCNPJ": documento,
        "DscGrupoTarifario": "Rede Básica",
        "IdcClasseConsumidor": "9",
        "IdcTipo": "7",
        "VlrDesconto": valor,
        "VlrCobranca": "",
    }


def _rde(raiz: str, codigo: str, ocorrencia: str = "REGISTRO EFETUADO") -> dict:
    return {
        "CodigoRDE": codigo,
        "CnpjBaseReceptora": raiz,
        "UfPessoaNacional": "SP",
        "PaisPessoaEstrangeira": "ALEMANHA",
        "MoedaOperacao": None,
        "ValorOperacao": None,
        "Sistema": "RDE-IED",
        "Ocorrencia": ocorrencia,
        "Modalidade": "INVESTIMENTO ESTRANGEIRO DIRETO",
        "Ano": 2011,
        "Mes": 11,
    }


def _json(itens: list[dict]) -> bytes:
    return json.dumps({"value": itens}, ensure_ascii=False).encode("utf-8")


def _montar(banco, tmp_path, pessoas=frozenset()) -> dict:
    with banco.connect() as conexao:
        return incentivos.montar(
            conexao, tmp_path / "base", AGORA, pessoas=set(pessoas)
        )


def _tabela(tmp_path, tabela: str, arquivo: str) -> pd.DataFrame:
    return pd.read_parquet(tmp_path / "base" / tabela / f"{arquivo}.parquet")


def _texto_gravado(tmp_path) -> str:
    """Tudo o que foi gravado (Parquets e manifestos), como texto, para procurar nome e CPF."""
    partes = [
        pd.read_parquet(p).astype(str).to_csv(index=False)
        for p in (tmp_path / "base").rglob("*.parquet")
    ]
    partes += [
        p.read_text(encoding="utf-8") for p in (tmp_path / "base").rglob("*.json")
    ]
    return "\n".join(partes)


def test_le_so_as_colunas_que_a_coleta_guarda():
    """Coluna que a coleta não guarda nunca chega aqui: a leitura não pode depender dela."""
    assert set(incentivos._REIDI.values()) <= set(fontes.COLUNAS_DO_REIDI)
    assert set(incentivos._CDE_MENSAL.values()) <= set(fontes.COLUNAS_DA_CDE)
    assert set(incentivos._CDE_REDE_BASICA.values()) <= set(
        fontes.COLUNAS_DA_CDE_NA_REDE_BASICA
    )
    assert set(incentivos._RDE.values()) | {"Ano", "Mes"} <= set(
        fontes.CAMPOS_DO_RDE_IED
    )


def test_reidi_so_cnpj_inteiro_valores_e_datas_da_fonte(banco, tmp_path, monkeypatch):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    linhas = [
        _reidi(EMPRESA, "48500001450201338"),
        _reidi(CPF, "2"),
        _reidi(INVALIDO, "3"),
        _reidi(EMPRESA, "48500001450201338"),  # repetida: fica a primeira
    ]
    conteudo = b"\xef\xbb\xbf" + _csv(linhas, "utf-8")
    _coletar(banco, "mme-reidi", fontes.REIDI_DO_MME, conteudo, PRIMEIRO_DIA)
    resumo = _montar(banco, tmp_path)
    assert resumo["reidi"]["cnpj_invalido"] == 2
    assert resumo["reidi"]["id_repetido"] == 1
    tabela = _tabela(tmp_path, "mme_reidi", "reidi")
    assert len(tabela) == 1
    linha = tabela.iloc[0]
    assert linha["cnpj"] == cnpjs.formatar(EMPRESA)
    assert linha["cnpj_basico"] == "11222333"
    assert linha["id_na_fonte"] == "48500001450201338|262"
    assert linha["valor_do_beneficio"] == pytest.approx(1_394_298.67)
    assert linha["valor_com_incidencia"] == pytest.approx(17_959_886.51)
    assert linha["portaria_em"] == date(2015, 1, 13)
    assert linha["execucao_ate"] == date(2015, 5, 15)
    assert linha["municipio"] == "Não Identificado"
    # a portaria é de 2015, mas a base só soube no dia do arquivo
    assert linha["disponivel_em"] == PRIMEIRO_DIA
    assert CPF not in _texto_gravado(tmp_path)


def test_reidi_que_muda_vira_linha_nova_sem_mudar_o_passado(
    banco, tmp_path, monkeypatch
):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    primeiro = [_reidi(EMPRESA, "1"), _reidi(OUTRA, "2")]
    _coletar(
        banco, "mme-reidi", fontes.REIDI_DO_MME, _csv(primeiro, "utf-8"), PRIMEIRO_DIA
    )
    segundo = [_reidi(EMPRESA, "1", beneficio="2.000,00"), _reidi(OUTRA, "2")]
    _coletar(
        banco, "mme-reidi", fontes.REIDI_DO_MME, _csv(segundo, "utf-8"), SEGUNDO_DIA
    )
    resumo = _montar(banco, tmp_path)
    assert resumo["reidi"]["retratos"] == 2
    tabela = _tabela(tmp_path, "mme_reidi", "reidi")
    assert len(tabela) == 3
    datas = tabela.assign(
        disponivel_em=pd.to_datetime(tabela["disponivel_em"]),
        visto_em=pd.to_datetime(tabela["visto_em"]),
    )
    antes = como_era_em(datas, PRIMEIRO_DIA, ["id_na_fonte"]).set_index("id_na_fonte")
    depois = como_era_em(datas, SEGUNDO_DIA, ["id_na_fonte"]).set_index("id_na_fonte")
    assert antes.loc["1|262", "valor_do_beneficio"] == pytest.approx(1_394_298.67)
    assert depois.loc["1|262", "valor_do_beneficio"] == pytest.approx(2_000.0)


def test_cde_mensal_soma_por_cnpj_tira_cpf_e_cada_mes_e_um_arquivo(
    banco, tmp_path, monkeypatch
):
    """Duas unidades da mesma empresa no mesmo mês e tipo viram uma linha somada (`linhas`=2); a
    filial é outra linha; o CPF que escapasse da coleta sai; maio e junho ficam em arquivos
    separados (um não é retrato do outro)."""
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    maio = [
        _cde(EMPRESA, "13.756,73"),
        _cde(EMPRESA, "1.330,94"),
        _cde(EMPRESA, "10,00", tipo="SubsRural"),
        _cde(FILIAL, "5,00"),
        _cde(CPF, "99,00"),
    ]
    junho = [_cde(OUTRA, "7,00", mes="06/2026")]
    _coletar(
        banco,
        "aneel-cde",
        URL_DA_CDE.format(mes="may2026"),
        _csv(maio, "latin-1"),
        PRIMEIRO_DIA,
    )
    _coletar(
        banco,
        "aneel-cde",
        URL_DA_CDE.format(mes="jun2026"),
        _csv(junho, "latin-1"),
        SEGUNDO_DIA,
    )
    resumo = _montar(banco, tmp_path)
    assert resumo["cde-beneficiarios-01may2026"]["cnpj_invalido"] == 1
    maio_gravado = _tabela(tmp_path, "aneel_cde", "cde-beneficiarios-01may2026")
    assert len(maio_gravado) == 3
    carfi = maio_gravado[
        (maio_gravado["cnpj"] == cnpjs.formatar(EMPRESA))
        & (maio_gravado["tipo_de_desconto"] == "SubsCARFI")
    ].iloc[0]
    assert carfi["valor_do_desconto"] == pytest.approx(15_087.67)
    assert carfi["linhas"] == 2
    assert carfi["mes"] == date(2026, 5, 1)
    assert carfi["gerado_em"] == date(2026, 7, 10)
    assert carfi["distribuidora"] == "COORSEL"
    assert carfi["arquivo"] == "mensal"
    assert set(maio_gravado["cnpj_basico"]) == {"11222333"}
    assert set(maio_gravado["disponivel_em"]) == {PRIMEIRO_DIA}
    junho_gravado = _tabela(tmp_path, "aneel_cde", "cde-beneficiarios-01jun2026")
    assert junho_gravado["consta"].all()  # maio não aparece como saída de junho
    assert junho_gravado["disponivel_em"].tolist() == [SEGUNDO_DIA]
    assert CPF not in _texto_gravado(tmp_path)


def test_cde_republicada_com_correcao_guarda_as_duas(banco, tmp_path, monkeypatch):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    url = URL_DA_CDE.format(mes="may2026")
    _coletar(
        banco, "aneel-cde", url, _csv([_cde(EMPRESA, "10,00")], "latin-1"), PRIMEIRO_DIA
    )
    _coletar(
        banco, "aneel-cde", url, _csv([_cde(EMPRESA, "12,00")], "latin-1"), SEGUNDO_DIA
    )
    _montar(banco, tmp_path)
    tabela = _tabela(tmp_path, "aneel_cde", "cde-beneficiarios-01may2026")
    assert dict(zip(tabela["visto_em"], tabela["valor_do_desconto"], strict=True)) == {
        PRIMEIRO_DIA: pytest.approx(10.0),
        SEGUNDO_DIA: pytest.approx(12.0),
    }


def test_cde_rede_basica_le_o_nome_do_mes_e_fica_sem_distribuidora(
    banco, tmp_path, monkeypatch
):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    linhas = [
        _rede_basica(EMPRESA, "119730,00"),
        _rede_basica(EMPRESA, "112461,60"),  # outra usina do mesmo CNPJ
        _rede_basica(EMPRESA, "1,00", mes="Março"),
    ]
    _coletar(
        banco, "aneel-cde", URL_DA_REDE_BASICA, _csv(linhas, "utf-8"), PRIMEIRO_DIA
    )
    _montar(banco, tmp_path)
    tabela = _tabela(tmp_path, "aneel_cde", "cde-rede-basica-2024").set_index("mes")
    assert tabela.loc[date(2024, 1, 1), "valor_do_desconto"] == pytest.approx(232_191.6)
    assert tabela.loc[date(2024, 1, 1), "linhas"] == 2
    assert tabela.loc[date(2024, 3, 1), "valor_do_desconto"] == pytest.approx(1.0)
    assert tabela["distribuidora"].isna().all()
    assert tabela["valor_cobrado"].isna().all()  # vazio na fonte não vira zero
    assert set(tabela["arquivo"]) == {"rede_basica"}
    assert set(tabela["grupo_tarifario"]) == {"Rede Básica"}


def test_rde_pela_raiz_sem_nome_e_com_o_mes(banco, tmp_path, monkeypatch):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    itens = [
        {**_rde("11222333", "IA001103"), "NomePessoaEstrangeira": "FULANO DE TAL"},
        _rde("11222333", "IA001103", ocorrencia="REGISTRO ENCERRADO"),
        _rde("12ABC345", "IA001104"),
        _rde("1234", "IA001105"),  # raiz mal formada
    ]
    _coletar(
        banco, "bcb-rde-ied", fontes.REGISTROS_DO_RDE_IED, _json(itens), PRIMEIRO_DIA
    )
    resumo = _montar(banco, tmp_path)
    assert resumo["rde_ied"]["cnpj_invalido"] == 1
    tabela = _tabela(tmp_path, "bcb_rde_ied", "rde_ied")
    assert sorted(tabela["cnpj_basico"]) == ["11222333", "11222333", "12ABC345"]
    assert set(tabela["mes"]) == {date(2011, 11, 1)}
    assert set(tabela["ocorrencia"]) == {"REGISTRO EFETUADO", "REGISTRO ENCERRADO"}
    assert set(tabela["disponivel_em"]) == {PRIMEIRO_DIA}
    assert "moeda" not in tabela and "valor" not in tabela
    assert "FULANO" not in _texto_gravado(tmp_path)


def test_montar_grava_com_manifesto_contrato_e_marca_de_pessoa(
    banco, tmp_path, monkeypatch
):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    _coletar(
        banco, "mme-reidi", fontes.REIDI_DO_MME,
        _csv([_reidi(EMPRESA, "1"), _reidi(OUTRA, "2")], "utf-8"), PRIMEIRO_DIA,
    )  # fmt: skip
    _coletar(
        banco, "aneel-cde", URL_DA_CDE.format(mes="may2026"),
        _csv([_cde(EMPRESA, "1,00")], "latin-1"), PRIMEIRO_DIA,
    )  # fmt: skip
    _coletar(
        banco, "bcb-rde-ied", fontes.REGISTROS_DO_RDE_IED,
        _json([_rde("33000167", "IA1")]), PRIMEIRO_DIA,
    )  # fmt: skip
    _montar(banco, tmp_path, pessoas={"33000167"})
    reidi = _tabela(tmp_path, "mme_reidi", "reidi")
    assert dict(zip(reidi["cnpj_basico"], reidi["trata_como_pessoa"], strict=True)) == {
        "11222333": False,
        "33000167": True,
    }
    assert _tabela(tmp_path, "bcb_rde_ied", "rde_ied")["trata_como_pessoa"].all()
    assert len(reidi["origem_sha256"].iloc[0]) == 64
    assert reidi["versao_do_codigo"].iloc[0] == "0123abc"
    assert reidi["montado_em"].iloc[0] == AGORA.isoformat()
    assert parquets_sem_manifesto(tmp_path / "base") == []
    manifestos = list((tmp_path / "base").rglob("*.json"))
    assert len(manifestos) == 3
    for manifesto in manifestos:
        conferencia = json.loads(manifesto.read_text(encoding="utf-8"))
        assert conferencia["conferencia_do_contrato"]["aprovada"], manifesto.name


def test_sem_arquivo_novo_e_pulado(banco, tmp_path, monkeypatch):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    _coletar(
        banco,
        "mme-reidi",
        fontes.REIDI_DO_MME,
        _csv([_reidi(EMPRESA, "1")], "utf-8"),
        PRIMEIRO_DIA,
    )
    _montar(banco, tmp_path)
    assert _montar(banco, tmp_path)["reidi"] == incentivos.JA_MONTADO


def test_nome_do_arquivo_e_valores_em_reais():
    assert incentivos.nome_do_arquivo(URL_DA_CDE.format(mes="MAY2026")) == (
        "cde-beneficiarios-01may2026"
    )
    assert (
        incentivos.nome_do_arquivo("https://x/y/CDE Rede Básica_2024.csv")
        == "cde-rede-b-sica-2024"
    )
    valores = incentivos._reais(pd.Series(["17.959.886,51", "", "abc", None]))
    assert valores.iloc[0] == pytest.approx(17_959_886.51)
    assert valores.iloc[1:].isna().all()


def test_comando_monta_e_sem_nada_guardado_sai_com_1(banco, tmp_path, monkeypatch):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    from scripts import carga_incentivos

    assert carga_incentivos.main(["--pasta", str(tmp_path / "b")]) == 1
    _coletar(
        banco,
        "mme-reidi",
        fontes.REIDI_DO_MME,
        _csv([_reidi(EMPRESA, "1")], "utf-8"),
        PRIMEIRO_DIA,
    )
    assert carga_incentivos.main(["--pasta", str(tmp_path / "b")]) == 0
    tabela = pd.read_parquet(tmp_path / "b" / "mme_reidi" / "reidi.parquet")
    assert tabela["trata_como_pessoa"].all()  # sem a Receita guardada: o conservador
