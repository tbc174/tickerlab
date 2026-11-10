"""O recorte da base que vai ao VPS (linha 739): pessoa nunca entra, o que não está na lista não vai."""

import io
import tarfile
from pathlib import Path

import duckdb
import pytest

from base.dicionario import TABELAS
from base.dossie import COLUNAS_DE_PESSOA, pode_consultar
from base.porta.duckdb import ARQUIVOS
from scripts import enviar_base_ao_vps as envio


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


def test_coluna_de_pessoa_e_coluna_desconhecida_nao_saem(tmp_path):
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
