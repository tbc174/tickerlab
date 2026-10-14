"""As rotas públicas do link compartilhado (onda 4 da ADR 0046): abrem sem login, só com o código.

A página `app.tickerlab.com.br/novo/c#<código>` lê o código depois do `#` (que não sai do navegador) e o
manda aqui **no corpo de um POST**, nunca no endereço: assim ele não fica em log nem em `Referer`.

- Toda falha (código inválido, inexistente, vencido, revogado, PDF apagado) dá o **mesmo 404**.
- A resposta é uma lista fechada de campos: nada sobre quem compartilhou.
- Limite de pedidos por IP (o da Cloudflare, `CF-Connecting-IP`), corpo pequeno e cabeçalhos que
  pedem para não guardar, não indexar e não mandar o endereço adiante.

Fora do `rotas.py` de propósito: as rotas de lá exigem conta e contrato de página; estas não.
"""

from datetime import date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from src.api_v1.acesso import LimiteDePedidos, agora, exigir_api_ligada
from src.banco import compartilhamentos as links
from src.banco.conexao import obter_engine
from src.ficha import AVISO

PEDIDOS_POR_MINUTO_POR_IP = 30
TAMANHO_MAXIMO_DO_CORPO = 1024  # bytes: o corpo é só {"codigo": "..."}
NAO_VALE = "Este link não existe ou não vale mais."
CABECALHOS_DE_PRIVACIDADE = {
    "Cache-Control": "no-store",
    "X-Robots-Tag": "noindex, nofollow",
    "Referrer-Policy": "no-referrer",
}

LIMITE_POR_IP = LimiteDePedidos(PEDIDOS_POR_MINUTO_POR_IP)


def _recusa(status: int, detalhe: str) -> HTTPException:
    return HTTPException(
        status_code=status, detail=detalhe, headers=CABECALHOS_DE_PRIVACIDADE
    )


def ip_de_quem_pede(request: Request) -> str:
    """O IP que a Cloudflare viu; sem ele (testes, rede local), o da conexão."""
    cloudflare = request.headers.get("cf-connecting-ip", "").strip()
    return cloudflare or (request.client.host if request.client else "desconhecido")


def conferir_o_pedido(request: Request) -> None:
    """Antes de ler o corpo: tamanho anunciado e limite por IP."""
    anunciado = request.headers.get("content-length", "")
    if anunciado.isdigit() and int(anunciado) > TAMANHO_MAXIMO_DO_CORPO:
        raise _recusa(413, "Corpo grande demais.")
    if not LIMITE_POR_IP.permitir(f"ip:{ip_de_quem_pede(request)}", agora()):
        raise _recusa(429, "Muitos pedidos: espere um minuto.")


router = APIRouter(
    prefix="/v1/compartilhados",
    dependencies=[Depends(exigir_api_ligada), Depends(conferir_o_pedido)],
)


class PedidoDoLinkV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    codigo: Annotated[str, Field(max_length=64)]


class ChecagemV1(BaseModel):
    pergunta: str
    situacao: str
    explicacao: str


class FichaCompartilhadaV1(BaseModel):
    ticker: str
    estrategia: str
    parametros: dict[str, int | float | str | bool]
    protecoes: dict[str, int | float]
    custo_por_operacao: float
    inicio: date
    fim: date
    checagens: list[ChecagemV1]
    tentativas: int
    resultado: str  # "passou", "não passou" ou "inconclusivo"
    titulo_do_veredito: str
    texto_do_veredito: str
    texto_das_tentativas: str
    fonte: str
    calculada_em: datetime


class PdfCompartilhadoV1(BaseModel):
    nome_do_arquivo: str
    tamanho: int  # bytes
    sha256: str
    gerado_em: datetime


class LinkCompartilhadoV1(BaseModel):
    """O que a página pública mostra. Nada sobre quem compartilhou."""

    tipo: Literal["ficha", "pdf"]
    titulo: str
    criado_em: datetime
    expira_em: datetime
    ficha: FichaCompartilhadaV1 | None
    pdf: PdfCompartilhadoV1 | None
    aviso: str


def _ficha_v1(aberto: links.LinkAberto) -> FichaCompartilhadaV1 | None:
    f = aberto.ficha
    if f is None:
        return None
    return FichaCompartilhadaV1(
        ticker=f.ticker,
        estrategia=f.estrategia,
        parametros=f.parametros,
        protecoes=f.protecoes,
        custo_por_operacao=f.custo_por_operacao,
        inicio=f.inicio,
        fim=f.fim,
        checagens=[
            ChecagemV1(
                pergunta=c.pergunta, situacao=c.situacao.value, explicacao=c.explicacao
            )
            for c in f.checagens
        ],
        tentativas=f.tentativas,
        resultado=f.veredito.resultado.value,
        titulo_do_veredito=f.veredito.titulo,
        texto_do_veredito=f.veredito.texto,
        texto_das_tentativas=f.texto_das_tentativas,
        fonte=f.fonte,
        calculada_em=f.calculada_em,
    )


def _pdf_v1(aberto: links.LinkAberto) -> PdfCompartilhadoV1 | None:
    p = aberto.pdf
    if p is None:
        return None
    return PdfCompartilhadoV1(
        nome_do_arquivo=p.nome_do_arquivo,
        tamanho=p.tamanho,
        sha256=p.sha256,
        gerado_em=p.gerado_em,
    )


@router.post("/abrir")
def abrir(pedido: PedidoDoLinkV1, response: Response) -> LinkCompartilhadoV1:
    """A ficha congelada ou os dados do PDF de um link valendo (e conta a visita)."""
    with obter_engine().begin() as conexao:
        aberto = links.abrir_link(conexao, pedido.codigo)
    if aberto is None:
        raise _recusa(404, NAO_VALE)
    response.headers.update(CABECALHOS_DE_PRIVACIDADE)
    return LinkCompartilhadoV1(
        tipo="ficha" if aberto.tipo == "ficha" else "pdf",
        titulo=aberto.titulo,
        criado_em=aberto.criado_em,
        expira_em=aberto.expira_em,
        ficha=_ficha_v1(aberto),
        pdf=_pdf_v1(aberto),
        aviso=AVISO,
    )


@router.post("/pdf", response_class=Response)
def baixar_pdf(pedido: PedidoDoLinkV1) -> Response:
    """O PDF original de um link de PDF valendo, como arquivo para salvar."""
    with obter_engine().connect() as conexao:
        encontrado = links.pdf_do_link(conexao, pedido.codigo)
    if encontrado is None:
        raise _recusa(404, NAO_VALE)
    nome, conteudo = encontrado  # o nome só tem letras sem acento, números e "-"
    return Response(
        content=conteudo,
        media_type="application/pdf",
        headers={
            **CABECALHOS_DE_PRIVACIDADE,
            "Content-Disposition": f'attachment; filename="{nome}"',
            "X-Content-Type-Options": "nosniff",
        },
    )
