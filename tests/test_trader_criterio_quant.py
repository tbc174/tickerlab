"""O pré-registro das estratégias quant P0 está travado pelo hash e bate com os números do código."""

import pytest

from trader import criterio_quant


def test_texto_vigente_e_o_aprovado():
    criterio_quant.conferir()  # não pode levantar erro


def test_texto_alterado_e_recusado(tmp_path):
    copia = tmp_path / "pre-registro.md"
    copia.write_text(
        criterio_quant.ARQUIVO.read_text(encoding="utf-8") + "\nmudança\n",
        encoding="utf-8",
    )
    with pytest.raises(criterio_quant.PreRegistroAlteradoError, match="versão nova"):
        criterio_quant.conferir(copia)


def test_orcamento_das_fichas_soma_o_total_da_versao():
    assert sum(criterio_quant.ORCAMENTO_POR_FICHA.values()) == (
        criterio_quant.ORCAMENTO_DE_TENTATIVAS
    )
    assert set(criterio_quant.FICHAS_SEM_CRITERIO) <= set(
        criterio_quant.ORCAMENTO_POR_FICHA
    )
    assert set(criterio_quant.CANDIDATOS) <= set(criterio_quant.ORCAMENTO_POR_FICHA)


def test_alavancagem_do_nucleo_so_tem_as_duas_versoes():
    assert criterio_quant.ALAVANCAGENS_DO_NUCLEO == (1.0, 1.3)
    assert criterio_quant.QUEDA_MAXIMA == criterio_quant.FREIO_GLOBAL == 0.35
    assert criterio_quant.FREIO_POR_CAMADA > criterio_quant.FREIO_GLOBAL


def test_numeros_do_codigo_aparecem_no_texto():
    texto = criterio_quant.ARQUIVO.read_text(encoding="utf-8")
    assert "**Status: APROVADO, versão 0.1, em 03/11/2026" in texto
    assert "DSR ≥ 0,95" in texto
    assert "≤ 0,30" in texto
    assert "±20% em cada parâmetro mantém ≥ 70% do Sharpe" in texto
    assert "no máximo ⅓ do Sharpe bruto" in texto
    assert "≥ 3,0" in texto
    assert "percentil 95 de 1.000 sinais deslocados" in texto
    assert "limite inferior de 90% (bootstrap em blocos de 21 dias)" in texto
    assert "DSR ≥ 0,90" in texto
    assert "| ≤ 35% |" in texto
    assert "queda de 35% do pico da carteira inteira" in texto
    assert "queda de 40% do pico da própria camada" in texto
    assert "volta no primeiro pregão 12 meses depois do disparo" in texto
    assert "**1,0x** e **1,3x**" in texto
    assert "≥ R$ 5 milhões nos 60 pregões anteriores" in texto
    assert "**Orçamento total desta versão: 60\ntentativas**" in texto
    assert "**+25 tentativas**" in texto
    for ficha, orcamento in criterio_quant.ORCAMENTO_POR_FICHA.items():
        assert f"### Ficha {ficha}." in texto
        assert f"**Orçamento:** {orcamento} tentativas" in texto
