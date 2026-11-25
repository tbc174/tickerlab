"""Quem já se mexeu num setor, na API externa (linha 810, PR 4): `GET /data/v1/buyers`, só pessoa jurídica.

`LeitorDeCompradores(porta, permitido, linhas_maximas).compradores(pedido, como_era_em)` parte das empresas com
estabelecimento ativo do CNAE pedido (e na UF, se pedida) no retrato da Receita que valia no dia, e lista, em
tipos simples e com as chaves em português (a rota traduz na saída), as empresas que deram algum destes sinais:

- `took_stake`: entrou como sócia PJ de uma empresa do setor na janela de `anos` (a tabela
  `entradas_de_socio_pj`, fonte `rfb-cnpj`). Não conta quem entrou até a abertura da empresa (fundador) nem a
  entrada dentro do mesmo grupo (uma era sócia da outra, ou as duas tinham uma sócia PJ em comum no dia). Conta
  também a entrada em empresa do setor que hoje está baixada (linha 1042): consolidador que incorpora o que compra
  faz a empresa sumir do retrato ativo, e era o histórico dele que sumia junto. A empresa baixada só entra na
  conta como lugar onde alguém entrou: `empresas_ativas` segue contando só as ativas;
- `fund_stake`: um FIP (registro de fundos da CVM, fonte `cvm-fidc-base`) que era sócio de uma empresa do
  setor no dia;
- `controls_in_sector`: a companhia aberta que, no FRE mais recente já entregue no dia, tinha uma controlada ou
  coligada no setor (`controladas`, fonte `cvm-hist-fre`).

No VPS os dois últimos sinais leem as cópias reduzidas com nome próprio (`controladas_pj` e `fips_registrados`,
linha 844, montadas e travadas por `base/recorte_dos_compradores.py`): só raízes da lista sem pessoa, sem razão
social, gestor nem administrador. A resposta é a mesma; quando a porta tem a tabela inteira, vale a inteira.

Cada comprador sai com a raiz do CNPJ, a razão social (em envelope) e, por sinal, quantas provas e até
`EXEMPLOS_POR_SINAL` exemplos, cada campo com a fonte e o dia em que ficou público. A ordem é pelo número de
entradas como sócia (compras de terceiros) e depois pelo de sinais, sem desempate pela data, e não por chance de compra. O sinal que não foi consultado (o portão não o libera
ou a porta não tem a tabela dele) não some em silêncio (linha 881, `src/api_externa/nao_disponivel.py`): ele vai
em `sinais_nao_disponiveis`, com o nome de fora, e os limites só falam dos sinais consultados.

**Sem pessoa:** o setor sai da lista sem pessoa da Receita (`cnpj_estabelecimentos_pj` e `cnpj_empresas_pj`,
linha 584), e todo comprador tem de estar em `cnpj_empresas_pj` no mesmo retrato; quem não está (MEI, empresário
individual, grupo 4) não sai. A tabela de entradas só tem sócio do tipo 1 (PJ), e o quadro de sócios com pessoa
não é lido. O sinal das páginas das assessorias (`ma_partes`) é de uso interno e não existe aqui.

**Sem olhar o futuro:** o retrato do setor e dos nomes é o mais novo já público no dia; a entrada só conta
depois de pública (`publico_em`) e com a data de entrada até o dia; o quadro de sócios do dia é refeito das
entradas e saídas já públicas; o FIP precisa estar registrado e não cancelado no dia; o FRE só conta depois de
recebido pela CVM, e a versão mais nova já recebida.
"""

import copy
import threading
from collections import OrderedDict, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from base.porta import Porta
from base.porta.duckdb import (
    arquivos_da_tabela,
    condicao_como_era,
    dia_de,
    nome_da_view,
)
from base.porta.rede import views
from src.api_externa import nao_disponivel
from src.api_externa.conjuntos import Permitido
from src.api_externa.envelope import campo
from src.api_externa.porta_compartilhada import lembrar

CONJUNTO = "buyers"
RECEITA, FRE, REGISTRO = "rfb-cnpj", "cvm-hist-fre", "cvm-fidc-base"
ESTABELECIMENTOS, EMPRESAS = "cnpj_estabelecimentos_pj", "cnpj_empresas_pj"
# a situação cadastral versão por versão (só PJ): dela vêm a data e o motivo da baixa das empresas baixadas
SITUACAO = "cnpj_situacao_cadastral"
# o código do erro do pedido anterior ao primeiro retrato da Receita, que vem com a primeira data que funciona
# (`first_known_at`); letras e sublinhado, como os outros códigos, para o conector poder repeti-lo
ANTES_DO_PRIMEIRO_RETRATO = "known_at_before_first_snapshot"
ENTRADAS, CONTROLADAS, FUNDOS = (
    "entradas_de_socio_pj",
    "controladas",
    "registro_de_fundos",
)
# No VPS a lista lê as cópias reduzidas, com nome próprio (linha 844, `base/recorte_dos_compradores.py`): só
# PJ, sem razão social, gestor nem administrador. Cada sinal lê a primeira opção que a porta tem. O FIP só lê a
# cópia, a tabela que o portão confere: o registro inteiro tem CNPJ_Fundo fora da lista sem pessoa e, sem a
# cópia na porta, o sinal fica de fora (Diretoria, 12/11). O modo dono, em casa, tem a lista própria e não passa
# por aqui. Na controlada, a inteira ainda vale quando as duas estão (linha 892, depois de 20/11).
CONTROLADAS_PJ, FIPS_REGISTRADOS = "controladas_pj", "fips_registrados"
LEITURAS = {
    CONTROLADAS: (CONTROLADAS, CONTROLADAS_PJ),
    FUNDOS: (FIPS_REGISTRADOS,),
}
PUBLICADO_EM, MES = "publico_em", "mes_do_retrato"
ATIVA, BAIXADA, FIP = "02", "08", "FIP"
# os campos que o portão confere para mostrar a baixa (situação, data e motivo), da mesma fonte da razão social
CAMPOS_DA_BAIXA = tuple(
    (RECEITA, nome)
    for nome in ("situacao_cadastral", "data_situacao_cadastral", "motivo_situacao")
)
ANOS_PADRAO, ANOS_MAXIMO = 3, 10
LIMITE_PADRAO, LIMITE_MAXIMO = 20, 50
EXEMPLOS_POR_SINAL = 5
TAMANHOS_DO_CNAE = (5, 7)  # a classe ou a subclasse
UFS = frozenset({
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA",
    "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
})  # fmt: skip
DIAS_POR_ANO = 365.25
# a baixa de uma empresa: o dia da baixa, o código do motivo como a Receita publica e o dia em que a versão ficou pública
Baixa = tuple[date, str, date]

# o sinal: a chave das provas (traduzida em `nomes.py`) e o nome que sai na lista `sinais` (já de fora)
ENTROU, FUNDO, CONTROLA = "entrou_como_socio", "fundo_socio", "controla_no_setor"
NOME_DE_FORA = {
    ENTROU: "took_stake",
    FUNDO: "fund_stake",
    CONTROLA: "controls_in_sector",
}
# o que o portão tem de liberar para o sinal sair: (fonte, campo da base)
CAMPOS_DO_SINAL = {
    ENTROU: ((RECEITA, "data_entrada"),),
    FUNDO: ((RECEITA, "data_entrada"), (REGISTRO, "Tipo_Fundo")),
    CONTROLA: ((FRE, "tipo"), (FRE, "participacao"), (FRE, "referencia")),
}
CAMPOS_DO_SETOR = (
    (RECEITA, "razao_social"),
    (RECEITA, "cnae_principal"),
    (RECEITA, "uf"),
)

SINAIS = (ENTROU, FUNDO, CONTROLA)

# os limites que valem para toda resposta; os de cada sinal só entram quando o sinal foi consultado
LIMITES_GERAIS = (
    (
        "Isto mostra movimentos passados, não intenção de compra: holding de família, reorganização e aumento "
        "de capital também entram, e entrar como sócio não é aquisição. A ordem é pelo número de entradas como "
        "sócia, depois pelo de sinais, e não por chance de compra nem por quão recente é a entrada. Nada aqui é "
        "recomendação de investimento."
    ),
    (
        "O setor é o das empresas com estabelecimento ativo do CNAE principal pedido (e na UF, se pedida) no "
        "retrato da Receita que valia em known_at. Só pessoa jurídica: MEI, empresário individual e sócio "
        "pessoa física não saem."
    ),
    (
        "Ainda fora: os atos de concentração do CADE e o fôlego do comprador (caixa, dívida, ofertas). Cada "
        "campo traz a fonte e o dia em que ficou público: nada publicado depois de known_at entra."
    ),
)
LIMITES_DO_SINAL = {
    ENTROU: (
        "Entradas como sócio: do quadro de sócios da Receita, que a base acompanha desde 05/2023 (antes disso, "
        "só quem ainda era sócio naquele mês). Contam também as entradas em empresa do setor que depois foi "
        "baixada (uma incorporação, por exemplo). Não contam quem entrou até a abertura da empresa nem a entrada "
        "entre empresas do mesmo grupo (uma era sócia da outra, ou as duas tinham uma sócia PJ em comum). "
        "Quando a empresa onde se entrou está baixada (sem nenhum estabelecimento ativo), o exemplo traz "
        'company_status "baixada", closed_on (o dia da baixa do último estabelecimento a baixar, só de versão já '
        "pública em known_at) e closure_reason_code (o código da tabela de motivos da situação cadastral da "
        "Receita, como ela publica, sem tradução nossa)."
    ),
    FUNDO: (
        "Fundo sócio: FIP registrado na CVM e não cancelado no dia, sócio de uma empresa do setor no quadro de "
        "sócios da Receita."
    ),
    CONTROLA: (
        "Controlada no setor: o FRE mais recente da companhia aberta já entregue no dia, com o tipo e a "
        "participação que ela informou, sem correção nossa."
    ),
}
# o nome de dentro da lista dos sinais que o portão não libera (ou cuja tabela a base não tem)
NAO_DISPONIVEIS = "sinais_nao_disponiveis"
LIMITE_DO_SINAL_NAO_DISPONIVEL = nao_disponivel.aviso(
    NAO_DISPONIVEIS, "sinais", "a lista de compradores"
)
GERAIS_ANTES_DOS_SINAIS = (
    2  # o aviso de que não é intenção de compra e o recorte do setor
)


def limites(
    sinais_servidos: Iterable[str], nao_disponiveis: Sequence[str] = ()
) -> list[str]:
    """Os limites de uma resposta: os gerais, a frase de cada sinal consultado e, quando algum sinal ficou
    de fora, o aviso de que a lista não diz nada sobre ele."""
    return nao_disponivel.limites(
        LIMITES_GERAIS,
        LIMITES_DO_SINAL,
        sinais_servidos,
        nao_disponiveis,
        LIMITE_DO_SINAL_NAO_DISPONIVEL,
        antes=GERAIS_ANTES_DOS_SINAIS,
    )


# os limites com todos os sinais consultados
LIMITES = tuple(limites(SINAIS))


# A resposta de um pedido só depende do pedido, do dia, do teto de linhas, de quais sinais o portão libera
# e dos arquivos da base; nada da conta, da chave ou da organização entra além do que o portão liberou, e
# isso já está na chave. Mudou um arquivo (data, tamanho), a chave muda e a conta é refeita (linha 848).
TAMANHO_DO_CACHE = 64
_CACHE: OrderedDict[tuple, "CompradoresServidos"] = OrderedDict()
_TRAVA = threading.Lock()
_EM_CURSO: dict[
    tuple, threading.Lock
] = {}  # pedidos sendo calculados (um só por chave de cada vez)
TABELAS_LIDAS = (
    ESTABELECIMENTOS,
    EMPRESAS,
    SITUACAO,
    ENTRADAS,
    FUNDOS,
    FIPS_REGISTRADOS,
    CONTROLADAS,
    CONTROLADAS_PJ,
)


def zerar_o_cache() -> None:
    with _TRAVA:
        _CACHE.clear()


def _impressao_da_base(porta: Porta) -> tuple:
    """Os arquivos das tabelas lidas (caminho, data e tamanho): muda quando a base muda."""
    impressao = []
    for tabela in TABELAS_LIDAS:
        padrao = porta.arquivos.get(tabela)
        for arquivo in arquivos_da_tabela(porta.pasta, padrao) if padrao else []:
            estado = arquivo.stat()
            impressao.append((arquivo.as_posix(), estado.st_mtime_ns, estado.st_size))
    return tuple(impressao)


class PedidoInvalido(ValueError):
    """Pedido que não dá para atender (`codigo` vai no 400)."""

    def __init__(self, codigo: str) -> None:
        super().__init__(codigo)
        self.codigo = codigo


@dataclass(frozen=True)
class PedidoDeCompradores:
    """O pedido já conferido: CNAE só com dígitos (5 ou 7), UF em maiúsculas ou None, anos e limite."""

    cnae: str
    uf: str | None = None
    anos: int = ANOS_PADRAO
    limite: int = LIMITE_PADRAO


@dataclass(frozen=True)
class CompradoresServidos:
    """O que sai de um pedido: o corpo, as fontes usadas e as linhas servidas (um comprador é uma linha)."""

    corpo: dict
    fontes: set[str] = field(default_factory=set)
    linhas: int = 0


def cnae_do_parametro(cnae: str) -> str:
    """O CNAE como o cliente escreve (com ponto, traço, barra ou espaço) vira só os dígitos da classe (5) ou da
    subclasse (7); `PedidoInvalido("invalid_cnae")` fora da forma."""
    digitos = "".join(c for c in cnae if c not in ".-/ ")
    if (
        not (digitos.isascii() and digitos.isdigit())
        or len(digitos) not in TAMANHOS_DO_CNAE
    ):
        raise PedidoInvalido("invalid_cnae")
    return digitos


def mes_do_retrato(porta: Porta, como_era_em: date) -> str | None:
    """O retrato da Receita mais novo já público no dia, o mesmo mês nas duas tabelas sem pessoa do CNPJ
    (None se alguma ainda não tinha retrato público). Lido uma vez por base e dia (3 a 6 s por pedido, linha 956)."""
    return lembrar(
        porta,
        ("mes_do_retrato_compradores", como_era_em),
        lambda: _ler_o_mes_do_retrato(porta, como_era_em),
    )


def primeiro_dia_do_retrato(porta: Porta) -> date | None:
    """O primeiro dia em que as duas tabelas sem pessoa do CNPJ já tinham retrato público (None se alguma está
    vazia): antes dele `mes_do_retrato` não acha mês. Lido uma vez por base."""
    return lembrar(
        porta,
        ("primeiro_dia_do_retrato_compradores",),
        lambda: _ler_o_primeiro_dia_do_retrato(porta),
    )


def _ler_o_primeiro_dia_do_retrato(porta: Porta) -> date | None:
    primeiros = []
    for tabela in (ESTABELECIMENTOS, EMPRESAS):
        achado = porta.con.execute(
            f"SELECT min({PUBLICADO_EM}) FROM {_view(tabela)}"
        ).fetchone()
        primeiros.append(None if achado is None else _dia(achado[0]))
    return None if None in primeiros else max(d for d in primeiros if d is not None)


def _ler_o_mes_do_retrato(porta: Porta, como_era_em: date) -> str | None:
    meses = []
    for tabela in (ESTABELECIMENTOS, EMPRESAS):
        condicao = condicao_como_era(porta.colunas(tabela), tabela)
        achado = porta.con.execute(
            f"SELECT max({MES}) FROM {_view(tabela)} WHERE {condicao}",
            {"dia": dia_de(como_era_em)},
        ).fetchone()
        meses.append(None if achado is None else achado[0])
    return None if None in meses else min(meses)


def pedido_dos_parametros(
    cnae: str, state: str | None, years: int | None, limit: int | None
) -> PedidoDeCompradores:
    """Os parâmetros da rota (como o cliente escreve) viram o pedido; `PedidoInvalido` fora da forma."""
    digitos = cnae_do_parametro(cnae)
    uf = (state or "").strip().upper() or None
    if uf is not None and uf not in UFS:
        raise PedidoInvalido("invalid_state")
    anos = ANOS_PADRAO if years is None else years
    if not 1 <= anos <= ANOS_MAXIMO:
        raise PedidoInvalido("invalid_years")
    limite = LIMITE_PADRAO if limit is None else limit
    if not 1 <= limite <= LIMITE_MAXIMO:
        raise PedidoInvalido("invalid_limit")
    return PedidoDeCompradores(digitos, uf, anos, limite)


def _aspas(nome: str) -> str:
    return '"' + nome.replace('"', '""') + '"'


def _view(tabela: str) -> str:
    return _aspas(nome_da_view(tabela))


def _dia(valor: object) -> date | None:
    if valor is None or pd.isna(valor):  # type: ignore[arg-type]
        return None
    return pd.Timestamp(valor).date()  # type: ignore[arg-type]


def _numero(valor: object) -> float | None:
    if valor is None or pd.isna(valor):  # type: ignore[arg-type]
        return None
    return float(valor)  # type: ignore[arg-type]


def _texto(valor: object) -> str | None:
    if valor is None or pd.isna(valor):  # type: ignore[arg-type]
        return None
    return str(valor)


class LeitorDeCompradores:
    """Lê os compradores de um setor de uma porta para um pedido."""

    def __init__(self, porta: Porta, permitido: Permitido, linhas_maximas: int) -> None:
        self.porta = porta
        self.permitido = permitido
        self.linhas_maximas = linhas_maximas
        self.tabelas = set(views(porta.con))
        # a tabela que cada sinal lê: a primeira das opções de `LEITURAS` que a porta tem; sem nenhuma, a primeira
        # (fora da porta, o sinal fica de fora: o FIP nunca cai na tabela inteira)
        self.lida = {
            tabela: next((t for t in opcoes if t in self.tabelas), opcoes[0])
            for tabela, opcoes in LEITURAS.items()
        }
        # o primeiro dia com retrato, quando o último pedido caiu antes dele (só depois de o portão liberar o
        # setor e algum sinal): a rota o diz no erro, a tela segue com o None (linha 990)
        self.primeira_data: date | None = None

    def _libera(self, campos: tuple[tuple[str, str], ...]) -> bool:
        return all(self.permitido(fonte, nome, False) for fonte, nome in campos)

    def _le_a_baixa(self) -> bool:
        """Os campos da baixa saem quando o portão libera os três e a porta tem a situação cadastral."""
        return SITUACAO in self.tabelas and self._libera(CAMPOS_DA_BAIXA)

    def _sinais_liberados(self) -> tuple[str, ...]:
        """Os sinais com todos os campos liberados pelo portão e as tabelas na porta."""
        precisa = {
            ENTROU: (ENTRADAS,),
            FUNDO: (ENTRADAS, self.lida[FUNDOS]),
            CONTROLA: (self.lida[CONTROLADAS],),
        }
        return tuple(
            s
            for s in SINAIS
            if self._libera(CAMPOS_DO_SINAL[s]) and set(precisa[s]) <= self.tabelas
        )

    def compradores(
        self, pedido: PedidoDeCompradores, como_era_em: date
    ) -> CompradoresServidos | None:
        """Os compradores do setor como eram no dia; None se o portão não libera o setor nem algum sinal, ou
        se a porta não tem o retrato da Receita do dia. Setor sem comprador sai com a lista vazia. Quando o dia é
        anterior ao primeiro retrato, `primeira_data` diz o primeiro dia que funciona."""
        self.primeira_data = None
        if (
            not self._libera(CAMPOS_DO_SETOR)
            or not {ESTABELECIMENTOS, EMPRESAS} <= self.tabelas
        ):
            return None
        sinais = self._sinais_liberados()
        if not sinais:
            return None
        impressao = _impressao_da_base(self.porta)
        if not impressao:  # sem arquivos para vigiar o cache ficaria cego: não guarda
            return self._montar(pedido, como_era_em, sinais)
        chave = (pedido, como_era_em, self.linhas_maximas, sinais, impressao)
        with _TRAVA:
            vez = _EM_CURSO.setdefault(chave, threading.Lock())
        # o mesmo pedido duas vezes ao mesmo tempo (o cliente desistiu aos 30 s e repetiu, ou duas telas) espera
        # o primeiro terminar e lê do cache, em vez de refazer a conta (linha 956)
        with vez:
            try:
                return self._do_cache_ou_montar(chave, pedido, como_era_em, sinais)
            finally:
                with _TRAVA:  # só depois de guardar: quem chega agora já acha o resultado no cache
                    if (
                        _EM_CURSO.get(chave) is vez
                    ):  # a trava de outro pedido igual não é desta chamada
                        _EM_CURSO.pop(chave, None)

    def _do_cache_ou_montar(
        self,
        chave: tuple,
        pedido: PedidoDeCompradores,
        como_era_em: date,
        sinais: tuple[str, ...],
    ) -> CompradoresServidos | None:
        with _TRAVA:
            guardado = _CACHE.get(chave)
            if guardado is not None:
                _CACHE.move_to_end(chave)
        if guardado is not None:
            return copy.deepcopy(guardado)
        servido = self._montar(pedido, como_era_em, sinais)
        if servido is not None:
            with _TRAVA:
                _CACHE[chave] = copy.deepcopy(servido)
                while len(_CACHE) > TAMANHO_DO_CACHE:
                    _CACHE.popitem(last=False)
        return servido

    def _montar(
        self, pedido: PedidoDeCompradores, como_era_em: date, sinais: tuple[str, ...]
    ) -> CompradoresServidos | None:
        mes = mes_do_retrato(self.porta, como_era_em)
        if mes is None:
            primeira = primeiro_dia_do_retrato(self.porta)
            if primeira is not None and como_era_em < primeira:
                self.primeira_data = primeira
            return None
        nao_disponiveis = [s for s in SINAIS if s not in sinais]
        desde = (
            pd.Timestamp(como_era_em)
            - pd.Timedelta(days=round(pedido.anos * DIAS_POR_ANO))
        ).date()
        consulta = _Consulta(self.porta, mes, como_era_em, desde, self.lida)
        # as empresas onde se entra: as ativas do setor e, para o sinal de entrada, as baixadas onde alguém entrou
        # na janela (consolidador que incorpora o que compra faz a empresa sumir da lista de ativas, linha 1042)
        alvos = consulta.alvos(pedido.cnae, pedido.uf, ENTROU in sinais)
        setor = alvos[~alvos["baixada"]]
        lista = _Lista(alvos)
        fontes = {RECEITA}
        if ENTROU in sinais or FUNDO in sinais:
            entradas = consulta.entradas(alvos) if ENTROU in sinais else None
            # só o quadro de sócios de quem pesa na conta: as empresas do setor e quem entrou nelas
            relevantes = set(alvos["raiz"].astype(str))
            if entradas is not None:
                relevantes |= set(entradas["comprador"].astype(str))
            socias = consulta.socias_no_dia(relevantes)
            if entradas is not None:
                lista.anotar_entradas(entradas, socias)
            if FUNDO in sinais:
                lista.anotar_fundos(consulta.fundos_socios(setor, socias))
                fontes.add(REGISTRO)
        if CONTROLA in sinais:
            lista.anotar_controladas(consulta.controladas(setor))
            fontes.add(FRE)
        nomes = consulta.nomes(lista.raizes())
        compradores = lista.montar(
            nomes,
            min(pedido.limite, max(self.linhas_maximas, 1)),
            consulta.baixas if self._le_a_baixa() else None,
        )
        corpo: dict[str, object] = {
            "como_era_em": como_era_em.isoformat(),
            "setor": {
                "cnae_principal": pedido.cnae,
                "uf": pedido.uf,
                "anos": pedido.anos,
                "desde": desde.isoformat(),
                "empresas_ativas": len(setor),
            },
            "compradores": compradores,
            "total_de_compradores": lista.total(nomes),
            "cortada": lista.total(nomes) > len(compradores),
            NAO_DISPONIVEIS: [NOME_DE_FORA[s] for s in nao_disponiveis],
            "limites": limites(sinais, nao_disponiveis),
        }
        return CompradoresServidos(corpo, fontes, len(compradores))


class _Consulta:
    """As consultas à porta de um pedido: o retrato do dia, o dia, o começo da janela e a tabela que cada
    sinal lê (a inteira ou a cópia reduzida)."""

    def __init__(
        self,
        porta: Porta,
        mes: str,
        dia: date,
        desde: date,
        lida: Mapping[str, str] | None = None,
    ) -> None:
        self.porta, self.mes, self.dia, self.desde = porta, mes, dia, desde
        self.lida = dict(lida or {})

    def _da_vez(self, tabela: str) -> str:
        return _view(self.lida.get(tabela, tabela))

    def _df(
        self, sql: str, parametros: dict[str, object], **tabelas: pd.DataFrame
    ) -> pd.DataFrame:
        cursor = self.porta.con.cursor()
        try:
            for nome, tabela in tabelas.items():
                cursor.register(nome, tabela)
            return cursor.execute(sql, parametros).df()
        finally:
            cursor.close()

    def setor(self, cnae: str, uf: str | None) -> pd.DataFrame:
        """As raízes com estabelecimento ativo do CNAE (na UF) no retrato: o `empresas_ativas` da lista, com a
        abertura mais antiga e a UF (`perfil_do_setor` confere o seu número contra esta conta)."""
        return self.alvos(cnae, uf, com_baixadas=False)[["raiz", "abertura", "uf"]]

    def alvos(self, cnae: str, uf: str | None, com_baixadas: bool) -> pd.DataFrame:
        """As raízes do setor no retrato, com a abertura mais antiga, a UF e se estão `baixada`.

        As ativas são as que têm estabelecimento ativo do CNAE (na UF), com a UF e a abertura só dos
        estabelecimentos ativos. As baixadas só vêm com `com_baixadas` e são as que têm estabelecimento baixado do
        CNAE (na UF) e **nenhum estabelecimento ativo no retrato**, em nenhum CNAE nem UF (empresa que fechou a
        filial daquele CNAE ou daquela UF segue funcionando e não é baixada do setor). Só as que tiveram alguém
        entrando na janela: o retrato tem centenas de milhares delas, e só estas pesam na lista."""
        ativas = "SELECT raiz, abertura_ativa AS abertura, uf_ativa AS uf, false AS baixada FROM recorte WHERE ativa"
        baixadas = (
            " UNION ALL "
            "SELECT raiz, abertura_todas, uf_todas, true FROM recorte WHERE so_baixadas AND EXISTS "
            f"(SELECT 1 FROM {_view(ENTRADAS)} e WHERE e.cnpj_basico = recorte.raiz "
            f"AND e.movimento = 'entrou' AND e.{PUBLICADO_EM} <= CAST($dia AS DATE) "
            "AND e.data_entrada >= CAST($desde AS DATE) AND e.data_entrada <= CAST($dia AS DATE)) "
            f"AND NOT EXISTS (SELECT 1 FROM {_view(ESTABELECIMENTOS)} a WHERE a.cnpj_basico = recorte.raiz "
            f"AND a.{MES} = $mes AND a.situacao_cadastral = $ativa)"
            if com_baixadas
            else ""
        )
        return self._df(
            "WITH recorte AS (SELECT cnpj_basico AS raiz, "
            "min(data_inicio_atividade) FILTER (WHERE situacao_cadastral = $ativa) AS abertura_ativa, "
            "min(uf) FILTER (WHERE situacao_cadastral = $ativa) AS uf_ativa, "
            "min(data_inicio_atividade) AS abertura_todas, min(uf) AS uf_todas, "
            "coalesce(bool_or(situacao_cadastral = $ativa), false) AS ativa, "
            "coalesce(bool_and(situacao_cadastral = $baixada), false) AS so_baixadas "
            f"FROM {_view(ESTABELECIMENTOS)} WHERE {MES} = $mes "
            "AND starts_with(cnae_principal, $cnae) AND ($uf IS NULL OR uf = $uf) GROUP BY cnpj_basico) "
            f"{ativas}{baixadas}",
            {
                "mes": self.mes,
                "ativa": ATIVA,
                "baixada": BAIXADA,
                "cnae": cnae,
                "uf": uf,
                # o DuckDB recusa parâmetro que a consulta não usa
                **(
                    {"dia": dia_de(self.dia), "desde": dia_de(self.desde)}
                    if com_baixadas
                    else {}
                ),
            },
        )

    def baixas(self, raizes: set[str]) -> dict[str, Baixa]:
        """Quando e por que baixou cada raiz (as que a lista mostra): a versão mais nova **já pública no dia** de cada
        estabelecimento da situação cadastral, só a que está baixada e consta no arquivo; da raiz vale a última filial
        a baixar (a empresa só baixa quando a última fecha). O motivo vai como código, sem traduzir."""
        if not raizes:
            return {}
        tabela = self._df(
            f"SELECT raiz, data_situacao_cadastral AS quando, lpad(motivo_situacao, 2, '0') AS motivo, "
            f"{PUBLICADO_EM} AS publico_em FROM ("
            f"SELECT cnpj_basico AS raiz, cnpj, consta, data_situacao_cadastral, motivo_situacao, "
            f"lpad(situacao_cadastral, 2, '0') AS situacao, {PUBLICADO_EM} "
            f"FROM {_view(SITUACAO)} WHERE cnpj_basico IN (SELECT raiz FROM baixadas) "
            f"AND {PUBLICADO_EM} <= CAST($dia AS DATE) "
            f"QUALIFY row_number() OVER (PARTITION BY cnpj ORDER BY {MES} DESC, {PUBLICADO_EM} DESC) = 1) "
            f"WHERE consta AND situacao = $baixada AND data_situacao_cadastral IS NOT NULL "
            f"QUALIFY row_number() OVER (PARTITION BY raiz ORDER BY data_situacao_cadastral DESC, cnpj) = 1",
            {"dia": dia_de(self.dia), "baixada": BAIXADA},
            baixadas=pd.DataFrame({"raiz": pd.Series(sorted(raizes), dtype="string")}),
        )
        return {
            str(linha["raiz"]): (
                pd.Timestamp(linha["quando"]).date(),
                str(linha["motivo"]),
                pd.Timestamp(linha["publico_em"]).date(),
            )
            for linha in tabela.to_dict("records")
            if _texto(linha["motivo"]) not in (None, "")
        }

    def socias_no_dia(self, raizes: set[str]) -> pd.DataFrame:
        """O quadro de sócios PJ do dia das `raizes`, refeito das entradas e saídas já públicas: o último
        movimento do par. Filtrar pela raiz antes da janela não muda o resultado (a raiz é chave da partição)
        e poupa ler e montar o quadro de todas as empresas do país a cada pedido (linha 848)."""
        return self._df(
            f"SELECT cnpj_basico AS raiz, raiz_socio_pj AS socia, data_entrada, {PUBLICADO_EM} "
            f"FROM {_view(ENTRADAS)} WHERE movimento IN ('entrou', 'saiu') "
            "AND cnpj_basico IN (SELECT raiz FROM relevantes) "
            f"AND {PUBLICADO_EM} <= CAST($dia AS DATE) "
            f"QUALIFY row_number() OVER (PARTITION BY cnpj_basico, raiz_socio_pj "
            f"ORDER BY {MES} DESC, movimento = 'saiu' DESC) = 1 AND movimento = 'entrou'",
            {"dia": dia_de(self.dia)},
            relevantes=pd.DataFrame(
                {"raiz": pd.Series(sorted(raizes), dtype="string")}
            ),
        )

    def entradas(self, alvos: pd.DataFrame) -> pd.DataFrame:
        """Quem entrou como sócio PJ de empresa do setor (ativa ou baixada) na janela, depois da abertura; a mais nova por par."""
        return self._df(
            f"SELECT e.cnpj_basico AS alvo, e.raiz_socio_pj AS comprador, e.data_entrada, e.{PUBLICADO_EM} "
            f"FROM {_view(ENTRADAS)} e JOIN setor s ON s.raiz = e.cnpj_basico "
            f"WHERE e.movimento = 'entrou' AND e.{PUBLICADO_EM} <= CAST($dia AS DATE) "
            "AND e.data_entrada >= CAST($desde AS DATE) AND e.data_entrada <= CAST($dia AS DATE) "
            "AND e.raiz_socio_pj <> e.cnpj_basico AND (s.abertura IS NULL OR e.data_entrada > s.abertura) "
            "QUALIFY row_number() OVER (PARTITION BY e.cnpj_basico, e.raiz_socio_pj "
            f"ORDER BY e.data_entrada DESC, e.{MES} DESC) = 1",
            {"dia": dia_de(self.dia), "desde": dia_de(self.desde)},
            setor=alvos[["raiz", "abertura"]],
        )

    def fundos_socios(self, setor: pd.DataFrame, socias: pd.DataFrame) -> pd.DataFrame:
        """Os FIPs registrados e não cancelados no dia que eram sócios de uma empresa do setor."""
        return self._df(
            "WITH fip AS (SELECT DISTINCT substr(regexp_replace(CNPJ_Fundo, '[^0-9A-Za-z]', '', 'g'), 1, 8) AS raiz "
            f"FROM {self._da_vez(FUNDOS)} WHERE Tipo_Fundo = $fip "
            "AND TRY_CAST(Data_Registro AS DATE) <= CAST($dia AS DATE) "
            "AND (TRY_CAST(Data_Cancelamento AS DATE) IS NULL "
            "OR TRY_CAST(Data_Cancelamento AS DATE) > CAST($dia AS DATE))) "
            f"SELECT q.raiz AS alvo, q.socia AS comprador, q.data_entrada, q.{PUBLICADO_EM} "
            "FROM socias q JOIN setor s ON s.raiz = q.raiz JOIN fip f ON f.raiz = q.socia",
            {"fip": FIP, "dia": dia_de(self.dia)},
            setor=setor[["raiz"]],
            socias=socias,
        )

    def controladas(self, setor: pd.DataFrame) -> pd.DataFrame:
        """Controladas e coligadas no setor, pela versão mais nova do FRE mais recente de cada companhia, já recebida no dia."""
        return self._df(
            "WITH c AS (SELECT *, regexp_replace(cnpj_companhia, '[^0-9A-Za-z]', '', 'g') AS cc, "
            "substr(regexp_replace(cnpj, '[^0-9A-Za-z]', '', 'g'), 1, 8) AS alvo "
            f"FROM {self._da_vez(CONTROLADAS)} WHERE {PUBLICADO_EM} <= CAST($dia AS DATE)), "
            # um documento só por companhia: a referência mais recente e, nela, a versão mais nova;
            # a controlada que a versão nova tirou não sai mais
            "ultimo AS (SELECT DISTINCT cc, referencia, versao FROM c "
            "QUALIFY dense_rank() OVER (PARTITION BY cc ORDER BY referencia DESC, versao DESC) = 1) "
            "SELECT substr(c.cc, 1, 8) AS comprador, c.alvo, c.tipo, c.participacao, c.referencia, "
            f"c.{PUBLICADO_EM} FROM c JOIN ultimo u USING (cc, referencia, versao) "
            "JOIN setor s ON s.raiz = c.alvo WHERE substr(c.cc, 1, 8) <> c.alvo "
            "QUALIFY row_number() OVER (PARTITION BY c.cc, c.alvo ORDER BY c.tipo) = 1",
            {"dia": dia_de(self.dia)},
            setor=setor[["raiz"]],
        )

    def nomes(self, raizes: set[str]) -> dict[str, tuple[str, date]]:
        """A razão social e o dia em que ficou pública, no retrato do dia; quem não está ali não é PJ aqui."""
        if not raizes:
            return {}
        # a lista vai no `IN` (e não numa junção): com a lista no filtro o DuckDB descarta os grupos de linhas do
        # Parquet pelo mínimo e máximo da raiz e lê só o que sobra; juntando, lia a tabela inteira (linha 956:
        # 18 s contra 7,5 s para 400 raízes, na máquina do servidor)
        parametros: dict[str, object] = {"mes": self.mes}
        marcas = []
        for i, raiz in enumerate(sorted(raizes)):
            parametros[f"r{i}"] = raiz
            marcas.append(f"$r{i}")
        tabela = self._df(
            f"SELECT p.cnpj_basico AS raiz, any_value(p.razao_social) AS razao_social, "
            f"max(p.{PUBLICADO_EM}) AS publico_em FROM {_view(EMPRESAS)} p "
            f"WHERE p.{MES} = $mes AND p.cnpj_basico IN ({', '.join(marcas)}) GROUP BY 1",
            parametros,
        )
        return {
            str(linha["raiz"]): (
                str(linha["razao_social"] or ""),
                pd.Timestamp(linha["publico_em"]).date(),
            )
            for linha in tabela.to_dict("records")
        }


def _mais_novas(provas: list[dict[str, object]]) -> list[dict[str, object]]:
    """Os exemplos de um sinal: as `EXEMPLOS_POR_SINAL` provas mais novas (a empresa desempata)."""
    return sorted(
        provas, key=lambda p: (str(p["_ordem"]), str(p["_alvo"])), reverse=True
    )[:EXEMPLOS_POR_SINAL]


def _mesmo_grupo(alvo: str, comprador: str, socias: dict[str, set[str]]) -> bool:
    """Uma era sócia da outra (fora a entrada que se olha) ou as duas tinham uma sócia PJ em comum."""
    do_alvo = socias.get(alvo, set()) - {comprador}
    do_comprador = socias.get(comprador, set())
    return alvo in do_comprador or bool(do_alvo & do_comprador)


class _Lista:
    """Os compradores juntando os sinais; cada prova guarda a empresa do setor e os campos em envelope."""

    def __init__(self, setor: pd.DataFrame) -> None:
        self.ufs = {
            str(r): _texto(u) for r, u in zip(setor["raiz"], setor["uf"], strict=True)
        }
        self.baixadas = {
            str(r) for r, b in zip(setor["raiz"], setor["baixada"], strict=True) if b
        }
        self.provas: dict[str, dict[str, list[dict[str, object]]]] = defaultdict(
            lambda: defaultdict(list)
        )

    def raizes(self) -> set[str]:
        return set(self.provas) | {
            str(p["_alvo"])
            for sinais in self.provas.values()
            for lista in sinais.values()
            for p in lista
        }

    def _anotar(
        self, comprador: str, sinal: str, alvo: str, ordem: object, **campos: object
    ) -> None:
        self.provas[comprador][sinal].append(
            {"_alvo": alvo, "_ordem": str(ordem or ""), **campos}
        )

    def anotar_entradas(self, entradas: pd.DataFrame, socias: pd.DataFrame) -> None:
        por_raiz: dict[str, set[str]] = defaultdict(set)
        for raiz, socia in zip(socias["raiz"], socias["socia"], strict=True):
            por_raiz[str(raiz)].add(str(socia))
        for linha in entradas.to_dict("records"):
            alvo, comprador = str(linha["alvo"]), str(linha["comprador"])
            if _mesmo_grupo(alvo, comprador, por_raiz):
                continue
            publico_em = _dia(linha[PUBLICADO_EM])
            entrada = _dia(linha["data_entrada"])
            self._anotar(
                comprador, ENTROU, alvo, entrada,
                data_entrada=campo(entrada and entrada.isoformat(), fonte=RECEITA, publico_em=publico_em, visto_em=None),
                ainda_socio=comprador in por_raiz.get(alvo, set()),
            )  # fmt: skip

    def anotar_fundos(self, fundos: pd.DataFrame) -> None:
        for linha in fundos.to_dict("records"):
            entrada = _dia(linha["data_entrada"])
            self._anotar(
                str(linha["comprador"]), FUNDO, str(linha["alvo"]), entrada,
                data_entrada=campo(
                    entrada and entrada.isoformat(), fonte=RECEITA, publico_em=_dia(linha[PUBLICADO_EM]), visto_em=None,
                ),
            )  # fmt: skip

    def anotar_controladas(self, controladas: pd.DataFrame) -> None:
        for linha in controladas.to_dict("records"):
            publico_em = _dia(linha[PUBLICADO_EM])
            referencia = _dia(linha["referencia"])
            self._anotar(
                str(linha["comprador"]), CONTROLA, str(linha["alvo"]), referencia,
                tipo=campo(_texto(linha["tipo"]), fonte=FRE, publico_em=publico_em, visto_em=None),
                participacao_no_capital=campo(_numero(linha["participacao"]), fonte=FRE, publico_em=publico_em, visto_em=None),
                referencia=campo(referencia and referencia.isoformat(), fonte=FRE, publico_em=publico_em, visto_em=None),
            )  # fmt: skip

    def _validos(self, nomes: dict[str, tuple[str, date]]) -> list[str]:
        """Os compradores da lista sem pessoa (o comprador fora dela não sai)."""
        return [c for c in self.provas if c in nomes]

    def total(self, nomes: dict[str, tuple[str, date]]) -> int:
        return len(self._validos(nomes))

    def montar(
        self,
        nomes: dict[str, tuple[str, date]],
        limite: int,
        baixas_de: Callable[[set[str]], dict[str, Baixa]] | None = None,
    ) -> list[dict[str, object]]:
        """Os `limite` primeiros: mais entradas de terceiros, depois mais sinais, depois mais provas e, no fim, a
        raiz. A data da prova não desempata (linha 1044): desempatar pela mais nova fazia o negócio de ontem subir o
        comprador e jogava para fora dos 50 quem comprou há mais tempo. `baixas_de` diz quando e por que baixou cada
        empresa baixada **que aparece num exemplo**: só estas são lidas, e só elas ganham os campos da baixa."""

        def chave(comprador: str) -> tuple[int, int, int, str]:
            sinais = self.provas[comprador]
            provas = sum(len(lista) for lista in sinais.values())
            return (
                -len(sinais.get(ENTROU, [])),
                -len(sinais),
                -provas,
                comprador,
            )

        escolhidos = sorted(self._validos(nomes), key=chave)[:limite]
        mostradas = {
            str(p["_alvo"])
            for c in escolhidos
            for lista in self.provas[c].values()
            for p in _mais_novas(lista)
        } & self.baixadas
        baixas = baixas_de(mostradas) if baixas_de and mostradas else {}
        return [self._comprador(c, nomes, baixas) for c in escolhidos]

    def _empresa(
        self,
        raiz: str,
        nomes: dict[str, tuple[str, date]],
        baixas: Mapping[str, Baixa] | None = None,
    ) -> dict[str, object]:
        empresa: dict[str, object] = {"raiz_do_cnpj": raiz}
        if raiz in nomes:
            nome, publico_em = nomes[raiz]
            empresa["razao_social"] = campo(
                nome, fonte=RECEITA, publico_em=publico_em, visto_em=None
            )
        # só onde a razão social já pode sair: empresa fora da lista sem pessoa não ganha campo
        if baixas and raiz in baixas and raiz in nomes:
            quando, motivo, publico_em = baixas[raiz]
            for nome_do_campo, valor in (
                ("situacao_da_empresa", "baixada"),
                ("baixada_em", quando.isoformat()),
                ("motivo_da_baixa", motivo),
            ):
                empresa[nome_do_campo] = campo(
                    valor, fonte=RECEITA, publico_em=publico_em, visto_em=None
                )
        return empresa

    def _comprador(
        self,
        comprador: str,
        nomes: dict[str, tuple[str, date]],
        baixas: Mapping[str, Baixa],
    ) -> dict[str, object]:
        sinais = self.provas[comprador]
        ordem = [s for s in (ENTROU, FUNDO, CONTROLA) if s in sinais]
        provas = {}
        for sinal in ordem:
            lista = sinais[sinal]
            provas[sinal] = {
                "quantas": len(lista),
                "exemplos": [
                    {
                        "empresa_do_setor": self._empresa(
                            str(p["_alvo"]), nomes, baixas
                        ),
                        "uf": self.ufs.get(str(p["_alvo"])),
                        **{k: v for k, v in p.items() if not k.startswith("_")},
                    }
                    for p in _mais_novas(lista)
                ],
            }
        return {
            **self._empresa(comprador, nomes),
            "sinais": [NOME_DE_FORA[s] for s in ordem],
            "provas": provas,
        }
