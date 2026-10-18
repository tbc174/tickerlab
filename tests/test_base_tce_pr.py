"""PIT do TCE-PR (base/tce_pr.py): só os atributos da lista, nenhuma pessoa, e só o que mudou.

Recortes com o formato real do PIT (atributos e codificação medidos em 17/10/2026), mas com nomes e
CPF inventados: o CPF 123.456.789-09 tem DV válido e é o exemplo clássico de documentação, nunca de
uma pessoa daqui. CNPJ 11.222.333/0001-81: exemplo com DV válido; ...-82, o mesmo com DV errado.
"""

import io
import re
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest
import requests

from base import cnpj, tce_pr
from base.arquivo import coleta, fontes
from base.arquivo.coleta import Resposta

AGORA = datetime(2026, 10, 18, 9, tzinfo=UTC)  # domingo, 6h em Brasília
CPF_INVENTADO = "00012345678909"  # como o PIT manda: 14 posições, zeros à esquerda
CNPJ_BOM = "11222333000181"
CNPJ_DV_ERRADO = "11222333000182"
# raiz antiga (00.000.208, como as dos bancos mais velhos), com os DVs certos: passa como CNPJ e como CPF
RAIZ_ANTIGA = next(
    v for v in (f"000002080001{dv:02d}" for dv in range(100)) if cnpj.dv_confere(v)
)

LICITACAO = (
    '<root><Licitacao cdIBGE="410740" nmMunicipio="Município Inventado" idPessoa="12277" '
    'nmEntidade="Prefeitura Inventada" idLicitacao="2315640" dsModalidadeLicitacao="Pregão" '
    'nrLicitacao="1" nrAnoLicitacao="2025" dtEdital="2025-01-30T00:00:00" '
    'vlLicitacao="1124890.93" dtEnvio="2025-02-04T09:56:11.707" '
    'dsObjeto="Contratação de show do cantor Fulano de Tal" '
    'DataReferencia="2026/09 "/></root>'
)
PARTICIPANTES = (
    "<root>"
    '<LicitacaoParticipante idLicitacao="2315640" sgDocParticipanteLicitacao="CNPJ        " '
    f'nrDocParticipanteLicitacao="{CNPJ_BOM}" nmParticipanteLicitacao="Empresa Inventada Ltda"/>'
    '<LicitacaoParticipante idLicitacao="2315640" sgDocParticipanteLicitacao="CPF         " '
    f'nrDocParticipanteLicitacao="{CPF_INVENTADO}" nmParticipanteLicitacao="Fulano de Tal"/>'
    '<LicitacaoParticipante idLicitacao="2315640" sgDocParticipanteLicitacao="CNPJ        " '
    f'nrDocParticipanteLicitacao="{CNPJ_DV_ERRADO}" nmParticipanteLicitacao="Outra Ltda"/>'
    "</root>"
)
VENCEDORES = (
    "<root>"
    f'<LicitacaoVencedor idlicitacao="2315640" nmPessoa="Empresa Inventada" nrDocumento="{CNPJ_BOM}" '
    'vlPropostaItem="1039374.67" dsItem="Show do cantor Fulano de Tal"/>'
    f'<LicitacaoVencedor idlicitacao="2315640" nmPessoa="Fulano de Tal" nrDocumento="{CPF_INVENTADO}" '
    'vlPropostaItem="10.00"/>'
    "</root>"
)


def _zip(arquivos: dict[str, bytes], data=(2026, 9, 10, 15, 53, 2)) -> bytes:
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as arquivo_zip:
        for nome, conteudo in arquivos.items():
            arquivo_zip.writestr(zipfile.ZipInfo(nome, data), conteudo)
    return saida.getvalue()


def _zip_de_licitacao(prefixo="2025_410740", **extra: bytes) -> bytes:
    return _zip(
        {
            f"{prefixo}_Licitacao.xml": b"\xef\xbb\xbf" + LICITACAO.encode(),
            f"{prefixo}_LicitacaoParticipante.xml": PARTICIPANTES.encode("utf-16"),
            f"{prefixo}_LicitacaoVencedor.xml": VENCEDORES.encode(),
            **extra,
        }
    )


def _xmls(regravado: bytes) -> dict[str, str]:
    with zipfile.ZipFile(io.BytesIO(regravado)) as arquivo_zip:
        return {n: arquivo_zip.read(n).decode("utf-8") for n in arquivo_zip.namelist()}


def test_atributo_fora_da_lista_nunca_chega_ao_acervo():
    xmls = _xmls(tce_pr.regravar(_zip_de_licitacao()))
    licitacao = xmls["2025_410740_Licitacao.xml"]
    assert 'idLicitacao="2315640"' in licitacao
    assert 'dtEnvio="2025-02-04T09:56:11.707"' in licitacao  # a D1 usa
    for fora in ("nmMunicipio", "nmEntidade", "dsObjeto", "Fulano", "Inventad"):
        assert fora not in licitacao
    vencedores = xmls["2025_410740_LicitacaoVencedor.xml"]
    assert "dsItem" not in vencedores and "nmPessoa" not in vencedores


def test_licitante_pf_vira_linha_anonima():
    participantes = _xmls(tce_pr.regravar(_zip_de_licitacao()))[
        "2025_410740_LicitacaoParticipante.xml"
    ]
    linhas = re.findall(r"<LicitacaoParticipante [^>]*/>", participantes)
    assert (
        len(linhas) == 3
    )  # a linha da pessoa fica (conta como concorrente), sem documento
    assert f'nrDocParticipanteLicitacao="{CNPJ_BOM}"' in linhas[0]
    assert 'tipoDocumento="cnpj"' in linhas[0]
    assert 'tipoDocumento="cpf"' in linhas[1]
    assert "nrDocParticipanteLicitacao" not in linhas[1]
    assert 'tipoDocumento="cnpj_dv_errado"' in linhas[2]
    assert CNPJ_DV_ERRADO not in participantes
    assert "12345678909" not in participantes and "Fulano" not in participantes


def test_vencedor_sem_sigla_decide_pelo_dv():
    vencedores = _xmls(tce_pr.regravar(_zip_de_licitacao()))[
        "2025_410740_LicitacaoVencedor.xml"
    ]
    linhas = re.findall(r"<LicitacaoVencedor [^>]*/>", vencedores)
    assert f'nrDocumento="{CNPJ_BOM}"' in linhas[0]
    assert 'tipoDocumento="cpf"' in linhas[1] and "nrDocumento" not in linhas[1]


@pytest.mark.parametrize(
    ("sigla", "numero", "esperado"),
    [
        ("CNPJ", CNPJ_BOM, ("cnpj", CNPJ_BOM)),
        ("CNPJ", CNPJ_DV_ERRADO, ("cnpj_dv_errado", None)),
        ("CPF", CPF_INVENTADO, ("cpf", None)),
        ("CPF", CNPJ_BOM, ("cpf", None)),  # a fonte diz CPF: vale a fonte
        (None, CPF_INVENTADO, ("cpf", None)),  # sem sigla: o DV do CPF decide
        (None, "12345678909", ("cpf", None)),
        # 5 zeros ou mais à esquerda passam nos dois DVs: a raiz do Banco do Brasil fica como CNPJ
        # (uma por agência; 39 dos 40 casos do ensaio), as outras saem sem o número
        (None, "00000000000191", ("cnpj", "00000000000191")),
        (
            "CNPJ",
            "00000000123456",
            ("cnpj_dv_errado", None),
        ),  # BB com DV errado não passa
        ("CNPJ", RAIZ_ANTIGA, ("cnpj_ou_cpf", None)),
        (None, RAIZ_ANTIGA, ("cnpj_ou_cpf", None)),
        (None, CNPJ_BOM, ("cnpj", CNPJ_BOM)),
        (None, "", ("vazio", None)),
        (None, "ABC", ("outro", None)),
        ("RG", "123456", ("outro", None)),
    ],
)
def test_documento_ou_classe(sigla, numero, esperado):
    assert tce_pr.documento_ou_classe(sigla, numero) == esperado


def test_xml_e_atributo_desconhecidos_ficam_de_fora():
    regravado = tce_pr.regravar(
        _zip_de_licitacao(
            **{"2025_410740_Novidade.xml": b'<root><Novidade nmPessoa="X"/></root>'}
        )
    )
    assert "2025_410740_Novidade.xml" not in _xmls(regravado)


def test_regravado_e_igual_byte_a_byte_para_o_mesmo_conteudo():
    # o PIT regrava o ZIP toda semana com data nova: o acervo guarda uma vez só (SHA-256 igual)
    antes = tce_pr.regravar(_zip_de_licitacao())
    depois = tce_pr.regravar(
        _zip(
            {
                n: zipfile.ZipFile(io.BytesIO(_zip_de_licitacao())).read(n)
                for n in sorted(
                    zipfile.ZipFile(io.BytesIO(_zip_de_licitacao())).namelist(),
                    reverse=True,
                )
            },
            data=(2026, 10, 17, 1, 0, 0),
        )
    )
    assert antes == depois


def test_utf16_de_2013_e_utf8_dao_o_mesmo_resultado():
    em_utf8 = _zip({"2013_410010_Licitacao.xml": LICITACAO.encode("utf-8")})
    em_utf16 = _zip({"2013_410010_Licitacao.xml": LICITACAO.encode("utf-16")})
    assert tce_pr.regravar(em_utf8) == tce_pr.regravar(em_utf16)


def test_nenhum_cpf_nem_nome_no_regravado():
    regravado = tce_pr.regravar(_zip_de_licitacao())
    assert tce_pr.vestigios_de_pessoa(regravado) == []
    # e a varredura acha o que não devia estar lá
    sujo = _zip(
        {
            "x_Contrato.xml": f'<root><Contrato nmContratado="A" nrDocContratado="{CPF_INVENTADO}"/></root>'.encode()
        }
    )
    vestigios = tce_pr.vestigios_de_pessoa(sujo)
    assert any("nmContratado" in v for v in vestigios)
    assert any("CPF" in v for v in vestigios)


def test_toda_lista_tem_so_atributos_sem_pessoa():
    for xml, permitidos in tce_pr.PERMITIDOS.items():
        for atributo in permitidos:
            assert not atributo.startswith("nm"), (xml, atributo)
            assert atributo not in ("dsObjeto", "dsHistorico", "dsItem"), (
                xml,
                atributo,
            )
            assert not atributo.lower().startswith(("dsmotivo", "dsmulta")), (
                xml,
                atributo,
            )


# --- a fonte no arquivista: ZIP dentro de ZIP remoto ---------------------------------------------


class ServidorDoPit:
    """Os ZIPs anuais em memória; HEAD e pedidos de trecho, contados. Ano que falta: 404."""

    def __init__(self, anos: dict[int, bytes]):
        self.anos = {fontes.PIT_DO_TCE_PR.format(ano=a): z for a, z in anos.items()}
        self.trechos: list[tuple[str, int, int]] = []

    def _zip(self, url):
        if url not in self.anos:
            resposta = requests.Response()
            resposta.status_code = 404
            raise requests.HTTPError("404", response=resposta)
        return self.anos[url]

    def cabecalhos(self, url):
        return {"Content-Length": str(len(self._zip(url)))}

    def ler_trecho(self, url, inicio, fim):
        self.trechos.append((url, inicio, fim))
        return self._zip(url)[inicio : fim + 1]

    def ler(self, url, *, metodo="GET", cabecalhos=None):
        return Resposta(url, self._zip(url), {})

    def baixar(self, url, destino: Path):
        raise AssertionError("nunca baixa o ZIP anual inteiro")


def _zip_do_ano(ano: int, municipios=("410010", "410020"), mudado: str = "") -> bytes:
    internos = {}
    for municipio in municipios:
        prefixo = f"{ano}_{municipio}"
        conteudo = _zip_de_licitacao(prefixo)
        if municipio == mudado:
            conteudo = _zip_de_licitacao(
                prefixo,
                **{
                    f"{prefixo}_Licitacao.xml": LICITACAO.replace(
                        "1124890.93", "1.00"
                    ).encode()
                },
            )
        internos[f"{prefixo}_Licitacao.zip"] = conteudo
        internos[f"{prefixo}_Contrato.zip"] = _zip(
            {f"{prefixo}_Contrato.xml": b"<root/>"}
        )
        internos[f"{prefixo}_Relacionamentos.zip"] = _zip(
            {
                f"{prefixo}_LicitacaoXContrato.xml": b'<root><LicitacaoXContrato idContrato="1" idLicitacao="2"/></root>'
            }
        )
        internos[f"{prefixo}_Despesa.zip"] = _zip(
            {f"{prefixo}_Empenho.xml": b"<root/>"}
        )
    return _zip(internos)


def test_descobre_os_anos_do_pit_e_so_os_tres_temas():
    servidor = ServidorDoPit(
        {a: _zip_do_ano(a, ("410010",)) for a in range(2013, 2027)}
    )
    alvos = fontes.descobrir_pit(servidor, AGORA)
    assert len(alvos) == 14 * 3  # 2013 a 2026, Despesa fica para o PR 2
    assert alvos[0].url == (
        "https://pit.tce.pr.gov.br/Arquivos/2013_PIT_TodosArquivos.zip#2013_410010_Contrato.zip"
    )
    assert not any("Despesa" in a.url for a in alvos)
    assert all(a.versao and "crc32-" in a.versao for a in alvos)


def test_ano_corrente_que_ainda_nao_saiu_fica_de_fora_mas_ano_fechado_que_falta_e_falha():
    janeiro = datetime(2027, 1, 4, 9, tzinfo=UTC)
    anos = {a: _zip_do_ano(a, ("410010",)) for a in range(2013, 2027)}
    assert len(fontes.descobrir_pit(ServidorDoPit(anos), janeiro)) == 14 * 3
    del anos[2020]
    with pytest.raises(requests.HTTPError):
        fontes.descobrir_pit(ServidorDoPit(anos), janeiro)


def test_so_baixa_zip_interno_com_crc_novo(banco, tmp_path):
    fonte = fontes.POR_ID["tce-pr-pit"]
    assert fonte.pesada and fonte.grupo == "semanal"
    espaco = {"espaco": lambda pasta: (900 * 1024**3, 800 * 1024**3)}
    servidor = ServidorDoPit({2025: _zip_do_ano(2025)})
    so_2025 = fonte.__class__(
        fonte.id,
        fonte.grupo,
        lambda c, a: fontes.descobrir_pit(c, a, anos=(2025,)),
        fonte.tipo,
        fonte.pesada,
    )
    primeira = coleta.arquivar(
        so_2025, servidor, AGORA, tmp_path / "t", pausa=0, **espaco
    )
    assert (primeira.novos, primeira.falhas) == (6, [])

    servidor.anos = {
        fontes.PIT_DO_TCE_PR.format(ano=2025): _zip_do_ano(2025, mudado="410020")
    }
    servidor.trechos.clear()
    segunda = coleta.arquivar(
        so_2025, servidor, AGORA, tmp_path / "t", pausa=0, **espaco
    )
    assert (segunda.pulados, segunda.novos, segunda.falhas) == (5, 1, [])
    # só o índice do ZIP anual e os 2 trechos do ZIP interno que mudou (cabeçalho local e dados)
    interno = [t for t in servidor.trechos if t[2] - t[1] < 10_000]
    assert len(servidor.trechos) <= 5 and len(interno) >= 2


def test_pit_nao_espera_entre_zips_internos_que_nem_pediu(banco, tmp_path, monkeypatch):
    esperas: list[float] = []
    monkeypatch.setattr(coleta, "esperar", esperas.append)
    fonte = fontes.POR_ID["tce-pr-pit"]
    so_2025 = fonte.__class__(
        fonte.id,
        fonte.grupo,
        lambda c, a: fontes.descobrir_pit(c, a, anos=(2025,)),
        fonte.tipo,
        fonte.pesada,
    )
    espaco = {"espaco": lambda pasta: (900 * 1024**3, 800 * 1024**3)}
    servidor = ServidorDoPit({2025: _zip_do_ano(2025)})
    coleta.arquivar(so_2025, servidor, AGORA, tmp_path / "t", pausa=1.0, **espaco)
    assert len(esperas) == 5  # 6 ZIPs internos baixados: uma pausa entre cada dois
    esperas.clear()
    resultado = coleta.arquivar(
        so_2025, servidor, AGORA, tmp_path / "t", pausa=1.0, **espaco
    )
    assert (
        resultado.pulados == 6 and esperas == []
    )  # nada mudou: nenhum pedido, nenhuma espera


def test_nome_com_pasta_vira_so_o_nome_no_regravado():
    # nome vindo da fonte com pasta ("../"): o acervo guarda só o nome do arquivo
    regravado = tce_pr.regravar(
        _zip({"../../2025_410740_Licitacao.xml": LICITACAO.encode()})
    )
    assert list(_xmls(regravado)) == ["2025_410740_Licitacao.xml"]


def test_xml_acima_do_limite_e_falha_e_nao_vai_para_o_acervo(monkeypatch):
    monkeypatch.setattr(tce_pr, "LIMITE_DO_XML", 100)
    with pytest.raises(ValueError, match="acima do limite"):
        tce_pr.regravar(_zip_de_licitacao())


# --- PR 2: o tema `Despesa` (empenho, liquidação, pagamento e estornos) ---------------------------

CPF_DO_CREDOR = "00012345678909"
EMPENHOS = (
    "<root>"
    '<Empenho cdIBGE="410740" idPessoa="12277" idEmpenho="901" nrEmpenho="1" nrAnoEmpenho="2025" '
    'dtEmpenho="2025-03-10T00:00:00" vlEmpenho="5000.00" cdFuncao="12" cdElemento="30" '
    f'sgDocCredor="CNPJ        " nrDocCredor="{CNPJ_BOM}" nmCredor="Empresa Inventada Ltda" '
    'nmOrdernador="Beltrano Inventado" sgDocOrdenador="CPF" nrDocOrdernador="00098765432100" '
    'dsHistorico="Pagamento da consulta do paciente Fulano de Tal" nmOrgao="Saúde Inventada" '
    'ultimoEnvioSIMAMNesteExercicio="2025/09" DataReferencia="2026/09 "/>'
    '<Empenho cdIBGE="410740" idPessoa="12277" idEmpenho="902" nrEmpenho="2" nrAnoEmpenho="2025" '
    'dtEmpenho="2025-03-11T00:00:00" vlEmpenho="80.00" '
    f'sgDocCredor="CPF         " nrDocCredor="{CPF_DO_CREDOR}" nmCredor="Fulano de Tal"/>'
    '<Empenho cdIBGE="410740" idPessoa="12277" idEmpenho="903" nrEmpenho="3" nrAnoEmpenho="2025" '
    'dtEmpenho="2025-03-12T00:00:00" vlEmpenho="70.00" '
    f'sgDocCredor="CNPJ        " nrDocCredor="{CNPJ_DV_ERRADO}" nmCredor="Outra Ltda"/>'
    "</root>"
)
LIQUIDACOES = (
    "<root>"
    '<EmpenhoLiquidacao idEmpenho="901" idLiquidacao="7001" dtLiquidacao="2025-03-20T00:00:00" '
    'vlLiquidacaoBruto="5000.00" nmLiquidante="Sicrano Inventado" nrDocLiquidante="00011122233" '
    'DataEnvioParaTCE="2025-04-02T08:00:00"/>'
    '<EmpenhoLiquidacao idEmpenho="902" idLiquidacao="7002" dtLiquidacao="2025-03-21T00:00:00" '
    'vlLiquidacaoBruto="80.00" DataEnvioParaTCE="2025-04-02T08:00:00"/>'
    "</root>"
)
PAGAMENTOS = (
    "<root>"
    '<EmpenhoPagamento idEmpenho="901" idPagamento="8001" dtOperacao="2025-03-25T00:00:00" '
    'vlOperacao="5000.00" nmResponsavel="Fulana Inventada" nrDocResponsavel="00044455566"/>'
    '<EmpenhoPagamento idEmpenho="902" idPagamento="8002" dtOperacao="2025-03-26T00:00:00" '
    'vlOperacao="80.00" nmResponsavel="Fulana Inventada" nrDocResponsavel="00044455566"/>'
    "</root>"
)
ESTORNO_DE_PAGAMENTO = (
    '<root><EmpenhoPagamentoEstorno idEmpenho="902" idEstornoPagamento="9001" vlEstorno="80.00" '
    'dtEstorno="2025-03-30T00:00:00" DataEnvioParaTCE="2025-04-02T08:00:00"/></root>'
)


def _zip_de_despesa(prefixo="2025_410740") -> bytes:
    return _zip(
        {
            f"{prefixo}_Empenho.xml": EMPENHOS.encode("utf-16"),
            f"{prefixo}_EmpenhoLiquidacao.xml": LIQUIDACOES.encode(),
            f"{prefixo}_EmpenhoPagamento.xml": PAGAMENTOS.encode(),
            f"{prefixo}_EmpenhoPagamentoEstorno.xml": ESTORNO_DE_PAGAMENTO.encode(),
            # fora do escopo do PR 2: nota fiscal da liquidação
            f"{prefixo}_EmpenhoLiquidacaoDocumentoFiscal.xml": b"<root/>",
        }
    )


def test_credor_pf_nunca_chega_ao_acervo():
    xmls = _xmls(tce_pr.regravar(_zip_de_despesa()))
    empenhos = xmls["2025_410740_Empenho.xml"]
    assert re.findall(r'idEmpenho="(\d+)"', empenhos) == [
        "901",
        "903",
    ]  # o 902 saiu inteiro
    assert 'descartadasPorCredorPf="1"' in empenhos  # contada no registro
    assert (
        f'nrDocCredor="{CNPJ_BOM}"' in empenhos and 'tipoDocumento="cnpj"' in empenhos
    )
    assert (
        'tipoDocumento="cnpj_dv_errado"' in empenhos and CNPJ_DV_ERRADO not in empenhos
    )
    # liquidação e pagamento do empenho de pessoa saem junto (e o estorno), também contados
    liquidacoes = xmls["2025_410740_EmpenhoLiquidacao.xml"]
    assert re.findall(r'idLiquidacao="(\d+)"', liquidacoes) == ["7001"]
    assert 'descartadasPorCredorPf="1"' in liquidacoes
    pagamentos = xmls["2025_410740_EmpenhoPagamento.xml"]
    assert re.findall(r'idPagamento="(\d+)"', pagamentos) == ["8001"]
    assert "idEstornoPagamento" not in xmls["2025_410740_EmpenhoPagamentoEstorno.xml"]
    tudo = "".join(xmls.values())
    assert "12345678909" not in tudo and "Fulano" not in tudo


def test_despesa_sem_ordenador_liquidante_responsavel_historico():
    xmls = _xmls(tce_pr.regravar(_zip_de_despesa()))
    tudo = "".join(xmls.values())
    for fora in (
        "nmOrdernador", "nrDocOrdernador", "sgDocOrdenador", "dsHistorico", "nmLiquidante",
        "nrDocLiquidante", "nmResponsavel", "nrDocResponsavel", "nmCredor", "nmOrgao",
        "Beltrano", "Sicrano", "Fulana", "paciente",
    ):  # fmt: skip
        assert fora not in tudo, fora
    assert 'dtEmpenho="2025-03-10T00:00:00"' in tudo and 'vlOperacao="5000.00"' in tudo
    assert 'DataEnvioParaTCE="2025-04-02T08:00:00"' in tudo  # a D1 usa
    assert "DocumentoFiscal" not in "".join(xmls)  # fora do escopo: não entra
    assert tce_pr.vestigios_de_pessoa(tce_pr.regravar(_zip_de_despesa())) == []


def test_descobre_so_a_despesa_na_fonte_propria():
    servidor = ServidorDoPit(
        {a: _zip_do_ano(a, ("410010",)) for a in range(2013, 2027)}
    )
    alvos = fontes.descobrir_pit_despesa(servidor, AGORA)
    assert len(alvos) == 14
    assert all(a.url.endswith("_Despesa.zip") for a in alvos)
    fonte = fontes.POR_ID["tce-pr-despesa"]
    assert fonte.pesada and fonte.grupo == "semanal"
    assert fontes.POR_ID["tce-pr-pit"].descobrir is not fonte.descobrir


def test_xml_partido_em_pedacos_entra_e_o_credor_pf_de_um_pedaco_leva_o_pagamento_do_outro():
    # Londrina (2025) parte cada XML da Despesa em `_1`, `_2`...: sem isso a cidade inteira ficava de fora
    pf = (
        '<root><Empenho idEmpenho="5" sgDocCredor="CPF" '
        f'nrDocCredor="{CPF_DO_CREDOR}" vlEmpenho="1.00"/></root>'
    )
    pj = (
        f'<root><Empenho idEmpenho="6" sgDocCredor="CNPJ" nrDocCredor="{CNPJ_BOM}" '
        'vlEmpenho="2.00"/></root>'
    )
    pagamento = (
        '<root><EmpenhoPagamento idEmpenho="5" idPagamento="1" vlOperacao="1.00"/>'
        '<EmpenhoPagamento idEmpenho="6" idPagamento="2" vlOperacao="2.00"/></root>'
    )
    xmls = _xmls(
        tce_pr.regravar(
            _zip(
                {
                    "2025_411370_Empenho_1.xml": pj.encode(),
                    "2025_411370_Empenho_2.xml": pf.encode(),
                    "2025_411370_EmpenhoPagamento_1.xml": pagamento.encode(),
                }
            )
        )
    )
    assert set(xmls) == {
        "2025_411370_Empenho_1.xml",
        "2025_411370_Empenho_2.xml",
        "2025_411370_EmpenhoPagamento_1.xml",
    }
    assert re.findall(
        r'idPagamento="(\d+)"', xmls["2025_411370_EmpenhoPagamento_1.xml"]
    ) == ["2"]
