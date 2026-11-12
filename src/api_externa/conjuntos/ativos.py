"""Os ativos de uma empresa na API externa (linha 845): `/data/v1/companies/{cnpj}/assets`, como era.

`LeitorDeAtivos(porta, permitido, linhas_maximas).ativos(cnpj, como_era_em)` junta, em tipos simples (a rota
traduz as chaves na saída), o que as bases abertas das agências diziam no dia sobre os ativos físicos da
empresa, um bloco por base:

- `contratos_de_petroleo_e_gas`: cada contrato de exploração e produção da ANP em que a empresa é sócia
  (`anp_concessionarios`), com a rodada, a fase, o campo ou bloco, a bacia, terra ou mar, a participação e se
  ela opera. Os outros sócios do consórcio não saem: a leitura é só das linhas do CNPJ pedido;
- `barragens_de_mineracao`: cada barragem do SIGBM da ANM declarada com o CNPJ da empresa como empreendedor
  (`anm_sigbm_barragens`), com a mina, o lugar, a categoria de risco, o dano potencial, o nível de emergência,
  a situação, a altura e o volume. As coordenadas não saem;
- `royalties_de_mineracao`: a CFEM (royalty da mineração) recolhida pela empresa (`anm_cfem_arrecadacao`),
  por processo minerário, substância e município, somada nos 12 meses de competência que terminam no mês de
  `como_era_em`, e a última competência com recolhimento (as duas são conta nossa).

Cada bloco diz se achou a empresa (`achou`), a fonte, o dia do dado mais novo da base inteira no dia pedido
(`dado_mais_novo`) e o que a base cobre: "não achou" é a resposta honesta de que, na base como era, a empresa
não aparece, e não quer dizer que ela não tenha o ativo. A lista `nao_coberto` diz os ativos que esta rota não
traz. Cada campo sai no envelope, com a fonte e o dia em que ficou público; o que foi publicado depois do dia
não entra (`como_era_em` na porta).

Pessoa não sai (ADR 0108 D2.2): o CNPJ só é servido se a rede o conhece como empresa que não é pessoa
(`empresas.e_empresa`); os nomes de sócio e de empreendedor (`empresa`, `empreendedor`) nunca são lidos. A
empresa é a pessoa jurídica: entram as linhas de todos os estabelecimentos da mesma raiz. Um bloco que o
portão não libera não aparece; se nenhum é liberado, a rota responde `not_available`.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from base import cnpj as cnpj_
from base.porta import Porta
from base.porta.rede import views
from src.api_externa.conjuntos import Permitido
from src.api_externa.conjuntos.empresas import e_empresa
from src.api_externa.envelope import campo

CONJUNTO = "assets"
PETROLEO_E_GAS = "contratos_de_petroleo_e_gas"
BARRAGENS = "barragens_de_mineracao"
ROYALTIES = "royalties_de_mineracao"

PUBLICO_EM = "disponivel_em"
MESES_DA_SOMA = 12
MESES_NO_ANO = 12
CASAS_DOS_REAIS = 2
# os campos da CFEM que a soma e a última competência usam (no portão, como conta nossa)
VALOR_DA_CFEM = "valor_recolhido"
ANO_DA_CFEM = "ano"
MES_DA_CFEM = "mes"


@dataclass(frozen=True)
class OrigemDoBloco:
    """De onde sai um bloco: a tabela, a fonte, os campos servidos como a fonte publicou (na ordem), a coluna
    que liga à raiz do CNPJ (None: a tabela só tem o CNPJ inteiro), a coluna de quando o TickerLab viu o
    valor (None: a tabela não tem), a ordem da lista e a frase do que a base cobre."""

    tabela: str
    fonte: str
    campos: tuple[str, ...]
    coluna_da_raiz: str | None
    visto_em: str | None
    ordem: tuple[str, ...]
    cobertura: str


ORIGENS: dict[str, OrigemDoBloco] = {
    PETROLEO_E_GAS: OrigemDoBloco(
        tabela="anp_concessionarios",
        fonte="anp-concessionarios",
        campos=(
            "numero_do_contrato",
            "bid",
            "fase",
            "nome_fantasia",
            "bacia",
            "ambiente",
            "participacao_pct",
            "operador",
        ),
        coluna_da_raiz=None,
        visto_em="visto_em",
        ordem=("fase", "numero_do_contrato"),
        cobertura=(
            "Contratos de exploração e produção de petróleo e gás natural vigentes na ANP, um por sócio do "
            "consórcio (só a parte da empresa pedida)."
        ),
    ),
    BARRAGENS: OrigemDoBloco(
        tabela="anm_sigbm_barragens",
        fonte="anm-sigbm-barragens",
        campos=(
            "id",
            "nome",
            "nome_mina",
            "uf",
            "municipio",
            "categoria_risco",
            "dano_potencial",
            "nivel_emergencia",
            "situacao_operacional",
            "altura_atual_m",
            "volume_atual_m3",
        ),
        coluna_da_raiz="cnpj_raiz",
        visto_em=None,
        ordem=("uf", "municipio", "id"),
        cobertura=(
            "Barragens de mineração do SIGBM da ANM, pelo CNPJ do empreendedor declarado (que não é "
            "necessariamente quem opera a mina); a categoria de risco e o dano potencial são os declarados."
        ),
    ),
    ROYALTIES: OrigemDoBloco(
        tabela="anm_cfem_arrecadacao",
        fonte="anm-cfem-arrecadacao",
        campos=("processo", "substancia", "uf", "municipio"),
        coluna_da_raiz="cnpj_raiz",
        visto_em=None,
        ordem=("processo", "substancia", "uf", "municipio"),
        cobertura=(
            "CFEM (royalty da mineração) recolhida com o CNPJ da empresa como titular do processo minerário, "
            "pela competência do recolhimento."
        ),
    ),
}

NAO_COBERTO = (
    "Imóveis, terras e matrículas.",
    "Veículos, aeronaves e embarcações.",
    "Marcas, patentes e software registrados.",
    (
        "Estabelecimentos de saúde (CNES) e licenças e outorgas das agências (ANTT, MAPA, Anvisa, Anatel, "
        "Ancine e os títulos minerários da ANM)."
    ),
    "Participações em outras empresas: ver /companies/{cnpj}/links.",
)

# o bloco que o portão não libera nem aparece: a resposta diz que a rota ainda não o cobre, para a ausência não
# ser lida como "a empresa não tem" (Diretoria, 12/11)
FORA_DA_ROTA = {
    PETROLEO_E_GAS: "Contratos de exploração e produção de petróleo e gás (ANP): ainda não saem por esta rota.",
    BARRAGENS: "Mineração: barragens (SIGBM da ANM) ainda não saem por esta rota.",
    ROYALTIES: "Mineração: royalties (CFEM da ANM) ainda não saem por esta rota.",
}

# os limites que valem para a resposta inteira; os de cada bloco (`LIMITES_DO_BLOCO`) só entram quando o bloco
# sai, para a resposta não falar de fonte que ela não entrega (revisão cruzada, 12/11)
LIMITES = (
    "Cada campo traz a fonte e o dia em que ficou público: nada publicado depois de known_at entra.",
    (
        "Não achar a empresa quer dizer que a fonte não a lista na base como era no dia; não quer dizer que ela "
        "não tenha o ativo."
    ),
    "Nada aqui é avaliação dos ativos nem recomendação de investimento.",
    "Pessoa natural (MEI, empresário individual) não é servida.",
)

LIMITES_DO_BLOCO = {
    PETROLEO_E_GAS: (
        "A ANP reescreve o arquivo dos contratos sem dizer o que saiu: um contrato encerrado pode continuar na "
        "última versão que a base viu."
    ),
    BARRAGENS: (
        "A ANM reescreve o arquivo do SIGBM sem dizer o que saiu: uma barragem descaracterizada pode continuar "
        "na última versão que a base viu."
    ),
    ROYALTIES: (
        "A soma da CFEM em 12 meses e a última competência são conta do TickerLab sobre as linhas da ANM, pela "
        "competência do recolhimento (não pelo dia do pagamento)."
    ),
}


@dataclass(frozen=True)
class AtivosServidos:
    """O que sai de um pedido de ativos: o corpo, as fontes usadas e as linhas servidas."""

    corpo: dict
    fontes: set[str] = field(default_factory=set)
    linhas: int = 0


@dataclass(frozen=True)
class _Bloco:
    corpo: dict
    linhas: int


def _texto(valor: object) -> str | None:
    if valor is None or (not isinstance(valor, str) and pd.isna(valor)):  # type: ignore[arg-type]
        return None
    texto = str(valor).strip()
    return texto or None


def _numero(valor: object) -> float | None:
    if valor is None or pd.isna(valor):  # type: ignore[arg-type]
        return None
    return float(valor)  # type: ignore[arg-type]


def _logico(valor: object) -> bool | None:
    if valor is None or pd.isna(valor):  # type: ignore[arg-type]
        return None
    return bool(valor)


def _dia(valor: object) -> date | None:
    if valor is None or pd.isna(valor):  # type: ignore[arg-type]
        return None
    return pd.Timestamp(valor).date()  # type: ignore[arg-type]


# o tipo de cada coluna que não é texto (o resto sai como texto, vazio como ausente)
_CONVERSOES: dict[str, Callable[[object], object]] = {
    "participacao_pct": _numero,
    "operador": _logico,
    "altura_atual_m": _numero,
    "volume_atual_m3": _numero,
}


def _valor(nome: str, valor: object) -> object:
    return _CONVERSOES.get(nome, _texto)(valor)


def _indice_da_competencia(ano: object, mes: object) -> int | None:
    """O mês de competência como um número só (ano * 12 + mês - 1); None se a linha não traz os dois."""
    try:
        ano_, mes_ = int(str(ano).strip()), int(str(mes).strip())
    except ValueError:
        return None
    if not 1 <= mes_ <= MESES_NO_ANO:
        return None
    return ano_ * MESES_NO_ANO + mes_ - 1


def _competencia(indice: int) -> str:
    ano, mes = divmod(indice, MESES_NO_ANO)
    return f"{ano:04d}-{mes + 1:02d}"


def _no_envelope(fonte: str, valor: object, publico_em: date) -> dict[str, object]:
    return campo(valor, fonte=fonte, publico_em=publico_em, visto_em=None)


@dataclass
class _Processo:
    """A CFEM de um processo, substância e município: a 1ª linha (os campos como a fonte publicou), a soma
    dos 12 meses, a última competência e o dia mais novo em que uma linha usada ficou pública."""

    linha: dict
    soma: float = 0.0
    ultima: int = -1
    publico_em: date = date.min

    def somar(self, indice: int, valor: float | None, publico_em: date) -> None:
        self.soma += valor or 0.0
        self.ultima = max(self.ultima, indice)
        self.publico_em = max(self.publico_em, publico_em)


def limites(liberados: Iterable[str]) -> list[str]:
    """Os limites da resposta: os gerais e, depois do primeiro, os de cada bloco que o portão libera."""
    servidos = set(liberados)
    dos_blocos = [frase for tipo, frase in LIMITES_DO_BLOCO.items() if tipo in servidos]
    return [LIMITES[0], *dos_blocos, *LIMITES[1:]]


def nao_coberto(liberados: Iterable[str]) -> list[str]:
    """O que a rota não cobre: os ativos fora das bases e, antes, cada bloco que o portão não libera."""
    servidos = set(liberados)
    fora = [frase for tipo, frase in FORA_DA_ROTA.items() if tipo not in servidos]
    return [*fora, *NAO_COBERTO]


class LeitorDeAtivos:
    """Lê os ativos de uma empresa de uma porta para um pedido."""

    def __init__(self, porta: Porta, permitido: Permitido, linhas_maximas: int) -> None:
        self.porta = porta
        self.permitido = permitido
        self.linhas_maximas = linhas_maximas

    def _servidos(self, origem: OrigemDoBloco) -> tuple[str, ...]:
        return tuple(
            nome for nome in origem.campos if self.permitido(origem.fonte, nome, False)
        )

    def _contas_da_cfem(self) -> tuple[bool, bool]:
        """Se a soma em 12 meses e a última competência saem (as duas são conta nossa sobre a tabela)."""
        fonte = ORIGENS[ROYALTIES].fonte
        soma = self.permitido(fonte, VALOR_DA_CFEM, True)
        ultima = self.permitido(fonte, ANO_DA_CFEM, True) and self.permitido(
            fonte, MES_DA_CFEM, True
        )
        return soma, ultima

    def _cnpjs_da_raiz(self, tabela: str, raiz: str) -> list[str]:
        """Os CNPJs, como a tabela os grava, dos estabelecimentos da raiz (a empresa é a pessoa jurídica). O
        prefixo (formatado ou só com os caracteres) corta a tabela antes da conta da raiz, que confere."""
        formatada = f"{raiz[:2]}.{raiz[2:5]}.{raiz[5:8]}"
        linhas = self.porta.con.execute(
            f'SELECT DISTINCT cnpj FROM "{tabela}" '
            "WHERE (upper(CAST(cnpj AS VARCHAR)) LIKE $formatada OR upper(CAST(cnpj AS VARCHAR)) LIKE $crua) "
            "AND left(upper(regexp_replace(CAST(cnpj AS VARCHAR), '[^0-9A-Za-z]', '', 'g')), 8) = $raiz",
            {"raiz": raiz, "formatada": f"{formatada}%", "crua": f"{raiz}%"},
        ).fetchall()
        return sorted(str(linha[0]) for linha in linhas)

    def _dado_mais_novo(self, tabela: str, como_era_em: date) -> date | None:
        """O dia mais novo em que a base inteira (não só a empresa) publicou algo, até `como_era_em`."""
        (mais_novo,) = self.porta.con.execute(
            f'SELECT max(CAST("{PUBLICO_EM}" AS DATE)) FROM "{tabela}" '
            f'WHERE CAST("{PUBLICO_EM}" AS DATE) <= $dia',
            {"dia": como_era_em},
        ).fetchone() or (None,)
        return _dia(mais_novo)

    def _linhas(
        self, origem: OrigemDoBloco, raiz: str, como_era_em: date, colunas: list[str]
    ) -> pd.DataFrame:
        """As linhas da raiz na tabela, como eram no dia (vazia se a tabela não está na base)."""
        if origem.tabela not in views(self.porta.con):
            return pd.DataFrame(columns=colunas)
        if origem.coluna_da_raiz is not None:
            filtros: dict[str, object] = {origem.coluna_da_raiz: [raiz]}
        else:
            cnpjs = self._cnpjs_da_raiz(origem.tabela, raiz)
            if not cnpjs:
                return pd.DataFrame(columns=colunas)
            filtros = {"cnpj": cnpjs}
        return self.porta.ler(
            origem.tabela, como_era_em=como_era_em, filtros=filtros, colunas=colunas
        )

    def _cabecalho(
        self, origem: OrigemDoBloco, como_era_em: date, achou: bool
    ) -> dict[str, object]:
        mais_novo = (
            self._dado_mais_novo(origem.tabela, como_era_em)
            if origem.tabela in views(self.porta.con)
            else None
        )
        return {
            "achou": achou,
            "fonte": origem.fonte,
            "dado_mais_novo": None if mais_novo is None else mais_novo.isoformat(),
            "cobertura": origem.cobertura,
        }

    def _bloco_de_linhas(
        self,
        tipo: str,
        raiz: str,
        como_era_em: date,
        servidos: tuple[str, ...],
        cabem: int,
    ) -> _Bloco:
        """Um bloco em que cada linha da tabela é um item (os contratos da ANP e as barragens do SIGBM)."""
        origem = ORIGENS[tipo]
        extras = [PUBLICO_EM] + ([origem.visto_em] if origem.visto_em else [])
        colunas = list(dict.fromkeys([*origem.campos, *origem.ordem, *extras]))
        tabela = self._linhas(origem, raiz, como_era_em, colunas)
        tabela = tabela.sort_values(
            list(origem.ordem), na_position="last", kind="stable"
        )
        itens = []
        for linha in tabela.to_dict("records"):
            publico_em = _dia(linha[PUBLICO_EM])
            visto_em = _dia(linha[origem.visto_em]) if origem.visto_em else None
            item = {
                nome: campo(
                    valor, fonte=origem.fonte, publico_em=publico_em, visto_em=visto_em
                )
                for nome in servidos
                if (valor := _valor(nome, linha[nome])) is not None
            }
            if item:
                itens.append(item)
        pagina = itens[:cabem]
        corpo = self._cabecalho(origem, como_era_em, bool(itens)) | {
            "itens": pagina,
            "cortada": len(itens) > cabem,
        }
        return _Bloco(corpo, len(pagina))

    def _bloco_da_cfem(
        self,
        raiz: str,
        como_era_em: date,
        servidos: tuple[str, ...],
        cabem: int,
    ) -> _Bloco:
        """A CFEM por processo, substância e município: a soma dos 12 meses de competência que terminam no
        mês de `como_era_em` e a última competência com recolhimento (contas nossas)."""
        origem = ORIGENS[ROYALTIES]
        soma_sai, ultima_sai = self._contas_da_cfem()
        colunas = list(
            dict.fromkeys(
                [*origem.campos, ANO_DA_CFEM, MES_DA_CFEM, VALOR_DA_CFEM, PUBLICO_EM]
            )
        )
        tabela = self._linhas(origem, raiz, como_era_em, colunas)
        fim = como_era_em.year * MESES_NO_ANO + como_era_em.month - 1
        inicio = fim - MESES_DA_SOMA + 1
        processos: dict[tuple[str, ...], _Processo] = {}
        for linha in tabela.to_dict("records"):
            indice = _indice_da_competencia(linha[ANO_DA_CFEM], linha[MES_DA_CFEM])
            publico_em = _dia(linha[PUBLICO_EM])
            if indice is None or indice > fim or publico_em is None:
                continue
            chave = tuple(_texto(linha[nome]) or "" for nome in origem.ordem)
            processo = processos.setdefault(chave, _Processo(linha))
            processo.somar(
                indice,
                _numero(linha[VALOR_DA_CFEM]) if indice >= inicio else None,
                publico_em,
            )
        itens = []
        for _, processo in sorted(
            processos.items(), key=lambda par: (-par[1].soma, par[0])
        ):
            item = {
                nome: _no_envelope(origem.fonte, valor, processo.publico_em)
                for nome in servidos
                if (valor := _texto(processo.linha[nome])) is not None
            }
            if soma_sai:
                item["recolhido_12_meses"] = _no_envelope(
                    origem.fonte,
                    round(processo.soma, CASAS_DOS_REAIS),
                    processo.publico_em,
                )
            if ultima_sai:
                item["ultima_competencia"] = _no_envelope(
                    origem.fonte, _competencia(processo.ultima), processo.publico_em
                )
            if item:
                itens.append(item)
        pagina = itens[:cabem]
        corpo = self._cabecalho(origem, como_era_em, bool(itens)) | {
            "periodo": {"inicio": _competencia(inicio), "fim": _competencia(fim)},
            "itens": pagina,
            "cortada": len(itens) > cabem,
        }
        return _Bloco(corpo, len(pagina))

    def _liberados(self) -> dict[str, tuple[str, ...]]:
        """Os campos como a fonte publicou que o portão libera em cada bloco; o bloco sem nada liberado fica
        de fora (o da CFEM fica se ao menos uma das contas sai)."""
        liberados = {}
        for tipo, origem in ORIGENS.items():
            campos = self._servidos(origem)
            if campos or (tipo == ROYALTIES and any(self._contas_da_cfem())):
                liberados[tipo] = campos
        return liberados

    def ativos(self, cnpj: str, como_era_em: date) -> AtivosServidos | None:
        """Os ativos do CNPJ como eram em `como_era_em`, só com o que o portão libera; None se o CNPJ não é de
        empresa ou se o portão não libera nenhum bloco. Empresa que nenhuma base tem sai com `achou` falso em
        cada bloco."""
        normal = cnpj_.normalizar_cnpj(cnpj)
        if not normal:
            raise ValueError(f"CNPJ inválido: {cnpj!r}")
        liberados = self._liberados()
        if not liberados:
            return None
        if not e_empresa(self.porta, normal):
            return None
        raiz = normal[: cnpj_.TAMANHO_DA_RAIZ]
        cabem = max(self.linhas_maximas, 1)
        corpo: dict[str, object] = {
            "cnpj": normal,
            "como_era_em": como_era_em.isoformat(),
        }
        linhas = 0
        for tipo, servidos in liberados.items():
            if tipo == ROYALTIES:
                bloco = self._bloco_da_cfem(raiz, como_era_em, servidos, cabem - linhas)
            else:
                bloco = self._bloco_de_linhas(
                    tipo, raiz, como_era_em, servidos, cabem - linhas
                )
            corpo[tipo] = bloco.corpo
            linhas += bloco.linhas
        corpo["nao_coberto"] = nao_coberto(liberados)
        corpo["limites"] = limites(liberados)
        # a fonte de todo bloco servido vai na atribuição, ache ou não a empresa: o "não achou" e o dia do
        # dado mais novo também são da base dela
        fontes = {ORIGENS[tipo].fonte for tipo in liberados}
        return AtivosServidos(corpo=corpo, fontes=fontes, linhas=linhas)
