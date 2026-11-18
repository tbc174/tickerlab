"""A análise completa de um CNPJ numa chamada: cada bloco que a chave pode ver, com fonte e data (frente 3, 18/11/2026).

`montar_analise` junta, para um CNPJ e um dia (`known_at`), os blocos das rotas por CNPJ que já existem (cadastro,
sócios PJ, vínculos, eventos, crédito, ativos e comparáveis) na ordem de `docs/padrao-de-analise.md`: uma frase no
topo (só com o que o cadastro serviu), os blocos, a linha do tempo (só com datas que vieram nos blocos), as leituras
(dedução, marcada e separada dos fatos), o que não foi achado, o que a análise não traz e os limites.

**Cada bloco passa pelo portão do próprio conjunto**, com a finalidade do contrato dele: é a mesma decisão de
chamar a rota do bloco, e a análise não libera nada novo. Se o bloco está aberto decide-se **antes de ler a
empresa**, pelas linhas que o portão libera hoje para a organização (contrato, linha de direito, prontidão, coleta
e guarda): bloco fechado não é lido, não aparece em lugar nenhum da resposta e não muda o tempo nem o tamanho dela
conforme a empresa. Tabela que ganha prontidão num conjunto lido aqui entra sozinha, sem mudar este arquivo.

**Prazo:** depois do cadastro, os outros blocos correm ao mesmo tempo, cada um no próprio cursor da porta; o que
passa do prazo tem a consulta interrompida e sai em `nao_respondeu_a_tempo`. A conexão do banco (o portão) é usada
por um bloco de cada vez e fecha para todos quando o prazo acaba.

**Sem pessoa:** o cadastro exige empresa (MEI, empresário individual e o que não é empresa não saem, e a análise
inteira volta None); o bloco de sócios só tem pessoa jurídica. O lugar do bloco de pessoas (frente 4) está marcado
em `BLOCOS`.
"""

import contextlib
import contextvars
import copy
import threading
import time
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from datetime import date

import duckdb

from base.porta import Porta
from src.api_externa.conjuntos import (
    Permitido,
    Servido,
    ativos,
    comparaveis,
    credito,
    empresas,
    eventos,
    ficha,
    socios_pj,
    vinculos,
)
from src.api_externa.nomes import para_fora
from src.portao_externo import Finalidade

__all__ = [
    "AINDA_NAO_TRAZ",
    "BLOCOS",
    "CADASTROS",
    "Analise",
    "Bloco",
    "blocos_abertos",
    "montar_analise",
]

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
    o portão tem de liberar para ele abrir (`exige`, pares fonte e campo; vazio: qualquer linha do conjunto).
    `listas`: as listas do corpo que, todas vazias, querem dizer que o bloco não achou nada."""

    nome: str
    conjunto: str
    finalidade: str
    ler: LerBloco
    exige: tuple[tuple[str, str], ...] = ()
    listas: tuple[str, ...] = ()


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
    # frente 4: o bloco de pessoas entra aqui, só com a permissão `pessoa_na_tela` da organização conferida no
    # servidor; até lá a análise nunca lê pessoa física
)

# o que a análise não consulta para nenhuma chave hoje (sem linha de direito na API): a mesma frase para todas
AINDA_NAO_TRAZ = (
    "Dívida ativa da União (PGFN)",
    "Sanções e impedimentos de contratar com o governo (CGU)",
    "Autuações e embargos ambientais (IBAMA)",
    "Cadastro de empregadores do trabalho análogo ao de escravo (MTE)",
    "Contratos públicos",
    "Processos judiciais",
    "Pessoas físicas (sócio pessoa física, administradores)",
)
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


@dataclass(frozen=True)
class Analise:
    """A análise montada: o corpo, as fontes usadas, as linhas e, por (conjunto, finalidade) de cada bloco
    lido, as linhas servidas e se o bloco foi negado (não saiu: vazio ou fora do prazo), para o consumo."""

    corpo: dict
    fontes: set[str]
    linhas: int
    consumo: dict[tuple[str, str], tuple[int, bool]] = field(default_factory=dict)


def _aberto(bloco: Bloco, liberadas: set[Liberada]) -> bool:
    do_conjunto = {
        (f, c)
        for conj, fin, f, c in liberadas
        if (conj, fin) == (bloco.conjunto, bloco.finalidade)
    }
    if bloco.exige:
        return set(bloco.exige) <= do_conjunto
    return bool(do_conjunto)


def blocos_abertos(
    liberadas: Iterable[Liberada],
) -> tuple[Bloco | None, tuple[Bloco, ...]]:
    """O cadastro que abre a análise (None: a chave não tem nenhum) e os outros blocos abertos para a chave, pelo
    que o portão libera hoje; não depende do CNPJ pedido."""
    linhas = set(liberadas)
    cadastro = next((bloco for bloco in CADASTROS if _aberto(bloco, linhas)), None)
    return cadastro, tuple(bloco for bloco in BLOCOS if _aberto(bloco, linhas))


class _PortaoDividido:
    """Os portões dos blocos com uma trava só: a conexão do banco atende um bloco de cada vez e, quando o prazo
    acaba, fecha para todos (o bloco atrasado não toca mais na conexão, que o pedido já devolveu)."""

    def __init__(self, fabrica: Callable[[str, str], Permitido]) -> None:
        self.fabrica = fabrica
        self.trava = threading.Lock()
        self.encerrado = False

    def de(self, bloco: Bloco) -> Permitido:
        with self.trava:
            permitido = self.fabrica(bloco.conjunto, bloco.finalidade)

        def dentro(fonte: str, nome: str, derivado: bool) -> bool:
            with self.trava:
                return not self.encerrado and permitido(fonte, nome, derivado)

        return dentro

    def encerrar(self) -> None:
        with self.trava:
            self.encerrado = True


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


def _ler_no_cursor(
    tarefa: _Tarefa, permitido: Permitido, linhas: int, cnpj: str, dia: date
) -> Servido | None:
    try:
        return tarefa.bloco.ler(tarefa.porta, permitido, linhas, cnpj, dia)
    finally:
        tarefa.porta.fechar()


def _ler_ao_mesmo_tempo(
    porta: Porta,
    blocos: tuple[Bloco, ...],
    portoes: _PortaoDividido,
    linhas: int,
    cnpj: str,
    dia: date,
    prazo: float,
) -> tuple[dict[str, Servido | None], list[str]]:
    """Cada bloco no próprio cursor e na própria linha de execução; o que passa do prazo é interrompido."""
    tarefas = [_Tarefa(bloco, _cursor(porta)) for bloco in blocos]
    executor = ThreadPoolExecutor(
        max_workers=max(len(tarefas), 1), thread_name_prefix="analise"
    )
    try:
        for tarefa in tarefas:
            # o contexto do pedido vai junto: o registro do piloto (D11) é o mesmo para todos os blocos
            contexto = contextvars.copy_context()
            permitido = portoes.de(tarefa.bloco)
            tarefa.futuro = executor.submit(
                contexto.run, _ler_no_cursor, tarefa, permitido, linhas, cnpj, dia
            )
        wait([t.futuro for t in tarefas if t.futuro], timeout=max(prazo, 0.0))
    finally:
        portoes.encerrar()
        executor.shutdown(wait=False, cancel_futures=True)
    lidos: dict[str, Servido | None] = {}
    atrasados: list[str] = []
    for tarefa in tarefas:
        if _terminou(tarefa):
            lidos[tarefa.bloco.nome] = tarefa.futuro.result()  # type: ignore[union-attr]
        else:
            atrasados.append(tarefa.bloco.nome)
    return lidos, atrasados


def _terminou(tarefa: _Tarefa) -> bool:
    """Se o bloco respondeu no prazo; o que não respondeu tem a consulta interrompida (o erro de um bloco que
    respondeu sobe: a rota responde 503, como na rota dele)."""
    futuro = tarefa.futuro
    if futuro is not None and futuro.done() and not futuro.cancelled():
        erro = futuro.exception()
        if erro is not None:
            raise erro
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
    inicio = time.monotonic()
    cadastro, outros = blocos_abertos(liberadas)
    if cadastro is None:
        return None
    portoes = _PortaoDividido(portao)
    linhas_do_bloco = max(min(linhas, LINHAS_POR_BLOCO), 1)
    lido = cadastro.ler(porta, portoes.de(cadastro), linhas_do_bloco, cnpj, dia)
    consumo = {
        (cadastro.conjunto, cadastro.finalidade): (
            0 if lido is None else lido.linhas,
            lido is None,
        )
    }
    if lido is None:
        return Analise({}, set(), 0, consumo)
    restante = prazo - (time.monotonic() - inicio)
    lidos, atrasados = _ler_ao_mesmo_tempo(
        porta, outros, portoes, linhas_do_bloco, cnpj, dia, restante
    )
    for bloco in outros:
        servido = lidos.get(bloco.nome)
        consumo[(bloco.conjunto, bloco.finalidade)] = (
            0 if servido is None else servido.linhas,
            servido is None,
        )
    return _Montagem(cadastro, lido, outros, lidos, atrasados, dia).analise(consumo)


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
            "ainda_nao_traz": list(AINDA_NAO_TRAZ),
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
