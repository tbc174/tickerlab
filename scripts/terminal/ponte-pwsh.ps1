#Requires -Version 7.0
# Lado do PowerShell 7 da ponte: importa o módulo e roda o `tl` com os argumentos que a ponte do 5.1 repassou.
Import-Module (Join-Path $PSScriptRoot 'TickerLab.psd1')
tl @args
