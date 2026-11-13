"""Os prompts do conector (linha 901): os fluxos da casa de M&A prontos para o analista escolher.

Prompt no MCP é "controlado pelo usuário" (especificação 2025-06-18, `server/prompts`): o analista o escolhe
no cliente (no Claude, entre os prompts do conector) e preenche os argumentos; o prompt só monta o pedido,
que leva às ferramentas. Nenhum prompt lê a base nem a API: o dado continua saindo só pelas ferramentas,
com o portão por conjunto e o filtro de pessoa delas. O ChatGPT pode não mostrar prompts (não confirmado
na documentação em 13/11/2026): nada do roteiro depende deles.

Os argumentos chegam como texto e são conferidos antes de entrar no pedido (CNPJ, CNAE, UF, data, anos).
"""

import re
from collections.abc import Callable
from datetime import date
from typing import Annotated

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.shared.exceptions import MCPError
from mcp.types import INVALID_PARAMS
from pydantic import Field

from conector_remoto.ferramentas import ANOS_MAXIMO_DOS_COMPRADORES, cnpj_do_pedido

FECHO = (
    "Cite a fonte e a data de cada número, separe o que a base diz do que você deduz e liste à parte o "
    "que faltou e por quê, sem preencher lacuna com estimativa. Não traga dado de pessoa física. Ferramenta "
    "que a chave não pode usar também é lacuna. Nada aqui é recomendação de investimento."
)
# só ASCII: o `\d` do Python aceita dígitos de outras escritas, e o `upper` faz "ß" virar "SS"
_CNAE = re.compile(r"[0-9]{2,7}")
# a ferramenta de compradores aceita só a classe ou a subclasse
_CNAE_DE_CLASSE = re.compile(r"[0-9]{5}|[0-9]{7}")
_UF = re.compile(r"[A-Za-z]{2}")
_NUMERO = re.compile(r"[0-9]{1,3}")
_PONTUACAO_DO_CNAE = re.compile(r"[\s./-]")
MAXIMO_DE_ANOS_DE_ABERTURA = 100

_DESCRICAO_DO_CNPJ = "CNPJ da empresa (14 caracteres, com ou sem pontuação)."
_DESCRICAO_DA_DATA = "Opcional: ver o dado como era conhecido neste dia (AAAA-MM-DD)."
_DESCRICAO_DO_CNAE = (
    "Código CNAE do setor, 2 a 7 dígitos ('62' traz a divisão inteira)."
)

ArgumentoCnpj = Annotated[str, Field(description=_DESCRICAO_DO_CNPJ)]
ArgumentoData = Annotated[str, Field(description=_DESCRICAO_DA_DATA)]
ArgumentoCnae = Annotated[str, Field(description=_DESCRICAO_DO_CNAE)]
ArgumentoCnaeDeClasse = Annotated[
    str,
    Field(
        description="Classe (5 dígitos) ou subclasse (7 dígitos) do CNAE; pontuação vale."
    ),
]


MENSAGEM_DE_DATA = "Data em formato errado: use AAAA-MM-DD."


def montar(pedido: Callable[[], str]) -> str:
    """Monta o pedido; argumento fora da forma vira erro de parâmetro com a frase em português.

    Sem isto o SDK devolveria só "Error rendering prompt", e o analista não saberia o que corrigir. A frase
    é nossa, fixa: nunca repete o que foi digitado.
    """
    try:
        return pedido()
    except ToolError as erro:
        raise MCPError(INVALID_PARAMS, str(erro)) from None
    except ValueError as erro:
        raise MCPError(INVALID_PARAMS, str(erro)) from None


def _cnae(
    texto: str,
    forma: re.Pattern[str] = _CNAE,
    mensagem: str = "CNAE tem de 2 a 7 dígitos.",
) -> str:
    limpo = _PONTUACAO_DO_CNAE.sub("", texto)
    if not forma.fullmatch(limpo):
        raise ValueError(mensagem)
    return limpo


def _uf(texto: str) -> str:
    limpo = texto.strip()
    if not _UF.fullmatch(limpo):
        raise ValueError("UF tem duas letras (ex.: SP).")
    return limpo.upper()


def _data(texto: str) -> str:
    """A data em AAAA-MM-DD, ou vazio; `ValueError` se não é uma data."""
    limpo = texto.strip()
    if not limpo:
        return ""
    try:
        return date.fromisoformat(limpo).isoformat()
    except ValueError:
        raise ValueError(MENSAGEM_DE_DATA) from None


def _anos(texto: str, maximo: int, mensagem: str) -> int | None:
    """O número de anos, de 1 a `maximo`, ou None se veio vazio; `ValueError` com a `mensagem` se não."""
    limpo = texto.strip()
    if not limpo:
        return None
    if not _NUMERO.fullmatch(limpo) or not 1 <= int(limpo) <= maximo:
        raise ValueError(mensagem)
    return int(limpo)


def _no_dia(como_era_em: str) -> str:
    return (
        f" Use `como_era_em` = {como_era_em} em todas as chamadas."
        if como_era_em
        else ""
    )


def triagem(cnpj: str, como_era_em: str = "") -> str:
    """O pedido da triagem de um CNPJ antes da reunião."""
    return (
        f"Faça a triagem da empresa de CNPJ {cnpj_do_pedido(cnpj)} para uma reunião de originação: "
        "quem é (cadastro, situação, idade, porte e CNAE) com `ficha_da_empresa`, o que "
        "aconteceu com ela com `eventos` e as participações e o auditor que a base tiver com `vinculos` "
        "(profundidade 1; leia os `limits`, que dizem o que a base cobre para empresa fechada)."
        f"{_no_dia(_data(como_era_em))} Termine com três pontos a investigar na reunião. {FECHO}"
    )


def alvos(cnae: str, uf: str, anos_de_abertura: str = "") -> str:
    """O pedido dos alvos de um setor numa UF."""
    anos = _anos(
        anos_de_abertura,
        MAXIMO_DE_ANOS_DE_ABERTURA,
        f"Anos de abertura é um número de 1 a {MAXIMO_DE_ANOS_DE_ABERTURA}.",
    )
    idade = (
        f" abertas há mais de {anos} anos (calcule a data de corte a partir de hoje e use "
        "`aberta_antes_de`),"
        if anos
        else ""
    )
    return (
        f"Liste as empresas ativas do CNAE {_cnae(cnae)} na UF {_uf(uf)},{idade} só as matrizes, com "
        "`buscar_empresas`. Mostre uma tabela com razão social, CNPJ, município, porte e data de "
        "abertura, e diga quantas vieram e se há mais páginas (`next_cursor`). Para as cinco que "
        f"parecerem mais relevantes, diga por quê, só com o que a tabela traz. {FECHO}"
    )


def compradores(cnae: str, uf: str = "", anos: str = "") -> str:
    """O pedido de quem já se mexeu num setor."""
    limpa_uf = _uf(uf) if uf.strip() else ""
    janela = _anos(
        anos,
        ANOS_MAXIMO_DOS_COMPRADORES,
        f"Anos é um número de 1 a {ANOS_MAXIMO_DOS_COMPRADORES}.",
    )
    setor = _cnae(
        cnae, _CNAE_DE_CLASSE, "CNAE é a classe (5 dígitos) ou a subclasse (7 dígitos)."
    )
    onde = f" na UF {limpa_uf}" if limpa_uf else ""
    quando = f" nos últimos {janela} anos (`anos`)" if janela else ""
    return (
        f"Quem já se mexeu no setor do CNAE {setor}{onde}{quando}? Use `compradores_do_setor` e "
        "mostre cada comprador com os sinais e os exemplos. Leia os `limits` e diga que é movimento "
        "passado, não intenção de compra. Para os três primeiros, sugira o que conferir antes de "
        f"procurá-los. {FECHO}"
    )


def comparaveis(cnpj: str, como_era_em: str = "") -> str:
    """O pedido dos comparáveis de uma companhia aberta."""
    return (
        f"Monte os comparáveis da empresa de CNPJ {cnpj_do_pedido(cnpj)} com `comparaveis`: a tabela "
        "dos pares com receita, EBITDA, lucro, dívida líquida e as razões, a mediana e onde a empresa "
        "fica em relação a ela. Se a empresa não for companhia aberta, diga que não há comparáveis "
        f"pela CVM para ela, sem estimar.{_no_dia(_data(como_era_em))} {FECHO}"
    )


def dossie(cnpj: str, orientacao: str, como_era_em: str = "") -> str:
    """O pedido do dossiê de uma empresa, com a orientação das instruções do conector."""
    return (
        f"Monte o dossiê da empresa de CNPJ {cnpj_do_pedido(cnpj)}.{_no_dia(_data(como_era_em))} "
        f"{orientacao} {FECHO}"
    )


def registrar_prompts(servidor: MCPServer, orientacao_do_dossie: str) -> None:
    """Põe os prompts no servidor. A orientação do dossiê vem das instruções (um lugar só para ela)."""

    def _triagem(cnpj: ArgumentoCnpj, como_era_em: ArgumentoData = "") -> str:
        return montar(lambda: triagem(cnpj, como_era_em))

    def _alvos(
        cnae: ArgumentoCnae,
        uf: Annotated[str, Field(description="UF, duas letras (ex.: SP).")],
        anos_de_abertura: Annotated[
            str, Field(description="Opcional: só as abertas há mais destes anos.")
        ] = "",
    ) -> str:
        return montar(lambda: alvos(cnae, uf, anos_de_abertura))

    def _compradores(
        cnae: ArgumentoCnaeDeClasse,
        uf: Annotated[str, Field(description="Opcional: UF, duas letras.")] = "",
        anos: Annotated[
            str, Field(description="Opcional: olhar só os últimos N anos (1 a 10).")
        ] = "",
    ) -> str:
        return montar(lambda: compradores(cnae, uf, anos))

    def _comparaveis(cnpj: ArgumentoCnpj, como_era_em: ArgumentoData = "") -> str:
        return montar(lambda: comparaveis(cnpj, como_era_em))

    def _dossie(cnpj: ArgumentoCnpj, como_era_em: ArgumentoData = "") -> str:
        return montar(lambda: dossie(cnpj, orientacao_do_dossie, como_era_em))

    # (função, nome, título, descrição): o título e a descrição são o que o analista vê no cliente
    fluxos = (
        (
            _triagem,
            "triagem_de_cnpj",
            "Triagem de um CNPJ",
            "Quem é a empresa, o que aconteceu com ela e de quem ela é parte, antes da reunião.",
        ),
        (
            _alvos,
            "alvos_no_setor",
            "Alvos de um setor numa UF",
            "Matrizes ativas de um CNAE numa UF, se quiser só as abertas há mais de N anos.",
        ),
        (
            _compradores,
            "compradores_no_setor",
            "Quem já se mexeu no setor",
            "Empresas, FIPs e companhias abertas que entraram num setor: movimento passado.",
        ),
        (
            _comparaveis,
            "comparaveis_da_empresa",
            "Comparáveis de uma companhia aberta",
            "Os pares na CVM, com a mediana e onde a empresa fica.",
        ),
        (
            _dossie,
            "dossie_da_empresa",
            "Dossiê de uma empresa",
            "Ficha, eventos, vínculos e comparáveis numa ficha só, com as lacunas à parte.",
        ),
    )
    for funcao, nome, titulo, descricao in fluxos:
        servidor.prompt(name=nome, title=titulo, description=descricao)(funcao)
