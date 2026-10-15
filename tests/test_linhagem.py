"""Linhagem para auditoria (série 3 da base de ML, PR 1; ADR 0055, exigência 13): de qualquer linha
da base, chegar ao arquivo original, à data da coleta e à versão do código que a processou."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest
import sqlalchemy as sa

from base.linhagem import linhagem_da_linha, linhagem_da_tabela
from base.ponto_no_tempo import gravar_parquet, montar_base
from src import acervo
from src import versao_do_codigo as vc
from src.banco.coletas import registrar
from src.banco.conexao import criar_engine, migrar_para
from tests.test_base_ponto_no_tempo import _tres_publicacoes

URL = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/DADOS/dfp_cia_aberta_2022.zip"
ORIGINAL = b"PK\x03\x04 arquivo da CVM (recorte)"
BAIXADO_EM = datetime(2026, 10, 13, 0, 30, tzinfo=UTC)
VERSAO = "7ddaf09c1e6b0b5a9c1d2e3f4a5b6c7d8e9f0a1b"


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    """Acervo e registro de coletas de mentira, com um original guardado e registrado."""
    monkeypatch.setenv(acervo.VARIAVEL_DA_PASTA, str(tmp_path / "acervo"))
    monkeypatch.setenv(vc.VARIAVEL, VERSAO)
    url_do_banco = f"sqlite:///{(tmp_path / 'b.sqlite').as_posix()}"
    migrar_para("head", url=url_do_banco)
    motor = criar_engine(url_do_banco)
    caminho = acervo.guardar_original("cvm-dfp-itr", URL, ORIGINAL, BAIXADO_EM)
    with motor.begin() as c:
        registrar(
            c,
            "cvm-dfp-itr",
            URL,
            ORIGINAL,
            "ok",
            agora=BAIXADO_EM,
            caminho_do_original=caminho,
        )
    origens = [{"url": URL, "sha256": hashlib.sha256(ORIGINAL).hexdigest()}]
    pasta = tmp_path / "base"
    gravar_parquet(montar_base(_tres_publicacoes()), pasta, origens=origens)
    yield motor, pasta
    motor.dispose()


def test_manifesto_do_ano_tem_a_versao_do_codigo(ambiente):
    _, pasta = ambiente
    manifesto = json.loads((pasta / "2022.json").read_text(encoding="utf-8"))
    assert manifesto["versao_do_codigo"] == VERSAO


def test_linha_sorteada_volta_ao_original(ambiente):
    motor, pasta = ambiente
    base = pd.concat(pd.read_parquet(p) for p in sorted(pasta.glob("*.parquet")))
    linha = base.sample(1, random_state=13).iloc[0]
    with motor.connect() as c:
        caminho = linhagem_da_linha(c, pasta, linha)
    assert caminho.versao_do_codigo == VERSAO
    assert caminho.base_confere  # o Parquet ainda tem o hash do manifesto
    [origem] = caminho.origens
    assert origem.url == URL
    assert origem.baixado_em.replace(tzinfo=None) == BAIXADO_EM.replace(tzinfo=None)
    assert origem.original_confere  # o arquivo no acervo tem o SHA-256 do registro
    assert caminho.completa


def test_original_mexido_no_acervo_quebra_a_linhagem(ambiente):
    motor, pasta = ambiente
    with motor.connect() as c:
        relativo = c.execute(
            sa.text("select caminho_do_original from coletas")
        ).scalar_one()
    (acervo.pasta_do_acervo() / relativo).write_bytes(b"outro conteudo")
    linha = pd.read_parquet(pasta / "2022.parquet").iloc[0]
    with motor.connect() as c:
        caminho = linhagem_da_linha(c, pasta, linha)
    assert not caminho.origens[0].original_confere and not caminho.completa


def test_origem_sem_coleta_registrada_quebra_a_linhagem(ambiente):
    motor, pasta = ambiente
    with motor.begin() as c:
        c.execute(sa.text("delete from coletas"))
    linha = pd.read_parquet(pasta / "2022.parquet").iloc[0]
    with motor.connect() as c:
        caminho = linhagem_da_linha(c, pasta, linha)
    assert caminho.origens[0].baixado_em is None and not caminho.completa


def test_manifesto_antigo_sem_versao_nao_e_linhagem_completa(ambiente):
    """Os Parquet da série 1 foram gravados antes da exigência 13: a linhagem diz que falta."""
    motor, pasta = ambiente
    manifesto = pasta / "2022.json"
    dados = json.loads(manifesto.read_text(encoding="utf-8"))
    del dados["versao_do_codigo"]
    manifesto.write_text(json.dumps(dados), encoding="utf-8")
    linha = pd.read_parquet(pasta / "2022.parquet").iloc[0]
    with motor.connect() as c:
        caminho = linhagem_da_linha(c, pasta, linha)
    assert caminho.versao_do_codigo is None and not caminho.completa


def _com_a_tabela_conferida(pasta, sha256: str) -> None:
    manifesto = pasta / "2022.json"
    dados = json.loads(manifesto.read_text(encoding="utf-8"))
    dados["origens"].append(
        {"url": "base/conferidas/codigos_fora_do_fca.csv", "sha256": sha256}
    )
    manifesto.write_text(json.dumps(dados), encoding="utf-8")


def test_tabela_conferida_do_repositorio_e_origem_valida(ambiente):
    """Série 3, PR 8: a tabela conferida à mão não tem coleta; o elo é o arquivo no repositório com
    o mesmo SHA-256 (cada linha dela diz a fonte e quando foi conferida)."""
    from base.fca import CODIGOS_CONFERIDOS

    motor, pasta = ambiente
    _com_a_tabela_conferida(
        pasta, hashlib.sha256(CODIGOS_CONFERIDOS.read_bytes()).hexdigest()
    )
    linha = pd.read_parquet(pasta / "2022.parquet").iloc[0]
    with motor.connect() as c:
        caminho = linhagem_da_linha(c, pasta, linha)
    conferida = caminho.origens[-1]
    assert conferida.no_repositorio and conferida.original_confere
    assert caminho.completa


def test_tabela_conferida_mudada_depois_quebra_a_linhagem(ambiente):
    """A tabela mudou depois da carga: a base precisa ser remontada (a versão antiga está no Git)."""
    motor, pasta = ambiente
    _com_a_tabela_conferida(pasta, "0" * 64)
    linha = pd.read_parquet(pasta / "2022.parquet").iloc[0]
    with motor.connect() as c:
        caminho = linhagem_da_linha(c, pasta, linha)
    assert not caminho.origens[-1].original_confere and not caminho.completa


def test_endereco_que_sai_da_pasta_das_conferidas_nao_confere(ambiente):
    motor, pasta = ambiente
    manifesto = pasta / "2022.json"
    dados = json.loads(manifesto.read_text(encoding="utf-8"))
    alvo = "base/conferidas/../../README.md"
    conteudo = (Path(__file__).resolve().parent.parent / "README.md").read_bytes()
    dados["origens"].append(
        {"url": alvo, "sha256": hashlib.sha256(conteudo).hexdigest()}
    )
    manifesto.write_text(json.dumps(dados), encoding="utf-8")
    linha = pd.read_parquet(pasta / "2022.parquet").iloc[0]
    with motor.connect() as c:
        caminho = linhagem_da_linha(c, pasta, linha)
    assert not caminho.origens[-1].original_confere and not caminho.completa


# --- tabelas derivadas (série 4, PR 2): o painel dos fundos e a ligação dos bancos são montados de
# tabelas da base (CDA, FCA, cadastro do IF.data), não de originais. A linhagem segue o manifesto de
# cada tabela de entrada até os arquivos da CVM e as respostas do BC
PASTA_DE_AMOSTRAS = Path(__file__).parent / "arquivos"


@pytest.fixture
def base_inteira(tmp_path, monkeypatch):
    """CDA de 2025, FCA, IF.data de 06/2025, o painel dos fundos e a ligação dos bancos, montados
    pelas cargas de verdade a partir das amostras (os downloads são de mentira, com registro)."""
    from scripts import carga_bcb_credito, carga_cda, carga_fca
    from scripts import montar_painel_dos_fundos as painel
    from src.banco.coletas import com_registro

    url_do_banco = f"sqlite:///{(tmp_path / 'b.sqlite').as_posix()}"
    monkeypatch.setenv("TICKERLAB_DATABASE_URL", url_do_banco)
    monkeypatch.setenv(acervo.VARIAVEL_DA_PASTA, str(tmp_path / "acervo"))
    monkeypatch.setenv(vc.VARIAVEL, VERSAO)
    monkeypatch.setattr(carga_bcb_credito, "PAUSA_IFDATA", 0)
    migrar_para("head", url=url_do_banco)
    amostras = {
        p.name: p.read_bytes()
        for pasta in ("cvm/cda", "cvm/fca", "bcb/ifdata")
        for p in (PASTA_DE_AMOSTRAS / pasta).iterdir()
    }

    def baixar_falso(endereco: str) -> bytes | None:
        if (
            "olinda" in endereco
        ):  # IF.data: só o tipo 1, relatório 1, e o cadastro de 06/2025
            if "@AnoMes=202506&@TipoInstituicao=1&@Relatorio='1'" in endereco:
                return amostras["valores_202506_t1_r1.json"]
            if "IfDataCadastro(AnoMes=@AnoMes)?@AnoMes=202506" in endereco:
                return amostras["cadastro_202506.json"]
            return json.dumps({"@odata.context": "x", "value": []}).encode()
        return amostras.get(endereco.rsplit("/", 1)[-1])  # o resto: 404

    for modulo, nome, fonte in (
        (carga_cda, "baixar", carga_cda.FONTE),
        (carga_fca, "baixar", carga_fca.FONTE),
        (carga_bcb_credito, "baixar_ifdata", carga_bcb_credito.FONTE_IFDATA),
    ):
        monkeypatch.setattr(modulo, nome, com_registro(fonte, baixar_falso))
    raiz = tmp_path / "acervo" / "base"
    assert (
        carga_cda.main(
            ["--pasta", str(raiz / "cda"), "--desde", "2025", "--ate", "2025"]
        )
        == 0
    )
    assert (
        carga_fca.main(
            ["--pasta", str(raiz / "fca"), "--desde", "2018", "--ate", "2026"]
        )
        == 0
    )
    assert painel.main(["--base", str(raiz)]) == 0
    assert carga_bcb_credito.main(
        ["--pasta", str(raiz / "bcb"), "--fca", str(raiz / "fca"), "--so", "ifdata",
         "--desde", "2025", "--ate", "2025"]
    ) == 0  # fmt: skip
    motor = criar_engine(url_do_banco)
    yield motor, raiz
    motor.dispose()


DERIVADAS = (
    "fundos/painel_emissor/2025.parquet",
    "fundos/painel_empresa/2025.parquet",
    "fundos/cobertura.parquet",
    "fundos/buracos.parquet",
    "bcb/ifdata/ligacao_dos_bancos.parquet",
)


@pytest.mark.parametrize("derivada", DERIVADAS)
def test_linha_do_painel_volta_ao_arquivo_da_cvm(base_inteira, derivada):
    """De qualquer linha do painel dos fundos e da ligação dos bancos, chegar aos zips da CVM e às
    respostas do BC, com a coleta, passando pelo manifesto de cada tabela de entrada."""
    motor, raiz = base_inteira
    linha = pd.read_parquet(raiz / derivada).sample(1, random_state=7)
    assert len(linha) == 1
    with motor.connect() as c:
        caminho = linhagem_da_tabela(c, raiz / derivada)
    assert caminho.completa, derivada
    originais = {o.url for o in caminho.originais()}
    assert all(
        o.baixado_em is not None or o.no_repositorio for o in caminho.originais()
    )
    if derivada.startswith("fundos/"):
        assert any(u.endswith("cda_fi_202509.zip") for u in originais)
        assert any(u.endswith("fca_cia_aberta_2026.zip") for u in originais)
        assert "base/conferidas/emissores_antigos.csv" in originais
    else:
        assert any("IfDataCadastro" in u for u in originais)
        assert any(u.endswith("fca_cia_aberta_2026.zip") for u in originais)
    # nenhuma tabela da base sobra entre os originais: todas foram seguidas até o fim
    assert not [u for u in originais if u.endswith(".parquet")]


def test_entrada_mudada_depois_quebra_a_linhagem_da_derivada(base_inteira):
    """O painel foi montado com os emissores de antes: se a tabela de emissores for regravada (outra
    carga do FCA), o painel não confere mais até ser remontado."""
    from base.parquet import gravar_tabela

    motor, raiz = base_inteira
    emissores = raiz / "fca" / "emissores.parquet"
    manifesto = json.loads(emissores.with_suffix(".json").read_text(encoding="utf-8"))
    tabela = pd.read_parquet(emissores)
    gravar_tabela(
        tabela.iloc[1:],
        raiz / "fca" / "emissores",
        manifesto["origens"],
        ["emissor", "cnpj"],
    )
    with motor.connect() as c:
        assert linhagem_da_tabela(c, emissores).completa  # a entrada, sozinha, confere
        painel = linhagem_da_tabela(
            c, raiz / "fundos" / "painel_empresa" / "2025.parquet"
        )
    assert not painel.completa


def _tabela_que_le(destino: Path, entradas: list[Path], raiz: Path) -> None:
    from base.parquet import gravar_tabela

    origens = [
        {
            "url": e.relative_to(raiz).as_posix(),
            "sha256": json.loads(e.with_suffix(".json").read_text(encoding="utf-8"))[
                "sha256_da_tabela"
            ],
        }
        for e in entradas
    ]
    gravar_tabela(pd.DataFrame({"x": [1]}), destino, origens, ["x"])


def test_ciclo_ou_cadeia_longa_demais_e_erro(ambiente, tmp_path):
    from base.parquet import gravar_tabela

    motor, _ = ambiente
    raiz = tmp_path / "derivadas"
    # cadeia de 7 tabelas, cada uma lida da anterior
    gravar_tabela(
        pd.DataFrame({"x": [1]}),
        raiz / "t0",
        [{"url": URL, "sha256": "ab" * 32}],
        ["x"],
    )
    for i in range(1, 7):
        _tabela_que_le(raiz / f"t{i}", [raiz / f"t{i - 1}.parquet"], raiz)
    with motor.connect() as c, pytest.raises(ValueError, match="profundidade"):
        linhagem_da_tabela(c, raiz / "t6.parquet")
    # ciclo: a t0 passa a dizer que veio da t1
    _tabela_que_le(raiz / "t0", [raiz / "t1.parquet"], raiz)
    with motor.connect() as c, pytest.raises(ValueError, match="ciclo"):
        linhagem_da_tabela(c, raiz / "t1.parquet")


def test_painel_remontado_igual_depois_da_entrada_mudada_volta_a_conferir(base_inteira):
    """O caso do servidor de casa na série 4 (PR 1): os emissores ganharam uma coluna, o painel saiu
    com o mesmo conteúdo e ficava com o manifesto antigo; remontado, a linhagem confere de novo."""
    from base.parquet import gravar_tabela
    from scripts import montar_painel_dos_fundos as painel

    motor, raiz = base_inteira
    emissores = raiz / "fca" / "emissores.parquet"
    manifesto = json.loads(emissores.with_suffix(".json").read_text(encoding="utf-8"))
    tabela = pd.read_parquet(emissores).assign(coluna_nova=1)
    gravar_tabela(
        tabela, raiz / "fca" / "emissores", manifesto["origens"], ["emissor", "cnpj"]
    )
    alvo = raiz / "fundos" / "painel_empresa" / "2025.parquet"
    with motor.connect() as c:
        assert not linhagem_da_tabela(c, alvo).completa
    assert painel.main(["--base", str(raiz)]) == 0
    assert not list(
        alvo.parent.glob("2025.v*")
    )  # o conteúdo é o mesmo: sem versão nova
    with motor.connect() as c:
        assert linhagem_da_tabela(c, alvo).completa
