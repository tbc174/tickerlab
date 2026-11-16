# Leitores: transformam texto (fila.md, `claude agents --json`, `git worktree list`, `gh pr list`) em objetos.
# As funções que recebem texto são puras e têm teste; as que chamam os programas só buscam o texto.

# --- fila.md ---------------------------------------------------------------------------------------------

function Read-TabelaMarkdown {
    <# Linhas da primeira tabela abaixo do título "## <Secao>", uma propriedade por coluna (vazio se não há). #>
    param([string]$Texto, [string]$Secao)
    $linhas = $Texto -split "`r?`n"
    $titulo = "^##\s+$([regex]::Escape($Secao))(\s|$)"
    $inicio = -1
    for ($i = 0; $i -lt $linhas.Count; $i++) {
        if ($linhas[$i] -match $titulo) { $inicio = $i; break }
    }
    if ($inicio -lt 0) { return @() }

    $cabecalho = $null
    $registros = @()
    for ($i = $inicio + 1; $i -lt $linhas.Count; $i++) {
        $linha = $linhas[$i]
        if ($linha -match '^##\s') { break }                                    # começou outra seção
        if ($linha -notmatch '^\s*\|') { if ($cabecalho) { break } else { continue } }
        if ($linha -match '^\s*\|\s*:?-{2,}') { continue }                       # |---|---| separa o cabeçalho
        $celulas = Split-CelulasDaTabela $linha
        if (-not $cabecalho) { $cabecalho = $celulas; continue }
        $registro = [ordered]@{}
        for ($c = 0; $c -lt $cabecalho.Count; $c++) {
            $registro[$cabecalho[$c]] = if ($c -lt $celulas.Count) { $celulas[$c] } else { '' }
        }
        $registros += [pscustomobject]$registro
    }
    return $registros
}

function Split-CelulasDaTabela([string]$Linha) {
    <# "| a | b \| c |" dá a e "b | c" (o \| é um pipe escapado dentro da célula). #>
    $partes = $Linha.Trim() -split '(?<!\\)\|'
    if ($partes.Count -lt 3) { return @() }
    # A linha começa e termina com |, então a primeira e a última parte são vazias.
    @($partes[1..($partes.Count - 2)] | ForEach-Object { ($_ -replace '\\\|', '|').Trim() })
}

function Read-Fila([string]$Texto) {
    <# Resumo do fila.md: quem trabalha agora e as próximas da fila, na ordem em que estão. #>
    [pscustomobject]@{
        Trabalhando = @(Read-TabelaMarkdown -Texto $Texto -Secao 'Trabalhando agora')
        Fila        = @(Read-TabelaMarkdown -Texto $Texto -Secao 'Fila')
    }
}

function Get-Fila {
    <# Lê o fila.md da pasta privada; $null quando ela não está configurada. #>
    $arquivo = Get-ArquivoDaFila
    if (-not $arquivo) { return $null }
    Read-Fila (Get-Content -LiteralPath $arquivo -Raw -Encoding utf8)
}

function Format-LinhaDaFila($Registro) {
    <# Uma linha curta de um registro da fila: conversa · mesa · item (as colunas que existirem). #>
    $nomes = @($Registro.PSObject.Properties.Name)
    $partes = foreach ($prefixo in 'Conversa', 'Mesa', 'Item') {
        $coluna = $nomes | Where-Object { $_ -like "$prefixo*" } | Select-Object -First 1
        if ($coluna) { $Registro.$coluna }
    }
    (@($partes) | Where-Object { $_ }) -join ' · '
}

function Format-TextoCurto([string]$Texto, [int]$Largura) {
    <# Corta o texto na largura, com … no fim; tira links do Markdown, negrito e quebras de linha. #>
    $limpo = ($Texto -replace '\[([^\]]*)\]\([^)]*\)', '$1' -replace '\*\*', '' -replace '\s+', ' ').Trim()
    if ($limpo.Length -le $Largura) { return $limpo }
    $limpo.Substring(0, [Math]::Max(0, $Largura - 1)) + '…'
}

function Format-Duracao([int]$Minutos) {
    <# 12 min, 3 h, 2 d. #>
    if ($Minutos -lt 60) { return "$Minutos min" }
    if ($Minutos -lt 1440) { return "$([int][Math]::Floor($Minutos / 60)) h" }
    return "$([int][Math]::Floor($Minutos / 1440)) d"
}

# --- conversas abertas (claude agents --json) --------------------------------------------------------------

$script:ROTULOS_DE_SITUACAO = @{ busy = 'trabalhando'; idle = 'parada'; waiting = 'pergunta' }

function Read-Sessoes([string]$Json) {
    <# Conversas do `claude agents --json` (app e terminal) como objetos: Nome, Mesa, Situacao, Esperando,
       Minutos desde que abriu, Pasta e Tipo. #>
    if ([string]::IsNullOrWhiteSpace($Json)) { return @() }
    $agora = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
    @($Json | ConvertFrom-Json | ForEach-Object {
        $propriedades = $_.PSObject.Properties
        $nome = if ($propriedades['name'] -and $_.name) { [string]$_.name } else { '(sem nome)' }
        $inicio = if ($propriedades['startedAt'] -and $_.startedAt) { [double]$_.startedAt } else { $agora }
        $situacao = [string]$_.status
        [pscustomobject]@{
            Nome      = $nome
            Mesa      = Get-MesaDoNome $nome
            Situacao  = if ($script:ROTULOS_DE_SITUACAO.ContainsKey($situacao)) { $script:ROTULOS_DE_SITUACAO[$situacao] } else { $situacao }
            Esperando = if ($propriedades['waitingFor']) { [string]$_.waitingFor } else { '' }
            Minutos   = [int][Math]::Max(0, ($agora - $inicio) / 60000)
            Pasta     = if ($propriedades['cwd'] -and $_.cwd) { Split-Path -Leaf ([string]$_.cwd) } else { '' }
            Tipo      = if ($propriedades['kind']) { [string]$_.kind } else { '' }
            Id        = if ($propriedades['sessionId']) { [string]$_.sessionId } else { '' }
        }
    })
}

function Get-Sessoes {
    <# Conversas abertas agora (app e terminal). Vazio, com aviso, se o claude não está no PATH. #>
    if (-not (Test-Ferramenta 'claude')) {
        Write-Aviso 'claude não está no PATH: não dá para listar as conversas.'
        return @()
    }
    $json = (& claude agents --json 2>$null) -join "`n"
    Read-Sessoes $json
}

# --- cópias do repositório (git worktree) ------------------------------------------------------------------

function Read-Copias([string[]]$LinhasPorcelain) {
    <# Saída de `git worktree list --porcelain` em objetos Pasta, Nome (a última pasta do caminho) e Ramo. #>
    $copias = @()
    $atual = $null
    foreach ($linha in @($LinhasPorcelain) + @('')) {
        if ($linha -like 'worktree *') {
            $atual = [ordered]@{ Pasta = $linha.Substring(9); Ramo = '' }
        } elseif ($linha -like 'branch *' -and $atual) {
            $atual.Ramo = $linha.Substring(7) -replace '^refs/heads/', ''
        } elseif ($linha -eq '' -and $atual) {
            $atual.Nome = Split-Path -Leaf $atual.Pasta
            $copias += [pscustomobject]$atual
            $atual = $null
        }
    }
    return $copias
}

function Get-Copias {
    <# As cópias do repositório, lidas do git. #>
    Read-Copias @(& git -C $script:RaizDoRepositorio worktree list --porcelain)
}

# --- pull requests (gh) ----------------------------------------------------------------------------------

function Get-ResumoDoCI($Verificacoes) {
    <# ✓ tudo passou, ✗ algo falhou, … ainda rodando, vazio sem verificação. #>
    $lista = @($Verificacoes | Where-Object { $null -ne $_ })
    if ($lista.Count -eq 0) { return '' }
    $estados = @($lista | ForEach-Object { [string]($_.conclusion ?? $_.state ?? $_.status) })
    $ruins = @('FAILURE', 'ERROR', 'TIMED_OUT', 'CANCELLED', 'ACTION_REQUIRED', 'STARTUP_FAILURE')
    $rodando = @('', 'PENDING', 'IN_PROGRESS', 'QUEUED', 'EXPECTED', 'WAITING', 'REQUESTED')
    if (@($estados | Where-Object { $_ -in $ruins }).Count -gt 0) { return '✗' }
    if (@($estados | Where-Object { $_ -in $rodando }).Count -gt 0) { return '…' }
    return '✓'
}

function Read-PullRequests([string]$Json) {
    <# `gh pr list --json ...` em objetos Numero, Titulo, Ramo, CI, Rascunho, AutoMerge e MescladoEm. #>
    if ([string]::IsNullOrWhiteSpace($Json)) { return @() }
    @($Json | ConvertFrom-Json | ForEach-Object {
        [pscustomobject]@{
            Numero     = [int]$_.number
            Titulo     = [string]$_.title
            Ramo       = [string]$_.headRefName
            CI         = Get-ResumoDoCI $_.statusCheckRollup
            Rascunho   = [bool]$_.isDraft
            AutoMerge  = $null -ne $_.autoMergeRequest
            MescladoEm = if ($_.mergedAt) { [datetime]$_.mergedAt } else { $null }
        }
    })
}

function Get-PullRequests {
    <# PRs do repositório (abertos por padrão) pelo gh; vazio, com aviso, se o gh não está no PATH. #>
    param([string]$Estado = 'open', [int]$Limite = 50)
    if (-not (Test-Ferramenta 'gh')) {
        Write-Aviso 'gh não está no PATH: não dá para listar os PRs.'
        return @()
    }
    $campos = 'number,title,headRefName,statusCheckRollup,isDraft,autoMergeRequest,mergedAt'
    $json = (& gh pr list --repo (Get-NomeDoRepositorio) --state $Estado --limit $Limite --json $campos 2>$null) -join "`n"
    Read-PullRequests $json
}

# --- cópias de PR já mesclado ----------------------------------------------------------------------------

function Find-CopiasMescladas {
    <# Cópias cujo PR foi mesclado, cada uma com os motivos para ainda não apagar (merge recente, conversa
       aberta parecida). O estado do git (mudança não salva, commit não enviado) entra depois, em Limpeza. #>
    param($Copias, $PullRequestsMesclados, $Sessoes, [datetime]$Agora = (Get-Date))
    # O gh lista do mais novo para o mais velho: se um ramo teve dois PRs, vale o mais novo.
    $porRamo = @{}
    foreach ($pr in @($PullRequestsMesclados)) {
        if (-not $porRamo.ContainsKey($pr.Ramo)) { $porRamo[$pr.Ramo] = $pr }
    }
    foreach ($copia in @($Copias)) {
        if (-not $copia.Ramo -or $copia.Ramo -eq 'main' -or -not $porRamo.ContainsKey($copia.Ramo)) { continue }
        $pr = $porRamo[$copia.Ramo]
        $motivos = @()
        if ($pr.MescladoEm -and ($Agora - $pr.MescladoEm).TotalHours -lt $script:HORAS_DE_SOSSEGO_APOS_O_MERGE) {
            $motivos += "mesclado há menos de $($script:HORAS_DE_SOSSEGO_APOS_O_MERGE) h"
        }
        $viva = @($Sessoes | Where-Object { Test-NomesParecidos $_.Nome $copia.Nome }) | Select-Object -First 1
        if ($viva) { $motivos += "conversa aberta parecida: $($viva.Nome)" }
        [pscustomobject]@{
            Pasta = $copia.Pasta; Nome = $copia.Nome; Ramo = $copia.Ramo
            PR = $pr.Numero; MescladoEm = $pr.MescladoEm; Motivos = @($motivos)
        }
    }
}
