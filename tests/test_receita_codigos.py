"""As tabelas de códigos da Receita (`base/receita_codigos.py`): tradução, zeros à esquerda e código novo."""

from base import receita_codigos as codigos


def test_traduz_os_codigos_das_tabelas_da_receita() -> None:
    assert codigos.qualificacao("05") == "Administrador"
    assert codigos.municipio("7107") == "SAO PAULO"
    assert codigos.cnae("6201501").startswith("Desenvolvimento de programas")
    assert codigos.pais("105") == "BRASIL"


def test_completa_os_zeros_a_esquerda() -> None:
    assert codigos.qualificacao("5") == codigos.qualificacao("05")
    assert codigos.situacao_cadastral("2") == "Ativa"
    assert codigos.tipo_de_socio("2") == "pessoa física"


def test_codigo_que_a_tabela_nao_tem_e_vazio() -> None:
    assert codigos.qualificacao("99") == "código 99"
    assert codigos.municipio("") is None
    assert codigos.situacao_cadastral(None) is None
