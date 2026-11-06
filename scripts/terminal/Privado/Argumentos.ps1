# Monta as linhas de comando do claude e do Windows Terminal, o script da aba e o prompt de abertura, e
# traduz o que o usuário digitou depois de `tl <comando>` em parâmetros.

function ConvertTo-Parametros([string[]]$Tokens) {
    <# "Dados 'minha tarefa' -Modelo sonnet -SoMostrar" vira posicionais e nomeados prontos para o splat. #>
    $posicionais = [System.Collections.Generic.List[string]]::new()
    $nomeados = @{}
    for ($i = 0; $i -lt $Tokens.Count; $i++) {
        $token = $Tokens[$i]
        if ($token -notmatch '^-([A-Za-z]\w*)$') { $posicionais.Add($token); continue }
        $nome = $Matches[1]
        $temValor = ($i + 1 -lt $Tokens.Count) -and ($Tokens[$i + 1] -notmatch '^-[A-Za-z]')
        if ($temValor) { $nomeados[$nome] = $Tokens[$i + 1]; $i++ } else { $nomeados[$nome] = $true }
    }
    return @{ Posicionais = $posicionais.ToArray(); Nomeados = $nomeados }
}

function Get-ArgumentosDoClaude {
    <# Argumentos do `claude` para uma conversa nova: nome, modelo, modo de permissão e o prompt por último. #>
    param([string]$Nome, [string]$Modelo, [string]$ModoDePermissao, [string]$Prompt)
    $argumentos = [System.Collections.Generic.List[string]]::new()
    $argumentos.AddRange([string[]]@('--name', $Nome))
    if ($Modelo) { $argumentos.AddRange([string[]]@('--model', $Modelo)) }
    if ($ModoDePermissao -and $ModoDePermissao -ne 'default') {
        $argumentos.AddRange([string[]]@('--permission-mode', $ModoDePermissao))
    }
    if ($Prompt) { $argumentos.Add($Prompt) }
    return $argumentos.ToArray()
}

function Get-ArgumentosDoTerminal {
    <# Argumentos do `wt`: aba nova com título e cor da mesa, na janela do TickerLab, rodando o lançador. #>
    param([string]$Titulo, [string]$Cor, [string]$Pasta, [string]$Lancador)
    @(
        '-w', $script:JANELA_DO_TERMINAL, 'new-tab',
        '--title', $Titulo, '--tabColor', $Cor, '--suppressApplicationTitle',
        '-d', $Pasta,
        'pwsh', '-NoLogo', '-NoExit', '-File', $Lancador
    )
}

function ConvertTo-LinhaDeComando([string]$Programa, [string[]]$Argumentos) {
    <# Texto legível de um comando (para o modo só-mostrar), com aspas no que tem espaço. #>
    $citados = $Argumentos | ForEach-Object {
        if ($_ -match '\s') { "'" + ($_ -replace "'", "''") + "'" } else { $_ }
    }
    (@($Programa) + @($citados)) -join ' '
}

function Get-ConteudoDoLancador {
    <# O script que a aba roda: entra na cópia, dá o título e abre o claude com o prompt gravado ao lado.
       O prompt vai em arquivo porque a linha de comando do wt trata ";" como separador e tem limite. #>
    param([string]$Titulo, [string]$Pasta, [string]$ArquivoDoPrompt, [string[]]$ArgumentosDoClaude)
    $citar = { param($texto) "'" + ([string]$texto -replace "'", "''") + "'" }
    $argumentosCitados = ($ArgumentosDoClaude | ForEach-Object { & $citar $_ }) -join ' '
    @(
        "# Gerado por 'tl nova' em $(Get-Date -Format 'dd/MM/yyyy HH:mm'). Abre a conversa $(& $citar $Titulo)."
        "Set-Location -LiteralPath $(& $citar $Pasta)"
        "`$Host.UI.RawUI.WindowTitle = $(& $citar $Titulo)"
        "`$prompt = Get-Content -LiteralPath $(& $citar $ArquivoDoPrompt) -Raw -Encoding utf8"
        "& claude $argumentosCitados `$prompt"
    ) -join "`r`n"
}

function Get-PromptDeAbertura {
    <# Preenche o modelo Privado/prompt-de-abertura.md com mesa, tarefa, cópia, ramo e passagem. #>
    param([string]$Mesa, [string]$Tarefa, [string]$Copia, [string]$Ramo, [string]$Passagem)
    $modelo = Get-Content -LiteralPath (Join-Path $script:PastaDoModulo 'Privado/prompt-de-abertura.md') -Raw -Encoding utf8
    $textoDoRamo = if ($Ramo) {
        " (ramo ``$Ramo``, criado da ``origin/main``)"
    } else {
        ' (a pasta principal: crie um ramo antes de mexer em código; nunca faça commit na main)'
    }
    $textoDaPassagem = if ($Passagem) {
        "Leia a passagem ``$Passagem`` e execute a tarefa descrita, do começo ao fim."
    } else {
        'Não há passagem escrita: escreva a sua pela skill `passar-a-vez` como primeiro passo, a partir do plano ou da linha da fila.'
    }
    $valores = @{ MESA = $Mesa; TAREFA = $Tarefa; COPIA = $Copia; RAMO = $textoDoRamo; PASSAGEM = $textoDaPassagem }
    $texto = $modelo
    foreach ($chave in $valores.Keys) { $texto = $texto.Replace("{{$chave}}", [string]$valores[$chave]) }
    if ($texto -match '\{\{\w+\}\}') { throw "Sobrou um campo sem valor no prompt de abertura: $($Matches[0])" }
    return $texto.TrimEnd()
}
