"""Gera as imagens de marca que aparecem no GitHub, a partir de `docs/banner.html`.

- `docs/imagens/banner.png`: o cabeçalho do README do repositório e do README de perfil (1280x400).
- `docs/imagens/previa-social.png`: a prévia social do repositório (1280x640), que se envia à mão em
  Settings > Social preview (o GitHub não tem rota de API para isso).

A página é desenhada pelo Edge ou pelo Chrome sem janela, com as fontes de `static/fontes/`. Os gráficos
do README saem de outro script (`scripts/gerar_imagens_do_readme.py`).

Roda: manual (python -m scripts.gerar_imagens_do_github; precisa do Edge ou do Chrome instalado), quando
a frase, a marca ou os comandos mostrados em docs/banner.html mudam.
"""

import shutil
import subprocess
import tempfile
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PAGINA = RAIZ / "docs" / "banner.html"
PASTA = RAIZ / "docs" / "imagens"
LARGURA = 1280
# nome do arquivo, altura em pixels, parâmetro da página e escala (o cabeçalho sai com o dobro de pontos)
IMAGENS: tuple[tuple[str, int, str, int], ...] = (
    ("banner.png", 400, "", 2),
    ("previa-social.png", 640, "?formato=previa", 1),
)
NAVEGADORES = ("msedge", "chrome", "chromium", "google-chrome")
PASTAS_DO_WINDOWS = (
    Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
    Path("C:/Program Files/Microsoft/Edge/Application/msedge.exe"),
    Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
)
ESPERA_MAXIMA_EM_SEGUNDOS = 120
# o navegador às vezes devolve o controle antes de gravar, ou não grava na primeira vez de um perfil novo
TENTATIVAS = 3
ESPERA_PELO_ARQUIVO_EM_SEGUNDOS = 10


def achar_navegador() -> str:
    """O caminho do Edge ou do Chrome; sem nenhum dos dois, não há como desenhar a página."""
    for nome in NAVEGADORES:
        caminho = shutil.which(nome)
        if caminho:
            return caminho
    for caminho in PASTAS_DO_WINDOWS:
        if caminho.is_file():
            return str(caminho)
    raise SystemExit("Instale o Edge ou o Chrome para gerar as imagens do GitHub.")


def comando(
    navegador: str, perfil: str, destino: Path, altura: int, parametro: str, escala: int
) -> list[str]:
    """A linha de comando que fotografa a página no tamanho pedido."""
    return [
        navegador,
        "--headless=new",
        "--disable-gpu",
        # perfil só desta rodada: com o navegador da pessoa aberto, a captura pode sair vazia sem avisar
        f"--user-data-dir={perfil}",
        "--allow-file-access-from-files",
        "--hide-scrollbars",
        f"--force-device-scale-factor={escala}",
        f"--window-size={LARGURA},{altura}",
        f"--screenshot={destino}",
        PAGINA.as_uri() + parametro,
    ]


def _apareceu(destino: Path) -> bool:
    """Espera um pouco pelo arquivo: o navegador pode gravá-lo logo depois de devolver o controle."""
    limite = time.monotonic() + ESPERA_PELO_ARQUIVO_EM_SEGUNDOS
    while time.monotonic() < limite:
        if destino.is_file() and destino.stat().st_size > 0:
            return True
        time.sleep(0.5)
    return False


def fotografar(navegador: str, perfil: str, imagem: tuple[str, int, str, int]) -> Path:
    """Grava uma imagem, tentando de novo quando o navegador sai sem gravar."""
    nome, altura, parametro, escala = imagem
    destino = PASTA / nome
    destino.unlink(missing_ok=True)
    for _ in range(TENTATIVAS):
        subprocess.run(
            comando(navegador, perfil, destino, altura, parametro, escala),
            check=True,
            timeout=ESPERA_MAXIMA_EM_SEGUNDOS,
            capture_output=True,
        )
        if _apareceu(destino):
            return destino
    raise SystemExit(f"O navegador não gravou {nome}.")


def main() -> None:
    navegador = achar_navegador()
    PASTA.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as perfil:
        for imagem in IMAGENS:
            destino = fotografar(navegador, perfil, imagem)
            print("gerada:", destino.relative_to(RAIZ))


if __name__ == "__main__":
    main()
