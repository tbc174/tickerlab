"""Lote Brasil, segunda camada, do arquivista (base/arquivo/lote_brasil2.py): descoberta e filtro de pessoa física."""

import io
import json
import zipfile
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
import requests

from base.arquivo import lote_brasil2, registro
from base.arquivo.coleta import ErroDeDescoberta, Resposta
from base.arquivo.fontes import FONTES, POR_ID
from base.arquivo.lote_brasil2 import RegraDoMembro
from base.licenca import familia_do_endereco
from src.banco.coletas import Marca, licenca_da_fonte, marca_da_fonte

AGORA = datetime(2026, 10, 22, 14, tzinfo=UTC)
FONTES_DO_LOTE = {f.id: f for f in lote_brasil2.fontes()}
RAIZ = lote_brasil2.RAIZ_DA_CGU


def _erro(status: int) -> requests.HTTPError:
    resposta = requests.Response()
    resposta.status_code = status
    return requests.HTTPError(response=resposta)


class Servidor:
    """Dublê do `Cliente`: páginas, cabeçalhos e arquivos fixos; um valor `int` vira erro HTTP."""

    def __init__(self, existem: dict[str, bytes | int] | None = None):
        self.existem = existem or {}
        self.pedidos: list[str] = []

    def _achar(self, url: str) -> bytes:
        self.pedidos.append(url)
        valor = self.existem.get(url, 403)
        if isinstance(valor, int):
            raise _erro(valor)
        return valor

    def ler(self, url, *, metodo="GET", cabecalhos=None, corpo=None):
        return Resposta(url, self._achar(url), {})

    def cabecalhos(self, url):
        self._achar(url)
        return {"ETag": "x"}

    def baixar(self, url, destino: Path):
        destino.write_bytes(self._achar(url))
        return {"ETag": "x"}


def _pacote(*recursos: tuple[str, str]) -> bytes:
    return json.dumps(
        {"result": {"resources": [{"format": f, "url": u} for f, u in recursos]}}
    ).encode()


def _csv(*linhas: list[str]) -> bytes:
    """CSV da CGU: cp1252, ";" e tudo entre aspas."""
    texto = "".join(";".join(f'"{c}"' for c in linha) + "\r\n" for linha in linhas)
    return texto.encode("cp1252")


def _zip(**membros: bytes) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as arquivo:
        for nome, dados in membros.items():
            arquivo.writestr(nome, dados)
    return buffer.getvalue()


def _ler_zip(caminho: Path) -> dict[str, str]:
    with zipfile.ZipFile(caminho) as arquivo:
        return {n: arquivo.read(n).decode("cp1252") for n in arquivo.namelist()}


# ---------------------------------------------------------------- catálogo
def test_ids_do_lote_sao_unicos_e_estao_no_catalogo_geral():
    ids = [f.id for f in lote_brasil2.fontes()]
    assert len(ids) == len(set(ids))
    assert set(ids) <= set(POR_ID)
    assert len([f for f in FONTES if f.id in ids]) == len(ids)


def test_o_lote_nao_repete_fonte_que_ja_existia():
    antigos = {f.id for f in FONTES if f.id not in FONTES_DO_LOTE}
    assert not set(FONTES_DO_LOTE) & antigos
    # CEIS, CNEP, CEPIM e leniência já são `cgu-*`; o lote não as refaz
    assert not any(i.startswith("cgu") for i in FONTES_DO_LOTE)


def test_todas_as_familias_pedidas_estao_no_lote():
    assert {i.split("-", 1)[0] for i in FONTES_DO_LOTE} == {
        "transparencia",
        "bndes",
        "inss",
        "susep",
    }


def test_nao_ha_fonte_de_cartao_de_pagamento_nem_de_pessoa():
    # o cartão de pagamento do governo (CPGF) só tem portador pessoa física (ADR 0088)
    assert not any("cpgf" in i or "cartao" in i for i in FONTES_DO_LOTE)


@pytest.mark.parametrize("fonte", sorted(FONTES_DO_LOTE))
def test_toda_fonte_do_lote_tem_licenca_marca_e_data_dos_termos(fonte):
    assert not licenca_da_fonte(fonte).startswith("Desconhecida")
    familia = fonte.split("-", 1)[0]
    assert registro.TERMOS_LIDOS_EM[familia] >= date(2026, 10, 15)
    assert marca_da_fonte(fonte) == Marca.VENDAVEL


def test_as_licencas_do_bndes_e_da_transparencia_dizem_que_so_ha_cnpj():
    assert "ODbL" in licenca_da_fonte("bndes-operacoes")
    assert "Só CNPJ" in licenca_da_fonte("transparencia-compras")
    # a família nova não herda o "só uso interno" do `cgu-*` (CEIS, CNEP...)
    assert marca_da_fonte("cgu-ceis") != marca_da_fonte("transparencia-compras")


@pytest.mark.parametrize(
    ("url", "familia"),
    [
        (f"{RAIZ}/compras/202609_Compras.zip", "transparencia"),
        ("https://dadosabertos.bndes.gov.br/dataset/x/a.csv", "bndes"),
        ("https://dadosabertos.inss.gov.br/dataset/x/a.csv", "inss"),
        (
            "https://www2.susep.gov.br/download/estatisticas/BaseCompleta.zip#a.csv",
            "susep",
        ),
    ],
)
def test_o_endereco_do_original_aponta_a_familia_da_licenca(url, familia):
    assert familia_do_endereco(url) == familia


def test_fontes_pesadas_conferem_a_assinatura_antes_de_baixar():
    pesadas = {i for i, f in FONTES_DO_LOTE.items() if f.pesada}
    assert {
        "transparencia-compras",
        "bndes-operacoes",
        "bndes-operacoes-indiretas",
        "inss-requerimentos-pendentes",
        "susep-ses-complementos",
    } <= pesadas


# ---------------------------------------------------------------- documento
@pytest.mark.parametrize(
    "valor",
    [
        "43588755000161",
        "43.588.755/0001-61",
        "**.588.755/0001-**",  # CNPJ mascarado
        "43588755000161 - NOME DA EMPRESA LTDA",  # BNDES
        "  43588755000161  ",
    ],
)
def test_e_cnpj_aceita_cnpj_com_ou_sem_pontuacao_ou_mascara(valor):
    assert lote_brasil2.e_cnpj(valor)


@pytest.mark.parametrize(
    "valor",
    [
        "",
        "12345678901",  # CPF
        "123.456.789-01",
        "***.456.789-**",  # CPF mascarado
        "EX0001",  # código de estrangeiro
        "Sigiloso",
        "12345678901 - FULANO DE TAL",
        "4358875500016",  # 13 dígitos
        "435887550001611",  # 15 dígitos
    ],
)
def test_e_cnpj_recusa_cpf_codigo_estrangeiro_sigilo_e_vazio(valor):
    assert not lote_brasil2.e_cnpj(valor)


# ------------------------------------------------------------- filtrar_csv
def _filtrar(dados: bytes, regra: RegraDoMembro) -> tuple[str, int]:
    saida = io.BytesIO()
    quantas = lote_brasil2.filtrar_csv(io.BytesIO(dados), saida, regra)
    return saida.getvalue().decode("cp1252"), quantas


def test_filtrar_csv_guarda_so_linhas_de_cnpj_e_tira_as_colunas_de_pessoa():
    dados = _csv(
        ["CÓDIGO FAVORECIDO", "NOME FAVORECIDO", "AUTOR", "VALOR"],
        ["43588755000161", "Empresa Ltda", "Deputado A", "10,00"],
        ["12345678901", "Fulano de Tal", "Deputado B", "20,00"],
        ["***.456.789-**", "Beltrano", "Deputado C", "30,00"],
        ["**.588.755/0001-**", "Outra SA", "Deputado D", "40,00"],
        ["", "Sem documento", "Deputado E", "50,00"],
    )
    texto, quantas = _filtrar(
        dados, RegraDoMembro(colunas_fora=("autor",), documento=("Código Favorecido",))
    )
    assert quantas == 2
    assert texto.splitlines() == [
        '"CÓDIGO FAVORECIDO";"NOME FAVORECIDO";"VALOR"',
        '"43588755000161";"Empresa Ltda";"10,00"',
        '"**.588.755/0001-**";"Outra SA";"40,00"',
    ]
    for pessoa in ("Fulano", "Beltrano", "Deputado"):
        assert pessoa not in texto


def test_filtrar_csv_tira_a_linha_de_cnpj_cujo_nome_traz_o_cpf_do_dono():
    # o nome do MEI no portal é "NOME 02903737789": é CNPJ, mas expõe o CPF (ADR 0088)
    dados = _csv(
        ["CNPJ", "FAVORECIDO", "VALOR", "PROCESSO"],
        ["43588755000161", "ANNA PINTO 02903737789", "1,00", "1"],
        ["43588755000161", "ANNA PINTO 029.037.377-89", "2,00", "2"],
        ["43588755000161", "ANNA PINTO ***.037.377-**", "3,00", "3"],
        ["43588755000161", "Empresa Ltda", "34762323258,00", "12345.123456/2020-12"],
        ["43588755000161", "Outra SA", "7", "123456"],
    )
    texto, quantas = _filtrar(dados, RegraDoMembro(documento=("cnpj",)))
    assert quantas == 2
    assert "ANNA" not in texto and "34762323258,00" in texto


def test_filtrar_csv_sem_coluna_de_documento_so_tira_as_colunas_de_pessoa():
    dados = _csv(["A", "GESTOR", "B"], ["1", "Fulano", "2"], ["3", "Beltrano", "4"])
    texto, quantas = _filtrar(dados, RegraDoMembro(colunas_fora=("gestor",)))
    assert quantas == 2
    assert "Fulano" not in texto and '"3";"4"' in texto


def test_filtrar_csv_da_ida_e_volta_sem_perder_acento():
    dados = _csv(["CNPJ", "NOME"], ["43588755000161", "AÇÚCAR É BOM Ltda"])
    texto, _ = _filtrar(dados, RegraDoMembro(documento=("cnpj",)))
    assert "AÇÚCAR É BOM Ltda" in texto


def test_filtrar_csv_descarta_linha_com_numero_de_colunas_errado():
    dados = _csv(["CNPJ", "NOME"], ["43588755000161"], ["43588755000161", "A", "B"])
    texto, quantas = _filtrar(dados, RegraDoMembro(documento=("cnpj",)))
    assert quantas == 0
    assert texto.splitlines() == ['"CNPJ";"NOME"']


def test_filtrar_csv_tira_o_bom_do_cabecalho():
    dados = b"\xef\xbb\xbf" + _csv(["CNPJ", "NOME"], ["43588755000161", "A"])
    texto, quantas = _filtrar(dados, RegraDoMembro(documento=("cnpj",)))
    assert quantas == 1
    assert texto.startswith('"CNPJ"')


def test_filtrar_csv_falha_se_a_coluna_do_documento_sumiu():
    dados = _csv(["OUTRA", "NOME"], ["43588755000161", "A"])
    with pytest.raises(ValueError, match="coluna do documento"):
        _filtrar(dados, RegraDoMembro(documento=("cnpj",)))


def test_filtrar_csv_falha_se_a_coluna_do_documento_aparece_duas_vezes():
    dados = _csv(["CNPJ", "cnpj"], ["43588755000161", "43588755000161"])
    with pytest.raises(ValueError, match="2 vezes"):
        _filtrar(dados, RegraDoMembro(documento=("cnpj",)))


def test_filtrar_csv_vazio_falha():
    with pytest.raises(ValueError, match="vazio"):
        _filtrar(b"", RegraDoMembro())


def test_campo_longo_nao_estoura_o_limite_do_csv():
    longo = "x" * 200_000
    dados = _csv(["CNPJ", "OBJETO"], ["43588755000161", longo])
    texto, quantas = _filtrar(dados, RegraDoMembro(documento=("cnpj",)))
    assert quantas == 1 and longo in texto


# --------------------------------------------------------------- csv_so_cnpj
def test_csv_so_cnpj_grava_filtrado_e_apaga_o_bruto(tmp_path):
    url = "https://dadosabertos.bndes.gov.br/x/operacoes.csv"
    servidor = Servidor(
        {
            url: _csv(
                ["cnpj", "nome_do_gestor", "valor"],
                ["43588755000161", "Empregado", "1"],
                ["12345678901", "Empregado", "2"],
            )
        }
    )
    destino = tmp_path / "saida.csv"
    cabecalhos = lote_brasil2.csv_so_cnpj(url, ("cnpj",), ("nome_do_gestor",))(
        servidor, destino
    )
    assert cabecalhos == {"ETag": "x"}
    assert destino.read_bytes().decode("cp1252").splitlines() == [
        '"cnpj";"valor"',
        '"43588755000161";"1"',
    ]
    assert [p.name for p in tmp_path.iterdir()] == ["saida.csv"]


def test_csv_so_cnpj_nao_deixa_o_bruto_se_o_filtro_falha(tmp_path):
    url = "https://dadosabertos.bndes.gov.br/x/operacoes.csv"
    servidor = Servidor({url: _csv(["outra"], ["1"])})
    with pytest.raises(ValueError):
        lote_brasil2.csv_so_cnpj(url, ("cnpj",))(servidor, tmp_path / "saida.csv")
    assert [p.name for p in tmp_path.iterdir() if p.name.endswith(".bruto")] == []


# --------------------------------------------------------------- zip_so_cnpj
REGRAS = (
    (r"^\d{6}_Compras\.csv$", RegraDoMembro(documento=("Código Contratado",))),
    (r"^\d{6}_ItemCompra\.csv$", RegraDoMembro()),
)


def _zip_de_compras() -> bytes:
    return _zip(
        **{
            "202609_ItemCompra.csv": _csv(["ITEM", "VALOR"], ["a", "1"]),
            "202609_Compras.csv": _csv(
                ["Código Contratado", "Nome"],
                ["43588755000161", "Empresa"],
                ["12345678901", "Pessoa"],
            ),
        }
    )


def test_zip_so_cnpj_regrava_cada_arquivo_pela_regra_dele(tmp_path):
    url = f"{RAIZ}/compras/202609_Compras.zip"
    destino = tmp_path / "saida.zip"
    lote_brasil2.zip_so_cnpj(url, REGRAS)(Servidor({url: _zip_de_compras()}), destino)
    lido = _ler_zip(destino)
    assert sorted(lido) == ["202609_Compras.csv", "202609_ItemCompra.csv"]
    assert "Pessoa" not in lido["202609_Compras.csv"]
    assert "43588755000161" in lido["202609_Compras.csv"]
    assert '"a";"1"' in lido["202609_ItemCompra.csv"]
    assert [p.name for p in tmp_path.iterdir()] == ["saida.zip"]


def test_zip_regravado_e_determinístico(tmp_path):
    url = f"{RAIZ}/compras/202609_Compras.zip"
    origem = Servidor({url: _zip_de_compras()})
    for nome in ("a.zip", "b.zip"):
        lote_brasil2.zip_so_cnpj(url, REGRAS)(origem, tmp_path / nome)
    assert (tmp_path / "a.zip").read_bytes() == (tmp_path / "b.zip").read_bytes()


def test_arquivo_novo_no_zip_sem_regra_faz_a_coleta_falhar(tmp_path):
    url = f"{RAIZ}/compras/202609_Compras.zip"
    zip_novo = _zip(
        **{
            "202609_Compras.csv": _csv(["Código Contratado"], ["1"]),
            "NovoArquivo.csv": b'"A"\r\n',
        }
    )
    with pytest.raises(ValueError, match="sem regra"):
        lote_brasil2.zip_so_cnpj(url, REGRAS)(
            Servidor({url: zip_novo}), tmp_path / "s.zip"
        )
    assert [p.name for p in tmp_path.iterdir()] == []


def test_as_regras_do_portal_cobrem_os_nomes_reais_dos_arquivos():
    casos = {
        lote_brasil2.TRANSFERENCIAS: ["202609_Transferencias.csv"],
        lote_brasil2.COMPRAS: [
            "202609_Compras.csv",
            "202609_ItemCompra.csv",
            "202609_TermoAditivo.csv",
            "202609_Apostilamento.csv",
        ],
        lote_brasil2.DESPESAS: ["202609_Despesas.csv"],
        lote_brasil2.ORCAMENTO: ["2026_OrcamentoDespesa.csv"],
        lote_brasil2.EMENDAS: [
            "EmendasParlamentares.csv",
            "EmendasParlamentares_Convenios.csv",
            "EmendasParlamentares_PorFavorecido.csv",
        ],
    }
    for regras, nomes in casos.items():
        for nome in nomes:
            lote_brasil2._regra_do_membro(nome, regras)


def test_licitacao_com_acento_ou_sem_acento_no_nome_tem_regra():
    for nome in (
        "202404_Licitação.csv",
        "202404_Licitacao.csv",
        "202404_ItemLicitação.csv",
    ):
        lote_brasil2._regra_do_membro(nome, lote_brasil2.LICITACOES)


def test_emendas_tiram_o_autor_parlamentar():
    regra = lote_brasil2._regra_do_membro(
        "EmendasParlamentares.csv", lote_brasil2.EMENDAS
    )
    assert "Nome do Autor da Emenda" in regra.colunas_fora
    por_favorecido = lote_brasil2._regra_do_membro(
        "EmendasParlamentares_PorFavorecido.csv", lote_brasil2.EMENDAS
    )
    assert por_favorecido.documento == ("Código do Favorecido",)


# ------------------------------------------------- descoberta no S3 da CGU
def test_a_cgu_responde_403_ao_que_nao_existe_e_a_descoberta_anda_para_tras():
    existem = {
        f"{RAIZ}/compras/202609_Compras.zip": b"x",
        f"{RAIZ}/compras/202608_Compras.zip": b"x",
        f"{RAIZ}/compras/202607_Compras.zip": b"x",
    }
    servidor = Servidor(existem)  # 202610 e o resto: 403
    alvos = lote_brasil2.descobrir_zips_da_cgu(
        "compras", "{periodo}_Compras.zip", REGRAS
    )(servidor, AGORA)
    assert [a.url for a in alvos] == [
        f"{RAIZ}/compras/202609_Compras.zip",
        f"{RAIZ}/compras/202608_Compras.zip",
    ]
    assert all(a.extensao == ".zip" and a.obter for a in alvos)
    assert f"{RAIZ}/compras/202607_Compras.zip" not in servidor.pedidos


def test_a_descoberta_atravessa_a_virada_do_ano():
    agora = datetime(2027, 1, 5, tzinfo=UTC)
    servidor = Servidor(
        {
            f"{RAIZ}/compras/202701_Compras.zip": 404,
            f"{RAIZ}/compras/202612_Compras.zip": b"x",
            f"{RAIZ}/compras/202611_Compras.zip": b"x",
        }
    )
    alvos = lote_brasil2.descobrir_zips_da_cgu(
        "compras", "{periodo}_Compras.zip", REGRAS
    )(servidor, agora)
    assert [a.url[-18:] for a in alvos] == ["202612_Compras.zip", "202611_Compras.zip"]


def test_licitacoes_paradas_desde_2024_ainda_sao_achadas():
    servidor = Servidor({f"{RAIZ}/licitacoes/202404_Licitacoes.zip": b"x"})
    alvos = lote_brasil2.descobrir_zips_da_cgu(
        "licitacoes", "{periodo}_Licitacoes.zip", REGRAS, quantos=1
    )(servidor, AGORA)
    assert [a.url for a in alvos] == [f"{RAIZ}/licitacoes/202404_Licitacoes.zip"]


def test_sem_nenhum_periodo_a_descoberta_falha_com_erro_de_descoberta():
    with pytest.raises(ErroDeDescoberta, match="compras"):
        lote_brasil2.descobrir_zips_da_cgu("compras", "{periodo}_Compras.zip", REGRAS)(
            Servidor(), AGORA
        )


def test_erro_que_nao_e_arquivo_inexistente_nao_e_engolido():
    servidor = Servidor({f"{RAIZ}/compras/202610_Compras.zip": 500})
    with pytest.raises(requests.HTTPError):
        lote_brasil2.descobrir_zips_da_cgu("compras", "{periodo}_Compras.zip", REGRAS)(
            servidor, AGORA
        )


def test_orcamento_e_anual_e_pega_os_dois_anos_mais_novos():
    servidor = Servidor(
        {
            f"{RAIZ}/orcamento-despesa/2026_OrcamentoDespesa.zip": b"x",
            f"{RAIZ}/orcamento-despesa/2025_OrcamentoDespesa.zip": b"x",
            f"{RAIZ}/orcamento-despesa/2024_OrcamentoDespesa.zip": b"x",
        }
    )
    alvos = lote_brasil2.descobrir_zips_da_cgu(
        "orcamento-despesa",
        "{periodo}_OrcamentoDespesa.zip",
        lote_brasil2.ORCAMENTO,
        quantos=2,
        anual=True,
    )(servidor, AGORA)
    assert len(alvos) == 2 and "2024" not in " ".join(a.url for a in alvos)


def test_emendas_e_um_arquivo_so_e_some_com_erro_claro():
    url = f"{RAIZ}/emendas-parlamentares/EmendasParlamentares.zip"
    alvos = lote_brasil2.descobrir_emendas_da_cgu(Servidor({url: b"x"}), AGORA)
    assert [a.url for a in alvos] == [url]
    with pytest.raises(ErroDeDescoberta):
        lote_brasil2.descobrir_emendas_da_cgu(Servidor(), AGORA)


# ----------------------------------------------------------------- CKAN
def test_ckan_devolve_os_arquivos_no_formato_pedido_e_deixa_o_painel_de_fora():
    portal = lote_brasil2.PORTAL_DO_INSS
    servidor = Servidor(
        {
            f"{portal}/api/3/action/package_show?id=a": _pacote(
                ("XLSX", "https://x/a1.xlsx"),
                ("PDF", "https://x/a2.pdf"),
                ("HTML", "https://x/pagina"),
                ("", "https://app.powerbi.com/view?r=1"),
            )
        }
    )
    alvos = lote_brasil2.descobrir_ckan(servidor, portal, "a", formatos=("xlsx",))
    assert [a.url for a in alvos] == ["https://x/a1.xlsx"]


def test_ckan_sem_arquivo_ou_sem_o_formato_pedido_e_erro():
    portal = lote_brasil2.PORTAL_DO_INSS
    servidor = Servidor(
        {
            f"{portal}/api/3/action/package_show?id=vazio": _pacote(),
            f"{portal}/api/3/action/package_show?id=pdf": _pacote(
                ("PDF", "https://x/a")
            ),
        }
    )
    with pytest.raises(ErroDeDescoberta, match="sem arquivos"):
        lote_brasil2.descobrir_ckan(servidor, portal, "vazio")
    with pytest.raises(ErroDeDescoberta, match="formatos"):
        lote_brasil2.descobrir_ckan(servidor, portal, "pdf", formatos=("csv",))


def test_bndes_so_cnpj_filtra_o_csv_e_leva_o_pdf_como_esta():
    portal = lote_brasil2.PORTAL_DO_BNDES
    servidor = Servidor(
        {
            f"{portal}/api/3/action/package_show?id=operacoes-financiamento": _pacote(
                ("CSV", "https://x/direta.csv"),
                ("CSV", "https://x/operacoes-indiretas-automaticas.csv"),
                ("PDF", "https://x/dicionario.pdf"),
                ("XLSX", "https://x/outra.xlsx"),
            )
        }
    )
    normais = lote_brasil2.descobrir_bndes_so_cnpj(
        ("operacoes-financiamento",),
        menos_estes=lote_brasil2.INDIRETAS_AUTOMATICAS,
    )(servidor, AGORA)
    assert [(a.url, a.obter is not None) for a in normais] == [
        ("https://x/direta.csv", True),
        ("https://x/dicionario.pdf", False),
    ]
    grandes = lote_brasil2.descobrir_bndes_so_cnpj(
        ("operacoes-financiamento",), so_estes=lote_brasil2.INDIRETAS_AUTOMATICAS
    )(servidor, AGORA)
    assert [a.url for a in grandes] == ["https://x/operacoes-indiretas-automaticas.csv"]


def test_bndes_sem_csv_de_operacoes_e_erro():
    portal = lote_brasil2.PORTAL_DO_BNDES
    servidor = Servidor(
        {
            f"{portal}/api/3/action/package_show?id=x": _pacote(
                ("PDF", "https://x/a.pdf")
            )
        }
    )
    with pytest.raises(ErroDeDescoberta, match="nenhum CSV"):
        lote_brasil2.descobrir_bndes_so_cnpj(("x",))(servidor, AGORA)


def test_bndes_conhece_as_colunas_de_documento_dos_arquivos_com_cliente():
    # o filtro falha se o cabeçalho não tiver nenhuma: a lista tem de cobrir cnpj e cpf_cnpj
    assert {"cnpj", "cpf_cnpj"} <= set(lote_brasil2.COLUNAS_DE_DOCUMENTO_DO_BNDES)


def test_inss_requerimentos_pega_so_os_meses_mais_novos():
    portal = lote_brasil2.PORTAL_DO_INSS
    meses = ["202601", "202607", "202603", "202609", "202608"]
    servidor = Servidor(
        {
            f"{portal}/api/3/action/package_show?id=req": _pacote(
                *(("CSV", f"https://x/req_PEND_{m}.csv") for m in meses),
                ("PDF", "https://x/dicionario.pdf"),
            )
        }
    )
    alvos = lote_brasil2.descobrir_inss_recentes("req", 3)(servidor, AGORA)
    assert [a.url[-10:-4] for a in alvos] == ["202607", "202608", "202609"]


def test_inss_nao_leva_os_pacotes_com_pessoa():
    ids = " ".join(
        [
            lote_brasil2.FOLHA_AGREGADA_DO_INSS,
            lote_brasil2.ACORDOS_INTERNACIONAIS_DO_INSS,
        ]
        + list(lote_brasil2.REQUERIMENTOS_DO_INSS.values())
    )
    for proibido in ("perfil", "servidor", "cat-", "microdados"):
        assert proibido not in ids


# ----------------------------------------------------------------- SUSEP
def test_susep_complementos_devolve_um_alvo_por_csv_do_zip(monkeypatch):
    monkeypatch.setattr(
        lote_brasil2,
        "membros_do_zip_remoto",
        lambda c, u: [
            *lote_brasil2.CSVS_COMPLEMENTARES_DA_SUSEP,
            "Administradores.csv",
        ],
    )
    alvos = lote_brasil2.descobrir_susep_complementos(Servidor(), AGORA)
    assert [a.url.split("#")[1] for a in alvos] == list(
        lote_brasil2.CSVS_COMPLEMENTARES_DA_SUSEP
    )
    assert all(
        a.url.startswith(lote_brasil2.SES_DA_SUSEP) and a.extensao == ".csv"
        for a in alvos
    )


def test_susep_complementos_falha_se_o_zip_perdeu_um_arquivo(monkeypatch):
    monkeypatch.setattr(
        lote_brasil2, "membros_do_zip_remoto", lambda c, u: ["Ses_campos.csv"]
    )
    with pytest.raises(ErroDeDescoberta, match="Ses_diversos.csv"):
        lote_brasil2.descobrir_susep_complementos(Servidor(), AGORA)


def test_susep_complementos_nao_leva_arquivo_de_pessoa_nem_os_gigantes():
    levados = {n.lower() for n in lote_brasil2.CSVS_COMPLEMENTARES_DA_SUSEP}
    for fora in (
        "administradores.csv",
        "ses_part_acion.csv",
        "ses_contatos.csv",
        "ses_dependencias.csv",
        "ses_balanco.csv",
        "ses_rmovram.csv",
    ):
        assert fora not in levados


def test_susep_complementos_nao_repete_o_que_o_susep_ses_ja_leva():
    from base.arquivo import fontes

    ja_levados = {n.lower() for n in fontes.CSVS_DA_SUSEP}
    novos = {n.lower() for n in lote_brasil2.CSVS_COMPLEMENTARES_DA_SUSEP}
    assert not novos & ja_levados
