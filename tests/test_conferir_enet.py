"""A amostra da conferência ENET: sorteio com semente fixa, por data-base, para a DFP e para o ITR (linha 784)."""

import pandas as pd

from base.cruzada import PARES
from scripts import conferir_enet
from scripts.conferir_enet import RECORTES, sortear


def _indice(referencias: list[str], quantas: int) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "cnpj": f"{n:02d}.000.000/0001-00",
                "empresa": f"EMPRESA {n}",
                "documento": "ITR",
                "referencia": pd.Timestamp(referencia),
                "versao": versao,
                "recebido_em": pd.Timestamp("2025-11-01"),
                "link": f"http://exemplo/{n}/{versao}",
            }
            for referencia in referencias
            for n in range(quantas)
            for versao in (1, 2)
        ]
    )


def test_o_recorte_do_itr_sorteia_por_trimestre_e_e_repetivel() -> None:
    recorte = RECORTES["ITR"]
    datas = [d.strftime("%Y-%m-%d") for d in recorte.referencias]
    indice = _indice(datas, 60)
    bancos = {f"{n:02d}.000.000/0001-00" for n in range(8)}
    seguradoras = {f"{n:02d}.000.000/0001-00" for n in range(8, 14)}
    primeira = sortear(indice, bancos, seguradoras, recorte)
    segunda = sortear(indice, bancos, seguradoras, recorte)
    assert primeira.equals(segunda)  # semente fixa
    assert sorted(primeira["referencia"].unique()) == datas
    por_trimestre = primeira.groupby(["referencia", "grupo_da_amostra"]).size()
    assert (por_trimestre.xs("banco", level=1) == 4).all()
    assert (por_trimestre.xs("seguradora", level=1) == 2).all()
    assert (por_trimestre.xs("nao_financeira", level=1) == 14).all()
    assert (primeira["versao"] == 2).all()  # a versão mais nova de cada entrega


def test_o_recorte_da_dfp_continua_o_de_50_companhias_de_2024() -> None:
    recorte = RECORTES["DFP"]
    assert recorte.referencias == (pd.Timestamp(2024, 12, 31),)
    assert sum(recorte.quantas.values()) == 50
    assert recorte.amostra == conferir_enet.AMOSTRA
    assert recorte.indice.endswith("/DOC/DFP/DADOS/dfp_cia_aberta_2024.zip")


def test_o_recorte_do_itr_tem_60_pacotes_e_tolerancia_igual_a_da_dfp() -> None:
    recorte = RECORTES["ITR"]
    assert len(recorte.referencias) * sum(recorte.quantas.values()) == 60
    assert recorte.indice.endswith("/DOC/ITR/DADOS/itr_cia_aberta_2025.zip")
    pares = {p.nome: p for p in PARES}
    assert (
        pares["itr_enet_x_nossa_leitura"].tolerancia
        == pares["dfp_enet_x_nossa_leitura"].tolerancia
    )
