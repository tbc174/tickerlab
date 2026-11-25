"""A análise completa de um CNPJ numa chamada: cada bloco que a chave pode ver, com fonte e data (frente 3, 18/11/2026).

`montar_analise` junta, para um CNPJ e um dia (`known_at`), os blocos das rotas por CNPJ que já existem (cadastro,
sócios PJ, vínculos, eventos, crédito, ativos e comparáveis) e os das tabelas ligadas pelo CNPJ do registro
`src/api_externa/tabelas_por_cnpj.py` (regulados, balanço no BC, administradora de FII e, para a organização com o
conjunto de integridade no contrato, sanções da CGU, embargos do IBAMA e lista suja do MTE), na ordem de
`docs/padrao-de-analise.md`: uma frase no topo (só com o que o cadastro serviu), os blocos, a linha do tempo (só
com datas que vieram nos blocos), as leituras (dedução, marcada e separada dos fatos), o que não foi achado, o que a
análise não traz e os limites.

**Cada bloco passa pelo portão do próprio conjunto**, com a finalidade do contrato dele: é a mesma decisão de
chamar a rota do bloco, e a análise não libera nada novo. Se o bloco está aberto decide-se **antes de ler a
empresa**, pelas linhas que o portão libera hoje para a organização (contrato, linha de direito, prontidão, coleta
e guarda): bloco fechado não é lido, não aparece em lugar nenhum da resposta e não muda o tempo nem o tamanho dela
conforme a empresa. Tabela que ganha prontidão num conjunto lido aqui entra sozinha, sem mudar este arquivo; o
bloco de uma entrada do registro abre quando o portão libera um campo dela (não o conjunto inteiro: o `profiles`
tem também o cadastro).

**Prazo:** depois do cadastro, os outros blocos correm ao mesmo tempo, cada um no próprio cursor da porta; o que
passa do prazo tem a consulta interrompida e sai em `nao_respondeu_a_tempo`. A conexão do banco (o portão) é usada
por um bloco de cada vez e fecha para todos quando o prazo acaba.

**Tempo por bloco:** cada pedido deixa no log uma linha por bloco (quando começou, quanto durou, quanto ficou no
portão e na fila da trava dele, e se respondeu, atrasou ou quebrou) e uma do total, com um id do pedido feito na
hora: só nomes de bloco e números, nunca o CNPJ nem o que o bloco leu. É o que diz, em produção, por que um bloco
foi para `nao_respondeu_a_tempo` (ensaio de 19/11/2026).

**Sem pessoa:** o cadastro exige empresa (MEI, empresário individual e o que não é empresa não saem, e a análise
inteira volta None); o bloco de sócios só tem pessoa jurídica. O lugar do bloco de pessoas (frente 4) está marcado
em `BLOCOS`.
"""

import contextlib
import contextvars
import copy
import dataclasses
import logging
import secrets
import threading
import time
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from datetime import date

import duckdb

from base.porta import Porta
from src.api_externa import tabelas_por_cnpj
from src.api_externa.conjuntos import (
    Permitido,
    Servido,
    ativos,
    comparaveis,
    credito,
    empresas,
    eventos,
    ficha,
    por_tabela,
    socios_pj,
    vinculos,
)
from src.api_externa.nomes import para_fora
from src.portao_externo import Finalidade

__all__ = [
    "AINDA_NAO_TRAZ",
    "ATRASADO",
    "BLOCOS",
    "CADASTROS",
    "ERRO",
    "RESPONDEU",
    "Analise",
    "Bloco",
    "TempoDoBloco",
    "ainda_nao_traz",
    "blocos_abertos",
    "montar_analise",
]

log = logging.getLogger(__name__)

ANALISE = Finalidade.ANALISE.value
CREDITO = Finalidade.CREDITO.value
PRAZO_EM_SEGUNDOS = 20.0  # abaixo dos 30 s do conector, com folga para a resposta
# a análise é um resumo: a lista inteira de cada bloco está na rota dele. Com 20, a da Vale no ensaio de 18/11
# deu ~100 mil caracteres, perto do teto do conector (120 mil); com 10, cabe com folga um grupo maior
LINHAS_POR_BLOCO = 10
LINHAS_DA_LINHA_DO_TEMPO = 40
DIAS_POR_ANO = 365.25

# (conjunto, finalidade, fonte, campo) de cada linha que o portão libera hoje para a organização
Liberada = tuple[str, str, str, str]
LerBloco = Callable[[Porta, Permitido, int, str, date], Servido | None]


@dataclass(frozen=True)
class Bloco:
    """Um bloco da análise: a chave dele na resposta, o conjunto e a finalidade do contrato, a leitura e o que
    o portão tem de liberar para ele abrir (`exige`: todos estes pares fonte e campo; `algum`: ao menos um
    destes; os dois vazios: qualquer linha do conjunto fora das tabelas do registro). `listas`: as listas do corpo que, todas vazias, querem
    dizer que o bloco não achou nada; `vazio`, a mesma pergunta para o corpo que não é de listas."""

    nome: str
    conjunto: str
    finalidade: str
    ler: LerBloco
    exige: tuple[tuple[str, str], ...] = ()
    listas: tuple[str, ...] = ()
    algum: tuple[tuple[str, str], ...] = ()
    vazio: Callable[[dict], bool] | None = None


def _perfil(
    porta: Porta, permitido: Permitido, _: int, cnpj: str, dia: date
) -> Servido | None:
    servido = ficha.LeitorDeFicha(porta, permitido).ficha(cnpj, dia)
    if servido is None or len(servido.corpo.get("entregas", [])) <= LINHAS_POR_BLOCO:
        return servido
    # as entregas vêm da mais nova à mais velha: a análise leva as mais novas, e a rota do perfil traz todas
    todas = servido.corpo["entregas"]
    corpo = servido.corpo | {"entregas": todas[:LINHAS_POR_BLOCO], "cortada": True}
    return _Lido(
        corpo, servido.fontes, servido.linhas - (len(todas) - LINHAS_POR_BLOCO)
    )


def _empresa(
    porta: Porta, permitido: Permitido, _: int, cnpj: str, dia: date
) -> Servido | None:
    return empresas.LeitorDeEmpresas(porta, permitido).empresa(cnpj, dia)


def _socios(
    porta: Porta, permitido: Permitido, linhas: int, cnpj: str, dia: date
) -> Servido | None:
    return socios_pj.LeitorDeSociosPj(porta, permitido, linhas).socios(cnpj, dia)


def _vinculos(
    porta: Porta, permitido: Permitido, linhas: int, cnpj: str, dia: date
) -> Servido | None:
    return vinculos.LeitorDeVinculos(porta, permitido, linhas).vinculos(cnpj, dia)


def _eventos(
    porta: Porta, permitido: Permitido, linhas: int, cnpj: str, dia: date
) -> Servido | None:
    return eventos.LeitorDeEventos(porta, permitido, linhas).eventos(cnpj, dia)


def _credito(
    porta: Porta, permitido: Permitido, _: int, cnpj: str, dia: date
) -> Servido | None:
    return credito.LeitorDeCredito(porta, permitido).ficha(cnpj, dia)


def _ativos(
    porta: Porta, permitido: Permitido, linhas: int, cnpj: str, dia: date
) -> Servido | None:
    return ativos.LeitorDeAtivos(porta, permitido, linhas).ativos(cnpj, dia)


def _comparaveis(
    porta: Porta, permitido: Permitido, linhas: int, cnpj: str, dia: date
) -> Servido | None:
    return comparaveis.LeitorDeComparaveis(porta, permitido, linhas).comparaveis(
        cnpj, dia
    )


def _do_registro(nome: str) -> Bloco:
    """Um bloco do registro de tabelas ligadas pelo CNPJ (`tabelas_por_cnpj`): abre quando o portão libera um
    campo de uma das tabelas dele (o conjunto, como `profiles`, também tem as linhas de outros blocos)."""
    entradas = tabelas_por_cnpj.do_bloco(nome)
    (conjunto,) = {
        e.conjunto for e in entradas
    }  # um bloco, um conjunto: o consumo é por conjunto

    def ler(
        porta: Porta, permitido: Permitido, linhas: int, cnpj: str, dia: date
    ) -> Servido | None:
        return por_tabela.LeitorPorTabela(porta, permitido, linhas).bloco(
            nome, cnpj, dia
        )

    return Bloco(
        nome,
        conjunto,
        ANALISE,
        ler,
        algum=tuple(par for e in entradas for par in por_tabela.pares(e)),
        vazio=por_tabela.vazio,
    )


CADASTRO = "cadastro"
# o cadastro abre a análise: o perfil (com as entregas à CVM) se a chave o tem, senão a situação na Receita
CADASTROS = (
    Bloco(CADASTRO, ficha.CONJUNTO, ANALISE, _perfil),
    Bloco(CADASTRO, empresas.CONJUNTO, ANALISE, _empresa),
)
BLOCOS = (
    Bloco(
        "socios_pj",
        socios_pj.CONJUNTO,
        ANALISE,
        _socios,
        socios_pj.CAMPOS,
        (socios_pj.SOCIAS, socios_pj.PARTICIPACOES),
    ),
    Bloco("vinculos", vinculos.CONJUNTO, ANALISE, _vinculos, listas=("vinculos",)),
    Bloco("eventos", eventos.CONJUNTO, ANALISE, _eventos, listas=("eventos",)),
    Bloco("credito", credito.CONJUNTO, CREDITO, _credito),
    Bloco("ativos", ativos.CONJUNTO, ANALISE, _ativos),
    Bloco(
        "comparaveis", comparaveis.CONJUNTO, ANALISE, _comparaveis, listas=("pares",)
    ),
    # as tabelas do registro entram sozinhas: entrada nova em `tabelas_por_cnpj` com ONDE_SAI = ANALISE
    *(_do_registro(nome) for nome in tabelas_por_cnpj.blocos(tabelas_por_cnpj.ANALISE)),
    # frente 4: o bloco de pessoas entra aqui, só com a permissão `pessoa_na_tela` da organização conferida no
    # servidor; até lá a análise nunca lê pessoa física
)

# o que a análise não consulta: a mesma frase para toda chave. Sanções, ambiente e lista suja só saem para a
# organização com o conjunto de integridade no contrato (ADR 0122, Emenda 1): para as outras, a frase diz que não
# estão disponíveis nesta chave, sem o motivo (ordem da Diretoria de 18/11/2026); com o bloco aberto, a linha sai
# daqui (o bloco que não achou nada vai para `nao_encontrado`). O bloco de cada linha (None: nenhuma chave o tem)
NAO_DISPONIVEL_NESTA_CHAVE = "não disponível nesta chave"
_AINDA_NAO_TRAZ: tuple[tuple[str | None, str], ...] = (
    (None, "Dívida ativa da União (PGFN)"),
    (
        tabelas_por_cnpj.SANCOES,
        f"Sanções e impedimentos de contratar com o governo (CGU): {NAO_DISPONIVEL_NESTA_CHAVE}",
    ),
    (
        tabelas_por_cnpj.EMBARGOS_AMBIENTAIS,
        f"Autuações e embargos ambientais (IBAMA): {NAO_DISPONIVEL_NESTA_CHAVE}",
    ),
    (
        tabelas_por_cnpj.LISTA_SUJA,
        f"Cadastro de empregadores do trabalho análogo ao de escravo (MTE): {NAO_DISPONIVEL_NESTA_CHAVE}",
    ),
    (None, "Contratos públicos"),
    (None, "Processos judiciais"),
    (None, "Pessoas físicas (sócio pessoa física, administradores)"),
)
# a lista da chave sem nenhum bloco de integridade
AINDA_NAO_TRAZ = tuple(frase for _, frase in _AINDA_NAO_TRAZ)


def ainda_nao_traz(abertos: Iterable[str]) -> list[str]:
    """O que a análise não consulta para esta chave: tira a linha do bloco aberto (o nome de dentro do bloco)."""
    nomes = set(abertos)
    return [frase for bloco, frase in _AINDA_NAO_TRAZ if bloco not in nomes]


LIMITES = (
    (
        "A análise junta os blocos que a organização pode ver, cada um lido como na rota dele e passando pelo "
        "portão do conjunto dele; bloco que não aparece não foi consultado, e isso não diz nada sobre a empresa."
    ),
    (
        "Os itens de ainda_nao_traz não foram consultados: a ausência deles não quer dizer que a empresa não "
        "tem registro nessas bases."
    ),
    (
        "As leituras são dedução do TickerLab a partir dos blocos citados em cada uma, não fato de uma fonte; "
        "nada aqui é recomendação de investimento."
    ),
    (
        f"Cada bloco traz até {LINHAS_POR_BLOCO} linhas por lista (truncated); a rota do bloco traz o resto."
    ),
)
# os valores de `tipo` e de `bloco` saem já com o nome de fora: quem integra procura o bloco pela chave dele
FATO, DEDUCAO = "fact", "inference"
NAO_ACHADO = "O bloco não trouxe dado desta empresa no dia: não achado não quer dizer que não existe."
NAO_RESPONDEU = "O bloco não respondeu a tempo e não entra nesta resposta; a rota dele pode ser pedida à parte."
# do corpo de cada bloco, o que já está no topo da análise
REPETIDOS = ("cnpj", "como_era_em", "limites")


@dataclass(frozen=True)
class _Lido:
    corpo: dict
    fontes: set[str]
    linhas: int


# o estado de cada bloco no log do tempo
RESPONDEU, ATRASADO, ERRO = "respondeu", "atrasado", "erro"
MS = 1000


@dataclass(frozen=True)
class TempoDoBloco:
    """O tempo de um bloco no pedido, em milissegundos: quando começou (desde o início do pedido), quanto durou
    (None: não acabou no prazo), quanto ficou dentro do portão (as perguntas ao banco) e esperando a trava dele."""

    bloco: str  # o nome de fora, o mesmo de `timed_out`
    estado: str
    comecou_ms: int | None
    duracao_ms: int | None
    portao_ms: int
    fila_ms: int

    def linha(self, pedido: str) -> str:
        return (
            f"análise: pedido={pedido} bloco={self.bloco} estado={self.estado} "
            f"comecou_ms={self.comecou_ms} duracao_ms={self.duracao_ms} "
            f"portao_ms={self.portao_ms} fila_portao_ms={self.fila_ms}"
        )


@dataclass(frozen=True)
class Analise:
    """A análise montada: o corpo, as fontes usadas, as linhas e, por (conjunto, finalidade) de cada bloco
    lido, as linhas servidas e se o bloco foi negado (não saiu: vazio ou fora do prazo), para o consumo; e o
    tempo de cada bloco (o que foi ao log)."""

    corpo: dict
    fontes: set[str]
    linhas: int
    consumo: dict[tuple[str, str], tuple[int, bool]] = field(default_factory=dict)
    tempos: tuple[TempoDoBloco, ...] = ()


# as linhas das tabelas do registro: abrem só o bloco delas, nunca o bloco que abre com qualquer linha do conjunto
# (o perfil, em `profiles`, abriria pela ANEEL sem um campo da ficha, e a análise perderia o cadastro da Receita)
_LINHAS_DO_REGISTRO = frozenset(
    par for entrada in tabelas_por_cnpj.REGISTRO for par in por_tabela.pares(entrada)
)


def _aberto(bloco: Bloco, liberadas: set[Liberada]) -> bool:
    do_conjunto = {
        (f, c)
        for conj, fin, f, c in liberadas
        if (conj, fin) == (bloco.conjunto, bloco.finalidade)
    }
    if bloco.exige:
        return set(bloco.exige) <= do_conjunto
    if bloco.algum:
        return bool(set(bloco.algum) & do_conjunto)
    return bool(do_conjunto - _LINHAS_DO_REGISTRO)


def blocos_abertos(
    liberadas: Iterable[Liberada],
) -> tuple[Bloco | None, tuple[Bloco, ...]]:
    """O cadastro que abre a análise (None: a chave não tem nenhum) e os outros blocos abertos para a chave, pelo
    que o portão libera hoje; não depende do CNPJ pedido."""
    linhas = set(liberadas)
    cadastro = next((bloco for bloco in CADASTROS if _aberto(bloco, linhas)), None)
    return cadastro, tuple(bloco for bloco in BLOCOS if _aberto(bloco, linhas))


@dataclass
class _NoPortao:
    """Os segundos de um bloco dentro do portão e na fila da trava dele (somados sob a trava)."""

    dentro: float = 0.0
    fila: float = 0.0


class _PortaoDividido:
    """Os portões dos blocos com uma trava só: a conexão do banco atende um bloco de cada vez e, quando o prazo
    acaba, fecha para todos (o bloco atrasado não toca mais na conexão, que o pedido já devolveu)."""

    def __init__(self, fabrica: Callable[[str, str], Permitido]) -> None:
        self.fabrica = fabrica
        self.trava = threading.Lock()
        self.encerrado = False
        # o bloco que perguntou depois do fim leu com o portão fechado: sai como atrasado, não como "sem dado"
        self.barrados: set[str] = set()
        self.no_portao: dict[str, _NoPortao] = {}

    @contextlib.contextmanager
    def _na_trava(self, bloco: Bloco) -> Iterator[None]:
        """A trava, contando quanto o bloco esperou por ela e quanto ficou com ela."""
        pediu = time.monotonic()
        with self.trava:
            entrou = time.monotonic()
            try:
                yield
            finally:
                conta = self.no_portao.setdefault(bloco.nome, _NoPortao())
                conta.fila += entrou - pediu
                conta.dentro += time.monotonic() - entrou

    def de(self, bloco: Bloco) -> Permitido:
        with self._na_trava(bloco):
            permitido = self.fabrica(bloco.conjunto, bloco.finalidade)

        def dentro(fonte: str, nome: str, derivado: bool) -> bool:
            if (
                self.encerrado
            ):  # depois do fim, "não" na hora, sem entrar na fila da trava
                return self._barrar(bloco)
            with self._na_trava(bloco):
                if self.encerrado:
                    return self._barrar(bloco)
                return permitido(fonte, nome, derivado)

        return dentro

    def _barrar(self, bloco: Bloco) -> bool:
        self.barrados.add(bloco.nome)
        return False

    def encerrar(self) -> None:
        """Fecha o portão para todos e espera só quem já está dentro dele.

        A marca vem antes da trava: quem pergunta depois dela volta "não" sem disputar a trava com o fim do
        prazo (em produção, o fim esperava a fila inteira e o pedido passava de 20 s para 28 a 32 s).
        """
        self.encerrado = True
        with (
            self.trava
        ):  # o bloco que está dentro termina antes de a conexão voltar para o pedido
            pass

    def conta(self, bloco: Bloco) -> _NoPortao:
        """Uma cópia do que o bloco passou no portão até agora."""
        with self.trava:
            conta = self.no_portao.get(bloco.nome, _NoPortao())
            return _NoPortao(conta.dentro, conta.fila)


@dataclass
class _Relogio:
    """O tempo de cada bloco de um pedido, para o log: um id do pedido feito na hora, só para juntar as linhas."""

    inicio: float
    pedido: str = field(default_factory=lambda: secrets.token_hex(4))
    tempos: list[TempoDoBloco] = field(default_factory=list)

    def _ms(self, segundos: float) -> int:
        return round(segundos * MS)

    def anotar(
        self,
        bloco: Bloco,
        estado: str,
        comecou: float | None,
        acabou: float | None,
        no_portao: _NoPortao,
    ) -> None:
        # o atrasado não tem duração: a consulta dele foi interrompida, e o fim que ela marca não é o do bloco
        duracao = None
        if estado != ATRASADO and comecou is not None and acabou is not None:
            duracao = self._ms(acabou - comecou)
        self.tempos.append(
            TempoDoBloco(
                para_fora(bloco.nome),
                estado,
                None if comecou is None else self._ms(comecou - self.inicio),
                duracao,
                self._ms(no_portao.dentro),
                self._ms(no_portao.fila),
            )
        )

    def registrar(self, prazo: float) -> None:
        for tempo in self.tempos:
            log.info(tempo.linha(self.pedido))
        atrasados = sum(t.estado == ATRASADO for t in self.tempos)
        log.info(
            "análise: pedido=%s total_ms=%d prazo_ms=%d blocos=%d atrasados=%d",
            self.pedido,
            self._ms(time.monotonic() - self.inicio),
            self._ms(prazo),
            len(self.tempos),
            atrasados,
        )


def _cursor(porta: Porta) -> Porta:
    """Outra porta com as mesmas views e um cursor próprio (o mesmo jeito da `porta_compartilhada`), sem o
    registro de coletas: o bloco não toca no banco por fora do portão."""
    copia = copy.copy(porta)
    copia.con = porta.con.cursor()
    copia.con.execute("SET TimeZone = 'UTC'")
    copia.banco = None
    return copia


@dataclass
class _Tarefa:
    bloco: Bloco
    porta: Porta
    futuro: Future | None = None
    # time.monotonic() do começo e do fim da leitura, gravados pela linha de execução do bloco
    comecou: float | None = None
    acabou: float | None = None


def _ler_no_cursor(
    tarefa: _Tarefa, permitido: Permitido, linhas: int, cnpj: str, dia: date
) -> Servido | None:
    tarefa.comecou = time.monotonic()
    try:
        return tarefa.bloco.ler(tarefa.porta, permitido, linhas, cnpj, dia)
    finally:
        tarefa.acabou = time.monotonic()
        tarefa.porta.fechar()


def _ler_ao_mesmo_tempo(
    porta: Porta,
    blocos: tuple[Bloco, ...],
    portoes: _PortaoDividido,
    linhas: int,
    cnpj: str,
    dia: date,
    prazo: float,
    relogio: _Relogio,
) -> tuple[dict[str, Servido | None], list[str]]:
    """Cada bloco no próprio cursor e na própria linha de execução; o que passa do prazo é interrompido. O tempo
    de cada um vai para o `relogio`, também quando um bloco quebra."""
    limite = time.monotonic() + prazo
    tarefas = [_Tarefa(bloco, _cursor(porta)) for bloco in blocos]
    # os portões de todos antes do primeiro bloco: montar um pergunta ao banco, e com blocos já correndo cada
    # montagem esperava a trava (em produção, o último bloco começava 15 s depois do primeiro)
    permitidos = [portoes.de(tarefa.bloco) for tarefa in tarefas]
    executor = ThreadPoolExecutor(
        max_workers=max(len(tarefas), 1), thread_name_prefix="analise"
    )
    try:
        for tarefa, permitido in zip(tarefas, permitidos, strict=True):
            # o contexto do pedido vai junto: o registro do piloto (D11) é o mesmo para todos os blocos
            contexto = contextvars.copy_context()
            tarefa.futuro = executor.submit(
                contexto.run, _ler_no_cursor, tarefa, permitido, linhas, cnpj, dia
            )
        wait(
            [t.futuro for t in tarefas if t.futuro],
            timeout=max(limite - time.monotonic(), 0.0),
        )
    finally:
        portoes.encerrar()
        executor.shutdown(wait=False, cancel_futures=True)
    terminadas = [
        t for t in tarefas if _terminou(t)
    ]  # todas antes do erro: as atrasadas são interrompidas
    for tarefa in tarefas:
        relogio.anotar(
            tarefa.bloco,
            _estado(tarefa, tarefa in terminadas, portoes),
            tarefa.comecou,
            tarefa.acabou,
            portoes.conta(tarefa.bloco),
        )
    for tarefa in terminadas:
        erro = tarefa.futuro.exception()  # type: ignore[union-attr]
        if erro is not None:
            raise erro  # o erro de um bloco que respondeu sobe: a rota responde 503, como na rota dele
    lidos: dict[str, Servido | None] = {}
    atrasados: list[str] = []
    for tarefa in tarefas:
        if tarefa in terminadas and tarefa.bloco.nome not in portoes.barrados:
            lidos[tarefa.bloco.nome] = tarefa.futuro.result()  # type: ignore[union-attr]
        else:
            atrasados.append(tarefa.bloco.nome)
    return lidos, atrasados


def _estado(tarefa: _Tarefa, terminou: bool, portoes: _PortaoDividido) -> str:
    if not terminou or tarefa.bloco.nome in portoes.barrados:
        return ATRASADO
    return ERRO if tarefa.futuro.exception() is not None else RESPONDEU  # type: ignore[union-attr]


def _terminou(tarefa: _Tarefa) -> bool:
    """Se o bloco respondeu no prazo; o que não respondeu tem a consulta interrompida."""
    futuro = tarefa.futuro
    if futuro is not None and futuro.done() and not futuro.cancelled():
        return True
    if futuro is None or futuro.cancelled():
        tarefa.porta.fechar()  # não chegou a correr: o cursor é fechado aqui
        return False
    with contextlib.suppress(duckdb.Error, RuntimeError):
        # o bloco pode ter acabado entre a pergunta e a interrupção: o cursor já fechado não importa
        tarefa.porta.con.interrupt()
    return False


def montar_analise(
    cnpj: str,
    dia: date,
    *,
    porta: Porta,
    liberadas: Iterable[Liberada],
    portao: Callable[[str, str], Permitido],
    linhas: int,
    prazo: float = PRAZO_EM_SEGUNDOS,
) -> Analise | None:
    """A análise do CNPJ como era em `dia`, com os blocos abertos para a chave; None se nenhum cadastro está
    aberto ou se o CNPJ não é de empresa (o mesmo `not_available` das rotas do bloco). `portao(conjunto,
    finalidade)` dá o portão de cada bloco; `liberadas`, as linhas que o portão libera hoje (o catálogo)."""
    relogio = _Relogio(time.monotonic())
    cadastro, outros = blocos_abertos(liberadas)
    if cadastro is None:
        return None
    try:
        return _montar(
            cnpj, dia, porta, cadastro, outros, portao, linhas, prazo, relogio
        )
    finally:
        relogio.registrar(prazo)


def _ler_o_cadastro(
    cadastro: Bloco,
    porta: Porta,
    portoes: _PortaoDividido,
    linhas: int,
    cnpj: str,
    dia: date,
    relogio: _Relogio,
) -> Servido | None:
    comecou = time.monotonic()
    estado = ERRO
    try:
        lido = cadastro.ler(porta, portoes.de(cadastro), linhas, cnpj, dia)
        estado = RESPONDEU
        return lido
    finally:
        relogio.anotar(
            cadastro, estado, comecou, time.monotonic(), portoes.conta(cadastro)
        )


def _montar(
    cnpj: str,
    dia: date,
    porta: Porta,
    cadastro: Bloco,
    outros: tuple[Bloco, ...],
    portao: Callable[[str, str], Permitido],
    linhas: int,
    prazo: float,
    relogio: _Relogio,
) -> Analise:
    portoes = _PortaoDividido(portao)
    linhas_do_bloco = max(min(linhas, LINHAS_POR_BLOCO), 1)
    lido = _ler_o_cadastro(
        cadastro, porta, portoes, linhas_do_bloco, cnpj, dia, relogio
    )
    consumo = {
        (cadastro.conjunto, cadastro.finalidade): (
            0 if lido is None else lido.linhas,
            lido is None,
        )
    }
    if lido is None:
        return Analise({}, set(), 0, consumo, tuple(relogio.tempos))
    restante = prazo - (time.monotonic() - relogio.inicio)
    lidos, atrasados = _ler_ao_mesmo_tempo(
        porta, outros, portoes, linhas_do_bloco, cnpj, dia, restante, relogio
    )
    for bloco in outros:
        servido = lidos.get(bloco.nome)
        # dois blocos do mesmo conjunto (o cadastro e os regulados, em `profiles`) somam as linhas, e o conjunto
        # só conta como negado se nenhum dos dois saiu
        linhas_antes, negado_antes = consumo.get(
            (bloco.conjunto, bloco.finalidade), (0, True)
        )
        consumo[(bloco.conjunto, bloco.finalidade)] = (
            linhas_antes + (0 if servido is None else servido.linhas),
            negado_antes and servido is None,
        )
    montada = _Montagem(cadastro, lido, outros, lidos, atrasados, dia).analise(consumo)
    return dataclasses.replace(montada, tempos=tuple(relogio.tempos))


def _valor(envelope: object) -> object:
    return envelope.get("valor") if isinstance(envelope, dict) else None


def _texto(envelope: object) -> str | None:
    valor = _valor(envelope)
    return None if valor in (None, "") else str(valor)


@dataclass(frozen=True)
class _Marco:
    dia: str
    o_que: str
    bloco: str
    envelope: dict

    def item(self) -> dict:
        return {
            "dia": self.dia,
            "o_que": self.o_que,
            "bloco": para_fora(self.bloco),
            "fonte": self.envelope.get("fonte"),
            "publico_em": self.envelope.get("publico_em"),
        }


def _marco(envelope: object, o_que: str, bloco: str) -> Iterator[_Marco]:
    dia = _texto(envelope)
    if dia is not None and isinstance(envelope, dict):
        yield _Marco(dia[:10], o_que, bloco, envelope)


def _campos_do_cadastro(corpo: dict) -> dict:
    """Os campos do cadastro na Receita: dentro de `cadastro_na_receita` no perfil, soltos na situação."""
    dentro = corpo.get("cadastro_na_receita")
    return dentro if isinstance(dentro, dict) else corpo


def _frase(cadastro: dict) -> dict:
    """A frase do topo, só com o que o cadastro serviu: fato da Receita, sem adjetivo nem conta."""
    campos = _campos_do_cadastro(cadastro)
    nome = _texto(campos.get("razao_social")) or "A empresa"
    partes = [nome]
    situacao = _texto(campos.get("situacao_cadastral_texto"))
    if situacao:
        partes.append(f"situação {situacao.lower()} na Receita")
    atividade = _texto(campos.get("cnae_principal_texto"))
    if atividade:
        partes.append(f"atividade principal: {atividade}")
    lugar = "/".join(
        p
        for p in (_texto(campos.get("municipio_texto")), _texto(campos.get("uf")))
        if p
    )
    if lugar:
        partes.append(f"sede em {lugar}")
    inicio = _texto(campos.get("data_inicio_atividade"))
    if inicio:
        partes.append(f"início da atividade em {inicio}")
    usados = [
        chave for chave in campos if chave in _CAMPOS_DA_FRASE and _texto(campos[chave])
    ]
    return {
        "texto": "; ".join(partes) + ".",
        "tipo": FATO,
        "a_partir_de": [para_fora(CADASTRO), *map(para_fora, usados)],
    }


_CAMPOS_DA_FRASE = (
    "razao_social",
    "situacao_cadastral_texto",
    "cnae_principal_texto",
    "municipio_texto",
    "uf",
    "data_inicio_atividade",
)
TEXTO_DO_VINCULO = {
    "subsidiary_of": "é controlada de",
    "affiliate_of": "é coligada de",
    "investee_of": "é participada de",
    "audits": "audita",
}


def _nome_da_ponta(ponta: object) -> str:
    if not isinstance(ponta, dict):
        return "?"
    return _texto(ponta.get("razao_social")) or str(ponta.get("raiz_do_cnpj") or "?")


def _marcos_do_cadastro(corpo: dict) -> Iterator[_Marco]:
    campos = _campos_do_cadastro(corpo)
    yield from _marco(
        campos.get("data_inicio_atividade"), "Início da atividade (Receita)", CADASTRO
    )
    situacao = _texto(campos.get("situacao_cadastral_texto")) or _texto(
        campos.get("situacao_cadastral")
    )
    yield from _marco(
        campos.get("data_situacao_cadastral"),
        f"Situação cadastral passou a {situacao or 'a atual'} (Receita)",
        CADASTRO,
    )


def _marcos_dos_socios(corpo: dict) -> Iterator[_Marco]:
    for item in corpo.get(socios_pj.SOCIAS, []):
        nome = _texto(item.get("razao_social")) or item.get("raiz_do_cnpj")
        yield from _marco(
            item.get("data_entrada"), f"Entrada da sócia {nome}", "socios_pj"
        )
    for item in corpo.get(socios_pj.PARTICIPACOES, []):
        nome = _texto(item.get("razao_social")) or item.get("raiz_do_cnpj")
        yield from _marco(
            item.get("data_entrada"), f"Passa a ser sócia de {nome}", "socios_pj"
        )


def _marcos_dos_vinculos(corpo: dict) -> Iterator[_Marco]:
    for item in corpo.get("vinculos", []):
        texto = TEXTO_DO_VINCULO.get(str(_valor(item.get("tipo"))), "tem vínculo com")
        o_que = f"{_nome_da_ponta(item.get('de'))} {texto} {_nome_da_ponta(item.get('para'))}"
        yield from _marco(item.get("aconteceu_em"), o_que, "vinculos")


def _marcos_dos_eventos(corpo: dict) -> Iterator[_Marco]:
    for item in corpo.get("eventos", []):
        if item.get("tipo_de_evento") == eventos.TROCA_DE_AUDITOR:
            novo = _texto(item.get("novo")) or "novo auditor"
            yield from _marco(
                item.get("efetiva_em"), f"Troca de auditor para {novo}", "eventos"
            )
            continue
        # dos documentos do IPE, só o fato relevante vira marco: comunicado e aviso encheriam a linha do tempo
        if _texto(item.get("categoria")) == FATO_RELEVANTE:
            yield from _marco(item.get("referencia"), "Fato relevante (CVM)", "eventos")


FATO_RELEVANTE = "Fato Relevante"
MARCOS = {
    CADASTRO: _marcos_do_cadastro,
    "socios_pj": _marcos_dos_socios,
    "vinculos": _marcos_dos_vinculos,
    "eventos": _marcos_dos_eventos,
}


def _vazio(bloco: Bloco, corpo: dict) -> bool:
    if bloco.vazio is not None:
        return bloco.vazio(corpo)
    return bool(bloco.listas) and all(not corpo.get(lista) for lista in bloco.listas)


class _Montagem:
    """O corpo da análise a partir dos blocos lidos."""

    def __init__(
        self,
        cadastro: Bloco,
        lido: Servido,
        outros: tuple[Bloco, ...],
        lidos: dict[str, Servido | None],
        atrasados: list[str],
        dia: date,
    ) -> None:
        self.cadastro = cadastro
        self.lido = lido
        self.outros = outros
        self.lidos = lidos
        self.atrasados = atrasados
        self.dia = dia

    def _servidos(self) -> dict[str, Servido]:
        servidos: dict[str, Servido] = {CADASTRO: self.lido}
        for bloco in self.outros:
            servido = self.lidos.get(bloco.nome)
            if servido is not None:
                servidos[bloco.nome] = servido
        return servidos

    def _nao_encontrado(self) -> list[dict]:
        nao = []
        for bloco in self.outros:
            if bloco.nome in self.atrasados:
                continue
            servido = self.lidos.get(bloco.nome)
            if servido is None or _vazio(bloco, servido.corpo):
                nao.append({"bloco": para_fora(bloco.nome), "por_que": NAO_ACHADO})
        return nao

    def _linha_do_tempo(self, servidos: dict[str, Servido]) -> tuple[list[dict], bool]:
        marcos = [
            marco
            for nome, servido in servidos.items()
            if nome in MARCOS
            for marco in MARCOS[nome](servido.corpo)
            if marco.dia
            <= self.dia.isoformat()  # a data de referência de um aviso pode estar adiante
        ]
        marcos.sort(key=lambda m: (m.dia, m.bloco, m.o_que))
        cortada = len(marcos) > LINHAS_DA_LINHA_DO_TEMPO
        return [m.item() for m in marcos[-LINHAS_DA_LINHA_DO_TEMPO:]], cortada

    def _leituras(self, servidos: dict[str, Servido]) -> list[dict]:
        return [leitura for ler in LEITURAS for leitura in ler(servidos, self.dia)]

    def analise(self, consumo: dict[tuple[str, str], tuple[int, bool]]) -> Analise:
        servidos = self._servidos()
        linha_do_tempo, cortada = self._linha_do_tempo(servidos)
        limites = list(LIMITES)
        for servido in servidos.values():
            limites += [t for t in servido.corpo.get("limites", []) if t not in limites]
        if cortada:
            limites.append(
                f"A linha do tempo traz os {LINHAS_DA_LINHA_DO_TEMPO} marcos mais novos dos blocos desta resposta."
            )
        corpo = {
            "cnpj": self.lido.corpo.get("cnpj"),
            "como_era_em": self.dia.isoformat(),
            "frase": _frase(self.lido.corpo),
            "blocos": {
                nome: {k: v for k, v in servido.corpo.items() if k not in REPETIDOS}
                for nome, servido in servidos.items()
            },
            "linha_do_tempo": linha_do_tempo,
            "leituras": self._leituras(servidos),
            "nao_encontrado": self._nao_encontrado(),
            "nao_respondeu_a_tempo": [
                {"bloco": para_fora(nome), "por_que": NAO_RESPONDEU}
                for nome in self.atrasados
            ],
            "ainda_nao_traz": ainda_nao_traz(bloco.nome for bloco in self.outros),
            "pedidos_usados": len(consumo),
            "limites": limites,
        }
        fontes = {fonte for servido in servidos.values() for fonte in servido.fontes}
        return Analise(corpo, fontes, sum(s.linhas for s in servidos.values()), consumo)


def _deducao(texto: str, *blocos: str) -> dict:
    return {
        "texto": texto,
        "tipo": DEDUCAO,
        "a_partir_de": [para_fora(bloco) for bloco in blocos],
    }


def _leitura_da_idade(servidos: dict[str, Servido], dia: date) -> Iterator[dict]:
    inicio = _texto(
        _campos_do_cadastro(servidos[CADASTRO].corpo).get("data_inicio_atividade")
    )
    if inicio is None:
        return
    anos = int((dia - date.fromisoformat(inicio[:10])).days / DIAS_POR_ANO)
    if anos >= 0:
        yield _deducao(
            f"Cerca de {anos} anos de atividade no dia pedido, pela data de início na Receita.",
            CADASTRO,
        )


def _leitura_da_cvm(servidos: dict[str, Servido], _: date) -> Iterator[dict]:
    if servidos[CADASTRO].corpo.get("entregas"):
        yield _deducao(
            "Entrega DFP ou ITR à CVM: é ou foi companhia registrada na CVM, com demonstrações públicas.",
            CADASTRO,
        )


def _leitura_do_grupo(servidos: dict[str, Servido], _: date) -> Iterator[dict]:
    if "vinculos" not in servidos:
        return
    raiz = str(servidos[CADASTRO].corpo.get("cnpj") or "")[:8]
    corpo = servidos["vinculos"].corpo
    itens = corpo.get("vinculos", [])
    controladoras = {
        _nome_da_ponta(i.get("para"))
        for i in itens
        if _valor(i.get("tipo")) == "subsidiary_of"
        and (i.get("de") or {}).get("raiz_do_cnpj") == raiz
    }
    controladas = {
        _nome_da_ponta(i.get("de"))
        for i in itens
        if _valor(i.get("tipo")) == "subsidiary_of"
        and (i.get("para") or {}).get("raiz_do_cnpj") == raiz
    }
    if controladoras:
        yield _deducao(
            f"Faz parte de um grupo: aparece como controlada de {', '.join(sorted(controladoras))}.",
            "vinculos",
        )
    if controladas:
        yield _deducao(
            f"Controla {'pelo menos ' if corpo.get('cortada') else ''}{len(controladas)} empresa(s) declarada(s) "
            "no FRE.",
            "vinculos",
        )


def _leitura_dos_socios(servidos: dict[str, Servido], _: date) -> Iterator[dict]:
    if "socios_pj" not in servidos:
        return
    corpo = servidos["socios_pj"].corpo
    socias, participacoes = (
        corpo.get(socios_pj.SOCIAS, []),
        corpo.get(socios_pj.PARTICIPACOES, []),
    )
    quantos = "pelo menos " if corpo.get("cortada") else ""
    if socias:
        yield _deducao(
            f"Tem {quantos}{len(socias)} sócia(s) pessoa jurídica no quadro do dia: há holding ou outra empresa "
            "no controle ou no capital.",
            "socios_pj",
        )
    if participacoes:
        yield _deducao(
            f"É sócia de {quantos}{len(participacoes)} empresa(s) no quadro do dia.",
            "socios_pj",
        )


LEITURAS = (_leitura_da_idade, _leitura_da_cvm, _leitura_do_grupo, _leitura_dos_socios)
