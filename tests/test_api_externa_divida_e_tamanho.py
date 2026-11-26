"""A dívida de mercado na ficha de crédito e os sinais de tamanho no perfil (linhas 1126 e 1130 da fila).

Base de mentira: uma empresa inventada (cedente de um CRA e de um FIDC, devedora de um CRI, prestadora com acessos
na Anatel) e linhas publicadas depois do dia pedido, que não podem aparecer. O informe do FIDC traz também uma
cedente com CPF de teste: ele nunca sai. O bloco da dívida liga só pelo portão (as tabelas de securitização não
têm a prontidão do D10 hoje), e o texto da dívida (os limites) sai junto com o bloco, nunca sozinho.
"""

import dataclasses
from datetime import UTC, date, datetime

import pandas as pd
import pytest

from base import cnpj as cnpj_
from base import porta as porta_
from base import prontidao
from base.porta import Porta
from base.prontidao import Prontidao, Prova
from src import portao_externo as portao
from src.api_externa import rotas
from src.api_externa.conjuntos import credito, divida_de_mercado, sinais_de_tamanho
from src.api_externa.conjuntos import ficha as ficha_
from src.api_externa.nomes import NOMES_DE_FORA, traduzir_chaves
from src.portao_externo import DIREITOS_DA_API_EXTERNA, PALAVRAS_QUE_NUNCA_SAEM
from tests import ajudantes_da_api_externa as aj
from tests.ajudantes_de_cpf import CPF_DE_TESTE, formatado
from tests.test_credito_sinais import _cadastral, _entidade, _fidc

EMPRESA = "11222333000181"  # inventada
SECURITIZADORA = "33.000.167/0001-01"
FUNDO = "13.416.131/0001-04"
ADMINISTRADORA = "30.178.001/0001-91"
DIA = date(2026, 11, 7)
DEPOIS = "2026-11-20"  # publicado depois do dia pedido: nunca sai
AGORA = datetime(2026, 11, 10, 12, tzinfo=UTC)


def _ts(dia: str) -> pd.Timestamp:
    return pd.Timestamp(dia)


def _papel(
    competencia, codigo, produto, papel, percentual, publico, versao=1, cnpj=EMPRESA
) -> dict:
    return {"competencia": _ts(competencia), "cnpj_securitizadora": SECURITIZADORA,
            "codigo_certificado": codigo, "produto": produto, "versao": versao, "papel": papel,
            "cnpj": cnpj_.formatar(cnpj), "percentual": percentual, "disponivel_em": _ts(publico)}  # fmt: skip


def _certificado(competencia, codigo, produto, publico) -> dict:
    return {"competencia": _ts(competencia), "cnpj_securitizadora": SECURITIZADORA,
            "codigo_certificado": codigo, "produto": produto, "versao": 1,
            "nome_securitizadora": "SECURITIZADORA INVENTADA S.A.", "numero_emissao": 1,
            "data_emissao": _ts("2024-03-01"), "tipo_lastro": "x", "disponivel_em": _ts(publico)}  # fmt: skip


def _informe_do_fidc(competencia, publico, carteira, inadimplente) -> dict:
    linha = _fidc(FUNDO, competencia, publico,
                  [("TAB_I2A12", 1, cnpj_.formatar(EMPRESA), "35.5"),
                   ("TAB_I2A12", 2, formatado(CPF_DE_TESTE), "10.0")],
                  carteira, inadimplente)  # fmt: skip
    return linha | {"DENOM_SOCIAL": "FIDC INVENTADO", "ADMIN": "ADMINISTRADORA INVENTADA DTVM",
                    "CNPJ_ADMIN": ADMINISTRADORA, "TAB_I2B3_VL_CRED_INAD": "1000000.00"}  # fmt: skip


def _anatel(competencia, servico, acessos, visto, recorte="completo") -> dict:
    return {"competencia": _ts(competencia), "servico": servico, "recorte": recorte, "cnpj": EMPRESA,
            "uf": "SP", "acessos": acessos, "visto_em": _ts(visto), "disponivel_em": _ts(visto)}  # fmt: skip


def _empresas_pj(mes, publico, capital, ativos) -> dict:
    return {"cnpj_basico": EMPRESA[:8], "razao_social": "EMPRESA INVENTADA LTDA", "natureza_juridica": "2062",
            "porte": "05", "capital_social": capital, "n_estabelecimentos": ativos, "mes_do_retrato": mes,
            "disponivel_em": _ts(publico)}  # fmt: skip


def _extras() -> dict[str, pd.DataFrame]:
    entidade, identificador = _entidade(EMPRESA, False)
    return {
        "entidades": pd.DataFrame([entidade]),
        "identificadores": pd.DataFrame([identificador]),
        "cnpj_situacao_cadastral": pd.DataFrame(
            [_cadastral(EMPRESA, "2026-09", "2026-09-30", "02")]
        ),
        "securitizacao_cedente_devedor": pd.DataFrame(
            [
                _papel("2026-08-01", "CRA001", "CRA", "cedente", 0.4, "2026-09-10"),
                _papel("2026-09-01", "CRA001", "CRA", "cedente", 0.5, "2026-10-10"),
                _papel(
                    "2026-09-01",
                    "CRA001",
                    "CRA",
                    "cedente",
                    0.6,
                    "2026-10-12",
                    versao=2,
                ),
                _papel("2025-01-01", "CRI009", "CRI", "devedor", 1.0, "2025-02-10"),
                _papel("2026-10-01", "CRA777", "CRA", "cedente", 0.9, DEPOIS),
            ]
        ),
        "securitizacao_certificados": pd.DataFrame(
            [
                _certificado("2026-09-01", "CRA001", "CRA", "2026-10-10"),
                _certificado("2025-01-01", "CRI009", "CRI", "2025-02-10"),
                _certificado("2026-10-01", "CRA777", "CRA", DEPOIS),
            ]
        ),
        "fidc_informe": pd.DataFrame(
            [
                _informe_do_fidc(
                    "2026-08-01", "2026-09-15", "50000000.00", "2000000.00"
                ),
                _informe_do_fidc(
                    "2026-09-01", "2026-10-15", "40000000.00", "45000000.00"
                ),
                _informe_do_fidc("2026-10-01", DEPOIS, "1.00", "1.00"),
            ]
        ),
        "anatel_acessos": pd.DataFrame(
            [
                _anatel("2026-06-01", "banda_larga_fixa", 50000, "2026-08-01"),
                _anatel("2026-07-01", "banda_larga_fixa", 54000, "2026-09-01"),
                _anatel(
                    "2026-07-01", "banda_larga_fixa", 54800, "2026-10-01"
                ),  # a revisão vale
                _anatel("2026-07-01", "telefonia_movel", 300, "2026-09-01"),
                _anatel(
                    "2026-07-01",
                    "telefonia_movel",
                    300,
                    "2026-09-01",
                    recorte="modalidade",
                ),  # outra visão
                _anatel("2026-08-01", "banda_larga_fixa", 99999, DEPOIS),
            ]
        ),
        "cnpj_empresas_pj": pd.DataFrame(
            [
                _empresas_pj("2026-09", "2026-09-30", 70000.0, 1),
                _empresas_pj("2026-10", "2026-10-31", 80000.0, 3),
                _empresas_pj("2026-11", DEPOIS, 999.0, 9),
            ]
        ),
    }


@pytest.fixture(autouse=True)
def _sem_leitura_por_faixa(monkeypatch):
    # a leitura por faixa de arquivo (`base/porta`, testada em `test_porta_pela_faixa`) só vale para arquivos de
    # verdade; aqui a `cnpj_empresas_pj` é uma tabela de mentira (`extras`) e vai pela view
    monkeypatch.setattr(porta_, "POR_FAIXA_DE_ARQUIVO", {})


def _porta(pasta, extras=None) -> Porta:
    return Porta(pasta, arquivos={}, conferidas={}, extras=extras or _extras())


def _divida(pasta, permitido=None, dia=DIA, extras=None, linhas_maximas=None):
    with _porta(pasta, extras) as porta:
        return divida_de_mercado.LeitorDaDivida(
            porta, permitido or (lambda *_: True), linhas_maximas
        ).bloco(EMPRESA, dia)


def _tamanho(pasta, permitido=None, dia=DIA):
    with _porta(pasta) as porta:
        return sinais_de_tamanho.LeitorDeTamanho(
            porta, permitido or (lambda *_: True)
        ).bloco(EMPRESA, dia)


# ---------------------------------------------------------------- a dívida de mercado


def test_certificados_da_empresa_por_produto_com_a_versao_mais_nova(tmp_path):
    bloco, fontes = _divida(tmp_path)
    cra = bloco["certificados_cra"]
    assert cra["fonte"] == "cvm-cra" and cra["publico_em"] == "2026-10-12"
    (certificado,) = cra["valor"]
    assert certificado["codigo_certificado"] == "CRA001"
    assert certificado["securitizadora"] == "SECURITIZADORA INVENTADA S.A."
    assert certificado["papeis"] == [{"papel": "cedente", "percentual": 0.6}]
    assert certificado["primeiro_mes_com_a_empresa"] == "2026-08"
    assert certificado["ultimo_mes_com_a_empresa"] == "2026-09"
    assert certificado["meses"] == 2
    assert certificado["ultimo_informe_do_certificado"] == "2026-09"
    (cri,) = bloco["certificados_cri"]["valor"]
    assert cri["papeis"] == [{"papel": "devedor", "percentual": 1.0}]
    assert cri["ultimo_informe_do_certificado"] == "2025-01"
    assert (
        "certificados_ots" not in bloco
    )  # nenhum OTS: a lista vazia não sai por produto
    assert {"cvm-cra", "cvm-cri", "cvm-fidc"} <= fontes


def test_o_ultimo_informe_e_o_do_proprio_certificado_nao_o_da_securitizadora(tmp_path):
    # revisão cruzada (P1): outro certificado da mesma securitizadora, informado depois, não diz nada do CRA001;
    # e o CRA001 informado em outubro sem a empresa mostra que ele seguiu no informe sem ela
    extras = _extras()
    extras["securitizacao_certificados"] = pd.concat([
        extras["securitizacao_certificados"],
        pd.DataFrame([
            _certificado("2026-10-01", "CRA002", "CRA", "2026-10-20"),
            _certificado("2026-10-01", "CRA001", "CRA", "2026-10-25"),
        ]),
    ])  # fmt: skip
    bloco, _ = _divida(tmp_path, extras=extras)
    (cra,) = bloco["certificados_cra"]["valor"]
    assert cra["ultimo_mes_com_a_empresa"] == "2026-09"
    assert cra["ultimo_informe_do_certificado"] == "2026-10"
    # achado P1 do Revisor: o quadro geral de outubro (sem a empresa) foi publicado depois das linhas dela; o
    # item e o envelope levam o dia da publicação mais nova que usaram
    assert cra["publico_em"] == "2026-10-25"
    assert bloco["certificados_cra"]["publico_em"] == "2026-10-25"
    (cri,) = bloco["certificados_cri"]["valor"]
    assert cri["ultimo_informe_do_certificado"] == "2025-01"
    assert "no_ultimo_informe" not in str(bloco)


def test_informe_de_produto_negado_nao_entra_no_certificado_liberado(tmp_path):
    # achado P0 do Revisor: com o CRA liberado e o CRI negado, um informe de CRI (mesma securitizadora, mesmo
    # código, publicado depois) não muda nada no item do CRA
    extras = _extras()
    extras["securitizacao_certificados"] = pd.concat([
        extras["securitizacao_certificados"],
        pd.DataFrame([_certificado("2026-10-01", "CRA001", "CRI", "2026-10-30")]),
    ])  # fmt: skip
    so_o_cra, _ = _divida(
        tmp_path, permitido=lambda fonte, *_: fonte == "cvm-cra", extras=extras
    )
    assert set(so_o_cra) == {"certificados_cra"}
    (cra,) = so_o_cra["certificados_cra"]["valor"]
    assert cra["ultimo_informe_do_certificado"] == "2026-09"
    assert cra["publico_em"] == "2026-10-12"


def test_as_listas_respeitam_o_teto_de_linhas_e_contam_os_itens(tmp_path):
    # revisão cruzada (P1): a lista sem teto estourava o plano e o corte da análise
    bloco, _ = _divida(tmp_path, linhas_maximas=1)
    assert len(bloco["certificados_cra"]["valor"]) == 1
    assert "cortada" not in bloco["certificados_cra"]
    assert bloco["certificados_cri"]["valor"] == []
    assert bloco["certificados_cri"]["cortada"] is True
    assert bloco["lista_dos_fundos_em_que_cede"]["cortada"] is True
    assert divida_de_mercado.itens(bloco) == 1
    inteiro, _ = _divida(tmp_path)
    assert divida_de_mercado.itens(inteiro) == 3
    with _porta(tmp_path) as porta:
        servida = credito.LeitorDeCredito(porta, lambda *_: True, 2).ficha(EMPRESA, DIA)
    assert servida is not None and servida.linhas == 1 + 2


def test_fundo_em_que_cede_com_a_instituicao_e_o_alerta_sem_o_documento_das_outras(
    tmp_path,
):
    bloco, _ = _divida(tmp_path)
    fundos = bloco["lista_dos_fundos_em_que_cede"]
    assert fundos["fonte"] == "cvm-fidc" and fundos["publico_em"] == "2026-10-15"
    (fundo,) = fundos["valor"]
    assert fundo["cnpj_fundo"] == FUNDO
    assert fundo["nome_do_fundo"] == "FIDC INVENTADO"
    assert fundo["instituicao_administradora"] == "ADMINISTRADORA INVENTADA DTVM"
    assert fundo["competencia"] == "2026-09"
    assert fundo["participacao_como_cedente"] == pytest.approx(0.355)
    assert fundo["carteira_do_fundo"] == 40_000_000.0
    assert (
        fundo["credito_inadimplente"] == 46_000_000.0
    )  # com e sem aquisição substancial dos riscos
    assert fundo["inadimplente_sobre_carteira"] == pytest.approx(1.15)
    texto = str(bloco)
    assert CPF_DE_TESTE not in texto and formatado(CPF_DE_TESTE) not in texto


@pytest.mark.parametrize(
    "dia", [DIA, date(2026, 9, 20), date(2025, 6, 1), date(2024, 1, 1)]
)
def test_nada_publicado_depois_do_dia_pedido(tmp_path, dia):
    bloco, _ = _divida(tmp_path, dia=dia)
    for envelope in bloco.values():
        assert envelope["publico_em"] <= dia.isoformat()
        for item in envelope["valor"]:
            assert item["publico_em"] <= dia.isoformat()
    assert "CRA777" not in str(bloco)


def test_o_portao_julga_cada_lista_pela_fonte_dela_como_derivada(tmp_path):
    perguntas = []

    def so_o_cri(fonte, campo, derivado):
        perguntas.append((fonte, campo, derivado))
        return fonte == "cvm-cri"

    bloco, fontes = _divida(tmp_path, permitido=so_o_cri)
    assert set(bloco) == {"certificados_cri"}
    assert fontes == {"cvm-cri"}
    for fonte, campo, derivado in perguntas:
        assert divida_de_mercado.CAMPOS[campo].fonte == fonte
        assert derivado is True


def test_portao_fechado_nada_sai(tmp_path):
    assert _divida(tmp_path, permitido=lambda *_: False) == ({}, set())


def test_sem_as_tabelas_nada_sai(tmp_path):
    extras = {
        k: v
        for k, v in _extras().items()
        if not k.startswith(("securitizacao", "fidc"))
    }
    assert _divida(tmp_path, extras=extras) == ({}, set())


# ---------------------------------------------------------------- os sinais de tamanho


def test_acessos_da_anatel_no_ultimo_mes_publico_somados_por_servico(tmp_path):
    bloco, fontes = _tamanho(tmp_path)
    acessos = bloco["acessos_na_anatel"]
    assert (
        acessos["fonte"] == "anatel-acessos" and acessos["publico_em"] == "2026-10-01"
    )
    assert acessos["valor"] == {
        "competencia": "2026-07",
        "acessos_por_servico": [
            {"servico": "banda_larga_fixa", "acessos": 54800},
            {"servico": "telefonia_movel", "acessos": 300},
        ],
        "acessos_total": 55100,
    }
    assert {"anatel-acessos", "rfb-cnpj"} <= fontes


def test_capital_e_estabelecimentos_do_retrato_mais_novo_publico_sem_conta_de_receita(
    tmp_path,
):
    bloco, _ = _tamanho(tmp_path)
    assert bloco["capital_social"]["valor"] == 80000.0
    assert bloco["capital_social"]["publico_em"] == "2026-10-31"
    assert bloco["n_estabelecimentos"]["valor"] == 3
    texto = str(bloco).lower()
    assert "receita_estimada" not in texto and "faturamento" not in texto


def test_o_aviso_do_capital_vai_nos_limites_do_perfil_so_com_o_capital():
    assert sinais_de_tamanho.AVISO_DO_CAPITAL in sinais_de_tamanho.limites(
        {"capital_social": {}}
    )
    assert sinais_de_tamanho.AVISO_DO_CAPITAL not in sinais_de_tamanho.limites(
        {"n_estabelecimentos": {}}
    )


def test_o_perfil_traz_os_sinais_e_o_aviso_do_capital(tmp_path):
    with _porta(tmp_path) as porta:
        servida = ficha_.LeitorDeFicha(porta, lambda *_: True).ficha(EMPRESA, DIA)
    assert servida is not None
    sinais = servida.corpo["sinais_de_tamanho"]
    assert sinais["n_estabelecimentos"]["valor"] == 3
    assert sinais["acessos_na_anatel"]["valor"]["acessos_total"] == 55100
    assert sinais_de_tamanho.AVISO_DO_CAPITAL in servida.corpo["limites"]
    assert "anatel-acessos" in servida.fontes


def test_o_perfil_sem_os_sinais_liberados_fica_como_era(tmp_path):
    def sem_os_sinais(_fonte, campo, _derivado):
        return campo not in sinais_de_tamanho.CAMPOS

    with _porta(tmp_path) as porta:
        servida = ficha_.LeitorDeFicha(porta, sem_os_sinais).ficha(EMPRESA, DIA)
    assert servida is not None
    assert "sinais_de_tamanho" not in servida.corpo
    assert sinais_de_tamanho.AVISO_DO_CAPITAL not in servida.corpo["limites"]


def test_retrato_sem_as_colunas_novas_nao_derruba_o_perfil(tmp_path):
    # regressão do CI: a `cnpj_empresas_pj` anterior à versão 1.1.0 não tem capital nem estabelecimentos
    extras = _extras()
    extras["cnpj_empresas_pj"] = extras["cnpj_empresas_pj"].drop(
        columns=["capital_social", "n_estabelecimentos"]
    )
    with _porta(tmp_path, extras) as porta:
        servida = ficha_.LeitorDeFicha(porta, lambda *_: True).ficha(EMPRESA, DIA)
    assert servida is not None
    sinais = servida.corpo["sinais_de_tamanho"]
    assert set(sinais) == {"acessos_na_anatel"}
    assert sinais_de_tamanho.AVISO_DO_CAPITAL not in servida.corpo["limites"]


def test_tamanho_com_o_portao_fechado_sai_vazio(tmp_path):
    assert _tamanho(tmp_path, permitido=lambda *_: False) == ({}, set())


# ---------------------------------------------------------------- os nomes e os direitos


def test_toda_chave_nova_tem_nome_de_fora_sem_palavra_de_pessoa(tmp_path):
    divida, _ = _divida(tmp_path)
    tamanho, _ = _tamanho(tmp_path)
    traduzido = traduzir_chaves(
        {"divida_de_mercado": divida, "sinais_de_tamanho": tamanho}
    )
    assert "market_debt" in traduzido and "size_signals" in traduzido
    for chave in aj.chaves_de(traduzido):
        assert not set(chave.split("_")) & PALAVRAS_QUE_NUNCA_SAEM, chave
    assert NOMES_DE_FORA["instituicao_administradora"] == "administering_institution"


# as listas de CRA, CRI e OTS ganham linha de direito com a prontidão das tabelas de securitização, em PR próprio
# (linha 1132; Diretoria, 26/11/2026): até lá, nem o portão nem o site as anunciam
CERTIFICADOS = frozenset({"certificados_cra", "certificados_cri", "certificados_ots"})
COM_DIREITO_HOJE = {
    nome: origem
    for nome, origem in divida_de_mercado.CAMPOS.items()
    if nome not in CERTIFICADOS
}


def test_os_certificados_ainda_nao_tem_linha_de_direito():
    campos = {l.campo for l in DIREITOS_DA_API_EXTERNA}
    fontes = {l.fonte for l in DIREITOS_DA_API_EXTERNA}
    assert not CERTIFICADOS & campos
    assert not {"cvm-cra", "cvm-cri", "cvm-securitizadoras-ots"} & fontes
    assert set(divida_de_mercado.CAMPOS) == CERTIFICADOS | set(COM_DIREITO_HOJE)


def test_os_campos_novos_sao_linhas_de_direito():
    for conjunto, campos in (
        (credito.CONJUNTO, COM_DIREITO_HOJE),
        (ficha_.CONJUNTO, sinais_de_tamanho.CAMPOS),
    ):
        linhas = {
            (l.fonte, l.campo, l.tabelas)
            for l in DIREITOS_DA_API_EXTERNA
            if l.conjunto == conjunto
        }
        for campo, origem in campos.items():
            assert (origem.fonte, campo, origem.tabelas) in linhas, campo


def test_pat_e_porte_do_bndes_nao_tem_linha_de_direito():
    campos = {l.campo for l in DIREITOS_DA_API_EXTERNA}
    fontes = {
        l.fonte
        for l in DIREITOS_DA_API_EXTERNA
        if l.conjunto in (credito.CONJUNTO, ficha_.CONJUNTO)
    }
    assert not {"porte_do_bndes", "trabalhadores_do_pat"} & campos
    assert not {"mte-pat", "bndes-operacoes"} & fontes


# ---------------------------------------------------------------- a rota de crédito, nos dois estados do portão


def _linhas_dos_certificados() -> tuple[portao.LinhaDeDireito, ...]:
    """As linhas de direito que o PR da prontidão (linha 1132) vai acrescentar, só para o teste do estado ligado."""
    return tuple(
        linha
        for nome in sorted(CERTIFICADOS)
        for linha in portao._campos(
            (divida_de_mercado.CAMPOS[nome].fonte,), credito.CONJUNTO,
            divida_de_mercado.CAMPOS[nome].tabelas, (nome,), "linha de teste", portao.Finalidade.CREDITO,
        )
    )  # fmt: skip


def _regras(tabelas: set[str], com_os_certificados: bool = False) -> portao.Regras:
    prova = Prova(AGORA.date(), "conferida no teste", "teste")
    versoes = prontidao.versoes_maiores()
    vigentes = portao.regras_vigentes()
    extras = _linhas_dos_certificados() if com_os_certificados else ()
    return dataclasses.replace(
        vigentes,
        linhas=(*vigentes.linhas, *extras),
        prontidao={t: Prontidao(versoes[t], prova, prova, prova) for t in tabelas},
    )


DO_CREDITO = {origem.tabela for origem in credito.FATOS.values()}
DA_SECURITIZACAO = {"securitizacao_cedente_devedor", "securitizacao_certificados"}


def _rota(banco, monkeypatch, pasta, tabelas, com_os_certificados=False):
    ator = aj.admin(banco)
    org = aj.organizacao(banco, ator)
    chave = aj.chave(banco, ator, org)
    aj.contrato(banco, ator, org, conjunto="credit", finalidade="credito")
    monkeypatch.setattr(
        rotas, "regras_da_api", lambda: _regras(tabelas, com_os_certificados)
    )
    monkeypatch.setattr(rotas, "abrir_porta", lambda _banco: _porta(pasta))
    cliente = aj.cliente_da_api(monkeypatch, AGORA)
    return cliente.get(f"/data/v1/credit/{EMPRESA}", headers=aj.bearer(chave.valor))


def test_sem_a_prontidao_da_securitizacao_a_divida_nao_sai_nem_o_texto_dela(
    banco, monkeypatch, tmp_path
):
    corpo = _rota(banco, monkeypatch, tmp_path, {"cnpj_situacao_cadastral"}).json()
    assert "market_debt" not in corpo
    assert credito.LIMITE_DA_DIVIDA not in corpo["limits"]


def test_com_a_prontidao_mas_sem_a_linha_de_direito_os_certificados_nao_saem(
    banco, monkeypatch, tmp_path
):
    # o estado de hoje depois da prontidão e antes do PR das linhas: só a lista dos FIDC
    corpo = _rota(banco, monkeypatch, tmp_path, DO_CREDITO | DA_SECURITIZACAO).json()
    assert set(corpo["market_debt"]) == {"fidcs_as_assignor_list"}
    assert not {"cvm-cra", "cvm-cri"} & {fonte["source"] for fonte in corpo["sources"]}


def test_com_a_prontidao_a_divida_sai_em_ingles_com_o_texto(
    banco, monkeypatch, tmp_path
):
    corpo = _rota(
        banco,
        monkeypatch,
        tmp_path,
        DO_CREDITO | DA_SECURITIZACAO,
        com_os_certificados=True,
    ).json()
    divida = corpo["market_debt"]
    assert set(divida) == {
        "cra_certificates",
        "cri_certificates",
        "fidcs_as_assignor_list",
    }
    (fundo,) = divida["fidcs_as_assignor_list"]["value"]
    assert fundo["administering_institution"] == "ADMINISTRADORA INVENTADA DTVM"
    assert credito.LIMITE_DA_DIVIDA in corpo["limits"]
    fontes = {fonte["source"] for fonte in corpo["sources"]}
    assert {"cvm-cra", "cvm-cri", "cvm-fidc"} <= fontes
    assert CPF_DE_TESTE not in str(corpo) and formatado(CPF_DE_TESTE) not in str(corpo)
