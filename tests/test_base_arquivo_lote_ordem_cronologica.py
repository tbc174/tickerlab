"""Coleta da ordem cronológica de pagamentos de PE e ES (linha 755 da fila; motor de risco cedente/sacado).

Os portais `dados.pe.gov.br` e `dados.es.gov.br` (CKAN, CC BY lida em 06/11/2026) publicam os pagamentos a
fornecedores com o CNPJ do credor, a data da liquidação e a do pagamento (";", datas e valores como
a fonte escreve). Aqui se confere o que a coleta baixa e o que sai **antes** de guardar: só linha de CNPJ,
sem o nome do credor nem texto livre, e sem linha com CPF em nenhum campo (ADR 0075 e 0088). Os arquivos
são de mentira.
"""

import io
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from base.arquivo import lote_ordem_cronologica as lote
from base.arquivo import registro
from base.arquivo.coleta import ErroDeDescoberta, Resposta
from base.arquivo.fontes import FONTES, POR_ID
from base.licenca import familia_do_endereco
from src.banco.coletas import Marca, licenca_da_fonte, marca_da_fonte

AGORA = datetime(2026, 11, 6, 22, tzinfo=UTC)
CNPJ_MASCARADO = "07.091.063/0001-40"
CNPJ_LIMPO = "07091063000140"
OUTRO_CNPJ = "00220359000506"
CPF = "88800000046"
CABECALHO_PE = (
    "descicao_unidade_gestora;data_liquidacao;CPF/CNPJ_Credor;nome_credor;numero_documento;"
    "valor_documento;categoria_contrato;fonte_recurso;numero_ordem_bancaria;data_ordem_bancaria;"
    "data_pagamento;valor_liquido_pagamento;justificativa_priorizacao;observacao;codigo_ug;cpf;cnpj;"
    "numero_empenho\r\n"
)
CABECALHO_ES = (
    "CodigoUg;UnidadeGestora;NomeCategoriaContrato;DataCronologica;Credor;NomeCredor;ObjetoContrato;"
    "CodigoNE;CodigoNL;DataEmissaoNL;DataEmissaoOB;CodigoOB;ValorOB;DescricaoEmpenho\r\n"
)


class Servidor:
    """Dublê do `Cliente`: a página do pacote e os arquivos, fixos."""

    def __init__(self, existem: dict[str, bytes]):
        self.existem = existem
        self.pedidos: list[str] = []

    def ler(self, url, **_):
        self.pedidos.append(url)
        return Resposta(url, self.existem[url], {})

    def cabecalhos(self, _url):
        return {"ETag": "x"}

    def baixar(self, url, destino: Path):
        self.pedidos.append(url)
        destino.write_bytes(self.existem[url])
        return {"ETag": "x"}


def _pagina(*enderecos: str) -> bytes:
    links = "".join(f'<li><a href="{e}">baixar</a></li>' for e in enderecos)
    return f"<html><body><ul>{links}</ul></body></html>".encode()


def _pagina_do(formato: lote.Formato) -> str:
    return f"{formato.portal}/dataset/{formato.pacote}"


def _filtrar(conteudo: str, formato: lote.Formato) -> str:
    saida = io.BytesIO()
    lote.filtrar_csv(io.BytesIO(conteudo.encode("utf-8-sig")), saida, formato)
    return saida.getvalue().decode("utf-8")


def _linha_pe(documento: str, credor: str = "EMPRESA SA", cpf: str = "") -> str:
    return (
        f"ASSEMBLEIA LEGISLATIVA;2025/12/22 00:00:00.000;{documento};{credor};5725;52000,00;SERVIÇOS;"
        "0500;2026OB000083;2026/01/19 00:00:00.000;2026/01/21 00:00:00.000;48464,00;"
        f"sem justificativa;obs livre;010001;{cpf};{documento};2025NE000426\r\n"
    )


def _linha_es(
    documento: str, credor: str = "EMPRESA SA", objeto: str = "OBJETO"
) -> str:
    return (
        f"450202;DETRAN;Locações;08/05/2024;{documento};{credor};{objeto};2024NE03514;2024NL04102;"
        "23/04/2024 00:00:00;07/05/2024 00:00:00;2024OB06585;59,6400;descricao livre\r\n"
    )


def test_os_portais_e_os_pacotes_sao_os_lidos_em_06_11():
    assert lote.PERNAMBUCO.portal == "https://dados.pe.gov.br"
    assert lote.PERNAMBUCO.pacote == "cronograma-de-pagamentos"
    assert lote.ESPIRITO_SANTO.portal == "https://dados.es.gov.br"
    assert lote.ESPIRITO_SANTO.pacote == (
        "portal-da-transparencia-contratos-ordem-cronologica-de-pagamentos"
    )


@pytest.mark.parametrize("formato", lote.FORMATOS, ids=lambda f: f.id)
def test_nenhuma_coluna_guardada_e_nome_ou_texto_livre(formato):
    proibidas = {
        "nome_credor",
        "nomecredor",
        "observacao",
        "objetocontrato",
        "descricaoempenho",
    }
    proibidas |= {"justificativa_priorizacao", "justificativa_suspencao", "cpf"}
    assert not proibidas & set(formato.guardadas)
    assert formato.documento in formato.guardadas


@pytest.mark.parametrize("formato", lote.FORMATOS, ids=lambda f: f.id)
def test_descobre_pela_pagina_so_o_csv_e_nunca_pela_api(formato):
    """O `robots.txt` dos portais fecha `/api/`: a descoberta lê a página do conjunto, não o CKAN."""
    recurso = f"{formato.portal}/dataset/x/resource/{{}}/download/{{}}"
    servidor = Servidor(
        {
            _pagina_do(formato): _pagina(
                recurso.format("a", "ordem_2026.csv"),
                recurso.format(
                    "b", "ordem_2026.json"
                ),  # o mesmo ano em JSON: fica de fora
                recurso.format("c", "ordem_2025.csv"),
                recurso.format("a", "ordem_2026.csv"),  # repetido
            )
        }
    )
    alvos = lote.descobrir_em(servidor, formato)
    assert [a.url for a in alvos] == [
        recurso.format("a", "ordem_2026.csv"),
        recurso.format("c", "ordem_2025.csv"),
    ]
    assert all(a.obter is not None for a in alvos)  # nada é guardado sem o filtro
    assert servidor.pedidos == [_pagina_do(formato)]
    assert not any("/api/" in pedido for pedido in servidor.pedidos)


@pytest.mark.parametrize("formato", lote.FORMATOS, ids=lambda f: f.id)
def test_so_baixa_do_proprio_portal_e_resolve_link_relativo(formato):
    """Link vindo da página é dado, não ordem: de outro host ou de outro esquema, não se baixa."""
    relativo = "/dataset/x/resource/a/download/ordem_2026.csv"
    servidor = Servidor(
        {
            _pagina_do(formato): _pagina(
                relativo,
                "https://outro.exemplo/dataset/x/download/ordem_2025.csv",
                "http://127.0.0.1/dataset/x/download/ordem_2024.csv",
                formato.portal.replace("https", "http")
                + "/dataset/x/download/ordem_2023.csv",
                f"{formato.portal}.outro.exemplo/dataset/x/download/ordem_2022.csv",
            )
        }
    )
    alvos = lote.descobrir_em(servidor, formato)
    assert [a.url for a in alvos] == [f"{formato.portal}{relativo}"]


@pytest.mark.parametrize("formato", lote.FORMATOS, ids=lambda f: f.id)
def test_pagina_sem_csv_do_portal_e_erro_de_descoberta(formato):
    servidor = Servidor(
        {_pagina_do(formato): _pagina("https://outro.exemplo/download/a.csv")}
    )
    with pytest.raises(ErroDeDescoberta, match="nenhum CSV"):
        lote.descobrir_em(servidor, formato)


def test_pe_guarda_so_cnpj_sem_o_nome_do_credor_e_sem_cpf():
    bruto = (
        CABECALHO_PE
        + _linha_pe(CNPJ_MASCARADO, "C B H BIRU OCULOS LTDA ME")
        + _linha_pe(
            CPF, "PESSOA INVENTADA LICITACAO", cpf=CPF
        )  # pessoa física: o documento é CPF
        + _linha_pe(OUTRO_CNPJ, "FIRMA DE JOSE 88800000046")  # CPF no nome do credor
        + _linha_pe("", "SEM DOCUMENTO LTDA")
        + _linha_pe("11.222.333/0001-81", "FORTQUIM LTDA")
    )
    guardado = _filtrar(bruto, lote.PERNAMBUCO)
    linhas = guardado.strip().splitlines()
    assert linhas[0].startswith('"descicao_unidade_gestora";')
    assert len(linhas) == 3  # o cabeçalho e as duas empresas
    for texto in (
        "BIRU",
        "FORTQUIM",
        "JOAO",
        "JOSE",
        CPF,
        "obs livre",
        "sem justificativa",
    ):
        assert texto not in guardado
    assert (
        "2026OB000083" in guardado and "52000,00" in guardado
    )  # o que fica, como a fonte escreve


def test_es_guarda_so_cnpj_sem_nome_nem_objeto_nem_descricao():
    bruto = (
        CABECALHO_ES
        + _linha_es(CNPJ_LIMPO, "NEUZILENE LADEIRA", "CONTRATO DE LOCAÇÃO DO IMÓVEL")
        + _linha_es(CPF, "MARIA DA SILVA")
        + _linha_es(OUTRO_CNPJ, "FIRMA", f"processo do {CPF}")  # CPF no texto livre
        + _linha_es("0000000000", "CURTO")
    )
    guardado = _filtrar(bruto, lote.ESPIRITO_SANTO)
    linhas = guardado.strip().splitlines()
    assert len(linhas) == 2
    assert CNPJ_LIMPO in linhas[1]
    for texto in ("NEUZILENE", "MARIA", "LOCAÇÃO", "descricao livre", CPF):
        assert texto not in guardado
    assert linhas[0] == (
        '"codigoug";"unidadegestora";"nomecategoriacontrato";"datacronologica";"credor";'
        '"codigone";"codigonl";"dataemissaonl";"dataemissaoob";"codigoob";"valorob"'
    )


def test_filtro_tira_a_marca_de_ordem_de_bytes_e_mantem_valores_e_datas_como_vieram():
    guardado = _filtrar(CABECALHO_ES + _linha_es(CNPJ_LIMPO), lote.ESPIRITO_SANTO)
    assert guardado.startswith('"codigoug"')
    assert "23/04/2024 00:00:00" in guardado and "59,6400" in guardado


def test_linha_com_numero_de_colunas_diferente_sai():
    quebrada = f"450202;DETRAN;Locações;08/05/2024;{CNPJ_LIMPO}\r\n"
    guardado = _filtrar(
        CABECALHO_ES + quebrada + _linha_es(OUTRO_CNPJ), lote.ESPIRITO_SANTO
    )
    assert len(guardado.strip().splitlines()) == 2


@pytest.mark.parametrize("formato", lote.FORMATOS, ids=lambda f: f.id)
def test_filtro_recusa_cabecalho_sem_a_coluna_do_documento(formato):
    with pytest.raises(ValueError, match=formato.documento):
        _filtrar("a;b\r\n1;2\r\n", formato)


def test_filtro_recusa_a_coluna_do_documento_repetida():
    with pytest.raises(ValueError, match="2 vezes"):
        _filtrar("Credor;credor;CodigoUg\r\n1;2;3\r\n", lote.ESPIRITO_SANTO)


def test_filtro_recusa_arquivo_vazio():
    with pytest.raises(ValueError, match="vazio"):
        _filtrar("", lote.PERNAMBUCO)


def test_obter_grava_o_csv_filtrado_e_nao_deixa_o_bruto(tmp_path):
    url = f"{lote.ESPIRITO_SANTO.portal}/x/download/ordem_2026.csv"
    servidor = Servidor({url: (CABECALHO_ES + _linha_es(CNPJ_LIMPO)).encode()})
    alvo = lote.alvo_do_csv(url, lote.ESPIRITO_SANTO)
    destino = tmp_path / "saida.csv"
    assert alvo.obter is not None
    alvo.obter(servidor, destino)
    assert "EMPRESA" not in destino.read_text(encoding="utf-8")
    assert [p.name for p in tmp_path.iterdir()] == ["saida.csv"]


def test_obter_nao_deixa_arquivo_pela_metade_quando_o_formato_muda(tmp_path):
    url = f"{lote.PERNAMBUCO.portal}/x/download/ordem_2026.csv"
    servidor = Servidor({url: b"a;b\r\n1;2\r\n"})
    destino = tmp_path / "saida.csv"
    with pytest.raises(ValueError):
        lote.alvo_do_csv(url, lote.PERNAMBUCO).obter(servidor, destino)  # type: ignore[misc]
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("formato", lote.FORMATOS, ids=lambda f: f.id)
def test_as_fontes_estao_no_registro_com_a_pausa_que_o_robots_pede(formato):
    fonte = POR_ID[formato.id]
    assert fonte in FONTES and fonte.grupo == "mensal"
    assert fonte in lote.fontes()
    assert (
        fonte.pausa_minima >= 10.0
    )  # Crawl-Delay: 10 nos dois robots.txt (06/11/2026)


def test_a_licenca_e_cc_by_vendavel_com_atribuicao_e_os_termos_foram_lidos():
    for fonte, familia in (
        (lote.PERNAMBUCO.id, "sefazpe"),
        (lote.ESPIRITO_SANTO.id, "esdados"),
    ):
        assert "CC BY" in licenca_da_fonte(fonte)
        assert "Só CNPJ" in licenca_da_fonte(fonte)
        assert marca_da_fonte(fonte) == Marca.VENDAVEL
        assert registro.TERMOS_LIDOS_EM[familia] >= date(2026, 11, 3)
    assert (
        familia_do_endereco(f"{lote.ESPIRITO_SANTO.portal}/dataset/x/a.csv")
        == "esdados"
    )
    assert familia_do_endereco(f"{lote.PERNAMBUCO.portal}/dataset/x/a.csv") == "sefazpe"


def test_es_recusa_documento_que_nao_e_cnpj_inteiro_de_digito_certo():
    """Revisão cruzada: CPF completado com zeros, documento todo mascarado, dígito errado e
    `CNPJ - NOME` não podem ir para o acervo (o nome e o CPF ficariam lá)."""
    bruto = CABECALHO_ES + "".join(
        _linha_es(documento)
        for documento in (
            "000" + CPF,  # CPF com zeros à esquerda até 14 dígitos
            "**************",
            "11222333000199",  # dígito verificador errado
            "11222333000181 - FULANO DE TAL",  # nome junto do CNPJ
            "11222333000181",  # este fica
        )
    )
    linhas = _filtrar(bruto, lote.ESPIRITO_SANTO).strip().splitlines()
    assert len(linhas) == 2
    assert "FULANO" not in "".join(linhas)


def test_cnpj_alfanumerico_de_digito_certo_entra():
    from base import cnpj as cnpjs

    base = "12ABC34501DE"
    completo = base + cnpjs.digitos_verificadores(base)
    guardado = _filtrar(CABECALHO_ES + _linha_es(completo), lote.ESPIRITO_SANTO)
    assert completo in guardado
