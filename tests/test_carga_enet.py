"""Carga noturna das versões antigas do ENET (série 1 da base de ML, PR 7): DFP do mais novo para o
mais velho e depois ITR, só até o fim da janela (6h), retomando na noite seguinte sem baixar de
novo. Sem internet: os índices da CVM e os pacotes do ENET são montados aqui."""

import io
import zipfile
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
import sqlalchemy as sa

from scripts import carga_enet
from src import acervo
from src.banco.conexao import criar_engine, migrar_para
from src.banco.modelo import coletas
from tests.test_base_enet import _dfp
from tests.test_base_enet_coleta import _pacote

FUSO = ZoneInfo("America/Sao_Paulo")
CABECALHO = (
    "CNPJ_CIA;DT_REFER;VERSAO;DENOM_CIA;CD_CVM;CATEG_DOC;ID_DOC;DT_RECEB;LINK_DOC"
)


def _zip_do_ano(documento: str, ano: int) -> bytes:
    """Um arquivo anual da CVM só com o índice: uma empresa com as versões 1, 2 e 3."""
    referencia = f"{ano}-12-31" if documento == "DFP" else f"{ano}-03-31"
    linhas = [
        f"00.000.208/0001-00;{referencia};{v};BRB;014206;{documento};{ano}{v};{ano + 1}-0{v}-10;"
        f"http://enet/{documento}/{ano}/{v}"
        for v in (1, 2, 3)
    ]
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as z:
        z.writestr(
            f"{documento.lower()}_cia_aberta_{ano}.csv",
            "\n".join([CABECALHO, *linhas]).encode("latin-1"),
        )
    return saida.getvalue()


@pytest.fixture
def url(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'c.sqlite').as_posix()}"
    monkeypatch.setenv("TICKERLAB_DATABASE_URL", url)
    monkeypatch.setenv(acervo.VARIAVEL_DA_PASTA, str(tmp_path / "acervo"))
    migrar_para("head", url=url)
    return url


class _Mundo:
    """A CVM e o ENET de mentira, com um relógio que anda 10 minutos a cada pacote."""

    def __init__(
        self,
        monkeypatch,
        comeco: datetime,
        quebrados: set[str] = frozenset(),
        estranhos: set[str] = frozenset(),
    ):
        self.agora, self.pacotes, self.quebrados = comeco, [], quebrados
        self.estranhos = estranhos  # pacotes num formato que o leitor não conhece
        monkeypatch.setattr(carga_enet, "baixar", self.arquivo_da_cvm)
        monkeypatch.setattr(carga_enet, "Baixador", lambda: self)
        monkeypatch.setattr(carga_enet, "agora", lambda: self.agora)

    def arquivo_da_cvm(self, endereco: str) -> bytes | None:
        nome = endereco.rsplit("/", 1)[-1]  # dfp_cia_aberta_2024.zip
        documento, ano = nome[:3].upper(), int(nome[-8:-4])
        return (
            _zip_do_ano(documento, ano) if ano >= 2023 else None
        )  # antes de 2023: 404

    def baixar(self, link: str) -> bytes:
        self.pacotes.append(link)
        self.agora += timedelta(minutes=10)
        if link in self.quebrados:
            return b"isto nao e zip"
        if link in self.estranhos:
            return _pacote_de("coisa-estranha.bin")
        return _pacote(_dfp(versao=int(link[-1])))


def _guardados(url: str) -> set[str]:
    motor = criar_engine(url)
    try:
        with motor.connect() as c:
            consulta = sa.select(coletas.c.url).where(
                coletas.c.fonte == "cvm-enet", coletas.c.situacao == "ok"
            )
            return set(c.execute(consulta).scalars())
    finally:
        motor.dispose()


def test_dfp_do_mais_novo_para_o_mais_velho_e_depois_itr(url, monkeypatch):
    mundo = _Mundo(monkeypatch, datetime(2026, 10, 14, 0, 30, tzinfo=FUSO))
    assert carga_enet.main(["--desde", "2023", "--ate", "2024"]) == 0
    assert mundo.pacotes == [
        "http://enet/DFP/2024/1",
        "http://enet/DFP/2024/2",
        "http://enet/DFP/2023/1",
        "http://enet/DFP/2023/2",
        "http://enet/ITR/2024/1",
        "http://enet/ITR/2024/2",
        "http://enet/ITR/2023/1",
        "http://enet/ITR/2023/2",
    ]  # a versão 3 vem dos dados abertos
    assert len(_guardados(url)) == 8


def test_para_as_6h_e_retoma_na_noite_seguinte_sem_baixar_de_novo(url, monkeypatch):
    mundo = _Mundo(monkeypatch, datetime(2026, 10, 14, 5, 35, tzinfo=FUSO))
    assert carga_enet.main(["--desde", "2023", "--ate", "2024"]) == 0
    assert len(mundo.pacotes) == 3  # 5h35, 5h45, 5h55; às 6h05 não começa outro
    mundo.agora, mundo.pacotes = datetime(2026, 10, 15, 0, 30, tzinfo=FUSO), []
    assert carga_enet.main(["--desde", "2023", "--ate", "2024"]) == 0
    assert len(mundo.pacotes) == 5 and len(_guardados(url)) == 8


DE_2023 = {f"http://enet/{d}/2023/{v}" for d in ("DFP", "ITR") for v in (1, 2)}
DE_2024 = {f"http://enet/{d}/2024/{v}" for d in ("DFP", "ITR") for v in (1, 2)}
SO_2024 = ["--desde", "2024", "--ate", "2024"]


def test_falha_passageira_nao_derruba_a_tarefa_mas_tudo_falhando_sim(url, monkeypatch):
    comeco = datetime(2026, 10, 14, 0, 30, tzinfo=FUSO)
    _Mundo(monkeypatch, comeco, quebrados={"http://enet/DFP/2024/1"})
    assert carga_enet.main(["--desde", "2024", "--ate", "2024"]) == 0
    tudo = {f"http://enet/{d}/2024/{v}" for d in ("DFP", "ITR") for v in (1, 2)}
    _Mundo(monkeypatch, comeco, quebrados=(tudo - _guardados(url)) | DE_2023)
    assert carga_enet.main(["--desde", "2023", "--ate", "2024"]) == 1  # avisa o Kuma


@pytest.mark.parametrize(
    ("hora", "fim"),
    [
        (
            datetime(2026, 10, 14, 0, 30, tzinfo=FUSO),
            datetime(2026, 10, 14, 6, 0, tzinfo=FUSO),
        ),
        (
            datetime(2026, 10, 14, 23, 0, tzinfo=FUSO),
            datetime(2026, 10, 15, 6, 0, tzinfo=FUSO),
        ),
        (
            datetime(2026, 10, 14, 6, 0, tzinfo=FUSO),
            datetime(2026, 10, 15, 6, 0, tzinfo=FUSO),
        ),
    ],
)
def test_fim_da_janela(hora, fim):
    assert carga_enet.fim_da_janela(hora, "06:00") == fim


def _pacote_de(nome: str) -> bytes:
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as z:
        z.writestr(nome, b"?")
    return saida.getvalue()


def test_pacote_de_formato_desconhecido_nao_diz_que_a_fonte_esta_fora_do_ar(
    url, monkeypatch, caplog
):
    mundo = _Mundo(monkeypatch, datetime(2026, 10, 14, 0, 30, tzinfo=FUSO))
    mundo.baixar = lambda link: _pacote_de("coisa-estranha.bin")  # type: ignore[method-assign]
    assert carga_enet.main(["--desde", "2024", "--ate", "2024"]) == 1
    assert "formato que o leitor não conhece" in caplog.text
    assert "fora do ar" not in caplog.text


def test_falha_de_rede_continua_dizendo_que_a_fonte_pode_estar_fora_do_ar(
    url, monkeypatch, caplog
):
    comeco = datetime(2026, 10, 14, 0, 30, tzinfo=FUSO)
    mundo = _Mundo(monkeypatch, comeco)

    def sem_rede(link: str) -> bytes:
        raise ConnectionError("sem rede")

    mundo.baixar = sem_rede  # type: ignore[method-assign]
    assert carga_enet.main(["--desde", "2024", "--ate", "2024"]) == 1
    assert "fora do ar" in caplog.text
    assert "formato que o leitor não conhece" not in caplog.text


def test_pacote_sem_leitor_nao_e_baixado_toda_noite_nem_acende_o_kuma_de_novo(
    url, monkeypatch
):
    """Regressão de 04/11/2026: os mesmos 45 pacotes sem leitor eram baixados de novo toda noite (11
    minutos e ~1 GB da CVM) e a tarefa saía com 1 para sempre ("Carga em dia: 0 baixadas")."""
    noite = datetime(2026, 10, 14, 0, 30, tzinfo=FUSO)
    mundo = _Mundo(monkeypatch, noite, estranhos=DE_2024)
    assert carga_enet.main(SO_2024) == 1  # a novidade avisa uma vez
    mundo.agora, mundo.pacotes = noite + timedelta(days=1), []
    assert carga_enet.main(SO_2024) == 0
    assert mundo.pacotes == []


def test_pacote_sem_leitor_e_tentado_de_novo_depois_de_um_mes_sem_acender_o_kuma(
    url, monkeypatch
):
    noite = datetime(2026, 10, 14, 0, 30, tzinfo=FUSO)
    mundo = _Mundo(monkeypatch, noite, estranhos=DE_2024)
    assert carga_enet.main(SO_2024) == 1
    mundo.agora, mundo.pacotes = noite + timedelta(days=31), []
    assert carga_enet.main(SO_2024) == 0  # já se sabia: não é novidade
    assert set(mundo.pacotes) == DE_2024


def test_tentar_de_novo_baixa_ja_o_que_foi_deixado_de_lado(url, monkeypatch):
    """Depois de ensinar o leitor um formato novo, não é preciso esperar um mês."""
    noite = datetime(2026, 10, 14, 0, 30, tzinfo=FUSO)
    mundo = _Mundo(monkeypatch, noite, estranhos=DE_2024)
    assert carga_enet.main(SO_2024) == 1
    mundo.agora, mundo.estranhos = noite + timedelta(days=1), set()
    assert carga_enet.main([*SO_2024, "--tentar-de-novo"]) == 0
    assert _guardados(url) == DE_2024


def test_pacote_cortado_tres_noites_seguidas_e_deixado_de_lado(url, monkeypatch):
    noite = datetime(2026, 10, 14, 0, 30, tzinfo=FUSO)
    mundo = _Mundo(monkeypatch, noite, quebrados=DE_2024)
    saidas = []
    for dia in range(5):
        mundo.agora = noite + timedelta(days=dia)
        saidas.append(carga_enet.main(SO_2024))
    assert saidas == [1, 0, 0, 0, 0]  # só a primeira é novidade
    assert len(mundo.pacotes) == 3 * len(DE_2024)


def test_sem_rede_toda_noite_continua_vermelho_e_nao_desiste_dos_pacotes(
    url, monkeypatch
):
    noite = datetime(2026, 10, 14, 0, 30, tzinfo=FUSO)
    mundo = _Mundo(monkeypatch, noite)
    com_rede = mundo.baixar

    def sem_rede(link: str) -> bytes:
        raise ConnectionError("sem rede")

    mundo.baixar = sem_rede  # type: ignore[method-assign]
    for dia in range(4):
        mundo.agora = noite + timedelta(days=dia)
        assert carga_enet.main(SO_2024) == 1
    mundo.baixar, mundo.agora = com_rede, noite + timedelta(days=4)  # type: ignore[method-assign]
    assert carga_enet.main(SO_2024) == 0
    assert _guardados(url) == DE_2024
