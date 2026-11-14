"""As cargas agendadas de casa não importam o pacote `scripts` (linha 933).

A imagem que os roteiros de casa usam leva `base/` e `src/`, mas não a pasta `scripts/` além do próprio
roteiro: `from scripts import ...` nelas para com `ModuleNotFoundError`. Foi o que derrubou a carga do café
e a mensal do Banco Central depois da linha 904, lote 4 (a ponte do CNPJ morava em `scripts/carga_ponte.py`).
O que as cargas dividem fica em `base/`."""

import ast
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
# as cargas que rodam pela imagem de casa e já foram consertadas; carga nova da imagem entra aqui
SEM_SCRIPTS = ("scripts/carga_setoriais.py", "scripts/carga_bcb_credito.py")


def _importa_scripts(arquivo: str) -> list[str]:
    arvore = ast.parse((RAIZ / arquivo).read_text(encoding="utf-8"))
    achados = []
    for no in ast.walk(arvore):
        if (
            isinstance(no, ast.ImportFrom)
            and (no.module or "").split(".")[0] == "scripts"
        ):
            achados.append(f"from {no.module} import ...")
        elif isinstance(no, ast.Import):
            achados += [
                f"import {a.name}"
                for a in no.names
                if a.name.split(".")[0] == "scripts"
            ]
    return achados


def test_cargas_de_casa_nao_importam_scripts():
    for arquivo in SEM_SCRIPTS:
        assert not _importa_scripts(arquivo), f"{arquivo} importa o pacote scripts"


def test_o_detector_pega_import_de_scripts(tmp_path, monkeypatch):
    falso = tmp_path / "carga_falsa.py"
    falso.write_text(
        "from scripts import carga_x\nimport scripts.y\n", encoding="utf-8"
    )
    monkeypatch.setattr(__import__(__name__), "RAIZ", tmp_path)
    assert len(_importa_scripts("carga_falsa.py")) == 2
