"""Perfil "TickerLab" do Windows Terminal: o Claude Code no PowerShell com a cara do TickerLab.

O perfil abre o PowerShell 7 na pasta do projeto já dentro do Claude Code (pelo lançador
`scripts/terminal/claude-tickerlab.ps1`), com as cores da marca (`src/marca.py`), a fonte mono oficial
(JetBrains Mono, quando instalada) e o ícone do TickerLab. Vai para o Windows Terminal como um
*fragment*, o jeito oficial de um programa acrescentar perfil e esquema de cores sem mexer no
`settings.json` da pessoa: `%LOCALAPPDATA%\\Microsoft\\Windows Terminal\\Fragments\\TickerLab\\tickerlab.json`.

O mesmo comando instala, na pasta do Claude Code (`~/.claude` ou `CLAUDE_CONFIG_DIR`), o estilo de saída
"TickerLab" (`estilo-de-saida-tickerlab.md`) e os atalhos de teclado (`keybindings.json`, só se a pessoa
ainda não tem os seus) e, com `--fonte`, a JetBrains Mono do repositório para o usuário (sem
administrador). Tudo se desfaz com `--desfazer`.

    python -m scripts.terminal.perfil_windows_terminal               # instala (ou atualiza)
    python -m scripts.terminal.perfil_windows_terminal --so-mostrar  # só imprime o fragment
    python -m scripts.terminal.perfil_windows_terminal --fonte       # instala também a fonte
    python -m scripts.terminal.perfil_windows_terminal --desfazer [--fonte]

O repositório é público: nenhum caminho do PC entra aqui; o fragment gerado aponta para a cópia do
repositório em que o comando rodou.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import shutil
import sys
from collections.abc import Mapping
from pathlib import Path

from src import marca

NOME = "TickerLab"
PASTA_DESTE_MODULO = Path(__file__).resolve().parent
RAIZ_DO_REPOSITORIO = PASTA_DESTE_MODULO.parent.parent
ESTILO_DE_SAIDA = PASTA_DESTE_MODULO / "estilo-de-saida-tickerlab.md"
ATALHOS = PASTA_DESTE_MODULO / "keybindings.json"
ARQUIVO_DA_FONTE_MONO = (
    marca.PASTA_ESTATICA / "fontes" / "JetBrainsMono-VariableFont_wght.ttf"
)
NOME_DA_FONTE_NO_REGISTRO = f"{marca.FONTE_MONO} (TrueType)"
FONTE_RESERVA = "Cascadia Mono"  # vem com o Windows Terminal
OPACIDADE_DA_MARCA_DAGUA = 0.06  # o símbolo no canto, quase invisível
FATOR_DAS_CORES_VIVAS = (
    0.25  # as cores "bright" do terminal: as da marca, 25% mais claras
)
CHAVE_DO_REGISTRO_DAS_FONTES = r"Software\Microsoft\Windows NT\CurrentVersion\Fonts"
WM_FONTCHANGE = 0x001D  # mensagem do Windows: "as fontes mudaram"
HWND_BROADCAST = 0xFFFF  # para todas as janelas


# ----- esquema de cores e perfil -----------------------------------------------------------------


def clarear(cor: str, fator: float) -> str:
    """A cor `#rrggbb` misturada com branco: `fator` 0 devolve a cor; 1 devolve branco."""
    canais = (int(cor[inicio : inicio + 2], 16) for inicio in (1, 3, 5))
    claros = (round(canal + (255 - canal) * fator) for canal in canais)
    return "#" + "".join(f"{canal:02x}" for canal in claros)


def esquema_de_cores() -> dict[str, str]:
    """O esquema "TickerLab" do Windows Terminal: as cores da marca nos papéis do terminal.

    Verde e vermelho são alta e queda, amarelo é atenção, o azul é o legível sobre o marinho; os
    "bright" são as mesmas cores um pouco mais claras, para o texto em negrito não mudar de tom.
    """
    azul, _, ciano, roxo = marca.SERIES[:4]
    vivo = FATOR_DAS_CORES_VIVAS
    return {
        "name": NOME,
        "background": marca.FUNDO,
        "foreground": marca.TEXTO,
        "cursorColor": marca.AZUL,
        "selectionBackground": marca.DESTAQUE,
        "black": marca.MARINHO,
        "red": marca.QUEDA,
        "green": marca.ALTA,
        "yellow": marca.ATENCAO,
        "blue": marca.AZUL_TEXTO,
        "purple": roxo,
        "cyan": ciano,
        "white": marca.TEXTO_APAGADO,
        "brightBlack": marca.TEXTO_SUTIL,
        "brightRed": clarear(marca.QUEDA, vivo),
        "brightGreen": clarear(marca.ALTA, vivo),
        "brightYellow": clarear(marca.ATENCAO, vivo),
        "brightBlue": azul,
        "brightPurple": clarear(roxo, vivo),
        "brightCyan": clarear(ciano, vivo),
        "brightWhite": marca.CLARO,
    }


def perfil(raiz: Path, pwsh: str, fonte: str) -> dict[str, object]:
    """O perfil "TickerLab": o PowerShell 7 na raiz do repositório, já dentro do Claude Code."""
    lancador = raiz / "scripts" / "terminal" / "claude-tickerlab.ps1"
    pasta_da_marca = raiz / "static" / "marca"
    return {
        "name": NOME,
        "commandline": f'"{pwsh}" -NoLogo -NoExit -File "{lancador}"',
        "startingDirectory": str(raiz),
        "icon": str(pasta_da_marca / "icone.png"),
        "tabTitle": NOME,
        "colorScheme": NOME,
        "font": {"face": fonte},
        "backgroundImage": str(pasta_da_marca / "icone-512.png"),
        "backgroundImageOpacity": OPACIDADE_DA_MARCA_DAGUA,
        "backgroundImageAlignment": "bottomRight",
        "backgroundImageStretchMode": "none",
        "useAcrylic": False,
    }


def fragmento(raiz: Path, pwsh: str, fonte: str) -> dict[str, object]:
    """O fragment do Windows Terminal: só o perfil e o esquema (o resto do settings.json fica como está)."""
    return {"profiles": [perfil(raiz, pwsh, fonte)], "schemes": [esquema_de_cores()]}


def caminho_do_pwsh() -> str:
    """O PowerShell 7 (`pwsh`) pelo PATH; fora dele, só o nome, para o Windows Terminal procurar."""
    return shutil.which("pwsh") or "pwsh.exe"


# ----- onde cada coisa fica ----------------------------------------------------------------------


def pasta_local(ambiente: Mapping[str, str]) -> Path:
    """`%LOCALAPPDATA%` (ou o equivalente dentro da pasta do usuário, quando a variável não existe)."""
    local = ambiente.get("LOCALAPPDATA")
    return Path(local) if local else Path.home() / "AppData" / "Local"


def arquivo_do_fragmento(ambiente: Mapping[str, str]) -> Path:
    """O fragment deste programa na pasta de fragments do Windows Terminal."""
    return (
        pasta_local(ambiente)
        / "Microsoft"
        / "Windows Terminal"
        / "Fragments"
        / NOME
        / "tickerlab.json"
    )


def pasta_do_claude(ambiente: Mapping[str, str]) -> Path:
    """A pasta de configuração do Claude Code: `CLAUDE_CONFIG_DIR` ou `~/.claude`."""
    pasta = ambiente.get("CLAUDE_CONFIG_DIR")
    return Path(pasta) if pasta else Path.home() / ".claude"


def arquivo_do_estilo(ambiente: Mapping[str, str]) -> Path:
    """Onde o Claude Code lê os estilos de saída da pessoa."""
    return pasta_do_claude(ambiente) / "output-styles" / f"{NOME}.md"


def arquivo_dos_atalhos(ambiente: Mapping[str, str]) -> Path:
    """Os atalhos de teclado do Claude Code (um arquivo só, da pessoa)."""
    return pasta_do_claude(ambiente) / "keybindings.json"


def arquivo_da_fonte_instalada(ambiente: Mapping[str, str]) -> Path:
    """Onde o Windows guarda as fontes instaladas só para o usuário."""
    return (
        pasta_local(ambiente)
        / "Microsoft"
        / "Windows"
        / "Fonts"
        / ARQUIVO_DA_FONTE_MONO.name
    )


# ----- fonte -------------------------------------------------------------------------------------


def _nomes_das_fontes_registradas(raiz: int) -> list[str]:
    """Os nomes das fontes registradas numa raiz do registro (HKLM: a máquina; HKCU: o usuário)."""
    if sys.platform != "win32":
        return []
    import winreg

    try:
        with winreg.OpenKey(raiz, CHAVE_DO_REGISTRO_DAS_FONTES) as chave:
            quantos_valores = winreg.QueryInfoKey(chave)[1]
            return [
                winreg.EnumValue(chave, indice)[0] for indice in range(quantos_valores)
            ]
    except OSError:
        return []


def fonte_instalada(nome: str) -> bool:
    """Se uma fonte dessa família está registrada no Windows (para a máquina ou só para o usuário)."""
    if sys.platform != "win32":
        return False
    import winreg

    raizes = (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER)
    return any(
        registrada.startswith(nome)
        for raiz in raizes
        for registrada in _nomes_das_fontes_registradas(raiz)
    )


def fonte_do_perfil() -> str:
    """A fonte mono oficial da marca, se estiver instalada; senão a que vem com o Windows Terminal."""
    return marca.FONTE_MONO if fonte_instalada(marca.FONTE_MONO) else FONTE_RESERVA


def _avisar_que_as_fontes_mudaram() -> None:
    """Avisa os programas abertos (o Windows Terminal inclusive) de que a lista de fontes mudou."""
    if sys.platform != "win32":
        return
    import ctypes

    ctypes.windll.user32.SendNotifyMessageW(HWND_BROADCAST, WM_FONTCHANGE, 0, 0)


def instalar_fonte(ambiente: Mapping[str, str]) -> Path:
    """Instala a JetBrains Mono do repositório para o usuário, como o "Instalar para o usuário" do Windows.

    Copia o arquivo para a pasta de fontes do usuário, registra em HKCU e avisa os programas abertos.
    Não precisa de administrador e se desfaz com `desinstalar_fonte`. Só no Windows.
    """
    if sys.platform != "win32":
        raise RuntimeError("a fonte só se instala no Windows")
    import ctypes
    import winreg

    destino = arquivo_da_fonte_instalada(ambiente)
    destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ARQUIVO_DA_FONTE_MONO, destino)
    with winreg.CreateKey(
        winreg.HKEY_CURRENT_USER, CHAVE_DO_REGISTRO_DAS_FONTES
    ) as chave:
        winreg.SetValueEx(
            chave, NOME_DA_FONTE_NO_REGISTRO, 0, winreg.REG_SZ, str(destino)
        )
    ctypes.windll.gdi32.AddFontResourceW(str(destino))
    _avisar_que_as_fontes_mudaram()
    return destino


def desinstalar_fonte(ambiente: Mapping[str, str]) -> Path:
    """Desfaz `instalar_fonte`: tira do registro, apaga o arquivo e avisa os programas abertos."""
    if sys.platform != "win32":
        raise RuntimeError("a fonte só se instala no Windows")
    import ctypes
    import winreg

    arquivo = arquivo_da_fonte_instalada(ambiente)
    ctypes.windll.gdi32.RemoveFontResourceW(str(arquivo))
    with (
        contextlib.suppress(OSError),  # já não estava registrada: nada a tirar
        winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            CHAVE_DO_REGISTRO_DAS_FONTES,
            0,
            winreg.KEY_SET_VALUE,
        ) as chave,
    ):
        winreg.DeleteValue(chave, NOME_DA_FONTE_NO_REGISTRO)
    arquivo.unlink(missing_ok=True)
    _avisar_que_as_fontes_mudaram()
    return arquivo


# ----- instalar e desfazer -----------------------------------------------------------------------


def gravar_fragmento(
    ambiente: Mapping[str, str], raiz: Path = RAIZ_DO_REPOSITORIO
) -> Path:
    """Grava o fragment (perfil e esquema) na pasta de fragments do Windows Terminal."""
    destino = arquivo_do_fragmento(ambiente)
    destino.parent.mkdir(parents=True, exist_ok=True)
    conteudo = json.dumps(
        fragmento(raiz, caminho_do_pwsh(), fonte_do_perfil()),
        indent=2,
        ensure_ascii=False,
    )
    destino.write_text(conteudo + "\n", encoding="utf-8")
    return destino


def instalar_estilo(ambiente: Mapping[str, str]) -> Path:
    """Copia o estilo de saída "TickerLab" para a pasta do Claude Code (sobrescreve: o arquivo é do projeto)."""
    destino = arquivo_do_estilo(ambiente)
    destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ESTILO_DE_SAIDA, destino)
    return destino


def instalar_atalhos(ambiente: Mapping[str, str]) -> tuple[Path, bool]:
    """Copia os atalhos se a pessoa ainda não tem os seus; os dela ficam (e o segundo valor avisa)."""
    destino = arquivo_dos_atalhos(ambiente)
    if destino.exists() and destino.read_bytes() != ATALHOS.read_bytes():
        return destino, False
    destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ATALHOS, destino)
    return destino, True


def instalar(
    ambiente: Mapping[str, str], com_fonte: bool, raiz: Path = RAIZ_DO_REPOSITORIO
) -> list[str]:
    """Instala tudo (a fonte primeiro, para o perfil já nascer com ela) e diz o que fez, uma linha por item."""
    feitos: list[str] = []
    if com_fonte:
        feitos.append(
            f"fonte {marca.FONTE_MONO} instalada para o usuário: {instalar_fonte(ambiente)}"
        )
    feitos.append(
        f"perfil e esquema do Windows Terminal: {gravar_fragmento(ambiente, raiz)}"
    )
    feitos.append(f"estilo de saída do Claude Code: {instalar_estilo(ambiente)}")
    atalhos, copiados = instalar_atalhos(ambiente)
    if copiados:
        feitos.append(f"atalhos de teclado do Claude Code: {atalhos}")
    else:
        feitos.append(
            f"atalhos de teclado: {atalhos} já existe com outro conteúdo; junte à mão os de {ATALHOS}"
        )
    return feitos


def _apagar_se_existir(arquivo: Path) -> bool:
    if not arquivo.exists():
        return False
    arquivo.unlink()
    return True


def _apagar_pasta_se_vazia(pasta: Path) -> None:
    if pasta.is_dir() and not any(pasta.iterdir()):
        pasta.rmdir()


def desfazer(ambiente: Mapping[str, str], com_fonte: bool) -> list[str]:
    """Remove o que `instalar` gravou (os atalhos só se ainda forem os nossos) e diz o que fez."""
    feitos: list[str] = []
    fragmento_instalado = arquivo_do_fragmento(ambiente)
    if _apagar_se_existir(fragmento_instalado):
        feitos.append(f"apagado: {fragmento_instalado}")
    _apagar_pasta_se_vazia(fragmento_instalado.parent)
    estilo = arquivo_do_estilo(ambiente)
    if _apagar_se_existir(estilo):
        feitos.append(f"apagado: {estilo}")
    atalhos = arquivo_dos_atalhos(ambiente)
    if atalhos.exists() and atalhos.read_bytes() == ATALHOS.read_bytes():
        atalhos.unlink()
        feitos.append(f"apagado: {atalhos}")
    elif atalhos.exists():
        feitos.append(f"mantido (tem atalhos da pessoa): {atalhos}")
    if com_fonte:
        feitos.append(
            f"fonte {marca.FONTE_MONO} removida do usuário: {desinstalar_fonte(ambiente)}"
        )
    return feitos


def dica_da_linha_de_status(
    ambiente: Mapping[str, str], raiz: Path = RAIZ_DO_REPOSITORIO
) -> str:
    """O que acrescentar ao settings.json do Claude Code para ligar a linha de status.

    O arquivo é da pessoa (hooks, permissões, modelo): este programa não o edita, só diz a linha.
    """
    comando = f"node {(raiz / 'scripts' / 'terminal' / 'statusline.js').as_posix()}"
    chave = json.dumps(
        {"statusLine": {"type": "command", "command": comando, "padding": 0}}
    )
    settings = pasta_do_claude(ambiente) / "settings.json"
    return f"linha de status (vale para o app também): acrescente a {settings} a chave {chave}"


def principal(
    argumentos: list[str] | None = None, ambiente: Mapping[str, str] | None = None
) -> int:
    """Linha de comando: instala, mostra ou desfaz."""
    analisador = argparse.ArgumentParser(
        prog="python -m scripts.terminal.perfil_windows_terminal",
        description="Instala o perfil TickerLab do Windows Terminal, o estilo de saída e os atalhos do Claude Code.",
    )
    analisador.add_argument(
        "--so-mostrar",
        action="store_true",
        help="só imprime o fragment, sem gravar nada",
    )
    analisador.add_argument(
        "--fonte",
        action="store_true",
        help="instala (ou, com --desfazer, remove) a fonte",
    )
    analisador.add_argument(
        "--desfazer", action="store_true", help="remove o que foi instalado"
    )
    opcoes = analisador.parse_args(argumentos)
    ambiente = os.environ if ambiente is None else ambiente
    if opcoes.so_mostrar:
        conteudo = fragmento(RAIZ_DO_REPOSITORIO, caminho_do_pwsh(), fonte_do_perfil())
        print(json.dumps(conteudo, indent=2, ensure_ascii=False))
        return 0
    feitos = (
        desfazer(ambiente, opcoes.fonte)
        if opcoes.desfazer
        else instalar(ambiente, opcoes.fonte)
    )
    for linha in feitos:
        print(linha)
    if not opcoes.desfazer:
        print(
            f'Pronto: o perfil "{NOME}" aparece no menu de abas do Windows Terminal (feche e abra o Terminal se não aparecer).'
        )
        print(dica_da_linha_de_status(ambiente))
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
