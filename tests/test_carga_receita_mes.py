"""Carga mensal do CNPJ (ADR 0106, PR 5): um mês por vez, em partes, retomando do último gravado."""

import json

import pandas as pd
import pytest

from base.receita_retrato import ParteDoQsa
from scripts import carga_receita_mes as rc

CHAVE_DE_PESSOAS = b"k" * 32


def _estabelecimentos(*linhas):
    return pd.DataFrame(linhas, columns=["cnpj", "situacao"])


def _simples(*linhas):
    return pd.DataFrame(linhas, columns=["cnpj_basico", "optante_mei"])


def _qsa(*socios):
    """Cada sócio: (cnpj_basico, tipo, raiz_pj, qualificacao, nome ou None)."""
    tabela = pd.DataFrame(
        [
            {
                "cnpj_basico": b,
                "tipo_socio": t,
                "raiz_socio_pj": r or "",
                "qualificacao": q,
                "data_entrada": pd.NaT,
                "pais": "",
            }
            for b, t, r, q, _ in socios
        ]
    )
    pessoas = pd.DataFrame(
        [
            {
                "cnpj_basico": b,
                "tipo_socio": t,
                "nome_socio": n,
                "qualificacao": q,
                "data_entrada": pd.NaT,
                "cpf_mascarado": "***982247**",
            }
            for b, t, _, q, n in socios
            if t != "1"
        ]
    )
    return [ParteDoQsa(tabela, pessoas)]


def _mes(pasta, restrita, mes, estab, simples, qsa):
    return rc.processar_mes(
        mes,
        pasta,
        restrita,
        estabelecimentos=[estab],
        simples=[simples],
        qsa=qsa,
        chave_de_pessoas=CHAVE_DE_PESSOAS,
        arquivos={"Simples.zip": "ab" * 32},
    )


@pytest.fixture
def pastas(tmp_path):
    return tmp_path / "cnpj", tmp_path / "restrito"


def _ler(pasta, tabela):
    arquivos = sorted((pasta / "vigente" / tabela).glob("*.parquet"))
    return pd.concat([pd.read_parquet(a) for a in arquivos], ignore_index=True)


def test_primeiro_mes_vira_retrato_inicial_sem_mudancas(pastas):
    pasta, restrita = pastas
    _mes(
        pasta,
        restrita,
        "2026-09",
        _estabelecimentos(("11111111000191", "ativa")),
        _simples(("11111111", False)),
        _qsa(("11111111", "1", "22222222", "22", None)),
    )
    assert len(_ler(pasta, "estabelecimentos")) == 1
    assert not list((pasta / "mudancas").rglob("*.parquet"))
    assert rc.ultimo_mes(pasta) == "2026-09"


def test_segundo_mes_grava_so_o_que_mudou(pastas):
    pasta, restrita = pastas
    qsa = _qsa(("11111111", "2", None, "49", "MARIA SILVA"))
    _mes(
        pasta,
        restrita,
        "2026-09",
        _estabelecimentos(("11111111000191", "ativa"), ("33333333000100", "ativa")),
        _simples(("11111111", False)),
        qsa,
    )
    _mes(
        pasta,
        restrita,
        "2026-10",
        _estabelecimentos(("11111111000191", "baixada"), ("33333333000100", "ativa")),
        _simples(("11111111", False)),
        qsa,
    )
    mudancas = pd.read_parquet(
        pasta / "mudancas" / "estabelecimentos" / "2026-10.parquet"
    )
    assert len(mudancas) == 1 and mudancas.iloc[0]["situacao_depois"] == "baixada"
    assert (
        _ler(pasta, "estabelecimentos")
        .set_index("cnpj")
        .loc["11111111000191", "situacao"]
        == "baixada"
    )
    assert (
        not (pasta / "mudancas" / "qsa" / "2026-10.parquet").exists()
        or pd.read_parquet(pasta / "mudancas" / "qsa" / "2026-10.parquet").empty
    )


def test_nome_so_no_restrito_e_historico_so_com_id(pastas):
    pasta, restrita = pastas
    _mes(
        pasta,
        restrita,
        "2026-09",
        _estabelecimentos(("11111111000191", "ativa")),
        _simples(("11111111", False)),
        _qsa(("11111111", "2", None, "49", "MARIA SILVA")),
    )
    pessoas = pd.concat(
        pd.read_parquet(a) for a in (restrita / "pessoas").rglob("*.parquet")
    )
    assert list(pessoas["nome"]) == ["MARIA SILVA"]
    for arquivo in pasta.rglob("*.parquet"):
        colunas = set(pd.read_parquet(arquivo).columns)
        assert not colunas & {"nome", "nome_socio", "cpf_mascarado"}, arquivo


def test_pessoa_que_saiu_sai_do_vigente_e_fica_so_o_id_no_historico(pastas):
    pasta, restrita = pastas
    kw = {
        "estab": _estabelecimentos(("11111111000191", "ativa")),
        "simples": _simples(("11111111", False)),
    }
    _mes(
        pasta,
        restrita,
        "2026-09",
        qsa=_qsa(("11111111", "2", None, "49", "MARIA SILVA")),
        **kw,
    )
    _mes(
        pasta,
        restrita,
        "2026-10",
        qsa=_qsa(("11111111", "1", "22222222", "22", None)),
        **kw,
    )
    pessoas = [pd.read_parquet(a) for a in (restrita / "pessoas").rglob("*.parquet")]
    assert all(p.empty for p in pessoas)
    mudancas = pd.read_parquet(pasta / "mudancas" / "qsa" / "2026-10.parquet")
    saiu = mudancas[mudancas["tipo"] == "saiu"]
    assert len(saiu) == 1 and saiu.iloc[0]["id_pessoa"]


def test_carga_retoma_do_ultimo_mes(pastas):
    pasta, restrita = pastas
    assert rc.pendentes(["2026-08", "2026-09", "2026-10"], pasta) == [
        "2026-08",
        "2026-09",
        "2026-10",
    ]
    _mes(
        pasta,
        restrita,
        "2026-08",
        _estabelecimentos(("11111111000191", "ativa")),
        _simples(("11111111", False)),
        _qsa(),
    )
    assert rc.pendentes(["2026-08", "2026-09", "2026-10"], pasta) == [
        "2026-09",
        "2026-10",
    ]


def test_mes_fora_de_ordem_recusa(pastas):
    pasta, restrita = pastas
    kw = {
        "estab": _estabelecimentos(("11111111000191", "ativa")),
        "simples": _simples(("11111111", False)),
        "qsa": _qsa(),
    }
    _mes(pasta, restrita, "2026-09", **kw)
    with pytest.raises(rc.MesForaDeOrdem):
        _mes(pasta, restrita, "2026-11", **kw)
    with pytest.raises(rc.MesForaDeOrdem):
        _mes(pasta, restrita, "2026-08", **kw)


def test_manifesto_guarda_o_sha256_dos_zips(pastas):
    pasta, restrita = pastas
    _mes(
        pasta,
        restrita,
        "2026-09",
        _estabelecimentos(("11111111000191", "ativa")),
        _simples(("11111111", False)),
        _qsa(),
    )
    manifesto = json.loads((pasta / "manifesto.json").read_text(encoding="utf-8"))
    assert manifesto["meses"]["2026-09"]["arquivos"] == {"Simples.zip": "ab" * 32}


def test_carga_recusa_com_pouco_disco(tmp_path):
    with pytest.raises(rc.PoucoDisco):
        rc.exigir_disco(tmp_path, livre=lambda pasta: 29 * 1024**3)
    rc.exigir_disco(tmp_path, livre=lambda pasta: 31 * 1024**3)


def test_cpf_inteiro_quebra_a_carga(pastas):
    pasta, restrita = pastas
    socios = _qsa(("11111111", "2", None, "49", "MARIA SILVA"))
    socios[0].pessoas_brutas["cpf_mascarado"] = "12345678901"
    with pytest.raises(ValueError, match="CPF"):
        _mes(
            pasta,
            restrita,
            "2026-09",
            _estabelecimentos(("11111111000191", "ativa")),
            _simples(("11111111", False)),
            socios,
        )
    assert rc.ultimo_mes(pasta) is None


def test_vigente_e_mudancas_tem_manifesto_e_entram_na_raiz_de_merkle(pastas):
    from base import ancoragem

    pasta, restrita = pastas
    for mes, situacao in (("2026-09", "ativa"), ("2026-10", "baixada")):
        _mes(
            pasta,
            restrita,
            mes,
            _estabelecimentos(("11111111000191", situacao)),
            _simples(("11111111", False)),
            _qsa(("11111111", "1", "22222222", "22", None)),
        )
    assert not ancoragem.parquets_sem_manifesto(pasta)
    folhas = ancoragem.folhas_da_base(pasta)
    assert "vigente/estabelecimentos/11" in folhas
    assert "mudancas/estabelecimentos/2026-10" in folhas
    manifesto = ancoragem.manifestos_atuais(pasta)["vigente/estabelecimentos/11"]
    assert manifesto["origens"][0]["url"].endswith("/2026-10/Simples.zip")
    assert manifesto["licenca"]["fontes"] == {"rfb-cnpj": "vendavel"}


def test_mes_grande_grava_as_mudancas_em_um_arquivo_por_prefixo(pastas, monkeypatch):
    from base import ancoragem

    monkeypatch.setattr(rc, "LINHAS_NUM_ARQUIVO_SO", 0)
    pasta, restrita = pastas
    for mes, situacao in (("2026-09", "ativa"), ("2026-10", "baixada")):
        _mes(
            pasta,
            restrita,
            mes,
            _estabelecimentos(("11111111000191", situacao)),
            _simples(("11111111", False)),
            _qsa(("11111111", "1", "22222222", "22", None)),
        )
    assert not (pasta / "mudancas" / "estabelecimentos" / "2026-10.parquet").exists()
    assert (
        pasta / "mudancas" / "estabelecimentos" / "2026-10" / "11.parquet"
    ).is_file()
    assert not ancoragem.parquets_sem_manifesto(pasta)
    assert "mudancas/estabelecimentos/2026-10/11" in ancoragem.folhas_da_base(pasta)
    manifesto = rc._manifesto(pasta)["meses"]["2026-10"]["mudancas"]
    assert manifesto["estabelecimentos"] == 1
