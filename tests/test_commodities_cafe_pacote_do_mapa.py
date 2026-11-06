"""O pacote do Mapa do café e a vista de cada tipo (plano do café, PR 10)."""

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from base.commodities.area_municipio import ler_mapbiomas, ler_pam
from base.commodities.clima_regiao import COLUNAS_DIARIAS, FONTE_CHIRPS
from src.commodities.cafe import calendario
from src.commodities.cafe.pacote_do_mapa import (
    AREA,
    CAMADAS,
    CHUVA,
    FORA_DAS_REGIOES,
    GEADA,
    PRODUCAO,
    SEM_GEADA,
    VERSAO_DO_PACOTE,
    PacoteDoMapa,
    do_dicionario,
    em_dicionario,
    gravar_pacote,
    ler_pacote,
    montar_pacote,
    montar_vista,
    texto_da_fase,
    ultimo_ano_da_pam,
    ultimo_inverno_publicado,
    vista_em_dicionario,
)
from src.commodities.cafe.regioes import REGIOES

PASTA = Path(__file__).resolve().parent.parent / "dados_de_exemplo" / "commodities"
PATOS_DE_MINAS, CACOAL, LINHARES, JUIZ_DE_FORA, FRANCA = (
    "3148004",
    "1100049",
    "3203205",
    "3136702",
    "3516200",
)
HOJE = date(2026, 11, 5)  # a PAM de 2025 já saiu (31/10/2026); o clima, até agosto
REGIOES_COM_CLIMA = (
    "cerrado-mineiro",
    "es-norte",
    "mogiana",
)  # Rondônia fica sem clima
CHUVA_DO_MES, NORMAL_DO_MES = 30.0, 40.0
VEDADAS = ("quebrada", "golpe", "calote", "recomendamos", "safra boa", "preço vai")


def _mensal() -> pd.DataFrame:
    """Chuva de junho a outubro de 2026 (CHIRPS publica 60 dias depois do fim do mês)."""
    linhas = []
    for regiao in REGIOES_COM_CLIMA:
        for mes in range(6, 11):
            competencia = pd.Timestamp(2026, mes, 1) + pd.offsets.MonthEnd(0)
            linhas.append(
                {
                    "regiao": regiao,
                    "competencia": competencia,
                    "fonte": FONTE_CHIRPS,
                    "chuva_mm": CHUVA_DO_MES,
                    "chuva_normal_mm": NORMAL_DO_MES,
                    "chuva_anomalia_mm": CHUVA_DO_MES - NORMAL_DO_MES,
                    "n_estacoes": None,
                    "disponivel_em": (competencia + pd.Timedelta(days=60)).date(),
                }
            )
    return pd.DataFrame(linhas)


def _diario_vazio() -> pd.DataFrame:
    return pd.DataFrame(columns=[*COLUNAS_DIARIAS, "regiao"])


def pacote_de_exemplo() -> PacoteDoMapa:
    """O pacote dos 5 municípios de exemplo em `HOJE` (também usado pela rota e pela tela)."""
    pam = ler_pam(
        json.loads(
            (PASTA / "pam_cafe_area_e_producao_5_municipios.json").read_text(
                encoding="utf-8"
            )
        )
    )
    area = ler_mapbiomas(PASTA / "mapbiomas_cafe_5_municipios.xlsx")
    malha = json.loads((PASTA / "malha_pequena.geojson").read_text(encoding="utf-8"))
    return montar_pacote(pam, area, _mensal(), _diario_vazio(), malha, HOJE)


@pytest.fixture(scope="module")
def pacote() -> PacoteDoMapa:
    return pacote_de_exemplo()


def _municipio(vista, codigo: str):
    return next(m for m in vista.municipios if m.codigo == codigo)


def _regiao(vista, regiao_id: str):
    return next(r for r in vista.regioes if r.id == regiao_id)


# --- sem olhar o futuro ------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("hoje", "ano"),
    [(date(2026, 10, 30), 2024), (date(2026, 10, 31), 2025), (date(2027, 1, 2), 2025)],
)
def test_o_ano_da_pam_e_o_ultimo_ja_publicado(hoje, ano):
    assert ultimo_ano_da_pam(hoje) == ano


@pytest.mark.parametrize(
    ("hoje", "ano"),
    [(date(2026, 10, 14), 2025), (date(2026, 10, 15), 2026), (date(2026, 3, 1), 2025)],
)
def test_o_inverno_da_geada_e_o_ultimo_ja_publicado(hoje, ano):
    assert ultimo_inverno_publicado(hoje) == ano  # agosto + 45 dias do INMET


def test_o_pacote_nao_usa_a_pam_que_ainda_nao_saiu(pacote):
    pam = pd.DataFrame(
        {
            "codigo": [PATOS_DE_MINAS],
            "nome": ["Patos de Minas"],
            "uf": ["MG"],
            "ano": [2025],
            **{
                f"{grandeza}_{tipo}_{u}": [1.0]
                for grandeza, u in (("area", "ha"), ("producao", "t"))
                for tipo in ("arabica", "conilon", "total")
            },
        }
    )
    vazio = pd.DataFrame(columns=["codigo", "ano", "area_mapbiomas_ha"])
    with pytest.raises(ValueError, match="sem dados"):
        montar_pacote(
            pam, vazio, _mensal(), _diario_vazio(), pacote.malha, date(2026, 10, 18)
        )


def test_a_chuva_so_usa_os_meses_ja_publicados(pacote):
    clima = {c.regiao: c for c in pacote.clima}
    chuva = clima["cerrado-mineiro"].chuva
    assert chuva.periodo == (
        date(2026, 6, 1),
        date(2026, 8, 31),
    )  # setembro sai em 29/11
    assert chuva.valor == pytest.approx(3 * CHUVA_DO_MES)
    assert chuva.normal == pytest.approx(3 * NORMAL_DO_MES)


# --- o pacote ----------------------------------------------------------------------------------------
def test_o_pacote_tem_os_dois_cafes_e_nao_o_total(pacote):
    assert set(pacote.por_tipo) == {"arabica", "conilon"}
    assert {d.ano for d in pacote.por_tipo.values()} == {2025}
    assert pacote.gerado_em == HOJE


def test_a_malha_so_tem_os_municipios_do_mapa(pacote):
    codigos = {f["properties"]["codarea"] for f in pacote.malha["features"]}
    assert codigos == {LINHARES}  # a malha de exemplo é só do ES


def test_o_pacote_vai_e_volta_pelo_json(pacote, tmp_path):
    caminho = tmp_path / "mapa.json"
    gravar_pacote(pacote, caminho)
    lido = ler_pacote(caminho)
    assert lido is not None
    assert em_dicionario(lido) == em_dicionario(pacote)


def test_pacote_sem_arquivo_ou_estragado_nao_e_mostrado(pacote, tmp_path):
    assert ler_pacote(tmp_path / "nao-existe.json") is None
    estragado = tmp_path / "estragado.json"
    estragado.write_text("{", encoding="utf-8")
    assert ler_pacote(estragado) is None
    outra_versao = tmp_path / "outra.json"
    dados = em_dicionario(pacote) | {"versao": VERSAO_DO_PACOTE + 1}
    outra_versao.write_text(json.dumps(dados), encoding="utf-8")
    assert ler_pacote(outra_versao) is None


def test_pacote_com_um_tipo_so_e_recusado(pacote):
    dados = em_dicionario(pacote)
    dados["por_tipo"] = {"arabica": dados["por_tipo"]["arabica"]}
    with pytest.raises(ValueError, match="tipos"):
        do_dicionario(dados)


def test_o_arquivo_vem_da_variavel_de_ambiente(pacote, tmp_path, monkeypatch):
    caminho = tmp_path / "outro.json"
    gravar_pacote(pacote, caminho)
    monkeypatch.setenv("TICKERLAB_MAPA_DO_CAFE", str(caminho))
    assert ler_pacote() is not None


# --- a vista -----------------------------------------------------------------------------------------
def test_a_vista_tem_as_quatro_camadas_com_fonte(pacote):
    vista = montar_vista(pacote, "arabica", 11)
    assert tuple(c.chave for c in vista.camadas) == CAMADAS
    assert all(c.o_que_e and c.fonte for c in vista.camadas)
    assert "2025" in vista.camadas[0].fonte


def test_o_valor_de_cada_camada_vem_da_pam_e_do_clima(pacote):
    vista = montar_vista(pacote, "arabica", 11)
    patos = _municipio(vista, PATOS_DE_MINAS)
    assert patos.regiao == "cerrado-mineiro"
    assert patos.valores[PRODUCAO] == 15253.0
    assert patos.valores[AREA] == 9175.0
    assert patos.valores[CHUVA] == pytest.approx(75.0)  # 90 mm contra 120 mm
    assert patos.area_mapbiomas_ha == pytest.approx(7838.29498)


def test_municipio_sem_o_cafe_do_tipo_fica_cinza_com_motivo(pacote):
    vista = montar_vista(pacote, "arabica", 11)
    cacoal = _municipio(vista, CACOAL)
    assert cacoal.valores[PRODUCAO] is None
    assert cacoal.sem_dado[PRODUCAO] == (
        "a PAM não registra café arábica neste município em 2025"
    )
    conilon = montar_vista(pacote, "conilon", 11)
    assert _municipio(conilon, CACOAL).valores[PRODUCAO] == 17066.0


def test_municipio_fora_das_regioes_nao_ganha_indice_de_clima(pacote):
    juiz_de_fora = _municipio(montar_vista(pacote, "arabica", 11), JUIZ_DE_FORA)
    assert juiz_de_fora.regiao is None
    assert juiz_de_fora.valores[CHUVA] is None
    assert juiz_de_fora.sem_dado[CHUVA] == FORA_DAS_REGIOES


def test_sem_diario_do_inmet_a_geada_fica_sem_dado(pacote):
    patos = _municipio(montar_vista(pacote, "arabica", 11), PATOS_DE_MINAS)
    assert patos.valores[GEADA] is None
    assert patos.sem_dado[GEADA] == SEM_GEADA


def test_regiao_sem_clima_diz_o_motivo(pacote):
    cacoal = _municipio(montar_vista(pacote, "conilon", 11), CACOAL)
    assert cacoal.regiao == "rondonia"
    assert "chuva" in cacoal.sem_dado[CHUVA]


def test_a_regiao_diz_a_chuva_com_normal_fonte_e_periodo(pacote):
    cerrado = _regiao(montar_vista(pacote, "arabica", 11), "cerrado-mineiro")
    assert cerrado.chuva.texto == (
        "Chuva de 90 mm contra a normal de 120 mm (1991–2020), CHIRPS v2.0 (satélite e "
        "pluviômetros, UCSB; Funk et al. 2015), de 01/06/2026 a 31/08/2026."
    )
    assert "Sem dado de temperatura" in cerrado.geada.texto


def test_a_regiao_traz_a_fase_e_o_que_o_mercado_olha_no_mes(pacote):
    cerrado = _regiao(montar_vista(pacote, "arabica", 11), "cerrado-mineiro")
    assert cerrado.fase.startswith("Em novembro, a safra em curso está na florada")
    assert cerrado.o_que_o_mercado_olha[0].titulo == "O que o mercado olha na florada"


@pytest.mark.parametrize("mes", range(1, 13))
def test_toda_fase_de_todo_mes_vira_frase(mes):
    for regiao in REGIOES:
        assert texto_da_fase(calendario.fase(mes, regiao)).startswith("Em ")


def test_tipo_desconhecido_e_recusado(pacote):
    with pytest.raises(ValueError, match="tipo"):
        montar_vista(pacote, "total", 11)


def test_a_vista_nao_tem_palavra_vedada_nem_previsao(pacote):
    for tipo in ("arabica", "conilon"):
        vista = vista_em_dicionario(montar_vista(pacote, tipo, 6))
        texto = json.dumps(
            {k: v for k, v in vista.items() if k != "malha"}, ensure_ascii=False
        )
        assert not [p for p in VEDADAS if p in texto.lower()]
        assert "não previsão" in vista["aviso"]


def test_a_vista_vira_json_com_datas_em_texto(pacote):
    vista = vista_em_dicionario(montar_vista(pacote, "arabica", 11))
    json.dumps(vista)  # não falha
    assert vista["gerado_em"] == "2026-11-05"
    assert vista["regioes"][0]["chuva"]["inicio"] == "2026-06-01"
