@echo off
rem Abre uma sessao do Claude Code neste PC que voce comanda pelo app Claude no celular.
rem Duplo clique, ou ponha um atalho em shell:startup (Win+R) para abrir quando o Windows ligar.
rem A sessao trabalha nesta pasta, com as regras do CLAUDE.md. O PC precisa ficar ligado e esta
rem janela aberta; para encerrar, feche a janela.
cd /d "%~dp0"
where claude >nul 2>nul
if errorlevel 1 (
    echo O Claude Code nao esta instalado neste PC ^(comando "claude" nao encontrado^).
    pause
    exit /b 1
)
claude remote-control
pause
