"""Confere que a imagem de produção tem tudo o que o app importa."""

import ast
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PACOTES_QUE_O_PIP_CHAMA_DIFERENTE: dict[str, str] = {}


def _importados_de_terceiros() -> set[str]:
    arquivos = [RAIZ / "app.py", *(RAIZ / "src").glob("*.py")]
    nomes: set[str] = set()
    for arquivo in arquivos:
        for no in ast.walk(ast.parse(arquivo.read_text(encoding="utf-8"))):
            if isinstance(no, ast.Import):
                nomes.update(a.name.split(".")[0] for a in no.names)
            elif isinstance(no, ast.ImportFrom) and no.level == 0 and no.module:
                nomes.add(no.module.split(".")[0])
    return {n for n in nomes if n not in sys.stdlib_module_names and n != "src"}


def _pacotes_do_requirements(nome_do_arquivo: str) -> dict[str, str]:
    pacotes = {}
    for linha in (RAIZ / nome_do_arquivo).read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if linha and not linha.startswith("#"):
            nome, _, versao = linha.partition("==")
            pacotes[nome.lower().replace("_", "-")] = versao
    return pacotes


def test_a_imagem_de_producao_instala_tudo_o_que_o_app_importa():
    producao = _pacotes_do_requirements("requirements-prod.txt")
    faltando = {
        PACOTES_QUE_O_PIP_CHAMA_DIFERENTE.get(n, n) for n in _importados_de_terceiros()
    } - set(producao)
    assert not faltando, f"Faltam no requirements-prod.txt: {sorted(faltando)}"


def test_versoes_de_producao_sao_as_mesmas_do_requirements_completo():
    completo = _pacotes_do_requirements("requirements.txt")
    for pacote, versao in _pacotes_do_requirements("requirements-prod.txt").items():
        assert completo.get(pacote) == versao, f"{pacote}: versão diferente"


def test_dockerfile_copia_o_que_o_app_le_em_tempo_de_execucao():
    dockerfile = (RAIZ / "Dockerfile").read_text(encoding="utf-8")
    for pasta in ("src", "conteudo", "dados_de_exemplo", ".streamlit"):
        assert f"COPY {pasta} " in dockerfile or f"COPY {pasta}\n" in dockerfile, pasta
    assert "COPY app.py" in dockerfile
    assert "USER app" in dockerfile  # não roda como root
    dockerignore = (RAIZ / ".dockerignore").read_text(encoding="utf-8")
    for fora in (".venv", "tests", "dados_locais", ".git"):
        assert fora in dockerignore.splitlines()
    for dentro in ("conteudo", "dados_de_exemplo", "src"):
        assert dentro not in dockerignore.splitlines()


def test_compose_publica_a_porta_so_em_localhost():
    compose = (RAIZ / "compose.yaml").read_text(encoding="utf-8")
    assert '"127.0.0.1:8501:8501"' in compose
    assert "0.0.0.0" not in compose
