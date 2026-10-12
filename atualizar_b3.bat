@echo off
rem Acumula o boletim diario de futuros da B3 (so leitura; a B3 guarda so ~3 semanas).
rem Roda pela tarefa agendada "TickerLab - boletim da B3" (seg a sex, 20h) ou com duplo clique.
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
echo ===== %date% %time% >> "dados_b3\atualizacao.log"
".venv\Scripts\python.exe" -m trader.atualizar_b3 >> "dados_b3\atualizacao.log" 2>&1
