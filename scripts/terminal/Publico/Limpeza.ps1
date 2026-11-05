# `tl limpar`: cópias do repositório cujo PR já foi mesclado (ADR 0101: acima de 10 cópias, apague-as).
# Só lista por padrão; `tl limpar -Apagar` remove as que estão seguras: merge há mais de 2 h, nenhuma conversa
# aberta parecida, nenhum PR aberto no mesmo ramo e o git da cópia limpo (nada por salvar nem por enviar).

function Get-TlCopiasMescladas {
    <# Lista as cópias de PR mesclado e diz, para cada uma, se está segura ou por que esperar. #>
    $copias = @(Get-Copias | Where-Object { $_.Ramo -and $_.Ramo -ne 'main' })
    $candidatas = @(Get-CandidatasALimpeza)
    Write-Titulo ("Cópias do repositório: {0} (teto {1}, ADR 0101) · de PR mesclado: {2}" -f
        $copias.Count, $script:TETO_DE_COPIAS, $candidatas.Count)
    if ($candidatas.Count -eq 0) {
        Write-Host '  nenhuma cópia de PR mesclado para apagar.'
        return
    }
    foreach ($candidata in $candidatas) {
        $estado = if ($candidata.Motivos.Count -eq 0) { 'segura' } else { 'espere: ' + ($candidata.Motivos -join '; ') }
        Write-Host ("  {0,-46} PR #{1,-4} {2}" -f (Format-TextoCurto $candidata.Nome 46), $candidata.PR, $estado)
    }
    $seguras = @($candidatas | Where-Object { $_.Motivos.Count -eq 0 }).Count
    Write-Host ''
    if ($seguras -gt 0) {
        Write-Host ("  {0} segura(s): tl limpar -Apagar remove a pasta e o ramo local (o PR e a main ficam)." -f $seguras)
    } else {
        Write-Host '  nenhuma segura agora.'
    }
}

function Remove-TlCopiasMescladas {
    <# Apaga as cópias seguras (git worktree remove e git branch -D). Com -SoMostrar, só lista os comandos. #>
    param([switch]$SoMostrar)
    $seguras = @(Get-CandidatasALimpeza | Where-Object { $_.Motivos.Count -eq 0 })
    if ($seguras.Count -eq 0) {
        Write-Host 'Nenhuma cópia segura para apagar agora (tl limpar mostra o porquê).'
        return
    }
    $apagadas = 0
    foreach ($copia in $seguras) {
        Write-Host ("  git worktree remove '{0}'  e  git branch -D {1}   (PR #{2})" -f $copia.Pasta, $copia.Ramo, $copia.PR)
        if ($SoMostrar) { continue }
        & git -C $script:RaizDoRepositorio worktree remove $copia.Pasta
        if ($LASTEXITCODE -ne 0) {
            Write-Aviso "não consegui remover $($copia.Pasta); deixei o ramo."
            continue
        }
        & git -C $script:RaizDoRepositorio branch -D $copia.Ramo
        $apagadas++
    }
    if ($SoMostrar) { Write-Host '  (só mostrando: nada foi apagado)' } else { Write-Host ("  {0} cópia(s) apagada(s)." -f $apagadas) }
}

function Get-CandidatasALimpeza {
    <# Cópias de PR mesclado com todos os motivos para esperar: conversa parecida e merge recente (Find-CopiasMescladas),
       PR aberto no mesmo ramo e o estado do git da cópia. #>
    $copias = @(Get-Copias)
    $mesclados = @(Get-PullRequests -Estado merged -Limite 200)
    $abertos = @(Get-PullRequests -Estado open)
    $sessoes = @(Get-Sessoes)
    foreach ($candidata in @(Find-CopiasMescladas -Copias $copias -PullRequestsMesclados $mesclados -Sessoes $sessoes)) {
        $motivos = @($candidata.Motivos)
        $aberto = $abertos | Where-Object Ramo -eq $candidata.Ramo | Select-Object -First 1
        if ($aberto) { $motivos += "PR aberto #$($aberto.Numero) no mesmo ramo" }
        $motivos += @(Get-MotivosDoGit -Pasta $candidata.Pasta -Ramo $candidata.Ramo -MescladoEm $candidata.MescladoEm)
        $candidata.Motivos = @($motivos)
        $candidata
    }
}

function Get-MotivosDoGit([string]$Pasta, [string]$Ramo, $MescladoEm) {
    <# O que o git da cópia diz contra apagar: mudança não salva, arquivo não versionado, commit não enviado
       (quando o ramo ainda existe no remoto) e commit feito depois do merge. #>
    $motivos = @()
    $status = @(& git -C $Pasta status --porcelain 2>$null)
    if (@($status | Where-Object { $_ -notmatch '^\?\?' }).Count -gt 0) { $motivos += 'mudança não salva' }
    if (@($status | Where-Object { $_ -match '^\?\?' }).Count -gt 0) { $motivos += 'arquivo não versionado' }
    & git -C $Pasta rev-parse --verify --quiet "origin/$Ramo" *> $null
    if ($LASTEXITCODE -eq 0 -and @(& git -C $Pasta log --oneline "origin/$Ramo..$Ramo" 2>$null).Count -gt 0) {
        $motivos += 'commit não enviado'
    }
    $ultimoCommit = [string](@(& git -C $Pasta log -1 --format=%cI $Ramo 2>$null) | Select-Object -First 1)
    if ($MescladoEm -and $ultimoCommit -and ([datetime]$ultimoCommit) -gt $MescladoEm) { $motivos += 'commit depois do merge' }
    return $motivos
}
