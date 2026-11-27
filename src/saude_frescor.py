"""Carimbo público do recorte principal recebido pela API, sem abrir dados da base."""

from datetime import UTC, datetime

from src import acervo

NOME_DA_MARCA = "mtime_base"


def frescor_da_base() -> dict[str, str] | None:
    """Devolve só a data da pasta do recorte e o nome fixo da marca, ou nada sem base.

    O recebedor extrai os arquivos numa pasta nova e troca `base/` inteira. O mtime dessa
    pasta registra o recebimento; o deploy de código e as bases auxiliares não o renovam.
    Isso mede a entrega do recorte, não a atualização de cada fonte dentro dele.
    """
    raiz = acervo.pasta_do_acervo()
    if raiz is None:
        return None
    try:
        pasta = (raiz / "base").resolve(strict=True)
        if not pasta.is_dir() or not any(a.is_file() for a in pasta.rglob("*.parquet")):
            return None
        data = datetime.fromtimestamp(pasta.stat().st_mtime, tz=UTC)
    except (OSError, ValueError, OverflowError):
        # A troca de pasta pode estar em curso. Sem marca válida, o vigia deve falhar.
        return None
    return {"base_atualizada_em": data.isoformat(), "fonte": NOME_DA_MARCA}
