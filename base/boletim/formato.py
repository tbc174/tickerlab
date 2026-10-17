"""Números no jeito brasileiro para o boletim (as mesmas regras dos relatórios de cruzamentos v2)."""

import math


def ok(v: object) -> bool:
    return v is not None and not (isinstance(v, float) and math.isnan(v))


def num(v: float | None, casas: int = 0) -> str:
    if not ok(v):
        return "—"
    s = f"{v:,.{casas}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def pct(v: float | None, casas: int = 1) -> str:
    """Fração (0,25) em porcentagem ("25,0%")."""
    return "—" if not ok(v) else f"{num(100 * v, casas)}%"  # type: ignore[operator]


def grande(v: float | None, casas: int = 1) -> str:
    """Contagens grandes: 1,2 mi, 3,4 bi."""
    if not ok(v):
        return "—"
    a = abs(v)  # type: ignore[arg-type]
    if a >= 1e9:
        return f"{num(v / 1e9, casas)} bi"  # type: ignore[operator]
    if a >= 1e6:
        return f"{num(v / 1e6, casas)} mi"  # type: ignore[operator]
    if a >= 1e4:
        return f"{num(v / 1e3, 0)} mil"  # type: ignore[operator]
    return num(v)


def reais(v: float | None) -> str:
    if not ok(v):
        return "—"
    sinal = "−" if v < 0 else ""  # type: ignore[operator]
    a = abs(v)  # type: ignore[arg-type]
    for limite, nome in ((1e12, "tri"), (1e9, "bi"), (1e6, "mi")):
        if a >= limite:
            return f"{sinal}R$ {num(a / limite, 1)} {nome}"
    if a >= 1e3:
        return f"{sinal}R$ {num(a / 1e3, 0)} mil"
    return f"{sinal}R$ {num(a, 0)}"


def tamanho(bytes_: int) -> str:
    for limite, nome in ((1e9, "GB"), (1e6, "MB"), (1e3, "KB")):
        if bytes_ >= limite:
            return f"{num(bytes_ / limite, 1)} {nome}"
    return f"{bytes_} B"


def com_sinal(v: int) -> str:
    return f"+{grande(v)}" if v > 0 else ("0" if v == 0 else f"−{grande(-v)}")
