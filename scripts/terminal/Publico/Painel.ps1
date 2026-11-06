# `tl ver`: uma tela com o estado de agora, para quem tem muitas conversas abertas não se perder.

function Show-TlPainel {
    <# Conversas abertas (app e terminal), cópias do repositório, PRs abertos com o CI e a fila única. #>
    param([int]$Conversas = 12)
    Write-Titulo ("TickerLab · painel · {0:dd/MM HH:mm}" -f (Get-Date))
    Show-SecaoDeConversas -Limite $Conversas
    Show-SecaoDeCopias
    Show-SecaoDePullRequests
    Show-SecaoDaFila
}

function Show-SecaoDeConversas([int]$Limite) {
    <# As que têm pergunta para você primeiro, depois as que trabalham, depois as paradas. #>
    $sessoes = @(Get-Sessoes | Sort-Object { $_.Situacao -ne 'pergunta' }, { $_.Situacao -ne 'trabalhando' }, Nome)
    $trabalhando = @($sessoes | Where-Object Situacao -eq 'trabalhando').Count
    $perguntando = @($sessoes | Where-Object Situacao -eq 'pergunta').Count
    Write-Host ''
    Write-Host ("Conversas abertas: {0} · {1} trabalhando · {2} com pergunta para você · teto {3}" -f
        $sessoes.Count, $trabalhando, $perguntando, $script:TETO_DE_CONVERSAS)
    foreach ($sessao in $sessoes | Select-Object -First $Limite) {
        $marca = switch ($sessao.Situacao) { 'trabalhando' { '●' } 'pergunta' { '?' } default { '○' } }
        $detalhe = if ($sessao.Esperando) { $sessao.Esperando } else { Format-Duracao $sessao.Minutos }
        Write-Host ("  {0} {1,-12} {2,-58} {3}" -f $marca, $sessao.Situacao, (Format-TextoCurto $sessao.Nome 58), $detalhe)
    }
    if ($sessoes.Count -gt $Limite) {
        Write-Host ("  … e mais {0} (tl ver -Conversas {1})" -f ($sessoes.Count - $Limite), $sessoes.Count)
    }
}

function Show-SecaoDeCopias {
    $copias = @(Get-Copias | Where-Object { $_.Ramo -and $_.Ramo -ne 'main' })
    $aviso = if ($copias.Count -gt $script:TETO_DE_COPIAS) {
        " (acima de $($script:TETO_DE_COPIAS), ADR 0101: veja tl limpar)"
    } else { '' }
    Write-Host ''
    Write-Host ("Cópias do repositório: {0}{1}" -f $copias.Count, $aviso)
}

function Show-SecaoDePullRequests {
    $prs = @(Get-PullRequests -Estado open)
    $verde = @($prs | Where-Object CI -eq '✓').Count
    $vermelho = @($prs | Where-Object CI -eq '✗').Count
    $rodando = @($prs | Where-Object CI -eq '…').Count
    Write-Host ''
    Write-Host ("PRs abertos: {0} · CI {1} ✓ · {2} ✗ · {3} …" -f $prs.Count, $verde, $vermelho, $rodando)
    foreach ($pr in $prs | Sort-Object Numero -Descending | Select-Object -First 8) {
        Write-Host ("  #{0,-4} {1,1} {2,-62} {3}" -f $pr.Numero, $pr.CI, (Format-TextoCurto $pr.Titulo 62), (Format-ExtrasDoPR $pr))
    }
    if ($prs.Count -gt 8) { Write-Host ("  … e mais {0} (tl pr)" -f ($prs.Count - 8)) }
}

function Format-ExtrasDoPR($PullRequest) {
    $extras = @()
    if ($PullRequest.Rascunho) { $extras += 'rascunho' }
    if ($PullRequest.AutoMerge) { $extras += 'auto-merge' }
    $extras -join ', '
}

function Show-SecaoDaFila {
    $fila = Get-Fila
    Write-Host ''
    if (-not $fila) {
        Write-Host ("Fila única: defina {0} para ver aqui (docs/terminal.md)." -f $script:VARIAVEL_DA_PASTA_PRIVADA)
        return
    }
    Write-Host ("Fila única: {0}/{1} trabalhando · {2} linhas na fila" -f
        $fila.Trabalhando.Count, $script:TETO_DE_CONVERSAS, $fila.Fila.Count)
    $proxima = $fila.Fila | Select-Object -First 1
    if ($proxima) { Write-Host ("  próxima: {0}" -f (Format-TextoCurto (Format-LinhaDaFila $proxima) 110)) }
}
