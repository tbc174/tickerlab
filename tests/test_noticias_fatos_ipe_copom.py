"""Gatilhos G2 (fato relevante) e G3 (Copom) das notas de dado (ADR 0093, plano, Tarefa 5)."""

from datetime import UTC, date, datetime

import pandas as pd
import pytest

from base.noticias_fatos import (
    COLUNAS_DOS_FATOS,
    COLUNAS_DOS_NUMEROS,
    fatos_de_fato_relevante,
    fatos_do_copom,
)
from src.topicos import topico_do_titulo

ACME = "11.111.111/0001-11"
OUTRA = "22.222.222/0001-22"
COLETADO = datetime(2026, 10, 17, tzinfo=UTC)
LINK = "https://www.rad.cvm.gov.br/ENET/frmDownloadDocumento.aspx?numProtocolo=1"


def _evento(
    protocolo,
    assunto,
    *,
    cnpj=ACME,
    categoria="Fato Relevante",
    versao=1,
    publicado="2026-10-14",
    **extra,
):
    linha = {
        "protocolo": protocolo,
        "versao": versao,
        "cnpj": cnpj,
        "empresa": "ACME S.A.",
        "categoria": categoria,
        "tipo": "",
        "assunto": assunto,
        "rotulo": "Fato relevante",
        "tema": "eventos",
        "materialidade": 80,
        "referencia": pd.Timestamp(publicado),
        "publicado_em": pd.Timestamp(publicado),
        "link": f"{LINK}{protocolo}",
    }
    linha.update(extra)
    return linha


def _eventos(*linhas):
    return pd.DataFrame(list(linhas))


def _g2(eventos, dia=date(2026, 10, 15), universo=(ACME,), **opcoes):
    return fatos_de_fato_relevante(
        eventos, set(universo), dia, coletado_em=COLETADO, **opcoes
    )


# --- G2: fato relevante ---------------------------------------------------------------------------


def test_so_fato_relevante_versao_1_de_companhia_do_universo():
    eventos = _eventos(
        _evento("A", "ACME conclui aquisição da Beta"),
        _evento("B", "Desempenho 4T25", categoria="Comunicado ao Mercado"),
        _evento("C", "ACME conclui aquisição da Gama", versao=2),
        _evento("D", "Outra conclui aquisição da Beta", cnpj=OUTRA),
    )
    fatos, numeros = _g2(eventos)
    assert fatos["chave_de_origem"].tolist() == ['{"protocolo":"A","versao":1}']
    assert numeros.empty
    assert list(fatos.columns) == COLUNAS_DOS_FATOS
    assert list(numeros.columns) == COLUNAS_DOS_NUMEROS


def test_topico_vem_das_regras_do_titulo():
    assunto = "ACME conclui aquisição da Beta"
    fatos, _ = _g2(_eventos(_evento("A", assunto)))
    leitura = topico_do_titulo(assunto)
    fato = fatos.iloc[0]
    assert fato["topico"] == leitura.principal == "AQUISICAO"
    assert fato["metodo_do_topico"] == leitura.metodo == "regra_titulo"
    assert fato["versao_do_topico"] == leitura.versao


def test_campos_do_fato_relevante():
    fatos, _ = _g2(_eventos(_evento("A", "ACME conclui aquisição da Beta")))
    fato = fatos.iloc[0]
    assert fato["pauta"] == "fato_relevante"
    assert fato["versao_do_gatilho"] == "fato-relevante-1.0"
    assert fato["tabela_de_origem"] == "eventos"
    assert fato["cnpj"] == ACME
    assert fato["empresa"] == "ACME S.A."
    assert fato["aconteceu_em"] == pd.Timestamp("2026-10-14")
    assert fato["publico_em"] == pd.Timestamp("2026-10-14")
    assert fato["link"] == f"{LINK}A"
    assert fato["trecho"] == "ACME conclui aquisição da Beta"
    assert fato["licenca"] == "cvm"
    assert not fato["reapresentacao"]
    assert fato["marcas"] == []


def test_outros_sai_sem_assunto():
    fatos, _ = _g2(_eventos(_evento("A", "Investor Tour 2026")))
    fato = fatos.iloc[0]
    assert fato["topico"] == "OUTROS"
    assert fato["trecho"] == ""
    assert fato["marcas"] == []  # não foi cortado por filtro: o assunto só não diz nada


def test_trecho_com_nome_de_pessoa_e_cortado_e_marcado():
    fatos, _ = _g2(_eventos(_evento("A", "Renúncia de Diretor Fulano de Tal")))
    fato = fatos.iloc[0]
    assert fato["topico"] == "ADMINISTRACAO"
    assert fato["trecho"] == ""
    assert fato["marcas"] == ["trecho_cortado"]


def test_nome_conhecido_no_assunto_corta_o_trecho():
    eventos = _eventos(
        _evento("A", "ACME conclui aquisição da Beta de Maria Souza Lima")
    )
    fatos, _ = _g2(eventos, pessoas={"maria souza lima"})
    assert fatos.iloc[0]["trecho"] == ""
    assert fatos.iloc[0]["marcas"] == ["trecho_cortado"]


def test_cpf_no_assunto_corta_o_trecho():
    fatos, _ = _g2(
        _eventos(_evento("A", "ACME conclui aquisição da Beta de 123.456.789-09"))
    )
    assert fatos.iloc[0]["trecho"] == ""
    assert fatos.iloc[0]["marcas"] == ["trecho_cortado"]


def test_trecho_longo_fica_com_200_caracteres_literais():
    assunto = "ACME conclui aquisição " + "da Beta " * 60
    fato = _g2(_eventos(_evento("A", assunto)))[0].iloc[0]
    assert len(fato["trecho"]) <= 200
    assert assunto.startswith(fato["trecho"])


def test_varios_assuntos_ficam_literais_no_trecho():
    assunto = "ACME conclui aquisição da Beta||Dividendos do ano"
    fato = _g2(_eventos(_evento("A", assunto)))[0].iloc[0]
    assert fato["trecho"] == assunto


def test_assunto_vazio_nao_quebra():
    fato = _g2(_eventos(_evento("A", None)))[0].iloc[0]
    assert fato["topico"] == "OUTROS"
    assert fato["trecho"] == ""


def test_g2_janela_e_universo():
    eventos = _eventos(
        _evento("A", "ACME conclui aquisição da Beta", publicado="2026-10-14")
    )
    assert _g2(eventos, dia=date(2026, 10, 14))[
        0
    ].empty  # só o que ficou público até ontem
    assert (
        len(_g2(eventos, dia=date(2026, 10, 21))[0]) == 1
    )  # 14, 15, 16, 19, 20 = 5 dias úteis
    assert _g2(eventos, dia=date(2026, 10, 22))[0].empty  # 6 dias úteis: velho demais
    assert _g2(eventos, universo=())[0].empty


def test_g2_id_e_hash_estaveis():
    eventos = _eventos(
        _evento("A", "ACME conclui aquisição da Beta"),
        _evento("B", "Investor Tour 2026"),
    )
    um = _g2(eventos)[0]
    dois = _g2(eventos.iloc[::-1].reset_index(drop=True), dia=date(2026, 10, 16))[0]
    assert um["id_fato"].tolist() == dois["id_fato"].tolist()
    assert um["hash_da_linha"].tolist() == dois["hash_da_linha"].tolist()
    assert um["id_fato"].is_unique
    assert all(len(h) == 64 for h in um["hash_da_linha"])


# --- G3: Copom ------------------------------------------------------------------------------------

REUNIOES = pd.DataFrame(
    {
        "reuniao": [280, 281],
        "data": pd.to_datetime(["2026-08-05", "2026-09-16"]),
        "meta_selic": [14.0, 13.75],
        "link": [
            "https://www.bcb.gov.br/controleinflacao/comunicadoscopom/280",
            "https://www.bcb.gov.br/controleinflacao/comunicadoscopom/281",
        ],
        "fonte": ["conferida"] * 2,
        "conferido_em": pd.to_datetime(["2026-10-17"] * 2),
    }
)


def _selic(meta_sgs=13.75, divulgado_meta="2026-09-17", focus=None):
    """SGS 432 do dia útil seguinte à reunião de 16/09 (quinta, 17/09) e o Focus anual."""
    focus = (
        focus
        if focus is not None
        else [("2026-09-08", 14.5), ("2026-09-14", 14.25), ("2026-09-16", 14.0)]
    )
    linhas = [
        {
            "serie": "bcb-sgs-432",
            "referencia": pd.Timestamp("2026-09-17"),
            "valor": meta_sgs,
            "divulgado_em": pd.Timestamp(divulgado_meta),
            "origem_coletada_em": pd.Timestamp("2026-09-18 08:00", tz="UTC"),
        },
        {  # a meta da reunião anterior, vigente em 06/08
            "serie": "bcb-sgs-432",
            "referencia": pd.Timestamp("2026-08-06"),
            "valor": 14.0,
            "divulgado_em": pd.Timestamp("2026-08-06"),
            "origem_coletada_em": pd.Timestamp("2026-08-07 08:00", tz="UTC"),
        },
    ]
    linhas += [
        {
            "serie": "focus-selic-anual",
            "referencia": pd.Timestamp(ref),
            "valor": valor,
            "divulgado_em": pd.Timestamp(safra),
            "origem_coletada_em": pd.Timestamp(safra, tz="UTC"),
        }
        for safra, valor in focus
        for ref in ("2026-12-31",)
    ]
    linhas.append(  # o Focus do ano seguinte não entra na nota
        {
            "serie": "focus-selic-anual",
            "referencia": pd.Timestamp("2027-12-31"),
            "valor": 11.0,
            "divulgado_em": pd.Timestamp("2026-09-14"),
            "origem_coletada_em": pd.Timestamp("2026-09-14", tz="UTC"),
        }
    )
    selic = pd.DataFrame(linhas)
    selic["publico_em"] = selic["divulgado_em"]
    return selic


def _g3(selic, dia=date(2026, 9, 18), reunioes=REUNIOES):
    return fatos_do_copom(reunioes, selic, dia)


def _n(numeros, campo):
    achado = numeros[numeros["campo"] == campo]
    assert len(achado) == 1, campo
    return achado.iloc[0]


def test_copom_com_as_duas_fontes_de_acordo():
    fatos, numeros = _g3(_selic())
    assert len(fatos) == 1
    fato = fatos.iloc[0]
    assert fato["pauta"] == "copom"
    assert fato["versao_do_gatilho"] == "copom-1.0"
    assert fato["chave_de_origem"] == '{"reuniao":281}'
    assert fato["cnpj"] == ""
    assert fato["empresa"] == ""
    assert fato["tabela_de_origem"] == "bcb_selic_focus + copom_reunioes"
    assert fato["aconteceu_em"] == fato["publico_em"] == pd.Timestamp("2026-09-16")
    assert fato["link"].endswith("/281")
    assert fato["licenca"] == "bcb"
    assert fato["marcas"] == []
    assert fato["coletado_em"] == pd.Timestamp("2026-09-18 08:00", tz="UTC")
    meta = _n(numeros, "meta_selic")
    assert (meta["valor"], meta["unidade"], meta["periodo"]) == (
        13.75,
        "pct_ao_ano",
        "16/09/2026",
    )
    assert meta["origem_divulgado_em"] == pd.Timestamp("2026-09-16")
    anterior = _n(numeros, "meta_selic_anterior")
    assert anterior["valor"] == 14.0
    assert anterior["periodo"] == "05/08/2026"


def test_focus_e_a_ultima_pesquisa_antes_da_reuniao_do_ano_da_reuniao():
    """A de 16/09 saiu no dia da reunião e a de 2027 é de outro ano: nenhuma das duas entra."""
    _, numeros = _g3(_selic())
    focus = _n(numeros, "focus_selic_fim_do_ano")
    assert focus["valor"] == 14.25  # a de 14/09
    assert focus["origem_divulgado_em"] == pd.Timestamp("2026-09-14")
    assert focus["periodo"] == "fim de 2026"
    assert focus["unidade"] == "pct_ao_ano"


def test_so_a_pesquisa_do_dia_da_reuniao_deixa_a_nota_sem_focus():
    _, numeros = _g3(_selic(focus=[("2026-09-16", 14.0)]))
    assert numeros[numeros["campo"] == "focus_selic_fim_do_ano"].empty
    assert not numeros[numeros["campo"] == "meta_selic"].empty


def test_meta_da_sgs_diferente_da_conferida_marca_fontes_divergem():
    fatos, numeros = _g3(_selic(meta_sgs=14.0))
    assert len(fatos) == 1
    assert fatos.iloc[0]["marcas"] == ["fontes_divergem"]
    assert (
        _n(numeros, "meta_selic")["valor"] == 13.75
    )  # a conferida; quem decide é a revisão


def test_sem_o_valor_da_sgs_ate_ontem_nao_ha_fato():
    assert _g3(_selic(divulgado_meta="2026-09-18"))[0].empty  # chegou hoje: ainda não


def test_reuniao_so_com_data_ate_ontem():
    assert _g3(_selic(), dia=date(2026, 9, 16))[0].empty


def test_reuniao_antiga_demais_nao_vira_nota():
    # de 16/09 a 23/09 são 5 dias úteis (16, 17, 18, 21, 22); a 24/09 já são 6
    assert len(_g3(_selic(), dia=date(2026, 9, 23))[0]) == 1
    assert _g3(_selic(), dia=date(2026, 9, 24))[0].empty


def test_primeira_reuniao_da_tabela_nao_tem_meta_anterior():
    fatos, numeros = _g3(_selic(), reunioes=REUNIOES.iloc[1:].reset_index(drop=True))
    assert len(fatos) == 1
    assert numeros[numeros["campo"] == "meta_selic_anterior"].empty


def test_copom_id_e_hash_estaveis_e_origem_sem_futuro():
    um = _g3(_selic())
    dois = _g3(_selic().iloc[::-1].reset_index(drop=True), dia=date(2026, 9, 21))
    assert um[0]["id_fato"].tolist() == dois[0]["id_fato"].tolist()
    assert um[0]["hash_da_linha"].tolist() == dois[0]["hash_da_linha"].tolist()
    publico = um[0].iloc[0]["publico_em"]
    assert (um[1]["origem_divulgado_em"] <= publico).all()


def test_copom_sem_nada_devolve_tabelas_vazias_com_as_colunas():
    fatos, numeros = _g3(_selic(), dia=date(2026, 1, 5))
    assert fatos.empty
    assert list(fatos.columns) == COLUNAS_DOS_FATOS
    assert list(numeros.columns) == COLUNAS_DOS_NUMEROS


@pytest.mark.parametrize("campo", ["id_fato", "hash_da_linha"])
def test_ids_de_pautas_diferentes_nunca_colidem(campo):
    g2 = _g2(_eventos(_evento("281", "ACME conclui aquisição da Beta")))[0]
    g3 = _g3(_selic())[0]
    assert set(g2[campo]).isdisjoint(set(g3[campo]))
