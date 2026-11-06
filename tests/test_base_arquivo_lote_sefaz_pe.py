"""Coleta dos benefícios fiscais de Pernambuco (SEFAZ-PE, linha 578 da fila; Ficha Clara, etapa 4b).

O portal `dados.pe.gov.br` (CKAN, licença CC BY lida em 03/11/2026) publica um CSV por ano, de 2008 a
2025, com `programa`, `cnpj`, `cacepe`, `empresa`, `termo_inicial` e `termo_final` (vírgula, UTF-8,
datas "2010/08/04 00:00:00.000"). Aqui se confere o que a coleta baixa e o que sai **antes** de
guardar: só linha de CNPJ, sem a razão social (firma individual leva o nome da pessoa) e sem CPF no
texto (ADR 0088). O arquivo guardado sai com ";" como o das outras coletas (`base/incentivos.py` lê assim). Os arquivos são de mentira.
"""

import io
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from base.arquivo import lote_sefaz_pe, registro
from base.arquivo.coleta import ErroDeDescoberta, Resposta
from base.arquivo.fontes import FONTES, POR_ID
from base.licenca import familia_do_endereco
from src.banco.coletas import Marca, licenca_da_fonte, marca_da_fonte

AGORA = datetime(2026, 11, 5, 22, tzinfo=UTC)
PORTAL = lote_sefaz_pe.PORTAL
PAGINA = f"{PORTAL}/dataset/{lote_sefaz_pe.PACOTE}"
CABECALHO = '"programa","cnpj","cacepe","empresa",termo_inicial,termo_final\r\n'


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
    """A página do conjunto de dados, com um link de download por recurso."""
    links = "".join(f'<li><a href="{e}">baixar</a></li>' for e in enderecos)
    return f"<html><body><ul>{links}</ul></body></html>".encode()


def _filtrar(conteudo: str) -> str:
    saida = io.BytesIO()
    lote_sefaz_pe.filtrar_csv(io.BytesIO(conteudo.encode("utf-8-sig")), saida)
    return saida.getvalue().decode("utf-8")


def _linha(programa: str, documento: str, empresa: str = "EMPRESA SA") -> str:
    return (
        f'"{programa}","{documento}","27695905","{empresa}",'
        "2010/08/04 00:00:00.000,2025/12/31 00:00:00.000\r\n"
    )


def test_o_pacote_e_o_portal_sao_os_lidos_em_03_11():
    assert lote_sefaz_pe.PACOTE == "beneficios-fiscais"
    assert lote_sefaz_pe.PORTAL == "https://dados.pe.gov.br"
    assert lote_sefaz_pe.COLUNAS_GUARDADAS == (
        "programa",
        "cnpj",
        "cacepe",
        "termo_inicial",
        "termo_final",
    )


def test_descobre_pela_pagina_so_o_csv_de_cada_ano_e_nunca_pela_api():
    """O `robots.txt` do portal fecha `/api/`: a descoberta lê a página do conjunto, não o CKAN."""
    recurso = (
        f"{PORTAL}/dataset/cd0c/resource/{{}}/download/beneficios_fiscais_{{}}_.{{}}"
    )
    servidor = Servidor(
        {
            PAGINA: _pagina(
                recurso.format("a", "2025", "csv"),
                recurso.format(
                    "b", "2025", "json"
                ),  # o mesmo ano em JSON: fica de fora
                recurso.format("c", "2008", "csv"),
                f"{PORTAL}/dataset/cd0c/resource/d/download/metadados_beneficios_fiscais.json",
                f"{PORTAL}/dataset/cd0c/resource/a/download/beneficios_fiscais_2025_.csv",  # repetido
            )
        }
    )
    alvos = lote_sefaz_pe.descobrir(servidor, AGORA)
    assert [a.url for a in alvos] == [
        recurso.format("a", "2025", "csv"),
        recurso.format("c", "2008", "csv"),
    ]
    assert all(a.obter is not None for a in alvos)  # nada é guardado sem o filtro
    assert servidor.pedidos == [PAGINA]
    assert not any("/api/" in pedido for pedido in servidor.pedidos)


def test_so_baixa_do_proprio_portal_e_resolve_link_relativo():
    """Link vindo da página é dado, não ordem: de outro host ou de outro esquema, não se baixa."""
    relativo = "/dataset/cd0c/resource/a/download/beneficios_fiscais_2025_.csv"
    servidor = Servidor(
        {
            PAGINA: _pagina(
                relativo,
                "https://outro.exemplo/dataset/x/download/beneficios_fiscais_2024_.csv",
                "http://127.0.0.1/dataset/x/download/beneficios_fiscais_2023_.csv",
                "http://dados.pe.gov.br/dataset/x/download/beneficios_fiscais_2022_.csv",
                f"{PORTAL}.outro.exemplo/dataset/x/download/beneficios_fiscais_2021_.csv",
            )
        }
    )
    alvos = lote_sefaz_pe.descobrir(servidor, AGORA)
    assert [a.url for a in alvos] == [f"{PORTAL}{relativo}"]


def test_pagina_so_com_link_de_fora_e_erro_de_descoberta():
    servidor = Servidor({PAGINA: _pagina("https://outro.exemplo/download/a.csv")})
    with pytest.raises(ErroDeDescoberta, match="nenhum CSV"):
        lote_sefaz_pe.descobrir(servidor, AGORA)


def test_pagina_sem_csv_e_erro_de_descoberta():
    servidor = Servidor({PAGINA: _pagina(f"{PORTAL}/dataset/x/download/a.json")})
    with pytest.raises(ErroDeDescoberta, match="nenhum CSV"):
        lote_sefaz_pe.descobrir(servidor, AGORA)


def test_filtro_guarda_so_cnpj_sem_a_razao_social_e_sem_cpf():
    cnpj = "04154994000151"
    bruto = (
        CABECALHO
        + _linha("MAQUINAS PESADAS", cnpj, "C B H BIRU OCULOS LTDA ME")
        + _linha(
            "PRODEPE", "12345678909", "JOAO DA SILVA"
        )  # CPF na coluna do documento
        + _linha(
            "PRODEPE", "00184780000177", "JOAO ADOEZIO CUNHA 12345678909"
        )  # CPF no nome
        + _linha("PRODEPE", "", "SEM DOCUMENTO LTDA")
        + _linha("PEAP", "00220359000506", "FORTQUIM LTDA")
    )
    guardado = _filtrar(bruto)
    linhas = guardado.strip().splitlines()
    assert linhas[0] == '"programa";"cnpj";"cacepe";"termo_inicial";"termo_final"'
    assert len(linhas) == 3
    assert cnpj in linhas[1] and "00220359000506" in linhas[2]
    for nome_ou_cpf in ("BIRU", "FORTQUIM", "JOAO", "12345678909", "empresa"):
        assert nome_ou_cpf not in guardado


def test_filtro_aceita_bom_e_mantem_as_datas_como_vieram():
    guardado = _filtrar(CABECALHO + _linha("PEAP", "00220359000506"))
    assert "2010/08/04 00:00:00.000" in guardado
    assert guardado.startswith('"programa"')  # sem a marca de ordem de bytes


def test_filtro_recusa_cabecalho_sem_a_coluna_do_documento():
    with pytest.raises(ValueError, match="cnpj"):
        _filtrar('"programa","cacepe","empresa"\r\n"X","1","Y"\r\n')


def test_filtro_recusa_arquivo_vazio():
    with pytest.raises(ValueError, match="vazio"):
        _filtrar("")


def test_obter_grava_o_csv_filtrado_e_nao_deixa_o_bruto(tmp_path):
    url = "https://x/beneficios_fiscais_2025_.csv"
    servidor = Servidor({url: (CABECALHO + _linha("PEAP", "00220359000506")).encode()})
    alvo = lote_sefaz_pe.alvo_do_csv(url)
    destino = tmp_path / "saida.csv"
    assert alvo.obter is not None
    alvo.obter(servidor, destino)
    assert "FORTQUIM" not in destino.read_text(encoding="utf-8")
    assert "EMPRESA" not in destino.read_text(encoding="utf-8")
    assert [p.name for p in tmp_path.iterdir()] == ["saida.csv"]


def test_obter_nao_deixa_arquivo_pela_metade_quando_o_formato_muda(tmp_path):
    url = "https://x/beneficios_fiscais_2025_.csv"
    servidor = Servidor({url: b'"programa","empresa"\r\n"X","Y"\r\n'})
    destino = tmp_path / "saida.csv"
    with pytest.raises(ValueError):
        lote_sefaz_pe.alvo_do_csv(url).obter(servidor, destino)  # type: ignore[misc]
    assert list(tmp_path.iterdir()) == []


def test_a_fonte_esta_no_registro_com_a_pausa_que_o_robots_pede():
    fonte = POR_ID["sefazpe-beneficios"]
    assert fonte in FONTES and fonte.grupo == "mensal"
    assert fonte in lote_sefaz_pe.fontes()
    assert fonte.pausa_minima >= 10.0  # Crawl-Delay: 10 do robots.txt (05/11/2026)


def test_a_licenca_e_cc_by_vendavel_com_atribuicao_e_os_termos_foram_lidos():
    fonte = "sefazpe-beneficios"
    assert "CC BY" in licenca_da_fonte(fonte)
    assert "Só CNPJ" in licenca_da_fonte(fonte)
    assert marca_da_fonte(fonte) == Marca.VENDAVEL
    assert registro.TERMOS_LIDOS_EM["sefazpe"] >= date(2026, 11, 3)
    assert familia_do_endereco(f"{PORTAL}/dataset/x/a.csv") == "sefazpe"
