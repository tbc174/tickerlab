"""Montagem do `acervo_pessoa/` (linha 808): arquivos de mentira, sem internet. Todo nome, endereço,
telefone e e-mail aqui é inventado."""

import hashlib
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from base import receita_contato as rc
from base import receita_individuais as ri
from base import receita_pessoa as rp
from base.oposicao_na_tela import Opostos
from base.pessoas import chave as chaves
from base.pessoas import oposicoes
from scripts import montar_acervo_pessoa as montar
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
    + _estabelecimento("22333444", "0001", "81", email="52998224725@exemplo.com")
)
EMPRESAS_0 = (
    '"11222333";"EMPRESA DE MENTIRA LTDA";"2062";"49";"0";"01";""\n'
    '"22333444";"BELTRANO EXEMPLO 52998224725";"2135";"50";"0";"01";""\n'
)
MEMBROS = {
    "Socios": "K.SOCIOCSV",
    "Estabelecimentos": "K.ESTABELE",
    "Empresas": "K.EMPRECSV",
}
ZIPS = (
    ("Socios0.zip", SOCIOS_0),
    ("Socios1.zip", SOCIOS_1),
    ("Estabelecimentos0.zip", ESTABELECIMENTOS_0),
    ("Empresas0.zip", EMPRESAS_0),
)


def _acervo(tmp_path: Path) -> tuple[Path, Path]:
    """Um acervo de mentira: `base/cnpj/manifesto.json` e os ZIPs no bruto pelo SHA-256."""
    acervo = tmp_path / "acervo"
    cnpj, bruto = acervo / "base" / "cnpj", acervo / "bruto" / "rfb-cnpj"
    cnpj.mkdir(parents=True)
    (bruto / "2026").mkdir(parents=True)
    arquivos = {}
    for nome, texto in ZIPS:
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
    assert list(tabela["cnpj"]) == ["11222333000181", "22333444000181"]
    assert set(tabela.columns) == {*rc.COLUNAS, "mes_do_retrato"}
    assert set(tabela["mes_do_retrato"]) == {"2026-10"}
    assert list(tabela["email"].isna()) == [False, True]
    assert manifesto["tabelas"][montar.CONTATO] == {"linhas": 2, "empresas": 2}
    assert manifesto["descartes"][rc.NAO_ATIVO] == 1
    assert manifesto["descartes"][rc.EMAIL_COM_CARA_DE_CPF] == 1
    assert set(manifesto["descartes"]) == {*rp.MOTIVOS, *rc.MOTIVOS, *ri.MOTIVOS}


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
            "mes_do_retrato": "2026-10",
        }
    ]
    assert manifesto["tabelas"][montar.INDIVIDUAIS] == {"linhas": 1, "empresas": 1}
    assert manifesto["descartes"][ri.NAO_E_INDIVIDUAL] == 1
    texto = (destino / montar.MANIFESTO).read_text(encoding="utf-8")
    assert "BELTRANO" not in texto and "52998224725" not in texto


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
        tmp_path, _opostos(("52998224725", "BELTRANO EXEMPLO"))
    )
    assert _tabela(destino, montar.INDIVIDUAIS).empty
    assert manifesto["descartes"][ri.OPOSTO] == 1
    contato = _tabela(destino, montar.CONTATO)
    assert set(contato["cnpj_basico"]) == {"11222333"}  # a raiz 22333444 saiu
    assert manifesto["descartes"][rc.DE_OPOSTO] >= 1


def test_oposicao_do_titular_nao_tira_o_socio_de_outra_empresa_com_o_mesmo_nome(
    tmp_path,
):
    # BELTRANO EXEMPLO é sócio da raiz 22333444 (miolo 123456) e titular de outra (CPF 52998224725)
    destino, _ = _montar_com(tmp_path, _opostos(("52998224725", "BELTRANO EXEMPLO")))
    assert "BELTRANO EXEMPLO" in set(_tabela(destino)["nome_socio"])


def test_manifesto_so_leva_contagem_nunca_id_nome_nem_cpf(tmp_path):
    opostos = _opostos(
        ("***123456**", "FULANA EXEMPLO"), ("52998224725", "BELTRANO EXEMPLO")
    )
    destino, _ = _montar_com(tmp_path, opostos)
    texto = (destino / montar.MANIFESTO).read_text(encoding="utf-8")
    assert not any(i in texto for i in opostos.ids)
    assert (
        "FULANA" not in texto and "52998224725" not in texto and "123456" not in texto
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
    proibidos = [b"123456", b"52998224725", b"FULANA", *(i.encode() for i in ids)]
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
