"""O radar não confunde ausência, região incompleta nem média com valorização."""

import copy
import json

import pytest

from src import radar_imobiliario as radar


@pytest.fixture
def dados_radar():
    return {
        "versao": 1,
        "apurado_em": "2026-10-26",
        "mensais": [
            {
                "cidade": "SP",
                "recorte": "todos",
                "mes": "2025-08",
                "quantidade": 10,
                "valor_medio": 100.0,
            },
            {
                "cidade": "SP",
                "recorte": "todos",
                "mes": "2026-08",
                "quantidade": 15,
                "valor_medio": 200.0,
            },
            {
                "cidade": "SP",
                "recorte": "residencial",
                "mes": "2026-08",
                "quantidade": 5,
                "valor_medio": 300.0,
            },
            {
                "cidade": "RIO",
                "recorte": "todos",
                "mes": "2026-08",
                "quantidade": 20,
                "valor_medio": 400.0,
            },
        ],
        "regioes": [
            {
                "cidade": "SP",
                "recorte": "todos",
                "mes": "2026-08",
                "tipo": "distrito",
                "nome": "CENTRO",
                "quantidade": 12,
                "valor_medio": 100.0,
            },
            {
                "cidade": "RIO",
                "recorte": "todos",
                "mes": "2026-08",
                "tipo": "bairro",
                "nome": "BAIRRO EXEMPLO",
                "quantidade": 20,
                "valor_medio": 400.0,
            },
        ],
    }


def test_filtra_cidade_e_recorte_sem_inventar_meses(dados_radar):
    pacote = radar.validar_pacote(dados_radar)
    assert pacote is not None
    vista = radar.montar_vista(pacote, "SP", "todos")
    assert [p.mes for p in vista.serie] == ["2025-08", "2026-08"]
    assert [p.variacao_anual_pct for p in vista.serie] == [None, 50.0]
    assert vista.serie[1].localizadas == 12
    assert vista.tipo_regiao == "distrito"
    assert len(vista.regioes) == 1


@pytest.mark.parametrize(
    "erro",
    ["duplicado", "regiao_excede", "identificador", "nan", "mes", "distrito_no_rio"],
)
def test_rejeita_pacote_inconsistente_ou_com_dado_por_imovel(dados_radar, erro):
    dados = copy.deepcopy(dados_radar)
    if erro == "duplicado":
        dados["mensais"].append(dados["mensais"][0])
    elif erro == "regiao_excede":
        dados["regioes"][0]["quantidade"] = 16
    elif erro == "identificador":
        dados["regioes"][0]["sql"] = "identificador-privado"
    elif erro == "nan":
        dados["mensais"][0]["valor_medio"] = float("nan")
    elif erro == "mes":
        dados["mensais"][0]["mes"] = "2026-13"
    else:
        dados["regioes"][1]["tipo"] = "distrito"
    with pytest.raises(ValueError):
        radar.validar_pacote(dados)


def test_ausencia_ou_json_invalido_nao_vira_numero(tmp_path, monkeypatch):
    arquivo = tmp_path / "radar.json"
    monkeypatch.setenv("TICKERLAB_RADAR_IMOBILIARIO", str(arquivo))
    assert radar.ler_pacote() is None
    arquivo.write_text('{"versao": 99}', encoding="utf-8")
    assert radar.ler_pacote() is None


def test_le_arquivo_validado_do_ambiente(dados_radar, tmp_path, monkeypatch):
    arquivo = tmp_path / "radar.json"
    arquivo.write_text(json.dumps(dados_radar), encoding="utf-8")
    monkeypatch.setenv("TICKERLAB_RADAR_IMOBILIARIO", str(arquivo))
    assert radar.ler_pacote() is not None


def test_competencia_futura_e_recusada(dados_radar):
    dados_radar["apurado_em"] = "2025-12-31"
    with pytest.raises(ValueError, match="posterior"):
        radar.validar_pacote(dados_radar)


def test_limita_tamanho_da_leitura(tmp_path, monkeypatch):
    arquivo = tmp_path / "radar.json"
    arquivo.write_bytes(b"x" * 21)
    monkeypatch.setattr(radar, "MAX_BYTES", 20)
    monkeypatch.setenv(radar.VARIAVEL_DO_ARQUIVO, str(arquivo))
    assert radar.ler_pacote() is None
