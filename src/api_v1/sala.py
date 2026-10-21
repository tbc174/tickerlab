"""As rotas da sala de dados por operação (B-20, PR 3): `/v1/operacoes` e os documentos delas.

**Só admins por enquanto** (D13 do plano): a conta que não é admin recebe 404, como se a sala
não existisse. Outra conta acertando o id de uma operação ou de um documento também recebe 404
(nunca 403: a resposta não confirma que o id existe, D11). Nem admin vê a sala de outra pessoa: não
há rota de admin aqui.

Fora do `rotas.py` de propósito, como o link compartilhado: o contrato por página (`src/paginas.py`)
não vale para a sala, que ainda não é página de plano nenhum. As rotas, o limite de envios e o
acesso só de admin ficam todos neste arquivo, com teste que percorre cada rota.

Quem faz o trabalho é `src/banco/sala.py` (o banco) e `src/sala/documentos.py` (cifra, disco e
leitura). Aqui só entram a conta, os limites do `src/planos.py` e o desenho das respostas. Nome do
arquivo e texto nunca vão para log (D8).
"""

import logging
import os
import re
import tempfile
import uuid
import zipfile
from collections.abc import Callable, Iterator
from datetime import date, datetime
from typing import Annotated, BinaryIO, Literal
from urllib.parse import quote

import sqlalchemy as sa
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Response,
    UploadFile,
)
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from src import auditoria
from src.api_v1.acesso import LimiteDePedidos, agora, conta_logada, exigir_api_ligada
from src.banco import sala
from src.banco.conexao import obter_engine
from src.banco.modelo import TIPOS_DE_OPERACAO
from src.banco.usuarios import Usuario
from src.planos import limites_do
from src.sala import arquivos, cofre, documentos, guarda, retencao

log = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", dependencies=[Depends(exigir_api_ligada)])

SEGUNDOS_EM_UMA_HORA = 3600
BLOCO_DO_DOWNLOAD = (
    1024 * 1024
)  # bytes lidos do ZIP por vez ao devolver "Baixar a sala"
SEM_SALA = "Esta operação não existe ou já foi apagada."
SEM_DOCUMENTO = "Este documento não existe ou já foi apagado."

# 30 envios por hora por conta (D6): conta também o arquivo recusado, para ninguém testar a
# conferência em massa. Fica na memória do processo, como os outros limites da API.
LIMITE_DE_ENVIOS = LimiteDePedidos(
    limites_do(None).envios_por_hora, janela=SEGUNDOS_EM_UMA_HORA
)

# o texto de cada código de recusa (lista fechada de `arquivos.MOTIVOS_DE_RECUSA`)
MENSAGENS_DE_RECUSA = {
    arquivos.VAZIO: "O arquivo está vazio.",
    arquivos.GRANDE_DEMAIS: "O arquivo passa de 25 MB.",
    arquivos.TIPO_NAO_ACEITO: "Só entram PDF, XLSX, DOCX e CSV.",
    arquivos.EXTENSAO_NAO_BATE: "O conteúdo do arquivo não é do tipo que o nome diz.",
    arquivos.COM_MACRO: "Arquivos com macro não entram.",
    arquivos.PDF_CIFRADO: "PDF protegido por senha não entra.",
    arquivos.PDF_ATIVO: "PDF com JavaScript, programa ou arquivo anexado não entra.",
    arquivos.PAGINAS_DEMAIS: "O arquivo passa de 300 páginas.",
    arquivos.ZIP_CAMINHO_ESTRANHO: "O arquivo tem um caminho interno estranho.",
    arquivos.ZIP_GRANDE_DEMAIS: "O arquivo, descomprimido, é grande demais.",
    arquivos.CSV_BINARIO: "O CSV tem bytes que não são de texto.",
    arquivos.ARQUIVO_DANIFICADO: "O arquivo está danificado.",
}
assert set(MENSAGENS_DE_RECUSA) == set(arquivos.MOTIVOS_DE_RECUSA)


def conta_da_sala(conta: Annotated[Usuario, Depends(conta_logada)]) -> Usuario:
    """A conta logada, se for admin; para as outras a sala não existe (404)."""
    if not conta.e_admin:
        raise HTTPException(status_code=404, detail="Not Found")
    return conta


Conta = Annotated[Usuario, Depends(conta_da_sala)]


class OperacaoV1(BaseModel):
    id: uuid.UUID
    tipo: str
    nome: str
    situacao: str  # "aberta" ou "encerrada"
    retencao_ate: date  # o dia em que a operação some sozinha
    criada_em: datetime


class DocumentoV1(BaseModel):
    """Um documento da sala (sem o conteúdo, o texto, o hash nem o caminho no disco)."""

    id: uuid.UUID
    nome: str
    tipo: str
    tamanho_bytes: int
    paginas: int | None
    situacao: str  # "na_fila", "lido", "sem_texto" ou "erro_na_leitura"
    recebido_em: datetime


class PedidoDeOperacaoV1(BaseModel):
    tipo: Literal["ma", "divida", "credito", "fidc"]
    nome: str = Field(max_length=500)
    prazo_em_dias: Literal[90, 180, 365] = retencao.PRAZO_PADRAO_EM_DIAS


class PedidoDeProrrogarV1(BaseModel):
    dias: int = Field(ge=1, le=retencao.PRORROGACAO_MAXIMA_EM_DIAS)


assert set(PedidoDeOperacaoV1.model_fields["tipo"].annotation.__args__) == set(  # type: ignore[union-attr]
    TIPOS_DE_OPERACAO
)


def _operacao_v1(operacao: sala.Operacao) -> OperacaoV1:
    return OperacaoV1(
        id=operacao.id,
        tipo=operacao.tipo,
        nome=operacao.nome,
        situacao=operacao.situacao,
        retencao_ate=operacao.retencao_ate,
        criada_em=operacao.criada_em,
    )


def _documento_v1(documento: sala.Documento) -> DocumentoV1:
    return DocumentoV1(
        id=documento.id,
        nome=documento.nome_original,
        tipo=documento.tipo,
        tamanho_bytes=documento.tamanho_bytes,
        paginas=documento.paginas,
        situacao=documento.situacao,
        recebido_em=documento.recebido_em,
    )


def _ou_404[T](achado: T | None, detalhe: str = SEM_SALA) -> T:
    if achado is None:
        raise HTTPException(status_code=404, detail=detalhe)
    return achado


# --- operações ----------------------------------------------------------------------------


@router.post("/operacoes", status_code=201)
def criar_operacao(conta: Conta, pedido: PedidoDeOperacaoV1) -> OperacaoV1:
    """Abre uma operação (a sala); some sozinha no prazo escolhido (90, 180 ou 365 dias)."""
    maximo = limites_do(conta.plano).operacoes_na_sala
    with obter_engine().begin() as conexao:
        if len(sala.listar_operacoes(conexao, usuario_id=conta.id)) >= maximo:
            raise HTTPException(
                status_code=409,
                detail=f"O limite é de {maximo} operações. Apague uma que já acabou.",
            )
        try:
            operacao = sala.criar_operacao(
                conexao,
                usuario_id=conta.id,
                tipo=pedido.tipo,
                nome=pedido.nome,
                prazo_em_dias=pedido.prazo_em_dias,
            )
        except ValueError as erro:
            raise HTTPException(status_code=422, detail=str(erro)) from erro
    return _operacao_v1(operacao)


@router.get("/operacoes")
def listar_operacoes(conta: Conta) -> list[OperacaoV1]:
    """As operações da conta, da mais antiga para a mais nova."""
    with obter_engine().connect() as conexao:
        return [
            _operacao_v1(o) for o in sala.listar_operacoes(conexao, usuario_id=conta.id)
        ]


@router.get("/operacoes/{operacao_id}")
def ver_operacao(conta: Conta, operacao_id: uuid.UUID) -> OperacaoV1:
    with obter_engine().connect() as conexao:
        operacao = sala.buscar_operacao(
            conexao, usuario_id=conta.id, operacao_id=operacao_id
        )
    return _operacao_v1(_ou_404(operacao))


@router.post("/operacoes/{operacao_id}/encerrar")
def encerrar_operacao(conta: Conta, operacao_id: uuid.UUID) -> OperacaoV1:
    """Encerra a operação e deixa 30 dias para baixar a sala antes de ela sumir."""
    with obter_engine().begin() as conexao:
        operacao = sala.encerrar_operacao(
            conexao, usuario_id=conta.id, operacao_id=operacao_id
        )
    return _operacao_v1(_ou_404(operacao))


@router.post("/operacoes/{operacao_id}/prorrogar")
def prorrogar_operacao(
    conta: Conta, operacao_id: uuid.UUID, pedido: PedidoDeProrrogarV1
) -> OperacaoV1:
    """Empurra o prazo em que a operação some (de 1 a 365 dias a partir de hoje)."""
    with obter_engine().begin() as conexao:
        operacao = sala.prorrogar_operacao(
            conexao, usuario_id=conta.id, operacao_id=operacao_id, dias=pedido.dias
        )
    return _operacao_v1(_ou_404(operacao))


@router.delete("/operacoes/{operacao_id}", status_code=204)
def apagar_operacao(conta: Conta, operacao_id: uuid.UUID) -> Response:
    """Apaga a operação, os documentos e a chave, na hora (sem lixeira)."""
    with obter_engine().begin() as conexao:
        apagada = documentos.apagar_operacao(
            conexao, usuario_id=conta.id, operacao_id=operacao_id
        )
    _ou_404(apagada or None)
    return Response(status_code=204)


# --- documentos ---------------------------------------------------------------------------


@router.get("/operacoes/{operacao_id}/documentos")
def listar_documentos(conta: Conta, operacao_id: uuid.UUID) -> list[DocumentoV1]:
    ids = {"usuario_id": conta.id, "operacao_id": operacao_id}
    with obter_engine().connect() as conexao:
        _ou_404(sala.buscar_operacao(conexao, **ids))
        return [_documento_v1(d) for d in sala.listar_documentos(conexao, **ids)]


def _conferir_cabe_na_sala(
    conexao: sa.Connection, conta: Usuario, operacao: sala.Operacao, tamanho: int
) -> None:
    """409 se a operação está encerrada ou o envio passaria dos limites da sala."""
    if operacao.situacao != "aberta":
        raise HTTPException(
            status_code=409, detail="A operação está encerrada: não recebe documentos."
        )
    limites = limites_do(conta.plano)
    ja_na_sala = sala.listar_documentos(
        conexao, usuario_id=conta.id, operacao_id=operacao.id
    )
    if len(ja_na_sala) >= limites.documentos_por_operacao:
        raise HTTPException(
            status_code=409,
            detail=f"O limite é de {limites.documentos_por_operacao} documentos por operação.",
        )
    if sum(d.tamanho_bytes for d in ja_na_sala) + tamanho > limites.bytes_por_operacao:
        megas = limites.bytes_por_operacao // arquivos.MEGABYTE
        raise HTTPException(
            status_code=409, detail=f"O limite é de {megas} MB por operação."
        )


@router.post(
    "/operacoes/{operacao_id}/documentos", status_code=201, response_model=DocumentoV1
)
def enviar_documento(
    conta: Conta,
    operacao_id: uuid.UUID,
    arquivo: Annotated[UploadFile, File()],
    segundo_plano: BackgroundTasks,
) -> Response | DocumentoV1:
    """Recebe um documento (multipart): confere pelo conteúdo, cifra, guarda e manda ler.

    A leitura do texto roda depois, em segundo plano e em processo separado: a resposta traz o
    documento "na_fila". Arquivo recusado volta 422 com o código do motivo (`motivo`).
    """
    if not LIMITE_DE_ENVIOS.permitir(str(conta.id), agora()):
        raise HTTPException(
            status_code=429, detail="Muitos envios: espere um pouco para enviar mais."
        )
    # um byte além do máximo basta para a conferência recusar, sem ler o resto para a memória
    conteudo = arquivo.file.read(arquivos.TAMANHO_MAXIMO_DO_ARQUIVO + 1)
    with obter_engine().begin() as conexao:
        operacao = _ou_404(
            sala.buscar_operacao(conexao, usuario_id=conta.id, operacao_id=operacao_id)
        )
        _conferir_cabe_na_sala(conexao, conta, operacao, len(conteudo))
        try:
            recebimento = documentos.receber_documento(
                conexao,
                usuario_id=conta.id,
                operacao_id=operacao_id,
                nome_original=arquivo.filename or "",
                conteudo=conteudo,
            )
        except sala.DocumentoRepetidoError as erro:
            raise HTTPException(status_code=409, detail=str(erro)) from erro
        except ValueError as erro:  # nome do arquivo vazio ou comprido demais
            raise HTTPException(status_code=422, detail=str(erro)) from erro
        except (guarda.SalaSemEspacoError, cofre.ChaveDaSalaAusenteError) as erro:
            log.error("a sala não recebeu um documento: %s", type(erro).__name__)
            raise HTTPException(
                status_code=503, detail="A sala não pode receber arquivos agora."
            ) from erro
    recebimento = _ou_404(recebimento)
    if recebimento.documento is None:
        motivo = recebimento.recusa or arquivos.ARQUIVO_DANIFICADO
        return JSONResponse(
            status_code=422,
            content={"detail": MENSAGENS_DE_RECUSA[motivo], "motivo": motivo},
        )
    segundo_plano.add_task(
        documentos.ler_documento,
        obter_engine(),
        usuario_id=conta.id,
        operacao_id=operacao_id,
        documento_id=recebimento.documento.id,
    )
    return _documento_v1(recebimento.documento)


_CARACTERES_FORA_DO_NOME = re.compile(r"[\x00-\x1f\x7f\"\\/:*?<>|]")


def _nome_do_arquivo(nome: str, tipo: str) -> str:
    """O nome de download: sem pasta, sem controle nem símbolo que o sistema recusa."""
    limpo = _CARACTERES_FORA_DO_NOME.sub("_", nome).strip(" .")
    return limpo or f"documento.{tipo}"


def _cabecalhos_de_anexo(nome: str, tipo: str) -> dict[str, str]:
    """Sempre anexo e nunca aberto na página (D9): o app não mostra o arquivo do cliente."""
    return {
        "Content-Disposition": (
            f"attachment; filename=\"documento.{tipo}\"; filename*=UTF-8''"
            f"{quote(_nome_do_arquivo(nome, tipo), safe='')}"
        ),
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "sandbox",
        "Cache-Control": "no-store",
    }


def _abrir_ou_503(abrir: Callable[[], bytes]) -> bytes:
    try:
        return abrir()
    except (cofre.CifraInvalidaError, FileNotFoundError) as erro:
        # o log leva só o tipo do erro: ids e nomes ficam de fora
        log.error("documento da sala não abriu: %s", type(erro).__name__)
        raise HTTPException(
            status_code=503, detail="Não foi possível abrir este arquivo agora."
        ) from erro


@router.get("/operacoes/{operacao_id}/documentos/{documento_id}/arquivo")
def baixar_documento(
    conta: Conta, operacao_id: uuid.UUID, documento_id: uuid.UUID
) -> Response:
    """O arquivo original, decifrado na hora, sempre como anexo (fica na auditoria)."""
    with obter_engine().begin() as conexao:
        aberto = _ou_404(
            _abrir_ou_503(
                lambda: documentos.baixar_documento(
                    conexao,
                    usuario_id=conta.id,
                    operacao_id=operacao_id,
                    documento_id=documento_id,
                )
            ),
            SEM_DOCUMENTO,
        )
    return Response(
        content=aberto.conteudo,
        media_type="application/octet-stream",
        headers=_cabecalhos_de_anexo(
            aberto.documento.nome_original, aberto.documento.tipo
        ),
    )


@router.delete("/operacoes/{operacao_id}/documentos/{documento_id}", status_code=204)
def apagar_documento(
    conta: Conta, operacao_id: uuid.UUID, documento_id: uuid.UUID
) -> Response:
    """Apaga o documento do banco e do disco, na hora (sem lixeira)."""
    with obter_engine().begin() as conexao:
        apagado = documentos.apagar_documento(
            conexao,
            usuario_id=conta.id,
            operacao_id=operacao_id,
            documento_id=documento_id,
        )
    _ou_404(apagado or None, SEM_DOCUMENTO)
    return Response(status_code=204)


# --- "Baixar a sala" ----------------------------------------------------------------------


def _entrada_do_zip(posicao: int, nome: str, tipo: str) -> str:
    """O nome dentro do ZIP: o número da ordem na frente garante nomes únicos e sem caminho."""
    return f"{posicao:03d}-{_nome_do_arquivo(nome, tipo)}"


def _montar_o_zip(
    conexao: sa.Connection,
    conta: Usuario,
    operacao_id: uuid.UUID,
    documentos_da_sala: list,
) -> tuple[BinaryIO, int]:
    """O ZIP da sala num arquivo temporário (nada fica na memória), e o total dos documentos."""
    saida = tempfile.TemporaryFile()  # noqa: SIM115 - fechado ao fim do download
    total = 0
    try:
        with zipfile.ZipFile(saida, "w", zipfile.ZIP_STORED, allowZip64=True) as zip_:
            for posicao, documento in enumerate(documentos_da_sala, start=1):
                aberto = _abrir_ou_503(
                    lambda doc=documento: documentos.abrir_documento(
                        conexao,
                        usuario_id=conta.id,
                        operacao_id=operacao_id,
                        documento_id=doc.id,
                    )
                )
                zip_.writestr(
                    _entrada_do_zip(posicao, documento.nome_original, documento.tipo),
                    _ou_404(aberto, SEM_DOCUMENTO).conteudo,
                )
                total += documento.tamanho_bytes
    except BaseException:
        saida.close()
        raise
    return saida, total


def _blocos_e_fechar(arquivo: BinaryIO) -> Iterator[bytes]:
    try:
        while bloco := arquivo.read(BLOCO_DO_DOWNLOAD):
            yield bloco
    finally:
        arquivo.close()


@router.get("/operacoes/{operacao_id}/sala")
def baixar_a_sala(conta: Conta, operacao_id: uuid.UUID) -> StreamingResponse:
    """Todos os documentos da operação num ZIP decifrado na hora (a saída da LGPD)."""
    ids = {"usuario_id": conta.id, "operacao_id": operacao_id}
    with obter_engine().begin() as conexao:
        _ou_404(sala.buscar_operacao(conexao, **ids))
        da_sala = sala.listar_documentos(conexao, **ids)
        zip_, total = _montar_o_zip(conexao, conta, operacao_id, da_sala)
        try:
            auditoria.registrar(
                conexao,
                conta.id,
                auditoria.ACAO_SALA_BAIXADA,
                operacao_id,
                {"documentos": len(da_sala), "tamanho_bytes": total},
            )
        except BaseException:
            zip_.close()
            raise
    tamanho = zip_.seek(0, os.SEEK_END)
    zip_.seek(0)
    return StreamingResponse(
        _blocos_e_fechar(zip_),
        media_type="application/octet-stream",
        headers={
            **_cabecalhos_de_anexo("sala.zip", "zip"),
            "Content-Length": str(tamanho),
        },
    )
