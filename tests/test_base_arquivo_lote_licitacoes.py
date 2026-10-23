"""Lote licitações e contratos (base/arquivo/lote_licitacoes.py e obter_pj.py): o que cada fonte acha
e, principalmente, que pessoa física nunca chega ao acervo (LGPD, ADR 0088)."""

import gzip
import io
import json
import zipfile
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

from base.arquivo import lote_licitacoes, obter_pj, registro
from base.arquivo.coleta import ErroDeDescoberta, Resposta, SemArquivo
from base.arquivo.destinos import DESTINOS
from base.arquivo.fontes import FONTES, POR_ID
from src.banco.coletas import Marca, licenca_da_fonte, marca_da_fonte

AGORA = datetime(2026, 10, 22, 14, tzinfo=UTC)
DUBLES = Path(__file__).parent / "arquivos" / "licitacoes"
FONTES_DO_LOTE = {f.id: f for f in lote_licitacoes.fontes()}
PESSOAS_FISICAS = ("98765432100", "JOAO DA SILVA", "11122233344", "maria", "Servidor")


class Servidor:
    """Um `Cliente` de mentira: `ler` e `baixar` respondem com o que foi combinado (int = erro HTTP)."""

    def __init__(self, respostas: dict[str, bytes | int | list[bytes]]):
        self.respostas = respostas
        self.pedidos: list[str] = []

    def _resposta(self, url: str) -> bytes:
        self.pedidos.append(url)
        resposta = self.respostas[url]
        if isinstance(resposta, int):
            erro = requests.Response()
            erro.status_code = resposta
            raise requests.HTTPError(response=erro)
        if isinstance(resposta, list):
            return resposta.pop(0)
        return resposta

    def ler(self, url, *, metodo="GET", cabecalhos=None, corpo=None):
        return Resposta(url, self._resposta(url), {})

    def baixar(self, url, destino):
        destino.write_bytes(self._resposta(url))
        return {"ETag": '"abc"'}


def _dublê(nome: str) -> bytes:
    return (DUBLES / nome).read_bytes()


def _zip(nome: str, conteudo: bytes) -> bytes:
    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, "w", zipfile.ZIP_DEFLATED) as arquivo:
        arquivo.writestr(nome, conteudo)
    return memoria.getvalue()


def _nao_guarda_pessoa_fisica(texto: str) -> None:
    for pessoa in PESSOAS_FISICAS:
        assert pessoa not in texto


# ---------------------------------------------------------------- catálogo
def test_ids_do_lote_sao_unicos_e_estao_no_catalogo_geral():
    ids = [f.id for f in lote_licitacoes.fontes()]
    assert len(ids) == len(set(ids))
    assert set(ids) <= set(POR_ID)
    assert len([f for f in FONTES if f.id in ids]) == len(ids)


def test_o_lote_nao_repete_nenhuma_fonte_que_ja_existia():
    ids_antigos = {f.id for f in FONTES if f.id not in FONTES_DO_LOTE}
    assert not set(FONTES_DO_LOTE) & ids_antigos


def test_todas_as_familias_pedidas_estao_no_lote():
    assert {i.split("-", 1)[0] for i in FONTES_DO_LOTE} == {
        "seges",
        "comprasgov",
        "transferegov",
        "pncp",
        "tcu",
        "govmg",
        "govsc",
    }


def test_grupos_do_lote_sao_conhecidos():
    assert {f.grupo for f in FONTES_DO_LOTE.values()} <= {"diaria", "semanal", "mensal"}


@pytest.mark.parametrize("fonte", sorted(FONTES_DO_LOTE))
def test_toda_fonte_do_lote_tem_licenca_marca_data_dos_termos_e_destino(fonte):
    assert not licenca_da_fonte(fonte).startswith("Desconhecida")
    assert len(licenca_da_fonte(fonte)) <= 80
    familia = fonte.split("-", 1)[0]
    assert registro.TERMOS_LIDOS_EM[familia] == date(2026, 10, 22)
    sem_licenca_escrita = familia in {"pncp", "tcu"} or fonte == "seges-pesquisa-precos"
    esperada = Marca.A_CONFIRMAR if sem_licenca_escrita else Marca.VENDAVEL
    assert marca_da_fonte(fonte) == esperada
    assert fonte in DESTINOS


def test_o_preco_de_referencia_da_seges_nao_herda_a_marca_vendavel_da_familia():
    assert marca_da_fonte("seges-pncp-compras") == Marca.VENDAVEL
    assert marca_da_fonte("seges-pesquisa-precos") == Marca.A_CONFIRMAR


def test_fontes_da_seges_conferem_a_assinatura_antes_de_baixar():
    seges = [f for i, f in FONTES_DO_LOTE.items() if i.startswith("seges-")]
    assert seges
    assert all(f.pesada for f in seges)


def test_fonte_de_api_pagina_com_pausa_e_fecha_o_dia_que_ja_foi_baixado():
    assert FONTES_DO_LOTE["pncp-contratos"].pausa_minima > 0
    assert FONTES_DO_LOTE["pncp-contratos"].guardado_vale is not None
    assert FONTES_DO_LOTE["comprasgov-resultado-itens"].guardado_vale is not None


# ---------------------------------------------------------------- SEGES
def test_seges_acha_so_o_arquivo_da_familia_em_cada_mes_e_pula_pasta_que_nao_existe():
    base = lote_licitacoes.SEGES + "comprasgov/pncp/"
    respostas: dict[str, bytes | int | list[bytes]] = {}
    for ano in range(2021, 2027):
        for mes in range(1, 13):
            if (ano, mes) <= (2026, 10):
                respostas[f"{base}{ano}/{mes:02d}/"] = 404
    respostas[f"{base}2024/05/"] = _dublê("pasta_pncp_2024_05.html")
    servidor = Servidor(respostas)

    alvos = POR_ID["seges-pncp-itens"].descobrir(servidor, AGORA)

    assert [a.url for a in alvos] == [f"{base}2024/05/compra_item_2024_05.csv.zip"]
    assert alvos[0].extensao == ".csv"
    assert alvos[0].obter is not None
    assert f"{base}2026/11/" not in servidor.pedidos  # mês que ainda não chegou
    assert f"{base}2021/01/" in servidor.pedidos


def test_seges_nao_confunde_compra_com_compra_item():
    base = lote_licitacoes.SEGES + "comprasgov/pncp/"
    respostas: dict[str, bytes | int | list[bytes]] = {
        f"{base}{ano}/{mes:02d}/": 404
        for ano in range(2021, 2027)
        for mes in range(1, 13)
        if (ano, mes) <= (2026, 10)
    }
    respostas[f"{base}2024/05/"] = _dublê("pasta_pncp_2024_05.html")
    alvos = POR_ID["seges-pncp-compras"].descobrir(Servidor(respostas), AGORA)
    assert [a.url.rsplit("/", 1)[-1] for a in alvos] == ["compra_2024_05.csv.zip"]


def test_seges_sem_nenhum_arquivo_e_erro_de_descoberta():
    base = lote_licitacoes.SEGES + "comprasgov/arp/"
    servidor = Servidor({f"{base}{ano}/": 404 for ano in range(2023, 2027)})
    with pytest.raises(ErroDeDescoberta):
        POR_ID["seges-arp-atas"].descobrir(servidor, AGORA)


def test_seges_siconv_traz_as_tabelas_da_lista_e_nao_o_zip_de_tres_gigas():
    alvos = POR_ID["seges-siconv"].descobrir(Servidor({}), AGORA)
    nomes = {a.url.rsplit("/", 1)[-1] for a in alvos}
    assert "siconv_contrato.csv.zip" in nomes
    assert "siconv_itens_licitacao.zip" in nomes
    assert "siconv.zip" not in nomes
    assert len(nomes) == len(alvos)


def test_seges_catalogo_vai_como_publicado_sem_filtro():
    alvos = POR_ID["seges-catalogo"].descobrir(Servidor({}), AGORA)
    assert [a.url.rsplit("/", 1)[-1] for a in alvos] == ["catmat.csv", "catser.csv"]
    assert all(a.obter is None for a in alvos)


# ---------------------------------------------------------------- LGPD: CSV
def _csv_filtrado(tmp_path: Path, recipiente: str, bruto: bytes) -> str:
    url = "https://exemplo.gov.br/fornecedores"
    destino = tmp_path / "saida.csv"
    obter_pj.csv_so_pj(url, recipiente)(Servidor({url: bruto}), destino)
    assert not (tmp_path / "saida.csv.bruto").exists()
    return destino.read_text(encoding="utf-8")


@pytest.mark.parametrize("recipiente", ["zip", "gz", "csv"])
def test_csv_guarda_so_pessoa_juridica_e_tira_as_colunas_de_pessoa(
    tmp_path, recipiente
):
    dados = _dublê("fornecedores.csv")
    bruto = {
        "zip": _zip("fornecedores.csv", dados),
        "gz": gzip.compress(dados),
        "csv": dados,
    }[recipiente]

    saida = _csv_filtrado(tmp_path, recipiente, bruto)

    linhas = saida.splitlines()
    assert linhas[0] == "ID_COMPRA;IDENTIFICACAO_PARTICIPANTE;NOME_PARTICIPANTE;VALOR"
    assert [linha.split(";")[0] for linha in linhas[1:]] == ["1", "4", "5"]
    assert "ACME LTDA" in saida
    assert "SEM FORNECEDOR" in saida  # sem fornecedor identificado não é pessoa física
    assert (
        "BETA, COMERCIO" in saida
    )  # a vírgula não precisa de aspas com o separador ';'
    _nao_guarda_pessoa_fisica(saida)
    assert "CPF_PREGOEIRO" not in saida
    assert "USUARIO_RESPONSAVEL" not in saida
    assert (
        "***456789**" not in saida
    )  # documento mascarado não prova que é pessoa jurídica


def test_csv_separado_por_virgula_e_em_latin1_sai_em_utf8_com_ponto_e_virgula(tmp_path):
    bruto = "id,cnpj_fornecedor,nome,email\n1,12345678000190,AÇÚCAR S/A,a@b.com\n2,123.456.789-00,ZÉ,z@b.com\n"
    url = "https://exemplo.gov.br/x.csv"
    destino = tmp_path / "saida.csv"
    obter_pj.csv_so_pj(url, "csv", "cp1252")(
        Servidor({url: bruto.encode("cp1252")}), destino
    )
    assert destino.read_text(encoding="utf-8").splitlines() == [
        "id;cnpj_fornecedor;nome",
        "1;12345678000190;AÇÚCAR S/A",
    ]


def test_csv_so_com_pessoas_fisicas_fica_so_com_o_cabecalho(tmp_path):
    bruto = b"ni_fornecedor;valor\n11122233344;1\n"
    saida = _csv_filtrado(tmp_path, "csv", bruto)
    assert saida.splitlines() == ["ni_fornecedor;valor"]


def test_cnpj_basico_nao_e_documento_de_pessoa():
    assert obter_pj.e_documento("cnpj_fornecedor")
    assert obter_pj.e_documento("IDENTIFICACAO_PARTICIPANTE")
    assert not obter_pj.e_documento("cnpj_basico")
    assert not obter_pj.e_pessoal(
        "cpf_cnpj"
    )  # coluna de documento nunca sai, a linha é que é filtrada
    assert obter_pj.e_pessoal("cpf_pregoeiro")
    assert obter_pj.e_pessoal("numero_conta_executor")


def test_zip_sem_csv_e_erro_e_nao_deixa_o_bruto(tmp_path):
    url = "https://exemplo.gov.br/vazio.zip"
    destino = tmp_path / "saida.csv"
    with pytest.raises(ValueError, match="nenhum CSV"):
        obter_pj.csv_so_pj(url, "zip")(
            Servidor({url: _zip("leiame.txt", b"oi")}), destino
        )
    assert not (tmp_path / "saida.csv.bruto").exists()


# ---------------------------------------------------------------- LGPD: API
def _paginas_do_pncp() -> list[bytes]:
    return [_dublê("pncp_pagina_1.json"), _dublê("pncp_pagina_2.json")]


def _ler_pncp(tmp_path: Path, paginas: list[bytes]) -> list[dict]:
    dia = date(2026, 10, 10)
    endereco = lote_licitacoes._endereco_dos_contratos_do_pncp
    servidor = Servidor({endereco(dia, n): [p] for n, p in enumerate(paginas, 1)})
    obter = obter_pj.json_paginado(
        lambda n: endereco(dia, n),
        lote_licitacoes._contratos_do_pncp,
        maximo_de_paginas=5,
    )
    destino = tmp_path / "pncp.jsonl"
    obter(servidor, destino)
    return [
        json.loads(linha) for linha in destino.read_text(encoding="utf-8").splitlines()
    ]


def test_pncp_guarda_so_pessoa_juridica_e_descarta_usuario_nome(tmp_path):
    itens = _ler_pncp(tmp_path, _paginas_do_pncp())

    assert [i["numeroControlePNCP"] for i in itens] == ["11-1-1/2026", "33-1-3/2026"]
    texto = json.dumps(itens, ensure_ascii=False)
    _nao_guarda_pessoa_fisica(texto)
    assert "usuarioNome" not in texto  # nem no item nem no órgão dentro dele
    assert itens[0]["orgaoEntidade"]["razaoSocial"] == "UNIAO"
    assert itens[0]["niFornecedor"] == "12345678000190"


def test_api_que_nao_para_de_paginar_e_erro_e_nao_arquivo_cortado(tmp_path):
    pagina = json.dumps(
        {"data": [{"niFornecedor": "12345678000190"}], "paginasRestantes": 9}
    )
    obter = obter_pj.json_paginado(
        lambda n: f"https://exemplo/{n}",
        lote_licitacoes._contratos_do_pncp,
        maximo_de_paginas=2,
    )
    servidor = Servidor({f"https://exemplo/{n}": [pagina.encode()] for n in (1, 2)})
    with pytest.raises(obter_pj.PaginacaoSemFim):
        obter(servidor, tmp_path / "x.jsonl")


@pytest.mark.parametrize(
    "corpo",
    [
        b"",  # o 204 do PNCP, sem corpo
        b'{"data": [], "paginasRestantes": 0}',
        json.dumps(
            {"data": [{"tipoPessoa": "PF", "niFornecedor": "98765432100"}]}
        ).encode(),
    ],
)
def test_janela_sem_pessoa_juridica_e_sem_arquivo_e_nao_falha(tmp_path, corpo):
    obter = obter_pj.json_paginado(
        lambda n: "https://exemplo/1",
        lote_licitacoes._contratos_do_pncp,
        maximo_de_paginas=2,
    )
    with pytest.raises(SemArquivo):
        obter(Servidor({"https://exemplo/1": [corpo]}), tmp_path / "x.jsonl")


def test_tipo_pessoa_pf_sai_mesmo_com_documento_de_14_digitos():
    assert (
        obter_pj.item_so_pj({"tipoPessoa": "PF", "niFornecedor": "12345678000190"})
        is None
    )
    assert obter_pj.item_so_pj({"tipoPessoa": "PJ", "niFornecedor": "12345678000190"})


# ---------------------------------------------------------------- compras.gov.br, PNCP, TCU
def test_comprasgov_tem_um_alvo_por_dia_da_janela_com_a_data_no_endereco():
    alvos = POR_ID["comprasgov-resultado-itens"].descobrir(Servidor({}), AGORA)
    assert len(alvos) == lote_licitacoes.DIAS_DO_COMPRASGOV
    assert (
        "dataResultadoPncpInicial=2026-10-21&dataResultadoPncpFinal=2026-10-21"
        in alvos[-1].url
    )
    assert "pagina=1" in alvos[-1].url
    assert len({a.url for a in alvos}) == len(alvos)


def test_comprasgov_le_o_resultado_e_a_paginacao_da_resposta(tmp_path):
    dia = date(2026, 9, 10)
    paginas = [
        {
            "resultado": [
                {"niFornecedor": "12345678000190", "tipoPessoa": "PJ", "valor": 1},
                {"niFornecedor": "11122233344", "tipoPessoa": "PF", "valor": 2},
            ],
            "paginasRestantes": 1,
        },
        {
            "resultado": [{"niFornecedor": "11222333000181", "tipoPessoa": "PJ"}],
            "paginasRestantes": 0,
        },
    ]
    enderecos = [lote_licitacoes._endereco_dos_resultados(dia, n) for n in (1, 2)]
    servidor = Servidor(
        {e: [json.dumps(p).encode()] for e, p in zip(enderecos, paginas, strict=True)}
    )
    obter = obter_pj.json_paginado(
        lambda n: lote_licitacoes._endereco_dos_resultados(dia, n),
        lote_licitacoes._resultados_do_comprasgov,
        maximo_de_paginas=3,
    )
    destino = tmp_path / "r.jsonl"
    obter(servidor, destino)
    nis = [
        json.loads(linha)["niFornecedor"] for linha in destino.read_text().splitlines()
    ]
    assert nis == ["12345678000190", "11222333000181"]


def test_dia_da_janela_so_fecha_depois_de_passados_os_dias_da_regra():
    url = lote_licitacoes._endereco_dos_resultados(date(2026, 9, 10), 1)
    guardado = lote_licitacoes._dia_fechado(30)

    def baixado_em(dia: date):
        return SimpleNamespace(
            url=url, baixado_em=datetime.combine(dia, datetime.min.time(), UTC)
        )

    assert not guardado(baixado_em(date(2026, 9, 20)))  # ainda entra registro novo
    assert guardado(baixado_em(date(2026, 10, 12)))
    # o SQLite dos testes devolve sem fuso
    sem_fuso = datetime(2026, 10, 12)  # noqa: DTZ001
    assert guardado(SimpleNamespace(url=url, baixado_em=sem_fuso))


def test_pncp_tem_um_alvo_por_dia_dos_ultimos_catorze_com_data_yyyymmdd():
    alvos = POR_ID["pncp-contratos"].descobrir(Servidor({}), AGORA)
    assert len(alvos) == lote_licitacoes.DIAS_DO_PNCP
    assert "dataInicial=20261021&dataFinal=20261021" in alvos[-1].url
    assert "tamanhoPagina=500" in alvos[-1].url
    assert (AGORA.date() - timedelta(days=14)).strftime("%Y%m%d") in alvos[0].url
    # o dia do endereço decide se o PNCP ainda pode mexer nele
    assert lote_licitacoes._dia_na_url(alvos[-1].url) == date(2026, 10, 21)


def test_tcu_pagina_pelo_offset_e_guarda_so_cnpj_formatado_ou_nao(tmp_path):
    paginas = [
        {
            "items": [
                {
                    "nome": "ACME LTDA",
                    "cpf_cnpj": "30.139.983/0001-02",
                    "processo": "1",
                },
                {
                    "nome": "JOAO DA SILVA",
                    "cpf_cnpj": "123.456.789-00",
                    "processo": "2",
                },
            ],
            "hasMore": True,
        },
        {
            "items": [{"nome": "BETA SA", "cpf_cnpj": "11.222.333/0001-81"}],
            "hasMore": False,
        },
    ]
    alvo = POR_ID["tcu-inidoneos"].descobrir(Servidor({}), AGORA)[0]
    assert "offset=0&limit=500" in alvo.url
    servidor = Servidor(
        {
            lote_licitacoes._endereco_dos_inidoneos(n): [json.dumps(p).encode()]
            for n, p in enumerate(paginas, 1)
        }
    )
    destino = tmp_path / "tcu.jsonl"
    assert alvo.obter is not None
    alvo.obter(servidor, destino)
    nomes = [json.loads(linha)["nome"] for linha in destino.read_text().splitlines()]
    assert nomes == ["ACME LTDA", "BETA SA"]
    assert "offset=500&limit=500" in lote_licitacoes._endereco_dos_inidoneos(2)


# ---------------------------------------------------------------- Transferegov
def test_transferegov_um_alvo_por_tabela_ordenado_pela_chave():
    alvos = POR_ID["transferegov-especiais"].descobrir(Servidor({}), AGORA)
    urls = [a.url for a in alvos]
    assert len(urls) == 8
    assert all("/transferenciasespeciais/" in u for u in urls)
    assert any(
        "empenho_especial?limit=1000&offset=0&order=id_empenho" in u for u in urls
    )
    assert any("order=id_op_ob" in u for u in urls)


def test_transferegov_toda_tabela_do_lote_tem_chave_de_ordenacao():
    for _, tabelas in lote_licitacoes.TABELAS_DO_TRANSFEREGOV.values():
        for tabela in tabelas:
            assert tabela in lote_licitacoes._CHAVES_DO_TRANSFEREGOV


def test_transferegov_pagina_ate_vir_pagina_menor_e_tira_conta_bancaria(tmp_path):
    linhas = lote_licitacoes.LINHAS_POR_PAGINA_DO_TRANSFEREGOV
    cheia = [
        {
            "id_plano_acao": n,
            "cnpj_beneficiario_plano_acao": "12345678000190",
            "numero_conta_plano_acao": "999",
            "nome_banco_plano_acao": "BANCO X",
            "nome_parlamentar_emenda_plano_acao": "Fulana",
        }
        for n in range(linhas)
    ]
    resto = [
        {"id_plano_acao": linhas, "cnpj_beneficiario_plano_acao": "11222333000181"}
    ]
    alvo = POR_ID["transferegov-especiais"].descobrir(Servidor({}), AGORA)[0]
    assert "plano_acao_especial" in alvo.url
    enderecos = [
        lote_licitacoes._endereco_do_transferegov(
            "transferenciasespeciais", "plano_acao_especial", n
        )
        for n in (1, 2)
    ]
    servidor = Servidor(
        {
            enderecos[0]: [json.dumps(cheia).encode()],
            enderecos[1]: [json.dumps(resto).encode()],
        }
    )
    destino = tmp_path / "t.jsonl"
    assert alvo.obter is not None
    alvo.obter(servidor, destino)
    saida = destino.read_text()
    assert len(saida.splitlines()) == linhas + 1
    for campo in ("numero_conta", "nome_banco", "parlamentar", "Fulana"):
        assert campo not in saida
    assert servidor.pedidos == enderecos


# ---------------------------------------------------------------- estados (CKAN)
def test_ckan_dos_estados_pega_so_csv_e_marca_o_gz():
    pacote = json.dumps(
        {
            "result": {
                "resources": [
                    {
                        "format": "CSV",
                        "url": "https://dados.mg.gov.br/x/dm_contratado.csv.gz",
                    },
                    {"format": "CSV", "url": "https://dados.sc.gov.br/x/contratos.csv"},
                    {
                        "format": "JSON",
                        "url": "https://dados.mg.gov.br/x/datapackage.json",
                    },
                    {
                        "format": "XLSX",
                        "url": "https://dados.sc.gov.br/x/contratos.xlsx",
                    },
                ]
            }
        }
    ).encode()
    servidor = Servidor(
        {
            f"{lote_licitacoes.PORTAL_DE_MG}/api/3/action/package_show?id=compras_contratos": pacote,
        }
    )
    alvos = POR_ID["govmg-compras-contratos"].descobrir(servidor, AGORA)
    assert [a.url.rsplit("/", 1)[-1] for a in alvos] == [
        "dm_contratado.csv.gz",
        "contratos.csv",
    ]


def test_ckan_dos_estados_sem_csv_e_erro_de_descoberta():
    pacote = json.dumps({"result": {"resources": []}}).encode()
    servidor = Servidor(
        {
            f"{lote_licitacoes.PORTAL_DE_SC}/api/3/action/package_show?id=contratos": pacote
        }
    )
    with pytest.raises(ErroDeDescoberta):
        POR_ID["govsc-contratos"].descobrir(servidor, AGORA)


def test_estado_ja_baixado_neste_mes_nao_baixa_de_novo():
    guardado = POR_ID["govsc-contratos"].guardado_vale
    assert guardado is not None
    assert guardado(SimpleNamespace(baixado_em=datetime.now(UTC) - timedelta(days=3)))
    assert not guardado(
        SimpleNamespace(baixado_em=datetime.now(UTC) - timedelta(days=40))
    )
