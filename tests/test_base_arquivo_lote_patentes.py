"""Lote patentes e marcas (base/arquivo/lote_patentes.py): INPI (marcas, desenhos, programas, partes
de patentes e contratos), EPO Linked open EP data e WIPO IP Statistics. Nada vai à internet: as
respostas são dublês de `tests/arquivos/patentes/`."""

import io
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from base.arquivo import fontes
from base.arquivo import lote_patentes as lote
from base.arquivo.coleta import Resposta, SemArquivo
from base.arquivo.destinos import DESTINOS
from base.arquivo.lote_setoriais import ARQUIVOS_DO_INPI as JA_COLETADOS_DO_INPI
from base.arquivo.registro import TERMOS_LIDOS_EM
from src.banco.coletas import (
    SEM_LICENCA_CONHECIDA,
    Marca,
    licenca_da_fonte,
    marca_da_fonte,
)

PASTA = Path(__file__).parent / "arquivos" / "patentes"
DE_NOITE = datetime(
    2026, 10, 24, 5, tzinfo=UTC
)  # 2h em Brasília: fora do horário europeu
DE_DIA = datetime(2026, 10, 23, 10, tzinfo=UTC)
FAMILIAS = {"inpi", "epo", "wipo"}


def _arquivo(nome: str) -> bytes:
    return (PASTA / nome).read_bytes()


def _filtrar(nome: str, regra: lote.RegraDoInpi) -> str:
    saida = io.BytesIO()
    lote.filtrar_titulares(io.BytesIO(_arquivo(nome)), saida, regra)
    return saida.getvalue().decode()


def _contar(nome: str, autor: str) -> dict[str, str]:
    saida = io.BytesIO()
    lote.contar_autores(io.BytesIO(_arquivo(nome)), saida, lote.RegraDeContagem(autor))
    linhas = saida.getvalue().decode().splitlines()
    assert linhas[0] == "numero_inpi,quantidade_de_autores"
    return dict(linha.split(",") for linha in linhas[1:])


class Duble:
    """Um cliente que serve um arquivo por endereço (`baixar`) ou uma resposta fixa (`ler`)."""

    def __init__(self, arquivos: dict[str, bytes] | None = None, resposta: bytes = b""):
        self.arquivos = arquivos or {}
        self.resposta = resposta
        self.pedidos: list[tuple[str, dict]] = []

    def baixar(self, url, destino):
        destino.write_bytes(self.arquivos[url])
        return {}

    def ler(self, url, *, metodo="GET", cabecalhos=None, corpo=None):
        self.pedidos.append((url, dict(cabecalhos or {})))
        return Resposta(url, self.resposta, {})


def _por_id():
    return {f.id: f for f in lote.fontes()}


# ---- o lote como um todo -----------------------------------------------------------------------
def test_ids_sem_duplicata_no_lote_e_no_catalogo():
    ids = [f.id for f in lote.fontes()]
    assert len(ids) == len(set(ids))
    todos = [f.id for f in fontes.FONTES]
    assert len(todos) == len(set(todos))
    assert set(ids) <= set(todos)


def test_toda_fonte_do_lote_tem_licenca_marca_data_e_destino():
    for fonte in lote.fontes():
        familia = fonte.id.split("-", 1)[0]
        assert licenca_da_fonte(fonte.id) != SEM_LICENCA_CONHECIDA, fonte.id
        assert len(licenca_da_fonte(fonte.id)) <= 80, fonte.id
        assert marca_da_fonte(fonte.id) is not None, fonte.id
        assert TERMOS_LIDOS_EM[familia].year == 2026, fonte.id
        assert fonte.grupo in fontes.GRUPOS, fonte.id
        assert fonte.id in DESTINOS, fonte.id


def test_as_tres_familias_estao_representadas_com_a_marca_de_cada_uma():
    assert {f.id.split("-", 1)[0] for f in lote.fontes()} == FAMILIAS
    esperada = {
        "inpi": Marca.A_CONFIRMAR,
        "epo": Marca.VENDAVEL,
        "wipo": Marca.USO_INTERNO,
    }
    for fonte in lote.fontes():
        assert marca_da_fonte(fonte.id) == esperada[fonte.id.split("-", 1)[0]], fonte.id


def test_o_lote_nao_repete_o_que_o_lote_setoriais_ja_coleta_do_inpi():
    novos = {c for arquivos in lote.ARQUIVOS_DO_INPI.values() for c, _ in arquivos}
    antigos = {c for caminhos in JA_COLETADOS_DO_INPI.values() for c in caminhos}
    assert not novos & antigos
    assert not set(lote.ARQUIVOS_DO_INPI) & set(JA_COLETADOS_DO_INPI)


def test_o_que_o_inpi_tem_de_texto_livre_ou_de_procurador_fica_de_fora():
    caminhos = {c for arquivos in lote.ARQUIVOS_DO_INPI.values() for c, _ in arquivos}
    for proibido in ("DESPACHO", "PROCURADORES", "CONTEUDO.csv", "NICE", "VIENA"):
        assert not [c for c in caminhos if proibido in c and "DI_CONTEUDO" not in c], (
            proibido
        )


def test_ritmo_mensal_e_vigias_de_termos_do_epo_e_da_wipo():
    assert {f.grupo for f in lote.fontes()} == {"mensal"}
    assert set(lote.termos()) == {"termos-epo", "termos-wipo"}
    for vigia in lote.termos():
        assert fontes.TERMOS[vigia].startswith("https://")
    por_id = _por_id()
    assert por_id["wipo-estatisticas"].pesada
    for id_, fonte in por_id.items():
        if id_.startswith(("inpi-", "epo-")):
            assert not fonte.pesada and fonte.guardado_vale is not None, id_


# ---- INPI: descoberta --------------------------------------------------------------------------
@pytest.mark.parametrize("id_", sorted(lote.ARQUIVOS_DO_INPI))
def test_inpi_cada_fonte_descobre_um_alvo_por_arquivo_sob_download(id_):
    alvos = _por_id()[id_].descobrir(Duble(), DE_NOITE)
    assert len(alvos) == len(lote.ARQUIVOS_DO_INPI[id_])
    assert all(a.url.startswith(lote.RAIZ_DO_INPI) for a in alvos)
    assert all(a.extensao == ".csv" and a.obter is not None for a in alvos)
    assert len({a.url for a in alvos}) == len(alvos)


# ---- INPI: LGPD --------------------------------------------------------------------------------
def test_lgpd_depositante_so_fica_se_o_documento_for_cnpj_de_quatorze_digitos():
    saida = _filtrar("depositantes_patentes.csv", lote.TITULAR_DE_PATENTE_OU_DESENHO)
    assert "EMPRESA FICTICIA INDUSTRIA S.A." in saida
    assert "12345678000190" in saida
    assert "98765432000155" in saida  # a padaria é CNPJ; o nome com CPF do dono sai
    for pessoa in (
        "MARIA DA SILVA",
        "JOAO EXEMPLO",
        "ACME FOREIGN",
        "SEM INFORMACAO",
        "12345678901",
        "123.456.789-09",
        "***123456***",
    ):
        assert pessoa not in saida, pessoa


def test_lgpd_a_pessoa_fisica_some_mas_a_linha_fica_para_virar_contagem():
    saida = _filtrar("depositantes_patentes.csv", lote.TITULAR_DE_PATENTE_OU_DESENHO)
    linhas = saida.splitlines()
    assert len(linhas) == 1 + 6  # cabeçalho e as seis linhas da fonte
    maria = next(linha for linha in linhas if "PI0000001,2," in linha)
    assert maria.startswith("1,PI0000001,2,BR,RJ,,,pessoa física,")


def test_lgpd_marcas_sem_representante_legal_e_titular_pf_esvaziado():
    regra = lote.ARQUIVOS_DO_INPI["inpi-marcas"][1][1]
    saida = _filtrar("depositantes_marcas.csv", regra)
    cabecalho = saida.splitlines()[0]
    assert "representante" not in cabecalho
    assert "MARCA EMPRESA LTDA" in saida
    for pessoa in (
        "REPRESENTANTE EXEMPLO",
        "ADVOGADO",
        "FULANO",
        "FOREIGN BRAND",
        "555666",
    ):
        assert pessoa not in saida, pessoa


def test_lgpd_marcas_sem_apostila_e_sem_cpf_no_nome_da_marca():
    regra = lote.ARQUIVOS_DO_INPI["inpi-marcas"][0][1]
    saida = _filtrar("bibliograficos_marcas.csv", regra)
    assert "apostila" not in saida.splitlines()[0]
    assert "FULANO EXEMPLO" not in saida
    assert "TICKERLAB EXEMPLO" in saida
    assert "12345678901" not in saida


def test_lgpd_contratos_sem_o_nome_das_partes():
    regra = lote.ARQUIVOS_DO_INPI["inpi-contratos-partes"][1][1]
    saida = _filtrar("cessionarios_contratos.csv", regra)
    assert "nome_cessionaria" not in saida
    assert "CESSIONARIA EXEMPLO" not in saida and "FULANO" not in saida
    assert "2091600" in saida  # o setor e o estado continuam


def test_lgpd_inventores_viram_so_a_quantidade_por_pedido():
    contagem = _contar("inventores_patentes.csv", "autor")
    assert contagem == {"PI0000001": "3", "PI0000002": "1"}
    saida = io.BytesIO()
    lote.contar_autores(
        io.BytesIO(_arquivo("inventores_patentes.csv")),
        saida,
        lote.RegraDeContagem("autor"),
    )
    assert b"INVENTOR" not in saida.getvalue().upper().replace(b"INVENTORES", b"")


def test_lgpd_autores_sem_ordem_contam_nomes_diferentes_sem_gravar_o_nome():
    contagem = _contar("autores_programas.csv", "nome_autor")
    assert contagem == {"512020000001": "2", "512020000002": "1"}


def test_filtro_com_coluna_que_a_fonte_tirou_e_erro_e_nao_deixa_arquivo(tmp_path):
    url = lote.RAIZ_DO_INPI + "patentes/PATENTES_DEPOSITANTES.csv"
    sem_documento = b"codigo_interno,numero_inpi,depositante\n1,PI1,EMPRESA\n"
    destino = tmp_path / "saida.csv"
    obter = lote.tratar_csv_do_inpi(url, lote.TITULAR_DE_PATENTE_OU_DESENHO)
    with pytest.raises(ValueError, match="cgccpfdepositante"):
        obter(Duble({url: sem_documento}), destino)
    assert not destino.exists()
    assert not list(tmp_path.glob("*.bruto"))


def test_obter_do_inpi_grava_o_csv_filtrado_e_devolve_os_cabecalhos(tmp_path):
    url = lote.RAIZ_DO_INPI + "patentes/PATENTES_DEPOSITANTES.csv"
    destino = tmp_path / "saida.csv"
    obter = lote.tratar_csv_do_inpi(url, lote.TITULAR_DE_PATENTE_OU_DESENHO)
    cabecalhos = obter(Duble({url: _arquivo("depositantes_patentes.csv")}), destino)
    assert cabecalhos == {}
    texto = destino.read_text(encoding="utf-8")
    assert "EMPRESA FICTICIA" in texto and "MARIA" not in texto
    assert not list(tmp_path.glob("*.bruto"))


def test_csv_do_inpi_com_marca_de_ordem_de_bytes_e_lido_normalmente():
    bruto = b"\xef\xbb\xbf" + _arquivo("depositantes_patentes.csv")
    saida = io.BytesIO()
    lote.filtrar_titulares(io.BytesIO(bruto), saida, lote.TITULAR_DE_PATENTE_OU_DESENHO)
    assert saida.getvalue().decode().startswith("codigo_interno,numero_inpi")


@pytest.mark.parametrize(
    "documento, e_cnpj",
    [
        ("12345678000190", True),
        ("12.345.678/0001-90", True),
        ("***123456***", False),
        ("123.456.789-09", False),
        ("", False),
        ("N/D", False),
    ],
)
def test_so_cnpj_completo_conta_como_pessoa_juridica(documento, e_cnpj):
    assert lote.e_cnpj_do_inpi(documento) is e_cnpj


# ---- EPO ---------------------------------------------------------------------------------------
def test_epo_um_alvo_por_empresa_com_o_nome_exato_e_sem_consultar_inventor():
    alvos = lote.descobrir_epo(Duble(), DE_NOITE)
    assert len(alvos) == len(lote.EMPRESAS_NO_EPO) == len({a.url for a in alvos})
    primeiro = urlsplit(alvos[0].url)
    assert f"{primeiro.scheme}://{primeiro.netloc}{primeiro.path}" == lote.PONTO_DO_EPO
    parametros = parse_qs(primeiro.query)
    assert parametros["output"] == ["json"]
    consulta = parametros["query"][0]
    assert 'vc:fn "Embraer S.A."' in consulta
    assert "vcApplicantOf" in consulta
    for proibido in ("inventor", "CONTAINS", "REGEX", "regex"):
        assert proibido not in consulta
    assert all(a.extensao == ".json" and a.obter is not None for a in alvos)


def test_epo_a_lista_so_tem_nome_de_empresa_nunca_de_pessoa():
    for nome in lote.EMPRESAS_NO_EPO:
        assert nome.endswith(("S.A.", "Ltda", "S.A", "PETROBRAS", "Petrobras")), nome


def test_epo_nome_com_aspas_nao_quebra_a_consulta():
    consulta = parse_qs(urlsplit(lote.endereco_do_epo('Tal "X" S.A.')).query)["query"][
        0
    ]
    assert 'vc:fn "Tal \\"X\\" S.A."' in consulta


@pytest.mark.parametrize(
    "hora, europeu", [(6, False), (7, True), (18, True), (19, False), (3, False)]
)
def test_epo_o_horario_europeu_vai_de_7h_a_19h_gmt(hora, europeu):
    assert lote.e_horario_europeu(datetime(2026, 10, 23, hora, tzinfo=UTC)) is europeu


def test_epo_de_dia_na_europa_nao_pede_nada_e_vira_sem_arquivo(tmp_path, monkeypatch):
    monkeypatch.setattr(lote, "_agora_utc", lambda: DE_DIA)
    cliente = Duble(resposta=b"{}")
    alvo = lote.descobrir_epo(cliente, DE_DIA)[0]
    with pytest.raises(SemArquivo, match="19h"):
        alvo.obter(cliente, tmp_path / "x.json")
    assert cliente.pedidos == []


def test_epo_de_noite_pede_json_do_sparql_e_grava_as_linhas_em_ordem(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(lote, "_agora_utc", lambda: DE_NOITE)
    resposta = {
        "head": {"vars": ["pub", "data"]},
        "results": {
            "bindings": [
                {"pub": {"value": "EP2"}, "data": {"value": "2020-02-02"}},
                {"pub": {"value": "EP1"}, "data": {"value": "2020-01-01"}},
            ]
        },
    }
    cliente = Duble(resposta=json.dumps(resposta).encode())
    alvo = lote.descobrir_epo(cliente, DE_NOITE)[0]
    destino = tmp_path / "x.json"
    alvo.obter(cliente, destino)
    assert cliente.pedidos == [(alvo.url, {"Accept": lote.RESPOSTA_DO_SPARQL})]
    gravado = json.loads(destino.read_text(encoding="utf-8"))
    assert [b["pub"]["value"] for b in gravado["results"]["bindings"]] == ["EP1", "EP2"]
    primeira = destino.read_bytes()
    alvo.obter(cliente, destino)
    assert destino.read_bytes() == primeira  # SHA-256 estável


def test_epo_vai_com_pausa_entre_pedidos_e_o_agente_do_tickerlab():
    assert _por_id()["epo-linked-patentes"].pausa_minima >= 1.0
    from base.arquivo.agente import AGENTE

    assert "TickerLab" in AGENTE


# ---- WIPO --------------------------------------------------------------------------------------
def test_wipo_quatro_zips_de_indicadores_com_o_endereco_oficial():
    alvos = lote.descobrir_wipo(Duble(), DE_NOITE)
    assert [a.url for a in alvos] == list(lote.ZIPS_DA_WIPO)
    assert len(alvos) == 4
    assert all(a.url.startswith("https://www.wipo.int/") for a in alvos)
    assert all(a.extensao == ".zip" for a in alvos)
    assert _por_id()["wipo-estatisticas"].tipo == "zip"


def test_a_licenca_da_wipo_manda_citar_e_nao_revender():
    licenca = licenca_da_fonte("wipo-estatisticas")
    assert "WIPO Statistics Database" in licenca
    assert marca_da_fonte("wipo-estatisticas") == Marca.USO_INTERNO
