"""Carimbo público do recorte principal recebido pela API, sem abrir dados da base."""

from datetime import UTC, datetime
from stat import S_ISREG

from src import acervo

NOME_DA_MARCA = "mtime_parquet"


def frescor_da_base() -> dict[str, str] | None:
    """Devolve o maior mtime dos Parquets da base principal, ou nada sem base.

    Vale tanto para troca da pasta inteira quanto para regravação dos mesmos arquivos.
    Percorre só metadados, sem abrir Parquet; o arquivo mais recente não garante que
    todas as fontes estejam em dia. Deploy de código não renova essa marca.
    """
    raiz = acervo.pasta_do_acervo()
    if raiz is None:
        return None
    try:
        pasta = (raiz / "base").resolve(strict=True)
        if not pasta.is_dir():
            return None
        marca = None
        for arquivo in pasta.rglob("*.parquet"):
            estado = arquivo.stat()
            if S_ISREG(estado.st_mode):
                marca = (
                    estado.st_mtime if marca is None else max(marca, estado.st_mtime)
                )
        if marca is None:
            return None
        data = datetime.fromtimestamp(marca, tz=UTC)
    except (OSError, ValueError, OverflowError):
        # A troca de pasta pode estar em curso. Sem marca válida, o vigia deve falhar.
        return None
    return {"base_atualizada_em": data.isoformat(), "fonte": NOME_DA_MARCA}
