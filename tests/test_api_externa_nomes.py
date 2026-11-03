"""A tabela única de nomes da API externa (B-32a; ADR 0108, D6 e D7).

Para fora, endereços, campos e códigos em inglês; dentro, colunas e contratos em português. A tradução
mora num lugar só, e um nome sem tradução não sai.
"""

import json
from pathlib import Path

import pytest

from base.dicionario import TABELAS
from src.api_externa import nomes

CONTRATOS = Path("base/contratos/v1")


def test_os_nomes_de_tempo_sao_os_do_d6():
    esperados = {
        "publico_em": "published_at",
        "visto_em": "observed_at",
        "referencia": "reference_period",
        "versao": "revision",
        "aconteceu_em": "valid_from",
        "coletado_em": "collected_at",
        "como_era_em": "known_at",
        "valia_em": "valid_at",
    }
    assert {nome: nomes.para_fora(nome) for nome in esperados} == esperados


def test_nome_sem_traducao_nao_sai():
    with pytest.raises(KeyError):
        nomes.para_fora("cpf_do_socio")


def test_a_traducao_e_de_mao_unica():
    # dois nomes de dentro com o mesmo nome de fora confundiriam quem integra
    de_fora = list(nomes.NOMES_DE_FORA.values())
    assert len(de_fora) == len(set(de_fora))


def test_nenhum_nome_de_fora_e_coluna_do_dicionario():
    # o D7: o inglês fica na porta; as tabelas e os contratos continuam em português
    de_fora = set(nomes.NOMES_DE_FORA.values())
    colunas = {coluna for tabela in TABELAS.values() for coluna in tabela.colunas}
    assert de_fora & colunas == set()


def test_nenhum_nome_de_fora_e_chave_de_contrato():
    de_fora = set(nomes.NOMES_DE_FORA.values())
    usados: set[str] = set()
    for arquivo in CONTRATOS.glob("*.json"):
        contrato = json.loads(arquivo.read_text(encoding="utf-8"))
        usados |= set(contrato.get("colunas", {}))
        usados |= set(contrato.get("chaves", []))
        usados |= set(contrato.get("datas", {}).values())
    assert usados, "nenhum contrato lido: o caminho mudou?"
    assert de_fora & usados == set()


def test_traduzir_chaves_troca_todas_as_chaves_e_mais_nada():
    dentro = {"valor": 1, "fontes": [{"fonte": "cvm", "licenca": "ODbL"}]}
    assert nomes.traduzir_chaves(dentro) == {
        "value": 1,
        "sources": [{"source": "cvm", "license": "ODbL"}],
    }


# ---------------------------------------------------------------- as linhas do portão saem traduzidas
# O catálogo passa cada finalidade, campo e fonte liberados por `para_fora` e `fontes_da_resposta`, que
# levantam erro sem tradução ou atribuição (500 no catálogo inteiro). Estes testes travam no CI a linha
# de direito nova que chegaria assim à produção (revisão cruzada do PR 1).


def test_toda_finalidade_tem_nome_de_fora():
    from src.portao_externo import Finalidade

    for finalidade in Finalidade:
        assert nomes.para_fora(finalidade.value)


def test_toda_linha_da_api_externa_tem_nome_de_fora_e_atribuicao():
    from src.api_externa import envelope
    from src.portao_externo import Canal, regras_vigentes

    linhas = [
        linha for linha in regras_vigentes().linhas if linha.canal == Canal.API_EXTERNA
    ]
    for linha in linhas:
        assert nomes.para_fora(linha.campo)
    fontes = {linha.fonte for linha in linhas}
    assert len(envelope.fontes_da_resposta(fontes)) == len(fontes)
