"""As tabelas ligadas pelo CNPJ do registro (`tabelas_por_cnpj`, linha 978, lote 1) na análise e na rota do fundo.

Base de mentira, sem internet; os CNPJs são de ninguém. O leitor (`conjuntos/por_tabela.py`) com a porta de
verdade, e as rotas com o portão e as linhas de direito de verdade (geradas do registro). Riscos: olhar o futuro
(a linha publicada depois do dia não sai, e cortar o futuro não muda o passado), bloco fechado vazando (duas
organizações; conjunto sem contrato; tabela sem prontidão), linha que saiu do arquivo (`consta` falso), a versão
velha de um informe e o aviso de piloto (as seis tabelas estão hoje só na prontidão de piloto).
"""

import dataclasses
from datetime import date

import pandas as pd
import pytest

from base import prontidao
from base.porta import Porta
from base.prontidao import AVISO_DE_PILOTO, Prontidao, ProntidaoDePiloto, Prova
from src import portao_externo as portao
from src.api_externa import rotas, tabelas_por_cnpj
from src.api_externa.conjuntos import analise, empresas, ficha, por_tabela
from src.banco import chaves_da_api as cb
from tests import ajudantes_da_api_externa as aj
from tests import test_api_externa_analise as analise_de_mentira
from tests import test_api_externa_empresas as empresas_de_mentira
from tests import test_api_externa_socios_pj as socios_de_mentira

AGORA = empresas_de_mentira.AGORA
EMPRESA = empresas_de_mentira.EMPRESA
RAIZ = EMPRESA[:8]
OUTRA_RAIZ = "99999999"
DIA = date(2025, 6, 30)
ANEEL = "aneel_indicadores_comerciais"
FII = "fii_informe_mensal"
FIP = "fip_informe"
FUNDO = "11111111000191"
OUTRO_FUNDO_DA_RAIZ = "11111111000272"  # a mesma raiz, outro CNPJ: não é o fundo pedido
_SEM_PESSOA = {"trata_como_pessoa": False, "origem_sha256": "0" * 64}


def _dias(tabela: pd.DataFrame, *colunas: str) -> pd.DataFrame:
    for coluna in colunas:
        tabela[coluna] = pd.to_datetime(tabela[coluna]).dt.date
    return tabela


def _aneel() -> pd.DataFrame:
    # fmt: off
    linhas = [
        # raiz, referência, município, unidades ativas, disponível em, consta
        (RAIZ, "2025-03-01", "3550308", 100, "2025-05-10", True),
        (RAIZ, "2025-03-01", "3304557", 300, "2025-05-10", True),
        (RAIZ, "2025-03-01", "3106200", 999, "2025-05-10", False),  # saiu do arquivo: não sai
        (RAIZ, "2025-02-01", "3550308", 90, "2025-04-10", True),  # mês mais velho: só o mais novo sai
        (RAIZ, "2025-04-01", "3550308", 120, "2025-07-15", True),  # só pública depois do dia
        (OUTRA_RAIZ, "2025-03-01", "3550308", 5, "2025-05-10", True),  # outra empresa
    ]
    # fmt: on
    tabela = pd.DataFrame(
        linhas,
        columns=[
            "cnpj_basico",
            "referencia",
            "municipio_ibge",
            "unidades_ativas",
            "disponivel_em",
            "consta",
        ],
    )  # fmt: skip
    tabela = _dias(tabela, "referencia", "disponivel_em")
    return tabela.assign(
        cnpj=tabela["cnpj_basico"] + "000100",
        sigla_do_agente="DISTRIBUIDORA",
        tipo_de_outorga="Concessão",
        faturas=1000,
        id_na_fonte=[f"aneel-{i}" for i in range(len(tabela))],
        visto_em=date(2025, 5, 10),
        **_SEM_PESSOA,
    )


def _fii() -> pd.DataFrame:
    # fmt: off
    linhas = [
        # cnpj, referência, versão, patrimônio, disponível em
        (FUNDO, "2025-04-01", 1, 100.0, "2025-05-15"),
        (FUNDO, "2025-04-01", 2, 110.0, "2025-06-10"),  # a reapresentação: vale esta
        (FUNDO, "2025-05-01", 1, 120.0, "2025-06-15"),
        (FUNDO, "2025-05-01", 2, 999.0, "2025-08-01"),  # reapresentada depois do dia: no dia vale a 1
        (OUTRO_FUNDO_DA_RAIZ, "2025-05-01", 1, 7.0, "2025-06-15"),
    ]
    # fmt: on
    tabela = pd.DataFrame(
        linhas,
        columns=["cnpj", "referencia", "versao", "patrimonio_liquido", "disponivel_em"],
    )
    tabela = _dias(tabela, "referencia", "disponivel_em")
    return tabela.assign(
        cnpj_basico=tabela["cnpj"].str[:8],
        nome_do_fundo="FII DE MENTIRA",
        cotistas=10,
        cotistas_pessoa_fisica=8,  # a trava do nome: nunca sai
        cnpj_administrador="12345678000199",  # idem
        consta=True,
        id_na_fonte=[f"{c}|{r}|{v}" for c, r, v, _p, _d in linhas],
        visto_em=tabela["disponivel_em"],
        **_SEM_PESSOA,
    )


def _fip() -> pd.DataFrame:
    tabela = pd.DataFrame(
        {
            "cnpj": [FUNDO, FUNDO],
            "competencia": ["2025-03-31", "2023-12-31"],
            "periodicidade": ["trimestral", "quadrimestral"],
            "patrimonio_liquido": [50.0, 40.0],
            "disponivel_em": ["2025-05-01", "2024-02-01"],
        }
    )
    tabela = _dias(tabela, "competencia", "disponivel_em")
    return tabela.assign(
        cnpj_basico=tabela["cnpj"].str[:8],
        consta=True,
        id_na_fonte=["fip-1", "fip-2"],
        visto_em=tabela["disponivel_em"],
        **_SEM_PESSOA,
    )


def gravar(pasta, tabela: str, linhas: pd.DataFrame) -> None:
    (pasta / tabela).mkdir(parents=True, exist_ok=True)
    linhas.to_parquet(pasta / tabela / "parte.parquet", index=False)


def _tudo(_fonte: str, _campo: str, _derivado: bool) -> bool:
    return True


def _ler(pasta, bloco, cnpj=EMPRESA, dia=DIA, permitido=_tudo, linhas=10):
    with Porta(pasta) as porta:
        return por_tabela.LeitorPorTabela(porta, permitido, linhas).bloco(
            bloco, cnpj, dia
        )


def _valores(sub: dict, campo: str) -> list:
    return [item[campo]["valor"] for item in sub["itens"]]


@pytest.fixture
def base(tmp_path):
    pasta = tmp_path / "base"
    gravar(pasta, ANEEL, _aneel())
    gravar(pasta, FII, _fii())
    gravar(pasta, FIP, _fip())
    return pasta


# ---------------------------------------------------------------- o registro


def test_toda_entrada_do_registro_tem_linha_de_direito_e_nenhuma_e_da_pgfn():
    linhas = {
        (linha.fonte, linha.campo): linha for linha in portao.DIREITOS_DA_API_EXTERNA
    }
    for entrada in tabelas_por_cnpj.REGISTRO:
        for fonte, campo in por_tabela.pares(entrada):
            linha = linhas[(fonte, campo)]
            assert linha.conjunto == entrada.conjunto
            assert entrada.tabela in linha.tabelas
    assert "pgfn_divida" not in {e.tabela for e in tabelas_por_cnpj.REGISTRO}


def test_campo_que_a_trava_do_nome_nega_nao_esta_no_registro():
    for entrada in tabelas_por_cnpj.REGISTRO:
        for campo in entrada.campos:
            assert not set(campo.split("_")) & portao.PALAVRAS_QUE_NUNCA_SAEM, campo


# ---------------------------------------------------------------- o leitor


def test_lista_tem_so_a_data_mais_nova_ja_publica_na_ordem_da_entrada(base):
    lido = _ler(base, tabelas_por_cnpj.REGULADOS)
    assert lido is not None
    sub = lido.corpo["indicadores_comerciais_da_aneel"]
    assert sub["achou"] is True
    assert _valores(sub, "municipio_ibge") == [
        "3304557",
        "3550308",
    ]  # mais unidades primeiro
    assert set(_valores(sub, "referencia")) == {"2025-03-01"}
    item = sub["itens"][0]
    assert item["unidades_ativas"] == {
        "valor": 300,
        "fonte": "aneel-fiscalizacao",
        "publico_em": "2025-05-10",
        "visto_em": "2025-05-10",
    }
    assert lido.fontes == {"aneel-fiscalizacao"}
    assert lido.linhas == 2


def test_linha_que_saiu_do_arquivo_e_a_de_outra_empresa_nao_saem(base):
    texto = str(_ler(base, tabelas_por_cnpj.REGULADOS).corpo)  # type: ignore[union-attr]
    assert "3106200" not in texto
    assert "999" not in texto
    assert ": 5," not in texto


def test_linha_publicada_depois_do_dia_nao_sai_e_depois_sai(base):
    antes = _ler(base, tabelas_por_cnpj.REGULADOS).corpo  # type: ignore[union-attr]
    assert "2025-04-01" not in str(antes)
    depois = _ler(base, tabelas_por_cnpj.REGULADOS, dia=date(2025, 8, 1)).corpo  # type: ignore[union-attr]
    assert _valores(depois["indicadores_comerciais_da_aneel"], "referencia") == [
        "2025-04-01"
    ]


def test_cortar_o_futuro_nao_muda_o_passado(tmp_path, base):
    sem_futuro = tmp_path / "sem"
    publico = lambda t: t[t["disponivel_em"] <= DIA]
    gravar(sem_futuro, ANEEL, publico(_aneel()))
    gravar(sem_futuro, FII, publico(_fii()))
    gravar(sem_futuro, FIP, publico(_fip()))
    for bloco, cnpj in (
        (tabelas_por_cnpj.REGULADOS, EMPRESA),
        (tabelas_por_cnpj.INFORMES_DO_FUNDO, FUNDO),
    ):
        assert _ler(sem_futuro, bloco, cnpj).corpo == _ler(base, bloco, cnpj).corpo  # type: ignore[union-attr]


def test_informe_sai_um_por_mes_na_versao_mais_nova_ja_entregue_e_so_do_fundo_pedido(
    base,
):
    sub = _ler(base, tabelas_por_cnpj.INFORMES_DO_FUNDO, FUNDO).corpo[
        "informe_mensal_do_fii"
    ]  # type: ignore[union-attr]
    assert _valores(sub, "referencia") == ["2025-05-01", "2025-04-01"]
    assert _valores(sub, "versao") == [1, 2]
    assert _valores(sub, "patrimonio_liquido") == [120.0, 110.0]
    assert "7.0" not in str(sub)  # o outro fundo da mesma raiz


def test_campo_negado_pelo_nome_nunca_e_lido(base):
    corpo = _ler(base, tabelas_por_cnpj.INFORMES_DO_FUNDO, FUNDO).corpo  # type: ignore[union-attr]
    chaves = aj.chaves_de(corpo)
    assert not chaves & {"cotistas_pessoa_fisica", "cnpj_administrador"}
    assert "12345678000199" not in str(corpo)


def test_informe_do_fip_leva_a_fonte_pela_periodicidade(base):
    sub = _ler(base, tabelas_por_cnpj.INFORMES_DO_FUNDO, FUNDO).corpo["informe_do_fip"]  # type: ignore[union-attr]
    fontes = [item["patrimonio_liquido"]["fonte"] for item in sub["itens"]]
    assert fontes == ["cvm-fip-trimestral", "cvm-fip-quadrimestral"]


def test_fonte_que_o_portao_nao_libera_nao_sai_nem_pela_linha(base):
    def so_trimestral(fonte, _campo, _derivado):
        return fonte != "cvm-fip-quadrimestral"

    corpo = _ler(
        base, tabelas_por_cnpj.INFORMES_DO_FUNDO, FUNDO, permitido=so_trimestral
    ).corpo  # type: ignore[union-attr]
    assert corpo["informe_do_fip"]["fontes"] == ["cvm-fip-trimestral"]
    assert _valores(corpo["informe_do_fip"], "competencia") == ["2025-03-31"]


def test_entrada_sem_campo_liberado_nao_aparece_e_bloco_sem_nenhuma_volta_none(base):
    def sem_idss(fonte, _campo, _derivado):
        return fonte != "ans-qualidade"

    corpo = _ler(base, tabelas_por_cnpj.REGULADOS, permitido=sem_idss).corpo  # type: ignore[union-attr]
    assert set(corpo) == {"indicadores_comerciais_da_aneel"}
    assert _ler(base, tabelas_por_cnpj.REGULADOS, permitido=lambda *_: False) is None


def test_tabela_fora_da_base_responde_nao_achou_com_a_cobertura(base):
    corpo = _ler(base, tabelas_por_cnpj.REGULADOS).corpo  # type: ignore[union-attr]
    idss = corpo["idss_da_ans"]
    assert idss["achou"] is False
    assert idss["itens"] == []
    assert idss["cobertura"]
    assert por_tabela.vazio({"idss_da_ans": idss})
    assert not por_tabela.vazio(corpo)


def test_lista_maior_que_o_limite_sai_cortada(base):
    sub = _ler(base, tabelas_por_cnpj.REGULADOS, linhas=1).corpo[
        "indicadores_comerciais_da_aneel"
    ]  # type: ignore[union-attr]
    assert sub["cortada"] is True
    assert _valores(sub, "municipio_ibge") == ["3304557"]


def test_cnpj_invalido_e_erro_de_quem_chama(base):
    with pytest.raises(ValueError, match="CNPJ inválido"):
        _ler(base, tabelas_por_cnpj.REGULADOS, cnpj="123")


# ---------------------------------------------------------------- a análise, com o portão de verdade


@pytest.fixture
def pasta_da_analise(tmp_path, monkeypatch):
    pasta = socios_de_mentira.base_com_socios(tmp_path)
    gravar(pasta, ANEEL, _aneel())
    monkeypatch.setattr(rotas, "abrir_porta", lambda banco_: Porta(pasta, banco_))
    return pasta


def _regras(cheias=analise_de_mentira.DO_PERFIL) -> portao.Regras:
    """As regras de verdade com o perfil pronto e as tabelas do lote 1 só na prontidão de piloto, como hoje (a
    prova do piloto com a data do teste: a de verdade é de depois de `AGORA`)."""
    prova = Prova(AGORA.date(), "conferida no teste", "teste")
    versoes = prontidao.versoes_maiores()
    vigentes = portao.regras_vigentes()
    do_lote = {e.tabela for e in tabelas_por_cnpj.REGISTRO}
    assert do_lote <= set(vigentes.prontidao_de_piloto)  # hoje as seis estão no piloto
    return dataclasses.replace(
        vigentes,
        prontidao={t: Prontidao(versoes[t], prova, prova, prova) for t in cheias},
        prontidao_de_piloto={
            **vigentes.prontidao_de_piloto,
            **{t: ProntidaoDePiloto(versoes[t], prova, prova) for t in do_lote},
        },
    )


def _marca_de_piloto(banco, ator, org):
    with banco.begin() as conexao:
        cb.conceder_direito(
            conexao,
            organizacao_id=org.id,
            conjunto=cb.CONJUNTO_DO_PILOTO,
            finalidade="analise",
            vigente_desde=date(2026, 11, 1),
            ator_id=ator.id,
            agora=AGORA,
        )


def _organizacao(banco, ator, nome, *conjuntos, piloto=False):
    org = aj.organizacao(banco, ator, nome)
    chave = aj.chave(banco, ator, org)
    for conjunto in conjuntos:
        aj.contrato(banco, ator, org, conjunto=conjunto)
    if piloto:
        _marca_de_piloto(banco, ator, org)
    return chave


def _analise(monkeypatch, chave, regras=_regras, **parametros):
    monkeypatch.setattr(rotas, "regras_da_api", regras)
    cliente = aj.cliente_da_api(monkeypatch, AGORA)
    return cliente.get(
        f"/data/v1/companies/{EMPRESA}/analysis",
        params={"known_at": DIA.isoformat(), **parametros},
        headers=aj.bearer(chave.valor),
    )


@pytest.mark.usefixtures("pasta_da_analise")
def test_organizacao_do_piloto_recebe_os_regulados_com_o_aviso_em_cada_campo(
    banco, monkeypatch
):
    ator = aj.admin(banco)
    chave = _organizacao(banco, ator, "Alfa", ficha.CONJUNTO, piloto=True)
    corpo = _analise(monkeypatch, chave).json()
    regulados = corpo["blocks"]["regulated_activities"]["aneel_commercial_indicators"]
    assert regulados["found"] is True
    campo = regulados["items"][0]["active_consumer_units"]
    assert campo["value"] == 300
    assert campo["source"] == "aneel-fiscalizacao"
    assert campo["published_at"] == "2025-05-10"
    assert campo["pilot"] is True
    assert campo["pilot_notice"] == AVISO_DE_PILOTO
    assert corpo["pilot_notice"] == AVISO_DE_PILOTO
    assert "aneel-fiscalizacao" in {f["source"] for f in corpo["sources"]}
    assert (
        corpo["requests_used"] == 1
    )  # o cadastro e os regulados contam no mesmo conjunto


@pytest.mark.usefixtures("pasta_da_analise")
def test_sem_a_marca_de_piloto_ou_sem_o_conjunto_os_regulados_nao_aparecem_nem_pelo_nome(
    banco, monkeypatch
):
    ator = aj.admin(banco)
    sem_marca = _organizacao(banco, ator, "Beta", ficha.CONJUNTO)
    sem_conjunto = _organizacao(banco, ator, "Gama", empresas.CONJUNTO, piloto=True)
    for chave in (sem_marca, sem_conjunto):
        resposta = _analise(monkeypatch, chave)
        assert resposta.status_code == 200
        texto = resposta.text
        for nome in (
            "regulated_activities",
            "aneel_commercial_indicators",
            "aneel-fiscalizacao",
            "3304557",
        ):
            assert nome not in texto
        assert "pilot_notice" not in texto


def test_resposta_de_quem_nao_ve_o_bloco_e_a_mesma_com_ou_sem_o_dado_na_base(
    tmp_path, banco, monkeypatch
):
    ator = aj.admin(banco)
    chave = _organizacao(banco, ator, "Beta", ficha.CONJUNTO)
    respostas = []
    for nome, linhas in (("com", _aneel()), ("sem", _aneel().iloc[0:0])):
        pasta = socios_de_mentira.base_com_socios(tmp_path / nome)
        gravar(pasta, ANEEL, linhas)
        monkeypatch.setattr(
            rotas, "abrir_porta", lambda banco_, pasta=pasta: Porta(pasta, banco_)
        )
        respostas.append(_analise(monkeypatch, chave).content)
    assert respostas[0] == respostas[1]


def test_linha_do_registro_no_profiles_nao_abre_o_perfil_sem_um_campo_da_ficha():
    """Regressão da revisão cruzada: só a ANEEL liberada em `profiles` (nenhum campo da ficha) não escolhe o
    perfil como cadastro; o cadastro é a situação na Receita, e o bloco dos regulados abre."""
    so_a_aneel = {
        ("profiles", "analise", fonte, nome)
        for entrada in tabelas_por_cnpj.do_bloco(tabelas_por_cnpj.REGULADOS)
        for fonte, nome in por_tabela.pares(entrada)
    }
    da_receita = {("companies", "analise", "rfb-cnpj", "razao_social")}
    cadastro, abertos = analise.blocos_abertos(so_a_aneel | da_receita)
    assert cadastro is analise.CADASTROS[1]  # a situação na Receita, não o perfil
    assert tabelas_por_cnpj.REGULADOS in {bloco.nome for bloco in abertos}
    assert analise.blocos_abertos(so_a_aneel)[0] is None


@pytest.mark.usefixtures("pasta_da_analise")
def test_com_a_prontidao_cheia_sai_para_quem_tem_o_conjunto_sem_o_aviso(
    banco, monkeypatch
):
    ator = aj.admin(banco)
    chave = _organizacao(banco, ator, "Beta", ficha.CONJUNTO)
    corpo = _analise(
        monkeypatch,
        chave,
        regras=lambda: _regras((*analise_de_mentira.DO_PERFIL, ANEEL)),
    ).json()
    campo = corpo["blocks"]["regulated_activities"]["aneel_commercial_indicators"][
        "items"
    ][0]["active_consumer_units"]
    assert "pilot" not in campo
    assert "pilot_notice" not in corpo


@pytest.mark.usefixtures("pasta_da_analise")
def test_analise_como_era_nao_ve_o_mes_publicado_depois(banco, monkeypatch):
    ator = aj.admin(banco)
    chave = _organizacao(banco, ator, "Alfa", ficha.CONJUNTO, piloto=True)
    antes = _analise(monkeypatch, chave).json()
    assert "2025-04-01" not in str(antes["blocks"]["regulated_activities"])
    depois = _analise(monkeypatch, chave, known_at="2025-08-01").json()
    itens = depois["blocks"]["regulated_activities"]["aneel_commercial_indicators"][
        "items"
    ]
    assert [i["reference_period"]["value"] for i in itens] == ["2025-04-01"]


@pytest.mark.usefixtures("pasta_da_analise")
def test_sancoes_ambiente_e_lista_suja_dizem_nao_disponivel_sem_o_motivo(
    banco, monkeypatch
):
    ator = aj.admin(banco)
    chave = _organizacao(banco, ator, "Alfa", ficha.CONJUNTO, piloto=True)
    fora = _analise(monkeypatch, chave).json()["not_included"]
    marcados = [item for item in fora if item.endswith(": não disponível nesta chave")]
    assert [m.split("(")[1][:3] for m in marcados] == ["CGU", "IBA", "MTE"]
    assert "interno" not in str(fora)
    assert "ADR" not in str(fora)
