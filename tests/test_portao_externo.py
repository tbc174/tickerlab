"""Portão da API externa (N3; ADR 0108): nega por padrão, nunca solta pessoa natural, nota de risco,
inferência nem dívida individual de agregado, não vaza o motivo e não muda a regra do app."""

import dataclasses
from datetime import date, timedelta
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from base.prontidao import PRAZO_DA_PROVA, Prontidao, ProntidaoDePiloto, Prova
from src import portao_externo as portao
from src.banco import coletas
from src.banco.coletas import Coleta, ColetaEGuarda, Guarda
from src.portao_externo import (
    Canal,
    Categoria,
    Decisao,
    Finalidade,
    LinhaDeDireito,
    Motivo,
    Pedido,
    Regras,
    codigo_publico,
    consulta_permitida,
    decidir,
)

RAIZ = Path(__file__).resolve().parents[1]
HOJE = date(2026, 10, 21)
LIDO_EM = date(2026, 10, 1)
ABERTA = ColetaEGuarda(Coleta.ABERTA, Guarda.SEM_PRAZO)
TABELA = (
    "demonstracoes"  # a tabela de onde sai o campo do teste (um registro de mentira)
)
PROVA = Prova(date(2026, 10, 15), "placar-2026-10-15", "mesmo documento, outro canal")
PRONTA = Prontidao(versao_maior=2, cruzada=PROVA, qualidade=PROVA, dicionario=PROVA)


def _linha(
    fonte: str = "cvm-dfp",
    campo: str = "receita_liquida",
    categoria: Categoria = Categoria.FATO_DE_PJ,
    **outros: object,
) -> LinhaDeDireito:
    base = {
        "fonte": fonte,
        "conjunto": "dfp",
        "campo": campo,
        "canal": Canal.API_EXTERNA,
        "finalidade": Finalidade.ANALISE,
        "categoria": categoria,
        "vigente_desde": date(2026, 10, 1),
        "prova": "teste",
        "tabelas": (TABELA,),
    }
    return LinhaDeDireito(**{**base, **outros})  # type: ignore[arg-type]


def _pedido(
    fonte: str = "cvm-dfp", campo: str = "receita_liquida", **outros: object
) -> Pedido:
    base = {
        "fonte": fonte,
        "conjunto": "dfp",
        "campo": campo,
        "canal": Canal.API_EXTERNA,
        "finalidade": Finalidade.ANALISE,
    }
    return Pedido(**{**base, **outros})  # type: ignore[arg-type]


def _regras(*linhas: LinhaDeDireito, **outros: object) -> Regras:
    """Regras em que tudo está em ordem para as linhas dadas: só o que o teste mudar nega."""
    familias = {linha.fonte.split("-", 1)[0] for linha in linhas} | {
        "cvm",
        "bcb",
        "conab",
    }
    base = dataclasses.replace(
        portao.regras_vigentes(),
        linhas=linhas,
        coleta_e_guarda=dict.fromkeys(familias, ABERTA),
        termos_lidos_em=dict.fromkeys(familias, LIDO_EM),
        prontidao={TABELA: PRONTA},
        versoes_maiores={TABELA: PRONTA.versao_maior},
    )
    return dataclasses.replace(base, **outros)


def _vendavel(monkeypatch: pytest.MonkeyPatch, fonte: str) -> None:
    """Força a marca de revenda: o teste prova que a regra vale qualquer que seja a marca."""
    monkeypatch.setitem(coletas.REVENDA, fonte, coletas.VENDAVEL_COM_ATRIBUICAO)
    monkeypatch.setitem(
        coletas.REVENDA, fonte.split("-", 1)[0], coletas.VENDAVEL_COM_ATRIBUICAO
    )


# --- o caminho que libera, e cada condição que falta nega ---


def test_campo_com_linha_e_marcas_em_ordem_sai_com_a_coleta_na_proveniencia() -> None:
    decisao = decidir(_pedido(), HOJE, _regras(_linha()))
    assert decisao == Decisao(True, Motivo.LIBERADO, Coleta.ABERTA)


def test_hoje_nada_sai_pela_api_externa() -> None:
    """Sem linha de direito escrita e sem as respostas da linha 159, toda família é negada."""
    for familia in coletas.LICENCAS:
        decisao = decidir(_pedido(fonte=familia), HOJE)
        assert not decisao.libera, familia


def test_sem_linha_para_o_campo_nega() -> None:
    regras = _regras(_linha(campo="ativo_total"))
    assert decidir(_pedido(), HOJE, regras).motivo is Motivo.SEM_LINHA_DE_DIREITO


@pytest.mark.parametrize(
    "mudanca",
    [
        {"canal": "api_externa", "finalidade": Finalidade.CREDITO},
        {"conjunto": "itr"},
        {"fonte": "cvm-itr"},
    ],
)
def test_a_linha_vale_so_para_a_propria_fonte_conjunto_e_finalidade(
    mudanca: dict,
) -> None:
    decisao = decidir(_pedido(**mudanca), HOJE, _regras(_linha()))
    assert decisao.motivo is Motivo.SEM_LINHA_DE_DIREITO


def test_linha_fora_da_vigencia_nega() -> None:
    antes = _regras(_linha(vigente_desde=HOJE + timedelta(days=1)))
    vencida = _regras(_linha(vigente_ate=HOJE))  # o dia do `vigente_ate` já não vale
    assert decidir(_pedido(), HOJE, antes).motivo is Motivo.SEM_LINHA_DE_DIREITO
    assert decidir(_pedido(), HOJE, vencida).motivo is Motivo.SEM_LINHA_DE_DIREITO


def test_revenda_que_nao_e_vendavel_nega() -> None:
    linha = _linha(fonte="wipo-patentes")  # WIPO: não revender, só uso interno
    decisao = decidir(_pedido(fonte="wipo-patentes"), HOJE, _regras(linha))
    assert decisao.motivo is Motivo.REVENDA_NAO_VENDAVEL


def test_familia_sem_coleta_e_guarda_nega() -> None:
    regras = _regras(_linha(), coleta_e_guarda={})
    assert decidir(_pedido(), HOJE, regras).motivo is Motivo.SEM_COLETA_E_GUARDA


@pytest.mark.parametrize(
    "guarda", [Guarda.SO_PROVA, Guarda.NAO_GUARDAR, Guarda.NAO_DIZ]
)
def test_guarda_que_nao_permite_nega(guarda: Guarda) -> None:
    regras = _regras(
        _linha(), coleta_e_guarda={"cvm": ColetaEGuarda(Coleta.ABERTA, guarda)}
    )
    assert decidir(_pedido(), HOJE, regras).motivo is Motivo.GUARDA_NAO_PERMITE


@pytest.mark.parametrize(
    "coleta", [Coleta.TERMO_VEDA, Coleta.NAO_LIDA, Coleta.ROBOTS_FECHA]
)
def test_coleta_que_nao_permite_nega(coleta: Coleta) -> None:
    regras = _regras(
        _linha(), coleta_e_guarda={"cvm": ColetaEGuarda(coleta, Guarda.SEM_PRAZO)}
    )
    assert decidir(_pedido(), HOJE, regras).motivo is Motivo.COLETA_NAO_PERMITE


def test_com_cadastro_e_com_prazo_saem() -> None:
    respostas = ColetaEGuarda(Coleta.COM_CADASTRO, Guarda.COM_PRAZO, dias_de_guarda=365)
    regras = _regras(_linha(), coleta_e_guarda={"cvm": respostas})
    assert decidir(_pedido(), HOJE, regras).libera


def test_robots_fecha_sai_so_com_as_condicoes_do_d5_e_ate_a_p49() -> None:
    limpa = ColetaEGuarda(
        Coleta.ROBOTS_FECHA,
        Guarda.SEM_PRAZO,
        licenca_permite_reuso_comercial=True,
        respeita_ritmo_e_se_identifica=True,
    )
    regras = _regras(_linha(), coleta_e_guarda={"cvm": limpa})
    assert decidir(_pedido(), HOJE, regras) == Decisao(
        True, Motivo.LIBERADO, Coleta.ROBOTS_FECHA
    )

    sem_ritmo = limpa._replace(respeita_ritmo_e_se_identifica=False)
    sem_licenca = limpa._replace(licenca_permite_reuso_comercial=False)
    for respostas in (sem_ritmo, sem_licenca):
        regras = _regras(_linha(), coleta_e_guarda={"cvm": respostas})
        assert decidir(_pedido(), HOJE, regras).motivo is Motivo.COLETA_NAO_PERMITE

    depois_da_p49 = _regras(
        _linha(), coleta_e_guarda={"cvm": limpa}, robots_fecha_sai=False
    )
    assert decidir(_pedido(), HOJE, depois_da_p49).motivo is Motivo.COLETA_NAO_PERMITE


def test_termos_sem_data_de_leitura_nega() -> None:
    regras = _regras(_linha(), termos_lidos_em={})
    assert decidir(_pedido(), HOJE, regras).motivo is Motivo.TERMOS_SEM_DATA


def test_leitura_dos_termos_vale_180_dias_ou_ate_o_revisar_em() -> None:
    ultimo_dia = LIDO_EM + timedelta(days=180)
    # o placar renovou a prova (D10): só a leitura dos termos decide aqui
    nova = PROVA._replace(data=ultimo_dia)
    renovada = PRONTA._replace(cruzada=nova, qualidade=nova)
    regras = _regras(_linha(), prontidao={TABELA: renovada})
    assert decidir(_pedido(), ultimo_dia, regras).libera
    assert (
        decidir(_pedido(), ultimo_dia + timedelta(days=1), regras).motivo
        is Motivo.LEITURA_VENCIDA
    )

    curta = ColetaEGuarda(
        Coleta.ABERTA, Guarda.SEM_PRAZO, revisar_em=date(2026, 10, 20)
    )
    regras = _regras(_linha(), coleta_e_guarda={"cvm": curta})
    assert decidir(_pedido(), HOJE, regras).motivo is Motivo.LEITURA_VENCIDA


def test_canal_desconhecido_nega() -> None:
    decisao = decidir(_pedido(canal="api_externa_v2"), HOJE, _regras(_linha()))
    assert decisao == Decisao(False, Motivo.CANAL_DESCONHECIDO)


# --- D2.3: a lista negada desde o primeiro dia ---


def test_a_lista_negada_e_a_da_auditoria_n0() -> None:
    assert {
        "b3", "yahoo", "fnc", "cecafe", "kraken", "mb", "fmi",
        "wayback", "contrapartes", "termos", "ico", "bcb-sgs-189",
        "datajud",  # só uso interno (plano dos processos, PR 3)
    } == portao.NEGADAS_DESDE_O_PRIMEIRO_DIA  # fmt: skip
    assert set(coletas.LICENCAS) >= portao.NEGADAS_DESDE_O_PRIMEIRO_DIA


@pytest.mark.parametrize("negada", sorted(portao.NEGADAS_DESDE_O_PRIMEIRO_DIA))
def test_lista_negada_nunca_sai_qualquer_que_seja_a_marca(
    monkeypatch: pytest.MonkeyPatch, negada: str
) -> None:
    for fonte in (negada, f"{negada}-detalhe"):
        _vendavel(monkeypatch, fonte)
        regras = _regras(_linha(fonte=fonte))
        decisao = decidir(_pedido(fonte=fonte), HOJE, regras)
        assert decisao == Decisao(False, Motivo.NEGADA_DESDE_O_PRIMEIRO_DIA), fonte


def test_o_resto_do_banco_central_nao_cai_junto_com_o_igpm() -> None:
    linha = _linha(fonte="bcb-sgs-432")
    assert decidir(_pedido(fonte="bcb-sgs-432"), HOJE, _regras(linha)).libera


def test_conab_sai_so_como_publicada(monkeypatch: pytest.MonkeyPatch) -> None:
    _vendavel(monkeypatch, "conab")
    regras = _regras(_linha(fonte="conab"))
    assert decidir(_pedido(fonte="conab"), HOJE, regras).libera
    derivado = _pedido(fonte="conab", derivado=True)
    assert decidir(derivado, HOJE, regras).motivo is Motivo.SO_COMO_PUBLICADO


def test_conab_vendavel_por_risco_assumido_sai_sem_forcar_a_marca() -> None:
    """ADR 0122 (05/11/2026): a CONAB passou a vendável por risco assumido; antes era a confirmar."""
    regras = _regras(_linha(fonte="conab"))
    assert decidir(_pedido(fonte="conab"), HOJE, regras).libera


# --- D2.4: o que nunca sai pela API externa, qualquer que seja a marca ---

CAMPOS_DE_PESSOA_E_DE_RISCO = [
    "nome_socio",
    "socios",
    "cpf",
    "cpf_do_administrador",
    "nome_do_administrador",
    "nome_pf",
    "pessoa_fisica_nome",
    "mei_nome",
    "empresario_individual",
    "score",
    "score_de_credito",
    "rating",
    "pd_12_meses",
    "insolvencia_inferida",
    "probabilidade_de_default",
]


@pytest.mark.parametrize("campo", CAMPOS_DE_PESSOA_E_DE_RISCO)
def test_campo_de_pessoa_ou_de_risco_nunca_sai_mesmo_com_linha_escrita(
    campo: str,
) -> None:
    """A linha escrita com a categoria errada não basta: o nome do campo também barra."""
    regras = _regras(_linha(campo=campo))
    assert decidir(_pedido(campo=campo), HOJE, regras) == Decisao(
        False, Motivo.NUNCA_SAI
    )


@pytest.mark.parametrize("categoria", sorted(portao.NUNCA_SAEM))
def test_categoria_que_nunca_sai_nega_mesmo_com_nome_inocente(
    categoria: Categoria,
) -> None:
    regras = _regras(_linha(campo="valor", categoria=categoria))
    assert decidir(_pedido(campo="valor"), HOJE, regras).motivo is Motivo.NUNCA_SAI


def test_com_duas_linhas_para_o_campo_vale_a_mais_restrita() -> None:
    linhas = (
        _linha(campo="valor"),
        _linha(campo="valor", categoria=Categoria.PESSOA_NATURAL),
    )
    for ordem in (linhas, linhas[::-1]):
        assert (
            decidir(_pedido(campo="valor"), HOJE, _regras(*ordem)).motivo
            is Motivo.NUNCA_SAI
        )


@pytest.mark.parametrize(
    "fonte", ["bcb-scr", "bcb-mdcr", "bcb-sicor", "bcb-scr-municipio"]
)
def test_agregado_de_credito_nunca_vira_divida_individual(fonte: str) -> None:
    como_empresa = _regras(_linha(fonte=fonte, campo="carteira_ativa"))
    decisao = decidir(_pedido(fonte=fonte, campo="carteira_ativa"), HOJE, como_empresa)
    assert decisao.motivo is Motivo.AGREGADO_SO_COMO_AGREGADO

    dividida = _regras(
        _linha(
            fonte=fonte,
            campo="carteira_ativa",
            categoria=Categoria.DIVIDA_INDIVIDUAL_DE_AGREGADO,
        )
    )
    assert (
        decidir(_pedido(fonte=fonte, campo="carteira_ativa"), HOJE, dividida).motivo
        is Motivo.NUNCA_SAI
    )

    agregado = _regras(
        _linha(fonte=fonte, campo="carteira_ativa", categoria=Categoria.AGREGADO)
    )
    assert decidir(_pedido(fonte=fonte, campo="carteira_ativa"), HOJE, agregado).libera


@pytest.mark.parametrize(
    "chave", ["nome", "cpf", "nome_socio", "lote_de_nomes", "email", ""]
)
def test_busca_reversa_por_pessoa_e_lote_de_nomes_nunca(chave: str) -> None:
    assert consulta_permitida(chave) == Decisao(False, Motivo.CONSULTA_PROIBIDA)


@pytest.mark.parametrize("chave", sorted(portao.CHAVES_DE_CONSULTA))
def test_busca_por_chave_de_empresa_pode(chave: str) -> None:
    assert consulta_permitida(chave).libera


@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    palavra=st.sampled_from(sorted(portao.PALAVRAS_QUE_NUNCA_SAEM)),
    antes=st.sampled_from(["", "nome_", "valor_", "total_"]),
    depois=st.sampled_from(["", "_nome", "_12m", "_do_cnpj"]),
    categoria=st.sampled_from(list(Categoria)),
    finalidade=st.sampled_from(list(Finalidade)),
)
def test_propriedade_campo_com_palavra_proibida_nunca_sai(
    palavra: str, antes: str, depois: str, categoria: Categoria, finalidade: Finalidade
) -> None:
    campo = (
        f"{antes}{palavra}{depois}".upper()
        if palavra == "cpf"
        else f"{antes}{palavra}{depois}"
    )
    linha = _linha(campo=campo, categoria=categoria, finalidade=finalidade)
    decisao = decidir(_pedido(campo=campo, finalidade=finalidade), HOJE, _regras(linha))
    assert not decisao.libera


# --- D10 (Emenda 1): só sai tabela pronta ---


def test_linha_sem_tabelas_nega() -> None:
    """O padrão vazio de `tabelas` nega: a B-32a escreve de que tabela cada campo sai."""
    regras = _regras(_linha(tabelas=()))
    assert decidir(_pedido(), HOJE, regras).motivo is Motivo.SEM_TABELA


def test_tabela_sem_prontidao_nega_mesmo_com_direito_e_marcas_em_ordem() -> None:
    regras = _regras(_linha(), prontidao={})
    assert decidir(_pedido(), HOJE, regras).motivo is Motivo.SEM_PRONTIDAO


@pytest.mark.parametrize("exigencia", ["cruzada", "qualidade", "dicionario"])
def test_falta_uma_exigencia_nega(exigencia: str) -> None:
    regras = _regras(_linha(), prontidao={TABELA: PRONTA._replace(**{exigencia: None})})
    assert decidir(_pedido(), HOJE, regras).motivo is Motivo.SEM_PRONTIDAO


def test_prova_com_91_dias_nega_e_com_90_libera() -> None:
    regras = _regras(_linha())
    limite = PROVA.data + PRAZO_DA_PROVA
    assert decidir(_pedido(), limite, regras).libera
    vencida = decidir(_pedido(), limite + timedelta(days=1), regras)
    assert vencida.motivo is Motivo.PRONTIDAO_VENCIDA


def test_versao_maior_diferente_nega() -> None:
    regras = _regras(_linha(), versoes_maiores={TABELA: PRONTA.versao_maior + 1})
    assert decidir(_pedido(), HOJE, regras).motivo is Motivo.CONTRATO_MUDOU


def test_campo_de_duas_tabelas_exige_as_duas() -> None:
    linha = _linha(tabelas=(TABELA, "cadastro"))
    so_uma = _regras(linha)
    as_duas = _regras(
        linha,
        prontidao={TABELA: PRONTA, "cadastro": PRONTA},
        versoes_maiores={TABELA: 2, "cadastro": 2},
    )
    assert decidir(_pedido(), HOJE, so_uma).motivo is Motivo.SEM_PRONTIDAO
    assert decidir(_pedido(), HOJE, as_duas).libera


def test_duas_linhas_vigentes_valem_as_tabelas_das_duas() -> None:
    """Como na categoria (vale a mais restrita): a outra linha do mesmo campo traz uma tabela que
    não está pronta, e o campo não sai."""
    regras = _regras(_linha(), _linha(tabelas=("cadastro",)))
    assert decidir(_pedido(), HOJE, regras).motivo is Motivo.SEM_PRONTIDAO


def test_linha_fora_da_vigencia_nao_traz_tabela() -> None:
    vencida = _linha(tabelas=("cadastro",), vigente_ate=HOJE)
    assert decidir(_pedido(), HOJE, _regras(_linha(), vencida)).libera


def test_direito_nega_antes_da_qualidade() -> None:
    """A qualidade é a última conferência: sem direito, o motivo no log continua o do direito."""
    regras = _regras(_linha(campo="ativo_total"), prontidao={})
    assert decidir(_pedido(), HOJE, regras).motivo is Motivo.SEM_LINHA_DE_DIREITO


def test_motivos_da_qualidade_sao_os_da_prontidao() -> None:
    from base.prontidao import Falta

    assert {falta.value for falta in Falta} <= {motivo.value for motivo in Motivo}


def test_regras_vigentes_leem_o_registro_e_o_dicionario() -> None:
    from base import prontidao

    regras = portao.regras_vigentes()
    assert regras.prontidao is prontidao.PRONTIDAO
    assert regras.versoes_maiores == prontidao.versoes_maiores()


@pytest.mark.parametrize("canal", sorted(portao.CANAIS_DO_APP))
def test_canais_do_app_ignoram_prontidao(canal: Canal) -> None:
    sem_nada = _regras(_linha(tabelas=()), prontidao={}, versoes_maiores={})
    decisao = decidir(_pedido(canal=canal), HOJE, sem_nada)
    assert decisao == Decisao(
        coletas.pode_usar(coletas.MOSTRAR, "cvm-dfp"), Motivo.REGRA_DO_APP
    )


# --- D2.2: negar não vaza o dado ---


def test_toda_negacao_tem_o_mesmo_codigo_publico_sem_fonte_nem_campo() -> None:
    negacoes = [
        decidir(_pedido(campo="cpf"), HOJE, _regras(_linha(campo="cpf"))),
        decidir(_pedido(fonte="b3-negocios"), HOJE, _regras()),
        decidir(_pedido(), HOJE, _regras()),
        decidir(_pedido(fonte="wipo-x"), HOJE, _regras(_linha(fonte="wipo-x"))),
        decidir(_pedido(), HOJE, _regras(_linha(), termos_lidos_em={})),
        decidir(_pedido(), HOJE, _regras(_linha(tabelas=()))),
        decidir(_pedido(), HOJE, _regras(_linha(), prontidao={})),
        decidir(_pedido(), HOJE + timedelta(days=90), _regras(_linha())),
        decidir(_pedido(), HOJE, _regras(_linha(), versoes_maiores={TABELA: 3})),
        consulta_permitida("cpf"),
    ]
    assert len({n.motivo for n in negacoes}) == len(
        negacoes
    )  # motivos diferentes por dentro
    codigos = {codigo_publico(n) for n in negacoes}
    assert codigos == {portao.CODIGO_PUBLICO_DA_NEGACAO}  # um só por fora
    assert all(n.coleta is None for n in negacoes)  # nem a proveniência sai
    for proibido in ("cpf", "b3", "sec", "cvm", "receita"):
        assert proibido not in portao.CODIGO_PUBLICO_DA_NEGACAO
    assert codigo_publico(decidir(_pedido(), HOJE, _regras(_linha()))) is None


# --- teste de propriedade: acrescentar uma regra de negar nunca libera nada ---

FONTES = [
    "cvm-dfp",
    "cvm-itr",
    "rfb-cnpj",
    "bcb-scr",
    "bcb-sgs-432",
    "conab",
    "ibge-pib",
    "nova-fonte",
]
CAMPOS = ["receita_liquida", "valor", "nome_socio", "carteira_ativa", "capital_social"]
CONJUNTOS = ["dfp", "cnpj"]
DATAS = st.dates(min_value=date(2026, 1, 1), max_value=date(2027, 12, 31))

pedidos = st.builds(
    Pedido,
    fonte=st.sampled_from(FONTES),
    conjunto=st.sampled_from(CONJUNTOS),
    campo=st.sampled_from(CAMPOS),
    canal=st.just(Canal.API_EXTERNA.value),
    finalidade=st.sampled_from([f.value for f in Finalidade]),
    derivado=st.booleans(),
)
linhas = st.builds(
    LinhaDeDireito,
    fonte=st.sampled_from(FONTES),
    conjunto=st.sampled_from(CONJUNTOS),
    campo=st.sampled_from(CAMPOS),
    canal=st.just(Canal.API_EXTERNA),
    finalidade=st.sampled_from(list(Finalidade)),
    categoria=st.sampled_from(list(Categoria)),
    vigente_desde=DATAS,
    prova=st.just("teste"),
    vigente_ate=st.none() | DATAS,
    tabelas=st.sampled_from([(), (TABELA,), (TABELA, "cadastro"), ("cadastro",)]),
)
provas = st.builds(
    Prova, data=DATAS, prova=st.just("placar"), independencia=st.sampled_from(["", "x"])
)
prontidoes = st.builds(
    Prontidao,
    versao_maior=st.integers(min_value=1, max_value=3),
    cruzada=st.none() | provas,
    qualidade=st.none() | provas,
    dicionario=st.none() | provas,
)
respostas = st.builds(
    ColetaEGuarda,
    coleta=st.sampled_from(list(Coleta)),
    guarda=st.sampled_from(list(Guarda)),
    revisar_em=st.none() | DATAS,
    licenca_permite_reuso_comercial=st.booleans(),
    respeita_ritmo_e_se_identifica=st.booleans(),
)
familias = st.sampled_from(["cvm", "rfb", "rfb-cnpj", "bcb", "conab", "ibge", "nova"])


@st.composite
def regras_quaisquer(draw: st.DrawFn) -> Regras:
    return dataclasses.replace(
        portao.regras_vigentes(),
        linhas=tuple(draw(st.lists(linhas, max_size=8))),
        coleta_e_guarda=draw(st.dictionaries(familias, respostas, max_size=5)),
        termos_lidos_em=draw(st.dictionaries(familias, DATAS, max_size=5)),
        robots_fecha_sai=draw(st.booleans()),
        prontidao=draw(
            st.dictionaries(st.sampled_from([TABELA, "cadastro"]), prontidoes)
        ),
        versoes_maiores={TABELA: 2, "cadastro": 1},
    )


@st.composite
def apertos(draw: st.DrawFn, regras: Regras) -> Regras:
    """Uma regra de negar a mais: lista, palavra, agregado, P-49, linha restrita ou resposta pior."""
    fonte = draw(st.sampled_from([*FONTES, "cvm", "bcb", "rfb"]))
    tipo = draw(st.integers(min_value=0, max_value=8))
    if tipo == 0:
        return dataclasses.replace(regras, negadas=regras.negadas | {fonte})
    if tipo == 1:
        palavra = draw(st.sampled_from(["valor", "receita", "capital", "carteira"]))
        return dataclasses.replace(
            regras, palavras_que_nunca_saem=regras.palavras_que_nunca_saem | {palavra}
        )
    if tipo == 2:
        return dataclasses.replace(
            regras, fontes_de_agregado=regras.fontes_de_agregado | {fonte}
        )
    if tipo == 3:
        return dataclasses.replace(
            regras, so_como_publicado=regras.so_como_publicado | {fonte}
        )
    if tipo == 4:
        return dataclasses.replace(regras, robots_fecha_sai=False)
    if tipo == 5:
        restrita = draw(linhas)._replace(
            categoria=draw(st.sampled_from(sorted(portao.NUNCA_SAEM)))
        )
        return dataclasses.replace(regras, linhas=(*regras.linhas, restrita))
    if tipo == 7:  # tirar a prontidão de uma tabela (D10.5, nível 3)
        tirada = draw(st.sampled_from([TABELA, "cadastro"]))
        resto = {k: v for k, v in regras.prontidao.items() if k != tirada}
        return dataclasses.replace(regras, prontidao=resto)
    if tipo == 8:  # o contrato de uma tabela sobe a versão maior
        tabela = draw(st.sampled_from([TABELA, "cadastro"]))
        versoes = {**regras.versoes_maiores, tabela: regras.versoes_maiores[tabela] + 1}
        return dataclasses.replace(regras, versoes_maiores=versoes)
    # a resposta de uma família piora (não some: sem a da fonte, vale a da família, como na revenda)
    familia = draw(familias)
    piores = {
        k: v._replace(guarda=Guarda.NAO_GUARDAR) if k == familia else v
        for k, v in regras.coleta_e_guarda.items()
    }
    return dataclasses.replace(regras, coleta_e_guarda=piores)


@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(data=st.data(), pedido=pedidos, regras=regras_quaisquer(), hoje=DATAS)
def test_propriedade_regra_de_negar_a_mais_nunca_libera_o_que_estava_negado(
    data: st.DataObject, pedido: Pedido, regras: Regras, hoje: date
) -> None:
    apertada = data.draw(apertos(regras))
    if decidir(pedido, hoje, apertada).libera:
        assert decidir(pedido, hoje, regras).libera


# --- a regra do app (ADR 0102) continua igual ---


@pytest.mark.parametrize("canal", sorted(portao.CANAIS_DO_APP))
def test_nos_canais_do_app_o_portao_so_repete_pode_usar(canal: Canal) -> None:
    for familia in [*coletas.LICENCAS, "nova-fonte", "b3-negocios", "yahoo-bvsp"]:
        for finalidade in Finalidade:
            uso = "treinar" if finalidade is Finalidade.TREINO else coletas.MOSTRAR
            pedido = _pedido(fonte=familia, canal=canal, finalidade=finalidade)
            decisao = decidir(pedido, HOJE, _regras())
            assert decisao == Decisao(
                coletas.pode_usar(uso, familia), Motivo.REGRA_DO_APP
            )


def test_pode_usar_libera_tudo_inclusive_a_b3_menos_as_so_internas() -> None:
    """ADR 0008, Emenda 6 (22/10/2026): a B3 entrou no app; a API externa tem a regra própria. As
    `FONTES_SO_INTERNAS` (o DataJud) só treinam e rotulam (`tests/test_trava_so_interna.py`); as
    `FONTES_SEM_TREINO` (o DATASUS, ADR 0122) fazem tudo menos treinar (`tests/test_trava_sem_treino.py`)."""
    for familia in coletas.LICENCAS:
        for uso in coletas.USOS:
            esperado = (
                familia not in coletas.FONTES_SO_INTERNAS
                or uso in coletas.USOS_INTERNOS
            ) and not (familia in coletas.FONTES_SEM_TREINO and uso == "treinar")
            assert coletas.pode_usar(uso, familia) is esperado, (familia, uso)


def test_nenhuma_tela_nem_a_api_do_app_usa_o_portao_externo() -> None:
    """O portão é só da API externa: o app não o importa, então nenhuma tela mudou."""
    arquivos = [
        RAIZ / "app.py",
        *(RAIZ / "telas").rglob("*.py"),
        *(RAIZ / "src" / "api_v1").rglob("*.py"),
    ]
    arquivos += [RAIZ / "src" / "api.py"]
    for arquivo in arquivos:
        assert "portao_externo" not in arquivo.read_text(encoding="utf-8"), arquivo


def test_coleta_e_guarda_so_de_familias_do_licencas() -> None:
    assert set(coletas.COLETA_E_GUARDA) <= set(coletas.LICENCAS)


# --- D11 (Emenda 2): a prontidão de piloto, só para a organização do piloto ---

DE_PILOTO = ProntidaoDePiloto(versao_maior=2, qualidade=PROVA, dicionario=PROVA)


def _regras_de_piloto(*linhas: LinhaDeDireito, **outros: object) -> Regras:
    """A tabela sem a prontidão cheia, com o registro de piloto em dia e a marca de pessoa decidida."""
    base = {
        "prontidao": {},
        "prontidao_de_piloto": {TABELA: DE_PILOTO},
        "pessoa_decidida": frozenset({TABELA}),
    }
    return _regras(*(linhas or (_linha(),)), **(base | outros))


def test_organizacao_do_piloto_sai_pelo_piloto_e_a_comum_nao() -> None:
    regras = _regras_de_piloto()
    do_piloto = decidir(_pedido(piloto=True), HOJE, regras)
    comum = decidir(_pedido(), HOJE, regras)
    assert do_piloto.libera and do_piloto.piloto
    assert do_piloto.motivo is Motivo.LIBERADO_PELO_PILOTO
    assert do_piloto.coleta is Coleta.ABERTA
    assert comum == Decisao(False, Motivo.SEM_PRONTIDAO)
    assert not comum.piloto


def test_tabela_pronta_sai_pela_prontidao_cheia_mesmo_para_o_piloto() -> None:
    """O aviso é só do que não tem a prontidão cheia: a tabela pronta sai sem ele."""
    regras = _regras_de_piloto(prontidao={TABELA: PRONTA})
    decisao = decidir(_pedido(piloto=True), HOJE, regras)
    assert decisao.motivo is Motivo.LIBERADO and not decisao.piloto


def test_piloto_com_prova_7_vencida_nega() -> None:
    """No limite dos 90 dias ainda sai; no dia seguinte, não (o motivo no log segue o da prontidão cheia)."""
    limite = PROVA.data + PRAZO_DA_PROVA
    depois = limite + timedelta(days=1)
    termos = dict.fromkeys(("cvm", "bcb", "conab"), limite)
    regras = _regras_de_piloto(termos_lidos_em=termos)
    assert decidir(_pedido(piloto=True), limite, regras).piloto
    assert decidir(_pedido(piloto=True), depois, regras) == Decisao(
        False, Motivo.SEM_PRONTIDAO
    )


def test_piloto_com_versao_maior_diferente_nega() -> None:
    regras = _regras_de_piloto(versoes_maiores={TABELA: DE_PILOTO.versao_maior + 1})
    assert decidir(_pedido(piloto=True), HOJE, regras) == Decisao(
        False, Motivo.SEM_PRONTIDAO
    )


def test_piloto_sem_a_marca_de_pessoa_decidida_nega() -> None:
    regras = _regras_de_piloto(pessoa_decidida=frozenset())
    assert not decidir(_pedido(piloto=True), HOJE, regras).libera


def test_piloto_sem_registro_de_piloto_nega() -> None:
    regras = _regras_de_piloto(prontidao_de_piloto={})
    assert not decidir(_pedido(piloto=True), HOJE, regras).libera


def test_piloto_com_linha_sem_tabela_nega() -> None:
    regras = _regras_de_piloto(_linha(tabelas=()))
    assert decidir(_pedido(piloto=True), HOJE, regras) == Decisao(
        False, Motivo.SEM_TABELA
    )


@pytest.mark.parametrize("campo", CAMPOS_DE_PESSOA_E_DE_RISCO)
def test_piloto_nunca_solta_campo_de_pessoa(campo: str) -> None:
    """Direito e pessoa vêm antes do piloto e não mudam (D11.4)."""
    regras = _regras_de_piloto(_linha(campo=campo))
    assert decidir(_pedido(campo=campo, piloto=True), HOJE, regras) == Decisao(
        False, Motivo.NUNCA_SAI
    )


def test_piloto_nao_solta_categoria_de_pessoa_nem_sem_direito() -> None:
    pessoa = _regras_de_piloto(_linha(categoria=Categoria.PESSOA_NATURAL))
    sem_linha = _regras_de_piloto(_linha(campo="outro"))
    negada = _regras_de_piloto(_linha(fonte="b3-negocios"))
    assert decidir(_pedido(piloto=True), HOJE, pessoa).motivo is Motivo.NUNCA_SAI
    assert (
        decidir(_pedido(piloto=True), HOJE, sem_linha).motivo
        is Motivo.SEM_LINHA_DE_DIREITO
    )
    assert not decidir(_pedido(fonte="b3-negocios", piloto=True), HOJE, negada).libera


def test_piloto_nao_solta_familia_sem_marcas() -> None:
    regras = _regras_de_piloto(termos_lidos_em={})
    assert decidir(_pedido(piloto=True), HOJE, regras).motivo is Motivo.TERMOS_SEM_DATA


@pytest.mark.parametrize("canal", sorted(portao.CANAIS_DO_APP))
def test_canais_do_app_ignoram_a_marca_de_piloto(canal: Canal) -> None:
    """Conta do app (com ou sem organização): a regra é a da ADR 0102, com ou sem a marca."""
    regras = _regras_de_piloto()
    com, sem = (
        decidir(_pedido(canal=canal, piloto=marca), HOJE, regras)
        for marca in (True, False)
    )
    assert com == sem and com.motivo is Motivo.REGRA_DO_APP and not com.piloto


def test_regras_vigentes_leem_o_registro_de_piloto_e_a_marca_de_pessoa() -> None:
    from base import prontidao

    regras = portao.regras_vigentes()
    assert regras.prontidao_de_piloto is prontidao.PRONTIDAO_DE_PILOTO
    assert regras.pessoa_decidida == prontidao.tabelas_com_pessoa_decidida()


def test_hoje_nada_sai_pelo_piloto() -> None:
    """O registro de piloto nasce vazio: nem a organização do piloto recebe nada até a mesa Dados gravar."""
    for linha in portao.DIREITOS_DA_API_EXTERNA:
        pedido = Pedido(
            fonte=linha.fonte, conjunto=linha.conjunto, campo=linha.campo,
            canal=Canal.API_EXTERNA, finalidade=linha.finalidade, piloto=True,
        )  # fmt: skip
        assert not decidir(pedido, HOJE).piloto


def test_conjunto_da_marca_nunca_e_conjunto_de_dado() -> None:
    """A linha de contrato da marca de piloto não pode virar, sem querer, o contrato de um conjunto servido."""
    from src.banco.chaves_da_api import CONJUNTO_DO_PILOTO

    assert all(
        linha.conjunto != CONJUNTO_DO_PILOTO for linha in portao.DIREITOS_DA_API_EXTERNA
    )
