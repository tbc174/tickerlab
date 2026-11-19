# `tl nova`: abre uma conversa do Claude Code numa cópia própria do repositório, numa aba da janela "tickerlab"
# do Windows Terminal, com o título "Mesa · tarefa", a cor da mesa e o prompt de abertura já escrito.

function New-TlConversa {
    <# Cria a cópia (git worktree) e o ramo a partir de origin/main, grava o prompt e o script da aba fora do
       repositório e abre a aba. Com -SoMostrar, só diz o que faria. Com -SemCopia, abre na pasta principal. #>
    [CmdletBinding()]
    param(
        [Parameter(Position = 0)][string]$Mesa,
        [Parameter(Position = 1)][string]$Tarefa,
        [string]$Modelo = $script:MODELO_PADRAO,
        [string]$Ramo = 'feat',
        [string]$Passagem = '',
        [string]$Permissao = 'default',
        [switch]$SemCopia,
        [switch]$SoMostrar
    )
    $pedido = @{
        Mesa = $Mesa; Tarefa = $Tarefa; Modelo = $Modelo; TipoDeRamo = $Ramo
        Passagem = $Passagem; Permissao = $Permissao; SemCopia = [bool]$SemCopia
    }
    $plano = Get-PlanoDaConversa $pedido
    Show-PlanoDaConversa $plano
    Show-AvisosDeTeto -Mesa $plano.Mesa.Nome
    if ($SoMostrar) {
        Write-Host '  (só mostrando: nada foi criado nem aberto)'
        return
    }
    if ($plano.Ramo) { New-CopiaDoRepositorio -Pasta $plano.Pasta -Ramo $plano.Ramo }
    Write-ArquivosDoLancador $plano
    Start-AbaDoTerminal $plano
    Write-Host ''
    Write-Host ("Conversa '{0}' aberta na janela '{1}' do Windows Terminal." -f $plano.Titulo, $script:JANELA_DO_TERMINAL)
    Write-Host ("Fechou a aba? Na pasta da cópia: claude --resume '{0}'" -f $plano.Titulo)
}

function Assert-PedidoValido($Pedido) {
    <# Erros claros antes de qualquer efeito: uso, modelo e modo de permissão (a mesa e o ramo erram sozinhos). #>
    if ([string]::IsNullOrWhiteSpace($Pedido.Mesa) -or [string]::IsNullOrWhiteSpace($Pedido.Tarefa)) {
        throw ('Uso: tl nova <Mesa> "<tarefa>" [-Modelo sonnet|opus|fable] [-Ramo feat|fix|docs|test|perf|ci|chore] ' +
            '[-Passagem arquivo.md] [-Permissao plan|acceptEdits|auto] [-SemCopia] [-SoMostrar]')
    }
    if ($Pedido.Modelo -notin $script:MODELOS) {
        throw "Modelo desconhecido: '$($Pedido.Modelo)'. Use um de: $($script:MODELOS -join ', ')."
    }
    if ($Pedido.Permissao -notin $script:MODOS_DE_PERMISSAO) {
        throw ("Modo de permissão desconhecido: '$($Pedido.Permissao)'. Use um de: $($script:MODOS_DE_PERMISSAO -join ', ') " +
            '(pular as permissões não entra aqui, de propósito).')
    }
}

function Resolve-Passagem([string]$Passagem) {
    <# Caminho completo da passagem: como foi digitado, ou dentro da pasta privada; erro se não existe. #>
    if (-not $Passagem) { return '' }
    if (Test-Path -LiteralPath $Passagem -PathType Leaf) { return (Resolve-Path -LiteralPath $Passagem).Path }
    $privada = Get-PastaPrivada
    if ($privada) {
        $naPrivada = Join-Path $privada $Passagem
        if (Test-Path -LiteralPath $naPrivada -PathType Leaf) { return (Resolve-Path -LiteralPath $naPrivada).Path }
    }
    throw "Não achei a passagem '$Passagem' (nem na pasta privada)."
}

function Get-PlanoDaConversa($Pedido) {
    <# Tudo o que `tl nova` vai fazer, calculado antes de tocar em qualquer coisa: é o que -SoMostrar imprime. #>
    Assert-PedidoValido $Pedido
    $mesa = Resolve-Mesa $Pedido.Mesa
    $titulo = Get-TituloDaConversa $Pedido.Mesa $Pedido.Tarefa
    $nome = Get-NomeDaCopia $Pedido.Mesa $Pedido.Tarefa
    $pasta = if ($Pedido.SemCopia) { $script:RaizDoRepositorio } else { Join-Path (Get-PastaDasCopias) $nome }
    $ramo = if ($Pedido.SemCopia) { '' } else { Get-NomeDoRamo $Pedido.TipoDeRamo $Pedido.Tarefa }
    $passagem = Resolve-Passagem $Pedido.Passagem
    $pastaDoLancador = Join-Path (Get-PastaDosLancadores) $nome
    [pscustomobject]@{
        Mesa               = $mesa
        Titulo             = $titulo
        Nome               = $nome
        Pasta              = $pasta
        Ramo               = $ramo
        Modelo             = $Pedido.Modelo
        Permissao          = $Pedido.Permissao
        Passagem           = $passagem
        PastaDoLancador    = $pastaDoLancador
        ArquivoDoPrompt    = Join-Path $pastaDoLancador 'prompt.md'
        Lancador           = Join-Path $pastaDoLancador 'abrir.ps1'
        Prompt             = Get-PromptDeAbertura -Mesa $mesa.Nome -Tarefa $Pedido.Tarefa -Copia $pasta -Ramo $ramo -Passagem $passagem
        ArgumentosDoClaude = Get-ArgumentosDoClaude -Nome $titulo -Modelo $Pedido.Modelo -ModoDePermissao $Pedido.Permissao
    }
}

function Show-PlanoDaConversa($Plano) {
    Write-Titulo ("{0} {1}" -f $Plano.Mesa.Emoji, $Plano.Titulo)
    Write-Host ("  cópia:     {0}" -f $Plano.Pasta)
    if ($Plano.Ramo) {
        Write-Host ("  ramo:      {0} (git worktree add, a partir de origin/main)" -f $Plano.Ramo)
    } else {
        Write-Host '  ramo:      nenhum (-SemCopia: a conversa abre na pasta principal)'
    }
    Write-Host ("  modelo:    {0} · permissão: {1}" -f $Plano.Modelo, $Plano.Permissao)
    $passagem = if ($Plano.Passagem) { $Plano.Passagem } else { 'nenhuma (a conversa escreve a sua)' }
    Write-Host ("  passagem:  {0}" -f $passagem)
    Write-Host ("  comando:   {0}" -f (ConvertTo-LinhaDeComando 'claude' (@($Plano.ArgumentosDoClaude) + @('<prompt>'))))
    Write-Host ("  aba:       janela '{0}' do Windows Terminal, cor {1}" -f $script:JANELA_DO_TERMINAL, $Plano.Mesa.Cor)
    Write-Host ("  lançador:  {0}" -f $Plano.Lancador)
}

function Show-AvisosDeTeto([string]$Mesa) {
    <# Avisa (sem impedir) quando a conversa nova passa dos tetos da fila única ou da ADR 0101. #>
    $sessoes = @(Get-Sessoes)
    if ($sessoes.Count -ge $script:TETO_DE_CONVERSAS) {
        Write-Aviso ("Já há {0} conversas abertas (teto {1}): feche uma antes, ou siga por sua conta." -f
            $sessoes.Count, $script:TETO_DE_CONVERSAS)
    }
    $daMesa = @($sessoes | Where-Object Mesa -eq $Mesa).Count
    if ($daMesa -ge $script:TETO_POR_MESA) {
        Write-Aviso ("A mesa {0} já tem {1} conversas abertas (teto {2} por mesa)." -f $Mesa, $daMesa, $script:TETO_POR_MESA)
    }
    $copias = @(Get-Copias | Where-Object { $_.Ramo -and $_.Ramo -ne 'main' }).Count
    if ($copias -ge $script:TETO_DE_COPIAS) {
        Write-Aviso ("Já há {0} cópias do repositório (ADR 0101: acima de {1}, apague as de PR mesclado: tl limpar)." -f
            $copias, $script:TETO_DE_COPIAS)
    }
}

function ConvertTo-CaminhoComparavel([string]$Caminho) {
    <# O git escreve C:/x/y e o Windows C:\x\y: iguala barras e maiúsculas para comparar. #>
    ($Caminho -replace '\\', '/').TrimEnd('/').ToLowerInvariant()
}

function New-CopiaDoRepositorio([string]$Pasta, [string]$Ramo) {
    <# git worktree add <pasta> -b <ramo> origin/main. Se a pasta já é a cópia desse ramo, reaproveita. #>
    $alvo = ConvertTo-CaminhoComparavel $Pasta
    $existente = Get-Copias | Where-Object { (ConvertTo-CaminhoComparavel $_.Pasta) -eq $alvo } | Select-Object -First 1
    if ($existente) {
        if ($existente.Ramo -eq $Ramo) {
            Write-Host ("  a cópia já existe com o ramo {0}: reaproveitando." -f $Ramo)
            return
        }
        throw "A pasta $Pasta já é uma cópia do ramo '$($existente.Ramo)'. Escolha outro nome de tarefa."
    }
    if (Test-Path -LiteralPath $Pasta) { throw "A pasta $Pasta já existe e não é uma cópia do repositório." }
    Write-Host '  git fetch origin main...'
    & git -C $script:RaizDoRepositorio fetch origin main --quiet
    & git -C $script:RaizDoRepositorio worktree add $Pasta -b $Ramo origin/main
    if ($LASTEXITCODE -ne 0) {
        throw "git worktree add falhou (código $LASTEXITCODE). O ramo '$Ramo' já existe? Veja: git branch --list '$Ramo'."
    }
}

function Write-ArquivosDoLancador($Plano) {
    <# Grava o prompt (prompt.md) e o script da aba (abrir.ps1) na pasta dos lançadores, fora do repositório. #>
    New-Item -ItemType Directory -Path $Plano.PastaDoLancador -Force | Out-Null
    Set-Content -LiteralPath $Plano.ArquivoDoPrompt -Value $Plano.Prompt -Encoding utf8 -NoNewline
    $conteudo = Get-ConteudoDoLancador -Titulo $Plano.Titulo -Pasta $Plano.Pasta `
        -ArquivoDoPrompt $Plano.ArquivoDoPrompt -ArgumentosDoClaude $Plano.ArgumentosDoClaude
    Set-Content -LiteralPath $Plano.Lancador -Value $conteudo -Encoding utf8
}

function Start-AbaDoTerminal($Plano) {
    <# Aba nova na janela "tickerlab" do Windows Terminal; sem o wt, roda o lançador neste mesmo terminal. #>
    if (-not (Test-Ferramenta 'wt')) {
        Write-Aviso 'Windows Terminal (wt) não está no PATH: abrindo a conversa aqui mesmo.'
        & $Plano.Lancador
        return
    }
    $argumentos = Get-ArgumentosDoTerminal -Titulo $Plano.Titulo -Cor $Plano.Mesa.Cor -Pasta $Plano.Pasta -Lancador $Plano.Lancador
    & wt @argumentos
}
