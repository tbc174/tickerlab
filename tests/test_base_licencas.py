"""Licenças e registros por CNPJ na base (linha 525 da fila; Ficha Clara, etapa 2b): Anvisa, ANTT
(RNTRC), MAPA (SIPEAGRO), Anatel, ANM e Ancine. Só CNPJ inteiro de dígito certo; nome nenhum entra; toda
linha vale desde o dia do arquivo.

Layout conferido em 29/10/2026 nos arquivos de verdade: a coleta grava todos com ";", só com as colunas
da lista; a AFE e o CBPF da Anvisa escrevem as datas como MM/DD/AAAA 00:00:00, os produtos como
DD/MM/AAAA 00:00:00 e o vencimento dos alimentos como MMAAAA; o SIPEAGRO repete linhas iguais; a
Anatel tem acento no nome das colunas. Os arquivos daqui são de mentira.
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
from base import licencas
from base import retratos as motor
from base.ancoragem import parquets_sem_manifesto
from base.arquivo import fontes
from base.setoriais.revisoes import como_era_em
from src.banco import coletas
from src.banco.coletas import com_registro

AGORA = datetime(2026, 12, 1, 22, tzinfo=UTC)
PRIMEIRO_DIA = date(2026, 10, 29)
SEGUNDO_DIA = date(2026, 11, 29)
URL_DA_AFE = fontes.CADASTROS_DE_EMPRESAS_DA_ANVISA[0].url
URL_DOS_ALIMENTOS = next(
    c.url for c in fontes.CADASTROS_DE_PRODUTOS_DA_ANVISA if "ALIMENTOS" in c.url
)
URL_DOS_MEDICAMENTOS = next(
    c.url for c in fontes.CADASTROS_DE_PRODUTOS_DA_ANVISA if "MEDICAMENTOS" in c.url
)
URL_DO_RNTRC = (
    "https://dados.antt.gov.br/dataset/rntrc/resource/{mes}/download/rntrc_{mes}.csv"
)
URL_DA_AVIACAO = fontes.CADASTROS_DO_SIPEAGRO[1].url
URL_DA_LAVRA = next(
    c.url for c in fontes.CADASTRO_MINEIRO_FILTRADO if "/Portaria_de_Lavra." in c.url
)
# as fontes de endereço fixo: (fonte, o arquivo como a coleta o define)
COLETAS_FIXAS = [
    *(("anvisa-empresas", c) for c in fontes.CADASTROS_DE_EMPRESAS_DA_ANVISA),
    *(("anvisa-produtos", c) for c in fontes.CADASTROS_DE_PRODUTOS_DA_ANVISA),
    *(("mapa-sipeagro", c) for c in fontes.CADASTROS_DO_SIPEAGRO),
    ("anatel-outorgas", fontes.OUTORGAS_DA_ANATEL_FILTRADAS),
    *(("anm-cadastro-mineiro", c) for c in fontes.CADASTRO_MINEIRO_FILTRADO),
    ("ancine-agentes", fontes.AGENTES_DA_ANCINE_FILTRADOS),
]


def _cnpj(raiz: str, filial: str = "0001") -> str:
    """Um CNPJ com o dígito certo, só com os 14 caracteres."""
    for dv in range(100):
        bruto = f"{raiz}{filial}{dv:02d}"
        if cnpjs.dv_confere(bruto):
            return bruto
    raise AssertionError(raiz)


EMPRESA = _cnpj("11222333")
OUTRA = _cnpj("33000167")
COM_LETRAS = _cnpj("12ABC345", "01DE")
MEI = _cnpj("44555666")
INVALIDO = EMPRESA[:-1] + str((int(EMPRESA[-1]) + 1) % 10)
CPF = "12345678909"
RAZAO_SOCIAL = "EMPRESA DE MENTIRA LTDA"


def _csv(linhas: list[dict[str, str]], codificacao: str = licencas.LATIN1) -> bytes:
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


def _afe(documento: str, autorizacao: str, ativo: str = "SIM", **extra: str) -> dict:
    return {
        "NU_CNPJ": documento,
        "NO_RAZAO_SOCIAL": RAZAO_SOCIAL,  # a coleta não guarda; aqui confere que nem é lida
        "NU_AUTORIZACAO": autorizacao,
        "NU_PROCESSO": "25351790864201030",
        "DT_AUTORIZACAO": "01/24/2011 00:00:00",
        "ATIVO": ativo,
        "TIPO_PRODUTO": "MEDICAMENTOS",
        "DT_CANCELAMENTO": "",
        "DT_PUBLICACAO": "01/25/2011 00:00:00",
        "CIDADE": "SÃO PAULO",
        "UF": "SP",
        **extra,
    }


def _rntrc(documento: str, numero: str, situacao: str = "ATIVO") -> dict:
    return {
        "numero_rntrc": numero,
        "data_primeiro_cadastro": "15/03/2009",
        "situacao_rntrc": situacao,
        "cpfcnpjtransportador": documento,
        "categoria_transportador": "ETC",
        "municipio": "CAMPINAS",
        "uf": "SP",
        "equiparado": "NÃO",
        "data_situacao_rntrc": "01/10/2026",
    }


def _montar(banco, tmp_path, pessoas=frozenset()) -> dict:
    with banco.connect() as conexao:
        return licencas.montar(conexao, tmp_path / "base", AGORA, pessoas=set(pessoas))


def _tabela(tmp_path, cadastro: str) -> pd.DataFrame:
    tabela = licencas.CADASTROS[cadastro].tabela
    return pd.read_parquet(tmp_path / "base" / tabela / f"{cadastro}.parquet")


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


@pytest.mark.parametrize(("fonte", "arquivo"), COLETAS_FIXAS)
def test_cada_arquivo_coletado_tem_um_cadastro_que_o_le(fonte, arquivo):
    """O endereço, o documento, a codificação e as colunas de cada cadastro batem com a coleta
    (`base/arquivo/fontes.py`): coluna que a coleta não guarda nunca chegaria aqui."""
    lidos = [
        c
        for c in licencas.CADASTROS.values()
        if c.fonte == fonte
        and (c.url_termina_em is None or arquivo.url.endswith(c.url_termina_em))
    ]
    assert len(lidos) == 1, arquivo.url
    cadastro = lidos[0]
    assert cadastro.cnpj_em == arquivo.cnpj_em
    assert cadastro.codificacao == arquivo.codificacao.removesuffix("-sig")
    guardadas = set(arquivo.colunas)
    assert {f for fs in cadastro.colunas.values() for f in fs} <= guardadas


def test_rntrc_le_as_colunas_que_a_coleta_guarda():
    cadastro = licencas.CADASTROS["rntrc"]
    assert cadastro.cnpj_em == "cpfcnpjtransportador"
    assert {f for fs in cadastro.colunas.values() for f in fs} <= set(
        fontes.COLUNAS_DO_RNTRC
    )


def test_so_cnpj_inteiro_entra_com_letras_ou_nao(banco, tmp_path, monkeypatch):
    """CPF, CNPJ mascarado e dígito errado saem (se escaparem da coleta); o CNPJ com letras fica;
    nome nenhum entra."""
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    linhas = [
        _afe(EMPRESA, "1"),
        _afe(cnpjs.formatar(COM_LETRAS), "2"),
        _afe(CPF, "3"),
        _afe("**.***.101/***-**", "4"),
        _afe(INVALIDO, "5"),
    ]
    _coletar(banco, "anvisa-empresas", URL_DA_AFE, _csv(linhas), PRIMEIRO_DIA)
    resumo = _montar(banco, tmp_path)
    tabela = _tabela(tmp_path, "afe")
    assert tabela["cnpj"].tolist() == [
        cnpjs.formatar(EMPRESA),
        cnpjs.formatar(COM_LETRAS),
    ]
    assert tabela["cnpj_basico"].tolist() == ["11222333", "12ABC345"]
    assert resumo["afe"]["cnpj_invalido"] == 3
    gravado = _texto_gravado(tmp_path)
    assert "MENTIRA" not in gravado and CPF not in gravado


def test_afe_le_a_data_americana_e_vale_desde_o_dia_do_arquivo(
    banco, tmp_path, monkeypatch
):
    """A data da fonte fica na coluna dela; `disponivel_em` é o dia do arquivo, mesmo no primeiro:
    a fonte não diz desde quando vale a situação que publica."""
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    linhas = [_afe(EMPRESA, "1", ativo="NAO", DT_CANCELAMENTO="01/25/2014 00:00:00")]
    _coletar(banco, "anvisa-empresas", URL_DA_AFE, _csv(linhas), PRIMEIRO_DIA)
    _montar(banco, tmp_path)
    linha = _tabela(tmp_path, "afe").iloc[0]
    assert linha["concedido_em"] == date(2011, 1, 24)
    assert linha["publicado_em"] == date(2011, 1, 25)
    assert linha["cancelado_em"] == date(2014, 1, 25)
    assert linha["situacao"] == "NAO"
    assert linha["disponivel_em"] == PRIMEIRO_DIA
    assert linha["id_na_fonte"] == "1|25351790864201030"


def test_alimentos_com_vencimento_so_do_mes_e_registro_de_outra_coluna(
    banco, tmp_path, monkeypatch
):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    linhas = [
        {
            "NU_CNPJ_EMPRESA": EMPRESA,
            "CO_SEQ_PRODUTO": "47256",
            "NO_PRODUTO": "BISCOITO",
            "NU_PROCESSO": "2500400488797",
            "NU_REGISTRO_PRODUTO": "",
            "NU_REGISTRO_NOTIFICACAO_PRODUTO": "410940109",
            "DT_VENCIMENTO_REGISTRO": "022009",
            "DT_REGULARIZACAO": "03/03/1999 00:00:00",
            "DT_PUBLICACAO": "03/03/1999 00:00:00",
            "SITUACAO_REGISTRO": "Inativo",
            "DS_CATEGORIA_PRODUTO": "BISCOITOS",
        }
    ]
    _coletar(banco, "anvisa-produtos", URL_DOS_ALIMENTOS, _csv(linhas), PRIMEIRO_DIA)
    _montar(banco, tmp_path)
    linha = _tabela(tmp_path, "alimentos").iloc[0]
    assert linha["vence_em"] == date(2009, 2, 1)
    assert linha["concedido_em"] == date(1999, 3, 3)
    assert linha["registro"] == "410940109"
    assert linha["situacao"] == "Inativo"
    assert linha["categoria"] == "BISCOITOS"
    assert linha["id_na_fonte"] == "47256"


def test_medicamento_com_varias_apresentacoes_fica_uma_vez(
    banco, tmp_path, monkeypatch
):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    medicamento = {
        "NU_CNPJ_EMPRESA": EMPRESA,
        "CO_SEQ_PRODUTO": "70549",
        "NO_PRODUTO": "REMÉDIO DE MENTIRINHA",
        "NU_REGISTRO_PRODUTO": "113000267",
        "VALIDADE_SITUACAO": "Válido",
        "DATA_PUBLICACAO": "22/12/1999 00:00:00",
    }
    _coletar(
        banco,
        "anvisa-produtos",
        URL_DOS_MEDICAMENTOS,
        _csv([medicamento, medicamento]),
        PRIMEIRO_DIA,
    )
    resumo = _montar(banco, tmp_path)
    assert resumo["medicamentos"]["id_repetido"] == 1
    assert _tabela(tmp_path, "medicamentos")["publicado_em"].tolist() == [
        date(1999, 12, 22)
    ]


def test_rntrc_de_cada_mes_e_um_retrato_com_mudanca_e_saida(
    banco, tmp_path, monkeypatch
):
    """A situação que muda vira linha nova desde o dia do arquivo novo, e o transportador que some
    ganha `consta` falso; o estado de um dia sai do `como_era_em`."""
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    _coletar(
        banco,
        "antt-rntrc",
        URL_DO_RNTRC.format(mes="2026-10"),
        _csv([_rntrc(EMPRESA, "1"), _rntrc(OUTRA, "2")]),
        PRIMEIRO_DIA,
    )
    _coletar(
        banco,
        "antt-rntrc",
        URL_DO_RNTRC.format(mes="2026-11"),
        _csv([_rntrc(EMPRESA, "1", situacao="SUSPENSO")]),
        SEGUNDO_DIA,
    )
    resumo = _montar(banco, tmp_path)
    assert resumo["rntrc"]["retratos"] == 2
    tabela = _tabela(tmp_path, "rntrc")
    assert len(tabela) == 4
    primeiro = tabela[tabela["visto_em"] == PRIMEIRO_DIA]
    assert set(primeiro["disponivel_em"]) == {PRIMEIRO_DIA}
    assert primeiro["situacao_desde"].iloc[0] == date(2026, 10, 1)
    depois = tabela[tabela["visto_em"] == SEGUNDO_DIA].set_index("id_na_fonte")
    assert depois.loc["1", "situacao"] == "SUSPENSO"
    assert not depois.loc["2", "consta"]
    assert set(depois["disponivel_em"]) == {SEGUNDO_DIA}
    datas = tabela.assign(
        disponivel_em=pd.to_datetime(tabela["disponivel_em"]),
        visto_em=pd.to_datetime(tabela["visto_em"]),
    )
    no_primeiro = como_era_em(datas, PRIMEIRO_DIA, ["id_na_fonte"]).set_index(
        "id_na_fonte"
    )
    assert no_primeiro.loc["1", "situacao"] == "ATIVO"  # o futuro não muda o passado
    assert no_primeiro.loc["2", "consta"]


def test_sipeagro_em_utf8_com_linha_repetida_e_uma_linha_por_aeronave(
    banco, tmp_path, monkeypatch
):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")

    def aeronave(numero: str) -> dict:
        return {
            "UNIDADE_DA_FEDERACAO": "BA",
            "MUNICIPIO": "LUÍS EDUARDO MAGALHÃES",
            "NUMERO_REGISTRO_ESTABELECIMENTO": "BA0016047",
            "STATUS_REGISTRO_ESTABELECIMENTO": "Ativo",
            "CPF_CNPJ": cnpjs.formatar(EMPRESA),
            "ATIVIDADE": "EMPRESAS DE AVIAÇÃO AGRÍCOLA",
            "CLASSIFICACAO": "AERONAVE CONVENCIONAL",
            "NUMERO_REGISTRO_AERONAVE": numero,
        }

    linhas = [aeronave("PSSAL"), aeronave("PSSAL"), aeronave("PRABC")]
    conteudo = _csv(linhas, licencas.UTF8)
    _coletar(banco, "mapa-sipeagro", URL_DA_AVIACAO, conteudo, PRIMEIRO_DIA)
    resumo = _montar(banco, tmp_path)
    assert resumo["aviacao_agricola"]["id_repetido"] == 1
    tabela = _tabela(tmp_path, "aviacao_agricola")
    assert sorted(tabela["complemento"]) == ["PRABC", "PSSAL"]
    assert set(tabela["municipio"]) == {"LUÍS EDUARDO MAGALHÃES"}
    assert set(tabela["situacao"]) == {"Ativo"}


def test_anatel_com_acento_no_nome_das_colunas(banco, tmp_path, monkeypatch):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    linha = {
        "Tipo de Identificação": "CNPJ",
        "CNPJ ou CPF": EMPRESA,
        "Tipo de Entidade": "Outorgada",
        "Tipo de Outorga": "Serviços de Interesse Restrito - SIR",
        "Fistel da Outorga": "50437303314",
        "Processo SEI da Outorga": "53500036134202046",
        "Data Inclusão da Outorga": "12/02/2021",
        "Código e Nome do Serviço da Notificação": "076 - Serviço de Rede Privado",
        "Fistel da Notificação": "50413785505",
        "Nome do Munícipio do Endereço Sede": "PORTO ALEGRE",
        "UF do Endereço Sede": "RS",
    }
    _coletar(
        banco,
        "anatel-outorgas",
        fontes.OUTORGAS_DA_ANATEL,
        _csv([linha], licencas.UTF8),
        PRIMEIRO_DIA,
    )
    _montar(banco, tmp_path)
    gravada = _tabela(tmp_path, "outorgas").iloc[0]
    assert gravada["id_na_fonte"] == "50437303314|50413785505"
    assert gravada["municipio"] == "PORTO ALEGRE"
    assert gravada["concedido_em"] == date(2021, 2, 12)
    assert gravada["descricao"] == "076 - Serviço de Rede Privado"


def test_anm_tem_um_cadastro_por_tipo_de_titulo(banco, tmp_path, monkeypatch):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    linha = {
        "Processo": "860623/2019",
        "Tipo de requerimento": "Portaria de Lavra",
        "Fase Atual": "CONCESSÃO DE LAVRA",
        "CPF/CNPJ do titular": cnpjs.formatar(EMPRESA),
        "Municipio(s)": "ORIZONA - GO",
        "Substância(s)": "CALCÁRIO",
        "Tipo(s) de Uso": "Corretivo de solo",
        "Situação": "Sim",
    }
    _coletar(banco, "anm-cadastro-mineiro", URL_DA_LAVRA, _csv([linha]), PRIMEIRO_DIA)
    resumo = _montar(banco, tmp_path)
    assert set(resumo) == {"portaria_de_lavra"}
    gravada = _tabela(tmp_path, "portaria_de_lavra").iloc[0]
    assert gravada["id_na_fonte"] == "860623/2019|Portaria de Lavra"
    assert (
        gravada["situacao"] == "CONCESSÃO DE LAVRA"
    )  # a "Situação" Sim/Não fica de fora
    assert gravada["descricao"] == "CALCÁRIO"


def test_montar_grava_com_manifesto_contrato_e_marca_de_pessoa(
    banco, tmp_path, monkeypatch
):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    linhas = [
        {
            "REGISTRO_ANCINE": "59538",
            "DATA_REGISTRO": "19/09/2024",
            "CNPJ": documento,
            "UF": "RJ",
            "MUNICIPIO": "RIO DE JANEIRO",
            "CLASSIFICACAO_AGENTE_ECONOMICO": "Produtora",
            "NATUREZA_JURIDICA": natureza,
            "BRASILEIRO_INDEPENDENTE": "Sim",
        }
        for documento, natureza in (
            (EMPRESA, "Sociedade Empresária Limitada"),
            (MEI, "Empresário (Individual)"),
        )
    ]
    linhas[1]["REGISTRO_ANCINE"] = "32426"
    _coletar(
        banco,
        "ancine-agentes",
        fontes.AGENTES_DA_ANCINE,
        _csv(linhas, licencas.UTF8),
        PRIMEIRO_DIA,
    )
    _coletar(
        banco, "anvisa-empresas", URL_DA_AFE, _csv([_afe(EMPRESA, "1")]), PRIMEIRO_DIA
    )
    _montar(banco, tmp_path, pessoas={"44555666"})
    tabela = _tabela(tmp_path, "agentes")
    assert dict(
        zip(tabela["id_na_fonte"], tabela["trata_como_pessoa"], strict=True)
    ) == {"59538": False, "32426": True}
    assert len(tabela["origem_sha256"].iloc[0]) == 64
    assert tabela["versao_do_codigo"].iloc[0] == "0123abc"
    assert tabela["montado_em"].iloc[0] == AGORA.isoformat()
    assert parquets_sem_manifesto(tmp_path / "base") == []
    manifestos = list((tmp_path / "base").rglob("*.json"))
    assert len(manifestos) == 2
    for manifesto in manifestos:
        conferencia = json.loads(manifesto.read_text(encoding="utf-8"))
        assert conferencia["conferencia_do_contrato"]["aprovada"], manifesto.name


def test_retrato_novo_so_acrescenta_e_o_ja_montado_e_pulado(
    banco, tmp_path, monkeypatch
):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    _coletar(
        banco, "anvisa-empresas", URL_DA_AFE, _csv([_afe(EMPRESA, "1")]), PRIMEIRO_DIA
    )
    _montar(banco, tmp_path)
    assert _montar(banco, tmp_path)["afe"] == licencas.JA_MONTADO
    _coletar(
        banco,
        "anvisa-empresas",
        URL_DA_AFE,
        _csv([_afe(EMPRESA, "1"), _afe(OUTRA, "2")]),
        SEGUNDO_DIA,
    )
    _montar(banco, tmp_path)
    assert len(_tabela(tmp_path, "afe")) == 2
    pasta = tmp_path / "base" / "anvisa_registros"
    assert not list(pasta.glob("afe.v*.parquet"))  # o passado não mudou: nada de versão


def test_datas_em_mais_de_um_formato_e_o_que_nao_e_data_fica_nulo():
    texto = pd.Series(["24/01/2011 00:00:00", "022009", "", "31/02/2020"])
    datas = licencas._datas(texto, (licencas.DIA_MES_ANO, licencas.MES_ANO))
    assert datas.iloc[0] == pd.Timestamp(2011, 1, 24)
    assert datas.iloc[1] == pd.Timestamp(2009, 2, 1)
    assert datas.iloc[2:].isna().all()


def test_primeira_coluna_cheia_e_coluna_que_a_fonte_nao_manda():
    bruta = pd.DataFrame({"NUREGISTRO": ["", "2"], "NUREGISTROPRODUTO": ["1", ""]})
    valor = licencas._primeira_cheia(
        bruta, ("NU_REGISTRO_PRODUTO", "NU_REGISTRO", "NU_QUE_NAO_EXISTE")
    )
    assert valor.tolist() == ["1", "2"]
    assert motor.nome_da_coluna("Nome do Munícipio") == "NOMEDOMUNICIPIO"


def test_comando_monta_e_sem_nada_guardado_sai_com_1(banco, tmp_path, monkeypatch):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    from scripts import carga_licencas

    assert carga_licencas.main(["--pasta", str(tmp_path / "b")]) == 1
    _coletar(
        banco, "anvisa-empresas", URL_DA_AFE, _csv([_afe(EMPRESA, "1")]), PRIMEIRO_DIA
    )
    assert carga_licencas.main(["--pasta", str(tmp_path / "b")]) == 0
    tabela = pd.read_parquet(tmp_path / "b" / "anvisa_registros" / "afe.parquet")
    assert tabela["trata_como_pessoa"].all()  # sem a Receita guardada: o conservador
