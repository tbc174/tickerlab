"""ZIPs minúsculos inventados: nenhum pedido ao INEP nem cadastro real."""

import hashlib
import io
import zipfile
from datetime import UTC, datetime

import pandas as pd
import pytest

from base import cnpj
from base import inep_censo_escolar as censo
from base.parquet import conferir_tabela
from scripts import carga_censo_escolar as carga


@pytest.fixture(autouse=True)
def _disco_de_teste(monkeypatch):
    monkeypatch.setattr(
        carga, "espaco_do_disco", lambda pasta: (1000 * 1024**3, 800 * 1024**3)
    )


def _cnpj(numero=1):
    base = f"{numero:08d}0001"
    return base + cnpj.digitos_verificadores(base)


def _escola(ano, codigo="99000001", **mudancas):
    return {
        "NU_ANO_CENSO": str(ano),
        "CO_ENTIDADE": codigo,
        "TP_DEPENDENCIA": "4",
        "TP_SITUACAO_FUNCIONAMENTO": "1",
        "NU_CNPJ_ESCOLA_PRIVADA": _cnpj(),
        "NU_CNPJ_MANTENEDORA": _cnpj(2),
        "SG_UF": "ZZ",
        "CO_MUNICIPIO": "9900000",
        "NO_MUNICIPIO": "Município inventado",
        "QT_MAT_BAS": "80",
        "QT_MAT_INF": "20",
        "QT_MAT_INF_CRE": "5",
        "QT_MAT_INF_PRE": "15",
        "QT_MAT_FUND": "50",
        "QT_MAT_FUND_AI": "30",
        "QT_MAT_FUND_AF": "20",
        "QT_MAT_MED": "10",
        "QT_MAT_PROF": "0",
        "QT_MAT_PROF_TEC": "0",
        "QT_MAT_EJA": "0",
        "QT_MAT_ESP": "4",
        "QT_MAT_INF_INT": "10",
        "QT_MAT_FUND_INT": "20",
        "QT_MAT_MED_INT": "0",
        "NO_GESTOR": "CAMPO PROIBIDO",
        "NU_TELEFONE": "CAMPO PROIBIDO",
        "DS_EMAIL": "CAMPO PROIBIDO",
        "DS_ENDERECO": "CAMPO PROIBIDO",
        **mudancas,
    }


def _zip(tmp_path, ano, linhas=None, *, corromper=False, sem_md5=False):
    linhas = linhas if linhas is not None else [_escola(ano)]
    tabela = pd.DataFrame(linhas)
    if ano == 2025:
        cadastro = [c for c in tabela if not c.startswith("QT_MAT_")]
        matriculas = [
            "NU_ANO_CENSO",
            "CO_ENTIDADE",
            *[c for c in tabela if c.startswith("QT_MAT_")],
        ]
        tabelas = {
            "Tabela_Escola_2025_V2.csv": tabela[cadastro],
            "Tabela_Matricula_2025_V2.csv": tabela[matriculas].iloc[::-1],
        }
    else:
        tabelas = {f"microdados_ed_basica_{ano}.csv": tabela}
    caminho = tmp_path / f"{ano}.zip"
    somas = []
    with zipfile.ZipFile(caminho, "w", zipfile.ZIP_DEFLATED) as pacote:
        for nome, dados in tabelas.items():
            conteudo = dados.to_csv(index=False, sep=";").encode("latin-1")
            soma = hashlib.md5(conteudo, usedforsecurity=False).hexdigest()
            somas.append(f"{soma.upper()} *{nome.lower()}")
            pacote.writestr(
                f"pacote/dados/{nome}", conteudo + (b"\n" if corromper else b"")
            )
        if ano == 2025:
            for tipo in ("Turma", "Docente", "Gestor_Escolar", "Curso_Tecnico"):
                pacote.writestr(f"pacote/dados/Tabela_{tipo}_2025_V2.csv", "NÃO LER")
        if not sem_md5:
            pacote.writestr(
                f"pacote/dados/md5_microdados_ed_basica_{ano}.txt", "\r\n".join(somas)
            )
    return caminho


@pytest.mark.parametrize("ano", [2022, 2023, 2024, 2025])
def test_ler_os_dois_esquemas_sem_somar_especial_ao_total(tmp_path, ano):
    tabela = censo.ler_edicao(_zip(tmp_path, ano), ano)
    assert len(tabela) == 1
    assert tabela.iloc[0]["cnpj_escola"] == _cnpj()
    assert tabela.iloc[0]["qt_mat_bas"] == 80
    assert tabela.iloc[0]["qt_mat_esp"] == 4
    assert tabela.iloc[0]["qt_mat_fund_int"] == 20
    assert "CAMPO PROIBIDO" not in tabela.to_csv()


@pytest.mark.parametrize(
    "invalido",
    [
        "",
        "0" * 14,
        "9" * 14,
        "123",
        "12345678901",
        "12345678901234",
        "12ABC34501DE35",
        "00000001000136.0",
        "00.000.001/0001-36",
    ],
)
def test_cnpj_invalido_nunca_sai_nem_como_segundo_documento(tmp_path, invalido):
    linhas = [
        _escola(2024, NU_CNPJ_ESCOLA_PRIVADA=invalido, NU_CNPJ_MANTENEDORA=invalido),
        _escola(2024, "99000002", NU_CNPJ_ESCOLA_PRIVADA=invalido),
        _escola(2024, "99000003", NU_CNPJ_MANTENEDORA=invalido),
    ]
    tabela = censo.ler_edicao(_zip(tmp_path, 2024, linhas), 2024)
    assert set(tabela["co_entidade"]) == {"99000002", "99000003"}
    assert pd.isna(tabela.loc[tabela.co_entidade == "99000002", "cnpj_escola"].iloc[0])
    assert pd.isna(
        tabela.loc[tabela.co_entidade == "99000003", "cnpj_mantenedora"].iloc[0]
    )


def test_juncao_pelo_codigo_preserva_situacao_e_so_privadas(tmp_path):
    linhas = [
        _escola(2025, TP_DEPENDENCIA="3"),
        _escola(2025, "99000002", QT_MAT_BAS="123", TP_SITUACAO_FUNCIONAMENTO="2"),
        _escola(2025, "99000003", QT_MAT_BAS="456", QT_MAT_BAS_INT="7"),
    ]
    tabela = censo.ler_edicao(_zip(tmp_path, 2025, linhas), 2025).set_index(
        "co_entidade"
    )
    assert list(tabela.index) == ["99000002", "99000003"]
    assert tabela.loc["99000002", "qt_mat_bas"] == 123
    assert tabela.loc["99000002", "situacao_funcionamento"] == 2
    assert tabela.loc["99000003", "qt_mat_bas_int"] == 7


@pytest.mark.parametrize("opcoes", [{"corromper": True}, {"sem_md5": True}])
def test_md5_ausente_ou_divergente_recusa_edicao(tmp_path, opcoes):
    with pytest.raises(ValueError, match="MD5"):
        censo.ler_edicao(_zip(tmp_path, 2025, **opcoes), 2025)


def test_coluna_nao_permitida_nao_e_materializada_pelo_pandas(tmp_path, monkeypatch):
    ler = pd.read_csv
    chamadas = []

    def conferir(*args, **kwargs):
        chamadas.append(kwargs.get("usecols"))
        assert kwargs.get("usecols") is not None
        return ler(*args, **kwargs)

    monkeypatch.setattr(pd, "read_csv", conferir)
    censo.ler_edicao(_zip(tmp_path, 2025), 2025)
    assert len(chamadas) == 2


class _Servidor:
    def __init__(self, caminho):
        self.conteudo = caminho.read_bytes()
        self.pedidos = []

    def baixar(self, url, destino):
        self.pedidos.append(url)
        destino.write_bytes(self.conteudo)
        return {"Last-Modified": "Fri, 31 Jul 2026 11:52:00 GMT"}


def test_carga_grava_edicao_com_linhagem_sem_antecipar_disponibilidade(tmp_path):
    servidor = _Servidor(_zip(tmp_path, 2025))
    quando = datetime(2026, 11, 27, tzinfo=UTC)
    assert carga.carregar_edicao(2025, tmp_path / "base", quando, servidor) == "gravado"
    arquivo = tmp_path / "base/inep_censo_escolar/2025.parquet"
    assert conferir_tabela(arquivo)
    tabela = pd.read_parquet(arquivo)
    assert tabela.iloc[0].fonte == censo.FONTE
    assert str(tabela.iloc[0].data_edicao) == "2025-05-28"
    assert str(tabela.iloc[0].disponivel_em) == "2026-11-27"
    assert tabela.iloc[0].origem_sha256 == hashlib.sha256(servidor.conteudo).hexdigest()
    assert servidor.pedidos == [censo.url_da_edicao(2025)]


def test_recoleta_igual_preserva_data_e_revisao_guarda_versao(tmp_path):
    pasta = tmp_path / "base"
    servidor = _Servidor(_zip(tmp_path, 2024))
    primeiro = datetime(2026, 11, 27, tzinfo=UTC)
    depois = datetime(2026, 12, 1, tzinfo=UTC)
    carga.carregar_edicao(2024, pasta, primeiro, servidor)
    assert carga.carregar_edicao(2024, pasta, depois, servidor) == "igual"
    arquivo = pasta / "inep_censo_escolar/2024.parquet"
    assert str(pd.read_parquet(arquivo).iloc[0].disponivel_em) == "2026-11-27"
    revisado = _Servidor(_zip(tmp_path, 2024, [_escola(2024, QT_MAT_BAS="79")]))
    assert carga.carregar_edicao(2024, pasta, depois, revisado) == "gravado"
    anterior = pasta / "inep_censo_escolar/2024.v1.parquet"
    assert pd.read_parquet(anterior).iloc[0].qt_mat_bas == 80
    assert pd.read_parquet(arquivo).iloc[0].qt_mat_bas == 79
    assert conferir_tabela(anterior)


def test_carga_corrompida_nao_publica_parquet(tmp_path):
    servidor = _Servidor(_zip(tmp_path, 2024, corromper=True))
    with pytest.raises(ValueError, match="MD5"):
        carga.carregar_edicao(
            2024, tmp_path / "base", datetime(2026, 11, 27, tzinfo=UTC), servidor
        )
    assert not list((tmp_path / "base").rglob("*.parquet"))


@pytest.mark.parametrize(
    "mudancas", [{"NU_ANO_CENSO": "2023"}, {"QT_MAT_BAS": "-1"}, {"QT_MAT_BAS": "1.5"}]
)
def test_ano_ou_contagem_invalida_recusa_edicao(tmp_path, mudancas):
    with pytest.raises(ValueError):
        censo.ler_edicao(_zip(tmp_path, 2025, [_escola(2025, **mudancas)]), 2025)


def test_codigo_duplicado_nao_multiplica_matriculas(tmp_path):
    with pytest.raises(ValueError, match="duplicado"):
        censo.ler_edicao(_zip(tmp_path, 2025, [_escola(2025)] * 2), 2025)


def test_freio_de_disco_impede_download(tmp_path, monkeypatch):
    from base.arquivo.coleta import FreioDeDisco

    monkeypatch.setattr(carga, "espaco_do_disco", lambda pasta: (1000, 1))
    servidor = _Servidor(_zip(tmp_path, 2024))
    with pytest.raises(FreioDeDisco):
        carga.carregar_edicao(2024, tmp_path / "base", datetime.now(UTC), servidor)
    assert servidor.pedidos == []


def test_catalogo_descreve_todas_as_colunas_e_mantem_marca_inep(tmp_path):
    import json

    from base.dicionario import TABELAS
    from src.banco.coletas import VENDAVEL_RISCO_ASSUMIDO, revenda_da_fonte

    carga.carregar_edicao(
        2024, tmp_path / "base", datetime.now(UTC), _Servidor(_zip(tmp_path, 2024))
    )
    arquivo = tmp_path / "base/inep_censo_escolar/2024.parquet"
    assert set(pd.read_parquet(arquivo)) == set(TABELAS[censo.TABELA].colunas)
    manifesto = json.loads(arquivo.with_suffix(".json").read_text(encoding="utf-8"))
    assert revenda_da_fonte("inep") == VENDAVEL_RISCO_ASSUMIDO
    assert "inep" in str(manifesto["licenca"])


def test_revisao_que_so_acrescenta_escola_tambem_preserva_edicao_anterior(tmp_path):
    pasta = tmp_path / "base"
    carga.carregar_edicao(
        2024, pasta, datetime(2026, 11, 27, tzinfo=UTC), _Servidor(_zip(tmp_path, 2024))
    )
    novas = [_escola(2024), _escola(2024, "99000002")]
    carga.carregar_edicao(
        2024,
        pasta,
        datetime(2026, 12, 1, tzinfo=UTC),
        _Servidor(_zip(tmp_path, 2024, novas)),
    )
    anterior = pasta / "inep_censo_escolar/2024.v1.parquet"
    assert anterior.exists()
    assert str(pd.read_parquet(anterior).iloc[0].disponivel_em) == "2026-11-27"


def _reescrever_zip(caminho, transformar):
    with zipfile.ZipFile(caminho) as pacote:
        membros = {m.filename: pacote.read(m) for m in pacote.infolist()}
    transformar(membros)
    with zipfile.ZipFile(caminho, "w") as pacote:
        for nome, conteudo in membros.items():
            pacote.writestr(nome, conteudo)


@pytest.mark.parametrize("problema", ["falta_escola", "sem_coluna", "duplicada"])
def test_tabela_de_matriculas_incompleta_ou_duplicada_impede_carga(tmp_path, problema):
    caminho = _zip(tmp_path, 2025)

    def mudar(membros):
        nome = "pacote/dados/Tabela_Matricula_2025_V2.csv"
        tabela = pd.read_csv(io.BytesIO(membros[nome]), sep=";", dtype=str)
        if problema == "falta_escola":
            tabela["CO_ENTIDADE"] = "99000009"
        elif problema == "sem_coluna":
            tabela = tabela.drop(columns="QT_MAT_BAS")
        else:
            tabela = pd.concat([tabela, tabela])
        anterior = hashlib.md5(membros[nome], usedforsecurity=False).hexdigest().upper()
        membros[nome] = tabela.to_csv(index=False, sep=";").encode("latin-1")
        novo = hashlib.md5(membros[nome], usedforsecurity=False).hexdigest().upper()
        manifesto = "pacote/dados/md5_microdados_ed_basica_2025.txt"
        membros[manifesto] = membros[manifesto].replace(
            anterior.encode(), novo.encode()
        )

    _reescrever_zip(caminho, mudar)
    with pytest.raises(ValueError):
        censo.ler_edicao(caminho, 2025)


@pytest.mark.parametrize("problema", ["formato", "duplicado", "sem_csv", "grande"])
def test_manifesto_md5_ambiguo_ou_incompleto_falha(tmp_path, problema):
    caminho = _zip(tmp_path, 2024)

    def mudar(membros):
        nome = "pacote/dados/md5_microdados_ed_basica_2024.txt"
        if problema == "formato":
            membros[nome] = b"sem um hash"
        elif problema == "duplicado":
            membros[nome] += b"\n" + membros[nome]
        elif problema == "sem_csv":
            membros[nome] = membros[nome].replace(
                b"microdados_ed_basica", b"outro_arquivo"
            )
        else:
            membros[nome] = b" " * (censo.MAX_MANIFESTO + 1)

    _reescrever_zip(caminho, mudar)
    with pytest.raises(ValueError, match="MD5"):
        censo.ler_edicao(caminho, 2024)


@pytest.mark.parametrize("falhar", [False, True])
def test_comando_manual_usa_edicoes_explicitas_e_nao_vaza_erro(
    tmp_path, monkeypatch, caplog, falhar
):
    from types import SimpleNamespace

    pedidos = []
    fechados = []
    cliente = SimpleNamespace(
        sessao=SimpleNamespace(close=lambda: fechados.append(True))
    )
    monkeypatch.setattr(carga, "ClienteHttp", lambda: cliente)
    monkeypatch.setattr(carga, "exigir_versao_do_codigo", lambda: "teste")

    def carregar(ano, pasta, quando, cliente):
        pedidos.append(ano)
        if falhar:
            raise ValueError("CELULA DA FONTE NAO DEVE SAIR")
        return "gravado"

    monkeypatch.setattr(carga, "carregar_edicao", carregar)
    codigo = carga.main(
        ["--ano", "2022", "--ano", "2022", "--ano", "2025", "--pasta", str(tmp_path)]
    )
    assert codigo == (1 if falhar else 0)
    assert pedidos == ([2022] if falhar else [2022, 2025])
    assert fechados == [True]
    assert "CELULA DA FONTE" not in caplog.text


def test_comando_sem_edicao_nao_baixa(monkeypatch):
    def nao_chamar():
        pytest.fail("não deve criar cliente sem edição explícita")

    monkeypatch.setattr(carga, "ClienteHttp", nao_chamar)
    with pytest.raises(SystemExit) as erro:
        carga.main([])
    assert erro.value.code == 2
