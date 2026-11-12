"""Registros da Anvisa por empresa (linha 860): `base/anvisa_porte.py` e `scripts/montar_anvisa_por_empresa.py`.

Contam por raiz de CNPJ e por tipo, só pessoa jurídica, sem olhar o futuro. Dados de mentira (raízes e situações
inventadas); nenhum dado de pessoa real.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from base import anvisa_porte as porte
from base import porta
from base.dicionario import TABELAS
from base.parquet import GRAVADO, IGUAL
from scripts import montar_anvisa_por_empresa as script

AGORA = datetime(2026, 11, 11, 12, tzinfo=UTC)
EMPRESA, OUTRA, MEI, SEM_MARCA, SO_PESSOA = (
    "11111111",
    "22222222",
    "33333333",
    "44444444",
    "55555555",
)
PRIMEIRO, SEGUNDO = "2026-10-29", "2026-11-10"
CONTAGENS = porte.colunas_de_contagem()


def _linha(
    raiz: str,
    cadastro: str,
    registro: str,
    situacao: str | None,
    *,
    retrato: str = PRIMEIRO,
    visto_em: str | None = None,
    consta: bool = True,
    pessoa: bool | None = False,
) -> dict[str, object]:
    return {
        "cadastro": cadastro,
        "id_na_fonte": registro,
        "cnpj_basico": raiz,
        "situacao": situacao,
        "consta": consta,
        "trata_como_pessoa": pessoa,
        "visto_em": pd.Timestamp(visto_em or retrato),
        "disponivel_em": pd.Timestamp(retrato),
    }


def _registros(*linhas: dict[str, object]) -> pd.DataFrame:
    return pd.DataFrame(list(linhas), columns=list(porte.COLUNAS_DE_ENTRADA))


def _da_empresa(tabela: pd.DataFrame, raiz: str, retrato: str = PRIMEIRO) -> pd.Series:
    achada = tabela[
        (tabela["cnpj_basico"] == raiz) & (tabela["disponivel_em"] == retrato)
    ]
    assert len(achada) == 1, (raiz, retrato, tabela)
    return achada.iloc[0]


def test_conta_o_total_e_os_ativos_de_cada_tipo():
    tabela = porte.contar(
        _registros(
            _linha(EMPRESA, "cosmeticos", "c1", "S"),
            _linha(EMPRESA, "cosmeticos", "c2", "S"),
            _linha(EMPRESA, "cosmeticos", "c3", "N"),
            _linha(EMPRESA, "saneantes", "s1", "S"),
            _linha(EMPRESA, "alimentos", "a1", "Ativo"),
            _linha(EMPRESA, "alimentos", "a2", "Inativo"),
            _linha(EMPRESA, "produtos_saude", "p1", "Válido"),
            _linha(EMPRESA, "produtos_saude", "p2", "Inválido"),
            _linha(EMPRESA, "medicamentos", "m1", "Ativo"),
            _linha(EMPRESA, "afe", "f1", "SIM"),
            _linha(EMPRESA, "cbpf", "b1", "Válido"),
            _linha(EMPRESA, "cbpf_medicamento", "b2", "Vencido"),
        )
    )
    linha = _da_empresa(tabela, EMPRESA)
    assert (linha["cosmeticos_total"], linha["cosmeticos_ativos"]) == (3, 2)
    assert (linha["saneantes_total"], linha["saneantes_ativos"]) == (1, 1)
    assert (linha["alimentos_total"], linha["alimentos_ativos"]) == (2, 1)
    assert (linha["produtos_saude_total"], linha["produtos_saude_ativos"]) == (2, 1)
    assert (linha["medicamentos_total"], linha["medicamentos_ativos"]) == (1, 1)
    # a autorização e o certificado contam à parte; o CBPF de medicamento é um certificado
    assert (linha["afe_total"], linha["afe_ativos"]) == (1, 1)
    assert (linha["cbpf_total"], linha["cbpf_ativos"]) == (2, 1)
    # `produtos` soma só os cinco tipos de produto
    assert (linha["produtos_total"], linha["produtos_ativos"]) == (9, 6)


def test_tipo_sem_registro_conta_zero_e_as_colunas_sao_inteiras():
    tabela = porte.contar(_registros(_linha(EMPRESA, "cosmeticos", "c1", "S")))
    linha = _da_empresa(tabela, EMPRESA)
    assert linha["saneantes_total"] == 0 and linha["medicamentos_ativos"] == 0
    assert list(tabela.columns[:3]) == [
        "cnpj_basico",
        "disponivel_em",
        "trata_como_pessoa",
    ]
    assert list(tabela.columns[3:]) == CONTAGENS
    assert all(str(tabela[c].dtype) == "int64" for c in CONTAGENS)


@pytest.mark.parametrize(
    ("tipo", "situacao", "ativa"),
    [
        ("cosmeticos", "S", True),
        ("cosmeticos", "s", True),
        ("cosmeticos", "N", False),
        ("saneantes", "S", True),
        ("alimentos", "Ativo", True),
        ("alimentos", " ATIVO ", True),
        ("alimentos", "Inativo", False),
        ("medicamentos", "Ativo / Inativo", True),
        ("medicamentos", "Inativo / Inativo", False),
        ("produtos_saude", "Válido", True),
        ("produtos_saude", "Valido", True),
        ("produtos_saude", "Inválido", False),
        ("produtos_saude", "Em validação", False),
        ("afe", "SIM", True),
        ("afe", "NÃO", False),
        ("cbpf", "Válido", True),
        ("cbpf", "Vencido", False),
        ("cosmeticos", None, False),
        ("cosmeticos", "", False),
        ("cosmeticos", "Situação que a fonte inventou", False),
        ("medicamentos", "S", False),  # o "S" é dos cosméticos: em medicamento não vale
    ],
)
def test_ativo_muda_de_nome_por_tipo(tipo, situacao, ativa):
    assert porte.e_ativa(tipo, situacao) is ativa


def test_nenhuma_raiz_de_pessoa_entra_nem_no_total_nem_nos_ativos():
    """A prova de zero pessoa: com a marca verdadeira, vazia ou em qualquer cadastro, a raiz inteira sai."""
    tabela = porte.contar(
        _registros(
            _linha(EMPRESA, "cosmeticos", "c1", "S"),
            _linha(MEI, "cosmeticos", "c2", "S", pessoa=True),
            _linha(SEM_MARCA, "cosmeticos", "c3", "S", pessoa=None),
            # uma raiz com uma linha de empresa e outra de pessoa sai inteira (na dúvida é pessoa)
            _linha(OUTRA, "cosmeticos", "c4", "S"),
            _linha(OUTRA, "saneantes", "s1", "S", pessoa=True),
            _linha(SO_PESSOA, "alimentos", "a1", "Ativo", pessoa=True),
        )
    )
    assert set(tabela["cnpj_basico"]) == {EMPRESA}
    assert not tabela["trata_como_pessoa"].any()
    # só o cosmético da EMPRESA foi contado: nada das outras raízes, em nenhum tipo
    assert tabela[["cosmeticos_total", "cosmeticos_ativos"]].iloc[0].tolist() == [1, 1]
    assert tabela["produtos_total"].sum() == 1 and tabela["alimentos_total"].sum() == 0
    assert tabela["saneantes_total"].sum() == 0


def test_pessoa_vista_depois_tira_a_raiz_dos_retratos_antigos_tambem():
    """A raiz que um dia foi marcada como pessoa não aparece em retrato nenhum (zero pessoa, ADR 0075)."""
    tabela = porte.contar(
        _registros(
            _linha(EMPRESA, "cosmeticos", "c1", "S", retrato=PRIMEIRO),
            _linha(MEI, "cosmeticos", "c2", "S", retrato=PRIMEIRO),
            _linha(MEI, "cosmeticos", "c2", "S", retrato=SEGUNDO, pessoa=True),
        )
    )
    assert MEI not in set(tabela["cnpj_basico"])
    assert set(tabela[tabela["disponivel_em"] == PRIMEIRO]["cnpj_basico"]) == {EMPRESA}


def test_o_que_saiu_do_arquivo_nao_conta():
    tabela = porte.contar(
        _registros(
            _linha(EMPRESA, "cosmeticos", "c1", "S"),
            _linha(EMPRESA, "cosmeticos", "c2", "S"),
            _linha(EMPRESA, "cosmeticos", "c2", "S", retrato=SEGUNDO, consta=False),
        )
    )
    assert _da_empresa(tabela, EMPRESA, PRIMEIRO)["cosmeticos_total"] == 2
    assert _da_empresa(tabela, EMPRESA, SEGUNDO)["cosmeticos_total"] == 1


def test_raiz_que_so_tem_registro_que_saiu_some_do_retrato():
    tabela = porte.contar(
        _registros(
            _linha(EMPRESA, "cosmeticos", "c1", "S"),
            _linha(OUTRA, "cosmeticos", "c2", "S"),
            _linha(OUTRA, "cosmeticos", "c2", "S", retrato=SEGUNDO, consta=False),
        )
    )
    assert OUTRA in set(tabela[tabela["disponivel_em"] == PRIMEIRO]["cnpj_basico"])
    assert OUTRA not in set(tabela[tabela["disponivel_em"] == SEGUNDO]["cnpj_basico"])


def test_cada_registro_conta_uma_vez_pela_versao_mais_nova():
    """O registro que mudou de situação tem duas linhas na fonte: vale a mais nova vista até o retrato."""
    tabela = porte.contar(
        _registros(
            _linha(EMPRESA, "cosmeticos", "c1", "S", retrato=PRIMEIRO),
            _linha(EMPRESA, "cosmeticos", "c1", "N", retrato=SEGUNDO, visto_em=SEGUNDO),
        )
    )
    primeiro = _da_empresa(tabela, EMPRESA, PRIMEIRO)
    segundo = _da_empresa(tabela, EMPRESA, SEGUNDO)
    assert (primeiro["cosmeticos_total"], primeiro["cosmeticos_ativos"]) == (1, 1)
    assert (segundo["cosmeticos_total"], segundo["cosmeticos_ativos"]) == (1, 0)


def test_sem_olhar_o_futuro_cortar_o_futuro_nao_muda_o_passado():
    completo = _registros(
        _linha(EMPRESA, "cosmeticos", "c1", "S", retrato=PRIMEIRO),
        _linha(EMPRESA, "cosmeticos", "c2", "S", retrato=SEGUNDO),
        _linha(OUTRA, "saneantes", "s1", "S", retrato=SEGUNDO),
    )
    so_o_passado = completo[completo["disponivel_em"] <= pd.Timestamp(PRIMEIRO)]
    do_passado = porte.contar(so_o_passado)
    do_completo = porte.contar(completo)
    no_primeiro = do_completo[do_completo["disponivel_em"] == PRIMEIRO]
    pd.testing.assert_frame_equal(
        do_passado.reset_index(drop=True), no_primeiro.reset_index(drop=True)
    )
    assert _da_empresa(do_completo, EMPRESA, PRIMEIRO)["cosmeticos_total"] == 1
    assert _da_empresa(do_completo, EMPRESA, SEGUNDO)["cosmeticos_total"] == 2


def test_cadastro_que_a_tabela_nao_conhece_e_raiz_torta_sao_ignorados():
    tabela = porte.contar(
        _registros(
            _linha(EMPRESA, "cosmeticos", "c1", "S"),
            _linha(EMPRESA, "outro_cadastro", "x1", "S"),
            _linha("123", "cosmeticos", "c2", "S"),  # raiz que não tem 8 caracteres
        )
    )
    assert list(tabela["cnpj_basico"]) == [EMPRESA]
    assert tabela["produtos_total"].tolist() == [1]


def test_sem_nada_para_contar_devolve_a_tabela_vazia_com_as_colunas_certas():
    tabela = porte.contar(_registros(_linha(MEI, "cosmeticos", "c1", "S", pessoa=True)))
    assert tabela.empty
    assert list(tabela.columns) == [
        "cnpj_basico",
        "disponivel_em",
        "trata_como_pessoa",
        *CONTAGENS,
    ]


def test_falta_de_coluna_na_entrada_para_com_mensagem_clara():
    with pytest.raises(ValueError, match="colunas ausentes"):
        porte.contar(_registros().drop(columns=["situacao"]))


def test_o_resumo_diz_quantas_linhas_ficaram_sem_situacao_classificada():
    registros = _registros(
        _linha(EMPRESA, "produtos_saude", "p1", "Válido"),
        _linha(EMPRESA, "produtos_saude", "p2", None),
        _linha(EMPRESA, "produtos_saude", "p3", ""),
        _linha(EMPRESA, "cosmeticos", "c1", "Situação nova"),
        _linha(
            EMPRESA, "cosmeticos", "c2", "S", consta=False
        ),  # saiu: não entra na conta
        _linha(EMPRESA, "medicamentos", "m1", "Ativo / Inativo"),
    )
    assert porte.situacoes_sem_classificar(registros) == {
        "produtos_saude": 2,
        "cosmeticos": 1,
    }


def test_o_carimbo_de_linhagem_traz_a_montagem_e_a_versao_do_codigo():
    tabela = porte.com_carimbo(
        porte.contar(_registros(_linha(EMPRESA, "cosmeticos", "c1", "S"))),
        AGORA,
        "abc123",
    )
    assert tabela["versao_do_codigo"].tolist() == ["abc123"]
    assert pd.Timestamp(tabela["montado_em"].iloc[0]) == pd.Timestamp(AGORA)


def test_o_dicionario_descreve_exatamente_as_colunas_que_a_montagem_grava():
    tabela = porte.com_carimbo(
        porte.contar(_registros(_linha(EMPRESA, "cosmeticos", "c1", "S"))), AGORA, "x"
    )
    contrato = TABELAS[porte.TABELA]
    assert list(contrato.colunas) == list(tabela.columns)
    assert contrato.linhas_de_pessoa == "trata_como_pessoa"
    assert contrato.datas["publico_em"] == porte.RETRATO
    assert contrato.granularidade_do_publico_em == "mes"


# --- o script: lê pela porta, grava a tabela e não regrava sem retrato novo --------------------------------------


def _colunas_do_cadastro() -> list[str]:
    return list(TABELAS[porte.CADASTRO_DA_TABELA].colunas)


def _acervo(tmp_path: Path, registros: pd.DataFrame) -> Path:
    """Uma pasta `base` com `anvisa_registros` (um Parquet por cadastro) e o manifesto de cada um."""
    base = tmp_path / "base"
    pasta = base / porte.CADASTRO_DA_TABELA
    pasta.mkdir(parents=True)
    for cadastro, parte in registros.groupby("cadastro"):
        completa = parte.assign(
            **{c: "" for c in _colunas_do_cadastro() if c not in parte.columns}
        )
        arquivo = pasta / f"{cadastro}.parquet"
        completa.to_parquet(arquivo, index=False)
        (pasta / f"{cadastro}.json").write_text(
            json.dumps({"sha256_da_tabela": "a" * 64}), encoding="utf-8"
        )
    return base


def _registros_do_acervo() -> pd.DataFrame:
    return _registros(
        _linha(EMPRESA, "cosmeticos", "c1", "S"),
        _linha(EMPRESA, "cosmeticos", "c2", "N"),
        _linha(MEI, "cosmeticos", "c3", "S", pessoa=True),
        _linha(OUTRA, "alimentos", "a1", "Ativo", retrato=SEGUNDO),
        _linha(EMPRESA, "medicamentos", "m1", "Ativo / Inativo"),
    )


def test_o_script_grava_a_tabela_sem_nenhuma_raiz_de_pessoa(tmp_path):
    base = _acervo(tmp_path, _registros_do_acervo())
    resumo = script.montar(base, AGORA, "versao-de-teste")
    assert resumo["gravou"] == GRAVADO and resumo["linhas_lidas"] == 5
    arquivo = base / porte.TABELA / f"{porte.TABELA}.parquet"
    gravada = pd.read_parquet(arquivo)
    assert set(gravada["cnpj_basico"]) == {EMPRESA, OUTRA}  # o MEI ficou de fora
    assert not gravada["trata_como_pessoa"].any()
    assert set(gravada["versao_do_codigo"]) == {"versao-de-teste"}
    linha = _da_empresa(gravada, EMPRESA)
    assert (linha["cosmeticos_total"], linha["cosmeticos_ativos"]) == (2, 1)
    assert (linha["medicamentos_total"], linha["medicamentos_ativos"]) == (1, 1)


def test_a_porta_serve_a_tabela_montada_e_recusa_a_linha_de_pessoa(tmp_path):
    """Defesa em profundidade: se um dia entrar uma linha marcada, a porta a esconde."""
    base = _acervo(tmp_path, _registros_do_acervo())
    script.montar(base, AGORA, "x")
    arquivo = base / porte.TABELA / f"{porte.TABELA}.parquet"
    gravada = pd.read_parquet(arquivo)
    intrusa = gravada.iloc[[0]].assign(cnpj_basico=SO_PESSOA, trata_como_pessoa=True)
    pd.concat([gravada, intrusa], ignore_index=True).to_parquet(arquivo, index=False)
    with porta.abrir(base) as p:
        lidas = p.ler(porte.TABELA)
    assert SO_PESSOA not in set(lidas["cnpj_basico"])
    assert {EMPRESA, OUTRA} <= set(lidas["cnpj_basico"])


def test_a_porta_so_mostra_o_retrato_depois_do_fim_do_mes(tmp_path):
    """O retrato de 2026-10-29 vale a partir de 2026-10-31 (regra do mês da porta), nunca antes."""
    base = _acervo(tmp_path, _registros_do_acervo())
    script.montar(base, AGORA, "x")
    with porta.abrir(base) as p:
        antes = p.ler(porte.TABELA, como_era_em="2026-10-30")
        depois = p.ler(porte.TABELA, como_era_em="2026-10-31")
    assert antes.empty
    assert set(depois["cnpj_basico"]) == {EMPRESA}


def test_remontar_sem_retrato_novo_nao_regrava(tmp_path):
    base = _acervo(tmp_path, _registros_do_acervo())
    primeira = script.montar(base, AGORA, "x")
    segunda = script.montar(base, datetime(2026, 11, 12, tzinfo=UTC), "x")
    assert primeira["gravou"] == GRAVADO
    assert segunda["gravou"] == IGUAL


def test_o_script_sai_com_1_sem_anvisa_registros_na_pasta(tmp_path, monkeypatch):
    monkeypatch.setattr(script, "exigir_versao_do_codigo", lambda: "teste")
    assert script.main(["--pasta", str(tmp_path / "vazia")]) == 1


def test_o_script_sai_com_0_e_grava_pela_linha_de_comando(tmp_path, monkeypatch):
    monkeypatch.setattr(script, "exigir_versao_do_codigo", lambda: "teste")
    base = _acervo(tmp_path, _registros_do_acervo())
    assert script.main(["--pasta", str(base)]) == 0
    assert (base / porte.TABELA / f"{porte.TABELA}.parquet").exists()
