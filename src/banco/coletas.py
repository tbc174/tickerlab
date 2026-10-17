"""Registro de coletas: uma linha por arquivo baixado das fontes oficiais (Radar, PR 1).

É o primeiro passo da base histórica (ADR 0024 do autor): saber de onde veio cada arquivo, quando,
o tamanho, o SHA-256 e sob qual licença. As coletas não mudam o que gravam; só passam a deixar
este registro. Um problema no registro nunca derruba a coleta (fica no log).
"""

import hashlib
import logging
import uuid
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from enum import StrEnum
from typing import NamedTuple

import requests
import sqlalchemy as sa

from src import acervo
from src.banco.conexao import obter_engine
from src.banco.modelo import coletas
from src.versao_do_codigo import versao_do_codigo

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
    # arquivo das fontes que só mostram o "agora" (plano dos coletores em modo arquivo, 14/10/2026)
    "rfb-cnpj": "Dados abertos do CNPJ (Receita; rodapé CC BY-ND do site: perguntar a licença)",
    "cgu": "Dados abertos da CGU (Decreto 8.777/2016; citar a CGU)",
    "pgfn": "Dados abertos da PGFN (rodapé CC BY-ND do site: perguntar a licença)",
    "ibama": "Dados abertos do IBAMA ('Outra (Aberta)'; citar o IBAMA)",
    "mte": "Cadastro de empregadores do MTE (dado público; citar o MTE)",
    "gleif": "CC0 (GLEIF, Global LEI Index)",
    "termos": "Termos de uso de terceiros: só prova interna da versão lida",
    "catalogo": "Lista de conjuntos de portais de dados abertos (metadados)",
    # o SGS do BC repassa o IGP-M, mas a série é da FGV (termos do IBRE: comercial pede autorização)
    "bcb-sgs-189": "IGP-M da FGV IBRE (repassado pelo BC): uso comercial pede autorização da FGV",
    "ccee": "CC BY 4.0 (dados abertos da CCEE; citar a CCEE)",
    "antt": "CC BY (dados abertos da ANTT; citar a ANTT)",
    "tesouro-br": "ODbL (Tesouro Transparente, Tesouro Nacional; citar a fonte)",
    "tesouro-br-divida": "ODbL (Tesouro Transparente, Tesouro Nacional; citar a fonte)",
    "tesouro-br-direto": "ODbL (Tesouro Transparente, Tesouro Nacional; citar a fonte)",
    "tesouro-br-leiloes": "ODbL (Tesouro Transparente, Tesouro Nacional; citar a fonte)",
    # prévia do balanço (14/10/2026): licença declarada no conjunto no dados.gov.br (o rodapé CC
    # BY-ND dos sites é do conteúdo das páginas); confirmação por escrito pedida às agências
    "anp": "CC BY (dados abertos da ANP no dados.gov.br; citar a ANP)",
    "anac": "CC BY (dados abertos da ANAC no dados.gov.br; citar a ANAC)",
    "ans": "CC BY (dados abertos da ANS no dados.gov.br; citar a ANS)",
    "ons": "CC BY 4.0 (dados abertos do ONS; citar o ONS)",
    "anatel": "CC BY (dados abertos da Anatel no dados.gov.br; citar a Anatel)",
    "aneel": "ODbL (dados abertos da ANEEL; citar). SAMP sem CPF e nome do consumidor",
    # série 4, PR 5b: "SES - Base de dados completa" com CC BY no dados.gov.br (lido em 15/10/2026);
    # só os CSVs sem pessoas (nunca administradores, contatos ou acionistas)
    "susep": "CC BY (SES da SUSEP no dados.gov.br; citar a SUSEP). Só os CSVs sem pessoas",
    # licença aberta sem nome no dados.gov.br; confirmação pedida pelo Fala.BR em 14/10/2026
    "comexstat": "Aberta sem nome ('Other (Open)', dados.gov.br); a confirmar com o MDIC",
    # negócios do pregão (ADR 0073): só pesquisa até a B3 autorizar por escrito (ADR 0019)
    "b3": "Política de Consumo de Market Data B3 V1.1: só pesquisa (ADRs 0019 e 0073)",
    # middle market de M&A: robots.txt e termos lidos antes; parecer jurídico depois (ADR 0060)
    "assessoria": "Posts públicos de assessorias de M&A: só fatos, sem texto (ADR 0082)",
    # termos lidos em 16/10/2026 (archive.org/about/terms); só a data das cópias entra na base
    "wayback": "Internet Archive: 'for scholarship and research purposes only'; só datas",
}
SEM_LICENCA_CONHECIDA = "Desconhecida: conferir antes de guardar"

# Pode entrar num produto de dados, num modelo ou num rótulo? (ADR 0055, exigência 11; ADR 0008,
# Emenda 1: as quatro marcas, com a resposta por escrito no `licencas-por-fonte.md`). Não é parecer
# jurídico: antes de vender qualquer coisa, parecer e decisão nova.
VENDAVEL_ODBL = (
    "vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor "
    "está na curadoria, nas versões e na qualidade)"
)
VENDAVEL_COM_ATRIBUICAO = "vendável com atribuição à fonte"
SO_USO_INTERNO = "só uso interno (entra em modelo; nunca vender nem exportar o dado)"
A_CONFIRMAR = (
    "a confirmar (sem resposta escrita sobre uso comercial ou treino de ML: vale como não "
    "comercial até a resposta)"
)
NAO_COMERCIAL = (
    "não comercial (uso pessoal, só pesquisa ou conta de estudante: só gabarito e pesquisa no PC; "
    "nunca em modelo, rótulo ou exportação)"
)
REVENDA = {
    "cvm": VENDAVEL_ODBL,
    "bcb": VENDAVEL_ODBL,
    "ibge": VENDAVEL_COM_ATRIBUICAO,
    "tesouro": VENDAVEL_COM_ATRIBUICAO,
    # treino de ML permitido por escrito (licencas-por-fonte.md, 13/10/2026); revenda ainda sem resposta
    "sec": SO_USO_INTERNO,  # os arquivos são escritos pelas empresas
    "iex": SO_USO_INTERNO,  # com a atribuição "Data provided for free by IEX"
    "cftc": SO_USO_INTERNO,  # obra do governo dos EUA
    "wiki": SO_USO_INTERNO,  # CC0
    "btc": SO_USO_INTERNO,  # blockchain pública lida por nó próprio
    "rfb": A_CONFIRMAR,  # planilha de cripto da Receita: perguntar a licença
    "gdelt": A_CONFIRMAR,  # sem termo lido sobre treino de ML
    "yahoo": NAO_COMERCIAL,  # termos do Yahoo: uso pessoal
    # sem termo de dados: só a exceção da ADR 0045 (modelo "Clima de risco do Bitcoin"); fora dela,
    # não comercial (`EXCECOES_DE_MODELO`)
    "kraken": NAO_COMERCIAL,
    "mb": NAO_COMERCIAL,
    # o conjunto só tem o rodapé CC BY-ND do site: perguntar a licença (e há dado pessoal)
    "rfb-cnpj": A_CONFIRMAR,
    "pgfn": A_CONFIRMAR,
    # dado pessoal (autuados, empregadores pessoa física): só interno
    "cgu": SO_USO_INTERNO,
    "ibama": SO_USO_INTERNO,
    "mte": SO_USO_INTERNO,
    "gleif": VENDAVEL_COM_ATRIBUICAO,
    "termos": SO_USO_INTERNO,
    "catalogo": SO_USO_INTERNO,
    "bcb-sgs-189": NAO_COMERCIAL,  # IGP-M da FGV: uso comercial pede autorização da FGV
    "ccee": VENDAVEL_COM_ATRIBUICAO,
    "antt": VENDAVEL_COM_ATRIBUICAO,
    "tesouro-br": VENDAVEL_ODBL,
    "tesouro-br-divida": VENDAVEL_ODBL,
    "tesouro-br-direto": VENDAVEL_ODBL,
    "tesouro-br-leiloes": VENDAVEL_ODBL,
    "anp": VENDAVEL_COM_ATRIBUICAO,
    "anac": VENDAVEL_COM_ATRIBUICAO,
    "ans": VENDAVEL_COM_ATRIBUICAO,
    "ons": VENDAVEL_COM_ATRIBUICAO,
    "anatel": VENDAVEL_COM_ATRIBUICAO,
    "aneel": VENDAVEL_ODBL,
    "susep": VENDAVEL_COM_ATRIBUICAO,
    "comexstat": A_CONFIRMAR,
    "b3": NAO_COMERCIAL,  # só pesquisa até a B3 autorizar por escrito (ADRs 0019 e 0073)
    "assessoria": A_CONFIRMAR,  # vender, mostrar ou treinar só com o parecer (ADRs 0063 e 0082)
    "wayback": NAO_COMERCIAL,  # "for scholarship and research purposes only"
}


class Marca(StrEnum):
    """As quatro marcas da Emenda 1 da ADR 0008, da menos para a mais restrita."""

    VENDAVEL = "vendavel"
    USO_INTERNO = "uso_interno"
    A_CONFIRMAR = "a_confirmar"  # vale como não comercial até a resposta escrita
    NAO_COMERCIAL = "nao_comercial"


MARCA_DA_REVENDA = {
    VENDAVEL_ODBL: Marca.VENDAVEL,
    VENDAVEL_COM_ATRIBUICAO: Marca.VENDAVEL,
    SO_USO_INTERNO: Marca.USO_INTERNO,
    A_CONFIRMAR: Marca.A_CONFIRMAR,
    NAO_COMERCIAL: Marca.NAO_COMERCIAL,
}
USOS = ("treinar", "rotular", "exportar")
PODEM_ENTRAR = {Marca.VENDAVEL, Marca.USO_INTERNO}  # nos três usos
MODELO_CLIMA_DE_RISCO = "clima-de-risco-do-bitcoin"
# exceção da ADR 0045: preços das corretoras de cripto sem termo de dados, só neste modelo
EXCECOES_DE_MODELO = {"kraken": MODELO_CLIMA_DE_RISCO, "mb": MODELO_CLIMA_DE_RISCO}


class LicencaNaoPermiteError(Exception):
    """Treinar, rotular ou exportar com fonte "não comercial" ou "a confirmar" (ADR 0008, Emenda 1)."""


LIMITE_DO_DETALHE = 300
LIMITE_DA_URL = 1000
HTTP_NAO_ENCONTRADO = 404


def licenca_da_fonte(fonte: str) -> str:
    """A licença da fonte ("rfb-cnpj") ou da sua família ("cvm-ipe" → a da CVM)."""
    return LICENCAS.get(fonte) or LICENCAS.get(
        fonte.split("-", 1)[0], SEM_LICENCA_CONHECIDA
    )


def revenda_da_fonte(fonte: str) -> str:
    """Se o dado da fonte pode ser revendido ("cvm-ipe" → o da CVM); fonte desconhecida, a confirmar
    (fonte nova sem resposta escrita: ADR 0008, Emenda 1)."""
    return REVENDA.get(fonte) or REVENDA.get(fonte.split("-", 1)[0], A_CONFIRMAR)


def marca_da_fonte(fonte: str) -> Marca:
    """A marca da fonte ("yahoo-bvsp" → não comercial; "cvm-ipe" → vendável)."""
    return MARCA_DA_REVENDA[revenda_da_fonte(fonte)]


def marca_mais_restrita(marcas: Iterable[Marca]) -> Marca:
    """A marca de uma tabela feita de várias fontes; sem nenhuma fonte conhecida, a confirmar."""
    ordem = list(Marca)
    return max(marcas, key=ordem.index, default=Marca.A_CONFIRMAR)


def _pode(fonte: str, uso: str, modelo: str | None) -> bool:
    if marca_da_fonte(fonte) in PODEM_ENTRAR:
        return True
    excecao = EXCECOES_DE_MODELO.get(fonte.split("-", 1)[0])
    return uso != "exportar" and modelo is not None and modelo == excecao


def exigir_licenca(
    uso: str, fontes: Iterable[str], modelo: str | None = None, onde: str = ""
) -> None:
    """Erro (não aviso) se alguma fonte não pode `uso` ("treinar", "rotular" ou "exportar").

    Passam "vendável" e "só uso interno"; Kraken e Mercado Bitcoin, só para treinar ou rotular o
    modelo da exceção da ADR 0045. `onde` (a tabela, o script) entra na mensagem.
    """
    if uso not in USOS:
        raise ValueError(f"uso {uso!r} não existe; use um de {USOS}")
    barradas = sorted({f for f in fontes if not _pode(f, uso, modelo)})
    if barradas:
        lista = ", ".join(f"{f} ({marca_da_fonte(f)})" for f in barradas)
        alvo = f" ({onde})" if onde else ""
        raise LicencaNaoPermiteError(
            f"{uso}{alvo} com fonte sem licença para isso: {lista} "
            "(ADR 0008, Emenda 1: só 'vendável' e 'só uso interno')"
        )


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
    registrar_arquivo(
        conexao,
        fonte,
        url,
        None if conteudo is None else hashlib.sha256(conteudo).hexdigest(),
        None if conteudo is None else len(conteudo),
        situacao,
        detalhe,
        agora,
        caminho_do_original,
    )


def registrar_arquivo(
    conexao: sa.Connection,
    fonte: str,
    url: str,
    sha256: str | None,
    tamanho: int | None,
    situacao: str,
    detalhe: str | None = None,
    agora: datetime | None = None,
    caminho_do_original: str | None = None,
) -> None:
    """Como `registrar`, para arquivos grandes: o SHA-256 e o tamanho já vêm calculados (em partes)."""
    conexao.execute(
        sa.insert(coletas).values(
            id=uuid.uuid4(),
            fonte=fonte,
            url=url[:LIMITE_DA_URL],
            situacao=situacao,
            bytes=tamanho,
            sha256=sha256,
            licenca=licenca_da_fonte(fonte),
            detalhe=None if detalhe is None else detalhe[:LIMITE_DO_DETALHE],
            caminho_do_original=caminho_do_original,
            baixado_em=agora or datetime.now(UTC),
            versao_do_codigo=versao_do_codigo(),
        )
    )


def ultima_coleta_ok(conexao: sa.Connection, url: str) -> sa.Row | None:
    """A coleta "ok" mais recente de `url` (para saber se o arquivo mudou), ou None."""
    return conexao.execute(
        sa.select(coletas)
        .where(coletas.c.url == url[:LIMITE_DA_URL], coletas.c.situacao == "ok")
        .order_by(coletas.c.baixado_em.desc())
        .limit(1)
    ).first()


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


class Versao(NamedTuple):
    baixado_em: datetime  # a primeira vez que este conteúdo foi baixado
    sha256: str
    caminho: str  # no acervo (`acervo.ler_original`)


def versoes_guardadas(conexao: sa.Connection, url: str) -> list[Versao]:
    """Cada conteúdo diferente de `url` guardado no acervo, do mais antigo ao mais novo, sem ler os
    arquivos (o CDA tem ~25 MB por versão: quem usa lê um de cada vez)."""
    linhas = conexao.execute(
        sa.select(coletas.c.baixado_em, coletas.c.sha256, coletas.c.caminho_do_original)
        .where(
            coletas.c.url == url[:LIMITE_DA_URL],
            coletas.c.situacao == "ok",
            coletas.c.caminho_do_original.is_not(None),
        )
        .order_by(coletas.c.baixado_em)
    ).all()
    vistos: set[str] = set()
    versoes = []
    for baixado_em, sha256, caminho in linhas:
        if sha256 not in vistos:
            vistos.add(sha256)
            versoes.append(Versao(baixado_em, sha256, caminho))
    return versoes


def ausente_antes(conexao: sa.Connection, url: str, quando: datetime) -> bool:
    """Alguma coleta antes de `quando` achou `url` sem arquivo ("nao_encontrado", o 404 da fonte)?"""
    return (
        conexao.execute(
            sa.select(coletas.c.id)
            .where(
                coletas.c.url == url[:LIMITE_DA_URL],
                coletas.c.situacao == "nao_encontrado",
                coletas.c.baixado_em < quando,
            )
            .limit(1)
        ).first()
        is not None
    )


def coletas_guardadas(
    conexao: sa.Connection, url: str
) -> list[tuple[datetime, str, bytes]]:
    """Cada conteúdo diferente de `url` guardado no acervo (quando foi baixado pela primeira vez, o
    SHA-256 e o conteúdo), do mais antigo ao mais novo (revisões das fontes setoriais, série 4, PR 5)."""
    guardadas = []
    for baixado_em, sha256, caminho in versoes_guardadas(conexao, url):
        conteudo = acervo.ler_original(caminho)
        if conteudo is not None:
            guardadas.append((baixado_em, sha256, conteudo))
    return guardadas


def originais_guardados(conexao: sa.Connection, url: str) -> list[bytes]:
    """Cada conteúdo diferente de `url` guardado no acervo, do mais antigo ao mais novo.

    A fonte que regrava o arquivo no mesmo endereço (o FCA da CVM só publica a versão mais nova de cada
    formulário) deixa no acervo as baixadas anteriores, que continuam valendo como versões.
    """
    return [conteudo for _, _, conteudo in coletas_guardadas(conexao, url)]


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


def originais_mais_recentes(conexao: sa.Connection, fonte: str) -> list[sa.Row]:
    """A coleta mais recente de cada endereço da fonte que tem o original guardado."""
    linhas = conexao.execute(
        sa.select(
            coletas.c.url,
            coletas.c.sha256,
            coletas.c.caminho_do_original,
            coletas.c.baixado_em,
        )
        .where(
            coletas.c.fonte == fonte,
            coletas.c.situacao == "ok",
            coletas.c.caminho_do_original.is_not(None),
        )
        .order_by(coletas.c.url, coletas.c.baixado_em)
    ).all()
    mais_recente: dict[str, sa.Row] = {}
    for linha in linhas:
        mais_recente[linha.url] = linha  # a ordem por data deixa a última
    return list(mais_recente.values())
