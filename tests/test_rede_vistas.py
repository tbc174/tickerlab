"""As duas vistas das ligações (ADR 0077, item 3; plano, tarefa 3.3).

A interna tem tudo. A publicada (o que um dia vai ao VPS e à API) não tem aresta de pessoa: cada uma vira
um atributo da empresa (`socios_em_comum_com`, `tem_socio_pep`, `administrador_sancionado`), com fonte e
data, e nenhum `id_pessoa` sai. Nesta série nenhuma aresta real de pessoa existe: tudo aqui é de mentira.
"""

import pandas as pd

from base.rede import ids, ligacoes, vistas

D = pd.Timestamp
EMPRESA_A, EMPRESA_B, MEI = "E" + "a" * 20, "E" + "b" * 20, "E" + "c" * 20
ORGAO = "E" + "d" * 20
PESSOA_1, PESSOA_2 = ids.PREFIXO_DE_PESSOA + "1" * 20, ids.PREFIXO_DE_PESSOA + "2" * 20


def _ligacao(de: str, para: str, tipo: str, publico_em: str, **campos) -> dict:
    return {
        "de": de,
        "para": para,
        "tipo": tipo,
        "aconteceu_em": D(publico_em),
        "publico_em": D(publico_em),
        "fonte": "fonte-de-mentira",
        "origem_sha256": "ab" * 32,
        "conferido_por": "regra",
        **campos,
    }


def _ligacoes() -> pd.DataFrame:
    return ligacoes.normalizar(
        pd.DataFrame(
            [
                _ligacao(EMPRESA_A, EMPRESA_B, "controlada_de", "2020-01-01"),
                _ligacao(PESSOA_1, EMPRESA_A, "socio_de", "2020-02-01"),
                _ligacao(PESSOA_1, EMPRESA_B, "socio_de", "2021-03-01"),
                _ligacao(PESSOA_1, ORGAO, "pep", "2019-01-01"),
                _ligacao(PESSOA_2, EMPRESA_A, "administrador_de", "2020-01-01"),
                _ligacao(PESSOA_2, MEI, "administrador_de", "2020-01-01"),
                _ligacao(PESSOA_2, ORGAO, "sancionada_por", "2022-06-01"),
                _ligacao(MEI, ORGAO, "sancionada_por", "2022-07-01"),
                _ligacao(EMPRESA_B, ORGAO, "sancionada_por", "2022-08-01"),
            ]
        )
    )


def _entidades() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "id_entidade": [EMPRESA_A, EMPRESA_B, MEI, ORGAO],
            "trata_como_pessoa": [False, False, True, False],
        }
    )


def _tem_pessoa(tabela: pd.DataFrame) -> bool:
    texto = tabela.astype(str).to_string()
    return (
        PESSOA_1 in texto
        or PESSOA_2 in texto
        or any("pessoa" in coluna for coluna in tabela.columns)
    )


def test_vista_interna_tem_tudo():
    interna = vistas.vista_interna(_ligacoes())
    pd.testing.assert_frame_equal(interna, _ligacoes())


def test_vista_publicada_nao_tem_id_pessoa():
    publicadas, atributos = vistas.vista_publicada(_ligacoes(), _entidades())
    assert not _tem_pessoa(publicadas) and not _tem_pessoa(atributos)
    assert set(publicadas["tipo"]) == {"controlada_de", "sancionada_por"}
    por_atributo = {
        (a.id_entidade, a.atributo): a for a in atributos.itertuples(index=False)
    }
    # o sócio em comum: cada empresa aponta a outra, público quando as duas arestas eram públicas
    comum = por_atributo[(EMPRESA_A, "socios_em_comum_com")]
    assert comum.valor == EMPRESA_B and comum.publico_em == D("2021-03-01")
    assert comum.fonte == "fonte-de-mentira"
    assert por_atributo[(EMPRESA_B, "socios_em_comum_com")].valor == EMPRESA_A
    pep = por_atributo[(EMPRESA_A, "tem_socio_pep")]
    assert (pep.valor, pep.publico_em) == ("sim", D("2020-02-01"))
    sancionado = por_atributo[(EMPRESA_A, "administrador_sancionado")]
    assert (sancionado.valor, sancionado.publico_em) == ("sim", D("2022-06-01"))


def test_mei_ei_e_nao_informada_sem_sinal_negativo_publicado():
    """Quem é tratado como pessoa (MEI, EI, natureza não informada) não recebe sinal negativo."""
    publicadas, atributos = vistas.vista_publicada(_ligacoes(), _entidades())
    assert MEI not in set(publicadas["de"]) | set(publicadas["para"])
    assert MEI not in set(atributos["id_entidade"])
    # a empresa comum continua com a sanção dela
    sancoes = publicadas[publicadas["tipo"] == "sancionada_por"]
    assert list(sancoes["de"]) == [EMPRESA_B]


def test_entidade_que_nao_esta_na_rede_e_tratada_como_pessoa():
    sem_a_b = _entidades()[lambda t: t["id_entidade"] != EMPRESA_B]
    publicadas, _ = vistas.vista_publicada(_ligacoes(), sem_a_b)
    assert "sancionada_por" not in set(publicadas["tipo"])


def test_aresta_anonima_da_lapide_nao_sai():
    anonima = _ligacoes().assign(de=lambda t: t["de"].mask(t["de"] == PESSOA_1, None))
    publicadas, atributos = vistas.vista_publicada(anonima, _entidades())
    assert publicadas["de"].notna().all()
    assert "socios_em_comum_com" not in set(atributos["atributo"])
