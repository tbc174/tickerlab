"""A seção D2 da ficha (ADR 0103): registros de insolvência e situação especial, só fatos.

A CVM (IPE) e a Receita (cadastro do CNPJ) dizem; a ficha copia com a data do fato, a data em que ficou
público, o veículo e o link. Não avalia, não dá nota, não olha o futuro, não cita pessoa. Sem registro,
diz "sem registro" com o dia da consulta; o que não leu, diz que não leu.
"""

import re
from pathlib import Path

import pandas as pd
import pytest

from base import contestacoes, dossie
from base.contrapartes import cafe
from src import dossie as dossie_do_app
from src.relatorio_empresa import ORDEM_DAS_SECOES

D = pd.Timestamp
HOJE = D("2026-10-22")
RAIZ = "02429144"
FRASE_FIXA = "a falta de registro nas fontes lidas não prova que não exista"
# a lista única da ADR 0103 (item 7): a do café mais a da 0085
VEDADAS = (
    *cafe.VEDADAS,
    "fraudador",
    "corrupção",
    "cartel",
    "conluio",
    "laranja",
    "superfaturamento",
    "direcionamento",
    "suspeito",
)
JULGAMENTOS = ("avaliamos", "classificamos", "nota ", "risco", "sinal")


def _cvm(*linhas: dict) -> pd.DataFrame:
    base = {
        "cnpj": "02.429.144/0001-93",
        "rotulo": "recuperacao_judicial",
        "evento": "recuperacao_judicial",
        "protocolo": "P1",
        "versao": 1,
        "referencia": D("2025-03-10"),
        "conhecido_em": D("2025-03-12"),
        "link": "https://www.rad.cvm.gov.br/doc/1",
        "evidencia": "categoria_ipe",
    }
    return pd.DataFrame([{**base, **linha} for linha in linhas or ({},)])


def _receita(*linhas: dict) -> pd.DataFrame:
    base = {
        "cnpj": "02429144000193",
        "cnpj_basico": RAIZ,
        "matriz": True,
        "situacao_especial": "FALIDO",
        "rotulo": "falencia",
        "data_situacao_especial": D("2025-06-01"),
        "mes_do_retrato": "2025-07",
        "disponivel_em": D("2025-07-31"),
    }
    return pd.DataFrame([{**base, **linha} for linha in linhas or ({},)])


def _contestacao(**linha: object) -> pd.DataFrame:
    base = {
        "registro": "recuperacao_judicial",
        "aconteceu_em": pd.NaT,
        "recebida_em": D("2026-10-20"),
        "texto": "A empresa informa que o pedido foi extinto em 2026.",
    }
    return pd.DataFrame([{**base, **linha}])


SEM_CONTESTACAO = contestacoes.vazia()
SEM_RECEITA = _receita().iloc[0:0]


def _secao(cvm=None, receita=None, contestadas=SEM_CONTESTACAO, hoje=HOJE) -> dict:
    cvm = _cvm() if cvm is None else cvm
    receita = _receita() if receita is None else receita
    secao = dossie.secao_insolvencia(cvm, receita, contestadas, hoje)
    assert secao is not None
    return secao


def _linhas(secao: dict) -> list[dict]:
    return secao["tabelas"].get("registros_de_insolvencia", [])


def _textos(secao: dict) -> str:
    return " ".join(secao["paragrafos"])


# --- a regra de mostrar ---------------------------------------------------------------------------


@pytest.mark.parametrize("tabela", ["insolvencia", "cnpj_situacao_especial"])
def test_a_d2_libera_so_as_duas_tabelas(tabela: str) -> None:
    assert dossie.pode_mostrar(tabela)


@pytest.mark.parametrize("tabela", ["pgfn_divida", "rotulos_atraso"])
def test_a_divida_ativa_e_o_rotulo_de_atraso_seguem_fora(tabela: str) -> None:
    """P-44: a ADR 0103 (D2) só desbloqueia a insolvência e a situação especial."""
    assert not dossie.pode_mostrar(tabela)
    assert tabela in dossie.TABELAS_PROIBIDAS


def test_a_secao_esta_registrada_com_as_duas_tabelas() -> None:
    registrada = next(s for s in dossie.SECOES if s.chave == "insolvencia")
    assert registrada.tabelas == ("insolvencia", "cnpj_situacao_especial")
    assert registrada.titulo == "Registros de insolvência e situação especial"
    dossie.exigir_que_pode_mostrar(registrada.tabelas)
    assert dossie.fontes_das_tabelas(registrada.tabelas)


def test_a_secao_entra_depois_dos_negocios_no_molde_a() -> None:
    ordem = list(ORDEM_DAS_SECOES)
    assert ordem.index("insolvencia") == ordem.index("negocios") + 1
    assert ordem.index("insolvencia") < ordem.index("notas_classicas")


def test_a_tabela_tem_colunas_e_titulo_declarados() -> None:
    colunas = dossie_do_app.colunas_da_tabela("registros_de_insolvencia")
    assert colunas is not None
    nomes = {coluna for coluna, _, _ in colunas}
    assert nomes == {
        "aconteceu_em",
        "publico_em",
        "registro",
        "veiculo",
        "situacao",
        "contestacao",
    }
    assert "link" not in nomes  # o link vai ao lado, como nas outras tabelas
    assert dossie_do_app.titulo_da_tabela("registros_de_insolvencia")


# --- o fato ----------------------------------------------------------------------------------------


def test_fato_da_cvm_traz_data_do_fato_data_publica_veiculo_e_link() -> None:
    [linha] = _linhas(_secao(receita=_receita().iloc[0:0]))
    assert linha["aconteceu_em"] == "2025-03-10"
    assert linha["publico_em"] == "2025-03-12"
    assert linha["registro"] == "Recuperação judicial"
    assert linha["veiculo"] == "CVM (IPE)"
    assert linha["link"] == "https://www.rad.cvm.gov.br/doc/1"


def test_fato_da_receita_traz_data_veiculo_e_o_endereco_do_cadastro() -> None:
    [linha] = _linhas(_secao(cvm=_cvm().iloc[0:0]))
    assert linha["aconteceu_em"] == "2025-06-01"
    assert linha["publico_em"] == "2025-07-31"
    assert linha["registro"] == "Falência"
    assert linha["veiculo"] == "Receita Federal (cadastro aberto do CNPJ)"
    assert linha["link"].startswith("https://")


def test_filiais_e_meses_do_mesmo_fato_contam_uma_vez_na_primeira_data_publica() -> (
    None
):
    receita = _receita(
        {},
        {"matriz": False, "cnpj": "02429144000274"},
        {"mes_do_retrato": "2025-08", "disponivel_em": D("2025-08-31")},
    )
    [linha] = _linhas(_secao(cvm=_cvm().iloc[0:0], receita=receita))
    assert linha["publico_em"] == "2025-07-31"


def test_reapresentacao_conta_uma_vez_com_a_data_da_primeira_versao() -> None:
    cvm = _cvm({}, {"versao": 2, "conhecido_em": D("2025-04-01")})
    [linha] = _linhas(_secao(cvm=cvm, receita=_receita().iloc[0:0]))
    assert linha["publico_em"] == "2025-03-12"


def test_os_fatos_vem_do_mais_novo_para_o_mais_antigo() -> None:
    cvm = _cvm(
        {}, {"protocolo": "P2", "rotulo": "falencia", "conhecido_em": D("2026-01-05")}
    )
    linhas = _linhas(_secao(cvm=cvm, receita=_receita().iloc[0:0]))
    assert [x["registro"] for x in linhas] == ["Falência", "Recuperação judicial"]


def test_exposicao_a_terceiro_e_situacao_sem_rotulo_ficam_de_fora() -> None:
    """O documento que fala de outra empresa não é fato da companhia; espólio e afins não têm rótulo."""
    cvm = _cvm({"rotulo": "exposicao_a_terceiro"})
    receita = _receita({"rotulo": None, "situacao_especial": "ESPOLIO"})
    secao = _secao(cvm=cvm, receita=receita)
    assert _linhas(secao) == []
    assert "Sem registro" in _textos(secao)


# --- sem olhar o futuro ----------------------------------------------------------------------------


def test_fato_publico_depois_do_dia_da_ficha_nao_aparece() -> None:
    cvm = _cvm({"conhecido_em": HOJE + pd.Timedelta(days=1)})
    receita = _receita({"disponivel_em": HOJE + pd.Timedelta(days=1)})
    assert _linhas(_secao(cvm=cvm, receita=receita)) == []


def test_fato_publico_no_proprio_dia_da_ficha_aparece() -> None:
    cvm = _cvm({"conhecido_em": HOJE})
    assert len(_linhas(_secao(cvm=cvm, receita=_receita().iloc[0:0]))) == 1


def test_cortar_o_futuro_nao_muda_o_passado() -> None:
    futuro_cvm = _cvm(
        {"protocolo": "F", "rotulo": "falencia", "conhecido_em": D("2027-01-01")}
    )
    futuro_receita = _receita(
        {"data_situacao_especial": D("2026-12-01"), "disponivel_em": D("2026-12-31")}
    )
    sem = _secao()
    com = _secao(
        cvm=pd.concat([_cvm(), futuro_cvm], ignore_index=True),
        receita=pd.concat([_receita(), futuro_receita], ignore_index=True),
    )
    assert com == sem


# --- sem achado e o que não sabemos ----------------------------------------------------------------


def test_sem_registro_diz_sem_registro_com_o_dia_da_consulta() -> None:
    secao = _secao(cvm=_cvm().iloc[0:0], receita=_receita().iloc[0:0])
    texto = _textos(secao)
    assert _linhas(secao) == []
    assert texto.count("Sem registro") == 2  # uma frase por fonte lida
    assert texto.count("22/10/2026") >= 2
    assert "CVM" in texto and "Receita" in texto


def test_so_a_fonte_sem_achado_diz_sem_registro() -> None:
    secao = _secao(cvm=_cvm().iloc[0:0])
    texto = _textos(secao)
    assert len(_linhas(secao)) == 1
    assert texto.count("Sem registro") == 1
    assert "CVM" in texto.split("Sem registro")[1]


def test_fonte_que_a_base_nao_leu_nao_vira_sem_registro() -> None:
    secao = dossie.secao_insolvencia(_cvm().iloc[0:0], None, SEM_CONTESTACAO, HOJE)
    assert secao is not None
    texto = _textos(secao)
    assert texto.count("Sem registro") == 1
    assert "não consultamos" in texto.lower()


def test_sem_nenhuma_das_duas_fontes_nao_ha_secao() -> None:
    assert dossie.secao_insolvencia(None, None, SEM_CONTESTACAO, HOJE) is None


@pytest.mark.parametrize("com_fato", [True, False])
def test_a_frase_fixa_do_que_nao_sabemos_vem_em_toda_secao(com_fato: bool) -> None:
    secao = (
        _secao()
        if com_fato
        else _secao(cvm=_cvm().iloc[0:0], receita=_receita().iloc[0:0])
    )
    assert FRASE_FIXA in _textos(secao)
    assert "O que não sabemos" in _textos(secao)


# --- só fatos ---------------------------------------------------------------------------------------


def test_nenhum_texto_da_secao_julga_cita_palavra_vedada_ou_pessoa() -> None:
    secoes = [
        _secao(),
        _secao(cvm=_cvm().iloc[0:0], receita=_receita().iloc[0:0]),
        _secao(contestadas=_contestacao()),
    ]
    for secao in secoes:
        escrito = (_textos(secao) + " " + str(secao["titulo"])).lower()
        assert cafe.palavras_vedadas_em(escrito) == []
        for palavra in (*VEDADAS, *JULGAMENTOS):
            assert not re.search(rf"\b{re.escape(palavra.strip())}\b", escrito), palavra
        ficha = dossie.montar_ficha(
            "02429144000193", "CPFL", [secao], "2026-10-22T07:00:00"
        )
        dossie.conferir_sem_pessoas(ficha, set())
        assert dossie.COLUNAS_DE_PESSOA.isdisjoint(
            _linhas(secao)[0] if _linhas(secao) else {}
        )


def test_a_secao_nao_tem_itens_nem_nota() -> None:
    secao = _secao()
    assert secao["itens"] == []
    assert secao["chave"] == "insolvencia"
    assert secao["titulo"] == "Registros de insolvência e situação especial"
    assert secao["fontes"]


def test_as_fontes_da_secao_vem_das_tabelas_lidas() -> None:
    assert _secao()["fontes"] == dossie.fontes_das_tabelas(
        ("insolvencia", "cnpj_situacao_especial")
    )


# --- o direito de resposta (ponto 9): fato contestado ----------------------------------------------


def test_fato_sem_contestacao_nao_tem_situacao() -> None:
    [linha] = _linhas(_secao(receita=_receita().iloc[0:0]))
    assert linha.get("situacao") is None and linha.get("contestacao") is None


def test_fato_contestado_ganha_situacao_contestada_e_mostra_o_texto_ao_lado() -> None:
    secao = _secao(receita=_receita().iloc[0:0], contestadas=_contestacao())
    [linha] = _linhas(secao)
    assert linha["situacao"] == "contestada"
    assert linha["contestacao"] == "A empresa informa que o pedido foi extinto em 2026."
    assert linha["contestada_em"] == "2026-10-20"
    assert linha["registro"] == "Recuperação judicial"  # o fato continua na ficha


def test_contestacao_com_data_do_fato_so_vale_para_aquele_fato() -> None:
    outra_data = _contestacao(aconteceu_em=D("2020-01-01"))
    mesma_data = _contestacao(aconteceu_em=D("2025-03-10"))
    assert (
        _linhas(_secao(receita=SEM_RECEITA, contestadas=outra_data))[0].get("situacao")
        is None
    )
    assert (
        _linhas(_secao(receita=SEM_RECEITA, contestadas=mesma_data))[0]["situacao"]
        == "contestada"
    )


def test_contestacao_de_outro_registro_nao_conta() -> None:
    outra = _contestacao(registro="falencia")
    linhas = _linhas(_secao(receita=_receita().iloc[0:0], contestadas=outra))
    assert linhas[0].get("situacao") is None


def test_contestacao_recebida_depois_do_dia_da_ficha_nao_conta() -> None:
    futura = _contestacao(recebida_em=HOJE + pd.Timedelta(days=1))
    [linha] = _linhas(_secao(receita=_receita().iloc[0:0], contestadas=futura))
    assert linha.get("situacao") is None


def test_vale_a_contestacao_mais_nova() -> None:
    duas = pd.concat(
        [
            _contestacao(),
            _contestacao(recebida_em=D("2026-10-21"), texto="Segunda versão."),
        ],
        ignore_index=True,
    )
    [linha] = _linhas(_secao(receita=_receita().iloc[0:0], contestadas=duas))
    assert linha["contestacao"] == "Segunda versão."


def test_a_contestacao_tambem_vale_para_o_fato_da_receita() -> None:
    contestada = _contestacao(registro="falencia")
    [linha] = _linhas(_secao(cvm=_cvm().iloc[0:0], contestadas=contestada))
    assert linha["situacao"] == "contestada"


# --- o arquivo das contestações ---------------------------------------------------------------------


def _gravar(pasta: Path, *linhas: str) -> Path:
    caminho = pasta / "contestacoes.csv"
    cabecalho = ",".join(contestacoes.COLUNAS)
    caminho.write_text("\n".join([cabecalho, *linhas]) + "\n", encoding="utf-8")
    return caminho


def test_o_arquivo_versionado_nasce_so_com_o_cabecalho() -> None:
    lidas = contestacoes.ler()
    assert lidas.empty
    assert list(lidas.columns) == [
        "cnpj",
        "registro",
        "aconteceu_em",
        "recebida_em",
        "texto",
    ]


def test_le_a_contestacao_com_cnpj_so_em_digitos(tmp_path: Path) -> None:
    caminho = _gravar(
        tmp_path,
        '02.429.144/0001-93,recuperacao_judicial,,2026-10-20,"Pedido extinto, conforme o diário."',
    )
    [linha] = contestacoes.ler(caminho).to_dict("records")
    assert linha["cnpj"] == "02429144000193"
    assert linha["recebida_em"] == D("2026-10-20")
    assert pd.isna(linha["aconteceu_em"])
    assert linha["texto"] == "Pedido extinto, conforme o diário."


def test_rejeita_registro_que_a_ficha_nao_conhece(tmp_path: Path) -> None:
    caminho = _gravar(tmp_path, "02.429.144/0001-93,inventado,,2026-10-20,Texto.")
    with pytest.raises(ValueError, match="registro"):
        contestacoes.ler(caminho)


def test_rejeita_texto_com_palavra_vedada(tmp_path: Path) -> None:
    caminho = _gravar(
        tmp_path, "02.429.144/0001-93,falencia,,2026-10-20,Isso foi uma fraude."
    )
    with pytest.raises(ValueError, match="vedada"):
        contestacoes.ler(caminho)


def test_rejeita_cnpj_invalido_e_data_invalida(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="CNPJ"):
        contestacoes.ler(_gravar(tmp_path, "123,falencia,,2026-10-20,Texto."))
    with pytest.raises(ValueError, match="data"):
        contestacoes.ler(_gravar(tmp_path, "02.429.144/0001-93,falencia,,ontem,Texto."))


def test_so_as_contestacoes_da_empresa_chegam_a_ficha() -> None:
    todas = pd.concat(
        [
            _contestacao().assign(cnpj="02429144000193"),
            _contestacao().assign(cnpj="33333333000133"),
        ],
        ignore_index=True,
    )
    da_empresa = contestacoes.da_empresa(todas, RAIZ)
    assert list(da_empresa["cnpj"]) == ["02429144000193"]


# --- a tela --------------------------------------------------------------------------------------


def _tela_da_secao(caminho: str) -> None:
    from pathlib import Path

    from src import dossie as dossie_da_tela
    from telas.research.relatorio_empresa import _mostrar_secao

    ficha = dossie_da_tela.ler_ficha(Path(caminho))
    assert ficha is not None
    for secao in dossie_da_tela.secoes_da_ficha(ficha):
        _mostrar_secao(secao)


def test_a_tela_mostra_o_fato_contestado_com_a_contestacao_ao_lado(
    tmp_path: Path,
) -> None:
    import json

    from streamlit.testing.v1 import AppTest

    secao = _secao(contestadas=_contestacao())
    ficha = dossie.montar_ficha(
        "02429144000193", "CPFL", [secao], "2026-10-22T07:00:00-03:00"
    )
    caminho = tmp_path / "02429144000193.json"
    caminho.write_text(json.dumps(ficha), encoding="utf-8")

    app = AppTest.from_function(_tela_da_secao, args=(str(caminho),)).run()

    assert not app.exception
    assert [s.value for s in app.subheader] == [
        "Registros de insolvência e situação especial"
    ]
    textos = " ".join(m.value for m in app.markdown)
    assert FRASE_FIXA in textos
    tabela = app.dataframe[0].value
    assert "Contestação da empresa" in tabela.columns
    assert "contestada" in tabela["Situação"].tolist()
    assert any("extinto em 2026" in str(c) for c in tabela["Contestação da empresa"])
