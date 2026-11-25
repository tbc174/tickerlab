"""A memória dos comparáveis por (grupo, dia) na porta dona (linha 1015, item c, PR 3; condições da Diretoria).

Pelo log de produção de 25/11 o bloco dos comparáveis atrasou em 6 de 6 pedidos: a cada pedido ele relia os FCA
do dia e os DFP do grupo inteiro e refazia as contas em Python. O que só depende da base e do dia fica guardado
na porta dona (morre com a base trocada); o que depende de quem pede (a trava de pessoa em lote e o portão) roda
a cada pedido, depois da memória.

Riscos que estes testes pegam: (a) a memória guardar o que depende de quem pede (pessoa ou permissão da
organização), e uma organização receber o que é da outra; (b) o ponto no tempo fora da chave (um dia servir o
de outro, ou o futuro); (c) a memória crescer sem teto; (d) a base trocada servir o grupo velho. Base de mentira
(a dos comparáveis), sem internet.
"""

from datetime import date

import pytest

from base.porta import Porta
from src.api_externa import pessoas, porta_compartilhada, rotas
from src.api_externa.conjuntos import comparaveis, empresas
from src.banco import chaves_da_api as cb
from tests import ajudantes_da_api_externa as aj
from tests import test_api_externa_por_cnpj_comparaveis as de_mentira
from tests.test_api_externa_por_cnpj_comparaveis_rota import AGORA, _regras, _rota

ALFA, DIA, PARES = de_mentira.ALFA, de_mentira.DIA, de_mentira.PARES
PESSOA = de_mentira.TRATADA_COMO_PESSOA
# dias de antes do DFP de 2024, de DIA, de depois do DFP 2024 do par 9 e de depois da ALFA mudar de setor
DIAS = (date(2024, 6, 1), date(2025, 3, 20), DIA, date(2025, 9, 1))


def _tudo(_fonte: str, _campo: str, _derivado: bool) -> bool:
    return True


def _sem_dfp(fonte: str, _campo: str, _derivado: bool) -> bool:
    return fonte != comparaveis.FONTE_DOS_NUMEROS


@pytest.fixture
def compartilhada(tmp_path, monkeypatch):
    """A porta compartilhada de verdade sobre a base de mentira: `pedido()` dá uma porta por pedido."""
    pasta = de_mentira.gravar_base(tmp_path / "base")
    aberturas: list[int] = []

    def abrir() -> Porta:
        aberturas.append(1)
        return Porta(pasta)

    porta_compartilhada.zerar()
    monkeypatch.setattr(porta_compartilhada, "abrir_a_base", abrir)
    monkeypatch.setattr(porta_compartilhada, "_pasta_da_base", lambda: pasta)
    yield pasta, aberturas
    porta_compartilhada.zerar()


def _pede(cnpj: str = ALFA, dia: date = DIA, permitido=_tudo):
    with porta_compartilhada.porta_do_pedido() as porta:
        return comparaveis.LeitorDeComparaveis(porta, permitido, 1000).comparaveis(
            cnpj, dia
        )


def _sem_memoria(pasta, cnpj: str = ALFA, dia: date = DIA, permitido=_tudo):
    with Porta(pasta) as porta:
        return comparaveis.LeitorDeComparaveis(porta, permitido, 1000).comparaveis(
            cnpj, dia
        )


def _guardados() -> comparaveis._Guardados:
    with porta_compartilhada.porta_do_pedido() as porta:
        guardados = comparaveis._guardados(porta)
    assert guardados is not None
    return guardados


def _leituras(monkeypatch) -> list[str]:
    """As tabelas que a porta lê (a leitura de verdade continua)."""
    lidas: list[str] = []
    ler = Porta.ler

    def contando(self, tabela, *args, **kwargs):
        lidas.append(tabela)
        return ler(self, tabela, *args, **kwargs)

    monkeypatch.setattr(Porta, "ler", contando)
    return lidas


def _pares(servida) -> list[str]:
    return [linha["cnpj"]["valor"] for linha in servida.corpo["pares"]]


# ---------------------------------------------------------------- o que fica guardado


def test_o_segundo_pedido_do_mesmo_grupo_e_dia_nao_le_a_base_de_novo(
    compartilhada, monkeypatch
):
    primeiro = _pede()
    lidas = _leituras(monkeypatch)
    segundo = _pede()
    assert comparaveis.TABELA_DO_CADASTRO not in lidas
    assert comparaveis.TABELA_DAS_DEMONSTRACOES not in lidas
    assert segundo == primeiro


def test_um_par_pedido_usa_a_mesma_entrada_do_grupo(compartilhada, monkeypatch):
    _pede(ALFA)
    lidas = _leituras(monkeypatch)
    servida = _pede(PARES[2])
    assert servida is not None and ALFA in _pares(servida)
    assert comparaveis.TABELA_DAS_DEMONSTRACOES not in lidas
    assert len(_guardados()) == 2  # os cadastros do dia e as companhias do grupo


def test_com_e_sem_memoria_a_resposta_e_a_mesma_em_todo_dia_e_cnpj(compartilhada):
    pasta, _aberturas = compartilhada
    # do dia mais novo para o mais velho: a memória cheia do futuro não pode vazar para o passado
    for dia in reversed(DIAS):
        for cnpj in (ALFA, PARES[0], PARES[8], de_mentira.BANCO, PESSOA):
            assert _pede(cnpj, dia) == _sem_memoria(pasta, cnpj, dia), (cnpj, dia)
            assert _pede(cnpj, dia) == _sem_memoria(pasta, cnpj, dia), (cnpj, dia)


def test_o_dia_entra_na_chave(compartilhada):
    """O par 9 entregou o DFP de 2024 em 01/08/2025: em DIA ele vale pelo de 2023, em 01/09 pelo de 2024."""
    depois = _pede(PARES[0], date(2025, 9, 1))
    antes = _pede(PARES[0], DIA)
    assert antes is not None and depois is not None

    def receita_do_par_9(servida) -> float:
        linha = next(
            p for p in servida.corpo["pares"] if p["cnpj"]["valor"] == PARES[8]
        )
        return linha["receita"]["valor"]

    assert (receita_do_par_9(antes), receita_do_par_9(depois)) == (100.0, 900.0)
    assert {chave[-1] for chave in _guardados().chaves()} == {DIA, date(2025, 9, 1)}


# ---------------------------------------------------------------- o que roda a cada pedido


def test_a_trava_de_pessoa_roda_a_cada_pedido_depois_da_memoria(
    compartilhada, monkeypatch
):
    _pede()
    perguntas: list[list[str]] = []
    em_lote = empresas.e_empresas

    def contando(porta, cnpjs):
        perguntas.append(list(cnpjs))
        return em_lote(porta, cnpjs)

    monkeypatch.setattr(comparaveis, "e_empresas", contando)
    servida = _pede()
    assert len(perguntas) == 1 and PESSOA in perguntas[0]
    assert servida is not None and PESSOA not in _pares(servida)
    # e quem a rede trata como pessoa não é servido nem pedido diretamente, com a memória cheia
    assert _pede(PESSOA) is None


def test_a_rede_que_passa_a_tratar_como_pessoa_vale_no_pedido_seguinte(
    compartilhada, monkeypatch
):
    """A trava não fica guardada: se a resposta dela muda, o par sai já no pedido seguinte."""
    servida = _pede()
    assert servida is not None and PARES[3] in _pares(servida)
    em_lote = empresas.e_empresas

    def sem_o_par_4(porta, cnpjs):
        return {c: e and c != PARES[3] for c, e in em_lote(porta, cnpjs).items()}

    monkeypatch.setattr(comparaveis, "e_empresas", sem_o_par_4)
    servida = _pede()
    assert servida is not None and PARES[3] not in _pares(servida)


def test_o_portao_roda_a_cada_pedido_e_nao_entra_na_memoria(compartilhada):
    tudo = _pede()
    guardado = {
        chave: repr(_guardados().valor(chave)) for chave in _guardados().chaves()
    }
    sem_dfp = _pede(permitido=_sem_dfp)
    assert sem_dfp is not None and tudo is not None
    assert comparaveis.FONTE_DOS_NUMEROS not in sem_dfp.fontes
    assert all(
        set(linha) == {"cnpj", "empresa", "setor"} for linha in sem_dfp.corpo["pares"]
    )
    # o pedido sem a DFP não mudou nada do que ficou guardado, e o seguinte com tudo volta inteiro
    assert {
        chave: repr(_guardados().valor(chave)) for chave in _guardados().chaves()
    } == guardado
    assert _pede() == tudo


def test_o_portao_que_nega_o_setor_nao_toca_a_memoria(compartilhada):
    def sem_setor(fonte: str, campo: str, derivado: bool) -> bool:
        return campo != "setor"

    assert _pede(permitido=sem_setor) is None
    assert len(_guardados()) == 0


# ---------------------------------------------------------------- o teto e a base trocada


def test_a_memoria_tem_teto_de_entradas_e_sai_a_mais_velha(compartilhada, monkeypatch):
    pasta, _aberturas = compartilhada
    monkeypatch.setattr(comparaveis, "ENTRADAS_GUARDADAS", 3)
    for dia in DIAS:
        assert _pede(PARES[0], dia) == _sem_memoria(pasta, PARES[0], dia)
        assert len(_guardados()) <= 3
    # as duas últimas a entrar são as do último dia (os cadastros e o grupo); a mais velha já saiu
    chaves = _guardados().chaves()
    assert chaves[-2:] == [("cadastros", DIAS[-1]), ("companhias", "energia", DIAS[-1])]
    assert all(chave[-1] != DIAS[0] for chave in chaves)


def test_o_teto_padrao_e_pequeno():
    assert 1 <= comparaveis.ENTRADAS_GUARDADAS <= 64


def test_base_trocada_os_numeros_sao_os_da_base_nova(compartilhada, monkeypatch):
    import os

    pasta, aberturas = compartilhada
    antes = _pede()
    assert antes is not None
    receita = antes.corpo["empresa_pedida"]["receita"]["valor"]
    alfa = {
        **de_mentira.NUMEROS_DA_ALFA,
        "receita": 2 * de_mentira.NUMEROS_DA_ALFA["receita"],
    }
    arquivo = pasta / "demonstracoes" / "2024.parquet"
    de_mentira._demonstracoes(numeros_da_alfa=alfa).to_parquet(arquivo, index=False)
    estado = arquivo.stat()
    os.utime(arquivo, ns=(estado.st_atime_ns, estado.st_mtime_ns + 10**9))
    depois = _pede()
    assert depois is not None
    assert depois.corpo["empresa_pedida"]["receita"]["valor"] == 2 * receita
    assert len(aberturas) == 2


def test_porta_comum_calcula_sempre(tmp_path, monkeypatch):
    pasta = de_mentira.gravar_base(tmp_path / "base")
    _sem_memoria(pasta)
    lidas = _leituras(monkeypatch)
    _sem_memoria(pasta)
    assert comparaveis.TABELA_DAS_DEMONSTRACOES in lidas
    with Porta(pasta) as porta:
        assert comparaveis._guardados(porta) is None


# ---------------------------------------------------------------- duas organizações na mesma entrada


@pytest.fixture
def tres_na_mesma_porta(banco, monkeypatch, compartilhada):
    """Três organizações na porta compartilhada: duas com o contrato dos comparáveis (uma delas também com a
    permissão de pessoa no conector) e uma só com o de `companies`."""
    monkeypatch.setattr(rotas, "abrir_porta", porta_compartilhada.porta_do_pedido)
    monkeypatch.setattr(rotas, "regras_da_api", _regras)
    ator = aj.admin(banco)
    chaves = {}
    for nome, conjunto in (
        ("com_pessoa", comparaveis.CONJUNTO),
        ("sem_pessoa", comparaveis.CONJUNTO),
        ("so_companies", empresas.CONJUNTO),
    ):
        org = aj.organizacao(banco, ator, nome=f"Organização {nome}")
        aj.contrato(banco, ator, org, conjunto=conjunto)
        chaves[nome] = aj.chave(banco, ator, org).valor
        if nome == "com_pessoa":
            with banco.begin() as conexao:
                cb.conceder_direito(
                    conexao,
                    organizacao_id=org.id,
                    conjunto=pessoas.CONJUNTO,
                    finalidade="analise",
                    vigente_desde=date(2026, 11, 1),
                    ator_id=ator.id,
                    agora=AGORA,
                )
    return aj.cliente_da_api(monkeypatch, AGORA), chaves, compartilhada[1]


def _get(cliente, chave: str | None, cnpj: str = ALFA):
    cabecalhos = {} if chave is None else aj.bearer(chave)
    return cliente.get(
        _rota(cnpj), params={"known_at": DIA.isoformat()}, headers=cabecalhos
    )


def test_duas_organizacoes_batem_na_mesma_entrada_e_cada_uma_passa_pela_trava(
    tres_na_mesma_porta,
):
    cliente, chaves, aberturas = tres_na_mesma_porta
    com_pessoa = _get(cliente, chaves["com_pessoa"])
    assert com_pessoa.status_code == 200
    guardadas = _guardados().chaves()
    sem_pessoa = _get(cliente, chaves["sem_pessoa"])
    assert sem_pessoa.status_code == 200
    # a mesma entrada guardada serviu as duas: nada novo entrou na memória
    assert _guardados().chaves() == guardadas
    assert sem_pessoa.json() == com_pessoa.json()
    for resposta in (com_pessoa, sem_pessoa):
        pares = {par["cnpj"]["value"] for par in resposta.json()["peers"]}
        assert PESSOA not in pares and set(PARES) <= pares
    # a permissão de pessoa no conector não abre pessoa nos comparáveis, nem com a memória cheia
    for chave in (chaves["com_pessoa"], chaves["sem_pessoa"]):
        negado = _get(cliente, chave, PESSOA)
        assert negado.status_code == 404
        assert negado.json() == {"detail": "not_available"}
    assert len(aberturas) == 1


def test_com_a_memoria_cheia_o_portao_continua_por_organizacao(tres_na_mesma_porta):
    cliente, chaves, _aberturas = tres_na_mesma_porta
    assert _get(cliente, chaves["com_pessoa"]).status_code == 200
    assert len(_guardados()) > 0
    # a organização sem o contrato dos comparáveis e o pedido sem chave nenhuma não aproveitam a memória
    so_companies = _get(cliente, chaves["so_companies"])
    assert so_companies.status_code == 404
    assert so_companies.json() == {"detail": "not_available"}
    assert _get(cliente, None).status_code == 401
