@echo off
rem Abre o painel do trader (so leitura). Duplo clique.
cd /d "%~dp0"
start "" ".venv\Scripts\pythonw.exe" -m trader.interface
