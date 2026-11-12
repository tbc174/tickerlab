"""CNES por competência (base/cnes.py). Nada vai à internet: a API é um dublê que pagina por `offset`
em itens, como a de verdade (formato conferido ao vivo em 04/11/2026)."""

from datetime import date

import pandas as pd
import pytest

from base import cnes

COLETA = date(2026, 11, 4)
COMPETENCIA = 202607


def _item(codigo: str, **campos: object) -> dict[str, object]:
    base: dict[str, object] = {
        "nu_comp": COMPETENCIA,
        "co_ibge": 330330,
        "co_cnes": codigo,
        "no_fantasia": f"FANTASIA {codigo}",
        "no_empresarial": f"EMPRESA {codigo}",
        "nu_cnpj": None,
        "nu_cnpj_mantenedora": None,
        "tp_gestao": "MUNICIPAL",
        "tp_unidade": "05 - HOSPITAL GERAL",
        "ds_class_estab": "Hospital",
        "ds_natureza_juridica": "Administração Pública",
        "no_grupo_nat_jur": "ADMINISTRACAO PUBLICA",
        "no_logradouro": "RUA DO SIGILO",
        "nu_endereco": "10",
        "ds_complemento": None,
        "nu_cep": "20000000",
        "nu_telefone": "2100000000",
        "ds_email": "contato@exemplo.invalid",
        "nu_latitude": -22.9,
        "nu_longitude": -43.2,
        "ds_status": "01 - ATIVO",
    }
    base.update(campos)
    return base


def _api(por_competencia: dict[int, list[dict[str, object]]]):
    """Dublê da API: respeita `offset` e `limit` em itens e conta as chamadas."""
    chamadas: list[tuple[int, int, int]] = []

    def buscar(competencia: int, offset: int, limit: int) -> dict[str, object]:
        chamadas.append((competencia, offset, limit))
        itens = por_competencia.get(competencia, [])
        return {cnes.CHAVE_DA_LISTA: itens[offset : offset + limit]}

    buscar.chamadas = chamadas  # type: ignore[attr-defined]
    return buscar


def test_paginacao_por_offset_nao_pula_nem_repete_item():
    itens = [_item(f"{n:07d}") for n in range(23)]
    api = _api({COMPETENCIA: itens})
    achados = cnes.buscar_competencia(api, COMPETENCIA, por_pagina=5)
    assert [i["co_cnes"] for i in achados] == [i["co_cnes"] for i in itens]
    # 4 páginas cheias de 5, uma de 3 e a vazia que encerra; o offset é a soma dos itens recebidos
    assert [offset for _, offset, _ in api.chamadas] == [0, 5, 10, 15, 20, 23]


def test_paginacao_que_repete_item_e_erro():
    itens = [_item("0000001"), _item("0000002")]

    def volta_ao_inicio(*_: int) -> dict[str, object]:
        return {cnes.CHAVE_DA_LISTA: itens}  # ignora o offset: a página 2 repete a 1

    with pytest.raises(ValueError, match="duas vezes"):
        cnes.buscar_competencia(volta_ao_inicio, COMPETENCIA, por_pagina=2)


def test_resposta_sem_a_lista_e_erro_e_nao_competencia_vazia():
    with pytest.raises(TypeError, match="lista"):
        cnes.itens_da_pagina({"erro": "fora do ar"})


def test_os_dois_cnpjs_ficam_cada_um_na_sua_coluna():
    hospital = _item(
        "2627183", nu_cnpj="33.000.167/0001-01", nu_cnpj_mantenedora="33000167000101"
    )
    unidade_publica = _item(
        "9633758", nu_cnpj=None, nu_cnpj_mantenedora="29.138.328/0001-50"
    )
    tabela = cnes.tabela_da_competencia(
        [hospital, unidade_publica], COMPETENCIA, COLETA
    )
    hospital_, publica = tabela.iloc[0], tabela.iloc[1]
    assert hospital_["cnpj"] == "33000167000101"
    assert hospital_["cnpj_mantenedora"] == "33000167000101"
    assert publica["cnpj"] == ""
    assert publica["cnpj_mantenedora"] == "29138328000150"
    assert publica["razao_social"] == "EMPRESA 9633758"


def test_pessoa_fisica_fica_sem_nome_e_cpf_nao_vira_cnpj():
    consultorio = _item("0000009", nu_cnpj="888.000.000-46", nu_cnpj_mantenedora=None)
    linha = cnes.tabela_da_competencia([consultorio], COMPETENCIA, COLETA).iloc[0]
    assert linha["cnpj"] == ""
    assert linha["cnpj_mantenedora"] == ""
    assert linha["razao_social"] == ""
    assert linha["nome_fantasia"] == ""
    assert (
        linha["codigo_cnes"] == "0000009"
    )  # o estabelecimento existe, só não tem nome guardado


def test_pessoa_fisica_fica_sem_coordenada_e_pessoa_juridica_mantem():
    """Condição do MS (05/11/2026): a coordenada do consultório, com o código CNES, acharia a pessoa."""
    consultorio = _item("0000009", nu_cnpj="888.000.000-46", nu_cnpj_mantenedora=None)
    hospital = _item("2627183", nu_cnpj="33.000.167/0001-01")
    tabela = cnes.tabela_da_competencia([consultorio, hospital], COMPETENCIA, COLETA)
    pessoa, empresa = tabela.iloc[0], tabela.iloc[1]
    assert pd.isna(pessoa["latitude"]) and pd.isna(pessoa["longitude"])
    assert empresa["latitude"] == -22.9
    assert empresa["longitude"] == -43.2


def test_endereco_telefone_e_email_nunca_entram():
    tabela = cnes.tabela_da_competencia([_item("0000001")], COMPETENCIA, COLETA)
    assert list(tabela.columns) == list(cnes.COLUNAS)
    texto = tabela.astype(str).to_string()
    for sigilo in ("RUA DO SIGILO", "20000000", "2100000000", "exemplo.invalid"):
        assert sigilo not in texto


def test_tipos_e_disponibilidade_pela_data_da_coleta():
    item = _item("0000001", nu_latitude=None, nu_cnpj_mantenedora="29.138.328/0001-50")
    linha = cnes.tabela_da_competencia([item], COMPETENCIA, COLETA).iloc[0]
    assert linha["competencia"] == COMPETENCIA
    assert linha["codigo_ibge_municipio"] == "330330"
    assert pd.isna(linha["latitude"])
    assert linha["longitude"] == -43.2
    assert linha["disponivel_em"] == pd.Timestamp(COLETA)  # nunca a competência


def test_competencia_vazia_e_registrada_e_nao_tratada_como_sem_estabelecimentos():
    api = _api({COMPETENCIA: [_item("0000001")]})
    tabela, situacao = cnes.coletar_competencia(api, 202608, COLETA)
    assert tabela.empty
    assert list(tabela.columns) == list(cnes.COLUNAS)
    assert situacao["situacao"] == cnes.COMPETENCIA_VAZIA
    assert situacao["linhas"] == 0
    assert situacao["competencia"] == 202608


def test_competencia_com_dados_registra_a_contagem():
    api = _api({COMPETENCIA: [_item("0000001"), _item("0000002")]})
    tabela, situacao = cnes.coletar_competencia(api, COMPETENCIA, COLETA)
    assert len(tabela) == 2
    assert situacao["situacao"] == cnes.COMPETENCIA_COM_DADOS
    assert situacao["linhas"] == 2
    assert tabela[cnes.CHAVE].duplicated().sum() == 0


def test_mesmo_estabelecimento_em_competencias_diferentes_nao_e_repeticao():
    julho = cnes.tabela_da_competencia([_item("0000001")], 202607, COLETA)
    junho = cnes.tabela_da_competencia(
        [_item("0000001", nu_comp=202606)], 202606, COLETA
    )
    junto = pd.concat([julho, junho])
    assert not junto.duplicated(cnes.CHAVE).any()
