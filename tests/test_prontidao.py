"""Prontidão por tabela para a API externa (ADR 0108, D10): as três provas, o prazo e o contrato."""

from datetime import date, timedelta
from pathlib import Path

import pytest

from base import prontidao
from base.dicionario import TABELAS
from base.prontidao import (
    PRAZO_DA_PROVA,
    PRONTIDAO,
    Falta,
    Prontidao,
    Prova,
    negacao_da_prontidao,
    prova_publicavel,
    versao_maior,
    versoes_maiores,
)

HOJE = date(2026, 11, 3)


def _prova(dias_atras: int = 10, **outros) -> Prova:
    base = {"data": HOJE - timedelta(days=dias_atras), "prova": "placar-2026-10-24"}
    return Prova(**(base | outros))


def _pronta(**outros) -> Prontidao:
    base = {
        "versao_maior": 2,
        "cruzada": _prova(independencia="mesmo documento, outro canal (ENET)"),
        "qualidade": _prova(),
        "dicionario": _prova(prova="revisao-do-dicionario-2026-10-20"),
    }
    return Prontidao(**(base | outros))


def _negacao(
    tabelas: tuple[str, ...] = ("dfp",),
    registro: dict[str, Prontidao] | None = None,
    versoes: dict[str, int] | None = None,
    hoje: date = HOJE,
) -> Falta | None:
    registro = {"dfp": _pronta()} if registro is None else registro
    versoes = {"dfp": 2, "cnpj": 2} if versoes is None else versoes
    return negacao_da_prontidao(tabelas, registro, versoes, hoje)


# --- o caminho que libera ---


def test_tabela_com_as_tres_provas_em_dia_libera() -> None:
    assert _negacao() is None


# --- risco 1: duas provas só, ou prova velha ---


@pytest.mark.parametrize("exigencia", ["cruzada", "qualidade", "dicionario"])
def test_falta_uma_exigencia_nega(exigencia: str) -> None:
    registro = {"dfp": _pronta(**{exigencia: None})}
    assert _negacao(registro=registro) is Falta.SEM_PRONTIDAO


@pytest.mark.parametrize("exigencia", ["cruzada", "qualidade", "dicionario"])
def test_prova_em_branco_nao_conta(exigencia: str) -> None:
    registro = {"dfp": _pronta(**{exigencia: _prova(prova=" ", independencia="x")})}
    assert _negacao(registro=registro) is Falta.SEM_PRONTIDAO


def test_cruzada_sem_a_independencia_anotada_nega() -> None:
    """D10.6: a prova da 6 diz por que as duas fontes são independentes (ou o par do mesmo documento)."""
    registro = {"dfp": _pronta(cruzada=_prova(independencia=""))}
    assert _negacao(registro=registro) is Falta.SEM_PRONTIDAO


@pytest.mark.parametrize("exigencia", ["cruzada", "qualidade", "dicionario"])
def test_prova_com_data_no_futuro_nao_conta(exigencia: str) -> None:
    futura = _prova(dias_atras=-1, independencia="x")
    assert _negacao(registro={"dfp": _pronta(**{exigencia: futura})}) is (
        Falta.SEM_PRONTIDAO
    )


@pytest.mark.parametrize("exigencia", ["cruzada", "qualidade"])
def test_prova_com_91_dias_nega(exigencia: str) -> None:
    velha = _prova(dias_atras=PRAZO_DA_PROVA.days + 1, independencia="x")
    registro = {"dfp": _pronta(**{exigencia: velha})}
    assert _negacao(registro=registro) is Falta.PRONTIDAO_VENCIDA


@pytest.mark.parametrize("exigencia", ["cruzada", "qualidade"])
def test_prova_com_90_dias_libera(exigencia: str) -> None:
    no_limite = _prova(dias_atras=PRAZO_DA_PROVA.days, independencia="x")
    assert _negacao(registro={"dfp": _pronta(**{exigencia: no_limite})}) is None


def test_prova_do_dicionario_nao_vence_com_o_tempo() -> None:
    """A 8 vale enquanto a versão maior do contrato não mudar (D10.4)."""
    antiga = _prova(dias_atras=400, prova="revisao-do-dicionario-2025-09-30")
    assert _negacao(registro={"dfp": _pronta(dicionario=antiga)}) is None


def test_prazo_e_de_90_dias() -> None:
    assert timedelta(days=90) == PRAZO_DA_PROVA


# --- risco 2: campo calculado de duas tabelas ---


def test_campo_de_duas_tabelas_exige_as_duas() -> None:
    so_uma = _negacao(tabelas=("dfp", "cnpj"))
    as_duas = _negacao(
        tabelas=("dfp", "cnpj"), registro={"dfp": _pronta(), "cnpj": _pronta()}
    )
    assert so_uma is Falta.SEM_PRONTIDAO
    assert as_duas is None


def test_sem_tabela_nega() -> None:
    """Linha de direito sem `tabelas` não sai: o padrão vazio nega (D10.3)."""
    assert _negacao(tabelas=()) is Falta.SEM_TABELA


# --- risco 3: o contrato mudou e a prontidão ficou ---


def test_versao_maior_diferente_nega() -> None:
    assert _negacao(versoes={"dfp": 3}) is Falta.CONTRATO_MUDOU
    assert _negacao(versoes={"dfp": 1}) is Falta.CONTRATO_MUDOU


def test_tabela_fora_do_dicionario_nega() -> None:
    assert _negacao(versoes={}) is Falta.CONTRATO_MUDOU


def test_versao_maior_le_so_o_primeiro_numero() -> None:
    """Menor e correção diferentes não mexem na prontidão: só coluna nova ou correção de texto."""
    assert versao_maior("2.0.0") == versao_maior("2.3.1") == 2
    assert versao_maior("10.0.0") == 10


def test_versoes_maiores_vem_do_dicionario() -> None:
    versoes = versoes_maiores()
    assert versoes.keys() == TABELAS.keys()
    for nome, tabela in TABELAS.items():
        assert versoes[nome] == versao_maior(tabela.versao_do_contrato)


# --- risco 6: a prova vai para o catálogo público ---


@pytest.mark.parametrize(
    "texto",
    [
        "/srv/tickerlab/placar/2026-10-24.json",
        r"C:\placar\2026-10-24.json",
        "placar em 192.168.0.10",
        "https://kuma.exemplo/status",
        "pessoa@exemplo.com",
        "",
        "   ",
    ],
)
def test_prova_com_caminho_ip_ou_email_nao_e_publicavel(texto: str) -> None:
    assert not prova_publicavel(texto)


@pytest.mark.parametrize(
    "texto",
    ["placar-2026-10-24", "conferencia-do-contrato dfp v2", "kuma: dfp-qualidade"],
)
def test_identificador_simples_e_publicavel(texto: str) -> None:
    assert prova_publicavel(texto)


def test_prova_sem_caminho_ip_ou_email() -> None:
    """Toda prova do registro de verdade é publicável (vale também quando ele deixar de ser vazio)."""
    for tabela, registro in PRONTIDAO.items():
        for prova in (registro.cruzada, registro.qualidade, registro.dicionario):
            if prova is not None:
                assert prova_publicavel(prova.prova), tabela
                assert prova_publicavel(prova.independencia or "-"), tabela


def test_registro_so_tem_tabela_do_dicionario() -> None:
    assert set(PRONTIDAO) <= set(TABELAS)


def test_registro_comeca_vazio() -> None:
    """D10: nenhuma tabela tem as três provas ainda (o placar da 427 é a A2b). Quando a primeira
    entrar, por PR de nível 2 da mesa Dados, este teste sai junto."""
    assert prontidao.PRONTIDAO == {}


# ---- ensaio local (linha 800): a regra só liga com TICKERLAB_AMBIENTE=ensaio ----


@pytest.mark.parametrize(
    "ambiente",
    [{}, {"TICKERLAB_AMBIENTE": ""}, {"TICKERLAB_AMBIENTE": "producao"},
     {"TICKERLAB_AMBIENTE": "ensaio2"}, {"TICKERLAB_AMBIENTE": "local"}],
)  # fmt: skip
def test_fora_do_ensaio_o_registro_e_o_de_verdade(ambiente) -> None:
    assert prontidao.em_ensaio(ambiente) is False
    assert prontidao.registro_vigente(ambiente) is PRONTIDAO


def test_no_ensaio_toda_tabela_do_dicionario_vale_como_pronta() -> None:
    ambiente = {"TICKERLAB_AMBIENTE": " Ensaio "}
    registro = prontidao.registro_vigente(ambiente, HOJE)
    assert set(registro) >= set(TABELAS)
    assert (
        negacao_da_prontidao(
            ("demonstracoes_como_era",), registro, versoes_maiores(), HOJE
        )
        is None
    )


def test_no_ensaio_o_registro_de_verdade_tem_precedencia(monkeypatch) -> None:
    real = _pronta(versao_maior=versoes_maiores()["demonstracoes_como_era"])
    monkeypatch.setitem(PRONTIDAO, "demonstracoes_como_era", real)
    registro = prontidao.registro_vigente({"TICKERLAB_AMBIENTE": "ensaio"}, HOJE)
    assert registro["demonstracoes_como_era"] is real


def test_em_producao_o_portao_segue_negando(monkeypatch) -> None:
    """Mesmo com a tabela no dicionário e o ambiente de produção, sem registro o portão nega."""
    monkeypatch.setenv("TICKERLAB_AMBIENTE", "producao")
    registro = prontidao.registro_vigente()
    assert (
        negacao_da_prontidao(
            ("demonstracoes_como_era",), registro, versoes_maiores(), HOJE
        )
        is Falta.SEM_PRONTIDAO
    )


def test_regras_vigentes_do_portao_usam_o_registro_do_ambiente(monkeypatch) -> None:
    from src import portao_externo as portao

    monkeypatch.setenv("TICKERLAB_AMBIENTE", "ensaio")
    assert "demonstracoes_como_era" in portao.regras_vigentes().prontidao
    monkeypatch.setenv("TICKERLAB_AMBIENTE", "producao")
    assert portao.regras_vigentes().prontidao is PRONTIDAO


def test_ensaio_se_anuncia_em_toda_resposta_e_producao_nao() -> None:
    from fastapi.testclient import TestClient

    from src.api import criar_app

    no_ensaio = TestClient(criar_app({"TICKERLAB_AMBIENTE": "ensaio"}))
    assert (
        no_ensaio.get("/saude").headers[prontidao.CABECALHO_DO_ENSAIO]
        == prontidao.AVISO_DO_ENSAIO
    )
    for ambiente in ({}, {"TICKERLAB_AMBIENTE": "producao"}):
        resposta = TestClient(criar_app(ambiente)).get("/saude")
        assert prontidao.CABECALHO_DO_ENSAIO not in resposta.headers


def test_deploy_de_producao_nao_aceita_o_ambiente_de_ensaio() -> None:
    """O compose, o Dockerfile e o script de deploy nunca levam TICKERLAB_AMBIENTE=ensaio."""
    raiz = Path(__file__).resolve().parents[1]
    arquivos = [
        *raiz.glob("compose*.y*ml"),
        raiz / "Dockerfile",
        raiz / "scripts" / "deploy-automatico.sh",
        *raiz.glob(".env*example"),
    ]
    assert arquivos
    for arquivo in arquivos:
        if arquivo.is_file():
            texto = arquivo.read_text(encoding="utf-8").lower()
            assert "ambiente=ensaio" not in texto.replace(" ", ""), arquivo.name
            assert "ambiente: ensaio" not in texto, arquivo.name
            assert 'ambiente: "ensaio"' not in texto, arquivo.name


# --- D11 (Emenda 2): o registro de piloto, separado do cheio ---


def _de_piloto(**outros) -> prontidao.ProntidaoDePiloto:
    base = {
        "versao_maior": 2,
        "qualidade": _prova(),
        "dicionario": _prova(prova="dicionario-escrito-2026-11-01"),
    }
    return prontidao.ProntidaoDePiloto(**(base | outros))


def _negacao_do_piloto(
    registro: dict | None = None,
    versoes: dict[str, int] | None = None,
    decididas: frozenset[str] = frozenset({"dfp"}),
    hoje: date = HOJE,
    tabelas: tuple[str, ...] = ("dfp",),
) -> Falta | None:
    registro = {"dfp": _de_piloto()} if registro is None else registro
    versoes = {"dfp": 2} if versoes is None else versoes
    return prontidao.negacao_do_piloto(tabelas, registro, versoes, decididas, hoje)


def test_piloto_com_a_qualidade_o_dicionario_e_a_versao_libera() -> None:
    assert _negacao_do_piloto() is None


def test_o_registro_de_piloto_e_vazio_e_separado_do_cheio() -> None:
    assert prontidao.PRONTIDAO_DE_PILOTO == {}
    assert prontidao.PRONTIDAO_DE_PILOTO is not PRONTIDAO


@pytest.mark.parametrize("exigencia", ["qualidade", "dicionario"])
def test_piloto_sem_uma_das_duas_provas_nega(exigencia: str) -> None:
    registro = {"dfp": _de_piloto(**{exigencia: None})}
    assert _negacao_do_piloto(registro) == Falta.SEM_PRONTIDAO


def test_piloto_com_prova_sem_identificador_ou_do_futuro_nega() -> None:
    vazia = {"dfp": _de_piloto(qualidade=_prova(prova="  "))}
    futura = {"dfp": _de_piloto(qualidade=_prova(dias_atras=-1))}
    assert _negacao_do_piloto(vazia) == Falta.SEM_PRONTIDAO
    assert _negacao_do_piloto(futura) == Falta.SEM_PRONTIDAO


def test_prova_7_do_piloto_vence_em_90_dias() -> None:
    no_limite = {"dfp": _de_piloto(qualidade=_prova(dias_atras=PRAZO_DA_PROVA.days))}
    vencida = {"dfp": _de_piloto(qualidade=_prova(dias_atras=PRAZO_DA_PROVA.days + 1))}
    assert _negacao_do_piloto(no_limite) is None
    assert _negacao_do_piloto(vencida) == Falta.PRONTIDAO_VENCIDA


def test_piloto_com_versao_maior_diferente_nega() -> None:
    assert _negacao_do_piloto(versoes={"dfp": 3}) == Falta.CONTRATO_MUDOU
    assert _negacao_do_piloto(versoes={}) == Falta.CONTRATO_MUDOU


def test_piloto_sem_a_marca_de_pessoa_decidida_nega() -> None:
    assert _negacao_do_piloto(decididas=frozenset()) == Falta.SEM_PRONTIDAO


def test_piloto_exige_todas_as_tabelas_e_alguma_tabela() -> None:
    duas = ("dfp", "cnpj")
    assert _negacao_do_piloto(tabelas=duas) == Falta.SEM_PRONTIDAO
    assert _negacao_do_piloto(tabelas=()) == Falta.SEM_TABELA


# --- D11.4: a marca de pessoa decidida, lida do dicionário ---


def test_tabela_de_pessoa_nunca_tem_a_marca_decidida() -> None:
    assert not prontidao.pessoa_decidida(
        "x", pessoa=True, colunas=("ano",), linhas_de_pessoa="trata_como_pessoa"
    )
    com_pessoa = {nome for nome, tabela in TABELAS.items() if tabela.pessoa}
    assert com_pessoa
    assert not com_pessoa & prontidao.tabelas_com_pessoa_decidida()


def test_tabela_com_cnpj_precisa_da_marca_por_linha() -> None:
    sem = prontidao.pessoa_decidida(
        "x", pessoa=False, colunas=("cnpj", "valor"), linhas_de_pessoa=""
    )
    com = prontidao.pessoa_decidida(
        "x", pessoa=False, colunas=("cnpj",), linhas_de_pessoa="trata_como_pessoa"
    )
    sem_cnpj = prontidao.pessoa_decidida(
        "x", pessoa=False, colunas=("ano", "valor"), linhas_de_pessoa=""
    )
    assert (sem, com, sem_cnpj) == (False, True, True)


def test_rede_e_montagem_sem_pessoa_contam_como_decididas() -> None:
    for nome in prontidao.TABELAS_DA_REDE | prontidao.SEM_PESSOA_NA_MONTAGEM:
        assert prontidao.pessoa_decidida(
            nome, pessoa=False, colunas=("cnpj",), linhas_de_pessoa=""
        )


def test_as_regras_da_marca_sao_as_do_teste_da_porta() -> None:
    """Um lugar só para cada verdade: se o teste da porta mudar a regra, este cobra a mesma mudança aqui."""
    from tests import test_porta_sem_pessoa as porta

    assert prontidao.TABELAS_DA_REDE == porta.DA_REDE
    assert prontidao.SEM_PESSOA_NA_MONTAGEM == porta.SEM_PESSOA_NA_MONTAGEM
    assert prontidao.COLUNA_DE_CNPJ.pattern == porta.COLUNA_DE_CNPJ.pattern
    assert not porta.AINDA_SEM_A_MARCA & prontidao.tabelas_com_pessoa_decidida()


def test_pessoa_tirada_na_rota_nao_basta() -> None:
    """Na dúvida, a leitura mais estreita: o histórico do CNPJ tira o MEI na rota, mas não tem a marca."""
    assert TABELAS["cnpj_simples_historico"].pessoa_tirada_na_rota
    assert "cnpj_simples_historico" not in prontidao.tabelas_com_pessoa_decidida()


# --- D11.3: a frase do aviso, num lugar só ---


def test_a_frase_do_aviso_diz_que_falta_a_conferencia_com_outra_fonte() -> None:
    """Vale para as duas frases que o Tiago escolhe (12/11): trocar o texto é mudar só a constante."""
    frase = prontidao.AVISO_DE_PILOTO
    assert "piloto" in frase.lower()
    assert "outra fonte" in frase
    assert "conferid" not in frase.lower()  # o dado de piloto não está conferido
    assert prova_publicavel(frase)


# --- o ensaio do piloto não vaza para produção ---

ENSAIO = {"TICKERLAB_AMBIENTE": "ensaio"}
ENSAIO_DO_PILOTO = ENSAIO | {"TICKERLAB_ENSAIO_DO_PILOTO": "1"}


@pytest.mark.parametrize(
    "ambiente",
    [
        {},
        {"TICKERLAB_ENSAIO_DO_PILOTO": "1"},
        {"TICKERLAB_AMBIENTE": "producao", "TICKERLAB_ENSAIO_DO_PILOTO": "1"},
        ENSAIO,
        ENSAIO | {"TICKERLAB_ENSAIO_DO_PILOTO": "sim"},
    ],
)
def test_fora_do_ensaio_do_piloto_o_registro_de_piloto_e_o_de_verdade(ambiente) -> None:
    assert not prontidao.em_ensaio_do_piloto(ambiente)
    assert (
        prontidao.registro_de_piloto_vigente(ambiente, HOJE)
        is prontidao.PRONTIDAO_DE_PILOTO
    )


@pytest.mark.parametrize("ambiente", [None, "producao", "teste"])
def test_variavel_do_ensaio_do_piloto_fora_do_ensaio_nao_faz_nada(
    monkeypatch, ambiente
) -> None:
    """Em produção a `TICKERLAB_ENSAIO_DO_PILOTO=1` é ignorada: os dois registros do portão ficam os de verdade."""
    from src.portao_externo import regras_vigentes

    if ambiente is None:
        monkeypatch.delenv("TICKERLAB_AMBIENTE", raising=False)
    else:
        monkeypatch.setenv("TICKERLAB_AMBIENTE", ambiente)
    monkeypatch.setenv("TICKERLAB_ENSAIO_DO_PILOTO", "1")

    assert not prontidao.em_ensaio_do_piloto()
    assert prontidao.registro_de_piloto_vigente() is prontidao.PRONTIDAO_DE_PILOTO
    assert prontidao.registro_vigente() is PRONTIDAO
    regras = regras_vigentes()
    assert regras.prontidao_de_piloto is prontidao.PRONTIDAO_DE_PILOTO
    assert regras.prontidao is PRONTIDAO


def test_no_ensaio_do_piloto_a_prova_vai_so_para_o_registro_de_piloto() -> None:
    assert prontidao.registro_vigente(ENSAIO_DO_PILOTO, HOJE) is PRONTIDAO
    piloto = prontidao.registro_de_piloto_vigente(ENSAIO_DO_PILOTO, HOJE)
    assert set(piloto) == set(versoes_maiores())
    (prova,) = {registro.qualidade for registro in piloto.values()}
    assert prova is not None and prova.prova == prontidao.PROVA_DE_ENSAIO


def test_o_ensaio_comum_nao_enche_o_registro_de_piloto() -> None:
    assert (
        prontidao.registro_de_piloto_vigente(ENSAIO, HOJE)
        is prontidao.PRONTIDAO_DE_PILOTO
    )
    assert prontidao.registro_vigente(ENSAIO, HOJE) is not PRONTIDAO
