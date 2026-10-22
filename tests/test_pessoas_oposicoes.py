"""Canal dos titulares do CNPJ (PR 7 do plano da base de CNPJ, ADR 0106 regra 3.8, ADR 0077 item 2): o pedido
vira oposição com prazo de 15 dias, a lápide tira o nome do restrito e o id do QSA, a carga seguinte não traz a
pessoa de volta e a saída já não mostra o nome. Dados de mentira; nenhuma pessoa real."""

import io
import logging
from datetime import date

import pandas as pd
import pytest

from base.pessoas import consulta, oposicoes, portao
from base.receita_retrato import ParteDoQsa
from scripts import carga_receita_mes as rc
from scripts import oposicao_do_titular as cli

CHAVE = b"k" * 32
MARIA = "MARIA DA SILVA"
JOAO = "JOAO PEREIRA"
EMPRESA = "11111111"
PEDIDO_EM = date(2026, 10, 22)


def _qsa(*socios):
    """Cada sócio PF: (cnpj_basico, nome, meio do CPF)."""
    tabela = pd.DataFrame(
        [
            {
                "cnpj_basico": b,
                "tipo_socio": "2",
                "raiz_socio_pj": "",
                "qualificacao": "49",
                "data_entrada": pd.Timestamp("2019-03-01"),
                "pais": "",
            }
            for b, _, _ in socios
        ]
    )
    pessoas = pd.DataFrame(
        [
            {
                "cnpj_basico": b,
                "tipo_socio": "2",
                "nome_socio": n,
                "qualificacao": "49",
                "data_entrada": pd.Timestamp("2019-03-01"),
                "cpf_mascarado": f"***{meio}**",
            }
            for b, n, meio in socios
        ]
    )
    return [ParteDoQsa(tabela, pessoas)]


def _mes(pasta, restrita, mes, *socios):
    rc.processar_mes(
        mes,
        pasta,
        restrita,
        estabelecimentos=[
            pd.DataFrame({"cnpj": [EMPRESA + "000191"], "situacao": ["ativa"]})
        ],
        simples=[pd.DataFrame({"cnpj_basico": [EMPRESA], "optante_mei": [False]})],
        qsa=_qsa(*socios),
        chave_de_pessoas=CHAVE,
        arquivos={"Socios0.zip": "ab" * 32},
    )


def _pessoas(restrita):
    arquivos = list((restrita / "pessoas").rglob("*.parquet"))
    return pd.concat([pd.read_parquet(a) for a in arquivos], ignore_index=True)


def _qsa_gravado(pasta):
    arquivos = list(pasta.rglob("qsa/*.parquet"))
    return pd.concat([pd.read_parquet(a) for a in arquivos], ignore_index=True)


def _vigente_qsa(pasta):
    arquivos = list((pasta / "vigente" / "qsa").glob("*.parquet"))
    return pd.concat([pd.read_parquet(a) for a in arquivos], ignore_index=True)


@pytest.fixture
def pastas(tmp_path):
    pasta, restrita = tmp_path / "cnpj", tmp_path / "restrito"
    _mes(
        pasta,
        restrita,
        "2026-09",
        (EMPRESA, MARIA, "982247"),
        (EMPRESA, JOAO, "123456"),
    )
    return pasta, restrita


@pytest.fixture
def portao_aberto(tmp_path, monkeypatch):
    """O portão aberto só neste teste: bandeira ligada e as quatro condições num `.toml` temporário."""
    condicoes = tmp_path / "conferidas"
    condicoes.mkdir()
    texto = "\n".join(
        f'[{c}]\ndata = "2026-10-22"\npode = true' for c in portao.CONDICOES
    )
    (condicoes / "portao_rfb_cnpj.toml").write_text(texto, encoding="utf-8")
    monkeypatch.setitem(portao.NOMES_LIBERADOS, "rfb-cnpj", True)
    monkeypatch.setattr(portao, "PASTA_DAS_CONDICOES", condicoes)
    return condicoes


def _opor(restrita, nome=MARIA, meio=None):
    ids = oposicoes.achar_titular(restrita, EMPRESA + "000191", nome, meio)
    oposicoes.registrar(restrita, ids, PEDIDO_EM)
    return ids


# --- achar o titular pela prova mínima


def test_titular_achado_pelo_cnpj_e_pelo_nome(pastas):
    _, restrita = pastas
    ids = oposicoes.achar_titular(
        restrita, "11.111.111/0001-91", "Maria da Silva", None
    )
    assert len(ids) == 1
    assert ids == oposicoes.achar_titular(restrita, EMPRESA, "MARIA  DA SILVA", None)


def test_nome_de_outra_empresa_nao_acha_ninguem(pastas):
    _, restrita = pastas
    assert oposicoes.achar_titular(restrita, "22222222", MARIA, None) == []
    assert oposicoes.achar_titular(restrita, EMPRESA, "MARIA SOUZA", None) == []


def test_homonimo_se_resolve_pelos_6_digitos_do_meio(tmp_path):
    pasta, restrita = tmp_path / "cnpj", tmp_path / "restrito"
    _mes(
        pasta,
        restrita,
        "2026-09",
        (EMPRESA, MARIA, "982247"),
        (EMPRESA, MARIA, "111111"),
    )
    assert len(oposicoes.achar_titular(restrita, EMPRESA, MARIA, None)) == 2
    assert len(oposicoes.achar_titular(restrita, EMPRESA, MARIA, "982247")) == 1
    # CPF inteiro, se vier, só tem o meio usado (e nunca é guardado)
    assert oposicoes.achar_titular(
        restrita, EMPRESA, MARIA, "529.982.247-25"
    ) == oposicoes.achar_titular(restrita, EMPRESA, MARIA, "982247")


# --- prazo de 15 dias


def test_pedido_conta_o_prazo_de_15_dias(pastas):
    _, restrita = pastas
    _opor(restrita)
    registro = oposicoes.ler(restrita)
    assert list(registro.columns) == list(oposicoes.COLUNAS)
    assert len(registro) == 1
    assert registro.iloc[0]["pedido_em"] == PEDIDO_EM
    assert registro.iloc[0]["prazo_ate"] == date(2026, 11, 6)
    assert pd.isna(registro.iloc[0]["atendida_em"])
    assert not set(registro.columns) & {"nome", "nome_socio", "cpf_mascarado"}


def test_pedido_repetido_nao_reabre_o_prazo(pastas):
    _, restrita = pastas
    _opor(restrita)
    oposicoes.registrar(
        restrita,
        oposicoes.achar_titular(restrita, EMPRESA, MARIA, None),
        date(2026, 10, 30),
    )
    registro = oposicoes.ler(restrita)
    assert len(registro) == 1 and registro.iloc[0]["pedido_em"] == PEDIDO_EM


def test_atendida_registra_o_dia_e_some_das_vencidas(pastas):
    pasta, restrita = pastas
    _opor(restrita)
    assert oposicoes.vencidas(restrita, date(2026, 11, 7)) == 1
    assert oposicoes.vencidas(restrita, date(2026, 11, 6)) == 0
    oposicoes.atender(pasta, restrita, date(2026, 10, 23))
    registro = oposicoes.ler(restrita)
    assert registro.iloc[0]["atendida_em"] == date(2026, 10, 23)
    assert registro.iloc[0]["atendida_em"] <= registro.iloc[0]["prazo_ate"]
    assert oposicoes.vencidas(restrita, date(2026, 12, 1)) == 0


# --- lápide


def test_oposicao_vira_lapide_no_remonte(pastas):
    pasta, restrita = pastas
    (id_maria,) = _opor(restrita)
    _mes(
        pasta,
        restrita,
        "2026-10",
        (EMPRESA, MARIA, "982247"),
        (EMPRESA, JOAO, "999999"),
    )
    oposicoes.atender(pasta, restrita, date(2026, 10, 23))
    # a lápide: o nome sai do restrito e o id sai do QSA vigente e das mudanças, a linha fica
    assert list(_pessoas(restrita)["nome"]) == [JOAO]
    assert id_maria not in set(_qsa_gravado(pasta).astype(str).to_numpy().ravel())
    assert len(_vigente_qsa(pasta)) == 2
    # o remonte (a carga do mês seguinte) lê as oposições e não traz a pessoa de volta
    _mes(
        pasta,
        restrita,
        "2026-11",
        (EMPRESA, MARIA, "982247"),
        (EMPRESA, JOAO, "999999"),
    )
    assert list(_pessoas(restrita)["nome"]) == [JOAO]
    assert id_maria not in set(_qsa_gravado(pasta).astype(str).to_numpy().ravel())
    # e a sócia que se opôs não vira uma "mudança" falsa no mês seguinte
    novembro = pasta / "mudancas" / "qsa" / "2026-11.parquet"
    assert not novembro.exists() or pd.read_parquet(novembro).empty


def test_carga_sem_oposicoes_segue_igual(pastas):
    _, restrita = pastas
    assert oposicoes.ler(restrita).empty
    assert sorted(_pessoas(restrita)["nome"]) == [JOAO, MARIA]


def test_lapide_anota_o_dia_e_nunca_o_id_no_log(pastas, caplog):
    pasta, restrita = pastas
    (id_maria,) = _opor(restrita)
    with caplog.at_level(logging.INFO):
        resumo = oposicoes.atender(pasta, restrita, date(2026, 10, 23))
    assert resumo.pessoas_tiradas == 1 and resumo.atendidas == 1
    assert id_maria not in caplog.text and "MARIA" not in caplog.text
    # rodar de novo não muda nada (idempotente)
    assert oposicoes.atender(pasta, restrita, date(2026, 10, 24)).atendidas == 0


# --- o nome sai da saída (tela, API, PDF, exportação)


def test_portao_fechado_a_consulta_nao_da_nome(pastas):
    pasta, restrita = pastas
    socios = consulta.socios_da_empresa(pasta, restrita, EMPRESA)
    assert len(socios) == 2 and socios["nome"].isna().all()


def test_oposicao_tira_o_nome_da_api(pastas, portao_aberto):
    pasta, restrita = pastas
    antes = consulta.socios_da_empresa(pasta, restrita, EMPRESA)
    assert sorted(antes["nome"]) == [JOAO, MARIA]
    _opor(restrita)
    # já no pedido, antes da lápide, o nome não sai mais: vira "sócio pessoa física"
    depois = consulta.socios_da_empresa(pasta, restrita, EMPRESA)
    assert list(depois["nome"].dropna()) == [JOAO] and depois["nome"].isna().sum() == 1
    oposicoes.atender(pasta, restrita, date(2026, 10, 23))
    # depois da lápide a linha continua no quadro, sem nome: "sócio pessoa física"
    final = consulta.socios_da_empresa(pasta, restrita, EMPRESA)
    assert len(final) == 2 and list(final["nome"].dropna()) == [JOAO]


def test_consulta_e_de_uma_empresa_so(pastas):
    pasta, restrita = pastas
    with pytest.raises(ValueError):
        consulta.socios_da_empresa(pasta, restrita, "")
    assert consulta.socios_da_empresa(pasta, restrita, "22222222").empty
    assert not {"cpf_mascarado", "id_pessoa"} & set(
        consulta.socios_da_empresa(pasta, restrita, EMPRESA)
    )


# --- o script do canal (o que quem atende roda no servidor)


def test_script_registra_e_atende_sem_mostrar_nome(pastas, capsys, monkeypatch):
    pasta, restrita = pastas
    monkeypatch.setattr("sys.stdin", io.StringIO(MARIA + "\n"))
    saida = cli.main(
        [
            "pedido",
            "--base", str(pasta),
            "--restrita", str(restrita),
            "--cnpj", EMPRESA + "000191",
            "--pedido-em", "2026-10-22",
            "--hoje", "2026-10-23",
        ]
    )  # fmt: skip
    texto = capsys.readouterr().out
    assert saida == 0
    assert "MARIA" not in texto and "982247" not in texto
    assert "2026-11-06" in texto
    assert list(_pessoas(restrita)["nome"]) == [JOAO]


def test_script_com_homonimo_pede_os_6_digitos(tmp_path, capsys, monkeypatch):
    pasta, restrita = tmp_path / "cnpj", tmp_path / "restrito"
    _mes(
        pasta,
        restrita,
        "2026-09",
        (EMPRESA, MARIA, "982247"),
        (EMPRESA, MARIA, "111111"),
    )
    monkeypatch.setattr("sys.stdin", io.StringIO(MARIA + "\n"))
    argumentos = [
        "pedido",
        "--base",
        str(pasta),
        "--restrita",
        str(restrita),
        "--cnpj",
        EMPRESA,
    ]
    assert cli.main(argumentos) == 1
    assert "6 dígitos" in capsys.readouterr().out
    assert oposicoes.ler(restrita).empty


def test_script_sem_ninguem_nao_registra(pastas, capsys, monkeypatch):
    pasta, restrita = pastas
    monkeypatch.setattr("sys.stdin", io.StringIO("FULANO DE TAL\n"))
    argumentos = [
        "pedido",
        "--base",
        str(pasta),
        "--restrita",
        str(restrita),
        "--cnpj",
        EMPRESA,
    ]
    assert cli.main(argumentos) == 1
    assert oposicoes.ler(restrita).empty


def test_script_conferir_falha_com_vencida(pastas, capsys):
    _, restrita = pastas
    _opor(restrita)
    argumentos = ["conferir", "--restrita", str(restrita), "--hoje"]
    assert cli.main([*argumentos, "2026-11-06"]) == 0
    assert cli.main([*argumentos, "2026-11-07"]) == 1
    assert "FALHAS:" in capsys.readouterr().out


def test_script_acesso_mostra_o_papel_sem_nome_nem_cpf(pastas, capsys, monkeypatch):
    _, restrita = pastas
    monkeypatch.setattr("sys.stdin", io.StringIO(MARIA + "\n"))
    argumentos = ["acesso", "--restrita", str(restrita), "--cnpj", EMPRESA]
    assert cli.main(argumentos) == 0
    texto = capsys.readouterr().out
    assert "49" in texto and "2019-03-01" in texto
    assert "MARIA" not in texto and "982247" not in texto
