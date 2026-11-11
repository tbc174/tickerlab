"""Encontrar empresas na tela do analista (linha 798, PR 3): setor, UF, idade, capital e estabelecimentos.

A tela busca pelo mesmo leitor da API externa (`LeitorDeProspeccao`, `GET /data/v1/companies`), com o mesmo
portão e a mesma prontidão das tabelas (`leitura.permitido_na_tela`): o analista vê na tela só o que a chave
dele veria pela API. Só os filtros que quem não programa entende:

- setor: a seção do CNAE do IBGE (de A a S), que vira as divisões de dois dígitos do CNAE principal. Ficam de
  fora a administração pública (O), os serviços domésticos (T, empregador pessoa física) e os organismos
  internacionais (U): nenhum é alvo de mandato de M&A;
- UF da matriz;
- idade mínima em anos, contada da abertura na Receita até hoje;
- capital social declarado (mínimo e máximo) e número mínimo de estabelecimentos ativos, com a ordem por um
  deles. São uma aproximação do tamanho: a Receita não tem "médio porte" nem faturamento, e a tela não sugere
  um nem outro.

Sempre a matriz ativa (uma linha por empresa).
"""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import date, timedelta

from base import cnae, cnes, receita_codigos
from base.porta import Porta
from src.analista import leitura
from src.api_externa.conjuntos import prospeccao
from src.api_externa.envelope import fontes_da_resposta
from src.portao_externo import Regras

SEM_FILTRO = "sem_filtro"
FiltroInvalido = prospeccao.FiltroInvalido

FORA_DA_BUSCA = frozenset({"O", "T", "U"})
SETORES: dict[str, str] = {
    letra: nome for letra, nome in cnae.SECOES.items() if letra not in FORA_DA_BUSCA
}
UFS: tuple[str, ...] = cnes.UFS
# três seções somam no máximo umas trinta divisões, abaixo do teto de valores por filtro do leitor
SETORES_MAXIMOS = 3
IDADE_MAXIMA = 100
TAMANHO_DA_PAGINA = 50
PAGINAS_DA_PLANILHA = 10  # o Excel leva no máximo dez páginas da tela de uma vez
_DIVISOES_DO_CNAE = range(1, 100)
CAPITAL_MAXIMO = prospeccao.CAPITAL_MAXIMO
ESTABELECIMENTOS_MAXIMOS = prospeccao.FILIAIS_MAXIMAS
# a ordem como a tela a oferece -> a ordem da API (`sort`) e o nome na tela; sem ordem é pelo CNPJ
ORDENS: dict[str, tuple[str, str]] = {
    "maior_capital": ("-capital", "Maior capital social"),
    "menor_capital": ("capital", "Menor capital social"),
    "mais_estabelecimentos": ("-branches", "Mais estabelecimentos ativos"),
}

LIMITES = (
    "Uma linha por empresa: a matriz, com cadastro ativo na Receita Federal.",
    "O setor é a seção do CNAE principal, como o IBGE a define; atividades secundárias não entram.",
    "A idade conta a partir da data de abertura no cadastro da Receita, até hoje.",
    "Cada campo traz a fonte e o dia em que ficou público: nada publicado depois de hoje entra.",
    "O porte da Receita é o declarado no cadastro e não mede faturamento.",
    (
        "Capital social e número de estabelecimentos ativos são só uma aproximação do tamanho: o capital é "
        "o declarado na Receita, não o patrimônio, e nenhum dos dois mede faturamento."
    ),
    "Nada aqui é recomendação de investimento.",
)


@dataclass(frozen=True)
class Filtros:
    """O que o analista escolheu na tela; `cursor` pede a página seguinte da mesma busca."""

    setores: tuple[str, ...] = ()
    ufs: tuple[str, ...] = ()
    idade_minima: int | None = None
    capital_minimo: float | None = None
    capital_maximo: float | None = None
    estabelecimentos_minimo: int | None = None
    ordem: str | None = None  # uma chave de `ORDENS`; None é pelo CNPJ
    cursor: str | None = None

    def vazio(self) -> bool:
        """Nenhum filtro (a ordem não filtra): a tela não lê a base inteira."""
        numeros = (
            self.idade_minima,
            self.capital_minimo,
            self.capital_maximo,
            self.estabelecimentos_minimo,
        )
        return not self.setores and not self.ufs and all(n is None for n in numeros)


def divisoes(setor: str) -> tuple[str, ...]:
    """As divisões (dois dígitos) do CNAE que formam a seção `setor`, como o IBGE as agrupa."""
    nome = SETORES[setor]
    return tuple(
        f"{d:02d}"
        for d in _DIVISOES_DO_CNAE
        if cnae.secao_do_cnae(f"{d:02d}00000") == nome
    )


def ordens_como_lista() -> list[dict[str, str]]:
    """As ordens que a tela oferece além da do CNPJ, para o formulário."""
    return [{"codigo": codigo, "nome": nome} for codigo, (_, nome) in ORDENS.items()]


def setores_como_lista() -> list[dict[str, str]]:
    """Os setores da busca, na ordem do IBGE, para a tela montar o formulário."""
    return [{"codigo": letra, "nome": nome} for letra, nome in SETORES.items()]


def aberta_ate(hoje: date, anos: int) -> date:
    """O último dia de abertura de uma empresa com pelo menos `anos` anos em `hoje` (29/02 vira 28/02)."""
    try:
        return hoje.replace(year=hoje.year - anos)
    except ValueError:
        return hoje.replace(year=hoje.year - anos, day=hoje.day - 1)


# o porte como a API o diz -> como a Receita o escreve no cadastro
PORTES = {
    "micro": "Microempresa",
    "small": "Empresa de pequeno porte",
    "other": "Demais",
    "not_informed": "Não informado",
}
# o campo servido -> o nome legível ao lado e a tabela de códigos da Receita que o traduz
_DESCRICOES = (
    ("cnae_principal", "cnae_descricao", receita_codigos.cnae),
    ("municipio", "municipio_nome", receita_codigos.municipio),
    ("porte", "porte_descricao", PORTES.get),
)


def legivel(empresa: Mapping) -> dict:
    """A empresa como o leitor a serviu, mais o nome ao lado de cada código (CNAE, município e porte), pelas
    tabelas de códigos da Receita. Só de campo servido: o que o portão nega continua de fora."""
    nomes: dict[str, str] = {}
    for campo, nome, traduzir in _DESCRICOES:
        servido = empresa.get(campo)
        valor = servido.get("valor") if isinstance(servido, Mapping) else None
        if valor is not None and (traduzido := traduzir(str(valor))):
            nomes[nome] = traduzido
    return {**empresa, **nomes}


def _validar(filtros: Filtros) -> None:
    if len(filtros.setores) > SETORES_MAXIMOS:
        raise FiltroInvalido
    if any(setor not in SETORES for setor in filtros.setores):
        raise FiltroInvalido
    if any(uf not in UFS for uf in filtros.ufs):
        raise FiltroInvalido
    idade = filtros.idade_minima
    if idade is not None and not 1 <= idade <= IDADE_MAXIMA:
        raise FiltroInvalido
    if filtros.ordem is not None and filtros.ordem not in ORDENS:
        raise FiltroInvalido
    # capital e estabelecimentos: a faixa e o mínimo acima do máximo o leitor da API confere


def busca_da_api(filtros: Filtros, hoje: date) -> prospeccao.Busca:
    """Os filtros da tela como a busca da API os escreve (a mesma validação de `busca_dos_pedidos`).

    `FiltroInvalido` se algo está fora da lista ou da faixa, ou se o cursor não é um cursor."""
    _validar(filtros)
    idade = filtros.idade_minima
    # o leitor filtra a abertura com "<": o dia seguinte ao limite inclui quem faz aniversário hoje
    antes = None if idade is None else aberta_ate(hoje, idade) + timedelta(days=1)
    return prospeccao.busca_dos_pedidos(
        cnae=[d for setor in filtros.setores for d in divisoes(setor)],
        state=list(filtros.ufs),
        municipality=[],
        size=[],
        legal_nature=[],
        registration_status=[],
        opened_before=antes,
        opened_after=None,
        head_office=True,
        cursor=filtros.cursor,
        limit=TAMANHO_DA_PAGINA,
        capital_min=filtros.capital_minimo,
        capital_max=filtros.capital_maximo,
        branches_min=filtros.estabelecimentos_minimo,
        sort=None if filtros.ordem is None else ORDENS[filtros.ordem][0],
    )


def buscar(
    porta: Porta, filtros: Filtros, *, hoje: date, regras: Regras | None = None
) -> leitura.Resposta:
    """Uma página da busca no retrato público hoje.

    Estados: `sem_filtro` (nada lido); `nao_liberada` (o portão não deixa sair a razão social ou algum campo
    que filtra, decidido sem consultar a base, ou ainda não há retrato público); `pronta`, com o corpo do
    leitor da API. `FiltroInvalido` se o pedido está fora do que a tela oferece (a rota responde 422)."""
    if filtros.vazio():
        return leitura.Resposta(SEM_FILTRO)
    busca = busca_da_api(filtros, hoje)
    permitido = leitura.permitido_na_tela(prospeccao.CONJUNTO, hoje, regras)
    precisa = {"razao_social", *busca.campos_filtrados()}
    if not all(permitido(prospeccao.FONTE, campo, False) for campo in precisa):
        return leitura.Resposta(leitura.NAO_LIBERADA)
    servida = prospeccao.LeitorDeProspeccao(porta, permitido, TAMANHO_DA_PAGINA).buscar(
        busca, hoje
    )
    if servida is None:
        return leitura.Resposta(leitura.NAO_LIBERADA)
    return leitura.Resposta(
        leitura.PRONTA,
        servida.corpo,
        fontes_da_resposta(servida.fontes),
        servida.linhas,
    )


def para_planilha(
    porta: Porta, filtros: Filtros, *, hoje: date, regras: Regras | None = None
) -> leitura.Resposta:
    """A busca para o Excel: as páginas seguidas, até `PAGINAS_DA_PLANILHA`, com os nomes ao lado dos
    códigos; `cortada` diz se ficou empresa de fora. Os mesmos estados de `buscar`."""
    resposta = buscar(porta, filtros, hoje=hoje, regras=regras)
    if resposta.corpo is None:
        return resposta
    empresas = list(resposta.corpo["empresas"])
    fontes = {fonte["fonte"]: fonte for fonte in resposta.fontes}
    corpo = resposta.corpo
    for _ in range(PAGINAS_DA_PLANILHA - 1):
        if not corpo["cortada"]:
            break
        seguinte = buscar(
            porta,
            replace(filtros, cursor=corpo["proximo_cursor"]),
            hoje=hoje,
            regras=regras,
        )
        if seguinte.corpo is None:
            break
        corpo = seguinte.corpo
        empresas += corpo["empresas"]
        fontes |= {fonte["fonte"]: fonte for fonte in seguinte.fontes}
    junta = {
        "como_era_em": resposta.corpo["como_era_em"],
        "empresas": [legivel(empresa) for empresa in empresas],
        "cortada": corpo["cortada"],
    }
    return leitura.Resposta(
        leitura.PRONTA, junta, [fontes[f] for f in sorted(fontes)], len(empresas)
    )
