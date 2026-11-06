"""`telas.comum._formatar_parametro`: como um parâmetro de estratégia aparece no resumo."""

from telas.comum import _formatar_parametro


def test_opcao_conhecida_usa_o_rotulo():
    assert _formatar_parametro("media", "cdi") == "CDI (Banco Central)"


def test_opcao_desconhecida_volta_como_texto():
    assert _formatar_parametro("x", "qualquer") == "qualquer"
    assert _formatar_parametro("x", 20) == "20"


def test_decimal_usa_virgula():
    assert _formatar_parametro("x", 0.5) == "0,5"
    assert _formatar_parametro("x", 2.0) == "2"


def test_tupla_junta_os_rotulos():
    assert _formatar_parametro("x", ("diario", "semanal")) == "Diário, Semanal"
    assert _formatar_parametro("x", ("zero", "desconhecida")) == "Zero, desconhecida"


def test_tupla_vazia_vira_traco():
    assert _formatar_parametro("x", ()) == "—"
