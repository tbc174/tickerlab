"""O pedido à API externa e a tradução de cada recusa numa mensagem clara e num código de saída.

A chave vai só no cabeçalho `Authorization: Bearer` (a API recusa a chave pela URL) e nunca entra numa
mensagem: as mensagens dizem o que fazer, não repetem o pedido. Os códigos de saída são distintos por tipo
de problema, para o agente decidir sem ler o texto (`Saida`).

O limite do minuto (HTTP 429 que não é a quota do mês) não derruba o comando de primeira: a CLI espera o
`Retry-After` uma vez e repete o pedido, para quem não programa não ter de rodar de novo à mão. Espera
acima de `ESPERA_MAXIMA`, ou ilegível, vira o erro de sempre: o terminal nunca fica preso.
"""

import time
from collections.abc import Callable, Mapping, Sequence
from enum import IntEnum
from typing import IO

import click
import httpx

from tickerlab import __version__

PREFIXO = "/data/v1"
ESPERA_MAXIMA = (
    60  # segundos: o limite é por minuto; mais que isso não é o limite do minuto
)
CODIGO_DA_QUOTA_DO_MES = "monthly_quota_exceeded"
esperar: Callable[[float], None] = time.sleep  # os testes trocam, para não dormir
PAGINAS_MAXIMAS = 100  # `prospectar --todas`: até 100 pedidos de uma vez; o resto fica no próximo cursor
CAMINHO_DA_BUSCA = "/companies"

Parametros = Mapping[str, str | Sequence[str]]
TEMPO_MAXIMO = (
    30.0  # segundos: a maior resposta (100 linhas de demonstrações) sai bem antes disso
)


class Saida(IntEnum):
    """Os códigos de saída da CLI (os mesmos no `docs/cli.md` e nas instruções do agente)."""

    OK = 0
    ERRO = 1  # erro inesperado
    USO = 2  # comando, opção ou CNPJ mal escrito (o mesmo código do click)
    CHAVE = 3  # sem chave, ou a API recusou a chave
    LIMITE = 4  # limite do minuto ou quota do mês
    SEM_DADO = 5  # nada disponível para esta chave (CNPJ sem dado, data sem dado ou fora do contrato)
    PEDIDO_INVALIDO = (
        6  # a API recusou o pedido (CNPJ com dígito errado, data no futuro...)
    )
    FORA_DO_AR = 7  # sem resposta da API, ou a API fora do ar


class ErroDaCli(click.ClickException):
    """Um erro com mensagem em português e o código de saída do tipo do problema."""

    def __init__(self, mensagem: str, saida: Saida) -> None:
        super().__init__(mensagem)
        self.exit_code = int(saida)

    def show(self, file: IO[str] | None = None) -> None:
        click.echo(f"Erro: {self.format_message()}", err=True, file=file)


SEM_CHAVE = (
    "Nenhuma chave da API configurada. Rode `tickerlab login` (a chave não aparece enquanto você digita) "
    "ou defina TICKERLAB_API_KEY."
)
SEM_DADO = (
    "Não há dado disponível para este pedido com a sua chave: o CNPJ (ou o setor) pode não ter este dado "
    "na data pedida, ou o conjunto não está no contrato da sua organização. A API não diz qual dos dois, "
    "de propósito. Veja o que a sua chave pode pedir com `tickerlab catalogo`."
)
MENSAGENS: Mapping[tuple[int, str], tuple[str, Saida]] = {
    (401, "invalid_api_key"): (
        (
            "A API recusou a chave (inválida, revogada ou vencida). Confira TICKERLAB_API_KEY ou rode "
            "`tickerlab login` de novo."
        ),
        Saida.CHAVE,
    ),
    (429, CODIGO_DA_QUOTA_DO_MES): (
        "A quota de pedidos do mês acabou. Veja o consumo com `tickerlab consumo`; ela volta no dia 1º.",
        Saida.LIMITE,
    ),
    (404, "not_available"): (SEM_DADO, Saida.SEM_DADO),
    (400, "invalid_cnpj"): (
        "CNPJ inválido: confira os 14 caracteres e o dígito verificador.",
        Saida.PEDIDO_INVALIDO,
    ),
    (400, "invalid_known_at"): (
        "A data de --como-era não pode estar no futuro.",
        Saida.PEDIDO_INVALIDO,
    ),
    (400, "invalid_assumed_return"): (
        "O --retorno-suposto precisa ser uma fração ao ano entre -1 e 1 (0.12 quer dizer 12% ao ano).",
        Saida.PEDIDO_INVALIDO,
    ),
    (400, "invalid_filter"): (
        (
            "A API recusou um dos filtros (CNAE, UF, município, porte, natureza, situação ou data). "
            "Confira com `tickerlab prospectar --help`."
        ),
        Saida.PEDIDO_INVALIDO,
    ),
    (400, "filter_required"): (
        "A busca precisa de pelo menos um filtro (por exemplo --cnae 3511 --uf SP).",
        Saida.USO,
    ),
    (400, "invalid_event_type"): (
        "Tipo de evento desconhecido. Confira com `tickerlab eventos --help`.",
        Saida.PEDIDO_INVALIDO,
    ),
    (400, "invalid_cnae"): (
        "A API recusou o CNAE: use 5 ou 7 dígitos (3511501 é a subclasse; 35115 é a classe).",
        Saida.PEDIDO_INVALIDO,
    ),
    (400, "invalid_state"): (
        "A API recusou a UF: use 2 letras, como SP.",
        Saida.PEDIDO_INVALIDO,
    ),
    (400, "invalid_years"): (
        "Os anos vão de 1 a 10.",
        Saida.USO,
    ),
    (400, "invalid_limit"): (
        "O limite vai de 1 a 50 compradores.",
        Saida.USO,
    ),
    (400, "invalid_depth"): (
        "A profundidade vai de 1 a 3 saltos.",
        Saida.USO,
    ),
    (400, "invalid_link_type"): (
        "Tipo de vínculo desconhecido. Confira com `tickerlab vinculos --help`.",
        Saida.PEDIDO_INVALIDO,
    ),
    (400, "invalid_cursor"): (
        "A API não reconheceu a página pedida. Rode o comando de novo, do começo.",
        Saida.PEDIDO_INVALIDO,
    ),
    (400, "api_key_in_url"): (
        (
            "A API recusou o pedido porque viu uma chave no endereço. A CLI não faz isso: confira "
            "TICKERLAB_API_URL."
        ),
        Saida.PEDIDO_INVALIDO,
    ),
}


def abrir_http(endereco: str) -> httpx.Client:
    """O cliente HTTP da CLI (os testes trocam por um `TestClient` da API montada em memória)."""
    return httpx.Client(
        base_url=endereco,
        timeout=TEMPO_MAXIMO,
        headers={"User-Agent": f"tickerlab-cli/{__version__}"},
    )


AbrirHttp = Callable[[str], httpx.Client]


def _detalhe(resposta: httpx.Response) -> str:
    try:
        corpo = resposta.json()
    except ValueError:
        return ""
    detalhe = corpo.get("detail") if isinstance(corpo, dict) else None
    return detalhe if isinstance(detalhe, str) else ""


def erro_da_resposta(resposta: httpx.Response, endereco: str) -> ErroDaCli:
    """A recusa da API como mensagem em português e código de saída."""
    status, detalhe = resposta.status_code, _detalhe(resposta)
    conhecida = MENSAGENS.get((status, detalhe))
    if conhecida is not None:
        return ErroDaCli(*conhecida)
    if status == 429:
        espera = resposta.headers.get("Retry-After", "60")
        return ErroDaCli(
            f"Limite de pedidos por minuto atingido: tente de novo em {espera} segundos.",
            Saida.LIMITE,
        )
    if status == 404:
        return ErroDaCli(
            f"{endereco} não tem a API de dados do TickerLab ligada (rota não encontrada). "
            "Confira TICKERLAB_API_URL.",
            Saida.FORA_DO_AR,
        )
    if status in (400, 422):
        codigo = f" (código {detalhe})" if detalhe else ""
        return ErroDaCli(f"A API recusou o pedido{codigo}.", Saida.PEDIDO_INVALIDO)
    if status >= 500:
        return ErroDaCli(
            f"A API está fora do ar agora (HTTP {status}). Tente de novo em alguns minutos.",
            Saida.FORA_DO_AR,
        )
    return ErroDaCli(f"Resposta inesperada da API (HTTP {status}).", Saida.ERRO)


def _espera_do_minuto(resposta: httpx.Response) -> int | None:
    """Os segundos a esperar se a recusa é o limite do minuto e a espera é curta; None nos outros casos."""
    if resposta.status_code != httpx.codes.TOO_MANY_REQUESTS:
        return None
    if _detalhe(resposta) == CODIGO_DA_QUOTA_DO_MES:
        return None
    texto = resposta.headers.get("Retry-After", "")
    if not texto.isdigit() or int(texto) > ESPERA_MAXIMA:
        return None
    return int(texto)


class ApiDoTickerlab:
    """Os pedidos à API externa com uma chave; cada método devolve o corpo da resposta, já em JSON."""

    def __init__(self, http: httpx.Client, chave: str, endereco: str) -> None:
        self._http = http
        self._chave = chave
        self.endereco = endereco

    def pedir(self, caminho: str, parametros: Parametros | None = None) -> dict:
        """GET em `/data/v1<caminho>`; `ErroDaCli` se a API recusa, não responde ou responde sem JSON.

        No limite do minuto, espera o `Retry-After` (até `ESPERA_MAXIMA`) e tenta mais uma vez.
        """
        resposta = self._get(caminho, parametros)
        segundos = _espera_do_minuto(resposta)
        if segundos is not None:
            click.echo(
                f"Limite de pedidos por minuto: esperando {segundos} segundos e tentando de novo...",
                err=True,
            )
            esperar(segundos)
            resposta = self._get(caminho, parametros)
        return self._corpo(resposta)

    def _get(self, caminho: str, parametros: Parametros | None) -> httpx.Response:
        try:
            resposta = self._http.get(
                PREFIXO + caminho,
                params=dict(parametros or {}),
                headers={"Authorization": f"Bearer {self._chave}"},
            )
        except httpx.TransportError as erro:
            # sem o texto do erro: ele pode trazer o pedido inteiro
            raise ErroDaCli(
                f"Não consegui falar com a API em {self.endereco} ({type(erro).__name__}). "
                "Confira a internet e TICKERLAB_API_URL.",
                Saida.FORA_DO_AR,
            ) from None
        return resposta

    def _corpo(self, resposta: httpx.Response) -> dict:
        if resposta.status_code != httpx.codes.OK:
            raise erro_da_resposta(resposta, self.endereco)
        try:
            corpo = resposta.json()
        except ValueError:
            corpo = None
        if not isinstance(corpo, dict):
            raise ErroDaCli(
                f"{self.endereco} respondeu algo que não é a API do TickerLab. Confira TICKERLAB_API_URL.",
                Saida.FORA_DO_AR,
            )
        return corpo

    def catalogo(self) -> dict:
        return self.pedir("/catalog")

    def consumo(self) -> dict:
        return self.pedir("/usage")

    def empresa(self, cnpj: str, como_era: str | None) -> dict:
        return self.pedir(f"/companies/{cnpj}", _datas(known_at=como_era))

    def perfil(self, cnpj: str, como_era: str | None) -> dict:
        return self.pedir(f"/companies/{cnpj}/profile", _datas(known_at=como_era))

    def comparaveis(self, cnpj: str, como_era: str | None) -> dict:
        return self.pedir(f"/companies/{cnpj}/comparables", _datas(known_at=como_era))

    def compradores(
        self,
        cnae: str,
        uf: str | None,
        anos: int,
        limite: int,
        como_era: str | None,
    ) -> dict:
        parametros = {
            "cnae": cnae,
            "years": str(anos),
            "limit": str(limite),
            **_datas(state=uf, known_at=como_era),
        }
        return self.pedir("/buyers", parametros)

    def vinculos(
        self,
        cnpj: str,
        como_era: str | None,
        profundidade: int,
        tipos: Sequence[str],
    ) -> dict:
        parametros: dict[str, str | Sequence[str]] = {
            **_datas(known_at=como_era),
            "depth": str(profundidade),
        }
        if tipos:
            parametros["types"] = list(tipos)
        return self.pedir(f"/companies/{cnpj}/links", parametros)

    def demonstracoes(
        self, cnpj: str, como_era: str | None, periodo: str | None
    ) -> dict:
        return self.pedir(
            f"/companies/{cnpj}/financials",
            _datas(known_at=como_era, period_end=periodo),
        )

    def fundo(
        self, cnpj: str, como_era: str | None, retorno_suposto: float | None
    ) -> dict:
        parametros = _datas(known_at=como_era)
        if retorno_suposto is not None:
            parametros["assumed_return"] = repr(retorno_suposto)
        return self.pedir(f"/funds/{cnpj}", parametros)

    def buscar_empresas(self, filtros: Parametros, todas: bool = False) -> dict:
        """A busca de empresas por filtros; com `todas`, segue o cursor até o fim (ou `PAGINAS_MAXIMAS`).

        Cada página é um pedido da quota. As páginas viram uma resposta só: as empresas em sequência, as
        fontes sem repetir, e `truncated`/`next_cursor` da última página (cursor vazio = acabou).
        """
        return self._paginas(CAMINHO_DA_BUSCA, filtros, "companies", todas)

    def eventos(
        self, cnpj: str, como_era: str | None, tipos: Sequence[str], todas: bool
    ) -> dict:
        """Os eventos da empresa, do mais novo ao mais velho; com `todas`, segue o cursor como a busca."""
        parametros: dict[str, str | Sequence[str]] = {**_datas(known_at=como_era)}
        if tipos:
            parametros["types"] = list(tipos)
        return self._paginas(f"/companies/{cnpj}/events", parametros, "events", todas)

    def _paginas(
        self, caminho: str, parametros: Parametros, lista: str, todas: bool
    ) -> dict:
        """A primeira página e, com `todas`, as seguintes pelo `next_cursor`, juntas numa resposta só."""
        corpo = self.pedir(caminho, parametros)
        paginas = 1
        while todas and corpo.get("next_cursor") and paginas < PAGINAS_MAXIMAS:
            paginas += 1
            click.echo(
                f"{len(corpo.get(lista) or [])} linhas até agora; buscando a página {paginas}...",
                err=True,
            )
            seguinte = self.pedir(
                caminho, {**parametros, "cursor": str(corpo["next_cursor"])}
            )
            corpo = juntar_paginas(corpo, seguinte, lista)
        return corpo

    def setores(self) -> dict:
        return self.pedir("/sectors")

    def setor(self, chave: str, como_era: str | None) -> dict:
        return self.pedir(f"/sectors/{chave}", _datas(known_at=como_era))


def juntar_paginas(
    anterior: Mapping, seguinte: Mapping, lista: str = "companies"
) -> dict:
    """Duas páginas numa resposta só: as linhas de `lista` na ordem da API e as fontes sem repetir."""
    fontes = list(anterior.get("sources") or [])
    vistas = {_chave_da_fonte(fonte) for fonte in fontes}
    for fonte in seguinte.get("sources") or []:
        if _chave_da_fonte(fonte) not in vistas:
            fontes.append(fonte)
            vistas.add(_chave_da_fonte(fonte))
    return {
        **seguinte,
        lista: [*(anterior.get(lista) or []), *(seguinte.get(lista) or [])],
        "sources": fontes,
    }


def _chave_da_fonte(fonte: object) -> str:
    return str(fonte.get("source")) if isinstance(fonte, Mapping) else str(fonte)


def _datas(**datas: str | None) -> dict[str, str]:
    return {nome: valor for nome, valor in datas.items() if valor is not None}
