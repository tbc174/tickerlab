# Ponte do `tl` para o Windows PowerShell 5.1 (powershell.exe, o azul que o Windows abre por padrão). O módulo exige o
# PowerShell 7, então o perfil do 5.1 carrega este arquivo (linha posta pelo instalar.ps1), que define um `tl` igual na
# aparência: cada comando roda num pwsh sem perfil, com os argumentos como vieram (`tl nova Dados "tarefa" -SoMostrar`).
# Sem `#Requires` de propósito: quem lê este arquivo é o 5.1. Gravado com BOM para o 5.1 ler os acentos.

function tl {
    $pwsh = Get-Command pwsh -ErrorAction SilentlyContinue
    if (-not $pwsh) {
        Write-Host 'O tl precisa do PowerShell 7 (pwsh), que não foi achado neste PC: winget install Microsoft.PowerShell' -ForegroundColor Yellow
        return
    }
    & $pwsh.Source -NoLogo -NoProfile -File (Join-Path $PSScriptRoot 'ponte-pwsh.ps1') @args
}
