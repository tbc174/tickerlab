"""A porta da base que os pedidos da API externa dividem (linha 956).

Abrir a porta (`base.porta.abrir`) cria as views de todas as tabelas e lê o cabeçalho dos Parquets de cada
uma. Medido na máquina de casa com os limites da API (meia CPU), isso levou de 8 a 12 s **a cada pedido**, antes
de qualquer consulta: era a maior parte da busca simples e um quarto do `compradores_do_setor`. Aqui a porta
abre uma vez por processo e cada pedido leva um cursor dela (`cursor()` do DuckDB: outra conexão, as mesmas
views, sem dividir resultado nem tabela registrada com os outros pedidos).

**Quando a base muda:** o recebedor do servidor troca a pasta `base/` (ou arquivos dela); as views guardam a
lista de arquivos de quando foram criadas. A cada pedido a porta compara a impressão dos arquivos (caminho, data
e tamanho) com a de quando abriu e, se mudou, abre outra (os pedidos em curso terminam na antiga). Só um pedido
abre por vez: os outros esperam a porta nova em vez de abrir uma cada um.

**O registro de coletas (`banco`) é de cada pedido:** a porta emprestada leva a conexão do banco do pedido, não
a de quem abriu a dona.
"""

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import sqlalchemy as sa

from base import porta as porta_da_base
from base.porta import METADADOS, Porta
from base.porta.duckdb import ARQUIVOS, arquivos_da_tabela
from src import acervo

# O contêiner da API tem meia CPU (`compose.yaml`) e o DuckDB vê os núcleos da máquina, não a cota: com as threads
# padrão, as linhas de execução disputam o meio núcleo. Medido no PC com teto rígido de meio núcleo, na análise
# completa fria de duas companhias grandes: padrão (16) 13,7 a 16,0 s; 2, de 8,3 a 8,8 s; 1, de 7,3 a 7,9 s (linha
# 1015, item e). Os pedidos ao mesmo tempo seguem em paralelo: cada cursor roda na linha de execução de quem pede
# (duas consultas pesadas em dois cursores, com 1: 2,38 s uma, 2,67 s as duas). A memória fica no padrão do DuckDB:
# a porta é uma só para todos os pedidos, e um teto como o da `api_v1` (512MB por pedido) não foi medido aqui.
THREADS_DA_PORTA = 1


def abrir_a_base() -> Porta:
    """Abre a porta da base do acervo (os testes trocam esta função)."""
    return porta_da_base.abrir(threads=THREADS_DA_PORTA)


class PortaEmprestada(Porta):
    """Uma `Porta` cuja conexão é um cursor da porta dona: as mesmas views, fechar não fecha a dona."""

    def __init__(
        self, dona: Porta, banco: sa.Connection | None, memoria: dict[Any, Any]
    ) -> None:
        # não chama `Porta.__init__`: ele abriria outra conexão (e refaria as views), que é o que se evita
        self.pasta = dona.pasta
        self.banco = banco
        self.tabelas = dona.tabelas
        self.arquivos = dona.arquivos
        self.con = dona.con.cursor()
        # o fuso é da sessão: o cursor herda o do sistema, e a data de publicação (olhar o futuro) usa o UTC
        self.con.execute("SET TimeZone = 'UTC'")
        # o que só depende dos arquivos (o mês do retrato de um dia, por exemplo) vale para a vida da porta dona
        self.memoria_da_base = memoria

    memoria_da_base: dict[Any, Any]


@dataclass(frozen=True)
class _Dona:
    porta: Porta
    pasta: Path | None
    impressao: tuple
    memoria: dict[Any, Any] = field(default_factory=dict)


_TRAVA = threading.Lock()
_DONA: _Dona | None = None


def _pasta_da_base() -> Path | None:
    raiz = acervo.pasta_do_acervo()
    return None if raiz is None else raiz / "base"


def _impressao(pasta: Path, arquivos: dict[str, str]) -> tuple:
    impressao = []
    for padrao in arquivos.values():
        for arquivo in arquivos_da_tabela(pasta, padrao):
            estado = arquivo.stat()
            impressao.append((arquivo.as_posix(), estado.st_mtime_ns, estado.st_size))
    return tuple(impressao)


def impressao_da_base(porta: Porta) -> tuple:
    """Os arquivos que as views da porta leem (caminho, data e tamanho): muda quando a base muda."""
    return _impressao(porta.pasta, porta.arquivos)


_NADA = object()  # o que `lembrar` lê quando a chave não está na memória
MEMORIA_MAXIMA = 256  # entradas por porta dona: o dia da pergunta (`known_at`) varia de pedido para pedido


# Uma trava por chave em cálculo: os pedidos que chegam juntos com a memória fria esperam o primeiro em vez de
# varrer a base cada um (três análises frias em meia CPU faziam três vezes as mesmas varreduras, linha 1015, item
# f). Quem espera relê a memória da própria porta: a trava de uma porta velha e de uma nova com a mesma chave só
# põe uma depois da outra.
_TRAVAS_EM_USO = threading.Lock()
_TRAVAS: dict[object, threading.Lock] = {}


def _trava_da(chave: object) -> threading.Lock:
    with _TRAVAS_EM_USO:
        if len(_TRAVAS) >= MEMORIA_MAXIMA and chave not in _TRAVAS:
            # o dia variado de quem pede não pode crescer a lista sem fim; quem já tem a trava velha termina com
            # ela, e o pior caso é um cálculo a mais, nunca uma resposta trocada
            _TRAVAS.clear()
        return _TRAVAS.setdefault(chave, threading.Lock())


def impressao_das_tabelas(porta: Porta, tabelas: tuple[str, ...]) -> tuple:
    """Os arquivos que as views de `tabelas` leem (caminho, data e tamanho), sem abrir nenhum."""
    return _impressao(
        porta.pasta, {t: porta.arquivos[t] for t in tabelas if t in porta.arquivos}
    )


def lembrar[T](
    porta: Porta,
    chave: object,
    calcular: Callable[[], T],
    tabelas: tuple[str, ...] = (),
) -> T:
    """O resultado de uma consulta que só depende dos arquivos da base, guardado enquanto a porta dona vive (a
    base mudou → porta nova → memória nova). Porta que não é de pedido (os testes) calcula sempre. Com a memória
    fria, os pedidos da mesma chave esperam o primeiro calcular; se o cálculo dele falha (o prazo interrompeu a
    consulta), nada fica guardado e o seguinte calcula.

    Com `tabelas`, o guardado leva a impressão dos arquivos delas e só vale enquanto ela não muda. As views leem
    os Parquets pelo caminho: se a carga troca um arquivo enquanto um pedido ainda está com a porta velha, o
    pedido calcula de novo, como fazia antes do guardado (achado P1 do Revisor no #1325, linha 1098)."""
    memoria = getattr(porta, "memoria_da_base", None)
    if memoria is None:
        return calcular()
    # a impressão é tirada ANTES de calcular: se o arquivo mudar durante o cálculo, o próximo calcula de novo
    conferida = impressao_das_tabelas(porta, tabelas) if tabelas else None
    # uma leitura só: entre um `in` e a leitura, outro pedido pode esvaziar a memória cheia (KeyError, 500)
    guardado = memoria.get(chave, _NADA)
    if guardado is not _NADA and guardado[0] == conferida:
        return guardado[1]
    with _trava_da(chave):
        guardado = memoria.get(
            chave, _NADA
        )  # quem esperou acha o que o primeiro calculou
        if guardado is not _NADA and guardado[0] == conferida:
            return guardado[1]
        valor = calcular()
        _guardar(memoria, chave, (conferida, valor))
    return valor  # não relê: outro pedido pode ter esvaziado a memória cheia entre as duas linhas


def _guardar(memoria: dict[Any, Any], chave: object, valor: object) -> None:
    if len(memoria) >= MEMORIA_MAXIMA:
        # as tabelas e as colunas da porta (uma entrada só, do tamanho da base) ficam: o dia variado de quem pede
        # não pode expulsá-las e fazer cada pedido perguntar tudo de novo
        metadados = memoria.get(METADADOS)
        memoria.clear()
        if metadados is not None:
            memoria[METADADOS] = metadados
    memoria[chave] = valor


def zerar() -> None:
    """Esquece a porta dona (os testes; a próxima chamada abre outra)."""
    global _DONA
    with _TRAVA:
        _DONA = None


def porta_do_pedido(banco: sa.Connection | None = None) -> Porta:
    """Uma porta para um pedido: um cursor da porta dona, aberta de novo se a base mudou. Quem pede fecha
    (`with porta:`), e isso fecha só o cursor. Se a base não está neste servidor, levanta o mesmo erro de
    `abrir` (a rota responde 503) e não guarda nada."""
    global _DONA
    with _TRAVA:
        dona = _DONA
        pasta = _pasta_da_base()
        if (
            dona is None
            or dona.pasta != pasta
            or dona.impressao != impressao_da_base(dona.porta)
        ):
            # a impressão é tirada ANTES de abrir (a abertura leva segundos): se a base mudar durante ela, a
            # impressão guardada já é velha e o pedido seguinte abre de novo, em vez de servir views velhas
            antes = () if pasta is None else _impressao(pasta, dict(ARQUIVOS))
            nova = abrir_a_base()
            dona = _Dona(nova, pasta, antes)
            _DONA = dona
        return PortaEmprestada(dona.porta, banco, dona.memoria)
