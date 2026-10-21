"""Os documentos da sala de dados de ponta a ponta: receber, ler, baixar e apagar (B-20, PR 2).

Junta as peças, sempre na mesma ordem: a conta e a operação conferidas no banco
(`src/banco/sala.py`), o tipo conferido pelo conteúdo (`arquivos.py`), a cifra (`cofre.py`), o
disco (`guarda.py`), a leitura em processo separado (`leitura.py`) e o CPF mascarado no texto
(`mascara.py`). As rotas da API (PR 3) só chamam estas funções.

Nome do arquivo e texto do documento nunca vão para log nem para a auditoria: só ids, tipo,
tamanho e o código do motivo de uma recusa (D8 e D15).
"""

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path

import sqlalchemy as sa

from src import auditoria
from src.banco import sala
from src.sala import arquivos, cofre, guarda, leitura, mascara

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Recebimento:
    """O resultado de um envio: o documento guardado, ou o código do motivo da recusa."""

    documento: sala.Documento | None
    recusa: str | None = None


@dataclass(frozen=True)
class Aberto:
    """Um documento decifrado, para baixar ou ler."""

    documento: sala.Documento
    conteudo: bytes


def _chave_da_operacao(
    conexao: sa.Connection, usuario_id: uuid.UUID, operacao_id: uuid.UUID
) -> bytes:
    """A chave da operação; na primeira vez, cria e grava (embrulhada pela chave-mestra)."""
    da_sala = {"usuario_id": usuario_id, "operacao_id": operacao_id}
    guardada = sala.chave_da_operacao(conexao, **da_sala)
    if guardada is None:
        chave, embrulhada, versao = cofre.nova_chave_da_operacao(operacao_id)
        if sala.guardar_chave_da_operacao(
            conexao, **da_sala, chave_cifrada=embrulhada, versao_da_chave=versao
        ):
            return chave
        guardada = sala.chave_da_operacao(
            conexao, **da_sala
        )  # outro envio gravou antes
        if guardada is None:
            raise RuntimeError("A operação sumiu no meio do envio.")
    embrulhada, versao = guardada
    return cofre.abrir_chave_da_operacao(embrulhada, versao, operacao_id)


def _recusar(
    conexao: sa.Connection,
    usuario_id: uuid.UUID,
    operacao_id: uuid.UUID,
    motivo: str,
    tamanho_bytes: int,
) -> Recebimento:
    auditoria.registrar(
        conexao,
        usuario_id,
        auditoria.ACAO_DOCUMENTO_RECUSADO,
        operacao_id,
        {"motivo": motivo, "tamanho_bytes": tamanho_bytes},
    )
    log.info("documento recusado na sala %s: %s", operacao_id, motivo)
    return Recebimento(None, motivo)


def receber_documento(
    conexao: sa.Connection,
    *,
    usuario_id: uuid.UUID,
    operacao_id: uuid.UUID,
    nome_original: str,
    conteudo: bytes,
    raiz: Path | None = None,
) -> Recebimento | None:
    """Confere, cifra e guarda o arquivo na sala; `None` se a sala não é da conta.

    Arquivo recusado volta com o código do motivo (e fica na auditoria). Levanta
    `sala.DocumentoRepetidoError` se o mesmo arquivo já está na sala, `guarda.SalaSemEspacoError`
    com o disco quase cheio e `cofre.ChaveDaSalaAusenteError` sem a chave-mestra no servidor.
    A leitura do texto vem depois, em `ler_documento` (a rota a dispara em segundo plano).
    """
    if (
        sala.buscar_operacao(conexao, usuario_id=usuario_id, operacao_id=operacao_id)
        is None
    ):
        return None
    raiz = raiz or guarda.pasta_da_sala()
    guarda.conferir_espaco_livre(raiz)
    try:
        tipo = arquivos.conferir(conteudo, nome_original)
    except arquivos.ArquivoRecusado as recusa:
        return _recusar(conexao, usuario_id, operacao_id, recusa.motivo, len(conteudo))
    chave = _chave_da_operacao(conexao, usuario_id, operacao_id)
    documento = sala.registrar_documento(
        conexao,
        usuario_id=usuario_id,
        operacao_id=operacao_id,
        nome_original=nome_original,
        tipo=tipo,
        tamanho_bytes=len(conteudo),
        sha256=hashlib.sha256(conteudo).hexdigest(),
    )
    assert documento is not None  # a operação foi conferida acima, na mesma transação
    cifrado = cofre.cifrar_documento(
        chave,
        conteudo,
        operacao_id=operacao_id,
        documento_id=documento.id,
        parte="original",
    )
    guarda.gravar(
        guarda.caminho_do_documento(raiz, operacao_id, documento.id, "original"),
        cifrado,
    )
    sala.guardar_nonce(
        conexao,
        usuario_id=usuario_id,
        operacao_id=operacao_id,
        documento_id=documento.id,
        nonce=cofre.nonce_de(cifrado),
    )
    return Recebimento(documento)


def abrir_documento(
    conexao: sa.Connection,
    *,
    usuario_id: uuid.UUID,
    operacao_id: uuid.UUID,
    documento_id: uuid.UUID,
    raiz: Path | None = None,
) -> Aberto | None:
    """O documento decifrado; `None` se não é da conta. Não registra nada (quem baixa registra).

    Levanta `cofre.CifraInvalidaError` se o arquivo do disco não é o que o banco espera (trocado
    de sala, de documento ou adulterado) e `FileNotFoundError` se ele sumiu do disco.
    """
    ids = {
        "usuario_id": usuario_id,
        "operacao_id": operacao_id,
        "documento_id": documento_id,
    }
    documento = sala.buscar_documento(conexao, **ids)
    if documento is None:
        return None
    raiz = raiz or guarda.pasta_da_sala()
    cifrado = guarda.ler(
        guarda.caminho_do_documento(raiz, operacao_id, documento_id, "original")
    )
    if cofre.nonce_de(cifrado) != sala.nonce_do_documento(conexao, **ids):
        raise cofre.CifraInvalidaError("O arquivo do disco não é o deste documento.")
    chave = _chave_da_operacao(conexao, usuario_id, operacao_id)
    conteudo = cofre.decifrar_documento(
        chave,
        cifrado,
        operacao_id=operacao_id,
        documento_id=documento_id,
        parte="original",
    )
    return Aberto(documento, conteudo)


def baixar_documento(
    conexao: sa.Connection,
    *,
    usuario_id: uuid.UUID,
    operacao_id: uuid.UUID,
    documento_id: uuid.UUID,
    raiz: Path | None = None,
) -> Aberto | None:
    """O documento decifrado para a pessoa baixar (fica na auditoria); `None` se não é da conta.

    A rota devolve sempre como anexo (`application/octet-stream`, `nosniff`, `sandbox`), nunca
    aberto dentro da página (D9).
    """
    aberto = abrir_documento(
        conexao,
        usuario_id=usuario_id,
        operacao_id=operacao_id,
        documento_id=documento_id,
        raiz=raiz,
    )
    if aberto is not None:
        auditoria.registrar(
            conexao,
            usuario_id,
            auditoria.ACAO_DOCUMENTO_BAIXADO,
            documento_id,
            {"operacao_id": str(operacao_id)},
        )
    return aberto


def _guardar_texto(
    conexao: sa.Connection,
    documento: sala.Documento,
    resultado: leitura.Leitura,
    usuario_id: uuid.UUID,
    raiz: Path,
) -> None:
    if resultado.situacao == "lido":
        # o CPF é mascarado aqui, do lado da API, mesmo que o filho tenha devolvido outra coisa
        paginas = [mascara.mascarar_cpfs(pagina) for pagina in resultado.paginas]
        chave = _chave_da_operacao(conexao, usuario_id, documento.operacao_id)
        cifrado = cofre.cifrar_documento(
            chave,
            json.dumps(paginas, ensure_ascii=False).encode("utf-8"),
            operacao_id=documento.operacao_id,
            documento_id=documento.id,
            parte="texto",
        )
        guarda.gravar(
            guarda.caminho_do_documento(
                raiz, documento.operacao_id, documento.id, "texto"
            ),
            cifrado,
        )
    sala.marcar_leitura(
        conexao,
        usuario_id=usuario_id,
        operacao_id=documento.operacao_id,
        documento_id=documento.id,
        situacao=resultado.situacao,
        paginas=len(resultado.paginas) if resultado.paginas else None,
        lido_por=leitura.VERSAO_DO_LEITOR,
    )


def ler_documento(
    motor: sa.Engine,
    *,
    usuario_id: uuid.UUID,
    operacao_id: uuid.UUID,
    documento_id: uuid.UUID,
    raiz: Path | None = None,
) -> str | None:
    """Lê o texto do documento em processo separado e guarda (cifrado e com CPF mascarado).

    Devolve a situação final (`lido`, `sem_texto` ou `erro_na_leitura`), ou `None` se o
    documento não é da conta (ou foi apagado antes da leitura). Recebe o motor, não uma conexão:
    a leitura pode levar até um minuto, e nenhuma transação fica aberta enquanto ela roda.
    """
    raiz = raiz or guarda.pasta_da_sala()
    ids = {
        "usuario_id": usuario_id,
        "operacao_id": operacao_id,
        "documento_id": documento_id,
    }
    try:
        with motor.begin() as conexao:
            aberto = abrir_documento(conexao, **ids, raiz=raiz)
    except (cofre.CifraInvalidaError, FileNotFoundError):
        resultado = leitura.ERRO
        log.warning(
            "documento %s da sala %s não abriu para ler", documento_id, operacao_id
        )
    else:
        if aberto is None:
            return None
        resultado = leitura.ler_em_subprocesso(aberto.conteudo, aberto.documento.tipo)
    with motor.begin() as conexao:
        documento = sala.buscar_documento(conexao, **ids)
        if documento is None:  # apagado enquanto lia
            return None
        _guardar_texto(conexao, documento, resultado, usuario_id, raiz)
    log.info(
        "leitura do documento %s: %s (%s)",
        documento_id,
        resultado.situacao,
        resultado.motivo,
    )
    return resultado.situacao


def texto_do_documento(
    conexao: sa.Connection,
    *,
    usuario_id: uuid.UUID,
    operacao_id: uuid.UUID,
    documento_id: uuid.UUID,
    raiz: Path | None = None,
) -> list[str] | None:
    """O texto lido do documento, por página (CPF já mascarado); `None` se não há ou não é da conta."""
    ids = {
        "usuario_id": usuario_id,
        "operacao_id": operacao_id,
        "documento_id": documento_id,
    }
    documento = sala.buscar_documento(conexao, **ids)
    if documento is None or documento.situacao != "lido":
        return None
    raiz = raiz or guarda.pasta_da_sala()
    try:
        cifrado = guarda.ler(
            guarda.caminho_do_documento(raiz, operacao_id, documento_id, "texto")
        )
    except FileNotFoundError:
        return None
    chave = _chave_da_operacao(conexao, usuario_id, operacao_id)
    texto = cofre.decifrar_documento(
        chave,
        cifrado,
        operacao_id=operacao_id,
        documento_id=documento_id,
        parte="texto",
    )
    return json.loads(texto)


def apagar_documento(
    conexao: sa.Connection,
    *,
    usuario_id: uuid.UUID,
    operacao_id: uuid.UUID,
    documento_id: uuid.UUID,
    raiz: Path | None = None,
) -> bool:
    """Apaga o documento do banco e do disco, na hora (sem lixeira). Devolve se era da conta."""
    apagado = sala.apagar_documento(
        conexao,
        usuario_id=usuario_id,
        operacao_id=operacao_id,
        documento_id=documento_id,
    )
    if apagado:
        guarda.apagar_documento(
            raiz or guarda.pasta_da_sala(), operacao_id, documento_id
        )
    return apagado


def apagar_operacao(
    conexao: sa.Connection,
    *,
    usuario_id: uuid.UUID,
    operacao_id: uuid.UUID,
    raiz: Path | None = None,
) -> bool:
    """Apaga a operação (e a chave dela, que torna os arquivos ilegíveis) e a pasta do disco."""
    apagada = sala.apagar_operacao(
        conexao, usuario_id=usuario_id, operacao_id=operacao_id
    )
    if apagada:
        guarda.apagar_operacao(raiz or guarda.pasta_da_sala(), operacao_id)
    return apagada


def apagar_arquivos_da_conta(
    conexao: sa.Connection, *, usuario_id: uuid.UUID, raiz: Path | None = None
) -> None:
    """Apaga do disco as pastas de todas as operações da conta (antes de apagar a conta)."""
    raiz = raiz or guarda.pasta_da_sala()
    for operacao in sala.listar_operacoes(conexao, usuario_id=usuario_id):
        guarda.apagar_operacao(raiz, operacao.id)
