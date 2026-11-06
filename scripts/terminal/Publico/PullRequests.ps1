# `tl pr`: PRs abertos com o estado do CI; `tl pr <número>` mostra um e, com -Acompanhar, segue o CI até acabar
# (o lugar do Auto-fix do app para quem trabalha no terminal: AGENTS.md, "O PR é de quem abriu até o merge").

function Show-TlPullRequests {
    <# Sem número, lista os PRs abertos; com número, mostra o PR e as verificações dele. #>
    param([Parameter(Position = 0)][int]$Numero = 0, [switch]$Acompanhar)
    if ($Numero -gt 0) {
        Show-UmPullRequest -Numero $Numero -Acompanhar:$Acompanhar
        return
    }
    $prs = @(Get-PullRequests -Estado open)
    Write-Titulo ("PRs abertos: {0}" -f $prs.Count)
    foreach ($pr in $prs | Sort-Object Numero -Descending) {
        Write-Host ("  #{0,-4} {1,1} {2,-60} {3,-36} {4}" -f $pr.Numero, $pr.CI, (Format-TextoCurto $pr.Titulo 60),
            (Format-TextoCurto $pr.Ramo 36), (Format-ExtrasDoPR $pr))
    }
    Write-Host ''
    Write-Host '  CI: ✓ passou · ✗ falhou · … rodando · (vazio) sem verificação.   tl pr <número> [-Acompanhar]'
}

function Show-UmPullRequest([int]$Numero, [switch]$Acompanhar) {
    if (-not (Test-Ferramenta 'gh')) {
        Write-Aviso 'gh não está no PATH: não dá para ver o PR.'
        return
    }
    $repositorio = Get-NomeDoRepositorio
    & gh pr view $Numero --repo $repositorio
    if ($Acompanhar) {
        & gh pr checks $Numero --repo $repositorio --watch
    } else {
        & gh pr checks $Numero --repo $repositorio
    }
}
