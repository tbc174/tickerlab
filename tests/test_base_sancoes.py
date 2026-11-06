"""Sanções por CNPJ na base (linha 525 da fila): CEIS, CNEP, CEPIM e leniência da CGU e as penalidades
da ANS. Só pessoa jurídica com CNPJ de dígito certo; nome nenhum entra.

Layout conferido em 29/10/2026 nos arquivos de verdade (CGU de 29/10 e ANS de 10/2026): `;`, latin-1,
cabeçalho com acento; o CEIS e o CNEP misturam pessoa física (CPF só com dígitos, tipo "F") e jurídica
(tipo "J"); a leniência vem num ZIP com dois CSVs (acordos e efeitos) e às vezes um "CNPJ" que não é
CNPJ (empresa estrangeira); o CEPIM não tem data nenhuma; a ANS escreve o CNPJ com pontuação. Os
arquivos daqui são de mentira.
"""

import hashlib
import io
import json
import zipfile
from datetime import UTC, date, datetime

import pandas as pd
import sqlalchemy as sa

from base import cnpj as cnpjs
from base import sancoes
from base.ancoragem import parquets_sem_manifesto
from base.setoriais.revisoes import como_era_em
from src.banco import coletas
from src.banco.coletas import com_registro

AGORA = datetime(2026, 10, 29, 22, tzinfo=UTC)
CABECALHO_CEIS = (
    '"CADASTRO";"CÓDIGO DA SANÇÃO";"TIPO DE PESSOA";"CPF OU CNPJ DO SANCIONADO";"NOME DO SANCIONADO";'
    '"NOME INFORMADO PELO ÓRGÃO SANCIONADOR";"RAZÃO SOCIAL - CADASTRO RECEITA";'
    '"NOME FANTASIA - CADASTRO RECEITA";"NÚMERO DO PROCESSO";"CATEGORIA DA SANÇÃO";'
    '"DATA INÍCIO SANÇÃO";"DATA FINAL SANÇÃO";"DATA PUBLICAÇÃO";"PUBLICAÇÃO";'
    '"DETALHAMENTO DO MEIO DE PUBLICAÇÃO";"DATA DO TRÂNSITO EM JULGADO";"ABRAGÊNCIA DA SANÇÃO";'
    '"ÓRGÃO SANCIONADOR";"UF ÓRGÃO SANCIONADOR";"ESFERA ÓRGÃO SANCIONADOR";"FUNDAMENTAÇÃO LEGAL";'
    '"DATA ORIGEM INFORMAÇÃO";"ORIGEM INFORMAÇÕES";"OBSERVAÇÕES"'
)
CABECALHO_CNEP = CABECALHO_CEIS.replace(
    '"CATEGORIA DA SANÇÃO";', '"CATEGORIA DA SANÇÃO";"VALOR DA MULTA";'
)
CABECALHO_CEPIM = '"CNPJ ENTIDADE";"NOME ENTIDADE";"NÚMERO CONVÊNIO";"ÓRGÃO CONCEDENTE";"MOTIVO DO IMPEDIMENTO"'
CABECALHO_ACORDOS = (
    '"ID DO ACORDO";"CNPJ DO SANCIONADO";"RAZÃO SOCIAL \x96 CADASTRO RECEITA";'
    '"NOME FANTASIA \x96 CADASTRO RECEITA";"DATA DE INÍCIO DO ACORDO";"DATA DE FIM DO ACORDO";'
    '"SITUAÇÃO DO ACORDO DE LENIÊNICA";"DATA DA INFORMAÇÃO";"NÚMERO DO PROCESSO";"TERMOS DO ACORDO";'
    '"ÓRGÃO SANCIONADOR"'
)
CABECALHO_EFEITOS = '"ID DO ACORDO";"EFEITO DO ACORDO DE LENIENCIA";"COMPLEMENTO"'
CABECALHO_ANS = (
    "NR_DEMANDA;NR_PROCESSO;TIPO_PROCESSO;OBJETO;REGISTRO_OPERADORA;CNPJ;RAZAO_SOCIAL;"
    "SITUACAO_OPERADORA;STATUS_DEMANDA;DT_DECISAO_1A;DT_PUBLICACAO_1A;DT_PUBLICACAO_1A_FINAL;"
    "VL_MULTA_FIXA_1A;VL_MULTA_DIARIA_1A;VL_TOTAL_APLICADO_1A;DT_CIENCIA_RECONSIDERA_TOTAL;"
    "DT_DECISAO_2A;DT_PUBLICACAO_2A;TIPO_DECISAO_2A;VL_MULTA_FIXA_2A;VL_MULTA_DIARIA_2A;"
    "VL_TOTAL_APLICADO_2A;VL_MULTA_FINAL_APLICADA;VL_TOTAL_DESCONTOS;DT_ARQUIVAMENTO;"
    "MOTIVO_ARQUIVAMENTO;TIPO_PENALIDADE;DT_SUSPENSAO_ADM;DT_SUSPENSAO_JUD;NR_GRU;DT_VENC_GRU;VL_GRU;"
    "DE_SITUACAO_GRU;DT_PAGTO_A_VISTA_ANS;VL_PAGO_A_VISTA_ANS;DT_VENC_1A_PARC_ANS;"
    "VL_PARCELAS_ANS_PAGAS;STATUS_PARCELAMENTO;DT_INSCRICAO;INSCRITO_DA;ORIGEM_PAGAMENTO;"
    "NR_COMPETENCIA_CARGA"
)
URL_CEIS = "https://portaldatransparencia.gov.br/download-de-dados/ceis/{dia}"
URL_CNEP = "https://portaldatransparencia.gov.br/download-de-dados/cnep/20261028"
URL_CEPIM = "https://portaldatransparencia.gov.br/download-de-dados/cepim/20261028"
URL_LENIENCIA = (
    "https://portaldatransparencia.gov.br/download-de-dados/acordos-leniencia/20261028"
)
URL_ANS = (
    "https://dadosabertos.ans.gov.br/FTP/PDA/penalidades_aplicadas_a_operadoras/"
    "penalidades_aplicadas_a_operadoras.csv"
)
URL_OUTRA_DA_ANS = "https://dadosabertos.ans.gov.br/FTP/PDA/historico_idss-020/idss.csv"


def _cnpj(raiz: str, filial: str = "0001") -> str:
    """Um CNPJ com o dígito certo, só com os 14 caracteres (como a CGU escreve)."""
    for dv in range(100):
        bruto = f"{raiz}{filial}{dv:02d}"
        if cnpjs.dv_confere(bruto):
            return bruto
    raise AssertionError(raiz)


EMPRESA = _cnpj("11222333")
OUTRA = _cnpj("33000167")
MEI = _cnpj("44555666")
INVALIDO = EMPRESA[:-1] + str((int(EMPRESA[-1]) + 1) % 10)
CPF = "12345678909"
NOME_DA_PESSOA = "MARIA DA SILVA DE MENTIRA"
RAZAO_SOCIAL = "EMPRESA DE MENTIRA LTDA"


def _ceis(
    codigo: str,
    documento: str = EMPRESA,
    pessoa: str = "J",
    nome: str = RAZAO_SOCIAL,
    inicio: str = "11/11/2015",
    fim: str = "11/11/2027",
    publicacao: str = "19/05/2017",
    origem: str = "20/05/2017",
    multa: str | None = None,
) -> str:
    campos = [
        "CEIS", codigo, pessoa, documento, nome, nome, nome, nome, "123/2017",
        "Suspensão", inicio, fim, publicacao, "DOU", "Seção 3", "", "Nacional",
        "Prefeitura de Mentira", "SP", "MUNICIPAL", "Lei 8.666/93, art. 87", origem,
        "Controladoria de Mentira", "observação com o nome " + nome,
    ]  # fmt: skip
    if multa is not None:
        campos.insert(10, multa)
    return ";".join(f'"{c}"' for c in campos)


def _ans(
    demanda: str,
    cnpj: str = EMPRESA,
    status: str = "Em Cobrança",
    publicacao: str = "03/06/2019",
    multa: str = "47520",
) -> str:
    campos = [""] * 42
    campos[0], campos[1], campos[2], campos[5], campos[6] = (
        demanda, "33910.000001/2019-01", "Consumidor", cnpjs.formatar(cnpj), RAZAO_SOCIAL,
    )  # fmt: skip
    campos[8], campos[9], campos[10], campos[22], campos[26] = (
        status, "31/05/2019", publicacao, multa, "Multa Pecuniária",
    )  # fmt: skip
    campos[29] = "\t2900000000"  # o NR_GRU vem com uma tabulação na frente
    return ";".join(campos)


def _csv(cabecalho: str, *linhas: str) -> bytes:
    return "\r\n".join([cabecalho, *linhas]).encode("latin-1")


def _zip(membros: dict[str, bytes]) -> bytes:
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as arquivo:
        for nome, conteudo in membros.items():
            arquivo.writestr(nome, conteudo)
    return saida.getvalue()


def _ceis_zip(*linhas: str) -> bytes:
    return _zip({"20261028_CEIS.csv": _csv(CABECALHO_CEIS, *linhas)})


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


def _ceis_no_dia(banco, dia: date, *linhas: str) -> None:
    _coletar(
        banco, "cgu-ceis", URL_CEIS.format(dia=f"{dia:%Y%m%d}"), _ceis_zip(*linhas), dia
    )


def _montar(banco, tmp_path, pessoas=frozenset()) -> dict:
    with banco.connect() as conexao:
        return sancoes.montar(conexao, tmp_path / "base", AGORA, pessoas=set(pessoas))


def _tabela(tmp_path, cadastro: str) -> pd.DataFrame:
    tabela = sancoes.CADASTROS[cadastro].tabela
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


def test_so_pj_nas_sancoes(banco, tmp_path, monkeypatch):
    """Pessoa física sai pelo tipo e pelo documento; nome nenhum entra, nem o da empresa."""
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    _ceis_no_dia(
        banco,
        date(2026, 10, 14),
        _ceis("1", EMPRESA),
        _ceis("2", CPF, pessoa="F", nome=NOME_DA_PESSOA),
        _ceis(
            "3", OUTRA, pessoa="F", nome=NOME_DA_PESSOA
        ),  # tipo F com documento de CNPJ
        _ceis("4", INVALIDO),
        _ceis(
            "5", "000" + CPF, nome=NOME_DA_PESSOA
        ),  # CPF com zeros à esquerda não vira CNPJ
    )
    resumo = _montar(banco, tmp_path)
    tabela = _tabela(tmp_path, "ceis")
    assert tabela["cnpj"].tolist() == [cnpjs.formatar(EMPRESA)]
    assert tabela["cnpj_basico"].tolist() == ["11222333"]
    assert resumo["ceis"]["pessoa_fisica"] == 2
    assert resumo["ceis"]["cnpj_invalido"] == 2
    gravado = _texto_gravado(tmp_path)
    assert "MENTIRA" not in gravado and CPF not in gravado
    assert not [c for c in tabela.columns if "nome" in c or "razao" in c]


def test_sancao_usa_a_publicacao_e_nunca_o_inicio(banco, tmp_path, monkeypatch):
    """No primeiro retrato guardado vale a publicação (ou a data em que o órgão informou, se for
    depois), nunca o início da sanção; o que só aparece num retrato seguinte vale desde o dia dele."""
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    antigas = (
        _ceis(
            "1",
            EMPRESA,
            inicio="11/11/2015",
            publicacao="19/05/2017",
            origem="20/05/2017",
        ),
        _ceis("2", OUTRA, inicio="01/02/2016", publicacao="", origem=""),
        _ceis("3", MEI, publicacao="10/01/2018", origem="03/03/2026"),
        _ceis(
            "4", _cnpj("55666777"), publicacao="01/12/2026", origem=""
        ),  # data de mentira
    )
    _ceis_no_dia(banco, date(2026, 10, 14), *antigas)
    _ceis_no_dia(banco, date(2026, 10, 20), *antigas, _ceis("9", _cnpj("99888777")))
    _montar(banco, tmp_path)
    tabela = _tabela(tmp_path, "ceis").set_index("id_na_fonte")
    assert tabela.loc["1", "disponivel_em"] == date(2017, 5, 20)
    assert tabela.loc["1", "inicio"] == date(2015, 11, 11)
    assert tabela.loc["2", "disponivel_em"] == date(
        2026, 10, 14
    )  # sem data: o dia do retrato
    assert tabela.loc["3", "disponivel_em"] == date(2026, 3, 3)
    assert tabela.loc["4", "disponivel_em"] == date(
        2026, 10, 14
    )  # nunca depois de visto
    assert tabela.loc["9", "disponivel_em"] == date(
        2026, 10, 20
    )  # entrou depois: desde o dia
    assert (tabela["disponivel_em"] >= tabela["inicio"].fillna(date.min)).all()


def test_sancao_que_sumiu_do_arquivo_fica_como_saida(banco, tmp_path, monkeypatch):
    """A sanção que sai do CEIS ganha uma linha `consta=False` no dia em que sumiu; o passado fica."""
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    fica, sai = _ceis("1", EMPRESA), _ceis("2", OUTRA)
    _ceis_no_dia(banco, date(2026, 10, 14), fica, sai)
    _ceis_no_dia(banco, date(2026, 10, 15), fica)
    _ceis_no_dia(banco, date(2026, 10, 16), fica, sai)  # e voltou
    _montar(banco, tmp_path)
    tabela = _tabela(tmp_path, "ceis")
    da_outra = tabela[tabela["id_na_fonte"] == "2"]
    assert da_outra["consta"].tolist() == [True, False, True]
    assert da_outra["disponivel_em"].tolist()[1:] == [
        date(2026, 10, 15),
        date(2026, 10, 16),
    ]
    chave = ["id_na_fonte"]
    em_datas = tabela.assign(  # como a porta lê: datas do pandas
        disponivel_em=pd.to_datetime(tabela["disponivel_em"]),
        visto_em=pd.to_datetime(tabela["visto_em"]),
    )
    no_dia_14 = como_era_em(em_datas, date(2026, 10, 14), chave).set_index(
        "id_na_fonte"
    )
    no_dia_15 = como_era_em(em_datas, date(2026, 10, 15), chave).set_index(
        "id_na_fonte"
    )
    assert no_dia_14.loc["2", "consta"] and not no_dia_15.loc["2", "consta"]
    assert (
        len(tabela[tabela["id_na_fonte"] == "1"]) == 1
    )  # o mesmo valor não vira linha nova


def test_revisao_da_sancao_vira_linha_nova_que_so_vale_desde_o_dia_em_que_foi_vista(
    banco, tmp_path, monkeypatch
):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    _ceis_no_dia(banco, date(2026, 10, 14), _ceis("1", EMPRESA, fim="11/11/2027"))
    _ceis_no_dia(banco, date(2026, 10, 15), _ceis("1", EMPRESA, fim="11/11/2030"))
    _montar(banco, tmp_path)
    tabela = _tabela(tmp_path, "ceis")
    assert tabela["fim"].tolist() == [date(2027, 11, 11), date(2030, 11, 11)]
    assert tabela["disponivel_em"].tolist() == [date(2017, 5, 20), date(2026, 10, 15)]
    assert tabela["visto_em"].tolist() == [date(2026, 10, 14), date(2026, 10, 15)]


def test_retrato_muito_menor_que_o_anterior_e_pulado(banco, tmp_path, monkeypatch):
    """Arquivo cortado pela metade não pode tirar metade das sanções do ar."""
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    todas = [_ceis(str(i), _cnpj(f"{10000000 + i}")) for i in range(1, 11)]
    _ceis_no_dia(banco, date(2026, 10, 14), *todas)
    _ceis_no_dia(banco, date(2026, 10, 15), *todas[:3])
    resumo = _montar(banco, tmp_path)
    assert resumo["ceis"]["retratos_pulados"] == 1
    assert _tabela(tmp_path, "ceis")["consta"].all()


def test_cnep_traz_o_valor_da_multa(banco, tmp_path, monkeypatch):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    cnep = _zip(
        {
            "20261028_CNEP.csv": _csv(
                CABECALHO_CNEP, _ceis("7", EMPRESA, multa="7986,15")
            )
        }
    )
    _coletar(banco, "cgu-cnep", URL_CNEP, cnep, date(2026, 10, 28))
    _montar(banco, tmp_path)
    tabela = _tabela(tmp_path, "cnep")
    assert tabela["valor_multa"].tolist() == [7986.15]
    assert tabela["cadastro"].tolist() == ["cnep"]
    assert tabela["orgao"].tolist() == ["Prefeitura de Mentira"]
    assert tabela["esfera_do_orgao"].tolist() == ["MUNICIPAL"]


def test_leniencia_le_so_os_acordos_e_descarta_o_que_nao_e_cnpj(
    banco, tmp_path, monkeypatch
):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    acordos = _csv(
        CABECALHO_ACORDOS,
        f'"10";"{EMPRESA}";"{RAZAO_SOCIAL}";"";"14/08/2017";"31/12/2019";"Cumprido";"";"00190.1/2017";'
        f'"termos com o nome {NOME_DA_PESSOA}";"CGU"',
        '"11";"EXBILFINGER";"ESTRANGEIRA";"";"01/01/2018";"";"Em execução";"";"1";"";"CGU"',
    )
    efeitos = _csv(CABECALHO_EFEITOS, '"10";"Redução da multa";"em 2/3"')
    leniencia = _zip({"20261028_Acordos.csv": acordos, "20261028_Efeitos.csv": efeitos})
    _coletar(banco, "cgu-leniencia", URL_LENIENCIA, leniencia, date(2026, 10, 28))
    resumo = _montar(banco, tmp_path)
    tabela = _tabela(tmp_path, "leniencia")
    assert tabela["id_na_fonte"].tolist() == ["10"]
    assert tabela["situacao"].tolist() == ["Cumprido"]
    assert tabela["categoria"].tolist() == ["Acordo de leniência"]
    assert tabela["inicio"].tolist() == [date(2017, 8, 14)]
    assert resumo["leniencia"]["cnpj_invalido"] == 1
    assert "MENTIRA" not in _texto_gravado(tmp_path)


def test_cepim_sem_data_vale_desde_o_retrato(banco, tmp_path, monkeypatch):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    cepim = _zip(
        {
            "20261028_CEPIM.csv": _csv(
                CABECALHO_CEPIM,
                f'"{EMPRESA}";"{RAZAO_SOCIAL}";"700123";"MINISTERIO DE MENTIRA";"Omissão no Dever de Prestar Contas"',
            )
        }
    )
    _coletar(banco, "cgu-cepim", URL_CEPIM, cepim, date(2026, 10, 28))
    _montar(banco, tmp_path)
    tabela = _tabela(tmp_path, "cepim")
    assert tabela["id_na_fonte"].tolist() == [f"{EMPRESA}|700123"]
    assert tabela["disponivel_em"].tolist() == [date(2026, 10, 28)]
    assert tabela["categoria"].tolist() == ["Omissão no Dever de Prestar Contas"]


def test_penalidades_da_ans_com_a_situacao_que_muda_de_um_mes_para_outro(
    banco, tmp_path, monkeypatch
):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    _coletar(banco, "ans-qualidade", URL_OUTRA_DA_ANS, b"a;b\r\n1;2", date(2026, 10, 1))
    _coletar(
        banco,
        "ans-qualidade",
        URL_ANS,
        _csv(CABECALHO_ANS, _ans("500")),
        date(2026, 10, 1),
    )
    _coletar(
        banco,
        "ans-qualidade",
        URL_ANS,
        _csv(CABECALHO_ANS, _ans("500", status="Arquivado"), _ans("501", OUTRA)),
        date(2026, 10, 25),
    )
    resumo = _montar(banco, tmp_path)
    assert resumo["penalidades"]["retratos"] == 2  # o outro arquivo da ANS não entra
    tabela = _tabela(tmp_path, "penalidades")
    assert (tmp_path / "base" / "ans_penalidades" / "penalidades.parquet").exists()
    da_500 = tabela[tabela["id_na_fonte"] == "500"]
    assert da_500["situacao"].tolist() == ["Em Cobrança", "Arquivado"]
    assert da_500["disponivel_em"].tolist() == [date(2019, 6, 3), date(2026, 10, 25)]
    assert set(tabela["cnpj"]) == {cnpjs.formatar(EMPRESA), cnpjs.formatar(OUTRA)}
    assert set(tabela["valor_multa"]) == {47520.0}
    assert set(tabela["orgao"]) == {"ANS"}
    assert set(tabela["assunto"]) == {"Consumidor"}
    assert "MENTIRA" not in _texto_gravado(tmp_path)


def test_montar_grava_com_manifesto_contrato_e_marca_de_pessoa(
    banco, tmp_path, monkeypatch
):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    _ceis_no_dia(banco, date(2026, 10, 14), _ceis("1", EMPRESA), _ceis("2", MEI))
    _montar(banco, tmp_path, pessoas={"44555666"})
    tabela = _tabela(tmp_path, "ceis")
    assert dict(
        zip(tabela["id_na_fonte"], tabela["trata_como_pessoa"], strict=True)
    ) == {
        "1": False,
        "2": True,
    }
    assert len(tabela["origem_sha256"].iloc[0]) == 64
    assert tabela["versao_do_codigo"].iloc[0] == "0123abc"
    assert tabela["montado_em"].iloc[0] == AGORA.isoformat()
    assert parquets_sem_manifesto(tmp_path / "base") == []
    for manifesto in (tmp_path / "base").rglob("*.json"):
        conferencia = json.loads(manifesto.read_text(encoding="utf-8"))
        assert conferencia["conferencia_do_contrato"]["aprovada"], manifesto.name


def test_retrato_novo_so_acrescenta_e_o_ja_montado_e_pulado(
    banco, tmp_path, monkeypatch
):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    _ceis_no_dia(banco, date(2026, 10, 14), _ceis("1", EMPRESA))
    _montar(banco, tmp_path)
    assert _montar(banco, tmp_path)["ceis"] == sancoes.JA_MONTADO
    _ceis_no_dia(banco, date(2026, 10, 15), _ceis("1", EMPRESA), _ceis("2", OUTRA))
    _montar(banco, tmp_path)
    assert len(_tabela(tmp_path, "ceis")) == 2
    pasta = tmp_path / "base" / "sancoes_cgu"
    assert not list(
        pasta.glob("ceis.v*.parquet")
    )  # o passado não mudou: nada de versão


def test_comando_monta_e_sem_nada_guardado_sai_com_1(banco, tmp_path, monkeypatch):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    from scripts import carga_sancoes

    assert carga_sancoes.main(["--pasta", str(tmp_path / "b")]) == 1
    _ceis_no_dia(banco, date(2026, 10, 14), _ceis("1", EMPRESA))
    assert carga_sancoes.main(["--pasta", str(tmp_path / "b")]) == 0
    tabela = pd.read_parquet(tmp_path / "b" / "sancoes_cgu" / "ceis.parquet")
    assert tabela["trata_como_pessoa"].all()  # sem a Receita guardada: o conservador
