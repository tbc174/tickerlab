#Requires -Version 7.0
<#
.SYNOPSIS
Instala o painel `tl` no perfil do PowerShell e, se pedido, grava a pasta privada na variável de ambiente.

.DESCRIPTION
Acrescenta uma linha Import-Module ao perfil do usuário (todas as janelas: $PROFILE.CurrentUserAllHosts), importa o
módulo já na janela em que rodou e, com -PastaPrivada, grava TICKERLAB_PASTA_PRIVADA nas variáveis do usuário, para
`tl fila` achar o fila.md. Com -SoMostrar, só diz o que faria. Rode de novo se mover o repositório: a linha do perfil
é atualizada. As outras janelas já abertas carregaram o perfil antes da linha: só veem o tl depois de reabertas.

.PARAMETER Perfil
Arquivo de perfil a editar. Padrão: o do usuário para todas as janelas do PowerShell 7 ($PROFILE.CurrentUserAllHosts);
os testes apontam para um arquivo temporário.

.EXAMPLE
.\scripts\terminal\instalar.ps1 -SoMostrar
.\scripts\terminal\instalar.ps1 -PastaPrivada 'C:\caminho\da\pasta-privada'
#>
param([string]$PastaPrivada, [switch]$SoMostrar, [string]$Perfil = $PROFILE.CurrentUserAllHosts)

$manifesto = Join-Path $PSScriptRoot 'TickerLab.psd1'
$marca = '# TickerLab: painel do terminal (tl)'
$linhaNova = "Import-Module '$manifesto'  $marca"

Write-Host "Perfil do PowerShell: $Perfil"
$linhas = if (Test-Path -LiteralPath $Perfil) { @(Get-Content -LiteralPath $Perfil -Encoding utf8) } else { @() }
$linhaAtual = $linhas | Where-Object { $_.Contains($marca) } | Select-Object -First 1
if ($linhaAtual -eq $linhaNova) {
    Write-Host '  já importa o módulo: nada a fazer.'
} elseif ($SoMostrar) {
    Write-Host ("  {0}: {1}" -f ($(if ($linhaAtual) { 'trocaria a linha por' } else { 'acrescentaria' })), $linhaNova)
} elseif ($linhaAtual) {
    $novas = $linhas | ForEach-Object { if ($_ -eq $linhaAtual) { $linhaNova } else { $_ } }
    Set-Content -LiteralPath $Perfil -Value $novas -Encoding utf8
    Write-Host "  atualizei a linha: $linhaNova"
} else {
    New-Item -ItemType Directory -Path (Split-Path -Parent $Perfil) -Force | Out-Null
    Add-Content -LiteralPath $Perfil -Value $linhaNova -Encoding utf8
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
if ($SoMostrar) {
    Write-Host 'Só mostrando: nada mudou.'
} else {
    # Sem isto o tl só apareceria na próxima janela: esta já tinha carregado o perfil sem a linha.
    Import-Module $manifesto -Force -Global
    Write-Host 'O tl já funciona nesta janela. As outras janelas do PowerShell 7 já abertas (o painel Terminal do app do'
    Write-Host 'Claude Code também) carregaram o perfil antes da linha: abra uma janela nova ou rode nelas'
    Write-Host '  . $PROFILE.CurrentUserAllHosts'
    Write-Host 'No Windows PowerShell 5.1 (powershell.exe) o tl não existe: use o PowerShell 7 (pwsh).'
}
