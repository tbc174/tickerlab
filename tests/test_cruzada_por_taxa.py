"""Conferência por taxa de acordo da Receita contra outro órgão (D10.6). Só regra, com dados de mentira."""

import pandas as pd

from base import cruzada_por_taxa as ct
from base.cruzada import OUTRO_ORGAO

PAR = ct.ParPorTaxa("par", "teste", 0.8, ("a", "b"))


def _frame(concordam: int, causas: list[str]) -> pd.DataFrame:
    linhas = [{"concorda": True, "causa": None}] * concordam
    linhas += [{"concorda": False, "causa": c} for c in causas]
    return pd.DataFrame(linhas, columns=["concorda", "causa"])


def test_pisos_congelados():
    # congelados em 11/11/2026, depois de ver as primeiras medidas: mudar um piso é decisão da Diretoria
    assert (ct.PISO_DA_UF, ct.PISO_DA_SITUACAO, ct.PISO_DA_RAZAO_SOCIAL) == (
        0.95,
        0.90,
        0.80,
    )
    assert ct.MAXIMO_NAO_EXPLICADO == 0.20


def test_pares_sao_de_outro_orgao_e_dizem_o_limite():
    assert len({p.nome for p in ct.PARES}) == len(ct.PARES)
    for par in ct.PARES:
        assert par.independencia == OUTRO_ORGAO
        assert "não é amostra" in par.limite and "MEI" in par.limite
        assert par.tabelas and par.piso in (0.95, 0.90, 0.80)


def test_taxa_e_piso():
    ok = ct.avaliar(PAR, _frame(8, ["x", "x"]))
    assert (ok.comparadas, ok.concordam, ok.taxa, ok.aprovado) == (10, 8, 0.8, True)
    assert not ct.avaliar(PAR, _frame(7, ["x"] * 3)).aprovado
    assert not ct.avaliar(PAR, _frame(0, [])).aprovado  # sem comparação não prova nada


def test_causas_e_aviso_do_nao_explicado():
    r = ct.avaliar(PAR, _frame(80, ["renomeação"] * 15 + [ct.NAO_EXPLICADO] * 5))
    assert r.causas == {"renomeação": 15, ct.NAO_EXPLICADO: 5}
    assert r.nao_explicado == 0.25 and r.avisa_a_diretoria
    assert not ct.avaliar(
        PAR, _frame(80, ["a"] * 17 + [ct.NAO_EXPLICADO] * 3)
    ).avisa_a_diretoria  # 15%


def test_relatorio_sem_cnpj_nem_nome():
    dados = ct.avaliar(PAR, _frame(9, ["a"])).como_dict()
    assert set(dados) >= {"nome", "piso", "taxa", "aprovado", "causas", "limite"}
    assert "cnpj" not in str(dados).lower().replace("cnpjs", "")


def test_nomes_com_forma_juridica_e_acento_diferentes_concordam():
    assert ct.nomes_concordam(
        "CLARO TELECOM PARTICIPAÇÕES S.A.", "CLARO TELECOM PARTICIPACOES S/A"
    )
    assert ct.nomes_concordam(
        "Tivit Terceirização de Serviços S/A", "TIVIT TERCEIRIZACAO DE SERVICOS LTDA"
    )
    assert not ct.nomes_concordam("Marisa Lojas S.A.", "M SERVICOS LTDA")
    assert ct.semelhanca_do_nome("", "") == 0.0


def test_causa_do_nome():
    assert (
        ct.causa_do_nome("GETNET ADQ E SERV S.A.", "GETNET ADQUIRENCIA E SERVICOS S.A.")
        == "renomeação ou abreviação"
    )
    assert ct.causa_do_nome("BANCO ALFA", "FABRICA BETA") == ct.NAO_EXPLICADO


def test_causa_da_uf_na_ordem_das_regras():
    assert "outro estabelecimento" in ct.causa_da_uf("SP", {"SP", "RJ"}, 0.1, "02")
    assert "antigo" in ct.causa_da_uf("SP", {"RJ"}, 3.0, "02")
    assert "sem operação" in ct.causa_da_uf("SP", {"RJ"}, 0.5, "08")
    assert ct.causa_da_uf("SP", {"RJ"}, None, "02") == ct.NAO_EXPLICADO


def test_causa_da_situacao():
    assert "suspenso ou inapto" in ct.causa_da_situacao("04", 0.1)
    assert "anterior à baixa" in ct.causa_da_situacao("08", 2.0)
    assert ct.causa_da_situacao("08", 0.2) == ct.NAO_EXPLICADO


def test_causa_do_nome_grafia_marca_e_abreviacao():
    assert ct.causa_do_nome("JHSF PARTICIPACOES S.A.", "JHS F PARTICIPACOES S.A.") in {
        "grafia",
        ct.NAO_EXPLICADO,
    }
    assert "mesma marca" in ct.causa_do_nome(
        "TRUE SECURITIZADORA S.A.", "TRUE ADMINISTRADORA FIDUCIARIA LTDA"
    )
    assert ct.causa_do_nome(
        "CAIXA ADM DIV PUB ESTADUAL SA",
        "CAIXA DE ADMINISTRACAO DA DIVIDA PUBLICA ESTADUAL S/A",
    ) == ("renomeação ou abreviação")


def test_par_informativo_nao_prova_nem_reprova():
    informativos = [p for p in ct.PARES if p.informativo]
    assert [p.nome for p in informativos] == ["razao_social_ifdata_x_receita"]
    assert "não prova nem reprova" in informativos[0].informativo.lower()
    assert (
        ct.avaliar(informativos[0], _frame(1, ["x"])).informativo
        == informativos[0].informativo
    )
