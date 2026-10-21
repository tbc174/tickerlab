"""Onde os arquivos cifrados da sala ficam no disco (decisões D2 e D6 do plano do B-20).

Num volume próprio do VPS (`./dados_sala:/app/dados_sala`, montado só no contêiner da API), uma
pasta por operação e dois arquivos por documento: `<documento_id>.bin` (o original cifrado) e
`<documento_id>.txt.bin` (o texto lido, cifrado). O caminho nasce **só dos ids** (UUID), nunca do
nome que veio no envio: não há como um nome de arquivo escapar da pasta.

Aqui só se grava, lê e apaga bytes já cifrados; quem cifra é `cofre.py` e quem junta banco, cifra
e disco é `documentos.py`.
"""

import os
import shutil
import uuid
from pathlib import Path

VARIAVEL_DA_PASTA = "TICKERLAB_PASTA_DA_SALA"
PASTA_PADRAO = Path("dados_sala")
FRACAO_LIVRE_MINIMA = 0.20  # o envio para com menos de 20% do disco livre (D6)

SUFIXOS = {"original": ".bin", "texto": ".txt.bin"}
PERMISSAO_DA_PASTA = 0o700
PERMISSAO_DO_ARQUIVO = 0o600


class SalaSemEspacoError(RuntimeError):
    """O disco da sala está quase cheio: o envio para até alguém liberar espaço."""


def pasta_da_sala() -> Path:
    """A pasta de todas as salas (`TICKERLAB_PASTA_DA_SALA`, ou `dados_sala`)."""
    return Path(os.environ.get(VARIAVEL_DA_PASTA) or PASTA_PADRAO)


def _uuid_em_texto(valor: uuid.UUID) -> str:
    # refazer o UUID garante só hexadecimal e hífen no nome, mesmo se vier texto de fora
    return str(uuid.UUID(str(valor)))


def pasta_da_operacao(raiz: Path, operacao_id: uuid.UUID) -> Path:
    """A pasta de uma operação; o nome é o UUID refeito (texto que não é UUID levanta erro)."""
    return raiz / _uuid_em_texto(operacao_id)


def caminho_do_documento(
    raiz: Path, operacao_id: uuid.UUID, documento_id: uuid.UUID, parte: str
) -> Path:
    """Onde fica o original (`parte="original"`) ou o texto (`parte="texto"`) do documento."""
    nome = _uuid_em_texto(documento_id) + SUFIXOS[parte]
    return pasta_da_operacao(raiz, operacao_id) / nome


def conferir_espaco_livre(raiz: Path) -> None:
    """Levanta `SalaSemEspacoError` se o disco da sala tem menos de 20% livre."""
    raiz.mkdir(mode=PERMISSAO_DA_PASTA, parents=True, exist_ok=True)
    uso = shutil.disk_usage(raiz)
    if uso.free < FRACAO_LIVRE_MINIMA * uso.total:
        raise SalaSemEspacoError("O disco da sala está quase cheio.")


def gravar(caminho: Path, dados: bytes) -> None:
    """Grava inteiro ou nada: escreve num temporário ao lado e troca de nome no fim."""
    caminho.parent.mkdir(mode=PERMISSAO_DA_PASTA, parents=True, exist_ok=True)
    temporario = caminho.with_name(f".{caminho.name}.{uuid.uuid4().hex}.parcial")
    descritor = os.open(
        temporario,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
        PERMISSAO_DO_ARQUIVO,
    )
    try:
        with os.fdopen(descritor, "wb") as arquivo:
            arquivo.write(dados)
            arquivo.flush()
            os.fsync(arquivo.fileno())
        os.replace(temporario, caminho)
    except BaseException:
        temporario.unlink(missing_ok=True)
        raise


def ler(caminho: Path) -> bytes:
    """Os bytes do arquivo (já cifrados); `FileNotFoundError` se não está no disco."""
    return caminho.read_bytes()


def apagar_documento(
    raiz: Path, operacao_id: uuid.UUID, documento_id: uuid.UUID
) -> None:
    """Apaga o original e o texto do documento (o que não existe é ignorado)."""
    for parte in SUFIXOS:
        caminho_do_documento(raiz, operacao_id, documento_id, parte).unlink(
            missing_ok=True
        )


def apagar_operacao(raiz: Path, operacao_id: uuid.UUID) -> None:
    """Apaga a pasta da operação inteira (o que não existe é ignorado)."""
    pasta = pasta_da_operacao(raiz, operacao_id)
    if pasta.is_symlink():  # nunca segue atalho para fora da sala
        pasta.unlink()
        return
    if pasta.exists():
        shutil.rmtree(pasta)
