"""Montagem do `acervo_pessoa/` (linha 808): arquivos de mentira, sem internet. Todo nome, endereço,
telefone e e-mail aqui é inventado."""

import hashlib
import io
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from base import oposicao_na_tela
from base import receita_contato as rc
from base import receita_individuais as ri
from base import receita_pessoa as rp
from base.oposicao_na_tela import Opostos
from base.pessoas import chave as chaves
from base.pessoas import oposicoes
from scripts import montar_acervo_pessoa as montar
from scripts import oposicao_do_titular as cli
from tests.test_receita_contato import _linha as _estabelecimento

AGORA = datetime(2026, 11, 10, tzinfo=UTC)
CHAVE = b"chave-de-mentira-so-para-teste-0123456789"
SEM_OPOSTOS = Opostos(frozenset(), CHAVE)
SEM_REP = '"***000000**";"";"00"'


def _linha(raiz, tipo, nome, faixa="5", representante=SEM_REP):
    return (
        f'"{raiz}";"{tipo}";"{nome}";"***123456**";"49";"20200131";"";'
        f'{representante};"{faixa}"\n'
    )


SOCIOS_0 = (
    _linha("11222333", "2", "FULANA EXEMPLO")
    + _linha("11222333", "2", "FULANA EXEMPLO")  # repetida: sai uma só
    + _linha("11222333", "2", "CRIANCA EXEMPLO", faixa="1")
    + _linha("11222333", "1", "HOLDING DE MENTIRA LTDA", faixa="0")
)
SOCIOS_1 = _linha("22333444", "2", "BELTRANO EXEMPLO") + _linha(
    "22333444", "2", "REPRESENTADO EXEMPLO", representante='"***654321**";"MAE";"35"'
)
ESTABELECIMENTOS_0 = (
    _estabelecimento("11222333", "0001", "81")
    + _estabelecimento("11222333", "0001", "81")  # repetido: sai um só
    + _estabelecimento("11222333", "0002", "62", matriz="2", situacao_cadastral="08")
    + _estabelecimento("22333444", "0001", "81", email="88800000127@exemplo.com")
)
EMPRESAS_0 = (
    '"11222333";"EMPRESA DE MENTIRA LTDA";"2062";"49";"0";"01";""\n'
    '"22333444";"BELTRANO EXEMPLO 88800000127";"2135";"50";"0";"01";""\n'
)
SIMPLES_0 = '"99888777";"S";"20200101";"00000000";"N";"00000000";"00000000"\n'
MEMBROS = {
    "Socios": "K.SOCIOCSV",
    "Estabelecimentos": "K.ESTABELE",
    "Empresas": "K.EMPRECSV",
    "Simples": "F.K.SIMPLES",
}
ZIPS = (
    ("Socios0.zip", SOCIOS_0),
    ("Socios1.zip", SOCIOS_1),
    ("Estabelecimentos0.zip", ESTABELECIMENTOS_0),
    ("Empresas0.zip", EMPRESAS_0),
    ("Simples.zip", SIMPLES_0),
)


def _acervo(tmp_path: Path, zips=ZIPS) -> tuple[Path, Path]:
    """Um acervo de mentira: `base/cnpj/manifesto.json` e os ZIPs no bruto pelo SHA-256."""
    acervo = tmp_path / "acervo"
    cnpj, bruto = acervo / "base" / "cnpj", acervo / "bruto" / "rfb-cnpj"
    cnpj.mkdir(parents=True)
    (bruto / "2026").mkdir(parents=True)
    arquivos = {}
    for nome, texto in zips:
        provisorio = tmp_path / nome
        with zipfile.ZipFile(provisorio, "w") as arquivo:
            membro = next(m for comeco, m in MEMBROS.items() if nome.startswith(comeco))
            arquivo.writestr(membro, texto.encode("latin-1"))
        sha = hashlib.sha256(provisorio.read_bytes()).hexdigest()
        provisorio.rename(bruto / "2026" / f"{sha}.zip")
        arquivos[nome] = sha
    meses = {"2026-09": {"arquivos": {}}, "2026-10": {"arquivos": arquivos}}
    (cnpj / "manifesto.json").write_text(json.dumps({"meses": meses}))
    return cnpj, bruto


def _tabela(destino: Path, nome: str = montar.SOCIOS) -> pd.DataFrame:
    partes = sorted((destino / nome).glob("*.parquet"))
    if not partes:
        return pd.DataFrame()
    return pd.concat([pd.read_parquet(p) for p in partes], ignore_index=True)


def test_monta_so_os_adultos_e_conta_os_descartes(tmp_path):
    cnpj, bruto = _acervo(tmp_path)
    destino = tmp_path / "fora" / "acervo_pessoa"
    manifesto = montar.carregar(cnpj, bruto, destino, AGORA, SEM_OPOSTOS)

    tabela = _tabela(destino)
    assert sorted(tabela["nome_socio"]) == ["BELTRANO EXEMPLO", "FULANA EXEMPLO"]
    assert set(tabela.columns) == {
        "cnpj_basico",
        "nome_socio",
        "qualificacao",
        "data_entrada",
        "id_pessoa",
        "mes_do_retrato",
    }
    assert set(tabela["mes_do_retrato"]) == {"2026-10"}
    assert sorted(p.name for p in (destino / montar.SOCIOS).iterdir()) == [
        "11.parquet",
        "22.parquet",
    ]
    assert manifesto["tabelas"][montar.SOCIOS] == {"linhas": 2, "empresas": 2}
    assert manifesto["descartes"][rp.MENOR_PELA_FAIXA] == 1
    assert manifesto["descartes"][rp.COM_REPRESENTANTE] == 1
    assert manifesto["descartes"][rp.NAO_E_PESSOA_FISICA] == 1
    assert not (destino / montar.TRABALHO).exists()


def test_monta_o_contato_so_dos_estabelecimentos_ativos(tmp_path):
    cnpj, bruto = _acervo(tmp_path)
    destino = tmp_path / "fora" / "acervo_pessoa"
    manifesto = montar.carregar(cnpj, bruto, destino, AGORA, SEM_OPOSTOS)

    tabela = _tabela(destino, montar.CONTATO)
    # 22333444 é empresário individual: o estabelecimento dele não sai (ADR 0128, Emenda 4)
    assert list(tabela["cnpj"]) == ["11222333000181"]
    assert set(tabela.columns) == {*rc.COLUNAS, "mes_do_retrato"}
    assert set(tabela["mes_do_retrato"]) == {"2026-10"}
    assert manifesto["tabelas"][montar.CONTATO] == {"linhas": 1, "empresas": 1}
    assert manifesto["descartes"][rc.NAO_ATIVO] == 1
    assert manifesto["descartes"][rc.CONTATO_DE_PESSOA] == 1
    assert set(manifesto["descartes"]) == {*rp.CONTAGENS, *rc.MOTIVOS, *ri.CONTAGENS}


def test_sem_os_zips_de_uma_tabela_nada_e_montado(tmp_path):
    cnpj, bruto = _acervo(tmp_path)
    manifesto = json.loads((cnpj / "manifesto.json").read_text())
    del manifesto["meses"]["2026-10"]["arquivos"]["Estabelecimentos0.zip"]
    (cnpj / "manifesto.json").write_text(json.dumps(manifesto))
    destino = tmp_path / "fora" / "acervo_pessoa"
    with pytest.raises(montar.ZipAusenteError):
        montar.carregar(cnpj, bruto, destino, AGORA, SEM_OPOSTOS)
    assert not destino.exists()


def test_manifesto_gravado_so_tem_numeros_e_sha(tmp_path):
    cnpj, bruto = _acervo(tmp_path)
    destino = tmp_path / "fora" / "acervo_pessoa"
    montar.carregar(cnpj, bruto, destino, AGORA, SEM_OPOSTOS)
    texto = (destino / montar.MANIFESTO).read_text(encoding="utf-8")
    assert "EXEMPLO" not in texto.upper() and "***" not in texto
    assert "3000" not in texto  # nem telefone
    assert json.loads(texto)["mes_do_retrato"] == "2026-10"


def test_remontar_troca_a_tabela_inteira(tmp_path):
    cnpj, bruto = _acervo(tmp_path)
    destino = tmp_path / "fora" / "acervo_pessoa"
    montar.carregar(cnpj, bruto, destino, AGORA, SEM_OPOSTOS)
    velho = destino / montar.SOCIOS / "99.parquet"
    pd.DataFrame({"cnpj_basico": ["99000000"]}).to_parquet(velho)
    montar.carregar(cnpj, bruto, destino, AGORA, SEM_OPOSTOS)
    assert not velho.exists()
    assert len(_tabela(destino)) == 2


def test_troca_que_falha_devolve_a_tabela_anterior_inteira(tmp_path, monkeypatch):
    atual, pronta = tmp_path / "socios_pf", tmp_path / "pronta"
    atual.mkdir()
    (atual / "11.parquet").write_bytes(b"anterior")
    pronta.mkdir()
    renomear = Path.rename

    def falha_ao_entrar(origem, alvo):
        if origem == pronta:
            raise OSError("disco")
        return renomear(origem, alvo)

    monkeypatch.setattr(Path, "rename", falha_ao_entrar)
    with pytest.raises(OSError, match="disco"):
        montar._trocar(pronta, atual)
    assert (atual / "11.parquet").read_bytes() == b"anterior"
    assert not (tmp_path / ("socios_pf" + montar.ANTIGA)).exists()


@pytest.mark.parametrize("pasta", ["base/acervo_pessoa", "acervo_pessoa"])
def test_destino_dentro_do_acervo_e_recusado(tmp_path, pasta):
    cnpj, bruto = _acervo(tmp_path)
    destino = tmp_path / "acervo" / pasta
    with pytest.raises(montar.DestinoRecusadoError):
        montar.carregar(cnpj, bruto, destino, AGORA, SEM_OPOSTOS)
    assert not destino.exists()


def test_destino_com_outro_nome_e_recusado(tmp_path):
    cnpj, bruto = _acervo(tmp_path)
    with pytest.raises(montar.DestinoRecusadoError):
        montar.carregar(
            cnpj, bruto, tmp_path / "fora" / "acervo_api", AGORA, SEM_OPOSTOS
        )


def test_zip_que_nao_esta_no_bruto_para_tudo(tmp_path):
    cnpj, bruto = _acervo(tmp_path)
    next((bruto / "2026").glob("*.zip")).unlink()
    destino = tmp_path / "fora" / "acervo_pessoa"
    with pytest.raises(montar.ZipAusenteError):
        montar.carregar(cnpj, bruto, destino, AGORA, SEM_OPOSTOS)
    assert not (destino / montar.SOCIOS).exists()


def test_zip_adulterado_para_tudo(tmp_path):
    cnpj, bruto = _acervo(tmp_path)
    guardado = next((bruto / "2026").glob("*.zip"))
    with zipfile.ZipFile(guardado, "w") as arquivo:
        arquivo.writestr("K.SOCIOCSV", _linha("11222333", "2", "OUTRO EXEMPLO"))
    destino = tmp_path / "fora" / "acervo_pessoa"
    with pytest.raises(montar.ZipAusenteError):
        montar.carregar(cnpj, bruto, destino, AGORA, SEM_OPOSTOS)
    assert not (destino / montar.SOCIOS).exists()


def _argumentos(tmp_path, cnpj, bruto, destino, restrita=True) -> list[str]:
    argumentos = ["--cnpj", str(cnpj), "--bruto", str(bruto), "--destino", str(destino)]
    if restrita:
        pasta = tmp_path / "restrita"
        (pasta / "pessoas").mkdir(parents=True, exist_ok=True)
        argumentos += ["--restrita", str(pasta)]
    return argumentos


@pytest.fixture(autouse=True)
def _chave(tmp_path, monkeypatch):
    arquivo = tmp_path / "pessoas.chave"
    arquivo.write_bytes(CHAVE)
    monkeypatch.setenv("TICKERLAB_PESSOAS_CHAVE", str(arquivo))


def test_ensaio_diz_o_mes_e_nao_grava(tmp_path, capsys):
    cnpj, bruto = _acervo(tmp_path)
    destino = tmp_path / "fora" / "acervo_pessoa"
    argumentos = _argumentos(tmp_path, cnpj, bruto, destino)
    assert montar.main([*argumentos, "--ensaio"]) == 0
    saida = capsys.readouterr().out
    assert "2026-10" in saida and "Socios0.zip" in saida
    assert "Estabelecimentos0.zip" in saida
    assert not destino.exists()


def test_main_monta_e_a_saida_nao_tem_nome(tmp_path, capsys):
    cnpj, bruto = _acervo(tmp_path)
    destino = tmp_path / "fora" / "acervo_pessoa"
    argumentos = _argumentos(tmp_path, cnpj, bruto, destino)
    assert montar.main(argumentos) == 0
    saida = capsys.readouterr().out
    assert '"linhas": 2' in saida and "EXEMPLO" not in saida.upper()


def test_main_com_destino_recusado_sai_com_falha(tmp_path, capsys):
    cnpj, bruto = _acervo(tmp_path)
    destino = tmp_path / "acervo" / "acervo_pessoa"
    argumentos = _argumentos(tmp_path, cnpj, bruto, destino)
    assert montar.main(argumentos) == 1
    assert capsys.readouterr().out.strip().splitlines()[-1].startswith("FALHAS:")


def test_falha_na_leitura_do_contato_deixa_socios_e_manifesto_como_estavam(
    tmp_path, monkeypatch
):
    cnpj, bruto = _acervo(tmp_path)
    destino = tmp_path / "fora" / "acervo_pessoa"
    montar.carregar(cnpj, bruto, destino, AGORA, SEM_OPOSTOS)
    antes = (destino / montar.MANIFESTO).read_text(encoding="utf-8")
    socios_antes = _tabela(destino).to_csv()

    def quebra(_arquivo, _contexto):
        raise RuntimeError("layout novo")

    tabelas = montar.TABELAS
    monkeypatch.setattr(
        montar, "TABELAS", (*tabelas[:2], tabelas[2]._replace(ler=quebra))
    )
    with pytest.raises(RuntimeError):
        montar.carregar(cnpj, bruto, destino, AGORA, SEM_OPOSTOS)
    assert (destino / montar.MANIFESTO).read_text(encoding="utf-8") == antes
    assert _tabela(destino).to_csv() == socios_antes
    assert not (destino / montar.TRABALHO).exists()


def test_monta_so_o_titular_do_empresario_individual_sem_cpf(tmp_path):
    cnpj, bruto = _acervo(tmp_path)
    destino = tmp_path / "fora" / "acervo_pessoa"
    manifesto = montar.carregar(cnpj, bruto, destino, AGORA, SEM_OPOSTOS)

    tabela = _tabela(destino, montar.INDIVIDUAIS)
    assert tabela.to_dict("records") == [
        {
            "cnpj_basico": "22333444",
            "titular": "BELTRANO EXEMPLO",
            "id_pessoa": next(iter(_opostos(("88800000127", "BELTRANO EXEMPLO")).ids)),
            "mes_do_retrato": "2026-10",
        }
    ]
    assert manifesto["tabelas"][montar.INDIVIDUAIS] == {"linhas": 1, "empresas": 1}
    assert manifesto["descartes"][ri.NAO_E_INDIVIDUAL] == 1
    texto = (destino / montar.MANIFESTO).read_text(encoding="utf-8")
    assert "BELTRANO" not in texto and "88800000127" not in texto


# ------------------------------------------------ oposição do titular (linha 829)


def _opostos(*pessoas: tuple[str, str]) -> Opostos:
    """Quem pediu a oposição: (CPF de mentira ou mascarado, nome)."""
    ids = set()
    for cpf, nome in pessoas:
        primeiro, ultimo = chaves.primeiro_e_ultimo(nome)
        ids.add(chaves.id_pessoa(cpf, primeiro, ultimo, CHAVE))
    return Opostos(frozenset(ids), CHAVE)


def _montar_com(tmp_path, opostos: Opostos) -> tuple[Path, dict]:
    cnpj, bruto = _acervo(tmp_path)
    destino = tmp_path / "fora" / "acervo_pessoa"
    return destino, montar.carregar(cnpj, bruto, destino, AGORA, opostos)


def test_socio_que_se_opos_nao_entra_e_os_outros_ficam(tmp_path):
    destino, manifesto = _montar_com(
        tmp_path, _opostos(("***123456**", "FULANA EXEMPLO"))
    )
    assert set(_tabela(destino)["nome_socio"]) == {"BELTRANO EXEMPLO"}
    assert manifesto["descartes"][rp.OPOSTO] == 2  # a linha repetida conta as duas
    assert manifesto["oposicoes_aplicadas"] == 1


def test_homonimo_de_outro_cpf_nao_sai(tmp_path):
    destino, manifesto = _montar_com(
        tmp_path, _opostos(("***999999**", "FULANA EXEMPLO"))
    )
    assert set(_tabela(destino)["nome_socio"]) == {"FULANA EXEMPLO", "BELTRANO EXEMPLO"}
    assert manifesto["descartes"].get(rp.OPOSTO, 0) == 0


def test_sem_oposicoes_monta_o_mesmo(tmp_path):
    destino, manifesto = _montar_com(tmp_path, SEM_OPOSTOS)
    assert set(_tabela(destino)["nome_socio"]) == {"FULANA EXEMPLO", "BELTRANO EXEMPLO"}
    assert manifesto["oposicoes_aplicadas"] == 0


def test_titular_individual_que_se_opos_sai_e_o_contato_da_raiz_dele_tambem(tmp_path):
    destino, manifesto = _montar_com(
        tmp_path, _opostos(("88800000127", "BELTRANO EXEMPLO"))
    )
    assert _tabela(destino, montar.INDIVIDUAIS).empty
    assert manifesto["descartes"][ri.OPOSTO] == 1
    contato = _tabela(destino, montar.CONTATO)
    assert set(contato["cnpj_basico"]) == {"11222333"}  # a raiz 22333444 saiu
    # o contato do empresário individual já sai pelo corte, antes de chegar à oposição
    assert manifesto["descartes"][rc.CONTATO_DE_PESSOA] == 1


def test_oposicao_do_titular_nao_tira_o_socio_de_outra_empresa_com_o_mesmo_nome(
    tmp_path,
):
    # BELTRANO EXEMPLO é sócio da raiz 22333444 (miolo 123456) e titular de outra (CPF 88800000127)
    destino, _ = _montar_com(tmp_path, _opostos(("88800000127", "BELTRANO EXEMPLO")))
    assert "BELTRANO EXEMPLO" in set(_tabela(destino)["nome_socio"])


def test_manifesto_so_leva_contagem_nunca_id_nome_nem_cpf(tmp_path):
    opostos = _opostos(
        ("***123456**", "FULANA EXEMPLO"), ("88800000127", "BELTRANO EXEMPLO")
    )
    destino, _ = _montar_com(tmp_path, opostos)
    texto = (destino / montar.MANIFESTO).read_text(encoding="utf-8")
    assert not any(i in texto for i in opostos.ids)
    assert (
        "FULANA" not in texto and "88800000127" not in texto and "123456" not in texto
    )


def test_sem_restrita_nada_e_montado(tmp_path, capsys):
    cnpj, bruto = _acervo(tmp_path)
    destino = tmp_path / "fora" / "acervo_pessoa"
    argumentos = _argumentos(tmp_path, cnpj, bruto, destino, restrita=False)
    assert montar.main(argumentos) == 1
    assert "FALHAS:" in capsys.readouterr().out
    assert not destino.exists()


def test_pasta_restrita_ausente_nada_e_montado(tmp_path, capsys):
    cnpj, bruto = _acervo(tmp_path)
    destino = tmp_path / "fora" / "acervo_pessoa"
    argumentos = _argumentos(tmp_path, cnpj, bruto, destino, restrita=False)
    assert montar.main([*argumentos, "--restrita", str(tmp_path / "nao-existe")]) == 1
    assert "SemOposicoesError" in capsys.readouterr().out
    assert not destino.exists()


def test_sem_a_chave_nada_e_montado(tmp_path, monkeypatch, capsys):
    cnpj, bruto = _acervo(tmp_path)
    destino = tmp_path / "fora" / "acervo_pessoa"
    monkeypatch.setenv("TICKERLAB_PESSOAS_CHAVE", str(tmp_path / "sem-chave"))
    assert montar.main(_argumentos(tmp_path, cnpj, bruto, destino)) == 1
    assert "ErroSemChave" in capsys.readouterr().out
    assert not destino.exists()


def test_main_com_oposicao_registrada_tira_o_oposto(tmp_path, capsys):
    cnpj, bruto = _acervo(tmp_path)
    destino = tmp_path / "fora" / "acervo_pessoa"
    argumentos = _argumentos(tmp_path, cnpj, bruto, destino)
    ids = list(_opostos(("***123456**", "FULANA EXEMPLO")).ids)
    oposicoes.registrar(tmp_path / "restrita", ids, AGORA.date())
    assert montar.main(argumentos) == 0
    assert set(_tabela(destino)["nome_socio"]) == {"BELTRANO EXEMPLO"}
    assert "FULANA" not in capsys.readouterr().out


def test_cpf_e_id_nunca_vao_a_arquivo_log_nem_saida(tmp_path, caplog, capsys):
    cnpj, bruto = _acervo(tmp_path)
    destino = tmp_path / "fora" / "acervo_pessoa"
    ids = _opostos(("***123456**", "FULANA EXEMPLO")).ids
    argumentos = _argumentos(tmp_path, cnpj, bruto, destino)
    oposicoes.registrar(tmp_path / "restrita", list(ids), AGORA.date())
    with caplog.at_level("INFO"):
        assert montar.main(argumentos) == 0
    proibidos = [b"123456", b"88800000127", b"FULANA", *(i.encode() for i in ids)]
    for arquivo in destino.rglob("*"):
        if arquivo.is_file():
            conteudo = arquivo.read_bytes()
            assert not any(p in conteudo for p in proibidos), arquivo.name
    texto = caplog.text + capsys.readouterr().out
    assert not any(p.decode() in texto for p in proibidos)


def test_pasta_que_existe_mas_nao_e_a_restrita_de_pessoas_nada_e_montado(
    tmp_path, capsys
):
    cnpj, bruto = _acervo(tmp_path)
    destino = tmp_path / "fora" / "acervo_pessoa"
    errada = tmp_path / "pasta-mae"
    errada.mkdir()
    argumentos = _argumentos(tmp_path, cnpj, bruto, destino, restrita=False)
    assert montar.main([*argumentos, "--restrita", str(errada)]) == 1
    assert "SemOposicoesError" in capsys.readouterr().out
    assert not destino.exists()


# ------------------------- a oposição de depois vale no dia, sem esperar a montagem do mês


def _montado_sem_oposicao(tmp_path) -> Path:
    destino, _ = _montar_com(tmp_path, SEM_OPOSTOS)
    return destino


def test_aplicar_no_acervo_tira_o_socio_e_e_idempotente(tmp_path):
    destino = _montado_sem_oposicao(tmp_path)
    ids = set(_opostos(("***123456**", "FULANA EXEMPLO")).ids)
    assert oposicao_na_tela.aplicar_no_acervo(destino, ids) == 1
    assert set(_tabela(destino)["nome_socio"]) == {"BELTRANO EXEMPLO"}
    assert oposicao_na_tela.aplicar_no_acervo(destino, ids) == 0
    assert oposicao_na_tela.aplicar_no_acervo(destino, set()) == 0


def test_aplicar_no_acervo_tira_o_titular_e_o_contato_da_raiz(tmp_path):
    destino = _montado_sem_oposicao(tmp_path)
    ids = set(_opostos(("88800000127", "BELTRANO EXEMPLO")).ids)
    # só o titular: o contato do empresário individual já não entra no acervo (ADR 0128, Emenda 4)
    assert oposicao_na_tela.aplicar_no_acervo(destino, ids) == 1
    assert _tabela(destino, montar.INDIVIDUAIS).empty
    assert set(_tabela(destino, montar.CONTATO)["cnpj_basico"]) == {"11222333"}
    assert "BELTRANO EXEMPLO" in set(
        _tabela(destino)["nome_socio"]
    )  # o sócio é outro id


def test_pedido_do_dono_de_mei_acha_pela_raiz_e_pelo_nome_e_tira_do_acervo(
    tmp_path, capsys, monkeypatch
):
    destino = _montado_sem_oposicao(tmp_path)
    restrita = tmp_path / "restrita"
    (restrita / "pessoas").mkdir(parents=True)  # sem sócios: o MEI não está no quadro
    monkeypatch.setattr("sys.stdin", io.StringIO("Beltrano Exemplo\n"))
    saida = cli.main(
        [
            "pedido",
            "--base", str(tmp_path / "base"),
            "--restrita", str(restrita),
            "--cnpj", "22333444000181",
            "--acervo-pessoa", str(destino),
            "--pedido-em", "2026-11-11",
            "--hoje", "2026-11-11",
        ]
    )  # fmt: skip
    texto = capsys.readouterr().out
    assert saida == 0 and "BELTRANO" not in texto.upper() and "88800000127" not in texto
    assert _tabela(destino, montar.INDIVIDUAIS).empty
    assert set(_tabela(destino, montar.CONTATO)["cnpj_basico"]) == {"11222333"}
    assert len(oposicoes.ids_opostos(restrita)) == 1


def test_atender_com_acervo_aplica_as_oposicoes_ja_registradas(tmp_path, capsys):
    destino = _montado_sem_oposicao(tmp_path)
    restrita = tmp_path / "restrita"
    (restrita / "pessoas").mkdir(parents=True)
    oposicoes.registrar(
        restrita, list(_opostos(("***123456**", "FULANA EXEMPLO")).ids), AGORA.date()
    )
    saida = cli.main(
        ["atender", "--base", str(tmp_path / "base"), "--restrita", str(restrita),
         "--acervo-pessoa", str(destino), "--hoje", "2026-11-11"]
    )  # fmt: skip
    assert saida == 0
    assert set(_tabela(destino)["nome_socio"]) == {"BELTRANO EXEMPLO"}


def test_pedido_sem_acervo_nao_acha_o_dono_de_mei(tmp_path, capsys, monkeypatch):
    restrita = tmp_path / "restrita"
    (restrita / "pessoas").mkdir(parents=True)
    monkeypatch.setattr("sys.stdin", io.StringIO("BELTRANO EXEMPLO\n"))
    saida = cli.main(
        ["pedido", "--base", str(tmp_path / "base"), "--restrita", str(restrita),
         "--cnpj", "22333444000181"]
    )  # fmt: skip
    assert saida == 1 and cli.NINGUEM in capsys.readouterr().out


# ---------------------------------------- MEI sem CPF na razão, acervo errado, acesso e conferência (829)

RAIZ_MEI = "33444555"
CNPJ_MEI = RAIZ_MEI + "000199"


def _acervo_com_mei_sem_cpf(tmp_path) -> Path:
    """Um `acervo_pessoa/` pronto: um sócio, um MEI cuja razão não traz CPF (id pela raiz) e o contato dele."""
    destino = tmp_path / "acervo_pessoa"
    for tabela in (montar.SOCIOS, montar.INDIVIDUAIS, montar.CONTATO):
        (destino / tabela).mkdir(parents=True)
    pd.DataFrame(
        {"nome_socio": ["FULANA EXEMPLO"], "id_pessoa": ["a" * 32]}
    ).to_parquet(destino / montar.SOCIOS / "p0.parquet")
    pd.DataFrame(
        {
            "cnpj_basico": [RAIZ_MEI],
            "titular": ["GICLANA EXEMPLO"],
            "id_pessoa": [chaves.id_da_raiz(RAIZ_MEI, CHAVE)],
        }
    ).to_parquet(destino / montar.INDIVIDUAIS / "p0.parquet")
    pd.DataFrame(
        {"cnpj_basico": [RAIZ_MEI, "11222333"], "email": ["x@exemplo.com"] * 2}
    ).to_parquet(destino / montar.CONTATO / "p0.parquet")
    return destino


def _restrita(tmp_path) -> Path:
    restrita = tmp_path / "restrita"
    (restrita / "pessoas").mkdir(parents=True)
    return restrita


def _pedido_do_mei(tmp_path, destino, monkeypatch) -> int:
    monkeypatch.setattr("sys.stdin", io.StringIO("Giclana Exemplo\n"))
    return cli.main(
        ["pedido", "--base", str(tmp_path / "base"), "--restrita", str(_restrita(tmp_path)),
         "--cnpj", CNPJ_MEI, "--acervo-pessoa", str(destino),
         "--pedido-em", "2026-11-11", "--hoje", "2026-11-11"]
    )  # fmt: skip


def test_pedido_do_mei_cuja_razao_nao_tem_cpf_tira_titular_e_contato(
    tmp_path, capsys, monkeypatch
):
    destino = _acervo_com_mei_sem_cpf(tmp_path)
    assert _pedido_do_mei(tmp_path, destino, monkeypatch) == 0
    assert "GICLANA" not in capsys.readouterr().out.upper()
    assert _tabela(destino, montar.INDIVIDUAIS).empty
    assert set(_tabela(destino, montar.CONTATO)["cnpj_basico"]) == {"11222333"}


def test_acervo_pessoa_errado_recusa_antes_de_registrar(tmp_path, capsys, monkeypatch):
    saida = _pedido_do_mei(tmp_path, tmp_path / "caminho-errado", monkeypatch)
    assert saida == 2 and "acervo_pessoa" in capsys.readouterr().err
    assert not oposicoes.ids_opostos(tmp_path / "restrita")  # nada foi registrado


def test_acervo_montado_antes_do_id_pessoa_recusa(tmp_path, capsys, monkeypatch):
    destino = _acervo_com_mei_sem_cpf(tmp_path)
    antigo = pd.read_parquet(destino / montar.SOCIOS / "p0.parquet").drop(
        columns="id_pessoa"
    )
    antigo.to_parquet(destino / montar.SOCIOS / "p0.parquet")
    assert _pedido_do_mei(tmp_path, destino, monkeypatch) == 2
    assert "monte de novo" in capsys.readouterr().err
    assert not oposicoes.ids_opostos(tmp_path / "restrita")


def test_acesso_do_mei_diz_que_a_tela_mostra_titular_e_contato_sem_imprimir_nome(
    tmp_path, capsys, monkeypatch
):
    destino = _acervo_com_mei_sem_cpf(tmp_path)
    monkeypatch.setattr("sys.stdin", io.StringIO("Giclana Exemplo\n"))
    saida = cli.main(
        ["acesso", "--restrita", str(_restrita(tmp_path)), "--cnpj", CNPJ_MEI,
         "--acervo-pessoa", str(destino)]
    )  # fmt: skip
    texto = capsys.readouterr().out
    assert saida == 0 and "empresário individual" in texto and "contato" in texto
    assert (
        "GICLANA" not in texto.upper()
        and chaves.id_da_raiz(RAIZ_MEI, CHAVE) not in texto
    )


def test_conferir_acusa_linha_de_quem_se_opos_que_seguiu_no_acervo(tmp_path, capsys):
    destino = _acervo_com_mei_sem_cpf(tmp_path)
    restrita = _restrita(tmp_path)
    oposicoes.registrar(restrita, [chaves.id_da_raiz(RAIZ_MEI, CHAVE)], AGORA.date())
    argumentos = ["conferir", "--restrita", str(restrita), "--acervo-pessoa", str(destino),
                  "--hoje", "2026-11-11"]  # fmt: skip
    assert cli.main(argumentos) == 1 and "FALHAS" in capsys.readouterr().out
    oposicao_na_tela.aplicar_no_acervo(destino, oposicoes.ids_opostos(restrita))
    assert cli.main(argumentos) == 0


# --------------------- sem contato de MEI, empresário individual e unipessoal (ADR 0128, Emenda 4)

# 33444555: MEI pelo Simples, com natureza de sociedade; 44555666: antiga EIRELI; 55666777: um sócio pessoa
# física só; 66777888: um sócio do exterior só; 77888999: dois sócios (fica).
SOCIOS_DO_CORTE = (
    _linha("55666777", "2", "CICRANA EXEMPLO")
    + _linha("66777888", "3", "FOREIGN EXAMPLE", faixa="0")
    + _linha("77888999", "2", "FULANO EXEMPLO")
    + _linha("77888999", "2", "OUTRA EXEMPLO").replace("***123456**", "***654321**")
)
EMPRESAS_DO_CORTE = (
    '"33444555";"LOJA DE MENTIRA LTDA";"2062";"49";"0";"01";""\n'
    '"44555666";"EIRELI DE MENTIRA";"2305";"65";"0";"01";""\n'
)
SIMPLES_DO_CORTE = (
    SIMPLES_0 + '"33444555";"S";"20200101";"00000000";"S";"20200101";"00000000"\n'
)
RAIZES_DO_CORTE = ("33444555", "44555666", "55666777", "66777888", "77888999")
ESTABELECIMENTOS_DO_CORTE = ESTABELECIMENTOS_0 + "".join(
    _estabelecimento(raiz, "0001", "81") for raiz in RAIZES_DO_CORTE
)
ZIPS_DO_CORTE = (
    ("Socios0.zip", SOCIOS_0),
    ("Socios1.zip", SOCIOS_1 + SOCIOS_DO_CORTE),
    ("Estabelecimentos0.zip", ESTABELECIMENTOS_DO_CORTE),
    ("Empresas0.zip", EMPRESAS_0 + EMPRESAS_DO_CORTE),
    ("Simples.zip", SIMPLES_DO_CORTE),
)


def _montar_o_corte(tmp_path) -> tuple[Path, dict]:
    cnpj, bruto = _acervo(tmp_path, ZIPS_DO_CORTE)
    destino = tmp_path / "fora" / "acervo_pessoa"
    return destino, montar.carregar(cnpj, bruto, destino, AGORA, SEM_OPOSTOS)


def test_montagem_corta_o_contato_inteiro_de_mei_eireli_individual_e_unipessoal(
    tmp_path,
):
    destino, manifesto = _montar_o_corte(tmp_path)
    contato = _tabela(destino, montar.CONTATO)
    assert sorted(contato["cnpj_basico"]) == ["11222333", "77888999"]
    da_empresa = contato[contato["cnpj_basico"] == "11222333"].iloc[0]
    assert da_empresa["logradouro"] == "DOS EXEMPLOS" and da_empresa["cep"]
    # 22333444 (individual), 33444555 (MEI), 44555666 (EIRELI), 55666777 e 66777888 (um sócio só)
    assert manifesto["descartes"][rc.CONTATO_DE_PESSOA] == 5
    assert manifesto[montar.CORTES] == {
        "mei_do_simples": 1,
        "eireli": 1,
        "quadro_de_um_socio": 2,
    }


def test_o_corte_do_contato_nao_mexe_em_socios_nem_titulares(tmp_path):
    destino, _ = _montar_o_corte(tmp_path)
    nomes = set(_tabela(destino)["nome_socio"])
    assert {"CICRANA EXEMPLO", "FULANO EXEMPLO", "OUTRA EXEMPLO"} <= nomes
    assert list(_tabela(destino, montar.INDIVIDUAIS)["cnpj_basico"]) == ["22333444"]


def test_manifesto_traz_a_marca_do_corte_que_a_tela_exige(tmp_path):
    destino, _ = _montar_com(tmp_path, SEM_OPOSTOS)
    manifesto = json.loads((destino / montar.MANIFESTO).read_text(encoding="utf-8"))
    assert rc.CONTATO_DE_PESSOA in manifesto["descartes"]
    assert "endereco_de_individual_cortado" not in manifesto["descartes"]
    assert set(manifesto[montar.CORTES]) == {
        "mei_do_simples",
        "eireli",
        "quadro_de_um_socio",
    }


def test_sem_o_simples_do_mes_nada_e_montado(tmp_path):
    """Sem o `Simples.zip` o MEI com natureza de sociedade passaria com o contato: a montagem para."""
    cnpj, bruto = _acervo(tmp_path)
    manifesto = json.loads((cnpj / "manifesto.json").read_text())
    del manifesto["meses"]["2026-10"]["arquivos"]["Simples.zip"]
    (cnpj / "manifesto.json").write_text(json.dumps(manifesto))
    destino = tmp_path / "fora" / "acervo_pessoa"
    with pytest.raises(montar.ZipAusenteError):
        montar.carregar(cnpj, bruto, destino, AGORA, SEM_OPOSTOS)
    assert not destino.exists()


# ------------------------------------- prova por máquina antes de levar a pasta (só contagens)


def _prova(saida: str) -> dict:
    return json.loads(saida.strip().splitlines()[-2])


def test_conferir_o_acervo_limpo_da_zero_em_tudo(tmp_path, capsys):
    destino, _ = _montar_o_corte(tmp_path)
    assert montar.main(["--conferir", str(destino)]) == 0
    saida = capsys.readouterr().out
    prova = _prova(saida)
    assert (
        prova[montar.SOCIOS]["linhas"] > 0 and prova[montar.INDIVIDUAIS]["linhas"] == 1
    )
    for tabela in (montar.SOCIOS, montar.INDIVIDUAIS):
        achados = {
            k: v for k, v in prova[tabela].items() if k not in ("linhas", "arquivos")
        }
        assert achados == dict.fromkeys(montar.ACHADOS, 0)
    assert prova[montar.MANIFESTO] == dict.fromkeys(montar.ACHADOS_DO_MANIFESTO, 0)
    assert "FALHAS" not in saida and "EXEMPLO" not in saida.upper()


@pytest.mark.parametrize(
    ("coluna", "valor", "achado"),
    [
        ("nome_socio", "FULANA 888.000.001-27", "onze_digitos"),
        ("nome_socio", "FULANA ***123456**", "cpf_ou_email"),
        ("nome_socio", "FULANA fulana@exemplo.com", "cpf_ou_email"),
        ("nome_socio", "FULANA (11) 3000-1000", "telefone"),
        ("nome_socio", "FULANA 01001-000", "cep"),
        ("qualificacao", "30", "menor_ou_representante"),
        ("qualificacao", "35", "menor_ou_representante"),
        ("cnpj_basico", "1122233", "cnpj_basico_fora_do_formato"),
        ("id_pessoa", "88800000127", "id_pessoa_fora_do_formato"),
        ("logradouro", "RUA DOS EXEMPLOS", "colunas_fora_do_esperado"),
    ],
)
def test_conferir_acusa_o_que_escapou_e_so_conta(
    tmp_path, capsys, coluna, valor, achado
):
    destino, _ = _montar_o_corte(tmp_path)
    arquivo = min((destino / montar.SOCIOS).glob("*.parquet"))
    tabela = pd.read_parquet(arquivo)
    tabela.loc[0, coluna] = valor
    tabela.to_parquet(arquivo, index=False)
    assert montar.main(["--conferir", str(destino)]) == 1
    saida = capsys.readouterr().out
    assert _prova(saida)[montar.SOCIOS][achado] >= 1
    assert "FALHAS" in saida and "EXEMPLO" not in saida.upper() and valor not in saida


def test_conferir_acusa_pessoa_no_manifesto(tmp_path, capsys):
    destino, _ = _montar_o_corte(tmp_path)
    caminho = destino / montar.MANIFESTO
    manifesto = json.loads(caminho.read_text(encoding="utf-8"))
    manifesto["anotacao"] = "fulana@exemplo.com"
    manifesto["origens"]["Socios0.zip"] = "88800000127"
    caminho.write_text(json.dumps(manifesto), encoding="utf-8")
    assert montar.main(["--conferir", str(destino)]) == 1
    saida = capsys.readouterr().out
    assert _prova(saida)[montar.MANIFESTO] == {
        "textos_com_cara_de_pessoa": 1,
        "origens_fora_do_formato": 1,
        "sem_a_marca_do_corte": 0,
        "corte_do_contato_vazio": 0,
    }
    assert "fulana" not in saida and "88800000127" not in saida


@pytest.mark.parametrize(
    ("estragar", "achado", "quantos"),
    [
        (lambda m: m["descartes"].pop(rc.CONTATO_DE_PESSOA), "sem_a_marca_do_corte", 1),
        (lambda m: m.pop(montar.CORTES), "corte_do_contato_vazio", 2),
        (
            lambda m: m[montar.CORTES].update(mei_do_simples=0),
            "corte_do_contato_vazio",
            1,
        ),
        (
            lambda m: m[montar.CORTES].pop("quadro_de_um_socio"),
            "corte_do_contato_vazio",
            1,
        ),
    ],
)
def test_conferir_acusa_manifesto_sem_o_corte_do_contato(
    tmp_path, capsys, estragar, achado, quantos
):
    """Um corte que zerou sem erro (layout da Receita mudado) não pode passar como conferido."""
    destino, _ = _montar_o_corte(tmp_path)
    caminho = destino / montar.MANIFESTO
    manifesto = json.loads(caminho.read_text(encoding="utf-8"))
    estragar(manifesto)
    caminho.write_text(json.dumps(manifesto), encoding="utf-8")
    assert montar.main(["--conferir", str(destino)]) == 1
    saida = capsys.readouterr().out
    assert _prova(saida)[montar.MANIFESTO][achado] == quantos
    assert f"manifesto.json.{achado}" in saida


def test_conferir_aceita_eireli_zerada(tmp_path, capsys):
    """A EIRELI foi extinta: zero raiz nela é verdade possível, não defeito."""
    destino, _ = _montar_o_corte(tmp_path)
    caminho = destino / montar.MANIFESTO
    manifesto = json.loads(caminho.read_text(encoding="utf-8"))
    manifesto[montar.CORTES]["eireli"] = 0
    caminho.write_text(json.dumps(manifesto), encoding="utf-8")
    assert montar.main(["--conferir", str(destino)]) == 0


def test_conferir_pasta_sem_as_tabelas_falha(tmp_path, capsys):
    assert montar.main(["--conferir", str(tmp_path / "acervo_pessoa")]) == 1
    assert "FALHAS" in capsys.readouterr().out
