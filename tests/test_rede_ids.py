"""Id determinístico de cada entidade da rede (ADR 0077, item 1; plano, D4).

O id é "E" + 20 hexadecimais do SHA-256 de `tipo|sistema|valor` do identificador primário, escolhido
numa ordem fixa (raiz do CNPJ > CNPJ > LEI > ISIN > código de regulador > nome + fonte). Quando a regra
mudaria o id de uma entidade que já existe (uma incorporação), a tabela conferida fixa o antigo.
"""

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from base.rede import ids

PETROBRAS = ("empresa", "cnpj_raiz", "33000167")


def _primarios(*linhas):
    return pd.DataFrame(linhas, columns=["tipo", "sistema", "valor"])


def test_mesmo_identificador_mesmo_id():
    primeiro = ids.id_entidade(*PETROBRAS)
    assert primeiro == ids.id_entidade(*PETROBRAS)
    assert primeiro.startswith("E") and len(primeiro) == 21
    assert primeiro != ids.id_entidade(
        "fundo", "cnpj_raiz", "33000167"
    )  # o tipo entra no hash


def test_ordem_do_identificador_primario():
    """Empresa com raiz e LEI: id pela raiz; só com LEI, pelo LEI; só nome, pelo nome com a fonte."""
    com_raiz = [
        ("lei", "5493000J2N45DDNE4Y28"),
        ("ticker", "PETR4"),
        ("cnpj_raiz", "33000167"),
    ]
    assert ids.identificador_primario(com_raiz) == ("cnpj_raiz", "33000167")
    so_lei = [("ticker", "XPTO3"), ("lei", "5493000J2N45DDNE4Y28")]
    assert ids.identificador_primario(so_lei) == ("lei", "5493000J2N45DDNE4Y28")
    regulador = [("nome:ans", "OPERADORA X"), ("codigo_ans", "368253")]
    assert ids.identificador_primario(regulador) == ("codigo_ans", "368253")
    assert ids.identificador_primario([("nome:ans", "OPERADORA X")]) == (
        "nome:ans",
        "OPERADORA X",
    )


def test_sem_identificador_que_possa_ser_primario_e_erro():
    """Ticker muda de dono e emissor também: nenhum dos dois dá identidade."""
    with pytest.raises(ValueError, match="primário"):
        ids.identificador_primario([("ticker", "PETR4")])


def test_dois_valores_no_sistema_primario_e_erro():
    with pytest.raises(ValueError, match="dois"):
        ids.identificador_primario(
            [("cnpj_raiz", "33000167"), ("cnpj_raiz", "60872504")]
        )


def test_tabela_conferida_fixa_o_id(tmp_path):
    """Incorporação: a entidade passou a ter outra raiz, mas o id antigo fica (linha do CSV)."""
    antigo = ids.id_entidade(*PETROBRAS)
    caminho = tmp_path / "entidades.csv"
    caminho.write_text(
        "tipo;sistema;valor;id_entidade;motivo;conferido_com;conferido_em\n"
        f"empresa;cnpj_raiz;99999999;{antigo};incorporada;FRE;2026-10-15\n",
        encoding="utf-8",
    )
    fixados = ids.ids_fixados(caminho)
    saida = ids.atribuir_ids(_primarios(("empresa", "cnpj_raiz", "99999999")), fixados)
    assert saida.tolist() == [antigo]


def test_tabela_conferida_do_repositorio_e_valida():
    fixados = ids.ids_fixados()
    assert all(i.startswith("E") and len(i) == 21 for i in fixados.values())


def test_colisao_e_erro():
    """Duas entidades diferentes com o mesmo id quebram a montagem (nunca se fundem caladas)."""
    outra = ("empresa", "cnpj_raiz", "60872504")
    fixados = {outra: ids.id_entidade(*PETROBRAS)}
    with pytest.raises(ValueError, match="colisão"):
        ids.atribuir_ids(_primarios(PETROBRAS, outra), fixados)


def test_mesma_entidade_repetida_nao_e_colisao():
    saida = ids.atribuir_ids(_primarios(PETROBRAS, PETROBRAS), {})
    assert saida.nunique() == 1


@settings(max_examples=50, deadline=None)
@given(st.permutations(range(6)))
def test_ordem_das_linhas_nao_muda_os_ids(ordem):
    linhas = [("empresa", "cnpj_raiz", f"{n:08d}") for n in range(4)] + [
        ("fundo", "cnpj", "12ABC34501DE35"),
        ("valor_mobiliario", "isin", "BRPETRACNPR6"),
    ]
    tabela = _primarios(*linhas)
    embaralhada = tabela.iloc[list(ordem)]
    assert (
        ids.atribuir_ids(embaralhada, {}).sort_index().tolist()
        == ids.atribuir_ids(tabela, {}).tolist()
    )
