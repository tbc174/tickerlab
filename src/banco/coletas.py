"""Registro de coletas: uma linha por arquivo baixado das fontes oficiais (Radar, PR 1).

É o primeiro passo da base histórica (ADR 0024 do autor): saber de onde veio cada arquivo, quando,
o tamanho, o SHA-256 e sob qual licença. As coletas não mudam o que gravam; só passam a deixar
este registro. Um problema no registro nunca derruba a coleta (fica no log).
"""

import hashlib
import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

import requests
import sqlalchemy as sa

from src import acervo
from src.banco.conexao import obter_engine
from src.banco.modelo import coletas

log = logging.getLogger(__name__)

# a licença de cada família de fontes (licencas-por-fonte.md do autor); a fonte é "família-detalhe"
LICENCAS = {
    "cvm": "ODbL (dados abertos da CVM; citar a fonte)",
    "sec": "Acesso público (EDGAR, SEC)",
    "bcb": "ODbL (dados abertos do Banco Central; citar a fonte)",
    "ibge": "Domínio público (citar o IBGE)",
    "tesouro": "Sem restrição (Fiscal Data, Tesouro dos EUA)",
    "iex": "Termos do IEX HIST (com atribuição)",
    "yahoo": "Uso pessoal: só interno, nunca exportar",
    # base de cripto (ADRs 0041 e 0045 do autor)
    "cftc": "Obra do governo dos EUA (domínio público; citar a CFTC)",
    "rfb": "Dados abertos da Receita Federal (Decreto 8.777/2016; citar a Receita)",
    "wiki": "CC0 (acessos às páginas da Wikimedia)",
    "gdelt": "GDELT (uso livre com citação; só contagem e tom, sem texto)",
    "btc": "Blockchain pública lida por nó próprio (Bitcoin Core, MIT)",
    "kraken": "Sem termo de dados de mercado: uso sem autorização (ADR 0045); só interno",
    "mb": "Sem termo de dados de mercado: uso sem autorização (ADR 0045); só interno",
}
SEM_LICENCA_CONHECIDA = "Desconhecida: conferir antes de guardar"

# Pode entrar num produto de dados? (ADR 0055 do autor, exigência 11; não é parecer jurídico: antes
# de vender qualquer coisa, parecer e decisão nova)
VENDAVEL_ODBL = (
    "vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor "
    "está na curadoria, nas versões e na qualidade)"
)
VENDAVEL_COM_ATRIBUICAO = "vendável com atribuição à fonte"
A_CONFIRMAR = (
    "a confirmar (sem resposta escrita sobre revenda; não vender até conferir)"
)
SO_USO_INTERNO = "só uso interno (nunca vender nem exportar)"
REVENDA = {
    "cvm": VENDAVEL_ODBL,
    "bcb": VENDAVEL_ODBL,
    "ibge": VENDAVEL_COM_ATRIBUICAO,
    "tesouro": VENDAVEL_COM_ATRIBUICAO,
    "sec": A_CONFIRMAR,  # os arquivos são escritos pelas empresas
    "iex": A_CONFIRMAR,
    "cftc": A_CONFIRMAR,
    "rfb": A_CONFIRMAR,
    "wiki": A_CONFIRMAR,
    "gdelt": A_CONFIRMAR,
    "btc": A_CONFIRMAR,
    "yahoo": SO_USO_INTERNO,
    "kraken": SO_USO_INTERNO,
    "mb": SO_USO_INTERNO,
}
LIMITE_DO_DETALHE = 300
LIMITE_DA_URL = 1000
HTTP_NAO_ENCONTRADO = 404


def licenca_da_fonte(fonte: str) -> str:
    """A licença pela família da fonte ("cvm-ipe" → a da CVM)."""
    return LICENCAS.get(fonte.split("-", 1)[0], SEM_LICENCA_CONHECIDA)


def revenda_da_fonte(fonte: str) -> str:
    """Se o dado da fonte pode ser revendido ("cvm-ipe" → o da CVM); fonte desconhecida, nunca."""
    return REVENDA.get(fonte.split("-", 1)[0], SO_USO_INTERNO)


def registrar(
    conexao: sa.Connection,
    fonte: str,
    url: str,
    conteudo: bytes | None,
    situacao: str,
    detalhe: str | None = None,
    agora: datetime | None = None,
    caminho_do_original: str | None = None,
) -> None:
    """Grava uma linha do registro. `conteudo` None = nada foi baixado (404 ou falha)."""
    conexao.execute(
        sa.insert(coletas).values(
            id=uuid.uuid4(),
            fonte=fonte,
            url=url[:LIMITE_DA_URL],
            situacao=situacao,
            bytes=None if conteudo is None else len(conteudo),
            sha256=None if conteudo is None else hashlib.sha256(conteudo).hexdigest(),
            licenca=licenca_da_fonte(fonte),
            detalhe=None if detalhe is None else detalhe[:LIMITE_DO_DETALHE],
            caminho_do_original=caminho_do_original,
            baixado_em=agora or datetime.now(UTC),
        )
    )


def original_mais_recente(conexao: sa.Connection, url: str) -> bytes | None:
    """A cópia mais recente de `url` guardada no acervo (None se nenhuma coleta guardou).

    Serve para reler um arquivo sem baixar de novo (regras de qualidade, base "como era na data").
    """
    caminho = conexao.execute(
        sa.select(coletas.c.caminho_do_original)
        .where(
            coletas.c.url == url[:LIMITE_DA_URL],
            coletas.c.situacao == "ok",
            coletas.c.caminho_do_original.is_not(None),
        )
        .order_by(coletas.c.baixado_em.desc())
        .limit(1)
    ).scalar()
    return acervo.ler_original(caminho) if caminho else None


def ultimas(
    conexao: sa.Connection, fonte: str | None = None, quantas: int = 50
) -> list[sa.Row]:
    """As coletas mais recentes (de uma fonte, ou de todas), da mais nova para a mais velha."""
    consulta = sa.select(coletas).order_by(coletas.c.baixado_em.desc()).limit(quantas)
    if fonte is not None:
        consulta = consulta.where(coletas.c.fonte == fonte)
    return list(conexao.execute(consulta))


def _guardar_sem_atrapalhar(
    fonte: str, url: str, conteudo: bytes, agora: datetime
) -> str | None:
    try:
        return acervo.guardar_original(fonte, url, conteudo, agora)
    except OSError:
        # disco cheio ou sem permissão: a coleta segue; o registro fica sem o caminho
        log.exception("Falha ao guardar o original da coleta de %s", fonte)
        return None


def _registrar_sem_atrapalhar(
    fonte: str, url: str, conteudo: bytes | None, situacao: str, detalhe: str | None
) -> None:
    agora = datetime.now(UTC)
    caminho = None
    if conteudo is not None:
        caminho = _guardar_sem_atrapalhar(fonte, url, conteudo, agora)
    try:
        with obter_engine().begin() as conexao:
            registrar(conexao, fonte, url, conteudo, situacao, detalhe, agora, caminho)
    except Exception:
        # o registro é para auditoria; a coleta segue mesmo sem ele
        log.exception("Falha ao registrar a coleta de %s", fonte)


def com_registro[Conteudo: (bytes, bytes | None)](
    fonte: str, baixar: Callable[..., Conteudo]
) -> Callable[..., Conteudo]:
    """Embrulha a função `baixar(url, ...)` de uma coleta para registrar cada arquivo.

    Arquivo baixado → guardado no acervo e "ok" com tamanho e SHA-256; `None` (a fonte respondeu 404) →
    "nao_encontrado"; erro → "falhou" e o erro segue para a coleta, como antes.
    """

    def baixar_e_registrar(url: str, *args: object, **kwargs: object) -> Conteudo:
        try:
            conteudo = baixar(url, *args, **kwargs)
        except Exception as erro:
            _registrar_sem_atrapalhar(fonte, url, None, "falhou", type(erro).__name__)
            raise
        situacao = "nao_encontrado" if conteudo is None else "ok"
        _registrar_sem_atrapalhar(fonte, url, conteudo, situacao, None)
        return conteudo

    return baixar_e_registrar


def buscar_com_registro(
    fonte: str, buscar: Callable[..., requests.Response] = requests.get
) -> Callable[..., requests.Response]:
    """Como `com_registro`, para os leitores que recebem um `buscar` no lugar do `requests.get`
    (Banco Central, Tesouro dos EUA): registra o endereço completo (com a consulta) e a resposta."""

    def buscar_e_registrar(
        url: str, *args: object, **kwargs: object
    ) -> requests.Response:
        try:
            resposta = buscar(url, *args, **kwargs)
        except Exception as erro:
            _registrar_sem_atrapalhar(fonte, url, None, "falhou", type(erro).__name__)
            raise
        endereco = getattr(resposta, "url", None) or url
        if resposta.ok:
            _registrar_sem_atrapalhar(fonte, endereco, resposta.content, "ok", None)
        else:
            situacao = (
                "nao_encontrado"
                if resposta.status_code == HTTP_NAO_ENCONTRADO
                else "falhou"
            )
            detalhe = f"HTTP {resposta.status_code}"
            _registrar_sem_atrapalhar(fonte, endereco, None, situacao, detalhe)
        return resposta

    return buscar_e_registrar
