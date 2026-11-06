#Requires -Version 7.0
<#
.SYNOPSIS
Instala o painel `tl` nos perfis do PowerShell e, se pedido, grava a pasta privada na variável de ambiente.

.DESCRIPTION
Acrescenta uma linha Import-Module ao perfil do usuário do PowerShell 7 (todas as janelas: $PROFILE.CurrentUserAllHosts)
e importa o módulo já na janela em que rodou. No Windows, acrescenta ao perfil do Windows PowerShell 5.1 (o azul, que o
Windows abre por padrão) uma linha que carrega a ponte ponte-windows-powershell.ps1: um `tl` que roda cada comando num
pwsh, porque o módulo exige o PowerShell 7. Com -PastaPrivada, grava TICKERLAB_PASTA_PRIVADA nas variáveis do usuário,
para `tl fila` achar o fila.md. Com -SoMostrar, só diz o que faria. Rode de novo se mover o repositório: as linhas dos
perfis são atualizadas. As outras janelas já abertas carregaram o perfil antes da linha: só veem o tl depois de reabertas.

.PARAMETER Perfil
Perfil do PowerShell 7 a editar. Padrão: o do usuário para todas as janelas ($PROFILE.CurrentUserAllHosts); os testes
apontam para um arquivo temporário.

.PARAMETER PerfilAntigo
Perfil do Windows PowerShell 5.1 a editar. Padrão: o do usuário para todas as janelas (Documentos\WindowsPowerShell\
profile.ps1); vazio fora do Windows, onde o 5.1 não existe. Os testes apontam para um arquivo temporário.

.EXAMPLE
.\scripts\terminal\instalar.ps1 -SoMostrar
.\scripts\terminal\instalar.ps1 -PastaPrivada 'C:\caminho\da\pasta-privada'
#>
param(
    [string]$PastaPrivada,
    [switch]$SoMostrar,
    [string]$Perfil = $PROFILE.CurrentUserAllHosts,
    [string]$PerfilAntigo = $(if ($IsWindows) { Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'WindowsPowerShell\profile.ps1' } else { '' })
)

$manifesto = Join-Path $PSScriptRoot 'TickerLab.psd1'
$ponte = Join-Path $PSScriptRoot 'ponte-windows-powershell.ps1'
$marca = '# TickerLab: painel do terminal (tl)'

function Set-LinhaDoPerfil([string]$Titulo, [string]$Caminho, [string]$Linha) {
    <# Deixa no perfil $Caminho exatamente uma $Linha com a $marca: acrescenta, troca a antiga ou não faz nada. #>
    Write-Host "${Titulo}: $Caminho"
    $linhas = if (Test-Path -LiteralPath $Caminho) { @(Get-Content -LiteralPath $Caminho -Encoding utf8) } else { @() }
    $linhaAtual = $linhas | Where-Object { $_.Contains($marca) } | Select-Object -First 1
    if ($linhaAtual -eq $Linha) {
        Write-Host '  já tem a linha: nada a fazer.'
    } elseif ($SoMostrar) {
        Write-Host ("  {0}: {1}" -f ($(if ($linhaAtual) { 'trocaria a linha por' } else { 'acrescentaria' })), $Linha)
    } elseif ($linhaAtual) {
        $novas = $linhas | ForEach-Object { if ($_ -eq $linhaAtual) { $Linha } else { $_ } }
        Set-Content -LiteralPath $Caminho -Value $novas -Encoding utf8
        Write-Host "  atualizei a linha: $Linha"
    } else {
        New-Item -ItemType Directory -Path (Split-Path -Parent $Caminho) -Force | Out-Null
        Add-Content -LiteralPath $Caminho -Value $Linha -Encoding utf8
        Write-Host "  acrescentei: $Linha"
    }
}

Set-LinhaDoPerfil 'Perfil do PowerShell 7' $Perfil "Import-Module '$manifesto'  $marca"
if ($PerfilAntigo) {
    Set-LinhaDoPerfil 'Perfil do Windows PowerShell 5.1' $PerfilAntigo ". '$ponte'  $marca"
} else {
    Write-Host 'Perfil do Windows PowerShell 5.1: não há (fora do Windows), nada a fazer.'
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
    Write-Host 'O tl já funciona nesta janela. As outras janelas já abertas (PowerShell 7, Windows PowerShell 5.1 e o painel'
    Write-Host 'Terminal do app do Claude Code) carregaram o perfil antes da linha: abra uma janela nova ou rode nelas'
    Write-Host '  . $PROFILE.CurrentUserAllHosts'
    Write-Host 'No Windows PowerShell 5.1 (o azul, powershell.exe) o tl passa pela ponte: cada comando roda num pwsh.'
}
