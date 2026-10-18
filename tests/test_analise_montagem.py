"""A montagem: a parte do modelo que passou nas portas fica; a que não passou volta ao molde."""

import copy
import json

from src.analise_escrita import entrada as en
from src.analise_escrita import montagem, saida
from tests.ajudantes_da_analise import PAR_DA_CPFL

ENTRADA = json.loads((PAR_DA_CPFL / "entrada.json").read_text(encoding="utf-8"))
RESPOSTA = json.loads((PAR_DA_CPFL / "gabarito.json").read_text(encoding="utf-8"))[
    "analise"
]
HASH = en.hash_da_entrada(ENTRADA)


def _origens(m: montagem.Montagem) -> dict[str, str]:
    return {p.chave: p.origem for p in m.analise.partes}


def _com_numero_errado(parte: str) -> dict:
    resposta = copy.deepcopy(RESPOSTA)
    (alvo,) = [p for p in resposta["partes"] if p["chave"] == parte]
    frase = alvo["paragrafos"][1]["frases"][1]
    frase["texto"] = frase["texto"].replace("94 ofertas", "95 ofertas")
    return resposta


def test_resposta_que_passa_fica_toda_do_modelo():
    m = montagem.analise_final(RESPOSTA, ENTRADA, HASH)
    assert set(_origens(m).values()) == {saida.ORIGEM_MODELO}
    assert m.motivo is None
    assert m.conferencia is not None and m.conferencia.aprovada


def test_parte_reprovada_vira_molde():
    m = montagem.analise_final(_com_numero_errado("dinheiro"), ENTRADA, HASH)
    origens = _origens(m)
    assert origens.pop("dinheiro") == saida.ORIGEM_MOLDE
    assert set(origens.values()) == {saida.ORIGEM_MODELO}
    assert m.conferencia is not None
    assert m.conferencia.partes_reprovadas == frozenset({"dinheiro"})


def test_hash_diferente_mostra_o_molde():
    m = montagem.analise_final(RESPOSTA, ENTRADA, "outro hash")
    assert set(_origens(m).values()) == {saida.ORIGEM_MOLDE}
    assert m.motivo == montagem.FICHA_NOVA


def test_sem_resposta_tudo_molde():
    m = montagem.analise_final(None, ENTRADA, None)
    assert set(_origens(m).values()) == {saida.ORIGEM_MOLDE}
    assert m.motivo == montagem.SEM_RESPOSTA
    assert m.conferencia is None


def test_resposta_fora_do_formato_tudo_molde():
    m = montagem.analise_final({"partes": "texto solto"}, ENTRADA, HASH)
    assert set(_origens(m).values()) == {saida.ORIGEM_MOLDE}
    assert m.motivo is not None and m.motivo.startswith(montagem.FORA_DO_FORMATO)


def test_parte_reprovada_na_porta2_vira_molde():
    m = montagem.analise_final(RESPOSTA, ENTRADA, HASH, reprovadas={"quem_manda"})
    assert _origens(m)["quem_manda"] == saida.ORIGEM_MOLDE
    assert _origens(m)["o_que_e"] == saida.ORIGEM_MODELO


def test_sem_o_pro_parte_que_cita_o_dossie_vira_molde_sem_o_dossie():
    m = montagem.analise_final(RESPOSTA, ENTRADA, HASH, incluir_so_pro=False)
    so_pro = {
        linha["id"]
        for linha in ENTRADA["linhas"]
        if linha.get("so_pro") and linha["id"] not in ENTRADA["obrigatorias"]
    }
    for parte in m.analise.partes:
        notas = {n for p in parte.paragrafos for f in p.frases for n in f.notas}
        assert not notas & so_pro, parte.chave
    assert (
        _origens(m)["o_que_mudou"] == saida.ORIGEM_MOLDE
    )  # cita os negócios do dossiê
