"""A porta que os pedidos da API externa dividem (linha 956): abre uma vez e acompanha a base.

Risco: abrir a porta custava 8 a 12 s por pedido na máquina de casa (meia CPU). Compartilhar a conexão não pode
(1) misturar o resultado de um pedido com o de outro, (2) servir a base velha depois que o recebedor troca os
arquivos, nem (3) fechar a porta de quem ainda está lendo. Base de mentira, sem internet.
"""

import os
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import pytest

from base.porta import Porta
from src.api_externa import porta_compartilhada as compartilhada
from src.api_externa.conjuntos import prospeccao
from tests.test_api_externa_prospeccao import _empresas, _estabelecimentos, _gravar

CONTAGEM = f"SELECT count(*) FROM {prospeccao.EMPRESAS}"


@dataclass
class BaseDeMentira:
    pasta: Path
    aberturas: list[Path] = field(default_factory=list)

    def abrir(self) -> Porta:
        self.aberturas.append(self.pasta)
        return Porta(self.pasta)


@pytest.fixture
def base(tmp_path: Path, monkeypatch) -> Iterator[BaseDeMentira]:
    pasta = tmp_path / "base"
    _gravar(pasta, prospeccao.ESTABELECIMENTOS, _estabelecimentos())
    _gravar(pasta, prospeccao.EMPRESAS, _empresas())
    falsa = BaseDeMentira(pasta)
    compartilhada.zerar()
    monkeypatch.setattr(compartilhada, "abrir_a_base", falsa.abrir)
    monkeypatch.setattr(compartilhada, "_pasta_da_base", lambda: falsa.pasta)
    yield falsa
    compartilhada.zerar()


def _linhas(porta: Porta) -> int:
    achado = porta.con.execute(CONTAGEM).fetchone()
    assert achado is not None
    return achado[0]


def test_a_porta_abre_uma_vez_para_varios_pedidos(base):
    for _ in range(4):
        with compartilhada.porta_do_pedido() as porta:
            assert _linhas(porta) == len(_empresas())
    assert len(base.aberturas) == 1


def test_fechar_a_porta_de_um_pedido_nao_fecha_a_dos_outros(base):
    primeira = compartilhada.porta_do_pedido()
    segunda = compartilhada.porta_do_pedido()
    primeira.fechar()
    assert _linhas(segunda) == len(_empresas())
    with compartilhada.porta_do_pedido() as terceira:
        assert _linhas(terceira) == len(_empresas())
    segunda.fechar()
    assert len(base.aberturas) == 1


@pytest.mark.usefixtures("base")
def test_o_registro_de_coletas_e_de_cada_pedido():
    um, outro = object(), object()
    with (
        compartilhada.porta_do_pedido(um) as a,  # type: ignore[arg-type]
        compartilhada.porta_do_pedido(outro) as b,  # type: ignore[arg-type]
    ):
        assert a.banco is um
        assert b.banco is outro


@pytest.mark.usefixtures("base")
def test_tabela_registrada_num_pedido_nao_aparece_no_outro():
    with compartilhada.porta_do_pedido() as a, compartilhada.porta_do_pedido() as b:
        a.con.register("so_deste_pedido", pd.DataFrame({"x": [1]}))
        assert a.con.execute("SELECT count(*) FROM so_deste_pedido").fetchone() == (1,)
        with pytest.raises(Exception, match="so_deste_pedido"):
            b.con.execute("SELECT count(*) FROM so_deste_pedido")


def test_arquivo_trocado_na_base_abre_a_porta_de_novo(base):
    with compartilhada.porta_do_pedido() as porta:
        antes = _linhas(porta)
    arquivo = next((base.pasta / prospeccao.EMPRESAS).glob("*.parquet"))
    tabela = pd.read_parquet(arquivo)
    pd.concat([tabela, tabela]).to_parquet(arquivo, index=False)
    # a data muda mesmo que a gravação caia no mesmo instante da anterior
    os.utime(arquivo, ns=(1, 1))
    with compartilhada.porta_do_pedido() as porta:
        assert _linhas(porta) == antes + len(tabela)
    assert len(base.aberturas) == 2


def test_arquivo_novo_na_base_abre_a_porta_de_novo(base):
    with compartilhada.porta_do_pedido():
        pass
    outra = base.pasta / prospeccao.EMPRESAS / "zz.parquet"
    pd.read_parquet(
        next((base.pasta / prospeccao.EMPRESAS).glob("*.parquet"))
    ).to_parquet(outra, index=False)
    with compartilhada.porta_do_pedido() as porta:
        assert _linhas(porta) > len(_empresas())
    assert len(base.aberturas) == 2


def test_pasta_trocada_abre_a_porta_de_novo(base, tmp_path, monkeypatch):
    with compartilhada.porta_do_pedido() as porta:
        assert _linhas(porta) == len(_empresas())
    nova = BaseDeMentira(tmp_path / "base_nova")
    _gravar(nova.pasta, prospeccao.ESTABELECIMENTOS, _estabelecimentos())
    _gravar(nova.pasta, prospeccao.EMPRESAS, _empresas().head(2))
    monkeypatch.setattr(compartilhada, "abrir_a_base", nova.abrir)
    monkeypatch.setattr(compartilhada, "_pasta_da_base", lambda: nova.pasta)
    with compartilhada.porta_do_pedido() as porta:
        assert _linhas(porta) == 2
    assert len(base.aberturas) == 1 and len(nova.aberturas) == 1


def test_pedidos_ao_mesmo_tempo_abrem_a_porta_uma_vez_e_leem_certo(base):
    resultados: list[int] = []
    erros: list[BaseException] = []

    def pedido() -> None:
        try:
            with compartilhada.porta_do_pedido() as porta:
                resultados.append(_linhas(porta))
        except BaseException as erro:  # noqa: BLE001
            erros.append(erro)

    fios = [threading.Thread(target=pedido) for _ in range(8)]
    for fio in fios:
        fio.start()
    for fio in fios:
        fio.join()
    assert not erros
    assert resultados == [len(_empresas())] * 8
    assert len(base.aberturas) == 1


def test_base_que_nao_abre_levanta_e_nao_guarda_nada(monkeypatch):
    compartilhada.zerar()

    def sem_base() -> Porta:
        raise ValueError("acervo desligado")

    monkeypatch.setattr(compartilhada, "abrir_a_base", sem_base)
    monkeypatch.setattr(compartilhada, "_pasta_da_base", lambda: None)
    for _ in range(2):
        with pytest.raises(ValueError, match="acervo desligado"):
            compartilhada.porta_do_pedido()
    compartilhada.zerar()


def test_o_que_depende_so_dos_arquivos_e_lembrado_enquanto_a_porta_vive(base):
    calculos: list[int] = []

    def conta() -> int:
        calculos.append(1)
        return 42

    with compartilhada.porta_do_pedido() as a:
        assert compartilhada.lembrar(a, "chave", conta) == 42
    with compartilhada.porta_do_pedido() as b:
        assert compartilhada.lembrar(b, "chave", conta) == 42
        assert compartilhada.lembrar(b, "outra", conta) == 42
    assert len(calculos) == 2  # uma por chave

    # a base mudou: a porta é outra e a memória da velha não vale
    arquivo = next((base.pasta / prospeccao.EMPRESAS).glob("*.parquet"))
    os.utime(arquivo, ns=(1, 1))
    with compartilhada.porta_do_pedido() as c:
        assert compartilhada.lembrar(c, "chave", conta) == 42
    assert len(calculos) == 3


def test_porta_comum_calcula_sempre(base):
    calculos: list[int] = []
    porta = Porta(base.pasta)
    for _ in range(2):
        compartilhada.lembrar(porta, "chave", lambda: calculos.append(1))
    assert len(calculos) == 2


def test_a_memoria_e_limitada(base):
    with compartilhada.porta_do_pedido() as porta:
        for i in range(compartilhada.MEMORIA_MAXIMA + 5):
            compartilhada.lembrar(porta, i, lambda i=i: i)
        assert len(porta.memoria_da_base) <= compartilhada.MEMORIA_MAXIMA  # type: ignore[attr-defined]


def test_pedido_em_curso_nao_mistura_a_memoria_da_porta_velha_com_a_nova(base):
    """O pedido que pegou a porta antes da troca termina nela; o que chega depois só vê a nova (condição 3)."""
    velho = compartilhada.porta_do_pedido()
    compartilhada.lembrar(velho, "mes", lambda: "velho")
    arquivo = next((base.pasta / prospeccao.EMPRESAS).glob("*.parquet"))
    os.utime(arquivo, ns=(1, 1))
    novo = compartilhada.porta_do_pedido()
    assert len(base.aberturas) == 2
    # o novo não lê o que o velho lembrou, e o que o novo lembra não chega ao velho
    assert compartilhada.lembrar(novo, "mes", lambda: "novo") == "novo"
    assert compartilhada.lembrar(velho, "mes", lambda: "outro") == "velho"
    # o pedido velho ainda lê (a porta velha não foi fechada debaixo dele)
    assert _linhas(velho) == len(_empresas())
    velho.fechar()
    assert _linhas(novo) == len(_empresas())
    novo.fechar()


def test_base_que_muda_durante_a_abertura_abre_de_novo_no_pedido_seguinte(
    base, monkeypatch
):
    """A abertura leva segundos: o arquivo gravado nesse meio-tempo não pode ficar fora da impressão guardada."""
    arquivo = next((base.pasta / prospeccao.EMPRESAS).glob("*.parquet"))
    abrir_de_verdade = base.abrir

    def abre_e_a_base_muda() -> Porta:
        porta = abrir_de_verdade()
        os.utime(
            arquivo, ns=(1, 1)
        )  # o recebedor grava depois que as views foram criadas
        return porta

    monkeypatch.setattr(compartilhada, "abrir_a_base", abre_e_a_base_muda)
    with compartilhada.porta_do_pedido():
        pass
    monkeypatch.setattr(compartilhada, "abrir_a_base", abrir_de_verdade)
    with compartilhada.porta_do_pedido():
        pass
    assert len(base.aberturas) == 2  # a impressão velha forçou a segunda abertura
    with compartilhada.porta_do_pedido():
        pass
    assert len(base.aberturas) == 2  # e agora ela confere


def test_o_cursor_do_pedido_fala_em_utc(base):
    with compartilhada.porta_do_pedido() as porta:
        fuso = porta.con.execute("SELECT current_setting('TimeZone')").fetchone()
        assert fuso == ("UTC",)
