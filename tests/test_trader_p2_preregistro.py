"""O pré-registro da Pesquisa 2 está travado pelo hash e bate com os números do código."""

import pytest

from trader.p2 import preregistro
from trader.p2.mercados import GRUPOS


def test_texto_vigente_e_o_aprovado():
    preregistro.conferir()  # não pode levantar erro


def test_texto_alterado_e_recusado(tmp_path):
    copia = tmp_path / "pre-registro.md"
    copia.write_text(
        preregistro.ARQUIVO.read_text(encoding="utf-8") + "\nmudança\n",
        encoding="utf-8",
    )
    with pytest.raises(preregistro.PreRegistroAlteradoError):
        preregistro.conferir(copia)


def test_pesos_dos_grupos_somam_um_e_cobrem_todos_os_grupos():
    assert set(preregistro.PESOS_DOS_GRUPOS) == set(GRUPOS)
    assert sum(preregistro.PESOS_DOS_GRUPOS.values()) == pytest.approx(1.0)


def test_numeros_do_codigo_aparecem_no_texto():
    texto = preregistro.ARQUIVO.read_text(encoding="utf-8")
    assert "moedas 30%, índices 30%, metais 15%, energia 15%, títulos 10%" in texto
    assert "Volatilidade alvo da carteira: 12% ao ano" in texto
    assert "**20 tentativas**" in texto
    assert "101 + as tentativas da Pesquisa 2" in texto
