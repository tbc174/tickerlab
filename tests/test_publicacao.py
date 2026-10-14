"""Confere que a imagem de produção tem tudo o que o app importa."""

import ast
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PACOTES_QUE_O_PIP_CHAMA_DIFERENTE: dict[str, str] = {"fpdf": "fpdf2"}
PACOTES_NOSSOS = {"src", "telas", "base"}  # pastas do próprio repositório, não do pip


def _importados_de_terceiros() -> set[str]:
    arquivos = [
        RAIZ / "app.py",
        *(RAIZ / "src").glob("*.py"),
        *(RAIZ / "telas").rglob("*.py"),
        *(RAIZ / "base").glob(
            "*.py"
        ),  # as regras de qualidade, que a tela Fundamentos usa
    ]
    nomes: set[str] = set()
    for arquivo in arquivos:
        for no in ast.walk(ast.parse(arquivo.read_text(encoding="utf-8"))):
            if isinstance(no, ast.Import):
                nomes.update(a.name.split(".")[0] for a in no.names)
            elif isinstance(no, ast.ImportFrom) and no.level == 0 and no.module:
                nomes.add(no.module.split(".")[0])
    return {
        n for n in nomes if n not in sys.stdlib_module_names and n not in PACOTES_NOSSOS
    }


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
    for pasta in ("src", "telas", "base", "conteudo", "dados_de_exemplo", ".streamlit"):
        assert f"COPY {pasta} " in dockerfile or f"COPY {pasta}\n" in dockerfile, pasta
    assert "COPY app.py" in dockerfile
    assert "COPY migracoes " in dockerfile and "COPY alembic.ini" in dockerfile
    assert "USER app" in dockerfile  # não roda como root
    dockerignore = (RAIZ / ".dockerignore").read_text(encoding="utf-8")
    for fora in (".venv", "tests", "dados_locais", ".git"):
        assert fora in dockerignore.splitlines()
    for dentro in ("conteudo", "dados_de_exemplo", "src", "telas", "base"):
        assert dentro not in dockerignore.splitlines()


def test_compose_publica_as_portas_so_em_localhost():
    compose = (RAIZ / "compose.yaml").read_text(encoding="utf-8")
    portas = re.findall(r'^\s+- "([\d.]+:\d+:\d+)"\s*$', compose, flags=re.MULTILINE)
    assert sorted(portas) == ["127.0.0.1:8000:8000", "127.0.0.1:8501:8501"]


def test_compose_tem_o_app_e_a_api_com_a_mesma_imagem():
    compose = (RAIZ / "compose.yaml").read_text(encoding="utf-8")
    assert "  tickerlab-api:" in compose
    assert compose.count("image: tickerlab:local") == 2
    assert '"src.api:app"' in compose
    assert "service_healthy" in compose  # a API espera as migrações do app


def test_a_imagem_de_producao_tem_o_que_o_login_do_google_exige():
    """O st.login usa o cliente Starlette do Authlib, que importa o httpx (sem ele: erro 500)."""
    producao = _pacotes_do_requirements("requirements-prod.txt")
    assert "authlib" in producao and "httpx" in producao


def test_toda_imagem_do_readme_existe():
    readme = (RAIZ / "README.md").read_text(encoding="utf-8")
    imagens = re.findall(r"\]\((docs/imagens/[^)]+)\)", readme)
    assert imagens, "o README deveria ter imagens"
    for caminho in imagens:
        assert (RAIZ / caminho).is_file(), caminho


def test_compose_manda_os_logs_em_json_nos_dois_servicos():
    compose = (RAIZ / "compose.yaml").read_text(encoding="utf-8")
    assert compose.count("TICKERLAB_LOG_FORMATO: json") == 2


def test_a_api_le_o_mesmo_cache_de_precos_do_app():
    """A API v1 calcula com os mesmos preços do app (ADR 0048): a pasta montada nos dois serviços."""
    compose = (RAIZ / "compose.yaml").read_text(encoding="utf-8")
    assert compose.count("- ./dados_locais:/app/dados_locais") == 2


def test_imagem_leva_a_versao_do_codigo():
    """Exigência 13 da ADR 0055: o build grava o commit, o compose o repassa e o deploy o informa
    (inclusive na volta para a versão anterior, porque o commit é lido na hora de subir)."""
    dockerfile = (RAIZ / "Dockerfile").read_text(encoding="utf-8")
    assert 'ARG TICKERLAB_VERSAO=""' in dockerfile
    assert "ENV TICKERLAB_VERSAO=${TICKERLAB_VERSAO}" in dockerfile
    compose = (RAIZ / "compose.yaml").read_text(encoding="utf-8")
    assert "TICKERLAB_VERSAO: ${TICKERLAB_VERSAO:-}" in compose
    deploy = (RAIZ / "scripts" / "deploy-automatico.sh").read_text(encoding="utf-8")
    assert (
        'subir() { TICKERLAB_VERSAO="$(git rev-parse HEAD)" docker compose up' in deploy
    )
