"""O perfil de uma empresa na API externa (linha 736, PR 2): `/data/v1/companies/{cnpj}/profile`, como era.

`LeitorDeFicha(porta, permitido).ficha(cnpj, como_era_em)` junta, em tipos simples e com as chaves em
português (a rota traduz na saída), o que a base sabia da empresa no dia, campo a campo pelo portão:

- `cadastro_na_receita`: a situação cadastral, a razão social, a natureza jurídica e o Simples como eram, pelo mesmo
  leitor de `companies` (`LeitorDeEmpresas`), e do estabelecimento a abertura, o CNAE principal, a UF e o município,
  da lista sem pessoa (`cnpj_estabelecimentos_pj`, a mesma da busca) no retrato mais novo já público (linha 955); ao
  lado do código da situação, do CNAE e do município vai o texto da tabela da Receita (`base/receita_codigos`), e o
  código que a tabela não tem fica sem texto (não se inventa); a tabela é a de hoje, não a do dia pedido (um
  código renomeado sai com o nome novo), e o cadastro e o estabelecimento podem vir de retratos de meses
  diferentes, cada um com o próprio `publico_em`;
- `entregas`: cada DFP e ITR que a companhia aberta devia até o dia, com o prazo da CVM, a primeira
  entrega e a situação da entrega, pela mesma regra da ficha da noite (`base.dossie.entregas_conhecidas_em`).

Cada campo sai no envelope, com a fonte e o dia em que ficou público. O perfil não lê a ficha da noite
(`dossies/atual`, que é só de hoje): monta tudo na hora para o dia pedido. A entrega que ainda não tinha
acontecido no dia sai como `not_filed`, sem a data dela; a falta de um documento conta como pública no dia
do prazo e só sai até o dia em que a base a conferiu (a montagem da tabela). A dívida com a União (PGFN)
fica fora: o portão não a deixa sair (sem a guarda dita, como na ficha de crédito).

Pessoa não sai (ADR 0108 D2.2): o CNPJ só é servido se a rede o conhece como empresa que não é pessoa
(`empresas.e_empresa`, dentro do `LeitorDeEmpresas`); sem o cadastro, nada sai, e o resto é `not_available`,
sem dizer o motivo. Campo negado pelo portão some da resposta, sem `null`. O documento (DFP, ITR) que o portão
não libera não some em silêncio (linha 881, `src/api_externa/nao_disponivel.py`): ele vai em
`entregas_nao_disponiveis` e os limites avisam que a lista de entregas não diz nada sobre ele; com algum
documento consultado, `entregas` sai sempre, vazia quando a empresa não tem entrega. Do mesmo jeito, o campo do
cadastro que o portão não libera, ou cuja tabela a base não tem (linha 891: no piloto, a situação cadastral e o
Simples ficaram fora do registro), vai em `campos_do_cadastro_nao_disponiveis`, com o nome de fora: sem a lista, o cadastro só com o
nome leria como "a empresa não tem situação". O campo que falta porque a base não tem a versão do dia (a raiz que
saiu do arquivo do Simples) não entra: ele foi consultado.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from base import cnpj as cnpj_
from base import receita_codigos
from base.dias_uteis import dias_uteis
from base.dossie import entregas_conhecidas_em
from base.porta import Porta
from base.porta.duckdb import condicao_como_era, dia_de, nome_da_view
from base.porta.rede import views
from src.api_externa import nao_disponivel
from src.api_externa.conjuntos import Permitido, empresas
from src.api_externa.conjuntos.empresas import LeitorDeEmpresas
from src.api_externa.envelope import campo
from src.api_externa.nomes import NOMES_DE_FORA
from src.api_externa.porta_compartilhada import lembrar

CONJUNTO = "profiles"
TABELA_DAS_ENTREGAS = "rotulos_atraso"
FONTES_DAS_ENTREGAS = {"DFP": "cvm-hist-dfp", "ITR": "cvm-hist-itr"}
CAMPOS_DAS_ENTREGAS = (
    "documento", "referencia", "prazo", "primeira_entrega", "dias_uteis_de_atraso",
    "situacao_da_entrega",
)  # fmt: skip
# contas nossas sobre o índice da CVM (o rótulo e os dias úteis), não o dado como a fonte publicou
DERIVADOS = frozenset({"dias_uteis_de_atraso", "situacao_da_entrega"})
# as colunas de `rotulos_atraso` de onde sai a situação da entrega (`_situacao_entregue`)
COLUNAS_DA_SITUACAO = ("atrasou", "atraso_grave", "zona_cinzenta")
CHAVES_DO_PEDIDO = ("cnpj", "como_era_em")
# do estabelecimento (linha 955): a lista sem pessoa que a busca lê, no retrato mais novo já público
TABELA_DO_ESTABELECIMENTO = empresas.LISTA_DE_ESTABELECIMENTOS
CAMPOS_DO_ESTABELECIMENTO = (
    "data_inicio_atividade",
    "cnae_principal",
    "uf",
    "municipio",
)
# o texto de cada código pela tabela da Receita, ao lado do código (que continua saindo): campo -> (nome, tabela)
TEXTOS_DOS_CODIGOS = {
    "situacao_cadastral": (
        "situacao_cadastral_texto",
        receita_codigos.situacao_cadastral,
    ),
    "cnae_principal": ("cnae_principal_texto", receita_codigos.cnae),
    "municipio": ("municipio_texto", receita_codigos.municipio),
}
# de onde sai cada campo novo do cadastro: do estabelecimento, ou do código que o texto traduz
ORIGEM_DO_CAMPO_NOVO = {
    **{nome: nome for nome in CAMPOS_DO_ESTABELECIMENTO},
    **{texto: codigo for codigo, (texto, _) in TEXTOS_DOS_CODIGOS.items()},
}
# os textos: não são coluna de tabela, saem da tabela da Receita pelo código
TEXTOS_DE_FORA_DA_TABELA = frozenset(texto for texto, _ in TEXTOS_DOS_CODIGOS.values())
# a tabela de cada campo novo, a mesma da linha de direito que o portão julga
TABELA_DO_CAMPO_NOVO = {
    nome: empresas.TABELA_DO_CAMPO_DO_CADASTRO.get(origem, TABELA_DO_ESTABELECIMENTO)
    for nome, origem in ORIGEM_DO_CAMPO_NOVO.items()
}

# a situação de cada entrega, em código de fora (D7): a regra de cada rótulo é a da tabela (`rotulos_atraso`)
NO_PRAZO = "on_time"
ATRASOU = "late"
ZONA_CINZENTA = "gray_zone"  # atraso curto, que um feriado local pode explicar
ATRASO_GRAVE = "severely_late"
NAO_ENTREGUE = "not_filed"  # até o dia pedido (ou até o dia em que a base conferiu)

# os limites que valem para todo perfil; os das entregas só entram quando algum documento foi consultado
LIMITES_GERAIS = (
    "Cada campo traz a fonte e o dia em que ficou público: nada publicado depois de known_at entra.",
    "Pessoa natural (MEI, empresário individual) não é servida.",
)
_FRASES_DAS_ENTREGAS = (
    (
        "As entregas cobrem só as companhias do cadastro de companhias abertas da CVM; uma empresa sem "
        "entregas não quer dizer que nada era devido."
    ),
    (
        "A situação de cada entrega é a regra do TickerLab sobre o índice público da CVM (prazo com feriados "
        "e prorrogações); não é opinião sobre a empresa, e nada aqui é recomendação de investimento."
    ),
)
LIMITES_DO_DOCUMENTO = {
    documento: _FRASES_DAS_ENTREGAS for documento in FONTES_DAS_ENTREGAS
}
# o nome de dentro da lista dos documentos (DFP, ITR) que o portão não libera (ou sem a tabela na base)
NAO_DISPONIVEIS = "entregas_nao_disponiveis"
LIMITE_DO_DOCUMENTO_NAO_DISPONIVEL = nao_disponivel.aviso(
    NAO_DISPONIVEIS, "documentos", "a lista de entregas"
)
# a lista e o aviso dos campos do cadastro de fora são os de `companies` (linha 898): um lugar só
CAMPOS_DO_CADASTRO_NAO_DISPONIVEIS = empresas.CAMPOS_DO_CADASTRO_NAO_DISPONIVEIS
LIMITE_DO_CAMPO_DO_CADASTRO_NAO_DISPONIVEL = (
    empresas.LIMITE_DO_CAMPO_DO_CADASTRO_NAO_DISPONIVEL
)


def limites(
    documentos_servidos: Iterable[str],
    nao_disponiveis: Sequence[str] = (),
    campos_do_cadastro_de_fora: Sequence[str] = (),
) -> list[str]:
    """Os limites de um perfil: os gerais, o aviso do cadastro quando algum campo dele ficou de fora, as frases
    das entregas quando algum documento foi consultado e, quando algum ficou de fora, o aviso de que a lista de
    entregas não diz nada sobre ele."""
    das_entregas = nao_disponivel.limites(
        LIMITES_GERAIS,
        LIMITES_DO_DOCUMENTO,
        documentos_servidos,
        nao_disponiveis,
        LIMITE_DO_DOCUMENTO_NAO_DISPONIVEL,
    )
    do_cadastro = (
        [LIMITE_DO_CAMPO_DO_CADASTRO_NAO_DISPONIVEL]
        if campos_do_cadastro_de_fora
        else []
    )
    # o cadastro vem antes das entregas na resposta: o aviso dele também
    return [*das_entregas[:1], *do_cadastro, *das_entregas[1:]]


# os limites com os dois documentos consultados
LIMITES = tuple(limites(FONTES_DAS_ENTREGAS))


@dataclass(frozen=True)
class FichaServida:
    """O que sai de um perfil: o corpo, as fontes usadas (para a atribuição) e as linhas servidas."""

    corpo: dict
    fontes: set[str] = field(default_factory=set)
    linhas: int = 0


def _sim(valor: object) -> bool:
    return False if pd.isna(valor) else bool(valor)  # type: ignore[arg-type]


def _dia(valor: object) -> str | None:
    return None if pd.isna(valor) else pd.Timestamp(valor).date().isoformat()  # type: ignore[arg-type]


def _do_estabelecimento(nome: str, valor: object) -> object:
    """O valor da lista num tipo que vira JSON: a abertura em ISO, o resto em texto, vazio em None."""
    if valor is None or pd.isna(valor):  # type: ignore[arg-type]
        return None
    if nome == "data_inicio_atividade":
        return _dia(valor)
    return str(valor).strip() or None


def texto_do_codigo(campo_do_codigo: str, codigo: object) -> str | None:
    """O texto do código pela tabela da Receita; None sem código ou quando a tabela não o tem (o
    `receita_codigos` devolveria "código X", que não é texto da Receita)."""
    if not isinstance(codigo, str) or not codigo.strip():
        return None
    _, traduzir = TEXTOS_DOS_CODIGOS[campo_do_codigo]
    texto = traduzir(codigo)
    if texto is None or texto.startswith("código "):
        return None
    return texto


def _situacao_entregue(linha: pd.Series) -> str:
    """O rótulo que a tabela deu à entrega, pelas colunas booleanas dela (a rota não recalcula)."""
    if not _sim(linha["atrasou"]):
        return NO_PRAZO
    if _sim(linha["atraso_grave"]):
        return ATRASO_GRAVE
    if _sim(linha["zona_cinzenta"]):
        return ZONA_CINZENTA
    return ATRASOU


def _dias_uteis_desde(prazo: pd.Timestamp, dia: pd.Timestamp) -> int:
    """Os dias úteis do prazo (conta) até `dia` (não conta), como a tabela conta até a entrega."""
    return max(int(dias_uteis(pd.Series([prazo]), pd.Series([dia]))[0]), 0)


def entrega_no_dia(
    linha: pd.Series, dia: pd.Timestamp
) -> tuple[dict[str, object], pd.Timestamp]:
    """Uma linha de `entregas_conhecidas_em` como a base a conhecia em `dia`, e o dia em que esse fato
    ficou público: a entrega até `dia` vale pela entrega; a que ainda não tinha acontecido (ou que a tabela
    não tem) sai `not_filed`, sem data de entrega, e a falta vale pelo prazo."""
    entrega = linha["primeira_entrega"]
    entregue = not pd.isna(entrega) and entrega <= dia
    valores: dict[str, object] = {
        "documento": str(linha["documento"]),
        "referencia": _dia(linha["referencia"]),
        "prazo": _dia(linha["prazo"]),
    }
    if entregue:
        atraso = linha["dias_uteis_de_atraso"]
        valores |= {
            "primeira_entrega": _dia(entrega),
            "dias_uteis_de_atraso": None if pd.isna(atraso) else int(atraso),  # type: ignore[call-overload]
            "situacao_da_entrega": _situacao_entregue(linha),
        }
        return valores, pd.Timestamp(entrega)
    ate = dia if not pd.isna(entrega) else linha["conferido_ate"]
    valores |= {
        "dias_uteis_de_atraso": _dias_uteis_desde(linha["prazo"], ate),
        "situacao_da_entrega": NAO_ENTREGUE,
    }
    return valores, pd.Timestamp(linha["prazo"])


def chave_do_retrato_do_estabelecimento(como_era_em: date) -> tuple[str, str]:
    """A chave, na memória da porta dona, do mês do estabelecimento num dia: só o dia, nada de quem pede."""
    return ("retrato_do_estabelecimento", dia_de(como_era_em))


class LeitorDeFicha:
    """Lê o perfil de uma empresa de uma porta para um pedido."""

    def __init__(self, porta: Porta, permitido: Permitido) -> None:
        self.porta = porta
        self.permitido = permitido

    def _rotulos(self, normal: str) -> pd.DataFrame | None:
        """As linhas da companhia em `rotulos_atraso`, lidas sem `como_era_em`: o documento sem entrega
        não tem `publico_em` e a porta o esconderia; o corte do dia fica em `entregas_conhecidas_em`."""
        if TABELA_DAS_ENTREGAS not in views(self.porta.con):
            return None
        return self.porta.ler(
            TABELA_DAS_ENTREGAS, filtros={"cnpj": cnpj_.formatar(normal)}
        )

    def _entrega_servida(
        self, linha: pd.Series, dia: pd.Timestamp
    ) -> tuple[dict, str] | None:
        """A entrega com os campos que o portão libera, cada um no envelope; None se nada sai dela."""
        fonte = FONTES_DAS_ENTREGAS.get(str(linha["documento"]))
        if fonte is None:
            return None
        valores, publico_em = entrega_no_dia(linha, dia)
        # só os campos da lista saem, nesta ordem: um campo novo em `entrega_no_dia` não escapa sozinho
        servidos = {
            nome: campo(valores[nome], fonte=fonte, publico_em=publico_em.date(), visto_em=None)
            for nome in CAMPOS_DAS_ENTREGAS
            if nome in valores and self.permitido(fonte, nome, nome in DERIVADOS)
        }  # fmt: skip
        return (servidos, fonte) if servidos else None

    def _retrato_do_estabelecimento(self, como_era_em: date) -> str | None:
        """O mês do retrato mais novo da lista de estabelecimentos já público no dia; None sem a lista.

        O `max` varre a lista inteira (no PC, em meia CPU, 1 a 4 s por análise): o mês de cada dia fica lembrado
        enquanto a base é a mesma, com o dia na chave, para nunca responder a outro dia (linha 1015, item f)."""
        return lembrar(
            self.porta,
            chave_do_retrato_do_estabelecimento(como_era_em),
            lambda: self._ler_o_retrato_do_estabelecimento(como_era_em),
        )

    def _ler_o_retrato_do_estabelecimento(self, como_era_em: date) -> str | None:
        con = self.porta.con
        if TABELA_DO_ESTABELECIMENTO not in views(con):
            return None
        condicao = condicao_como_era(
            self.porta.colunas(TABELA_DO_ESTABELECIMENTO), TABELA_DO_ESTABELECIMENTO
        )
        achado = con.execute(
            f'SELECT max({empresas.MES}) FROM "{nome_da_view(TABELA_DO_ESTABELECIMENTO)}" WHERE {condicao}',
            {"dia": dia_de(como_era_em)},
        ).fetchone()
        mes = None if achado is None else achado[0]
        return None if mes is None else str(mes)

    def _estabelecimento(self, normal: str, como_era_em: date) -> dict[str, dict]:
        """A abertura, o CNAE, a UF e o município do CNPJ no retrato mais novo já público da lista sem pessoa,
        só o que o portão libera; nada sem a lista, sem retrato público ou se o CNPJ não está nele uma só vez
        (o que saiu da lista não leva o dado de um retrato mais velho)."""
        liberados = [
            nome
            for nome in CAMPOS_DO_ESTABELECIMENTO
            if self.permitido(empresas.FONTE, nome, False)
        ]
        mes = self._retrato_do_estabelecimento(como_era_em) if liberados else None
        if mes is None:
            return {}
        linhas = self.porta.ler(
            TABELA_DO_ESTABELECIMENTO,
            como_era_em=como_era_em,
            filtros={"cnpj": normal, empresas.MES: mes},
            colunas=[*liberados, empresas.MES, empresas.PUBLICADO_EM],
        )
        if len(linhas) != 1:
            return {}
        linha = linhas.iloc[0]
        publico_em = pd.Timestamp(linha[empresas.PUBLICADO_EM]).date()
        return {
            nome: campo(_do_estabelecimento(nome, linha[nome]), fonte=empresas.FONTE, publico_em=publico_em, visto_em=None)
            for nome in liberados
        }  # fmt: skip

    def _com_os_textos(self, cadastro: dict[str, object]) -> dict[str, object]:
        """O cadastro com o texto de cada código logo depois dele, no envelope do código (a mesma fonte e o
        mesmo dia), se o portão libera o texto e a tabela da Receita tem o código."""
        saida: dict[str, object] = {}
        for nome, valor in cadastro.items():
            saida[nome] = valor
            if nome not in TEXTOS_DOS_CODIGOS or not isinstance(valor, dict):
                continue
            nome_do_texto, _ = TEXTOS_DOS_CODIGOS[nome]
            texto = texto_do_codigo(nome, valor.get("valor"))
            if texto is None or not self.permitido(
                valor["fonte"], nome_do_texto, False
            ):
                continue
            saida[nome_do_texto] = {**valor, "valor": texto}
        return saida

    def campos_novos_de_fora(self) -> list[str]:
        """Os campos novos do cadastro (linha 955) que o portão não libera ou cuja tabela a base não tem, com o
        nome de fora; o texto de um código que ficou de fora fica de fora também."""
        existem = views(self.porta.con)
        return [
            NOMES_DE_FORA[nome]
            for nome, origem in ORIGEM_DO_CAMPO_NOVO.items()
            if TABELA_DO_CAMPO_NOVO[nome] not in existem
            or not self.permitido(empresas.FONTE, origem, False)
            or not self.permitido(empresas.FONTE, nome, False)
        ]

    def _documentos_servidos(self) -> dict[str, list[str]]:
        """Os campos que o portão libera de cada documento (DFP, ITR), na ordem de `CAMPOS_DAS_ENTREGAS`;
        sem a tabela na base, nenhum documento é consultado."""
        tem_a_tabela = TABELA_DAS_ENTREGAS in views(self.porta.con)
        return {
            documento: [
                nome
                for nome in CAMPOS_DAS_ENTREGAS
                if tem_a_tabela and self.permitido(fonte, nome, nome in DERIVADOS)
            ]
            for documento, fonte in FONTES_DAS_ENTREGAS.items()
        }

    def _entregas(self, normal: str, como_era_em: date) -> tuple[list[dict], set[str]]:
        """As entregas que a base conhecia no dia, da mais nova à mais velha, só dos documentos com campo
        liberado (a entrega sem nenhum campo liberado não sai); a lista vazia é a empresa sem entrega."""
        rotulos = self._rotulos(normal)
        if rotulos is None:
            return [], set()
        dia = pd.Timestamp(como_era_em).normalize()
        servidas = [
            servida
            for _, linha in entregas_conhecidas_em(rotulos, dia).iterrows()
            if (servida := self._entrega_servida(linha, dia)) is not None
        ]
        return [linha for linha, _ in servidas], {fonte for _, fonte in servidas}

    def ficha(self, cnpj: str, como_era_em: date) -> FichaServida | None:
        """O perfil do CNPJ como era em `como_era_em`, só com o que o portão libera; None se o CNPJ não é
        de empresa ou se o cadastro não sai (sem cadastro, nada sai)."""
        normal = cnpj_.normalizar_cnpj(cnpj)
        if not normal:
            raise ValueError(f"CNPJ inválido: {cnpj!r}")
        cadastro = LeitorDeEmpresas(self.porta, self.permitido).empresa(
            normal, como_era_em
        )
        if cadastro is None:
            return None
        do_cadastro = {
            nome: valor
            for nome, valor in cadastro.corpo.items()
            if nome not in (*CHAVES_DO_PEDIDO, *empresas.CHAVES_DO_AVISO)
        }
        do_cadastro |= self._estabelecimento(normal, como_era_em)
        blocos: dict[str, object] = {
            "cadastro_na_receita": self._com_os_textos(do_cadastro)
        }
        fontes = set(cadastro.fontes)
        linhas = cadastro.linhas
        documentos = self._documentos_servidos()
        servidos = [documento for documento, campos in documentos.items() if campos]
        nao_disponiveis = nao_disponivel.nao_disponiveis(documentos)
        if servidos:
            # o bloco sai sempre que algum documento foi consultado, mesmo vazio: sumir é só "não consultado"
            entregas, fontes_das_entregas = self._entregas(normal, como_era_em)
            blocos["entregas"] = entregas
            fontes |= fontes_das_entregas
            linhas += len(entregas)
        # a lista do cadastro vem pronta do leitor de `companies`, já com o nome de fora; os campos novos, depois
        campos_de_fora = [
            *cadastro.corpo[CAMPOS_DO_CADASTRO_NAO_DISPONIVEIS],
            *self.campos_novos_de_fora(),
        ]
        corpo = {
            "cnpj": normal,
            "como_era_em": como_era_em.isoformat(),
            **blocos,
            CAMPOS_DO_CADASTRO_NAO_DISPONIVEIS: campos_de_fora,
            NAO_DISPONIVEIS: nao_disponiveis,
            "limites": limites(servidos, nao_disponiveis, campos_de_fora),
        }
        return FichaServida(corpo, fontes, linhas)
