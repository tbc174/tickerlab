"""Financiamentos por CNPJ na base (linha 469 da fila): BNDES (operações não automáticas) e Finep
(crédito direto e descentralizado). É histórico de contratações, nunca saldo nem dívida: nada se soma,
o vazio fica nulo, e cada banco aparece com o papel dele.

Layout conferido em 04/11/2026 nos arquivos de verdade (piloto da passagem de 04/11): o CSV do BNDES
vem em latin-1 com ";", valores "9090000,0" e situação LIQUIDADO, ATIVO ou "-"; a planilha da Finep tem
o cabeçalho na linha 7, a "Posição: 23/10/2026" na linha 6 e números de verdade nas células. Os
arquivos daqui são de mentira.
"""

import csv
import hashlib
import io
import json
from datetime import UTC, date, datetime
from decimal import Decimal

import openpyxl
import pandas as pd
import pytest
import sqlalchemy as sa

from base import cnpj as cnpjs
from base import financiamentos
from base.ancoragem import parquets_sem_manifesto
from base.arquivo import finep
from base.setoriais.revisoes import como_era_em
from src.banco import coletas
from src.banco.coletas import com_registro

AGORA = datetime(
    2026, 11, 2, 22, tzinfo=UTC
)  # antes de hoje: o contrato recusa data futura
PRIMEIRO_DIA = date(2026, 10, 25)
SEGUNDO_DIA = date(2026, 11, 1)
URL_DO_BNDES = (
    "https://dadosabertos.bndes.gov.br/dataset/x/resource/y/download/"
    + financiamentos.ARQUIVO_DO_BNDES
)
NOME_DE_MENTIRA = "EMPRESA DE MENTIRA LTDA"
PROJETO_DE_MENTIRA = "PROJETO DE MENTIRA"


def _cnpj(raiz: str, filial: str = "0001") -> str:
    """Um CNPJ com o dígito certo, só com os 14 caracteres."""
    for dv in range(100):
        bruto = f"{raiz}{filial}{dv:02d}"
        if cnpjs.dv_confere(bruto):
            return bruto
    raise AssertionError(raiz)


EMPRESA = _cnpj("11222333")
OUTRA = _cnpj("33000167")
BANCO_REPASSADOR = _cnpj("60701190")
INVALIDO = EMPRESA[:-1] + str((int(EMPRESA[-1]) + 1) % 10)
CPF = "12345678909"


# BNDES


def _bndes(documento: str, contrato: str = "1234567", **campos: str) -> dict[str, str]:
    linha = {
        "cliente": NOME_DE_MENTIRA,
        "cnpj": cnpjs.formatar(documento) if len(documento) == 14 else documento,
        "descricao_do_projeto": PROJETO_DE_MENTIRA,
        "uf": "SP",
        "municipio": "SAO PAULO",
        "municipio_codigo": "3550308",
        "numero_do_contrato": contrato,
        "data_da_contratacao": "2002-01-02",
        "valor_contratado_reais": "9090000,0",
        "valor_desembolsado_reais": "9007445,1",
        "fonte_de_recurso_desembolsos": "RECURSOS LIVRES - TESOURO",
        "custo_financeiro": "TJLP",
        "juros": "2,5",
        "prazo_carencia_meses": "24",
        "prazo_amortizacao_meses": "96",
        "modalidade_de_apoio": "REEMBOLSÁVEL",
        "forma_de_apoio": "DIRETA",
        "produto": "BNDES FINEM",
        "instrumento_financeiro": "FINEM",
        "inovacao": "NÃO",
        "area_operacional": "AREA INDUSTRIAL",
        "setor_cnae": "INDÚSTRIA DE TRANSFORMAÇÃO",
        "subsetor_cnae_agrupado": "METALURGIA",
        "subsetor_cnae_codigo": "C24",
        "subsetor_cnae_nome": "METALURGIA",
        "setor_bndes": "INDUSTRIA",
        "subsetor_bndes": "METALURGIA",
        "porte_do_cliente": "GRANDE",
        "natureza_do_cliente": "PRIVADA",
        "instituicao_financeira_credenciada": "----------",
        "cnpj_da_instituicao_financeira_credenciada": "----------",
        "tipo_de_garantia": "REAL",
        "tipo_de_excepcionalidade": "-",
        "situacao_do_contrato": "LIQUIDADO",
    }
    return {**linha, **campos}


def _csv_do_bndes(linhas: list[dict[str, str]]) -> bytes:
    """Como a coleta grava o CSV do BNDES: ";", tudo entre aspas, latin-1."""
    saida = io.StringIO()
    escritor = csv.DictWriter(
        saida, list(linhas[0]), delimiter=";", quoting=csv.QUOTE_ALL
    )
    escritor.writeheader()
    escritor.writerows(linhas)
    return saida.getvalue().encode("latin-1")


def _ler_bndes(tmp_path, linhas: list[dict[str, str]]):
    caminho = tmp_path / "bndes.csv"
    caminho.write_bytes(_csv_do_bndes(linhas))
    return financiamentos.ler_bndes(caminho)


def test_bndes_valores_em_decimal_e_vazio_fica_nulo(tmp_path):
    tabela, _ = _ler_bndes(
        tmp_path,
        [
            _bndes(EMPRESA, "1"),
            _bndes(EMPRESA, "2", valor_desembolsado_reais="", juros=""),
        ],
    )
    um = tabela.set_index("contrato").loc["1"]
    assert um["valor_contratado"] == Decimal("9090000.00")
    assert str(um["valor_contratado"]) == "9090000.00"  # centavos, nunca float
    assert um["valor_desembolsado"] == Decimal("9007445.10")
    assert um["juros"] == Decimal("2.5")
    assert um["carencia_meses"] == 24
    assert um["amortizacao_meses"] == 96
    assert um["contratado_em"] == pd.Timestamp("2002-01-02")
    assert um["cnpj"] == cnpjs.formatar(EMPRESA)
    assert um["cnpj_basico"] == "11222333"
    assert um["fonte"] == "bndes"
    assert um["modalidade"] == "bndes_nao_automatica"
    dois = tabela.set_index("contrato").loc["2"]
    assert dois["valor_desembolsado"] is None  # vazio na fonte não vira zero
    assert dois["juros"] is None


def test_bndes_cada_banco_com_o_seu_papel(tmp_path):
    """DIRETA: o próprio BNDES, sem repassador (é normal); INDIRETA: a instituição credenciada, com o
    CNPJ dela só quando inteiro e de dígito certo."""
    tabela, _ = _ler_bndes(
        tmp_path,
        [
            _bndes(EMPRESA, "1"),
            _bndes(
                EMPRESA, "2", forma_de_apoio="INDIRETA",
                instituicao_financeira_credenciada="BANCO REPASSADOR S.A.",
                cnpj_da_instituicao_financeira_credenciada=cnpjs.formatar(BANCO_REPASSADOR),
            ),
            _bndes(
                EMPRESA, "3", forma_de_apoio="INDIRETA",
                instituicao_financeira_credenciada="BANCO REPASSADOR S.A.",
                cnpj_da_instituicao_financeira_credenciada="60.701.190/0001-00",
            ),
        ],
    )  # fmt: skip
    por_contrato = tabela.set_index("contrato")
    direta = por_contrato.loc["1"]
    assert direta["financiador"] == "BNDES"
    assert direta["agente_papel"] == "financiador_direto"
    assert direta["forma_de_apoio"] == "DIRETA"
    assert cnpjs.dv_confere(cnpjs.completo(direta["cnpj_do_financiador"]))
    indireta = por_contrato.loc["2"]
    assert indireta["financiador"] == "BANCO REPASSADOR S.A."
    assert indireta["agente_papel"] == "instituicao_credenciada"
    assert indireta["cnpj_do_financiador"] == cnpjs.formatar(BANCO_REPASSADOR)
    assert por_contrato.loc["3", "cnpj_do_financiador"] is None


def test_bndes_situacao_como_a_fonte_escreve_e_a_classe(tmp_path):
    tabela, _ = _ler_bndes(
        tmp_path,
        [
            _bndes(EMPRESA, "1", situacao_do_contrato="LIQUIDADO"),
            _bndes(EMPRESA, "2", situacao_do_contrato="ATIVO"),
            _bndes(EMPRESA, "3", situacao_do_contrato="-"),
            _bndes(EMPRESA, "4", situacao_do_contrato="SUSPENSO"),
        ],
    )
    por_contrato = tabela.set_index("contrato")
    assert por_contrato.loc["1", "situacao_classe"] == "liquidado"
    assert por_contrato.loc["2", "situacao_classe"] == "ativo"
    assert por_contrato.loc["3", "situacao"] is None
    assert por_contrato.loc["3", "situacao_classe"] == "nao_informado"
    assert por_contrato.loc["4", "situacao"] == "SUSPENSO"
    assert por_contrato.loc["4", "situacao_classe"] == "nao_classificado"


def test_bndes_subcreditos_ficam_separados_com_id_estavel(tmp_path):
    """O mesmo contrato tem várias linhas (subcréditos), algumas iguais em tudo: nenhuma é somada nem
    descartada, e o `id_na_fonte` de cada uma não depende da ordem do arquivo."""
    linhas = [
        _bndes(EMPRESA, "9", valor_contratado_reais="100,0"),
        _bndes(EMPRESA, "9", valor_contratado_reais="50,0"),
        _bndes(EMPRESA, "9", valor_contratado_reais="100,0"),
        _bndes(EMPRESA, "9", valor_contratado_reais="70,0", juros="3,0"),
    ]
    tabela, _ = _ler_bndes(tmp_path, linhas)
    assert len(tabela) == 4
    assert tabela["id_na_fonte"].is_unique
    assert all(i.startswith("bndes|9|") for i in tabela["id_na_fonte"])
    invertida, _ = _ler_bndes(tmp_path, linhas[::-1])
    antes = dict(zip(tabela["id_na_fonte"], tabela["valor_contratado"], strict=True))
    depois = dict(
        zip(invertida["id_na_fonte"], invertida["valor_contratado"], strict=True)
    )
    assert antes == depois


def test_bndes_so_reembolsavel_e_cnpj_inteiro_sem_nome(tmp_path):
    tabela, contagem = _ler_bndes(
        tmp_path,
        [
            _bndes(EMPRESA, "1"),
            _bndes(EMPRESA, "2", modalidade_de_apoio="NÃO REEMBOLSÁVEL"),
            _bndes(CPF, "3"),
            _bndes(INVALIDO, "4"),
            _bndes("**.***.333/0001-**", "5"),
        ],
    )
    assert tabela["contrato"].tolist() == ["1"]
    assert contagem == {
        "linhas": 5,
        "nao_reembolsavel": 1,
        "cnpj_invalido": 3,
    }
    texto = tabela.astype(str).to_csv()
    assert NOME_DE_MENTIRA not in texto and PROJETO_DE_MENTIRA not in texto


def test_nenhuma_coluna_de_saldo_total_ou_nota():
    """A base não sustenta saldo, dívida atual nem nota (o piloto não sustenta nenhum)."""
    proibidas = ("saldo", "total", "divida", "score", "nota", "soma")
    assert not [c for c in financiamentos.COLUNAS if any(p in c for p in proibidas)]


# Finep: a coleta


def _planilha_da_finep(
    diretos: list[dict], descentralizados: list[dict], sem_aba: str | None = None
) -> bytes:
    """Uma planilha como a da Finep: guia na frente, linhas soltas no topo, a posição na linha 6 e o
    cabeçalho na 7; outras abas (subvenção) que não são crédito."""
    livro = openpyxl.Workbook()
    livro.worksheets[0].title = "Guia_de_Leitura"
    abas = {
        finep.ABA_DO_CREDITO_DIRETO: (finep.CABECALHO_DO_CREDITO_DIRETO, diretos),
        finep.ABA_DO_DESCENTRALIZADO: (
            finep.CABECALHO_DO_DESCENTRALIZADO,
            descentralizados,
        ),
        "Projetos_Subvenção_Direta": (("Título", "CNPJ Proponente"), []),
    }
    for nome, (cabecalho, linhas) in abas.items():
        if nome == sem_aba:
            continue
        aba = livro.create_sheet(nome)
        aba.cell(2, 7, "FINEP - Financiadora de Estudos e Projetos")
        aba.cell(5, 7, nome)
        aba.cell(6, 1, "Posição: 23/10/2026")
        for coluna, titulo in enumerate(cabecalho, 1):
            aba.cell(7, coluna, titulo)
        for numero, linha in enumerate(linhas, 8):
            for coluna, titulo in enumerate(cabecalho, 1):
                aba.cell(numero, coluna, linha.get(titulo))
    saida = io.BytesIO()
    livro.save(saida)
    return saida.getvalue()


def _direto(documento: str, contrato: str, **campos) -> dict:
    linha = {
        "Demanda": "DEMANDA DE MENTIRA",
        "Ref": "3699/06",
        "Contrato": contrato,
        "Data Entrada SF": datetime(2006, 12, 21),  # noqa: DTZ001 (célula do Excel, sem fuso)
        "Data Assinatura": datetime(2008, 11, 26),  # noqa: DTZ001
        "Título": PROJETO_DE_MENTIRA,
        "Proponente": NOME_DE_MENTIRA,
        "CNPJ Proponente": cnpjs.formatar(documento)
        if len(documento) == 14
        else documento,
        "Município Proponente": "BARUERI",
        "UF Proponente": "SP",
        "Executor": NOME_DE_MENTIRA,
        "CNPJ Executor": cnpjs.formatar(OUTRA),
        "UF Projeto": "SP",
        "Valor Finep": 4000000.04,
        "Contrapartida Financeira": 1000000,
        "Valor Pago": 3999999.5,
        "Status": "ENCERRADO",
        "Resumo Publicável": "RESUMO DE MENTIRA",
    }
    return {**linha, **campos}


def _descentralizado(documento: str, convenio: str, **campos) -> dict:
    linha = {
        "Data Assinatura": datetime(2026, 10, 22),  # noqa: DTZ001
        "Contrato Finep Agente": convenio,
        "Beneficiario": NOME_DE_MENTIRA,
        "CNPJ Beneficiário": cnpjs.formatar(documento),
        "UF Beneficiário": "PR",
        "Valor Financiado": 4000000,
        "Valor Liberado": None,
        "Contrapartida": 0,
        "Outros Recursos": 0,
        "Agente": "AGENCIA DE FOMENTO DE MENTIRA",
    }
    return {**linha, **campos}


class _Servidor:
    def __init__(self, arquivos: dict[str, bytes]):
        self.arquivos = arquivos

    def baixar(self, url, destino):
        destino.write_bytes(self.arquivos[url])
        return {"ETag": '"finep-1"'}


def _coletar_finep(tmp_path, planilha: bytes) -> bytes:
    """O CSV que a coleta grava a partir da planilha."""
    destino = tmp_path / "finep.csv"
    obter = finep.planilha_so_credito(finep.CONTRATACAO_DA_FINEP)
    obter(_Servidor({finep.CONTRATACAO_DA_FINEP: planilha}), destino)
    assert not list(tmp_path.glob("*.bruto"))
    return destino.read_bytes()


def test_coleta_da_finep_so_credito_sem_nome_nem_cpf(tmp_path):
    planilha = _planilha_da_finep(
        [
            _direto(EMPRESA, "02.08.0467.00"),
            _direto(CPF, "02.08.0468.00"),
            _direto(INVALIDO, "02.08.0469.00"),
        ],
        [_descentralizado(EMPRESA, "07.22.0001.00")],
    )
    texto = _coletar_finep(tmp_path, planilha).decode("utf-8")
    linhas = list(csv.DictReader(io.StringIO(texto), delimiter=";"))
    assert [linha["aba"] for linha in linhas] == [
        "credito_direto",
        "credito_descentralizado",
    ]
    direto, descentralizado = linhas
    assert direto["posicao"] == "2026-10-23"
    assert direto["Contrato"] == "02.08.0467.00"
    assert direto["Data Assinatura"] == "2008-11-26"
    assert direto["Valor Finep"] == "4000000.04"
    assert direto["Contrapartida Financeira"] == "1000000"
    assert descentralizado["Valor Liberado"] == ""
    assert descentralizado["Agente"] == "AGENCIA DE FOMENTO DE MENTIRA"
    for fora in (
        "Proponente",
        "Executor",
        "Título",
        "Resumo Publicável",
        "Beneficiario",
    ):
        assert fora not in linhas[0]
    for fora in (NOME_DE_MENTIRA, PROJETO_DE_MENTIRA, "RESUMO", "DEMANDA", CPF):
        assert fora not in texto


def test_coleta_da_finep_sem_a_aba_de_credito_falha(tmp_path):
    """Se a Finep renomear a aba, a coleta para em vez de gravar um arquivo sem o crédito."""
    planilha = _planilha_da_finep(
        [_direto(EMPRESA, "1")], [], sem_aba=finep.ABA_DO_DESCENTRALIZADO
    )
    with pytest.raises(ValueError, match="Descentralizado"):
        _coletar_finep(tmp_path, planilha)
    assert not list(tmp_path.glob("*.bruto"))
    assert not (tmp_path / "finep.csv").exists()


def test_coleta_da_finep_sem_a_coluna_do_cnpj_falha(tmp_path):
    direto = _direto(EMPRESA, "1")
    cabecalho = finep.CABECALHO_DO_CREDITO_DIRETO
    finep_sem_cnpj = tuple(
        "CNPJ do Proponente" if c == "CNPJ Proponente" else c for c in cabecalho
    )
    livro = openpyxl.load_workbook(io.BytesIO(_planilha_da_finep([direto], [])))
    for coluna, titulo in enumerate(finep_sem_cnpj, 1):
        livro[finep.ABA_DO_CREDITO_DIRETO].cell(7, coluna, titulo)
    saida = io.BytesIO()
    livro.save(saida)
    with pytest.raises(ValueError, match="CNPJ Proponente"):
        _coletar_finep(tmp_path, saida.getvalue())


# Finep: a leitura


def _ler_finep(tmp_path, diretos: list[dict], descentralizados: list[dict]):
    caminho = tmp_path / "lido.csv"
    caminho.write_bytes(
        _coletar_finep(tmp_path, _planilha_da_finep(diretos, descentralizados))
    )
    return financiamentos.ler_finep(caminho)


def test_le_so_as_colunas_que_a_coleta_guarda():
    """Coluna que a coleta não guarda nunca chega aqui: a leitura não pode depender dela."""
    guardadas = {"aba", "posicao", *finep.COLUNAS_GUARDADAS}
    assert set(financiamentos.COLUNAS_LIDAS_DA_FINEP) <= guardadas


def test_finep_encerrado_e_tecnico_e_valor_pago_e_desembolso(tmp_path):
    tabela, contagem = _ler_finep(
        tmp_path,
        [
            _direto(EMPRESA, "02.08.0467.00"),
            _direto(EMPRESA, "2", Status="Aguardando Quitação de Financiamento"),
            _direto(EMPRESA, "3", Status="AGUARDANDO QUITAÇÃO DO FINANCIAMENTO"),
            _direto(EMPRESA, "4", Status="Aguardando Registro"),
            _direto(EMPRESA, "5", Status="CANCELADO"),
            _direto(EMPRESA, "6", Status="RESCINDIDO"),
            _direto(EMPRESA, "7", Status="Em Execução", **{"Valor Pago": None}),
        ],
        [],
    )
    assert contagem["linhas"] == 7
    por_contrato = tabela.set_index("contrato")
    encerrado = por_contrato.loc["02.08.0467.00"]
    assert encerrado["situacao"] == "ENCERRADO"
    assert encerrado["situacao_classe"] == "encerrado_tecnico"  # nunca "liquidado"
    assert encerrado["valor_contratado"] == Decimal("4000000.04")
    assert encerrado["valor_desembolsado"] == Decimal("3999999.50")
    assert encerrado["financiador"] == "FINEP"
    assert encerrado["agente_papel"] == "financiador_direto"
    assert cnpjs.dv_confere(cnpjs.completo(encerrado["cnpj_do_financiador"]))
    assert encerrado["cnpj_do_executor"] == cnpjs.formatar(OUTRA)
    assert encerrado["contratado_em"] == pd.Timestamp("2008-11-26")
    assert encerrado["fonte"] == "finep"
    assert encerrado["modalidade"] == "finep_credito_direto"
    assert encerrado["id_na_fonte"] == "finep|direto|02.08.0467.00|1"
    assert encerrado["convenio_do_agente"] is None
    classes = por_contrato["situacao_classe"].to_dict()
    assert classes["2"] == classes["3"] == "ativo"
    assert classes["4"] == "pendente"
    assert classes["5"] == "cancelado"
    assert classes["6"] == "rescindido"
    assert classes["7"] == "ativo"
    assert por_contrato.loc["7", "valor_desembolsado"] is None
    assert "liquidado" not in set(classes.values())


def test_finep_descentralizado_e_do_agente_e_o_convenio_nao_e_contrato(tmp_path):
    """O "Contrato Finep Agente" é o convênio entre a Finep e o agente, não o empréstimo da empresa:
    duas empresas no mesmo convênio (e duas operações iguais da mesma) ficam separadas."""
    tabela, _ = _ler_finep(
        tmp_path,
        [],
        [
            _descentralizado(EMPRESA, "07.22.0001.00"),
            _descentralizado(EMPRESA, "07.22.0001.00"),
            _descentralizado(OUTRA, "07.22.0001.00", **{"Valor Liberado": 1073000}),
        ],
    )
    assert len(tabela) == 3
    assert tabela["id_na_fonte"].is_unique
    assert tabela["contrato"].isna().all()
    assert set(tabela["convenio_do_agente"]) == {"07.22.0001.00"}
    assert set(tabela["financiador"]) == {"AGENCIA DE FOMENTO DE MENTIRA"}
    assert set(tabela["agente_papel"]) == {"agente_descentralizado"}
    assert tabela["cnpj_do_financiador"].isna().all()
    assert set(tabela["situacao_classe"]) == {"nao_informado"}
    assert set(tabela["modalidade"]) == {"finep_credito_descentralizado"}
    outra = tabela[tabela["cnpj"] == cnpjs.formatar(OUTRA)].iloc[0]
    assert outra["valor_desembolsado"] == Decimal("1073000.00")
    assert outra["valor_contratado"] == Decimal("4000000.00")


# montagem


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


def _montar(banco, tmp_path, pessoas=frozenset()) -> dict:
    with banco.connect() as conexao:
        return financiamentos.montar(
            conexao, tmp_path / "base", AGORA, pessoas=set(pessoas)
        )


def _tabela(tmp_path, arquivo: str) -> pd.DataFrame:
    return pd.read_parquet(tmp_path / "base" / "financiamentos" / f"{arquivo}.parquet")


def _texto_gravado(tmp_path) -> str:
    partes = [
        pd.read_parquet(p).astype(str).to_csv(index=False)
        for p in (tmp_path / "base").rglob("*.parquet")
    ]
    partes += [
        p.read_text(encoding="utf-8") for p in (tmp_path / "base").rglob("*.json")
    ]
    return "\n".join(partes)


def test_desembolso_que_muda_vira_linha_nova_do_mesmo_registro(
    banco, tmp_path, monkeypatch
):
    """Dois retratos do BNDES: só o desembolso de um subcrédito muda. A mudança vira linha nova do
    mesmo `id_na_fonte`, desde o dia do 2º retrato; nada sai como `consta` falso; o passado não muda."""
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    primeiro = [
        _bndes(EMPRESA, "9", valor_contratado_reais="100,0"),
        _bndes(
            EMPRESA, "9", valor_contratado_reais="50,0", situacao_do_contrato="ATIVO"
        ),
    ]
    segundo = [
        primeiro[0],
        {**primeiro[1], "valor_desembolsado_reais": "60,0"},
    ]
    _coletar(
        banco, "bndes-operacoes", URL_DO_BNDES, _csv_do_bndes(primeiro), PRIMEIRO_DIA
    )
    _coletar(
        banco, "bndes-operacoes", URL_DO_BNDES, _csv_do_bndes(segundo), SEGUNDO_DIA
    )
    resumo = _montar(banco, tmp_path)
    assert resumo["bndes"]["retratos"] == 2
    tabela = _tabela(tmp_path, "bndes")
    assert len(tabela) == 3
    assert tabela["consta"].all()
    assert tabela["id_na_fonte"].nunique() == 2
    datas = tabela.assign(
        disponivel_em=pd.to_datetime(tabela["disponivel_em"]),
        visto_em=pd.to_datetime(tabela["visto_em"]),
    )
    antes = como_era_em(datas, PRIMEIRO_DIA, ["id_na_fonte"])
    depois = como_era_em(datas, SEGUNDO_DIA, ["id_na_fonte"])
    contratado_50 = lambda t: t[t["valor_contratado"] == Decimal("50.00")].iloc[0]
    assert contratado_50(antes)["valor_desembolsado"] == Decimal("9007445.10")
    assert contratado_50(depois)["valor_desembolsado"] == Decimal("60.00")
    nova = tabela[tabela["visto_em"] == SEGUNDO_DIA].iloc[0]
    assert nova["disponivel_em"] == SEGUNDO_DIA  # nunca antes do retrato que a trouxe
    assert set(tabela[tabela["visto_em"] == PRIMEIRO_DIA]["disponivel_em"]) == {
        PRIMEIRO_DIA
    }


def test_registro_que_some_ganha_consta_falso(banco, tmp_path, monkeypatch):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    primeiro = [_bndes(EMPRESA, "1"), _bndes(OUTRA, "2")]
    _coletar(
        banco, "bndes-operacoes", URL_DO_BNDES, _csv_do_bndes(primeiro), PRIMEIRO_DIA
    )
    _coletar(banco, "bndes-operacoes", URL_DO_BNDES, _csv_do_bndes(primeiro[:1] * 1 + [_bndes(EMPRESA, "3")]), SEGUNDO_DIA)  # fmt: skip
    _montar(banco, tmp_path)
    tabela = _tabela(tmp_path, "bndes")
    saiu = tabela[~tabela["consta"]]
    assert saiu["contrato"].tolist() == ["2"]
    assert saiu["disponivel_em"].tolist() == [SEGUNDO_DIA]


def test_montar_grava_bndes_e_finep_com_manifesto_contrato_e_marca_de_pessoa(
    banco, tmp_path, monkeypatch
):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    _coletar(
        banco, "bndes-operacoes", URL_DO_BNDES,
        _csv_do_bndes([_bndes(EMPRESA, "1"), _bndes(OUTRA, "2")]), PRIMEIRO_DIA,
    )  # fmt: skip
    _coletar(
        banco, "bndes-operacoes", URL_DO_BNDES.replace(".csv", ".pdf"), b"%PDF dicionario",
        PRIMEIRO_DIA,
    )  # fmt: skip
    planilha = _planilha_da_finep(
        [_direto(EMPRESA, "02.08.0467.00")], [_descentralizado(OUTRA, "07.22.0001.00")]
    )
    _coletar(
        banco, "finep-contratacao", finep.CONTRATACAO_DA_FINEP,
        _coletar_finep(tmp_path, planilha), PRIMEIRO_DIA,
    )  # fmt: skip
    resumo = _montar(banco, tmp_path, pessoas={"33000167"})
    assert resumo["bndes"]["na_tabela"] == 2
    assert resumo["finep"]["na_tabela"] == 2
    bndes = _tabela(tmp_path, "bndes")
    assert dict(zip(bndes["cnpj_basico"], bndes["trata_como_pessoa"], strict=True)) == {
        "11222333": False,
        "33000167": True,
    }
    assert list(bndes.columns[: len(financiamentos.COLUNAS)]) == financiamentos.COLUNAS
    assert isinstance(bndes["valor_contratado"].iloc[0], Decimal)
    finep_gravada = _tabela(tmp_path, "finep")
    assert set(finep_gravada["modalidade"]) == {
        "finep_credito_direto",
        "finep_credito_descentralizado",
    }
    assert set(finep_gravada["disponivel_em"]) == {PRIMEIRO_DIA}
    assert len(bndes["origem_sha256"].iloc[0]) == 64
    assert bndes["versao_do_codigo"].iloc[0] == "0123abc"
    assert bndes["montado_em"].iloc[0] == AGORA.isoformat()
    assert parquets_sem_manifesto(tmp_path / "base") == []
    manifestos = list((tmp_path / "base").rglob("*.json"))
    assert len(manifestos) == 2
    for manifesto in manifestos:
        conferencia = json.loads(manifesto.read_text(encoding="utf-8"))
        assert conferencia["conferencia_do_contrato"]["aprovada"], (
            manifesto.name,
            conferencia["conferencia_do_contrato"],
        )
    texto = _texto_gravado(tmp_path)
    for fora in (NOME_DE_MENTIRA, PROJETO_DE_MENTIRA, CPF):
        assert fora not in texto


def test_sem_arquivo_novo_e_pulado(banco, tmp_path, monkeypatch):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    _coletar(
        banco, "bndes-operacoes", URL_DO_BNDES, _csv_do_bndes([_bndes(EMPRESA)]),
        PRIMEIRO_DIA,
    )  # fmt: skip
    _montar(banco, tmp_path)
    assert _montar(banco, tmp_path)["bndes"] == financiamentos.JA_MONTADO


def test_comando_monta_e_sem_nada_guardado_sai_com_1(banco, tmp_path, monkeypatch):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    from scripts import carga_financiamentos

    assert carga_financiamentos.main(["--pasta", str(tmp_path / "b")]) == 1
    _coletar(
        banco, "bndes-operacoes", URL_DO_BNDES, _csv_do_bndes([_bndes(EMPRESA)]),
        PRIMEIRO_DIA,
    )  # fmt: skip
    assert carga_financiamentos.main(["--pasta", str(tmp_path / "b")]) == 0
    tabela = pd.read_parquet(tmp_path / "b" / "financiamentos" / "bndes.parquet")
    assert tabela["trata_como_pessoa"].all()  # sem a Receita guardada: o conservador
