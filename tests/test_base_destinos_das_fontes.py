"""Toda fonte do arquivista tem um destino (base/arquivo/destinos.py): ninguém baixa por dias sem tabela."""

import json
from pathlib import Path

from base.arquivo import destinos
from base.arquivo.destinos import DESTINOS, TIPOS, Destino
from base.arquivo.fontes import FONTES

CATALOGO = Path(__file__).parent.parent / "base" / "contratos" / "catalogo.json"


def test_toda_fonte_tem_destino():
    sem_destino = sorted({f.id for f in FONTES} - DESTINOS.keys())
    assert not sem_destino, (
        f"fontes sem destino em base/arquivo/destinos.py: {sem_destino}"
    )


def test_destino_sem_fonte_nao_existe():
    orfaos = sorted(DESTINOS.keys() - {f.id for f in FONTES})
    assert not orfaos, f"destinos de fontes que não existem mais: {orfaos}"


def test_tipo_do_destino_e_conhecido():
    assert {d.tipo for d in DESTINOS.values()} <= set(TIPOS)


def test_tabela_do_destino_esta_no_catalogo():
    catalogo = set(json.loads(CATALOGO.read_text(encoding="utf-8"))["tabelas"])
    for id_, destino in DESTINOS.items():
        faltam = [t for t in destino.tabelas if t not in catalogo]
        assert not faltam, f"{id_}: tabelas fora do catálogo: {faltam}"


def test_tipo_tabela_lista_tabelas_e_os_outros_nao():
    for id_, destino in DESTINOS.items():
        assert bool(destino.tabelas) == (destino.tipo == "tabela"), id_


def test_planejada_diz_onde():
    for id_, destino in DESTINOS.items():
        if destino.tipo == "planejada":
            assert destino.onde.strip(), f"{id_}: planejada sem `onde` (série e PR)"
        else:
            assert not destino.onde, f"{id_}: só a planejada tem `onde`"


def test_onde_nao_vaza_caminho_da_pasta_privada():
    for id_, destino in DESTINOS.items():
        assert "/" in destino.onde or not destino.onde, id_
        assert "\\" not in destino.onde and ":" not in destino.onde, id_
        assert "projeto-acoes" not in destino.onde, id_


def test_so_liga_diz_por_que():
    for id_, destino in DESTINOS.items():
        if destino.tipo in ("so_liga", "so_pesquisa", "planejada"):
            assert destino.porque.strip(), f"{id_}: sem `porque`"


def test_vigias_sao_os_termos_e_catalogos():
    vigias = {f.id for f in FONTES if f.vigia}
    marcados = {i for i, d in DESTINOS.items() if d.tipo == "vigia"}
    assert vigias == marcados


def test_placar_conta_por_tipo_e_fecha_com_as_fontes():
    placar = destinos.placar()
    assert set(placar) == set(TIPOS)
    assert sum(placar.values()) == len(FONTES)
    assert placar["vigia"] == sum(f.vigia for f in FONTES)


def test_destino_e_imutavel():
    destino = Destino("tabela", tabelas=("eventos",))
    try:
        destino.tipo = "vigia"  # type: ignore[misc]
    except AttributeError:
        return
    raise AssertionError("Destino deveria ser congelado")
