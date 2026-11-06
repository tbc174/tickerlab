"""O esquema do leitor de releases e a conferência do trecho (vitrine, PR 2; ADR 0090, 0087)."""

from base import leitor_release as lr

TEXTO = (
    "Receita líquida atingiu R$ 1.234,5 milhões no 3T25, alta de 8%.\n"
    "O lucro líquido dos controladores foi de R$ 210 milhões."
)


def _linha(trecho, valor=1234.5, **extra):
    base = {
        "linha": "receita_liquida", "valor": valor, "unidade": "milhoes",
        "periodo": "trimestre", "trecho": trecho, "pagina": 1,
    }  # fmt: skip
    return base | extra


def _leitura(*linhas, ajustes=()):
    return lr.LeituraDoRelease.model_validate(
        {"linhas": list(linhas), "ajustes": list(ajustes)}
    )


def test_descarta_trecho_que_nao_existe():
    leitura = _leitura(_linha("Receita líquida somou R$ 1.234,5 milhões"))
    conferida = lr.conferir(leitura, TEXTO)
    assert conferida.linhas == []
    assert [d.motivo for d in conferida.descartes] == [lr.TRECHO_AUSENTE]


def test_descarta_numero_fora_do_trecho():
    leitura = _leitura(
        _linha("Receita líquida atingiu R$ 1.234,5 milhões", valor=999.0)
    )
    conferida = lr.conferir(leitura, TEXTO)
    assert conferida.linhas == []
    assert [d.motivo for d in conferida.descartes] == [lr.NUMERO_FORA_DO_TRECHO]


def test_aceita_espacos_e_quebras_diferentes():
    leitura = _leitura(_linha("receita  líquida atingiu R$ 1.234,5\n milhões no 3T25"))
    conferida = lr.conferir(leitura, TEXTO)
    assert len(conferida.linhas) == 1 and conferida.descartes == []


def test_aceita_o_valor_em_formato_brasileiro_ou_americano():
    texto = "Net revenue was R$ 1,234.5 million; lucro de 210,0 milhões."
    leitura = _leitura(_linha("Net revenue was R$ 1,234.5 million"))
    assert len(lr.conferir(leitura, texto).linhas) == 1


def test_ajuste_tambem_e_conferido():
    ajuste = {
        "descricao": "lucro líquido ajustado", "valor": 210.0, "unidade": "milhoes",
        "trecho": "O lucro líquido dos controladores foi de R$ 210 milhões",
    }  # fmt: skip
    falso = ajuste | {"valor": 5.0}
    conferida = lr.conferir(_leitura(ajustes=[ajuste, falso]), TEXTO)
    assert len(conferida.ajustes) == 1 and len(conferida.descartes) == 1


def test_linha_fora_da_lista_fechada_nao_passa():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        _leitura(_linha("Receita líquida atingiu R$ 1.234,5 milhões", linha="ebitda"))


def test_mascara_nomes_antes_do_envio():
    texto = (
        "“Foi um trimestre forte”, afirma João da Silva Santos, Diretor-Presidente. "
        "Segundo o CFO Maria Souza Lima, a Empresa Alfa S.A. cresceu. "
        "Contato: Carlos Pereira, Diretor de Relações com Investidores."
    )
    mascarado = lr.mascarar_pessoas(texto)
    for nome in ("João da Silva Santos", "Maria Souza Lima", "Carlos Pereira"):
        assert nome not in mascarado
    assert mascarado.count(lr.PESSOA) == 3
    assert "Empresa Alfa S.A." in mascarado  # o nome da empresa fica (0087, regra 5)


def test_preco_do_haiku_esta_cadastrado():
    assert (
        lr.custo_em_dolares(1_000_000, 1_000_000, lote=False, modelo=lr.MODELO) == 0.6
    )
    assert lr.custo_em_dolares(1_000_000, 1_000_000, lote=True, modelo=lr.MODELO) == 0.3


def _confere_sinal(trecho, valor):
    texto = trecho
    leitura = _leitura(_linha(trecho, valor=valor))
    return lr.conferir(leitura, texto)


def test_aceita_prejuizo_com_sinal_de_menos_ou_parenteses():
    assert len(_confere_sinal("Prejuízo do período -149,4 -69,0", -149.4).linhas) == 1
    assert (
        len(_confere_sinal("Lucro (Prejuízo) 476 (5.138) -109%", -5138.0).linhas) == 1
    )
    assert len(_confere_sinal("Resultado −2,6 88,9", -2.6).linhas) == 1


def test_descarta_sinal_trocado():
    assert _confere_sinal("Lucro (Prejuízo) 476 (5.138)", 5138.0).descartes
    assert _confere_sinal("Lucro do período 5.138 3.280", -5138.0).descartes


def test_hifen_no_meio_de_palavra_nao_e_sinal_de_menos():
    assert len(_confere_sinal("Período 2T24-5.891 receita", 5891.0).linhas) == 1
