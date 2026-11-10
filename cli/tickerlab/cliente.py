"""O pedido à API externa e a tradução de cada recusa numa mensagem clara e num código de saída.

A chave vai só no cabeçalho `Authorization: Bearer` (a API recusa a chave pela URL) e nunca entra numa
mensagem: as mensagens dizem o que fazer, não repetem o pedido. Os códigos de saída são distintos por tipo
de problema, para o agente decidir sem ler o texto (`Saida`).
"""

from collections.abc import Callable, Mapping
from enum import IntEnum
from typing import IO

import click
import httpx

from tickerlab import __version__

PREFIXO = "/data/v1"
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
    (429, "monthly_quota_exceeded"): (
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


class ApiDoTickerlab:
    """Os pedidos à API externa com uma chave; cada método devolve o corpo da resposta, já em JSON."""

    def __init__(self, http: httpx.Client, chave: str, endereco: str) -> None:
        self._http = http
        self._chave = chave
        self.endereco = endereco

    def pedir(self, caminho: str, parametros: Mapping[str, str] | None = None) -> dict:
        """GET em `/data/v1<caminho>`; `ErroDaCli` se a API recusa, não responde ou responde sem JSON."""
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

    def setores(self) -> dict:
        return self.pedir("/sectors")

    def setor(self, chave: str, como_era: str | None) -> dict:
        return self.pedir(f"/sectors/{chave}", _datas(known_at=como_era))


def _datas(**datas: str | None) -> dict[str, str]:
    return {nome: valor for nome, valor in datas.items() if valor is not None}
