#Requires -Version 7
<#
.SYNOPSIS
    Abre o Claude Code com a cara do TickerLab: a única fonte da linha de comando do `claude` no terminal.
.DESCRIPTION
    Sem parâmetros, roda o `claude` na pasta atual, no modo de permissão do app (auto) e com as configurações só do
    terminal (claude-terminal.json: estilo de saída "TickerLab" e os verbos do giro). É o comando do perfil
    "TickerLab" do Windows Terminal (python -m scripts.terminal.perfil_windows_terminal).

    -NovaAba abre outra aba da janela "tickerlab" do Windows Terminal, no perfil TickerLab, na pasta pedida e com o
    nome "Mesa · tarefa": o equivalente do start_session do app para quem trabalha no terminal.
    -SoMostrar só imprime o comando que rodaria.
.PARAMETER Pasta
    Pasta em que o claude abre (a cópia da tarefa). Padrão: a pasta atual.
.PARAMETER Nome
    Nome da conversa (claude --name), "Mesa · tarefa" como no app: aparece no /resume, no título da aba e na linha
    de status.
.PARAMETER Prompt
    Arquivo com o prompt de abertura (a passagem da tarefa). Vai como a primeira mensagem da conversa.
.PARAMETER Resto
    Qualquer outro argumento vai direto ao claude (por exemplo --resume, --model opus).
.EXAMPLE
    .\scripts\terminal\claude-tickerlab.ps1
.EXAMPLE
    .\scripts\terminal\claude-tickerlab.ps1 -NovaAba -Pasta ..\analise-acoes-dados-coleta -Nome 'Dados · coleta nova' -Prompt ..\passagem.md
#>
[CmdletBinding()]
param(
    [switch]$NovaAba,
    [string]$Pasta = (Get-Location).Path,
    [string]$Nome,
    [string]$Prompt,
    [switch]$SoMostrar,
    [Parameter(ValueFromRemainingArguments)] [string[]]$Resto = @()
)

$ErrorActionPreference = 'Stop'
$ConfiguracaoDoTerminal = Join-Path $PSScriptRoot 'claude-terminal.json'
$ModoDePermissao = 'auto'       # o mesmo do app: o classificador decide, com as regras autoMode de ~/.claude/settings.json
$NomeDoPerfil = 'TickerLab'      # perfil do Windows Terminal (perfil_windows_terminal.py)
$JanelaDoTerminal = 'tickerlab'  # todas as conversas do TickerLab na mesma janela, uma aba cada

function Get-ArgumentosDoClaude {
    $argumentos = @('--permission-mode', $ModoDePermissao, '--settings', $ConfiguracaoDoTerminal)
    if ($Nome) { $argumentos += @('--name', $Nome) }
    $argumentos += $Resto
    if ($Prompt) { $argumentos += (Get-Content -LiteralPath $Prompt -Raw -Encoding utf8).Trim() }
    return $argumentos
}

function Get-ArgumentosDaAba {
    <# A aba roda este mesmo script (com -NoExit, para o terminal ficar aberto quando o claude fechar). O título
       fica "Mesa · tarefa" mesmo que o claude mude o título da janela (--suppressApplicationTitle). #>
    $pastaCompleta = (Resolve-Path -LiteralPath $Pasta).Path
    $lancador = @('pwsh', '-NoLogo', '-NoExit', '-File', $PSCommandPath)
    if ($Nome) { $lancador += @('-Nome', $Nome) }
    if ($Prompt) { $lancador += @('-Prompt', (Resolve-Path -LiteralPath $Prompt).Path) }
    $lancador += $Resto
    $titulo = if ($Nome) { $Nome } else { $NomeDoPerfil }
    $aba = @('-w', $JanelaDoTerminal, 'nt', '-p', $NomeDoPerfil, '-d', $pastaCompleta, '--title', $titulo, '--suppressApplicationTitle')
    return $aba + $lancador
}

function Format-Comando([string]$Programa, [string[]]$Argumentos) {
    <# O comando como texto, para -SoMostrar: argumento com espaço ou aspas vai entre aspas. #>
    $partes = @($Programa) + @($Argumentos | ForEach-Object {
        if ($_ -match '[\s"]') { '"' + ($_ -replace '"', '\"') + '"' } else { $_ }
    })
    return $partes -join ' '
}

if ($NovaAba) {
    $argumentos = Get-ArgumentosDaAba
    if ($SoMostrar) { Format-Comando 'wt' $argumentos; return }
    & wt @argumentos
    return
}

$argumentos = Get-ArgumentosDoClaude
if ($SoMostrar) { Format-Comando 'claude' $argumentos; return }
Set-Location -LiteralPath $Pasta
& claude @argumentos
