"""Revendedores varejistas de combustíveis da ANP (base/arquivo/anp_revendedores.py e base/anp_revendedores.py,
linha 1123), em duas tabelas: o cadastro (CSV dos dados abertos, CC BY) e o detalhe por produto (API da ANP,
licença a confirmar, fechado). Só as colunas da lista chegam ao acervo (sem razão social, endereço nem
coordenada), o MEI é marcado e nada usa o dado antes do dia em que o vimos. Respostas inventadas no formato
conferido em 26/11/2026; nenhum documento nem nome real."""

import csv
import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pytest
import sqlalchemy as sa

from base import anp_revendedores as revendedores
from base import cadastros_em_retrato as montagem
from base import cnpj as cnpjs
from base import dossie, licenca, vitrine
from base.arquivo import anp_revendedores as arquivista
from base.arquivo.coleta import Resposta
from base.arquivo.fontes import POR_ID
from base.parquet import LINHAGEM
from src.banco import coletas
from src.banco.coletas import Marca, com_registro, licenca_da_fonte, marca_da_fonte
from tests.ajudantes_de_cpf import CPF_DE_TESTE

AGORA = datetime(2026, 12, 1, 22, tzinfo=UTC)
DIA = date(2026, 11, 26)
DIA_SEGUINTE = date(2026, 12, 26)
NOME_INVENTADO = "POSTO FICTICIO DE TESTE LTDA"
RUA_INVENTADA = "RUA INVENTADA DO TESTE"
M3 = "m³"
PROIBIDOS = (
    NOME_INVENTADO,
    CPF_DE_TESTE,
    RUA_INVENTADA,
    "FUNDOS",
    "BAIRRO INVENTADO",
    "88330000",
    "-26.9999999",
    "OBSERVACAO LIVRE",
    "PR/SC0001234",
)


def _cnpj(raiz: str, filial: str = "0001") -> str:
    for dv in range(100):
        if cnpjs.dv_confere(bruto := f"{raiz}{filial}{dv:02d}"):
            return bruto
    raise AssertionError(raiz)


EMPRESA = _cnpj("11222333")
FILIAL = _cnpj("11222333", "0002")
MEI = _cnpj("44555666")
DV_ERRADO = EMPRESA[:-1] + str((int(EMPRESA[-1]) + 1) % 10)


class Servidor:
    """Responde `ler` com a página pedida da API e `baixar` com o CSV, em memória, e guarda o que foi pedido."""

    def __init__(self, paginas: list[bytes] | None = None, arquivo: bytes = b""):
        self.paginas = paginas or []
        self.arquivo = arquivo
        self.pedidos: list[str] = []

    def ler(self, url, **_):
        self.pedidos.append(url)
        return Resposta(url, self.paginas[int(url.rsplit("=", 1)[1]) - 1], {})

    def baixar(self, url, destino: Path):
        self.pedidos.append(url)
        destino.write_bytes(self.arquivo)
        return {"ETag": '"x"'}


def _obter(descobrir, servidor: Servidor, destino: Path) -> None:
    (alvo,) = descobrir(servidor, AGORA)
    assert alvo.obter is not None
    alvo.obter(servidor, destino)  # type: ignore[arg-type]


def _linhas(destino: Path) -> list[dict[str, str]]:
    with destino.open(encoding="utf-8", newline="") as texto:
        return list(csv.DictReader(texto, delimiter=";"))


@pytest.fixture(autouse=True)
def esperas(monkeypatch) -> list[float]:
    """As pausas pedidas pela coleta, sem esperar de verdade."""
    pedidas: list[float] = []
    monkeypatch.setattr(arquivista, "esperar", pedidas.append)
    return pedidas


# --- a coleta do cadastro (CSV) ---------------------------------------------------------------------------
CABECALHO_DA_ANP = (
    "CODIGOISIMP;AUTORIZACAO;DATAPUBLICACAO;RAZAOSOCIAL;CNPJ;ENDERECO;COMPLEMENTO;BAIRRO;CEP;UF;"
    "MUNICIPIO;BANDEIRA;DATAVINCULACAO"
)


def _linha_da_anp(cnpj: str) -> str:
    return (
        f"123456;PR/SC0001234;05/03/2019;{NOME_INVENTADO} {CPF_DE_TESTE};{cnpj};{RUA_INVENTADA};FUNDOS;"
        "BAIRRO INVENTADO;88330000;SC;ITAJAI;BANDEIRA A;04/04/2024"
    )


def test_o_cadastro_chega_ao_acervo_so_com_as_colunas_da_lista_e_so_de_cnpj(tmp_path):
    original = "\n".join(
        [CABECALHO_DA_ANP, _linha_da_anp(EMPRESA), _linha_da_anp(CPF_DE_TESTE)]
    ).encode("utf-8-sig")
    destino = tmp_path / "c.csv"

    _obter(arquivista.descobrir_cadastro, Servidor(arquivo=original), destino)

    (linha,) = _linhas(destino)
    assert linha == {
        "DATAPUBLICACAO": "05/03/2019",
        "CNPJ": EMPRESA,
        "UF": "SC",
        "MUNICIPIO": "ITAJAI",
        "BANDEIRA": "BANDEIRA A",
        "DATAVINCULACAO": "04/04/2024",
    }
    guardado = destino.read_text(encoding="utf-8")
    assert not [p for p in PROIBIDOS if p in guardado]


# --- a coleta do detalhe (API) ----------------------------------------------------------------------------
def _produto(nome: str, tancagem=30, bicos=4, unidade=M3) -> dict:
    return {
        "produto": nome,
        "tancagem": tancagem,
        "unidMedidaTancagem": unidade,
        "qtdeBicos": bicos,
    }


def _posto(cnpj: str, produtos=None) -> dict:
    return {
        "codigoSIMP": "123456",
        "autorizacao": "PR/SC0001234",
        "razaoSocial": f"{NOME_INVENTADO} {CPF_DE_TESTE}",
        "cnpj": cnpj,
        "endereco": RUA_INVENTADA,
        "complemento": "FUNDOS",
        "bairro": "BAIRRO INVENTADO",
        "cep": "88330000",
        "uf": "SC",
        "municipio": "ITAJAI",
        "produtos": [_produto("GASOLINA C COMUM")] if produtos is None else produtos,
        "latitude": "-26.9999999",
        "observacao": "OBSERVACAO LIVRE",
        "statusSIGAF": "",
    }


def _resposta(postos: list[dict], total: int, paginas: int, succeeded=True) -> bytes:
    return json.dumps(
        {
            "status": 200,
            "succeeded": succeeded,
            "data": postos,
            "searchPageFilter": {"totalRegistro": total, "totalPagina": paginas},
        },
        ensure_ascii=False,
    ).encode("utf-8")


def _duas_paginas() -> Servidor:
    gasolina_e_etanol = [
        _produto("GASOLINA C COMUM", 30, 4),
        _produto("ETANOL HIDRATADO COMUM", 15.5, 2),
    ]
    return Servidor(
        [
            _resposta([_posto(EMPRESA, gasolina_e_etanol)], total=2, paginas=2),
            _resposta([_posto(FILIAL, [])], total=2, paginas=2),
        ]
    )


def test_o_detalhe_le_as_paginas_uma_por_vez_com_pausa_e_grava_posto_e_produto(
    tmp_path, esperas
):
    servidor = _duas_paginas()
    destino = tmp_path / "r.csv"

    _obter(arquivista.descobrir_produtos, servidor, destino)

    assert servidor.pedidos == [
        arquivista.endereco_da_pagina(1),
        arquivista.endereco_da_pagina(2),
    ]
    assert esperas == [arquivista.PAUSA_ENTRE_PAGINAS_EM_SEGUNDOS]
    assert arquivista.PAUSA_ENTRE_PAGINAS_EM_SEGUNDOS >= 10
    linhas = _linhas(destino)
    assert tuple(linhas[0]) == arquivista.COLUNAS_DOS_PRODUTOS
    assert [(x["cnpj"], x["produto"], x["tancagem"], x["bicos"]) for x in linhas] == [
        (EMPRESA, "ETANOL HIDRATADO COMUM", "15.5", "2"),
        (EMPRESA, "GASOLINA C COMUM", "30", "4"),
        (FILIAL, "", "", ""),  # posto sem produto não some
    ]
    guardado = destino.read_text(encoding="utf-8")
    assert not [p for p in (*PROIBIDOS, "ITAJAI", "123456") if p in guardado]


def test_o_detalhe_nao_grava_documento_que_nao_e_cnpj(tmp_path):
    servidor = Servidor([_resposta([_posto(CPF_DE_TESTE), _posto(EMPRESA)], 2, 1)])
    destino = tmp_path / "r.csv"

    _obter(arquivista.descobrir_produtos, servidor, destino)

    assert {x["cnpj"] for x in _linhas(destino)} == {EMPRESA}


@pytest.mark.parametrize(
    ("paginas", "mensagem"),
    [
        ([_resposta([_posto(EMPRESA)], 1, 1, succeeded=False)], "recusou"),
        # veio menos do que a API diz ter: gravar faria o resto "sair" da tabela
        ([_resposta([_posto(EMPRESA)], 2, 1)], "1 de 2"),
        # a paginação repetiu um posto (a lista mudou no meio da leitura)
        ([_resposta([_posto(EMPRESA)], 2, 2)] * 2, "1 de 2"),
        ([_resposta([], 0, 0)], "nenhum"),
        ([b'{"succeeded": true}'], "formato"),
        # uma página de HTML (pedido de chave, de cadastro ou teste de robô) para a coleta
        ([b"<html>prove que voce e humano</html>"], "formato"),
    ],
)
def test_a_coleta_incompleta_ou_estranha_e_erro_e_nada_fica(
    tmp_path, paginas, mensagem
):
    destino = tmp_path / "r.csv"
    with pytest.raises(ValueError, match=mensagem):
        _obter(arquivista.descobrir_produtos, Servidor(paginas), destino)
    assert not destino.exists()


# --- as fontes, a licença e o que fica fechado ------------------------------------------------------------
def test_o_cadastro_e_cc_by_e_o_detalhe_fica_a_confirmar():
    ids = {revendedores.FONTE_DO_CADASTRO, revendedores.FONTE_DOS_PRODUTOS}
    assert ids <= set(POR_ID)
    (cadastro,) = arquivista.descobrir_cadastro(Servidor(), AGORA)  # type: ignore[arg-type]
    (produtos,) = arquivista.descobrir_produtos(Servidor(), AGORA)  # type: ignore[arg-type]
    assert licenca.familia_do_endereco(cadastro.url) == "anp"
    assert licenca.familia_do_endereco(produtos.url) == revendedores.FONTE_DOS_PRODUTOS
    assert marca_da_fonte(revendedores.FONTE_DO_CADASTRO) is Marca.VENDAVEL
    assert marca_da_fonte(revendedores.FONTE_DOS_PRODUTOS) is Marca.A_CONFIRMAR
    assert "26/11/2026" in licenca_da_fonte(revendedores.FONTE_DOS_PRODUTOS)


def test_as_duas_ficam_fechadas_e_so_o_cadastro_pode_aparecer_no_site():
    cadastro, produtos = revendedores.TABELA, revendedores.TABELA_DOS_PRODUTOS
    assert {cadastro, produtos} <= dossie.FECHADAS_ATE_A_PRONTIDAO
    assert produtos in vitrine.TABELAS_SO_INTERNAS
    assert cadastro not in vitrine.TABELAS_SO_INTERNAS

    # o detalhe não sai de fora nem quando houver prontidão: consulta aberta, CSV, lista e conector
    assert not dossie.pode_mostrar(produtos)
    assert not dossie.pode_consultar(produtos)
    assert not dossie.pode_consultar_aberto(produtos)
    assert dossie.pode_consultar(cadastro)
    nos_temas = {n for tema in vitrine.TEMAS_DO_CNPJ for n in tema.tabelas}
    assert cadastro in nos_temas
    assert produtos not in nos_temas


# --- os leitores ------------------------------------------------------------------------------------------
def _do_acervo(colunas: tuple[str, ...], base: dict[str, str], *linhas: dict) -> bytes:
    texto = [";".join(colunas)]
    texto += [";".join((base | linha)[c] for c in colunas) for linha in linhas]
    return ("\n".join(texto) + "\n").encode("utf-8")


def _cadastro(*linhas: dict[str, str]) -> bytes:
    base = {
        "CNPJ": EMPRESA,
        "UF": "SC",
        "MUNICIPIO": "ITAJAI",
        "BANDEIRA": "BANDEIRA A",
        "DATAPUBLICACAO": "05/03/2019",
        "DATAVINCULACAO": "04/04/2024",
    }
    return _do_acervo(arquivista.COLUNAS_DO_CADASTRO, base, *linhas)


def _produtos(*linhas: dict[str, str]) -> bytes:
    base = {
        "cnpj": EMPRESA,
        "produto": "GASOLINA C COMUM",
        "tancagem": "30",
        "unidade_da_tancagem": M3,
        "bicos": "4",
        "interdicao": "",
    }
    return _do_acervo(arquivista.COLUNAS_DOS_PRODUTOS, base, *linhas)


def test_o_leitor_do_cadastro_da_tipos_e_tira_cnpj_errado():
    tabela, contagem = revendedores.ler_cadastro(_cadastro({}, {"CNPJ": DV_ERRADO}))

    (linha,) = tabela.to_dict("records")
    assert linha["cnpj_basico"] == EMPRESA[:8]
    assert linha["bandeira"] == "BANDEIRA A"
    assert linha["data_da_autorizacao"] == pd.Timestamp("2019-03-05")
    assert linha["data_da_vinculacao"] == pd.Timestamp("2024-04-04")
    assert contagem["cnpj_invalido"] == 1


def test_o_leitor_dos_produtos_da_tipos_e_nao_converte_outra_unidade():
    tabela, contagem = revendedores.ler_produtos(
        _produtos(
            {"tancagem": "15.5"},
            {"produto": "DIESEL", "unidade_da_tancagem": "litros"},
        )
    )

    assert tabela["tancagem_m3"].iloc[0] == pytest.approx(15.5)
    assert tabela["bicos"].iloc[0] == 4
    assert contagem["unidade_desconhecida"] == 1
    assert pd.isna(tabela["tancagem_m3"].iloc[1])


def test_o_leitor_para_se_a_coluna_sumir():
    with pytest.raises(KeyError, match="bicos"):
        revendedores.ler_produtos(b"cnpj;produto\n")
    with pytest.raises(KeyError, match="BANDEIRA"):
        revendedores.ler_cadastro(b"CNPJ;UF\n")


# --- a montagem -------------------------------------------------------------------------------------------
@pytest.fixture
def acervo_do_teste(tmp_path, monkeypatch):
    monkeypatch.setenv("TICKERLAB_ACERVO", str(tmp_path / "acervo"))


def _coletar(banco, fonte: str, url: str, conteudo: bytes, dia: date) -> None:
    com_registro(fonte, lambda _url: conteudo)(url)
    with banco.begin() as conexao:
        conexao.execute(
            sa.update(coletas.coletas)
            .where(coletas.coletas.c.sha256 == hashlib.sha256(conteudo).hexdigest())
            .values(baixado_em=datetime(dia.year, dia.month, dia.day, 3, tzinfo=UTC))
        )


def _coletar_cadastro(banco, dia: date, *linhas: dict[str, str]) -> None:
    fonte = revendedores.FONTE_DO_CADASTRO
    _coletar(banco, fonte, arquivista.CSV_DO_CADASTRO, _cadastro(*linhas), dia)


def _montada(banco, pasta: Path, tabela: str, nome: str) -> pd.DataFrame:
    with banco.connect() as conexao:
        revendedores.montar(conexao, pasta, AGORA, pessoas={MEI[:8]})
    return pd.read_parquet(pasta / tabela / f"{nome}.parquet")


def _montado_o_cadastro(banco, pasta: Path) -> pd.DataFrame:
    return _montada(banco, pasta, revendedores.TABELA, "cadastro")


@pytest.mark.usefixtures("acervo_do_teste")
def test_a_troca_de_bandeira_vira_linha_nova_so_a_partir_do_dia_em_que_foi_vista(
    banco, tmp_path
):
    _coletar_cadastro(banco, DIA, {}, {"CNPJ": MEI})
    antes = _montado_o_cadastro(banco, tmp_path / "antes")
    _coletar_cadastro(banco, DIA_SEGUINTE, {"BANDEIRA": "BANDEIRA B"}, {"CNPJ": MEI})
    depois = _montado_o_cadastro(banco, tmp_path / "depois")

    assert list(depois.columns) == [
        *revendedores.COLUNAS,
        *montagem.CARIMBOS_DA_LINHA,
        *LINHAGEM,
    ]
    assert dict(
        zip(depois["cnpj_basico"], depois["trata_como_pessoa"], strict=True)
    ) == {EMPRESA[:8]: False, MEI[:8]: True}
    da_empresa = depois[depois["cnpj_basico"] == EMPRESA[:8]]
    assert list(
        zip(da_empresa["bandeira"], da_empresa["disponivel_em"], strict=True)
    ) == [("BANDEIRA A", DIA), ("BANDEIRA B", DIA_SEGUINTE)]
    # sem olhar o futuro: o retrato novo não muda o que já se sabia no primeiro dia
    ate_o_dia = depois[depois["disponivel_em"] <= DIA].drop(columns=list(LINHAGEM))
    pd.testing.assert_frame_equal(
        ate_o_dia.reset_index(drop=True),
        antes.drop(columns=list(LINHAGEM)).reset_index(drop=True),
    )


@pytest.mark.usefixtures("acervo_do_teste")
def test_o_posto_que_sai_da_lista_fica_marcado(banco, tmp_path):
    _coletar_cadastro(banco, DIA, {}, {"CNPJ": FILIAL}, {"CNPJ": MEI})
    _coletar_cadastro(banco, DIA_SEGUINTE, {}, {"CNPJ": MEI})

    tabela = _montado_o_cadastro(banco, tmp_path / "base")

    da_filial = tabela[tabela["cnpj"].str.contains("/0002-")]
    assert list(da_filial["consta"]) == [True, False]


@pytest.mark.usefixtures("acervo_do_teste")
def test_os_produtos_montam_na_tabela_deles(banco, tmp_path):
    fonte = revendedores.FONTE_DOS_PRODUTOS
    conteudo = _produtos({}, {"cnpj": MEI})
    _coletar(banco, fonte, arquivista.ENDERECO_DA_API, conteudo, DIA)
    pasta = tmp_path / "base"

    tabela = _montada(banco, pasta, revendedores.TABELA_DOS_PRODUTOS, "produtos")

    assert list(tabela.columns) == [
        *revendedores.COLUNAS_DOS_PRODUTOS,
        *montagem.CARIMBOS_DA_LINHA,
        *LINHAGEM,
    ]
    assert set(tabela["disponivel_em"]) == {DIA}
    assert int(tabela["trata_como_pessoa"].sum()) == 1
