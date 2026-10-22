"""Portão da API externa (N3; ADR 0108): nega por padrão, nunca solta pessoa natural, nota de risco,
inferência nem dívida individual de agregado, não vaza o motivo e não muda a regra do app."""

import dataclasses
from datetime import date, timedelta
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

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
    linha = _linha(fonte="sec-10k")  # SEC: só uso interno
    decisao = decidir(_pedido(fonte="sec-10k"), HOJE, _regras(linha))
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
    regras = _regras(_linha())
    ultimo_dia = LIDO_EM + timedelta(days=180)
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


def test_conab_hoje_e_a_confirmar_e_nao_sai() -> None:
    regras = _regras(_linha(fonte="conab"))
    assert (
        decidir(_pedido(fonte="conab"), HOJE, regras).motivo
        is Motivo.REVENDA_NAO_VENDAVEL
    )


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


# --- D2.2: negar não vaza o dado ---


def test_toda_negacao_tem_o_mesmo_codigo_publico_sem_fonte_nem_campo() -> None:
    negacoes = [
        decidir(_pedido(campo="cpf"), HOJE, _regras(_linha(campo="cpf"))),
        decidir(_pedido(fonte="b3-negocios"), HOJE, _regras()),
        decidir(_pedido(), HOJE, _regras()),
        decidir(_pedido(fonte="sec-10k"), HOJE, _regras(_linha(fonte="sec-10k"))),
        decidir(_pedido(), HOJE, _regras(_linha(), termos_lidos_em={})),
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
    )


@st.composite
def apertos(draw: st.DrawFn, regras: Regras) -> Regras:
    """Uma regra de negar a mais: lista, palavra, agregado, P-49, linha restrita ou resposta pior."""
    fonte = draw(st.sampled_from([*FONTES, "cvm", "bcb", "rfb"]))
    tipo = draw(st.integers(min_value=0, max_value=6))
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


def test_pode_usar_libera_tudo_inclusive_a_b3() -> None:
    """ADR 0008, Emenda 6 (22/10/2026): a B3 entrou no app; a API externa tem a regra própria."""
    for familia in coletas.LICENCAS:
        for uso in coletas.USOS:
            assert coletas.pode_usar(uso, familia) is True, (familia, uso)


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
