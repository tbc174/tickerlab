"""Quem já se mexeu num setor, na API externa (linha 810, PR 4): `GET /data/v1/buyers`, só pessoa jurídica.

`LeitorDeCompradores(porta, permitido, linhas_maximas).compradores(pedido, como_era_em)` parte das empresas com
estabelecimento ativo do CNAE pedido (e na UF, se pedida) no retrato da Receita que valia no dia, e lista, em
tipos simples e com as chaves em português (a rota traduz na saída), as empresas que deram algum destes sinais:

- `took_stake`: entrou como sócia PJ de uma empresa do setor na janela de `anos` (a tabela
  `entradas_de_socio_pj`, fonte `rfb-cnpj`). Não conta quem entrou até a abertura da empresa (fundador) nem a
  entrada dentro do mesmo grupo (uma era sócia da outra, ou as duas tinham uma sócia PJ em comum no dia);
- `fund_stake`: um FIP (registro de fundos da CVM, fonte `cvm-fidc-base`) que era sócio de uma empresa do
  setor no dia;
- `controls_in_sector`: a companhia aberta que, no FRE mais recente já entregue no dia, tinha uma controlada ou
  coligada no setor (`controladas`, fonte `cvm-hist-fre`).

No VPS os dois últimos sinais leem as cópias reduzidas com nome próprio (`controladas_pj` e `fips_registrados`,
linha 844, montadas e travadas por `base/recorte_dos_compradores.py`): só raízes da lista sem pessoa, sem razão
social, gestor nem administrador. A resposta é a mesma; quando a porta tem a tabela inteira, vale a inteira.

Cada comprador sai com a raiz do CNPJ, a razão social (em envelope) e, por sinal, quantas provas e até
`EXEMPLOS_POR_SINAL` exemplos, cada campo com a fonte e o dia em que ficou público. A ordem é pelo número de
sinais e depois pelo de entradas, não por chance de compra. O sinal que não foi consultado (o portão não o libera
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
from collections.abc import Iterable, Mapping, Sequence
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

CONJUNTO = "buyers"
RECEITA, FRE, REGISTRO = "rfb-cnpj", "cvm-hist-fre", "cvm-fidc-base"
ESTABELECIMENTOS, EMPRESAS = "cnpj_estabelecimentos_pj", "cnpj_empresas_pj"
ENTRADAS, CONTROLADAS, FUNDOS = (
    "entradas_de_socio_pj",
    "controladas",
    "registro_de_fundos",
)
# No VPS a lista lê as cópias reduzidas, com nome próprio (linha 844, `base/recorte_dos_compradores.py`): só
# PJ, sem razão social, gestor nem administrador. Em casa, a tabela inteira; ela vale quando as duas estão.
CONTROLADAS_PJ, FIPS_REGISTRADOS = "controladas_pj", "fips_registrados"
LEITURAS = {
    CONTROLADAS: (CONTROLADAS, CONTROLADAS_PJ),
    FUNDOS: (FUNDOS, FIPS_REGISTRADOS),
}
PUBLICADO_EM, MES = "publico_em", "mes_do_retrato"
ATIVA, FIP = "02", "FIP"
ANOS_PADRAO, ANOS_MAXIMO = 3, 10
LIMITE_PADRAO, LIMITE_MAXIMO = 20, 50
EXEMPLOS_POR_SINAL = 5
TAMANHOS_DO_CNAE = (5, 7)  # a classe ou a subclasse
UFS = frozenset({
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA",
    "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
})  # fmt: skip
DIAS_POR_ANO = 365.25

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
        "de capital também entram, e entrar como sócio não é aquisição. A ordem é pelo número de sinais, não "
        "por chance de compra. Nada aqui é recomendação de investimento."
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
        "só quem ainda era sócio naquele mês). Não contam quem entrou até a abertura da empresa nem a entrada "
        "entre empresas do mesmo grupo (uma era sócia da outra, ou as duas tinham uma sócia PJ em comum)."
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
TABELAS_LIDAS = (
    ESTABELECIMENTOS,
    EMPRESAS,
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


def pedido_dos_parametros(
    cnae: str, state: str | None, years: int | None, limit: int | None
) -> PedidoDeCompradores:
    """Os parâmetros da rota (como o cliente escreve) viram o pedido; `PedidoInvalido` fora da forma."""
    digitos = "".join(c for c in cnae if c not in ".-/ ")
    if (
        not (digitos.isascii() and digitos.isdigit())
        or len(digitos) not in TAMANHOS_DO_CNAE
    ):
        raise PedidoInvalido("invalid_cnae")
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
        # a tabela que cada sinal lê: a inteira, se a porta a tem, ou a cópia reduzida
        self.lida = {
            tabela: next((t for t in opcoes if t in self.tabelas), tabela)
            for tabela, opcoes in LEITURAS.items()
        }

    def _libera(self, campos: tuple[tuple[str, str], ...]) -> bool:
        return all(self.permitido(fonte, nome, False) for fonte, nome in campos)

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

    def _mes_do_retrato(self, como_era_em: date) -> str | None:
        """O retrato mais novo já público no dia, o mesmo mês nas duas tabelas da Receita."""
        meses = []
        for tabela in (ESTABELECIMENTOS, EMPRESAS):
            condicao = condicao_como_era(self.porta.colunas(tabela), tabela)
            achado = self.porta.con.execute(
                f"SELECT max({MES}) FROM {_view(tabela)} WHERE {condicao}",
                {"dia": dia_de(como_era_em)},
            ).fetchone()
            meses.append(None if achado is None else achado[0])
        return None if None in meses else min(meses)

    def compradores(
        self, pedido: PedidoDeCompradores, como_era_em: date
    ) -> CompradoresServidos | None:
        """Os compradores do setor como eram no dia; None se o portão não libera o setor nem algum sinal, ou
        se a porta não tem o retrato da Receita do dia. Setor sem comprador sai com a lista vazia."""
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
        mes = self._mes_do_retrato(como_era_em)
        if mes is None:
            return None
        nao_disponiveis = [s for s in SINAIS if s not in sinais]
        desde = (
            pd.Timestamp(como_era_em)
            - pd.Timedelta(days=round(pedido.anos * DIAS_POR_ANO))
        ).date()
        consulta = _Consulta(self.porta, mes, como_era_em, desde, self.lida)
        setor = consulta.setor(pedido.cnae, pedido.uf)
        lista = _Lista(setor)
        fontes = {RECEITA}
        if ENTROU in sinais or FUNDO in sinais:
            entradas = consulta.entradas(setor) if ENTROU in sinais else None
            # só o quadro de sócios de quem pesa na conta: as empresas do setor e quem entrou nelas
            relevantes = set(setor["raiz"].astype(str))
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
            nomes, min(pedido.limite, max(self.linhas_maximas, 1))
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
        """As raízes com estabelecimento ativo do CNAE (na UF) no retrato, com a abertura mais antiga e a UF."""
        return self._df(
            f"SELECT cnpj_basico AS raiz, min(data_inicio_atividade) AS abertura, min(uf) AS uf "
            f"FROM {_view(ESTABELECIMENTOS)} WHERE {MES} = $mes AND situacao_cadastral = $ativa "
            "AND starts_with(cnae_principal, $cnae) AND ($uf IS NULL OR uf = $uf) GROUP BY cnpj_basico",
            {"mes": self.mes, "ativa": ATIVA, "cnae": cnae, "uf": uf},
        )

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

    def entradas(self, setor: pd.DataFrame) -> pd.DataFrame:
        """Quem entrou como sócio PJ de empresa do setor na janela, depois da abertura; a mais nova por par."""
        return self._df(
            f"SELECT e.cnpj_basico AS alvo, e.raiz_socio_pj AS comprador, e.data_entrada, e.{PUBLICADO_EM} "
            f"FROM {_view(ENTRADAS)} e JOIN setor s ON s.raiz = e.cnpj_basico "
            f"WHERE e.movimento = 'entrou' AND e.{PUBLICADO_EM} <= CAST($dia AS DATE) "
            "AND e.data_entrada >= CAST($desde AS DATE) AND e.data_entrada <= CAST($dia AS DATE) "
            "AND e.raiz_socio_pj <> e.cnpj_basico AND (s.abertura IS NULL OR e.data_entrada > s.abertura) "
            "QUALIFY row_number() OVER (PARTITION BY e.cnpj_basico, e.raiz_socio_pj "
            f"ORDER BY e.data_entrada DESC, e.{MES} DESC) = 1",
            {"dia": dia_de(self.dia), "desde": dia_de(self.desde)},
            setor=setor[["raiz", "abertura"]],
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
        tabela = self._df(
            f"SELECT p.cnpj_basico AS raiz, any_value(p.razao_social) AS razao_social, "
            f"max(p.{PUBLICADO_EM}) AS publico_em FROM {_view(EMPRESAS)} p "
            f"JOIN pedidas r ON r.raiz = p.cnpj_basico WHERE p.{MES} = $mes GROUP BY 1",
            {"mes": self.mes},
            pedidas=pd.DataFrame({"raiz": sorted(raizes)}),
        )
        return {
            str(linha["raiz"]): (
                str(linha["razao_social"] or ""),
                pd.Timestamp(linha["publico_em"]).date(),
            )
            for linha in tabela.to_dict("records")
        }


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
        self, nomes: dict[str, tuple[str, date]], limite: int
    ) -> list[dict[str, object]]:
        """Os `limite` primeiros: mais sinais, depois mais entradas, depois a prova mais nova, depois a raiz."""

        def chave(comprador: str) -> tuple[int, int, str]:
            sinais = self.provas[comprador]
            return -len(sinais), -len(sinais.get(ENTROU, [])), comprador

        def mais_nova(comprador: str) -> str:
            return max(
                (
                    str(p["_ordem"])
                    for lista in self.provas[comprador].values()
                    for p in lista
                ),
                default="",
            )

        ordem = sorted(sorted(self._validos(nomes)), key=mais_nova, reverse=True)
        ordem.sort(
            key=lambda c: chave(c)[:2]
        )  # estável: o empate fica com a prova mais nova primeiro
        return [self._comprador(c, nomes) for c in ordem[:limite]]

    def _empresa(
        self, raiz: str, nomes: dict[str, tuple[str, date]]
    ) -> dict[str, object]:
        empresa: dict[str, object] = {"raiz_do_cnpj": raiz}
        if raiz in nomes:
            nome, publico_em = nomes[raiz]
            empresa["razao_social"] = campo(
                nome, fonte=RECEITA, publico_em=publico_em, visto_em=None
            )
        return empresa

    def _comprador(
        self, comprador: str, nomes: dict[str, tuple[str, date]]
    ) -> dict[str, object]:
        sinais = self.provas[comprador]
        ordem = [s for s in (ENTROU, FUNDO, CONTROLA) if s in sinais]
        provas = {}
        for sinal in ordem:
            lista = sorted(
                sinais[sinal],
                key=lambda p: (str(p["_ordem"]), str(p["_alvo"])),
                reverse=True,
            )
            provas[sinal] = {
                "quantas": len(lista),
                "exemplos": [
                    {
                        "empresa_do_setor": self._empresa(str(p["_alvo"]), nomes),
                        "uf": self.ufs.get(str(p["_alvo"])),
                        **{k: v for k, v in p.items() if not k.startswith("_")},
                    }
                    for p in lista[:EXEMPLOS_POR_SINAL]
                ],
            }
        return {
            **self._empresa(comprador, nomes),
            "sinais": [NOME_DE_FORA[s] for s in ordem],
            "provas": provas,
        }
