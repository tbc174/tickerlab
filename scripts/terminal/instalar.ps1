#Requires -Version 7.0
<#
.SYNOPSIS
Instala o painel `tl` no perfil do PowerShell e, se pedido, grava a pasta privada na variável de ambiente.

.DESCRIPTION
Acrescenta uma linha Import-Module ao perfil do usuário (todas as janelas: $PROFILE.CurrentUserAllHosts) e,
com -PastaPrivada, grava TICKERLAB_PASTA_PRIVADA nas variáveis do usuário, para `tl fila` achar o fila.md.
Com -SoMostrar, só diz o que faria. Rode de novo se mover o repositório: a linha do perfil é atualizada.

.EXAMPLE
.\scripts\terminal\instalar.ps1 -SoMostrar
.\scripts\terminal\instalar.ps1 -PastaPrivada 'C:\caminho\da\pasta-privada'
#>
param([string]$PastaPrivada, [switch]$SoMostrar)

$manifesto = Join-Path $PSScriptRoot 'TickerLab.psd1'
$marca = '# TickerLab: painel do terminal (tl)'
$linhaNova = "Import-Module '$manifesto'  $marca"
$perfil = $PROFILE.CurrentUserAllHosts

Write-Host "Perfil do PowerShell: $perfil"
$linhas = if (Test-Path -LiteralPath $perfil) { @(Get-Content -LiteralPath $perfil -Encoding utf8) } else { @() }
$linhaAtual = $linhas | Where-Object { $_.Contains($marca) } | Select-Object -First 1
if ($linhaAtual -eq $linhaNova) {
    Write-Host '  já importa o módulo: nada a fazer.'
} elseif ($SoMostrar) {
    Write-Host ("  {0}: {1}" -f ($(if ($linhaAtual) { 'trocaria a linha por' } else { 'acrescentaria' })), $linhaNova)
} elseif ($linhaAtual) {
    $novas = $linhas | ForEach-Object { if ($_ -eq $linhaAtual) { $linhaNova } else { $_ } }
    Set-Content -LiteralPath $perfil -Value $novas -Encoding utf8
    Write-Host "  atualizei a linha: $linhaNova"
} else {
    New-Item -ItemType Directory -Path (Split-Path -Parent $perfil) -Force | Out-Null
    Add-Content -LiteralPath $perfil -Value $linhaNova -Encoding utf8
    Write-Host "  acrescentei: $linhaNova"
}

if ($PastaPrivada) {
    $fila = Join-Path $PastaPrivada 'projeto-acoes/fila.md'
    if (-not (Test-Path -LiteralPath $fila)) {
        Write-Host "  ! não achei $fila; confira a pasta antes de seguir." -ForegroundColor Yellow
    }
    if ($SoMostrar) {
        Write-Host "  gravaria TICKERLAB_PASTA_PRIVADA = $PastaPrivada (variável de ambiente do usuário)"
    } elseif ($IsWindows) {
        [Environment]::SetEnvironmentVariable('TICKERLAB_PASTA_PRIVADA', $PastaPrivada, 'User')
        $env:TICKERLAB_PASTA_PRIVADA = $PastaPrivada
        Write-Host "  gravei TICKERLAB_PASTA_PRIVADA = $PastaPrivada"
    } else {
        Write-Host "  fora do Windows, ponha no perfil: `$env:TICKERLAB_PASTA_PRIVADA = '$PastaPrivada'"
    }
} else {
    Write-Host '  (sem -PastaPrivada: tl fila só funciona depois de definir TICKERLAB_PASTA_PRIVADA)'
}

Write-Host ''
Write-Host 'Depois: abra um PowerShell novo e digite tl.'
