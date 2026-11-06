# `tl fila`: quem trabalha agora e as próximas da fila única (projeto-acoes/fila.md, na pasta privada).

function Show-TlFila {
    <# Lista "Trabalhando agora" e as primeiras linhas da fila; -Tudo mostra a fila inteira. #>
    param([Parameter(Position = 0)][int]$Quantas = 8, [switch]$Tudo)
    $fila = Get-Fila
    if (-not $fila) {
        Write-Aviso ("Não achei a fila: defina a variável de ambiente {0} com a pasta privada (a que tem {1}). Veja docs/terminal.md." -f
            $script:VARIAVEL_DA_PASTA_PRIVADA, $script:ARQUIVO_DA_FILA)
        return
    }
    Write-Titulo ("Trabalhando agora: {0}/{1}" -f $fila.Trabalhando.Count, $script:TETO_DE_CONVERSAS)
    foreach ($linha in $fila.Trabalhando) {
        Write-Host ("  ● {0}" -f (Format-TextoCurto (Format-LinhaDaFila $linha) 110))
    }
    $proximas = if ($Tudo) { $fila.Fila } else { @($fila.Fila | Select-Object -First $Quantas) }
    $resto = if (-not $Tudo -and $fila.Fila.Count -gt $Quantas) { " (mostrando $Quantas; tl fila -Tudo)" } else { '' }
    Write-Host ''
    Write-Titulo ("Fila: {0} linhas{1}" -f $fila.Fila.Count, $resto)
    foreach ($linha in $proximas) {
        Write-Host ("  {0,3} {1}" -f (Get-NumeroDaFila $linha), (Format-TextoCurto (Format-LinhaDaFila $linha) 110))
    }
}

function Get-NumeroDaFila($Registro) {
    <# A coluna "#" da fila, ou vazio se a tabela não a tem. #>
    $coluna = $Registro.PSObject.Properties['#']
    if ($coluna) { [string]$coluna.Value } else { '' }
}
