# `tl`: a porta de entrada. `tl` sozinho mostra o painel; `tl <comando> ...` chama a função do comando.

$script:COMANDOS = [ordered]@{
    ver     = @{ Funcao = 'Show-TlPainel';         Ajuda = 'painel: conversas abertas, cópias do repositório, PRs e fila' }
    nova    = @{ Funcao = 'New-TlConversa';        Ajuda = 'abre uma conversa numa cópia própria: tl nova <Mesa> "<tarefa>" [-Modelo sonnet|opus|fable] [-Ramo feat|fix|docs|test|perf|ci|chore] [-Passagem arquivo.md] [-Permissao plan|acceptEdits|auto] [-SemCopia] [-SoMostrar]' }
    fila    = @{ Funcao = 'Show-TlFila';           Ajuda = 'quem trabalha agora e as próximas da fila única: tl fila [-Quantas 8] [-Tudo]' }
    pr      = @{ Funcao = 'Show-TlPullRequests';   Ajuda = 'PRs abertos com o CI; tl pr <número> [-Acompanhar] segue o CI de um até acabar' }
    limpar  = @{ Funcao = 'Get-TlCopiasMescladas'; Ajuda = 'cópias de PR já mesclado; tl limpar -Apagar [-SoMostrar] remove as que estão seguras' }
    celular = @{ Funcao = 'Start-TlCelular';       Ajuda = 'Remote Control: comanda este PC pelo app do celular ou pelo claude.ai/code' }
    ajuda   = @{ Funcao = 'Show-TlAjuda';          Ajuda = 'esta lista' }
}

function tl {
    # Sem bloco param de propósito: assim "-Modelo sonnet" chega em $args como texto e ConvertTo-Parametros
    # decide o que é posicional e o que é nomeado, sem o PowerShell reclamar de parâmetro desconhecido.
    $comando = if ($args.Count -gt 0) { [string]$args[0] } else { 'ver' }
    if ($comando -in @('-h', '--help', '-?', 'help')) { $comando = 'ajuda' }
    if (-not $script:COMANDOS.Contains($comando)) {
        Write-Aviso "Não conheço 'tl $comando'."
        Show-TlAjuda
        return
    }
    $resto = if ($args.Count -gt 1) { [string[]]$args[1..($args.Count - 1)] } else { [string[]]@() }
    $parametros = ConvertTo-Parametros $resto
    $posicionais = $parametros.Posicionais
    $nomeados = $parametros.Nomeados
    $funcao = $script:COMANDOS[$comando].Funcao
    if ($comando -eq 'limpar' -and $nomeados.ContainsKey('Apagar')) {
        $funcao = 'Remove-TlCopiasMescladas'
        $nomeados.Remove('Apagar')
    }
    & $funcao @posicionais @nomeados
}

function Show-TlAjuda {
    <# Lista os comandos do painel e as mesas. #>
    Write-Titulo 'tl: o TickerLab no terminal'
    foreach ($nome in $script:COMANDOS.Keys) {
        Write-Host ("  tl {0,-8} {1}" -f $nome, $script:COMANDOS[$nome].Ajuda)
    }
    Write-Host ''
    Write-Host ('  Mesas: ' + (($script:MESAS.Values | ForEach-Object { "$($_.Emoji) $($_.Nome)" }) -join '   '))
    Write-Host '  Mais em docs/terminal.md.'
}
