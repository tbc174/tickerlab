"""Revendedores varejistas de combustíveis da ANP (base/arquivo/anp_revendedores.py e base/anp_revendedores.py,
linha 1123): a coleta pagina a API da própria ANP e grava só as colunas da lista (sem razão social, endereço nem
coordenada), a tabela sai uma linha por posto e produto, o MEI é marcado e nada usa o dado antes do dia em que o
vimos. Respostas inventadas no formato conferido em 26/11/2026; nenhum documento nem nome real."""

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
from base import licenca
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


def _cnpj(raiz: str, filial: str = "0001") -> str:
    for dv in range(100):
        if cnpjs.dv_confere(bruto := f"{raiz}{filial}{dv:02d}"):
            return bruto
    raise AssertionError(raiz)


EMPRESA = _cnpj("11222333")
FILIAL = _cnpj("11222333", "0002")
MEI = _cnpj("44555666")


def _produto(nome: str, tancagem=30, bicos=4, unidade=M3) -> dict:
    return {
        "produto": nome,
        "tancagem": tancagem,
        "unidMedidaTancagem": unidade,
        "qtdeBicos": bicos,
    }


def _posto(cnpj: str, bandeira: str = "BANDEIRA A", produtos=None) -> dict:
    return {
        "codigoSIMP": "123456",
        "autorizacao": "PR/SC0001234",
        "dataPublicacao": "05/03/2019",
        "razaoSocial": f"{NOME_INVENTADO} {CPF_DE_TESTE}",
        "cnpj": cnpj,
        "endereco": RUA_INVENTADA,
        "complemento": "FUNDOS",
        "bairro": "BAIRRO INVENTADO",
        "cep": "88330000",
        "uf": "SC",
        "municipio": "BALNEARIO CAMBORIU",
        "distribuidora": bandeira,
        "dataVinculacao": "04/04/2024",
        "classe": "",
        "produtos": [_produto("GASOLINA C COMUM")] if produtos is None else produtos,
        "latitude": "-26.9999999",
        "longitude": "-48.9999999",
        "observacao": "OBSERVACAO LIVRE",
        "statusSIGAF": "",
    }


def _resposta(
    postos: list[dict], total: int, pagina: int, paginas: int, succeeded: bool = True
) -> bytes:
    return json.dumps(
        {
            "status": 200,
            "succeeded": succeeded,
            "data": postos,
            "searchPageFilter": {
                "numeroPagina": pagina,
                "tamanhoPagina": 5000,
                "totalRegistro": total,
                "totalPagina": paginas,
            },
        },
        ensure_ascii=False,
    ).encode("utf-8")


class Servidor:
    """Responde `ler` com a página pedida, em memória, e guarda o que foi pedido."""

    def __init__(self, paginas: list[bytes]):
        self.paginas = paginas
        self.pedidos: list[str] = []

    def ler(self, url, *, metodo="GET", cabecalhos=None, corpo=None):
        self.pedidos.append(url)
        numero = int(url.rsplit("=", 1)[1])
        return Resposta(url, self.paginas[numero - 1], {})


def _obter(servidor: Servidor, destino: Path) -> None:
    (alvo,) = arquivista.descobrir(servidor, AGORA)  # type: ignore[arg-type]
    assert alvo.obter is not None
    alvo.obter(servidor, destino)  # type: ignore[arg-type]


def _linhas(destino: Path) -> list[dict[str, str]]:
    with destino.open(encoding="utf-8", newline="") as texto:
        return list(csv.DictReader(texto, delimiter=";"))


def _duas_paginas() -> Servidor:
    return Servidor(
        [
            _resposta(
                [
                    _posto(
                        EMPRESA,
                        produtos=[
                            _produto("GASOLINA C COMUM", 30, 4),
                            _produto("ETANOL HIDRATADO COMUM", 15.5, 2),
                        ],
                    )
                ],
                total=2,
                pagina=1,
                paginas=2,
            ),
            _resposta([_posto(FILIAL, produtos=[])], total=2, pagina=2, paginas=2),
        ]
    )


# --- a coleta ---------------------------------------------------------------------------------------------
def test_a_coleta_le_todas_as_paginas_e_grava_uma_linha_por_posto_e_produto(tmp_path):
    servidor = _duas_paginas()
    destino = tmp_path / "r.csv"
    _obter(servidor, destino)
    assert servidor.pedidos == [
        arquivista.endereco_da_pagina(1),
        arquivista.endereco_da_pagina(2),
    ]
    linhas = _linhas(destino)
    assert [(x["cnpj"], x["produto"], x["tancagem"], x["bicos"]) for x in linhas] == [
        (EMPRESA, "ETANOL HIDRATADO COMUM", "15.5", "2"),
        (EMPRESA, "GASOLINA C COMUM", "30", "4"),
        (FILIAL, "", "", ""),  # posto sem produto não some
    ]


def test_a_coleta_nao_guarda_razao_social_endereco_nem_coordenada(tmp_path):
    destino = tmp_path / "r.csv"
    _obter(_duas_paginas(), destino)
    guardado = destino.read_text(encoding="utf-8")
    for proibido in (
        NOME_INVENTADO,
        CPF_DE_TESTE,
        RUA_INVENTADA,
        "FUNDOS",
        "BAIRRO INVENTADO",
        "88330000",
        "-26.9999999",
        "OBSERVACAO LIVRE",
    ):
        assert proibido not in guardado, proibido
    assert tuple(_linhas(destino)[0]) == arquivista.COLUNAS


def test_a_coleta_nao_grava_documento_que_nao_e_cnpj(tmp_path):
    servidor = Servidor([_resposta([_posto(CPF_DE_TESTE), _posto(EMPRESA)], 2, 1, 1)])
    destino = tmp_path / "r.csv"
    _obter(servidor, destino)
    assert {x["cnpj"] for x in _linhas(destino)} == {EMPRESA}
    assert CPF_DE_TESTE not in destino.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("paginas", "mensagem"),
    [
        ([_resposta([_posto(EMPRESA)], 1, 1, 1, succeeded=False)], "recusou"),
        # veio menos do que a API diz ter: gravar faria o resto "sair" da tabela
        ([_resposta([_posto(EMPRESA)], 2, 1, 1)], "1 de 2"),
        # a paginação repetiu um posto (a lista mudou no meio da leitura)
        (
            [
                _resposta([_posto(EMPRESA)], 2, 1, 2),
                _resposta([_posto(EMPRESA)], 2, 2, 2),
            ],
            "1 de 2",
        ),
        ([_resposta([], 0, 1, 0)], "nenhum"),
        ([b'{"succeeded": true}'], "formato"),
    ],
)
def test_a_coleta_incompleta_ou_estranha_e_erro_e_nada_fica(
    tmp_path, paginas, mensagem
):
    destino = tmp_path / "r.csv"
    with pytest.raises(ValueError, match=mensagem):
        _obter(Servidor(paginas), destino)
    assert not destino.exists()


# --- a fonte e a licença ----------------------------------------------------------------------------------
def test_a_fonte_esta_no_arquivista_e_a_licenca_fica_a_confirmar():
    assert revendedores.FONTE in POR_ID
    (alvo,) = arquivista.descobrir(Servidor([]), AGORA)  # type: ignore[arg-type]
    assert alvo.url == arquivista.ENDERECO
    assert licenca.familia_do_endereco(alvo.url) == revendedores.FONTE
    assert "26/11/2026" in licenca_da_fonte(revendedores.FONTE)
    assert marca_da_fonte(revendedores.FONTE) is Marca.A_CONFIRMAR


# --- o leitor ---------------------------------------------------------------------------------------------
def _csv_do_acervo(*linhas: dict[str, str]) -> bytes:
    base = {
        "cnpj": EMPRESA,
        "codigo_simp": "123456",
        "autorizacao": "PR/SC0001234",
        "data_da_autorizacao": "05/03/2019",
        "uf": "SC",
        "municipio": "ITAJAI",
        "bandeira": "BANDEIRA A",
        "data_da_vinculacao": "04/04/2024",
        "produto": "GASOLINA C COMUM",
        "tancagem": "30",
        "unidade_da_tancagem": M3,
        "bicos": "4",
    }
    texto = [";".join(arquivista.COLUNAS)]
    texto += [
        ";".join((base | linha)[c] for c in arquivista.COLUNAS) for linha in linhas
    ]
    return ("\n".join(texto) + "\n").encode("utf-8")


def test_o_leitor_da_tipos_e_nao_leva_coluna_de_nome():
    tabela, contagem = revendedores.ler(_csv_do_acervo({"tancagem": "15.5"}))
    linha = tabela.iloc[0]
    assert linha["cnpj_basico"] == EMPRESA[:8]
    assert linha["tancagem_m3"] == pytest.approx(15.5)
    assert linha["bicos"] == 4
    assert linha["data_da_autorizacao"] == pd.Timestamp("2019-03-05")
    assert linha["data_da_vinculacao"] == pd.Timestamp("2024-04-04")
    assert contagem["linhas"] == 1
    assert not [c for c in tabela.columns if "razao" in c or "endereco" in c]


def test_o_leitor_tira_cnpj_errado_e_nao_converte_outra_unidade():
    errado = EMPRESA[:-1] + str((int(EMPRESA[-1]) + 1) % 10)
    tabela, contagem = revendedores.ler(
        _csv_do_acervo(
            {"cnpj": errado},
            {"unidade_da_tancagem": "litros", "tancagem": "30000"},
        )
    )
    assert contagem["cnpj_invalido"] == 1
    assert contagem["unidade_desconhecida"] == 1
    assert len(tabela) == 1
    assert pd.isna(tabela["tancagem_m3"].iloc[0])


def test_o_leitor_para_se_a_coluna_sumir():
    with pytest.raises(KeyError, match="bicos"):
        revendedores.ler(b"cnpj;produto\n")


# --- a montagem -------------------------------------------------------------------------------------------
@pytest.fixture
def acervo_do_teste(tmp_path, monkeypatch):
    monkeypatch.setenv("TICKERLAB_ACERVO", str(tmp_path / "acervo"))


def _coletar(banco, conteudo: bytes, dia: date) -> None:
    com_registro(revendedores.FONTE, lambda _url: conteudo)(arquivista.ENDERECO)
    with banco.begin() as conexao:
        conexao.execute(
            sa.update(coletas.coletas)
            .where(coletas.coletas.c.sha256 == hashlib.sha256(conteudo).hexdigest())
            .values(baixado_em=datetime(dia.year, dia.month, dia.day, 3, tzinfo=UTC))
        )


def _montada(banco, pasta: Path) -> pd.DataFrame:
    with banco.connect() as conexao:
        revendedores.montar(conexao, pasta, AGORA, pessoas={MEI[:8]})
    return pd.read_parquet(pasta / revendedores.TABELA / f"{revendedores.NOME}.parquet")


def test_a_troca_de_bandeira_vira_linha_nova_so_a_partir_do_dia_em_que_foi_vista(
    banco, tmp_path, acervo_do_teste
):
    _coletar(banco, _csv_do_acervo({}, {"cnpj": MEI}), DIA)
    antes = _montada(banco, tmp_path / "antes")
    _coletar(
        banco, _csv_do_acervo({"bandeira": "BANDEIRA B"}, {"cnpj": MEI}), DIA_SEGUINTE
    )
    depois = _montada(banco, tmp_path / "depois")

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
    ) == [
        ("BANDEIRA A", DIA),
        ("BANDEIRA B", DIA_SEGUINTE),
    ]
    # sem olhar o futuro: o retrato novo não muda o que já se sabia no primeiro dia
    ate_o_dia = depois[depois["disponivel_em"] <= DIA].drop(columns=list(LINHAGEM))
    pd.testing.assert_frame_equal(
        ate_o_dia.reset_index(drop=True),
        antes.drop(columns=list(LINHAGEM)).reset_index(drop=True),
    )


def test_o_posto_que_sai_da_lista_fica_marcado(banco, tmp_path, acervo_do_teste):
    _coletar(banco, _csv_do_acervo({}, {"cnpj": FILIAL}, {"cnpj": MEI}), DIA)
    _coletar(banco, _csv_do_acervo({}, {"cnpj": MEI}), DIA_SEGUINTE)
    tabela = _montada(banco, tmp_path / "base")
    da_filial = tabela[tabela["cnpj"].str.contains("/0002-")]
    assert list(da_filial["consta"]) == [True, False]
