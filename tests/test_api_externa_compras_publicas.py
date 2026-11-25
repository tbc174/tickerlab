"""O cadastro de fornecedores do SICAF e o Banco de Preços em Saúde (BPS) na análise completa, só no conjunto de
compras públicas (`public_procurement`; linha 988, ADR 0122, Emenda 2: cada lote num conjunto próprio, desligado por
padrão).

Base de mentira, sem internet; os CNPJs são de ninguém. O leitor (`conjuntos/por_tabela.py`) com a porta de verdade,
a rota da análise com o portão e as linhas de direito de verdade e a tela do analista (a conta do app, com ou sem
organização). Riscos: a licença deixar de travar fora do conjunto (no `profiles`, no conjunto ampliado, na tela, para
outra organização), linha de pessoa física saindo ou contando, o número do processo de compra do BPS saindo, bloco
fechado vazando pelo nome ou pelo tamanho (duas organizações, resposta idêntica com e sem o dado), o BPS abrindo sem a
prontidão (hoje ele não tem nenhuma) e olhar o futuro.
"""

import dataclasses
from datetime import date

import pandas as pd
import pytest

from base import prontidao
from base.porta import Porta
from base.prontidao import Prontidao, ProntidaoDePiloto, Prova
from src import portao_externo as portao
from src.analista import analise as analise_da_tela
from src.api_externa import rotas, tabelas_por_cnpj
from src.api_externa.conjuntos import analise, ficha
from src.banco import coletas
from src.portao_externo import Finalidade
from tests import ajudantes_da_api_externa as aj
from tests import test_api_externa_analise as analise_de_mentira
from tests import test_api_externa_socios_pj as socios_de_mentira
from tests.test_api_externa_tabelas_por_cnpj import (
    AGORA,
    DIA,
    EMPRESA,
    OUTRA_RAIZ,
    RAIZ,
    _ler,
    _organizacao,
    gravar,
)

SICAF = "comprasgov_sicaf"
BPS = "bps_compras"
TABELAS = (SICAF, BPS)
FONTE_DO_SICAF = "comprasgov-sicaf"
FONTE_DO_BPS = "bps"
FONTES = (FONTE_DO_SICAF, FONTE_DO_BPS)
# os arquivos de verdade do SICAF (`base/arquivo/destinos.py`): a família inteira vai para a mesma tabela
ARQUIVOS_DO_SICAF = ("comprasgov-sicaf-ativos", "comprasgov-sicaf-inativos")
BLOCO = tabelas_por_cnpj.COMPRAS_PUBLICAS
CONJUNTO = tabelas_por_cnpj.CONJUNTO_DE_COMPRAS_PUBLICAS
DE_PESSOA = "LINHA-DE-PESSOA"  # marca do texto que só a linha de pessoa tem
PROCESSO = (
    "PROCESSO-QUE-FICA-EM-CASA"  # o número do processo de compra do BPS: nunca sai
)
NOMES_DE_FORA = (
    "public_procurement",
    "sicaf_supplier_registration",
    "bps_health_purchases",
    *FONTES,
)


def _comum(tabela: pd.DataFrame) -> pd.DataFrame:
    """As colunas de toda tabela ligada pelo CNPJ: a raiz, o id, a origem e as datas."""
    for coluna in ("disponivel_em", "visto_em"):
        tabela[coluna] = pd.to_datetime(tabela[coluna]).dt.date
    return tabela.assign(
        cnpj_basico=tabela["cnpj"].str[:8],
        id_na_fonte=[f"id-{i}" for i in range(len(tabela))],
        origem_sha256="0" * 64,
    )


def _sicaf_linha(cnpj: str = EMPRESA, **diferente) -> dict:
    linha = {
        "cnpj": cnpj,
        "ativo": True,
        "habilitado_a_licitar": True,
        "cnae": "4644301",
        "descricao_do_cnae": "Comércio atacadista de medicamentos",
        "natureza_juridica": "2062",
        "descricao_da_natureza_juridica": "Sociedade Empresária Limitada",
        "porte": "05",
        "descricao_do_porte": "Demais",
        "municipio": "São Paulo",
        "uf": "SP",
        "disponivel_em": "2025-06-01",
        "consta": True,
        "trata_como_pessoa": False,
    }
    return linha | diferente


def _sicaf() -> pd.DataFrame:
    linhas = [
        _sicaf_linha(),
        _sicaf_linha(
            RAIZ + "000270", descricao_do_cnae="SAIU-DO-ARQUIVO", consta=False
        ),
        _sicaf_linha(
            RAIZ + "000351", descricao_do_cnae=DE_PESSOA, trata_como_pessoa=True
        ),
        _sicaf_linha(
            RAIZ + "000432", descricao_do_cnae=DE_PESSOA, trata_como_pessoa=None
        ),
        _sicaf_linha(OUTRA_RAIZ + "000100", descricao_do_cnae="OUTRA-EMPRESA"),
        _sicaf_linha(
            RAIZ + "000513", descricao_do_cnae="DO-FUTURO", disponivel_em="2025-09-01"
        ),
    ]
    tabela = pd.DataFrame(linhas)
    tabela["visto_em"] = tabela["disponivel_em"]
    return _comum(tabela)


def _bps_linha(cnpj: str = EMPRESA, **diferente) -> dict:
    linha = {
        "cnpj": cnpj,
        "data_da_compra": "2025-03-10",
        "ano_da_compra": 2025,
        "instituicao": "Secretaria Estadual de Saúde",
        "cnpj_da_instituicao": "46374500000194",
        "esfera": "Estadual",
        "uf": "SP",
        "municipio": "São Paulo",
        "catmat": "BR0267611",
        "item": "Dipirona 500 mg, comprimido",
        "descricao_do_pdm": "Dipirona",
        "descricao_da_classe": "Analgésicos",
        "generico": "Sim",
        "registro_na_anvisa": "100000000",
        "cnpj_do_fabricante": "60318797000100",
        "cnpj_basico_do_fabricante": "60318797",
        "tipo_de_compra": "Administrativa",
        "unidade_de_fornecimento": "Comprimido",
        "quantidade": 10000.0,
        "preco_unitario": 0.12,
        "preco_total": 1200.0,
        "processo_de_compra": PROCESSO,
        "disponivel_em": "2025-04-01",
        "consta": True,
        "trata_como_pessoa": False,
    }
    return linha | diferente


def _bps() -> pd.DataFrame:
    linhas = [
        _bps_linha(),
        _bps_linha(item="SAIU-DO-ARQUIVO", consta=False),
        _bps_linha(RAIZ + "000270", item=DE_PESSOA, trata_como_pessoa=True),
        _bps_linha(RAIZ + "000351", item=DE_PESSOA, trata_como_pessoa=None),
        _bps_linha(OUTRA_RAIZ + "000100", item="OUTRA-EMPRESA"),
        _bps_linha(
            item="DO-FUTURO", data_da_compra="2025-08-01", disponivel_em="2025-09-01"
        ),
    ]
    tabela = pd.DataFrame(linhas)
    tabela["visto_em"] = tabela["disponivel_em"]
    tabela["data_da_compra"] = pd.to_datetime(tabela["data_da_compra"]).dt.date
    return _comum(tabela)


def _gravar_tudo(pasta, ate: date | None = None) -> None:
    for tabela, linhas in ((SICAF, _sicaf()), (BPS, _bps())):
        if ate is not None:
            linhas = linhas[linhas["disponivel_em"] <= ate]
        gravar(pasta, tabela, linhas)


@pytest.fixture
def base(tmp_path):
    pasta = tmp_path / "base"
    _gravar_tudo(pasta)
    return pasta


def _corpo(pasta, dia=DIA) -> dict:
    lido = _ler(pasta, BLOCO, dia=dia)
    assert lido is not None
    return lido.corpo


# ---------------------------------------------------------------- o registro e as marcas


def test_as_duas_tabelas_estao_so_no_conjunto_de_compras_publicas_com_a_marca_de_pessoa():
    entradas = {
        e.tabela: e for e in tabelas_por_cnpj.REGISTRO if e.conjunto == CONJUNTO
    }
    assert set(entradas) == set(TABELAS)
    assert {f for e in entradas.values() for f in e.fontes} == set(FONTES)
    for tabela in TABELAS:
        assert [
            e.conjunto for e in tabelas_por_cnpj.REGISTRO if e.tabela == tabela
        ] == [CONJUNTO]
    for entrada in entradas.values():
        assert entrada.bloco == BLOCO and entrada.onde_sai == tabelas_por_cnpj.ANALISE
        assert entrada.marca_de_pessoa == tabelas_por_cnpj.TRATA_COMO_PESSOA
        assert set(entrada.campos).isdisjoint(
            {"nome", "cnpj", "razao_social", "processo_de_compra"}
        )
        assert not any("cpf" in campo for campo in entrada.campos)


def test_a_licenca_deixa_de_travar_so_no_conjunto_de_compras_publicas():
    for fonte in (*FONTES, *ARQUIVOS_DO_SICAF):
        assert coletas.sai_no_conjunto_de_compras_publicas(fonte, CONJUNTO), fonte
        for outro in (
            "profiles",
            "assets",
            coletas.CONJUNTO_DE_INTEGRIDADE,
            coletas.CONJUNTO_SEM_TRAVA_DE_LICENCA,
        ):
            assert not coletas.sai_no_conjunto_de_compras_publicas(fonte, outro), (
                fonte,
                outro,
            )
            assert not coletas.sai_sem_trava_de_licenca(fonte, outro), (fonte, outro)
    # a família inteira não entra: só as fontes do lote, pelo prefixo
    for fora in (
        "comprasgov-contratos",
        "comprasgov",
        "bpsx",
        "anatel-pados",
        "mte-pat",
    ):
        assert not coletas.sai_no_conjunto_de_compras_publicas(fora, CONJUNTO), fora


def test_o_conjunto_ampliado_nao_abre_as_compras_e_o_de_compras_nao_abre_o_ampliado():
    for fonte in (*FONTES, *ARQUIVOS_DO_SICAF):
        assert not coletas.sai_sem_trava_de_licenca(
            fonte, coletas.CONJUNTO_SEM_TRAVA_DE_LICENCA
        ), fonte
    for fonte in coletas.FONTES_SEM_TRAVA_DE_LICENCA:
        assert not coletas.sai_no_conjunto_de_compras_publicas(fonte, CONJUNTO), fonte


def test_fora_do_conjunto_o_portao_segue_negando_pela_marca():
    hoje = AGORA.date()
    regras = portao.regras_vigentes()
    for fonte in (*FONTES, *ARQUIVOS_DO_SICAF):
        assert portao._negacao_das_marcas(fonte, CONJUNTO, hoje, regras) is None, fonte
        for outro in ("profiles", coletas.CONJUNTO_SEM_TRAVA_DE_LICENCA):
            assert portao._negacao_das_marcas(fonte, outro, hoje, regras) is not None, (
                fonte,
                outro,
            )


def _regras(*cheias: str) -> portao.Regras:
    """As regras de verdade com o perfil e as tabelas pedidas com a prontidão cheia (a prova com a data do teste)."""
    prova = Prova(AGORA.date(), "conferida no teste", "teste")
    versoes = prontidao.versoes_maiores()
    return dataclasses.replace(
        portao.regras_vigentes(),
        prontidao={
            t: Prontidao(versoes[t], prova, prova, prova)
            for t in (*analise_de_mentira.DO_PERFIL, *cheias)
        },
    )


def test_o_portao_de_verdade_libera_so_no_conjunto():
    regras = _regras(*TABELAS)
    campos = {FONTE_DO_SICAF: "habilitado_a_licitar", FONTE_DO_BPS: "preco_unitario"}
    for fonte, campo in campos.items():
        for conjunto in (
            CONJUNTO,
            "profiles",
            "assets",
            coletas.CONJUNTO_DE_INTEGRIDADE,
            coletas.CONJUNTO_SEM_TRAVA_DE_LICENCA,
        ):
            pedido = portao.Pedido(
                fonte,
                conjunto,
                campo,
                portao.Canal.API_EXTERNA,
                portao.Finalidade.ANALISE,
            )
            decisao = portao.decidir(pedido, AGORA.date(), regras)
            assert decisao.libera is (conjunto == CONJUNTO), (fonte, conjunto, decisao)


def test_as_compras_saem_so_como_publicadas():
    """Nenhuma conta nossa sobre o registro, mesmo no conjunto: preço médio, ranking e afins ficam de fora (o BPS
    por ser de licença a confirmar, o SICAF por não ter linha de direito de campo derivado)."""
    for fonte in FONTES:
        pedido = portao.Pedido(
            fonte,
            CONJUNTO,
            "qualquer_campo",
            portao.Canal.API_EXTERNA,
            portao.Finalidade.ANALISE,
            derivado=True,
        )
        decisao = portao.decidir(pedido, AGORA.date(), _regras(*TABELAS))
        assert not decisao.libera, (fonte, decisao)


def test_toda_fonte_do_lote_tem_atribuicao():
    from src.api_externa.envelope import ATRIBUICOES_DA_API

    for fonte in FONTES:
        assert ATRIBUICOES_DA_API[fonte]


def test_o_bloco_nao_entra_na_lista_do_que_a_analise_nao_consulta():
    """Para a chave sem o conjunto, o bloco nem é citado: não vaza pelo nome."""
    assert analise.ainda_nao_traz(()) == list(analise.AINDA_NAO_TRAZ)
    assert not any(
        "SICAF" in frase or "Preços em Saúde" in frase
        for frase in analise.AINDA_NAO_TRAZ
    )


# ---------------------------------------------------------------- o leitor


def test_so_a_linha_de_empresa_que_consta_sai(base):
    corpo = _corpo(base)
    sicaf = corpo["cadastro_no_sicaf"]
    assert [i["descricao_do_cnae"]["valor"] for i in sicaf["itens"]] == [
        "Comércio atacadista de medicamentos"
    ]
    assert sicaf["itens"][0]["habilitado_a_licitar"]["fonte"] == FONTE_DO_SICAF
    bps = corpo["compras_no_bps"]
    assert [i["item"]["valor"] for i in bps["itens"]] == ["Dipirona 500 mg, comprimido"]
    assert bps["itens"][0]["preco_unitario"]["valor"] == 0.12
    assert bps["itens"][0]["preco_unitario"]["fonte"] == FONTE_DO_BPS
    texto = str(corpo)
    for fora in (DE_PESSOA, "SAIU-DO-ARQUIVO", "OUTRA-EMPRESA", "DO-FUTURO", PROCESSO):
        assert fora not in texto


def test_o_processo_de_compra_nunca_sai_nem_pelo_nome(base):
    assert "processo_de_compra" not in str(_corpo(base))


def test_cortar_o_futuro_nao_muda_o_passado(tmp_path, base):
    sem_futuro = tmp_path / "sem"
    _gravar_tudo(sem_futuro, ate=DIA)
    assert _corpo(sem_futuro) == _corpo(base)
    depois = str(_corpo(base, dia=date(2025, 9, 30)))
    assert "DO-FUTURO" in depois  # a compra de agosto aparece quando fica pública


# ---------------------------------------------------------------- a análise, com o portão de verdade


def _analise(monkeypatch, valor_da_chave, regras):
    monkeypatch.setattr(rotas, "regras_da_api", regras)
    cliente = aj.cliente_da_api(monkeypatch, AGORA)
    return cliente.get(
        f"/data/v1/companies/{EMPRESA}/analysis",
        params={"known_at": DIA.isoformat()},
        headers=aj.bearer(valor_da_chave),
    )


def _pasta(tmp_path, monkeypatch, nome="base", com_dado=True):
    pasta = socios_de_mentira.base_com_socios(tmp_path / nome)
    if com_dado:
        _gravar_tudo(pasta)
    monkeypatch.setattr(rotas, "abrir_porta", lambda banco_: Porta(pasta, banco_))
    return pasta


def _com_as_duas():
    return _regras(*TABELAS)


def test_com_o_conjunto_o_bloco_sai_com_fonte_e_data(tmp_path, banco, monkeypatch):
    _pasta(tmp_path, monkeypatch)
    chave = _organizacao(banco, aj.admin(banco), "Alfa", ficha.CONJUNTO, CONJUNTO)
    resposta = _analise(monkeypatch, chave.valor, _com_as_duas)
    assert resposta.status_code == 200
    bloco = resposta.json()["blocks"]["public_procurement"]
    sicaf = bloco["sicaf_supplier_registration"]
    assert sicaf["found"] is True
    habilitado = sicaf["items"][0]["qualified_to_bid"]
    assert habilitado["value"] is True and habilitado["source"] == FONTE_DO_SICAF
    assert habilitado["published_at"] == "2025-06-01"
    preco = bloco["bps_health_purchases"]["items"][0]["unit_price_brl"]
    assert preco["value"] == 0.12 and preco["source"] == FONTE_DO_BPS
    fontes = {f["source"] for f in resposta.json()["sources"]}
    assert set(FONTES) <= fontes
    for nunca in (
        DE_PESSOA,
        "OUTRA-EMPRESA",
        PROCESSO,
        "processo_de_compra",
        "purchase_process",
    ):
        assert nunca not in resposta.text


def test_sem_o_conjunto_nada_aparece_nem_pelo_nome_nem_pelo_tamanho(
    tmp_path, banco, monkeypatch
):
    chave = _organizacao(banco, aj.admin(banco), "Beta", ficha.CONJUNTO)
    respostas = []
    for nome, com_dado in (("com", True), ("sem", False)):
        _pasta(tmp_path, monkeypatch, nome, com_dado=com_dado)
        resposta = _analise(monkeypatch, chave.valor, _com_as_duas)
        assert resposta.status_code == 200
        respostas.append(resposta.content)
    assert respostas[0] == respostas[1]
    for nome in NOMES_DE_FORA:
        assert nome not in respostas[0].decode()


def test_o_conjunto_de_outra_organizacao_nao_abre_nada(tmp_path, banco, monkeypatch):
    _pasta(tmp_path, monkeypatch)
    ator = aj.admin(banco)
    alfa = _organizacao(banco, ator, "Alfa", ficha.CONJUNTO, CONJUNTO)
    beta = _organizacao(banco, ator, "Beta", ficha.CONJUNTO)
    assert "public_procurement" in _analise(monkeypatch, alfa.valor, _com_as_duas).text
    texto = _analise(monkeypatch, beta.valor, _com_as_duas).text
    for nome in NOMES_DE_FORA:
        assert nome not in texto


@pytest.mark.parametrize(
    "outro", [tabelas_por_cnpj.INTEGRIDADE, tabelas_por_cnpj.SEM_TRAVA_DE_LICENCA]
)
def test_os_outros_conjuntos_por_contrato_nao_abrem_as_compras(
    tmp_path, banco, monkeypatch, outro
):
    _pasta(tmp_path, monkeypatch)
    chave = _organizacao(banco, aj.admin(banco), "Alfa", ficha.CONJUNTO, outro)
    texto = _analise(monkeypatch, chave.valor, _com_as_duas).text
    for nome in NOMES_DE_FORA:
        assert nome not in texto


def test_chave_invalida_nao_ve_nada(tmp_path, monkeypatch):
    _pasta(tmp_path, monkeypatch)
    resposta = _analise(monkeypatch, "tl_chave_que_nao_existe", _com_as_duas)
    assert resposta.status_code == 401
    for nome in NOMES_DE_FORA:
        assert nome not in resposta.text


def _como_hoje():
    """As regras de hoje: o SICAF só na prontidão de piloto (a prova com a data do teste: a de verdade é de depois
    de `AGORA`) e o BPS sem prontidão nenhuma, até a causa da queda de 2023 (linha 1029)."""
    prova = Prova(AGORA.date(), "conferida no teste", "teste")
    versoes = prontidao.versoes_maiores()
    vigentes = _regras()
    assert (
        SICAF in vigentes.prontidao_de_piloto
        and BPS not in vigentes.prontidao_de_piloto
    )
    assert BPS not in vigentes.prontidao
    return dataclasses.replace(
        vigentes,
        prontidao_de_piloto={
            **vigentes.prontidao_de_piloto,
            SICAF: ProntidaoDePiloto(versoes[SICAF], prova, prova),
        },
    )


def test_como_hoje_so_o_piloto_com_o_conjunto_ve_o_sicaf_e_o_bps_nunca_sai(
    tmp_path, banco, monkeypatch
):
    _pasta(tmp_path, monkeypatch)
    ator = aj.admin(banco)
    com_piloto = _organizacao(
        banco, ator, "Alfa", ficha.CONJUNTO, CONJUNTO, piloto=True
    )
    sem_piloto = _organizacao(banco, ator, "Beta", ficha.CONJUNTO, CONJUNTO)
    so_piloto = _organizacao(banco, ator, "Gama", ficha.CONJUNTO, piloto=True)
    resposta = _analise(monkeypatch, com_piloto.valor, _como_hoje)
    assert resposta.status_code == 200
    bloco = resposta.json()["blocks"]["public_procurement"]
    assert bloco["sicaf_supplier_registration"]["found"] is True
    assert "bps_health_purchases" not in resposta.text and FONTE_DO_BPS not in {
        f["source"] for f in resposta.json()["sources"]
    }
    for chave in (sem_piloto, so_piloto):
        texto = _analise(monkeypatch, chave.valor, _como_hoje).text
        for nome in NOMES_DE_FORA:
            assert nome not in texto


# ---------------------------------------------------------------- a tela do analista (conta do app, sem contrato)


def test_as_compras_nunca_abrem_na_tela_mesmo_com_o_portao_liberando(monkeypatch):
    """A conta do app, com ou sem organização (de piloto ou não), não tem o contrato da organização: o conjunto
    fica fora da tela mesmo que o portão libere, como a integridade e as fontes ampliadas."""
    monkeypatch.setattr(
        analise_da_tela,
        "decidir",
        lambda *_args, **_kw: type("Libera", (), {"libera": True})(),
    )
    regras = _com_as_duas()
    for piloto in (False, True):
        liberadas = analise_da_tela.liberadas_na_tela(
            AGORA.date(), regras, piloto=piloto
        )
        assert liberadas
        assert CONJUNTO not in {c for c, *_ in liberadas}
        fechado = analise_da_tela.portao_da_tela(AGORA.date(), regras, piloto=piloto)(
            CONJUNTO, Finalidade.ANALISE.value
        )
        for fonte in (*FONTES, *ARQUIVOS_DO_SICAF):
            assert not fechado(fonte, "habilitado_a_licitar", False), fonte


def test_a_analise_da_tela_nao_traz_o_bloco(tmp_path):
    pasta = socios_de_mentira.base_com_socios(tmp_path / "tela")
    _gravar_tudo(pasta)
    for piloto in (False, True):
        with Porta(pasta) as porta:
            resposta = analise_da_tela.analise(
                porta, EMPRESA, hoje=AGORA.date(), regras=_com_as_duas(), piloto=piloto
            )
        texto = str(resposta.corpo)
        assert BLOCO not in {b["nome"] for b in resposta.corpo.get("blocos", [])}
        for nunca in ("SICAF", "Preços em Saúde", "Dipirona", PROCESSO, DE_PESSOA):
            assert nunca not in texto
