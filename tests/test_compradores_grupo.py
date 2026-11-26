"""Quem já se mexeu no setor soma pelo grupo e separa compra de reorganização (linha 1043).

Base de mentira, só empresa (raízes de ninguém, nada de pessoa física), montada com o `Mundo` do teste dos 29 vazio.
O que se confere:

- a entrada é julgada na data dela: reorganização (a sócia que sai é do grupo do comprador) não conta e vai para
  `entradas_no_grupo`, com a raiz que liga as duas; a controladora que entra junto com o comprador não faz da compra
  uma entrada do mesmo grupo;
- compradores com uma sócia PJ em comum (até 3 níveis acima) ganham o bloco `grupo` e a ordem é pelas empresas do
  setor em que o grupo entrou;
- sem olhar o futuro: a sócia que só entrou no comprador depois do dia pedido não liga ninguém;
- a API traduz todos os nomes novos.
"""

import json
from datetime import date

import pytest

from base.porta import Porta
from src.api_externa import nomes
from src.api_externa.conjuntos import compradores
from src.novidades_da_pesquisa import achar_cpf
from tests.test_compradores_29_negocios import CLASSE, Mundo

HOJE = date(2026, 11, 10)


@pytest.fixture(autouse=True)
def _cache_limpo():
    compradores.zerar_o_cache()
    yield
    compradores.zerar_o_cache()


def _corpo(mundo: Mundo, tmp_path, dia: date = HOJE) -> dict:
    base = tmp_path / "base"
    mundo.gravar(base)
    leitor = compradores.LeitorDeCompradores(Porta(base), lambda *_: True, 50)
    servido = leitor.compradores(
        compradores.PedidoDeCompradores(CLASSE, None, 5, 50), dia
    )
    assert servido is not None
    return servido.corpo


def _linha(corpo: dict, raiz: str) -> dict:
    (achado,) = [c for c in corpo["compradores"] if c["raiz_do_cnpj"] == raiz]
    return achado


def _entradas_de(linha: dict) -> set[str]:
    prova = linha["provas"].get(compradores.ENTROU, {"exemplos": []})
    return {e["empresa_do_setor"]["raiz_do_cnpj"] for e in prova["exemplos"]}


def _reorganizacao(mundo: Mundo) -> tuple[str, str, str, str]:
    """A controladora passa ao comprador a empresa do setor (2024-05-10); o comprador também compra outra de um
    terceiro, para estar na lista. Devolve (comprador, controladora, empresa da reorganização, empresa comprada)."""
    comprador, controladora = mundo.comprador(), mundo.comprador("33")
    reorganizada, comprada = mundo.empresa("20"), mundo.empresa("20")
    mundo.entrar(controladora, comprador, "2015-01-01")
    mundo.entrar(controladora, reorganizada, "2015-01-01")
    mundo.entrar(comprador, reorganizada, "2024-05-10")
    mundo.sair(controladora, reorganizada, "2015-01-01", "2024-05-10")
    mundo.entrar(comprador, comprada, "2025-02-10")
    return comprador, controladora, reorganizada, comprada


def test_reorganizacao_nao_conta_e_sai_em_entradas_no_grupo(tmp_path):
    mundo = Mundo(montar=False)
    comprador, controladora, reorganizada, comprada = _reorganizacao(mundo)
    corpo = _corpo(mundo, tmp_path)
    linha = _linha(corpo, comprador)
    assert _entradas_de(linha) == {comprada}
    assert linha["provas"][compradores.ENTROU]["quantas"] == 1
    no_grupo = linha["entradas_no_grupo"]
    assert no_grupo["quantas"] == 1
    (exemplo,) = no_grupo["exemplos"]
    assert exemplo["empresa_do_setor"]["raiz_do_cnpj"] == reorganizada
    assert exemplo["ligada_por"]["raiz_do_cnpj"] == controladora
    assert exemplo["data_entrada"]["valor"] == "2024-05-10"
    assert corpo["entradas_intragrupo"] == 1


def test_a_irma_e_a_controlada_que_passam_a_empresa_tambem_sao_reorganizacao(tmp_path):
    mundo = Mundo(montar=False)
    controladora = mundo.comprador("33")
    da_irma, da_controlada = mundo.comprador(), mundo.comprador()
    irma, controlada = mundo.comprador("34"), mundo.comprador("34")
    mundo.entrar(controladora, da_irma, "2015-01-01")
    mundo.entrar(controladora, irma, "2015-01-01")
    mundo.entrar(da_controlada, controlada, "2015-01-01")
    for quem_passa, quem_recebe in ((irma, da_irma), (controlada, da_controlada)):
        empresa = mundo.empresa("20")
        mundo.entrar(quem_passa, empresa, "2015-01-01")
        mundo.entrar(quem_recebe, empresa, "2024-05-10")
        mundo.sair(quem_passa, empresa, "2015-01-01", "2024-05-10")
    raizes = {c["raiz_do_cnpj"] for c in _corpo(mundo, tmp_path)["compradores"]}
    assert not raizes & {da_irma, da_controlada}


def test_a_controladora_que_entra_junto_nao_faz_da_compra_mesmo_grupo(tmp_path):
    mundo = Mundo(montar=False)
    controladora, comprador, vendedora = (
        mundo.comprador("33"),
        mundo.comprador(),
        mundo.comprador("34"),
    )
    empresa = mundo.empresa("20")
    mundo.entrar(controladora, comprador, "2018-01-01")
    mundo.entrar(vendedora, empresa, "2015-01-01")
    mundo.entrar(comprador, empresa, "2024-04-10")
    mundo.entrar(controladora, empresa, "2024-04-10")
    mundo.sair(vendedora, empresa, "2015-01-01", "2024-04-10")
    corpo = _corpo(mundo, tmp_path)
    assert _entradas_de(_linha(corpo, comprador)) == {empresa}
    # a controladora entrou na mesma compra: as duas são um grupo, que entrou numa empresa só
    grupo = _linha(corpo, comprador)["grupo"]
    assert grupo["empresas_do_setor_com_entrada"] == 1
    assert corpo["entradas_intragrupo"] == 0


def test_veiculos_irmaos_ganham_o_bloco_grupo_e_sobem_juntos(tmp_path):
    mundo = Mundo(montar=False)
    controladora = mundo.comprador("33")
    veiculos = [mundo.comprador() for _ in range(3)]
    for i, veiculo in enumerate(veiculos):
        mundo.entrar(controladora, veiculo, "2019-01-01")
        mundo.entrar(veiculo, mundo.empresa("20"), f"2024-0{3 + i}-10")
    # uma holding sozinha com duas entradas: sem o grupo ela viria antes de cada veículo
    sozinha = mundo.comprador("31")
    for _ in range(2):
        mundo.entrar(sozinha, mundo.empresa("20"), "2025-01-10")
    corpo = _corpo(mundo, tmp_path)
    ordem = [c["raiz_do_cnpj"] for c in corpo["compradores"]]
    assert ordem[:3] == sorted(veiculos) and ordem[3] == sozinha
    grupo = _linha(corpo, veiculos[0])["grupo"]
    assert grupo["ligada_por"]["raiz_do_cnpj"] == controladora
    assert grupo["ligada_por"]["razao_social"]["valor"] == mundo.nomes[controladora]
    assert grupo["empresas_do_setor_com_entrada"] == 3
    assert {e["raiz_do_cnpj"] for e in grupo["empresas"]} == set(veiculos[1:])
    assert "grupo" not in _linha(corpo, sozinha)


def test_o_grupo_sobe_ate_tres_niveis(tmp_path):
    """Dois veículos cujas controladoras diretas são diferentes, mas têm a mesma avó: um grupo só."""
    mundo = Mundo(montar=False)
    avo = mundo.comprador("33")
    a, b = mundo.comprador("34"), mundo.comprador("34")
    va, vb = mundo.comprador(), mundo.comprador()
    for socia, empresa in ((avo, a), (avo, b), (a, va), (b, vb)):
        mundo.entrar(socia, empresa, "2019-01-01")
    for veiculo in (va, vb):
        mundo.entrar(veiculo, mundo.empresa("20"), "2024-03-10")
    corpo = _corpo(mundo, tmp_path)
    grupo = _linha(corpo, va)["grupo"]
    assert {e["raiz_do_cnpj"] for e in grupo["empresas"]} == {vb}
    assert grupo["ligada_por"]["raiz_do_cnpj"] == avo


def test_a_socia_que_ainda_nao_era_publica_nao_liga_o_grupo(tmp_path):
    """A controladora entrou nos dois veículos em 2026-10-20: o retrato só sai em 30/11, depois do dia pedido."""
    mundo = Mundo(montar=False)
    controladora = mundo.comprador("33")
    veiculos = [mundo.comprador() for _ in range(2)]
    for veiculo in veiculos:
        mundo.entrar(controladora, veiculo, "2026-10-20")
        mundo.entrar(veiculo, mundo.empresa("20"), "2024-03-10")
    corpo = _corpo(mundo, tmp_path)
    assert all("grupo" not in c for c in corpo["compradores"])


def test_o_grupo_do_comprador_tambem_e_datado_na_entrada(tmp_path):
    """Diretoria, condição 1: B compra T de S em 2022; só em 2024 a sócia de S entra em B. Pelo quadro de hoje B e S
    têm a mesma sócia e a compra viraria reorganização; na data da compra não tinham: é compra de terceiro."""
    mundo = Mundo(montar=False)
    socia_de_s, b, s = (
        mundo.comprador("33"),
        mundo.comprador(),
        mundo.comprador("34"),
    )
    t = mundo.empresa("20")
    mundo.entrar(socia_de_s, s, "2015-01-01")
    mundo.entrar(s, t, "2015-01-01")
    mundo.entrar(b, t, "2022-06-10")
    mundo.sair(s, t, "2015-01-01", "2022-06-10")
    mundo.entrar(socia_de_s, b, "2024-03-01")
    corpo = _corpo(mundo, tmp_path)
    assert _entradas_de(_linha(corpo, b)) == {t}
    assert corpo["entradas_intragrupo"] == 0


def _socia_de_muita_gente(mundo: Mundo, *raizes: str) -> str:
    """Uma sócia PJ (um fundo, um banco) nas `raizes` e em tantas outras que passa do teto da ponte."""
    fundo = mundo.comprador("35")
    # uma acima do teto mesmo depois de sair de uma delas (o teto conta o quadro do dia)
    outras = compradores.PARTICIPACOES_MAXIMAS_DA_PONTE + 2 - len(raizes)
    for raiz in (*raizes, *(mundo.comprador("36") for _ in range(outras))):
        mundo.entrar(fundo, raiz, "2019-01-01")
    return fundo


def test_socia_de_muita_gente_nao_junta_compradores_sem_relacao(tmp_path):
    """Diretoria, condição 2: a sócia em comum não prova controle; a que é sócia de mais empresas que o teto não
    serve de ponte."""
    mundo = Mundo(montar=False)
    a, b = mundo.comprador(), mundo.comprador()
    _socia_de_muita_gente(mundo, a, b)
    for raiz in (a, b):
        mundo.entrar(raiz, mundo.empresa("20"), "2024-03-10")
    corpo = _corpo(mundo, tmp_path)
    assert all("grupo" not in c for c in corpo["compradores"])


def test_socia_de_muita_gente_nao_tira_compra_real_da_conta(tmp_path):
    """O fundo vende ao comprador uma empresa do setor e também é sócio do comprador: não é reorganização."""
    mundo = Mundo(montar=False)
    comprador, empresa = mundo.comprador(), mundo.empresa("20")
    fundo = _socia_de_muita_gente(mundo, comprador, empresa)
    mundo.entrar(comprador, empresa, "2024-03-10")
    mundo.sair(fundo, empresa, "2019-01-01", "2024-03-10")
    corpo = _corpo(mundo, tmp_path)
    assert _entradas_de(_linha(corpo, comprador)) == {empresa}


def test_a_socia_fora_da_lista_sem_pessoa_nao_liga_nem_aparece(tmp_path):
    """A sócia que não está na lista sem pessoa (MEI, empresário individual) não serve de ponte nem sai na resposta."""
    mundo = Mundo(montar=False)
    fora_da_lista = "37000000"  # sem nome: não está em `cnpj_empresas_pj`
    veiculos = [mundo.comprador() for _ in range(2)]
    for veiculo in veiculos:
        mundo.entrar(fora_da_lista, veiculo, "2019-01-01")
        mundo.entrar(veiculo, mundo.empresa("20"), "2024-03-10")
    corpo = _corpo(mundo, tmp_path)
    assert all("grupo" not in c for c in corpo["compradores"])
    assert fora_da_lista not in json.dumps(corpo)


def test_nenhum_cpf_sai_na_resposta(tmp_path):
    mundo = Mundo(montar=False)
    _reorganizacao(mundo)
    controladora = mundo.comprador("33")
    for _ in range(2):
        veiculo = mundo.comprador()
        mundo.entrar(controladora, veiculo, "2019-01-01")
        mundo.entrar(veiculo, mundo.empresa("20"), "2024-03-10")
    texto = json.dumps(_corpo(mundo, tmp_path), default=str)
    assert not achar_cpf(texto)


def test_os_limites_dizem_o_que_o_grupo_nao_ve(tmp_path):
    """Diretoria, condição 3: ligação não prova controle; reorganização por pessoa física, sócia que saiu antes do
    primeiro retrato e sócia estrangeira sem CNPJ ficam de fora."""
    mundo = Mundo(montar=False)
    _reorganizacao(mundo)
    limites = " ".join(_corpo(mundo, tmp_path)["limites"])
    assert "não prova controle" in limites
    assert "pessoa física" in limites and "primeiro retrato" in limites
    assert "sem CNPJ" in limites
    assert "controladora" not in limites


def _consultas(mundo: Mundo, tmp_path, monkeypatch) -> int:
    contadas = []
    original = compradores._Consulta._df

    def contar(self, *args, **kwargs):
        contadas.append(1)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(compradores._Consulta, "_df", contar)
    _corpo(mundo, tmp_path)
    compradores.zerar_o_cache()
    return len(contadas)


def _grupos(quantos: int) -> Mundo:
    mundo = Mundo(montar=False)
    for _ in range(quantos):
        avo, meio = mundo.comprador("33"), mundo.comprador("34")
        mundo.entrar(avo, meio, "2015-01-01")
        for _ in range(2):
            veiculo = mundo.comprador()
            mundo.entrar(meio, veiculo, "2019-01-01")
            mundo.entrar(veiculo, mundo.empresa("20"), "2024-03-10")
        _reorganizacao(mundo)
    return mundo


def test_as_socias_acima_saem_em_lote(tmp_path, monkeypatch):
    """Diretoria, condição 4: uma consulta por nível para a lista inteira; 2 ou 12 grupos, o mesmo número."""
    poucos = _consultas(_grupos(2), tmp_path / "poucos", monkeypatch)
    muitos = _consultas(_grupos(12), tmp_path / "muitos", monkeypatch)
    assert poucos == muitos


def test_a_api_traduz_os_nomes_novos():
    for nome in (
        "grupo",
        "ligada_por",
        "empresas",
        "empresas_do_setor_com_entrada",
        "entradas_no_grupo",
        "entradas_intragrupo",
        "quadro_de_socios_em",
    ):
        assert nomes.para_fora(nome)
