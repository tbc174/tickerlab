"""Ancoragem da base (ADR 0078): a raiz de Merkle de uma versão da base é determinística,
qualquer mudança num manifesto muda a raiz, a prova de inclusão de uma tabela confere sem as outras
tabelas, e nenhuma folha é de registro individual de pessoa (LGPD)."""

import hashlib
import json

import pandas as pd
import pytest

from base import ancoragem as an
from base.parquet import gravar_tabela
from src import versao_do_codigo as vc

ORIGENS = [{"url": "https://dados.cvm.gov.br/x.zip", "sha256": "ab" * 32}]


def _sha(dados: bytes) -> bytes:
    return hashlib.sha256(dados).digest()


def test_folha_e_no_tem_prefixos_diferentes():
    # RFC 6962: 0x00 na folha e 0x01 no nó; assim uma folha nunca se passa por um nó.
    assert an.hash_folha(b"x") == _sha(b"\x00x")
    assert an.hash_no(b"a" * 32, b"b" * 32) == _sha(b"\x01" + b"a" * 32 + b"b" * 32)


def test_raiz_segue_a_divisao_da_rfc_6962():
    h = [an.hash_folha(bytes([i])) for i in range(3)]
    assert an.raiz_de_merkle(h[:1]) == h[0]
    assert an.raiz_de_merkle(h[:2]) == an.hash_no(h[0], h[1])
    # 3 folhas: a maior potência de 2 menor que 3 é 2, então ((0, 1), 2), sem duplicar a última.
    assert an.raiz_de_merkle(h) == an.hash_no(an.hash_no(h[0], h[1]), h[2])


def test_raiz_de_nada_e_erro():
    with pytest.raises(ValueError):
        an.raiz_de_merkle([])


@pytest.mark.parametrize("total", range(1, 10))
def test_prova_de_inclusao_confere_para_toda_folha(total):
    folhas = [an.hash_folha(f"t{i}".encode()) for i in range(total)]
    raiz = an.raiz_de_merkle(folhas)
    for i, folha in enumerate(folhas):
        caminho = an.prova_de_inclusao(folhas, i)
        assert an.conferir_prova(folha, caminho, raiz)
        assert not an.conferir_prova(an.hash_folha(b"outra"), caminho, raiz)


def test_prova_mexida_nao_confere():
    folhas = [an.hash_folha(f"t{i}".encode()) for i in range(5)]
    raiz = an.raiz_de_merkle(folhas)
    caminho = an.prova_de_inclusao(folhas, 2)
    caminho[0] = {
        **caminho[0],
        "lado": "direita" if caminho[0]["lado"] == "esquerda" else "esquerda",
    }
    assert not an.conferir_prova(folhas[2], caminho, raiz)


def _manifesto(linhas=10, sha="cd" * 32):
    return {
        "linhas": linhas,
        "sha256_da_tabela": sha,
        "ordem": ["cnpj"],
        "origens": ORIGENS,
    }


def test_folha_do_manifesto_nao_depende_da_ordem_das_chaves():
    m = _manifesto()
    invertido = dict(reversed(list(m.items())))
    assert an.folha_do_manifesto("fca/emissores", m) == an.folha_do_manifesto(
        "fca/emissores", invertido
    )
    assert an.folha_do_manifesto("fca/emissores", m) != an.folha_do_manifesto(
        "fca/tickers", m
    )


def test_so_entra_manifesto_de_tabela_inteira():
    with pytest.raises(ValueError, match="tabela inteira"):
        an.folha_do_manifesto("fca/emissores", {"cpf": "123"})


def test_tabela_pequena_de_pessoas_nao_entra():
    # Uma tabela de pessoas com poucas linhas é quase um registro individual: fica fora (LGPD).
    with pytest.raises(ValueError, match="pessoas"):
        an.folha_do_manifesto(
            "pessoas/nivel1", _manifesto(linhas=an.LINHAS_MINIMAS_PESSOAS - 1)
        )
    an.folha_do_manifesto(
        "pessoas/nivel1", _manifesto(linhas=an.LINHAS_MINIMAS_PESSOAS)
    )


def test_folha_de_arquivo_usa_so_o_hash_do_conteudo():
    folha = an.folha_de_arquivo("pre-registros/m3-v1.md", b"criterio")
    assert hashlib.sha256(b"criterio").hexdigest().encode() in folha
    assert b'criterio"' not in folha


def _gravar(pasta, nome, valores):
    tabela = pd.DataFrame({"cnpj": [str(v) for v in valores], "valor": valores})
    gravar_tabela(tabela, pasta / nome, ORIGENS, ["cnpj"])


@pytest.fixture
def base(tmp_path, monkeypatch):
    monkeypatch.setenv(vc.VARIAVEL, "587cb6c4d2e1f0a9b8c7d6e5f4a3b2c1d0e9f8a7")
    _gravar(tmp_path, "fca/emissores", [1, 2])
    _gravar(tmp_path, "fca/tickers", [3])
    _gravar(tmp_path, "cda/fundos", [4, 5, 6])
    # versão antiga guardada ao lado: não faz parte da versão atual
    (tmp_path / "fca" / "emissores.parquet").replace(
        tmp_path / "fca" / "emissores.v1.parquet"
    )
    (tmp_path / "fca" / "emissores.json").replace(
        tmp_path / "fca" / "emissores.v1.json"
    )
    _gravar(tmp_path, "fca/emissores", [1, 2, 9])
    return tmp_path


def test_manifestos_atuais_pula_versoes_antigas_e_json_soltos(base):
    (base / "solto.json").write_text("{}", encoding="utf-8")
    assert list(an.manifestos_atuais(base)) == [
        "cda/fundos",
        "fca/emissores",
        "fca/tickers",
    ]


def test_ancora_e_deterministica_e_confere(base):
    ancora = an.montar_ancora(an.folhas_da_base(base), rotulo="2026-10-15")
    assert ancora["formato"] == an.FORMATO
    assert [f["nome"] for f in ancora["folhas"]] == [
        "cda/fundos",
        "fca/emissores",
        "fca/tickers",
    ]
    de_novo = an.montar_ancora(an.folhas_da_base(base), rotulo="2026-10-15")
    assert an.texto_da_ancora(ancora) == an.texto_da_ancora(de_novo)
    assert an.diferencas(ancora, an.folhas_da_base(base)) == []


def test_ancora_acusa_tabela_mudada_nova_e_sumida(base):
    ancora = an.montar_ancora(an.folhas_da_base(base), rotulo="v1")
    _gravar(base, "fca/tickers", [3, 4])
    _gravar(base, "novas/tabela", [7])
    (base / "cda" / "fundos.json").unlink()
    assert an.diferencas(ancora, an.folhas_da_base(base)) == [
        "cda/fundos: sumiu",
        "fca/tickers: mudou",
        "novas/tabela: não estava na âncora",
    ]


def test_ancora_nao_leva_dado_nenhum_das_tabelas(base):
    texto = an.texto_da_ancora(an.montar_ancora(an.folhas_da_base(base), rotulo="v1"))
    ancora = json.loads(texto)
    assert set(ancora) == {"formato", "rotulo", "algoritmo", "folhas", "raiz"}
    assert "dados.cvm.gov.br" not in texto.decode()  # só hashes, nem as origens


def test_prova_de_uma_tabela_confere_so_com_o_manifesto_dela(base):
    ancora = an.montar_ancora(an.folhas_da_base(base), rotulo="v1")
    prova = an.prova_da_tabela(ancora, "fca/tickers")
    manifesto = json.loads((base / "fca" / "tickers.json").read_text(encoding="utf-8"))
    assert an.conferir_prova_da_tabela(prova, manifesto)
    assert set(prova) == {"formato", "rotulo", "nome", "caminho", "raiz"}
    assert not an.conferir_prova_da_tabela(prova, {**manifesto, "linhas": 2})


def test_nao_ha_prova_de_inclusao_para_tabela_de_pessoas():
    folhas = {
        "fca/emissores": an.hash_folha(b"a"),
        "pessoas/nivel1": an.hash_folha(b"b"),
    }
    ancora = an.montar_ancora(folhas, rotulo="v1")
    with pytest.raises(ValueError, match="pessoas"):
        an.prova_da_tabela(ancora, "pessoas/nivel1")


def test_parquets_sem_manifesto_ficam_de_fora_e_sao_listados(base):
    pd.DataFrame({"a": [1]}).to_parquet(base / "cripto.parquet", index=False)
    (base / "eventos").mkdir()
    pd.DataFrame({"a": [1]}).to_parquet(base / "eventos" / "2024.parquet", index=False)
    pd.DataFrame({"a": [1]}).to_parquet(base / "eventos" / "2023.v1.parquet", index=False)
    assert an.parquets_sem_manifesto(base) == ["cripto.parquet", "eventos/2024.parquet"]
    assert "eventos/2024" not in an.manifestos_atuais(base)
