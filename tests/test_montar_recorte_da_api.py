"""O recorte da base que vai ao VPS (linha 739): pessoa nunca entra, o que não está na lista não vai."""

import io
import tarfile
from pathlib import Path

import duckdb
import pytest

from base.dicionario import TABELAS
from base.dossie import COLUNAS_DE_PESSOA, pode_consultar
from base.porta.duckdb import ARQUIVOS
from scripts import montar_recorte_da_api as envio


def _parquet(caminho: Path, selecao: str) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    duckdb.sql(f"COPY ({selecao}) TO '{caminho.as_posix()}' (FORMAT PARQUET)")


def _base_de_mentira(raiz: Path) -> Path:
    base = raiz / "base"
    # pgfn: três linhas, uma de pessoa, uma sem marca (na dúvida é pessoa) e uma de empresa
    _parquet(
        base / "pgfn_divida" / "2026" / "a.parquet",
        "SELECT * FROM (VALUES ('11111111000191', true, 'x'), ('22222222000191', NULL, 'y'), "
        "('33333333000191', false, 'z')) t(cnpj, trata_como_pessoa, coluna_desconhecida)",
    )
    # ofertas: coluna de pessoa e uma coluna que o dicionário não conhece
    conhecida = next(
        c
        for c in TABELAS["ofertas_resolucao_160"].colunas
        if c not in COLUNAS_DE_PESSOA
    )
    _parquet(
        base / "ofertas" / "resolucao_160.parquet",
        f"SELECT 'Fulano de Tal' AS administrador, 'DEB' AS {conhecida}, 1 AS segredo_da_casa",
    )
    # demonstrações: nada a tirar, segue igual, com o manifesto ao lado
    nome = next(iter(TABELAS["demonstracoes_como_era"].colunas))
    _parquet(base / "demonstracoes" / "2020.parquet", f"SELECT 1 AS {nome}")
    (base / "demonstracoes" / "2020.json").write_text('{"sha256": "abc"}')
    # fora da lista: nunca é lido
    _parquet(base / "cnpj" / "vigente" / "socios.parquet", "SELECT 'Fulano' AS nome")
    return base


def test_a_lista_inteira_passa_na_conferencia():
    envio.conferir_a_lista(envio.tabelas_do_degrau(2))


def test_os_degraus_nao_repetem_tabela_nem_se_cruzam_com_o_que_fica_em_casa():
    todas = envio.tabelas_do_degrau(2)
    assert len(todas) == len(set(todas))
    assert not set(todas) & set(envio.FICAM_EM_CASA)


def test_tabela_nova_que_a_porta_libera_nao_entra_sozinha():
    """Se a porta passar a mostrar uma tabela, alguém decide: degrau 2 ou fica em casa."""
    decididas = {*envio.DEGRAU_1, *envio.DEGRAU_2_ACRESCENTA, *envio.FICAM_EM_CASA}
    novas = sorted(n for n in TABELAS if pode_consultar(n) and n not in decididas)
    assert novas == []


def test_nenhuma_tabela_da_lista_e_de_pessoa_nem_mora_em_pasta_proibida():
    for nome in envio.tabelas_do_degrau(2):
        assert not TABELAS[nome].pessoa, nome
        assert ARQUIVOS[nome].split("/")[0] not in envio.PASTAS_PROIBIDAS, nome


@pytest.mark.parametrize(
    "nome", ["entidades", "identificadores", "ligacoes", "cnpj_situacao_especial"]
)
def test_rede_e_situacao_especial_nao_vao_ate_a_linha_787(nome):
    """Têm pessoa (MEI, EI, nome em `nao_informada`): só filtradas pela vista publicada."""
    assert nome in envio.FICAM_EM_CASA
    assert nome not in envio.tabelas_do_degrau(2)
    with pytest.raises(envio.RecorteErro, match="fica em casa"):
        envio.conferir_a_lista((nome,))


def test_tabela_fora_da_lista_e_recusada():
    with pytest.raises(envio.RecorteErro, match="fica em casa"):
        envio.conferir_a_lista(("scr_credito",))
    with pytest.raises(envio.RecorteErro, match="não serve"):
        envio.conferir_a_lista(("cnpj_qsa",))


def test_tabela_em_pasta_proibida_e_recusada(monkeypatch):
    monkeypatch.setitem(ARQUIVOS, "demonstracoes_como_era", "cnpj/vigente/*.parquet")
    with pytest.raises(envio.RecorteErro, match="pasta proibida"):
        envio.conferir_a_lista(("demonstracoes_como_era",))


def test_linha_de_pessoa_e_a_sem_marca_nao_saem(tmp_path):
    base = _base_de_mentira(tmp_path)
    saida = tmp_path / "saida"
    resultados = envio.montar(base, saida, ("pgfn_divida",))
    lidas = duckdb.sql(
        f"SELECT cnpj, trata_como_pessoa FROM '{(saida / 'pgfn_divida/2026/a.parquet').as_posix()}'"
    ).fetchall()
    assert lidas == [("33333333000191", False)]
    assert resultados[0].linhas_tiradas == 2
    assert resultados[0].recortados == 1


def test_coluna_de_pessoa_e_coluna_desconhecida_nao_saem(tmp_path, monkeypatch):
    # a tabela de exemplo já não está na lista (fica em casa): o filtro de coluna é testado sem a lista
    monkeypatch.setattr(envio, "conferir_a_lista", lambda tabelas: None)
    base = _base_de_mentira(tmp_path)
    saida = tmp_path / "saida"
    envio.montar(base, saida, ("ofertas_resolucao_160",))
    colunas = duckdb.sql(
        f"SELECT * FROM '{(saida / 'ofertas/resolucao_160.parquet').as_posix()}' LIMIT 0"
    ).columns
    assert not set(colunas) & COLUNAS_DE_PESSOA
    assert "segredo_da_casa" not in colunas


def test_arquivo_sem_nada_a_tirar_vai_igual_com_o_manifesto(tmp_path):
    base = _base_de_mentira(tmp_path)
    saida = tmp_path / "saida"
    resultados = envio.montar(base, saida, ("demonstracoes_como_era",))
    origem = base / "demonstracoes" / "2020.parquet"
    assert (saida / "demonstracoes/2020.parquet").read_bytes() == origem.read_bytes()
    assert (saida / "demonstracoes/2020.json").read_text() == '{"sha256": "abc"}'
    assert resultados[0].copiados == 1


def test_pasta_fora_da_lista_nunca_e_copiada(tmp_path):
    base = _base_de_mentira(tmp_path)
    saida = tmp_path / "saida"
    envio.montar(base, saida, envio.DEGRAU_1)
    assert not (saida / "cnpj").exists()
    assert not list(saida.rglob("socios*"))


def test_arquivo_sem_a_marca_de_pessoa_nao_sai(tmp_path):
    base = tmp_path / "base"
    _parquet(base / "pgfn_divida" / "2026" / "a.parquet", "SELECT '1' AS cnpj")
    with pytest.raises(envio.RecorteErro, match="separar pessoa"):
        envio.montar(base, tmp_path / "saida", ("pgfn_divida",))


def test_saida_com_pessoa_derruba_o_envio(tmp_path):
    arquivo = tmp_path / "pgfn_divida" / "a.parquet"
    _parquet(arquivo, "SELECT true AS trata_como_pessoa")
    con = duckdb.connect()
    with pytest.raises(envio.RecorteErro, match="linha de pessoa"):
        envio.conferir_saida(con, "pgfn_divida", arquivo)
    outro = tmp_path / "ofertas.parquet"
    _parquet(outro, "SELECT 'Fulano' AS administrador")
    with pytest.raises(envio.RecorteErro, match="coluna de pessoa"):
        envio.conferir_saida(con, "ofertas_resolucao_160", outro)


def test_o_tar_tem_so_arquivo_comum_com_caminho_relativo_dentro_de_base(tmp_path):
    base = _base_de_mentira(tmp_path)
    saida = tmp_path / "saida"
    envio.montar(base, saida, ("pgfn_divida", "demonstracoes_como_era"))
    pacote = io.BytesIO()
    assert envio.empacotar(saida, pacote) == 3  # a.parquet, 2020.parquet, 2020.json
    pacote.seek(0)
    with tarfile.open(fileobj=pacote) as tar:
        nomes = tar.getnames()
        assert all(m.isreg() for m in tar.getmembers())
    assert sorted(nomes) == [
        "demonstracoes/2020.json",
        "demonstracoes/2020.parquet",
        "pgfn_divida/2026/a.parquet",
    ]
    assert not any(n.startswith(("/", "..", "cnpj")) for n in nomes)


def test_main_falha_com_a_linha_de_falhas_quando_falta_arquivo_do_nucleo(
    tmp_path, capsys
):
    base = tmp_path / "base"
    base.mkdir()
    codigo = envio.main(
        ["--degrau", "1", "--base", str(base), "--saida", str(tmp_path / "saida")]
    )
    assert codigo == 1
    assert capsys.readouterr().out.startswith("FALHAS: sem arquivo na base")


def test_o_compose_monta_o_recorte_so_para_leitura_na_api():
    """O contêiner da API lê a base em /app/acervo, montada `:ro`, e não liga as rotas de dado por conta própria."""
    compose = (Path(__file__).resolve().parents[1] / "compose.yaml").read_text(
        encoding="utf-8"
    )
    api = compose.split("  tickerlab-api:", 1)[1].split("\n  # ", 1)[0]
    assert "- ./acervo_api:/app/acervo:ro" in api
    assert "TICKERLAB_ACERVO: /app/acervo" in api
    assert "TICKERLAB_API_EXTERNA" not in api
    assert "TICKERLAB_API_V1" not in api


def test_saida_com_sobra_de_rodada_antiga_derruba_o_envio(tmp_path, capsys):
    """O tar leva tudo o que está na pasta de saída: sobra (ex.: rede com pessoa) não pode ir junto."""
    base = _base_de_mentira(tmp_path)
    saida = tmp_path / "saida"
    (saida / "rede").mkdir(parents=True)
    (saida / "rede" / "entidades.parquet").write_bytes(b"velho")
    codigo = envio.main(["--degrau", "1", "--base", str(base), "--saida", str(saida)])
    assert codigo == 1
    assert "não está vazia" in capsys.readouterr().out


def test_link_simbolico_na_saida_nao_vai_no_tar(tmp_path):
    saida = tmp_path / "saida"
    saida.mkdir()
    alvo = tmp_path / "fora.parquet"
    alvo.write_bytes(b"x")
    try:
        (saida / "atalho.parquet").symlink_to(alvo)
    except OSError:
        pytest.skip("sem permissão para link simbólico")
    with pytest.raises(envio.RecorteErro, match="link simbólico"):
        envio.empacotar(saida, io.BytesIO())


@pytest.mark.parametrize(
    "tabela",
    [
        "anatel_acessos",
        "ifdata_cadastro",
        "carteiras_bloco_8",
        "controladas",
        "auditores",
        "ofertas_antigas",
        "trocas_de_auditor",
        "ofertas_resolucao_160",
    ],
)
def test_tabela_com_pessoa_ou_duvida_fica_em_casa(tabela, tmp_path):
    # achadas pela 789 em 10/11/2026 (linha 739): nunca no degrau 1 nem no 2
    assert tabela not in envio.DEGRAU_1 + envio.DEGRAU_2_ACRESCENTA
    with pytest.raises(envio.RecorteErro, match="fica em casa"):
        envio.montar(tmp_path / "base", tmp_path / "saida", (tabela,))


TABELAS_PJ = ("cnpj_empresas_pj", "cnpj_estabelecimentos_pj")


def _empresas_pj(
    base: Path, linhas: str, raizes_com_estabelecimento: str = "('00000000')"
) -> None:
    _parquet(
        base / "cnpj_empresas_pj" / "00.parquet",
        f"SELECT * FROM (VALUES {linhas}) t(cnpj_basico, razao_social, natureza_juridica, porte)",
    )
    _parquet(
        base / "cnpj_estabelecimentos_pj" / "00.parquet",
        f"SELECT * FROM (VALUES {raizes_com_estabelecimento}) t(cnpj_basico)",
    )


def _raizes_da_saida(saida: Path) -> list[str]:
    arquivo = saida / "cnpj_empresas_pj" / "00.parquet"
    linhas = duckdb.sql(f"SELECT cnpj_basico FROM '{arquivo.as_posix()}'").fetchall()
    return sorted(r[0] for r in linhas)


def test_as_tabelas_pj_do_cnpj_estao_no_degrau_2():
    """Pode da Diretoria de 10/11/2026 18h31 (Emenda 4), linha 796."""
    for nome in TABELAS_PJ:
        assert nome in envio.tabelas_do_degrau(2)
        assert nome not in envio.FICAM_EM_CASA
    # o histórico (MEI e EI sem marca por linha) segue em casa
    assert "cnpj_empresas_historico" in envio.FICAM_EM_CASA


def test_empresas_pj_limpa_sai_inteira(tmp_path):
    base = tmp_path / "base"
    _empresas_pj(base, "('00000000', 'BANCO DO BRASIL SA', '2038', 'demais')")
    envio.montar(base, tmp_path / "saida", TABELAS_PJ)
    assert _raizes_da_saida(tmp_path / "saida") == ["00000000"]


def test_mei_com_natureza_de_empresa_nao_sai_em_empresas_pj(tmp_path):
    """A vista de estabelecimentos tira o MEI; a raiz dele sai de `cnpj_empresas_pj` junto (razão = nome)."""
    base = tmp_path / "base"
    _empresas_pj(
        base,
        "('00000000', 'BANCO DO BRASIL SA', '2038', 'demais'), "
        "('55555555', 'FULANO DE TAL', '2062', 'micro')",
    )
    envio.montar(base, tmp_path / "saida", TABELAS_PJ)
    assert _raizes_da_saida(tmp_path / "saida") == ["00000000"]


def test_empresas_pj_nao_vai_sem_estabelecimentos(tmp_path):
    base = tmp_path / "base"
    _empresas_pj(base, "('00000000', 'BANCO DO BRASIL SA', '2038', 'demais')")
    with pytest.raises(envio.RecorteErro, match="junto"):
        envio.montar(base, tmp_path / "saida", ("cnpj_empresas_pj",))


@pytest.mark.parametrize(
    ("razao", "natureza"),
    [
        ("EMPRESA 123.456.789-09 LTDA", "2062"),
        ("EMPRESA 12345678909 LTDA", "2062"),
        ("EMPRESA 123456789012 LTDA", "2062"),
        ("JOAO DA SILVA", "2135"),
        ("MARIA", "4014"),
    ],
)
def test_empresas_pj_com_pessoa_na_saida_e_recusada(tmp_path, razao, natureza):
    base = tmp_path / "base"
    _empresas_pj(
        base, f"('11111111', '{razao}', '{natureza}', 'micro')", "('11111111')"
    )
    with pytest.raises(envio.RecorteErro, match="saiu com pessoa"):
        envio.montar(base, tmp_path / "saida", TABELAS_PJ)


def test_cnpj_de_14_digitos_na_razao_nao_e_pessoa(tmp_path):
    base = tmp_path / "base"
    _empresas_pj(
        base,
        "('22222222', 'FILIAL DA 12345678000190 SA', '2062', 'demais')",
        "('22222222')",
    )
    envio.montar(base, tmp_path / "saida", TABELAS_PJ)


# ---------------------------------------------------------------- entradas de sócio PJ (linha 810)

COM_ENTRADAS = (*TABELAS_PJ, "entradas_de_socio_pj")


def _entradas(base: Path, pares: str) -> None:
    """Entradas (empresa, sócia PJ) com as colunas da tabela de verdade."""
    _parquet(
        base / "entradas_de_socio_pj" / "00.parquet",
        "SELECT 'entrada' AS movimento, cnpj_basico, raiz_socio_pj, DATE '2024-05-01' AS data_entrada, "
        "'49' AS qualificacao, '2026-10' AS mes_do_retrato, DATE '2026-10-30' AS disponivel_em "
        f"FROM (VALUES {pares}) t(cnpj_basico, raiz_socio_pj)",
    )


def _empresas_e_entradas(base: Path, pares: str) -> None:
    _empresas_pj(
        base,
        "('00000000', 'BANCO DO BRASIL SA', '2038', 'demais'), "
        "('11111111', 'HOLDING SA', '2054', 'demais'), "
        "('55555555', 'FULANO DE TAL', '2062', 'micro')",
        "('00000000'), ('11111111')",
    )
    _entradas(base, pares)


def test_entradas_de_socio_pj_sobe_com_o_pode_da_diretoria():
    """Pode da Diretoria de 11/11/2026 (Emenda 4), linha 810: só PJ com PJ, conferida na saída."""
    assert "entradas_de_socio_pj" in envio.tabelas_do_degrau(2)
    assert "entradas_de_socio_pj" not in envio.FICAM_EM_CASA


def test_entradas_pj_com_pj_sai_inteira(tmp_path):
    base = tmp_path / "base"
    _empresas_e_entradas(base, "('00000000', '11111111')")
    envio.montar(base, tmp_path / "saida", COM_ENTRADAS)
    arquivo = tmp_path / "saida" / "entradas_de_socio_pj" / "00.parquet"
    assert duckdb.sql(f"SELECT count(*) FROM '{arquivo.as_posix()}'").fetchone() == (1,)


@pytest.mark.parametrize(
    "par",
    [
        "('00000000', '99999999')",  # sócia fora da lista sem pessoa
        "('99999999', '11111111')",  # empresa fora da lista
        "('00000000', '55555555')",  # sócia de MEI, que a saída de empresas tira
        "('00000000', NULL)",  # sócia sem raiz
    ],
)
def test_entradas_com_raiz_fora_da_lista_sem_pessoa_derruba_o_envio(tmp_path, par):
    base = tmp_path / "base"
    _empresas_e_entradas(base, f"('00000000', '11111111'), {par}")
    with pytest.raises(envio.RecorteErro, match="fora da lista sem pessoa"):
        envio.montar(base, tmp_path / "saida", COM_ENTRADAS)


def test_entradas_nao_vai_sem_empresas_pj(tmp_path):
    base = tmp_path / "base"
    _entradas(base, "('00000000', '11111111')")
    with pytest.raises(envio.RecorteErro, match="junto"):
        envio.montar(base, tmp_path / "saida", ("entradas_de_socio_pj",))
