"""Esquema `pessoas`: pseudônimo por HMAC, portão por fonte, tabelas e acervo restrito (PR 4 do plano
da base de CNPJ, ADR 0106). Dados de mentira; nenhuma pessoa real."""

import pandas as pd
import pytest

from base.pessoas import chave, portao, proibidas, tabelas

CHAVE = b"k" * 32


def test_mascara_deixa_os_6_do_meio():
    assert chave.mascarar_cpf("529.982.247-25") == "***982247**"
    assert chave.mascarar_cpf("52998224725") == "***982247**"


def test_mascara_e_idempotente_e_recusa_lixo():
    assert chave.mascarar_cpf("***982247**") == "***982247**"
    with pytest.raises(ValueError):
        chave.mascarar_cpf("123")


def test_normalizacao_do_nome_e_unica():
    assert chave.normalizar_nome("  José   da Silva-Júnior ") == "JOSE DA SILVA"
    assert chave.normalizar_nome("MARIA D'ÁVILA FILHO") == "MARIA D AVILA"


def test_chave_usa_primeiro_e_ultimo_nome():
    assert chave.primeiro_e_ultimo("Ana Maria de Souza Lima") == ("ANA", "LIMA")
    assert chave.primeiro_e_ultimo("Madonna") == ("MADONNA", "MADONNA")


def test_id_igual_entre_cpf_inteiro_e_mascarado():
    a = chave.id_pessoa("529.982.247-25", "Ana", "Lima", CHAVE)
    b = chave.id_pessoa("***982247**", "ANA", "lima", CHAVE)
    assert a == b
    assert len(a) == 32 and "982247" not in a


def test_id_muda_com_a_chave_e_com_o_nome():
    base = chave.id_pessoa("***982247**", "ANA", "LIMA", CHAVE)
    assert base != chave.id_pessoa("***982247**", "ANA", "LIMA", b"z" * 32)
    assert base != chave.id_pessoa("***982247**", "ANA", "SOUZA", CHAVE)


def test_sem_chave_nao_roda(tmp_path, monkeypatch):
    monkeypatch.delenv(chave.VARIAVEL_DA_CHAVE, raising=False)
    with pytest.raises(chave.ErroSemChave):
        chave.ler_chave(tmp_path / "nao-existe")
    curta = tmp_path / "curta"
    curta.write_text("abc")
    with pytest.raises(chave.ErroSemChave):
        chave.ler_chave(curta)
    boa = tmp_path / "boa"
    boa.write_text("k" * 40 + "\n")
    assert chave.ler_chave(boa) == b"k" * 40


def _brutas():
    return pd.DataFrame(
        {
            "cnpj_basico": ["33000167", "33000167"],
            "tipo_socio": ["2", "3"],
            "nome_socio": ["MARIA DA SILVA", "JOHN SMITH"],
            "qualificacao": ["49", "37"],
            "data_entrada": pd.to_datetime(["2019-03-01", None]),
            "cpf_mascarado": ["***982247**", "00000000000"],
        }
    )


def test_nome_do_socio_so_no_esquema_pessoas():
    pessoas = tabelas.montar_pessoas(_brutas(), "rfb-cnpj", CHAVE)
    assert list(pessoas.columns) == list(tabelas.COLUNAS_DE_PESSOAS)
    assert set(pessoas["nivel"]) == {2}
    assert list(pessoas["nome"]) == ["MARIA DA SILVA", "JOHN SMITH"]
    assert pessoas["id_pessoa"].is_unique
    # todo o resto da cadeia carrega só o id
    ids = tabelas.ids_das_linhas(_brutas(), CHAVE)
    assert "nome" not in "".join(ids.astype(str))


def test_cpf_so_mascarado():
    inteiro = _brutas().assign(cpf_mascarado=["52998224725", "00000000000"])
    with pytest.raises(ValueError):
        tabelas.montar_pessoas(inteiro, "rfb-cnpj", CHAVE)


def test_tabelas_de_apoio_nascem_vazias_com_as_colunas():
    assert tabelas.acessos_vazios().empty
    assert {"id_pessoa", "quando", "quem", "finalidade"} <= set(
        tabelas.acessos_vazios().columns
    )
    assert {"id_pessoa", "pedido_em", "prazo_ate", "atendida_em"} <= set(
        tabelas.oposicoes_vazias().columns
    )


def test_oposicao_tira_o_nome_do_que_sai():
    pessoas = tabelas.montar_pessoas(_brutas(), "rfb-cnpj", CHAVE)
    opostos = {pessoas["id_pessoa"].iloc[0]}
    depois = tabelas.sem_opostos(pessoas, opostos)
    assert list(depois["nome"]) == ["JOHN SMITH"]


# --- portão


def _toml(pasta, fonte, **condicoes):
    linhas = []
    for nome in portao.CONDICOES:
        if nome in condicoes:
            data, pode = condicoes[nome]
            linhas += [f"[{nome}]", f'data = "{data}"', f"pode = {str(pode).lower()}"]
    arquivo = pasta / f"portao_{fonte.replace('-', '_')}.toml"
    arquivo.write_text("\n".join(linhas), encoding="utf-8")


def test_portao_fechado_nenhum_nome_sai():
    assert all(aberto is False for aberto in portao.NOMES_LIBERADOS.values())
    assert portao.nome_para_saida("rfb-cnpj", "MARIA DA SILVA") is None
    assert portao.nome_para_saida("fonte-que-nao-existe", "MARIA") is None


def test_portao_so_abre_com_as_quatro_condicoes(tmp_path, monkeypatch):
    todas = {c: ("2026-10-21", True) for c in portao.CONDICOES}
    _toml(tmp_path, "rfb-cnpj", **todas)
    assert portao.condicoes_cumpridas("rfb-cnpj", tmp_path)
    faltando = dict(todas)
    del faltando["canal"]
    _toml(tmp_path, "rfb-cnpj", **faltando)
    assert not portao.condicoes_cumpridas("rfb-cnpj", tmp_path)
    sem_pode = dict(todas, ripd=("2026-10-21", False))
    _toml(tmp_path, "rfb-cnpj", **sem_pode)
    assert not portao.condicoes_cumpridas("rfb-cnpj", tmp_path)
    _toml(tmp_path, "rfb-cnpj", **dict(todas, lia=("", True)))
    assert not portao.condicoes_cumpridas("rfb-cnpj", tmp_path)
    assert not portao.condicoes_cumpridas("outra", tmp_path)


def test_bandeira_sozinha_nao_abre_sem_o_toml(tmp_path, monkeypatch):
    monkeypatch.setitem(portao.NOMES_LIBERADOS, "rfb-cnpj", True)
    assert portao.nome_para_saida("rfb-cnpj", "MARIA", tmp_path) is None


def test_portao_abre_com_bandeira_e_condicoes(tmp_path, monkeypatch):
    _toml(tmp_path, "rfb-cnpj", **{c: ("2026-10-21", True) for c in portao.CONDICOES})
    monkeypatch.setitem(portao.NOMES_LIBERADOS, "rfb-cnpj", True)
    assert portao.nome_para_saida("rfb-cnpj", "MARIA", tmp_path) == "MARIA"


# --- colunas proibidas


def test_coluna_proibida_e_achada():
    achados = proibidas.procurar(
        pd.DataFrame({"cpf": ["x"], "Data_Nascimento": ["y"], "valor": [1]}), "t"
    )
    assert len(achados) == 2


def test_conteudo_parecido_com_cpf_quebra():
    achados = proibidas.procurar(pd.DataFrame({"doc": ["529.982.247-25"]}), "t")
    assert achados
    assert proibidas.procurar(pd.DataFrame({"doc": ["52998224725"]}), "t")


def test_cnpj_nao_e_confundido_com_cpf():
    cnpj = pd.DataFrame(
        {"doc": ["33000167000101", "12ABC34501DE35", "33.000.167/0001-01"]}
    )
    assert proibidas.procurar(cnpj, "t") == []


def test_email_de_pessoa_quebra():
    assert proibidas.procurar(pd.DataFrame({"contato": ["fulano@exemplo.com"]}), "t")


def test_cpf_mascarado_passa():
    assert proibidas.procurar(pd.DataFrame({"doc": ["***982247**"]}), "t") == []


def test_nenhuma_tabela_fora_de_pessoas_tem_coluna_proibida():
    from base.dicionario import TABELAS

    achados = {}
    for nome, tabela in TABELAS.items():
        if tabela.pessoa or nome.startswith("pessoas"):
            continue
        ruins = proibidas.colunas_proibidas(tabela.colunas, nome)
        if ruins:
            achados[nome] = ruins
    assert achados == {}
